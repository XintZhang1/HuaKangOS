"""Zero-price sales gifts: independent authority, real work, original cost."""
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select,func

from app.main import app
from app.db import SessionLocal
from app.models import CashEntry,Store,User,UserStore
from app.flow_models import Case,Item,PaymentLink
from app.addon_models import AddonQuote,AddonApproval,AddonReservation,AddonAcceptance,AddonDispatch,AddonReturnPosting
from app import addon_service as service
from tests.conftest import login,TEST_DIR
from tests import test_addon_orders as a

technician=a.technician
restore_addon=a.restore_addon


def gift_line(items,work,key='first',qty=2000,goods=0,installation=0):
    return dict(line_key=key,item_id=items[0]['id'],work_item_id=work['id'],quantity_milli=qty,
        goods_unit_cents=goods,installation_unit_cents=installation,gift_reason='本次购车赠送组件及实际安装',gift_cost_bearer='selling_store')


def quote(c,row,items,work,**kw):
    return a.cmd(c,row,'quote',dict(lines=[gift_line(items,work,**kw)],discount_cents=0,reason='销售约定本店承担真实赠送成本'))


def approve(c,row):
    who=c.get('/api/auth/me').json()['username'];login(c,'manager')
    row=a.cmd(c,row,'approve',dict(minimum_cents=0,confirm_gift=True,reason='独立复核赠送原因及本销售店成本承担',evidence_id=a.proof(c,row)))
    login(c,who);return row


def gifted(c):
    row,items,work,source,vin=a.setup(c)
    row=a.authorized(c,approve(c,quote(c,row,items,work)))
    return row,items,work,source,vin


def test_zero_gift_real_installation_customer_acceptance_original_returns_no_cash_or_invoice(client):
    row,items,work,source,vin=gifted(client)
    assert row['totals']['charge_cents']==row['totals']['receivable_cents']==0
    assert not any(t['key']=='addon_receive' for t in row['tasks'])
    a.cmd(client,row,'receive',dict(amount_cents=1,account_id=1,reference='forbidden-fake-cash',evidence_id=a.proof(client,row,'receipt')),409)
    from tests import test_invoices as invoices
    login(client,'finance');invoices.create(client,row['id'],1,status=409);login(client,'admin')
    row=a.quality(client,a.install(client,a.dispatch(client,row,vin)),False)
    a.cmd(client,row,'accept',dict(quote_id=row['quote']['id'],evidence_id=a.proof(client,row)),409)
    row=a.cmd(client,row,'rectify',dict(inspection_id=row['inspections'][0]['id'],result='实际重新紧固后复检',evidence_id=a.proof(client,row,'inspection')))
    row=a.quality(client,row)
    assert row['state']!='completed' and any(t['key']=='addon_accept' for t in row['tasks'])
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as failure:service.guard_order_delivery(db,db.get(Case,source['id']))
        assert failure.value.status_code==409
    acceptance=dict(request_id=uuid.uuid4().hex,version=a.detail(client,row)['version'],values=dict(quote_id=row['quote']['id'],evidence_id=a.proof(client,row)))
    row=a.cmd(client,row,'accept',body=acceptance);assert row['state']=='completed'
    assert a.cmd(client,row,'accept',body=acceptance)==row
    a.cmd(client,row,'accept',status=409,body={**acceptance,'request_id':uuid.uuid4().hex})
    with SessionLocal() as db:
        service.guard_order_delivery(db,db.get(Case,source['id']))
        fact=db.scalar(select(AddonAcceptance));assert fact.amount_cents==0 and fact.value_cents==246
        assert db.get(Item,items[0]['id']).inventory_value_cents==62
        assert service.actual_income_rows(db,db.get(Case,row['id']))[0]['amount_cents']==0
        assert service.invoice_source_amount(db,db.get(Case,row['id']))==0
    for qty in (333,667,1000):
        row=a.resolve(client,a.resolve(client,a.resolution(client,row,'return',qty),'resolution_approve'),'resolution_consent')
        row=a.resolve(client,row,'return_receive',passed=True)
    assert row['totals']['cost_cents']==row['totals']['paid_cents']==row['totals']['refund_due_cents']==0
    assert not row['payments'] and not row['credits']
    with SessionLocal() as db:
        posts=list(db.scalars(select(AddonReturnPosting)))
        assert sum(p.quantity_milli for p in posts)==2000 and sum(p.value_cents for p in posts)==246
        assert all(p.goods_cents==p.installation_cents==p.retained_cents==0 for p in posts)
        assert (db.get(Item,items[0]['id']).quantity_milli,db.get(Item,items[0]['id']).inventory_value_cents)==(2500,308)
        assert db.scalar(select(func.count()).select_from(CashEntry))==db.scalar(select(func.count()).select_from(PaymentLink))==0
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as restored:validate_sqlite(restored)


@pytest.mark.parametrize('change',[
    {'gift_reason':''},{'gift_reason':'短'},{'gift_cost_bearer':None},{'gift_cost_bearer':'headquarters'},
    {'burden_store_id':2},{'goods_unit_cents':1},
])
def test_new_zero_line_requires_explicit_reason_and_actual_selling_store(client,change):
    row,items,work,source,vin=a.setup(client);line=gift_line(items,work);line.update(change)
    a.cmd(client,row,'quote',dict(lines=[line],reason='明确零价原项目'),422)
    with SessionLocal() as db:assert not db.scalar(select(AddonQuote.id)) and not db.scalar(select(AddonReservation.id))


def test_full_discount_requires_gift_terms_and_independent_explicit_approval(client):
    row,items,work,source,vin=a.setup(client);line=gift_line(items,work,goods=500,installation=100)
    value=dict(lines=[{k:v for k,v in line.items() if not k.startswith('gift_')}],discount_cents=1200,reason='全额优惠仍须明确赠送')
    a.cmd(client,row,'quote',value,422);value['lines']=[line];row=a.cmd(client,row,'quote',value)
    assert row['totals']['quoted_cents']==0 and row['quote']['discount_cents']==1200
    payload=dict(minimum_cents=0,confirm_gift=True,reason='报价人不能自行批准赠送',evidence_id=a.proof(client,row))
    a.cmd(client,row,'approve',payload,403)
    login(client,'manager');payload.update(evidence_id=a.proof(client,row),confirm_gift=False)
    a.cmd(client,row,'approve',payload,409)
    payload.update(confirm_gift=True,minimum_cents=1);a.cmd(client,row,'approve',payload,409)
    payload.update(allow_below_minimum=True);body=dict(request_id=uuid.uuid4().hex,version=a.detail(client,row)['version'],values=payload)
    row=a.cmd(client,row,'approve',body=body);assert a.cmd(client,row,'approve',body=body)==row
    a.cmd(client,row,'approve',status=409,body={**body,'request_id':uuid.uuid4().hex})
    assert row['quote_history'][0]['approval']['gift_confirmed']
    login(client,'admin');row=a.authorized(client,row)
    assert row['quote']['gift_terms']['first']['burden_store_id']==1


def test_zero_unissued_cancel_has_no_stock_or_fictitious_customer_receipt(client):
    row,items,work,source,vin=gifted(client)
    row=a.resolve(client,a.resolve(client,a.resolution(client,row,'cancel',2000),'resolution_approve'),'resolution_consent')
    assert row['state']=='completed' and not row['acceptances'] and not row['payments']
    assert not row['tasks'] and row['totals']['charge_cents']==0
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(AddonReservation.quantity_milli)))==0
        assert not db.scalar(select(AddonDispatch.id))
        assert db.get(Item,items[0]['id']).quantity_milli==2500
        service.guard_order_delivery(db,db.get(Case,source['id']))


def test_zero_gift_rejects_customer_advance_allocation_and_preserves_real_advance(client):
    from tests import test_business_finance as finance
    from app.business_finance_models import FinanceCreditLink
    row,items,work,source,vin=gifted(client);customer={'id':row['customer_id']}
    prepaid,account=finance.advance(client,customer,600);original=finance.current_advance(client,customer)
    finance.create(client,customer,'advance_apply',dict(amount_cents=1,advance_id=original['id'],advance_version=original['version'],target_case_id=row['id'],target_version=a.source_detail(client,row)['version']),409)
    assert finance.current_advance(client,customer)['balance_cents']==600
    assert a.detail(client,row)['totals']['paid_cents']==0
    with SessionLocal() as db:
        assert not db.scalar(select(FinanceCreditLink.id))
        assert db.scalar(select(func.count()).select_from(CashEntry))==1


def test_gift_terms_frozen_after_authority_and_paid_addition_has_independent_delta(client):
    row,items,work,source,vin=gifted(client);row=a.accept(client,a.quality(client,a.install(client,a.dispatch(client,row,vin))))
    original=row['quote']['id'];line=gift_line(items,work);line['gift_reason']='不能把原赠送改写为其他理由'
    a.cmd(client,row,'quote',dict(lines=[line],reason='尝试重写已获准赠送'),409)
    line=gift_line(items,work);line['goods_unit_cents']=100
    a.cmd(client,row,'quote',dict(lines=[line],reason='尝试将原赠送改为收费'),409)
    lines=[gift_line(items,work),dict(line_key='paid',item_id=items[1]['id'],work_item_id=work['id'],quantity_milli=1000,goods_unit_cents=100,installation_unit_cents=50)]
    row=a.cmd(client,row,'quote',dict(lines=lines,reason='新增单独收费安装项目'))
    assert row['quote_history'][0]['quote']['id']==original and row['totals']['charge_cents']==150
    row=approve(client,row)
    a.cmd(client,row,'authorize',dict(quote_id=original,evidence_id=a.proof(client,row)),409)
    row=a.authorized(client,row);row=a.pay(client,row,150,a.bank(client));row=a.accept(client,a.quality(client,a.install(client,a.dispatch(client,row,vin,1000,'paid'))))
    assert row['state']=='completed' and row['totals']['paid_cents']==150
    with SessionLocal() as db:
        assert [x.amount_cents for x in db.scalars(select(AddonAcceptance).order_by(AddonAcceptance.id))]==[0,150]
        assert db.scalar(select(func.count()).select_from(CashEntry))==1


def test_gift_permissions_store_scope_and_competing_authority(client):
    one,items,work,source,vin=a.setup(client);one=approve(client,quote(client,one,items,work))
    src=a.source_detail(client,source)
    r=client.post(a.API,json=dict(request_id=uuid.uuid4().hex,source_order_id=src['id'],source_version=src['version'],due_date=src['due_date'],reason='另一原销售赠送申请'))
    assert r.status_code==201,r.text
    two=approve(client,quote(client,r.json(),items,work));requests=[]
    for row in (one,two):requests.append((row,dict(request_id=uuid.uuid4().hex,version=a.detail(client,row)['version'],values=dict(quote_id=row['quote']['id'],evidence_id=a.proof(client,row)))))
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in requests]
        for c in clients:login(c,'admin')
        def post(pair):
            c,(row,body)=pair;return c.post(a.API+f"/{row['id']}/actions/authorize",json=body).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(post,zip(clients,requests)))==[200,409]
    with SessionLocal() as db:assert db.scalar(select(func.sum(AddonReservation.quantity_milli)))==2000
    login(client,'inventory');hidden=a.detail(client,one)
    assert 'totals' not in hidden and 'gift_terms' not in hidden['quote'] and 'gift' not in hidden['lines'][0]
    projected=client.get('/api/flow/cases/'+str(one['id']));assert projected.status_code==200 and 'gift_reason' not in projected.text and 'gift_terms' not in projected.text
    a.cmd(client,one,'approve',dict(minimum_cents=0,confirm_gift=True,reason='库管无权批准赠送',evidence_id=1),403)
    login(client,'admin')
    with SessionLocal() as db:
        db.add(Store(id=2,code='GIFTO',name='赠送测试另店'));u=db.scalar(select(User).where(User.username=='admin'));db.add(UserStore(user_id=u.id,store_id=2));db.commit()
    assert client.get(a.API+f"/{one['id']}",headers={'X-Store-ID':'2'}).status_code==404
    assert client.post(a.API+f"/{one['id']}/actions/authorize",headers={'X-Store-ID':'2'},json=requests[0][1]).status_code==404


def test_legacy_zero_lines_keep_original_digest_and_never_infer_gift_history(client):
    row,items,work,source,vin=a.setup(client)
    lines=[gift_line(items,work,qty=1000),dict(line_key='paid',item_id=items[1]['id'],work_item_id=work['id'],quantity_milli=1000,goods_unit_cents=100,installation_unit_cents=50)]
    row=a.authorized(client,approve(client,a.cmd(client,row,'quote',dict(lines=lines,reason='模拟迁移前混合报价'))))
    # Explicit synthetic old-schema snapshot: v1 allowed zero lines inside a
    # positive quote without representing them as an independently defined gift.
    from app.flow_engine import request_digest
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:
        connection.row_factory=sqlite3.Row
        ls=[dict(x) for x in connection.execute('SELECT * FROM addon_lines ORDER BY id')]
        keys=['line_key','item_id','work_item_id','sku','name','unit','work_code','work_name','quantity_milli','goods_unit_cents','installation_unit_cents','goods_cents','installation_cents']
        digest=request_digest('addon_quote',[{k:x[k] for k in keys} for x in ls])
        connection.execute("UPDATE addon_quotes SET pricing_version=1,gift_terms='{}',digest=?",(digest,))
        connection.execute('UPDATE addon_approvals SET gift_confirmed=0')
    plain=[{k:v for k,v in line.items() if not k.startswith('gift_')} for line in lines]
    row=a.cmd(client,row,'quote',dict(lines=plain,reason='保留原已授权行，不补写旧赠送'))
    assert row['quote']['pricing_version']==2 and row['quote']['gift_terms']=={}
    assert row['quote_history'][0]['quote']['pricing_version']==1 and row['quote_history'][0]['quote']['gift_terms']=={}
    with SessionLocal() as db:assert db.get(AddonQuote,row['quote_history'][0]['quote']['id']).digest==digest


def test_restored_gift_rejects_changed_terms_authority_and_fake_completion(client):
    row,items,work,source,vin=gifted(client);row=a.quality(client,a.install(client,a.dispatch(client,row,vin)))
    from app.addon_backup_integrity import validate
    changes=[("UPDATE addon_approvals SET gift_confirmed=0",()),
        ("UPDATE addon_quotes SET gift_terms=?",(json.dumps({'first':{'reason':'篡改赠送','cost_bearer':'selling_store','burden_store_id':2}}),)),
        ("UPDATE addon_quotes SET gift_terms='{}'",()),
        ("UPDATE flow_cases SET state='completed' WHERE id=?",(row['id'],))]
    for sql,args in changes:
        with sqlite3.connect(TEST_DIR/'test.sqlite') as source_db,sqlite3.connect(':memory:') as restored:
            source_db.backup(restored);validate(restored);restored.execute(sql,args)
            with pytest.raises(ValueError,match='加装'):validate(restored)
    a.accept(client,row)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source_db,sqlite3.connect(':memory:') as restored:
        source_db.backup(restored);validate(restored)
        restored.execute('UPDATE addon_installations SET quantity_milli=quantity_milli-1')
        with pytest.raises(ValueError,match='未安装'):validate(restored)


def test_addon_gift_migration_preserves_nonempty_legacy_snapshots(tmp_path):
    import importlib
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine,text
    path=tmp_path/'synthetic-legacy-addon.sqlite';engine=create_engine('sqlite:///'+path.as_posix())
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE addon_quotes (id INTEGER PRIMARY KEY,goods_cents BIGINT NOT NULL,installation_cents BIGINT NOT NULL,discount_cents BIGINT NOT NULL,digest VARCHAR(64) NOT NULL,CONSTRAINT ck_addon_quote_money CHECK(goods_cents>=0 AND installation_cents>=0 AND discount_cents>=0 AND goods_cents+installation_cents>0))'))
        connection.execute(text('CREATE TABLE addon_approvals (id INTEGER PRIMARY KEY,reason VARCHAR(1000) NOT NULL)'))
        connection.execute(text("INSERT INTO addon_quotes VALUES(1,123,45,6,'original-digest')"))
        connection.execute(text("INSERT INTO addon_approvals VALUES(1,'original-approval')"))
        module=importlib.import_module('migrations.versions.w35j_addon_gifts')
        with Operations.context(MigrationContext.configure(connection)):module.upgrade()
        assert tuple(connection.execute(text('SELECT goods_cents,installation_cents,discount_cents,digest,pricing_version,gift_terms FROM addon_quotes')).one())==(123,45,6,'original-digest',1,'{}')
        assert connection.execute(text('SELECT gift_confirmed FROM addon_approvals')).scalar()==0
        connection.execute(text("INSERT INTO addon_quotes VALUES(2,0,0,0,'new-digest',2,'{}')"))
    engine.dispose()
