"""Package dimension filters original retail facts, preserving period recognition."""
from collections import defaultdict
from .retail_bundle_service import analytics_rows


def build_retail_bundle_analytics(db,user,source_tables,yuan):
    source={r['case_id']:r for r in analytics_rows(db,user)}
    rows=[];totals=defaultdict(int);aggregate=getattr(user,'_aggregate_scope',False)
    for fact in source_tables['retail_settlements']['rows']:
        identity=(fact.get('route') or {}).get('id')
        package=source.get(identity)
        if package is None:continue
        values=fact['values'];label=package['name']+' v'+str(package['rule_version'])
        amount=fact['amount_cents'];totals[label]+=amount
        rows.append({'values':[values[0],values[1],values[3],values[4],package['code'],
            package['name'],package['rule_version'],package['sets'],yuan(amount),values[6]],
            'route':None if aggregate else fact['route'],'amount_cents':amount,
            'source_case_id':identity,'rule_id':package['rule_id']})
    key='retail_bundle_settlements';labels=sorted(totals)
    return {'tables':{key:{'title':'期间精品套餐履约与原单退货',
        'headers':['精品单','门店','发生日期','原事实','套餐编码','套餐名称','原规则版本','原开单套数','对外结算（元）','商品成本（元）'],'rows':rows}},
        'charts':[{'id':key,'title':'期间精品套餐履约净额','section':'materials','type':'bar','unit':'cents',
            'labels':labels,'series':[{'name':'套餐履约金额','values':[totals[k] for k in labels]}],'table':key,
            'caption':'筛选原精品履约及实际退货事实，沿用相同日期和原分摊，不增加另一笔收入、库存或现金。原开单套数只作来源说明，不能逐事实累加为销量。'}],
        'metrics':{'retail_bundle_revenue_cents':sum(totals.values())}}
