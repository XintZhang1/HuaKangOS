"""Original sales accessories: versioned consent, real stock/work and dispositions."""
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal,today
from app.models import User,UserStore,Vehicle,CashEntry
from app.flow_models import Case,Item,StockMove,PaymentLink,Task
from app.addon_models import *
from tests.conftest import login,PASSWORD_HASH
from tests.test_workflow import evidence,order,action,seed_car,detail as source_detail
from tests.test_procurement import setup as purchase_setup,command as purchase_command,receive as purchase_receive,bank
from tests.test_repair_orders import typed
API='/api/addon-orders'
@pytest.fixture(autouse=True)
def restore_addon():
    yield
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.addon_backup_integrity import validate
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);validate(restored)
        if restored.execute('SELECT COUNT(*) FROM addon_dispatches').fetchone()[0]:
            restored.execute('UPDATE addon_dispatches SET value_cents=value_cents+1')
            with pytest.raises(ValueError,match='加装'):validate(restored)
@pytest.fixture(autouse=True)
def technician():
    with SessionLocal() as db:
        u=User(username='technician',display_name='合成安装技师',role='technician',password_hash=PASSWORD_HASH,must_change_password=False);db.add(u);db.flush();db.add(UserStore(user_id=u.id,store_id=1));db.commit()
def detail(c,row):
    r=c.get(API+f"/{row['id']}");assert r.status_code==200,r.text;return r.json()
def cmd(c,row,action,v=None,status=200,body=None):
    r=c.post(API+f"/{row['id']}/actions/{action}",json=body or dict(request_id=uuid.uuid4().hex,version=detail(c,row)['version'],values=v or {}));assert r.status_code==status,r.text;return r.json()
def proof(c,row,category='authorization'):return evidence(c,row,category)
def setup(c,source=None):
    purchase,items,_=purchase_setup(c);purchase=purchase_receive(c,purchase_command(c,purchase,'approve'))
    if source is None:source=action(c,action(c,order(c),'approve'),'allocate',{'vehicle_id':seed_car()})
    with SessionLocal() as db:
        from app.flow_models import VehicleHold
        h=db.scalar(select(VehicleHold).where(VehicleHold.case_id==source['id']));vin=db.get(Vehicle,h.vehicle_id).vin if h else ''
    work=typed(c,'work_items',dict(code='AD-'+uuid.uuid4().hex[:6],name='实际销售加装',billing_unit='job',standard_fee_cents=100))
    source=source_detail(c,source);r=c.post(API,json=dict(request_id=uuid.uuid4().hex,source_order_id=source['id'],source_version=source['version'],due_date=today().isoformat(),delivery_blocking=source['state']!='delivered',reason='客户明确销售原单加装'))
    assert r.status_code==201,r.text;return r.json(),items,work,source,vin
def quoted(c,row,items,work,qty=2000,extra=None):
    lines=[dict(line_key='first',item_id=items[0]['id'],work_item_id=work['id'],quantity_milli=qty,goods_unit_cents=500,installation_unit_cents=100)]
    if extra:lines+=extra
    return cmd(c,row,'quote',dict(lines=lines,discount_cents=3 if not row['quote'] else 0,reason='逐项核对商品与安装服务'))
def approved(c,row):
    who=c.get('/api/auth/me').json()['username'];login(c,'manager');row=cmd(c,row,'approve',dict(minimum_cents=0,allow_below_minimum=False,reason='独立批准本次价格',evidence_id=proof(c,row)));login(c,who);return row
def authorized(c,row):return cmd(c,row,'authorize',dict(quote_id=row['quote']['id'],evidence_id=proof(c,row)))
def dispatch(c,row,vin,qty=2000,key='first'):return cmd(c,row,'dispatch',dict(checked_vin=vin,lines=[dict(line_key=key,quantity_milli=qty)],evidence_id=proof(c,row,'evidence')))
def install(c,row,dispatch_id=None,qty=None):
    d=next(d for d in row['dispatches'] if d['id']==dispatch_id) if dispatch_id else row['dispatches'][-1]
    return cmd(c,row,'install',dict(dispatch_id=d['id'],quantity_milli=qty or d['uninstalled_milli'],result='本人实际完成本批安装',evidence_id=proof(c,row,'inspection')))
def quality(c,row,passed=True,i=None):return cmd(c,row,'quality',dict(installation_id=i or row['installations'][-1]['id'],passed=passed,result='实际检查通过' if passed else '检查发现固定件松动',evidence_id=proof(c,row,'inspection')))
def accept(c,row):return cmd(c,row,'accept',dict(quote_id=row['quote']['id'],evidence_id=proof(c,row)))
def pay(c,row,amount,a):return cmd(c,row,'receive',dict(amount_cents=amount,account_id=a,reference=uuid.uuid4().hex,evidence_id=proof(c,row,'receipt')))
def resolution(c,row,kind,qty=500,installed=True):
    if kind=='cancel':line=dict(line_key='first',quantity_milli=qty)
    else:line=dict(dispatch_id=row['dispatches'][0]['id'],installation_id=row['installations'][0]['id'] if installed else None,quantity_milli=qty)
    return cmd(c,row,'resolution',dict(kind=kind,lines=[line],confirm_no_goods_refund=kind=='vehicle_gift',reason='客户明确原单实物及保留费处置',evidence_id=proof(c,row)))
def resolve(c,row,action,**extra):
    who=c.get('/api/auth/me').json()['username']
    if action in {'resolution_approve','resolution_reject'}:login(c,'manager')
    category='authorization' if action.startswith('resolution_') else 'inspection'
    row=cmd(c,row,action,dict(resolution_id=row['plans'][-1]['id'],result='本人确认当前原单实际处理',evidence_id=proof(c,row,category),**extra))
    if action in {'resolution_approve','resolution_reject'}:login(c,who)
    return row
def refund(c,row,a,amount):return cmd(c,row,'refund',dict(resolution_id=row['plans'][-1]['id'],kind='cash',original_id=next(p['id'] for p in row['payments'] if p['direction']=='in'),amount_cents=amount,account_id=a,reference=uuid.uuid4().hex,evidence_id=proof(c,row,'receipt')))
def completed(c):
    row,items,work,source,vin=setup(c);row=authorized(c,approved(c,quoted(c,row,items,work)));a=bank(c);row=pay(c,row,1197,a);row=accept(c,quality(c,install(c,dispatch(c,row,vin))));return row,items,work,source,vin,a

def test_authorize_actual_install_fail_rectify_and_original_partial_return(client):
    row,items,work,source,vin=setup(client);row=quoted(client,row,items,work)
    with SessionLocal() as db:assert db.get(Item,items[0]['id']).quantity_milli==2500 and not db.scalar(select(AddonReservation.id))
    row=authorized(client,approved(client,row));a=bank(client);row=pay(client,row,1197,a);row=dispatch(client,row,vin);row=quality(client,install(client,row),False)
    cmd(client,row,'accept',dict(quote_id=row['quote']['id'],evidence_id=proof(client,row)),409)
    cmd(client,row,'quality',dict(installation_id=row['installations'][0]['id'],passed=True,result='未整改不能放行',evidence_id=proof(client,row,'inspection')),409)
    row=cmd(client,row,'rectify',dict(inspection_id=row['inspections'][0]['id'],result='已重新固定并申请复检',evidence_id=proof(client,row,'inspection')));row=accept(client,quality(client,row))
    assert row['state']=='completed'
    row=resolve(client,resolve(client,resolution(client,row,'return'),'resolution_approve'),'resolution_consent');row=resolve(client,row,'return_receive',passed=False)
    with SessionLocal() as db:assert db.get(Item,items[0]['id']).quantity_milli==500
    cmd(client,row,'resolution_cancel',dict(resolution_id=row['plans'][0]['id'],result='不能删除实际收到事实',evidence_id=proof(client,row)),409)
    row=resolve(client,row,'return_rectify');row=resolve(client,row,'return_receive',passed=True);expected=row['return_postings'][0]['goods_cents'];assert row['totals']['refund_due_cents']==expected
    row=refund(client,row,a,expected);assert row['state']=='completed' and row['totals']['retained_installation_cents']>0
    with SessionLocal() as db:
        item=db.get(Item,items[0]['id']);dispatchrow=db.scalar(select(AddonDispatch));ret=db.scalar(select(AddonReturnPosting));assert item.quantity_milli==1000 and item.inventory_value_cents==308-dispatchrow.value_cents+ret.value_cents
        assert sum(c.amount_cents*(1 if c.direction=='in' else -1) for c in db.scalars(select(CashEntry)))==1197-expected

def test_addition_requires_new_price_and_current_customer_authorization(client):
    row,items,work,source,vin,a=completed(client);old_quote=row['quote']['id'];extra=[dict(line_key='extra',item_id=items[1]['id'],work_item_id=work['id'],quantity_milli=1000,goods_unit_cents=100,installation_unit_cents=50)]
    row=quoted(client,row,items,work,extra=extra)
    cmd(client,row,'dispatch',dict(checked_vin=vin,lines=[dict(line_key='extra',quantity_milli=1000)],evidence_id=proof(client,row,'evidence')),409)
    row=approved(client,row);cmd(client,row,'authorize',dict(quote_id=old_quote,evidence_id=proof(client,row)),409)
    row=authorized(client,row);row=dispatch(client,row,vin,1000,'extra');row=accept(client,quality(client,install(client,row)));assert row['totals']['receivable_cents']==150
    with SessionLocal() as db:
        income=list(db.scalars(select(AddonAcceptance).order_by(AddonAcceptance.id)));assert [x.amount_cents for x in income]==[1197,150]
        assert sum(x.quantity_milli for x in db.scalars(select(AddonReservation)))==0

def test_wrong_vin_cross_original_authority_and_exact_replay(client):
    row,items,work,source,vin=setup(client);row=quoted(client,row,items,work)
    cmd(client,row,'approve',dict(minimum_cents=0,allow_below_minimum=False,reason='管理员仍不可自批',evidence_id=proof(client,row)),403)
    row=approved(client,row);v=dict(quote_id=row['quote']['id'],evidence_id=proof(client,row));body=dict(request_id=uuid.uuid4().hex,version=row['version'],values=v)
    first=cmd(client,row,'authorize',body=body);assert cmd(client,row,'authorize',body=body)==first
    cmd(client,row,'authorize',status=409,body={**body,'request_id':uuid.uuid4().hex})
    cmd(client,row,'dispatch',dict(checked_vin='LDD00000000000000',lines=[dict(line_key='first',quantity_milli=2000)],evidence_id=proof(client,row,'evidence')),409)
    with SessionLocal() as db:assert db.scalar(select(func.sum(AddonReservation.quantity_milli)))==2000 and db.scalar(select(func.count()).select_from(AddonDispatch))==0
    login(client,'technician');cmd(client,row,'receive',dict(amount_cents=1,account_id=1,reference='invalid',evidence_id=1),403)
    response=client.get(API+f"/{row['id']}");assert response.status_code==200 and 'totals' not in response.json() and 'goods_cents' not in response.json()['lines'][0]
    generic=client.get('/api/flow/cases/'+str(row['id']));assert generic.status_code==200 and 'goods_unit_cents' not in generic.text and 'installation_unit_cents' not in generic.text
    assert client.get(f"/api/flow/files/{v['evidence_id']}").status_code in {403,404}
    login(client,'admin')
    with SessionLocal() as db:
        from app.models import Store
        db.add(Store(id=2,code='OTHER',name='另一合成店'));u=db.scalar(select(User).where(User.username=='admin'));db.add(UserStore(user_id=u.id,store_id=2));db.commit()
    assert client.get(API+f"/{row['id']}",headers={'X-Store-ID':'2'}).status_code==404
    assert client.post(API+f"/{row['id']}/actions/dispatch",headers={'X-Store-ID':'2'},json=dict(request_id=uuid.uuid4().hex,version=first['version'],values=dict(checked_vin=vin,lines=[dict(line_key='first',quantity_milli=1000)],evidence_id=v['evidence_id']))).status_code==404

def test_competing_authorization_reserves_item_once_across_cases(client):
    one,items,work,source,vin=setup(client);one=approved(client,quoted(client,one,items,work))
    src=source_detail(client,source);r=client.post(API,json=dict(request_id=uuid.uuid4().hex,source_order_id=src['id'],source_version=src['version'],due_date=today().isoformat(),delivery_blocking=True,reason='另一个明确加装申请'));assert r.status_code==201,r.text
    two=approved(client,quoted(client,r.json(),items,work));requests=[]
    for row in (one,two):requests.append((row,dict(request_id=uuid.uuid4().hex,version=detail(client,row)['version'],values=dict(quote_id=row['quote']['id'],evidence_id=proof(client,row)))))
    from contextlib import ExitStack
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in requests]
        for c in clients:login(c,'admin')
        def post(data):
            c,(row,body)=data
            return c.post(API+f"/{row['id']}/actions/authorize",json=body).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(post,zip(clients,requests)))==[200,409]
    with SessionLocal() as db:assert db.scalar(select(func.sum(AddonReservation.quantity_milli)))==2000 and db.get(Item,items[0]['id']).quantity_milli==2500

def test_unissued_cancel_releases_quantity_and_repeated_refund_refused(client):
    row,items,work,source,vin=setup(client);row=authorized(client,approved(client,quoted(client,row,items,work)));a=bank(client);row=pay(client,row,1197,a)
    row=resolve(client,resolve(client,resolution(client,row,'cancel',2000),'resolution_approve'),'resolution_consent');assert row['totals']['refund_due_cents']==1197
    with SessionLocal() as db:assert db.scalar(select(func.sum(AddonReservation.quantity_milli)))==0 and db.get(Item,items[0]['id']).quantity_milli==2500 and not db.scalar(select(AddonDispatch.id))
    v=dict(resolution_id=row['plans'][0]['id'],kind='cash',original_id=row['payments'][0]['id'],amount_cents=1197,account_id=a,reference=uuid.uuid4().hex,evidence_id=proof(client,row,'receipt'));body=dict(request_id=uuid.uuid4().hex,version=detail(client,row)['version'],values=v)
    result=cmd(client,row,'refund',body=body);assert cmd(client,row,'refund',body=body)==result;cmd(client,row,'refund',v,409)
    assert result['state']=='completed' and result['totals']['charge_cents']==0

def test_actual_failed_return_reject_requires_actual_handback(client):
    row,items,work,source,vin,a=completed(client);row=resolve(client,resolve(client,resolution(client,row,'return'),'resolution_approve'),'resolution_consent');row=resolve(client,row,'return_receive',passed=False)
    row=resolve(client,row,'resolution_reject');assert row['plans'][0]['status']=='handback'
    row=resolve(client,row,'return_handback');assert row['plans'][0]['status']=='rejected' and not row['return_postings'] and row['totals']['refund_due_cents']==0
    with SessionLocal() as db:assert db.get(Item,items[0]['id']).quantity_milli==500

def test_central_advance_restore_and_single_cash_statement(client):
    from tests import test_business_finance as finance
    row,items,work,source,vin=setup(client);row=authorized(client,approved(client,quoted(client,row,items,work)));customer={'id':row['customer_id']};pre,a=finance.advance(client,customer,600);finance.apply_advance(client,customer,row,600)
    assert detail(client,row)['totals']['receivable_cents']==597
    statement=finance.create(client,customer,'statement',dict(starts_on=today().isoformat(),ends_on=today().isoformat()));statement=finance.approve(client,statement)
    assert any(x['source_case_id']==row['id'] for x in statement['lines'])
    statement=finance.command(client,statement,'collect',finance.proof(client,statement,amount_cents=597,account_id=a,reference='addon-consolidated-cash',allocations=[dict(source_case_id=row['id'],amount_cents=597)],source_versions=finance.versions(client,row)))
    login(client,'admin');row=detail(client,row);row=resolve(client,resolve(client,resolution(client,row,'cancel',2000),'resolution_approve'),'resolution_consent')
    original=next(c for c in row['credits'] if c['amount_cents']>0);row=cmd(client,row,'refund',dict(resolution_id=row['plans'][0]['id'],kind='advance',original_id=original['id'],amount_cents=600,evidence_id=proof(client,row,'receipt')))
    row=refund(client,row,a,597);assert row['totals']['paid_cents']==0
    assert finance.current_advance(client,customer)['balance_cents']==600
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==3 and db.scalar(select(func.count()).select_from(AddonPayment))==4

def test_unapproved_invoice_refused_and_distinct_resolution_next_actor(client):
    from tests import test_invoices as invoices
    row,items,work,source,vin=setup(client);row=quoted(client,row,items,work);login(client,'finance');invoices.create(client,row['id'],100,status=409);login(client,'admin');row=authorized(client,approved(client,row));a=bank(client);row=pay(client,row,1197,a)
    with SessionLocal() as db:
        sales_id=db.scalar(select(User.id).where(User.username=='sales'));case=db.get(Case,row['id']);case.owner_id=sales_id;db.commit()
    login(client,'sales');row=resolution(client,detail(client,row),'cancel',2000);row=resolve(client,row,'resolution_approve')
    with SessionLocal() as db:
        task=db.scalar(select(Task).where(Task.case_id==row['id'],Task.key=='addon_resolution_'+str(row['plans'][0]['id']),Task.status=='open'));assert task.assignee_id==sales_id and task.role=='sales'
    row=resolve(client,row,'resolution_consent');login(client,'finance');row=refund(client,row,a,1197);assert row['state']=='completed'

def test_vehicle_return_gift_original_vin_new_generation_no_double_inventory(client):
    from tests import test_vehicle_operations as vehicles
    from tests import test_aftercare as after
    from tests.test_workflow import approved_doc
    purchase,vid,location=vehicles.inventory(client);source=action(client,action(client,order(client,'100.00',model='虚构型号'),'approve'),'allocate',{'vehicle_id':vid})
    fid=approved_doc(client,source,'contract');source=action(client,source,'sign',{'evidence_id':evidence(client,source,'signed_contract',fid)});a=bank(client)
    source=action(client,source,'receive',dict(amount='100.00',account_id=a,reference='original-car-cash',evidence_id=evidence(client,source,'receipt')));source=action(client,source,'inspect',dict(outcome='合格',result='原交车检查合格',evidence_id=evidence(client,source,'inspection')));source=action(client,source,'dispatch',dict(evidence_id=evidence(client,source)))
    fid=approved_doc(client,source,'handover');source=action(client,source,'deliver',{'evidence_id':evidence(client,source,'signed_handover',fid)})
    row,items,work,source,vin=setup(client,source);row=authorized(client,approved(client,quoted(client,row,items,work)));row=pay(client,row,1197,a);row=accept(client,quality(client,install(client,dispatch(client,row,vin))))
    after.create(client,source,'vehicle_return',409)
    row=resolve(client,resolve(client,resolution(client,row,'vehicle_gift',2000),'resolution_approve'),'resolution_consent',confirm_no_goods_refund=True)
    parent=after.create(client,source,'vehicle_return');assert [s['case_id'] for s in parent['sources']]==[source['id']]
    parent=after.confirmed(client,after.approved(client,after.plan(client,parent,10000)))
    after.cmd(client,parent,'apply',dict(evidence_id=evidence(client,parent,'receipt')),409)
    physical=vehicles.get(client,{'id':after.detail(client,parent)['vehicle_return']['operation_case_id']});physical=vehicles.act(client,physical,'intake',{'location_id':location});physical=vehicles.act(client,physical,'inspect',dict(outcome='pass',findings='逐项核对原VIN及随车装件'))
    physical=vehicles.act(client,physical,'disposition',dict(inspection_id=physical['inspections'][-1]['id'],decision='release'));physical=vehicles.act(client,physical,'release',{'location_id':location})
    parent=after.applied(client,parent);parent=after.refund(client,parent,a,10000);assert parent['state']=='completed'
    row=detail(client,row);assert row['plans'][0]['status']=='completed' and row['handovers'][0]['new_vehicle_id']==physical['received_vehicle_id'] and row['totals']['charge_cents']==1197
    with SessionLocal() as db:
        old=db.get(Vehicle,vid);new=db.get(Vehicle,physical['received_vehicle_id']);assert old.purchase_cost_cents==new.purchase_cost_cents and db.get(Item,items[0]['id']).quantity_milli==500
        assert db.scalar(select(func.count()).select_from(AddonReturnPosting))==0
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as conn:validate_sqlite(conn)

def test_original_all_returns_quantity_cost_remainder_and_concurrent_refund(client):
    row,items,work,source,vin,a=completed(client)
    for qty in (333,667,1000):row=resolve(client,resolve(client,resolution(client,row,'return',qty),'resolution_approve'),'resolution_consent');row=resolve(client,row,'return_receive',passed=True)
    with SessionLocal() as db:
        d=db.scalar(select(AddonDispatch));posts=list(db.scalars(select(AddonReturnPosting)));assert sum(p.quantity_milli for p in posts)==d.quantity_milli and sum(p.value_cents for p in posts)==d.value_cents and sum(p.goods_cents for p in posts)==d.goods_cents
        assert db.get(Item,items[0]['id']).quantity_milli==2500 and db.get(Item,items[0]['id']).inventory_value_cents==308
    plan=row['plans'][-1];amount=plan['refund_available_cents'];v=dict(resolution_id=plan['id'],kind='cash',original_id=row['payments'][0]['id'],amount_cents=amount,account_id=a,reference=uuid.uuid4().hex,evidence_id=proof(client,row,'receipt'));body=dict(request_id=uuid.uuid4().hex,version=detail(client,row)['version'],values=v)
    from contextlib import ExitStack
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for c in clients:login(c,'admin')
        def post(c):return c.post(API+f"/{row['id']}/actions/refund",json={**body,'request_id':uuid.uuid4().hex}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(post,clients))==[200,409]

def test_original_procurement_return_cannot_consume_addon_reserved_items(client):
    from tests import test_procurement as purchase
    row,items,work,source,vin=setup(client);row=authorized(client,approved(client,quoted(client,row,items,work)))
    original=client.get('/api/procurement/orders').json()['items'][0];line_id=next(l['id'] for l in original['lines'] if l['item_id']==items[0]['id']);receipt=next(r for r in original['receipts'] if r['line_id']==line_id)
    original,ret=purchase.return_request(client,original,receipt,2000);purchase.return_action(client,original,ret,'return_approve',status=409)
    with SessionLocal() as db:assert db.get(Item,items[0]['id']).quantity_milli==2500 and db.scalar(select(func.sum(AddonReservation.quantity_milli)))==2000
    row=resolve(client,resolve(client,resolution(client,row,'cancel',2000),'resolution_approve'),'resolution_consent');original=purchase.return_action(client,original,ret,'return_approve');purchase.return_action(client,original,ret,'return_dispatch')

def test_cash_correction_preserves_original_link_and_refunds_corrected_source(client):
    from tests import test_business_finance as finance
    row,items,work,source,vin=setup(client);row=authorized(client,approved(client,quoted(client,row,items,work)));a=bank(client);row=pay(client,row,1000,a);original=row['payments'][0];customer={'id':row['customer_id']}
    correction=finance.create(client,customer,'correction',dict(original_cash_id=original['cash_id'],amount_cents=900,account_id=a,reference='addon-corrected-cash',allocations=[dict(source_case_id=row['id'],amount_cents=900)]));correction=finance.approve(client,correction);finance.command(client,correction,'execute',finance.proof(client,correction,source_versions=finance.versions(client,row)))
    login(client,'admin');row=detail(client,row);assert row['totals']['cash_paid_cents']==900 and row['payments'][0]['available_cents']==0 and row['payments'][0]['superseded']
    assert any(p['cash_kind']=='correction_reverse' for p in row['payments'])
    row=resolve(client,resolve(client,resolution(client,row,'cancel',2000),'resolution_approve'),'resolution_consent')
    v=dict(resolution_id=row['plans'][0]['id'],kind='cash',original_id=original['id'],amount_cents=900,account_id=a,reference=uuid.uuid4().hex,evidence_id=proof(client,row,'receipt'));cmd(client,row,'refund',v,409)
    corrected=next(p for p in row['payments'] if p['cash_kind']=='correction_record');v.update(original_id=corrected['id'],evidence_id=proof(client,row,'receipt'));row=cmd(client,row,'refund',v);assert row['totals']['paid_cents']==0
