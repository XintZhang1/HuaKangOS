"""Real employee callback UI and report/CSV, with declared synthetic historical sources."""
from pathlib import Path
import csv,io,json,secrets,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import browser_huakangos as harness
from playwright.sync_api import expect


def prepare_database(env,work):
    # Only the newly initialized disposable database is passed to this process.
    # These completed historical sources isolate callback/report verification;
    # this is not evidence that sales/repair completion itself was UI-tested.
    code='''
from app.db import SessionLocal,today
from app.models import User
from app.flow_models import Customer,Case
from sqlalchemy import select
with SessionLocal() as db:
    admin=db.scalar(select(User).where(User.username=='admin'))
    customer=Customer(store_id=1,name='虚构回访客户',phone='13900007676',owner_id=admin.id,contact_allowed=True)
    db.add(customer);db.flush()
    for kind,state in [('order','delivered'),('repair','completed'),('callback','completed')]:
        db.add(Case(store_id=1,kind=kind,flow_version=2,state=state,number='SYNTHETIC-CALLBACK-'+kind,
            title='回访统计隔离历史样本',owner_id=admin.id,created_by=admin.id,customer_id=customer.id,
            business_date=today(),due_date=today(),data={'topic':'原回访样本'} if kind=='callback' else {}))
    db.commit()
'''
    completed=subprocess.run([sys.executable,'-c',code],cwd=harness.ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
    if completed.returncode:raise RuntimeError(completed.stderr)


def exercise(browser,base,password,output):
    contexts=[];errors=[];screens=[];req=harness.checked_request
    def page():
        c=browser.new_context(viewport={'width':390,'height':844},locale='zh-CN');contexts.append(c)
        p=c.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page();employee=page();manager=page();finance=page()
    try:
        harness.login_page(admin,base,'admin',password)
        for role,p in [('customer_service',employee),('manager',manager),('finance',finance)]:
            secret=secrets.token_urlsafe(24)
            req(admin,'/api/users','POST',{'username':'callback-'+role,'display_name':'虚构回访'+role,'role':role,'password':secret,'store_roles':[{'store_id':1,'role':role}]},status=201)
            harness.login_page(p,base,'callback-'+role,secret)
            p.locator('#modal [name=current_password]').fill(secret);changed=secrets.token_urlsafe(24)
            p.locator('#modal [name=new_password]').fill(changed);harness.save_modal(p)
            harness.login_page(p,base,'callback-'+role,changed)
        created=[]
        for subtype,label in [('sales_callback','销售回访'),('repair_callback','维修回访')]:
            harness.navigate(employee,'customer-service','客户服务工作台')
            employee.locator('[name=care_create_type]').select_option(subtype)
            employee.locator('[data-act=care-new]').click()
            customers=req(employee,'/api/customer-service/lookup/customers')['items']
            customer=next(r for r in customers if '虚构回访客户' in r['label'])
            employee.locator('#modal [name=customer_id]').select_option(str(customer['id']))
            sources=req(employee,'/api/customer-service/lookup/source_cases?subtype='+subtype+'&customer_id='+str(customer['id']))['items']
            expect(employee.locator('#modal [name=source_case_id] option')).to_have_count(2)
            employee.locator('#modal [name=source_case_id]').select_option(str(sources[0]['id']))
            employee.locator('#modal [name=topic]').fill('原文私密'+label)
            employee.locator('#modal [name=description]').fill('本演练只有虚构当面反馈，不发送外部消息')
            harness.save_modal(employee)
            row=req(employee,'/api/customer-service/cases')['items'][0];created.append(row['id'])
            def action(key,values):
                employee.locator(f'[data-act=care-action][data-action={key}]').click()
                for k,v in values.items():
                    el=employee.locator('#modal [name='+k+']')
                    if el.evaluate('(e)=>e.tagName')=='SELECT':el.select_option(v)
                    else:el.fill(v)
                harness.assert_fits_mobile(employee);harness.save_modal(employee)
            action('start',{})
            if subtype=='sales_callback':
                for _ in range(2):action('followup',{'channel':'internal','contact_result':'progress','note':'仅合成跟进原文'})
                action('close',{'result':'resolved','note':'虚构客户当面确认已解决'})
            else:action('cancel',{'reason':'虚构客户已明确不需本次回访'})
        harness.assert_fits_mobile(employee);screens.append(harness.take_screenshot(employee,output,'01_employee_callback.png'))
        report=req(manager,'/api/flow/analytics');table=report['tables']['callbacks']
        chart=next(c for c in report['charts'] if c['id']=='callback_state')
        assert sum(r['count'] for r in table['rows'])==sum(chart['series'][0]['values'])==3
        assert report['metrics']['callback_completed_count']==2 and report['metrics']['callback_cancelled_count']==1
        harness.navigate(manager,'analytics/customers','数据可视化')
        panel=manager.locator('.chartpanel').filter(has_text='本期回访任务进度')
        expect(panel.locator('svg')).to_be_visible();panel.locator('[data-act=charttable]').click()
        expect(manager.locator('#main h1')).to_have_text('客户回访明细')
        harness.assert_fits_mobile(manager);screens.append(harness.take_screenshot(manager,output,'02_manager_callback_rows.png'))
        with manager.expect_download() as event:manager.locator('[data-act=exporttable]').click()
        event.value.save_as(output/'synthetic-callbacks.csv')
        rows=list(csv.reader(io.StringIO((output/'synthetic-callbacks.csv').read_text(encoding='utf-8-sig'))))
        assert rows[0]==table['headers'] and sum(int(r[-1]) for r in rows[1:])==3
        index=next(i for i,r in enumerate(table['rows']) if r['route']['id']==created[0])
        manager.locator(f'[data-act=drill][data-index="{index}"]').click()
        expect(manager.locator('#main')).to_contain_text('客户服务办理')
        private=req(finance,'/api/flow/analytics')['tables']['callbacks']
        assert sum(r['count'] for r in private['rows'])==3 and all(r['route'] is None for r in private['rows'])
        assert '原文私密' not in str(private) and '13900007676' not in str(private)
        harness.navigate(finance,'table/callbacks','客户回访明细')
        assert finance.locator('[data-act=drill]').count()==0
        harness.assert_fits_mobile(finance);screens.append(harness.take_screenshot(finance,output,'03_finance_counts_only.png'))
        assert not errors,errors
        return {'status':'passed','mode':'real-Windows-Chrome-HTTP','synthetic_only':True,'viewport':'390x844','callback_count':3,
                'completed':2,'cancelled':1,'screenshots':screens,'javascript_errors':errors,
                'steps':['客服创建销售与维修回访，接手、反复跟进、结案及取消实际办理','主管图表、明细、真实CSV下载和原单下钻一致，跟进不重计','财务同数汇总不暴露原文、电话和原单'],
                'limits':['旧callback及已完成销售/维修是明确的合成历史fixture，不能据此证明原销售或维修全过程已通过浏览器验证']}
    finally:
        for c in contexts:c.close()


if __name__=='__main__':
    harness.prepare_database=prepare_database;harness.exercise=exercise;harness.main()
