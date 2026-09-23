"""Facts precede settlement; project versions and actual installation are not revenue."""
import csv,io
from datetime import timedelta
from sqlalchemy import select,text
from app.db import today,SessionLocal
from app.flow_models import Case
from app.repair_models import RepairLine,RepairSettlement
from tests import test_workflow as flow,test_repair_orders as repair,test_retail as retail
from tests.conftest import login
from tests.test_multistore import second_store,switch


def report(c,**params):
    r=c.get('/api/flow/analytics',params=params);assert r.status_code==200,r.text;return r.json()
def reconciled(c,key,amount,**params):
    data=report(c,**params);table=data['tables'][key]
    assert sum(r['amount_cents'] for r in table['rows'])==amount
    chart=next(ch for ch in data['charts'] if ch['id']==key)
    assert sum(chart['series'][0]['values'])==amount
    response=c.get('/api/flow/analytics/export',params={'dataset':key,**params});assert response.status_code==200,response.text
    rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows[0]==table['headers']
    assert [[v.removeprefix("'") for v in row] for row in rows[1:]]==[[str(v) for v in row['values']] for row in table['rows']]
    return data


def finished_children(c):
    order=flow.action(c,flow.order(c,addon=True,agency=True,insurance=True),'approve')
    children={x['kind']:x for x in flow.detail(c,order)['children']}
    for kind,amount in [('addon','123.45'),('agency','20.01'),('insurance','300.00')]:
        child=children[kind]
        values={'amount':amount,'work':'合成项目'} if kind!='insurance' else {'amount':amount,'insurer':'合成保险公司','commission':'3.21'}
        child=flow.action(c,child,'service_quote',values)
        values={'evidence_id':flow.evidence(c,child)}
        if kind=='insurance':values.update(policy_number='ANALYTICS-POLICY',start_date=today().isoformat(),end_date=(today()+timedelta(days=365)).isoformat())
        children[kind]=flow.action(c,child,'policy_issue' if kind=='insurance' else 'service_finish',values)
    return children


def test_completed_service_facts_precede_cash_and_have_distinct_insurance_basis(client):
    children=finished_children(client)
    for kind,value in [('addon',12345),('agency',2001),('insurance',30000)]:
        data=reconciled(client,kind+'_completed',value)
        assert data['metrics']['cash_in_cents']==0
        assert data['tables'][kind+'_completed']['rows'][0]['route']['id']==children[kind]['id']
    assert data['tables']['insurance_completed']['rows'][0]['values'][-1]=='3.21'
    old=(today()-timedelta(days=1)).isoformat()
    for kind in children:reconciled(client,kind+'_completed',0,date_from=old,date_to=old)
    second_store(client);switch(client,2)
    for kind in children:assert report(client)['tables'][kind+'_completed']['rows']==[]
    switch(client,1);login(client,'inventory')
    assert client.get('/api/flow/analytics/export',params={'dataset':'insurance_completed'}).status_code==403


def test_missing_original_quote_refuses_money_guessing(client):
    children=finished_children(client)
    with SessionLocal() as db:
        db.execute(text("DELETE FROM flow_events WHERE case_id=:id AND action='service_quote'"),{'id':children['addon']['id']});db.commit()
    response=client.get('/api/flow/analytics');assert response.status_code==409 and '核价依据' in response.json()['detail']


def test_repair_projects_use_settlement_quote_only_and_include_internal_basis_without_cash(client):
    order,item,work,_=repair.setup(client);order=repair.ready(client,order,item,work)
    order=repair.allocate(client,order,[{'payer_type':'internal','payer_name':'门店责任','amount_cents':order['amount_cents']}])
    order=repair.cmd(client,order,'release',{'evidence_id':flow.evidence(client,order)})
    with SessionLocal() as db:
        settled=db.scalar(select(RepairSettlement).where(RepairSettlement.case_id==order['id']))
        lines=list(db.scalars(select(RepairLine).where(RepairLine.quote_id==settled.quote_id)))
        expected={kind:sum(l.amount_cents for l in lines if l.kind==kind) for kind in ('work','part')}
    data=reconciled(client,'repair_projects',expected['work']);reconciled(client,'repair_parts',expected['part'])
    assert data['metrics']['repair_cents']==data['metrics']['cash_in_cents']==0
    assert expected['work']+expected['part']==order['amount_cents']


def test_installation_uses_original_scope_after_actual_prior_returns_and_later_return_cannot_erase_work(client):
    items,customer,work,_=retail.setup(client,True)
    order=retail.authorize(client,retail.approve(client,retail.create(client,items,customer,work)))
    order=retail.dispatch(client,order);source=order['dispatches'][0]
    order,ret=retail.request_return(client,order,source,500)
    order=retail.ret_cmd(client,order,ret,'return_approve');order=retail.ret_cmd(client,order,ret,'return_receive')
    expected=order['lines'][0]['installation_cents']-order['return_postings'][0]['installation_cents']
    order=retail.cmd(client,order,'install',{'evidence_id':flow.evidence(client,order),'result':'实际安装剩余商品'})
    first=reconciled(client,'retail_installation',expected)
    assert first['tables']['retail_installation']['rows'][0]['quantity_milli']==1500
    order=retail.cmd(client,order,'accept',{'evidence_id':flow.evidence(client,order)})
    order,ret=retail.request_return(client,order,source,1000)
    order=retail.ret_cmd(client,order,ret,'return_approve');retail.ret_cmd(client,order,ret,'return_receive')
    later=reconciled(client,'retail_installation',expected)
    assert later['tables']['retail_installation']==first['tables']['retail_installation']
