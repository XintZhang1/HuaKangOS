"""Nonempty imported handovers, frozen packages and all claim money paths."""
from sqlalchemy import select
from app.db import SessionLocal,today
from app.models import User,UserStore
from tests.conftest import login
from tests import test_claims as claims,test_retail_bundles as bundle,test_vehicle_imports as imported
from tests import test_retail as retail,test_reconciliation as recon
from tests.test_workflow import evidence


def fresh_store(c,code):
    login(c);c.headers['X-Store-ID']='1'
    response=c.post('/api/stores',json={'code':code,'name':'合成验收'+code,'active':True})
    assert response.status_code==201,response.text
    sid=response.json()['id']
    with SessionLocal() as db:
        for user in db.scalars(select(User)):
            if not db.scalar(select(UserStore.user_id).where(UserStore.store_id==sid,UserStore.user_id==user.id)):
                db.add(UserStore(store_id=sid,user_id=user.id,role=None if user.role=='admin' else user.role))
        db.commit()
    c.headers['X-Store-ID']=str(sid)
    return sid


def freeze(c,expected):
    from app.reconciliation_service import CURRENT_DEFINITION_VERSION
    login(c,'finance');row=recon.batch(c)
    assert row['definition_version']==CURRENT_DEFINITION_VERSION
    assert set(expected)<={x['source'] for x in row['manifest']}
    login(c)


def seed(c):
    fresh_store(c,'PGCLAIMDIRECT')
    row,source,account,payer=claims.reimbursement(c)
    row=claims.cmd(c,row,'direct_confirm',{'amount_cents':3000,'evidence_id':claims.proof(c,row,True)})
    original=row['customer_payments'][0]['id'];row,plan=claims.return_plan(c,row,original,1000)
    claims.cmd(c,row,'direct_return',{'plan_id':plan,'original_id':original,'amount_cents':1000,'evidence_id':claims.proof(c,row,True)})
    freeze(c,['claims_orders','claims_customer_payments','claims_return_plans'])

    fresh_store(c,'PGCLAIMPASS')
    row,source,account,payer=claims.reimbursement(c,'customer_via_store')
    row=claims.cash(c,row,'pass_receive',3000,account);incoming=row['cash'][0]['id']
    row=claims.cash(c,row,'pass_pay',1000,account,original_id=incoming);outgoing=row['cash'][-1]['id']
    row,plan=claims.return_plan(c,row,incoming,2000)
    row=claims.cash(c,row,'unused_refund',2000,account,original_id=incoming,plan_id=plan)
    row=claims.cmd(c,row,'close',{'reason':'合成未转付原款已退回','evidence_id':claims.proof(c,row)})
    row,plan=claims.return_plan(c,row,outgoing,1000)
    row=claims.cash(c,row,'customer_return',1000,account,original_id=outgoing,plan_id=plan);actual_return=row['cash'][-1]['id']
    claims.cash(c,row,'party_return',1000,account,original_id=actual_return,plan_id=plan)
    freeze(c,['claims_cash','claims_closures'])

    fresh_store(c,'PGCLAIMREDUCE')
    source,account,payer=claims.completed(c,True)
    source=claims.receive(c,source,source['allocations'][1],4997,account)
    row,_=claims.create(c,source,payer=payer);row=claims.external(c,claims.assessed(c,row,4997),3000,'partial')
    original=next(x['id'] for x in row['source_payments'] if x['allocation_id']==source['allocations'][1]['id'])
    row=claims.cmd(c,row,'resolution',{'internal_bearer':'合成门店','refunds':[{'original_id':original,'amount_cents':1997}],
        'reason':'合成实际核赔原责任调减','evidence_id':claims.proof(c,row)})
    row=claims.reviewed(c,row,'resolution_approve')
    row=claims.cash(c,row,'thirdparty_refund',1997,account,original_id=original)
    claims.cmd(c,row,'resolution_apply',{'evidence_id':claims.proof(c,row,True)})
    freeze(c,['claims_resolutions','claims_applications','claims_responsibility_entries'])

    fresh_store(c,'PGIMPORT')
    row,location=imported.approved(c,2)
    funds=imported.manifest(c,row,2);login(c,'inventory')
    shipment=imported.prepare(c,row,'ship',[[f'PG-S-{i}',r['id'],r['values']['vin'],str(today()),str(today())] for i,r in enumerate(funds['rows'])])
    imported.done(c,shipment,'inventory')
    receipt=imported.prepare(c,row,'receive',[[f'PG-R-{i}',r['id'],r['values']['vin'],str(today()),location] for i,r in enumerate(funds['rows'])])
    imported.done(c,receipt,'inventory')
    freeze(c,['vehicle_import_batches','vehicle_import_rows','vehicle_import_results'])

    fresh_store(c,'PGPACKAGE')
    items,customer,work,_=bundle.stock_setup(c,True);rule=bundle.publish(c,items,work)
    row=bundle.sale(c,rule,customer,2);account=retail.bank(c)
    row=retail.dispatch(c,retail.authorize(c,retail.approve(c,row)))
    row=retail.pay(c,row,2000,account)
    row=retail.cmd(c,row,'install',{'evidence_id':evidence(c,row),'result':'合成原套餐安装完成'})
    row=retail.cmd(c,row,'accept',{'evidence_id':evidence(c,row)})
    row,request=retail.request_return(c,row,row['dispatches'][0],1000)
    row=retail.ret_cmd(c,row,request,'return_approve');row=retail.ret_cmd(c,row,request,'return_receive')
    retail.refund(c,row,row['payments'][0],account,row['totals']['refund_due_cents'])
    freeze(c,['retail_bundle_rules','retail_bundle_components','retail_bundle_sales','retail_bundle_allocations'])
    login(c);c.headers['X-Store-ID']='1'

