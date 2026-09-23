"""Real Chrome store-context races, using only the harness's isolated database.

python tests/browser_store_switch.py [--screenshots OUTSIDE_REPOSITORY]
Delays/failures are browser network fixtures, never a production service change.
"""
import secrets
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login


def exercise(browser, base, password, output):
    contexts, errors, steps, screenshots = [], [], [], []
    req = harness.checked_request

    def new_page():
        context = browser.new_context(viewport={'width': 390, 'height': 844}, locale='zh-CN')
        contexts.append(context)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        return page

    def settled(page, store, heading='我的工作'):
        page.wait_for_function("sid=>!state.storeSwitch && String(state.store)===String(sid) && String(state.user.active_store_id)===String(sid)", arg=store)
        expect(page.locator('#main h1')).to_have_text(heading)

    def captured(page, held):
        for _ in range(100):
            if held:
                return held.pop(0)
            page.wait_for_timeout(20)
        raise AssertionError('Expected isolated delayed request was not captured')

    admin = new_page()
    try:
        suffix = secrets.token_hex(4)
        harness.login_page(admin, base, 'admin', password)
        stores = [1] + [req(admin, '/api/stores', 'POST', {
            'code': f'SW-{i}-{suffix}', 'name': f'合成换店{i}', 'active': True}, status=201)['id'] for i in [2, 3]]
        username, initial = 'switch-' + suffix, secrets.token_urlsafe(28)
        req(admin, '/api/users', 'POST', {'username': username, 'display_name': '合成多岗位员工',
            'role': 'manager', 'password': initial,
            'store_roles': [{'store_id': sid, 'role': role} for sid, role in zip(stores, ['manager', 'service', 'finance'])]}, status=201)
        for sid in stores:
            req(admin, '/api/dictionaries/repair', 'POST', {'request_id': secrets.token_hex(16),
                'values': {'name': f'仅门店{sid}条目', 'detail': '合成换店隔离验证', 'active': True}}, store=sid, status=201)
        page = new_page(); employee_login(page, base, username, initial)
        settled(page, 1)
        harness.navigate(page, 'dictionaries/repair', '维修字典')
        expect(page.locator('#main')).to_contain_text('仅门店1条目')

        held, controls = [], {'delay_store': str(stores[1]), 'fail_target': False, 'fail_all': False}

        def auth_route(route):
            sid = route.request.headers.get('x-store-id')
            if controls['fail_all'] or (controls['fail_target'] and sid == str(stores[1])):
                route.fulfill(status=503 if controls['fail_all'] else 403,
                    content_type='application/json', body='{"detail":"合成换店拒绝"}')
            elif sid == controls['delay_store']:
                held.append(route)
            else:
                route.continue_()

        page.route('**/api/auth/me', auth_route)
        page.locator('#store').select_option(str(stores[1]))
        pending = captured(page, held)
        expect(page.locator('#main h1')).to_have_text('正在切换门店')
        expect(page.locator('#main')).not_to_contain_text('仅门店1条目')
        assert page.locator('[data-act=dictionary-new]').count() == 0
        page.evaluate("()=>go('dictionaries/repair')")
        page.wait_for_function("()=>state.storeSwitch?.route==='dictionaries/repair'")
        assert page.evaluate('()=>state.user.role') == 'manager'
        harness.assert_fits_mobile(page)
        screenshots.append(harness.take_screenshot(page, output, 'store_switch_01_waiting_mobile.png'))
        controls['delay_store'] = None; pending.continue_()
        settled(page, stores[1], '维修字典')
        assert page.evaluate('()=>state.user.role') == 'service'
        expect(page.locator('#main')).to_contain_text(f'仅门店{stores[1]}条目')
        expect(page.locator('#main')).not_to_contain_text('仅门店1条目')
        steps.append('延迟换店期间立即移除原店资料；完成后以新岗位打开最新字典导航')

        controls['delay_store'] = '1'
        page.locator('#store').select_option('1'); older = captured(page, held)
        page.locator('#store').select_option(str(stores[2]))
        # The selected dictionary hash already exists, so use the application's
        # navigation action (assigning the same browser hash fires no event).
        page.evaluate("()=>go('dictionaries/repair')")
        settled(page, stores[2], '维修字典')
        controls['delay_store'] = None; older.continue_()
        page.wait_for_timeout(150)
        settled(page, stores[2], '维修字典')
        assert page.evaluate('()=>state.user.role') == 'finance'
        expect(page.locator('#main')).to_contain_text(f'仅门店{stores[2]}条目')
        steps.append('快速连续换店仅提交最后目标；迟到的前一次身份响应不能回滚页面')

        stale = []
        page.route('**/api/dictionaries/repair?*', lambda route: stale.append((route, route.fetch())))
        page.evaluate("()=>go('dictionaries/repair')")
        old_route, old_response = captured(page, stale)
        page.locator('#store').select_option('1')
        settled(page, 1)
        page.unroute('**/api/dictionaries/repair?*')
        old_route.fulfill(response=old_response)
        page.wait_for_timeout(150)
        settled(page, 1)
        expect(page.locator('#main')).not_to_contain_text(f'仅门店{stores[2]}条目')
        assert page.evaluate('()=>state.row') is None
        steps.append('真实原店业务读取迟到也不回填新店缓存或页面')

        controls['fail_target'] = True
        page.locator('#store').select_option(str(stores[1]))
        page.evaluate("()=>{location.hash='case/999999'}")
        settled(page, 1)
        assert page.evaluate('()=>state.user.role') == 'manager'
        expect(page.locator('#toast')).to_contain_text('已返回原门店')
        screenshots.append(harness.take_screenshot(page, output, 'store_switch_02_recovered_mobile.png'))
        steps.append('目标门店拒绝时重新读取原店身份和全部目录，舍弃目标原单导航')

        controls['fail_target'] = False; controls['fail_all'] = True
        page.locator('#store').select_option(str(stores[1]))
        expect(page.locator('#main h1')).to_have_text('暂时无法切换门店')
        assert page.locator('.navlink').count() == 0
        screenshots.append(harness.take_screenshot(page, output, 'store_switch_03_recovery_failed_mobile.png'))
        controls['fail_all'] = False
        page.locator('[data-act=store-retry]').click()
        settled(page, 1)
        harness.navigate(page, 'dictionaries/repair', '维修字典')
        expect(page.locator('#main')).to_contain_text('仅门店1条目')
        harness.assert_fits_mobile(page)
        screenshots.append(harness.take_screenshot(page, output, 'store_switch_04_retry_mobile.png'))
        steps.append('原店恢复也失败时保持阻断；明确重试后才重新显示原店资料')
        assert not errors, errors
        return {'status': 'passed', 'mode': 'actual-browser-http', 'synthetic_only': True,
            'viewport': '390x844', 'steps': steps, 'screenshots': screenshots,
            'javascript_errors': errors, 'employee_roles': ['manager', 'service', 'finance'],
            'network_fixtures': 'delayed responses and explicit 403/503 in isolated browser only'}
    finally:
        for context in contexts:
            context.close()


if __name__ == '__main__':
    harness.exercise = exercise
    harness.main()
