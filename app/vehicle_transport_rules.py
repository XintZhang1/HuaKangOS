"""Pure original-source rules shared by live commands, reports and restoration."""
from datetime import date, datetime, timezone
import hashlib
import json
import re

ACTIVE_ORIGINS = {'transit', 'rejected', 'return_transit'}
OBSERVATIONS = {'dispatch_verified', 'not_located', 'original_seen', 'unusable_held', 'other_vin_seen', 'found_usable'}


def clean(row):
    if isinstance(row, dict):
        return {k: clean(v) for k, v in row.items()}
    if isinstance(row, (list, tuple)): return [clean(v) for v in row]
    if isinstance(row, (date, datetime)): return row.isoformat()
    return row


def signature(value):
    return hashlib.sha256(json.dumps(clean(value), sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def timestamp(value):
    if isinstance(value, str): value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime): raise ValueError('实物核对时间不完整')
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def parties(parent, exception):
    source, target = parent['from_store_id'], parent['to_store_id']
    if source == target: raise ValueError('整车调拨双方不能相同')
    return (target, source) if exception['origin_status'] == 'return_transit' else (source, target)


def origin_payload(parent, exception, original, source, destination, found=None, loss=None):
    keys = ('id', 'from_store_id', 'to_store_id', 'from_case_id', 'to_case_id', 'source_vehicle_id', 'vin', 'snapshot')
    return {'parent': {k: parent[k] for k in keys},
        'exception': {k: exception[k] for k in ('id', 'transfer_id', 'original_id', 'origin_status', 'kind', 'store_id', 'requested_by')},
        'dispatch': {k: original[k] for k in ('id', 'store_id', 'transfer_id', 'case_id', 'vehicle_id', 'kind', 'quantity', 'value_cents', 'evidence_id', 'actor_id', 'business_date')},
        'source_observation': source, 'destination_observation': destination, 'found_observation': found, 'loss': loss}


def validate_observation(parent, exception, observation, original, *, loss=None, timezone_name='Asia/Shanghai'):
    sid = observation['store_id']; vin = observation['vin']; kind = observation['kind']
    sender, receiver = parties(parent, exception)
    if observation['exception_id'] != exception['id'] or sid not in {sender, receiver} or kind not in OBSERVATIONS:
        raise ValueError('整车观察不属于本次原调拨双方')
    if not re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}', vin): raise ValueError('观察VIN不是明确的17位车辆身份')
    if (kind == 'other_vin_seen') == (vin == parent['vin']):
        raise ValueError('其他VIN观察须与原车不同；其余核对必须针对原VIN')
    actual, created = timestamp(observation['actual_at']), timestamp(observation['created_at'])
    from zoneinfo import ZoneInfo
    actual_day = actual.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(timezone_name)).date()
    if actual > created or actual_day.isoformat() < str(original['business_date'])[:10]:
        raise ValueError('实物核对不能晚于登记或早于原发出记录')
    if kind == 'found_usable':
        if not loss or loss['kind'] != 'missing' or actual < timestamp(loss['created_at']):
            raise ValueError('后来找到须关联已确认失联原车；实际销毁原车不能改称找回')
    elif loss and created >= timestamp(loss['created_at']):
        raise ValueError('损失后的发现须另记找回观察，不能覆盖原调查')
    elif sid == sender and kind != 'dispatch_verified':
        raise ValueError('本段发出方只确认本店原VIN发运；不替接收方确认失联或到货')
    elif sid == receiver and kind == 'dispatch_verified':
        raise ValueError('本段接收方不能替发出方确认原发运')


def validate_plan(parent, exception, original, source, destination, plan, found=None, loss=None, *, timezone_name='Asia/Shanghai'):
    snapshot = parent['snapshot']
    if isinstance(snapshot, str): snapshot = json.loads(snapshot)
    value = snapshot['purchase_cost_cents']
    if type(value) is not int or value < 0 or original['kind'] != 'dispatch' or original['quantity'] != -1 or original['value_cents'] != -value:
        raise ValueError('损失与找回必须对应唯一原发出及整数原成本')
    if original['id'] != exception['original_id'] or original['transfer_id'] != parent['id'] or original['store_id'] != parent['from_store_id'] or original['vehicle_id'] != parent['source_vehicle_id']:
        raise ValueError('原发出来源与车辆或调拨门店不一致')
    if plan['exception_id'] != exception['id'] or source['id'] != plan['source_observation_id'] or destination['id'] != plan['destination_observation_id']:
        raise ValueError('方案没有锁定原调查两店观察')
    if source['store_id'] != parent['from_store_id'] or destination['store_id'] != parent['to_store_id']:
        raise ValueError('方案中的两店原观察相互替换或不属于调拨双方')
    for obs in (source, destination): validate_observation(parent, exception, obs, original, loss=loss, timezone_name=timezone_name)
    sender, receiver = parties(parent, exception)
    by_store = {source['store_id']: source, destination['store_id']: destination}
    if by_store[sender]['kind'] != 'dispatch_verified': raise ValueError('原发出方尚未明确核对原VIN发运')
    created = timestamp(plan['created_at'])
    if any(timestamp(obs['created_at']) > created for obs in (source, destination)):
        raise ValueError('方案不能引用未来才登记的实物观察')
    if plan['store_id'] != parent['from_store_id']:
        raise ValueError('原损失、成本恢复方案应由原资产门店提出')
    kind = plan['kind']; a = plan['source_bearer_cents']; b = plan['destination_bearer_cents']
    if type(a) is not int or type(b) is not int or min(a, b) < 0: raise ValueError('成本承担必须为非负整数分')
    if kind == 'resume':
        if loss or by_store[receiver]['kind'] != 'original_seen' or a or b or plan['loss_method'] != 'none' or found:
            raise ValueError('解除差异须接收方已确认原VIN在场；不生成库存、损失或现金')
    elif kind == 'loss':
        if loss or a + b != value: raise ValueError('双方损失承担必须恰好等于该原VIN未入库原成本')
        expected = 'not_located' if plan['loss_method'] == 'missing' else 'unusable_held' if plan['loss_method'] == 'destroyed' else None
        if expected is None or by_store[receiver]['kind'] != expected or found:
            raise ValueError('失联确认或在手不可用车处置须依据本段接收方实际观察')
    elif kind == 'found_receive':
        if not loss or loss['kind'] != 'missing' or a or b or plan['loss_method'] != 'none' or not found:
            raise ValueError('找回原成本接收只用于已确认失联原车')
        validate_observation(parent, exception, found, original, loss=loss, timezone_name=timezone_name)
        if found['kind'] != 'found_usable' or found['id'] != plan['found_observation_id'] or plan['receiving_store_id'] != found['store_id']:
            raise ValueError('实际找回门店必须是本人核对原车已在场的门店')
        if timestamp(found['created_at']) > created: raise ValueError('恢复方案不能引用未来找回观察')
    else: raise ValueError('整车差异方案类型不受支持')
    expected = signature(origin_payload(parent, exception, original, source, destination, found, loss))
    if plan['origin_digest'] != expected: raise ValueError('原VIN、原成本或本版原观察摘要不一致')
    return value


def independent_reviewers(exception, plan, observations):
    return {exception['requested_by'], plan['actor_id']} | {o['actor_id'] for o in observations if o}


def found_pair_amount(parent, loss, receiving_store_id):
    """Source-perspective net liability: original burden reversal + actual asset receipt."""
    if receiving_store_id not in {parent['from_store_id'], parent['to_store_id']}:
        raise ValueError('实际找回接收门店不属于原调拨双方')
    return (loss['value_cents'] if receiving_store_id == parent['to_store_id'] else 0) - loss['destination_bearer_cents']
