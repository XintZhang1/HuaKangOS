"""Latest deployment-source graphs, created with guarded synthetic APIs."""
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User,UserStore
from tests.conftest import login
from tests import test_opening_import as opening,test_recharge_bundles as bundle


def seed(client):
    from app.reconciliation_service import CURRENT_DEFINITION_VERSION
    login(client);client.headers['X-Store-ID']='1'
    created=client.post('/api/stores',json={'code':'PGOPEN','name':'合成全新期初店','active':True})
    assert created.status_code==201,created.text
    sid=created.json()['id']
    with SessionLocal() as db:
        for user in db.scalars(select(User)):
            if not db.scalar(select(UserStore.user_id).where(UserStore.store_id==sid,UserStore.user_id==user.id)):
                db.add(UserStore(store_id=sid,user_id=user.id,role=None if user.role=='admin' else user.role))
        db.commit()
    client.headers['X-Store-ID']=str(sid)
    source,_=opening.source_data(client)
    reviewed,_=opening.reviewed(client,source);opening.confirm(client,reviewed)
    from tests import test_reconciliation as reconciliation
    login(client,'finance')
    statement=reconciliation.batch(client)
    assert statement['definition_version']==CURRENT_DEFINITION_VERSION
    assert {'opening_account_entries','opening_vehicle_entries','opening_imports',
        'opening_attestations'}<={x['source'] for x in statement['manifest']}
    login(client);client.headers['X-Store-ID']='1'
    a,z,member,rule,purchase=bundle.setup(client)
    actual=bundle.approve(client,bundle.refund(client,a,purchase,1))
    bundle.command(client,actual,'execute',bundle.proof(client,actual,account_id=a['account_id'],reference='PG-COMBO-REFUND'))
    login(client);client.headers['X-Store-ID']='1'
    # Keep a second approved share unexecuted to validate all original holds.
    bundle.approve(client,bundle.refund(client,a,purchase,1))
    login(client);client.headers['X-Store-ID']='1'
