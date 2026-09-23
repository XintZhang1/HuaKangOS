"""Real role projections for approved opening account mappings."""
from tests.conftest import login
from tests import test_opening_import as opening
from tests.test_business_entity_opening import source


def test_inventory_common_timeline_never_exposes_approved_opening_account_mapping(client):
    data,revision,account=source(client)
    row=opening.preflight(client,data)['batch']
    login(client,'finance')
    response=client.get('/api/flow/cases/'+str(row['case_id']))
    assert response.status_code==200,response.text
    event=next(e for e in response.json()['events'] if 'account_context' in e['detail'])
    assert event['detail']['account_context']['accounts'][0]['account_id']==account['id']
    login(client,'inventory')
    response=client.get('/api/flow/cases/'+str(row['case_id']))
    assert response.status_code==200,response.text
    for event in response.json()['events']:
        assert not {'account_context','owners','objects'} & event['detail'].keys()
    assert account['name'] not in response.text
    dedicated=client.get('/api/opening-import/batches/'+str(row['case_id']))
    assert dedicated.status_code==200,dedicated.text
    assert dedicated.json()['accounts']==[] and dedicated.json()['customers']==[]
    assert account['name'] not in dedicated.text
