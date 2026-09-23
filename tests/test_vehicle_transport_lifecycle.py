"""Race, rollback and successive original-VIN lifecycles on isolated synthetic data."""
import uuid,sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import select,func,text
from fastapi import HTTPException
from app.db import engine,SessionLocal,today
from app.models import User,Vehicle,CashEntry
from app.tenancy import set_scope,project_user
from app.vehicle_transport_models import (VehicleTransportLoss,VehicleTransportFoundReceipt,
    VehicleTransportClaim,VehicleTransportClaimPayment)
from app import vehicle_transport_service as service
from tests import test_vehicle_transport as v
from tests import test_vehicle_transport_finance as f
from tests import test_reconciliation as monthly


def competing(row,action,values,sid,user_name):
    def run(_):
        with SessionLocal() as db:
            set_scope(db,[sid],sid);user=db.scalar(select(User).where(User.username==user_name));user=project_user(user,user.role)
            try:
                result=service.command(db,user,row['id'],uuid.uuid4().hex,row['version'],row['case_version'],row['exception_version'],action,values)
                return 200,result
            except HTTPException as exc:return exc.status_code,exc.detail
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
    assert sorted(code for code,_ in results)==[200,409],results
    return next(data for code,data in results if code==200)


def test_two_cashiers_post_exactly_one_original_loss(client):
    _,row,_,_=v.start(client);v.observations(client,row);v.propose_loss(client,row);v.approve_both(client,row)
    v.as_user(client,'finance',1);evidence=v.evidence(client,row,True);current=v.get(client,row)
    competing(current,'post_loss',{'confirmed':True,'evidence_id':evidence,'reason':'同一本人原损失确认并发仅能入账一次'},1,'finance')
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(VehicleTransportLoss))==1
        assert db.scalar(select(func.count()).select_from(CashEntry))==0
    v.verify_transport()


def test_two_receivers_cannot_create_two_generations_for_same_found_vin(client):
    _,row,_,locations=v.posted(client);v.found_plan(client,row,2);v.as_user(client,'inventory',2)
    evidence=v.evidence(client,row);current=v.get(client,row)
    competing(current,'found_receive',{'confirmed':True,'vin':v.old.VIN,'location_id':locations[2],
        'evidence_id':evidence,'reason':'同一本人原实车验收并发仅能接收一次'},2,'inventory')
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(VehicleTransportFoundReceipt))==1
        assert db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.approval_state=='approved'))==1
    v.verify_transport(found=1)


def test_concurrent_original_claim_cash_has_one_actual_cash_and_receipt(client):
    _,row,_,_=v.posted(client);account=f.account(client,1);claim=f.claim(client,row);f.approve(client,row,claim['id'])
    evidence=v.evidence(client,row,True);current=v.get(client,row);c=current['claims'][0]
    values={'confirmed':True,'claim_id':c['id'],'claim_version':c['version'],'amount_cents':100,'account_id':account,
        'reference':'CONCURRENT-ACTUAL-ONE','business_date':today(),'evidence_id':evidence,'reason':'同一原赔付实际到账只登记一次'}
    competing(current,'recovery_receive',values,1,'finance')
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(VehicleTransportClaimPayment))==1
        assert db.scalar(select(func.count()).select_from(CashEntry))==1
    v.verify_transport()


def test_recovery_capacity_counts_pending_targets_and_unreturned_original_cash(client):
    _,row,_,_=v.posted(client);account=f.account(client,1)
    a=f.claim(client,row,6000000);f.approve(client,row,a['id']);f.cash(client,row,a['id'],account,6000000)
    f.claim_act(client,row,a['id'],'recovery_plan',target_cents=0,due_date=today().isoformat())
    f.approve(client,row,a['id'])
    v.as_user(client,'admin',1);party=f.procurement.supplier(client);v.as_user(client,'finance',1)
    new={'counterparty_kind':'carrier','counterparty_id':party['id'],'target_cents':1,'due_date':today().isoformat(),
        'evidence_id':v.evidence(client,row,True),'reason':'旧款尚未原路退回时不能释放已占赔付承担'}
    v.act(client,row,'recovery_create',new,409)
    original=v.get(client,row)['claims'][0]['payments'][0]['id']
    f.cash(client,row,a['id'],account,5999999,original)
    new['target_cents']=6000000;v.act(client,row,'recovery_create',new,409)
    new['target_cents']=5999999;v.act(client,row,'recovery_create',new)
    v.verify_transport()


def test_resolved_wrong_vin_then_new_loss_keeps_both_original_investigations(client):
    parent,row,_,locations=v.start(client,'vin_mismatch');v.observations(client,row,'original_seen')
    v.as_user(client,'inventory',1);v.act(client,row,'plan_resume');v.approve_both(client,row,financial=False)
    assert v.get(client,row)['status']=='resolved'
    v.as_user(client,'inventory',1);current=v.old.get(client,parent)
    response=client.post(v.API,json={'request_id':uuid.uuid4().hex,'transfer_id':parent['id'],'version':current['version'],
        'case_version':current['case_version'],'kind':'missing','evidence_id':v.old.upload(client,parent),'reason':'解除原误认后再次实际发现原VIN未定位'})
    assert response.status_code==201,response.text;new=response.json()
    v.observations(client,new);v.propose_loss(client,new);v.approve_both(client,new);v.as_user(client,'finance',1)
    v.act(client,new,'post_loss',{'confirmed':True,'evidence_id':v.evidence(client,new,True),'reason':'新的两店原事实确认原成本损失'})
    v.found_plan(client,new,1);v.as_user(client,'inventory',1)
    v.act(client,new,'found_receive',{'confirmed':True,'vin':v.old.VIN,'location_id':locations[1],'evidence_id':v.evidence(client,new),'reason':'原车后来实际找到并真实接回原店'})
    v.verify_transport(found=1)
    assert v.get(client,row)['status']=='resolved' and v.get(client,new)['status']=='recovered'


def test_original_compensation_refund_remains_possible_after_found_car_is_transferred_again(client):
    _,row,_,locations=v.posted(client);account=f.account(client,1);claim=f.claim(client,row);f.approve(client,row,claim['id']);f.cash(client,row,claim['id'],account)
    original=v.get(client,row)['claims'][0]['payments'][0]['id']
    v.found_plan(client,row,2);v.as_user(client,'inventory',2)
    found=v.act(client,row,'found_receive',{'confirmed':True,'vin':v.old.VIN,'location_id':locations[2],'evidence_id':v.evidence(client,row),'reason':'原车按已批准的实际找回入库'})
    response=client.post('/api/vehicle-transfers',json={'request_id':uuid.uuid4().hex,'vehicle_id':found['found']['vehicle_id'],
        'destination_store_id':1,'due_date':today().isoformat(),'reason':'找回后另一笔合法调拨，保留旧原款历史'})
    assert response.status_code==201,response.text;parent=response.json()
    # Native transfer retains its assigned original manager; the additional
    # transport reviewer is not automatically the owner of this new task.
    v.as_user(client,'manager',2);v.old.command(client,parent,'approve');v.as_user(client,'manager',1);v.old.command(client,parent,'approve')
    v.as_user(client,'inventory',2);v.old.command(client,parent,'dispatch',v.old.proof_values(client,parent))
    v.as_user(client,'finance',1);f.claim_act(client,row,claim['id'],'recovery_plan',target_cents=0,due_date=today().isoformat());f.approve(client,row,claim['id']);f.cash(client,row,claim['id'],account,100,original)
    v.verify_transport(found=1)
    v.as_user(client,'inventory',1);v.old.command(client,parent,'accept',v.old.proof_values(client,parent,location_id=locations[1]))
    v.verify_transport(found=1)


def test_rejected_and_withdrawn_loss_plans_preserve_history_and_require_fresh_review(client):
    _,row,_,_=v.start(client);v.observations(client,row);v.propose_loss(client,row)
    v.as_user(client,'manager',1);p=v.get(client,row)['plans'][-1]
    v.act(client,row,'reject',{'plan_id':p['id'],'evidence_id':v.evidence(client,row,True),'reason':'原承担协议尚未充分核对，明确不通过'})
    v.propose_loss(client,row);v.as_user(client,'finance',1);p=v.get(client,row)['plans'][-1]
    v.act(client,row,'withdraw',{'plan_id':p['id'],'evidence_id':v.evidence(client,row,True),'reason':'原申请人撤回本版未生效的承担方案'})
    v.propose_loss(client,row);v.approve_both(client,row);v.as_user(client,'finance',1)
    v.act(client,row,'post_loss',{'confirmed':True,'evidence_id':v.evidence(client,row,True),'reason':'第三版协议两店独立批准后实际确认损失'})
    assert [p['status'] for p in v.get(client,row)['plans']]==['rejected','withdrawn','approved'];v.verify_transport()


def test_monthly_v12_cannot_invent_origin_even_after_manifest_digest_recomputed(client,tmp_path):
    _,row,_,_=v.posted(client);v.as_user(client,'finance',1);batch=monthly.batch(client)
    from app.reconciliation_service import digest as digest_manifest
    path=tmp_path/'forged-statement.sqlite'
    with sqlite3.connect(engine.url.database) as source,sqlite3.connect(path) as target:source.backup(target)
    with sqlite3.connect(path) as db:
        manifest=json_load(db.execute('SELECT manifest FROM reconciliation_batches WHERE id=?',(batch['id'],)).fetchone()[0])
        entry=next(x for x in manifest if x['source']=='vehicle_transport_losses');entry['data']['value_cents']+=1
        db.execute('UPDATE reconciliation_batches SET manifest=?,digest=? WHERE id=?',(json_dump(manifest),digest_manifest(manifest),batch['id']));db.commit()
        from app.backup_integrity import validate_sqlite
        with pytest.raises(ValueError):validate_sqlite(db)


def json_load(value):
    import json
    return json.loads(value)


def json_dump(value):
    import json
    return json.dumps(value,ensure_ascii=False)
