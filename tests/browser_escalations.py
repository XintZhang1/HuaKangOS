"""Owner-run real-browser check of the escalation page (提交、待我评审、登记结果).

python tests/browser_escalations.py [--screenshots OUTSIDE_REPOSITORY]
Only the standard harness's NEW synthetic database and owned local server are used.
This script has not been treated as passed merely because it compiles.
"""
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login


def exercise(browser, base, password, output):
    steps, images, errors = [], [], []
    admin_ctx = browser.new_context(viewport={'width': 390, 'height': 844}, locale='zh-CN')
    admin = admin_ctx.new_page()
    admin.on('pageerror', lambda error: errors.append(str(error)))
    req = harness.checked_request
    sales_ctx = mgr_ctx = None
    try:
        harness.login_page(admin, base, 'admin', password)
        for username, display, role, initial in (('esc-sales', '试用销售', 'sales', 'Xc-Trial-Password-01'),
                                                 ('esc-manager', '试用店长', 'manager', 'Xc-Trial-Password-02')):
            req(admin, '/api/users', 'POST', {'username': username, 'display_name': display, 'role': role,
                                              'password': initial, 'store_ids': [1],
                                              'store_roles': [{'store_id': 1, 'role': role}]}, status=201)
        sales_ctx = browser.new_context(viewport={'width': 390, 'height': 844}, locale='zh-CN')
        sales = sales_ctx.new_page()
        sales.on('pageerror', lambda error: errors.append(str(error)))
        sales_password = employee_login(sales, base, 'esc-sales', 'Xc-Trial-Password-01')
        assert sales_password
        assert sales.locator('a[href="#escalations"]').count() == 1
        harness.navigate(sales, 'escalations', '评审申请')
        assert sales.locator('[data-act=esctab]').count() == 1, '员工不应看到待我评审页签'
        sales.locator('[data-act=escnew]').click()
        sales.locator('#modal [name=subject]').fill('给这张单批准 5% 折扣')
        sales.locator('#modal [name=case_reference]').fill('XC-R09-01')
        sales.locator('#modal [name=blocked_message]').fill('没有该模块的操作权限，请联系店长')
        sales.locator('#modal [name=reason_category]').select_option('authority')
        harness.save_modal(sales)
        expect(sales.locator('#main')).to_contain_text('给这张单批准 5% 折扣')
        expect(sales.locator('#main')).to_contain_text('待处理')
        harness.assert_fits_mobile(sales)
        images.append(harness.take_screenshot(sales, output, 'escalation_01_employee_submitted.png'))
        steps.append('销售提交评审申请，列表显示待处理，且看不到“待我评审”页签')
        mgr_ctx = browser.new_context(viewport={'width': 390, 'height': 844}, locale='zh-CN')
        mgr = mgr_ctx.new_page()
        mgr.on('pageerror', lambda error: errors.append(str(error)))
        manager_password = employee_login(mgr, base, 'esc-manager', 'Xc-Trial-Password-02')
        assert manager_password
        harness.navigate(mgr, 'escalations', '评审申请')
        mgr.locator('[data-act=esctab][data-scope=to_review]').click()
        expect(mgr.locator('#main')).to_contain_text('给这张单批准 5% 折扣')
        steps.append('店长在“待我评审”里看到本店同事的申请')
        mgr.locator('[data-act=escview]').first.click()
        expect(mgr.locator('#modal')).to_contain_text('没有该模块的操作权限')
        expect(mgr.locator('#modal')).to_contain_text('岗位权限不足')
        mgr.locator('#modal').get_by_role('button', name='×').click()
        steps.append('查看详情能看到系统提示原文与类别')
        mgr.locator('[data-act=escclaim]').first.click()
        expect(mgr.locator('#main')).to_contain_text('已接手')
        mgr.locator('[data-act=escdone]').first.click()
        mgr.locator('#modal [name=note]').fill('已在原单批准 5% 折扣')
        harness.save_modal(mgr)
        assert req(mgr, '/api/escalations?scope=to_review')['items'] == []
        expect(mgr.locator('#main')).to_contain_text('评审申请')
        harness.assert_fits_mobile(mgr)
        images.append(harness.take_screenshot(mgr, output, 'escalation_02_manager_done.png'))
        steps.append('店长登记“已办理”并写明结果，该申请随即从待评审队列移除')
        # Same hash would not re-render: reload the employee page to read the current state.
        sales.reload()
        expect(sales.locator('#main h1')).to_have_text('评审申请')
        expect(sales.locator('#main')).to_contain_text('已办理')
        sales.locator('[data-act=escview]').first.click()
        expect(sales.locator('#modal')).to_contain_text('已在原单批准 5% 折扣')
        sales.locator('#modal').get_by_role('button', name='×').click()
        assert sales.locator('[data-act=escclaim]').count() == 0
        steps.append('申请人看到“已办理”与处理结果，且没有越权按钮')
        assert not errors, errors
        return {'status': 'passed', 'mode': 'actual-browser-http', 'synthetic_only': True,
                'steps': steps, 'screenshots': images, 'javascript_errors': errors, 'viewport': '390x844'}
    finally:
        for context in (mgr_ctx, sales_ctx, admin_ctx):
            if context:
                context.close()


if __name__ == '__main__':
    harness.exercise = exercise
    harness.main()
