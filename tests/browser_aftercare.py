"""Five employee roles over actual Chrome HTTP, with synthetic source business."""
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
        login_page(admin,base,'admin',password);employees={};ids={}
        for role in ('sales','service','technician','manager','finance'):
            secret=secrets.token_urlsafe(24);u=checked_request(admin,'/api/users','POST',{'username':'after-'+role,'display_name':'售后验收'+role,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},status=201);ids[role]=u['id']
            p=page();login_page(p,base,'after-'+role,secret);p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24);p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'after-'+role,changed);employees[role]=p
        sales,service,tech,manager,finance=(employees[k] for k in ('sales','service','technician','manager','finance'))
        def post(p,path,values,status=200):return checked_request(p,path,'POST',values,status=status)
        def current_source(row):return checked_request(admin,'/api/flow/cases/'+str(row['id']))
        def source_action(row,key,v):return post(admin,f"/api/flow/cases/{row['id']}/actions/{key}",{'request_id':secrets.token_hex(16),'version':current_source(row)['version'],'values':v})
        def api_upload(case_id,label,category='evidence'):
            r=admin.evaluate('''async({id,label,category})=>{const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];const f=new FormData();f.append('category',category);f.append('file',new Blob([label],{type:'text/plain'}),label+'.txt');const r=await fetch('/api/flow/cases/'+id+'/files',{method:'POST',headers:{'X-CSRF-Token':token,'X-Store-ID':'1'},body:f});return{status:r.status,body:await r.json()};}''',{'id':case_id,'label':label,'category':category});assert r['status']==200,r;return r['body']['id']
        source=post(sales,'/api/flow/cases',{'request_id':secrets.token_hex(16),'kind':'order','values':{'customer_name':'合成售后客户','customer_phone':'13900006100','model':'合成车型','amount':'100.00','delivery_due':date.today().isoformat(),'addon':True,'insurance':True}},201)
        source=source_action(source,'approve',{});children=current_source(source)['children'];addon=next(c for c in children if c['kind']=='addon');insurance=next(c for c in children if c['kind']=='insurance')
        source_action(addon,'service_quote',{'amount':'20.00','work':'已实际完成加装检查服务'});source_action(addon,'service_finish',{'evidence_id':api_upload(addon['id'],'原加装实际完工')})
        source_action(insurance,'service_quote',{'amount':'15.00','insurer':'合成保险公司','commission':'1.00'})
        account=post(admin,'/api/flow/master/accounts',{'values':{'name':'合成售后原收款账户','account_type':'bank','active':True}},201)
        source_action(source,'receive',{'amount':'100.00','account_id':account['id'],'reference':'原订单合成银行流水','evidence_id':api_upload(source['id'],'原车款实际到账','receipt')})
        def visit(p,route,title):
            p.goto(base+'/?visit='+secrets.token_hex(5)+'#'+route);expect(p.locator('#main h1')).to_have_text(title)
        visit(sales,'aftercare','售后纠正');sales.locator('[data-act=aftercare-new]').click();expect(sales.locator('#modal [name=source]')).to_be_visible();sales.locator('#modal [name=source]').select_option(label=next(x for x in sales.locator('#modal [name=source] option').all_text_contents() if source['number'] in x));sales.locator('#modal [name=reason]').fill('客户申请退订；加装已履约保留，保险尚未提交');save_modal(sales)
        rows=checked_request(admin,'/api/aftercare/orders')['items'];row=next(r for r in rows if r['source_case_id']==source['id']);case_id=row['id'];title='已履约退订 · '+row['number'];route='aftercare/'+str(case_id)
        def current():return checked_request(admin,'/api/aftercare/orders/'+str(case_id))
        def refresh(p):visit(p,route,title)
        def task(key,role):
            t=next(t for t in checked_request(admin,'/api/flow/cases/'+str(case_id))['tasks'] if t['key']==key and t['status']=='open')
            if t['assignee_id']!=ids[role]:post(admin,'/api/flow/tasks/'+str(t['id'])+'/assign',{'version':t['version'],'assignee_id':ids[role],'reason':'合成五岗位明确交接'})
        def select(p,name,value):p.locator('#modal [name='+name+']').select_option(str(value))
        def upload(p,label,category='evidence'):
            p.locator('[data-act=upload]').click();select(p,'category',category);p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('合成实际凭据 '+label).encode()});save_modal(p);expect(p.locator('#main')).to_contain_text(label+'.txt')
            return next(f['id'] for f in checked_request(admin,'/api/flow/cases/'+str(case_id))['files'] if f['name']==label+'.txt')
        links={s['kind']:s for s in row['sources']};task('aftercare_execution_'+str(links['addon']['id']),'technician');refresh(tech)
        assert all('net_cents' not in s for s in checked_request(tech,'/api/aftercare/orders/'+str(case_id))['sources'])
        fid=upload(tech,'加装实际完工核对');tech.locator('[data-act=aftercare-action][data-key=execution][data-id="'+str(links['addon']['id'])+'"]').click();select(tech,'outcome','尚未执行');select(tech,'external_result','无需外部终止');tech.locator('#modal [name=result]').fill('声明未经执行应被后台拒绝');select(tech,'evidence_id',fid);tech.locator('#modal button[type=submit]').click();expect(tech.locator('#modal .formerror')).to_contain_text('不能声明从未执行');assert_fits_mobile(tech);screenshots.append(take_screenshot(tech,output,'01_aftercare_executed_service_refusal.png'))
        select(tech,'outcome','已经完成履约');tech.locator('#modal [name=result]').fill('本人核对原加装确已履约，保留实际费用');save_modal(tech);steps.append('技师无法查看价格；原完工事实阻止谎报未执行，核对本服务实际履约')
        task('aftercare_execution_'+str(links['insurance']['id']),'service');refresh(service);fid=upload(service,'保险未提交外部核对');service.locator('[data-act=aftercare-action][data-key=execution][data-id="'+str(links['insurance']['id'])+'"]').click();select(service,'outcome','尚未执行');select(service,'external_result','无需外部终止');service.locator('#modal [name=result]').fill('本人核对保险尚未提交，未生成保单');select(service,'evidence_id',fid);save_modal(service);steps.append('服务顾问核对关联保险尚未实际办理，不伪造外部退保')
        task('aftercare_plan','sales');refresh(sales);sales.locator('[data-key=plan][data-act=aftercare-action]').click()
        for kind,value in [('order','100.00'),('addon','0.00'),('insurance','15.00')]:
            el=sales.locator('[data-aftercare-line][data-id="'+str(links[kind]['id'])+'"]');el.locator('[name=credit]').fill(value)
        sales.locator('[data-aftercare-line][data-id="'+str(links['order']['id'])+'"] [name=units]').fill('100.00');sales.locator('#modal [name=commission]').fill('1.00');sales.locator('#modal [name=reason]').fill('整车原车款退回；已履约加装二十元保留另收；保险保费与预计佣金分别减免');assert_fits_mobile(sales);screenshots.append(take_screenshot(sales,output,'02_aftercare_frozen_source_plan_mobile.png'));save_modal(sales)
        task('aftercare_approve','manager');refresh(manager);fid=upload(manager,'本次主管独立方案核对','authorization');manager.locator('[data-key=approve][data-act=aftercare-action]').click();manager.locator('#modal [name=reason]').fill('核对保留费与原现金上限，明确同意当前版本');select(manager,'evidence_id',fid);save_modal(manager)
        task('aftercare_consent','sales');refresh(sales);fid=upload(sales,'客户同意本次退订保留费及原款方案','authorization');sales.locator('[data-key=customer_confirm][data-act=aftercare-action]').click();select(sales,'evidence_id',fid);save_modal(sales);steps.append('销售冻结三原单保留费与原路金额；主管和客户使用各自当前方案凭据')
        assert request(tech,'/api/flow/files/'+str(fid))['status']==403
        task('aftercare_apply','finance');refresh(finance);fid=upload(finance,'费用纠正与退回前置事实核对','receipt');finance.locator('[data-key=apply][data-act=aftercare-action]').click();select(finance,'evidence_id',fid);save_modal(finance);assert current()['applied']
        r=current();t=r['plans'][-1]['returns'][0];task('aftercare_refund_'+str(t['id']),'finance');refresh(finance);fid=upload(finance,'第一笔实际原路退款','receipt');finance.locator('[data-key=refund][data-act=aftercare-action]').click();finance.locator('#modal [name=amount]').fill('101.00');select(finance,'account_id',account['id']);finance.locator('#modal [name=reference]').fill('实际退款第一笔');select(finance,'evidence_id',fid);finance.locator('#modal button[type=submit]').click();expect(finance.locator('#modal .formerror')).to_contain_text('退款超过');assert_fits_mobile(finance);screenshots.append(take_screenshot(finance,output,'03_aftercare_original_cash_cap_mobile.png'))
        finance.locator('#modal [name=amount]').fill('60.00');save_modal(finance);refresh(finance);fid=upload(finance,'第二笔实际原路退款','receipt');finance.locator('[data-key=refund][data-act=aftercare-action]').click();select(finance,'account_id',account['id']);finance.locator('#modal [name=reference]').fill('实际退款第二笔');select(finance,'evidence_id',fid);save_modal(finance)
        task('aftercare_collect_'+str(links['addon']['id']),'finance');refresh(finance);fid=upload(finance,'原加装保留费实际到账','receipt');finance.locator('[data-key=collect][data-act=aftercare-action]').click();select(finance,'account_id',account['id']);finance.locator('#modal [name=reference]').fill('加装保留费实际到账');select(finance,'evidence_id',fid);save_modal(finance);refresh(finance);assert_fits_mobile(finance);screenshots.append(take_screenshot(finance,output,'04_aftercare_cash_and_retained_fee_complete.png'))
        r=current();assert r['state']=='completed' and all(s['refund_cents']==s['due_cents']==0 for s in r['sources']);assert current_source(source)['state']=='executing';assert sum(x['amount_cents'] for x in r['refunds'])==10000
        steps.append('财务实际分两笔原账户退满原款，超额拒绝；另收原加装保留费，原销售状态和原收款仍保留')
        assert not errors,errors
        return {'mode':'real-http-chrome','viewport':390,'passed':steps,'javascript_errors':errors,'screenshots':screenshots}
    finally:
        for context in contexts:context.close()

if __name__=='__main__':harness.exercise=exercise;harness.main()
