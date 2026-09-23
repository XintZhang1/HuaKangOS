"""Real employee Chrome exercise of source-backed noncustomer vehicle income."""
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
        supplier=typed('suppliers',dict(code='VIN-INC-SUP',name='合成原车辆厂家',tax_identifier='SYNTHINCOME00001'))
        account=master('accounts',dict(name='合成厂家原款银行',account_type='bank',active=True));wrong=master('accounts',dict(name='另一账户不能冒充原退款',account_type='bank',active=True))
        model=typed('vehicle_models',dict(code='INC-MODEL',name='合成返利原车型',brand='合成品牌',model_year=2026,fuel_type='electric',seats=5,battery_wh=60000,guide_price_cents=12000000));wh=typed('warehouses',dict(code='INC-CAR-W',name='合成原车仓',warehouse_type='vehicles'));loc=typed('locations',dict(code='INC-CAR-L',name='合成原车位',warehouse_id=wh['id']))
        car=post(admin,'/api/vehicle-procurement/orders',dict(request_id=secrets.token_hex(16),supplier_id=supplier['id'],contracting_party='合成门店',reason='合成厂家返利原采购',due_date=date.today().isoformat(),lines=[dict(model_id=model['id'],color='白',quantity=1)]),201)
        car=domain(admin,'/api/vehicle-procurement/orders',car['id'],'approve',dict(prices=[dict(line_id=car['lines'][0]['id'],unit_cost_cents=100000,list_price_cents=120000)],evidence_id=rawproof(admin,car['id'],'合成采购核价原件','procurement_contract')))
        vin='LHGCM82633A118855';car=domain(admin,'/api/vehicle-procurement/orders',car['id'],'ship',dict(line_id=car['lines'][0]['id'],vin=vin,shipped_date=date.today().isoformat(),expected_date=date.today().isoformat(),evidence_id=rawproof(admin,car['id'],'合成原车实际发运')));car=domain(admin,'/api/vehicle-procurement/orders',car['id'],'receive',dict(shipment_id=car['shipments'][0]['id'],vin=vin,location_id=loc['id'],evidence_id=rawproof(admin,car['id'],'合成原车实际接收')))
        employees={}
        for role in ('finance','manager','sales'):
            secret=secrets.token_urlsafe(24);post(admin,'/api/users',dict(username='income-'+role,display_name='厂家收入验收'+role,role=role,password=secret,store_roles=[dict(store_id=1,role=role)]),201);p=page();login_page(p,base,'income-'+role,secret);p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24);p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'income-'+role,changed);employees[role]=p
        finance,manager,sales=(employees[k] for k in ('finance','manager','sales'))
        finance.goto(base+'/#vehicle-income');expect(finance.locator('#main h1')).to_have_text('厂家及供应商整车其他收入');finance.locator('[data-act=vehicle-income-new]').click()
        finance.locator('#modal [name=supplier]').select_option(str(supplier['id']));finance.locator('#modal [name=external_reference]').fill('SYNTH-FACTORY-SETTLEMENT-2026');finance.locator('#modal [data-income-source]').select_option(label=car['number']+' · '+vin);finance.locator('#modal [data-income-add]').click();expect(finance.locator('#modal [data-income-source]')).to_have_count(2);finance.locator('#modal [name=reason]').fill('按厂家真实结算单与已接收原车核对其他收入');assert_fits_mobile(finance);save_modal(finance)
        row=req(admin,'/api/vehicle-income')['items'][0];cid=row['id'];route='vehicle-income/'+str(cid)
        def current():return req(admin,'/api/vehicle-income/'+str(cid))
        def visit(p):p.goto(base+'/?visit='+secrets.token_hex(4)+'#'+route);expect(p.locator('#main h1')).to_have_text('厂家及供应商整车其他收入')
        def action(p,key):p.locator('[data-act=vehicle-income-action][data-key='+key+']').click();expect(p.locator('#modal')).to_be_visible()
        def upload(p,label,category):
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category);p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('仅合成实际原件 '+label).encode()});save_modal(p);expect(p.locator('#main')).to_contain_text(label+'.txt');return next(f['id'] for f in req(admin,'/api/flow/cases/'+str(cid))['files'] if f['name']==label+'.txt')
        def simple(p,key,label,category='evidence'):
            visit(p);fid=upload(p,label,category);action(p,key);p.locator('#modal [name=evidence_id]').select_option(str(fid));p.locator('#modal [name=reason]').fill(label+'，本人按原件实际核对');return fid
        simple(finance,'propose','原厂家应收申请');finance.locator('#modal [name=amount]').fill('10.00');expect(finance.locator('#modal [name=mode]')).to_have_value('');finance.locator('#modal [name=mode]').select_option('按对方原票或结算凭据办理');save_modal(finance)
        assert current()['totals']['target_cents']==0 and current()['payments']==[]
        visit(finance);assert finance.locator('[data-key=approve]').count()==0;assert finance.locator('[data-key=receive]').count()==0;assert_fits_mobile(finance);screens.append(take_screenshot(finance,output,'01_finance_pending_independent_target.png'))
        simple(manager,'approve','独立主管确认原厂家结算');assert_fits_mobile(manager);save_modal(manager)
        def cash(key,label,amount,original=None,account_id=None):
            simple(finance,key,label,'receipt');finance.locator('#modal [name=amount]').fill(amount);finance.locator('#modal [name=account_id]').select_option(str(account_id or account['id']));finance.locator('#modal [name=reference]').fill(label); 
            if original is not None:finance.locator('#modal [name=original]').select_option(label=next(o.inner_text() for o in finance.locator('#modal [name=original] option').all() if o.inner_text().startswith(str(original)+' · ')))
        cash('receive','合成第一笔到账','6.00');save_modal(finance);cash('receive','合成第二笔到账','4.00');save_modal(finance)
        result=current();assert result['state']=='completed' and result['totals']['net_received_cents']==1000
        first,second=[p['id'] for p in result['payments']];assert_fits_mobile(finance);screens.append(take_screenshot(finance,output,'02_two_real_original_cash_receipts.png'));steps.append('财务选真实厂家与原采购VIN，不新建客户；开票依据必须手选；另一主管批准前没有应收或收款，批准后两笔实际到账')
        simple(finance,'propose','原结算修订为四元五角');finance.locator('#modal [name=amount]').fill('4.50');finance.locator('#modal [name=mode]').select_option('按对方原票或结算凭据办理');save_modal(finance)
        simple(manager,'approve','独立核对调减原目标');save_modal(manager);assert current()['totals']['refund_due_cents']==550
        cash('refund','原第二笔四元退回','4.00',second,wrong['id']);finance.locator('#modal button[type=submit]').click();expect(finance.locator('#modal .formerror')).to_contain_text('原');screens.append(take_screenshot(finance,output,'03_wrong_refund_account_refused.png'));finance.locator('#modal [name=account_id]').select_option(str(account['id']));save_modal(finance)
        cash('refund','原第一笔部分退回','1.50',first);save_modal(finance)
        result=current();assert result['state']=='completed' and result['totals']['net_received_cents']==450 and len(result['payments'])==4
        assert result['sources'][0]['vin']==vin and all(r['invoice_mode']=='external_document' for r in result['revisions']);assert_fits_mobile(finance);screens.append(take_screenshot(finance,output,'04_original_partial_refunds_and_frozen_revisions.png'));steps.append('已结清原单可追加独立目标修订；原资金不覆盖，原账户错选被中文提示拒绝；分两笔原路退款后原应收与现金一致')
        assert request(sales,'/api/vehicle-income/'+str(cid))['status']==403;assert request(sales,'/api/flow/cases/'+str(cid))['status'] in (403,404)
        sales.goto(base+'/#home');assert sales.locator('a[href="#vehicle-income"]').count()==0
        analytics=req(finance,'/api/flow/analytics');assert analytics['metrics']['vehicle_other_income_recognized_cents']==analytics['metrics']['vehicle_other_income_cash_net_cents']==450
        steps.append('普通销售不能读取非客户收入原单；财务报表确认差额与实际净收各为450分，没有重复现金；全部办理390px无页面溢出')
        assert not errors,errors
        return dict(status='passed',synthetic_only=True,mode='real-Windows-Chrome-HTTP',viewport=390,passed=steps,javascript_errors=errors,screenshots=screens,target_cents=450,actual_net_cents=450,actual_cash_count=4,original_vin=vin)
    finally:
        for c in contexts:c.close()
if __name__=='__main__':harness.exercise=exercise;harness.main()
