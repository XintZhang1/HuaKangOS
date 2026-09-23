"""V10: freeze local original retail/group allocations and pending liabilities.

Actual period cash/stock/member movements remain in their original ledgers. The
new immutable associations are explicitly generation-time sources, NOT another
cash or revenue book. C/P/S are independently labelled credit, original issue
consideration and internal settlement, never summed across tables. Only local
product scopes are included; an issuer's private case/files are not disclosed.
Older statement definitions keep their original source sets.
"""
from collections import defaultdict

VALUE_FIELDS = ('credit_cents', 'consideration_cents', 'settlement_cents')
FROZEN_FIELDS = {
    'retail_group_scopes': ('eligibility_id', 'item_id', 'component', 'work_item_id',
        'sku', 'name', 'unit', 'work_code'),
    'retail_group_plans': ('case_id', 'member_id', 'evidence_id', 'actor_id', 'digest'),
    'retail_group_tenders': ('plan_id', 'sequence', 'kind', 'wallet_id',
        'eligibility_id', 'units', *VALUE_FIELDS, 'expires_on'),
    'retail_group_units': ('tender_id', 'sequence', *VALUE_FIELDS),
    'retail_group_allocations': ('unit_id', 'line_id', 'component', *VALUE_FIELDS),
    'retail_group_reservations': ('tender_id', 'principal_id', 'benefit_id'),
    'retail_group_captures': ('tender_id', 'reservation_id', 'principal_id', 'benefit_id'),
    'retail_group_closures': ('tender_id', 'evidence_id', 'actor_id', 'reason'),
    'retail_group_returns': ('plan_id', 'posting_id'),
    'retail_group_return_parts': ('return_id', 'allocation_id', 'capture_id', *VALUE_FIELDS),
    'retail_group_restores': ('unit_id', 'capture_id', 'principal_id', 'benefit_id',
        *VALUE_FIELDS, 'evidence_id', 'actor_id'),
    'retail_group_settlements': ('return_part_id', 'restore_id', 'side', 'amount_cents'),
    'retail_group_cash_allocations': ('allocation_id', 'payment_link_id', 'amount_cents', 'original_id'),
}
PERIOD_NAMES = set()
CURRENT_NAMES = set(FROZEN_FIELDS)


def source_summary(entries):
    """Summarize one table; the tables intentionally overlap economically."""
    out = {'count': len(entries), 'amount_cents': 0, 'value_cents': 0,
           'quantity_milli_by_item': {}, 'units_by_kind': {},
           **{name: 0 for name in VALUE_FIELDS}}
    for entry in entries:
        data = entry['data']
        if entry['basis'] != 'current':
            raise ValueError('精品集团原关联必须明确采用生成时点口径')
        for key in ('amount_cents', *VALUE_FIELDS):
            value = data.get(key, 0)
            if type(value) is not int:
                raise ValueError('精品集团冻结金额必须为整数分')
            out[key] += value
        if entry['source'] == 'retail_group_tenders':
            kind, units = data['kind'], data['units']
            if kind not in {'cash', 'principal', 'bonus', 'coupon', 'package'} or type(units) is not int or units <= 0:
                raise ValueError('精品集团冻结单位口径无效')
            out['units_by_kind'][kind] = out['units_by_kind'].get(kind, 0) + units
    return out


def pending_from_manifest(manifest):
    """Reconstruct the frozen subset, not today's subsequently changed wallet.

    Actual returns reduce consideration immediately. A not-yet-complete original
    coupon/package remains a nonspendable claim without fabricating a new expiry
    or another refund. Later lawful restores must not invalidate an older batch.
    """
    tables = {name: {} for name in CURRENT_NAMES}
    for entry in manifest:
        if entry['source'] in tables:
            tables[entry['source']][entry['source_id']] = entry['data']
    plans = tables['retail_group_plans']
    tenders = tables['retail_group_tenders']
    units = tables['retail_group_units']
    allocations = tables['retail_group_allocations']
    captures = tables['retail_group_captures']
    returns = tables['retail_group_returns']
    remaining = defaultdict(lambda: [0, 0, 0])
    for part in tables['retail_group_return_parts'].values():
        allocation = allocations.get(part['allocation_id'])
        record = returns.get(part['return_id'])
        unit = units.get(allocation['unit_id']) if allocation else None
        tender = tenders.get(unit['tender_id']) if unit else None
        if not tender or not record or record['plan_id'] != tender['plan_id']:
            raise ValueError('冻结精品退回份额缺少本单原分摊')
        if part['capture_id'] is None:
            continue
        capture = captures.get(part['capture_id'])
        if not capture or capture['tender_id'] != tender['id']:
            raise ValueError('冻结待恢复份额不是本单原核销')
        for i, key in enumerate(VALUE_FIELDS):
            remaining[unit['id']][i] += part[key]
    for restore in tables['retail_group_restores'].values():
        unit = units.get(restore['unit_id'])
        capture = captures.get(restore['capture_id'])
        if not unit or not capture or unit['tender_id'] != capture['tender_id']:
            raise ValueError('冻结原恢复缺少原单位或原核销')
        for i, key in enumerate(VALUE_FIELDS):
            remaining[unit['id']][i] -= restore[key]
    out = []
    for uid, values in sorted(remaining.items()):
        unit = units[uid]
        tender = tenders[unit['tender_id']]
        plan = plans.get(tender['plan_id'])
        if not plan or any(v < 0 or v > unit[key] for v, key in zip(values, VALUE_FIELDS)):
            raise ValueError('冻结原单位待恢复负债不守恒')
        if not values[0]:
            if any(values):
                raise ValueError('零原面额仍残留对价或往来')
            continue
        out.append({'case_id': plan['case_id'], 'plan_id': plan['id'],
            'unit_id': uid, 'tender_id': tender['id'], 'kind': tender['kind'],
            **dict(zip(VALUE_FIELDS, values)), 'spendable_cents': 0,
            'original_expires_on': tender['expires_on'],
            'original_unit_complete': values[0] == unit['credit_cents'],
            'restorable': tender['kind'] in {'principal', 'bonus'} or values[0] == unit['credit_cents']})
    return out


def validate_frozen_summary(manifest, summary, start, end):
    for name in CURRENT_NAMES:
        entries = [e for e in manifest if e['source'] == name]
        if summary.get(name) != source_summary(entries):
            raise ValueError('冻结精品集团 C/P/S 摘要与原关联集合不一致')
    if summary.get('retail_group_pending_original_units') != pending_from_manifest(manifest):
        raise ValueError('冻结精品原单位待恢复负债与原退和原恢复不一致')
