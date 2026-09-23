"""Package filtering is a subset of the original period retail population."""
from tests import test_retail_bundles as bundles,test_service_analytics as analytics
from tests.test_retail import technician
from tests.conftest import login
from tests.test_multistore import second_store,switch


def test_original_frozen_package_return_matches_chart_csv_without_duplicating_income(client):
    bundles.test_fractional_quantity_stable_per_set_cents_and_ordinary_retail_fulfillment(client)
    data=analytics.reconciled(client,'retail_bundle_settlements',184)
    assert data['metrics']['retail_bundle_revenue_cents']==data['metrics']['retail_revenue_cents']==184
    assert data['metrics']['recorded_business_net_cents']==data['metrics']['cash_net_cents']==184
    assert data['tables']['retail_bundle_settlements']['rows'][0]['values'][6:8]==[1,2]
    second_store(client);switch(client,2)
    assert not analytics.report(client)['tables']['retail_bundle_settlements']['rows']
    switch(client,'all')
    assert all(row['route'] is None for row in analytics.report(client)['tables']['retail_bundle_settlements']['rows'])
    switch(client,1);login(client,'inventory')
    assert client.get('/api/flow/analytics/export',params={'dataset':'retail_bundle_settlements'}).status_code==403
