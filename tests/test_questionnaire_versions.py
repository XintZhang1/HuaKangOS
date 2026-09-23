"""Issued original questionnaire schema, strict answers, audit and native transactions."""
import copy,csv,io,json,sqlite3,uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select,update
from app.db import SessionLocal,engine
from app.main import app
from app.models import User,UserStore
from app.tenancy import set_scope
from app.customer_service import authority
from app.questionnaire_models import QuestionnaireBinding,QuestionnaireResponse,QuestionnaireVersion
from app.questionnaire_schema import LEGACY_QUESTIONS,digest
from app.questionnaire_integrity import validate
from tests.conftest import login,TEST_DIR,PASSWORD_HASH
from tests import test_customer_service as care
from tests.test_multistore import second_store,switch

API=care.API+'/questionnaires'
SCHEMA=[{'key':'wait_minutes','label':'本次实际等候分钟数','kind':'integer','required':True,'min_value':0,'max_value':600},
    {'key':'first_visit','label':'是否首次到店','kind':'boolean','required':True},
    {'key':'channel','label':'如何了解到本店','kind':'choice','required':False,'choices':[{'key':'friend','label':'亲友介绍'},{'key':'passing','label':'路过门店'}]},
    {'key':'suggestion','label':'其他建议','kind':'text','required':False,'max_length':200}]


def catalog(c):
    r=c.get(API+'/versions');assert r.status_code==200,r.text;return r.json()

def propose(c,schema=None,**kw):
    values={'policy_version':catalog(c)['policy_version'],'name':'新的到店体验问卷','questions':copy.deepcopy(SCHEMA if schema is None else schema),'reason':'明确本轮实际调查题目，仅用于后续发放'}
    values.update(kw.pop('values',{}))
    return care.post(c,'/questionnaires/versions',values,status=kw.pop('status',201),**kw)

def review(c,row,decision='approve',**kw):
    row=row.get('questionnaire_version',row)
    values={'policy_version':catalog(c)['policy_version'],'decision':decision,'reason':'独立逐题核对了题意、范围和必答规则','confirmed':True}
    values.update(kw.pop('values',{}))
    return care.post(c,f'/questionnaires/versions/{row["id"]}/review',values,**kw)

def published(c):
    login(c,'admin');row=propose(c);login(c,'manager');review(c,row);login(c,'admin');return row['questionnaire_version']

def questionnaire(c,**kw):
    return care.care(c,kw.pop('customer_id',None) or care.customer(),subtype='questionnaire',**kw)

def started(c,**kw):return care.action(c,questionnaire(c,**kw),'start')['case']

def close(c,row,values=None,**kw):
    return care.action(c,row,'close',{'result':'resolved','note':'本人按原题逐项记录客户实际反馈',**(values or {})},**kw)

def verify(count=None):
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        result=validate(db)
        if count is not None:assert result['questionnaire_responses']==count
        from app.backup_integrity import validate_sqlite
        assert validate_sqlite(db)['integrity']=='ok'
        return result


def test_original_v1_remains_after_new_publication_and_false_is_not_missing(client):
    old=started(client);original=copy.deepcopy(old['questionnaire'])
    version=published(client)
    fresh=started(client)
    assert fresh['questionnaire']['number']==2 and fresh['questionnaire']['version_id']==version['id']
    bad=close(client,fresh,{'satisfaction':4,'recommend':False},status=422)
    assert '旧版' in bad['detail']
    completed=close(client,old,{'satisfaction':4,'recommend':False})['case']
    assert completed['questionnaire']['questions']==original['questions']==LEGACY_QUESTIONS
    assert completed['questionnaire']['response']['answers']=={'satisfaction':4,'recommend':False}
    fresh=close(client,fresh,{'answers':{'wait_minutes':0,'first_visit':False}})['case']
    assert fresh['questionnaire']['response']['answers']=={'wait_minutes':0,'first_visit':False}
    assert len(fresh['records'])==3
    assert verify(2)['questionnaire_bindings']==2


@pytest.mark.parametrize('answer',[{}, {'wait_minutes':None,'first_visit':False}, {'wait_minutes':False,'first_visit':False},
    {'wait_minutes':0.0,'first_visit':False}, {'wait_minutes':0,'first_visit':0}, {'wait_minutes':0,'first_visit':'false'},
    {'wait_minutes':0,'first_visit':False,'alien':1}, {'wait_minutes':0,'first_visit':False,'channel':'invented'},
    {'wait_minutes':0,'first_visit':False,'suggestion':''}])
def test_invalid_missing_or_coerced_answer_is_atomic_and_never_becomes_no_or_zero(client,answer):
    published(client);row=started(client)
    close(client,row,{'answers':answer},status=422)
    actual=client.get(care.API+f'/cases/{row["id"]}').json()
    assert actual['version']==row['version'] and actual['state']=='working'
    verify(0)


def test_partial_declined_retains_explicit_zero_and_missing_separately_in_same_csv_chart(client):
    published(client);row=started(client)
    result=close(client,row,{'result':'declined','answers':{'wait_minutes':0}})['case']
    assert result['questionnaire']['response']['answers']=={'wait_minutes':0}
    r=client.get(API+'/report');assert r.status_code==200,r.text;report=r.json()
    values=report['tables']['questionnaire_answers']['rows']
    assert values[0]['answered'] and values[0]['answer']==0
    assert values[1]['answered'] is False and values[1]['answer'] is None
    chart=next(c for c in report['charts'] if c['id']=='questionnaire_2_first_visit')
    assert chart['labels']==['未回答'] and chart['series'][0]['values']==[1]
    for key,table in report['tables'].items():
        response=client.get(API+'/export/'+key);assert response.status_code==200,response.text
        exported=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        assert exported==[table['headers']]+[[str(v) for v in x['values']] for x in table['rows']]
    verify(1)


@pytest.mark.parametrize('mutate',['empty','duplicate','unknown','bool_range','reserved','no_required','choice_duplicate','long_text'])
def test_invalid_schema_never_creates_publication_or_receipt(client,mutate):
    schema=copy.deepcopy(SCHEMA)
    if mutate=='empty':schema=[]
    elif mutate=='duplicate':schema[1]['key']=schema[0]['key']
    elif mutate=='unknown':schema[0]['script']='bad'
    elif mutate=='bool_range':schema[0]['min_value']=False
    elif mutate=='reserved':schema[0]['key']='satisfaction'
    elif mutate=='no_required':
        for q in schema:q['required']=False
    elif mutate=='choice_duplicate':schema[2]['choices'][1]['key']='friend'
    elif mutate=='long_text':schema[3]['max_length']=2001
    before=catalog(client);propose(client,schema,status=422)
    assert catalog(client)==before
    verify(0)


def test_independent_review_pending_reject_stale_and_no_older_activation(client):
    proposal=propose(client);review(client,proposal,status=403)
    assert questionnaire(client)['questionnaire']['number']==1
    login(client,'manager');review(client,proposal,'reject')
    login(client,'admin');second=propose(client);third=propose(client)
    login(client,'manager');review(client,third)
    review(client,second,status=409)
    login(client,'admin');row=questionnaire(client)
    assert row['questionnaire']['number']==4
    verify(0)


def test_legacy_and_new_close_idempotency_same_original_record_after_later_publication(client):
    row=started(client);key=uuid.uuid4().hex;values={'satisfaction':5,'recommend':False}
    old=close(client,row,values,request_id=key)
    published(client)
    assert close(client,row,values,request_id=key)==old
    close(client,row,{'satisfaction':4,'recommend':False},request_id=key,status=409)
    verify(1)


def test_rules_and_answers_never_expand_employee_or_cross_store_scope(client):
    customer=care.customer(owner='sales');login(client,'sales')
    row=started(client,customer_id=customer,assignee='sales')
    propose(client,status=403)
    login(client,'admin');published(client)
    two=second_store(client);switch(client,two)
    assert catalog(client)['active_number']==1 and not catalog(client)['items']
    assert client.get(care.API+f'/cases/{row["id"]}').status_code==404
    assert not client.get(API+'/report').json()['tables']['questionnaire_issued']['rows']
    switch(client,1);care.user_id('reception');login(client,'reception')
    assert not client.get(API+'/report').json()['tables']['questionnaire_issued']['rows']
    login(client,'finance');assert client.get(API+'/versions').status_code==403
    assert client.get(API+'/export/questionnaire_answers').status_code==403
    login(client,'admin');switch(client,'all');assert client.get(API+'/report').status_code==409


def test_native_model_guard_and_source_replay_do_not_accept_rehashed_fabrication(client):
    published(client);row=started(client);close(client,row,{'answers':{'wait_minutes':0,'first_visit':False}})
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='admin'))
        with pytest.raises(HTTPException):db.scalar(select(QuestionnaireResponse))
        with authority(db,user):
            with pytest.raises(HTTPException):db.execute(update(QuestionnaireResponse).values(answers={}))
            response=db.scalar(select(QuestionnaireResponse));response.answers={}
            with pytest.raises(HTTPException):db.flush()
            db.rollback()
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as db:
        source.backup(db);validate(db)
        binding_id,record_id,schema_digest=db.execute('SELECT r.binding_id,r.record_id,b.schema_digest FROM care_questionnaire_responses r JOIN care_questionnaire_bindings b ON b.id=r.binding_id').fetchone()
        value={'wait_minutes':99,'first_visit':True}
        db.execute('UPDATE care_questionnaire_responses SET answers=?,digest=?',(json.dumps(value),digest({'binding_id':binding_id,'record_id':record_id,'schema_digest':schema_digest,'answers':value})))
        with pytest.raises(ValueError,match='问卷版本'):validate(db)


@pytest.mark.parametrize('sql',[
    "UPDATE care_questionnaire_policies SET active_version_id=NULL",
    "UPDATE care_questionnaire_reviews SET actor_id=(SELECT proposed_by FROM care_questionnaire_versions LIMIT 1)",
    "UPDATE care_questionnaire_bindings SET number=7",
    "UPDATE care_questionnaire_bindings SET origin='migration'",
    "DELETE FROM care_questionnaire_bindings",
    "UPDATE care_questionnaire_responses SET record_id=1",
    "UPDATE care_questionnaire_policies SET next_number=30",
    "DROP TABLE care_questionnaire_reviews",
])
def test_restore_rejects_broken_publication_binding_source_or_partial_domain(client,sql):
    published(client);row=started(client);close(client,row,{'answers':{'wait_minutes':0,'first_visit':False}})
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as db:
        source.backup(db);validate(db);db.execute(sql)
        with pytest.raises(ValueError,match='问卷版本'):validate(db)


def test_actual_two_client_native_close_has_one_original_answer_and_winning_replay(client):
    published(client);row=started(client);callers=[TestClient(app),TestClient(app)]
    try:
        for c,who in zip(callers,['admin','manager']):login(c,who)
        bodies=[{'request_id':uuid.uuid4().hex,'version':row['version'],'values':{'result':'resolved','note':'本人记录客户逐题当面回答','answers':{'wait_minutes':i,'first_visit':False}}} for i in range(2)]
        def run(i):return callers[i].post(care.API+f'/cases/{row["id"]}/actions/close',json=bodies[i])
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(run,range(2)))
        assert sorted(r.status_code for r in responses)==[200,409],[r.text for r in responses]
        winner=next(i for i,r in enumerate(responses) if r.status_code==200)
        assert run(winner).json()==responses[winner].json()
        verify(1)
    finally:
        for c in callers:c.close()


def test_actual_two_publication_reviewers_cannot_both_commit_same_registry_version(client):
    with SessionLocal() as db:
        user=User(username='independent_manager',display_name='另一独立主管',role='manager',password_hash=PASSWORD_HASH,must_change_password=False)
        db.add(user);db.flush();db.add(UserStore(user_id=user.id,store_id=1));db.commit()
    one=propose(client);two=propose(client);version=catalog(client)['policy_version'];callers=[TestClient(app),TestClient(app)]
    try:
        login(callers[0],'manager');login(callers[1],'independent_manager')
        bodies=[{'request_id':uuid.uuid4().hex,'values':{'policy_version':version,'decision':'approve','reason':'独立核对本次完整题目版本','confirmed':True}} for _ in range(2)]
        def run(i):return callers[i].post(API+f'/versions/{[one,two][i]["questionnaire_version"]["id"]}/review',json=bodies[i])
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(run,range(2)))
        assert sorted(r.status_code for r in responses)==[200,409],[r.text for r in responses]
        verify(0)
    finally:
        for c in callers:c.close()


def test_nonempty_actual_o57b_originals_upgrade_then_native_old_and_new_questionnaires(client,tmp_path):
    from pathlib import Path
    from datetime import datetime,date
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import MetaData,Table,DateTime,Date,inspect
    from app.db import make_engine,Base
    from scripts.migrate_database import table_fingerprint
    fixture=json.loads((Path(__file__).parent/'fixtures/questionnaire_o57b_synthetic.json').read_text(encoding='utf-8'))
    path=tmp_path/'actual-o57b-questionnaires.sqlite';url='sqlite:///'+path.as_posix()
    cfg=Config('alembic.ini');cfg.attributes['url_override']=url;command.upgrade(cfg,'o57b_found_transit_searches')
    migrated=make_engine(url);metadata=MetaData();metadata.reflect(migrated)
    try:
        with migrated.begin() as db:
            for table in metadata.sorted_tables:
                source=copy.deepcopy(fixture['tables'].get(table.name,[]))
                for row in source:
                    for column in table.columns:
                        value=row.get(column.name)
                        if value is not None and isinstance(column.type,DateTime):row[column.name]=datetime.fromisoformat(value)
                        elif value is not None and isinstance(column.type,Date):row[column.name]=date.fromisoformat(value)
                if source:db.execute(table.insert(),source)
        original_tables=[t for t in metadata.sorted_tables if t.name!='alembic_version']
        with migrated.connect() as db:before={t.name:table_fingerprint(db,t) for t in original_tables}
        with sqlite3.connect(path) as db:assert validate(db)=={'questionnaire_versions':0,'questionnaire_bindings':0,'questionnaire_responses':0}
        command.upgrade(cfg,'head')
        with migrated.connect() as db:assert before=={t.name:table_fingerprint(db,t) for t in original_tables}
        inspector=inspect(migrated)
        for name,table in Base.metadata.tables.items():
            if name.startswith('care_questionnaire_'):assert {c['name'] for c in inspector.get_columns(name)}==set(table.columns.keys())
        with sqlite3.connect(path) as db:
            assert validate(db)=={'questionnaire_versions':0,'questionnaire_bindings':4,'questionnaire_responses':2}
            assert not db.execute('PRAGMA foreign_key_check').fetchone()
        SessionLocal.configure(bind=migrated);login(client,'admin')
        replay=fixture['legacy_replay']
        original=client.post(care.API+f'/cases/{replay["case_id"]}/actions/close',json={k:replay[k] for k in ['request_id','version','values']})
        assert original.status_code==200,original.text
        assert original.json()==replay['result']  # Old immutable receipt is returned byte-for-JSON-byte.
        published(client)
        pending=client.get(care.API+f'/cases/{fixture["pending_id"]}').json()
        assert pending['questionnaire']['number']==1
        close(client,pending,{'satisfaction':5,'recommend':False})
        fresh=started(client);close(client,fresh,{'answers':{'wait_minutes':0,'first_visit':False}})
        with sqlite3.connect(path) as db:
            assert validate(db)=={'questionnaire_versions':1,'questionnaire_bindings':5,'questionnaire_responses':4}
            from app.backup_integrity import validate_sqlite
            assert validate_sqlite(db)['integrity']=='ok'
        assert client.get(API+'/report').status_code==200
    finally:
        SessionLocal.configure(bind=engine);migrated.dispose()


def test_http_pages_include_original_question_builder_and_not_implicit_yes_defaults(client):
    published(client);row=started(client)
    response=client.get('/static/customerservice.js');assert response.status_code==200
    script=response.text
    assert 'careQuestionnaireOriginal' in script and 'careQuestionnaireProposalDialog' in script
    assert "if(raw===null||raw==='')continue" in script
    assert "Number.isSafeInteger(Number(raw))" in script
    assert row['questionnaire']['response'] is None
