"""Real Chrome employee approval and original member price authorization, isolated DB."""
import secrets
from datetime import date,timedelta
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request as req,request,login_page,save_modal,take_screenshot,assert_fits_mobile

def exercise(browser,base,password,output):
    contexts=[];employees={};errors=[];steps=[];shots=[]
    def page(width=390):
        c=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(c);p=c.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440)
    try:
        login_page(admin,base,'admin',password)
        def post(p,path,v,status=200):return req(p,path,'POST',v,status=status)
        def typed(kind,v):return post(admin,'/api/masters/'+kind,dict(request_id=secrets.token_hex(16),values=v),201)
        def rawproof(p,cid,label,category='evidence'):
            r=p.evaluate('''async({id,label,category})=>{const f=new FormData();f.append('category',category);f.append('file',new Blob([label],{type:'text/plain'}),label+'.txt');const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];const r=await fetch('/api/flow/cases/'+id+'/files',{method:'POST',headers:{'X-CSRF-Token':token,'X-Store-ID':'1'},body:f});return {status:r.status,body:await r.json()};}''',dict(id=cid,label=label,category=category));assert r['status']==200,r;return r['body']['id']
        def visit(p,route):p.goto(base+'/?trial='+secrets.token_hex(4)+'#'+route);expect(p.locator('#main h1')).to_be_visible()
        def fill(p,name,value):p.locator('#modal [name='+name+']').fill(str(value))
        def choose(p,name,value):p.locator('#modal [name='+name+']').select_option(str(value))
        def upload(p,cid,label,category='evidence'):
            p.locator('[data-act=upload]').click();choose(p,'category',category);p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('仅合成本次实际原件 '+label).encode()});save_modal(p);expect(p.locator('#main')).to_contain_text(label+'.txt')
            return next(f['id'] for f in req(admin,'/api/flow/cases/'+str(cid))['files'] if f['name']==label+'.txt')
        for role,key in [('manager','manager1'),('manager','manager2'),('service','service'),('finance','finance')]:
            secret=secrets.token_urlsafe(24);post(admin,'/api/users',dict(username='price-'+key,display_name='价格验收'+key,role=role,password=secret,store_roles=[dict(store_id=1,role=role)]),201)
            p=page();login_page(p,base,'price-'+key,secret);fill(p,'current_password',secret);changed=secrets.token_urlsafe(24);fill(p,'new_password',changed);save_modal(p);login_page(p,base,'price-'+key,changed);employees[key]=p
        manager,approver,service,finance=[employees[k] for k in ('manager1','manager2','service','finance')]
        customer=post(admin,'/api/flow/master/customers',dict(values=dict(name='会员原价合成客户',phone='13900009696',contact_allowed=True,note='')),201)
        work=typed('work_items',dict(code='PRICE-WORK',name='明确会员维修工时',billing_unit='job',standard_fee_cents=10000));tier=typed('member_tiers',dict(code='PRICE-REF',name='旧九折参考主档',discount_basis_points=9000))
        identity=post(admin,'/api/group/identities/link',dict(request_id=secrets.token_hex(16),kind='customer',local_id=customer['id']),201);post(admin,'/api/group/members',dict(request_id=secrets.token_hex(16),identity_id=identity['identity_id']),201)
        membership=post(admin,'/api/membership/rules',dict(request_id=secrets.token_hex(16),values=dict(code='PRICE-GRADE',name='明确会期等级',enabled=True,allowed_store_ids=[1],validity_months=12,fee_cents=0,fee_owner='collecting_store',refund_policy='before_start',points_enabled=False,points_numerator=1,points_denominator_fen=100)),201)
        renew=post(service,'/api/membership/orders',dict(request_id=secrets.token_hex(16),customer_id=customer['id'],purpose='renew',values=dict(rule_id=membership['id']),reason='合成原会期与真实会员身份'),201)
        for p,key in [(manager,'approve'),(finance,'execute')]:
            current=req(admin,'/api/membership/orders/'+str(renew['case']['id']));post(p,f"/api/membership/orders/{renew['case']['id']}/actions/{key}",dict(request_id=secrets.token_hex(16),version=current['order']['version'],case_version=current['case']['version'],member_version=current['member']['version'],values=dict(evidence_id=rawproof(p,renew['case']['id'],'原会期'+key),reason='本人核对原会期事实')))
        visit(manager,'member-pricing');manager.locator('[data-act=member-price-new]').click();fill(manager,'code','PRICE-LOCAL');fill(manager,'name','本店工时八折实际规则');choose(manager,'membership_rule',membership['id']);choose(manager,'tier',tier['id']);expect(manager.locator('#modal [name=basis_points]')).to_have_value('9000');fill(manager,'basis_points','8000');choose(manager,'source',work['id']);choose(manager,'enabled','true');fill(manager,'ends_on',(date.today()+timedelta(days=30)).isoformat());choose(manager,'stack_mode','exclusive_benefits');fill(manager,'reason','公司明确工时八折，会员价不叠加券包，本金可付款');assert_fits_mobile(manager);shots.append(take_screenshot(manager,output,'01_explicit_rule_reference_is_not_automatic.png'));save_modal(manager)
        r=req(admin,'/api/member-pricing/rules')['items'][0];route='member-pricing/'+str(r['id']);cid=r['case_id']
        def rule_action(p,key,label):
            visit(p,route);fid=upload(p,cid,label);p.locator('[data-act=member-price-action][data-key='+key+']').click();fill(p,'reason',label+'，本人核对公司规则');choose(p,'evidence_id',fid)
        rule_action(manager,'submit','本人原价格提交');save_modal(manager)
        rule_action(manager,'approve','申请人自批必须拒绝');manager.locator('#modal button[type=submit]').click();expect(manager.locator('#modal .formerror')).to_contain_text('申请人不能自批');shots.append(take_screenshot(manager,output,'02_independent_approval_refusal.png'))
        rule_action(approver,'approve','另一主管独立批准八折');assert_fits_mobile(approver);save_modal(approver)
        steps.append('主管页面明确引用旧九折参考但逐项批准八折和互斥规则；本人自批被中文错误拒绝，另一主管凭独立原件批准')
        def newrepair():return post(service,'/api/repair-orders',dict(request_id=secrets.token_hex(16),customer_id=customer['id'],plate='合成价A001',problem='合成会员工时服务',due_date=date.today().isoformat()),201)
        def current(row):return req(admin,'/api/repair-orders/'+str(row['id']))
        def quote_ui(row):
            visit(service,'repair-orders/'+str(row['id']));service.locator('[data-act=repair-action][data-key=quote]').click();choose(service,'member_pricing_rule',r['id']);choose(service,'source','work:'+str(work['id']));fill(service,'price','100.00');fill(service,'discount','0.03');fill(service,'reason','仅对本次明确工时按八折，人工优惠三分另列');assert_fits_mobile(service);save_modal(service)
        def approve_quote(row):
            visit(manager,'repair-orders/'+str(row['id']));manager.locator('[data-act=repair-action][data-key=price_approve]').click();fill(manager,'reason','本店主管确认本版实际价格');save_modal(manager)
        def consent(row,label):
            visit(service,'repair-orders/'+str(row['id']));fid=upload(service,row['id'],label,'authorization');service.locator('[data-act=repair-action][data-key=authorize]').click();choose(service,'evidence_id',fid)
        first=newrepair();quote_ui(first);assert current(first)['quotes'][-1]['amount_cents']==7997;approve_quote(first);consent(first,'原八折客户本版授权');save_modal(service);assert current(first)['amount_cents']==7997
        assert_fits_mobile(service);shots.append(take_screenshot(service,output,'03_employee_frozen_member_quote.png'));steps.append('服务顾问在实际报价页明确选择本店规则：100元工时八折减人工3分，冻结79.97元；价格审批及客户本版原件授权均由员工页面完成')
        second=newrepair();quote_ui(second);approve_quote(second)
        disabled=post(admin,'/api/member-pricing/rules',dict(request_id=secrets.token_hex(16),code=r['code'],name='独立停用原规则',enabled=False,membership_rule_id=membership['id'],starts_on=date.today().isoformat(),ends_on=(date.today()+timedelta(days=30)).isoformat(),stack_mode='exclusive_benefits',reason='公司停用本价格的新授权',scopes=[]),201)
        for p,key in [(admin,'submit'),(manager,'approve')]:
            d=req(admin,'/api/member-pricing/rules/'+str(disabled['id']));post(p,f"/api/member-pricing/rules/{d['id']}/actions/{key}",dict(request_id=secrets.token_hex(16),version=d['case_version'],values=dict(reason='本人核对价格停用',evidence_id=rawproof(p,d['case_id'],'价格停用'+key))))
        consent(second,'停用后不能补认客户授权');service.locator('#modal button[type=submit]').click();expect(service.locator('#modal .formerror')).to_contain_text('规则未生效');assert_fits_mobile(service);shots.append(take_screenshot(service,output,'04_rule_changed_before_authorization_refused.png'))
        assert current(first)['amount_cents']==7997 and not current(second)['quotes'][-1]['authorized'];assert request(service,'/api/member-pricing/rules')['status']==403
        report=req(finance,'/api/flow/analytics');assert report['metrics']['current_authorized_member_discount_cents']==2000 and report['metrics']['cash_in_cents']==0
        steps.append('已批准停用版本阻止旧报价补授权，已授权79.97元原价保持；服务岗位不能读价格规则后台，财务只统计当前已授权20元折让，现金仍为零')
        assert not errors,errors
        return dict(status='passed',mode='real-Windows-Chrome-HTTP',viewport=390,synthetic_only=True,passed=steps,javascript_errors=errors,screenshots=shots,authorized_quote_cents=7997,member_discount_cents=2000,actual_cash_cents=0)
    except Exception:
        for name,p in employees.items():take_screenshot(p,output,'failure_'+name+'.png')
        raise
    finally:
        for c in contexts:c.close()
if __name__=='__main__':harness.exercise=exercise;harness.main()
