"""Actual receipt, per-case allocation, and frozen reconciliation use distinct populations."""
from app.reconciliation_service import CURRENT_DEFINITION_VERSION
import json,sqlite3,uuid
from datetime import timedelta
from sqlalchemy import select
import pytest
from app.db import SessionLocal,today
from app.models import CashEntry
from app import reconciliation_service as rec_service
from app.reconciliation_backup_integrity import validate_reconciliation_sqlite
from app.backup_integrity import validate_sqlite
from tests import test_business_finance as finance,test_retail as retail,test_service_analytics as analytics
from tests.conftest import login,TEST_DIR


def batch(c,start,end):
    r=c.post('/api/reconciliation/batches',json={'request_id':uuid.uuid4().hex,'start':start.isoformat(),'end':end.isoformat(),'reason':'按实际到账日期及原更正来源核对'})
    assert r.status_code==201,r.text;return r.json()


def test_one_cash_multiple_orders_report_once_and_link_to_statement(client):
    one,items,customer=finance.ready_retail(client);items2,_,_,_=retail.setup(client)
    two=retail.authorize(client,retail.approve(client,retail.create(client,items2,customer,qty=500)))
    account=finance.bank(client);statement=finance.approve(client,finance.create(client,customer,'statement',{'starts_on':today().isoformat(),'ends_on':today().isoformat()}))
    allocations=[{'source_case_id':line['source_case_id'],'amount_cents':line['due_cents']} for line in statement['lines']];total=sum(r['amount_cents'] for r in allocations)
    statement=finance.command(client,statement,'collect',finance.proof(client,statement,amount_cents=total,account_id=account,reference='REPORT-SINGLE-CASH',allocations=allocations,source_versions=finance.versions(client,one,two)))
    data=analytics.report(client);assert data['metrics']['cash_in_cents']==total and data['metrics']['receivable_cents']==0
    analytics.reconciled(client,'finance_allocations',total)
    assert len(data['tables']['cash']['rows'])==1 and data['tables']['cash']['rows'][0]['route']=={'type':'case','id':statement['case']['id']}
    frozen=batch(client,today(),today());assert frozen['summary']['cash_entries']['count']==1 and frozen['summary']['flow_payment_links']['count']==2
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);assert validate_sqlite(restored)['verified_finance_cash_batches']==1


def test_cross_month_corrected_actual_cash_and_old_definition_survive_with_tamper_refusal(client,monkeypatch):
    source,_,customer=finance.ready_retail(client);account=finance.bank(client);source=retail.pay(client,source,700,account)
    past=today().replace(day=1)-timedelta(days=1)
    with SessionLocal() as db:
        cash=db.scalar(select(CashEntry));original=cash.id
        db.connection().exec_driver_sql('UPDATE cash_entries SET business_date=? WHERE id=?',(past.isoformat(),original))
        db.connection().exec_driver_sql('UPDATE flow_payment_links SET business_date=? WHERE cash_id=?',(past.isoformat(),original));db.commit()
    old_snapshot=rec_service.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(rec_service,'snapshot',lambda db,user,start,end,definition_version=2:old_snapshot(db,user,start,end,2))
        old=batch(client,past,past)
    assert old['definition_version']==2 and old['summary']['period_cash_in_cents']==700
    correction=finance.create(client,customer,'correction',{'original_cash_id':original,'amount_cents':500,'account_id':account,'reference':'CORRECT-ACTUAL-DATE','allocations':[{'source_case_id':source['id'],'amount_cents':500}]})
    correction=finance.approve(client,correction);finance.command(client,correction,'execute',finance.proof(client,correction,source_versions=finance.versions(client,source)))
    data=analytics.report(client,date_from=past.isoformat(),date_to=past.isoformat());assert data['metrics']['cash_in_cents']==500 and data['metrics']['cash_out_cents']==0
    current=analytics.report(client,date_from=today().isoformat(),date_to=today().isoformat());assert current['metrics']['cash_in_cents']==current['metrics']['cash_out_cents']==0
    analytics.reconciled(client,'finance_corrections',-200,date_from=today().isoformat(),date_to=today().isoformat())
    analytics.reconciled(client,'finance_allocations',500,date_from=past.isoformat(),date_to=past.isoformat())
    # The former version is immutable; explicit recalculation produces current definition 4.
    from tests import test_reconciliation as rec
    old_loaded=rec.get(client,old);assert old_loaded['digest']==old['digest'] and old_loaded['summary']['period_cash_in_cents']==700
    new=rec.cmd(client,old,'recalculate',{'reason':'按更正后实际现金建立新来源版本'})
    assert new['definition_version']==CURRENT_DEFINITION_VERSION and new['summary']['period_cash_in_cents']==500
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original_db,sqlite3.connect(':memory:') as copied:
        original_db.backup(copied);validate_sqlite(copied)
        summary=dict(new['summary']);summary['excluded_cash_ids']=[]
        hashed=rec_service.digest({'manifest':new['manifest'],'summary':summary})
        copied.execute('UPDATE reconciliation_batches SET summary=?,digest=? WHERE id=?',(json.dumps(summary),hashed,new['id']))
        with pytest.raises(ValueError,match='排除集合'):validate_reconciliation_sqlite(copied)


def test_advance_chart_is_balance_not_second_cash_or_business_income(client):
    source,_,customer=finance.ready_retail(client);advance,account=finance.advance(client,customer,1500)
    finance.apply_advance(client,customer,source,600)
    data=analytics.reconciled(client,'finance_advances',900);analytics.reconciled(client,'finance_advance_movements',900)
    assert data['metrics']['cash_in_cents']==1500 and data['metrics']['recorded_business_net_cents']==0
    assert data['metrics']['receivable_cents']==400
    assert data['tables']['finance_advances']['rows'][0]['route']=={'type':'case','id':advance['case']['id']}
    statement=finance.create(client,customer,'statement',{'starts_on':today().isoformat(),'ends_on':today().isoformat()})
    data=analytics.reconciled(client,'finance_customer_statements',400)
    assert data['metrics']['receivable_cents']==400


def test_actual_supplier_return_receivable_is_in_total_until_each_cash_receipt(client):
    from tests import test_warehouse as wh
    from app.flow_models import StockMove
    item,loc,_=wh.setup(client,3000,1000)
    with SessionLocal() as db:original=db.scalar(select(StockMove.id).where(StockMove.item_id==item,StockMove.purpose=='wh_other_in'))
    returned=wh.create(client,'other_in_return',item,1000,src=loc,original=original);wh.approve(client,returned);returned=wh.execute(client,returned)
    supplier=wh.typed(client,'suppliers',{'code':'REPORT-RETURN','name':'合成应收供应方'})
    account=finance.bank(client)
    row=finance.create(client,None,'other_return',{'stock_move_id':returned['stock_moves'][0]['id'],'source_version':returned['version'],'supplier_id':supplier['id'],'amount_cents':400})
    assert analytics.report(client)['metrics']['receivable_cents']==0
    row=finance.approve(client,row);data=analytics.reconciled(client,'finance_other_returns',400)
    assert data['metrics']['receivable_cents']==400 and data['metrics']['cash_in_cents']==0
    finance.command(client,row,'collect',finance.proof(client,row,amount_cents=250,account_id=account,reference='REPORT-OTHER-RETURN'))
    data=analytics.reconciled(client,'finance_other_returns',150)
    assert data['metrics']['receivable_cents']==150 and data['metrics']['cash_in_cents']==250
    frozen=batch(client,today(),today());assert frozen['summary']['current_receivable_cents']==150
