"""Explicit statistical meanings of V2 source columns (stable cNN keys).

There are deliberately no spreadsheet formulas or inventory transactions here.
Only ratios with known operands are recomputed; other rates remain unaggregated.
"""

DETAIL_REPORTS = frozenset({'vehicle_details', 'hail_vehicle_details',
    'secondary_vehicle_details', 'vehicle_details_sheet2', 'accessory_details'})
VEHICLE_REPORTS = frozenset(DETAIL_REPORTS - {'accessory_details'})
CONTRACT_REPORTS = frozenset(VEHICLE_REPORTS | {'sales_targets', 'sales_overview',
    'sales_profit_statement', 'secondary_profit_statement', 'individual_profit',
    'model_profit', 'model_profit_sheet5', 'bank_finance', 'insurance_resources',
    'insurance_settlement', 'extended_warranty'})
AFTER_SALES_REPORTS = frozenset({'after_sales_monthly', 'after_sales_targets', 'sales_targets'})

# Numerator and denominator are field keys, never inferred from label fragments.
# A third item of 100 denotes a percentage; 1 denotes a unit price.
RATIOS = {
    'sales_targets': {'c10': ('c06', 'c02', 100), 'c11': ('c09', 'c05', 100)},
    'trade_in': {'c05': ('c03', 'c02', 100), 'c06': (('c03', 'c04'), 'c02', 100),
                 'c12': ('c08', 'c07', 100)},
    'extended_warranty': {'c05': ('c04', 'c02', 100)},
    'small_products': {'c06': ('c05', 'c03', 100)},
    'after_sales_monthly': {'c04': ('c03', 'c02', 100), 'c06': ('c05', 'c03', 100),
        'c08': ('c07', 'c03', 100), 'c11': ('c10', 'c09', 100),
        'c13': ('c12', 'c03', 100), 'c15': ('c14', 'c03', 100)},
    'after_sales_targets': {'c06': ('c05', 'c01', 100), 'c07': ('c05', 'c04', 1),
        'c10': ('c09', 'c02', 100), 'c11': ('c09', 'c08', 1),
        'c13': ('c12', 'c08', 1), 'c15': ('c12', 'c14', 100),
        'c17': ('c16', 'c03', 100), 'c21': ('c16', 'c20', 1),
        'c23': ('c09', 'c22', 1)},
    'sales_overview': {'c05': ('c04', 'c02', 100)},
    'bank_finance': {'c09': ('c04', 'c07', 100), 'c10': ('c13', ('c07', 'c08'), 100)},
    'insurance_settlement': {'c07': ('c03', 'c04', 100), 'c08': ('c03', 'c06', 100)},
    'insurance_resources': {'c06': ('c03', 'c04', 100), 'c08': ('c07', 'c04', 100)},
    'marketing': {'c10': ('c15', 'c05', 100), 'c11': ('c16', 'c06', 100),
        'c12': ('c17', 'c07', 100), 'c13': ('c18', 'c08', 100),
        'c14': ('c19', 'c09', 100)},
    'insurance_renewal': {'c08': ('c07', 'c06', 100)},
    'sales_profit_statement': {'c05': ('c02', 'c01', 1), 'c08': ('c07', 'c03', 100)},
    'secondary_profit_statement': {'c05': ('c02', 'c01', 1), 'c08': ('c07', 'c03', 100)},
    'individual_profit': {'c05': ('c04', 'c03', 100), 'c06': ('c07', 'c04', 1)},
    'model_profit': {'c05': ('c04', 'c03', 1)},
    'model_profit_sheet5': {'c04': ('c03', 'c02', 1)},
}

# Same-value standards are meaningful, adding them is not.
NON_ADDITIVE = {
    'vehicle_details': {'c01', 'c09', 'c17', 'c31'},
    'hail_vehicle_details': {'c01', 'c09', 'c16', 'c30'},
    'secondary_vehicle_details': {'c01', 'c07', 'c16', 'c28'},
    'vehicle_details_sheet2': {'c01', 'c07', 'c16', 'c29'},
    'accessory_details': {'c04'},
    'vehicle_policy': set('c%02d' % n for n in range(3, 17)),
    'vehicle_policy_reference': set('c%02d' % n for n in range(3, 8)),
    'bank_commission': {'c02', 'c03', 'c04'},
    'marketing': {'c21', 'c22', 'c23'},
}
STOCK_FIELDS = {'sales_overview': {'c06', 'c07', 'c08', 'c09', 'c10'},
                'after_sales_monthly': {'c09', 'c10'}}
# Original merged cells are repeated only for entering institution rows. Their
# values describe one store/brand/month, not a separate sale per institution.
SHARED_FIELDS = {'bank_finance': {'c07', 'c08', 'c11', 'c12', 'c13', 'c14'},
                 'insurance_resources': {'c03', 'c04', 'c05', 'c07'},
                 'insurance_renewal': {'c06', 'c07', 'c09'}}
GROUPING_FIELDS = {
    'sales_targets': ['c01'], 'trade_in': ['c01'], 'extended_warranty': ['c01'],
    'small_products': ['c01', 'c02'], 'after_sales_monthly': ['c01'],
    'after_sales_targets': [], 'bank_finance': ['c01', 'c02'],
    'insurance_settlement': ['c01', 'c02'], 'sales_overview': ['c01'],
    'insurance_resources': ['c01'], 'marketing': [], 'insurance_renewal': ['c01'],
    'vehicle_details': ['c03', 'c04', 'c18', 'c29'],
    'hail_vehicle_details': ['c03', 'c04', 'c17', 'c28'],
    'secondary_vehicle_details': ['c03', 'c04', 'c17', 'c26'],
    'vehicle_details_sheet2': ['c03', 'c04', 'c17', 'c27'],
    'accessory_details': ['c01', 'c02', 'c03'],
    'sales_profit_statement': ['c11', 'c06', 'c09'],
    'secondary_profit_statement': ['c11', 'c06', 'c09'],
    'vehicle_policy': ['c01', 'c02'], 'vehicle_policy_reference': ['c01', 'c02'],
    'individual_profit': ['c01', 'c02'], 'model_profit': ['c01', 'c02'],
    'model_profit_sheet5': ['c01'], 'bank_commission': ['c01'],
}
DEFAULTS = {'sales_targets': 'c06', 'trade_in': 'c13', 'extended_warranty': 'c04', 'small_products': 'c05',
    'after_sales_monthly': 'c03', 'after_sales_targets': 'c16', 'bank_finance': 'c05',
    'insurance_settlement': 'c03', 'sales_overview': 'c04', 'insurance_resources': 'c13',
    'marketing': 'c19', 'insurance_renewal': 'c09', 'hail_vehicle_details': 'c43',
    'secondary_vehicle_details': 'c40', 'vehicle_details_sheet2': 'c41',
    'model_profit': 'c04', 'model_profit_sheet5': 'c03', 'vehicle_policy': 'c16',
    'vehicle_policy_reference': 'c04', 'bank_commission': 'c04'}


def configure_catalog(catalog):
    for report in catalog:
        key = report['key']
        if key == 'after_sales_revenue':
            for metric, label, kind, unit, precision in (
                ('materials', '材料费', 'money', '元', 2), ('labor', '工时费', 'money', '元', 2),
                ('cost', '核定成本', 'money', '元', 2), ('profit', '核定毛利', 'money', '元', 2),
                ('count', '售后记录数', 'count', '笔', 0)):
                report['metrics'].append({'key': metric, 'label': label, 'type': kind,
                                          'unit': unit, 'precision': precision})
            report['grouping_fields'] = [{'key': 'service_type', 'label': '服务类别', 'type': 'text'}]
        if report['source'] != 'manual':
            continue
        # Derived unit prices retain the precision visible in the source sheets.
        unit_price_keys = {field for field, rule in RATIOS.get(key, {}).items() if rule[2] == 1}
        for column in report['columns']:
            if column['key'] in unit_price_keys:
                column['type'], column['precision'] = 'decimal', 6
        report['metrics'] = [dict(c) for c in report['columns'] if c['type'] not in {'text', 'date'}]
        report['default_metric'] = DEFAULTS.get(key, report['default_metric'])
        report['aggregation'] = 'explicit_statistical_rules'
        report['entry_modes'] = ['detail', 'snapshot']
        report['supports_contract'] = key in VEHICLE_REPORTS
        report['default_entry_mode'] = 'detail' if key in DETAIL_REPORTS else 'snapshot'
        report['grouping_fields'] = [dict(c) for c in report['columns']
                                     if c['key'] in GROUPING_FIELDS.get(key, [])]
        report['automatic_source'] = ('contracts_and_after_sales' if key in CONTRACT_REPORTS & AFTER_SALES_REPORTS
            else 'contracts' if key in CONTRACT_REPORTS else 'after_sales' if key in AFTER_SALES_REPORTS else None)
        rules = {}
        for field in report['metrics']:
            name = field['key']
            if name in RATIOS.get(key, {}):
                numerator, denominator, scale = RATIOS[key][name]
                rules[name] = {'kind': 'ratio', 'numerator': numerator, 'denominator': denominator, 'scale': scale}
            elif name in STOCK_FIELDS.get(key, set()):
                rules[name] = {'kind': 'closing_snapshot'}
            elif name in SHARED_FIELDS.get(key, set()):
                rules[name] = {'kind': 'shared_scope', 'scope': ['store_id', 'brand', 'month']}
            elif key == 'sales_overview' and name == 'c03':
                rules[name] = {'kind': 'last_day_sum'}
            elif field['type'] == 'percent' or name in NON_ADDITIVE.get(key, set()):
                rules[name] = {'kind': 'non_additive'}
            else:
                rules[name] = {'kind': 'sum'}
        report['aggregation_rules'] = rules
        if key in SHARED_FIELDS:
            names = [column['label'] for column in report['columns'] if column['key'] in SHARED_FIELDS[key]]
            report['input_notice'] = ('、'.join(names) + '是门店、品牌、月份的共享数据；同范围在多个机构行重复填写时须一致，仅计一次；冲突留空并提示核对。')
        report['period_basis'] = ('实际到账日期（销售实绩）；人工统计日期（目标和补充）'
            if key in CONTRACT_REPORTS - VEHICLE_REPORTS else
            '合同日期（已核价车辆事实，不计作到账业绩）' if key in VEHICLE_REPORTS else
            '售后业务日期及人工统计日期' if key in AFTER_SALES_REPORTS else '人工填报的统计日期')


# Fields generated from business facts. Other fields remain clerk-confirmed.
GENERATED_FIELDS = {
    'bank_finance': {'c04', 'c05', 'c06'},
    'insurance_resources': {'c02', 'c03'},
    'insurance_settlement': {'c04'},
    'extended_warranty': {'c02', 'c04', 'c05'},
    'sales_targets': {'c06', 'c07', 'c08', 'c09', 'c10', 'c11'},
    'sales_overview': {'c04', 'c05'},
    'sales_profit_statement': {'c01', 'c02', 'c03', 'c04', 'c05'},
    'secondary_profit_statement': {'c01', 'c02', 'c03', 'c04', 'c05'},
    'individual_profit': {'c04', 'c05', 'c06', 'c07', 'c08', 'c09'},
    'model_profit': {'c03', 'c04', 'c05', 'c06'},
    'model_profit_sheet5': {'c02', 'c03', 'c04', 'c05'},
    'after_sales_monthly': {'c03', 'c04', 'c12', 'c13', 'c14', 'c15'},
    'after_sales_targets': {'c04', 'c05', 'c06', 'c07', 'c08', 'c09', 'c10', 'c11',
        'c12', 'c13', 'c15', 'c16', 'c17', 'c18', 'c21', 'c23'},
}
