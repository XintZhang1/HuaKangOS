"""A reviewed empty-store policy can precede real opening balances/inventory."""
import copy,json,sqlite3,uuid
from datetime import timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import select,func
from app.db import SessionLocal,today
from app.models import CashEntry,Vehicle
from app.flow_models import Account,Case,Customer,Item,FlowEvent
from app.opening_import_models import OpeningAccountEntry,OpeningVehicleEntry
from app.opening_import_backup_integrity import validate_opening_import
from app.business_entity_integrity import validate_business_entities
from app import business_entity_service as entities
from tests import test_business_entities as be,test_opening_import as oi
from tests.conftest import login,TEST_DIR


def source(c):
    rev,a=be.setup_policy(c);data,loc=oi.source_data(c)
    assert data['accounts']==[]
    data['accounts']=[{'account_id':a['id'],'name':a['name'],'account_type':a['account_type'],'opening_balance_cents':500001,'source_reference':'合成原期初银行核对表'}]
    data['opening_date']=(today()-timedelta(days=30)).isoformat()
    return data,rev,a


def restored():
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as copy:
        original.backup(copy);return validate_opening_import(copy),validate_business_entities(copy)


def test_production_policy_then_three_role_opening_reuses_approved_account_and_trial_rolls_back(client,monkeypatch):
    data,rev,a=source(client)
    monkeypatch.setattr(entities,'settings',SimpleNamespace(environment='production',timezone='Asia/Shanghai'))
    preflight_key=uuid.uuid4().hex;preflight=oi.preflight(client,data,preflight_key);row=preflight['batch'];assert row
    before=row;key=uuid.uuid4().hex;row=oi.act(client,row,'trial',{'evidence_id':oi.proof(client,row)},key=key)
    assert oi.preflight(client,data,preflight_key)==preflight
    assert client.get('/api/opening-import/batches/'+str(row['case_id'])).json()['status']=='trial_passed'
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Account))==1
        assert db.scalar(select(Account.id))==a['id']
        for model in (Customer,Item,Vehicle,OpeningAccountEntry,OpeningVehicleEntry,CashEntry):assert db.scalar(select(func.count()).select_from(model))==0
        event=db.scalar(select(FlowEvent).where(FlowEvent.case_id==row['case_id'],FlowEvent.action=='opening_preflight'))
        assert event.detail['account_context']['accounts'][0]['account_id']==a['id']
        assert event.detail['account_context']['revision_id']==rev['revision_id']
    # Use the existing real three-role path from this already-tested batch.
    login(client,'manager');row=oi.act(client,row,'approve',{'evidence_id':oi.proof(client,row)})
    login(client,'inventory');row=oi.act(client,row,'verify_inventory',{'evidence_id':oi.proof(client,row),'observed':oi.inventory_observation(oi.Source.model_validate(data))})
    assert row['accounts']==[]
    login(client,'finance');row=oi.act(client,row,'verify_finance',{'evidence_id':oi.proof(client,row,'receipt'),'observed':oi.finance_observation(oi.Source.model_validate(data))})
    login(client,'manager');key=uuid.uuid4().hex;done=oi.confirm(client,row,key=key);assert oi.confirm(client,row,key=key)==done
    oi.confirm(client,row,status=409)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Account))==1 and db.scalar(select(OpeningAccountEntry.account_id))==a['id']
        assert db.scalar(select(func.count()).select_from(CashEntry))==0
        assert db.scalar(select(Case.business_date).where(Case.id==row['case_id']))==today()
        assert db.scalar(select(OpeningAccountEntry.business_date)).isoformat()==data['opening_date']
    balance=client.get('/api/opening-import/account-balances').json()['items'][0]
    assert (balance['opening_cents'],balance['in_cents'],balance['out_cents'],balance['balance_cents'])==(500001,0,0,500001)
    assert restored()[0]['verified_opening_imports']==1
    assert not oi.preflight(client,data)['valid']


@pytest.mark.parametrize('fault',['missing','wrong','name','type','duplicate','unbound'])
def test_policy_opening_account_mapping_errors_are_explicit_rows(client,fault):
    data,rev,a=source(client)
    if fault=='missing':data['accounts'][0].pop('account_id')
    elif fault=='wrong':data['accounts'][0]['account_id']=999999
    elif fault=='name':data['accounts'][0]['name']='不同的合成账户名称'
    elif fault=='type':data['accounts'][0]['account_type']='cash'
    elif fault=='duplicate':data['accounts'].append(copy.deepcopy(data['accounts'][0]))
    else:
        other=be.account(client,'未批准的合成账户');data['accounts'][0].update(account_id=other['id'],name=other['name'])
    result=oi.preflight(client,data);assert not result['valid'] and any(x['section']=='accounts' and x['row']>=1 for x in result['errors'])
    with SessionLocal() as db:assert not db.scalar(select(OpeningAccountEntry.id)) and not db.scalar(select(Case.id).where(Case.kind=='opening_import'))


@pytest.mark.parametrize('change',['version','binding','business'])
def test_preflight_account_or_business_change_refuses_without_partial_opening(client,change):
    data,rev,a=source(client);row=oi.preflight(client,data)['batch']
    if change=='version':
        with SessionLocal() as db:account=db.scalar(select(Account).where(Account.id==a['id']));account.version+=1;db.commit()
    elif change=='binding':
        be.approved(client,'account_binding',be.account_details(a,rev))
    else:
        from tests.test_workflow import order
        order(client)
    oi.act(client,row,'trial',{'evidence_id':oi.proof(client,row)},status=409)
    with SessionLocal() as db:assert not db.scalar(select(OpeningAccountEntry.id)) and not db.scalar(select(Item.id))
    assert oi.act(client,row,'cancel')['status']=='cancelled'


def test_no_policy_keeps_creation_only_contract_and_does_not_accept_account_id(client):
    data,_=oi.source_data(client);data['accounts'][0]['account_id']=1
    result=oi.preflight(client,data);assert not result['valid'] and '不接收账户编号' in result['errors'][0]['message']


def test_opening_restore_refuses_changed_approved_account_mapping(client):
    data,rev,a=source(client);row,_=oi.reviewed(client,data);oi.confirm(client,row)
    assert restored()[0]['verified_opening_imports']==1
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as copy:
        original.backup(copy)
        eid,raw=copy.execute("SELECT id,detail FROM flow_events WHERE action='opening_preflight'").fetchone();detail=json.loads(raw);detail['account_context']['accounts'][0]['account_binding_id']=999999
        copy.execute('UPDATE flow_events SET detail=? WHERE id=?',(json.dumps(detail),eid))
        with pytest.raises(ValueError,match='批准渠道'):validate_opening_import(copy)


def test_real_other_store_account_cannot_be_recognized_by_name(client):
    data,rev,a=source(client);created=client.post('/api/stores',json={'code':'OTHER-OPENING','name':'合成另外开户门店'});assert created.status_code==201,created.text
    client.headers['X-Store-ID']=str(created.json()['id']);other=be.account(client,'另店不可泄露账户')
    client.headers['X-Store-ID']='1';data['accounts'][0]['account_id']=other['id']
    result=oi.preflight(client,data);assert not result['valid']
    assert result['errors'][0]['section']=='accounts' and '另店不可泄露账户' not in json.dumps(result,ensure_ascii=False)
    with SessionLocal() as db:assert not db.scalar(select(OpeningAccountEntry.id))


def test_account_reapproval_after_all_witnesses_blocks_confirmation_and_remains_cancelable(client):
    data,rev,a=source(client);row,_=oi.reviewed(client,data)
    be.approved(client,'account_binding',be.account_details(a,rev));login(client,'manager')
    result=oi.confirm(client,row,status=409);assert '批准渠道' in result['detail']
    with SessionLocal() as db:assert not db.scalar(select(OpeningAccountEntry.id)) and not db.scalar(select(Item.id))
    assert oi.act(client,row,'cancel')['status']=='cancelled'


def test_unique_pg_seed_helper_uses_own_store_and_recoverable_sources(client):
    from tests.postgres_entity_opening import seed
    result=seed(client);assert result['store_id']!=1
    assert restored()[0]['verified_opening_imports']==1
