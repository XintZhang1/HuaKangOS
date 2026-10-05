"""Typed employee answers for existing API contracts, without guessed facts.

Probe values exist only in a temporary copy used for schema validation. They are
never saved, displayed as known facts, or sent to a business write endpoint.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from fastapi import HTTPException

MAX_QUESTIONS = 64
MAX_OPTIONS = 200
PROTECTED = {'request_id', 'version', 'store_id', 'password', 'token', 'api_key',
             'authorization', 'cookie', 'csrf', '__proto__', 'constructor', 'prototype'}


def option_value(option):
    value = option.get('value') if isinstance(option, dict) else option
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value) if isinstance(value, (str, int)) else ''


def normalize_questions(raw, sanitize):
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_QUESTIONS:
        raise HTTPException(422, '请按表单提供缺项列表；内容较多时拆分表单，不要遗漏必填项')
    result, seen = [], set()
    for item in raw:
        if not isinstance(item, dict):
            raise HTTPException(422, '缺项必须包含准确字段名和中文标签')
        key = sanitize(item.get('key') or '', 120).strip()
        label = sanitize(item.get('label') or '', 160).strip()
        if (not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+))*', key)
                or len(key) > 120 or not label or any(p.lower() in PROTECTED or p.lower().endswith('_version') for p in key.split('.'))):
            raise HTTPException(422, '请按真实业务字段填写缺项；内部版本、提交标识和门店应由系统读取')
        if key in seen:
            raise HTTPException(422, '同一字段不要重复提问：' + label)
        seen.add(key)
        raw_options = item.get('options') or []
        if not isinstance(raw_options, list) or len(raw_options) > MAX_OPTIONS:
            raise HTTPException(422, '候选较多，请先按员工给出的名称缩小查询，再提供完整的可选列表')
        options, values = [], set()
        for option in raw_options:
            value = option_value(option)
            if isinstance(option, dict):
                title = sanitize(option.get('label') or '', 160).strip()
                if not title or not value or len(value) > 200 or sanitize(value, 200) != value:
                    raise HTTPException(422, '候选需要真实值和中文名称，不要编造或填写敏感内容')
                normalized = {'label': title, 'value': value}
            elif isinstance(option, str) and option.strip():
                value = sanitize(option, 200).strip()
                normalized = value  # Retain R2 string-enum compatibility.
            else:
                raise HTTPException(422, '请选择已查询到的候选值，不要用空项或无效对象代替')
            if value in values:
                continue
            values.add(value)
            options.append(normalized)
        result.append({'key': key, 'label': label, 'options': options,
                       'required': item.get('required') is not False})
    return result


def _resolve(schema, root):
    schema = deepcopy(schema or {})
    for _ in range(12):
        ref = schema.get('$ref')
        if ref:
            if not ref.startswith('#/$defs/'):
                return {}
            schema = deepcopy(root.get('$defs', {}).get(ref.split('/')[-1], {}))
            continue
        options = [x for x in schema.get('anyOf', []) if x.get('type') != 'null']
        if options:
            schema = deepcopy(options[0])
            continue
        return schema
    return {}


def _flow_schema(fields):
    properties, required = {}, []
    ids = {'employee', 'vehicle', 'account', 'file', 'signed_file', 'handover_file',
           'item', 'member', 'payment', 'stock_issue', 'billable_case', 'customer'}
    for field in fields:
        kind = field['type']
        spec = {'title': field['label'], 'type': 'string', 'minLength': 1}
        if kind in ids:
            spec = {'title': field['label'], 'type': 'integer', 'minimum': 1}
        elif kind == 'bool':
            spec = {'title': field['label'], 'type': 'boolean'}
        elif kind in {'date', 'future_date'}:
            spec['format'] = 'date'
        elif kind in {'money', 'money_zero', 'quantity', 'quantity_zero'}:
            spec['x-input-type'] = 'decimal'
            spec['x-unit'] = '元' if kind.startswith('money') else '数量'
        elif kind == 'select':
            spec['enum'] = list(field.get('options', []))
        if field['key'] in {'phone', 'customer_phone'}:
            spec['pattern'] = r'^[0-9+() \-]{3,30}$'
        properties[field['key']] = spec
        if field.get('required'):
            required.append(field['key'])
    return {'type': 'object', 'properties': properties, 'required': required}


def body_schema(gateway, operation_id, path_args, body, question_fields=None):
    operation = gateway.inspect_operation(operation_id)
    root = deepcopy(operation.get('body_schema') or {})
    kind = (path_args or {}).get('kind') or (body or {}).get('kind')
    values = None
    native = operation.get('action_schemas', {}).get((path_args or {}).get('action'))
    if native is not None:
        values = deepcopy(native)
    elif operation_id.startswith(('POST /api/masters/', 'PUT /api/masters/')):
        from .master_data import CATALOG
        if kind in CATALOG:
            values = CATALOG[kind][1].model_json_schema()
    elif '/api/flow/master/' in operation_id:
        from .flow_api import MASTERS
        if kind in MASTERS:
            values = _flow_schema(MASTERS[kind]['fields'])
    elif operation_id == 'POST /api/flow/cases':
        from .flow_specs import SPECS
        if kind in SPECS:
            values = _flow_schema(SPECS[kind]['fields'])
    elif question_fields is not None:
        values = _flow_schema(question_fields)
    if values:
        root.setdefault('$defs', {}).update(values.get('$defs', {}))
        root.setdefault('properties', {})['values'] = values
    return root


def _schema_at(root, key):
    node = root
    for part in key.split('.'):
        node = _resolve(node, root)
        if node.get('type') == 'array' and part.isdigit():
            node = node.get('items', {})
        else:
            props = node.get('properties', {})
            if part not in props:
                # Dynamic action envelopes are parsed again by their native API.
                if node.get('additionalProperties') is True:
                    return {}
                raise HTTPException(422, '缺项字段不在本次表单中：' + key)
            node = props[part]
    return _resolve(node, root)


def _canonical(root, key):
    # Compatibility only for historical R2 cards with an invented top prefix.
    top = root.get('properties', {})
    if not key.startswith('values.') and key.split('.')[0] not in top and key.split('.')[-1] in top:
        return key.split('.')[-1]
    return key


def _put(body, key, value):
    parts, node = key.split('.'), body
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                raise HTTPException(422, '请先提供真实明细行，再填写该行的缺项：' + key)
            position = int(part)
            if last:
                node[position] = value
            else:
                node = node[position]
        elif isinstance(node, dict):
            if part.isdigit():
                raise HTTPException(422, '明细字段路径不正确：' + key)
            if last:
                node[part] = value
            else:
                if part not in node:
                    if parts[index + 1].isdigit():
                        raise HTTPException(422, '不能凭空增加未知明细行：' + key)
                    node[part] = {}
                node = node[part]
        else:
            raise HTTPException(422, '缺项字段路径不正确：' + key)


def describe_questions(gateway, operation_id, path_args, body, questions, question_fields=None):
    root = body_schema(gateway, operation_id, path_args, body, question_fields)
    result = []
    for q in questions:
        q = deepcopy(q)
        key = _canonical(root, q['key'])
        spec = _schema_at(root, key)
        typ = spec.get('type', 'string')
        scale = 100 if typ == 'integer' and key.endswith('_cents') else 1000 if typ == 'integer' and key.endswith('_milli') else 1
        q['key'] = key
        q['input_type'] = ('decimal' if scale != 1 else 'date' if spec.get('format') == 'date'
                           else spec.get('x-input-type') or {'integer': 'integer', 'boolean': 'boolean'}.get(typ, 'text'))
        q['storage_type'] = typ
        q['scale'] = scale
        q['unit'] = '元' if scale == 100 else '数量' if scale == 1000 else spec.get('x-unit', '')
        if scale != 1:
            q['label'] = q['label'].replace('（分）', '（元）').replace('(分)', '（元）').replace('（千分之一）', '')
        if typ in {'array', 'object'}:
            raise HTTPException(422, '请把多行或复合资料展开为具体字段，不能只用一个文本框：' + q['label'])
        if typ == 'boolean' and not q['options']:
            q['options'] = [{'label': '是', 'value': 'true'}, {'label': '否', 'value': 'false'}]
        if spec.get('enum') and not q['options']:
            q['options'] = [{'label': str(x), 'value': option_value(x)} for x in spec['enum']]
        result.append(q)
    return result


def _typed(value, spec, label, *, scale=1):
    typ = spec.get('type', 'string')
    try:
        if scale != 1:
            amount = Decimal(value)
            if not amount.is_finite() or amount * scale != (amount * scale).to_integral_value():
                raise ValueError()
            # Native numeric bounds are checked again before any write.
            if abs(amount) > Decimal('1e15'):
                raise ValueError()
            return int(amount * scale)
        if typ == 'integer':
            if not re.fullmatch(r'-?(?:0|[1-9][0-9]*)', value):
                raise ValueError()
            return int(value)
        if typ == 'boolean':
            if value not in {'true', 'false'}:
                raise ValueError()
            return value == 'true'
        if typ == 'number':
            number = Decimal(value)
            if not number.is_finite() or abs(number) > Decimal('1e15'):
                raise ValueError()
            return float(number)
        if spec.get('format') == 'date':
            date.fromisoformat(value)
        return value
    except (ValueError, InvalidOperation, OverflowError):
        raise HTTPException(422, label + '填写不正确，请检查数值、单位或日期') from None


def probe_body(gateway, operation_id, path_args, body, questions, question_fields=None):
    root = body_schema(gateway, operation_id, path_args, body, question_fields)
    result = deepcopy(body or {})
    for q in questions:
        key = _canonical(root, q['key'])
        spec = _schema_at(root, key)
        typ = spec.get('type', q.get('storage_type', 'string'))
        if q.get('options'):
            value = _typed(option_value(q['options'][0]), spec, q['label'])
        elif spec.get('enum'):
            value = spec['enum'][0]
        elif typ in {'integer', 'number'}:
            value = max(1, spec.get('minimum', 1), int(spec.get('exclusiveMinimum', 0)) + 1)
            if 'maximum' in spec:
                value = min(value, spec['maximum'])
        elif typ == 'boolean':
            value = False
        elif spec.get('format') == 'date':
            from .db import today
            value = today().isoformat()
        elif spec.get('x-input-type') == 'decimal':
            value = '1'
        else:
            pattern = spec.get('pattern', '')
            value = '00000000000' if ('phone' in key or '[0-9+' in pattern) else 'PENDING' if pattern else '待员工填写'
            value = (value * (1 + spec.get('minLength', 1) // len(value)))[:max(len(value), spec.get('minLength', 1))]
        _put(result, key, value)
    return result


def merge_answers(gateway, row, answers):
    if not isinstance(answers, dict) or not answers:
        return row.payload
    root = body_schema(gateway, row.operation_id, row.payload.get('path_args'), row.payload.get('body'))
    questions = {q['key']: q for q in (row.questions or [])}
    payload = deepcopy(row.payload)
    body = payload.setdefault('body', {})
    for key, value in answers.items():
        if key not in questions:
            raise HTTPException(422, '回答包含不属于这张卡的字段，请刷新确认卡')
        q = questions[key]
        if not isinstance(value, str) or len(value) > 200:
            raise HTTPException(422, q['label'] + '填写内容过长或格式不正确')
        value = value.strip()
        if not value:
            continue
        if q.get('options') and value not in {option_value(x) for x in q['options']}:
            raise HTTPException(422, q['label'] + '不在本次查询到的候选中，请重新选择')
        canonical = _canonical(root, key)
        spec = _schema_at(root, canonical)
        # Action fields were obtained by the authorized get_case call when prepared.
        if not spec:
            spec = {'type': q.get('storage_type', 'string')}
        typ = spec.get('type')
        scale = 100 if typ == 'integer' and canonical.endswith('_cents') else 1000 if typ == 'integer' and canonical.endswith('_milli') else 1
        # Select values are native values, not employee-entered human units.
        converted = _typed(value, spec, q['label'], scale=1 if q.get('options') else scale)
        _put(body, canonical, converted)
    return payload
