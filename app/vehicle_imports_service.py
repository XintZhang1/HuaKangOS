"""CSV review calls the same guarded purchase actions in one transaction."""
from contextlib import contextmanager
from datetime import date,timedelta
import hashlib,json
from fastapi import HTTPException
from sqlalchemy import select,or_,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .flow_models import FileAsset,Task
from .models import User
from .flow_documents import upload_file,file_info
from .private_files import read_content
from .transfer_service import authority
from . import flow_engine as flow,vehicle_procurement_service as purchase
from .vehicle_imports_csv import parse,LABELS
from .vehicle_imports_models import VehicleImportBatch as Batch,VehicleImportRow as Row,VehicleImportClaim as Claim,VehicleImportResult as Result,VehicleImportRequest as Request

READ=purchase.READ
PREP={'funds':{'admin','manager'},'ship':{'admin','inventory'},'receive':{'admin','inventory'}}
STATUS={'invalid':'逐行预检未通过','prepared':'待试执行','trial_passed':'待主管复核','reviewed':'待本人确认办理','confirmed':'已执行原单动作','cancelled':'已取消，来源保留'}


@contextmanager
def access(db,user,roles=READ):
    with authority(db,user,roles):
        previous=db.info.get('_vehicle_import_authority');db.info['_vehicle_import_authority']=True
        try:yield
        finally:
            if previous is None:db.info.pop('_vehicle_import_authority',None)
            else:db.info['_vehicle_import_authority']=previous


def load(db,user,key):
    batch=purchase.one(db,Batch,key);case,_=purchase.get_order(db,user,batch.case_id)
    if batch.kind=='funds' and user.role not in purchase.MONEY:raise HTTPException(403,'当前岗位不能读取请款文件及金额；请使用已复核的车辆清单')
    return batch,case


def items(db,batch):return purchase.rows(db,Row,batch_id=batch.id)


def describe(db,user,batch,case):
    asset=purchase.one(db,FileAsset,batch.source_file_id)
    result={'id':batch.id,'version':batch.version,'case_id':case.id,'case_number':case.number,'case_version':case.version,
        'source_case_version':batch.source_case_version,'kind':batch.kind,'kind_label':LABELS[batch.kind],'status':batch.status,'status_label':STATUS[batch.status],
        'source_digest':batch.source_digest,'source_reference':batch.source_reference,'prepared_by':batch.prepared_by,'reviewed_by':batch.reviewed_by,
        'replacement_batch_id':batch.replacement_batch_id,'row_count':batch.row_count,'errors':batch.errors,'file':file_info(asset,db),'rows':[],
        'actions':[],'tasks':[{'id':t.id,'title':t.title,'assignee_id':t.assignee_id,'due_date':t.due_date.isoformat(),'overdue':t.due_date<today()} for t in purchase.rows(db,Task,case_id=case.id) if t.key.startswith(f'vi_{batch.id}_') and t.status=='open']}
    if batch.kind=='funds':result['amount_cents']=batch.amount_cents
    for r in items(db,batch):
        fact=db.scalar(select(Result).where(Result.row_id==r.id))
        result['rows'].append({'id':r.id,'row_number':r.row_number,'values':r.values,'errors':r.errors,
            'result':({k:getattr(fact,k) for k in ('funds_request_id','shipment_id','receipt_id') if getattr(fact,k)} if fact else None)})
    own=batch.prepared_by==user.id and user.role in PREP[batch.kind]
    if batch.status=='prepared' and own:result['actions'].append('trial')
    if batch.status=='trial_passed' and user.role in purchase.MANAGE and batch.prepared_by!=user.id:result['actions'].append('review')
    if batch.status=='reviewed' and own:result['actions'].append('confirm')
    if batch.status not in {'confirmed','cancelled'} and (own or user.role in purchase.MANAGE):result['actions'].append('cancel')
    if result['tasks'] and user.role in purchase.MANAGE:result['actions'].append('reassign')
    return result


def run(db,user,key,payload,op,roles=READ):
    with access(db,user,roles):
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
        try:
            old=db.scalar(select(Request).where(Request.actor_id==user.id,Request.request_key==key))
            if old:
                if old.digest!=digest:raise HTTPException(409,'请求编号已用于不同资料，请核对原提交结果')
                return describe(db,user,*load(db,user,old.batch_id))
            batch,case=op();db.flush();db.add(Request(actor_id=user.id,request_key=key,digest=digest,batch_id=batch.id));db.commit()
            return describe(db,user,batch,case)
        except (IntegrityError,OperationalError,StaleDataError) as exc:
            db.rollback();raise HTTPException(409,'批次、来源行或原单已被同时办理；本次未保存，请刷新核对并保留请求编号') from exc
        except Exception:db.rollback();raise


def _key(*values):return hashlib.sha256(json.dumps(values,ensure_ascii=False).encode()).hexdigest()


def _validated_rows(db,user,case,kind,source_reference,parsed,replacement):
    errors=[];seen=set();line_counts={};total=0;normalized=[];replaced_ids=set();ancestor=replacement
    while ancestor:
        if ancestor.id in replaced_ids or (ancestor.case_id,ancestor.kind,ancestor.status)!=(case.id,kind,'cancelled'):raise HTTPException(409,'替代来源链异常，请核对历史批次')
        replaced_ids.add(ancestor.id);ancestor=purchase.one(db,Batch,ancestor.replacement_batch_id) if ancestor.replacement_batch_id else None
    for raw in parsed:
        v=raw['values'];err=list(raw['errors']);line_id=None;manifest=None
        origin=_key(case.store_id,kind,source_reference,v.get('source_row','invalid-'+str(raw['number'])))
        vehicle=_key(case.store_id,case.id,kind,v.get('vin','invalid-'+str(raw['number'])))
        for key in (origin,vehicle):
            if key in seen:err.append('本批次来源行或 VIN 重复')
            seen.add(key)
            histories=list(db.scalars(select(Row).where(or_(Row.origin_key==key,Row.vehicle_key==key))))
            for old in histories:
                previous=purchase.one(db,Batch,old.batch_id)
                if previous.status!='cancelled':err.append('该来源行或 VIN 已有批次；须先核对原批次，不得重复导入');break
            cancelled=[r for r in histories if purchase.one(db,Batch,r.batch_id).status=='cancelled']
            if cancelled and max(cancelled,key=lambda r:r.id).batch_id not in replaced_ids:err.append('请明确关联最近已取消且未执行的替代批次')
        if not err:
            try:
                if kind=='funds':
                    line=purchase.one(db,purchase.Line,v['line_id'])
                    if line.case_id!=case.id:raise HTTPException(422,'采购车型行不属于原单')
                    line_id=line.id;price=db.scalar(select(purchase.Price).where(purchase.Price.line_id==line.id))
                    if not price or v['amount_cents']>price.unit_cost_cents:raise HTTPException(422,'逐 VIN 请款超过已冻结的单车成本')
                    line_counts[line.id]=line_counts.get(line.id,0)+1
                    available=line.quantity-sum(c.quantity for c in purchase.rows(db,purchase.Cancellation,line_id=line.id))
                    previous=sum(1 for r in db.scalars(select(Row).join(Batch,Batch.id==Row.batch_id).where(Batch.case_id==case.id,Batch.kind=='funds',Batch.status.not_in(['cancelled','invalid']),Row.line_id==line.id)))
                    if line_counts[line.id]+previous>available:raise HTTPException(409,'请款 VIN 数量超过原采购行尚有效数量')
                    total+=v['amount_cents']
                else:
                    manifest=purchase.one(db,Row,v['manifest_row_id']);parent=purchase.one(db,Batch,manifest.batch_id)
                    if parent.case_id!=case.id or parent.kind!='funds' or parent.status!='confirmed' or manifest.vin!=v['vin']:
                        raise HTTPException(422,'请选择本采购单已确认请款清单中的同一 VIN 行')
                    line_id=manifest.line_id
                    if kind=='ship':
                        shipped=date.fromisoformat(v['shipped_date']);expected=date.fromisoformat(v['expected_date'])
                        if not case.business_date<=shipped<=today() or not shipped<=expected<=today()+timedelta(days=365):raise HTTPException(422,'实际发运日期不能早于原单或晚于今天，预计到货不能早于发运')
                    else:
                        if date.fromisoformat(v['received_date'])!=today():raise HTTPException(422,'到货确认须使用今天的实际验收日期，不能预报或回填')
                        shipped=_shipment(db,case,manifest.id)
                        if date.fromisoformat(v['received_date'])<shipped.shipped_date:raise HTTPException(422,'实际到货不能早于原发运日期')
                        location=purchase.require_active(db,'locations',v['location_id']);warehouse=purchase.require_active(db,'warehouses',location.warehouse_id)
                        if warehouse.warehouse_type not in {'vehicles','mixed'}:raise HTTPException(422,'到货库位须属于本店整车仓或混合仓')
            except HTTPException as exc:err.append(str(exc.detail))
        if err:errors.append({'row_number':raw['number'],'errors':list(dict.fromkeys(err))})
        normalized.append((raw,line_id,manifest.id if manifest else None,origin,vehicle,list(dict.fromkeys(err))))
    return normalized,errors,total


def prepare(db,user,case_id,key,version,kind,source_reference,name,content,replacement_id=None):
    if kind not in PREP:raise HTTPException(422,'导入类别不存在')
    if not name.lower().endswith('.csv'):raise HTTPException(422,'请保留原始 .csv 扩展名，不得改名伪装为其他文件')
    parsed=parse(kind,content);sha=hashlib.sha256(content).hexdigest()
    def op():
        case,_=purchase.get_order(db,user,case_id)
        if case.version!=version:raise HTTPException(409,'采购单已变化，请刷新后重新核对清单')
        if case.state not in {'receiving','completed'}:raise HTTPException(409,'须先批准原采购计划和逐行成本')
        replacement=None
        if replacement_id:
            replacement=purchase.one(db,Batch,replacement_id)
            if (replacement.case_id,replacement.kind,replacement.status)!=(case.id,kind,'cancelled') or db.scalar(select(Result.id).join(Row,Row.id==Result.row_id).where(Row.batch_id==replacement.id)):
                raise HTTPException(409,'替代批次须为同原单同类别、已取消且未执行的批次')
        normalized,errors,total=_validated_rows(db,user,case,kind,source_reference,parsed,replacement)
        asset=upload_file(db,user,case,name,content,'procurement_contract' if kind=='funds' else 'evidence');db.flush()
        # Supplier files may be deduplicated within the same case. Keep the first
        # uploader, while this batch records the new employee's own confirmation.
        batch=Batch(case_id=case.id,kind=kind,status='invalid' if errors else 'prepared',source_file_id=asset.id,source_digest=sha,
            source_reference=source_reference,source_case_version=case.version,replacement_batch_id=replacement_id,prepared_by=user.id,row_count=len(parsed),amount_cents=total,errors=errors)
        db.add(batch);db.flush()
        for raw,line_id,manifest_id,origin,vehicle,err in normalized:
            value=raw['values'];r=Row(batch_id=batch.id,row_number=raw['number'],source_row=value.get('source_row',''),vin=value.get('vin',''),line_id=line_id,
                manifest_row_id=manifest_id,origin_key=origin,vehicle_key=vehicle,values=value,errors=err)
            db.add(r);db.flush()
            if not errors:
                for token in (origin,vehicle):db.add(Claim(key=token,row_id=r.id))
        if not errors:flow.ensure_task(db,case,f'vi_{batch.id}_prepare','导入清单试执行与核对','manager' if kind=='funds' else 'inventory',assignee=user.id,due=today()+timedelta(days=7))
        frozen=[{'number':r['number'],'values':r['values']} for r in parsed]
        flow.log_event(db,user,case,'vi_prepare','登记车辆导入来源与逐行预检',detail={'batch_id':batch.id,'kind':kind,'rows':len(parsed),'error_rows':len(errors),
            'source_digest':sha,'rows_digest':_key(sha,frozen)})
        return batch,case
    return run(db,user,key,{'action':'prepare','case_id':case_id,'version':version,'kind':kind,'source_reference':source_reference,'name':name,'sha':sha,'replacement_id':replacement_id},op,PREP[kind])


def _shipment(db,case,manifest_id):
    result=db.scalar(select(Result).join(Row,Row.id==Result.row_id).join(Batch,Batch.id==Row.batch_id).where(Row.manifest_row_id==manifest_id,Batch.kind=='ship',Batch.status=='confirmed',Batch.case_id==case.id))
    if not result or not result.shipment_id:raise HTTPException(409,'此请款 VIN 尚无已确认的导入发运；不能把请款或发运意向当作到货')
    shipment=purchase.one(db,purchase.Shipment,result.shipment_id)
    if shipment.status!='transit':raise HTTPException(409,'此 VIN 已验收或退回，不能重复到货')
    return shipment


def _apply(db,user,batch,case):
    for r in items(db,batch):
        v=r.values;evidence={'evidence_id':batch.source_file_id}
        if batch.kind=='funds':
            action='request_funds';values=evidence|{'amount_cents':v['amount_cents'],'reason':'车辆导入批次 '+str(batch.id)+' 来源行 '+r.source_row};model=purchase.Funds;field='funds_request_id'
        elif batch.kind=='ship':
            action='ship';values=evidence|{'line_id':r.line_id,'vin':r.vin,'shipped_date':date.fromisoformat(v['shipped_date']),'expected_date':date.fromisoformat(v['expected_date'])};model=purchase.Shipment;field='shipment_id'
            if values['shipped_date']>today():raise HTTPException(422,'实际发运日期不能在未来')
        else:
            shipment=_shipment(db,case,r.manifest_row_id)
            if date.fromisoformat(v['received_date'])!=today() or date.fromisoformat(v['received_date'])<shipment.shipped_date:raise HTTPException(409,'到货日期须为今天且不早于原发运；请取消未执行批次后重新核对实际资料')
            action='receive';values=evidence|{'shipment_id':shipment.id,'vin':r.vin,'location_id':v['location_id']};model=purchase.Receipt;field='receipt_id'
        previous=set(db.scalars(select(model.id).where(model.case_id==case.id)))
        purchase.command_in_transaction(db,user,case.id,case.version,action,values);db.flush()
        fresh=list(db.scalars(select(model.id).where(model.case_id==case.id,model.id.not_in(previous))))
        if len(fresh)!=1:raise HTTPException(409,'原单动作结果不唯一，本批次未执行')
        db.add(Result(row_id=r.id,**{field:fresh[0]}));db.flush()


def command(db,user,key,batch_id,version,case_version,action,values):
    def op():
        batch,case=load(db,user,batch_id)
        if batch.version!=version:raise HTTPException(409,'批次已变化，请刷新核对')
        if action=='reassign':
            if user.role not in purchase.MANAGE:raise HTTPException(403,'仅主管可以交接内部核验任务')
            task=purchase.one(db,Task,values['task_id'])
            if task.case_id!=case.id or not task.key.startswith(f'vi_{batch.id}_') or task.status!='open':raise HTTPException(409,'任务不是本批次待办')
            target=flow.assignable(db,values['assignee_id'],case.store_id)
            if target.role not in ({'admin','manager'} if task.role=='manager' else {'admin','inventory'}):raise HTTPException(422,'接收人须在本店担任对应岗位')
            if task.key.endswith('_review') and values['assignee_id']==batch.prepared_by:raise HTTPException(403,'不能把复核交给清单编制人')
            if not task.key.endswith('_review') and values['assignee_id']!=batch.prepared_by:raise HTTPException(409,'实际确认由原编制人办理；人员交接请取消未执行批次并由新员工核对替代资料')
            task.assignee_id=values['assignee_id'];batch.updated_at=utcnow()
        elif action=='cancel':
            if user.id!=batch.prepared_by and user.role not in purchase.MANAGE:raise HTTPException(403,'仅编制人或主管可取消未执行批次')
            if batch.status in {'confirmed','cancelled'}:raise HTTPException(409,'批次已结束；已执行事实请在原采购单办理取消、退车或退款')
            for r in items(db,batch):
                for claim in purchase.rows(db,Claim,row_id=r.id):db.delete(claim)
            batch.status='cancelled'
            for t in purchase.rows(db,Task,case_id=case.id):
                if t.key.startswith(f'vi_{batch.id}_') and t.status=='open':flow.finish_task(db,case,t.key,user,'cancelled')
        else:
            if case.version!=case_version or case.version!=batch.source_case_version:raise HTTPException(409,'原采购单已变化，旧清单不能覆盖并行办理；请取消后按新版本核对替代资料')
            asset=purchase.evidence(db,user,case,batch.source_file_id,batch.kind=='funds')
            if hashlib.sha256(read_content(db,asset)).hexdigest()!=batch.source_digest:raise HTTPException(409,'冻结来源内容校验不一致')
            if action=='review':
                if user.role not in purchase.MANAGE or user.id==batch.prepared_by:raise HTTPException(403,'须由编制人之外的主管复核，管理员也不能自行复核')
                if batch.status!='trial_passed':raise HTTPException(409,'先由实际经办人完成试执行')
                purchase.assert_task(db,user,case,f'vi_{batch.id}_review');batch.reviewed_by=user.id;batch.status='reviewed'
                flow.finish_task(db,case,f'vi_{batch.id}_review',user)
                flow.ensure_task(db,case,f'vi_{batch.id}_confirm','按冻结清单确认实际办理','manager' if batch.kind=='funds' else 'inventory',assignee=batch.prepared_by,due=today()+timedelta(days=7))
            elif action in {'trial','confirm'}:
                if user.id!=batch.prepared_by or user.role not in PREP[batch.kind]:raise HTTPException(403,'须由本店原清单编制人核对并确认自己的实际动作')
                expected='prepared' if action=='trial' else 'reviewed'
                if batch.status!=expected:raise HTTPException(409,'批次尚未完成前置核验或已经办理')
                purchase.assert_task(db,user,case,f'vi_{batch.id}_'+('prepare' if action=='trial' else 'confirm'))
                if action=='trial':
                    savepoint=db.begin_nested()
                    try:_apply(db,user,batch,case);db.flush()
                    finally:savepoint.rollback()
                    batch,case=load(db,user,batch_id);batch.status='trial_passed'
                    candidates=[u for u in flow.eligible_users(db,'manager',case.store_id) if u.id!=batch.prepared_by]
                    if not candidates:candidates=list(db.scalars(select(User).where(User.role=='admin',User.active.is_(True),User.id!=batch.prepared_by).order_by(User.id)))
                    if not candidates:raise HTTPException(409,'请先配置另一名本店主管进行独立复核')
                    flow.finish_task(db,case,f'vi_{batch.id}_prepare',user)
                    flow.ensure_task(db,case,f'vi_{batch.id}_review','复核车辆导入来源与逐行结果','manager',assignee=candidates[0].id,due=today()+timedelta(days=7))
                else:
                    if values.get('confirmed') is not True:raise HTTPException(422,'请明确确认本次实际办理')
                    _apply(db,user,batch,case);batch.status='confirmed';batch.confirmed_by=user.id
                    flow.finish_task(db,case,f'vi_{batch.id}_confirm',user)
            else:raise HTTPException(404,'导入动作不存在')
        # The generic case serializer hides keys containing cost from stock roles.
        note_key='cost_review_note' if batch.kind=='funds' else 'reason'
        flow.log_event(db,user,case,'vi_'+action,{'trial':'试执行通过（全部业务结果已回滚）','review':'主管复核导入清单','confirm':'按导入清单执行原采购动作','cancel':'取消未执行导入批次','reassign':'交接导入核验任务'}[action],detail={'batch_id':batch.id,'kind':batch.kind,note_key:values['reason']})
        return batch,case
    return run(db,user,key,{'action':action,'batch_id':batch_id,'version':version,'case_version':case_version,'values':values},op)
