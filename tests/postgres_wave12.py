"""Nonempty v3 original transport loss, paired clearing and actual recovery."""
import uuid
from sqlalchemy import select
from app.db import SessionLocal,today
from app.models import User,UserStore
from app.flow_models import Item
from tests.conftest import login,PASSWORD_HASH
from tests.postgres_wave8 import fresh_store,freeze
from tests import test_transfers as transfer,test_transfer_exception_workflow as exc,test_reconciliation as monthly
from tests.test_procurement import bank
from tests.test_repair_orders import typed


def seed(c):
    source=fresh_store(c,'PGLOSSFROM');destination=fresh_store(c,'PGLOSSTO');suffix=uuid.uuid4().hex[:10]
    manager='lossreview'+suffix;inventory='lossreceive'+suffix
    with SessionLocal() as db:
        # This newly created synthetic store has one receiving clerk and one
        # reviewer, so ordinary task routing selects those actual employees.
        for relationship in db.scalars(select(UserStore).where(UserStore.store_id==destination,UserStore.role.in_({'manager','inventory'}))):db.delete(relationship)
        db.flush()
        for name,role in [(manager,'manager'),(inventory,'inventory')]:
            person=User(username=name,display_name='合成调入方'+role,role=role,password_hash=PASSWORD_HASH,must_change_password=False)
            db.add(person);db.flush();db.add(UserStore(user_id=person.id,store_id=destination,role=role))
        a=Item(store_id=source,sku='PG-LOSS-A',name='合成运输核对件',unit='件',quantity_milli=3000,inventory_value_cents=100,unit_cost_cents=33)
        b=Item(store_id=destination,sku='PG-LOSS-B',name='合成运输核对件',unit='件',quantity_milli=0,inventory_value_cents=0,unit_cost_cents=0)
        db.add_all([a,b]);db.commit();aid,bid=a.id,b.id
    transfer.switch(c,source);login(c,'inventory')
    result=c.post('/api/transfers',json={'request_id':uuid.uuid4().hex,'destination_store_id':destination,'due_date':today().isoformat(),
        'reason':'独立合成库原批运输核对','lines':[{'item_id':aid,'quantity_milli':3000}]})
    assert result.status_code==201,result.text
    row=result.json();assert row['flow_version']==3
    login(c,'manager');transfer.command(c,row,'approve')
    transfer.switch(c,destination);login(c,manager);transfer.command(c,row,'approve')
    transfer.switch(c,source);login(c,'inventory');source_case=transfer.get(c,row)['case_id'];outproof=exc.proof(c,source_case)
    dispatched=transfer.command(c,row,'dispatch',{'evidence_id':outproof,'reason':'整批实际交承运人'})
    origin=next(x['id'] for x in dispatched['movements'] if x['kind']=='dispatch')
    transfer.switch(c,destination);login(c,inventory);current=transfer.get(c,row);dest_case=current['case_id'];inproof=exc.proof(c,dest_case)
    transfer.command(c,row,'receive',{'evidence_id':inproof,'reason':'合格两件实际入库，坏件在本店单独保管','lines':[{'line_id':current['lines'][0]['id'],'item_id':bid,'accept_milli':2000,'reject_milli':1000}]})
    current=transfer.get(c,row)
    origin=next(x['id'] for x in current['movements'] if x['kind']=='reject')
    result=c.post('/api/transfer-exceptions',json={'request_id':uuid.uuid4().hex,'transfer_id':row['id'],'version':current['version'],
        'case_version':current['case_version'],'original_id':origin,'quantity_milli':1000,'finding':'damaged',
        'result':'本人实际核对一件在手破损不能合格入库','evidence_id':inproof,'due_date':today().isoformat(),'confirmed':True})
    assert result.status_code==201,result.text
    exception=result.json()
    transfer.switch(c,source);login(c,'inventory');exc.action(c,exception,'observe',{'evidence_id':outproof,'result':'本人核对原发出清单与完好交接记录','confirmed':True})
    login(c,'finance');fp=exc.proof(c,source_case,True)
    exc.action(c,exception,'plan',{'source_bearer_cents':18,'destination_bearer_cents':16,'reason':'双方据原成本分别确认责任','evidence_id':fp})
    for sid,person in [(source,'manager'),(destination,manager)]:
        transfer.switch(c,sid);login(c,person);live=exc.current(c,exception);proof=exc.proof(c,live['case_id'],True)
        exc.action(c,exception,'approve',{'plan_id':live['plans'][-1]['id'],'reason':'本人独立核对原事实及原成本承担','evidence_id':proof})
    login(c,inventory);exc.action(c,exception,'dispose',{'result':'本人按批准方案实际处理原在手坏件，处置结果留存','evidence_id':inproof,'confirmed':True})
    transfer.switch(c,source);login(c,'finance');exc.action(c,exception,'post_loss',{'evidence_id':fp,'confirmed':True})
    login(c);carrier=typed(c,'suppliers',{'code':'PGCARRIER'+suffix,'name':'合成原运输承运人','payment_terms_days':30});account=bank(c)
    login(c,'finance');claim=exc.create_claim(c,exception,carrier,fp,17);claim=exc.approve_claim(c,exception,claim,fp)
    result=exc.recovery(c,exception,'recovery_receive',claim,amount_cents=15,account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),confirmed=True,evidence_id=fp)
    original=result['recoveries'][0]['payments'][0]
    result=exc.recovery(c,exception,'recovery_plan',claim,target_cents=10,due_date=today().isoformat(),reason='往来方有据调减原赔款目标',evidence_id=fp)
    claim=exc.approve_claim(c,exception,result['recoveries'][0],fp)
    exc.recovery(c,exception,'recovery_refund',claim,original_id=original['id'],amount_cents=5,account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),confirmed=True,evidence_id=fp)
    transfer.switch(c,destination);login(c,'finance');origins=c.get('/api/reconciliation/origins').json()['items']
    origin=next(x for x in origins if x['origin_kind']=='material_loss' and x['transfer_id']==row['id']);clearing=monthly.clear(c,origin,10)
    monthly.cmd(c,clearing,'pay',monthly.payvalues(c,clearing),kind='clearing')
    transfer.switch(c,source);monthly.cmd(c,clearing,'receive',monthly.payvalues(c,clearing),kind='clearing')
    freeze(c,{'transfer_loss_postings','transfer_loss_settlements','transfer_recovery_claims','transfer_recovery_payments','interstore_clearing_offsets'})
    transfer.switch(c,destination);freeze(c,{'transfer_loss_settlements','interstore_clearing_offsets'})
