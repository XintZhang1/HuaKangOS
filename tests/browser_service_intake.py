"""Five actual employee Chrome sessions: arrival, v4 stock/cash and internal rework."""
import secrets
from datetime import datetime,timedelta
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request,request,login_page,navigate,save_modal,take_screenshot,assert_fits_mobile

def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screenshots=[]
    def page(width=390):
        c=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(c);p=c.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440)
    try:
        login_page(admin,base,'admin',password)
        def typed(kind,values):return checked_request(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':values},status=201)
        def master(kind,values):return checked_request(admin,'/api/flow/master/'+kind,'POST',{'values':values},status=201)
        def post(path,values):return checked_request(admin,'/api/service-intake'+path,'POST',{'request_id':secrets.token_hex(16),**values},status=201)
        customer=master('customers',{'name':'合成接待客户','phone':'13900008222','contact_allowed':True,'note':''})
        vehicle=checked_request(admin,'/api/customer-service/vehicles','POST',{'request_id':secrets.token_hex(16),'values':{'customer_id':customer['id'],'vin':'LFV2A21K9J1234567','plate':'合成接A123','model_name':'合成车型','source_reference':'合成实际登记凭据','confirmed':True}},status=201)['vehicle']
        item=master('items',{'sku':'INTAKE-PART','name':'本次返修配件','unit':'件','reorder':'0','active':True})
        work=typed('work_items',{'code':'INTAKE-WORK','name':'现场维修服务','billing_unit':'job','standard_fee_cents':10000})
        wash=typed('work_items',{'code':'INTAKE-WASH','name':'车身外观清洗','billing_unit':'job','standard_fee_cents':3000})
        account=master('accounts',{'name':'合成接待收款账户','account_type':'bank','active':True})
        supplier=typed('suppliers',{'code':'INTAKE-SUPPLIER','name':'合成接待配件供货商'})
        purchase=checked_request(admin,'/api/procurement/orders','POST',{'request_id':secrets.token_hex(16),'supplier_id':supplier['id'],'reason':'合成接待验收库存','lines':[{'item_id':item['id'],'quantity_milli':5000,'unit_cost_cents':123}]},status=201)
        def upload_api(case_id,label):
            result=admin.evaluate('''async({id,label})=>{const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];const fd=new FormData();fd.append('category','evidence');fd.append('file',new Blob([label],{type:'text/plain'}),label+'.txt');const r=await fetch('/api/flow/cases/'+id+'/files',{method:'POST',headers:{'X-CSRF-Token':token,'X-Store-ID':'1'},body:fd});return{status:r.status,body:await r.json()};}''',{'id':case_id,'label':label});assert result['status']==200,result;return result['body']['id']
        fid=upload_api(purchase['id'],'合成采购到货')
        for key,values in [('approve',{}),('receive',{'lines':[{'line_id':purchase['lines'][0]['id'],'quantity_milli':5000}],'evidence_id':fid})]:purchase=checked_request(admin,f"/api/procurement/orders/{purchase['id']}/actions/{key}",'POST',{'request_id':secrets.token_hex(16),'version':purchase['version'],'values':values})
        employees={};ids={}
        for role,label in [('service','服务顾问'),('manager','主管'),('technician','技师'),('inventory','库管'),('finance','财务')]:
            secret=secrets.token_urlsafe(24)
            u=checked_request(admin,'/api/users','POST',{'username':'intake-'+role,'display_name':'接待验收'+label,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},status=201);ids[role]=u['id']
            p=page();login_page(p,base,'intake-'+role,secret);p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24);p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'intake-'+role,changed);employees[role]=p
        service,manager,technician,inventory,finance=(employees[k] for k in ('service','manager','technician','inventory','finance'))
        navigate(manager,'service-intake/resources','工位与快捷项目');manager.locator('[data-act=intake-resource-new]').click()
        manager.locator('#modal [name=code]').fill('REPAIR-BAY');manager.locator('#modal [name=name]').fill('实际维修工位');manager.locator('#modal [name=type]').select_option('维修');save_modal(manager)
        resources=checked_request(admin,'/api/service-intake/resources');res=next(r for r in resources if r['code']=='REPAIR-BAY')
        washres=post('/resources',{'code':'WASH-BAY','name':'实际洗车工位','resource_type':'wash'})
        preset=post('/presets',{'code':'QUICK-REPAIR','name':'维修快捷预填','profile':'quick','lines':[{'work_item_id':work['id'],'quantity_milli':1000}]})
        washpreset=post('/presets',{'code':'QUICK-WASH','name':'标准洗车预填','profile':'wash','lines':[{'work_item_id':wash['id'],'quantity_milli':1000}]})
        def select(p,name,value):p.locator('#modal [name='+name+']').select_option(str(value))
        def fill(p,name,value):p.locator('#modal [name='+name+']').fill(str(value))
        def book(p,resource_id,preset_id,offset=1):
            navigate(p,'service-intake/appointments','维修预约与到店');p.locator('[data-act=intake-new]').click();select(p,'customer_vehicle_id',vehicle['id']);select(p,'resource_id',resource_id);select(p,'preset_id',preset_id)
            start=datetime.now()+timedelta(hours=offset);fill(p,'starts_at',start.strftime('%Y-%m-%dT%H:%M'));fill(p,'ends_at',(start+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'));fill(p,'reason','客户预约后现场确认维修诉求');save_modal(p)
            expect(p.locator('#main h1')).to_have_text('合成接待客户 · 维修预约')
            return checked_request(admin,'/api/service-intake/appointments')['items'][0]
        a=book(service,res['id'],preset['id'])
        def visit(p,route,title):p.goto(base+'/?visit='+secrets.token_hex(5)+'#'+route);expect(p.locator('#main h1')).to_have_text(title)
        def upload(p,case_id,label,category='evidence'):
            p.locator('[data-act=upload]').click();select(p,'category',category);p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('合成凭据：'+label).encode()});save_modal(p);expect(p.locator('#main')).to_contain_text(label+'.txt')
            return next(f['id'] for f in checked_request(admin,'/api/flow/cases/'+str(case_id))['files'] if f['name']==label+'.txt')
        def ensure_task(case_id,key,role):
            task=next(t for t in checked_request(admin,'/api/flow/cases/'+str(case_id))['tasks'] if t['key']==key and t['status']=='open')
            if task['assignee_id']!=ids[role]:checked_request(admin,'/api/flow/tasks/'+str(task['id'])+'/assign','POST',{'version':task['version'],'assignee_id':ids[role],'reason':'真实岗位演练明确交接责任'})
        ensure_task(a['case_id'],'intake_arrive','service');visit(service,'service-intake/appointments/'+str(a['id']),a['title'])
        assert not service.locator('[data-act=intake-action][data-key=convert]').count()
        arrival_file=upload(service,a['case_id'],'现场客户车辆VIN','inspection');service.locator('[data-act=intake-action][data-key=arrive]').click();fill(service,'checked_vin','LFV2A21K9J7654321');fill(service,'odometer_km',10000);select(service,'evidence_id',arrival_file)
        service.locator('#modal button[type=submit]').click();expect(service.locator('#modal .formerror')).to_contain_text('现场VIN');assert_fits_mobile(service);screenshots.append(take_screenshot(service,output,'00_mobile_vin_mismatch_refused.png'))
        fill(service,'checked_vin',vehicle['vin']);save_modal(service);ensure_task(a['case_id'],'intake_convert','service');visit(service,'service-intake/appointments/'+str(a['id']),a['title'])
        service.locator('[data-act=intake-action][data-key=convert]').click();save_modal(service)
        converted=checked_request(admin,'/api/service-intake/appointments/'+str(a['id']));case_id=converted['repair_case_id'];title='合成接待客户 · 维修明细';route='repair-orders/'+str(case_id)
        def current():return checked_request(admin,'/api/repair-orders/'+str(case_id))
        def repair_visit(p):visit(p,route,title)
        def action(p,key):p.locator('[data-act=repair-action][data-key='+key+']').click();expect(p.locator('#modal')).to_be_visible()
        original=current();assert original['flow_version']==4 and original['state']=='approval' and not original['quotes'][0]['price_approved']
        repair_visit(service);assert_fits_mobile(service);screenshots.append(take_screenshot(service,output,'01_mobile_prefill_pending_approval.png'))
        steps.append('服务顾问登记时段并现场核对VIN；错误VIN中文拒绝，实际到店后只转一张v4工单，快捷预填仍待价格与客户授权')
        action(service,'quote_cancel');fill(service,'reason','加入本次实际需要配件后重新报价');save_modal(service)
        action(service,'quote');line=service.locator('[data-repair-line]').first;line.locator('[name=source]').select_option('work:'+str(work['id']));line.locator('[name=price]').fill('100.00')
        service.locator('[data-act=repair-add-line]').click();line=service.locator('[data-repair-line]').nth(1);line.locator('[name=source]').select_option('part:'+str(item['id']));line.locator('[name=price]').fill('5.00');fill(service,'reason','确认本次实际维修与一件配件');save_modal(service)
        def authorize_quote(label):
            q=current()['quotes'][-1];ensure_task(case_id,'repair_price_'+str(q['id']),'manager');repair_visit(manager);action(manager,'price_approve');fill(manager,'reason','主管核对本版价格及最低金额');save_modal(manager)
            repair_visit(service);fid=upload(service,case_id,label,'authorization');action(service,'authorize');select(service,'evidence_id',fid);save_modal(service);return fid
        auth_file=authorize_quote('本次维修报价客户授权')
        ensure_task(case_id,'repair_work','technician');repair_visit(technician);assert 'amount_cents' not in request(technician,'/api/repair-orders/'+str(case_id))['body'];assert auth_file not in [f['id'] for f in checked_request(technician,'/api/flow/cases/'+str(case_id))['files']]
        refused=technician.evaluate('''async id=>{const r=await fetch('/api/flow/files/'+id,{headers:{'X-Store-ID':'1'}});return r.status;}''',auth_file);assert refused in (403,404),refused
        action(technician,'start');fill(technician,'result','技师确认本车实际进位并开工');save_modal(technician)
        ensure_task(case_id,'repair_issue','inventory');repair_visit(inventory);fid=upload(inventory,case_id,'库管本次实际发料');action(inventory,'issue');select(inventory,'line_label',inventory.locator('#modal [name=line_label] option').nth(1).get_attribute('value'));fill(inventory,'quantity','1.000');select(inventory,'evidence_id',fid);save_modal(inventory)
        assert_fits_mobile(inventory);screenshots.append(take_screenshot(inventory,output,'02_mobile_inventory_without_prices.png'))
        steps.append('主管价格批准和客户授权后，技师实际进位、库管按授权发料；技师库管接口和页面均不返回报价与授权文件')
        def finish_quality():
            repair_visit(technician);action(technician,'finish');fill(technician,'result','本人完成授权范围施工');save_modal(technician)
            ensure_task(case_id,'repair_quality','service');repair_visit(service);fid=upload(service,case_id,'本次实际质检'+secrets.token_hex(3),'inspection');action(service,'quality');fill(service,'result','安全检查与维修质量通过');select(service,'outcome','合格');select(service,'evidence_id',fid);save_modal(service)
        finish_quality();repair_visit(manager);fid=upload(manager,case_id,'本次客户承担确认');action(manager,'allocate');fill(manager,'amount_customer','105.00');fill(manager,'labor_cost','10.00');select(manager,'evidence',fid);save_modal(manager)
        repair_visit(finance);fid=upload(finance,case_id,'本次客户实际收款','receipt');action(finance,'receive');select(finance,'account_id',account['id']);fill(finance,'reference','INTAKE-ORIGINAL-CASH');select(finance,'evidence_id',fid);save_modal(finance)
        repair_visit(service);fid=upload(service,case_id,'原维修客户接车');action(service,'release');select(service,'evidence_id',fid);save_modal(service);original=current();original_id=case_id;assert original['state']=='completed'
        steps.append('质检通过、主管冻结客户105元承担、财务实际到账后服务顾问确认接车；实际工位释放')
        navigate(service,'service-intake/reworks','原单责任返修');service.locator('[data-act=intake-rework-new]').click();select(service,'source_case_id',original_id);select(service,'source_line_id',checked_request(admin,'/api/service-intake/sources')['items'][0]['lines'][0]['id']);select(service,'resource_id',res['id']);fill(service,'reason','已完成项目出现原责任缺陷，申请本次售后返修');save_modal(service)
        expect(service.locator('#main h1')).to_have_text('合成接待客户 · 售后责任返修申请');rw=checked_request(admin,'/api/service-intake/reworks')['items'][0];rroute='service-intake/reworks/'+str(rw['id']);rtitle=rw['title']
        ensure_task(rw['case_id'],'intake_liability','manager');visit(manager,rroute,rtitle);fid=upload(manager,rw['case_id'],'原责任审核与内部承担');manager.locator('[data-act=intake-action][data-key=approve]').click();fill(manager,'reason','核对原维修证据属于本店责任');fill(manager,'internal_name','门店维修责任');select(manager,'evidence_id',fid);save_modal(manager)
        assert_fits_mobile(manager);screenshots.append(take_screenshot(manager,output,'03_mobile_rework_liability_approved.png'))
        ensure_task(rw['case_id'],'intake_rework_convert','service');visit(service,rroute,rtitle);fid=upload(service,rw['case_id'],'返修本次实际到店VIN','inspection');service.locator('[data-act=intake-action][data-key=convert]').click();fill(service,'checked_vin',vehicle['vin']);fill(service,'odometer_km',10200);select(service,'evidence_id',fid);save_modal(service)
        rw=checked_request(admin,'/api/service-intake/reworks/'+str(rw['id']));case_id=rw['repair_case_id'];route='repair-orders/'+str(case_id);title='合成接待客户 · 责任返修';repair_visit(service)
        action(service,'quote');line=service.locator('[data-repair-line]').first;line.locator('[name=source]').select_option('work:'+str(work['id']));line.locator('[name=price]').fill('15.00');fill(service,'reason','独立记录本次责任返修工作');save_modal(service);authorize_quote('本次内部返修客户施工授权')
        ensure_task(case_id,'repair_work','technician');repair_visit(technician);action(technician,'start');fill(technician,'result','本次责任返修实际进入工位');save_modal(technician);finish_quality()
        repair_visit(manager);fid=upload(manager,case_id,'本次内部责任费用确认');action(manager,'allocate');expect(manager.locator('#modal')).to_contain_text('全部由 门店维修责任 承担');fill(manager,'labor_cost','8.00');select(manager,'evidence_id',fid);save_modal(manager)
        row=current();assert row['customer_due_cents']==0 and row['revenue_cents']==0 and row['allocations'][0]['amount_cents']==1500
        repair_visit(service);fid=upload(service,case_id,'责任返修客户实际接车');action(service,'release');select(service,'evidence_id',fid);save_modal(service)
        repair_visit(finance);assert not finance.locator('[data-key=receive]').count();assert_fits_mobile(finance);screenshots.append(take_screenshot(finance,output,'04_mobile_internal_rework_no_customer_cash.png'))
        finance.locator('.panel').filter(has=finance.get_by_role('heading',name='各承担方与实际到账',exact=True)).screenshot(path=str(output/'05_mobile_internal_allocation_panel.png'));screenshots.append(str(output/'05_mobile_internal_allocation_panel.png'))
        assert checked_request(admin,'/api/service-intake/reworks/'+str(rw['id']))['status']=='completed'
        original_after=checked_request(admin,'/api/repair-orders/'+str(original_id));assert sum(p['amount_cents'] for a in original_after['allocations'] for p in a['payments'])==10500
        steps.append('服务顾问关联已交车同VIN原单，主管批准全部内部责任后再次现场转单；本次15元单独记内部费用，原105元收款不复制且不再向客户收取')
        a=book(service,washres['id'],washpreset['id'],4);ensure_task(a['case_id'],'intake_arrive','service');visit(service,'service-intake/appointments/'+str(a['id']),a['title']);fid=upload(service,a['case_id'],'洗车实际来访','inspection');service.locator('[data-act=intake-action][data-key=arrive]').click();fill(service,'checked_vin',vehicle['vin']);fill(service,'odometer_km',10300);select(service,'evidence_id',fid);save_modal(service)
        service.locator('[data-act=intake-action][data-key=leave]').click();fill(service,'reason','客户临时离场，本次未开单未施工');select(service,'evidence_id',fid);save_modal(service)
        a=checked_request(admin,'/api/service-intake/appointments/'+str(a['id']));assert a['arrived_at'] and a['status']=='cancelled' and not a['repair_case_id'];screenshots.append(take_screenshot(service,output,'06_mobile_arrived_then_left_no_order.png'))
        steps.append('快捷洗车预约实际到店后临时离场，明确记录未开单离场；到店事实保留，无伪造施工和现金')
        assert not errors,errors
        return {'mode':'real_http_chrome','file_scan_mode':'structure_only','viewport':'390x844','checks_passed':len(steps),'steps':steps,'javascript_errors':errors,'screenshots':screenshots,'original_cash_cents':10500,'rework_internal_cents':1500,'rework_customer_cash_cents':0}
    finally:
        for c in contexts:c.close()

if __name__=='__main__':harness.exercise=exercise;harness.main()
