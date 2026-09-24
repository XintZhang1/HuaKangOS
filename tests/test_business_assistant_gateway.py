"""The assistant must re-enter native roles, store scope and guarded commands."""
import asyncio
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app import business_assistant_gateway as gateway
from app.db import SessionLocal
from app.flow_models import Customer,Case
from tests.conftest import login


def invoke(client,operation,path=None,query=None,body=None,store=1):
    request=SimpleNamespace(base_url='http://testserver/',headers={
        'cookie':'; '.join(f'{k}={v}' for k,v in client.cookies.items()),
        'x-csrf-token':client.headers.get('X-CSRF-Token','')})
    # Even a misleading in-memory role cannot override native session identity.
    user=SimpleNamespace(role='admin',_active_store_id=store,_aggregate_scope=False)
    return asyncio.run(gateway.invoke(request,user,operation,path,query,body))


def test_discovery_excludes_credentials_files_opening_and_arbitrary_urls():
    ids={row['id'] for row in gateway.catalog()}
    assert 'POST /api/flow/cases' in ids and 'POST /api/masters/{kind}' in ids
    # Reads now cover the management pages the employee's own role can open, but credentials,
    # files, exports, imports and deployment settings stay out of the catalogue.
    assert 'GET /api/users' in ids and 'GET /api/audit' in ids
    assert all('/auth/' not in op and '/opening/' not in op and '/files' not in op and '/export' not in op
               and '/local-preview' not in op and '/branding' not in op and '/business-assistant/' not in op
               for op in ids)
    for op in ('GET https://example.org','POST /api/auth/password','POST /api/masters/opening/confirm','GET /api/flow/files/{file_id}'):
        with pytest.raises(HTTPException):gateway.inspect_operation(op)
    with pytest.raises(HTTPException):gateway.validate_operation('GET /api/flow/master/{kind}',{'kind':'templates'})


@pytest.mark.parametrize('path,query',[
    ({'kind':'../accounts'},{}),({'kind':'customers/../../users'},{}),
    ({'kind':'customers','store_id':2},{}),({'kind':'customers'},{'X-Store-ID':2}),
    ({'kind':'customers'},{'q':['invalid']}),
])
def test_operation_parameters_cannot_escape_declared_route(path,query):
    with pytest.raises(HTTPException):gateway.validate_operation('GET /api/flow/master/{kind}',path,query)

def test_wrong_placeholder_returns_exact_candidate_but_never_executes():
    with pytest.raises(HTTPException) as mistake:gateway.inspect_operation('GET /api/flow/cases/{id}')
    assert mistake.value.status_code==422
    assert 'GET /api/flow/cases/{case_id}' in mistake.value.detail and '本次未执行' in mistake.value.detail


def test_dynamic_fields_are_checked_before_confirmation_and_units_shown():
    with pytest.raises(HTTPException) as customer:
        gateway.validate_operation('POST /api/flow/cases',body={'kind':'lead','values':{'source':'展厅到店'}})
    assert '客户姓名' in customer.value.detail
    with pytest.raises(HTTPException) as missing:
        gateway.validate_operation('POST /api/flow/cases',body={'kind':'lead','values':{'customer_name':'合成接待'}})
    assert '客户来源' in missing.value.detail
    with pytest.raises(HTTPException) as typed:
        gateway.validate_operation('POST /api/masters/{kind}',{'kind':'vehicle_series'},body={'values':{'name':'合成车系','code':'TEST'}})
    assert '所属品牌' in typed.value.detail
    prepared=gateway.validate_operation('POST /api/masters/{kind}',{'kind':'vehicle_brands'},body={'request_id':'model-chosen-key','values':{'name':'合成品牌','code':'TEST'}})
    assert prepared['body']['request_id']!='model-chosen-key'
    fields=gateway.display_fields({'path_args':{'kind':'vehicle_models'},'body':{'values':{'guide_price_cents':123456,'fuel_type':'electric'},'lines':[{'quantity_milli':1250}]*12}},'POST /api/masters/{kind}')
    assert {'label':'指导价（元）','value':'1234.56'} in fields
    assert {'label':'动力类型','value':'纯电'} in fields
    assert sum(r['value']=='1.25' for r in fields)==12


def test_forwarding_retains_native_owner_and_financial_role_scope(client):
    result=client.post('/api/flow/master/customers',json={'values':{'name':'主管客户','phone':'13900009001'}})
    assert result.status_code==201
    login(client,'sales')
    assert invoke(client,'GET /api/flow/master/{kind}',{'kind':'customers'})['data']['total']==0
    assert invoke(client,'GET /api/flow/master/{kind}',{'kind':'accounts'})['status']==403
    assert invoke(client,'POST /api/masters/{kind}',{'kind':'vehicle_brands'},body={'request_id':'synthetic-key-00000001','values':{'code':'BAD','name':'禁止建品牌'}})['status']==403
    # A store id the employee does not work in is refused. Since 2026-09-24 an unknown/deactivated
    # store answers 409 with the actionable "当前门店已停用或不存在" message so the page can recover;
    # a store that exists and is active but is not theirs stays 403. Either way nothing is returned.
    unavailable=invoke(client,'GET /api/flow/master/{kind}',{'kind':'customers'},store=999)
    assert unavailable['status'] in {403,404,409},unavailable
    assert 'data' not in unavailable or unavailable.get('data',{}).get('total') is None


def test_native_idempotency_and_customer_ownership_survive_gateway(client):
    login(client,'sales')
    operation='POST /api/flow/cases'
    normalized=gateway.validate_operation(operation,body={'kind':'lead','values':{'customer_name':'助手合成接待','source':'展厅到店'}})
    first=invoke(client,operation,body=normalized['body'])
    again=invoke(client,operation,body=normalized['body'])
    assert first['status']==201 and again['status']==201,(first,again)
    assert first['data']['id']==again['data']['id']
    assert first['route']=='case/'+str(first['data']['id'])
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Case))==1
        assert db.scalar(select(func.count()).select_from(Customer))==1
    found=invoke(client,'GET /api/flow/master/{kind}',{'kind':'customers'})
    assert found['data']['total']==1


def test_native_csrf_and_revoked_session_are_not_bypassed(client):
    normalized=gateway.validate_operation('POST /api/flow/master/{kind}',{'kind':'customers'},body={'values':{'name':'未授权'}})
    old=client.headers.pop('X-CSRF-Token')
    result=invoke(client,'POST /api/flow/master/{kind}',{'kind':'customers'},body=normalized['body'])
    assert result['status']==403
    client.headers['X-CSRF-Token']=old
    assert client.post('/api/auth/logout',json={}).status_code==200
    assert invoke(client,'GET /api/flow/tasks')['status']==401
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Customer))==0


def test_catalog_subset_and_sanitizing_are_explicit(client):
    data=invoke(client,'GET /api/flow/catalog',query={'assistant_kind':'lead'})['data']
    assert set(data['kinds'])=={'lead'} and data['kinds']['lead']['label']=='售前接待'
    sanitized=gateway.sanitize({'password':'secret','nested':{'api_key':'secret','name':'正常'},'note':'sk-fake00000000000000000000000000'})
    assert sanitized['nested']=={'name':'正常'} and 'sk-' not in sanitized['note'] and 'password' not in sanitized
