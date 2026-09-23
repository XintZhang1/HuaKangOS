"""Real employee Chrome HTTP commission invoices and original red results at 390px."""
from pathlib import Path
from datetime import date,timedelta
import secrets,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import browser_huakangos as harness
from playwright.sync_api import expect


def exercise(browser,base,password,output):
    contexts=[];errors=[];screens=[];steps=[];req=harness.checked_request
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(context)
        p=context.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440);finance=page();manager=page()
    def post(p,path,values,status=200):return req(p,path,'POST',values,status=status)
    def upload(p,cid,label,category='evidence'):
        row=req(p,f'/api/flow/cases/{cid}');harness.navigate(p,f'case/{cid}',row['title'])
        p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category)
        p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('仅供合成验收 '+label+' '+secrets.token_hex(8)).encode()})
        harness.save_modal(p);return req(p,f'/api/flow/cases/{cid}')['files'][0]['id']
    try:
        harness.login_page(admin,base,'admin',password)
        for role,p in [('finance',finance),('manager',manager)]:
            secret=secrets.token_urlsafe(24)
            post(admin,'/api/users',{'username':'commission-'+role,'display_name':'佣金验收'+role,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},201)
            harness.login_page(p,base,'commission-'+role,secret)
            p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24)
            p.locator('#modal [name=new_password]').fill(changed);harness.save_modal(p)
            harness.login_page(p,base,'commission-'+role,changed)
        customer=post(admin,'/api/flow/master/customers',{'values':{'name':'虚构佣金客户','phone':'13900009323','contact_allowed':True,'note':'原保费并非门店收入','confirm_new_customer':True}},201)
        cv=post(admin,'/api/customer-service/vehicles',{'request_id':secrets.token_hex(16),'values':{'customer_id':customer['id'],'vin':'LTEST000000009323','plate':'虚构A323','model_name':'虚构车型','source_reference':'仅供合成原VIN核对','confirmed':True}},201)['vehicle']
        insurer=post(admin,'/api/masters/insurers',{'request_id':secrets.token_hex(16),'values':{'code':'COMMISSION-INS','name':'合成保险公司','license_number':'SYNTHETIC-ONLY','settlement_days':30}},201)
        row=post(admin,'/api/insurance-orders',{'request_id':secrets.token_hex(16),'customer_id':customer['id'],'customer_vehicle_id':cv['id'],'due_date':date.today().isoformat(),'reason':'虚构保险委托，核对佣金发票'},201);cid=row['id']
        def ins(p,key,values):
            fresh=req(p,f'/api/insurance-orders/{cid}')
            return post(p,f'/api/insurance-orders/{cid}/actions/{key}',{'request_id':secrets.token_hex(16),'version':fresh['version'],'values':values})
        row=ins(admin,'quote',{'insurer_id':insurer['id'],'insurer_version':insurer['version'],'collection_mode':'customer_direct','payee_account_name':'','payee_account_reference':'','lines':[{'name':'商业险','premium_cents':10001}],'expected_commission_cents':999,'start_date':date.today().isoformat(),'end_date':(date.today()+timedelta(days=365)).isoformat(),'valid_until':(date.today()+timedelta(days=7)).isoformat(),'terms':'客户直付原保费；佣金须另行实际确认','reason':'核对本版保险报价'})
        ins(manager,'review',{'decision':'approved','reason':'另一主管独立核对原报价','evidence_id':upload(manager,cid,'原保险独立核价','authorization')})
        ins(admin,'authorize',{'quote_id':row['quote']['id'],'digest':row['quote']['digest'],'evidence_id':upload(admin,cid,'客户原版保险授权','authorization')})
        row=ins(admin,'submit',{'external_reference':'SYNTHETIC-COMMISSION-SUBMIT','business_date':date.today().isoformat(),'evidence_id':upload(admin,cid,'外部实际提交原件','authorization')})
        ins(admin,'result',{'submission_id':row['submissions'][-1]['id'],'outcome':'issued','policy_number':'SYNTHETIC-COMMISSION-POLICY','result':'实际保险公司出保合成样本','business_date':date.today().isoformat(),'evidence_id':upload(admin,cid,'实际出保原件','authorization')})
        def confirm(amount,label):
            proposal=ins(finance,'commission',{'target_cents':amount,'reason':label,'evidence_id':upload(finance,cid,label+'原件','receipt')})
            return ins(manager,'commission_review',{'confirmation_id':proposal['commissions'][-1]['id'],'decision':'approved','reason':'另一主管核对'+label,'business_date':date.today().isoformat(),'evidence_id':upload(manager,cid,label+'独立批准','receipt')})
        confirm(501,'原实际佣金5.01元')
        current=req(finance,f'/api/insurance-orders/{cid}')
        harness.navigate(finance,f'insurance-orders/{cid}',current['title'])
        finance.locator('[data-act=invoice-new]').click()
        expect(finance.locator('#modal [name=buyer_name]')).to_have_value('合成保险公司')
        expect(finance.locator('#modal')).to_contain_text('客户保费不计入')
        for name,value in {'amount':'5.01','issuer_name':'合成门店经营主体','issuer_tax_id':'TEST00000000000001','buyer_tax_id':'TESTINSURER000001','reason':'开具已独立确认的实际佣金'}.items():finance.locator('#modal [name='+name+']').fill(value)
        harness.assert_fits_mobile(finance);finance.locator('#modal').evaluate('(e)=>e.scrollTop=0');screens.append(harness.take_screenshot(finance,output,'01_commission_invoice_basis.png'))
        harness.save_modal(finance);expect(finance.locator('#main h1')).to_have_text('开票申请')
        blue=req(finance,'/api/invoices/orders')['items'][0]
        def nav(p,r):harness.navigate(p,'invoices/'+str(r['id']),'开票申请' if r['direction']=='blue' else '原票冲红')
        def action(p,r,key,values):
            nav(p,r);p.locator(f'[data-act=invoice-action][data-key={key}]').click()
            for name,value in values.items():
                el=p.locator('#modal [name='+name+']')
                if el.evaluate('(e)=>e.tagName')=='SELECT':el.select_option(str(value))
                else:el.fill(str(value))
            harness.assert_fits_mobile(p);harness.save_modal(p)
        def actual(r,amount,label):
            action(manager,r,'approve',{'reason':'独立复核'+label,'evidence_id':upload(manager,r['id'],label+'审批')})
            action(finance,r,'submit',{'reference':'SYNTHETIC-'+label,'reason':'本人已提交外部办理','evidence_id':upload(finance,r['id'],label+'提交')})
            action(finance,r,'record',{'invoice_number':'SYNTHETIC-'+label,'amount':amount,'reason':'对照外部实际票据核对','evidence_id':upload(finance,r['id'],label+'实际票据','invoice')})
            return req(finance,'/api/invoices/orders/'+str(r['id']))
        blue=actual(blue,'5.01','COMMISSION-BLUE')
        screens.append(harness.take_screenshot(finance,output,'02_actual_commission_blue.png'))
        steps.append('财务从原保险进入佣金开票，默认原保险公司抬头；另一主管批准，实际蓝票5.01元，原100.01元保费不占开票额度')
        confirm(200,'实际佣金降低到2元');nav(finance,blue)
        expect(finance.locator('#main')).to_contain_text('3.01')
        finance.locator('[data-act=invoice-red]').click();finance.locator('#modal [name=amount]').fill('3.01');finance.locator('#modal [name=reason]').fill('佣金实际降低，关联原蓝票冲红差额');harness.save_modal(finance)
        red=req(finance,'/api/invoices/orders')['items'][0];red=actual(red,'3.01','COMMISSION-RED')
        assert red['balance']['actual_net_cents']==200 and red['balance']['correction_cents']==0
        screens.append(harness.take_screenshot(finance,output,'03_commission_original_red.png'))
        report=req(finance,'/api/flow/analytics');assert report['metrics']['invoice_net_cents']==200 and report['metrics']['cash_in_cents']==0
        harness.navigate(finance,'table/invoices','期间专用发票协同实际结果')
        with finance.expect_download() as event:finance.locator('[data-act=exporttable]').click()
        event.value.save_as(output/'synthetic-commission-invoices.csv')
        text=(output/'synthetic-commission-invoices.csv').read_text(encoding='utf-8-sig')
        assert 'SYNTHETIC-COMMISSION-BLUE' in text and 'SYNTHETIC-COMMISSION-RED' in text
        steps.append('原佣金降到2元后自动出现差额核对；原蓝票冲红3.01元，净票额2元，开票/冲红均不产生现金；真实CSV下载与原票一致')
        other=post(admin,'/api/stores',{'code':'COMMISSION-B','name':'合成隔离乙店'},201)['id']
        assert req(admin,'/api/invoices/orders',store=other)['total']==0
        assert not errors,errors
        return {'status':'passed','mode':'real-Windows-Chrome-HTTP','viewport':'390x844','synthetic_only':True,'steps':steps,'screenshots':screens,'javascript_errors':errors,'net_invoice_cents':200,'cash_in_cents':0}
    finally:
        for context in contexts:context.close()


if __name__=='__main__':harness.exercise=exercise;harness.main()
