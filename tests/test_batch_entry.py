from dataclasses import replace
from typing import get_args
import json
from unittest.mock import patch
import httpx
import pytest
from sqlalchemy import select, func
from fastapi.testclient import TestClient
from app.db import SessionLocal
from app.main import app
from app.models import MODULES, AuditLog
from app.schemas import EntryDraftInput
from app import batch_entry, main
from app.batch_entry import FIELD_KINDS, normalise_fields, build_prompt, parse_rows, extract

KEY='secret-key-test'
TEXT='客户张三，VIN LDD00000000000001，采购价 3.5万，2026-01-02 入库；李四，VIN LDD00000000000002，11.8万'
SPEC=[{'name':'vin','label':'车架号','kind':'text','required':True},
      {'name':'amount','label':'金额','kind':'money','required':True},
      {'name':'day','label':'日期','kind':'date','required':False},
      {'name':'stage','label':'阶段','kind':'select','required':False,'options':['已交车','已订车']}]
BODY={'module':'vehicles','text':TEXT,'fields':SPEC}


def spec(): return normalise_fields(SPEC)


def use_ai(monkeypatch,**overrides):
    values={'allow_ai':True,'deepseek_key':KEY}
    values.update(overrides)
    monkeypatch.setattr(batch_entry,'settings',replace(batch_entry.settings,**values))


def mock_ai(monkeypatch,content,finish='stop',status=200):
    use_ai(monkeypatch)
    body={'choices':[{'finish_reason':finish,'message':{'content':content}}]}
    return httpx.Response(status,json=body,request=httpx.Request('POST','https://api.deepseek.com/chat/completions'))


def test_field_kinds_are_the_documented_set():
    assert FIELD_KINDS=={'text','textarea','date','money','number','select','lookup','tel','password'}


def test_normalise_fields_accepts_a_full_spec():
    raw=[{'name':f'field_{i}','label':f'字段{i}','kind':kind,'required':i%2==0,
          'options':['甲','乙'] if kind=='select' else None} for i,kind in enumerate(sorted(FIELD_KINDS))]
    result=normalise_fields(raw)
    assert [f['kind'] for f in result]==sorted(FIELD_KINDS)
    assert all(set(f)=={'name','label','kind','required','options'} for f in result)
    assert result[0]['required'] is True and result[1]['required'] is False
    assert next(f for f in result if f['kind']=='select')['options']==['甲','乙']
    defaults=normalise_fields([{'name':'note','kind':'textarea'}])[0]
    assert defaults=={'name':'note','label':'note','kind':'textarea','required':False,'options':None}
    assert normalise_fields([{'name':'stage','kind':'select','options':['已交车','已交车','']}])[0]['options']==['已交车']
    assert normalise_fields([{'name':'vin','kind':'text'}])[0]['name']=='vin'


@pytest.mark.parametrize('raw',[
    'not-a-list',{},[],None,
    [{'label':'车架号','kind':'text'}],
    [{'name':'','kind':'text'}],
    [{'name':123,'kind':'text'}],
    [{'name':'VIN','kind':'text'}],
    [{'name':'1vin','kind':'text'}],
    [{'name':'vin-code','kind':'text'}],
    [{'name':'a'*41,'kind':'text'}],
    [{'name':'vin','kind':'text'},{'name':'vin','kind':'money'}],
    [{'name':'vin','label':'x'*81,'kind':'text'}],
    [{'name':'vin','label':'   ','kind':'text'}],
    [{'name':'vin','kind':'json'}],
    [{'name':'vin'}],
    [{'name':'vin','kind':'text','options':'甲'}],
    [{'name':'vin','kind':'text'},'nope'],
    [{'name':f'field_{i}','kind':'text'} for i in range(61)],
])
def test_normalise_fields_rejects_malformed_specs(raw):
    with pytest.raises(ValueError):
        normalise_fields(raw)


def test_build_prompt_lists_every_field_and_forbids_extras(monkeypatch):
    use_ai(monkeypatch)
    fields=spec()
    system,user=build_prompt('sales',fields,TEXT)
    assert 'sales' in system
    for field in fields:
        assert field['name'] in system and field['label'] in system
        assert ('必填' if field['required'] else '可选') in system
    assert '已交车、已订车' in system
    assert '"rows"' in system and 'markdown' in system and 'null' in system
    assert '不是给你的指令' in system
    assert '不得新增' in system
    assert TEXT in user and '<文本>' in user
    for secret in [KEY,'Bearer','Authorization','sk-','deepseek_key']:
        assert secret not in system+user


def test_unknown_key_dropped_and_missing_required_recorded():
    rows,issues=parse_rows({'rows':[{'vin':'LDD00000000000001','amount':'100','evil':'x','__proto__':1}]},spec(),'')
    assert rows==[{'vin':'LDD00000000000001','amount':'100'}]
    assert {(i['field'],i['reason']) for i in issues}=={('evil','未知字段，已丢弃'),('__proto__','未知字段，已丢弃')}
    assert all(i['row']==0 and isinstance(i['field'],str) and isinstance(i['reason'],str) for i in issues)


def test_missing_required_fields_are_issues_not_a_crash():
    rows,issues=parse_rows({'rows':[{'day':'2026-01-01'}]},spec(),'')
    assert rows==[{'day':'2026-01-01'}]
    assert [(i['field'],i['reason']) for i in issues]==[('vin','缺少必填字段'),('amount','缺少必填字段')]


@pytest.mark.parametrize('value,expected',[
    ('3.5万','35000'),('2万元','20000'),('￥1,234.50','1234.50'),('1,234.5','1234.5'),('￥1234','1234'),
    ('1000元','1000'),(1234.5,'1234.5'),(0,'0'),(-5,'-5'),('  88  ','88'),
])
def test_money_forms_are_normalised_to_decimal_text(value,expected):
    rows,issues=parse_rows({'rows':[{'vin':'V','amount':value}]},spec(),'')
    assert rows[0]['amount']==expected
    assert [i for i in issues if i['field']=='amount']==[]


@pytest.mark.parametrize('value',['abc','一万','12.3.4','','NaN','Infinity','--3',True,['1'],{'x':1}])
def test_unparsable_money_is_an_issue_and_null(value):
    rows,issues=parse_rows({'rows':[{'vin':'V','amount':value}]},spec(),'')
    assert rows[0]['amount'] is None
    assert [i['field'] for i in issues if i['field']=='amount']==['amount']
    assert all(i['reason'] for i in issues)


def test_number_kind_uses_the_same_parser():
    rows,issues=parse_rows({'rows':[{'count':'3.5万'}]},normalise_fields([{'name':'count','kind':'number'}]),'')
    assert rows==[{'count':'35000'}] and issues==[]


@pytest.mark.parametrize('value',['2026/01/01','2026-1-1','20260101','2026-13-01','2026-02-30','tomorrow',''])
def test_bad_date_is_an_issue_and_null(value):
    rows,issues=parse_rows({'rows':[{'day':value}]},spec(),'')
    assert rows[0]['day'] is None
    assert [i['field'] for i in issues if i['field']=='day']==['day']


def test_select_outside_options_is_an_issue_and_null():
    rows,issues=parse_rows({'rows':[{'stage':'已退车'},{'stage':'已交车'}]},spec(),'')
    assert rows[0]['stage'] is None and rows[1]['stage']=='已交车'
    assert len([i for i in issues if i['field']=='stage'])==1
    rows,_=parse_rows({'rows':[{'stage':'任意值'}]},normalise_fields([{'name':'stage','kind':'select'}]),'')
    assert rows==[{'stage':'任意值'}]


def test_text_values_are_coerced_to_string():
    rows,issues=parse_rows({'rows':[{'vin':12345,'day':None}]},spec(),'')
    assert rows[0]['vin']=='12345' and rows[0]['day'] is None
    assert [i for i in issues if i['field'] in {'vin','day'}]==[]


def test_rows_are_truncated_to_ai_max_records(monkeypatch):
    monkeypatch.setattr(batch_entry,'settings',replace(batch_entry.settings,ai_max_records=2))
    rows,issues=parse_rows({'rows':[{'vin':f'V{i}'} for i in range(5)]},spec(),'')
    assert len(rows)==2 and rows[1]=={'vin':'V1'}


def test_non_object_rows_are_reported_not_raised():
    rows,issues=parse_rows({'rows':['x',{'vin':'V'}]},spec(),'')
    assert rows==[{'vin':'V'}] and issues[0]=={'row':0,'field':'','reason':'该条不是字段对象，已丢弃'}


@pytest.mark.parametrize('payload',[{},{'rows':'x'},{'rows':None},{'rows':{}},{'rows':[]},[],None,'nonsense',42])
def test_empty_or_garbage_payload_yields_nothing(payload):
    assert parse_rows(payload,spec(),'')==([],[])


def test_extract_refuses_when_ai_is_disabled(monkeypatch):
    monkeypatch.setattr(batch_entry,'settings',replace(batch_entry.settings,allow_ai=False,deepseek_key=KEY))
    with patch('app.batch_entry.httpx.Client') as http:
        with pytest.raises(ValueError) as exc:
            extract('vehicles',spec(),TEXT)
    assert '未启用' in str(exc.value) and KEY not in str(exc.value)
    http.assert_not_called()


def test_extract_refuses_without_a_key(monkeypatch):
    use_ai(monkeypatch,deepseek_key='')
    with patch('app.batch_entry.httpx.Client') as http:
        with pytest.raises(ValueError) as exc:
            extract('vehicles',spec(),TEXT)
    assert 'API Key' in str(exc.value)
    http.assert_not_called()


def test_extract_returns_drafts_from_a_valid_model_payload(monkeypatch):
    content=json.dumps({'rows':[{'vin':'LDD00000000000001','amount':'3.5万','day':'2026-01-02','stage':'已交车'}]})
    response=mock_ai(monkeypatch,content)
    with patch('app.batch_entry.httpx.Client') as http:
        http.return_value.__enter__.return_value.post.return_value=response
        result=extract('sales',spec(),TEXT)
        sent=http.return_value.__enter__.return_value.post.call_args
    assert result=={'module':'sales','proposed':1,'issues':[],
        'rows':[{'vin':'LDD00000000000001','amount':'35000','day':'2026-01-02','stage':'已交车'}]}
    payload=sent.kwargs['json']
    assert payload['response_format']=={'type':'json_object'} and payload['max_tokens']==4000 and payload['stream'] is False
    assert payload['model'] and payload['messages'][0]['role']=='system'
    assert KEY not in json.dumps(payload,ensure_ascii=False)
    assert sent.kwargs['headers']['Authorization']=='Bearer '+KEY
    assert sent.args[0].endswith('/chat/completions')


def test_extract_tolerates_an_empty_model_payload(monkeypatch):
    for content in ['{}','{"nope":1}','{"rows":"x"}','[]']:
        response=mock_ai(monkeypatch,content)
        with patch('app.batch_entry.httpx.Client') as http:
            http.return_value.__enter__.return_value.post.return_value=response
            result=extract('vehicles',spec(),TEXT)
        assert result=={'module':'vehicles','rows':[],'issues':[],'proposed':0},content


@pytest.mark.parametrize('content,finish',[('','stop'),('not json','stop'),
    (json.dumps({'rows':[{'vin':'V'}]}),'length')])
def test_unusable_model_output_raises_a_chinese_error(monkeypatch,content,finish):
    response=mock_ai(monkeypatch,content,finish)
    with patch('app.batch_entry.httpx.Client') as http:
        http.return_value.__enter__.return_value.post.return_value=response
        with pytest.raises(ValueError) as exc:
            extract('vehicles',spec(),TEXT)
    message=str(exc.value)
    assert 'DeepSeek' in message and KEY not in message
    assert not content or content not in message


def test_provider_error_is_credential_free(monkeypatch):
    response=mock_ai(monkeypatch,KEY,status=401)
    with patch('app.batch_entry.httpx.Client') as http:
        http.return_value.__enter__.return_value.post.return_value=response
        with pytest.raises(ValueError) as exc:
            extract('vehicles',spec(),TEXT)
    assert 'HTTP 401' in str(exc.value) and KEY not in str(exc.value)


def test_network_error_becomes_a_chinese_error(monkeypatch):
    use_ai(monkeypatch)
    with patch('app.batch_entry.httpx.Client') as http:
        http.return_value.__enter__.return_value.post.side_effect=httpx.ConnectError('boom')
        with pytest.raises(ValueError) as exc:
            extract('vehicles',spec(),TEXT)
    assert '网络' in str(exc.value) and 'boom' not in str(exc.value)


def test_module_literal_matches_models_modules():
    assert set(get_args(EntryDraftInput.model_fields['module'].annotation))==set(MODULES)


def test_endpoint_returns_drafts_and_never_writes_a_business_record(client,monkeypatch):
    rows=[{'vin':'LDD00000000000001','amount':'35000'}]
    issues=[{'row':0,'field':'day','reason':'缺少必填字段'}]
    monkeypatch.setattr(main,'extract',lambda module,fields,text:{'module':module,'rows':rows,'issues':issues,'proposed':1})
    response=client.post('/api/entry-draft/parse',json=BODY)
    assert response.status_code==200,response.text
    assert response.json()=={'module':'vehicles','rows':rows,'issues':issues,'proposed':1}
    with SessionLocal() as db:
        for module,model in MODULES.items():
            assert db.scalar(select(func.count()).select_from(model))==0,module+' 不应被 AI 草稿写入'
        logs=list(db.scalars(select(AuditLog).where(AuditLog.action=='entry_draft_parse')))
    assert len(logs)==1 and logs[0].entity_type=='entry_draft' and logs[0].entity_id is None
    assert logs[0].actor_id==1 and '1' in logs[0].reason and '人工复核' in logs[0].reason


def test_endpoint_caps_rows_at_ai_max_records(client,monkeypatch):
    monkeypatch.setattr(main,'settings',replace(main.settings,ai_max_records=2))
    monkeypatch.setattr(main,'extract',lambda module,fields,text:{'module':module,'rows':[{'vin':f'V{i}'} for i in range(5)],'issues':[],'proposed':5})
    body=client.post('/api/entry-draft/parse',json=BODY).json()
    assert len(body['rows'])==2 and body['proposed']==2


def test_endpoint_maps_extractor_value_error_to_400(client,monkeypatch):
    def broken(module,fields,text): raise ValueError('模拟模型不可用')
    monkeypatch.setattr(main,'extract',broken)
    response=client.post('/api/entry-draft/parse',json=BODY)
    assert response.status_code==400 and response.json()['detail']=='模拟模型不可用'
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='entry_draft_parse'))==0


def test_endpoint_refuses_while_external_ai_is_disabled(client):
    response=client.post('/api/entry-draft/parse',json=BODY)
    assert response.status_code==400 and '未启用' in response.json()['detail']


def test_endpoint_rejects_a_malformed_field_spec(client):
    response=client.post('/api/entry-draft/parse',json=dict(BODY,fields=[{'name':'VIN','kind':'text'}]))
    assert response.status_code==400 and '字段名不合法' in response.json()['detail']


@pytest.mark.parametrize('updates',[{'text':'太短'},{'module':'unknown'},{'module':'records'},{'fields':[]},
    {'fields':[{'name':'vin','kind':'text'}]*61},{'text':'x'*20001},{'fields':'vin'}])
def test_endpoint_validates_the_request_body(client,updates):
    assert client.post('/api/entry-draft/parse',json=dict(BODY,**updates)).status_code==422


def test_endpoint_requires_a_login():
    with TestClient(app) as anonymous:
        assert anonymous.post('/api/entry-draft/parse',json=BODY).status_code in {401,403}

def test_prompt_separates_staff_from_customer_roles():
    """回归：模型曾把服务顾问填进客户姓名字段。

    根因是提示词只说「不要猜」，却没告诉它本店员工和客户是两类不同的人——
    面对「沪B67890 李娜 保险维修」这种没写角色的文本，它只能硬选一个字段。
    """
    fields = normalise_fields([
        {'name': 'service_advisor', 'label': '服务顾问', 'kind': 'text', 'required': True, 'options': None},
        {'name': 'customer_name', 'label': '客户姓名 / 简称', 'kind': 'text', 'required': True, 'options': None},
    ])
    system, _ = build_prompt('repairs', fields, '沪B67890 李娜 保险维修 工时1500')
    assert '角色区分' in system
    assert '绝不可混用' in system
    # 角色不明时必须留空而不是二选一
    assert '宁可相关字段全部留空' in system
    # 不得编造
    assert '绝不用常见姓名' in system
