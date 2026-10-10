"""Customer-feedback checks against a marked, external, synthetic HTTP fixture.

Start tests/browser_click/run.py --serve with a fresh external --output first.
This runner never imports app code or reads deployment configuration. All local
evidence and synthetic credentials stay in that fixture. HTTP checks are reported
separately from real Chromium form operations; neither is full legacy acceptance.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import sys
from urllib.parse import urlsplit
import uuid

import httpx
from playwright.async_api import async_playwright, expect


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def request_id():
    return 'feedback_' + uuid.uuid4().hex


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_fixture(path):
    path = path.resolve(strict=True)
    manifest = json.loads(path.read_text(encoding='utf-8'))
    require(manifest.get('schema') == 1 and manifest.get('synthetic_data_only') is True,
            'Only a schema-1, explicitly synthetic fixture is accepted')
    origin = urlsplit(manifest['origin'])
    require(origin.scheme == 'http' and origin.hostname in {'127.0.0.1', 'localhost', '::1'}
            and not origin.username and not origin.password and not origin.query
            and not origin.fragment and origin.path in {'', '/'}, 'Loopback HTTP is required')
    repository = Path(__file__).resolve().parents[1]
    for name in ('source_root', 'runtime_root', 'evidence_root', 'database_path', 'credentials_path'):
        target = Path(manifest[name]).resolve(strict=True)
        require(target.is_relative_to(path.parent) and not target.is_relative_to(repository),
                name + ' must belong to the external fixture')
    require(Path(manifest['database_path']).is_relative_to(Path(manifest['runtime_root'])),
            'Synthetic database must be inside fixture runtime')
    credentials = json.loads(Path(manifest['credentials_path']).read_text(encoding='utf-8'))
    require(credentials.get('synthetic_data_only') is True, 'Synthetic credentials required')
    require(Path(manifest['browser']['executable']).is_file(), 'Browser is missing')
    return manifest, credentials


class FeedbackChecks:
    def __init__(self, manifest, credentials):
        self.manifest, self.credentials = manifest, credentials
        self.origin = manifest['origin'].rstrip('/')
        self.clients, self.identities = {}, {}
        self.extra_secrets = []
        self.browser_api_requests = []
        self.active_page = None
        self.store = int(manifest['stores'][0]['id'])
        self.second_store = int(manifest['stores'][1]['id'])
        self.today = datetime.now(timezone.utc).date().isoformat()
        self.suffix = uuid.uuid4().hex[:8]
        self.directory = Path(manifest['evidence_root']) / ('feedback-' + self.suffix)
        self.directory.mkdir(exist_ok=False)
        self.report = {'schema': 1, 'synthetic_data_only': True, 'complete': False, 'passed': False,
                       'scope': '2026-10 customer feedback, focused HTTP and native-browser checks',
                       'full_193_acceptance': False, 'employee_acceptance': 'not_run',
                       'real_model_calls': 0, 'checks': [], 'page_errors': [],
                       'external_requests': [], 'artifacts': [], 'fixture_mutations': [],
                       'script_sha256': digest(Path(__file__)),
                       'source_provenance_sha256': digest(Path(manifest['evidence_root']) / 'provenance.json')}
        self.save()

    def redact(self, value):
        result = str(value)
        for user in self.credentials['users'].values():
            result = result.replace(user['password'], '[REDACTED]')
        for value in self.extra_secrets:
            result = result.replace(value, '[REDACTED]')
        return result

    def save(self):
        (self.directory / 'report.json').write_text(
            self.redact(json.dumps(self.report, ensure_ascii=False, indent=2)) + '\n', encoding='utf-8')

    def check(self, name, **facts):
        self.report['checks'].append({'name': name, 'passed': True, **facts})
        self.save()

    def response(self, role, method, path, payload=None, expected=200, store=None):
        require(path.startswith('/api/') and '://' not in path and not path.startswith('//'),
                'Requests must use a same-origin API path')
        client = self.clients[role]
        if isinstance(payload, dict):
            self.extra_secrets.extend(str(payload[key]) for key in ('password', 'current_password', 'new_password')
                                      if payload.get(key))
        headers = {'X-App-Request': '1', 'X-Store-ID': str(store or self.store)}
        csrf = client.cookies.get('dealer_csrf')
        if csrf:
            headers['X-CSRF-Token'] = csrf
        response = client.request(method, path, json=payload, headers=headers)
        require(response.status_code == expected,
                f'{role} {method} {path}: expected {expected}, got {response.status_code}: '
                + self.redact(response.text[:1600]))
        return response

    def api(self, role, method, path, payload=None, expected=200, store=None):
        return self.response(role, method, path, payload, expected, store).json()

    def login(self, role, store=None):
        user = self.credentials['users'][role]
        self.clients[role] = httpx.Client(base_url=self.origin, timeout=30, trust_env=False,
                                          follow_redirects=False)
        info = self.api(role, 'POST', '/api/auth/login', user, store=store)
        if info['must_change_password']:
            replacement = secrets.token_urlsafe(28)
            self.api(role, 'POST', '/api/auth/password', {
                'current_password': user['password'], 'new_password': replacement}, store=store)
            user['password'] = replacement
            credential_path = Path(self.manifest['credentials_path'])
            credential_path.write_text(json.dumps(self.credentials, ensure_ascii=False), encoding='utf-8')
            credential_path.chmod(0o600)
            info = self.api(role, 'POST', '/api/auth/login', user, store=store)
        self.identities[role] = info
        return info

    def setup(self):
        self.login('admin')
        for role in ('sales', 'sales_peer', 'manager', 'finance'):
            self.login(role)
        for key, role, store in [('clerk', 'clerk', self.store),
                                 ('general_manager', 'general_manager', self.store),
                                 ('group_deputy_manager', 'group_deputy_manager', self.store),
                                 ('chairman', 'chairman', self.store),
                                 ('store_admin', 'store_admin', self.store),
                                 ('store_admin_peer', 'store_admin', self.store),
                                 ('other_sales', 'sales', self.second_store),
                                 ('other_manager', 'manager', self.second_store)]:
            user = {'username': 'feedback_' + key[:14] + '_' + self.suffix,
                    'password': secrets.token_urlsafe(28)}
            self.api('admin', 'POST', '/api/users', {**user, 'display_name': '合成验证-' + key,
                'role': role, 'store_ids': [store], 'store_roles': [{'store_id': store, 'role': role}],
                'can_group_summary': False}, expected=201)
            self.credentials['users'][key] = user
            self.login(key, store=store)
        users = self.api('admin', 'GET', '/api/users')
        require(users['roles']['manager'] == '销售经理', 'Manager role label was not updated')
        require(users['roles']['clerk'] == '销售内勤', 'Clerk role label was not updated')
        require(users['roles']['group_deputy_manager'] == '集团副总经理', 'Independent deputy role missing')
        require(users['roles']['store_admin'] == '门店管理员', 'Store administrator role label missing')
        self.check('original account API and Chinese role labels', transport='HTTP')

    def cache_integration(self):
        with httpx.Client(base_url=self.origin, trust_env=False, timeout=30) as client:
            home = client.get('/')
            direct = client.get('/static/index.html')
            version = client.get('/api/app-version')
            require(home.status_code == direct.status_code == version.status_code == 200,
                    'Current app cache entry points are unavailable')
            require(all(response.headers.get('cache-control') == 'no-store'
                        for response in (home, direct, version)), 'HTML or release API can retain stale cache')
            require(home.text == direct.text and version.json()['version'] in home.text,
                    'Document entry points and release API disagree')
            assets = re.findall(r'(?:src|href)="(/static/[^\"]+)"', home.text)
            require(assets and all(re.search(r'\?v=[a-f0-9]{64}$', url) for url in assets),
                    'Current app did not version every local script/style URL')
            asset = client.get(next(url for url in assets if '/appversion.js?' in url))
            require(asset.headers.get('etag') == '"' + hashlib.sha256(asset.content).hexdigest() + '"',
                    'Static ETag does not identify actual bytes')
            require(asset.headers.get('cache-control') == 'no-cache, max-age=0, must-revalidate'
                    and asset.headers.get('content-security-policy'), 'Static revalidation/CSP guard is absent')
        self.check('real app dynamic HTML, release API, automatic asset hashes, ETag, CSP and cache headers', transport='HTTP')

    def contract(self, *, sale_price=10000, creator='sales', store=None, marker=None):
        body = {'request_id': request_id(), 'customer_name': '合成反馈客户-' + self.suffix,
                'customer_phone': '', 'brand': '合成品牌', 'model': '合成车型',
                'vin': 'SYNTHETIC-' + uuid.uuid4().hex[:16], 'salesperson_id': self.identities['sales']['id'],
                'contract_date': self.today, 'sale_price_cents': sale_price,
                'gift_description': '合成赠送约定', 'form_data': {}}
        if marker:
            body.update(customer_name=marker, brand=marker, model=marker)
        row = self.api(creator, 'POST', '/api/business-records/contracts', body, expected=201, store=store)
        require(row['workflow_version'] == 'trial-v30', 'New contracts must use the feedback workflow')
        return row, body

    def action(self, role, row, action, *, extra=None, expected=200, store=None):
        return self.api(role, 'POST', f'/api/business-records/contracts/{row["id"]}/{action}',
                        {'request_id': request_id(), 'version': row['version'], 'note': '合成边界核对',
                         **(extra or {})}, expected=expected, store=store)

    def replayed_action(self, role, row, action, extra=None):
        path = f'/api/business-records/contracts/{row["id"]}/{action}'
        body = {'request_id': request_id(), 'version': row['version'], 'note': '合成幂等审批', **(extra or {})}
        result = self.api(role, 'POST', path, body)
        replay = self.api(role, 'POST', path, body)
        require(result == replay, action + ' replay did not return its original result')
        self.api(role, 'POST', path, {**body, 'note': '同请求不同内容'}, expected=409)
        return result

    @staticmethod
    def limits(**changes):
        return {'minimum_sale_price_cents': 10000, 'gift_limit_cents': 100,
                'offered_gift_value_cents': 100, 'approval_basis': '合成书面限额核对', **changes}

    def contract_checks(self):
        row, body = self.contract()
        base = f'/api/business-records/contracts/{row["id"]}'
        self.action('general_manager', row, 'approve', expected=409)
        self.action('group_deputy_manager', row, 'deputy-approve', expected=409)
        self.action('sales', row, 'manager-approve', extra=self.limits(), expected=403)
        self.api('sales_peer', 'GET', base, expected=404)
        self.api('other_manager', 'GET', base, expected=404, store=self.second_store)
        self.action('other_manager', row, 'manager-approve', extra=self.limits(), expected=404,
                    store=self.second_store)
        self.response('sales', 'GET', base + '/print', expected=409)
        for omitted in ('minimum_sale_price_cents', 'gift_limit_cents', 'offered_gift_value_cents'):
            values = self.limits()
            values.pop(omitted)
            self.action('manager', row, 'manager-approve', extra=values, expected=422)
            self.action('manager', row, 'manager-approve', extra=self.limits(**{omitted: None}), expected=422)
        self.action('manager', row, 'manager-approve', extra=self.limits(approval_basis=''), expected=422)
        self.action('manager', row, 'manager-approve', extra=self.limits(gift_limit_cents=1.5), expected=422)
        self.check('ordered approvals, missing/unknown limits, integer cents, store and sales ownership guards', transport='HTTP')

        row = self.replayed_action('manager', row, 'manager-approve', self.limits())
        require(row['status'] == 'manager_approved' and row['approval_limits']['requires_deputy'] is False,
                'Exact price/gift boundary incorrectly escalated')
        self.action('manager', row, 'approve', expected=403)
        row = self.replayed_action('general_manager', row, 'approve')
        require(row['status'] == 'approved' and 'print' in row['actions'], 'Normal contract was not released')
        pdf = self.response('sales', 'GET', base + '/print')
        require(pdf.content.startswith(b'%PDF'), 'Approved download is not a PDF')
        (self.directory / 'approved-contract.pdf').write_bytes(pdf.content)
        self.api('sales', 'PUT', base, {**body, 'request_id': request_id(), 'version': row['version']}, expected=409)
        self.action('group_deputy_manager', row, 'deputy-approve', expected=409)
        self.check('equal limits need only sales manager and GM; approved contract prints and locks', transport='HTTP')
        self.approved = row

        for name, price, limits in [('below_price', 9999, self.limits()),
                                    ('above_gift', 10000, self.limits(offered_gift_value_cents=101)),
                                    ('both_exceeded', 9999, self.limits(offered_gift_value_cents=101))]:
            candidate, _ = self.contract(sale_price=price)
            candidate = self.action('manager', candidate, 'manager-approve', extra=limits)
            require(candidate['approval_limits']['requires_deputy'] is True, name + ' did not escalate')
            candidate = self.action('general_manager', candidate, 'approve')
            require(candidate['status'] == 'deputy_pending', name + ' skipped deputy review')
            self.response('sales', 'GET', f'/api/business-records/contracts/{candidate["id"]}/print', expected=409)
            self.action('chairman', candidate, 'deputy-approve', expected=403)
            candidate = self.replayed_action('group_deputy_manager', candidate, 'deputy-approve')
            require(candidate['status'] == 'approved', name + ' failed independent final approval')
        self.check('strict price/gift excess escalates; chairman cannot substitute for deputy', transport='HTTP')

        zero, _ = self.contract()
        zero = self.action('manager', zero, 'manager-approve', extra=self.limits(
            minimum_sale_price_cents=0, gift_limit_cents=0, offered_gift_value_cents=0))
        require(zero['approval_limits']['requires_deputy'] is False, 'Explicit zero was treated as unknown')
        own, _ = self.contract(creator='admin')
        self.action('admin', own, 'manager-approve', extra=self.limits(), expected=403)
        own = self.action('manager', own, 'manager-approve', extra=self.limits())
        self.action('admin', own, 'approve', expected=403)
        same, _ = self.contract()
        same = self.action('admin', same, 'manager-approve', extra=self.limits())
        self.action('admin', same, 'approve', expected=403)
        third, _ = self.contract(sale_price=9999)
        third = self.action('manager', third, 'manager-approve', extra=self.limits())
        third = self.action('admin', third, 'approve')
        self.action('admin', third, 'deputy-approve', expected=403)
        self.check('explicit zero accepted and creator/prior approver cannot self-approve', transport='HTTP')

        returned, original = self.contract(sale_price=9999)
        returned = self.action('manager', returned, 'manager-approve', extra=self.limits())
        returned = self.action('general_manager', returned, 'approve')
        returned = self.action('group_deputy_manager', returned, 'reject')
        require(returned['status'] == 'rejected', 'Deputy cannot return an excess contract')
        returned = self.api('sales', 'PUT', f'/api/business-records/contracts/{returned["id"]}',
                           {**original, 'request_id': request_id(), 'version': returned['version']})
        require(returned['status'] == 'submitted' and returned['approval_limits'] is None
                and all(returned.get(field) is None for field in
                        ('manager_approved_by', 'general_manager_approved_by', 'deputy_approved_by')),
                'Resubmission retained stale limits or approval identities')
        returned = self.action('manager', returned, 'manager-approve', extra=self.limits())
        returned = self.action('general_manager', returned, 'approve')
        returned = self.action('group_deputy_manager', returned, 'deputy-approve')
        require(returned['status'] == 'approved', 'Returned contract cannot repeat the whole approval chain')
        daily = self.api('clerk', 'GET', '/api/business-records/daily-vehicle-reports?day=' + self.today)
        changes = next(item['changes'] for item in daily['rows'] if item['contract_id'] == returned['id'])
        deputy = [item for item in changes if item['action'] == 'record_deputy_approve']
        require(len(deputy) == 1 and '集团副总经理' in deputy[0]['label'],
                'Daily vehicle updates omitted deputy approval')
        require(all('可打印' not in item['label'] for item in changes if item['action'] == 'record_approve'),
                'Daily GM event incorrectly promises printing before deputy approval')
        self.check('all new approval steps replay safely; return/resubmit clears prior approvals and reruns chain',
                   transport='HTTP')
        self.check('daily vehicle updates include deputy completion without claiming GM already released printing', transport='HTTP')

    def legacy_checks(self):
        # Only new synthetic rows created above are converted into historical
        # fixture inputs. No production database or existing business row is read.
        for workflow in ('trial-v29', 'legacy-v2'):
            row, _ = self.contract()
            with sqlite3.connect(self.manifest['database_path']) as db:
                updated = db.execute('UPDATE business_record_contracts SET workflow_version=? '
                    'WHERE id=? AND status=? AND workflow_version=?',
                    (workflow, row['id'], 'submitted', 'trial-v30')).rowcount
                require(updated == 1, 'Historical synthetic fixture conversion failed')
            self.report['fixture_mutations'].append({'contract_id': row['id'], 'workflow_version': workflow,
                                                    'purpose': 'historical contract compatibility input'})
            if workflow == 'trial-v29':
                row = self.action('manager', row, 'manager-approve')
            else:
                row = self.action('clerk', row, 'price-review', extra={
                    'expected_amount_cents': 10000, 'cost_cents': 7000,
                    'profit_cents': 2000, 'gift_cost_cents': 100})
            row = self.action('general_manager', row, 'approve')
            require(row['status'] == 'approved', workflow + ' stopped following its preserved workflow')
            self.response('sales', 'GET', f'/api/business-records/contracts/{row["id"]}/print')
        self.check('both historical workflow versions still approve and print', transport='HTTP')

    def office_checks(self):
        row = self.approved
        catalog = self.api('clerk', 'GET', '/api/business-records/catalog?report_key=vehicle_details')
        self.office_spec = catalog['reports'][0]
        fields = {item['label']: item['key'] for item in self.office_spec['columns']}
        self.profit_key, self.gift_key = fields['核定单车利润'], fields['精品成本（赠送）']
        self.commission_key = fields['银行返佣']
        path = f'/api/business-records/contracts/{row["id"]}/office-review'
        body = {'request_id': request_id(), 'version': row['version'], 'report_key': 'vehicle_details',
                'period': self.today, 'values': {}, 'expected_amount_cents': None,
                'cost_cents': None, 'profit_cents': None, 'gift_cost_cents': None,
                'note': '合成未知成本保持空白'}
        row = self.api('clerk', 'PUT', path, body)
        require(all(row['office_data'][field] is None for field in
                    ('cost_cents', 'profit_cents', 'gift_cost_cents')), 'Unknown manual costs became zero')
        conflicting = {**body, 'request_id': request_id(), 'version': row['version'],
                       'profit_cents': 12345, 'values': {self.profit_key: '123.46'}}
        self.api('clerk', 'PUT', path, conflicting, expected=422)
        body.update(request_id=request_id(), version=row['version'], cost_cents=999,
                    profit_cents=12345, gift_cost_cents=500,
                    values={self.commission_key: '67.89'}, note='合成核定结果，不从成本自动反推')
        row = self.api('clerk', 'PUT', path, body)
        office = row['office_data']
        require(Decimal(office['values'][self.profit_key]) == Decimal('123.45')
                and Decimal(office['values'][self.gift_key]) == Decimal('5.00'),
                'Top amounts do not mirror the original detail columns exactly')
        require(office['profit_cents'] == 12345 and office['cost_cents'] == 999,
                'Independent manual profit was overwritten by an invented formula')
        row = self.action('clerk', row, 'office-submit')
        manager_view = self.api('general_manager', 'GET', f'/api/business-records/contracts/{row["id"]}')
        visible = manager_view['office_data']
        require(visible['sensitive_fields_hidden'] is False,
                'Authorized GM still receives a restricted office review')
        require(visible['cost_cents'] == 999 and visible['profit_cents'] == 12345
                and visible['gift_cost_cents'] == 500
                and Decimal(visible['values'][self.commission_key]) == Decimal('67.89')
                and Decimal(visible['values'][self.profit_key]) == Decimal('123.45')
                and Decimal(visible['values'][self.gift_key]) == Decimal('5.00'),
                'GM cannot see all exact nonzero cost, profit, gift and commission review values')
        require(visible['note'] == body['note'], 'GM cannot see the submitted pricing explanation')
        row = self.action('general_manager', row, 'office-approve')
        for role in ('clerk', 'chairman', 'admin', 'general_manager'):
            full = self.api(role, 'GET', f'/api/business-records/contracts/{row["id"]}')
            require(full['cost_cents'] == 999 and full['profit_cents'] == 12345
                    and full['gift_cost_cents'] == 500, role + ' lost full financial review values')
        for role in ('sales', 'manager', 'finance', 'group_deputy_manager'):
            restricted = self.api(role, 'GET', f'/api/business-records/contracts/{row["id"]}')
            require(not any(key in restricted for key in ('cost_cents', 'profit_cents', 'gift_cost_cents')),
                    role + ' incorrectly inherited the newly authorized GM financial access')
            require(self.commission_key not in restricted.get('office_data', {}).get('values', {}),
                    role + ' can see GM-only pricing commission details')
        self.approved = self.api('clerk', 'GET', f'/api/business-records/contracts/{row["id"]}')
        self.check('unknown/manual amounts, mirrors, mismatch rejection, full GM pricing and unchanged lower-role restrictions',
                   transport='HTTP')

    async def native_login(self, browser, role):
        context = await browser.new_context(viewport={'width': 1440, 'height': 1050},
                                            service_workers='block', accept_downloads=True)
        async def route(request_route):
            destination = urlsplit(request_route.request.url)
            if destination.netloc != urlsplit(self.origin).netloc or destination.scheme != 'http':
                self.report['external_requests'].append(destination.scheme + '://' + destination.netloc)
                await request_route.abort()
            else:
                await request_route.continue_()
        await context.route('**/*', route)
        context.on('request', lambda request: self.browser_api_requests.append(
            (role, request.method, urlsplit(request.url).path)) if '/api/' in request.url else None)
        page = await context.new_page()
        self.active_page = page
        page.set_default_timeout(15000)
        page.on('pageerror', lambda error: self.report['page_errors'].append(self.redact(error)))
        await page.goto(self.origin + '/', wait_until='domcontentloaded')
        await page.locator('input[name=username]').fill(self.credentials['users'][role]['username'])
        await page.locator('input[name=password]').fill(self.credentials['users'][role]['password'])
        async with page.expect_response(lambda response: urlsplit(response.url).path == '/api/auth/login') as pending:
            await page.locator('form button[type=submit]').click()
        require((await pending.value).status == 200, role + ' native login failed')
        await page.locator('#main h1').wait_for()
        return context, page

    def synthetic_invoice(self, role, row, store=None, expected=200):
        from io import BytesIO
        from reportlab.pdfgen.canvas import Canvas
        document = BytesIO()
        canvas = Canvas(document)
        canvas.drawString(60, 760, 'SYNTHETIC INVOICE - ISOLATED PERMISSION CHECK')
        canvas.drawString(60, 730, 'Contract ' + str(row['id']))
        canvas.save()
        content = document.getvalue()
        client = self.clients[role]
        response = client.post(f'/api/business-records/contracts/{row["id"]}/invoice',
            headers={'X-App-Request': '1', 'X-Store-ID': str(store or self.store),
                     'X-CSRF-Token': client.cookies.get('dealer_csrf')},
            data={'request_id': request_id(), 'version': '0'},
            files={'file': ('synthetic-invoice.pdf', content, 'application/pdf')})
        require(response.status_code == expected, 'Synthetic invoice returned ' + str(response.status_code)
                + ', expected ' + str(expected) + ': ' + self.redact(response.text))
        return response.json(), content

    def store_admin_checks(self):
        role, prefix = 'store_admin', '/api/business-records'
        foreign_marker = 'FOREIGN_ONLY_' + self.suffix
        foreign, foreign_body = self.contract(store=self.second_store, marker=foreign_marker)
        foreign = self.action('other_manager', foreign, 'manager-approve', extra=self.limits(), store=self.second_store)
        foreign = self.action('admin', foreign, 'approve', store=self.second_store)
        foreign_invoice, _ = self.synthetic_invoice('admin', foreign, self.second_store)
        foreign_file = foreign_invoice['files'][0]['id']
        manual = self.api('admin', 'POST', prefix + '/manual-reports', {
            'request_id': request_id(), 'report_key': 'vehicle_details', 'period': self.today,
            'brand': foreign_marker, 'entry_mode': 'snapshot', 'values': {'c03': foreign_marker, 'c45': '4321.98'},
            'note': foreign_marker}, expected=201, store=self.second_store)
        target_body = {'request_id': request_id(), 'month': self.today[:7], 'brand': foreign_marker,
                      'series': foreign_marker, 'sales_units': 77, 'mechanical_cents': 87654321}
        self.api('admin', 'POST', prefix + '/monthly-targets', target_body, expected=201, store=self.second_store)
        service_body = {'request_id': request_id(), 'service_type': 'repair', 'customer_name': foreign_marker,
                        'customer_phone': '', 'vehicle': foreign_marker, 'brand': foreign_marker,
                        'service_items': foreign_marker, 'materials_cents': 123400, 'labor_cents': 5600,
                        'cost_cents': 50000, 'handler_name': '合成二店经办人', 'business_date': self.today}
        self.api('admin', 'POST', prefix + '/after-sales', service_body, expected=201, store=self.second_store)
        own_invoice, own_pdf = self.synthetic_invoice('finance', self.approved)
        own_file = own_invoice['files'][0]['id']
        own_base = prefix + f'/contracts/{self.approved["id"]}'
        own = self.api(role, 'GET', own_base)
        require(own['cost_cents'] == 999 and own['profit_cents'] == 12345 and own['gift_cost_cents'] == 500,
                'Store administrator lacks the authorized current-store pricing read')
        require(Decimal(own['office_data']['values'][self.commission_key]) == Decimal('67.89'),
                'Store administrator cannot read current-store commission details')
        require(own['actions'] == ['print'], 'Read-only store administrator received a business-write action')
        caps = self.api(role, 'GET', prefix + '/catalog')['capabilities']
        require(caps['read_internal'] and caps['read_invoice'] and caps['read_finance'],
                'Store administrator read capabilities are incomplete')
        require(not any(value for name, value in caps.items() if not name.startswith('read_')),
                'Store administrator received a business-write capability')
        self.api(role, 'GET', own_base + '/invoice')
        downloaded = self.response(role, 'GET', own_base + f'/invoice/files/{own_file}/download')
        require(downloaded.content == own_pdf, 'Authorized invoice original bytes were changed')
        self.api(role, 'GET', prefix + '/standard-prices')
        self.api(role, 'GET', prefix + '/settings')
        catalog = self.api(role, 'GET', prefix + '/catalog')
        require(self.identities['other_sales']['id'] not in {person['id'] for person in catalog['sales_people']},
                'Catalog exposed a salesperson assigned only to another store')
        self.check('store administrator reads complete local records, pricing, reference prices and invoice originals', transport='HTTP')

        for path in (prefix + f'/contracts/{foreign["id"]}', prefix + f'/customers/{foreign["customer_id"]}',
                     prefix + f'/manual-reports/{manual["id"]}', prefix + f'/contracts/{foreign["id"]}/invoice',
                     prefix + f'/contracts/{foreign["id"]}/invoice/files/{foreign_file}/download',
                     own_base + f'/invoice/files/{foreign_file}/download'):
            self.api(role, 'GET', path, expected=404)
        for resource in ('contracts', 'after-sales'):
            self.api(role, 'GET', prefix + '/' + resource + '?customer_id=' + str(foreign['customer_id']), expected=404)
        for selected in (self.second_store, 'all'):
            self.api(role, 'GET', prefix + '/contracts', expected=403, store=selected)
        for path in (prefix + '/contracts?q=' + foreign_marker,
                     prefix + '/customers?q=' + foreign_marker,
                     prefix + '/after-sales?q=' + foreign_marker,
                     prefix + '/manual-reports?report_key=vehicle_details',
                     prefix + '/monthly-targets?month=' + self.today[:7],
                     prefix + '/daily-vehicle-reports?day=' + self.today,
                     prefix + '/daily-vehicle-reports/export?day=' + self.today,
                     prefix + '/daily-reports?day=' + self.today,
                     prefix + '/daily-reports/export?day=' + self.today,
                     prefix + '/daily-reports/trend?day=' + self.today,
                     prefix + '/daily-reports/trend/export?day=' + self.today):
            path += ('&' if '?' in path else '?') + 'store_id=' + str(self.second_store)
            response = self.response(role, 'GET', path)
            require(foreign_marker not in response.text, 'Query parameter widened a store administrator read: ' + path)
        report_query = f'report=vehicle_details&date_from={self.today[:7]}-01&date_to={self.today}&source_mode=manual&group_by=store&store_id={self.second_store}'
        for path in (prefix + '/reports?' + report_query, prefix + '/reports/export?' + report_query):
            response = self.response(role, 'GET', path)
            require(foreign_marker not in response.text and '4321.98' not in response.text,
                    'Cross-store source leaked through statistics or CSV')
        self.api('general_manager', 'GET', prefix + f'/contracts/{foreign["id"]}', expected=404)
        self.api('general_manager', 'GET', prefix + '/catalog', expected=403, store=self.second_store)
        self.check('ID/header/query/store-summary, list/search/report/export and invoice-file tenancy boundaries', transport='HTTP')

        for action, extra in [('manager-approve', self.limits()), ('approve', {}), ('deputy-approve', {}),
                              ('reject', {}), ('office-submit', {}), ('office-approve', {}),
                              ('receipt', {'actual_amount_cents': 1, 'received_on': self.today})]:
            self.action(role, own, action, extra=extra, expected=403)
        self.api(role, 'POST', prefix + '/contracts', {**foreign_body, 'request_id': request_id()}, expected=403)
        self.api(role, 'POST', prefix + '/monthly-targets', {**target_body, 'request_id': request_id()}, expected=403)
        self.api(role, 'POST', prefix + '/after-sales', {**service_body, 'request_id': request_id()}, expected=403)
        self.api(role, 'POST', prefix + '/standard-prices/import', {
            'request_id': request_id(), 'rows': [{'name': '合成禁止写价格', 'sale_price_cents': 1}]}, expected=403)
        self.api(role, 'POST', prefix + '/standard-prices/estimate',
                 {'items': [{'price_id': 1, 'quantity': 1}]}, expected=403)
        self.api(role, 'GET', prefix + '/report-prefill?report_key=vehicle_details&contract_id='
                 + str(own['id']), expected=403)
        self.api(role, 'GET', prefix + '/daily-reports/preview', expected=403)
        self.api(role, 'PUT', own_base + '/office-review', {'request_id': request_id(), 'version': own['version'],
            'report_key': 'vehicle_details', 'values': {}, 'cost_cents': 1}, expected=403)
        self.api(role, 'POST', own_base + '/invoice/recognize', {'request_id': request_id(),
            'version': own_invoice['invoice']['version']}, expected=403)
        self.api(role, 'POST', own_base + '/invoice/confirm', {'request_id': request_id(),
            'version': own_invoice['invoice']['version'], 'fields': {}}, expected=403)
        self.synthetic_invoice(role, own, expected=403)
        for path in ('/api/settings', '/api/flow/catalog', '/api/flow/master/customers', '/api/flow/lookup/employee',
                     '/api/business-assistant/status', '/api/business-assistant/tools', '/api/feedback',
                     '/api/flow/files/1/security', '/api/records/vehicles'):
            self.api(role, 'GET', path, expected=403)
        self.api(role, 'POST', '/api/flow/files/1/scan', {'version': 0, 'request_id': request_id()}, expected=403)
        self.api(role, 'POST', '/api/stores', {'code': 'FORBIDDEN', 'name': '合成禁止建店', 'active': True}, expected=403)
        self.api(role, 'PUT', '/api/stores/' + str(self.store),
                 {'code': 'FORBIDDEN', 'name': '合成禁止改店', 'active': True}, expected=403)
        self.api(role, 'DELETE', '/api/branding/photo', {}, expected=403)
        self.check('store administrator cannot submit business facts, approval, receipts, targets, AI or global configuration', transport='HTTP')
        self.store_account_checks()

    def store_account_checks(self):
        role = 'store_admin'
        listing = self.api(role, 'GET', '/api/users')
        capability = listing['capabilities']
        require(capability['scope'] == 'store' and capability['store_id'] == self.store
                and set(capability['assignable_roles']) == {'sales', 'manager', 'clerk', 'finance'},
                'Local account manager received incorrect role/store capabilities')
        require({item['id'] for item in listing['stores']} == {self.store}, 'User form exposes unrelated stores')
        hidden = {self.identities[name]['id'] for name in ('admin', 'sales', 'general_manager',
            'group_deputy_manager', 'chairman', 'store_admin', 'store_admin_peer', 'other_manager')}
        require(not hidden.intersection(item['id'] for item in listing['items']),
                'Local account list exposes high-role, cross-store or own administrator accounts')
        require(all(item['can_edit'] and item['can_reset_password'] and item['store_ids'] == [self.store]
                    for item in listing['items']), 'Local employee projection is not confined to manageable accounts')

        def new_user(**changes):
            payload = {'username': 'local_' + uuid.uuid4().hex[:16], 'display_name': '合成本店员工',
                       'password': secrets.token_urlsafe(28), 'role': 'sales', 'store_ids': [self.store],
                       'store_roles': [{'store_id': self.store, 'role': 'sales'}], 'can_group_summary': False}
            payload.update(changes)
            return payload

        account = self.api(role, 'POST', '/api/users', new_user(), expected=201)
        require(account['store_ids'] == [self.store] and account['role'] == 'sales', 'Local employee creation changed scope')
        for higher in ('admin', 'store_admin', 'general_manager', 'chairman', 'group_deputy_manager'):
            self.api(role, 'POST', '/api/users', new_user(role=higher,
                store_roles=[{'store_id': self.store, 'role': higher}] if higher != 'admin' else []), expected=403)
        self.api(role, 'POST', '/api/users', new_user(store_ids=[self.second_store],
            store_roles=[{'store_id': self.second_store, 'role': 'sales'}]), expected=403)
        self.api(role, 'POST', '/api/users', new_user(can_group_summary=True), expected=403)
        inactive_store = self.api('admin', 'POST', '/api/stores', {
            'code': 'INACTIVE_' + self.suffix, 'name': '合成停用店', 'active': False}, expected=201)
        peer = next(item for item in self.api('admin', 'GET', '/api/users')['items']
                    if item['id'] == self.identities['store_admin_peer']['id'])
        invalid_admin_changes = ({'can_group_summary': True},
                        {'store_ids': [self.store, self.second_store], 'store_roles': [
                            {'store_id': self.store, 'role': 'store_admin'},
                            {'store_id': self.second_store, 'role': 'store_admin'}]},
                        {'store_ids': [self.store, inactive_store['id']], 'store_roles': [
                            {'store_id': self.store, 'role': 'store_admin'},
                            {'store_id': inactive_store['id'], 'role': 'store_admin'}]},
                        {'store_roles': [{'store_id': self.store, 'role': 'sales'}]},
                        {'role': 'sales', 'store_roles': [{'store_id': self.store, 'role': 'store_admin'}]})
        for changes in invalid_admin_changes:
            candidate = new_user(role='store_admin', store_roles=[{'store_id': self.store, 'role': 'store_admin'}])
            candidate.update(changes)
            self.api('admin', 'POST', '/api/users', candidate, expected=422)
            self.api('admin', 'PUT', '/api/users/' + str(peer['id']), {
                'request_id': request_id(), 'access_version': peer['access_version'],
                'role': 'store_admin', 'display_name': '合成无效门店管理员', 'active': True,
                'store_ids': [self.store], 'store_roles': [{'store_id': self.store, 'role': 'store_admin'}],
                'can_group_summary': False, **changes}, expected=422)
        update = {'request_id': request_id(), 'access_version': account['access_version'],
                  'role': 'clerk', 'display_name': '合成本店账号维护', 'active': True,
                  'store_ids': [self.store], 'store_roles': [{'store_id': self.store, 'role': 'clerk'}],
                  'can_group_summary': False}
        account = self.api(role, 'PUT', '/api/users/' + str(account['id']), update)
        replay = self.api(role, 'PUT', '/api/users/' + str(account['id']), update)
        require(replay == account, 'Local account replay did not preserve exact committed result')
        self.api(role, 'PUT', '/api/users/' + str(account['id']),
                 {**update, 'display_name': '合成重放不同内容'}, expected=409)
        self.api(role, 'PUT', '/api/users/' + str(account['id']), {**update, 'request_id': request_id()}, expected=409)
        current = {**update, 'request_id': request_id(), 'access_version': account['access_version']}
        for changes in ({'role': 'admin', 'store_roles': []}, {'can_group_summary': True},
                        {'store_ids': [self.store, self.second_store], 'store_roles': [
                            {'store_id': self.store, 'role': 'clerk'}, {'store_id': self.second_store, 'role': 'clerk'}]}):
            self.api(role, 'PUT', '/api/users/' + str(account['id']), {**current, **changes}, expected=403)
        for ident in hidden:
            self.api(role, 'PUT', '/api/users/' + str(ident), {**current, 'request_id': request_id()}, expected=404)
            self.api(role, 'POST', f'/api/users/{ident}/password',
                     {'password': secrets.token_urlsafe(28), 'reason': '合成越权拒绝'}, expected=404)
        self.api(role, 'POST', f'/api/users/{account["id"]}/password',
                 {'password': secrets.token_urlsafe(28), 'reason': '合成本店员工密码重置'})
        for active in (False, True):
            account = self.api(role, 'PUT', '/api/users/' + str(account['id']), {
                **update, 'request_id': request_id(), 'access_version': account['access_version'], 'active': active})
            require(account['active'] is active, 'Local account activation did not persist')
        batch_password = secrets.token_urlsafe(28)
        allowed_name, forbidden_name = 'batch_' + uuid.uuid4().hex[:16], 'batch_' + uuid.uuid4().hex[:16]
        batch = {'store_id': self.store, 'password': batch_password, 'rows': [
            {'username': allowed_name, 'display_name': '合成普通员工', 'role': 'sales'},
            {'username': forbidden_name, 'display_name': '合成禁止提权', 'role': 'admin'}]}
        self.api(role, 'POST', '/api/users/batch', batch, expected=403)
        names = {item['username'] for item in self.api('admin', 'GET', '/api/users')['items']}
        require(allowed_name not in names and forbidden_name not in names, 'Rejected batch partially created users')
        batch['rows'] = batch['rows'][:1]
        self.api(role, 'POST', '/api/users/batch', {**batch, 'store_id': self.second_store}, expected=403)
        accepted = self.api(role, 'POST', '/api/users/batch', batch, expected=201)
        require(accepted['count'] == 1 and accepted['created'][0]['store_ids'] == [self.store],
                'Authorized local batch escaped its current store')
        audit = self.api(role, 'GET', '/api/audit')
        require(audit['items'] and all(item['store_id'] == self.store for item in audit['items']),
                'Local audit contains unrelated store/global events')
        require(all(item['entity_type'].startswith('record_') or item['entity_type'] == 'store_account'
                    for item in audit['items']), 'Local audit exposed unrestricted account/global event payloads')
        self.check('local employee create/edit/reset/batch works; high-role/cross-store grants and global audit are denied', transport='HTTP')
        self.invalid_store_admin_checks()

    def invalid_store_admin_checks(self):
        ident = self.identities['store_admin_peer']['id']
        mutations = [('extra_store', 'INSERT INTO user_stores (user_id, store_id, role) VALUES (?, ?, ?)',
                      (ident, self.second_store, 'store_admin')),
                     ('mixed_role', 'UPDATE user_stores SET role=? WHERE user_id=?', ('sales', ident)),
                     ('summary', 'UPDATE users SET can_group_summary=1 WHERE id=?', (ident,))]
        for name, sql, values in mutations:
            try:
                with sqlite3.connect(self.manifest['database_path']) as db:
                    # Simulate a pre-existing malformed row only in this marked
                    # synthetic fixture; current schema independently forbids it.
                    if name == 'summary':
                        db.execute('PRAGMA ignore_check_constraints=ON')
                    db.execute(sql, values)
                self.api('store_admin_peer', 'GET', '/api/auth/me', expected=403)
                self.api('store_admin_peer', 'GET', '/api/users', expected=403)
            finally:
                with sqlite3.connect(self.manifest['database_path']) as db:
                    db.execute('DELETE FROM user_stores WHERE user_id=? AND store_id=?', (ident, self.second_store))
                    db.execute('UPDATE user_stores SET role=? WHERE user_id=?', ('store_admin', ident))
                    db.execute('UPDATE users SET can_group_summary=0 WHERE id=?', (ident,))
            self.report['fixture_mutations'].append({'kind': 'synthetic_invalid_store_admin_' + name,
                'restored': True, 'user_id': ident})
        self.api('store_admin_peer', 'GET', '/api/auth/me')
        self.check('invalid historical multi-store/mixed-role/group-summary store administrators fail closed', transport='HTTP')

    async def native_store_admin(self, browser):
        context, page = await self.native_login(browser, 'store_admin')
        await expect(page.locator('#store')).to_have_count(0)
        await page.goto(self.origin + '/#records-sales/' + str(self.approved['id']))
        office = page.locator('.br-office-panel')
        for text in ('9.99', '123.45', '5.00', '银行返佣', '67.89'):
            await expect(office).to_contain_text(text)
        for action in ('office_edit', 'office_submit', 'office_approve', 'approve', 'manager_approve', 'deputy_approve'):
            await expect(page.locator('[data-action=' + action + ']')).to_have_count(0)
        await expect(page.locator('[data-record-invoice=download]')).to_have_count(1)
        for action in ('upload', 'recognize', 'edit'):
            await expect(page.locator('[data-record-invoice=' + action + ']')).to_have_count(0)
        await self.screenshot(page, 'store-admin-read-only-pricing-invoice')
        await page.goto(self.origin + '/#users')
        await expect(page.locator('#main h1')).to_have_text('本店员工账号')
        await expect(page.locator('#main')).not_to_contain_text(self.credentials['users']['store_admin_peer']['username'])
        await page.locator('[data-act=newuser]').click()
        options = await page.locator('#modal [name=role] option').evaluate_all(
            '(rows)=>rows.map(row=>row.value).filter(Boolean)')
        require(set(options) == {'sales', 'manager', 'clerk', 'finance'}, 'Native local user dialog exposed higher roles')
        require(await page.locator('#modal [name=role]').get_attribute('required') is not None,
                'Native local user dialog allowed the empty role placeholder')
        await expect(page.locator('#modal [name=role]')).to_have_value('sales')
        await expect(page.locator('#modal [name=can_group_summary]')).to_have_count(0)
        await expect(page.locator('#modal [name=store_ids]')).to_have_count(0)
        username, password = 'native_' + uuid.uuid4().hex[:16], secrets.token_urlsafe(28)
        self.extra_secrets.append(password)
        for name, value in {'username': username, 'password': password, 'display_name': '合成本店页面员工'}.items():
            await page.locator('#modal [name=' + name + ']').fill(value)
        await self.screenshot(page, 'store-admin-local-account-form')
        created = await self.submit_form(page, '/api/users')
        require(created['store_ids'] == [self.store] and created['role'] == 'sales', 'Native user form escaped local scope')
        await page.locator('[data-act=edituser][data-id="' + str(created['id']) + '"]').click()
        await page.locator('#modal [name=role]').select_option('finance')
        edited = await self.submit_form(page, '/api/users/' + str(created['id']))
        require(edited['role'] == 'finance' and edited['store_ids'] == [self.store], 'Native employee role edit failed')
        await self.screenshot(page, 'store-admin-local-account-list')
        await page.locator('[data-act=batchusers]').click()
        await expect(page.locator('#modal [name=store_id]')).to_be_disabled()
        await expect(page.locator('#modal [name=store_id] option')).to_have_count(1)
        await page.locator('#modal [name=rows]').fill('合成越权｜native_forbidden_' + self.suffix + '｜总经理')
        await expect(page.locator('#staff-batch-preview')).to_contain_text('不在可分配范围')
        await expect(page.locator('#modal button[type=submit]')).to_be_disabled()
        await self.screenshot(page, 'store-admin-batch-high-role-rejected')
        await page.locator('#modal').get_by_role('button', name='取消', exact=True).click()
        await page.goto(self.origin + '/#stores')
        await expect(page.locator('#main')).to_contain_text('没有门店设置权限')
        require(not any(role == 'store_admin' and path.startswith('/api/business-assistant/')
                        for role, method, path in self.browser_api_requests),
                'Store administrator page started an unauthorized AI request')
        await context.close()
        context, page = await self.native_login(browser, 'admin')
        await page.goto(self.origin + '/#users')
        await expect(page.locator('#main h1')).to_have_text('员工账号')
        for key in ('general_manager', 'other_manager', 'store_admin'):
            await expect(page.locator('#main')).to_contain_text(self.credentials['users'][key]['username'])
        await page.locator('[data-act=newuser]').click()
        await page.locator('#modal [name=role]').select_option('store_admin')
        await expect(page.locator('#modal [name=can_group_summary]')).to_be_disabled()
        await expect(page.locator('#modal [name=can_group_summary]')).not_to_be_checked()
        for ident in (self.store, self.second_store):
            await page.locator('#modal [name=store_ids][value="' + str(ident) + '"]').check()
            await expect(page.locator('#modal [name=store_role_' + str(ident) + ']')).to_be_disabled()
            await expect(page.locator('#modal [name=store_role_' + str(ident) + ']')).to_have_value('store_admin')
        await expect(page.locator('#modal [name=store_ids]:checked')).to_have_count(1)
        await expect(page.locator('#modal [name=store_ids][value="' + str(self.second_store) + '"]')).to_be_checked()
        password = secrets.token_urlsafe(28)
        self.extra_secrets.append(password)
        for name, value in {'username': 'native_admin_' + uuid.uuid4().hex[:12], 'password': password,
                            'display_name': '合成新门店管理员'}.items():
            await page.locator('#modal [name=' + name + ']').fill(value)
        await self.screenshot(page, 'global-admin-create-independent-store-admin')
        created = await self.submit_form(page, '/api/users')
        require(created['role'] == 'store_admin' and created['store_ids'] == [self.second_store]
                and created['can_group_summary'] is False
                and created['store_roles'][0]['role'] == 'store_admin',
                'Global administrator form did not create the independent single-store role')
        await context.close()
        self.check('native store administrator reads pricing/invoice and manages fixed-store employees with no business/AI privileges',
                   transport='native Chromium')

    async def screenshot(self, page, name, full_page=True):
        path = self.directory / (name + '.png')
        await page.screenshot(path=str(path), full_page=full_page)
        self.report['artifacts'].append({'name': path.name, 'sha256': digest(path)})
        self.save()

    async def submit_form(self, page, path):
        async with page.expect_response(lambda response: urlsplit(response.url).path == path
                and response.request.method in {'POST', 'PUT'}) as pending:
            await page.locator('#modal button[type=submit]').click()
        response = await pending.value
        require(response.status in {200, 201}, 'Native form failed: ' + path + ': '
                + self.redact(await response.text()))
        result = await response.json()
        await expect(page.locator('#modal')).not_to_be_visible()
        return result

    async def native_approval(self, browser):
        context, page = await self.native_login(browser, 'sales')
        await page.goto(self.origin + '/#records-sales')
        await page.locator('[data-br=new-contract]').click()
        for name, value in {'customer_name': '合成浏览器客户', 'customer_phone': '19900000001',
                            'contract_date': self.today, 'brand': '合成品牌', 'model': '合成车型',
                            'vin': 'SYNTHETIC-BROWSER', 'sale_price': '100.00',
                            'seller_name': '合成一店', 'signature_date': self.today}.items():
            await page.locator('#modal [name=' + name + ']').fill(value)
        await page.locator('#modal [name=payment_method]').select_option('全款')
        row = await self.submit_form(page, '/api/business-records/contracts')
        await context.close()
        for role, action, path in [('manager', 'manager_approve', 'manager-approve'),
                                    ('general_manager', 'approve', 'approve'),
                                    ('group_deputy_manager', 'deputy_approve', 'deputy-approve')]:
            context, page = await self.native_login(browser, role)
            await page.goto(self.origin + '/#records-sales/' + str(row['id']))
            await page.locator('[data-action=' + action + ']').click()
            if role == 'manager':
                for name in ('minimum_sale_price', 'gift_limit', 'offered_gift_value'):
                    field = page.locator('#modal [name=' + name + ']')
                    await expect(field).to_have_value('')
                    require(await field.get_attribute('required') is not None,
                            'Unverified manager limit must be an empty required input: ' + name)
                await self.screenshot(page, 'native-manager-unverified-empty-limits')
                for name, value in {'minimum_sale_price': '100.01', 'gift_limit': '0',
                                    'offered_gift_value': '0', 'approval_basis': '合成书面政策'}.items():
                    await page.locator('#modal [name=' + name + ']').fill(value)
            row = await self.submit_form(page, f'/api/business-records/contracts/{row["id"]}/{path}')
            if role == 'general_manager':
                require(row['status'] == 'deputy_pending', 'Native GM path skipped deputy')
                await expect(page.locator('[data-action=print]')).to_have_count(0)
            if role == 'group_deputy_manager':
                require(row['status'] == 'approved', 'Native deputy path did not release contract')
                async with page.expect_download() as pending:
                    await page.locator('[data-action=print]').click()
                pdf_path = self.directory / 'native-approved-contract.pdf'
                await (await pending.value).save_as(str(pdf_path))
                require(pdf_path.read_bytes().startswith(b'%PDF'), 'Native print did not download a PDF')
                await self.screenshot(page, 'native-deputy-approved')
            await context.close()
        self.check('native sales form, manager limits, GM, conditional deputy and PDF download', transport='native Chromium')

    async def native_monthly(self, browser):
        context, page = await self.native_login(browser, 'manager')
        await page.goto(self.origin + '/#records-dashboard/targets')
        await expect(page.locator('#main h1')).to_have_text('月度目标')
        await page.locator('[data-br-target=new]').click()
        for name, value in {'brand': '合成页面品牌', 'series': '合成页面系列', 'sales_units': '0',
                            'mechanical': '12.34', 'accident': '/', 'after_sales': ''}.items():
            await page.locator('#modal [name=' + name + ']').fill(value)
        row = await self.submit_form(page, '/api/business-records/monthly-targets')
        require(row['sales_units'] == 0 and row['mechanical_cents'] == 1234
                and row['accident_cents'] == '/' and row['after_sales_cents'] is None,
                'Native target form changed zero/slash/unknown semantics')
        await page.locator('[data-br-target=revise][data-id="' + str(row['id']) + '"]').click()
        await page.locator('#modal [name=sales_units]').fill('3')
        revised = await self.submit_form(page, '/api/business-records/monthly-targets')
        require(revised['supersedes_id'] == row['id'] and revised['sales_units'] == 3,
                'Native target correction overwrote history')
        await expect(page.locator('#main')).to_contain_text('/（不适用）')
        await expect(page.locator('#main')).to_contain_text('未下达')
        await self.screenshot(page, 'native-monthly-targets')
        await context.close()
        context, page = await self.native_login(browser, 'clerk')
        await page.goto(self.origin + '/#records-dashboard/targets')
        await expect(page.locator('#main h1')).to_have_text('月度目标')
        await expect(page.locator('[data-br-target=new]')).to_have_count(0)
        await context.close()
        self.check('native manager issues/revises monthly targets; clerk page is read-only', transport='native Chromium')

    async def native_checks(self):
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(executable_path=self.manifest['browser']['executable'],
                headless=True, args=['--disable-dev-shm-usage', '--no-sandbox'])
            try:
                await self.native_approval(browser)
                await self.native_monthly(browser)
                await self.native_store_admin(browser)
                context, page = await self.native_login(browser, 'general_manager')
                await page.goto(self.origin + '/#records-sales/' + str(self.approved['id']))
                office = page.locator('.br-office-panel')
                for text in (self.office_spec['title'], '此车销售总成本', '9.99', '此车销售利润',
                             '123.45', '赠品成本', '5.00', '银行返佣', '67.89'):
                    await expect(office).to_contain_text(text)
                await expect(office).not_to_contain_text('成本、利润、返佣及核价备注不在本页展示')
                await self.screenshot(page, 'gm-full-nonzero-pricing')
                await office.get_by_text('此车销售总成本', exact=True).first.scroll_into_view_if_needed()
                await self.screenshot(page, 'gm-cost-profit-gift-nonzero', full_page=False)
                await office.get_by_role('cell', name='银行返佣（元）', exact=True).first.scroll_into_view_if_needed()
                await self.screenshot(page, 'gm-bank-commission-nonzero', full_page=False)
                await context.close()
                context, page = await self.native_login(browser, 'clerk')
                await page.goto(self.origin + '/#records-sales/' + str(self.approved['id']))
                await page.locator('[data-action=office_edit]').click()
                await expect(page.locator('#modal')).to_contain_text('下方明细不会自动计算')
                await page.locator('#modal [name=profit]').fill('123.45')
                await page.locator('#modal [name=gift_cost]').fill('5.00')
                await expect(page.locator('#modal [name=value_' + self.profit_key + ']')).to_have_value('123.45')
                await expect(page.locator('#modal [name=value_' + self.gift_key + ']')).to_have_value('5.00')
                require(await page.locator('#modal [name=value_' + self.profit_key + ']').get_attribute('readonly') is not None,
                        'Mirrored profit is not read-only')
                await self.screenshot(page, 'office-mirror-explanation')
                for name in ('cost', 'profit', 'gift_cost'):
                    await page.locator('#modal [name=' + name + ']').fill('')
                row = await self.submit_form(page,
                    f'/api/business-records/contracts/{self.approved["id"]}/office-review')
                require(all(row['office_data'][name] is None for name in
                            ('cost_cents', 'profit_cents', 'gift_cost_cents')),
                        'Native clearing did not send/store explicit null financial amounts')
                await page.locator('[data-action=office_edit]').click()
                for name in ('cost', 'profit', 'gift_cost', 'value_' + self.profit_key, 'value_' + self.gift_key):
                    await expect(page.locator('#modal [name=' + name + ']')).to_have_value('')
                await page.locator('#modal [name=cost]').scroll_into_view_if_needed()
                await self.screenshot(page, 'office-cleared-reopen', full_page=False)
                row = await self.submit_form(page,
                    f'/api/business-records/contracts/{self.approved["id"]}/office-review')
                await page.locator('[data-action=office_submit]').click()
                row = await self.submit_form(page,
                    f'/api/business-records/contracts/{self.approved["id"]}/office-submit')
                await context.close()
                context, page = await self.native_login(browser, 'general_manager')
                await page.goto(self.origin + '/#records-sales/' + str(self.approved['id']))
                await page.locator('#main h1').wait_for()
                await expect(page.locator('#main')).to_contain_text(self.office_spec['title'])
                await expect(page.locator('.br-office-panel')).to_contain_text('银行返佣')
                await expect(page.locator('.br-office-panel')).to_contain_text('67.89')
                await self.screenshot(page, 'gm-full-original-sheet')
                await page.locator('[data-action=office_approve]').click()
                await self.submit_form(page,
                    f'/api/business-records/contracts/{self.approved["id"]}/office-approve')
                latest = self.api('clerk', 'GET', f'/api/business-records/contracts/{self.approved["id"]}')
                require(all(latest[name] is None for name in ('cost_cents', 'profit_cents', 'gift_cost_cents')),
                        'Approval restored prior amounts after an explicit null correction')
                await context.close()
                self.check('native full GM pricing, clerk mirrors and explicit-null revision/reopen/approval',
                           transport='native Chromium')
                require(not self.report['page_errors'], 'Browser JavaScript errors occurred')
                require(not self.report['external_requests'], 'Browser attempted non-loopback requests')
            except Exception:
                if self.active_page and not self.active_page.is_closed():
                    await self.screenshot(self.active_page, 'native-failure')
                raise
            finally:
                await browser.close()

    def run(self):
        try:
            self.cache_integration()
            self.setup()
            self.contract_checks()
            self.legacy_checks()
            self.office_checks()
            self.monthly_checks()
            self.store_admin_checks()
            asyncio.run(self.native_checks())
            self.report.update(complete=True, passed=True)
        except Exception as error:
            self.report.update(error=self.redact(error), error_type=type(error).__name__)
            raise
        finally:
            for client in self.clients.values():
                client.close()
            self.save()

    def monthly_checks(self):
        path = '/api/business-records/monthly-targets'
        body = {'request_id': request_id(), 'month': self.today[:7], 'brand': '合成目标品牌',
                'series': '合成目标系列', 'sales_units': 0, 'mechanical_cents': 12345,
                'accident_cents': '/', 'after_sales_cents': None, 'note': '合成空值边界'}
        self.api('clerk', 'POST', path, body, expected=403)
        self.api('sales', 'POST', path, body, expected=403)
        self.api('admin', 'POST', path, body, expected=409, store='all')
        for changes in ({'sales_units': 0.5}, {'mechanical_cents': 1.5}, {'sales_units': -1},
                        {'accident_cents': 'unknown'}, {'month': '2026-13'}):
            self.api('manager', 'POST', path, {**body, **changes}, expected=422)
        row = self.api('manager', 'POST', path, body, expected=201)
        require(all(row[key] == body[key] for key in
                    ('sales_units', 'mechanical_cents', 'accident_cents', 'after_sales_cents')),
                'Target API collapsed explicit zero, slash or unknown values')
        replay = self.api('manager', 'POST', path, body, expected=201)
        require(replay['id'] == row['id'], 'Exact target replay created another row')
        self.api('manager', 'POST', path, {**body, 'request_id': request_id()}, expected=409)
        self.api('manager', 'POST', path, {**body, 'sales_units': 7}, expected=409)
        revision = {**body, 'request_id': request_id(), 'supersedes_id': row['id'],
                    'supersedes_version': row['version'], 'sales_units': 9, 'mechanical_cents': None}
        self.api('manager', 'POST', path, {**revision, 'supersedes_version': row['version'] + 1}, expected=409)
        self.api('manager', 'POST', path, {**revision, 'series': '另一系列'}, expected=422)
        self.api('other_manager', 'POST', path, revision, expected=404, store=self.second_store)
        revised = self.api('general_manager', 'POST', path, revision, expected=201)
        require(revised['id'] != row['id'] and revised['supersedes_id'] == row['id'], 'Revision was not appended')
        self.api('manager', 'POST', path, {**revision, 'request_id': request_id()}, expected=409)
        current = self.api('clerk', 'GET', path + '?month=' + body['month'])
        history = self.api('manager', 'GET', path + '?month=' + body['month'] + '&include_history=true')
        require([item['id'] for item in current['items']] == [revised['id']], 'Current list contains retired targets')
        require(len(history['items']) == 2 and not next(item for item in history['items']
                if item['id'] == row['id'])['is_current'], 'Revision history disappeared')
        elsewhere = self.api('other_manager', 'GET', path + '?month=' + body['month'], store=self.second_store)
        require(not elsewhere['items'], 'Targets leaked across stores')
        report = self.api('manager', 'GET', '/api/business-records/reports?report=sales_targets&'
            f'date_from={body["month"]}-01&date_to={self.today}&brand=合成目标品牌&source_mode=combined&group_by=store')
        total = report['grand_total']
        require(Decimal(total['c02']) == Decimal('9') and total['c03'] is None
                and total['c04'] is None and total['c05'] is None,
                'Monthly report counted history or treated unknown/not-applicable targets as zero')
        require(all(total[key] is None for key in ('c06', 'c07', 'c08', 'c09')),
                'Targets manufactured sales or after-sales actuals')
        self.api('clerk', 'POST', '/api/business-records/manual-reports', {
            'request_id': request_id(), 'report_key': 'sales_targets', 'period': self.today,
            'brand': body['brand'], 'entry_mode': 'snapshot', 'values': {
                'c01': body['series'], 'c02': '999', 'c03': '666', 'c04': '444', 'c05': '1110',
                'c06': '4', 'c07': '11', 'c08': '12', 'c09': '23'},
            'note': '合成旧格式累计实绩与目标列兼容输入'}, expected=201)
        report = self.api('manager', 'GET', '/api/business-records/reports?report=sales_targets&'
            f'date_from={body["month"]}-01&date_to={self.today}&brand=合成目标品牌&source_mode=combined&group_by=store')
        total = report['grand_total']
        require(Decimal(total['c02']) == Decimal('9') and total['c03'] is None
                and total['c04'] is None and total['c05'] is None
                and Decimal(total['c06']) == Decimal('4') and Decimal(total['c09']) == Decimal('23'),
                'Ordinary manual snapshot replaced manager targets or lost its own actuals')
        self.check('monthly targets preserve zero/null/slash, append corrections, enforce permissions and feed current totals',
                   transport='HTTP')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    manifest, credentials = load_fixture(args.manifest)
    checks = FeedbackChecks(manifest, credentials)
    try:
        checks.run()
    except Exception as error:
        print(checks.redact(error), file=sys.stderr)
        print('Evidence: ' + str(checks.directory))
        return 1
    print('Passed checks: ' + str(len(checks.report['checks'])))
    print('Evidence: ' + str(checks.directory))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
