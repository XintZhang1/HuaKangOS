"""Three independent employee sessions, actual HTTP and 390px report evidence."""
import csv,io,re,secrets
from datetime import datetime,timedelta,timezone,date
from pathlib import Path
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login

def exercise(browser,base,password,output):
    contexts=[];errors=[];screens=[];steps=[];req=harness.checked_request
    def page(width=390):
        c=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(c);p=c.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    def shot(p,name,selector):
        expect(p.locator('#toast')).not_to_have_class(re.compile('visible'),timeout=10000);p.locator(selector).first.scroll_into_view_if_needed();path=output/name;p.screenshot(path=str(path));screens.append(str(path))
    admin=page(1440)
    try:
        harness.login_page(admin,base,'admin',password);people={};ids={}
        for role,label in [('sales','销售'),('service','服务顾问'),('manager','主管')]:
            secret=secrets.token_urlsafe(25);u=req(admin,'/api/users','POST',{'username':'visits-'+role,'display_name':'合成实际跟进'+label,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},status=201);ids[role]=u['id']
            p=page();employee_login(p,base,'visits-'+role,secret);people[role]=p
        sales,service,manager=(people[k] for k in ('sales','service','manager'));day=admin.evaluate('day()')
        lead=req(sales,'/api/flow/cases','POST',{'request_id':secrets.token_hex(16),'kind':'lead','values':{'customer_name':'合成售前跟进客户','customer_phone':'13900006771','source':'展厅到店','confirm_new_customer':True}},status=201)
        lead=req(manager,f'/api/flow/cases/{lead["id"]}/actions/assign','POST',{'request_id':secrets.token_hex(16),'version':lead['version'],'values':{'assignee_id':ids['sales']}})
        harness.navigate(sales,'case/'+str(lead['id']),lead['title']);sales.locator('[data-act=caseaction][data-key=remind]').click();sales.locator('#modal [name=result]').fill('本次已沟通预算，约定明天再联系');harness.save_modal(sales)
        sales.locator('[data-act=caseaction][data-key=intent]').click();sales.locator('#modal [name=need]').fill('本次明确家庭通勤车型需求');harness.save_modal(sales)
        harness.navigate(sales,'visit-activity','跟进与进出厂统计');harness.assert_fits_mobile(sales)
        d=req(sales,'/api/visit-activity-reports');assert d['metrics']['presales_contact_events']==2 and d['metrics']['presales_contact_cases']==1
        expect(sales.locator('#main')).to_contain_text('本次已沟通预算，约定明天再联系');shot(sales,'01_presales_actual_followup_mobile.png','.work-cards .card')
        with sales.expect_download() as event:sales.locator('[data-act=va-export][data-key=presales_activity]').last.click()
        downloaded=list(csv.reader(io.StringIO(Path(event.value.path()).read_text(encoding='utf-8-sig'))));t=d['tables']['presales_activity'];assert downloaded==[t['headers']]+[[str(v) for v in row['values']] for row in t['rows']]
        steps.append('销售实际记录沟通及购车需求，报告两次原事件；未来回访任务未重复计数，390px和真实CSV均与源行一致')
        customer=req(admin,'/api/flow/master/customers','POST',{'values':{'name':'合成进出厂客户','phone':'13900006772','contact_allowed':True,'confirm_new_customer':True}},status=201)
        vehicle=req(admin,'/api/customer-service/vehicles','POST',{'request_id':secrets.token_hex(16),'values':{'customer_id':customer['id'],'vin':'LFV2A21K9J1234553','plate':'合成厂A123','model_name':'合成进厂车型','source_reference':'合成现场车辆登记凭据','confirmed':True}},status=201)['vehicle']
        resource=req(manager,'/api/service-intake/resources','POST',{'request_id':secrets.token_hex(16),'code':'VISIT-BAY','name':'合成进出厂工位','resource_type':'repair'},status=201)
        start=datetime.now(timezone.utc)+timedelta(hours=1)
        ap=req(service,'/api/service-intake/appointments','POST',{'request_id':secrets.token_hex(16),'customer_vehicle_id':vehicle['id'],'resource_id':resource['id'],'starts_at':start.isoformat(),'ends_at':(start+timedelta(hours=1)).isoformat(),'problem':'预约只是计划，不代替实际到店'},status=201)
        assert req(manager,'/api/visit-activity-reports')['metrics']['service_actual_arrivals']==0
        def proof(p,cid,category,name):
            title=req(p,'/api/flow/cases/'+str(cid))['title'];harness.navigate(p,'case/'+str(cid),title);p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category);p.locator('#modal [name=file]').set_input_files({'name':name+'.txt','mimeType':'text/plain','buffer':('合成真实来源：'+name).encode()});harness.save_modal(p)
            return next(f['id'] for f in req(p,'/api/flow/cases/'+str(cid))['files'] if f['name']==name+'.txt')
        fid=proof(service,ap['case_id'],'inspection','本次实际到店VIN核验')
        harness.navigate(service,'service-intake/appointments/'+str(ap['id']),ap['title']);service.locator('[data-act=intake-action][data-key=arrive]').click();service.locator('#modal [name=checked_vin]').fill(vehicle['vin']);service.locator('#modal [name=odometer_km]').fill('10000');service.locator('#modal [name=evidence_id]').select_option(str(fid));harness.save_modal(service)
        fid=proof(service,ap['case_id'],'inspection','本次未开单实际离场凭据')
        harness.navigate(service,'service-intake/appointments/'+str(ap['id']),ap['title']);service.locator('[data-act=intake-action][data-key=leave]').click();service.locator('#modal [name=reason]').fill('客户临时离场，实际未开单施工');service.locator('#modal [name=evidence_id]').select_option(str(fid));harness.save_modal(service)
        harness.navigate(service,'visit-activity','跟进与进出厂统计');harness.assert_fits_mobile(service)
        d=req(service,'/api/visit-activity-reports');assert d['metrics']['service_actual_arrivals']==d['metrics']['service_actual_departures']==1
        section=service.locator('.panel').filter(has=service.get_by_role('heading',name='期间实际进出厂原始行',exact=True));section.locator('.work-cards .card').last.scroll_into_view_if_needed();shot(service,'02_actual_departure_without_repair_mobile.png','[data-act=va-export][data-key=service_visit_cohort]')
        steps.append('服务顾问对同一VIN登记实际到店及未开单离场；预约初始零到店，实际链后进一出一，无伪造维修、完工或现金')
        legacy=req(admin,'/api/repair-orders','POST',{'request_id':secrets.token_hex(16),'customer_id':customer['id'],'plate':'合成旧A123','problem':'独立历史方式开单，没有现场到店来源','due_date':day},status=201)
        harness.navigate(manager,'visit-activity','跟进与进出厂统计');d=req(manager,'/api/visit-activity-reports');assert not d['complete'] and d['metrics']['service_actual_arrivals']==1 and d['metrics']['presales_contact_events']==2
        harness.assert_fits_mobile(manager);shot(manager,'03_missing_arrival_not_inferred_mobile.png','[data-act=va-export][data-key=visit_source_issues]')
        manager.locator('#visit-activity-filters [name=case_id]').select_option(str(legacy['id']));manager.locator('#visit-activity-filters button[type=submit]').click();expect(manager.locator('#main')).to_contain_text('没有获权的实际到店来源')
        manager.locator('#datefilters [name=date_from]').fill(day);manager.locator('#datefilters [name=date_to]').fill((date.fromisoformat(day)-timedelta(days=1)).isoformat());manager.locator('#datefilters button[type=submit]').click();expect(manager.locator('#main')).to_contain_text('开始日期不能晚于结束日期');expect(manager.locator('#visit-activity-filters [name=case_id]')).to_have_value(str(legacy['id']));harness.assert_fits_mobile(manager)
        shot(manager,'04_visit_period_chinese_refusal_mobile.png','div.notice.error');manager.locator('#datefilters [name=date_to]').fill(day);manager.locator('#datefilters button[type=submit]').click();expect(manager.locator('#main')).to_contain_text('没有获权的实际到店来源')
        with manager.expect_download() as event:manager.locator('[data-act=va-export][data-key=visit_source_issues]').click()
        assert '没有获权的实际到店来源' in Path(event.value.path()).read_text(encoding='utf-8-sig')
        steps.append('主管核对旧工单来源缺口：不以开单日补到店；反向日期中文拒绝保留筛选，可原页改正并下载相同缺口明细')
        assert not errors,errors
        return {'status':'passed','mode':'actual-chrome-http','viewport':'390x844','employee_sessions':3,'steps':steps,'screenshots':screens,'javascript_errors':errors,'synthetic_only':True}
    finally:
        for c in contexts:c.close()

if __name__=='__main__':harness.exercise=exercise;harness.main()
