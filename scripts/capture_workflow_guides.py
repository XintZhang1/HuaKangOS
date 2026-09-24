"""Capture actual workflow entries using an isolated database and employee logins.

Run with --screenshots OUTSIDE_REPOSITORY. This command never connects to an
existing preview, sends a model request, or publishes images automatically.
Review the external PNGs before copying them and screenshots.json to the source.
"""
from collections import defaultdict
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import expect
from tests import browser_huakangos as h

ROLE_LABELS = {'admin': '系统管理员', 'manager': '主管', 'sales': '销售',
               'inventory': '库管', 'service': '服务顾问', 'finance': '财务',
               'auditor': '审计', 'reception': '前台', 'technician': '技师',
               'customer_service': '客服'}
SOURCE_FILES = []
ROUTE_FILTER = set()


def load_sources(paths):
    workflows, ids = [], set()
    for path in paths:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        rows = data if isinstance(data, list) else data['workflows']
        for row in rows:
            assert row['id'] not in ids, f"重复流程编号：{row['id']}"
            ids.add(row['id'])
            route = row['screenshot']['route']
            assert re.fullmatch(r'[a-z][a-z0-9-]*(?:/[a-z][a-z0-9_-]*)*', route), route
            assert route == row['entry']['route'], (row['id'], route, row['entry'])
            roles = row['entry'].get('roles') or row['roles']
            assert roles and all(role in ROLE_LABELS for role in roles), (row['id'], roles)
            workflows.append(row)
    assert workflows, '尚未生成流程来源文件。'
    return workflows


def employee(browser, admin, base, role, errors, viewport=None, store_ids=(1,)):
    """Create and sign in the actual role, including its mandatory password change."""
    context = browser.new_context(viewport=viewport or {'width': 1440, 'height': 1000}, locale='zh-CN')
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append({'role': role, 'error': str(error)}))
    first, password = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    username = 'guide-' + role + '-' + secrets.token_hex(3)
    values = {'username': username, 'display_name': '演示' + ROLE_LABELS[role],
              'role': role, 'password': first}
    if role != 'admin':
        values['store_roles'] = [{'store_id': store, 'role': role} for store in store_ids]
    h.checked_request(admin, '/api/users', 'POST', values, status=201)
    h.login_page(page, base, username, first)
    page.locator('#modal [name=current_password]').fill(first)
    page.locator('#modal [name=new_password]').fill(password)
    h.save_modal(page)
    h.login_page(page, base, username, password)
    expect(page.locator('#main h1')).to_have_text('我的工作')
    actual = h.checked_request(page, '/api/auth/me')
    assert actual['role'] == role, actual
    return context, page


def seed(admin):
    """Small master-data fixture through the same authenticated business APIs."""
    for kind, values in [
        ('customers', {'name': '合成演示客户', 'phone': '13900006661', 'contact_allowed': True, 'note': '操作指引演示资料'}),
        ('items', {'sku': 'GUIDE-PART', 'name': '合成演示配件', 'unit': '件', 'reorder': '0', 'active': True}),
        ('accounts', {'name': '合成演示账户', 'account_type': 'bank', 'active': True}),
        ('references', {'category': '厂家', 'name': '合成演示厂家', 'active': True, 'detail': '操作指引演示资料'}),
    ]:
        h.checked_request(admin, '/api/flow/master/' + kind, 'POST', {'values': values}, status=201)
    for kind, values in [
        ('suppliers', {'code': 'GUIDE-SUPPLIER', 'name': '合成演示供应商', 'payment_terms_days': 30}),
        ('insurers', {'code': 'GUIDE-INSURER', 'name': '合成演示保险公司'}),
        ('work_items', {'code': 'GUIDE-WORK', 'name': '合成演示检查', 'billing_unit': 'job', 'standard_fee_cents': 10000}),
        ('warehouses', {'code': 'GUIDE-WH', 'name': '合成演示仓库', 'warehouse_type': 'materials'}),
    ]:
        h.checked_request(admin, '/api/masters/' + kind, 'POST', {'request_id': secrets.token_hex(16), 'values': values}, status=201)
    h.checked_request(admin, '/api/vehicle-catalog/entry', 'POST', {
        'request_id': secrets.token_hex(16), 'brand_name': '演示品牌', 'series_name': '演示车系',
        'name': '演示纯电车型', 'model_year': 2026, 'fuel_type': 'electric', 'seats': 5,
        'displacement_ml': 0, 'battery_wh': 60501, 'guide_price_cents': 13980000,
    })


def read_entry(page, base, route):
    page.goto(base + '/#' + route)
    expect(page.locator('#store')).to_be_visible()
    page.wait_for_function("() => document.querySelector('#main h1') || document.querySelector('#main .errorpage')")
    assert page.locator('#main .errorpage').count() == 0, page.locator('#main').inner_text()
    expect(page.locator('#main h1')).to_be_visible()
    title = page.locator('#main h1').inner_text().strip()
    assert title and title not in ['请选择工作栏目', '暂时无法显示'], title
    assert page.evaluate('location.hash') == '#' + route
    assert page.locator('#main').inner_text().strip(), '入口为空白'
    page.evaluate('document.fonts.ready')
    return title


def mark_demo(page, role):
    page.evaluate("""label => {
        document.getElementById('workflow-capture-label')?.remove();
        const note=document.createElement('div'); note.id='workflow-capture-label';
        note.textContent='合成演示入口 · '+label+' · 非整流程验收';
        note.style.cssText='position:fixed;bottom:12px;left:16px;z-index:99999;padding:8px 12px;background:#fff;color:#692124;border:1px solid #c43c43;border-radius:7px;font:14px sans-serif;box-shadow:0 2px 6px #0002;pointer-events:none';
        document.body.append(note);
    }""", ROLE_LABELS[role])


def exercise(browser, base, password, output):
    assert urlsplit(base).hostname == '127.0.0.1' and urlsplit(base).port != 8000
    workflows = load_sources(SOURCE_FILES)
    groups = defaultdict(list)
    for row in workflows:
        if not ROUTE_FILTER or row['screenshot']['route'] in ROUTE_FILTER:
            groups[row['screenshot']['route']].append(row)
    assert groups
    errors, failures, captures, contexts, pages = [], [], {}, [], {}
    admin_context = browser.new_context(viewport={'width': 1440, 'height': 1000}, locale='zh-CN')
    contexts.append(admin_context)
    admin = admin_context.new_page()
    try:
        h.login_page(admin, base, 'admin', password)
        seed(admin)
        for route, rows in sorted(groups.items()):
            allowed = set(rows[0]['entry'].get('roles') or rows[0]['roles'])
            for row in rows[1:]:
                allowed &= set(row['entry'].get('roles') or row['roles'])
            # A shared screenshot uses one role authorized for every referenced entry.
            order = ['sales', 'reception', 'service', 'inventory', 'finance', 'customer_service', 'technician', 'auditor', 'manager', 'admin']
            candidates = [role for role in order if role in allowed]
            if not candidates:
                failures.append({'route': route, 'error': '共用入口的岗位没有交集', 'workflow_ids': [r['id'] for r in rows]})
                continue
            attempts = []
            for role in candidates:
                try:
                    if role not in pages:
                        context, page = employee(browser, admin, base, role, errors)
                        contexts.append(context)
                        pages[role] = page
                    page = pages[role]
                    title = read_entry(page, base, route)
                    mark_demo(page, role)
                    filename = route.replace('/', '-').replace('_', '-') + '.png'
                    if page.locator('#toast').count():
                        expect(page.locator('#toast')).not_to_have_class(re.compile('visible'), timeout=7000)
                    # Manuals illustrate the entry at readable size; a whole long
                    # report would turn the navigation and buttons into tiny text.
                    page.screenshot(path=str(output / filename), full_page=False)
                    captures[route] = {
                        'src': 'workflow-assets/' + filename,
                        'caption': title + '：合成演示入口（' + ROLE_LABELS[role] + '）',
                        'role': role, 'role_label': ROLE_LABELS[role], 'page_title': title,
                        'capture_kind': 'entry', 'synthetic_only': True,
                        'workflow_ids': [row['id'] for row in rows],
                        'viewport': {'width': 1440, 'height': 1000},
                        'sha256': hashlib.sha256((output / filename).read_bytes()).hexdigest(),
                        'role_attempts': attempts,
                    }
                    print('已采集 ' + route + ' · ' + ROLE_LABELS[role], flush=True)
                    break
                except Exception as error:
                    attempts.append({'role': role, 'error': str(error)[:2500]})
            else:
                failures.append({'route': route, 'attempts': attempts})
        result = {'synthetic_only': True, 'capture_kind': 'entry',
                  'scope': '实际岗位入口截图，不代表各流程办理完成或公司验收。',
                  'time': datetime.now(timezone.utc).isoformat(), 'captured_routes': len(captures),
                  'workflow_count': sum(len(v['workflow_ids']) for v in captures.values()),
                  'page_errors': errors, 'failures': failures, 'external_model_requests': 0,
                  'source_files': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in SOURCE_FILES},
                  'status': 'passed' if not errors and not failures else 'failed',
                  'reviewed_for_publication': False}
        (output / 'screenshots.json').write_text(json.dumps(captures, ensure_ascii=False, indent=2), encoding='utf-8')
        return result
    finally:
        for context in reversed(contexts):
            context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshots', type=Path, required=True)
    parser.add_argument('--source', type=Path, action='append')
    parser.add_argument('--route', action='append', default=[])
    args = parser.parse_args()
    SOURCE_FILES.extend(path.resolve() for path in (args.source or [ROOT / 'docs/workflow-source/business.json', ROOT / 'docs/workflow-source/services.json']))
    ROUTE_FILTER.update(args.route)
    load_sources(SOURCE_FILES)
    h.exercise = exercise
    sys.argv = [sys.argv[0], '--screenshots', str(args.screenshots)]
    h.main()


if __name__ == '__main__':
    main()
