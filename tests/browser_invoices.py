"""Actual finance/manager mobile workflow with uploads, failure, blue/red results and CSV."""
from pathlib import Path
import json,secrets,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import browser_huakangos as harness
from playwright.sync_api import expect


def exercise(browser,base,password,output):
    contexts=[];steps=[];screenshots=[];errors=[];req=harness.checked_request
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(context)
        p=context.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440);finance=page();manager=page()
    def upload(p,cid,category='evidence'):
        case=req(p,f'/api/flow/cases/{cid}');harness.navigate(p,f'case/{cid}',case['title'])
        p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category)
        p.locator('#modal [name=file]').set_input_files({'name':'合成发票协同.txt','mimeType':'text/plain','buffer':'纯虚构发票与办理结果，用于内部测试'.encode()})
        harness.save_modal(p);return req(p,f'/api/flow/cases/{cid}')['files'][0]['id']
    def navigate(p,row):harness.navigate(p,'invoices/'+str(row['id']),'开票申请' if row['direction']=='blue' else '原票冲红')
    def modal(p,key,values):
        p.locator(f'[data-act=invoice-action][data-key={key}]').click()
        for name,value in values.items():
            el=p.locator('#modal [name='+name+']')
            if el.evaluate('(x)=>x.tagName')=='SELECT':el.select_option(str(value))
            else:el.fill(str(value))
        harness.assert_fits_mobile(p);harness.save_modal(p)
    try:
        harness.login_page(admin,base,'admin',password)
        for name,role,p in [('finance','finance',finance),('manager','manager',manager)]:
            secret=secrets.token_urlsafe(24)
            req(admin,'/api/users','POST',{'username':'invoice-'+name,'display_name':'发票验收'+name,'role':role,'password':secret,
                'store_roles':[{'store_id':1,'role':role}]},status=201)
            harness.login_page(p,base,'invoice-'+name,secret);p.locator('#modal [name=current_password]').fill(secret)
            changed=secrets.token_urlsafe(24);p.locator('#modal [name=new_password]').fill(changed);harness.save_modal(p)
            harness.login_page(p,base,'invoice-'+name,changed)
        source=harness.create_repair_source(admin,1)['case']
        harness.navigate(finance,'invoices','开票与原票冲红');finance.locator(f'[data-act=invoice-new][data-source="{source["id"]}"]').click()
        for name,value in {'amount':'100.00','issuer_name':'合成开票主体甲','issuer_tax_id':'TEST00000000000001','buyer_name':'合成购买方','reason':'已核对原维修确认金额'}.items():finance.locator('#modal [name='+name+']').fill(value)
        harness.save_modal(finance);expect(finance.locator('#main h1')).to_have_text('开票申请')
        row=req(finance,'/api/invoices/orders')['items'][0];assert row['state']=='approval'
        fid=upload(manager,row['id']);navigate(manager,row);modal(manager,'approve',{'evidence_id':fid,'reason':'另一位主管复核原单和抬头'})
        steps.append('财务手机建立100元蓝票申请，另一位店长用本人账号核对原单和抬头后批准')
        fid=upload(finance,row['id']);navigate(finance,row)
        modal(finance,'submit',{'reference':'BROWSER-EXTERNAL-1','evidence_id':fid,'reason':'实际已提交外部办理'})
        expect(finance.locator('#main')).to_contain_text('外部办理中')
        modal(finance,'difference',{'external_number':'OUTSIDE-PENDING','observed_amount':'101.00','evidence_id':fid,'reason':'外部待核对金额不一致'})
        expect(finance.locator('#main')).to_contain_text('101.00')
        modal(finance,'failure',{'evidence_id':fid,'reason':'外部已撤销错误结果，本次未开票'})
        modal(finance,'submit',{'reference':'BROWSER-EXTERNAL-2','evidence_id':fid,'reason':'核对后重新办理'})
        screenshots.append(harness.take_screenshot(finance,output,'01_invoice_external_failure_retry.png'))
        fid=upload(finance,row['id'],'invoice');navigate(finance,row)
        modal(finance,'record',{'invoice_number':'BROWSER-BLUE-100','amount':'100.00','evidence_id':fid,'reason':'实际蓝票100元已核对'})
        expect(finance.locator('#main')).to_contain_text('BROWSER-BLUE-100');harness.assert_fits_mobile(finance)
        screenshots.append(harness.take_screenshot(finance,output,'02_invoice_actual_blue.png'))
        steps.append('外部差异和失败保留记录；重办后上传发票类别文件，实际蓝票仅登记一次')
        finance.locator('[data-act=invoice-red]').click();finance.locator('#modal [name=amount]').fill('30.00');finance.locator('#modal [name=reason]').fill('按原票办理部分冲红并保留70元')
        harness.save_modal(finance);expect(finance.locator('#main h1')).to_have_text('原票冲红')
        red=req(finance,'/api/invoices/orders')['items'][0];assert red['original_case_id']==row['id'] and red['balance']['available_cents']==0
        fid=upload(manager,red['id']);navigate(manager,red);modal(manager,'approve',{'evidence_id':fid,'reason':'核对原蓝票及部分冲红'})
        fid=upload(finance,red['id']);navigate(finance,red);modal(finance,'submit',{'reference':'BROWSER-RED-SUBMIT','evidence_id':fid,'reason':'原票冲红实际已申请'})
        fid=upload(finance,red['id'],'invoice');navigate(finance,red);modal(finance,'record',{'invoice_number':'BROWSER-RED-30','amount':'30.00','evidence_id':fid,'reason':'实际红票30元已核对'})
        expect(finance.locator('#main')).to_contain_text('70.00');harness.assert_fits_mobile(finance)
        screenshots.append(harness.take_screenshot(finance,output,'03_invoice_partial_red.png'))
        report=req(finance,'/api/flow/analytics');assert report['metrics']['invoice_net_cents']==7000 and report['metrics']['cash_in_cents']==0
        harness.navigate(finance,'table/invoices','期间专用发票协同实际结果')
        with finance.expect_download() as event:finance.locator('[data-act=exporttable]').click()
        event.value.save_as(output/'synthetic_invoice_results.csv')
        text=(output/'synthetic_invoice_results.csv').read_text(encoding='utf-8-sig');assert 'BROWSER-BLUE-100' in text and 'BROWSER-RED-30' in text
        steps.append('原票部分冲红30元后净票额70元，现金为0；真实下载CSV与蓝红票明细一致')
        two=req(admin,'/api/stores','POST',{'code':'INVOICE-B','name':'合成隔离票据乙店'},status=201)['id']
        assert req(admin,'/api/invoices/orders',store=two)['total']==0
        assert not errors,errors
        return {'mode':'real Chromium mobile HTTP','passed':len(steps),'steps':steps,'screenshots':screenshots,'javascript_errors':errors,
            'limitations':['只登记合成外部票据；无税务平台直连、真实开票或公司经营主体审核。']}
    except Exception:harness.take_screenshot(finance,output,'failure.png');raise
    finally:
        for context in contexts:context.close()


if __name__=='__main__':harness.exercise=exercise;harness.main()
