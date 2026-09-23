"""Approved legal entities and actual original cash survive a nonempty transfer."""
import uuid
from sqlalchemy import select

from app.db import SessionLocal
from app.tenancy import set_scope
from app import business_entity_service as entities
from app.business_entity_models import CaseEntityContext, CashEntityContext
from tests.conftest import login
from tests.postgres_wave8 import fresh_store, freeze
from tests.test_business_entity_flows import labor_repair, long_policy
from tests.test_workflow import evidence, master, order as basic_order
from tests import test_repair_orders as repair
from tests import test_invoices as invoice
from tests import test_aftercare as aftercare
from tests import test_insurance_orders as insurance
from tests.test_customer_service import vehicle


def seed(c):
    sid=fresh_store(c,'PGENTITY')
    rev,bank=long_policy(c);aid=bank['id']
    row=labor_repair(c)
    row=repair.receive(c,row,row['allocations'][0],1001,aid)
    row=repair.cmd(c,row,'release',{'evidence_id':evidence(c,row)})
    login(c,'finance')
    body={**invoice.request_body(c,row['id']),'issuer_name':rev['legal_name'],'issuer_tax_id':rev['tax_identifier']}
    result=c.post('/api/invoices/orders',json=body);assert result.status_code==201,result.text
    invoice.record(c,invoice.submit(c,invoice.approve(c,result.json())))
    login(c);request=aftercare.create(c,row)
    request=aftercare.applied(c,aftercare.confirmed(c,aftercare.approved(c,aftercare.plan(c,request,333))))
    aftercare.refund(c,request,aid,333)
    # Actual customer and VIN are explicitly created in this fresh store.
    customer=master(c,'customers',{'name':'合成主体保险客户','phone':'','contact_allowed':True,'note':''})
    cv=vehicle(c,customer_id=customer['id'],vin='LDD'+uuid.uuid4().hex[:14].upper())
    policy,_,_=insurance.setup(c,cv=cv);policy=insurance.ready(c,policy)
    policy=insurance.cash(c,policy,'receive',10001,aid)
    policy=insurance.cash(c,policy,'disburse',10001,aid,tender_id=policy['tenders'][0]['id'])
    policy=insurance.issued(c,policy);policy=insurance.commission(c,policy,501)
    policy=insurance.cash(c,policy,'commission_receive',501,aid,confirmation_id=policy['commissions'][-1]['id'])
    policy=insurance.apply_plan(c,insurance.termination(c,policy,2000))
    policy=insurance.cash(c,policy,'insurer_return',8001,aid,original_id=policy['pass_entries'][0]['id'])
    policy=insurance.cash(c,policy,'refund',8001,aid,plan_id=policy['plans'][-1]['id'],tender_id=policy['tenders'][0]['id'])
    policy=insurance.commission(c,policy,100)
    insurance.cash(c,policy,'commission_return',401,aid,confirmation_id=policy['commissions'][-1]['id'],original_id=policy['commission_payments'][0]['id'])
    basic_order(c)
    # Existing sealed-source definition remains explicit; legal contexts are
    # independently immutable and checked by the complete restore validator.
    freeze(c,['insurance_customer_refunds','insurance_commission_payments'])
    with SessionLocal() as db:
        from app.models import User
        from app.tenancy import project_user
        set_scope(db,[sid],sid);user=project_user(db.scalar(select(User).where(User.username=='admin')),'admin')
        with entities.authority(db,user):
            assert len(list(db.scalars(select(CaseEntityContext))))>=5
            assert len(list(db.scalars(select(CashEntityContext))))==8
    login(c);c.headers['X-Store-ID']='1'
