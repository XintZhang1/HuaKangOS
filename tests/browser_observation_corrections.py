"""Actual HTTP Chrome employee flow through registered production routes."""
import sys,secrets,re,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import browser_huakangos as harness
from browser_masters import employee_login
from playwright.sync_api import expect

def exercise(browser,base,password,output):
    contexts=[];errors=[];screens=[];steps=[];req=harness.checked_request
    def page(width=390):
        ctx=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(ctx);p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    def go(p,route):
        harness.navigate(p,route,'日期里程原观察纠正')
    def shot(p,name,selector):
        expect(p.locator('#toast')).not_to_have_class(re.compile('visible'),timeout=7000);p.locator(selector).first.scroll_into_view_if_needed();harness.assert_fits_mobile(p);path=output/name;p.screenshot(path=str(path));screens.append(str(path))
    admin=page(1440)
    try:
        harness.login_page(admin,base,'admin',password);people={};ids={}
        for role in ('service','manager','customer_service'):
            secret=secrets.token_urlsafe(25);user=req(admin,'/api/users','POST',{'username':'correction-'+role,'display_name':'合成纠正'+{'service':'顾问','manager':'主管','customer_service':'客服'}[role],'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},status=201);ids[role]=user['id']
            p=page();employee_login(p,base,'correction-'+role,secret);people[role]=p
        advisor,manager,clerk=(people[r] for r in ('service','manager','customer_service'));day=admin.evaluate('day()')
        customer=req(admin,'/api/flow/master/customers','POST',{'values':{'name':'合成原里程纠正客户','phone':'13900001991','contact_allowed':True,'confirm_new_customer':True}},status=201)
        cv=req(advisor,'/api/customer-service/vehicles','POST',{'request_id':secrets.token_hex(16),'values':{'customer_id':customer['id'],'vin':'LFV2A21K9J1234553','plate':'合成纠A199','model_name':'合成原观察车型','source_reference':'本车现场原始资料','confirmed':True}},status=201)['vehicle']
        for kind,km,datevalue in [('maintenance',1000,admin.evaluate('relativeDay(-31)')),('odometer',50000,day)]:
            cv=req(advisor,f"/api/customer-service/vehicles/{cv['id']}/observations",'POST',{'request_id':secrets.token_hex(16),'version':cv['version'],'values':{'kind':kind,'observed_date':datevalue,'odometer_km':km,'valid_until':None,'source_reference':'合成原件-错误五万公里','confirmed':True}},status=200)['vehicle']
        req(manager,'/api/customer-service/reminders/rules','POST',{'request_id':secrets.token_hex(16),'values':{'name':'合成每月保养提醒','kind':'maintenance','interval_days':30,'interval_km':5000,'lead_days':3,'lead_km':100,'assignee_id':ids['service'],'active':True}},status=201)
        old=req(manager,'/api/observation-corrections/reminders/generate','POST',{'request_id':secrets.token_hex(16)})['created'][0]['case_id']
        harness.navigate(clerk,f"customer-vehicles/{cv['id']}",'客户车辆 · '+cv['plate']);clerk.locator('[data-route^="observation-corrections/vehicles/"]').click();expect(clerk.locator('#main h1')).to_have_text('日期里程原观察纠正');clerk.locator('[data-act=oc-new]').last.click();clerk.locator('#modal [name=odometer_km]').fill('500');clerk.locator('#modal [name=reason]').fill('对原仪表照片核对发现多录一位零');clerk.locator('#modal button[type=submit]').click();expect(clerk.locator('#modal .formerror')).to_contain_text('早于前一条')
        clerk.locator('#modal button[type=submit]').scroll_into_view_if_needed()
        shot(clerk,'01_correction_neighbor_refusal_mobile.png','#modal')
        clerk.locator('#modal [name=odometer_km]').fill('5000');harness.save_modal(clerk);expect(clerk.locator('#main')).to_contain_text('待提交依据')
        case_id=int(clerk.evaluate("state.route.split('/').at(-1)"));clerk.locator('[data-act=oc-upload]').click();clerk.locator('#modal [name=file]').set_input_files({'name':'原仪表照片核对说明.txt','mimeType':'text/plain','buffer':'本车本次原件核对，实际读数5000公里。'.encode()});harness.save_modal(clerk)
        row=req(clerk,f'/api/observation-corrections/cases/{case_id}');file_id=row['files'][0]['id'];clerk.locator('[data-act=oc-action][data-key=submit]').click();clerk.locator('#modal [name=evidence_id]').select_option(str(file_id));harness.save_modal(clerk);expect(clerk.locator('#main')).to_contain_text('基准复核中')
        assert clerk.locator('[data-act=oc-action][data-key=approve]').count()==0;shot(clerk,'02_correction_submitted_original_preserved_mobile.png','.panel')
        task=req(advisor,f'/api/customer-service/cases/{old}')
        task=req(advisor,f'/api/customer-service/cases/{old}/actions/start','POST',{'request_id':secrets.token_hex(16),'version':task['version'],'values':{}})['case']
        refusal=harness.request(advisor,f'/api/customer-service/cases/{old}/actions/followup','POST',{'request_id':secrets.token_hex(16),'version':task['version'],'values':{'channel':'in_person','contact_result':'contacted','note':'不能使用正在复核中的基准对外联系'}})
        assert refusal['status']==409,refusal
        harness.navigate(advisor,f'customer-service/{old}',task['subtype_label']+' · '+task['number'])
        expect(advisor.locator('#main')).to_contain_text('复核')
        assert advisor.locator('[data-act=care-action][data-action=close]').count()==0
        shot(advisor,'05_original_reminder_pending_review_mobile.png','.notice.warn')

        go(manager,f'observation-corrections/cases/{case_id}');manager.locator('[data-act=oc-action][data-key=approve]').click();manager.locator('#modal [name=evidence_id]').select_option(str(file_id));manager.locator('#modal [name=reason]').fill('另一位主管独立核对同一原件和相邻有效记录');shot(manager,'03_correction_independent_review_mobile.png','#modal');harness.save_modal(manager)
        go(advisor,f"observation-corrections/vehicles/{cv['id']}");expect(advisor.locator('#main')).to_contain_text('5,000 公里');new=req(advisor,'/api/observation-corrections/reminders/generate','POST',{'request_id':secrets.token_hex(16)})['created'];assert len(new)==1
        assert req(advisor,f'/api/customer-service/cases/{old}')['state']=='cancelled'
        assert req(advisor,'/api/observation-corrections/reminders/generate','POST',{'request_id':secrets.token_hex(16)})['created']==[]
        shot(advisor,'04_correction_effective_source_mobile.png','.panel')
        raw=req(advisor,f"/api/customer-service/vehicles/{cv['id']}")['observations'];assert next(o for o in raw if o['kind']=='odometer')['odometer_km']==50000
        steps=['原客户车辆页进入纠错；原服务任务复核中仅可内部核对，原API拒绝外联且无结案按钮','客服用原件提出误录纠正：低于前序实际值被中文拒绝，原页改正为5000','申请人上传本单原件并提交，不能自批；独立主管复用原件留下本次复核记录','服务顾问看到有效5000公里；原50000公里记录保留，旧提醒取消留史且仅生成一条替代提醒']
        assert not errors,errors
        return {'status':'passed','mode':'actual-chrome-http','integration_pending':False,'viewport':'390x844','employee_sessions':3,'steps':steps,'screenshots':screens,'source_sha256':{str(p.relative_to(harness.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [harness.ROOT/'app/customer_service.py',harness.ROOT/'app/insurance_service.py',harness.ROOT/'app/observation_corrections_service.py',harness.ROOT/'app/observation_corrections_integrity.py',harness.ROOT/'web/observationcorrections.js',harness.ROOT/'web/customerservice.js',Path(__file__).resolve()]},'javascript_errors':errors,'synthetic_only':True,'limitations':['仅全新合成数据库中的员工办理；不代表公司业务验收或正式启用。']}
    finally:
        for ctx in contexts:ctx.close()

if __name__=='__main__':
    harness.exercise=exercise;harness.main()
