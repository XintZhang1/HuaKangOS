"""Actual Chrome employee and 390px physical vehicle acceptance on synthetic data."""
import secrets
from datetime import date
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login,take_screenshot
API='/api/vehicle-operations'

def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screens=[];req=harness.checked_request
    def page(width=390):
        ctx=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(ctx);p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440)
    try:
        harness.login_page(admin,base,'admin',password)
        def typed(kind,v):return req(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':v},status=201)
        def visit(p,cid):
            p.goto(base+'/?visit='+secrets.token_hex(4)+'#vehicle-operation/'+str(cid));expect(p.locator('#main h1')).to_have_text(req(admin,API+'/orders/'+str(cid))['kind_label'],timeout=15000)
        def generic(p,cid):
            p.goto(base+'/?visit='+secrets.token_hex(4)+'#case/'+str(cid));expect(p.locator('[data-act=upload]')).to_be_visible(timeout=15000)
        def upload(p,name,category='evidence',source=None):
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category)
            if source:p.locator('#modal [name=source_file_id]').select_option(str(source))
            p.locator('#modal [name=file]').set_input_files({'name':name+'.txt','mimeType':'text/plain','buffer':('合成实车凭据：'+name).encode()});harness.save_modal(p)
            return req(p,'/api/flow/cases/'+p.url.split('/')[-1])['files'][-1]['id'] if '#case/' in p.url else None
        def file(cid,category='evidence',source=None):
            generic(admin,cid);upload(admin,'合成凭据'+secrets.token_hex(3),category,source)
            return max(req(admin,'/api/flow/cases/'+str(cid))['files'],key=lambda f:f['id'])['id']
        people={}
        for role in ['inventory','manager','service','finance']:
            secret=secrets.token_urlsafe(26);req(admin,'/api/users','POST',{'username':'vo-'+role,'display_name':'合成车辆'+role,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},status=201)
            p=page();employee_login(p,base,'vo-'+role,secret);people[role]=p
        inventory,manager,service,finance=[people[k] for k in ['inventory','manager','service','finance']]
        supplier=typed('suppliers',{'code':'VO-S','name':'合成整车供货方'})
        model=typed('vehicle_models',{'code':'VO-M','name':'合成车辆型号','brand':'虚构品牌','model_year':2026,'fuel_type':'electric','seats':5,'battery_wh':60000})
        w=typed('warehouses',{'code':'VO-W','name':'合成整车仓','warehouse_type':'vehicles'})
        a=typed('locations',{'code':'VO-A','name':'甲库位','warehouse_id':w['id']})['id'];b=typed('locations',{'code':'VO-B','name':'乙库位','warehouse_id':w['id']})['id']
        vin='LHGCM82633A123456'
        purchase=req(admin,'/api/vehicle-procurement/orders','POST',{'request_id':secrets.token_hex(16),'supplier_id':supplier['id'],'contracting_party':'虚构测试门店主体','reason':'有凭据的合成车辆采购','due_date':date.today().isoformat(),'lines':[{'model_id':model['id'],'color':'白','quantity':1}]},status=201)
        def pc(action,v):
            row=req(admin,'/api/vehicle-procurement/orders/'+str(purchase['id']));return req(admin,f'/api/vehicle-procurement/orders/{row["id"]}/actions/{action}','POST',{'request_id':secrets.token_hex(16),'version':row['version'],'values':v})
        purchase=pc('approve',{'prices':[{'line_id':purchase['lines'][0]['id'],'unit_cost_cents':10000001,'list_price_cents':12000000}],'evidence_id':file(purchase['id'],'invoice')})
        purchase=pc('ship',{'line_id':purchase['lines'][0]['id'],'vin':vin,'shipped_date':date.today().isoformat(),'expected_date':date.today().isoformat(),'evidence_id':file(purchase['id'])})
        purchase=pc('receive',{'shipment_id':purchase['shipments'][0]['id'],'vin':vin,'location_id':a,'evidence_id':file(purchase['id'])});vid=purchase['receipts'][0]['vehicle_id']
        def new(kind,original=None):
            harness.navigate(inventory,'vehicle-operations','整车库位与出退库');inventory.locator('[data-act=vo-new]').click();inventory.locator('#modal [name=kind]').select_option(kind)
            if original:inventory.locator('#modal [name=original_operation_id]').select_option(str(original))
            else:inventory.locator('#modal [name=vehicle_id]').select_option(str(vid))
            if kind!='other_out':inventory.locator('#modal [name=location_id]').select_option(str(b if kind=='local_move' else a))
            else:inventory.locator('#modal [name=recipient]').fill('合成内部转用部门')
            inventory.locator('#modal [name=reason]').fill('合成门店依实际安排办理实车');harness.save_modal(inventory)
            expect(inventory.locator('#main h1')).to_have_text({'local_move':'整车店内移库','other_out':'整车其他出库','other_return':'其他出库原车退回'}[kind]);return req(admin,API+'/orders')['items'][0]['id']
        def dialog(p,action):
            p.locator('[data-act=vo-action][data-key='+action+']').click();expect(p.locator('#modal')).to_be_visible();p.locator('#modal [name=reason]').fill('本人核对的合成实际业务凭据')
        def act(p,cid,action,values=None):
            visit(p,cid);upload(p,'合成实际动作'+action);dialog(p,action)
            for k,v in (values or {}).items():
                el=p.locator('#modal [name='+k+']')
                if el.evaluate('(e)=>e.tagName')=='SELECT':el.select_option(str(v))
                else:el.fill(str(v))
            harness.save_modal(p)
        move=new('local_move');act(manager,move,'approve');visit(inventory,move);upload(inventory,'现场实车交接');dialog(inventory,'dispatch');inventory.locator('#modal [name=vin]').fill('LHGCM82633A999999');inventory.locator('#modal button[type=submit]').click()
        expect(inventory.locator('#modal .formerror')).to_contain_text('现场VIN');harness.assert_fits_mobile(inventory);screens.append(take_screenshot(inventory,output,'01_vehicle_vin_refusal_mobile.png'))
        inventory.locator('#modal [name=vin]').fill(vin);harness.save_modal(inventory)
        assert not req(admin,'/api/flow/lookup/vehicle')['items'];act(inventory,move,'reject',{'vin':vin});act(inventory,move,'return_receive',{'vin':vin})
        assert req(admin,API+'/orders/'+str(move))['status']=='completed';screens.append(take_screenshot(inventory,output,'02_vehicle_local_return_mobile.png'))
        steps.append('真实库管申请、主管审批；错误现场VIN中文拒绝；实际发出后拒收并原位接回，期间不能配车')
        out=new('other_out');act(manager,out,'approve');act(inventory,out,'dispatch',{'vin':vin});back=new('other_return',out);act(manager,back,'approve');act(inventory,back,'receive',{'vin':vin})
        result=req(admin,API+'/orders/'+str(back));assert result['received_vehicle_id']!=vid and result['cost_cents']==10000001
        assert 'cost_cents' not in req(inventory,API+'/orders/'+str(back));visit(finance,back);harness.assert_fits_mobile(finance);screens.append(take_screenshot(finance,output,'03_vehicle_original_cost_return_mobile.png'))
        assert not finance.locator('[data-act=vo-action]').count();steps.append('其他实出与原车实退分别留据，新库存代次保留原成本；库管不读成本，财务只能查看')
        source=req(admin,'/api/flow/cases','POST',{'request_id':secrets.token_hex(16),'kind':'order','values':{'customer_name':'纯合成退车客户','model':'合成车辆型号','amount':'100.00','delivery_due':date.today().isoformat()}},status=201)
        def saleact(action,v=None):
            fresh=req(admin,'/api/flow/cases/'+str(source['id']));return req(admin,f'/api/flow/cases/{source["id"]}/actions/{action}','POST',{'request_id':secrets.token_hex(16),'version':fresh['version'],'values':v or {}})
        source=saleact('approve');source=saleact('allocate',{'vehicle_id':result['received_vehicle_id']})
        def document(kind):
            templates=req(admin,'/api/flow/master/templates')['items'];t=next(t for t in templates if t['kind']==kind)
            req(admin,'/api/flow/master/templates/'+str(t['id']),'PUT',{'version':t['version'],'values':{'title':t['title'],'clauses':t['clauses'],'approved':True}})
            return req(admin,'/api/flow/cases/'+str(source['id'])+'/documents','POST',{'kind':kind})['id']
        contract=document('contract');source=saleact('sign',{'evidence_id':file(source['id'],'signed_contract',contract)})
        account=req(admin,'/api/flow/master/accounts','POST',{'values':{'name':'合成车辆账户','account_type':'bank','active':True}},status=201)['id']
        source=saleact('receive',{'amount':'100.00','account_id':account,'reference':'纯合成收款','evidence_id':file(source['id'],'receipt')})
        source=saleact('inspect',{'outcome':'合格','result':'原车出库检查合格','evidence_id':file(source['id'],'inspection')})
        source=saleact('dispatch',{'evidence_id':file(source['id'])});handover=document('handover');source=saleact('deliver',{'evidence_id':file(source['id'],'signed_handover',handover)})
        fresh=req(admin,'/api/flow/cases/'+str(source['id']));after=req(admin,'/api/aftercare/orders','POST',{'request_id':secrets.token_hex(16),'source_case_id':source['id'],'source_version':fresh['version'],'scenario':'vehicle_return','reason':'虚构客户根据约定申请原车退回'},status=201)
        def afteract(action,v):
            current=req(admin,'/api/aftercare/orders/'+str(after['id']));return req(admin,f'/api/aftercare/orders/{after["id"]}/actions/{action}','POST',{'request_id':secrets.token_hex(16),'version':current['version'],'source_versions':{str(s['case_id']):s['version'] for s in current['sources']},'values':v})
        link=after['sources'][0];after=afteract('plan',{'reason':'完整核对纯合成原款及费用','lines':[{'source_id':link['id'],'credit_cents':10000,'returns':[{'kind':'cash','original_id':link['eligible_returns'][0]['entry_id'],'units':10000}]}]})
        after=afteract('approve',{'reason':'核对合成当前退车方案','evidence_id':file(after['id'],'authorization')})
        after=afteract('customer_confirm',{'evidence_id':file(after['id'],'authorization')});returned=after['vehicle_return']['operation_case_id']
        act(inventory,returned,'intake',{'vin':vin,'location_id':a});act(service,returned,'inspect',{'outcome':'fail','findings':'本次实际检查不合格，需整改复检'})
        visit(manager,returned);upload(manager,'本次主管判定');dialog(manager,'disposition')
        assert manager.locator('#modal [name=decision] option[value=release]').count()==0
        harness.assert_fits_mobile(manager);screens.append(take_screenshot(manager,output,'04_vehicle_failed_inspection_mobile.png'))
        manager.locator('#modal [name=decision]').select_option('rectify');harness.save_modal(manager)
        act(service,returned,'inspect',{'outcome':'pass','findings':'整改完成，本次重新检查合格'});act(manager,returned,'disposition',{'decision':'release'});act(inventory,returned,'release',{'vin':vin,'location_id':b})
        proof=req(admin,'/api/aftercare/orders/'+str(after['id']))['vehicle_return'];assert proof['accepted'] and proof['new_vehicle_id']!=result['received_vehicle_id']
        harness.assert_fits_mobile(inventory);screens.append(take_screenshot(inventory,output,'05_vehicle_customer_return_mobile.png'))
        steps.append('真实库管隔离收车、服务顾问检查不合格、主管要求整改；复检合格后再由主管判定和库管实车新代次入库，原交付记录保留')
        req(admin,'/api/stores','POST',{'code':'VO-BR-B','name':'合成车辆乙店'},status=201)
        assert harness.request(admin,API+'/orders/'+str(back),store='2')['status']==404
        assert harness.request(admin,API+'/orders',store='all')['status']==409
        inventory.reload();expect(inventory.locator('#main h1')).to_have_text('客户退车隔离验收');harness.assert_fits_mobile(inventory)
        steps.append('跨店和集团明细读取被服务端拒绝；刷新后仍保持本店及原单页面')
        assert not errors,errors
        return {'checks':len(steps),'steps':steps,'screenshots':screens,'javascript_errors':errors,'transport':'real Chrome HTTP/cookies/CSP','data':'isolated synthetic database; passwords randomized outside repository'}
    except Exception:
        for n,p in [('admin',admin),*list(locals().get('people',{}).items())]:
            p.screenshot(path=str(output/('failure_'+n+'.png')),full_page=True)
        raise
    finally:
        for c in contexts:c.close()

if __name__=='__main__':harness.exercise=exercise;harness.main()
