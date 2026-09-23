"""Original manufacturer income: authority, real cash, source invoice and restore."""
import json,sqlite3,uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal,today
from app.models import CashEntry,Store,User,UserStore
from app.flow_models import Case,Customer,PaymentLink,Account
from app.vehicle_income_models import *
from tests.conftest import login,TEST_DIR
from tests.test_workflow import order,action,seed_car,evidence,detail as source_detail
from tests.test_repair_orders import typed
from tests.test_procurement import bank

API='/api/vehicle-income'

@pytest.fixture(autouse=True)
def restore_income():
    yield
    from app.vehicle_income_integrity import validate
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored);validate(restored)

def setup(c,policy=False):
    account=None;entity=None
    if policy:
        from tests.test_business_entities import setup_policy
        entity,account=setup_policy(c)
    supplier=typed(c,'suppliers',dict(code='INC-'+uuid.uuid4().hex[:8],name='纯合成整车厂家',tax_identifier='SYNTHETIC00000001'))
    source=action(c,action(c,order(c),'approve'),'allocate',{'vehicle_id':seed_car()})
    return supplier,source,account or {'id':bank(c)},entity
def create(c,supplier,source,status=201,body=None):
    body=body or dict(request_id=uuid.uuid4().hex,supplier_id=supplier['id'],supplier_version=supplier['version'],external_reference='SETTLEMENT-'+uuid.uuid4().hex,sources=[dict(source_case_id=source['id'],source_version=source_detail(c,source)['version'])],due_date=today().isoformat(),reason='厂家按真实原车结算其他收入')
    r=c.post(API,json=body);assert r.status_code==status,r.text;return r.json()
def detail(c,row):
    r=c.get(API+'/'+str(row['id']));assert r.status_code==200,r.text;return r.json()
def cmd(c,row,key,v=None,status=200,body=None):
    r=c.post(API+f"/{row['id']}/actions/{key}",json=body or dict(request_id=uuid.uuid4().hex,version=detail(c,row)['version'],values=v or {}));assert r.status_code==status,r.text;return r.json()
def propose(c,row,amount=1000,mode='store_invoice'):
    return cmd(c,row,'propose',dict(target_cents=amount,invoice_mode=mode,due_date=today().isoformat(),reason='核对本次厂家真实结算与开票依据',evidence_id=evidence(c,row)))
def approve(c,row):
    who=c.get('/api/auth/me').json()['username'];login(c,'manager')
    row=cmd(c,row,'approve',dict(revision_id=row['pending_revision_id'],reason='独立核对原车依据和应收目标',evidence_id=evidence(c,row)));login(c,who);return row
def receive(c,row,account,amount,**extra):
    return cmd(c,row,'receive',dict(amount_cents=amount,account_id=account['id'],reference=uuid.uuid4().hex,business_date=today().isoformat(),reason='本人核对厂家实际银行到账',evidence_id=evidence(c,row,'receipt'),**extra))
def refund(c,row,account,original,amount,**extra):
    return cmd(c,row,'refund',dict(original_id=original,amount_cents=amount,account_id=account['id'],reference=uuid.uuid4().hex,business_date=today().isoformat(),reason='本人核对原厂家款实际退回',evidence_id=evidence(c,row,'receipt'),**extra))
def ready(c,amount=1000,mode='store_invoice',policy=False):
    supplier,source,account,entity=setup(c,policy);login(c,'finance');row=approve(c,propose(c,create(c,supplier,source),amount,mode));return row,supplier,source,account,entity

def test_original_income_partial_cash_target_reduction_exact_original_refunds(client):
    row,supplier,source,account,_=ready(client)
    assert row['totals']['target_cents']==1000 and row['totals']['net_received_cents']==0
    row=receive(client,row,account,600);row=receive(client,row,account,400);assert row['state']=='completed'
    first,second=[p['id'] for p in row['payments']]
    row=propose(client,row,450)
    cmd(client,row,'receive',dict(amount_cents=1,account_id=account['id'],reference='blocked-revision',business_date=today().isoformat(),reason='待修订不能额外收款',evidence_id=evidence(client,row,'receipt')),409)
    row=approve(client,row);assert row['totals']['net_received_cents']==1000 and row['totals']['refund_due_cents']==550
    login(client,'admin');wrong={'id':bank(client)};login(client,'finance')
    cmd(client,row,'refund',dict(original_id=second,amount_cents=400,account_id=wrong['id'],reference='wrong-account',business_date=today().isoformat(),reason='不能换账户退款',evidence_id=evidence(client,row,'receipt')),409)
    row=refund(client,row,account,second,400);row=refund(client,row,account,first,150)
    assert row['state']=='completed' and row['totals']['net_received_cents']==450
    assert [r['previous_cents'] for r in row['revisions']]==[0,1000]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==4
        assert not db.scalar(select(PaymentLink.id))
        assert db.get(Case,row['id']).customer_id is None
        assert db.scalar(select(func.count()).select_from(Customer))==1
        assert sum(c.amount_cents*(1 if c.direction=='in' else -1) for c in db.scalars(select(CashEntry)))==450

def test_source_read_roles_unknown_ids_duplicate_reference_and_no_generic_edits(client):
    supplier,source,account,_=setup(client);login(client,'finance')
    body=dict(request_id=uuid.uuid4().hex,supplier_id=supplier['id'],supplier_version=supplier['version'],external_reference='REAL-SETTLEMENT-ONE',sources=[dict(source_case_id=source['id'],source_version=source_detail(client,source)['version'])],due_date=today().isoformat(),reason='明确同一真实结算来源')
    row=create(client,supplier,source,body=body);assert create(client,supplier,source,body=body)==row
    create(client,supplier,source,status=409,body={**body,'request_id':uuid.uuid4().hex})
    bad={**body,'request_id':uuid.uuid4().hex,'external_reference':'WRONG-VIN','sources':[dict(source_case_id=source['id'],source_version=body['sources'][0]['source_version'],vehicle_id=999999)]}
    create(client,supplier,source,status=409,body=bad)
    assert client.post('/api/flow/cases/'+str(row['id'])+'/actions/receive',json=dict(request_id=uuid.uuid4().hex,version=row['version'],values={})).status_code==404
    fid=evidence(client,row)
    for role in ('sales','inventory','service'):
        login(client,role);assert client.get(API+'/'+str(row['id'])).status_code==403
        assert client.get('/api/flow/cases/'+str(row['id'])).status_code in {403,404}
        assert client.get('/api/flow/files/'+str(fid)).status_code in {403,404}
    login(client,'admin')
    with SessionLocal() as db:
        db.add(Store(id=2,code='INCO',name='纯合成收入另店'));u=db.scalar(select(User).where(User.username=='admin'));db.add(UserStore(user_id=u.id,store_id=2));db.commit()
    assert client.get(API+'/'+str(row['id']),headers={'X-Store-ID':'2'}).status_code==404
    assert client.post(API,json={**body,'request_id':uuid.uuid4().hex},headers={'X-Store-ID':'2'}).status_code in {404,422}
    assert client.get(API,headers={'X-Store-ID':'all'}).status_code in {403,409}

def test_independent_target_rejection_withdrawal_source_stale_and_cancellation(client):
    supplier,source,account,_=setup(client);login(client,'finance');row=propose(client,create(client,supplier,source))
    cmd(client,row,'approve',dict(revision_id=row['pending_revision_id'],reason='财务没有主管权',evidence_id=evidence(client,row)),403)
    login(client,'admin');cmd(client,row,'approve',dict(revision_id=row['pending_revision_id'],reason='管理员独立于申请人',evidence_id=evidence(client,row)))
    login(client,'finance');row=detail(client,row);row=propose(client,row,900)
    with SessionLocal() as db:c=db.get(Case,source['id']);c.title+=' 来源新事实';db.commit()
    login(client,'manager');cmd(client,row,'approve',dict(revision_id=row['pending_revision_id'],reason='旧来源版本不应通过',evidence_id=evidence(client,row)),409)
    row=cmd(client,row,'reject',dict(revision_id=row['pending_revision_id'],reason='退回重新核对原来源',evidence_id=evidence(client,row)))
    login(client,'finance');row=propose(client,row,800);row=cmd(client,row,'withdraw',dict(revision_id=row['pending_revision_id'],reason='撤回尚未批准的新目标'))
    assert row['totals']['target_cents']==1000
    cmd(client,row,'cancel',dict(reason='不能取消已批准应收'),409)
    fresh=create(client,supplier,source);fresh=propose(client,fresh,200)
    fresh=cmd(client,fresh,'cancel',dict(reason='取消尚未批准申请'));assert fresh['state']=='cancelled'

def test_duplicate_stale_and_competing_actual_cash_use_target_once(client):
    row,supplier,source,account,_=ready(client);proof=evidence(client,row,'receipt')
    body=dict(request_id=uuid.uuid4().hex,version=detail(client,row)['version'],values=dict(amount_cents=700,account_id=account['id'],reference='ONE-ACTUAL-BANK-ROW',business_date=today().isoformat(),reason='原实际收款',evidence_id=proof))
    first=cmd(client,row,'receive',body=body);assert cmd(client,row,'receive',body=body)==first
    cmd(client,row,'receive',status=409,body={**body,'request_id':uuid.uuid4().hex})
    requests=[]
    for n in (1,2):requests.append(dict(request_id=uuid.uuid4().hex,version=detail(client,row)['version'],values=dict(amount_cents=300,account_id=account['id'],reference='FINAL-'+str(n),business_date=today().isoformat(),reason='竞争同一未收余额',evidence_id=evidence(client,row,'receipt'))))
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in requests]
        for c in clients:login(c,'finance')
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(lambda pair:pair[0].post(API+f"/{row['id']}/actions/receive",json=pair[1]).status_code,zip(clients,requests)))
    assert sorted(statuses)==[200,409]
    with SessionLocal() as db:assert db.scalar(select(func.sum(CashEntry.amount_cents)))==1000 and db.scalar(select(func.count()).select_from(VehicleIncomeCash))==2

def test_invoice_basis_supplier_buyer_original_red_and_external_document_mode(client):
    from tests import test_invoices as inv
    row,supplier,source,account,_=ready(client)
    def invoice(amount,original=None,status=201,buyer=None):
        body=inv.request_body(client,row['id'],amount,original);body.update(buyer_name=buyer or supplier['name'],buyer_tax_id=supplier['tax_identifier'])
        result=client.post('/api/invoices/orders',json=body);assert result.status_code==status,result.text;return result.json()
    invoice(1000,status=422,buyer='虚构客户不能代替真实厂家')
    blue=inv.record(client,inv.submit(client,inv.approve(client,invoice(1000))))
    row=approve(client,propose(client,detail(client,row),400));assert inv.read(client,blue['id'])['balance']['correction_cents']==600
    red=inv.record(client,inv.submit(client,inv.approve(client,invoice(600,blue['id']))))
    assert red['balance']['actual_net_cents']==400
    with SessionLocal() as db:assert not db.scalar(select(CashEntry.id))
    row=approve(client,propose(client,detail(client,row),400,'external_document'));invoice(1,status=409)
    assert row['totals']['receivable_cents']==400

def test_formal_original_entity_cash_and_invoice_inherit_without_new_identity(client):
    from tests.test_business_entities import actor
    from app import business_entity_service as entity
    from app.business_entity_models import CaseEntityContext,CashEntityContext
    row,supplier,source,account,revision=ready(client,policy=True);row=receive(client,row,account,1000)
    with SessionLocal() as db:
        user=actor(db)
        with entity.authority(db,user):
            context=db.scalar(select(CaseEntityContext).where(CaseEntityContext.case_id==row['id']));original=db.scalar(select(CaseEntityContext).where(CaseEntityContext.case_id==source['id']))
            assert context.source_case_id==source['id'] and context.derived_kind=='vehicle_income' and context.revision_id==original.revision_id
            assert db.scalar(select(CashEntityContext.case_id).where(CashEntityContext.cash_id==row['payments'][0]['cash_id']))==row['id']
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:validate_sqlite(connection)

def test_quarantine_wrong_source_file_and_immutable_originals(client):
    supplier,source,account,_=setup(client);login(client,'finance');row=create(client,supplier,source);foreign=evidence(client,source)
    cmd(client,row,'propose',dict(target_cents=1000,invoice_mode='store_invoice',due_date=today().isoformat(),reason='不能借原单文件直接作本单事实',evidence_id=foreign),403)
    fid=evidence(client,row)
    from app.file_security import _authority
    from app.file_security_models import FileSecurity
    with SessionLocal() as db:
        with _authority(db):scan=db.scalar(select(FileSecurity).where(FileSecurity.file_id==fid));scan.state='quarantined';db.commit()
    cmd(client,row,'propose',dict(target_cents=1000,invoice_mode='store_invoice',due_date=today().isoformat(),reason='隔离原件不可办理',evidence_id=fid),409)
    row=approve(client,propose(client,row))
    from fastapi import HTTPException
    with SessionLocal() as db:
        revision=db.scalar(select(VehicleIncomeRevision));revision.target_cents=1
        with pytest.raises(HTTPException):db.flush()

def test_restored_target_cash_source_and_independent_authority_tampering_rejected(client):
    row,supplier,source,account,_=ready(client);row=receive(client,row,account,1000)
    from app.vehicle_income_integrity import validate
    sqls=[('UPDATE vehicle_income_revisions SET target_cents=999',()),('UPDATE vehicle_income_cash SET amount_cents=999',()),('UPDATE vehicle_income_decisions SET actor_id=(SELECT actor_id FROM vehicle_income_revisions LIMIT 1)',()),('UPDATE vehicle_income_sources SET snapshot=?',(json.dumps({'case_id':source['id']}),))]
    for sql,args in sqls:
        with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
            original.backup(restored);validate(restored);restored.execute(sql,args)
            with pytest.raises(ValueError,match='整车收入'):validate(restored)

def test_report_period_rows_csv_and_group_store_only_projection(client):
    from tests.test_service_analytics import report,reconciled
    from tests.test_multistore import second_store,switch
    row,supplier,source,account,_=ready(client)
    row=receive(client,row,account,700);row=approve(client,propose(client,row,400))
    data=reconciled(client,'vehicle_other_income_facts',400)
    reconciled(client,'vehicle_other_income_cash',700)
    assert data['metrics']['vehicle_other_income_refund_due_cents']==300
    assert data['metrics']['vehicle_other_income_cash_net_cents']==data['metrics']['cash_in_cents']==700
    assert data['metrics']['vehicle_other_income_recognized_cents']==400
    login(client,'admin');two=second_store(client);switch(client,two)
    empty=report(client)
    assert empty['tables']['vehicle_other_income_facts']['rows']==[]
    assert empty['metrics']['vehicle_other_income_cash_net_cents']==0
    switch(client,'all');aggregate=report(client)
    for key in ('vehicle_other_income_facts','vehicle_other_income_balances','vehicle_other_income_cash'):
        table=aggregate['tables'][key]
        assert len(table['rows'])==1 and table['headers'][0]=='门店'
        assert all(set(r)<={'values','amount_cents','refund_due_cents'} for r in table['rows'])
        assert supplier['name'] not in json.dumps(table,ensure_ascii=False) and row['number'] not in json.dumps(table)
        assert 'route' not in json.dumps(table) and 'revision_id' not in json.dumps(table) and 'cash_id' not in json.dumps(table)
    assert aggregate['metrics']['vehicle_other_income_cash_net_cents']==700
    reconciled(client,'vehicle_other_income_facts',400);reconciled(client,'vehicle_other_income_cash',700)
    switch(client,1);login(client,'sales')
    result=client.get('/api/flow/analytics')
    if result.status_code==200:assert 'vehicle_other_income_facts' not in result.json()['tables']
    else:assert result.status_code==403


def test_formal_unknown_original_and_mixed_identity_sources_fail_closed(client):
    from tests.test_business_entities import actor,case,setup_policy
    from app import business_entity_service as entity
    with SessionLocal() as db:
        user=actor(db);old=case(db,user,state='completed');oldid=old.id;db.commit()
    setup_policy(client)
    # Model a restored, pre-policy delivered original without backfilling legal identity.
    with SessionLocal() as db:db.get(Case,oldid).state='delivered';db.commit()
    supplier,known,account,_=setup(client)
    login(client,'finance')
    original=client.get('/api/flow/cases/'+str(oldid)).json()
    refused=create(client,supplier,original,status=409)
    assert '主体未知' in refused['detail']
    body=dict(request_id=uuid.uuid4().hex,supplier_id=supplier['id'],supplier_version=supplier['version'],external_reference='MIXED-OLD-NEW',sources=[dict(source_case_id=s['id'],source_version=source_detail(client,s)['version']) for s in (original,known)],due_date=today().isoformat(),reason='未知历史不得被本次主体配置补认')
    assert '已知与未知' in create(client,supplier,known,status=409,body=body)['detail']
    with SessionLocal() as db:
        user=actor(db);old=db.get(Case,oldid)
        assert entity.case_entity_snapshot(db,user,old)['status']=='unknown'
        assert not db.scalar(select(VehicleIncomeOrder.id))


def test_zero_target_requires_initial_positive_then_competing_full_original_refund(client):
    supplier,source,account,_=setup(client);login(client,'finance');row=create(client,supplier,source)
    cmd(client,row,'propose',dict(target_cents=0,invoice_mode='external_document',due_date=today().isoformat(),reason='初次零元没有应收事实',evidence_id=evidence(client,row)),422)
    row=approve(client,propose(client,row,1000,'external_document'))
    cmd(client,row,'receive',dict(amount_cents=1001,account_id=account['id'],reference='OVER-TARGET',business_date=today().isoformat(),reason='不能超收本版应收',evidence_id=evidence(client,row,'receipt')),409)
    cmd(client,row,'receive',dict(amount_cents=1,account_id=account['id'],reference='FUTURE',business_date=(today()+timedelta(days=1)).isoformat(),reason='未来不是真实到账',evidence_id=evidence(client,row,'receipt')),422)
    row=receive(client,row,account,1000);original=row['payments'][0]['id']
    row=approve(client,propose(client,row,0,'external_document'))
    assert row['totals']['refund_due_cents']==1000 and row['totals']['target_cents']==0
    requests=[]
    for n in (1,2):requests.append(dict(request_id=uuid.uuid4().hex,version=detail(client,row)['version'],values=dict(original_id=original,amount_cents=1000,account_id=account['id'],reference='REFUND-'+str(n),business_date=today().isoformat(),reason='竞争原款退款不重复',evidence_id=evidence(client,row,'receipt'))))
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in requests]
        for c in clients:login(c,'finance')
        with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(lambda pair:pair[0].post(API+f"/{row['id']}/actions/refund",json=pair[1]).status_code,zip(clients,requests)))
    assert sorted(statuses)==[200,409]
    final=detail(client,row);assert final['state']=='completed' and final['totals']['net_received_cents']==0
    with SessionLocal() as db:assert len(list(db.scalars(select(CashEntry))))==2


def test_supplier_and_account_renames_do_not_relabel_original_cash_or_buyer(client):
    from app.master_models import Supplier
    row,supplier,source,account,_=ready(client)
    row=receive(client,row,account,1000)
    with SessionLocal() as db:
        db.get(Supplier,supplier['id']).name='变更后名称不得替换原主体';db.get(Account,account['id']).name='变更后账户名称';db.commit()
    row=detail(client,row)
    assert row['supplier']['name']==supplier['name'] and row['payments'][0]['account_snapshot']['name']!='变更后账户名称'
    row=approve(client,propose(client,row,0));row=refund(client,row,account,row['payments'][0]['id'],1000)
    assert row['payments'][-1]['account_snapshot']['name']=='变更后账户名称'
    login(client,'auditor');assert detail(client,row)['totals']['net_received_cents']==0
    cmd(client,row,'propose',dict(target_cents=100,invoice_mode='store_invoice',due_date=today().isoformat(),reason='审计岗位不可办理',evidence_id=row['revisions'][0]['evidence_id']),403)

def test_original_sales_vin_survives_later_release_and_restore_uses_frozen_event(client):
    from tests import test_sales_quotes as sales
    from app.flow_models import VehicleHold
    supplier=typed(client,'suppliers',dict(code='INC-SALES-SUP',name='原销售车型返利厂家'))
    source,quote,car,customer=sales.setup(client);source=sales.approve(client,source);source=action(client,source,'allocate',dict(vehicle_id=car))
    login(client,'finance');row=approve(client,propose(client,create(client,supplier,source),1000))
    assert row['sources'][0]['allocation_event_id'] and row['sources'][0]['vehicle_id']==car
    login(client,'admin');source=action(client,source,'release_vehicle',dict(reason='客户原车需改配，保留已确认原厂家事实',evidence_id=evidence(client,source)))
    with SessionLocal() as db:assert not db.scalar(select(VehicleHold).where(VehicleHold.case_id==source['id']))
    assert detail(client,row)['sources'][0]['vehicle_id']==car
    from app.vehicle_income_integrity import validate
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:validate(connection)


def test_account_rename_does_not_reuse_same_actual_bank_reference(client):
    row,supplier,source,account,_=ready(client)
    row=receive(client,row,account,500)
    original_reference=row['payments'][0]['reference']
    with SessionLocal() as db:db.get(Account,account['id']).name='相同原账户的新展示名称';db.commit()
    cmd(client,row,'receive',dict(amount_cents=500,account_id=account['id'],reference=original_reference,business_date=today().isoformat(),reason='展示名称变化不能让同一流水重复',evidence_id=evidence(client,row,'receipt')),409)
    assert detail(client,row)['totals']['net_received_cents']==500
