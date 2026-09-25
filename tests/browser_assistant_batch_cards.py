"""Real local Chrome checks for the batch card panel, pager and batch confirm.

业主 2026-09-25 试用反馈对应的四条：一轮几十张卡要折叠分页、不能铺满对话、
点一次就能办完整组、离开助手页不该把这一轮掐断。这里用真实 Chrome + 真实页面/CSS，
只把助手接口换成确定性 mock（不调用真实模型），并断言实际发出的 HTTP 请求。
"""
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import expect  # noqa: E402
from tests import browser_huakangos as h  # noqa: E402

CARD_COUNT = 6


def card(index):
    return {'id': 'synthetic-card-%d' % index, 'turn': 'turn-1', 'label': '新增车型 %d' % index,
            'summary': '新增车型：合成车型 %d（2027，纯电）' % index, 'status': 'pending', 'digest': '%064d' % index,
            'expires_at': '2099-01-01T00:00:00Z',
            'display_fields': [{'label': '品牌', 'value': '合成品牌'}, {'label': '车系', 'value': '合成车系 %d' % index},
                               {'label': '名称', 'value': '合成车型 %d' % index}]}


def exercise(browser, base, password, output):
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, locale='zh-CN')
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    steps, screenshots = [], []
    session = {'id': 'synthetic-session', 'title': '整表导入', 'created_at': '2026-09-25T09:00:00Z',
               'updated_at': '2026-09-25T09:00:00Z', 'busy': False, 'messages': [], 'proposals': []}
    batches, messages, replies = [], [], []

    def assistant(route):
        request = route.request
        path = urlsplit(request.url).path.removeprefix('/api/business-assistant')
        body = request.post_data_json if request.method == 'POST' else {}
        status, result = 200, {}
        if path == '/status':
            result = {'enabled': True, 'ready': True, 'model': 'deterministic-ui-fixture',
                      'message': '可以开始办理业务', 'limits': {'max_message_chars': 12000}}
        elif path == '/sessions' and request.method == 'GET':
            result = {'items': [session] if session['messages'] else []}
        elif path == '/sessions' and request.method == 'POST':
            status = 201
            result = session
        elif path.endswith('/messages/stream'):
            messages.append(body)
            session['messages'].append({'role': 'user', 'content': body['content']})
            if len(messages) == 1:
                session['proposals'] = [card(index) for index in range(1, CARD_COUNT + 1)]
                answer = '本轮共准备 %d 张待确认卡，可在右侧逐张翻看，或点“全部确认”一次办完。' % CARD_COUNT
            else:
                answer = '第二轮已处理完：剩下缺电池容量的行我没有建卡，补齐后可以继续。'
            replies.append(answer)
            session['messages'].append({'role': 'assistant', 'content': answer})
            result = session
        elif path.endswith('/proposals/batch'):
            batches.append(body)
            wanted = {item['id'] for item in body['items']}
            for row in session['proposals']:
                if row['id'] in wanted:
                    row['status'] = 'succeeded'
                    row['result'] = {'message': '已办理'}
            result = dict(session, batch={'total': len(body['items']), 'done': len(body['items']),
                                          'items': [{'id': item['id'], 'status': 'succeeded'} for item in body['items']]})
        elif path.startswith('/sessions/'):
            result = session
        else:
            raise AssertionError({'unexpected_assistant_request': path})
        if path.endswith('/messages/stream'):
            route.fulfill(status=status, content_type='text/event-stream',
                          body='event: done\ndata: ' + json.dumps({'session': result}, ensure_ascii=False) + '\n\n')
        else:
            route.fulfill(status=status, content_type='application/json', body=json.dumps(result, ensure_ascii=False))

    page.route('**/api/business-assistant/**', assistant)
    try:
        h.login_page(page, base, 'admin', password)
        h.navigate(page, 'business-assistant', '业务助手')
        page.locator('#business-assistant-input').fill('把这张表整表导进车型目录')
        page.locator('#business-assistant-form button[type=submit]').click()

        # 1. 卡片与对话平行：对话区只有对话，卡片在自己的栏里。
        expect(page.locator('#business-assistant-messages')).to_contain_text('本轮共准备 6 张待确认卡')
        expect(page.locator('#business-assistant-messages .ba-proposal')).to_have_count(0)
        expect(page.locator('#business-assistant-cards')).to_be_visible()
        expect(page.locator('#business-assistant-cards .ba-proposal')).to_have_count(1)
        expect(page.locator('.ba-cardnav-pos')).to_have_text('1 / 6')
        expect(page.locator('.ba-cardnav-count')).to_contain_text('还有 6 张待确认')
        assert page.locator('#business-assistant-cards').bounding_box()['x'] > page.locator('.ba-chat').bounding_box()['x'], \
            '卡片栏在对话右侧，而不是压在对话下面'
        screenshots.append(h.take_screenshot(page, output, 'assistant-cards-desktop.png'))
        steps.append('整表一轮后：对话区不含卡片，卡片在右侧独立栏，显示 1/6 与“全部确认（6 张）”')

        # 2. 翻页：本地切换，不请求接口。
        page.locator('[data-ba-action=card-next]').click()
        expect(page.locator('.ba-cardnav-pos')).to_have_text('2 / 6')
        expect(page.locator('#business-assistant-cards .ba-proposal')).to_contain_text('合成车型 2')
        page.locator('[data-ba-action=card-prev]').click()
        expect(page.locator('.ba-cardnav-pos')).to_have_text('1 / 6')
        steps.append('“›/‹”在本轮卡片间翻页，当前卡片随之切换（不发请求）')

        # 3. 展开全部 / 收起：需要通读时一次看全，不需要时收起来。
        page.locator('[data-ba-action=card-fold]').click()
        expect(page.locator('#business-assistant-cards .ba-proposal')).to_have_count(CARD_COUNT)
        page.locator('[data-ba-action=card-fold]').click()
        expect(page.locator('#business-assistant-cards .ba-proposal')).to_have_count(1)
        steps.append('“展开全部/收起”在整组明细和单张视图之间切换')

        # 4. 一次点击办完整组：弹窗确认 → 一条批量请求 → 每张各自的结果。
        page.locator('[data-ba-action=card-confirm-all]').click()
        expect(page.locator('#modal')).to_contain_text('全部确认前请再核对一次')
        expect(page.locator('#modal')).to_contain_text('逐张按原接口办理')
        page.locator('#modal button[type=submit]').click()
        expect(page.locator('.ba-cardnav-count')).to_contain_text('已全部办理')
        expect(page.locator('[data-ba-action=confirm]')).to_have_count(0)
        assert len(batches) == 1 and len(batches[0]['items']) == CARD_COUNT, batches
        assert {item['digest'] for item in batches[0]['items']} == {'%064d' % index for index in range(1, CARD_COUNT + 1)}, \
            '每张卡仍然带着它自己冻结的 digest'
        screenshots.append(h.take_screenshot(page, output, 'assistant-cards-confirmed.png'))
        steps.append('“全部确认”一次点击 → 一条批量请求（每张仍带自己的 digest）→ 6 张全部办理')

        # 5. 确认之后给出下一轮入口。
        expect(page.locator('.ba-nextstep')).to_contain_text('已办理')
        expect(page.locator('[data-ba-action=continue]')).to_be_visible()
        steps.append('确认完成后出现“继续处理”按钮，员工不必自己猜要发什么')

        # 6. 离开助手页不中止这一轮：发出后立刻切到别的页面，回来看结果还在、没有"已停止等待"。
        page.evaluate("businessAssistantState.draft='再准备一张';businessAssistantSend();location.hash='#work';")
        expect(page.locator('#main h1')).to_have_text('我的工作')
        page.wait_for_timeout(1200)
        page.evaluate("location.hash='#business-assistant'")
        expect(page.locator('#business-assistant-messages')).to_contain_text('第二轮已处理完')
        expect(page.locator('#business-assistant-cards')).to_be_visible()
        assert page.evaluate('businessAssistantState.needsRefresh') is False, '后台跑完的一轮不该被标成需要刷新'
        assert page.evaluate('businessAssistantState.draft') == '', '这一轮在后台办完了，草稿应已清空'
        assert not page.locator('.ba-error').inner_text().strip(), '离开页面再回来不该出现“已停止等待”'
        steps.append('发出后立刻离开助手页：这一轮在后台跑完，回来能看到结果、没有中止提示')

        # 7. 窄屏：卡片栏落在对话上方且不横向溢出，整栏可收起。
        page.set_viewport_size({'width': 390, 'height': 844})
        h.assert_fits_mobile(page)
        assert page.locator('#business-assistant-cards').bounding_box()['y'] < page.locator('.ba-chat').bounding_box()['y'], \
            '窄屏时卡片栏在对话之前，不再把对话顶走'
        page.locator('[data-ba-action=panel-fold]').click()
        expect(page.locator('.ba-cards-list')).to_be_hidden()
        steps.append('390px 窄屏：卡片栏在对话上方且可整栏收起，页面不横向溢出')
        screenshots.append(h.take_screenshot(page, output, 'assistant-cards-mobile.png'))

        assert not errors, errors
        return {'mode': 'real Windows Chrome employee UI; assistant responses mocked',
                'steps': steps, 'screenshots': screenshots, 'javascript_errors': errors,
                'batches': [{'items': len(item['items']), 'action': item['action']} for item in batches],
                'limitations': ['只验证页面交互与发出的请求；真实模型与落库由一次性实例的脚本另验',
                                'mock 不证明 DeepSeek 调用或业务入账']}
    except Exception:
        h.take_screenshot(page, output, 'assistant-cards-failure.png')
        raise
    finally:
        context.close()


h.exercise = exercise
if __name__ == '__main__':
    h.main()
