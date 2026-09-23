"""Reviewable price history and original excess returns; never added to revenue."""
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .config import settings
from .sales_quote_analytics import analytics_rows


def build_sales_quotes(db,user,stores,yuan,in_period):
    source=analytics_rows(db,user);tables={};charts=[];change_total=0;excess_total=0;adjustments=defaultdict(int)
    def day(r):return datetime.fromisoformat(r['occurred_at'].replace('Z','+00:00')).astimezone(ZoneInfo(settings.timezone)).date()
    def table(key,title,headers):
        tables[key]={'title':title,'headers':headers,'rows':[]};return tables[key]['rows']
    def add(rows,r,values,amount=None):
        rows.append({'values':values,'route':{'type':'case','id':r['case_id']},'amount_cents':amount,'quote_id':r.get('quote_id',r['id']),'source_id':r['id']})
    versions=table('sales_quote_versions','期间创建的整车报价版本',['原单','门店','创建日期','版本','车型','方案金额（元）','当前办理结果'])
    changes=table('sales_quote_changes','期间客户确认的整车价款变更',['原单','门店','确认日期','新版本','原价款（元）','新价款（元）','本次价差（元）'])
    excess=table('sales_quote_excess','当前可办理的整车超收退回',['原单','门店','有效版本','有效价款（元）','已结算（元）','待退回（元）'])
    refunds=table('sales_quote_adjustments','期间整车原路超收退回',['原单','门店','发生日期','版本','退回方式','金额（元）','原业务退款记录','预收回退记录'])
    statuses={'pending':'待核价','approve':'主管已批准','approved':'主管已批准','activated':'客户已确认生效','rejected':'已拒绝','withdrawn':'已撤回'}
    for r in source['versions']:
        if in_period(day(r)):add(versions,r,[r['number'],stores.get(r['store_id'],''),day(r).isoformat(),r['revision'],r['model_name'],yuan(r['amount_cents']),statuses.get(r['status'],r['status'])],r['amount_cents'])
    for r in source['changes']:
        if not in_period(day(r)):continue
        add(changes,r,[r['number'],stores.get(r['store_id'],''),day(r).isoformat(),r['revision'],yuan(r['prior_amount_cents']),yuan(r['prior_amount_cents']+r['amount_cents']),yuan(r['amount_cents'])],r['amount_cents']);change_total+=r['amount_cents']
    for r in source['excess']:
        add(excess,r,[r['number'],stores.get(r['store_id'],''),r['revision'],yuan(r['quote_cents']),yuan(r['paid_cents']),yuan(r['amount_cents'])],r['amount_cents']);excess_total+=r['amount_cents']
    for r in source['adjustments']:
        if not in_period(day(r)):continue
        kind='原现金实际退款' if r['payment_id'] else '原预收抵用回退'
        add(refunds,r,[r['number'],stores.get(r['store_id'],''),day(r).isoformat(),r['revision'],kind,yuan(r['amount_cents']),r['payment_id'] or '',r['credit_id'] or ''],r['amount_cents']);adjustments[kind]+=r['amount_cents']
    labels=sorted(adjustments)
    charts.append({'id':'sales_quote_adjustments','title':'期间整车超收原路退回','section':'finance','type':'bar','unit':'cents','labels':labels,'series':[{'name':'退回金额','values':[adjustments[k] for k in labels]}],'table':'sales_quote_adjustments','caption':'原现金退款与原预收回退分开；预收回退没有现金流出。报价版本及变更价差不是营业收入。'})
    return {'tables':tables,'charts':charts,'metrics':{'sales_quote_signed_change_cents':change_total,'sales_quote_excess_cents':excess_total,'sales_quote_cash_return_cents':adjustments['原现金实际退款'],'sales_quote_advance_return_cents':adjustments['原预收抵用回退']}}
