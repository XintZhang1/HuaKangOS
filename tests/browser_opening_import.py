"""Four actual employee browsers; synthetic new DB, cookies, CSP, mobile and no secrets."""
import json,secrets
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login,take_screenshot


def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screens=[];req=harness.checked_request
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(context);p=context.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440)
    try:
        harness.login_page(admin,base,'admin',password);people={}
        for key,role,title in [('prepare','manager','合成期初准备主管'),('approve','manager','合成独立复核主管'),('inventory','inventory','合成期初库管'),('finance','finance','合成期初财务')]:
            secret=secrets.token_urlsafe(25);req(admin,'/api/users','POST',{'username':'opening-'+key,'display_name':title,'role':role,'password':secret,
                'store_roles':[{'store_id':1,'role':role}],'can_group_summary':role=='manager'},status=201)
            p=page();employee_login(p,base,'opening-'+key,secret);people[key]=p
        def typed(kind,v):return req(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':v},status=201)
        typed('vehicle_models',{'code':'OPEN-MODEL','name':'合成期初纯电车','brand':'虚构品牌','model_year':2026,'fuel_type':'electric','seats':5,'battery_wh':60000,'guide_price_cents':11000000})
        wh=typed('warehouses',{'code':'OPEN-W','name':'合成期初整车仓','warehouse_type':'vehicles'})
        typed('locations',{'code':'OPEN-LOCATION','name':'合成核验一号库位','warehouse_id':wh['id']})
        prep,approve,inventory,finance=[people[k] for k in ['prepare','approve','inventory','finance']]
        harness.navigate(prep,'opening-import','正式期初核验');prep.locator('[data-act=oi-example]').click();expect(prep.locator('#oi-source')).to_contain_text('schema_version')
        source=json.loads(prep.locator('#oi-source').input_value());invalid=json.loads(json.dumps(source));invalid['accounts'][0]['opening_balance_cents']=1.001
        prep.locator('#oi-source').fill(json.dumps(invalid,ensure_ascii=False));prep.locator('[data-act=oi-preflight]').click();expect(prep.locator('#main')).to_contain_text('逐行检查结果')
        harness.assert_fits_mobile(prep);screens.append(take_screenshot(prep,output,'01_opening_row_error_mobile.png'))
        prep.locator('#oi-source').fill(json.dumps(source,ensure_ascii=False));prep.locator('[data-act=oi-preflight]').click();expect(prep.locator('#main h1')).to_contain_text('待试导入');cid=int(prep.url.split('/')[-1])
        def visit(p):
            p.goto(base+'/?visit='+secrets.token_hex(4)+'#opening-batch/'+str(cid));expect(p.locator('#main h1')).to_contain_text('期初资料核验',timeout=15000)
        def upload(p,name,category='evidence'):
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category);p.locator('#modal [name=file]').set_input_files({'name':name+'.txt','mimeType':'text/plain','buffer':('仅合成核验：'+name).encode()});harness.save_modal(p)
        def action(p,key):
            p.locator('[data-act=oi-action][data-key='+key+']').click();expect(p.locator('#modal')).to_be_visible();p.locator('#modal [name=reason]').fill('本人核对合成资料与明确来源')
        upload(prep,'合成期初原始清单');action(prep,'trial');harness.save_modal(prep);expect(prep.locator('#main h1')).to_contain_text('待主管复核')
        assert req(admin,'/api/flow/master/accounts')['items']==[];assert req(admin,'/api/vehicle-operations/vehicles')['items']==[]
        steps.append('准备主管通过实际手机页面逐行预检，金额小数拒绝；试导入回滚后账户和可用车辆仍为空')
        visit(approve);upload(approve,'独立主管核对原清单');action(approve,'approve');harness.save_modal(approve)
        visit(inventory);assert '100,000.01' not in inventory.locator('#main').inner_text() and '5,000.01' not in inventory.locator('#main').inner_text()
        upload(inventory,'库管实车和物资实盘清单');action(inventory,'verify_inventory')
        inventory.locator('#modal [name=vin_0]').fill('LTEST000000000999');inventory.locator('#modal [name=loc_0]').fill('OPEN-LOCATION');inventory.locator('#modal [name=qty_0]').fill('2.5')
        inventory.locator('#modal button[type=submit]').click();expect(inventory.locator('#modal .formerror')).to_contain_text('不一致')
        harness.assert_fits_mobile(inventory);screens.append(take_screenshot(inventory,output,'02_opening_inventory_vin_refusal_mobile.png'))
        inventory.locator('#modal [name=vin_0]').fill(source['vehicles'][0]['vin']);harness.save_modal(inventory)
        steps.append('独立主管批准后库管对照实车重输VIN、库位和实盘数量；VIN差异明确拒绝，库存岗位看不到账户余额或车辆成本')
        visit(finance);upload(finance,'财务账户与库存原值核对表','receipt');action(finance,'verify_finance')
        finance.locator('#modal [name=balance_0]').fill('5000.02');finance.locator('#modal [name=material_value]').fill('100.01');finance.locator('#modal [name=vehicle_value]').fill('100000.01')
        finance.locator('#modal button[type=submit]').click();expect(finance.locator('#modal .formerror')).to_contain_text('不一致')
        harness.assert_fits_mobile(finance);screens.append(take_screenshot(finance,output,'03_opening_finance_one_cent_refusal_mobile.png'))
        finance.locator('#modal [name=balance_0]').fill('5000.01');harness.save_modal(finance)
        steps.append('财务独立上传本人凭据并逐账户核对余额；一分钱差异拒绝，车辆和物资原值另行核对')
        visit(approve);action(approve,'confirm');approve.locator('#modal [name=confirmed]').check();harness.save_modal(approve)
        expect(approve.locator('#main h1')).to_contain_text('已启用');harness.assert_fits_mobile(approve);screens.append(take_screenshot(approve,output,'04_opening_confirmed_sources_mobile.png'))
        done=req(admin,'/api/opening-import/batches/'+str(cid));assert done['status']=='confirmed'
        assert len(req(admin,'/api/flow/master/accounts')['items'])==1 and len(req(admin,'/api/vehicle-operations/vehicles')['items'])==1
        harness.navigate(finance,'opening-balances','期初与实际账户余额');harness.assert_fits_mobile(finance);screens.append(take_screenshot(finance,output,'05_opening_balance_not_receipt_mobile.png'))
        balance=req(finance,'/api/opening-import/account-balances')['items'][0];assert (balance['opening_cents'],balance['in_cents'],balance['out_cents'],balance['balance_cents'])==(500001,0,0,500001)
        req(inventory,'/api/opening-import/batches/'+str(cid)+'/source',status=403);req(prep,'/api/opening-import/batches',store='all',status=409)
        two=req(admin,'/api/stores','POST',{'code':'OPEN-OTHER','name':'合成隔离乙店','active':True},status=201)['id'];req(admin,'/api/opening-import/batches/'+str(cid),store=two,status=404)
        steps.append('三岗凭据齐全后一次创建客户、物资、可售车辆首代次与保管库位；账户期初5000.01元、实际收支均为0，串店和集团汇总读写拒绝')
        assert not errors,errors
        return {'status':'passed','mode':'actual-chrome-http','steps':steps,'screenshots':screens,'javascript_errors':errors,'synthetic_only':True}
    finally:
        for context in contexts:context.close()


if __name__=='__main__':
    harness.exercise=exercise;harness.main()
