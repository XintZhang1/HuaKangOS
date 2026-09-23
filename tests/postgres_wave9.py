"""Nonempty customer services, explicit catalogue and versioned sales money."""
import uuid
from unittest.mock import patch
from sqlalchemy import select
from app.db import SessionLocal,today
from app.models import Vehicle,User
from app.tenancy import set_scope
from tests.conftest import login
from tests.postgres_wave8 import fresh_store,freeze
from tests import test_service_orders as svc,test_sales_quotes as sales,test_business_finance as finance
from tests.test_workflow import action,evidence

def seed(c):
    fresh_store(c,'PGSERVICECASH')
    row,p,payee=svc.setup(c);row=svc.authorized(c,svc.approved(c,svc.quoted(c,row,p,payee)))
    account=svc.bank(c);row=svc.cash(c,row,'receive',2997,account)
    tender=next(t for t in row['tenders'] if t['bucket']=='pass')
    row=svc.cash(c,row,'disburse',1500,account,tender_id=tender['id'])
    row=svc.cash(c,row,'thirdparty_return',1500,account,original_id=row['pass_entries'][0]['id'])
    row=svc.complete_line(c,row,'fee1');row=svc.apply_termination(c,svc.termination(c,row,{'fee1':200,'pass1':0}))
    plan=row['plans'][-1]
    for choice in plan['returns']:
        row=svc.cash(c,row,'refund',choice['amount_cents'],account,plan_id=plan['id'],tender_id=choice['tender_id'])
    assert row['summary']['customer_paid_cents']==200
    freeze(c,['service_orders','service_lines','service_pass_entries','service_refunds'])

    fresh_store(c,'PGSERVICEADV')
    row,p,_=svc.setup(c,'other_income');row=svc.authorized(c,svc.approved(c,svc.quoted(c,row,p)))
    customer={'id':row['summary']['customer_id']}
    finance.advance(c,customer,997);finance.apply_advance(c,customer,row,997);login(c)
    row=svc.apply_termination(c,svc.termination(c,svc.detail(c,row),{'fee1':200}));plan=row['plans'][-1]
    row=svc.cmd(c,row,'refund',dict(plan_id=plan['id'],tender_id=row['tenders'][0]['id'],amount_cents=797,evidence_id=svc.proof(c,row,True)))
    assert finance.current_advance(c,customer)['balance_cents']==797
    freeze(c,['service_tender_slices','service_charge_adjustments','service_refunds'])

    def car(sid):
        with SessionLocal() as db:
            set_scope(db,[sid],sid);admin=db.scalar(select(User).where(User.role=='admin'))
            row=Vehicle(doc_no='SYNTH-PG-Q-'+uuid.uuid4().hex[:8],business_date=today(),approval_state='approved',
                created_by=admin.id,vin='LDD'+uuid.uuid4().hex[:14].upper(),brand='合成品牌',model='待明确车型',
                purchase_cost_cents=8000,list_price_cents=10000)
            db.add(row);db.commit();return row.id
    for mode in ['CASH','ADV']:
        sid=fresh_store(c,'PGQUOTE'+mode)
        with patch.object(sales,'seed_car',lambda:car(sid)):
            row,quote,vid,customer=sales.setup(c)
        row=sales.ready(c,row,vid)
        if mode=='CASH':row,account=sales.pay(c,row,10000)
        else:
            _,account=finance.advance(c,customer,15000);finance.apply_advance(c,customer,row,10000);login(c)
        row=sales.propose(c,row,{**quote,'amount_cents':6000});row=sales.approve(c,row);row=sales.sign(c,row)
        if mode=='CASH':
            original=next(p for p in row['payments'] if p['direction']=='in')
            row=action(c,row,'refund_excess',{'original_id':original['id'],'amount':'40.00','account_id':account,
                'reference':uuid.uuid4().hex,'evidence_id':evidence(c,row,'receipt')})
        else:assert finance.current_advance(c,customer)['balance_cents']==9000
        freeze(c,['sales_quotes','sales_quote_reviews','sales_quote_consents','sales_quote_adjustments'])
    login(c);c.headers['X-Store-ID']='1'
