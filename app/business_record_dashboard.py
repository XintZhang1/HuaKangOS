"""Live multi-chart dashboard built from the same authorized report projections."""
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from .db import get_db, today, utcnow
from .security import get_user

router = APIRouter(prefix='/api/business-records', tags=['实时多图经营看板'])


def _calendar_series(panel, start, end):
    by_day = {row['label']: row for row in panel['series']}
    series = []
    current = start
    while current <= end:
        label = str(current)
        series.append(by_day.get(label, {'label': label, 'value': None, 'exact_value': None,
            'record_count': 0, 'unknown_count': 1, 'status': 'no_source'}))
        current += timedelta(days=1)
    panel['series'] = series
    return panel


def _observation_source_dates(rows, metric):
    """Follow daily_operations' closing snapshot per store/brand/salesperson."""
    latest = {}
    for row in rows:
        if metric not in row.get('_applicable_fields', row):
            continue
        scope = (row.get('store_id'), row.get('brand') or '', row.get('salesperson_id'))
        source_day = str(row.get('_snapshot_source_period', row['period']))
        order = (source_day, row.get('id') or 0)
        if scope not in latest or order > latest[scope]:
            latest[scope] = order
    return sorted({day for day, _ in latest.values()})


@router.get('/dashboard-panels')
def dashboard_panels(mode: str = 'daily', day: date | None = None,
        date_from: date | None = None, date_to: date | None = None,
        brand: str = Query('', max_length=100), salesperson_id: int | None = Query(None, gt=0),
        group_by: str = '', db=Depends(get_db), user=Depends(get_user)):
    from .business_records import require_read
    from .business_record_report_generation import build
    from .business_record_report_specs import can_view_sensitive_reports
    require_read(user)
    if user.role in {'sales', 'finance', 'service'}:
        raise HTTPException(403, '当前岗位不开放经营看板')
    if mode not in {'daily', 'monthly'}:
        raise HTTPException(422, '请选择日报或月报')
    selected = day or today()
    end = date_to or selected
    start = date_from or (end - timedelta(days=6) if mode == 'daily' else end.replace(day=1))
    if start > end or (end - start).days > 366:
        raise HTTPException(422, '请选择不超过一年的有效日期范围')
    grouping = group_by or ('store' if getattr(user, '_aggregate_scope', False) else 'salesperson')
    if grouping not in {'store', 'salesperson', 'brand'}:
        raise HTTPException(422, '请选择门店、销售顾问或品牌比较')
    cache = {}
    def report(key, group, beginning=start, ending=end, category=''):
        identity = (key, group, beginning, ending, category)
        if identity not in cache:
            try:
                cache[identity] = build(db, user, key, date_from=beginning, date_to=ending,
                    brand=brand, salesperson_id=salesperson_id, group_by=group, category_field=category)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
        return cache[identity]
    specifications = [
        ('sales_trend', '实销及退车趋势', 'sales_volume', 'day', ''),
        ('orders_trend', '实际收订趋势', 'daily_operations:c01', 'day', ''),
        ('sales_comparison', '门店 / 销售顾问实销比较', 'sales_volume', grouping, ''),
        ('cash_trend', '现金车消化台数', 'cash_deliveries', 'day', ''),
        ('cash_amount', '现金车消化金额', 'cash_consumption_amount', 'day', ''),
        ('trade_in', '系统置换及退车冲减', 'trade_in:c07', 'day', ''),
        ('warranty', '延保出单', 'extended_warranty:c04', 'category', 'c01'),
        ('products', '小产品出单', 'small_products:c05', 'category', 'c01'),
    ]
    if can_view_sensitive_reports(user):
        specifications.append(('profit', '核定毛利及退车冲减', 'profit', grouping, ''))
    panels = []
    for ident, title, key, group, category in specifications:
        try:
            result = dict(report(key, group, category=category))
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        if group == 'day':
            result = _calendar_series(result, start, end)
        result.update(panel_id=ident, panel_title=title, group_by=group,
            query={'report': key, 'date_from': str(start), 'date_to': str(end), 'group_by': group,
                   'category_field': category, 'brand': brand, 'salesperson_id': salesperson_id},
            data_status=result['source_status']['status'])
        panels.append(result)
    flow_start = start if mode == 'monthly' else end
    flow_prefix = '期间累计' if mode == 'monthly' else '当日'
    orders = report('daily_operations', 'group', flow_start, end)
    sales = report('sales_volume', 'group', flow_start, end)
    cash = report('cash_deliveries', 'group', flow_start, end)
    cash_amount = report('cash_consumption_amount', 'group', flow_start, end)
    # Stock and tomorrow's forecast are observations, never period totals.
    # A future month-end must not relabel today's forecast as next month's.
    observation_day = min(end, today()) if mode == 'monthly' else end
    observation = report('daily_operations', 'group', observation_day, observation_day)
    try:
        observation_sources = build(db, user, 'daily_operations',
            date_from=observation_day, date_to=observation_day, brand=brand,
            salesperson_id=salesperson_id, group_by='group', snapshot_sources=True)['rows']
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    overview = []
    for key, label, result, metric, unit in (
        ('orders', flow_prefix + '实际收订', orders, 'c01', '台'),
        ('sales', flow_prefix + '净实销', sales, 'value', '台'),
        ('cash_count', flow_prefix + '现金车消化', cash, 'value', '台'),
        ('cash_amount', flow_prefix + '现金车消化金额', cash_amount, 'value', '元'),
        ('cash_remaining', '剩余现金车', observation, 'c03', '台'),
        ('tomorrow_delivery', '次日预计交车', observation, 'c04', '台')):
        value = result['grand_total'].get(metric)
        item = {'key': key, 'label': label, 'value': value, 'unit': unit,
                'status': 'known' if value is not None else 'awaiting_data',
                'date_from': str(flow_start), 'date_to': str(end),
                'note': str(flow_start) + ' 至 ' + str(end) if mode == 'monthly' else '核算日 ' + str(end)}
        if key in {'cash_remaining', 'tomorrow_delivery'}:
            source_dates = _observation_source_dates(observation_sources, metric)
            item.update(date_from=str(observation_day), date_to=str(observation_day),
                observation_date=str(observation_day), source_dates=source_dates,
                note='观察日 ' + str(observation_day))
            if key == 'cash_remaining':
                item['note'] += '；余额来源日期 ' + '、'.join(source_dates) if source_dates else '；尚无余额观察'
            else:
                forecast_date = str(observation_day + timedelta(days=1))
                item.update(forecast_date=forecast_date,
                    note=item['note'] + '；预计交车日期 ' + forecast_date)
            if value is None:
                item['note'] += '；待补齐'
        overview.append(item)
    return {'mode': mode, 'day': str(end), 'date_from': str(start), 'date_to': str(end),
        'updated_at': utcnow().isoformat(), 'publication': {'status': 'live'}, 'panels': panels, 'overview': overview,
        'notice': '实时事实视图，不等于内勤已确认日报。交车按发票上传日、退车按批准日；收订、现金余额和预计交车使用各自人工核实来源，缺项保留待补齐。'}
