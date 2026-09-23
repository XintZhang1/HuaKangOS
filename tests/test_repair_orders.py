"""Repair v3 exact pricing, authorization, physical facts and multi-payer cash."""
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal,today
from app.models import User,UserStore,CashEntry
from app.flow_models import Case,Item,StockMove,PaymentLink
from app.repair_models import RepairQuote,RepairLine,RepairAuthorization,RepairStock,RepairAllocation,RepairPayment
from tests.conftest import login,PASSWORD_HASH
from tests.test_workflow import master,evidence
from tests.test_procurement import setup as purchase_setup,command as purchase_command,receive as purchase_receive,bank


@pytest.fixture(autouse=True)
def technician():
    with SessionLocal() as db:
        u=User(username='technician',display_name='独立技师',role='technician',password_hash=PASSWORD_HASH,must_change_password=False)
        db.add(u);db.flush();db.add(UserStore(user_id=u.id,store_id=1));db.commit()


def typed(c,kind,values):
    r=c.post('/api/masters/'+kind,json={'request_id':uuid.uuid4().hex,'values':values})
    assert r.status_code==201,r.text;return r.json()
def detail(c,row):
    r=c.get('/api/repair-orders/'+str(row['id']));assert r.status_code==200,r.text;return r.json()
def cmd(c,row,key,values=None,status=200,version=None,request_id=None):
    r=c.post(f"/api/repair-orders/{row['id']}/actions/{key}",json={'request_id':request_id or uuid.uuid4().hex,
        'version':detail(c,row)['version'] if version is None else version,'values':values or {}})
    assert r.status_code==status,r.text;return r.json()
def create(c,customer):
    r=c.post('/api/repair-orders',json={'request_id':uuid.uuid4().hex,'customer_id':customer['id'],'plate':'验收修A001','problem':'合成维修诊断','due_date':today().isoformat()})
    assert r.status_code==201,r.text;return r.json()
def setup(c):
    purchase,items,_=purchase_setup(c);purchase=purchase_command(c,purchase,'approve');purchase_receive(c,purchase)
    work=typed(c,'work_items',{'code':'WORK-'+uuid.uuid4().hex[:8],'name':'检查维修项目','billing_unit':'job','standard_fee_cents':10000})
    customer=master(c,'customers',{'name':'维修明细合成客户','phone':'13900000001','contact_allowed':True,'note':''})
    return create(c,customer),items[0],work,customer
def quote(c,row,item,work,quantity=2000,discount=3):
    return cmd(c,row,'quote',{'reason':'诊断后确认本次维修方案','discount_cents':discount,'lines':[
        {'kind':'work','source_id':work['id'],'quantity_milli':1000,'unit_price_cents':10000},
        {'kind':'part','source_id':item['id'],'quantity_milli':quantity,'unit_price_cents':500}]})
def authorize(c,row,evidence_id=None):
    q=detail(c,row)['quotes'][-1]
    row=cmd(c,row,'price_approve',{'quote_id':q['id'],'minimum_total_cents':0,'allow_below_minimum':False,'reason':'主管明确核对本报价及最低可接受价'})
    return cmd(c,row,'authorize',{'quote_id':q['id'],'evidence_id':evidence_id or evidence(c,row,'authorization')})
def current_quote(c,row):
    row=detail(c,row);return next(q for q in row['quotes'] if q['id']==row['data']['quote_id'])
def issue(c,row,quantity):
    line=next(l for l in current_quote(c,row)['lines'] if l['kind']=='part')
    return cmd(c,row,'issue',{'line_key':line['line_key'],'quantity_milli':quantity,'evidence_id':evidence(c,row)})
def return_material(c,row,source,quantity,**kwargs):
    return cmd(c,row,'return_material',{'original_id':source['id'],'quantity_milli':quantity,'evidence_id':evidence(c,row)},**kwargs)
def ready(c,row,item,work):
    row=quote(c,row,item,work);row=authorize(c,row);row=cmd(c,row,'start',{'result':'技师核对当前授权后开工'})
    row=issue(c,row,2000);row=cmd(c,row,'finish',{'result':'授权项目施工完成，配件已使用'})
    return cmd(c,row,'quality',{'passed':True,'result':'全部检查通过','evidence_id':evidence(c,row,'inspection')})
def allocate(c,row,allocations=None):
    return cmd(c,row,'allocate',{'labor_cost_cents':1000,'evidence_id':evidence(c,row),
        'allocations':allocations if allocations is not None else [{'payer_type':'customer','amount_cents':detail(c,row)['amount_cents'],'due_date':today().isoformat()}]})
def receive(c,row,allocation,amount,account):
    return cmd(c,row,'receive',{'allocation_id':allocation['id'],'amount_cents':amount,'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':evidence(c,row,'receipt')})


def test_multiline_quote_physical_return_and_multi_party_late_cash(client):
    row,item,work,_=setup(client);row=quote(client,row,item,work)
    assert sum(l['amount_cents'] for l in row['quotes'][0]['lines'])==10997
    row=authorize(client,row);row=cmd(client,row,'start',{'result':'实际开工'})
    row=issue(client,row,2000);source=row['stock'][0]
    row=return_material(client,row,source,500);row=issue(client,row,500)
    row=cmd(client,row,'finish',{'result':'实际施工结束'})
    row=cmd(client,row,'quality',{'passed':False,'result':'发现缺陷需返工','evidence_id':evidence(client,row)})
    cmd(client,row,'allocate',{'labor_cost_cents':0,'evidence_id':evidence(client,row),'allocations':[]},409)
    cmd(client,row,'release',{'evidence_id':evidence(client,row)},409)
    row=cmd(client,row,'finish',{'result':'已处理缺陷重新提交'})
    row=cmd(client,row,'quality',{'passed':True,'result':'复检通过','evidence_id':evidence(client,row)})
    insurer=typed(client,'insurers',{'code':'INS-1','name':'合成保险公司'})
    manufacturer=master(client,'references',{'category':'厂家','name':'合成生产厂家','detail':'厂家赔付核对','active':True})
    splits=[{'payer_type':'customer','amount_cents':1997},{'payer_type':'insurer','payer_id':insurer['id'],'amount_cents':3000},
        {'payer_type':'manufacturer','payer_id':manufacturer['id'],'amount_cents':4000},{'payer_type':'internal','payer_name':'集团内部承担','amount_cents':2000}]
    row=allocate(client,row,splits);assert row['revenue_cents']==8997 and row['cost_cents']==1246
    a=bank(client);customer=row['allocations'][0]
    row=receive(client,row,customer,1000,a);cmd(client,row,'release',{'evidence_id':evidence(client,row)},409)
    row=receive(client,row,customer,997,a);row=cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    assert row['state']=='credit_open' and row['receivable_cents']==7000
    for allocation in row['allocations'][1:3]:row=receive(client,row,allocation,allocation['amount_cents'],a)
    assert row['state']=='completed' and row['receivable_cents']==0
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(PaymentLink.amount_cents)).where(PaymentLink.case_id==row['id']))==8997
        assert db.scalar(select(func.sum(CashEntry.amount_cents)).where(CashEntry.category=='workflow_repair'))==8997
        stored=db.get(Item,item['id']);assert (stored.quantity_milli,stored.inventory_value_cents)==(500,62)


def test_amendment_needs_current_price_and_customer_authorization(client):
    row,item,work,_=setup(client);row=quote(client,row,item,work,1000,0)
    q=row['quotes'][-1]
    cmd(client,row,'price_approve',{'quote_id':q['id'],'minimum_total_cents':10600,'reason':'确认最低价格','allow_below_minimum':False},409)
    row=cmd(client,row,'price_approve',{'quote_id':q['id'],'minimum_total_cents':10600,'reason':'主管明确承担本次低价例外','allow_below_minimum':True})
    fid=evidence(client,row,'authorization');row=cmd(client,row,'authorize',{'quote_id':q['id'],'evidence_id':fid})
    row=cmd(client,row,'start',{'result':'按原授权开工'});row=issue(client,row,1000)
    lines=[{'line_key':l['line_key'],'kind':l['kind'],'source_id':l['work_item_id'] or l['item_id'],
        'quantity_milli':l['quantity_milli']+(1000 if l['kind']=='part' else 0),'unit_price_cents':l['unit_price_cents']} for l in current_quote(client,row)['lines']]
    row=cmd(client,row,'quote',{'reason':'追加已确认需要的配件','lines':lines,'discount_cents':1})
    q2=row['quotes'][-1];cmd(client,row,'issue',{'line_key':lines[1]['line_key'],'quantity_milli':1,'evidence_id':evidence(client,row)},409)
    cmd(client,row,'authorize',{'quote_id':q['id'],'evidence_id':evidence(client,row)},409)
    row=cmd(client,row,'price_approve',{'quote_id':q2['id'],'minimum_total_cents':0,'reason':'复核追加报价','allow_below_minimum':False})
    cmd(client,row,'authorize',{'quote_id':q2['id'],'evidence_id':fid},409)
    old_bytes=client.get('/api/flow/files/'+str(fid)).content
    clone=client.post(f"/api/flow/cases/{row['id']}/files",data={'category':'authorization'},files={'file':('重复上传旧授权.txt',old_bytes,'text/plain')})
    assert clone.status_code==200,clone.text
    cmd(client,row,'authorize',{'quote_id':q2['id'],'evidence_id':clone.json()['id']},409)
    row=cmd(client,row,'authorize',{'quote_id':q2['id'],'evidence_id':evidence(client,row,'authorization')})
    row=issue(client,row,1000);assert row['amount_cents']==10999
    assert row['quotes'][0]['lines'][0]['amount_cents']==row['quotes'][1]['lines'][0]['amount_cents']
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(RepairAuthorization))==2


def test_started_cancel_uses_authorized_stop_fee_and_original_returns(client):
    row,item,work,_=setup(client);row=authorize(client,quote(client,row,item,work));row=cmd(client,row,'start',{'result':'已经开始检查'})
    row=issue(client,row,2000);source=row['stock'][0]
    cmd(client,row,'cancel',{'reason':'不能抹除实际施工'},409)
    row=cmd(client,row,'quote',{'purpose':'stop','retained_amount_cents':1000,'reason':'客户要求停止；已完成检查协商保留十元','lines':[]})
    row=authorize(client,row);row=return_material(client,row,source,2000)
    cmd(client,row,'issue',{'line_key':source['line_key'],'quantity_milli':1,'evidence_id':evidence(client,row)},409)
    row=cmd(client,row,'finish',{'result':'已完成检查，未使用配件全部退回'})
    row=cmd(client,row,'quality',{'passed':True,'result':'停工后交接安全检查通过','evidence_id':evidence(client,row)})
    row=allocate(client,row);row=receive(client,row,row['allocations'][0],1000,bank(client));row=cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    assert row['state']=='completed' and row['amount_cents']==1000
    with SessionLocal() as db:
        assert (db.get(Item,item['id']).quantity_milli,db.get(Item,item['id']).inventory_value_cents)==(2500,308)
        assert db.scalar(select(func.sum(StockMove.value_cents)).where(StockMove.case_id==row['id']))==0


def test_quote_and_command_replays_stale_and_cancellation(client):
    row,item,work,_=setup(client);version=row['version'];key=uuid.uuid4().hex
    values={'reason':'核对取消业务','lines':[{'kind':'work','source_id':work['id'],'quantity_milli':1000,'unit_price_cents':100}]}
    row=cmd(client,row,'quote',values,version=version,request_id=key)
    cmd(client,row,'quote',values,version=version,request_id=key)
    cmd(client,row,'quote',values,version=version,status=409)
    row=cmd(client,row,'quote_cancel',{'quote_id':row['quotes'][0]['id'],'reason':'尚未授权作废报价'})
    assert row['state']=='assessment' and row['quotes'][0]['cancelled']
    row=cmd(client,row,'cancel',{'reason':'客户未开工取消'})
    assert row['state']=='cancelled'
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RepairQuote))==1
        line=db.scalar(select(RepairLine));line.amount_cents=1
        with pytest.raises(HTTPException):db.commit()


def test_real_employee_roles_cost_visibility_and_stock_assignment(client):
    row,item,work,customer=setup(client);login(client,'service');row=create(client,customer);row=quote(client,row,item,work)
    cmd(client,row,'price_approve',{'quote_id':row['quotes'][0]['id'],'minimum_total_cents':0,'reason':'非法自行批准'},403)
    login(client,'manager');row=cmd(client,row,'price_approve',{'quote_id':row['quotes'][0]['id'],'minimum_total_cents':0,'reason':'主管明确价格授权'})
    login(client,'service');row=cmd(client,row,'authorize',{'quote_id':row['quotes'][0]['id'],'evidence_id':evidence(client,row)})
    login(client,'technician');assert 'amount_cents' not in detail(client,row)
    row=cmd(client,row,'start',{'result':'技师实际开工'})
    cmd(client,row,'issue',{'line_key':current_quote(client,row)['lines'][1]['line_key'],'quantity_milli':2000,'evidence_id':evidence(client,row)},403)
    login(client,'inventory');assert 'unit_price_cents' not in current_quote(client,row)['lines'][0]
    row=issue(client,row,2000);assert 'value_cents' not in row['stock'][0]
    login(client,'technician');row=cmd(client,row,'finish',{'result':'实际施工完成'})
    login(client,'service');row=cmd(client,row,'quality',{'passed':True,'result':'独立岗位检查通过','evidence_id':evidence(client,row)})
    login(client,'manager');row=allocate(client,row);a=bank(client)
    login(client,'finance');row=receive(client,row,row['allocations'][0],10997,a)
    login(client,'service');row=cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    assert row['state']=='completed'


@pytest.mark.parametrize('key,values',[('quote',{'reason':'跨店','lines':[]}),('price_approve',{'quote_id':1,'minimum_total_cents':0,'reason':'跨店'}),
    ('authorize',{'quote_id':1,'evidence_id':1}),('start',{'result':'跨店'}),('issue',{'line_key':'x','quantity_milli':1,'evidence_id':1}),
    ('return_material',{'original_id':1,'quantity_milli':1,'evidence_id':1}),('finish',{'result':'跨店'}),('quality',{'passed':True,'result':'跨店','evidence_id':1}),
    ('allocate',{'labor_cost_cents':0,'allocations':[],'evidence_id':1}),('receive',{'allocation_id':1,'amount_cents':1,'account_id':1,'reference':'cross','evidence_id':1}),
    ('release',{'evidence_id':1}),('cancel',{'reason':'跨店'}),('quote_cancel',{'quote_id':1,'reason':'跨店'})])
def test_all_branches_refuse_other_store(client,key,values):
    row,_,_,_=setup(client);fid=evidence(client,row)
    two=client.post('/api/stores',json={'code':'B','name':'另一门店','active':True}).json()['id'];client.headers['X-Store-ID']=str(two)
    assert client.get('/api/repair-orders').json()['total']==0
    assert client.get('/api/repair-orders/'+str(row['id'])).status_code==404
    assert client.get('/api/flow/files/'+str(fid)).status_code==404
    response=client.post(f"/api/repair-orders/{row['id']}/actions/{key}",json={'request_id':uuid.uuid4().hex,'version':row['version'],'values':values})
    assert response.status_code==404,response.text


def race(client,row,key,values):
    version=detail(client,row)['version']
    def worker(c):
        return c.post(f"/api/repair-orders/{row['id']}/actions/{key}",json={'request_id':uuid.uuid4().hex,'version':version,'values':values}).status_code
    with TestClient(app) as first,TestClient(app) as second:
        login(first);login(second)
        with ThreadPoolExecutor(max_workers=2) as executor:return sorted(executor.map(worker,[first,second]))


def test_competing_issue_return_and_payment_post_each_fact_once(client):
    row,item,work,_=setup(client);row=authorize(client,quote(client,row,item,work));row=cmd(client,row,'start',{'result':'实际开工'})
    key=current_quote(client,row)['lines'][1]['line_key'];fid=evidence(client,row)
    assert race(client,row,'issue',{'line_key':key,'quantity_milli':2000,'evidence_id':fid})==[200,409]
    row=detail(client,row);source=row['stock'][0]
    assert race(client,row,'return_material',{'original_id':source['id'],'quantity_milli':1000,'evidence_id':fid})==[200,409]
    row=issue(client,row,1000);row=cmd(client,row,'finish',{'result':'重新核对实际施工完成'})
    row=cmd(client,row,'quality',{'passed':True,'result':'检查通过','evidence_id':fid});row=allocate(client,row)
    a=bank(client);fid=evidence(client,row,'receipt')
    assert race(client,row,'receive',{'allocation_id':row['allocations'][0]['id'],'amount_cents':10997,'account_id':a,'reference':'once-cash','evidence_id':fid})==[200,409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RepairPayment))==1
        assert db.scalar(select(func.count()).select_from(RepairStock))==3
        assert db.scalar(select(func.sum(StockMove.value_cents)).where(StockMove.case_id==row['id']))==-246


def test_quarantined_auth_and_allocation_and_return_bounds(client,monkeypatch):
    from tests.test_file_security import mode
    row,item,work,_=setup(client);row=quote(client,row,item,work)
    q=row['quotes'][0];row=cmd(client,row,'price_approve',{'quote_id':q['id'],'minimum_total_cents':0,'reason':'明确价格授权'})
    mode(monkeypatch,'quarantine');fid=evidence(client,row,'authorization')
    cmd(client,row,'authorize',{'quote_id':q['id'],'evidence_id':fid},409)
    mode(monkeypatch,'structure_only');row=cmd(client,row,'authorize',{'quote_id':q['id'],'evidence_id':evidence(client,row,'authorization')})
    row=cmd(client,row,'start',{'result':'实际开工'});row=issue(client,row,2000)
    return_material(client,row,row['stock'][0],2001,status=409)
    row=cmd(client,row,'finish',{'result':'施工完成'});row=cmd(client,row,'quality',{'passed':True,'result':'检查通过','evidence_id':evidence(client,row)})
    mode(monkeypatch,'quarantine');fid=evidence(client,row)
    cmd(client,row,'allocate',{'labor_cost_cents':0,'allocations':[{'payer_type':'customer','amount_cents':10997}],'evidence_id':fid},409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(RepairAllocation))==0


def test_allocation_exact_sum_inactive_party_and_history_versions(client):
    row,item,work,_=setup(client);row=ready(client,row,item,work)
    cmd(client,row,'allocate',{'labor_cost_cents':0,'allocations':[{'payer_type':'customer','amount_cents':10998}],'evidence_id':evidence(client,row)},422)
    supplier=master(client,'references',{'category':'供应商','name':'不是厂家','detail':'不能冒作厂家','active':True})
    cmd(client,row,'allocate',{'labor_cost_cents':0,'allocations':[{'payer_type':'manufacturer','payer_id':supplier['id'],'amount_cents':10997}],'evidence_id':evidence(client,row)},422)
    response=client.post(f"/api/flow/cases/{row['id']}/actions/quote",json={'request_id':uuid.uuid4().hex,'version':row['version'],'values':{}})
    assert response.status_code==409
    from tests.test_workflow_extended import repair
    old=repair(client)
    assert old['flow_version']==2
    assert client.get('/api/repair-orders/'+str(old['id'])).status_code==409
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(RepairAllocation))==0
