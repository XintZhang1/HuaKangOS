"""Actual Chrome employee/cookie/CSP warehouse acceptance on a fresh synthetic database."""
import secrets
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login,take_screenshot

API='/api/warehouse'
def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];screens=[];req=harness.checked_request
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(context);p=context.new_page();p.on('pageerror',lambda error:errors.append(str(error)));return p
    admin=page(1440)
    try:
        harness.login_page(admin,base,'admin',password)
        def typed(kind,v):return req(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':v},status=201)
        warehouse=typed('warehouses',{'code':'WH-SYNTH','name':'合成物资仓','warehouse_type':'materials'})
        a=typed('locations',{'code':'BIN-A','name':'合成甲库位','warehouse_id':warehouse['id']})['id'];b=typed('locations',{'code':'BIN-B','name':'合成乙库位','warehouse_id':warehouse['id']})['id']
        item=req(admin,'/api/flow/master/items','POST',{'values':{'sku':'BIN-SYNTH','name':'合成仓储物资','unit':'件','reorder':'0','active':True}},status=201)['id']
        people={}
        for role in ['inventory','manager','finance']:
            secret=secrets.token_urlsafe(26);req(admin,'/api/users','POST',{'username':'wh-'+role,'display_name':'合成仓储'+role,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},status=201)
            p=page();employee_login(p,base,'wh-'+role,secret);people[role]=p
        inventory,manager,finance=(people[k] for k in ['inventory','manager','finance'])
        def current(cid):return req(admin,API+'/cases/'+str(cid))
        def visit(p,cid):
            p.goto(base+'/?visit='+secrets.token_hex(4)+'#warehouse/'+str(cid))
            try:expect(p.locator('#main h1')).to_have_text(current(cid)['operation_label'],timeout=15000)
            except AssertionError:
                p.screenshot(path=str(output/'synthetic-failure.png'),full_page=True)
                raise AssertionError({'page':p.locator('body').inner_text(),'javascript_errors':errors,'screenshot':str(output/'synthetic-failure.png')})
        def upload(p,name,category='evidence'):
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category)
            p.locator('#modal [name=file]').set_input_files({'name':name+'.txt','mimeType':'text/plain','buffer':('纯合成实际仓储证明：'+name).encode()});harness.save_modal(p)
        def action(p,key):
            try:p.locator('[data-act=wh-action][data-key='+key+']').click(timeout=10000)
            except Exception:
                p.screenshot(path=str(output/'synthetic-action-failure.png'),full_page=True)
                raise AssertionError({'page':p.locator('body').inner_text(),'javascript_errors':errors,'screenshot':str(output/'synthetic-action-failure.png')})
            expect(p.locator('#modal')).to_be_visible()
        def new(op,qty=None,src=None,dest=None):
            harness.navigate(inventory,'warehouse','库位与仓储作业');inventory.locator('[data-act=wh-new][data-operation='+op+']').click()
            inventory.locator('#modal [name=item_id]').select_option(str(item))
            if qty is not None:inventory.locator('#modal [name=quantity]').fill(str(qty))
            if src:inventory.locator('#modal [name=source]').select_option(str(src))
            if dest:inventory.locator('#modal [name=destination]').select_option(str(dest))
            if inventory.locator('#modal [name=recipient]').count():inventory.locator('#modal [name=recipient]').fill('虚构合成班组')
            inventory.locator('#modal [name=reason]').fill('合成门店员工核对实物与原始凭据');harness.save_modal(inventory)
            row=req(admin,API+'/cases')['items'][0];expect(inventory.locator('#main h1')).to_have_text(row['operation_label']);return row['id']
        def approve(cid,value=None):
            visit(manager,cid);upload(manager,'合成主管核对凭据','receipt' if value is not None else 'evidence');action(manager,'approve')
            if value is not None:manager.locator('#modal [name=value]').fill(str(value))
            harness.save_modal(manager)
        def execute(cid):visit(inventory,cid);upload(inventory,'合成实际收发凭据');action(inventory,'execute');harness.save_modal(inventory)
        cid=new('activate',0);approve(cid);assert req(inventory,API+f'/items/{item}/stock')['enabled']
        incoming=new('other_in',10,dest=a);approve(incoming,'10.01');execute(incoming)
        assert 'value_cents' not in req(inventory,API+f'/items/{item}/stock')
        expect(inventory.locator('#main')).not_to_contain_text('10.01');harness.assert_fits_mobile(inventory)
        screens.append(take_screenshot(inventory,output,'01_warehouse_receipt_mobile.png'))
        steps.append('实际库管逐项启用真实库位并申请其他入库；主管按受限凭据核价，实际收货后才入账，库管看不到成本')
        move=new('local_move',7,src=a,dest=b);approve(move);visit(inventory,move);upload(inventory,'合成移库实际交接');action(inventory,'dispatch');harness.save_modal(inventory)
        assert req(inventory,API+f'/items/{item}/stock')['available_milli']==3000
        action(inventory,'accept');inventory.locator('#modal [name=quantity]').fill('8');inventory.locator('#modal button[type=submit]').click()
        expect(inventory.locator('#modal .formerror')).to_contain_text('超过本次尚在途');harness.assert_fits_mobile(inventory)
        screens.append(take_screenshot(inventory,output,'02_warehouse_over_accept_refusal.png'))
        inventory.locator('#modal [name=quantity]').fill('2');harness.save_modal(inventory)
        action(inventory,'reject_transit');inventory.locator('#modal [name=reason]').fill('剩余包装现场异常拒收');harness.save_modal(inventory)
        action(inventory,'return_transit');harness.save_modal(inventory);assert current(move)['state']=='completed'
        s=req(admin,API+f'/items/{item}/stock');assert s['quantity_milli']==10000 and s['value_cents']==1001
        steps.append('真实移库发出减少库位可用量，超量接收中文拒绝；部分接收后拒收余量并实际回原位，门店数量价值不变')
        count=new('count',src=a);approve(count);visit(inventory,count);upload(inventory,'合成现场实盘观察');action(inventory,'capture');inventory.locator('#modal [name=counted]').fill('7');harness.save_modal(inventory)
        later=new('other_in',2,dest=a);approve(later,'4.00');execute(later)
        visit(manager,count);action(manager,'post_count');harness.save_modal(manager)
        c=current(count)['count'];assert c['baseline_quantity_milli']==8000 and c['movement_bridge_milli']==2000 and c['current_book_milli']==9000
        screens.append(take_screenshot(manager,output,'03_warehouse_count_bridge_mobile.png'))
        steps.append('实盘围栏在提交观察后释放，期间追加实际入库，主管按原观察差额过账并能查看衔接流水')
        harness.navigate(finance,'warehouse-item/'+str(item),'物资真实库位');harness.assert_fits_mobile(finance)
        screens.append(take_screenshot(finance,output,'04_warehouse_ledger_mobile.png'))
        assert harness.request(finance,API+f'/cases/{count}/commands/post_count','POST',{'request_id':secrets.token_hex(16),'version':current(count)['version'],'values':{'evidence_id':1}})['status']==403
        assert not finance.locator('[data-act=wh-new]').count()
        steps.append('财务岗位只读原始库位流水与价值，无实际仓储办理权限；390像素页面可以读取和滚动明细')
        purchase=req(admin,'/api/flow/cases','POST',{'request_id':secrets.token_hex(16),'kind':'purchase','values':{'item_id':item,'quantity':'1','unit_cost':'2.01','supplier':'合成已有采购来源'}},status=201)
        purchase=req(admin,f'/api/flow/cases/{purchase["id"]}/actions/approve','POST',{'request_id':secrets.token_hex(16),'version':purchase['version'],'values':{}})
        inventory.goto(base+'/?visit='+secrets.token_hex(4)+'#case/'+str(purchase['id']));expect(inventory.locator('[data-act=upload]')).to_be_visible()
        upload(inventory,'合成原采购实际接收凭据');origin=req(inventory,'/api/flow/cases/'+str(purchase['id']));file=next(f for f in origin['files'] if not f['generated'])
        failed=harness.request(inventory,f'/api/flow/cases/{purchase["id"]}/actions/stock_in','POST',{'request_id':secrets.token_hex(16),'version':origin['version'],'values':{'evidence_id':file['id']}})
        assert failed['status']==409 and '真实库位' in failed['body']['detail']
        harness.navigate(inventory,'warehouse-allocation/'+str(purchase['id']),'准备物资库位');inventory.locator('[data-act=wh-allocate]').click()
        inventory.locator('#modal [name=quantity]').fill('1');inventory.locator('#modal [name=location]').select_option(str(b));inventory.locator('#modal [name=location_qty]').fill('1')
        harness.assert_fits_mobile(inventory);screens.append(take_screenshot(inventory,output,'05_warehouse_original_allocation.png'));harness.save_modal(inventory)
        origin=req(inventory,'/api/flow/cases/'+str(purchase['id']));req(inventory,f'/api/flow/cases/{purchase["id"]}/actions/stock_in','POST',{'request_id':secrets.token_hex(16),'version':origin['version'],'values':{'evidence_id':file['id']}})
        assert req(admin,API+f'/items/{item}/stock')['quantity_milli']==12000
        steps.append('原采购实际收发缺库位分配被拒绝；库管通过原单准备页明确精确数量与库位后一次实际过账')
        req(admin,'/api/stores','POST',{'code':'WH-B','name':'合成仓储乙店'},status=201)
        assert harness.request(admin,API+f'/items/{item}/stock',store='2')['status']==404
        assert harness.request(admin,API+'/cases',store='all')['status']==409
        assert not errors,errors
        return {'checks':len(steps),'steps':steps,'screenshots':screens,'javascript_errors':errors,'transport':'actual browser HTTP / cookies / CSP','data':'fresh synthetic database; randomized passwords not retained'}
    finally:
        for c in contexts:c.close()

if __name__=='__main__':harness.exercise=exercise;harness.main()
