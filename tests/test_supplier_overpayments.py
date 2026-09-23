"""Lower approved return targets create liabilities, then real original cash refunds."""
import sqlite3,uuid
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal
from app.models import CashEntry,Store,User,UserStore
from app.business_finance_models import FinanceSupplierRefund,FinanceReturnTargetRevision
from app.backup_integrity import validate_sqlite
from tests.conftest import login,TEST_DIR
from tests import test_business_finance as f,test_finance_corrections as corrections,test_service_analytics as reports


@pytest.fixture(autouse=True)
def restore():
    yield
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored);validate_sqlite(restored)


def overpaid(c,target=100):
    source,account=corrections.supplier_target(c)
    f.command(c,source,'collect',f.proof(c,source,amount_cents=400,account_id=account,reference='REAL-SUPPLIER-400'))
    adjustment=corrections.approve_target(c,corrections.target_adjust(c,source,target),source)
    f.command(c,adjustment,'execute',f.proof(c,adjustment,source_versions=f.versions(c,source['case'])))
    return f.detail(c,source),account


def request(c,source,amount,status=201,original_id=None):
    d=f.detail(c,source);r=d['return_target']
    if original_id is None:
        from app.flow_models import PaymentLink
        with SessionLocal() as db:original_id=db.scalar(select(PaymentLink.id).where(PaymentLink.case_id==source['case']['id'],PaymentLink.direction=='in'))
    return f.create(c,None,'other_return_refund',{'receivable_id':r['receivable_id'],'source_version':d['case']['version'],
        'original_payment_id':original_id,'amount_cents':amount},status)


def approve(c,row,source):return f.approve(c,row,source['case'])


def pay(c,row,source,account,status=200,body=None):
    return f.command(c,row,'execute',f.proof(c,row,account_id=account,reference=uuid.uuid4().hex,source_versions=f.versions(c,source['case'])),status,body)


def test_lower_than_collected_target_creates_liability_then_two_real_refunds(client):
    source,account=overpaid(client);target=source['return_target']
    assert target['target_cents']==100 and target['received_cents']==400 and target['overpayment_cents']==300
    assert source['order']['status']=='approved'
    reports.reconciled(client,'finance_other_returns',0)
    data=reports.reconciled(client,'finance_supplier_overpayments',300)
    assert data['metrics']['receivable_cents']==0 and data['metrics']['cash_in_cents']==400 and data['metrics']['cash_out_cents']==0
    row=approve(client,request(client,source,100),source)
    assert f.detail(client,source)['return_target']['refund_reserved_cents']==100
    wrong=corrections.bank(client);pay(client,row,source,wrong,409);pay(client,row,source,account)
    assert f.detail(client,source)['return_target']['overpayment_cents']==200
    row=approve(client,request(client,source,200),source);pay(client,row,source,account)
    source=f.detail(client,source);assert source['order']['status']=='completed' and source['return_target']['overpayment_cents']==0
    data=reports.reconciled(client,'finance_supplier_overpayments',0)
    assert data['metrics']['cash_in_cents']==400 and data['metrics']['cash_out_cents']==300
    reports.reconciled(client,'finance_allocations',400)
    with SessionLocal() as db:
        facts=list(db.scalars(select(CashEntry)));assert len(facts)==3 and facts[0].amount_cents==400
        assert [c.category for c in facts[1:]]==['business_finance_other_return_refund']*2


@pytest.mark.parametrize('action',['cancel','reject'])
def test_reserved_refund_blocks_target_changes_and_can_be_released(client,action):
    source,account=overpaid(client,target=0);one=request(client,source,400);two=request(client,source,1)
    f.command(client,one,'approve',f.proof(client,one,source_versions=f.versions(client,source['case'])),403)
    one=approve(client,one,source)
    login(client,'manager');f.command(client,two,'approve',f.proof(client,two,source_versions=f.versions(client,source['case'])),409)
    login(client,'finance');corrections.target_adjust(client,source,100,409)
    login(client,'manager');f.command(client,one,action,{'reason':'独立核对后释放未实际退款占额'})
    assert f.detail(client,source)['return_target']['refund_reserved_cents']==0
    login(client,'finance');adjustment=corrections.approve_target(client,corrections.target_adjust(client,source,100),source)
    f.command(client,adjustment,'execute',f.proof(client,adjustment,source_versions=f.versions(client,source['case'])))
    assert f.detail(client,source)['return_target']['overpayment_cents']==300


def test_target_in_progress_blocks_refund_and_cancels_without_erasing_cash(client):
    source,account=overpaid(client);refund=request(client,source,100)
    adjustment=corrections.approve_target(client,corrections.target_adjust(client,source,0),source)
    login(client,'manager');f.command(client,refund,'approve',f.proof(client,refund,source_versions=f.versions(client,source['case'])),409)
    f.command(client,adjustment,'cancel',{'reason':'撤销未执行目标修订并保留实际回款'})
    login(client,'finance');refund=approve(client,refund,source);pay(client,refund,source,account)
    assert f.detail(client,source)['return_target']['overpayment_cents']==200


def test_each_original_receipt_limits_refund_even_when_total_overpayment_is_larger(client):
    source,account=corrections.supplier_target(client)
    for amount in (100,300):
        f.command(client,source,'collect',f.proof(client,source,amount_cents=amount,account_id=account,reference=uuid.uuid4().hex))
    adjustment=corrections.approve_target(client,corrections.target_adjust(client,source,0),source)
    f.command(client,adjustment,'execute',f.proof(client,adjustment,source_versions=f.versions(client,source['case'])))
    from app.flow_models import PaymentLink
    with SessionLocal() as db:
        originals=list(db.scalars(select(PaymentLink.id).where(PaymentLink.case_id==source['case']['id'],PaymentLink.direction=='in').order_by(PaymentLink.id)))
    request(client,source,101,409,originals[0])
    one=approve(client,request(client,source,100,original_id=originals[0]),source);pay(client,one,source,account)
    request(client,source,1,409,originals[0])
    two=approve(client,request(client,source,300,original_id=originals[1]),source);pay(client,two,source,account)
    assert f.detail(client,source)['return_target']['overpayment_cents']==0


def test_same_store_unrelated_customer_receipt_cannot_fund_supplier_refund(client):
    sale,_,customer=f.ready_retail(client);account=f.bank(client)
    from tests import test_retail as retail
    retail.pay(client,sale,100,account)
    from app.flow_models import PaymentLink
    with SessionLocal() as db:foreign=db.scalar(select(PaymentLink.id).where(PaymentLink.case_id==sale['id'],PaymentLink.direction=='in'))
    source,_=overpaid(client)
    request(client,source,1,409,foreign)


def test_original_capacity_stale_duplicate_cross_store_and_foreign_source_refused(client):
    source,account=overpaid(client);request(client,source,301,409)
    row=approve(client,request(client,source,300),source);current=f.detail(client,row)
    body={'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],
        'values':f.proof(client,row,account_id=account,reference='SUPPLIER-REFUND-ONCE',source_versions=f.versions(client,source['case']))}
    result=f.command(client,row,'execute',body=body);assert f.command(client,row,'execute',body=body)==result
    f.command(client,row,'execute',body={**body,'request_id':uuid.uuid4().hex},status=409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==2
    login(client)
    with SessionLocal() as db:
        db.add(Store(id=2,code='SUPPLIER-B',name='合成退款乙店'));db.flush();db.add(UserStore(user_id=db.scalar(select(User.id).where(User.username=='admin')),store_id=2));db.commit()
    client.headers['X-Store-ID']='2';assert client.get(f.API+'/'+str(row['case']['id'])).status_code==404
    f.create(client,None,'other_return_refund',{'receivable_id':source['return_target']['receivable_id'],'source_version':source['case']['version'],'original_payment_id':1,'amount_cents':1},404)


@pytest.mark.parametrize('competitor',['refund','target'])
def test_competing_refund_or_target_approvals_share_original_source_lock(client,competitor):
    source,account=overpaid(client);rows=[request(client,source,200)]
    rows.append(request(client,source,200) if competitor=='refund' else corrections.target_adjust(client,source,0))
    bodies=[]
    for row in rows:
        d=f.detail(client,row);bodies.append({'request_id':uuid.uuid4().hex,'version':d['order']['version'],'case_version':d['case']['version'],
            'values':f.proof(client,row,source_versions=f.versions(client,source['case']))})
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for c in clients:login(c,'manager')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda i:clients[i].post(f.API+f"/{rows[i]['case']['id']}/actions/approve",json=bodies[i]).status_code,range(2)))
    assert sorted(results)==[200,409]


@pytest.mark.parametrize('tamper',['amount','original','batch'])
def test_restore_rejects_supplier_refund_source_tampering(client,tamper):
    source,account=overpaid(client);row=approve(client,request(client,source,100),source);pay(client,row,source,account)
    sql={'amount':'UPDATE business_finance_supplier_refunds SET amount_cents=amount_cents+1',
        'original':'UPDATE business_finance_supplier_refunds SET original_payment_id=99999',
        'batch':"UPDATE flow_payment_links SET original_id=NULL WHERE direction='out'"}[tamper]
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored);validate_sqlite(restored);restored.execute(sql)
        with pytest.raises(ValueError):validate_sqlite(restored)
