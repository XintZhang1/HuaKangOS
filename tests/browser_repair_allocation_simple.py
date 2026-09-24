"""Real Windows employee Chrome checks for repair allocations in a fresh synthetic DB."""
import secrets
from datetime import date

from playwright.sync_api import expect
import browser_huakangos as h


def exercise(browser, base, password, output):
    contexts, errors, shots, steps = [], [], [], []

    def page(width):
        context = browser.new_context(viewport={'width': width, 'height': 844}, locale='zh-CN')
        contexts.append(context)
        result = context.new_page()
        result.on('pageerror', lambda error: errors.append(str(error)))
        return result

    admin, manager = page(1440), page(390)
    key = lambda: secrets.token_hex(16)
    post = lambda p, path, data, status=200: h.checked_request(p, path, 'POST', data, status=status)
    get = lambda path: h.checked_request(admin, path)

    def proof(cid, title, category='evidence'):
        result = admin.evaluate('''async ({cid,title,category})=>{
          const data=new FormData();data.append('category',category);
          data.append('file',new Blob([title],{type:'text/plain'}),title+'.txt');
          const csrf=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];
          const r=await fetch('/api/flow/cases/'+cid+'/files',{method:'POST',headers:{'X-Store-ID':'1','X-CSRF-Token':csrf},body:data});
          return {status:r.status,body:await r.json()};}''', {'cid': cid, 'title': title, 'category': category})
        assert result['status'] == 200, result
        return result['body']['id']

    def command(cid, action, values):
        current = get('/api/repair-orders/'+str(cid))
        return post(admin, f'/api/repair-orders/{cid}/actions/{action}', {
            'request_id': key(), 'version': current['version'], 'values': values})

    def visit(cid):
        manager.goto(base+'/?allocation_trial='+key()+'#repair-orders/'+str(cid))
        expect(manager.locator('[data-act=repair-action][data-key=allocate]')).to_be_visible()

    def open_allocation():
        manager.locator('[data-act=repair-action][data-key=allocate]').click()
        expect(manager.locator('#modal h2')).to_have_text('确认费用承担')

    def fill(name, value):
        manager.locator('#modal [name='+name+']').fill(str(value))

    def select_live(name, text):
        choice = manager.locator('#modal .lookup').filter(has=manager.locator('select[name='+name+']'))
        choice.locator('[data-lookup-query]').fill(text)
        choice.get_by_role('option', name=text, exact=False).click()

    def inline_proof(title):
        manager.locator('#modal [data-act=inline-file-open]').click()
        manager.locator('#modal [data-inline-file]').set_input_files({
            'name': title+'.txt', 'mimeType': 'text/plain', 'buffer': title.encode('utf-8')})
        manager.locator('#modal [data-act=inline-file-upload]').click()
        expect(manager.locator('#modal [data-inline-file-status]')).to_contain_text('已选用')

    try:
        h.login_page(admin, base, 'admin', password)
        initial = secrets.token_urlsafe(24)
        employee = post(admin, '/api/users', {'username': 'allocation-manager', 'display_name': '合成维修主管',
            'role': 'manager', 'password': initial, 'store_roles': [{'store_id': 1, 'role': 'manager'}]}, 201)
        h.login_page(manager, base, 'allocation-manager', initial)
        fill('current_password', initial)
        changed = secrets.token_urlsafe(24)
        fill('new_password', changed)
        h.save_modal(manager)
        h.login_page(manager, base, 'allocation-manager', changed)
        customer = post(admin, '/api/flow/master/customers', {'values': {
            'name': '合成承担简化客户', 'phone': '13900008531', 'contact_allowed': True, 'note': ''}}, 201)
        work = post(admin, '/api/masters/work_items', {'request_id': key(), 'values': {
            'code': 'ALLOC-WORK', 'name': '合成检查作业', 'billing_unit': 'job', 'standard_fee_cents': 15001}}, 201)
        insurer = post(admin, '/api/masters/insurers', {'request_id': key(), 'values': {
            'code': 'ALLOC-INSURER', 'name': '合成承担保险公司'}}, 201)

        def ready(suffix):
            row = post(admin, '/api/repair-orders', {'request_id': key(), 'customer_id': customer['id'],
                'plate': '合成承担'+suffix, 'problem': '隔离检查作业，无配件实物变化', 'due_date': date.today().isoformat()}, 201)
            cid = row['id']
            row = command(cid, 'quote', {'reason': '隔离试用实际检查项目', 'discount_cents': 0, 'lines': [
                {'kind': 'work', 'source_id': work['id'], 'quantity_milli': 1000, 'unit_price_cents': 15001}]})
            qid = row['data']['quote_id']
            command(cid, 'price_approve', {'quote_id': qid, 'minimum_total_cents': 0,
                'allow_below_minimum': False, 'reason': '核对合成作业原报价'})
            command(cid, 'authorize', {'quote_id': qid, 'evidence_id': proof(cid, suffix+'本版授权', 'authorization')})
            command(cid, 'start', {'result': '隔离作业实际开工'})
            command(cid, 'finish', {'result': '隔离作业施工完成'})
            command(cid, 'quality', {'passed': True, 'result': '隔离作业质检合格',
                'evidence_id': proof(cid, suffix+'本版质检', 'inspection')})
            task = next(t for t in get('/api/flow/cases/'+str(cid))['tasks'] if t['key'] == 'repair_allocate')
            if task['assignee_id'] != employee['id']:
                post(admin, '/api/flow/tasks/'+str(task['id'])+'/assign', {
                    'version': task['version'], 'assignee_id': employee['id'], 'reason': '交由本次试用主管核对'})
            return cid

        cid = ready('A001')
        visit(cid)
        directory_requests = []
        manager.on('request', lambda request: directory_requests.append(request.url) if (
            '/api/masters/insurers?' in request.url or '/api/flow/master/references?' in request.url) else None)
        open_allocation()
        assert not directory_requests, directory_requests
        expect(manager.locator('#modal [name=amount_customer]')).to_have_value('')
        expect(manager.locator('#modal [data-repair-payer=insurer]')).not_to_be_visible()
        manager.locator('#modal [data-repair-customer-all]').click()
        expect(manager.locator('#modal [name=amount_customer]')).to_have_value('150.01')
        expect(manager.locator('#modal [data-repair-allocation-total]')).to_contain_text('已分配完整')
        fill('labor_cost', '0')
        inline_proof('A001主管承担确认')
        expect(manager.locator('#modal [name=amount_customer]')).to_have_value('150.01')
        h.assert_fits_mobile(manager)
        shots.append(h.take_screenshot(manager, output, '01_customer_full_inline_proof.png'))
        h.save_modal(manager)
        allocations = get('/api/repair-orders/'+str(cid))['allocations']
        assert [(a['payer_type'], a['amount_cents']) for a in allocations] == [('customer', 15001)]
        steps.append('主管390px：空白客户金额经明确点击带入150.01元；未请求保险或厂家目录；表内上传保留金额并成功确认')

        cid = ready('A002')
        current = get('/api/repair-orders/'+str(cid))
        claim = post(admin, '/api/claims', {'request_id': key(), 'source_case_id': cid,
            'source_version': current['version'], 'party_type': 'insurer', 'payment_route': 'repair_receivable',
            'payer_id': insurer['id'], 'payer_name': '', 'reason': '合成保险承担核赔'}, 201)
        claim_id = claim['id']
        visit(cid)
        open_allocation()
        expect(manager.locator('#modal [data-repair-customer-all]')).to_be_disabled()
        expect(manager.locator('#modal .notice')).to_contain_text('待核损核价')
        shots.append(h.take_screenshot(manager, output, '02_pending_claim_blocks_customer_full.png'))
        manager.locator('#modal [data-act=close]').first.click()

        def claim_command(actor, action, values):
            claim = get('/api/claims/'+str(claim_id))
            return post(actor, f'/api/claims/{claim_id}/actions/{action}', {
                'request_id': key(), 'version': claim['version'], 'source_version': claim['source_version'], 'values': values})

        line = claim['source_lines'][0]
        claim_command(admin, 'assess', {'reason': '原检查作业核价五十元', 'lines': [
            {'line_id': line['id'], 'quantity_milli': line['quantity_milli'], 'amount_cents': 5000}]})
        claim_command(manager, 'approve', {'reason': '另一主管独立核对原核价',
            'evidence_id': proof(claim_id, 'A002独立核价确认', 'authorization')})
        transmitted = claim_command(admin, 'transmit', {'submitted_on': date.today().isoformat(),
            'external_reference': 'SYNTHETIC-ALLOC-INS', 'evidence_id': proof(claim_id, 'A002外部提交', 'authorization')})
        assessment = transmitted['assessments'][-1]
        claim_command(admin, 'result', {'transmission_id': transmitted['transmissions'][-1]['id'],
            'outcome': 'approved', 'result_on': date.today().isoformat(), 'result': '保险通知核准五十元',
            'lines': [{'line_id': assessment['lines'][0]['line_id'], 'quantity_milli': 1000, 'amount_cents': 5000}],
            'evidence_id': proof(claim_id, 'A002外部核准', 'authorization')})
        visit(cid)
        open_allocation()
        expect(manager.locator('#modal .notice')).to_contain_text('核赔金额 50.00 元')
        expect(manager.locator('#modal [data-repair-customer-all]')).to_be_disabled()
        fill('amount_customer', '150.01')
        fill('labor_cost', '10.00')
        inline_proof('A002各方承担凭据')
        manager.locator('#modal button[type=submit]').click()
        expect(manager.locator('#modal .formerror')).to_contain_text('核赔')
        assert not get('/api/repair-orders/'+str(cid))['settled']
        steps.append('主管390px：未核赔和已核赔工单均不默认客户全额；手填全额试图绕过时原后端拒绝，未冻结错误分配')

        fill('amount_customer', '100.01')
        manager.locator('#modal [data-repair-add-payer=insurer]').click()
        select_live('payer_insurer', '合成承担保险公司')
        fill('amount_insurer', '50.00')
        manager.locator('#modal [data-repair-add-payer=manufacturer]').click()
        fill('amount_manufacturer', '0.00')
        fill('due_manufacturer', '')
        manager.locator('#modal [data-repair-add-payer=internal]').click()
        fill('amount_internal', '0')
        fill('due_internal', '')
        expect(manager.locator('#modal [data-repair-allocation-total]')).to_contain_text('已分配完整')
        fill('amount_customer', '100.02')
        expect(manager.locator('#modal [data-repair-allocation-total]')).to_contain_text('超出 0.01 元')
        manager.locator('#modal button[type=submit]').click()
        expect(manager.locator('#modal .formerror')).to_contain_text('已超出 0.01 元')
        fill('amount_customer', '100.01')
        h.assert_fits_mobile(manager)
        shots.append(h.take_screenshot(manager, output, '03_insurer_split_zero_other_parties.png'))
        h.save_modal(manager)
        result = get('/api/repair-orders/'+str(cid))
        assert [(a['payer_type'], a['amount_cents']) for a in result['allocations']] == [('customer', 10001), ('insurer', 5000)]
        bound_claim = get('/api/claims/'+str(claim_id))
        assert next(a for a in bound_claim['source_allocations'] if a['payer_type'] == 'insurer')['insurer_id'] == insurer['id']
        assert bound_claim['phase'] == 'bound'
        assert all(not a['payments'] for a in result['allocations'])
        steps.append('主管390px：按需选择保险公司，客户100.01元+保险50元；其他方填0且空到期日可提交；超分0.01元先拦截；核赔绑定且未登记任何现金')
        assert not errors, errors
        return {'status': 'passed', 'mode': 'real-Windows-Chrome-HTTP', 'synthetic_only': True,
            'viewport': '390x844', 'passed': len(steps), 'steps': steps, 'screenshots': shots,
            'javascript_errors': errors, 'limits': [
                '报价、授权、施工、质检及核赔前置资料使用真实API合成；承担分配和上传使用真实主管页面',
                '没有改动用户数据库、预览进程或调用外部模型',
                '本脚本不验证实际收款、HTTPS、实体手机、库位领退料或公司业务验收；失效上下文由Node专项覆盖']}
    except Exception:
        h.take_screenshot(manager, output, 'failure_manager.png')
        raise
    finally:
        for context in contexts:
            context.close()


if __name__ == '__main__':
    h.exercise = exercise
    h.main()
