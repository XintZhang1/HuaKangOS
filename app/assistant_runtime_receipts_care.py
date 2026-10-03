"""Exact, read-only receipts for the original care, Group and clearing APIs.

This is a finite native contract, not a table resolver. It never invokes a
command, infers an absent receipt from an error, or manufactures business facts.
"""
import hashlib
import json
from datetime import date

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from .assistant_runtime_receipts_common import (
    digest_matches, invalid, json_signature, native_get, positive_int, result,
    success, validate_evidence,
)
from .assistant_runtime_schemas import ReceiptLookup


CARE_RULE = 'POST /api/customer-service/reminders/rules'
CARE_GENERATE = 'POST /api/customer-service/reminders/generate'
CARE_CREATE = 'POST /api/customer-service/cases'
CARE_ACTION = 'POST /api/customer-service/cases/{case_id}/actions/{action}'
VEHICLE_CREATE = 'POST /api/customer-service/vehicles'
VEHICLE_UPDATE = 'PUT /api/customer-service/vehicles/{vehicle_id}'
VEHICLE_OBSERVATION = 'POST /api/customer-service/vehicles/{vehicle_id}/observations'
VEHICLE_HISTORY = 'POST /api/customer-service/vehicles/{vehicle_id}/history-links'
PRICE_CREATE = 'POST /api/member-pricing/rules'
PRICE_ACTION = 'POST /api/member-pricing/rules/{key}/actions/{action}'
PACKAGE_CREATE = 'POST /api/repair-packages/purchases'
PACKAGE_CAPTURE = 'POST /api/repair-packages/orders/{key}/capture'
PACKAGE_ACTION = 'POST /api/repair-packages/purchases/{key}/actions/{action}'
PACKAGE_REFUND = 'POST /api/repair-packages/refunds/{key}/actions/{action}'
BUNDLE_CREATE = 'POST /api/recharge-bundles/orders'
BUNDLE_ACTION = 'POST /api/recharge-bundles/orders/{key}/actions/{action}'
BENEFIT_ACTION = 'POST /api/group/benefits/members/{member_id}/actions/{action}'
MEMBERSHIP_CREATE = 'POST /api/membership/orders'
MEMBERSHIP_ACTION = 'POST /api/membership/orders/{key}/actions/{action}'
RETAIL_ACTION = 'POST /api/retail-group/orders/{case_id}/actions/{action}'
QUESTIONNAIRE_CREATE = 'POST /api/customer-service/questionnaires/versions'
QUESTIONNAIRE_REVIEW = 'POST /api/customer-service/questionnaires/versions/{version_id}/review'
CORRECTION_CREATE = 'POST /api/observation-corrections/cases'
CORRECTION_ACTION = 'POST /api/observation-corrections/cases/{case_id}/actions/{action}'
CLEARING_CREATE = 'POST /api/reconciliation/clearing'
CLEARING_ACTION = 'POST /api/reconciliation/clearing/{key}/actions/{action}'

CARE_READ = 'GET /api/customer-service/cases/{case_id}'
RULE_READ = 'GET /api/customer-service/reminders/rules'
VEHICLE_READ = 'GET /api/customer-service/vehicles/{vehicle_id}'
VEHICLE_HISTORY_READ = 'GET /api/customer-service/vehicles/{vehicle_id}/history'
PRICE_READ = 'GET /api/member-pricing/rules/{key}'
PACKAGE_READ = 'GET /api/repair-packages/purchases/{key}'
REPAIR_READ = 'GET /api/repair-orders/{case_id}'
BUNDLE_READ = 'GET /api/recharge-bundles/orders/{key}'
BENEFIT_READ = 'GET /api/group/benefits/members/{member_id}'
MEMBER_READ = 'GET /api/group/members/{member_id}'
MEMBERSHIP_READ = 'GET /api/membership/orders/{key}'
RETAIL_READ = 'GET /api/retail-group/orders/{case_id}'
QUESTIONNAIRE_READ = 'GET /api/customer-service/questionnaires/versions'
CORRECTION_READ = 'GET /api/observation-corrections/cases/{case_id}'
CLEARING_READ = 'GET /api/reconciliation/clearing/{key}'

_CARE = frozenset({CARE_RULE, CARE_GENERATE, CARE_CREATE, CARE_ACTION,
                  VEHICLE_CREATE, VEHICLE_UPDATE, VEHICLE_OBSERVATION, VEHICLE_HISTORY,
                  QUESTIONNAIRE_CREATE, QUESTIONNAIRE_REVIEW})
_GROUP = frozenset({PRICE_CREATE, PRICE_ACTION, PACKAGE_CREATE, PACKAGE_CAPTURE,
                   PACKAGE_ACTION, PACKAGE_REFUND, BUNDLE_CREATE, BUNDLE_ACTION,
                   BENEFIT_ACTION, MEMBERSHIP_CREATE, MEMBERSHIP_ACTION, RETAIL_ACTION})
OPERATIONS = _CARE | _GROUP | frozenset({CORRECTION_CREATE, CORRECTION_ACTION,
                                       CLEARING_CREATE, CLEARING_ACTION})


def supports(operation):
    return type(operation) is str and operation in OPERATIONS


def read_operations(snapshot):
    op = snapshot.operation_id
    if op in {CARE_CREATE, CARE_ACTION, CARE_GENERATE}:
        return (CARE_READ,)
    if op == CARE_RULE:
        return (RULE_READ,)
    if op in {VEHICLE_CREATE, VEHICLE_UPDATE, VEHICLE_OBSERVATION}:
        return (VEHICLE_READ,)
    if op == VEHICLE_HISTORY:
        return (VEHICLE_READ, VEHICLE_HISTORY_READ)
    if op in {PRICE_CREATE, PRICE_ACTION}:
        return (PRICE_READ,)
    if op in {PACKAGE_CREATE, PACKAGE_ACTION, PACKAGE_REFUND}:
        return (PACKAGE_READ,)
    if op == PACKAGE_CAPTURE:
        return (REPAIR_READ,)
    if op in {BUNDLE_CREATE, BUNDLE_ACTION}:
        return (BUNDLE_READ,)
    if op == BENEFIT_ACTION:
        return (BENEFIT_READ,)
    if op == MEMBERSHIP_CREATE:
        return (MEMBERSHIP_READ,)
    if op == MEMBERSHIP_ACTION:
        return (MEMBERSHIP_READ, MEMBER_READ, BENEFIT_READ)
    if op == RETAIL_ACTION:
        return (RETAIL_READ,)
    if op in {QUESTIONNAIRE_CREATE, QUESTIONNAIRE_REVIEW}:
        return (QUESTIONNAIRE_READ,)
    if op in {CORRECTION_CREATE, CORRECTION_ACTION}:
        return (CORRECTION_READ,)
    if op in {CLEARING_CREATE, CLEARING_ACTION}:
        return (CLEARING_READ,)
    return ()


def _path(snapshot, *keys):
    if set(snapshot.path_args) != set(keys):
        invalid()
    for key in keys:
        value = snapshot.path_args[key]
        if key == 'action':
            if type(value) is not str:
                invalid()
        elif not positive_int(value):
            invalid()
    return snapshot.path_args


def _values(schema, values, **dump):
    if schema is None:
        invalid()
    return schema.model_validate(values).model_dump(**dump)


def _membership_context(db, user, snapshot, body):
    """Use the original authorized Case and its immutable purpose/value source."""
    from . import flow_engine, group_service, membership_service
    from .membership_models import MembershipOrder
    with group_service.authority(db, user, membership_service.READ):
        row = flow_engine.get_case(db, user, snapshot.path_args['key'])
        if (row.kind != 'membership' or row.flow_version != 2
                or row.store_id != snapshot.store_id):
            raise HTTPException(404, '当前无法读取原会员业务单')
        orders = list(db.scalars(select(MembershipOrder).where(
            MembershipOrder.case_id == row.id, MembershipOrder.store_id == snapshot.store_id)))
        if len(orders) != 1:
            invalid()
        order = orders[0]
        if (not positive_int(order.member_id) or type(order.values) is not dict
                or not positive_int(order.version) or order.version < body.version
                or not positive_int(row.version) or row.version < body.case_version):
            invalid()
        # All current scalar/JSON context is checked again after the native GETs.
        context = (row.id, row.store_id, row.kind, row.flow_version, row.version,
                   row.customer_id, row.owner_id, row.created_by,
                   order.id, order.store_id, order.case_id, order.version,
                   order.member_id, order.purpose, json_signature(order.values),
                   order.requested_by, order.approved_by, order.status,
                   body.version, body.case_version, body.member_version,
                   order.created_at.isoformat(), order.updated_at.isoformat())
        return context, order.purpose, json.loads(json_signature(order.values)), order.member_id


def _command(db, user, snapshot):
    """Reproduce only the original endpoint DTO and executor's exact payload."""
    if not supports(snapshot.operation_id) or snapshot.query or snapshot.body is None or snapshot.request_id is None:
        invalid()
    op, raw, context = snapshot.operation_id, snapshot.body, ()
    if op in _CARE:
        from . import customer_service_api as api
        body = (api.Request if op == CARE_GENERATE else api.Update
                if op in {CARE_ACTION, VEHICLE_UPDATE, VEHICLE_OBSERVATION} else api.Save).model_validate(raw)
        family = 'care'
        if op == CARE_GENERATE:
            _path(snapshot)
            if body.request_id != snapshot.request_id:
                invalid()
            return family, 'generate', None, context
        if op == CARE_RULE:
            _path(snapshot)
            action, payload = 'rule_save', {'id': None, 'version': None, **_values(api.Rule, body.values)}
        elif op == CARE_CREATE:
            _path(snapshot)
            action, payload = 'care_create', _values(api.NewCare, body.values)
        elif op == CARE_ACTION:
            path = _path(snapshot, 'case_id', 'action')
            v = _values({'start': api.Start, 'followup': api.Followup, 'handoff': api.Handoff,
                         'cancel': api.Cancel, 'close': api.Close}.get(path['action']), body.values)
            if v.get('answers') is None:
                v.pop('answers', None)
            action, payload = 'care_' + path['action'], {'case_id': path['case_id'], 'version': body.version, **v}
        elif op == VEHICLE_CREATE:
            _path(snapshot)
            action, payload = 'vehicle_create', _values(api.VehicleInput, body.values)
        elif op in {VEHICLE_UPDATE, VEHICLE_OBSERVATION}:
            path = _path(snapshot, 'vehicle_id')
            action = 'vehicle_update' if op == VEHICLE_UPDATE else 'observe'
            v = _values(api.VehicleEdit if op == VEHICLE_UPDATE else api.Observation, body.values)
            payload = {'id': path['vehicle_id'], 'version': body.version, **v}
        elif op == VEHICLE_HISTORY:
            path = _path(snapshot, 'vehicle_id')
            action, payload = 'history_link', {'vehicle_id': path['vehicle_id'], **_values(api.HistoryLink, body.values)}
        elif op == QUESTIONNAIRE_CREATE:
            _path(snapshot)
            action, payload = 'questionnaire_propose', _values(api.QuestionnaireProposal, body.values)
        else:
            path = _path(snapshot, 'version_id')
            action, payload = 'questionnaire_review', {'version_id': path['version_id'], **_values(api.QuestionnaireDecision, body.values)}
    elif op in {PRICE_CREATE, PRICE_ACTION}:
        from . import member_pricing_api as api
        family = 'group'
        body = (api.Create if op == PRICE_CREATE else api.Command).model_validate(raw)
        if op == PRICE_CREATE:
            _path(snapshot)
            action, payload = 'member_price_create', body.model_dump(mode='json', exclude={'request_id'})
        else:
            path = _path(snapshot, 'key', 'action')
            if path['action'] not in {'submit', 'approve', 'reject', 'cancel'}:
                invalid()
            v = _values(api.Reason if path['action'] == 'cancel' else api.Proof, body.values, mode='json')
            action, payload = 'member_price_' + path['action'], {'rule_id': path['key'], 'version': body.version, 'values': v}
    elif op in {PACKAGE_CREATE, PACKAGE_CAPTURE, PACKAGE_ACTION, PACKAGE_REFUND}:
        from . import repair_package_api as api
        family = 'group'
        body = (api.Purchase if op == PACKAGE_CREATE else api.Command).model_validate(raw)
        if op == PACKAGE_CREATE:
            _path(snapshot)
            action, payload = 'repair_package:purchase', body.model_dump(exclude={'request_id'})
        else:
            path = _path(snapshot, 'key', *(() if op == PACKAGE_CAPTURE else ('action',)))
            if op == PACKAGE_CAPTURE:
                schema, action = api.Evidence, 'repair_package:capture:' + str(path['key'])
            elif op == PACKAGE_ACTION:
                schema = {'authorize': api.Authorize, 'issue': api.Cash, 'cancel': api.Cancel,
                          'refund_request': api.Refund}.get(path['action'])
                action = ('repair_package:refund_request:' + str(path['key'])
                          if path['action'] == 'refund_request' else
                          'repair_package:purchase:' + str(path['key']) + ':' + path['action'])
            else:
                if path['action'] not in {'approve', 'reject', 'cancel', 'pay'}:
                    invalid()
                schema = api.RefundCash if path['action'] == 'pay' else api.Cancel
                action = 'repair_package:refund:' + str(path['key']) + ':' + path['action']
            payload = {'version': body.version, **_values(schema, body.values, mode='json')}
    elif op in {BUNDLE_CREATE, BUNDLE_ACTION, MEMBERSHIP_CREATE, MEMBERSHIP_ACTION}:
        if op in {BUNDLE_CREATE, BUNDLE_ACTION}:
            from . import recharge_bundle_api as api
        else:
            from . import membership_api as api
        family = 'group'
        create = op in {BUNDLE_CREATE, MEMBERSHIP_CREATE}
        body = (api.Create if create else api.Command).model_validate(raw)
        dump = {'mode': 'json'} if op in {BUNDLE_CREATE, BUNDLE_ACTION} else {'exclude_none': True}
        if create:
            _path(snapshot)
            schemas = ({'purchase': api.Purchase, 'refund': api.Refund} if op == BUNDLE_CREATE else
                       {'topup': api.Topup, 'benefit_issue': api.Benefit, 'card_issue': api.Empty,
                        'card_loss': api.Card, 'card_replace': api.Card, 'renew': api.Tier,
                        'tier_change': api.Tier, 'renew_refund': api.Refund, 'points_adjust': api.Points})
            v = _values(schemas.get(body.purpose), body.values, **dump)
            if op == MEMBERSHIP_CREATE and body.purpose == 'points_adjust' and (v['action'] == 'exchange') != bool(v.get('target_rule_id')):
                invalid()
            action = 'bundle_create' if op == BUNDLE_CREATE else 'membership_create'
            payload = {'customer_id': body.customer_id, 'purpose': body.purpose, 'values': v, 'reason': body.reason}
        else:
            path = _path(snapshot, 'key', 'action')
            v = _values({'execute': api.Execute, 'approve': api.Evidence, 'cancel': api.Reason,
                         'reject': api.Reason}.get(path['action']), body.values, **dump)
            action = ('bundle:' if op == BUNDLE_ACTION else 'membership:') + str(path['key']) + ':' + path['action']
            payload = {'version': body.version, 'case_version': body.case_version, 'member_version': body.member_version, 'values': v}
            if op == MEMBERSHIP_ACTION:
                context, purpose, original, member_id = _membership_context(db, user, snapshot, body)
                if path['action'] == 'execute' and purpose in {'topup', 'benefit_issue', 'points_adjust'} and original.get('action') != 'settle_debt':
                    target = 'topup' if purpose == 'topup' else original.get('action')
                    if target not in {'topup', 'grant', 'purchase', 'adjust', 'exchange'}:
                        invalid()
                    v = {k: value for k, value in original.items() if k != 'action'} | v | {'case_id': path['key'], 'case_version': body.case_version}
                    action = 'member_topup' if target == 'topup' else 'benefit:' + str(member_id) + ':' + target
                    payload = {'member_id': member_id, 'version': body.member_version, 'values': v} if target == 'topup' else {'version': body.member_version, 'values': v}
    elif op == BENEFIT_ACTION:
        from . import group_benefits_api as api
        family, body = 'group', api.Command.model_validate(raw)
        path = _path(snapshot, 'member_id', 'action')
        action = 'benefit:' + str(path['member_id']) + ':' + path['action']
        payload = {'version': body.version, 'values': _values(api.SCHEMAS.get(path['action']), body.values)}
    elif op == RETAIL_ACTION:
        from . import retail_group_api as api
        family, body = 'group', api.Envelope.model_validate(raw)
        path = _path(snapshot, 'case_id', 'action')
        v = _values(api.SCHEMAS.get(path['action']), body.values)
        v = {key: str(value) if key == 'due_date' else value for key, value in v.items()}
        action, payload = 'retail_group_' + path['action'], {'case_id': path['case_id'], 'version': body.version, 'values': v}
    elif op in {CORRECTION_CREATE, CORRECTION_ACTION}:
        from . import observation_corrections_api as api
        family = 'correction'
        body = (api.Create if op == CORRECTION_CREATE else api.Command).model_validate(raw)
        if op == CORRECTION_CREATE:
            _path(snapshot)
            action = 'create'
            payload = body.model_dump(mode='json', exclude={'request_id', 'proposed'})
            payload['proposed'] = body.proposed.model_dump(mode='json') if body.proposed is not None else {}
        else:
            path = _path(snapshot, 'case_id', 'action')
            action = path['action']
            v = _values({'submit': api.Proof, 'approve': api.Review, 'reject': api.Review,
                         'cancel': api.Reason}.get(action), body.values, mode='json')
            payload = {'case_id': path['case_id'], 'version': body.version, 'values': v}
    else:
        from . import reconciliation_api as api
        family = 'clearing'
        body = (api.ClearingCreate if op == CLEARING_CREATE else api.Command).model_validate(raw)
        if op == CLEARING_CREATE:
            _path(snapshot)
            action, payload = 'clearing_create', body.model_dump(mode='json', exclude={'request_id'})
        else:
            path = _path(snapshot, 'key', 'action')
            v = _values({'pay': api.Payment, 'receive': api.Payment, 'difference': api.Proof,
                         'cancel': api.Reason, 'reject': api.Reason}.get(path['action']), body.values)
            action, payload = 'clearing:' + str(path['key']) + ':' + path['action'], {'version': body.version, 'case_version': body.case_version, 'values': v}
    if body.request_id != snapshot.request_id:
        invalid()
    return family, action, payload, context


def _encoded(family, action, payload):
    options = {'ensure_ascii': False, 'sort_keys': True, 'separators': (',', ':')}
    if family != 'group':
        options['default'] = str
    value = {'action': action, 'values': payload} if family == 'clearing' else [action, payload]
    return json.dumps(value, **options)


def _receipt_rows(db, user, snapshot, family):
    from . import customer_service, group_service, observation_corrections_service, reconciliation_service
    from .customer_service_models import CareReceipt
    from .group_models import GroupReceipt
    from .observation_corrections_models import CorrectionReceipt
    from .reconciliation_models import ReconciliationReceipt
    if family == 'care':
        authority, models = customer_service.authority, (('care', CareReceipt),)
    elif family == 'group':
        authority, models = group_service.authority, (('group', GroupReceipt),)
    elif family == 'correction':
        authority, models = observation_corrections_service.authority, (('correction', CorrectionReceipt),)
    else:
        authority, models = reconciliation_service.authority, (('clearing', ReconciliationReceipt),)
    if snapshot.operation_id == CARE_GENERATE:
        # CorrectionReceipt uses its original Protected read authority too.
        with observation_corrections_service.authority(db, user) as store_id:
            if store_id != snapshot.store_id:
                raise HTTPException(404, '当前门店无法核对原业务回执')
            correction = _rows(db, snapshot, 'correction', CorrectionReceipt)
        with customer_service.authority(db, user) as store_id:
            if store_id != snapshot.store_id:
                raise HTTPException(404, '当前门店无法核对原业务回执')
            care = _rows(db, snapshot, 'care', CareReceipt)
        return (*care, *correction)
    with authority(db, user) as store_id:
        if store_id != snapshot.store_id:
            raise HTTPException(404, '当前门店无法核对原业务回执')
        return tuple(row for tag, model in models for row in _rows(db, snapshot, tag, model))


def _rows(db, snapshot, tag, model):
    rows = db.scalars(select(model).where(model.store_id == snapshot.store_id,
                                          model.request_key == snapshot.request_id).order_by(model.id))
    return tuple((tag, row.id, row.store_id, row.actor_id, row.request_key,
                  row.digest, json_signature(row.result),
                  row.created_at.isoformat() if tag != 'clearing' else None) for row in rows)


def read_source(db, user, snapshot):
    with db.no_autoflush:
        try:
            family, action, payload, context = _command(db, user, snapshot)
        except ValidationError:
            invalid()
        encoded = None if snapshot.operation_id == CARE_GENERATE else _encoded(family, action, payload)
        rows = _receipt_rows(db, user, snapshot, family)
        return (json_signature(snapshot.model_dump(mode='json')), family, action, encoded, context, rows)


def _one(value, key='id'):
    if type(value) is not dict or not positive_int(value.get(key)):
        invalid()
    return value[key]


def _target(snapshot, actual, key):
    if key in snapshot.path_args and actual != snapshot.path_args[key]:
        invalid()


def _version(value):
    version = value.get('version')
    if version is not None and not positive_int(version):
        invalid()
    return version


async def _visible_objects(db, snapshot, source, native_reader, stored):
    op, objects = snapshot.operation_id, []
    async def get(operation, **path):
        return await native_get(db, native_reader, operation, path_args=path)
    if op == CARE_GENERATE:
        created = stored.get('created')
        if type(created) is not list:
            invalid()
        seen = set()
        for item in created:
            key = _one(item, 'case_id')
            if key in seen:
                invalid()
            seen.add(key)
            visible = await get(CARE_READ, case_id=key)
            if _one(visible) != key:
                invalid()
            objects.append(('care_case', key, _version(visible)))
        return objects
    if op == CARE_RULE:
        key = _one(stored.get('rule'))
        data = await get(RULE_READ)
        rows = data.get('items')
        if type(rows) is not list:
            invalid()
        found = [r for r in rows if type(r) is dict and r.get('id') == key]
        if len(found) != 1:
            raise HTTPException(404, '当前无法读取原提醒规则')
        return [('reminder_rule', key, _version(found[0]))]
    if op in {CARE_CREATE, CARE_ACTION}:
        key = _one(stored.get('case'))
        _target(snapshot, key, 'case_id')
        data = await get(CARE_READ, case_id=key)
        if _one(data) != key:
            invalid()
        return [('care_case', key, _version(data))]
    if op in {VEHICLE_CREATE, VEHICLE_UPDATE, VEHICLE_OBSERVATION, VEHICLE_HISTORY}:
        key = _one(stored.get('vehicle'))
        _target(snapshot, key, 'vehicle_id')
        data = await get(VEHICLE_READ, vehicle_id=key)
        if _one(data.get('vehicle')) != key:
            invalid()
        if op == VEHICLE_OBSERVATION:
            original = stored.get('observation')
            observation_id = _one(original)
            if original.get('vehicle_id') != key or type(data.get('observations')) is not list:
                invalid()
            matching = [row for row in data['observations'] if type(row) is dict and row.get('id') == observation_id and row.get('vehicle_id') == key]
            if len(matching) != 1:
                invalid()
        if op == VEHICLE_HISTORY:
            if not positive_int(stored.get('link_id')):
                invalid()
            history = await get(VEHICLE_HISTORY_READ, vehicle_id=key)
            if type(history.get('items')) is not list:
                invalid()
            # The immutable native receipt owns link_id; GET grants visibility
            # to the real vehicle and its original related service summaries.
        return [('customer_vehicle', key, _version(data['vehicle']))]
    if op in {PRICE_CREATE, PRICE_ACTION}:
        key = _one(stored)
        _target(snapshot, key, 'key')
        data = await get(PRICE_READ, key=key)
        if _one(data) != key:
            invalid()
        return [('member_pricing_rule', key, _version(data))]
    if op in {PACKAGE_CREATE, PACKAGE_ACTION, PACKAGE_REFUND}:
        refund = op == PACKAGE_REFUND or op == PACKAGE_ACTION and snapshot.path_args['action'] == 'refund_request'
        key = _one(stored, 'purchase_id' if refund else 'id')
        if op == PACKAGE_ACTION or op == PACKAGE_REFUND:
            _target(snapshot, _one(stored) if op == PACKAGE_REFUND else key, 'key')
        data = await get(PACKAGE_READ, key=key)
        if _one(data) != key:
            invalid()
        if refund:
            refund_id = _one(stored)
            refunds = data.get('refunds')
            if type(refunds) is not list or len([r for r in refunds if type(r) is dict and r.get('id') == refund_id and r.get('purchase_id') == key]) != 1:
                raise HTTPException(404, '当前无法读取原套餐退款记录')
        return [('package_purchase', key, _version(data))]
    if op == PACKAGE_CAPTURE:
        key = _one(stored, 'case_id')
        _target(snapshot, key, 'key')
        data = await get(REPAIR_READ, case_id=key)
        if _one(data) != key:
            invalid()
        return [('case', key, _version(data))]
    if op in {BUNDLE_CREATE, BUNDLE_ACTION, MEMBERSHIP_CREATE, MEMBERSHIP_ACTION}:
        delegated = op == MEMBERSHIP_ACTION and source[2].startswith(('member_', 'benefit:'))
        key = snapshot.path_args['key'] if delegated else _one(stored.get('case'))
        _target(snapshot, key, 'key')
        data = await get(MEMBERSHIP_READ if op in {MEMBERSHIP_CREATE, MEMBERSHIP_ACTION} else BUNDLE_READ, key=key)
        if _one(data.get('case')) != key:
            invalid()
        if delegated:
            member_id = source[4][12]
            if _one(stored.get('member')) != member_id or _one(data.get('member')) != member_id:
                invalid()
            member = await get(MEMBER_READ if source[2] == 'member_topup' else BENEFIT_READ, member_id=member_id)
            if _one(member.get('member')) != member_id:
                invalid()
        return [('case', key, _version(data['case']))]
    if op == BENEFIT_ACTION:
        key = _one(stored.get('member'))
        _target(snapshot, key, 'member_id')
        data = await get(BENEFIT_READ, member_id=key)
        if _one(data.get('member')) != key:
            invalid()
        return [('group_member', key, _version(data['member']))]
    if op == RETAIL_ACTION:
        key = _one(stored, 'case_id')
        _target(snapshot, key, 'case_id')
        data = await get(RETAIL_READ, case_id=key)
        if _one(data, 'case_id') != key:
            invalid()
        return [('case', key, _version(data))]
    if op in {QUESTIONNAIRE_CREATE, QUESTIONNAIRE_REVIEW}:
        key = _one(stored.get('questionnaire_version'))
        _target(snapshot, key, 'version_id')
        data = await get(QUESTIONNAIRE_READ)
        rows = data.get('items')
        if type(rows) is not list:
            invalid()
        if len([r for r in rows if type(r) is dict and r.get('id') == key]) != 1:
            # The original bounded directory does not prove nonexistence.
            raise HTTPException(404, '原问卷版本未在当前可见目录中完整核对')
        return [('questionnaire_version', key, None)]
    if op in {CORRECTION_CREATE, CORRECTION_ACTION}:
        key = _one(stored.get('case'))
        _target(snapshot, key, 'case_id')
        data = await get(CORRECTION_READ, case_id=key)
        if _one(data) != key:
            invalid()
        return [('observation_correction', key, _version(data))]
    if op in {CLEARING_CREATE, CLEARING_ACTION}:
        key = _one(stored)
        _target(snapshot, key, 'key')
        data = await get(CLEARING_READ, key=key)
        if _one(data) != key:
            invalid()
        return [('clearing_order', key, _version(data))]
    invalid()


async def lookup_visible(db, user, snapshot, native_reader):
    source = read_source(db, user, snapshot)
    rows = source[5]
    if not rows:
        return result('not_found', 'native_receipt_not_found')
    if len(rows) != 1:
        return result('mismatch', 'native_receipt_ambiguous')
    tag, receipt_id, store_id, actor_id, nonce, actual_digest, frozen_json, _ = rows[0]
    if (not positive_int(receipt_id) or store_id != snapshot.store_id
            or actor_id != snapshot.actor_id or nonce != snapshot.request_id):
        return result('mismatch', 'native_receipt_identity_mismatch')
    stored = json.loads(frozen_json)
    if type(stored) is not dict:
        return result('mismatch', 'native_receipt_result_invalid')
    encoded = source[3]
    if snapshot.operation_id == CARE_GENERATE:
        as_of = stored.get('as_of')
        if type(as_of) is not str or type(stored.get('automatic')) is not bool or stored['automatic']:
            return result('mismatch', 'native_receipt_generation_invalid')
        try:
            if date.fromisoformat(as_of).isoformat() != as_of:
                raise ValueError()
        except ValueError:
            return result('mismatch', 'native_receipt_generation_invalid')
        encoded = _encoded(tag, 'generate_reminders' if tag == 'care' else 'generate', {'day': as_of, 'automatic': False})
    expected = hashlib.sha256(encoded.encode()).hexdigest()
    if not digest_matches(actual_digest, expected):
        return result('mismatch', 'native_receipt_digest_mismatch')
    try:
        objects = await _visible_objects(db, snapshot, source, native_reader, stored)
    except HTTPException as error:
        if error.status_code == 404:
            return result('inaccessible', 'native_receipt_object_inaccessible')
        if error.status_code == 409:
            return result('mismatch', 'native_receipt_result_mismatch')
        raise
    return success(snapshot, receipt_id, objects)


def validate_lookup(snapshot, lookup):
    """Restrict restored results to this operation's original native namespace."""
    op = snapshot.operation_id
    if not supports(op):
        return False
    try:
        lookup = ReceiptLookup.model_validate(lookup)
    except (ValueError, TypeError):
        return False
    if op == CARE_GENERATE:
        return validate_evidence(snapshot, lookup, {'care_case'}, min_objects=0)
    if op == CARE_RULE:
        kind = 'reminder_rule'
    elif op in {CARE_CREATE, CARE_ACTION}:
        kind = 'care_case'
    elif op in {VEHICLE_CREATE, VEHICLE_UPDATE, VEHICLE_OBSERVATION, VEHICLE_HISTORY}:
        kind = 'customer_vehicle'
    elif op in {PRICE_CREATE, PRICE_ACTION}:
        kind = 'member_pricing_rule'
    elif op in {PACKAGE_CREATE, PACKAGE_ACTION, PACKAGE_REFUND}:
        kind = 'package_purchase'
    elif op == BENEFIT_ACTION:
        kind = 'group_member'
    elif op in {QUESTIONNAIRE_CREATE, QUESTIONNAIRE_REVIEW}:
        kind = 'questionnaire_version'
    elif op in {CORRECTION_CREATE, CORRECTION_ACTION}:
        kind = 'observation_correction'
    elif op in {CLEARING_CREATE, CLEARING_ACTION}:
        kind = 'clearing_order'
    else:
        kind = 'case'
    if not validate_evidence(snapshot, lookup, {kind}, min_objects=1, max_objects=1):
        return False
    key = ('vehicle_id' if kind == 'customer_vehicle' else 'member_id' if kind == 'group_member'
           else 'version_id' if kind == 'questionnaire_version' else 'case_id'
           if op in {CARE_ACTION, CORRECTION_ACTION, RETAIL_ACTION} else 'key')
    # Refund actions target a refund but return its original purchase object.
    if op == PACKAGE_REFUND:
        return True
    target = snapshot.path_args.get(key)
    return target is None or positive_int(target) and lookup.object_refs[0].id == target


__all__ = ['supports', 'read_source', 'read_operations', 'lookup_visible', 'validate_lookup']
