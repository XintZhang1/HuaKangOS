"""Approved local prices remain original quote provenance across reports and restores."""
import copy,csv,io,json,sqlite3
from decimal import Decimal
import pytest
from app import reconciliation_service as service
from app.backup_integrity import validate_sqlite
from app.reconciliation_v18 import SOURCE_FIELDS
from tests.conftest import TEST_DIR,login
from tests.test_workflow import evidence
from tests import test_member_pricing as pricing,test_repair_orders as repair,test_reconciliation as monthly


def settled(client):
    row,item,work,customer=repair.setup(client)
    membership=pricing.member(client,customer)
    rule=pricing.rule(client,membership,[pricing.scope('repair','work',work,8000),pricing.scope('repair','part',item,9000)])
    row=repair.authorize(client,pricing.quote(client,row,item,work,rule))
    row=repair.cmd(client,row,'start',{'result':'按本版会员价格及客户授权实际施工'})
    row=repair.issue(client,row,1000)
    row=repair.cmd(client,row,'finish',{'result':'已实际完成授权工时及配件安装'})
    row=repair.cmd(client,row,'quality',{'passed':True,'result':'本次维修完成质检','evidence_id':evidence(client,row)})
    row=repair.allocate(client,row)
    assert row['amount_cents']==8447
    row=repair.receive(client,row,row['allocations'][0],8447,repair.bank(client))
    row=repair.cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    login(client,'finance')
    return row,rule


def test_member_price_actual_net_cash_original_quote_and_new_statement(client,monkeypatch):
    row,rule=settled(client)
    original=service.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(service,'snapshot',lambda db,user,start,end,definition_version=17:original(db,user,start,end,17))
        old=monthly.batch(client)
    assert not set(SOURCE_FIELDS)&old['summary'].keys()
    new=monthly.cmd(client,old,'recalculate',{'reason':'以本店批准价格和原会期冻结核对本版报价'})
    assert new['definition_version']==service.CURRENT_DEFINITION_VERSION
    assert old['summary']['period_cash_in_cents']==new['summary']['period_cash_in_cents']==8447
    assert new['summary']['period_cash_out_cents']==0
    expected={'member_pricing_rules':1,'member_pricing_scopes':2,'member_pricing_decisions':2,
              'member_pricing_snapshots':1,'member_pricing_lines':2,'member_pricing_authorizations':1}
    for name,count in expected.items():
        assert new['summary'][name]['count']==count and new['summary'][name]['amount_cents']==0
    assert monthly.get(client,old)['manifest']==old['manifest']
    result=client.get('/api/flow/analytics');assert result.status_code==200,result.text
    report=result.json()
    assert report['metrics']['repair_cents']==report['metrics']['cash_in_cents']==8447
    assert report['metrics']['receivable_cents']==0
    for name,index,chart_id in [('repair_settlements',4,'repair_value'),('cash',5,'cash_trend')]:
        response=client.get('/api/flow/analytics/export',params={'dataset':name})
        assert response.status_code==200,response.text
        records=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        assert records[0]==report['tables'][name]['headers'] and len(records[1:])==1
        assert sum(Decimal(r[index].removeprefix("'"))*100 for r in records[1:])==8447
        assert sum(next(c for c in report['charts'] if c['id']==chart_id)['series'][0]['values'])==8447
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);assert validate_sqlite(restored)['verified_reconciliation_batches']==2


@pytest.mark.parametrize('tamper',['ratio','contract','authorization','old_definition','summary','unknown_source'])
def test_member_price_monthly_rehash_cannot_replace_original_approval(client,tamper):
    row,rule=settled(client);batch=monthly.batch(client)
    manifest=copy.deepcopy(batch['manifest']);summary=copy.deepcopy(batch['summary'])
    if tamper=='ratio':next(e for e in manifest if e['source']=='member_pricing_lines')['data']['basis_points']+=1
    elif tamper=='contract':next(e for e in manifest if e['source']=='member_pricing_snapshots')['data']['contract']['rule_version']+=1
    elif tamper=='authorization':next(e for e in manifest if e['source']=='member_pricing_authorizations')['data']['snapshot_digest']='0'*64
    elif tamper=='old_definition':summary['definition_version']=17
    elif tamper=='summary':summary['member_pricing_lines']['amount_cents']=2050
    else:manifest.append({'key':'member_pricing_private:1','source':'member_pricing_private','source_id':1,'case_id':None,'basis':'current','data':{'id':1,'store_id':1}})
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);validate_sqlite(restored)
        restored.execute('UPDATE reconciliation_batches SET manifest=?,summary=?,digest=? WHERE id=?',
                         (json.dumps(manifest),json.dumps(summary),service.digest({'manifest':manifest,'summary':summary}),batch['id']))
        with pytest.raises(ValueError):validate_sqlite(restored)


def test_price_rule_original_case_file_and_task_stay_local_financial_scope(client):
    row,rule=settled(client);login(client,'manager')
    source=client.get('/api/flow/cases/'+str(rule['case_id']));assert source.status_code==200
    source=source.json();assert source['data']['member_price_rule_id']==rule['id']
    file_id=source['files'][0]['id']
    assert client.get('/api/flow/files/'+str(file_id)).status_code==200
    login(client,'service')
    assert client.get('/api/member-pricing/rules/'+str(rule['id'])).status_code==403
    assert client.get('/api/flow/cases/'+str(rule['case_id'])).status_code==404
    assert client.get('/api/flow/files/'+str(file_id)).status_code==404
    assert client.get('/api/member-pricing/candidates',params={'case_id':row['id']}).status_code==200
    login(client,'admin');store=client.post('/api/stores',json={'code':'PRICE-OTHER','name':'会员价隔离模拟门店'}).json()['id']
    client.headers['X-Store-ID']=str(store)
    assert client.get('/api/member-pricing/rules/'+str(rule['id'])).status_code==404
    assert client.get('/api/flow/cases/'+str(rule['case_id'])).status_code==404
    assert client.get('/api/flow/files/'+str(file_id)).status_code==404
    client.headers['X-Store-ID']='all'
    assert client.get('/api/flow/cases/'+str(rule['case_id'])).status_code==404
    assert client.get('/api/flow/files/'+str(file_id)).status_code==404
