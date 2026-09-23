"""Local approval owns prices; membership identity never grants implicit price authority."""
from datetime import date
import uuid
from fastapi import HTTPException
from sqlalchemy import select,func
from .db import today,utcnow
from .tenancy import single_store
from .flow_models import Case,Task,Item,FileAsset
from .master_models import WorkItem,MemberTier
from .membership_models import MembershipRule,MembershipPeriod
from .group_models import GroupMember,GroupIdentityLink
from .member_pricing_models import *
from . import group_service as group,flow_engine as flow
from .file_security import require_usable
from .member_pricing_specs import spec

MANAGE={'admin','manager'}
READ=MANAGE|{'finance','auditor'}
FRONT=READ|{'sales','service'}
STACKS={'member_then_benefits':'先会员价，再按原剩余容量使用券包赠金','exclusive_benefits':'会员价与券包赠金不叠用；本金仍可付款'}
COMPONENTS={'repair':{'work','part'},'retail':{'goods','installation'},'addon':{'goods','installation'}}
LINE_FIELDS=('line_key','component','source_id','scope_id','charge_scope','basis_cents','member_discount_cents','manual_discount_cents','net_cents','carry_cents','basis_points')
def canonical(value):return flow.request_digest('member_pricing',value)
def can_read(user,row=None):return user.role in READ and not getattr(user,'_aggregate_scope',False)
def _role(user,roles):
    if user.role not in roles or getattr(user,'_aggregate_scope',False):raise HTTPException(403,'请由本店有权岗位办理会员价格，不支持集团汇总写入')
def _rows(db,model,**kw):return list(db.scalars(select(model).filter_by(**kw).order_by(model.id)))
def _one(db,model,key):
    result=db.scalar(select(model).where(model.id==key))
    if not result:raise HTTPException(404,'本店原会员价格或明细来源不存在')
    return result
def plain(row):return {c.name:(getattr(row,c.name).isoformat() if isinstance(getattr(row,c.name),date) else getattr(row,c.name)) for c in row.__table__.columns}
def get_rule(db,user,key):
    single_store(db);_role(user,READ);rule=_one(db,MemberPricingRule,key);row=flow.get_case(db,user,rule.case_id)
    if row.kind!='member_pricing_rule' or row.flow_version!=1:raise HTTPException(409,'不支持的会员价格规则版本')
    return rule,row

def _latest(db,code):
    approved=select(MemberPricingDecision.rule_id).where(MemberPricingDecision.decision=='approved')
    return db.scalar(select(MemberPricingRule).where(MemberPricingRule.code==code,MemberPricingRule.id.in_(approved)).order_by(MemberPricingRule.rule_version.desc()))
def _current(db,rule):
    latest=_latest(db,rule.code)
    if not latest or latest.id!=rule.id or not rule.enabled or not rule.starts_on<=today()<=rule.ends_on:raise HTTPException(409,'会员价格规则未生效、已停用、过期或已有新批准版本，请重新报价')

def _proof(db,user,row,key):
    from .flow_documents import can_file
    asset=_one(db,FileAsset,key);require_usable(db,asset)
    if asset.case_id!=row.id or asset.generated or asset.category not in {'evidence','authorization'} or not can_file(user,row,asset):raise HTTPException(403,'请上传本价格申请已扫描通过且本人可读的真实依据')
    if db.scalar(select(MemberPricingDecision.id).join(FileAsset,FileAsset.id==MemberPricingDecision.evidence_id).where(FileAsset.case_id==row.id,FileAsset.sha256==asset.sha256)):
        raise HTTPException(409,'独立批准须使用本次复核依据，不重复使用申请原件')
    return asset

def _scope(db,v):
    kind=v['business_kind'];component=v['component']
    if kind not in COMPONENTS or component not in COMPONENTS[kind]:raise HTTPException(422,'业务与价格组件不匹配')
    source=_one(db,WorkItem if component in {'work','installation'} else Item,v['source_id'])
    if not source.active:raise HTTPException(409,'不能为停用项目建立新会员价格范围')
    snapshot={k:getattr(source,k) for k in ('id','version','name')};snapshot['code']=source.code if component in {'work','installation'} else source.sku
    bundle={}
    if v.get('bundle_rule_id'):
        from .retail_bundle_models import RetailBundleRule,RetailBundleComponent
        if kind!='retail':raise HTTPException(422,'精品套装范围只适用于精品商品及安装')
        r=_one(db,RetailBundleRule,v['bundle_rule_id']);column=RetailBundleComponent.work_item_id if component=='installation' else RetailBundleComponent.item_id
        if not db.scalar(select(RetailBundleComponent.id).where(RetailBundleComponent.rule_id==r.id,column==source.id)):raise HTTPException(409,'指定项目不属于此套装原组件')
        bundle={k:getattr(r,k) for k in ('id','code','rule_version','name','price_cents_per_set')}
    if v.get('allow_contract_pricing') and kind!='repair':raise HTTPException(422,'合同维修基价叠用仅适用于明确客户维修收费')
    return dict(business_kind=kind,component=component,source_id=source.id,source_snapshot=snapshot,basis_points=v['basis_points'],bundle_rule_id=v.get('bundle_rule_id'),bundle_snapshot=bundle,allow_contract_pricing=v.get('allow_contract_pricing',False))

def describe(db,user,rule):
    _role(user,READ);row=_one(db,Case,rule.case_id)
    return dict(**plain(rule),case_version=row.version,state=row.state,number=row.number,scopes=[plain(s) for s in _rows(db,MemberPricingScope,rule_id=rule.id)],decisions=[plain(d) for d in _rows(db,MemberPricingDecision,rule_id=rule.id)],tasks=[dict(id=t.id,key=t.key,assignee_id=t.assignee_id,due_date=t.due_date.isoformat()) for t in _rows(db,Task,case_id=row.id,status='open')])

def create_rule(db,user,request_id,v):
    def run(sid):
        member_rule=_one(db,MembershipRule,v['membership_rule_id'])
        if sid not in member_rule.allowed_store_ids:raise HTTPException(403,'集团会期版本没有本店适用权限')
        if not date(2000,1,1)<=date.fromisoformat(v['starts_on'])<=date.fromisoformat(v['ends_on'])<=date(2100,1,1):raise HTTPException(422,'请核对价格有效起止日期')
        if v['enabled'] and not v['scopes']:raise HTTPException(422,'启用会员价格前须明确至少一个本店项目范围')
        scopes=[_scope(db,x) for x in v['scopes']]
        keys=[(s['business_kind'],s['component'],s['source_id'],s['bundle_rule_id'],s['allow_contract_pricing']) for s in scopes]
        if len(keys)!=len(set(keys)):raise HTTPException(422,'相同业务项目及套装/合同范围不能重复配置')
        tier={}
        if v.get('reference_tier_id'):
            t=_one(db,MemberTier,v['reference_tier_id'])
            if not t.active or t.version!=v.get('reference_tier_version'):raise HTTPException(409,'参考会员等级已变更，请重新核对')
            tier={k:getattr(t,k) for k in ('id','version','code','name','discount_basis_points')}
        elif v.get('reference_tier_version') is not None:raise HTTPException(422,'参考等级及其版本必须成对填写')
        revision=(db.scalar(select(func.max(MemberPricingRule.rule_version)).where(MemberPricingRule.code==v['code'])) or 0)+1
        member_snapshot={k:getattr(member_rule,k) for k in ('id','code','rule_version','name','allowed_store_ids')}
        payload={k:v[k] for k in ('code','name','enabled','membership_rule_id','starts_on','ends_on','stack_mode','reason')};payload.update(rule_version=revision,membership_snapshot=member_snapshot,reference_tier_id=v.get('reference_tier_id'),reference_tier_snapshot=tier,scopes=scopes)
        row=Case(kind='member_pricing_rule',flow_version=1,number='HKMP'+uuid.uuid4().hex[:18].upper(),title='会员价格 · '+v['name'],state='draft',owner_id=user.id,created_by=user.id,business_date=today(),due_date=today(),data={})
        db.add(row);db.flush()
        from .business_entity_service import freeze_case_entity
        freeze_case_entity(db,user,row)
        rule=MemberPricingRule(case_id=row.id,**{k:x for k,x in payload.items() if k not in {'scopes','starts_on','ends_on'}},starts_on=date.fromisoformat(v['starts_on']),ends_on=date.fromisoformat(v['ends_on']),digest=canonical(payload),actor_id=user.id)
        db.add(rule);db.flush();row.data={'member_price_rule_id':rule.id};db.add_all([MemberPricingScope(rule_id=rule.id,sequence=i+1,**s) for i,s in enumerate(scopes)]);db.flush()
        flow.ensure_task(db,row,'member_price_submit','提交明确会员价格与叠用依据','manager',assignee=user.id)
        flow.log_event(db,user,row,'member_price_create','建立本店会员价格版本',detail={'rule_id':rule.id,'digest':rule.digest});return describe(db,user,rule)
    return group._execute(db,user,request_id,'member_price_create',v,run,MANAGE)

def command(db,user,key,request_id,version,action,v):
    def run(sid):
        rule,row=get_rule(db,user,key)
        if row.version!=version:raise HTTPException(409,'价格申请已变化，请刷新并保留原请求编号')
        row.updated_at=utcnow();db.flush()
        if action=='submit':
            if row.state!='draft' or rule.actor_id!=user.id:raise HTTPException(409,'请由原申请人提交尚未提交的价格版本')
            _proof(db,user,row,v['evidence_id']);decision='submitted';row.state='approval'
            managers=[u for u in flow.eligible_users(db,'manager',sid) if u.id!=rule.actor_id]
            if not managers:raise HTTPException(409,'请配置另一位主管独立批准会员价格')
            flow.finish_task(db,row,'member_price_submit',user);flow.ensure_task(db,row,'member_price_approve','独立核对适用等级、项目、比例与叠用','manager',assignee=managers[0].id)
        elif action in {'approve','reject'}:
            if row.state!='approval':raise HTTPException(409,'价格版本不在待独立复核阶段')
            task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key=='member_price_approve',Task.status=='open'))
            if user.id==rule.actor_id:raise HTTPException(403,'申请人不能自批会员价格，管理员也不例外')
            if not task or user.role!='admin' and task.assignee_id!=user.id:raise HTTPException(403,'请由当前主管接手人办理或先明确交接')
            _proof(db,user,row,v['evidence_id']);latest=_latest(db,rule.code)
            if action=='approve':
                if latest and latest.rule_version>=rule.rule_version:raise HTTPException(409,'已有更新的批准价格版本，不能逆序批准旧申请')
                if rule.enabled:
                    for s in _rows(db,MemberPricingScope,rule_id=rule.id):
                        source=_one(db,WorkItem if s.component in {'work','installation'} else Item,s.source_id)
                        if not source.active or source.version!=s.source_snapshot['version']:raise HTTPException(409,'价格复核期间原项目已变化，请重新提交明确范围')
                from .business_entity_service import require_case_entity
                require_case_entity(db,user,row)
            decision='approved' if action=='approve' else 'rejected';row.state='completed' if action=='approve' else 'rejected';flow.close_tasks(db,row,user)
        elif action=='cancel':
            if row.state not in {'draft','approval'}:raise HTTPException(409,'已决定价格不普通取消；停用须新建并批准停用版本')
            decision='cancelled';row.state='cancelled';flow.close_tasks(db,row,user)
        else:raise HTTPException(404,'不存在此价格办理步骤')
        db.add(MemberPricingDecision(rule_id=rule.id,decision=decision,reason=v['reason'],evidence_id=v.get('evidence_id'),actor_id=user.id));db.flush()
        flow.log_event(db,user,row,'member_price_'+action,{'submit':'提交本店会员价格依据','approve':'独立批准会员价格','reject':'退回会员价格依据','cancel':'取消未生效会员价格'}[action],detail={'rule_id':rule.id,'digest':rule.digest,**v});db.flush();return describe(db,user,rule)
    return group._execute(db,user,request_id,'member_price_'+action,dict(rule_id=key,version=version,values=v),run,MANAGE)

def _member_state(db,user,row,rule,lock=False):
    from .membership_service import current_period
    sid=single_store(db)
    if row.store_id!=sid or not row.customer_id:raise HTTPException(409,'会员价格须关联本店真实客户原业务')
    with group.authority(db,user,FRONT):
        q=select(GroupMember).join(GroupIdentityLink,GroupIdentityLink.identity_id==GroupMember.identity_id).where(GroupIdentityLink.local_kind=='customer',GroupIdentityLink.local_id==row.customer_id,GroupIdentityLink.store_id==sid)
        member=db.scalar(q.with_for_update() if lock else q)
        if not member or not member.active:raise HTTPException(409,'本店客户没有已确认且启用的集团会员身份')
        period=current_period(db,member)
        if not period or period.rule_id!=rule.membership_rule_id:raise HTTPException(409,'当前实际会期或等级不适用本价格版本，请重新核对报价')
        original=_one(db,MembershipRule,period.rule_id);latest=db.scalar(select(MembershipRule).where(MembershipRule.code==original.code).order_by(MembershipRule.rule_version.desc()))
        if not latest.enabled or sid not in original.allowed_store_ids or sid not in latest.allowed_store_ids:raise HTTPException(409,'会员等级已停用或不适用本店，不能新授权会员价')
        if lock:member.updated_at=utcnow();db.flush()
        return dict(member_id=member.id,identity_id=member.identity_id,period_id=period.id,membership_rule_id=period.rule_id,starts_on=period.starts_on.isoformat(),ends_on=period.ends_on.isoformat())

def candidates(db,user,row):
    _role(user,FRONT);result=[]
    for rule in db.scalars(select(MemberPricingRule).where(MemberPricingRule.enabled.is_(True)).order_by(MemberPricingRule.id.desc())):
        try:_current(db,rule);_member_state(db,user,row,rule)
        except HTTPException as error:
            if error.status_code in {403,404,409}:continue
            raise
        result.append(dict(id=rule.id,rule_version=rule.rule_version,name=rule.name,stack_mode=rule.stack_mode,membership_name=rule.membership_snapshot['name'],starts_on=rule.starts_on.isoformat(),ends_on=rule.ends_on.isoformat(),scopes=[plain(s) for s in _rows(db,MemberPricingScope,rule_id=rule.id)]))
    return result

def _distribute(total,weights):
    if not total:return [0]*len(weights)
    base=sum(weights)
    if total>base or base<=0:raise HTTPException(422,'人工优惠不能超过会员价后的本次新增收费')
    pieces=[total*w//base for w in weights];left=total-sum(pieces)
    for i in sorted(range(len(weights)),key=lambda i:(-(total*weights[i]%base),i))[:left]:pieces[i]+=1
    return pieces

def prepare_quote(db,user,row,selection,components,manual_discount_cents=0):
    """Components are newly chargeable increments; prior authorized amounts are carried unchanged."""
    if not selection:return None
    _role(user,FRONT);rule=_one(db,MemberPricingRule,selection['rule_id']);_current(db,rule)
    if selection.get('rule_version')!=rule.rule_version:raise HTTPException(409,'所选价格版本已变化，请重新核对')
    identity=_member_state(db,user,row,rule,True);scopes=_rows(db,MemberPricingScope,rule_id=rule.id);priced=[];seen=set();matched=False
    if row.kind not in COMPONENTS or (row.kind=='repair' and row.flow_version not in {3,4}) or (row.kind=='retail' and row.flow_version!=2) or (row.kind=='addon' and row.flow_version!=3):raise HTTPException(409,'此原业务版本不支持会员价格，不能改写旧版本报价')
    for c in components:
        identity_key=(c['line_key'],c['component'])
        if identity_key in seen or c['basis_cents']<0 or c.get('carry_cents',0)<0:raise HTTPException(422,'价格组件重复或金额无效')
        seen.add(identity_key);found=None;charge=c.get('charge_scope','customer')
        if charge!='original_liability' and c['basis_cents']>0 and c.get('price_source')!='package_contract':
            found=next((s for s in scopes if s.business_kind==row.kind and s.component==c['component'] and s.source_id==c['source_id'] and s.bundle_rule_id==c.get('bundle_rule_id') and s.allow_contract_pricing==bool(c.get('contract_rule_id'))),None)
        rate=found.basis_points if found else 10000;net=(c['basis_cents']*rate+5000)//10000
        if c['basis_cents']>0 and net==0:raise HTTPException(409,'会员比例把正价舍入为零，请调整明确价格或使用既有赠送授权，不跳过赠送核价')
        if found:matched=True
        priced.append(dict(line_key=c['line_key'],component=c['component'],source_id=c['source_id'],scope_id=found.id if found else None,charge_scope=charge,basis_cents=c['basis_cents'],member_discount_cents=c['basis_cents']-net,manual_discount_cents=0,net_cents=net,carry_cents=c.get('carry_cents',0),basis_points=rate,bundle_rule_id=c.get('bundle_rule_id'),contract_rule_id=c.get('contract_rule_id'),price_source=c.get('price_source','ordinary'),contract_component_id=c.get('contract_component_id')))
    if not matched:raise HTTPException(409,'本次新增收费没有所选规则明确适用项目；原责任行与未授权套装/合同基价不参与会员折扣')
    discounts=_distribute(manual_discount_cents,[p['net_cents'] if p['charge_scope']!='original_liability' and p['price_source']!='package_contract' else 0 for p in priced])
    for p,discount in zip(priced,discounts):p['manual_discount_cents']=discount;p['net_cents']-=discount
    if rule.stack_mode=='exclusive_benefits' and any(p['member_discount_cents'] for p in priced) and getattr(row,'id',None):
        from .group_benefits_models import BenefitReservation,BenefitEntry
        with group.authority(db,user,FRONT):
            held=db.scalar(select(BenefitReservation.id).where(BenefitReservation.case_id==row.id,BenefitReservation.status=='reserved'))
            consumed=db.scalar(select(func.coalesce(func.sum(BenefitEntry.credit_cents),0)).where(BenefitEntry.case_id==row.id,BenefitEntry.purpose.in_(['capture','reverse']))) or 0
        if held or consumed>0:raise HTTPException(409,'本单已有券包赠金占额或核销，不能新增与其互斥的会员价；请先按原来源处理')
    contract=dict(definition_version=1,case_kind=row.kind,flow_version=row.flow_version,customer_id=row.customer_id,store_id=row.store_id,rule_id=rule.id,rule_digest=rule.digest,rule_version=rule.rule_version,stack_mode=rule.stack_mode,priced_on=today().isoformat(),identity=identity,lines=priced)
    return contract

def freeze_quote(db,user,row,quote_kind,quote_id,contract):
    if not contract:return None
    if (contract['case_kind'],contract['store_id'],contract['customer_id'])!=(row.kind,row.store_id,row.customer_id) or quote_kind!=row.kind:raise HTTPException(409,'会员价格来源与本次原报价不一致')
    ident=contract['identity'];snap=MemberPricingSnapshot(case_id=row.id,quote_kind=quote_kind,quote_id=quote_id,rule_id=contract['rule_id'],customer_id=row.customer_id,member_id=ident['member_id'],period_id=ident['period_id'],definition_version=1,contract=contract,digest=canonical(contract),actor_id=user.id)
    db.add(snap);db.flush();db.add_all([MemberPricingLine(snapshot_id=snap.id,**{k:l[k] for k in LINE_FIELDS}) for l in contract['lines']]);db.flush();return snap

def snapshot(db,row,quote_id):return db.scalar(select(MemberPricingSnapshot).where(MemberPricingSnapshot.case_id==row.id,MemberPricingSnapshot.quote_kind==row.kind,MemberPricingSnapshot.quote_id==quote_id))
def guard_authorization(db,user,row,quote_id):
    snap=snapshot(db,row,quote_id)
    if not snap:return None
    if snap.definition_version!=1 or snap.digest!=canonical(snap.contract):raise HTTPException(409,'会员价格冻结来源无效')
    if db.scalar(select(MemberPricingAuthorization.id).where(MemberPricingAuthorization.snapshot_id==snap.id)):return snap
    rule=_one(db,MemberPricingRule,snap.rule_id);_current(db,rule)
    if _member_state(db,user,row,rule,True)!=snap.contract['identity']:raise HTTPException(409,'原报价后会员身份或会期已变化，请撤回并重新报价，不改写已批准价格')
    return snap

def record_authorization(db,user,row,quote_id,evidence_id):
    snap=guard_authorization(db,user,row,quote_id)
    if snap and not db.scalar(select(MemberPricingAuthorization.id).where(MemberPricingAuthorization.snapshot_id==snap.id)):
        asset=_one(db,FileAsset,evidence_id);require_usable(db,asset)
        if asset.case_id!=row.id:raise HTTPException(403,'会员价格授权必须属于当前本店原报价')
        db.add(MemberPricingAuthorization(snapshot_id=snap.id,evidence_id=evidence_id,snapshot_digest=snap.digest,actor_id=user.id));db.flush()
    return snap

def active_snapshot(db,row):
    quote_id=(row.data.get('authorized_quote_id') or row.data.get('quote_id')) if row.kind=='repair' else row.id if row.kind=='retail' else row.data.get('addon_quote_id')
    return snapshot(db,row,quote_id) if quote_id else None

def benefit_exclusions(db,row,kind):
    if kind not in {'bonus','coupon','package','points'}:return set()
    from .member_pricing_analytics import current_quote_prices
    value=current_quote_prices(db,row,allow_pending_retail=True)
    return {(p['line_key'],p['component']) for p in value['parts'] if p['exclusive'] and p.get('price_source')!='package_contract'} if value else set()

def guard_benefit_use(db,user,row,kind,component_keys=None):
    blocked=benefit_exclusions(db,row,kind)
    if blocked and (component_keys is None or blocked & set(component_keys)):raise HTTPException(409,'本次会员价项目已明确不与券包赠金叠用；本金仍可支付，不能在授权后重算原价')

def describe_quote(db,user,row,quote_id):
    snap=snapshot(db,row,quote_id)
    if not snap:return None
    if user.role not in FRONT:return None
    rule=_one(db,MemberPricingRule,snap.rule_id)
    return dict(snapshot_id=snap.id,rule_name=rule.name,rule_version=rule.rule_version,membership_name=rule.membership_snapshot['name'],stack_mode=rule.stack_mode,priced_on=snap.contract['priced_on'],member_discount_cents=sum(l['member_discount_cents'] for l in snap.contract['lines']),manual_discount_cents=sum(l['manual_discount_cents'] for l in snap.contract['lines']),lines=snap.contract['lines'],digest=snap.digest)

def prepare_retail(db,user,customer,prepared,basis,selection,manual_discount_cents=0,bundle_rule_id=None):
    from types import SimpleNamespace
    row=SimpleNamespace(kind='retail',flow_version=2,store_id=customer.store_id,customer_id=customer.id)
    components=[]
    for n,(item,work,line) in enumerate(prepared):
        for offset,component,source in [(0,'goods',item.id),(1,'installation',work.id if work else 0)]:
            components.append(dict(line_key='item'+str(item.id),component=component,source_id=source,basis_cents=basis[2*n+offset],carry_cents=0,charge_scope='customer',bundle_rule_id=bundle_rule_id))
    return prepare_quote(db,user,row,selection,components,manual_discount_cents)
