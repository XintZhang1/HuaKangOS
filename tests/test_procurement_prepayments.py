"""Registered employee API simulations; every fixture is isolated synthetic data."""
import csv,io,sqlite3,uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal,engine,today
from app.models import CashEntry,Store,User,UserStore
from app.flow_models import Item,StockMove,Task,FileAsset
from app.procurement_models import PurchasePayment
from app.procurement_prepayment_models import PurchasePrepaymentRequest,PurchasePaymentAllocation
from tests.conftest import login,PASSWORD_HASH
from tests.test_procurement import setup,detail,command,receive,bank,return_request,return_action
from tests.test_workflow import evidence


def request(c,row,amount=309,until=None,**kw):
    return command(c,row,'prepay_request',dict(amount_cents=amount,valid_until=(until or today()).isoformat(),
        reason='依据采购合同申请首付款，金额仅财务可见',evidence_id=evidence(c,row,'receipt')),**kw)


def ref(c,row,rid=None):
    r=detail(c,row)['prepayments']['requests'][-1] if rid is None else next(r for r in detail(c,row)['prepayments']['requests'] if r['id']==rid)
    return dict(funds_request_id=r['id'],funds_version=r['version'])


def decide(c,row,action='prepay_approve',**kw):
    return command(c,row,action,{**ref(c,row), 'reason':'独立核对原合同付款条件','evidence_id':evidence(c,row,'receipt')},**kw)


def advance(c,row,account,amount=309,**kw):
    return command(c,row,'prepay_pay',{**ref(c,row),'account_id':account,'amount_cents':amount,
        'reference':uuid.uuid4().hex,'evidence_id':evidence(c,row,'receipt'),'confirmed':True},**kw)


def refund(c,row,payment,amount,account,**kw):
    return command(c,row,'refund',dict(original_payment_id=payment,amount_cents=amount,account_id=account,
        reference=uuid.uuid4().hex,evidence_id=evidence(c,row,'receipt')),**kw)


def approved(c,amount=309):
    row,items,_=setup(c);row=command(c,row,'approve');account=bank(c)
    login(c,'finance');row=request(c,row,amount)
    login(c,'manager');row=decide(c,row)
    login(c,'finance');return row,items,account


def test_prepayment_employee_partial_arrival_termination_return_original_cash_conservation(client):
    row,items,account=approved(client)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==0
        assert db.scalar(select(func.count()).select_from(StockMove))==0
    row=advance(client,row,account,200);row=advance(client,row,account,109)
    assert row['totals']['prepaid_cents']==309 and row['totals']['supplier_refund_due_cents']==0
    assert row['totals']['applied_cents']==0 and row['prepayments']['requests'][0]['status']=='paid'
    payments=[p['id'] for p in row['payments']]
    login(client,'inventory');hidden=receive(client,row,[dict(line_id=row['lines'][0]['id'],quantity_milli=1000)])
    assert 'prepayments' not in hidden and 'totals' not in hidden
    generic=client.get('/api/flow/cases/'+str(row['id'])).json()
    assert '依据采购合同申请首付款' not in str(generic)
    login(client,'manager');row=detail(client,row)
    assert row['totals']['prepaid_cents']==186 and row['totals']['applied_cents']==123
    row=command(client,row,'close_receiving',{'reason':'供应商无法供剩余货物，明确终止未到约定'})
    assert row['totals']['supplier_refund_due_cents']==186 and row['totals']['prepaid_cents']==0
    login(client,'finance');refund(client,row,payments[0],78,account,status=409)
    row=refund(client,row,payments[0],77,account);row=refund(client,row,payments[1],109,account)
    assert row['totals']['paid_net_cents']==123 and row['totals']['supplier_refund_due_cents']==0
    login(client,'inventory');row,ret=return_request(client,row,row['receipts'][0],500)
    login(client,'manager');row=return_action(client,row,ret,'return_approve')
    login(client,'inventory');row=return_action(client,row,ret,'return_dispatch')
    login(client,'finance');row=detail(client,row)
    assert row['totals']['supplier_refund_due_cents']==62 and row['totals']['applied_cents']==61
    row=refund(client,row,payments[0],62,account)
    assert row['state']=='completed' and row['totals']['paid_net_cents']==61
    with SessionLocal() as db:
        item=db.get(Item,items[0]['id']);assert (item.quantity_milli,item.inventory_value_cents)==(500,61)
        cash=list(db.scalars(select(CashEntry)));assert sum(c.amount_cents*(1 if c.direction=='out' else -1) for c in cash)==61
        assert db.scalar(select(func.sum(StockMove.value_cents)))==61
        assert db.scalar(select(func.sum(PurchasePaymentAllocation.amount_cents)))==61
        assert db.scalar(select(func.count()).select_from(PurchasePayment))==5
    with sqlite3.connect(engine.url.database) as db:
        from app.procurement_prepayment_integrity import validate
        assert validate(db)['verified_procurement_prepayments']==1


def test_prepayment_independent_review_refusal_cancel_and_explicit_expiry(client,monkeypatch):
    row,_,_=setup(client);row=command(client,row,'approve')
    row=request(client,row,100);decide(client,row,status=403)
    login(client,'manager');row=decide(client,row,'prepay_reject')
    assert row['prepayments']['requests'][0]['status']=='rejected'
    login(client,'finance');row=request(client,row,100)
    command(client,row,'prepay_expire',{**ref(client,row),'reason':'尚未到期不能自动作废'},409)
    row=command(client,row,'prepay_cancel',{**ref(client,row),'reason':'申请人明确取消未支付申请'})
    row=request(client,row,100)
    from app import procurement_prepayment_service as svc
    monkeypatch.setattr(svc,'today',lambda:today()+timedelta(days=1))
    login(client,'manager');decide(client,row,status=409)
    login(client,'finance');row=command(client,row,'prepay_expire',{**ref(client,row),'reason':'确认原申请有效期已届满'})
    assert [r['status'] for r in row['prepayments']['requests']]==['rejected','cancelled','expired']
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==0
    with sqlite3.connect(engine.url.database) as db:
        from app.procurement_prepayment_integrity import validate
        assert validate(db)['verified_procurement_prepayments']==3


def test_prepayment_reservation_and_full_receipt_do_not_invent_or_duplicate_payment(client):
    row,_,account=approved(client,200)
    login(client,'inventory');receive(client,row)
    login(client,'finance');row=detail(client,row)
    command(client,row,'pay',{'amount_cents':110,'account_id':account,'reference':'reserved','evidence_id':evidence(client,row,'receipt')},409)
    row=advance(client,row,account,200)
    row=command(client,row,'pay',{'amount_cents':109,'account_id':account,'reference':'arrival-balance','evidence_id':evidence(client,row,'receipt')})
    assert row['state']=='completed' and row['totals']['applied_cents']==309 and row['totals']['prepaid_cents']==0
    assert sum(a['amount_cents'] for a in row['prepayments']['allocations'])==309


def test_prepayment_duplicate_stale_strict_amount_and_original_account_guards(client):
    row,_,account=approved(client)
    values={**ref(client,row),'account_id':account,'amount_cents':100,'reference':'one-original','evidence_id':evidence(client,row,'receipt'),'confirmed':True}
    version=detail(client,row)['version'];key=uuid.uuid4().hex
    row=command(client,row,'prepay_pay',values,version=version,request_id=key)
    assert command(client,row,'prepay_pay',values,version=version,request_id=key)==row
    command(client,row,'prepay_pay',values,version=version,status=409)
    command(client,row,'prepay_pay',{**values,**ref(client,row),'confirmed':1},status=422)
    command(client,row,'prepay_pay',{**values,**ref(client,row),'amount_cents':1.5},status=422)
    command(client,row,'prepay_pay',{**values,**ref(client,row),'amount_cents':210},status=409)
    login(client,'manager');row=command(client,row,'close_receiving',{'reason':'停止全部尚未到货的约定'})
    assert row['prepayments']['requests'][0]['status']=='cancelled' and row['totals']['supplier_refund_due_cents']==100
    login(client);other=bank(client);login(client,'finance')
    refund(client,row,row['payments'][0]['id'],100,other,status=409)
    row=refund(client,row,row['payments'][0]['id'],100,account)
    assert row['totals']['paid_net_cents']==0
    with SessionLocal() as db:
        r=db.scalar(select(PurchasePrepaymentRequest));r.amount_cents+=1
        with pytest.raises(HTTPException):db.flush()
        db.rollback()


def test_prepayment_competing_actual_payments_use_parent_and_request_versions(client):
    row,_,account=approved(client,200)
    values={**ref(client,row),'account_id':account,'amount_cents':150,'evidence_id':evidence(client,row,'receipt'),'confirmed':True}
    version=detail(client,row)['version']
    with TestClient(app) as left,TestClient(app) as right:
        login(left,'finance');login(right,'finance')
        def call(c):return c.post(f"/api/procurement/orders/{row['id']}/actions/prepay_pay",json=dict(request_id=uuid.uuid4().hex,version=version,values={**values,'reference':uuid.uuid4().hex})).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(call,[left,right]))
    assert sorted(codes)==[200,409]
    row=detail(client,row);assert row['totals']['paid_net_cents']==150 and row['totals']['prepayment_reserved_cents']==50
    with SessionLocal() as db:assert db.scalar(select(func.sum(CashEntry.amount_cents)))==150


def test_prepayment_return_releases_original_unpaid_authority_and_reuses_cash(client):
    row,_,account=approved(client)
    row=advance(client,row,account,200)
    login(client,'inventory');receive(client,row)
    login(client,'finance');row=detail(client,row)
    assert row['totals']['applied_cents']==200 and row['totals']['payable_cents']==109
    login(client,'inventory');row,ret=return_request(client,row,row['receipts'][0],1000)
    login(client,'manager');return_action(client,row,ret,'return_approve')
    login(client,'inventory');return_action(client,row,ret,'return_dispatch')
    login(client,'finance');row=detail(client,row)
    assert row['prepayments']['requests'][0]['status']=='cancelled'
    assert row['totals']['prepayment_reserved_cents']==0 and row['totals']['applied_cents']==186
    assert row['totals']['supplier_refund_due_cents']==14
    assert any(a['amount_cents']<0 and a['original_id'] for a in row['prepayments']['allocations'])
    refund(client,row,row['payments'][0]['id'],14,account)
    with sqlite3.connect(engine.url.database) as db:
        from app.procurement_prepayment_integrity import validate
        validate(db)


@pytest.mark.parametrize('action',['prepay_request','prepay_approve','prepay_reject','prepay_cancel','prepay_expire','prepay_pay'])
def test_prepayment_all_actions_are_store_scoped(client,action):
    row,_,account=approved(client);r=ref(client,row);fid=evidence(client,row,'receipt')
    login(client)
    other=client.post('/api/stores',json={'code':'OTHER','name':'另一门店','active':True}).json()['id'];client.headers['X-Store-ID']=str(other)
    assert client.get('/api/procurement/orders/'+str(row['id'])).status_code==404
    assert client.get('/api/procurement/payables').json()['prepaid_cents']==0
    values={'prepay_request':dict(amount_cents=1,valid_until=today().isoformat(),reason='其他门店',evidence_id=fid),
        'prepay_approve':{**r,'reason':'其他门店','evidence_id':fid},'prepay_reject':{**r,'reason':'其他门店','evidence_id':fid},
        'prepay_cancel':{**r,'reason':'其他门店'},'prepay_expire':{**r,'reason':'其他门店'},
        'prepay_pay':{**r,'account_id':account,'amount_cents':1,'reference':'cross','evidence_id':fid,'confirmed':True}}[action]
    response=client.post(f"/api/procurement/orders/{row['id']}/actions/{action}",json={'request_id':uuid.uuid4().hex,'version':row['version'],'values':values})
    assert response.status_code==404,response.text


def test_prepayment_foreign_request_proof_quarantine_and_old_cash_cannot_be_reclassified(client,monkeypatch):
    row,_,account=approved(client);r=ref(client,row)
    login(client);other,_,_=setup(client);other=command(client,other,'approve')
    fid=evidence(client,other,'receipt')
    login(client,'finance')
    command(client,row,'prepay_pay',{**r,'account_id':account,'amount_cents':1,'reference':'wrong-proof','evidence_id':fid,'confirmed':True},status=422)
    command(client,other,'prepay_cancel',{**r,'reason':'本店另单原申请不能替换'},status=404)
    from tests.test_file_security import mode
    mode(monkeypatch,'quarantine');fid=evidence(client,row,'receipt')
    command(client,row,'prepay_pay',{**r,'account_id':account,'amount_cents':1,'reference':'bad-proof','evidence_id':fid,'confirmed':True},status=409)
    mode(monkeypatch,'structure_only')
    login(client,'inventory');receive(client,other)
    login(client,'finance');command(client,other,'pay',{'account_id':account,'amount_cents':1,'reference':'old-source','evidence_id':evidence(client,other,'receipt')})
    request(client,other,1,status=409)
    with SessionLocal() as db:assert db.scalar(select(func.sum(CashEntry.amount_cents)))==1


def test_prepayment_reports_csv_and_receipt_balances_reconcile(client):
    row,_,account=approved(client,200);advance(client,row,account,200)
    report=client.get('/api/procurement/payables').json();assert report['prepaid_cents']==200
    exported=list(csv.DictReader(io.StringIO(client.get('/api/procurement/payables/export').content.decode('utf-8-sig'))))
    assert sum(int(r['有效预付（分）']) for r in exported)==report['prepaid_cents']
    login(client,'inventory');receive(client,row,[{'line_id':row['lines'][0]['id'],'quantity_milli':1000}])
    login(client,'finance');report=client.get('/api/procurement/payables').json()
    exported=list(csv.DictReader(io.StringIO(client.get('/api/procurement/payables/export').content.decode('utf-8-sig'))))
    assert sum(int(r['有效预付（分）']) for r in exported)==report['prepaid_cents']==77
    assert sum(int(r['到货原款抵用（分）']) for r in exported)==123
    with SessionLocal() as db:assert db.scalar(select(func.sum(PurchasePaymentAllocation.amount_cents)))==123


def test_prepayment_manager_request_uses_another_admin_and_retains_explicit_handoff(client):
    row,_,_=setup(client);row=command(client,row,'approve')
    login(client,'manager');row=request(client,row,100);decide(client,row,status=403)
    login(client);row=decide(client,row)
    assert row['prepayments']['requests'][0]['status']=='approved'
    with SessionLocal() as db:
        task=db.scalar(select(Task).where(Task.case_id==row['id'],Task.key.like('procurement_prepay_pay_%')))
        assert task.role=='finance'
        finance=db.scalar(select(User).where(User.username=='finance'));assert task.assignee_id==finance.id


def test_prepayment_payment_competes_with_contract_remainder_termination(client):
    row,_,account=approved(client,200)
    values={**ref(client,row),'account_id':account,'amount_cents':200,'reference':'competing-close','evidence_id':evidence(client,row,'receipt'),'confirmed':True}
    version=detail(client,row)['version']
    with TestClient(app) as cashier,TestClient(app) as manager:
        login(cashier,'finance');login(manager,'manager')
        def call(pair):
            c,action,v=pair
            return c.post(f"/api/procurement/orders/{row['id']}/actions/{action}",json={'request_id':uuid.uuid4().hex,'version':version,'values':v}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(call,[(cashier,'prepay_pay',values),(manager,'close_receiving',{'reason':'明确停止未到余量'})]))
    assert sorted(codes)==[200,409]
    row=detail(client,row)
    if row['receiving_closed']:
        assert row['totals']['paid_net_cents']==0 and row['prepayments']['requests'][0]['status']=='cancelled'
    else:
        assert row['totals']['paid_net_cents']==200
        login(client,'manager');row=command(client,row,'close_receiving',{'reason':'重新核对已付款后明确停止未到余量'})
        assert row['totals']['supplier_refund_due_cents']==200
    with sqlite3.connect(engine.url.database) as db:
        from app.procurement_prepayment_integrity import validate
        validate(db)


def test_prepayment_competing_original_refunds_do_not_consume_applied_cash(client):
    row,_,account=approved(client,200);row=advance(client,row,account,200)
    login(client,'manager');row=command(client,row,'close_receiving',{'reason':'终止全部未到货约定'})
    login(client,'finance');fid=evidence(client,row,'receipt');row=detail(client,row)
    values=dict(original_payment_id=row['payments'][0]['id'],amount_cents=150,account_id=account,evidence_id=fid)
    with TestClient(app) as left,TestClient(app) as right:
        login(left,'finance');login(right,'finance')
        def call(c):return c.post(f"/api/procurement/orders/{row['id']}/actions/refund",json=dict(request_id=uuid.uuid4().hex,version=row['version'],values={**values,'reference':uuid.uuid4().hex})).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(call,[left,right]))
    assert sorted(codes)==[200,409]
    row=detail(client,row);assert row['totals']['paid_net_cents']==row['totals']['supplier_refund_due_cents']==50
    with sqlite3.connect(engine.url.database) as db:
        from app.procurement_prepayment_integrity import validate
        validate(db)
