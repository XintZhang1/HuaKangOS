"""Deferred real-browser original vehicle loss/found acceptance.

Run only on the owner computer with the existing disposable browser harness.
No existing database/server argument is accepted. Starting stock is synthetic.
Compiling this script is NOT actual-browser acceptance.
"""
from pathlib import Path
import secrets
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import browser_huakangos as harness
from playwright.sync_api import expect

VIN='LHGCM82633A123456'


def prepare_database(env,work):
    assert work.name.startswith('huakangos-browser-db-') and env['DATABASE_URL']=='sqlite:///'+(work/'synthetic.sqlite').as_posix()
    code="""from app.db import SessionLocal,today
from app.models import Vehicle
with SessionLocal() as db:
    db.add(Vehicle(vin='LHGCM82633A123456',brand='浏览器测试品牌',model='浏览器测试车型',color='白',supplier='合成库存来源',purchase_cost_cents=10000001,list_price_cents=12000000,store_id=1,doc_no='SYNTHETIC-CAR',business_date=today(),approval_state='approved',created_by=1))
    db.commit()
"""
    done=subprocess.run([sys.executable,'-c',code],cwd=harness.ROOT,env=env,capture_output=True,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if done.returncode:raise RuntimeError('虚构整车库存夹具初始化失败：'+done.stderr)


def exercise(browser,base,password,output):
    steps=[];screenshots=[];errors=[]
    admin_context=browser.new_context(viewport={'width':1280,'height':900},locale='zh-CN')
    context=browser.new_context(viewport={'width':390,'height':844},locale='zh-CN')
    admin=admin_context.new_page();page=context.new_page();req=harness.checked_request
    for p in (admin,page):p.on('pageerror',lambda e:errors.append(str(e)))
    try:
        harness.login_page(admin,base,'admin',password)
        two=req(admin,'/api/stores','POST',{'code':'VEHICLE-B','name':'整车接收模拟门店'},status=201)['id']
        credentials={}
        for name,role,sid in [('car-out','inventory',1),('car-in','inventory',two),('car-out-manager','manager',1),('car-in-manager','manager',two),('car-finance','finance',1)]:
            secret=secrets.token_urlsafe(24);credentials[name]=secret
            req(admin,'/api/users','POST',{'username':name,'display_name':name,'password':secret,'role':role,'store_roles':[{'store_id':sid,'role':role}],'can_group_summary':False},status=201)
        wh=req(admin,'/api/masters/warehouses','POST',{'request_id':secrets.token_hex(16),'values':{'code':'CAR-W','name':'整车接收仓','warehouse_type':'vehicles','address':'合成试用地址','active':True}},store=two,status=201)
        loc=req(admin,'/api/masters/locations','POST',{'request_id':secrets.token_hex(16),'values':{'code':'CAR-L','name':'验收A位','warehouse_id':wh['id'],'active':True}},store=two,status=201)
        car=req(admin,'/api/flow/lookup/vehicle')['items'][0]
        def login(name):
            if page.locator('[data-act=logout]').count():page.locator('[data-act=logout]').click();expect(page.locator('.loginform')).to_be_visible()
            harness.login_page(page,base,name,credentials[name])
            if page.locator('#modal [name=current_password]').count():
                replacement=secrets.token_urlsafe(24);page.locator('#modal [name=current_password]').fill(credentials[name]);page.locator('#modal [name=new_password]').fill(replacement)
                harness.save_modal(page);credentials[name]=replacement;expect(page.locator('.loginform')).to_be_visible();harness.login_page(page,base,name,replacement)
            expect(page.locator('#main h1')).to_have_text('我的工作')
        login('car-out');harness.navigate(page,'vehicle-transfers','整车跨店调拨');page.locator('[data-act=vehicle-transfer-new]').click()
        page.locator('#modal [name=vehicle_id]').select_option(str(car['id']));page.locator('#modal [name=destination_store_id]').select_option(str(two))
        page.locator('#modal [name=reason]').fill('两店调剂合成整车库存');harness.assert_fits_mobile(page)
        screenshots.append(harness.take_screenshot(page,output,'01_vehicle_transfer_request.png'));harness.save_modal(page);expect(page.locator('#main h1')).to_have_text('整车调拨')
        row=req(page,'/api/vehicle-transfers')['items'][0];key=row['id'];assert req(page,'/api/flow/lookup/vehicle')['items']==[]
        steps.append('调出库管手机申请整车调拨；同车从可配库存中移除')
        def view(sid):
            harness.navigate(page,'vehicle-transfers/'+str(key),'整车调拨');return req(page,'/api/vehicle-transfers/'+str(key),store=sid)
        def action(name,fields=None):
            page.locator(f'[data-act=vehicle-transfer-action][data-key={name}]').click();page.locator('#modal [name=reason]').fill('本店实际核对确认')
            for key,value in (fields or {}).items():
                item=page.locator(f'#modal [name="{key}"]')
                if item.evaluate('(e)=>e.tagName')=='SELECT':item.select_option(str(value))
                else:item.fill(str(value))
            harness.assert_fits_mobile(page);harness.save_modal(page)
        login('car-out-manager');view(1);action('approve')
        login('car-in-manager');view(two);action('approve');steps.append('双方独立主管批准，未代替库管确认实际交接')
        def upload(sid):
            row=req(page,'/api/vehicle-transfers/'+str(key),store=sid);case=req(page,'/api/flow/cases/'+str(row['case_id']),store=sid)
            harness.navigate(page,'case/'+str(case['id']),case['title']);page.locator('[data-act=upload]').click()
            page.locator('#modal [name=file]').set_input_files({'name':'实车VIN交接.txt','mimeType':'text/plain','buffer':'模拟现场核对VIN与外观'.encode()})
            harness.save_modal(page);case=req(page,'/api/flow/cases/'+str(case['id']),store=sid);view(sid);return case['files'][0]['id']
        login('car-out');proof=upload(1)
        page.locator('[data-act=vehicle-transfer-action][data-key=dispatch]').click();page.locator('#modal [name=reason]').fill('错误VIN必须阻断')
        page.locator('#modal [name=evidence_id]').select_option(str(proof));page.locator('#modal [name=vin]').fill('LHGCM82633A999999');page.locator('#modal button[type=submit]').click()
        expect(page.locator('#modal .formerror')).to_contain_text('VIN');harness.assert_fits_mobile(page)
        screenshots.append(harness.take_screenshot(page,output,'02_vehicle_wrong_vin_blocked.png'))
        page.locator('#modal [name=vin]').fill(VIN);harness.save_modal(page)
        steps.append('现场VIN不匹配显示中文拒绝；更正核对后发出，车辆进入在途')
        in_transit=req(admin,'/api/flow/analytics',store='all');assert in_transit['metrics']['vehicle_in_transit_count']==1
        assert in_transit['metrics']['inventory_count']==0 and in_transit['metrics']['vehicle_in_transit_cents']==10000001
        # Business data uses the original workflow and actual DOM forms below;
        # no SQL status updates create the transport exception or its postings.
        login('car-out');proof=upload(1)
        page.locator('[data-act=vt-new]').click()
        page.locator('#modal [name=kind]').select_option('missing')
        page.locator('#modal [name=evidence_id]').select_option(str(proof))
        page.locator('#modal [name=reason]').fill('现场复核原车本段运输失联，启动双方核对')
        harness.save_modal(page)
        expect(page.locator('#main h1')).to_have_text('整车运输差异与原车找回')
        ex_id=req(page,'/api/vehicle-transfers/'+str(key))['active_exception_id']
        route='vehicle-transport-exceptions/'+str(ex_id)
        endpoint='/api/vehicle-transport-exceptions/'+str(ex_id)
        def original_proof(sid,category='evidence'):
            detail=req(page,endpoint,store=sid)
            case=req(page,'/api/flow/cases/'+str(detail['case_id']),store=sid)
            harness.navigate(page,'case/'+str(case['id']),case['title'])
            page.locator('[data-act=upload]').click()
            page.locator('#modal [name=category]').select_option(category)
            name='合成原车凭据-'+secrets.token_hex(6)+'.txt'
            page.locator('#modal [name=file]').set_input_files({'name':name,'mimeType':'text/plain','buffer':'本店本人核验的合成原事实，不是真实公司凭证'.encode()})
            harness.save_modal(page)
            fid=next(x['id'] for x in req(page,'/api/flow/cases/'+str(case['id']),store=sid)['files'] if x['name']==name)
            harness.navigate(page,route,'整车运输差异与原车找回')
            return fid
        def exception_action(name,sid,fields=None,financial=False,physical=False):
            fid=original_proof(sid,'receipt' if financial else 'evidence')
            page.locator('[data-act=vt-action][data-key='+name+']').click()
            page.locator('#modal [name=evidence_id]').select_option(str(fid))
            page.locator('#modal [name=reason]').fill('本人明确核对原单与合成原凭据，记录本步已发生事实')
            if physical:
                expect(page.locator('#modal [name=vin]')).to_have_value('')
                page.locator('#modal [name=vin]').fill(VIN)
            for field,value in (fields or {}).items():
                widget=page.locator('#modal [name='+field+']')
                if widget.evaluate('(e)=>e.tagName')=='SELECT':widget.select_option(str(value))
                else:widget.fill(str(value))
            confirmed=page.locator('#modal [name=confirmed]')
            if confirmed.count():
                expect(confirmed).not_to_be_checked();confirmed.check()
            harness.assert_fits_mobile(page);harness.save_modal(page)
            expect(page.locator('#main h1')).to_have_text('整车运输差异与原车找回')
        assert req(page,'/api/vehicle-transfers/'+str(key))['actions']==[]
        exception_action('observe',1,{'kind':'dispatch_verified'},physical=True)
        login('car-in');exception_action('observe',two,{'kind':'not_located'},physical=True)
        assert req(page,endpoint,store=two)['can_money'] is False
        screenshots.append(harness.take_screenshot(page,output,'04_transport_observation_no_money_390px.png'))
        login('car-finance');exception_action('plan_loss',1,{'loss_method':'missing','source_amount':'60000.00','destination_amount':'40000.01'},financial=True)
        login('car-out-manager');exception_action('approve',1,financial=True)
        login('car-in-manager');exception_action('approve',two,financial=True)
        login('car-finance');exception_action('post_loss',1,financial=True)
        assert req(page,endpoint)['loss']['value_cents']==10000001
        report=req(admin,'/api/flow/analytics',store='all')
        assert report['metrics']['inventory_count']==report['metrics']['vehicle_in_transit_count']==0
        assert report['metrics']['cash_in_cents']==report['metrics']['cash_out_cents']==0
        steps.append('两店本人记录原VIN观察，财务提原成本承担，另一主管各自批准后确认损失；没有再次出库或现金')
        screenshots.append(harness.take_screenshot(page,output,'05_transport_original_loss_390px.png'))
        login('car-in');exception_action('observe_found',two,physical=True)
        observation=req(page,endpoint,store=two)['observations'][-1]['id']
        login('car-finance');exception_action('plan_found',1,{'found_observation_id':observation},financial=True)
        login('car-out-manager');exception_action('approve',1,financial=True)
        login('car-in-manager');exception_action('approve',two,financial=True)
        assert req(admin,'/api/flow/analytics',store='all')['metrics']['inventory_count']==0
        login('car-in');exception_action('found_receive',two,{'location_id':loc['id']},physical=True)
        own=req(page,'/api/flow/lookup/vehicle',store=two)['items']
        assert len(own)==1 and own[0]['id']!=car['id']
        report=req(admin,'/api/flow/analytics',store='all')
        assert report['metrics']['inventory_count']==1 and report['metrics']['inventory_cost_cents']==10000001
        assert report['metrics']['cash_in_cents']==report['metrics']['cash_out_cents']==0
        screenshots.append(harness.take_screenshot(page,output,'06_transport_found_real_receipt_390px.png'))
        login('car-finance');harness.navigate(page,'vehicle-transport-report','原车运输与找回核对')
        harness.assert_fits_mobile(page)
        screenshots.append(harness.take_screenshot(page,output,'07_transport_same_source_finance_390px.png'))
        steps.append('后来找到需新观察、两店新批准和库管手工VIN/明确确认实际验收，批准本身仍零库存；新代次恢复原成本')
        assert not errors,errors
        return {'mode':'real Chromium employee HTTP','passed':len(steps),'steps':steps,'javascript_errors':errors,'screenshots':screenshots,
            'limitations':['起始整车为临时库合成夹具；不验证采购/期初入口','此脚本未覆盖赔付现金和实际清算的全部页面；对应后端专项与本机人工验收分别保留','本地HTTP与结构校验，不代替生产HTTPS、查毒或真实实物验收']}
    except Exception:harness.take_screenshot(page,output,'failure.png');raise
    finally:context.close();admin_context.close()


if __name__=='__main__':
    harness.prepare_database=prepare_database;harness.exercise=exercise;harness.main()
