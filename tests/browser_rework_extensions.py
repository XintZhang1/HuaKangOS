"""Actual employee Chrome UI on an isolated temporary DB, never port 8000."""
import secrets
from datetime import datetime
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_huakangos import checked_request,login_page,save_modal,take_screenshot,assert_fits_mobile

def exercise(browser,base,password,output):
    contexts=[];errors=[];shots=[];steps=[]
    def page(width=390):
        context=browser.new_context(viewport={'width':width,'height':844},locale='zh-CN');contexts.append(context);p=context.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page(1440);employees={}
    try:
        login_page(admin,base,'admin',password)
        def request(path,method='GET',values=None,status=200,p=None):return checked_request(p or admin,path,method,values,status=status)
        def master(kind,values):return request('/api/flow/master/'+kind,'POST',{'values':values},201)
        def command(cid,action,values):
            current=request('/api/repair-orders/'+str(cid))
            return request(f'/api/repair-orders/{cid}/actions/{action}','POST',{'request_id':secrets.token_hex(16),'version':current['version'],'values':values})
        def upload_api(cid,label,category='evidence'):
            result=admin.evaluate('''async({id,label,category})=>{const token=document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=')[1];const fd=new FormData();fd.append('category',category);fd.append('file',new Blob([label],{type:'text/plain'}),label+'.txt');const r=await fetch('/api/flow/cases/'+id+'/files',{method:'POST',headers:{'X-CSRF-Token':token,'X-Store-ID':'1'},body:fd});return{status:r.status,body:await r.json()};}''',{'id':cid,'label':label,'category':category})
            assert result['status']==200,result;return result['body']['id']
        customer=master('customers',{'name':'合成原责任返修客户','phone':'13900007788','contact_allowed':True,'note':''})
        account=master('accounts',{'name':'合成客户实际收款账户','account_type':'bank','active':True})
        vehicle=request('/api/customer-service/vehicles','POST',{'request_id':secrets.token_hex(16),'values':{'customer_id':customer['id'],'vin':'LFV2A21K9J1234567','plate':'合成返A001','model_name':'虚构车型','source_reference':'现场核验原车VIN合成凭据','confirmed':True}},201)['vehicle']
        work=request('/api/masters/work_items','POST',{'request_id':secrets.token_hex(16),'values':{'code':'REWORK-WORK','name':'合成维修作业','billing_unit':'job','standard_fee_cents':600}},201)
        original=request('/api/repair-orders','POST',{'request_id':secrets.token_hex(16),'customer_id':customer['id'],'plate':vehicle['plate'],'problem':'合成原已修项目','due_date':datetime.now().date().isoformat()},201);oid=original['id']
        original=command(oid,'quote',{'reason':'原维修真实接口合成报价','lines':[{'kind':'work','source_id':work['id'],'quantity_milli':1000,'unit_price_cents':1000}]});qid=original['quotes'][-1]['id']
        command(oid,'price_approve',{'quote_id':qid,'minimum_total_cents':0,'allow_below_minimum':False,'reason':'核对原维修价格'})
        command(oid,'authorize',{'quote_id':qid,'evidence_id':upload_api(oid,'原客户报价授权','authorization')})
        command(oid,'start',{'result':'原维修实际开始'});command(oid,'finish',{'result':'原维修实际完成'})
        original_proof=upload_api(oid,'原质检与责任核验','inspection');command(oid,'quality',{'passed':True,'result':'原维修质检通过','evidence_id':original_proof})
        original=command(oid,'allocate',{'labor_cost_cents':100,'evidence_id':original_proof,'allocations':[{'payer_type':'customer','amount_cents':1000}]})
        command(oid,'receive',{'allocation_id':original['allocations'][0]['id'],'amount_cents':1000,'account_id':account['id'],'reference':'SYNTHETIC-ORIGINAL-CASH','evidence_id':upload_api(oid,'原实际收款','receipt')})
        original=command(oid,'release',{'evidence_id':original_proof})
        request('/api/service-intake/bindings','POST',{'request_id':secrets.token_hex(16),'source_case_id':oid,'source_version':original['version'],'customer_vehicle_id':vehicle['id'],'checked_vin':vehicle['vin'],'source_reference':'依据原维修核验VIN与同一客户','evidence_id':original_proof},201)
        resource=request('/api/service-intake/resources','POST',{'request_id':secrets.token_hex(16),'code':'REWORK-BAY','name':'合成返修实际工位','resource_type':'repair'},201)
        ids={}
        for role in ('service','manager','technician','finance'):
            secret=secrets.token_urlsafe(24);u=request('/api/users','POST',{'username':'rework-'+role,'display_name':'返修验收'+role,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},201);ids[role]=u['id']
            p=page();login_page(p,base,'rework-'+role,secret);p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24);p.locator('#modal [name=new_password]').fill(changed);save_modal(p);login_page(p,base,'rework-'+role,changed);employees[role]=p
        service,manager,tech,finance=(employees[k] for k in ('service','manager','technician','finance'))
        def visit(p,route,title=None):
            p.goto(base+'/?trial='+secrets.token_hex(5)+'#'+route)
            if title:expect(p.locator('#main h1')).to_have_text(title)
            else:expect(p.locator('#main h1')).to_be_visible()
        def fill(p,name,value):p.locator('#modal [name='+name+']').fill(str(value))
        def choose(p,name,value):p.locator('#modal [name='+name+']').select_option(str(value))
        def upload(p,cid,label,category='evidence'):
            p.locator('[data-act=upload]').click();choose(p,'category',category);p.locator('#modal [name=file]').set_input_files({'name':label+'.txt','mimeType':'text/plain','buffer':('合成凭据：'+label).encode()});save_modal(p)
            return next(f['id'] for f in request('/api/flow/cases/'+str(cid))['files'] if f['name']==label+'.txt')
        def handoff(cid,key,role):
            task=next(t for t in request('/api/flow/cases/'+str(cid))['tasks'] if t['key']==key and t['status']=='open')
            if task['assignee_id']!=ids[role]:request('/api/flow/tasks/'+str(task['id'])+'/assign','POST',{'version':task['version'],'assignee_id':ids[role],'reason':'明确合成验收岗位接手人'})
        visit(service,'rework-extensions','原责任与新增自费返修');service.locator('[data-act=rework-new]').click()
        expect(service.locator('#modal [name=source_line]')).to_have_count(1);service.locator('#modal [name=source_line]').check();choose(service,'recipient_id',ids['service']);choose(service,'evidence_id',original_proof);fill(service,'limit','6.00');fill(service,'reason','核对原项目责任，新增洗护自费独立说明')
        assert_fits_mobile(service);shots.append(take_screenshot(service,output,'01_source_consent_employee.png'));save_modal(service)
        grant=request('/api/rework-extensions/grants')['items'][0];route='rework-extensions/'+str(grant['id'])
        assert not service.locator('[data-act=rework-decide][data-key=approve]').count()
        visit(manager,route,'核对原责任授权');manager.locator('[data-act=rework-decide][data-key=approve]').click();fill(manager,'reason','本人独立核对原责任项目和六元上限');save_modal(manager)
        visit(service,route,'核对原责任授权');service.locator('[data-act=rework-receive]').click();choose(service,'resource','合成返修实际工位 · REWORK-BAY');fill(service,'reason','接收本次责任修复及新增自费诉求');save_modal(service)
        r=request('/api/service-intake/reworks')['items'][0];rroute='service-intake/reworks/'+str(r['id']);handoff(r['case_id'],'intake_liability','manager')
        visit(manager,rroute,r['title']);fid=upload(manager,r['case_id'],'接收店承接责任复核');manager.locator('[data-act=intake-action][data-key=approve]').click();fill(manager,'reason','确认承接原责任和新增自费分离');assert manager.locator('#modal [name=internal_name]').count()==0;choose(manager,'evidence_id',fid);save_modal(manager)
        handoff(r['case_id'],'intake_rework_convert','service');visit(service,rroute,r['title']);fid=upload(service,r['case_id'],'本次实际VIN核验','inspection');service.locator('[data-act=intake-action][data-key=convert]').click();fill(service,'checked_vin',vehicle['vin']);fill(service,'odometer_km','10100');choose(service,'evidence_id',fid);save_modal(service)
        r=request('/api/service-intake/reworks/'+str(r['id']));cid=r['repair_case_id'];rr='repair-orders/'+str(cid)
        def current():return request('/api/repair-orders/'+str(cid))
        def action(p,key):p.locator('[data-act=repair-action][data-key='+key+']').click()
        visit(service,rr);action(service,'quote');line=service.locator('[data-rework-line]').first;line.locator('[name=source]').select_option('work:'+str(work['id']));line.locator('[name=source_line_id]').select_option(str(grant['source_lines'][0]['id']));line.locator('[name=price]').fill('6.01');fill(service,'reason','冻结原责任与新增自费范围')
        service.locator('#modal button[type=submit]').click();expect(service.locator('#modal .formerror')).to_contain_text('超过原店本次批准额度');assert not current()['quotes']
        line.locator('[name=price]').fill('6.00');service.locator('[data-act=rework-add-line]').click();second=service.locator('[data-rework-line]').nth(1);second.locator('[name=source]').select_option('work:'+str(work['id']));second.locator('[name=charge_scope]').select_option('customer_extra');second.locator('[name=price]').fill('3.00')
        assert_fits_mobile(service);shots.append(take_screenshot(service,output,'02_split_quote_and_cap_refusal.png'));save_modal(service)
        q=current()['quotes'][-1];handoff(cid,'repair_price_'+str(q['id']),'manager');visit(manager,rr);action(manager,'price_approve');fill(manager,'reason','核对本版原责任六元与新增自费三元');save_modal(manager)
        visit(service,rr);fid=upload(service,cid,'本版新增自费客户授权','authorization');action(service,'authorize');choose(service,'evidence_id',fid);save_modal(service)
        handoff(cid,'repair_work','technician');visit(tech,rr);action(tech,'start');fill(tech,'result','按授权原责任及新增项目实际施工');save_modal(tech);action(tech,'finish');fill(tech,'result','本次原责任和新项目实际完成');save_modal(tech)
        handoff(cid,'repair_quality','service');visit(service,rr);fid=upload(service,cid,'本次质检','inspection');action(service,'quality');fill(service,'result','本次施工质量与安全合格');choose(service,'outcome','合格');choose(service,'evidence_id',fid);save_modal(service)
        visit(manager,rr);fid=upload(manager,cid,'本次分类承担核对');action(manager,'allocate');expect(manager.locator('#modal')).to_contain_text('本次客户新增 3.00 元');assert manager.locator('#modal [name=amount_customer]').count()==0;fill(manager,'labor_cost','1.00');choose(manager,'evidence_id',fid);save_modal(manager)
        visit(finance,rr);fid=upload(finance,cid,'本次新增三元实际到账','receipt');action(finance,'receive');expect(finance.locator('#modal [name=amount]')).to_have_value('3.00');choose(finance,'account_id',account['id']);fill(finance,'reference','SYNTHETIC-EXTRA-CASH');choose(finance,'evidence_id',fid);save_modal(finance)
        visit(service,rr);fid=upload(service,cid,'本次客户实际接车');action(service,'release');choose(service,'evidence_id',fid);save_modal(service)
        visit(finance,rr);assert_fits_mobile(finance);shots.append(take_screenshot(finance,output,'03_original_liability_and_new_cash.png'))
        original=request('/api/repair-orders/'+str(oid));final=current();assert sum(p['amount_cents'] for a in original['allocations'] for p in a['payments'])==1000
        assert sum(p['amount_cents'] for a in final['allocations'] for p in a['payments'])==300 and final['revenue_cents']==300 and final['state']=='completed'
        assert not errors,errors
        return {'mode':'real_http_chrome','file_scan_mode':'structure_only','viewport':'390x844','original_cash_cents':1000,'new_customer_cash_cents':300,'internal_responsibility_cents':600,'screenshots':shots,'javascript_errors':errors,'boundaries':['原单由真实注册接口建立并完成；新返修授权、分类、审批、客户授权、施工、结算及现金由四个员工页面办理','跨店权限由独立API专项验证，本浏览器验证同店新契约','新临时库随机端口，未触碰8000预览']}
    except Exception:
        for name,p in employees.items():take_screenshot(p,output,'failure_'+name+'.png')
        raise
    finally:
        for context in contexts:context.close()

if __name__=='__main__':harness.exercise=exercise;harness.main()
