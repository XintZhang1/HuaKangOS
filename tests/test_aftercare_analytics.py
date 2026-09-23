"""A subsequent correction never rewrites original fulfillment into its own period."""
from datetime import timedelta
from sqlalchemy import select
from app.db import today,SessionLocal
from app.flow_models import Case
from tests import test_aftercare as after,test_service_analytics as analytics


def test_cross_period_original_repair_kept_gross_and_adjustment_and_cash_separate(client):
    source,account=after.completed_repair(client)
    yesterday=today()-timedelta(days=1)
    with SessionLocal() as db:
        row=db.scalar(select(Case).where(Case.id==source['id']))
        row.data={**row.data,'released_date':yesterday.isoformat()};row.completed_date=yesterday;db.commit()
    old=analytics.report(client,date_from=yesterday.isoformat(),date_to=yesterday.isoformat())
    assert old['metrics']['repair_cents']==10997
    row=after.confirmed(client,after.approved(client,after.plan(client,after.create(client,source),2000)))
    row=after.applied(client,row)
    preserved=analytics.report(client,date_from=yesterday.isoformat(),date_to=yesterday.isoformat())
    assert preserved['tables']['repair_settlements']==old['tables']['repair_settlements']
    assert preserved['metrics']['repair_settlement_net_cents']==10997
    data=analytics.reconciled(client,'aftercare_adjustments',-2000,date_from=today().isoformat(),date_to=today().isoformat())
    assert data['metrics']['repair_cents']==0 and data['metrics']['repair_settlement_net_cents']==-2000
    assert data['metrics']['customer_period_amount_cents']==-2000
    assert data['metrics']['cash_out_cents']==0
    analytics.reconciled(client,'business_net_facts',-2000,date_from=today().isoformat(),date_to=today().isoformat())
    after.refund(client,row,account,2000)
    final=analytics.report(client,date_from=today().isoformat(),date_to=today().isoformat())
    assert final['metrics']['cash_out_cents']==2000
    assert final['tables']['aftercare_adjustments']==data['tables']['aftercare_adjustments']
    assert final['metrics']['repair_settlement_net_cents']==-2000
    combined=analytics.report(client,date_from=yesterday.isoformat(),date_to=today().isoformat())
    assert combined['metrics']['repair_settlement_net_cents']==combined['metrics']['customer_period_amount_cents']==8997
