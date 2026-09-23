"""Real Chromium acceptance for huakangos employee accounts and store roles.

Run: python tests/browser_huakangos.py [--screenshots OUTSIDE_REPOSITORY]
Uses an independent temporary database, random credentials and actual browser HTTP.
Never uses a transport bridge or an existing company service/database.
"""
from pathlib import Path
import argparse
import json
import os
import secrets
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def browser_environment(work, password):
    """A fresh synthetic database must never inherit the company's object store."""
    return {**os.environ, 'DATABASE_URL': 'sqlite:///' + (work/'synthetic.sqlite').as_posix(),
            'APP_ENV': 'test', 'ALLOWED_HOSTS': '127.0.0.1,localhost', 'COOKIE_SECURE': 'false',
            'SCHEDULER_ENABLED': 'false', 'SCHEDULER_MODE': 'off', 'FILE_SCAN_MODE': 'structure_only',
            'FILE_STORAGE_MODE': 'blob', 'PRIVATE_FILE_ROOT': '', 'ALLOW_AI_EXTERNAL': 'false',
            'DEEPSEEK_API_KEY': '', 'LEGACY_BUSINESS_WRITE': 'false',
            'HUAKANGOS_INITIAL_PASSWORD': password, 'DEALER_INITIAL_PASSWORD': password, 'PYTHONUTF8': '1'}


def chromium_path():
    candidates = [os.getenv('CHROMIUM_PATH'), shutil.which('chromium'), shutil.which('google-chrome'),
                  r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                  r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe']
    return next((str(p) for p in candidates if p and Path(p).is_file()), None)


def request(page, path, method='GET', data=None, store='1', csrf=True):
    """Run fetch inside the actual browser; normal cookies, CSP and networking apply."""
    return page.evaluate('''async ({path,method,data,store,csrf})=>{
        const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];
        const headers={'Content-Type':'application/json','X-App-Request':'1','X-Store-ID':String(store)};
        if(csrf&&token)headers['X-CSRF-Token']=token;
        const r=await fetch(path,{method,headers,...(data===null?{}:{body:JSON.stringify(data)})});
        return {status:r.status,body:await r.json()};
    }''', {'path':path,'method':method,'data':data,'store':store,'csrf':csrf})


def login_page(page, base, username, password):
    page.goto(base)
    page.locator('.loginform [name=username]').fill(username)
    page.locator('.loginform [name=password]').fill(password)
    page.locator('.loginform button[type=submit]').click()
    page.wait_for_selector('#store')


def navigate(page, route, expected_heading):
    page.evaluate('(route)=>{location.hash=route}', route)
    expect(page.locator('#main h1')).to_have_text(expected_heading)


def save_modal(page):
    page.locator('#modal button[type=submit]').click()
    # A failed request leaves the dialog open with a Chinese explanation.
    try:
        expect(page.locator('#modal')).not_to_be_visible(timeout=10000)
    except AssertionError:
        error = page.locator('#modal .formerror')
        if error.count() and error.inner_text():
            raise AssertionError(error.inner_text())
        raise


def take_screenshot(page, output, filename):
    path = output / filename
    if page.locator('#toast').count():
        expect(page.locator('#toast')).not_to_have_class(re.compile('visible'), timeout=7000)
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def assert_fits_mobile(page):
    metrics = page.evaluate('''()=>({width:innerWidth,document:document.documentElement.scrollWidth,
        modal:document.querySelector('#modal')?.getBoundingClientRect().toJSON()})''')
    assert metrics['document'] <= metrics['width'] + 1, metrics
    if page.locator('#modal').is_visible():
        assert metrics['modal']['left'] >= 0 and metrics['modal']['right'] <= metrics['width'] + 1, metrics
    clipped = page.locator('.kpi .value-text').evaluate_all('(rows)=>rows.filter(r=>r.scrollWidth>r.clientWidth+1).length')
    assert not clipped, '窄屏 KPI 文字被裁切'


def checked_request(page, path, method='GET', data=None, store=1, status=200):
    result = request(page, path, method, data, store)
    assert result['status'] == status, {'path':path, 'result':result}
    return result['body']


def create_repair_source(page, store):
    """Create every prerequisite through its HTTP workflow, never arbitrary SQL state edits."""
    values = {'customer_name':'集团浏览器会员','customer_phone':'13900009999','plate':'验收A1001',
              'repair_type':'一般维修','problem':'合成验收维修，不是真实业务',
              'due_date':datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()}
    candidates=checked_request(page,'/api/customer-choice/matches?phone=13900009999',store=store)['items']
    exact=[c for c in candidates if c['name']==values['customer_name']]
    assert len(exact)<=1,'Synthetic fixture must identify one authorized customer explicitly'
    if exact:values['customer_id']=exact[0]['id']
    row = checked_request(page,'/api/flow/cases','POST',{'request_id':secrets.token_hex(16),'kind':'repair','values':values},store,201)
    uploaded = page.evaluate('''async ({id,store})=>{
        const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];
        const form=new FormData();form.append('category','evidence');
        form.append('file',new Blob(['独立测试：模拟客户授权、质检和收款凭据，不含真实资料'],{type:'text/plain'}),'集团模拟凭据.txt');
        const r=await fetch('/api/flow/cases/'+id+'/files',{method:'POST',headers:{'X-CSRF-Token':token,'X-Store-ID':String(store)},body:form});
        return {status:r.status,body:await r.json()};
    }''', {'id':row['id'],'store':store})
    assert uploaded['status'] == 200, uploaded
    evidence_id = uploaded['body']['id']
    for action, data in [
        ('quote', {'labor':'100','parts':'0','discount':'0','labor_cost':'10','payer':'客户','work':'合成检查项目'}),
        ('authorize', {'evidence_id':evidence_id}), ('start', {}),
        ('finish', {'result':'合成验收施工完成'}), ('quality', {'evidence_id':evidence_id})
    ]:
        row = checked_request(page,f'/api/flow/cases/{row["id"]}',store=store)
        row = checked_request(page,f'/api/flow/cases/{row["id"]}/actions/{action}','POST',
                              {'request_id':secrets.token_hex(16),'version':row['version'],'values':data},store)
    assert row['state'] == 'settling'
    account = checked_request(page,'/api/flow/master/accounts','POST',
                              {'values':{'name':f'集团验收账户{store}','account_type':'bank','active':True}},store,201)
    return {'case':row,'evidence_id':evidence_id,'account_id':account['id'],'store':store}


def group_browser_scenario(admin, employee, base, account_id, password, two, output, steps, screenshots):
    a, b = create_repair_source(admin,1), create_repair_source(admin,two)
    current=next(u for u in checked_request(admin,'/api/users')['items'] if u['id']==account_id)
    changed = checked_request(admin,f'/api/users/{account_id}','PUT',{
        'request_id':secrets.token_hex(16),'access_version':current['access_version'],
        'display_name':'页面验收财务','role':'sales','active':True,'can_group_summary':False,
        'store_roles':[{'store_id':1,'role':'finance'},{'store_id':two,'role':'finance'}]})
    assert changed['account_role'] == 'sales'
    assert request(employee,'/api/auth/me')['status'] == 401
    login_page(employee,base,'browser-employee',password)
    expect(employee.locator('.identity .role')).to_have_text('财务')

    navigate(employee,f'case/{a["case"]["id"]}',a['case']['title'])
    employee.locator(f'[data-route="group/{a["case"]["customer_id"]}/{a["case"]["id"]}"]').click()
    expect(employee.locator('#main h1')).to_have_text('集团会员')
    employee.locator('[data-act=group-link]').click()
    employee.locator('#modal [name=identity]').select_option('new')
    employee.locator('#modal [name=confirmed]').check()
    save_modal(employee)
    employee.locator('[data-act=group-issue]').click()
    save_modal(employee)
    employee.locator('[data-act=group-action][data-key=topup]').click()
    employee.locator('#modal [name=amount]').fill('100.00')
    employee.locator('#modal [name=account_id]').select_option(str(a['account_id']))
    employee.locator('#modal [name=reference]').fill('BROWSER-TOPUP-ONLY')
    employee.locator('#modal [name=evidence_id]').select_option(str(a['evidence_id']))
    save_modal(employee)
    expect(employee.locator('.kpi').filter(has=employee.locator('.label',has_text='本金余额（元）')).locator('.value')).to_have_text('100.00')
    wallet_a = checked_request(employee,f'/api/group/members?customer_id={a["case"]["customer_id"]}')
    member_id, identity_id = wallet_a['member']['id'], wallet_a['identity_id']
    assert_fits_mobile(employee)
    screenshots.append(take_screenshot(employee,output,'05_mobile_group_topup.png'))
    steps.append('财务员工从真实维修单进入，人工关联身份、开通集团会员并按合成凭据登记本金充值')

    employee.locator('#store').select_option(str(two))
    expect(employee.locator('#main h1')).to_have_text('我的工作')
    expect(employee.locator('.identity .role')).to_have_text('财务')
    assert request(employee,f'/api/group/members/{member_id}',store=two)['status'] == 404
    navigate(employee,f'case/{b["case"]["id"]}',b['case']['title'])
    employee.locator(f'[data-route="group/{b["case"]["customer_id"]}/{b["case"]["id"]}"]').click()
    expect(employee.locator('#main h1')).to_have_text('集团会员')
    employee.locator('[data-act=group-link]').click()
    employee.locator('#modal [name=identity]').select_option(str(identity_id))
    employee.locator('#modal [name=confirmed]').check()
    save_modal(employee)
    wallet_b = checked_request(employee,f'/api/group/members/{member_id}',store=two)
    assert wallet_b['member']['balance_cents'] == 10000 and wallet_b['entries'] == []
    employee.locator('[data-act=group-action][data-key=reserve]').click()
    employee.locator('#modal [name=amount]').fill('70.00')
    employee.locator('#modal [name=evidence_id]').select_option(str(b['evidence_id']))
    save_modal(employee)
    employee.locator('[data-act=group-action][data-key=capture]').click()
    employee.locator('#modal [name=evidence_id]').select_option(str(b['evidence_id']))
    save_modal(employee)
    expect(employee.locator('.kpi').filter(has=employee.locator('.label',has_text='本金余额（元）')).locator('.value')).to_have_text('30.00')
    wallet_b = checked_request(employee,f'/api/group/members/{member_id}',store=two)
    assert wallet_b['member']['balance_cents'] == 3000 and wallet_b['member']['reserved_cents'] == 0
    assert [entry['purpose'] for entry in wallet_b['entries']] == ['capture']
    assert 'BROWSER-TOPUP-ONLY' not in json.dumps(wallet_b)
    assert_fits_mobile(employee)
    screenshots.append(take_screenshot(employee,output,'06_mobile_group_cross_store_capture.png'))
    navigate(employee,'group-reconciliation','本店会员往来对账')
    reconciliation = checked_request(employee,'/api/group/reconciliation',store=two)
    assert reconciliation['clearing_sum_cents'] == 0
    screenshots.append(take_screenshot(employee,output,'07_mobile_group_reconciliation.png'))
    steps.append('乙店人工确认同一身份后使用甲店本金，70元占用与核销完成；只见乙店流水，内部配对往来为零差额')
    refund_browser_scenario(admin,employee,base,a,member_id,output,steps,screenshots)


def refund_browser_scenario(admin, employee, base, source, member_id, output, steps, screenshots):
    reviewer_password = secrets.token_urlsafe(24)
    checked_request(admin,'/api/users','POST',{'username':'browser-manager','display_name':'独立复核店长',
        'role':'manager','password':reviewer_password,'store_roles':[{'store_id':1,'role':'manager'}]},status=201)
    context = admin.context.browser.new_context(viewport={'width':1440,'height':1050},locale='zh-CN')
    reviewer = context.new_page()
    errors = []
    reviewer.on('pageerror',lambda error:errors.append(str(error)))
    route = f'group/{source["case"]["customer_id"]}/{source["case"]["id"]}'
    try:
        login_page(reviewer,base,'browser-manager',reviewer_password)
        changed_password = secrets.token_urlsafe(24)
        reviewer.locator('#modal [name=current_password]').fill(reviewer_password)
        reviewer.locator('#modal [name=new_password]').fill(changed_password)
        save_modal(reviewer)
        login_page(reviewer,base,'browser-manager',changed_password)
        employee.locator('#store').select_option('1')
        expect(employee.locator('#main h1')).to_have_text('我的工作')
        expect(employee.locator('.identity .role')).to_have_text('财务')
        navigate(employee,route,'集团会员')

        def apply(amount):
            employee.locator('[data-act=group-action][data-key=refund_request]').click()
            employee.locator('#modal [name=amount]').fill(amount)
            employee.locator('#modal [name=evidence_id]').select_option(str(source['evidence_id']))
            employee.locator('#modal [name=reason]').fill('合成验收客户申请原本金退款')
            save_modal(employee)
            assert employee.locator('[data-act=group-action][data-key=refund_approve]').count() == 0

        def approve():
            reviewer.goto(base+'/#'+route)
            reviewer.reload()
            expect(reviewer.locator('#main h1')).to_have_text('集团会员')
            reviewer.locator('[data-act=group-action][data-key=refund_approve]').click()
            reviewer.locator('#modal [name=reason]').fill('独立店长核对合成申请与原收款')
            save_modal(reviewer)
            employee.reload()
            expect(employee.locator('#main h1')).to_have_text('集团会员')

        apply('20.00')
        approve()
        wallet = checked_request(employee,f'/api/group/members/{member_id}')
        assert wallet['member']['reserved_cents'] == 2000 and wallet['member']['available_cents'] == 1000
        employee.locator('[data-act=group-action][data-key=refund_cancel]').click()
        employee.locator('#modal [name=reason]').fill('客户撤销本次合成退款申请')
        save_modal(employee)
        wallet = checked_request(employee,f'/api/group/members/{member_id}')
        assert wallet['member']['balance_cents'] == 3000 and wallet['member']['reserved_cents'] == 0
        assert wallet['refund_requests'][0]['status'] == 'cancelled'
        assert [entry['purpose'] for entry in wallet['entries']] == ['topup']
        screenshots.append(take_screenshot(employee,output,'08_mobile_refund_cancel_releases_hold.png'))
        steps.append('财务申请20元原款退款，独立店长批准占额；申请人撤销后释放全部占额，不新增现金流水')

        apply('10.00')
        approve()
        employee.locator('[data-act=group-action][data-key=refund]').click()
        employee.locator('#modal [name=account_id]').select_option(str(source['account_id']))
        employee.locator('#modal [name=reference]').fill('BROWSER-REFUND-ONLY')
        employee.locator('#modal [name=evidence_id]').select_option(str(source['evidence_id']))
        save_modal(employee)
        wallet = checked_request(employee,f'/api/group/members/{member_id}')
        assert wallet['member']['balance_cents'] == 2000 and wallet['member']['reserved_cents'] == 0
        assert wallet['refund_requests'][0]['status'] in {'executed','completed'}
        assert [entry['purpose'] for entry in wallet['entries']] == ['refund','topup']
        cash = checked_request(employee,'/api/records/cash')['items']
        assert len(cash) == 2
        assert sum(row['amount_cents'] * (1 if row['direction']=='in' else -1) for row in cash) == 9000
        assert_fits_mobile(employee)
        screenshots.append(take_screenshot(employee,output,'09_mobile_approved_actual_refund.png'))
        steps.append('独立店长批准后由财务登记10元实际原账户退款，本金余额20元、占额为零，退款追溯原充值')
        assert not errors, errors
    finally:
        context.close()


def exercise(browser, base, initial_password, output):
    steps, screenshots, errors = [], [], []
    admin_context = browser.new_context(viewport={'width':1440,'height':1050}, locale='zh-CN')
    employee_context = browser.new_context(viewport={'width':390,'height':844}, locale='zh-CN')
    for context in (admin_context, employee_context):
        context.on('page', lambda page: page.on('pageerror', lambda error: errors.append(str(error))))
    admin = admin_context.new_page()
    employee = employee_context.new_page()
    try:
        response = admin.goto(base)
        assert "script-src 'self'" in response.headers['content-security-policy']
        assert 'huakangos' in admin.title()
        login_page(admin, base, 'admin', initial_password)
        cookies = {c['name']:c for c in admin_context.cookies()}
        assert cookies['dealer_session']['httpOnly'] and cookies['dealer_session']['sameSite'] == 'Strict'
        assert not cookies['dealer_csrf']['httpOnly']
        assert 'dealer_session=' not in admin.evaluate('document.cookie')
        steps.append('真实 HTTP 登录；检查 CSP、HttpOnly 会话和 SameSite Cookie')

        navigate(admin, 'stores', '门店设置')
        admin.locator('[data-act=newstore]').click()
        admin.locator('#modal [name=name]').fill('浏览器验收乙店')
        admin.locator('#modal [name=code]').fill('UI-B')
        save_modal(admin)
        two = next(s['id'] for s in request(admin,'/api/stores')['body']['items'] if s['code'] == 'UI-B')
        steps.append('管理员通过页面建立第二家模拟门店')

        navigate(admin, 'users', '员工账号')
        admin.locator('[data-act=newuser]').click()
        employee_password = secrets.token_urlsafe(24)
        admin.locator('#modal [name=username]').fill('browser-employee')
        admin.locator('#modal [name=password]').fill(employee_password)
        admin.locator('#modal [name=display_name]').fill('页面验收员工')
        admin.locator('#modal [name=role]').select_option('sales')
        for sid, role in ((1,'sales'),(two,'service')):
            admin.locator(f'#modal [name=store_ids][value="{sid}"]').check()
            admin.locator(f'#modal [name=store_role_{sid}]').select_option(role)
        admin.set_viewport_size({'width':390,'height':844})
        assert_fits_mobile(admin)
        screenshots.append(take_screenshot(admin, output, '01_mobile_store_roles.png'))
        admin.locator('.store-role-list').scroll_into_view_if_needed()
        screenshots.append(take_screenshot(admin, output, '01b_mobile_store_role_mapping.png'))
        save_modal(admin)
        account = next(u for u in request(admin,'/api/users')['body']['items'] if u['username'] == 'browser-employee')
        assert [(x['store_id'],x['role']) for x in account['store_roles']] == [(1,'sales'),(two,'service')]
        steps.append('390px 页面创建同一员工甲店销售、乙店售后岗位，API 保存一致')
        admin.set_viewport_size({'width':1440,'height':1050})

        # New administrators have global access; empty role maps must not mismatch selected stores.
        admin.locator('[data-act=newuser]').click()
        admin.locator('#modal [name=username]').fill('browser-admin')
        admin.locator('#modal [name=password]').fill(secrets.token_urlsafe(24))
        admin.locator('#modal [name=display_name]').fill('备用验收管理员')
        admin.locator('#modal [name=role]').select_option('admin')
        admin.locator('#modal [name=store_ids][value="1"]').check()
        save_modal(admin)
        steps.append('管理员账号表单不会提交不匹配的本店岗位列表')

        login_page(employee, base, 'browser-employee', employee_password)
        expect(employee.locator('#modal [name=current_password]')).to_be_visible()
        next_password = secrets.token_urlsafe(24)
        employee.locator('#modal [name=current_password]').fill(employee_password)
        employee.locator('#modal [name=new_password]').fill(next_password)
        save_modal(employee)
        login_page(employee, base, 'browser-employee', next_password)
        expect(employee.locator('.identity .role')).to_have_text('销售')
        assert request(employee,'/api/auth/me')['body']['role'] == 'sales'
        assert employee.locator('#store option[value=all]').count() == 0
        steps.append('真实员工首次登录强制改密，重新登录显示甲店销售权限')

        navigate(employee, 'master/customers', '客户档案')
        employee.locator('[data-act=newmaster]').click()
        employee.locator('#modal [name=name]').fill('甲店独立验收客户')
        employee.locator('#modal [name=phone]').fill('13900001234')
        save_modal(employee)
        expect(employee.locator('#main')).to_contain_text('甲店独立验收客户')
        employee.locator('#store').select_option(str(two))
        expect(employee.locator('.identity .role')).to_have_text('售后 / 保险')
        navigate(employee, 'master/customers', '客户档案')
        expect(employee.locator('#main')).not_to_contain_text('甲店独立验收客户')
        assert request(employee,'/api/auth/me',store=two)['body']['role'] == 'service'
        employee.locator('[data-act=newmaster]').click()
        employee.locator('#modal [name=name]').fill('乙店独立验收客户')
        employee.locator('#modal [name=phone]').fill('13900005678')
        save_modal(employee)
        expect(employee.locator('#main')).to_contain_text('乙店独立验收客户')
        employee.reload()
        expect(employee.locator('#store')).to_have_value(str(two))
        expect(employee.locator('.identity .role')).to_have_text('售后 / 保险')
        expect(employee.locator('#main')).to_contain_text('乙店独立验收客户')
        expect(employee.locator('#main')).not_to_contain_text('甲店独立验收客户')
        navigate(employee, 'cases/repair', '维修工单')
        expect(employee.locator('[data-act=newcase]')).to_be_visible()
        screenshots.append(take_screenshot(employee, output, '02_mobile_service_role.png'))
        employee.locator('#store').select_option('1')
        expect(employee.locator('.identity .role')).to_have_text('销售')
        employee.evaluate("location.hash='cases/repair'")
        expect(employee.locator('#main')).to_contain_text('当前账号无法查看此业务')
        assert employee.locator('[data-act=newcase]').count() == 0
        navigate(employee, 'master/customers', '客户档案')
        expect(employee.locator('#main')).to_contain_text('甲店独立验收客户')
        expect(employee.locator('#main')).not_to_contain_text('乙店独立验收客户')
        assert_fits_mobile(employee)
        steps.append('手机切店与整页刷新保留获权门店并重新核验岗位；两个门店新客户不会串店显示')

        refused = request(employee,'/api/users')
        assert refused['status'] == 403 and '管理员' in refused['body']['detail']
        refused = request(employee,'/api/flow/master/customers','POST',{'values':{'name':'拒绝样本'}},csrf=False)
        assert refused['status'] == 403 and '校验' in refused['body']['detail']
        refused = request(employee,'/api/auth/me',store=99999)
        assert refused['status'] == 403 and '门店' in refused['body']['detail']
        employee.evaluate("location.hash='users'")
        expect(employee.locator('#main')).to_contain_text('仅系统管理员可以管理账号')
        screenshots.append(take_screenshot(employee, output, '03_mobile_chinese_refusal.png'))
        steps.append('实际浏览器请求拒绝员工账号管理、伪造门店和缺少 CSRF；页面显示中文错误')

        navigate(admin, 'analytics/overview', '数据可视化')
        admin.locator('#store').select_option('all')
        expect(admin.locator('.identity .role')).to_have_text('集团汇总（只读）')
        aggregate = request(admin,'/api/auth/me',store='all')['body']
        assert aggregate['aggregate_scope'] and aggregate['write_modules'] == [] and not aggregate['can_users']
        refused = request(admin,'/api/stores','POST',{'code':'NO','name':'不应建立'},store='all')
        assert refused['status'] == 409 and '只读' in refused['body']['detail']
        screenshots.append(take_screenshot(admin, output, '04_aggregate_readonly.png'))
        steps.append('管理员切至集团汇总后只读，真实网络写请求被后端拒绝')
        group_browser_scenario(admin,employee,base,account['id'],next_password,two,output,steps,screenshots)
        admin.locator('[data-act=logout]').click()
        expect(admin.locator('.loginform [name=username]')).to_be_visible()
        assert admin.locator('#modal input').count() == 0
        assert admin.locator('#modal').inner_html() == ''
        admin.locator('.loginform [name=username]').fill('browser-employee')
        admin.locator('.loginform [name=password]').fill(next_password)
        admin.locator('.loginform button[type=submit]').click()
        expect(admin.locator('#store')).to_be_visible()
        expect(admin.locator('.identity .role')).to_have_text('财务')
        assert admin.locator('#store').input_value() == '1'
        steps.append('集团汇总退出后同页登录员工，不继承上一个账号的门店或汇总范围')
        assert not errors, errors
        return {'mode':'real Chromium browser HTTP', 'passed':len(steps), 'steps':steps,
                'javascript_errors':errors,'screenshots':screenshots,
                'limitations':['本地 HTTP 验证不替代生产 HTTPS 和 Secure Cookie 验证','全部数据为新建合成资料，无真实客户资料']}
    except Exception:
        take_screenshot(admin, output, 'failure_admin.png')
        take_screenshot(employee, output, 'failure_employee.png')
        raise
    finally:
        employee_context.close()
        admin_context.close()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshots', type=Path)
    args = parser.parse_args()
    executable = chromium_path()
    if not executable:
        raise SystemExit('请安装 Chrome/Edge 或设置 CHROMIUM_PATH。')
    output = (args.screenshots or Path(tempfile.mkdtemp(prefix='huakangos-browser-evidence-'))).resolve()
    if output == ROOT or ROOT in output.parents:
        raise SystemExit('截图和验收输出必须存放在仓库目录之外。')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='huakangos-browser-db-') as work_path:
        work = Path(work_path)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        password = secrets.token_urlsafe(28)
        env = browser_environment(work, password)
        initializer=globals().get('initialize_database')
        initialized = initializer(env,work) if initializer else subprocess.run([sys.executable,'-m','app.cli','init'],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
        if initialized.returncode:
            raise RuntimeError('隔离测试库初始化失败：' + initialized.stderr)
        # Optional synthetic stock fixture, never a production write API. The
        # callback receives only this newly initialized temporary test database.
        prepare=globals().get('prepare_database')
        if prepare:prepare(env,work)
        flags = getattr(subprocess,'CREATE_NO_WINDOW',0)
        with (work/'server.log').open('w',encoding='utf-8') as log:
            server = subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],
                                      cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=flags)
            try:
                with httpx.Client(base_url=base,timeout=2,trust_env=False) as client:
                    for _ in range(120):
                        if server.poll() is not None:
                            raise RuntimeError('隔离测试服务启动失败。')
                        try:
                            if client.get('/api/health').status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(.1)
                    else:
                        raise RuntimeError('隔离测试服务未能就绪。')
                with sync_playwright() as p:
                    browser = p.chromium.launch(executable_path=executable,headless=True)
                    try:
                        result = exercise(browser,base,password,output)
                        (output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                        print(json.dumps(result,ensure_ascii=False,indent=2))
                    finally:
                        browser.close()
            finally:
                if os.name == 'nt' and server.poll() is None:
                    # Windows venv launchers may own a child interpreter; stop our whole tree.
                    subprocess.run(['taskkill','/PID',str(server.pid),'/T','/F'],capture_output=True,creationflags=flags)
                elif server.poll() is None:
                    server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
        if os.name=='nt':
            # The venv launcher can exit before the terminated child's handles
            # are released. Probe only this run's closed log, then let the
            # existing TemporaryDirectory context perform its normal cleanup.
            for attempt in range(50):
                try:
                    os.replace(work/'server.log',work/'server.log')
                    break
                except PermissionError:
                    time.sleep(.1)


if __name__ == '__main__':
    main()
