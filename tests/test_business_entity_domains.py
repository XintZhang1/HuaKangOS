from fastapi import HTTPException
"""Reviewed empty-store policies exercised through real procurement/finance APIs."""
import uuid,sqlite3,json
import pytest
from sqlalchemy import select,func
from app.db import SessionLocal,today
from app.models import Store,User,UserStore,CashEntry
from app.flow_models import Case,Item,PaymentLink,FlowEvent,VehicleHold,Task
from app.business_entity_models import CaseEntityContext,CashEntityContext
from app.business_entity_integrity import validate_business_entities
from app import business_entity_service as entities
from tests.conftest import login,TEST_DIR
from tests import test_business_entities as be,test_procurement as p,test_vehicle_procurement as vp
from tests import test_transfers as tr,test_vehicle_transfers as vt,test_reconciliation as recon
from tests import test_business_finance as bf,test_retail as retail,test_group_membership as group
from tests.test_workflow import master,evidence


def restore():
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as copy:
        source.backup(copy);return validate_business_entities(copy)


def contexts(sid=1):
    with SessionLocal() as db:
        from app.tenancy import set_scope,project_user
        set_scope(db,[sid],sid);user=project_user(db.scalar(select(User).where(User.username=='admin')),'admin')
        with entities.authority(db,user):
            return {r.case_id:{c.name:getattr(r,c.name) for c in r.__table__.columns} for r in db.scalars(select(CaseEntityContext))},[{c.name:getattr(r,c.name) for c in r.__table__.columns} for r in db.scalars(select(CashEntityContext).order_by(CashEntityContext.cash_id))]


def two_policies(c):
    rev,a=be.setup_policy(c)
    with SessionLocal() as db:
        db.add(Store(id=2,code='ENTITY-TWO',name='完全合成乙店'));db.flush()
        for user in db.scalars(select(User).where(User.role.in_(['manager','finance']))):db.add(UserStore(user_id=user.id,store_id=2,role=user.role))
        db.commit()
    tr.switch(c,2);other=be.revision(c,'SYNTH-B','完全合成乙经营公司');be.store_binding(c,other);b=be.account(c,'合成乙银行')
    be.approved(c,'account_binding',be.account_details(b,other,'SYNTH-SECOND-BANK'))
    be.approved(c,'policy',{'binding_id':be.config(c)['store_binding']['id'],'policy_version':1})
    tr.switch(c,1);return rev,a,other,b


def test_material_purchase_actual_return_and_original_cash_entity(client):
    rev,a=be.setup_policy(client);row,_,_=p.setup(client);row=p.command(client,row,'approve');row=p.receive(client,row)
    row=p.pay(client,row,a['id'],309);original=row['payments'][0]
    row,ret=p.return_request(client,row,row['receipts'][0],2500)
    p.return_action(client,row,ret,'return_approve');row=p.return_action(client,row,ret,'return_dispatch')
    values={'original_payment_id':original['id'],'amount_cents':308,'account_id':a['id'],'reference':'ENTITY-PURCHASE-RETURN','evidence_id':evidence(client,row,'receipt')}
    old=p.detail(client,row);key=uuid.uuid4().hex;done=p.command(client,row,'refund',values,version=old['version'],request_id=key)
    assert p.command(client,row,'refund',values,version=old['version'],request_id=key)==done
    p.command(client,row,'refund',values,version=old['version'],status=409)
    cases,cash=contexts();assert cases[row['id']]['revision_id']==rev['revision_id']
    assert len(cash)==2 and cash[1]['original_cash_id']==cash[0]['cash_id']
    assert restore()['verified_entity_cash']==2


def test_vehicle_purchase_contract_party_prepay_and_original_refund(client):
    rev,a=be.setup_policy(client);v,loc=vp.setup(client,1)
    bad=client.post(vp.API+'/orders',json={'request_id':uuid.uuid4().hex,**v})
    assert bad.status_code==409 and '主体' in bad.json()['detail']
    v['contracting_party']=rev['legal_name'];row=vp.create(client,v)
    row=vp.command(client,row,'approve',{'prices':[{'line_id':row['lines'][0]['id'],'unit_cost_cents':1001,'list_price_cents':1300}],'evidence_id':evidence(client,row,'invoice')})
    row=vp.funds(client,row,1001);row=vp.pay(client,row,a['id'],1001)
    row=vp.ship(client,row);row=vp.receive(client,row,loc)
    row=vp.command(client,row,'return_request',{'shipment_id':row['shipments'][0]['id'],'reason':'合成原供应方实车退回','evidence_id':evidence(client,row)})
    vp.ret(client,row,'return_approve');row=vp.ret(client,row,'return_dispatch')
    row=vp.command(client,row,'refund',{'original_payment_id':row['payments'][0]['id'],'amount_cents':1001,'account_id':a['id'],'reference':'ENTITY-CAR-REFUND','evidence_id':evidence(client,row,'receipt')})
    cases,cash=contexts();assert len(cases)==1 and cases[row['id']]['revision_id']==rev['revision_id']
    assert len(cash)==2 and cash[1]['original_cash_id']==cash[0]['cash_id']
    assert restore()['verified_entity_cash']==2


def test_actual_two_entity_material_transfer_and_clearing_preserve_both_sources(client):
    left,a,right,b=two_policies(client)
    purchase,items,_=p.setup(client);p.command(client,purchase,'approve');p.receive(client,purchase)
    login(client,'inventory')
    result=client.post('/api/transfers',json={'request_id':uuid.uuid4().hex,'destination_store_id':2,'due_date':today().isoformat(),'reason':'两店各自主体实际调拨','lines':[{'item_id':items[0]['id'],'quantity_milli':2500}]})
    assert result.status_code==201,result.text;t=result.json()
    login(client,'manager');tr.command(client,t,'approve');tr.switch(client,2);tr.command(client,t,'approve')
    login(client,'admin');item=master(client,'items',{'sku':'ENTITY-DEST','name':items[0]['name'],'unit':'件','reorder':'0','active':True})
    tr.switch(client,1);login(client,'inventory');tr.command(client,t,'dispatch',{'evidence_id':tr.upload(client,t),'reason':'本人实际发出'})
    tr.switch(client,2);assert client.get('/api/transfers/'+str(t['id'])).status_code==403
    login(client,'admin');t=tr.get(client,t);t=tr.command(client,t,'receive',{'evidence_id':tr.upload(client,t),'reason':'乙店实际验收','lines':[{'line_id':t['lines'][0]['id'],'item_id':item['id'],'accept_milli':2500,'reject_milli':0}]})
    login(client,'finance');o=client.get('/api/reconciliation/origins').json()['items'][0];clearing=recon.clear(client,o)
    recon.cmd(client,clearing,'pay',recon.payvalues(client,clearing,b['id']),kind='clearing')
    tr.switch(client,1);recon.cmd(client,clearing,'receive',recon.payvalues(client,clearing,a['id']),kind='clearing')
    lc,lcash=contexts(1);rc,rcash=contexts(2)
    assert {x['revision_id'] for x in lc.values()}=={left['revision_id']}
    assert {x['revision_id'] for x in rc.values()}=={right['revision_id']}
    assert len(lcash)==len(rcash)==1 and lcash[0]['case_id']!=rcash[0]['case_id']
    assert restore()['verified_entity_cash']==2


def test_vehicle_transfer_creation_freezes_recipient_without_actor_recipient_role(client):
    left,a,right,b=two_policies(client);v,loc=vp.setup(client,1);v['contracting_party']=left['legal_name'];row=vp.create(client,v)
    row=vp.command(client,row,'approve',{'prices':[{'line_id':row['lines'][0]['id'],'unit_cost_cents':1001,'list_price_cents':1300}],'evidence_id':evidence(client,row,'invoice')})
    row=vp.ship(client,row);row=vp.receive(client,row,loc)
    login(client,'inventory');t=vt.create(client,row['receipts'][0]['vehicle_id'])
    assert len(contexts(2)[0])==1 and next(iter(contexts(2)[0].values()))['revision_id']==right['revision_id']
    tr.switch(client,2);assert client.get('/api/vehicle-transfers/'+str(t['id'])).status_code==403
    assert restore()['verified_entity_cases']==3


def test_group_principal_original_cash_and_finance_advance_refund(client):
    rev,a=be.setup_policy(client)
    customer=master(client,'customers',{'name':'合成集团本金客户','phone':'13900101310','contact_allowed':True,'note':''})
    from tests.test_workflow import order
    row=order(client,customer_id=customer['id'],customer_name=customer['name'],customer_phone=customer['phone'])
    data={'customer_id':customer['id'],'case_id':row['id'],'account_id':a['id'],'evidence_id':evidence(client,row,'receipt')}
    m=group.issue(client,data);original=group.cmd(client,m,'topup',group.topup_values(data,1001))
    login(client,'finance');request=group.cmd(client,m,'refund_request',group.refund_request_values(data,original,1001))
    login(client,'manager');approved=group.cmd(client,m,'refund_approve',group.refund_review_values(data,request))
    login(client,'finance');group.cmd(client,m,'refund',group.refund_payment_values(data,approved))
    prepaid,_=bf.advance(client,customer,301,a['id']);advance=bf.current_advance(client,customer)
    refund=bf.create(client,customer,'advance_refund',{'amount_cents':301,'advance_id':advance['id'],'advance_version':advance['version']})
    refund=bf.approve(client,refund);refund=bf.command(client,refund,'execute',bf.proof(client,refund,account_id=a['id'],reference='ENTITY-ADVANCE-REFUND'))
    cases,cash=contexts();assert cases[refund['case']['id']]['source_case_id']==prepaid['case']['id']
    assert len(cash)==4 and cash[1]['original_cash_id']==cash[0]['cash_id'] and cash[3]['original_cash_id']==cash[2]['cash_id']
    assert restore()['verified_entity_cash']==4


def test_finance_correction_can_replace_channel_only_with_same_approved_entity(client):
    rev,a=be.setup_policy(client);other=be.account(client,'同主体另一个合成银行账户')
    be.approved(client,'account_binding',be.account_details(other,rev,'ENTITY-SECOND-APPROVED'))
    row,_,customer=bf.ready_retail(client);row=retail.pay(client,row,700,a['id'])
    with SessionLocal() as db:original=db.scalar(select(CashEntry.id).order_by(CashEntry.id))
    unbound=be.account(client,'未核对渠道的合成账户')
    login(client,'finance');bad=bf.create(client,customer,'correction',{'original_cash_id':original,'amount_cents':500,'account_id':unbound['id'],'reference':'ENTITY-BAD-CORRECTION','allocations':[{'source_case_id':row['id'],'amount_cents':500}]})
    bad=bf.approve(client,bad);bf.command(client,bad,'execute',bf.proof(client,bad,source_versions=bf.versions(client,row)),409)
    # The original-account reversal happens before the replacement attempt;
    # refusal must roll the entire pair back, including attribution contexts.
    assert len(contexts()[1])==1
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==1
    bf.command(client,bad,'cancel',{'reason':'取消未生效的错误渠道方案，另提核实后的申请'})
    correction=bf.create(client,customer,'correction',{'original_cash_id':original,'amount_cents':500,'account_id':other['id'],'reference':'ENTITY-CORRECTED-RECEIPT','allocations':[{'source_case_id':row['id'],'amount_cents':500}]})
    correction=bf.approve(client,correction);correction=bf.command(client,correction,'execute',bf.proof(client,correction,source_versions=bf.versions(client,row)))
    cases,cash=contexts();assert len(cash)==3 and cash[1]['original_cash_id']==original and cash[2]['original_cash_id'] is None
    assert cash[1]['account_binding_id']==cash[0]['account_binding_id']!=cash[2]['account_binding_id']
    assert cases[correction['case']['id']]['source_case_id']==row['id']
    assert restore()['verified_entity_cash']==3


def test_one_monthly_cash_multiple_sources_has_one_entity_context(client):
    rev,a=be.setup_policy(client);one,_,customer=bf.ready_retail(client)
    items,_,_,_=retail.setup(client);two=retail.authorize(client,retail.approve(client,retail.create(client,items,customer,qty=500)))
    login(client,'finance');statement=bf.create(client,customer,'statement',{'starts_on':today().isoformat(),'ends_on':today().isoformat()})
    statement=bf.approve(client,statement);allocations=[{'source_case_id':x['source_case_id'],'amount_cents':x['due_cents']} for x in statement['lines']]
    assert len(allocations)==2
    values=bf.proof(client,statement,amount_cents=sum(x['amount_cents'] for x in allocations),account_id=a['id'],reference='ENTITY-ONE-CASH-TWO-ORDERS',allocations=allocations,source_versions=bf.versions(client,one,two))
    statement=bf.command(client,statement,'collect',values)
    cases,cash=contexts();assert len(cash)==1 and cash[0]['case_id']==statement['case']['id']
    assert {cases[x]['revision_id'] for x in (one['id'],two['id'],statement['case']['id'])}=={rev['revision_id']}
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==1
        assert db.scalar(select(func.count()).select_from(PaymentLink))==2
    assert restore()['verified_entity_cash']==1


def test_delivered_and_converted_need_source_facts_and_successor_is_still_checked(client):
    from app.models import Vehicle
    from app import flow_engine as flow
    be.setup_policy(client)
    with SessionLocal() as db:
        user=be.actor(db);lead=be.case(db,user,'lead','converted');entities.freeze_case_entity(db,user,lead)
        order=be.case(db,user,'order','delivered');order.parent_id=lead.id;entities.freeze_case_entity(db,user,order)
        with pytest.raises(HTTPException) as unauthorized:
            entities.blockers(db)
        assert unauthorized.value.status_code == 403
        with entities.authority(db,user):
            assert '仍有未结业务或独立待办' in entities.blockers(db)
            car=Vehicle(vin='LHGCM82633A876543',brand='合成品牌',model='合成车型',color='白',supplier='合成来源',purchase_cost_cents=0,list_price_cents=0,doc_no='ENTITY-DELIVERED',business_date=today(),approval_state='approved',created_by=user.id)
            db.add(car);db.flush();order.vehicle_id=car.id;db.add(VehicleHold(vehicle_id=car.id,case_id=order.id,delivered=True))
            flow.log_event(db,user,lead,'reserve','合成原订购事实');flow.log_event(db,user,order,'deliver','合成原实际提车事实');db.flush()
            assert entities.blockers(db)==[]
            task=Task(case_id=order.id,key='invoice_adjust',title='独立原发票待办',role='finance',assignee_id=user.id,due_date=today());db.add(task);db.flush()
            assert '仍有未结业务或独立待办' in entities.blockers(db)
            task.status='done';order.state='executing';db.flush()
            assert '仍有未结业务或独立待办' in entities.blockers(db)


@pytest.mark.parametrize('tamper',['case','cash','document_missing','document_changed'])
def test_restore_refuses_missing_policy_attribution_and_document_tampering(client,tamper):
    rev,a=be.setup_policy(client)
    from tests.test_workflow import order
    row=order(client)
    with SessionLocal() as db:
        user=be.actor(db);source=db.scalar(select(Case).where(Case.id==row['id']));cash=be.cash(db,user,a)
        entities.record_cash_entity(db,user,source,cash,a['id']);db.commit()
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as copy:
        source.backup(copy);validate_business_entities(copy)
        if tamper=='case':copy.execute('DELETE FROM business_entity_case_contexts')
        elif tamper=='cash':copy.execute('DELETE FROM business_entity_cash_contexts')
        else:
            fid,snapshot=copy.execute('SELECT id,snapshot FROM flow_files WHERE generated=1').fetchone();snapshot=json.loads(snapshot)
            if tamper=='document_missing':snapshot.pop('主体资料版本编号')
            else:snapshot['经营主体法定名称']='篡改为另一合成公司'
            copy.execute('UPDATE flow_files SET snapshot=? WHERE id=?',(json.dumps(snapshot),fid))
        with pytest.raises(ValueError,match='主体'):validate_business_entities(copy)


def test_invoice_issuer_restore_refuses_changed_legal_party(client):
    from tests.test_business_entity_flows import labor_repair
    from tests import test_repair_orders as repair,test_invoices as invoice
    rev,a=be.setup_policy(client);row=labor_repair(client);row=repair.receive(client,row,row['allocations'][0],1001,a['id'])
    login(client,'finance');body=invoice.request_body(client,row['id']);body.update(issuer_name=rev['legal_name'],issuer_tax_id=rev['tax_identifier'])
    result=client.post('/api/invoices/orders',json=body);assert result.status_code==201,result.text
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as copy:
        source.backup(copy);validate_business_entities(copy)
        copy.execute("UPDATE invoice_applications SET issuer_name='篡改销售主体'")
        with pytest.raises(ValueError,match='发票销售方'):validate_business_entities(copy)


def test_approved_entity_field_limits_reach_actual_invoice_and_prevent_lossy_downgrade(client,monkeypatch):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from app.db import engine
    from tests.test_business_entity_flows import labor_repair
    from tests import test_repair_orders as repair,test_invoices as invoice
    name='合成'+('独立经营资料'*28)  # 170 chars, above the former invoice 160 limit.
    tax='SYNTHETIC'+('1'*16)
    be.approved(client,'revision',{'code':'LONG-ENTITY','tax_identifier':tax,'legal_name':name,'registered_address':'虚构长名称边界测试地址'})
    rev=be.config(client)['revisions'][0];be.store_binding(client,rev);a=be.account(client)
    be.approved(client,'account_binding',be.account_details(a,rev));be.approved(client,'policy',{'binding_id':be.config(client)['store_binding']['id'],'policy_version':1})
    row=labor_repair(client);row=repair.receive(client,row,row['allocations'][0],1001,a['id']);login(client,'finance')
    body=invoice.request_body(client,row['id']);body.update(issuer_name=name,issuer_tax_id=tax)
    result=client.post('/api/invoices/orders',json=body);assert result.status_code==201,result.text
    invoice.record(client,invoice.submit(client,invoice.approve(client,result.json())))
    assert restore()['verified_entity_cases']==2
    spec=importlib.util.spec_from_file_location('entity_revision_test',Path(__file__).parents[1]/'migrations/versions/l248_business_entities.py');revision=importlib.util.module_from_spec(spec);spec.loader.exec_module(revision)
    with engine.connect() as connection:
        monkeypatch.setattr(revision,'op',Operations(MigrationContext.configure(connection)))
        with pytest.raises(RuntimeError,match='不可降级截断'):revision.downgrade()
