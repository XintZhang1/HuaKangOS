"""Focused HTTP and real Chromium cache/update regression, with no business DB.

Usage: python tests/web_release_cache.py --output /tmp/new-cache-check \
    --browser /path/to/chromium
Copies only the current cache module and update UI into a new external synthetic
fixture. Tests real HTTP caching across three release directories on one origin.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import threading
import time

import httpx
from playwright.async_api import async_playwright, expect
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
import uvicorn


def require(condition, text):
    if not condition:
        raise AssertionError(text)


async def run(output, browser):
    repository = Path(__file__).resolve().parents[1]
    output = output.resolve()
    require(not output.is_relative_to(repository) and not output.exists(), 'Use a new external fixture directory')
    output.mkdir(parents=True)
    module_copy = output / 'web_release.py'
    shutil.copyfile(repository / 'app/web_release.py', module_copy)
    spec = importlib.util.spec_from_file_location('isolated_web_release', module_copy)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = {'synthetic_data_only': True, 'business_database_access': False, 'passed': False,
              'checks': [], 'page_errors': [], 'external_requests': [], 'inputs': {}}
    for name in ('app/web_release.py', 'web/appversion.js', 'web/appversion.css'):
        result['inputs'][name] = hashlib.sha256((repository / name).read_bytes()).hexdigest()
    template = '''<!doctype html><html><head><meta name="huakangos-release" content="__HUAKANGOS_RELEASE__">
    <link rel="stylesheet" href="/static/demo.css?v=unchanged">
    <link rel="stylesheet" href="/static/appversion.css"></head><body>
    <form><input name="draft" id="draft" value=""><button type="button">保留草稿</button></form>
    <div id="loaded"></div><script src="/static/appversion.js" defer></script>
    <script src="/static/demo.js?v=unchanged" defer></script></body></html>'''
    releases, statics = [], []
    for value, color in (('old', 'red'), ('new', 'tan'), ('two', 'skyblue')):
        root = output / value
        (root / 'app').mkdir(parents=True)
        (root / 'web').mkdir()
        (root / 'app/backend.py').write_text('version = "same"\n')
        (root / 'web/index.html').write_text(template)
        (root / 'web/demo.css').write_text(f'body{{background-color:{color}}}')
        (root / 'web/demo.js').write_text(
            f'window.cacheDemo="{value}";document.querySelector("#loaded").textContent=cacheDemo;'
            'window.brState={drafts:{}};document.querySelector("#draft").addEventListener("input",'
            'e=>{brState.drafts.contract={values:{note:e.target.value}}});')
        for name in ('appversion.js', 'appversion.css'):
            shutil.copyfile(repository / 'web' / name, root / 'web' / name)
        os.utime(root / 'web/demo.js', (1700000000, 1700000000))
        releases.append(module.WebRelease(root))
        statics.append(module.ReleaseStaticFiles(releases[-1]))
    state = {'generation': 0, 'legacy': True, 'fail_version': False, 'version_calls': 0}

    async def home(request):
        if state['legacy']:
            return HTMLResponse(template.replace('<script src="/static/appversion.js" defer></script>', ''),
                                headers={'Cache-Control': 'public, max-age=86400', 'ETag': '"legacy-document"'})
        return releases[state['generation']].home()

    async def version(request):
        state['version_calls'] += 1
        return JSONResponse({'version': releases[state['generation']].version},
                            status_code=503 if state['fail_version'] else 200,
                            headers={'Cache-Control': 'no-store'})

    async def static(request):
        response = await statics[state['generation']].get_response(request.path_params['path'], request.scope)
        if state['legacy']:
            # Seed a stronger stale cache than the old heuristic policy permits.
            response.headers['Cache-Control'] = 'public, max-age=86400'
        return response

    app = Starlette(routes=[Route('/', home), Route('/api/app-version', version),
                            Route('/static/{path:path}', static, methods=['GET', 'HEAD'])])
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{port}'
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            await asyncio.sleep(.05)
        require(server.started, 'Synthetic HTTP server did not start')
        state.update(generation=1, legacy=False)
        async with httpx.AsyncClient(base_url=origin) as client:
            page = await client.get('/')
            require(page.headers['cache-control'] == 'no-store', 'Document must not be reused from cache')
            require(releases[1].version in page.text, 'Document must carry release fingerprint')
            urls = re.findall(r'(?:src|href)="([^"]+)"', page.text)
            require(all(re.search(r'\?v=[a-f0-9]{64}$', url) for url in urls), 'Every asset needs an automatic content hash')
            direct = await client.get('/static/index.html')
            require(direct.text == page.text and direct.headers['cache-control'] == 'no-store', 'Direct index entry must use the same fresh document')
            response = await client.get('/static/demo.js?v=unchanged')
            old_etag = response.headers['etag']
            require(response.headers['cache-control'] == module.REVALIDATE, 'Static files must revalidate')
            for tag in (old_etag, 'W/' + old_etag, '*'):
                same = await client.get('/static/demo.js', headers={'If-None-Match': tag})
                require(same.status_code == 304, 'Unchanged content should permit safe 304')
            timestamp = await client.get('/static/demo.js', headers={'If-Modified-Since': 'Fri, 01 Jan 2100 00:00:00 GMT'})
            require(timestamp.status_code == 200, 'Timestamp alone must not hide new bytes')
            state['generation'] = 2
            changed = await client.get('/static/demo.js?v=unchanged', headers={'If-None-Match': old_etag})
            require(changed.status_code == 200 and changed.headers['etag'] != old_etag and '"two"' in changed.text,
                    'Equal mtime/size builds must return changed content, even at an old URL')
            require((releases[1].root / 'web/demo.js').stat().st_size == (releases[2].root / 'web/demo.js').stat().st_size,
                    'The regression needs genuinely equal-sized JS files')
            head = await client.head('/static/demo.js')
            require(not head.content and int(head.headers['content-length']) == len(changed.content), 'HEAD must describe the same bytes')
            backend = releases[2].root / 'app/backend.py'
            backend.write_text('version = "next"\n')
            require(module.WebRelease(releases[2].root).version != releases[2].version, 'Backend-only changes need a new release fingerprint')
            backend.write_text('version = "same"\n')
            result['checks'].append('HTTP: fresh HTML, all asset hashes, safe 304, equal-mtime/size replacement, HEAD, backend-only update')

        state.update(generation=0, legacy=True)
        async with async_playwright() as playwright:
            chromium = await playwright.chromium.launch(executable_path=str(browser), headless=True)
            context = await chromium.new_context()
            await context.add_cookies([{'name': 'cache_test_session', 'value': 'synthetic', 'url': origin}])
            page = await context.new_page()
            page.on('pageerror', lambda error: result['page_errors'].append(str(error)))
            page.on('request', lambda request: result['external_requests'].append(request.url)
                    if not request.url.startswith(origin + '/') else None)
            await page.clock.install()
            await page.goto(origin)
            await expect(page.locator('#loaded')).to_have_text('old')
            await page.evaluate("sessionStorage.setItem('huakangos.active-store','synthetic-store')")
            state.update(generation=1, legacy=False)
            # Same context/origin, no cache clearing, interception or new browser.
            await page.reload()
            await expect(page.locator('#loaded')).to_have_text('new')
            require(await page.locator('body').evaluate('(node)=>getComputedStyle(node).backgroundColor') == 'rgb(210, 180, 140)',
                    'Previously cached stylesheet must update too')
            await page.goto(origin)
            await expect(page.locator('#loaded')).to_have_text('new')
            result['checks'].append('Chromium: cached legacy HTML/JS/CSS update on normal reload; subsequent same-browser revisit stays current')
            await page.locator('#draft').fill('合成草稿，更新前保留')
            loaded = await page.locator('meta[name="huakangos-release"]').get_attribute('content')
            state['generation'] = 2
            await page.clock.fast_forward(61000)
            await expect(page.locator('#app-update-notice')).to_be_visible()
            await expect(page.locator('#draft')).to_have_value('合成草稿，更新前保留')
            require(await page.locator('meta[name="huakangos-release"]').get_attribute('content') == loaded,
                    'Polling must not reload the old page')
            async def cancel(dialog):
                require(dialog.type == 'confirm', 'Draft update needs explicit discard confirmation')
                await dialog.dismiss()
            page.once('dialog', cancel)
            await page.locator('#app-update-now').click()
            await expect(page.locator('#draft')).to_have_value('合成草稿，更新前保留')
            await page.evaluate("()=>{window.finishSyntheticWrite=huakangAppVersion.beginRequest('POST');}")
            await page.locator('#app-update-now').click()
            await expect(page.locator('#app-update-message')).to_contain_text('正在提交')
            await page.evaluate('finishSyntheticWrite();brState.drafts={};document.querySelector("form").reset()')
            for pending in ({'runId': 'synthetic-run'}, {'session': {'busy': True}}, {'files': {'busy': True}}):
                await page.evaluate('(value)=>{window.businessAssistantState=value}', pending)
                await page.locator('#app-update-now').click()
                require(await page.locator('meta[name="huakangos-release"]').get_attribute('content') == loaded,
                        'Assistant work must block updating even without an open form')
            await page.evaluate('window.businessAssistantState={};window.AssistantWorkspace={snapshot:()=>({followupPending:true})}')
            await page.locator('#app-update-now').click()
            require(await page.locator('meta[name="huakangos-release"]').get_attribute('content') == loaded,
                    'A pending follow-up change must block updating')
            await page.evaluate('window.AssistantWorkspace={snapshot:()=>({followupPending:false}),hasUnsavedUi:()=>true}')
            page.once('dialog', cancel)
            await page.locator('#app-update-now').click()
            require(await page.locator('meta[name="huakangos-release"]').get_attribute('content') == loaded,
                    'A saved in-memory assistant draft needs explicit discard confirmation')
            await page.evaluate('window.AssistantWorkspace=null')
            state['fail_version'] = True
            await page.evaluate('huakangAppVersion.check()')
            require(await page.locator('meta[name="huakangos-release"]').get_attribute('content') == loaded,
                    'Restart/offline checks must not force navigation')
            state['fail_version'] = False
            async with page.expect_navigation():
                await page.locator('#app-update-now').click()
            await expect(page.locator('#loaded')).to_have_text('two')
            require(await page.evaluate("sessionStorage.getItem('huakangos.active-store')") == 'synthetic-store',
                    'Updating must preserve the store preference')
            require(any(cookie['name'] == 'cache_test_session' and cookie['value'] == 'synthetic'
                        for cookie in await context.cookies()), 'Updating must preserve login cookies')
            await expect(page.locator('#app-update-notice')).to_have_count(0)
            result['checks'].append('Chromium: timed notice, form/assistant drafts, pending writes/runs/follow-up, explicit reload, cookie/store retention, transient error')
            require(not result['page_errors'] and not result['external_requests'], 'No browser errors or external requests permitted')
            await chromium.close()
        result['passed'] = True
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        result['server_stopped'] = not thread.is_alive()
        (output / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    require(result['server_stopped'], 'Fixture server failed to stop')
    print(json.dumps({'passed': True, 'checks': len(result['checks']), 'report': str(output / 'report.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browser', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.output, args.browser.resolve(strict=True)))
