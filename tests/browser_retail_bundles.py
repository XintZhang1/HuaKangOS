"""Real Chrome employee package publication, frozen allocation and original partial return."""
import secrets
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request,request,login_page,navigate,save_modal,take_screenshot,assert_fits_mobile

def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screenshots=[]
    def page(width=390):
        ctx=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(ctx)
        p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440)
    try:
        login_page(admin,base,'admin',password)
        def typed(kind,v):return checked_request(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':v},status=201)
        def master(kind,v):return checked_request(admin,'/api/flow/master/'+kind,'POST',{'values':v},status=201)
        customer=master('customers',{'name':'合成精品客户','phone':'13900000321','contact_allowed':True,'note':''})
        items=[master('items',{'sku':'RETAIL-'+str(i),'name':name,'unit':'件','reorder':'0','active':True}) for i,name in enumerate(['安装精品','随车礼品'])]
        work=typed('work_items',{'code':'RETAIL-INSTALL','name':'精品实际安装','billing_unit':'job','standard_fee_cents':100})
        supplier=typed('suppliers',{'code':'RETAIL-SUP','name':'合成精品供应商'});account=master('accounts',{'name':'合成精品银行账户','account_type':'bank','active':True})
        purchase=checked_request(admin,'/api/procurement/orders','POST',{'request_id':secrets.token_hex(16),'supplier_id':supplier['id'],'reason':'本次合成精品验收库存',
            'lines':[{'item_id':items[0]['id'],'quantity_milli':2500,'unit_cost_cents':123},{'item_id':items[1]['id'],'quantity_milli':1000,'unit_cost_cents':1}]},status=201)
        def admin_upload(case,label):
            result=admin.evaluate('''async ({id,label})=>{const f=new FormData();f.append('category','evidence');f.append('file',new Blob([label],{type:'text/plain'}),label+'.txt');const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];const r=await fetch('/api/flow/cases/'+id+'/files',{method:'POST',headers:{'X-CSRF-Token':token,'X-Store-ID':'1'},body:f});return {status:r.status,body:await r.json()};}''',{'id':case,'label':label})
            assert result['status']==200,result;return result['body']['id']
        fid=admin_upload(purchase['id'],'合成精品采购到货')
        for key,values in [('approve',{}),('receive',{'evidence_id':fid,'lines':[{'line_id':l['id'],'quantity_milli':l['quantity_milli']} for l in purchase['lines']]})]:
            purchase=checked_request(admin,f"/api/procurement/orders/{purchase['id']}/actions/{key}",'POST',{'request_id':secrets.token_hex(16),'version':purchase['version'],'values':values})
        employees={}
        for role,label in [('sales','销售'),('manager','店长'),('inventory','库管'),('technician','技师'),('finance','财务')]:
            secret=secrets.token_urlsafe(24);checked_request(admin,'/api/users','POST',{'username':'retail-'+role,'display_name':'精品验收'+label,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},status=201)
            p=page();login_page(p,base,'retail-'+role,secret);p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24)
            p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'retail-'+role,changed);employees[role]=p
        sales,manager,inventory,technician,finance=(employees[k] for k in ['sales','manager','inventory','technician','finance'])
        customer=checked_request(sales,'/api/flow/master/customers','POST',{'values':{'name':'销售精品客户','phone':'13900000322','contact_allowed':True,'note':''}},status=201)
        navigate(manager,'retail-bundle-rules','精品套餐配置');manager.locator('[data-act=retail-bundle-rule]').click()
        assert not manager.locator('#modal [name=enabled]').is_checked()
        manager.locator('#modal [name=code]').fill('MOBILE-RETAIL-KIT');manager.locator('#modal [name=name]').fill('组合精品安装套餐')
        line=manager.locator('[data-retail-bundle-line]').first
        line.locator('[name=item]').select_option(str(items[0]['id']));line.locator('[name=quantity]').fill('1.000');line.locator('[name=goods]').fill('5.00')
        line.locator('[name=work]').select_option(str(work['id']));line.locator('[name=installation]').fill('1.00')
        manager.locator('[data-act=retail-bundle-add]').click();line=manager.locator('[data-retail-bundle-line]').nth(1)
        line.locator('[name=item]').select_option(str(items[1]['id']));line.locator('[name=quantity]').fill('0.333');line.locator('[name=goods]').fill('0.01')
        manager.locator('#modal [name=price]').fill('6.00');manager.locator('#modal [name=terms]').fill('客户已明确按冻结原组件金额退货，已实际安装的对应费用保留，不重估剩余商品。')
        manager.locator('#modal [name=enabled]').check();assert_fits_mobile(manager);save_modal(manager)
        screenshots.append(take_screenshot(manager,output,'00_mobile_frozen_package_rule.png'))
        navigate(sales,'retail-bundles','精品销售套餐');sales.locator('[data-act=retail-bundle-sale]').click()
        sales.locator('#modal [name=customer]').select_option(str(customer['id']));sales.locator('#modal [name=sets]').fill('2')
        sales.locator('#modal button[type=submit]').click();expect(sales.locator('#modal h2')).to_have_text('确认套餐分摊与退货规则')
        expect(sales.locator('#modal')).to_contain_text('0.666');expect(sales.locator('#modal')).to_contain_text('不因退回部分商品重新定价剩余商品')
        sales.locator('#modal [name=accepted]').check();assert_fits_mobile(sales);save_modal(sales)
        expect(sales).to_have_url(__import__('re').compile(r'#retail/\d+'));case_id=int(sales.url.split('/')[-1]);route='retail/'+str(case_id)
        def current():return checked_request(admin,'/api/retail/orders/'+str(case_id))
        assert current()['bundle']['rule_version']==1 and current()['lines'][1]['quantity_milli']==666
        sales.locator('[data-act=generatedoc][data-kind=retail_quote]').click()
        expect(sales.locator('.filerecord').filter(has_text='精品套餐报价确认单')).to_have_count(1)
        generated=next(f for f in checked_request(admin,'/api/flow/cases/'+str(case_id))['files'] if f['category']=='retail_quote')
        assert generated['generated'] and not generated['template_approved']
        expect(sales.locator('#main')).to_contain_text('商品套餐分摊')
        assert_fits_mobile(sales);screenshots.append(take_screenshot(sales,output,'01_mobile_original_package_quote.png'))

        def visit(p):p.goto(base+'/?visit='+secrets.token_hex(5)+'#'+route);expect(p.locator('#main h1')).to_contain_text('精品销售 · ')
        def action(p,key,id=None):
            selector='[data-act=retail-action][data-key='+key+']'+('[data-id="'+str(id)+'"]' if id else '')
            p.locator(selector).click();expect(p.locator('#modal')).to_be_visible()
        def upload(p,label,category='evidence'):
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category);p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('合成证据：'+label).encode()});save_modal(p)
            expect(p.locator('#main')).to_contain_text(label+'.txt');return next(f['id'] for f in checked_request(admin,'/api/flow/cases/'+str(case_id))['files'] if f['name']==label+'.txt')
        def proof(p,fid):p.locator('#modal [name=evidence_id]').select_option(str(fid))
        visit(manager);action(manager,'approve');manager.locator('#modal [name=minimum]').fill('12.01');manager.locator('#modal [name=reason]').fill('明确本报价价格及授权例外')
        manager.locator('#modal button[type=submit]').click();expect(manager.locator('#modal .formerror')).to_contain_text('低于明确最低价');manager.locator('#modal [name=allow_below_minimum]').check();save_modal(manager)
        visit(sales);auth=upload(sales,'客户报价与安装保留费确认','authorization');action(sales,'authorize');proof(sales,auth);save_modal(sales)
        assert current()['amount_cents']==1200;steps.append('店长手机发布默认关闭的组成规则再明确启用；销售购买2套显示0.666商品及每套冻结分摊，生成草稿报价不算授权，主管低价批准后客户实际确认')
        visit(finance);cash=upload(finance,'本单分笔实际到账','receipt')
        for n,amount in enumerate(['5.00','7.00']):
            visit(finance);action(finance,'receive');finance.locator('#modal [name=amount]').fill(amount);finance.locator('#modal [name=account_id]').select_option(str(account['id']));finance.locator('#modal [name=reference]').fill('RETAIL-BROWSER-IN-'+str(n));proof(finance,cash);save_modal(finance)
        visit(inventory);assert 'amount_cents' not in request(inventory,'/api/retail/orders/'+str(case_id))['body']
        assert request(inventory,'/api/flow/files/'+str(auth))['status']==403
        expect(inventory.locator('#main')).not_to_contain_text('客户报价与安装保留费确认.txt')
        stock=upload(inventory,'实际精品出库与交接');action(inventory,'dispatch');proof(inventory,stock);save_modal(inventory)
        visit(sales);handover=upload(sales,'客户实际接收商品');action(sales,'accept');proof(sales,handover);sales.locator('#modal button[type=submit]').click();expect(sales.locator('#modal .formerror')).to_contain_text('尚未由技师确认实际安装');screenshots.append(take_screenshot(sales,output,'02_mobile_install_required.png'));sales.locator('#modal [data-act=close]').last.click()
        visit(technician);assert 'amount_cents' not in request(technician,'/api/retail/orders/'+str(case_id))['body'];installation=upload(technician,'实际安装结果');action(technician,'install');technician.locator('#modal [name=result]').fill('本次安装已完成并核对结果');proof(technician,installation);save_modal(technician)
        visit(sales);action(sales,'accept');proof(sales,handover);save_modal(sales);assert current()['state']=='completed';steps.append('分笔真实收款、库管出库、技师实际安装与客户接收独立；未安装不能交付，库存与技师看不到价格')
        action(sales,'return_request');sales.locator('#modal [name=reason]').fill('客户要求原单部分退货');sales.locator('#modal [name=source]').select_option(index=1);sales.locator('#modal [name=quantity]').fill('0.500');proof(sales,handover);save_modal(sales);ret=current()['returns'][0]
        visit(manager);action(manager,'return_approve',ret['id']);manager.locator('#modal [name=reason]').fill('核对原商品及已履约安装费保留');save_modal(manager)
        visit(inventory);qc=upload(inventory,'退货可售检查','inspection');action(inventory,'return_receive',ret['id']);inventory.locator('#modal [name=result]').fill('外观不合格需修复后重新检查');inventory.locator('#modal [name=outcome]').select_option('不合格');proof(inventory,qc);save_modal(inventory)
        assert current()['totals']['refund_due_cents']==0;assert_fits_mobile(inventory);screenshots.append(take_screenshot(inventory,output,'03_mobile_failed_return_no_stock.png'));steps.append('原出库部分退货先经店长批准；库管验收不合格不增加可售库存和退款额度')
        visit(technician);fix=upload(technician,'退货缺陷整改');action(technician,'return_rectify',ret['id']);technician.locator('#modal [name=result]').fill('缺陷处理完成，提交独立复检');proof(technician,fix);save_modal(technician)
        visit(inventory);action(inventory,'return_receive',ret['id']);inventory.locator('#modal [name=result]').fill('复检通过，可重新销售');inventory.locator('#modal [name=outcome]').select_option('合格');proof(inventory,qc);save_modal(inventory)
        assert current()['totals']['refund_due_cents']==250 and current()['totals']['retained_installation_cents']==50
        visit(finance);refund_file=upload(finance,'实际原路退款','receipt');action(finance,'refund');finance.locator('#modal [name=account_id]').select_option(str(account['id']));finance.locator('#modal [name=reference]').fill('RETAIL-BROWSER-REFUND');finance.locator('#modal [name=original]').select_option(index=1);proof(finance,refund_file);save_modal(finance)
        final=current();assert final['state']=='completed' and final['totals']['net_paid_cents']==950 and final['totals']['refund_due_cents']==0
        assert_fits_mobile(finance);screenshots.append(take_screenshot(finance,output,'04_mobile_original_refund.png'))
        finance.locator('.panel').filter(has=finance.get_by_role('heading',name='精品收退款与当前应收',exact=True)).screenshot(path=str(output/'05_mobile_settlement_panel.png'));screenshots.append(str(output/'05_mobile_settlement_panel.png'))
        steps.append('技师整改、库管复检合格才按原成本入库；原账户退回2.50元，已履约安装保留0.50元，真实净收9.50元，剩余赠品原分摊0.02元不重估')
        assert not errors,errors
        return {'mode':'real_http_chrome','file_scan_mode':'structure_only','viewport':'390x844','checks_passed':len(steps),'steps':steps,'javascript_errors':errors,'screenshots':screenshots,'actual_net_cash_cents':950,'retained_installation_cents':50}
    finally:
        for context in contexts:context.close()

if __name__=='__main__':harness.exercise=exercise;harness.main()
