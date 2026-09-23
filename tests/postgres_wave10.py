"""Synthetic v3 costs, insurance and add-ons, plus v4 sales dispatch."""
import uuid
from unittest.mock import patch
from sqlalchemy import select
from app.db import SessionLocal,today
from app.models import Vehicle,User
from app.tenancy import set_scope
from tests.conftest import login
from tests.postgres_wave8 import fresh_store,freeze
from tests import test_procurement_costs as cost,test_insurance_orders as insurance,test_addon_orders as addon,test_sales_quotes as sales,test_business_finance as finance


def _car(sid):
    with SessionLocal() as db:
        set_scope(db,[sid],sid);admin=db.scalar(select(User).where(User.role=='admin'))
        car=Vehicle(doc_no='PG10-'+uuid.uuid4().hex[:16],business_date=today(),approval_state='approved',created_by=admin.id,
            vin='LDD'+uuid.uuid4().hex[:14].upper(),brand='合成品牌',model='测试车型',purchase_cost_cents=8000,list_price_cents=10000)
        db.add(car);db.commit();return car.id


def seed(c):
    from tests.test_workflow import master
    original_vehicle=insurance.vehicle
    def vehicle(client,customer_id=None,**values):
        customer_id=customer_id or master(client,'customers',{'name':'合成保险原单客户','phone':'','contact_allowed':True,'note':''})['id']
        return original_vehicle(client,customer_id=customer_id,vin='LDD'+uuid.uuid4().hex[:14].upper(),**values)
    with patch.object(insurance,'vehicle',vehicle):_seed(c)


def _seed(c):
    fresh_store(c,'PGCOSTV3');item,first,second=cost.mixed(c);cost.retail_take(c,item);cost.returned(c,first)
    freeze(c,['procurement_return_valuations'])
    fresh_store(c,'PGINSURANCE');row,_,_=insurance.setup(c);row=insurance.ready(c,row);a=insurance.bank(c)
    row=insurance.cash(c,row,'receive',10001,a);row=insurance.cash(c,row,'disburse',10001,a,tender_id=row['tenders'][0]['id']);row=insurance.issued(c,row)
    row=insurance.commission(c,row,501);row=insurance.cash(c,row,'commission_receive',501,a,confirmation_id=row['commissions'][-1]['id'])
    row=insurance.apply_plan(c,insurance.termination(c,row,2000));row=insurance.cash(c,row,'insurer_return',8001,a,original_id=row['pass_entries'][0]['id'])
    row=insurance.cash(c,row,'refund',8001,a,plan_id=row['plans'][-1]['id'],tender_id=row['tenders'][0]['id'])
    row=insurance.commission(c,row,100);row=insurance.cash(c,row,'commission_return',401,a,confirmation_id=row['commissions'][-1]['id'],original_id=row['commission_payments'][0]['id'])
    freeze(c,['insurance_customer_refunds','insurance_commission_payments','insurance_pass_entries'])
    fresh_store(c,'PGRENEWAL');row,_,cv=insurance.setup(c,'customer_direct');row=insurance.ready(c,row)
    row=insurance.cmd(c,row,'direct_paid',dict(amount_cents=10001,external_reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=insurance.proof(c,row,True)))
    row=insurance.issued(c,row);insurance.commission(c,row,0)
    renewed,_,_=insurance.setup(c,'customer_direct',previous=row['results'][0]['id'],cv=cv);renewed=insurance.ready(c,renewed);insurance.issued(c,renewed)
    freeze(c,['insurance_renewal_links','insurance_direct_entries'])
    fresh_store(c,'PGINSADV');row,_,cv=insurance.setup(c);row=insurance.ready(c,row);customer={'id':cv['customer_id']}
    finance.advance(c,customer,10001);finance.apply_advance(c,customer,row,10001);login(c)
    row=insurance.apply_plan(c,insurance.termination(c,insurance.detail(c,row),0))
    row=insurance.cmd(c,row,'refund',dict(plan_id=row['plans'][-1]['id'],tender_id=row['tenders'][0]['id'],amount_cents=10001,business_date=today().isoformat(),evidence_id=insurance.proof(c,row,True)))
    insurance.commission(c,row,0);freeze(c,['insurance_tenders','insurance_customer_refunds'])
    sid=fresh_store(c,'PGADDON')
    def session():
        db=SessionLocal();set_scope(db,[sid],sid);return db
    with patch.object(addon,'seed_car',lambda:_car(sid)),patch.object(addon,'SessionLocal',session):
        row,items,work,source,vin,a=addon.completed(c)
    row=addon.resolve(c,addon.resolve(c,addon.resolution(c,row,'return'),'resolution_approve'),'resolution_consent');row=addon.resolve(c,row,'return_receive',passed=True)
    addon.refund(c,row,a,row['totals']['refund_due_cents']);freeze(c,['addon_dispatches','addon_installations','addon_acceptances','addon_return_postings','addon_payments'])
    sid=fresh_store(c,'PGSALESV4')
    with patch.object(sales,'seed_car',lambda:_car(sid)):row,q,vid,customer=sales.setup(c)
    row=sales.ready(c,row,vid);row=sales.propose(c,row,{**q,'addon':True,'insurance':True,'agency':True});row=sales.approve(c,row);sales.sign(c,row)
    freeze(c,['sales_quotes','insurance_orders','addon_orders','service_orders'])
    login(c);c.headers['X-Store-ID']='1'
