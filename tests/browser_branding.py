"""Actual Chrome visual acceptance with a new synthetic DB and random employees.

Reuses the owned temporary server harness; no live company service or DB is used.
Screenshots and the JSON result stay outside the repository. No mock UI data.
"""
import secrets
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login, take_screenshot


def exercise(browser, base, password, output):
    contexts=[];errors=[];screens=[];steps=[];req=harness.checked_request
    def page(width=1440,height=1000):
        context=browser.new_context(viewport={'width':width,'height':height},locale='zh-CN')
        contexts.append(context);p=context.new_page()
        p.on('pageerror',lambda e:errors.append(str(e)))
        return p
    def shot(p,name):
        harness.assert_fits_mobile(p)
        screens.append(take_screenshot(p,output,name))
    def upload(p,cid,category='evidence'):
        result=p.evaluate('''async ({cid,category})=>{
          const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];
          const data=new FormData();data.append('category',category);
          data.append('file',new Blob(['合成视觉验收：仅测试本次实际办理凭据'],{type:'text/plain'}),'合成凭据.txt');
          const r=await fetch('/api/flow/cases/'+cid+'/files',{method:'POST',headers:{'X-Store-ID':'1','X-CSRF-Token':token},body:data});
          return {status:r.status,body:await r.json()};
        }''',{'cid':cid,'category':category})
        assert result['status']==200,result
        return result['body']['id']
    def command(p,cid,key,values=None):
        row=req(p,'/api/procurement/orders/'+str(cid))
        return req(p,f'/api/procurement/orders/{cid}/actions/{key}','POST',
                   {'request_id':secrets.token_hex(16),'version':row['version'],'values':values or {}})
    desktop=page();mobile=page(390,844)
    try:
        desktop.goto(base);expect(desktop.locator('.loginform')).to_be_visible()
        expect(desktop.locator('.hk-logo')).to_have_count(2)
        assert desktop.locator('.loginform input').count()==2
        shot(desktop,'01_login_desktop.png')
        mobile.goto(base);expect(mobile.locator('.loginform')).to_be_visible()
        shot(mobile,'02_login_mobile.png')
        mobile.locator('[name=username]').fill('不存在的合成账号')
        mobile.locator('[name=password]').fill(secrets.token_urlsafe(20))
        mobile.locator('.loginform button[type=submit]').click()
        expect(mobile.locator('.formerror')).to_contain_text('用户名或密码错误')
        shot(mobile,'03_login_error_mobile.png')
        steps.append('真实桌面与390px登录；只有账号/密码，无虚构验证码或搜索；服务端中文登录失败保留输入与可重试按钮')

        harness.login_page(desktop,base,'admin',password)
        employees={}
        for role,title in [('inventory','合成仓库员工'),('finance','合成财务员工'),('manager','合成审批主管')]:
            secret=secrets.token_urlsafe(25)
            req(desktop,'/api/users','POST',{'username':'visual-'+role,'display_name':title,'role':role,'password':secret,
                'store_roles':[{'store_id':1,'role':role}],'can_group_summary':role=='manager'},status=201)
            p=page();employee_login(p,base,'visual-'+role,secret);employees[role]=p
        inventory,finance,manager=[employees[k] for k in ['inventory','finance','manager']]
        supplier=req(desktop,'/api/masters/suppliers','POST',{'request_id':secrets.token_hex(16),'values':{
            'code':'VISUAL-SUPPLIER','name':'合成门店物资供应商','payment_terms_days':30}},status=201)
        items=[req(desktop,'/api/flow/master/items','POST',{'values':{'sku':'VISUAL-'+str(i),'name':name,
            'unit':'件','reorder':'2','active':True}},status=201) for i,name in enumerate(['合成保养滤芯','合成车内清洁用品','合成精品脚垫'])]
        account=req(desktop,'/api/flow/master/accounts','POST',{'values':{'name':'合成采购结算账户','account_type':'bank','active':True}},status=201)
        orders=[]
        for item,cost in zip(items,[12500,3600,68000]):
            order=req(inventory,'/api/procurement/orders','POST',{'request_id':secrets.token_hex(16),
                'supplier_id':supplier['id'],'reason':'合成门店补货视觉验收',
                'lines':[{'item_id':item['id'],'quantity_milli':10000,'unit_cost_cents':cost}]},status=201)
            cid=order['id'];order=command(manager,cid,'approve');orders.append(cid)
            if len(orders)<3:
                evidence=upload(inventory,cid)
                order=command(inventory,cid,'receive',{'evidence_id':evidence,'lines':[{'line_id':order['lines'][0]['id'],'quantity_milli':6000}]})
        cid=orders[0];evidence=upload(finance,cid,'receipt')
        command(finance,cid,'pay',{'account_id':account['id'],'amount_cents':30000,'reference':'VISUAL-ACTUAL-PAYMENT','evidence_id':evidence})

        harness.navigate(inventory,'work','我的工作')
        inventory.locator('[data-act=refresh]').click()
        expect(inventory.locator('.work-table tbody tr')).not_to_have_count(0)
        assert req(inventory,'/api/procurement/payables',status=403)
        expect(inventory.locator('.nav a[href="#warehouse"]')).to_have_count(1)
        expect(inventory.locator('.nav a[href="#procurement"]')).to_have_count(1)
        expect(inventory.locator('.nav a[href="#analytics/overview"]')).to_have_count(0)
        shot(inventory,'04_inventory_work_desktop.png')
        inventory.set_viewport_size({'width':390,'height':844})
        expect(inventory.locator('.work-cards')).to_be_visible()
        shot(inventory,'05_inventory_work_mobile.png')
        inventory.locator('[data-act=menu]').click()
        expect(inventory.locator('.sidebar')).to_be_visible()
        inventory.locator('.nav summary',has_text='物资管理').click()
        shot(inventory,'06_inventory_navigation_mobile.png')
        inventory.locator('.nav a[href="#master/items"]').click()
        expect(inventory.locator('#main h1')).to_contain_text('物资')
        expect(inventory.locator('.sidebar')).not_to_be_visible()
        assert '库存成本' not in inventory.locator('#main').inner_text()
        shot(inventory,'07_inventory_catalog_mobile.png')
        steps.append('真实库管完成多单申请及部分验收；桌面待办表、手机办理卡、展开导航及物资目录可用，仍无财务报表及成本权限')

        harness.navigate(inventory,'procurement/'+str(orders[0]),'合成门店物资供应商 · 采购办理')
        inventory.locator('[data-act=procurement-action][data-key=receive]').click()
        line=req(inventory,'/api/procurement/orders/'+str(orders[0]))['lines'][0]
        inventory.locator('[name=quantity_'+str(line['id'])+']').fill('99')
        inventory.locator('#modal button[type=submit]').click()
        expect(inventory.locator('#modal .formerror')).to_contain_text('验收数量超过')
        shot(inventory,'08_inventory_refusal_mobile.png')
        inventory.locator('#modal [data-act=close]').first.click()

        harness.navigate(finance,'analytics/overview','数据可视化')
        expect(finance.locator('.chartarea svg').first).to_be_visible()
        assert req(finance,'/api/procurement/payables')['payable_cents']==66600
        shot(finance,'09_finance_analytics_desktop.png')
        finance.set_viewport_size({'width':390,'height':844})
        shot(finance,'10_finance_analytics_mobile.png')
        finance.locator('[data-act=logout]').click()
        expect(finance.locator('.loginform')).to_be_visible()
        assert finance.locator('#modal').inner_text()==''
        assert finance.locator('.loginform [name=password]').input_value()==''
        steps.append('财务实际分笔付款后图表展示真实合成台账；桌面与390px统计口径/日期/图表明细可读；退出清理旧数据和密码')
        assert not errors,errors
        return {'status':'passed','mode':'actual-chrome-http','synthetic_only':True,'steps':steps,
            'screenshots':screens,'javascript_errors':errors,'brand_sources':['example/real1.png','example/real3.jpg']}
    finally:
        for context in contexts:context.close()


if __name__=='__main__':
    harness.exercise=exercise;harness.main()
