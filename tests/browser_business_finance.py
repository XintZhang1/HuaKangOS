"""Independent store employees confirm advances, split receipts and corrections on Chrome."""
import secrets,re
from datetime import date
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request,request,login_page,navigate,save_modal,take_screenshot,assert_fits_mobile

def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screenshots=[]
    def page(width=390):
        ctx=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(ctx);p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440);service=page();finance=page();manager=page()
    try:
        login_page(admin,base,'admin',password);two=checked_request(admin,'/api/stores','POST',{'code':'BF-B','name':'财务验收乙店','active':True},status=201)['id']
        for role,p in [('service',service),('finance',finance),('manager',manager)]:
            secret=secrets.token_urlsafe(24);checked_request(admin,'/api/users','POST',{'username':'bf-'+role,'display_name':'财务验收'+role,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role},{'store_id':two,'role':role}]},status=201)
            login_page(p,base,'bf-'+role,secret);p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24);p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'bf-'+role,changed)
        def master(kind,values):return checked_request(admin,'/api/flow/master/'+kind,'POST',{'values':values},status=201)
        customer=master('customers',{'name':'独立财务合成客户','phone':'13900000123','contact_allowed':True,'note':''});account=master('accounts',{'name':'财务验收实际账户','account_type':'bank','active':True})
        item=master('items',{'sku':'BF-ITEM','name':'财务来源合成精品','unit':'件','reorder':'0','active':True});supplier=checked_request(admin,'/api/masters/suppliers','POST',{'request_id':secrets.token_hex(16),'values':{'code':'BF-SUP','name':'合成供应商'}},status=201)
        def upload_api(case_id,category='evidence'):
            result=admin.evaluate('''async a=>{const f=new FormData();f.append('category',a.category);f.append('file',new Blob(['synthetic proof'],{type:'text/plain'}),'source.txt');const t=document.cookie.split('; ').find(x=>x.startsWith('dealer_csrf='))?.split('=')[1];const r=await fetch('/api/flow/cases/'+a.id+'/files',{method:'POST',headers:{'X-CSRF-Token':t,'X-Store-ID':'1'},body:f});return {status:r.status,body:await r.json()};}''',{'id':case_id,'category':category});assert result['status']==200,result;return result['body']['id']
        purchase=checked_request(admin,'/api/procurement/orders','POST',{'request_id':secrets.token_hex(16),'supplier_id':supplier['id'],'reason':'合成实际库存来源','lines':[{'item_id':item['id'],'quantity_milli':2000,'unit_cost_cents':100}]},status=201)
        for action,values in [('approve',{}),('receive',{'evidence_id':upload_api(purchase['id']),'lines':[{'line_id':purchase['lines'][0]['id'],'quantity_milli':2000}]})]:purchase=checked_request(admin,f"/api/procurement/orders/{purchase['id']}/actions/{action}",'POST',{'request_id':secrets.token_hex(16),'version':purchase['version'],'values':values})
        sources=[]
        for _ in range(2):
            sale=checked_request(admin,'/api/retail/orders','POST',{'request_id':secrets.token_hex(16),'customer_id':customer['id'],'discount_cents':0,'lines':[{'item_id':item['id'],'quantity_milli':1000,'unit_price_cents':500,'installation_unit_price_cents':0}]},status=201)
            for action,values in [('approve',{'minimum_total_cents':0,'allow_below_minimum':False,'reason':'复核原精品价格'}),('authorize',{'revision':1,'evidence_id':upload_api(sale['id'],'authorization')})]:sale=checked_request(admin,f"/api/retail/orders/{sale['id']}/actions/{action}",'POST',{'request_id':secrets.token_hex(16),'version':sale['version'],'values':values})
            sources.append(sale)
        def visit(p,route,title='业务财务结算'):
            p.goto(base+'/?v='+secrets.token_hex(4));expect(p.locator('#main h1')).to_have_text('我的工作');navigate(p,route,title)
        def fill(p,name,value):
            control=p.locator('#modal [name='+name+']');control.select_option(label=str(value)) if control.evaluate('(e)=>e.tagName')=='SELECT' else control.fill(str(value))
        def create(p,key,fields=None,advance_id=None):
            visit(p,'business-finance/'+str(customer['id']));selector=f'[data-act=business-finance-create][data-key={key}]'+(f'[data-id="{advance_id}"]' if advance_id else '')
            p.locator(selector).click()
            for name,value in (fields or {}).items():fill(p,name,value)
            fill(p,'reason','客户确认本次原款与业务事项');assert_fits_mobile(p);save_modal(p);expect(p).to_have_url(re.compile(r'#business-finance-order/\d+'));return int(p.url.split('/')[-1])
        def act(p,case_id,key,values=None):
            visit(p,'business-finance-order/'+str(case_id),'财务业务办理');p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option('receipt')
            name=key+secrets.token_hex(3)+'.txt';p.locator('#modal [name=file]').set_input_files({'name':name,'mimeType':'text/plain','buffer':('本人实际办理的合成凭据 '+name).encode()});save_modal(p)
            fid=next(f['id'] for f in checked_request(admin,'/api/flow/cases/'+str(case_id))['files'] if f['name']==name)
            p.locator(f'[data-act=business-finance-action][data-key={key}]').click();p.locator('#modal [name=evidence_id]').select_option(str(fid));fill(p,'reason','本人核对当前独立批准及真实银行凭据')
            for name,value in (values or {}).items():fill(p,name,value)
            assert_fits_mobile(p);save_modal(p)
        order=create(service,'advance',{'amount':'6.00'});act(finance,order,'execute',{'account_id':account['name'],'reference':'BF-ADVANCE-ACTUAL'})
        advances=checked_request(admin,'/api/business-finance/advances?customer_id='+str(customer['id']))['items'];assert advances[0]['balance_cents']==600
        application=create(service,'advance_apply',{'amount':'2.00','source':sources[0]['number']+' · 5.00元'},advances[0]['id']);act(manager,application,'approve');act(finance,application,'execute')
        assert checked_request(admin,'/api/retail/orders/'+str(sources[0]['id']))['totals']['advance_credit_cents']==200
        screenshots.append(take_screenshot(finance,output,'01_approved_original_advance.png'));steps.append('服务顾问建立6元实际预收；财务确认一笔现金，独立店长批准2元占额后财务抵用原精品')
        statement=create(finance,'statement');act(manager,statement,'approve');act(finance,statement,'collect',{'account_id':account['name'],'reference':'BF-ONE-CASH-TWO-SOURCES'})
        result=checked_request(admin,'/api/business-finance/orders/'+str(statement));assert len(result['batches'])==1 and len(result['allocations'])==2 and sum(a['amount_cents'] for a in result['allocations'])==800
        screenshots.append(take_screenshot(finance,output,'02_one_receipt_two_sources.png'));steps.append('财务按冻结客户账单用一笔8元真实到账分配两个原单，各原单客户未收正确清零')
        correction=create(finance,'correction',{'original':next(r for r in checked_request(admin,'/api/business-finance/receipts?customer_id='+str(customer['id']))['items'] if r['cash_id']==result['batches'][0]['cash_id'])['business_date']+' · '+account['name']+' · BF-ONE-CASH-TWO-SOURCES · 8.00元','account_id':account['name'],'reference':'BF-CORRECT-ONLY','allocation_'+str(sources[0]['id']):'3.00','allocation_'+str(sources[1]['id']):'4.00'})
        act(manager,correction,'approve');act(finance,correction,'execute');assert checked_request(admin,'/api/retail/orders/'+str(sources[1]['id']))['totals']['receivable_cents']==100
        screenshots.append(take_screenshot(finance,output,'03_append_original_correction.png'));steps.append('财务提出原8元误记应为7元，另一位店长批准后追加冲正及正确分配，原款保持并恢复1元原业务应收')
        principal=next(r for r in checked_request(admin,'/api/business-finance/receipts?customer_id='+str(customer['id']))['items'] if r.get('source_kind')=='advance')
        principal_label=principal['business_date']+' · '+account['name']+' · BF-ADVANCE-ACTUAL · 6.00元'
        adjusted=create(finance,'stored_correction',{'original':principal_label,'amount':'5.00','account_id':account['name'],'reference':'BF-ADVANCE-CORRECTED'})
        act(manager,adjusted,'approve');act(finance,adjusted,'execute')
        assert checked_request(admin,'/api/business-finance/advances?customer_id='+str(customer['id']))['items'][0]['balance_cents']==300
        screenshots.append(take_screenshot(finance,output,'04_advance_original_correction.png'));steps.append('手机财务将原预收误记6元更正为5元，店长独立批准；原已抵用2元保留，可退余额变为3元')
        effective=next(r for r in checked_request(admin,'/api/business-finance/receipts?customer_id='+str(customer['id']))['items'] if not r.get('source_kind'))
        voided=create(finance,'correction',{'original':effective['business_date']+' · '+account['name']+' · BF-CORRECT-ONLY · 7.00元'})
        act(manager,voided,'approve');act(finance,voided,'execute')
        expect(finance.locator('#main')).to_contain_text('不生成零元收款')
        assert checked_request(admin,'/api/retail/orders/'+str(sources[1]['id']))['totals']['cash_paid_cents']==0
        screenshots.append(take_screenshot(finance,output,'05_zero_false_receipt.png'));steps.append('完整误登记以全零正确分配申请并独立批准，追加冲正不生成零元到账，不冒充客户实际退款')
        identity=checked_request(admin,'/api/group/identities/link','POST',{'request_id':secrets.token_hex(16),'kind':'customer','local_id':customer['id']},status=201)
        member=checked_request(admin,'/api/group/members','POST',{'request_id':secrets.token_hex(16),'identity_id':identity['identity_id']},status=201)['member']
        topup=checked_request(admin,'/api/membership/orders','POST',{'request_id':secrets.token_hex(16),'customer_id':customer['id'],'purpose':'topup','values':{'amount_cents':200},'reason':'真实浏览器合成会员原充值'},status=201)
        checked_request(finance,'/api/membership/orders/'+str(topup['case']['id'])+'/actions/execute','POST',{'request_id':secrets.token_hex(16),'version':topup['order']['version'],'case_version':topup['case']['version'],'member_version':topup['member']['version'],'values':{'account_id':account['id'],'reference':'BF-MEMBER-ORIGINAL','evidence_id':upload_api(topup['case']['id'],'receipt'),'reason':'本人核对会员实际到账'}})
        original_member=next(r for r in checked_request(admin,'/api/business-finance/receipts?customer_id='+str(customer['id']))['items'] if r.get('source_kind')=='member')
        corrected_member=create(finance,'stored_correction',{'original':original_member['business_date']+' · '+account['name']+' · BF-MEMBER-ORIGINAL · 2.00元','amount':'1.00','account_id':account['name'],'reference':'BF-MEMBER-CORRECTED'})
        act(manager,corrected_member,'approve');act(finance,corrected_member,'execute')
        assert checked_request(admin,'/api/group/members/'+str(member['id']))['member']['balance_cents']==100
        screenshots.append(take_screenshot(finance,output,'06_member_original_correction.png'));steps.append('财务从独立会员原充值创建误记更正，另一位店长批准后原2元与冲正保留，有效本金为1元')
        refund=create(service,'advance_refund',{'amount':'3.00'},advances[0]['id']);act(manager,refund,'approve');act(finance,refund,'execute',{'account_id':account['name'],'reference':'BF-ORIGINAL-REFUND'})
        assert checked_request(admin,'/api/business-finance/advances?customer_id='+str(customer['id']))['items'][0]['balance_cents']==0
        assert request(finance,'/api/business-finance/orders/'+str(statement),store=two)['status']==404
        steps.append('更正后的未用3元原预收独立批准后真实退原账户；乙店无法读取甲店财务办理与凭据')
        # A distinct synthetic warehouse return supplies the original supplier receivable.
        returned_item=master('items',{'sku':'BF-RETURN-ITEM','name':'原其他入库退回合成物资','unit':'件','reorder':'0','active':True})
        def typed(kind,values):return checked_request(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':values},status=201)
        warehouse=typed('warehouses',{'code':'BF-RETURN-WH','name':'超收退款验收仓','warehouse_type':'materials'})
        location=typed('locations',{'code':'BF-RETURN-LOC','name':'超收退款验收库位','warehouse_id':warehouse['id']})
        def warehouse_case(operation,quantity,**values):
            return checked_request(admin,'/api/warehouse/cases','POST',{'request_id':secrets.token_hex(16),'operation':operation,'item_id':returned_item['id'],'quantity_milli':quantity,'reason':'全合成其他入库及原物退回','recipient':'合成供应方','due_date':date.today().isoformat(),'locations':[],**values},status=201)
        def warehouse_action(row,key,**values):
            return checked_request(admin,f"/api/warehouse/cases/{row['id']}/commands/{key}",'POST',{'request_id':secrets.token_hex(16),'version':row['version'],'values':{'evidence_id':upload_api(row['id'],'receipt' if key=='approve' and row['operation']=='other_in' else 'evidence'),**values}})
        activation=warehouse_case('activate',0,locations=[{'location_id':location['id'],'quantity_milli':0}]);warehouse_action(activation,'approve')
        incoming=warehouse_case('other_in',1000,destination_location_id=location['id']);incoming=warehouse_action(incoming,'approve',value_cents=400);incoming=warehouse_action(incoming,'execute')
        returned=warehouse_case('other_in_return',1000,source_location_id=location['id'],original_move_id=incoming['stock_moves'][0]['id']);returned=warehouse_action(returned,'approve');returned=warehouse_action(returned,'execute')
        original_return=checked_request(finance,'/api/business-finance/orders','POST',{'request_id':secrets.token_hex(16),'customer_id':None,'purpose':'other_return','values':{'stock_move_id':returned['stock_moves'][0]['id'],'source_version':returned['version'],'supplier_id':supplier['id'],'amount_cents':400},'reason':'供应方确认退货应退原款4元'},status=201)['case']['id']
        act(manager,original_return,'approve');act(finance,original_return,'collect',{'amount':'4.00','account_id':account['name'],'reference':'BF-SUPPLIER-ORIGINAL'})
        def create_from_source(key,fields):
            visit(finance,'business-finance-order/'+str(original_return),'财务业务办理');finance.locator(f'[data-act=business-finance-create][data-key={key}]').click()
            for name,value in fields.items():fill(finance,name,value)
            fill(finance,'reason','供应方确认最终目标及应退原收款');assert_fits_mobile(finance);save_modal(finance)
            expect(finance).to_have_url(re.compile(r'#business-finance-order/\d+'));return int(finance.url.split('/')[-1])
        reduced=create_from_source('other_return_adjust',{'amount':'1.00'});act(manager,reduced,'approve');act(finance,reduced,'execute')
        visit(finance,'business-finance-order/'+str(original_return),'财务业务办理');expect(finance.locator('#main')).to_contain_text('超收应退')
        assert checked_request(admin,'/api/business-finance/orders/'+str(original_return))['return_target']['overpayment_cents']==300
        screenshots.append(take_screenshot(finance,output,'07_supplier_target_overpayment.png'));steps.append('财务将已实际到账4元的供应方目标独立更正为1元，原到账保留并显示3元超收待退')
        refund_source=checked_request(admin,'/api/business-finance/orders/'+str(original_return))['supplier_refund_sources'][0]
        actual_refund=create_from_source('other_return_refund',{'source':account['name']+' · BF-SUPPLIER-ORIGINAL · 本笔可退3.00元','amount':'3.00'})
        act(manager,actual_refund,'approve');act(finance,actual_refund,'execute',{'reference':'BF-SUPPLIER-ACTUAL-REFUND'})
        outcome=checked_request(admin,'/api/business-finance/orders/'+str(original_return))
        assert outcome['order']['status']=='completed' and outcome['return_target']['received_cents']==100 and outcome['return_target']['overpayment_cents']==0
        screenshots.append(take_screenshot(finance,output,'08_supplier_original_cash_refund.png'));steps.append('店长独立批准3元原款退款，手机财务自动预填原账户并登记真实退款，原收入与实际支出分别保留')
        # Prepare actual original goods and refunds through registered domain APIs;
        # the new correction itself is entered/reviewed/executed by real employee UI.
        target=sources[1]
        def retail_action(key,values):
            current=checked_request(admin,'/api/retail/orders/'+str(target['id']))
            return checked_request(admin,f"/api/retail/orders/{target['id']}/actions/{key}",'POST',{'request_id':secrets.token_hex(16),'version':current['version'],'values':values})
        target=retail_action('receive',{'amount_cents':500,'account_id':account['id'],'reference':'BF-PARTIAL-ORIGINAL','evidence_id':upload_api(target['id'],'receipt')})
        original_payment=next(p for p in target['payments'] if p['reference']=='BF-PARTIAL-ORIGINAL')
        target=retail_action('dispatch',{'evidence_id':upload_api(target['id'])});target=retail_action('accept',{'evidence_id':upload_api(target['id'])})
        def return_half():
            nonlocal target
            target=retail_action('return_request',{'reason':'合成原精品部分退货','evidence_id':upload_api(target['id']),'lines':[{'dispatch_id':target['dispatches'][0]['id'],'quantity_milli':500}]})
            ret=target['returns'][-1]
            target=retail_action('return_approve',{'return_id':ret['id'],'return_version':ret['version'],'reason':'独立核对原退货'})
            ret=next(r for r in target['returns'] if r['id']==ret['id'])
            target=retail_action('return_receive',{'return_id':ret['id'],'return_version':ret['version'],'passed':True,'result':'原商品实际检查通过','evidence_id':upload_api(target['id'],'inspection')})
        return_half()
        target=retail_action('refund',{'original_payment_id':original_payment['id'],'account_id':account['id'],'amount_cents':250,'reference':'BF-PARTIAL-ACTUAL-REFUND','evidence_id':upload_api(target['id'],'receipt')})
        correct_account=master('accounts',{'name':'财务更正后的实际账户','account_type':'bank','active':True})
        original=next(r for r in checked_request(admin,'/api/business-finance/receipts?customer_id='+str(customer['id']))['items'] if r['reference']=='BF-PARTIAL-ORIGINAL')
        label=original['business_date']+' · '+account['name']+' · BF-PARTIAL-ORIGINAL · 5.00元 · 已实退2.50元，剩余2.50元'
        partial=create(finance,'correction',{'original':label,'account_id':correct_account['name'],'reference':'BF-PARTIAL-CORRECTED','allocation_'+str(target['id']):'2.00'})
        act(manager,partial,'approve');act(finance,partial,'execute')
        outcome=checked_request(admin,'/api/business-finance/orders/'+str(partial))
        assert outcome['partial_correction']['refunded_cents']==250 and outcome['partial_correction']['corrected_amount_cents']==450 and outcome['partial_correction']['corrected_net_cents']==200
        expect(finance.locator('#main')).to_contain_text('已经真实退款 2.50 元保留原记录')
        screenshots.append(take_screenshot(finance,output,'09_preserve_refund_correct_remaining.png'));steps.append('已实退2.50元的原5元业务款，手机财务只分配正确剩余2元，独立批准后总原款更正为4.50元；原退款不重做')
        target=checked_request(admin,'/api/retail/orders/'+str(target['id']));return_half()
        successor=next(p for p in target['payments'] if p['direction']=='in' and p['reference']=='BF-PARTIAL-CORRECTED')
        target=retail_action('refund',{'original_payment_id':successor['id'],'account_id':correct_account['id'],'amount_cents':200,'reference':'BF-PARTIAL-LATER-REAL-REFUND','evidence_id':upload_api(target['id'],'receipt')})
        assert target['totals']['cash_paid_cents']==0
        visit(finance,'business-finance-order/'+str(partial),'财务业务办理');screenshots.append(take_screenshot(finance,output,'10_original_refund_and_later_effective_refund.png'));steps.append('余下原商品实际退货后，从更正后的原账户退剩余2元；第一次2.50元退款仍保留原账户')
        assert not errors,errors
        return {'mode':'real_http_chrome','file_scan_mode':'structure_only','viewport':'390x844','checks_passed':len(steps),'steps':steps,'javascript_errors':errors,'screenshots':screenshots}
    finally:
        for context in contexts:context.close()

if __name__=='__main__':harness.exercise=exercise;harness.main()
