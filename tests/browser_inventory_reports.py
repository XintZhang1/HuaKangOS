"""Real HTTP Chrome, 390px employee reports and exact CSV; synthetic DB only."""
import csv,io,secrets
from datetime import date,timedelta
from pathlib import Path
import browser_huakangos as harness
from browser_masters import employee_login,take_screenshot
from playwright.sync_api import expect


def exercise(browser,base,password,output):
    contexts=[];errors=[];screens=[];steps=[];req=harness.checked_request
    def page(width=390):
        ctx=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(ctx)
        p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440)
    try:
        harness.login_page(admin,base,'admin',password);people={}
        for key,role in [('inventory','inventory'),('manager','manager')]:
            pw=secrets.token_urlsafe(25)
            req(admin,'/api/users','POST',{'username':'report-'+key,'display_name':'合成报表'+key,'password':pw,'role':role,'store_roles':[{'store_id':1,'role':role}]},status=201)
            p=page();employee_login(p,base,'report-'+key,pw);people[key]=p
        inventory,manager=people['inventory'],people['manager']
        def master(kind,v):return req(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':v},status=201)
        supplier=master('suppliers',{'code':'REPORT-S','name':'合成报表供应商','payment_terms_days':30})
        model=master('vehicle_models',{'code':'REPORT-M','name':'合成报表车型','brand':'虚构品牌','model_year':2026,'fuel_type':'electric','seats':5,'battery_wh':60000,'guide_price_cents':12000000})
        wh=master('warehouses',{'code':'REPORT-W','name':'合成整车仓','warehouse_type':'vehicles'})
        loc=master('locations',{'code':'REPORT-L','name':'合成验收库位','warehouse_id':wh['id']})
        day=admin.evaluate('day()')
        car=req(admin,'/api/vehicle-procurement/orders','POST',{'request_id':secrets.token_hex(16),'supplier_id':supplier['id'],'contracting_party':'合成经营主体','reason':'本轮报表合成库存','due_date':day,'lines':[{'model_id':model['id'],'quantity':1,'color':'白'}]},status=201)
        def proof(p,case,category='evidence'):
            title=req(p,'/api/flow/cases/'+str(case))['title']
            harness.navigate(p,'case/'+str(case),title)
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category)
            p.locator('#modal [name=file]').set_input_files({'name':'合成报表凭据.txt','mimeType':'text/plain','buffer':'仅用于合成实际收发来源'.encode()})
            harness.save_modal(p)
            return req(p,'/api/flow/cases/'+str(case))['files'][-1]['id']
        def action(p,domain,key,name,v):
            row=req(p,f'/api/{domain}/orders/{key}')
            return req(p,f'/api/{domain}/orders/{key}/actions/{name}','POST',{'request_id':secrets.token_hex(16),'version':row['version'],'values':v})
        asset=proof(admin,car['id'],'procurement_contract')
        car=action(manager,'vehicle-procurement',car['id'],'approve',{'prices':[{'line_id':car['lines'][0]['id'],'unit_cost_cents':10000001,'list_price_cents':12000000}],'evidence_id':asset})
        asset=proof(inventory,car['id']);car=action(inventory,'vehicle-procurement',car['id'],'ship',{'line_id':car['lines'][0]['id'],'vin':'LTEST000000000601','shipped_date':day,'expected_date':day,'evidence_id':asset})
        car=action(inventory,'vehicle-procurement',car['id'],'receive',{'shipment_id':car['shipments'][0]['id'],'vin':'LTEST000000000601','location_id':loc['id'],'evidence_id':asset})
        harness.navigate(inventory,'vehicle-period','整车期间入出存')
        expect(inventory.locator('#main')).to_contain_text('本次所列代次均可核对');expect(inventory.locator('#main')).not_to_contain_text('100,000.01')
        expect(inventory.locator('#main')).not_to_contain_text('100000.01');harness.assert_fits_mobile(inventory)
        screens.append(take_screenshot(inventory,output,'01_vehicle_period_inventory_mobile.png'))
        data=req(inventory,'/api/inventory-reports/vehicles');assert data['complete'] and 'value_cents' not in data['details'][0]
        with inventory.expect_download() as event:inventory.locator('[data-act=inventory-report-export][data-key=vehicle_period_movements]').click()
        exported=Path(event.value.path()).read_text(encoding='utf-8-sig')
        assert 'LTEST000000000601' in exported and '成本' not in exported and '价值' not in exported
        steps.append('真实库管390px按实际验收查看库存代次，图表/表/下载同源且全部隐藏成本')
        harness.navigate(manager,'vehicle-period','整车期间入出存');expect(manager.locator('#main')).to_contain_text('100000.01')
        harness.assert_fits_mobile(manager);screens.append(take_screenshot(manager,output,'02_vehicle_period_manager_value_mobile.png'))
        with manager.expect_download() as event:manager.locator('[data-act=inventory-report-export][data-key=vehicle_period_balances]').first.click()
        lines=list(csv.reader(io.StringIO(Path(event.value.path()).read_text(encoding='utf-8-sig'))))
        expected=req(manager,'/api/inventory-reports/vehicles')['tables']['vehicle_period_balances']
        assert lines==[expected['headers']]+[[str(v) for v in r['values']] for r in expected['rows']]
        steps.append('主管实收原值100000.01元，真实CSV逐单与API同源表完全一致')
        item=req(admin,'/api/flow/master/items','POST',{'values':{'sku':'REPORT-ITEM','name':'合成报告物资','unit':'件','reorder':'0','active':True}},status=201)
        order=req(inventory,'/api/procurement/orders','POST',{'request_id':secrets.token_hex(16),'supplier_id':supplier['id'],'reason':'合成订货批次','lines':[{'item_id':item['id'],'quantity_milli':2500,'unit_cost_cents':123}]},status=201)
        action(manager,'procurement',order['id'],'approve',{})
        asset=proof(inventory,order['id'])
        action(inventory,'procurement',order['id'],'receive',{'lines':[{'line_id':order['lines'][0]['id'],'quantity_milli':1000}],'evidence_id':asset})
        action(manager,'procurement',order['id'],'close_receiving',{'reason':'供货方确认余量关闭'})
        harness.navigate(manager,'procurement-cohort','物资采购订货统计');expect(manager.locator('#main')).to_contain_text('已关闭未到');expect(manager.locator('#main')).to_contain_text('截至本次查询')
        expect(manager.locator('#main')).to_contain_text('3.08');harness.assert_fits_mobile(manager)
        screens.append(take_screenshot(manager,output,'03_procurement_cohort_closed_mobile.png'))
        report=req(manager,'/api/inventory-reports/procurement');assert report['rows'][0]['closed']['quantity_milli']==1500 and report['rows'][0]['received']['value_cents']==123
        harness.navigate(inventory,'procurement-cohort','物资采购订货统计');expect(inventory.locator('#main')).not_to_contain_text('3.08');expect(inventory.locator('#main')).not_to_contain_text('原订货金额（元）')
        steps.append('同一原订货批次2.5件，实际到货1件、关闭余量1.5件；主管金额可见、库管只见数量，未当作期间到货口径')
        inventory.locator('#datefilters [name=date_from]').fill(day)
        inventory.locator('#datefilters [name=date_to]').fill((date.fromisoformat(day)-timedelta(days=1)).isoformat())
        inventory.locator('#datefilters button[type=submit]').click()
        expect(inventory.locator('#main')).to_contain_text('开始日期不能晚于结束日期',timeout=15000)
        screens.append(take_screenshot(inventory,output,'04_inventory_report_invalid_period_chinese.png'))
        inventory.locator('#datefilters [name=date_to]').fill(day);inventory.locator('#datefilters button[type=submit]').click()
        expect(inventory.locator('#main')).to_contain_text('原订货与到退货来源可核对')
        steps.append('真实网页倒置日期被API拒绝，员工看到具体中文说明，可在原页改正并重新查询')
        other=req(admin,'/api/stores','POST',{'code':'REPORT-EMPTY','name':'合成空白乙店'},status=201)['id']
        assert req(admin,'/api/inventory-reports/vehicles',store=other)['rows']==[]
        assert req(admin,'/api/inventory-reports/procurement',store=other)['rows']==[]
        group=req(admin,'/api/inventory-reports/vehicles',store='all');assert all(r.get('route') is None for t in group['tables'].values() for r in t['rows'])
        assert not errors,errors
        return {'status':'passed','mode':'actual-chrome-http','steps':steps,'screenshots':screens,'javascript_errors':errors,'synthetic_only':True}
    finally:
        for ctx in contexts:ctx.close()


if __name__=='__main__':harness.exercise=exercise;harness.main()
