"""Reviewed identity configuration and explicit transaction-owned source hooks.

This module does not infer historical ownership or install catch-all cash hooks.
Calling domains must freeze at creation and record attribution before committing.
"""
import hashlib,json,uuid
from contextlib import contextmanager
from datetime import timedelta,timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .config import settings
from .models import User,Store,CashEntry,Vehicle,Sale,Repair,Policy
from .flow_models import Case,Task,Account,Item,Member,VehicleHold,FileAsset,FlowEvent,RequestReceipt
from .tenancy import single_store,role_for_store
from .file_security import require_usable
from . import flow_engine as flow
from .business_entity_models import *

READ={'admin','manager','finance','auditor'}
OPERATIONS={'revision':'主体资料版本','store_binding':'门店主体绑定','account_binding':'资金账户主体绑定','policy':'启用新业务主体冻结'}
LABELS={'submit':'提交来源资料','approve':'独立批准生效','reject':'拒绝申请','cancel':'取消未生效申请','reassign':'转交复核待办'}
SPEC={'label':'经营主体配置','module':'system','create_roles':[],'fields':[],'initial':'draft','actions':[]}
LIMITATION='批准资料用于启用后的新业务。历史归属未确认的记录不会自动补认；更换主体前须核清库存、资金和未结业务。系统不代替工商认证。'
FINISHED={'completed','cancelled','rejected','expired','closed'}


@contextmanager
def authority(db,user,roles=None):
    sid=single_store(db)
    if getattr(user,'_aggregate_scope',False) or db.info.get('aggregate_scope'):raise HTTPException(409,'经营主体配置不在集团汇总中开放，请选择一家门店')
    actual=role_for_store(db,user,sid)
    if not actual or (roles is not None and actual not in roles):raise HTTPException(403,'当前门店岗位不能办理经营主体资料')
    if not db.scalar(select(Store.id).where(Store.id==sid,Store.active.is_(True))):raise HTTPException(403,'门店未启用')
    old=db.info.get('_business_entity_authority');db.info['_business_entity_authority']=(sid,user.id)
    try:yield sid
    finally:
        if old is None:db.info.pop('_business_entity_authority',None)
        else:db.info['_business_entity_authority']=old


def can_read_case(db,user,case):
    return not (getattr(user,'_aggregate_scope',False) or db.info.get('aggregate_scope')) and user.role in READ


def one(db,model,key,column='id'):
    row=db.scalar(select(model).where(getattr(model,column)==key))
    if row is None:raise HTTPException(404,'本店记录不存在或未获授权')
    return row


def plain(row,exclude=()):
    return {c.name:(getattr(row,c.name).isoformat() if hasattr(getattr(row,c.name),'isoformat') else getattr(row,c.name)) for c in row.__table__.columns if c.name not in exclude}


def control(db):
    row=db.scalar(select(EntityStoreControl))
    if not row:row=EntityStoreControl();db.add(row);db.flush()
    return row


def current_store_binding(db,actual_date=None):
    return db.scalar(select(StoreEntityBinding).where(StoreEntityBinding.effective_from<=(actual_date or today())).order_by(StoreEntityBinding.effective_from.desc(),StoreEntityBinding.id.desc()))


def current_account_binding(db,key,actual_date=None):
    return db.scalar(select(AccountEntityBinding).where(AccountEntityBinding.account_id==key,AccountEntityBinding.effective_from<=(actual_date or today())).order_by(AccountEntityBinding.effective_from.desc(),AccountEntityBinding.id.desc()))


def revision_entity(db,revision_id):return one(db,EntityRevision,revision_id).entity_id


def legal_info(db,revision_id):
    revision=one(db,EntityRevision,revision_id);entity=one(db,BusinessEntity,revision.entity_id)
    # Source store files and application identifiers never confer cross-store access.
    return {'revision_id':revision.id,'entity_id':entity.id,'entity_version':entity.version,'revision':revision.revision,'code':entity.code,'tax_identifier':entity.tax_identifier,
            'legal_name':revision.legal_name,'registered_address':revision.registered_address,'contact_phone':revision.contact_phone}


def _file(db,user,case,key):
    asset=one(db,FileAsset,key)
    if asset.case_id!=case.id:raise HTTPException(422,'来源与批准凭据必须属于本次主体申请')
    if asset.generated:raise HTTPException(422,'系统模板不能证明经营主体与账户资料已核对')
    if asset.category not in {'evidence','signed_contract','receipt'}:raise HTTPException(422,'请上传主体资料、账户证明或本次核对凭据')
    require_usable(db,asset)
    return asset


def _get(db,key):
    case=one(db,Case,key)
    if case.kind!='business_entity' or case.flow_version!=1:raise HTTPException(404,'经营主体申请不存在或版本不支持')
    return case,one(db,EntityApplication,key)


def _proposal(db,app):
    return one(db,{'revision':EntityRevisionProposal,'store_binding':StoreEntityProposal,'account_binding':AccountEntityProposal,'policy':EntityPolicyProposal}[app.operation],app.id,'application_id')


def blockers(db):
    """Current local facts only; unresolved historical states fail conservatively."""
    from .opening_import_models import OpeningAccountEntry
    from .business_finance_models import FinanceAdvance
    from .vehicle_operations_models import VehiclePosition
    from .cash_basis import effective_cash
    from .transfer_models import TransferSettlement
    from .transfer_exception_models import TransferLossSettlement
    from .vehicle_transfer_models import VehicleTransferSettlement
    from .reconciliation_models import ClearingOffset
    from .group_models import GroupSettlementEntry
    from .group_benefits_models import BenefitSettlement
    reasons=[]
    if db.scalar(select(Item.id).where((Item.quantity_milli!=0)|(Item.inventory_value_cents!=0))):reasons.append('仍有物资数量或库存价值')
    if db.scalar(select(VehiclePosition.id).where(VehiclePosition.status.in_({'stored','transit','handover'}))) or db.scalar(select(VehicleHold.vehicle_id).where(VehicleHold.delivered.is_(False))):reasons.append('仍有整车库存、在途或销售占用')
    # An approved old row without an explicit exit/delivery is unknown stock,
    # not evidence that inventory is zero.
    legacy=select(Vehicle.id).where(Vehicle.approval_state=='approved',~select(VehiclePosition.id).where(VehiclePosition.vehicle_id==Vehicle.id).exists(),
        ~select(VehicleHold.vehicle_id).where(VehicleHold.vehicle_id==Vehicle.id,VehicleHold.delivered.is_(True)).exists(),
        ~select(Sale.id).where(Sale.vehicle_id==Vehicle.id,Sale.approval_state=='approved',Sale.sale_stage=='delivered').exists())
    if db.scalar(legacy):reasons.append('存在尚未核清实物去向的历史车辆')
    # These are terminal only in their own workflow. A delivered vehicle order
    # still needs its original physical delivery fact; a converted lead needs
    # the generated order. Their independent tasks and successor cases remain
    # subject to the normal checks below.
    terminal_order=(Case.kind=='order')&(Case.state=='delivered')&select(VehicleHold.vehicle_id).where(VehicleHold.case_id==Case.id,VehicleHold.delivered.is_(True)).exists()&select(FlowEvent.id).where(FlowEvent.case_id==Case.id,FlowEvent.action=='deliver').exists()
    child=Case.__table__.alias('entity_successor_order')
    terminal_lead=(Case.kind=='lead')&(Case.state=='converted')&select(child.c.id).where(child.c.parent_id==Case.id,child.c.store_id==Case.store_id,child.c.kind=='order').exists()&select(FlowEvent.id).where(FlowEvent.case_id==Case.id,FlowEvent.action=='reserve').exists()
    if db.scalar(select(Case.id).where(Case.kind!='business_entity',Case.state.not_in(FINISHED),~terminal_order,~terminal_lead)) or db.scalar(select(Task.id).join(Case,Case.id==Task.case_id).where(Case.kind!='business_entity',Task.status=='open')):reasons.append('仍有未结业务或独立待办')
    if db.scalar(select(FinanceAdvance.id).where((FinanceAdvance.balance_cents!=0)|(FinanceAdvance.reserved_cents!=0))):reasons.append('仍有客户预收余额或占用')
    if db.scalar(select(Member.id).where(Member.balance_cents!=0)):reasons.append('仍有旧会员储值余额')
    offsets={}
    for r in db.scalars(select(ClearingOffset)):offsets[r.origin_kind,r.origin_id]=offsets.get((r.origin_kind,r.origin_id),0)+r.amount_cents
    if any(r.amount_cents+offsets.get((kind,r.id),0) for kind,model in [('material',TransferSettlement),('material_loss',TransferLossSettlement),('vehicle',VehicleTransferSettlement)] for r in db.scalars(select(model))):reasons.append('仍有未清算的店间调拨往来')
    from .transfer_goods_recovery_service import entity_has_unsettled
    if entity_has_unsettled(db,offsets):reasons.append('仍有原物资找回后的反向店间往来')
    from .vehicle_transport_models import VehicleTransportLossSettlement,VehicleTransportFoundSettlement
    if any(r.amount_cents+offsets.get((kind,r.id),0) for kind,model in [('vehicle_loss',VehicleTransportLossSettlement),('vehicle_found',VehicleTransportFoundSettlement)] for r in db.scalars(select(model))):reasons.append('仍有原整车运输损失或找回资产归属待实际清算')
    if any(db.scalar(select(func.sum(model.amount_cents)).where(model.side=='store')) for model in (GroupSettlementEntry,BenefitSettlement)):reasons.append('仍有集团会员或权益内部结算余额')
    for model,predicate in [(Sale,Sale.sale_stage!='delivered'),(Repair,Repair.repair_stage!='completed'),(Policy,Policy.end_date>=today())]:
        if db.scalar(select(model.id).where(model.approval_state.in_({'draft','submitted','approved'}),predicate)):reasons.append('存在未结或状态未知的旧版业务');break
    balances={}
    for r in db.scalars(select(OpeningAccountEntry)):balances[r.account_name]=balances.get(r.account_name,0)+r.amount_cents
    for r in effective_cash(db,list(db.scalars(select(CashEntry).where(CashEntry.approval_state=='approved'))),6):balances[r.account]=balances.get(r.account,0)+(r.amount_cents if r.direction=='in' else -r.amount_cents)
    if any(balances.values()):reasons.append('仍有资金账户余额（含期初余额）')
    if db.scalar(select(CashEntry.id).where(CashEntry.approval_state.in_({'draft','submitted'}))):reasons.append('仍有未确认的旧资金资料')
    return reasons


def _date(value):
    if value!=today():raise HTTPException(422,'本版主体绑定只允许批准当日生效，不回填历史或预约未来切换')


def _validate_proposal(db,app,p,approval=False):
    if app.operation=='revision':
        if p.entity_id:
            entity=one(db,BusinessEntity,p.entity_id)
            if entity.version!=p.expected_entity_version:raise HTTPException(409,'主体资料已产生新版本，请核对后重新申请')
            if (entity.code,entity.tax_identifier)!=(p.code,p.tax_identifier):raise HTTPException(422,'主体编码与识别号不能通过资料修订改变')
        elif db.scalar(select(BusinessEntity.id).where((BusinessEntity.code==p.code)|(BusinessEntity.tax_identifier==p.tax_identifier))):raise HTTPException(409,'主体标识已有批准记录，请明确选择原主体追加版本')
    elif app.operation=='store_binding':
        _date(p.effective_from);one(db,EntityRevision,p.revision_id)
        current=current_store_binding(db)
        if current and revision_entity(db,current.revision_id)!=revision_entity(db,p.revision_id):
            reasons=blockers(db)
            if reasons:raise HTTPException(409,'不能切换经营主体：'+'；'.join(reasons)+'。请先核清，不会迁改原业务归属')
    elif app.operation=='account_binding':
        _date(p.effective_from);account=one(db,Account,p.account_id)
        if not account.active:raise HTTPException(409,'资金账户已停用')
        if account.version!=p.expected_account_version:raise HTTPException(409,'资金账户资料已更新，请重新核对')
        revision=one(db,EntityRevision,p.revision_id);store=current_store_binding(db)
        if not store or revision_entity(db,store.revision_id)!=revision.entity_id:raise HTTPException(409,'账户主体须与当前批准的门店主体一致')
        if p.holder_name!=revision.legal_name:raise HTTPException(422,'账户户名须与本次批准主体名称一致；不自动判断别名或代收授权')
        if account.account_type!=p.channel_type:raise HTTPException(422,'账户类型与实际资金渠道不一致')
        current=current_account_binding(db,account.id)
        if current and revision_entity(db,current.revision_id)!=revision.entity_id:raise HTTPException(409,'已绑定账户不可改属于另一主体，请为新主体建立独立资金账户')
        channel=db.scalar(select(EntityAccountChannel).where(EntityAccountChannel.account_id==account.id))
        digest=channel_digest(db,p.channel_type,p.channel_identifier)
        if channel and channel.digest!=digest:raise HTTPException(409,'原账户实际渠道不可改写，请另建资金账户')
        duplicate=db.scalar(select(EntityAccountChannel).where(EntityAccountChannel.digest==digest))
        if duplicate and duplicate.account_id!=account.id:raise HTTPException(409,'该实际资金渠道已被使用，不能重复建立资金账')
    else:
        if db.scalar(select(EntityPolicy.id)):raise HTTPException(409,'本店主体冻结策略已经启用，不可重复启用或追溯重置')
        reasons=blockers(db)
        if reasons:raise HTTPException(409,'不能启用主体冻结：'+'；'.join(reasons)+'。请先核清旧业务；本版不推断其主体')
        binding=current_store_binding(db)
        if not binding or binding.id!=p.binding_id:raise HTTPException(409,'门店有效主体已变，请重新核对启用范围')
        accounts=list(db.scalars(select(Account).where(Account.active.is_(True))))
        if not accounts:raise HTTPException(409,'启用前请配置至少一个经批准的资金账户')
        for account in accounts:
            ab=current_account_binding(db,account.id)
            if not ab or revision_entity(db,ab.revision_id)!=revision_entity(db,binding.revision_id) or ab.account_name!=account.name:raise HTTPException(409,'启用前所有启用资金账户均须有对应主体的批准绑定')


def channel_digest(db,kind,identifier):
    # Cash boxes belong to a physical store. Bank/wallet exact identifiers are
    # central conflict keys; this is duplication protection, not bank validation.
    key=[kind,str(single_store(db)) if kind=='cash' else '',identifier.replace(' ','').upper()]
    return hashlib.sha256(json.dumps(key,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def _apply(db,user,case,app,p,submission,evidence_id):
    if app.operation=='revision':
        if p.entity_id:
            entity=one(db,BusinessEntity,p.entity_id);entity.version+=1
        else:entity=BusinessEntity(code=p.code,tax_identifier=p.tax_identifier,created_by=app.requested_by);db.add(entity);db.flush()
        db.add(EntityRevision(entity_id=entity.id,revision=entity.version,legal_name=p.legal_name,registered_address=p.registered_address,contact_phone=p.contact_phone,
            application_id=case.id,source_store_id=case.store_id,source_evidence_id=submission.source_evidence_id,approved_by=user.id))
    elif app.operation=='store_binding':db.add(StoreEntityBinding(revision_id=p.revision_id,effective_from=p.effective_from,application_id=case.id))
    elif app.operation=='account_binding':
        channel=db.scalar(select(EntityAccountChannel).where(EntityAccountChannel.account_id==p.account_id))
        if not channel:
            channel=EntityAccountChannel(digest=channel_digest(db,p.channel_type,p.channel_identifier),owner_store_id=case.store_id,account_id=p.account_id);db.add(channel);db.flush()
        account=one(db,Account,p.account_id)
        db.add(AccountEntityBinding(account_id=p.account_id,revision_id=p.revision_id,channel_id=channel.id,effective_from=p.effective_from,holder_name=p.holder_name,
            channel_type=p.channel_type,channel_identifier=p.channel_identifier,institution_name=p.institution_name,account_name=account.name,application_id=case.id))
    else:
        db.add(EntityPolicy(policy_version=1,binding_id=p.binding_id,case_cursor=db.scalar(select(func.max(Case.id))) or 0,cash_cursor=db.scalar(select(func.max(CashEntry.id))) or 0,application_id=case.id))
    db.add(EntityDecision(application_id=case.id,decision='approved',actor_id=user.id,evidence_id=evidence_id,reason='独立核对来源资料后批准'))


def _prior(db,user,key,digest):
    receipt=db.scalar(select(RequestReceipt).where(RequestReceipt.request_key==key))
    if not receipt:return None
    if receipt.actor_id!=user.id or receipt.digest!=digest:raise HTTPException(409,'此操作编号已用于不同内容，请刷新后重试')
    return _get(db,receipt.case_id)[0]


def create(db,user,key,v):
    with authority(db,user,{'admin'}):
        digest=flow.request_digest('entity_create',json.loads(json.dumps(v,default=str)))
        old=_prior(db,user,key,digest)
        if old:return describe(db,user,old)
        try:
            case=Case(number='BE-'+uuid.uuid4().hex[:18].upper(),kind='business_entity',flow_version=1,state='draft',title=OPERATIONS[v['operation']],owner_id=user.id,created_by=user.id,business_date=today(),due_date=v['due_date'],data={'operation':v['operation']})
            db.add(case);db.flush();app=EntityApplication(id=case.id,operation=v['operation'],requested_by=user.id,reason=v['reason']);db.add(app);db.flush()
            data=v['details'];model={'revision':EntityRevisionProposal,'store_binding':StoreEntityProposal,'account_binding':AccountEntityProposal,'policy':EntityPolicyProposal}[app.operation]
            p=model(application_id=case.id,**data);db.add(p);db.flush();_validate_proposal(db,app,p)
            control(db);flow.log_event(db,user,case,'entity_create','提出经营主体配置申请',detail={'operation':app.operation,'proposal':plain(p),'reason':app.reason});flow.save_receipt(db,user,key,digest,case);db.commit();return describe(db,user,case)
        except (IntegrityError,OperationalError,StaleDataError):db.rollback();raise HTTPException(409,'主体配置发生冲突，请刷新后核对原申请')


def command(db,user,key,request_id,version,action,v):
    roles={'admin'} if action in {'submit','cancel'} else {'manager'} if action in {'approve','reject'} else {'admin','manager'}
    with authority(db,user,roles):
        digest=flow.request_digest('entity_action',{'id':key,'version':version,'action':action,'values':json.loads(json.dumps(v,default=str))});old=_prior(db,user,request_id,digest)
        if old:return describe(db,user,old)
        case,app=_get(db,key)
        if case.version!=version:raise HTTPException(409,'申请已更新，请刷新后核对当前版本')
        if case.state in FINISHED:raise HTTPException(409,'申请已结束；生效资料只能另提新申请')
        before=case.state
        try:
            if action=='submit':
                if case.state!='draft' or app.requested_by!=user.id:raise HTTPException(409,'仅原申请管理员可提交自己的草稿')
                if _file(db,user,case,v['evidence_id']).created_by!=user.id:raise HTTPException(422,'请提交本人上传并核对的来源资料')
                _validate_proposal(db,app,_proposal(db,app));ctrl=control(db)
                managers=[u for u in flow.eligible_users(db,'manager',case.store_id) if u.id!=user.id and role_for_store(db,u,case.store_id)=='manager']
                if not managers:raise HTTPException(409,'本店须配置另一名主管独立复核；管理员不能自批或代替主管')
                db.add(EntitySubmission(application_id=case.id,control_version=ctrl.version,source_evidence_id=v['evidence_id'],actor_id=user.id))
                case.state='approval';flow.ensure_task(db,case,'entity_review','独立复核经营主体配置','manager',assignee=min(managers,key=lambda u:u.id).id,due=case.due_date)
            elif action in {'approve','reject'}:
                if case.state!='approval' or app.requested_by==user.id:raise HTTPException(409,'申请必须由另一位主管独立复核')
                task=db.scalar(select(Task).where(Task.case_id==case.id,Task.key=='entity_review',Task.status=='open'))
                if not task or task.assignee_id!=user.id:raise HTTPException(403,'请由当前待办负责人复核，或先明确转交')
                submission=one(db,EntitySubmission,case.id,'application_id')
                if action=='approve':
                    _file(db,user,case,submission.source_evidence_id)
                    if _file(db,user,case,v['evidence_id']).created_by!=user.id:raise HTTPException(422,'请使用本复核人上传的实际核对凭据')
                    ctrl=control(db)
                    if submission.control_version!=ctrl.version:raise HTTPException(409,'提交后门店主体或受控业务发生变化，请取消后重新核对申请')
                    _validate_proposal(db,app,_proposal(db,app),True);_apply(db,user,case,app,_proposal(db,app),submission,v['evidence_id']);ctrl.version+=1;case.state='completed'
                else:db.add(EntityDecision(application_id=case.id,decision='rejected',actor_id=user.id,reason=v['reason']));case.state='rejected'
                flow.finish_task(db,case,'entity_review',user)
            elif action=='cancel':
                if app.requested_by!=user.id:raise HTTPException(403,'仅原申请管理员可取消尚未生效申请')
                db.add(EntityDecision(application_id=case.id,decision='cancelled',actor_id=user.id,reason=v['reason']));case.state='cancelled';flow.finish_task(db,case,'entity_review',user,'cancelled')
            elif action=='reassign':
                task=one(db,Task,v['task_id'])
                if case.state!='approval' or task.case_id!=case.id or task.key!='entity_review' or task.status!='open':raise HTTPException(409,'只能转交本申请当前未完成复核待办')
                candidate=one(db,User,v['assignee_id'])
                if candidate.id==app.requested_by or role_for_store(db,candidate,case.store_id)!='manager':raise HTTPException(422,'下一责任人须为本店另一名启用主管')
                task.assignee_id=candidate.id;task.due_date=v['due_date']
            else:raise HTTPException(404,'主体配置动作不存在')
            if case.state in FINISHED:case.completed_date=today()
            case.updated_at=utcnow();flow.log_event(db,user,case,'entity_'+action,LABELS[action],before,detail=json.loads(json.dumps(v,default=str)));flow.save_receipt(db,user,request_id,digest,case);db.commit();return describe(db,user,case)
        except (IntegrityError,OperationalError,StaleDataError):db.rollback();raise HTTPException(409,'主体配置发生并发冲突，请刷新后核对，勿重复提交不同操作编号')


def describe(db,user,case):
    app=one(db,EntityApplication,case.id);p=_proposal(db,app);tasks=list(db.scalars(select(Task).where(Task.case_id==case.id)))
    actions=[]
    if user.role=='admin' and user.id==app.requested_by and case.state not in FINISHED:actions=['submit','cancel'] if case.state=='draft' else ['cancel','reassign']
    if user.role=='manager' and case.state=='approval':
        actions=['reassign']
        if any(t.status=='open' and t.assignee_id==user.id for t in tasks):actions=['approve','reject','reassign']
    return {'id':case.id,'number':case.number,'version':case.version,'state':case.state,'title':case.title,'operation':app.operation,'requested_by':app.requested_by,'reason':app.reason,
        'details':plain(p,{'store_id','application_id'}),'actions':actions,'due_date':case.due_date.isoformat() if case.due_date else None,
        'tasks':[{'id':t.id,'title':t.title,'role':t.role,'assignee_id':t.assignee_id,'status':t.status,'due_date':t.due_date.isoformat(),'overdue':t.status=='open' and t.due_date<today()} for t in tasks],
        'own_file_ids':list(db.scalars(select(FileAsset.id).where(FileAsset.case_id==case.id,FileAsset.created_by==user.id,FileAsset.generated.is_(False)))),
        'submission':plain(s) if (s:=db.scalar(select(EntitySubmission).where(EntitySubmission.application_id==case.id))) else None,
        'decision':plain(d) if (d:=db.scalar(select(EntityDecision).where(EntityDecision.application_id==case.id))) else None,'limitation':LIMITATION}


def configuration(db,user):
    with authority(db,user,READ):
        binding=current_store_binding(db);policy=db.scalar(select(EntityPolicy));revision_ids=set()
        if user.role=='admin':revision_ids.update(db.scalars(select(EntityRevision.id)))
        else:
            revision_ids.update(db.scalars(select(EntityRevision.id).where(EntityRevision.source_store_id==single_store(db))))
            revision_ids.update(db.scalars(select(StoreEntityBinding.revision_id)));revision_ids.update(db.scalars(select(AccountEntityBinding.revision_id)))
            revision_ids.update(db.scalars(select(StoreEntityProposal.revision_id)));revision_ids.update(db.scalars(select(AccountEntityProposal.revision_id)))
            for p in db.scalars(select(EntityRevisionProposal).where(EntityRevisionProposal.entity_id.is_not(None))):revision_ids.update(db.scalars(select(EntityRevision.id).where(EntityRevision.entity_id==p.entity_id)))
        return {'store_binding':({**plain(binding),'entity':legal_info(db,binding.revision_id)} if binding else None),'policy':plain(policy) if policy else None,
            'revisions':[legal_info(db,k) for k in sorted(revision_ids)],'accounts':[{'id':a.id,'version':a.version,'name':a.name,'account_type':a.account_type,'active':a.active,
                'binding':plain(b) if (b:=current_account_binding(db,a.id)) else None} for a in db.scalars(select(Account).order_by(Account.id))],
            'switch_blockers':blockers(db),'limitation':LIMITATION,'operations':OPERATIONS}


def freeze_case_entity(db,user,case,*,required=None,source_case=None):
    """Call immediately after creating Case, before its first event; never commit."""
    if source_case is not None:return freeze_derived_case_entity(db,user,case,source_case,required=required)
    with authority(db,user):
        source=one(db,Case,case.id)
        if source.kind=='business_entity':return None
        return _freeze(db,user,source,required=required)


def _freeze(db,user,source,*,required=None,coordinated=False):
        required=settings.environment=='production' or bool(required)
        policy=db.scalar(select(EntityPolicy));existing=db.scalar(select(CaseEntityContext).where(CaseEntityContext.case_id==source.id))
        if existing:return existing
        if not policy:
            if required:raise HTTPException(409,'本店尚未批准启用经营主体策略')
            return None
        if source.id<=policy.case_cursor:raise HTTPException(409,'历史业务主体未知，不能用当前主体自动补填')
        if source.created_by!=user.id:raise HTTPException(403,'主体须由原业务创建事务冻结，不能代为补记')
        if source.business_date<policy.approved_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).date():raise HTTPException(409,'业务日期早于主体策略启用，不能推断旧期间归属')
        if not coordinated and db.scalar(select(FlowEvent.id).where(FlowEvent.case_id==source.id)):raise HTTPException(409,'该业务已有办理事实，缺失的主体不可事后推断补填')
        binding=current_store_binding(db,source.business_date)
        if not binding:raise HTTPException(409,'业务日期没有已批准门店主体')
        row=CaseEntityContext(case_id=source.id,policy_id=policy.id,binding_id=binding.id,revision_id=binding.revision_id,actor_id=user.id)
        db.add(row);control(db).version+=1;db.flush();return row


def _derived_sources(db,case):
    """Only actual persisted domain relations, never caller-supplied kind/IDs."""
    if case.kind=='vehicle_income' and case.flow_version==1:
        from .vehicle_income_service import entity_source_ids
        return 'vehicle_income',entity_source_ids(db,case)
    if case.kind=='aftercare' and case.flow_version==2:
        from .aftercare_models import AftercareOrder
        r=one(db,AftercareOrder,case.id);return 'aftercare',{r.source_case_id}
    if case.kind=='invoice' and case.flow_version==3:
        from .invoice_models import InvoiceApplication
        r=one(db,InvoiceApplication,case.id);return 'invoice',{r.original_case_id or r.source_case_id}
    if case.kind=='vehicle_operations' and case.flow_version==2:
        from .vehicle_operations_models import VehicleOperation
        r=one(db,VehicleOperation,case.id)
        if r.kind=='other_return' and r.original_operation_id:return 'vehicle_return',{r.original_operation_id}
        if r.kind=='customer_return' and r.aftercare_case_id and r.source_order_id:return 'vehicle_return',{r.aftercare_case_id,r.source_order_id}
    if case.kind=='claim' and case.flow_version==2:
        from .claims_models import ClaimOrder
        r=one(db,ClaimOrder,case.id);return 'claim',{r.source_case_id}
    if case.kind=='membership' and case.flow_version==2:
        from .membership_models import MembershipOrder,MembershipPeriod
        r=db.scalar(select(MembershipOrder).where(MembershipOrder.case_id==case.id))
        if r and r.purpose=='renew_refund':
            period=one(db,MembershipPeriod,r.values['period_id'])
            return 'membership_refund',{period.case_id}
    if case.kind=='business_finance' and case.flow_version==2:
        from .business_finance_models import FinanceOrder,FinanceAdvance,FinanceReturnReceivable
        from .flow_models import StockMove
        r=db.scalar(select(FinanceOrder).where(FinanceOrder.case_id==case.id))
        if r and r.purpose=='advance_refund':return 'advance_refund',{one(db,FinanceAdvance,r.values['advance_id']).case_id}
        if r and r.purpose=='correction':return 'finance_correction',{one(db,CashEntityContext,r.values['original_cash_id'],'cash_id').case_id}
        if r and r.purpose in {'stored_correction','fee_correction'}:
            context=db.scalar(select(CashEntityContext).where(CashEntityContext.cash_id==r.values['original_cash_id']))
            # The caller has verified the typed principal source. In production
            # cash_source_case already refuses an unknown original cash context.
            return 'finance_correction',{context.case_id if context else one(db,Case,r.values['source_case_id']).id}
        if r and r.purpose=='other_return':return 'other_return',{one(db,StockMove,r.values['stock_move_id']).case_id}
        if r and r.purpose in {'other_return_adjust','other_return_refund'}:return 'other_return',{one(db,FinanceReturnReceivable,r.values['receivable_id']).case_id}
    raise HTTPException(409,'该业务不属于有据原单派生用途，不能借用历史主体替代当前主体')


def freeze_derived_case_entity(db,user,case,source_case,*,required=None):
    """Call after the domain's immutable source relation is flushed, before log.

    The supplied source is checked against that actual relation. Old unknown
    sources fail closed; they are never relabelled using today's store binding.
    """
    with authority(db,user):
        target=one(db,Case,case.id);original=one(db,Case,source_case.id)
        if not flow.can_read(db,user,original):raise HTTPException(403,'当前岗位没有原业务的派生权限')
        kind,sources=_derived_sources(db,target)
        if original.id not in sources or original.id>=target.id:raise HTTPException(409,'指定原单与本次实际派生关系不一致')
        existing=db.scalar(select(CaseEntityContext).where(CaseEntityContext.case_id==target.id))
        if existing:
            if (existing.source_case_id,existing.derived_kind)!=(original.id,kind):raise HTTPException(409,'本业务已冻结另一主体来源，不可覆盖')
            return existing
        policy=db.scalar(select(EntityPolicy))
        if not policy and settings.environment!='production' and not required:return None
        if not policy or target.id<=policy.case_cursor:raise HTTPException(409,'派生业务须在主体策略启用后创建，不能回填旧业务')
        if target.created_by!=user.id or db.scalar(select(FlowEvent.id).where(FlowEvent.case_id==target.id)):raise HTTPException(409,'派生主体须由原创建事务在实际办理前冻结')
        source=db.scalar(select(CaseEntityContext).where(CaseEntityContext.case_id==original.id))
        if not source:raise HTTPException(409,'历史原业务主体未知，不能用本店当前配置认领原责任')
        for cid in sources:
            other=one(db,CaseEntityContext,cid,'case_id')
            if revision_entity(db,other.revision_id)!=revision_entity(db,source.revision_id):raise HTTPException(409,'相关原业务不是同一经营主体，不能合并承担或结算')
        if source.policy_id!=policy.id:raise HTTPException(409,'原业务主体策略与本店来源不一致')
        context=CaseEntityContext(case_id=target.id,policy_id=source.policy_id,binding_id=source.binding_id,revision_id=source.revision_id,source_case_id=original.id,derived_kind=kind,actor_id=user.id)
        db.add(context);control(db).version+=1;db.flush();return context


def assert_same_case_entities(db,user,cases,*,required=None):
    """Batch guard; returning identity ID does not authorize raw source reads."""
    with authority(db,user):
        required=settings.environment=='production' or bool(required) or bool(db.scalar(select(EntityPolicy.id)))
        identities=set()
        for case in cases:
            source=one(db,Case,case.id)
            if not flow.can_read(db,user,source):raise HTTPException(403,'当前岗位不能处理批次中某个原单')
            context=require_case_entity(db,user,source,required=required)
            identities.add(revision_entity(db,context.revision_id) if context else None)
        if len(identities)!=1:raise HTTPException(409,'一次月结、资金分配或责任方案必须全部属于同一已确认经营主体')
        return next(iter(identities))


def note_coordinated_case(db,user,case):
    """Three central builders only: call after add, BEFORE the first flush.

    An in-memory token binds this newly pending object to this transaction. It
    grants no directory/file reads and cannot be reused after commit/rollback.
    """
    key='_reconciliation_authority' if case.kind=='interstore_clearing' else '_transfer_authority'
    auth=db.info.get(key);sid=single_store(db)
    versions={'material_transfer':{2,3},'vehicle_transfer':{2},'interstore_clearing':{2}}
    if case.flow_version not in versions.get(case.kind,set()) or case not in db.new or case.created_by!=user.id or not auth or auth[0]!=user.id:
        raise HTTPException(403,'只能登记受控调拨或清算事务刚创建的双方任务')
    if role_for_store(db,user,auth[1]) not in ({'admin','finance'} if key=='_reconciliation_authority' else {'admin','manager','inventory'}):raise HTTPException(403,'发起方当前岗位没有协调权限')
    # Retain the pending object until both sides are frozen: SQLAlchemy's
    # identity map alone is weak, and central builders normally retain IDs.
    db.info.setdefault('_entity_coord_pending',{})[id(case)]=(db.get_transaction(),sid,user.id,auth,key,case)


def freeze_coordinated_case(db,user,case,source,*,required=None):
    """Freeze one paired Case after its fixed central source is flushed.

    Invoke inside existing transfer/reconciliation coordination scope. The
    caller receives only None; the other store's identity/account is not read
    through the public configuration API or returned to the initiating person.
    """
    from .transfer_models import MaterialTransfer,TransferMovement
    from .vehicle_transfer_models import VehicleTransfer,VehicleMovement
    from .reconciliation_models import ClearingOrder,ClearingCash,ClearingOffset
    contracts={MaterialTransfer:('material_transfer','_transfer_authority','from_store_id','to_store_id','from_case_id','to_case_id',[(TransferMovement,'transfer_id')]),
        VehicleTransfer:('vehicle_transfer','_transfer_authority','from_store_id','to_store_id','from_case_id','to_case_id',[(VehicleMovement,'transfer_id')]),
        ClearingOrder:('interstore_clearing','_reconciliation_authority','payer_store_id','receiver_store_id','payer_case_id','receiver_case_id',[(ClearingCash,'order_id'),(ClearingOffset,'order_id')])}
    contract=contracts.get(type(source));sid=single_store(db)
    if not contract:raise HTTPException(403,'不支持此协调来源类型')
    kind,key,left,right,left_case,right_case,facts=contract;auth=db.info.get(key)
    token=db.info.get('_entity_coord_pending',{}).get(id(case))
    if not auth or auth[0]!=user.id or not token or token[:5]!=(db.get_transaction(),sid,user.id,auth,key) or token[5] is not case:raise HTTPException(403,'协调主体冻结只允许原创建事务，不接受历史任务补填')
    persisted=db.scalar(select(type(source)).where(type(source).id==source.id))
    if not persisted or source.requested_by!=user.id or source.status!='requested' or getattr(source,left)!=auth[1] or sid not in (getattr(source,left),getattr(source,right)):
        raise HTTPException(403,'协调来源、发起店或双方范围不一致')
    expected=getattr(source,left_case) if sid==getattr(source,left) else getattr(source,right_case)
    current=one(db,Case,case.id)
    if current.id!=expected or current.kind!=kind or current.flow_version not in ({2,3} if kind=='material_transfer' else {2}) or current.created_by!=user.id:raise HTTPException(403,'待冻结任务不是本协调来源固定的一方')
    if any(db.scalar(select(model.id).where(getattr(model,column)==source.id)) for model,column in facts):raise HTTPException(409,'协调业务已有实物或资金事实，不能回填主体')
    previous=db.info.get('_business_entity_authority');db.info['_business_entity_authority']=(sid,user.id)
    try:
        result=_freeze(db,user,current,required=required,coordinated=True)
        if result:flow.log_event(db,user,current,'entity_coordinated_freeze','系统按双方来源冻结本店主体',detail={'source_kind':kind,'source_id':source.id,'initiating_store_id':auth[1]})
        db.info['_entity_coord_pending'].pop(id(case),None);db.flush()
    finally:
        if previous is None:db.info.pop('_business_entity_authority',None)
        else:db.info['_business_entity_authority']=previous


def require_case_entity(db,user,case,*,required=False):
    with authority(db,user):
        source=one(db,Case,case.id);policy=db.scalar(select(EntityPolicy));context=db.scalar(select(CaseEntityContext).where(CaseEntityContext.case_id==source.id))
        if context:return context
        if required or (policy and source.id>policy.case_cursor):raise HTTPException(409,'该业务缺少创建时冻结的经营主体，不能用当前设置推断')
        return None


def cash_source_case(db,user,cash_id,*,required=None):
    """Actual cash's primary source; shared PaymentLinks never choose identity."""
    with authority(db,user):
        one(db,CashEntry,cash_id);context=db.scalar(select(CashEntityContext).where(CashEntityContext.cash_id==cash_id))
        if context:return one(db,Case,context.case_id)
        if settings.environment=='production' or required or db.scalar(select(EntityPolicy.id)):raise HTTPException(409,'原现金主体未知，不能按当前门店补认或更正归属')
        return None


def require_account_entity(db,user,case,account_id,actual_date,*,original_cash_id=None):
    """Identity/channel guard; actual amount and refund capacity stay in the domain."""
    with authority(db,user):
        context=require_case_entity(db,user,case);account=one(db,Account,account_id)
        if not context:
            if settings.environment=='production' or db.scalar(select(EntityPolicy.id)):raise HTTPException(409,'原业务主体未知，不得用当前账户推断新的资金归属')
            return None
        if original_cash_id:
            original=one(db,CashEntityContext,original_cash_id,'cash_id');original_case=one(db,CaseEntityContext,original.case_id,'case_id');binding=one(db,AccountEntityBinding,original.account_binding_id)
            if revision_entity(db,original_case.revision_id)!=revision_entity(db,context.revision_id) or binding.account_id!=account_id:raise HTTPException(409,'原路资金操作必须保留原主体和原实际资金账户')
            cash=one(db,CashEntry,original_cash_id)
            if actual_date<cash.business_date:raise HTTPException(422,'原路退款日期不能早于原实际流水')
        else:
            binding=current_account_binding(db,account_id,actual_date)
            if not account.active:raise HTTPException(409,'资金账户已停用')
        if not binding or revision_entity(db,binding.revision_id)!=revision_entity(db,context.revision_id):raise HTTPException(409,'实际资金账户与原业务经营主体不一致')
        if binding.account_name!=account.name:raise HTTPException(409,'账户名称与批准渠道快照不一致，请核对原资金账户')
        return binding


def record_cash_entity(db,user,case,cash,account_id,*,original_cash_id=None):
    """Append after CashEntry flush, before the calling command commits once."""
    with authority(db,user):
        source=one(db,CashEntry,cash.id);context=require_case_entity(db,user,case)
        if not context:
            if settings.environment=='production' or db.scalar(select(EntityPolicy.id)):raise HTTPException(409,'原业务主体未知，新增实际资金须先完成有据归属方案')
            return None
        policy=one(db,EntityPolicy,context.policy_id)
        if source.id<=policy.cash_cursor:raise HTTPException(409,'历史资金流水不能自动补记主体')
        if source.created_by!=user.id:raise HTTPException(403,'资金归属须由实际流水创建事务记录')
        if source.business_date<policy.approved_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).date():raise HTTPException(409,'资金实际日期早于主体策略启用，不能自动补记旧资金归属')
        binding=require_account_entity(db,user,case,account_id,source.business_date,original_cash_id=original_cash_id)
        if source.account!=binding.account_name or source.approval_state!='approved':raise HTTPException(409,'仅可冻结本次已确认、对应实际账户的资金流水')
        if original_cash_id:
            original=one(db,CashEntry,original_cash_id)
            if original_cash_id>=source.id or source.direction==original.direction:raise HTTPException(409,'原路反向流水必须关联此前相反方向的原实际收付款')
        old=db.scalar(select(CashEntityContext).where(CashEntityContext.cash_id==source.id))
        if old:
            if (old.case_id,old.account_binding_id,old.original_cash_id)!=(case.id,binding.id,original_cash_id):raise HTTPException(409,'该原始资金流水已冻结另一归属，不能重复归账')
            return old
        row=CashEntityContext(cash_id=source.id,case_id=case.id,account_binding_id=binding.id,original_cash_id=original_cash_id,actor_id=user.id)
        db.add(row);control(db).version+=1;db.flush();return row


def case_entity_snapshot(db,user,case):
    with authority(db,user):
        context=require_case_entity(db,user,case)
        return {'status':'frozen','context':plain(context),'entity':legal_info(db,context.revision_id)} if context else {'status':'unknown','label':'历史或未启用业务，主体未确认'}
