"""Actual business entry points with a reviewed empty-store ownership policy."""
import sqlite3
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func

from app import business_entity_service as entities
from app.business_entity_models import CaseEntityContext, CashEntityContext
from app.business_entity_integrity import validate_business_entities
from app.db import SessionLocal, today
from app.flow_models import Case, PaymentLink
from app.models import CashEntry
from tests.conftest import login, TEST_DIR
from tests.test_business_entities import setup_policy, actor, account
from tests.test_workflow import master, evidence, order as basic_order
from tests import test_repair_orders as repair
from tests import test_invoices as invoice
from tests import test_aftercare as aftercare
from tests import test_insurance_orders as insurance
from tests import test_business_entities as be


def long_policy(c):
    """Exercise approved upper-width names through the real billing contract."""
    name='合成经营主体'+'测试'*83
    tax='SYNTHETIC'+'9'*21
    be.approved(c,'revision',{'code':'SYNTH-LONG','tax_identifier':tax,'legal_name':name,'registered_address':'完整虚构测试登记地址'})
    rev=next(r for r in be.config(c)['revisions'] if r['code']=='SYNTH-LONG')
    be.store_binding(c,rev);bank=be.account(c)
    be.approved(c,'account_binding',be.account_details(bank,rev))
    be.approved(c,'policy',{'binding_id':be.config(c)['store_binding']['id'],'policy_version':1})
    return rev,bank


def labor_repair(c):
    customer=master(c,'customers',{'name':'主体归属合成客户','phone':'13900101010','contact_allowed':True,'note':''})
    work=repair.typed(c,'work_items',{'code':'ENTITY-WORK','name':'合成检查作业','billing_unit':'job','standard_fee_cents':1001})
    row=repair.create(c,customer)
    row=repair.cmd(c,row,'quote',{'reason':'客户同意本次独立作业报价','discount_cents':0,'lines':[{'kind':'work','source_id':work['id'],'quantity_milli':1000,'unit_price_cents':1001}]})
    row=repair.authorize(c,row)
    row=repair.cmd(c,row,'start',{'result':'按本版授权实际开工'})
    row=repair.cmd(c,row,'finish',{'result':'全部授权作业实际完成'})
    row=repair.cmd(c,row,'quality',{'passed':True,'result':'本次实际检查合格','evidence_id':evidence(c,row,'inspection')})
    return repair.allocate(c,row)


def restored():
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as copy:
        source.backup(copy)
        return validate_business_entities(copy)


def test_repair_cash_invoice_and_aftercare_keep_original_approved_entity(client):
    rev,bank=setup_policy(client);row=labor_repair(client)
    # An active, but unapproved, bank account must not create a cash fact.
    wrong=account(client,'未批准归属的合成账户')
    repair.cmd(client,row,'receive',{'allocation_id':row['allocations'][0]['id'],'amount_cents':1001,'account_id':wrong['id'],'reference':uuid.uuid4().hex,'evidence_id':evidence(client,row,'receipt')},409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==0
    row=repair.receive(client,row,row['allocations'][0],1001,bank['id'])
    row=repair.cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    login(client,'finance')
    src=client.get('/api/invoices/sources/'+str(row['id']));assert src.status_code==200,src.text
    assert src.json()['issuer']=={'legal_name':rev['legal_name'],'tax_identifier':rev['tax_identifier']}
    bad=invoice.request_body(client,row['id'])
    rejected=client.post('/api/invoices/orders',json=bad);assert rejected.status_code==409,rejected.text
    body={**bad,'request_id':uuid.uuid4().hex,'issuer_name':rev['legal_name'],'issuer_tax_id':rev['tax_identifier']}
    result=client.post('/api/invoices/orders',json=body);assert result.status_code==201,result.text
    bill=result.json();invoice.record(client,invoice.submit(client,invoice.approve(client,bill)))
    login(client,'admin');request=aftercare.create(client,row)
    request=aftercare.plan(client,request,333)
    request=aftercare.applied(client,aftercare.confirmed(client,aftercare.approved(client,request)))
    request=aftercare.refund(client,request,bank['id'],333)
    assert request['state']=='completed'
    with SessionLocal() as db:
        user=actor(db)
        with entities.authority(db,user):
            contexts={r.case_id:r for r in db.scalars(select(CaseEntityContext))}
            assert contexts[bill['id']].source_case_id==contexts[request['id']].source_case_id==row['id']
            assert {r.revision_id for r in contexts.values()}=={rev['revision_id']}
            cash=list(db.scalars(select(CashEntry).order_by(CashEntry.id)))
            links=list(db.scalars(select(CashEntityContext).order_by(CashEntityContext.cash_id)))
            assert [r.amount_cents for r in cash]==[1001,333]
            assert links[1].original_cash_id==cash[0].id and links[1].case_id==request['id']
    assert restored()['verified_entity_cash']==2


def test_insurance_original_principal_and_commission_returns_preserve_cash_context(client):
    rev,bank=setup_policy(client);row,_,_=insurance.setup(client);row=insurance.ready(client,row);aid=bank['id']
    row=insurance.cash(client,row,'receive',10001,aid)
    row=insurance.cash(client,row,'disburse',10001,aid,tender_id=row['tenders'][0]['id'])
    row=insurance.issued(client,row);row=insurance.commission(client,row,501)
    row=insurance.cash(client,row,'commission_receive',501,aid,confirmation_id=row['commissions'][-1]['id'])
    row=insurance.apply_plan(client,insurance.termination(client,row,2000))
    row=insurance.cash(client,row,'insurer_return',8001,aid,original_id=row['pass_entries'][0]['id'])
    row=insurance.cash(client,row,'refund',8001,aid,plan_id=row['plans'][-1]['id'],tender_id=row['tenders'][0]['id'])
    row=insurance.commission(client,row,100)
    row=insurance.cash(client,row,'commission_return',401,aid,confirmation_id=row['commissions'][-1]['id'],original_id=row['commission_payments'][0]['id'])
    assert row['state']=='completed'
    with SessionLocal() as db:
        user=actor(db)
        with entities.authority(db,user):
            cash=list(db.scalars(select(CashEntry).order_by(CashEntry.id)))
            ctx=list(db.scalars(select(CashEntityContext).order_by(CashEntityContext.cash_id)))
            assert len(cash)==len(ctx)==6 and all(r.case_id==row['id'] for r in ctx)
            assert [r.original_cash_id for r in ctx]==[None,None,None,cash[1].id,cash[0].id,cash[2].id]
            assert sum(r.amount_cents*(1 if r.direction=='in' else -1) for r in cash)==100
    assert restored()['verified_entity_cash']==6


def test_production_new_business_refuses_missing_policy_without_partial_case(client,monkeypatch):
    # Override only this domain's policy; no production server or database is used.
    monkeypatch.setattr(entities,'settings',SimpleNamespace(environment='production',timezone='Asia/Shanghai'))
    customer=master(client,'customers',{'name':'合成待启用客户','phone':'13900101011','contact_allowed':True,'note':''})
    result=client.post('/api/repair-orders',json={'request_id':uuid.uuid4().hex,'customer_id':customer['id'],'plate':'TEST-ENTITY','problem':'未批准主体不得正式开单','due_date':today().isoformat()})
    assert result.status_code==409 and '主体策略' in result.json()['detail']
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Case))==0


def test_production_new_invoice_uses_dedicated_source_and_issuer_flow(client,monkeypatch):
    from app import config
    monkeypatch.setattr(config,'settings',SimpleNamespace(environment='production'))
    login(client,'finance')
    response=client.post('/api/flow/cases',json={'request_id':uuid.uuid4().hex,'kind':'invoice','values':{}})
    assert response.status_code==409 and '开票与原票冲红' in response.json()['detail']
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Case))==0


def test_new_generic_order_has_frozen_context_and_cross_store_cannot_read_it(client):
    rev,_=setup_policy(client);row=basic_order(client)
    login(client,'inventory')
    catalog=client.get('/api/vehicle-procurement/catalog');assert catalog.status_code==200,catalog.text
    assert catalog.json()['operating_party']==rev['legal_name']
    assert set(catalog.json())=={'operating_party','can_read','can_create','can_money','actions'}
    login(client)
    with SessionLocal() as db:
        user=actor(db)
        with entities.authority(db,user):
            context=db.scalar(select(CaseEntityContext).where(CaseEntityContext.case_id==row['id']))
            assert context.revision_id==rev['revision_id'] and context.source_case_id is None
    result=client.post('/api/stores',json={'code':'ENTITY-OTHER','name':'合成另外门店'});assert result.status_code==201,result.text
    client.headers['X-Store-ID']=str(result.json()['id'])
    assert client.get('/api/flow/cases/'+str(row['id'])).status_code==404
    assert client.get('/api/vehicle-procurement/catalog').json()['operating_party'] is None
    assert restored()['verified_entity_cases']==1


def test_approved_long_legal_identity_survives_invoice_application_and_actual_result(client):
    rev,bank=long_policy(client);row=labor_repair(client)
    row=repair.receive(client,row,row['allocations'][0],1001,bank['id'])
    row=repair.cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    login(client,'finance')
    payload={**invoice.request_body(client,row['id']),'issuer_name':rev['legal_name'],'issuer_tax_id':rev['tax_identifier']}
    response=client.post('/api/invoices/orders',json=payload);assert response.status_code==201,response.text
    bill=invoice.record(client,invoice.submit(client,invoice.approve(client,response.json())))
    assert bill['issuer_name']==rev['legal_name'] and bill['issuer_tax_id']==rev['tax_identifier']
    assert restored()['verified_entity_cases']==2
