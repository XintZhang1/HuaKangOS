"""Targeted native Chromium checks in a new, external synthetic source mirror.

Run with the isolated Python environment containing root requirements and
playwright==1.56.0. No real model, production configuration or customer files.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright, expect
from synthetic import gift_csv, vehicle_xlsx


SEED = '''
import json, os
from pathlib import Path
from types import SimpleNamespace
from app.cli import initialize
initialize(SimpleNamespace(demo=False, admin_user=os.environ['SYNTH_ADMIN']))
from app.db import SessionLocal
from app.models import User, Store, UserStore
from app.security import hash_password
credentials=json.loads(Path(os.environ['SYNTH_CREDENTIALS']).read_text())
with SessionLocal() as db:
    db.get(Store,1).brand='合成品牌'
    db.get(Store,1).name='合成门店一'
    db.add_all([Store(id=2,code='SYNTH2',name='合成同品牌二店',brand='合成品牌'), Store(id=3,code='SYNTH3',name='合成异品牌店',brand='其他合成品牌')])
    for role, values in credentials.items():
        if role=='admin': continue
        store=2 if role=='other_sales' else 1
        actual='sales' if role=='other_sales' else role
        user=User(username=values['username'],display_name='合成'+role,role=actual,password_hash=hash_password(values['password']),must_change_password=False)
        db.add(user);db.flush();db.add(UserStore(user_id=user.id,store_id=store,role=actual))
    db.commit()
'''

SERVER = '''
import ipaddress, json, os, socket
from pathlib import Path
ledger=Path(os.environ['SYNTH_NETWORK_LEDGER'])
ledger.write_text(json.dumps({'real_model_calls':0,'blocked_external_attempts':[]}))
def allow(host):
    if host in ('localhost','127.0.0.1','::1'): return
    try:
        if ipaddress.ip_address(host).is_loopback: return
    except ValueError: pass
    value=json.loads(ledger.read_text());value['blocked_external_attempts'].append(str(host));ledger.write_text(json.dumps(value))
    raise RuntimeError('Synthetic browser server blocks outbound network')
original_connect=socket.socket.connect
original_connect_ex=socket.socket.connect_ex
original_getaddrinfo=socket.getaddrinfo
def connect(self,address):
    if self.family in (socket.AF_INET,socket.AF_INET6): allow(address[0])
    return original_connect(self,address)
def connect_ex(self,address):
    if self.family in (socket.AF_INET,socket.AF_INET6): allow(address[0])
    return original_connect_ex(self,address)
def getaddrinfo(host,*args,**kwargs):
    if host is not None: allow(host)
    return original_getaddrinfo(host,*args,**kwargs)
socket.socket.connect=connect;socket.socket.connect_ex=connect_ex;socket.getaddrinfo=getaddrinfo
import uvicorn
uvicorn.run('app.main:app',host='127.0.0.1',port=int(os.environ['SYNTH_PORT']))
'''


def inventory(source):
    files = [source / name for name in ('requirements.txt', 'alembic.ini')]
    for name in ('app', 'web', 'migrations'):
        files += sorted((source / name).rglob('*'))
    result = {}
    for path in files:
        relative = path.relative_to(source)
        if not path.is_file() or any(part in {'__pycache__', '.pytest_cache', 'node_modules'} or part.startswith('.env') for part in relative.parts):
            continue
        if path.suffix.lower() in {'.pyc', '.db', '.sqlite', '.sqlite3', '.log'}:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError('External source link refused: ' + str(relative))
        result[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def run(source, browser, output):
    source = source.resolve()
    if output.exists() or output.resolve().is_relative_to(source):
        raise ValueError('Output must be a new directory outside repository')
    output.mkdir(parents=True)
    mirror, runtime, evidence = (output / name for name in ('source', 'runtime', 'evidence'))
    runtime.mkdir(); evidence.mkdir()
    before = inventory(source)
    for relative in before:
        target = mirror / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    if inventory(mirror) != before or inventory(source) != before:
        raise RuntimeError('Source changed while making the isolated mirror')
    (output / 'source-manifest.json').write_text(json.dumps(before, indent=2))
    fingerprint = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
    scripts = output / 'scripts'; scripts.mkdir()
    for name in ('browser_check.py', 'synthetic.py'):
        shutil.copyfile(Path(__file__).with_name(name), scripts / name)
    credentials = {role: {'username': role + '_' + secrets.token_hex(4), 'password': secrets.token_urlsafe(24)} for role in ('admin', 'manager', 'sales', 'other_sales')}
    credentials_path = runtime / 'credentials.json'
    credentials_path.write_text(json.dumps(credentials)); credentials_path.chmod(0o600)
    disabled_config = runtime / 'disabled-model.json'
    disabled_config.write_text(json.dumps({'enabled':False,'synthetic':True}))
    env = {key: value for key, value in os.environ.items() if key in {'PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR'}}
    env.update({'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(mirror),
                'DATABASE_URL': 'sqlite:///' + str(runtime / 'synthetic.sqlite'), 'APP_ENV': 'test',
                'SCHEDULER_ENABLED': 'false', 'SCHEDULER_MODE': 'off', 'ALLOW_AI_EXTERNAL': 'false',
                'FILE_SCAN_MODE': 'structure_only', 'FILE_STORAGE_MODE': 'blob', 'COOKIE_SECURE': 'false',
                'BUSINESS_ASSISTANT_CONFIG': str(disabled_config), 'SYNTH_NETWORK_LEDGER': str(evidence / 'network.json'),
                'ALLOWED_HOSTS': '127.0.0.1,localhost', 'SYNTH_ADMIN': credentials['admin']['username'],
                'SYNTH_CREDENTIALS': str(credentials_path), 'HUAKANGOS_INITIAL_PASSWORD': credentials['admin']['password']})
    with (evidence / 'initialize.log').open('w') as log:
        subprocess.run([sys.executable, '-c', SEED], cwd=mirror, env=env, stdout=log, stderr=log, check=True)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    origin = 'http://127.0.0.1:' + str(port)
    env['SYNTH_PORT'] = str(port)
    server_log = (evidence / 'server.log').open('w')
    server = subprocess.Popen([sys.executable, '-c', SERVER], cwd=mirror, env=env, stdout=server_log, stderr=server_log)
    report = {'scope': 'urgent-pricing-gift-search', 'source_fingerprint': fingerprint, 'script_fingerprints': {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in scripts.iterdir()}, 'passed': False, 'checks': [], 'page_errors': [], 'external_requests': [], 'responses': []}
    def passed(name):
        report['checks'].append(name); print('PASS ' + name, flush=True)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(120):
            if server.poll() is not None: raise RuntimeError('Server exited during startup')
            try:
                with opener.open(origin + '/', timeout=1): break
            except OSError: time.sleep(.25)
        else: raise RuntimeError('Server startup timed out')
        with sync_playwright() as playwright:
            chromium = playwright.chromium.launch(executable_path=str(browser), headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            context = chromium.new_context(viewport={'width': 1440, 'height': 1100}, locale='zh-CN')
            page = context.new_page()
            page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
            page.on('request', lambda request: report['external_requests'].append(request.url) if not request.url.startswith(origin) else None)
            page.on('response', lambda response: report['responses'].append({'path': response.url.removeprefix(origin), 'status': response.status}) if '/api/business-records/' in response.url else None)
            page.set_default_timeout(10000)
            def login(role, route='records-settings'):
                context.clear_cookies()
                page.goto('about:blank')
                page.goto(origin + '/#' + route)
                expect(page.locator('[name=username]')).to_be_visible()
                page.locator('[name=username]').fill(credentials[role]['username'])
                page.locator('[name=password]').fill(credentials[role]['password'])
                page.locator('button[type=submit]').click()
                expect(page.locator('[name=username]')).not_to_be_visible()
                page.goto(origin + '/#' + route)
            def screenshot(name): page.screenshot(path=str(evidence / (name + '.png')), full_page=True)
            def open_upload(kind):
                page.locator('[data-br-flow="price-upload"][data-kind="' + kind + '"]').click()
                expect(page.locator('#modal[open] input[type=file]')).to_be_visible()
            def file_upload(name, content, mime='application/octet-stream'):
                page.locator('#modal input[type=file]').set_input_files({'name': name, 'mimeType': mime, 'buffer': content})
                page.locator('[data-price-recognize]').click()
            def close_modal(): page.locator('#modal [data-act=close]').click()
            # Profile is established with original UI and local store permissions.
            login('admin')
            page.locator('[data-br-flow=store-profile]').click()
            page.locator('#modal [name=address]').fill('合成地址，不是真实门店')
            page.locator('[data-seller-add]').click()
            page.locator('[data-seller-name]').fill('合成卖方公司')
            page.locator('[data-seller-address]').fill('合成卖方地址')
            page.locator('[data-br=defer-form]').click()
            page.locator('[data-br-flow=store-profile]').click()
            expect(page.locator('#modal [name=address]')).to_have_value('合成地址，不是真实门店')
            expect(page.locator('[data-seller-name]')).to_have_value('合成卖方公司')
            page.locator('#modal button[type=submit]').click()
            expect(page.locator('#modal')).not_to_be_visible()
            passed('profile UI save and draft field retention')
            # Admin is permitted to publish gift costs; manager sees only sale amounts.
            open_upload('gift')
            file_upload('合成赠品.csv', gift_csv(), 'text/csv')
            expect(page.locator('[data-price-status]')).to_have_text('待核对 3 项')
            expect(page.locator('[data-price-key=unit_cost_cents]').first).to_have_value('40.00')
            page.locator('#modal button[type=submit]').click()
            expect(page.locator('#modal')).not_to_be_visible()
            passed('real gift CSV upload, preview, costs and confirmed backend publication')
            login('manager')
            expect(page.locator('#br-pricing-vehicle')).not_to_be_visible()
            expect(page.locator('#br-pricing-gift')).not_to_be_visible()
            vehicle_toggle=page.locator('[data-price-toggle=vehicle]'); gift_toggle=page.locator('[data-price-toggle=gift]')
            vehicle_toggle.click(); expect(page.locator('#br-pricing-vehicle')).to_be_visible(); expect(page.locator('#br-pricing-gift')).not_to_be_visible()
            gift_toggle.click(); vehicle_toggle.click(); expect(page.locator('#br-pricing-gift')).to_be_visible(); expect(page.locator('#br-pricing-vehicle')).not_to_be_visible()
            gift_toggle.click(); vehicle_toggle.click(); expect(page.locator('#br-pricing-vehicle')).to_be_visible(); expect(page.locator('#br-pricing-gift')).not_to_be_visible()
            passed('independent collapsed panels and reopen state')
            open_upload('vehicle')
            expect(page.get_by_role('button',name='手工添加车型',exact=True)).not_to_be_visible()
            expect(page.locator('[data-policy-confirm-label]')).not_to_be_visible()
            expect(page.locator('[data-policy-tools]')).not_to_be_visible()
            file_upload('invalid.txt', b'synthetic invalid extension')
            expect(page.locator('#modal .formerror')).to_contain_text('.xlsx')
            expect(page.locator('#modal button[type=submit]')).to_be_disabled()
            passed('invalid extension leaves publication disabled with feedback')
            file_upload('corrupt.xlsx', b'not a real workbook')
            expect(page.locator('#modal .formerror')).to_contain_text('Excel')
            expect(page.locator('[data-price-status]')).to_contain_text('原有效目录不变')
            passed('corrupt XLSX rejected by actual backend')
            file_upload('合成限价.xlsx', vehicle_xlsx(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            expect(page.locator('[data-price-status]')).to_contain_text('原表已保存，尚未发布')
            expect(page.locator('#modal .formerror')).to_contain_text('尚未连接DeepSeek')
            expect(page.locator('[data-policy-confirm-label]')).not_to_be_visible()
            expect(page.locator('[data-policy-tools]')).not_to_be_visible()
            expect(page.get_by_role('button',name='手工添加车型',exact=True)).to_be_visible()
            screenshot('vehicle-recognition-disabled-feedback')
            passed('valid XLSX retained; disabled model failure visible; no publication')
            page.get_by_role('button',name='手工添加车型',exact=True).click()
            expect(page.locator('[data-policy-confirm-label]')).to_be_visible()
            expect(page.locator('[data-policy-tools]')).to_be_visible()
            values={'family':'合成车系','series':'合成系列','model':'合成配置','guide_price_cents':'120000','control_price_cents':'100000','note':'合成限价条件','policy_text':'合成赠品总成本额度，允许替换','policy_limit':'100'}
            page.locator('[data-price-key=policy_mode]').select_option('limit')
            for key,value in values.items(): page.locator('[data-price-key="'+key+'"]').fill(value)
            page.locator('[data-policy-confirm]').check()
            page.locator('#modal button[type=submit]').click()
            expect(page.locator('#modal')).not_to_be_visible()
            expect(page.locator('#br-pricing-vehicle')).to_be_visible()
            expect(page.locator('#br-pricing-gift')).not_to_be_visible()
            expect(page.locator('#br-pricing-vehicle')).to_contain_text('合成配置')
            vehicle_toggle.click(); vehicle_toggle.click(); expect(page.locator('#br-pricing-vehicle')).to_contain_text('合成配置')
            screenshot('desktop-pricing-panels')
            passed('manual recovery confirmed real vehicle import and publication retains panel state')
            # Native sales UI confirms hidden import controls and no catalog amounts.
            login('sales','records-settings')
            expect(page.locator('h1')).to_have_text('门店基础资料')
            expect(page.locator('[data-br-flow=price-upload]')).to_have_count(0)
            passed('sales has no upload controls')
            page.goto(origin + '/#records-sales')
            page.locator('[data-br=new-contract]').click()
            expect(page.locator('[data-br-gift-search]')).to_be_visible()
            expect(page.locator('[data-br-gift-row]:visible')).to_have_count(0)
            expect(page.locator('[data-br-gift-search-status]')).to_contain_text('仅显示已选')
            expect(page.locator('[data-br-gift-selected]')).not_to_contain_text('单价')
            passed('empty query has search hint and no unselected gift rows')
            search=page.locator('[data-br-gift-search]')
            search.fill('脚垫'); expect(page.locator('[data-br-gift-results] [data-br-gift-row]:visible')).to_have_count(1)
            mat=page.locator('[data-br-gift-row]').filter(has_text='合成脚垫')
            mat.locator('[type=checkbox]').check(); mat.locator('input[name^=gift_quantity_]').fill('2')
            search.fill('礼盒'); expect(mat).to_be_visible(); expect(mat.locator('input[name^=gift_quantity_]')).to_have_value('2')
            box=page.locator('[data-br-gift-row]').filter(has_text='合成礼盒'); box.locator('[type=checkbox]').check()
            search.fill('不存在'); expect(page.locator('[data-br-gift-selected] [data-br-gift-row]:visible')).to_have_count(2)
            expect(page.locator('[data-br-gift-search-status]')).to_contain_text('没有找到')
            box.locator('[type=checkbox]').uncheck(); expect(box).not_to_be_visible()
            page.locator('[data-br-gift-search-clear]').click(); expect(mat).to_be_visible(); expect(page.locator('[data-br-gift-row]:visible')).to_have_count(1)
            expect(mat.locator('input[name^=gift_quantity_]')).to_have_value('2')
            passed('search selection, quantities and deselection persist across queries and clearing')
            page.locator('#modal [name=customer_name]').fill('合成合同客户')
            page.locator('#modal [name=customer_phone]').fill('13800009999')
            page.locator('#modal [name=vehicle_price_id]').select_option(label='合成车系 / 合成系列 / 合成配置')
            page.locator('#modal [name=vin]').fill('LTESTSYNTH0000001')
            page.locator('#modal [name=sale_price]').fill('110000')
            page.locator('#modal [name=exterior_color]').select_option('白')
            page.locator('#modal [name=interior_color]').select_option('黑')
            page.locator('[data-br=defer-form]').click()
            page.goto(origin + '/#records-settings')
            page.locator('[data-price-toggle=vehicle]').click()
            page.locator('[data-price-toggle=gift]').click()
            page.locator('[data-price-toggle=vehicle]').click()
            page.goto(origin + '/#records-sales')
            page.locator('[data-br=new-contract]').click()
            expect(page.locator('#modal [name=customer_name]')).to_have_value('合成合同客户')
            mat=page.locator('[data-br-gift-row]').filter(has_text='合成脚垫')
            expect(mat.locator('[type=checkbox]')).to_be_checked(); expect(mat.locator('input[name^=gift_quantity_]')).to_have_value('2')
            expect(page.locator('[data-br-gift-row]:visible')).to_have_count(1)
            passed('contract draft retains form and selected gift quantity')
            page.set_viewport_size({'width':390,'height':844})
            mat.scroll_into_view_if_needed(); screenshot('mobile-selected-gift')
            page.set_viewport_size({'width':1440,'height':1100})
            page.locator('#modal button[type=submit]').click()
            expect(page.locator('#modal')).not_to_be_visible()
            page.wait_for_url('**/#records-sales/*')
            contract_url=page.url
            expect(page.locator('.br-gift-summary')).to_contain_text('合成脚垫')
            expect(page.locator('.br-gift-summary')).not_to_contain_text('合成礼盒')
            page.reload(); expect(page.locator('.br-gift-summary')).to_contain_text('合成脚垫')
            page.locator('[data-br=contract-action][data-action=edit]').click()
            mat=page.locator('[data-br-gift-row]').filter(has_text='合成脚垫')
            expect(mat.locator('[type=checkbox]')).to_be_checked(); expect(mat.locator('input[name^=gift_quantity_]')).to_have_value('2')
            expect(page.locator('[data-br-gift-row]:visible')).to_have_count(1)
            mat.scroll_into_view_if_needed(); screenshot('desktop-saved-contract-gifts')
            passed('actual contract submission, full reload and edit recall frozen gift selection and quantity')
            close_modal()
            login('other_sales','records-sales/'+contract_url.rsplit('/',1)[1])
            expect(page.locator('#main .notice.error')).to_have_text('合同不存在或不可访问')
            expect(page.locator('body')).not_to_contain_text('合成合同客户')
            expect(page.locator('[data-br=contract-action][data-action=edit]')).to_have_count(0)
            passed('same-brand second-store sales cannot read first-store contract')
            assert not report['page_errors'], report['page_errors']
            assert not report['external_requests'], report['external_requests']
            network=json.loads((evidence / 'network.json').read_text())
            assert not network['blocked_external_attempts'], network
            report.update(network)
            unexpected=[r for r in report['responses'] if r['status']>=500 and not r['path'].endswith('/recognize')]
            assert not unexpected, unexpected
            passed('no JavaScript errors, external browser requests or unexpected server errors')
            report['passed']=True
            context.close(); chromium.close()
    except Exception as error:
        report['error']=str(error)
        try: page.screenshot(path=str(evidence / 'failure.png'), full_page=True)
        except Exception: pass
        raise
    finally:
        server.terminate()
        try: server.wait(timeout=10)
        except subprocess.TimeoutExpired: server.kill();server.wait(timeout=5)
        report['server_exit_code'] = server.returncode
        server_log.close()
        report['graceful_shutdown'] = server.returncode in (-15,0) and 'Application shutdown complete.' in (evidence / 'server.log').read_text()
        if not report['graceful_shutdown']:
            report['passed'] = False
            report['shutdown_error'] = 'Application did not exit gracefully'
        (evidence / 'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('Evidence: ' + str(evidence),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--browser',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path(tempfile.gettempdir()) / ('hkos-urgent-browser-'+secrets.token_hex(5)))
    args=parser.parse_args()
    run(args.source,args.browser,args.output)
