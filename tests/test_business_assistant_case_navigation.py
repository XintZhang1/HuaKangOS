"""Actual scoped case/contact endpoints; model replies are synthetic and local."""
from datetime import timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app.db import SessionLocal,today
from app.flow_models import Case,Customer,FlowEvent
from app.models import Store,User,UserStore
from app import business_assistant_gateway as gateway
from app import business_assistant_service as service
from tests.conftest import login
from tests.test_business_assistant import session,confirm
from tests.test_business_assistant_case_tools import ask_tool
from tests.test_business_assistant_gateway import invoke
from tests.test_employee_simplicity import lead
from tests.test_workflow import action,detail,create


@pytest.fixture
def assistant_config(monkeypatch):
    monkeypatch.setattr(service,'load_config',lambda:service.AssistantConfig(True,'synthetic-case-only','deepseek-flash',5,True))


def intent_case(client):
    row=lead(client);login(client,'sales')
    return action(client,row,'intent',{'need':'合成客户明确购车意向','due_date':today().isoformat()})


@pytest.mark.parametrize('operation,path,query',[
    ('GET /api/flow/master/{kind}',{'kind':'customer'},{}),
    ('PUT /api/flow/master/{kind}/{record_id}',{'kind':'customer','record_id':1},{}),
    ('GET /api/flow/catalog',{}, {'assistant_kind':'customer'}),
    ('GET /api/masters/{kind}',{'kind':'supplier'},{}),
])
def test_wrong_kind_is_input_error_before_native_permission_check(client,operation,path,query):
    with pytest.raises(HTTPException) as error:invoke(client,operation,path,query)
    assert error.value.status_code==422
    assert '类别参数错误' in error.value.detail and ('customers' in error.value.detail or 'suppliers' in error.value.detail)


def test_customer_catalog_subset_distinguishes_allowed_from_wrong_role(client):
    data=invoke(client,'GET /api/flow/catalog',query={'assistant_kind':'customers'})
    assert data['status']==200 and data['data']['master_types']['customers']['can_write']
    assert data['data']['kinds']=={}
    login(client,'inventory')
    denied=invoke(client,'GET /api/flow/catalog',query={'assistant_kind':'customers'})
    assert denied['status']==403 and denied['error_category']=='permission'


@pytest.mark.parametrize('actor',['admin','sales'])
def test_intent_get_case_shows_native_follow_and_related_phone_entry(client,assistant_config,monkeypatch,actor):
    row=intent_case(client);login(client,actor);sid=session(client)
    original=detail(client,row)
    result,tools=ask_tool(client,monkeypatch,sid,'get_case',{'case_id':row['id']})
    data=tools[0]['data'];assert data['actions']==original['actions']
    assert {'follow','reserve','close'}<=set(a['key'] for a in data['actions'])
    assert all(a['key']!='remind' for a in data['actions'])
    contact=data['related_operations'][0]
    assert contact['enabled'] and contact['tool']=='prepare_customer_contact'
    assert '意向跟进' in ' '.join(data['assistant_guidance'])
    assert '不能编造' in ' '.join(data['assistant_guidance']) and result['proposals']==[]


@pytest.mark.parametrize('actor',['admin','sales'])
def test_phone_draft_preserves_other_customer_fields_and_requires_click(client,assistant_config,monkeypatch,actor):
    row=intent_case(client)
    with SessionLocal() as db:
        customer=db.get(Customer,row['customer_id']);customer.note='合成备注应保留';customer.contact_allowed=False;db.commit()
    login(client,actor);sid=session(client)
    result,_=ask_tool(client,monkeypatch,sid,'prepare_customer_contact',{'case_id':row['id'],'phone':'13900001234'})
    draft=result['proposals'][0];body=draft['details']['body']
    assert body['values']=={'name':'补电话测试','phone':'13900001234','contact_allowed':False,'note':'合成备注应保留'}
    assert detail(client,row)['customer']['phone']==''
    posted=confirm(client,sid,draft);assert posted.status_code==200,posted.text
    assert posted.json()['proposals'][0]['status']=='succeeded'
    assert confirm(client,sid,draft).status_code==200
    after=detail(client,row);assert after['state']=='intent'
    assert after['customer']['phone']=='13900001234' and after['customer']['contact_allowed'] is False
    with SessionLocal() as db:assert db.get(Customer,row['customer_id']).note=='合成备注应保留'


def test_contact_draft_uses_customer_version_and_rejects_intervening_update(client,assistant_config,monkeypatch):
    row=intent_case(client);sid=session(client)
    result,_=ask_tool(client,monkeypatch,sid,'prepare_customer_contact',{'case_id':row['id'],'phone':'13900001234'})
    draft=result['proposals'][0]
    with SessionLocal() as db:
        customer=db.get(Customer,row['customer_id']);customer.note='其他员工已更新';db.commit()
    posted=confirm(client,sid,draft).json()['proposals'][0]
    assert posted['status']=='failed' and posted['result']['status']==409
    with SessionLocal() as db:
        customer=db.get(Customer,row['customer_id']);assert customer.phone=='' and customer.note=='其他员工已更新'


@pytest.mark.parametrize('phone',['','bad phone','13900001234'+'0'*25])
def test_bad_phone_does_not_create_a_confirmation(client,assistant_config,monkeypatch,phone):
    row=intent_case(client);sid=session(client)
    result,tools=ask_tool(client,monkeypatch,sid,'prepare_customer_contact',{'case_id':row['id'],'phone':phone})
    assert result['proposals']==[] and tools[0]['status']==422


def test_intent_follow_needs_employee_facts_then_uses_real_action(client,assistant_config,monkeypatch):
    row=intent_case(client);sid=session(client);tomorrow=(today()+timedelta(days=1)).isoformat()
    result,tools=ask_tool(client,monkeypatch,sid,'prepare_case_action',{'case_id':row['id'],'action':'follow','values':{'due_date':tomorrow},'summary':'安排明天跟进'})
    assert result['proposals']==[] and tools[0]['status']==422 and '沟通结果' in tools[0]['error']
    result,tools=ask_tool(client,monkeypatch,sid,'prepare_case_action',{'case_id':row['id'],'action':'remind','values':{'due_date':tomorrow,'result':'不应转换接待状态'},'summary':'不应转换接待状态'})
    assert result['proposals']==[] and tools[0]['status']==409 and '意向跟进' in tools[0]['error']
    facts='合成员工确认：客户今天来店看车，约定明天再电话联系'
    result,_=ask_tool(client,monkeypatch,sid,'prepare_case_action',{'case_id':row['id'],'action':'follow','values':{'due_date':tomorrow,'result':facts},'summary':'登记真实跟进及明天计划'})
    draft=result['proposals'][0]
    assert detail(client,row)['due_date']==today().isoformat()
    assert confirm(client,sid,draft).json()['proposals'][0]['status']=='succeeded'
    after=detail(client,row);assert after['state']=='intent' and after['due_date']==tomorrow
    assert after['data']['result']==facts
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(FlowEvent).where(FlowEvent.case_id==row['id'],FlowEvent.action=='follow'))==1


def test_find_cases_scopes_mine_and_visible_without_picking_same_name(client,assistant_config,monkeypatch):
    first=lead(client);second=lead(client)
    own=create(client,'lead',{'customer_name':'管理员本人合成客户','source':'展厅到店'})
    sid=session(client)
    _,mine=ask_tool(client,monkeypatch,sid,'find_cases',{'query':'补电话测试','kind':'lead'})
    assert mine[0]['data']['items']==[] and mine[0]['data']['scope']=='mine'
    _,visible=ask_tool(client,monkeypatch,sid,'find_cases',{'query':'补电话测试','kind':'lead','scope':'visible'})
    data=visible[0]['data'];assert {item['id'] for item in data['items']}=={first['id'],second['id']}
    assert data['selection_required'] and not data['has_more']
    _,one=ask_tool(client,monkeypatch,sid,'find_cases',{'query':own['number'],'kind':'lead'})
    assert one[0]['data']['items'][0]['id']==own['id'] and not one[0]['data']['selection_required']
    login(client,'sales');sid=session(client)
    _,sales=ask_tool(client,monkeypatch,sid,'find_cases',{'query':'补电话测试','kind':'lead'})
    assert len(sales[0]['data']['items'])==2


@pytest.mark.parametrize('mode',['role','store','other_owner'])
def test_contact_helper_cannot_bypass_native_visibility_or_owner(client,assistant_config,monkeypatch,mode):
    row=intent_case(client)
    if mode=='role':login(client,'inventory')
    elif mode=='store':
        with SessionLocal() as db:
            db.add(Store(id=2,code='CASE-B',name='合成乙店'));db.flush()
            uid=db.scalar(select(User.id).where(User.username=='sales'));db.add(UserStore(user_id=uid,store_id=2));db.commit()
        login(client,'sales');client.headers['X-Store-ID']='2'
    else:
        with SessionLocal() as db:
            customer=db.get(Customer,row['customer_id']);customer.owner_id=db.scalar(select(User.id).where(User.username=='manager'));db.commit()
    sid=session(client)
    result,tools=ask_tool(client,monkeypatch,sid,'prepare_customer_contact',{'case_id':row['id'],'phone':'13900001234'})
    assert result['proposals']==[] and tools[0]['status'] in {403,404}
    with SessionLocal() as db:assert db.get(Customer,row['customer_id']).phone==''


def test_existing_phone_is_not_rewritten(client,assistant_config,monkeypatch):
    row=intent_case(client)
    with SessionLocal() as db:db.get(Customer,row['customer_id']).phone='13900001234';db.commit()
    sid=session(client)
    result,tools=ask_tool(client,monkeypatch,sid,'prepare_customer_contact',{'case_id':row['id'],'phone':'13900001234'})
    assert result['proposals']==[] and tools[0]['data']['unchanged']


def test_mine_query_with_more_visible_pages_is_not_reported_as_final_empty(client,assistant_config,monkeypatch):
    with SessionLocal() as db:
        admin_id=db.scalar(select(User.id).where(User.username=='admin'))
        sales_id=db.scalar(select(User.id).where(User.username=='sales'))
        for index in range(31):
            db.add(Case(store_id=1,number=f'PAGING-{index:03}',kind='lead',state='contacting',title='分页合成客户',
                        owner_id=admin_id if index==0 else sales_id,created_by=admin_id,business_date=today()))
        db.commit()
    sid=session(client)
    first,tools=ask_tool(client,monkeypatch,sid,'find_cases',{'query':'分页合成客户','kind':'lead'})
    data=tools[0]['data'];assert data['items']==[] and data['has_more'] and data['next_page']==2 and data['selection_required']
    assert first['proposals']==[]
    second,tools=ask_tool(client,monkeypatch,sid,'find_cases',{'query':'分页合成客户','kind':'lead','page':2})
    data=tools[0]['data'];assert len(data['items'])==1 and not data['has_more']
    assert data['items'][0]['number']=='PAGING-000' and second['proposals']==[]
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Case))==31


def test_redacted_customer_note_is_never_written_back(client,assistant_config,monkeypatch):
    row=intent_case(client);original='合成备注：password=synthetic-only-value'
    with SessionLocal() as db:db.get(Customer,row['customer_id']).note=original;db.commit()
    sid=session(client)
    result,tools=ask_tool(client,monkeypatch,sid,'prepare_customer_contact',{'case_id':row['id'],'phone':'13900001234'})
    assert result['proposals']==[] and tools[0]['status']==409 and '完整保留' in tools[0]['error']
    with SessionLocal() as db:
        customer=db.get(Customer,row['customer_id']);assert customer.note==original and customer.phone==''


@pytest.mark.parametrize('name,operation',[
    ('find_cases','GET /api/flow/cases'),
    ('get_case','GET /api/flow/cases/{case_id}'),
    ('prepare_customer_contact','GET /api/flow/master/{kind}'),
])
def test_truncated_reads_are_not_reported_as_empty_or_permission_denied(client,assistant_config,monkeypatch,name,operation):
    row=intent_case(client);sid=session(client);original=gateway.invoke
    async def oversized(request,user,operation_id,*args,**kwargs):
        if operation_id==operation:return {'status':200,'data':{'truncated':True,'total':30,'detail':'结果较多'}}
        return await original(request,user,operation_id,*args,**kwargs)
    monkeypatch.setattr(gateway,'invoke',oversized)
    args={'query':'合成'} if name=='find_cases' else {'case_id':row['id']}
    if name=='prepare_customer_contact':args['phone']='13900001234'
    result,tools=ask_tool(client,monkeypatch,sid,name,args)
    assert result['proposals']==[] and tools[0]['status']==409 and '较多' in tools[0]['error']
