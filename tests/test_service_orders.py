"""Services freeze fees/principal and preserve every actual original money path."""
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal,today
from app.models import CashEntry,User,UserStore,Store
from app.flow_models import Case,PaymentLink
from app.service_orders_models import ServiceTenderSlice,ServicePassEntry
from tests.conftest import login,PASSWORD_HASH
from tests.test_workflow import master,evidence,order
from tests.test_repair_orders import typed
from tests.test_procurement import bank

API='/api/service-orders'
def detail(c,row):
    r=c.get(API+f"/{row['id']}");assert r.status_code==200,r.text;return r.json()
def cmd(c,row,action,v=None,status=200,body=None):
    r=c.post(API+f"/{row['id']}/actions/{action}",json=body or dict(request_id=uuid.uuid4().hex,version=detail(c,row)['version'],values=v or {}));assert r.status_code==status,r.text;return r.json()
def proof(c,row,financial=False):return evidence(c,row,'receipt' if financial else 'authorization')
def config(c,path,values):
    r=c.post(API+'/'+path,json={'request_id':uuid.uuid4().hex,**values});assert r.status_code==201,r.text;return r.json()
def setup(c,kind='agency',source=None):
    customer=master(c,'customers',{'name':'合成代办客户','phone':'13900000883','contact_allowed':True,'note':''}) if source is None else {'id':source['customer_id']}
    p=typed(c,'agency_projects',{'code':'SERVICE-'+uuid.uuid4().hex[:8],'name':'合成上牌办理','service_fee_cents':1000,'expected_days':3}) if kind=='agency' else config(c,'income-items',{'code':'SV-'+uuid.uuid4().hex[:8],'name':'合成客户咨询服务','unit':'项','standard_fee_cents':1000})
    payee=config(c,'payees',{'code':'PAY-'+uuid.uuid4().hex[:8],'name':'合成代缴单位','account_name':'合成第三方收款户','account_reference':'SYNTHETIC-ONLY'})
    r=c.post(API,json={'request_id':uuid.uuid4().hex,'subtype':kind,'customer_id':customer['id'],'source_order_id':source['id'] if source else None,'source_version':source['version'] if source else None,'due_date':today().isoformat(),'reason':'客户申请本店实际服务'});assert r.status_code==201,r.text
    return r.json(),p,payee
def quoted(c,row,p,payee=None,discount=3):
    lines=[dict(line_key='fee1',bucket='fee',**({'agency_project_id':p['id']} if row['kind']=='agency' else {'income_item_id':p['id']}),quantity_milli=1000,unit_price_cents=1000,due_date=today().isoformat())]
    if payee:lines.append(dict(line_key='pass1',bucket='pass',payee_id=payee['id'],name='实际牌证代缴本金',quantity_milli=1000,unit_price_cents=2000,due_date=today().isoformat()))
    return cmd(c,row,'quote',dict(lines=lines,discount_cents=discount,reason='逐项核对本次服务报价'))
def approved(c,row):
    old=c.get('/api/auth/me').json()['username'];login(c,'manager');row=cmd(c,row,'approve',dict(minimum_fee_cents=0,allow_below_minimum=False,reason='本人独立核对本版收费',evidence_id=proof(c,row)));login(c,old);return row
def authorized(c,row):return cmd(c,row,'authorize',dict(quote_id=row['quote']['id'],evidence_id=proof(c,row)))
def cash(c,row,action,amount,account,**kw):return cmd(c,row,action,dict(amount_cents=amount,account_id=account,reference=uuid.uuid4().hex,evidence_id=proof(c,row,True),**kw))
def complete_line(c,row,key):
    if row['kind']=='agency':
        row=cmd(c,row,'submit',dict(line_key=key,external_reference='实际受理-'+uuid.uuid4().hex,submitted_on=today().isoformat(),evidence_id=proof(c,row)))
        row=cmd(c,row,'external_result',dict(line_key=key,submission_id=row['submissions'][-1]['id'],outcome='approved',result='经办核对第三方实际办理结果',evidence_id=proof(c,row)))
    return cmd(c,row,'fulfill',dict(line_key=key,result='实际服务已完成并交付客户',evidence_id=proof(c,row)))
def termination(c,row,retained,returns=None):
    if returns is None:
        returns=[]
        for line in row['lines']:
            amount=max(0,line['paid_cents']-retained[line['line_key']])
            for t in row['tenders']:
                if t['amount_cents']>0 and t['line_key']==line['line_key']:
                    take=min(amount,t['available_cents'])
                    if take:returns.append(dict(tender_id=t['id'],amount_cents=take));amount-=take
    return cmd(c,row,'termination',dict(lines=[dict(line_key=l['line_key'],retained_cents=retained[l['line_key']]) for l in row['lines']],returns=returns,reason='客户协商终止，保留实际已履约费用',evidence_id=proof(c,row)))
def apply_termination(c,row):
    p=row['plans'][-1];old=c.get('/api/auth/me').json()['username'];login(c,'manager');row=cmd(c,row,'termination_approve',dict(plan_id=p['id'],evidence_id=proof(c,row)));login(c,old)
    row=cmd(c,row,'consent',dict(plan_id=p['id'],evidence_id=proof(c,row)));return cmd(c,row,'termination_apply',dict(plan_id=p['id'],evidence_id=proof(c,row,True)))

def test_agency_complete_fee_vs_pass_through_cash(client):
    row,p,payee=setup(client);row=authorized(client,approved(client,quoted(client,row,p,payee)));a=bank(client)
    assert row['summary']['customer_due_cents']==2997
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==0
    row=cash(client,row,'receive',1000,a);row=cash(client,row,'receive',1997,a)
    assert sum(t['amount_cents'] for t in row['tenders'] if t['bucket']=='fee')==997
    for t in row['tenders']:
        if t['bucket']=='pass':row=cash(client,row,'disburse',t['amount_cents'],a,tender_id=t['id'])
    row=complete_line(client,row,'fee1');row=complete_line(client,row,'pass1');assert row['state']=='completed'
    with SessionLocal() as db:
        links=list(db.scalars(select(PaymentLink).where(PaymentLink.case_id==row['id'])));assert len(links)==2 and all(p.direction=='in' for p in links)
        cashrows=list(db.scalars(select(CashEntry)));assert sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in cashrows)==997
        from app.service_orders_service import actual_income_rows
        income=actual_income_rows(db,db.get(Case,row['id']));assert sum(r['amount_cents'] for r in income)==997

def test_submitted_rejected_or_supplement_cannot_fake_completion(client):
    row,p,_=setup(client);row=authorized(client,approved(client,quoted(client,row,p)))
    row=cmd(client,row,'submit',dict(line_key='fee1',external_reference='首次提交',submitted_on=today().isoformat(),evidence_id=proof(client,row)))
    row=cmd(client,row,'external_result',dict(line_key='fee1',submission_id=row['submissions'][-1]['id'],outcome='need_documents',result='需补齐真实客户资料',evidence_id=proof(client,row)))
    cmd(client,row,'fulfill',dict(line_key='fee1',result='不能虚构批准',evidence_id=proof(client,row)),409)
    cmd(client,row,'submit',dict(line_key='fee1',external_reference='遗漏关联补件',submitted_on=today().isoformat(),evidence_id=proof(client,row)),409)
    row=cmd(client,row,'submit',dict(line_key='fee1',external_reference='补件第二次',submitted_on=today().isoformat(),supplement_result_id=row['results'][-1]['id'],evidence_id=proof(client,row)))
    row=cmd(client,row,'external_result',dict(line_key='fee1',submission_id=row['submissions'][-1]['id'],outcome='rejected',result='第三方明确拒绝本申请',evidence_id=proof(client,row)))
    cmd(client,row,'cancel',{'reason':'不能抹掉已提交历史'},409)
    row=apply_termination(client,termination(client,row,{'fee1':0}));assert row['state']=='completed' and len(row['results'])==2

def test_performed_fee_retention_thirdparty_return_and_customer_original_refunds(client):
    row,p,payee=setup(client);row=authorized(client,approved(client,quoted(client,row,p,payee)));a=bank(client);row=cash(client,row,'receive',2997,a)
    t=next(t for t in row['tenders'] if t['bucket']=='pass');row=cash(client,row,'disburse',1500,a,tender_id=t['id']);out=row['pass_entries'][0]
    row=complete_line(client,row,'fee1')
    cmd(client,row,'termination',dict(lines=[{'line_key':'fee1','retained_cents':200},{'line_key':'pass1','retained_cents':0}],returns=[],reason='不能先退仍在第三方本金',evidence_id=proof(client,row)),409)
    row=cash(client,row,'thirdparty_return',1500,a,original_id=out['id']);row=apply_termination(client,termination(client,row,{'fee1':200,'pass1':0}));plan=row['plans'][-1]
    for choice in plan['returns']:
        row=cash(client,row,'refund',choice['amount_cents'],a,plan_id=plan['id'],tender_id=choice['tender_id'])
    assert row['summary']['customer_paid_cents']==200 and row['summary']['pass_cash_balance_cents']==0 and row['state']=='completed'
    with SessionLocal() as db:
        from app.service_orders_service import actual_income_rows
        facts=actual_income_rows(db,db.get(Case,row['id']));assert [x['amount_cents'] for x in facts]==[997,-797]
        assert sum(x.amount_cents*(1 if x.direction=='in' else -1) for x in db.scalars(select(CashEntry)))==200

def test_other_customer_income_has_no_fake_thirdparty_approval(client):
    row,p,_=setup(client,'other_income');row=authorized(client,approved(client,quoted(client,row,p)));row=complete_line(client,row,'fee1')
    assert row['summary']['customer_due_cents']==997 and not row['submissions'];row=cash(client,row,'receive',997,bank(client));assert row['state']=='completed'

def test_price_self_approval_current_version_and_append_only_increase(client):
    row,p,_=setup(client);row=quoted(client,row,p)
    cmd(client,row,'quote',dict(lines=[dict(line_key='overflow',bucket='fee',agency_project_id=p['id'],quantity_milli=1_000_000_000,unit_price_cents=1_000_000_000_000,due_date=today().isoformat())],discount_cents=0,reason='拒绝越界而非服务器异常'),422)
    cmd(client,row,'approve',dict(minimum_fee_cents=0,allow_below_minimum=False,reason='不得自己批准自己的报价',evidence_id=proof(client,row)),403)
    row=approved(client,row);oldquote=row['quote']['id'];row=quoted(client,row,p,discount=5)
    cmd(client,row,'authorize',dict(quote_id=oldquote,evidence_id=proof(client,row)),409)
    row=authorized(client,approved(client,row));a=bank(client);row=cash(client,row,'receive',100,a)
    cmd(client,row,'quote',dict(lines=[dict(line_key='fee1',bucket='fee',agency_project_id=p['id'],quantity_milli=1000,unit_price_cents=1100,due_date=today().isoformat())],discount_cents=0,reason='不可改已有收款原行'),409)
    row=cmd(client,row,'quote',dict(lines=[dict(line_key='fee1',bucket='fee',agency_project_id=p['id'],quantity_milli=1000,unit_price_cents=1000,due_date=today().isoformat()),dict(line_key='fee2',bucket='fee',agency_project_id=p['id'],quantity_milli=1000,unit_price_cents=500,due_date=today().isoformat())],discount_cents=1,reason='客户另行增加服务项目'))
    cmd(client,row,'receive',dict(amount_cents=50,account_id=a,reference=uuid.uuid4().hex,evidence_id=proof(client,row,True)),409)
    assert row['quote']['fee_cents']==1494 and row['lines'][0]['amount_cents']==995

def test_replay_stale_decimal_and_competing_collection(client):
    row,p,_=setup(client,'other_income');row=authorized(client,approved(client,quoted(client,row,p)));a=bank(client)
    v=dict(amount_cents=997,account_id=a,reference=uuid.uuid4().hex,evidence_id=proof(client,row,True));body=dict(request_id=uuid.uuid4().hex,version=detail(client,row)['version'],values=v)
    with TestClient(app) as c2:
        login(c2);version=body['version'];v2={**v,'reference':uuid.uuid4().hex,'evidence_id':proof(c2,row,True)}
        body['version']=detail(client,row)['version'];other=dict(request_id=uuid.uuid4().hex,version=body['version'],values=v2)
        def send(c,payload):return c.post(API+f"/{row['id']}/actions/receive",json=payload)
        with ThreadPoolExecutor(2) as pool:
            responses=list(pool.map(lambda pair:send(*pair),[(client,body),(c2,other)]))
        assert sorted(r.status_code for r in responses)==[200,409]
        winner=0 if responses[0].status_code==200 else 1;assert send([client,c2][winner],[body,other][winner]).json()==responses[winner].json()
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==1
    cmd(client,row,'receive',{**v,'amount_cents':1.1},422)

def test_termination_cancel_releases_hold_and_refund_cannot_exceed_original(client):
    row,p,_=setup(client,'other_income');row=authorized(client,approved(client,quoted(client,row,p)));a=bank(client);row=cash(client,row,'receive',997,a)
    row=termination(client,row,{'fee1':100});plan=row['plans'][-1];login(client,'manager');row=cmd(client,row,'termination_approve',dict(plan_id=plan['id'],evidence_id=proof(client,row)));login(client)
    cmd(client,row,'receive',dict(amount_cents=1,account_id=a,reference=uuid.uuid4().hex,evidence_id=proof(client,row,True)),409)
    row=cmd(client,row,'termination_cancel',dict(plan_id=plan['id'],reason='客户撤回未生效方案'));assert row['tenders'][0]['available_cents']==997
    row=apply_termination(client,termination(client,row,{'fee1':100}));plan=row['plans'][-1]
    cmd(client,row,'refund',dict(plan_id=plan['id'],tender_id=row['tenders'][0]['id'],amount_cents=898,account_id=a,reference=uuid.uuid4().hex,evidence_id=proof(client,row,True)),409)
    row=cash(client,row,'refund',500,a,plan_id=plan['id'],tender_id=row['tenders'][0]['id']);row=cash(client,row,'refund',397,a,plan_id=plan['id'],tender_id=row['tenders'][0]['id']);assert row['summary']['customer_paid_cents']==100

def test_employee_scope_and_foreign_original_refused(client):
    row,p,_=setup(client);row=authorized(client,approved(client,quoted(client,row,p)))
    login(client,'inventory');assert client.get(API+f"/{row['id']}").status_code==403
    login(client,'finance');cmd(client,row,'fulfill',dict(line_key='fee1',result='财务不能声明实际服务',evidence_id=1),403)
    login(client)
    with SessionLocal() as db:
        db.add(Store(id=2,code='SO2',name='另一合成门店'));u=User(username='other_service',display_name='另一店服务',role='service',password_hash=PASSWORD_HASH,must_change_password=False);db.add(u);db.flush();db.add(UserStore(user_id=u.id,store_id=2));db.commit()
    with TestClient(app) as c2:
        login(c2,'other_service');assert c2.get(API+f"/{row['id']}").status_code==404

def test_nonempty_restore_rejects_quote_principal_original_refund_tamper(client):
    row,p,payee=setup(client);row=authorized(client,approved(client,quoted(client,row,p,payee)));a=bank(client);row=cash(client,row,'receive',2997,a)
    t=next(t for t in row['tenders'] if t['bucket']=='pass');row=cash(client,row,'disburse',1000,a,tender_id=t['id']);row=cash(client,row,'thirdparty_return',1000,a,original_id=row['pass_entries'][0]['id'])
    row=complete_line(client,row,'fee1');row=apply_termination(client,termination(client,row,{'fee1':200,'pass1':0}));p=row['plans'][-1]
    for choice in p['returns']:row=cash(client,row,'refund',choice['amount_cents'],a,plan_id=p['id'],tender_id=choice['tender_id'])
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.service_orders_backup_integrity import validate
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored);result=validate(restored);assert result['verified_service_orders']==1 and result['verified_service_tenders']==4
        from app.backup_integrity import validate_sqlite
        assert validate_sqlite(restored)['verified_service_orders']==1
        changes=["UPDATE service_lines SET amount_cents=amount_cents+1 WHERE bucket='fee'", "UPDATE service_pass_entries SET amount_cents=amount_cents+1 WHERE purpose='disburse'", "UPDATE service_refunds SET original_tender_id=(SELECT MIN(id) FROM service_tender_slices)", "UPDATE service_orders SET delivery_blocking=1"]
        for sql in changes:
            restored.execute('SAVEPOINT malicious');restored.execute(sql)
            with pytest.raises(ValueError,match='服务'):validate(restored)
            restored.execute('ROLLBACK TO malicious');restored.execute('RELEASE malicious')

def test_advance_allocation_and_original_restore_no_fake_cash(client):
    from tests import test_business_finance as finance
    row,p,_=setup(client,'other_income');row=authorized(client,approved(client,quoted(client,row,p)));customer={'id':row['summary']['customer_id']}
    advance,a=finance.advance(client,customer,997);finance.apply_advance(client,customer,row,997);row=detail(client,row)
    assert row['summary']['customer_due_cents']==0 and row['tenders'][0]['credit_link_id']
    login(client);row=apply_termination(client,termination(client,row,{'fee1':200}));plan=row['plans'][-1]
    row=cmd(client,row,'refund',dict(plan_id=plan['id'],tender_id=row['tenders'][0]['id'],amount_cents=797,evidence_id=proof(client,row,True)))
    assert finance.current_advance(client,customer)['balance_cents']==797 and row['summary']['customer_paid_cents']==200
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==1
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.service_orders_backup_integrity import validate
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:assert validate(db)['verified_service_tenders']==2

def test_one_central_receipt_two_service_orders_and_append_correction(client):
    from tests import test_business_finance as finance
    row,p,_=setup(client,'other_income');row=authorized(client,approved(client,quoted(client,row,p)));customer={'id':row['summary']['customer_id']};a=bank(client)
    data={'request_id':uuid.uuid4().hex,'subtype':'other_income','customer_id':customer['id'],'due_date':today().isoformat(),'reason':'同客户另一项独立服务'}
    result=client.post(API,json=data);assert result.status_code==201,result.text;two=authorized(client,approved(client,quoted(client,result.json(),p)))
    statement=finance.create(client,customer,'statement',{'starts_on':today().isoformat(),'ends_on':today().isoformat()});statement=finance.approve(client,statement)
    amounts=[{'source_case_id':row['id'],'amount_cents':500},{'source_case_id':two['id'],'amount_cents':400}]
    statement=finance.command(client,statement,'collect',finance.proof(client,statement,amount_cents=900,account_id=a,reference='central-service-cash',allocations=amounts,source_versions=finance.versions(client,row,two)))
    with SessionLocal() as db:
        original=db.scalar(select(CashEntry));cash_id=original.id;assert db.scalar(select(func.count()).select_from(CashEntry))==1
        assert len(list(db.scalars(select(PaymentLink).where(PaymentLink.cash_id==cash_id))))==2
    correction=finance.create(client,customer,'correction',{'original_cash_id':cash_id,'amount_cents':800,'account_id':a,'reference':'corrected-service-cash','allocations':[{'source_case_id':row['id'],'amount_cents':300},{'source_case_id':two['id'],'amount_cents':500}]})
    correction=finance.approve(client,correction);finance.command(client,correction,'execute',finance.proof(client,correction,source_versions=finance.versions(client,row,two)))
    assert detail(client,row)['summary']['customer_paid_cents']==300 and detail(client,two)['summary']['customer_paid_cents']==500
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.service_orders_backup_integrity import validate
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:assert validate(db)['verified_service_orders']==2

def test_completed_pass_thirdparty_return_remains_actionable_until_customer_refund(client):
    row,p,payee=setup(client);row=authorized(client,approved(client,quoted(client,row,p,payee)));a=bank(client);row=cash(client,row,'receive',2997,a)
    t=next(t for t in row['tenders'] if t['bucket']=='pass');row=cash(client,row,'disburse',2000,a,tender_id=t['id']);original=row['pass_entries'][0]
    row=complete_line(client,row,'fee1');row=complete_line(client,row,'pass1');assert row['state']=='completed'
    row=cash(client,row,'thirdparty_return',500,a,original_id=original['id']);assert row['state']=='working'
    assert any(t['status']=='open' and t['key']=='serviceorder_resolve_pass' for t in row['tasks'])
    row=apply_termination(client,termination(client,row,{'fee1':997,'pass1':1500}));p=row['plans'][-1]
    row=cash(client,row,'refund',500,a,plan_id=p['id'],tender_id=t['id']);assert row['state']=='completed' and row['summary']['pass_cash_balance_cents']==0

def test_original_receipt_cannot_be_reused_for_second_actual_payment(client):
    row,p,_=setup(client,'other_income');row=authorized(client,approved(client,quoted(client,row,p)));a=bank(client);fid=proof(client,row,True)
    row=cmd(client,row,'receive',dict(amount_cents=100,account_id=a,reference='first-real',evidence_id=fid))
    cmd(client,row,'receive',dict(amount_cents=100,account_id=a,reference='second-fake',evidence_id=fid),409)

def test_competing_refunds_same_original_and_wrong_account(client):
    row,p,_=setup(client,'other_income');row=authorized(client,approved(client,quoted(client,row,p)));a=bank(client);row=cash(client,row,'receive',997,a)
    row=apply_termination(client,termination(client,row,{'fee1':0}));plan=row['plans'][-1];t=row['tenders'][0]
    another=master(client,'accounts',{'name':'不是原付款账户','account_type':'bank','active':True})['id']
    cmd(client,row,'refund',dict(plan_id=plan['id'],tender_id=t['id'],amount_cents=997,account_id=another,reference=uuid.uuid4().hex,evidence_id=proof(client,row,True)),409)
    with TestClient(app) as c2:
        login(c2);fid1=proof(client,row,True);fid2=proof(c2,row,True);version=detail(client,row)['version']
        bodies=[dict(request_id=uuid.uuid4().hex,version=version,values=dict(plan_id=plan['id'],tender_id=t['id'],amount_cents=997,account_id=a,reference=uuid.uuid4().hex,evidence_id=fid)) for fid in (fid1,fid2)]
        with ThreadPoolExecutor(2) as pool:responses=list(pool.map(lambda x:x[0].post(API+f"/{row['id']}/actions/refund",json=x[1]),[(client,bodies[0]),(c2,bodies[1])]))
        assert sorted(r.status_code for r in responses)==[200,409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==2
        assert sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in db.scalars(select(PaymentLink)))==0

def test_quarantined_authorization_and_foreign_source_cannot_be_used(client,monkeypatch):
    row,p,_=setup(client,'other_income');row=approved(client,quoted(client,row,p))
    from app.config import settings
    from app import file_security
    from dataclasses import replace
    with monkeypatch.context() as m:
        m.setattr(file_security,'settings',replace(settings,file_scan_mode='quarantine'));fid=proof(client,row)
        cmd(client,row,'authorize',dict(quote_id=row['quote']['id'],evidence_id=fid),409)
    other,p2,_=setup(client,'other_income');other=approved(client,quoted(client,other,p2))
    cmd(client,row,'authorize',dict(quote_id=row['quote']['id'],evidence_id=proof(client,other)),422)

def test_linked_order_explicit_delivery_gate_only_and_source_version(client):
    from tests.test_workflow import detail as old_detail
    from app.service_orders_service import guard_order_delivery
    from fastapi import HTTPException
    source=order(client);source=old_detail(client,source);row,p,_=setup(client,source=source)
    with SessionLocal() as db:guard_order_delivery(db,db.get(Case,source['id']))
    source=old_detail(client,source);body=dict(request_id=uuid.uuid4().hex,subtype='agency',customer_id=source['customer_id'],source_order_id=source['id'],source_version=source['version'],delivery_blocking=True,due_date=today().isoformat(),reason='客户明确约定交车前办完')
    r=client.post(API,json=body);assert r.status_code==201,r.text;blocking=r.json()
    with SessionLocal() as db:
        with pytest.raises(HTTPException,match='交车前'):guard_order_delivery(db,db.get(Case,source['id']))
    cmd(client,blocking,'cancel',{'reason':'客户取消尚未办理申请'})
    with SessionLocal() as db:guard_order_delivery(db,db.get(Case,source['id']))
    body['request_id']=uuid.uuid4().hex;assert client.post(API,json=body).status_code==409

def test_partial_processing_fee_on_termination_is_only_retained_income(client):
    row,p,_=setup(client);row=authorized(client,approved(client,quoted(client,row,p)));a=bank(client);row=cash(client,row,'receive',997,a)
    row=cmd(client,row,'submit',dict(line_key='fee1',external_reference='已实际申请但客户终止',submitted_on=today().isoformat(),evidence_id=proof(client,row)))
    row=apply_termination(client,termination(client,row,{'fee1':200}));plan=row['plans'][-1];row=cash(client,row,'refund',797,a,plan_id=plan['id'],tender_id=row['tenders'][0]['id'])
    with SessionLocal() as db:
        from app.service_orders_service import actual_income_rows
        facts=actual_income_rows(db,db.get(Case,row['id']));assert len(facts)==1 and facts[0]['amount_cents']==200 and facts[0]['kind']=='retained_fee'

def test_parent_aftercare_requires_explicit_independent_resolution_not_completed_only(client):
    from tests.test_workflow import detail as old_detail
    from app.service_orders_service import guard_parent_aftercare
    from fastapi import HTTPException
    source=old_detail(client,order(client));row,p,payee=setup(client,source=source);row=authorized(client,approved(client,quoted(client,row,p,payee)));a=bank(client);row=cash(client,row,'receive',2997,a)
    t=next(t for t in row['tenders'] if t['bucket']=='pass');row=cash(client,row,'disburse',2000,a,tender_id=t['id']);row=complete_line(client,row,'fee1');row=complete_line(client,row,'pass1');assert row['state']=='completed'
    with SessionLocal() as db:
        with pytest.raises(HTTPException,match='客户同意'):guard_parent_aftercare(db,None,db.get(Case,source['id']))
    row=apply_termination(client,termination(client,row,{'fee1':997,'pass1':2000}));assert row['state']=='completed'
    with SessionLocal() as db:assert guard_parent_aftercare(db,None,db.get(Case,source['id']))=={row['id']}
    from app.db import utcnow
    from app.service_orders_backup_integrity import validate_parent_aftercare_exclusions
    from tests.conftest import TEST_DIR
    import sqlite3
    cutoff=utcnow();excluded=[row['id']]
    row=cash(client,row,'thirdparty_return',500,a,original_id=row['pass_entries'][0]['id'])
    assert row['state']=='working'
    with sqlite3.connect(TEST_DIR/'test.sqlite') as restored:
        assert validate_parent_aftercare_exclusions(restored,source['id'],excluded,cutoff)
        with pytest.raises(ValueError,match='未结清'):validate_parent_aftercare_exclusions(restored,source['id'],excluded)
        with pytest.raises(ValueError,match='清单'):validate_parent_aftercare_exclusions(restored,source['id'],[],cutoff)

def test_cancel_authorized_unperformed_order_has_zero_due_and_no_revenue(client):
    row,p,_=setup(client,'other_income');row=authorized(client,approved(client,quoted(client,row,p)));row=cmd(client,row,'cancel',{'reason':'尚未实际办理前客户取消'})
    assert row['summary']['customer_due_cents']==0 and not row['summary']['authorized']

def test_actual_parent_aftercare_excludes_resolved_principal_and_old_snapshot_survives_new_child(client):
    from tests import test_aftercare as after
    from tests.test_workflow import action as sales_action,seed_car,detail as sales_detail
    source=sales_action(client,order(client,'100.00'),'approve');source=sales_action(client,source,'allocate',{'vehicle_id':seed_car()})
    row,p,payee=setup(client,source=source);row=authorized(client,approved(client,quoted(client,row,p,payee)));a=bank(client);row=cash(client,row,'receive',2997,a)
    t=next(t for t in row['tenders'] if t['bucket']=='pass');row=cash(client,row,'disburse',2000,a,tender_id=t['id']);row=complete_line(client,row,'fee1');row=complete_line(client,row,'pass1')
    after.create(client,source,'sale_termination',status=409)
    row=apply_termination(client,termination(client,row,{'fee1':997,'pass1':2000}))
    first=after.create(client,source,'sale_termination');assert len(first['sources'])==1 and first['sources'][0]['kind']=='order'
    after.cmd(client,first,'cancel',{'reason':'客户先取消本次销售售后'})
    source=sales_detail(client,source);second_child,_,_=setup(client,source=source);cmd(client,second_child,'cancel',{'reason':'尚未实际办理的新增服务撤回'})
    second=after.create(client,source,'sale_termination');second=after.applied(client,after.confirmed(client,after.approved(client,after.plan(client,second,10000,[]))))
    assert second['state']=='completed' and len(second['sources'])==1
    # A later independent third-party return reopens its own task, while both
    # historical parent exclusion proofs remain valid at their request times.
    row=cash(client,row,'thirdparty_return',500,a,original_id=row['pass_entries'][0]['id']);assert row['state']=='working'
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as restored:
        result=validate_sqlite(restored);assert result['verified_aftercare_orders']==2 and result['verified_service_orders']==2
