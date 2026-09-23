"""Restoring mismatched cash/allocation dates would corrupt period reconciliation."""
import sqlite3
import pytest
from app.backup_integrity import validate_sqlite
from tests.conftest import TEST_DIR
from tests import test_workflow as flow,test_aftercare as after
from tests.test_procurement import bank


@pytest.mark.parametrize('refund',[False,True])
def test_cash_and_original_allocation_date_must_match_on_restore(client,refund):
    if refund:
        source,account=after.completed_repair(client)
        row=after.confirmed(client,after.approved(client,after.plan(client,after.create(client,source),100)))
        after.refund(client,after.applied(client,row),account,100)
    else:
        row=flow.action(client,flow.order(client),'approve')
        flow.action(client,row,'receive',{'amount':'50.00','account_id':bank(client),'reference':'DATE-ORIGINAL','evidence_id':flow.evidence(client,row,'receipt')})
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);validate_sqlite(restored)
        restored.execute("UPDATE flow_payment_links SET business_date='2000-01-01' WHERE id=(SELECT MAX(id) FROM flow_payment_links)")
        with pytest.raises(ValueError):validate_sqlite(restored)


def test_ordinary_order_refund_requires_original_collection_reference(client):
    row=flow.action(client,flow.order(client),'approve');account=bank(client)
    row=flow.action(client,row,'receive',{'amount':'50.00','account_id':account,'reference':'REFUND-ORIGINAL','evidence_id':flow.evidence(client,row,'receipt')})
    row=flow.action(client,row,'cancel_request',{'reason':'合成客户明确撤回未执行订单'});row=flow.action(client,row,'cancel_approve')
    original=flow.detail(client,row)['payments'][0]['id']
    flow.action(client,row,'refund',{'amount':'50.00','account_id':account,'reference':'REFUND-ACTUAL','evidence_id':flow.evidence(client,row,'receipt'),'original_id':original})
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);validate_sqlite(restored)
        restored.execute("UPDATE flow_payment_links SET original_id=NULL WHERE direction='out'")
        with pytest.raises(ValueError):validate_sqlite(restored)
