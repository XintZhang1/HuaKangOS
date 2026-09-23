"""Real Windows launcher + HTTP Chrome first-admin setup in a NEW preview directory."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    runtime=Path(os.environ['LOCALAPPDATA'])/'huakangos'/('preview-browser-'+uuid.uuid4().hex)
    output=Path(tempfile.mkdtemp(prefix='huakangos-preview-browser-evidence-'))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    launch=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'start-preview.ps1'),'-Port',str(port),'-DataDirectory',str(runtime),'-NoBrowser']
    def start(reuse=False):
        command=list(launch)
        if reuse:
            index=command.index('-Port');del command[index:index+2]
        child_env=os.environ.copy()
        child_env.update(FILE_STORAGE_MODE='blob',PRIVATE_FILE_ROOT='',ALLOW_AI_EXTERNAL='false',SCHEDULER_ENABLED='false')
        # Windows detached grandchildren can retain inherited pipe handles after
        # PowerShell exits. Files keep communicate() from waiting on a live server.
        log=output/('launcher-reuse.log' if reuse else 'launcher-first.log')
        with log.open('wb') as stream:
            result=subprocess.run(command,cwd=ROOT,env=child_env,stdout=stream,stderr=subprocess.STDOUT,creationflags=FLAGS,timeout=150)
        if result.returncode:raise RuntimeError('预览启动器失败；请核查独立测试运行目录中的日志')
        return log.read_text(encoding='utf-8',errors='replace')
    server_pid=None
    try:
        first=start()
        with httpx.Client(base_url=base,trust_env=False) as client:
            before=client.get('/api/local-preview/status').json();server_pid=before['pid']
            assert before['bootstrap_required'] is True
        token=secrets.token_urlsafe(32)
        def ticket(expires):
            (runtime/'bootstrap.json').write_text(json.dumps({'instance_id':before['instance_id'],'token_hash':hashlib.sha256(token.encode()).hexdigest(),'expires_at':expires}),encoding='utf-8')
        ticket(time.time()-1)
        password=secrets.token_urlsafe(28)
        errors=[];screens=[]
        chrome=os.environ.get('CHROMIUM_PATH',r'C:\Program Files\Google\Chrome\Application\chrome.exe')
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(executable_path=chrome,headless=True)
            try:
                context=browser.new_context(viewport={'width':390,'height':844},locale='zh-CN')
                page=context.new_page();page.on('pageerror',lambda error:errors.append(type(error).__name__))
                page.goto(base+'/#preview-setup='+token)
                expect(page.locator('#preview-setup-form')).to_be_visible()
                assert 'preview-setup' not in page.url
                def screenshot(name,selector):
                    page.locator(selector).first.scroll_into_view_if_needed()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                    target=output/name;page.screenshot(path=str(target));screens.append(str(target))
                screenshot('01_first_admin_setup_mobile.png','#preview-setup-form')
                page.locator('[name=username]').fill('preview-browser-admin')
                page.locator('[name=password]').fill(password)
                page.locator('[name=confirmation]').fill(password+'different')
                page.locator('#preview-setup-form button').click()
                expect(page.locator('.formerror')).to_contain_text('两次密码不一致')
                screenshot('02_password_confirmation_refused_mobile.png','.formerror')
                page.locator('[name=confirmation]').fill(password)
                page.locator('#preview-setup-form button').click()
                expect(page.locator('.formerror')).to_contain_text('首次设置链接已失效')
                screenshot('03_expired_setup_refused_mobile.png','.formerror')
                ticket(time.time()+900)
                requests=[]
                page.on('request',lambda request: requests.append(request.url) if request.url.endswith('/api/local-preview/bootstrap') else None)
                # Two submit events before the network returns still send one request.
                page.locator('#preview-setup-form').evaluate("form=>{form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));}")
                expect(page.locator('#main h1')).to_be_visible(timeout=30000)
                assert len(requests)==1
                assert not page.locator('#preview-setup-form').count()
                screenshot('04_local_preview_workbench_mobile.png','#main h1')
                second=start(reuse=True)
                with httpx.Client(base_url=base,trust_env=False) as client:
                    after=client.get('/api/local-preview/status').json()
                    assert after['pid']==server_pid and after['instance_id']==before['instance_id']
                    assert after['repository_id']==before['repository_id'] and after['source_fingerprint']==before['source_fingerprint']
                    assert not after['bootstrap_required']
                    replay=client.post('/api/local-preview/bootstrap',headers={'X-App-Request':'1','X-Local-Preview-Token':token},json={'username':'replacement-admin','password':password})
                    assert replay.status_code==409
                # Fresh browser gets the untouched ordinary login, not setup.
                context.close();context=browser.new_context(viewport={'width':390,'height':844},locale='zh-CN');page=context.new_page()
                page.goto(base);expect(page.locator('.loginform [name=username]')).to_be_visible()
                assert not page.locator('#preview-setup-form').count()
                page.locator('.loginform [name=username]').fill('preview-browser-admin');page.locator('.loginform [name=password]').fill(password);page.locator('.loginform button').click()
                expect(page.locator('#main h1')).to_be_visible(timeout=30000)
                with sqlite3.connect(runtime/'preview.sqlite') as conn:
                    assert conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]==1
                    assert conn.execute('SELECT COUNT(*) FROM flow_cases').fetchone()[0]==0
                    assert conn.execute('SELECT COUNT(*) FROM business_entities').fetchone()[0]==0
                assert not errors
                for file in runtime.glob('*.log'):
                    contents=file.read_text(encoding='utf-8',errors='replace')
                    assert password not in contents and token not in contents
                assert token not in first+second and password not in first+second
                result={'status':'passed','mode':'real-Windows-launcher-and-Chrome-HTTP','viewport':'390x844','steps':['新独立空库首次设置入口，原URL片段立即清除','密码不一致与过期链接中文拒绝；重复提交仅发送一次，正确提交自动进入工作台','不指定端口重复启动仍复用原端口、同一健康PID和原源码指纹；账号保留，原设置请求拒绝','全新浏览器正常登录；没有合成业务或经营主体；日志无密码或设置token'],'screenshots':screens,'javascript_errors':errors,'runtime':str(runtime),'ordinary_url':base,'synthetic_only':True}
                (output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps(result,ensure_ascii=False,indent=2))
                context.close()
            finally:browser.close()
    except Exception as error:
        # Browser exceptions can contain the URL fragment. Do not print them.
        frames=[{'file':Path(frame.filename).name,'line':frame.lineno}
                for frame in traceback.extract_tb(error.__traceback__)]
        print(json.dumps({'status':'failed','error_type':type(error).__name__,'frames':frames,'runtime':str(runtime),'evidence':str(output)},ensure_ascii=False))
        raise SystemExit(1) from None
    finally:
        if not server_pid and (runtime/'process.json').exists():
            try:
                owned=json.loads((runtime/'process.json').read_text(encoding='utf-8'))
                with httpx.Client(trust_env=False,timeout=2) as client:
                    current=client.get(f"http://127.0.0.1:{owned['port']}/api/local-preview/status").json()
                if current['instance_id']==owned['instance_id'] and current['pid']==owned['pid']:
                    server_pid=current['pid']
            except (OSError,ValueError,KeyError,httpx.HTTPError):
                pass
        if server_pid:
            subprocess.run(['taskkill','/PID',str(server_pid),'/T','/F'],capture_output=True,creationflags=FLAGS)


if __name__=='__main__':main()
