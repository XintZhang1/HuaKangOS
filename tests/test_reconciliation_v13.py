"""Nonempty original correction/prepayment statements; old source contracts stay frozen."""
import copy,json,sqlite3
import pytest
from sqlalchemy import select
from app.db import SessionLocal,today
from app.models import User,CashEntry
from app.tenancy import set_scope
from app import reconciliation_service as svc
from app.reconciliation_v13 import SOURCE_FIELDS
from app.reconciliation_backup_integrity import validate_reconciliation_sqlite
from tests.conftest import login,TEST_DIR
from tests import test_reconciliation as monthly,test_business_finance as finance
from tests import test_finance_corrections as corrections,test_procurement_prepayments as prepay
from tests import test_insurance_invoices as commission,test_insurance_orders as insurance


def restore():
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored)
        from app.backup_integrity import validate_sqlite
        return validate_sqlite(restored)


def test_stored_correction_and_prepayment_freeze_originals_without_extra_cash(client,monkeypatch):
    _,_,customer=finance.ready_retail(client);_,account=finance.advance(client,customer,1000)
    login(client,'finance');original_snapshot=svc.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(svc,'snapshot',lambda db,user,start,end,definition_version=12:original_snapshot(db,user,start,end,12))
        old=monthly.batch(client)
    saved=copy.deepcopy(old)
    corrections.post(client,corrections.correction(client,customer,700,account=account))
    login(client);order,_,supplier_account=prepay.approved(client)
    prepay.advance(client,order,supplier_account,309)
    current=monthly.cmd(client,old,'recalculate',{'reason':'原款更正和采购预付入账，按新口径追加核对版本'})
    assert current['definition_version']==svc.CURRENT_DEFINITION_VERSION
    assert (current['summary']['period_cash_in_cents'],current['summary']['period_cash_out_cents'])==(700,309)
    assert current['summary']['business_finance_stored_corrections']['count']==1
    assert current['summary']['procurement_prepayment_requests']['amount_cents']==309
    assert current['summary']['procurement_prepayment_disbursements']['count']==1
    assert current['summary']['procurement_payment_allocations']['count']==0
    assert len(current['summary']['excluded_cash_ids'])==2
    assert not set(SOURCE_FIELDS)&old['summary'].keys()
    assert all('correction_cents' not in e['data'] for e in old['manifest'] if e['source']=='business_finance_advances')
    assert monthly.get(client,old)['manifest']==saved['manifest'] and monthly.get(client,old)['digest']==saved['digest']
    # Restoring the saved older statement compares its frozen originals, not today's balances.
    assert restore()['verified_reconciliation_batches']==2
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='finance'))
        for version in range(1,13):
            manifest,summary,_=original_snapshot(db,user,today(),today(),version)
            assert not any(e['source'] in SOURCE_FIELDS for e in manifest)
            assert not set(SOURCE_FIELDS)&summary.keys()
        from app.cash_basis import effective_cash
        rows=list(db.scalars(select(CashEntry)))
        assert len(effective_cash(db,rows,3))==4 and len(effective_cash(db,rows,4))==2


def test_pure_void_has_no_replacement_batch_and_restores_monthly_cash(client):
    source,_,customer=finance.ready_retail(client);account=finance.bank(client)
    source=finance.retail.pay(client,source,700,account)
    with SessionLocal() as db:original=db.scalar(select(CashEntry.id))
    request=finance.create(client,customer,'correction',{'original_cash_id':original,'amount_cents':0,'allocations':[]})
    request=finance.approve(client,request)
    finance.command(client,request,'execute',finance.proof(client,request,source_versions=finance.versions(client,source)))
    row=monthly.batch(client)
    assert row['summary']['period_cash_in_cents']==row['summary']['period_cash_out_cents']==0
    facts=[e['data'] for e in row['manifest'] if e['source']=='business_finance_corrections']
    assert len(facts)==1 and facts[0]['corrected_batch_id'] is None
    assert restore()['verified_reconciliation_batches']==1


@pytest.mark.parametrize('tamper',['source_amount','source_omission','summary','old_definition'])
def test_v13_restore_rejects_rehashed_wrong_originals_and_summary(client,tamper):
    order,_,account=prepay.approved(client);prepay.advance(client,order,account,200)
    row=monthly.batch(client)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored);validate_reconciliation_sqlite(restored)
        manifest=copy.deepcopy(row['manifest']);summary=copy.deepcopy(row['summary'])
        if tamper=='source_amount':
            entry=next(e for e in manifest if e['source']=='procurement_prepayment_requests');entry['data']['amount_cents']+=1
        elif tamper=='source_omission':
            manifest=[e for e in manifest if e['source']!='procurement_prepayment_disbursements']
        elif tamper=='summary':summary['procurement_prepayment_requests']['amount_cents']+=1
        else:summary['definition_version']=12
        restored.execute('UPDATE reconciliation_batches SET manifest=?,summary=?,digest=? WHERE id=?',
                         (json.dumps(manifest),json.dumps(summary),svc.digest({'manifest':manifest,'summary':summary}),row['id']))
        with pytest.raises(ValueError):validate_reconciliation_sqlite(restored)


def test_commission_difference_enters_only_new_definition_and_restores_original_invoice(client):
    source=commission.prepare(client);commission.actual(client,source)
    insurance.commission(client,source,200);login(client,'finance')
    row=monthly.batch(client)
    differences=[e for e in row['manifest'] if e['source']=='invoice_corrections']
    assert len(differences)==1 and differences[0]['data']['amount_cents']==301
    assert restore()['verified_reconciliation_batches']==1
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='finance'))
        manifest,_,_=svc.snapshot(db,user,today(),today(),12)
        assert not any(e['source']=='invoice_corrections' and e['case_id']==source['id'] for e in manifest)
