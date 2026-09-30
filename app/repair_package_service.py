"""Mixed prepaid components: one real purchase, explicit exact original intervals."""
from contextlib import contextmanager
from datetime import date,timedelta
import hashlib,json
from fastapi import HTTPException
from sqlalchemy import select,func
from .db import today,utcnow
from .config import settings
from datetime import timezone
from zoneinfo import ZoneInfo
from .models import Store
from .flow_models import Case,Item,FileAsset
from .master_models import WorkItem
from .group_models import GroupMember,GroupIdentityLink
from .tenancy import single_store
from . import group_service as group,flow_engine as flow
from .repair_package_models import *

READ={'admin','manager','finance','auditor','service','sales','reception'}
FRONT={'admin','service','sales'}
MANAGE={'admin','manager'}
FINANCE={'admin','finance'}
MONEY={'admin','manager','finance','auditor','service'}
INTERNAL={'admin','manager','finance','auditor'}
AMOUNTS=('quantity_milli','credit_cents','paid_cents','settlement_cents')

def canonical(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

@contextmanager
def authority(db,user,roles=READ):
    with group.authority(db,user,roles) as sid:
        previous=db.info.get('_package_authority');db.info['_package_authority']=(user.id,sid)
        try:yield sid
        finally:
            if previous is None:db.info.pop('_package_authority',None)
            else:db.info['_package_authority']=previous

def execute(db,user,key,action,values,roles,fn):
    with authority(db,user,roles):return group._execute(db,user,key,'repair_package:'+action,values,fn,roles)

def one(db,model,key):
    obj=db.scalar(select(model).where(model.id==key).with_for_update())
    if not obj:raise HTTPException(404,'当前授权范围内记录不存在')
    return obj

def plain(row):return {c.name:(getattr(row,c.name).isoformat() if isinstance(getattr(row,c.name),(date,datetime)) else getattr(row,c.name)) for c in row.__table__.columns}

def _member(db,key,sid,active=True,write=False):
    linked=select(GroupIdentityLink.identity_id).where(GroupIdentityLink.store_id==sid,GroupIdentityLink.local_kind=='customer')
    query=select(GroupMember).where(GroupMember.id==key,GroupMember.identity_id.in_(linked))
    member=db.scalar(query.with_for_update() if write else query)
    if not member:raise HTTPException(404,'套餐会员尚未明确关联本店真实客户')
    if active and not member.active:raise HTTPException(409,'会员已停用，不能新购买或使用套餐')
    if write:member.updated_at=utcnow();db.flush()
    return member

def _proof(db,user,row,key,authorization=False):
    from .repair_service import _evidence
    asset=_evidence(db,user,row,key)
    if asset.generated or (authorization and asset.category!='authorization'):raise HTTPException(422,'请上传本版客户授权原件')
    return asset

def _rule(db,key,sid,issuance=False):
    rule=one(db,PackageRule,key)
    if sid not in rule.contract['allowed_store_ids']:raise HTTPException(404,'该套餐未授权本店履约')
    if rule.definition_version!=1 or rule.digest!=canonical(rule.contract):raise HTTPException(409,'套餐冻结规则摘要异常')
    actions={r.action for r in db.scalars(select(PackageRuleDecision).where(PackageRuleDecision.rule_id==key))}
    if issuance and ('approve' not in actions or actions&{'reject','cancel','revoke'}):raise HTTPException(409,'套餐规则尚未独立批准或已停止新购买')
    return rule

def rule_info(db,user,rule):
    contract={**rule.contract,'components':[{k:v for k,v in c.items() if k!='settlement_cents' or user.role in INTERNAL} for c in rule.contract['components']]}
    if user.role not in INTERNAL:contract.pop('discount_bearer',None)
    result={'id':rule.id,'issuer_store_id':rule.issuer_store_id,'name':rule.name,'code':rule.code,'rule_version':rule.rule_version,'created_by':rule.actor_id,'digest':rule.digest,'contract':contract,'decisions':[{'action':d.action,'actor_id':d.actor_id,'reason':d.reason} for d in db.scalars(select(PackageRuleDecision).where(PackageRuleDecision.rule_id==rule.id))]}
    result['mappings']=[plain(m) for m in db.scalars(select(PackageMapping).where(PackageMapping.rule_id==rule.id,PackageMapping.store_id==single_store(db)))]
    return result

def rules(db,user):
    with authority(db,user) as sid:
        return {'items':[rule_info(db,user,r) for r in db.scalars(select(PackageRule).order_by(PackageRule.id.desc())) if sid in r.contract['allowed_store_ids']]}

def create_rule(db,user,key,v):
    def run(sid):
        ids=sorted(set(v['allowed_store_ids']))
        if sid not in ids or len(ids)!=len(v['allowed_store_ids']) or len(list(db.scalars(select(Store.id).where(Store.id.in_(ids),Store.active.is_(True)))))!=len(ids):raise HTTPException(422,'请明确发行店及启用的履约门店')
        components=v['components'];keys=[c['key'] for c in components]
        if len(set(keys))!=len(keys):raise HTTPException(422,'组件编号不能重复')
        if not any(c['kind']=='work' for c in components) or not any(c['kind']=='part' for c in components):raise HTTPException(422,'混合套餐须明确实际作业和实际配件组件')
        for c in components:
            if c['kind']=='work' and c['unit']=='job' and c['quantity_milli']%1000:raise HTTPException(422,'按次作业须为完整次数')
            if not 0<=c['paid_cents']<=c['settlement_cents']<=c['credit_cents']:raise HTTPException(422,'组件C/P/S分摊不守恒')
            if c['settlement_cents']!=(c['credit_cents'] if v['discount_bearer']=='group' else c['paid_cents']):raise HTTPException(422,'组件内部价与明确优惠承担方不一致')
        if sum(c['paid_cents'] for c in components)<=0:raise HTTPException(422,'付费混合套餐必须有实际购买对价')
        contract={k:v[k] for k in ('name','allowed_store_ids','validity_days','refund_policy','discount_bearer','components')};contract.update(definition_version=1,issuer_store_id=sid)
        rev=(db.scalar(select(func.max(PackageRule.rule_version)).where(PackageRule.issuer_store_id==sid,PackageRule.code==v['code'])) or 0)+1
        rule=PackageRule(issuer_store_id=sid,code=v['code'],rule_version=rev,name=v['name'],contract=contract,digest=canonical(contract),actor_id=user.id)
        db.add(rule);db.flush();return rule_info(db,user,rule)
    return execute(db,user,key,'rule',v,FRONT|MANAGE,run)

def decide_rule(db,user,key,rule_id,action,v):
    def run(sid):
        rule=_rule(db,rule_id,sid)
        if rule.issuer_store_id!=sid:raise HTTPException(403,'仅原发行店可决定套餐规则')
        decisions=list(db.scalars(select(PackageRuleDecision).where(PackageRuleDecision.rule_id==rule.id)))
        if action=='revoke':
            if not any(d.action=='approve' for d in decisions) or any(d.action=='revoke' for d in decisions):raise HTTPException(409,'仅已批准规则可停止新购买')
        elif decisions:raise HTTPException(409,'规则已经决定，请另立新版本')
        if action in {'approve','reject'} and user.id==rule.actor_id:raise HTTPException(403,'规则申请和批准须由不同员工办理')
        db.add(PackageRuleDecision(rule_id=rule.id,store_id=sid,action=action,reason=v['reason'],actor_id=user.id));db.flush();return rule_info(db,user,rule)
    return execute(db,user,key,'rule:'+str(rule_id)+':'+action,v,MANAGE,run)

def map_component(db,user,key,rule_id,v):
    def run(sid):
        rule=_rule(db,rule_id,sid);c=next((c for c in rule.contract['components'] if c['key']==v['component_key']),None)
        if not c:raise HTTPException(404,'原规则组件不存在')
        obj=one(db,WorkItem if c['kind']=='work' else Item,v['source_id'])
        unit=obj.billing_unit if c['kind']=='work' else obj.unit
        if not obj.active or unit!=c['unit']:raise HTTPException(409,'本店项目或物料停用、计量单位不符')
        mapping=PackageMapping(rule_id=rule.id,component_key=c['key'],store_id=sid,kind=c['kind'],source_id=obj.id,snapshot={'code':obj.code if c['kind']=='work' else obj.sku,'name':obj.name,'unit':unit,'source_version':obj.version,'specification':c['specification'],'confirmation':v['reason']},actor_id=user.id)
        db.add(mapping);db.flush();return plain(mapping)
    return execute(db,user,key,'map:'+str(rule_id),v,MANAGE,run)

def _purchase(db,user,key,sid,active=True,local=False):
    purchase=one(db,PackagePurchase,key)
    if local and purchase.issuer_store_id!=sid:raise HTTPException(404,'购买及退款须在原发行门店办理')
    _rule(db,purchase.rule_id,sid);_member(db,purchase.member_id,sid,active)
    if purchase.digest!=canonical(purchase.contract):raise HTTPException(409,'原购买合同摘要不一致')
    return purchase

def subtract(spans,cuts):
    result=[list(p) for p in spans]
    for a,b in cuts:
        result=[r for x,y in result for r in ([[x,y]] if b<=x or a>=y else ([[x,a]] if x<a else [])+([[b,y]] if b<y else []))]
    return sorted(result)

def take(spans,quantity):
    selected=[];remaining=quantity
    for a,b in sorted(spans):
        q=min(b-a,remaining)
        if q:selected.append([a,a+q]);remaining-=q
        if not remaining:break
    if remaining or quantity<=0:raise HTTPException(409,'组件剩余数量不足或已被其他工单、退款占用')
    return selected

def amounts(lot,spans):
    return {'quantity_milli':sum(b-a for a,b in spans),**{k:sum(getattr(lot,k)*b//lot.quantity_milli-getattr(lot,k)*a//lot.quantity_milli for a,b in spans) for k in AMOUNTS[1:]}}

def free_spans(db,lot,exclude_holds=(),exclude_refund=None):
    blocked=[]
    for entry in db.scalars(select(PackageEntry).where(PackageEntry.lot_id==lot.id,PackageEntry.purpose.in_(['capture','refund']))):
        reverse=[p for e in db.scalars(select(PackageEntry).where(PackageEntry.original_id==entry.id,PackageEntry.purpose=='reverse')) for p in e.spans]
        blocked+=subtract(entry.spans,reverse)
    for h in db.scalars(select(PackageHold).where(PackageHold.lot_id==lot.id,PackageHold.status=='reserved')):
        if h.id not in exclude_holds:blocked+=h.spans
    # Refund rows are local, but only the issuer can approve them; query their
    # immutable central allocation mirrors through the purchase events is not
    # needed: approved refund claims have central hold entries below.
    for h in db.scalars(select(PackageRefundClaim).where(PackageRefundClaim.lot_id==lot.id,PackageRefundClaim.status=='reserved')):
        if h.refund_id!=exclude_refund:blocked+=h.spans
    return subtract([[0,lot.quantity_milli]],blocked)

def refund_info(user,row):
    data={k:v for k,v in plain(row).items() if k not in {'cash_id','evidence_id'} or user.role in INTERNAL}
    data['selections']=[{k:v for k,v in selection.items() if k!='settlement_cents' or user.role in INTERNAL} for selection in row.selections]
    return data

def purchase_info(db,user,p):
    sid=single_store(db);own=p.issuer_store_id==sid;money=user.role in MONEY
    out={'id':p.id,'version':p.version,'status':p.status,'rule_id':p.rule_id,'member_id':p.member_id,'name':p.contract['name'],'sets':p.sets,'expires_on':p.expires_on.isoformat(),'valid_until':p.valid_until.isoformat(),'digest':p.digest,'lots':[]}
    if own:out.update(case_id=p.case_id,amount_cents=p.amount_cents)
    if own:
        out['refunds']=[refund_info(user,x) for x in db.scalars(select(PackageRefund).where(PackageRefund.purchase_id==p.id))]
        if user.role in {'admin','manager','finance','auditor'}:out.update(cash_id=p.cash_id,account_id=p.account_id)
    for lot in db.scalars(select(PackageLot).where(PackageLot.purchase_id==p.id)):
        available=free_spans(db,lot);data={'id':lot.id,'version':lot.version,'component_key':lot.component_key,'kind':lot.snapshot['kind'],'name':lot.snapshot['name'],'unit':lot.snapshot['unit'],'quantity_milli':lot.quantity_milli,'available_milli':sum(b-a for a,b in available),'mapping':None}
        m=db.scalar(select(PackageMapping).where(PackageMapping.rule_id==p.rule_id,PackageMapping.component_key==lot.component_key,PackageMapping.store_id==sid))
        if m:data['mapping']={'source_id':m.source_id,'kind':m.kind,'name':m.snapshot['name'],'unit':m.snapshot['unit']}
        if money:data.update({k:getattr(lot,k) for k in AMOUNTS[1:] if k!='settlement_cents' or user.role in INTERNAL},available_spans=available)
        out['lots'].append(data)
    return out

def _purchase_customers(db,user,member,sid):
    """The original list's local customer responsibility guard, shared by detail."""
    from .flow_models import Customer
    query=select(Customer).join(GroupIdentityLink,GroupIdentityLink.local_id==Customer.id).where(GroupIdentityLink.store_id==sid,GroupIdentityLink.local_kind=='customer',GroupIdentityLink.identity_id==member.identity_id,Customer.store_id==sid)
    if user.role in {'sales','reception'}:query=query.where(Customer.owner_id==user.id)
    customers=list(db.scalars(query))
    if not customers:raise HTTPException(403,'只能查看当前明确负责的本店客户套餐')
    return customers


def purchases(db,user,member_id):
    with authority(db,user) as sid:
        member=_member(db,member_id,sid,False)
        customers=_purchase_customers(db,user,member,sid)
        return {'customers':[{'id':c.id,'name':c.name} for c in customers],'items':[purchase_info(db,user,p) for p in db.scalars(select(PackagePurchase).where(PackagePurchase.member_id==member_id)) if sid in p.contract['allowed_store_ids'] and (p.issuer_store_id==sid or p.status=='issued')]}


def purchase_detail(db,user,purchase_id):
    with authority(db,user) as sid:
        purchase=_purchase(db,user,purchase_id,sid,False)
        member=_member(db,purchase.member_id,sid,False)
        _purchase_customers(db,user,member,sid)
        if sid not in purchase.contract['allowed_store_ids'] or (purchase.issuer_store_id!=sid and purchase.status!='issued'):
            raise HTTPException(404,'当前授权范围内购买记录不存在')
        detail=purchase_info(db,user,purchase)
        entries=list(db.scalars(select(PackageEntry).join(PackageLot,PackageEntry.lot_id==PackageLot.id).where(
            PackageLot.purchase_id==purchase.id,PackageEntry.store_id==sid,
            PackageEntry.purpose=='capture').order_by(PackageEntry.id.desc()).limit(501)))
        if len(entries)>500:
            raise HTTPException(413,'本店套餐核销记录超过当前上限，请按原业务期间核对')
        fields=['id','store_id','lot_id','case_id','purpose','hold_id','quantity_milli']
        if user.role in MONEY:fields+=['credit_cents','paid_cents']
        if user.role in INTERNAL:fields+=['settlement_cents']
        return {**detail,'capture_entries':[{key:getattr(entry,key) for key in fields} for entry in entries],
            'capture_entry_limit':500}

def create_purchase(db,user,key,v):
    def run(sid):
        rule=_rule(db,v['rule_id'],sid,True)
        if rule.issuer_store_id!=sid:raise HTTPException(403,'请由规则原发行店购买，其他店只办理明确履约')
        member=_member(db,v['member_id'],sid,write=True);row=group._case(db,user,member,v['case_id'],v['case_version'],sid)
        if row.kind not in {'lead','membership','order','repair'} or row.state in flow.TERMINAL or row.data.get('aftercare_ended'):raise HTTPException(409,'购买申请须关联当前有效的真实客户接待或会员业务')
        components=rule.contract['components'];sets=v['sets']
        if any(c['quantity_milli']*sets>1_000_000_000 or any(c[k]*sets>1_000_000_000_000 for k in AMOUNTS[1:]) for c in components) or any(sum(c[k] for c in components)*sets>1_000_000_000_000 for k in AMOUNTS[1:]):raise HTTPException(422,'整批组件数量或金额超过统一办理上限，请拆分明确的购买合同')
        contract={**rule.contract,'rule_id':rule.id,'rule_digest':rule.digest,'sets':v['sets'],'member_id':member.id,'customer_identity_id':member.identity_id,'source_customer_id':row.customer_id}
        p=PackagePurchase(rule_id=rule.id,member_id=member.id,issuer_store_id=sid,case_id=row.id,sets=v['sets'],contract=contract,digest=canonical(contract),amount_cents=v['sets']*sum(c['paid_cents'] for c in contract['components']),expires_on=today()+timedelta(days=contract['validity_days']),valid_until=today()+timedelta(days=7),requested_by=user.id)
        db.add(p);db.flush();db.add(PackagePurchaseEvent(purchase_id=p.id,action='propose',digest=p.digest,actor_id=user.id));flow.ensure_task(db,row,'repair_package_authorize_'+str(p.id),'取得混合套餐本版购买授权','service',assignee=user.id if user.role=='service' else None)
        flow.log_event(db,user,row,'repair_package_propose','冻结混合维修套餐购买合同',detail={'purchase_id':p.id,'digest':p.digest});db.flush();return purchase_info(db,user,p)|{'case_version':row.version}
    return execute(db,user,key,'purchase',v,FRONT,run)

def purchase_action(db,user,key,purchase_id,version,action,v):
    def run(sid):
        p=_purchase(db,user,purchase_id,sid,action!='cancel',True);group._version(p,version)
        member=_member(db,p.member_id,sid,action!='cancel',True);row=group._case(db,user,member,p.case_id,v['case_version'],sid)
        if action in {'authorize','issue'} and (row.state in flow.TERMINAL or row.data.get('aftercare_ended')):raise HTTPException(409,'原业务已结束，请取消未收款合同并从新的有效业务重新申请')
        if action in {'authorize','issue'} and (today()>p.valid_until or today()>p.expires_on):raise HTTPException(409,'购买合同已过期，请取消并重新取得当前客户授权')
        if action=='authorize':
            if p.status!='proposed':raise HTTPException(409,'购买合同当前不能重复授权')
            _proof(db,user,row,v['evidence_id'],True);_rule(db,p.rule_id,sid,True);p.status='authorized';flow.finish_task(db,row,'repair_package_authorize_'+str(p.id),user);flow.ensure_task(db,row,'repair_package_pay_'+str(p.id),'登记套餐购买实际到账','finance')
        elif action=='issue':
            if p.status!='authorized':raise HTTPException(409,'客户确认本版购买后才能实际收款发行')
            _rule(db,p.rule_id,sid,True);_proof(db,user,row,v['evidence_id']);_task(db,user,row,'repair_package_pay_'+str(p.id))
            if v['amount_cents']!=p.amount_cents:raise HTTPException(409,'实际到账须等于已确认合同总价，不支持静默部分发行')
            cash,account=group._cash(db,user,row,v,'in');cash.category='repair_package_purchase';cash.note='混合维修套餐实际购买；'+row.number
            p.cash_id=cash.id;p.account_id=account.id;p.status='issued'
            for c in p.contract['components']:db.add(PackageLot(purchase_id=p.id,component_key=c['key'],quantity_milli=c['quantity_milli']*p.sets,credit_cents=c['credit_cents']*p.sets,paid_cents=c['paid_cents']*p.sets,settlement_cents=c['settlement_cents']*p.sets,snapshot=c))
            flow.finish_task(db,row,'repair_package_pay_'+str(p.id),user)
        else:
            if p.status not in {'proposed','authorized'}:raise HTTPException(409,'实际收款后须走未用原款退款，不可取消购买事实')
            p.status='cancelled'
            for prefix in ('repair_package_authorize_','repair_package_pay_'):flow.finish_task(db,row,prefix+str(p.id),user,'cancelled')
        db.add(PackagePurchaseEvent(purchase_id=p.id,action=action,digest=p.digest,evidence_id=v.get('evidence_id'),actor_id=user.id));flow.log_event(db,user,row,'repair_package_'+action,'办理混合维修套餐购买',detail={'purchase_id':p.id,'digest':p.digest});db.flush();return purchase_info(db,user,p)|{'case_version':row.version}
    return execute(db,user,key,'purchase:'+str(purchase_id)+':'+action,{'version':version,**v},FINANCE if action=='issue' else FRONT|MANAGE,run)

def _task(db,user,row,key):
    from .flow_models import Task
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
    if not task or (user.role!='admin' and task.assignee_id!=user.id):raise HTTPException(403,'请由当前实际待办接手人办理')

def close_unpaid_purchases(db,user,row):
    """Native terminal transition cancels unissued wishes, never posted cash."""
    if row.kind not in {'lead','membership','order','repair'} or not (row.state in flow.TERMINAL or row.data.get('aftercare_ended')):return
    from .flow_models import Task
    pending=db.scalar(select(Task.id).where(Task.case_id==row.id,Task.status=='open',Task.key.like('repair_package_%')))
    if not pending:return
    # This internal hook follows a transition already authorized by the source
    # domain. It grants no user-facing query or unrelated central mutation.
    with authority(db,user,{user.role}) as sid:
        for purchase in db.scalars(select(PackagePurchase).where(PackagePurchase.case_id==row.id,PackagePurchase.issuer_store_id==sid,PackagePurchase.status.in_(['proposed','authorized'])).with_for_update()):
            purchase.status='cancelled';db.add(PackagePurchaseEvent(purchase_id=purchase.id,action='cancel',digest=purchase.digest,actor_id=user.id))
            for prefix in ('repair_package_authorize_','repair_package_pay_'):flow.finish_task(db,row,prefix+str(purchase.id),user,'cancelled')
            flow.log_event(db,user,row,'repair_package_cancel','原业务结束，同事务取消尚未实际收款的套餐合同',detail={'purchase_id':purchase.id,'digest':purchase.digest})
        db.flush()

def case_paid_amount(db,case_id):return db.scalar(select(func.coalesce(func.sum(PackagePaymentLink.amount_cents),0)).where(PackagePaymentLink.case_id==case_id)) or 0
def case_reserved_amount(db,case_id):return db.scalar(select(func.coalesce(func.sum(PackageReservationLink.amount_cents),0)).where(PackageReservationLink.case_id==case_id,PackageReservationLink.status=='reserved')) or 0

def guard_release(db,row):
    if db.scalar(select(PackageReservationLink.id).where(PackageReservationLink.case_id==row.id,PackageReservationLink.status=='reserved')):raise HTTPException(409,'原套餐仍有未核销组件数量，请先核对实际履约并核销后再交车')

def invoice_source_discount(db,row):
    paid=db.scalar(select(func.coalesce(func.sum(PackagePaymentLink.amount_cents-PackagePaymentLink.recognized_cents),0)).where(PackagePaymentLink.case_id==row.id)) or 0
    held=db.scalar(select(func.coalesce(func.sum(PackageReservationLink.amount_cents-PackageReservationLink.recognized_cents),0)).where(PackageReservationLink.case_id==row.id,PackageReservationLink.status=='reserved')) or 0
    return paid+held

def _state(db,hold,status):
    hold.status=status
    link=db.scalar(select(PackageReservationLink).where(PackageReservationLink.hold_id==hold.id))
    if not link:raise HTTPException(409,'本店套餐占额链接缺失')
    link.status=status;db.flush()

def release_quote(db,user,row,quote_id=None):
    with authority(db,user,READ):
        q=select(PackageHold).where(PackageHold.case_id==row.id,PackageHold.store_id==row.store_id,PackageHold.status=='reserved')
        if quote_id:q=q.where(PackageHold.quote_id==quote_id)
        for h in db.scalars(q):
            lot=one(db,PackageLot,h.lot_id);lot.updated_at=utcnow();_state(db,h,'released')
        if quote_id and row.data.get('authorized_quote_id') and row.data['authorized_quote_id']!=quote_id:
            snapshot=db.scalar(select(PackageQuoteSnapshot).where(PackageQuoteSnapshot.case_id==row.id,PackageQuoteSnapshot.quote_id==quote_id))
            if snapshot:
                for key in snapshot.contract['release_ids']:
                    h=one(db,PackageHold,key)
                    if h.quote_id==row.data['authorized_quote_id']:
                        lot=one(db,PackageLot,h.lot_id)
                        if subtract(h.spans,free_spans(db,lot)):raise HTTPException(409,'无法恢复原已授权组件占额，请核对原来源')
                        lot.updated_at=utcnow();_state(db,h,'reserved')

def _entry(db,user,row,lot,purpose,spans,evidence_id,hold=None,original=None,refund=None):
    entry=PackageEntry(store_id=row.store_id,lot_id=lot.id,case_id=row.id,purpose=purpose,spans=spans,**amounts(lot,spans),evidence_id=evidence_id,hold_id=hold.id if hold else None,original_id=original.id if original else None,refund_id=refund.id if refund else None,actor_id=user.id)
    db.add(entry);db.flush()
    if purpose!='refund':
        sign=1 if purpose=='capture' else -1
        db.add(PackagePaymentLink(case_id=row.id,entry_id=entry.id,purpose=purpose,amount_cents=sign*entry.credit_cents,recognized_cents=sign*entry.paid_cents,actor_id=user.id))
        if entry.settlement_cents:db.add_all([PackageSettlement(entry_id=entry.id,side=side,amount_cents=delta*sign*entry.settlement_cents,actor_id=user.id) for side,delta in [('center',-1),('store',1)]])
    lot.updated_at=utcnow();db.flush();return entry

def refund_request(db,user,key,purchase_id,version,v):
    def run(sid):
        p=_purchase(db,user,purchase_id,sid,False,True);group._version(p,version)
        if p.status!='issued' or p.contract['refund_policy']=='none' or (p.contract['refund_policy']=='unused_before_expiry' and today()>p.expires_on):raise HTTPException(409,'本批次尚未发行或原冻结规则不允许当前未用退款')
        member=_member(db,p.member_id,sid,False,True);row=group._case(db,user,member,p.case_id,v['case_version'],sid);_proof(db,user,row,v['evidence_id'])
        chosen=[]
        if len({s['lot_id'] for s in v['selections']})!=len(v['selections']):raise HTTPException(422,'同一组件请合并申请数量')
        for s in sorted(v['selections'],key=lambda s:s['lot_id']):
            lot=one(db,PackageLot,s['lot_id'])
            if lot.purchase_id!=p.id:raise HTTPException(404,'原购买组件不存在')
            _quantity(lot,s['quantity_milli']);spans=take(free_spans(db,lot),s['quantity_milli']);chosen.append({'lot_id':lot.id,'spans':spans,**amounts(lot,spans)})
        refund=PackageRefund(purchase_id=p.id,case_id=row.id,selections=chosen,amount_cents=sum(s['paid_cents'] for s in chosen),requested_by=user.id,evidence_id=v['evidence_id'],reason=v['reason'])
        db.add(refund);db.flush();p.updated_at=utcnow();flow.ensure_task(db,row,'repair_package_refund_review_'+str(refund.id),'复核原套餐未用组件退款','manager');flow.log_event(db,user,row,'repair_package_refund_request','申请原套餐未用退款',detail={'refund_id':refund.id,'purchase_id':p.id});db.flush();return refund_info(user,refund)|{'case_version':row.version,'purchase_version':p.version}
    return execute(db,user,key,'refund_request:'+str(purchase_id),{'version':version,**v},FRONT|FINANCE,run)

def refund_action(db,user,key,refund_id,version,action,v):
    def run(sid):
        refund=one(db,PackageRefund,refund_id);group._version(refund,version);p=_purchase(db,user,refund.purchase_id,sid,False,True);member=_member(db,p.member_id,sid,False,True);row=group._case(db,user,member,p.case_id,v['case_version'],sid)
        if refund.status not in {'requested','approved'}:raise HTTPException(409,'退款已结束')
        review='repair_package_refund_review_'+str(refund.id);pay='repair_package_refund_pay_'+str(refund.id)
        if action=='approve':
            if refund.status!='requested':raise HTTPException(409,'退款已批准')
            if refund.requested_by==user.id:raise HTTPException(403,'未用退款申请和批准必须独立')
            if p.contract['refund_policy']=='unused_before_expiry' and today()>p.expires_on:raise HTTPException(409,'原规则不允许过期后新批准退款')
            for s in refund.selections:
                lot=one(db,PackageLot,s['lot_id']);lot.updated_at=utcnow()
                if subtract(s['spans'],free_spans(db,lot)):raise HTTPException(409,'申请组件已使用或占用，请撤销后核对原剩余量')
                db.add(PackageRefundClaim(store_id=sid,refund_id=refund.id,lot_id=lot.id,spans=s['spans']))
            refund.status='approved';refund.approved_by=user.id;flow.finish_task(db,row,review,user);flow.ensure_task(db,row,pay,'登记原账户实际套餐退款' if refund.amount_cents else '确认零对价原组件退回注销','finance')
        elif action in {'cancel','reject'}:
            if action=='cancel' and user.id!=refund.requested_by and user.role not in MANAGE:raise HTTPException(403,'仅申请人或本店主管可撤销')
            for claim in db.scalars(select(PackageRefundClaim).where(PackageRefundClaim.refund_id==refund.id)):
                claim.status='released';one(db,PackageLot,claim.lot_id).updated_at=utcnow()
            refund.status='cancelled' if action=='cancel' else 'rejected';flow.finish_task(db,row,review,user,'cancelled');flow.finish_task(db,row,pay,user,'cancelled')
        else:
            if refund.status!='approved':raise HTTPException(409,'请先独立批准原退款')
            _task(db,user,row,pay);_proof(db,user,row,v['evidence_id'])
            if v['amount_cents']!=refund.amount_cents:raise HTTPException(409,'实际退款须等于原组件分摊，不得手工改总额')
            claims=list(db.scalars(select(PackageRefundClaim).where(PackageRefundClaim.refund_id==refund.id)))
            if len(claims)!=len(refund.selections) or any(c.status!='reserved' for c in claims):raise HTTPException(409,'原退款占额缺失')
            if refund.amount_cents:
                if not v.get('account_id') or not v.get('reference'):raise HTTPException(422,'正金额原款退款须明确原账户和实际退款流水')
                cash,_=group._cash(db,user,row,v,'out',p);cash.category='repair_package_refund';cash.note='混合维修套餐未用原款退款；'+row.number;refund.cash_id=cash.id
            refund.status='executed'
            for s in refund.selections:
                lot=one(db,PackageLot,s['lot_id']);_entry(db,user,row,lot,'refund',s['spans'],v['evidence_id'],refund=refund)
            for claim in claims:claim.status='applied'
            flow.finish_task(db,row,pay,user)
        p.updated_at=utcnow();flow.log_event(db,user,row,'repair_package_refund_'+action,'办理原套餐未用退款',detail={'refund_id':refund.id,'purchase_id':p.id});db.flush();return refund_info(user,refund)|{'case_version':row.version,'purchase_version':p.version}
    roles=MANAGE if action in {'approve','reject'} else FINANCE if action=='pay' else FRONT|MANAGE
    return execute(db,user,key,'refund:'+str(refund_id)+':'+action,{'version':version,**v},roles,run)

def _quantity(lot,qty):
    if qty<=0 or (lot.snapshot['kind']=='work' and lot.snapshot['unit']=='job' and qty%1000):raise HTTPException(422,'组件用量无效；按次作业须为完整次数')

def _lot_for_case(db,user,row,key,version=None):
    lot=one(db,PackageLot,key)
    if version is not None:group._version(lot,version)
    p=_purchase(db,user,lot.purchase_id,row.store_id)
    member=_member(db,p.member_id,row.store_id,write=True)
    linked=db.scalar(select(GroupIdentityLink.id).where(GroupIdentityLink.store_id==row.store_id,GroupIdentityLink.local_kind=='customer',GroupIdentityLink.local_id==row.customer_id,GroupIdentityLink.identity_id==member.identity_id))
    if not linked:raise HTTPException(409,'当前维修客户与原套餐身份不一致')
    if p.status!='issued' or today()>p.expires_on:raise HTTPException(409,'原套餐未实际收款发行或已经过期')
    mapping=db.scalar(select(PackageMapping).where(PackageMapping.rule_id==p.rule_id,PackageMapping.component_key==lot.component_key,PackageMapping.store_id==row.store_id))
    if not mapping:raise HTTPException(409,'本店尚未明确核对原套餐组件物料或作业映射')
    obj=one(db,WorkItem if mapping.kind=='work' else Item,mapping.source_id)
    if not obj.active or (obj.billing_unit if mapping.kind=='work' else obj.unit)!=lot.snapshot['unit']:raise HTTPException(409,'原本店组件已停用或计量单位变化')
    lot.updated_at=utcnow();db.flush();return lot,p,mapping

def prepare_quote(db,user,row,v,old):
    """Called before quote/member pricing; owns explicit component allocations only."""
    selections=[(i,l) for i,l in enumerate(v.get('lines',[])) if l.get('package_lot_id')]
    old_holds=[]
    with authority(db,user,FRONT|MANAGE):
        if old:old_holds=list(db.scalars(select(PackageHold).where(PackageHold.case_id==row.id,PackageHold.quote_id==old.id,PackageHold.store_id==row.store_id,PackageHold.status=='reserved')))
        if not selections and not old_holds:return None
        if row.kind!='repair' or row.flow_version not in {3,4}:raise HTTPException(409,'此工单版本不支持组件合同')
        if v.get('purpose')=='stop':return prepare_stop(db,user,row,v,old,old_holds)
        old_keys={h.line_key:h for h in old_holds};prepared=[];allocated={}
        for index,line in selections:
            if line.get('charge_scope')=='original_liability':raise HTTPException(409,'原责任返修不得核销客户已购买套餐')
            lot,p,mapping=_lot_for_case(db,user,row,line['package_lot_id'],line['package_lot_version']);qty=line['quantity_milli'];_quantity(lot,qty)
            if mapping.kind!=line['kind'] or mapping.source_id!=line['source_id']:raise HTTPException(409,'报价行不是本店已核实的原组件')
            previous=old_keys.get(line.get('line_key'))
            if previous and (previous.lot_id!=lot.id or qty!=previous.quantity_milli):raise HTTPException(409,'已授权套餐组件不能改来源或加减量，请独立新行或实际停工')
            if previous:spans=previous.spans
            else:spans=take(subtract(free_spans(db,lot,tuple(h.id for h in old_holds)),allocated.get(lot.id,[])),qty)
            allocated.setdefault(lot.id,[]).extend(spans);value=amounts(lot,spans)
            expected=(value['credit_cents']*1000+qty-1)//qty
            if line['unit_price_cents']!=expected:raise HTTPException(409,'组件报价须使用原合同基价，不能手工改价')
            prepared.append({'index':index,'lot_id':lot.id,'lot_version':lot.version,'rule_id':p.rule_id,'component_key':lot.component_key,'spans':spans,**value})
        if old_holds and {h.line_key for h in old_holds}!={v['lines'][p['index']].get('line_key') for p in prepared if v['lines'][p['index']].get('line_key') in old_keys}:raise HTTPException(409,'新报价必须保留已授权组件；减少请走实际取消或停工')
        return {'lines':prepared,'release_ids':[h.id for h in old_holds]}

def quote_basis(prepared,specs,components):
    if not prepared:return
    for p in prepared['lines']:
        i=p['index'];spec=specs[i];spec['amount_cents']=p['credit_cents']
        components[i].update(basis_cents=p['credit_cents'],carry_cents=0,price_source='package_contract',contract_rule_id=p['rule_id'],contract_component_id=p['component_key'])

def freeze_quote(db,user,row,quote,lines,prepared):
    if not prepared:return
    with authority(db,user,FRONT|MANAGE):
        db.add(PackageQuoteSnapshot(case_id=row.id,quote_id=quote.id,contract=prepared,digest=canonical(prepared),actor_id=user.id))
        for key in prepared['release_ids']:_state(db,one(db,PackageHold,key),'released')
        for p in prepared['lines']:
            line=lines[p['index']];lot=one(db,PackageLot,p['lot_id'])
            if line.amount_cents!=p['credit_cents'] or (line.quantity_milli!=p['quantity_milli'] and not (prepared.get('stop') and line.quantity_milli>=p['quantity_milli'])):raise HTTPException(409,'套餐组件金额被重复折扣或改量')
            if subtract(p['spans'],free_spans(db,lot)):raise HTTPException(409,'组件已被竞争办理占用')
            data={k:p[k] for k in AMOUNTS};h=PackageHold(store_id=row.store_id,lot_id=lot.id,case_id=row.id,quote_id=quote.id,line_id=line.id,line_key=line.line_key,spans=p['spans'],**data,digest=canonical({'quote_digest':quote.digest,'lot_id':lot.id,'spans':p['spans'],**data}))
            db.add(h);db.flush();db.add(PackageReservationLink(hold_id=h.id,case_id=row.id,quote_id=quote.id,amount_cents=h.credit_cents,recognized_cents=h.paid_cents));lot.updated_at=utcnow();db.flush()

def prepare_stop(db,user,row,v,old,holds):
    # The repair quote adapter builds explicit retained component quantities;
    # its resulting price must equal this frozen contract, never a pooled fee.
    values=v.get('package_retained')
    if values is None:raise HTTPException(422,'套餐停工必须逐组件确认实际保留量，不能只填汇总保留费')
    selected={x['line_key']:x['quantity_milli'] for x in values}
    if len(selected)!=len(values) or set(selected)!={h.line_key for h in holds}:raise HTTPException(422,'请逐一明确全部原套餐组件保留数量')
    from .repair_service import _stock_net
    prepared=[]
    for h in holds:
        qty=selected[h.line_key];lot=one(db,PackageLot,h.lot_id)
        if qty<0 or qty>h.quantity_milli:raise HTTPException(422,'保留数量超过原授权量')
        if lot.snapshot['kind']=='part' and qty!=_stock_net(db,row,h.line_key)[0]:raise HTTPException(409,'停工套餐配件保留量必须等于本行实际净领料')
        if qty:
            _quantity(lot,qty);spans=take(h.spans,qty);p=one(db,PackagePurchase,lot.purchase_id)
            prepared.append({'line_key':h.line_key,'lot_id':lot.id,'lot_version':lot.version,'rule_id':p.rule_id,'component_key':lot.component_key,'spans':spans,**amounts(lot,spans)})
    return {'lines':prepared,'release_ids':[h.id for h in holds],'stop':True,'retained':selected}

def stop_specs(prepared,specs,retained,distribute):
    if not prepared:return
    covered=prepared['retained'];by_key={p['line_key']:p for p in prepared['lines']};own=sum(p['credit_cents'] for p in prepared['lines'])
    rest=retained-own;ordinary=[s for s in specs if s['line_key'] not in covered]
    if rest<0 or rest>sum(s['_original_amount'] for s in ordinary):raise HTTPException(409,'套餐停工总保留费必须包含逐组件原C分摊，其余不得超过已授权自费')
    allocation=iter(distribute(rest,[s['_original_amount'] for s in ordinary]))
    for i,s in enumerate(specs):
        if s['line_key'] in covered:
            p=by_key.get(s['line_key']);s['amount_cents']=p['credit_cents'] if p else 0
            if p:p['index']=i
        else:s['amount_cents']=next(allocation)
        s.pop('_original_amount',None);s['discount_cents']=(s['quantity_milli']*s['unit_price_cents']+500)//1000-s['amount_cents']

def quote_info(db,user,row,quote_id):
    snapshot=db.scalar(select(PackageQuoteSnapshot).where(PackageQuoteSnapshot.case_id==row.id,PackageQuoteSnapshot.quote_id==quote_id))
    if not snapshot:return None
    contract=snapshot.contract
    return {'digest':snapshot.digest,'stop':bool(contract.get('stop')),'lines':[{'index':p['index'],'lot_id':p['lot_id'],'component_key':p['component_key'],'quantity_milli':p['quantity_milli'],**({k:p[k] for k in AMOUNTS[1:] if k!='settlement_cents' or user.role in INTERNAL} if user.role in MONEY else {})} for p in contract['lines']],'retained':contract.get('retained')}

def excluded_line_keys(db,row,quote_id):
    snapshot=db.scalar(select(PackageQuoteSnapshot).where(PackageQuoteSnapshot.case_id==row.id,PackageQuoteSnapshot.quote_id==quote_id))
    return {p['line_key'] for p in snapshot.contract['lines']} if snapshot else set()

def guard_authorization(db,user,row,quote_id):
    with authority(db,user,FRONT|MANAGE):
        for h in db.scalars(select(PackageHold).where(PackageHold.case_id==row.id,PackageHold.store_id==row.store_id,PackageHold.quote_id==quote_id)):
            if h.status!='reserved':raise HTTPException(409,'本版套餐组件占额已经失效')
            _lot_for_case(db,user,row,h.lot_id)

def capture(db,user,key,case_id,version,v):
    def run(sid):
        from . import repair_service as repair
        row=repair.get_order(db,user,case_id);group._version(row,version);row.updated_at=utcnow();_proof(db,user,row,v['evidence_id'])
        due=repair.customer_due(db,row,False)
        from .aftercare_service import guard_source_action
        guard_source_action(db,user,row,'package_capture')
        quote=repair._authorized(db,row);holds=list(db.scalars(select(PackageHold).where(PackageHold.case_id==row.id,PackageHold.store_id==sid,PackageHold.quote_id==quote.id,PackageHold.status=='reserved')))
        if not holds:raise HTTPException(409,'当前报价没有尚未核销的组件占额')
        own=sum(h.credit_cents for h in holds);other=repair._credits(db,row)[1]-own
        if own>max(0,due-other):raise HTTPException(409,'本单客户容量已被其他收款或权益占用')
        for h in holds:
            # Current quote was authorized while valid. Staff/master/member
            # changes after real work cannot destroy its already reserved claim.
            from .repair_models import RepairAuthorization
            lot=one(db,PackageLot,h.lot_id);p=one(db,PackagePurchase,lot.purchase_id);_member(db,p.member_id,sid,False,True)
            approved=db.scalar(select(RepairAuthorization).where(RepairAuthorization.quote_id==quote.id))
            authorized_on=((approved.created_at.replace(tzinfo=timezone.utc) if approved.created_at.tzinfo is None else approved.created_at).astimezone(ZoneInfo(settings.timezone)).date()) if approved else None
            if not authorized_on or authorized_on>p.expires_on:raise HTTPException(409,'原套餐核销缺有效期内本版客户授权')
            if lot.snapshot['kind']=='part' and repair._stock_net(db,row,h.line_key)[0]!=h.quantity_milli:raise HTTPException(409,'组件核销量必须等于真实净领料')
            if not row.data.get('finish_result'):raise HTTPException(409,'尚无实际施工完成事实')
            _entry(db,user,row,lot,'capture',h.spans,v['evidence_id'],hold=h);_state(db,h,'captured')
        repair.sync_after_member(db,user,row,v['evidence_id'])
        from .invoice_service import sync_source
        sync_source(db,user,row);flow.log_event(db,user,row,'repair_package_capture','按当前授权实际履约核销组件',detail={'quote_id':quote.id});db.flush();return {'case_id':row.id,'case_version':row.version,'credit_cents':own}
    return execute(db,user,key,'capture:'+str(case_id),{'version':version,**v},FINANCE,run)

def analytics_rows(db,user):
    if user.role not in {'admin','manager','finance','auditor'}:raise HTTPException(403,'套餐金额统计需要经营查询权限')
    ids=tuple(db.info.get('store_scope',()))
    # Only immutable local projections; never inspect arbitrary central wallets.
    links=list(db.scalars(select(PackagePaymentLink).where(PackagePaymentLink.store_id.in_(ids)).order_by(PackagePaymentLink.id).limit(25001)))
    if len(links)>25000:raise HTTPException(413,'套餐履约来源超过当前统计上限')
    settlements=list(db.scalars(select(PackageSettlement).where(PackageSettlement.store_id.in_(ids))))
    internal={s.entry_id:s.amount_cents for s in settlements if s.side=='store'}
    result={'entries':[{'id':l.id,'entry_id':l.entry_id,'store_id':l.store_id,'case_id':l.case_id,'credit_cents':l.amount_cents,'recognized_cents':l.recognized_cents,'external_discount_cents':l.amount_cents-l.recognized_cents,'group_discount_cents':internal.get(l.entry_id,0)-l.recognized_cents,'service_discount_cents':l.amount_cents-internal.get(l.entry_id,0),'purpose':l.purpose,'occurred_at':l.occurred_at.isoformat()} for l in links],'settlements':[plain(s) for s in settlements],'purchases':[],'refunds':[],'lots':[]}
    from .models import CashEntry
    old=db.info.get('_group_authority');db.info['_group_authority']=('package_report',ids)
    try:
        for p in db.scalars(select(PackagePurchase).where(PackagePurchase.issuer_store_id.in_(ids),PackagePurchase.status=='issued')):
            actual=db.scalar(select(CashEntry).where(CashEntry.id==p.cash_id,CashEntry.store_id==p.issuer_store_id))
            result['purchases'].append({'id':p.id,'store_id':p.issuer_store_id,'case_id':p.case_id,'cash_id':p.cash_id,'amount_cents':p.amount_cents,'name':p.contract['name'],'business_date':actual.business_date.isoformat(),'expires_on':p.expires_on.isoformat()})
            for lot in db.scalars(select(PackageLot).where(PackageLot.purchase_id==p.id)):
                available=amounts(lot,free_spans(db,lot));held=[h for h in db.scalars(select(PackageHold).where(PackageHold.lot_id==lot.id,PackageHold.status=='reserved'))]
                claims=[amounts(lot,c.spans) for c in db.scalars(select(PackageRefundClaim).where(PackageRefundClaim.lot_id==lot.id,PackageRefundClaim.status=='reserved'))]
                result['lots'].append({'id':lot.id,'purchase_id':p.id,'store_id':p.issuer_store_id,'case_id':p.case_id,'name':lot.snapshot['name'],'kind':lot.snapshot['kind'],'unit':lot.snapshot['unit'],'initial_quantity_milli':lot.quantity_milli,'initial_paid_cents':lot.paid_cents,'available_quantity_milli':available['quantity_milli'],'available_paid_cents':available['paid_cents'],'reserved_quantity_milli':sum(h.quantity_milli for h in held),'reserved_paid_cents':sum(h.paid_cents for h in held),'refund_reserved_quantity_milli':sum(c['quantity_milli'] for c in claims),'refund_reserved_paid_cents':sum(c['paid_cents'] for c in claims),'expires_on':p.expires_on.isoformat(),'expired':today()>p.expires_on})
        for refund in db.scalars(select(PackageRefund).where(PackageRefund.store_id.in_(ids),PackageRefund.status=='executed')):
            actual=db.scalar(select(CashEntry).where(CashEntry.id==refund.cash_id)) if refund.cash_id else None
            result['refunds'].append({'id':refund.id,'purchase_id':refund.purchase_id,'store_id':refund.store_id,'case_id':refund.case_id,'cash_id':refund.cash_id,'amount_cents':refund.amount_cents,'business_date':actual.business_date.isoformat() if actual else refund.updated_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).date().isoformat()})
    finally:
        if old is None:db.info.pop('_group_authority',None)
        else:db.info['_group_authority']=old
    return result
