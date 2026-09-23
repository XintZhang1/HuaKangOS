"""Real HTTP Chrome, distinct employee sessions, mobile service/principal/refunds."""
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
        login_page(admin,base,'admin',password)
        def post(p,path,values,status=200):return checked_request(p,path,'POST',values,status=status)
        employees={}
        for role in ('sales','service','manager','finance','inventory'):
            secret=secrets.token_urlsafe(24);post(admin,'/api/users',{'username':'svc-'+role,'display_name':'服务验收'+role,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},201)
            p=page();login_page(p,base,'svc-'+role,secret);p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24);p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'svc-'+role,changed);employees[role]=p
        sales,service,manager,finance,inventory=(employees[k] for k in ('sales','service','manager','finance','inventory'))
        customer=post(sales,'/api/flow/master/customers',{'values':{'name':'合成明细服务客户','phone':'13900007111','contact_allowed':True,'note':'仅合成浏览器验收','confirm_new_customer':True}},201)
        project=post(admin,'/api/masters/agency_projects',{'request_id':secrets.token_hex(16),'values':{'code':'BROWSER-SVC','name':'合成上牌代办','service_fee_cents':1000,'expected_days':3}},201)
        payee=post(admin,'/api/service-orders/payees',{'request_id':secrets.token_hex(16),'code':'BROWSER-PAY','name':'合成牌证缴费单位','account_name':'合成第三方收费户','account_reference':'SYNTHETIC-PAYEE-ONLY'},201)
        income=post(admin,'/api/service-orders/income-items',{'request_id':secrets.token_hex(16),'code':'BROWSER-INCOME','name':'合成客户资料咨询','unit':'项','standard_fee_cents':500},201)
        account=post(admin,'/api/flow/master/accounts',{'values':{'name':'合成服务原收款银行','account_type':'bank','active':True}},201)
        def visit(p,route,title):p.goto(base+'/?visit='+secrets.token_hex(5)+'#'+route);expect(p.locator('#main h1')).to_have_text(title)
        visit(sales,'service-orders','代办与其它客户服务');sales.locator('[data-act=serviceorder-new]').click()
        sales.locator('#modal [name=customer]').select_option(label=str(customer['id'])+' · '+customer['name']);sales.locator('#modal [name=reason]').fill('客户委托本店上牌并代缴实际本金');save_modal(sales)
        row=checked_request(sales,'/api/service-orders')['rows'][0];cid=row['id'];title=row['title'];route='service-orders/'+str(cid)
        def current():return checked_request(admin,'/api/service-orders/'+str(cid))
        def refresh(p):visit(p,route,title)
        def action(p,key,**extra):
            selector='[data-act=serviceorder-action][data-key='+key+']'+''.join('[data-'+k+'="'+str(v)+'"]' for k,v in extra.items());p.locator(selector).click();expect(p.locator('#modal')).to_be_visible()
        def upload(p,label,financial=False):
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option('receipt' if financial else 'authorization');p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('合成实际原件 '+label).encode()});save_modal(p);expect(p.locator('#main')).to_contain_text(label+'.txt')
            return next(f['id'] for f in checked_request(admin,'/api/flow/cases/'+str(cid))['files'] if f['name']==label+'.txt')
        def select(p,name,value):p.locator('#modal [name='+name+']').select_option(str(value))
        action(sales,'quote');lines=sales.locator('[data-service-line]');lines.nth(0).locator('[name=source]').select_option('fee:'+str(project['id']));lines.nth(0).locator('[name=price]').fill('10.00');lines.nth(1).locator('[name=source]').select_option('pass:'+str(payee['id']));lines.nth(1).locator('[name=name]').fill('实际牌证代缴本金');lines.nth(1).locator('[name=price]').fill('20.00');sales.locator('#modal [name=discount]').fill('0.03');sales.locator('#modal [name=reason]').fill('服务费优惠三分，代缴本金完整保留');assert_fits_mobile(sales);screenshots.append(take_screenshot(sales,output,'01_service_fee_principal_quote_mobile.png'));save_modal(sales)
        def simple(p,key,label,financial=False,**extra):
            refresh(p);fid=upload(p,label,financial);action(p,key,**extra);select(p,'evidence_id',fid);return fid
        simple(manager,'approve','独立主管核价原件');manager.locator('#modal [name=reason]').fill('独立核对服务费与代缴本金分列');save_modal(manager)
        simple(sales,'authorize','客户当前报价授权');save_modal(sales)
        def cash_action(key,amount,label,refuse=False,**extra):
            simple(finance,key,label,True,**extra);finance.locator('#modal [name=amount]').fill(amount);select(finance,'account_id',account['id']);finance.locator('#modal [name=reference]').fill(label+'独立流水')
            if refuse:
                finance.locator('#modal button[type=submit]').click();expect(finance.locator('#modal .formerror')).to_contain_text('超过');assert_fits_mobile(finance);screenshots.append(take_screenshot(finance,output,'02_service_overcollection_refused_mobile.png'));finance.locator('#modal [name=amount]').fill('29.97')
            save_modal(finance)
        cash_action('receive','29.98','客户实际到账',True)
        tender=next(t for t in current()['tenders'] if t['bucket']=='pass');cash_action('disburse','20.00','原本金实际付第三方',tender=tender['id'])
        assert current()['summary']['customer_paid_cents']==2997 and current()['summary']['thirdparty_paid_cents']==2000
        steps.append('销售建立双明细报价、另一主管批准和客户当前版授权；财务超收一分被拒绝，实际收款与代缴分开')
        fee=current()['lines'][0]['line_key'];principal=current()['lines'][1]['line_key']
        def transmit(line,label):
            simple(sales,'submit',label,line=line);sales.locator('#modal [name=external_reference]').fill(label+'真实受理号');save_modal(sales)
        def result(line,outcome,label):
            simple(sales,'external_result',label,line=line);select(sales,'outcome',outcome);sales.locator('#modal [name=result]').fill(label);save_modal(sales)
        transmit(fee,'首次实际提交');result(fee,'要求补件','第三方要求补齐客户资料')
        refresh(sales);assert sales.locator('[data-key=fulfill][data-line="'+fee+'"]').count()==0;assert_fits_mobile(sales);screenshots.append(take_screenshot(sales,output,'03_service_supplement_no_fake_completion.png'))
        transmit(fee,'按原要求实际补件');result(fee,'批准','第三方确认资料办理完成');simple(sales,'fulfill','代办实际交付客户',line=fee);sales.locator('#modal [name=result]').fill('本人实际办理并向客户交接');save_modal(sales)
        transmit(principal,'代缴实际凭证提交');result(principal,'批准','实际缴费结果确认');simple(sales,'fulfill','代缴事项实际办结',line=principal);sales.locator('#modal [name=result]').fill('原代缴本金已实际支付并交付凭证');save_modal(sales)
        assert current()['state']=='completed';steps.append('逐行外部提交、要求补件、引用补件及实际批准，实际办结与现金完全分离')
        original=current()['pass_entries'][0];cash_action('thirdparty_return','5.00','第三方实退原本金',original=original['id'])
        refresh(sales);fid=upload(sales,'客户协商终止保留费方案');action(sales,'termination');sales.locator('[data-service-retained="'+fee+'"] input').fill('2.00');sales.locator('[data-service-retained="'+principal+'"] input').fill('15.00')
        fee_tender=next(t for t in current()['tenders'] if t['bucket']=='fee' and t['amount_cents']>0)
        sales.locator('[data-service-return="'+str(fee_tender['id'])+'"] input').fill('7.97');sales.locator('[data-service-return="'+str(tender['id'])+'"] input').fill('5.00');sales.locator('#modal [name=reason]').fill('已履约服务保留两元，实际退回本金五元按原款退客户');select(sales,'evidence_id',fid);save_modal(sales);plan=current()['plans'][-1]['id']
        simple(manager,'termination_approve','独立主管终止复核',plan=plan);save_modal(manager);simple(sales,'consent','客户同意保留费和原款退款',plan=plan);save_modal(sales);simple(finance,'termination_apply','财务核对费用生效',True,plan=plan);save_modal(finance)
        cash_action('refund','7.97','服务费原款实际退回',plan=plan,tender=fee_tender['id']);cash_action('refund','5.00','已返还本金原款实退',plan=plan,tender=tender['id'])
        refresh(finance);assert_fits_mobile(finance);screenshots.append(take_screenshot(finance,output,'04_service_retained_fee_original_refunds.png'));final=current();assert final['state']=='completed' and final['summary']['customer_paid_cents']==1700 and final['summary']['pass_cash_balance_cents']==0
        steps.append('办结后第三方实退五元、独立批准与客户同意保留费、财务生效再分原款实退，最终本金余额为零')
        # A distinct service adviser handles a standalone attributable service.
        standalone=post(service,'/api/service-orders',{'request_id':secrets.token_hex(16),'subtype':'other_income','customer_id':customer['id'],'due_date':date.today().isoformat(),'reason':'客户独立咨询服务，无第三方代办'},201);sid=standalone['id']
        def act2(p,key,v):return post(p,f'/api/service-orders/{sid}/actions/{key}',{'request_id':secrets.token_hex(16),'version':checked_request(admin,'/api/service-orders/'+str(sid))['version'],'values':v})
        def proof2(p,label,category='authorization'):
            r=p.evaluate('''async({id,label,category})=>{const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];const f=new FormData();f.append('category',category);f.append('file',new Blob([label],{type:'text/plain'}),label+'.txt');const r=await fetch('/api/flow/cases/'+id+'/files',{method:'POST',headers:{'X-CSRF-Token':token,'X-Store-ID':'1'},body:f});return{status:r.status,body:await r.json()};}''',{'id':sid,'label':label,'category':category});assert r['status']==200,r;return r['body']['id']
        act2(service,'quote',{'lines':[{'line_key':'consult','bucket':'fee','income_item_id':income['id'],'quantity_milli':1000,'unit_price_cents':500,'due_date':date.today().isoformat()}],'discount_cents':0,'reason':'独立客户咨询服务收费'})
        q=checked_request(admin,'/api/service-orders/'+str(sid))['quote']['id'];act2(manager,'approve',{'minimum_fee_cents':500,'allow_below_minimum':False,'reason':'主管独立确认实际咨询价格','evidence_id':proof2(manager,'独立咨询批准')});act2(service,'authorize',{'quote_id':q,'evidence_id':proof2(service,'独立客户咨询授权')})
        act2(service,'fulfill',{'line_key':'consult','result':'顾问实际完成客户咨询并交付资料','evidence_id':proof2(service,'独立咨询实际履约')});act2(finance,'receive',{'amount_cents':500,'account_id':account['id'],'reference':'独立咨询真实到账','evidence_id':proof2(finance,'独立咨询到账','receipt')})
        visit(service,'service-orders/'+str(sid),standalone['title']);assert_fits_mobile(service);screenshots.append(take_screenshot(service,output,'05_standalone_customer_service_mobile.png'))
        assert request(inventory,'/api/service-orders/'+str(cid))['status']==403
        steps.append('服务顾问独立客户服务无虚构外部提交；库管真实员工账号不能读取服务价格与财务原件，五员工独立会话验证')
        assert not errors,errors
        return {'mode':'real-http-chrome','viewport':390,'passed':steps,'javascript_errors':errors,'screenshots':screenshots}
    finally:
        for c in contexts:c.close()

if __name__=='__main__':harness.exercise=exercise;harness.main()
