"""Standalone synthetic policy-before-opening seed with unique identities/VIN."""
import uuid
from datetime import timedelta
from app.db import today
from tests.conftest import login
from tests.postgres_wave8 import fresh_store
from tests import test_business_entities as be,test_opening_import as oi


def seed(c):
    token=uuid.uuid4().hex.upper();sid=fresh_store(c,'PGOPEN'+token[:10])
    be.approved(c,'revision',{'code':'PGOPEN-'+token[:12],'tax_identifier':'SYNTH'+token[:25],
        'legal_name':'完全合成期初经营主体'+token[:8],'registered_address':'合成隔离库期初核验地址'})
    rev=next(r for r in be.config(c)['revisions'] if r['code']=='PGOPEN-'+token[:12]);be.store_binding(c,rev)
    account=be.account(c,'合成期初批准账户'+token[:10]);be.approved(c,'account_binding',be.account_details(account,rev,'PG-OPEN-BANK-'+token))
    be.approved(c,'policy',{'binding_id':be.config(c)['store_binding']['id'],'policy_version':1})
    source,_=oi.source_data(c);source['opening_date']=(today()-timedelta(days=3)).isoformat();source['source_reference']='合成原期初-'+token
    source['accounts']=[{'account_id':account['id'],'name':account['name'],'account_type':account['account_type'],'opening_balance_cents':500001,'source_reference':'合成原银行核对-'+token}]
    source['vehicles'][0]['vin']='LD'+token[:15]
    row,_=oi.reviewed(c,source);done=oi.confirm(c,row)
    balances=c.get('/api/opening-import/account-balances');assert balances.status_code==200,balances.text
    balance=balances.json()['items'][0];assert balance['account_id']==account['id'] and (balance['opening_cents'],balance['in_cents'],balance['out_cents'],balance['balance_cents'])==(500001,0,0,500001)
    login(c);c.headers['X-Store-ID']='1'
    return {'store_id':sid,'case_id':done['case_id'],'account_id':account['id'],'revision_id':rev['revision_id']}
