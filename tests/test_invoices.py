"""Original-source limits, externally attested results and append-only corrections."""
import uuid
from datetime import timedelta
from sqlalchemy import select,func
import pytest
from app.db import SessionLocal,today,utcnow
from app.models import User,CashEntry
from app.flow_models import Case,Task,PaymentLink,StockMove
from app.invoice_models import InvoiceApplication,InvoiceResult
from tests.conftest import login
from tests.test_multistore import second_store,switch


def source(amount=1001):
    with SessionLocal() as db:
        actor=db.scalar(select(User.id).where(User.username=='sales'))
        row=Case(number='INVOICE-SOURCE-'+uuid.uuid4().hex,kind='order',flow_version=2,state='executing',title='虚构有据原单',
            owner_id=actor,created_by=actor,business_date=today(),due_date=today(),amount_cents=amount)
        db.add(row);db.commit();return row.id
def read(client,key):
    response=client.get('/api/invoices/orders/'+str(key));assert response.status_code==200,response.text;return response.json()
def request_body(client,src,amount=1001,original=None):
    srcrow=client.get('/api/flow/cases/'+str(src)).json()
    return {'request_id':uuid.uuid4().hex,'source_case_id':src,'source_version':srcrow['version'],
        'direction':'red' if original else 'blue','original_case_id':original,'amount_cents':amount,
        'issuer_name':'虚构经营主体甲','issuer_tax_id':'TEST00000000000001','buyer_name':'虚构购买方','buyer_tax_id':'',
        'due_date':today().isoformat(),'reason':'合成资料确认开票需求'}
def create(client,src,amount=1001,original=None,status=201):
    response=client.post('/api/invoices/orders',json=request_body(client,src,amount,original));assert response.status_code==status,response.text
    return response.json()
def proof(client,row,category='evidence'):
    r=client.post('/api/flow/cases/'+str(row['id'])+'/files',data={'category':category},files={'file':('合成票据.txt','虚构凭据，只供测试'.encode(),'text/plain')})
    assert r.status_code==200,r.text;return r.json()['id']
def cmd(client,row,action,values=None,status=200,body=None):
    fresh=read(client,row['id'])
    body=body or {'request_id':uuid.uuid4().hex,'version':fresh['version'],'source_version':fresh['source_version'],'values':values or {'reason':'合成办理依据'}}
    r=client.post(f"/api/invoices/orders/{row['id']}/actions/{action}",json=body);assert r.status_code==status,r.text
    return r.json()
def approve(client,row):
    login(client,'manager');row=cmd(client,row,'approve',{'reason':'独立复核来源及抬头','evidence_id':proof(client,row)})
    login(client,'finance');return row
def submit(client,row):return cmd(client,row,'submit',{'reference':'合成外部办理流水','evidence_id':proof(client,row),'reason':'员工实际已提交的凭据'})
def record(client,row,amount=None,number=None):
    return cmd(client,row,'record',{'invoice_number':number or 'TEST-'+uuid.uuid4().hex,'issued_on':today().isoformat(),
        'amount_cents':amount or row['amount_cents'],'evidence_id':proof(client,row,'invoice'),'reason':'实际外部票据核对'})
def actual(client,src,amount=1001,original=None):return record(client,submit(client,approve(client,create(client,src,amount,original))))


def test_blue_partial_red_and_reissue_use_original_amount_and_no_cash(client):
    src=source();login(client,'finance');blue=actual(client,src)
    assert blue['state']=='completed' and blue['balance']['actual_net_cents']==1001
    red=create(client,src,333,blue['id']);assert red['balance']['available_cents']==0
    create(client,src,1,status=409)
    red=record(client,submit(client,approve(client,red)))
    assert red['balance']['actual_net_cents']==668 and red['balance']['available_cents']==333
    red2=actual(client,src,668,blue['id']);assert red2['balance']['actual_net_cents']==0
    create(client,src,1,blue['id'],status=409)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(InvoiceResult))==3
        assert all(db.scalar(select(func.count()).select_from(m))==0 for m in (CashEntry,PaymentLink,StockMove))


def test_duplicate_stale_competing_applications_and_payload_reuse(client):
    src=source();login(client,'finance');body=request_body(client,src,700)
    first=client.post('/api/invoices/orders',json=body);assert first.status_code==201
    repeated=client.post('/api/invoices/orders',json=body);assert repeated.status_code==201 and repeated.json()['id']==first.json()['id']
    other={**body,'request_id':uuid.uuid4().hex};assert client.post('/api/invoices/orders',json=other).status_code==409
    assert client.post('/api/invoices/orders',json={**body,'amount_cents':600}).status_code==409
    create(client,src,302,status=409);create(client,src,301)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(InvoiceApplication))==2


def test_independent_approval_and_action_role(client):
    src=source();row=create(client,src)
    cmd(client,row,'approve',{'reason':'本人重复批准','evidence_id':proof(client,row)},409)
    login(client,'finance');cmd(client,row,'approve',{'reason':'财务不能批准','evidence_id':proof(client,row)},403)
    login(client,'manager');row=cmd(client,row,'approve',{'reason':'另一主管核对','evidence_id':proof(client,row)})
    cmd(client,row,'submit',{'reason':'主管不能替代财务','reference':'fake','evidence_id':proof(client,row)},403)


def test_external_failure_reopens_responsibility_and_cancel_releases_amount(client):
    src=source();login(client,'finance');row=submit(client,approve(client,create(client,src)))
    cmd(client,row,'cancel',status=409)
    row=cmd(client,row,'difference',{'reason':'收到金额不一致结果待核对','external_number':'OUTSIDE-1','observed_amount_cents':2000,'evidence_id':proof(client,row)})
    assert row['state']=='working' and row['result'] is None
    row=cmd(client,row,'failure',{'reason':'外部已撤回未开出发票','evidence_id':proof(client,row)})
    assert row['state']=='pending'
    row=cmd(client,row,'cancel');assert row['state']=='cancelled' and row['balance']['available_cents']==1001
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(InvoiceResult))==0
        assert db.scalar(select(func.count()).select_from(Task).where(Task.case_id==row['id'],Task.status=='open'))==0


def test_business_change_before_submission_blocks_old_application(client):
    src=source();login(client,'finance');row=approve(client,create(client,src))
    with SessionLocal() as db:
        original=db.scalar(select(Case).where(Case.id==src));original.amount_cents=500;db.commit()
    cmd(client,row,'submit',{'reference':'wrong','reason':'原单额度已降低','evidence_id':proof(client,row)},409)
    row=cmd(client,row,'cancel');create(client,src,500)


def test_external_failure_retry_reopens_the_actual_result_task(client):
    src=source();login(client,'finance');row=submit(client,approve(client,create(client,src)))
    row=cmd(client,row,'failure',{'reason':'外部明确失败未开出','evidence_id':proof(client,row)})
    row=record(client,submit(client,row));assert row['state']=='completed'


def test_real_external_result_after_business_change_is_retained_and_adjustment_survives_close(client):
    src=source();login(client,'finance');row=submit(client,approve(client,create(client,src)))
    with SessionLocal() as db:
        original=db.scalar(select(Case).where(Case.id==src));original.state='cancelled';original.updated_at=utcnow();db.commit()
    row=record(client,row);assert row['state']=='resolving' and row['balance']['correction_cents']==1001
    with SessionLocal() as db:
        task=db.scalar(select(Task).where(Task.case_id==src,Task.key=='invoice_adjust'));assert task.status=='open'
        from app.flow_engine import close_tasks
        original=db.scalar(select(Case).where(Case.id==src));actor=db.scalar(select(User).where(User.username=='finance'))
        close_tasks(db,original,actor);db.commit();assert task.status=='open'
    login(client,'manager');row=cmd(client,row,'review_result',{'reason':'确认实际票据，原单冲红另行办理','evidence_id':proof(client,row)})
    login(client,'finance');red=actual(client,src,1001,row['id']);assert red['balance']['correction_cents']==0
    with SessionLocal() as db:assert db.scalar(select(Task.status).where(Task.case_id==src,Task.key=='invoice_adjust'))=='done'


def test_actual_amount_difference_keeps_both_facts_and_requires_independent_review(client):
    src=source(1500);login(client,'finance');row=record(client,submit(client,approve(client,create(client,src,1001))),1100)
    assert row['amount_cents']==1001 and row['result']['amount_cents']==1100 and row['state']=='resolving'
    cmd(client,row,'cancel',status=409)
    login(client,'manager');row=cmd(client,row,'review_result',{'reason':'复核原始票据金额差异','evidence_id':proof(client,row)})
    assert row['balance']['actual_net_cents']==1100


def test_exact_actual_retry_and_unique_external_number(client):
    src=source();login(client,'finance');row=submit(client,approve(client,create(client,src)));fid=proof(client,row,'invoice');r=read(client,row['id'])
    body={'request_id':uuid.uuid4().hex,'version':r['version'],'source_version':r['source_version'],'values':{'invoice_number':'SAME-NUMBER',
        'amount_cents':1001,'issued_on':today().isoformat(),'evidence_id':fid,'reason':'实际原票'}}
    one=cmd(client,row,'record',body=body);again=cmd(client,row,'record',body=body);assert one['result']==again['result']
    second=submit(client,approve(client,create(client,source())))
    values={'invoice_number':'SAME-NUMBER','amount_cents':1001,'issued_on':today().isoformat(),'evidence_id':proof(client,second,'invoice'),'reason':'重复票号'}
    cmd(client,second,'record',values,409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(InvoiceResult))==1


def test_cross_store_all_reads_writes_and_wrong_original_are_refused(client):
    src=source();login(client,'finance');blue=actual(client,src)
    create(client,source(),100,blue['id'],status=404)
    login(client);other=second_store(client);switch(client,other)
    assert client.get('/api/invoices/orders/'+str(blue['id'])).status_code==404
    assert client.get('/api/invoices/sources').json()['items']==[]
    assert client.get('/api/invoices/orders').json()['items']==[]
    response=client.post('/api/invoices/orders/'+str(blue['id'])+'/actions/cancel',json={'request_id':uuid.uuid4().hex,'version':1,'source_version':1,'values':{'reason':'跨店尝试'}})
    assert response.status_code==404
    switch(client,'all');data=client.get('/api/invoices/orders').json();assert len(data['items'])==1
    assert client.post('/api/invoices/orders',json=request_body(client,src,1)).status_code==409


@pytest.mark.parametrize('role',['sales','service','inventory'])
def test_private_invoice_source_files_and_generic_bypass(client,role):
    src=source();login(client,'finance');row=actual(client,src);fid=row['result']['evidence_id']
    login(client,role)
    assert client.get('/api/invoices/orders').status_code==403
    assert client.get('/api/invoices/sources').status_code==403
    assert client.get('/api/flow/cases/'+str(row['id'])).status_code==404
    assert client.get('/api/flow/files/'+str(fid)).status_code==404


def test_future_date_wrong_category_and_red_parties_refused(client):
    src=source();login(client,'finance');row=submit(client,approve(client,create(client,src)))
    values={'invoice_number':'FUTURE','amount_cents':1001,'issued_on':today().isoformat(),'evidence_id':proof(client,row),'reason':'文件类别核对'}
    cmd(client,row,'record',values,422)
    values['evidence_id']=proof(client,row,'invoice');values['issued_on']=(today()+timedelta(days=1)).isoformat();cmd(client,row,'record',values,422)
    row=record(client,row)
    body=request_body(client,src,100,row['id']);body['buyer_name']='不一致的购买方'
    assert client.post('/api/invoices/orders',json=body).status_code==422


def test_old_invoice_reserves_the_same_source_and_v3_cannot_use_generic_action(client):
    src=source();login(client,'finance')
    with SessionLocal() as db:
        original=db.scalar(select(Case).where(Case.id==src));old=Case(number='OLD-INVOICE',kind='invoice',flow_version=2,state='pending',title='历史开票申请',
            parent_id=src,owner_id=original.owner_id,created_by=original.created_by,business_date=today(),due_date=today(),amount_cents=501)
        db.add(old);db.commit()
    row=create(client,src,500);create(client,src,1,status=409)
    response=client.post('/api/flow/cases/'+str(row['id'])+'/actions/invoice_issue',json={'request_id':uuid.uuid4().hex,'version':row['version'],'values':{'invoice_number':'BYPASS','evidence_id':proof(client,row,'invoice')}})
    assert response.status_code==409


def test_two_sessions_compete_for_same_original_red_capacity(client):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi import HTTPException
    from app.tenancy import set_scope,project_user
    from app import invoice_service as service
    src=source();login(client,'finance');blue=actual(client,src);body=request_body(client,src,700,blue['id'])
    body['due_date']=today();body.pop('request_id')
    def attempt(_):
        with SessionLocal() as db:
            set_scope(db,[1],1);actor=project_user(db.scalar(select(User).where(User.username=='finance')),'finance')
            try:service.create(db,actor,uuid.uuid4().hex,body);return 201
            except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(attempt,range(2)))==[201,409]
    assert read(client,blue['id'])['red_available_cents']==301


@pytest.mark.parametrize('tamper',["UPDATE invoice_results SET amount_cents=amount_cents+1", "UPDATE invoice_approvals SET actor_id=(SELECT created_by FROM flow_cases WHERE id=invoice_approvals.case_id)",
    "UPDATE invoice_applications SET buyer_name='changed' WHERE direction='red'", "UPDATE flow_files SET category='evidence' WHERE category='invoice'"])
def test_nonempty_restore_and_tampered_invoice_facts(client,tamper):
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.invoice_backup_integrity import validate_invoices_sqlite
    src=source();login(client,'finance');blue=actual(client,src);actual(client,src,400,blue['id'])
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored);assert validate_invoices_sqlite(restored)=={'verified_invoices':2}
        restored.execute(tamper)
        with pytest.raises(ValueError):validate_invoices_sqlite(restored)


def test_period_actual_invoice_rows_chart_and_csv_share_same_dates(client,monkeypatch):
    import csv,io
    from datetime import date
    from decimal import Decimal
    import app.invoice_service as service
    src=source();login(client,'finance');blue=submit(client,approve(client,create(client,src)))
    def in_period(row,issued):return cmd(client,row,'record',{'invoice_number':uuid.uuid4().hex,'issued_on':issued,'amount_cents':row['amount_cents'],'evidence_id':proof(client,row,'invoice'),'reason':'实际票面日期'})
    blue=in_period(blue,'2026-01-20');red=submit(client,approve(client,create(client,src,333,blue['id'])));in_period(red,'2026-02-20')
    for start,end,expected in [('2026-01-01','2026-01-31',1001),('2026-02-01','2026-02-28',-333)]:
        q={'date_from':start,'date_to':end};r=client.get('/api/flow/analytics',params=q);assert r.status_code==200,r.text;data=r.json()
        assert data['metrics']['invoice_net_cents']==expected
        table=data['tables']['invoices'];chart=next(c for c in data['charts'] if c['id']=='invoices')
        assert sum(x['amount_cents'] for x in table['rows'])==sum(chart['series'][0]['values'])==expected
        r=client.get('/api/flow/analytics/export',params={'dataset':'invoices',**q});values=list(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))))
        assert values[0]==table['headers'] and sum(Decimal(x[-1].removeprefix("'"))*100 for x in values[1:])==expected


def test_actual_retail_return_raises_invoice_adjustment_without_reducing_frozen_quote(client):
    from tests import test_retail as retail
    items,customer,_,_=retail.setup(client)
    order=retail.dispatch(client,retail.authorize(client,retail.approve(client,retail.create(client,items,customer))))
    login(client,'finance');blue=actual(client,order['id'],order['amount_cents'])
    login(client);order,request=retail.request_return(client,order,order['dispatches'][0],500)
    order=retail.ret_cmd(client,order,request,'return_approve');order=retail.ret_cmd(client,order,request,'return_receive')
    assert order['amount_cents']==blue['amount_cents']
    with SessionLocal() as db:assert db.scalar(select(Task.status).where(Task.case_id==order['id'],Task.key=='invoice_adjust'))=='open'
    login(client,'finance');assert read(client,blue['id'])['balance']['correction_cents']==order['totals']['return_reduction_cents']
