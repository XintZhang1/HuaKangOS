"""Real Chrome zero-price gifts: real employee approval, physical receipt and return."""
import secrets
from datetime import date
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request as req,request,login_page,save_modal,take_screenshot,assert_fits_mobile
def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screens=[]
    def page(width=390):
        c=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(c);p=c.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440)
    try:
        login_page(admin,base,'admin',password)
        def post(p,path,v,status=200):return req(p,path,'POST',v,status=status)
        def typed(kind,v):return post(admin,'/api/masters/'+kind,dict(request_id=secrets.token_hex(16),values=v),201)
        def master(kind,v):return post(admin,'/api/flow/master/'+kind,dict(values=v),201)
        def rawproof(p,cid,label,category='evidence'):
            r=p.evaluate('''async({id,label,category})=>{const f=new FormData();f.append('category',category);f.append('file',new Blob([label],{type:'text/plain'}),label+'.txt');const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];const r=await fetch('/api/flow/cases/'+id+'/files',{method:'POST',headers:{'X-CSRF-Token':token,'X-Store-ID':'1'},body:f});return {status:r.status,body:await r.json()};}''',{'id':cid,'label':label,'category':category});assert r['status']==200,r;return r['body']['id']
        def domain(p,path,cid,key,v):return post(p,f'{path}/{cid}/actions/{key}',dict(request_id=secrets.token_hex(16),version=req(admin,f'{path}/{cid}')['version'],values=v))
        supplier=typed('suppliers',{'code':'ADD-SUP','name':'合成加装供应商'});item=master('items',{'sku':'ADD-ITEM','name':'合成车辆加装组件','unit':'件','reorder':'0','active':True});work=typed('work_items',{'code':'ADD-WORK','name':'组件实际安装','billing_unit':'job','standard_fee_cents':100});account=master('accounts',{'name':'合成加装原款银行','account_type':'bank','active':True})
        purchase=post(admin,'/api/procurement/orders',dict(request_id=secrets.token_hex(16),supplier_id=supplier['id'],reason='合成验收备料',lines=[dict(item_id=item['id'],quantity_milli=2500,unit_cost_cents=123)]),201)
        purchase=domain(admin,'/api/procurement/orders',purchase['id'],'approve',{});domain(admin,'/api/procurement/orders',purchase['id'],'receive',dict(lines=[dict(line_id=purchase['lines'][0]['id'],quantity_milli=2500)],evidence_id=rawproof(admin,purchase['id'],'合成物资实际到货')))
        model=typed('vehicle_models',dict(code='ADD-MODEL',name='合成安装车型',brand='合成品牌',model_year=2026,fuel_type='electric',seats=5,battery_wh=60000,guide_price_cents=12000000));wh=typed('warehouses',dict(code='ADD-CAR-W',name='合成车辆仓',warehouse_type='vehicles'));loc=typed('locations',dict(code='ADD-CAR-L',name='合成车辆位',warehouse_id=wh['id']))
        car=post(admin,'/api/vehicle-procurement/orders',dict(request_id=secrets.token_hex(16),supplier_id=supplier['id'],contracting_party='合成门店',reason='合成安装原VIN',due_date=date.today().isoformat(),lines=[dict(model_id=model['id'],color='白',quantity=1)]),201)
        car=domain(admin,'/api/vehicle-procurement/orders',car['id'],'approve',dict(prices=[dict(line_id=car['lines'][0]['id'],unit_cost_cents=100000,list_price_cents=120000)],evidence_id=rawproof(admin,car['id'],'合成车辆核价原件','procurement_contract')))
        vin='LHGCM82633A118833';car=domain(admin,'/api/vehicle-procurement/orders',car['id'],'ship',dict(line_id=car['lines'][0]['id'],vin=vin,shipped_date=date.today().isoformat(),expected_date=date.today().isoformat(),evidence_id=rawproof(admin,car['id'],'合成原车实际发运')));car=domain(admin,'/api/vehicle-procurement/orders',car['id'],'receive',dict(shipment_id=car['shipments'][0]['id'],vin=vin,location_id=loc['id'],evidence_id=rawproof(admin,car['id'],'合成原车实际接收')))
        employees={}
        for role in ('sales','manager','inventory','technician','service','finance'):
            secret=secrets.token_urlsafe(24);post(admin,'/api/users',dict(username='addon-'+role,display_name='加装验收'+role,role=role,password=secret,store_roles=[dict(store_id=1,role=role)]),201);p=page();login_page(p,base,'addon-'+role,secret);p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24);p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'addon-'+role,changed);employees[role]=p
        sales,manager,inventory,technician,service,finance=(employees[k] for k in ('sales','manager','inventory','technician','service','finance'))
        source=post(sales,'/api/flow/cases',dict(request_id=secrets.token_hex(16),kind='order',values=dict(customer_name='合成加装客户',customer_phone='13900006123',confirm_new_customer=True,model='合成安装车型',amount='1200',delivery_due=date.today().isoformat())),201)
        source=domain(admin,'/api/flow/cases',source['id'],'approve',{});source=domain(admin,'/api/flow/cases',source['id'],'allocate',dict(vehicle_id=car['receipts'][0]['vehicle_id']))
        sales.goto(base+'/#addon-orders');expect(sales.locator('#main h1')).to_have_text('销售加装明细');sales.locator('[data-act=addon-new]').click();sales.locator('#modal [name=source]').select_option(label=str(source['id'])+' · '+source['number']+' · '+source['title']);sales.locator('#modal [name=reason]').fill('客户明确本车加装组件与施工');save_modal(sales)
        row=req(admin,'/api/addon-orders')['items'][0];cid=row['id'];route='addon-orders/'+str(cid)
        def current():return req(admin,'/api/addon-orders/'+str(cid))
        def visit(p):p.goto(base+'/?visit='+secrets.token_hex(4)+'#'+route);expect(p.locator('#main h1')).to_have_text('销售加装明细')
        def action(p,key,**extra):p.locator('[data-act=addon-action][data-key='+key+']'+''.join('[data-'+k+'="'+str(v)+'"]' for k,v in extra.items())).click();expect(p.locator('#modal')).to_be_visible()
        def upload(p,label,category):
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category);p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('仅合成实际原件 '+label).encode()});save_modal(p);expect(p.locator('#main')).to_contain_text(label+'.txt');return next(f['id'] for f in req(admin,'/api/flow/cases/'+str(cid))['files'] if f['name']==label+'.txt')
        def simple(p,key,label,category='authorization',**extra):visit(p);fid=upload(p,label,category);action(p,key,**extra);p.locator('#modal [name=evidence_id]').select_option(str(fid));return fid
        action(sales,'quote');line=sales.locator('[data-addon-line]').first;line.locator('[name=item]').select_option(str(item['id']));line.locator('[name=work]').select_option(str(work['id']));line.locator('[name=quantity]').fill('2.000');line.locator('[name=goods]').fill('0.00');line.locator('[name=installation]').fill('0.00');line.locator('[name=gift_reason]').fill('购买本车赠送组件和实际安装');line.locator('[name=gift_cost_bearer]').select_option('selling_store');sales.locator('#modal [name=reason]').fill('本销售门店承担真实商品及安装成本');assert_fits_mobile(sales);save_modal(sales);screens.append(take_screenshot(sales,output,'01_addon_frozen_quote_mobile.png'))
        simple(manager,'approve','独立主管赠送核价');manager.locator('#modal [name=reason]').fill('独立确认赠送原因及本销售门店承担成本');manager.locator('#modal button[type=submit]').click();expect(manager.locator('#modal .formerror')).to_contain_text('赠送');screens.append(take_screenshot(manager,output,'02_gift_approval_requires_explicit_confirmation.png'));manager.locator('#modal [name=gift_approval]').select_option('明确批准本版赠送及本销售门店成本承担');save_modal(manager);auth=simple(sales,'authorize','客户本版零价加装授权');save_modal(sales)
        visit(finance);assert finance.locator('[data-key=receive]').count()==0;assert current()['totals']['receivable_cents']==0
        simple(inventory,'dispatch','本车原物资实领','evidence');inventory.locator('#modal [name=checked_vin]').fill('LHGCM82633A000000');inventory.locator('#modal button[type=submit]').click();expect(inventory.locator('#modal .formerror')).to_contain_text('VIN');assert_fits_mobile(inventory);screens.append(take_screenshot(inventory,output,'02_addon_wrong_vin_refused_mobile.png'));inventory.locator('#modal [name=checked_vin]').fill(vin);save_modal(inventory)
        d=current()['dispatches'][0]['id'];simple(technician,'install','技师实际安装','inspection',dispatch=d);technician.locator('#modal [name=result]').fill('本人完成本批原车组件安装');save_modal(technician)
        i=current()['installations'][0]['id'];simple(service,'quality','加装实际不合格检查','inspection',installation=i);service.locator('#modal [name=outcome]').select_option('不合格');service.locator('#modal [name=result]').fill('固定件松动，需整改复检');save_modal(service);visit(sales);assert sales.locator('[data-key=accept]').count()==0;assert_fits_mobile(sales);screens.append(take_screenshot(sales,output,'03_addon_failed_quality_blocks_acceptance.png'))
        inspection=current()['inspections'][0]['id'];simple(technician,'rectify','实际整改原缺陷','inspection',inspection=inspection);technician.locator('#modal [name=result]').fill('已重新紧固，交顾问复检');save_modal(technician);simple(service,'quality','整改复检通过','inspection',installation=i);service.locator('#modal [name=result]').fill('本人复检原缺陷已消除');save_modal(service);simple(sales,'accept','客户实际接收加装');save_modal(sales)
        assert current()['state']=='completed';steps.append('销售按行冻结赠送原因及本销售门店成本承担；主管漏确认拒绝后独立批准；客户授权，VIN错配拒绝，检查不合格整改复检后仍须客户接收')
        simple(sales,'resolution','原商品部分拆回方案');sales.locator('#modal [name=kind]').select_option('实际拆回原商品');sales.locator('#modal [name=original]').select_option(label='已装:'+str(i)+' · 安装批次'+str(i));sales.locator('#modal [name=quantity]').fill('0.500');sales.locator('#modal [name=reason]').fill('客户实际拆回半件零价赠品，核对原成本');save_modal(sales);pid=current()['plans'][0]['id']
        simple(manager,'resolution_approve','独立批准拆回方案',plan=pid);manager.locator('#modal [name=result]').fill('独立复核原数量与安装保留费');save_modal(manager);simple(sales,'resolution_consent','客户同意赠品原实物拆回',plan=pid);sales.locator('#modal [name=result]').fill('客户确认零价赠品部分退回，无原客户款项可退');save_modal(sales)
        simple(inventory,'return_receive','拆回可售实际验收','inspection',plan=pid);inventory.locator('#modal [name=result]').fill('本人检查原商品可恢复可售');save_modal(inventory)
        result=current();assert result['totals']['charge_cents']==result['totals']['paid_cents']==result['totals']['refund_due_cents']==0
        assert result['payments']==[] and result['credits']==[] and result['return_postings'][0]['value_cents']>0
        visit(finance);assert finance.locator('[data-key=receive]').count()==finance.locator('[data-key=refund]').count()==0;assert_fits_mobile(finance);screens.append(take_screenshot(finance,output,'05_gift_return_original_cost_without_customer_cash.png'));steps.append('零价赠送仍经过原VIN领料、实际安装与客户接收；原批次部分拆回恢复真实库存成本，无收款、退款或虚构客户资金')
        visit(inventory);assert 'totals' not in req(inventory,'/api/addon-orders/'+str(cid));assert request(inventory,'/api/flow/files/'+str(auth))['status']==403;assert 'goods_cents' not in req(technician,'/api/addon-orders/'+str(cid))['lines'][0];steps.append('六个真实员工会话，库管技师均不能读取报价金额或客户价格授权文件；390px全部办理')
        assert not errors,errors
        return dict(status='passed',synthetic_only=True,mode='real-Windows-Chrome-HTTP',viewport=390,passed=steps,javascript_errors=errors,screenshots=screens,gift_charge_cents=result['totals']['charge_cents'],customer_paid_cents=result['totals']['paid_cents'],original_return_value_cents=result['return_postings'][0]['value_cents'])
    finally:
        for c in contexts:c.close()
if __name__=='__main__':harness.exercise=exercise;harness.main()
