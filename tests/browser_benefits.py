"""Real mobile Chromium: frozen coupon purchase, cross-store use and approved refund."""
import secrets
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import (checked_request, request, login_page, navigate, save_modal,
    create_repair_source, take_screenshot, assert_fits_mobile)


def exercise(browser,base,initial_password,output):
    contexts=[];errors=[];screenshots=[];steps=[]
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN')
        contexts.append(context);p=context.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440);finance=page();manager=page()
    try:
        login_page(admin,base,'admin',initial_password)
        two=checked_request(admin,'/api/stores','POST',{'code':'BEN-B','name':'权益验收乙店','active':True},status=201)['id']
        for role,p in [('finance',finance),('manager',manager)]:
            password=secrets.token_urlsafe(24)
            checked_request(admin,'/api/users','POST',{'username':'benefit-'+role,'display_name':'权益验收'+role,
                'role':role,'password':password,'store_roles':[{'store_id':1,'role':role},{'store_id':two,'role':role}]},status=201)
            login_page(p,base,'benefit-'+role,password)
            p.locator('#modal [name=current_password]').fill(password)
            changed=secrets.token_urlsafe(24);p.locator('#modal [name=new_password]').fill(changed);save_modal(p)
            login_page(p,base,'benefit-'+role,changed)
        a,b=create_repair_source(admin,1),create_repair_source(admin,two)
        linked=checked_request(admin,'/api/group/identities/link','POST',{'request_id':secrets.token_hex(16),
            'kind':'customer','local_id':a['case']['customer_id']},status=201)
        member=checked_request(admin,'/api/group/members','POST',{'request_id':secrets.token_hex(16),
            'identity_id':linked['identity_id']},status=201)['member']
        checked_request(admin,'/api/group/identities/link','POST',{'request_id':secrets.token_hex(16),
            'kind':'customer','local_id':b['case']['customer_id'],'identity_id':linked['identity_id']},store=two,status=201)
        def visit(p,setup):
            p.goto(base+'/?visit='+secrets.token_hex(4))
            p.locator('#store').select_option(str(setup['store']))
            expect(p.locator('#main h1')).to_have_text('我的工作')
            p.wait_for_function('(sid)=>String(state.store)===sid && location.hash==="#work"',arg=str(setup['store']))
            navigate(p,f"benefits/{setup['case']['customer_id']}/{setup['case']['id']}",'集团权益')
        def detail(setup):
            return checked_request(admin,'/api/group/benefits/members?customer_id='+str(setup['case']['customer_id']),store=setup['store'])
        visit(admin,a);admin.locator('[data-act=benefit-rule]').click()
        admin.locator('#modal [name=code]').fill('BROWSER-COUPON')
        admin.locator('#modal [name=name]').fill('跨店固定额消费券')
        admin.locator('#modal [name=stores]').fill('1,'+str(two))
        admin.locator('#modal [name=credit]').fill('10')
        admin.locator('#modal [name=settlement]').fill('8')
        admin.locator('#modal [name=sale]').fill('8')
        save_modal(admin)
        r=checked_request(admin,'/api/group/benefits/rules')['items'][0]
        assert r['credit_cents_per_unit']==1000 and r['sale_cents_per_unit']==800
        steps.append('集团管理员页面发布跨店固定券规则；售价8元、抵扣10元、履约门店承担2元优惠')
        visit(finance,a)
        assert not finance.locator('[data-act=benefit-rule]').count()
        finance.locator('[data-act=benefit-action][data-key=purchase]').click()
        finance.locator('#modal [name=units]').fill('3')
        finance.locator('#modal [name=account_id]').select_option(str(a['account_id']))
        finance.locator('#modal [name=reference]').fill('BENEFIT-BROWSER-PAID')
        finance.locator('#modal [name=evidence_id]').select_option(str(a['evidence_id']))
        finance.locator('#modal [name=reason]').fill('客户实际支付24元购买三张消费券')
        assert_fits_mobile(finance);save_modal(finance)
        assert detail(a)['wallets'][0]['balance_units']==3
        steps.append('财务员工手机页面登记实际24元购券收款，生成3张独立券；本金余额不改变')
        visit(finance,b)
        finance.locator('[data-act=benefit-action][data-key=reserve]').click()
        finance.locator('#modal [name=units]').fill('9')
        finance.locator('#modal [name=evidence_id]').select_option(str(b['evidence_id']))
        finance.locator('#modal [name=reason]').fill('合成检验超量请求拒绝')
        finance.locator('#modal button[type=submit]').click()
        expect(finance.locator('#modal .formerror')).to_contain_text('权益不足')
        assert_fits_mobile(finance)
        screenshots.append(take_screenshot(finance,output,'01_benefit_mobile_overuse_refused.png'))
        finance.locator('#modal [name=units]').fill('1');save_modal(finance)
        assert detail(b)['wallets'][0]['reserved_units']==1
        finance.locator('[data-act=benefit-action][data-key=capture]').click()
        finance.locator('#modal [name=evidence_id]').select_option(str(b['evidence_id']))
        finance.locator('#modal [name=reason]').fill('已核对本次客户维修消费实际使用一张')
        save_modal(finance)
        assert detail(b)['wallets'][0]['balance_units']==2
        assert_fits_mobile(finance)
        screenshots.append(take_screenshot(finance,output,'02_benefit_mobile_cross_store_capture.png'))
        steps.append('乙店财务超量占额收到中文拒绝，修正后占用并实际核销一张；不产生乙店现金')
        visit(finance,a)
        finance.locator('[data-act=benefit-action][data-key=refund_request]').click()
        finance.locator('#modal [name=units]').fill('1')
        finance.locator('#modal [name=evidence_id]').select_option(str(a['evidence_id']))
        finance.locator('#modal [name=reason]').fill('客户申请退回一张未使用消费券');save_modal(finance)
        assert not finance.locator('[data-act=benefit-action][data-key=refund_approve]').count()
        visit(manager,a);manager.locator('[data-act=benefit-action][data-key=refund_approve]').click()
        manager.locator('#modal [name=reason]').fill('独立店长核对原购券与客户申请');save_modal(manager)
        assert detail(a)['wallets'][0]['reserved_units']==1
        steps.append('原店财务申请未用券部分退款，独立店长批准后占用一张，避免再次消费')
        visit(finance,a);finance.locator('[data-act=benefit-action][data-key=refund]').click()
        finance.locator('#modal [name=account_id]').select_option(str(a['account_id']))
        finance.locator('#modal [name=reference]').fill('BENEFIT-BROWSER-REFUND')
        finance.locator('#modal [name=evidence_id]').select_option(str(a['evidence_id']))
        finance.locator('#modal [name=reason]').fill('实际原账户已退款8元');save_modal(finance)
        final=detail(a);assert final['wallets'][0]['balance_units']==1 and final['wallets'][0]['reserved_units']==0
        assert final['member']['balance_cents']==0
        cash=checked_request(admin,'/api/records/cash')['items']
        benefit_cash=[x for x in cash if x['category'].startswith('benefit_')]
        assert len(benefit_cash)==2 and sum(x['amount_cents']*(1 if x['direction']=='in' else -1) for x in benefit_cash)==1600
        assert_fits_mobile(finance)
        screenshots.append(take_screenshot(finance,output,'03_benefit_mobile_original_refund.png'))
        steps.append('原账户实际退款8元；现金净16元，余1张未用，乙店已核销1张，原本金仍为0')
        assert request(finance,'/api/group/benefits/rules','POST',{'request_id':secrets.token_hex(16),'values':{k:v for k,v in r.items() if k not in ['id','issuer_store_id','rule_version']}})['status']==403
        assert not errors,errors
        return {'mode':'real Chromium browser HTTP','passed':len(steps),'steps':steps,'javascript_errors':errors,'screenshots':screenshots,
            'limitations':['合成数据与本地HTTP，不替代生产HTTPS','本场景验证消费券手机闭环；套餐混合付款在API集成测试覆盖']}
    except Exception:
        take_screenshot(finance,output,'failure_finance.png');take_screenshot(admin,output,'failure_admin.png');raise
    finally:
        for context in contexts:context.close()


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
