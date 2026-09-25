"""Conversation safety: no model execution, durable human confirmation, scoped replay."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
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
        # 2026-09-25 整表实测：一轮要准备十几张卡时 2500 token 会把回复截断成 finish_reason=length，
        # 被误报成"连接异常"。工具调用很占 token，这里按官方上限给足。
        assert body[token_field]==8192 and body['thinking']=={'type':'disabled'}
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


def test_a_transient_network_error_is_retried_once(monkeypatch):
    """2026-09-25 预览实测遇到连接重置：模型调用是只读的，可以重试一次。"""
    calls=[]
    def handler(request):
        calls.append(request.url.host)
        if len(calls)==1:
            raise httpx.ConnectError('connection reset',request=request)
        return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':'好的。'},'finish_reason':'stop'}]})
    real_client=httpx.AsyncClient
    real_sleep=asyncio.sleep
    monkeypatch.setattr(service.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    monkeypatch.setattr(service.asyncio,'sleep',lambda seconds:real_sleep(0))
    config=service.AssistantConfig(True,'tp-fake-provider-key-000000000','deepseek-flash',5,True)
    result=asyncio.run(service.model_reply(config,[{'role':'user','content':'你好'}]))
    assert result['content']=='好的。' and len(calls)==2
    assert set(calls)=={'api.deepseek.com'}


def test_a_malformed_reply_is_not_retried(monkeypatch):
    """回复格式不对是确定性问题：重试不会变好，只会重复消耗额度。"""
    calls=[]
    def handler(request):
        calls.append(1)
        return httpx.Response(200,json={'unexpected':True})
    real_client=httpx.AsyncClient
    monkeypatch.setattr(service.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    config=service.AssistantConfig(True,'tp-fake-provider-key-000000000','deepseek-flash',5,True)
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.model_reply(config,[{'role':'user','content':'你好'}]))
    assert error.value.status_code==503 and len(calls)==1


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


def test_oversized_tool_batch_runs_only_the_reviewed_number_and_returns_explicit_skips(client,assistant,monkeypatch):
    sid=session(client);step=0;second_messages=[]
    executed=service.PER_ROUND_TOOLS
    offered=executed+3
    async def model(config,messages):
        nonlocal step
        step+=1
        if step==1:
            calls=[]
            for i in range(offered):
                args={'operation_id':'read_records'} if i<executed else {'operation_id':'create_record','summary':'不得准备','body':{'name':'未执行'}}
                calls.append({'id':f'tool-{i}','type':'function','function':{'name':'read_data' if i<executed else 'prepare_operation','arguments':json.dumps(args)}})
            return {'content':'','tool_calls':calls}
        second_messages.extend(messages);return {'content':'已查到当前资料，请补充名称。'}
    monkeypatch.setattr(service,'model_reply',model)
    result=message(client,sid);assert result.status_code==200
    assert len(assistant[1])==executed and all(call['id']=='read_records' for call in assistant[1])
    assert result.json()['proposals']==[]
    returned=[m for m in second_messages if m['role']=='tool']
    assert len(returned)==offered
    assert all(json.loads(m['content']).get('executed') is False for m in returned[executed:])


def test_a_large_tool_batch_keeps_going_instead_of_stopping_the_turn(client,assistant,monkeypatch):
    """2026-09-25 业主裁定：整表导入时一轮提几十个准备调用是期望行为，不能因此掐断对话。

    每轮只真正执行 PER_ROUND_TOOLS 个，其余的按"未执行"回给模型让它下一轮继续。
    """
    sid=session(client);step=0
    offered=service.PER_ROUND_TOOLS*2+1
    async def model(config,messages):
        nonlocal step
        step+=1
        return {'content':'','tool_calls':[{'id':f'{step}-{i}','type':'function','function':{'name':'read_data','arguments':'{"operation_id":"read_records"}'}} for i in range(offered)]}
    monkeypatch.setattr(service,'model_reply',model)
    result=message(client,sid);assert result.status_code==200
    assert step==service.AssistantConfig().max_rounds,'a big batch must not end the turn on the second round'
    assert len(assistant[1])==service.AssistantConfig().max_rounds*service.PER_ROUND_TOOLS
    assert '还没准备好' in result.json()['messages'][-1]['content']
    assert client.get(BASE+'/issues').json()['items'][0]['category']=='model'


@pytest.mark.parametrize('malformed',[True,False])
def test_invalid_or_absurd_tool_lists_fail_closed_without_processing(client,assistant,monkeypatch,malformed):
    sid=session(client)
    count=service.HARD_TOOLS+1
    async def model(config,messages):
        return {'content':'','tool_calls':{} if malformed else [{'id':str(i),'type':'function','function':{
            'name':'prepare_operation','arguments':'{"operation_id":"create_record","summary":"不得生成","body":{"name":"不应创建"}}'}} for i in range(count)]}
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
    result=message(client,sid);assert result.status_code==200 and count==service.AssistantConfig().max_rounds
    text=result.json()['messages'][-1]['content']
    assert ('待确认卡片' in text and '全部确认' in text) if has_pending else ('还没准备好' in text)
    assert client.get(BASE+'/issues').json()['items'][0]['category']=='model'


def test_a_claim_without_a_tool_call_is_sent_back_once(client,assistant,monkeypatch):
    """2026-09-25 试用实测：长会话里模型照抄自己上一轮的话，声称"卡已准备好"却没调用工具。

    数据库里 0 张卡时必须退回一轮要求它真的准备，而不是把这句假话交给员工。
    """
    sid=session(client);rounds=[]
    async def model(config,messages):
        rounds.append([m.get('content') for m in messages if m.get('role')=='system'])
        if len(rounds)==1:
            return {'content':'第 7 批 4 张待确认卡已真实生成，请逐张核对后点击确认。'}
        return {'content':'这几行缺少电池容量，系统不会建卡；请补齐后再发我。'}
    monkeypatch.setattr(service,'model_reply',model)
    result=message(client,sid);assert result.status_code==200
    assert len(rounds)==2,'claiming a card without preparing one must be sent back once'
    assert any('没有生成任何待确认卡' in text for text in rounds[1] if text),rounds[1]
    assert '缺少电池容量' in result.json()['messages'][-1]['content']
    assert result.json()['proposals']==[]


def test_the_card_count_told_to_the_model_comes_from_the_database(client,assistant,monkeypatch):
    """2026-09-25 整表实测：模型准备的卡是对的（50 张），但收尾汇总自己数成"共 44 张"、"23 行缺字段"。

    卡数只有系统知道，所以每轮把数据库里的权威数字作为一条系统消息给它，禁止它口算——
    被系统拒绝、没成卡的那一行也不能算进去。
    """
    sid=session(client);rounds=[]
    def prepare(key):
        return {'id':'p-'+key,'type':'function','function':{'name':'prepare_operation','arguments':json.dumps(
            {'operation_id':'create_record','summary':'新增'+key,'body':{'name':key}})}}
    async def model(config,messages):
        rounds.append(messages)
        if len(rounds)==1:
            return {'content':'','tool_calls':[prepare('甲'),prepare('乙'),
                    {'id':'p-bad','type':'function','function':{'name':'prepare_operation',
                     'arguments':json.dumps({'operation_id':'no_such_operation','summary':'这一条不成卡'})}}]}
        return {'content':'已按系统给的数字汇报：待确认卡已准备好，请逐张核对。'}
    monkeypatch.setattr(service,'model_reply',model)
    result=message(client,sid);assert result.status_code==200
    assert len(rounds)==2
    tally=[m['content'] for m in rounds[1] if m.get('role')=='system' and '实际生成' in str(m.get('content'))]
    assert tally and '实际生成 2 张待确认卡' in tally[-1],rounds[1]
    assert len(result.json()['proposals'])==2


def test_prerequisite_facts_reach_both_the_model_and_the_card(client,assistant,monkeypatch):
    """2026-09-25 Codex 复核 P1：第二条限制要真的生效——前序事实必须回到模型手里，也要随卡给员工看。

    原实现只在 validate_operation 里算出来，prepare_proposal 既没返回给模型也没写进卡，
    于是"逐项确认前序"只写在提示词里。
    """
    fake,_=assistant
    base=fake.validate_operation
    notes=['相关业务：客户到店接待','客户：李试用','车辆：待确认']
    def validate(operation_id,path_args,query,body):
        return {**base(operation_id,path_args,query,body),'prerequisites':list(notes)}
    monkeypatch.setattr(fake,'validate_operation',validate)
    sid=session(client);rounds=[]
    async def model(config,messages):
        rounds.append(messages)
        if len(rounds)==1:
            return {'content':'','tool_calls':[{'id':'p1','type':'function','function':{
                'name':'prepare_operation','arguments':json.dumps(
                    {'operation_id':'create_record','summary':'新增合成资料','body':{'name':'合成资料'}})}}]}
        return {'content':'办理前请先确认这些前序事实。'}
    monkeypatch.setattr(service,'model_reply',model)
    result=message(client,sid);assert result.status_code==200
    tool=[m for m in rounds[1] if m.get('role')=='tool'][-1]
    returned=json.loads(tool['content'])
    assert returned['prerequisites']==notes,returned
    assert '逐项' in returned['prerequisite_rule']
    card=[p for p in result.json()['proposals'] if p['status']=='pending'][-1]
    assert card['result']['prerequisites']==notes,card


def test_every_pending_card_stays_visible_past_the_old_eighty_card_window(client,assistant):
    """2026-09-25 Codex 复核 P1：待确认卡上限放到 200，但会话只回最近 80 条时，81 张以后就确认不了。"""
    sid=session(client)
    with SessionLocal() as db:
        thread=db.scalar(select(AssistantSession).where(AssistantSession.id==sid))
        for index in range(95):
            db.add(AssistantProposal(id=str(uuid4()),store_id=thread.store_id,session_id=sid,owner_id=thread.owner_id,
                owner_role=thread.owner_role,access_version=thread.access_version,operation_id='create_record',
                label='新增资料',summary='第 %d 张' % index,payload={'body':{'name':'资料%d' % index}},
                digest=uuid4().hex*2,expires_at=utcnow()+timedelta(minutes=30)))
        db.commit()
    view=client.get(f'{BASE}/sessions/{sid}').json()
    pending=[p for p in view['proposals'] if p['status']=='pending']
    assert len(pending)==95
    assert pending[0]['summary']=='第 0 张','the oldest pending card must not fall out of the window'


def test_a_refused_write_keeps_the_escalation_offer_on_the_card(client,assistant,monkeypatch):
    """2026-09-25 Codex 复核 P1：写操作被 403 挡下时，评审提示原来在确认结果里被丢掉了。"""
    fake,_=assistant;sid=session(client)
    hint='这一步需要更高的岗位权限。可以读 GET /api/escalations/refusals 找到这条被挡记录，再用 prepare_operation 生成评审申请确认卡。'
    async def invoke(request,user,operation_id,path_args=None,query=None,body=None):
        return {'status':403,'data':{'detail':'当前岗位不能新增资料'},'route':'masters','hint':hint}
    monkeypatch.setattr(fake,'invoke',invoke)
    draft=make_proposal(client,monkeypatch,sid)
    response=confirm(client,sid,draft);assert response.status_code==200,response.text
    card=next(p for p in response.json()['proposals'] if p['id']==draft['id'])
    assert card['status']=='failed'
    assert card['result']['hint']==hint
    assert '更高的岗位权限' in card['result']['message'] and '评审申请卡' in card['result']['message']


def test_the_session_lease_covers_the_longest_allowed_turn(client,assistant,monkeypatch):
    """2026-09-25 Codex 复核 P2：单轮上限 600 秒，租约却写死 4 分钟，长任务会被当成已中断。"""
    config=service.AssistantConfig(True,'test-secret-not-real','deepseek-flash',5,True)
    monkeypatch.setattr(service,'load_config',lambda:config)
    assert service.busy_lease_seconds(config)>=config.turn_timeout_seconds+30
    short=replace(config,turn_timeout_seconds=30)
    assert service.busy_lease_seconds(short)==90
    sid=session(client);left=[]
    async def model(inner,messages):
        with SessionLocal() as db:
            thread=db.scalar(select(AssistantSession).where(AssistantSession.id==sid))
            left.append((thread.busy_until-utcnow()).total_seconds())
        return {'content':'好'}
    monkeypatch.setattr(service,'model_reply',model)
    assert message(client,sid).status_code==200
    assert left and left[0]>=config.turn_timeout_seconds,left


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


def prepare_call(key):
    return {'id':'p-'+key,'type':'function','function':{'name':'prepare_operation','arguments':json.dumps(
        {'operation_id':'create_record','summary':'新增'+key,'body':{'name':key}})}}


def prepare_turn(monkeypatch,keys):
    """每轮准备一组卡：keys 既可以是这一轮的键列表，也可以是"每一轮一个列表"。"""
    turns=[keys] if keys and isinstance(keys[0],str) else [list(turn) for turn in keys]
    rounds=[]
    async def model(config,messages):
        rounds.append(messages)
        index=(len(rounds)-1)//2
        if (len(rounds)-1)%2==0:
            return {'content':'','tool_calls':[prepare_call(key) for key in turns[min(index,len(turns)-1)]]}
        return {'content':'已准备好，请核对后点击确认。'}
    monkeypatch.setattr(service,'model_reply',model)


def test_cards_prepared_in_one_turn_carry_that_turn_so_the_page_can_fold_them(client,assistant,monkeypatch):
    """业主 2026-09-25：一轮生成的卡片要能折叠成一组翻页，分组靠服务端给出的事实，不靠前端猜时间。"""
    prepare_turn(monkeypatch,[['甲','乙'],['丙','丁']])
    sid=session(client)
    first=message(client,sid,key='turn-one-0000000001');assert first.status_code==200,first.text
    cards=[card for card in first.json()['proposals'] if card['status']=='pending']
    assert len(cards)==2 and {card['turn'] for card in cards}=={'turn-one-0000000001'},cards
    second=message(client,sid,key='turn-two-0000000002');assert second.status_code==200,second.text
    turns={card['turn'] for card in second.json()['proposals']}
    assert turns=={'turn-one-0000000001','turn-two-0000000002'},turns
    assert [card['summary'] for card in second.json()['proposals'] if card['turn']=='turn-two-0000000002']==['新增丙','新增丁']


def test_batch_confirm_still_runs_every_card_through_its_own_native_call(client,assistant,monkeypatch):
    """业主 2026-09-25：一次点击办一整组——但每张仍是它自己的校验、自己的原接口调用。"""
    fake,calls=assistant;prepare_turn(monkeypatch,['甲','乙','丙'])
    sid=session(client)
    prepared=message(client,sid);assert prepared.status_code==200
    pending=[card for card in prepared.json()['proposals'] if card['status']=='pending']
    assert len(pending)==3
    posted=client.post(f'{BASE}/sessions/{sid}/proposals/batch',
                       json={'action':'confirm','items':[{'id':card['id'],'digest':card['digest']} for card in pending]})
    assert posted.status_code==200,posted.text
    body=posted.json()
    assert body['batch']['total']==3 and body['batch']['done']==3,body['batch']
    assert len(calls)==3,'one click must still be three separate native calls'
    assert {row['status'] for row in body['proposals']}=={'succeeded'}


def test_batch_confirm_reports_one_bad_card_without_blocking_the_rest(client,assistant,monkeypatch):
    fake,calls=assistant;prepare_turn(monkeypatch,['甲','乙','丙'])
    sid=session(client)
    pending=[card for card in message(client,sid).json()['proposals'] if card['status']=='pending']
    items=[{'id':card['id'],'digest':card['digest']} for card in pending]
    items[1]={'id':pending[1]['id'],'digest':'0'*64}
    posted=client.post(f'{BASE}/sessions/{sid}/proposals/batch',json={'action':'confirm','items':items})
    assert posted.status_code==200,posted.text
    outcomes={row['id']:row['status'] for row in posted.json()['batch']['items']}
    assert outcomes[pending[1]['id']]=='refused' and '变化' in posted.json()['batch']['items'][1]['message']
    assert [outcomes[card['id']] for card in (pending[0],pending[2])]==['succeeded','succeeded']
    assert len(calls)==2,'the refused card must not reach the native API'


def test_batch_confirm_refuses_absurd_or_repeated_selections(client,assistant,monkeypatch):
    prepare_turn(monkeypatch,['甲'])
    sid=session(client)
    card=[row for row in message(client,sid).json()['proposals'] if row['status']=='pending'][0]
    one={'id':card['id'],'digest':card['digest']}
    assert client.post(f'{BASE}/sessions/{sid}/proposals/batch',json={'action':'confirm','items':[]}).status_code==422
    assert client.post(f'{BASE}/sessions/{sid}/proposals/batch',
                       json={'action':'confirm','items':[one]*2}).status_code==422
    assert client.post(f'{BASE}/sessions/{sid}/proposals/batch',
                       json={'action':'confirm','items':[one]*(service.BATCH_LIMIT+1)}).status_code==422
    assert client.post(f'{BASE}/sessions/{sid}/proposals/batch',
                       json={'action':'confirm','items':[{'id':card['id'],'digest':'not-a-digest'}]}).status_code==422
    assert client.post(f'{BASE}/sessions/{sid}/proposals/batch',
                       json={'action':'confirm','items':[one],'extra':1}).status_code==422
    with SessionLocal() as db:assert db.scalar(select(AssistantProposal).where(AssistantProposal.id==card['id'])).status=='pending'


def test_batch_cancel_needs_no_native_call_and_leaves_other_cards_pending(client,assistant,monkeypatch):
    fake,calls=assistant;prepare_turn(monkeypatch,['甲','乙'])
    sid=session(client)
    pending=[card for card in message(client,sid).json()['proposals'] if card['status']=='pending']
    posted=client.post(f'{BASE}/sessions/{sid}/proposals/batch',
                       json={'action':'cancel','items':[{'id':pending[0]['id'],'digest':pending[0]['digest']}]})
    assert posted.status_code==200,posted.text
    statuses={row['id']:row['status'] for row in posted.json()['proposals']}
    assert statuses[pending[0]['id']]=='cancelled' and statuses[pending[1]['id']]=='pending'
    assert calls==[],'cancelling a card never calls the business API'


def test_a_prerequisite_chain_prepared_in_one_turn_carries_its_step_order(client,assistant,monkeypatch):
    """业主 2026-09-25：员工说一个中间/最后一步时，整条前序链要在同一轮里按步骤准备好。

    步骤顺序必须由服务端存下来，页面才能按"第 1 步 / 第 2 步…"分组展示。
    """
    sid=session(client);rounds=[]
    def prepare(key,step,order=None):
        args={'operation_id':'create_record','summary':'新增'+key,'body':{'name':key},'step':step}
        if order is not None:args['step_order']=order
        return {'id':'p-'+key,'type':'function','function':{'name':'prepare_operation','arguments':json.dumps(args)}}
    async def model(config,messages):
        rounds.append(messages)
        if len(rounds)==1:
            return {'content':'','tool_calls':[prepare('接待','1 售前接待'),prepare('回访','2、分派接待回访'),
                                               prepare('订单','新建订单',3),prepare('明细','新建订单')]}
        return {'content':'一共 3 步，请分组核对。'}
    monkeypatch.setattr(service,'model_reply',model)
    result=message(client,sid);assert result.status_code==200,result.text
    cards=result.json()['proposals']
    assert [(card['step_order'],card['step']) for card in cards]==[
        (1,'售前接待'),(2,'分派接待回访'),(3,'新建订单'),(0,'新建订单')],cards
    schema=[tool for tool in service.TOOLS if tool['function']['name']=='prepare_operation'][0]['function']['parameters']['properties']
    assert 'step' in schema and 'step_order' in schema,'提示词/工具必须告诉模型怎么标步骤'
