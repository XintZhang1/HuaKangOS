"""V2 reporting: fixed input schemas and projections of authorized record facts.

The source spreadsheets define labels, not live data or executable formulas.
Unknown manual values stay null. Ratios and unit prices are never summed.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
import re


def _column(key, label, kind='money', unit=None):
    units = {'money': '元', 'count': '个', 'percent': '%', 'decimal': '', 'text': '', 'date': ''}
    precision = {'money': 2, 'count': 0, 'percent': 2, 'decimal': 4, 'text': None, 'date': None}
    return {'key': key, 'label': label, 'type': kind, 'unit': units[kind] if unit is None else unit,
            'precision': precision[kind]}


def _fields(spec):
    """Short fixed schema notation: label|type|unit; keys are stable column numbers."""
    result = []
    for index, value in enumerate(spec.split(';'), 1):
        parts = value.split('|')
        result.append(_column('c' + str(index).zfill(2), parts[0],
                              parts[1] if len(parts) > 1 else 'money',
                              parts[2] if len(parts) > 2 else None))
    return result


def _manual(key, title, spec, source, default=None):
    columns = _fields(spec)
    metrics = [dict(c) for c in columns if c['type'] not in {'text', 'date'}]
    return {'key': key, 'title': title, 'source': 'manual', 'source_template': source,
            'aggregation': 'individual_record',
            'unit': '', 'period_basis': '人工填报的统计日期', 'columns': columns,
            'metrics': metrics, 'default_metric': default or (metrics[0]['key'] if metrics else None)}


REPORT_CATALOG = [
    {'key': key, 'title': title, 'source': source, 'unit': unit, 'period_basis': basis,
     'columns': [], 'metrics': [_column('value', title, kind, unit)], 'default_metric': 'value'}
    for key, title, source, unit, kind, basis in (
        ('expected_receipts', '应到账金额', 'contracts', '元', 'money', '审批通过合同的合同日期；未到账合同也计入'),
        ('actual_receipts', '实到账金额', 'contracts', '元', 'money', '财务核实的实际到账日期'),
        ('profit', '内勤核定利润排名', 'contracts', '元', 'money', '财务核实的实际到账日期；每份合同只计一次'),
        ('sales_volume', '实销台数排名', 'contracts', '台', 'count', '财务核实的实际到账日期；每份合同只计一次'),
        ('after_sales_revenue', '售后业务产值', 'after_sales', '元', 'money', '售后记录的统计日期'),
    )
]

# All eleven supplied screenshot structures. Organization/person examples are
# intentionally absent: current records supply their own authorized dimensions.
REPORT_CATALOG += [
    _manual('sales_targets', '实销与产值任务目标',
            '系列|text;店内实销任务|count|台;机电产值任务;事故产值任务;售后产值任务合计', '截图78'),
    _manual('trade_in', '置换收车与收益',
            '经办人|text;主责区域看车|count|台;主责收车|count|台;辅助收车|count|台;本店收车率|percent;综合收车率|percent;系统置换数|count|台;本店收车台次|count|台;超级置换|count|台;亲属置换|count|台;流失数|count|台;置换率|percent;店内收益', '截图79'),
    _manual('extended_warranty', '延保业务',
            '合作公司|text;车辆实销|count|台;接触客户|count|人;延保出单|count|单;渗透率|percent', '截图80上'),
    _manual('small_products', '小产品业务',
            '合作公司|text;业务项目|text;车辆实销|count|台;接触客户|count|人;出单|count|单;渗透率|percent', '截图80下'),
    _manual('after_sales_monthly', '售后月度产值与毛利',
            '业务分类|text;目标;产值;达成率|percent;零售维修;零售维修占比|percent;保修索赔;保修索赔占比|percent;配件总库存;呆滞件库存;呆滞件占比|percent;材料费;材料费占比|percent;工时费;工时费占比|percent;工时毛利率|percent;配件毛利率|percent', '截图81'),
    _manual('after_sales_targets', '售后任务完成与人员产效',
            '机电产值任务;事故产值任务;售后产值总目标;机修台次|count|台次;机修产值;机修完成率|percent;机修单产;事故台次|count|台次;事故产值;事故完成率|percent;事故单产;事故毛利产值;事故车单车毛利;事故毛利产值任务;事故毛利产值完成率|percent;总产值实际完成;总产值完成率|percent;精品养护实际完成;精品养护完成率|percent;服务顾问三包索赔人数|count|人;服务顾问人均产效;事故理赔人数|count|人;事故人均产效;机修技师|count|人;钣金油漆|count|人', '截图82'),
    _manual('bank_finance', '金融放款与返利',
            '金融机构|text;金融类别|text;约定返利率|percent;放款台数|count|台;放款金额;返利金额;实销|count|台;批发|count|台;渗透率|percent;厂家渗透率|percent;外部银行台数|count|台;外部银行放款;厂家金融台数|count|台;厂家金融放款', '截图83：按机构逐行填报，金额统一元'),
    _manual('insurance_settlement', '保险定损与到账',
            '保险公司|text;区域|text;直赔到账金额;新车保费;续保保费;总保费;新车送修比|percent;总送修比|percent;县区保费;含城区总保费;其他到账金额', '截图84'),
    _manual('sales_overview', '销售板块与库存统计',
            '系列|text;实销任务|count|台;单日交付量|count|台;实销完成|count|台;销售任务完成率|percent;在库|count|台;在途|count|台;库存合计|count|台;现金车|count|台;可售试驾|count|台', '截图85'),
    _manual('insurance_resources', '保险资源数据',
            '保险公司|text;新车保费;出单数量|count|单;实销|count|台;批发|count|台;保险渗透率|percent;全损数量|count|单;全损渗透率|percent;续保台次|count|台次;续保保费;定损到账;资源送修比|percent;总保费;保费占比|percent;当日定损金额', '截图86：按保险公司逐行填报'),
    _manual('marketing', '集团月度营销汇总',
            '新媒体投入;垂媒投入;各类投入;总投入;新媒体线索|count|条;垂媒线索|count|条;自然进店线索|count|条;系统下发线索|count|条;线索合计|count|条;新媒体转化率|percent;垂媒转化率|percent;自然进店转化率|percent;系统下发线索转化率|percent;综合转化率|percent;新媒体订单|count|单;垂媒订单|count|单;自然进店订单|count|单;系统下发线索订单|count|单;总订单数|count|单;线上实销数|count|台;新媒体成交成本;垂媒成交成本;综合成交成本;三方垂媒|count|单;懂车帝|count|单;汽车之家|count|单;易车网|count|单;线上平台|count|单;抖音|count|单;小红书|count|单;视频号|count|单;各类投放|count|单;线上广告|count|单;线下广告|count|单', '截图87'),
    _manual('insurance_renewal', '续保业务',
            '保险公司|text;店内续保数量|count|单;店内续保保费;店外续保数量|count|单;店外续保保费;计划|count|单;现售|count|单;完成率|percent;总保费', '截图88'),
]

_VEHICLE = ('序号|count;台数|count|台;车系|text;车型|text;车架号|text;单车利润;开票日期|date;销售顾问|text;'
            '指导价;颜色|text;提车价;开票价;置换金额;客户名称|text;地址|text;订单类型|text;库存天数|count|天;'
            '现金或三方|text;客户电话|text;上牌费;上牌净利;金融服务费;车辆售价;贷款金额;店端贴息;'
            '分期服务费返佣;银行返佣;客户返佣;承保公司|text;商业险;新保返佣折扣|percent;保险返佣;'
            '全损收入;全损小产品;延保金额;延保返佣;二手车返佣;贴膜收入;精品成本（赠送）;调库拖车费;'
            '调车地点|text;选装金额;厂家折让;区补;核定单车利润;精品明细|text;补充列1|text;补充列2|text')
_PROFIT = ('销量台数|count|台;总利润;收入;支出;单车毛利;营收项|text;营收项收入;营收项占比|percent;成本项|text;成本项支出')
_MODEL_PROFIT = '车型|text;开票数量|count|台;车型综合毛利;平均车毛利;毛利贡献率|percent'
_HAIL = ('序号|count;台数|count|台;车系|text;车型|text;车架号|text;单车利润2;开票日期|date;销售顾问|text;'
         '指导价;颜色（原表列名2暮云灰）|text;提车价;开票价;客户名称|text;地址|text;订单类型|text;库存天数|count|天;'
         '现金或三方|text;客户电话|text;上牌费;上牌费返佣;服务费;车辆售价;贷款金额;店端贴息;分期服务费返佣;'
         '银行返佣;客户返佣;承保公司|text;商业险;新保返佣折扣|percent;保险返佣;车小安;车小安返佣;延保金额;'
         '延保返佣;二手车返佣;贴膜收入;精品成本（赠送）;调库拖车费;调车地点|text;选装;厂家折让;单车利润22;精品明细|text;列1|text')
_SECONDARY = ('序号|count;台数|count|台;车系|text;车辆型号|text;车架号|text;外饰颜色|text;指导价;颜色或内饰|text;'
              '提车价;开票价;开票日期|date;销售顾问|text;客户名称|text;地址|text;订单类型|text;库存天数|count|天;'
              '现金或三方|text;客户电话|text;上牌费;服务费;车辆售价;贷款金额;店端贴息;分期服务费返佣;银行返佣;'
              '承保公司|text;商业险;新保返佣折扣|percent;保险返佣;车小安;车小安返佣;延保金额;延保返佣;'
              '贴膜收入;精品成本（赠送）;调库拖车费;调车地点|text;选装;厂家折让;单车利润;精品明细|text')
REPORT_CATALOG += [
    _manual('vehicle_details', '车辆明细统计', _VEHICLE, 'Excel：车辆明细', 'c45'),
    _manual('hail_vehicle_details', '特殊车辆明细统计', _HAIL, 'Excel：冰雹车；指导价统一按元填写'),
    _manual('accessory_details', '精品价格明细', '车系|text;车型|text;精品明细|text;价格;备注|text', 'Excel：明细'),
    _manual('sales_profit_statement', '销售利润统计表', _PROFIT, 'Excel：销售利润表', 'c02'),
    _manual('secondary_vehicle_details', '二级交车明细统计', _SECONDARY, 'Excel：二级交车明细；指导价统一按元填写'),
    _manual('secondary_profit_statement', '二级销售利润统计表', _PROFIT, 'Excel：二级销售利润表', 'c02'),
    _manual('vehicle_policy', '车型利润体系人工记录',
            '车系|text;车型|text;建议零售价;提车价;厂家折让;广告支持折让;WES;精诚服务;9.21政策后;10.16后追加政策在库车型;11.1后追加政策在库车型;3.1至3.31追加政策;2026年2月26日至3月31日;2026年3月1日至3月31日;超级置换;折让合计未包含超级置换',
            'Excel：比亚迪车型利润体系一览表（2），仅人工统计，不形成车型基础资料依赖'),
    _manual('individual_profit', '个人毛利分析',
            '销售部|text;数据分布|text;开票目标|count|台;累计开票|count|台;开票完成率|percent;月度单台毛利;月度总毛利;单车毛利;特殊单车毛利', 'Excel：个人毛利分析表', 'c07'),
    _manual('model_profit', '车型毛利结构', '业务类别|text;' + _MODEL_PROFIT, 'Excel：车型布局图；正常与冰雹车分别填写'),
    _manual('model_profit_sheet5', '车型毛利补充统计', _MODEL_PROFIT, 'Excel：Sheet5'),
    _manual('vehicle_details_sheet2', '车辆补充明细统计', _SECONDARY.replace('上牌费;服务费;', '上牌费;上牌费返佣;服务费;'), 'Excel：Sheet2；指导价统一按元填写'),
    _manual('bank_commission', '银行返佣标准人工记录',
            '银行|text;分期期数|count|期;分期费率（对客户）|percent;返佣比例|percent;备注|text', 'Excel：银行返佣'),
    _manual('vehicle_policy_reference', '车型利润体系补充记录',
            '车系|text;车型|text;建议零售价;提车价;广告支持折让;WES;精诚服务', 'Excel：比亚迪车型利润体系一览表'),
]
# These source sheets contain no nonempty cells, so there are no hidden metrics to
# reproduce. Keeping this explicit avoids inventing forms for empty worksheets.
EMPTY_SOURCE_SHEETS = ('Sheet1', 'Sheet4', '折让')
CATALOG_BY_KEY = {item['key']: item for item in REPORT_CATALOG}


def validate_manual_values(report_key, values):
    report = CATALOG_BY_KEY.get(report_key)
    if not report or report['source'] != 'manual':
        raise ValueError('请选择已登记的人工报表。')
    if not isinstance(values, dict):
        raise ValueError('报表内容必须按字段填写。')
    fields = {field['key']: field for field in report['columns']}
    if set(values) - set(fields):
        raise ValueError('包含不属于当前报表的字段。')
    result = {}
    for key, field in fields.items():
        value = values.get(key)
        if value is None or value == '':
            result[key] = None
            continue
        if isinstance(value, bool) or isinstance(value, (dict, list)):
            raise ValueError(field['label'] + '格式不正确。')
        text = str(value).strip()
        if field['type'] == 'text':
            if len(text) > 1000 or any(ord(c) < 32 and c not in '\n\t' for c in text):
                raise ValueError(field['label'] + '内容过长或包含控制字符。')
            result[key] = text
        elif field['type'] == 'date':
            try:
                result[key] = date.fromisoformat(text).isoformat()
            except ValueError:
                raise ValueError(field['label'] + '请填写YYYY-MM-DD。') from None
        else:
            if not re.fullmatch(r'-?\d+(?:\.\d+)?', text):
                raise ValueError(field['label'] + '请填写有限十进制数字。')
            number = Decimal(text)
            if abs(number) > Decimal('999999999999.99'):
                raise ValueError(field['label'] + '超出可记录范围。')
            if max(0, -number.as_tuple().exponent) > field['precision']:
                raise ValueError(field['label'] + f"最多保留{field['precision']}位小数，不自动舍入。")
            if field['type'] == 'count' and number < 0:
                raise ValueError(field['label'] + '不能为负数。')
            result[key] = format(number, 'f')
    if not any(v is not None for v in result.values()):
        raise ValueError('请至少填写一项数据，未知项可以留空。')
    return result


def _money(cents):
    return None if cents is None else format(Decimal(cents) / 100, '.2f')


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _period(value, start, end):
    value = str(_iso(value) or '')[:10]
    return bool(value) and (not start or value >= str(start)) and (not end or value <= str(end))


def project_report(report, records, *, group_by='salesperson', metric=None, updated_at=None):
    """Pure projection; caller supplies only authorized, date-filtered facts."""
    if group_by not in {'salesperson', 'store', 'brand', 'month'}:
        raise ValueError('不支持的报表分组。')
    definition = CATALOG_BY_KEY.get(report)
    if definition is None:
        raise ValueError('报表不存在。')
    metric = metric or definition['default_metric']
    fields = {x['key']: x for x in definition['metrics']}
    if metric not in fields:
        raise ValueError('请选择当前报表中的指标。')
    selected = fields[metric]
    rows = [dict(row) for row in records]
    groups = defaultdict(list)
    group_labels = {}
    for row in rows:
        label = {'salesperson': row.get('salesperson', '未指定销售'),
                 'store': row.get('store', '未指定门店'), 'brand': row.get('brand') or '未填品牌',
                 'month': str(row.get('period') or '')[:7] or '未填日期'}[group_by]
        group_key = (group_by, row.get(group_by + '_id')) if group_by in {'salesperson', 'store'} else (group_by, label)
        if group_by in {'salesperson', 'store'} and row.get(group_by + '_id') is not None:
            label += ' (#' + str(row[group_by + '_id']) + ')'
        if definition['source'] == 'manual':
            categories = [str(row[column['key']]) for column in definition['columns']
                          if column['type'] == 'text' and row.get(column['key']) is not None][:2]
            label += ' · ' + ' / '.join(categories) if categories else ''
            label += ' · ' + str(row.get('period', '')) + ' · #' + str(row.get('id', ''))
            group_key = (*group_key, row.get('id'))
        group_labels[group_key] = label
        groups[group_key].append(row.get(metric if definition['source'] == 'manual' else 'value'))
    series = []
    for group_key, values in groups.items():
        label = group_labels[group_key]
        known = [Decimal(str(v)) for v in values if v is not None]
        total = sum(known, Decimal(0)) if len(known) == len(values) else None
        series.append({'label': label, 'value': float(total) if total is not None else None,
                       'exact_value': format(total, 'f') if total is not None else None,
                       'record_count': len(values), 'unknown_count': len(values) - len(known)})
    if group_by == 'month':
        series.sort(key=lambda item: item['label'])
    else:
        series.sort(key=lambda item: (item['value'] is None, -(item['value'] or 0), item['label']))
    common = [_column('period', '统计日期', 'date'), _column('store', '门店', 'text'),
              _column('brand', '品牌', 'text'), _column('salesperson', '销售/经办人', 'text')]
    columns = common + (definition['columns'] if definition['source'] == 'manual' else [
        _column('number', '合同号/记录号', 'text'), _column('customer_name', '客户', 'text'),
        _column('value', selected['label'], selected['type'], selected['unit'])])
    return {'report': report, 'metric': metric, 'title': definition['title'], 'metric_label': selected['label'],
            'unit': selected['unit'], 'precision': selected['precision'], 'period_basis': definition['period_basis'],
            'series': series, 'rows': rows, 'columns': columns, 'updated_at': updated_at,
            'record_count': len(rows), 'notice': ('人工统计按每条记录展示，不跨日期累加库存、目标、比例或单价。'
                                                 if definition['source'] == 'manual' else
                                                 '未核定数据保留为空，不按零计算。')}


def build_report(db, user, report, date_from=None, date_to=None, brand='', salesperson_id=None, group_by='salesperson'):
    """Shared DB adapter for JSON and CSV; scopes remain owned by business_records."""
    from sqlalchemy import select
    from .business_records import visible_query
    from .business_records_models import SalesContract, ContractReceipt, AfterSalesRecord, ManualReportRecord
    from .models import User, Store
    key, separator, metric = report.partition(':')
    definition = CATALOG_BY_KEY.get(key)
    if not definition:
        raise ValueError('报表不存在。')
    rows, updated = [], []
    model = (ManualReportRecord if definition['source'] == 'manual' else
             AfterSalesRecord if definition['source'] == 'after_sales' else SalesContract)
    query = visible_query(user, model)
    if model is ManualReportRecord:
        query = query.where(model.report_key == key)
    if brand:
        query = query.where(model.brand == brand)
    owner_field = model.owner_id if model is AfterSalesRecord else model.salesperson_id
    if salesperson_id is not None:
        query = query.where(owner_field == salesperson_id)
    objects = list(db.scalars(query))
    owner_ids = {getattr(item, 'salesperson_id', getattr(item, 'owner_id', None)) for item in objects}
    store_ids = {item.store_id for item in objects}
    names = {row.id: row.display_name for row in db.scalars(select(User).where(User.id.in_(owner_ids - {None})))}
    stores = {row.id: row.name for row in db.scalars(select(Store).where(Store.id.in_(store_ids)))}
    receipt_map = {}
    if model is SalesContract and key != 'expected_receipts':
        ids = [item.id for item in objects]
        if ids:
            receipt_map = {row.contract_id: row for row in db.scalars(
                select(ContractReceipt).where(ContractReceipt.contract_id.in_(ids)))}
    for item in objects:
        owner = getattr(item, 'salesperson_id', getattr(item, 'owner_id', None))
        row = {'id': item.id, 'store_id': item.store_id, 'salesperson_id': owner,
               'store': stores.get(item.store_id, str(item.store_id)),
               'brand': item.brand, 'salesperson': names.get(owner, '未指定销售'),
               'number': getattr(item, 'number', str(item.id)), 'customer_name': getattr(item, 'customer_name', '')}
        if model is ManualReportRecord:
            period = item.period
            row.update(item.values)
        elif model is AfterSalesRecord:
            period = item.business_date
            row['value'] = (_money(item.materials_cents + item.labor_cents)
                            if item.materials_cents is not None and item.labor_cents is not None else None)
        elif key == 'expected_receipts':
            if item.status != 'approved':
                continue
            period = item.contract_date
            row['value'] = _money(item.expected_amount_cents)
        else:
            receipt = receipt_map.get(item.id)
            if receipt is None:
                continue
            period = receipt.received_on
            if key == 'actual_receipts':
                row['value'] = _money(receipt.actual_amount_cents)
            elif key == 'profit':
                row['value'] = _money(item.profit_cents)
            else:
                # V2 binds one contract to one vehicle; no receipt can multiply it.
                row['value'] = '1'
        if not _period(period, date_from, date_to):
            continue
        row['period'] = str(_iso(period))[:10]
        rows.append(row)
        updated.append(_iso(item.updated_at))
        if model is SalesContract and key != 'expected_receipts':
            updated.append(_iso(receipt.created_at))
    return project_report(key, rows, group_by=group_by, metric=metric if separator else None,
                          updated_at=max((x for x in updated if x), default=None))
