"""Native delivery-material checks; all runtime data stays in a new external mirror.

Requires root dependencies plus playwright==1.56.0. API preparations are recorded
separately from native browser actions; no HTTP response or model is mocked.
"""
import argparse
from datetime import date
import hashlib
import io
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
import uuid

import httpx
from PIL import Image
from playwright.sync_api import sync_playwright, expect
from reportlab.pdfgen.canvas import Canvas

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'record_pricing'))
from browser_check import inventory, SERVER
from synthetic import VEHICLE_ROW, vehicle_xlsx

BASE = '/api/business-records'
SEED = '''
import json, os
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from app.cli import initialize
initialize(SimpleNamespace(demo=False,admin_user=os.environ['SYNTH_ADMIN']))
from app.db import SessionLocal, utcnow
from app.models import User, Store, UserStore
from app.business_records_models import SalesContract
from app.security import hash_password
credentials=json.loads(Path(os.environ['SYNTH_CREDENTIALS']).read_text())
with SessionLocal() as db:
    db.get(Store,1).brand='合成品牌';db.get(Store,1).name='合成交车门店一'
    db.add(Store(id=2,code='SYNTH2',name='合成交车门店二',brand='合成品牌'))
    people={}
    for name,values in credentials.items():
        if name=='admin': continue
        role='finance' if name=='other_finance' else name
        user=User(username=values['username'],display_name='合成'+name,role=role,password_hash=hash_password(values['password']),must_change_password=False)
        db.add(user);db.flush();people[name]=user.id
        db.add(UserStore(user_id=user.id,store_id=2 if name=='other_finance' else 1,role=role))
    # Historical fixture only; no claim that this is a native approval result.
    legacy=SalesContract(number='SYNTHETIC-HISTORICAL',store_id=1,salesperson_id=people['sales'],created_by=people['sales'],customer_name='合成历史客户',brand='合成品牌',model='合成历史车型',vin='SYNTHETIC-LEGACY',contract_date=date(2026,10,12),sale_price_cents=11000000,status='approved',workflow_version='legacy-v2',expected_amount_cents=11000000,cost_cents=10000000,profit_cents=1000000,gift_cost_cents=0,priced_by=people['general_manager'],approved_by=people['general_manager'],approved_at=utcnow(),approved_snapshot={'synthetic_historical_fixture':True})
    db.add(legacy);db.commit()
    Path(os.environ['SYNTH_IDS']).write_text(json.dumps({'legacy_id':legacy.id}))
'''


def command(**values):
    return {'request_id': uuid.uuid4().hex, **values}


def png(color='white'):
    output=io.BytesIO();Image.new('RGB',(80,60),color).save(output,format='PNG');return output.getvalue()


def pdf():
    output=io.BytesIO();canvas=Canvas(output,invariant=1);canvas.drawString(50,750,'SYNTHETIC GIFT DOCUMENT - TEST ONLY');canvas.save();return output.getvalue()


class API:
    def __init__(self,origin,credentials,report):
        self.origin,self.credentials,self.report,self.clients,self.users=origin,credentials,report,{},{}

    def client(self,role):
        if role not in self.clients:
            client=httpx.Client(base_url=self.origin,headers={'X-App-Request':'1'},timeout=30,trust_env=False)
            response=client.post('/api/auth/login',json=self.credentials[role]);assert response.status_code==200,response.text
            self.users[role]=response.json()
            client.headers.update({'X-CSRF-Token':client.cookies['dealer_csrf'],'X-Store-ID':'2' if role=='other_finance' else '1'})
            self.clients[role]=client
        return self.clients[role]

    def call(self,role,method,path,status=200,**kwargs):
        response=self.client(role).request(method,BASE+path,**kwargs)
        self.report['api_preparations_and_checks'].append({'role':role,'method':method,'path':path,'status':response.status_code})
        assert response.status_code==status,response.text
        return response.json()

    def contract(self,name,approved=True):
        catalog=self.call('sales','GET','/pricing/catalog')
        body=command(customer_name=name,customer_phone='13800009999',brand='合成品牌',model='合成系列 合成配置',vin='SYNTH-'+uuid.uuid4().hex[:12],salesperson_id=self.users['sales']['id'],contract_date=date(2026,10,12).isoformat(),sale_price_cents=11000000,vehicle_price_id=catalog['vehicles'][0]['id'],gift_items=[],form_data={'seller_name':'合成卖方','exterior_color':'白','interior_color':'黑','deposit':'2000'},submission_data={'payment_method':'全款'})
        row=self.call('sales','POST','/contracts',201,json=body)
        if approved:
            row=self.call('manager','POST',f'/contracts/{row["id"]}/manager-approve',json=command(version=row['version']))
            row=self.call('general_manager','POST',f'/contracts/{row["id"]}/approve',json=command(version=row['version']))
            assert row['status']=='approved'
        return row

    def prepare(self):
        self.call('admin','PUT','/store-profile',json=command(version=0,sellers=[{'name':'合成卖方','address':'合成地址'}]))
        uploaded=self.call('admin','POST','/pricing/uploads',201,data=command(kind='vehicle'),files={'file':('synthetic.xlsx',vehicle_xlsx())})
        catalog=self.call('admin','GET','/pricing/catalog')
        self.call('admin','POST','/pricing/vehicle/import',201,json=command(version=catalog['version'],brand_version=catalog['brand_version'],brand=catalog['brand'],file_id=uploaded['id'],policy_confirmed=True,rows=[VEHICLE_ROW]))
        return self.contract('合成交车客户'),self.contract('合成待批客户',approved=False)


def run(source,browser,output):
    source=source.resolve();output=output.resolve()
    if output.exists() or output.is_relative_to(source):raise ValueError('Use a new output directory outside repository')
    mirror,runtime,evidence,scripts=(output/name for name in ('source','runtime','evidence','scripts'))
    for directory in (runtime,evidence,scripts):directory.mkdir(parents=True)
    before=inventory(source)
    for relative in before:
        target=mirror/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/relative,target)
    if inventory(mirror)!=before or inventory(source)!=before:raise RuntimeError('Source changed during snapshot')
    (output/'source-manifest.json').write_text(json.dumps(before,indent=2))
    script_paths=['record_delivery/browser_check.py','record_pricing/browser_check.py','record_pricing/synthetic.py']
    for relative in script_paths:
        target=scripts/'tests'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(HERE.parent/relative,target)
    credentials={role:{'username':role+'_'+secrets.token_hex(4),'password':secrets.token_urlsafe(24)} for role in ('admin','manager','general_manager','finance','sales','other_finance')}
    credentials_path=runtime/'credentials.json';credentials_path.write_text(json.dumps(credentials));credentials_path.chmod(0o600)
    config=runtime/'disabled-model.json';config.write_text(json.dumps({'enabled':False,'synthetic':True}))
    env={key:value for key,value in os.environ.items() if key in {'PATH','HOME','LANG','LC_ALL','TMPDIR'}}
    env.update({'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(mirror),'DATABASE_URL':'sqlite:///'+str(runtime/'synthetic.sqlite'),'APP_ENV':'test','SCHEDULER_ENABLED':'false','SCHEDULER_MODE':'off','ALLOW_AI_EXTERNAL':'false','FILE_SCAN_MODE':'structure_only','FILE_STORAGE_MODE':'blob','COOKIE_SECURE':'false','BUSINESS_ASSISTANT_CONFIG':str(config),'SYNTH_NETWORK_LEDGER':str(evidence/'network.json'),'ALLOWED_HOSTS':'127.0.0.1,localhost','SYNTH_ADMIN':credentials['admin']['username'],'SYNTH_CREDENTIALS':str(credentials_path),'SYNTH_IDS':str(runtime/'ids.json'),'HUAKANGOS_INITIAL_PASSWORD':credentials['admin']['password']})
    with (evidence/'initialize.log').open('w') as log:subprocess.run([sys.executable,'-c',SEED],cwd=mirror,env=env,stdout=log,stderr=log,check=True)
    with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    env['SYNTH_PORT']=str(port);origin='http://127.0.0.1:'+str(port)
    server_log=(evidence/'server.log').open('w');server=subprocess.Popen([sys.executable,'-c',SERVER],cwd=mirror,env=env,stdout=server_log,stderr=server_log)
    report={'scope':'stamped-gift-document-native','source_fingerprint':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),'script_fingerprints':{name:hashlib.sha256((scripts/'tests'/name).read_bytes()).hexdigest() for name in script_paths},'passed':False,'checks':[],'api_preparations_and_checks':[],'responses':[],'page_errors':[],'external_requests':[],'limitations':['User Library screenshot unavailable; no assumptions about its contract state.','Historical legacy row is an explicitly seeded synthetic fixture.','API setup is not claimed as native UI approval coverage.','No real model or production access.']}
    def passed(name):report['checks'].append(name);print('PASS '+name,flush=True)
    api=API(origin,credentials,report)
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(120):
            if server.poll() is not None:raise RuntimeError('Synthetic server exited')
            try:
                with opener.open(origin+'/',timeout=1):break
            except OSError:time.sleep(.25)
        else:raise RuntimeError('Synthetic server unavailable')
        main,pending=api.prepare();ident=main['id'];route='records-sales/'+str(ident)
        legacy=json.loads((runtime/'ids.json').read_text())['legacy_id']
        failure=api.call('finance','POST',f'/contracts/{ident}/delivery-confirm',409,json=command(version=main['version'],invoice_version=1));assert '发票' in failure['detail']
        with sync_playwright() as playwright:
            chromium=playwright.chromium.launch(executable_path=str(browser),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
            context=chromium.new_context(viewport={'width':1440,'height':1000},locale='zh-CN',accept_downloads=True)
            page=context.new_page();page.set_default_timeout(10000)
            page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
            page.on('request',lambda request:report['external_requests'].append(request.url) if not request.url.startswith(origin) else None)
            page.on('response',lambda response:report['responses'].append({'path':response.url.removeprefix(origin),'status':response.status}) if '/api/business-records/' in response.url else None)
            def login(role,path=route):
                context.clear_cookies();page.goto('about:blank');page.goto(origin+'/#'+path)
                page.locator('[name=username]').fill(credentials[role]['username']);page.locator('[name=password]').fill(credentials[role]['password']);page.locator('button[type=submit]').click();expect(page.locator('[name=username]')).not_to_be_visible()
            def navigate(path):page.goto(origin+'/#'+path)
            def card():return page.locator('[data-record-invoice-section]')
            def open_gift():card().locator('[data-br-flow=gift-upload]').click();expect(page.locator('#modal[open] input[type=file]')).to_be_visible()
            def choose(name,content):page.locator('#modal input[type=file]').set_input_files({'name':name,'mimeType':'application/octet-stream','buffer':content})
            def submit():page.locator('#modal button[type=submit]').click()
            def close():page.locator('#modal .modalhead [data-act=close]').click()
            def shot(name):page.screenshot(path=str(evidence/(name+'.png')),full_page=True)
            try:
                login('finance','records-finance')
                link=page.locator('a[href="#'+route+'"]');expect(link).to_have_text('查看 / 上传交车材料');link.click()
                expect(card().locator('[data-br-flow=gift-upload]')).to_be_visible();expect(card()).to_contain_text('待上传')
                expect(page.locator('[data-br-flow=delivery-confirm]')).to_have_count(0)
                card().scroll_into_view_if_needed();shot('desktop-delivery-entry')
                card().screenshot(path=str(evidence/'desktop-materials-card.png'))
                passed('finance list links to invoice-adjacent stamped gift upload on approved v210 contract')
                # The original invoice UI uploads a real synthetic PNG, then falls back to manual confirmation.
                card().locator('[data-record-invoice=upload]').click();choose('synthetic-invoice.png',png('blue'));submit()
                expect(page.locator('#modal h2')).to_have_text('收银核对发票')
                expect(page.locator('#modal .notice')).to_contain_text('尚未连接DeepSeek')
                page.locator('#modal [name=invoice_number]').fill('SYNTHETIC-INVOICE-001');page.locator('#modal [name=issued_on]').fill('2026-10-12');page.locator('#modal [name=total_amount]').fill('110000');submit()
                expect(page.locator('#modal')).not_to_be_visible();expect(card()).to_contain_text('发票已核实')
                current=api.call('finance','GET',f'/contracts/{ident}')
                failure=api.call('finance','POST',f'/contracts/{ident}/delivery-confirm',409,json=command(version=current['version'],invoice_version=current['delivery_state']['invoice_version']));assert '盖章赠品单' in failure['detail']
                expect(page.locator('[data-br-flow=delivery-confirm]')).to_have_count(0)
                passed('actual invoice UI saves and confirms; missing stamped gift blocks delivery in UI and backend')
                open_gift();expect(page.locator('#modal')).to_contain_text('10')
                choose('invalid.txt',b'synthetic invalid file');submit();expect(page.locator('#modal .formerror')).to_contain_text('PDF')
                choose('empty.png',b'');submit();expect(page.locator('#modal .formerror')).not_to_be_empty()
                choose('broken.png',b'not a png');submit();expect(page.locator('#modal .formerror')).to_contain_text('图片损坏')
                assert page.locator('#modal input[type=file]').input_value().endswith('broken.png');shot('invalid-upload-feedback')
                passed('invalid extension, empty file and corrupt PNG show failure and retain the form')
                choose('synthetic-stamped-gift.png',png());submit();expect(page.locator('#modal')).not_to_be_visible()
                expect(card()).to_contain_text('synthetic-stamped-gift.png');page.reload();expect(card()).to_contain_text('synthetic-stamped-gift.png')
                current=api.call('finance','GET',f'/contracts/{ident}');first=current['delivery_state']['gift_document'];assert first['sha256']==hashlib.sha256(png()).hexdigest()
                with page.expect_download() as downloaded:page.locator('[data-br-flow=gift-download]').click()
                assert Path(downloaded.value.path()).read_bytes()==png()
                expect(page.locator('[data-br-flow=delivery-confirm]')).to_be_visible()
                passed('native PNG upload persists, refreshes, downloads exact bytes and enables delivery')
                open_gift();choose('synthetic-stamped-correction.pdf',pdf());submit();expect(page.locator('#modal')).not_to_be_visible();expect(card()).to_contain_text('synthetic-stamped-correction.pdf')
                old=api.client('finance').get(BASE+f'/contracts/{ident}/gift-document/files/{first["id"]}/download');assert old.status_code==200 and old.content==png()
                page.set_viewport_size({'width':390,'height':844});card().scroll_into_view_if_needed();shot('mobile-delivery-materials');card().screenshot(path=str(evidence/'mobile-materials-card.png'));page.set_viewport_size({'width':1440,'height':1000})
                passed('native PDF correction is current while previous original remains downloadable')
                # Pause only request transport; every request continues unchanged to the real server.
                for action in ('switch_contract','other_modal'):
                    page.reload();expect(card()).to_contain_text('发票已核实')
                    held=[];pattern='**/api/business-records/contracts/*/gift-document'
                    def hold(request_route):held.append(request_route)
                    page.route(pattern,hold);open_gift();choose('synthetic-'+action+'.png',png('green'));submit()
                    expect(page.locator('#modal form')).to_have_attribute('data-submitting','true')
                    assert len(held)==1
                    if action=='switch_contract':
                        navigate('records-sales/'+str(pending['id']));expect(page.locator('h1')).to_contain_text('销售合同');expect(page.locator('#main')).to_contain_text('合成待批客户')
                    else:
                        close();card().locator('[data-record-invoice=upload]').click();expect(page.locator('#modal h2')).to_have_text('上传合同发票')
                    with page.expect_response(lambda response:response.url.endswith(f'/contracts/{ident}/gift-document') and response.request.method=='POST') as delivered:held[0].continue_()
                    assert delivered.value.status==200;delivered.value.body();page.unroute(pattern,hold)
                    # A real read verifies completion before inspecting the current native page.
                    updated=api.call('finance','GET',f'/contracts/{ident}');assert updated['delivery_state']['gift_document']['filename']=='synthetic-'+action+'.png'
                    if action=='switch_contract':
                        expect(page.locator('#main')).to_contain_text('合成待批客户');expect(page.locator('[data-br-flow=gift-upload]')).to_have_count(0);navigate(route);expect(card()).to_be_visible()
                    else:expect(page.locator('#modal h2')).to_have_text('上传合同发票');close()
                passed('unchanged real uploads finishing after contract switch or another modal preserve current page/window')
                page.reload();expect(card()).to_contain_text('synthetic-other_modal.png')
                # Competing actual server write makes the reviewed version stale.
                open_gift();choose('synthetic-stale.png',png())
                current=api.call('finance','GET',f'/contracts/{ident}')
                replacement=api.call('finance','POST',f'/contracts/{ident}/gift-document',data=command(version=current['version']),files={'file':('synthetic-concurrent.png',png('red'))})
                submit();expect(page.locator('#modal .formerror')).to_contain_text('记录已更新');close();page.reload();expect(card()).to_contain_text('synthetic-concurrent.png')
                passed('stale upload fails visibly without replacing the concurrent saved document')
                page.locator('[data-br-flow=delivery-confirm]').click();page.locator('#modal [name=note]').fill('合成财务人工确认');submit();expect(page.locator('#modal')).not_to_be_visible()
                expect(page.locator('#main')).to_contain_text('财务已确认交车')
                delivered=api.call('finance','GET',f'/contracts/{ident}')['delivery_state'];assert delivered['materials_ready'] and delivered['delivery']['gift_document_id']==replacement['gift_document']['id']
                card().scroll_into_view_if_needed();shot('desktop-saved-delivery-materials')
                passed('native financial delivery confirmation binds verified invoice and current gift document')
                navigate('records-sales/'+str(pending['id']));expect(page.locator('#main')).to_contain_text('合成待批客户');expect(page.locator('[data-br-flow=gift-upload]')).to_have_count(0)
                navigate('records-sales/'+str(legacy));expect(page.locator('#main')).to_contain_text('合成历史客户');expect(page.locator('[data-record-invoice=upload]')).to_be_visible();expect(page.locator('[data-br-flow=gift-upload]')).to_have_count(0)
                passed('pending and historical workflows do not expose new stamped gift mutation')
                login('sales');expect(page.locator('#main')).to_contain_text('合成交车客户');expect(page.locator('[data-br-flow=gift-upload]')).to_have_count(0)
                response=api.call('sales','POST',f'/contracts/{ident}/gift-document',403,data=command(version=delivered['contract_version'] if 'contract_version' in delivered else 1),files={'file':('synthetic.png',png())});assert response['detail']
                login('other_finance');expect(page.locator('#main .notice.error')).to_have_text('合同不存在或不可访问')
                api.call('other_finance','POST',f'/contracts/{ident}/gift-document',404,data=command(version=1),files={'file':('synthetic.png',png())})
                passed('sales cannot upload and same-brand other-store finance cannot view or upload this contract')
                assert not report['page_errors'],report['page_errors'];assert not report['external_requests'],report['external_requests']
                unexpected=[row for row in report['responses'] if row['status']>=500 and not row['path'].endswith('/invoice/recognize')];assert not unexpected,unexpected
                network=json.loads((evidence/'network.json').read_text());assert not network['blocked_external_attempts'];report.update(network)
                report['transport_pause']='Two browser requests paused and continued unchanged; no fulfill, mocks or body/header changes.'
                passed('no JavaScript errors, unexpected 5xx, external requests or real model calls')
                report['passed']=True
            except Exception:
                page.screenshot(path=str(evidence/'failure.png'),full_page=True)
                raise
            finally:context.close();chromium.close()
    except Exception as error:report['error']=str(error);raise
    finally:
        for client in api.clients.values():client.close()
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
        server_log.close();report['server_exit_code']=server.returncode;report['graceful_shutdown']=server.returncode in (0,-15) and 'Application shutdown complete.' in (evidence/'server.log').read_text()
        if not report['graceful_shutdown']:report['passed']=False
        (evidence/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print('Evidence: '+str(evidence),flush=True)
        if report.get('error') is None and not report['passed']:
            raise RuntimeError('Browser verification cleanup failed; inspect report.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,default=HERE.parents[1]);parser.add_argument('--browser',type=Path,required=True);parser.add_argument('--output',type=Path,default=Path(tempfile.gettempdir())/('hkos-delivery-browser-'+secrets.token_hex(5)));args=parser.parse_args();run(args.source,args.browser,args.output)
