"""Actual HTTP Chrome, original repair stock and employee 390px reports."""
import csv,io,re,secrets
from datetime import datetime,timedelta,timezone,date
from pathlib import Path
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login


def exercise(browser,base,password,output):
    contexts=[];errors=[];screens=[];steps=[];req=harness.checked_request
    def page(width=390):
        ctx=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(ctx);p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    def shot(p,name,selector):
        expect(p.locator('#toast')).not_to_have_class(re.compile('visible'),timeout=10000);p.locator(selector).first.scroll_into_view_if_needed();path=output/name;p.screenshot(path=str(path));screens.append(str(path))
    admin=page(1440)
    try:
        harness.login_page(admin,base,'admin',password);people={}
        for role in ('inventory','manager'):
            secret=secrets.token_urlsafe(25);req(admin,'/api/users','POST',{'username':'rm-'+role,'display_name':'合成实际领料'+role,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},status=201)
            p=page();employee_login(p,base,'rm-'+role,secret);people[role]=p
        inventory,manager=people['inventory'],people['manager'];day=admin.evaluate('day()')
        def typed(kind,v):return req(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':v},status=201)
        def master(kind,v):return req(admin,'/api/flow/master/'+kind,'POST',{'values':v},status=201)
        def proof(p,cid,category='evidence'):
            harness.navigate(p,'case/'+str(cid),req(p,'/api/flow/cases/'+str(cid))['title']);p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category)
            p.locator('#modal [name=file]').set_input_files({'name':'合成领料实际凭据-'+secrets.token_hex(3)+'.txt','mimeType':'text/plain','buffer':'合成实际流程事实，仅测试'.encode()});harness.save_modal(p);return req(p,'/api/flow/cases/'+str(cid))['files'][-1]['id']
        item=master('items',{'sku':'RM-PART','name':'合成原成本配件','unit':'件','reorder':'0','active':True})
        supplier=typed('suppliers',{'code':'RM-S','name':'合成维修原料供应商'})
        purchase=req(admin,'/api/procurement/orders','POST',{'request_id':secrets.token_hex(16),'supplier_id':supplier['id'],'reason':'合成维修供料','lines':[{'item_id':item['id'],'quantity_milli':5000,'unit_cost_cents':123}]},status=201)
        for name,values in [('approve',{}),('receive',{'lines':[{'line_id':purchase['lines'][0]['id'],'quantity_milli':5000}],'evidence_id':proof(admin,purchase['id'])})]:
            purchase=req(admin,f'/api/procurement/orders/{purchase["id"]}/actions/{name}','POST',{'request_id':secrets.token_hex(16),'version':purchase['version'],'values':values})
        customer=master('customers',{'name':'合成维修领料客户','phone':'13900008761','contact_allowed':True,'note':''})
        vehicle=req(admin,'/api/customer-service/vehicles','POST',{'request_id':secrets.token_hex(16),'values':{'customer_id':customer['id'],'vin':'LFV2A21K9J1234591','plate':'合成料A123','model_name':'冻结合成车型甲','source_reference':'合成原车辆登记凭据','confirmed':True}},status=201)['vehicle']
        resource=req(admin,'/api/service-intake/resources','POST',{'request_id':secrets.token_hex(16),'code':'RM-BAY','name':'合成实际维修工位','resource_type':'repair'},status=201)
        start=datetime.now(timezone.utc)+timedelta(hours=1)
        a=req(admin,'/api/service-intake/appointments','POST',{'request_id':secrets.token_hex(16),'customer_vehicle_id':vehicle['id'],'resource_id':resource['id'],'starts_at':start.isoformat(),'ends_at':(start+timedelta(hours=1)).isoformat(),'problem':'合成原实际维修'},status=201)
        for name,v in [('arrive',{'checked_vin':vehicle['vin'],'odometer_km':5000,'evidence_id':proof(admin,a['case_id'],'inspection')}),('convert',{'due_date':day})]:
            a=req(admin,f'/api/service-intake/appointments/{a["id"]}/actions/{name}','POST',{'request_id':secrets.token_hex(16),'version':a['version'],'values':v})
        cid=a['repair_case_id']
        def current():return req(admin,'/api/repair-orders/'+str(cid))
        def command(p,name,v):return req(p,f'/api/repair-orders/{cid}/actions/{name}','POST',{'request_id':secrets.token_hex(16),'version':current()['version'],'values':v})
        work1=typed('work_items',{'code':'RM-W1','name':'合成诊断作业','billing_unit':'job','standard_fee_cents':1000});work2=typed('work_items',{'code':'RM-W2','name':'合成检查作业','billing_unit':'job','standard_fee_cents':1000})
        row=command(admin,'quote',{'reason':'两项作业，配件授权三件','lines':[{'kind':'work','source_id':w['id'],'quantity_milli':1000,'unit_price_cents':1000} for w in (work1,work2)]+[{'kind':'part','source_id':item['id'],'quantity_milli':3000,'unit_price_cents':500}]});qid=row['quotes'][-1]['id']
        command(manager,'price_approve',{'quote_id':qid,'minimum_total_cents':0,'allow_below_minimum':False,'reason':'主管确认当前报价价格'})
        command(admin,'authorize',{'quote_id':qid,'evidence_id':proof(admin,cid,'authorization')});command(admin,'start',{'result':'合成技师实际开工'})
        assert req(manager,'/api/repair-material-reports')['details']==[]
        line=next(l for l in current()['quotes'][-1]['lines'] if l['kind']=='part')
        row=command(inventory,'issue',{'line_key':line['line_key'],'quantity_milli':2000,'evidence_id':proof(inventory,cid)});original=row['stock'][0]
        command(inventory,'return_material',{'original_id':original['id'],'quantity_milli':500,'evidence_id':proof(inventory,cid)})
        harness.navigate(inventory,'repair-materials','维修实际领退料分析');harness.assert_fits_mobile(inventory)
        expect(inventory.locator('#main')).to_contain_text('冻结合成车型甲');expect(inventory.locator('#main')).not_to_contain_text('期间净领成本（元）')
        data=req(inventory,'/api/repair-material-reports');assert data['rows'][0]['net_milli']==1500 and 'net_cents' not in data['rows'][0]
        shot(inventory,'01_repair_material_inventory_quantity_mobile.png','.work-cards .card')
        with inventory.expect_download() as event:inventory.locator('[data-act=rm-export][data-key=repair_material_totals]').click()
        downloaded=Path(event.value.path()).read_text(encoding='utf-8-sig');assert '成本（元）' not in downloaded and '1.5' in downloaded
        steps.append('库管实际领2件、原退0.5件，报告净1.5件；授权3件不冒充领料，390px页面/API/真实CSV均隐藏成本')
        harness.navigate(manager,'repair-materials','维修实际领退料分析');harness.assert_fits_mobile(manager)
        data=req(manager,'/api/repair-material-reports');assert data['complete'] and data['rows'][0]['net_cents']==184
        assert sum(data['charts'][0]['series'][0]['values'])==184
        shot(manager,'02_repair_material_manager_original_cost_mobile.png','.work-cards .card')
        for w in (work1,work2):
            manager.locator('#repair-material-filters [name=work_item_id]').select_option(str(w['id']));manager.locator('#repair-material-filters button[type=submit]').click()
            expect(manager.locator('#main')).to_contain_text('1.84');assert len(req(manager,'/api/repair-material-reports?work_item_id='+str(w['id']))['details'])==2
        with manager.expect_download() as event:manager.locator('[data-act=rm-export][data-key=repair_material_movements]').click()
        rows=list(csv.reader(io.StringIO(Path(event.value.path()).read_text(encoding='utf-8-sig'))));t=req(manager,'/api/repair-material-reports?work_item_id='+str(work2['id']))['tables']['repair_material_movements']
        assert rows==[t['headers']]+[[str(v) for v in row['values']] for row in t['rows']]
        steps.append('主管核对原成本2.46元、原退0.62元、净1.84元；按两个原作业分别筛查均只保留同两笔领退流水，成本不倍增，图表和CSV与表同源')
        vehicle=req(admin,'/api/customer-service/vehicles/'+str(vehicle['id']))['vehicle']
        req(admin,'/api/customer-service/vehicles/'+str(vehicle['id']),'PUT',{'request_id':secrets.token_hex(16),'version':vehicle['version'],'values':{'plate':vehicle['plate'],'model_name':'当前名称乙不可覆盖历史','active':True,'reason':'合成有据档案更正'}})
        manager.reload();expect(manager.locator('#main')).to_contain_text('冻结合成车型甲');expect(manager.locator('#main')).not_to_contain_text('当前名称乙不可覆盖历史')
        manager.locator('#repair-material-filters [name=work_item_id]').select_option(str(work2['id']));manager.locator('#repair-material-filters button[type=submit]').click()
        expect(manager.locator('#main')).to_contain_text('1.84')
        manager.locator('#datefilters [name=date_from]').fill(day);manager.locator('#datefilters [name=date_to]').fill((date.fromisoformat(day)-timedelta(days=1)).isoformat());manager.locator('#datefilters button[type=submit]').click()
        expect(manager.locator('#main')).to_contain_text('开始日期不能晚于结束日期');harness.assert_fits_mobile(manager)
        expect(manager.locator('#repair-material-filters [name=work_item_id]')).to_have_value(str(work2['id']))
        shot(manager,'03_repair_material_date_error_mobile.png','div.notice.error')
        manager.locator('#datefilters [name=date_to]').fill(day);manager.locator('#datefilters button[type=submit]').click();expect(manager.locator('#main')).to_contain_text('领退料来源：可核对')
        steps.append('车辆当前名称更正后刷新仍显示原绑定快照；反向期间中文拒绝，保留筛选后可原页改正')
        assert not errors,errors
        return {'status':'passed','mode':'actual-chrome-http','steps':steps,'screenshots':screens,'javascript_errors':errors,'synthetic_only':True}
    finally:
        for ctx in contexts:ctx.close()


if __name__=='__main__':harness.exercise=exercise;harness.main()
