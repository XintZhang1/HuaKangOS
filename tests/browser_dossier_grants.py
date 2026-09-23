"""Owner-run real-browser original dossier / selected-file acceptance.

python tests/browser_dossier_grants.py [--screenshots OUTSIDE_REPOSITORY]
Uses the existing harness's new synthetic SQLite database, generated passwords
and owned local server. Importing/compiling this file is NOT browser acceptance.
"""
from pathlib import Path
import secrets
import re
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login


def exercise(browser, base, password, output):
    contexts, errors, steps, screenshots = [], [], [], []
    suffix = secrets.token_hex(4)
    req = harness.checked_request

    def new_page():
        context = browser.new_context(viewport={'width': 390, 'height': 844}, locale='zh-CN')
        contexts.append(context)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        return page

    admin = new_page()
    try:
        harness.login_page(admin, base, 'admin', password)
        two = req(admin, '/api/stores', 'POST', {'code': 'DOS-' + suffix,
                   'name': '合成档案接收店', 'active': True}, status=201)['id']
        people = {}
        for label, role, sid in [('sender', 'sales', 1), ('reviewer', 'manager', 1),
                                 ('receiver', 'sales', two), ('peer', 'sales', two)]:
            name, initial = 'dossier-' + label + '-' + suffix, secrets.token_urlsafe(28)
            row = req(admin, '/api/users', 'POST', {'username': name, 'display_name': '合成授权' + label,
                'role': role, 'password': initial, 'store_roles': [{'store_id': sid, 'role': role}]}, status=201)
            page = new_page(); employee_login(page, base, name, initial)
            # Explicitly choose the employee's actual active store in the UI.
            page.locator('#store').select_option(str(sid))
            people[label] = (page, row['id'])
        sender, sender_id = people['sender']; reviewer, _ = people['reviewer']
        receiver, receiver_id = people['receiver']; peer, _ = people['peer']
        row = req(admin, '/api/flow/cases', 'POST', {'request_id': secrets.token_hex(16), 'kind': 'lead',
            'values': {'customer_name': '合成授权客户' + suffix,
                       'customer_phone': '13900' + str(secrets.randbelow(1000000)).zfill(6),
                       'source': '展厅到店', 'model': '合成车型', 'confirm_new_customer': True}}, status=201)
        row = req(admin, f'/api/flow/cases/{row["id"]}/actions/assign', 'POST', {
            'request_id': secrets.token_hex(16), 'version': row['version'], 'values': {'assignee_id': sender_id}})
        files = []
        raw = b'Synthetic exact selected document, not company data'
        for category in ('evidence', 'inspection'):
            harness.navigate(sender, 'case/' + str(row['id']), row['title'])
            sender.locator('[data-act=upload]').click()
            sender.locator('#modal [name=category]').select_option(category)
            filename = '合成逐件-' + category + '-' + suffix + '.txt'
            sender.locator('#modal [name=file]').set_input_files({'name': filename, 'mimeType': 'text/plain', 'buffer': raw})
            harness.save_modal(sender)
            files.append(next(f['id'] for f in req(sender, f'/api/flow/cases/{row["id"]}')['files'] if f['name'] == filename))
        assert files[0] != files[1]
        sender.locator('[data-act=dossier-new]').click()
        sender.locator('#modal [name=to_store_id]').select_option(str(two))
        expect(sender.locator('#modal [name=recipient_id]')).to_be_enabled()
        sender.locator('#modal [name=recipient_id]').select_option(str(receiver_id))
        expect(sender.locator('#modal [name=dossier_file]')).to_have_count(2)
        expect(sender.locator('#modal [name=include_contact]')).not_to_be_checked()
        expect(sender.locator('#modal [name=include_financials]')).not_to_be_checked()
        assert sender.locator('#modal [name=dossier_file]:checked').count() == 0
        sender.locator(f'#modal [name=dossier_file][value="{files[0]}"]').check()
        sender.locator('#modal [name=purpose]').fill('仅本次指定员工核对原记录和勾选的原件')
        sender.locator('#modal [name=confirmed]').check()
        harness.assert_fits_mobile(sender)
        screenshots.append(harness.take_screenshot(sender, output, 'dossier_01_exact_scope_390px.png'))
        harness.save_modal(sender)
        expect(sender.locator('#main h1')).to_have_text('档案授权')
        items = req(sender, '/api/dossier-grants?box=sent')['items']
        grant = req(sender, '/api/dossier-grants/' + str(items[0]['id']))
        assert grant['status'] == 'pending' and [f['id'] for f in grant['files']] == [files[0]]
        expect(sender.locator('[data-act=dossier-decision][data-key=approve]')).to_have_count(0)
        req(receiver, f'/api/dossier-grants/{grant["id"]}/record', store=two, status=403)
        steps.append('真实页面指定门店和员工；文件默认全不选，电话金额独立选择，发起人不能自批')

        harness.navigate(reviewer, f'dossier-grants/review/{grant["id"]}', '档案授权')
        reviewer.locator('[data-act=dossier-decision][data-key=approve]').click()
        reviewer.locator('#modal [name=reason]').fill('独立核对原单版本、具体员工和仅一份文件')
        reviewer.locator('#modal [name=confirmed]').check()
        harness.save_modal(reviewer)
        expect(reviewer.locator('#main')).to_contain_text('已批准')
        screenshots.append(harness.take_screenshot(reviewer, output, 'dossier_02_review_390px.png'))
        steps.append('原店不同人员从真实页面独立批准原版本与逐件文件')

        harness.navigate(receiver, f'dossier-grants/received/{grant["id"]}', '档案授权')
        expect(receiver.locator('#main')).to_contain_text('已冻结的原单快照')
        expect(receiver.locator('[data-act=dossier-download]')).to_have_count(1)
        with receiver.expect_download() as downloading:
            receiver.locator('[data-act=dossier-download]').click()
        assert Path(downloading.value.path()).read_bytes() == raw
        for path in (f'/api/flow/cases/{row["id"]}', f'/api/flow/files/{files[0]}',
                     f'/api/dossier-grants/{grant["id"]}/files/{files[1]}'):
            req(receiver, path, store=two, status=404)
        req(peer, f'/api/dossier-grants/{grant["id"]}/record', store=two, status=404)
        harness.assert_fits_mobile(receiver)
        screenshots.append(harness.take_screenshot(receiver, output, 'dossier_03_received_390px.png'))
        steps.append('指定员工真实下载字节一致；同内容未选文件、同店同岗位其他员工、原单原地址均拒绝')

        reviewer.locator('[data-act=dossier-decision][data-key=revoke]').click()
        reviewer.locator('#modal [name=reason]').fill('原店确认此临时用途已结束，撤销未来读取')
        reviewer.locator('#modal [name=confirmed]').check(); harness.save_modal(reviewer)
        req(receiver, f'/api/dossier-grants/{grant["id"]}/files/{files[0]}', store=two, status=403)
        receiver.locator('[data-act=refresh]').click()
        expect(receiver.locator('#main')).to_contain_text('当前不可读取')
        expect(receiver.locator('[data-act=dossier-download]')).to_have_count(0)
        expect(receiver.locator('#main')).not_to_contain_text('合成授权客户' + suffix)
        screenshots.append(harness.take_screenshot(receiver, output, 'dossier_04_revoked_390px.png'))
        steps.append('撤销后旧链接拒绝；接收页面重新核验清除原单及下载按钮，不声称远程删除既有副本')
        assert not errors, errors
        return {'status': 'passed', 'mode': 'actual-browser-http', 'synthetic_only': True,
                'viewport': '390x844', 'steps': steps, 'screenshots': screenshots, 'javascript_errors': errors}
    finally:
        for context in contexts:
            context.close()


if __name__ == '__main__':
    harness.exercise = exercise
    harness.main()
