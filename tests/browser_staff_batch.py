"""Owner-run real-browser check of batch staff creation and its administrator-only rule.

python tests/browser_staff_batch.py [--screenshots OUTSIDE_REPOSITORY]
Only the standard harness's NEW synthetic database and owned local server are used.
This script has not been treated as passed merely because it compiles.
"""
import secrets
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login


def exercise(browser,base,password,output):
    context=browser.new_context(viewport={'width':390,'height':844},locale='zh-CN')
    page=context.new_page();errors=[];steps=[];images=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    req=harness.checked_request;suffix=secrets.token_hex(3)
    sales='staff-sales-'+suffix;stock='staff-stock-'+suffix;manager='staff-mgr-'+suffix
    staff_password=secrets.token_urlsafe(28)
    manager_context=None
    try:
        harness.login_page(page,base,'admin',password)
        harness.navigate(page,'users','员工账号')
        expect(page.locator('#main [data-act=batchusers]')).to_be_visible()
        page.locator('#main [data-act=batchusers]').click()
        rows=f'陆销售｜{sales}｜销售\n何库管｜{stock}｜库管'
        page.locator('#modal [name=rows]').fill(rows)
        page.locator('#modal [name=password]').fill(staff_password)
        preview=page.locator('#staff-batch-preview');submit=page.locator('#modal button[type=submit]')
        expect(preview).to_contain_text('都可以建立')
        harness.assert_fits_mobile(page)
        images.append(harness.take_screenshot(page,output,'staff_batch_01_paste_preview_mobile.png'))
        page.locator('#modal [name=rows]').fill(rows+'\n坏行')
        expect(preview).to_contain_text('要先改好')
        expect(submit).to_be_disabled()
        page.locator('#modal [name=rows]').fill(f'第二个管理员｜staff-admin-{suffix}｜系统管理员')
        expect(preview).to_contain_text('系统管理员账号请用“新增员工”单独建立')
        page.locator('#modal [name=rows]').fill(f'陆销售｜{sales}｜销售\n何库管｜{stock}｜库管')
        expect(preview).to_contain_text('都可以建立')
        submit.click()
        expect(page.locator('#toast')).to_contain_text('已新增 2 个账号')
        expect(page.locator('#main')).to_contain_text(sales)
        listing={row['username']:row for row in req(page,'/api/users')['items']}
        assert listing[sales]['role']=='sales' and listing[stock]['role']=='inventory',listing[sales]
        assert listing[sales]['stores'][0]['name']==listing[stock]['stores'][0]['name']
        assert listing[sales]['must_change_password'] is True and listing[stock]['must_change_password'] is True
        audit=req(page,'/api/audit?page=1')['items']
        assert sum(1 for row in audit if row['action']=='create_user')>=2,audit[:3]
        steps.append('管理员在真实界面粘贴两行并逐行预览后一次建立；门店岗位、首登改密与审计记录都成立')
        harness.assert_fits_mobile(page)
        images.append(harness.take_screenshot(page,output,'staff_batch_02_created_mobile.png'))
        req(page,'/api/users','POST',{'username':manager,'display_name':'合成店长'+suffix,'role':'manager',
            'password':staff_password,'store_ids':[1],'store_roles':[{'store_id':1,'role':'manager'}]},status=201)
        manager_context=browser.new_context(viewport={'width':390,'height':844},locale='zh-CN')
        other=manager_context.new_page();other.on('pageerror',lambda error:errors.append(str(error)))
        employee_login(other,base,manager,staff_password)
        assert other.locator('a[href="#users"]').count()==0
        harness.navigate(other,'work','我的工作')
        assert other.locator('[data-act=batchusers]').count()==0
        refused=harness.request(other,'/api/users/batch','POST',
            {'store_id':1,'password':staff_password,'rows':[{'username':'mgr-batch-'+suffix,'display_name':'店长越权','role':'sales'}]})
        assert refused['status']==403 and '仅系统管理员' in refused['body']['detail'],refused
        single=harness.request(other,'/api/users','POST',
            {'username':'mgr-single-'+suffix,'display_name':'店长越权单建','role':'sales','password':staff_password,'store_ids':[1]})
        assert single['status']==403,single
        steps.append('店长既看不到入口，直接调用接口也被 403 拒绝；批量新增没有打开第二条权限路径')
        steps.append('批量对话框拒绝坏行与系统管理员行，提交前必须先核对预览')
        assert not errors,errors
        return {'status':'passed','mode':'actual-browser-http','synthetic_only':True,
                'steps':steps,'screenshots':images,'javascript_errors':errors,'viewport':'390x844'}
    finally:
        if manager_context:manager_context.close()
        context.close()


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
