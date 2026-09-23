"""Opt-in TLS browser acceptance against a fresh synthetic local instance.

Uses a one-day local certificate and an isolated Chromium SPKI pin; installs no
certificate and never disables certificate errors globally. A synthetic clamd
protocol peer only exercises scan transport. This is not production acceptance.
"""
from pathlib import Path
from contextlib import contextmanager
import argparse
import base64
import hashlib
import io
import json
import os
import secrets
import shutil
import socket
import socketserver
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time

import httpx
from PIL import Image
from playwright.sync_api import sync_playwright, expect
from browser_huakangos import (
    ROOT, chromium_path, checked_request, login_page, save_modal,
    take_screenshot, assert_fits_mobile, request,
)


def exact(sock, size):
    data=b''
    while len(data)<size:
        part=sock.recv(size-len(data))
        if not part:raise ValueError('Incomplete synthetic scanner request')
        data+=part
    return data


@contextmanager
def synthetic_scanner():
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(5)
            command=b''
            while not command.endswith(b'\0'):command+=exact(self.request,1)
            if command==b'zVERSION\0':
                self.request.sendall(b'ClamAV synthetic-TLS-test/no-signatures\0')
            elif command==b'zINSTREAM\0':
                total=0
                while True:
                    size=struct.unpack('!I',exact(self.request,4))[0]
                    if not size:break
                    total+=size
                    if total>12*1024*1024:raise ValueError('Synthetic stream too large')
                    exact(self.request,size)
                self.request.sendall(b'stream: OK\0')
            else:raise ValueError('Unsupported synthetic scanner command')
    class Server(socketserver.ThreadingTCPServer):
        daemon_threads=True
    with Server(('127.0.0.1',0),Handler) as server:
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        try:yield server.server_address[1]
        finally:server.shutdown();worker.join(5)


def certificate(openssl, work):
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    cert,key=work/'certificate.pem',work/'private-key.pem'
    config=work/'openssl.cnf'
    config.write_text('[req]\nprompt=no\ndistinguished_name=subject\n[subject]\nCN=localhost\n',encoding='ascii')
    def command(args,content=None):
        result=subprocess.run([openssl,*map(str,args)],input=content,capture_output=True,
            creationflags=flags,timeout=30)
        if result.returncode:raise RuntimeError('Temporary certificate command failed')
        return result.stdout
    command(['req','-x509','-config',config,'-newkey','rsa:2048','-nodes','-days','1','-keyout',key,
        '-out',cert,'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'])
    key.chmod(0o600)
    public=command(['x509','-in',cert,'-pubkey','-noout'])
    der=command(['pkey','-pubin','-outform','DER'],public)
    return cert,key,base64.b64encode(hashlib.sha256(der).digest()).decode('ascii')


def stop_server(server):
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    if server.poll() is None:
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(server.pid),'/T','/F'],
                capture_output=True,creationflags=flags)
        else:server.terminate()
    try:server.wait(timeout=10)
    except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)


def exercise(browser, base, password, output, work):
    contexts=[];errors=[];steps=[];screens=[]
    def page(width):
        context=browser.new_context(viewport={'width':width,'height':844},
            locale='zh-CN',accept_downloads=True,ignore_https_errors=False)
        contexts.append(context);p=context.new_page()
        p.on('pageerror',lambda error:errors.append(str(error)))
        return p
    admin=page(1280);staff=page(390)
    try:
        response=admin.goto(base)
        assert response.status==200
        assert response.headers['strict-transport-security']=='max-age=31536000'
        assert "script-src 'self'" in response.headers['content-security-policy']
        assert "frame-ancestors 'none'" in response.headers['content-security-policy']
        login_page(admin,base,'admin',password)
        pwd=secrets.token_urlsafe(24)
        checked_request(admin,'/api/users','POST',{'username':'tls-sales','display_name':'合成HTTPS销售',
            'role':'sales','password':pwd,'store_roles':[{'store_id':1,'role':'sales'}]},status=201)
        login_page(staff,base,'tls-sales',pwd)
        final=secrets.token_urlsafe(24)
        staff.locator('#modal [name=current_password]').fill(pwd)
        staff.locator('#modal [name=new_password]').fill(final);save_modal(staff)
        login_page(staff,base,'tls-sales',final)
        cookies={c['name']:c for c in staff.context.cookies()}
        assert cookies['dealer_session']['secure'] and cookies['dealer_session']['httpOnly']
        assert cookies['dealer_csrf']['secure'] and not cookies['dealer_csrf']['httpOnly']
        assert cookies['dealer_session']['sameSite']==cookies['dealer_csrf']['sameSite']=='Strict'
        assert 'dealer_session=' not in staff.evaluate('document.cookie')
        assert staff.evaluate('window.isSecureContext') is True
        steps.append('真实 TLS 登录和员工首次改密；Secure/HttpOnly/SameSite Cookie 及安全上下文核对')
        assert request(staff,'/api/users')['status']==403
        assert request(staff,'/api/flow/cases','POST',{},csrf=False)['status']==403
        assert request(staff,'/api/auth/me',store=999999)['status']==403
        # Scripts added as actual DOM nodes obey CSP; Playwright evaluation itself
        # is a testing transport and is not used as the CSP enforcement assertion.
        staff.evaluate("""()=>{const s=document.createElement('script');
            s.textContent='window.__hk_forbidden_inline=1';document.body.appendChild(s)}""")
        assert staff.evaluate('window.__hk_forbidden_inline===undefined')
        steps.append('真实浏览器拒绝无CSRF写入/外店范围/员工管理账号，CSP阻止新增内联脚本')
        from datetime import datetime
        from zoneinfo import ZoneInfo
        row=checked_request(staff,'/api/flow/cases','POST',{'request_id':secrets.token_hex(16),
            'kind':'order','values':{'customer_name':'合成HTTPS附件客户','model':'合成TLS车型',
            'amount':'100.00','delivery_due':datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()}},status=201)
        staff.goto(base+'/#case/'+str(row['id']))
        expect(staff.locator('#main h1')).to_have_text(row['title'])
        buffer=io.BytesIO();Image.new('RGB',(300,200),(34,80,122)).save(buffer,'PNG')
        content=buffer.getvalue()
        staff.locator('[data-act=upload]').click()
        staff.locator('#modal [name=category]').select_option('evidence')
        staff.locator('#modal [name=file]').set_input_files({'name':'合成HTTPS照片.png',
            'mimeType':'image/png','buffer':content});save_modal(staff)
        expect(staff.locator('#main')).to_contain_text('合成HTTPS照片.png')
        detail=checked_request(staff,'/api/flow/cases/'+str(row['id']))
        asset=next(f for f in detail['files'] if f['name']=='合成HTTPS照片.png')
        assert asset['security']['engine_version'].startswith('ClamAV synthetic')
        with staff.expect_download() as item:
            staff.locator('[data-act=downloadfile][data-id="'+str(asset['id'])+'"]').click()
        downloaded=work/'downloaded.png';item.value.save_as(downloaded)
        assert downloaded.read_bytes()==content
        staff.reload();expect(staff.locator('#main h1')).to_have_text(row['title'])
        assert_fits_mobile(staff)
        screens.append(take_screenshot(staff,output,'01_https_employee_mobile.png'))
        staff.emulate_media(media='print')
        pdf=staff.pdf(format='A4',print_background=True)
        assert pdf.startswith(b'%PDF-') and len(pdf)>1000
        (work/'synthetic-browser-print.pdf').write_bytes(pdf)
        staff.emulate_media(media='screen')
        steps.append('390px员工页实际HTTPS上传合成PNG/私有对象下载字节一致，刷新会话及浏览器打印成功')
        staff.locator('[data-act=logout]').click()
        expect(staff.locator('.loginform')).to_be_visible()
        assert request(staff,'/api/flow/cases/'+str(row['id']))['status']==401
        steps.append('退出后原受保护业务请求返回401')
        assert not errors,errors
        return {'mode':'real-https-chrome-pinned-temporary-key','passed':len(steps),
            'steps':steps,'javascript_errors':errors,'screenshots':screens,
            'limitations':['仅本机直连Uvicorn TLS；不是正式域名证书、反向代理或多机部署验收',
                'Chromium只允许本次临时公钥SPKI；未安装系统根证书，未全局忽略证书错误',
                '合成ClamAV协议服务无病毒库；PNG由程序生成，不证明实机相机或真实扫描',
                '全新随机密码合成库，未访问公司资料']}
    except Exception:
        take_screenshot(staff,output,'failure_https_employee.png')
        raise
    finally:
        for context in contexts:context.close()


def main():
    sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--openssl',default=shutil.which('openssl'))
    args=parser.parse_args()
    if not args.openssl or not Path(args.openssl).is_file():raise SystemExit('需要可用的OpenSSL可执行文件。')
    executable=chromium_path()
    if not executable:raise SystemExit('需要Chrome或Edge。')
    output=Path(tempfile.mkdtemp(prefix='huakangos-https-evidence-')).resolve()
    work=Path(tempfile.mkdtemp(prefix='huakangos-https-test-')).resolve()
    if work.is_relative_to(ROOT) or output.is_relative_to(ROOT):raise ValueError('Only external temporary artifacts allowed')
    print('TLS acceptance evidence: '+str(output),flush=True)
    result={'status':'failed','temporary_directory':str(work)}
    try:
        cert,key,pin=certificate(args.openssl,work)
        context=ssl.create_default_context(cafile=str(cert))
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        base='https://127.0.0.1:'+str(port)
        password=secrets.token_urlsafe(28)
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        with synthetic_scanner() as scanner_port:
            env={**os.environ,'DATABASE_URL':'sqlite:///'+(work/'synthetic.sqlite').as_posix(),
                'APP_ENV':'production','ALLOWED_HOSTS':'127.0.0.1,localhost','COOKIE_SECURE':'true',
                'FILE_STORAGE_MODE':'private_local','PRIVATE_FILE_ROOT':str(work/'private-objects'),
                'FILE_SCAN_MODE':'clamav','CLAMAV_HOST':'127.0.0.1','CLAMAV_PORT':str(scanner_port),
                'ALLOW_AI_EXTERNAL':'false','DEEPSEEK_API_KEY':'','LEGACY_BUSINESS_WRITE':'false',
                'SCHEDULER_ENABLED':'false','SCHEDULER_MODE':'off','HUAKANGOS_INITIAL_PASSWORD':password,
                'DEALER_INITIAL_PASSWORD':password,'PYTHONUTF8':'1'}
            initialized=subprocess.run([sys.executable,'-m','app.cli','init'],cwd=ROOT,env=env,
                capture_output=True,creationflags=flags,timeout=60)
            if initialized.returncode:raise RuntimeError('Synthetic TLS database initialization failed')
            with (work/'server.log').open('w',encoding='utf-8') as log:
                server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1',
                    '--port',str(port),'--ssl-certfile',str(cert),'--ssl-keyfile',str(key)],
                    cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=flags)
                try:
                    with httpx.Client(base_url=base,verify=context,trust_env=False,timeout=2) as probe:
                        for _ in range(100):
                            if server.poll() is not None:raise RuntimeError('TLS server exited')
                            try:
                                if probe.get('/api/health').status_code==200:break
                            except httpx.HTTPError:pass
                            time.sleep(.1)
                        else:raise RuntimeError('TLS server did not become ready')
                        assert probe.get('/api/health',headers={'Host':'invalid.example'}).status_code==400
                        # An unaffiliated browser/client must not trust this certificate.
                        with httpx.Client(trust_env=False,timeout=2) as untrusted:
                            try:untrusted.get(base)
                            except httpx.ConnectError:pass
                            else:raise AssertionError('Untrusted certificate unexpectedly accepted')
                    with sync_playwright() as p:
                        browser=p.chromium.launch(executable_path=executable,headless=True,
                            args=['--ignore-certificate-errors-spki-list='+pin])
                        try:result=exercise(browser,base,password,output,work)|{'status':'passed'}
                        finally:browser.close()
                finally:stop_server(server)
        # Retain only useful synthetic records; the ephemeral TLS private key
        # never enters screenshots, reports, logs, or the repository.
    finally:
        (work/'private-key.pem').unlink(missing_ok=True)
        (output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
