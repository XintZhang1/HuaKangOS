"""Real Chromium / 390px employee verification of paired material transfers.

Reuses only the isolated-server harness; no existing database or company service.
"""
from pathlib import Path
import json
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import browser_huakangos as harness
from playwright.sync_api import expect


def exercise(browser,base,password,output):
    steps=[];screenshots=[];errors=[]
    admin_context=browser.new_context(viewport={'width':1280,'height':960},locale='zh-CN')
    employee_context=browser.new_context(viewport={'width':390,'height':844},locale='zh-CN')
    admin=admin_context.new_page();page=employee_context.new_page()
    for p in (admin,page):p.on('pageerror',lambda error:errors.append(str(error)))
    req=harness.checked_request
    try:
        harness.login_page(admin,base,'admin',password)
        two=req(admin,'/api/stores','POST',{'code':'TX-B','name':'调入验收店'},status=201)['id']
        credentials={}
        for name,role,sid in [('out-stock','inventory',1),('in-stock','inventory',two),('out-manager','manager',1),('in-manager','manager',two)]:
            secret=secrets.token_urlsafe(24);credentials[name]=secret
            req(admin,'/api/users','POST',{'username':name,'display_name':name,'password':secret,'role':role,
                'store_roles':[{'store_id':sid,'role':role}],'can_group_summary':False},status=201)
        item_values={'sku':'TRANSFER-BROWSER','name':'浏览器调拨滤芯','unit':'件','reorder':'0','active':True}
        a=req(admin,'/api/flow/master/items','POST',{'values':item_values},status=201)
        b=req(admin,'/api/flow/master/items','POST',{'values':item_values},store=two,status=201)
        purchase=req(admin,'/api/flow/cases','POST',{'request_id':secrets.token_hex(16),'kind':'purchase',
            'values':{'item_id':a['id'],'quantity':'3','unit_cost':'0.33','supplier':'合成采购来源','note':'浏览器测试前置库存'}},status=201)
        cid=purchase['id']
        def raw_upload(target,case_id,sid):
            result=target.evaluate('''async ({cid,sid})=>{const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];const f=new FormData();f.set('category','evidence');f.set('file',new File(['合成入库验收'],'测试凭据.txt',{type:'text/plain'}));const r=await fetch('/api/flow/cases/'+cid+'/files',{method:'POST',headers:{'X-Store-ID':String(sid),'X-CSRF-Token':token,'X-App-Request':'1'},body:f});return {status:r.status,body:await r.json()};}''',{'cid':case_id,'sid':sid})
            assert result['status']==200,result
            return result['body']['id']
        proof=raw_upload(admin,cid,1)
        for action,values in [('approve',{}),('stock_in',{'evidence_id':proof})]:
            purchase=req(admin,f'/api/flow/cases/{cid}/actions/{action}','POST',{'request_id':secrets.token_hex(16),'version':purchase['version'],'values':values})
        def login(name):
            if page.locator('[data-act=logout]').count():page.locator('[data-act=logout]').click();expect(page.locator('.loginform')).to_be_visible()
            harness.login_page(page,base,name,credentials[name])
            if page.locator('#modal [name=current_password]').count():
                replacement=secrets.token_urlsafe(24)
                page.locator('#modal [name=current_password]').fill(credentials[name]);page.locator('#modal [name=new_password]').fill(replacement)
                page.locator('#modal button[type=submit]').click();credentials[name]=replacement
                expect(page.locator('.loginform')).to_be_visible()
                harness.login_page(page,base,name,replacement)
            expect(page.locator('#main h1')).to_have_text('我的工作')
        login('out-stock');harness.navigate(page,'transfers','跨店物资调拨')
        page.locator('[data-act=transfer-new]').click()
        page.locator('#modal [name=destination]').select_option(str(two))
        page.locator('#modal [name=reason]').fill('两店调剂库存，逐批验收')
        page.locator('#modal [name=item_id]').select_option(str(a['id']))
        page.locator('#modal [name=quantity]').fill('3')
        harness.assert_fits_mobile(page)
        screenshots.append(harness.take_screenshot(page,output,'01_transfer_request_mobile.png'))
        harness.save_modal(page);expect(page.locator('#main h1')).to_have_text('物资调拨')
        row=req(page,'/api/transfers')['items'][0];key=row['id'];line=row['lines'][0]['id']
        steps.append('调出库管在手机页面申请调拨，双方收到各自审批任务')
        def view(sid):
            harness.navigate(page,f'transfers/{key}','物资调拨')
            return req(page,f'/api/transfers/{key}',store=sid)
        def action(key,reason,fields=None):
            page.locator(f'[data-act=transfer-action][data-key={key}]').click()
            page.locator('#modal [name=reason]').fill(reason)
            for name,value in (fields or {}).items():
                locator=page.locator(f'#modal [name="{name}"]')
                if locator.evaluate('(e)=>e.tagName')=='SELECT':locator.select_option(str(value))
                else:locator.fill(str(value))
            harness.assert_fits_mobile(page);harness.save_modal(page)
        login('out-manager');view(1);action('approve','调出方同意调拨')
        login('in-manager');view(two);action('approve','调入方确认接收安排')
        steps.append('两家门店的独立主管账号分别批准，各自不能代替库管交接')
        def upload(sid):
            r=req(page,f'/api/transfers/{key}',store=sid);case=req(page,f'/api/flow/cases/{r["case_id"]}',store=sid)
            harness.navigate(page,f'case/{case["id"]}',case['title'])
            page.locator('[data-act=upload]').click()
            page.locator('#modal [name=file]').set_input_files({'name':'实际交接记录.txt','mimeType':'text/plain','buffer':'合成实物交接记录'.encode()})
            harness.save_modal(page)
            expect(page.locator('.filerecord')).to_contain_text('仅结构校验通过')
            page.locator('[data-act=filescaninfo]').click();expect(page.locator('#modal')).to_contain_text('未进行病毒扫描')
            page.locator('#modal [data-act=close]').last.click()
            case=req(page,f'/api/flow/cases/{case["id"]}',store=sid)
            proof=case['files'][0]['id'];view(sid);return proof
        login('out-stock');proof_a=upload(1);action('dispatch','物流已接收全部三件',{'evidence_id':proof_a})
        screenshots.append(harness.take_screenshot(page,output,'02_outgoing_in_transit.png'))
        steps.append('调出库管上传凭据并发出，全部数量转为在途，扫描状态可查看')
        login('in-stock');proof_b=upload(two)
        action('receive','两件合格，一件破损拒收',{'evidence_id':proof_b,f'accept_{line}':'2',f'reject_{line}':'1',f'item_{line}':b['id']})
        r=req(page,f'/api/transfers/{key}',store=two);rejection=next(m for m in r['movements'] if m['kind']=='reject')
        action('return_ship','拒收物资交物流退回',{'evidence_id':proof_b,'target':rejection['id']})
        screenshots.append(harness.take_screenshot(page,output,'03_rejected_return_in_transit.png'))
        steps.append('调入库管按合格/拒收数量分别办理，拒收件发运退回且不计可用库存')
        login('out-stock');r=view(1);shipment=next(m for m in r['movements'] if m['kind']=='return_ship')
        action('return_receive','原店接收退回实物',{'evidence_id':proof_a,'target':shipment['id'],'returned_qty':'1'})
        expect(page.locator('#main')).to_contain_text('已结清实物')
        harness.assert_fits_mobile(page)
        screenshots.append(harness.take_screenshot(page,output,'04_completed_return_mobile.png'))
        report=req(admin,'/api/flow/analytics',store='all')
        assert report['metrics']['material_cost_cents']==99
        assert report['metrics']['material_in_transit_cents']==0 and report['metrics']['interstore_material_net_cents']==0
        assert report['metrics']['cash_in_cents']==report['metrics']['cash_out_cents']==0
        steps.append('原店确认退回后结清；两店库存价值合计0.99元、在途0、内部往来净额0、现金不重复')
        assert errors==[],errors
        return {'mode':'real Chromium browser HTTP','passed':len(steps),'steps':steps,'javascript_errors':errors,'screenshots':screenshots,
                'limitations':['合成资料及本地HTTP，不代表生产HTTPS和运输实物验证','仅结构校验模式，未调用公司查毒服务']}
    except Exception:
        harness.take_screenshot(page,output,'failure.png');raise
    finally:employee_context.close();admin_context.close()


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
