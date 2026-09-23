"""Real 390px employee upload/download and a separately restored HTTP instance."""
from pathlib import Path
from contextlib import closing
import hashlib,json,os,secrets,socket,sqlite3,subprocess,sys,time
from datetime import date
import httpx
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request,login_page,save_modal,take_screenshot,assert_fits_mobile

RUNTIME={}


def prepare(env,work):
    env['FILE_STORAGE_MODE']='private_local';env['PRIVATE_FILE_ROOT']=str(work/'private-objects')
    RUNTIME.update(env=env,work=work)


def exercise(browser,base,password,output):
    contexts=[];errors=[];screenshots=[];steps=[];restored_server=None
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN',accept_downloads=True)
        contexts.append(context);p=context.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440);employee=page();work=RUNTIME['work'];flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    try:
        login_page(admin,base,'admin',password)
        secret=secrets.token_urlsafe(24)
        checked_request(admin,'/api/users','POST',{'username':'private-sales','display_name':'私有附件验收销售','role':'sales','password':secret,'store_roles':[{'store_id':1,'role':'sales'}]},status=201)
        login_page(employee,base,'private-sales',secret);employee.locator('#modal [name=current_password]').fill(secret)
        actual=secrets.token_urlsafe(24);employee.locator('#modal [name=new_password]').fill(actual);save_modal(employee);login_page(employee,base,'private-sales',actual)
        row=checked_request(employee,'/api/flow/cases','POST',{'request_id':secrets.token_hex(16),'kind':'order',
            'values':{'customer_name':'私有附件合成客户','customer_phone':'13900006401','model':'合成恢复车型','amount':'123.45','delivery_due':date.today().isoformat()}},status=201)
        def visit(p,url):
            p.goto(url+'/?visit='+secrets.token_hex(6)+'#case/'+str(row['id']));expect(p.locator('#main h1')).to_have_text(row['title'])
        visit(employee,base);employee.locator('[data-act=upload]').click()
        employee.locator('#modal [name=category]').select_option('evidence')
        payload='私有目录合成原凭据；恢复后必须保持同一原字节。'.encode()
        employee.locator('#modal [name=file]').set_input_files({'name':'私有恢复合成凭据.txt','mimeType':'text/plain','buffer':payload});save_modal(employee)
        expect(employee.locator('#main')).to_contain_text('私有恢复合成凭据.txt')
        detail=checked_request(employee,'/api/flow/cases/'+str(row['id']));file=next(f for f in detail['files'] if f['name']=='私有恢复合成凭据.txt')
        def download(p,target):
            with p.expect_download() as item:p.locator('[data-act=downloadfile][data-id="'+str(file['id'])+'"]').click()
            saved=work/target;item.value.save_as(saved);assert saved.read_bytes()==payload
        download(employee,'original-download.txt');employee.evaluate('window.scrollTo(0,0)');assert_fits_mobile(employee)
        screenshots.append(take_screenshot(employee,output,'01_private_employee_upload_mobile.png'))
        with closing(sqlite3.connect(work/'synthetic.sqlite')) as db:
            ref=db.execute('SELECT object_key,sha256,size FROM private_file_objects WHERE file_id=?',(file['id'],)).fetchone()
            assert ref and ref[1]==hashlib.sha256(payload).hexdigest() and ref[2]==len(payload)
            assert db.execute('SELECT length(content) FROM flow_files WHERE id=?',(file['id'],)).fetchone()[0]==0
        assert str(work) not in json.dumps(detail,ensure_ascii=False)
        steps.append('销售在真实手机页上传和下载；数据库只存同店不可变对象引用，API 不暴露私有路径，下载字节一致')
        # The actual maintenance CLI is scoped only to this harness's new DB;
        # no credentials are put in command arguments or output.
        for args in [('backup','--output',str(work/'bundle')),('verify-backup',str(work/'bundle')),
                     ('restore-backup',str(work/'bundle'),'--output',str(work/'restored')),('files-audit',)]:
            result=subprocess.run([sys.executable,'-m','app.cli',*args],cwd=harness.ROOT,env=RUNTIME['env'],capture_output=True,text=True,encoding='utf-8',creationflags=flags)
            if result.returncode:raise RuntimeError('合成成套备份/恢复 CLI 失败：'+result.stderr)
            if args[0]=='restore-backup':assert json.loads(result.stdout)['verified_private_objects']>=2
            if args[0]=='files-audit':assert json.loads(result.stdout)['orphans']==[]
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        restored_base='http://127.0.0.1:'+str(port)
        env={**RUNTIME['env'],'DATABASE_URL':'sqlite:///'+(work/'restored'/'database.sqlite').as_posix(),'PRIVATE_FILE_ROOT':str(work/'restored'/'object_store')}
        with (work/'restored-server.log').open('w',encoding='utf-8') as log:
            restored_server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=harness.ROOT,env=env,stdout=log,stderr=log,creationflags=flags)
            with httpx.Client(base_url=restored_base,timeout=2,trust_env=False) as probe:
                for _ in range(120):
                    if restored_server.poll() is not None:raise RuntimeError('恢复实例未能启动')
                    try:
                        if probe.get('/api/health').status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.1)
                else:raise RuntimeError('恢复实例未就绪')
            restored=page();login_page(restored,restored_base,'private-sales',actual);visit(restored,restored_base)
            assert checked_request(restored,'/api/flow/cases/'+str(row['id']))['number']==row['number']
            download(restored,'restored-download.txt');restored.evaluate('window.scrollTo(0,0)');assert_fits_mobile(restored)
            screenshots.append(take_screenshot(restored,output,'02_private_restored_download_mobile.png'))
            steps.append('从成套备份恢复到新数据库和新对象根，第二个真实 HTTP 服务用同一销售账号重新登录、查原单并下载同字节')
            # Simulate disk damage only inside the synthetic restored directory.
            damaged=work/'restored'/'object_store'/ref[0];damaged.write_bytes(b'synthetic-damaged')
            current=checked_request(restored,'/api/flow/files/'+str(file['id'])+'/security')
            rescanned=checked_request(restored,'/api/flow/files/'+str(file['id'])+'/scan','POST',{'request_id':secrets.token_hex(16),'version':current['security']['version']})
            assert rescanned['security']['state']=='rejected'
            visit(restored,restored_base);expect(restored.locator('[data-act=downloadfile][data-id="'+str(file['id'])+'"]').first).to_be_disabled()
            expect(restored.locator('#main')).to_contain_text('已隔离');assert_fits_mobile(restored)
            screenshots.append(take_screenshot(restored,output,'03_private_damaged_object_quarantined_mobile.png'))
            response=restored.evaluate('''async id=>{const r=await fetch('/api/flow/files/'+id,{headers:{'X-Store-ID':'1'}});return {status:r.status,body:await r.json()}}''',file['id'])
            assert response['status']==409 and '附件' in response['body']['detail']
            steps.append('合成对象受损后重扫追加拒绝记录，手机显示隔离且下载按钮禁用，直接 HTTP 请求同样拒绝')
        assert not errors,errors
        return {'mode':'real-http-chrome','viewport':390,'passed':steps,'javascript_errors':errors,'screenshots':screenshots,
            'limitations':['本机私有目录和结构校验合成验证，不是 S3、真实 ClamAV 或生产 HTTPS/ACL 验收']}
    finally:
        for context in contexts:context.close()
        if restored_server and restored_server.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(restored_server.pid),'/T','/F'],capture_output=True,creationflags=flags)
            else:restored_server.terminate()
            restored_server.wait(timeout=10)


if __name__=='__main__':
    harness.prepare_database=prepare;harness.exercise=exercise;harness.main()
