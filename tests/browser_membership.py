"""Real employee Chrome: independent membership, cross-store cards and points debt."""
import secrets
import re
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request,request,login_page,navigate,save_modal,take_screenshot,assert_fits_mobile


def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screenshots=[]
    def page(width=390):
        ctx=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(ctx)
        p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440);service=page();finance=page();manager=page()
    try:
        login_page(admin,base,'admin',password)
        two=checked_request(admin,'/api/stores','POST',{'code':'MB-B','name':'会员验收乙店','active':True},status=201)['id']
        for role,p in [('service',service),('finance',finance),('manager',manager)]:
            secret=secrets.token_urlsafe(24);checked_request(admin,'/api/users','POST',{'username':'membership-'+role,'display_name':'会员验收'+role,'role':role,
                'password':secret,'store_roles':[{'store_id':1,'role':role},{'store_id':two,'role':role}]},status=201)
            login_page(p,base,'membership-'+role,secret);p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24)
            p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'membership-'+role,changed)
        def master(kind,values,sid=1):return checked_request(admin,'/api/flow/master/'+kind,'POST',{'values':values},store=sid,status=201)
        customers={sid:master('customers',{'name':'集团卡验收客户','phone':'13900000423','contact_allowed':True,'note':''},sid) for sid in [1,two]}
        identity=checked_request(admin,'/api/group/identities/link','POST',{'request_id':secrets.token_hex(16),'kind':'customer','local_id':customers[1]['id']},status=201)
        member=checked_request(admin,'/api/group/members','POST',{'request_id':secrets.token_hex(16),'identity_id':identity['identity_id']},status=201)['member']
        checked_request(admin,'/api/group/identities/link','POST',{'request_id':secrets.token_hex(16),'kind':'customer','local_id':customers[two]['id'],'identity_id':identity['identity_id']},store=two,status=201)
        account=master('accounts',{'name':'会员验收实际账户','account_type':'bank','active':True})
        pr=checked_request(admin,'/api/group/benefits/rules','POST',{'request_id':secrets.token_hex(16),'values':{'code':'MB-EARN','name':'合成消费积分','kind':'points','allowed_store_ids':[1,two],
            'credit_cents_per_unit':1,'settlement_cents_per_unit':0,'sale_cents_per_unit':0,'exchange_points_per_unit':0,'refund_policy':'none','discount_bearer':'service_store','validity_days':365,'service_code':''}},status=201)
        level=checked_request(admin,'/api/membership/rules','POST',{'request_id':secrets.token_hex(16),'values':{'code':'MB-LEVEL','name':'合成测试会员','enabled':True,'allowed_store_ids':[1,two],
            'validity_months':12,'fee_cents':0,'fee_owner':'collecting_store','refund_policy':'none','points_enabled':True,'points_numerator':1,'points_denominator_fen':100,'points_benefit_rule_id':pr['id']}},status=201)
        def visit(p,route,sid=1,title='会员卡与续会'):
            p.goto(base+'/?v='+secrets.token_hex(4));expect(p.locator('#main h1')).to_have_text('我的工作')
            previous=p.locator('#store').element_handle();p.locator('#store').select_option(str(sid))
            p.wait_for_function('(el)=>!el.isConnected',arg=previous)
            expect(p.locator('#main h1')).to_have_text('我的工作');navigate(p,route,title)
        def member_info(sid=1):return checked_request(admin,'/api/membership/members?customer_id='+str(customers[sid]['id']),store=sid)
        def create_ui(key,sid=1,fields=None,card=None):
            visit(service,'membership/'+str(customers[sid]['id']),sid)
            selector=f'[data-act=membership-create][data-key={key}]'+(f'[data-id="{card}"]' if card else '')
            service.locator(selector).click()
            for name,value in (fields or {}).items():
                control=service.locator('#modal [name='+name+']')
                if control.evaluate('(e)=>e.tagName')=='SELECT':control.select_option(label=value)
                else:control.fill(str(value))
            service.locator('#modal [name=reason]').fill('客户本人确认本次办理事项');save_modal(service)
            expect(service).to_have_url(re.compile(r'#membership-order/\d+'));return int(service.url.split('/')[-1])
        def upload(p,case_id,label,sid=1):
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option('evidence')
            p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('合成凭据：'+label).encode()});save_modal(p)
            return next(f['id'] for f in checked_request(admin,'/api/flow/cases/'+str(case_id),store=sid)['files'] if f['name']==label+'.txt')
        def act(p,case_id,key,sid=1,cash=False):
            visit(p,'membership-order/'+str(case_id),sid,'会员业务办理');fid=upload(p,case_id,'本人实际'+key+secrets.token_hex(3),sid)
            p.locator('[data-act=membership-action][data-key='+key+']').click();p.locator('#modal [name=evidence_id]').select_option(str(fid))
            p.locator('#modal [name=reason]').fill('本人核对客户授权与真实办理凭据')
            if cash:p.locator('#modal [name=account_id]').select_option(str(account['id']));p.locator('#modal [name=reference]').fill('MB-'+secrets.token_hex(6))
            assert_fits_mobile(p);save_modal(p)
        first=create_ui('card_issue');act(service,first,'execute');card=member_info()['cards'][0]
        lost=create_ui('card_loss',two,card=card['id']);act(service,lost,'execute',two)
        replacement=create_ui('card_replace',two,card=card['id']);act(service,replacement,'execute',two)
        assert [c['status'] for c in member_info(two)['cards']]==['active','replaced']
        assert request(service,'/api/membership/cards/lookup?number='+card['number'],store=two)['status']==404
        assert request(service,'/api/membership/orders/'+str(first),store=two)['status']==404
        visit(service,'membership/'+str(customers[two]['id']),two);assert_fits_mobile(service);screenshots.append(take_screenshot(service,output,'01_cross_store_card_replacement.png'))
        steps.append('服务顾问甲店发卡，乙店挂失并换补；原卡失效，外店原办理单仍不可读取')
        topup=create_ui('topup',fields={'amount':'123.45'});act(finance,topup,'execute',cash=True)
        assert member_info()['member']['balance_cents']==12345
        steps.append('独立会员单充值123.45元，财务凭本店实际账户和凭据确认，会员本金只入账一次')
        renewal=create_ui('renew',fields={'rule':f"{level['id']} · {level['name']} · 版本1"})
        act(manager,renewal,'approve');act(finance,renewal,'execute')
        assert member_info()['active_period_id']
        visit(service,'membership/'+str(customers[1]['id']));assert_fits_mobile(service);screenshots.append(take_screenshot(service,output,'02_independent_renewal.png'))
        steps.append('服务顾问申请明确规则，另一位店长复核，财务办理免费续会；有效期与积分规则留存')
        # Real API prerequisites only: no SQL or fake balances are used for points.
        item=master('items',{'sku':'MB-ITEM','name':'积分来源合成精品','unit':'件','reorder':'0','active':True})
        supplier=checked_request(admin,'/api/masters/suppliers','POST',{'request_id':secrets.token_hex(16),'values':{'code':'MB-SUP','name':'积分采购合成供应商'}},status=201)
        procurement=checked_request(admin,'/api/procurement/orders','POST',{'request_id':secrets.token_hex(16),'supplier_id':supplier['id'],'reason':'真实库存来源验收',
            'lines':[{'item_id':item['id'],'quantity_milli':2000,'unit_cost_cents':100}]},status=201)
        def api_upload(case_id):
            result=admin.evaluate('''async id=>{const f=new FormData();f.append('category','evidence');f.append('file',new Blob(['synthetic proof'],{type:'text/plain'}),'source.txt');const t=document.cookie.split('; ').find(x=>x.startsWith('dealer_csrf='))?.split('=')[1];let r=await fetch('/api/flow/cases/'+id+'/files',{method:'POST',headers:{'X-CSRF-Token':t,'X-Store-ID':'1'},body:f});return {status:r.status,body:await r.json()};}''',case_id)
            assert result['status']==200,result;return result['body']['id']
        for key,values in [('approve',{}),('receive',{'evidence_id':api_upload(procurement['id']),'lines':[{'line_id':procurement['lines'][0]['id'],'quantity_milli':2000}]})]:
            procurement=checked_request(admin,f"/api/procurement/orders/{procurement['id']}/actions/{key}",'POST',{'request_id':secrets.token_hex(16),'version':procurement['version'],'values':values})
        sale=checked_request(admin,'/api/retail/orders','POST',{'request_id':secrets.token_hex(16),'customer_id':customers[1]['id'],'discount_cents':0,
            'lines':[{'item_id':item['id'],'quantity_milli':2000,'unit_price_cents':500,'installation_unit_price_cents':0}]},status=201)
        fid=api_upload(sale['id'])
        def retail(key,values):
            nonlocal sale
            sale=checked_request(admin,f"/api/retail/orders/{sale['id']}/actions/{key}",'POST',{'request_id':secrets.token_hex(16),'version':sale['version'],'values':values});return sale
        retail('approve',{'minimum_total_cents':0,'allow_below_minimum':False,'reason':'核对积分来源实际报价'})
        # Authorization files remain separately classified, as the actual sales workflow requires.
        auth=admin.evaluate('''async id=>{const f=new FormData();f.append('category','authorization');f.append('file',new Blob(['synthetic authorization'],{type:'text/plain'}),'authorized.txt');const t=document.cookie.split('; ').find(x=>x.startsWith('dealer_csrf='))?.split('=')[1];let r=await fetch('/api/flow/cases/'+id+'/files',{method:'POST',headers:{'X-CSRF-Token':t,'X-Store-ID':'1'},body:f});return {status:r.status,body:await r.json()};}''',sale['id']);assert auth['status']==200
        retail('authorize',{'revision':1,'evidence_id':auth['body']['id']});retail('dispatch',{'evidence_id':fid})
        # Finance uses the real existing retail mobile flow to attest the actual receipt.
        visit(finance,'retail/'+str(sale['id']),title='精品销售 · '+sale['number'])
        finance.locator('[data-act=upload]').click();finance.locator('#modal [name=category]').select_option('receipt');finance.locator('#modal [name=file]').set_input_files({'name':'积分实际收款.txt','mimeType':'text/plain','buffer':b'synthetic actual receipt'});save_modal(finance)
        receipt=next(f['id'] for f in checked_request(admin,'/api/flow/cases/'+str(sale['id']))['files'] if f['name']=='积分实际收款.txt')
        finance.locator('[data-act=retail-action][data-key=receive]').click();finance.locator('#modal [name=amount]').fill('10.00');finance.locator('#modal [name=account_id]').select_option(str(account['id']));finance.locator('#modal [name=reference]').fill('MB-RETAIL-IN');finance.locator('#modal [name=evidence_id]').select_option(str(receipt));save_modal(finance)
        sale=checked_request(admin,'/api/retail/orders/'+str(sale['id']));retail('accept',{'evidence_id':fid})
        wallet=checked_request(admin,'/api/group/benefits/members?customer_id='+str(customers[1]['id']))['wallets'][0];assert wallet['balance_units']==10
        coupon=checked_request(admin,'/api/group/benefits/rules','POST',{'request_id':secrets.token_hex(16),'values':{'code':'MB-EXCHANGE','name':'合成积分兑换券','kind':'coupon','allowed_store_ids':[1,two],
            'credit_cents_per_unit':100,'settlement_cents_per_unit':0,'sale_cents_per_unit':0,'exchange_points_per_unit':1,'refund_policy':'none','discount_bearer':'service_store','validity_days':365,'service_code':''}},status=201)
        exchange=create_ui('exchange',fields={'wallet':f"{wallet['id']} · {wallet['rule']['name']} · 可用10",'units':'10','rule':f"{coupon['id']} · {coupon['name']} · 版本1"});act(finance,exchange,'execute')
        retail('return_request',{'reason':'客户要求原单部分退货','evidence_id':fid,'lines':[{'dispatch_id':sale['dispatches'][0]['id'],'quantity_milli':500}]})
        ret=sale['returns'][0];retail('return_approve',{'return_id':ret['id'],'return_version':ret['version'],'reason':'核对原单退货'});ret=sale['returns'][0]
        retail('return_receive',{'return_id':ret['id'],'return_version':ret['version'],'evidence_id':fid,'passed':True,'result':'实际检查可以入库'})
        assert member_info()['points_debt_units']==3
        visit(finance,'retail/'+str(sale['id']),title='精品销售 · '+sale['number']);finance.locator('[data-act=retail-action][data-key=refund]').click()
        finance.locator('#modal [name=account_id]').select_option(str(account['id']));finance.locator('#modal [name=reference]').fill('MB-RETAIL-REFUND');finance.locator('#modal [name=original]').select_option(index=1);finance.locator('#modal [name=evidence_id]').select_option(str(receipt));save_modal(finance)
        assert checked_request(admin,'/api/retail/orders/'+str(sale['id']))['totals']['refund_due_cents']==0
        visit(service,'membership/'+str(customers[1]['id']));expect(service.locator('#main')).to_contain_text('原消费退款待追回积分');assert_fits_mobile(service);screenshots.append(take_screenshot(service,output,'03_points_debt_after_actual_refund.png'))
        steps.append('已履约精品实收10元获10积分，财务兑换后部分原单退货；积分不足记3积分待追回，实际退款仍成功')
        assert not errors,errors
        return {'mode':'real_http_chrome','file_scan_mode':'structure_only','viewport':'390x844','checks_passed':len(steps),'steps':steps,'javascript_errors':errors,'screenshots':screenshots}
    except Exception as error:
        raise AssertionError(str(error)+'; browser errors: '+repr(errors)) from error
    finally:
        for context in contexts:context.close()


if __name__=='__main__':harness.exercise=exercise;harness.main()
