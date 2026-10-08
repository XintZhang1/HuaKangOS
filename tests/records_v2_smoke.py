"""Focused V2 native-browser smoke against an already-running isolated fixture.

No app imports, server startup, production credentials, model calls or legacy CI.
Identity prerequisites use the original users API; positive V2 business writes
use rendered forms. Supplemental requests are reads, explicit rejection probes,
and one replay of the exact receipt command captured from its real UI submission.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import sys
from urllib.parse import urlsplit
import uuid

from playwright.async_api import async_playwright, expect


def require(value, message):
    if not value:
        raise AssertionError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def validate_manifest(path):
    path = path.resolve(strict=True)
    manifest = read_json(path)
    require(manifest.get('schema') == 1 and manifest.get('synthetic_data_only') is True,
            'Only a marked schema-1 synthetic fixture is accepted')
    origin = urlsplit(manifest['origin'])
    require(origin.scheme in {'http', 'https'} and origin.hostname in {'127.0.0.1', 'localhost', '::1'}
            and not origin.username and not origin.password and origin.path in {'', '/'}
            and not origin.query and not origin.fragment, 'Only a loopback fixture origin is accepted')
    repository = Path(__file__).resolve().parents[1]
    roots = {key: Path(manifest[key]).resolve(strict=True) for key in
             ('source_root', 'runtime_root', 'evidence_root', 'database_path', 'credentials_path')}
    for key, target in roots.items():
        require(not target.is_relative_to(repository), key + ' must be outside the workspace')
        require(target.is_relative_to(path.parent), key + ' must belong to this isolated fixture')
    require(roots['source_root'] != repository and (roots['source_root'] / 'web' / 'businessrecords.js').is_file(),
            'Fixture source must contain the V2 implementation')
    require(roots['database_path'].is_relative_to(roots['runtime_root']) and
            roots['credentials_path'].is_relative_to(roots['runtime_root']),
            'Database and random credentials must remain inside isolated runtime')
    credentials = read_json(roots['credentials_path'])
    require(credentials.get('synthetic_data_only') is True, 'Credentials must be synthetic')
    for role in ('admin', 'sales', 'sales_peer', 'finance', 'service'):
        require(role in credentials.get('users', {}) and credentials['users'][role].get('password'),
                'Required synthetic identity is missing: ' + role)
    executable = manifest['browser']['executable']
    require(Path(executable).is_file(), 'Fixture browser executable is missing')
    return manifest, credentials, roots, executable


class Smoke:
    def __init__(self, manifest, credentials, roots):
        self.manifest, self.credentials, self.roots = manifest, credentials, roots
        self.origin = manifest['origin'].rstrip('/')
        self.store = int(manifest['stores'][0]['id'])
        self.directory = roots['evidence_root'] / ('records-v2-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
        self.directory.mkdir(exist_ok=False)
        self.secret_values = [user['password'] for user in credentials['users'].values()]
        self.pages, self.contexts = {}, []
        self.active_page = None
        self.report = {'schema': 1, 'scope': 'V2 representative native-browser records flow',
                       'synthetic_data_only': True, 'full_193_acceptance': False,
                       'human_acceptance': 'pending', 'complete': False, 'passed': False,
                       'source_root': str(roots['source_root']), 'checks': [], 'page_errors': [],
                       'external_requests': [], 'browser_business_writes': [], 'artifacts': []}
        self.report['fingerprints'] = {str(path.relative_to(roots['source_root'])): hashlib.sha256(path.read_bytes()).hexdigest()
            for pattern in ('app/business_record*.py', 'web/businessrecords.*', 'web/app.js', 'web/charts.js')
            for path in roots['source_root'].glob(pattern)}
        self.report['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.save()

    def redact(self, value):
        text = str(value)
        for secret in self.secret_values:
            text = text.replace(secret, '[REDACTED]')
        return text

    def save(self):
        encoded = json.dumps(self.report, ensure_ascii=False, indent=2)
        (self.directory / 'report.json').write_text(self.redact(encoded) + '\n', encoding='utf-8')

    def check(self, name, **facts):
        self.report['checks'].append({'name': name, 'passed': True, **facts})
        self.save()

    async def screen(self, page, name):
        path = self.directory / (name + '.png')
        await page.screenshot(path=str(path), full_page=True)
        self.report['artifacts'].append({'name': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        self.save()

    async def headers(self, context):
        cookies = {cookie['name']: cookie['value'] for cookie in await context.cookies(self.origin)}
        require('dealer_csrf' in cookies, 'Authenticated CSRF cookie is missing')
        return {'X-App-Request': '1', 'X-Store-ID': str(self.store), 'X-CSRF-Token': cookies['dealer_csrf']}

    async def request(self, context, method, path, data=None):
        require(path.startswith('/api/') and '://' not in path and not path.startswith('//'), 'Only same-origin API probes are accepted')
        response = await context.request.fetch(self.origin + path, method=method,
            headers=await self.headers(context), data=data, max_redirects=0)
        return response

    async def login(self, browser, role):
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000},
            accept_downloads=True, service_workers='block')
        self.contexts.append(context)
        async def route(request_route):
            request = request_route.request
            target = urlsplit(request.url)
            if target.scheme not in {'http', 'https'} or target.netloc != urlsplit(self.origin).netloc:
                self.report['external_requests'].append(target.scheme + '://' + target.netloc + target.path)
                await request_route.abort('blockedbyclient')
            else:
                await request_route.continue_()
        await context.route('**/*', route)
        page = await context.new_page()
        page.set_default_timeout(15000)
        page.on('pageerror', lambda error: self.report['page_errors'].append(self.redact(error)))
        page.on('request', lambda request: self.report['browser_business_writes'].append(
            {'method': request.method, 'path': urlsplit(request.url).path})
            if request.method in {'POST', 'PUT', 'DELETE'} and '/api/business-records/' in request.url else None)
        self.pages[role] = page
        self.active_page = page
        await page.goto(self.origin + '/', wait_until='domcontentloaded')
        user = self.credentials['users'][role]
        async def sign_in():
            await page.locator('input[name=username]').fill(user['username'])
            await page.locator('input[name=password]').fill(user['password'])
            async with page.expect_response(lambda response: urlsplit(response.url).path == '/api/auth/login') as pending:
                await page.locator('form button[type=submit]').click()
            response = await pending.value
            require(response.status == 200, role + ' native login failed')
            return await response.json()
        info = await sign_in()
        if info.get('must_change_password'):
            new_password = secrets.token_urlsafe(28)
            self.secret_values.append(new_password)
            await page.locator('#modal input[name=current_password]').fill(user['password'])
            await page.locator('#modal input[name=new_password]').fill(new_password)
            async with page.expect_response(lambda response: urlsplit(response.url).path == '/api/auth/password') as pending:
                await page.locator('#modal button[type=submit]').click()
            require((await pending.value).status == 200, 'Required personal-password change failed')
            user['password'] = new_password
            await page.locator('input[name=username]').wait_for(state='visible')
            info = await sign_in()
        await expect(page.locator('#main h1')).to_have_text('经营看板')
        await page.locator('#br-chart svg').wait_for()
        cookies = {cookie['name']: cookie for cookie in await context.cookies(self.origin)}
        require(cookies.get('dealer_session', {}).get('httpOnly') is True, 'Session cookie is not HttpOnly')
        require(cookies.get('dealer_session', {}).get('sameSite') == 'Strict', 'Session cookie is not SameSite=Strict')
        return page, context, info

    async def nav(self, page, route, heading=None):
        self.active_page = page
        await page.goto(self.origin + '/#' + route, wait_until='domcontentloaded')
        await page.locator('#main h1').wait_for()
        if heading:
            await expect(page.locator('#main h1')).to_contain_text(heading)

    async def submit(self, page, path):
        self.active_page = page
        async with page.expect_response(lambda response: urlsplit(response.url).path == path
                and response.request.method in {'POST', 'PUT'}) as pending:
            await page.locator('#modal button[type=submit]').click()
        response = await pending.value
        require(response.status in {200, 201}, 'Business UI submission failed: ' + path + ' [' + str(response.status) + '] ' + self.redact(await response.text()))
        result = await response.json()
        await expect(page.locator('#modal')).not_to_be_visible()
        return result, response.request.post_data_json

    async def fill(self, page, values):
        self.active_page = page
        for name, value in values.items():
            await page.locator('#modal [name="' + name + '"]').fill(str(value))

    async def run(self, browser):
        today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        suffix = uuid.uuid4().hex[:8]
        admin_page, admin_context, _ = await self.login(browser, 'admin')
        for role, label in (('clerk', '合成内勤'), ('general_manager', '合成总经理')):
            user = {'username': 'record_' + role + '_' + suffix, 'password': secrets.token_urlsafe(28)}
            self.secret_values.append(user['password'])
            response = await self.request(admin_context, 'POST', '/api/users', {
                **user, 'display_name': label, 'role': role, 'store_ids': [self.store],
                'store_roles': [{'store_id': self.store, 'role': role}], 'can_group_summary': False})
            require(response.status == 201, 'Synthetic identity prerequisite failed: ' + role)
            self.credentials['users'][role] = user
        self.check('original API creates synthetic clerk and general-manager identities')

        sales, sales_context, sales_info = await self.login(browser, 'sales')
        await self.nav(sales, 'records-customers', '客户信息')
        await sales.locator('[data-br=new-customer]').click()
        await self.fill(sales, {'name': '合成客户-' + suffix, 'phone': '19900000101', 'note': 'V2隔离浏览器合成记录'})
        await self.submit(sales, '/api/business-records/customers')
        await self.nav(sales, 'records-sales', '销售业务')
        await sales.locator('[data-br=new-contract]').click()
        await self.fill(sales, {'customer_name': '合成客户-' + suffix, 'customer_phone': '19900000101',
            'contract_date': today, 'brand': '合成自由品牌', 'model': '无需车型档案的合成车型',
            'vin': 'SYNTHETIC' + suffix.upper(), 'sale_price': '150000.01',
            'gift_description': '合成脚垫与保养服务，由内勤核定成本', 'seller_name': '合成一店',
            'buyer_document_name': '合成证件', 'buyer_id_number': 'SYNTHETIC-' + suffix,
            'signature_date': today, 'delivery_place': '合成交付地点', 'deposit': '1000.00'})
        await sales.locator('#modal select[name=payment_method]').select_option('全款')
        await sales.locator('#modal select[name=salesperson_id]').select_option(str(sales_info['id']))
        # Explicitly leave and resume the current memory-only form once.
        await sales.locator('[data-br=defer-form]').click()
        await sales.locator('[data-br=new-contract]').click()
        await expect(sales.locator('#modal [name=customer_name]')).to_have_value('合成客户-' + suffix)
        contract, _ = await self.submit(sales, '/api/business-records/contracts')
        key, number = contract['id'], contract['number']
        await expect(sales.locator('#main h1')).to_contain_text(number)
        await expect(sales.locator('[data-action=print]')).to_have_count(0)
        self.check('customer and freeform contract created through UI, draft restored', contract_id=key,
                   sale_price_cents=contract['sale_price_cents'])
        before_print = await self.request(sales_context, 'GET', f'/api/business-records/contracts/{key}/print')
        require(before_print.status == 409, 'Printing an unapproved contract was not rejected')
        forbidden = await self.request(sales_context, 'POST', f'/api/business-records/contracts/{key}/price-review',
            {'request_id': 'negative_' + uuid.uuid4().hex, 'version': contract['version'],
             'expected_amount_cents': 15000001, 'cost_cents': 13000000, 'profit_cents': 2000001, 'gift_cost_cents': 50000, 'note': ''})
        require(forbidden.status == 403, 'Sales was allowed to price a contract')
        peer, peer_context, _ = await self.login(browser, 'sales_peer')
        peer_read = await self.request(peer_context, 'GET', f'/api/business-records/contracts/{key}')
        require(peer_read.status == 404, 'Peer sales could read another salesperson contract')
        self.check('negative guards', print_before_approval=409, sales_price_review=403, peer_contract=404)

        clerk, clerk_context, _ = await self.login(browser, 'clerk')
        await self.nav(clerk, 'records-sales/' + str(key), number)
        await clerk.locator('[data-action=price_review]').click()
        await self.fill(clerk, {'expected_amount': '150000.01', 'cost': '130000.00', 'profit': '20000.01',
                              'gift_cost': '500.00', 'note': '合成内勤人工核价'})
        priced, _ = await self.submit(clerk, f'/api/business-records/contracts/{key}/price-review')
        require(priced['status'] == 'priced', 'Price review did not enter the management-approval stage')
        await expect(clerk.locator('[data-action=print]')).to_have_count(0)
        manager, manager_context, _ = await self.login(browser, 'general_manager')
        await self.nav(manager, 'records-sales/' + str(key), number)
        await manager.locator('[data-action=approve]').click()
        await self.fill(manager, {'note': '合成管理审批通过'})
        approved, _ = await self.submit(manager, f'/api/business-records/contracts/{key}/approve')
        require(approved['status'] == 'approved', 'Management approval did not release the contract')
        async with manager.expect_download() as pending:
            await manager.locator('[data-action=print]').click()
        pdf_path = self.directory / 'approved-contract.pdf'
        await (await pending.value).save_as(str(pdf_path))
        require(pdf_path.read_bytes().startswith(b'%PDF'), 'Printed artifact is not PDF')
        from pypdf import PdfReader
        require(len(PdfReader(pdf_path).pages) == 2, 'Printed contract does not preserve the two-page template')
        self.report['artifacts'].append({'name': pdf_path.name, 'sha256': hashlib.sha256(pdf_path.read_bytes()).hexdigest(), 'pages': 2})
        await self.screen(manager, 'approved-contract')
        self.check('manual pricing then management approval releases two-page PDF')

        finance, finance_context, _ = await self.login(browser, 'finance')
        await self.nav(finance, 'records-finance', '财务流水')
        await finance.locator('a[href="#records-sales/' + str(key) + '"]').click()
        await finance.locator('[data-action=receipt]').click()
        await self.fill(finance, {'actual_amount': '149000.01', 'received_on': today, 'note': '合成财务线下核实汇总到账'})
        receipt, receipt_body = await self.submit(finance, f'/api/business-records/contracts/{key}/receipt')
        require(receipt['actual_amount_cents'] == 14900001 and receipt['received_on'] == today, 'Receipt lost actual amount/date')
        replay = await self.request(finance_context, 'POST', f'/api/business-records/contracts/{key}/receipt', receipt_body)
        require(replay.status == 200 and (await replay.json())['receipt']['id'] == receipt['receipt']['id'], 'Exact original receipt command did not replay its original result')
        with sqlite3.connect(self.roots['database_path'].as_uri() + '?mode=ro', uri=True) as db:
            db.execute('PRAGMA query_only=ON')
            require(db.execute('SELECT count(*) FROM business_record_receipts WHERE contract_id=?', (key,)).fetchone()[0] == 1,
                    'Receipt replay created duplicate rows')
        await self.screen(finance, 'confirmed-receipt')
        self.check('finance UI confirms actual amount/date; exact request replay creates one receipt')

        await self.nav(manager, 'records-dashboard', '经营看板')
        for report_key, expected in (('expected_receipts', '150000.01'), ('actual_receipts', '149000.01'), ('profit', '20000.01'), ('sales_volume', '1')):
            await manager.locator('#br-report-filter select[name=report]').select_option(report_key)
            await manager.locator('#br-report-filter select[name=group_by]').select_option('salesperson')
            await manager.locator('#br-report-filter select[name=salesperson_id]').select_option(str(sales_info['id']))
            async with manager.expect_response(lambda response: urlsplit(response.url).path == '/api/business-records/reports') as pending:
                await manager.locator('#br-report-filter button[type=submit]').click()
            response = await pending.value
            require(response.status == 200, 'Report query failed')
            report = await response.json()
            matching = [row for row in report['rows'] if row.get('id') == key]
            require(len(matching) == 1 and matching[0]['value'] == expected, 'Report lost the original amount: ' + report_key)
            await expect(manager.locator('#br-chart svg')).to_have_count(1)
            await manager.locator('.br-disclosure summary').click()
            await expect(manager.locator('.br-disclosure table')).to_be_visible()
            await expect(manager.locator('.br-disclosure table')).to_contain_text(expected)
        async with manager.expect_download() as pending:
            await manager.locator('[data-br=export-report]').click()
        csv_path = self.directory / 'sales-volume.csv'
        await (await pending.value).save_as(str(csv_path))
        require(number in csv_path.read_text(encoding='utf-8-sig'), 'Export omitted the visible contract')
        await self.screen(manager, 'single-chart-and-details')
        self.check('four contract reports keep expected/actual amounts separate, single chart and CSV same scope')

        service, service_context, _ = await self.login(browser, 'service')
        catalog_response = await self.request(service_context, 'GET', '/api/business-records/catalog')
        service_catalog = await catalog_response.json()
        require(len(service_catalog['service_types']) == 6, 'Expected exactly six service record types')
        await self.nav(service, 'records-after-sales', '售后业务')
        for kind in service_catalog['service_types']:
            await service.locator('[data-br=new-after-sales]').click()
            await service.locator('#modal select[name=service_type]').select_option(kind['value'])
            await self.fill(service, {'business_date': today, 'customer_name': '合成售后-' + suffix,
                'vehicle': '合成车牌-' + suffix, 'brand': '合成品牌', 'service_items': kind['label'] + '合成服务',
                'materials': '100.01', 'labor': '200.02', 'cost': '80.00', 'handler_name': '合成服务顾问'})
            await self.submit(service, '/api/business-records/after-sales')
        await self.screen(service, 'six-service-types')
        self.check('six service types submitted through UI', count=6)

        catalog_response = await self.request(clerk_context, 'GET', '/api/business-records/catalog')
        catalog = await catalog_response.json()
        manual = [item for item in catalog['reports'] if item['source'] == 'manual']
        require(manual, 'Manual report catalog is empty')
        await self.nav(clerk, 'records-manual', '统计填报')
        for spec in manual:
            await clerk.locator('[data-br=new-manual]').click()
            await clerk.locator('[data-br=manual-report-select][data-report="' + spec['key'] + '"]').click()
            for column in spec['columns']:
                await expect(clerk.locator('#modal [name="value_' + column['key'] + '"]')).to_have_count(1)
            await clerk.locator('[data-br=defer-form]').click()
        specimen = next((item for item in manual if any(c['type'] == 'money' for c in item['columns']) and
                         any(c['type'] == 'percent' for c in item['columns'])), manual[0])
        await clerk.locator('[data-br=new-manual]').click()
        await clerk.locator('[data-br=manual-report-select][data-report="' + specimen['key'] + '"]').click()
        values = {'period': today, 'brand': '合成统计品牌'}
        filled = []
        for column in specimen['columns']:
            if column['type'] in {'money', 'percent', 'count'}:
                values['value_' + column['key']] = {'money': '12345.67', 'percent': '15.25', 'count': '3'}[column['type']]
                filled.append(column['key'])
                if len(filled) == 3:
                    break
        require(filled, 'Representative manual report has no numeric fields')
        await self.fill(clerk, values)
        manual_record, _ = await self.submit(clerk, '/api/business-records/manual-reports')
        require(all(manual_record['values'][key] == values['value_' + key] for key in filled), 'Manual numeric values were rounded or changed')
        await self.screen(clerk, 'manual-statistics')
        self.check('all manual report forms preserve catalog fields; one representative record submitted',
                   forms=len(manual), columns=sum(len(item['columns']) for item in manual), submitted_report=specimen['key'])
        require(not self.report['page_errors'], 'Browser page errors occurred')
        require(not self.report['external_requests'], 'External network requests were attempted')
        self.report.update(complete=True, passed=True)
        self.save()


async def execute(manifest, credentials, roots, executable):
    smoke = Smoke(manifest, credentials, roots)
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(executable_path=executable, headless=True)
            try:
                await asyncio.wait_for(smoke.run(browser), timeout=480)
            except BaseException:
                page = smoke.active_page
                if page is not None and not page.is_closed():
                    try:
                        if await page.locator('#store').count():
                            await smoke.screen(page, 'failure-page')
                    except Exception:
                        pass
                raise
            finally:
                await browser.close()
    except BaseException as error:
        smoke.report['failure'] = smoke.redact(type(error).__name__ + ': ' + str(error))
        smoke.report.update(complete=False, passed=False)
    finally:
        smoke.save()
    print(json.dumps({'passed': smoke.report['passed'], 'report': str(smoke.directory / 'report.json'),
                      'completed_checks': len(smoke.report['checks'])}, ensure_ascii=False))
    return 0 if smoke.report['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    args = parser.parse_args()
    manifest, credentials, roots, executable = validate_manifest(args.manifest)
    return asyncio.run(execute(manifest, credentials, roots, executable))


if __name__ == '__main__':
    sys.exit(main())
