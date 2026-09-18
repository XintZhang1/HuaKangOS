"""Optional real-browser smoke test. Uses an isolated DB and random passwords.
Requires playwright and Chromium. python tests/browser_smoke.py
Use --bridge only for offline DOM + real API testing; not a full network E2E test.
Writes synthetic-data screenshots to docs/. Never connects to DeepSeek.
"""
from pathlib import Path
import os
import base64
import httpx
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(tempfile.mkdtemp(prefix='dealerdesk-browser-'))
PASSWORD=secrets.token_urlsafe(22)
TEMP_PASSWORD=secrets.token_urlsafe(22)
NEW_PASSWORD=secrets.token_urlsafe(22)
PORT=18765
BASE=f'http://127.0.0.1:{PORT}'
BRIDGE='--bridge' in sys.argv
BRIDGE_CLIENTS={}
env={**os.environ,'DATABASE_URL':'sqlite:///'+str(WORK/'demo.sqlite'),'SCHEDULER_ENABLED':'false','APP_ENV':'test',
    'ALLOWED_HOSTS':'127.0.0.1,localhost','ALLOW_AI_EXTERNAL':'false','DEEPSEEK_API_KEY':'','COOKIE_SECURE':'false',
    'DEALER_INITIAL_PASSWORD':PASSWORD}
subprocess.run([sys.executable,'-m','app.cli','init','--demo'],cwd=ROOT,env=env,check=True,capture_output=True)
log=open(WORK/'server.log','w')
server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(PORT)],cwd=ROOT,env=env,stdout=log,stderr=log)


def wait_ready():
    for _ in range(100):
        try:
            with urllib.request.urlopen(BASE+'/api/health',timeout=1) as r:
                if r.status==200:return
        except Exception:time.sleep(.1)
    raise RuntimeError('Test server failed to start')


def mount_bridge(page):
    """Offline DOM + real local HTTP API bridge. Does NOT test browser networking,
    cookie enforcement, CSP or downloads; normal mode tests those separately.
    Does not alter or bypass the container's managed network policy.
    """
    if page in BRIDGE_CLIENTS:
        page.evaluate('window.__resetLogin()')
        return
    client=httpx.Client(base_url=BASE,timeout=90)
    BRIDGE_CLIENTS[page]=client
    def request(data):
        headers={**data.get('headers',{}),'Origin':BASE}
        response=client.request(data.get('method','GET'),data['path'],headers=headers,content=data.get('body'))
        return {'body':base64.b64encode(response.content).decode(),'status':response.status_code,
                'headers':dict(response.headers),'csrf':client.cookies.get('dealer_csrf','')}
    html=(ROOT/'web/index.html').read_text()
    html=re.sub(r'<script\b[^>]*>.*?</script>','',html,flags=re.S)
    html=re.sub(r'<link\b[^>]*>','',html)
    page.set_content(html)
    page.add_style_tag(content=(ROOT/'web/style.css').read_text())
    page.expose_function('_dealerBridge',request)
    page.add_script_tag(content="""
        window.__csrf='';
        Object.defineProperty(document,'cookie',{configurable:true,get:()=>window.__csrf?'dealer_csrf='+window.__csrf:''});
        window.fetch=async(path,options={})=>{
          const r=await window._dealerBridge({path:String(path),...options});window.__csrf=r.csrf;
          const bytes=Uint8Array.from(atob(r.body),c=>c.charCodeAt(0));
          return new Response(bytes,{status:r.status,headers:r.headers});
        };
    """)
    page.add_script_tag(content='(()=>{'+(ROOT/'web/app.js').read_text()+"\nwindow.__resetLogin=()=>{state.user=null;renderLogin();};})();")


def login_page(page,username,password):
    if BRIDGE: mount_bridge(page)
    else: page.goto(BASE)
    page.locator('#login-form input[name=username]').fill(username)
    page.locator('#login-form input[name=password]').fill(password)
    page.locator('#login-form button[type=submit]').click()


def nav(page,module):
    page.locator(f'.nav-item[data-route="{module}"]').click()
    page.locator('.loading-line').wait_for(state='hidden')


def save_submit(page):
    page.locator('#modal button[type=submit][value=submit]').click()
    page.locator('#modal').wait_for(state='hidden')
    page.locator('.loading-line').wait_for(state='hidden')


def first_row_id(page):
    text=page.locator('tbody tr').first.inner_text()
    return int(re.search(r'ID (\d+)',text).group(1))


def first_action(page,action):
    page.locator('tbody tr').first.locator(f'[data-workflow="{action}"]').click()
    page.locator('#field-reason').fill('浏览器测试：已核对对应原始单据')
    page.locator('#modal button[type=submit]').click()
    page.locator('#modal').wait_for(state='hidden')
    page.locator('.loading-line').wait_for(state='hidden')


try:
    wait_ready()
    with sync_playwright() as p:
        executable=os.getenv('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('google-chrome')
        browser=p.chromium.launch(headless=True,executable_path=executable,args=['--no-sandbox','--disable-dev-shm-usage'])
        context=browser.new_context(viewport={'width':1440,'height':1080},locale='zh-CN')
        page=context.new_page();errors=[];console_errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('console',lambda e:console_errors.append(e.text) if e.type=='error' and '401' not in e.text else None)
        login_page(page,'admin',PASSWORD)
        page.get_by_role('heading',name='经营总览',exact=True).wait_for()
        page.locator('.kpi').first.wait_for()
        page.locator('#toast').evaluate("e=>e.className=''");page.wait_for_timeout(220)
        page.screenshot(path=str(ROOT/'docs'/'01_dashboard.png'),full_page=True)
        nav(page,'vehicles');page.locator('[data-action=new]').click()
        for name,value in {'vin':'LDD00000000000999','brand':'浏览器测试牌','model':'浏览器测试车','purchase_cost':'100000.00','list_price':'120000.00'}.items():
            page.locator('#field-'+name).fill(value)
        save_submit(page);vehicle_id=first_row_id(page);first_action(page,'approve')
        assert '已审核' in page.locator('tbody tr').first.inner_text()
        page.locator('#toast').evaluate("e=>e.className=''");page.wait_for_timeout(220)
        page.screenshot(path=str(ROOT/'docs'/'02_inventory.png'),full_page=False)
        nav(page,'sales');page.locator('[data-action=new]').click()
        for name,value in {'vehicle_id':str(vehicle_id),'salesperson':'浏览器员工','customer_name':'浏览器客户','contract_amount':'110000.00'}.items():page.locator('#field-'+name).fill(value)
        save_submit(page);sale_id=first_row_id(page);first_action(page,'approve');first_action(page,'advance')
        assert '已交车' in page.locator('tbody tr').first.inner_text()
        nav(page,'cash');page.locator('[data-action=new]').click()
        for name,value in {'amount':'110000.00','account':'浏览器测试账户','voucher_no':'UI-BANK-001','related_id':str(sale_id)}.items():page.locator('#field-'+name).fill(value)
        save_submit(page);first_action(page,'approve')
        nav(page,'policies');page.locator('[data-action=new]').click()
        for name,value in {'policy_number':'UI-POLICY-001','insurer':'浏览器保险机构','plate_number':'沪TEST001','customer_name':'浏览器客户','premium':'5000.00','commission':'500.00'}.items():page.locator('#field-'+name).fill(value)
        save_submit(page);policy_id=first_row_id(page);first_action(page,'approve')
        nav(page,'repairs');page.locator('[data-action=new]').click()
        for name,value in {'plate_number':'沪TEST001','service_advisor':'浏览器售后员工','customer_name':'浏览器客户','policy_id':str(policy_id),'labor_amount':'300.00','parts_amount':'700.00','cost_amount':'600.00'}.items():page.locator('#field-'+name).fill(value)
        page.locator('#field-repair_type').select_option('insurance')
        save_submit(page);first_action(page,'approve');first_action(page,'advance')
        assert '已完工' in page.locator('tbody tr').first.inner_text()
        nav(page,'reports');page.locator('[data-action=preview-report]').click()
        page.get_by_role('heading',name='外发数据预览').wait_for()
        assert '浏览器客户' not in page.locator('.json-view').inner_text()
        page.locator('#modal [data-action=close-modal]').last.click()
        page.locator('[data-action=generate-report]').click()
        page.get_by_role('heading',name='经营汇总与规则审查').wait_for()
        assert '110,000.00' not in page.locator('.inline-error').all_inner_texts()
        page.locator('#toast').evaluate("e=>e.className=''");page.wait_for_timeout(220)
        page.screenshot(path=str(ROOT/'docs'/'03_daily_report.png'),full_page=False)
        nav(page,'findings');page.locator('.finding-card').first.wait_for()
        page.locator('#toast').evaluate("e=>e.className=''");page.wait_for_timeout(220)
        page.screenshot(path=str(ROOT/'docs'/'04_review_center.png'),full_page=False)
        page.locator('[data-action=review]').first.click()
        page.locator('#field-status').select_option('reviewing');page.locator('#field-note').fill('测试复核：已经联系经办人核对原始单据。')
        page.locator('#modal button[type=submit]').click();page.locator('#modal').wait_for(state='hidden')
        nav(page,'users');page.locator('[data-action=new-user]').click()
        for name,value in {'username':'ui-sales','display_name':'浏览器销售员工','password':TEMP_PASSWORD}.items():page.locator('#field-'+name).fill(value)
        page.locator('#field-role').select_option('sales');page.locator('#modal button[type=submit]').click();page.locator('#modal').wait_for(state='hidden')
        employee_context=browser.new_context(viewport={'width':1280,'height':900},locale='zh-CN')
        employee=employee_context.new_page();employee.on('pageerror',lambda e:errors.append(str(e)))
        login_page(employee,'ui-sales',TEMP_PASSWORD)
        employee.get_by_role('heading',name='修改我的密码').wait_for()
        employee.locator('#field-current_password').fill(TEMP_PASSWORD)
        employee.locator('#field-new_password').fill(NEW_PASSWORD)
        employee.locator('#field-confirmation').fill(NEW_PASSWORD)
        employee.locator('#modal button[type=submit]').click()
        employee.locator('#login-form').wait_for();login_page(employee,'ui-sales',NEW_PASSWORD)
        employee.get_by_role('heading',name='门店销售',exact=True).wait_for()
        assert employee.locator('.nav-item[data-route=cash]').count()==0
        assert (BRIDGE_CLIENTS[employee].get('/api/dashboard').status_code if BRIDGE else employee.request.get(BASE+'/api/dashboard').status)==403
        nav(employee,'vehicles')
        assert employee.get_by_role('columnheader',name='采购成本').count()==0
        employee_context.close()
        nav(page,'cash')
        if BRIDGE:
            assert BRIDGE_CLIENTS[page].get('/api/export/cash').content.startswith(b'\xef\xbb\xbf')
        else:
            with page.expect_download() as download_info:page.locator('[data-action=export]').click()
            download_info.value.save_as(WORK/'cash.csv')
            assert (WORK/'cash.csv').read_bytes().startswith(b'\xef\xbb\xbf')
        # Multi-store admin, real form submission, isolated inventory and feedback.
        nav(page,'stores');page.locator('[data-action=new-store]').click()
        page.locator('#field-code').fill('EAST');page.locator('#field-name').fill('东城门店 · 演示')
        page.locator('#modal button[type=submit]').click();page.locator('#modal').wait_for(state='hidden')
        page.locator('tbody').get_by_text('东城门店 · 演示',exact=True).wait_for()
        page.screenshot(path=str(ROOT/'docs'/'06_stores.png'),full_page=True)
        options=page.locator('#store-switch option').evaluate_all("opts=>opts.map(o=>({value:o.value,text:o.textContent}))")
        second=next(o['value'] for o in options if '东城门店' in o['text'])
        page.locator('#store-switch').select_option(second)
        page.wait_for_timeout(300);nav(page,'vehicles')
        assert 'LDD00000000000999' not in page.locator('#main').inner_text()
        nav(page,'feedback');page.locator('[data-action=new-feedback]').click()
        page.locator('#field-title').fill('希望库存提示更清楚')
        page.locator('#field-description').fill('希望把超龄车辆的提醒放在更显眼的位置，方便每天检查。')
        page.locator('#modal button[type=submit]').click();page.locator('#modal').wait_for(state='hidden')
        page.locator('.feedback-card').get_by_text('#1 希望库存提示更清楚',exact=True).wait_for()
        page.screenshot(path=str(ROOT/'docs'/'07_feedback.png'),full_page=True)
        page.locator('#store-switch').select_option('1');page.wait_for_timeout(300)
        assert page.locator('.feedback-card').count()==0
        page.locator('#store-switch').select_option('all');page.wait_for_timeout(300)
        nav(page,'dashboard');page.get_by_role('heading',name='各门店经营对照').wait_for()
        page.screenshot(path=str(ROOT/'docs'/'01_dashboard.png'),full_page=True)
        nav(page,'dashboard');page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(350)
        page.locator('#toast').evaluate("e=>e.className=''");page.wait_for_timeout(220)
        page.screenshot(path=str(ROOT/'docs'/'05_mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+2'),page.evaluate("[...document.querySelectorAll('*')].map(e=>[e.tagName,e.className,e.getBoundingClientRect().right,e.scrollWidth,e.clientWidth]).filter(r=>r[2]>392)")
        assert not errors,errors
        assert not console_errors,console_errors
        browser.close()
        print(('OFFLINE DOM + REAL LOCAL API BRIDGE PASSED: ' if BRIDGE else 'BROWSER SMOKE PASSED: ')+ ' all five forms; submit/approve; delivery/completion; cash link; AI preview; report; review; CSV; forced password change; staff RBAC; store creation/switch/combined dashboard; feedback creation/isolation; mobile layout.')
finally:
    server.terminate()
    try:server.wait(timeout=5)
    except subprocess.TimeoutExpired:server.kill();server.wait()
    log.close()
    for client in BRIDGE_CLIENTS.values():client.close()
