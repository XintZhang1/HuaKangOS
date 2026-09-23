"""Real Chrome/HTTP employee historical-bin report, synthetic isolated DB only."""
import csv,io,secrets,re
from datetime import date,timedelta
from pathlib import Path
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login


def exercise(browser,base,password,output):
    contexts=[];errors=[];screens=[];steps=[];req=harness.checked_request
    def page(width=390):
        ctx=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(ctx)
        p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    def screenshot(p,name,selector=None):
        path=output/name
        expect(p.locator('#toast')).not_to_have_class(re.compile('visible'),timeout=10000)
        if selector:p.locator(selector).first.scroll_into_view_if_needed()
        else:p.evaluate('window.scrollTo(0,0)')
        p.screenshot(path=str(path),full_page=False);screens.append(str(path))
    admin=page(1440)
    try:
        harness.login_page(admin,base,'admin',password);people={}
        for role in ('inventory','manager'):
            pw=secrets.token_urlsafe(25)
            req(admin,'/api/users','POST',{'username':'wp-'+role,'display_name':'合成库位报表'+role,'password':pw,'role':role,'store_roles':[{'store_id':1,'role':role}]},status=201)
            p=page();employee_login(p,base,'wp-'+role,pw);people[role]=p
        inventory,manager=people['inventory'],people['manager']
        def typed(kind,v):return req(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':v},status=201)
        warehouse=typed('warehouses',{'code':'PERIOD-W','name':'合成期间物资仓','warehouse_type':'materials'})['id']
        a=typed('locations',{'code':'PERIOD-A','name':'合成原位','warehouse_id':warehouse})['id']
        b=typed('locations',{'code':'PERIOD-B','name':'合成目的位','warehouse_id':warehouse})['id']
        item=req(admin,'/api/flow/master/items','POST',{'values':{'sku':'PERIOD-MATERIAL','name':'合成期间物资','unit':'件','reorder':'0','active':True}},status=201)['id']
        day=admin.evaluate('day()')
        def current(cid):return req(admin,'/api/warehouse/cases/'+str(cid))
        def proof(p,cid,category='evidence'):
            harness.navigate(p,'case/'+str(cid),req(p,'/api/flow/cases/'+str(cid))['title'])
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category)
            p.locator('#modal [name=file]').set_input_files({'name':'合成库位实际凭据.txt','mimeType':'text/plain','buffer':'仅用于合成真实库位启用及收发验收'.encode()});harness.save_modal(p)
            return req(p,'/api/flow/cases/'+str(cid))['files'][-1]['id']
        def command(p,cid,name,values):
            return req(p,f'/api/warehouse/cases/{cid}/commands/{name}','POST',{'request_id':secrets.token_hex(16),'version':current(cid)['version'],'values':values})
        def create(op,qty,src=None,dest=None,locations=None):
            return req(inventory,'/api/warehouse/cases','POST',{'request_id':secrets.token_hex(16),'operation':op,'item_id':item,'quantity_milli':qty,'source_location_id':src,'destination_location_id':dest,'reason':'合成员工实际作业','due_date':day,'locations':locations or []},status=201)['id']
        def approve(cid,value=None):
            v={'evidence_id':proof(manager,cid,'receipt' if value is not None else 'evidence')}
            if value is not None:v['value_cents']=value
            command(manager,cid,'approve',v)
        activate=create('activate',0,locations=[{'location_id':a,'quantity_milli':0}]);approve(activate)
        incoming=create('other_in',10000,dest=a);approve(incoming,1001);command(inventory,incoming,'execute',{'evidence_id':proof(inventory,incoming)})
        moving=create('local_move',4000,src=a,dest=b);approve(moving);asset=proof(inventory,moving)
        command(inventory,moving,'dispatch',{'evidence_id':asset});command(inventory,moving,'accept',{'quantity_milli':1000,'evidence_id':asset})
        harness.navigate(inventory,'warehouse-period','库位期间入出存')
        expect(inventory.locator('#main')).to_contain_text('有未知期初或覆盖缺口');expect(inventory.locator('#main')).to_contain_text('已知并可核对；这不代表全期间完整')
        expect(inventory.locator('#main')).not_to_contain_text('10.01');expect(inventory.locator('#main')).not_to_contain_text('价值（元）');harness.assert_fits_mobile(inventory)
        screenshot(inventory,'01_warehouse_period_unknown_opening_mobile.png','div.notice:has-text("全期间来源")')
        data=req(inventory,'/api/inventory-reports/warehouses');assert not data['complete'] and data['closing_complete']
        assert sorted(r['closing']['quantity_milli'] for r in data['rows'])==[1000,3000,6000]
        assert all(r['opening'] is None for r in data['rows']) and 'value_cents' not in str(data)
        with inventory.expect_download() as event:inventory.locator('[data-act=inventory-report-export][data-key=warehouse_period_balances]').click()
        contents=Path(event.value.path()).read_text(encoding='utf-8-sig');assert '店内在途' in contents and '价值' not in contents and '10.01' not in contents
        steps.append('真实库管390px：启用当日午夜期初未知、期末已知分别显示；原位6件、在途3件、已接收1件不重计，页面/API/CSV均隐藏成本')
        harness.navigate(manager,'warehouse-period','库位期间入出存');harness.assert_fits_mobile(manager)
        expect(manager.locator('#main')).to_contain_text('有据期末库位及店内在途价值')
        screenshot(manager,'02_warehouse_period_known_closing_chart_mobile.png','svg[aria-label="有据期末库位及店内在途价值"]')
        data=req(manager,'/api/inventory-reports/warehouses');assert sum(data['charts'][0]['series'][0]['values'])==1001
        assert sum(r['closing']['value_cents'] for r in data['rows'])==1001 and not data['complete']
        with manager.expect_download() as event:manager.locator('[data-act=inventory-report-export][data-key=warehouse_period_entries]').click()
        rows=list(csv.reader(io.StringIO(Path(event.value.path()).read_text(encoding='utf-8-sig'))));table=data['tables']['warehouse_period_entries']
        assert rows==[table['headers']]+[[str(v) for v in r['values']] for r in table['rows']]
        assert sum(e['quantity_milli'] for e in data['details'] if e['label'].startswith('店内'))==0
        assert sum(e['value_cents'] for e in data['details'] if e['label'].startswith('店内'))==0
        screenshot(manager,'04_warehouse_period_transit_quantity_value_mobile.png','.work-cards .card:has-text("店内在途 ·")')
        steps.append('主管期末图10.01元与库位账完全相等，部分移库两边流水数量价值守恒；真实逐行CSV等于同一次报表表格')
        box=manager.locator('[data-warehouse-report-kind=items]');box.locator('input').fill('PERIOD-MATERIAL');box.locator('button').click()
        expect(box.locator('small')).to_contain_text('已更新匹配资料');box.locator('select').select_option(str(item))
        manager.locator('#warehouse-report-filters [name=warehouse_id]').select_option(str(warehouse));manager.locator('#warehouse-report-filters button[type=submit]').click()
        expect(manager.locator('#warehouse-report-filters [name=item_id]')).to_have_value(str(item));expect(manager.locator('#main')).to_contain_text('合成原位')
        manager.locator('#datefilters [name=date_from]').fill(day);manager.locator('#datefilters [name=date_to]').fill((date.fromisoformat(day)-timedelta(days=1)).isoformat());manager.locator('#datefilters button[type=submit]').click()
        expect(manager.locator('#main')).to_contain_text('开始日期不能晚于结束日期');harness.assert_fits_mobile(manager)
        screenshot(manager,'03_warehouse_period_date_error_filters_retained.png')
        expect(manager.locator('#warehouse-report-filters [name=item_id]')).to_have_value(str(item))
        manager.locator('#datefilters [name=date_to]').fill(day);manager.locator('#datefilters button[type=submit]').click();expect(manager.locator('#main')).to_contain_text('期末来源：已知并可核对')
        with manager.expect_download() as event:manager.locator('[data-act=inventory-report-export][data-key=warehouse_period_balances]').first.click()
        rows=list(csv.reader(io.StringIO(Path(event.value.path()).read_text(encoding='utf-8-sig'))))
        filtered=req(manager,f'/api/inventory-reports/warehouses?item_id={item}&warehouse_id={warehouse}&date_from={day}&date_to={day}')['tables']['warehouse_period_balances']
        assert rows==[filtered['headers']]+[[str(v) for v in r['values']] for r in filtered['rows']]
        steps.append('真实物资编码查找及仓库筛选，导出保留筛选；倒置日期中文拒绝并保留原筛选，可原页改正继续查询')
        other=req(admin,'/api/stores','POST',{'code':'PERIOD-EMPTY','name':'合成期间乙店'},status=201)['id']
        assert req(admin,'/api/inventory-reports/warehouses',store=other)['rows']==[]
        assert harness.request(admin,f'/api/inventory-reports/warehouses?item_id={item}',store=other)['status']==404
        group=req(admin,'/api/inventory-reports/warehouses',store='all');assert all(not row.get('route') for t in group['tables'].values() for row in t['rows'])
        assert not errors,errors
        return {'status':'passed','mode':'actual-chrome-http','steps':steps,'screenshots':screens,'javascript_errors':errors,'synthetic_only':True}
    finally:
        for ctx in contexts:ctx.close()


if __name__=='__main__':harness.exercise=exercise;harness.main()
