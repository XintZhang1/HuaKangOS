"""Real employee Chrome mixed package purchase/use/refund in a new isolated DB."""
import secrets
from datetime import date
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request as req,login_page,save_modal,take_screenshot,assert_fits_mobile

def exercise(browser,base,password,output):
    contexts=[];employees={};errors=[];shots=[];steps=[]
    def page(width=390):
        c=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(c);p=c.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440)
    try:
        login_page(admin,base,'admin',password)
        def post(p,path,v,status=200):return req(p,path,'POST',v,status=status)
        def key():return secrets.token_hex(16)
        def master(kind,v):return post(admin,'/api/flow/master/'+kind,{'values':v},201)
        def typed(kind,v):return post(admin,'/api/masters/'+kind,{'request_id':key(),'values':v},201)
        def proof(cid,label,category='evidence'):
            result=admin.evaluate('''async({cid,label,category})=>{const f=new FormData();f.append('category',category);f.append('file',new Blob([label],{type:'text/plain'}),label+'.txt');const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];const r=await fetch('/api/flow/cases/'+cid+'/files',{method:'POST',headers:{'X-CSRF-Token':token,'X-Store-ID':'1'},body:f});return {status:r.status,body:await r.json()};}''',dict(cid=cid,label=label,category=category));assert result['status']==200,result;return result['body']['id']
        def visit(p,route):p.goto(base+'/?trial='+key()+'#'+route);expect(p.locator('#main h1')).to_be_visible()
        def fill(p,name,value):p.locator('#modal [name='+name+']').fill(str(value))
        def choose(p,name,value):p.locator('#modal [name='+name+']').select_option(str(value))
        ids={}
        for role in ('service','manager','finance','inventory','technician'):
            secret=secrets.token_urlsafe(24);u=post(admin,'/api/users',dict(username='package-'+role,display_name='套餐验收'+role,role=role,password=secret,store_roles=[dict(store_id=1,role=role)]),201);ids[role]=u['id']
            p=page();login_page(p,base,'package-'+role,secret);fill(p,'current_password',secret);changed=secrets.token_urlsafe(24);fill(p,'new_password',changed);save_modal(p);login_page(p,base,'package-'+role,changed);employees[role]=p
        service,manager,finance,inventory,tech=[employees[k] for k in ('service','manager','finance','inventory','technician')]
        customer=master('customers',dict(name='合成多组件原套餐客户',phone='13900006191',contact_allowed=True,note=''))
        item=master('items',dict(sku='PACKAGE-PART',name='合成原套餐实际配件',unit='件',reorder='0',active=True));work=typed('work_items',dict(code='PACKAGE-WORK',name='合成原套餐检查作业',billing_unit='job',standard_fee_cents=601));account=master('accounts',dict(name='合成套餐原收款账户',account_type='bank',active=True))
        supplier=typed('suppliers',dict(code='PACKAGE-SUP',name='合成真实配件供应商',payment_terms_days=30));purchase=post(admin,'/api/procurement/orders',dict(request_id=key(),supplier_id=supplier['id'],reason='独立合成套餐实际采购备货',lines=[dict(item_id=item['id'],quantity_milli=5000,unit_cost_cents=123)]),201)
        purchase=post(admin,f"/api/procurement/orders/{purchase['id']}/actions/approve",dict(request_id=key(),version=purchase['version'],values={}))
        post(admin,f"/api/procurement/orders/{purchase['id']}/actions/receive",dict(request_id=key(),version=purchase['version'],values=dict(lines=[dict(line_id=purchase['lines'][0]['id'],quantity_milli=5000)],evidence_id=proof(purchase['id'],'实际采购入库'))))
        identity=post(admin,'/api/group/identities/link',dict(request_id=key(),kind='customer',local_id=customer['id']),201);member=post(admin,'/api/group/members',dict(request_id=key(),identity_id=identity['identity_id']),201)['member']
        row=post(service,'/api/repair-orders',dict(request_id=key(),customer_id=customer['id'],plate='合成套A001',problem='实际检查与实际配件使用',due_date=date.today().isoformat()),201);cid=row['id'];route='repair-orders/'+str(cid);memberroute='repair-packages/'+str(member['id'])
        def current():return req(admin,'/api/repair-orders/'+str(cid))
        def contract():return req(admin,f"/api/repair-packages/members/{member['id']}/purchases")['items'][0]
        def handoff(taskkey,role,case_id=cid):
            task=next(t for t in req(admin,'/api/flow/cases/'+str(case_id))['tasks'] if t['key']==taskkey and t['status']=='open')
            if task['assignee_id']!=ids[role]:post(admin,'/api/flow/tasks/'+str(task['id'])+'/assign',dict(version=task['version'],assignee_id=ids[role],reason='明确实际合成员工接手'))
        def act(p,name):p.locator('[data-act=repair-action][data-key='+name+']').click()
        visit(service,'repair-packages');service.locator('[data-act=package-rule-new]').click();fill(service,'code','PACKAGE-UI');service.locator('#modal form > label > input[name=name]').fill('合成检查与三件配件组合');parts=service.locator('[data-package-component]')
        for i,name,spec,unit,qty,credit,paid in [(0,'实际检查作业','明确实际检查范围','job','1.000','6.01','4.01'),(1,'实际三件配件','原采购相同规格','件','3.000','10.00','7.01')]:
            el=parts.nth(i)
            for field,value in [('name',name),('specification',spec),('unit',unit),('quantity',qty),('credit',credit),('paid',paid)]:el.locator('[name='+field+']').fill(value)
        assert_fits_mobile(service);shots.append(take_screenshot(service,output,'01_explicit_frozen_components.png'));save_modal(service)
        visit(manager,'repair-packages');manager.locator('[data-act=package-rule-decide][data-key=approve]').click();fill(manager,'reason','独立主管核对各组件原价和退款条款');save_modal(manager)
        for component,source in [('component_1',work),('component_2',item)]:
            manager.locator('[data-act=package-map][data-key='+component+']').click();manager.locator('#modal [name=source]').select_option(index=1);fill(manager,'reason','本店确认实际项目规格单位');save_modal(manager)
        visit(service,memberroute);service.locator('[data-act=package-purchase]').click();fill(service,'sets','1');service.locator('#modal [name=source]').select_option(index=1);service.locator('#modal [name=rule]').select_option(index=1);save_modal(service);p=contract();assert p['status']=='proposed'
        fid=proof(cid,'本版套餐购买授权','authorization');visit(service,memberroute);service.locator('[data-act=package-purchase-action][data-key=authorize]').click();choose(service,'evidence_id',fid);save_modal(service)
        assert contract()['status']=='authorized';handoff('repair_package_pay_'+str(p['id']),'finance');fid=proof(cid,'套餐真实到账凭据','receipt')
        visit(finance,memberroute);finance.locator('[data-act=package-purchase-action][data-key=issue]').click();choose(finance,'account_id',account['id']);fill(finance,'reference','SYNTHETIC-PACKAGE-PURCHASE');choose(finance,'evidence_id',fid);save_modal(finance);assert contract()['status']=='issued'
        steps.append('服务顾问明确多组件原价及实物，主管独立批准和本地映射；顾问取得本版授权，财务在原账户只登记一次1102分真实购买')
        visit(service,memberroute);service.locator('[data-act=package-use]').first.click();save=service.locator('#modal button[type=submit]');save.click();expect(service.locator('#modal h2')).to_have_text('核对原套餐及新增自费');fill(service,'q1','2.000');service.locator('#package-extra-add').click();extra=service.locator('[data-package-extra]');extra.locator('[name=source]').select_option('0');extra.locator('[name=price]').fill('2.00');fill(service,'reason','本次检查加实际两件配件，第三件保留未用，另加自费二元');assert_fits_mobile(service);shots.append(take_screenshot(service,output,'02_original_components_and_extra_customer.png'));save_modal(service)
        q=current()['quotes'][-1];assert q['amount_cents']==1467;handoff('repair_price_'+str(q['id']),'manager');visit(manager,route);act(manager,'price_approve');fill(manager,'reason','独立核对原套餐与新增自费本版价格');save_modal(manager)
        fid=proof(cid,'本版实际作业配件新增自费授权','authorization');visit(service,route);act(service,'authorize');choose(service,'evidence_id',fid);save_modal(service)
        handoff('repair_work','technician');visit(tech,route);act(tech,'start');fill(tech,'result','实际按已授权组件开始施工');save_modal(tech)
        handoff('repair_issue','inventory');fid=proof(cid,'原配件实际发出');visit(inventory,route);act(inventory,'issue');inventory.locator('#modal [name=line_label]').select_option(index=1);fill(inventory,'quantity','2.000');choose(inventory,'evidence_id',fid);save_modal(inventory)
        visit(tech,route);act(tech,'finish');fill(tech,'result','实际检查与两件配件使用完毕');save_modal(tech)
        handoff('repair_quality','service');fid=proof(cid,'实际合格质检','inspection');visit(service,route);act(service,'quality');choose(service,'outcome','合格');fill(service,'result','实际完成作业与配件质量均合格');choose(service,'evidence_id',fid);save_modal(service)
        fid=proof(cid,'实际承担核对');visit(manager,route);act(manager,'allocate');fill(manager,'amount_customer','14.67');fill(manager,'labor_cost','1.00');choose(manager,'evidence',fid);save_modal(manager)
        fid=proof(cid,'实际原组件履约核销');visit(finance,route);finance.locator('[data-act=package-capture]').click();choose(finance,'evidence_id',fid);save_modal(finance);assert current()['customer_due_cents']==200
        fid=proof(cid,'新增自费实际到账','receipt');visit(finance,route);act(finance,'receive');fill(finance,'amount','2.00');choose(finance,'account_id',account['id']);fill(finance,'reference','SYNTHETIC-PACKAGE-EXTRA');choose(finance,'evidence_id',fid);save_modal(finance)
        fid=proof(cid,'客户实际接车');handoff('repair_release','service');visit(service,route);act(service,'release');choose(service,'evidence_id',fid);save_modal(service);assert current()['state']=='completed'
        assert [l['available_milli'] for l in contract()['lots']]==[0,1000];steps.append('五个员工按真实报价、价格复核、本版授权、实际领料、施工、质检和核销办理；核销原权益868分P，仅另收新增自费200分，保留一件原配件未用')
        fid=proof(cid,'未用一件客户退款申请');visit(service,memberroute);service.locator('[data-act=package-purchase-action][data-key=refund_request]').click();service.locator('#modal [name=component]').select_option(index=1);fill(service,'quantity','1.000');fill(service,'reason','客户明确未使用第三件退原分摊款');choose(service,'evidence_id',fid);save_modal(service)
        visit(manager,memberroute);manager.locator('[data-act=package-refund][data-key=approve]').click();fill(manager,'reason','独立核对未用原组件和原价尾数');save_modal(manager)
        fid=proof(cid,'未用原账户真实退款','receipt');visit(finance,memberroute);finance.locator('[data-act=package-refund][data-key=pay]').click();choose(finance,'account_id',account['id']);fill(finance,'reference','SYNTHETIC-PACKAGE-UNUSED-REFUND');choose(finance,'evidence_id',fid);save_modal(finance)
        final=contract();assert final['refunds'][0]['amount_cents']==234 and final['refunds'][0]['status']=='executed';assert_fits_mobile(finance);shots.append(take_screenshot(finance,output,'03_employee_original_unused_refund.png'))
        assert not errors,errors
        return dict(status='passed',mode='real-Windows-Chrome-HTTP',viewport='390x844',synthetic_only=True,steps=steps,screenshots=shots,javascript_errors=errors,purchase_cash_cents=1102,extra_cash_cents=200,unused_refund_cents=234,recognized_package_cents=868,boundaries=['独立临时库随机端口；未触碰8000','主档及初始库存由真实注册接口合成；套餐购买/履约/退款业务由五岗位页面办理','售后实物原退与跨店竞争由独立API专项覆盖'])
    except Exception:
        for role,p in employees.items():take_screenshot(p,output,'failure_'+role+'.png')
        raise
    finally:
        for context in contexts:context.close()

if __name__=='__main__':harness.exercise=exercise;harness.main()
