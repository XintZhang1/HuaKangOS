"""Actual Chrome, five employee roles, versioned repair and post-release payer cash."""
import secrets
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request,request,login_page,navigate,save_modal,take_screenshot,assert_fits_mobile


def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screenshots=[]
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(context)
        p=context.new_page();p.on('pageerror',lambda error:errors.append(str(error)));return p
    admin=page(1440)
    try:
        login_page(admin,base,'admin',password)
        def typed(kind,values):return checked_request(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':values},status=201)
        def master(kind,values):return checked_request(admin,'/api/flow/master/'+kind,'POST',{'values':values},status=201)
        customer=master('customers',{'name':'合成维修客户','phone':'13900000111','contact_allowed':True,'note':''})
        item=master('items',{'sku':'REPAIR-PART','name':'合成维修配件','unit':'件','reorder':'0','active':True})
        work=typed('work_items',{'code':'REPAIR-JOB','name':'检查与维修项目','billing_unit':'job','standard_fee_cents':10000})
        insurer=typed('insurers',{'code':'REPAIR-INS','name':'合成保险公司'})
        manufacturer=master('references',{'category':'厂家','name':'合成维修厂家','detail':'合成索赔往来','active':True})
        account=master('accounts',{'name':'合成维修结算账户','account_type':'bank','active':True})
        supplier=typed('suppliers',{'code':'REPAIR-SUPPLIER','name':'合成配件供应商'})
        purchase=checked_request(admin,'/api/procurement/orders','POST',{'request_id':secrets.token_hex(16),'supplier_id':supplier['id'],
            'reason':'为本次独立维修验收准备库存','lines':[{'item_id':item['id'],'quantity_milli':3000,'unit_cost_cents':123}]},status=201)
        def upload_fetch(case_id,label):
            result=admin.evaluate('''async ({id,label})=>{const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];const f=new FormData();f.append('category','evidence');f.append('file',new Blob([label],{type:'text/plain'}),label+'.txt');const r=await fetch('/api/flow/cases/'+id+'/files',{method:'POST',headers:{'X-CSRF-Token':token,'X-Store-ID':'1'},body:f});return{status:r.status,body:await r.json()};}''',{'id':case_id,'label':label})
            assert result['status']==200,result;return result['body']['id']
        fid=upload_fetch(purchase['id'],'合成采购到货证据')
        for key,values in [('approve',{}),('receive',{'lines':[{'line_id':purchase['lines'][0]['id'],'quantity_milli':3000}],'evidence_id':fid})]:
            purchase=checked_request(admin,f"/api/procurement/orders/{purchase['id']}/actions/{key}",'POST',{'request_id':secrets.token_hex(16),'version':purchase['version'],'values':values})
        employees={}
        for role,label in [('service','服务顾问'),('technician','技师'),('inventory','库管'),('manager','店长'),('finance','财务')]:
            secret=secrets.token_urlsafe(24)
            checked_request(admin,'/api/users','POST',{'username':'repair-'+role,'display_name':'维修验收'+label,'role':role,
                'password':secret,'store_roles':[{'store_id':1,'role':role}]},status=201)
            p=page();login_page(p,base,'repair-'+role,secret)
            p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24)
            p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'repair-'+role,changed);employees[role]=p
        service,technician,inventory,manager,finance=(employees[k] for k in ('service','technician','inventory','manager','finance'))
        navigate(service,'repair-orders','维修明细工单');service.locator('[data-act=repair-new]').click()
        service.locator('#modal [name=customer_id]').select_option(str(customer['id']))
        service.locator('#modal [name=plate]').fill('合成修A001');service.locator('#modal [name=problem]').fill('合成检查、维修及追加配件验收');save_modal(service)
        expect(service.locator('#main h1')).to_have_text('合成维修客户 · 维修明细')
        case_id=checked_request(admin,'/api/repair-orders')['items'][0]['id'];route='repair-orders/'+str(case_id)
        def current():return checked_request(admin,'/api/repair-orders/'+str(case_id))
        def visit(p):p.goto(base+'/?visit='+secrets.token_hex(5)+'#'+route);expect(p.locator('#main h1')).to_have_text('合成维修客户 · 维修明细')
        def action(p,key):p.locator('[data-act=repair-action][data-key='+key+']').click();expect(p.locator('#modal')).to_be_visible()
        def upload(p,label,category='evidence'):
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category)
            p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('合成证据：'+label).encode()});save_modal(p)
            expect(p.locator('#main')).to_contain_text(label+'.txt')
            return next(f['id'] for f in checked_request(admin,'/api/flow/cases/'+str(case_id))['files'] if f['name']==label+'.txt')
        def evidence_select(p,file_id):p.locator('#modal [name=evidence_id]').select_option(str(file_id))
        def price():
            visit(manager);action(manager,'price_approve');manager.locator('#modal [name=reason]').fill('主管明确核对当前版本及最低可接受金额');save_modal(manager)
        def authorize(label):
            visit(service);fid=upload(service,label,'authorization');action(service,'authorize');evidence_select(service,fid);save_modal(service);return fid
        action(service,'quote');line=service.locator('[data-repair-line]').first
        line.locator('[name=source]').select_option('work:'+str(work['id']));line.locator('[name=quantity]').fill('1.000');line.locator('[name=price]').fill('100.00')
        service.locator('[data-act=repair-add-line]').click();line=service.locator('[data-repair-line]').nth(1)
        line.locator('[name=source]').select_option('part:'+str(item['id']));line.locator('[name=quantity]').fill('1.000');line.locator('[name=price]').fill('5.00')
        service.locator('#modal [name=reason]').fill('诊断后确认一项作业与一件配件');assert_fits_mobile(service);save_modal(service)
        price();authorize('第一版客户授权')
        visit(technician);assert 'amount_cents' not in request(technician,'/api/repair-orders/'+str(case_id))['body']
        action(technician,'start');technician.locator('#modal [name=result]').fill('技师已核对客户当前授权并开工');save_modal(technician)
        visit(inventory);stock_file=upload(inventory,'实际发料交接')
        def issue(qty,refuse=False):
            visit(inventory);action(inventory,'issue');inventory.locator('#modal [name=line_label]').select_option(index=1)
            inventory.locator('#modal [name=quantity]').fill('9.000' if refuse else qty);evidence_select(inventory,stock_file)
            if refuse:
                inventory.locator('#modal button[type=submit]').click();expect(inventory.locator('#modal .formerror')).to_contain_text('超过当前客户授权')
                screenshots.append(take_screenshot(inventory,output,'00_mobile_unauthorized_quantity_refused.png'))
                inventory.locator('#modal [name=quantity]').fill(qty)
            save_modal(inventory)
        issue('1.000',True)
        steps.append('服务顾问报价、店长价格审批、客户当前版本授权后技师开工；库管超授权量被中文拒绝')
        visit(service);action(service,'quote');service.locator('[data-repair-line]').nth(1).locator('[name=quantity]').fill('2.000')
        service.locator('#modal [name=reason]').fill('施工中确认需追加一件配件，客户另行授权');save_modal(service)
        visit(inventory);assert not inventory.locator('[data-key=issue]').count();assert len(current()['stock'])==1
        price();authorize('第二版增项客户授权');issue('1.000')
        visit(service);assert_fits_mobile(service);screenshots.append(take_screenshot(service,output,'01_mobile_authorized_amendment.png'))
        steps.append('追加一件配件形成第二版报价，原版本保留；重新审批及客户授权前不能发新增配件')
        visit(inventory);action(inventory,'return_material');inventory.locator('#modal [name=original_id]').select_option(str(current()['stock'][0]['id']))
        inventory.locator('#modal [name=quantity]').fill('0.500');evidence_select(inventory,stock_file);save_modal(inventory);issue('0.500')
        visit(technician);action(technician,'finish');technician.locator('#modal [name=result]').fill('施工完成，领退料与实际使用一致');save_modal(technician)
        visit(service);quality_file=upload(service,'实际维修质检','inspection');action(service,'quality')
        service.locator('#modal [name=result]').fill('发现需要复核的缺陷');service.locator('#modal [name=outcome]').select_option('不合格');evidence_select(service,quality_file);save_modal(service)
        assert current()['state']=='working'
        visit(technician);action(technician,'finish');technician.locator('#modal [name=result]').fill('已完成缺陷处理并重新提交');save_modal(technician)
        visit(service);action(service,'quality');service.locator('#modal [name=result]').fill('复检与安全交接检查通过');service.locator('#modal [name=outcome]').select_option('合格');evidence_select(service,quality_file);save_modal(service)
        steps.append('库管原领料部分退回及重新发料；独立服务岗位质检不合格阻断，技师处理后复检通过')
        visit(manager);allocate_file=upload(manager,'各方承担确认');action(manager,'allocate')
        for key,value in [('customer','10.00'),('insurer','50.00'),('manufacturer','30.00'),('internal','20.00')]:manager.locator('#modal [name=amount_'+key+']').fill(value)
        manager.locator('#modal [name=payer_insurer]').select_option(str(insurer['id']));manager.locator('#modal [name=payer_manufacturer]').select_option(str(manufacturer['id']))
        manager.locator('#modal [name=internal_name]').fill('集团内部承担');manager.locator('#modal [name=labor_cost]').fill('2.00');manager.locator('#modal [name=evidence]').select_option(str(allocate_file));save_modal(manager)
        visit(finance);cash_file=upload(finance,'实际各方到账凭据','receipt')
        def pay(payer):
            visit(finance);allocation=next(a for a in current()['allocations'] if a['payer_type']==payer)
            finance.locator('[data-key=receive][data-id="'+str(allocation['id'])+'"]').click()
            finance.locator('#modal [name=account_id]').select_option(str(account['id']));finance.locator('#modal [name=reference]').fill('BROWSER-REPAIR-'+payer)
            evidence_select(finance,cash_file);save_modal(finance)
        pay('customer');visit(service);release_file=upload(service,'客户实际接车');action(service,'release');evidence_select(service,release_file);save_modal(service)
        assert current()['state']=='credit_open' and current()['receivable_cents']==8000
        assert_fits_mobile(service);screenshots.append(take_screenshot(service,output,'02_mobile_released_pending_insurer.png'))
        steps.append('主管冻结客户、保险、厂家、内部四方承担；客户10元结清后服务顾问确认接车，保险厂家80元继续挂应收')
        pay('insurer');pay('manufacturer');final=current()
        assert final['state']=='completed' and final['receivable_cents']==0 and final['revenue_cents']==9000
        assert sum(p['amount_cents'] for a in final['allocations'] for p in a['payments'])==9000
        assert_fits_mobile(finance);screenshots.append(take_screenshot(finance,output,'03_mobile_all_payers_reconciled.png'))
        finance.locator('.panel').filter(has=finance.get_by_role('heading',name='各承担方与实际到账',exact=True)).screenshot(path=str(output/'04_mobile_payer_panel.png'))
        screenshots.append(str(output/'04_mobile_payer_panel.png'))
        steps.append('财务在交车后登记保险及厂家到账，实际收款90元与外部承担一致，内部20元没有现金')
        assert not errors,errors
        return {'mode':'real_http_chrome','file_scan_mode':'structure_only','viewport':'390x844','checks_passed':len(steps),
            'steps':steps,'javascript_errors':errors,'screenshots':screenshots,'authorized_cents':11000,'cash_received_cents':9000,'internal_cents':2000}
    finally:
        for context in contexts:context.close()


if __name__=='__main__':
    harness.exercise=exercise;harness.main()
