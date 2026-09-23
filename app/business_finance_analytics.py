"""Business finance views preserve one cash source and original customer scope."""
from collections import defaultdict
from sqlalchemy import select
from .flow_models import Case,Customer,PaymentLink
from .models import CashEntry
from .business_finance_models import FinanceOrder,FinanceAdvance,FinanceAdvanceEntry,FinanceStatement,FinanceStatementLine,FinanceCashBatch,FinanceCashAllocation,FinanceCorrection,FinanceStoredCorrection,FinanceReturnReceivable,FinanceReturnTargetRevision
from .business_finance_service import LABELS,superseded_cash_ids,adjustment_cash_ids
from .operations_analytics import local_day


def build_business_finance_analytics(db,user,start,end,cases,stores,bounded,yuan):
    aggregate=bool(getattr(user,'_aggregate_scope',False) or len([sid for sid in db.info.get('store_scope',()) if sid])>1)
    orders={o.case_id:o for o in bounded(db,FinanceOrder)}
    byid={c.id:c for c in cases};byid.update({c.id:c for c in bounded(db,Case,select(Case).where(Case.id.in_(orders)))})
    customers={c.id:c for c in bounded(db,Customer)};cash={c.id:c for c in bounded(db,CashEntry)}
    tables={};charts=[];metrics={}
    def table(key,title,headers):tables[key]={'title':title,'headers':headers,'rows':[]};return tables[key]['rows']
    def add(target,case_id,values,amount,**extra):target.append({'values':values,'route':None if aggregate else {'type':'case','id':case_id},'amount_cents':amount,**extra})
    def number(key):return byid[key].number if key in byid else '原业务'
    def customer(key):return '本店客户' if aggregate else customers[key].name if key in customers else '供应方'
    def chart(key,title,rows,caption):
        total=defaultdict(int)
        for r in rows:total[r['values'][1]]+=r['amount_cents']
        labels=sorted(total);charts.append({'id':key,'title':title,'section':'finance','type':'bar','unit':'cents','labels':labels,
            'series':[{'name':'金额','values':[total[k] for k in labels]}],'table':key,'caption':caption})
    advances={a.id:a for a in bounded(db,FinanceAdvance)}
    current=table('finance_advances','当前本店客户预收余额',['原预收单','门店','客户','原登记（元）','未用余额（元）','批准占额（元）','可用余额（元）','累计更正（元）','有效原款（元）'])
    for a in advances.values():add(current,a.case_id,[number(a.case_id),stores.get(a.store_id,''),customer(a.customer_id),yuan(a.initial_cents),yuan(a.balance_cents),yuan(a.reserved_cents),yuan(a.balance_cents-a.reserved_cents),yuan(a.correction_cents),yuan(a.initial_cents+a.correction_cents)],a.balance_cents)
    chart('finance_advances','当前客户预收未用余额',current,'本店原登记预收加已批准误记更正差额，减已抵用及退款，加原单退回；占额仍在余额内。预收不是新增营业收入，不与集团会员本金混账。')
    metrics['business_finance_advance_balance_cents']=sum(r['amount_cents'] for r in current)
    movements=table('finance_advance_movements','期间原预收余额流水',['办理单','门店','日期','客户','事实','余额变动（元）'])
    labels={'receive':'原登记收到预收款','apply':'批准抵用原业务','refund':'未用原款实际退款','return':'原抵用回退余额','correction':'误记更正本金差额（非实际收退款）'}
    for e in bounded(db,FinanceAdvanceEntry):
        stamp=cash[e.cash_id].business_date if e.cash_id else local_day(e.occurred_at)
        if start<=stamp<=end:add(movements,e.case_id,[number(e.case_id),stores.get(e.store_id,''),stamp.isoformat(),customer(advances[e.advance_id].customer_id),labels[e.purpose],yuan(e.amount_cents)],e.amount_cents)
    chart('finance_advance_movements','期间预收余额变动',movements,'原现金收退按现金业务日；抵用、原抵用回退和更正差额按办理日。余额更正和抵用回退不是现金收付，不能再加到现金图。')
    statements={s.id:s for s in bounded(db,FinanceStatement)};allocations=list(bounded(db,FinanceCashAllocation));batches={b.id:b for b in bounded(db,FinanceCashBatch)}
    following={s.previous_id for s in statements.values() if s.previous_id};allocated_lines=defaultdict(int)
    for allocation in allocations:
        if allocation.statement_line_id:allocated_lines[allocation.statement_line_id]+=allocation.amount_cents
    frozen=table('finance_customer_statements','客户当前账单版本未分配额度',['客户月结单','门店','客户','原单','账单期间','冻结客户应收（元）','本版本已分配（元）','尚可分配（元）'])
    for line in bounded(db,FinanceStatementLine):
        s=statements[line.statement_id];o=orders[s.case_id]
        if s.id in following or o.status not in {'draft','approved'}:continue
        applied=allocated_lines[line.id];remaining=line.due_cents-applied
        add(frozen,s.case_id,[number(s.case_id),stores.get(s.store_id,''),customer(s.customer_id),line.snapshot['number'],s.starts_on.isoformat()+' 至 '+s.ends_on.isoformat(),yuan(line.due_cents),yuan(applied),yuan(remaining)],remaining)
    chart('finance_customer_statements','当前客户账单尚未分配额度',frozen,'仅最新且未完成账单。冻结账单额度不代表新增应收，也未减去后来直接在原业务收取的款项；办理时重新验证原业务余额，变化时追加重算。')
    effective=table('finance_allocations','期间集中实际收款逐单分配',['收款办理单','门店','真实到账日','客户原业务','分配金额（元）'])
    excluded=superseded_cash_ids(db)|adjustment_cash_ids(db)
    for a in allocations:
        b=batches[a.batch_id];c=cash[b.cash_id]
        if c.id in excluded or c.direction!='in' or not start<=c.business_date<=end:continue
        add(effective,b.case_id,[number(b.case_id),stores.get(b.store_id,''),c.business_date.isoformat(),number(a.case_id),yuan(a.amount_cents)],a.amount_cents,cash_id=c.id)
    chart('finance_allocations','期间集中收款原单分配',effective,'逐单列当前有效收款的业务分配。部分实退后更正只分配剩余净额；加原更正冻结的已实际退款才等于总原款。已被更正原款和误记反向调整排除，不另加一次现金。')
    changes=table('finance_corrections','期间追加的原收款误记更正',['更正办理单','门店','办理日','原误记（元）','正确重记（元）','明确真实到账日','更正差额（元）'])
    for fix in bounded(db,FinanceCorrection):
        c=byid[fix.case_id]
        processed=cash[batches[fix.reversing_batch_id].cash_id].business_date
        if not start<=processed<=end:continue
        original=cash[fix.original_cash_id];b=batches.get(fix.corrected_batch_id);actual=cash[b.cash_id] if b else None;amount=actual.amount_cents if actual else 0;delta=amount-original.amount_cents
        add(changes,c.id,[c.number,stores.get(c.store_id,''),processed.isoformat(),yuan(original.amount_cents),yuan(amount),actual.business_date.isoformat() if actual else '未到账，撤销误记',yuan(delta)],delta)
    for fix in bounded(db,FinanceStoredCorrection):
        c=byid[fix.case_id];processed=local_day(fix.occurred_at)
        if not start<=processed<=end:continue
        original=cash[fix.original_cash_id];actual=cash.get(fix.corrected_cash_id);amount=actual.amount_cents if actual else 0;delta=amount-original.amount_cents
        add(changes,c.id,[c.number,stores.get(c.store_id,''),processed.isoformat(),yuan(original.amount_cents),yuan(amount),actual.business_date.isoformat() if actual else '未到账，撤销误记',yuan(delta)],delta)
    chart('finance_corrections','期间办理的误记更正差额',changes,'按更正办理日追溯原误记与正确重记差额；不表示当日真实资金移动。实际现金仍按已冻结的真实到账日统计，原现金与反向调整保留可查。')
    other=table('finance_other_returns','当前其他入库原单退货应收',['应收办理单','门店','原实物退货','原成本（元）','当前批准目标（元）','实际净收款（元）','尚未收到（元）'])
    paid=defaultdict(int)
    for p in bounded(db,PaymentLink):paid[p.case_id]+=p.amount_cents*(1 if p.direction=='in' else -1)
    from .flow_models import StockMove
    moves={m.id:m for m in bounded(db,StockMove)}
    for r in bounded(db,FinanceReturnReceivable):
        from .business_finance_return_adjustments import effective_target
        target=effective_target(db,r);remaining=max(0,target-paid[r.case_id])
        add(other,r.case_id,[number(r.case_id),stores.get(r.store_id,''),number(moves[r.stock_move_id].case_id),yuan(r.value_cents),yuan(target),yuan(paid[r.case_id]),yuan(remaining)],remaining)
    chart('finance_other_returns','当前其他入库退货待收款',other,'只有已实际原单退货且独立批准的应收；采用追加修订后的目标，净收款扣除原款实际退款。超收应退另列，不能抵成负应收；保留原实物成本，批准不生成现金。')
    metrics['business_finance_other_return_due_cents']=sum(r['amount_cents'] for r in other)
    return {'tables':tables,'charts':charts,'metrics':metrics}
