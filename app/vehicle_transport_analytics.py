"""Local original-VIN ledgers; no other store's files, claims or cash are read."""
from collections import defaultdict
from contextlib import contextmanager
from datetime import date
from sqlalchemy import select, or_
from fastapi import HTTPException
from .models import Store
from .vehicle_transfer_models import VehicleTransfer
from .vehicle_transport_models import (VehicleTransportException, VehicleTransportLoss,
    VehicleTransportLossSettlement, VehicleTransportFoundReceipt, VehicleTransportFoundSettlement,
    VehicleTransportClaim, VehicleTransportClaimPlan, VehicleTransportClaimReview, VehicleTransportClaimPayment)
from .inventory_report_common import bounded, yuan, route, as_of, period, MONEY_ROLES

DEFINITIONS = [
    '原车运输损失按原发出VIN及批准后实际核销日减少在途原资产，不产生第二次库存出库。两店成本承担合计等于该原车原成本，但不与资产减少重复相加。',
    '后来找到只是实际观察；两店独立批准并真实验收入库后，按原VIN新库存代次恢复原成本。原损失、原赔款及旧清算均保留历史。',
    '找回净往来为原损失承担冲回加实际资产归属：接收店为原调入店时应承接原成本。往来不是实际付款；只有双方实际收付确认后才结清。',
    '外部追偿目标、实际到账、原款退款分别追原条目。找回后先独立确认原目标归零，再按原银行款退款；查找、入库、目标调整均不自动制造现金。',
    '期间原资产变化、门店承担变化和当前追偿/店间余额是不同口径。跨期找回可显示负的损失净变化，不倒改旧月结。集团汇总隐藏原VIN和原单跳转。',
]


@contextmanager
def report_authority(db, user):
    ids=tuple(sid for sid in db.info.get('store_scope',()) if sid)
    if user.role not in MONEY_ROLES or not ids:raise HTTPException(403,'原整车损失财务来源须有明确授权门店及管理岗位')
    old=db.info.get('_transfer_authority');db.info['_transfer_authority']=('vehicle-transport-report',ids)
    try:yield ids
    finally:
        if old is None:db.info.pop('_transfer_authority',None)
        else:db.info['_transfer_authority']=old


def source_rows(db,user):
    with report_authority(db,user) as ids:
        parents={p.id:p for p in bounded(db,VehicleTransfer,select(VehicleTransfer).where(or_(
            VehicleTransfer.from_store_id.in_(ids),VehicleTransfer.to_store_id.in_(ids))))}
        exs={e.id:e for e in bounded(db,VehicleTransportException,select(VehicleTransportException).where(VehicleTransportException.transfer_id.in_(parents)))}
        aggregate=bool(db.info.get('aggregate_scope') or getattr(user,'_aggregate_scope',False) or len(ids)>1)
        result={key:[] for key in ('losses','found','burdens','burden_reversals','clearing','claims','claim_changes','cash','pending')}
        def base(sid,transfer_id,eid):
            parent=parents.get(transfer_id)
            if not parent or sid not in {parent.from_store_id,parent.to_store_id}:raise HTTPException(409,'原车核算来源与本店调拨不一致')
            return dict(store_id=sid,transfer_id=transfer_id,exception_id=eid,number=parent.number,
                vin='汇总不展示' if aggregate else parent.vin,
                case_id=None if aggregate else parent.from_case_id if sid==parent.from_store_id else parent.to_case_id)
        losses={p.id:p for p in bounded(db,VehicleTransportLoss)}
        own_burdens={}
        for p in losses.values():
            b=base(p.store_id,p.transfer_id,p.exception_id)
            result['losses'].append(dict(b,id=p.id,business_date=p.business_date.isoformat(),amount_cents=p.value_cents,loss_id=p.id))
            own_burdens[p.store_id,p.id]=(p.source_bearer_cents,b,p.business_date)
        loss_pairs=bounded(db,VehicleTransportLossSettlement)
        found_pairs=bounded(db,VehicleTransportFoundSettlement)
        found_receipts=bounded(db,VehicleTransportFoundReceipt)
        parent_ex={p.transfer_id:p.exception_id for p in losses.values()}
        for p in loss_pairs:parent_ex[p.transfer_id]=p.exception_id
        for p in found_receipts:parent_ex[p.transfer_id]=p.exception_id
        # A party may have no original burden, and therefore no local loss pair.
        for ex in exs.values():
            if ex.status!='resolved':parent_ex[ex.transfer_id]=ex.id
        for p in loss_pairs:
            b=base(p.store_id,p.transfer_id,p.exception_id)
            result['clearing'].append(dict(b,id=p.id,origin_kind='vehicle_loss',counterparty_store_id=p.counterparty_store_id,
                amount_cents=p.amount_cents,business_date=p.business_date.isoformat(),loss_id=p.loss_id))
            if p.amount_cents<0:own_burdens[p.store_id,p.loss_id]=(-p.amount_cents,b,p.business_date)
        recovered={}
        for p in found_pairs:
            b=base(p.store_id,p.transfer_id,parent_ex.get(p.transfer_id))
            result['clearing'].append(dict(b,id=p.id,origin_kind='vehicle_found',counterparty_store_id=p.counterparty_store_id,
                amount_cents=p.amount_cents,business_date=p.business_date.isoformat(),loss_id=p.loss_id,receipt_id=p.receipt_id))
            recovered[p.store_id,p.loss_id]=(p.business_date,p.receipt_id)
        for p in found_receipts:
            b=base(p.store_id,p.transfer_id,p.exception_id)
            result['found'].append(dict(b,id=p.id,business_date=p.business_date.isoformat(),amount_cents=p.value_cents,
                loss_id=p.loss_id,vehicle_id=p.vehicle_id))
            recovered[p.store_id,p.loss_id]=(p.business_date,p.id)
        for (sid,lid),(amount,b,day) in own_burdens.items():
            result['burdens'].append(dict(b,id=lid,loss_id=lid,amount_cents=amount,business_date=day.isoformat()))
            if (sid,lid) in recovered:
                day,receipt_id=recovered[sid,lid]
                result['burden_reversals'].append(dict(b,id=receipt_id,loss_id=lid,amount_cents=-amount,business_date=day.isoformat()))
        from .vehicle_transport_recovery import position
        for c in bounded(db,VehicleTransportClaim):
            ex=exs.get(c.exception_id)
            if not ex:raise HTTPException(409,'原车追偿不属于本店原差异')
            parent=parents[ex.transfer_id];p=position(db,c);b=base(c.store_id,parent.id,ex.id)
            found=parent.status=='recovered';counterparty=c.counterparty_snapshot['name'] if not aggregate else '原往来方（汇总隐藏）'
            result['claims'].append(dict(b,id=c.id,claim_id=c.id,counterparty=counterparty,
                target_cents=p['target_cents'],paid_cents=p['paid_cents'],due_cents=0 if found else p['due_cents'],
                refund_cents=p['refund_cents'],occupied_cents=p['occupied_cents'],
                pending_found_adjustment=bool(found and p['target_cents']),pending_plan_id=p['pending'].id if p['pending'] else None))
            prior=0
            for plan in p['plans']:
                review=p['reviews'].get(plan.id)
                if not review or review.decision!='approve':continue
                result['claim_changes'].append(dict(b,id=review.id,claim_id=c.id,counterparty=counterparty,
                    business_date=review.business_date.isoformat(),amount_cents=plan.target_cents-prior))
                prior=plan.target_cents
            for payment in p['payments']:
                result['cash'].append(dict(b,id=payment.id,claim_id=c.id,counterparty=counterparty,cash_id=payment.cash_id,
                    business_date=payment.business_date.isoformat(),amount_cents=payment.amount_cents*(1 if payment.direction=='in' else -1)))
        for ex in exs.values():
            if ex.status in {'resolved','recovered'}:continue
            p=parents[ex.transfer_id]
            # Single original dispatch owner; do not count one VIN twice in a group.
            if p.from_store_id not in ids:continue
            result['pending'].append(dict(base(p.from_store_id,p.id,ex.id),id=ex.id,status=ex.status,count=1,
                loss_recorded=p.status=='lost'))
        return result


def build_vehicle_transport(db,user,start=None,end=None,source_data=None):
    start,end=period(user,start,end)
    if user.role not in MONEY_ROLES:raise HTTPException(403,'整车运输财务报表仅供财务及管理岗位；库管从原差异查看实车待办')
    data=source_data if source_data is not None else source_rows(db,user)
    stores=dict(db.execute(select(Store.id,Store.name)).all());tables={};charts=[];metrics={}
    aggregate=bool(db.info.get('aggregate_scope') or getattr(user,'_aggregate_scope',False) or len(db.info.get('store_scope',()))>1)
    def new(key,title,headers):
        t={'id':key,'title':title,'headers':headers,'rows':[]};tables[key]=t;return t
    def put(t,r,values,**facts):
        t['rows'].append(dict(values=values,store_id=r['store_id'],source_id=r['id'],
            route=None if aggregate or not r.get('case_id') else route(db,r['case_id']),**facts))
    def bars(t,fields,caption,unit='cents'):
        totals={field:defaultdict(int) for field,_ in fields}
        for r in t['rows']:
            for field,_ in fields:totals[field][r['store_id']]+=r[field]
        ids=sorted({r['store_id'] for r in t['rows']})
        charts.append(dict(id=t['id'],title=t['title'],type='bar',section='inventory' if unit=='count' else 'finance',unit=unit,
            table=t['id'],labels=[stores.get(s,'') for s in ids],series=[dict(name=label,values=[totals[field][s] for s in ids]) for field,label in fields],caption=caption))
    in_period=lambda r:start.isoformat()<=r['business_date']<=end.isoformat()
    for kind,key,title,caption in [
        ('losses','vehicle_transport_loss_cost','期间整车原损失核销',DEFINITIONS[0]),
        ('found','vehicle_transport_found_cost','期间原车找回实际入库',DEFINITIONS[1]),
        ('burdens','vehicle_transport_burdens','期间两店原车损失承担',DEFINITIONS[0]),
        ('burden_reversals','vehicle_transport_burden_reversals','期间找回原车承担冲回',DEFINITIONS[2]),
    ]:
        t=new(key,title,['门店','原调拨','VIN','实际日期','原记录','金额（元）'])
        for r in filter(in_period,data[kind]):put(t,r,[stores.get(r['store_id'],''),r['number'],r['vin'],r['business_date'],r['id'],yuan(r['amount_cents'])],amount_cents=r['amount_cents'],business_date=r['business_date'])
        bars(t,[('amount_cents','本口径金额')],caption);metrics[key+'_cents']=sum(r['amount_cents'] for r in t['rows'])
    changes=new('vehicle_transport_asset_changes','期间原车资产损失净变化',['门店','原调拨','VIN','实际日期','原事实','损失净增减（元）'])
    for kind,label,sign in [('losses','原在途损失',1),('found','原车实际恢复',-1)]:
        for r in filter(in_period,data[kind]):put(changes,r,[stores.get(r['store_id'],''),r['number'],r['vin'],r['business_date'],label,yuan(sign*r['amount_cents'])],amount_cents=sign*r['amount_cents'])
    bars(changes,[('amount_cents','原资产损失净变化')],DEFINITIONS[4]);metrics['vehicle_transport_asset_change_cents']=sum(r['amount_cents'] for r in changes['rows'])
    for kind,key,title in [('claim_changes','vehicle_transport_claim_changes','期间原车外部赔付目标增减'),('cash','vehicle_transport_claim_cash','期间原车赔付原现金收退关联')]:
        t=new(key,title,['门店','原调拨','原追偿','实际日期','原往来方','净额（元）'])
        for r in filter(in_period,data[kind]):put(t,r,[stores.get(r['store_id'],''),r['number'],r['claim_id'],r['business_date'],r['counterparty'],yuan(r['amount_cents'])],amount_cents=r['amount_cents'],**({'cash_id':r['cash_id']} if kind=='cash' else {}))
        bars(t,[('amount_cents','净额')],DEFINITIONS[3]);metrics[key+'_cents']=sum(r['amount_cents'] for r in t['rows'])
    t=new('vehicle_transport_claim_balances','当前原车赔付待收待退',['门店','原调拨','原往来方','已批准目标（元）','实际净收（元）','当前允许待收（元）','已确认待退（元）','办理提示'])
    for r in data['claims']:
        put(t,r,[stores.get(r['store_id'],''),r['number'],r['counterparty'],*[yuan(r[k]) for k in ('target_cents','paid_cents','due_cents','refund_cents')],
            '原车已找回，先独立调整原目标，再退原款' if r['pending_found_adjustment'] else '待独立复核本版目标' if r['pending_plan_id'] else '沿原到账办理'],**{k:r[k] for k in ('due_cents','refund_cents','pending_found_adjustment')})
    bars(t,[('due_cents','当前待收'),('refund_cents','已确认待退')],DEFINITIONS[3])
    metrics['vehicle_transport_claim_due_cents']=sum(r['due_cents'] for r in t['rows']);metrics['vehicle_transport_claim_refund_cents']=sum(r['refund_cents'] for r in t['rows'])
    metrics['vehicle_transport_claim_adjustments_pending']=sum(r['pending_found_adjustment'] for r in t['rows'])
    from .reconciliation_service import settlement_rows
    offsets=defaultdict(int)
    for r in settlement_rows(db,user)['settlements']:offsets[r['origin_kind'],r['origin_id']]+=r['amount_cents']
    t=new('vehicle_transport_clearing','当前原车损失与找回净往来',['门店','对方店','原调拨','往来原类型','原金额（元）','实际双方结清（元）','仍待清算（元）'])
    for r in data['clearing']:
        off=offsets[r['origin_kind'],r['id']];net=r['amount_cents']+off
        put(t,r,[stores.get(r['store_id'],''),stores.get(r['counterparty_store_id'],''),r['number'],
            '原损失承担' if r['origin_kind']=='vehicle_loss' else '找回资产归属及承担冲回',yuan(r['amount_cents']),yuan(off),yuan(net)],
            amount_cents=net,original_cents=r['amount_cents'],offset_cents=off,origin_kind=r['origin_kind'])
    bars(t,[('amount_cents','净应收，负为应付')],DEFINITIONS[2]);metrics['vehicle_transport_clearing_net_cents']=sum(r['amount_cents'] for r in t['rows'])
    t=new('vehicle_transport_pending','当前原VIN差异及找回待办',['原资产门店','原调拨','VIN','差异阶段','原损失已记'])
    from .vehicle_transport_service import STATUS_LABELS
    for r in data['pending']:put(t,r,[stores.get(r['store_id'],''),r['number'],r['vin'],STATUS_LABELS[r['status']],'是' if r['loss_recorded'] else '否'],count=1)
    bars(t,[('count','原VIN差异数')],'按原发出方只计一次；差异待办不等于库内车辆。','count');metrics['vehicle_transport_pending_count']=len(t['rows'])
    return dict(date_from=start.isoformat(),date_to=end.isoformat(),as_of=as_of(),tables=tables,charts=charts,metrics=metrics,definitions=DEFINITIONS)
