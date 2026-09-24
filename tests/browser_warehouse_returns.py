"""Real Chrome: original warehouse batch return by inventory employee, synthetic DB."""
import re,secrets,sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import expect
from tests import browser_huakangos as h

def choose(page,name,text):
    root=page.locator('#modal select[name="'+name+'"]').locator('..')
    root.locator('[data-lookup-query]').fill(text)
    option=root.get_by_role('option',name=re.compile(re.escape(text))).first
    expect(option).to_be_visible();option.click()

def proof(page,case_id,category='evidence'):
    result=page.evaluate('''async ({case_id,category})=>{
      const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];
      const data=new FormData();data.append('category',category);data.append('file',new Blob(['合成仓储原批次实际核对凭据'],{type:'text/plain'}),'合成凭据.txt');
      const result=await fetch('/api/flow/cases/'+case_id+'/files',{method:'POST',headers:{'X-CSRF-Token':token,'X-Store-ID':'1'},body:data});
      return {status:result.status,body:await result.json()};
    }''',{'case_id':case_id,'category':category})
    assert result['status']==200,result
    return result['body']['id']

def exercise(browser,base,password,output):
    admin_context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN');admin=admin_context.new_page()
    employee_context=browser.new_context(viewport={'width':390,'height':844},locale='zh-CN');employee=employee_context.new_page()
    errors=[]
    for page in [admin,employee]:page.on('pageerror',lambda error:errors.append(str(error)))
    req=h.checked_request;steps=[];screens=[];day=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    try:
        h.login_page(admin,base,'admin',password)
        secret=secrets.token_urlsafe(26);req(admin,'/api/users','POST',{'username':'return-inventory','display_name':'原退试用库管','role':'inventory','password':secret,'store_roles':[{'store_id':1,'role':'inventory'}]},status=201)
        h.login_page(employee,base,'return-inventory',secret)
        changed=secrets.token_urlsafe(26);req(employee,'/api/auth/password','POST',{'current_password':secret,'new_password':changed});h.login_page(employee,base,'return-inventory',changed)
        def typed(kind,values):return req(admin,'/api/masters/'+kind,'POST',{'request_id':secrets.token_hex(16),'values':values},status=201)
        warehouse=typed('warehouses',{'code':'RETURN-W','name':'原退物资仓','warehouse_type':'materials'})
        a=typed('locations',{'code':'RETURN-A','name':'甲库位','warehouse_id':warehouse['id']})['id'];b=typed('locations',{'code':'RETURN-B','name':'乙库位','warehouse_id':warehouse['id']})['id']
        item=req(admin,'/api/flow/master/items','POST',{'values':{'sku':'RETURN-GIFT','name':'原退合成礼品','unit':'件','reorder':'0','active':True}},status=201)['id']
        def create(operation,quantity,**extra):return req(admin,'/api/warehouse/cases','POST',{'request_id':secrets.token_hex(16),'operation':operation,'item_id':item,'quantity_milli':quantity,'reason':'合成原批次准备','due_date':day,**extra},status=201)
        def cmd(page,row,action,**values):
            current=req(page,'/api/warehouse/cases/'+str(row['id']));return req(page,'/api/warehouse/cases/'+str(row['id'])+'/commands/'+action,'POST',{'request_id':secrets.token_hex(16),'version':current['version'],'values':values})
        activated=create('activate',0,locations=[{'location_id':a,'quantity_milli':0}]);cmd(admin,activated,'approve',evidence_id=proof(admin,activated['id']))
        incoming=create('other_in',3000,destination_location_id=a);cmd(admin,incoming,'approve',value_cents=1001,evidence_id=proof(admin,incoming['id'],'receipt'));cmd(admin,incoming,'execute',evidence_id=proof(admin,incoming['id']))
        gift=create('gift',3000,source_location_id=a,recipient='合成领取人');cmd(admin,gift,'approve',evidence_id=proof(admin,gift['id']));gift=cmd(admin,gift,'execute',evidence_id=proof(admin,gift['id']))
        original=gift['stock_moves'][0]['id']
        def finish(row):
            cmd(admin,row,'approve',evidence_id=proof(admin,row['id']))
            h.navigate(employee,'warehouse/'+str(row['id']),row['operation_label'])
            proof(employee,row['id']);employee.reload();expect(employee.locator('[data-act=wh-action][data-key=execute]')).to_be_visible()
            employee.locator('[data-act=wh-action][data-key=execute]').click();h.save_modal(employee)
            assert req(admin,'/api/warehouse/cases/'+str(row['id']))['state']=='completed'
        h.navigate(employee,'warehouse/'+str(gift['id']),gift['operation_label'])
        employee.locator('[data-act=wh-original-return]').click()
        expect(employee.locator('#modal [data-return-summary]')).to_contain_text('尚可退')
        expect(employee.locator('#modal [name=quantity]')).to_have_value('');expect(employee.locator('#modal select[name=location]')).to_have_value('')
        expect(employee.locator('#modal [data-return-summary]')).not_to_contain_text('价值')
        employee.locator('#modal [name=quantity]').fill('1.251');choose(employee,'location','乙库位');employee.locator('#modal [name=reason]').fill('合成现场核对部分礼品退回')
        h.assert_fits_mobile(employee);screens.append(h.take_screenshot(employee,output,'01_original_return_mobile.png'));h.save_modal(employee)
        first=req(admin,'/api/warehouse/cases')['items'][0];assert first['original_move_id']==original and first['destination_location_id']==b and first['state']=='pending'
        assert req(admin,'/api/warehouse/items/'+str(item)+'/stock')['quantity_milli']==0
        finish(first);steps.append('实际库管从原礼品收发行申请部分退回，原批次及物资带入，数量/库位须本人填写；主管批准后实物确认才入账')
        h.navigate(employee,'warehouse','库位与仓储作业');employee.locator('[data-act=wh-new][data-operation=gift_return]').click()
        choose(employee,'original','原退合成礼品');expect(employee.locator('#modal [name=quantity]')).to_have_attribute('max','1.749')
        employee.locator('#modal [name=quantity]').fill('2');choose(employee,'location','乙库位');employee.locator('#modal [name=reason]').fill('合成最后剩余退回')
        employee.locator('#modal button[type=submit]').click();expect(employee.locator('#modal')).to_be_visible();assert employee.locator('#modal [name=quantity]').evaluate('(el)=>!el.checkValidity()')
        employee.locator('#modal [name=quantity]').fill('1.749');h.save_modal(employee);last=req(admin,'/api/warehouse/cases')['items'][0];finish(last)
        stock=req(admin,'/api/warehouse/items/'+str(item)+'/stock');assert (stock['quantity_milli'],stock['value_cents'])==(3000,1001)
        assert next(r for r in stock['balances'] if r['location_id']==b)['quantity_milli']==3000
        assert req(employee,'/api/warehouse/return-sources?operation=gift_return')['items']==[]
        h.navigate(employee,'warehouse/'+str(gift['id']),gift['operation_label']);expect(employee.locator('[data-act=wh-original-return]')).to_have_count(0)
        h.assert_fits_mobile(employee);screens.append(h.take_screenshot(employee,output,'02_fully_returned_source_mobile.png'))
        steps.append('全局退回实时搜索受限原批次，显示真实剩余，超量保留表单；两笔全部原退数量与1001分价值守恒，已退尽原行不再提供退回')
        assert not errors,errors
        return {'passed':len(steps),'steps':steps,'screenshots':screens,'javascript_errors':errors,'data':'fresh synthetic DB; actual inventory account; no customer database','transport':'actual Chrome HTTP/cookies/CSP'}
    finally:
        employee_context.close();admin_context.close()

if __name__=='__main__':h.exercise=exercise;h.main()
