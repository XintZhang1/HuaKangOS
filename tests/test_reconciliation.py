"""Real ledger statements and independently confirmed store cash, synthetic only."""
import csv,io,uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,func
from fastapi import HTTPException
from app.db import SessionLocal,today
from app.models import User,CashEntry
from app.tenancy import set_scope,project_user
from app.flow_models import Case
from app.reconciliation_models import ReconciliationBatch,ClearingOrder,ClearingBucket,ClearingCash,ClearingOffset
from app import reconciliation_service as svc
from tests import test_group_membership as group
from tests import test_transfers as transfer
from tests import test_vehicle_transfers as vehicle
from tests.test_procurement import bank
from tests.conftest import login

API='/api/reconciliation'
def batch(c):
    r=c.post(API+'/batches',json={'request_id':uuid.uuid4().hex,'start':today().isoformat(),'end':today().isoformat(),'reason':'核对本期银行及业务账'})
    assert r.status_code==201,r.text;return r.json()
def get(c,row,kind='batches'):
    r=c.get(API+f'/{kind}/{row["id"]}');assert r.status_code==200,r.text;return r.json()
def cmd(c,row,action,values=None,status=200,kind='batches',old=None,key=None):
    row=old or get(c,row,kind)
    r=c.post(API+f'/{kind}/{row["id"]}/actions/{action}',json={'request_id':key or uuid.uuid4().hex,
        'version':row['version'],'case_version':row['case_version'],'values':values or {'reason':'已核对本次业务事实'}})
    assert r.status_code==status,r.text;return r.json()
def proof(c,row,kind='batches'):
    row=get(c,row,kind);r=c.post(f'/api/flow/cases/{row["case_id"]}/files',
        files={'file':('对账凭据.txt','合成银行及对账凭据'.encode(),'text/plain')},data={'category':'receipt'})
    assert r.status_code==200,r.text;return r.json()['id']
def origin(c,kind='material'):
    if kind=='material':
        a,b=transfer.seed();t=transfer.approved(c,a)
        transfer.command(c,t,'dispatch',{'evidence_id':transfer.upload(c,t),'reason':'实际发出合成备件'})
        transfer.switch(c,2);r=transfer.get(c,t)
        transfer.command(c,t,'receive',{'evidence_id':transfer.upload(c,t),'reason':'全部实际验收',
            'lines':[{'line_id':r['lines'][0]['id'],'item_id':b,'accept_milli':3000,'reject_milli':0}]})
    else:
        car,locations=vehicle.seed();t=vehicle.approved(c,car)
        vehicle.command(c,t,'dispatch',vehicle.proof_values(c,t));vehicle.switch(c,2)
        vehicle.command(c,t,'accept',vehicle.proof_values(c,t,location_id=locations[2]))
    login(c,'finance');r=c.get(API+'/origins');assert r.status_code==200,r.text
    return next(x for x in r.json()['items'] if x['origin_kind']==kind)
def clear(c,o,amount=None,status=201):
    r=c.post(API+'/clearing',json={'request_id':uuid.uuid4().hex,'origin_kind':o['origin_kind'],'origin_id':o['origin_id'],
        'amount_cents':amount or o['available_cents'],'due_date':today().isoformat(),'reason':'双方核对原调拨应付款'})
    assert r.status_code==status,r.text;return r.json()
def payvalues(c,row,account=None):
    if account is None:
        login(c,'admin');account=bank(c);login(c,'finance')
    return {'account_id':account,'reference':uuid.uuid4().hex,
        'evidence_id':proof(c,row,'clearing'),'reason':'已按银行实际发生额核对'}


def test_batch_diff_independent_seal_and_preserved_reopen(client):
    a=group.seed();m=group.issue(client,a);group.cmd(client,m,'topup',group.topup_values(a))
    login(client,'finance');r=batch(client);assert r['summary']['period_cash_in_cents']==10000
    fid=proof(client,r);line=next(x for x in r['manifest'] if x['source']=='cash_entries')
    r=cmd(client,r,'issue',{'line_key':line['key'],'difference_cents':-100,'evidence_id':fid,'reason':'银行对账暂差一元待核实'})
    cmd(client,r,'submit',status=409)
    issue=r['issues'][0]
    r=cmd(client,r,'resolve',{'issue_id':issue['id'],'issue_version':issue['version'],'evidence_id':fid,'reason':'银行复核尾差为核对输入错误，原款一致'})
    r=cmd(client,r,'submit');cmd(client,r,'seal',{'reason':'财务不得自行封存','evidence_id':fid},403)
    login(client,'manager');sealed=cmd(client,r,'seal',{'reason':'独立核对原款及差异处理记录','evidence_id':fid});assert sealed['status']=='sealed'
    cmd(client,sealed,'issue',{'line_key':line['key'],'difference_cents':0,'evidence_id':fid,'reason':'不能改已封存快照'},403)
    new=cmd(client,sealed,'reopen',{'reason':'补充后续确认资料重新核对'});assert new['revision']==2 and new['previous_id']==sealed['id']
    old=get(client,sealed);assert old['status']=='sealed' and old['digest']==sealed['digest'] and old['successor_id']==new['id']


def test_late_posting_detected_and_recalculation_new_version(client):
    a=group.seed();m=group.issue(client,a);login(client,'finance');r=batch(client)
    group.cmd(client,m,'topup',group.topup_values(a));assert get(client,r)['source_changed']
    cmd(client,r,'submit',status=409)
    fresh=cmd(client,r,'recalculate',{'reason':'银行新到账已入原业务，重算本期'})
    assert fresh['revision']==2 and fresh['summary']['period_cash_in_cents']==10000
    assert get(client,r)['status']=='superseded'
    cmd(client,fresh,'submit')
    login(client,'manager');fid=proof(client,fresh);cmd(client,fresh,'seal',{'evidence_id':fid,'reason':'来源一致独立确认封存'})


@pytest.mark.parametrize('kind',['material','vehicle'])
def test_two_store_actual_cash_partial_clearing_and_original_conservation(client,kind):
    o=origin(client,kind);amount=min(o['available_cents'],60);r=clear(client,o,amount)
    clear(client,o,o['available_cents'],409)
    transfer.switch(client,1);cmd(client,r,'receive',payvalues(client,r),409,kind='clearing')
    transfer.switch(client,2);paid=cmd(client,r,'pay',payvalues(client,r),kind='clearing');assert paid['status']=='paid'
    cmd(client,r,'cancel',status=409,kind='clearing')
    report=client.get('/api/flow/analytics').json();assert report['metrics']['cash_out_cents']==amount
    with SessionLocal() as db:
        set_scope(db,[2],2);u=project_user(db.scalar(select(User).where(User.username=='finance')),'finance')
        rows=svc.settlement_rows(db,u);assert rows['in_transit'][0]['amount_cents']==amount
        assert not list(db.scalars(select(ClearingOffset)))
    transfer.switch(client,1);done=cmd(client,r,'receive',payvalues(client,r),kind='clearing');assert done['status']=='settled'
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(ClearingOffset.amount_cents)))==0
        cash=list(db.scalars(select(CashEntry).where(CashEntry.category=='interstore_clearing')))
        assert len(cash)==2 and sum(c.amount_cents*(1 if c.direction=='in' else -1) for c in cash)==0
    transfer.switch(client,2);remaining=client.get(API+'/origins').json()['items'][0]
    assert remaining['settled_cents']==amount and remaining['available_cents']==o['total_cents']-amount


def test_cancel_reject_roles_scope_and_evidence(client):
    o=origin(client);r=clear(client,o,50);fid=proof(client,r,'clearing')
    login(client,'sales');assert client.get(API+'/batches').status_code==403
    assert client.get(API+f'/clearing/{r["id"]}').status_code==403
    assert client.get(f'/api/flow/cases/{r["case_id"]}').status_code==404
    login(client,'admin');transfer.switch(client,3);assert client.get(API+f'/clearing/{r["id"]}').status_code==404
    transfer.switch(client,1);login(client,'finance');cmd(client,r,'receive',payvalues(client,r)|{'evidence_id':fid},409,kind='clearing')
    cmd(client,r,'reject',kind='clearing');transfer.switch(client,2)
    assert client.get(API+'/origins').json()['items'][0]['available_cents']==100
    r=clear(client,o,50);cmd(client,r,'cancel',kind='clearing')
    assert client.get(API+'/origins').json()['items'][0]['available_cents']==100


def test_duplicate_stale_and_competing_original_claims(client):
    o=origin(client);r=clear(client,o,40);before=get(client,r,'clearing');values=payvalues(client,r);before=get(client,r,'clearing');key=uuid.uuid4().hex
    first=cmd(client,r,'pay',values,kind='clearing',old=before,key=key)
    assert cmd(client,r,'pay',values,kind='clearing',old=before,key=key)==first
    cmd(client,r,'pay',values,409,kind='clearing',old=before)
    payload={'origin_kind':'material','origin_id':o['origin_id'],'amount_cents':50,'due_date':today().isoformat(),'reason':'并发占用余款'}
    def claim(_):
        with SessionLocal() as db:
            set_scope(db,[2],2);user=project_user(db.scalar(select(User).where(User.username=='finance')),'finance')
            try:svc.create_clearing(db,user,uuid.uuid4().hex,payload);return 201
            except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(claim,range(2)))==[201,409]
    assert client.get(API+'/origins').json()['items'][0]['reserved_cents']==90


def test_batch_csv_and_immutable_snapshot(client):
    group.seed();login(client,'finance');r=batch(client)
    output=client.get(API+f'/batches/{r["id"]}/export');assert output.status_code==200
    data=list(csv.reader(io.StringIO(output.content.decode('utf-8-sig'))));assert len(data)==len(r['manifest'])+1
    with SessionLocal() as db:
        row=db.scalar(select(ReconciliationBatch).where(ReconciliationBatch.id==r['id']));row.digest='0'*64
        with pytest.raises(HTTPException):db.commit()


def test_restored_statement_digest_and_two_store_clearing_pairs(client):
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.reconciliation_backup_integrity import validate_reconciliation_sqlite
    o=origin(client);r=clear(client,o,50)
    cmd(client,r,'pay',payvalues(client,r),kind='clearing');transfer.switch(client,1)
    cmd(client,r,'receive',payvalues(client,r),kind='clearing')
    transfer.switch(client,2);pending=clear(client,o,30);cmd(client,pending,'pay',payvalues(client,pending),kind='clearing')
    b=batch(client);b=cmd(client,b,'submit');login(client,'manager')
    cmd(client,b,'seal',{'reason':'独立核对原账封存','evidence_id':proof(client,b)})
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored)
        assert validate_reconciliation_sqlite(restored)=={'verified_reconciliation_batches':1,'verified_clearing_orders':2}
        for sql,error in [("UPDATE reconciliation_batches SET digest='wrong'",'摘要'),
            ("UPDATE reconciliation_batches SET manifest=json_set(manifest,'$[0].data.amount_cents',1)",'摘要'),
            ('UPDATE interstore_clearing_buckets SET reserved_cents=0','占用'),
            ('UPDATE interstore_clearing_offsets SET amount_cents=amount_cents+1','守恒'),
            ("UPDATE cash_entries SET amount_cents=amount_cents+1 WHERE category='interstore_clearing'",'现金')]:
            restored.execute(sql)
            with pytest.raises(ValueError,match=error):validate_reconciliation_sqlite(restored)
            restored.rollback()


def test_wrong_store_file_actual_paid_amount_cannot_be_overridden_and_receive_race(client):
    o=origin(client);r=clear(client,o,50);out=payvalues(client,r)
    cmd(client,r,'pay',out|{'amount_cents':1},422,kind='clearing')
    cmd(client,r,'pay',out,kind='clearing');transfer.switch(client,1)
    values=payvalues(client,r);cmd(client,r,'receive',values|{'evidence_id':out['evidence_id']},422,kind='clearing')
    latest=get(client,r,'clearing')
    def receive(_):
        with SessionLocal() as db:
            set_scope(db,[1],1);user=project_user(db.scalar(select(User).where(User.username=='finance')),'finance')
            try:svc.clearing_command(db,user,r['id'],uuid.uuid4().hex,latest['version'],latest['case_version'],'receive',values);return 200
            except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(receive,range(2)))==[200,409]
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(ClearingCash))==2


def test_batch_duplicate_stale_cross_store_and_admin_self_seal_refused(client):
    group.seed();group.seed(2);r=batch(client);key=uuid.uuid4().hex
    first=cmd(client,r,'submit',old=r,key=key)
    assert cmd(client,r,'submit',old=r,key=key)==first
    cmd(client,r,'submit',old=r,status=409)
    cmd(client,first,'seal',{'reason':'管理员本人也必须独立复核','evidence_id':proof(client,first)},403)
    transfer.switch(client,2);assert client.get(API+f'/batches/{r["id"]}').status_code==404
    assert client.get(API+f'/batches/{r["id"]}/export').status_code==404
    transfer.switch(client,'all');assert client.get(API+'/batches').status_code==409


def test_statement_preserves_distinct_benefit_and_item_units(client):
    from tests import test_group_benefits as benefits
    from tests import test_procurement as procurement
    a,b,m=benefits.setup(client)
    for kind,count in [('bonus',10),('points',20),('coupon',1),('package',2)]:
        rule=benefits.rule(client,kind,sale_cents_per_unit=0,settlement_cents_per_unit=0,refund_policy='none')
        benefits.issuance(client,m,a,rule,count,'grant')
    order,items,_=procurement.setup(client);procurement.command(client,order,'approve');procurement.receive(client,order)
    row=batch(client);totals=row['summary']['benefit_entries']
    assert 'units' not in totals and totals['units_by_kind']=={'bonus':10,'points':20,'coupon':1,'package:SERVICE-JOB':2}
    stock=row['summary']['flow_stock_moves']
    assert 'quantity_milli' not in stock
    assert stock['quantity_milli_by_item']=={str(items[0]['id']):2500,str(items[1]['id']):1000}


def test_vehicle_procurement_and_retail_actual_sources_are_in_statement_and_late_return_changes_it(client):
    from tests import test_vehicle_procurement as vp
    from tests import test_retail as retail
    row,loc=vp.approved(client,quantity=1);row=vp.funds(client,row,10000001);vp.pay(client,row,vp.bank(client),10000001)
    row=vp.ship(client,row);vp.receive(client,row,loc)
    items,customer,work,_=retail.setup(client)
    sale=retail.authorize(client,retail.approve(client,retail.create(client,items,customer)))
    sale=retail.pay(client,sale,sale['amount_cents'],retail.bank(client));sale=retail.dispatch(client,sale)
    statement=batch(client)
    for name in ['vehicle_purchase_payments','vehicle_purchase_receipts','vehicle_purchase_movements','retail_payments','retail_dispatches']:
        assert statement['summary'][name]['count']>0
    sale,ret=retail.request_return(client,sale,sale['dispatches'][0],500)
    retail.ret_cmd(client,sale,ret,'return_approve');retail.ret_cmd(client,sale,ret,'return_receive')
    assert get(client,statement)['source_changed'];cmd(client,statement,'submit',status=409)
    new=cmd(client,statement,'recalculate',{'reason':'实际零售退货已入库，重新生成本期对账'})
    assert new['summary']['retail_return_postings']['count']==1


def test_internal_cash_reporting_keeps_pending_transit_and_reconciles_csv_original_offsets(client):
    from decimal import Decimal
    o=origin(client);r=clear(client,o,40);cmd(client,r,'pay',payvalues(client,r),kind='clearing')
    single=client.get('/api/flow/analytics').json()
    assert single['metrics']['cash_out_cents']==single['metrics']['internal_cash_out_cents']==40
    assert single['tables']['cash']['rows'][0]['route']=={'type':'case','id':r['case_id']}
    with SessionLocal() as db:
        cash=db.scalar(select(CashEntry).where(CashEntry.category=='interstore_clearing'));cid,version=cash.id,cash.version
    login(client,'admin');refused=client.post(f'/api/records/cash/{cid}/actions/void',json={'version':version,'reason':'禁止旧接口抹掉真实内部现金'})
    assert refused.status_code==409,refused.text
    transfer.switch(client,'all');report=client.get('/api/flow/analytics').json()
    assert report['metrics']['cash_in_cents']==report['metrics']['cash_out_cents']==0
    assert report['metrics']['internal_cash_in_transit_cents']==40
    chart=next(c for c in report['charts'] if c['id']=='internal_cash_transit')
    assert sum(chart['series'][0]['values'])==sum(x['amount_cents'] for x in report['tables']['internal_cash_transit']['rows'])==40
    transfer.switch(client,1);login(client,'finance');cmd(client,r,'receive',payvalues(client,r),kind='clearing')
    login(client,'admin');transfer.switch(client,'all');report=client.get('/api/flow/analytics').json()
    assert report['metrics']['internal_cash_in_transit_cents']==0
    assert report['metrics']['internal_cash_in_cents']==report['metrics']['internal_cash_out_cents']==40
    assert report['metrics']['cash_in_cents']==report['metrics']['cash_out_cents']==0
    assert [int(Decimal(x['values'][1])*100) for x in report['tables']['transfer_clearing']['rows']]==[60,-60]
    for name in ['internal_cash','internal_cash_transit','transfer_clearing']:
        exported=client.get('/api/flow/analytics/export',params={'dataset':name});assert exported.status_code==200
        data=list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))))
        assert data[0]==report['tables'][name]['headers']
        assert [[v.removeprefix("'") for v in row] for row in data[1:]]==[[str(v) for v in row['values']] for row in report['tables'][name]['rows']]
