"""Original customer settlement adapters; never bypass fulfillment or price approval."""
from sqlalchemy import select,func
from datetime import date,datetime
from fastapi import HTTPException
from .db import utcnow
from .flow_models import Case,PaymentLink
from .business_finance_models import (FinanceAdvance,FinanceAdvanceEntry,FinanceApplication,FinanceCreditLink,FinanceCashAllocation,
    FinanceCashBatch,FinanceAdvanceReturn,FinanceOrder,FinanceReturnReceivable)
from . import flow_engine as flow


def case_credit_amount(db,case_id):
    return db.scalar(select(func.coalesce(func.sum(FinanceCreditLink.amount_cents),0)).where(FinanceCreditLink.case_id==case_id)) or 0


def case_reserved_amount(db,case_id):
    return db.scalar(select(func.coalesce(func.sum(FinanceApplication.amount_cents),0)).where(FinanceApplication.target_case_id==case_id,FinanceApplication.status=='reserved')) or 0


def source_details(db,user,key,include_reservations=True,allow_correcting=False):
    row=flow.get_case(db,user,key)
    if allow_correcting:
        from .business_finance_partial_corrections import ended_sale,fully_returned_insurance
        resolved=ended_sale(db,user,row)
        if resolved:
            from .aftercare_service import net_charge
            gross=net_charge(db,row);due=max(0,gross-flow.paid_amount(db,row))
            return row,dict(case_id=row.id,number=row.number,kind=row.kind,version=row.version,customer_id=row.customer_id,
                business_date=row.business_date.isoformat(),allocation_id=None,payer_type='customer',amount_cents=gross,
                due_cents=due,credit_cents=case_credit_amount(db,row.id),allocations=[])
        if db.info.get('_partial_finance_case') and fully_returned_insurance(db,row):
            return row,dict(case_id=row.id,number=row.number,kind=row.kind,version=row.version,customer_id=row.customer_id,
                business_date=row.business_date.isoformat(),allocation_id=None,payer_type='customer',amount_cents=0,
                due_cents=0,credit_cents=case_credit_amount(db,row.id),allocations=[])
    if row.kind=='retail':
        from .retail_group_service import guard_external_settlement
        guard_external_settlement(db,row,'business_finance')
    from .flow_specs import flow_spec
    flow_spec(row.kind,row.flow_version)
    from .sales_quote_service import guard_source_action as guard_quote
    guard_quote(db,user,row,'business_finance')
    from .aftercare_service import guard_source_action
    guard_source_action(db,user,row,'business_finance')
    from .aftercare_service import net_charge
    from . import repair_service as repair,retail_service as retail
    from . import service_orders_service as service_orders
    if service_orders.is_detailed(row):return row,service_orders.source_finance(db,user,row,include_reservations)
    from . import insurance_service as insurance
    if insurance.is_detailed(row):return row,insurance.source_finance(db,user,row,include_reservations)
    from . import addon_service as addon
    if addon.is_detailed(row):return row,addon.source_finance(db,user,row,include_reservations)
    allocation_id=None;allocated=[]
    if repair.is_detailed(row):
        from .repair_models import RepairAllocation
        allocation=db.scalar(select(RepairAllocation).where(RepairAllocation.case_id==row.id,RepairAllocation.payer_type=='customer'))
        due=repair.customer_due(db,row,include_reservations)
        allocation_id=allocation.id if allocation else None
        gross=net_charge(db,row,allocation.id) if allocation else 0
        allocated=[{k:(v.isoformat() if isinstance(v,(date,datetime)) else v) for k,v in a.items()} for a in repair.receivable_rows(db,row)]
    elif row.kind=='retail' and row.flow_version==2:
        if not row.data.get('authorized') or row.data.get('cancelled') or retail._active(db,row):raise HTTPException(409,'精品须已确认报价且无在办退货，才可原单结算')
        values=retail.totals(db,row);gross=values['charge_cents'];due=retail.collectable_amount(db,row) if include_reservations else values['receivable_cents']
    elif row.kind in {'order','repair','addon','agency','insurance'} and (row.flow_version in {1,2} or (row.kind=='order' and row.flow_version in {3,4})):
        action=next((a for a in flow_spec(row.kind,row.flow_version)['actions'] if a.key=='receive'),None)
        ended_correction=allow_correcting and (row.state=='completed' or
            (row.kind=='order' and row.flow_version in {3,4} and row.state=='delivered'))
        if not action or (row.state not in action.states and not ended_correction):
            raise HTTPException(409,'原业务当前不接受客户结算，请先完成原业务前置步骤')
        if row.kind=='repair' and row.data.get('payer') not in {None,'客户'}:raise HTTPException(409,'客户月结不能代收保险或厂家承担')
        gross=net_charge(db,row);due=gross-flow.paid_amount(db,row)
        if include_reservations:
            from .group_service import case_reserved_amount as principal_held
            from .group_benefits_service import case_reserved_amount as benefit_held
            due-=principal_held(db,row.id)+benefit_held(db,row.id)+case_reserved_amount(db,row.id)
    elif row.kind=='business_finance' and row.flow_version==2:
        receivable=db.scalar(select(FinanceReturnReceivable).where(FinanceReturnReceivable.case_id==row.id))
        if not receivable:raise HTTPException(409,'只有已独立批准的其他入库退货应收可办理收款')
        from .business_finance_return_adjustments import effective_target,guard_collection
        guard_collection(db,receivable)
        gross=effective_target(db,receivable);due=gross-sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in db.scalars(select(PaymentLink).where(PaymentLink.case_id==row.id)))
    else:raise HTTPException(409,'该来源不属于本店客户业务结算范围')
    return row,{'case_id':row.id,'number':row.number,'kind':row.kind,'version':row.version,'customer_id':row.customer_id,
        'business_date':row.business_date.isoformat(),'allocation_id':allocation_id,'payer_type':'customer','amount_cents':gross,
        'due_cents':max(0,due),'credit_cents':case_credit_amount(db,row.id),'allocations':allocated}


def sync_source(db,user,row,evidence_id):
    from . import repair_service as repair,retail_service as retail
    from . import service_orders_service as service_orders
    db.flush()
    from . import insurance_service as insurance
    from . import addon_service as addon
    from .business_finance_partial_corrections import ended_sale
    resolved=ended_sale(db,user,row)
    if resolved:
        from .aftercare_service import _sync
        after,_=resolved
        _sync(db,user,after,evidence_id);after.updated_at=utcnow()
        # The existing applied plan remains immutable; only financial responsibility reopens.
        flow.log_event(db,user,after,'aftercare_receipt_correction','原收款误记更正后核对保留费余额',detail={'correction_case_id':db.info['_partial_finance_case'],'source_case_id':row.id})
    elif addon.is_detailed(row):addon.sync_after_finance(db,user,row,evidence_id)
    elif insurance.is_detailed(row):insurance.sync_after_finance(db,user,row,evidence_id)
    elif service_orders.is_detailed(row):service_orders.sync_after_finance(db,user,row,evidence_id)
    elif repair.is_detailed(row):repair.sync_after_member(db,user,row,evidence_id=evidence_id)
    elif row.kind=='retail':retail._sync(db,user,row)
    elif row.kind!='business_finance':
        from .aftercare_service import net_charge
        remaining=net_charge(db,row)-flow.paid_amount(db,row)
        if remaining>0:
            flow.ensure_task(db,row,'receive','核对原单客户余额并登记实际到账','finance',reopen=True)
            if row.state=='completed':row.state='credit_open';row.completed_date=None
        else:
            flow.finish_task(db,row,'receive',user)
            if row.state=='credit_open':flow.complete_case(db,user,row)
    row.updated_at=utcnow();db.flush()
    from .membership_points import sync_consumption_points
    from .invoice_service import sync_source as invoice_sync
    sync_consumption_points(db,user,row,evidence_id=evidence_id);invoice_sync(db,user,row)


def source_evidence_allowed(db,row,asset):
    if asset.store_id!=row.store_id:return False
    batch=db.scalar(select(FinanceCashBatch).join(FinanceCashAllocation,FinanceCashAllocation.batch_id==FinanceCashBatch.id)
        .where(FinanceCashAllocation.case_id==row.id,FinanceCashBatch.case_id==asset.case_id,FinanceCashBatch.evidence_id==asset.id))
    if batch:return True
    entry=db.scalar(select(FinanceAdvanceEntry).join(FinanceCreditLink,FinanceCreditLink.entry_id==FinanceAdvanceEntry.id)
        .join(FinanceAdvance,FinanceAdvance.id==FinanceAdvanceEntry.advance_id)
        .where(FinanceCreditLink.case_id==row.id,FinanceAdvanceEntry.case_id==asset.case_id,FinanceAdvanceEntry.evidence_id==asset.id,FinanceAdvance.customer_id==row.customer_id))
    return bool(entry)


def _credit_remaining(db,original):
    returned=-(db.scalar(select(func.coalesce(func.sum(FinanceCreditLink.amount_cents),0)).where(FinanceCreditLink.original_id==original.id)) or 0)
    held=db.scalar(select(func.coalesce(func.sum(FinanceAdvanceReturn.amount_cents),0)).where(FinanceAdvanceReturn.original_credit_id==original.id,FinanceAdvanceReturn.status=='reserved')) or 0
    return original.amount_cents-returned-held


def eligible_advance_credits(db,user,source):
    flow.get_case(db,user,source.id);result=[]
    for link in db.scalars(select(FinanceCreditLink).where(FinanceCreditLink.case_id==source.id,FinanceCreditLink.amount_cents>0)):
        amount=_credit_remaining(db,link)
        if amount:result.append({'kind':'advance','entry_id':link.id,'remaining_units':amount,'remaining_credit_cents':amount,
            'credit_per_unit':1,'discount_per_unit':0,'discount_remaining_cents':0,'unit':'分','name':'原本店预收抵用'})
    return result


def reserve_advance_returns(db,user,aftercare,source,plan_id,selections,evidence_id):
    from .aftercare_service import assert_group_plan
    plan=assert_group_plan(db,aftercare,source,plan_id,'reserve')
    expected={(v['entry_id'],v['units'],v['credit_cents']) for v in plan['selections'] if v['kind']=='advance'}
    if expected!={(v['entry_id'],v['units'],v['credit_cents']) for v in selections if v['kind']=='advance'}:raise HTTPException(409,'预收原路退回不符批准方案')
    from .business_finance_service import authority
    with authority(db,user,{'admin','manager'}):
        flow.file_exists(db,aftercare,evidence_id)
        for value in selections:
            if value['kind']!='advance':continue
            original=db.scalar(select(FinanceCreditLink).where(FinanceCreditLink.id==value['entry_id'],FinanceCreditLink.case_id==source.id,FinanceCreditLink.amount_cents>0).with_for_update())
            if not original or value['units']!=value['credit_cents'] or value['units']>_credit_remaining(db,original):raise HTTPException(409,'预收抵用退回超过原单剩余额度')
            entry=db.scalar(select(FinanceAdvanceEntry).where(FinanceAdvanceEntry.id==original.entry_id))
            advance=db.scalar(select(FinanceAdvance).where(FinanceAdvance.id==entry.advance_id).with_for_update())
            if not advance or advance.customer_id!=source.customer_id:raise HTTPException(409,'原预收客户与售后客户不一致')
            advance.updated_at=utcnow()
            db.add(FinanceAdvanceReturn(aftercare_case_id=aftercare.id,source_case_id=source.id,plan_id=plan_id,original_credit_id=original.id,amount_cents=value['units']))
        db.flush()


def cancel_advance_returns(db,user,aftercare,source,plan_id):
    from .aftercare_service import assert_group_plan
    assert_group_plan(db,aftercare,source,plan_id,'cancel')
    from .business_finance_service import authority
    with authority(db,user):
        for hold in db.scalars(select(FinanceAdvanceReturn).where(FinanceAdvanceReturn.plan_id==plan_id,FinanceAdvanceReturn.source_case_id==source.id).with_for_update()):
            if hold.status=='applied':raise HTTPException(409,'已生效预收抵用退回不能取消')
            hold.status='released'
        db.flush()


def apply_advance_returns(db,user,aftercare,source,plan_id,selections,evidence_id):
    from .aftercare_service import assert_group_plan
    plan=assert_group_plan(db,aftercare,source,plan_id,'apply')
    if {(v['entry_id'],v['units']) for v in plan['selections'] if v['kind']=='advance'}!={(v['entry_id'],v['units']) for v in selections if v['kind']=='advance'}:raise HTTPException(409,'预收退回与原客户已确认方案不一致')
    flow.file_exists(db,aftercare,evidence_id)
    from .business_finance_service import authority
    with authority(db,user,{'admin','finance'}):
        expected={(v['entry_id'],v['units']) for v in selections if v['kind']=='advance'}
        holds=list(db.scalars(select(FinanceAdvanceReturn).where(FinanceAdvanceReturn.plan_id==plan_id,FinanceAdvanceReturn.source_case_id==source.id).with_for_update()))
        if expected!={(h.original_credit_id,h.amount_cents) for h in holds} or any(h.status!='reserved' for h in holds):raise HTTPException(409,'预收抵用退回与批准占额不一致')
        result=[]
        for hold in holds:
            original=db.scalar(select(FinanceCreditLink).where(FinanceCreditLink.id==hold.original_credit_id))
            entry=db.scalar(select(FinanceAdvanceEntry).where(FinanceAdvanceEntry.id==original.entry_id))
            advance=db.scalar(select(FinanceAdvance).where(FinanceAdvance.id==entry.advance_id).with_for_update())
            if _credit_remaining(db,original)<0 or advance.balance_cents+hold.amount_cents>advance.initial_cents:raise HTTPException(409,'原预收退回余额不守恒')
            advance.balance_cents+=hold.amount_cents;advance.updated_at=utcnow()
            posting=FinanceAdvanceEntry(advance_id=advance.id,case_id=aftercare.id,purpose='return',amount_cents=hold.amount_cents,
                original_id=entry.id,evidence_id=evidence_id,actor_id=user.id)
            db.add(posting);db.flush()
            credit=FinanceCreditLink(case_id=source.id,entry_id=posting.id,application_id=original.application_id,original_id=original.id,amount_cents=-hold.amount_cents)
            db.add(credit);db.flush();hold.status='applied';hold.returned_credit_id=credit.id
            result.append({'kind':'advance','entry_id':credit.id,'credit_cents':hold.amount_cents,'external_discount_cents':0})
        db.flush();return result


def return_retail_advance(db,user,row,action,evidence_id=None):
    """Return only excess original advance credit after real retail return/cancel."""
    from .flow_models import FlowEvent,FileAsset
    from .retail_models import RetailReturnPosting
    from .retail_service import totals
    if row.kind!='retail' or row.flow_version!=2 or action not in {'cancel','return_receive'}:raise HTTPException(409,'预收回退只由本次原精品取消或实际退货触发')
    excess=totals(db,row)['advance_return_due_cents']
    if excess<=0:return
    event=db.scalar(select(FlowEvent).where(FlowEvent.case_id==row.id,FlowEvent.action=='retail_'+action,FlowEvent.actor_id==user.id).order_by(FlowEvent.id.desc()))
    if not event:raise HTTPException(409,'原精品退回缺少本次明确业务确认')
    if action=='return_receive':
        if not evidence_id or event.detail.get('evidence_id')!=evidence_id or not db.scalar(select(RetailReturnPosting.id).where(RetailReturnPosting.case_id==row.id,RetailReturnPosting.evidence_id==evidence_id)):
            raise HTTPException(409,'预收回退须有本次原单实际退货及凭据')
    else:
        if not row.data.get('cancelled') or row.data.get('dispatched'):raise HTTPException(409,'仅未发货原单的明确取消可以回退预收抵用')
        evidence_id=db.scalar(select(FileAsset.id).where(FileAsset.case_id==row.id,FileAsset.category=='authorization',FileAsset.generated.is_(False)).order_by(FileAsset.id.desc()))
        if not evidence_id:raise HTTPException(409,'原单预收回退缺少原客户确认的报价及约定')
    flow.file_exists(db,row,evidence_id)
    from .business_finance_service import authority
    with authority(db,user,{'admin','manager','sales','service','inventory'}):
        for original in db.scalars(select(FinanceCreditLink).where(FinanceCreditLink.case_id==row.id,FinanceCreditLink.amount_cents>0).order_by(FinanceCreditLink.id).with_for_update()):
            amount=min(excess,_credit_remaining(db,original))
            if amount<=0:continue
            previous=db.scalar(select(FinanceAdvanceEntry).where(FinanceAdvanceEntry.id==original.entry_id))
            advance=db.scalar(select(FinanceAdvance).where(FinanceAdvance.id==previous.advance_id).with_for_update())
            if advance.customer_id!=row.customer_id or advance.balance_cents+amount>advance.initial_cents:raise HTTPException(409,'原客户预收回退不守恒')
            advance.balance_cents+=amount;advance.updated_at=utcnow()
            entry=FinanceAdvanceEntry(advance_id=advance.id,case_id=row.id,purpose='return',amount_cents=amount,original_id=previous.id,evidence_id=evidence_id,actor_id=user.id)
            db.add(entry);db.flush();db.add(FinanceCreditLink(case_id=row.id,entry_id=entry.id,application_id=original.application_id,original_id=original.id,amount_cents=-amount))
            excess-=amount
            if not excess:break
        if excess:raise HTTPException(409,'原预收抵用正在其他退回方案中占用，不能重复回退')
        db.flush()


def restore_service_credit(db,user,row,credit_link,amount,evidence_id,plan_id):
    from .service_orders_service import assert_advance_return
    return _restore_original_credit(db,user,row,credit_link,amount,evidence_id,plan_id,assert_advance_return)


def restore_insurance_credit(db,user,row,credit_link,amount,evidence_id,plan_id):
    from .insurance_service import assert_advance_return
    return _restore_original_credit(db,user,row,credit_link,amount,evidence_id,plan_id,assert_advance_return)


def restore_addon_credit(db,user,row,credit_link,amount,evidence_id,resolution_id):
    from .addon_service import assert_advance_return
    return _restore_original_credit(db,user,row,credit_link,amount,evidence_id,resolution_id,assert_advance_return)


def _restore_original_credit(db,user,row,credit_link,amount,evidence_id,plan_id,assert_advance_return):
    """Restore an original advance only after its domain validates the approved return."""
    from .business_finance_service import authority
    if type(amount) is not int or amount<=0:
        raise HTTPException(422,'原预收退回金额须为正整数分')
    with authority(db,user,{'admin','finance'}):
        original=db.scalar(select(FinanceCreditLink).where(
            FinanceCreditLink.id==credit_link.id,FinanceCreditLink.case_id==row.id,
            FinanceCreditLink.amount_cents>0).with_for_update())
        if not original:raise HTTPException(409,'未找到本业务原单的预收抵用')
        assert_advance_return(db,user,row,original,amount,evidence_id,plan_id)
        flow.file_exists(db,row,evidence_id)
        if amount>_credit_remaining(db,original):
            raise HTTPException(409,'退回超过原预收抵用未退额度或额度已占用')
        previous=db.scalar(select(FinanceAdvanceEntry).where(
            FinanceAdvanceEntry.id==original.entry_id,FinanceAdvanceEntry.purpose=='apply'))
        if not previous:raise HTTPException(409,'原预收抵用流水不完整')
        advance=db.scalar(select(FinanceAdvance).where(FinanceAdvance.id==previous.advance_id).with_for_update())
        if not advance or advance.customer_id!=row.customer_id or advance.balance_cents+amount>advance.initial_cents:
            raise HTTPException(409,'原客户预收退回余额不守恒')
        advance.balance_cents+=amount;advance.updated_at=utcnow()
        entry=FinanceAdvanceEntry(advance_id=advance.id,case_id=row.id,purpose='return',
            amount_cents=amount,original_id=previous.id,evidence_id=evidence_id,actor_id=user.id)
        db.add(entry);db.flush()
        credit=FinanceCreditLink(case_id=row.id,entry_id=entry.id,application_id=original.application_id,
            original_id=original.id,amount_cents=-amount)
        db.add(credit);db.flush()
        return credit
