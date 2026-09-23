"""Actual Chrome HTTP: independent entity approvals and 390px Chinese errors.

Run only after the root integration registers this domain. The harness creates
a fresh temporary database and random credentials outside the repository.
"""
import secrets,re,json
from datetime import date,timedelta
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login


def exercise(browser,base,password,output):
    contexts=[];errors=[];screens=[];steps=[];req=harness.checked_request
    def page():
        context=browser.new_context(viewport={'width':390,'height':844},locale='zh-CN');contexts.append(context);p=context.new_page();p.on('pageerror',lambda error:errors.append(str(error)));return p
    def shot(p,name):
        harness.assert_fits_mobile(p);screens.append(harness.take_screenshot(p,output,name))
    admin=page()
    try:
        harness.login_page(admin,base,'admin',password)
        secret=secrets.token_urlsafe(24);req(admin,'/api/users','POST',{'username':'entity-reviewer','display_name':'合成独立复核主管','role':'manager','password':secret,'store_roles':[{'store_id':1,'role':'manager'}]},status=201)
        manager=page();employee_login(manager,base,'entity-reviewer',secret)
        secret=secrets.token_urlsafe(24);req(admin,'/api/users','POST',{'username':'entity-finance','display_name':'合成核对财务','role':'finance','password':secret,'store_roles':[{'store_id':1,'role':'finance'}]},status=201)
        finance=page();employee_login(finance,base,'entity-finance',secret)
        def current(p):return req(p,'/api/business-entities/applications/'+p.url.rsplit('/',1)[-1])
        def navigate(p,row):harness.navigate(p,'business-entity/'+str(row['id']),row['title'])
        def upload(p,category='evidence'):
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category)
            p.locator('#modal [name=file]').set_input_files({'name':'纯合成主体核对-'+secrets.token_hex(3)+'.txt','mimeType':'text/plain','buffer':('本人独立核对记录 '+secrets.token_hex(12)+'，纯合成资料，不是真实工商或账户资料。').encode()});harness.save_modal(p)
        def submit(p,action):
            p.locator(f'[data-act=be-action][data-key={action}]').click()
            try:expect(p.locator('#modal button[type=submit]')).to_be_visible(timeout=2500)
            except AssertionError:raise AssertionError({'action':action,'main':p.locator('#main').inner_text(),'toast':p.locator('#toast').inner_text(),'errors':errors})
            harness.save_modal(p)
        def new(operation,values):
            harness.navigate(admin,'business-entities','经营主体与账户归属');admin.locator(f'[data-act=be-new][data-kind={operation}]').click()
            for key,value in values.items():admin.locator(f'#modal [name={key}]').fill(value)
            if operation=='policy':admin.locator('#modal [name=ack]').check()
            admin.locator('#modal [name=reason]').fill('本人对照纯合成来源申请，等待另一主管实际核对');harness.save_modal(admin)
            try:expect(admin.locator('[data-act=be-action][data-key=submit]')).to_be_visible()
            except AssertionError:
                shot(admin,'failure_entity_application_mobile.png');raise AssertionError({'url':admin.url,'main':admin.locator('#main').inner_text(),'errors':errors})
            row=current(admin);upload(admin);submit(admin,'submit');return current(admin)
        def approve(row):
            navigate(manager,row);upload(manager);submit(manager,'approve');expect(manager.locator('#main')).to_contain_text('本次配置已独立批准生效');return current(manager)
        row=new('revision',{'code':'BROWSER-ENTITY','tax_identifier':'SYNTHETIC000000001','legal_name':'纯合成浏览器经营公司','registered_address':'虚构资料街测试一号'})
        expect(admin.locator('[data-act=be-action][data-key=approve]')).to_have_count(0)
        assert harness.request(admin,f'/api/business-entities/applications/{row["id"]}/actions/approve','POST',{'request_id':secrets.token_hex(16),'version':row['version'],'values':{'evidence_id':row['own_file_ids'][0]}})['status']==403
        navigate(manager,row);upload(manager);shot(manager,'01_entity_independent_review_mobile.png');submit(manager,'approve')
        steps.append('管理员通过手机表单提出真实字段的合成主体资料，管理员API不能自批，另一主管上传本人核对凭据后独立批准')
        row=new('store_binding',{});approve(row)
        account=req(admin,'/api/flow/master/accounts','POST',{'values':{'name':'合成实际银行账户','account_type':'bank','active':True}},status=201)
        harness.navigate(admin,'business-entities','经营主体与账户归属');admin.locator('[data-act=be-new][data-kind=account_binding]').click()
        for key,value in {'holder_name':'不对应主体的户名','channel_identifier':'SYNTHETIC-BANK-1122','institution_name':'纯合成测试银行','reason':'核对实际账户开户资料'}.items():admin.locator(f'#modal [name={key}]').fill(value)
        admin.locator('#modal button[type=submit]').click();expect(admin.locator('#modal .formerror')).to_contain_text('账户户名须与本次批准主体名称一致')
        shot(admin,'02_entity_wrong_account_holder_refused_mobile.png')
        admin.locator('#modal [name=holder_name]').fill('纯合成浏览器经营公司');harness.save_modal(admin);upload(admin);submit(admin,'submit');row=current(admin);approve(row)
        steps.append('账户绑定错误户名中文拒绝且保留输入，改正后原表单保存；真实资金渠道经独立主管批准')
        row=new('policy',{})
        approve(row)
        harness.navigate(finance,'business-entities','经营主体与账户归属');expect(finance.locator('#main')).to_contain_text('纯合成浏览器经营公司');expect(finance.locator('#main')).to_contain_text('已批准启用')
        expect(finance.locator('[data-act=be-new]')).to_have_count(0);shot(finance,'03_entity_finance_frozen_configuration_mobile.png')
        cfg=req(finance,'/api/business-entities/configuration');assert cfg['policy'] and cfg['accounts'][0]['binding']['account_name']==account['name']
        finance.reload();expect(finance.locator('#main')).to_contain_text('纯合成浏览器经营公司')
        steps.append('空门店主体策略单独申请批准，财务手机只读查看批准主体与真实渠道，刷新保留本店；历史归属不会自动补认')
        secret=secrets.token_urlsafe(24);req(admin,'/api/users','POST',{'username':'entity-inventory','display_name':'合成期初实物库管','role':'inventory','password':secret,'store_roles':[{'store_id':1,'role':'inventory'}]},status=201)
        inventory=page();employee_login(inventory,base,'entity-inventory',secret)
        def typed(kind,values):return req(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':values},status=201)
        typed('vehicle_models',{'code':'OPEN-MODEL','name':'合成正式期初车','brand':'纯合成品牌','model_year':2026,'fuel_type':'electric','seats':5,'battery_wh':60000,'guide_price_cents':11000000})
        wh=typed('warehouses',{'code':'OPEN-W','name':'合成正式期初仓','warehouse_type':'vehicles'});typed('locations',{'code':'OPEN-LOCATION','name':'合成期初核对位','warehouse_id':wh['id']})
        template=req(admin,'/api/opening-import/example');assert template['policy_enabled'] and template['source']['accounts']==[]
        source=template['source'];source['opening_date']=(date.today()-timedelta(days=3)).isoformat()
        source['accounts']=[{'account_id':account['id'],'name':account['name'],'account_type':'bank','opening_balance_cents':500001,'source_reference':'合成期初原账户核对表'}]
        harness.navigate(admin,'opening-import','正式期初核验');expect(admin.locator('#main')).to_contain_text('期初账户与批准配置')
        source['accounts'][0]['account_id']=999999;admin.locator('#oi-source').fill(json.dumps(source,ensure_ascii=False));admin.locator('[data-act=oi-preflight]').click()
        expect(admin.locator('#main')).to_contain_text('逐行检查结果');expect(admin.locator('#main')).to_contain_text('按编号明确选择本店已批准')
        shot(admin,'04_entity_opening_wrong_account_refused_mobile.png')
        source['accounts'][0]['account_id']=account['id'];admin.locator('#oi-source').fill(json.dumps(source,ensure_ascii=False));admin.locator('[data-act=oi-preflight]').click();expect(admin.locator('#main h1')).to_contain_text('待试导入')
        opening_id=int(admin.url.rsplit('/',1)[-1])
        def opening_visit(p):
            p.goto(base+'/?opening='+secrets.token_hex(4)+'#opening-batch/'+str(opening_id));expect(p.locator('#main h1')).to_contain_text('期初资料核验',timeout=15000)
        def opening_action(p,key):
            p.locator('[data-act=oi-action][data-key='+key+']').click();expect(p.locator('#modal')).to_be_visible();p.locator('#modal [name=reason]').fill('本人对照合成原清单核实实际资料')
        upload(admin);opening_action(admin,'trial');harness.save_modal(admin);expect(admin.locator('#main h1')).to_contain_text('待主管复核')
        assert len(req(admin,'/api/flow/master/accounts')['items'])==1 and req(admin,'/api/vehicle-operations/vehicles')['items']==[]
        opening_visit(manager);upload(manager);opening_action(manager,'approve');harness.save_modal(manager)
        opening_visit(inventory);assert account['name'] not in inventory.locator('#main').inner_text();upload(inventory);opening_action(inventory,'verify_inventory')
        inventory.locator('#modal [name=vin_0]').fill(source['vehicles'][0]['vin']);inventory.locator('#modal [name=loc_0]').fill('OPEN-LOCATION');inventory.locator('#modal [name=qty_0]').fill('2.5');harness.save_modal(inventory)
        opening_visit(finance);upload(finance,'receipt');opening_action(finance,'verify_finance')
        finance.locator('#modal [name=balance_0]').fill('5000.01');finance.locator('#modal [name=material_value]').fill('100.01');finance.locator('#modal [name=vehicle_value]').fill('100000.01');harness.save_modal(finance)
        opening_visit(manager);opening_action(manager,'confirm');manager.locator('#modal [name=confirmed]').check();harness.save_modal(manager);expect(manager.locator('#main h1')).to_contain_text('已启用')
        assert len(req(admin,'/api/flow/master/accounts')['items'])==1
        harness.navigate(finance,'opening-balances','期初与实际账户余额');balance=req(finance,'/api/opening-import/account-balances')['items'][0]
        assert balance['account_id']==account['id'] and (balance['opening_cents'],balance['in_cents'],balance['out_cents'],balance['balance_cents'])==(500001,0,0,500001)
        shot(finance,'05_entity_approved_account_opening_not_receipt_mobile.png')
        steps.append('先启用主体后进行正式期初：错误账户编号逐行拒绝，试导入保留唯一预配置账户且回滚库存；主管、库管、财务分别核验，旧基准日期初余额记入原批准账户，实际收入支出仍为0')
        assert not errors,errors
        return {'status':'passed','mode':'actual-chrome-http','steps':steps,'screenshots':screens,'javascript_errors':errors,'synthetic_only':True}
    finally:
        for context in contexts:context.close()


if __name__=='__main__':harness.exercise=exercise;harness.main()
