"""Deterministic, suggestion-only gift sheet reader. It never calls a model."""
import csv
import io
import json
import re
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException

HEADERS = {
    'name': {'赠品名称', '精品名称', '商品名称', '物料名称', '项目名称', '名称', '品名', '项目', 'name'},
    'unit_cost_cents': {'成本', '成本价', '赠品成本', '采购价', '采购成本', '结算价', '结算单价', '成本单价', '进价', 'unit_cost'},
    'unit_price_cents': {'售价', '销售价', '销售单价', '零售价', '零售价格', '赠品售价', 'unit_price'},
    'brand': {'品牌', '品牌名称', 'brand'},
    'unit': {'单位', '计量单位', 'unit'},
    'applicable_models': {'适用车型', '车型', '车型范围', 'applicable_models'},
    'source_ref': {'来源', '来源位置', 'source_ref'},
    'note': {'说明', '备注', 'note'},
}


def canonical_brand(value):
    value = str(value or '').strip()
    return {'启源': '长安启源', '长安凯程': '凯程', '深蓝': '深蓝汽车', 'BYD': '比亚迪'}.get(value, value)


def _header(value):
    return re.sub(r'[\s()（）]', '', str(value or '')).removesuffix('人民币元').removesuffix('元').lower()


def _money(value, location):
    text = str(value or '').strip()
    if not text:
        return None
    try:
        number = Decimal(text.replace(',', ''))
        if not number.is_finite() or not 0 <= number <= Decimal('9999999999.99') or number * 100 != (number * 100).to_integral_value():
            raise ValueError()
        return int(number * 100)
    except (InvalidOperation, ValueError):
        raise HTTPException(422, location + '须为精确到分的非负金额，未知请留空') from None


def preview_gift_file(content, media, brand):
    from .business_record_pricing_recognition import XLSX, spreadsheet_source
    if media == XLSX:
        sheets = []
        for sheet in json.loads(spreadsheet_source(content)):
            lines = []
            for row in sheet['rows']:
                values = {re.sub(r'\d', '', cell['cell']): cell['value'] for cell in row['cells']}
                lines.append((row['row'], values))
            sheets.append((sheet['sheet'], lines))
    elif media.startswith('text/csv'):
        try:
            parsed = list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))
        except (UnicodeError, csv.Error):
            raise HTTPException(422, '请使用UTF-8 CSV赠品表') from None
        if len(parsed) > 2500 or any(len(row) > 100 for row in parsed):
            raise HTTPException(422, '赠品表不得超过2500行、100列')
        sheets = [('CSV', [(i + 1, {str(k): v for k, v in enumerate(row)}) for i, row in enumerate(parsed)])]
    else:
        raise HTTPException(422, '赠品成本请使用普通xlsx或UTF-8 CSV；复杂合并表及xls请先整理为分品牌标准表')
    rows, warnings, row_errors = [], [], []
    for sheet, lines in sheets:
        columns, labels = None, {}
        for number, values in lines:
            found, ambiguous = {}, set()
            for column, value in values.items():
                matched = next((key for key, labels in HEADERS.items() if _header(value) in labels), None)
                if matched:
                    if matched in found:
                        ambiguous.add(matched)
                    found[matched] = column
            nonempty = [value for value in values.values() if str(value).strip()]
            if 'name' in found and (len(found) >= 2 or len(nonempty) == 1):
                columns = {key: column for key, column in found.items() if key not in ambiguous}
                labels = dict(values)
                # Keep duplicate candidates visible without choosing a column.
                if ambiguous:
                    warnings.append(f'{sheet}第{number}行有重复表头，相关列留空；请对照各行原文核定。')
                continue
            if not nonempty:
                continue
            if columns is None:
                rows.append({'name': '', 'brand': brand, 'unit_cost_cents': None, 'unit_price_cents': None,
                    'source': f'{sheet}:{number}', 'source_ref': f'{sheet}:{number}',
                    'source_text': ' | '.join(f'{column}: {value}' for column, value in values.items())})
                row_errors.append({'row': len(rows), 'source': rows[-1]['source'], 'errors': ['未匹配表头，请人工填写或移除说明行']})
                continue
            name = str(values.get(columns.get('name'), '')).strip()
            problems, raw_values = [], {}
            if not name:
                problems.append('缺少赠品名称，请补填或移除说明行')
            item = {key: str(values.get(column, '')).strip() for key, column in columns.items()}
            item['name'] = name
            for key in ('unit_cost_cents', 'unit_price_cents'):
                original = item.get(key)
                try:
                    item[key] = _money(original, f'{sheet}第{number}行')
                except HTTPException:
                    item[key] = None
                    raw_values[key] = original
                    problems.append(('成本' if key == 'unit_cost_cents' else '售价') + '需人工核对，原值已保留')
            item['brand'] = item.get('brand') or brand
            item['source_ref'] = item.get('source_ref') or f'{sheet}:{number}'
            item['source'] = f'{sheet}:{number}'
            if raw_values:
                item['raw_values'] = raw_values
            item['source_text'] = ' | '.join(f'{labels.get(column, column)}: {value}' for column, value in values.items())
            if any(column not in columns.values() and str(value).strip() for column, value in values.items()):
                problems.append('未映射列已保留原文，请核对条件和金额')
            if problems:
                row_errors.append({'row': len(rows) + 1, 'source': item['source'], 'errors': problems})
            rows.append(item)
        if columns is None:
            warnings.append(sheet + '未找到明确表头，原文已放入核对行；请补填项目或移除说明行。')
    if len(rows) > 2000:
        raise HTTPException(422, '识别候选超过2000行，请分批核对上传')
    if not rows:
        rows = [{'name': '', 'brand': brand}]
        warnings.append('原表没有可填项目，请手工补充。')
    return {'rows': rows, 'warnings': ['成本与售价分别保留；识别只作建议，格式问题请在此修正。'] + warnings,
            'row_errors': row_errors, 'recognition_complete': not row_errors and not warnings,
            'requires_confirmation': True, 'notice': '本地表格解析结果；请核对品牌、来源和全部项目后确认。'}
