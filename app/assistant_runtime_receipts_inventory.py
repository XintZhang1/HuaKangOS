"""The 28 registered intake, transfer and pointer/master receipt templates.

Only original command DTOs and immutable receipts are read. No command is
replayed, no physical fact substitutes for a command receipt, and every result
is checked through the current employee's original GET before it is returned.
"""
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from .assistant_runtime_receipts_common import (
    digest_matches, invalid, json_signature, native_get, positive_int, result,
    success, validate_evidence,
)
from .assistant_runtime_schemas import ReceiptLookup, SubmissionSnapshot
from .dossier_grant_models import DossierReceipt
from .master_models import MasterReceipt
from .retail_bundle_models import RetailBundleReceipt
from .rework_extension_models import ReworkGrantReceipt
from .service_intake_models import IntakeReceipt
from .transfer_exception_models import TransferExceptionReceipt
from .transfer_goods_recovery_models import GoodsReceipt
from .transfer_models import TransferReceipt
from .vehicle_imports_models import VehicleImportRequest
from .vehicle_transport_models import VehicleTransportReceipt


# family, original receipt model, original pointer/result, native object type,
# original GET. Vehicle transfer intentionally shares TransferReceipt.
OPERATIONS = {
    'POST /api/service-intake/appointments': ('appointment', IntakeReceipt, 'result', 'service_appointment', 'GET /api/service-intake/appointments/{key}'),
    'POST /api/service-intake/appointments/{key}/actions/{action}': ('appointment', IntakeReceipt, 'result', 'service_appointment', 'GET /api/service-intake/appointments/{key}'),
    'POST /api/gate-visits': ('gate', IntakeReceipt, 'result', 'gate_visit', 'GET /api/gate-visits/{key}'),
    'POST /api/gate-visits/{key}/actions/{action}': ('gate', IntakeReceipt, 'result', 'gate_visit', 'GET /api/gate-visits/{key}'),
    'POST /api/gate-visits/{key}/corrections': ('gate', IntakeReceipt, 'result', 'gate_visit', 'GET /api/gate-visits/{key}'),
    'POST /api/gate-visits/corrections/{key}/actions/{action}': ('gate', IntakeReceipt, 'result', 'gate_visit', 'GET /api/gate-visits/{key}'),
    'POST /api/gate-visits/repair-orders/{key}/departure': ('departure', IntakeReceipt, 'result', 'case', 'GET /api/repair-orders/{case_id}'),
    'POST /api/rework-extensions/requests': ('rework_request', IntakeReceipt, 'result', 'case', 'GET /api/service-intake/reworks/{key}'),
    'POST /api/transfers': ('material', TransferReceipt, 'result', 'material_transfer', 'GET /api/transfers/{key}'),
    'POST /api/transfers/{key}/actions/{action}': ('material', TransferReceipt, 'result', 'material_transfer', 'GET /api/transfers/{key}'),
    'POST /api/vehicle-transfers': ('vehicle', TransferReceipt, 'result', 'vehicle_transfer', 'GET /api/vehicle-transfers/{key}'),
    'POST /api/vehicle-transfers/{key}/actions/{action}': ('vehicle', TransferReceipt, 'result', 'vehicle_transfer', 'GET /api/vehicle-transfers/{key}'),
    'POST /api/transfer-exceptions': ('exception', TransferExceptionReceipt, 'result', 'transfer_exception', 'GET /api/transfer-exceptions/{key}'),
    'POST /api/transfer-exceptions/{key}/actions/{action}': ('exception', TransferExceptionReceipt, 'result', 'transfer_exception', 'GET /api/transfer-exceptions/{key}'),
    'POST /api/transfer-goods-recoveries': ('goods', GoodsReceipt, 'recovery_id', 'goods_recovery', 'GET /api/transfer-goods-recoveries/{key}'),
    'POST /api/transfer-goods-recoveries/{key}/actions/{action}': ('goods', GoodsReceipt, 'recovery_id', 'goods_recovery', 'GET /api/transfer-goods-recoveries/{key}'),
    'POST /api/vehicle-transport-exceptions': ('transport', VehicleTransportReceipt, 'result', 'vehicle_transport_exception', 'GET /api/vehicle-transport-exceptions/{key}'),
    'POST /api/vehicle-transport-exceptions/{key}/actions/{action}': ('transport', VehicleTransportReceipt, 'result', 'vehicle_transport_exception', 'GET /api/vehicle-transport-exceptions/{key}'),
    'POST /api/dictionaries/{group}': ('dictionary', MasterReceipt, 'result', 'dictionary_entry', 'GET /api/dictionaries/{group}'),
    'PUT /api/dictionaries/{group}/{record_id}': ('dictionary', MasterReceipt, 'result', 'dictionary_entry', 'GET /api/dictionaries/{group}'),
    'POST /api/masters/{kind}': ('master', MasterReceipt, 'result', None, 'GET /api/masters/{kind}'),
    'PUT /api/masters/{kind}/{record_id}': ('master', MasterReceipt, 'result', None, 'GET /api/masters/{kind}'),
    'POST /api/dossier-grants': ('dossier', DossierReceipt, 'grant_id', 'dossier_grant', 'GET /api/dossier-grants/{grant_id}'),
    'POST /api/dossier-grants/{grant_id}/actions/{action}': ('dossier', DossierReceipt, 'grant_id', 'dossier_grant', 'GET /api/dossier-grants/{grant_id}'),
    'POST /api/rework-extensions/grants': ('rework_grant', ReworkGrantReceipt, 'grant_id', 'rework_source_grant', 'GET /api/rework-extensions/grants/{key}'),
    'POST /api/rework-extensions/grants/{key}/actions/{action}': ('rework_grant', ReworkGrantReceipt, 'grant_id', 'rework_source_grant', 'GET /api/rework-extensions/grants/{key}'),
    'POST /api/retail-bundles/rules': ('bundle', RetailBundleReceipt, 'rule_id', 'retail_bundle_rule', 'GET /api/retail-bundles/rules'),
    'POST /api/vehicle-imports/batches/{batch_id}/actions/{action}': ('import', VehicleImportRequest, 'batch_id', 'vehicle_import_batch', 'GET /api/vehicle-imports/batches/{batch_id}'),
}


@dataclass(frozen=True)
class _Command:
    digest: str | None
    object_type: str
    default_source: tuple = ()


def supports(operation_id):
    return type(operation_id) is str and operation_id in OPERATIONS


def _checked(snapshot):
    try:
        checked = SubmissionSnapshot.model_validate(
            snapshot.model_dump() if isinstance(snapshot, SubmissionSnapshot) else snapshot)
        if not supports(checked.operation_id) or checked.query or checked.body is None:
            invalid()
        keys = set(re.findall(r'\{([a-z_]+)\}', checked.operation_id))
        if set(checked.path_args) != keys:
            invalid()
        for key, value in checked.path_args.items():
            if key not in {'action', 'group', 'kind'} and not positive_int(value):
                invalid()
            if key in {'action', 'group', 'kind'} and (type(value) is not str or not value):
                invalid()
        return checked
    except (ValidationError, ValueError, TypeError):
        invalid()


def _pair(action, payload, *, string_dates=False):
    options = {'sort_keys': True, 'ensure_ascii': False, 'separators': (',', ':')}
    if string_dates:
        options['default'] = str
    return hashlib.sha256(json.dumps([action, payload], **options).encode()).hexdigest()


def _values(schemas, action, values, *, mode='python'):
    schema = schemas.get(action)
    if schema is None:
        invalid()
    return schema.model_validate(values).model_dump(mode=mode)


def _receipts(db, user, snapshot):
    family, model, pointer, _, _ = OPERATIONS[snapshot.operation_id]
    nonce = model.request_id if family == 'bundle' else model.request_key
    query = select(model).where(model.store_id == snapshot.store_id, nonce == snapshot.request_id)
    # This original family has an actor-specific nonce, unlike the other 27.
    if family == 'import':
        query = query.where(model.actor_id == snapshot.actor_id)
    context = nullcontext()
    if family == 'goods':
        from .transfer_goods_recovery_service import authority
        context = authority(db, user)
    with context:
        rows = list(db.scalars(query.order_by(model.id).execution_options(populate_existing=True)))
        detached = []
        for row in rows:
            source = {'id': row.id, 'store_id': row.store_id, 'actor_id': row.actor_id,
                      'nonce': row.request_id if family == 'bundle' else row.request_key,
                      'digest': row.digest, pointer: deepcopy(getattr(row, pointer))}
            if family == 'dossier':
                source.update(action=row.action, request_data=deepcopy(row.request_data),
                              scope_digest=row.scope_digest)
            detached.append(source)
        return detached


def _convert_default(db, user, snapshot, receipts):
    """Recover only the original append-only convert event, never today's date."""
    if len(receipts) != 1 or receipts[0]['actor_id'] != snapshot.actor_id:
        return None, ()
    saved = receipts[0].get('result')
    if (type(saved) is not dict or saved.get('id') != snapshot.path_args['key']
            or saved.get('status') != 'converted' or not positive_int(saved.get('case_id'))
            or not positive_int(saved.get('repair_case_id'))):
        return None, ()
    from . import flow_engine as flow
    from .flow_models import FlowEvent
    from .service_intake_models import ServiceAppointment
    appointment = db.scalar(select(ServiceAppointment).where(
        ServiceAppointment.id == saved['id'], ServiceAppointment.store_id == snapshot.store_id
    ).execution_options(populate_existing=True))
    case = flow.get_case(db, user, saved['case_id'])
    if (appointment is None or appointment.case_id != case.id
            or appointment.repair_case_id != saved['repair_case_id']
            or case.store_id != snapshot.store_id or case.kind != 'service_intake'
            or case.flow_version != 2):
        invalid()
    events = list(db.scalars(select(FlowEvent).where(
        FlowEvent.store_id == snapshot.store_id, FlowEvent.case_id == case.id,
        FlowEvent.action == 'intake_convert'
    ).order_by(FlowEvent.id).execution_options(populate_existing=True)))
    evidence = tuple((event.id, event.store_id, event.actor_id, event.case_id,
                      event.action, json_signature(event.detail),
                      event.occurred_at.isoformat()) for event in events)
    binding = (appointment.id, appointment.store_id, appointment.case_id,
               appointment.repair_case_id, case.id, case.store_id, case.kind, case.flow_version)
    if len(events) != 1 or events[0].actor_id != snapshot.actor_id:
        return None, (binding, evidence)
    detail = events[0].detail
    if type(detail) is not dict or set(detail) != {'due_date'} or type(detail['due_date']) is not str:
        return None, (binding, evidence)
    return detail['due_date'], (binding, evidence)


def _command(db, user, snapshot, receipts):
    """Mirror the original handler's DTO dump and service digest, explicitly."""
    from . import flow_engine as flow
    operation, body, path = snapshot.operation_id, snapshot.body, snapshot.path_args
    family, _, _, object_type, _ = OPERATIONS[operation]
    action = path.get('action')
    key = path.get('key')
    default_source = ()
    if family == 'appointment':
        from . import service_intake_api as api
        if not path:
            native = api.AppointmentSave.model_validate(body)
            payload = native.model_dump(mode='json', exclude={'request_id'})
            digest = flow.request_digest('intake_appointment_create', payload)
        else:
            native = api.Command.model_validate(body)
            values = native.values
            if action == 'convert' and 'due_date' not in values:
                day, default_source = _convert_default(db, user, snapshot, receipts)
                if day is None:
                    return _Command(None, object_type, default_source)
                values = {**values, 'due_date': day}
            values = _values(api.APPOINTMENT_ACTIONS, action, values, mode='json')
            digest = flow.request_digest('intake_appointment_' + action,
                                         {'id': key, 'version': native.version, **values})
    elif family in {'gate', 'departure'}:
        from . import gate_visit_api as api
        if not path:
            native = api.VisitCreate.model_validate(body)
            digest = flow.request_digest('intake_gate_create', native.model_dump(exclude={'request_id'}))
        else:
            native = api.Command.model_validate(body)
            if family == 'departure':
                suffix, schema = 'repair_exit', api.Actual
            elif operation == 'POST /api/gate-visits/{key}/corrections':
                suffix, schema = 'correct', api.Correction
            elif operation == 'POST /api/gate-visits/corrections/{key}/actions/{action}':
                if action not in {'approve', 'reject', 'cancel'}:
                    invalid()
                suffix, schema = 'review_' + action, api.Reason if action == 'cancel' else api.Review
            else:
                if action not in {'arrive', 'leave', 'cancel', 'handoff'}:
                    invalid()
                suffix = action
                schema = api.Handoff if action == 'handoff' else api.Reason if action == 'cancel' else api.Actual
            values = schema.model_validate(native.values).model_dump(mode='json')
            digest = flow.request_digest('intake_gate_' + suffix,
                                         {'id': key, 'version': native.version, **values})
    elif family == 'rework_request':
        from .rework_extension_api import Accept
        native = Accept.model_validate(body)
        digest = flow.request_digest('intake_rework_extension_create', native.model_dump(exclude={'request_id'}))
    elif family in {'material', 'vehicle'}:
        from . import transfer_api as material_api, vehicle_transfer_api as vehicle_api
        api = material_api if family == 'material' else vehicle_api
        if not path:
            native = api.Create.model_validate(body)
            payload = native.model_dump(mode='json', exclude={'request_id'})
            digest = _pair('create' if family == 'material' else 'vehicle:create', payload)
        else:
            native = api.Command.model_validate(body)
            schemas = api.SCHEMAS
            if family == 'material' and action == 'return_receive':
                from .transfer_service import action_version
                version = action_version(db, user, key)
                default_source = (version,)
                if version == 3:
                    schemas = {**schemas, 'return_receive': material_api.ReturnReceiveV3}
            values = _values(schemas, action, native.values)
            prefix = '' if family == 'material' else 'vehicle:'
            digest = _pair(prefix + str(key) + ':' + action,
                           {'version': native.version, 'case_version': native.case_version, 'values': values})
    elif family in {'exception', 'goods', 'transport'}:
        from . import transfer_exception_api as exception_api
        from . import transfer_goods_recovery_api as goods_api
        from . import vehicle_transport_api as transport_api
        api = {'exception': exception_api, 'goods': goods_api, 'transport': transport_api}[family]
        if not path:
            native = api.Create.model_validate(body)
            if family == 'goods' and native.confirmed is not True:
                invalid()
            payload = native.model_dump(exclude={'request_id', 'confirmed'})
            if family == 'goods' and payload.get('previous_recovery_id') is None:
                payload.pop('previous_recovery_id', None)
            action_key = 'vehicle_transport:create' if family == 'transport' else 'create'
        else:
            native = api.Command.model_validate(body)
            values = _values(api.SCHEMAS, action, native.values)
            if family == 'goods' and 'confirmed' in values and values['confirmed'] is not True:
                invalid()
            payload = {'version': native.version, 'case_version': native.case_version, 'values': values}
            if family == 'transport':
                payload['exception_version'] = native.exception_version
            else:
                payload['transfer_version'] = native.transfer_version
            action_key = ('vehicle_transport:' if family == 'transport' else '') + str(key) + ':' + action
        if family == 'transport':
            from .vehicle_transport_rules import signature
            digest = signature({'action': action_key, 'values': payload})
        else:
            digest = _pair(action_key, payload, string_dates=True)
    elif family in {'dictionary', 'master'}:
        from . import dictionary_api as dictionary_api, master_api as master_api
        from .master_data import _digest
        update = operation.startswith('PUT ')
        api = dictionary_api if family == 'dictionary' else master_api
        native = (api.Update if update else api.Save).model_validate(body)
        record_id, version = (path['record_id'], native.version) if update else (None, None)
        if family == 'dictionary':
            group = path['group']
            dictionary_api.category(group)
            values = native.values.model_dump()
            name = 'dictionary:' + group
        else:
            from .assistant_runtime_domains.typed_master import KIND_TO_TYPE
            kind = path['kind']
            if kind not in KIND_TO_TYPE:
                invalid()
            object_type = KIND_TO_TYPE[kind]
            # Original raw values are hashed before the master's schema defaults.
            values, name = native.values, 'master:' + kind
        digest = _digest(name, {'id': record_id, 'version': version, 'values': values})
    elif family == 'dossier':
        from . import dossier_grant_api as api, dossier_grant_rules as rules
        if not path:
            native = api.Save.model_validate(body)
            payload = native.values.model_dump()
            payload['expires_at'] = rules.iso(payload['expires_at'])
            action_key = 'propose'
        else:
            if action not in {'approve', 'reject', 'cancel', 'revoke'}:
                invalid()
            native = api.Decision.model_validate(body)
            payload = {'grant_id': path['grant_id'], 'version': native.version, **native.values.model_dump()}
            action_key = action
        digest = rules.digest({'action': action_key, 'payload': payload})
        for receipt in receipts:
            if (receipt['action'] != action_key
                    or json_signature(receipt['request_data']) != json_signature(payload)):
                invalid()
    elif family == 'rework_grant':
        from . import rework_extension_api as api
        from .rework_extension_service import digest as grant_digest
        if not path:
            native = api.Proposal.model_validate(body)
            payload = native.model_dump(mode='json', exclude={'request_id'})
            action_key = 'propose'
        else:
            if action not in {'approve', 'reject', 'cancel', 'revoke'}:
                invalid()
            native = api.Command.model_validate(body)
            payload = {'id': key, 'version': native.version,
                       **api.Reason.model_validate(native.values).model_dump(mode='json')}
            action_key = action
        digest = grant_digest([action_key, payload])
    elif family == 'bundle':
        from .retail_bundle_api import Publish
        native = Publish.model_validate(body)
        digest = flow.request_digest('retail_bundle_rule',
                                     {'base_version': native.base_version, 'values': native.values.model_dump(mode='json')})
    elif family == 'import':
        from . import vehicle_imports_api as api
        if action not in {'trial', 'review', 'confirm', 'cancel', 'reassign'}:
            invalid()
        native = api.Action.model_validate(body)
        values = {'confirm': api.Confirm, 'reassign': api.Reassign}.get(action, api.Reason).model_validate(native.values).model_dump()
        payload = {'action': action, 'batch_id': path['batch_id'], 'version': native.version,
                   'case_version': native.source_case_version, 'values': values}
        # Original imports use json.dumps' default spaces, not compact JSON.
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    else:
        invalid()
    if native.request_id != snapshot.request_id:
        invalid()
    return _Command(digest, object_type, default_source)


def _bundle(db, user, snapshot):
    checked = _checked(snapshot)
    from .business_assistant_service import require_preparation_read_phase
    from .tenancy import single_store
    require_preparation_read_phase(db)
    if user.id != checked.actor_id or single_store(db) != checked.store_id:
        invalid()
    receipts = _receipts(db, user, checked)
    try:
        command = _command(db, user, checked, receipts)
    except (ValidationError, ValueError, TypeError, OverflowError):
        invalid()
    return checked, command, receipts


def read_source(db, user, snapshot):
    checked, command, receipts = _bundle(db, user, snapshot)
    return ('inventory', checked.operation_id, checked.actor_id, checked.store_id,
            checked.request_id, command.digest, command.object_type,
            command.default_source, tuple(json_signature(row) for row in receipts))


def read_operations(snapshot):
    checked = _checked(snapshot)
    reads = (OPERATIONS[checked.operation_id][4],)
    if OPERATIONS[checked.operation_id][0] == 'rework_request':
        reads += ('GET /api/flow/cases/{case_id}',)
    return reads


def _target(snapshot, receipt):
    family, _, pointer, _, _ = OPERATIONS[snapshot.operation_id]
    saved = receipt[pointer]
    if pointer == 'result':
        if type(saved) is not dict or saved.get('truncated'):
            invalid()
        if 'store_id' in saved and saved['store_id'] != snapshot.store_id:
            invalid()
        target = saved.get('case_id') if family == 'departure' else saved.get('id')
    else:
        target = saved
    if not positive_int(target):
        invalid()
    path = snapshot.path_args
    expected = path.get('record_id', path.get('grant_id', path.get('batch_id', path.get('key'))))
    correction_review = snapshot.operation_id == 'POST /api/gate-visits/corrections/{key}/actions/{action}'
    if expected is not None and not correction_review and target != expected:
        invalid()
    if family == 'dossier':
        if receipt['action'] != path.get('action', 'propose') or not digest_matches(receipt['scope_digest'], receipt['scope_digest']):
            invalid()
    if correction_review:
        corrections = saved.get('corrections')
        if type(corrections) is not list or len([row for row in corrections if type(row) is dict and row.get('id') == expected]) != 1:
            invalid()
    if family == 'departure' and not positive_int(saved.get('exit_id')):
        invalid()
    return target


async def _listed(db, reader, operation, path, target, *, dictionary=False, rules=False):
    for page in range(1, 51):
        query = {} if rules else {'page': page, **({'page_size': 100} if dictionary else {})}
        data = await native_get(db, reader, operation, path_args=path, query=query)
        items = data.get('items')
        if type(items) is not list or any(type(row) is not dict or not positive_int(row.get('id')) for row in items):
            invalid()
        matches = [row for row in items if row['id'] == target]
        if len(matches) > 1:
            invalid()
        if matches:
            return matches[0]
        if rules:
            raise HTTPException(404, '当前原套餐目录未包含该原记录')
        # Original dictionary and master lists have exact page/total semantics.
        size = 100 if dictionary else 30
        total = data.get('total')
        if (type(data.get('page')) is not int or data['page'] != page
                or type(total) is not int or total < 0 or len(items) > size
                or dictionary and data.get('page_size') != size):
            invalid()
        if page * size >= total:
            raise HTTPException(404, '当前原列表未包含该原记录')
        if not items:
            raise HTTPException(503, '原列表分页未完整，不能核定回执结果')
    raise HTTPException(503, '原列表分页窗口未命中，不能核定回执结果')


async def lookup_visible(db, user, snapshot, native_reader):
    try:
        checked, command, receipts = _bundle(db, user, snapshot)
        if not receipts:
            return result('not_found', 'native_receipt_not_found')
        if len(receipts) != 1:
            return result('mismatch', 'native_receipt_ambiguous')
        receipt = receipts[0]
        if (not positive_int(receipt['id']) or receipt['store_id'] != checked.store_id
                or receipt['actor_id'] != checked.actor_id or receipt['nonce'] != checked.request_id):
            return result('mismatch', 'native_receipt_identity_mismatch')
        if command.digest is None:
            return result('unsupported', 'native_default_not_frozen')
        if not digest_matches(receipt['digest'], command.digest):
            return result('mismatch', 'native_receipt_digest_mismatch')
        target = _target(checked, receipt)
        family, _, pointer, _, operation = OPERATIONS[checked.operation_id]
        if family in {'dictionary', 'master', 'bundle'}:
            path = ({'group': checked.path_args['group']} if family == 'dictionary' else
                    {'kind': checked.path_args['kind']} if family == 'master' else {})
            data = await _listed(db, native_reader, operation, path, target,
                                 dictionary=family == 'dictionary', rules=family == 'bundle')
        else:
            arg = ('grant_id' if family == 'dossier' else 'batch_id' if family == 'import'
                   else 'case_id' if family == 'departure' else 'key')
            data = await native_get(db, native_reader, operation, path_args={arg: target})
        if data.get('id') != target or not positive_int(data.get('id')):
            invalid()
        if 'store_id' in data and data['store_id'] != checked.store_id:
            invalid()
        if family in {'appointment', 'gate', 'rework_request'} and not positive_int(data.get('customer_vehicle_id')):
            invalid()
        if family == 'dictionary':
            from .dictionary_api import category
            if data.get('category') != category(checked.path_args['group']):
                invalid()
        if family == 'dossier':
            if data.get('from_store_id') != checked.store_id or not digest_matches(data.get('scope_digest'), receipt['scope_digest']):
                invalid()
        if family == 'rework_grant' and data.get('from_store_id') != checked.store_id:
            invalid()
        if family == 'departure':
            intake = data.get('service_intake')
            if (data.get('store_id') != checked.store_id or data.get('flow_version') != 4
                    or type(intake) is not dict or intake.get('cancelled_gate_exit_id') != receipt[pointer]['exit_id']):
                invalid()
        if family in {'material', 'vehicle', 'exception', 'goods', 'transport', 'import'} and not positive_int(data.get('case_id')):
            invalid()
        if family in {'exception', 'goods', 'transport'} and not positive_int(data.get('transfer_id')):
            invalid()
        if family == 'rework_request':
            case_id = data.get('case_id')
            contract = data.get('rework_extension')
            if (not positive_int(case_id) or type(contract) is not dict
                    or contract.get('grant_id') != checked.body['grant_id']
                    or receipt['result'].get('case_id') != case_id):
                invalid()
            case = await native_get(db, native_reader, 'GET /api/flow/cases/{case_id}',
                                    path_args={'case_id': case_id})
            if (case.get('id') != case_id or case.get('store_id') != checked.store_id
                    or case.get('kind') != 'service_intake' or case.get('flow_version') != 2
                    or type(case.get('data')) is not dict or case['data'].get('rework_id') != target):
                invalid()
            target, data = case_id, case
        correction_review = checked.operation_id == 'POST /api/gate-visits/corrections/{key}/actions/{action}'
        if correction_review:
            corrections = data.get('corrections')
            if type(corrections) is not list or len([row for row in corrections if type(row) is dict and row.get('id') == checked.path_args['key']]) != 1:
                invalid()
        # Transport details expose parent Transfer.version separately from the
        # original Exception.version; bundle rule revisions are also distinct.
        version = data.get('exception_version') if family == 'transport' else data.get('rule_version') if family == 'bundle' else data.get('version')
        if version is not None and not positive_int(version):
            invalid()
        return success(checked, receipt['id'], [(command.object_type, target, version)])
    except HTTPException as exc:
        if exc.status_code in {401, 403, 404}:
            return result('inaccessible', 'native_object_inaccessible')
        if exc.status_code == 409:
            return result('mismatch', 'native_receipt_source_mismatch')
        raise


def validate_lookup(snapshot, lookup):
    try:
        checked = _checked(snapshot)
        family, _, _, object_type, _ = OPERATIONS[checked.operation_id]
        if family == 'master':
            from .assistant_runtime_domains.typed_master import KIND_TO_TYPE
            object_type = KIND_TO_TYPE.get(checked.path_args['kind'])
        if object_type is None or not validate_evidence(checked, lookup, {object_type}, min_objects=1, max_objects=1):
            return False
        lookup = ReceiptLookup.model_validate(lookup)
        path = checked.path_args
        target = path.get('record_id', path.get('grant_id', path.get('batch_id', path.get('key'))))
        if checked.operation_id == 'POST /api/gate-visits/corrections/{key}/actions/{action}':
            target = None  # path key is Correction.id; the checked result is Visit.id.
        return target is None or lookup.object_refs[0].id == target
    except (HTTPException, ValueError, TypeError, KeyError):
        return False


__all__ = ['supports', 'read_source', 'read_operations', 'lookup_visible', 'validate_lookup']
