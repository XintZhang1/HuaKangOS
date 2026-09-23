"""Actual employee Chromium at 390px: found goods, return, disposal, original cash."""
import re,secrets
from playwright.sync_api import expect
import browser_huakangos as h
from browser_masters import employee_login


def exercise(browser,base,password,output):
    contexts=[];workers={};errors=[];screens=[];steps=[];req=h.checked_request
    def page(width=390):
        ctx=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(ctx)
        p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    def shot(p,name,selector):
        expect(p.locator('#toast')).not_to_have_class(re.compile('visible'),timeout=10000)
        target=p.locator(selector).first;target.scroll_into_view_if_needed();target.evaluate('(e)=>window.scrollBy(0,e.getBoundingClientRect().top-120)')
        h.assert_fits_mobile(p);path=output/name;p.screenshot(path=str(path));screens.append(str(path))
    def navigate(p,route,title):
        if p.evaluate('location.hash')=='#'+route:p.reload();expect(p.locator('#main h1')).to_have_text(title)
        else:h.navigate(p,route,title)
    admin=page(1280)
    try:
        h.login_page(admin,base,'admin',password)
        two=req(admin,'/api/stores','POST',dict(code='FOUND-B',name='合成找回乙店'),status=201)['id'];sids={'out':1,'in':two,'finance':1,'ma':1,'mb':two}
        for key,role in [('out','inventory'),('in','inventory'),('finance','finance'),('ma','manager'),('mb','manager')]:
            secret=secrets.token_urlsafe(25);username='found-'+key
            req(admin,'/api/users','POST',dict(username=username,display_name={'out':'找回甲库管','in':'找回乙库管','finance':'找回甲财务','ma':'找回甲店长','mb':'找回乙店长'}[key],role=role,password=secret,store_roles=[dict(store_id=sids[key],role=role)]),status=201)
            workers[key]=page();employee_login(workers[key],base,username,secret)
        day=admin.evaluate('day()')
        item=req(admin,'/api/flow/master/items','POST',dict(values=dict(sku='FOUND-FILTER',name='合成找回滤芯',unit='件',reorder='0',active=True)),status=201)['id']
        supplier=req(admin,'/api/masters/suppliers','POST',dict(request_id=secrets.token_hex(16),values=dict(code='FOUND-CARRIER',name='合成原承运单位')),status=201)['id']
        account=req(admin,'/api/flow/master/accounts','POST',dict(values=dict(name='合成找回原银行账户',account_type='bank',active=True)),status=201)['id']
        def upload(p,cid,sid,category='evidence'):
            case=req(p,f'/api/flow/cases/{cid}',store=sid);navigate(p,'case/'+str(cid),case['title'])
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category)
            filename='合成找回-'+category+'-'+secrets.token_hex(3)+'.txt'
            p.locator('#modal [name=file]').set_input_files(dict(name=filename,mimeType='text/plain',buffer=('本人核对的实际原件 '+filename).encode()))
            h.save_modal(p);return next(f['id'] for f in req(p,f'/api/flow/cases/{cid}',store=sid)['files'] if f['name']==filename)
        purchase=req(admin,'/api/procurement/orders','POST',dict(request_id=secrets.token_hex(16),supplier_id=supplier,reason='独立合成找回原库存',lines=[dict(item_id=item,quantity_milli=3000,unit_cost_cents=33)]),status=201)
        pr=upload(admin,purchase['id'],1)
        for action,values in [('approve',{}),('receive',dict(lines=[dict(line_id=purchase['lines'][0]['id'],quantity_milli=3000)],evidence_id=pr))]:
            purchase=req(admin,f"/api/procurement/orders/{purchase['id']}/actions/{action}",'POST',dict(request_id=secrets.token_hex(16),version=purchase['version'],values=values))
        transfer=req(workers['out'],'/api/transfers','POST',dict(request_id=secrets.token_hex(16),destination_store_id=two,due_date=day,reason='合成原发运后短缺及后来找到链',lines=[dict(item_id=item,quantity_milli=3000)]),status=201)
        def tr(key,action,values):
            p=workers[key];r=req(p,f"/api/transfers/{transfer['id']}",store=sids[key])
            return req(p,f"/api/transfers/{r['id']}/actions/{action}",'POST',dict(request_id=secrets.token_hex(16),version=r['version'],case_version=r['case_version'],values=values),store=sids[key])
        for key in ['ma','mb']:tr(key,'approve',dict(reason='独立批准本店原调拨'))
        local={key:req(workers[key],f"/api/transfers/{transfer['id']}",store=sids[key])['case_id'] for key in workers}
        proofs={key:upload(workers[key],local[key],sids[key],'evidence' if key in {'out','in'} else 'receipt') for key in workers}
        dispatched=tr('out','dispatch',dict(evidence_id=proofs['out'],reason='本人真实交原承运人三件物资'))
        t=req(workers['in'],f"/api/transfers/{transfer['id']}",store=two)
        ex=req(workers['in'],'/api/transfer-exceptions','POST',dict(request_id=secrets.token_hex(16),transfer_id=t['id'],version=t['version'],case_version=t['case_version'],original_id=dispatched['movements'][0]['id'],quantity_milli=3000,finding='missing',result='本人核对本店确未收到原三件物资',evidence_id=proofs['in'],due_date=day,confirmed=True),store=two,status=201)
        def exception(key,action,values):
            p=workers[key];r=req(p,f"/api/transfer-exceptions/{ex['id']}",store=sids[key])
            return req(p,f"/api/transfer-exceptions/{ex['id']}/actions/{action}",'POST',dict(request_id=secrets.token_hex(16),version=r['version'],transfer_version=r['transfer_version'],case_version=r['case_version'],values=values),store=sids[key])
        exception('out','observe',dict(evidence_id=proofs['out'],result='本人核对甲店实际发出三件的原件',confirmed=True))
        ex=exception('finance','plan',dict(evidence_id=proofs['finance'],source_bearer_cents=50,destination_bearer_cents=49,reason='原成本99分，甲50乙49承担'))
        for key in ['ma','mb']:ex=exception(key,'approve',dict(evidence_id=proofs[key],plan_id=ex['plans'][-1]['id'],reason='本人独立核对原双方事实及承担'))
        exception('finance','post_loss',dict(evidence_id=proofs['finance'],confirmed=True))
        ex=exception('finance','recovery_create',dict(evidence_id=proofs['finance'],counterparty_kind='carrier',counterparty_id=supplier,target_cents=30,due_date=day,reason='承运单位实际原件已确认赔付30分'))
        claim=ex['recoveries'][0]
        ex=exception('ma','recovery_approve',dict(evidence_id=proofs['ma'],claim_id=claim['id'],claim_version=claim['version'],plan_id=claim['pending_plan_id'],reason='独立确认原承运单位赔付原件'))
        claim=ex['recoveries'][0];exception('finance','recovery_receive',dict(evidence_id=proofs['finance'],claim_id=claim['id'],claim_version=claim['version'],amount_cents=30,account_id=account,reference='SYNTHETIC-FOUND-IN',business_date=day,confirmed=True))
        goods=None
        def view(key):
            p=workers[key];navigate(p,'transfer-goods-recoveries/'+str(goods['id']),'损失后找到原物资')
            return req(p,f"/api/transfer-goods-recoveries/{goods['id']}",store=sids[key])
        def action(key,name,extra=None,claim_id=None,save=True):
            p=workers[key];view(key);selector=f'[data-act=transfer-goods-action][data-key={name}]'+(f'[data-claim="{claim_id}"]' if claim_id else '')
            p.locator(selector).click()
            expect(p.locator('#modal')).to_be_visible()
            for field in ('result','reason'):
                if p.locator(f'#modal [name={field}]').count():p.locator(f'#modal [name={field}]').fill('本人核对本次原物资事实或往来方真实原件，保留原账')
            p.locator('#modal [name=evidence_id]').select_option(str(proofs[key]))
            for field,value in (extra or {}).items():
                loc=p.locator(f'#modal [name={field}]')
                if loc.evaluate('(e)=>e.tagName')=='SELECT':loc.select_option(str(value))
                else:loc.fill(str(value))
            if p.locator('#modal [name=confirmed]').count():p.locator('#modal [name=confirmed]').check()
            if save:h.save_modal(p)
        def start(key):
            p=workers[key];navigate(p,'transfers/'+str(transfer['id']),'物资调拨');p.locator('[data-act=transfer-goods-new]').click()
            p.locator('#modal [name=quantity]').fill('1');p.locator('#modal [name=result]').fill('本人实际找到可辨认的原一件物资并暂时保管')
            p.locator('#modal [name=evidence_id]').select_option(str(proofs[key]));p.locator('#modal [name=confirmed]').check();h.save_modal(p)
            expect(p.locator('#main h1')).to_have_text('损失后找到原物资')
            return req(p,'/api/transfer-goods-recoveries',store=sids[key])['items'][0]
        goods=start('out');shot(workers['out'],'01_actual_found_mobile.png','.panel:has(h2:text-is("本次实际找回"))')
        action('in','match');r=view('out');assert 'claims' not in r
        action('out','inspect',{'passed':'yes'},save=False)
        req(workers['out'],f"/api/transfer-goods-recoveries/{goods['id']}/actions/inspect",'POST',dict(request_id=secrets.token_hex(16),version=r['version'],transfer_version=r['transfer_version'],case_version=r['case_version'],values=dict(evidence_id=proofs['out'],result='本人另一设备先完成原实物复验',passed=True,confirmed=True)))
        workers['out'].locator('#modal button[type=submit]').click();expect(workers['out'].locator('#modal .formerror')).to_contain_text('变化')
        shot(workers['out'],'02_stale_inspection_mobile.png','#modal');workers['out'].locator('#modal [data-act=close]').first.click()
        action('finance','plan');action('ma','approve');action('mb','approve');action('out','restore')
        assert view('out')['status']=='financial'
        steps.append('两店390px库管沿原调拨登记找到、分别核对并复验；同一原版本冲突中文拒绝，双方独立主管批准后原店实际入库')
        action('finance','terms',{'target':'0.00'},claim['id']);action('ma','terms_approve',claim_id=claim['id'])
        action('finance','refund',dict(amount='0.30',account=account,reference='SYNTHETIC-FOUND-RETURN'),claim['id'])
        r=view('finance');assert r['status']=='closed' and [(p['direction'],p['amount_cents']) for p in r['claims'][0]['payments']]==[('in',30),('out',30)]
        shot(workers['finance'],'03_original_compensation_return_mobile.png','.panel:has(h2:text-is("本店原赔付处理"))')
        steps.append('原库存恢复先完成，赔付原30分保留；财务登记实际新目标0、独立店长批准、原账户实际退回30分后结束原赔付处理')
        goods=start('in');action('out','match');action('in','inspect',{'passed':'yes'});action('in','ship')
        shot(workers['in'],'04_found_return_in_transit_mobile.png','.panel:has(h2:text-is("本次实际找回"))')
        action('out','receive',{'passed':'yes'});action('finance','plan');action('ma','approve');action('mb','approve');action('out','restore')
        action('finance','terms',{'target':'0.00'},claim['id']);action('ma','terms_approve',claim_id=claim['id']);assert view('finance')['status']=='closed'
        steps.append('乙店找到原第二件，经本人发回及甲店实际收到复验后恢复原成本；原退运未到时不计可用库存')
        goods=start('in');action('out','match');action('in','inspect',{'passed':'no'});action('finance','plan');action('ma','approve');action('mb','approve');action('in','dispose');action('finance','finish_bad')
        r=view('in');assert r['status']=='closed' and r['plans'][-1]['restored_quantity_milli']==0
        shot(workers['in'],'05_found_bad_disposal_mobile.png','.panel:has(h2:text-is("双方本人事实"))')
        steps.append('乙店找到原第三件但复验不合格，两店独立批准后由乙库管实际处置；不恢复库存、成本或承担，不伪造退款')
        items=req(admin,'/api/flow/lookup/item');items=items.get('items',[]) if isinstance(items,dict) else items
        t=req(admin,f"/api/transfers/{transfer['id']}");assert t['status']=='completed' and t['lines'][0]['lost_milli']==3000 and len(t['goods_recovery_ids'])==3
        assert not errors,errors
        return dict(status='passed',mode='actual-chrome-http',steps=steps,screenshots=screens,javascript_errors=errors,synthetic_only=True,limitations=['本地HTTP合成凭据；非公司实物或银行操作','仅结构校验，未声称查毒通过'])
    except Exception:
        for key,p in {'admin':admin,**workers}.items():p.screenshot(path=str(output/('failure_'+key+'.png')))
        raise
    finally:
        for ctx in contexts:ctx.close()


if __name__=='__main__':h.exercise=exercise;h.main()
