"""Current authorized price facts, never revenue or a sum of historical quote versions."""
from collections import defaultdict
from sqlalchemy import select
from .member_pricing_integrity import business_day
from .member_pricing_models import MemberPricingSnapshot,MemberPricingAuthorization

def current_quote_prices(db,row,*,allow_pending_retail=False):
    if row.state=='cancelled' or row.kind not in {'repair','addon','retail'}:return None
    snaps={s.quote_id:s for s in db.scalars(select(MemberPricingSnapshot).where(MemberPricingSnapshot.case_id==row.id))}
    if not snaps:return None
    if row.kind=='retail':
        s=snaps.get(row.id);auth=db.scalar(select(MemberPricingAuthorization).where(MemberPricingAuthorization.snapshot_id==s.id)) if s else None
        if not s or not auth and not allow_pending_retail:return None
        parts=[dict(p,exclusive=p['member_discount_cents']>0 and s.contract['stack_mode']=='exclusive_benefits') for p in s.contract['lines']]
        return dict(quote_id=row.id,revision=1,authorized_at=auth.created_at if auth else None,parts=parts)
    if row.kind=='repair':
        from .repair_models import RepairQuote as Quote,RepairLine as Line,RepairAuthorization as Authorization
    else:
        from .addon_models import AddonQuote as Quote,AddonLine as Line,AddonAuthorization as Authorization
    quotes=list(db.scalars(select(Quote).where(Quote.case_id==row.id).order_by(Quote.revision)));ids=[q.id for q in quotes]
    auths={a.quote_id:a for a in db.scalars(select(Authorization).where(Authorization.quote_id.in_(ids)))} if ids else {}
    if row.kind=='repair':current=next((q for q in quotes if q.id==row.data.get('authorized_quote_id')),None)
    else:current=next((q for q in reversed(quotes) if q.id in auths),None)
    if not current or current.id not in auths or row.kind=='repair' and current.purpose!='service':return None
    lines=defaultdict(list)
    for l in db.scalars(select(Line).where(Line.quote_id.in_(ids)).order_by(Line.id)):lines[l.quote_id].append(l)
    memo={}
    def reconstruct(q):
        if q.id in memo:return memo[q.id]
        earlier=[p for p in quotes if p.revision<q.revision and (row.kind=='addon' or p.id in auths and auths[p.id].created_at<=q.created_at)]
        previous=earlier[-1] if earlier else None;prior=reconstruct(previous) if previous else {};result={};s=snaps.get(q.id)
        explicit={(p['line_key'],p['component']):p for p in s.contract['lines']} if s else {}
        for line in lines[q.id]:
            components=[(line.kind,line.amount_cents)] if row.kind=='repair' else [('goods',line.goods_cents),('installation',line.installation_cents)]
            for component,amount in components:
                key=(line.line_key,component);p=explicit.get(key);old=prior.get(key)
                carried=bool(old and (p and p['carry_cents'] or not p))
                discount=(old['member_discount_cents'] if carried else 0)+(p['member_discount_cents'] if p else 0)
                exclusive=bool(carried and old['exclusive'] or p and p['member_discount_cents'] and s.contract['stack_mode']=='exclusive_benefits')
                result[key]=dict(line_key=line.line_key,component=component,amount_cents=amount,member_discount_cents=discount,exclusive=exclusive,price_source=p.get('price_source','ordinary') if p else old.get('price_source','ordinary') if carried else 'ordinary')
        memo[q.id]=result;return result
    return dict(quote_id=current.id,revision=current.revision,authorized_at=auths[current.id].created_at,parts=list(reconstruct(current).values()))

def build_member_pricing(db,user,cases,stores,bounded,yuan,in_period):
    if user.role not in {'admin','manager','finance','auditor'}:return {'tables':{},'charts':[],'metrics':{}}
    aggregate=bool(getattr(user,'_aggregate_scope',False) or len([s for s in db.info.get('store_scope',()) if s])>1)
    key='member_pricing_current_quotes';table={'title':'当前已授权报价会员折让','headers':['门店','当前报价数','会员折让（元）'] if aggregate else ['原单','门店','业务','当前报价版本','当前授权日期','会员折让（元）'],'rows':[]};totals=defaultdict(lambda:[0,0])
    for row in cases:
        value=current_quote_prices(db,row)
        if not value or not in_period(business_day(value['authorized_at'])):continue
        discount=sum(p['member_discount_cents'] for p in value['parts'])
        if not discount:continue
        store=stores.get(row.store_id,'');totals[store][0]+=1;totals[store][1]+=discount
        if not aggregate:table['rows'].append({'values':[row.number,store,{'repair':'维修','addon':'加装','retail':'精品'}[row.kind],value['revision'],business_day(value['authorized_at']).isoformat(),yuan(discount)],'amount_cents':discount,'quote_id':value['quote_id'],'route':{'type':'case','id':row.id}})
    if aggregate:table['rows']=[{'values':[store,n,yuan(amount)],'amount_cents':amount,'quote_count':n} for store,(n,amount) in sorted(totals.items())]
    labels=sorted(totals)
    return {'tables':{key:table},'charts':[{'id':key,'title':'当前已授权报价会员折让','section':'finance','type':'bar','unit':'cents','labels':labels,'series':[{'name':'会员折让','values':[totals[s][1] for s in labels]}],'table':key,'caption':'按当前正常报价的客户授权日期筛选，每单只取当前已授权版本，并承接原行已冻结会员折让。待授权、已取消和停工报价不计；这是当前价格事实，不是实际消费优惠、现金或营收，退货不反向改写原授权报价。'}],'metrics':{'current_authorized_member_discount_cents':sum(v[1] for v in totals.values()),'current_authorized_member_quote_count':sum(v[0] for v in totals.values())}}
