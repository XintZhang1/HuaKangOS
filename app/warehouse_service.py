"""Explicit warehouse approval, physical confirmation, original return and count bridge."""
import json,uuid
from contextlib import contextmanager
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select,func,or_
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .flow_models import Case,StockMove,Task,Item
from .master_models import StorageLocation
from .transfer_service import assert_task
from .vehicle_procurement_service import evidence
from . import flow_engine as flow
from . import warehouse_stock as stock
from .warehouse_models import (WarehouseDocument as Document,WarehouseApproval as Approval,WarehouseEnrollment as Enrollment,
    WarehouseBalance as Balance,WarehouseEntry as Entry,WarehouseHold as Hold,WarehouseAllocation as Allocation,
    WarehouseAllocationLine as AllocationLine,WarehouseCountObservation as Observation)

READ={'admin','manager','inventory','finance','auditor'}
MONEY={'admin','manager','finance','auditor'}
MANAGE={'admin','manager'}
PHYSICAL={'admin','inventory'}
NAMES={'activate':'真实库位启用','other_in':'其他物资入库','other_in_return':'原其他入库退回','consumable':'耗材领用','consumable_return':'原耗材领用退回',
    'gift':'礼品发出','gift_return':'原礼品退回','disposal':'其他处置出库','local_move':'店内移库','count':'库位盘点'}
LABELS={'approve':'批准作业','reject':'拒绝申请','cancel':'撤销未执行作业','execute':'确认实际收发','dispatch':'确认实际移出',
    'accept':'确认实际接收','reject_transit':'登记在途拒收','return_transit':'确认实际返回原位','capture':'提交实盘观察','post_count':'批准盘点差异',
    'assign':'交接当前待办','void_observation':'按凭据作废错误实盘观察'}
ROLES={k:(MANAGE if k in {'approve','reject','cancel','post_count','assign','void_observation'} else PHYSICAL) for k in LABELS}
PURPOSES={'other_in':'wh_other_in','other_in_return':'wh_other_return','consumable':'wh_consumable','consumable_return':'wh_consume_return',
    'gift':'wh_gift','gift_return':'wh_gift_return','disposal':'wh_disposal','count':'wh_count'}
EXTERNAL_PURPOSES={'purchase','issue','return','count','procurement_receipt','procurement_return','transfer_out','transfer_in','transfer_return','repair_issue_v3','repair_return_v3','retail_dispatch','retail_return'}
OUT={'other_in_return','consumable','gift','disposal','local_move'}
RETURNS={'other_in_return':'wh_other_in','consumable_return':'wh_consumable','gift_return':'wh_gift'}
RETURN_ORIGINS={'other_in_return':'other_in','consumable_return':'consumable','gift_return':'gift'}
@contextmanager
def authority(db,user,roles):
    from .tenancy import single_store,role_for_store
    from .models import Store
    sid=single_store(db)
    if role_for_store(db,user,sid) not in roles or not db.scalar(select(Store.id).where(Store.id==sid,Store.active.is_(True))):
        raise HTTPException(403,'当前门店岗位不能读取或办理此仓储作业')
    yield sid
def rows(db,model,**kw):return stock.rows(db,model,**kw)
def one(db,model,key):
    row=db.scalar(select(model).where(model.id==key).with_for_update())
    if not row:raise HTTPException(404,'当前门店记录不存在')
    return row
def get_case(db,user,key):
    row=flow.get_case(db,user,key)
    if row.kind!='warehouse' or row.flow_version!=2:raise HTTPException(404,'仓储作业不存在或版本不支持')
    return row,one(db,Document,key)
def task(db,user,row,key):assert_task(db,user,row,key)
def close(db,user,row,state='completed'):
    # Successful handlers finish the task they performed before cancelling leftovers.
    row.state=state;row.completed_date=today();flow.close_tasks(db,row,user)
def digest(action,v):return flow.request_digest(action,json.loads(json.dumps(v,default=str)))
def conflict(db,e):
    db.rollback()
    if isinstance(e,HTTPException):raise e
    raise HTTPException(409,'库存或作业已被其他操作更新，请刷新核对；本次没有部分过账')
def action_keys(row,doc):
    if row.state=='pending':return ['approve','reject','cancel','assign']
    if row.state=='ready':return ['dispatch' if doc.operation=='local_move' else 'execute','cancel','assign']
    if row.state=='counting':return ['capture','cancel','assign']
    if row.state=='review':return ['post_count','void_observation','assign']
    if row.state=='transit':return ['accept','reject_transit','assign']
    if row.state=='returning':return ['return_transit','assign']
    return []

def _return_query(db,user,operation):
    """Only this domain's completed original batches, with actual returns deducted."""
    from .tenancy import single_store
    sid=single_store(db)
    if operation not in RETURNS:raise HTTPException(422,'请选择其他入库、耗材或礼品的原单退回')
    returned=select(StockMove.original_id.label('source_id'),func.sum(func.abs(StockMove.quantity_milli)).label('qty'),
        func.sum(func.abs(StockMove.value_cents)).label('value')).where(StockMove.store_id==sid,StockMove.original_id.is_not(None)).group_by(StockMove.original_id).subquery()
    return select(StockMove,Case,Document,Item,func.coalesce(returned.c.qty,0).label('returned_quantity_milli'),func.coalesce(returned.c.value,0).label('returned_value_cents')).join(
        Case,Case.id==StockMove.case_id).join(Document,Document.id==Case.id).join(Item,Item.id==StockMove.item_id).outerjoin(returned,returned.c.source_id==StockMove.id).where(
        StockMove.store_id==sid,Case.store_id==sid,Document.store_id==sid,Item.store_id==sid,
        Case.kind=='warehouse',Case.flow_version==2,Case.state=='completed',Document.operation==RETURN_ORIGINS[operation],
        Document.item_id==StockMove.item_id,StockMove.purpose==RETURNS[operation],StockMove.original_id.is_(None),
        StockMove.quantity_milli>0 if operation=='other_in_return' else StockMove.quantity_milli<0,
        Case.id.in_(flow.case_query(user).with_only_columns(Case.id)))

def _return_summary(user,operation,entry):
    move,case,doc,item,returned,returned_value=entry
    remaining=abs(move.quantity_milli)-returned
    result={'original_move_id':move.id,'source_case_id':case.id,'source_number':case.number,'business_date':move.business_date,
        'operation':operation,'item_id':item.id,'item_name':item.name,'sku':item.sku,'unit':item.unit,
        'original_quantity_milli':abs(move.quantity_milli),'returned_quantity_milli':returned,'remaining_quantity_milli':remaining,
        'can_return':user.role in PHYSICAL and item.active and remaining>0}
    if user.role in MONEY:result.update(original_value_cents=abs(move.value_cents),returned_value_cents=returned_value,remaining_value_cents=abs(move.value_cents)-returned_value)
    return result

def return_sources(db,user,operation,q='',original_move_id=None,page=1,page_size=30):
    with authority(db,user,READ):
        query=_return_query(db,user,operation)
        if original_move_id is not None:query=query.where(StockMove.id==original_move_id)
        else:
            query=query.where(Item.active.is_(True),func.abs(StockMove.quantity_milli)>query.selected_columns.returned_quantity_milli,
                Item.id.in_(select(Enrollment.item_id)))
        if q.strip():query=query.where(or_(Item.name.contains(q.strip(),autoescape=True),Item.sku.contains(q.strip(),autoescape=True),Case.number.contains(q.strip(),autoescape=True)))
        total=db.scalar(select(func.count()).select_from(query.subquery()))
        entries=list(db.execute(query.order_by(StockMove.business_date.desc(),StockMove.id.desc()).offset((page-1)*page_size).limit(page_size)))
        if original_move_id is not None and not entries:raise HTTPException(404,'未找到该原批次，请从对应作业重新选择')
        return {'items':[_return_summary(user,operation,entry) for entry in entries],'total':total,'page':page,'page_size':page_size}

def _verified_return_source(db,user,operation,original_id,item_id):
    entry=db.execute(_return_query(db,user,operation).where(StockMove.id==original_id,StockMove.item_id==item_id)).first()
    if not entry:raise HTTPException(422,'请选择同一物资已完成的对应原仓储批次')
    return entry
def describe(db,user,row):
    d=one(db,Document,row.id);item=one(db,Item,d.item_id);money=user.role in MONEY
    result={k:getattr(row,k) for k in ['id','number','state','version','store_id','business_date','due_date']}
    result.update({k:getattr(d,k) for k in ['operation','item_id','quantity_milli','source_location_id','destination_location_id','original_move_id','reason','recipient']})
    result.update(operation_label=NAMES[d.operation],item_name=item.name,unit=item.unit,can_money=money,
        actions=[{'key':k,'label':LABELS[k]} for k in action_keys(row,d) if user.role in ROLES[k]])
    result['stock_moves']=[]
    for m in rows(db,StockMove,case_id=row.id):
        record={'id':m.id,'quantity_milli':m.quantity_milli,'purpose':m.purpose,'original_id':m.original_id,'business_date':m.business_date,**({'value_cents':m.value_cents} if money else {})}
        operation=next((op for op,purpose in RETURNS.items() if purpose==m.purpose),None)
        if operation:
            entry=db.execute(_return_query(db,user,operation).where(StockMove.id==m.id)).first()
            if entry:
                source=_return_summary(user,operation,entry);record['return_source']=source
                record.update(return_operation=operation,returnable_milli=source['remaining_quantity_milli'],returned_milli=source['returned_quantity_milli'],can_return=source['can_return'])
        result['stock_moves'].append(record)
    result['transit_quantity_milli']=sum(b.quantity_milli for b in rows(db,Balance,transit_case_id=row.id))
    ob=db.scalar(select(Observation).where(Observation.case_id==row.id))
    if ob:
        bridge=[e for e in rows(db,Entry,balance_id=ob.balance_id) if e.id>ob.entry_cursor and e.case_id!=row.id]
        b=one(db,Balance,ob.balance_id)
        result['count']={'baseline_quantity_milli':ob.baseline_quantity_milli,'counted_quantity_milli':ob.counted_quantity_milli,
            'difference_milli':ob.counted_quantity_milli-ob.baseline_quantity_milli,'movement_bridge_milli':sum(e.quantity_milli for e in bridge),
            'current_book_milli':b.quantity_milli,'projected_milli':ob.counted_quantity_milli+sum(e.quantity_milli for e in bridge),
            'entries':[{'id':e.id,'case_id':e.case_id,'quantity_milli':e.quantity_milli,'reason':e.reason} for e in bridge]}
    approval=db.scalar(select(Approval).where(Approval.case_id==row.id))
    if approval and money and d.operation=='other_in':result['approved_value_cents']=approval.value_cents
    return result

def stock_view(db,user,key,include_entries=True):
    item=stock.item_lock(db,key);enrollment=stock.enrolled(db,key);money=user.role in MONEY
    from .inventory_availability import available_quantity,reserved_quantity
    balances=rows(db,Balance,item_id=key);locs={l.id:l for l in rows(db,StorageLocation)}
    result={'id':key,'name':item.name,'sku':item.sku,'unit':item.unit,'version':item.version,'enabled':bool(enrollment),
        'quantity_milli':item.quantity_milli,'available_milli':available_quantity(db,item),'reserved_milli':reserved_quantity(db,key),
        'balances':[{'id':b.id,'version':b.version,'location_id':b.location_id,'location_name':locs[b.location_id].name if b.location_id in locs else '店内移库在途',
            'transit_case_id':b.transit_case_id,'quantity_milli':b.quantity_milli,**({'value_cents':b.value_cents} if money else {})} for b in balances]}
    result.update(item_active=item.active,location_ledger_enabled=result['enabled'],
        field_notes={'enabled':'兼容字段：是否已核对并启用真实库位账，与 location_ledger_enabled 相同；不是物资档案启用状态。',
            'location_ledger_enabled':'是否已核对并启用真实库位账；未启用不表示物资档案停用。',
            'item_active':'物资档案是否启用，来自原物资 active。'})
    if money:result['value_cents']=item.inventory_value_cents
    if include_entries:
        entries=list(db.scalars(select(Entry).join(Balance,Balance.id==Entry.balance_id).where(Balance.item_id==key).order_by(Entry.id).limit(50001)))
        if len(entries)>50000:raise HTTPException(413,'单项库位流水超过本版五万条明细上限，请由管理员导出完整账本核对，未返回截断合计')
        result['entries']=[{'id':e.id,'balance_id':e.balance_id,'case_id':e.case_id,'stock_move_id':e.stock_move_id,'quantity_milli':e.quantity_milli,
            'reason':e.reason,'business_date':e.business_date,**({'value_cents':e.value_cents} if money else {})} for e in entries]
    return result

def create(db,user,key,v):
    try:
        with authority(db,user,PHYSICAL):
            fp=digest('warehouse_create',v);prior=flow.prior_request(db,user,key,fp)
            if prior:return describe(db,user,prior)
            item=stock.item_lock(db,v['item_id']);op=v['operation']
            if not item.active:raise HTTPException(409,'物资已停用')
            if op not in NAMES:raise HTTPException(422,'仓储作业类型不存在')
            qty=v['quantity_milli'];src=v.get('source_location_id');dest=v.get('destination_location_id');original=v.get('original_move_id')
            if op!='activate' and not stock.enrolled(db,item.id):raise HTTPException(409,'请先逐项核对并启用真实库位')
            if op=='activate':
                if stock.enrolled(db,item.id):raise HTTPException(409,'此物资已启用，改位置请办理移库')
                stock.reconcile_source(db,item)
                if qty!=item.quantity_milli:raise HTTPException(409,'启用数量须与当前已对平的门店库存一致，请刷新')
                if src or dest or original:raise HTTPException(422,'启用使用逐库位分配，不关联原收发或单一出入库位')
            elif op=='count':
                if qty or not src or dest or original:raise HTTPException(422,'盘点须指定一个实际库位，申请数量填零；实盘结果在现场提交')
                if any(d.source_location_id==src for _,d,_ in stock.count_rows(db,item.id)):raise HTTPException(409,'该物资库位已有未处理盘点')
            else:
                if qty<=0:raise HTTPException(422,'实际作业数量须大于零')
                if op in OUT and not src:raise HTTPException(422,'出库或移库须明确原库位')
                if op not in OUT and not dest:raise HTTPException(422,'入库须明确接收库位')
                if op=='local_move' and (not dest or src==dest):raise HTTPException(422,'移库须选择不同的出发和接收库位')
                if op!='local_move' and src and dest:raise HTTPException(422,'单向收发不同时填写出发和接收库位')
                if op in {'consumable','gift'} and not v.get('recipient'):raise HTTPException(422,'领用或礼品出库须记录实际领取人／班组')
                if op in RETURNS:
                    move=one(db,StockMove,original or 0)
                    if move.item_id!=item.id or move.purpose!=RETURNS[op]:raise HTTPException(422,'只能退回同一物资对应作业的原始收发')
                    _verified_return_source(db,user,op,move.id,item.id)
                    remaining=abs(move.quantity_milli)-sum(abs(m.quantity_milli) for m in rows(db,StockMove,original_id=move.id))
                    if qty>remaining:raise HTTPException(409,'退回数量超过原始收发尚未退回的数量')
                elif original:raise HTTPException(422,'此作业不能指定原收发记录')
            for loc in [src,dest]:
                if loc:stock.location(db,loc)
            row=Case(number='WH-'+uuid.uuid4().hex[:16],kind='warehouse',flow_version=2,state='pending',title=NAMES[op]+' · '+item.name,
                owner_id=user.id,created_by=user.id,business_date=today(),due_date=v['due_date'],data={'operation':op,'item_id':item.id})
            db.add(row);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row);db.add(Document(id=row.id,operation=op,item_id=item.id,quantity_milli=qty,source_location_id=src,destination_location_id=dest,
                original_move_id=original,reason=v['reason'],recipient=v.get('recipient',''),baseline_quantity_milli=item.quantity_milli,
                baseline_value_cents=item.inventory_value_cents,baseline_item_version=item.version))
            if op=='activate':stock.prepare(db,user,row,item,qty,'activation',v.get('locations',[]))
            elif v.get('locations'):raise HTTPException(422,'仅库位启用可提交分配清单')
            flow.ensure_task(db,row,'wh_approve','复核'+NAMES[op],'manager',due=row.due_date)
            flow.log_event(db,user,row,'warehouse_create','申请'+NAMES[op],'',{'item_id':item.id,'quantity_milli':qty})
            flow.save_receipt(db,user,key,fp,row);db.commit();return describe(db,user,row)
    except (HTTPException,IntegrityError,OperationalError,StaleDataError) as e:conflict(db,e)

def release(db,user,row,doc):
    qty=stock.held(db,doc.item_id,doc.source_location_id,exclude=None) if doc.source_location_id else 0
    own=sum(h.quantity_milli for h in rows(db,Hold,case_id=row.id))
    if own:db.add(Hold(case_id=row.id,item_id=doc.item_id,location_id=doc.source_location_id,quantity_milli=-own,reason='release',actor_id=user.id))
def portion(value,qty,remaining):return value if qty==remaining else (2*value*qty+remaining)//(2*remaining)
def post(db,user,row,item,qty,value,purpose,loc,original=None):
    if qty<0:
        from .inventory_availability import assert_can_issue
        assert_can_issue(db,item,-qty)
    if item.quantity_milli+qty<0 or item.inventory_value_cents+value<0 or (item.quantity_milli+qty==0 and item.inventory_value_cents+value!=0):
        raise HTTPException(409,'原单价值与当前库存不能对平，不能留下负值或无数量库存价值')
    stock.prepare(db,user,row,item,qty,purpose,[{'location_id':loc,'quantity_milli':abs(qty)}])
    item.quantity_milli+=qty;item.inventory_value_cents+=value
    item.unit_cost_cents=(2*item.inventory_value_cents*1000+item.quantity_milli)//(2*item.quantity_milli) if item.quantity_milli else 0
    item.updated_at=utcnow();move=StockMove(case_id=row.id,item_id=item.id,quantity_milli=qty,value_cents=value,unit_cost_cents=abs(value)*1000//abs(qty) if qty else 0,
        purpose=purpose,actor_id=user.id,business_date=today(),original_id=original)
    db.add(move);db.flush();stock.after_stock_move(db,user,row,item,move);return move

def command(db,user,case_id,key,version,action,v):
    try:
        with authority(db,user,ROLES.get(action,set())):
            fp=digest('warehouse_'+action,{'id':case_id,'version':version,**v});prior=flow.prior_request(db,user,key,fp)
            if prior:return describe(db,user,prior)
            row,doc=get_case(db,user,case_id)
            if row.version!=version:raise HTTPException(409,'作业已更新，请刷新后办理；本次没有覆盖他人记录')
            if action not in action_keys(row,doc):raise HTTPException(409,'当前作业状态不能执行此动作')
            item=stock.item_lock(db,doc.item_id);before=row.state;row.updated_at=utcnow()
            with stock.own_claim(db,row):
                _act(db,user,row,doc,item,action,v)
            # Item version also serializes reservations, bin fences and allocation consumption.
            item.updated_at=utcnow();db.flush()
            flow.log_event(db,user,row,'warehouse_'+action,LABELS[action],before,json.loads(json.dumps({k:x for k,x in v.items() if k not in {'value_cents'}},default=str)))
            flow.save_receipt(db,user,key,fp,row);db.commit();return describe(db,user,row)
    except (HTTPException,IntegrityError,OperationalError,StaleDataError) as e:conflict(db,e)

def _act(db,user,row,doc,item,action,v):
    op=doc.operation
    if action=='assign':
        t=one(db,Task,v['task_id'])
        if t.case_id!=row.id or t.status!='open':raise HTTPException(409,'只能交接本单未完成待办')
        u=flow.assignable(db,v['assignee_id'],row.store_id,{t.role});t.assignee_id=u.id;t.due_date=v['due_date'];return
    if action in {'cancel','reject'}:
        if action=='reject':task(db,user,row,'wh_approve')
        release(db,user,row,doc);close(db,user,row,'rejected' if action=='reject' else 'cancelled');return
    if action=='void_observation':
        task(db,user,row,'wh_count_review');evidence(db,user,row,v['evidence_id'])
        # Incorrect observations stay immutable. Explicit supervisor invalidation
        # releases their restriction; it never changes actual stock or old facts.
        close(db,user,row,'cancelled');return
    if action=='approve':
        task(db,user,row,'wh_approve');e=evidence(db,user,row,v['evidence_id'],financial=op=='other_in')
        if op=='other_in' and v.get('value_cents') is None:raise HTTPException(422,'其他入库须主管根据来源凭据明确批准总价值（整数分）')
        if op!='other_in' and v.get('value_cents') is not None:raise HTTPException(422,'本作业成本来自原始账，不能手工指定')
        db.add(Approval(case_id=row.id,value_cents=v.get('value_cents') or 0,evidence_id=e.id,actor_id=user.id))
        flow.finish_task(db,row,'wh_approve',user)
        if op=='activate':
            if stock.enrolled(db,item.id):raise HTTPException(409,'物资已启用')
            if (item.quantity_milli,item.inventory_value_cents,item.version)!=(doc.baseline_quantity_milli,doc.baseline_value_cents,doc.baseline_item_version):
                raise HTTPException(409,'申请后库存发生变化，请撤销旧启用申请并重新核对')
            cursor=stock.reconcile_source(db,item);a=rows(db,Allocation,case_id=row.id,purpose='activation',status='prepared')[0];changes={}
            for line in rows(db,AllocationLine,allocation_id=a.id):
                stock.location(db,line.location_id);b=stock.balance(db,item.id,line.location_id);changes[b.id]=line.quantity_milli
            if not changes:raise HTTPException(422,'零库存也须明确至少一个实际接收库位')
            db.add(Enrollment(item_id=item.id,case_id=row.id,baseline_quantity_milli=item.quantity_milli,baseline_value_cents=item.inventory_value_cents,stock_move_cursor=cursor,actor_id=user.id))
            stock.rebalance(db,user,row,item,changes,'activation');a.status='consumed';close(db,user,row);return
        if op in OUT:
            from .inventory_availability import assert_can_issue
            assert_can_issue(db,item,doc.quantity_milli);stock.assert_bin(db,item.id,doc.source_location_id,doc.quantity_milli)
            db.add(Hold(case_id=row.id,item_id=item.id,location_id=doc.source_location_id,quantity_milli=doc.quantity_milli,reason='reserve',actor_id=user.id))
        if op=='count':
            if any(c.id!=row.id and d.source_location_id==doc.source_location_id for c,d,_ in stock.count_rows(db,item.id)):raise HTTPException(409,'该库位已有进行中盘点')
            b=stock.balance(db,item.id,doc.source_location_id)
            if stock.held(db,item.id,doc.source_location_id):raise HTTPException(409,'该库位有已批准的出库或移库，请先实际办理或撤销后实盘')
            flow.set_data(row,count_baseline_qty=b.quantity_milli,count_cursor=db.scalar(select(func.coalesce(func.max(Entry.id),0)).where(Entry.balance_id==b.id)))
            row.state='counting';flow.ensure_task(db,row,'wh_capture','现场清点并提交观察','inventory',due=row.due_date)
        else:
            row.state='ready';flow.ensure_task(db,row,'wh_execute','确认'+('实际移出' if op=='local_move' else '实际收发'),'inventory',due=row.due_date)
        return
    if action=='capture':
        task(db,user,row,'wh_capture');e=evidence(db,user,row,v['evidence_id']);b=stock.balance(db,item.id,doc.source_location_id)
        db.add(Observation(case_id=row.id,balance_id=b.id,baseline_quantity_milli=row.data['count_baseline_qty'],counted_quantity_milli=v['counted_quantity_milli'],
            entry_cursor=row.data['count_cursor'],evidence_id=e.id,actor_id=user.id))
        row.state='review';flow.finish_task(db,row,'wh_capture',user);flow.ensure_task(db,row,'wh_count_review','复核实盘差异与期间收发','manager',due=row.due_date);return
    if action=='post_count':
        task(db,user,row,'wh_count_review');evidence(db,user,row,v['evidence_id']);ob=db.scalar(select(Observation).where(Observation.case_id==row.id));delta=ob.counted_quantity_milli-ob.baseline_quantity_milli
        if delta:
            if delta<0:
                from .inventory_availability import assert_can_issue
                assert_can_issue(db,item,-delta);stock.assert_bin(db,item.id,doc.source_location_id,-delta)
            value=portion(item.inventory_value_cents,abs(delta),item.quantity_milli) if delta<0 else (item.unit_cost_cents*delta*2+1000)//2000
            if delta>0 and not item.quantity_milli:raise HTTPException(409,'零库存盘盈缺少可靠成本，请保留观察并先办理有来源价值的其他入库，不能猜测成本')
            post(db,user,row,item,delta,value if delta>0 else -value,'wh_count',doc.source_location_id)
        flow.finish_task(db,row,'wh_count_review',user);close(db,user,row);return
    if action=='execute':
        task(db,user,row,'wh_execute');evidence(db,user,row,v['evidence_id']);qty=doc.quantity_milli*(-1 if op in OUT else 1)
        if op in RETURNS:
            original=one(db,StockMove,doc.original_move_id);previous=rows(db,StockMove,original_id=original.id)
            _verified_return_source(db,user,op,original.id,item.id)
            remaining=abs(original.quantity_milli)-sum(abs(x.quantity_milli) for x in previous);remaining_value=abs(original.value_cents)-sum(abs(x.value_cents) for x in previous)
            if abs(qty)>remaining:raise HTTPException(409,'原收发已被其他退回使用，当前数量超过可退余量')
            value=portion(remaining_value,abs(qty),remaining)
        elif op=='other_in':value=db.scalar(select(Approval.value_cents).where(Approval.case_id==row.id))
        else:value=portion(item.inventory_value_cents,abs(qty),item.quantity_milli)
        post(db,user,row,item,qty,value if qty>0 else -value,PURPOSES[op],doc.source_location_id if qty<0 else doc.destination_location_id,doc.original_move_id)
        release(db,user,row,doc);flow.finish_task(db,row,'wh_execute',user);close(db,user,row);return
    if action=='dispatch':
        task(db,user,row,'wh_execute');evidence(db,user,row,v['evidence_id'])
        from .inventory_availability import assert_can_issue
        assert_can_issue(db,item,doc.quantity_milli);src=stock.assert_bin(db,item.id,doc.source_location_id,doc.quantity_milli);transit=stock.balance(db,item.id,transit_case_id=row.id)
        stock.rebalance(db,user,row,item,{src.id:-doc.quantity_milli,transit.id:doc.quantity_milli},'local_dispatch');release(db,user,row,doc)
        row.state='transit';flow.finish_task(db,row,'wh_execute',user);flow.ensure_task(db,row,'wh_accept','实际接收移库物资或登记拒收','inventory',due=row.due_date);return
    if action=='reject_transit':
        task(db,user,row,'wh_accept');evidence(db,user,row,v['evidence_id']);row.state='returning';flow.finish_task(db,row,'wh_accept',user)
        flow.ensure_task(db,row,'wh_transit_return','确认在途物资实际返回原位','inventory',due=row.due_date);return
    if action in {'accept','return_transit'}:
        task(db,user,row,'wh_accept' if action=='accept' else 'wh_transit_return');evidence(db,user,row,v['evidence_id']);transit=stock.balance(db,item.id,transit_case_id=row.id);qty=v['quantity_milli']
        if qty>transit.quantity_milli:raise HTTPException(409,'数量超过本次尚在途数量')
        dest=stock.assert_bin(db,item.id,doc.destination_location_id if action=='accept' else doc.source_location_id,0)
        stock.rebalance(db,user,row,item,{transit.id:-qty,dest.id:qty},'local_accept' if action=='accept' else 'local_return')
        if not transit.quantity_milli:
            flow.finish_task(db,row,'wh_accept' if action=='accept' else 'wh_transit_return',user);close(db,user,row)
        return
    raise HTTPException(404,'仓储动作不存在')

def prepare_external(db,user,case_id,key,version,v):
    try:
        with authority(db,user,PHYSICAL):
            fp=digest('warehouse_allocation',{'id':case_id,'version':version,**v});prior=flow.prior_request(db,user,key,fp)
            row=flow.get_case(db,user,case_id)
            if prior:return {'case_id':row.id,'version':row.version,'prepared':True}
            if row.version!=version:raise HTTPException(409,'原单已更新，请刷新后再准备库位')
            options=allocation_options(db,user,case_id)
            if v['item_id'] not in {x['id'] for x in options['items']} or v['purpose'] not in options['purposes']:
                raise HTTPException(422,'库位分配必须属于本原单相关物资与允许收发动作')
            sign=1 if v['purpose'] in {'purchase','return','procurement_receipt','transfer_in','transfer_return','repair_return_v3','retail_return','addon_return_v3'} else -1
            if not v['quantity_milli'] or (v['purpose']!='count' and v['quantity_milli']*sign<=0):raise HTTPException(422,'入库填正数量，出库填负数量；不能用分配改变原业务收发方向')
            item=stock.item_lock(db,v['item_id'])
            stock.prepare(db,user,row,item,v['quantity_milli'],v['purpose'],v['locations'])
            # Preparing locations reserves no quantity and changes no inventory
            # fact. In particular it must not invalidate legacy stock_count's
            # captured Item version; actual posting validates/locks it again.
            row.updated_at=utcnow();db.flush()
            flow.log_event(db,user,row,'warehouse_allocation','准备物资库位（尚未实际收发）',row.state,{'item_id':item.id,'quantity_milli':v['quantity_milli'],'purpose':v['purpose']})
            flow.save_receipt(db,user,key,fp,row);db.commit();return {'case_id':row.id,'version':row.version,'prepared':True}
    except (HTTPException,IntegrityError,OperationalError,StaleDataError) as e:conflict(db,e)

def allocation_options(db,user,case_id):
    row=flow.get_case(db,user,case_id)
    mapping={'purchase':['purchase'],'material_issue':['issue'],'material_return':['return'],'stock_count':['count'],
        'procurement':['procurement_receipt','procurement_return'],'material_transfer':['transfer_out','transfer_in','transfer_return'],
        'repair':['repair_issue_v3','repair_return_v3'],'retail':['retail_dispatch','retail_return']}
    if row.kind=='addon' and row.flow_version==3:mapping['addon']=['addon_dispatch_v3','addon_return_v3']
    if row.kind not in mapping or row.state in {'cancelled','rejected'}:raise HTTPException(422,'此原单不支持物资库位准备')
    ids=set()
    if row.kind in {'purchase','material_issue','material_return','stock_count'}:ids.add(row.data['item_id'])
    elif row.kind=='procurement':
        from .procurement_models import PurchaseLine
        ids.update(db.scalars(select(PurchaseLine.item_id).where(PurchaseLine.case_id==row.id)))
    elif row.kind=='retail':
        from .retail_models import RetailLine
        ids.update(db.scalars(select(RetailLine.item_id).where(RetailLine.case_id==row.id)))
    elif row.kind=='addon':
        from .addon_models import AddonLine,AddonQuote
        ids.update(db.scalars(select(AddonLine.item_id).join(AddonQuote,AddonQuote.id==AddonLine.quote_id).where(AddonQuote.case_id==row.id,AddonLine.item_id.is_not(None))))
    elif row.kind=='repair':
        from .repair_models import RepairLine,RepairQuote
        ids.update(db.scalars(select(RepairLine.item_id).join(RepairQuote,RepairQuote.id==RepairLine.quote_id).where(RepairQuote.case_id==row.id,RepairLine.item_id.is_not(None))))
    elif row.kind=='material_transfer':
        from .transfer_service import authority as transfer_authority
        from .transfer_models import MaterialTransfer,TransferLine
        with transfer_authority(db,user,PHYSICAL):
            transfer=db.scalar(select(MaterialTransfer).where((MaterialTransfer.from_case_id==row.id)|(MaterialTransfer.to_case_id==row.id)))
            if not transfer:raise HTTPException(404,'原调拨单不存在')
            lines=list(db.scalars(select(TransferLine).where(TransferLine.transfer_id==transfer.id)))
            if row.store_id==transfer.from_store_id:ids.update(l.source_item_id for l in lines)
            else:ids.update(db.scalars(select(Item.id).where(Item.sku.in_([l.sku for l in lines]))))
    return {'case_id':row.id,'number':row.number,'version':row.version,'purposes':mapping[row.kind],
        'items':[stock_view(db,user,i,False) for i in sorted(ids)]}

def _location_guard(db,key):
    return stock.location_in_use(db,key)
from .master_data import register_reference_guard
register_reference_guard('locations',_location_guard)
