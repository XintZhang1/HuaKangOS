"""Actual Chrome, original CSV bytes and four employee contexts; synthetic only."""
import csv,io,secrets
from pathlib import Path
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login,take_screenshot

VIN='LTEST000000000401'
def csv_bytes(header,row):
    text=io.StringIO(newline='');writer=csv.writer(text);writer.writerow(header);writer.writerow(row);return ('\ufeff'+text.getvalue()).encode()


def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screens=[];req=harness.checked_request
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(context);p=context.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440)
    try:
        harness.login_page(admin,base,'admin',password);people={}
        for key,role in [('prepare','manager'),('review','manager'),('inventory','inventory'),('finance','finance')]:
            password=secrets.token_urlsafe(25);req(admin,'/api/users','POST',{'username':'imports-'+key,'display_name':'合成导入'+key,'role':role,'password':password,'store_roles':[{'store_id':1,'role':role}]},status=201)
            employee=page();employee_login(employee,base,'imports-'+key,password);people[key]=employee
        prep,review,inventory,finance=[people[k] for k in ['prepare','review','inventory','finance']]
        def master(kind,v):return req(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':v},status=201)
        supplier=master('suppliers',{'code':'VI-S','name':'合成清单供应商','payment_terms_days':30})
        model=master('vehicle_models',{'code':'VI-M','name':'合成清单车型','brand':'虚构品牌','model_year':2026,'fuel_type':'electric','seats':5,'battery_wh':60000,'guide_price_cents':12000000})
        wh=master('warehouses',{'code':'VI-W','name':'合成整车仓','warehouse_type':'vehicles'})
        loc=master('locations',{'code':'VI-L','name':'合成到货库位','warehouse_id':wh['id']})
        day=req(admin,'/api/flow/catalog')['today'] if 'today' in req(admin,'/api/flow/catalog') else admin.evaluate('day()')
        source=req(admin,'/api/vehicle-procurement/orders','POST',{'request_id':secrets.token_hex(16),'supplier_id':supplier['id'],'contracting_party':'合成采购经营主体','reason':'合成批量导入验收','due_date':day,'lines':[{'model_id':model['id'],'quantity':1,'color':'白色'}]},status=201);cid=source['id'];line=source['lines'][0]['id']
        harness.navigate(admin,'vehicle-procurement/'+str(cid),'整车采购办理');admin.locator('[data-act=upload]').click();admin.locator('#modal [name=category]').select_option('procurement_contract');admin.locator('#modal [name=file]').set_input_files({'name':'合成已批准采购依据.txt','mimeType':'text/plain','buffer':'仅合成采购审批来源'.encode()});harness.save_modal(admin)
        asset=req(admin,'/api/flow/cases/'+str(cid))['files'][0]
        req(admin,f'/api/vehicle-procurement/orders/{cid}/actions/approve','POST',{'request_id':secrets.token_hex(16),'version':source['version'],'values':{'prices':[{'line_id':line,'unit_cost_cents':10000001,'list_price_cents':12000000}],'evidence_id':asset['id']}})
        def visit(p,bid):
            p.goto(base+'/?visit='+secrets.token_hex(4)+'#vehicle-import/'+str(bid));expect(p.locator('#main h1')).to_contain_text('车辆导入批次',timeout=15000)
        def upload(p,kind,data,replace=False):
            if replace:p.locator('[data-act=vi-replace]').click()
            else:
                harness.navigate(p,'vehicle-imports/'+str(cid),'车辆请款与批量交接');p.locator('[data-act=vi-new][data-kind='+kind+']').click()
            p.locator('#modal [name=source_reference]').fill('SYNTH-'+kind)
            p.locator('#modal [name=file]').set_input_files({'name':'合成原始'+kind+'.csv','mimeType':'text/csv','buffer':data});harness.save_modal(p)
            expect(p.locator('#main h1')).to_contain_text('车辆导入批次');return int(p.url.split('/')[-1])
        def action(p,name):
            p.locator('[data-act=vi-action][data-key='+name+']').click();p.locator('#modal [name=reason]').fill('本人对照合成来源清单核对')
            if name=='confirm':p.locator('#modal [name=confirmed]').check()
            harness.save_modal(p)
        funds_header=['source_row','line_id','vin','amount_cents']
        invalid=upload(prep,'funds',csv_bytes(funds_header,['F-1',line,VIN,'1.01']));expect(prep.locator('#main')).to_contain_text('须为正整数')
        harness.assert_fits_mobile(prep);screens.append(take_screenshot(prep,output,'01_vehicle_import_row_error_mobile.png'))
        action(prep,'cancel');funds_bytes=csv_bytes(funds_header,['F-1',line,VIN,10000001]);bid=upload(prep,'funds',funds_bytes,True);action(prep,'trial')
        assert req(admin,f'/api/vehicle-procurement/orders/{cid}')['funds_requests']==[]
        visit(review,bid);action(review,'review');visit(prep,bid);action(prep,'confirm');done=req(prep,'/api/vehicle-imports/batches/'+str(bid));manifest=done['rows'][0]['id']
        with prep.expect_download() as download:prep.locator('[data-act=downloadfile][data-id="'+str(done['file']['id'])+'"]').click()
        assert Path(download.value.path()).read_bytes()==funds_bytes
        steps.append('准备主管从真实 CSV 逐行预检，分金额小数拒绝；取消后明确关联替代，试执行回滚，另一主管复核后仅创建原生请款，下载原文件字节一致')
        req(inventory,'/api/vehicle-imports/batches/'+str(bid),status=403);req(inventory,'/api/flow/files/'+str(done['file']['id']),status=403)
        harness.navigate(inventory,'vehicle-imports/'+str(cid),'车辆请款与批量交接');expect(inventory.locator('#main')).not_to_contain_text('100,000.01')
        screens.append(take_screenshot(inventory,output,'02_vehicle_import_inventory_manifest_mobile.png'))
        ship_bytes=csv_bytes(['source_row','manifest_row_id','vin','shipped_date','expected_date'],['S-1',manifest,VIN,day,day]);ship=upload(inventory,'ship',ship_bytes);action(inventory,'trial')
        assert req(admin,f'/api/vehicle-procurement/orders/{cid}')['shipments']==[]
        # The first manager assigned to physical-file review is the preparing manager from the funds stage.
        visit(prep,ship);action(prep,'review');visit(inventory,ship);action(inventory,'confirm');current=req(admin,f'/api/vehicle-procurement/orders/{cid}');assert len(current['shipments'])==1 and not current['receipts'] and not current['payments']
        steps.append('库管仅取得无金额的请款 VIN 行，财务源文件 API 和下载拒绝；供应方发运单独试执行与主管复核，未付款也按原先货后付规则发运，尚无车辆入库')
        header=['source_row','manifest_row_id','vin','received_date','location_id']
        bad=upload(inventory,'receive',csv_bytes(header,['R-1',manifest,'LTEST000000000999',day,loc['id']]));expect(inventory.locator('#main')).to_contain_text('同一 VIN')
        harness.assert_fits_mobile(inventory);screens.append(take_screenshot(inventory,output,'03_vehicle_import_arrival_vin_refusal_mobile.png'));action(inventory,'cancel')
        receipt=upload(inventory,'receive',csv_bytes(header,['R-1',manifest,VIN,day,loc['id']]),True);action(inventory,'trial');visit(prep,receipt);action(prep,'review');visit(inventory,receipt);action(inventory,'confirm')
        expect(inventory.locator('#main')).to_contain_text('实际验收 #');expect(inventory.locator('#main')).not_to_contain_text('100,000.01');harness.assert_fits_mobile(inventory);screens.append(take_screenshot(inventory,output,'04_vehicle_import_arrival_confirmed_mobile.png'))
        current=req(admin,f'/api/vehicle-procurement/orders/{cid}');assert len(current['receipts'])==1 and current['totals']['payable_cents']==10000001 and current['payments']==[]
        harness.navigate(finance,'vehicle-procurement/'+str(cid),'整车采购办理');expect(finance.locator('#main')).to_contain_text('100,000.01');harness.assert_fits_mobile(finance);screens.append(take_screenshot(finance,output,'05_vehicle_import_payable_not_payment_mobile.png'))
        steps.append('到货清单错误 VIN 明确拒绝，纠正后按真实库位验收入库；财务应付100000.01元、实际付款仍为0，原成本和唯一库存事实保留')
        other=req(admin,'/api/stores','POST',{'code':'VIMP-B','name':'合成隔离乙店'},status=201)['id'];req(admin,'/api/vehicle-imports/batches/'+str(receipt),store=other,status=404)
        req(admin,f'/api/vehicle-imports/orders/{cid}/batches',store='all',status=409)
        assert not errors,errors
        return {'status':'passed','mode':'actual-chrome-http','steps':steps,'screenshots':screens,'javascript_errors':errors,'synthetic_only':True}
    finally:
        for context in contexts:context.close()


if __name__=='__main__':
    harness.exercise=exercise;harness.main()

