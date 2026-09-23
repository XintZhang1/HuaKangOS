"""Both stores attest their own physical actions; coordination never moves ownership.

Only this service may briefly scope into the other party to enqueue/update its
case/task and paired internal receivable. Goods are posted only in the actor's
current store. All changes and the idempotency receipt commit together.
"""
from contextlib import contextmanager
from datetime import date
import hashlib
import json
import uuid
from fastapi import HTTPException
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today, utcnow
from .models import Store
from .tenancy import single_store, role_for_store, set_scope
from .flow_models import Case, Item, StockMove, Task, FileAsset
from . import flow_engine as eng
from . import business_entity_service as entities
from .transfer_models import MaterialTransfer, TransferLine, TransferMovement, TransferSettlement, TransferReceipt

READ_ROLES={'admin','manager','inventory','finance','auditor'}
WRITE_ROLES={'admin','manager','inventory'}
LABELS={'requested':'待双方批准','approved':'待发出','transit':'在途与验收中','completed':'已结清实物','cancelled':'已取消'}
MOVEMENTS={'dispatch':'发出','accept':'验收入库','reject':'拒收待退','return_ship':'退回在途','return_receive':'退回入库'}
NEW_TRANSFER_VERSION=3


@contextmanager
def authority(db,user,roles=READ_ROLES):
    sid=single_store(db)
    if role_for_store(db,user,sid) not in roles or not db.scalar(select(Store.id).where(Store.id==sid,Store.active.is_(True))):
        raise HTTPException(403,'当前门店岗位不能办理物资调拨')
    previous=db.info.get('_transfer_authority')
    db.info['_transfer_authority']=(user.id,sid)
    try:yield sid
    finally:
        if previous is None:db.info.pop('_transfer_authority',None)
        else:db.info['_transfer_authority']=previous


@contextmanager
def coordination_scope(db,sid,parties):
    # Never expose this helper as an endpoint. Caller has authenticated a party.
    if not db.info.get('_transfer_authority') or sid not in parties:
        raise HTTPException(403,'调拨双方范围无效')
    db.flush()
    previous={k:db.info.get(k) for k in ('store_scope','write_store')}
    set_scope(db,[sid],sid)
    try:
        yield
        db.flush()
    finally:
        for k,v in previous.items():
            if v is None:db.info.pop(k,None)
            else:db.info[k]=v


def get_transfer(db,key,sid):
    row=db.scalar(select(MaterialTransfer).where(MaterialTransfer.id==key,
        or_(MaterialTransfer.from_store_id==sid,MaterialTransfer.to_store_id==sid)))
    if not row:raise HTTPException(404,'调拨不存在或不属于当前门店')
    return row


def lines_for(db,row):return list(db.scalars(select(TransferLine).where(TransferLine.transfer_id==row.id).order_by(TransferLine.id)))
def movements_for(db,row):return list(db.scalars(select(TransferMovement).where(TransferMovement.transfer_id==row.id).order_by(TransferMovement.id)))


def local_case(db,user,row,sid):
    case=eng.get_case(db,user,row.from_case_id if sid==row.from_store_id else row.to_case_id)
    if case.kind!='material_transfer' or case.flow_version not in {2,3}:raise HTTPException(409,'调拨流程版本不受支持')
    return case


def action_version(db,user,key):
    with authority(db,user,WRITE_ROLES) as sid:
        return local_case(db,user,get_transfer(db,key,sid),sid).flow_version


def serialize(db,user,row,sid):
    source=sid==row.from_store_id
    case=local_case(db,user,row,sid)
    info={'id':row.id,'number':row.number,'version':row.version,'case_id':case.id,'case_version':case.version,
        'status':row.status,'status_label':LABELS[row.status],'side':'source' if source else 'destination',
        'from_store_name':db.get(Store,row.from_store_id).name,'to_store_name':db.get(Store,row.to_store_id).name,
        'source_approved':row.source_approved_by is not None,'destination_approved':row.destination_approved_by is not None,
        'due_date':row.due_date.isoformat(),'reason':row.reason,'flow_version':case.flow_version,'lines':[],'movements':[]}
    moves=movements_for(db,row)
    loss_by_line={};active=None;active_found=None
    if case.flow_version==3:
        from . import transfer_exception_service as exceptions
        from .transfer_exception_models import TransferException
        loss_by_line=exceptions.loss_totals(db,row);active=exceptions._active(db,row)
        info['active_exception_id']=active.id if active else None
        info['exception_ids']=list(db.scalars(select(TransferException.id).where(TransferException.transfer_id==row.id).order_by(TransferException.id)))
        from . import transfer_goods_recovery_service as found
        from .transfer_goods_recovery_models import GoodsRecovery
        with found.authority(db,user):
            discoveries=list(db.scalars(select(GoodsRecovery).where(GoodsRecovery.transfer_id==row.id).order_by(GoodsRecovery.id)))
            active_found=next((g for g in discoveries if g.active_transfer_id is not None),None)
            info['active_goods_recovery_id']=active_found.id if active_found else None
            info['goods_recovery_ids']=[g.id for g in discoveries]
    for line in lines_for(db,row):
        own=[m for m in moves if m.line_id==line.id]
        sums={kind:sum(m.quantity_milli for m in own if m.kind==kind) for kind in MOVEMENTS}
        value={kind:sum(m.value_cents for m in own if m.kind==kind) for kind in MOVEMENTS}
        detail={'id':line.id,'sku':line.sku,'name':line.name,'unit':line.unit,'quantity_milli':line.quantity_milli,
            'sent_milli':sums['dispatch'],'accepted_milli':sums['accept'],'rejected_milli':sums['reject'],
            'uninspected_milli':sums['dispatch']-sums['accept']-sums['reject'],
            'return_pending_milli':sums['reject']-sums['return_ship'],
            'return_in_transit_milli':sums['return_ship']-sums['return_receive'],
            'returned_milli':sums['return_receive']}
        lost=loss_by_line.get(line.id,{})
        if case.flow_version==3:
            detail['lost_milli']=lost.get('quantity_milli',0)
            detail['uninspected_milli']-=lost.get('outbound_milli',0)
            detail['return_pending_milli']-=lost.get('rejected_milli',0)
            detail['return_in_transit_milli']-=lost.get('returning_milli',0)
        if user.role in eng.MANAGEMENT:
            detail.update(sent_value_cents=value['dispatch'],accepted_value_cents=value['accept'],returned_value_cents=value['return_receive'],
                          in_transit_value_cents=value['dispatch']-value['accept']-value['return_receive']-lost.get('value_cents',0))
            if case.flow_version==3:detail['lost_value_cents']=lost.get('value_cents',0)
        info['lines'].append(detail)
    for m in moves:
        item={'id':m.id,'line_id':m.line_id,'kind':m.kind,'label':MOVEMENTS[m.kind],'quantity_milli':m.quantity_milli,
              'original_id':m.original_id,'business_date':m.business_date.isoformat(),'reason':m.reason}
        if m.store_id==sid:item['evidence_id']=m.evidence_id
        if user.role in eng.MANAGEMENT:item['value_cents']=m.value_cents
        if case.flow_version==3 and m.kind in exceptions.STAGES:
            remaining=exceptions.bucket_remaining(db,row,m);item['remaining_milli']=remaining['remaining_milli']
            if user.role in eng.MANAGEMENT:item['remaining_cents']=remaining['remaining_cents']
        info['movements'].append(item)
    role=role_for_store(db,user,sid)
    actions=[]
    if row.status in {'requested','approved'}:
        approved=row.source_approved_by if source else row.destination_approved_by
        if role in {'admin','manager'} and not approved:actions+=['approve','reject_request']
        if source and role in WRITE_ROLES and (user.id==row.requested_by or role in {'admin','manager'}):actions+=['cancel']
        if source and row.status=='approved' and role in {'admin','inventory'}:actions+=['dispatch']
    if row.status=='transit' and role in {'admin','inventory'}:
        actions+=['return_receive'] if source else ['receive','return_ship']
    info['actions']=[] if active or active_found else actions
    return info


def list_transfers(db,user):
    with authority(db,user) as sid:
        rows=list(db.scalars(select(MaterialTransfer).where(or_(MaterialTransfer.from_store_id==sid,MaterialTransfer.to_store_id==sid)).order_by(MaterialTransfer.id.desc()).limit(501)))
        if len(rows)>500:raise HTTPException(413,'调拨记录超过500条，请先按期间归档后使用明细查询')
        return {'items':[serialize(db,user,row,sid) for row in rows]}


def transfer_detail(db,user,key):
    with authority(db,user) as sid:return serialize(db,user,get_transfer(db,key,sid),sid)


def destinations(db,user):
    with authority(db,user,WRITE_ROLES) as sid:
        # Store names identify transfer counterparties; this grants no access to business.
        return {'items':[{'id':s.id,'name':s.name} for s in db.scalars(select(Store).where(Store.active.is_(True),Store.id!=sid).order_by(Store.id))]}


def execute(db,user,key,action,payload,operation):
    with authority(db,user,WRITE_ROLES) as sid:
        digest=hashlib.sha256(json.dumps([action,payload],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        try:
            old=db.scalar(select(TransferReceipt).where(TransferReceipt.request_key==key))
            if old:
                if old.actor_id!=user.id or old.digest!=digest:raise HTTPException(409,'请求编号已被其他操作使用')
                result=json.loads(json.dumps(old.result))
                if user.role not in eng.MANAGEMENT:
                    for line in result.get('lines',[]):
                        for field in list(line):
                            if field.endswith('_cents'):line.pop(field)
                    for move in result.get('movements',[]):
                        for field in list(move):
                            if field.endswith('_cents'):move.pop(field)
                return result
            result=operation(sid)
            db.add(TransferReceipt(store_id=sid,request_key=key,actor_id=user.id,digest=digest,result=result))
            db.commit()
            return result
        except (IntegrityError,OperationalError,StaleDataError):
            db.rollback();raise HTTPException(409,'调拨或库存已变化，请刷新核对；保留原请求编号查询结果')
        except Exception:
            db.rollback();raise


def create_transfer(db,user,request_id,destination_store_id,reason,due_date,lines):
    payload=dict(destination_store_id=destination_store_id,reason=reason,due_date=due_date,lines=lines)
    def operation(sid):
        if destination_store_id==sid or not db.scalar(select(Store.id).where(Store.id==destination_store_id,Store.active.is_(True))):
            raise HTTPException(422,'请选择另一家启用门店')
        if len({line['item_id'] for line in lines})!=len(lines):raise HTTPException(422,'同一物资请合并为一行')
        items=[]
        for line in lines:
            item=eng.scoped_get(db,Item,line['item_id'])
            if not item or not item.active:raise HTTPException(422,'调出物资不存在或已停用')
            if line['quantity_milli']>item.quantity_milli:raise HTTPException(409,'申请数量超过当前账面库存')
            items.append((item,line['quantity_milli']))
        number='HKT'+uuid.uuid4().hex[:16].upper()
        cases={}
        for party in (sid,destination_store_id):
            with coordination_scope(db,party,(sid,destination_store_id)):
                managers=eng.eligible_users(db,'manager',party)
                if not managers:raise HTTPException(409,'调拨门店未配置主管，请先配置接手岗位')
                case=Case(number=number+('-OUT' if party==sid else '-IN'),kind='material_transfer',flow_version=NEW_TRANSFER_VERSION,
                    state='approval',title='物资调拨 · '+('调出' if party==sid else '调入'),owner_id=managers[0].id,
                    created_by=user.id,amount_cents=0,business_date=today(),due_date=date.fromisoformat(due_date),data={})
                db.add(case);entities.note_coordinated_case(db,user,case);db.flush();eng.ensure_task(db,case,'transfer_approve','确认本店调拨安排','manager')
                eng.log_event(db,user,case,'transfer_request','收到物资调拨申请',detail={'number':number})
                cases[party]=case.id
        row=MaterialTransfer(number=number,from_store_id=sid,to_store_id=destination_store_id,
            from_case_id=cases[sid],to_case_id=cases[destination_store_id],requested_by=user.id,reason=reason,due_date=date.fromisoformat(due_date))
        db.add(row);db.flush()
        for item,qty in items:db.add(TransferLine(transfer_id=row.id,source_item_id=item.id,sku=item.sku,name=item.name,unit=item.unit,quantity_milli=qty))
        db.flush()
        for party,cid in cases.items():
            with coordination_scope(db,party,(sid,destination_store_id)):
                own=eng.scoped_get(db,Case,cid);own.data={'transfer_id':row.id}
                entities.freeze_coordinated_case(db,user,own,row)
        return serialize(db,user,row,sid)
    return execute(db,user,request_id,'create',payload,operation)


def assert_task(db,user,case,key):
    task=db.scalar(select(Task).where(Task.case_id==case.id,Task.key==key,Task.status=='open'))
    if not task or (user.role!='admin' and task.assignee_id!=user.id):raise HTTPException(403,'请由当前待办负责人办理，主管可先转交任务')


def evidence(db,user,case,key):
    from .flow_documents import can_file
    asset=eng.file_exists(db,case,key)
    if not can_file(user,case,asset):raise HTTPException(403,'当前岗位不能使用此凭据')
    return asset


def posting(db,user,case,item,qty,value,purpose,original=None):
    if qty<0:
        from .inventory_availability import assert_can_issue
        assert_can_issue(db,item,-qty)
    if qty<0 and (item.quantity_milli < -qty or item.inventory_value_cents < -value):raise HTTPException(409,'当前库存不足，调拨未过账')
    item.quantity_milli+=qty;item.inventory_value_cents+=value
    item.unit_cost_cents=item.inventory_value_cents*1000//item.quantity_milli if item.quantity_milli else 0
    item.updated_at=utcnow()
    move=StockMove(case_id=case.id,item_id=item.id,quantity_milli=qty,value_cents=value,unit_cost_cents=abs(value)*1000//abs(qty),
        purpose=purpose,actor_id=user.id,business_date=today(),original_id=original)
    db.add(move);db.flush()
    from .warehouse_stock import after_stock_move
    after_stock_move(db,user,case,item,move)
    return move


def movement(db,user,row,line,kind,qty,value,evidence_id,stock_move_id=None,original_id=None,reason=''):
    result=TransferMovement(transfer_id=row.id,line_id=line.id,store_id=single_store(db),kind=kind,quantity_milli=qty,value_cents=value,
        evidence_id=evidence_id,actor_id=user.id,business_date=today(),stock_move_id=stock_move_id,original_id=original_id,reason=reason)
    db.add(result);db.flush();return result


def synchronize(db,user,row,action,reason):
    parties=(row.from_store_id,row.to_store_id)
    for sid,cid in ((row.from_store_id,row.from_case_id),(row.to_store_id,row.to_case_id)):
        with coordination_scope(db,sid,parties):
            case=eng.scoped_get(db,Case,cid)
            case.updated_at=utcnow()
            case.state={'requested':'approval','approved':'pending','transit':'working','completed':'completed','cancelled':'cancelled'}[row.status]
            if row.status in {'completed','cancelled'}:
                case.completed_date=today();eng.close_tasks(db,case,user)
            elif row.status=='approved':
                eng.finish_task(db,case,'transfer_approve',user)
                if sid==row.from_store_id:eng.ensure_task(db,case,'transfer_dispatch','核对实物并发出调拨','inventory')
            elif row.status=='transit':
                eng.finish_task(db,case,'transfer_dispatch',user)
                if sid==row.to_store_id:eng.ensure_task(db,case,'transfer_receive','验收物资并处理拒收退回','inventory')
            eng.log_event(db,user,case,'transfer_'+action,'物资调拨：'+LABELS[row.status],detail={'transfer_id':row.id,'reason':reason})


def command(db,user,key,request_id,version,case_version,action,values):
    def operation(sid):
        row=get_transfer(db,key,sid);case=local_case(db,user,row,sid)
        if row.version!=version or case.version!=case_version:raise HTTPException(409,'调拨已被其他人办理，请刷新核对后再操作')
        modern=case.flow_version==3
        if modern:
            from . import transfer_exception_service as exceptions
            # Every third-version command shares this CAS/row lock with loss
            # investigations. Read remaining quantity only after the touch.
            row=db.scalar(select(MaterialTransfer).where(MaterialTransfer.id==row.id).with_for_update())
            row.updated_at=utcnow();case.updated_at=utcnow();db.flush()
            exceptions.guard_transfer_command(db,user,row,action)
        source=sid==row.from_store_id
        role=role_for_store(db,user,sid)
        if action in {'approve','reject_request'}:
            if role not in {'admin','manager'}:raise HTTPException(403,'调拨安排需要本店主管批准')
            assert_task(db,user,case,'transfer_approve')
            if row.status not in {'requested','approved'}:raise HTTPException(409,'已发出调拨不能取消审批')
            if user.id==row.requested_by and role!='admin':raise HTTPException(403,'申请人不能自行批准调拨')
            if action=='reject_request':row.status='cancelled'
            else:
                if source:
                    if row.source_approved_by:raise HTTPException(409,'调出方已批准')
                    row.source_approved_by=user.id
                else:
                    if row.destination_approved_by:raise HTTPException(409,'调入方已批准')
                    row.destination_approved_by=user.id
                eng.finish_task(db,case,'transfer_approve',user)
                if row.source_approved_by and row.destination_approved_by:row.status='approved'
        elif action=='cancel':
            if not source or (user.id!=row.requested_by and role not in {'admin','manager'}):raise HTTPException(403,'仅调出方申请人或主管可撤销')
            if row.status not in {'requested','approved'}:raise HTTPException(409,'已发出物资请办理拒收及退回，不得取消账目')
            row.status='cancelled'
        else:
            if role not in {'admin','inventory'}:raise HTTPException(403,'实物交接由本店库管确认')
            evidence(db,user,case,values['evidence_id'])
            lines={line.id:line for line in lines_for(db,row)}
            moves=movements_for(db,row)
            if action=='dispatch':
                if not source or row.status!='approved':raise HTTPException(409,'双方批准后由调出方发货')
                assert_task(db,user,case,'transfer_dispatch')
                for line in lines.values():
                    item=eng.scoped_get(db,Item,line.source_item_id)
                    if not item or not item.active or item.unit!=line.unit or item.sku!=line.sku or item.name!=line.name:raise HTTPException(409,'物资档案已变化，请取消并重新核对调拨')
                    if item.quantity_milli<line.quantity_milli:raise HTTPException(409,'可发库存不足，未发出任何一行')
                    value=item.inventory_value_cents*line.quantity_milli//item.quantity_milli
                    stock=posting(db,user,case,item,-line.quantity_milli,-value,'transfer_out')
                    movement(db,user,row,line,'dispatch',line.quantity_milli,value,values['evidence_id'],stock.id)
                row.status='transit'
            elif action=='receive':
                if source or row.status!='transit':raise HTTPException(409,'仅调入方可验收在途物资')
                assert_task(db,user,case,'transfer_receive')
                if len({v['line_id'] for v in values['lines']})!=len(values['lines']):raise HTTPException(422,'验收行不能重复')
                for receive in values['lines']:
                    line=lines.get(receive['line_id'])
                    if not line:raise HTTPException(422,'验收行不属于本次调拨')
                    dispatch=next((m for m in moves if m.line_id==line.id and m.kind=='dispatch'),None)
                    if not dispatch:raise HTTPException(409,'该物资尚未发出')
                    handled=sum(m.quantity_milli for m in moves if m.line_id==line.id and m.kind in {'accept','reject'})
                    accepted,rejected=receive['accept_milli'],receive['reject_milli']
                    remaining=exceptions.bucket_remaining(db,row,dispatch)['remaining_milli'] if modern else line.quantity_milli-handled
                    if accepted+rejected<=0 or accepted+rejected>remaining:raise HTTPException(409,'验收数量超过未验收在途数量')
                    for kind,qty in (('accept',accepted),('reject',rejected)):
                        if not qty:continue
                        value=exceptions.portion(db,row,dispatch,qty) if modern else (handled+qty)*dispatch.value_cents//line.quantity_milli-handled*dispatch.value_cents//line.quantity_milli
                        handled+=qty;stock=None
                        if kind=='accept':
                            item=eng.scoped_get(db,Item,receive.get('item_id')) if receive.get('item_id') else None
                            if not item or not item.active or item.name!=line.name or item.unit!=line.unit:raise HTTPException(422,'请选择本店已启用、名称和单位一致的接收物资档案')
                            stock=posting(db,user,case,item,qty,value,'transfer_in')
                        accepted_move=movement(db,user,row,line,kind,qty,value,values['evidence_id'],stock.id if stock else None,dispatch.id,values['reason'])
                        if kind=='accept':
                            for party,other,amount in ((row.from_store_id,row.to_store_id,value),(row.to_store_id,row.from_store_id,-value)):
                                with coordination_scope(db,party,(row.from_store_id,row.to_store_id)):
                                    db.add(TransferSettlement(store_id=party,transfer_id=row.id,movement_id=accepted_move.id,counterparty_store_id=other,amount_cents=amount))
            elif action=='return_ship':
                if source or row.status!='transit':raise HTTPException(409,'拒收物资由调入方确认退回发运')
                assert_task(db,user,case,'transfer_receive')
                original=next((m for m in moves if m.id==values['rejection_id'] and m.kind=='reject'),None)
                if not original or (not modern and any(m.kind=='return_ship' and m.original_id==original.id for m in moves)):raise HTTPException(409,'拒收记录不存在或已安排退回')
                left=exceptions.bucket_remaining(db,row,original) if modern else {'remaining_milli':original.quantity_milli,'remaining_cents':original.value_cents}
                if left['remaining_milli']<=0:raise HTTPException(409,'本拒收批次已退运或已按真实差异结清，不能再次发出')
                movement(db,user,row,lines[original.line_id],'return_ship',left['remaining_milli'],left['remaining_cents'],values['evidence_id'],original_id=original.id,reason=values['reason'])
                with coordination_scope(db,row.from_store_id,(row.from_store_id,row.to_store_id)):
                    source_case=eng.scoped_get(db,Case,row.from_case_id)
                    eng.ensure_task(db,source_case,'transfer_return','接收拒收退回物资','inventory',reopen=True)
            elif action=='return_receive':
                if not source or row.status!='transit':raise HTTPException(409,'退回物资由原调出方确认入库')
                if modern and values.get('passed') is not True:raise HTTPException(409,'退回物资须实际核对质量合格才能入库；坏件请按退回发运批次提交运输差异')
                assert_task(db,user,case,'transfer_return')
                shipment=next((m for m in moves if m.id==values['shipment_id'] and m.kind=='return_ship'),None)
                if not shipment:raise HTTPException(404,'退回发运记录不存在')
                done=sum(m.quantity_milli for m in moves if m.kind=='return_receive' and m.original_id==shipment.id)
                qty=values['quantity_milli']
                remaining=exceptions.bucket_remaining(db,row,shipment)['remaining_milli'] if modern else shipment.quantity_milli-done
                if qty>remaining:raise HTTPException(409,'退回验收量超过退回在途量')
                value=exceptions.portion(db,row,shipment,qty) if modern else (done+qty)*shipment.value_cents//shipment.quantity_milli-done*shipment.value_cents//shipment.quantity_milli
                line=lines[shipment.line_id];item=eng.scoped_get(db,Item,line.source_item_id)
                if not item or item.unit!=line.unit:raise HTTPException(409,'原调出物资档案无法接收退回，请先核对')
                dispatch=next(m for m in moves if m.line_id==line.id and m.kind=='dispatch')
                stock=posting(db,user,case,item,qty,value,'transfer_return',dispatch.stock_move_id)
                movement(db,user,row,line,'return_receive',qty,value,values['evidence_id'],stock.id,shipment.id,values['reason'])
            else:raise HTTPException(404,'调拨动作不存在')
        row.updated_at=utcnow()
        if row.status=='transit':
            allmoves=movements_for(db,row)
            if modern:
                lost=exceptions.loss_totals(db,row);finished=True
                for line in lines_for(db,row):
                    sent=next(m for m in allmoves if m.line_id==line.id and m.kind=='dispatch')
                    done=[m for m in allmoves if m.line_id==line.id and m.kind in {'accept','return_receive'}]
                    qty=sum(m.quantity_milli for m in done)+lost.get(line.id,{}).get('quantity_milli',0)
                    value=sum(m.value_cents for m in done)+lost.get(line.id,{}).get('value_cents',0)
                    if qty>sent.quantity_milli or value>sent.value_cents:raise HTTPException(409,'实际验收、原退与原损失超过发出批次')
                    finished=finished and qty==sent.quantity_milli and value==sent.value_cents
                if finished:row.status='completed'
            elif sum(m.quantity_milli for m in allmoves if m.kind in {'accept','return_receive'})==sum(m.quantity_milli for m in allmoves if m.kind=='dispatch'):
                row.status='completed'
        synchronize(db,user,row,action,values['reason']);db.flush()
        return serialize(db,user,row,sid)
    return execute(db,user,request_id,f'{key}:{action}',dict(version=version,case_version=case_version,values=values),operation)
