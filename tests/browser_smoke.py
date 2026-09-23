"""Optional UI acceptance with a temporary database and random credentials.
Install Playwright separately, then: python tests/browser_smoke.py
An installed Chromium is required; CHROMIUM_PATH overrides its location.
--bridge exercises actual DOM plus HTTP APIs, NOT browser network/CSP/cookies.
No managed browser policy is changed. No external AI calls are made.
"""
from pathlib import Path
import argparse
import base64
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

JS_BRIDGE = r'''
window.__testCsrf='';
Object.defineProperty(document,'cookie',{get:()=>window.__testCsrf?'dealer_csrf='+window.__testCsrf:''});
window.fetch=async(url,opts={})=>{
 let body=opts.body,form=null;
 if(body instanceof FormData){form=[];for(const [key,value] of body.entries()){if(value instanceof Blob){const bytes=new Uint8Array(await value.arrayBuffer());let s='';for(let i=0;i<bytes.length;i++)s+=String.fromCharCode(bytes[i]);form.push({key,name:value.name,type:value.type,content:btoa(s)});}else form.push({key,value});}body=null;}
 const r=await window.bridgeRequest(String(url),opts.method||'GET',opts.headers||{},body||null,form);
 window.__testCsrf=r.csrf;
 const bytes=Uint8Array.from(atob(r.body),c=>c.charCodeAt(0));
 return new Response(bytes,{status:r.status,headers:r.headers});
};
'''


def mount(page, client, base):
    def bridge(source, url, method, headers, body, form):
        headers = {**headers, 'Origin': base}
        if form is None:
            response = client.request(method, url, headers=headers, content=body)
        else:
            fields, files = {}, []
            for entry in form:
                if 'content' in entry:
                    files.append((entry['key'], (entry['name'], base64.b64decode(entry['content']), entry['type'])))
                else:
                    fields[entry['key']] = entry['value']
            response = client.request(method, url, headers=headers, data=fields, files=files)
        return {'body': base64.b64encode(response.content).decode(), 'status': response.status_code,
                'headers': dict(response.headers), 'csrf': client.cookies.get('dealer_csrf', '')}
    page.expose_binding('bridgeRequest', bridge)
    html = (ROOT/'web/index.html').read_text(encoding='utf-8')
    html = html.replace('<link rel="stylesheet" href="/static/styles.css">', '')
    pattern=r'<script src="/static/([A-Za-z0-9_.-]+\.js)" defer></script>'
    scripts=re.findall(pattern,html)
    html=re.sub(pattern,'',html)
    page.set_content(html)
    page.add_style_tag(content=(ROOT/'web/styles.css').read_text(encoding='utf-8'))
    page.add_script_tag(content=JS_BRIDGE)
    page.add_script_tag(content='\n'.join((ROOT/'web'/name).read_text(encoding='utf-8') for name in scripts))


def navigate(page, route):
    page.evaluate('(r)=>{location.hash=r}', route)
    page.wait_for_timeout(750)


def screenshot(page, destination):
    page.wait_for_timeout(350)
    if page.locator('#toast').count():
        page.locator('#toast').evaluate("e=>e.style.display='none'")
    page.screenshot(path=str(destination), full_page=True)


def exercise(page, client, OUT):
    steps = []
    def save(label):
        page.locator('#modal form button[type=submit]').click();page.wait_for_timeout(500)
        if page.locator('#modal .formerror').count():
            text=page.locator('#modal .formerror').inner_text()
            assert not text,text
        steps.append(label)
    # Create a new reception and traverse both feedback branches in the actual form.
    navigate(page,'cases/lead');page.locator('[data-act=newcase]').click();page.wait_for_timeout(350)
    page.locator('[name=customer_name]').fill('页面验收客户');page.locator('[name=customer_phone]').fill('13900008888');page.locator('[name=source]').select_option('展厅到店');save('浏览器新建接待')
    page.wait_for_timeout(500)
    page.locator('[data-key=assign]').click();page.wait_for_timeout(400)
    options=page.locator('[name=assignee_id] option').evaluate_all('(els)=>els.map(x=>({v:x.value,t:x.textContent}))')
    value=next(x['v'] for x in options if '销售' in x['t']);page.locator('[name=assignee_id]').select_option(value);save('分派销售接待')
    page.locator('[data-key=remind]').click();page.wait_for_timeout(300);page.locator('[name=result]').fill('暂未明确车型，约定再次联系');save('接待回访分支')
    page.locator('[data-key=intent]').click();page.wait_for_timeout(300);page.locator('[name=need]').fill('意向购买家用轿车');save('回访转意向分支')
    page.locator('[data-key=reserve]').click();page.wait_for_timeout(350);page.locator('[name=model]').fill('试用车型');page.locator('[name=amount]').fill('128000.00');page.locator('[name=addon]').check();save('意向转预订单')
    lead=client.get('/api/flow/cases?kind=lead&q=页面验收客户',headers={'X-Store-ID':'1'}).json()['items'][0]
    dossier=client.get('/api/flow/cases/'+str(lead['id']),headers={'X-Store-ID':'1'}).json();order=dossier['children'][0]
    navigate(page,'case/'+str(order['id']));assert '车辆订购确认书' in page.locator('body').inner_text();steps.append('订单自动生成文件')
    page.locator('[data-act=upload]').click();page.wait_for_timeout(250)
    page.locator('[name=file]').set_input_files({'name':'沟通确认记录.txt','mimeType':'text/plain','buffer':'试用留痕，不含真实客户资料'.encode()});save('上传留痕附件')
    # Execute confirmation to create simultaneous departmental tasks.
    page.locator('[data-key=approve]').click();page.wait_for_timeout(250);save('确认订单生成并行任务')
    # Full dedicated dashboard and source-table drilldown.
    navigate(page,'analytics/overview');page.locator('#store').select_option('all');page.wait_for_timeout(850)
    screenshot(page, OUT/'01_经营总览.png')
    page.locator('[data-act=charttable][data-table=deliveries]').first.click();page.wait_for_timeout(550);assert page.locator('tbody tr').count()>0;steps.append('经营图表下钻明细')
    navigate(page,'analytics/sales');screenshot(page, OUT/'04_销售分析.png')
    navigate(page,'analytics/repair');assert not page.locator('.errorpage').count();steps.append('维修结算与工单独立视图')
    navigate(page,'analytics/members');assert not page.locator('.errorpage').count();steps.append('会员余额及期间资金变动视图')
    # Return to a store for physical actions and report generation.
    page.locator('#store').select_option('1');page.wait_for_timeout(450);navigate(page,'work');screenshot(page, OUT/'02_我的工作.png')
    navigate(page,'case/'+str(order['id']));screenshot(page, OUT/'03_订单办理.png')
    navigate(page,'master/templates');screenshot(page, OUT/'06_模板管理.png');steps.append('公司模板启用与版本管理页面')
    navigate(page,'reports');page.locator('[data-act=newreport]').click();page.wait_for_timeout(350);save('程序生成并保存经营日报');page.wait_for_timeout(900)
    assert '新流程和既有记录合并' in page.locator('body').inner_text();screenshot(page, OUT/'07_每日汇总.png')
    navigate(page,'audit');assert not page.locator('.errorpage').count();steps.append('审计历史与中文时间显示')
    page.set_viewport_size({'width':390,'height':844});navigate(page,'work');screenshot(page, OUT/'05_手机待办.png')
    navigate(page,'analytics/sales');screenshot(page, OUT/'08_手机图表.png')
    # Download original generated bytes over real HTTP, validate archive structure.
    d=client.get('/api/flow/cases/'+str(order['id']),headers={'X-Store-ID':'1'}).json();fid=next(f['id'] for f in d['files'] if f['generated'])
    response=client.get('/api/flow/files/'+str(fid),headers={'X-Store-ID':'1'});assert response.status_code==200 and response.content[:2]==b'PK'
    assert 'attachment' in response.headers['content-disposition'];steps.append('经过权限校验下载自动生成文档')
    r=client.get('/api/flow/analytics/export?dataset=deliveries',headers={'X-Store-ID':'all'});assert r.status_code==200 and r.content.startswith(b'\xef\xbb\xbf');steps.append('中文表头明细导出')
    return steps


def exercise_employee_pdi(page, client, output, administrator_password):
    """Actual employee forms on a narrow viewport; all data and credentials synthetic."""
    steps=[]
    base=str(client.base_url).rstrip('/')
    with httpx.Client(base_url=base,timeout=45,trust_env=False) as admin_client:
        login_result=admin_client.post('/api/auth/login',json={'username':'admin','password':administrator_password},
            headers={'X-App-Request':'1'})
        assert login_result.status_code==200,login_result.text
        def api(method,path,**kwargs):
            headers={'X-Store-ID':'1','X-App-Request':'1','Origin':base,
                     'X-CSRF-Token':admin_client.cookies.get('dealer_csrf','')}
            result=admin_client.request(method,path,headers=headers,**kwargs)
            assert result.status_code<400,(result.status_code,result.text)
            return result.json()
        def dossier():return api('GET','/api/flow/cases/'+str(order_id))
        def action(key,values=None):
            current=dossier()
            return api('POST',f'/api/flow/cases/{order_id}/actions/{key}',json={
                'version':current['version'],'request_id':secrets.token_hex(16),'values':values or {}})
        def proof(name,category='evidence',source=None):
            values={'category':category}
            if source:values['source_file_id']=str(source)
            return api('POST',f'/api/flow/cases/{order_id}/files',data=values,
                       files={'file':(name,'完全虚构的浏览器验收凭据'.encode(),'text/plain')})['id']
        staff={}
        for role in ('service','technician'):
            username='pdi_'+role+'_'+secrets.token_hex(4)
            initial=secrets.token_urlsafe(28);personal=secrets.token_urlsafe(28)
            created=api('POST','/api/users',json={'username':username,'display_name':'PDI验收'+role,
                'role':role,'password':initial,'store_ids':[1]})
            with httpx.Client(base_url=base,timeout=45,trust_env=False) as employee:
                response=employee.post('/api/auth/login',json={'username':username,'password':initial},headers={'X-App-Request':'1'})
                assert response.status_code==200,response.text
                response=employee.post('/api/auth/password',json={'current_password':initial,'new_password':personal},
                    headers={'X-App-Request':'1','X-CSRF-Token':employee.cookies.get('dealer_csrf',''),'Origin':base})
                assert response.status_code==200,response.text
            staff[role]={'id':created['id'],'username':username,'password':personal}
        vehicle_id=api('GET','/api/flow/lookup/vehicle')['items'][0]['id']
        vehicle=api('GET','/api/records/vehicles/'+str(vehicle_id))
        today_value=api('GET','/api/flow/catalog')['today']
        order=api('POST','/api/flow/cases',json={'kind':'order','request_id':secrets.token_hex(16),
            'values':{'customer_name':'手机PDI验收虚构客户','model':vehicle['model'],'amount':'100','delivery_due':today_value}})
        order_id=order['id'];action('approve');action('allocate',{'vehicle_id':vehicle_id})
        source=next(f['id'] for f in dossier()['files'] if f['generated'] and f['category']=='contract')
        action('sign',{'evidence_id':proof('PDI签约凭据.txt','signed_contract',source)})
        account_id=api('GET','/api/flow/master/accounts')['items'][0]['id']
        action('receive',{'amount':'100','account_id':account_id,'reference':'PDI-'+secrets.token_hex(8),'evidence_id':proof('PDI付款凭据.txt')})
        def assign(key,role):
            task=next(t for t in dossier()['tasks'] if t['key']==key)
            api('POST',f"/api/flow/tasks/{task['id']}/assign",json={'version':task['version'],
                'assignee_id':staff[role]['id'],'reason':'虚构浏览器验收岗位交接'})
        def login_employee(role):
            page.locator('[data-act=logout]').click()
            page.locator('[name=username]').fill(staff[role]['username'])
            page.locator('[name=password]').fill(staff[role]['password'])
            page.locator('.loginform button[type=submit]').click();page.wait_for_selector('#store')
            navigate(page,'case/'+str(order_id))
            assert not page.locator('.errorpage').count()
        def save_form():
            page.locator('#modal form button[type=submit]').click()
            page.locator('#modal').wait_for(state='hidden')
            if page.locator('#modal .formerror').count():assert not page.locator('#modal .formerror').inner_text()
        def upload_ui(name,category):
            page.locator('[data-act=upload]').click()
            page.locator('[name=category]').select_option(category)
            page.locator('[name=file]').set_input_files({'name':name,'mimeType':'text/plain','buffer':('合成验收凭据 '+name).encode()})
            save_form()
            return next(f['id'] for f in dossier()['files'] if f['name']==name)
        def employee_action(key,result,fid,outcome=None):
            page.locator('[data-key='+key+']').click()
            page.locator('[name=result]').fill(result)
            page.locator('[name=evidence_id]').select_option(str(fid))
            if outcome:page.locator('[name=outcome]').select_option(outcome)
            save_form()
        assign('inspect','service')
        page.set_viewport_size({'width':390,'height':844});login_employee('service')
        inspection=upload_ui('PDI初检.txt','inspection')
        employee_action('inspect','外观缺陷，暂不能交付',inspection,'不合格')
        assert dossier()['data']['inspection_status']=='failed'
        page.get_by_text('检查不合格，禁止出库',exact=True).wait_for()
        assert page.locator('[data-key=dispatch]').count()==0  # Service does not receive inventory actions.
        steps.append('服务员工手机初检不合格并生成缺陷任务')
        blocked=next(a for a in dossier()['actions'] if a['key']=='dispatch')
        assert not blocked['enabled'] and '检查' in blocked['reason']
        screenshot(page,output/'09_员工手机检查不合格.png')
        assign('rectify','technician');login_employee('technician')
        rectification=upload_ui('PDI缺陷处理.txt','evidence')
        employee_action('rectify','处理外观缺陷并完成自查',rectification)
        assert dossier()['data']['inspection_status']=='awaiting_reinspection'
        page.get_by_text('缺陷已处理，等待复检',exact=True).wait_for()
        steps.append('技师手机记录实际缺陷处理并交回复检')
        assign('reinspect','service');login_employee('service')
        inspection=upload_ui('PDI复检.txt','inspection')
        employee_action('reinspect','按交车项目重新检查，全部合格',inspection,'合格')
        assert dossier()['data']['inspection_status']=='passed'
        page.get_by_text('交车检查合格',exact=True).wait_for()
        assert next(a for a in dossier()['actions'] if a['key']=='dispatch')['enabled']
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        screenshot(page,output/'10_员工手机复检合格.png')
        steps.append('服务员工手机复检通过后才开放库管出库条件')
    return steps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bridge', action='store_true')
    parser.add_argument('--screenshots', type=Path, help='Optional synthetic-data screenshots directory')
    args = parser.parse_args()
    executable = os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('google-chrome')
    if not executable:
        executable=next((str(path) for path in [Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')] if path.is_file()),None)
    if not executable:
        raise SystemExit('Chromium not found; install it or set CHROMIUM_PATH.')
    with tempfile.TemporaryDirectory(prefix='dealerdesk-ui-') as work_string:
        work = Path(work_string)
        output = (args.screenshots or Path(tempfile.mkdtemp(prefix='huakangos-smoke-evidence-'))).resolve()
        if output==ROOT or ROOT in output.parents:raise SystemExit('截图与验收输出须存放在仓库之外。')
        output.mkdir(parents=True, exist_ok=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        password = secrets.token_urlsafe(28)
        env = {**os.environ, 'DATABASE_URL': 'sqlite:///'+(work/'trial.sqlite').as_posix(),
               'FILE_STORAGE_MODE': 'blob', 'PRIVATE_FILE_ROOT': '',
               'SCHEDULER_ENABLED': 'false', 'FILE_SCAN_MODE': 'structure_only', 'APP_ENV': 'test', 'ALLOWED_HOSTS': '127.0.0.1,localhost',
               'ALLOW_AI_EXTERNAL': 'false', 'DEEPSEEK_API_KEY': '', 'COOKIE_SECURE': 'false',
               'LEGACY_BUSINESS_WRITE': 'false', 'DEALER_INITIAL_PASSWORD': password,'HUAKANGOS_INITIAL_PASSWORD':password}
        subprocess.run([sys.executable, '-m', 'app.cli', 'init', '--demo'], cwd=ROOT, env=env,
                       check=True, capture_output=True, text=True)
        with (work/'server.log').open('w', encoding='utf-8') as log:
            server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                                       '--port', str(port)], cwd=ROOT, env=env, stdout=log, stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                with httpx.Client(base_url=base, timeout=45, trust_env=False) as client:
                    for _ in range(120):
                        if server.poll() is not None:
                            raise RuntimeError('Test server exited before becoming ready.')
                        try:
                            if client.get('/api/health').status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(.1)
                    else:
                        raise RuntimeError('Test server did not become ready. '+(work/'server.log').read_text(encoding='utf-8',errors='replace')[-4000:])
                    with sync_playwright() as playwright:
                        browser = playwright.chromium.launch(executable_path=executable, headless=True,
                                                             args=['--no-sandbox', '--disable-dev-shm-usage'])
                        try:
                            page = browser.new_page(viewport={'width':1512,'height':1100}, locale='zh-CN')
                            errors = []
                            page.on('pageerror', lambda error: errors.append(str(error)))
                            if args.bridge:
                                mount(page, client, base)
                            else:
                                page.goto(base)
                            page.locator('[name=username]').fill('admin')
                            page.locator('[name=password]').fill(password)
                            page.locator('button[type=submit]').click()
                            page.wait_for_selector('#store')
                            if not args.bridge:
                                for cookie in page.context.cookies():
                                    client.cookies.set(cookie['name'], cookie['value'])
                            steps = exercise(page, client, output)
                            steps += exercise_employee_pdi(page, client, output, password)
                            assert not errors, errors
                            result = {'mode': 'DOM + HTTP bridge (not browser network E2E)' if args.bridge else 'browser HTTP',
                                      'passed': len(steps), 'steps': steps, 'javascript_errors': errors}
                            (output/'acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                            print(json.dumps(result, ensure_ascii=False, indent=2))
                        finally:
                            browser.close()
            finally:
                if server.poll() is None:
                    if os.name=='nt':
                        subprocess.run(['taskkill','/PID',str(server.pid),'/T','/F'],stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill(); server.wait(timeout=5)


if __name__ == '__main__':
    main()
