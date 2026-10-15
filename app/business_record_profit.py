"""Frozen customer-sheet profit formulas; exact fen, no invented component rates."""
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from .db import get_db
from .security import get_user
from .business_records_schemas import Strict, OfficeExtensionFacts

router = APIRouter(prefix='/api/business-records', tags=['单车大毛利'])
# Source: customer workbook 9.30(1), ordinary AS, hail AQ, secondary AN, Sheet2 AO.
FORMULAS = {
    'vehicle_details': ('W-K+U+V+Z+AA+AF+AH+AJ+AL-AM-AN-AP+AQ-AB+AK+AR', 'AS', 'AM'),
    'hail_vehicle_details': ('V-K+T+U-X+Y+Z+AE+AG+AI+AK-AL-AM-AO+AP-AA+AJ', 'AQ', 'AL'),
    'secondary_vehicle_details': ('U-I+S+T-W+X+Y+AC+AE+AG+AH-AI-AJ+AM-AL', 'AN', 'AI'),
    'vehicle_details_sheet2': ('V-I+T+U-X+Y+Z+AD+AF+AH+AI-AJ-AK-AM+AN', 'AO', 'AJ'),
}


def column_key(letter):
    number = 0
    for char in letter:
        number = number * 26 + ord(char) - 64
    return 'c' + str(number).zfill(2)


def calculate_profit(report_key, values):
    import re
    from .business_record_reports import CATALOG_BY_KEY
    if report_key not in FORMULAS:
        raise ValueError('请选择已登记原公式的车辆明细表')
    expression, output, gift = FORMULAS[report_key]
    columns = {column['key']: column for column in CATALOG_BY_KEY[report_key]['columns']}
    items, subtotal, missing = [], 0, []
    for operator, letter in re.findall(r'([+-]?)([A-Z]+)', expression):
        key, sign = column_key(letter), -1 if operator == '-' else 1
        value, cents = values.get(key), None
        if value not in (None, ''):
            try:
                number = Decimal(str(value))
                if not number.is_finite() or number != number.quantize(Decimal('.01')):
                    raise ValueError
                cents = int(number * 100)
                if abs(cents) > 999999999999:
                    raise ValueError
            except (InvalidOperation, ValueError, TypeError):
                raise ValueError(columns[key]['label'] + '须为精确到分的金额') from None
            subtotal += sign * cents
        else:
            missing.append({'key': key, 'label': columns[key]['label']})
        items.append({'key': key, 'source_column': letter, 'label': columns[key]['label'],
                      'sign': sign, 'amount_cents': cents})
    if abs(subtotal) > 999999999999:
        raise ValueError('汇总利润超出可记录金额范围')
    return {'formula_version': 'customer-sheets-v210', 'report_key': report_key,
            'label': '核定单车大毛利', 'formula': expression, 'output_key': column_key(output),
            'status': 'incomplete' if missing else 'complete', 'items': items, 'missing': missing,
            'known_subtotal_cents': subtotal, 'total_cents': None if missing else subtotal}


def accessory_sales_profit(extension):
    """Only explicitly checked amounts form the boutique sales margin."""
    income = extension.get('accessory_sales_income_cents')
    cost = extension.get('accessory_sales_cost_cents')
    return None if income is None or cost is None else income - cost


def include_accessory_sales(base, extension):
    # The original formula already includes film-shop commission. Keep its
    # operands frozen and append only the separately checked boutique margin.
    result = dict(base)
    items, missing = list(base['items']), list(base['missing'])
    subtotal = base['known_subtotal_cents']
    for key, label, sign in (
            ('accessory_sales_income_cents', '店内精品销售收入', 1),
            ('accessory_sales_cost_cents', '店内精品销售成本', -1)):
        amount = extension.get(key)
        items.append({'key': key, 'source_column': '', 'source_label': '内勤核对精品销售',
                      'label': label, 'sign': sign, 'amount_cents': amount})
        if amount is None:
            missing.append({'key': key, 'label': label})
        else:
            subtotal += sign * amount
    if abs(subtotal) > 999999999999:
        raise ValueError('汇总利润超出可记录金额范围')
    result.update(formula_version='customer-sheets-v217-accessory-sales',
        base_formula_version=base['formula_version'], base_total_cents=base['total_cents'],
        accessory_sales_profit_cents=accessory_sales_profit(extension),
        items=items, missing=missing, known_subtotal_cents=subtotal,
        status='incomplete' if missing else 'complete', total_cents=None if missing else subtotal)
    return result


def apply_office_profit(db, contract, data, *, require_materials=True):
    """Override only computed facts. Every net component remains clerk supplied."""
    from .business_record_delivery import require_office_materials
    from .business_record_reports import validate_manual_values
    values = dict(data.get('values', {}))
    from .business_record_accessories import effective_terms
    terms = effective_terms(db, contract)
    from .business_record_pricing import frozen_gift_cost
    gift_cost = frozen_gift_cost(terms) if terms is not None else contract.gift_cost_cents
    gift_key = column_key(FORMULAS[data['report_key']][2])
    values[gift_key] = None if gift_cost is None else format(Decimal(gift_cost) / 100, '.2f')
    if require_materials:
        delivery = require_office_materials(db, contract)
        data['period'] = str(delivery.accounting_on)
        data['invoice_amount_cents'] = delivery.invoice_amount_cents
        data['invoice_file_id'] = delivery.invoice_file_id
        from .business_record_delivery_models import RecordGiftDocument
        data['gift_document_id'] = db.scalar(select(RecordGiftDocument.id).where(
            RecordGiftDocument.contract_id == contract.id).order_by(RecordGiftDocument.id.desc()).limit(1))
    values = validate_manual_values(data['report_key'], values)
    from .business_record_accessories import apply_accessory_verification
    data = apply_accessory_verification(db, contract, data, terms)
    result = include_accessory_sales(calculate_profit(data['report_key'], values), data.get('extension_data') or {})
    result['formula_version'] = 'customer-sheets-v219-actual-paid-accessory-cost'
    amount = result['total_cents']
    values[result['output_key']] = None if amount is None else format(Decimal(amount) / 100, '.2f')
    # Original first profit column is a duplicate result, never another operand.
    if data['report_key'] in {'vehicle_details', 'hail_vehicle_details'}:
        values['c06'] = values[result['output_key']]
    data.update(values=values, profit_cents=amount, gift_cost_cents=gift_cost, profit_calculation=result)
    return data


class ProfitPreview(Strict):
    report_key: str = Field(max_length=80)
    values: dict = Field(default_factory=dict, max_length=150)
    extension_data: OfficeExtensionFacts = Field(default_factory=OfficeExtensionFacts)


@router.post('/contracts/{key}/profit-preview')
def preview_profit(key: int, body: ProfitPreview, db=Depends(get_db), user=Depends(get_user)):
    from .business_records import get_contract
    from .business_record_report_specs import can_view_sensitive_reports
    if not can_view_sensitive_reports(user):
        raise HTTPException(403, '当前岗位不可查看单车成本利润')
    contract = get_contract(db, user, key)
    if body.report_key not in FORMULAS:
        raise HTTPException(422, '请选择已登记原公式的车辆明细表')
    try:
        result = apply_office_profit(db, contract, body.model_dump(), require_materials=False)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return {key: result[key] for key in ('profit_cents', 'gift_cost_cents', 'profit_calculation', 'values',
                                        'extension_data', 'accessory_sales_verification')}
