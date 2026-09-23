"""Portable real-browser gate acceptance; execute only in a disposable local test environment.

This script is retained for the owner's later computer run. Merely collecting or
compiling it is not browser acceptance. It never starts on import.
"""
import csv
import io
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login


def exercise(browser, base, password, output):
    contexts, errors, steps, screenshots = [], [], [], []
    req = harness.checked_request
    suffix = secrets.token_hex(4)

    def page(width=390):
        context = browser.new_context(viewport={'width': width, 'height': 844}, locale='zh-CN')
        contexts.append(context)
        result = context.new_page()
        result.on('pageerror', lambda error: errors.append(str(error)))
        return result

    def proof(p, case_id, name):
        row = req(p, '/api/flow/cases/' + str(case_id))
        harness.navigate(p, 'case/' + str(case_id), row['title'])
        p.locator('[data-act=upload]').click()
        p.locator('#modal [name=category]').select_option('evidence')
        filename = name + '-' + suffix + '.txt'
        p.locator('#modal [name=file]').set_input_files({'name': filename, 'mimeType': 'text/plain', 'buffer': ('合成验收凭据：' + name).encode()})
        harness.save_modal(p)
        return next(f['id'] for f in req(p, '/api/flow/cases/' + str(case_id))['files'] if f['name'] == filename)

    def visit(p, row):
        harness.navigate(p, 'gate-visits/' + str(row['id']), row['title'])
        harness.assert_fits_mobile(p)

    def fill_actual(p, vin, fid):
        p.locator('#modal [name=checked_vin]').fill(vin)
        p.locator('#modal [name=evidence_id]').select_option(str(fid))
        p.locator('#modal [name=reason]').fill('合成现场逐位核对，本次时间及方向均有原凭据')
        expect(p.locator('#modal [name=confirmed]')).not_to_be_checked()
        p.locator('#modal [name=confirmed]').check()

    admin = page(1440)
    try:
        harness.login_page(admin, base, 'admin', password)
        workers = {}
        for role in ('service', 'manager'):
            secret = secrets.token_urlsafe(25)
            name = 'gate-' + role + '-' + suffix
            req(admin, '/api/users', 'POST', {'username': name, 'display_name': '合成门岗' + role, 'role': role,
                'password': secret, 'store_roles': [{'store_id': 1, 'role': role}]}, status=201)
            p = page()
            employee_login(p, base, name, secret)
            workers[role] = p
        service, manager = workers['service'], workers['manager']
        customer = req(admin, '/api/flow/master/customers', 'POST', {'values': {'name': '合成门岗客户' + suffix,
            'phone': '13900' + str(secrets.randbelow(1000000)).zfill(6), 'contact_allowed': True, 'confirm_new_customer': True}}, status=201)
        vin = 'LFV2A21K9J' + str(secrets.randbelow(10000000)).zfill(7)
        vehicle = req(admin, '/api/customer-service/vehicles', 'POST', {'request_id': secrets.token_hex(16), 'values': {
            'customer_id': customer['id'], 'vin': vin, 'plate': '合成门岗', 'model_name': '合成验收车型',
            'source_reference': '独立合成车辆身份凭据', 'confirmed': True}}, status=201)['vehicle']
        before = req(manager, '/api/visit-activity-reports')['metrics']
        harness.navigate(service, 'gate-visits', '非维修实际进出厂')
        service.locator('[data-act=gate-new]').click()
        service.locator('#modal [name=customer_vehicle_id]').select_option(str(vehicle['id']))
        service.locator('#modal [name=purpose]').select_option('consultation')
        service.locator('#modal [name=description]').fill('非维修咨询安排；保存时不代替实际进厂')
        harness.save_modal(service)
        row = next(r for r in req(service, '/api/gate-visits')['items'] if r['vin'] == vin)
        assert row['status'] == 'planned'
        assert req(manager, '/api/visit-activity-reports')['metrics']['service_actual_arrivals'] == before['service_actual_arrivals']
        fid = proof(service, row['case_id'], '现场实际进厂')
        visit(service, row)
        service.locator('[data-act=gate-action][data-key=arrive]').click()
        fill_actual(service, vin, fid)
        harness.save_modal(service)
        expect(service.locator('#main')).to_contain_text('已实际进厂')
        assert req(manager, '/api/visit-activity-reports')['metrics']['service_actual_arrivals'] == before['service_actual_arrivals'] + 1
        screenshots.append(harness.take_screenshot(service, output, 'gate_01_actual_arrival_390px.png'))
        steps.append('服务顾问真实页面登记安排和明确确认实际进厂；初始零计数，实际进厂仅新增一笔')
        original = req(service, '/api/gate-visits/' + str(row['id']))['facts'][0]['actual_at']
        service.locator('[data-act=gate-action][data-key=correct]').click()
        service.locator('#modal [name=kind]').select_option('arrive_time')
        corrected = (datetime.now().astimezone() - timedelta(minutes=15)).strftime('%Y-%m-%dT%H:%M')
        service.locator('#modal [name=actual_at]').fill(corrected)
        service.locator('#modal [name=evidence_id]').select_option(str(fid))
        service.locator('#modal [name=reason]').fill('核对门岗原记录后申请纠正错误的进厂时间')
        harness.save_modal(service)
        expect(service.locator('[data-act=gate-action][data-key=leave]')).to_have_count(0)
        expect(service.locator('[data-act=gate-review][data-key=approve]')).to_have_count(0)
        reviewer_file = proof(manager, row['case_id'], '另一主管独立复核原记录')
        visit(manager, row)
        manager.locator('[data-act=gate-review][data-key=approve]').click()
        manager.locator('#modal [name=evidence_id]').select_option(str(reviewer_file))
        manager.locator('#modal [name=reason]').fill('独立核对原车辆、门岗时点和申请依据属实')
        harness.save_modal(manager)
        current = req(manager, '/api/gate-visits/' + str(row['id']))
        assert current['facts'][0]['actual_at'] == original and current['arrived_at'] != original
        screenshots.append(harness.take_screenshot(manager, output, 'gate_02_independent_review_390px.png'))
        steps.append('纠正待复核时停止新进出动作；另一主管独立批准，原时间保留而有效时间改变')
        fid = proof(service, row['case_id'], '本次实际离场')
        visit(service, row)
        service.locator('[data-act=gate-action][data-key=leave]').click()
        fill_actual(service, vin, fid)
        harness.save_modal(service)
        assert req(service, '/api/gate-visits/' + str(row['id']))['status'] == 'departed'
        harness.navigate(manager, 'visit-activity', '跟进与进出厂统计')
        report = req(manager, '/api/visit-activity-reports')
        assert report['metrics']['service_actual_arrivals'] == before['service_actual_arrivals'] + 1
        assert report['metrics']['service_actual_departures'] == before['service_actual_departures'] + 1
        harness.assert_fits_mobile(manager)
        with manager.expect_download() as download:
            manager.locator('[data-act=va-export][data-key=service_gate_movements]').click()
        records = list(csv.reader(io.StringIO(Path(download.value.path()).read_text(encoding='utf-8-sig'))))
        table = report['tables']['service_gate_movements']
        assert records == [table['headers']] + [[str(v) for v in r['values']] for r in table['rows']]
        screenshots.append(harness.take_screenshot(manager, output, 'gate_03_same_source_report_390px.png'))
        steps.append('服务顾问明确确认实际离场，主管同源统计进一出一，真实下载 CSV 与源行逐格相同')
        assert not errors, errors
        return {'status': 'passed', 'mode': 'actual-browser-http', 'synthetic_only': True, 'viewport': '390x844',
            'steps': steps, 'screenshots': screenshots, 'javascript_errors': errors}
    finally:
        for context in contexts:
            context.close()


if __name__ == '__main__':
    harness.exercise = exercise
    harness.main()
