"""Real Chrome employee prepayment loop on a new temporary DB and random port."""
import secrets
from pathlib import Path
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request,login_page,save_modal,assert_fits_mobile,take_screenshot,navigate


def exercise(browser,base,initial_password,output):
    contexts=[];errors=[];screenshots=[];steps=[]
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(context)
        p=context.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440)
    try:
        login_page(admin,base,'admin',initial_password)
        supplier=checked_request(admin,'/api/masters/suppliers','POST',{'request_id':secrets.token_hex(16),'values':{'code':'PREPAY-BROWSER','name':'合成预付款供应商','payment_terms_days':30}},status=201)
        item=checked_request(admin,'/api/flow/master/items','POST',{'values':{'sku':'PREPAY-ITEM','name':'合成预付物资','unit':'件','reorder':'0','active':True}},status=201)
        account=checked_request(admin,'/api/flow/master/accounts','POST',{'values':{'name':'合成预付原账户','account_type':'bank','active':True}},status=201)
        row=checked_request(admin,'/api/procurement/orders','POST',{'request_id':secrets.token_hex(16),'supplier_id':supplier['id'],'reason':'真实界面合成预付流程','lines':[{'item_id':item['id'],'quantity_milli':2500,'unit_cost_cents':123}]},status=201)
        employees={}
        for role,label in [('inventory','库管'),('manager','店长'),('finance','财务')]:
            password=secrets.token_urlsafe(24)
            checked_request(admin,'/api/users','POST',{'username':'prepay-'+role,'display_name':'预付验收'+label,'role':role,'password':password,'store_roles':[{'store_id':1,'role':role}]},status=201)
            employee=page();login_page(employee,base,'prepay-'+role,password)
            employee.locator('#modal [name=current_password]').fill(password);changed=secrets.token_urlsafe(24)
            employee.locator('#modal [name=new_password]').fill(changed);save_modal(employee)
            login_page(employee,base,'prepay-'+role,changed);employees[role]=employee
        manager,finance,inventory=(employees[k] for k in ('manager','finance','inventory'))
        cid=row['id'];route='procurement/'+str(cid)
        def current():return checked_request(admin,'/api/procurement/orders/'+str(cid))
        def visit(employee):
            employee.goto(base+'/?visit='+secrets.token_hex(4)+'#'+route)
            expect(employee.locator('#main h1')).to_have_text('合成预付款供应商 · 采购办理')
        def act(employee,key):
            employee.locator('[data-act=procurement-action][data-key='+key+']').click();expect(employee.locator('#modal')).to_be_visible()
        def upload(employee,name,category='receipt'):
            employee.locator('[data-act=upload]').click();employee.locator('#modal [name=category]').select_option(category)
            employee.locator('#modal [name=file]').set_input_files({'name':name+'.txt','mimeType':'text/plain','buffer':('合成独立凭据'+name).encode()})
            save_modal(employee)
            return next(f['id'] for f in checked_request(admin,'/api/flow/cases/'+str(cid))['files'] if f['name']==name+'.txt')
        visit(manager);act(manager,'approve');save_modal(manager)
        visit(finance);proof=upload(finance,'预付款合同与实际银行凭据')
        act(finance,'prepay_request');finance.locator('#modal [name=amount]').fill('3.08')
        finance.locator('#modal [name=reason]').fill('按原采购合同申请首付款')
        finance.locator('#modal [name=evidence_id]').select_option(str(proof));save_modal(finance)
        assert current()['totals']['paid_net_cents']==0
        assert not finance.locator('[data-key=prepay_approve]').count()
        steps.append('财务员工申请；申请不产生现金，申请人看不到自批按钮')
        visit(manager);act(manager,'prepay_approve');manager.locator('#modal [name=reason]').fill('本人独立核对原采购付款条件')
        manager.locator('#modal [name=evidence_id]').select_option(str(proof));save_modal(manager)
        assert current()['totals']['paid_net_cents']==0
        visit(finance);act(finance,'prepay_pay')
        finance.locator('#modal [name=account_id]').select_option(str(account['id']))
        finance.locator('#modal [name=reference]').fill('PREPAY-REAL-BROWSER-1')
        finance.locator('#modal [name=evidence_id]').select_option(str(proof))
        finance.locator('#modal button[type=submit]').click()
        expect(finance.locator('#modal .formerror')).to_contain_text('请本人明确勾选已核对实际付款')
        assert current()['totals']['paid_net_cents']==0
        finance.locator('#modal [name=confirmed]').check();assert_fits_mobile(finance)
        screenshots.append(take_screenshot(finance,output,'01_employee_actual_prepayment_confirmation.png'))
        save_modal(finance);assert current()['totals']['prepaid_cents']==308
        steps.append('独立店长批准后仍无现金；财务未勾实际付款明确确认被中文拒绝，勾选后只登记308分')
        visit(inventory);proof_goods=upload(inventory,'首批实际到货','evidence')
        assert not inventory.locator('[data-key=prepay_pay]').count()
        assert 'prepayments' not in checked_request(inventory,'/api/procurement/orders/'+str(cid))
        act(inventory,'receive');inventory.locator('#modal [name=quantity_'+str(row['lines'][0]['id'])+']').fill('1.000');save_modal(inventory)
        assert current()['totals']['applied_cents']==123 and current()['totals']['prepaid_cents']==185
        visit(manager);act(manager,'close_receiving');manager.locator('#modal [name=reason]').fill('双方已明确其余货物不再供货');save_modal(manager)
        assert current()['totals']['supplier_refund_due_cents']==185
        def refund(amount,reference):
            visit(finance);act(finance,'refund');finance.locator('#modal [name=amount]').fill(amount)
            finance.locator('#modal [name=account_id]').select_option(str(account['id']))
            finance.locator('#modal [name=reference]').fill(reference);finance.locator('#modal [name=evidence_id]').select_option(str(proof))
            finance.locator('#modal [name=original_payment_id]').select_option(str(current()['payments'][0]['id']));save_modal(finance)
        refund('1.85','PREPAY-REFUND-UNUSED');assert current()['totals']['paid_net_cents']==123
        steps.append('库管部分到货只抵用123分且不见财务数据；店长终止未到余量后财务原路实退185分')
        visit(inventory);act(inventory,'return_request');receipt=current()['receipts'][0]
        inventory.locator('#modal [name=quantity_'+str(receipt['id'])+']').fill('0.500');inventory.locator('#modal [name=reason]').fill('核对原批实际退回半件');save_modal(inventory)
        visit(manager);act(manager,'return_approve');manager.locator('#modal [name=reason]').fill('核对原批次可退数量');save_modal(manager)
        visit(inventory);act(inventory,'return_dispatch');inventory.locator('#modal [name=evidence_id]').select_option(str(proof_goods));save_modal(inventory)
        assert current()['totals']['supplier_refund_due_cents']==62
        refund('0.62','PREPAY-REFUND-RETURN');final=current()
        assert final['totals']['paid_net_cents']==final['totals']['applied_cents']==61 and final['state']=='completed'
        assert final['totals']['prepaid_cents']==final['totals']['supplier_refund_due_cents']==0
        assert_fits_mobile(finance);screenshots.append(take_screenshot(finance,output,'02_employee_original_return_refund.png'))
        with finance.expect_download() as download:
            navigate(finance,'procurement','采购与供应商结算');finance.locator('[data-act=procurement-export]').click()
        exported=Path(download.value.path()).read_text(encoding='utf-8-sig')
        assert '有效预付（分）' in exported and '合成预付款供应商' in exported and ',61,' in exported
        steps.append('原批实退62分后原付款再实退62分，净现金和抵用均61分；手机页面与实际下载CSV一致')
        assert not errors,errors
        return dict(mode='real_http_chrome',file_scan_mode='structure_only',viewport='390x844',checks_passed=len(steps),steps=steps,screenshots=screenshots,javascript_errors=errors,net_paid_cents=61)
    except Exception:
        for role,p in locals().get('employees',{}).items():take_screenshot(p,output,'failure_'+role+'.png')
        raise
    finally:
        for context in contexts:context.close()


if __name__=='__main__':
    harness.exercise=exercise;harness.main()
