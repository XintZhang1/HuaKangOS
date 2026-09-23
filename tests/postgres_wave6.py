"""New nonempty source facts for migration/restore acceptance; all writes use business APIs."""
from tests.conftest import login
from tests import test_vehicle_operations as vehicles,test_vehicle_procurement as purchase,test_aftercare as aftercare
from tests import test_business_finance as finance,test_retail as retail,test_group_aftercare as group_returns
from tests import test_group_membership as group,test_repair_orders as repair
from tests.test_workflow import evidence


def seed(client):
    client.headers['X-Store-ID']='1';login(client,'admin')
    order,loc=purchase.approved(client,1);order=purchase.ship(client,order,vin='LHGCM8263A6060001');order=purchase.receive(client,order,loc)
    car=order['receipts'][0]['vehicle_id'];dest=vehicles.destination(client)
    move=vehicles.act(client,vehicles.create(client,'local_move',car,dest),'approve');move=vehicles.act(client,move,'dispatch')
    move=vehicles.act(client,move,'reject');vehicles.act(client,move,'return_receive')
    out=vehicles.act(client,vehicles.create(client,'other_out',car),'approve');out=vehicles.act(client,out,'dispatch')
    returned=vehicles.act(client,vehicles.create(client,'other_return',location=loc,original=out['id']),'approve');vehicles.act(client,returned,'receive')

    login(client,'admin');source,account=aftercare.completed_repair(client)
    row=aftercare.confirmed(client,aftercare.approved(client,aftercare.plan(client,aftercare.create(client,source),2000)))
    row=aftercare.applied(client,row);aftercare.refund(client,row,account,2000)

    login(client,'admin');source,data,member,_,_=group_returns.source(client)
    group.cmd(client,member,'topup',group.topup_values(data,10997))
    reserved=group.cmd(client,member,'reserve',group.reserve_values(data,10997))
    captured=group.cmd(client,member,'capture',group.reservation_values(data,reserved))
    source=repair.cmd(client,source,'release',{'evidence_id':evidence(client,source)})
    row=aftercare.plan(client,aftercare.create(client,source),1700,[{'kind':'principal','original_id':captured['entry_id'],'units':1700}])
    aftercare.applied(client,aftercare.confirmed(client,aftercare.approved(client,row)))

    login(client,'admin');one,_,customer=finance.ready_retail(client)
    prepaid,account=finance.advance(client,customer,1500);finance.apply_advance(client,customer,one,600)
    login(client,'admin');items,_,_,_=retail.setup(client)
    two=retail.authorize(client,retail.approve(client,retail.create(client,items,customer,qty=500)))
    from app.db import today
    login(client,'finance');statement=finance.approve(client,finance.create(client,customer,'statement',{'starts_on':today().isoformat(),'ends_on':today().isoformat()}))
    allocations=[{'source_case_id':line['source_case_id'],'amount_cents':line['due_cents']} for line in statement['lines']]
    finance.command(client,statement,'collect',finance.proof(client,statement,amount_cents=sum(a['amount_cents'] for a in allocations),account_id=account,
        reference='PG-WAVE6-MONTHLY',allocations=allocations,source_versions=finance.versions(client,one,two)))
    client.headers['X-Store-ID']='1';login(client,'admin')
