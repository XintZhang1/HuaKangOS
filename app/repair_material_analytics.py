"""Actual repair issues/returns, original quote semi-joins and frozen model context."""
from collections import defaultdict
from fastapi import HTTPException
from sqlalchemy import select,or_
from .db import today
from .models import Store
from .flow_models import Case,Item,StockMove,FlowEvent
from .repair_models import RepairStock,RepairQuote,RepairLine,RepairAuthorization
from .service_intake_models import RepairVehicleBinding
from .inventory_report_common import bounded,period,as_of,qty,yuan,route,table,MONEY_ROLES

DEFINITION=('按原 StockMove 实际业务日统计，领料为正、原退为负；净领料数量和原成本不是报价量、配件售价或已确认施工耗用。'
 '车型只使用维修绑定时冻结的名称，旧绑定不补猜。作业筛选表示原领料授权报价包含该作业，每笔原流水只出现一次，不表示配件成本已分配给该作业。')


def build_repair_materials(db,user,start=None,end=None,case_id=None,item_id=None,model_name=None,work_item_id=None):
    start,end=period(user,start,end);money=user.role in MONEY_ROLES
    from .flow_engine import case_query
    case_stmt=case_query(user).where(Case.kind=='repair')
    if case_id:case_stmt=case_stmt.where(Case.id==case_id)
    cases={c.id:c for c in bounded(db,Case,case_stmt)}
    if case_id and case_id not in cases:raise HTTPException(404,'当前授权范围没有该维修原单')
    if item_id and not db.scalar(select(Item.id).where(Item.id==item_id)):raise HTTPException(404,'当前授权范围没有该物资')
    ids=list(cases);stores=dict(db.execute(select(Store.id,Store.name)).all())
    bindings={b.case_id:b for b in bounded(db,RepairVehicleBinding,select(RepairVehicleBinding).where(RepairVehicleBinding.case_id.in_(ids)))}
    snapshots=defaultdict(list)
    for event in bounded(db,FlowEvent,select(FlowEvent).where(FlowEvent.case_id.in_(ids),FlowEvent.action=='repair_vehicle_model_snapshot')):snapshots[event.case_id].append(event)
    model_context={};context_errors={}
    for cid,case in cases.items():
        binding=bindings.get(cid);events=snapshots[cid]
        if not events:model_context[cid]=None;continue
        data=events[0].detail or {}
        if len(events)!=1 or not binding or data.get('schema_version')!=1 or type(data.get('customer_vehicle_version')) is not int or data['customer_vehicle_version']<1 or data.get('customer_vehicle_id')!=binding.customer_vehicle_id or data.get('vin')!=binding.vin or not isinstance(data.get('model_name'),str) or not data['model_name'].strip():
            model_context[cid]=None;context_errors[cid]='车型冻结事件与原车辆绑定不一致'
        else:model_context[cid]=data['model_name']
    quotes={q.id:q for q in bounded(db,RepairQuote,select(RepairQuote).where(RepairQuote.case_id.in_(ids)))}
    lines=bounded(db,RepairLine,select(RepairLine).where(RepairLine.quote_id.in_(quotes)));line_index={(l.quote_id,l.line_key):l for l in lines}
    works=defaultdict(dict)
    for l in lines:
        if l.kind=='work':works[l.quote_id][l.work_item_id]=l.code+' · '+l.name
    authorizations={a.quote_id:a for a in bounded(db,RepairAuthorization,select(RepairAuthorization).where(RepairAuthorization.quote_id.in_(quotes)))}
    stocks=bounded(db,RepairStock,select(RepairStock).where(RepairStock.case_id.in_(ids)));stock_by_id={s.id:s for s in stocks};by_move={s.stock_move_id:s for s in stocks}
    children={c.id:c for c in bounded(db,Case,select(Case).where(Case.parent_id.in_(ids),Case.kind.in_(['material_issue','material_return'])))}
    movements=bounded(db,StockMove,select(StockMove).where(or_(StockMove.case_id.in_(ids),StockMove.case_id.in_(children))))
    moves={m.id:m for m in movements};facts=[];issues=[]
    items={i.id:i for i in bounded(db,Item,select(Item).where(Item.id.in_({m.item_id for m in movements})))}
    def issue(cid,message,source=None):issues.append({'case_id':cid,'source_id':source,'message':message})
    for s in stocks:
        if s.stock_move_id not in moves:issue(s.case_id,'维修领退料缺少本店原库存流水',s.stock_move_id)
    returns=defaultdict(list)
    for s in stocks:
        if s.original_id:returns[s.original_id].append(s)
    for origin_id,children_stock in returns.items():
        original=stock_by_id.get(origin_id)
        if not original or original.original_id or sum(-s.quantity_milli for s in children_stock)>original.quantity_milli or sum(-s.value_cents for s in children_stock)>original.value_cents:
            for s in children_stock:issue(s.case_id,'原领料退回的累计数量或原成本不守恒',s.stock_move_id)
        elif sum(-s.quantity_milli for s in children_stock)==original.quantity_milli and sum(-s.value_cents for s in children_stock)!=original.value_cents:
            issue(original.case_id,'原领料全部退回后仍有未冲回的原成本',original.stock_move_id)
    for m in movements:
        cid=m.case_id if m.case_id in cases else children[m.case_id].parent_id
        if m.purpose not in {'repair_issue_v3','repair_return_v3','issue','return'}:continue
        s=by_move.get(m.id);line=None;quote=None;errors=[];historical=False
        if m.business_date>today():errors.append('实际领退日期晚于今天')
        if m.purpose.startswith('repair_'):
            if not s:errors.append('原库存流水缺少维修明细关联')
            else:
                quote=quotes.get(s.quote_id);line=line_index.get((s.quote_id,s.line_key));auth=authorizations.get(s.quote_id)
                if not quote or quote.case_id!=cid or not line or line.kind!='part' or line.item_id!=m.item_id:errors.append('原报价配件行与领料关联不一致')
                if not auth or not quote or auth.quote_digest!=quote.digest:errors.append('原领料报价缺少对应冻结客户授权')
                if (s.case_id,s.store_id,s.quantity_milli,s.value_cents)!=(cid,m.store_id,-m.quantity_milli,-m.value_cents):errors.append('维修领退料与原库存数量成本不一致')
                if s.original_id:
                    orig=stock_by_id.get(s.original_id);source=moves.get(orig.stock_move_id) if orig else None
                    if not orig or orig.original_id or orig.case_id!=cid or orig.quote_id!=s.quote_id or orig.line_key!=s.line_key or m.original_id!=orig.stock_move_id or m.purpose!='repair_return_v3' or not source or m.business_date<source.business_date:errors.append('原退未关联同一维修原领料及原日期')
                elif m.purpose!='repair_issue_v3' or m.original_id:errors.append('原领料方向或来源错误')
        else:
            historical=True
            if m.case_id not in children:errors.append('历史领退料缺少明确维修子单')
            if m.purpose=='return':
                original=moves.get(m.original_id)
                if not original or original.purpose!='issue' or original.case_id not in children or children[original.case_id].parent_id!=cid or original.item_id!=m.item_id or m.business_date<original.business_date:errors.append('历史原退缺少本维修原领料')
        if (m.purpose in {'issue','repair_issue_v3'} and (m.quantity_milli>=0 or m.value_cents>0)) or (m.purpose in {'return','repair_return_v3'} and (m.quantity_milli<=0 or m.value_cents<0)):errors.append('原领退料数量或成本方向错误')
        for message in errors:issue(cid,message,m.id)
        if cid in context_errors:issue(cid,context_errors[cid],m.id)
        item=items.get(m.item_id)
        if not item:issue(cid,'原配件档案不在当前授权范围',m.id)
        facts.append({'case_id':cid,'store_id':m.store_id,'number':cases[cid].number,'source_id':m.id,'repair_stock_id':s.id if s else None,'original_source_id':m.original_id,
          'date':m.business_date.isoformat(),'item_id':m.item_id,'code':line.code if line else item.sku if item else '来源不足','name':line.name if line else item.name if item else '来源不足',
          'unit':line.unit if line else item.unit if item else '未知','model_name':model_context[cid],'quote_id':quote.id if quote else None,'quote_revision':quote.revision if quote else None,
          'work_items':works[quote.id] if quote else {},'quantity_milli':-m.quantity_milli,'value_cents':-m.value_cents,
          'kind':'退料' if m.quantity_milli>0 else '领料','context_note':'历史原库存流水；无报价作业维度' if historical else ''})
    # Keep filters based on actual original facts. Work membership is a semi-join:
    # two work lines never multiply the same physical material posting.
    options={'cases':[{'id':cid,'label':cases[cid].number} for cid in sorted({f['case_id'] for f in facts})],
      'items':[{'id':iid,'label':next(f['code']+' · '+f['name'] for f in facts if f['item_id']==iid)} for iid in sorted({f['item_id'] for f in facts})],
      'models':sorted({f['model_name'] for f in facts if f['model_name']}),
      'work_items':[{'id':wid,'label':next(f['work_items'][wid] for f in facts if wid in f['work_items'])} for wid in sorted({wid for f in facts for wid in f['work_items']})]}
    if work_item_id and not any(o['id']==work_item_id for o in options['work_items']):raise HTTPException(404,'获权原领料报价中没有该作业')
    if model_name and model_name!='__unknown__' and model_name not in options['models']:raise HTTPException(404,'获权原领料没有该冻结车型；当前档案名称不能替代历史车型')
    selected=[f for f in facts if start.isoformat()<=f['date']<=end.isoformat() and (not case_id or f['case_id']==case_id) and (not item_id or f['item_id']==item_id)
      and (not model_name or (f['model_name'] is None if model_name=='__unknown__' else f['model_name']==model_name)) and (not work_item_id or work_item_id in f['work_items'])]
    selected.sort(key=lambda f:(f['date'],f['source_id']))
    # Source issues remain visible even when the broken relation prevents a
    # requested dimension from matching; a filter must not create false completeness.
    issues=[i for i in issues if not case_id or i['case_id']==case_id];complete=not issues
    totals=defaultdict(lambda:{'issued_milli':0,'returned_milli':0,'net_milli':0,'issued_cents':0,'returned_cents':0,'net_cents':0})
    for f in selected:
        key=(f['store_id'],f['item_id'],f['code'],f['name'],f['unit'],f['model_name']);t=totals[key]
        t['issued_milli']+=max(f['quantity_milli'],0);t['returned_milli']+=max(-f['quantity_milli'],0);t['net_milli']+=f['quantity_milli']
        t['issued_cents']+=max(f['value_cents'],0);t['returned_cents']+=max(-f['value_cents'],0);t['net_cents']+=f['value_cents']
    summary=[]
    for k,t in totals.items():summary.append(dict(zip(('store_id','item_id','code','name','unit','model_name'),k))|t)
    tables={};balance=table('实际维修领退料净量'+('及原成本' if money else ''),['门店','配件编码','配件','单位','历史冻结车型','实际领量','实际退量','期间净领量']+(['原领成本（元）','原退成本（元）','期间净领成本（元）'] if money else []));tables['repair_material_totals']=balance
    for r in summary:balance['rows'].append({'values':[stores.get(r['store_id'],''),r['code'],r['name'],r['unit'],r['model_name'] or '历史车型未知']+[qty(r[k]) for k in ('issued_milli','returned_milli','net_milli')]+([yuan(r[k]) for k in ('issued_cents','returned_cents','net_cents')] if money else []),
      'quantity_milli':r['net_milli'],**({'amount_cents':r['net_cents']} if money else {})})
    detail=table('期间实际领退料原始行',['门店','原维修单','实际日期','动作','配件编码','配件','单位','历史冻结车型','原报价版本','原报价包含作业（不是耗用分摊）','原库存流水','原领流水','有符号净领量']+(['有符号原成本（元）'] if money else []));tables['repair_material_movements']=detail
    for f in selected:detail['rows'].append({'values':[stores.get(f['store_id'],''),f['number'],f['date'],f['kind'],f['code'],f['name'],f['unit'],f['model_name'] or '历史车型未知',f['quote_revision'] or '无报价维度','；'.join(f['work_items'].values()) or '未知',f['source_id'],f['original_source_id'] or '原领',qty(f['quantity_milli'])]+([yuan(f['value_cents'])] if money else []),'route':route(db,f['case_id']),'quantity_milli':f['quantity_milli'],**({'amount_cents':f['value_cents']} if money else {})})
    gap=table('领退料来源差异',['原维修单','原库存流水','需要核对的来源']);tables['repair_material_issues']=gap
    for i in issues:gap['rows'].append({'values':[cases[i['case_id']].number,i['source_id'] or '缺失',i['message']],'route':route(db,i['case_id'])})
    charts=[]
    if complete and money:
        labels=sorted({r['model_name'] or '历史车型未知' for r in summary});values=[sum(r['net_cents'] for r in summary if (r['model_name'] or '历史车型未知')==label) for label in labels]
        charts.append({'id':'repair_material_cost','title':'期间实际净领料原成本（按历史车型）','section':'repair','type':'bar','unit':'cents','labels':labels,'series':[{'name':'净领料原成本','values':values}],'table':'repair_material_totals','caption':'原退冲回原领成本。历史车型未知独列；不是配件售价、逐作业分摊或施工实际耗用。'})
    if not money:
        for f in selected:f.pop('value_cents')
        for r in summary:
            for k in ('issued_cents','returned_cents','net_cents'):r.pop(k)
    return {'date_from':start.isoformat(),'date_to':end.isoformat(),'as_of':as_of(),'complete':complete,'model_complete':all(f['model_name'] for f in selected),
      'can_money':money,'rows':summary,'details':selected,'issues':issues,'options':options,'tables':tables,'charts':charts,'definition':DEFINITION,'definitions':[DEFINITION],
      'metrics':{'repair_material_source_complete':complete,'repair_material_actual_net_cents':sum(r['net_cents'] for r in summary) if complete and money else None},
      'filters':{'case_id':case_id,'item_id':item_id,'model_name':model_name,'work_item_id':work_item_id}}
