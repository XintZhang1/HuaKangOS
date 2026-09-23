"""Real HTTP Chrome at 390px: staff attestation, original premium and commission."""
import secrets
from datetime import date,timedelta
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request,login_page,save_modal,assert_fits_mobile

def take_screenshot(page,output,filename):
    path=output/filename
    page.screenshot(path=str(path),full_page=False)
    return str(path)

def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screens=[]
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(context);p=context.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440)
    try:
        login_page(admin,base,'admin',password)
        def post(p,path,values,status=200):return checked_request(p,path,'POST',values,status=status)
        employees={}
        for role in ('sales','manager','finance'):
            secret=secrets.token_urlsafe(24);post(admin,'/api/users',{'username':'ins-'+role,'display_name':'保险验收'+{'sales':'销售','manager':'店长','finance':'财务'}[role],'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},201)
            p=page();login_page(p,base,'ins-'+role,secret);p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24);p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'ins-'+role,changed);employees[role]=p
        sales,manager,finance=[employees[k] for k in ('sales','manager','finance')]
        customer=post(sales,'/api/flow/master/customers',{'values':{'name':'合成保险客户','phone':'13900009221','contact_allowed':True,'note':'仅合成验收','confirm_new_customer':True}},201)
        cv=post(sales,'/api/customer-service/vehicles',{'request_id':secrets.token_hex(16),'values':{'customer_id':customer['id'],'vin':'LTEST000000000922','plate':'合成A922','model_name':'合成客户车型','source_reference':'合成客户实际提供VIN','confirmed':True}},201)['vehicle']
        insurer=post(admin,'/api/masters/insurers',{'request_id':secrets.token_hex(16),'values':{'code':'BROWSER-INS','name':'合成保险公司','license_number':'SYNTHETIC-INS-ONLY','settlement_days':30}},201)
        account=post(admin,'/api/flow/master/accounts',{'values':{'name':'合成保险原款账户','account_type':'bank','active':True}},201)
        sales.goto(base+'/?visit='+secrets.token_hex(5)+'#insurance-orders');expect(sales.locator('#main h1')).to_have_text('保险核价与结算');sales.locator('[data-act=insurance-new]').click();sales.locator('#modal [name=customer]').select_option(str(customer['id']));sales.locator('#modal button[type=submit]').click();expect(sales.locator('#modal [name=vehicle]')).to_be_visible();sales.locator('#modal [name=vehicle]').select_option(label=str(cv['id'])+' · '+cv['vin']+' · '+cv['plate']);sales.locator('#modal [name=reason]').fill('客户委托门店独立核价代缴保险');save_modal(sales)
        row=checked_request(sales,'/api/insurance-orders')['rows'][0];cid=row['id'];route='insurance-orders/'+str(cid)
        def current():return checked_request(admin,'/api/insurance-orders/'+str(cid))
        def refresh(p):p.goto(base+'/?visit='+secrets.token_hex(5)+'#'+route);expect(p.locator('#main h1')).to_have_text(row['title'])
        def action(p,key,**extra):
            selector='[data-act=insurance-action][data-key='+key+']'+''.join('[data-'+k+'="'+str(v)+'"]' for k,v in extra.items());p.locator(selector).click();expect(p.locator('#modal')).to_be_visible()
        def select(p,name,value):p.locator('#modal [name='+name+']').select_option(str(value))
        def upload(p,label,financial=False):
            p.locator('[data-act=upload]').click();select(p,'category','receipt' if financial else 'authorization');p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('合成实际原件 '+label).encode()});save_modal(p)
            return next(f['id'] for f in checked_request(admin,'/api/flow/cases/'+str(cid))['files'] if f['name']==label+'.txt')
        def simple(p,key,label,financial=False,**extra):
            refresh(p);fid=upload(p,label,financial);action(p,key,**extra);select(p,'evidence_id',fid);return fid
        refresh(sales);action(sales,'quote');select(sales,'insurer',insurer['id']);lines=sales.locator('[data-insurance-line]');lines.nth(0).locator('[name=line_name]').fill('交强险');lines.nth(0).locator('[name=line_amount]').fill('30.00');lines.nth(1).locator('[name=line_name]').fill('商业险');lines.nth(1).locator('[name=line_amount]').fill('70.01');sales.locator('#modal [name=expected]').fill('5.01');sales.locator('#modal [name=payee]').fill('合成保险公司收款户');sales.locator('#modal [name=payee_reference]').fill('SYNTHETIC-INSURER-ACCOUNT');sales.locator('#modal [name=end]').fill((date.today()+timedelta(days=365)).isoformat());sales.locator('#modal [name=terms]').fill('合成客户按本版核对险种；真实退保依据保险公司批单另行核对。');sales.locator('#modal [name=reason]').fill('依据本次保险公司实际报价');assert_fits_mobile(sales);sales.locator('#modal').evaluate('(e)=>e.scrollTop=0');screens.append(take_screenshot(sales,output,'01_insurance_frozen_quote_mobile.png'));save_modal(sales)
        simple(manager,'review','独立主管本版核价原件');manager.locator('#modal [name=reason]').fill('另一主管核对险种保费和缴费户');save_modal(manager)
        simple(sales,'authorize','客户当前版险种授权');save_modal(sales)
        def cash_action(key,amount,label,refuse=None,**extra):
            simple(finance,key,label,True,**extra);finance.locator('#modal [name=amount]').fill(amount);select(finance,'account_id',account['id']);finance.locator('#modal [name=reference]').fill(label+'独立流水')
            if refuse:
                finance.locator('#modal button[type=submit]').click();expect(finance.locator('#modal .formerror')).to_contain_text(refuse);assert_fits_mobile(finance);screens.append(take_screenshot(finance,output,'02_insurance_original_cash_refusal.png'));finance.locator('#modal [data-act=close]').last.click();return
            save_modal(finance)
        cash_action('receive','100.01','客户原保费实际到账');tender=current()['tenders'][0]['id'];cash_action('disburse','100.01','原保费实际代缴',tender=tender)
        simple(sales,'submit','首次投保提交');sales.locator('#modal [name=external_reference]').fill('合成实际受理号-1');save_modal(sales)
        simple(sales,'result','保险公司实际补件要求');select(sales,'outcome','需要补件');sales.locator('#modal [name=result]').fill('须补客户真实投保资料，尚未出保');save_modal(sales)
        simple(sales,'submit','按原单实际补件');sales.locator('#modal [name=external_reference]').fill('合成实际受理号-2');save_modal(sales)
        simple(sales,'result','保险公司实际出保');select(sales,'outcome','实际出保');sales.locator('#modal [name=policy_number]').fill('SYNTHETIC-POLICY-922');sales.locator('#modal [name=result]').fill('本人对照保险公司真实保单确认出保');save_modal(sales)
        def confirmed(amount,label):
            simple(finance,'commission',label+'结算原件',True);finance.locator('#modal [name=target]').fill(amount);finance.locator('#modal [name=reason]').fill(label+'：累计实际应得佣金');save_modal(finance)
            confirmation=current()['commissions'][-1]['id'];simple(manager,'commission_review',label+'主管独立复核',True,confirmation=confirmation);manager.locator('#modal [name=reason]').fill('另一主管核对保险公司累计实际结算');save_modal(manager);return confirmation
        confirmation=confirmed('5.01','首次实际佣金');cash_action('commission_receive','5.01','实际佣金到账',confirmation=confirmation);assert current()['state']=='completed'
        refresh(finance);finance.locator('section').filter(has=finance.get_by_role('heading',name='实际佣金结算',exact=True)).scroll_into_view_if_needed();assert_fits_mobile(finance);screens.append(take_screenshot(finance,output,'03_insurance_actual_premium_commission.png'));steps.append('销售手机逐险种报价、另一店长批准、客户本版授权；财务实际代收并按原资金代缴，销售记录补件和真实出保，预计佣金不产生收入或现金')
        refresh(sales);fid=upload(sales,'保险公司真实退保与保留保费');action(sales,'termination');sales.locator('#modal [name=retained]').fill('20.00');sales.locator('[data-insurance-return="'+str(tender)+'"] input').fill('80.01');sales.locator('#modal [name=reason]').fill('客户与保险公司确认实际退保，保留保费20元');select(sales,'evidence_id',fid);save_modal(sales);plan=current()['plans'][-1]['id']
        simple(manager,'termination_review','撤保独立复核',plan=plan);manager.locator('#modal [name=reason]').fill('独立核对真实退保批单与原客户款');save_modal(manager);simple(sales,'termination_consent','客户本版撤保同意',plan=plan);save_modal(sales);simple(finance,'termination_apply','批准撤保金额实际生效',True,plan=plan);save_modal(finance)
        cash_action('refund','80.01','尚未追回不得先退款',refuse='可退额度不足',plan=plan,tender=tender)
        cash_action('insurer_return','80.01','保险公司实退原款',original=current()['pass_entries'][0]['id']);cash_action('refund','80.01','客户原保费实退',plan=plan,tender=tender)
        steps.append('真实退保经另一店长与客户本版同意；保险公司尚未回款时拒绝客户退款，实际追回后才按原账户退80.01元')
        confirmation=confirmed('1.00','退保后实际佣金');cash_action('commission_return','4.01','原佣金实际退回',confirmation=confirmation,original=current()['commission_payments'][0]['id'])
        final=current();assert final['state']=='completed' and final['summary']['customer_paid_cents']==final['summary']['insurer_paid_cents']==2000 and final['summary']['actual_commission_cents']==100
        refresh(finance);finance.locator('section').filter(has=finance.get_by_role('heading',name='撤保方案第 1 版',exact=True)).scroll_into_view_if_needed();assert_fits_mobile(finance);screens.append(take_screenshot(finance,output,'04_insurance_original_returns_and_commission.png'));steps.append('实际佣金先独立确认为5.01元再到账；退保重新确认累计1元，财务按原佣金账户实际退4.01元，原保费与佣金全部逐笔守恒')
        assert not errors,errors
        return dict(mode='real_http_chrome',viewport='390x844',checks_passed=len(steps),steps=steps,screenshots=screens,javascript_errors=errors,net_commission_cents=100,file_scan_mode='structure_only')
    finally:
        for context in contexts:context.close()

if __name__=='__main__':harness.exercise=exercise;harness.main()
