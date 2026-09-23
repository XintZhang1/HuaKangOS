from tests import test_vehicle_operations as operations,test_service_analytics as analytics


def test_vehicle_moves_are_unavailable_and_location_distribution_does_not_add_inventory(client):
    purchase,vehicle,location=operations.inventory(client);dest=operations.destination(client)
    baseline=analytics.report(client);cost=baseline['metrics']['inventory_cost_cents']
    row=operations.act(client,operations.create(client,'local_move',vehicle,dest),'approve')
    row=operations.act(client,row,'dispatch')
    data=analytics.reconciled(client,'vehicle_location_moves',-cost)
    assert data['metrics']['inventory_cost_cents']==cost and data['metrics']['inventory_count']==1
    assert data['tables']['inventory']['rows'][0]['values'][4]=='店内移库在途'
    assert data['tables']['vehicle_locations']['rows'][0]['values'][5]=='店内移库在途'
    operations.act(client,row,'accept')
    analytics.reconciled(client,'vehicle_location_moves',0)
    assert analytics.report(client)['tables']['inventory']['rows'][0]['values'][4]=='可售'
    out=operations.act(client,operations.create(client,'other_out',vehicle),'approve');out=operations.act(client,out,'dispatch')
    data=analytics.reconciled(client,'vehicle_other_movements',-cost)
    assert data['metrics']['inventory_count']==data['metrics']['inventory_cost_cents']==0
    assert data['metrics']['vehicle_other_stock_delta']==-1
    returned=operations.act(client,operations.create(client,'other_return',location=location,original=out['id']),'approve')
    operations.act(client,returned,'receive')
    data=analytics.reconciled(client,'vehicle_other_movements',0)
    assert data['metrics']['inventory_cost_cents']==cost and data['metrics']['inventory_count']==1
    assert data['metrics']['cash_in_cents']==baseline['metrics']['cash_in_cents']
