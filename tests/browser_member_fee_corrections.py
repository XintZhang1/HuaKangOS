"""Real Chrome employees: same original fee correction and actual original refund."""
import secrets,re
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request,request,login_page,navigate,save_modal,take_screenshot,assert_fits_mobile


def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];shots=[];timestamp_checks=[]
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN',timezone_id='Asia/Shanghai');contexts.append(context)
        result=context.new_page();result.on('pageerror',lambda e:errors.append(str(e)));return result
    admin=page(1440);service=page();finance=page();manager=page()
    try:
        login_page(admin,base,'admin',password)
        two=checked_request(admin,'/api/stores','POST',{'code':'FEE-B','name':'续会费验收乙店','active':True},status=201)['id']
        for role,p in [('service',service),('finance',finance),('manager',manager)]:
            secret=secrets.token_urlsafe(24)
            checked_request(admin,'/api/users','POST',{'username':'fee-'+role,'display_name':'续会费验收'+role,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role},{'store_id':two,'role':role}]},status=201)
            login_page(p,base,'fee-'+role,secret);p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24)
            p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'fee-'+role,changed)
        def api(p,url,body=None):return checked_request(p,url,'POST' if body is not None else 'GET',body,status=201 if body is not None and url.endswith(('/orders','/rules')) else 200)
        def expected_time(value):
            stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
            if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
            local=stamp.astimezone(ZoneInfo('Asia/Shanghai'))
            return f'{local.year}/{local.month}/{local.day} {local:%H:%M:%S}'
        def verify_times(p,cid,endpoint):
            details=api(p,endpoint+str(cid));source=api(p,'/api/flow/cases/'+str(cid))
            rows=p.locator('.panel').filter(has=p.get_by_role('heading',name='办理记录',exact=True)).locator('tbody tr')
            expect(rows).to_have_count(len(details['events']))
            files={f['id']:f for f in source['files']}
            for index,event in enumerate(details['events']):
                expected=expected_time(event['occurred_at'])
                expect(rows.nth(index).locator('td').first).to_have_text(expected)
                record={'case_id':cid,'event_id':event['id'],'raw_event':event['occurred_at'],'displayed_event':expected}
                if event.get('evidence_id'):
                    asset=files[event['evidence_id']];file_time=expected_time(asset['created_at'])
                    card=p.locator('.filerecord').filter(has=p.get_by_text(asset['name'],exact=True))
                    expect(card.locator('.filetext p').first).to_contain_text(file_time)
                    record.update(file_id=asset['id'],raw_file=asset['created_at'],displayed_file=file_time)
                timestamp_checks.append(record)
        def master(kind,values):return checked_request(admin,'/api/flow/master/'+kind,'POST',{'values':values},status=201)
        customer=master('customers',{'name':'续会费全合成客户','phone':'13900000566','contact_allowed':True,'note':''})
        original=master('accounts',{'name':'原登记合成银行账户','account_type':'bank','active':True})
        correct=master('accounts',{'name':'经核对实际银行账户','account_type':'bank','active':True})
        identity=checked_request(admin,'/api/group/identities/link','POST',{'request_id':secrets.token_hex(16),'kind':'customer','local_id':customer['id']},status=201)
        checked_request(admin,'/api/group/members','POST',{'request_id':secrets.token_hex(16),'identity_id':identity['identity_id']},status=201)
        def rule(fee):return api(admin,'/api/membership/rules',{'request_id':secrets.token_hex(16),'values':{'code':'FEE-'+str(fee),'name':'合成会期'+str(fee),'enabled':True,'allowed_store_ids':[1],
            'validity_months':12,'fee_cents':fee,'fee_owner':'collecting_store','refund_policy':'before_start','points_enabled':False,'points_numerator':1,'points_denominator_fen':100,'points_benefit_rule_id':None}})
        free=rule(0);paid=rule(19900)
        def visit(p,route,title):
            p.goto(base+'/?v='+secrets.token_hex(4));expect(p.locator('#main h1')).to_have_text('我的工作');navigate(p,route,title)
        def fill(p,name,value):
            control=p.locator('#modal [name='+name+']')
            control.select_option(label=str(value)) if control.evaluate('(e)=>e.tagName')=='SELECT' else control.fill(str(value))
        def upload(p,cid):
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option('receipt');name='本次原款凭证'+secrets.token_hex(3)+'.txt'
            p.locator('#modal [name=file]').set_input_files({'name':name,'mimeType':'text/plain','buffer':('本人核对的合成原款凭据 '+name).encode()});save_modal(p)
            return next(f['id'] for f in api(admin,'/api/flow/cases/'+str(cid))['files'] if f['name']==name)
        def member_create(key,selected=None,period=None):
            visit(service,'membership/'+str(customer['id']),'会员卡与续会')
            selector=f'[data-act=membership-create][data-key={key}]'+(f'[data-id="{period}"]' if period else '')
            service.locator(selector).click()
            if selected:fill(service,'rule',f"{selected['id']} · {selected['name']} · 版本1")
            fill(service,'reason','客户明确同意原会员规则及此次办理');assert_fits_mobile(service);save_modal(service)
            expect(service).to_have_url(re.compile(r'#membership-order/\d+'));return int(service.url.split('/')[-1])
        def member_action(p,cid,key,bank=None,wrong=False):
            visit(p,'membership-order/'+str(cid),'会员业务办理');fid=upload(p,cid)
            p.locator(f'[data-act=membership-action][data-key={key}]').click();p.locator('#modal [name=evidence_id]').select_option(str(fid));fill(p,'reason','本人核对原规则及本次实际办理')
            if bank:fill(p,'account_id',bank['name']);fill(p,'reference','REAL-'+secrets.token_hex(6))
            if wrong:
                p.locator('#modal button[type=submit]').click();expect(p.locator('#modal .formerror')).to_contain_text('当前有效原账户');assert_fits_mobile(p)
                shots.append(take_screenshot(p,output,'03_wrong_original_account_refused.png'));fill(p,'account_id',correct['name'])
            assert_fits_mobile(p);save_modal(p)
        first=member_create('renew',free);member_action(manager,first,'approve');member_action(finance,first,'execute')
        renewal=member_create('renew',paid);member_action(manager,renewal,'approve');member_action(finance,renewal,'execute',original)
        before=api(finance,'/api/membership/members?customer_id='+str(customer['id']))
        visit(finance,'business-finance/'+str(customer['id']),'业务财务结算');finance.locator('[data-act=business-finance-create][data-key=fee_correction]').click()
        assert finance.locator('#modal [name=amount]').count()==0 and finance.locator('#modal [name=actual_business_date]').count()==0
        receipt=next(r for r in api(finance,'/api/business-finance/receipts?customer_id='+str(customer['id']))['items'] if r.get('source_kind')=='membership_fee')
        fill(finance,'original',f"{receipt['business_date']} · {receipt['account']} · {receipt['reference']} · 199.00元")
        fill(finance,'account_id',correct['name']);fill(finance,'reference','REAL-CORRECTED-FEE');fill(finance,'reason','同额原续会费实际为另一账户和凭证，原会期不变')
        assert_fits_mobile(finance);save_modal(finance);expect(finance).to_have_url(re.compile(r'#business-finance-order/\d+'));cid=int(finance.url.split('/')[-1])
        def finance_action(p,key):
            visit(p,'business-finance-order/'+str(cid),'财务业务办理');fid=upload(p,cid)
            p.locator(f'[data-act=business-finance-action][data-key={key}]').click();p.locator('#modal [name=evidence_id]').select_option(str(fid));fill(p,'reason','本人核对同额原款冻结账户和凭证');assert_fits_mobile(p);save_modal(p)
        finance_action(manager,'approve');shots.append(take_screenshot(manager,output,'01_independent_fee_approval.png'))
        finance_action(finance,'execute');expect(finance.locator('#main')).to_contain_text('会员、会期、等级及权益保持原记录')
        expect(finance.locator('#main')).to_contain_text('已追加同额登记更正（非退款）')
        assert api(finance,'/api/membership/members?customer_id='+str(customer['id']))==before
        verify_times(finance,cid,'/api/business-finance/orders/')
        shots.append(take_screenshot(finance,output,'02_same_fee_recording_completed.png'))
        steps.append('服务顾问原免费会期与199元未来续会，店长独立批准，财务确认；随后财务在390像素页面申请同额账户凭证更正，经理批准后财务执行，会期及权益逐项保持')
        visit(service,'business-finance/'+str(customer['id']),'业务财务结算');assert service.locator('[data-key=fee_correction]').count()==0
        assert request(service,'/api/business-finance/orders/'+str(cid))['status'] in {403,404}
        assert request(finance,'/api/business-finance/orders/'+str(cid),store=two)['status']==404
        actual=member_create('renew_refund',period=before['periods'][-1]['id']);member_action(manager,actual,'approve');member_action(finance,actual,'execute',original,wrong=True)
        expect(finance.locator('#main')).to_contain_text('原款退款依据已冻结')
        result=api(finance,'/api/membership/members?customer_id='+str(customer['id']));assert len(result['periods'])==1
        private=api(service,'/api/membership/orders/'+str(actual));basis=next(e for e in private['events'] if e['action']=='fee_refund_basis');assert basis['detail']=={'recorded':True} and basis['evidence_id'] is None
        report=api(finance,'/api/flow/analytics');assert (report['metrics']['cash_in_cents'],report['metrics']['cash_out_cents'],report['metrics']['membership_fee_net_cents'])==(19900,19900,0)
        verify_times(finance,actual,'/api/membership/orders/')
        assert_fits_mobile(finance);shots.append(take_screenshot(finance,output,'04_actual_refund_effective_account.png'))
        steps.append('服务顾问不能读财务更正原单，乙店无法读取；真实续会退款拒绝旧账户中文提示，再按有效原账户实际退款，现金收199退199且会费净额0，客服只见退款结果')
        assert not errors,errors
        return {'status':'passed','mode':'real-Windows-Chrome-HTTP','viewport':390,'browser_timezone':'Asia/Shanghai','synthetic_only':True,'passed':steps,'javascript_errors':errors,'screenshots':shots,'cash_in_cents':19900,'cash_out_cents':19900,'timestamp_checks':timestamp_checks}
    except Exception:
        for name,p in [('admin',admin),('service',service),('finance',finance),('manager',manager)]:
            take_screenshot(p,output,'failure_'+name+'.png')
            if p.locator('#modal .formerror').count():print(name,p.locator('#modal .formerror').inner_text())
        print('browser evidence:',output)
        raise
    finally:
        for context in contexts:context.close()


if __name__=='__main__':harness.exercise=exercise;harness.main()
