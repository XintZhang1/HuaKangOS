"""Business-specific tools reuse actual scoped actions and preserve submitted units."""
import json
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from app.db import SessionLocal,today
from app.models import Store,User,UserStore
from app.flow_models import FlowEvent,Customer
from app import business_assistant_service as service
from app import business_assistant_gateway as gateway
from tests.conftest import login
from tests.test_business_assistant import session,message,confirm,BASE
from tests.test_employee_simplicity import lead
from tests.test_workflow import detail,action


@pytest.fixture
def assistant_config(monkeypatch):
    monkeypatch.setattr(service,'load_config',lambda:service.AssistantConfig(True,'synthetic-not-real','deepseek-flash',5,True))


def ask_tool(client,monkeypatch,sid,name,args):
    count=0;results=[]
    async def model(config,messages):
        nonlocal count
        count+=1
        if count==1:return {'content':'','tool_calls':[{'id':'business-tool','type':'function','function':{
            'name':name,'arguments':json.dumps(args)}}]}
        results.extend(json.loads(m['content']) for m in messages if m['role']=='tool')
        return {'content':'请核对当前办理内容。'}
    monkeypatch.setattr(service,'model_reply',model)
    result=message(client,sid);assert result.status_code==200,result.text
    return result.json(),results


def values(phone=True):
    data={'due_date':today().isoformat(),'result':'合成客户希望下次联系'}
    if phone:data['customer_phone']='13900008888'
    return data


def prepare(client,monkeypatch,sid,row,v=None):
    return ask_tool(client,monkeypatch,sid,'prepare_case_action',{'case_id':row['id'],'action':'remind','values':v if v is not None else values(),'summary':'安排接待回访'})


def test_get_case_returns_native_actions_and_missing_phone_prevents_any_draft(client,assistant_config,monkeypatch):
    row=lead(client);login(client,'sales');sid=session(client)
    _,read=ask_tool(client,monkeypatch,sid,'get_case',{'case_id':row['id']})
    assert read[0]['status']==200
    callback=next(a for a in read[0]['data']['actions'] if a['key']=='remind')
    assert next(f for f in callback['fields'] if f['key']=='customer_phone')['required']
    result,tools=prepare(client,monkeypatch,sid,row,values(False))
    assert result['proposals']==[] and tools[0]['status']==422 and '联系电话' in tools[0]['error']
    assert detail(client,row)['customer']['phone']==''


def test_prepare_callback_fetches_version_then_native_confirmation_fills_phone_once(client,assistant_config,monkeypatch):
    row=lead(client);login(client,'sales');sid=session(client)
    before=detail(client,row)
    result,_=prepare(client,monkeypatch,sid,row)
    draft=result['proposals'][0]
    assert draft['details']['body']['version']==before['version']
    assert draft['details']['body']['values']==values()
    assert detail(client,row)['customer']['phone']==''
    posted=confirm(client,sid,draft);assert posted.status_code==200,posted.text
    assert posted.json()['proposals'][0]['status']=='succeeded'
    assert confirm(client,sid,draft).status_code==200
    after=detail(client,row)
    assert after['customer']['phone']=='13900008888' and after['state']=='reminder'
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(FlowEvent).where(FlowEvent.case_id==row['id'],FlowEvent.action=='remind'))==1


def test_native_stale_version_rejects_case_draft_after_intervening_action(client,assistant_config,monkeypatch):
    row=lead(client);login(client,'sales');sid=session(client)
    result,_=prepare(client,monkeypatch,sid,row);draft=result['proposals'][0]
    action(client,row,'intent',{'need':'合成明确意向','due_date':today().isoformat()})
    response=confirm(client,sid,draft)
    assert response.json()['proposals'][0]['status']=='failed'
    assert response.json()['proposals'][0]['result']['status']==409
    assert detail(client,row)['customer']['phone']==''


@pytest.mark.parametrize('mode',['role','store'])
def test_case_tools_preserve_native_role_and_cross_store_refusal(client,assistant_config,monkeypatch,mode):
    row=lead(client)
    if mode=='role':login(client,'inventory')
    else:
        with SessionLocal() as db:
            db.add(Store(id=2,code='ASSISTANT-B',name='合成乙店'));db.flush()
            uid=db.scalar(select(User.id).where(User.username=='sales'))
            db.add(UserStore(user_id=uid,store_id=2));db.commit()
        login(client,'sales');client.headers['X-Store-ID']='2'
    sid=session(client)
    result,tools=prepare(client,monkeypatch,sid,row)
    assert result['proposals']==[] and tools[0]['status'] in {403,404}
    with SessionLocal() as db:assert db.scalar(select(Customer.phone).where(Customer.id==row['customer_id']))==''


def test_disabled_action_does_not_produce_a_draft(client,assistant_config,monkeypatch):
    row=lead(client);login(client,'sales');sid=session(client)
    with SessionLocal() as db:
        db.get(Customer,row['customer_id']).contact_allowed=False;db.commit()
    result,tools=prepare(client,monkeypatch,sid,row)
    assert result['proposals']==[] and tools[0]['status']==409


def test_case_tool_validates_units_without_converting_them_in_draft(client,assistant_config,monkeypatch):
    sid=session(client)
    async def current_case(*args,**kwargs):
        return {'status':200,'data':{'version':7,'actions':[{'key':'material','enabled':True,'fields':[
            {'key':'amount','label':'金额（元）','type':'money','required':True},
            {'key':'quantity','label':'数量','type':'quantity','required':True}]}]}}
    monkeypatch.setattr(gateway,'invoke',current_case)
    supplied={'amount':'12.34','quantity':'1.250'}
    result,_=ask_tool(client,monkeypatch,sid,'prepare_case_action',{
        'case_id':42,'action':'material','values':supplied,'summary':'合成金额与数量校验'})
    body=result['proposals'][0]['details']['body']
    assert body['version']==7 and body['values']==supplied


def test_case_tool_rejects_model_supplied_version_or_raw_url(client,assistant_config,monkeypatch):
    sid=session(client)
    result,tools=ask_tool(client,monkeypatch,sid,'prepare_case_action',{
        'case_id':1,'action':'remind','values':values(),'summary':'不应执行','version':999,
        'operation_id':'POST /api/flow/cases/1/actions/remind'})
    assert result['proposals']==[] and tools[0]['status']==422
