"""Actual warehouse employee forms: purchase receipt, repair issue and original return."""
import secrets
from datetime import date
from playwright.sync_api import expect
import browser_huakangos as h


def exercise(browser, base, password, output):
    contexts, errors, screenshots, steps = [], [], [], []
    def page(width):
        context = browser.new_context(viewport={'width': width, 'height': 844}, locale='zh-CN')
        contexts.append(context)
        value = context.new_page()
        value.on('pageerror', lambda error: errors.append(str(error)))
        return value
    admin, worker = page(1440), page(390)
    key = lambda: secrets.token_hex(16)
    post = lambda p, path, data, status=200: h.checked_request(p, path, 'POST', data, status=status)
    get = lambda path: h.checked_request(admin, path)
    master = lambda kind, data: post(admin, '/api/flow/master/'+kind, {'values': data}, 201)
    typed = lambda kind, data: post(admin, '/api/masters/'+kind, {'request_id': key(), 'values': data}, 201)
    def proof(cid, title, category='evidence'):
        result = admin.evaluate('''async ({cid,title,category})=>{const data=new FormData();data.append('category',category);
          data.append('file',new Blob([title],{type:'text/plain'}),title+'.txt');
          const csrf=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];
          const r=await fetch('/api/flow/cases/'+cid+'/files',{method:'POST',headers:{'X-Store-ID':'1','X-CSRF-Token':csrf},body:data});
          return {status:r.status,body:await r.json()};}''', {'cid': cid, 'title': title, 'category': category})
        assert result['status'] == 200, result
        return result['body']['id']
    def choose(name, text):
        choice = worker.locator('#modal .lookup').filter(has=worker.locator('select[name='+name+']'))
        choice.locator('[data-lookup-query]').fill(text)
        choice.get_by_role('option', name=text, exact=False).click()
    def fill(name, value): worker.locator('#modal [name='+name+']').fill(str(value))
    def visit(route):
        worker.goto(base+'/?warehouse_trial='+key()+'#'+route)
        expect(worker.locator('#main h1')).to_be_visible()
    def open_prep():
        worker.locator('#modal [data-prep-open]').click()
        expect(worker.locator('#modal [data-prep-body]')).to_be_visible()
    def save_prep():
        worker.locator('#modal [data-prep-save]').click()
        expect(worker.locator('#modal [data-prep-status]')).to_contain_text('库位已保存')
    try:
        h.login_page(admin, base, 'admin', password)
        initial = secrets.token_urlsafe(24)
        employee = post(admin, '/api/users', {'username': 'prep-inventory', 'display_name': '合成库位仓管',
            'role': 'inventory', 'password': initial, 'store_roles': [{'store_id': 1, 'role': 'inventory'}]}, 201)
        h.login_page(worker, base, 'prep-inventory', initial)
        fill('current_password', initial)
        changed = secrets.token_urlsafe(24)
        fill('new_password', changed)
        h.save_modal(worker)
        h.login_page(worker, base, 'prep-inventory', changed)
        item = master('items', {'sku': 'PREP-PART', 'name': '合成精确领退配件', 'unit': '件', 'reorder': '0', 'active': True})
        wh = typed('warehouses', {'code': 'PREP-WH', 'name': '合成配件仓', 'warehouse_type': 'materials'})
        loc = typed('locations', {'code': 'PREP-A', 'name': '甲库位', 'warehouse_id': wh['id']})
        activation = post(admin, '/api/warehouse/cases', {'request_id': key(), 'operation': 'activate',
            'item_id': item['id'], 'quantity_milli': 0, 'source_location_id': None, 'destination_location_id': None,
            'original_move_id': None, 'reason': '从零启用合成配件库位', 'recipient': '合成仓管',
            'due_date': date.today().isoformat(), 'locations': [{'location_id': loc['id'], 'quantity_milli': 0}]}, 201)
        post(admin, f"/api/warehouse/cases/{activation['id']}/commands/approve", {'request_id': key(),
            'version': activation['version'], 'values': {'evidence_id': proof(activation['id'], '合成空库存启用确认')}})
        supplier = typed('suppliers', {'code': 'PREP-SUP', 'name': '合成库位供货商', 'payment_terms_days': 30})
        purchase = post(admin, '/api/procurement/orders', {'request_id': key(), 'supplier_id': supplier['id'],
            'reason': '合成原表库位分配采购', 'lines': [{'item_id': item['id'], 'quantity_milli': 5000, 'unit_cost_cents': 100}]}, 201)
        pid = purchase['id']
        purchase = post(admin, f'/api/procurement/orders/{pid}/actions/approve', {'request_id': key(),
            'version': purchase['version'], 'values': {}})
        proof(pid, '采购实到合成凭据')
        stock = lambda: get(f"/api/warehouse/items/{item['id']}/stock")
        receipts = lambda: get('/api/procurement/orders/'+str(pid))['receipts']
        assert stock()['quantity_milli'] == 0
        visit('procurement/'+str(pid))
        worker.locator('[data-act=procurement-action][data-key=receive]').click()
        quantity_name = 'quantity_'+str(purchase['lines'][0]['id'])
        fill(quantity_name, '1.251')
        choose('evidence', '采购实到合成凭据')
        original_evidence = worker.locator('#modal [name=evidence]').input_value()
        open_prep()
        expect(worker.locator('#modal [data-prep-quantity]')).to_have_value('1.251')
        expect(worker.locator('#modal [data-prep-item]')).to_contain_text('合成精确领退配件')
        save_prep()
        assert stock()['quantity_milli'] == 0 and len(receipts()) == 0
        fill(quantity_name, '1.501')
        expect(worker.locator('#modal [data-prep-status]')).to_contain_text('数量已变化')
        worker.locator('#modal button[type=submit]').click()
        expect(worker.locator('#modal .formerror')).to_contain_text('先分配并保存')
        assert stock()['quantity_milli'] == 0
        open_prep()
        expect(worker.locator('#modal [data-prep-quantity]')).to_have_value('1.501')
        worker.locator('#modal [data-prep-add]').click()
        expect(worker.locator('#modal [data-prep-location]')).to_have_count(2)
        save_prep()
        expect(worker.locator('#modal [name=evidence]')).to_have_value(original_evidence)
        invalid = worker.locator('#modal form').evaluate('form=>Array.from(form.elements).filter(el=>el.willValidate&&!el.validity.valid).map(el=>({name:el.name,type:el.type,required:el.required}))')
        assert not invalid, '保存后未使用的空库位行阻断原表提交：'+str(invalid)
        h.assert_fits_mobile(worker)
        screenshots.append(h.take_screenshot(worker, output, '01_purchase_saved_quantity_changed.png'))
        physical_requests = []
        worker.on('request', lambda request: physical_requests.append(request.post_data_json) if (
            request.method == 'POST' and request.url.endswith(f'/api/procurement/orders/{pid}/actions/receive')) else None)
        h.save_modal(worker)
        assert stock()['quantity_milli'] == 1501 and len(receipts()) == 1
        assert len(physical_requests) == 1
        post(worker, f'/api/procurement/orders/{pid}/actions/receive', physical_requests[0])
        assert stock()['quantity_milli'] == 1501 and len(receipts()) == 1
        steps.append('390px仓管：采购原表按1.251准备，改1.501后旧计划失效；空额外库位不阻断，凭据保留；实际收货及相同请求重放只入库1501千分位一次')

        visit('procurement/'+str(pid))
        worker.locator('[data-act=procurement-action][data-key=receive]').click()
        fill(quantity_name, '0.500')
        choose('evidence', '采购实到合成凭据')
        open_prep()
        save_prep()
        current = get('/api/procurement/orders/'+str(pid))
        post(admin, '/api/warehouse/allocations/'+str(pid), {'request_id': key(), 'version': current['version'],
            'values': {'item_id': item['id'], 'quantity_milli': 500, 'purpose': 'procurement_receipt',
                'locations': [{'location_id': loc['id'], 'quantity_milli': 500}]}})
        worker.locator('#modal button[type=submit]').click()
        expect(worker.locator('#modal .formerror')).not_to_be_empty()
        assert stock()['quantity_milli'] == 1501 and len(receipts()) == 1
        screenshots.append(h.take_screenshot(worker, output, '02_stale_source_no_second_receipt.png'))
        worker.locator('#modal [data-act=close]').first.click()
        steps.append('另一账号更新原单库位版本后，仓管旧表收货被拒绝，库存与到货批次均未增加')

        customer = master('customers', {'name': '合成库位维修客户', 'phone': '13900008532', 'contact_allowed': True, 'note': ''})
        repair = post(admin, '/api/repair-orders', {'request_id': key(), 'customer_id': customer['id'],
            'plate': '合成库A001', 'problem': '合成原领料及未用退回', 'due_date': date.today().isoformat()}, 201)
        rid = repair['id']
        def repair_command(action, values):
            current = get('/api/repair-orders/'+str(rid))
            return post(admin, f'/api/repair-orders/{rid}/actions/{action}', {'request_id': key(), 'version': current['version'], 'values': values})
        repair = repair_command('quote', {'reason': '按实物配件诊断', 'discount_cents': 0, 'lines': [
            {'kind': 'part', 'source_id': item['id'], 'quantity_milli': 1000, 'unit_price_cents': 200}]})
        quote_id = repair['data']['quote_id']
        repair_command('price_approve', {'quote_id': quote_id, 'minimum_total_cents': 0, 'allow_below_minimum': False, 'reason': '核对配件报价'})
        repair_command('authorize', {'quote_id': quote_id, 'evidence_id': proof(rid, '维修本版授权', 'authorization')})
        repair_command('start', {'result': '按实际客户授权开工'})
        task = next(t for t in get('/api/flow/cases/'+str(rid))['tasks'] if t['key'] == 'repair_issue')
        if task['assignee_id'] != employee['id']:
            post(admin, '/api/flow/tasks/'+str(task['id'])+'/assign', {'version': task['version'],
                'assignee_id': employee['id'], 'reason': '由本次合成仓管实际发料'})
        proof(rid, '维修原领料凭据')
        visit('repair-orders/'+str(rid))
        worker.locator('[data-act=repair-action][data-key=issue]').click()
        choose('line_label', '合成精确领退配件')
        fill('quantity', '0.751')
        choose('evidence_id', '维修原领料凭据')
        open_prep()
        expect(worker.locator('#modal [data-prep-quantity]')).to_have_value('0.751')
        save_prep()
        assert stock()['quantity_milli'] == 1501
        h.assert_fits_mobile(worker)
        screenshots.append(h.take_screenshot(worker, output, '03_repair_issue_inline_preparation.png'))
        h.save_modal(worker)
        assert stock()['quantity_milli'] == 750
        issued = get('/api/repair-orders/'+str(rid))['stock'][0]
        assert issued['quantity_milli'] == 751
        steps.append('390px仓管：原维修授权配件0.751在原领料表准备库位，保存未出库，最终发料仅扣751千分位')

        second = typed('locations', {'code': 'PREP-B', 'name': '乙库位', 'warehouse_id': wh['id']})
        proof(rid, '维修未用原料退回凭据')
        visit('repair-orders/'+str(rid))
        worker.locator('[data-act=repair-action][data-key=return_material]').click()
        choose('original_id', '合成精确领退配件')
        fill('quantity', '0.251')
        choose('evidence_id', '维修未用原料退回凭据')
        open_prep()
        bin_choice = worker.locator('#modal [data-prep-location] .lookup')
        bin_choice.locator('[data-lookup-query]').fill('乙库位')
        bin_choice.get_by_role('option', name='合成配件仓 · 乙库位', exact=True).click()
        worker.locator('#modal [data-prep-quantity]').fill('0.251')
        save_prep()
        assert stock()['quantity_milli'] == 750
        h.assert_fits_mobile(worker)
        screenshots.append(h.take_screenshot(worker, output, '04_repair_original_return_other_bin.png'))
        h.save_modal(worker)
        final = stock()
        assert final['quantity_milli'] == 1001
        balances = {b['location_id']: b['quantity_milli'] for b in final['balances']}
        assert balances[loc['id']] == 750 and balances[second['id']] == 251, balances
        final_repair = get('/api/repair-orders/'+str(rid))
        returns = [s for s in final_repair['stock'] if s['original_id']]
        assert len(returns) == 1 and returns[0]['original_id'] == issued['id'] and returns[0]['quantity_milli'] == -251
        assert sum(b['quantity_milli'] for b in final['balances']) == final['quantity_milli']
        assert sum(b['value_cents'] for b in final['balances']) == final['value_cents']
        steps.append('390px仓管：选择原领料批次，0.251未用料退到另一明确库位；保存未入库，最终退回原批次一次，库位数量与价值合计一致')
        assert not errors, errors
        return {'status': 'passed', 'mode': 'real-Windows-Chrome-HTTP', 'synthetic_only': True,
            'viewport': '390x844', 'passed': len(steps), 'steps': steps, 'screenshots': screenshots,
            'javascript_errors': errors, 'limits': ['全部初始主档、启用、采购批准及维修授权施工由真实API合成；收货、领料、退料由独立仓管页面办理',
                '同请求重放通过该员工真实HTTP验证；没有修改用户数据或预览服务', '未验证生产HTTPS、实体手机和公司业务验收；网络不确定与部分保存失败由Node专项覆盖']}
    except Exception:
        h.take_screenshot(worker, output, 'failure_worker.png')
        raise
    finally:
        for context in contexts:
            context.close()


if __name__ == '__main__':
    h.exercise = exercise
    h.main()
