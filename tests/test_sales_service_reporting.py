"""Real settlement sources reconcile across business, cash, charts, exports and versions."""
from app.reconciliation_service import CURRENT_DEFINITION_VERSION
import csv,io,json,sqlite3
from datetime import timedelta
import pytest
from app.db import today
from tests import test_insurance_orders as insurance,test_addon_orders as addon,test_sales_quotes as quotes,test_reconciliation as monthly
from tests.test_procurement import bank
from tests.test_service_analytics import report
from tests.conftest import TEST_DIR,login
from app.backup_integrity import validate_sqlite
from app import reconciliation_service as reconciliation
from app.reconciliation_backup_integrity import validate_reconciliation_sqlite


def assert_table(c,key,amount):
    data=report(c);table=data['tables'][key]
    assert sum(row['amount_cents'] for row in table['rows'])==amount
    chart=next(ch for ch in data['charts'] if ch['id']==key)
    assert sum(chart['series'][0]['values'])==amount
    result=c.get('/api/flow/analytics/export',params={'dataset':key});assert result.status_code==200,result.text
    rows=list(csv.reader(io.StringIO(result.content.decode('utf-8-sig'))))
    assert rows[0]==table['headers']
    assert [[v.removeprefix("'") for v in row] for row in rows[1:]]==[[str(v) for v in row['values']] for row in table['rows']]
    return data


def test_insurance_current_principal_approved_income_cash_and_period_are_separate(client):
    c=client;row,_,_=insurance.setup(c)
    assert report(c)['metrics']['receivable_cents']==0
    row=insurance.ready(c,row)
    assert report(c)['metrics']['receivable_cents']==10001
    a=bank(c);row=insurance.cash(c,row,'receive',10001,a);row=insurance.cash(c,row,'disburse',10001,a,tender_id=row['tenders'][0]['id']);row=insurance.issued(c,row)
    data=assert_table(c,'insurance_commission_facts',0)
    assert data['metrics']['recorded_business_net_cents']==0
    assert data['metrics']['insurance_issued_premium_cents']==10001
    assert data['tables']['insurance_completed']['rows']==[]
    row=insurance.commission(c,row,499)
    data=assert_table(c,'insurance_commission_facts',499)
    assert data['metrics']['receivable_cents']==499
    row=insurance.cash(c,row,'commission_receive',499,a,confirmation_id=row['commissions'][-1]['id'])
    data=assert_table(c,'insurance_commission_cash',499)
    assert data['metrics']['cash_in_cents']==10500 and data['metrics']['cash_out_cents']==10001
    assert data['metrics']['recorded_business_net_cents']==499
    past=(today()-timedelta(days=1)).isoformat()
    prior=report(c,date_from=past,date_to=past)
    assert prior['tables']['insurance_policy_facts']['rows']==prior['tables']['insurance_commission_facts']['rows']==[]
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:assert validate_sqlite(db)['verified_insurance_orders']==1
    login(c,'sales');assert c.get('/api/flow/analytics/export',params={'dataset':'insurance_commission_facts'}).status_code==403


def test_addon_actual_acceptance_and_original_return_reconcile_without_old_double_count(client):
    c=client;row,items,work,source,vin,a=addon.completed(c)
    data=assert_table(c,'addon_actual_facts',1197)
    assert data['tables']['addon_completed']['rows']==[] and data['metrics']['recorded_business_net_cents']==1197
    row=addon.resolve(c,addon.resolve(c,addon.resolution(c,row,'return'),'resolution_approve'),'resolution_consent');row=addon.resolve(c,row,'return_receive',passed=True)
    reduction=row['totals']['return_reduction_cents']
    data=assert_table(c,'addon_actual_facts',1197-reduction)
    assert data['metrics']['recorded_business_net_cents']==1197-reduction
    assert data['metrics']['cash_in_cents']==1197 and data['metrics']['cash_out_cents']==0


def test_monthly_v7_freezes_new_original_values_and_preserves_v6_definition(client,monkeypatch):
    from tests.test_procurement_costs import mixed,retail_take,returned
    c=client;item,first,second=mixed(c);retail_take(c,item);returned(c,first)
    original=reconciliation.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(reconciliation,'snapshot',lambda db,user,start,end,definition_version=6:original(db,user,start,end,6))
        old=monthly.batch(c)
    assert old['definition_version']==6
    assert not any(x['source']=='procurement_return_valuations' for x in old['manifest'])
    new=monthly.cmd(c,old,'recalculate',{'reason':'核对原采购冲款与库存均价差额'})
    assert new['definition_version']==CURRENT_DEFINITION_VERSION
    frozen=next(x for x in new['manifest'] if x['source']=='procurement_return_valuations')
    assert frozen['data']['variance_cents']==450
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);validate_sqlite(restored)
        manifest=json.loads(json.dumps(new['manifest']));next(x for x in manifest if x['key']==frozen['key'])['data']['variance_cents']=451
        restored.execute('UPDATE reconciliation_batches SET manifest=?,digest=? WHERE id=?',(json.dumps(manifest),reconciliation.digest({'manifest':manifest,'summary':new['summary']}),new['id']))
        with pytest.raises(ValueError,match='不可变原始'):validate_reconciliation_sqlite(restored)


def test_new_sales_v4_creates_three_typed_domains_only_after_current_customer_consent(client):
    from tests.test_workflow import action,evidence
    c=client;row,quote,car,_=quotes.setup(c);row=quotes.ready(c,row,car)
    assert row['flow_version']==4 and not [r for r in row['children'] if r['kind'] in {'addon','insurance','agency'}]
    row=quotes.propose(c,row,{**quote,'addon':True,'insurance':True,'agency':True})
    row=quotes.approve(c,row)
    assert not [r for r in quotes.detail(c,row)['children'] if r['kind'] in {'addon','insurance','agency'}]
    row=quotes.sign(c,row);children={r['kind']:r for r in row['children'] if r['kind'] in {'addon','insurance','agency'}}
    assert set(children)=={'addon','insurance','agency'} and all(r['flow_version']==3 for r in children.values())
    for kind,url in [('addon','addon-orders'),('insurance','insurance-orders'),('agency','service-orders')]:
        response=c.get('/api/'+url+'/'+str(children[kind]['id']));assert response.status_code==200,response.text
    action(c,row,'dispatch',{'evidence_id':evidence(c,row)},409)
    quotes.propose(c,row,{**quote,'addon':False,'insurance':True,'agency':True},409)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:validate_sqlite(db)
