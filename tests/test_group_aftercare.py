"""Post-delivery returns consume approved original tenders, never arbitrary reverse."""
import uuid
import sqlite3
from datetime import timedelta
import pytest
from sqlalchemy import select,func
from app.db import SessionLocal,today
from app.models import CashEntry,User,UserStore
from app.flow_models import Case
from app.group_models import GroupEntry,GroupPaymentLink,GroupSettlementEntry
from app.group_benefits_models import BenefitWallet,BenefitEntry,BenefitPaymentLink,BenefitSettlement
from app.group_aftercare_models import GroupAftercareHold
from app.business_finance_models import FinanceCreditLink
from tests.conftest import login,PASSWORD_HASH,TEST_DIR
from tests.test_workflow import evidence
from tests.test_procurement import bank
from tests import test_repair_orders as repair,test_aftercare as aftercare,test_group_membership as group,test_group_benefits as benefits,test_business_finance as finance

@pytest.fixture(autouse=True)
def technician():
    with SessionLocal() as db:
        u=User(username='technician',display_name='实际合成技师',role='technician',password_hash=PASSWORD_HASH,must_change_password=False)
        db.add(u);db.flush();db.add(UserStore(user_id=u.id,store_id=1));db.commit()
    yield
    finance.assert_restore()
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored);validate_sqlite(restored)

def source(c):
    row,item,work,customer=repair.setup(c)
    data={'case_id':row['id'],'customer_id':customer['id'],'account_id':bank(c),'evidence_id':evidence(c,row),'store_id':1}
    member=group.issue(c,data)
    row=repair.allocate(c,repair.ready(c,row,item,work));return row,data,member,customer,work

def test_released_principal_only_returns_by_approved_aftercare_original(client):
    row,data,member,_,_=source(client)
    group.cmd(client,member,'topup',group.topup_values(data,10997))
    held=group.cmd(client,member,'reserve',group.reserve_values(data,10997));capture=group.cmd(client,member,'capture',group.reservation_values(data,held))
    row=repair.cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    group.cmd(client,member,'reverse',{'original_id':capture['entry_id'],'amount_cents':1,'case_version':group.case_version(row['id']),'evidence_id':data['evidence_id'],'reason':'不得绕过已交车关口'},409)
    request=aftercare.create(client,row);request=aftercare.plan(client,request,1701,[{'kind':'principal','original_id':capture['entry_id'],'units':1701}]);request=aftercare.approved(client,request)
    assert group.wallet(client,member)['balance_cents']==0
    request=aftercare.cmd(client,request,'cancel_plan',{'reason':'客户更改本次明确金额'})
    request=aftercare.plan(client,request,1700,[{'kind':'principal','original_id':capture['entry_id'],'units':1700}]);request=aftercare.approved(client,request)
    request=aftercare.applied(client,aftercare.confirmed(client,request));assert request['state']=='completed'
    assert group.wallet(client,member)['balance_cents']==1700
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==1
        assert db.scalar(select(func.sum(GroupPaymentLink.amount_cents)))==9297
        assert db.scalar(select(func.sum(GroupSettlementEntry.amount_cents)))==0
        assert {h.status for h in db.scalars(select(GroupAftercareHold))}=={'applied','released'}

def test_expired_package_returns_frozen_whole_unit_without_new_cash(client):
    row,data,member,_,work=source(client)
    rule=benefits.rule(client,'package',allowed_store_ids=[1],service_code=work['code'],credit_cents_per_unit=1000,sale_cents_per_unit=700,settlement_cents_per_unit=700)
    wallet=benefits.issuance(client,member,data,rule,1);held=benefits.reserve(client,member,data,wallet);capture=benefits.capture(client,member,data,wallet,held)
    row=repair.receive(client,row,repair.detail(client,row)['allocations'][0],9997,data['account_id']);row=repair.cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    with SessionLocal() as db:
        # Synthetic passage of time, not a user mutation of the frozen entitlement.
        db.connection().exec_driver_sql('UPDATE benefit_wallets SET expires_on=? WHERE id=?',((today()-timedelta(days=1)).isoformat(),wallet['id']));db.commit()
    request=aftercare.create(client,row)
    entry=next(s for s in request['sources'][0]['eligible_returns'] if s['kind']=='benefit')
    assert entry['remaining_units']==1 and entry['remaining_credit_cents']==1000
    aftercare.cmd(client,request,'plan',{'reason':'不能拆成现金份额','lines':[{'source_id':request['sources'][0]['id'],'credit_cents':500,'returns':[{'kind':'benefit','original_id':capture['entry_id'],'units':1}]}]},422)
    request=aftercare.plan(client,request,1000,[{'kind':'benefit','original_id':capture['entry_id'],'units':1}]);request=aftercare.applied(client,aftercare.confirmed(client,aftercare.approved(client,request)))
    with SessionLocal() as db:
        current=db.connection().exec_driver_sql('SELECT balance_units,expires_on FROM benefit_wallets WHERE id=?',(wallet['id'],)).one();assert current[0]==1 and current[1]<today().isoformat()
        assert db.scalar(select(func.count()).select_from(CashEntry))==2
        assert db.scalar(select(func.sum(BenefitPaymentLink.amount_cents)))==0
        assert db.scalar(select(func.sum(BenefitSettlement.amount_cents)))==0

def test_aftercare_returns_advance_to_original_balance_without_refunding_cash(client):
    row,data,_,customer,_=source(client);advance,_=finance.advance(client,customer,10997,data['account_id']);finance.apply_advance(client,customer,row,10997)
    login(client);row=repair.cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    request=aftercare.create(client,row);original=next(s for s in request['sources'][0]['eligible_returns'] if s['kind']=='advance')
    request=aftercare.plan(client,request,701,[{'kind':'advance','original_id':original['entry_id'],'units':701}]);request=aftercare.applied(client,aftercare.confirmed(client,aftercare.approved(client,request)))
    assert finance.current_advance(client,customer)['balance_cents']==701 and request['state']=='completed'
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(FinanceCreditLink.amount_cents)))==10296
        assert db.scalar(select(func.count()).select_from(CashEntry))==1


@pytest.mark.parametrize('consumed',[False,True])
def test_consumed_points_debt_does_not_block_aftercare_advance_return_or_original_refund(client,consumed):
    from tests import test_membership_lifecycle as membership
    row,item,work,customer=repair.setup(client);member=group.issue(client,{'customer_id':customer['id']})
    point_rule=benefits.rule(client,'points',allowed_store_ids=[1]);level=membership.rule(client,points_enabled=True,points_benefit_rule_id=point_rule['id']);membership.renew(client,customer,level);login(client)
    row=repair.allocate(client,repair.ready(client,row,item,work));prepaid,account=finance.advance(client,customer,10997);finance.apply_advance(client,customer,row,10997)
    login(client);row=repair.cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    wallet=benefits.info(client,{'customer_id':customer['id']})['wallets'][0];assert wallet['balance_units']==109
    if consumed:
        coupon=benefits.rule(client,'coupon',allowed_store_ids=[1],sale_cents_per_unit=0,settlement_cents_per_unit=0,exchange_points_per_unit=1)
        exchange=membership.create(client,customer,'points_adjust',{'action':'exchange','wallet_id':wallet['id'],'target_rule_id':coupon['id'],'units':109});login(client,'finance')
        membership.cmd(client,exchange,'execute',{'evidence_id':membership.proof(client,exchange),'wallet_version':wallet['version'],'reason':'客户明确兑换原消费所得积分'})
    login(client);request=aftercare.create(client,row);original=next(s for s in request['sources'][0]['eligible_returns'] if s['kind']=='advance')
    request=aftercare.plan(client,request,701,[{'kind':'advance','original_id':original['entry_id'],'units':701}]);request=aftercare.applied(client,aftercare.confirmed(client,aftercare.approved(client,request)))
    expected_debt=7 if consumed else 0
    assert membership.info(client,customer)['points_debt_units']==expected_debt
    a=finance.current_advance(client,customer);refund=finance.create(client,customer,'advance_refund',{'amount_cents':701,'advance_id':a['id'],'advance_version':a['version']});refund=finance.approve(client,refund)
    finance.command(client,refund,'execute',finance.proof(client,refund,account_id=account,reference='original-refund-with-points-debt'))
    assert finance.current_advance(client,customer)['balance_cents']==0 and membership.info(client,customer)['points_debt_units']==expected_debt
    membership.assert_report(client,membership_points=102,membership_points_debts=expected_debt)
