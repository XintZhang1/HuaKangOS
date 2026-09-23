"""Real 390px employee Chromium: two-store cash and independently sealed statement."""
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request as req,login_page,navigate,save_modal,assert_fits_mobile,take_screenshot


def exercise(browser,base,password,output):
    contexts=[];errors=[];screenshots=[];steps=[]
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(context)
        p=context.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440);payer=page();receiver=page();manager=page()
    day=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    def raw_upload(p,cid,sid):
        response=p.evaluate('''async ({cid,sid})=>{const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];const f=new FormData();f.set('category','evidence');f.set('file',new File(['合成实际交接凭据'],'合成凭据.txt',{type:'text/plain'}));const r=await fetch('/api/flow/cases/'+cid+'/files',{method:'POST',headers:{'X-Store-ID':String(sid),'X-CSRF-Token':token,'X-App-Request':'1'},body:f});return {status:r.status,body:await r.json()};}''',{'cid':cid,'sid':sid})
        assert response['status']==200,response;return response['body']['id']
    def upload(p,cid,sid):
        case=req(p,f'/api/flow/cases/{cid}',store=sid);navigate(p,f'case/{cid}',case['title'])
        p.locator('[data-act=upload]').click();p.locator('#modal [name=file]').set_input_files({'name':'本店银行核对.txt','mimeType':'text/plain','buffer':'合成实际付款到账与对账复核凭据'.encode()})
        save_modal(p);assert_fits_mobile(p)
        return req(p,f'/api/flow/cases/{cid}',store=sid)['files'][0]['id']
    def modal(p,key,reason,values=None,kind='clearing-action'):
        p.locator(f'[data-act={kind}][data-key={key}]').click();p.locator('#modal [name=reason]').fill(reason)
        for k,v in (values or {}).items():
            el=p.locator(f'#modal [name={k}]')
            if el.evaluate('(x)=>x.tagName')=='SELECT':el.select_option(str(v))
            else:el.fill(str(v))
        assert_fits_mobile(p);save_modal(p)
    try:
        login_page(admin,base,'admin',password)
        two=req(admin,'/api/stores','POST',{'code':'CLEAR-B','name':'清算付款乙店'},status=201)['id']
        for name,role,sid,p in [('payer','finance',two,payer),('receiver','finance',1,receiver),('manager','manager',two,manager)]:
            secret=secrets.token_urlsafe(24)
            req(admin,'/api/users','POST',{'username':'clear-'+name,'display_name':'合成清算'+name,'role':role,'password':secret,
                'store_roles':[{'store_id':sid,'role':role}]},status=201)
            login_page(p,base,'clear-'+name,secret);p.locator('#modal [name=current_password]').fill(secret)
            changed=secrets.token_urlsafe(24);p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'clear-'+name,changed)
        accounts={sid:req(admin,'/api/flow/master/accounts','POST',{'values':{'name':'合成清算账户'+str(sid),'account_type':'bank','active':True}},store=sid,status=201)['id'] for sid in [1,two]}
        items={sid:req(admin,'/api/flow/master/items','POST',{'values':{'sku':'CLEAR-PART','name':'清算合成滤芯','unit':'件','reorder':'0','active':True}},store=sid,status=201)['id'] for sid in [1,two]}
        purchase=req(admin,'/api/flow/cases','POST',{'request_id':secrets.token_hex(16),'kind':'purchase','values':{'item_id':items[1],'quantity':'3','unit_cost':'0.33','supplier':'合成库存来源','note':'对账测试前置库存'}},status=201)
        fid=raw_upload(admin,purchase['id'],1)
        for action,values in [('approve',{}),('stock_in',{'evidence_id':fid})]:
            purchase=req(admin,f'/api/flow/cases/{purchase["id"]}/actions/{action}','POST',{'request_id':secrets.token_hex(16),'version':purchase['version'],'values':values})
        transfer=req(admin,'/api/transfers','POST',{'request_id':secrets.token_hex(16),'destination_store_id':two,'due_date':day,'reason':'合成实物调拨前置',
            'lines':[{'item_id':items[1],'quantity_milli':3000}]},status=201)
        def transfer_action(sid,action,values):
            row=req(admin,f'/api/transfers/{transfer["id"]}',store=sid)
            return req(admin,f'/api/transfers/{row["id"]}/actions/{action}','POST',{'request_id':secrets.token_hex(16),'version':row['version'],'case_version':row['case_version'],'values':values},store=sid)
        transfer_action(1,'approve',{'reason':'调出店批准'});transfer_action(two,'approve',{'reason':'调入店批准'})
        out=req(admin,f'/api/transfers/{transfer["id"]}');transfer_action(1,'dispatch',{'reason':'物流实物发出','evidence_id':raw_upload(admin,out['case_id'],1)})
        inc=req(admin,f'/api/transfers/{transfer["id"]}',store=two)
        transfer_action(two,'receive',{'reason':'调入店实物验收','evidence_id':raw_upload(admin,inc['case_id'],two),
            'lines':[{'line_id':inc['lines'][0]['id'],'item_id':items[two],'accept_milli':3000,'reject_milli':0}]})
        navigate(payer,'clearing','店间实际清算');payer.locator('[data-act=clearing-new]').click()
        payer.locator('#modal [name=amount]').fill('0.60');payer.locator('#modal [name=reason]').fill('双方对99分原调拨先清算60分');save_modal(payer)
        expect(payer.locator('#main h1')).to_have_text('店间实际清算')
        clearing=req(payer,'/api/reconciliation/clearing',store=two)['items'][0]
        steps.append('乙店财务手机申请原99分调拨的60分清算，保留39分未占用额度')
        navigate(payer,'reconciliation','业务对账与月结');payer.locator('[data-act=reconcile-new]').click()
        payer.locator('#modal [name=reason]').fill('实际月结对账来源基线');save_modal(payer)
        batches=req(payer,'/api/reconciliation/batches',store=two)['items'];statement=batches[0]
        payment_proof=upload(payer,clearing['case_id'],two);navigate(payer,f'clearing/{clearing["id"]}','店间实际清算')
        modal(payer,'pay','乙店银行实际转出60分',{'account_id':accounts[two],'reference':'BROWSER-CLEAR-OUT','evidence_id':payment_proof})
        expect(payer.locator('#main')).to_contain_text('付款已记，收款店待确认')
        steps.append('付款店仅登记自己真实支出；未收到确认保持内部在途，不能提前抹平')
        navigate(payer,f'reconciliation/{statement["id"]}','业务对账与月结')
        expect(payer.locator('#main')).to_contain_text('原来源已有晚到')
        payer.locator('[data-act=reconcile-action][data-key=submit]').click();payer.locator('#modal [name=reason]').fill('尝试原版本提交应被拒绝')
        payer.locator('#modal button[type=submit]').click();expect(payer.locator('#modal .formerror')).to_contain_text('来源有晚到')
        screenshots.append(take_screenshot(payer,output,'01_reconciliation_late_source_refused.png'))
        payer.locator('#modal [data-act=close]').last.click()
        modal(payer,'recalculate','银行支付已记入原单，追加重算版本',kind='reconcile-action')
        fresh=req(payer,'/api/reconciliation/batches',store=two)['items'][0];assert fresh['revision']==2
        proof_batch=upload(payer,fresh['case_id'],two);navigate(payer,f'reconciliation/{fresh["id"]}','业务对账与月结')
        source=req(payer,f'/api/reconciliation/batches/{fresh["id"]}',store=two)
        cash_line=next(x for x in source['manifest'] if x['source']=='cash_entries')
        payer.locator(f'[data-act=reconcile-action][data-key=issue][data-line="{cash_line["key"]}"]').click()
        payer.locator('#modal [name=difference]').fill('0');payer.locator('#modal [name=reason]').fill('银行回单金额已核对，需要留存核对记录')
        payer.locator('#modal [name=evidence_id]').select_option(str(proof_batch));save_modal(payer)
        modal(payer,'resolve','原回单与账面60分一致，不需要改原现金',{'evidence_id':proof_batch},kind='reconcile-action')
        modal(payer,'submit','财务已核对全部来源与差异处理',kind='reconcile-action')
        navigate(manager,f'reconciliation/{fresh["id"]}','业务对账与月结')
        modal(manager,'seal','独立店长核对回单及新版本后封存',{'evidence_id':proof_batch},kind='reconcile-action')
        expect(manager.locator('#main')).to_contain_text('已封存');assert_fits_mobile(manager)
        with manager.expect_download() as downloaded:
            manager.locator('[data-act=reconcile-action][data-key=export]').click()
        assert downloaded.value.suggested_filename.endswith('.csv')
        screenshots.append(take_screenshot(manager,output,'02_reconciliation_independent_sealed.png'))
        steps.append('晚到支付使原快照提交被拒；重算新版本、财务逐条处理差异、独立店长手机封存')
        incoming=req(receiver,f'/api/reconciliation/clearing/{clearing["id"]}',store=1)
        proof_in=upload(receiver,incoming['case_id'],1);navigate(receiver,f'clearing/{clearing["id"]}','店间实际清算')
        modal(receiver,'receive','甲店银行实际到账60分',{'account_id':accounts[1],'reference':'BROWSER-CLEAR-IN','evidence_id':proof_in})
        expect(receiver.locator('#main')).to_contain_text('双方已确认结清');assert_fits_mobile(receiver)
        screenshots.append(take_screenshot(receiver,output,'03_clearing_both_actual_cash.png'))
        old=req(payer,f'/api/reconciliation/batches/{statement["id"]}',store=two);assert old['status']=='superseded'
        remaining=req(payer,'/api/reconciliation/origins',store=two)['items'][0]
        assert remaining['settled_cents']==60 and remaining['available_cents']==39 and remaining['reserved_cents']==0
        assert len(req(payer,f'/api/reconciliation/clearing/{clearing["id"]}',store=two)['cash'])==1
        assert len(req(receiver,f'/api/reconciliation/clearing/{clearing["id"]}',store=1)['cash'])==1
        steps.append('甲店独立确认真实到账后，双方各一笔现金，原往来只核销60分；历史对账版本保留')
        assert not errors,errors
        return {'mode':'real Chromium browser HTTP','passed':len(steps),'steps':steps,'javascript_errors':errors,'screenshots':screenshots,
            'limitations':['合成资料与本地HTTP，不替代正式HTTPS及实际月结业务周期','集团会员中心无虚构现金账户，本场景实结范围为店间调拨']}
    except Exception:
        take_screenshot(payer,output,'failure_payer.png');take_screenshot(receiver,output,'failure_receiver.png');raise
    finally:
        for context in contexts:context.close()


if __name__=='__main__':
    harness.exercise=exercise;harness.main()
