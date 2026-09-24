"""Actual employee Chrome checks for search, help and unsent assistant drafts.

Only a fresh synthetic database and random local port are used. No model is
called. The walkthrough screenshots show entry points, not all business steps.
Run: python tests/browser_workflow_guides.py --screenshots OUTSIDE_REPOSITORY
"""
import json
from pathlib import Path
import secrets
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import expect
from scripts.capture_workflow_guides import employee, mark_demo, read_entry, seed
from tests import browser_huakangos as h


def exercise(browser, base, password, output):
    assert urlsplit(base).hostname == '127.0.0.1' and urlsplit(base).port != 8000
    catalogue = json.loads((ROOT / 'web/workflow-guides.json').read_text(encoding='utf-8'))
    lead = next(row for row in catalogue['workflows'] if row['id'] == 'wf-reception')
    restricted = next(row for row in catalogue['workflows'] if 'sales' not in row['entry']['roles'] and row['entry']['mode'] == 'write')
    errors, shots, steps, mutations, recommendations = [], [], [], [], []
    keyboard_probe = {}
    admin_context = browser.new_context(viewport={'width': 1440, 'height': 1000}, locale='zh-CN')
    admin = admin_context.new_page()
    employee_context = None
    try:
        h.login_page(admin, base, 'admin', password)
        seed(admin)
        second = h.checked_request(admin, '/api/stores', 'POST', {'code': 'GUIDE-TWO', 'name': '合成演示乙店'}, status=201)
        employee_context, page = employee(browser, admin, base, 'sales', errors,
                                           {'width': 390, 'height': 844}, (1, second['id']))
        def record_request(request):
            path = urlsplit(request.url).path
            if request.method not in ('GET', 'HEAD', 'OPTIONS') and path.startswith('/api/'):
                target = recommendations if path == '/api/workflow-guides/recommendations' else mutations
                target.append({'method': request.method, 'path': path})
        page.on('request', record_request)

        page.locator('#workflow-top-search').click()
        page.locator('[data-wf-action=browse]').click()
        expect(page.locator('#main h1')).to_have_text('操作指引')
        expect(page.locator('#workflow-guide-results .wf-card')).to_have_count(len(catalogue['workflows']))
        page.locator('#workflow-guide-query').fill('HK-001')
        expect(page.locator('#workflow-guide-results .wf-card')).to_have_count(1)
        expect(page.locator('#workflow-guide-results .wf-card')).to_contain_text(lead['title'])
        page.locator('#workflow-guide-query').fill('')
        page.locator('#workflow-guide-category').select_option(lead['category'])
        categories = page.locator('#workflow-guide-results .wf-card>span').all_text_contents()
        assert categories and set(categories) == {lead['category']}
        steps.append('全部操作指引显示完整目录；需求编号搜索和业务分类筛选实际生效。')

        def search(query, workflow):
            page.locator('#workflow-top-search').click()
            expect(page.locator('#workflow-search-dialog')).to_be_visible()
            page.locator('#workflow-search-input').fill(query)
            result = page.locator(f'[role=option][data-wf-action=result][data-id="{workflow["id"]}"]')
            expect(result).to_be_visible()
            result.click()
            expect(page.locator('#main h1')).to_have_text(workflow['title'])
            expect(page.locator('#workflow-search-dialog')).to_have_count(0)

        search('安排接待回访', lead)
        h.assert_fits_mobile(page)
        image = page.locator('.wf-figure img')
        expect(image).to_be_visible()
        image.scroll_into_view_if_needed()
        page.wait_for_function("() => [...document.querySelectorAll('.wf-figure img')].every(i=>i.complete&&i.naturalWidth>0)")
        image.click()
        expect(page.locator('.wf-image-dialog')).to_be_visible()
        page.wait_for_function("() => document.querySelector('.wf-image-dialog img')?.naturalWidth > 0")
        page.locator('.wf-image-dialog [aria-label="关闭截图"]').click()
        expect(page.locator('.wf-image-dialog')).to_have_count(0)
        page.evaluate('scrollTo(0,0)')
        page.mouse.move(195, 600)
        page.mouse.wheel(0, 650)
        page.wait_for_function('() => scrollY > 100')
        mark_demo(page, 'sales')
        shots.append(h.take_screenshot(page, output, '01_mobile_search_help.png'))
        steps.append('390px 销售账号从顶栏实时搜索打开接待指引，入口图片实际加载，手动滚动可阅读。')

        page.locator('[data-wf-path=assistant]').click()
        expect(page.locator('[data-wf-panel=assistant]')).to_be_visible()
        expect(page.locator('[data-wf-panel=manual]')).not_to_be_visible()
        page.locator('[data-wf-path=manual]').click()
        page.locator('[data-wf-action=manual]').click()
        expect(page.locator('#main h1')).to_have_text('售前接待')
        expect(page.locator('[data-act=newcase][data-kind=lead]')).to_be_visible()
        h.assert_fits_mobile(page)
        shots.append(h.take_screenshot(page, output, '02_mobile_native_entry.png'))
        steps.append('指引中切换人工／助手步骤，打开原售前接待入口；未创建业务。')

        page.keyboard.press('Control+k')
        expect(page.locator('#workflow-search-dialog')).to_be_visible()
        page.evaluate("""() => {
            window.__workflowEscapeTrace=[];
            for(const type of ['keydown','cancel','input','focusin']) document.addEventListener(type,event=>{
                if(['workflow-search-input','workflow-search-dialog','workflow-top-search'].includes(event.target.id))
                    window.__workflowEscapeTrace.push({type,key:event.key||'',target:event.target.id,value:event.target.value||'',prevented:event.defaultPrevented,ctrl:event.ctrlKey,meta:event.metaKey,alt:event.altKey});
            },true);
        }""")
        page.locator('#workflow-search-input').fill('HK-001')
        expect(page.locator(f'[role=option][data-wf-action=result][data-id="{lead["id"]}"]')).to_be_visible()
        page.keyboard.press('Escape')
        expect(page.locator('#workflow-search-dialog')).to_have_count(0)
        page.locator('#workflow-top-search').click()
        expect(page.locator('#workflow-search-dialog')).to_be_visible()
        page.keyboard.press('Escape')
        expect(page.locator('#workflow-search-dialog')).to_have_count(0)
        page.locator('#workflow-top-search').focus()
        expect(page.locator('#workflow-top-search')).to_be_focused()
        page.locator('#workflow-top-search').press_sequentially('HK-001', delay=60)
        keyboard_probe = page.evaluate("""() => ({opened:!!document.querySelector('#workflow-search-dialog'),
            top:{value:document.querySelector('#workflow-top-search').value,
                readOnly:document.querySelector('#workflow-top-search').readOnly,
                disabled:document.querySelector('#workflow-top-search').disabled,
                editable:document.querySelector('#workflow-top-search').isContentEditable},
            events:window.__workflowEscapeTrace})""")
        expect(page.locator('#workflow-search-dialog')).to_be_visible()
        expect(page.locator('#workflow-search-input')).to_have_value('HK-001')
        page.keyboard.press('Escape')
        page.keyboard.press('Control+k')
        page.locator('#workflow-search-input').fill('不存在的流程演示xyz')
        expect(page.locator('#workflow-search-status')).to_contain_text('没有找到')
        expect(page.locator('[data-wf-action=result]')).to_have_count(0)
        page.locator('#workflow-search-input').fill(lead['title'])
        page.keyboard.press('ArrowDown')
        page.keyboard.press('ArrowUp')
        page.keyboard.press('Enter')
        expect(page.locator('#main h1')).to_have_text(lead['title'])
        page.keyboard.press('Control+k')
        page.keyboard.press('Escape')
        steps.append('Ctrl K、方向键/Enter、需求编号搜索、空结果、Esc 关闭后再次点击及逐键输入 HK-001 重开正常。')

        read_entry(page, base, 'workflows/' + lead['id'])
        page.locator('[data-wf-action=form][data-id=wf-reception]').click()
        expect(page.locator('#modal')).to_be_visible()
        expect(page.locator('#modal h2')).to_have_text('新建售前接待')
        expect(page.locator('#modal [name=customer_name]')).to_be_visible()
        page.locator('#modal [data-act=close]').first.click()
        page.goto(base + '/#workflow-form/' + lead['id'])
        expect(page.locator('#main h1')).to_have_text('售前接待')
        expect(page.locator('#modal h2')).to_have_text('新建售前接待')
        expect(page.locator('#modal')).to_be_visible()
        expect(page.locator('#modal [name=customer_name]')).to_be_visible()
        shots.append(h.take_screenshot(page, output, '05_mobile_direct_original_form.png'))
        page.locator('#modal [data-act=close]').first.click()
        assert not mutations, mutations
        steps.append('文章的新建表单按钮及冷打开 workflow-form 链接均打开原接待表单；未填入、提交或新建业务。')

        read_entry(page, base, 'workflows/' + lead['id'])
        page.locator('[data-wf-action=assistant]').click()
        expect(page.locator('#main h1')).to_have_text('业务助手')
        draft = page.locator('#business-assistant-input')
        expect(draft).to_contain_text(lead['title'])
        assert '生成表单后等我核对确认' in draft.input_value()
        assert not mutations, mutations
        mark_demo(page, 'sales')
        shots.append(h.take_screenshot(page, output, '03_mobile_unsent_assistant_draft.png'))
        steps.append('让助手带我办仅预填本流程文字；没有创建会话、发送消息或办理业务的 POST。')

        custom = '保留这段未发送的个人试用内容。'
        draft.fill(custom)
        # Hash navigation preserves the page's draft without a full reload.
        page.evaluate('(id)=>{location.hash="workflows/"+id}', lead['id'])
        expect(page.locator('#main h1')).to_have_text(lead['title'])
        page.locator('[data-wf-action=assistant]').click()
        expect(page.locator('#main h1')).to_have_text('业务助手')
        expect(page.locator('#business-assistant-input')).to_have_value(custom)
        page.locator('#store').select_option(str(second['id']))
        expect(page.locator('#main h1')).to_have_text('我的工作')
        page.evaluate('location.hash="business-assistant"')
        expect(page.locator('#main h1')).to_have_text('业务助手')
        expect(page.locator('#business-assistant-input')).to_have_value('')
        steps.append('已有未发送草稿不会被流程按钮覆盖；切店后草稿清空。')

        read_entry(page, base, 'workflows/' + restricted['id'])
        expect(page.locator('[data-wf-action=manual]')).to_be_disabled()
        expect(page.locator('.wf-role-note')).to_be_visible()
        h.assert_fits_mobile(page)
        steps.append('非本岗位操作可读步骤，原办理入口禁用，未扩展权限。')
        form_ids = page.evaluate('() => Object.keys(WORKFLOW_QUICK_FORMS)')
        restricted_form = next(row for row in catalogue['workflows'] if row['id'] in form_ids and 'sales' not in row['entry']['roles'])
        page.goto(base + '/#workflow-form/' + restricted_form['id'])
        expect(page.locator('#main h1')).to_have_text(restricted_form['title'])
        expect(page.locator('[data-wf-action=form]')).to_be_disabled()
        expect(page.locator('#modal')).not_to_be_visible()
        steps.append('销售直接输入非本岗位的 workflow-form 链接不会打开或提交表单。')
        # Search and guides never submit business writes; the current store is local UI state.
        assert not mutations, mutations

        # Create one more synthetic employee with known random credentials to
        # exercise a genuinely unauthenticated deep link, not a reused cookie.
        link_name = 'guide-link-' + secrets.token_hex(4)
        link_initial, link_password = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        h.checked_request(admin, '/api/users', 'POST', {'username': link_name, 'display_name': '演示链接销售',
            'role': 'sales', 'password': link_initial, 'store_roles': [{'store_id': 1, 'role': 'sales'}]}, status=201)
        setup_context = browser.new_context(viewport={'width': 390, 'height': 844}, locale='zh-CN')
        try:
            setup_page = setup_context.new_page()
            h.login_page(setup_page, base, link_name, link_initial)
            setup_page.locator('#modal [name=current_password]').fill(link_initial)
            setup_page.locator('#modal [name=new_password]').fill(link_password)
            h.save_modal(setup_page)
        finally:
            setup_context.close()
        login_checks = []
        for target in ('workflow-form/' + lead['id'], 'cases/lead'):
            cold_context = browser.new_context(viewport={'width': 390, 'height': 844}, locale='zh-CN')
            try:
                cold = cold_context.new_page()
                cold.on('pageerror', lambda error: errors.append({'role': 'sales', 'error': str(error)}))
                cold.on('request', lambda request: record_request(request) if not urlsplit(request.url).path.startswith('/api/auth/') else None)
                cold.goto(base + '/#' + target)
                expect(cold.locator('.loginform')).to_be_visible()
                assert cold.evaluate('location.hash') == '#' + target
                cold.locator('.loginform [name=username]').fill(link_name)
                cold.locator('.loginform [name=password]').fill(link_password)
                cold.locator('.loginform button[type=submit]').click()
                expect(cold.locator('#main h1')).to_have_text('售前接待')
                if target.startswith('workflow-form/'):
                    expect(cold.locator('#modal h2')).to_have_text('新建售前接待')
                    expect(cold.locator('#modal')).to_be_visible()
                    expect(cold.locator('#modal [name=customer_name]')).to_be_visible()
                    cold.locator('#modal [data-act=close]').first.click()
                else:
                    expect(cold.locator('#modal')).not_to_be_visible()
                login_checks.append({'requested_route': target, 'actual_route': cold.evaluate('location.hash'), 'passed': True})
            except Exception:
                cold.screenshot(path=str(output / 'deep-link-failure.png'), full_page=True)
                raise
            finally:
                cold_context.close()
        steps.append('未登录打开原页面或 workflow-form 链接，登录后仍到目标页面／原表单；不退回工作首页。')
        assert not mutations, mutations

        handbook_results = []
        for name, url in [('served', base + '/static/workflow-handbook.html'),
                          ('offline', (ROOT / 'docs/全量工作流手册.html').as_uri())]:
            book = employee_context.new_page()
            book.on('request', record_request)
            book.on('pageerror', lambda error: errors.append({'role': 'sales', 'error': str(error)}))
            book.add_init_script("window.__guideCsp=[];document.addEventListener('securitypolicyviolation',e=>window.__guideCsp.push({directive:e.violatedDirective,blocked:e.blockedURI}));")
            book.goto(url)
            expect(book.locator('#workflow-handbook-main h1')).to_have_text('huakangos 工作流手册')
            expect(book.locator('.wf-handbook-coverage li')).to_have_count(193)
            book.locator('#handbook-query').fill('HK-001')
            book.locator(f'[data-wfh-guide="{lead["id"]}"]').click()
            expect(book.locator('#workflow-handbook-main h1')).to_have_text(lead['title'])
            book.locator('.wf-figure img').scroll_into_view_if_needed()
            book.wait_for_function("() => [...document.querySelectorAll('.wf-figure img')].every(i=>i.complete&&i.naturalWidth>0)")
            book.locator('.wf-figure img').click()
            expect(book.locator('.wf-image-dialog')).to_be_visible()
            book.wait_for_function("() => document.querySelector('.wf-image-dialog img')?.naturalWidth > 0")
            book.locator('.wf-image-dialog [aria-label="关闭截图"]').click()
            expect(book.locator('.wf-image-dialog')).to_have_count(0)
            assets = book.evaluate("""async () => {
                const images=[...new Set(handbookData.workflows.map(w=>w.screenshot.src))];
                return Promise.all(images.map(src=>new Promise(resolve=>{
                    const image=new Image();image.onload=()=>resolve({src,width:image.naturalWidth});
                    image.onerror=()=>resolve({src,error:true});
                    image.src=handbookData.images?.[src]||src;
                })));
            }""")
            assert len(assets) == len({row['screenshot']['src'] for row in catalogue['workflows']})
            assert all(row.get('width', 0) > 0 for row in assets), assets
            assert not book.evaluate('window.__guideCsp'), book.evaluate('window.__guideCsp')
            width = book.evaluate('({actual:document.documentElement.scrollWidth,viewport:innerWidth})')
            assert width['actual'] <= width['viewport'] + 1, width
            book.locator('[data-wf-path=assistant]').click()
            expect(book.locator('[data-wf-panel=assistant]')).to_be_visible()
            shots.append(h.take_screenshot(book, output, '04_handbook_' + name + '.png'))
            form_link = book.locator('[data-wf-system="workflow-form/wf-reception"]')
            expect(form_link).to_be_visible()
            assert urlsplit(form_link.get_attribute('href')).fragment == 'workflow-form/wf-reception'
            if name == 'served':
                form_link.click()
                expect(book.locator('#main h1')).to_have_text('售前接待')
                expect(book.locator('#modal')).to_be_visible()
                expect(book.locator('#modal h2')).to_have_text('新建售前接待')
                expect(book.locator('#modal [name=customer_name]')).to_be_visible()
                book.locator('#modal [data-act=close]').first.click()
            handbook_results.append({'mode': name, 'images_loaded': len(assets), 'csp_violations': [],
                                     'form_link': 'native form opened' if name == 'served' else 'offline link verified; existing preview never contacted'})
            book.close()
        steps.append('在线手册及离线单 HTML 均可按需求编号查找、切换办理方式；全部入口图片加载，无 CSP 错误或横向溢出。')
        steps.append('在线手册表单链接实际打开原表单；离线链接目标核对正确，未连接用户原预览。')
        assert not mutations, mutations
        assert not errors, errors
        return {'status': 'passed', 'synthetic_only': True, 'viewport': {'width': 390, 'height': 844},
                'employee_role': 'sales', 'steps': steps, 'screenshots': shots,
                'page_errors': errors, 'api_mutations_after_setup': mutations, 'external_model_requests': 0,
                'read_only_recommendation_requests': recommendations,
                'handbooks': handbook_results,
                'unauthenticated_deep_links': login_checks,
                'sequential_typing_probe': keyboard_probe,
                'limitations': ['入口和指引联动验收；未逐项办理 193 条业务。', '模型未调用；预填不代表模型理解或办理成功。']}
    except Exception as error:
        if employee_context and 'page' in locals():
            page.screenshot(path=str(output / 'failure.png'), full_page=True)
            (output / 'failure.json').write_text(json.dumps({'error': str(error), 'page_errors': errors,
                'mutations': mutations, 'completed_steps': steps,
                'search_trace': page.evaluate('() => window.__workflowEscapeTrace || []'),
                'keyboard_probe': keyboard_probe}, ensure_ascii=False, indent=2), encoding='utf-8')
        raise
    finally:
        if employee_context:
            employee_context.close()
        admin_context.close()


if __name__ == '__main__':
    h.exercise = exercise
    h.main()
