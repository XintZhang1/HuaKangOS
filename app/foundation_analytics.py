"""Opening baselines and recharge components never become a second cash source."""
from collections import defaultdict
from sqlalchemy import select
from .flow_models import Account
from .opening_import_models import OpeningAccountEntry,OpeningImport
from .operations_analytics import local_day
from .recharge_bundle_service import analytics_rows


def build_foundation_analytics(db,user,start,end,cases,stores,cash,bounded,yuan):
    aggregate=bool(getattr(user,'_aggregate_scope',False) or len([x for x in db.info.get('store_scope',()) if x])>1)
    tables={};charts=[];metrics={};byid={c.id:c for c in cases}
    def table(key,title,headers):tables[key]={'title':title,'headers':headers,'rows':[]};return tables[key]['rows']
    def add(rows,cid,values,amount=None,units=None,**extra):
        r={'values':values,'route':None if aggregate else {'type':'case','id':cid},**extra}
        if amount is not None:r['amount_cents']=amount
        if units is not None:r['units']=units
        rows.append(r)
    def chart(key,title,rows,unit,field,caption,section='members'):
        totals=defaultdict(int)
        for r in rows:totals[r['values'][1]]+=r[field]
        names=sorted(totals)
        charts.append({'id':key,'title':title,'type':'bar','section':section,'unit':unit,'labels':names,
            'series':[{'name':title,'values':[totals[k] for k in names]}],'table':key,'caption':caption})
    data=analytics_rows(db,user)
    movement=table('recharge_bundle_cash','期间组合本金实际净收',['办理单','门店','到账日','组合规则','版本','事实','份数','现金变动（元）'])
    for r in data['cash']:
        if not start.isoformat()<=r['business_date']<=end.isoformat():continue
        add(movement,r['case_id'],[byid[r['case_id']].number,stores.get(r['store_id'],''),r['business_date'],r['name'],r['rule_version'],
            '有效原购买本金' if r['purpose']=='purchase' else '原组合退款',r['shares'],yuan(r['amount_cents'])],r['amount_cents'],cash_id=r['cash_id'])
    chart('recharge_bundle_cash','期间组合本金净收',movement,'cents','amount_cents','只核对已有唯一现金；赠品没有第二笔收款，本金充值不是营业收入。')
    metrics['recharge_bundle_net_cash_cents']=sum(r['amount_cents'] for r in movement)
    for kind,label,unit in [('bonus','赠送金额','cents'),('points','积分','count'),('coupon','消费券','count'),('package','作业套餐','count')]:
        key='recharge_bundle_'+kind
        rows=table(key,'期间组合'+label+'发行与原退回收',['办理单','门店 / 规则','办理日','事实','单位','变动'])
        for r in data['gifts']:
            if r['kind']!=kind or not start<=local_day(r['occurred_at'])<=end:continue
            add(rows,r['case_id'],[byid[r['case_id']].number,stores.get(r['store_id'],'')+' / '+r['name'],str(local_day(r['occurred_at'])),
                {'grant':'原组合赠送','refund_recovery':'退款收回原赠品','correction':'原组合误记同步更正'}[r['purpose']],r['unit_label'],yuan(r['units']) if kind=='bonus' else r['units']],units=r['units'])
        chart(key,'组合'+label+'发行净变动',rows,unit,'units','包括组合原发行、原组合退款回收和原批次误记差额；实际消费另见原权益流水。各规则独立，不跨种类合计或称为现金。')
    held=table('recharge_bundle_refund_holds','当前组合退款批准占额',['办理单','门店','组合','份数','原本金占额（元）'])
    for r in data['refund_holds']:
        add(held,r['case_id'],[byid[r['case_id']].number,stores.get(r['store_id'],''),r['name'],r['shares'],yuan(r['amount_cents'])],r['amount_cents'])
    chart('recharge_bundle_refund_holds','当前组合退款本金占额',held,'cents','amount_cents','等待原账户实退；本金占额已包括在集团本金总占额内，不能再次相加。')
    accounts={r.id:r for r in bounded(db,Account)};imports={r.id:r for r in bounded(db,OpeningImport)}
    balances=table('opening_account_balances','当前期初与实际账户余额',['期初批次','门店','账户','基准日','期初（元）','其后实际收入（元）','其后实际支出（元）','当前余额（元）'])
    for entry in bounded(db,OpeningAccountEntry):
        owner=imports[entry.import_id];account=accounts[entry.account_id]
        facts=[c for c in cash if c.store_id==entry.store_id and c.account==account.name and c.business_date>=entry.business_date]
        incoming=sum(c.amount_cents for c in facts if c.direction=='in');outgoing=sum(c.amount_cents for c in facts if c.direction=='out')
        balance=entry.amount_cents+incoming-outgoing
        add(balances,owner.case_id,[byid[owner.case_id].number,stores.get(entry.store_id,''),account.name,str(entry.business_date),yuan(entry.amount_cents),yuan(incoming),yuan(outgoing),yuan(balance)],balance,opening_cents=entry.amount_cents)
    chart('opening_account_balances','当前有期初来源的账户余额',balances,'cents','amount_cents','日初原余额加该日及以后有效真实收支；不计为当前所选期间收入。仅包括已明确导入期初来源的账户。','finance')
    return {'tables':tables,'charts':charts,'metrics':metrics}
