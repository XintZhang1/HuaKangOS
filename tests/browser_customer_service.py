"""Real employee browser: customer vehicles, care tasks, reminders and revocable history.

Uses only an isolated synthetic database and random credentials; no external messages.
"""
from pathlib import Path
import argparse,json,os,re,secrets,socket,subprocess,sys,tempfile,time
import httpx
from playwright.sync_api import sync_playwright,expect
from browser_huakangos import chromium_path,checked_request,request,login_page,navigate,save_modal,assert_fits_mobile
from browser_masters import employee_login,take_screenshot

ROOT=Path(__file__).resolve().parents[1]
API='/api/customer-service'
VIN='LFV2A21K9J1234567'


def relative(page,days):return page.evaluate('(n)=>relativeDay(n)',days)


def ui_vehicle(page,cid,identity=None):
    navigate(page,'customer-vehicles','客户车辆档案');page.locator('[data-act=care-vehicle-new]').click()
    page.locator('#modal [name=customer_id]').select_option(str(cid))
    page.locator('#modal [name=vin]').fill(VIN)
    page.locator('#modal [name=plate]').fill('合成A1234')
    page.locator('#modal [name=model_name]').fill('虚构客户车辆')
    if identity:page.locator('#modal [name=customer_identity_id]').fill(str(identity))
    page.locator('#modal [name=source_reference]').fill('客户当面核对身份证明及行驶证的合成凭据')
    page.locator('#modal [name=confirmed]').check();save_modal(page)
    expect(page.locator('#main h1')).to_have_text('客户车辆 · 合成A1234')
    return int(page.url.split('/')[-1])


def ui_observe(page,kind,when,km,until=None):
    page.locator('[data-act=care-observe]').click()
    page.locator('#modal [name=kind]').select_option(kind)
    page.locator('#modal [name=observed_date]').fill(when)
    page.locator('#modal [name=odometer_km]').fill(str(km))
    if until:page.locator('#modal [name=valid_until]').fill(until)
    page.locator('#modal [name=source_reference]').fill('客户当面提供的合成日期里程凭据')
    page.locator('#modal [name=confirmed]').check();save_modal(page)


def ui_rule(page,kind,assignee):
    navigate(page,'customer-reminders','车辆提醒与续保提取')
    page.locator('[name=care_rule_kind]').select_option(kind)
    page.locator('[data-act=care-rule-new]').click()
    page.locator('#modal [name=assignee_id]').select_option(str(assignee))
    save_modal(page)


def care_open(page,case):
    navigate(page,'customer-service/'+str(case['id']),case['subtype_label']+' · '+case['number'])


def ui_start(page):page.locator('[data-act=care-action][data-action=start]').click();save_modal(page)


def exercise(browser,base,password,output):
    contexts=[browser.new_context(viewport={'width':1440,'height':1050},locale='zh-CN') for _ in range(3)]
    errors=[];steps=[];screens=[]
    for context in contexts:context.on('page',lambda page:page.on('pageerror',lambda error:errors.append(str(error))))
    admin,manager,clerk=[c.new_page() for c in contexts]
    try:
        login_page(admin,base,'admin',password)
        two=checked_request(admin,'/api/stores','POST',{'code':'CARE-B','name':'虚构服务乙店','active':True},status=201)['id']
        credentials={};users={}
        for username,role in [('care-manager','manager'),('care-employee','customer_service')]:
            pw=secrets.token_urlsafe(28);credentials[username]=pw
            users[username]=checked_request(admin,'/api/users','POST',{'username':username,'display_name':'合成'+role,'role':role,'password':pw,
                'store_roles':[{'store_id':1,'role':role},{'store_id':two,'role':role}],'can_group_summary':role=='manager'},status=201)['id']
        employee_login(manager,base,'care-manager',credentials['care-manager'])
        employee_login(clerk,base,'care-employee',credentials['care-employee'])
        customer=checked_request(manager,'/api/flow/master/customers','POST',{'values':{'name':'虚构无电话客户','phone':'','contact_allowed':False}},status=201)
        aid=ui_vehicle(manager,customer['id'])
        a=checked_request(manager,API+'/vehicles/'+str(aid))['vehicle']
        assert not a['customer_phone']
        ui_observe(manager,'delivery',relative(manager,-100),100)
        ui_observe(manager,'insurance',relative(manager,0),100,relative(manager,1))
        steps.append('店长从网页登记无电话客户车辆，VIN 与库存分离，交付和保险期限具有日期里程来源')

        ui_rule(manager,'maintenance',users['care-employee']);ui_rule(manager,'renewal',users['care-employee'])
        manager.locator('[data-act=care-generate]').click()
        expect(manager.locator('#main')).to_contain_text('新建 2 条内部任务')
        manager.locator('[data-act=care-generate]').click()
        expect(manager.locator('#main')).to_contain_text('新建 0 条内部任务')
        tasks=checked_request(manager,API+'/cases')['items'];maintenance=next(r for r in tasks if r['subtype']=='maintenance');renewal=next(r for r in tasks if r['subtype']=='renewal')
        assert maintenance['assignee_id']==users['care-employee']
        steps.append('配置保养与续保规则并提取到期任务，重复点击生成不重复派单，经办人为实际客服账号')

        clerk.set_viewport_size({'width':390,'height':844})
        care_open(clerk,maintenance);ui_start(clerk)
        clerk.locator('[data-act=care-action][data-action=followup]').click()
        clerk.locator('#modal [name=channel]').select_option('phone')
        clerk.locator('#modal [name=note]').fill('尝试记录未获授权的主动电话跟进')
        clerk.locator('#modal button[type=submit]').click()
        expect(clerk.locator('#modal .formerror')).to_contain_text('客户未允许后续联系或没有电话')
        assert_fits_mobile(clerk);screens.append(take_screenshot(clerk,output,'01_mobile_contact_refusal.png'))
        clerk.locator('#modal [name=channel]').select_option('internal')
        clerk.locator('#modal [name=note]').fill('已在店内核对资料，等待客户主动到店')
        clerk.locator('#modal [name=next_due_date]').fill(relative(clerk,1));save_modal(clerk)
        clerk.locator('[data-act=care-action][data-action=close]').click()
        clerk.locator('#modal [name=result]').select_option('appointment')
        clerk.locator('#modal [name=note]').fill('已记录客户当面约定的后续到店安排');save_modal(clerk)
        expect(clerk.locator('#main')).to_contain_text('已结案')
        screens.append(take_screenshot(clerk,output,'02_mobile_care_completed.png'))
        steps.append('客服手机接手实际任务；无电话或未授权电话被中文拒绝，内部跟进与约定结果分别留档后结案')

        navigate(clerk,'customer-service','客户服务工作台')
        clerk.locator('[name=care_create_type]').select_option('questionnaire');clerk.locator('[data-act=care-new]').click()
        clerk.locator('#modal [name=customer_id]').select_option(str(customer['id']))
        expect(clerk.locator('#modal [name=vehicle_id] option[value="'+str(aid)+'"]')).to_have_count(1)
        clerk.locator('#modal [name=vehicle_id]').select_option(str(aid))
        clerk.locator('#modal [name=topic]').fill('虚构到店问卷')
        clerk.locator('#modal [name=description]').fill('客户当面参与合成服务问卷');save_modal(clerk)
        expect(clerk.locator('#main h1')).to_contain_text('客户问卷 · CC');questionnaire_id=int(clerk.url.split('/')[-1])
        ui_start(clerk);clerk.locator('[data-act=care-action][data-action=close]').click()
        clerk.locator('#modal [name=note]').fill('客户已完成本次问卷')
        clerk.locator('#modal button[type=submit]').click()
        expect(clerk.locator('#modal .formerror')).to_contain_text('满意度与是否愿意推荐')
        assert_fits_mobile(clerk);screens.append(take_screenshot(clerk,output,'03_mobile_questionnaire.png'))
        clerk.locator('#modal [name=satisfaction]').select_option('4');clerk.locator('#modal [name=recommend]').select_option('yes');save_modal(clerk)
        expect(clerk.locator('#main')).to_contain_text('满意度 4 / 5')
        steps.append('客服网页问卷必须记录实际回答，空问卷拒绝结案，满意度与推荐回答按 v1 留存')

        care_open(clerk,renewal);ui_start(clerk);clerk.locator('[data-act=care-action][data-action=close]').click()
        clerk.locator('#modal [name=result]').select_option('renewed');clerk.locator('#modal [name=note]').fill('合成续保办理完成待校验')
        clerk.locator('#modal button[type=submit]').click()
        expect(clerk.locator('#modal .formerror')).to_contain_text('尚无新的保险期限来源登记')
        screens.append(take_screenshot(clerk,output,'04_mobile_renewal_source_refusal.png'))
        clerk.locator('#modal [data-act=close]').first.click()
        navigate(clerk,'customer-vehicles/'+str(aid),'客户车辆 · 合成A1234')
        ui_observe(clerk,'insurance',relative(clerk,0),100,relative(clerk,365))
        care_open(clerk,renewal);clerk.locator('[data-act=care-action][data-action=close]').click()
        clerk.locator('#modal [name=result]').select_option('renewed');clerk.locator('#modal [name=note]').fill('已按新的合成保险凭据登记完整保险期限');save_modal(clerk)
        expect(clerk.locator('#main')).to_contain_text('续保已完成')
        steps.append('续保任务不能凭状态愿望结案，登记新的保险期限来源后才能确认续保完成')

        navigate(manager,'customer-vehicles/'+str(aid),'客户车辆 · 合成A1234');manager.locator('[data-act=care-history-link]').click()
        manager.locator('#modal [name=case_id]').select_option(str(questionnaire_id))
        manager.locator('#modal [name=summary]').fill('客户当面完成服务体验问卷，反馈沟通清楚')
        manager.locator('#modal [name=source_reference]').fill('已核对合成客户及车辆原单')
        manager.locator('#modal [name=confirmed]').check();save_modal(manager)
        manager.locator('#store').select_option(str(two));expect(manager).to_have_url(re.compile(r'#work$'))
        b_customer=checked_request(manager,'/api/flow/master/customers','POST',{'values':{'name':'虚构无电话客户','phone':'','contact_allowed':False}},store=two,status=201)
        bid=ui_vehicle(manager,b_customer['id'],a['customer_identity_id'])
        expect(manager.locator('#main')).to_contain_text('暂无获准服务摘要')
        assert request(manager,'/api/flow/cases/'+str(questionnaire_id),store=two)['status']==404
        manager.locator('#store').select_option('1');expect(manager).to_have_url(re.compile(r'#work$'))
        navigate(manager,'customer-history-grants','跨店服务历史授权');manager.locator('[data-act=care-grant-new]').click()
        manager.locator('#modal [name=from_vehicle_id]').select_option(str(aid));manager.locator('#modal [name=to_store_id]').select_option(str(two))
        manager.locator('#modal [name=to_vehicle_id]').fill(str(bid));manager.locator('#modal [name=source_reference]').fill('客户确认仅提供本车非财务服务摘要')
        manager.locator('#modal [name=confirmed]').check();save_modal(manager)
        clerk.locator('#store').select_option(str(two));expect(clerk).to_have_url(re.compile(r'#work$'))
        navigate(clerk,'customer-vehicles/'+str(bid),'客户车辆 · 合成A1234')
        expect(clerk.locator('#main')).to_contain_text('客户当面完成服务体验问卷，反馈沟通清楚')
        expect(clerk.locator('#main')).to_contain_text('已授权跨店摘要')
        history=checked_request(clerk,API+f'/vehicles/{bid}/history',store=two)['items'][0]
        assert 'case_id' not in history and 'files' not in history and 'amount_cents' not in history
        assert request(clerk,'/api/flow/cases/'+str(questionnaire_id),store=two)['status']==404
        screens.append(take_screenshot(clerk,output,'05_mobile_authorized_history.png'))
        manager.locator('[data-act=care-grant-revoke]').click();manager.locator('#modal [name=reason]').fill('客户已撤回跨店服务历史授权');save_modal(manager)
        clerk.reload();expect(clerk.locator('#store')).to_have_value(str(two))
        expect(clerk).to_have_url(re.compile(r'#customer-vehicles/'+str(bid)+'$'))
        expect(clerk.locator('#main')).to_contain_text('暂无获准服务摘要')
        expect(clerk.locator('#main')).not_to_contain_text('客户当面完成服务体验问卷，反馈沟通清楚')
        screens.append(take_screenshot(clerk,output,'06_mobile_revoked_history.png'))
        steps.append('共享 VIN 与同人关系不自动开放历史；授权后乙店只见最小摘要且原单拒绝；撤销后全页刷新仍留乙店当前车辆，来源摘要立即不可读')
        assert not errors,errors
        return {'mode':'real Chrome HTTP, isolated synthetic customer service','passed':len(steps),'steps':steps,'screenshots':screens,
            'javascript_errors':errors,'limitations':['本地 HTTP 不代表正式 HTTPS 部署验证','无真实客户、外部联络或公司业务数据']}
    finally:
        for context in contexts:context.close()


def main():
    sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--screenshots',type=Path);args=parser.parse_args()
    executable=chromium_path()
    if not executable:raise SystemExit('请安装 Chrome/Edge 或设置 CHROMIUM_PATH。')
    output=(args.screenshots or Path(tempfile.mkdtemp(prefix='huakangos-care-evidence-'))).resolve()
    if output==ROOT or ROOT in output.parents:raise SystemExit('验收输出必须在仓库外。')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='huakangos-care-db-') as directory:
        work=Path(directory)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}';password=secrets.token_urlsafe(28)
        env={**os.environ,'DATABASE_URL':'sqlite:///'+(work/'synthetic.sqlite').as_posix(),'APP_ENV':'test','ALLOWED_HOSTS':'127.0.0.1,localhost','COOKIE_SECURE':'false',
            'FILE_STORAGE_MODE':'blob','PRIVATE_FILE_ROOT':'',
            'SCHEDULER_ENABLED':'false','SCHEDULER_MODE':'off','FILE_SCAN_MODE':'structure_only','ALLOW_AI_EXTERNAL':'false','DEEPSEEK_API_KEY':'','LEGACY_BUSINESS_WRITE':'false',
            'HUAKANGOS_INITIAL_PASSWORD':password,'DEALER_INITIAL_PASSWORD':password,'PYTHONUTF8':'1'}
        initialized=subprocess.run([sys.executable,'-m','app.cli','init'],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
        if initialized.returncode:raise RuntimeError('隔离测试库初始化失败：'+initialized.stderr)
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        with (work/'server.log').open('w',encoding='utf-8') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=flags)
            try:
                with httpx.Client(base_url=base,timeout=2,trust_env=False) as client:
                    for _ in range(120):
                        if server.poll() is not None:raise RuntimeError('隔离测试服务启动失败。')
                        try:
                            if client.get('/api/health').status_code==200:break
                        except httpx.HTTPError:pass
                        time.sleep(.1)
                    else:raise RuntimeError('隔离测试服务未能就绪。')
                with sync_playwright() as p:
                    browser=p.chromium.launch(executable_path=executable,headless=True)
                    try:
                        result=exercise(browser,base,password,output)
                        (output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                        print(json.dumps(result,ensure_ascii=False,indent=2))
                    finally:browser.close()
            finally:
                if os.name=='nt' and server.poll() is None:subprocess.run(['taskkill','/PID',str(server.pid),'/T','/F'],capture_output=True,creationflags=flags)
                elif server.poll() is None:server.terminate()
                try:server.wait(timeout=10)
                except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)


if __name__=='__main__':main()
