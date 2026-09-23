"""Synthetic domain invariants; public native integration is tested separately.

The local fixture exercises the same original services without mocking their
money operations. No fixture redirects a production handler or bypasses its
same-transaction issuance association. See test_retail_group_api for HTTP flows.
"""
import hashlib
import uuid
import sqlite3
from datetime import timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app.db import SessionLocal,today
from app.models import User,CashEntry,UserStore
from app.flow_models import Case,FileAsset,PaymentLink,Task
from app.tenancy import set_scope,project_user,role_for_store
from app.group_models import GroupEntry,GroupMember
from app.group_benefits_models import BenefitWallet,BenefitEntry,BenefitSettlement
from app.retail_models import RetailReturnPosting,RetailPayment
from app import retail_group_service as svc,retail_group_rules as rules,group_benefits_service as benefits
from app.retail_group_models import RetailGroupEligibility, RetailGroupPlan, RetailGroupUnit, RetailGroupRestore, RetailGroupSettlement,RetailGroupWallet
from tests.conftest import login,TEST_DIR
from tests import test_retail as retail,test_group_membership as group,test_group_benefits as benefit
technician=retail.technician


def actor(db,username='admin',store=1):
    set_scope(db,[store],store)
    user=db.scalar(select(User).where(User.username==username))
    return project_user(user,role_for_store(db,user,store))


def proof(case_id,username='admin',category='authorization',*,generated=False):
    with SessionLocal() as db:
        row=db.scalar(select(Case).where(Case.id==case_id));user=actor(db,username,row.store_id)
        content=('仅合成测试 '+uuid.uuid4().hex).encode()
        asset=FileAsset(case_id=row.id,category=category,name='合成上传原件.txt',media_type='text/plain',size=len(content),sha256=hashlib.sha256(content).hexdigest(),content=content,created_by=user.id,generated=generated)
        db.add(asset);db.flush()
        from app.file_security import initialize_file_security
        initialize_file_security(db,user,row,asset);db.commit();return asset.id


def case_store(case_id):
    with SessionLocal() as db:return db.scalar(select(Case.store_id).where(Case.id==case_id))


def call(case_id,action,values,username='finance',store=None,key=None,version=None):
    with SessionLocal() as db:
        user=actor(db,username,store or case_store(case_id));row=db.scalar(select(Case).where(Case.id==case_id))
        return svc.command(db,user,case_id,key or uuid.uuid4().hex,version if version is not None else row.version,action,values)


def info(case_id,username='finance',store=None):
    with SessionLocal() as db:
        user=actor(db,username,store or case_store(case_id));row=svc.retail.get_order(db,user,case_id)
        return svc.describe(db,user,row)


def action_values(row,tender_id=None,unit_id=None,username='finance',**extra):
    current=info(row['id'],username)
    tender=next((t for t in current['tenders'] if t['id']==tender_id or any(u['id']==unit_id for u in t['units_detail'])),None)
    v={'plan_version':current['plan_version'],'member_version':current['member_version'],'evidence_id':proof(row['id'],username)}
    if tender:
        if tender.get('wallet_version'):v['wallet_version']=tender['wallet_version']
        if tender.get('reservation_version'):v['reservation_version']=tender['reservation_version']
    if tender_id:v['tender_id']=tender_id
    if unit_id:v['unit_id']=unit_id
    return v|extra


def approved_rule(c,items,work=None,kind='coupon',scope_store=1,**changes):
    prices={'credit_cents_per_unit':1,'settlement_cents_per_unit':0,'sale_cents_per_unit':0} if kind=='bonus' else {'credit_cents_per_unit':400,'settlement_cents_per_unit':321,'sale_cents_per_unit':321}
    rule=benefit.rule(c,kind,**(prices|{'allowed_store_ids':sorted({1,scope_store})}|changes))
    with SessionLocal() as db:
        user=actor(db);config=rules.create(db,user,uuid.uuid4().hex,rule['id'])
    scopes=[dict(store_id=scope_store,item_id=item['id'],component='goods',work_item_id=None) for item in items]
    if work:scopes.append(dict(store_id=scope_store,item_id=items[0]['id'],component='installation',work_item_id=work['id']))
    submit={'evidence_id':proof(config['case_id']),'scopes':scopes,**svc.MODES}
    with SessionLocal() as db:config=rules.command(db,actor(db),config['case_id'],uuid.uuid4().hex,config['version'],'submit',submit)
    # The independent manager confirms the original applicant's source, not a
    # redundant upload. Decision.actor_id must still be the actual manager.
    approval={'evidence_id':submit['evidence_id'],'reason':'合成独立主管明确批准原有效期与原单位累积退回'}
    with SessionLocal() as db:rules.command(db,actor(db,'manager'),config['case_id'],uuid.uuid4().hex,config['version'],'approve',approval)
    return rule,config


def issue_native_with_hook(c,member,source,rule,units=3,purpose='purchase'):
    # The native issuance now attaches its own approved annex atomically.
    with SessionLocal() as db:
        user=actor(db)
        with svc.authority(db,user,{'admin'}):
            m=svc.group._member(db,member['id'],1);row=svc.group._case(db,user,m,source['case_id'],group.case_version(source['case_id']),1)
            r=benefits._rule(db,rule['id'])
            cash=account=None;reference=None
            if purpose=='purchase':
                reference=uuid.uuid4().hex
                cash,account=benefits._cash(db,user,row,{'evidence_id':source['evidence_id'],'account_id':source['account_id'],'reference':reference},'in',units*r.sale_cents_per_unit)
            wallet,entry=benefits._issue(db,user,m,row,r,units,purpose,source['evidence_id'],'合成原发行',cash,account,reference)
            db.commit()
            return {'id':wallet.id,'version':wallet.version,'kind':r.kind}


def setup(c,with_benefit=True,kind='coupon',goods_only=False,authorize=True,store=1):
    source=group.seed(name='精品合成客户',phone='13900000091');member=group.issue(c,source)
    group.cmd(c,member,'topup',group.topup_values(source,2000))
    if store!=1:
        group.seed(store)
        with SessionLocal() as db:
            for name in ('manager','technician','sales','inventory','service'):
                u=db.scalar(select(User).where(User.username==name));db.add(UserStore(user_id=u.id,store_id=store))
            db.commit()
        group.switch(c,store)
    items,customer,work,_=retail.setup(c,True)
    group.link(c,{'customer_id':customer['id']},member['identity_id'])
    row=retail.create(c,items,customer,work);row=retail.authorize(c,retail.approve(c,row));row=retail.dispatch(c,row)
    # Native technician flow, preserving actual employee evidence.
    login(c,'technician');row=retail.cmd(c,row,'install',{'evidence_id':retail.evidence(c,row),'result':'本人实际完成安装'})
    login(c);row=retail.cmd(c,row,'accept',{'evidence_id':retail.evidence(c,row)})
    wallet=rule=None
    if with_benefit:
        group.switch(c,1)
        rule,_=approved_rule(c,items[:1] if goods_only else items,None if goods_only else work,kind,scope_store=store)
        wallet=issue_native_with_hook(c,member,source,rule,units=300 if kind=='bonus' else 3,purpose='grant' if kind=='bonus' else 'purchase')
        group.switch(c,store)
    selections=[{'kind':'principal','amount_cents':300}]
    if wallet:selections.insert(0,{'kind':kind,'wallet_id':wallet['id'],'wallet_version':wallet['version'],'units':100 if kind=='bonus' else 1})
    with SessionLocal() as db:
        user=actor(db)
        with svc.authority(db,user):version=svc.group._member(db,member['id'],1).version
    values={'member_id':member['id'],'member_version':version,'evidence_id':proof(row['id']),'selections':selections}
    result=call(row['id'],'authorize',values,'admin') if authorize else values
    return row,result,member,wallet,source


def spend_all(row):
    for tender in info(row['id'])['tenders']:
        if tender['kind']=='cash':continue
        call(row['id'],'reserve',action_values(row,tender_id=tender['id']))
        call(row['id'],'capture',action_values(row,tender_id=tender['id']))


def native_cash(row,amount,account_id,original=None):
    evidence=proof(row['id'],'finance','receipt')
    with SessionLocal() as db:
        user=actor(db,'finance',case_store(row['id']));case=svc.retail.get_order(db,user,row['id'])
        with svc.authority(db,user,svc.FINANCE):
            values={'evidence_id':evidence,'account_id':account_id,'reference':uuid.uuid4().hex}
            if original:
                svc.guard_cash_refund(db,user,case,original,amount);origin=svc.one(db,PaymentLink,original)
                payment=svc.retail.flow.add_payment(db,user,case,values,direction='out',original=origin,amount=amount)
                svc.attach_cash_refund(db,user,case,payment,original)
            else:
                svc.guard_cash_receive(db,user,case,amount)
                payment=svc.retail.flow.add_payment(db,user,case,values,direction='in',amount=amount)
                svc.attach_cash(db,user,case,payment)
            db.add(RetailPayment(case_id=case.id,payment_link_id=payment.id,evidence_id=evidence));case.updated_at=svc.utcnow();db.flush();svc._sync(db,user,case);db.commit();return payment.id


def native_return(c,row,quantity=500):
    login(c);current=retail.detail(c,row);source=current['dispatches'][0]
    row,ret=retail.request_return(c,current,source,quantity);row=retail.ret_cmd(c,row,ret,'return_approve')
    ret=next(r for r in row['returns'] if r['id']==ret['id'])
    e=proof(row['id'],'inventory','inspection')
    with SessionLocal() as db:
        user=actor(db,'inventory',case_store(row['id']));case=svc.retail.get_order(db,user,row['id'])
        with svc.authority(db,user,svc.retail.READ_ROLES):
            svc.retail._return(db,user,case,'return_receive',{'return_id':ret['id'],'return_version':ret['version'],'evidence_id':e,'passed':True,'result':'本人实际验收合格'})
            db.flush();posts=svc.rows(db,RetailReturnPosting,case_id=case.id)
            for post in posts:svc.record_actual_return(db,user,case,post)
            case.updated_at=svc.utcnow();db.flush();db.commit()
    return posts[-1].id


def test_mixed_original_partial_return_pending_liability_and_cash_once(client):
    row,plan,m,w,source=setup(client);spend_all(row)
    cash=info(row['id'])['totals']['cash_collectable_cents'];assert cash==500
    first=native_cash(row,201,source['account_id']);second=native_cash(row,299,source['account_id'])
    posting=native_return(client,row)
    detail=info(row['id']);assert detail['totals']['group_return_pending_cents']['coupon']>0
    amounts=detail['totals']
    assert amounts['group_paid_cents']-amounts['group_recognized_cents']==amounts['group_discount_borne_cents']+amounts['service_discount_borne_cents']
    assert amounts['group_internal_settlement_cents']-amounts['group_recognized_cents']==amounts['group_discount_borne_cents']
    coupon=next(t for t in detail['tenders'] if t['kind']=='coupon');unit=coupon['units_detail'][0]
    assert unit['pending_original_unit'] and not unit['restorable'] and unit['spendable_pending_cents']==0
    with pytest.raises(HTTPException) as error:call(row['id'],'restore',action_values(row,unit_id=unit['id']))
    assert error.value.status_code==409
    principal=next(t for t in detail['tenders'] if t['kind']=='principal');call(row['id'],'restore',action_values(row,unit_id=principal['units_detail'][0]['id']))
    with SessionLocal() as db:
        user=actor(db,'finance');case=svc.retail.get_order(db,user,row['id'])
        with svc.authority(db,user):
            cash_rights=svc.cash_refundable(db,case)
            paid_ids=sorted({r.payment_link_id for r,_ in cash_rights})
            amounts={pid:sum(a for r,a in cash_rights if r.payment_link_id==pid) for pid in paid_ids}
            assert sum(amounts.values())==detail['totals']['cash_refund_due_cents']>0
            adjustments=svc.analytics_adjustments(db,case)
            assert sum(a['consideration_cents'] for a in adjustments)<0
            assert db.scalar(select(func.sum(RetailGroupSettlement.amount_cents)))==0
    with pytest.raises(HTTPException):native_cash(row,501,source['account_id'],first)
    for pid,amount in amounts.items():native_cash(row,amount,source['account_id'],pid)
    assert info(row['id'])['totals']['cash_refund_due_cents']==0
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(GroupEntry).where(GroupEntry.purpose=='topup'))==1
        assert db.scalar(select(func.count()).select_from(CashEntry))==4+len(amounts) # procurement, topup, coupon, 2 retail => checked below


def test_original_unit_restore_offsets_pending_once_and_preserves_expiry(client):
    row,_,m,w,source=setup(client);spend_all(row)
    native_return(client,row,500);native_return(client,row,1500)
    # Installation remains earned, so the coupon's retained installation slice
    # remains consumed: full goods return does NOT manufacture a whole coupon.
    coupon=next(t for t in info(row['id'])['tenders'] if t['kind']=='coupon');unit=coupon['units_detail'][0]
    assert unit['pending_credit_cents']<unit['credit_cents'] and not unit['restorable']
    assert coupon['expires_on'] and coupon['original_refund_policy']=='unused_anytime'


def test_release_uncaptured_no_cash_then_partial_cash_and_stale_duplicate(client):
    row,plan,m,w,source=setup(client,False)
    tender=next(t for t in plan['tenders'] if t['kind']=='principal')
    values=action_values(row,tender_id=tender['id']);key=uuid.uuid4().hex
    with SessionLocal() as db:version=db.scalar(select(Case.version).where(Case.id==row['id']))
    held=call(row['id'],'reserve',values,key=key,version=version)
    assert call(row['id'],'reserve',values,key=key,version=version)==held
    with pytest.raises(HTTPException) as error:call(row['id'],'release',action_values(row,tender_id=tender['id'],reason='客户确认改用现金'),version=version)
    assert error.value.status_code==409
    released=call(row['id'],'release',action_values(row,tender_id=tender['id'],reason='客户明确释放原占额，另行核对现金'))
    assert released['totals']['group_paid_cents']==0 and released['totals']['cash_collectable_cents']==1200
    native_cash(row,100,source['account_id']);assert info(row['id'])['totals']['cash_collectable_cents']==1100
    with pytest.raises(HTTPException):call(row['id'],'capture',action_values(row,tender_id=tender['id']))


def test_cross_store_role_and_rule_issuer_independent_approval(client):
    row,plan,member,w,source=setup(client)
    with pytest.raises(HTTPException) as error:info(row['id'],'inventory')
    assert error.value.status_code==403
    group.seed(2)
    with pytest.raises(HTTPException):info(row['id'],'finance',2)
    with pytest.raises(HTTPException):call(row['id'],'reserve',action_values(row,tender_id=plan['tenders'][0]['id']),'sales')
    with SessionLocal() as db:
        user=actor(db)
        with svc.authority(db,user):
            rule=benefits._rule(db,svc.one(db,BenefitWallet,w['id']).rule_id)
            with pytest.raises(HTTPException):rules.create(db,user,uuid.uuid4().hex,rule.id)


@pytest.mark.parametrize('kind',['coupon','package'])
def test_whole_original_unit_restore_after_expiry_offsets_only_once(client,monkeypatch,kind):
    from datetime import date
    row,_,m,w,source=setup(client,kind=kind,goods_only=True);spend_all(row)
    native_return(client,row,500);native_return(client,row,1500)
    detail=info(row['id']);tender=next(t for t in detail['tenders'] if t['kind']==kind);unit=tender['units_detail'][0]
    assert unit['pending_credit_cents']==400 and unit['restorable']
    original_expiry=tender['expires_on'];monkeypatch.setattr(svc,'today',lambda:date.fromisoformat(original_expiry)+timedelta(days=1))
    call(row['id'],'restore',action_values(row,unit_id=unit['id']))
    detail=info(row['id']);tender=next(t for t in detail['tenders'] if t['kind']==kind)
    assert tender['expired'] and tender['expires_on']==original_expiry
    assert tender['original_issuance_case_id']==source['case_id'] and tender['original_refund_policy']=='unused_anytime'
    assert tender['units_detail'][0]['pending_credit_cents']==0
    with pytest.raises(HTTPException):call(row['id'],'restore',action_values(row,unit_id=unit['id']))
    with SessionLocal() as db:
        user=actor(db)
        with svc.authority(db,user):
            wallet=svc.one(db,BenefitWallet,w['id']);assert wallet.balance_units==3
            entries=list(db.scalars(select(BenefitEntry).where(BenefitEntry.wallet_id==w['id'],BenefitEntry.case_id==row['id'])))
            assert sum(e.credit_cents for e in entries)==0
            case=svc.one(db,Case,row['id']);adjustments=svc.analytics_adjustments(db,case)
            ids={u.id for u in svc.rows(db,RetailGroupUnit,tender_id=tender['id'])}
            assert sum(a['credit_cents'] for a in adjustments if a['unit_id'] in ids)==0
            assert sum(a['consideration_cents'] for a in adjustments if a['unit_id'] in ids)==0
            assert sum(a['settlement_cents'] for a in adjustments if a['unit_id'] in ids)==0
            assert db.scalar(select(func.sum(RetailGroupSettlement.amount_cents)))==0


def test_existing_cash_cannot_be_reallocated_to_new_group_plan(client):
    row,values,member,w,source=setup(client,False,authorize=False)
    login(client,'finance');retail.pay(client,row,100,source['account_id'])
    with pytest.raises(HTTPException) as error:call(row['id'],'authorize',values,'admin')
    assert error.value.status_code==409 and '已有实际收款' in error.value.detail
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(RetailGroupPlan))==0


def test_actual_return_cannot_be_blocked_by_uncaptured_group_hold(client):
    row,plan,_,_,source=setup(client,False);tender=next(t for t in plan['tenders'] if t['kind']=='principal')
    call(row['id'],'reserve',action_values(row,tender_id=tender['id']))
    native_return(client,row,500)
    with pytest.raises(HTTPException) as error:call(row['id'],'capture',action_values(row,tender_id=tender['id']))
    assert '实际退货不受占额阻挡' in error.value.detail
    released=call(row['id'],'release',action_values(row,tender_id=tender['id'],reason='客户释放未核销方案并核对退货后的现金'))
    assert released['totals']['group_paid_cents']==0 and not sum(released['totals']['group_return_pending_cents'].values())
    assert released['totals']['cash_collectable_cents']==950


def test_rule_modes_are_explicit_and_admin_cannot_approve_own_request(client):
    items,customer,work,_=retail.setup(client)
    rule=benefit.rule(client,allowed_store_ids=[1])
    with SessionLocal() as db:config=rules.create(db,actor(db),uuid.uuid4().hex,rule['id'])
    values={'evidence_id':proof(config['case_id']),'scopes':[{'store_id':1,'item_id':items[0]['id'],'component':'goods','work_item_id':None}]}
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as error:rules.command(db,actor(db),config['case_id'],uuid.uuid4().hex,config['version'],'submit',values)
        assert '没有默认公司规则' in error.value.detail
    with SessionLocal() as db:config=rules.command(db,actor(db),config['case_id'],uuid.uuid4().hex,config['version'],'submit',values|svc.MODES)
    own_proof=proof(config['case_id'])
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as error:rules.command(db,actor(db),config['case_id'],uuid.uuid4().hex,config['version'],'approve',{'evidence_id':own_proof,'reason':'管理员尝试批准本人申请'})
        assert error.value.status_code==403
    with SessionLocal() as db:
        user=actor(db)
        with svc.authority(db,user):
            with pytest.raises(HTTPException):rules.guard_issuance(db,user,benefits._rule(db,rule['id']))


def test_wallet_without_issuance_binding_cannot_borrow_new_rule(client):
    row,values,member,w,source=setup(client,goods_only=True,authorize=False)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:connection.execute('DELETE FROM retail_group_wallets WHERE wallet_id=?',(w['id'],))
    with pytest.raises(HTTPException) as error:call(row['id'],'authorize',values,'admin')
    assert '发行时冻结' in error.value.detail


def test_nonempty_backup_pending_and_whole_restore_and_tamper_refusal(client,tmp_path):
    from app.retail_group_integrity import validate_retail_group
    from app.benefit_backup_integrity import validate_benefits_sqlite
    row,plan,m,w,source=setup(client,goods_only=True);spend_all(row)
    native_cash(row,500,source['account_id']);native_return(client,row,500)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:
        result=validate_retail_group(connection);assert result['verified_retail_group_returns']==1
        validate_benefits_sqlite(connection)
    native_return(client,row,1500)
    coupon=next(t for t in info(row['id'])['tenders'] if t['kind']=='coupon')
    call(row['id'],'restore',action_values(row,unit_id=coupon['units_detail'][0]['id']))
    path=tmp_path/'restore.sqlite'
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source_db,sqlite3.connect(path) as restored_db:source_db.backup(restored_db)
    with sqlite3.connect(path) as connection:
        assert validate_retail_group(connection)['verified_retail_group_restores']==1
        validate_benefits_sqlite(connection)
        connection.execute('UPDATE retail_group_settlements SET amount_cents=amount_cents+1 WHERE id=(SELECT MAX(id) FROM retail_group_settlements)')
        with pytest.raises(ValueError,match='结算'):validate_retail_group(connection)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source_db,sqlite3.connect(path) as restored_db:source_db.backup(restored_db)
    with sqlite3.connect(path) as connection:
        connection.execute('DELETE FROM retail_group_wallets')
        with pytest.raises(ValueError,match='发行'):validate_retail_group(connection)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source_db,sqlite3.connect(path) as restored_db:source_db.backup(restored_db)
    with sqlite3.connect(path) as connection:
        connection.execute('DELETE FROM retail_group_cash_allocations WHERE id=(SELECT MIN(id) FROM retail_group_cash_allocations)')
        with pytest.raises(ValueError,match='现金'):validate_retail_group(connection)


def test_competing_original_reservations_only_one_wins(client):
    from concurrent.futures import ThreadPoolExecutor
    row,plan,member,w,source=setup(client,False)
    tender=next(t for t in plan['tenders'] if t['kind']=='principal')
    values=action_values(row,tender_id=tender['id'])
    with SessionLocal() as db:version=db.scalar(select(Case.version).where(Case.id==row['id']))
    def attempt(_):
        try:call(row['id'],'reserve',values,version=version);return 200
        except HTTPException as error:return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(attempt,[1,2]))==[200,409]
    with SessionLocal() as db:
        user=actor(db)
        with svc.authority(db,user):assert svc.group._member(db,member['id'],1).reserved_cents==300


def test_bonus_fen_restore_never_creates_cash_or_coupon_units(client):
    row,plan,member,w,source=setup(client,kind='bonus');spend_all(row)
    with SessionLocal() as db:before=db.scalar(select(func.count()).select_from(CashEntry))
    native_return(client,row,500)
    tender=next(t for t in info(row['id'])['tenders'] if t['kind']=='bonus');unit=tender['units_detail'][0]
    assert unit['pending_credit_cents']>0 and unit['restorable'] and not unit['pending_original_unit']
    call(row['id'],'restore',action_values(row,unit_id=unit['id']))
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==before
        user=actor(db)
        with svc.authority(db,user):
            wallet=svc.one(db,BenefitWallet,w['id'])
            assert wallet.balance_units==200+unit['pending_credit_cents']
            entry=db.scalar(select(BenefitEntry).where(BenefitEntry.wallet_id==w['id'],BenefitEntry.purpose=='reverse'))
            assert entry.units==unit['pending_credit_cents'] and entry.cash_id is None


def test_a_issues_b_consumes_and_restores_without_foreign_cash_or_file_access(client):
    from app.retail_group_integrity import validate_retail_group
    row,plan,member,w,source=setup(client,goods_only=True,store=2);spend_all(row)
    view=info(row['id']);tender=next(t for t in view['tenders'] if t['kind']=='coupon')
    assert tender['issuer_store_id']==1 and 'original_issuance_case_id' not in tender
    login(client,'finance')
    assert client.get('/api/flow/cases/'+str(source['case_id'])).status_code==404
    native_return(client,row,500);native_return(client,row,1500)
    unit=next(t for t in info(row['id'])['tenders'] if t['kind']=='coupon')['units_detail'][0]
    call(row['id'],'restore',action_values(row,unit_id=unit['id']))
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry).where(CashEntry.store_id==2))==0
        user=actor(db,'finance',2)
        with svc.authority(db,user):
            assert svc.one(db,BenefitWallet,w['id']).balance_units==3
            assert db.scalar(select(func.sum(BenefitSettlement.amount_cents)).where(BenefitSettlement.side=='center'))==0
            assert db.scalar(select(func.sum(RetailGroupSettlement.amount_cents)))==0
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:assert validate_retail_group(connection)['verified_retail_group_plans']==1


def test_legacy_release_guard_and_external_credit_fail_closed(client):
    row,plan,member,w,source=setup(client,False)
    tender=next(t for t in plan['tenders'] if t['kind']=='principal')
    call(row['id'],'reserve',action_values(row,tender_id=tender['id']))
    with SessionLocal() as db:
        user=actor(db,'finance');case=svc.retail.get_order(db,user,row['id'])
        with svc.group.authority(db,user):
            with pytest.raises(HTTPException) as error:svc.guard_legacy_wallet_action(db,case)
            assert error.value.status_code==409 and '旧维修权益入口' in error.value.detail
        with svc.authority(db,user):
            svc.guard_legacy_wallet_action(db,case)
            for action in ('advance_apply','cash_correction','statement_collect'):
                with pytest.raises(HTTPException):svc.guard_external_settlement(db,case,action)
            assert svc.group._member(db,member['id'],1).reserved_cents==300


def test_explicit_finance_handoff_keeps_original_wallet_and_receipt(client):
    row,plan,member,w,source=setup(client,False)
    current=info(row['id'])
    with SessionLocal() as db:admin_id=db.scalar(select(User.id).where(User.username=='admin'))
    changed=call(row['id'],'reassign',{'plan_version':current['plan_version'],'task_key':'retail_group_payment','assignee_id':admin_id,'due_date':today()+timedelta(days=1),'reason':'明确转交获权管理员核对原财务待办'},'manager')
    tender=next(t for t in changed['tenders'] if t['kind']=='principal')
    with pytest.raises(HTTPException):call(row['id'],'reserve',action_values(row,tender_id=tender['id']))
    call(row['id'],'reserve',action_values(row,tender_id=tender['id'],username='admin'),'admin')


def test_authorized_original_reuse_keeps_uploader_and_each_actual_actor(client):
    from app.retail_group_integrity import validate_retail_group
    row,values,member,w,source=setup(client,False,authorize=False)
    original=proof(row['id'],'service')
    plan=call(row['id'],'authorize',values|{'evidence_id':original},'admin')
    tender=next(t for t in plan['tenders'] if t['kind']=='principal')
    for action in ('reserve','capture'):
        call(row['id'],action,action_values(row,tender_id=tender['id'])|{'evidence_id':original})
    with SessionLocal() as db:
        user=actor(db,'finance')
        with svc.authority(db,user):
            asset=svc.one(db,FileAsset,original)
            assert asset.created_by==db.scalar(select(User.id).where(User.username=='service'))
            original_plan=svc.require_plan(db,svc.one(db,Case,row['id']))
            assert original_plan.actor_id==db.scalar(select(User.id).where(User.username=='admin'))
            entry=db.scalar(select(GroupEntry).where(GroupEntry.case_id==row['id'],GroupEntry.purpose=='capture'))
            assert entry.evidence_id==original and entry.actor_id==user.id
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:
        assert validate_retail_group(connection)['verified_retail_group_plans']==1


@pytest.mark.parametrize('source_kind',['other_case','other_store','generated'])
def test_reused_evidence_still_requires_this_store_case_and_uploaded_original(client,source_kind):
    row,values,member,w,source=setup(client,False,authorize=False)
    if source_kind=='generated':bad=proof(row['id'],'service',generated=True)
    elif source_kind=='other_store':bad=proof(group.seed(2)['case_id'],'admin')
    else:bad=proof(source['case_id'],'service')
    with pytest.raises(HTTPException) as error:
        call(row['id'],'authorize',values|{'evidence_id':bad},'admin')
    assert error.value.status_code==422 and '本单实际上传' in error.value.detail
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RetailGroupPlan))==0
        user=actor(db)
        with svc.authority(db,user):assert svc.group._member(db,member['id'],1).reserved_cents==0


def test_local_wallet_does_not_grant_original_case_access(client):
    row,plan,member,w,source=setup(client)
    with SessionLocal() as db:
        user=actor(db,'sales');case=db.scalar(select(Case).where(Case.id==row['id']));case.owner_id=user.id;db.commit()
    # The employee may handle this assigned retail order, but the linked member
    # wallet does not make the earlier repair/issuance case theirs to inspect.
    local=info(row['id'],'sales')
    coupon=next(t for t in local['tenders'] if t['kind']=='coupon')
    assert coupon['issuer_store_id']==1 and 'original_issuance_case_id' not in coupon
    assert 'consideration_cents' not in coupon and 'settlement_cents' not in coupon
    assert 'group_recognized_cents' not in local['totals'] and 'service_discount_borne_cents' not in local['totals']
    login(client,'sales');assert client.get('/api/flow/cases/'+str(source['case_id'])).status_code==404
    financial=info(row['id'],'finance')
    assert next(t for t in financial['tenders'] if t['kind']=='coupon')['original_issuance_case_id']==source['case_id']


def test_new_issuance_refuses_changed_local_approved_item(client):
    values={'sku':'RULE-ITEM-'+uuid.uuid4().hex[:8],'name':'合成未进货目录','unit':'件','reorder':'0','active':True}
    item=retail.master(client,'items',values)
    rule,_=approved_rule(client,[item])
    # A master can be disabled without changing any past approved snapshot.
    changed=client.put('/api/flow/master/items/'+str(item['id']),json={'version':item['version'],'values':values|{'active':False}})
    assert changed.status_code==200,changed.text
    with SessionLocal() as db:
        user=actor(db)
        with svc.authority(db,user):
            with pytest.raises(HTTPException) as error:rules.guard_issuance(db,user,benefits._rule(db,rule['id']))
            assert error.value.status_code==409 and '批准商品已停用' in error.value.detail
            assert db.scalar(select(func.count()).select_from(BenefitWallet))==0


def test_original_item_unit_cannot_be_reinterpreted_by_id_alone(client):
    row,values,member,w,source=setup(client,goods_only=True,authorize=False)
    # Simulate a mismatched restored original. Item id equality must not make
    # a coupon approved for boxes cover a previously agreed piece quantity.
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:connection.execute("UPDATE retail_group_scopes SET unit='箱'")
    with pytest.raises(HTTPException) as error:call(row['id'],'authorize',values,'admin')
    assert error.value.status_code==409 and '单位或安装项目' in error.value.detail
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(RetailGroupPlan))==0
