"""Concise operating totals with authorized, same-scope drilldowns and exports."""
from datetime import date, timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from .db import get_db, today, utcnow
from .security import get_user

router = APIRouter(prefix='/api/business-records', tags=['实时多图经营看板'])


def _source_display(key, value, status=''):
    automatic = key.split(':', 1)[0] == 'operating_sales'
    state = 'known' if value is not None else 'awaiting_contract' if automatic else 'awaiting_approval'
    return {'data_source': 'automatic' if automatic else 'office', 'data_status': state,
        'status_label': ('自动汇总' if automatic else '已审核') if value is not None else
            '待核对合同信息' if automatic else '待审核'}


def _calendar_series(panel, start, end):
    by_day = {row['label']: row for row in panel['series']}
    series, current = [], start
    while current <= end:
        label = str(current)
        zero = panel.get('empty_is_zero', False)
        series.append(by_day.get(label, {'label': label, 'value': 0 if zero else None,
            'exact_value': '0' if zero else None, 'record_count': 0,
            'unknown_count': 0 if zero else 1, 'status': 'known' if zero else 'awaiting_approval'}))
        current += timedelta(days=1)
    panel['series'] = series
    return panel


@router.get('/dashboard-panels')
def dashboard_panels(mode: str = 'daily', day: date | None = None,
        date_from: date | None = None, date_to: date | None = None,
        brand: str = Query('', max_length=100), salesperson_id: int | None = Query(None, gt=0),
        group_by: str = '', db=Depends(get_db), user=Depends(get_user)):
    from .business_records import require_read
    from .business_record_report_generation import build, project
    from .business_record_reports import CATALOG_BY_KEY
    from .business_record_report_specs import can_view_sensitive_reports, can_view_dashboard
    require_read(user)
    if not can_view_dashboard(user):
        raise HTTPException(403, '可视化看板仅向当前授权门店的集团副总经理、董事长和系统管理员开放')
    if mode not in {'daily', 'monthly', 'range'}:
        raise HTTPException(422, '请选择日报、月报或日期范围')
    end = date_to or day or today()
    start = date_from or end.replace(day=1)
    if start > end or (end - start).days > 366:
        raise HTTPException(422, '请选择不超过一年的有效日期范围')
    grouping = group_by or ('store' if getattr(user, '_aggregate_scope', False) else 'salesperson')
    if grouping not in {'store', 'salesperson', 'brand'}:
        raise HTTPException(422, '请选择门店、销售顾问或品牌比较')
    flow_start = end if mode == 'daily' else start
    prefix = '当日' if mode == 'daily' else '期间累计'
    sources, projections = {}, {}

    def report(key, group, beginning, ending):
        base_key, _, selected = key.partition(':')
        identity = (key, group, beginning, ending)
        if identity in projections:
            return projections[identity]
        source_identity = (base_key, beginning, ending)
        try:
            if source_identity not in sources:
                # The same guarded source rows feed every number, trend and
                # comparison. Metric changes never broaden the store scope.
                sources[source_identity] = build(db, user, base_key, date_from=beginning,
                    date_to=ending, brand=brand, salesperson_id=salesperson_id,
                    group_by='group', snapshot_sources=True)
            source = sources[source_identity]
            definition = CATALOG_BY_KEY[base_key]
            result = project(definition, source['rows'], group_by=group,
                metric=selected or definition['default_metric'], updated_at=source['updated_at'])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        result['empty_is_zero'] = bool(definition.get('empty_is_zero'))
        value = result['grand_total'].get(result['metric'])
        result.update(group_by=group, date_from=str(beginning), date_to=str(ending),
            query={'report': key, 'date_from': str(beginning), 'date_to': str(ending),
                   'group_by': group, 'brand': brand, 'salesperson_id': salesperson_id},
            **_source_display(base_key, value))
        result['source_status'] = {'status': result['data_status'], 'record_count': result['record_count']}
        if group == 'day':
            _calendar_series(result, beginning, ending)
        projections[identity] = result
        return result

    specifications = [
        ('orders', prefix + '合同订单', 'operating_sales:orders', '台'),
        ('sales', prefix + '实销车辆', 'operating_sales:deliveries', '台'),
        ('vehicle_amount', prefix + '实销车辆金额', 'operating_sales:vehicle_amount', '元'),
        ('cash_count', prefix + '现金车消化', 'operating_sales:cash_count', '台'),
        ('cash_amount', prefix + '现金车消化金额', 'operating_sales:cash_amount', '元'),
    ]
    extension_specs = [
        ('insurance', '保险出单', 'operating_extensions:insurance_count', '单', 'insurance'),
        ('warranty', '延保出单', 'operating_extensions:warranty_count', '单', 'warranty'),
        ('total_loss', '全损出单', 'operating_extensions:total_loss_count', '单', 'total_loss'),
        ('products', '小产品出单', 'operating_extensions:product_count', '单', 'product'),
        ('trade_in', '置换', 'operating_extensions:trade_in_count', '台', 'trade_in'),
        ('finance', '金融放款车辆', 'operating_extensions:finance_count', '台', 'finance'),
    ]
    sensitive = can_view_sensitive_reports(user)
    if sensitive:
        specifications.append(('profit', prefix + '核定毛利', 'operating_profit:value', '元'))
        extension_specs += [(name, label, 'operating_profit:' + name, '元', '') for name, label in (
            ('finance_amount', '核实放款金额'),
            ('insurance_commission', '保险返佣'), ('warranty_commission', '延保返佣'),
            ('trade_in_commission', '二手车返佣'), ('bank_commission', '银行返佣'))]
    panels, overview, extensions = [], [], []

    def item(ident, label, key, unit):
        comparison = report(key, grouping, flow_start, end)
        trend = report(key, 'day', start, end)
        panel = dict(comparison, panel_id=ident, panel_title=label,
            trend=trend, comparison=comparison)
        panels.append(panel)
        value = comparison['grand_total'].get(comparison['metric'])
        display = _source_display(key, value)
        return {'key': ident, 'panel_id': ident, 'label': label, 'value': value, 'unit': unit,
            'status': display['data_status'], **display,
            'date_from': str(flow_start), 'date_to': str(end),
            'note': '核算日 ' + str(end) if mode == 'daily' else str(flow_start) + ' 至 ' + str(end)}

    for ident, label, key, unit in specifications:
        overview.append(item(ident, label, key, unit))
    for ident, label, key, unit, rate_name in extension_specs:
        card = item(ident, label, key, unit)
        if rate_name:
            totals = panels[-1]['grand_total']
            rate = totals.get(rate_name + '_rate')
            card.update(penetration_rate=rate,
                penetration_status_label='已审核' if rate is not None else
                    '暂无实销' if totals.get('deliveries') == '0' else '待审核')
        extensions.append(card)
    champion_comparison = report('operating_sales:deliveries', 'salesperson', flow_start, end)
    ranking = champion_comparison['summary_rows']
    leaders = [row for row in ranking if row.get('deliveries') is not None and Decimal(row['deliveries']) > 0]
    best = max((Decimal(row['deliveries']) for row in leaders), default=None)
    champion = {'label': '销冠', 'names': [row['label'] for row in leaders if Decimal(row['deliveries']) == best],
        'count': format(best, 'f') if best is not None else None,
        'status': 'known' if best is not None else 'empty',
        'status_label': '按实销台数' if best is not None else '暂无实销', 'panel_id': 'sales',
        'comparison': champion_comparison}
    return {'mode': mode, 'day': str(end), 'date_from': str(start), 'date_to': str(end),
        'overview_date_from': str(flow_start), 'overview_date_to': str(end),
        'trend_date_from': str(start), 'trend_date_to': str(end),
        'updated_at': utcnow().isoformat(), 'publication': {'status': 'live'},
        'panels': panels, 'overview': overview, 'extension_overview': extensions, 'champion': champion,
        'notice': '订单按合同日期，实销按交车所绑定发票上传日，退车在批准日冲减。'
            '现金车取合同独立标记，消化金额按该车合同售价。延伸及核定毛利仅计总经理已审核资料，缺项显示待审核。'
            '核定毛利已包含原表延伸净额，返佣明细不再重复加总。'}
