"""Real 390px employees: original transfer, damaged goods and external recovery."""
import re,secrets
from playwright.sync_api import expect
import browser_huakangos as h
from browser_masters import employee_login


def exercise(browser,base,password,output):
    contexts=[];errors=[];screens=[];steps=[];req=h.checked_request
    def page(width=390):
        ctx=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(ctx);p=ctx.new_page();p.on('pageerror',lambda error:errors.append(str(error)));return p
    def screenshot(p,name,selector=None):
        expect(p.locator('#toast')).not_to_have_class(re.compile('visible'),timeout=10000)
        if selector:
            target=p.locator(selector).first;target.scroll_into_view_if_needed();target.evaluate('(e)=>window.scrollBy(0,e.getBoundingClientRect().top-120)')
        h.assert_fits_mobile(p);path=output/name;p.screenshot(path=str(path));screens.append(str(path))
    admin=page(1400);workers={};sids={}
    try:
        h.login_page(admin,base,'admin',password)
        other=req(admin,'/api/stores','POST',dict(code='TX-B',name='合成运输乙店'),status=201)['id']
        admin.reload();expect(admin.locator('#store')).to_be_visible();day=admin.evaluate('day()')
        for key,role,sid in [('out','inventory',1),('in','inventory',other),('finance','finance',1),('manager_a','manager',1),('manager_b','manager',other)]:
            secret=secrets.token_urlsafe(25);username='tx-'+key
            req(admin,'/api/users','POST',dict(username=username,display_name={'out':'甲店库管','in':'乙店库管','finance':'甲店财务','manager_a':'甲店店长','manager_b':'乙店店长'}[key],role=role,password=secret,store_roles=[dict(store_id=sid,role=role)]),status=201)
            workers[key]=page();sids[key]=sid;employee_login(workers[key],base,username,secret)
        items={sid:req(admin,'/api/flow/master/items','POST',{'values':dict(sku='TX-PART-'+str(sid),name='合成调拨滤芯',unit='件',reorder='0',active=True)},store=sid,status=201)['id'] for sid in (1,other)}
        supplier=req(admin,'/api/masters/suppliers','POST',dict(request_id=secrets.token_hex(16),values=dict(code='TX-SUP',name='合成供货与承运单位')),status=201)
        account=req(admin,'/api/flow/master/accounts','POST',{'values':dict(name='合成追偿实际账户',account_type='bank',active=True)},status=201)['id']
        purchase=req(admin,'/api/procurement/orders','POST',dict(request_id=secrets.token_hex(16),supplier_id=supplier['id'],reason='独立合成调拨原库存',lines=[dict(item_id=items[1],quantity_milli=3000,unit_cost_cents=33)]),status=201)
        def raw_upload(p,cid,sid,category='evidence'):
            r=p.evaluate('''async ({cid,sid,category})=>{const token=document.cookie.split('; ').find(x=>x.startsWith('dealer_csrf='))?.split('=')[1];const body=new FormData();body.set('category',category);body.set('file',new File(['仅合成实际原件'],'合成原件.txt',{type:'text/plain'}));const response=await fetch('/api/flow/cases/'+cid+'/files',{method:'POST',headers:{'X-Store-ID':String(sid),'X-CSRF-Token':token,'X-App-Request':'1'},body});return {status:response.status,body:await response.json()};}''',dict(cid=cid,sid=sid,category=category))
            assert r['status']==200,r;return r['body']['id']
        fid=raw_upload(admin,purchase['id'],1)
        for action,v in [('approve',{}),('receive',dict(lines=[dict(line_id=purchase['lines'][0]['id'],quantity_milli=3000)],evidence_id=fid))]:
            purchase=req(admin,f"/api/procurement/orders/{purchase['id']}/actions/{action}",'POST',dict(request_id=secrets.token_hex(16),version=purchase['version'],values=v))
        p=workers['out'];h.navigate(p,'transfers','跨店物资调拨');p.locator('[data-act=transfer-new]').click()
        p.locator('#modal [name=destination]').select_option(str(other));p.locator('#modal [name=item_id]').select_option(str(items[1]));p.locator('#modal [name=quantity]').fill('3');p.locator('#modal [name=reason]').fill('三件实际跨店调拨，双方各自办理');h.save_modal(p)
        transfer=req(p,'/api/transfers')['items'][0];assert transfer['flow_version']==3
        def original(p,key,sid):
            t=req(p,f"/api/transfers/{transfer['id']}",store=sid);h.navigate(p,'transfers/'+str(t['id']),'物资调拨');return t
        for key in ('manager_a','manager_b'):
            p=workers[key];original(p,key,sids[key]);p.locator('[data-act=transfer-action][data-key=approve]').click();p.locator('#modal [name=reason]').fill('本人核对本店实际调拨安排');h.save_modal(p)
        def upload(p,cid,sid,category='evidence'):
            case=req(p,f'/api/flow/cases/{cid}',store=sid);h.navigate(p,'case/'+str(cid),case['title'])
            p.locator('[data-act=upload]').click();p.locator('#modal [name=category]').select_option(category)
            filename='合成-'+category+'-'+secrets.token_hex(3)+'.txt'
            p.locator('#modal [name=file]').set_input_files(dict(name=filename,mimeType='text/plain',buffer=('本店员工核对的合成实际原件 '+filename).encode()))
            h.save_modal(p)
            return next(f['id'] for f in req(p,f'/api/flow/cases/{cid}',store=sid)['files'] if f['name']==filename)
        p=workers['out'];out=original(p,'out',1);outproof=upload(p,out['case_id'],1);original(p,'out',1)
        p.locator('[data-act=transfer-action][data-key=dispatch]').click();p.locator('#modal [name=evidence_id]').select_option(str(outproof));p.locator('#modal [name=reason]').fill('本人点清三件后实际交承运人发出');h.save_modal(p)
        p=workers['in'];inc=original(p,'in',other);inproof=upload(p,inc['case_id'],other);inc=original(p,'in',other);line=inc['lines'][0]['id']
        p.locator('[data-act=transfer-action][data-key=receive]').click();p.locator(f'#modal [name=accept_{line}]').fill('2');p.locator(f'#modal [name=reject_{line}]').fill('1');p.locator(f'#modal [name=item_{line}]').select_option(str(items[other]));p.locator('#modal [name=evidence_id]').select_option(str(inproof));p.locator('#modal [name=reason]').fill('本人验收两件合格、一件在手损坏');h.save_modal(p)
        p.locator('[data-act=transfer-exception-new]').click();p.locator('#modal [name=finding]').select_option('damaged');p.locator('#modal [name=quantity]').fill('1');p.locator('#modal [name=result]').fill('乙店实到一件拒收坏件，尚未退运');p.locator('#modal [name=evidence_id]').select_option(str(inproof));p.locator('#modal [name=confirmed]').check();h.save_modal(p)
        expect(p.locator('#main h1')).to_have_text('调拨运输差异');row=req(p,'/api/transfer-exceptions',store=other)['items'][0]
        screenshot(p,'01_inventory_rejected_damage_mobile.png','.panel:has(h2:text-is("本次原实物"))')
        current=req(p,f"/api/transfers/{transfer['id']}",store=other);assert not current['actions'] and current['active_exception_id']==row['id']
        assert 'value_cents' not in row and 'source_bearer_cents' not in str(row)
        steps.append('甲乙两库管390px实际发运/部分验收拒收；乙店沿原拒收批次发起在手坏件差异，普通收发暂停，库管看不到成本')
        def refresh(key):
            p=workers[key];route='transfer-exceptions/'+str(row['id'])
            if p.evaluate('location.hash')=='#'+route:
                p.reload();expect(p.locator('#main h1')).to_have_text('调拨运输差异')
            else:h.navigate(p,route,'调拨运输差异')
            return req(p,f"/api/transfer-exceptions/{row['id']}",store=sids[key])
        p=workers['out'];r=refresh('out');p.locator('[data-act=transfer-exception-action][data-key=observe]').click();p.locator('#modal [name=result]').fill('本人核对甲店原包装与发出清点');p.locator('#modal [name=evidence_id]').select_option(str(outproof));p.locator('#modal [name=confirmed]').check()
        req(p,f"/api/transfer-exceptions/{row['id']}/actions/observe",'POST',dict(request_id=secrets.token_hex(16),version=r['version'],transfer_version=r['transfer_version'],case_version=r['case_version'],values=dict(result='本人另一设备已核对实际发运清点',evidence_id=outproof,confirmed=True)))
        p.locator('#modal button[type=submit]').click();expect(p.locator('#modal .formerror')).to_contain_text('变化');screenshot(p,'02_conflicting_observation_mobile.png','#modal')
        p.locator('#modal [data-act=close]').first.click();refresh('out')
        steps.append('另一设备先追加观察后，原手机表单明确中文版本冲突；不盲重试，不重复确认实物')
        p=workers['finance'];fp=upload(p,out['case_id'],1,'receipt');refresh('finance');p.locator('[data-act=transfer-exception-action][data-key=plan]').click()
        p.locator('#modal [name=source]').fill('0.17');p.locator('#modal [name=destination]').fill('0.16');p.locator('#modal [name=reason]').fill('按原33分损失明确甲17分乙16分承担，不是赔款');p.locator('#modal [name=evidence_id]').select_option(str(fp));h.save_modal(p)
        for key in ('manager_a','manager_b'):
            p=workers[key];cid=out['case_id'] if key=='manager_a' else inc['case_id'];mf=upload(p,cid,sids[key],'receipt');refresh(key)
            p.locator('[data-act=transfer-exception-action][data-key=approve]').click();p.locator('#modal [name=reason]').fill('本人独立核对本版双方原事实与成本承担');p.locator('#modal [name=evidence_id]').select_option(str(mf));h.save_modal(p)
        p=workers['in'];refresh('in');p.locator('[data-act=transfer-exception-action][data-key=dispose]').click();p.locator('#modal [name=result]').fill('本人按已批准方案实际处置乙店在手一件坏件');p.locator('#modal [name=evidence_id]').select_option(str(inproof));p.locator('#modal [name=confirmed]').check();h.save_modal(p)
        assert not p.locator('[data-act=transfer-exception-action][data-key=cancel]').count();screenshot(p,'03_custodian_disposal_mobile.png','.panel:has(h2:text-is("真实处置"))')
        p=workers['finance'];refresh('finance');p.locator('[data-act=transfer-exception-action][data-key=post_loss]').click();p.locator('#modal [name=evidence_id]').select_option(str(fp));p.locator('#modal [name=confirmed]').check();h.save_modal(p)
        assert req(p,f"/api/transfers/{transfer['id']}")['status']=='completed'
        steps.append('甲店财务拟原33分承担，两位不同店长独立复核；只有乙店库管确认实际处置后，甲店财务才能确认损失，实物结清未制造现金')
        p.locator('[data-act=transfer-exception-action][data-key=recovery_create]').click();p.locator('#modal [name=party]').select_option('carrier:'+str(supplier['id']));p.locator('#modal [name=target]').fill('0.10');p.locator('#modal [name=reason]').fill('承运人实际原件确认累计赔付10分');p.locator('#modal [name=evidence_id]').select_option(str(fp));h.save_modal(p)
        def approve_recovery():
            p=workers['manager_a'];refresh('manager_a');p.locator('[data-act=transfer-exception-action][data-key=recovery_approve]').click();p.locator('#modal [name=reason]').fill('本人独立核对承运人最新实际赔付目标');p.locator('#modal [name=evidence_id]').select_option(str(fp));h.save_modal(p)
        approve_recovery();p=workers['finance'];r=refresh('finance');p.locator('[data-act=transfer-exception-action][data-key=recovery_receive]').click();p.locator('#modal [name=amount]').fill('0.10');p.locator('#modal [name=account]').select_option(str(account));p.locator('#modal [name=reference]').fill('SYNTHETIC-RECOVERY-IN');p.locator('#modal [name=evidence_id]').select_option(str(fp));p.locator('#modal [name=confirmed]').check();h.save_modal(p)
        p.locator('[data-act=transfer-exception-action][data-key=recovery_plan]').click();p.locator('#modal [name=target]').fill('0.04');p.locator('#modal [name=reason]').fill('承运人确认仅4分，新增版本并退回原超收6分');p.locator('#modal [name=evidence_id]').select_option(str(fp));h.save_modal(p)
        approve_recovery();p=workers['finance'];r=refresh('finance');assert r['recoveries'][0]['refund_cents']==6
        p.locator('[data-act=transfer-exception-action][data-key=recovery_refund]').click();p.locator('#modal [name=amount]').fill('0.06');p.locator('#modal [name=account]').select_option(str(account));p.locator('#modal [name=reference]').fill('SYNTHETIC-RECOVERY-RETURN');p.locator('#modal [name=evidence_id]').select_option(str(fp));p.locator('#modal [name=confirmed]').check();h.save_modal(p)
        r=req(p,f"/api/transfer-exceptions/{row['id']}");claim=r['recoveries'][0];assert claim['target_cents']==claim['paid_cents']==4 and claim['refund_cents']==claim['due_cents']==0
        assert [(x['direction'],x['amount_cents']) for x in claim['payments']]==[('in',10),('out',6)]
        screenshot(p,'04_finance_original_recovery_mobile.png','.panel:has(h2:text-is("本店外部追偿"))')
        steps.append('财务与独立店长在手机办理承运人目标10分、实际到账10分、新版目标4分及原账户退回6分；目标、原现金和损失不重复记账')
        h.navigate(p,'analytics/materials','数据可视化')
        chart=p.locator('.chartpanel:has(h2:text-is("期间物资运输损失原成本"))')
        expect(chart.locator('svg')).to_be_visible();screenshot(p,'05_material_loss_chart_mobile.png','.chartpanel:has(h2:text-is("期间物资运输损失原成本"))')
        chart.locator('[data-act=charttable]').click();expect(p.locator('#main h1')).to_have_text('期间物资运输损失原成本')
        expect(p.locator('#main')).to_contain_text('0.33');screenshot(p,'06_material_loss_sources_mobile.png','#main h1')
        p.locator('[data-act=drill]').first.click();expect(p.locator('#main h1')).to_have_text(req(p,f"/api/flow/cases/{out['case_id']}")['title'])
        assert p.evaluate('location.hash')=='#case/'+str(out['case_id'])
        steps.append('财务390px在经营可视化查看原33分运输损失图及同源明细，原单按钮回到本店原调拨任务，页面不横溢')
        assert not errors,errors
        return dict(status='passed',mode='actual-chrome-http',steps=steps,screenshots=screens,javascript_errors=errors,synthetic_only=True)
    except Exception:
        for key,p in {'admin':admin,**workers}.items():p.screenshot(path=str(output/('failure_'+key+'.png')))
        raise
    finally:
        for ctx in contexts:ctx.close()


if __name__=='__main__':h.exercise=exercise;h.main()
