"""Real renewal fees: recording corrections, frozen statements and actual cash dates."""
import copy,csv,io,json,sqlite3,uuid
from datetime import timedelta
from decimal import Decimal
import pytest
from app.db import today
from app import reconciliation_service as reconciliation
from app.backup_integrity import validate_sqlite
from app.reconciliation_v21 import SOURCE_FIELDS
from tests.conftest import TEST_DIR
from tests import test_member_fee_corrections as fee,test_reconciliation as monthly


def rows(table,where='',values=()):
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:
        connection.row_factory=sqlite3.Row
        return [dict(row) for row in connection.execute('SELECT * FROM '+table+(' WHERE '+where if where else '')+' ORDER BY id',values)]


def facts(data):
    original=rows('membership_fees','id=?',(data['fee_id'],))[0]
    period=rows('membership_periods','id=?',(original['period_id'],))[0]
    cash=rows('cash_entries','id=?',(original['cash_id'],))[0]
    return original,period,cash


def batch(client,start,end):
    response=client.post('/api/reconciliation/batches',json={'request_id':uuid.uuid4().hex,'start':str(start),'end':str(end),'reason':'核对续会费原业务日与登记更正来源'})
    assert response.status_code==201,response.text
    return response.json()


def report(client,start,end,*,cash_in,cash_out,fee_net):
    params={'date_from':str(start),'date_to':str(end)}
    response=client.get('/api/flow/analytics',params=params);assert response.status_code==200,response.text
    value=response.json();metrics=value['metrics']
    assert (metrics['cash_in_cents'],metrics['cash_out_cents'],metrics['membership_fee_net_cents'])==(cash_in,cash_out,fee_net)
    for dataset in ('cash','membership_fees'):
        table=value['tables'][dataset];response=client.get('/api/flow/analytics/export',params={**params,'dataset':dataset});assert response.status_code==200,response.text
        exported=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        assert exported[0]==table['headers']
        assert [[cell.removeprefix("'") for cell in row] for row in exported[1:]]==[[str(cell) for cell in row['values']] for row in table['rows']]
    cash_rows=value['tables']['cash']['rows']
    actual_in=sum(int(Decimal(row['values'][5])*100) for row in cash_rows if row['values'][3]=='收入')
    actual_out=sum(int(Decimal(row['values'][5])*100) for row in cash_rows if row['values'][3]=='支出')
    assert (actual_in,actual_out)==(cash_in,cash_out)
    trend=next(chart for chart in value['charts'] if chart['id']=='cash_trend')
    assert [sum(series['values']) for series in trend['series']]==[cash_in,cash_out]
    fee_chart=next(chart for chart in value['charts'] if chart['id']=='membership_fees')
    assert sum(row['amount_cents'] for row in value['tables']['membership_fees']['rows'])==sum(fee_chart['series'][0]['values'])==fee_net
    return value


def assert_sources(statement,counts):
    assert statement['definition_version']==21
    for name in SOURCE_FIELDS:
        summary=statement['summary'][name]
        assert summary=={'count':counts.get(name,0),'amount_cents':0,'value_cents':0,'quantity_milli_by_item':{},'units_by_kind':{}}
        assert summary['count']==sum(entry['source']==name for entry in statement['manifest'])


def corrected(client,data,**values):
    return fee.post(client,fee.approve(client,fee.correction(client,data,**values)))


def test_original_fee_once_and_statement20_stays_frozen_while21_adds_count_only_sources(client,monkeypatch):
    data=fee.setup_paid(client);original,period,cash=facts(data);amount=original['amount_cents'];day=cash['business_date']
    snapshot=reconciliation.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(reconciliation,'snapshot',lambda db,user,start,end,definition_version=20:snapshot(db,user,start,end,20))
        old=batch(client,day,day)
    old_manifest=copy.deepcopy(old['manifest']);old_digest=old['digest']
    assert old['definition_version']==20 and not set(SOURCE_FIELDS)&old['summary'].keys()
    correction=corrected(client,data);current=monthly.cmd(client,old,'recalculate',{'reason':'新定义核对原续会费同額登记更正'})
    assert_sources(current,{'membership_fee_correction_requests':1,'membership_fee_corrections':1})
    assert current['summary']['period_cash_in_cents']==amount and current['summary']['period_cash_out_cents']==0
    posted=rows('membership_fee_corrections')[0]
    assert current['summary']['excluded_cash_ids']==sorted([posted['original_cash_id'],posted['reversing_cash_id']])
    assert posted['corrected_cash_id'] not in current['summary']['excluded_cash_ids']
    old_now=monthly.get(client,old);assert old_now['manifest']==old_manifest and old_now['digest']==old_digest and old_now['definition_version']==20
    assert not set(SOURCE_FIELDS)&{entry['source'] for entry in old_now['manifest']}
    assert facts(data)==(original,period,cash)
    assert len(rows('membership_fees'))==1
    effective=fee.source(client,data);value=report(client,day,day,cash_in=amount,cash_out=0,fee_net=amount)
    assert len(value['tables']['cash']['rows'])==len(value['tables']['membership_fees']['rows'])==1
    assert value['tables']['cash']['rows'][0]['values'][6:]==[effective['account'],effective['reference']]
    assert value['tables']['cash']['rows'][0]['values'][4]=='会员续会收款'
    assert value['tables']['cash']['rows'][0]['route']=={'type':'case','id':correction['case']['id']}
    assert value['tables']['membership_fees']['rows'][0]['route']=={'type':'case','id':data['order']['case']['id']}
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);result=validate_sqlite(restored);assert result['integrity']=='ok' and result['verified_reconciliation_batches']==2


def test_cross_period_continuous_corrections_keep_original_fee_date_and_real_refund_account(client,monkeypatch):
    from app import membership_service,group_service
    original_day=today().replace(day=1)-timedelta(days=1)
    # Simulated business clock at actual API posting, never SQL-created cash.
    with monkeypatch.context() as patch:
        patch.setattr(membership_service,'today',lambda:original_day)
        patch.setattr(group_service,'today',lambda:original_day)
        data=fee.setup_paid(client)
    original,period,cash=facts(data);amount=original['amount_cents'];assert cash['business_date']==str(original_day)
    corrected(client,data,reference='SYNTHETIC-FEE-FIRST-CORRECTION')
    corrected(client,data,reference='SYNTHETIC-FEE-SECOND-CORRECTION')
    effective=fee.source(client,data);assert effective['cash_id']!=original['cash_id'] and effective['business_date']==str(original_day)
    assert facts(data)==(original,period,cash) and len(rows('membership_fees'))==1
    report(client,original_day,original_day,cash_in=amount,cash_out=0,fee_net=amount)
    report(client,today(),today(),cash_in=0,cash_out=0,fee_net=0)
    refund=fee.refund(client,data)
    actual_refund=rows('membership_fees','original_id=?',(original['id'],))[0]
    refund_cash=rows('cash_entries','id=?',(actual_refund['cash_id'],))[0]
    assert refund_cash['business_date']==str(today()) and refund_cash['account']==effective['account'] and refund_cash['amount_cents']==amount
    basis=rows('membership_fee_refund_bases','refund_fee_id=?',(actual_refund['id'],))[0]
    assert basis['original_fee_id']==original['id'] and basis['original_cash_id']==effective['cash_id']
    assert facts(data)==(original,period,cash)
    report(client,original_day,original_day,cash_in=amount,cash_out=0,fee_net=amount)
    refunded=report(client,today(),today(),cash_in=0,cash_out=amount,fee_net=-amount)
    assert refunded['tables']['cash']['rows'][0]['values'][4]=='会员续会原款退款'
    assert refunded['tables']['cash']['rows'][0]['route']=={'type':'case','id':refund['case']['id']}
    assert refunded['tables']['membership_fees']['rows'][0]['route']=={'type':'case','id':refund['case']['id']}
    full=report(client,original_day,today(),cash_in=amount,cash_out=amount,fee_net=0)
    assert len(full['tables']['cash']['rows'])==2
    statement=batch(client,original_day,today());assert_sources(statement,{'membership_fee_correction_requests':2,'membership_fee_corrections':2,'membership_fee_refund_bases':1})
    assert statement['summary']['period_cash_in_cents']==statement['summary']['period_cash_out_cents']==amount
    excluded={row[key] for row in rows('membership_fee_corrections') for key in ('original_cash_id','reversing_cash_id')}
    assert set(statement['summary']['excluded_cash_ids'])==excluded
    assert effective['cash_id'] not in excluded and refund_cash['id'] not in excluded
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);assert validate_sqlite(restored)['integrity']=='ok'


@pytest.mark.parametrize('tamper',['cash_reference','summary_adds_income','old_definition','unknown_source'])
def test_rehashed_statement_cannot_forge_fee_original_chain_or_extend_source_contract(client,tamper):
    data=fee.setup_paid(client);corrected(client,data);fee.refund(client,data);statement=monthly.batch(client)
    manifest=copy.deepcopy(statement['manifest']);summary=copy.deepcopy(statement['summary'])
    if tamper=='cash_reference':
        entry=next(e for e in manifest if e['source']=='membership_fee_corrections')
        entry['data']['corrected_cash_id']=entry['data']['reversing_cash_id']
    elif tamper=='summary_adds_income':summary['membership_fee_corrections']['amount_cents']=facts(data)[0]['amount_cents']
    elif tamper=='old_definition':summary['definition_version']=20
    else:manifest.append({'key':'membership_fee_correction_unknown:1','source':'membership_fee_correction_unknown','source_id':1,'case_id':data['order']['case']['id'],'basis':'current','data':{'id':1,'store_id':1}})
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);assert validate_sqlite(restored)['integrity']=='ok'
        restored.execute('UPDATE reconciliation_batches SET manifest=?,summary=?,digest=? WHERE id=?',(json.dumps(manifest),json.dumps(summary),reconciliation.digest({'manifest':manifest,'summary':summary}),statement['id']))
        with pytest.raises(ValueError):validate_sqlite(restored)
