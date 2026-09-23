"""Explicit appointment arrival, v4 repair reuse, resources and rework liability."""
import uuid
from datetime import timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import utcnow,today,SessionLocal
from app.models import User,UserStore,Store,CashEntry
from app.flow_models import Case,StockMove,PaymentLink,Item,Task
from app.service_intake_models import ServiceResource,ServiceAppointment,RepairVehicleBinding,RepairIntake,ResourceUse,ReworkRequest
from tests.conftest import login,PASSWORD_HASH
from tests.test_workflow import evidence,master
from tests.test_customer_service import vehicle as care_vehicle
from tests.test_repair_orders import typed,cmd as repair_cmd,detail as repair_detail,quote,authorize,ready,allocate,receive,setup as repair_setup
from tests.test_procurement import bank
API='/api/service-intake'
@pytest.fixture(autouse=True)
def technician():
    with SessionLocal() as db:
        user=User(username='technician',display_name='接待技师',role='technician',password_hash=PASSWORD_HASH,must_change_password=False);db.add(user);db.flush();db.add(UserStore(user_id=user.id,store_id=1));db.commit()
def post(c,path,values,status=201,key=None):
    response=c.post(API+path,json={'request_id':key or uuid.uuid4().hex,**values});assert response.status_code==status,response.text;return response.json()
def resource(c,kind='repair'):
    return post(c,'/resources',{'code':'RES-'+uuid.uuid4().hex[:8],'name':'独立'+kind+'工位','resource_type':kind})
def customer_vehicle(c):
    customer=master(c,'customers',{'name':'接待合成客户','phone':'13900000912','contact_allowed':True,'note':''})
    return care_vehicle(c,customer['id'],vin='LFV2A21K9J1234567'),customer
def slot(offset=1,duration=1):
    start=utcnow()+timedelta(hours=offset)
    return {'starts_at':start.replace(tzinfo=timezone.utc).isoformat(),'ends_at':(start+timedelta(hours=duration)).replace(tzinfo=timezone.utc).isoformat()}
def appointment(c,v,r,**kw):return post(c,'/appointments',{'customer_vehicle_id':v['id'],'resource_id':r['id'],'problem':'实际到店检查保养',**slot(),**kw})
def detail(c,kind,row):
    response=c.get(API+'/'+kind+'/'+str(row['id']));assert response.status_code==200,response.text;return response.json()
def cmd(c,kind,row,action,v=None,status=200,version=None,key=None):
    current=detail(c,kind,row)
    return post(c,f"/{kind}/{row['id']}/actions/{action}",{'version':current['version'] if version is None else version,'values':v or {}},status,key)
def proof(c,row,category='evidence'):return evidence(c,{'id':row['case_id']},category)
def arrive(c,a):return cmd(c,'appointments',a,'arrive',{'checked_vin':a['vin'],'odometer_km':10000,'evidence_id':proof(c,a,'inspection')})
def convert(c,a):
    result=cmd(c,'appointments',a,'convert',{'due_date':today().isoformat()});return repair_detail(c,{'id':result['repair_case_id']})
def normal(c,resource_row=None,preset=None):
    v,customer=customer_vehicle(c);r=resource_row or resource(c)
    a=appointment(c,v,r,**({'preset_id':preset['id']} if preset else {}));a=arrive(c,a);return convert(c,a),v,r,a,customer
def work_quote(c,row,amount=1000):
    work=typed(c,'work_items',{'code':'INTAKE-JOB-'+uuid.uuid4().hex[:8],'name':'实际维修服务','billing_unit':'job','standard_fee_cents':amount})
    row=repair_cmd(c,row,'quote',{'reason':'确认本次实际施工范围','lines':[{'kind':'work','source_id':work['id'],'quantity_milli':1000,'unit_price_cents':amount}]})
    return authorize(c,row),work
def finish(c,row):
    row=repair_cmd(c,row,'finish',{'result':'实际施工完成'});return repair_cmd(c,row,'quality',{'passed':True,'result':'安全与施工质量检查通过','evidence_id':evidence(c,row,'inspection')})
def released(c,row,internal=False):
    row=finish(c,row);row=allocate(c,row,[{'payer_type':'internal','payer_name':'门店维修责任','amount_cents':row['amount_cents']}] if internal else None)
    if not internal:row=receive(c,row,row['allocations'][0],row['amount_cents'],bank(c))
    return repair_cmd(c,row,'release',{'evidence_id':evidence(c,row)})
def request_rework(c,row,vehicle,res):
    sources=c.get(API+'/sources').json()['items'];source=next(x for x in sources if x['id']==row['id'])
    return post(c,'/reworks',{'source_case_id':row['id'],'source_version':repair_detail(c,row)['version'],'customer_vehicle_id':vehicle['id'],
        'resource_id':res['id'],'source_line_ids':[source['lines'][0]['id']],'reason':'售后发现原已维修项目缺陷'})
def approve_rework(c,r):return cmd(c,'reworks',r,'approve',{'reason':'核对原故障属于本店返修责任','internal_name':'门店维修责任','evidence_id':proof(c,r)})
def convert_rework(c,r):
    result=cmd(c,'reworks',r,'convert',{'checked_vin':r['vin'],'odometer_km':10200,'evidence_id':proof(c,r,'inspection'),'due_date':today().isoformat()})
    return repair_detail(c,{'id':result['repair_case_id']})

def test_appointment_requires_actual_arrival_and_binds_customer_vin(client):
    v,_=customer_vehicle(client);r=resource(client);a=appointment(client,v,r)
    cmd(client,'appointments',a,'convert',{'due_date':today().isoformat()},409)
    cmd(client,'appointments',a,'arrive',{'checked_vin':'LFV2A21K9J7654321','odometer_km':1,'evidence_id':proof(client,a)},409)
    a=arrive(client,a);row=convert(client,a);assert row['flow_version']==4 and row['service_intake']['vin']==v['vin']
    cmd(client,'appointments',a,'cancel',{'reason':'不能抹除实际到店'},409)
    cmd(client,'appointments',a,'convert',{'due_date':today().isoformat()},409)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RepairIntake))==1
        assert db.scalar(select(func.count()).select_from(StockMove))==0 and db.scalar(select(func.count()).select_from(CashEntry))==0
        assert db.get(Case,row['id']).vehicle_id is None

def test_fast_wash_prefills_real_quote_without_fake_approval_or_cash(client):
    work=typed(client,'work_items',{'code':'WASH','name':'外观清洗','billing_unit':'job','standard_fee_cents':3000})
    preset=post(client,'/presets',{'code':'WASH1','name':'标准洗车预填','profile':'wash','lines':[{'work_item_id':work['id'],'quantity_milli':1000}]})
    row,v,r,a,_=normal(client,resource(client,'wash'),preset)
    assert row['state']=='approval' and not row['quotes'][0]['price_approved'] and row['quotes'][0]['amount_cents']==3000
    repair_cmd(client,row,'start',{'result':'不得假设已授权'},409)
    row=authorize(client,row);row=repair_cmd(client,row,'start',{'result':'客户实际到店后开始洗车'})
    row=released(client,row);assert row['state']=='completed' and row['revenue_cents']==3000
    with SessionLocal() as db:
        assert db.get(ServiceResource,r['id']).active_case_id is None
        assert db.scalar(select(func.count()).select_from(ResourceUse))==2
        assert db.scalar(select(func.sum(PaymentLink.amount_cents)).where(PaymentLink.case_id==row['id']))==3000

def test_rework_same_origin_has_internal_floor_and_preserves_original_payment(client):
    original,v,res,_,_=normal(client);original,_=work_quote(client,original);original=repair_cmd(client,original,'start',{'result':'原单实际开始'});original=released(client,original)
    r=request_rework(client,original,v,res)
    cmd(client,'reworks',r,'convert',{'checked_vin':v['vin'],'odometer_km':1,'evidence_id':proof(client,r),'due_date':today().isoformat()},409)
    r=approve_rework(client,r);rework=convert_rework(client,r);assert rework['service_intake']['internal_only']
    rework,_=work_quote(client,rework,600);rework=repair_cmd(client,rework,'start',{'result':'开始本次责任修复'});rework=finish(client,rework)
    repair_cmd(client,rework,'allocate',{'labor_cost_cents':200,'evidence_id':evidence(client,rework),'allocations':[{'payer_type':'customer','amount_cents':600}]},409)
    rework=allocate(client,rework,[{'payer_type':'internal','payer_name':'门店维修责任','amount_cents':600}]);assert rework['customer_due_cents']==0 and rework['revenue_cents']==0
    rework=repair_cmd(client,rework,'release',{'evidence_id':evidence(client,rework)});assert rework['state']=='completed'
    report=client.get(f'/api/flow/analytics?date_from={today()}&date_to={today()}');assert report.status_code==200,report.text
    arrivals=report.json()['tables']['service_arrivals']['rows'];assert len(arrivals)==2 and any(x['values'][3]=='原单返修' for x in arrivals)
    assert report.json()['metrics']['service_arrivals_count']==2
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(PaymentLink.amount_cents)).where(PaymentLink.case_id==original['id']))==1000
        assert db.scalar(select(func.count()).select_from(PaymentLink).where(PaymentLink.case_id==rework['id']))==0
        assert db.scalar(select(ReworkRequest).where(ReworkRequest.id==r['id'])).active_source_id is None

def test_legacy_v3_requires_manager_binding_not_plate_matching(client):
    original,item,work,customer=repair_setup(client);original=ready(client,original,item,work);original=allocate(client,original);original=receive(client,original,original['allocations'][0],original['amount_cents'],bank(client));original=repair_cmd(client,original,'release',{'evidence_id':evidence(client,original)})
    v=care_vehicle(client,customer['id']);res=resource(client);source=next(s for s in client.get(API+'/sources').json()['items'] if s['id']==original['id'])
    values={'source_case_id':original['id'],'source_version':original['version'],'customer_vehicle_id':v['id'],'resource_id':res['id'],'source_line_ids':[source['lines'][0]['id']],'reason':'核对缺失VIN的原维修'}
    post(client,'/reworks',values,409)
    bind={'source_case_id':original['id'],'source_version':repair_detail(client,original)['version'],'customer_vehicle_id':v['id'],'checked_vin':v['vin'],'source_reference':'主管审核原接车VIN凭据','evidence_id':evidence(client,original)}
    post(client,'/bindings',bind);r=request_rework(client,original,v,res);assert r['status']=='requested'

def test_resource_actual_occupancy_blocks_overlap_and_rework_reentry(client):
    row,v,res,_,_=normal(client);row,_=work_quote(client,row);row=repair_cmd(client,row,'start',{'result':'实际占用该维修工位'})
    # Distinct vehicles may be inside the factory at once, but not on the same occupied resource.
    # A second arrival of this same VIN is separately rejected by the shared gate contract.
    another=care_vehicle(client,row['customer_id'],vin='LFV2A21K9J7654321')
    later=appointment(client,another,res,**slot(3));later=arrive(client,later);second=convert(client,later);second,_=work_quote(client,second)
    repair_cmd(client,second,'start',{'result':'原占用尚未释放'},409)
    row=repair_cmd(client,row,'finish',{'result':'本次施工已完成待检查'})
    result=post(client,f"/orders/{row['id']}/resource/release",{'version':row['version'],'values':{'reason':'已移到安全待检区','evidence_id':evidence(client,row)}},200)
    row=repair_cmd(client,result,'quality',{'passed':False,'result':'需继续处理缺陷','evidence_id':evidence(client,row)})
    repair_cmd(client,row,'finish',{'result':'未重新进位不能报完工'},409)
    row=post(client,f"/orders/{row['id']}/resource/acquire",{'version':row['version'],'values':{'reason':'实际返回工位继续施工','evidence_id':evidence(client,row)}},200)
    row=released(client,row);second=repair_cmd(client,second,'start',{'result':'工位已空实际开始下一单'});assert second['service_intake']['resource_occupied']

def test_appointment_reschedule_cancel_no_show_and_replay(client,monkeypatch):
    import app.service_intake_service as service
    v,_=customer_vehicle(client);res=resource(client);a=appointment(client,v,res);version=a['version'];key=uuid.uuid4().hex
    values={**slot(3),'resource_id':res['id'],'reason':'客户明确更改到店时段'}
    changed=cmd(client,'appointments',a,'reschedule',values,version=version,key=key)
    assert cmd(client,'appointments',a,'reschedule',values,version=version,key=key)==changed
    cmd(client,'appointments',a,'reschedule',values,version=version,status=409)
    cmd(client,'appointments',a,'no_show',{'reason':'尚未到预约结束'},409)
    monkeypatch.setattr(service,'utcnow',lambda:service._utc(changed['ends_at'])+timedelta(minutes=1))
    changed=cmd(client,'appointments',a,'no_show',{'reason':'结束后经核实未到店'});assert changed['status']=='no_show'
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(RepairIntake))==0

@pytest.mark.parametrize('operation',['book','convert','start','rework'])
def test_competing_intake_operations(client,operation):
    v,_=customer_vehicle(client);res=resource(client);body={'customer_vehicle_id':v['id'],'resource_id':res['id'],'problem':'并发预约核对',**slot()};path='/appointments'
    if operation!='book':
        a=arrive(client,appointment(client,v,res));path=f"/appointments/{a['id']}/actions/convert";body={'version':a['version'],'values':{'due_date':today().isoformat()}}
        if operation in {'start','rework'}:
            row=convert(client,a);row,_=work_quote(client,row)
            if operation=='start':path=f"/repair-orders/{row['id']}/actions/start";body={'version':row['version'],'values':{'result':'并发实际开工'}}
            else:
                row=repair_cmd(client,row,'start',{'result':'原单实际开工'});row=released(client,row)
                source=next(s for s in client.get(API+'/sources').json()['items'] if s['id']==row['id'])
                path='/reworks';body={'source_case_id':row['id'],'source_version':row['version'],'customer_vehicle_id':v['id'],'resource_id':res['id'],'source_line_ids':[source['lines'][0]['id']],'reason':'并发同原单返修'}
    clients=[TestClient(app),TestClient(app)]
    try:
        for c in clients:login(c)
        def run(c):return c.post(('/api' if operation=='start' else API)+path,json={'request_id':uuid.uuid4().hex,**body}).status_code
        with ThreadPoolExecutor(2) as pool:codes=list(pool.map(run,clients))
        assert sorted(codes)==([201,409] if operation in {'book','rework'} else [200,409]),codes
    finally:
        for c in clients:c.close()

def test_arrived_departure_preserves_fact_and_cannot_convert(client):
    from app.service_intake_models import ArrivalFact
    v,_=customer_vehicle(client);res=resource(client);a=arrive(client,appointment(client,v,res))
    cmd(client,'appointments',a,'cancel',{'reason':'不可抹除实际到店'},409)
    key=uuid.uuid4().hex;version=a['version'];values={'reason':'客户核实未开单离场','evidence_id':proof(client,a)}
    ended=cmd(client,'appointments',a,'leave',values,version=version,key=key)
    assert cmd(client,'appointments',a,'leave',values,version=version,key=key)==ended
    assert ended['status']=='cancelled' and ended['arrived_at'] and not ended['repair_case_id']
    cmd(client,'appointments',a,'convert',{'due_date':today().isoformat()},409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(ArrivalFact))==1
    appointment(client,v,res,starts_at=a['starts_at'],ends_at=a['ends_at'])

def test_rework_cancel_reject_and_unstarted_order_cancel_release_source(client):
    original,v,res,_,_=normal(client);original,_=work_quote(client,original);original=repair_cmd(client,original,'start',{'result':'原维修开工'});original=released(client,original)
    r=request_rework(client,original,v,res);r=cmd(client,'reworks',r,'reject',{'reason':'核对原责任不成立'});assert r['status']=='rejected'
    r=approve_rework(client,request_rework(client,original,v,res));r=cmd(client,'reworks',r,'cancel',{'reason':'客户取消本次未执行返修'});assert r['status']=='cancelled'
    r=approve_rework(client,request_rework(client,original,v,res));row=convert_rework(client,r)
    cmd(client,'reworks',r,'cancel',{'reason':'已有明细不能抹除申请'},409)
    repair_cmd(client,row,'cancel',{'reason':'客户取消未开工返修'})
    assert detail(client,'reworks',r)['status']=='cancelled'
    assert request_rework(client,original,v,res)['status']=='requested'

def test_cross_store_related_reads_actions_and_group_readonly_refused(client):
    original,v,res,a,_=normal(client);original,_=work_quote(client,original);original=repair_cmd(client,original,'start',{'result':'原维修开工'});original=released(client,original);r=request_rework(client,original,v,res)
    with SessionLocal() as db:
        db.add(Store(id=2,code='SECOND',name='另一门店'));u=db.scalar(select(User).where(User.username=='admin'));db.add(UserStore(user_id=u.id,store_id=2));db.commit()
    client.headers['X-Store-ID']='2'
    assert client.get(API+'/catalog').json()['vehicles']==[]
    for path in [f"/appointments/{a['id']}",f"/reworks/{r['id']}"]:
        assert client.get(API+path).status_code==404
    post(client,'/appointments',{'customer_vehicle_id':v['id'],'resource_id':res['id'],'problem':'跨店预约',**slot()},404)
    app_values={'reschedule':{**slot(),'resource_id':res['id'],'reason':'跨店改约'},'cancel':{'reason':'跨店取消'},'no_show':{'reason':'跨店未到'},'leave':{'reason':'跨店离场','evidence_id':1},'arrive':{'checked_vin':v['vin'],'odometer_km':1,'evidence_id':1},'convert':{'due_date':today().isoformat()}}
    for action,values in app_values.items():post(client,f"/appointments/{a['id']}/actions/{action}",{'version':a['version'],'values':values},404)
    rw_values={'approve':{'reason':'跨店责任','internal_name':'跨店主体','evidence_id':1},'reject':{'reason':'跨店拒绝'},'cancel':{'reason':'跨店撤销'},'convert':{**app_values['arrive'],'due_date':today().isoformat()}}
    for action,values in rw_values.items():post(client,f"/reworks/{r['id']}/actions/{action}",{'version':r['version'],'values':values},404)
    for action in ['acquire','release']:post(client,f"/orders/{original['id']}/resource/{action}",{'version':original['version'],'values':{'reason':'跨店进出位','evidence_id':1}},404)
    client.headers['X-Store-ID']='all'
    post(client,'/resources',{'code':'ALL','name':'集团不可过账','resource_type':'repair'},409)

def test_forged_original_line_vehicle_and_quarantine_refused(client):
    from app.file_security_models import FileSecurity
    original,v,res,_,customer=normal(client);original,_=work_quote(client,original);original=repair_cmd(client,original,'start',{'result':'原维修开工'});original=released(client,original)
    source=client.get(API+'/sources').json()['items'][0]
    values={'source_case_id':original['id'],'source_version':original['version'],'customer_vehicle_id':v['id'],'resource_id':res['id'],'source_line_ids':[999999],'reason':'核对被伪造项目'}
    post(client,'/reworks',values,404)
    other_vehicle=care_vehicle(client,customer['id'],vin='LFV2A21K9J7654321')
    post(client,'/reworks',{**values,'source_line_ids':[source['lines'][0]['id']],'customer_vehicle_id':other_vehicle['id']},409)
    with SessionLocal() as db:
        b=db.scalar(select(RepairVehicleBinding).where(RepairVehicleBinding.case_id==original['id']));db.info['_file_scan_authority']=True
        db.scalar(select(FileSecurity).where(FileSecurity.file_id==b.evidence_id)).state='quarantined';db.commit()
    post(client,'/reworks',{**values,'source_line_ids':[source['lines'][0]['id']]},409)

def test_employee_actions_assignee_transfer_and_private_prices(client):
    v,_=customer_vehicle(client);res=resource(client);a=appointment(client,v,res)
    login(client,'finance');post(client,'/resources',{'code':'NO','name':'非主管新增','resource_type':'repair'},403)
    post(client,f"/appointments/{a['id']}/actions/arrive",{'version':a['version'],'values':{'checked_vin':v['vin'],'odometer_km':1,'evidence_id':1}},403)
    login(client,'service');a=arrive(client,a);row=convert(client,a)
    with SessionLocal() as db:
        worker=User(username='service-two',display_name='接班服务顾问',role='service',password_hash=PASSWORD_HASH,must_change_password=False);db.add(worker);db.flush();db.add(UserStore(user_id=worker.id,store_id=1));db.commit();worker_id=worker.id
    login(client,'admin');task=next(t for t in client.get('/api/flow/cases/'+str(row['id'])).json()['tasks'] if t['key']=='repair_quote')
    result=client.post('/api/flow/tasks/'+str(task['id'])+'/assign',json={'version':task['version'],'assignee_id':worker_id,'reason':'人工交接明确后续责任'});assert result.status_code==200,result.text
    work=typed(client,'work_items',{'code':'ROLE-JOB','name':'岗位实际维修','billing_unit':'job','standard_fee_cents':1000})
    values={'reason':'服务顾问报价','lines':[{'kind':'work','source_id':work['id'],'quantity_milli':1000,'unit_price_cents':1000}]}
    login(client,'service');repair_cmd(client,row,'quote',values,409)
    login(client,'service-two');row=repair_cmd(client,row,'quote',values)
    repair_cmd(client,row,'price_approve',{'quote_id':row['quotes'][-1]['id'],'minimum_total_cents':0,'reason':'申请不能自批'},403)
    login(client,'manager');row=repair_cmd(client,row,'price_approve',{'quote_id':row['quotes'][-1]['id'],'minimum_total_cents':0,'reason':'主管核对价格'})
    login(client,'service');row=repair_cmd(client,row,'authorize',{'quote_id':row['quotes'][-1]['id'],'evidence_id':evidence(client,row,'authorization')})
    login(client,'technician');row=repair_detail(client,row);assert 'amount_cents' not in row and 'amount_cents' not in row['quotes'][0]
    row=repair_cmd(client,row,'start',{'result':'本人按授权实际开工'});assert row['service_intake']['resource_occupied']

def test_detailed_v4_parts_return_preserves_original_cost_and_internal_stop(client):
    from tests.test_procurement import setup as purchase_setup,command as purchase_cmd,receive as purchase_receive
    from tests.test_repair_orders import issue,return_material
    purchase,items,_=purchase_setup(client);purchase=purchase_cmd(client,purchase,'approve');purchase_receive(client,purchase)
    original,v,res,_,_=normal(client);original,_=work_quote(client,original);original=repair_cmd(client,original,'start',{'result':'原维修开工'});original=released(client,original)
    r=approve_rework(client,request_rework(client,original,v,res));row=convert_rework(client,r)
    with SessionLocal() as db:item=db.get(Item,items[0]['id']);before=(item.quantity_milli,item.inventory_value_cents)
    row=repair_cmd(client,row,'quote',{'reason':'返修使用本次独立配件','lines':[{'kind':'part','source_id':items[0]['id'],'quantity_milli':2000,'unit_price_cents':500}]})
    row=authorize(client,row);row=repair_cmd(client,row,'start',{'result':'实际处理本次返修'});row=issue(client,row,2000);source=row['stock'][0]
    repair_cmd(client,row,'cancel',{'reason':'已施工不允许抹除'},409)
    row=repair_cmd(client,row,'quote',{'purpose':'stop','reason':'客户约定停工且未使用配件全部退回','retained_amount_cents':300,'lines':[]});row=authorize(client,row)
    row=return_material(client,row,source,500);row=return_material(client,row,source,1500)
    row=finish(client,row);row=allocate(client,row,[{'payer_type':'internal','payer_name':'门店维修责任','amount_cents':300}]);row=repair_cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    with SessionLocal() as db:
        item=db.get(Item,items[0]['id']);assert (item.quantity_milli,item.inventory_value_cents)==before
        assert db.scalar(select(func.sum(StockMove.quantity_milli)).where(StockMove.case_id==row['id']))==0
        assert db.scalar(select(func.sum(StockMove.value_cents)).where(StockMove.case_id==row['id']))==0
        assert db.scalar(select(func.count()).select_from(PaymentLink).where(PaymentLink.case_id==row['id']))==0

def test_v4_authorization_category_prices_and_immutable_binding(client):
    from app.service_intake_models import ArrivalFact
    row,v,res,a,_=normal(client);work=typed(client,'work_items',{'code':'SAFE-AUTH','name':'客户报价授权','billing_unit':'job','standard_fee_cents':1000})
    row=repair_cmd(client,row,'quote',{'reason':'核对授权文件权限','lines':[{'kind':'work','source_id':work['id'],'quantity_milli':1000,'unit_price_cents':1000}]})
    q=row['quotes'][0];row=repair_cmd(client,row,'price_approve',{'quote_id':q['id'],'minimum_total_cents':0,'reason':'主管核对价格'})
    repair_cmd(client,row,'authorize',{'quote_id':q['id'],'evidence_id':evidence(client,row,'inspection')},422)
    fid=evidence(client,row,'authorization');row=repair_cmd(client,row,'authorize',{'quote_id':q['id'],'evidence_id':fid})
    for role in ['inventory','technician']:
        login(client,role);case=client.get('/api/flow/cases/'+str(row['id']));assert case.status_code==200
        assert fid not in [f['id'] for f in case.json()['files']]
        assert client.get('/api/flow/files/'+str(fid)).status_code==403
    with SessionLocal() as db:
        binding=db.scalar(select(RepairVehicleBinding).where(RepairVehicleBinding.case_id==row['id']));binding.vin='LFV2A21K9J7654321'
        with pytest.raises(HTTPException,match='不能覆盖'):db.commit()
        db.rollback();assert db.scalar(select(ArrivalFact.checked_vin))==v['vin']

def test_resource_boundary_and_same_vin_different_bays_compete(client):
    v,_=customer_vehicle(client);res=resource(client);first=appointment(client,v,res)
    from datetime import datetime
    boundary=datetime.fromisoformat(first['ends_at'].replace('Z','+00:00'))
    appointment(client,v,res,starts_at=boundary.isoformat(),ends_at=(boundary+timedelta(hours=1)).isoformat())
    second_resource=resource(client);second=appointment(client,v,second_resource,**slot(3))
    one=convert(client,arrive(client,first));one,_=work_quote(client,one)
    # The common gate now rejects duplicate actual arrivals before a second
    # repair can be opened, even on another resource. Boundary bookings remain legal.
    cmd(client,'appointments',second,'arrive',{'checked_vin':v['vin'],'odometer_km':10001,'evidence_id':proof(client,second)},409)
    one=repair_cmd(client,one,'start',{'result':'唯一原实际进厂进入工位'})
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ServiceResource).where(ServiceResource.active_case_id.is_not(None)))==1
    one=released(client,one)
    second=arrive(client,second)
    assert second['status']=='arrived'

def test_converted_reserved_slot_blocks_other_actual_work(client,monkeypatch):
    import app.service_intake_service as service
    v,_=customer_vehicle(client);res=resource(client);a=appointment(client,v,res);booked=convert(client,arrive(client,a));booked,_=work_quote(client,booked)
    another=care_vehicle(client,booked['customer_id'],vin='LFV2A21K9J7654321')
    other=appointment(client,another,res,**slot(3));outside=convert(client,arrive(client,other));outside,_=work_quote(client,outside)
    monkeypatch.setattr(service,'utcnow',lambda:service._utc(a['starts_at'])+timedelta(minutes=10))
    repair_cmd(client,outside,'start',{'result':'他车不得抢占已转单保留时段'},409)
    booked=repair_cmd(client,booked,'start',{'result':'本预约按实际时段开工'});assert booked['service_intake']['resource_occupied']

def test_local_day_task_due_including_reschedule(client):
    import app.service_intake_service as service
    from datetime import datetime,time
    from zoneinfo import ZoneInfo
    local_date=today()+timedelta(days=2);start=datetime.combine(local_date,time(1),ZoneInfo('Asia/Shanghai'))
    v,_=customer_vehicle(client);res=resource(client);a=appointment(client,v,res,starts_at=start.isoformat(),ends_at=(start+timedelta(hours=1)).isoformat())
    with SessionLocal() as db:assert db.scalar(select(Task.due_date).where(Task.case_id==a['case_id'],Task.key=='intake_arrive'))==local_date
    a=cmd(client,'appointments',a,'reschedule',{'resource_id':res['id'],'starts_at':(start+timedelta(days=1)).isoformat(),'ends_at':(start+timedelta(days=1,hours=1)).isoformat(),'reason':'保持当地凌晨日期的改约'})
    with SessionLocal() as db:assert db.scalar(select(Task.due_date).where(Task.case_id==a['case_id'],Task.key=='intake_arrive'))==local_date+timedelta(days=1)

@pytest.mark.parametrize('tamper',['vin','source_quote','allocation','occupancy','use','authorization','arrival'])
def test_nonempty_intake_restore_rejects_tampered_facts(client,tamper):
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.service_intake_backup_integrity import validate
    from app.backup_integrity import validate_sqlite
    original,v,res,_,_=normal(client);original,_=work_quote(client,original);original=repair_cmd(client,original,'start',{'result':'原维修实际开始'});original=released(client,original)
    r=approve_rework(client,request_rework(client,original,v,res));repair=convert_rework(client,r);repair,_=work_quote(client,repair,600);repair=repair_cmd(client,repair,'start',{'result':'责任返修独立施工'});repair=released(client,repair,True)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);result=validate(restored);assert result=={'verified_service_intakes':1,'verified_rework_requests':1,'verified_resource_uses':4,'verified_rework_extension_grants':0,'verified_rework_extensions':0,'verified_rework_quote_scopes':0}
        assert validate_sqlite(restored)['verified_files']>0
        statements={'vin':"UPDATE intake_vehicle_bindings SET vin='LFV2A21K9J7654321'",'source_quote':'UPDATE intake_rework_requests SET source_quote_id=-1',
            'allocation':"UPDATE repair_allocations SET payer_type='customer' WHERE payer_type='internal'",'occupancy':f"UPDATE intake_resources SET active_case_id={repair['id']} WHERE id={res['id']}",
            'use':"UPDATE intake_resource_uses SET action='release' WHERE id=1",'authorization':"UPDATE repair_authorizations SET quote_digest='fake'",'arrival':"UPDATE intake_arrivals SET checked_vin='LFV2A21K9J7654321'"}
        restored.execute(statements[tamper])
        with pytest.raises(ValueError,match='维修接待'):validate(restored)

def test_service_reports_use_actual_arrival_and_same_csv_population(client):
    import csv,io
    v,_=customer_vehicle(client);res=resource(client);a=arrive(client,appointment(client,v,res,mode='walk_in',**slot(0)));a=cmd(client,'appointments',a,'leave',{'reason':'本次到店后未维修离场','evidence_id':proof(client,a)})
    query=f'date_from={today()}&date_to={today()}';response=client.get('/api/flow/analytics?'+query);assert response.status_code==200,response.text;data=response.json()
    for name,expected in [('service_arrivals',1),('service_appointments',1),('service_resources',1)]:
        chart=next(c for c in data['charts'] if c['id']==name);rows=data['tables'][name]['rows'];assert sum(chart['series'][0]['values'])==len(rows)==expected
        export=client.get('/api/flow/analytics/export?dataset='+name+'&'+query);assert export.status_code==200,export.text
        csvrows=list(csv.reader(io.StringIO(export.content.decode('utf-8-sig'))));assert csvrows[1:]==[[str(v) for v in row['values']] for row in rows]
    assert data['metrics']['service_arrivals_count']==1 and data['metrics']['service_resources_busy']==0
    assert a['number'] in str(data['tables']['service_arrivals']['rows'])
    with SessionLocal() as db:
        db.add(Store(id=2,code='REPORT-SECOND',name='报表另一门店'));u=db.scalar(select(User).where(User.username=='admin'));db.add(UserStore(user_id=u.id,store_id=2));db.commit()
    client.headers['X-Store-ID']='2';other=client.get('/api/flow/analytics?'+query);assert other.status_code==200,other.text
    assert other.json()['metrics']['service_arrivals_count']==0 and other.json()['tables']['service_resources']['rows']==[]
    client.headers['X-Store-ID']='1';login(client,'technician')
    assert client.get('/api/flow/analytics/export?dataset=service_arrivals&'+query).status_code==403
