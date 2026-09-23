"""Exact original component returns, invoked by approved native aftercare plans."""
from fastapi import HTTPException
from sqlalchemy import select,func
from .db import utcnow
from . import repair_package_service as packages,group_service as group,flow_engine as flow
from .repair_package_models import PackageEntry,PackageLot,PackagePurchase,PackageHold,PackageAftercareHold,PackageStockReturn
from .repair_models import RepairStock
from .flow_models import Case,StockMove,Item
from .group_models import GroupIdentityLink

def _original(db,user,source,key):
    original=db.scalar(select(PackageEntry).where(PackageEntry.id==key,PackageEntry.case_id==source.id,PackageEntry.store_id==source.store_id,PackageEntry.purpose=='capture'))
    if not original:raise HTTPException(404,'本店原套餐核销不存在')
    lot=packages.one(db,PackageLot,original.lot_id);purchase=packages.one(db,PackagePurchase,lot.purchase_id)
    member=packages._member(db,purchase.member_id,source.store_id,False)
    linked=db.scalar(select(GroupIdentityLink.id).where(GroupIdentityLink.store_id==source.store_id,GroupIdentityLink.local_kind=='customer',GroupIdentityLink.local_id==source.customer_id,GroupIdentityLink.identity_id==member.identity_id))
    if not linked:raise HTTPException(409,'原组件核销会员与本店原单客户不符')
    return original,lot,purchase

def remaining_spans(db,original,exclude_plan=None):
    used=[p for e in db.scalars(select(PackageEntry).where(PackageEntry.original_id==original.id,PackageEntry.purpose=='reverse')) for p in e.spans]
    for h in db.scalars(select(PackageAftercareHold).where(PackageAftercareHold.original_id==original.id,PackageAftercareHold.status=='reserved')):
        if h.plan_id!=exclude_plan:used+=h.spans
    return packages.subtract(original.spans,used)

def quote_return(db,user,source,entry_id,units,exclude_plan=None):
    with packages.authority(db,user):
        original,lot,p=_original(db,user,source,entry_id)
        if lot.snapshot['kind']!='part':raise HTTPException(409,'已经完成的作业不能伪装未用次数；服务补偿请走原维修费用纠正')
        packages._quantity(lot,units);spans=packages.take(remaining_spans(db,original,exclude_plan),units);amount=packages.amounts(lot,spans)
        return {'kind':'repair_package','entry_id':original.id,'units':units,'spans':spans,'credit_cents':amount['credit_cents'],'discount_cents':amount['credit_cents']-amount['paid_cents'],**amount}

def eligible_capture_sources(db,user,source):
    with packages.authority(db,user):
        result=[]
        for entry in db.scalars(select(PackageEntry).where(PackageEntry.case_id==source.id,PackageEntry.store_id==source.store_id,PackageEntry.purpose=='capture')):
            original,lot,p=_original(db,user,source,entry.id)
            if lot.snapshot['kind']!='part':continue
            spans=remaining_spans(db,original);value=packages.amounts(lot,spans)
            if value['quantity_milli']:
                result.append({'kind':'repair_package','entry_id':entry.id,'member_id':p.member_id,'remaining_units':value['quantity_milli'],'remaining_credit_cents':value['credit_cents'],'discount_remaining_cents':value['credit_cents']-value['paid_cents'],'credit_per_unit':None,'discount_per_unit':None,'unit':'千分量','name':lot.snapshot['name'],'exact_components':True})
        return result

def reserve_returns(db,user,aftercare,source,plan_id,selections,evidence_id):
    from .aftercare_service import assert_group_plan
    with packages.authority(db,user,packages.MANAGE):
        plan=assert_group_plan(db,aftercare,source,plan_id,'reserve');selected=[s for s in selections if s['kind']=='repair_package'];expected=[s for s in plan['selections'] if s['kind']=='repair_package']
        normalize=lambda items:sorted((s['kind'],s['entry_id'],s['units'],s['credit_cents']) for s in items)
        if normalize(selected)!=normalize(expected):raise HTTPException(409,'原组件退回不符当前批准方案')
        for s in selected:
            quoted=quote_return(db,user,source,s['entry_id'],s['units'])
            if quoted['credit_cents']!=s['credit_cents']:raise HTTPException(409,'部分组件退回金额不符原数量区间')
            original,lot,p=_original(db,user,source,s['entry_id']);lot.updated_at=utcnow()
            db.add(PackageAftercareHold(aftercare_case_id=aftercare.id,source_case_id=source.id,plan_id=plan_id,original_id=original.id,spans=quoted['spans'],**{k:quoted[k] for k in packages.AMOUNTS}))
        if selected:flow.ensure_task(db,aftercare,'repair_package_material_return_'+str(plan_id),'按已确认方案核对原套餐配件实际退回','inventory')
        db.flush();return {'credit_cents':sum(s['credit_cents'] for s in selected)}

def cancel_returns(db,user,aftercare,source,plan_id):
    from .aftercare_service import assert_group_plan
    with packages.authority(db,user):
        assert_group_plan(db,aftercare,source,plan_id,'cancel')
        for h in db.scalars(select(PackageAftercareHold).where(PackageAftercareHold.plan_id==plan_id,PackageAftercareHold.source_case_id==source.id)):
            if h.status=='applied' or db.scalar(select(PackageStockReturn.id).where(PackageStockReturn.hold_id==h.id)):raise HTTPException(409,'组件已有实际实物原退，不能取消抹除；请完成原批准方案')
            h.status='released'
        flow.finish_task(db,aftercare,'repair_package_material_return_'+str(plan_id),user,'cancelled')
        db.flush()

def apply_returns(db,user,aftercare,source,plan_id,evidence_id):
    from .aftercare_service import assert_group_plan
    with packages.authority(db,user,packages.FINANCE):
        plan=assert_group_plan(db,aftercare,source,plan_id,'apply');expected=[s for s in plan['selections'] if s['kind']=='repair_package'];holds=list(db.scalars(select(PackageAftercareHold).where(PackageAftercareHold.plan_id==plan_id,PackageAftercareHold.source_case_id==source.id)))
        if sorted((h.original_id,h.quantity_milli,h.credit_cents) for h in holds)!=sorted((s['entry_id'],s['units'],s['credit_cents']) for s in expected) or any(h.status!='reserved' for h in holds):raise HTTPException(409,'当前原组件退回占额缺失或已经结束')
        output=[]
        for h in holds:
            original,lot,p=_original(db,user,source,h.original_id)
            if lot.snapshot['kind']!='part':raise HTTPException(409,'已完成工时不得恢复为未用权益')
            actual=db.scalar(select(func.coalesce(func.sum(PackageStockReturn.quantity_milli),0)).where(PackageStockReturn.hold_id==h.id)) or 0
            if actual!=h.quantity_milli:raise HTTPException(409,'请先按本方案完成原配件实际退回及可入库质检')
            if packages.subtract(h.spans,remaining_spans(db,original,plan_id)):raise HTTPException(409,'原组件已被其他方案退回')
            original_hold=packages.one(db,PackageHold,original.hold_id)
            entry=packages._entry(db,user,source,lot,'reverse',h.spans,evidence_id,hold=original_hold,original=original);h.status='applied'
            output.append({'kind':'repair_package','entry_id':entry.id,'credit_cents':h.credit_cents,'external_discount_cents':h.credit_cents-h.paid_cents})
        db.flush()
        from .invoice_service import sync_source
        sync_source(db,user,source)
        return output

def return_material(db,user,key,aftercare_id,v):
    def run(sid):
        from . import repair_service as repair
        from .aftercare_service import assert_group_plan
        aftercare=flow.get_case(db,user,aftercare_id);group._version(aftercare,v['version']);hold=packages.one(db,PackageAftercareHold,v['hold_id'])
        if hold.aftercare_case_id!=aftercare.id or hold.status!='reserved':raise HTTPException(404,'当前已批售后组件占额不存在')
        source=repair.get_order(db,user,hold.source_case_id);group._version(source,v['source_version']);assert_group_plan(db,aftercare,source,hold.plan_id,'apply');packages._proof(db,user,aftercare,v['evidence_id'])
        packages._task(db,user,aftercare,'repair_package_material_return_'+str(hold.plan_id))
        original,lot,p=_original(db,user,source,hold.original_id);claim=packages.one(db,PackageHold,original.hold_id)
        if lot.snapshot['kind']!='part':raise HTTPException(409,'作业不是可退回实物')
        stock=packages.one(db,RepairStock,v['original_stock_id']);qty=v['quantity_milli']
        if stock.case_id!=source.id or stock.line_key!=claim.line_key or stock.original_id:raise HTTPException(404,'请选择本组件实际原领料批次')
        used=db.scalar(select(func.coalesce(func.sum(PackageStockReturn.quantity_milli),0)).where(PackageStockReturn.hold_id==hold.id)) or 0
        returns=list(db.scalars(select(RepairStock).where(RepairStock.original_id==stock.id)));left=stock.quantity_milli+sum(x.quantity_milli for x in returns);value_left=stock.value_cents+sum(x.value_cents for x in returns)
        if qty>left or qty>hold.quantity_milli-used:raise HTTPException(409,'实际退回超过原领料或批准组件数量')
        value=value_left if qty==left else (2*value_left*qty+left)//(2*left)
        move=packages.one(db,StockMove,stock.stock_move_id);item=packages.one(db,Item,move.item_id)
        posted=repair._post_stock(db,user,source,item,qty,value,'repair_return_v3',move.id)
        fact=RepairStock(case_id=source.id,quote_id=stock.quote_id,line_key=stock.line_key,stock_move_id=posted.id,original_id=stock.id,quantity_milli=-qty,value_cents=-value,evidence_id=v['evidence_id'])
        db.add(fact);db.flush();db.add(PackageStockReturn(hold_id=hold.id,original_stock_id=stock.id,stock_fact_id=fact.id,quantity_milli=qty,value_cents=value,evidence_id=v['evidence_id'],result=v['result'],actor_id=user.id))
        source.updated_at=utcnow();source.cost_cents-=value;aftercare.updated_at=utcnow();flow.log_event(db,user,source,'repair_package_material_return','按已批售后实际收回原配件',detail={'aftercare_case_id':aftercare.id,'hold_id':hold.id,'stock_fact_id':fact.id});db.flush()
        hs=list(db.scalars(select(PackageAftercareHold).where(PackageAftercareHold.plan_id==hold.plan_id,PackageAftercareHold.status=='reserved')))
        if all((db.scalar(select(func.coalesce(func.sum(PackageStockReturn.quantity_milli),0)).where(PackageStockReturn.hold_id==h.id)) or 0)==h.quantity_milli for h in hs):flow.finish_task(db,aftercare,'repair_package_material_return_'+str(hold.plan_id),user)
        db.flush();return {'case_id':aftercare.id,'version':aftercare.version,'source_case_id':source.id,'source_version':source.version,'hold_id':hold.id,'stock_fact_id':fact.id,'quantity_milli':qty,'value_cents':value}
    return packages.execute(db,user,key,'return_material:'+str(aftercare_id),v,{'admin','inventory'},run)

def return_targets(db,user,aftercare_id):
    with packages.authority(db,user,packages.READ|{'inventory'}) as sid:
        row=flow.get_case(db,user,aftercare_id)
        if row.kind!='aftercare' or row.flow_version!=2:raise HTTPException(404,'本店原售后不存在')
        items=[]
        for h in db.scalars(select(PackageAftercareHold).where(PackageAftercareHold.aftercare_case_id==row.id,PackageAftercareHold.store_id==sid,PackageAftercareHold.status=='reserved')):
            original=packages.one(db,PackageEntry,h.original_id);lot=packages.one(db,PackageLot,original.lot_id);claim=packages.one(db,PackageHold,original.hold_id);source=packages.one(db,Case,h.source_case_id)
            used=db.scalar(select(func.coalesce(func.sum(PackageStockReturn.quantity_milli),0)).where(PackageStockReturn.hold_id==h.id)) or 0
            stocks=[]
            for stock in db.scalars(select(RepairStock).where(RepairStock.case_id==source.id,RepairStock.line_key==claim.line_key,RepairStock.original_id.is_(None))):
                returned=db.scalar(select(func.coalesce(func.sum(RepairStock.quantity_milli),0)).where(RepairStock.original_id==stock.id)) or 0
                stocks.append({'id':stock.id,'quantity_milli':stock.quantity_milli,'returnable_milli':stock.quantity_milli+returned})
            items.append({'hold_id':h.id,'name':lot.snapshot['name'],'unit':lot.snapshot['unit'],'quantity_milli':h.quantity_milli,'returned_milli':used,'remaining_milli':h.quantity_milli-used,'source_case_id':source.id,'source_version':source.version,'original_stocks':stocks})
        return {'id':row.id,'version':row.version,'state':row.state,'items':items}
