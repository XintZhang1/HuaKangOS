"""Conversation safety: no model execution, durable human confirmation, scoped replay."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import sys
from types import ModuleType
from uuid import uuid4
import pytest
import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.db import SessionLocal, utcnow
from app.models import Store, User
from app.main import app
from app.business_assistant_models import AssistantProposal, AssistantMessage, AssistantSession
from app import business_assistant_service as service
from tests.conftest import login

BASE='/api/business-assistant'


@pytest.fixture
def assistant(monkeypatch):
    config=service.AssistantConfig(True,'test-secret-not-real','deepseek-flash',5,True)
    monkeypatch.setattr(service,'load_config',lambda:config)
    fake=ModuleType('app.business_assistant_gateway')
    calls=[]
    def inspect(operation_id):
        if operation_id not in {'read_records','create_record','create_unkeyed'}:raise HTTPException(404,'没有找到这项操作')
        return {'id':operation_id,'label':'查询资料' if operation_id=='read_records' else '新增资料',
                'write':operation_id!='read_records','method':'GET' if operation_id=='read_records' else 'POST',
                'idempotent':operation_id=='create_record'}
    def validate(operation_id,path_args,query,body):
        operation=inspect(operation_id)
        if operation['write'] and not body.get('name'):raise HTTPException(422,'请填写名称')
        body=dict(body)
        if operation['idempotent']:body['request_id']=str(uuid4())
        return {'operation':operation,'path_args':path_args,'query':query,'body':body}
    async def invoke(request,user,operation_id,path_args=None,query=None,body=None):
        await asyncio.sleep(0.03)
        calls.append({'id':operation_id,'body':body})
        if user.role=='auditor' and operation_id!='read_records':return {'status':403,'data':{'detail':'当前岗位不能新增资料'}}
        return {'status':200 if operation_id=='read_records' else 201,'data':{'id':71,'name':(body or {}).get('name','合成资料')}}
    fake.inspect_operation=inspect;fake.validate_operation=validate;fake.invoke=invoke
    fake.catalog=lambda **kwargs:[inspect('read_records'),inspect('create_record'),inspect('create_unkeyed')]
    monkeypatch.setitem(sys.modules,'app.business_assistant_gateway',fake)
    import app
    monkeypatch.setattr(app,'business_assistant_gateway',fake,raising=False)
    async def answer(config,messages):return {'content':'请告诉我要新增的名称。'}
    monkeypatch.setattr(service,'model_reply',answer)
    return fake,calls


def session(client):
    r=client.post(BASE+'/sessions',json={});assert r.status_code==201,r.text
    return r.json()['id']


def message(client,sid,content='帮我新增资料',key=None):
    return client.post(f'{BASE}/sessions/{sid}/messages',json={'request_id':key or str(uuid4()),'content':content})


def make_proposal(client,monkeypatch,sid,operation='create_record',body=None):
    count=0
    async def model(config,messages):
        nonlocal count
        count+=1
        if count==1:return {'content':'','tool_calls':[{'id':'draft-1','type':'function','function':{
            'name':'prepare_operation','arguments':json.dumps({'operation_id':operation,'summary':'新增合成资料','body':body or {'name':'合成资料'}})}}]}
        return {'content':'已准备好，请核对后点击确认。'}
    monkeypatch.setattr(service,'model_reply',model)
    result=message(client,sid);assert result.status_code==200,result.text
    return result.json()['proposals'][-1]


def confirm(client,sid,proposal,action='confirm'):
    return client.post(f'{BASE}/sessions/{sid}/proposals/{proposal["id"]}/{action}',json={'digest':proposal['digest']})


def test_status_is_independent_and_test_config_isolated(client,monkeypatch,tmp_path):
    monkeypatch.delenv('BUSINESS_ASSISTANT_CONFIG',raising=False)
    monkeypatch.setenv('ALLOW_AI_EXTERNAL','true')
    assert client.get(BASE+'/status').json()['ready'] is False
    config=tmp_path/'private-assistant.json'
    config.write_text(json.dumps({'enabled':True,'api_key':'synthetic-test-key','model':'deepseek-flash','synthetic':False}))
    monkeypatch.setenv('BUSINESS_ASSISTANT_CONFIG',str(config))
    assert service.load_config().enabled is False
    config.write_text(json.dumps({'enabled':True,'api_key':'synthetic-test-key','model':'deepseek-flash','synthetic':True}))
    assert service.load_config().enabled is True
    status=client.get(BASE+'/status').json()
    assert status['ready'] and 'api_key' not in status and 'synthetic-test-key' not in json.dumps(status)


@pytest.mark.parametrize('provider,api_kind,host,token_field',[
    ('deepseek','pay_as_you_go','api.deepseek.com','max_tokens'),
    ('mimo','token_plan','token-plan-cn.xiaomimimo.com','max_completion_tokens'),
    ('mimo','pay_as_you_go','api.xiaomimimo.com','max_completion_tokens')])
def test_provider_adapter_uses_only_fixed_official_endpoint_and_compatible_tool_fields(monkeypatch,provider,api_kind,host,token_field):
    calls=[]
    def handler(request):
        body=json.loads(request.content);calls.append((request,body))
        assert request.url.host==host
        assert request.headers['Authorization']=='Bearer tp-fake-provider-key-000000000'
        assert body[token_field]==2500 and body['thinking']=={'type':'disabled'}
        assert body['temperature']==(0.3 if provider=='mimo' else 0.1)
        assert body['tool_choice']=='auto' and body['tools']
        assert ('max_tokens' in body) != ('max_completion_tokens' in body)
        return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':'请告诉我要办理什么。'}}]})
    real_client=httpx.AsyncClient
    monkeypatch.setattr(service.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    config=service.AssistantConfig(True,'tp-fake-provider-key-000000000','mimo-v2.6-flash' if provider=='mimo' else 'deepseek-flash',5,True,provider,api_kind)
    result=asyncio.run(service.model_reply(config,[{'role':'user','content':'你好'}]))
    assert result['content']=='请告诉我要办理什么。' and len(calls)==1


@pytest.mark.parametrize('status',[401,429,302])
def test_mimo_failure_never_falls_back_or_follows_redirects(monkeypatch,status):
    hosts=[]
    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(status,headers={'Location':'https://not-a-provider.invalid/leak'},json={'error':'tp-fake-provider-secret-000000000'})
    real_client=httpx.AsyncClient
    monkeypatch.setattr(service.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    config=service.AssistantConfig(True,'tp-fake-provider-secret-000000000','mimo-v2.6-flash',5,True,'mimo','token_plan')
    with pytest.raises(HTTPException) as error:asyncio.run(service.model_reply(config,[{'role':'user','content':'你好'}]))
    assert error.value.status_code==503 and 'tp-fake' not in str(error.value.detail)
    assert hosts==['token-plan-cn.xiaomimimo.com']


def test_private_provider_selection_rejects_arbitrary_endpoints(client,monkeypatch,tmp_path):
    config=tmp_path/'mimo-config.json'
    values={'enabled':True,'synthetic':True,'api_key':'tp-fake-config-key-000000000','provider':'mimo','api_kind':'token_plan'}
    config.write_text(json.dumps(values));monkeypatch.setenv('BUSINESS_ASSISTANT_CONFIG',str(config))
    loaded=service.load_config();assert loaded.provider=='mimo' and loaded.model=='mimo-v2.6-flash'
    status=client.get(BASE+'/status').json()
    assert status['provider']=='mimo' and status['model']=='mimo-v2.6-flash' and 'tp-fake' not in json.dumps(status)
    config.write_text(json.dumps({**values,'endpoint':'https://not-a-provider.invalid'}))
    assert client.get(BASE+'/status').json()['ready'] is False
    with pytest.raises(HTTPException):service.load_config()


def test_multiturn_questions_and_message_retry_are_idempotent(client,assistant,monkeypatch):
    sid=session(client);key=str(uuid4());seen=[]
    async def model(config,messages):
        seen.append(messages)
        return {'content':'请补充客户姓名和电话。' if len(seen)==1 else '已收到，可以继续选择车型。'}
    monkeypatch.setattr(service,'model_reply',model)
    first=message(client,sid,key=key);assert first.status_code==200
    retry=message(client,sid,key=key);assert retry.status_code==200
    assert len(seen)==1 and len(retry.json()['messages'])==2
    assert message(client,sid,'不同内容',key).status_code==409
    second=message(client,sid,'客户叫合成甲');assert second.status_code==200
    assert any(m['content']=='请补充客户姓名和电话。' for m in seen[-1])
    assert len(second.json()['messages'])==4


def test_inspected_static_operation_ids_survive_clarification_without_any_proposal(client,assistant,monkeypatch):
    sid=session(client);step=0;contexts=[]
    original=assistant[0].inspect_operation
    assistant[0].inspect_operation=lambda op:{**original('read_records'),'id':op,'body_schema':{'type':'object','title':'当前静态字段'}}
    async def model(config,messages):
        nonlocal step
        step+=1;contexts.append(messages[0]['content'])
        if step in {1,3,5,7}:
            return {'content':'','tool_calls':[{'id':f'check-{i}','type':'function','function':{
                'name':'inspect_operation','arguments':json.dumps({'operation_id':f'op-{i}'})}} for i in (step,step+1)]}
        return {'content':'请补充当前资料。'}
    monkeypatch.setattr(service,'model_reply',model)
    for _ in range(4):assert message(client,sid).status_code==200
    with SessionLocal() as db:
        memory=db.get(AssistantSession,sid).recent_operation_ids
        assert memory==['op-3','op-4','op-5','op-6','op-7','op-8']
        assert all(isinstance(item,str) for item in memory)
    result=client.get(f'{BASE}/sessions/{sid}').json()
    assert result['proposals']==[] and 'recent_operation_ids' not in result
    assert 'op-1' in contexts[2] and '当前静态字段' in contexts[2]


def test_oversized_tool_batch_runs_only_first_two_and_returns_explicit_skips(client,assistant,monkeypatch):
    sid=session(client);step=0;second_messages=[]
    async def model(config,messages):
        nonlocal step
        step+=1
        if step==1:
            calls=[]
            for i in range(9):
                args={'operation_id':'read_records'} if i<2 else {'operation_id':'create_record','summary':'不得准备','body':{'name':'未执行'}}
                calls.append({'id':f'tool-{i}','type':'function','function':{'name':'read_data' if i<2 else 'prepare_operation','arguments':json.dumps(args)}})
            return {'content':'','tool_calls':calls}
        second_messages.extend(messages);return {'content':'已查到当前资料，请补充名称。'}
    monkeypatch.setattr(service,'model_reply',model)
    result=message(client,sid);assert result.status_code==200
    assert len(assistant[1])==2 and all(call['id']=='read_records' for call in assistant[1])
    assert result.json()['proposals']==[]
    returned=[m for m in second_messages if m['role']=='tool']
    assert len(returned)==9
    assert all(json.loads(m['content']).get('executed') is False for m in returned[2:])


def test_second_oversized_batch_stops_without_processing_any_more_tools(client,assistant,monkeypatch):
    sid=session(client);step=0
    async def model(config,messages):
        nonlocal step
        step+=1
        return {'content':'','tool_calls':[{'id':f'{step}-{i}','type':'function','function':{'name':'read_data','arguments':'{"operation_id":"read_records"}'}} for i in range(9)]}
    monkeypatch.setattr(service,'model_reply',model)
    result=message(client,sid);assert result.status_code==200
    assert len(assistant[1])==2 and step==2 and result.json()['proposals']==[]
    assert '还没准备好' in result.json()['messages'][-1]['content']
    assert client.get(BASE+'/issues').json()['items'][0]['category']=='model'


@pytest.mark.parametrize('malformed',[True,False])
def test_invalid_or_more_than_thirty_tools_fail_closed_without_processing(client,assistant,monkeypatch,malformed):
    sid=session(client)
    async def model(config,messages):
        return {'content':'','tool_calls':{} if malformed else [{'id':str(i),'type':'function','function':{
            'name':'prepare_operation','arguments':'{"operation_id":"create_record","summary":"不得生成","body":{"name":"不应创建"}}'}} for i in range(31)]}
    monkeypatch.setattr(service,'model_reply',model)
    result=message(client,sid);assert result.status_code==200
    assert result.json()['proposals']==[] and assistant[1]==[]
    assert client.get(BASE+'/issues').json()['items'][0]['category']=='model'


@pytest.mark.parametrize('has_pending',[False,True])
def test_round_budget_reports_truthful_progress_and_model_issue(client,assistant,monkeypatch,has_pending):
    sid=session(client)
    if has_pending:make_proposal(client,monkeypatch,sid)
    count=0
    async def model(config,messages):
        nonlocal count
        count+=1
        return {'content':'','tool_calls':[{'id':f'check-{count}','type':'function','function':{'name':'inspect_operation','arguments':'{"operation_id":"read_records"}'}}]}
    monkeypatch.setattr(service,'model_reply',model)
    result=message(client,sid);assert result.status_code==200 and count==10
    text=result.json()['messages'][-1]['content']
    assert ('下方待确认操作' in text) if has_pending else ('还没准备好' in text)
    assert client.get(BASE+'/issues').json()['items'][0]['category']=='model'


@pytest.mark.parametrize('operation',['create_record','create_unkeyed'])
def test_prepare_never_executes_and_duplicate_confirmation_posts_once(client,assistant,monkeypatch,operation):
    fake,calls=assistant;sid=session(client)
    draft=make_proposal(client,monkeypatch,sid,operation)
    assert calls==[] and draft['status']=='pending'
    first=confirm(client,sid,draft);assert first.status_code==200,first.text
    assert first.json()['proposals'][0]['status']=='succeeded'
    again=confirm(client,sid,draft);assert again.status_code==200
    assert len(calls)==1
    if operation=='create_record':assert calls[0]['body']['request_id']==draft['details']['body']['request_id']


def test_concurrent_confirmation_claims_only_once(client,assistant,monkeypatch):
    sid=session(client);draft=make_proposal(client,monkeypatch,sid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:confirm(client,sid,draft),range(2)))
    assert all(r.status_code in {200,409} for r in results)
    assert len(assistant[1])==1
    assert client.get(f'{BASE}/sessions/{sid}').json()['proposals'][0]['status']=='succeeded'


def test_repeated_model_preparation_reuses_same_pending_card(client,assistant,monkeypatch):
    sid=session(client)
    one=make_proposal(client,monkeypatch,sid)
    two=make_proposal(client,monkeypatch,sid)
    assert one['id']==two['id'] and one['digest']==two['digest']
    assert len(client.get(f'{BASE}/sessions/{sid}').json()['proposals'])==1


@pytest.mark.parametrize('status',['executing','uncertain'])
@pytest.mark.parametrize('operation',['create_record','create_unkeyed'])
def test_unresolved_same_intent_cannot_get_a_new_proposal_or_request_key(client,assistant,monkeypatch,status,operation):
    sid=session(client);one=make_proposal(client,monkeypatch,sid,operation)
    with SessionLocal() as db:
        row=db.get(AssistantProposal,one['id']);row.status=status;row.started_at=utcnow();db.commit()
    repeated=make_proposal(client,monkeypatch,sid,operation)
    assert repeated['id']==one['id'] and repeated['digest']==one['digest']
    assert repeated['status']==status
    assert len(client.get(f'{BASE}/sessions/{sid}').json()['proposals'])==1
    assert assistant[1]==[]
    assert any('不能重复提交' in item['summary'] for item in client.get(BASE+'/issues').json()['items'])


def test_cancel_competing_with_confirm_has_one_final_outcome(client,assistant,monkeypatch):
    sid=session(client);draft=make_proposal(client,monkeypatch,sid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda action:confirm(client,sid,draft,action),['confirm','cancel']))
    assert all(r.status_code in {200,409} for r in results)
    final=client.get(f'{BASE}/sessions/{sid}').json()['proposals'][0]['status']
    assert final in {'succeeded','cancelled'}
    assert len(assistant[1])==(1 if final=='succeeded' else 0)


def test_cancel_and_expiry_do_not_execute(client,assistant,monkeypatch):
    sid=session(client);draft=make_proposal(client,monkeypatch,sid)
    assert confirm(client,sid,draft,'cancel').json()['proposals'][0]['status']=='cancelled'
    assert confirm(client,sid,draft).status_code==200
    expired=make_proposal(client,monkeypatch,sid)
    with SessionLocal() as db:
        db.get(AssistantProposal,expired['id']).expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert confirm(client,sid,expired).status_code==409
    assert assistant[1]==[]


def test_digest_and_current_access_version_rechecked(client,assistant,monkeypatch):
    sid=session(client);draft=make_proposal(client,monkeypatch,sid)
    wrong={**draft,'digest':'0'*64};assert confirm(client,sid,wrong).status_code==409
    with SessionLocal() as db:
        db.scalar(select(User).where(User.username=='admin')).access_version+=1;db.commit()
    assert confirm(client,sid,draft).status_code==404
    assert assistant[1]==[]


def test_proposal_tamper_is_rejected(client,assistant,monkeypatch):
    sid=session(client);draft=make_proposal(client,monkeypatch,sid)
    with SessionLocal() as db:
        row=db.get(AssistantProposal,draft['id']);row.payload={**row.payload,'body':{'name':'changed'}};db.commit()
    assert confirm(client,sid,draft).status_code==409
    assert assistant[1]==[]


def test_other_owner_and_other_store_cannot_read_confirm_or_export(client,assistant,monkeypatch):
    sid=session(client);draft=make_proposal(client,monkeypatch,sid)
    client.post(f'{BASE}/sessions/{sid}/issues',json={'category':'input','summary':'缺少车型'})
    login(client,'sales')
    assert client.get(f'{BASE}/sessions/{sid}').status_code==404
    assert confirm(client,sid,draft).status_code==404
    assert client.get(BASE+'/issues').json()['items']==[]
    login(client)
    with SessionLocal() as db:db.add(Store(id=2,code='SECOND',name='合成乙店'));db.commit()
    client.headers['X-Store-ID']='2'
    assert client.get(f'{BASE}/sessions/{sid}').status_code==404
    assert message(client,sid).status_code==404
    assert confirm(client,sid,draft).status_code==404
    assert client.get(BASE+'/issues/export').json()['items']==[]
    client.headers['X-Store-ID']='all'
    assert client.get(BASE+'/sessions').status_code==409


@pytest.mark.parametrize('change',['account_role','store_role'])
def test_real_demotion_and_relogin_hide_old_financial_conversation_everywhere(client,assistant,monkeypatch,change):
    from tests.test_user_access import listed,body,put
    row=listed(client,'finance')
    with TestClient(app) as staff:
        login(staff,'finance');sid=session(staff)
        draft=make_proposal(staff,monkeypatch,sid,body={'name':'合成财务资料','amount_cents':987650})
        assert staff.post(f'{BASE}/sessions/{sid}/issues',json={'category':'rule','summary':'原财务问题987650'}).status_code==201
        values={'role':'sales','store_roles':[{'store_id':1,'role':'sales'}]} if change=='account_role' else {'store_roles':[{'store_id':1,'role':'sales'}]}
        updated=put(client,row,body(row,**values));assert updated.status_code==200,updated.text
        assert staff.get(BASE+'/sessions').status_code==401
        login(staff,'finance')
        assert staff.get('/api/auth/me').json()['role']=='sales'
        assert staff.get(BASE+'/sessions').json()['items']==[]
        assert staff.get(f'{BASE}/sessions/{sid}').status_code==404
        assert message(staff,sid,'继续办理').status_code==404
        assert confirm(staff,sid,draft).status_code==404
        assert confirm(staff,sid,draft,'cancel').status_code==404
        assert staff.post(f'{BASE}/sessions/{sid}/issues',json={'category':'input','summary':'继续旧问题'}).status_code==404
        assert staff.get(BASE+'/issues').json()['items']==[]
        assert staff.get(BASE+'/issues/export').json()['items']==[]
        # New-role conversations remain usable; existing history is retained.
        assert session(staff)!=sid
    with SessionLocal() as db:
        assert db.get(AssistantProposal,draft['id']) is not None
        assert db.scalar(select(AssistantMessage).where(AssistantMessage.session_id==sid)) is not None


def test_native_permission_refusal_is_not_success(client,assistant,monkeypatch):
    login(client,'auditor');sid=session(client);draft=make_proposal(client,monkeypatch,sid)
    result=confirm(client,sid,draft)
    assert result.status_code==200 and result.json()['proposals'][0]['status']=='failed'
    assert result.json()['proposals'][0]['result']['status']==403
    assert client.get(BASE+'/issues').json()['items'][0]['category']=='rule'


def test_unknown_execution_result_never_replays_non_idempotent_operation(client,assistant,monkeypatch):
    sid=session(client);draft=make_proposal(client,monkeypatch,sid,'create_unkeyed');attempts=[]
    async def broken(*args,**kwargs):attempts.append(1);raise RuntimeError('internal URL / secret not for user')
    monkeypatch.setattr(assistant[0],'invoke',broken)
    result=confirm(client,sid,draft);assert result.json()['proposals'][0]['status']=='uncertain'
    assert 'secret' not in result.text
    assert confirm(client,sid,draft).status_code==200 and attempts==[1]
    assert client.get(BASE+'/issues').json()['items'][0]['category']=='system'


def test_model_cannot_execute_write_through_read_tool(client,assistant,monkeypatch):
    sid=session(client);count=0
    async def model(config,messages):
        nonlocal count
        count+=1
        if count==1:return {'content':'','tool_calls':[{'id':'bad-1','type':'function','function':{'name':'read_data','arguments':'{"operation_id":"create_record","body":{"name":"bad"}}'}}]}
        return {'content':'这项操作需要先核对。'}
    monkeypatch.setattr(service,'model_reply',model)
    result=message(client,sid);assert result.status_code==200
    assert assistant[1]==[] and result.json()['proposals']==[]
    assert client.get(BASE+'/issues').json()['items'][0]['category']=='rule'


def test_connection_failure_is_chinese_and_issue_is_recorded(client,assistant,monkeypatch):
    sid=session(client)
    async def unavailable(*args):raise HTTPException(503,'业务助手暂时无法连接，请稍后再试')
    monkeypatch.setattr(service,'model_reply',unavailable)
    result=message(client,sid);assert result.status_code==200
    assert result.json()['busy'] is False
    assert result.json()['messages'][-1]['content']=='业务助手暂时无法连接，请稍后再试'
    assert client.get(BASE+'/issues').json()['items'][0]['status_code']==503


def test_access_change_during_turn_stops_before_second_external_context(client,assistant,monkeypatch):
    sid=session(client);remote_calls=[]
    async def model(config,messages):
        remote_calls.append(1)
        with SessionLocal() as db:
            db.scalar(select(User).where(User.username=='admin')).access_version+=1;db.commit()
        return {'content':'','tool_calls':[{'id':'lookup','type':'function','function':{'name':'list_operations','arguments':'{}'}}]}
    monkeypatch.setattr(service,'model_reply',model)
    response=message(client,sid)
    assert response.status_code==404 and remote_calls==[1]
    assert client.get(BASE+'/sessions').json()['items']==[]


def test_credentials_and_phone_not_copied_to_problem_export(client,assistant):
    sid=session(client)
    result=client.post(f'{BASE}/sessions/{sid}/issues',json={'category':'input','summary':'sk-thisisnotarealkey000000000 tp-fake-mimo-test-key-000000000 电话13800138000 缺少车型'})
    assert result.status_code==201
    exported=client.get(BASE+'/issues/export')
    assert 'sk-thisisnotarealkey' not in exported.text and '13800138000' not in exported.text
    assert 'tp-fake-mimo-test-key' not in exported.text
    assert exported.json()['items'][0]['synthetic'] is True


def test_confirmation_shows_every_line_and_exact_money_quantity():
    rows=service.display_fields({'body':{'lines':[{'amount_cents':12345,'qty_milli':1250,'name':'x'*200} for _ in range(20)]}})
    assert len(rows)==60
    assert rows[0]['value']=='123.45' and rows[1]['value']=='1.25'
    assert len(rows[-1]['value'])==200


def test_real_native_customer_creation_through_confirm_preserves_permission_and_single_effect(client,monkeypatch):
    from app.flow_models import Customer
    from sqlalchemy import func
    from app import business_assistant_gateway
    monkeypatch.setattr(service,'load_config',lambda:service.AssistantConfig(True,'test-only','deepseek-flash',5,True))
    step=0
    async def model(config,messages):
        nonlocal step
        step+=1
        if step==1:return {'content':'','tool_calls':[{'id':'native-draft','type':'function','function':{
            'name':'prepare_operation','arguments':json.dumps({'operation_id':'POST /api/flow/master/{kind}',
                'path_args':{'kind':'customers'},'summary':'新增合成客户','body':{'values':{'name':'助手合成客户','phone':'13900008881'}}})}}]}
        return {'content':'请核对客户资料，再点击确认。'}
    monkeypatch.setattr(service,'model_reply',model)
    login(client,'sales');sid=session(client)
    prepared=message(client,sid).json();assert len(prepared['proposals'])==1,prepared
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Customer))==0
    draft=prepared['proposals'][0]
    posted=confirm(client,sid,draft);assert posted.status_code==200,posted.text
    assert posted.json()['proposals'][0]['status']=='succeeded',posted.text
    assert confirm(client,sid,draft).status_code==200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Customer))==1
        row=db.scalar(select(Customer));assert row.name=='助手合成客户' and row.store_id==1
        assert row.owner_id==db.scalar(select(User.id).where(User.username=='sales'))
