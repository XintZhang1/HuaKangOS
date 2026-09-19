"""可视化数据层：把 analytics 的确定性指标整理成浏览器模块可直接渲染的只读结构。

契约（浏览器模块按此并行实现，字段名与单位不要随意改动）：
  * 所有金额都是整数“分”，永不返回 float，也不预先格式化成字符串；数量为普通整数；
  * trends[].dates 长度恒等于 days，每个 series 的 values 长度与之一致，无数据时补 0；
  * 无数据的维度仍返回完整结构（items 为空数组），不省略、不返回 null；
  * 本模块只读：不写入、不修改任何业务记录、审计日志或日报。

金额口径不在这里重算：窗口汇总全部来自 analytics.daily_metrics 的逐日结果。
"""
from collections import defaultdict
from datetime import date, timedelta
from .analytics import BASIS, approved, daily_metrics, detect, load_data
from .config import settings

CURRENCY = 'CNY'
MIN_DAYS, MAX_DAYS = 7, 365
BREAKDOWN_CAP, RANKING_CAP = 8, 10
OTHER_KEY, OTHER_LABEL = '__other__', '其他'

CASH_CATEGORY_LABELS = {
    'sale_collection': '销售收款', 'repair_collection': '维修收款', 'premium_collection': '保费代收',
    'commission': '保险佣金', 'vehicle_purchase': '车辆采购', 'operating_expense': '运营支出',
    'refund': '退款', 'capital': '资本金', 'loan': '借款', 'transfer': '内部转账',
}
REPAIR_TYPE_LABELS = {'maintenance': '保养', 'repair': '一般维修', 'insurance': '保险维修'}
SEVERITY_LABELS = {'high': '高风险', 'medium': '中风险', 'low': '低风险'}


def clamp_days(days: int) -> int:
    """契约：days 默认 90，越界收敛到 7..365（0 -> 7，1000 -> 365），不因此报错。"""
    return max(MIN_DAYS, min(MAX_DAYS, int(days)))


def notes() -> list:
    return [
        BASIS,
        '图表按所选期间的已审核记录汇总，只读，不改动任何数据。',
    ]


def kpi_specs() -> tuple:
    """(key, 中文名, unit, daily_metrics 字段, 是否期末快照, hint)

    与 /api/dashboard 相同的期末/累计规则：库存、超龄、应收是时点值取末日，
    其余为窗口内逐日累计。
    """
    return (
        ('delivery_amount', '交车金额', 'money', ('delivery_amount_cents',), False, ''),
        ('delivery_count', '交车台数', 'count', ('delivery_count',), False, ''),
        ('new_order_count', '新车订单', 'count', ('new_order_count',), False, ''),
        ('repair_completed_count', '维修完工台次', 'count', ('repair_completed_count',), False, ''),
        ('repair_amount', '维修金额', 'money', ('repair_amount_cents',), False, ''),
        ('gross_difference', '毛利', 'money', ('gross_difference_cents',), False,
         '结算金额减录入成本，不含税费、返利、工资、折旧，不等于净利润。'),
        ('policy_premium', '保单保费', 'money', ('policy_premium_cents',), False, '代收保费，不算门店收入。'),
        ('expected_commission', '预计佣金', 'money', ('expected_commission_cents',), False, ''),
        ('net_cash', '净现金流', 'money', ('net_cash_cents',), False, '内部转账不算。'),
        ('stock_count', '库存台数', 'count', ('stock_count',), True, ''),
        ('aging_stock_count', '超龄库存', 'count', ('aging_stock_count',), True,
         '库龄超过 %d 天。' % settings.inventory_aging),
        ('receivable', '应收合计', 'money', ('sales_receivable_cents', 'repair_receivable_cents'), True,
         '销售和维修待收款，只含已审核。'),
    )


def trend_specs() -> tuple:
    """(组 id, 中文标题, unit, ((series key, 中文名, daily_metrics 字段), ...))"""
    return (
        ('money', '金额走势', 'money', (
            ('delivery_amount', '交车金额', 'delivery_amount_cents'),
            ('repair_amount', '维修金额', 'repair_amount_cents'),
            ('gross_difference', '毛利', 'gross_difference_cents'),
        )),
        ('volume', '台次走势', 'count', (
            ('delivery_count', '交车台数', 'delivery_count'),
            ('repair_completed_count', '维修完工台次', 'repair_completed_count'),
            ('new_order_count', '新车订单', 'new_order_count'),
        )),
        ('cashflow', '现金流走势', 'money', (
            ('cash_in', '现金流入', 'cash_in_cents'),
            ('cash_out', '现金流出', 'cash_out_cents'),
            ('net_cash', '净现金流', 'net_cash_cents'),
        )),
        ('stock', '库存走势', 'count', (
            ('stock_count', '在库台数', 'stock_count'),
            ('available_count', '可售台数', 'available_count'),
            ('reserved_count', '预留台数', 'reserved_count'),
            ('aging_stock_count', '超龄库存', 'aging_stock_count'),
        )),
    )


def _kpis(series: list) -> list:
    last = series[-1]
    items = []
    for key, label, unit, metrics, snapshot, hint in kpi_specs():
        total = sum(last[name] for name in metrics) if snapshot else sum(day[name] for day in series for name in metrics)
        items.append({'key': key, 'label': label, 'unit': unit, 'value': int(total), 'hint': hint})
    return items


def _trends(series: list) -> list:
    dates = [day['date'] for day in series]
    groups = []
    for group_id, title, unit, specs in trend_specs():
        groups.append({
            'id': group_id, 'title': title, 'unit': unit, 'axis': 'date', 'dates': list(dates),
            'series': [{'key': key, 'label': label, 'values': [int(day[metric]) for day in series]}
                       for key, label, metric in specs],
        })
    return groups


def _items(totals: dict, labels: dict, cap: int, fold: bool = False, share: bool = False) -> list:
    """按值降序、按 key 稳定排序。

    契约：只有 breakdowns 折叠尾部为“其他”（余额非零时才追加），rankings 直接截断到 cap；
    share 只在 breakdowns 上出现，且在折叠之后按最终 items 计算，因此合计约等于 1。
    """
    items = [{'key': key, 'label': labels.get(key) or key or '未填写', 'value': int(value)}
             for key, value in totals.items() if value]
    items.sort(key=lambda item: (-item['value'], item['key']))
    if len(items) > cap:
        remainder = sum(item['value'] for item in items[cap:]) if fold else 0
        items = items[:cap]
        if remainder:
            items.append({'key': OTHER_KEY, 'label': OTHER_LABEL, 'value': int(remainder)})
            items.sort(key=lambda item: (-item['value'], item['key']))
    if not share:
        return items
    total = sum(item['value'] for item in items)
    return [{**item, 'share': (item['value'] / total) if total else 0.0} for item in items]


def _group(group_id: str, title: str, chart: str, unit: str, dimension: str, items: list) -> dict:
    return {'id': group_id, 'title': title, 'chart': chart, 'unit': unit, 'dimension': dimension, 'items': items}


def _on_hand(data, day: date) -> list:
    """与 analytics.daily_metrics 相同的在库口径：已审核入库且截至 day 尚未交车的车辆。"""
    allocated = {row.vehicle_id: row for row in approved(data, 'sales', day)}
    return [row for row in approved(data, 'vehicles', day)
            if row.id not in allocated or not allocated[row.id].delivery_date or allocated[row.id].delivery_date > day]


def _cash_by_category(data, start: date, day: date) -> dict:
    totals = defaultdict(int)
    for row in approved(data, 'cash', day):
        if row.business_date >= start:
            totals[row.category] += row.amount_cents
    return totals


def _stock_by_brand(data, day: date) -> dict:
    totals = defaultdict(int)
    for row in _on_hand(data, day):
        totals[row.brand] += row.purchase_cost_cents
    return totals


def _repairs_by_type(data, start: date, day: date) -> dict:
    totals = defaultdict(int)
    for row in approved(data, 'repairs', day):
        if row.repair_stage == 'completed' and row.completion_date and start <= row.completion_date <= day:
            totals[row.repair_type] += 1
    return totals


def _findings_by_severity(findings: list) -> dict:
    totals = defaultdict(int)
    for finding in findings:
        totals[finding['severity']] += 1
    return totals


def _sales_by_person(data, start: date, day: date) -> dict:
    totals = defaultdict(int)
    for row in approved(data, 'sales', day):
        if row.sale_stage == 'delivered' and row.delivery_date and start <= row.delivery_date <= day:
            totals[row.salesperson] += row.contract_amount_cents
    return totals


def _policies_by_insurer(data, start: date, day: date) -> dict:
    totals = defaultdict(int)
    for row in approved(data, 'policies', day):
        if row.business_date >= start:
            totals[row.insurer] += row.premium_cents
    return totals


def _breakdowns(data, start: date, day: date, findings: list) -> list:
    return [
        _group('cash_category', '收支分类构成', 'pie', 'money', 'category',
               _items(_cash_by_category(data, start, day), CASH_CATEGORY_LABELS, BREAKDOWN_CAP, fold=True, share=True)),
        _group('stock_brand', '库存品牌构成', 'pie', 'money', 'brand',
               _items(_stock_by_brand(data, day), {}, BREAKDOWN_CAP, fold=True, share=True)),
        _group('repair_type', '维修类型构成', 'pie', 'count', 'repair_type',
               _items(_repairs_by_type(data, start, day), REPAIR_TYPE_LABELS, BREAKDOWN_CAP, fold=True, share=True)),
        _group('finding_severity', '复核问题严重度', 'pie', 'count', 'severity',
               _items(_findings_by_severity(findings), SEVERITY_LABELS, BREAKDOWN_CAP, fold=True, share=True)),
    ]


def _rankings(data, start: date, day: date) -> list:
    return [
        _group('salesperson', '销售顾问业绩', 'bar', 'money', 'salesperson',
               _items(_sales_by_person(data, start, day), {}, RANKING_CAP)),
        _group('brand_stock', '品牌库存金额', 'bar', 'money', 'brand',
               _items(_stock_by_brand(data, day), {}, RANKING_CAP)),
        _group('insurer', '保险公司保费', 'bar', 'money', 'insurer',
               _items(_policies_by_insurer(data, start, day), {}, RANKING_CAP)),
    ]


def visualization(db, day: date, days: int) -> dict:
    """只读载荷。调用方已完成登录校验与门店范围绑定，这里只按当前 scope 读取。"""
    days = clamp_days(days)
    start = day - timedelta(days=days - 1)
    data = load_data(db, day)
    # 每个自然日一行，口径与 /api/dashboard 一致；不在本模块重算任何金额。
    series = [daily_metrics(data, day - timedelta(days=offset)) for offset in range(days - 1, -1, -1)]
    findings = detect(data, day)
    return {
        'end_date': day.isoformat(),
        'start_date': start.isoformat(),
        'days': days,
        'currency': CURRENCY,
        'kpis': _kpis(series),
        'trends': _trends(series),
        'breakdowns': _breakdowns(data, start, day, findings),
        'rankings': _rankings(data, start, day),
        'notes': notes(),
    }