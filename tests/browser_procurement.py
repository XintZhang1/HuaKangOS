"""Actual HTTP Chrome: three employee roles complete multi-line procurement.

Run: .venv/Scripts/python tests/browser_procurement.py
Reuses the isolated server harness; no existing database or credentials are used.
"""
import secrets
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import (checked_request, request, login_page, navigate,
    save_modal, take_screenshot, assert_fits_mobile)


def exercise(browser, base, initial_password, output):
    contexts=[];errors=[];steps=[];screenshots=[]
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN')
        contexts.append(context);result=context.new_page()
        result.on('pageerror',lambda error:errors.append(str(error)))
        return result
    admin=page(1440)
    try:
        login_page(admin,base,'admin',initial_password)
        supplier=checked_request(admin,'/api/masters/suppliers','POST',{'request_id':secrets.token_hex(16),
            'values':{'code':'BROWSER-SUPPLIER','name':'合成验收供应商','payment_terms_days':30}},status=201)
        items=[checked_request(admin,'/api/flow/master/items','POST',{'values':{
            'sku':'BROWSER-PART-'+str(i),'name':'合成备件'+str(i),'unit':'件','reorder':'0','active':True}},status=201) for i in range(2)]
        account=checked_request(admin,'/api/flow/master/accounts','POST',{'values':{
            'name':'合成供应商结算账户','account_type':'bank','active':True}},status=201)
        employees={}
        for role,label in [('inventory','库管'),('manager','店长'),('finance','财务')]:
            password=secrets.token_urlsafe(24)
            checked_request(admin,'/api/users','POST',{'username':'purchase-'+role,'display_name':'采购验收'+label,
                'role':role,'password':password,'store_roles':[{'store_id':1,'role':role}]},status=201)
            employee=page();login_page(employee,base,'purchase-'+role,password)
            employee.locator('#modal [name=current_password]').fill(password)
            changed=secrets.token_urlsafe(24)
            employee.locator('#modal [name=new_password]').fill(changed);save_modal(employee)
            login_page(employee,base,'purchase-'+role,changed);employees[role]=employee
        inventory,manager,finance=(employees[k] for k in ('inventory','manager','finance'))
        navigate(inventory,'procurement','采购与供应商结算')
        inventory.locator('[data-act=procurement-new]').click()
        inventory.locator('#modal [name=supplier]').select_option(str(supplier['id']))
        inventory.locator('#modal [name=reason]').fill('浏览器合成备货验收')
        line=inventory.locator('[data-purchase-line]').first
        line.locator('[name=item]').select_option(str(items[0]['id']))
        line.locator('[name=quantity]').fill('2.500');line.locator('[name=cost]').fill('1.23')
        inventory.locator('[data-act=procurement-add-line]').click()
        line=inventory.locator('[data-purchase-line]').nth(1)
        line.locator('[name=item]').select_option(str(items[1]['id']))
        line.locator('[name=quantity]').fill('1.000');line.locator('[name=cost]').fill('0.01')
        assert_fits_mobile(inventory);save_modal(inventory)
        expect(inventory.locator('#main h1')).to_have_text('合成验收供应商 · 采购办理')
        row=checked_request(admin,'/api/procurement/orders')['items'][0];case_id=row['id']
        route='procurement/'+str(case_id)
        def current():return checked_request(admin,'/api/procurement/orders/'+str(case_id))
        def visit(employee):
            # Reload also refreshes an unchanged route after another employee acts.
            employee.goto(base+'/?visit='+secrets.token_hex(4)+'#'+route)
            expect(employee.locator('#main h1')).to_have_text('合成验收供应商 · 采购办理')
        def action(employee,key):
            employee.locator('[data-act=procurement-action][data-key='+key+']').click()
            expect(employee.locator('#modal')).to_be_visible()
        def upload(employee,label,category='evidence'):
            employee.locator('[data-act=upload]').click()
            employee.locator('#modal [name=category]').select_option(category)
            employee.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain',
                'buffer':('独立合成验收凭据：'+label).encode('utf-8')})
            save_modal(employee)
            expect(employee.locator('#main')).to_contain_text(label+'.txt')
        def payment(amount,reference,refund=False):
            visit(finance);action(finance,'refund' if refund else 'pay')
            finance.locator('#modal [name=amount]').fill(amount)
            finance.locator('#modal [name=account_id]').select_option(str(account['id']))
            finance.locator('#modal [name=reference]').fill(reference)
            files=checked_request(admin,'/api/flow/cases/'+str(case_id))['files']
            finance.locator('#modal [name=evidence_id]').select_option(str(next(f['id'] for f in files if f['category']=='receipt')))
            if refund:finance.locator('#modal [name=original_payment_id]').select_option(str(current()['payments'][0]['id']))
            save_modal(finance)
        assert current()['totals']['payable_cents']==0
        assert request(inventory,'/api/procurement/payables')['status']==403
        assert not inventory.locator('[data-key=approve]').count()
        steps.append('库管员工使用手机多行申请；申请未形成库存、现金或应付；库管不能查看财务对账')
        visit(manager);action(manager,'approve');save_modal(manager)
        visit(inventory);upload(inventory,'首批到货验收')
        row=current();action(inventory,'receive')
        inventory.locator('#modal [name=quantity_'+str(row['lines'][0]['id'])+']').fill('9.000')
        inventory.locator('#modal button[type=submit]').click()
        expect(inventory.locator('#modal .formerror')).to_contain_text('验收数量超过')
        assert current()['totals']['payable_cents']==0
        assert_fits_mobile(inventory)
        screenshots.append(take_screenshot(inventory,output,'00_mobile_over_receipt_refused.png'))
        steps.append('库管超量验收被中文说明拒绝，表单保留且未形成库存或应付，再核对修改本次数量')
        inventory.locator('#modal [name=quantity_'+str(row['lines'][0]['id'])+']').fill('1.000')
        save_modal(inventory);assert current()['totals']['payable_cents']==123
        assert_fits_mobile(inventory)
        screenshots.append(take_screenshot(inventory,output,'01_mobile_partial_receipt.png'))
        steps.append('独立店长批准，库管上传实际凭据并只验收首批；实际应付为 1.23 元')
        visit(finance);upload(finance,'实际供应商付款','receipt')
        payment('1.00','BROWSER-PAY-1');assert current()['totals']['payable_cents']==23
        visit(inventory);action(inventory,'receive');row=current()
        for line in row['lines']:
            remaining=line['quantity_milli']-line['received_milli']
            if remaining:inventory.locator('#modal [name=quantity_'+str(line['id'])+']').fill(f'{remaining/1000:.3f}')
        save_modal(inventory);assert current()['totals']['payable_cents']==209
        payment('2.09','BROWSER-PAY-2');assert current()['state']=='completed'
        steps.append('财务分笔实际付款；库管补齐两行到货，库存与 3.09 元净付款完全核对')
        visit(inventory);upload(inventory,'退回原批次实物凭据');action(inventory,'return_request')
        receipt=current()['receipts'][0]
        inventory.locator('#modal [name=quantity_'+str(receipt['id'])+']').fill('0.500')
        inventory.locator('#modal [name=reason]').fill('合成验收原批次退货');save_modal(inventory)
        assert current()['totals']['returned_cents']==0
        visit(manager);action(manager,'return_approve')
        manager.locator('#modal [name=reason]').fill('主管已核对原批次及退货数量');save_modal(manager)
        assert current()['totals']['returned_cents']==0
        visit(inventory);action(inventory,'return_dispatch')
        files=checked_request(admin,'/api/flow/cases/'+str(case_id))['files']
        inventory.locator('#modal [name=evidence_id]').select_option(str(next(f['id'] for f in files if f['name']=='退回原批次实物凭据.txt')))
        save_modal(inventory)
        assert current()['totals']['supplier_refund_due_cents']==62
        assert_fits_mobile(inventory)
        screenshots.append(take_screenshot(inventory,output,'02_mobile_physical_return.png'))
        steps.append('库管申请退货、店长独立批准均不出库存；库管确认实物发出才减少原批次 0.500 件及 0.62 元')
        payment('0.62','BROWSER-REFUND-1',True)
        final=current();assert final['state']=='completed'
        assert final['totals']['paid_net_cents']==247 and final['totals']['supplier_refund_due_cents']==0
        assert final['payments'][-1]['original_id']==final['payments'][0]['id']
        assert_fits_mobile(finance)
        screenshots.append(take_screenshot(finance,output,'03_mobile_original_account_refund.png'))
        with finance.expect_download() as download:
            navigate(finance,'procurement','采购与供应商结算')
            finance.locator('[data-act=procurement-export]').click()
        text=__import__('pathlib').Path(download.value.path()).read_text(encoding='utf-8-sig')
        assert '合成验收供应商' in text and '247' in text
        steps.append('财务按原付款及原账户登记退款，净付款 2.47 元；浏览器下载 CSV 与原单账本一致')
        assert not errors,errors
        return {'mode':'real_http_chrome','file_scan_mode':'structure_only','viewport':'390x844',
            'checks_passed':len(steps),'steps':steps,'javascript_errors':errors,'screenshots':screenshots,
            'net_paid_cents':247,'received_cents':309,'returned_cents':62}
    finally:
        for context in contexts:context.close()


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
