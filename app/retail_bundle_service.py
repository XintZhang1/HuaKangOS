"""Frozen per-set pricing, ordinary retail fulfillment, no second cash or stock ledger."""
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today
from .tenancy import single_store
from .flow_models import Item, Customer
from .retail_models import RetailLine
from .retail_bundle_models import RetailBundleRule as Rule, RetailBundleComponent as Component, RetailBundleSale as Sale, RetailBundleAllocation as Allocation, RetailBundleReceipt as Receipt
from . import retail_service as retail

RULE_ROLES = {'admin', 'manager'}
READ_ROLES = retail.MONEY_ROLES
TERMS = '退货按本单冻结的商品及安装分摊金额和原出库剩余数量办理，最后一次收尽余分；不因退回部分商品重新定价剩余商品。已实际完成的对应安装费保留，未施工的对应安装费随验收退货减免。'


def _read(user):
    if user.role not in READ_ROLES: raise HTTPException(403, '当前岗位不能查看精品套餐配置和价格')


def _rule(db, key):
    return retail._one(db, Rule, key)


def _components(db, rule_id):
    return list(db.scalars(select(Component).where(Component.rule_id == rule_id).order_by(Component.sequence)))


def _latest(db, code):
    return db.scalar(select(func.max(Rule.rule_version)).where(Rule.code == code)) or 0


def _current(db, rule):
    if rule.rule_version != _latest(db, rule.code) or not rule.enabled:
        raise HTTPException(409, '此精品套餐版本已停用或已有新版本，请刷新后重新选择')
    if not rule.sale_starts_on <= today() <= rule.sale_ends_on:
        raise HTTPException(409, '当前日期不在精品套餐的销售有效期内')


def rule_info(db, rule):
    def clean(row):
        return {c.name: (getattr(row,c.name).isoformat() if isinstance(getattr(row,c.name),date) else getattr(row,c.name)) for c in row.__table__.columns}
    return {**clean(rule), 'mandatory_terms': TERMS, 'components': [clean(c) for c in _components(db,rule.id)]}


def rules(db, user):
    _read(user)
    values=list(db.scalars(select(Rule).order_by(Rule.id.desc()).limit(1001)))
    if len(values)>1000: raise HTTPException(409,'套餐版本过多，请按门店整理后查询')
    latest={}
    for r in values: latest[(r.store_id,r.code)]=max(latest.get((r.store_id,r.code),0),r.rule_version)
    return {'items':[{**rule_info(db,r),'is_latest':r.rule_version==latest[(r.store_id,r.code)]} for r in values], 'mandatory_terms':TERMS}


def create_rule(db, user, request_id, base_version, values):
    if user.role not in RULE_ROLES: raise HTTPException(403,'精品套餐须由店长或管理员配置')
    single_store(db)
    digest=retail.flow.request_digest('retail_bundle_rule',{'base_version':base_version,'values':values})
    try:
        previous=db.scalar(select(Receipt).where(Receipt.request_id==request_id))
        if previous:
            if previous.actor_id!=user.id or previous.digest!=digest: raise HTTPException(409,'原请求编号的经办人或内容不一致')
            return rule_info(db,_rule(db,previous.rule_id))
        current=_latest(db,values['code'])
        if current!=base_version: raise HTTPException(409,'套餐配置已更新，请基于最新版本发布')
        if values['sale_starts_on']>values['sale_ends_on']: raise HTTPException(422,'销售结束日期不能早于开始日期')
        if len({v['item_id'] for v in values['components']})!=len(values['components']): raise HTTPException(422,'同一套餐不能重复配置同一商品，请合并数量')
        from .master_data import require_active
        prepared=[];weights=[]
        for value in values['components']:
            item=retail._one(db,Item,value['item_id'])
            if not item.active: raise HTTPException(409,'套餐商品已停用')
            work=require_active(db,'work_items',value['work_item_id']) if value['work_item_id'] else None
            if not work and value['installation_reference_cents']: raise HTTPException(422,'未配置安装项目不能分摊安装金额')
            weights.extend([value['goods_reference_cents'],value['installation_reference_cents']])
            prepared.append((item,work,value))
        gross=sum(weights)
        if not gross or gross>1_000_000_000_000 or values['price_cents_per_set']>gross: raise HTTPException(422,'每套成交金额不能超过参考合计，且须明确正数参考金额')
        amounts=retail._distribute(values['price_cents_per_set'],weights)
        rule=Rule(code=values['code'],name=values['name'],rule_version=current+1,enabled=values['enabled'],
            sale_starts_on=date.fromisoformat(values['sale_starts_on']),sale_ends_on=date.fromisoformat(values['sale_ends_on']),
            price_cents_per_set=values['price_cents_per_set'],refund_terms=values['refund_terms'],created_by=user.id)
        db.add(rule);db.flush()
        for idx,(item,work,value) in enumerate(prepared):
            db.add(Component(rule_id=rule.id,sequence=idx+1,sku=item.sku,name=item.name,unit=item.unit,
                work_code=work.code if work else '',work_name=work.name if work else '',
                goods_cents_per_set=amounts[2*idx],installation_cents_per_set=amounts[2*idx+1],**value))
        db.add(Receipt(request_id=request_id,actor_id=user.id,digest=digest,rule_id=rule.id));db.flush()
        from .services import audit
        audit(db,user.id,'create','retail_bundle_rule',rule.id,after={'code':rule.code,'version':rule.rule_version,'enabled':rule.enabled},reason='发布冻结的店内精品套餐规则')
        db.commit();return rule_info(db,rule)
    except (IntegrityError,OperationalError,StaleDataError):
        db.rollback();raise HTTPException(409,'套餐规则并发变化或请求重复，请刷新并保留原请求编号')
    except Exception: db.rollback();raise


def preview(db,user,key,sets):
    _read(user);single_store(db)
    rule=_rule(db,key);_current(db,rule)
    from .inventory_availability import available_quantity
    from .master_data import require_active
    result=rule_info(db,rule);available=[]
    for c in result['components']:
        item=retail._one(db,Item,c['item_id'])
        if not item.active: raise HTTPException(409,'套餐商品已停用，请配置新版本')
        if c['work_item_id']: require_active(db,'work_items',c['work_item_id'])
        if item.unit!=c['unit']: raise HTTPException(409,'商品计量单位已经变化，请发布套餐新版本')
        c.update(quantity_milli=c['quantity_milli_per_set']*sets,goods_cents=c['goods_cents_per_set']*sets,installation_cents=c['installation_cents_per_set']*sets)
        available.append(max(0,available_quantity(db,item))//c['quantity_milli_per_set'])
    result.update(sets=sets,amount_cents=rule.price_cents_per_set*sets,available_sets=min(available))
    return result


def create_sale(db,user,request_id,values):
    if values.get('member_pricing') is None:values={k:value for k,value in values.items() if k!='member_pricing'}
    if user.role not in retail.FRONT: raise HTTPException(403,'销售或服务顾问才能开精品套餐单')
    def operation():
        rule=_rule(db,values['rule_id']);_current(db,rule)
        if rule.rule_version!=values['rule_version']: raise HTTPException(409,'精品套餐版本已变化，请重新核对原报价')
        if values['terms_accepted'] is not True: raise HTTPException(422,'请先向客户说明并确认冻结的套餐退货及安装费用规则')
        customer=retail._one(db,Customer,values['customer_id'])
        if user.role=='sales' and customer.owner_id!=user.id: raise HTTPException(403,'此客户不在本人范围，请先由主管交接')
        related=values.get('related_repair_id')
        if related:
            repair=retail.flow.get_case(db,user,related)
            if repair.kind!='repair' or repair.customer_id!=customer.id: raise HTTPException(422,'精品附带销售须关联同店同一客户的可读维修原单')
        components=_components(db,rule.id);sets=values['sets'];prepared=[];net=[];gross=0
        from .inventory_availability import assert_can_issue
        from .master_data import require_active
        # Lock in item order to serialize every stock writer without cross-bundle deadlocks.
        items={}
        for c in sorted(components,key=lambda c:c.item_id):
            item=db.scalar(select(Item).where(Item.id==c.item_id).with_for_update())
            if not item or not item.active or item.unit!=c.unit: raise HTTPException(409,'套餐商品已停用或单位已变化，请发布新版本')
            qty=c.quantity_milli_per_set*sets
            if qty>1_000_000_000: raise HTTPException(422,'套餐数量超出单行上限')
            assert_can_issue(db,item,qty);items[c.item_id]=item
        for c in components:
            item=items[c.item_id];work=require_active(db,'work_items',c.work_item_id) if c.work_item_id else None
            line={'quantity_milli':c.quantity_milli_per_set*sets,'unit_price_cents':0,'installation_unit_price_cents':0,
                'sku':c.sku,'name':c.name,'unit':c.unit,'work_code':c.work_code,'work_name':c.work_name}
            prepared.append((item,work,line));net.extend([c.goods_cents_per_set*sets,c.installation_cents_per_set*sets])
            gross+=(c.goods_reference_cents+c.installation_reference_cents)*sets
        if gross>1_000_000_000_000: raise HTTPException(422,'套餐合计超出金额上限')
        from . import member_pricing_service as pricing
        contract=pricing.prepare_retail(db,user,customer,prepared,net,values.get('member_pricing'),bundle_rule_id=rule.id)
        if contract:net=[p['net_cents'] for p in contract['lines']]
        row=retail._create_frozen_order(db,user,customer,related,prepared,net,gross-sum(net));db.flush()
        pricing.freeze_quote(db,user,row,'retail',row.id,contract)
        sale=Sale(case_id=row.id,rule_id=rule.id,sets=sets,terms_accepted=True,actor_id=user.id);db.add(sale);db.flush()
        lines={line.item_id:line for line in retail._rows(db,RetailLine,case_id=row.id)}
        for c in components:
            db.add(Allocation(sale_id=sale.id,component_id=c.id,line_id=lines[c.item_id].id,quantity_milli=c.quantity_milli_per_set*sets,
                goods_reference_cents=c.goods_reference_cents*sets,installation_reference_cents=c.installation_reference_cents*sets,
                goods_cents=c.goods_cents_per_set*sets,installation_cents=c.installation_cents_per_set*sets))
        retail.flow.log_event(db,user,row,'retail_bundle_create','按冻结套餐组成及每套分摊开单',detail={'rule_id':rule.id,'rule_version':rule.rule_version,'sets':sets,'terms_accepted':True})
        return row
    return retail._execute(db,user,request_id,'bundle_create',values,operation)


def sale_info(db,row,money=True):
    sale=db.scalar(select(Sale).where(Sale.case_id==row.id))
    if not sale: return None
    rule=_rule(db,sale.rule_id)
    result={'id':sale.id,'rule_id':rule.id,'code':rule.code,'name':rule.name,'rule_version':rule.rule_version,'sets':sale.sets,
        'mandatory_terms':TERMS,'terms_accepted':sale.terms_accepted}
    if money:
        result['refund_terms']=rule.refund_terms
        result['price_cents_per_set']=rule.price_cents_per_set
        result['allocations']=[{k:getattr(a,k) for k in ('line_id','component_id','quantity_milli','goods_reference_cents','installation_reference_cents','goods_cents','installation_cents')}
            for a in db.scalars(select(Allocation).where(Allocation.sale_id==sale.id).order_by(Allocation.id))]
    return result


def analytics_rows(db,user):
    """A source dimension of existing retail facts, never an added revenue/cash source."""
    if user.role not in {'admin','manager','finance','auditor'}: raise HTTPException(403,'当前岗位不能查看套餐经营汇总')
    from .flow_models import Case
    from .retail_models import RetailReturnPosting,RetailDispatch
    sales=list(db.execute(select(Sale,Rule,Case).join(Rule,Rule.id==Sale.rule_id).join(Case,Case.id==Sale.case_id).order_by(Sale.id).limit(25001)))
    if len(sales)>25000: raise HTTPException(409,'套餐经营来源过多，请缩小门店范围后查询')
    keys=[sale.case_id for sale,_,_ in sales]
    postings=list(db.scalars(select(RetailReturnPosting).where(RetailReturnPosting.case_id.in_(keys)).limit(25001))) if keys else []
    dispatches=list(db.scalars(select(RetailDispatch).where(RetailDispatch.case_id.in_(keys)).limit(25001))) if keys else []
    if max(len(postings),len(dispatches))>25000: raise HTTPException(409,'套餐库存来源过多，请缩小门店范围后查询')
    from collections import defaultdict
    returned=defaultdict(lambda:[0,0,0]);cost=defaultdict(int)
    for p in postings:
        returned[p.case_id][0]+=p.goods_cents+p.installation_cents-p.retained_cents
        returned[p.case_id][1]+=p.retained_cents;returned[p.case_id][2]+=p.value_cents
    for d in dispatches:cost[d.case_id]+=d.value_cents
    return [{'case_id':row.id,'number':row.number,'store_id':row.store_id,'rule_id':rule.id,'code':rule.code,'name':rule.name,
        'rule_version':rule.rule_version,'sets':sale.sets,'business_date':row.business_date.isoformat(),'accepted_date':row.data.get('accepted_date'),
        'quoted_cents':row.amount_cents,'return_reduction_cents':returned[row.id][0],'retained_installation_cents':returned[row.id][1],
        'charge_cents':0 if row.data.get('cancelled') else row.amount_cents-returned[row.id][0],
        'cost_cents':cost[row.id]-returned[row.id][2],'cancelled':bool(row.data.get('cancelled'))} for sale,rule,row in sales]
