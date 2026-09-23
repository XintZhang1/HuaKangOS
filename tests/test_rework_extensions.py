"""HK038 registered APIs: original responsibility is never a new customer charge."""
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal,utcnow,today
from app.models import User,UserStore,CashEntry
from app.flow_models import PaymentLink,Case,StockMove,Item
from app.repair_models import RepairLine,RepairQuote,RepairAllocation
from app.rework_extension_models import ReworkSourceGrant,ReworkExtension,ReworkQuoteScope
from app.service_intake_models import ReworkRequest
from tests.conftest import login,PASSWORD_HASH
from tests.test_service_intake import normal,work_quote,released,resource,proof,convert_rework,cmd as intake_cmd,finish
from tests.test_repair_orders import cmd as repair_cmd,detail as repair_detail,typed,receive
from tests.test_workflow import evidence,master
from tests.test_procurement import bank
from tests.test_multistore import second_store
from tests.test_customer_service import vehicle as care_vehicle

API='/api/rework-extensions'
def switch(c,name,sid=1):
    c.headers.pop('X-Store-ID',None);login(c,name);c.headers['X-Store-ID']=str(sid)
def call(c,path,body,status=201,key=None):
    response=c.post(API+path,json={'request_id':key or uuid.uuid4().hex,**body})
    assert response.status_code==status,response.text
    return response.json()
def decide(c,g,action='approve',status=200,key=None,version=None):
    return call(c,f'/grants/{g["id"]}/actions/{action}',{'version':g['version'] if version is None else version,'values':{'reason':'核对本次原责任范围与接收人'}},status,key)
def employee(name,role,sid):
    with SessionLocal() as db:
        u=db.scalar(select(User).where(User.username==name))
        if not u:
            u=User(username=name,display_name='虚构'+name,role=role,password_hash=PASSWORD_HASH,must_change_password=False);db.add(u);db.flush()
        if not db.get(UserStore,(u.id,sid)):db.add(UserStore(user_id=u.id,store_id=sid))
        db.commit();return u.id
def fixture(c,cross=False,limit=600):
    employee('technician','technician',1)
    original,vehicle,res,_,_=normal(c);original,_=work_quote(c,original,1000);original=repair_cmd(c,original,'start',{'result':'原维修实际开工'});original=released(c,original)
    source_proof=evidence(c,original);original=repair_detail(c,original)
    source=next(s for s in c.get('/api/service-intake/sources').json()['items'] if s['id']==original['id'])
    sid=second_store(c) if cross else 1
    names={role:role+('2' if cross else '') for role in ('service','manager','technician','finance','inventory')}
    users={role:employee(name,role,sid) for role,name in names.items()}
    if cross:
        switch(c,'admin',sid)
        customer=master(c,'customers',{'name':'接待合成客户','phone':'13900000912','contact_allowed':True,'note':''})
        target=care_vehicle(c,customer['id'],customer_identity_id=vehicle['customer_identity_id'],vin=vehicle['vin']);res=resource(c)
    else:target=vehicle
    account=bank(c)
    work=typed(c,'work_items',{'code':'EXTRA-'+uuid.uuid4().hex[:8],'name':'本店维修项目','billing_unit':'job','standard_fee_cents':600})
    switch(c,'admin',1)
    values={'source_case_id':original['id'],'source_case_version':original['version'],'source_line_ids':[source['lines'][0]['id']],
        'to_store_id':sid,'to_vehicle_id':target['id'],'recipient_id':users['service'],'original_liability_limit_cents':limit,
        'evidence_id':source_proof,'reason':'原已修项目责任与本次新自费分开','expires_at':(utcnow()+timedelta(days=2)).isoformat()+'Z'}
    grant=call(c,'/grants',values)
    return {'original':original,'source':source,'source_proof':source_proof,'source_vehicle':vehicle,'vehicle':target,'resource':res,'sid':sid,'names':names,'users':users,'account':account,'work':work,'grant':grant,'proposal':values}
def grant_ready(c,d):
    switch(c,'manager',1);d['grant']=decide(c,d['grant']);return d['grant']
def accept(c,d,status=201,key=None):
    switch(c,d['names']['service'],d['sid'])
    return call(c,'/requests',{'grant_id':d['grant']['id'],'grant_version':d['grant']['version'],'resource_id':d['resource']['id'],'reason':'接收核对原责任与新增需求'},status,key)
def converted(c,d):
    grant_ready(c,d);request=accept(c,d)
    switch(c,d['names']['manager'],d['sid'])
    request=intake_cmd(c,'reworks',request,'approve',{'reason':'独立确认本次承接原责任','internal_name':d['grant']['responsible_name'],'evidence_id':proof(c,request)})
    switch(c,d['names']['service'],d['sid']);row=convert_rework(c,request)
    d['request']=request;return row
def quoted(c,d,row,original=600,extra=300,status=200,lines=None,key=None):
    if lines is None:lines=[{'kind':'work','source_id':d['work']['id'],'quantity_milli':1000,'unit_price_cents':original,'charge_scope':'original_liability','source_line_id':d['source']['lines'][0]['id']},
        {'kind':'work','source_id':d['work']['id'],'quantity_milli':1000,'unit_price_cents':extra,'charge_scope':'customer_extra'}]
    return call(c,f'/orders/{row["id"]}/quote',{'version':repair_detail(c,row)['version'],'values':{'reason':'冻结原责任和本次新自费项目','lines':lines}},status,key)
def authorized(c,d,row):
    q=row['quotes'][-1];switch(c,d['names']['manager'],d['sid'])
    row=repair_cmd(c,row,'price_approve',{'quote_id':q['id'],'minimum_total_cents':0,'allow_below_minimum':False,'reason':'主管核对分类与报价'})
    switch(c,d['names']['service'],d['sid'])
    return repair_cmd(c,row,'authorize',{'quote_id':q['id'],'evidence_id':evidence(c,row,'authorization')})
def ready(c,d,row):
    switch(c,d['names']['technician'],d['sid']);row=repair_cmd(c,row,'start',{'result':'按当前授权实际开工'});row=repair_cmd(c,row,'finish',{'result':'原责任及新项目施工完成'})
    switch(c,d['names']['service'],d['sid']);return repair_cmd(c,row,'quality',{'passed':True,'result':'独立检查施工安全合格','evidence_id':evidence(c,row,'inspection')})
def split(d,original=600,extra=300):return [{'payer_type':'internal','payer_name':d['grant']['responsible_name'],'amount_cents':original},{'payer_type':'customer','amount_cents':extra}]

@pytest.mark.parametrize('cross',[False,True])
def test_same_vin_original_liability_and_new_customer_project_actual_cash_once(client,cross):
    d=fixture(client,cross);row=converted(client,d)
    assert not row['service_intake']['internal_only'] and row['service_intake']['rework_extension']['definition_version']==1
    row=quoted(client,d,row);assert row['quotes'][-1]['rework_scope']=={'original_liability_cents':600,'customer_extra_cents':300}
    row=authorized(client,d,row);row=ready(client,d,row)
    switch(client,d['names']['manager'],d['sid'])
    repair_cmd(client,row,'allocate',{'labor_cost_cents':100,'evidence_id':evidence(client,row),'allocations':split(d,500,400)},409)
    row=repair_cmd(client,row,'allocate',{'labor_cost_cents':100,'evidence_id':evidence(client,row),'allocations':split(d)})
    assert row['revenue_cents']==300 and row['customer_due_cents']==300
    switch(client,d['names']['finance'],d['sid']);customer=next(a for a in row['allocations'] if a['payer_type']=='customer')
    row=receive(client,row,customer,300,d['account'])
    switch(client,d['names']['service'],d['sid']);row=repair_cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    assert row['state']=='completed' and row['receivable_cents']==0
    if cross:
        assert client.get('/api/repair-orders/'+str(d['original']['id'])).status_code==404
        assert client.get('/api/flow/files/'+str(d['source_proof'])).status_code==404
        grant=client.get(API+'/grants/'+str(d['grant']['id'])).json()
        assert not {'source_case_id','source_case_version','evidence_id','customer_id','cost_cents','paid_cents','files'} & grant.keys()
        assert all(set(x)=={'id','code','name','quantity_milli'} for x in grant['source_lines'])
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(PaymentLink.amount_cents)).where(PaymentLink.case_id==d['original']['id']))==1000
        assert db.scalar(select(func.sum(PaymentLink.amount_cents)).where(PaymentLink.case_id==row['id']))==300
        assert db.scalar(select(func.count()).select_from(CashEntry).where(CashEntry.category=='workflow_repair'))==2
        assert db.scalar(select(ReworkRequest.active_source_id).where(ReworkRequest.id==d['request']['id'])) is None
        from app.repair_service import eligible_benefit_units,eligible_benefit_credit
        source_row=db.get(Case,row['id']);code=row['quotes'][-1]['lines'][0]['code']
        assert eligible_benefit_units(db,source_row,code)==1
        assert eligible_benefit_credit(db,source_row,code)==300

def test_source_grant_requires_independent_approval_and_duplicate_stale_revocation(client):
    d=fixture(client);g=d['grant'];decide(client,g,status=403)
    grant_ready(client,d);switch(client,'manager');decide(client,g,version=g['version'],status=409)
    d['grant']=decide(client,d['grant'],'revoke');accept(client,d,409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(ReworkExtension))==0

def test_unrelated_normal_order_and_old_internal_rework_cannot_take_split_quote(client):
    d=fixture(client);switch(client,'admin')
    # The new quote route must not attach a source to an unrelated case.
    from tests.test_repair_orders import create
    ordinary=create(client,{'id':d['original']['customer_id']})
    quoted(client,d,ordinary,status=409)
    from tests.test_service_intake import request_rework,approve_rework
    legacy=convert_rework(client,approve_rework(client,request_rework(client,d['original'],d['vehicle'],d['resource'])))
    quoted(client,d,legacy,status=409)
    assert repair_detail(client,legacy)['service_intake']['internal_only']

def test_over_cap_wrong_source_and_customer_only_quote_leave_no_quote(client):
    d=fixture(client);row=converted(client,d)
    quoted(client,d,row,original=601,status=409)
    wrong=[{'kind':'work','source_id':d['work']['id'],'quantity_milli':1000,'unit_price_cents':600,'charge_scope':'original_liability','source_line_id':999999}]
    quoted(client,d,row,lines=wrong,status=422)
    quoted(client,d,row,lines=[{**wrong[0],'charge_scope':'customer_extra','source_line_id':None}],status=422)
    assert repair_detail(client,row)['quotes']==[]

def test_grant_recipient_role_expiry_and_third_store_fail_closed(client,monkeypatch):
    d=fixture(client,True);grant_ready(client,d)
    switch(client,'admin',d['sid'])
    assert client.get(API+'/grants/'+str(d['grant']['id'])).status_code==404
    call(client,'/requests',{'grant_id':d['grant']['id'],'grant_version':d['grant']['version'],'resource_id':d['resource']['id'],'reason':'未指定员工不能领用'},404)
    switch(client,d['names']['service'],d['sid'])
    from app import rework_extension_service as svc
    monkeypatch.setattr(svc,'utcnow',lambda:utcnow()+timedelta(days=3))
    accept(client,d,409)
    assert not client.get(API+'/grants/'+str(d['grant']['id'])).json()['can_receive']
    monkeypatch.undo()
    with SessionLocal() as db:
        u=db.get(User,d['users']['service']);u.access_version+=1;db.commit()
    # Login obtains a fresh session, but does not repair the frozen grant.
    switch(client,d['names']['service'],d['sid'])
    assert client.get(API+'/grants/'+str(d['grant']['id'])).status_code==409
    accept(client,d,409)

def test_reject_cancel_and_wrong_vin_do_not_create_claims(client):
    d=fixture(client,True);switch(client,'manager');g=decide(client,d['grant'],'reject');assert g['status']=='rejected';d['grant']=g;accept(client,d,409)
    switch(client,'admin');g=call(client,'/grants',d['proposal']);assert decide(client,g,'cancel')['status']=='cancelled'
    switch(client,'admin',d['sid'])
    other=care_vehicle(client,d['vehicle']['customer_id'],vin='LFV2A21K9J7654321')
    switch(client,'admin');call(client,'/grants',{**d['proposal'],'to_vehicle_id':other['id']},422)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(ReworkRequest))==0

def test_consumption_duplicate_old_version_and_cancel_release_shared_original_slot(client):
    d=fixture(client);grant_ready(client,d);key=uuid.uuid4().hex;request=accept(client,d,key=key)
    assert accept(client,d,key=key)==request
    accept(client,d,409)
    switch(client,'manager');request=intake_cmd(client,'reworks',request,'cancel',{'reason':'未转工单取消本次承接'})
    assert request['status']=='cancelled'
    # The spent one-use consent is retained; a new consent can take the same
    # original source slot only after explicit cancellation released it.
    switch(client,'admin');d['grant']=call(client,'/grants',d['proposal']);grant_ready(client,d)
    assert accept(client,d)['status']=='requested'
    with SessionLocal() as db:
        rows=list(db.scalars(select(ReworkRequest).order_by(ReworkRequest.id)))
        assert [r.active_source_id for r in rows]==[None,d['original']['id']]

def test_unstarted_order_cancel_releases_source_without_inventing_departure(client):
    d=fixture(client);row=converted(client,d)
    row=repair_cmd(client,row,'cancel',{'reason':'客户取消尚未开工返修'})
    assert row['state']=='cancelled'
    r=client.get('/api/service-intake/reworks/'+str(d['request']['id'])).json();assert r['status']=='cancelled'
    with SessionLocal() as db:
        assert db.get(ReworkRequest,d['request']['id']).active_source_id is None
        assert db.scalar(select(func.count()).select_from(PaymentLink).where(PaymentLink.case_id==row['id']))==0
    from app.gate_attendance import intervals
    from app.tenancy import set_scope
    with SessionLocal() as db:
        set_scope(db,[d['sid']],d['sid']);facts=[x for x in intervals(db,d['vehicle']['vin']) if x.get('repair_case_id')==row['id']]
        assert len(facts)==1 and facts[0]['leave'] is None

def test_competing_receivers_and_old_rework_share_single_original_reservation(client):
    d=fixture(client);grant_ready(client,d)
    payload={'grant_id':d['grant']['id'],'grant_version':d['grant']['version'],'resource_id':d['resource']['id'],'reason':'合成竞争争用同一原单'}
    with TestClient(app) as a,TestClient(app) as b:
        switch(a,'service');switch(b,'service')
        def run(c):return c.post(API+'/requests',json={'request_id':uuid.uuid4().hex,**payload}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(run,[a,b]))
    assert sorted(codes)==[201,409]
    switch(client,'admin')
    from tests.test_service_intake import post
    post(client,'/reworks',{'source_case_id':d['original']['id'],'source_version':repair_detail(client,d['original'])['version'],
        'customer_vehicle_id':d['vehicle']['id'],'resource_id':d['resource']['id'],'source_line_ids':[d['source']['lines'][0]['id']],'reason':'旧入口也不能重复原返修占用'},409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(ReworkRequest))==1

def test_quote_duplicate_and_new_authorization_prevents_reclassifying_original_line(client):
    d=fixture(client);row=converted(client,d);row=quoted(client,d,row);row=authorized(client,d,row)
    switch(client,d['names']['technician']);row=repair_cmd(client,row,'start',{'result':'开工后原分类不可改换'})
    switch(client,d['names']['service']);q=repair_detail(client,row)['quotes'][-1]
    lines=[{'kind':l['kind'],'source_id':l['work_item_id'],'line_key':l['line_key'],'quantity_milli':l['quantity_milli'],'unit_price_cents':l['unit_price_cents'],
        'charge_scope':l['charge_scope'],'source_line_id':l['source_line_id']} for l in q['lines']]
    lines[0].update(charge_scope='customer_extra',source_line_id=None)
    quoted(client,d,row,lines=lines,status=409)
    assert len(repair_detail(client,row)['quotes'])==1

def test_split_quote_exact_duplicate_and_stale_version_commit_once(client):
    d=fixture(client);row=converted(client,d);key=uuid.uuid4().hex
    body={'version':row['version'],'values':{'reason':'本版原责任冻结幂等校验','lines':[{'kind':'work','source_id':d['work']['id'],'quantity_milli':1000,'unit_price_cents':600,'charge_scope':'original_liability','source_line_id':d['source']['lines'][0]['id']}]}}
    first=call(client,f'/orders/{row["id"]}/quote',body,200,key);again=call(client,f'/orders/{row["id"]}/quote',body,200,key)
    assert first==again
    call(client,f'/orders/{row["id"]}/quote',body,409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(ReworkQuoteScope))==1

def test_real_same_material_split_stock_original_return_and_stop_preserve_value(client):
    from tests.test_procurement import setup as purchase_setup,command as purchase_cmd,receive as purchase_receive
    d=fixture(client);row=converted(client,d);switch(client,'admin')
    purchase,items,_=purchase_setup(client);purchase=purchase_cmd(client,purchase,'approve');purchase_receive(client,purchase);item=items[0]
    with SessionLocal() as db:initial=(db.get(Item,item['id']).quantity_milli,db.get(Item,item['id']).inventory_value_cents)
    switch(client,'service')
    lines=[{'kind':'part','source_id':item['id'],'quantity_milli':1000,'unit_price_cents':600,'charge_scope':'original_liability','source_line_id':d['source']['lines'][0]['id']},
        {'kind':'part','source_id':item['id'],'quantity_milli':1000,'unit_price_cents':300,'charge_scope':'customer_extra'}]
    row=quoted(client,d,row,lines=lines);row=authorized(client,d,row)
    switch(client,'technician');row=repair_cmd(client,row,'start',{'result':'按原责任与新增自费实际开工'})
    switch(client,'inventory')
    for line in repair_detail(client,row)['quotes'][-1]['lines']:
        row=repair_cmd(client,row,'issue',{'line_key':line['line_key'],'quantity_milli':1000,'evidence_id':evidence(client,row)})
    original_issue=row['stock'][0]
    row=repair_cmd(client,row,'return_material',{'original_id':original_issue['id'],'quantity_milli':500,'evidence_id':evidence(client,row)})
    switch(client,'service')
    row=call(client,f'/orders/{row["id"]}/quote',{'version':repair_detail(client,row)['version'],'values':{'purpose':'stop','reason':'实际施工后协商部分退料和保留费','retained_amount_cents':450,'lines':[]}},200)
    assert row['quotes'][-1]['rework_scope']=={'original_liability_cents':300,'customer_extra_cents':150}
    row=authorized(client,d,row)
    repair_cmd(client,row,'cancel',{'reason':'已开工须保留施工与原退料'},409)
    switch(client,'technician');repair_cmd(client,row,'cancel',{'reason':'开工实物不得取消抹账'},403)
    row=repair_cmd(client,row,'finish',{'result':'按停工版本确认保留施工及退料'})
    switch(client,'service');row=repair_cmd(client,row,'quality',{'passed':True,'result':'停工保留项目及安全检查合格','evidence_id':evidence(client,row,'inspection')})
    switch(client,'manager');row=repair_cmd(client,row,'allocate',{'labor_cost_cents':0,'evidence_id':evidence(client,row),'allocations':split(d,300,150)})
    switch(client,'finance');row=receive(client,row,next(a for a in row['allocations'] if a['payer_type']=='customer'),150,d['account'])
    switch(client,'service');row=repair_cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    switch(client,'finance');row=repair_detail(client,row)
    with SessionLocal() as db:
        stored=db.get(Item,item['id']);movements=list(db.scalars(select(StockMove).where(StockMove.case_id==row['id'])))
        assert (stored.quantity_milli,stored.inventory_value_cents)==(initial[0]+sum(m.quantity_milli for m in movements),initial[1]+sum(m.value_cents for m in movements))
        assert sum(m.quantity_milli for m in movements)==-1500
        assert row['cost_cents']==-sum(m.value_cents for m in movements)
        assert db.scalar(select(func.sum(PaymentLink.amount_cents)).where(PaymentLink.case_id==d['original']['id']))==1000

def test_readonly_restore_rejects_source_partition_and_cash_tampering(client):
    import sqlite3
    from app.db import engine
    from app.rework_extension_integrity import validate
    from app.service_intake_backup_integrity import validate as validate_intake
    d=fixture(client,True);row=converted(client,d);row=quoted(client,d,row);row=authorized(client,d,row);row=ready(client,d,row)
    switch(client,d['names']['manager'],d['sid']);row=repair_cmd(client,row,'allocate',{'labor_cost_cents':0,'evidence_id':evidence(client,row),'allocations':split(d)})
    switch(client,d['names']['finance'],d['sid']);row=receive(client,row,next(a for a in row['allocations'] if a['payer_type']=='customer'),300,d['account'])
    with sqlite3.connect(engine.url.database) as source:
        with sqlite3.connect(':memory:') as restored:
            source.backup(restored);assert validate(restored)=={'verified_rework_extension_grants':1,'verified_rework_extensions':1,'verified_rework_quote_scopes':1};validate_intake(restored)
        mutations=["UPDATE rework_source_grants SET original_liability_limit_cents=601", "UPDATE rework_extensions SET grant_digest='bad'",
            "UPDATE rework_quote_scopes SET customer_extra_cents=301", "UPDATE rework_line_scopes SET source_line_id=999999 WHERE charge_scope='original_liability'",
            "UPDATE repair_allocations SET amount_cents=amount_cents+1 WHERE payer_type='customer' AND case_id="+str(row['id']),
            "UPDATE repair_payments SET allocation_id=(SELECT id FROM repair_allocations WHERE payer_type='internal' LIMIT 1) WHERE payment_link_id IN (SELECT id FROM flow_payment_links WHERE case_id="+str(row['id'])+")"]
        for sql in mutations:
            with sqlite3.connect(':memory:') as restored:
                source.backup(restored);restored.execute(sql)
                with pytest.raises(ValueError,match='原责任返修恢复检查'):validate(restored)

def test_consumed_consent_staff_change_allows_safe_local_cancel_without_original_access(client):
    d=fixture(client,True);row=converted(client,d)
    with SessionLocal() as db:
        source_user=db.scalar(select(User).where(User.username=='admin'));source_user.access_version+=1
        receiver=db.get(User,d['users']['service']);receiver.active=False;receiver.access_version+=1;db.commit()
    switch(client,d['names']['manager'],d['sid'])
    row=repair_cmd(client,row,'cancel',{'reason':'原接收人离岗，主管安全取消未开工返修'})
    assert row['state']=='cancelled'
    assert client.get('/api/repair-orders/'+str(d['original']['id'])).status_code==404
    assert client.get('/api/flow/files/'+str(d['source_proof'])).status_code==404
    with SessionLocal() as db:assert db.get(ReworkRequest,d['request']['id']).active_source_id is None

def test_started_local_rework_survives_source_staff_change_via_explicit_task_handoff(client):
    from app.flow_models import FlowEvent,Task
    d=fixture(client,True);row=converted(client,d);row=quoted(client,d,row);row=authorized(client,d,row)
    switch(client,d['names']['technician'],d['sid']);row=repair_cmd(client,row,'start',{'result':'已实际施工，不得抹除'})
    replacement=employee('replacement-service','service',d['sid'])
    with SessionLocal() as db:
        source_user=db.scalar(select(User).where(User.username=='admin'));source_user.access_version+=1
        receiver=db.get(User,d['users']['service']);receiver.active=False;receiver.access_version+=1;db.commit()
    row=repair_cmd(client,row,'finish',{'result':'原实际施工完成，交新的服务接手'})
    switch(client,d['names']['manager'],d['sid'])
    repair_cmd(client,row,'cancel',{'reason':'已施工不能取消事实'},409)
    task=next(t for t in client.get('/api/flow/cases/'+str(row['id'])).json()['tasks'] if t['key']=='repair_quality' and t['status']=='open')
    assigned=client.post('/api/flow/tasks/'+str(task['id'])+'/assign',json={'version':task['version'],'assignee_id':replacement,'reason':'原员工离岗，明确交接本店已施工返修'})
    assert assigned.status_code==200,assigned.text
    switch(client,'replacement-service',d['sid'])
    assert client.get(API+'/grants/'+str(d['grant']['id'])).status_code==404
    assert client.get('/api/flow/files/'+str(d['source_proof'])).status_code==404
    row=repair_cmd(client,row,'quality',{'passed':True,'result':'新接手服务按本店冻结范围复检合格','evidence_id':evidence(client,row,'inspection')})
    switch(client,d['names']['manager'],d['sid']);row=repair_cmd(client,row,'allocate',{'labor_cost_cents':0,'evidence_id':evidence(client,row),'allocations':split(d)})
    switch(client,d['names']['finance'],d['sid']);row=receive(client,row,next(a for a in row['allocations'] if a['payer_type']=='customer'),300,d['account'])
    switch(client,'replacement-service',d['sid']);row=repair_cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    assert row['state']=='completed'
    with SessionLocal() as db:
        assert db.scalar(select(Task.assignee_id).where(Task.case_id==row['id'],Task.key=='repair_release'))==replacement
        assert db.scalar(select(func.count()).select_from(FlowEvent).where(FlowEvent.case_id==row['id'],FlowEvent.action=='reassign'))==1
        assert db.scalar(select(func.sum(PaymentLink.amount_cents)).where(PaymentLink.case_id==d['original']['id']))==1000
