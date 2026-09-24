"""Real Chrome semantic guide search with a scripted, network-free model adapter.

Uses a newly initialized temporary database, random port and actual sales login.
Only recommend_ids and its private configuration are synthetic. No business
operation or assistant message is submitted by this acceptance scenario.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
from playwright.sync_api import expect, sync_playwright
from scripts.capture_workflow_guides import employee, mark_demo
from tests import browser_huakangos as h

QUERY = '刚来了位叔叔不知道从哪里开始'
TYPED = '这位顾客只说需要替他办一件事'
RETRY = '店里这一件事情想请你指个路'
LATE = '等一等再回答这件暂时说不清的事情'
SWITCH = '换一家店以前尚未找到办事的位置'
EMPTY = '想找一件完全不在经营范围内的事情'


def serve(port, trace):
    assert os.environ.get('APP_ENV') == 'test'
    assert 'huakangos-guide-recommend-' in os.environ.get('DATABASE_URL', '')
    from app import workflow_guides_api as service
    from app import business_assistant_service as assistant
    from app.main import app
    from fastapi import HTTPException
    import uvicorn

    config = assistant.AssistantConfig(True, 'synthetic-no-network', 'scripted-guide-fixture', 5, True)
    assistant.load_config = lambda: config
    if hasattr(service, 'load_config'):
        service.load_config = lambda: config

    def no_network(*args, **kwargs):
        raise AssertionError('External provider calls are forbidden by this synthetic browser test')
    assistant.provider_request = no_network
    calls = {}

    async def recommend_ids(config, catalogue, query):
        calls[query] = calls.get(query, 0) + 1
        with Path(trace).open('a', encoding='utf-8') as output:
            output.write(json.dumps({'query': query, 'call': calls[query]}, ensure_ascii=False) + '\n')
        if query == RETRY and calls[query] == 1:
            raise HTTPException(503, '暂时没找到推荐，请再试一次')
        if query in (LATE, SWITCH):
            await asyncio.sleep(1.8)
        if query == EMPTY:
            return []
        # Unknown/duplicate IDs are deliberately rejected by the real endpoint;
        # the model never gets to invent links, titles or actions.
        return ['wf-reception', 'wf-not-real', 'javascript:alert(1)', 'wf-reception']
    service.recommend_ids = recommend_ids
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')


def trace_rows(work):
    path = work / 'model-trace.jsonl'
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []


def wait_trace(work, query):
    for _ in range(150):
        if any(row['query'] == query for row in trace_rows(work)):
            return
        time.sleep(.02)
    raise AssertionError('Expected scripted model query was never received: ' + query)


def exercise(browser, base, password, output, work):
    assert urlsplit(base).port != 8000
    errors, steps, screenshots, writes, requests = [], [], [], [], []
    admin_context = browser.new_context(viewport={'width': 1440, 'height': 1000}, locale='zh-CN')
    admin = admin_context.new_page()
    context = None
    try:
        h.login_page(admin, base, 'admin', password)
        second = h.checked_request(admin, '/api/stores', 'POST', {'code': 'GUIDE-REC-TWO', 'name': '合成推荐乙店'}, status=201)
        context, page = employee(browser, admin, base, 'sales', errors, {'width': 390, 'height': 844}, (1, second['id']))

        def record(request):
            path = urlsplit(request.url).path
            if request.method not in ('GET', 'HEAD', 'OPTIONS') and path.startswith('/api/'):
                if path == '/api/workflow-guides/recommendations':
                    requests.append(request.post_data_json)
                else:
                    writes.append({'method': request.method, 'path': path})
        page.on('request', record)
        before = h.checked_request(page, '/api/flow/cases?kind=lead')['total']

        def open_search(query):
            if not page.locator('#workflow-search-dialog').count():
                page.locator('#workflow-top-search').click()
            page.locator('#workflow-search-input').fill(query)

        def result():
            return page.locator('#workflow-ai-results [role=option][data-wf-action=result][data-id=wf-reception]')

        def mode(name):
            page.locator(f'[data-wf-action=search-mode][data-mode={name}]').first.click()

        def shot(name):
            mark_demo(page, 'sales')
            path = output / name
            page.screenshot(path=str(path), full_page=False)
            screenshots.append(str(path))

        open_search('客户档案')
        expect(page.locator('#workflow-search-results [data-wf-action=result]').first).to_be_visible()
        expect(page.locator('#workflow-ai-section')).not_to_be_visible()
        page.wait_for_timeout(1250)
        assert not trace_rows(work), trace_rows(work)
        assert not requests, requests
        steps.append('默认普通搜索即时展示本地匹配；停顿后仍不请求 AI。')

        open_search('登记接待并安排回访')
        page.locator('#workflow-search-results [data-wf-action=manual][data-id=wf-reception]').click()
        expect(page.locator('#main h1')).to_have_text('售前接待')
        open_search('登记接待并安排回访')
        page.locator('#workflow-search-results [data-wf-action=form][data-id=wf-reception]').click()
        expect(page.locator('#modal')).to_be_visible()
        expect(page.locator('#modal h2')).to_have_text('新建售前接待')
        expect(page.locator('#modal [name=customer_name]')).to_be_visible()
        shot('06_mobile_normal_original_form.png')
        page.locator('#modal [data-act=close]').first.click()
        expect(page.locator('#modal')).not_to_be_visible()
        assert not writes and not requests
        steps.append('普通搜索结果可直接进入原接待页面或打开原新建表单；只打开，不提交。')

        open_search(QUERY)
        expect(page.locator('#workflow-search-results [data-wf-action=result]')).to_have_count(0)
        expect(page.locator('#workflow-ai-section')).not_to_be_visible()
        expect(page.locator('[data-wf-action=search-mode][data-mode=ai]').last).to_be_visible()
        page.wait_for_timeout(1250)
        assert not requests and not trace_rows(work)
        h.assert_fits_mobile(page)
        shot('01_mobile_normal_no_matches.png')
        steps.append('普通搜索即使没有结果也不请求 AI；显示显式切换 AI 搜索的入口。')

        # The no-match suggestion is an explicit mode switch, like the AI tab.
        page.locator('[data-wf-action=search-mode][data-mode=ai]').last.click()
        expect(result()).to_be_visible(timeout=10000)
        expect(page.locator('#workflow-search-results')).not_to_be_visible()
        expect(page.locator('#workflow-ai-results [role=option][data-wf-action=result]')).to_have_count(1)
        expect(result()).to_contain_text('登记接待并安排回访')
        assert trace_rows(work) == [{'query': QUERY, 'call': 1}]
        assert requests[-1] == {'query': QUERY, 'trigger': 'manual'}
        h.assert_fits_mobile(page)
        shot('02_mobile_ai_matches.png')
        steps.append('点击 AI 搜索才执行一次；普通结果与 AI 结果分开，真实接口过滤不存在、重复和恶意 ID。')

        page.locator('#workflow-ai-results [data-wf-action=manual][data-id=wf-reception]').click()
        expect(page.locator('#main h1')).to_have_text('售前接待')
        open_search(QUERY)
        mode('ai')
        expect(result()).to_be_visible(timeout=10000)
        page.locator('#workflow-ai-results [data-wf-action=form][data-id=wf-reception]').click()
        expect(page.locator('#modal')).to_be_visible()
        expect(page.locator('#modal h2')).to_have_text('新建售前接待')
        expect(page.locator('#modal [name=customer_name]')).to_be_visible()
        shot('07_mobile_ai_original_form.png')
        page.locator('#modal [data-act=close]').first.click()
        expect(page.locator('#modal')).not_to_be_visible()
        assert not writes
        open_search(QUERY)
        mode('ai')
        expect(result()).to_be_visible(timeout=10000)
        assert len(trace_rows(work)) == 1
        steps.append('AI 结果的进入页面和新建表单复用本店原入口；返回后同查询缓存有效，没有自动办理。')

        sent_before = len(requests)
        open_search('客户档案')
        page.wait_for_timeout(1250)
        assert len(requests) == sent_before and len(trace_rows(work)) == 1
        expect(result()).to_have_count(0)
        page.locator('#workflow-search-input').press('Enter')
        expect(result()).to_be_visible(timeout=10000)
        assert requests[-1] == {'query': '客户档案', 'trigger': 'manual'}
        assert len([row for row in trace_rows(work) if row['query'] == '客户档案']) == 1
        sent_before = len(requests)
        page.locator('[data-wf-action=ai-search]').click()
        page.wait_for_timeout(300)
        assert len(requests) == sent_before and len(trace_rows(work)) == 2
        mode('normal')
        expect(page.locator('#workflow-search-results [data-wf-action=result]').first).to_be_visible()
        expect(page.locator('#workflow-ai-section')).not_to_be_visible()
        mode('ai')
        expect(result()).to_be_visible(timeout=10000)
        assert len(requests) == sent_before and len(trace_rows(work)) == 2
        steps.append('AI 模式输入不触发请求；按 Enter 才搜索，即使有本地匹配也可显式请求；同查询按钮和切换模式复用缓存。')

        # Composition is deliberately labelled as event simulation, not an
        # unperformed Windows IME interaction. No request may run mid-composition.
        page.locator('#workflow-search-input').evaluate("""(input,query) => {
            input.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));
            input.value=query;
            input.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:true,
                inputType:'insertCompositionText',data:'叔叔'}));
        }""", TYPED)
        page.wait_for_timeout(1250)
        assert len(requests) == sent_before and len(trace_rows(work)) == 2
        page.locator('#workflow-search-input').evaluate("input => input.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'叔叔'}))")
        page.wait_for_timeout(1250)
        assert len(requests) == sent_before and len(trace_rows(work)) == 2
        expect(result()).to_have_count(0)
        page.locator('[data-wf-action=ai-search]').click()
        expect(result()).to_be_visible(timeout=10000)
        assert len([row for row in trace_rows(work) if row['query'] == TYPED]) == 1
        steps.append('composition 事件模拟：中文选字期间及完成后均不请求，点击搜索才提交完整文字。')

        result().click()
        expect(page.locator('#main h1')).to_have_text('登记接待并安排回访')
        assert not writes, writes
        steps.append('AI 结果只打开已有指引，不提交业务，也不发送助手消息。')

        open_search(RETRY)
        expect(page.locator('#workflow-ai-section')).not_to_be_visible()
        mode('ai')
        expect(page.locator('#workflow-ai-status')).to_contain_text('暂时', timeout=10000)
        expect(page.locator('#workflow-search-input')).to_have_value(RETRY)
        page.locator('[data-wf-action=ai-search]').click()
        expect(result()).to_be_visible(timeout=10000)
        assert len([row for row in trace_rows(work) if row['query'] == RETRY]) == 2
        steps.append('AI 搜索失败保留原输入，显示中文说明，可点击搜索重试。')

        open_search(EMPTY)
        sent_before = len(requests)
        page.wait_for_timeout(1250)
        assert len(requests) == sent_before
        page.locator('[data-wf-action=ai-search]').click()
        wait_trace(work, EMPTY)
        expect(page.locator('#workflow-ai-status')).to_contain_text('没有找到', timeout=10000)
        expect(page.locator('#workflow-ai-results [role=option][data-wf-action=result]')).to_have_count(0)
        shot('03_mobile_ai_no_matches.png')
        steps.append('模型没有合适结果时不捏造流程或入口。')

        open_search(LATE)
        page.locator('[data-wf-action=ai-search]').click()
        wait_trace(work, LATE)
        mode('normal')
        expect(page.locator('#workflow-ai-section')).not_to_be_visible()
        open_search('客户档案')
        expect(page.locator('#workflow-search-results [data-wf-action=result]').first).to_be_visible()
        page.wait_for_timeout(2100)
        expect(page.locator('#workflow-ai-section')).not_to_be_visible()
        expect(result()).not_to_be_visible()
        steps.append('AI 请求进行中切回普通，立即恢复本地结果；迟到回复不会重新显示或切换模式。')

        open_search(SWITCH)
        mode('ai')
        wait_trace(work, SWITCH)
        page.keyboard.press('Escape')
        expect(page.locator('#workflow-search-dialog')).to_have_count(0)
        page.locator('#store').select_option(str(second['id']))
        expect(page.locator('#main h1')).to_have_text('我的工作')
        page.wait_for_timeout(2100)
        expect(page.locator('#workflow-search-dialog')).to_have_count(0)
        open_search('客户档案')
        expect(page.locator('#workflow-ai-section')).not_to_be_visible()
        expect(page.locator('#workflow-search-results [data-wf-action=result]').first).to_be_visible()
        steps.append('关闭搜索并切店后旧请求失效，重新打开默认普通搜索。')

        page.set_viewport_size({'width': 1440, 'height': 1000})
        h.assert_fits_mobile(page)
        shot('04_desktop_normal_matches.png')
        mode('ai')
        expect(result()).to_be_visible(timeout=10000)
        expect(page.locator('#workflow-search-results')).not_to_be_visible()
        h.assert_fits_mobile(page)
        shot('05_desktop_ai_matches.png')
        page.keyboard.press('Escape')
        assert h.checked_request(page, '/api/flow/cases?kind=lead', store=second['id'])['total'] == 0
        assert h.checked_request(admin, '/api/flow/cases?kind=lead')['total'] == before
        assert all(request['trigger'] == 'manual' for request in requests), requests
        assert not writes, writes
        assert not errors, errors
        steps.append('390px 手机及 1440px 电脑两种模式均可用，无横向溢出；全程无业务写入或接待数量变化。')
        (output / 'scripted-model-trace.json').write_text(json.dumps(trace_rows(work), ensure_ascii=False, indent=2), encoding='utf-8')
        return {'status': 'passed', 'synthetic_only': True, 'viewports': [{'width': 390, 'height': 844}, {'width': 1440, 'height': 1000}],
                'employee_role': 'sales', 'steps': steps, 'screenshots': screenshots,
                'page_errors': errors, 'read_only_recommendation_requests': requests,
                'api_business_writes': writes, 'external_model_requests': 0,
                'scripted_model_calls': len(trace_rows(work)),
                'limitations': ['模型推荐回复为固定脚本，不证明真实 DeepSeek 理解或推荐质量。', '中文输入法使用 composition 事件模拟，未操作 Windows 实际输入法。', '真实本机 HTTP 浏览器检查，不替代生产 HTTPS 或公司业务验收。']}
    except Exception as error:
        if context:
            page.screenshot(path=str(output / 'failure.png'), full_page=True)
            (output / 'failure.json').write_text(json.dumps({'error': str(error), 'page_errors': errors,
                'writes': writes, 'requests': requests, 'trace': trace_rows(work), 'steps': steps}, ensure_ascii=False, indent=2), encoding='utf-8')
        raise
    finally:
        if context:
            context.close()
        admin_context.close()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshots', type=Path, required=True)
    args = parser.parse_args()
    executable = h.chromium_path()
    if not executable:
        raise SystemExit('请安装 Chrome/Edge 或设置 CHROMIUM_PATH。')
    output = args.screenshots.resolve()
    if output == ROOT or ROOT in output.parents:
        raise SystemExit('验收记录必须存放在源码目录之外。')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'acceptance.json').unlink(missing_ok=True)
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    with tempfile.TemporaryDirectory(prefix='huakangos-guide-recommend-') as name:
        work = Path(name)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        password = secrets.token_urlsafe(28)
        env = h.browser_environment(work, password)
        env.update(BUSINESS_ASSISTANT_CONFIG='', PYTHONDONTWRITEBYTECODE='1')
        initialized = subprocess.run([sys.executable, '-m', 'app.cli', 'init'], cwd=ROOT, env=env,
            capture_output=True, text=True, encoding='utf-8', creationflags=flags)
        if initialized.returncode:
            raise RuntimeError('隔离库初始化失败：' + initialized.stderr)
        with (work / 'server.log').open('w', encoding='utf-8') as log:
            server = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve', str(port), str(work / 'model-trace.jsonl')],
                cwd=ROOT, env=env, stdout=log, stderr=log, creationflags=flags)
            try:
                with httpx.Client(base_url=base, timeout=2, trust_env=False) as client:
                    for _ in range(150):
                        if server.poll() is not None:
                            raise RuntimeError('隔离服务启动失败：' + (work / 'server.log').read_text(encoding='utf-8'))
                        try:
                            if client.get('/api/health').status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(.1)
                    else:
                        raise RuntimeError('隔离服务未就绪')
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=executable, headless=True)
                    try:
                        result = exercise(browser, base, password, output, work)
                        (output / 'acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                        print(json.dumps(result, ensure_ascii=False, indent=2))
                    finally:
                        browser.close()
            finally:
                if os.name == 'nt' and server.poll() is None:
                    subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'], capture_output=True, creationflags=flags)
                elif server.poll() is None:
                    server.terminate()
                server.wait(timeout=10)
        if os.name == 'nt':
            for _ in range(50):
                try:
                    os.replace(work / 'server.log', work / 'server.log')
                    break
                except PermissionError:
                    time.sleep(.1)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--serve':
        serve(int(sys.argv[2]), sys.argv[3])
    else:
        main()
