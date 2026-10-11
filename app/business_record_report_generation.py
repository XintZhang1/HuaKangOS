"""Pure source mapping and statistical projection for original customer tables."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import SimpleNamespace
from .business_record_report_specs import (
    VEHICLE_REPORTS, GROUPING_FIELDS, GENERATED_FIELDS, STOCK_FIELDS, RATIOS,
    CONTRACT_REPORTS, AFTER_SALES_REPORTS, SHARED_FIELDS, TARGET_FIELDS)

SERVICE_LABELS = {'repair': '维修', 'maintenance': '保养', 'accident': '事故维修',
    'renewal': '续保', 'extended_warranty': '延保', 'accessories': '精品销售'}


def money(value):
    return None if value is None else format(Decimal(value) / 100, '.2f')


def approved_amount(contract, key):
    """A new approved office revision supersedes valuations, including unknowns.

    Legacy contract columns are retained as their historical facts; their new
    office revision lives in its own frozen payload instead of rewriting them.
    """
    office = getattr(contract, 'office_approved_data', None)
    if key == 'expected_amount_cents' and office is not None and office.get(key) is None:
        # Optional office input does not erase the amount already agreed in
        # the approved customer contract.
        return getattr(contract, key)
    return office.get(key) if office is not None else getattr(contract, key)


def field_values(definition, labels):
    return {column['key']: labels[column['label']] for column in definition['columns']
            if column['label'] in labels}


def prefill_contract_values(report_key, contract, salesperson_name=''):
    """Map only identical business meanings. Invoice facts are not contract dates."""
    from .business_record_reports import CATALOG_BY_KEY
    if report_key not in VEHICLE_REPORTS:
        raise ValueError('只有车辆明细报表支持关联合同；汇总表由来源明细生成。')
    if contract.status not in {'priced', 'approved'}:
        raise ValueError('合同须先完成审批，才能带入内勤统计明细。')
    form = contract.form_data or {}
    labels = {'台数': '1', '车型': contract.model, '车辆型号': contract.model,
        '车架号': contract.vin, '销售顾问': salesperson_name,
        '客户名称': contract.customer_name, '客户电话': contract.customer_phone,
        '地址': form.get('buyer_address'), '颜色': form.get('exterior_color'),
        '颜色（原表列名2暮云灰）': form.get('exterior_color'), '外饰颜色': form.get('exterior_color'),
        '颜色或内饰': form.get('interior_color'), '车辆售价': money(contract.sale_price_cents),
        '精品成本（赠送）': money(approved_amount(contract, 'gift_cost_cents')), '精品明细': contract.gift_description,
        '单车利润': money(approved_amount(contract, 'profit_cents')), '核定单车利润': money(approved_amount(contract, 'profit_cents')),
        '单车利润2': money(approved_amount(contract, 'profit_cents')), '单车利润22': money(approved_amount(contract, 'profit_cents'))}
    # Old free-text supplemental amounts are not trusted as finite decimals.
    loan = form.get('loan_amount')
    if loan:
        try:
            parsed = Decimal(str(loan))
            if parsed.is_finite() and parsed >= 0 and max(0, -parsed.as_tuple().exponent) <= 2:
                labels['贷款金额'] = format(parsed, 'f')
        except (InvalidOperation, ValueError):
            pass
    values = field_values(CATALOG_BY_KEY[report_key], labels)
    values = {key: value for key, value in values.items() if value is not None}
    locked = list(values)
    if getattr(contract, 'workflow_version', None) in {'trial-v29', 'trial-v30'}:
        financial_labels = {'精品成本（赠送）', '单车利润', '核定单车利润', '单车利润2', '单车利润22'}
        financial_keys = {column['key'] for column in CATALOG_BY_KEY[report_key]['columns']
                          if column['label'] in financial_labels}
        locked = [key for key in locked if key not in financial_keys]
    return {'values': values, 'locked_fields': locked,
        'source_fields': {key: '合同及内勤核价' for key in values},
        'contract_id': contract.id, 'contract_version': contract.version,
        'period': str(contract.contract_date), 'brand': contract.brand,
        'salesperson_id': contract.salesperson_id}


def effective_records(records):
    """Append-only corrections replace their predecessor, never alter old values."""
    superseded = {row.get('supersedes_id') for row in records if row.get('supersedes_id') is not None}
    return [dict(row) for row in records if row.get('id') not in superseded]


def dimension(row, definition):
    fields = GROUPING_FIELDS.get(definition['key'], [])
    return (row.get('store_id'), row.get('brand') or '', row.get('salesperson_id'),
            *(row.get(key) or '' for key in fields))


def latest_snapshots(rows, definition):
    """A monthly cumulative input is one observation, not a new transaction."""
    snapshots, details = {}, []
    for row in rows:
        if row.get('entry_mode') not in {'snapshot', 'final', 'target'}:
            details.append(row)
            continue
        key = (str(row.get('period', ''))[:7], dimension(row, definition),
               row.get('entry_mode') == 'final', row.get('entry_mode') == 'target')
        order = (str(row.get('_snapshot_source_period', row.get('period', ''))), row.get('id') or 0)
        prior = snapshots.get(key)
        if prior is None or order > (str(prior.get('period', '')), prior.get('id') or 0):
            snapshots[key] = row
    return details + list(snapshots.values())


def _values(rows, key):
    return [row.get(key) for row in rows if key in row.get('_applicable_fields', row)]


def _sum(values):
    if not values or any(value is None or value == '' for value in values):
        return None
    return sum((Decimal(str(value)) for value in values), Decimal(0))


def _closing(rows, key, definition):
    latest = {}
    for row in rows:
        if key not in row.get('_applicable_fields', row):
            continue
        dim = dimension(row, definition)
        order = (str(row.get('_snapshot_source_period', row.get('period', ''))), row.get('id') or 0)
        if dim not in latest or order > latest[dim][0]:
            latest[dim] = (order, row.get(key))
    return _sum([value for _, value in latest.values()])


def _shared(rows, key):
    scopes = defaultdict(list)
    for row in rows:
        if key in row.get('_applicable_fields', row):
            scopes[(row.get('store_id'), row.get('brand') or '', str(row.get('period', ''))[:7])].append(row)
    values, conflict = [], False
    for entries in scopes.values():
        automatic = {row['contract_id']: row.get(key) for row in entries
                     if row.get('entry_mode') == 'generated' and row.get('contract_id') is not None}
        if automatic:
            values.append(_sum(list(automatic.values())))
            continue
        known = {Decimal(str(row[key])) for row in entries if row.get(key) not in (None, '')}
        if len(known) > 1:
            conflict = True
        values.append(next(iter(known)) if len(known) == 1 else None)
    return _sum(values), conflict


def _operand(numbers, expression):
    if isinstance(expression, (list, tuple)):
        return _sum([numbers.get(key) for key in expression])
    return numbers.get(expression)


def _profit_totals(rows, key):
    """The original 'all vehicles' block is a subtotal, not another sale."""
    scopes = defaultdict(list)
    for row in rows:
        if key in row.get('_applicable_fields', row):
            scopes[(row.get('store_id'), row.get('brand'), row.get('salesperson_id'),
                    str(row.get('period', ''))[:7])].append(row)
    amounts, conflict = [], False
    all_labels = {'全部', '全部车辆', '合计', '总计'}
    for entries in scopes.values():
        parents = [row for row in entries if row.get('c11') in all_labels]
        children = [row for row in entries if row.get('c11') not in all_labels]
        known = {Decimal(str(row[key])) for row in parents if row.get(key) not in (None, '')}
        if known:
            if len(known) != 1:
                amounts.append(None)
                conflict = True
                continue
            total = next(iter(known))
            child_total = _sum([row.get(key) for row in children])
            categories = {row.get('c11') for row in children}
            if {'正常车辆', '冰雹车'} <= categories and child_total is not None and child_total != total:
                amounts.append(None)
                conflict = True
            else:
                amounts.append(total)
        else:
            amounts.extend(row.get(key) for row in children or parents)
    return _sum(amounts), conflict


def _target_ambiguities(rows, definition):
    """Do not sum facts whose target/series scopes might describe the same work."""
    if definition['key'] != 'sales_targets':
        return set(), []
    ambiguous, warnings = set(), []
    targets = [row for row in rows if row.get('entry_mode') == 'target']
    def applies(row, field):
        return field in row.get('_applicable_fields', row)
    for target in targets:
        for other in rows:
            if other is target or other.get('entry_mode') == 'generated':
                continue
            if target.get('store_id') != other.get('store_id') or str(target.get('period'))[:7] != str(other.get('period'))[:7]:
                continue
            if any(target.get(field) and other.get(field) and target[field] != other[field]
                   for field in ('brand', 'c01')):
                continue
            ambiguous |= {field for field in TARGET_FIELDS if applies(target, field) and applies(other, field)}
    if ambiguous:
        warnings.append('管理者月度目标与旧目标或未分品牌目标存在范围重叠，相关合计留空；请核对品牌、系列和旧目标来源，不能将全店目标与分项重复相加。')
    actual_fields = {'c06', 'c07', 'c08', 'c09'}
    generated = [row for row in rows if row.get('entry_mode') == 'generated' and not row.get('c01')]
    for manual in rows:
        if manual.get('entry_mode') in {'generated', 'target'} or not manual.get('c01'):
            continue
        for automatic in generated:
            if _overlap(manual, automatic, definition, include_categories=False):
                conflict = {field for field in actual_fields if applies(manual, field) and applies(automatic, field)}
                if conflict:
                    ambiguous |= conflict
                    if not any('未填写系列的业务' in warning for warning in warnings):
                        warnings.append('未填写系列的业务与人工分系列实绩可能重叠，相关合计留空；请核实业务系列或使用已核对的完整范围数据。')
    return ambiguous, warnings


def aggregate_rows(rows, definition, label):
    result = {'label': label, 'record_count': len(rows), 'unknown_count': 0, 'aggregation_warnings': [],
              'source_labels': sorted({row.get('source_label', '人工核填') for row in rows})}
    rules = definition.get('aggregation_rules', {})
    columns = definition['columns'] if definition['source'] == 'manual' else definition['metrics']
    numbers = {}
    for column in columns:
        key = column['key']
        values = _values(rows, key)
        if column['type'] in {'text', 'date'}:
            known = sorted({str(value) for value in values if value not in (None, '')})
            result[key] = known[0] if len(known) == 1 else '、'.join(known) if len(known) <= 5 else '多项（见明细）'
            continue
        kind = rules.get(key, {}).get('kind', 'sum')
        if kind == 'ratio':
            continue
        if kind == 'closing_snapshot':
            numbers[key] = _closing(rows, key, definition)
        elif kind == 'shared_scope':
            numbers[key], conflict = _shared(rows, key)
            if conflict:
                result['aggregation_warnings'].append(column['label'] + '存在同门店、品牌、月份不一致的共享值，请更正后汇总。')
        elif kind == 'last_day_sum':
            applicable = [row for row in rows if key in row.get('_applicable_fields', row)]
            last = max((str(row.get('period', '')) for row in applicable), default='')
            numbers[key] = _sum([row.get(key) for row in applicable if str(row.get('period', '')) == last])
        elif kind == 'non_additive':
            # A rate without an identified denominator has no defensible average.
            numbers[key] = Decimal(str(values[0])) if len(values) == 1 and values[0] not in (None, '') else None
        else:
            numbers[key] = _sum(values)
        if definition['key'] in {'sales_profit_statement', 'secondary_profit_statement'} and kind == 'sum':
            numbers[key], conflict = _profit_totals(rows, key)
            if conflict:
                result['aggregation_warnings'].append(column['label'] + '的全部车辆小计与分类数据不一致，请核对。')
        result['unknown_count'] += sum(value in (None, '') for value in values)
    ambiguous, warnings = _target_ambiguities(rows, definition)
    for field in ambiguous:
        numbers[field] = None
    result['aggregation_warnings'].extend(warnings)
    if definition['key'] == 'insurance_renewal':
        # Institution-specific inside/outside facts sum to the store total.
        # If either side is absent, retain the unique clerk-confirmed total.
        for output, operands in (('c07', ('c02', 'c04')), ('c09', ('c03', 'c05'))):
            derived = _operand(numbers, operands)
            if derived is not None:
                numbers[output] = derived
    for key, rule in rules.items():
        if rule['kind'] != 'ratio':
            continue
        numerator, denominator = _operand(numbers, rule['numerator']), _operand(numbers, rule['denominator'])
        numbers[key] = (numerator / denominator * rule['scale']
                        if numerator is not None and denominator not in (None, 0) else None)
        operands = (rule['numerator'] if isinstance(rule['numerator'], (list, tuple)) else [rule['numerator']])
        operands = list(operands) + list(rule['denominator'] if isinstance(rule['denominator'], (list, tuple)) else [rule['denominator']])
        if numbers[key] is None and denominator != 0 and not (set(operands) & ambiguous):
            entered = _values(rows, key)
            # One clerk-confirmed observation can be displayed unchanged when
            # its operands were not recorded. Multiple rates cannot be averaged.
            if len(entered) == 1 and entered[0] not in (None, ''):
                numbers[key] = Decimal(str(entered[0]))
    for column in columns:
        if column['type'] in {'text', 'date'}:
            continue
        number = numbers.get(column['key'])
        precision = column['precision']
        result[column['key']] = (format(number.quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP), 'f')
                                 if number is not None else None)
    result['source_label'] = '；'.join(result['source_labels'])
    return result


def group_identity(row, group_by, category_field):
    if group_by == 'group':
        return ('group',), '合计（当前授权范围）'
    if group_by == 'category':
        value = row.get(category_field) or '未填写分类'
        return ('category', value), SERVICE_LABELS.get(value, value) if category_field == 'service_type' else str(value)
    if group_by == 'month':
        value = str(row.get('period') or '')[:7] or '未填日期'
        return ('month', value), value
    if group_by == 'brand':
        value = row.get('brand') or '未填品牌'
        return ('brand', value), value
    if group_by == 'store':
        return ('store', row.get('store_id')), row.get('store') or '未指定门店'
    if row.get('handler_name'):
        return ('handler', row.get('store_id'), row['handler_name']), f"{row['handler_name']} · {row.get('store', '')}"
    return ('salesperson', row.get('salesperson_id')), row.get('salesperson') or '未指定销售/经办人'


def project(definition, records, *, group_by, metric, updated_at=None, category_field='',
            category_value='', source_mode='combined', legacy_rows=None):
    if group_by not in {'salesperson', 'store', 'brand', 'month', 'group', 'category'}:
        raise ValueError('不支持的报表分组。')
    fields = {column['key']: column for column in definition['metrics']}
    if metric not in fields:
        raise ValueError('请选择当前报表中的指标。')
    allowed_categories = {column['key'] for column in definition.get('grouping_fields', [])}
    if category_field and category_field not in allowed_categories:
        raise ValueError('请选择当前报表可用的分类字段。')
    if group_by == 'category' and not category_field:
        raise ValueError('请先选择用于分组的分类字段。')
    rows = [dict(row) for row in records if not category_value or str(row.get(category_field) or '') == category_value]
    legacy = [dict(row) for row in (legacy_rows or [])
              if not category_value or str(row.get(category_field) or '') == category_value]
    grouped, labels = defaultdict(list), {}
    for row in rows:
        identity, label = group_identity(row, group_by, category_field)
        grouped[identity].append(row)
        labels[identity] = label
    summary = [aggregate_rows(values, definition, labels[key]) for key, values in grouped.items()]
    grand = aggregate_rows(rows, definition, '合计（当前授权范围）')
    # Contribution ratios use the same authorized, filtered denominator as totals.
    contribution = {'model_profit': ('c06', 'c04'), 'model_profit_sheet5': ('c05', 'c03'),
                    'insurance_resources': ('c14', 'c02')}.get(definition['key'])
    if contribution:
        output, value_key = contribution
        total = Decimal(grand[value_key]) if grand.get(value_key) is not None else None
        for entry in [*summary, grand]:
            value = Decimal(entry[value_key]) if entry.get(value_key) is not None else None
            if value is not None and total not in (None, 0):
                entry[output] = format((value / total * 100).quantize(Decimal('.000001')), 'f')
            elif total == 0:
                entry[output] = None
    summary.sort(key=(lambda row: row['label']) if group_by == 'month' else
                 (lambda row: (row.get(metric) is None, -Decimal(row[metric] or 0), row['label'])))
    selected = fields[metric]
    series = [{'label': row['label'], 'value': float(row[metric]) if row.get(metric) is not None else None,
               'exact_value': row.get(metric), 'record_count': row['record_count'],
               'unknown_count': row['unknown_count']} for row in summary]
    common = [{'key': key, 'label': label, 'type': kind, 'unit': '', 'precision': None}
              for key, label, kind in (('period', '统计日期', 'date'), ('store', '门店', 'text'),
              ('brand', '品牌', 'text'), ('salesperson', '销售/经办人', 'text'),
              ('number', '合同号/记录号', 'text'), ('source_label', '数据来源', 'text'), ('note', '备注', 'text'))]
    value_columns = definition['columns'] if definition['source'] == 'manual' else definition['metrics']
    summary_columns = [{'key': 'label', 'label': '分组', 'type': 'text', 'precision': None, 'unit': ''}] + value_columns
    notice = ('累计快照每月每维度取最新，单笔记录累加；库存取截至日最后快照。'
        '比例和单价仅在分子分母明确时重算，无法汇总或分母为零保留为空。'
        '旧记录单独列示，不并入当前排名。')
    if definition.get('automatic_source') and source_mode == 'combined':
        notice += '同月同维度的内勤最终月值替代相应自动统计，不重复累加；普通补录仅补充其他字段。'
    if definition['source'] != 'manual':
        notice = '按当前授权范围及筛选条件汇总；未核定数据保留为空，不按零计算。'
    if definition.get('input_notice'):
        notice += definition['input_notice']
    if grand['aggregation_warnings']:
        notice += '当前数据需核对：' + '；'.join(grand['aggregation_warnings'])
    def public(row):
        return {key: value for key, value in row.items() if not key.startswith('_')}
    return {'report': definition['key'], 'metric': metric, 'title': definition['title'],
        'metric_label': selected['label'], 'unit': selected['unit'], 'precision': selected['precision'],
        'period_basis': definition['period_basis'], 'series': series, 'rows': [public(row) for row in rows],
        'columns': common + value_columns, 'summary_rows': summary, 'summary_columns': summary_columns,
        'grand_total': grand, 'legacy_rows': [public(row) for row in legacy], 'legacy_count': len(legacy),
        'source_mode': source_mode, 'updated_at': updated_at, 'record_count': len(rows), 'notice': notice}


def contract_statistics(key, contract, receipt, category, supplement, definition):
    """Confirmed collection is the only sales-performance event."""
    extension_report = key in {'bank_finance', 'insurance_resources', 'insurance_settlement', 'extended_warranty'}
    if receipt is None and not extension_report:
        return None
    profit, cost = money(approved_amount(contract, 'profit_cents')), money(approved_amount(contract, 'cost_cents'))
    income = money(receipt.actual_amount_cents) if receipt is not None else None
    if extension_report:
        from .business_record_reports import CATALOG_BY_KEY
        vehicle_key = supplement.report_key if supplement is not None else 'vehicle_details'
        raw = dict(supplement.values) if supplement is not None else {}
        raw.update(prefill_contract_values(vehicle_key, contract)['values'])
        labels = {column['label']: raw.get(column['key']) for column in CATALOG_BY_KEY[vehicle_key]['columns']}
        if key == 'bank_finance':
            loan = labels.get('核实放款金额')
            if loan is None:
                return None
            return {'c01': labels.get('金融机构') or '未填写金融机构',
                    'c02': labels.get('金融类别') or '未填写金融类别',
                    'c04': '1' if Decimal(loan) > 0 else '0' if Decimal(loan) == 0 else None,
                    'c05': loan, 'c06': labels.get('银行返佣')}
        if key in {'insurance_resources', 'insurance_settlement'}:
            premium, policies = labels.get('保险统计保费'), labels.get('保险出单数量')
            if premium is None and policies is None:
                return None
            if key == 'insurance_settlement':
                if premium is None:
                    return None
                return {'c01': labels.get('承保公司') or '未填写保险公司', 'c04': premium}
            return {'c01': labels.get('承保公司') or '未填写保险公司',
                    'c02': premium, 'c03': policies}
        warranty = labels.get('延保出单数量')
        if warranty is None:
            return None
        return {'c01': labels.get('延保合作公司') or '未填写延保合作公司', 'c02': '1', 'c04': warranty}
    if key == 'sales_targets':
        values = {'c06': '1'}
        if supplement is not None:
            from .business_record_reports import CATALOG_BY_KEY
            source = CATALOG_BY_KEY.get(supplement.report_key, {})
            series_field = next((field['key'] for field in source.get('columns', [])
                                 if field['label'] == '车系'), None)
            if series_field and supplement.values.get(series_field):
                values['c01'] = supplement.values[series_field]
        return values
    if key == 'sales_overview':
        return {'c04': '1'}
    if key in {'sales_profit_statement', 'secondary_profit_statement'}:
        secondary = category in {'二级车辆', '补充车辆'}
        if (key == 'secondary_profit_statement') != secondary:
            return None
        return {'c01': '1', 'c02': profit, 'c03': income, 'c04': cost, 'c11': category}
    if key == 'individual_profit':
        return {'c04': '1', 'c07': profit, 'c08': profit if category != '冰雹车' else '0',
                'c09': profit if category == '冰雹车' else '0'}
    if key == 'model_profit':
        return {'c01': category, 'c02': contract.model, 'c03': '1', 'c04': profit}
    if key == 'model_profit_sheet5':
        return {'c01': contract.model, 'c02': '1', 'c03': profit}
    return None


def after_sales_statistics(key, item):
    revenue = money(item.materials_cents + item.labor_cents)
    profit = money(item.materials_cents + item.labor_cents - item.cost_cents) if item.cost_cents is not None else None
    mechanical = item.service_type in {'repair', 'maintenance'}
    accident = item.service_type == 'accident'
    if key == 'after_sales_revenue':
        return {'value': revenue, 'materials': money(item.materials_cents),
                'labor': money(item.labor_cents), 'cost': money(item.cost_cents),
                'profit': profit, 'count': '1'}
    if key == 'sales_targets':
        return {'c07': revenue if mechanical else '0', 'c08': revenue if accident else '0', 'c09': revenue}
    if key == 'after_sales_monthly':
        return {'c01': SERVICE_LABELS[item.service_type], 'c03': revenue,
                'c12': money(item.materials_cents), 'c14': money(item.labor_cents)}
    if key == 'after_sales_targets':
        return {'c04': '1' if mechanical else '0', 'c05': revenue if mechanical else '0',
            'c08': '1' if accident else '0', 'c09': revenue if accident else '0',
            'c12': profit if accident else '0', 'c16': revenue,
            'c18': revenue if item.service_type in {'accessories', 'maintenance'} else '0'}
    return None


def _in_period(period, start, end):
    value = str(period or '')[:10]
    return bool(value) and (not start or value >= str(start)) and (not end or value <= str(end))


def _overlap(manual, automatic, definition, include_categories=True):
    if str(manual.get('period'))[:7] != str(automatic.get('period'))[:7]:
        return False
    for key in ('store_id', 'brand', 'salesperson_id'):
        value = manual.get(key)
        if value not in (None, '') and value != automatic.get(key):
            return False
    for key in GROUPING_FIELDS.get(definition['key'], []) if include_categories else []:
        if key == 'c11' and definition['key'] in {'sales_profit_statement', 'secondary_profit_statement'} and manual.get(key) in {'全部', '全部车辆', '合计', '总计'}:
            continue
        if definition['key'] == 'sales_targets' and key == 'c01' and manual.get(key):
            # A missing business series cannot replace a confirmed series or be
            # removed by that series' manually confirmed performance figure.
            if manual[key] != automatic.get(key):
                return False
        if manual.get(key) and automatic.get(key) and manual[key] != automatic[key]:
            return False
    return True


def fill_month_window(result, date_from, date_to):
    """Keep absent calendar months explicit in both chart and summary export."""
    if date_from is None or date_to is None:
        return result
    start, end = str(date_from)[:7], str(date_to)[:7]
    year, month = map(int, start.split('-'))
    end_year, end_month = map(int, end.split('-'))
    summaries = {row['label']: row for row in result['summary_rows']}
    series = {row['label']: row for row in result['series']}
    labels = []
    while (year, month) <= (end_year, end_month):
        label = f'{year:04d}-{month:02d}'
        labels.append(label)
        if label not in summaries:
            blank = {column['key']: None if column['type'] not in {'text', 'date'} else ''
                     for column in result['summary_columns']}
            blank.update(label=label, record_count=0, unknown_count=1,
                         aggregation_warnings=[], source_labels=[])
            summaries[label] = blank
            series[label] = {'label': label, 'value': None, 'exact_value': None,
                             'record_count': 0, 'unknown_count': 1}
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    result['summary_rows'] = [summaries[label] for label in labels]
    result['series'] = [series[label] for label in labels]
    result['notice'] += '所选月份窗口逐月列示，未录入月份留空，不按零处理或跨过缺失月份比较。'
    return result


def build(db, user, report, *, date_from=None, date_to=None, brand='', salesperson_id=None,
          group_by='salesperson', handler_name='', service_type='', category_field='',
          category_value='', source_mode='combined', snapshot_sources=False):
    """All data access passes through the original identity/store scope adapter."""
    from sqlalchemy import select
    from sqlalchemy.orm import aliased
    from .business_records import visible_query
    from .business_records_models import SalesContract, ContractReceipt, AfterSalesRecord, ManualReportRecord
    from .models import User, Store
    from .business_record_reports import CATALOG_BY_KEY
    from .business_record_report_specs import assert_report_access, can_view_sensitive_reports
    assert_report_access(user, report)
    key, separator, metric = report.partition(':')
    definition = CATALOG_BY_KEY.get(key)
    if definition is None:
        raise ValueError('报表不存在。')
    source_mode = source_mode or 'combined'
    if source_mode not in {'combined', 'generated', 'manual'}:
        raise ValueError('不支持的数据来源。')
    if service_type and service_type not in SERVICE_LABELS:
        raise ValueError('不支持的售后类别。')
    if date_from and date_to and date_from > date_to:
        raise ValueError('开始日期不得晚于结束日期。')
    is_manual = definition['source'] == 'manual'
    successor = aliased(ManualReportRecord)
    def current_manual(query):
        # Resolve supersession inside the same store before applying the outer
        # employee visibility. A reassigned correction must retire the old row
        # for its former owner without revealing the replacement's contents.
        return query.where(~select(successor.id).where(
            successor.store_id == ManualReportRecord.store_id,
            successor.supersedes_id == ManualReportRecord.id,
        ).correlate(ManualReportRecord).exists())
    manual_objects = []
    if is_manual or key == 'profit':
        # Corrections are resolved before period selection, including date corrections.
        query = current_manual(visible_query(user, ManualReportRecord)).where(
            ManualReportRecord.report_key == ('individual_profit' if key == 'profit' else key))
        if key == 'profit':
            query = query.where(ManualReportRecord.entry_mode == 'final')
        manual_objects = list(db.scalars(query))
    contracts = []
    if definition['source'] == 'contracts' or key in CONTRACT_REPORTS:
        query = visible_query(user, SalesContract)
        if brand:
            query = query.where(SalesContract.brand == brand)
        if salesperson_id is not None:
            query = query.where(SalesContract.salesperson_id == salesperson_id)
        contracts = list(db.scalars(query))
    after_sales = []
    if definition['source'] == 'after_sales' or key in AFTER_SALES_REPORTS:
        query = visible_query(user, AfterSalesRecord)
        if brand:
            query = query.where(AfterSalesRecord.brand == brand)
        if handler_name:
            query = query.where(AfterSalesRecord.handler_name == handler_name)
        if service_type:
            query = query.where(AfterSalesRecord.service_type == service_type)
        # salesperson_id remains the sales-account filter for sales facts only.
        # It must never silently mean the clerk who happened to enter a service.
        after_sales = list(db.scalars(query))
    contract_ids = [item.id for item in contracts]
    receipts = {item.contract_id: item for item in db.scalars(select(ContractReceipt).where(
        ContractReceipt.contract_id.in_(contract_ids)))} if contract_ids else {}
    supplements = []
    if contract_ids:
        supplements = list(db.scalars(current_manual(visible_query(user, ManualReportRecord)).where(
            ManualReportRecord.contract_id.in_(contract_ids), ManualReportRecord.report_key.in_(VEHICLE_REPORTS))))
    objects = [*manual_objects, *contracts, *after_sales]
    owner_ids = {getattr(item, 'salesperson_id', getattr(item, 'owner_id', None)) for item in objects}
    store_ids = {item.store_id for item in objects}
    names = {item.id: item.display_name for item in db.scalars(select(User).where(User.id.in_(owner_ids - {None})))}
    stores = {item.id: item.name for item in db.scalars(select(Store).where(Store.id.in_(store_ids)))}
    updated = [str(item.updated_at.isoformat()) for item in objects if item.updated_at]
    updated += [str(item.created_at.isoformat()) for item in receipts.values() if item.created_at]
    def base(item):
        owner = getattr(item, 'salesperson_id', getattr(item, 'owner_id', None))
        return {'id': item.id, 'store_id': item.store_id, 'store': stores.get(item.store_id, str(item.store_id)),
            'brand': item.brand, 'salesperson_id': owner, 'salesperson': names.get(owner, '未指定销售/经办人'),
            'number': getattr(item, 'number', str(item.id)), 'customer_name': getattr(item, 'customer_name', '')}
    def manual_row(item):
        values = dict(item.values)
        if item.entry_mode == 'target':
            # The original slash remains in the target history. Report numbers
            # retain null, never zero, for both unknown and inapplicable cells.
            values = {field: None if field in TARGET_FIELDS and value == '/' else value
                      for field, value in values.items()}
        return dict(base(item), **values, period=str(item.period), entry_mode=item.entry_mode,
            contract_id=item.contract_id, supersedes_id=item.supersedes_id,
            source_label='管理者下达月度目标' if item.entry_mode == 'target' else
                '历史人工记录' if item.entry_mode == 'legacy' else '人工核填', note=item.note or '')
    manual_rows = effective_records([manual_row(item) for item in manual_objects])
    if key == 'profit':
        for row in manual_rows:
            row['value'] = row.get('c07')
    manual_rows = [row for row in manual_rows if (not brand or row['brand'] == brand)
                   and (salesperson_id is None or row['salesperson_id'] == salesperson_id)]
    legacy = [row for row in manual_rows if row['entry_mode'] == 'legacy' and _in_period(row['period'], date_from, date_to)]
    manual_rows = latest_snapshots([row for row in manual_rows if row['entry_mode'] != 'legacy'
                                   and _in_period(row['period'], None, date_to)], definition)
    supplements_by_contract = {}
    for item in effective_records([{'id': value.id, 'supersedes_id': value.supersedes_id, '_object': value}
                                   for value in supplements if value.entry_mode != 'legacy']):
        value = item['_object']
        previous = supplements_by_contract.get(value.contract_id)
        if previous is None or (value.period, value.id) > (previous.period, previous.id):
            supplements_by_contract[value.contract_id] = value
    generated = []
    for contract in contracts:
        new_flow = getattr(contract, 'workflow_version', None) in {'trial-v29', 'trial-v30'}
        approved_office = getattr(contract, 'office_approved_data', None)
        source = supplements_by_contract.get(contract.id)
        if approved_office:
            # Only the exact approved payload is a source. An independently
            # appended manual draft must not replace it before approval.
            source = SimpleNamespace(report_key=approved_office['report_key'],
                period=approved_office['period'], values=approved_office.get('values', {}),
                note=approved_office.get('note', ''))
        elif new_flow:
            source = None
        vehicle_key = source.report_key if source is not None else 'vehicle_details'
        category = {'vehicle_details': '正常车辆', 'hail_vehicle_details': '冰雹车',
            'secondary_vehicle_details': '二级车辆', 'vehicle_details_sheet2': '补充车辆'}[vehicle_key]
        receipt = receipts.get(contract.id)
        row = base(contract)
        row.update(contract_id=contract.id, entry_mode='generated', source_label='合同及内勤核价', note='')
        if key in VEHICLE_REPORTS:
            if vehicle_key != key or contract.status not in {'priced', 'approved'}:
                continue
            if new_flow and not approved_office:
                continue
            period = approved_office.get('period') if approved_office else source.period if source else contract.contract_date
            values = dict(source.values) if source is not None else {}
            values.update(prefill_contract_values(key, contract, row['salesperson'])['values'])
            row['source_label'] = '总经理批准的内勤资料' if approved_office else row['source_label'] + ('＋内勤补充' if source is not None else '')
            row['note'] = source.note if source is not None else ''
        elif definition['source'] == 'contracts':
            if key == 'expected_receipts':
                if contract.status != 'approved':
                    continue
                expected = approved_amount(contract, 'expected_amount_cents')
                period, values = contract.contract_date, {'value': money(expected)}
                if new_flow and not approved_office:
                    values = {'value': money(contract.sale_price_cents)}
            else:
                if receipt is None:
                    continue
                period = receipt.received_on
                values = {'value': money(receipt.actual_amount_cents) if key == 'actual_receipts'
                    else money(approved_amount(contract, 'profit_cents')) if key == 'profit' and (not new_flow or approved_office)
                    else None if key == 'profit' else '1'}
                row['source_label'] = '财务确认到账＋内勤核价'
        else:
            if new_flow and not approved_office and key in {'bank_finance', 'insurance_resources', 'insurance_settlement', 'extended_warranty'}:
                continue
            values = contract_statistics(key, contract, receipt, category, source, definition)
            if values is None:
                continue
            extension_report = key in {'bank_finance', 'insurance_resources', 'insurance_settlement', 'extended_warranty'}
            period = ((approved_office.get('period') if approved_office else source.period if source else receipt.received_on if receipt else None)
                      if extension_report else receipt.received_on)
            row['source_label'] = '总经理批准的内勤附带信息' if extension_report and approved_office else '已核实业务记录＋内勤核价'
        if not _in_period(period, date_from, date_to):
            continue
        row.update(values)
        row.update(period=str(period), _applicable_fields=set(values))
        generated.append(row)
    for item in after_sales:
        if not _in_period(item.business_date, date_from, date_to):
            continue
        values = after_sales_statistics(key, item)
        if values is None:
            continue
        row = base(item)
        row.update(values)
        row.update(period=str(item.business_date), entry_mode='generated', handler_name=item.handler_name,
            salesperson=item.handler_name, salesperson_id=None, service_type=item.service_type,
            source_label='售后业务记录', note='', _applicable_fields=set(values))
        generated.append(row)
    prepared = []
    # An explicitly final monthly value is authoritative for its scope. It is
    # never another transaction to add to the automatically generated numbers.
    target_rows = [row for row in manual_rows if row['entry_mode'] == 'target'
                   and _in_period(row['period'], date_from, date_to)]
    def has_issued_target(row):
        # Only replace the exact same target scope. An unclassified old target
        # is not guessed to be one of the manager's named series.
        return key == 'sales_targets' and row.get('salesperson_id') is None and any(
            target['store_id'] == row['store_id'] and target['brand'] == row['brand']
            and target.get('c01') == row.get('c01')
            and target['period'][:7] == row['period'][:7] for target in target_rows)
    final_rows = [row for row in manual_rows if row['entry_mode'] == 'final'
                  and _in_period(row['period'], date_from, date_to)]
    value_columns = definition['columns'] if is_manual else definition['metrics']
    numeric_keys = {field['key'] for field in value_columns if field['type'] not in {'text', 'date'}}
    def final_fields(row):
        fields = {key for key in numeric_keys if row.get(key) not in (None, '')}
        return fields - TARGET_FIELDS - {'c10', 'c11'} if has_issued_target(row) else fields
    for index, first in enumerate(final_rows):
        for second in final_rows[index + 1:]:
            if final_fields(first) & final_fields(second) and (
                    _overlap(first, second, definition) or _overlap(second, first, definition)):
                raise ValueError('内勤最终月值存在重叠范围，请更正为互不重复的销售、品牌和分类后再统计。')
    if source_mode == 'combined':
        for row in generated:
            overrides = set().union(*(final_fields(final) for final in final_rows if _overlap(final, row, definition)))
            if overrides:
                row['_applicable_fields'] = set(row.get('_applicable_fields', row)) - overrides
                for field in overrides:
                    if field in row:
                        row[field] = None
        generated = [row for row in generated if set(row.get('_applicable_fields', row)) & numeric_keys]
    generated_by_period_store = defaultdict(list)
    for row in generated:
        generated_by_period_store[(row['period'][:7], row['store_id'])].append(row)
    contract_lookup = {item.id: item for item in contracts}
    for row in manual_rows:
        if row.get('contract_id') and key in VEHICLE_REPORTS:
            if source_mode != 'manual':
                # The corresponding automatic vehicle row already contains this supplement.
                continue
            linked = contract_lookup.get(row['contract_id'])
            if linked is not None and linked.status in {'priced', 'approved'}:
                approved_office = getattr(linked, 'office_approved_data', None)
                if approved_office and row['id'] != approved_office.get('manual_report_id'):
                    continue
                if getattr(linked, 'workflow_version', None) in {'trial-v29', 'trial-v30'} and not approved_office:
                    continue
                row.update(prefill_contract_values(key, linked, names.get(linked.salesperson_id, ''))['values'])
                row['source_label'] = '内勤补充（合同共有事实锁定）'
            else:
                # The original manual record remains accessible in its history,
                # but an obsolete valuation is not a current business fact.
                continue
        applicable = {column['key'] for column in value_columns}
        if row['entry_mode'] == 'target':
            applicable &= TARGET_FIELDS | {'c01'}
        elif has_issued_target(row):
            applicable -= TARGET_FIELDS | {'c10', 'c11'}
        if not _in_period(row['period'], date_from, date_to):
            # Before-period rows only carry closing stock, not prior period revenue.
            applicable &= STOCK_FIELDS.get(key, set())
            if not applicable:
                continue
            row['note'] = ((row.get('note') or '') + '；库存来源快照日期：' + row['period']).lstrip('；')
            row['_snapshot_source_period'] = row['period']
            row['period'] = str(date_from)
        if source_mode in {'combined', 'manual'} and row['entry_mode'] not in {'final', 'target'} and any(
                _overlap(final, row, definition) for final in final_rows):
            applicable -= set().union(*(final_fields(final) for final in final_rows if _overlap(final, row, definition)))
            row['source_label'] = '人工补录（数值已由内勤最终月值替代）'
        if source_mode == 'combined' and key in GENERATED_FIELDS and row['entry_mode'] not in {'final', 'target'}:
            candidates = generated_by_period_store[(row['period'][:7], row['store_id'])]
            overlaps = [item for item in candidates if _overlap(row, item, definition)]
            if overlaps:
                # Each field is displaced only by an actual contributing source.
                replaced = set().union(*(item.get('_applicable_fields', set()) for item in overlaps))
                replaced |= {field for field, rule in RATIOS.get(key, {}).items()
                             if rule[0] in replaced or rule[1] in replaced}
                applicable -= replaced & GENERATED_FIELDS[key]
                row['source_label'] = '人工补充（同维度实绩采用业务来源）'
            shared_overlaps = [item for item in candidates if _overlap(row, item, definition, include_categories=False)]
            if shared_overlaps:
                shared_generated = set().union(*(item.get('_applicable_fields', set()) for item in shared_overlaps))
                displaced = shared_generated & SHARED_FIELDS.get(key, set())
                applicable -= displaced
                if displaced:
                    row['source_label'] = '人工补充（门店月度共享实绩采用业务来源）'
        if row['entry_mode'] == 'final':
            row['source_label'] = '内勤最终月值'
            applicable -= numeric_keys - final_fields(row)
        row['_applicable_fields'] = applicable
        # Removed values are visible in original manual details, but must not masquerade
        # as currently selected report facts or be included in CSV detail totals.
        for field in value_columns:
            if field['key'] not in applicable and field['type'] not in {'text', 'date'}:
                row[field['key']] = None
        prepared.append(row)
    rows = (prepared if source_mode == 'manual' else generated if source_mode == 'generated'
            else generated + prepared)
    if not is_manual and key != 'profit' and source_mode == 'manual':
        rows = []
    if not can_view_sensitive_reports(user):
        for row in rows + legacy:
            row['note'] = ''
    if snapshot_sources:
        return {'rows': [{**row, '_applicable_fields': sorted(row.get('_applicable_fields', row))}
                         for row in rows], 'legacy_rows': legacy, 'updated_at': max(updated, default=None)}
    result = project(definition, rows, group_by=group_by, metric=metric if separator else definition['default_metric'],
        updated_at=max(updated, default=None), category_field=category_field, category_value=category_value,
        source_mode=source_mode, legacy_rows=legacy)
    return fill_month_window(result, date_from, date_to) if group_by == 'month' else result
