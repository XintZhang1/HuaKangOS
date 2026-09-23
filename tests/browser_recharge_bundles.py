"""Real 390px employee Chrome: frozen combination, cross-store use and refund."""
import secrets, re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request, request, login_page, navigate, save_modal, take_screenshot, assert_fits_mobile, create_repair_source


def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screenshots=[]
    def page(width=390):
        ctx=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(ctx)
        p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440);service=page();finance=page();manager=page()
    try:
        login_page(admin,base,'admin',password)
        two=checked_request(admin,'/api/stores','POST',{'code':'RB-B','name':'组合验收乙店','active':True},status=201)['id']
        for role,p in [('service',service),('finance',finance),('manager',manager)]:
            secret=secrets.token_urlsafe(24)
            checked_request(admin,'/api/users','POST',{'username':'rb-'+role,'display_name':'组合验收'+role,'role':role,'password':secret,
                'store_roles':[{'store_id':1,'role':role},{'store_id':two,'role':role}]},status=201)
            login_page(p,base,'rb-'+role,secret);p.locator('#modal [name=current_password]').fill(secret)
            changed=secrets.token_urlsafe(24);p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'rb-'+role,changed)
        a,z=create_repair_source(admin,1),create_repair_source(admin,two)
        identity=checked_request(admin,'/api/group/identities/link','POST',{'request_id':secrets.token_hex(16),'kind':'customer','local_id':a['case']['customer_id']},status=201)
        checked_request(admin,'/api/group/members','POST',{'request_id':secrets.token_hex(16),'identity_id':identity['identity_id']},status=201)
        checked_request(admin,'/api/group/identities/link','POST',{'request_id':secrets.token_hex(16),'kind':'customer','local_id':z['case']['customer_id'],'identity_id':identity['identity_id']},store=two,status=201)
        gift_rules=[]
        for kind,name in [('bonus','组合赠送金额'),('points','组合积分'),('coupon','组合消费券'),('package','组合服务套餐')]:
            values={'code':'RB-'+kind,'name':name,'kind':kind,'allowed_store_ids':[1,two],
                'credit_cents_per_unit':1 if kind in {'bonus','points'} else 100,'settlement_cents_per_unit':0,'sale_cents_per_unit':0,
                'exchange_points_per_unit':0,'refund_policy':'none','discount_bearer':'service_store','validity_days':365,
                'service_code':'RB-SERVICE' if kind=='package' else ''}
            gift_rules.append(checked_request(admin,'/api/group/benefits/rules','POST',{'request_id':secrets.token_hex(16),'values':values},status=201))
        def visit(p,route,title='会员充值组合套餐',sid=1):
            p.goto(base+'/?visit='+secrets.token_hex(4));expect(p.locator('#main h1')).to_have_text('我的工作')
            old=p.locator('#store').element_handle();p.locator('#store').select_option(str(sid));p.wait_for_function('(e)=>!e.isConnected',arg=old)
            expect(p.locator('#main h1')).to_have_text('我的工作');navigate(p,route,title)
        def fill(p,key,value):
            control=p.locator('#modal [name='+key+']')
            if control.get_attribute('type')=='checkbox':control.check() if value else control.uncheck()
            elif control.evaluate('(e)=>e.tagName')=='SELECT':control.select_option(label=str(value))
            else:control.fill(str(value))
        visit(admin,'recharge-bundle-rules','充值组合规则');admin.locator('[data-act=bundle-rule]').click()
        assert not admin.locator('#modal [name=enabled]').is_checked()
        for key,value in {'code':'MOBILE-COMBO','name':'合成三份充值组合','principal':'10.00','store_1':True,'store_'+str(two):True,
                          'sale_ends_on':str(datetime.now(ZoneInfo('Asia/Shanghai')).date()+timedelta(days=30)),
                          'refund_terms':'已向客户说明赠品用后不可拆单份退款，只退原批次完整份额','enabled':True}.items():fill(admin,key,value)
        for rule in gift_rules:
            fill(admin,'gift_'+rule['kind'],f"{rule['name']} · {rule['code']} · 版本1")
            fill(admin,'units_'+rule['kind'],{'bonus':'1.00','points':'10','coupon':'2','package':'1'}[rule['kind']])
        save_modal(admin);bundle=checked_request(admin,'/api/recharge-bundles/rules')['items'][0]
        assert bundle['enabled'] and len(bundle['components'])==4
        steps.append('管理员按门店名配置四类赠品和有效期，默认关闭，明确条款后发布启用冻结版本')
        def current():return checked_request(admin,'/api/recharge-bundles/purchases?customer_id='+str(a['case']['customer_id']))
        def create(p,key,shares,purchase_id=None):
            visit(p,'recharge-bundles/'+str(a['case']['customer_id']))
            p.locator('[data-act=bundle-create][data-key='+key+']'+(f'[data-id="{purchase_id}"]' if purchase_id else '')).click()
            if key=='purchase':fill(p,'rule',f"{bundle['name']} · {bundle['code']} · 版本1")
            fill(p,'shares',shares);fill(p,'terms_accepted',True);fill(p,'reason','已向客户明确说明原批次赠品使用后的整份退款条件')
            expect(p.locator('#modal')).to_contain_text('不能拆单份退款');assert_fits_mobile(p);save_modal(p)
            expect(p).to_have_url(re.compile(r'#recharge-bundle-order/\d+'));return int(p.url.split('/')[-1])
        def act(p,key,case_id,expected_account=None):
            visit(p,'recharge-bundle-order/'+str(case_id),'充值组合办理')
            if key in {'execute','approve'}:
                p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option('receipt')
                name='本人组合'+key+secrets.token_hex(3)+'.txt';p.locator('#modal [name=file]').set_input_files({'name':name,'mimeType':'text/plain','buffer':('合成实际条款及收退款凭据 '+name).encode()});save_modal(p)
                fid=next(f['id'] for f in checked_request(admin,'/api/flow/cases/'+str(case_id))['files'] if f['name']==name)
            p.locator('[data-act=bundle-action][data-key='+key+']').click()
            if key in {'execute','approve'}:p.locator('#modal [name=evidence_id]').select_option(str(fid))
            if key=='execute':
                if expected_account is not None:expect(p.locator('#modal [name=account_id]')).to_have_value(str(expected_account))
                else:p.locator('#modal [name=account_id]').select_option(str(a['account_id']))
                fill(p,'reference','RB-REAL-'+secrets.token_hex(8))
            fill(p,'reason','本人已核对已确认条款、原批次完整赠品及实际银行凭据');assert_fits_mobile(p);save_modal(p)
        purchase_case=create(service,'purchase',3);act(finance,'execute',purchase_case)
        purchase=current()['items'][0];assert current()['member']['balance_cents']==3000 and purchase['refundable_shares']==3
        assert_fits_mobile(finance);screenshots.append(take_screenshot(finance,output,'01_four_gifts_one_actual_receipt.png'))
        steps.append('服务顾问手机说明整份条件并申请3份；财务真实收30元，只有一笔本金现金，四类赠品各自发行')
        visit(finance,f"benefits/{z['case']['customer_id']}/{z['case']['id']}",'集团权益',two)
        wallet=next(w for w in checked_request(admin,'/api/group/benefits/members?customer_id='+str(z['case']['customer_id']),store=two)['wallets'] if w['rule']['kind']=='coupon')
        finance.locator(f'[data-act=benefit-action][data-key=reserve][data-id="{wallet["id"]}"]').click()
        fill(finance,'units',1);finance.locator('#modal [name=evidence_id]').select_option(str(z['evidence_id']));fill(finance,'reason','本人核对客户本次实际维修使用一张');save_modal(finance)
        finance.locator('[data-act=benefit-action][data-key=capture]').click();finance.locator('#modal [name=evidence_id]').select_option(str(z['evidence_id']));fill(finance,'reason','本人核对客户本次实际维修核销');save_modal(finance)
        assert current()['items'][0]['refundable_shares']==2
        visit(service,'recharge-bundles/'+str(a['case']['customer_id']));expect(service.locator('#main')).to_contain_text('当前最多可退 2 个完整份额')
        assert_fits_mobile(service);screenshots.append(take_screenshot(service,output,'02_original_batch_partial_use.png'))
        steps.append('乙店财务用于原维修并核销一张券，不新增现金；甲店即时显示原组合仅剩2个可退完整份额')
        rejected_case=create(service,'refund',1,purchase['id']);act(manager,'approve',rejected_case)
        assert current()['member']['reserved_cents']==1000
        act(service,'cancel',rejected_case);assert current()['member']['reserved_cents']==0
        refund_case=create(service,'refund',2,purchase['id']);act(manager,'approve',refund_case)
        assert current()['member']['reserved_cents']==2000
        act(finance,'execute',refund_case)
        final=current();assert final['member']['balance_cents']==1000 and final['member']['reserved_cents']==0 and final['items'][0]['refundable_shares']==0
        facts=[x for x in checked_request(admin,'/api/records/cash')['items'] if x['category'].startswith('group_member_')]
        assert len(facts)==2 and sum(x['amount_cents']*(1 if x['direction']=='in' else -1) for x in facts)==1000
        assert request(finance,'/api/recharge-bundles/orders/'+str(purchase_case),store=two)['status']==404
        assert_fits_mobile(finance);screenshots.append(take_screenshot(finance,output,'03_original_account_refund_and_gift_recovery.png'))
        steps.append('不同店长批准后同时占本金和四类原赠品，撤销释放；再退2整份20元到原账户并原子回收赠品，乙店无权读取甲店凭据')
        second_case=create(service,'purchase',3);act(finance,'execute',second_case)
        def financial_action(p,key,case_id):
            visit(p,'business-finance-order/'+str(case_id),'财务业务办理')
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option('receipt')
            name='组合纠错'+key+secrets.token_hex(3)+'.txt';p.locator('#modal [name=file]').set_input_files({'name':name,'mimeType':'text/plain','buffer':('合成原组合误记及独立确认 '+name).encode()});save_modal(p)
            fid=next(x['id'] for x in checked_request(admin,'/api/flow/cases/'+str(case_id))['files'] if x['name']==name)
            p.locator(f'[data-act=business-finance-action][data-key={key}]').click();p.locator('#modal [name=evidence_id]').select_option(str(fid))
            fill(p,'reason','本人按原组合每份本金和四类原赠品核对误记');assert_fits_mobile(p);save_modal(p)
        def correct_bundle(amount,account_name):
            visit(finance,'business-finance/'+str(a['case']['customer_id']),'业务财务结算')
            origin=next(x for x in checked_request(admin,'/api/business-finance/receipts?customer_id='+str(a['case']['customer_id']))['items'] if x.get('bundle_purchase_id') and x['sources'][0]['case_id']==second_case)
            finance.locator('[data-act=business-finance-create][data-key=stored_correction]').click()
            label=f"{origin['business_date']} · {origin['account']} · {origin['reference']} · {origin['amount_cents']/100:.2f}元 · {origin['bundle_name']}（每份{origin['bundle_principal_per_share']/100:.2f}元）"
            for key,value in {'original':label,'amount':amount,'account_id':account_name,'reference':'RB-FIX-'+secrets.token_hex(8),'reason':'银行及客户确认原组合误记，原赠品同份纠正'}.items():fill(finance,key,value)
            assert_fits_mobile(finance);save_modal(finance);case_id=int(finance.url.split('/')[-1])
            financial_action(manager,'approve',case_id);financial_action(finance,'execute',case_id);return case_id
        original_account=checked_request(admin,'/api/flow/master/accounts')['items']
        original_name=next(x['name'] for x in original_account if x['id']==a['account_id'])
        corrected=correct_bundle('20.00',original_name)
        updated=checked_request(admin,'/api/recharge-bundles/orders/'+str(second_case))['purchase']
        assert updated['shares']==3 and updated['effective_shares']==updated['refundable_shares']==2
        expect(finance.locator('#main')).to_contain_text('更正为 2 份');expect(finance.locator('#main')).to_contain_text('原赠品')
        screenshots.append(take_screenshot(finance,output,'04_original_bundle_cash_and_gifts_corrected.png'))
        steps.append('另一本店原组合30元误记更正为20元，财务申请、独立店长批准后同步回收四类原赠品各一份；原发行和到期日保留')
        other=checked_request(admin,'/api/flow/master/accounts','POST',{'values':{'name':'组合更正有效原账户','account_type':'bank','active':True}},status=201)
        before=updated['components'];correct_bundle('20.00',other['name'])
        updated=checked_request(admin,'/api/recharge-bundles/orders/'+str(second_case))['purchase']
        assert updated['original_account']['id']==a['account_id'] and updated['effective_account']['id']==other['id']
        assert [(x['balance_units'],x['expires_on']) for x in updated['components']]==[(x['balance_units'],x['expires_on']) for x in before]
        visit(finance,'recharge-bundle-order/'+str(second_case),'充值组合办理');expect(finance.locator('#main')).to_contain_text('组合更正有效原账户')
        screenshots.append(take_screenshot(finance,output,'05_bundle_effective_original_account.png'))
        steps.append('同金额更正真实账户不再赠送权益，原账户和当前有效原账户同时可查，赠品数量与原有效期不变')
        actual=create(service,'refund',1,updated['id']);act(manager,'approve',actual);act(finance,'execute',actual,expected_account=other['id'])
        assert checked_request(admin,'/api/recharge-bundles/orders/'+str(second_case))['purchase']['refundable_shares']==1
        screenshots.append(take_screenshot(finance,output,'06_corrected_bundle_real_refund.png'))
        steps.append('更正后的组合再申请退一整份，财务手机自动预填当前有效原账户，独立批准后实际退10元并回收原赠品')
        assert not errors,errors
        return {'mode':'real_http_chrome','file_scan_mode':'structure_only','viewport':'390x844','checks_passed':len(steps),
                'steps':steps,'javascript_errors':errors,'screenshots':screenshots}
    except Exception:
        take_screenshot(admin,output,'failure_admin.png');take_screenshot(finance,output,'failure_finance.png');take_screenshot(service,output,'failure_service.png');raise
    finally:
        for ctx in contexts:ctx.close()


if __name__=='__main__':harness.exercise=exercise;harness.main()
