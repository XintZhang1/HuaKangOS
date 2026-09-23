"""Actual employee Chrome on mobile: quote approval, VIN consent, repricing and delivery."""
import secrets,re
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login

def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screens=[];req=harness.checked_request
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(context)
        p=context.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440)
    try:
        harness.login_page(admin,base,'admin',password)
        def master(kind,values):return req(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':values},status=201)
        supplier=master('suppliers',{'code':'SQ-SUP','name':'合成报价实车供应商','payment_terms_days':30})
        model=master('vehicle_models',{'code':'SQ-EV','name':'合成报价纯电车型','brand':'虚构品牌','model_year':2026,'fuel_type':'electric','seats':5,'battery_wh':60000,'guide_price_cents':12000000})
        warehouse=master('warehouses',{'code':'SQ-W','name':'合成整车库','warehouse_type':'vehicles'})
        location=master('locations',{'code':'SQ-L','name':'合成销售交付位','warehouse_id':warehouse['id']})
        account=req(admin,'/api/flow/master/accounts','POST',{'values':{'name':'合成车辆收款账户','account_type':'bank','active':True}},status=201)
        day=admin.evaluate('day()')
        source=req(admin,'/api/vehicle-procurement/orders','POST',{'request_id':secrets.token_hex(16),'supplier_id':supplier['id'],'contracting_party':'合成报价试验有限公司','reason':'合成报价验收备车','due_date':day,'lines':[{'model_id':model['id'],'quantity':1,'color':'白色'}]},status=201)
        def api_upload(p,cid,label,category='evidence',source_file=None):
            result=p.evaluate('''async ({id,label,category,source_file})=>{const f=new FormData();f.append('category',category);if(source_file)f.append('source_file_id',source_file);f.append('file',new Blob(['合成来源 '+label],{type:'text/plain'}),label+'.txt');const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];const r=await fetch('/api/flow/cases/'+id+'/files',{method:'POST',headers:{'X-CSRF-Token':token,'X-Store-ID':'1'},body:f});return {status:r.status,body:await r.json()};}''',{'id':cid,'label':label,'category':category,'source_file':source_file})
            assert result['status']==200,result;return result['body']['id']
        contract=api_upload(admin,source['id'],'合成采购核价','procurement_contract')
        def purchase(key,values):
            current=req(admin,'/api/vehicle-procurement/orders/'+str(source['id']))
            return req(admin,f"/api/vehicle-procurement/orders/{source['id']}/actions/{key}",'POST',{'request_id':secrets.token_hex(16),'version':current['version'],'values':values})
        purchase('approve',{'prices':[{'line_id':source['lines'][0]['id'],'unit_cost_cents':8000,'list_price_cents':12000000}],'evidence_id':contract})
        fact=api_upload(admin,source['id'],'合成采购发运验收')
        shipped=purchase('ship',{'line_id':source['lines'][0]['id'],'vin':'LTEST000000000501','shipped_date':day,'expected_date':day,'evidence_id':fact})
        received=purchase('receive',{'shipment_id':shipped['shipments'][0]['id'],'vin':'LTEST000000000501','location_id':location['id'],'evidence_id':fact})
        vehicle=received['receipts'][0]['vehicle_id']
        employees={}
        for role,label in [('sales','销售'),('manager','店长'),('inventory','库管'),('service','检测顾问'),('finance','财务')]:
            secret=secrets.token_urlsafe(24);req(admin,'/api/users','POST',{'username':'quote-'+role,'display_name':'报价验收'+label,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},status=201)
            p=page();employee_login(p,base,'quote-'+role,secret);employees[role]=p
        sales,manager,inventory,service,finance=[employees[k] for k in ('sales','manager','inventory','service','finance')]
        customer=req(sales,'/api/flow/master/customers','POST',{'values':{'name':'合成购车客户','phone':'13900005333','contact_allowed':True,'note':''}},status=201)
        harness.navigate(sales,'sales-quotes','车辆报价与预订');sales.locator('[data-act=sales-quote-new]').click()
        sales.locator('#modal [name=customer]').select_option(str(customer['id']));sales.locator('#modal [name=model]').select_option(str(model['id']))
        sales.locator('#modal [name=amount]').fill('100.01');sales.locator('#modal [name=terms]').fill('合成客户确认车辆价款单独结算，变更需再次签回本报价版本。');sales.locator('#modal [name=reason]').fill('客户明确选择车型及价款')
        harness.assert_fits_mobile(sales);harness.save_modal(sales);expect(sales).to_have_url(re.compile(r'#sales-quotes/\d+'))
        cid=int(sales.url.split('/')[-1]);route='sales-quotes/'+str(cid)
        def current():return req(admin,'/api/sales-quotes/orders/'+str(cid))
        def visit(p):p.goto(base+'/?visit='+secrets.token_hex(5)+'#'+route);expect(p.locator('#main h1')).to_contain_text('车辆报价 · ')
        def act(p,key):p.locator('[data-act=sales-quote-action][data-key='+key+']').click();expect(p.locator('#modal')).to_be_visible()
        def upload(p,label,category='evidence',source_id=None):
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category)
            if source_id:p.locator('#modal [name=source_file_id]').select_option(str(source_id))
            p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('合成验收：'+label).encode()});harness.save_modal(p)
            return next(f['id'] for f in current()['files'] if f['name']==label+'.txt')
        def proof(p,fid):p.locator('#modal [name=evidence_id]').select_option(str(fid))
        visit(manager);act(manager,'quote_approve');manager.locator('#modal [name=reason]').fill('另一位主管核对本版车型与实际价款');harness.save_modal(manager)
        visit(inventory);assert 'amount_cents' not in req(inventory,'/api/sales-quotes/orders/'+str(cid))
        act(inventory,'allocate');inventory.locator('#modal [name=vehicle]').select_option(index=1);harness.save_modal(inventory);assert current()['vehicle_id']==vehicle
        for template in req(admin,'/api/flow/master/templates')['items']:
            if template['kind'] in {'contract','handover'}:req(admin,f"/api/flow/master/templates/{template['id']}",'PUT',{'version':template['version'],'values':{'title':template['title'],'clauses':template['clauses'],'approved':True}})
        def sign(p,label):
            visit(p);p.locator('[data-act=generatedoc][data-kind=contract]').click()
            expect(p.locator('#toast')).to_contain_text('生成')
            generated=next(f for f in current()['files'] if f['category']=='contract' and f['template_approved'])
            fid=upload(p,label,'signed_contract',generated['id']);act(p,'sign');proof(p,fid);harness.save_modal(p);return fid
        original_signature=sign(sales,'客户首版车型VIN合同签回')
        harness.assert_fits_mobile(sales);screens.append(harness.take_screenshot(sales,output,'01_mobile_current_quote_and_vin.png'))
        steps.append('销售在手机按明确车型报价，独立店长批准，库管只看无价格的本车型可用VIN并实际配车；销售生成本版合同并上传真实签回')
        visit(finance);fid=upload(finance,'车辆实际到账','receipt');act(finance,'receive');finance.locator('#modal [name=amount]').fill('100.01');finance.locator('#modal [name=account_id]').select_option(str(account['id']));finance.locator('#modal [name=reference]').fill('SQ-ACTUAL-IN');proof(finance,fid);harness.save_modal(finance)
        visit(service);pdi=upload(service,'实车交车检测','inspection');act(service,'inspect');service.locator('#modal [name=outcome]').select_option('合格');service.locator('#modal [name=result]').fill('本人核对本VIN实际检测合格');proof(service,pdi);harness.save_modal(service)
        visit(sales);sales.locator('[data-act=sales-quote-revise]').click();sales.locator('#modal [name=amount]').fill('99.98');sales.locator('#modal [name=reason]').fill('与客户协商三分差额，保留车型及实车');harness.save_modal(sales)
        visit(inventory);expect(inventory.locator('[data-key=dispatch]')).to_be_disabled();expect(inventory.locator('#main')).to_contain_text('原有效报价及文件保留')
        visit(manager);act(manager,'quote_approve');manager.locator('#modal [name=reason]').fill('批准本次降价与原款退差额');harness.save_modal(manager)
        visit(sales);act(sales,'sign');proof(sales,original_signature);sales.locator('#modal button[type=submit]').click();expect(sales.locator('#modal .formerror')).to_contain_text('不是当前版本');harness.assert_fits_mobile(sales);screens.append(harness.take_screenshot(sales,output,'02_mobile_old_signature_rejected.png'));sales.locator('#modal [data-act=close]').last.click()
        sign(sales,'客户新价款本版签回');assert current()['excess_cents']==3
        steps.append('已收款且PDI合格后提出新报价，暂阻出库；主管再次批准，旧版合同签回中文拒绝，新版客户确认后产生原款三分待退')
        visit(finance);refund=upload(finance,'三分原路实际退款','receipt');act(finance,'refund_excess');finance.locator('#modal [name=original_id]').select_option(str(current()['payments'][0]['id']));finance.locator('#modal [name=account_id]').select_option(str(account['id']));finance.locator('#modal [name=reference]').fill('SQ-ACTUAL-REFUND');proof(finance,refund);harness.save_modal(finance)
        assert current()['paid_cents']==9998;harness.assert_fits_mobile(finance);screens.append(harness.take_screenshot(finance,output,'03_mobile_original_difference_refund.png'))
        visit(inventory);out=upload(inventory,'实际车辆出库交接');act(inventory,'dispatch');proof(inventory,out);harness.save_modal(inventory)
        visit(sales);sales.locator('[data-act=generatedoc][data-kind=handover]').click();expect(sales.locator('#toast')).to_contain_text('生成');handover=next(f for f in current()['files'] if f['category']=='handover')
        pickup=upload(sales,'客户实际提车签回','signed_handover',handover['id']);act(sales,'deliver');proof(sales,pickup);harness.save_modal(sales)
        assert current()['state']=='delivered' and len(current()['quotes'])==2
        harness.assert_fits_mobile(sales);screens.append(harness.take_screenshot(sales,output,'04_mobile_final_delivery_quote_history.png'))
        steps.append('财务按原收款和原账户实际退款，现金净收99.98元；库管才可出库，销售以绑定最新报价与VIN的交付单确认实际提车，两版历史完整保留')
        harness.navigate(sales,'sales-quotes','车辆报价与预订')
        expect(sales.locator('#main')).to_contain_text('版本报价')
        sales.locator('[data-route="'+route+'"]').click()
        expect(sales).to_have_url(re.compile('#'+route+'$'))
        expect(sales.locator('#main h1')).to_contain_text('车辆报价 · ')
        assert not errors,errors
        return {'mode':'real_http_chrome','viewport':'390x844','file_scan_mode':'structure_only','checks_passed':len(steps),'steps':steps,'screenshots':screens,'javascript_errors':errors,'net_cash_cents':9998}
    finally:
        for context in contexts:context.close()

if __name__=='__main__':harness.exercise=exercise;harness.main()
