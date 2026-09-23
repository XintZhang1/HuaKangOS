"""Bundle corrections keep historical cash definitions and exact original units."""
import copy,csv,io,json,sqlite3
from decimal import Decimal
import pytest
from sqlalchemy import select
from app.db import SessionLocal,today
from app.models import User,CashEntry
from app.tenancy import set_scope
from app.cash_basis import effective_cash
from app import reconciliation_service as service
from app.reconciliation_v17 import SOURCE_FIELDS
from app.backup_integrity import validate_sqlite
from tests.conftest import login,TEST_DIR
from tests import test_recharge_corrections as bundle_fix,test_recharge_bundles as bundle,test_finance_corrections as finance_fix,test_business_finance as finance,test_reconciliation as monthly


@pytest.mark.parametrize('amount',[0,2000])
def test_bundle_cash_units_original_and_new_statement_definition(client,monkeypatch,amount):
    a,_,_,_,purchase=bundle.setup(client);login(client,'finance')
    original=service.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(service,'snapshot',lambda db,user,start,end,definition_version=16:original(db,user,start,end,16))
        old=monthly.batch(client)
    assert old['summary']['period_cash_in_cents']==3000 and not set(SOURCE_FIELDS)&old['summary'].keys()
    request=finance.approve(client,bundle_fix.fix(client,a,amount))
    held=monthly.cmd(client,old,'recalculate',{'reason':'批准占用原本金及全部原赠品，仅冻结待更正来源'})
    assert held['definition_version']==service.CURRENT_DEFINITION_VERSION
    assert held['summary']['period_cash_in_cents']==3000
    assert held['summary']['business_finance_bundle_correction_components']['count']==4
    assert held['summary']['business_finance_bundle_correction_postings']['count']==0
    request=finance.command(client,request,'execute',finance.proof(client,request))
    current=monthly.cmd(client,held,'recalculate',{'reason':'同步更正原组合本金及发行差额后重新核对'})
    assert current['summary']['period_cash_in_cents']==amount and current['summary']['period_cash_out_cents']==0
    assert current['summary']['business_finance_bundle_correction_postings']['count']==4
    assert len(current['summary']['excluded_cash_ids'])==2
    assert all(current['summary'][name]['amount_cents']==0 for name in SOURCE_FIELDS)
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='finance'))
        manifest,summary,_=original(db,user,today(),today(),16)
        assert summary['excluded_cash_ids']==[]
        assert (summary['period_cash_in_cents'],summary['period_cash_out_cents'])==(3000+amount,3000)
        assert not any(e['source'] in SOURCE_FIELDS or e['source'] in {'business_finance_stored_correction_requests','business_finance_stored_corrections'} for e in manifest)
        cash=list(db.scalars(select(CashEntry)))
        assert len(effective_cash(db,cash,4))==len(cash)
        assert len(effective_cash(db,cash,5))==(1 if amount else 0)
    report=client.get('/api/flow/analytics');assert report.status_code==200,report.text
    report=report.json();assert report['metrics']['cash_net_cents']==report['metrics']['recharge_bundle_net_cash_cents']==amount
    for name,column,unit in [('recharge_bundle_cash',7,'amount_cents'),('recharge_bundle_bonus',5,'units'),('recharge_bundle_points',5,'units'),('recharge_bundle_coupon',5,'units'),('recharge_bundle_package',5,'units')]:
        table=report['tables'][name];chart=next(c for c in report['charts'] if c['id']==name)
        total=sum(r[unit] for r in table['rows']);assert total==sum(chart['series'][0]['values'])
        export=client.get('/api/flow/analytics/export',params={'dataset':name});assert export.status_code==200
        records=list(csv.reader(io.StringIO(export.content.decode('utf-8-sig'))));assert records[0]==table['headers']
        factor=100 if name in {'recharge_bundle_cash','recharge_bundle_bonus'} else 1
        assert sum(Decimal(r[column].removeprefix("'"))*factor for r in records[1:])==total
    assert bundle.detail(client,purchase)['purchase']['shares']==3
    assert monthly.get(client,old)['manifest']==old['manifest'] and monthly.get(client,held)['manifest']==held['manifest']
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);assert validate_sqlite(restored)['verified_reconciliation_batches']==3


@pytest.mark.parametrize('tamper',['shares','delta_units','posting','old_definition','summary'])
def test_bundle_frozen_correction_rejects_rehashed_wrong_original(client,tamper):
    a,_,_,_,_=bundle.setup(client);login(client,'finance');finance_fix.post(client,bundle_fix.fix(client,a,2000))
    batch=monthly.batch(client)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);validate_sqlite(restored)
        manifest=copy.deepcopy(batch['manifest']);summary=copy.deepcopy(batch['summary'])
        if tamper=='shares':next(e for e in manifest if e['source']=='business_finance_bundle_corrections')['data']['corrected_shares']+=1
        elif tamper=='delta_units':next(e for e in manifest if e['source']=='business_finance_bundle_correction_components')['data']['delta_units']-=1
        elif tamper=='posting':next(e for e in manifest if e['source']=='business_finance_bundle_correction_postings')['data']['benefit_entry_id']+=99999
        elif tamper=='old_definition':summary['definition_version']=16
        else:summary['business_finance_bundle_correction_postings']['amount_cents']=1
        restored.execute('UPDATE reconciliation_batches SET manifest=?,summary=?,digest=? WHERE id=?',(json.dumps(manifest),json.dumps(summary),service.digest({'manifest':manifest,'summary':summary}),batch['id']))
        with pytest.raises(ValueError):validate_sqlite(restored)
