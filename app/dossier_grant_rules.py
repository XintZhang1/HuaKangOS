"""Small, allowlisted dossier projections shared with read-only restore checks.

No recursive source JSON, automatic related-case traversal or file discovery is
part of an approved projection. Adding a projection requires a new definition.
"""
import hashlib
import json
from datetime import datetime, timezone

PROJECTION_VERSION = 1
MAX_FILES = 100  # Operational per-grant review/response budget, not a security proof.
MAX_VALIDITY_DAYS = 366  # Operational finite-grant limit; dates still checked on every read.
MANAGE = {'admin', 'manager'}
FINANCIAL = {'admin', 'manager', 'finance', 'auditor'}
READ = FINANCIAL | {'sales', 'service', 'reception', 'customer_service', 'inventory', 'technician'}
WRITE = READ - {'auditor'}
STATES = {'pending': '待原店复核', 'approved': '已批准', 'rejected': '未批准',
          'cancelled': '已取消', 'revoked': '已撤销', 'expired': '已到期', 'suspended': '权限变化，已暂停'}
# System policy/opening/configuration cases are not customer dossiers. They must
# use their own administrative controls instead of a general sharing backdoor.
EXCLUDED = {'business_entity', 'opening_import', 'reconciliation', 'interstore_clearing',
            'retail_group_rule', 'business_finance'}
FILE_KEYS = ('id', 'store_id', 'case_id', 'category', 'name', 'media_type', 'size', 'sha256',
             'created_by', 'generated', 'template_version', 'template_approved',
             'source_fingerprint', 'source_file_id')


def timestamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime):
        raise ValueError('授权时间格式错误')
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def iso(value):
    return timestamp(value).isoformat() + 'Z'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def file_snapshot(asset):
    info = {key: getattr(asset, key) for key in FILE_KEYS}
    info['created_at'] = iso(asset.created_at)
    return info


def scope_payload(grant, files):
    """Accept dicts or ORM rows, allowing restore validation without a live user."""
    def get(key):
        return grant[key] if isinstance(grant, dict) else getattr(grant, key)
    keys = ('from_store_id', 'to_store_id', 'source_case_id', 'source_case_version',
        'recipient_id', 'recipient_role', 'recipient_access_version', 'requested_by',
        'requester_role', 'requester_access_version', 'purpose')
    value = {key: get(key) for key in keys}
    value.update({key: bool(get(key)) for key in ('include_record', 'include_financials', 'include_contact')})
    record = get('record_snapshot')
    value['record_snapshot'] = json.loads(record) if isinstance(record, str) else record
    value['expires_at'], value['created_at'] = iso(get('expires_at')), iso(get('created_at'))
    value['files'] = sorted(files, key=lambda r: r['id'])
    return value


def role_allows(db, role, case):
    from .flow_engine import READ_KINDS
    if role not in READ or case.kind in EXCLUDED:
        return False
    if role == 'finance' and case.kind in {'customer_care', 'observation_correction'}:
        return False
    if case.kind == 'vehicle_operations':
        from .vehicle_operations_service import role_can_read_case
        return role_can_read_case(db, role, case)
    if role in FINANCIAL:
        return True
    if case.kind not in READ_KINDS.get(role, set()):
        return False
    if role == 'inventory' and case.kind == 'repair':
        return case.flow_version in {3, 4}
    if role == 'inventory' and case.kind == 'addon':
        return case.flow_version == 3
    return True


def validate_record(record, include_record, include_contact, include_financials):
    """Structural allowlist is checked on live reads and offline restoration."""
    if not include_record:
        if record or include_contact or include_financials:
            raise ValueError('仅文件范围附带了原单内容')
        return
    required = {'definition_version', 'case', 'events', 'event_total', 'events_omitted'}
    optional = {'customer', 'vehicle'} | ({'financials'} if include_financials else set())
    if not isinstance(record, dict) or not required <= record.keys() or record.keys() - required - optional:
        raise ValueError('快照字段不是批准的白名单')
    if record['definition_version'] != PROJECTION_VERSION:
        raise ValueError('未知快照定义')
    header = record['case']
    keys = {'id', 'store_id', 'number', 'kind', 'flow_version', 'version', 'state', 'title',
            'kind_label', 'state_label', 'business_date', 'due_date', 'completed_date', 'updated_at'}
    if not isinstance(header, dict) or header.keys() != keys:
        raise ValueError('原单头字段不完整')
    for key in ('id', 'store_id', 'flow_version', 'version'):
        if type(header[key]) is not int or header[key] <= 0:
            raise ValueError('原单来源版本非法')
    if header['kind'] in EXCLUDED:
        raise ValueError('不能授权系统管理类原单')
    if 'customer' in record:
        allowed = {'name', 'phone', 'contact_allowed'} if include_contact else {'name'}
        if not isinstance(record['customer'], dict) or record['customer'].keys() != allowed:
            raise ValueError('联系方式超出批准范围')
    if 'vehicle' in record and (not isinstance(record['vehicle'], dict)
                               or record['vehicle'].keys() != {'vin', 'model', 'color'}):
        raise ValueError('车辆资料超出批准范围')
    if include_financials:
        f = record.get('financials')
        if not isinstance(f, dict) or f.keys() != {'amount_cents', 'paid_cents', 'cost_cents', 'basis'}:
            raise ValueError('原单金额快照不完整')
        # Case.cost_cents is nullable: a missing original cost is an unknown
        # fact, not zero and not permission to infer another domain's cost.
        if (any(type(f[k]) is not int for k in ('amount_cents', 'paid_cents'))
            or f['cost_cents'] is not None and type(f['cost_cents']) is not int):
            raise ValueError('金额不是整数分')
    events = record['events']
    if not isinstance(events, list) or len(events) > 200:
        raise ValueError('原办理记录窗口非法')
    ids = []
    for event in events:
        if not isinstance(event, dict) or event.keys() != {'id', 'label', 'from_state', 'to_state', 'occurred_at'}:
            raise ValueError('原事件包含未授权明细')
        if type(event['id']) is not int or event['id'] <= 0:
            raise ValueError('原事件编号非法')
        ids.append(event['id'])
        timestamp(event['occurred_at'])
    if ids != sorted(set(ids)):
        raise ValueError('原事件顺序或编号重复')
    if (type(record['event_total']) is not int or type(record['events_omitted']) is not int
        or record['event_total'] < len(events) or record['events_omitted'] != record['event_total'] - len(events)):
        raise ValueError('原办理记录窗口计数不一致')
