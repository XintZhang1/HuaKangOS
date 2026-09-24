"""Owner-run real-browser check: deactivating the store you work in must recover, not dead-end.

python tests/browser_store_deactivation.py [--screenshots OUTSIDE_REPOSITORY]
Only the standard harness's NEW synthetic database and owned local server are used.
This script has not been treated as passed merely because it compiles.
"""
import secrets
from playwright.sync_api import expect
import browser_huakangos as harness


def exercise(browser,base,password,output):
    context=browser.new_context(viewport={'width':390,'height':844},locale='zh-CN')
    page=context.new_page();errors=[];steps=[];images=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    req=harness.checked_request;suffix=secrets.token_hex(3)
    def current_store():
        return str(page.evaluate('()=>state.store'))
    def wait_for_store(store_id,tries=60):
        # The top-bar select switches asynchronously; the test thread does not block on it.
        for _ in range(tries):
            if current_store()==str(store_id):return True
            page.wait_for_timeout(200)
        return False
    def usable(store_id):
        # A 200 here is the check that failed for the reporting employee before the fix.
        return harness.request(page,'/api/flow/catalog',store=int(store_id))['status']==200
    try:
        harness.login_page(page,base,'admin',password)
        doomed=req(page,'/api/stores','POST',{'code':'DROP-'+suffix,'name':'即将停用的门店','active':True},status=201)['id']
        page.reload();expect(page.locator('#store')).to_be_visible()
        page.locator('#store').select_option(str(doomed))
        assert wait_for_store(doomed),'切换到新门店没有生效'
        assert usable(doomed),'新门店一开始应当可用'
        harness.navigate(page,'stores','门店设置')
        page.locator(f'[data-act=editstore][data-id="{doomed}"]').click()
        page.locator('#modal [name=active]').uncheck()
        harness.save_modal(page)
        # The page has to move itself to a usable store and say so, not report a permission problem.
        expect(page.locator('#toast')).to_contain_text('当前门店已停用')
        expect(page.locator('#main')).not_to_contain_text('没有该门店的访问权限')
        expect(page.locator('#store')).not_to_have_value(str(doomed))
        current=current_store()
        assert current and current!=str(doomed),current
        assert usable(current),'切换后的门店必须可以直接办理'
        steps.append('在真实界面停用当前门店后，页面自动切到可用门店并说明原因，没有出现“没有该门店的访问权限”，切换后的门店可直接办理')
        images.append(harness.take_screenshot(page,output,'store_deactivation_01_switched_mobile.png'))
        harness.navigate(page,'users','员工账号')
        expect(page.locator('#main')).to_contain_text('员工账号')
        steps.append('切换后的门店上下文可继续办理（员工账号页正常读取）')
        # A hard reload of the old address must also come back usable, without logging in again.
        page.goto(base+'/#stores');expect(page.locator('#main h1')).to_have_text('门店设置')
        assert current_store()==current and usable(current)
        steps.append('直接刷新页面仍从可用门店开始，不需要重新登录')
        # Restoring the store and switching back still works.
        harness.navigate(page,'stores','门店设置')
        page.locator(f'[data-act=editstore][data-id="{doomed}"]').click()
        page.locator('#modal [name=active]').check()
        harness.save_modal(page)
        page.locator('#store').select_option(str(doomed))
        assert wait_for_store(doomed),'重新启用后切回该门店没有生效'
        assert usable(doomed)
        steps.append('重新启用后可以正常切回该门店')
        harness.assert_fits_mobile(page)
        images.append(harness.take_screenshot(page,output,'store_deactivation_02_restored_mobile.png'))
        assert not errors,errors
        return {'status':'passed','mode':'actual-browser-http','synthetic_only':True,
                'steps':steps,'screenshots':images,'javascript_errors':errors,'viewport':'390x844'}
    finally:
        context.close()


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
