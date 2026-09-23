"""Actual HTTP Chrome: five employee accounts, mobile claims and original-path returns."""
import secrets
from datetime import date
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request,request,login_page,save_modal,take_screenshot,assert_fits_mobile

def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screenshots=[]
    def page(width=390):
        c=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(c);p=c.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440)
    try:
        login_page(admin,base,'admin',password);employees={}
        def post(p,path,values,status=200):return checked_request(p,path,'POST',values,status=status)
        def master(kind,v):return post(admin,'/api/flow/master/'+kind,{'values':v},201)
        def typed(kind,v):return post(admin,'/api/masters/'+kind,{'request_id':secrets.token_hex(16),'values':v},201)
        for role in ('service','manager','finance','technician','inventory'):
            secret=secrets.token_urlsafe(24);post(admin,'/api/users',{'username':'claim-'+role,'display_name':'核赔验收'+role,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},201)
            p=page();login_page(p,base,'claim-'+role,secret);p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24);p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'claim-'+role,changed);employees[role]=p
        service,manager,finance,technician,inventory=(employees[k] for k in ('service','manager','finance','technician','inventory'))
        customer=master('customers',{'name':'合成核赔客户','phone':'13900004101','contact_allowed':True,'note':''})
        work=typed('work_items',{'code':'CLAIM-JOB','name':'合成原维修诊断项目','billing_unit':'job','standard_fee_cents':5000})
        insurer=typed('insurers',{'code':'CLAIM-INS','name':'合成核赔保险公司'});account=master('accounts',{'name':'合成核赔原银行','account_type':'bank','active':True})
        source=post(service,'/api/repair-orders',{'request_id':secrets.token_hex(16),'customer_id':customer['id'],'plate':'合成核赔A001','problem':'原维修实际履约后客户申请报销','due_date':date.today().isoformat()},201)
        def source_now():return checked_request(admin,'/api/repair-orders/'+str(source['id']))
        def source_action(p,key,v):return post(p,f"/api/repair-orders/{source['id']}/actions/{key}",{'request_id':secrets.token_hex(16),'version':source_now()['version'],'values':v})
        def api_upload(p,case_id,label,category='authorization'):
            r=p.evaluate('''async({id,label,category})=>{const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];const f=new FormData();f.append('category',category);f.append('file',new Blob([label],{type:'text/plain'}),label+'.txt');const r=await fetch('/api/flow/cases/'+id+'/files',{method:'POST',headers:{'X-CSRF-Token':token,'X-Store-ID':'1'},body:f});return{status:r.status,body:await r.json()};}''',{'id':case_id,'label':label,'category':category});assert r['status']==200,r;return r['body']['id']
        source_action(service,'quote',{'reason':'合成原维修实际诊断报价','lines':[{'kind':'work','source_id':work['id'],'quantity_milli':1000,'unit_price_cents':5000}]})
        q=source_now()['quotes'][-1]
        source_action(manager,'price_approve',{'quote_id':q['id'],'minimum_total_cents':5000,'allow_below_minimum':False,'reason':'独立核对原维修价格'})
        source_action(service,'authorize',{'quote_id':q['id'],'evidence_id':api_upload(service,source['id'],'原客户维修报价授权')})
        source_action(technician,'start',{'result':'技师本人实际开工'});source_action(technician,'finish',{'result':'技师实际完成诊断维修'})
        source_action(service,'quality',{'passed':True,'result':'实际维修质量检查通过','evidence_id':api_upload(service,source['id'],'原维修质检','inspection')})
        source_action(manager,'allocate',{'labor_cost_cents':500,'allocations':[{'payer_type':'customer','amount_cents':5000,'due_date':date.today().isoformat()}],'evidence_id':api_upload(manager,source['id'],'原客户承担确认')})
        source_action(finance,'receive',{'allocation_id':source_now()['allocations'][0]['id'],'amount_cents':5000,'account_id':account['id'],'reference':'原客户实际维修付款','evidence_id':api_upload(finance,source['id'],'原客户实收','receipt')})
        source_action(service,'release',{'evidence_id':api_upload(service,source['id'],'客户已实际接车')})
        def visit(p,route,title):p.goto(base+'/?visit='+secrets.token_hex(5)+'#'+route);expect(p.locator('#main h1')).to_have_text(title)
        visit(service,'claims','理赔索赔与客户报销');service.locator('[data-act=claim-new]').click()
        expect(service.locator('#modal [name=source]')).to_be_visible()
        service.locator('#modal [name=source]').select_option(label=next(x for x in service.locator('#modal [name=source] option').all_text_contents() if source['number'] in x))
        service.locator('#modal [name=party]').select_option('保险 · '+insurer['name']);service.locator('#modal [name=route]').select_option('第三方经门店转付客户');service.locator('#modal [name=reason]').fill('经核对客户实际付款，向保险申请经店报销');save_modal(service)
        row=checked_request(admin,'/api/claims')['items'][0];case_id=row['id'];route='claims/'+str(case_id);title=row['title']
        def current():return checked_request(admin,'/api/claims/'+str(case_id))
        def refresh(p):visit(p,route,title)
        def action(p,key,plan=None):
            selector='[data-act=claim-action][data-key='+key+']'+('[data-plan="'+str(plan)+'"]' if plan else '')
            p.locator(selector).click();expect(p.locator('#modal')).to_be_visible()
        def upload(p,label,financial=False):
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option('receipt' if financial else 'authorization');p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('合成实际原件 '+label).encode()});save_modal(p)
            expect(p.locator('#main')).to_contain_text(label+'.txt');return next(f['id'] for f in checked_request(admin,'/api/flow/cases/'+str(case_id))['files'] if f['name']==label+'.txt')
        def select(p,name,value):p.locator('#modal [name='+name+']').select_option(str(value))
        def simple(p,key,label,reason=None,financial=False):
            refresh(p);fid=upload(p,label,financial);action(p,key)
            if reason:p.locator('#modal [name=reason]').fill(reason)
            select(p,'evidence_id',fid);save_modal(p)
        action(service,'assess');service.locator('[data-claim-line] [name=amount]').fill('30.00');service.locator('#modal [name=reason]').fill('引用原维修项目核损三十元');assert_fits_mobile(service);screenshots.append(take_screenshot(service,output,'01_claim_assessment_mobile.png'));save_modal(service)
        simple(manager,'approve','主管独立核价原件','主管核对原明细和当前申请金额')
        refresh(service);fid=upload(service,'本次外部实际提交');action(service,'transmit');service.locator('#modal [name=external_reference]').fill('合成核赔受理一号');select(service,'evidence_id',fid);save_modal(service)
        refresh(service);fid=upload(service,'外部实际部分核准通知');action(service,'result');select(service,'outcome','partial');service.locator('[data-claim-line] [name=amount]').fill('20.00');service.locator('#modal [name=reason]').fill('外部实际核准二十元，余十元拒绝');select(service,'evidence_id',fid);save_modal(service)
        refresh(service);assert_fits_mobile(service);screenshots.append(take_screenshot(service,output,'02_claim_external_result_no_cash.png'));assert current()['cash']==[]
        steps.append('顾问原明细核价，另一主管独立复核；实际提交与部分核准均留原件，未产生现金')
        simple(manager,'reimbursement_approve','独立核对原客户现金净额','核对原客户五十元实收和本案二十元核准')
        def cash_action(key,amount,label,plan=None,refuse=False):
            refresh(finance);fid=upload(finance,label,True);action(finance,key,plan);finance.locator('#modal [name=amount]').fill(amount)
            if finance.locator('#modal [name=original]').count():select(finance,'original',finance.locator('#modal [name=original] option').nth(1).get_attribute('value'))
            select(finance,'account_id',account['id']);finance.locator('#modal [name=reference]').fill(label+'流水');select(finance,'evidence_id',fid)
            if refuse:
                finance.locator('#modal button[type=submit]').click();expect(finance.locator('#modal .formerror')).to_contain_text('超过原核准');assert_fits_mobile(finance);screenshots.append(take_screenshot(finance,output,'03_claim_cash_cap_refused.png'));finance.locator('#modal [name=amount]').fill('20.00')
            save_modal(finance)
        cash_action('pass_receive','20.01','第三方实际到款',refuse=True);cash_action('pass_pay','10.00','实际转付客户十元')
        steps.append('财务核准不作到账；实际到店超过核准一分被拒绝，实际二十元到账后仅转付客户十元')
        incoming=next(x for x in current()['cash'] if x['purpose']=='pass_receive');payout=next(x for x in current()['cash'] if x['purpose']=='pass_pay')
        def make_return(original,amount,label):
            refresh(service);fid=upload(service,label);action(service,'return_plan');service.locator('[data-claim-selection][data-id="'+str(original)+'"] input').fill(amount);service.locator('#modal [name=reason]').fill(label);select(service,'evidence_id',fid);save_modal(service)
            plan=current()['return_plans'][-1]['id'];refresh(manager);fid=upload(manager,label+'独立批准');action(manager,'return_approve',plan);select(manager,'evidence_id',fid);save_modal(manager);return plan
        unused=make_return(incoming['id'],'10.00','未转付十元原路退回第三方方案');cash_action('unused_refund','10.00','未转付原款实际退款',unused)
        simple(service,'close','第三方核对未用金额结案','未转付十元已原路退回，仅保留实际客户报销十元')
        assert current()['reimbursement_usage_cents']==1000
        paid=make_return(payout['id'],'5.00','客户另将原已报销五元原路返还');cash_action('customer_return','5.00','客户五元实际退回原账户',paid)
        assert current()['reimbursement_usage_cents']==1000
        cash_action('party_return','5.00','客户返还五元实际退第三方',paid);assert current()['reimbursement_usage_cents']==500
        refresh(finance);assert_fits_mobile(finance);screenshots.append(take_screenshot(finance,output,'04_claim_original_returns_complete.png'))
        steps.append('独立批准未转付部分直接退原第三方；已转付部分客户退回再实际退第三方，资金到原第三方后才释放报销额度')
        for p in (technician,inventory):
            assert request(p,'/api/claims/'+str(case_id))['status']==403
            fid=checked_request(admin,'/api/flow/cases/'+str(case_id))['files'][0]['id'];denied=request(p,'/api/flow/files/'+str(fid));assert denied['status'] in (403,404),denied
        steps.append('技师、库管实际账号不能读取核赔价格与凭据；五岗位真实账户经独立HTTP会话办理或核验')
        assert source_now()['amount_cents']==5000 and source_now()['state']=='completed'
        assert not errors,errors
        return {'mode':'real-http-chrome','viewport':390,'passed':steps,'javascript_errors':errors,'screenshots':screenshots}
    finally:
        for c in contexts:c.close()

if __name__=='__main__':harness.exercise=exercise;harness.main()
