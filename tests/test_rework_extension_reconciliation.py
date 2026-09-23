"""The receiving store freezes its responsibility split, not another store's file ledger."""
import copy,csv,io,json,sqlite3
from decimal import Decimal
import pytest
from app.backup_integrity import validate_sqlite
from app import reconciliation_service as service
from app.rework_extension_sources import SOURCE_FIELDS
from tests.conftest import TEST_DIR
from tests import test_rework_extensions as rework,test_reconciliation as monthly
from tests.test_repair_orders import cmd as repair_cmd,receive
from tests.test_workflow import evidence


def settled(client):
    d=rework.fixture(client,True)
    row=rework.ready(client,d,rework.authorized(client,d,rework.quoted(client,d,rework.converted(client,d))))
    rework.switch(client,d['names']['manager'],d['sid'])
    row=repair_cmd(client,row,'allocate',{'labor_cost_cents':100,'evidence_id':evidence(client,row),'allocations':rework.split(d)})
    rework.switch(client,d['names']['finance'],d['sid'])
    customer=next(a for a in row['allocations'] if a['payer_type']=='customer')
    row=receive(client,row,customer,300,d['account'])
    rework.switch(client,d['names']['service'],d['sid'])
    row=repair_cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    rework.switch(client,d['names']['finance'],d['sid'])
    return d,row


def test_local_monthly_rework_split_never_copies_source_cash_or_files(client,monkeypatch):
    d,row=settled(client)
    original=service.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(service,'snapshot',lambda db,user,start,end,definition_version=15:original(db,user,start,end,15))
        old=monthly.batch(client)
    assert not set(SOURCE_FIELDS)&old['summary'].keys()
    assert old['summary']['period_cash_in_cents']==300
    new=monthly.cmd(client,old,'recalculate',{'reason':'冻结本店原责任和本次新增收费的原分类'})
    assert new['definition_version']==service.CURRENT_DEFINITION_VERSION
    assert new['summary']['period_cash_in_cents']==300 and new['summary']['period_cash_out_cents']==0
    for name,count in [('rework_extensions',1),('rework_quote_scopes',1),('rework_line_scopes',2)]:
        assert new['summary'][name]['count']==count and new['summary'][name]['amount_cents']==0
    sources=[e for e in new['manifest'] if e['source'] in SOURCE_FIELDS]
    assert all(e['data']['store_id']==d['sid'] and not {'evidence_id','source_case_id','source_case_version','files'}&e['data'].keys() for e in sources)
    assert not any(e['source'].startswith('rework_grant') or e['source']=='rework_source_grants' for e in new['manifest'])
    assert all(e['data']['store_id']==d['sid'] for e in new['manifest'] if e['source']=='cash_entries')
    report=client.get('/api/flow/analytics');assert report.status_code==200,report.text
    report=report.json()
    assert report['metrics']['repair_cents']==300
    for dataset,chart_id,column in [('repair_settlements','repair_value',4),('cash','cash_trend',5)]:
        table=report['tables'][dataset]
        exported=client.get('/api/flow/analytics/export',params={'dataset':dataset})
        assert exported.status_code==200,exported.text
        records=list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))))
        assert records[0]==table['headers'] and len(records[1:])==len(table['rows'])==1
        assert sum(Decimal(r[column].removeprefix("'"))*100 for r in records[1:])==300
        plotted=next(c for c in report['charts'] if c['id']==chart_id)
        assert sum(plotted['series'][0]['values'])==300
    assert report['tables']['repair_settlements']['rows'][0]['route']=={'type':'case','id':row['id']}
    assert monthly.get(client,old)['manifest']==old['manifest']
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);result=validate_sqlite(restored)
        assert result['verified_reconciliation_batches']==2


@pytest.mark.parametrize('tamper',['classification','old_definition','summary','central_authority'])
def test_rehashed_statement_cannot_reassign_rework_liability_or_expose_central_grant(client,tamper):
    d,row=settled(client);batch=monthly.batch(client)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);validate_sqlite(restored)
        manifest=copy.deepcopy(batch['manifest']);summary=copy.deepcopy(batch['summary'])
        if tamper=='classification':next(e for e in manifest if e['source']=='rework_line_scopes')['data']['charge_scope']='customer_extra'
        elif tamper=='old_definition':summary['definition_version']=15
        elif tamper=='summary':summary['rework_quote_scopes']['amount_cents']=600
        else:
            key=d['grant']['id'];manifest.append({'key':'rework_source_grants:'+str(key),'source':'rework_source_grants','source_id':key,'case_id':None,'basis':'current','data':{'id':key,'store_id':d['sid'],'evidence_id':d['source_proof']}})
        restored.execute('UPDATE reconciliation_batches SET manifest=?,summary=?,digest=? WHERE id=?',(json.dumps(manifest),json.dumps(summary),service.digest({'manifest':manifest,'summary':summary}),batch['id']))
        with pytest.raises(ValueError):validate_sqlite(restored)
