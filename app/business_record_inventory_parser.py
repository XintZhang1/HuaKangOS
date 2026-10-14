"""Bounded XLSX values only: mappings are reviewed before any publication."""
import io
import posixpath
import re
import zipfile
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET
from fastapi import HTTPException

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
TAG = '{' + NS['s'] + '}'
VIN = re.compile(r'^[A-HJ-NPR-Z0-9]{17}$')
HEADERS = {
    'vin': {'VIN', '车架号', '车辆识别号', '车辆识别代号'},
    'model': {'车型名称', '车型', '车系'},
    'configuration': {'配置', '配置名称', '配置及外观和内饰颜色'},
    'exterior_color': {'外观颜色', '车身颜色', '颜色', '外饰颜色'},
    'interior_color': {'内饰颜色', '内饰'},
    'guide_price': {'销售标准价', '指导价', '市场指导价', '市场指导价元', '建议零售价'},
    'production_on': {'生产日期', '出厂日期'},
    'owner': {'所属店', '所属门店'},
    'location': {'存放点', '位置', '存放地', '所在地'},
    'funding': {'监管银行', '资金性质', '库存资金性质', '合格证', '备注1'},
}


def _header(value):
    return re.sub(r'[\s（）()]', '', str(value)).upper()


def read_inventory_workbook(content):
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, '库存文件不能为空且不得超过10MB')
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist(); names = {i.filename for i in infos}
            if len(infos) != len(names) or len(infos) > 1500 or sum(i.file_size for i in infos) > 128 * 1024 * 1024:
                raise ValueError()
            for item in infos:
                name = item.filename.lower()
                if '..' in name.split('/') or name.startswith('/') or '\\' in name or item.flag_bits & 1:
                    raise ValueError()
                # Some ordinary dealer sheets carry embedded document icons.
                # They are opaque attachments: never extracted or executed by
                # this value-only reader; the whole original still goes through
                # the configured file scanner before preview/publication.
                inert_embedding = name.startswith('xl/embeddings/')
                if any(v in name for v in ('vba', 'activex/', 'externallinks/')) or name.endswith('.bin') and not inert_embedding:
                    raise ValueError()
                if item.file_size > 64 * 1024 * 1024 or item.file_size > max(100000, 250 * item.compress_size):
                    raise ValueError()
                if name.endswith(('.xml', '.rels')):
                    raw = archive.read(item)
                    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper() or re.search(br'TargetMode\s*=\s*[\"\x27]External', raw, re.I):
                        raise ValueError()
            shared = []
            if 'xl/sharedStrings.xml' in names:
                shared = [''.join(n.itertext()) for n in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
            links = {n.attrib['Id']: n.attrib['Target'] for n in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
            book = ET.fromstring(archive.read('xl/workbook.xml'))
            date1904 = book.find('s:workbookPr', NS)
            date1904 = date1904 is not None and date1904.get('date1904') in {'1', 'true'}
            result = []
            for sheet in book.findall('s:sheets/s:sheet', NS):
                if sheet.get('state', 'visible') != 'visible':
                    continue
                target = links[sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
                path = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('xl', target))
                if not path.startswith('xl/'):
                    raise ValueError()
                rows, hidden_columns, merges = [], [], []
                # Real sheets may have a million formatted empty rows. Iterparse
                # clears them, and limits apply to actual values, not dimensions.
                for _, node in ET.iterparse(io.BytesIO(archive.read(path)), events=('end',)):
                    if node.tag == TAG + 'col' and node.get('hidden') in {'1', 'true'}:
                        hidden_columns.append([int(node.get('min')), int(node.get('max'))])
                    elif node.tag == TAG + 'mergeCell':
                        merges.append(node.get('ref'))
                    elif node.tag == TAG + 'row':
                        values = {}
                        for cell in node.findall('s:c', NS):
                            value = cell.findtext('s:v', '', NS)
                            if cell.get('t') == 's':
                                value = shared[int(value)]
                            elif cell.get('t') == 'inlineStr':
                                value = ''.join(cell.find('s:is', NS).itertext())
                            if value:
                                if len(value) > 8000:
                                    raise ValueError()
                                values[re.sub(r'\d', '', cell.get('r'))] = value.strip()
                        if values:
                            rows.append({'row': int(node.get('r')), 'values': values,
                                         'hidden': node.get('hidden') in {'1', 'true'}})
                            if len(rows) > 10020:
                                raise ValueError()
                        node.clear()
                result.append({'name': sheet.get('name'), 'rows': rows, 'merges': merges,
                               'hidden_columns': hidden_columns, 'date1904': date1904,
                               'auxiliary': bool(re.search(r'180|汇总|统计', sheet.get('name', '')))})
            if not result:
                raise ValueError()
            return result
    except (ValueError, KeyError, IndexError, AttributeError, OSError, ET.ParseError, zipfile.BadZipFile):
        raise HTTPException(422, '库存Excel结构无效、含外部链接或超过安全读取范围；请使用普通xlsx（最多10000条明细）') from None


def sheet_proposals(sheets):
    result = []
    for sheet in sheets:
        best = (0, 0, {})
        for row in sheet['rows']:
            if row['row'] > 20:
                break
            mapping = {}
            for col, value in row['values'].items():
                for key, aliases in HEADERS.items():
                    if _header(value) in {_header(alias) for alias in aliases}:
                        mapping[key] = col
            if len(mapping) > best[0]:
                best = (len(mapping), row['row'], mapping)
        header = next((r['values'] for r in sheet['rows'] if r['row'] == best[1]), {})
        result.append({'sheet': sheet['name'], 'header_row': best[1], 'columns': best[2],
                       'headers': header, 'auxiliary': sheet['auxiliary'],
                       'hidden_columns': sheet['hidden_columns'],
                       'configuration_contains_colors': header.get(best[2].get('configuration')) == '配置及外观和内饰颜色',
                       'notice': '辅助统计表不参与当前库存发布' if sheet['auxiliary'] else ''})
    return result


def _date(value, date1904=False):
    value = str(value or '').strip()
    if not value:
        return None
    try:
        if re.fullmatch(r'\d+(?:\.0+)?', value):
            serial = int(Decimal(value))
            if not 1 <= serial <= 100000:
                return None
            return (date(1904, 1, 1) if date1904 else date(1899, 12, 30)) + timedelta(days=serial)
        return date.fromisoformat(value.replace('/', '-').replace('.', '-'))
    except (ValueError, OverflowError, InvalidOperation):
        return None


def _money(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        number = Decimal(str(value).replace(',', '').strip())
        if not number.is_finite() or number <= 0 or number > Decimal('9999999999.99') or number * 100 != (number * 100).to_integral_value():
            return None
        return int(number * 100)
    except InvalidOperation:
        return None


def mapped_preview(sheets, mapping):
    sheet = next((s for s in sheets if s['name'] == mapping.sheet), None)
    if sheet is None or sheet['auxiliary']:
        raise HTTPException(422, '请选择原始车辆明细工作表，180天及汇总辅助表不参与发布')
    columns = mapping.columns
    if set(columns) - set(HEADERS) or any(not re.fullmatch(r'[A-Z]{1,3}', v) for v in columns.values()):
        raise HTTPException(422, '请使用预览中的库存字段与Excel列映射')
    if not all(columns.get(k) for k in ('vin', 'model', 'configuration')):
        raise HTTPException(422, '请明确VIN、车型和配置来源列')
    overrides = {r.source_row: r for r in mapping.overrides}
    rows, pending, excluded, errors, owners, funds = [], [], [], [], set(), set()
    seen = set()
    for source in sheet['rows']:
        if source['row'] <= mapping.header_row:
            continue
        values = source['values']
        get = lambda key: values.get(columns.get(key, ''), '').strip()
        raw_vin = get('vin').upper()
        # Totals and section headings are not vehicles. A nonempty malformed
        # identifier is reported rather than discarded as a non-vehicle row.
        if not raw_vin:
            continue
        if raw_vin in {'VIN', '车架号', '车辆识别号', '合计', '总计'}:
            continue
        owner, fund = get('owner'), get('funding')
        owners.add(owner); funds.add(fund)
        if not VIN.fullmatch(raw_vin):
            errors.append({'source_row': source['row'], 'message': 'VIN须为17位字母数字，不含I/O/Q；请修正原表'})
            continue
        if owner not in mapping.source_owners:
            excluded.append({'source_row': source['row'], 'vin': raw_vin, 'reason': '未选择该来源所属店'})
            continue
        if raw_vin in seen:
            errors.append({'source_row': source['row'], 'message': '同一VIN重复，请核对原表后重新上传'})
            continue
        seen.add(raw_vin)
        override = overrides.get(source['row'])
        production = override.production_on if override and override.production_on else _date(get('production_on'), sheet['date1904'])
        age = (mapping.as_of_date - production).days if production else None
        if age is not None and age >= 0 and age > 180:
            excluded.append({'source_row': source['row'], 'vin': raw_vin, 'reason': '生产日期理论库龄超过180天', 'age_days': age})
            continue
        issues = []
        config, exterior, interior, extra = get('configuration'), get('exterior_color'), get('interior_color'), ''
        if mapping.configuration_contains_colors:
            parts = config.split('_')
            if len(parts) >= 3:
                config, parsed_exterior, parsed_interior = parts[:3]
                extra = '_'.join(parts[3:])
                if exterior and exterior != parsed_exterior:
                    issues.append('配置文本外观色与独立列不同，请核对')
                else:
                    exterior = parsed_exterior
                if interior and interior != parsed_interior:
                    issues.append('配置文本内饰色与独立列不同，请核对')
                else:
                    interior = parsed_interior
            else:
                issues.append('配置文本未提供完整内外饰颜色，请核对补齐')
        if override:
            if override.exterior_color is not None:
                exterior = override.exterior_color
            if override.interior_color is not None:
                interior = override.interior_color
            if exterior and interior:
                issues = [v for v in issues if '颜色' not in v and '色' not in v]
        if not exterior:
            issues.append('外观颜色待补齐')
        if not interior:
            issues.append('内饰颜色待补齐')
        if not get('model') or not config:
            errors.append({'source_row': source['row'], 'message': '车型或配置为空，请修正原表'})
        if production is None or age is not None and age < 0:
            issues.append('生产日期未核对，本行不发布；补齐后重新预览库龄')
        guide = _money(get('guide_price'))
        if guide is None:
            issues.append('标准价待核对')
        funding_kind = mapping.funding_map.get(fund, 'unknown')
        if funding_kind == 'unknown':
            issues.append('库存资金性质待核对')
        if source['hidden']:
            issues.append('原表隐藏行，发布前请核对')
        item = {'source_row': source['row'], 'vin': raw_vin, 'model': get('model'),
                'configuration': config, 'exterior_color': exterior, 'interior_color': interior,
                'extra_configuration': extra, 'guide_price_cents': guide,
                'production_on': production.isoformat() if production else None, 'age_days': age,
                'funding_kind': funding_kind, 'funding_source': fund, 'source_owner': owner,
                'location': get('location'), 'issues': issues,
                'vehicle_price_id': override.vehicle_price_id if override else None}
        bounds = {'model': 160, 'configuration': 300, 'exterior_color': 100, 'interior_color': 100,
                  'extra_configuration': 500, 'funding_source': 160, 'source_owner': 160, 'location': 160}
        if any(len(item[key]) > limit for key, limit in bounds.items()):
            errors.append({'source_row': source['row'], 'message': '库存字段过长，请核对原表，不会截断发布'})
        (pending if production is None or age < 0 else rows).append(item)
    # Previously reviewed rows may become excluded when the uploader changes
    # the date/store selection. Those overrides have no effect on publication.
    unknown_overrides = set(overrides) - {r['source_row'] for r in rows + pending + excluded}
    if unknown_overrides:
        errors.append({'source_row': min(unknown_overrides), 'message': '核对内容指向未选中或已排除的行，请重新预览'})
    return {'rows': rows, 'pending': pending, 'excluded': excluded, 'errors': errors, 'source_owners': sorted(owners),
            'funding_values': sorted(funds), 'row_count': len(rows), 'excluded_count': len(excluded),
            'pending_count': len(pending),
            'as_of_date': mapping.as_of_date.isoformat(), 'publishable': not errors and bool(rows),
            'notice': '按核算日期与生产日期排除超过180天车辆；未知或未来生产日期留在原件待核对，本行不发布。未出现的旧车不会自动记为已售。'}
