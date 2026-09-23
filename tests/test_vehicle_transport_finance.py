"""Actual original claim cash, typed clearing, monthly sources and local reports."""
import copy,csv,io,json,sqlite3,uuid
from datetime import timedelta
from sqlalchemy import select,func
import pytest
from app.db import SessionLocal,today,engine
from app.models import CashEntry
from app.vehicle_transport_models import VehicleTransportClaim,VehicleTransportClaimPayment,VehicleTransportLoss
from app.reconciliation_service import CURRENT_DEFINITION_VERSION
from tests.conftest import TEST_DIR
from tests import test_vehicle_transport as v
from tests import test_reconciliation as monthly
from tests import test_procurement as procurement
from app.backup_integrity import validate_sqlite


def report(c,**params):
    r=c.get('/api/inventory-reports/vehicle-transport',params=params);assert r.status_code==200,r.text;return r.json()


def sources(c,kind):
    r=c.get('/api/reconciliation/origins');assert r.status_code==200,r.text
    return next(x for x in r.json()['items'] if x['origin_kind']==kind)


def account(c,sid):
    v.as_user(c,'admin',sid);key=procurement.bank(c);v.as_user(c,'finance',sid);return key


def claim(c,row,amount=100):
    sid=int(c.headers['X-Store-ID']);v.as_user(c,'admin',sid);party=procurement.supplier(c)
    v.as_user(c,'finance',sid)
    result=v.act(c,row,'recovery_create',{'counterparty_kind':'carrier','counterparty_id':party['id'],'target_cents':amount,
        'due_date':today().isoformat(),'evidence_id':v.evidence(c,row,True),'reason':'原承运方已确认本店赔付方案待独立复核'})
    return result['claims'][-1]


def claim_act(c,row,key,action,**extra):
    current=next(r for r in v.get(c,row)['claims'] if r['id']==key)
    values={'claim_id':current['id'],'claim_version':current['version'],'evidence_id':v.evidence(c,row,True),
        'reason':'本人核对本店原追偿约定及实际资金凭据',**extra}
    if action in {'recovery_approve','recovery_reject','recovery_cancel'}:values['plan_id']=current['pending_plan_id']
    return v.act(c,row,action,values)


def approve(c,row,cid,sid=1):
    v.as_user(c,'manager' if sid==1 else 'transport_manager2',sid)
    result=claim_act(c,row,cid,'recovery_approve');v.as_user(c,'finance',sid);return result


def cash(c,row,cid,acc,amount=100,original=None):
    return claim_act(c,row,cid,'recovery_receive' if original is None else 'recovery_refund',confirmed=True,account_id=acc,
        amount_cents=amount,reference=uuid.uuid4().hex,business_date=today().isoformat(),**({'original_id':original} if original else {}))


def test_original_claim_cash_found_then_independent_zero_and_original_refund(client):
    _,row,_,locations=v.posted(client);acc=account(client,1)
    c=claim(client,row);approve(client,row,c['id']);cash(client,row,c['id'],acc)
    v.verify_transport()
    with SessionLocal() as db:
        original=db.scalar(select(VehicleTransportClaimPayment)).id
        assert db.scalar(select(func.count()).select_from(CashEntry))==1
    before=report(client);assert before['metrics']['vehicle_transport_claim_cash_cents']==100
    assert client.get('/api/flow/analytics').json()['metrics']['cash_in_cents']==100
    v.found_plan(client,row,2);v.as_user(client,'inventory',2)
    v.act(client,row,'found_receive',{'confirmed':True,'vin':v.old.VIN,'location_id':locations[2],
        'evidence_id':v.evidence(client,row),'reason':'本人实际找回原VIN并验收原车入库'})
    v.as_user(client,'finance',1);after=report(client)
    assert after['metrics']['vehicle_transport_claim_adjustments_pending']==1
    assert after['metrics']['vehicle_transport_claim_due_cents']==0
    # Finding did not fabricate a zero target or reverse the original cash.
    current=v.get(client,row)['claims'][0];assert current['target_cents']==100 and current['paid_cents']==100
    claim_act(client,row,c['id'],'recovery_plan',target_cents=0,due_date=today().isoformat())
    approve(client,row,c['id']);cash(client,row,c['id'],acc,100,original)
    v.verify_transport(found=1)
    with SessionLocal() as db:
        facts=list(db.scalars(select(CashEntry)));assert len(facts)==2 and sum(x.amount_cents*(1 if x.direction=='in' else -1) for x in facts)==0
    r=report(client);assert r['metrics']['vehicle_transport_claim_cash_cents']==0
    assert r['metrics']['vehicle_transport_claim_adjustments_pending']==0
    assert client.get('/api/flow/analytics').json()['metrics']['cash_out_cents']==100
    batch=monthly.batch(client);assert batch['definition_version']==CURRENT_DEFINITION_VERSION
    assert batch['summary']['vehicle_transport_claim_payments']['count']==2
    assert batch['summary']['period_cash_in_cents']==batch['summary']['period_cash_out_cents']==100
    v.verify_transport(found=1)


@pytest.mark.parametrize('kind,receiving',[('vehicle_loss',None),('vehicle_found',1),('vehicle_found',2)])
def test_new_original_liabilities_use_original_two_store_cash_routes(client,kind,receiving):
    _,row,_,locations=v.posted(client)
    if receiving:
        v.found_plan(client,row,receiving);v.as_user(client,'inventory',receiving)
        v.act(client,row,'found_receive',{'confirmed':True,'vin':v.old.VIN,'location_id':locations[receiving],
            'evidence_id':v.evidence(client,row),'reason':'本人确认原实车找回并真实入库'})
    payer=1 if receiving==1 else 2;receiver=3-payer
    v.as_user(client,'finance',payer);origin=sources(client,kind)
    amount=min(40,origin['available_cents']);r=monthly.clear(client,origin,amount)
    paid=monthly.cmd(client,r,'pay',monthly.payvalues(client,r),kind='clearing')
    assert paid['status']=='paid'
    assert sources(client,kind)['settled_cents']==0
    v.as_user(client,'finance',receiver)
    monthly.cmd(client,r,'receive',monthly.payvalues(client,r),kind='clearing')
    v.as_user(client,'finance',payer);assert sources(client,kind)['settled_cents']==amount
    v.verify_transport(found=int(bool(receiving)))
    r=report(client)
    own=next(x for x in r['tables']['vehicle_transport_clearing']['rows'] if x['origin_kind']==kind)
    assert own['amount_cents']==-origin['total_cents']+amount
    batch=monthly.batch(client)
    assert batch['summary']['interstore_clearing_cash']['count']==1
    v.verify_transport(found=int(bool(receiving)))


def test_found_review_blocks_new_loss_payment_but_not_already_paid_receipt(client):
    _,row,_,_=v.posted(client);v.as_user(client,'finance',2)
    origin=sources(client,'vehicle_loss');unpaid=monthly.clear(client,origin,40)
    paid=monthly.clear(client,origin,30);monthly.cmd(client,paid,'pay',monthly.payvalues(client,paid),kind='clearing')
    v.found_plan(client,row,1);v.as_user(client,'finance',2)
    assert sources(client,'vehicle_loss')['active_vehicle_exception_id']==row['id']
    monthly.clear(client,origin,10,409)
    monthly.cmd(client,unpaid,'pay',monthly.payvalues(client,unpaid),409,kind='clearing')
    monthly.cmd(client,unpaid,'cancel',kind='clearing')
    v.as_user(client,'finance',1)
    assert monthly.cmd(client,paid,'receive',monthly.payvalues(client,paid),kind='clearing')['status']=='settled'
    v.verify_transport()


@pytest.mark.parametrize('receiving',[1,2])
def test_same_source_reports_and_group_actual_original_value_do_not_double_count(client,receiving):
    _,row,_,locations=v.posted(client)
    first=report(client);assert first['metrics']['vehicle_transport_loss_cost_cents']==v.COST
    assert first['metrics']['vehicle_transport_burdens_cents']==6000000
    v.found_plan(client,row,receiving);v.as_user(client,'inventory',receiving)
    v.act(client,row,'found_receive',{'confirmed':True,'vin':v.old.VIN,'location_id':locations[receiving],
        'evidence_id':v.evidence(client,row),'reason':'本人实际验收后来找到的同一原车'})
    v.as_user(client,'finance',1)
    first=report(client);assert first['metrics']['vehicle_transport_burden_reversals_cents']==-6000000
    v.as_user(client,'finance',2)
    second=report(client);assert second['metrics']['vehicle_transport_burdens_cents']==4000001
    assert second['metrics']['vehicle_transport_burden_reversals_cents']==-4000001
    v.as_user(client,'admin','all');group=report(client)
    assert group['metrics']['vehicle_transport_asset_change_cents']==0
    assert group['metrics']['vehicle_transport_loss_cost_cents']==group['metrics']['vehicle_transport_found_cost_cents']==v.COST
    assert v.old.VIN not in json.dumps(group,ensure_ascii=False)
    assert all(r['route'] is None for t in group['tables'].values() for r in t['rows'])
    assert group['metrics']['vehicle_transport_clearing_net_cents']==0
    v.as_user(client,'finance',receiving)
    inv=client.get('/api/inventory-reports/vehicles');assert inv.status_code==200,inv.text
    found=[x for x in inv.json()['details'] if x['kind']=='transport_found'];assert len(found)==1 and found[0]['value_cents']==v.COST
    v.as_user(client,'finance',1);assert not client.get('/api/inventory-reports/vehicles').json()['transit']
    standalone=report(client);combined=client.get('/api/flow/analytics');assert combined.status_code==200,combined.text
    key='vehicle_transport_loss_cost';assert standalone['tables'][key]==combined.json()['tables'][key]
    export=client.get('/api/inventory-reports/vehicle-transport/export/'+key);assert export.status_code==200,export.text
    assert list(csv.reader(io.StringIO(export.content.decode('utf-8-sig'))))==[standalone['tables'][key]['headers']]+[[str(x) for x in r['values']] for r in standalone['tables'][key]['rows']]
    v.as_user(client,'inventory',1);assert client.get('/api/inventory-reports/vehicle-transport').status_code==403
    assert 'value_cents' not in json.dumps(client.get('/api/inventory-reports/vehicles').json())


def test_v12_current_originals_period_cost_and_unchanged_v1_through_v11(client,monkeypatch):
    from app import reconciliation_service as svc
    from app.reconciliation_v12 import FROZEN_FIELDS
    from app.models import User
    from app.tenancy import set_scope
    _,row,_,locations=v.posted(client);v.as_user(client,'finance',1);snapshot=svc.snapshot
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='finance'))
        for version in range(1,12):
            manifest,summary,_=snapshot(db,user,today(),today(),version)
            assert not set(FROZEN_FIELDS)&summary.keys()
            assert not any(e['source'] in FROZEN_FIELDS for e in manifest)
        manifest,summary,_=snapshot(db,user,today()-timedelta(days=1),today()-timedelta(days=1))
        assert summary['vehicle_transport_losses']['count']==0
        assert summary['vehicle_transport_plans']['count']==1
    with monkeypatch.context() as patch:
        patch.setattr(svc,'snapshot',lambda db,user,start,end,definition_version=11:snapshot(db,user,start,end,11))
        old=monthly.batch(client)
    assert old['definition_version']==11
    new=monthly.cmd(client,old,'recalculate',{'reason':'按本店原VIN损失来源新版本重新核对'})
    assert new['definition_version']==svc.CURRENT_DEFINITION_VERSION and new['summary']['vehicle_transport_losses']['value_cents']==v.COST
    saved=copy.deepcopy(new['manifest']);saved_digest=new['digest']
    v.found_plan(client,row,2);v.as_user(client,'inventory',2)
    v.act(client,row,'found_receive',{'confirmed':True,'vin':v.old.VIN,'location_id':locations[2],
        'evidence_id':v.evidence(client,row),'reason':'月结之后本人实际验收找到的原车'})
    v.as_user(client,'finance',1);same=monthly.get(client,new)
    assert same['manifest']==saved and same['digest']==saved_digest and same['source_changed']
    v.verify_transport(found=1)
