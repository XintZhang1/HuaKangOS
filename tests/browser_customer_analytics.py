"""Employee mobile graphs, customer drilldown and real CSV download over HTTP."""
from pathlib import Path
import secrets,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import browser_huakangos as harness
from playwright.sync_api import expect


def exercise(browser,base,password,output):
    contexts=[];errors=[];screenshots=[];steps=[];req=harness.checked_request
    def page(width):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(context)
        p=context.new_page();p.on('pageerror',lambda error:errors.append(str(error)));return p
    admin=page(1440);finance=page(390)
    try:
        harness.login_page(admin,base,'admin',password)
        source=harness.create_repair_source(admin,1);row=source['case']
        for action,values in [('credit',{'due_date':row['due_date'],'reason':'合成客户已获月结授权'}),('release',{'evidence_id':source['evidence_id']})]:
            row=req(admin,f'/api/flow/cases/{row["id"]}')
            row=req(admin,f'/api/flow/cases/{row["id"]}/actions/{action}','POST',{'request_id':secrets.token_hex(16),'version':row['version'],'values':values})
        req(admin,'/api/customer-service/vehicles','POST',{'request_id':secrets.token_hex(16),'values':{'customer_id':row['customer_id'],'vin':'LFV2A21K9J1234567',
            'plate':'合成A1001','model_name':'合成验证车型','source_reference':'当面核对合成车辆资料','confirmed':True}},status=201)
        secret=secrets.token_urlsafe(24)
        req(admin,'/api/users','POST',{'username':'analysis-finance','display_name':'统计验收财务','role':'finance','password':secret,'store_roles':[{'store_id':1,'role':'finance'}]},status=201)
        harness.login_page(finance,base,'analysis-finance',secret)
        finance.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24)
        finance.locator('#modal [name=new_password]').fill(changed);harness.save_modal(finance);harness.login_page(finance,base,'analysis-finance',changed)
        harness.navigate(finance,'analytics/customers','数据可视化')
        harness.assert_fits_mobile(finance);screenshots.append(harness.take_screenshot(finance,output,'01_customer_mobile_analysis.png'))
        data=req(finance,'/api/flow/analytics');summary=data['tables']['customer_value']['rows'][0]
        assert summary['amount_cents']==10000 and data['tables']['customer_vehicle_stats']['rows'][0]['route'] is None
        harness.navigate(finance,'customer-value/'+summary['customer_key'],'客户业务 · '+summary['values'][1])
        harness.assert_fits_mobile(finance);expect(finance.locator('#main')).to_contain_text('100.00')
        screenshots.append(harness.take_screenshot(finance,output,'02_customer_source_drilldown.png'))
        with finance.expect_download() as event:finance.locator('[data-act=customer-value-export]').click()
        event.value.save_as(output/'synthetic_customer_details.csv')
        text=(output/'synthetic_customer_details.csv').read_text(encoding='utf-8-sig');assert row['number'] in text and '100.00' in text
        steps.append('财务手机查看当前车型统计和客户业务，按共享身份进入原单明细，实际下载本客户CSV一致')
        finance.locator('[data-route="case/'+str(row['id'])+'"]').click();expect(finance.locator('#main h1')).to_have_text(row['title'])
        harness.navigate(finance,'table/business_net_facts','期间已记录业务净额明细');harness.assert_fits_mobile(finance)
        screenshots.append(harness.take_screenshot(finance,output,'03_business_fact_basis.png'))
        steps.append('业务净额明细与原维修接车事实相符；现金为零、应收100元，财务没有客户车辆隐私历史入口')
        assert data['metrics']['cash_in_cents']==0 and data['metrics']['receivable_cents']==10000
        assert not errors,errors
        return {'mode':'real Chromium mobile HTTP','passed':len(steps),'steps':steps,'screenshots':screenshots,'javascript_errors':errors}
    except Exception:harness.take_screenshot(finance,output,'failure.png');raise
    finally:
        for context in contexts:context.close()


if __name__=='__main__':harness.exercise=exercise;harness.main()
