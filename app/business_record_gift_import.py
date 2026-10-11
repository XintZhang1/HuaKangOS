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
    rows, warnings = [], []
    for sheet, lines in sheets:
        columns = None
        for number, values in lines:
            found = {}
            for column, value in values.items():
                matched = next((key for key, labels in HEADERS.items() if _header(value) in labels), None)
                if matched:
                    if matched in found:
                        raise HTTPException(422, f'{sheet}第{number}行存在多个{value}列，请先整理明确口径')
                    found[matched] = column
            if 'name' in found and {'unit_cost_cents', 'unit_price_cents'} & found.keys():
                columns = found
                continue
            if columns is None or not any(str(v).strip() for v in values.values()):
                continue
            name = str(values.get(columns['name'], '')).strip()
            if not name:
                raise HTTPException(422, f'{sheet}第{number}行缺少赠品名称，请核对原表')
            item = {key: str(values.get(column, '')).strip() for key, column in columns.items()}
            for key in ('unit_cost_cents', 'unit_price_cents'):
                item[key] = _money(item.get(key), f'{sheet}第{number}行')
            item['brand'] = item.get('brand') or brand
            item['source_ref'] = item.get('source_ref') or f'{sheet}:{number}'
            item['source'] = f'{sheet}:{number}'
            rows.append(item)
        if columns is None:
            warnings.append(sheet + '未找到明确的名称和成本/售价表头，未导入该表')
    if not rows or len(rows) > 2000:
        raise HTTPException(422, '未找到完整赠品目录，或超过2000项；请使用名称、成本（元）、售价（元）、品牌、单位、适用车型列的标准表')
    if warnings:
        # Partial workbook recognition must never look like a full publication.
        raise HTTPException(422, '；'.join(warnings) + '。请拆分品牌并移除非目录表后重新上传')
    return {'rows': rows, 'warnings': ['成本与售价分别保留；空白价格表示待补齐，不自动相互复制。'],
            'requires_confirmation': True, 'notice': '本地表格解析结果；请核对品牌、来源和全部项目后确认。'}
