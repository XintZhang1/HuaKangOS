"""Price history cannot create turnover; original cash and advances remain distinct."""
import csv,io,uuid
from datetime import timedelta
from decimal import Decimal
from tests import test_sales_quotes as sale
from tests.test_service_analytics import report
from tests.conftest import login
from app.db import today


def test_price_changes_and_original_refund_reconcile_without_revenue(client):
    c=client;row,q,car,_=sale.setup(c);row=sale.ready(c,row,car);row,account=sale.pay(c,row,10000)
    row=sale.propose(c,row,{**q,'amount_cents':9001});row=sale.approve(c,row);row=sale.sign(c,row)
    data=report(c)
    assert data['metrics']['sales_quote_signed_change_cents']==-999
    assert data['metrics']['sales_quote_excess_cents']==999
    assert data['metrics']['recorded_business_net_cents']==0
    assert len(data['tables']['sales_quote_versions']['rows'])==2
    original=next(p for p in row['payments'] if p['direction']=='in')
    row=sale.action(c,row,'refund_excess',{'original_id':original['id'],'amount':'9.99','account_id':account,'reference':uuid.uuid4().hex,'evidence_id':sale.evidence(c,row,'receipt')})
    data=report(c)
    assert data['metrics']['sales_quote_excess_cents']==0
    assert data['metrics']['sales_quote_cash_return_cents']==999
    assert data['metrics']['cash_out_cents']==999 and data['metrics']['recorded_business_net_cents']==0
    table=data['tables']['sales_quote_adjustments'];chart=next(x for x in data['charts'] if x['id']=='sales_quote_adjustments')
    assert sum(sum(s['values']) for s in chart['series'])==sum(r['amount_cents'] for r in table['rows'])==999
    response=c.get('/api/flow/analytics/export',params={'dataset':'sales_quote_adjustments'});assert response.status_code==200,response.text
    rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows[0]==table['headers'] and Decimal(rows[1][5])*100==999
    prior=(today()-timedelta(days=1)).isoformat()
    past=c.get('/api/flow/analytics',params={'date_from':prior,'date_to':prior}).json()
    assert past['tables']['sales_quote_changes']['rows']==past['tables']['sales_quote_adjustments']['rows']==[]
    login(c,'sales');assert c.get('/api/flow/analytics').status_code==403
    login(c);other=c.post('/api/stores',json={'code':'QREPORT','name':'报价统计隔离店','active':True}).json()['id'];c.headers['X-Store-ID']=str(other)
    assert report(c)['tables']['sales_quote_versions']['rows']==[]


def test_original_advance_return_is_not_cash_outflow(client):
    sale.test_advance_repricing_returns_only_original_excess_without_cash(client)
    data=report(client)
    assert data['metrics']['sales_quote_advance_return_cents']==4000
    assert data['metrics']['sales_quote_cash_return_cents']==data['metrics']['cash_out_cents']==0
    assert data['tables']['sales_quote_adjustments']['rows'][0]['values'][4]=='原预收抵用回退'
