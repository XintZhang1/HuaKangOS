"""Real Chrome employee acceptance for evidence-based vehicle acquisition and refund."""
import secrets
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login,take_screenshot

API='/api/vehicle-procurement';VIN='LHGCM82633A123456'
def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screens=[]
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(context);p=context.new_page()
        p.on('pageerror',lambda error:errors.append(str(error)));return p
    admin=page(1440);req=harness.checked_request
    try:
        harness.login_page(admin,base,'admin',password)
        def master(kind,v):return req(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':v},status=201)
        supplier=master('suppliers',{'code':'S-CAR','name':'虚构实车供应商','payment_terms_days':30})
        model=master('vehicle_models',{'code':'MODEL-CAR','name':'合成试验车型','brand':'虚构汽车','model_year':2026,'fuel_type':'electric','seats':5,'battery_wh':60000,'guide_price_cents':12000000})
        warehouse=master('warehouses',{'code':'CAR-W','name':'合成整车仓','warehouse_type':'vehicles'})
        location=master('locations',{'code':'CAR-L','name':'合成验收A位','warehouse_id':warehouse['id']})
        account=req(admin,'/api/flow/master/accounts','POST',{'values':{'name':'合成购车资金账户','account_type':'bank','active':True}},status=201)
        employees={}
        for role,label in [('inventory','库管'),('manager','店长'),('finance','财务')]:
            secret=secrets.token_urlsafe(26)
            req(admin,'/api/users','POST',{'username':'vbuy-'+role,'display_name':'合成整车'+label,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},status=201)
            employee=page();employee_login(employee,base,'vbuy-'+role,secret);employees[role]=employee
        inventory,manager,finance=(employees[k] for k in ('inventory','manager','finance'))
        harness.navigate(inventory,'vehicle-procurement','整车采购与付款');inventory.locator('[data-act=vp-new]').click()
        inventory.locator('#modal [name=supplier_id]').select_option(str(supplier['id']))
        inventory.locator('#modal [name=contracting_party]').fill('虚构汽车销售试验有限公司')
        inventory.locator('#modal [name=reason]').fill('合成门店需求补充两台实车')
        inventory.locator('#modal [name=model]').select_option(str(model['id']));inventory.locator('#modal [name=color]').fill('白色')
        inventory.locator('#modal [name=quantity]').fill('2');harness.assert_fits_mobile(inventory)
        screens.append(take_screenshot(inventory,output,'01_vehicle_plan_mobile.png'));harness.save_modal(inventory)
        expect(inventory.locator('#main h1')).to_have_text('整车采购办理')
        row=req(admin,API+'/orders')['items'][0];cid=row['id'];route='vehicle-procurement/'+str(cid)
        def current():return req(admin,API+'/orders/'+str(cid))
        def visit(p):p.goto(base+'/?visit='+secrets.token_hex(4)+'#'+route);expect(p.locator('#main h1')).to_have_text('整车采购办理')
        def action(p,key,id=None):
            loc=p.locator('[data-act=vp-action][data-key='+key+']'+('' if id is None else '[data-id="'+str(id)+'"]'));loc.click();expect(p.locator('#modal')).to_be_visible()
        def upload(p,label,category='evidence'):
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category)
            p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('纯合成验收来源：'+label).encode()})
            harness.save_modal(p);expect(p.locator('#main')).to_contain_text(label+'.txt')
        assert 'totals' not in req(inventory,API+'/orders/'+str(cid)) and current()['totals']['approved_cents']==0
        steps.append('实际库管手机提交车型台数计划，不读取成本、不提前形成实车库存或采购应付')
        visit(manager);upload(manager,'合成采购合同与核价依据','procurement_contract');action(manager,'approve')
        line=current()['lines'][0];manager.locator('#modal [name=cost_'+str(line['id'])+']').fill('100000.01')
        manager.locator('#modal [name=price_'+str(line['id'])+']').fill('120000.00');harness.save_modal(manager)
        action(manager,'request_funds');manager.locator('#modal [name=amount]').fill('200000.02');manager.locator('#modal [name=reason]').fill('按合成采购合同先付全款');harness.save_modal(manager)
        visit(finance);upload(finance,'合成实际银行收退款凭据','receipt')
        def pay(amount,reference,refund=False,original=None):
            visit(finance);action(finance,'refund' if refund else 'pay')
            finance.locator('#modal [name=amount]').fill(amount);finance.locator('#modal [name=account_id]').select_option(str(account['id']))
            finance.locator('#modal [name=reference]').fill(reference)
            if refund:finance.locator('#modal [name=original_payment_id]').select_option(str(original))
            harness.save_modal(finance)
        pay('50000.00','VPAY-1');pay('150000.02','VPAY-2')
        assert current()['totals']['prepaid_cents']==20000002 and current()['totals']['received_quantity']==0
        screens.append(take_screenshot(finance,output,'02_vehicle_prepayment_mobile.png'))
        steps.append('店长按受限合同凭据冻结价格并请款，财务分两笔登记真实付款；未到货金额单列预付')
        visit(inventory);upload(inventory,'合成发运及现场验收凭据');action(inventory,'ship')
        inventory.locator('#modal [name=vin]').fill(VIN);harness.save_modal(inventory);action(inventory,'receive')
        inventory.locator('#modal [name=vin]').fill('LHGCM82633A999999');inventory.locator('#modal [name=location_id]').select_option(str(location['id']))
        inventory.locator('#modal button[type=submit]').click();expect(inventory.locator('#modal .formerror')).to_contain_text('现场VIN与发运VIN不一致')
        screens.append(take_screenshot(inventory,output,'03_vehicle_vin_refusal_mobile.png'))
        inventory.locator('#modal [name=vin]').fill(VIN);harness.save_modal(inventory)
        assert current()['totals']['received_quantity']==1 and current()['totals']['prepaid_cents']==10000001
        assert not req(inventory,API+'/orders/'+str(cid))['payments']
        expect(inventory.locator('#main')).not_to_contain_text('合成采购合同与核价依据.txt')
        assert harness.request(inventory,API+'/reconciliation')['status']==403
        steps.append('库管实际发运后逐VIN验收，错误VIN中文拒绝；入库成本来自冻结核价，库存账号看不到资金或合同文件')
        visit(manager);action(manager,'cancel_remaining');manager.locator('#modal [name=reason]').fill('供应商确认另一台尚未发运并取消');harness.save_modal(manager)
        assert current()['totals']['supplier_refund_due_cents']==10000001
        second_payment=current()['payments'][1]['id'];pay('100000.01','VREFUND-CANCEL',True,second_payment)
        assert current()['state']=='completed'
        visit(inventory);action(inventory,'return_request');inventory.locator('#modal [name=reason]').fill('原车经核对供应缺陷需退回');harness.save_modal(inventory)
        assert req(inventory,'/api/flow/lookup/vehicle')['items']==[]
        visit(manager);action(manager,'return_approve');manager.locator('#modal [name=reason]').fill('核对原入库和原车退回安排');harness.save_modal(manager)
        visit(inventory);action(inventory,'return_dispatch');inventory.locator('#modal [name=reason]').fill('合成原车已与供应商完成实物交接');harness.save_modal(inventory)
        assert current()['totals']['returned_cents']==10000001
        screens.append(take_screenshot(inventory,output,'04_vehicle_return_mobile.png'))
        steps.append('未发运余量取消后形成供应商应退；已入库原车退回须申请、主管批准和库管实际发出，申请即阻断配车')
        first_payment=current()['payments'][0]['id'];pay('50000.00','VREFUND-1',True,first_payment);pay('50000.01','VREFUND-2',True,second_payment)
        assert current()['state']=='completed' and current()['totals']['paid_net_cents']==0
        visit(finance);harness.assert_fits_mobile(finance);screens.append(take_screenshot(finance,output,'05_vehicle_settled_mobile.png'))
        harness.navigate(finance,'vehicle-procurement','整车采购与付款')
        with finance.expect_download() as download:finance.locator('[data-act=vp-export]').click()
        file=output/'synthetic-vehicle-reconciliation.csv';download.value.save_as(file)
        assert len(file.read_text(encoding='utf-8-sig').splitlines())==2
        steps.append('财务按原款和原账户分笔退回，实物与净付款归零；导出同一原账对账集合')
        assert not errors,errors
        return {'mode':'real Chrome HTTP, synthetic vehicle procurement','passed':len(steps),'steps':steps,'screenshots':screens,'javascript_errors':errors,
            'limitations':['仅本地HTTP，不替代正式HTTPS、PostgreSQL并发或公司业务验收','无公司资料、外部转账或真实业务']}
    finally:
        for context in contexts:context.close()

if __name__=='__main__':
    harness.exercise=exercise;harness.main()
