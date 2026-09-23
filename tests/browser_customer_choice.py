"""Actual employee customer choice, owner privacy and mobile browser behavior."""
import secrets
from datetime import date
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login,take_screenshot

def exercise(browser,base,password,output):
    errors=[];screens=[];steps=[];contexts=[];req=harness.checked_request
    def page(width=390):
        ctx=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(ctx);p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440);sales=page()
    try:
        harness.login_page(admin,base,'admin',password)
        phone='13900004321';hidden=req(admin,'/api/flow/master/customers','POST',{'values':{'name':'不可见的其他负责人客户','phone':phone,'contact_allowed':False,'note':'仅合成隐私验证'}},status=201)
        secret=secrets.token_urlsafe(25);req(admin,'/api/users','POST',{'username':'choice-sales','display_name':'合成销售选择客户','role':'sales','password':secret,'store_roles':[{'store_id':1,'role':'sales'}]},status=201);employee_login(sales,base,'choice-sales',secret)
        def begin(name,telephone=phone):
            sales.goto(base+'/?visit='+secrets.token_hex(4)+'#work');expect(sales.locator('[data-act=newcase][data-kind=order]')).to_be_visible(timeout=15000);sales.locator('[data-act=newcase][data-kind=order]').click()
            sales.locator('#modal [name=customer_name]').fill(name)
            if telephone:sales.locator('#modal [name=customer_phone]').fill(telephone)
            sales.locator('#modal [name=model]').fill('合成车型');sales.locator('#modal [name=amount]').fill('10.00');sales.locator('#modal [name=delivery_due]').fill(date.today().isoformat())
        def latest():return req(sales,'/api/flow/cases?kind=order')['items'][0]
        begin('本人首次核对客户');expect(sales.locator('[data-choice-decision]')).to_be_hidden();harness.assert_fits_mobile(sales);harness.save_modal(sales);first=latest()
        assert first['customer_id']!=hidden['id'] and req(sales,'/api/customer-choice/matches?phone='+phone)['items'][0]['id']==first['customer_id']
        assert '不可见的其他负责人客户' not in sales.locator('body').inner_text();steps.append('销售按本人权限无匹配时正常新建；同店他人同电话档案不显示也不造成存在性提示')
        begin('本人首次核对客户');expect(sales.locator('[data-act=choice-select]')).to_be_visible(timeout=10000)
        sales.locator('#modal button[type=submit]').click();expect(sales.locator('#modal .formerror')).to_contain_text('明确选择')
        harness.assert_fits_mobile(sales);screens.append(take_screenshot(sales,output,'01_customer_explicit_choice_mobile.png'))
        sales.locator('[data-act=choice-select]').click();expect(sales.locator('#modal [name=customer_name]')).to_be_disabled();harness.save_modal(sales);second=latest()
        assert second['customer_id']==first['customer_id'];steps.append('同名同电话不会自动复用；本人明确点击已有客户后新业务复用主档，姓名电话不能顺手覆盖')
        begin('同电话另一独立客户');expect(sales.locator('[data-choice-decision]')).to_be_visible();sales.locator('#modal [name=choice_confirm]').check();harness.assert_fits_mobile(sales);screens.append(take_screenshot(sales,output,'02_customer_confirm_independent_mobile.png'));harness.save_modal(sales)
        third=latest();assert third['customer_id'] not in {first['customer_id'],hidden['id']};steps.append('员工明确确认另建时建立独立客户，不合并电话关联和集团身份')
        begin('无电话新客户','');expect(sales.locator('[data-choice-decision]')).to_be_hidden();harness.save_modal(sales);steps.append('没有电话的新客户无需额外确认字段，正常建立业务')
        before=req(sales,'/api/flow/master/customers')['items'];original=next(c for c in before if c['id']==first['customer_id'])
        harness.navigate(sales,'master/customers','客户档案');sales.locator('[data-act=newmaster][data-kind=customers]').click()
        sales.locator('#modal [name=name]').fill('明确另建的独立主档');sales.locator('#modal [name=phone]').fill(phone);sales.locator('#modal [name=note]').fill('独立主档的合成备注')
        expect(sales.locator('[data-choice-decision]')).to_be_visible();assert sales.locator('[data-act=choice-select]').count()==0
        sales.locator('#modal [name=choice_confirm]').check();harness.assert_fits_mobile(sales);screens.append(take_screenshot(sales,output,'03_customer_master_independent_mobile.png'));harness.save_modal(sales)
        after=req(sales,'/api/flow/master/customers')['items'];assert len(after)==len(before)+1
        kept=next(c for c in after if c['id']==original['id']);assert kept['name']==original['name'] and kept['contact_allowed']==original['contact_allowed'] and kept['note']==original['note']
        steps.append('新增主档遇同电话也须明确另建；保存新客户备注和联系偏好不覆盖原档案')
        assert harness.request(sales,'/api/flow/cases','POST',{'request_id':secrets.token_hex(16),'kind':'order','values':{'customer_id':hidden['id'],'model':'隐私测试','amount':'1','delivery_due':date.today().isoformat()}})['status']==404
        req(admin,'/api/stores','POST',{'code':'CHOICE-OTHER','name':'合成客户乙店'},status=201);assert harness.request(admin,'/api/customer-choice/matches?phone='+phone,store='2')['body']['items']==[]
        assert harness.request(admin,'/api/customer-choice/matches?phone='+phone,store='all')['status']==409
        assert not errors,errors
        return {'checks':len(steps),'steps':steps,'screenshots':screens,'javascript_errors':errors,'transport':'actual Chrome HTTP / cookies / CSP','data':'fresh synthetic database; random passwords not retained'}
    except Exception:
        sales.screenshot(path=str(output/'failure_customer_choice.png'),full_page=True);raise
    finally:
        for context in contexts:context.close()

if __name__=='__main__':harness.exercise=exercise;harness.main()
