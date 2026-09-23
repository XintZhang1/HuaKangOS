"""Real 390px Chrome finance reports, scoped source facts and actual CSV."""
import csv,io,re,secrets
from datetime import date,timedelta
from pathlib import Path
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login


def exercise(browser,base,password,output):
    contexts=[];errors=[];screens=[];steps=[];req=harness.checked_request
    def page(width=390):
        ctx=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(ctx);p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    def shot(p,name,selector):
        expect(p.locator('#toast')).not_to_have_class(re.compile('visible'),timeout=10000)
        target=p.locator(selector).first;target.scroll_into_view_if_needed();target.evaluate('(e)=>window.scrollBy(0,e.getBoundingClientRect().top-130)');harness.assert_fits_mobile(p)
        path=output/name;p.screenshot(path=str(path));screens.append(str(path))
    admin=page(1440)
    try:
        harness.login_page(admin,base,'admin',password)
        other=req(admin,'/api/stores','POST',{'code':'MV-B','name':'合成物资对照B店'},status=201)['id']
        admin.reload();expect(admin.locator('#store')).to_be_visible()
        secret=secrets.token_urlsafe(25);req(admin,'/api/users','POST',{'username':'mv-finance','display_name':'合成物资对照财务','role':'finance','password':secret,
            'store_roles':[{'store_id':1,'role':'finance'},{'store_id':other,'role':'finance'}],'can_group_summary':True},status=201)
        finance=page();employee_login(finance,base,'mv-finance',secret)
        def seed(store,code,accepted):
            admin.locator('#store').select_option(str(store))
            def post(path,v,status=200):return req(admin,path,'POST',v,store=store,status=status)
            def master(kind,v):return post('/api/flow/master/'+kind,{'values':v},201)
            def typed(kind,v):return post('/api/masters/'+kind,{'request_id':secrets.token_hex(16),'values':v},201)
            def proof(cid):
                title=req(admin,'/api/flow/cases/'+str(cid),store=store)['title'];harness.navigate(admin,'case/'+str(cid),title)
                admin.locator('[data-act=upload]').click();admin.locator('#modal [name=category]').select_option('authorization')
                admin.locator('#modal [name=file]').set_input_files({'name':'合成物资原件-'+secrets.token_hex(4)+'.txt','mimeType':'text/plain','buffer':'仅合成实际凭据'.encode()});harness.save_modal(admin)
                return req(admin,'/api/flow/cases/'+str(cid),store=store)['files'][-1]['id']
            item=master('items',dict(sku='MV-'+code,name='合成精品原成本'+code,unit='件',reorder='0',active=True))
            supplier=typed('suppliers',dict(code='MV-S-'+code,name='合成供货'+code))
            purchase=post('/api/procurement/orders',dict(request_id=secrets.token_hex(16),supplier_id=supplier['id'],reason='物资对照真实采购',lines=[dict(item_id=item['id'],quantity_milli=3000,unit_cost_cents=123)]),201)
            for action,values in [('approve',{}),('receive',{'lines':[dict(line_id=purchase['lines'][0]['id'],quantity_milli=3000)],'evidence_id':proof(purchase['id'])})]:
                purchase=post(f'/api/procurement/orders/{purchase["id"]}/actions/{action}',dict(request_id=secrets.token_hex(16),version=purchase['version'],values=values))
            customer=master('customers',dict(name='合成精品客户'+code,phone='1390000970'+str(store),contact_allowed=True,note='',confirm_new_customer=True))
            row=post('/api/retail/orders',dict(request_id=secrets.token_hex(16),customer_id=customer['id'],discount_cents=0,lines=[dict(item_id=item['id'],quantity_milli=2000,unit_price_cents=500,work_item_id=None,installation_unit_price_cents=0)]),201)
            def command(action,values):
                current=req(admin,'/api/retail/orders/'+str(row['id']),store=store)
                return post(f'/api/retail/orders/{row["id"]}/actions/{action}',dict(request_id=secrets.token_hex(16),version=current['version'],values=values))
            row=command('approve',dict(minimum_total_cents=0,reason='核对原冻结商品价格',allow_below_minimum=False))
            row=command('authorize',dict(revision=1,evidence_id=proof(row['id'])))
            row=command('dispatch',dict(evidence_id=proof(row['id'])))
            if accepted:row=command('accept',dict(evidence_id=proof(row['id'])))
            return row,item,command,proof
        one,item,command,proof=seed(1,'A',False)
        harness.navigate(finance,'material-value','物资收入成本对照')
        d=req(finance,'/api/material-value');assert d['metrics']['material_source_net_cents']==0 and d['metrics']['material_unfulfilled_cost_cents']==246
        shot(finance,'01_material_unfulfilled_finance_mobile.png','.panel:has(h2:text-is("当前已领未履约成本核对")) .work-cards .card')
        one=command('accept',dict(evidence_id=proof(one['id'])))
        two,item2,_,_=seed(other,'B',True)
        finance.reload();expect(finance.locator('#main h1')).to_have_text('物资收入成本对照')
        finance.locator('#material-value-filters [name=item_id]').select_option(str(item['id']));finance.locator('#material-value-filters button[type=submit]').click()
        expect(finance.locator('#material-value-filters [name=item_id]')).to_have_value(str(item['id']))
        d=req(finance,'/api/material-value?item_id='+str(item['id']));assert d['metrics']['material_source_net_cents']==1000 and d['metrics']['material_selected_goods_cost_cents']==246
        shot(finance,'02_material_goods_original_cost_mobile.png','.work-cards .card')
        with finance.expect_download() as event:finance.locator('[data-act=mv-export][data-key=material_goods]').first.click()
        exported=list(csv.reader(io.StringIO(Path(event.value.path()).read_text(encoding='utf-8-sig'))));t=d['tables']['material_goods']
        assert exported==[t['headers']]+[[str(v) for v in row['values']] for row in t['rows']]
        steps.append('财务在390px核对未接收商品仅列2.46元已领未履约；实际接收后商品10元、原成本2.46元，无需虚造收款；筛选及真实CSV与图表同源')
        finance.locator('#store').select_option(str(other));expect(finance).to_have_url(re.compile(r'#work$'))
        harness.navigate(finance,'material-value','物资收入成本对照');expect(finance.locator('#material-value-filters [name=item_id]')).to_have_value('')
        d=req(finance,'/api/material-value',store=other);assert d['metrics']['material_source_net_cents']==1000
        assert harness.request(finance,'/api/material-value?item_id='+str(item['id']),store=other)['status']==404
        expect(finance.locator('#main')).not_to_contain_text(one['number'])
        finance.locator('#store').select_option('all');expect(finance.locator('.identity .role')).to_have_text('集团汇总（只读）')
        harness.navigate(finance,'material-value','物资收入成本对照');expect(finance.locator('#main')).to_contain_text('合成物资对照B店')
        d=req(finance,'/api/material-value',store='all');assert d['metrics']['material_source_net_cents']==2000
        assert all(not r.get('route') for t in d['tables'].values() for r in t['rows'])
        shot(finance,'03_material_group_readonly_mobile.png','.panel:has(h2:text-is("相关原单期间对外金额核对")) .work-cards .card')
        steps.append('财务切B店立即清除A店筛选和原单；外店物资404。明确集团授权可汇总两店20元，原单办理入口全部隐藏')
        day=finance.evaluate('day()');finance.locator('#datefilters [name=date_from]').fill(day);finance.locator('#datefilters [name=date_to]').fill((date.fromisoformat(day)-timedelta(days=1)).isoformat());finance.locator('#datefilters button[type=submit]').click()
        expect(finance.locator('#main .notice.error')).to_contain_text('开始日期不能晚于结束日期');shot(finance,'04_material_invalid_period_mobile.png','.notice.error')
        finance.locator('#datefilters [name=date_to]').fill(day);finance.locator('#datefilters button[type=submit]').click();expect(finance.locator('#main .notice.error')).to_have_count(0)
        steps.append('错误期间中文拒绝并保留筛选，财务可在原页面改正；未显示截断或伪零统计')
        assert not errors,errors
        return dict(status='passed',mode='actual-chrome-http',steps=steps,screenshots=screens,javascript_errors=errors,synthetic_only=True)
    finally:
        for context in contexts:context.close()


if __name__=='__main__':harness.exercise=exercise;harness.main()
