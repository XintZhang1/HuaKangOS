"""Actual mobile employee views and CSV download for period stock reconstruction."""
from pathlib import Path
from datetime import date,timedelta
import json,secrets,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import browser_huakangos as harness
from playwright.sync_api import expect


def exercise(browser,base,password,output):
    steps=[];screenshots=[];errors=[]
    contexts=[browser.new_context(viewport={'width':390,'height':844},locale='zh-CN') for _ in range(2)]
    admin,employee=[c.new_page() for c in contexts];req=harness.checked_request
    for page in (admin,employee):page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        harness.login_page(admin,base,'admin',password)
        source={'opening_date':(date.today()-timedelta(days=10)).isoformat(),'source_reference':'浏览器合成期初清单',
                'items':[{'sku':'BROWSER-STOCK','name':'手机验收物资','unit':'件','opening_quantity_milli':2500,
                          'opening_value_cents':503,'source_reference':'合成盘点第1行'}]}
        batch=req(admin,'/api/masters/opening/preflight','POST',{'request_id':secrets.token_hex(16),'source_text':json.dumps(source,ensure_ascii=False)})['batch']
        def review(action,batch):
            body={'request_id':secrets.token_hex(16),'version':batch['version'],'digest':batch['source_digest']}
            if action=='confirm':body.update(confirmed=True,expected_totals=batch['totals'])
            return req(admin,f"/api/masters/opening/{batch['id']}/{action}",'POST',body)['batch']
        batch=review('trial',batch);review('confirm',batch)
        initial=secrets.token_urlsafe(24)
        req(admin,'/api/users','POST',{'username':'stock-reader','display_name':'物资报表验收库管','password':initial,
            'role':'inventory','store_roles':[{'store_id':1,'role':'inventory'}],'can_group_summary':False},status=201)
        harness.navigate(admin,'stock-period','物资期间入出存')
        admin.locator('#datefilters [name=date_from]').fill((date.today()-timedelta(days=5)).isoformat())
        admin.locator('#datefilters [name=date_to]').fill((date.today()-timedelta(days=2)).isoformat())
        admin.locator('#datefilters button[type=submit]').click();expect(admin.locator('svg')).to_be_visible()
        expect(admin.locator('#main')).to_contain_text('5.03');expect(admin.locator('#main')).to_contain_text('来源与当前库存一致')
        harness.assert_fits_mobile(admin);screenshots.append(harness.take_screenshot(admin,output,'01_stock_period_value.png'))
        with admin.expect_download() as event:admin.locator('[data-act=stock-period-export]').click()
        downloaded=event.value;downloaded.save_as(output/'synthetic_stock_period.csv')
        exported=(output/'synthetic_stock_period.csv').read_text(encoding='utf-8-sig')
        assert '5.03' in exported and '期末价值' in exported and 'BROWSER-STOCK' in exported
        steps.append('手机期间选择重建期初/期末5.03元，原始来源可查，真实CSV下载与表格一致')
        harness.login_page(employee,base,'stock-reader',initial)
        replacement=secrets.token_urlsafe(24)
        employee.locator('#modal [name=current_password]').fill(initial);employee.locator('#modal [name=new_password]').fill(replacement)
        harness.save_modal(employee);harness.login_page(employee,base,'stock-reader',replacement)
        harness.navigate(employee,'stock-period','物资期间入出存')
        expect(employee.locator('#main')).to_contain_text('2.5');expect(employee.locator('#main')).not_to_contain_text('5.03')
        expect(employee.locator('svg')).to_have_count(0);harness.assert_fits_mobile(employee)
        screenshots.append(harness.take_screenshot(employee,output,'02_stock_period_inventory_role.png'))
        report=req(employee,'/api/stock-reports/period');assert not report['can_money'] and 'value_cents' not in report['rows'][0]['closing']
        steps.append('真实库管账号只见数量，页面及API均不返回成本，手机布局不溢出')
        two=req(admin,'/api/stores','POST',{'code':'PERIOD-B','name':'合成空白报表乙店','active':True},status=201)['id']
        admin.reload();expect(admin.locator('#main h1')).to_have_text('物资期间入出存')
        admin.locator('#store').select_option(str(two));expect(admin.locator('#main h1')).to_have_text('我的工作')
        harness.navigate(admin,'stock-period','物资期间入出存')
        expect(admin.locator('#main')).not_to_contain_text('手机验收物资')
        steps.append('切至另一门店后不展示原店库存或期间来源')
        assert not errors,errors
        return {'mode':'real Chromium mobile HTTP','passed':len(steps),'steps':steps,'javascript_errors':errors,'screenshots':screenshots,
                'limitations':['全部为新空库合成期初；未代表正式公司期初核对或HTTPS手机实机验收']}
    except Exception:harness.take_screenshot(admin,output,'failure.png');raise
    finally:
        for context in contexts:context.close()


if __name__=='__main__':harness.exercise=exercise;harness.main()
