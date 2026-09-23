"""A creation cohort with current fulfilment; never mix it with period receipts."""
from collections import defaultdict
from sqlalchemy import select
from .models import Store
from .db import today
from .flow_models import Case, FlowEvent, StockMove
from .procurement_models import PurchaseOrder, PurchaseLine, PurchaseReceipt, PurchaseReturnPosting
from .inventory_report_common import bounded, period, local_date, yuan, qty, as_of, route, table, MONEY_ROLES

DEFINITION = ('期间按原采购申请事件的本地日期选择订货批次，履约数量和金额为截至本次查询时的累计事实，'
              '不是截至期间末日的历史状态，也不是期间到货统计。原订货＝累计实际到货＋仍待到货＋已关闭未到货＋待批准；'
              '退货单列、不重开原订货余量，净留存＝到货－实际退货。数量按原单位分别统计，审批、付款和待退申请不计实际到退货。')
QUANTITY_KEYS = ('ordered', 'received', 'open', 'closed', 'pending', 'returned', 'retained')
LABELS = ['原订货', '累计到货', '仍待到货', '已关闭未到', '待批准', '实际退货', '净留存']


def build_procurement_cohort(db, user, start=None, end=None):
    start, end = period(user, start, end)
    can_money = user.role in MONEY_ROLES
    stores = dict(db.execute(select(Store.id, Store.name)).all())
    cases = {r.id: r for r in bounded(db, Case, select(Case).where(Case.kind.in_(['procurement', 'purchase'])))}
    headers = {r.id: r for r in bounded(db, PurchaseOrder)}
    events = defaultdict(lambda: defaultdict(list))
    for e in bounded(db, FlowEvent, select(FlowEvent).where(FlowEvent.case_id.in_(cases), FlowEvent.action.in_(['procurement_create', 'procurement_approve', 'procurement_close_receiving']))):
        events[e.case_id][e.action].append(e)
    selected = {}; issues = []
    for key, case in cases.items():
        if case.kind == 'purchase':
            if start <= case.business_date <= end:
                issues.append({'case_id': key, 'number': case.number, 'store_id': case.store_id,
                               'issue': '历史简表采购：仅按原登记日期列出，缺少不可变逐行订货来源，不混入新订货履约合计'})
            continue
        source = events[key]['procurement_create']
        if len(source) != 1:
            issues.append({'case_id': key, 'number': case.number, 'store_id': case.store_id,
                           'issue': '缺少唯一原采购申请事件，无法确认所属订货期间'})
            continue
        day = local_date(source[0].occurred_at)
        if start <= day <= end: selected[key] = (case, day)
    lines = bounded(db, PurchaseLine, select(PurchaseLine).where(PurchaseLine.case_id.in_(selected)))
    receipts = bounded(db, PurchaseReceipt, select(PurchaseReceipt).where(PurchaseReceipt.case_id.in_(selected)))
    returns = bounded(db, PurchaseReturnPosting, select(PurchaseReturnPosting).where(PurchaseReturnPosting.case_id.in_(selected)))
    moves = {m.id: m for m in bounded(db, StockMove, select(StockMove).where(StockMove.case_id.in_(selected), StockMove.purpose.in_(['procurement_receipt', 'procurement_return'])))}
    by_line = defaultdict(list); by_receipt = defaultdict(list)
    for r in receipts: by_line[r.line_id].append(r)
    for r in returns: by_receipt[r.receipt_id].append(r)
    rows = []; details = []; covered_moves = set()
    for line in lines:
        case, day = selected[line.case_id]; header = headers.get(case.id); errors = []
        approved = len(events[case.id]['procurement_approve']) == 1
        if not header: errors.append('缺少原供应商采购约定')
        if day != case.business_date: errors.append('原申请日期与登记日期不一致')
        if len(events[case.id]['procurement_approve']) > 1: errors.append('重复采购批准来源')
        values = {k: {'quantity_milli': 0, 'value_cents': 0} for k in QUANTITY_KEYS}
        values['ordered'] = {'quantity_milli': line.quantity_milli, 'value_cents': line.amount_cents}
        for receipt in by_line[line.id]:
            move = moves.get(receipt.stock_move_id); covered_moves.add(receipt.stock_move_id)
            if not move or (move.case_id, move.item_id, move.purpose, move.quantity_milli, move.value_cents) != (case.id, line.item_id, 'procurement_receipt', receipt.quantity_milli, receipt.value_cents):
                errors.append('实际到货与原库存流水不一致')
            for k, amount in [('quantity_milli', receipt.quantity_milli), ('value_cents', receipt.value_cents)]: values['received'][k] += amount
            if move:
                if move.business_date < day: errors.append('到货日期早于原订货申请')
                if move.business_date > today(): errors.append('实际到货日期晚于今天')
                details.append({'case_id': case.id, 'store_id': case.store_id, 'number': case.number, 'line_id': line.id, 'sku': line.sku,
                                'date': move.business_date.isoformat(), 'kind': 'receive', 'label': '实际到货', 'source_id': receipt.id,
                                'stock_move_id': move.id, 'quantity_milli': receipt.quantity_milli, 'value_cents': receipt.value_cents, 'unit': line.unit})
            rq = rv = 0
            for returned in by_receipt[receipt.id]:
                rm = moves.get(returned.stock_move_id); covered_moves.add(returned.stock_move_id)
                if not rm or (rm.case_id, rm.item_id, rm.purpose, rm.original_id, rm.quantity_milli, rm.value_cents) != (case.id, line.item_id, 'procurement_return', receipt.stock_move_id, -returned.quantity_milli, -returned.value_cents):
                    errors.append('实际退货与原验收流水不一致')
                rq += returned.quantity_milli; rv += returned.value_cents
                if rm:
                    if move and rm.business_date < move.business_date: errors.append('实际退货日期早于原到货')
                    if rm.business_date > today(): errors.append('实际退货日期晚于今天')
                    details.append({'case_id': case.id, 'store_id': case.store_id, 'number': case.number, 'line_id': line.id, 'sku': line.sku,
                                    'date': rm.business_date.isoformat(), 'kind': 'return', 'label': '实际退货', 'source_id': returned.id,
                                    'stock_move_id': rm.id, 'quantity_milli': -returned.quantity_milli, 'value_cents': -returned.value_cents, 'unit': line.unit})
            if rq > receipt.quantity_milli or rv > receipt.value_cents: errors.append('原批次累计退货超过实际到货')
            values['returned']['quantity_milli'] += rq; values['returned']['value_cents'] += rv
        remaining = {k: values['ordered'][k]-values['received'][k] for k in ('quantity_milli', 'value_cents')}
        if any(v < 0 for v in remaining.values()): errors.append('累计到货超过原采购约定')
        if values['received']['quantity_milli'] and not approved: errors.append('已有实际到货但缺少唯一采购批准来源')
        closed = case.state in {'cancelled', 'rejected'} or bool(case.data.get('receiving_closed'))
        if closed and remaining['quantity_milli'] and case.state not in {'cancelled', 'rejected'} and len(events[case.id]['procurement_close_receiving']) != 1:
            errors.append('已关闭未到余量缺少原关闭确认')
        values['closed' if closed else 'open' if approved else 'pending'] = remaining
        values['retained'] = {k: values['received'][k]-values['returned'][k] for k in ('quantity_milli', 'value_cents')}
        for error in dict.fromkeys(errors): issues.append({'case_id': case.id, 'number': case.number, 'store_id': case.store_id, 'line_id': line.id, 'issue': error})
        rows.append({'case_id': case.id, 'store_id': case.store_id, 'number': case.number, 'line_id': line.id, 'date': day.isoformat(),
                     'supplier': header.supplier_name if header else '来源缺失', 'sku': line.sku, 'name': line.item_name, 'unit': line.unit,
                     'status': '已关闭' if closed else '已批准待履约' if approved else '待批准', 'reconciled': not errors,
                     'issues': list(dict.fromkeys(errors)), **values})
    for key, (case, _) in selected.items():
        if not any(l.case_id == key for l in lines): issues.append({'case_id': key, 'number': case.number, 'store_id': case.store_id, 'issue': '原采购单缺少订货明细'})
    for move in moves.values():
        if move.id not in covered_moves:
            case = selected[move.case_id][0]
            issues.append({'case_id': case.id, 'number': case.number, 'store_id': case.store_id, 'issue': '库存到退货流水缺少对应原采购确认记录'})
    complete = not issues
    tables = {}
    columns = ['门店', '采购单', '申请日期', '供应商', '物资编码', '物资名称', '单位', '当前进度']+[label+'数量' for label in LABELS]
    if can_money: columns += [label+'金额（元）' for label in LABELS]
    columns += ['来源核对']
    summary = table('物资采购订货批次履约', columns); tables['procurement_cohort_lines'] = summary
    for r in rows:
        display = [stores.get(r['store_id'], ''), r['number'], r['date'], r['supplier'], r['sku'], r['name'], r['unit'], r['status']]+[qty(r[k]['quantity_milli']) for k in QUANTITY_KEYS]
        if can_money: display += [yuan(r[k]['value_cents']) for k in QUANTITY_KEYS]
        summary['rows'].append({'values': display+['已核对' if r['reconciled'] else '来源差异待核对'], 'route': route(db, r['case_id']),
                                **{k+'_milli': r[k]['quantity_milli'] for k in QUANTITY_KEYS},
                                **({k+'_cents': r[k]['value_cents'] for k in QUANTITY_KEYS} if can_money else {})})
    detail_table = table('所选订货批次累计到退货原账', ['门店', '采购单', '实际日期', '物资编码', '实际业务', '原确认记录', '库存流水', '数量', '单位']+(['库存价值变化（元）'] if can_money else []))
    tables['procurement_cohort_postings'] = detail_table
    details.sort(key=lambda r: (r['date'], r['stock_move_id']))
    for r in details:
        detail_table['rows'].append({'values': [stores.get(r['store_id'], ''), r['number'], r['date'], r['sku'], r['label'], r['source_id'], r['stock_move_id'], qty(r['quantity_milli']), r['unit']]+([yuan(r['value_cents'])] if can_money else []),
                                     'route': route(db, r['case_id']), 'quantity_milli': r['quantity_milli'], **({'amount_cents': r['value_cents']} if can_money else {})})
    problem_table = table('原采购来源差异及历史简表', ['门店', '原采购单', '差异说明']); tables['procurement_cohort_issues'] = problem_table
    for r in issues: problem_table['rows'].append({'values': [stores.get(r['store_id'], ''), r['number'], r['issue']], 'route': route(db, r['case_id'])})
    charts = []
    if complete:
        for unit in sorted({r['unit'] for r in rows}):
            key = 'procurement_cohort_unit_'+str(len(charts))
            tables[key] = {'title': '物资订货履约（'+unit+'）', 'headers': summary['headers'],
                           'rows': [shown for original, shown in zip(rows, summary['rows']) if original['unit'] == unit], 'chart_only': True}
            charts.append({'id': 'procurement_cohort_'+str(len(charts)), 'title': '订货履约数量（'+unit+'）', 'section': 'inventory', 'type': 'bar', 'unit': 'quantity',
                           'labels': LABELS, 'series': [{'name': unit, 'values': [sum(r[k]['quantity_milli'] for r in rows if r['unit'] == unit)/1000 for k in QUANTITY_KEYS]}],
                           'table': key, 'caption': '只包含单位为“'+unit+'”的行。'+DEFINITION})
    metrics = {'procurement_cohort_order_count': len(selected), 'procurement_cohort_line_count': len(rows),
               'procurement_cohort_complete': complete, 'procurement_cohort_issue_count': len(issues)}
    if can_money:
        metrics.update({'procurement_cohort_'+k+'_cents': sum(r[k]['value_cents'] for r in rows) if complete else None for k in QUANTITY_KEYS})
    else:
        for r in rows:
            for k in QUANTITY_KEYS: r[k].pop('value_cents')
        for r in details: r.pop('value_cents')
    return {'date_from': start.isoformat(), 'date_to': end.isoformat(), 'as_of': as_of(), 'can_money': can_money,
            'complete': complete, 'rows': rows, 'details': details, 'issues': issues, 'tables': tables, 'charts': charts,
            'metrics': metrics, 'definition': DEFINITION, 'definitions': [DEFINITION]}
