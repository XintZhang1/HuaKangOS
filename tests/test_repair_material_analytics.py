"""Actual issue/return dimensions, original-cost signs, immutable model and scope."""
import csv,io,uuid
from datetime import timedelta
from sqlalchemy import select,text,func
from app.db import SessionLocal,engine,today
from app.flow_models import StockMove,FlowEvent
from tests.conftest import login
from tests.test_repair_orders import technician,quote,authorize,cmd,issue,return_material,typed
from tests.test_service_intake import normal,cmd as intake_cmd
from tests.test_procurement import setup as purchase_setup,command as purchase_command,receive as purchase_receive
from tests.test_workflow import evidence
API='/api/repair-material-reports'

def report(c,**params):
    r=c.get(API,params=params);assert r.status_code==200,r.text;return r.json()
def source(c,actual=True,two_work=False):
    purchase,items,_=purchase_setup(c);purchase=purchase_command(c,purchase,'approve');purchase_receive(c,purchase)
    row,v,resource,a,customer=normal(c);work=typed(c,'work_items',{'code':'ACTUAL-W','name':'实际诊断作业','billing_unit':'job','standard_fee_cents':10000})
    if two_work:
        other=typed(c,'work_items',{'code':'ACTUAL-W2','name':'同报价另一作业','billing_unit':'job','standard_fee_cents':100})
        row=cmd(c,row,'quote',{'reason':'两项作业但一条实际配件','lines':[{'kind':'work','source_id':w['id'],'quantity_milli':1000,'unit_price_cents':10000} for w in (work,other)]+[{'kind':'part','source_id':items[0]['id'],'quantity_milli':2000,'unit_price_cents':500}]})
    else:row=quote(c,row,items[0],work)
    row=authorize(c,row);row=cmd(c,row,'start',{'result':'真实开工，尚未领料'})
    if actual:row=issue(c,row,1000)
    return row,items[0],work,v,a

def csv_same(c,d,key,**params):
    r=c.get(API+'/export/'+key,params=params);assert r.status_code==200,r.text
    values=list(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))));t=d['tables'][key]
    assert values==[t['headers']]+[[str(v) for v in row['values']] for row in t['rows']]


def test_quote_is_not_actual_material_and_original_return_cost_is_exact(client):
    row,item,work,v,_=source(client,False);assert report(client)['details']==[]
    row=issue(client,row,1000);original=row['stock'][0];row=return_material(client,row,original,333)
    d=report(client);assert d['complete'] and d['model_complete'];assert len(d['details'])==2
    assert d['rows'][0]['issued_milli']==1000 and d['rows'][0]['returned_milli']==333 and d['rows'][0]['net_milli']==667
    with SessionLocal() as db:
        movements=list(db.scalars(select(StockMove).where(StockMove.case_id==row['id'])))
        assert d['rows'][0]['net_cents']==-sum(m.value_cents for m in movements)
    for key in d['tables']:csv_same(client,d,key)
    assert sum(d['charts'][0]['series'][0]['values'])==sum(r['amount_cents'] for r in d['tables']['repair_material_totals']['rows'])
    row=return_material(client,row,original,667);d=report(client);assert d['rows'][0]['net_milli']==d['rows'][0]['net_cents']==0


def test_work_filter_semijoin_never_duplicates_and_current_rename_not_history(client):
    row,item,work,v,_=source(client,two_work=True);d=report(client);assert len(d['details'])==1 and len(d['details'][0]['work_items'])==2
    for w in d['options']['work_items']:
        filtered=report(client,work_item_id=w['id']);assert filtered['rows'][0]['net_cents']==d['rows'][0]['net_cents'] and len(filtered['details'])==1
    old=d['details'][0]['model_name']
    v=client.get('/api/customer-service/vehicles/'+str(v['id'])).json()['vehicle']
    r=client.put('/api/customer-service/vehicles/'+str(v['id']),json={'request_id':uuid.uuid4().hex,'version':v['version'],'values':{'plate':v['plate'],'model_name':'更新后当前车型不可冒充历史','active':True,'reason':'合成车型名称有据更正'}});assert r.status_code==200,r.text
    assert report(client,model_name=old)['details'][0]['model_name']==old
    r=client.get(API,params={'model_name':'更新后当前车型不可冒充历史'});assert r.status_code==404
    assert report(client,work_item_id=work['id'],item_id=item['id'],case_id=row['id'])['details'][0]['source_id']==d['details'][0]['source_id']


def test_older_binding_without_snapshot_stays_unknown_and_snapshot_is_immutable(client):
    row,_,_,_,_=source(client)
    with SessionLocal() as db:
        e=db.scalar(select(FlowEvent).where(FlowEvent.case_id==row['id'],FlowEvent.action=='repair_vehicle_model_snapshot'))
        import pytest
        from fastapi import HTTPException
        with pytest.raises(HTTPException):e.detail={'model_name':'不得覆盖'};db.commit()
        db.rollback()
    # Synthetic fixture simulates a previously bound case predating this feature.
    with engine.begin() as db:db.execute(text("DELETE FROM flow_events WHERE action='repair_vehicle_model_snapshot' AND case_id=:id"),{'id':row['id']})
    d=report(client);assert d['complete'] and not d['model_complete'] and d['details'][0]['model_name'] is None
    assert report(client,model_name='__unknown__')['rows'][0]['net_milli']==1000
    assert d['options']['models']==[]


def test_cross_period_return_uses_actual_date_and_signed_net(client):
    row,_,_,_,_=source(client);source_move=row['stock'][0];previous=today()-timedelta(days=1)
    with engine.begin() as db:db.execute(text('UPDATE flow_stock_moves SET business_date=:day WHERE id=:id'),{'day':previous.isoformat(),'id':source_move['stock_move_id']})
    return_material(client,row,source_move,400)
    d=report(client,date_from=today().isoformat(),date_to=today().isoformat());assert d['complete']
    assert d['rows'][0]['issued_milli']==0 and d['rows'][0]['net_milli']==-400 and d['rows'][0]['net_cents']<0
    csv_same(client,d,'repair_material_movements',date_from=today().isoformat(),date_to=today().isoformat())
    old=report(client,date_from=previous.isoformat(),date_to=previous.isoformat());assert old['rows'][0]['net_milli']==1000


def test_duplicate_issue_stale_and_failed_convert_do_not_duplicate_model_or_ledger(client):
    row,_,_,_,a=source(client,False);q=row['quotes'][-1];line=next(l for l in q['lines'] if l['kind']=='part');fid=evidence(client,row)
    body={'line_key':line['line_key'],'quantity_milli':1000,'evidence_id':fid};from tests.test_repair_orders import detail
    version=detail(client,row)['version'];key=uuid.uuid4().hex
    cmd(client,row,'issue',body,version=version,request_id=key);cmd(client,row,'issue',body,version=version,request_id=key)
    cmd(client,row,'issue',body,status=409,version=version)
    intake_cmd(client,'appointments',a,'convert',{'due_date':today().isoformat()},409)
    assert len(report(client)['details'])==1
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(FlowEvent).where(FlowEvent.case_id==row['id'],FlowEvent.action=='repair_vehicle_model_snapshot'))==1


def test_roles_scope_export_and_combined_report_do_not_leak_cost(client):
    row,item,work,_,_=source(client);d=report(client)
    combined=client.get('/api/flow/analytics').json()
    for key,t in d['tables'].items():assert combined['tables'][key]==t
    login(client,'inventory');data=report(client);assert not data['can_money'] and 'value_cents' not in str(data['details']) and 'net_cents' not in str(data['rows']) and data['charts']==[]
    assert '成本（元）' not in str(data['tables']);csv_same(client,data,'repair_material_movements')
    login(client,'sales');assert client.get(API).status_code==403 and client.get(API+'/export/repair_material_totals').status_code==403
    login(client,'admin');client.post('/api/stores',json={'code':'RM-OTHER','name':'合成另一门店'});client.headers['X-Store-ID']='2'
    assert report(client)['details']==[]
    for param,value in [('case_id',row['id']),('item_id',item['id']),('work_item_id',work['id'])]:assert client.get(API,params={param:value}).status_code==404
    client.headers['X-Store-ID']='all';assert all(not r.get('route') for t in report(client)['tables'].values() for r in t['rows'])


def test_source_mismatch_never_returns_complete_cost_chart(client):
    row,_,work,_,_=source(client)
    with engine.begin() as db:db.execute(text('UPDATE repair_stock SET value_cents=value_cents+1 WHERE case_id=:id'),{'id':row['id']})
    d=report(client,work_item_id=work['id']);assert not d['complete'] and not d['charts']
    assert d['metrics']['repair_material_actual_net_cents'] is None and '数量成本不一致' in str(d['issues'])


def test_invalid_snapshot_and_dates_fail_closed(client):
    row,_,_,_,_=source(client)
    with engine.begin() as db:db.execute(text("UPDATE flow_events SET detail='{}' WHERE case_id=:id AND action='repair_vehicle_model_snapshot'"),{'id':row['id']})
    d=report(client);assert not d['complete'] and not d['model_complete'] and '绑定不一致' in str(d['issues'])
    assert client.get(API,params={'date_from':today().isoformat(),'date_to':(today()-timedelta(days=1)).isoformat()}).status_code==422


def test_generic_historical_repair_has_actual_cost_but_no_invented_quote_or_model(client):
    from tests.test_workflow import test_inventory_and_repair_chain
    test_inventory_and_repair_chain(client)
    d=report(client);assert d['complete'] and not d['model_complete'] and len(d['details'])==1
    f=d['details'][0];assert f['quantity_milli']==4000 and f['value_cents']==12000 and f['quote_id'] is None and not f['work_items']
    assert '无报价作业维度' in f['context_note'] and d['options']['models']==[]
    csv_same(client,d,'repair_material_movements')


def test_same_database_snapshot_keeps_pending_actual_return_out_of_old_report(client):
    from app.repair_material_analytics import build_repair_materials
    from app.models import User
    from app.tenancy import set_scope,project_user
    row,_,_,_,_=source(client);original=row['stock'][0]
    with SessionLocal() as old:
        set_scope(old,[1],1);user=project_user(old.scalar(select(User).where(User.username=='admin')),'admin')
        assert old.scalar(select(StockMove.id).where(StockMove.case_id==row['id']))
        return_material(client,row,original,500)
        data=build_repair_materials(old,user);assert data['complete'] and data['rows'][0]['net_milli']==1000
    assert report(client)['rows'][0]['net_milli']==500


def test_amended_quote_work_filter_keeps_original_issue_and_return_versions(client):
    from tests.test_repair_orders import current_quote
    row,item,work,_,_=source(client);original=row['stock'][0];old_quote=current_quote(client,row)
    extra=typed(client,'work_items',{'code':'AMEND-W','name':'增项后才有作业','billing_unit':'job','standard_fee_cents':100})
    lines=[{'line_key':l['line_key'],'kind':l['kind'],'source_id':l['work_item_id'] or l['item_id'],'quantity_milli':2500 if l['kind']=='part' else l['quantity_milli'],'unit_price_cents':l['unit_price_cents']} for l in old_quote['lines']]
    lines.append({'kind':'work','source_id':extra['id'],'quantity_milli':1000,'unit_price_cents':100})
    row=cmd(client,row,'quote',{'reason':'增加作业和配件授权量','discount_cents':3,'lines':lines});row=authorize(client,row)
    row=issue(client,row,500);return_material(client,row,original,250)
    all_rows=report(client);filtered=report(client,work_item_id=extra['id'])
    assert all_rows['complete'] and len(all_rows['details'])==3 and all_rows['rows'][0]['net_milli']==1250
    assert len(filtered['details'])==1 and filtered['details'][0]['quantity_milli']==500
    original_return=next(f for f in all_rows['details'] if f['kind']=='退料')
    assert original_return['quote_id']==old_quote['id'] and extra['id'] not in original_return['work_items']
    csv_same(client,filtered,'repair_material_movements',work_item_id=extra['id'])
