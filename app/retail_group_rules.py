"""Explicitly approved, issuance-time retail eligibility; no old batch backfill."""
import uuid
from fastapi import HTTPException
from sqlalchemy import select,func
from .db import today,utcnow
from .models import Store
from .flow_models import Case,Item,Task
from .master_models import WorkItem
from .tenancy import role_for_store,single_store
from .group_benefits_models import BenefitWallet,BenefitEntry
from . import flow_engine as flow,group_service as group,group_benefits_service as benefits
from . import retail_group_service as svc
from .retail_group_models import RetailGroupEligibility as Eligibility,RetailGroupScope as Scope,RetailGroupDecision as Decision,RetailGroupWallet as WalletBinding

ROLES={'admin','manager'}
READ=ROLES|{'finance','auditor'}
SPEC=dict(label='精品权益商品规则',module='membership',create_roles=[],fields=[],initial='draft',actions=[])


def can_read_case(db,user,row):return not getattr(user,'_aggregate_scope',False) and user.role in READ


def _case(db,user,key):
    row=db.scalar(select(Case).where(Case.id==key,Case.kind=='retail_group_rule',Case.flow_version==2))
    if row is None or not can_read_case(db,user,row):raise HTTPException(404,'本店精品权益规则申请不存在或未获权')
    return row


def _rule(db,rule_id):
    rule=benefits._rule(db,rule_id)
    if rule.issuer_store_id!=single_store(db) or rule.kind not in {'bonus','coupon','package'}:
        raise HTTPException(409,'只能为本店发行的赠金、券或套餐配置明确商品用途')
    return rule


def _unissued(db,rule):
    if db.scalar(select(BenefitWallet.id).where(BenefitWallet.rule_id==rule.id)):
        raise HTTPException(409,'该规则已经发行权益，不能补授或修改商品适用范围；请创建新规则版本')


def _scope(db,user,rule,values):
    sid=values['store_id']
    if sid not in rule.allowed_store_ids or role_for_store(db,user,sid) not in ROLES or not db.scalar(select(Store.id).where(Store.id==sid,Store.active.is_(True))):
        raise HTTPException(403,'申请与批准人须在每家适用门店具有主管岗位；集团只读汇总不是商品规则授权')
    # Only explicit, independently authorized typed master identities are read.
    # No other-store case, customer, price, cash or file enters this scope.
    previous=db.info.get('store_scope')
    try:
        db.info['store_scope']=(sid,)
        with db.no_autoflush:
            item=db.scalar(select(Item).where(Item.id==values['item_id'],Item.active.is_(True)))
            if not item:raise HTTPException(422,'适用商品须是指定门店的启用物资')
            work=None
            if values['component']=='installation':
                work=db.scalar(select(WorkItem).where(WorkItem.id==values['work_item_id'],WorkItem.active.is_(True)))
                if not work:raise HTTPException(422,'安装范围须指定同店启用作业项目')
            elif values['component']!='goods' or values.get('work_item_id') is not None:
                raise HTTPException(422,'商品范围不能借用任意安装项目')
            return dict(store_id=sid,item_id=item.id,component=values['component'],work_item_id=work.id if work else None,
                sku=item.sku,name=item.name,unit=item.unit,work_code=work.code if work else '')
    finally:
        if previous is None:db.info.pop('store_scope',None)
        else:db.info['store_scope']=previous


def create(db,user,request_id,rule_id):
    def operation(sid):
        with svc.authority(db,user,ROLES):
            rule=_rule(db,rule_id);_unissued(db,rule)
            row=Case(kind='retail_group_rule',flow_version=2,number='HKRG'+uuid.uuid4().hex[:18].upper(),state='draft',title='精品权益商品规则 · '+rule.name,
                customer_id=None,owner_id=user.id,created_by=user.id,business_date=today(),due_date=today(),amount_cents=0,data={'rule_id':rule.id})
            db.add(row);db.flush()
            from .business_entity_service import freeze_case_entity
            freeze_case_entity(db,user,row)
            flow.ensure_task(db,row,'retail_rule_submit','明确商品用途、原退和有效期约定','manager',assignee=user.id)
            flow.log_event(db,user,row,'retail_rule_create','建立精品权益商品适用申请',detail={'rule_id':rule.id})
            return {'case_id':row.id,'version':row.version}
    return group._execute(db,user,request_id,'retail_rule_create',{'rule_id':rule_id},operation,ROLES)


def command(db,user,case_id,request_id,version,action,values):
    def operation(sid):
        with svc.authority(db,user,ROLES):
            row=_case(db,user,case_id);group._version(row,version);row.updated_at=utcnow()
            rule=_rule(db,row.data['rule_id'])
            if action=='submit':
                if row.state!='draft':raise HTTPException(409,'申请已提交或结束')
                if row.created_by!=user.id:raise HTTPException(403,'请由原申请人提交已明确的公司规则')
                if any(values.get(k)!=v for k,v in svc.MODES.items()):raise HTTPException(422,'须明确批准部分退回累计原单位、保留原有效期、待恢复负债不自动清零；没有默认公司规则')
                _unissued(db,rule);svc._evidence(db,user,row,values['evidence_id'])
                scopes=values['scopes']
                if not scopes or len(scopes)>200:raise HTTPException(422,'须指定 1 至 200 项实际商品或安装用途')
                prepared=[_scope(db,user,rule,v) for v in scopes]
                if len({(v['store_id'],v['item_id'],v['component']) for v in prepared})!=len(prepared):raise HTTPException(422,'同店商品用途请合并，不能重复配置')
                eligibility=Eligibility(rule_id=rule.id,issuer_store_id=sid,case_id=row.id,requested_by=user.id,evidence_id=values['evidence_id'],**svc.MODES)
                db.add(eligibility);db.flush();db.add_all([Scope(eligibility_id=eligibility.id,**v) for v in prepared])
                row.state='approval';flow.finish_task(db,row,'retail_rule_submit',user)
                candidates=[u for u in flow.eligible_users(db,'manager',sid) if u.id!=user.id and all(role_for_store(db,u,v['store_id']) in ROLES for v in prepared)]
                if not candidates:raise HTTPException(409,'须先配置另一名在全部适用门店获权的主管，申请与批准不能由同一人完成')
                flow.ensure_task(db,row,'retail_rule_approve','独立批准商品用途及部分退回规则','manager',assignee=candidates[0].id)
            elif action=='cancel' and row.state=='draft':
                if row.created_by!=user.id:raise HTTPException(403,'只有申请人可取消尚未提交的申请')
                row.state='cancelled';row.completed_date=today();flow.finish_task(db,row,'retail_rule_submit',user,'cancelled')
            elif action in {'approve','reject','cancel'}:
                if row.state!='approval':raise HTTPException(409,'申请不在独立审批阶段')
                eligibility=db.scalar(select(Eligibility).where(Eligibility.case_id==row.id))
                if not eligibility:raise HTTPException(409,'规则申请原始范围缺失')
                if action!='cancel':
                    if eligibility.requested_by==user.id:raise HTTPException(403,'申请人与批准人必须不同，管理员也不能自批')
                    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key=='retail_rule_approve',Task.status=='open'))
                    if not task or task.assignee_id!=user.id:raise HTTPException(403,'请由当前独立审批待办的主管办理')
                elif eligibility.requested_by!=user.id:raise HTTPException(403,'只有申请人可撤销未获批规则')
                evidence_id=values.get('evidence_id') or (eligibility.evidence_id if action=='cancel' else None)
                svc._evidence(db,user,row,evidence_id)
                if action=='approve':
                    _unissued(db,rule)
                    for scope in svc.rows(db,Scope,eligibility_id=eligibility.id):
                        current=_scope(db,user,rule,{'store_id':scope.store_id,'item_id':scope.item_id,'component':scope.component,'work_item_id':scope.work_item_id})
                        if any(current[k]!=getattr(scope,k) for k in ('sku','name','unit','work_code')):raise HTTPException(409,'适用商品或作业在审批间变化，请取消后使用新规则重新申请')
                db.add(Decision(eligibility_id=eligibility.id,approved=action=='approve',actor_id=user.id,evidence_id=evidence_id,reason=values['reason']))
                row.state={'approve':'completed','reject':'rejected','cancel':'cancelled'}[action];row.completed_date=today();flow.finish_task(db,row,'retail_rule_approve',user)
            else:raise HTTPException(404,'精品权益规则动作不存在')
            flow.log_event(db,user,row,'retail_rule_'+action,{'submit':'提交明确商品规则','approve':'独立批准商品规则','reject':'拒绝商品规则','cancel':'取消未批准商品规则'}[action],detail=values)
            db.flush();return {'case_id':row.id,'version':row.version,'state':row.state}
    return group._execute(db,user,request_id,'retail_rule_'+action,{'case_id':case_id,'version':version,'values':values},operation,ROLES)


def guard_issuance(db,user,rule):
    """Before native benefit wallet creation. Returns a same-transaction permit.

    A rule without a retail annex retains its original service-only semantics.
    The new wallet cannot later acquire retail eligibility by inspecting names.
    """
    with svc.authority(db,user,group.IDENTITY_ROLES|{'finance'}):
        proposal=db.scalar(select(Eligibility).where(Eligibility.rule_id==rule.id))
        if not proposal:return None
        if proposal.issuer_store_id!=single_store(db):raise HTTPException(403,'只能由规则原发行店发行商品权益')
        row=db.scalar(select(Case).where(Case.id==proposal.case_id,Case.kind=='retail_group_rule',Case.flow_version==2))
        if row is None:raise HTTPException(409,'本店原商品规则申请缺失')
        decision=db.scalar(select(Decision).where(Decision.eligibility_id==proposal.id,Decision.approved.is_(True)))
        if not decision:raise HTTPException(409,'商品用途及部分退回规则尚未独立批准，不能发行本版本')
        # Issuing does not grant foreign-store master access. Validate current
        # issuer-store identities here; use at every other store must match its
        # own frozen retail line against the approved scope in that store.
        for scope in svc.rows(db,Scope,eligibility_id=proposal.id,store_id=single_store(db)):
            item=db.scalar(select(Item).where(Item.id==scope.item_id,Item.active.is_(True)))
            if not item or item.unit!=scope.unit:raise HTTPException(409,'本店批准商品已停用或单位已改变，不能按旧商品范围新发行')
            if scope.component=='installation':
                work=db.scalar(select(WorkItem).where(WorkItem.id==scope.work_item_id,WorkItem.active.is_(True)))
                if not work or work.code!=scope.work_code:raise HTTPException(409,'本店批准安装项目已停用或编码已改变，不能按旧用途新发行')
        row.updated_at=utcnow();db.flush() # CAS with rule approval / concurrent issuance.
        wallet_cursor=db.scalar(select(func.coalesce(func.max(BenefitWallet.id),0)))
        entry_cursor=db.scalar(select(func.coalesce(func.max(BenefitEntry.id),0)))
        token=object();db.info.setdefault('_retail_group_issue_permits',{})[token]=(db.get_transaction(),user.id,proposal,decision,wallet_cursor,entry_cursor)
        return token


def attach_issuance(db,user,wallet,origin,permit):
    """After native wallet + original entry flush. Never called for old wallets."""
    if permit is None:return
    with svc.authority(db,user,group.IDENTITY_ROLES|{'finance'}):
        saved=db.info.get('_retail_group_issue_permits',{}).pop(permit,None)
        if not saved or saved[0] is not db.get_transaction() or saved[1]!=user.id:raise HTTPException(409,'商品权益发行授权须来自当前同一事务')
        _,_,proposal,decision,wallet_cursor,entry_cursor=saved
        if wallet.rule_id!=proposal.rule_id or origin.wallet_id!=wallet.id or wallet.issuer_store_id!=single_store(db) or origin.purpose not in {'purchase','grant','exchange_in'} or origin.actor_id!=user.id:
            raise HTTPException(409,'新发行原批次与已批准商品规则不符')
        if wallet.source_case_id!=origin.case_id or wallet.initial_units!=origin.units or origin.occurred_at<decision.occurred_at or wallet.id<=wallet_cursor or origin.id<=entry_cursor:
            raise HTTPException(409,'原发行事实与冻结商品用途不一致')
        db.add(WalletBinding(wallet_id=wallet.id,eligibility_id=proposal.id,decision_id=decision.id,origin_id=origin.id,actor_id=user.id));db.flush()


def describe(db,user,case_id):
    with svc.authority(db,user,READ):
        row=_case(db,user,case_id);rule=_rule(db,row.data['rule_id'])
        proposal=db.scalar(select(Eligibility).where(Eligibility.case_id==row.id));decision=db.scalar(select(Decision).where(Decision.eligibility_id==proposal.id)) if proposal else None
        task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key=='retail_rule_approve',Task.status=='open'))
        actions=[]
        if user.role in ROLES:
            if row.state=='draft' and row.created_by==user.id:actions=['submit','cancel']
            elif row.state=='approval':
                if proposal.requested_by==user.id:actions=['cancel']
                elif task and task.assignee_id==user.id:actions=['approve','reject']
        return {'id':row.id,'number':row.number,'version':row.version,'state':row.state,'actions':actions,
            'rule':benefits.rule_info(rule,user.role in {'admin','manager','finance','auditor'}),
            'modes':{k:getattr(proposal,k) for k in svc.MODES} if proposal else None,
            'scopes':[{'store_id':s.store_id,'item_id':s.item_id,'component':s.component,'work_item_id':s.work_item_id,'sku':s.sku,'name':s.name,'unit':s.unit,'work_code':s.work_code} for s in svc.rows(db,Scope,eligibility_id=proposal.id)] if proposal else [],
            'decision':{'approved':decision.approved,'reason':decision.reason,'actor_id':decision.actor_id,'occurred_at':decision.occurred_at.isoformat()} if decision else None}


def list_rules(db,user):
    with svc.authority(db,user,READ):
        rows=list(db.scalars(select(Case).where(Case.kind=='retail_group_rule',Case.flow_version==2).order_by(Case.id.desc()).limit(201)))
        if len(rows)>200:raise HTTPException(413,'本店规则申请超过当前查看上限，请按原业务清单查询')
        current=[{'id':r.id,'name':r.name,'kind':r.kind,'rule_version':r.rule_version} for r in db.scalars(select(benefits.BenefitRule).where(benefits.BenefitRule.issuer_store_id==single_store(db),benefits.BenefitRule.kind.in_(['bonus','coupon','package'])).order_by(benefits.BenefitRule.id.desc()).limit(500))]
        return {'can_create':user.role in ROLES,'rules':current,'items':[{'id':r.id,'number':r.number,'title':r.title,'state':r.state} for r in rows]}


def item_catalogue(db,user,store_id):
    with svc.authority(db,user,ROLES):
        if role_for_store(db,user,store_id) not in ROLES:raise HTTPException(403,'没有指定门店的商品规则管理岗位')
        previous=db.info.get('store_scope')
        try:
            db.info['store_scope']=(store_id,)
            with db.no_autoflush:
                items=list(db.scalars(select(Item).where(Item.active.is_(True)).order_by(Item.id).limit(501)))
                works=list(db.scalars(select(WorkItem).where(WorkItem.active.is_(True)).order_by(WorkItem.id).limit(501)))
                if len(items)>500 or len(works)>500:raise HTTPException(413,'指定门店商品或作业超过当前选择上限，不能截断后配置规则')
                return {'items':[{'id':r.id,'sku':r.sku,'name':r.name,'unit':r.unit} for r in items],
                    'works':[{'id':r.id,'code':r.code,'name':r.name} for r in works]}
        finally:
            if previous is None:db.info.pop('store_scope',None)
            else:db.info['store_scope']=previous
