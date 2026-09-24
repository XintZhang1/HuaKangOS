"""Real Chrome file-to-form trial; only model replies are scripted, never paid.

Uses a new temporary database, actual sales login, multipart parser, assistant
service, human confirmation gateway and native sales lead. No company data.
Run with --screenshots OUTSIDE_REPOSITORY. --serve is internal to this harness.
"""
import argparse
import hashlib
import io
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
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from playwright.sync_api import expect, sync_playwright
from tests import browser_huakangos as h


def package(parts):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)
    return output.getvalue()


def fixtures(work):
    folder = work / '合成待整理资料'
    folder.mkdir()
    (folder / '客户.csv').write_text('姓名,电话,来源,备注\n文件合成甲,13900007771,展厅到店,0\n不发送合成乙,13900007772,展厅到店,=1+1\n', encoding='utf-8-sig')
    (folder / '说明.txt').write_text('合成文本资料：仅作试用，不要自动办理。', encoding='utf-8')
    spreadsheet = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    relationship = 'http://schemas.openxmlformats.org/package/2006/relationships'
    (folder / '车型.xlsx').write_bytes(package({
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        'xl/workbook.xml': f'<workbook xmlns="{spreadsheet}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="合成车型" sheetId="1" r:id="r1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': f'<Relationships xmlns="{relationship}"><Relationship Id="r1" Target="worksheets/sheet1.xml" Type="worksheet"/></Relationships>',
        'xl/worksheets/sheet1.xml': f'<worksheet xmlns="{spreadsheet}"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>车型</t></is></c><c r="B1" t="inlineStr"><is><t>编号</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>合成纯电车</t></is></c><c r="B2" t="inlineStr"><is><t>0007</t></is></c></row></sheetData></worksheet>',
    }))
    word = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    (folder / '接待.docx').write_bytes(package({
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        'word/document.xml': f'<w:document xmlns:w="{word}"><w:body><w:p><w:r><w:t>合成 Word 接待说明</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>客户</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>合成 Word 客户</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>',
    }))
    invalid = work / '不能执行.py'
    invalid.write_text("raise RuntimeError('MUST_NOT_EXECUTE')", encoding='utf-8')
    paged = work / '多页.csv'
    paged.write_text('姓名,编号\n' + ''.join(f'分页合成{i},00{i}\n' for i in range(52)), encoding='utf-8')
    return folder, invalid, paged


def serve(port, trace):
    # This process only receives browser_environment's newly created test DB.
    assert os.environ.get('APP_ENV') == 'test'
    assert 'huakangos-assistant-files-' in os.environ.get('DATABASE_URL', '')
    from app import business_assistant_service as service
    from app import business_assistant_stream as stream
    from app.main import app
    import uvicorn
    service.load_config = lambda: service.AssistantConfig(True, 'synthetic-no-network', 'scripted-browser-fixture', 5, True)

    def no_provider(*args, **kwargs):
        raise AssertionError('External model requests are forbidden in this test')

    service.provider_request = no_provider

    async def reply(config, messages):
        with Path(trace).open('a', encoding='utf-8') as log:
            log.write(json.dumps({'roles': [m['role'] for m in messages]}, ensure_ascii=False) + '\n')
        if messages[-1]['role'] == 'tool':
            return {'content': '请核对下方表单，点击确认办理。'}
        latest = next(m['content'] for m in reversed(messages) if m['role'] == 'user')
        if '<文件资料>' not in latest:
            return {'content': '请在待确认表单中点击确认办理。'}
        selected = json.loads(latest.split('<文件资料>\n', 1)[1].split('\n</文件资料>', 1)[0])
        assert len(selected) == 1 and len(selected[0]['tables']) == 1
        table = selected[0]['tables'][0]
        assert len(table['rows']) == 1 and table['rows'][0]['row_number'] == 2
        row = dict(zip(table['columns'], table['rows'][0]['values']))
        assert row['姓名'] == '文件合成甲' and '不发送合成乙' not in latest
        values = {'customer_name': row['姓名'], 'customer_phone': row['电话'], 'source': row['来源']}
        return {'content': '已经整理好所选资料。', 'tool_calls': [{'id': 'file-lead', 'type': 'function', 'function': {
            'name': 'prepare_operation', 'arguments': json.dumps({'operation_id': 'POST /api/flow/cases',
                'summary': '登记文件合成甲的售前接待', 'body': {'kind': 'lead', 'values': values}}, ensure_ascii=False)}}]}

    async def stream_reply(config, messages, thinking, emit):
        result = await reply(config, messages)
        await emit('status', {'phase': 'responding'})
        if result.get('content'):
            await emit('delta', {'text': result['content']})
        return result

    service.model_reply = no_provider
    stream.model_reply_stream = stream_reply
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')


def exercise(browser, base, password, output, work):
    context = browser.new_context(viewport={'width': 390, 'height': 844}, locale='zh-CN', accept_downloads=True)
    page = context.new_page()
    errors, steps, screenshots, sent = [], [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: sent.append(request.post_data_json) if request.method == 'POST' and urlsplit(request.url).path.endswith('/messages/stream') else None)
    folder, invalid, paged = fixtures(work)
    original_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in folder.iterdir()}
    trace = work / 'model-trace.jsonl'

    def count_leads():
        return h.checked_request(page, '/api/flow/cases?kind=lead')['total']

    def open_files():
        page.locator('.ba-files-tab[data-baf-action=open]').click()
        expect(page.locator('#ba-file-picker')).to_be_attached()

    def choose_file(suffix):
        options = page.locator('#ba-active-file option').evaluate_all('(rows)=>rows.map(r=>({value:r.value,label:r.textContent}))')
        matches = [item for item in options if item['label'].endswith(suffix)]
        assert len(matches) == 1, options
        page.locator('#ba-active-file').select_option(matches[0]['value'])
        return matches[0]['value']

    def upload(input_id, path, expected_files):
        with page.expect_response(lambda response: urlsplit(response.url).path == '/api/business-assistant/file-preview') as response:
            page.locator(input_id).set_input_files(path)
        assert response.value.status == 200, response.value.text()
        expect(page.locator('#ba-active-file option')).to_have_count(expected_files)
        expect(page.locator('#ba-file-picker')).to_be_enabled()
        return response.value.json()

    def download(button, name):
        with page.expect_download() as pending:
            page.locator(button).click()
        target = output / name
        pending.value.save_as(str(target))
        return target.read_text(encoding='utf-8-sig')

    try:
        h.login_page(page, base, 'admin', password)
        second = h.checked_request(page, '/api/stores', 'POST', {'name': '文件试用二店', 'code': 'ASSISTANT-FILES-2'}, status=201)
        initial, changed = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        h.checked_request(page, '/api/users', 'POST', {'username': 'assistant-files-sales', 'display_name': '文件试用销售', 'password': initial, 'role': 'sales',
            'store_ids': [1, second['id']], 'store_roles': [{'store_id': 1, 'role': 'sales'}, {'store_id': second['id'], 'role': 'sales'}]}, status=201)
        h.checked_request(page, '/api/auth/logout', 'POST', {})
        h.login_page(page, base, 'assistant-files-sales', initial)
        h.checked_request(page, '/api/auth/password', 'POST', {'current_password': initial, 'new_password': changed})
        h.login_page(page, base, 'assistant-files-sales', changed)
        h.navigate(page, 'business-assistant', '业务助手')
        expect(page.locator('.identity .role')).to_have_text('销售')
        open_files()
        result = upload('#ba-file-picker', [str(p) for p in sorted(folder.iterdir())], 4)
        assert all(not item['error'] for item in result['files']), result
        assert not trace.exists() and count_leads() == 0
        choose_file('车型.xlsx')
        expect(page.locator('.ba-file-table')).to_contain_text('合成纯电车')
        expect(page.locator('.ba-file-table')).to_contain_text('0007')
        choose_file('接待.docx')
        expect(page.locator('.ba-file-table')).to_contain_text('合成 Word 客户')
        expect(page.locator('.ba-file-text')).to_contain_text('合成 Word 接待说明')
        choose_file('说明.txt')
        expect(page.locator('.ba-file-text')).to_contain_text('合成文本资料')
        expect(page.locator('#ba-file-text')).not_to_be_checked()
        choose_file('客户.csv')
        expect(page.locator('.ba-file-table')).to_contain_text('文件合成甲')
        expect(page.locator('[data-baf-row]:checked')).to_have_count(0)
        # Browser automation's click scrolls even overflow:hidden containers.
        # Check an employee can actually wheel to the rows without that help.
        page.locator('.ba-files h2').scroll_into_view_if_needed()
        page.mouse.move(320, 600)
        page.mouse.wheel(0, 650)
        expect(page.locator('[data-baf-row]').first).to_be_in_viewport(timeout=3000)
        h.assert_fits_mobile(page)
        screenshots.append(h.take_screenshot(page, output, '01-files-mobile-preview.png'))
        steps.append('390px 真实销售账号选择 Excel/CSV/Word/TXT，原文件预览保留编号前导零，默认不勾选，不调用模型、不新增业务')

        exported = download('[data-baf-action=export-table]', 'table-export.csv')
        assert '文件合成甲' in exported and '不发送合成乙' in exported and '"\'=1+1"' in exported
        steps.append('真实下载表格 CSV，完整保留两行，公式文本加引号前缀防止电子表格执行')

        result = upload('#ba-folder-picker', str(folder), 4)
        assert all(item['name'].startswith(folder.name + '/') for item in result['files']), result
        steps.append('原生文件夹选择提交相对名称，四类文件均由真实预览接口解析')

        upload('#ba-file-picker', str(paged), 1)
        expect(page.locator('[data-baf-row]')).to_have_count(50)
        page.locator('[data-baf-action=next]').click()
        expect(page.locator('[data-baf-row]')).to_have_count(2)
        page.locator('[data-baf-action=select-page]').click()
        expect(page.locator('[data-baf-row]:checked')).to_have_count(2)
        page.locator('[data-baf-action=prev]').click()
        expect(page.locator('[data-baf-row]:checked')).to_have_count(0)
        page.locator('[data-baf-action=next]').click()
        expect(page.locator('[data-baf-row]:checked')).to_have_count(2)
        page.locator('[data-baf-action=unselect-page]').click()
        expect(page.locator('[data-baf-row]:checked')).to_have_count(0)
        steps.append('52 行表格分页不漏行，选择本页只勾选当前页，翻页保留选择并可取消')

        upload('#ba-file-picker', str(invalid), 1)
        expect(page.locator('.ba-file-preview .ba-error')).to_be_visible()
        expect(page.locator('#ba-file-picker')).to_be_enabled()
        page.route('**/api/business-assistant/file-preview', lambda route: route.fulfill(status=503, content_type='application/json', body=json.dumps({'detail': '合成网络故障，请重试'}, ensure_ascii=False)), times=1)
        page.locator('#ba-file-picker').set_input_files(str(folder / '客户.csv'))
        expect(page.locator('#ba-file-error')).to_have_text('合成网络故障，请重试')
        expect(page.locator('#ba-file-picker')).to_be_enabled()
        upload('#ba-file-picker', str(folder / '客户.csv'), 1)
        expect(page.locator('#ba-file-error')).to_have_text('')
        page.locator('[data-baf-action=fill]').click()
        expect(page.locator('#ba-file-error')).to_contain_text('先勾选')
        page.locator('[data-baf-row="0:0:0"]').check()
        page.locator('[data-baf-action=fill]').click()
        expect(page.locator('#ba-file-error')).to_contain_text('要办什么事')
        page.locator('#ba-file-goal').fill('登记选中客户的售前接待')
        page.locator('[data-baf-action=preview]').click()
        expect(page.locator('#modal')).to_contain_text('文件合成甲')
        expect(page.locator('#modal')).not_to_contain_text('不发送合成乙')
        h.assert_fits_mobile(page)
        page.locator('#modal [data-act=close]').last.click()
        assert not trace.exists() and not sent and count_leads() == 0
        steps.append('代码文件拒绝、接口故障、未勾选及未填事项均显示中文错误，修正后可继续；核对弹窗仅含选中行')

        page.locator('[data-baf-action=fill]').click()
        expect(page.locator('.ba-proposal')).to_contain_text('文件合成甲', timeout=15000)
        expect(page.locator('.ba-proposal')).to_contain_text('待确认')
        file_message = page.locator('.ba-user .ba-file-message')
        expect(file_message).to_contain_text('已发送 1 个文件的选中资料 · 1 行')
        assert '以下 JSON' not in page.locator('.ba-user').inner_text()
        assert '<文件资料>' not in page.locator('.ba-user').inner_text()
        expect(file_message.locator('details')).not_to_have_attribute('open', '')
        file_message.locator('summary').click()
        expect(file_message.locator('tbody tr')).to_have_count(1)
        expect(file_message).to_contain_text('文件合成甲')
        expect(file_message).not_to_contain_text('不发送合成乙')
        file_message.locator('summary').click()
        assert len(sent) == 1 and '不发送合成乙' not in sent[0]['content']
        assert count_leads() == 0
        h.assert_fits_mobile(page)
        page.locator('.ba-proposal').scroll_into_view_if_needed()
        screenshots.append(h.take_screenshot(page, output, '02-files-mobile-proposal.png'))
        exported = download('[data-baf-action=export-proposal]', 'proposal-export.csv')
        assert '文件合成甲' in exported and '待确认' in exported and '不发送合成乙' not in exported
        page.locator('#business-assistant-input').fill('确认')
        page.locator('#business-assistant-form button[type=submit]').click()
        expect(page.locator('.ba-assistant .ba-text').last).to_contain_text('请在待确认表单中点击')
        assert count_leads() == 0
        page.locator('[data-ba-action=confirm]').click()
        expect(page.locator('.ba-proposal')).to_contain_text('已完成', timeout=15000)
        expect(page.locator('[data-ba-action=confirm]')).to_have_count(0)
        leads = h.checked_request(page, '/api/flow/cases?kind=lead')
        assert leads['total'] == 1 and '文件合成甲' in json.dumps(leads, ensure_ascii=False), leads
        assert '不发送合成乙' not in json.dumps(leads, ensure_ascii=False)
        page.locator('.ba-proposal').scroll_into_view_if_needed()
        screenshots.append(h.take_screenshot(page, output, '03-files-mobile-completed.png'))
        steps.append('仅勾选资料发送至脚本模型，真实服务生成待确认表单；聊天输入确认不写业务，人工按钮确认后原系统售前接待恰好新增一笔；填写内容可导出')

        page.locator('.ba-proposal .ba-record-link').last.click()
        expect(page.locator('#main')).to_contain_text('文件合成甲')
        h.navigate(page, 'business-assistant', '业务助手')
        open_files()
        expect(page.locator('#ba-active-file')).to_be_visible()
        page.locator('#ba-file-goal').fill('一店未发送资料')
        page.locator('#store').select_option(str(second['id']))
        expect(page.locator('#main h1')).to_have_text('我的工作')
        h.navigate(page, 'business-assistant', '业务助手')
        open_files()
        expect(page.locator('#ba-active-file')).to_have_count(0)
        expect(page.locator('#main')).not_to_contain_text('一店未发送资料')
        expect(page.locator('#main')).not_to_contain_text('文件合成甲')
        h.assert_fits_mobile(page)
        steps.append('完成后可返回原单据；切换二店清空文件、勾选、待发事项及原店对话')
        assert original_hashes == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in folder.iterdir()}
        assert not errors, errors
        return {'mode': 'real Windows Chrome 390px; synthetic sales employee; real file parser, assistant SSE gateway and native business APIs; streaming model adapter scripted',
            'passed': len(steps), 'steps': steps, 'screenshots': screenshots, 'javascript_errors': errors,
            'paid_api_calls': 0, 'scripted_model_calls': len(trace.read_text(encoding='utf-8').splitlines()),
            'input_files_unchanged': True, 'native_leads_created': 1,
            'limitations': ['模型回复为固定脚本，本记录不证明真实 DeepSeek 理解或填表能力', '仅本地 HTTP；不替代生产 HTTPS、公司资料或业务验收']}
    except Exception:
        h.take_screenshot(page, output, 'assistant-files-failure.png')
        raise
    finally:
        context.close()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshots', type=Path)
    args = parser.parse_args()
    executable = h.chromium_path()
    if not executable:
        raise SystemExit('请安装 Chrome/Edge 或设置 CHROMIUM_PATH。')
    output = (args.screenshots or Path(tempfile.mkdtemp(prefix='huakangos-assistant-file-evidence-'))).resolve()
    if output == h.ROOT or h.ROOT in output.parents:
        raise SystemExit('验收记录必须存放在源码目录之外。')
    output.mkdir(parents=True, exist_ok=True)
    # A failed rerun must never leave an earlier pass looking current.
    (output / 'acceptance.json').unlink(missing_ok=True)
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    with tempfile.TemporaryDirectory(prefix='huakangos-assistant-files-') as work_path:
        work = Path(work_path)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        password = secrets.token_urlsafe(28)
        env = h.browser_environment(work, password)
        env.update(BUSINESS_ASSISTANT_CONFIG='', PYTHONDONTWRITEBYTECODE='1')
        initialized = subprocess.run([sys.executable, '-m', 'app.cli', 'init'], cwd=h.ROOT, env=env, capture_output=True, text=True, encoding='utf-8', creationflags=flags)
        if initialized.returncode:
            raise RuntimeError('隔离库初始化失败：' + initialized.stderr)
        with (work / 'server.log').open('w', encoding='utf-8') as log:
            server = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve', str(port), str(work / 'model-trace.jsonl')],
                cwd=h.ROOT, env=env, stdout=log, stderr=log, creationflags=flags)
            try:
                with httpx.Client(base_url=base, timeout=2, trust_env=False) as client:
                    for _ in range(120):
                        if server.poll() is not None:
                            raise RuntimeError('隔离测试服务启动失败：' + (work / 'server.log').read_text(encoding='utf-8'))
                        try:
                            if client.get('/api/health').status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(.1)
                    else:
                        raise RuntimeError('隔离测试服务未能就绪')
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
