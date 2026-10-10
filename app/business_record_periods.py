"""Read-only month choices and daily vehicle-update reminders.

The clerk's maintained original sheets remain the reporting authority. Month
and range views update live; a daily report is frozen only by an explicit clerk
confirmation. Vehicle-update reminders expose actual authorized audit events.
"""
import csv
import hashlib
import io
import json
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .config import settings
from .db import get_db, get_write_db, today
from .models import AuditLog, Store, User
from .security import get_user
from .business_records_models import SalesContract, ContractReceipt, ManualReportRecord, AfterSalesRecord
from .business_records_schemas import Command
from .business_record_period_models import RecordDailyReport
from .tenancy import single_store

router = APIRouter(prefix='/api/business-records', tags=['销售内勤每日维护'])


class ConfirmDailyReport(Command):
    day: date
    report: str = Field(min_length=1, max_length=80, pattern=r'^[a-z0-9_]+$')
    expected_version: int = Field(ge=0, strict=True)
    source_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    note: str = Field(default='', max_length=2000)

UPDATE_ACTIONS = {
    'record_create': '销售预填合同',
    'record_edit': '销售更新预填合同',
    'record_manager_approve': '销售经理审批通过',
    'record_approve': '总经理合同审批通过',
    'record_deputy_approve': '集团副总经理合同审批通过，可打印',
    'record_reject': '合同审批退回',
    'record_office_save': '销售内勤资料已更新',
    'record_office_submit': '销售内勤资料提交审批',
    'record_office_approve': '销售内勤附带信息审批通过',
    'record_office_reject': '销售内勤附带信息审批退回',
    'record_receipt': '收银确认实际到账',
    'record_invoice_upload': '发票已上传',
    'record_invoice_confirm': '发票信息已核实',
}


def _require_updates(user):
    from .business_records import require_read
    require_read(user)
    if user.role == 'service':
        raise HTTPException(403, '当前岗位不开放销售车辆更新清单')


@router.get('/report-periods')
def report_periods(db=Depends(get_db), user=Depends(get_user)):
    """List months present in authorized facts; there is no publication gate."""
    from .business_records import visible_query, require_read
    from .business_record_report_specs import can_view_sensitive_reports
    require_read(user)
    if user.role in {'finance', 'service'}:
        raise HTTPException(403, '当前岗位不开放经营报表')
    periods = set()
    for model, field in ((SalesContract, SalesContract.contract_date),
                         (AfterSalesRecord, AfterSalesRecord.business_date)):
        query = visible_query(user, model).with_only_columns(model.store_id, field).distinct()
        for store, day in db.execute(query):
            periods.add((store, str(day)[:7]))
    if can_view_sensitive_reports(user):
        query = visible_query(user, ManualReportRecord).with_only_columns(
            ManualReportRecord.store_id, ManualReportRecord.period).distinct()
        for store, day in db.execute(query):
            periods.add((store, str(day)[:7]))
    contracts = visible_query(user, SalesContract).with_only_columns(SalesContract.id)
    for store, day in db.execute(select(ContractReceipt.store_id, ContractReceipt.received_on).where(
            ContractReceipt.contract_id.in_(contracts)).distinct()):
        periods.add((store, str(day)[:7]))
    return {'items': [{'store_id': store, 'month': month} for store, month in sorted(
        periods, key=lambda pair: (pair[1], pair[0]), reverse=True)], 'can_publish': False,
        'mode': 'live', 'notice': '销售内勤更新表格后自动统计所选月份，可随时查询历史月份。'}


def _day_window(day):
    zone = ZoneInfo(settings.timezone)
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start.astimezone(timezone.utc).replace(tzinfo=None), end.astimezone(timezone.utc).replace(tzinfo=None)


def _local_timestamp(value):
    return value.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).isoformat()


def build_daily_vehicle_updates(db, user, day):
    from .business_records import visible_query, STATUS_LABELS, OFFICE_STATUS_LABELS
    _require_updates(user)
    start, end = _day_window(day)
    visible = visible_query(user, SalesContract).with_only_columns(SalesContract.id)
    events = list(db.scalars(select(AuditLog).where(
        AuditLog.entity_type == 'record_contract', AuditLog.entity_id.in_(visible),
        AuditLog.action.in_(UPDATE_ACTIONS), AuditLog.occurred_at >= start,
        AuditLog.occurred_at < end).order_by(AuditLog.occurred_at, AuditLog.id)))
    keys = {event.entity_id for event in events}
    contracts = {item.id: item for item in db.scalars(visible_query(user, SalesContract).where(
        SalesContract.id.in_(keys)))} if keys else {}
    names = {item.id: item.display_name for item in db.scalars(select(User).where(
        User.id.in_({item.salesperson_id for item in contracts.values()})))} if contracts else {}
    stores = {item.id: item.name for item in db.scalars(select(Store).where(
        Store.id.in_({item.store_id for item in contracts.values()})))} if contracts else {}
    rows = {}
    for event in events:
        contract = contracts.get(event.entity_id)
        if contract is None or event.store_id != contract.store_id:
            continue
        row = rows.setdefault(contract.id, {
            'contract_id': contract.id, 'number': contract.number, 'store_id': contract.store_id,
            'store': stores.get(contract.store_id, ''), 'salesperson_id': contract.salesperson_id,
            'salesperson': names.get(contract.salesperson_id, ''), 'customer_name': contract.customer_name,
            'brand': contract.brand, 'model': contract.model, 'vin': contract.vin,
            'status': contract.status, 'status_label': STATUS_LABELS.get(contract.status, '待核对'),
            'office_status': contract.office_status,
            'office_status_label': OFFICE_STATUS_LABELS.get(contract.office_status, '待核对'), 'changes': []})
        # Audit payloads can contain costs. Only fixed state keys and fixed
        # action labels are exposed; raw before/after/note are never returned.
        before, after = event.before_data or {}, event.after_data or {}
        change = {'id': event.id, 'action': event.action, 'label': UPDATE_ACTIONS[event.action],
            'occurred_at': _local_timestamp(event.occurred_at),
            'status_before': STATUS_LABELS.get(before.get('status'), ''),
            'status_after': STATUS_LABELS.get(after.get('status'), ''),
            'office_status_before': OFFICE_STATUS_LABELS.get(before.get('office_status'), ''),
            'office_status_after': OFFICE_STATUS_LABELS.get(after.get('office_status'), '')}
        row['changes'].append(change)
        row['last_changed_at'] = change['occurred_at']
    result = sorted(rows.values(), key=lambda row: (row['last_changed_at'], row['number']), reverse=True)
    for row in result:
        row['change_count'] = len(row['changes'])
        row['change_summary'] = '；'.join(item['occurred_at'][11:19] + ' ' + item['label'] for item in row['changes'])
    columns = [{'key': key, 'label': label, 'type': 'text', 'unit': '', 'precision': None} for key, label in (
        ('number', '合同号'), ('store', '门店'), ('salesperson', '销售'), ('customer_name', '客户'),
        ('brand', '品牌'), ('model', '车型'), ('vin', '车架号'), ('status_label', '当前合同状态'),
        ('office_status_label', '当前销售内勤状态'), ('last_changed_at', '最后更新时间'),
        ('change_count', '当日更新次数'), ('change_summary', '当日发生的更新'))]
    return {'day': day.isoformat(), 'status': 'updates', 'title': '当日车辆更新', 'rows': result,
        'pending_rows': [], 'columns': columns,
        'counts': {'changed_vehicles': len(result), 'changes': sum(row['change_count'] for row in result)},
        'notice': '按当天实际发生的合同、审批、销售内勤资料及收银更新提醒逐台列示，不按合同日期或销售内勤统计日期筛选。销售内勤仍需自行维护、整理每日汇总报表；本清单不表示日报已完成。'}


def daily_query(day: date | None = None, db=Depends(get_db), user=Depends(get_user)):
    return build_daily_vehicle_updates(db, user, day or today())


@router.get('/daily-vehicle-reports')
def daily_vehicle_report(result=Depends(daily_query)):
    return result


@router.get('/daily-vehicle-reports/export')
def export_daily_vehicle_report(result=Depends(daily_query)):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow([column['label'] for column in result['columns']])
    for row in result['rows']:
        values = [row.get(column['key'], '') for column in result['columns']]
        writer.writerow(["'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@'))
                         else value for value in values])
    return Response(('\ufeff' + output.getvalue()).encode('utf-8'), media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="daily-vehicle-updates-' + result['day'] + '.csv"'})


def _require_confirm(user):
    from .business_records import require_read
    require_read(user)
    if getattr(user, '_aggregate_scope', False) or user.role not in {'clerk', 'admin'}:
        raise HTTPException(403, '请由当前门店销售内勤预览核对后确认日报')


def _daily_report_query(user):
    from .business_records import require_read, _group_ids
    require_read(user)
    query = select(RecordDailyReport)
    if getattr(user, '_aggregate_scope', False):
        query = query.where(RecordDailyReport.store_id.in_(_group_ids(user)))
    return query


def _capture_daily_source(db, user, day, report):
    from .business_record_report_generation import build
    from .business_record_reports import CATALOG_BY_KEY
    source = build(db, user, report, date_from=day, date_to=day, source_mode='combined', snapshot_sources=True)
    payload = {'schema_version': 1, 'day': str(day), 'definition': deepcopy(CATALOG_BY_KEY[report]),
               'rows': source['rows'], 'legacy_rows': source['legacy_rows']}
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()
    return payload, digest


def _daily_report_info(row, user):
    from .business_record_report_specs import can_view_sensitive_reports
    return {'id': row.id, 'store_id': row.store_id, 'day': str(row.day), 'report': row.report_key,
            'version': row.version, 'confirmed_by': row.confirmed_by,
            'confirmed_at': _local_timestamp(row.confirmed_at),
            'note': row.note if can_view_sensitive_reports(user) else ''}


def _latest_daily(db, user, report, start, end, version=None):
    query = _daily_report_query(user).where(RecordDailyReport.report_key == report,
        RecordDailyReport.day >= start, RecordDailyReport.day <= end)
    if version is not None:
        query = query.where(RecordDailyReport.version == version)
    rows = db.scalars(query.order_by(RecordDailyReport.version.desc()))
    latest = {}
    for row in rows:
        latest.setdefault((row.store_id, row.day), row)
    return list(latest.values())


def _allowed_store_ids(db, user):
    from .business_records import _group_ids
    if getattr(user, '_aggregate_scope', False):
        return set(_group_ids(user))
    return {single_store(db)}


def _render_daily(db, user, day, report, snapshots, *, brand='', salesperson_id=None,
                  group_by='salesperson', category_field='', category_value=''):
    from .business_record_reports import CATALOG_BY_KEY
    from .business_record_report_generation import project
    from .business_record_report_specs import assert_report_access, sensitive_report, can_view_sensitive_reports
    assert_report_access(user, report)
    key, separator, metric = report.partition(':')
    if user.role == 'sales' and salesperson_id not in (None, user.id):
        raise HTTPException(403, '销售只能查看本人数据')
    if any(sensitive_report(row.payload['definition']) for row in snapshots) and not can_view_sensitive_reports(user):
        raise HTTPException(403, '所选历史日报包含当前岗位不可查看的内部数据')
    definition = snapshots[0].payload['definition'] if snapshots else CATALOG_BY_KEY[key]
    if any(row.payload['definition'] != definition for row in snapshots):
        raise ValueError('所选门店的日报口径版本不同，请分别查看，不混合不同定义。')
    rows, legacy = [], []
    for snapshot in snapshots:
        for source_key, target in (('rows', rows), ('legacy_rows', legacy)):
            for row in snapshot.payload[source_key]:
                if user.role == 'sales' and row.get('salesperson_id') != user.id:
                    continue
                if salesperson_id is not None and row.get('salesperson_id') != salesperson_id:
                    continue
                if brand and row.get('brand') != brand:
                    continue
                visible_row = deepcopy(row)
                if not can_view_sensitive_reports(user):
                    visible_row['note'] = ''
                target.append(visible_row)
    updated = max((_local_timestamp(row.confirmed_at) for row in snapshots), default=None)
    result = project(definition, rows, group_by=group_by,
        metric=metric if separator else definition['default_metric'], updated_at=updated,
        category_field=category_field, category_value=category_value, source_mode='combined', legacy_rows=legacy)
    missing = sorted(_allowed_store_ids(db, user) - {row.store_id for row in snapshots})
    status = 'unconfirmed' if not snapshots else 'partial' if missing else 'confirmed'
    result['publication'] = {'status': status, 'day': str(day), 'confirmed_at': updated,
        'versions': [_daily_report_info(row, user) for row in snapshots], 'missing_store_ids': missing}
    result['notice'] = ({'unconfirmed': '本日此报表尚未经销售内勤确认，空白不代表零业绩。',
        'partial': '部分授权门店尚未确认本日报表，仅列示已确认门店，请勿视为集团完整汇总。',
        'confirmed': '销售内勤已确认的日报版本；后续表格更新不会改写本版，重新确认将追加更正版本。'}[status]
        + result['notice'])
    return result


@router.get('/daily-reports/preview')
def preview_daily_report(day: date | None = None, report: str = 'sales_volume', group_by: str = 'salesperson',
                         category_field: str = Query('', max_length=80), db=Depends(get_db), user=Depends(get_user)):
    from .business_record_report_generation import project
    _require_confirm(user)
    day = day or today()
    if day > today():
        raise HTTPException(422, '不能预览确认未来日期的日报')
    key, separator, metric = report.partition(':')
    try:
        payload, digest = _capture_daily_source(db, user, day, key)
        definition = payload['definition']
        result = project(definition, payload['rows'], group_by=group_by,
            metric=metric if separator else definition['default_metric'], category_field=category_field,
            source_mode='combined', legacy_rows=payload['legacy_rows'])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    prior = db.scalar(_daily_report_query(user).where(RecordDailyReport.day == day,
        RecordDailyReport.report_key == key).order_by(RecordDailyReport.version.desc()).limit(1))
    result['confirmation'] = {'day': str(day), 'report': key, 'source_digest': digest,
        'expected_version': prior.version if prior else 0, 'scope': 'entire_store_report'}
    result['publication'] = {'status': 'preview', 'day': str(day), 'versions': [], 'confirmed_at': None}
    result['notice'] = '待销售内勤核对的整店当日原表，确认将保存完整报表；尚未成为员工看到的每日报表。' + result['notice']
    return result


@router.post('/daily-reports/confirm', status_code=201)
def confirm_daily_report(body: ConfirmDailyReport, request: Request,
                          db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import _manual, _run, _body, _lock_customer_scope
    from .business_record_report_specs import assert_report_access
    from .services import audit
    _manual(request)
    _require_confirm(user)
    assert_report_access(user, body.report)
    if body.day > today():
        raise HTTPException(422, '不能确认未来日期的日报')
    def perform():
        _lock_customer_scope(db)
        prior = db.scalar(_daily_report_query(user).where(RecordDailyReport.day == body.day,
            RecordDailyReport.report_key == body.report).order_by(RecordDailyReport.version.desc()).limit(1))
        if body.expected_version != (prior.version if prior else 0):
            raise HTTPException(409, '日报已有新确认版本，请重新预览核对')
        try:
            payload, digest = _capture_daily_source(db, user, body.day, body.report)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        if body.source_digest != digest:
            raise HTTPException(409, '预览后源表数据已更新，本次未确认；请重新预览核对')
        row = RecordDailyReport(store_id=single_store(db), day=body.day, report_key=body.report,
            version=body.expected_version + 1, confirmed_by=user.id, note=body.note,
            source_digest=digest, payload=payload)
        db.add(row)
        db.flush()
        result = _daily_report_info(row, user)
        audit(db, user.id, 'record_daily_confirm', 'record_daily_report', row.id, after=result)
        return result
    try:
        return _run(db, user, body.request_id, 'report_day:confirm', _body(body), perform)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '日报已有新确认版本，请刷新核对') from None


def confirmed_daily_query(day: date | None = None, report: str = 'sales_volume',
        brand: str = Query('', max_length=100), salesperson_id: int | None = Query(None, gt=0),
        group_by: str = 'salesperson', category_field: str = Query('', max_length=80),
        category_value: str = Query('', max_length=1000), source_mode: str = 'combined',
        version: int | None = Query(None, gt=0), db=Depends(get_db), user=Depends(get_user)):
    from .business_record_report_specs import assert_report_access
    assert_report_access(user, report)
    if source_mode != 'combined':
        raise HTTPException(422, '已确认日报使用销售内勤核对的完整原表，请勿切换来源口径')
    day = day or today()
    snapshots = _latest_daily(db, user, report.split(':', 1)[0], day, day, version=version)
    try:
        return _render_daily(db, user, day, report, snapshots, brand=brand, salesperson_id=salesperson_id,
            group_by=group_by, category_field=category_field, category_value=category_value)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get('/daily-reports')
def confirmed_daily_report(result=Depends(confirmed_daily_query)):
    return result


def _report_csv(result, view, filename):
    if view not in {'summary', 'details', 'detail'}:
        raise HTTPException(422, '请选择导出统计表或来源明细')
    columns = result['summary_columns'] if view == 'summary' else result['columns']
    rows = result['summary_rows'] + [result['grand_total']] if view == 'summary' else result['rows']
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow([column['label'] for column in columns])
    for row in rows:
        values = [row.get(column['key'], '') for column in columns]
        writer.writerow(["'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@'))
                         else value for value in values])
    return Response(('\ufeff' + output.getvalue()).encode('utf-8'), media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="' + filename + '"'})


@router.get('/daily-reports/export')
def export_confirmed_daily_report(view: str = 'details', result=Depends(confirmed_daily_query)):
    return _report_csv(result, view, 'clerk-confirmed-daily-report.csv')


def daily_trend_query(day: date | None = None, days: int = Query(7, ge=2, le=90),
        report: str = 'sales_volume', brand: str = Query('', max_length=100),
        salesperson_id: int | None = Query(None, gt=0), category_field: str = Query('', max_length=80),
        category_value: str = Query('', max_length=1000), source_mode: str = 'combined',
        db=Depends(get_db), user=Depends(get_user)):
    from .business_record_report_specs import assert_report_access
    assert_report_access(user, report)
    if source_mode != 'combined':
        raise HTTPException(422, '已确认日报趋势使用销售内勤核对的完整原表')
    day = day or today()
    start = day - timedelta(days=days - 1)
    snapshots = _latest_daily(db, user, report.split(':', 1)[0], start, day)
    by_day = {}
    for snapshot in snapshots:
        by_day.setdefault(snapshot.day, []).append(snapshot)
    series, rows, template, prior = [], [], None, None
    for offset in range(days):
        selected = start + timedelta(days=offset)
        try:
            result = _render_daily(db, user, selected, report, by_day.get(selected, []), brand=brand,
                salesperson_id=salesperson_id, group_by='group', category_field=category_field, category_value=category_value)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        template = result
        status = result['publication']['status']
        value = result['grand_total'].get(result['metric']) if status == 'confirmed' else None
        exact_difference = format(Decimal(value) - Decimal(prior), 'f') if value is not None and prior is not None else None
        change = (format(((Decimal(value) - Decimal(prior)) / abs(Decimal(prior)) * 100)
                         .quantize(Decimal('.000001')), 'f')
                  if value is not None and prior is not None and Decimal(prior) != 0 else None)
        rows.append({'label': str(selected), 'value': value, result['metric']: value, 'status': status,
            'status_label': {'confirmed': '已确认', 'unconfirmed': '未确认', 'partial': '部分门店未确认'}[status],
            'difference': exact_difference, 'change_percent': change,
            'confirmed_store_count': len(result['publication']['versions'])})
        series.append({'label': str(selected), 'value': float(value) if value is not None else None,
                       'exact_value': value, 'status': status, 'record_count': result['record_count'],
                       'unknown_count': result['grand_total']['unknown_count']})
        prior = value
    current, previous = rows[-1], rows[-2]
    columns = [
        {'key': 'label', 'label': '日期', 'type': 'date', 'unit': '', 'precision': None},
        {'key': 'value', 'label': template['metric_label'], 'type': 'decimal', 'unit': template['unit'], 'precision': template['precision']},
        {'key': 'status_label', 'label': '销售内勤确认状态', 'type': 'text', 'unit': '', 'precision': None},
        {'key': 'difference', 'label': '较前一日变化', 'type': 'decimal', 'unit': template['unit'], 'precision': template['precision']},
        {'key': 'change_percent', 'label': '较前一日变化率', 'type': 'percent', 'unit': '%', 'precision': 6}]
    return {'report': template['report'], 'metric': template['metric'], 'title': template['title'] + ' · 日报趋势',
        'metric_label': template['metric_label'], 'unit': template['unit'], 'precision': template['precision'],
        'period_basis': '每天销售内勤确认的日报版本', 'series': series, 'rows': rows, 'columns': columns,
        'summary_rows': rows, 'summary_columns': columns,
        'grand_total': {'label': '所选日期', 'value': current['value'], template['metric']: current['value'],
                        'record_count': 1, 'unknown_count': int(current['value'] is None)},
        'record_count': days, 'legacy_rows': [], 'legacy_count': 0, 'source_mode': 'combined',
        'updated_at': max((_local_timestamp(row.confirmed_at) for row in snapshots), default=None),
        'publication': {'status': 'trend', 'day': str(day), 'days': days},
        'comparison': {'current': current['value'], 'previous': previous['value'],
                       'difference': current['difference'], 'change_percent': current['change_percent']},
        'notice': '逐日读取销售内勤已确认版本；未确认、部分门店未确认及未知值保持空白，不计作零。与前一日相比，缺失日不跳过，基期为零时变化率留空。'}


@router.get('/daily-reports/trend')
def daily_report_trend(result=Depends(daily_trend_query)):
    return result


@router.get('/daily-reports/trend/export')
def export_daily_report_trend(view: str = 'details', result=Depends(daily_trend_query)):
    return _report_csv(result, view, 'clerk-confirmed-daily-trend.csv')
