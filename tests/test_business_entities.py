"""Synthetic acceptance through the registered production entity routes."""
import uuid,sqlite3,json
from datetime import timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app.main import app
from app import business_entity_service as svc
from app.business_entity_models import *
from app.db import SessionLocal,today,engine
from app.models import User,UserStore,Store,CashEntry
from app.flow_models import Case,Account,Item,FlowEvent,FileAsset
from app.tenancy import set_scope,project_user
from tests.conftest import login,PASSWORD_HASH
from tests.test_workflow import evidence

def config(c):
    r=c.get('/api/business-entities/configuration');assert r.status_code==200,r.text;return r.json()
def create(c,operation,details,status=201,key=None):
    r=c.post('/api/business-entities/applications',json={'request_id':key or uuid.uuid4().hex,'operation':operation,'details':details,'reason':'合成资料由本人核对后提出','due_date':today().isoformat()})
    assert r.status_code==status,r.text;return r.json()
def act(c,row,action,values=None,status=200,key=None):
    r=c.post(f'/api/business-entities/applications/{row["id"]}/actions/{action}',json={'request_id':key or uuid.uuid4().hex,'version':row['version'],'values':values or {}})
    assert r.status_code==status,r.text;return r.json()
def approved(c,operation,details):
    login(c,'admin');row=create(c,operation,details);row=act(c,row,'submit',{'evidence_id':evidence(c,row)})
    login(c,'manager');row=act(c,row,'approve',{'evidence_id':evidence(c,row)});login(c,'admin');return row
def revision(c,code='SYNTH-A',name='纯合成甲经营公司'):
    row=approved(c,'revision',{'code':code,'tax_identifier':('SYNTHETIC0000000'+code[-1]),'legal_name':name,'registered_address':'完全虚构测试地址一号'})
    return next(x for x in config(c)['revisions'] if x['code']==code and x['legal_name']==name)
def store_binding(c,rev):return approved(c,'store_binding',{'revision_id':rev['revision_id'],'effective_from':today().isoformat()})
def account(c,name='虚构银行资金账'):
    r=c.post('/api/flow/master/accounts',json={'values':{'name':name,'account_type':'bank','active':True}});assert r.status_code==201,r.text;return r.json()
def account_details(a,rev,channel='SYNTH-BANK-00001'):
    return {'account_id':a['id'],'expected_account_version':a['version'],'revision_id':rev['revision_id'],'effective_from':today().isoformat(),'holder_name':rev['legal_name'],'channel_type':'bank','channel_identifier':channel,'institution_name':'虚构银行测试支行'}
def setup_policy(c):
    rev=revision(c);store_binding(c,rev);a=account(c);approved(c,'account_binding',account_details(a,rev));cfg=config(c)
    approved(c,'policy',{'binding_id':cfg['store_binding']['id'],'policy_version':1});return rev,a
def actor(db,role='admin'):
    set_scope(db,[1],1);return project_user(db.scalar(select(User).where(User.username==role)),role)
def case(db,user,kind='order',state='draft'):
    row=Case(number='TEST-'+uuid.uuid4().hex,kind=kind,flow_version=2,state=state,title='纯合成原业务',owner_id=user.id,created_by=user.id,business_date=today(),data={});db.add(row);db.flush();return row
def cash(db,user,a,direction='in',amount=101):
    row=CashEntry(doc_no='SYNTH-'+uuid.uuid4().hex,business_date=today(),approval_state='approved',created_by=user.id,direction=direction,category='合成款',amount_cents=amount,account=a['name'],voucher_no='合成凭据');db.add(row);db.flush();return row

def test_independent_review_source_duplicate_stale_and_immutable(client):
    values={'code':'SYNTH-A','tax_identifier':'SYNTHETIC00000001','legal_name':'纯合成主体','registered_address':'虚构测试地址'};key=uuid.uuid4().hex
    row=create(client,'revision',values,key=key);assert create(client,'revision',values,key=key)['id']==row['id']
    proof=evidence(client,row);submitted=act(client,row,'submit',{'evidence_id':proof})
    act(client,submitted,'approve',{'evidence_id':proof},403)
    act(client,row,'cancel',{'reason':'过期版本不能取消'},409)
    login(client,'manager');act(client,submitted,'approve',{'evidence_id':proof},422)
    proof=evidence(client,submitted);key=uuid.uuid4().hex;done=act(client,submitted,'approve',{'evidence_id':proof},key=key)
    assert act(client,submitted,'approve',{'evidence_id':proof},key=key)==done and done['state']=='completed'
    with SessionLocal() as db:
        user=actor(db)
        with svc.authority(db,user):
            assert db.scalar(select(func.count()).select_from(EntityRevision))==1
            item=db.scalar(select(EntityRevision));item.legal_name='禁止改写'
            with pytest.raises(HTTPException):db.flush()

def test_rejected_and_cancelled_have_no_approved_facts(client):
    values={'code':'SYNTH-A','tax_identifier':'SYNTHETIC00000001','legal_name':'纯合成主体','registered_address':'虚构测试地址'}
    row=create(client,'revision',values);row=act(client,row,'submit',{'evidence_id':evidence(client,row)})
    login(client,'manager');assert act(client,row,'reject',{'reason':'实际资料不一致'})['state']=='rejected'
    login(client,'admin');row=create(client,'revision',values);assert act(client,row,'cancel',{'reason':'取消未提交资料'})['state']=='cancelled'
    assert config(client)['revisions']==[]

def test_only_local_authorized_roles_and_no_global_file_leak(client):
    rev=revision(client);store_binding(client,rev);row=create(client,'revision',{'code':'SECOND','tax_identifier':'SYNTHETIC00000002','legal_name':'第二合成主体','registered_address':'虚构地址'})
    client.post('/api/stores',json={'code':'BE-B','name':'纯合成乙店'});client.headers['X-Store-ID']='2'
    assert client.get(f'/api/business-entities/applications/{row["id"]}').status_code==404
    assert len(config(client)['revisions'])==1 and 'source_evidence_id' not in config(client)['revisions'][0]
    client.headers['X-Store-ID']='all';assert client.get('/api/business-entities/configuration').status_code==409
    client.headers['X-Store-ID']='1';login(client,'sales');assert client.get('/api/business-entities/catalog').json()['can_read'] is False
    assert client.get('/api/business-entities/configuration').status_code==403
    with SessionLocal() as db:
        with pytest.raises(HTTPException):db.scalar(select(BusinessEntity))

def test_source_file_must_be_same_case_and_usable(client):
    v={'code':'SYNTH-A','tax_identifier':'SYNTHETIC00000001','legal_name':'纯合成主体','registered_address':'虚构测试地址'}
    a=create(client,'revision',v);b=create(client,'revision',{**v,'code':'SYNTH-B','tax_identifier':'SYNTHETIC00000002'})
    act(client,a,'submit',{'evidence_id':evidence(client,b)},422)
    eid=evidence(client,a)
    from app.file_security_models import FileSecurity
    with SessionLocal() as db:
        # Loss of scan audit is a real historic/missing-state condition.
        from app.file_security import _authority
        with _authority(db):
            scan=db.scalar(select(FileSecurity).where(FileSecurity.file_id==eid));scan.state='quarantined';db.commit()
    act(client,a,'submit',{'evidence_id':eid},409)

def test_handoff_requires_real_manager_and_preserves_overdue(client):
    row=create(client,'revision',{'code':'SYNTH-A','tax_identifier':'SYNTHETIC00000001','legal_name':'純合成主体','registered_address':'虚构测试地址'});row=act(client,row,'submit',{'evidence_id':evidence(client,row)})
    with SessionLocal() as db:
        u=User(username='review2',display_name='第二主管',role='manager',password_hash=PASSWORD_HASH,must_change_password=False);db.add(u);db.flush();uid=u.id;db.add(UserStore(user_id=uid,store_id=1));db.commit()
    row=act(client,row,'reassign',{'task_id':row['tasks'][0]['id'],'assignee_id':uid,'due_date':(today()-timedelta(days=1)).isoformat(),'reason':'主管明确转交'});assert row['tasks'][0]['overdue']
    login(client,'manager');act(client,row,'approve',{'evidence_id':evidence(client,row)},403)
    login(client,'review2');assert act(client,row,'approve',{'evidence_id':evidence(client,row)})['state']=='completed'

def test_store_identity_switch_refuses_cash_stock_and_open_business(client):
    a=revision(client);store_binding(client,a);b=revision(client,'SYNTH-B','纯合成乙经营公司');account_row=account(client)
    with SessionLocal() as db:user=actor(db);cash(db,user,account_row);db.commit()
    request={'revision_id':b['revision_id'],'effective_from':today().isoformat()}
    assert '资金账户余额' in create(client,'store_binding',request,409)['detail']
    with SessionLocal() as db:user=actor(db);cash(db,user,account_row,'out');db.add(Item(sku='ENT-STOCK',name='合成库存',quantity_milli=1000,inventory_value_cents=23));db.commit()
    assert '物资' in create(client,'store_binding',request,409)['detail']
    with SessionLocal() as db:
        user=actor(db);item=db.scalar(select(Item));item.quantity_milli=0;item.inventory_value_cents=0;case(db,user);db.commit()
    assert '未结业务' in create(client,'store_binding',request,409)['detail']

def test_account_actual_channel_cannot_relabel_or_duplicate(client):
    rev=revision(client);store_binding(client,rev);a=account(client);approved(client,'account_binding',account_details(a,rev));b=account(client,'另一资金账')
    assert '不能重复' in create(client,'account_binding',account_details(b,rev),409)['detail']
    assert '实际渠道不可改写' in create(client,'account_binding',account_details(a,rev,'ANOTHER-BANK'),409)['detail']
    assert create(client,'account_binding',{**account_details(a,rev),'holder_name':'不匹配户名'},422)

def test_policy_is_explicit_and_does_not_attribute_old_cases_or_cash(client):
    with SessionLocal() as db:user=actor(db);old=case(db,user,state='completed');oldid=old.id;db.commit()
    rev,a=setup_policy(client)
    cfg=config(client);assert cfg['policy']['case_cursor']>=oldid and cfg['store_binding']['entity']['legal_name']==rev['legal_name']
    with SessionLocal() as db:
        user=actor(db);old=db.scalar(select(Case).where(Case.id==oldid));assert svc.case_entity_snapshot(db,user,old)['status']=='unknown'
        with pytest.raises(HTTPException):svc.freeze_case_entity(db,user,old)
        fresh=case(db,user);context=svc.freeze_case_entity(db,user,fresh);assert context.revision_id==rev['revision_id']
        cash_row=cash(db,user,a);ctx=svc.record_cash_entity(db,user,fresh,cash_row,a['id']);assert svc.record_cash_entity(db,user,fresh,cash_row,a['id']).cash_id==ctx.cash_id
        refunded=cash(db,user,a,'out',50);svc.record_cash_entity(db,user,fresh,refunded,a['id'],original_cash_id=cash_row.id);db.commit()
    with SessionLocal() as db:
        user=actor(db)
        with svc.authority(db,user):assert db.scalar(select(func.count()).select_from(CaseEntityContext))==1 and db.scalar(select(func.count()).select_from(CashEntityContext))==2

def test_hooks_reject_late_missing_foreign_account_and_rollback_atomically(client):
    rev,a=setup_policy(client)
    with SessionLocal() as db:
        user=actor(db);source=case(db,user);flow_event=FlowEvent(case_id=source.id,actor_id=user.id,action='already',label='已有办理',after_state='draft',detail={});db.add(flow_event);db.flush()
        with pytest.raises(HTTPException):svc.freeze_case_entity(db,user,source)
        with pytest.raises(HTTPException):svc.require_case_entity(db,user,source)
        db.rollback()
    with SessionLocal() as db:
        user=actor(db);source=case(db,user);svc.freeze_case_entity(db,user,source);r=cash(db,user,a)
        with pytest.raises(HTTPException):svc.record_cash_entity(db,user,source,r,999999)
        db.rollback()
    with SessionLocal() as db:
        user=actor(db)
        with svc.authority(db,user):assert db.scalar(select(func.count()).select_from(CashEntityContext))==0 and db.scalar(select(func.count()).select_from(CaseEntityContext))==0
        assert db.scalar(select(func.count()).select_from(CashEntry))==0

def test_new_legal_name_revision_never_rewrites_frozen_context(client):
    rev,a=setup_policy(client)
    with SessionLocal() as db:user=actor(db);source=case(db,user);cid=source.id;svc.freeze_case_entity(db,user,source);db.commit()
    approved(client,'revision',{'entity_id':rev['entity_id'],'expected_entity_version':rev['entity_version'],'code':rev['code'],'tax_identifier':rev['tax_identifier'],'legal_name':'合成公司名称第二版','registered_address':'虚构新地址'})
    revised=next(r for r in config(client)['revisions'] if r['revision']==2);store_binding(client,revised)
    with SessionLocal() as db:
        user=actor(db);old=db.scalar(select(Case).where(Case.id==cid));assert svc.case_entity_snapshot(db,user,old)['entity']['legal_name']==rev['legal_name']
        new=case(db,user);svc.freeze_case_entity(db,user,new);assert svc.case_entity_snapshot(db,user,new)['entity']['legal_name']=='合成公司名称第二版'

def test_parallel_approvals_use_store_control_cas_and_require_recheck(client):
    values={'code':'SYNTH-A','tax_identifier':'SYNTHETIC00000001','legal_name':'合成主体一','registered_address':'虚构地址'}
    a=create(client,'revision',values);a=act(client,a,'submit',{'evidence_id':evidence(client,a)})
    b=create(client,'revision',{**values,'code':'SYNTH-B','tax_identifier':'SYNTHETIC00000002'});b=act(client,b,'submit',{'evidence_id':evidence(client,b)})
    login(client,'manager');act(client,a,'approve',{'evidence_id':evidence(client,a)})
    assert '提交后' in act(client,b,'approve',{'evidence_id':evidence(client,b)},409)['detail']
    assert len(config(client)['revisions'])==1  # local approved metadata, never the unrelated global registry


def test_enable_refuses_active_unknown_history_and_production_default_is_closed(client,monkeypatch):
    rev=revision(client);store_binding(client,rev);a=account(client);approved(client,'account_binding',account_details(a,rev));binding=config(client)['store_binding']
    with SessionLocal() as db:user=actor(db);active=case(db,user);activeid=active.id;db.commit()
    assert '未结业务' in create(client,'policy',{'binding_id':binding['id']},409)['detail']
    from dataclasses import replace
    # Only the module's policy setting changes; never start a production service
    # with synthetic scanner settings or a company database.
    from types import SimpleNamespace
    monkeypatch.setattr(svc,'settings',SimpleNamespace(environment='production',timezone='Asia/Shanghai'))
    with SessionLocal() as db:
        user=actor(db);fresh=case(db,user)
        for value in (None,False,True):
            with pytest.raises(HTTPException):svc.freeze_case_entity(db,user,fresh,required=value)
        cfgcase=db.scalar(select(Case).where(Case.kind=='business_entity'));assert svc.freeze_case_entity(db,user,cfgcase) is None
        r=cash(db,user,a)
        with pytest.raises(HTTPException):svc.record_cash_entity(db,user,fresh,r,a['id'])
        assert svc.case_entity_snapshot(db,user,db.scalar(select(Case).where(Case.id==activeid)))['status']=='unknown'


def test_restore_nonempty_source_and_tamper_refusal(client):
    from app.business_entity_integrity import validate_business_entities
    rev,a=setup_policy(client)
    with SessionLocal() as db:
        user=actor(db);source=case(db,user);svc.freeze_case_entity(db,user,source);r=cash(db,user,a);svc.record_cash_entity(db,user,source,r,a['id']);db.commit()
    with sqlite3.connect(engine.url.database) as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);result=validate_business_entities(restored)
        assert result=={'verified_entity_applications':4,'verified_entity_cases':1,'verified_entity_cash':1}
        restored.execute("UPDATE business_entity_revisions SET legal_name='篡改名称'")
        with pytest.raises(ValueError,match='批准资料'):validate_business_entities(restored)


def test_two_simultaneous_approvals_only_one_store_version_wins(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    values={'code':'SYNTH-A','tax_identifier':'SYNTHETIC00000001','legal_name':'合成主体一','registered_address':'虚构地址'}
    orders=[]
    for suffix in ('A','B'):
        row=create(client,'revision',{**values,'code':'SYNTH-'+suffix,'tax_identifier':'SYNTHETIC0000000'+suffix});orders.append(act(client,row,'submit',{'evidence_id':evidence(client,row)}))
    login(client,'manager');proofs=[evidence(client,row) for row in orders];barrier=Barrier(2)
    def run(index):
        with SessionLocal() as db:
            user=actor(db,'manager')
            with svc.authority(db,user):svc.control(db)
            barrier.wait(timeout=10)
            try:return svc.command(db,user,orders[index]['id'],uuid.uuid4().hex,orders[index]['version'],'approve',{'evidence_id':proofs[index]})['state']
            except HTTPException as ex:return ex.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,[0,1]))
    assert sorted(map(str,results))==['409','completed']


@pytest.mark.parametrize('kind',['material_transfer','vehicle_transfer','interstore_clearing'])
def test_coordinated_new_counterparty_case_freezes_without_cross_store_read(client,kind):
    # Configure both stores through actual independent approvals; the initiator
    # below only has an inventory role in store A.
    rev,a=setup_policy(client)
    client.post('/api/stores',json={'code':'ENTITY-B','name':'合成乙店'})
    with SessionLocal() as db:
        manager=db.scalar(select(User).where(User.username=='manager'));db.add(UserStore(user_id=manager.id,store_id=2,role='manager'));db.commit()
    client.headers['X-Store-ID']='2';revb=revision(client,'SYNTH-B','合成乙经营主体');store_binding(client,revb);ab=account(client,'乙店账户');approved(client,'account_binding',account_details(ab,revb,'SYNTH-BANK-B'));approved(client,'policy',{'binding_id':config(client)['store_binding']['id']});client.headers['X-Store-ID']='1'
    from app.transfer_service import authority as transfer_authority,coordination_scope
    from app.transfer_models import MaterialTransfer
    from app.vehicle_transfer_models import VehicleTransfer
    from app.reconciliation_service import authority as clearing_authority,coordination
    from app.reconciliation_models import ClearingBucket,ClearingOrder
    from app.models import Vehicle
    role='finance' if kind=='interstore_clearing' else 'inventory';auth=clearing_authority if kind=='interstore_clearing' else transfer_authority;scope=coordination if kind=='interstore_clearing' else coordination_scope
    with SessionLocal() as db:
        user=actor(db,role);pairs={}
        with auth(db,user,{role}):
            for sid in (1,2):
                with scope(db,sid,(1,2)):
                    r=Case(number='COORD-'+uuid.uuid4().hex,kind=kind,flow_version=2,state='approval',title='合成双方调拨',owner_id=2,created_by=user.id,business_date=today(),data={});db.add(r);svc.note_coordinated_case(db,user,r);db.flush();pairs[sid]=r
            if kind=='interstore_clearing':
                bucket=ClearingBucket(origin_kind='material',debtor_origin_id=100,creditor_origin_id=101,payer_store_id=1,receiver_store_id=2,total_cents=100,reserved_cents=100,settled_cents=0);db.add(bucket);db.flush()
                transfer=ClearingOrder(bucket_id=bucket.id,payer_store_id=1,receiver_store_id=2,payer_case_id=pairs[1].id,receiver_case_id=pairs[2].id,amount_cents=100,requested_by=user.id,due_date=today(),reason='合成固定双方原清算')
            else:
                values={'number':'COORD-'+uuid.uuid4().hex,'from_store_id':1,'to_store_id':2,'from_case_id':pairs[1].id,'to_case_id':pairs[2].id,'requested_by':user.id,'reason':'合成双方来源','due_date':today()}
                if kind=='vehicle_transfer':
                    vehicle=Vehicle(doc_no='SYNTH-V',business_date=today(),created_by=user.id,vin='LFV2A21K9J1234531',brand='合成',model='合成车辆',purchase_cost_cents=100,list_price_cents=100);db.add(vehicle);db.flush()
                    transfer=VehicleTransfer(**values,source_vehicle_id=vehicle.id,vin=vehicle.vin,snapshot={'model':'合成车辆'})
                else:transfer=MaterialTransfer(**values)
            db.add(transfer);db.flush()
            for sid in (1,2):
                with scope(db,sid,(1,2)):
                    assert svc.freeze_coordinated_case(db,user,pairs[sid],transfer) is None
                    if sid==2:
                        with pytest.raises(HTTPException):svc.configuration(db,user)
            db.commit()
            with scope(db,2,(1,2)):
                with pytest.raises(HTTPException):svc.freeze_coordinated_case(db,user,pairs[2],transfer)
    with SessionLocal() as db:
        user=actor(db)
        with svc.authority(db,user):assert db.scalar(select(func.count()).select_from(CaseEntityContext))==1
        set_scope(db,[2],2)
        with svc.authority(db,user):assert db.scalar(select(func.count()).select_from(CaseEntityContext))==1


def test_old_unknown_case_new_cash_refuses_even_after_policy_in_trial(client):
    with SessionLocal() as db:user=actor(db);old=case(db,user,state='completed');oid=old.id;db.commit()
    rev,a=setup_policy(client)
    with SessionLocal() as db:
        user=actor(db);source=db.scalar(select(Case).where(Case.id==oid));r=cash(db,user,a)
        with pytest.raises(HTTPException):svc.record_cash_entity(db,user,source,r,a['id'])
        with pytest.raises(HTTPException):svc.require_account_entity(db,user,source,a['id'],today())


def test_frozen_migration_upgrade_empty_downgrade_roundtrip(tmp_path):
    import os,sys,subprocess
    target=tmp_path/'entity-migration.sqlite'
    env={**os.environ,'DATABASE_URL':'sqlite:///'+target.as_posix(),'APP_ENV':'test','SCHEDULER_ENABLED':'false','SCHEDULER_MODE':'off','ALLOW_AI_EXTERNAL':'false','DEEPSEEK_API_KEY':'','FILE_SCAN_MODE':'structure_only'}
    for command in (['upgrade','l248_business_entities'],['downgrade','k137_user_access'],['upgrade','l248_business_entities']):
        result=subprocess.run([sys.executable,'-m','alembic',*command],env=env,capture_output=True,text=True,encoding='utf-8')
        assert result.returncode==0,result.stderr
    with sqlite3.connect(target) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='l248_business_entities'
        assert len(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'business_entit%'").fetchall())==16
        assert not db.execute('PRAGMA foreign_key_check').fetchone()


def test_derived_return_keeps_original_entity_after_store_identity_changes(client):
    from app.aftercare_models import AftercareOrder
    from app.business_entity_integrity import validate_business_entities
    rev,a=setup_policy(client)
    with SessionLocal() as db:
        user=actor(db);original=case(db,user,state='completed');oid=original.id;svc.freeze_case_entity(db,user,original)
        original_cash=cash(db,user,a);cashid=original_cash.id;svc.record_cash_entity(db,user,original,original_cash,a['id'])
        spent=cash(db,user,a,'out');svc.record_cash_entity(db,user,original,spent,a['id']);db.commit()
    newer=revision(client,'SYNTH-B','新独立合成经营主体');store_binding(client,newer)
    with SessionLocal() as db:
        user=actor(db);original=db.scalar(select(Case).where(Case.id==oid));new=case(db,user);svc.freeze_case_entity(db,user,new)
        after=case(db,user,kind='aftercare');db.add(AftercareOrder(id=after.id,source_case_id=oid,scenario='sale_termination',reason='明确原责任来源',requested_by=user.id));db.flush()
        context=svc.freeze_derived_case_entity(db,user,after,original)
        assert context.source_case_id==oid and context.derived_kind=='aftercare' and context.revision_id==rev['revision_id']
        assert svc.case_entity_snapshot(db,user,new)['entity']['entity_id']==newer['entity_id']
        assert svc.case_entity_snapshot(db,user,after)['entity']['entity_id']==rev['entity_id']
        r=cash(db,user,a,'out',50);svc.record_cash_entity(db,user,after,r,a['id'],original_cash_id=cashid);db.commit()
    with sqlite3.connect(engine.url.database) as db:
        assert validate_business_entities(db)['verified_entity_cases']==3
        db.execute('UPDATE business_entity_case_contexts SET source_case_id=? WHERE case_id=?',(new.id,after.id))
        with pytest.raises(ValueError,match='派生主体'):validate_business_entities(db)


def test_arbitrary_new_business_cannot_borrow_old_entity_and_unknown_source_refused(client):
    from app.aftercare_models import AftercareOrder
    with SessionLocal() as db:user=actor(db);legacy=case(db,user,state='completed');lid=legacy.id;db.commit()
    rev,a=setup_policy(client)
    with SessionLocal() as db:
        user=actor(db);original=case(db,user,state='completed');svc.freeze_case_entity(db,user,original)
        ordinary=case(db,user)
        with pytest.raises(HTTPException,match='有据原单派生'):svc.freeze_case_entity(db,user,ordinary,source_case=original)
        after=case(db,user,kind='aftercare');db.add(AftercareOrder(id=after.id,source_case_id=lid,scenario='sale_termination',reason='旧未知原责任',requested_by=user.id));db.flush()
        with pytest.raises(HTTPException,match='实际派生关系'):svc.freeze_derived_case_entity(db,user,after,original)
        legacy=db.scalar(select(Case).where(Case.id==lid))
        with pytest.raises(HTTPException,match='主体未知'):svc.freeze_derived_case_entity(db,user,after,legacy)


def test_multiple_source_batch_rejects_mixed_entity_but_accepts_revision_change(client):
    rev,a=setup_policy(client)
    with SessionLocal() as db:user=actor(db);old=case(db,user,state='completed');oid=old.id;svc.freeze_case_entity(db,user,old);db.commit()
    approved(client,'revision',{'entity_id':rev['entity_id'],'expected_entity_version':rev['entity_version'],'code':rev['code'],'tax_identifier':rev['tax_identifier'],'legal_name':'同主体合成新名称','registered_address':'同主体合成新地址'})
    v2=next(r for r in config(client)['revisions'] if r['revision']==2);store_binding(client,v2)
    with SessionLocal() as db:
        user=actor(db);old=db.scalar(select(Case).where(Case.id==oid));same=case(db,user,state='completed');sameid=same.id;svc.freeze_case_entity(db,user,same)
        assert svc.assert_same_case_entities(db,user,[old,same])==rev['entity_id'];db.commit()
    different=revision(client,'SYNTH-B','完全另一合成主体');store_binding(client,different)
    with SessionLocal() as db:
        user=actor(db);old=db.scalar(select(Case).where(Case.id==oid));new=case(db,user);svc.freeze_case_entity(db,user,new)
        with pytest.raises(HTTPException,match='同一已确认经营主体'):svc.assert_same_case_entities(db,user,[old,new])
