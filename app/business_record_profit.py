"""Frozen customer-sheet profit formulas; exact fen, no invented component rates."""
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from .db import get_db
from .security import get_user
from .business_records_schemas import Strict

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


def apply_office_profit(db, contract, data, *, require_materials=True):
    """Override only computed facts. Every net component remains clerk supplied."""
    from .business_record_pricing_models import RecordContractTerms
    from .business_record_delivery import require_office_materials
    from .business_record_reports import validate_manual_values
    values = dict(data.get('values', {}))
    terms = db.scalar(select(RecordContractTerms).where(RecordContractTerms.contract_id == contract.id))
    gift_cost = terms.gift_total_cents if terms is not None else contract.gift_cost_cents
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
    result = calculate_profit(data['report_key'], values)
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
    return {key: result[key] for key in ('profit_cents', 'gift_cost_cents', 'profit_calculation', 'values')}
