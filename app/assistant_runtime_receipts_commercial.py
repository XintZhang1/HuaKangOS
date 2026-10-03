"""Fixed original commercial command receipts, without replay or business writes.

The central receipt reader owns confirmation, identity, authority and fresh
source checks. This module restores only the listed native DTO/digest contracts
and reads their original receipt tables and current employee GETs.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import json

from fastapi import HTTPException
from sqlalchemy import select

from .assistant_runtime_receipts_common import (
    digest_matches, invalid, json_signature, native_get, positive_int,
    result, success, validate_evidence,
)


_FLOW_READ = 'GET /api/flow/cases/{case_id}'


@dataclass(frozen=True)
class _Route:
    family: str
    path_key: str | None
    read_operation: str
    read_key: str
    kinds: tuple[str, ...]
    object_type: str = 'case'
    fixed_action: str | None = None


# These are the complete original templates, not URL prefixes or a model map.
_ROUTES = {
    'POST /api/service-orders': _Route('service', None, 'GET /api/service-orders/{case_id}', 'case_id', ('agency', 'other_income')),
    'POST /api/service-orders/{case_id}/actions/{action}': _Route('service', 'case_id', 'GET /api/service-orders/{case_id}', 'case_id', ('agency', 'other_income')),
    'POST /api/addon-orders': _Route('addon', None, 'GET /api/addon-orders/{key}', 'key', ('addon',)),
    'POST /api/addon-orders/{key}/actions/{action}': _Route('addon', 'key', 'GET /api/addon-orders/{key}', 'key', ('addon',)),
    'POST /api/insurance-orders': _Route('insurance', None, 'GET /api/insurance-orders/{case_id}', 'case_id', ('insurance',)),
    'POST /api/insurance-orders/{case_id}/actions/{action}': _Route('insurance', 'case_id', 'GET /api/insurance-orders/{case_id}', 'case_id', ('insurance',)),
    'POST /api/reconciliation/batches': _Route('batch', None, 'GET /api/reconciliation/batches/{key}', 'key', (), 'reconciliation_batch'),
    'POST /api/reconciliation/batches/{key}/actions/{action}': _Route('batch', 'key', 'GET /api/reconciliation/batches/{key}', 'key', (), 'reconciliation_batch'),
    'POST /api/invoices/orders': _Route('invoice', None, 'GET /api/invoices/orders/{key}', 'key', ('invoice',)),
    'POST /api/invoices/orders/{key}/actions/{action}': _Route('invoice', 'key', 'GET /api/invoices/orders/{key}', 'key', ('invoice',)),
    'POST /api/business-finance/orders': _Route('finance', None, 'GET /api/business-finance/orders/{key}', 'key', ('business_finance',)),
    'POST /api/business-finance/orders/{key}/actions/{action}': _Route('finance', 'key', 'GET /api/business-finance/orders/{key}', 'key', ('business_finance',)),
    'POST /api/repair-packages/orders/{key}/quote': _Route('package_quote', 'key', 'GET /api/repair-orders/{case_id}', 'case_id', ('repair',), fixed_action='quote'),
    'POST /api/warehouse/cases': _Route('warehouse', None, 'GET /api/warehouse/cases/{case_id}', 'case_id', ('warehouse',)),
    'POST /api/warehouse/cases/{case_id}/commands/{action}': _Route('warehouse', 'case_id', 'GET /api/warehouse/cases/{case_id}', 'case_id', ('warehouse',)),
    'POST /api/procurement/orders': _Route('procurement', None, 'GET /api/procurement/orders/{case_id}', 'case_id', ('procurement',)),
    'POST /api/procurement/orders/{case_id}/actions/{action}': _Route('procurement', 'case_id', 'GET /api/procurement/orders/{case_id}', 'case_id', ('procurement',)),
    'POST /api/retail-bundles/sales': _Route('bundle_sale', None, 'GET /api/retail/orders/{key}', 'key', ('retail',)),
    'POST /api/retail/orders': _Route('retail', None, 'GET /api/retail/orders/{key}', 'key', ('retail',)),
    'POST /api/retail/orders/{key}/actions/{action}': _Route('retail', 'key', 'GET /api/retail/orders/{key}', 'key', ('retail',)),
    'POST /api/claims': _Route('claims', None, 'GET /api/claims/{case_id}', 'case_id', ('claim',)),
    'POST /api/claims/{case_id}/actions/{action}': _Route('claims', 'case_id', 'GET /api/claims/{case_id}', 'case_id', ('claim',)),
    'POST /api/rework-extensions/orders/{key}/quote': _Route('rework_quote', 'key', 'GET /api/repair-orders/{case_id}', 'case_id', ('repair',), fixed_action='quote'),
    'POST /api/repair-orders': _Route('repair', None, 'GET /api/repair-orders/{case_id}', 'case_id', ('repair',)),
    'POST /api/repair-orders/{case_id}/actions/{action}': _Route('repair', 'case_id', 'GET /api/repair-orders/{case_id}', 'case_id', ('repair',)),
    'POST /api/vehicle-operations/orders': _Route('vehicle_operation', None, 'GET /api/vehicle-operations/orders/{case_id}', 'case_id', ('vehicle_operations',)),
    'POST /api/vehicle-operations/orders/{case_id}/actions/{action}': _Route('vehicle_operation', 'case_id', 'GET /api/vehicle-operations/orders/{case_id}', 'case_id', ('vehicle_operations',)),
    'POST /api/vehicle-procurement/orders': _Route('vehicle_purchase', None, 'GET /api/vehicle-procurement/orders/{case_id}', 'case_id', ('vehicle_procurement',)),
    'POST /api/vehicle-procurement/orders/{case_id}/actions/{action}': _Route('vehicle_purchase', 'case_id', 'GET /api/vehicle-procurement/orders/{case_id}', 'case_id', ('vehicle_procurement',)),
    'POST /api/aftercare/orders': _Route('aftercare', None, 'GET /api/aftercare/orders/{case_id}', 'case_id', ('aftercare',)),
    'POST /api/aftercare/orders/{case_id}/actions/{action}': _Route('aftercare', 'case_id', 'GET /api/aftercare/orders/{case_id}', 'case_id', ('aftercare',)),
    'POST /api/sales-quotes/orders': _Route('sales', None, 'GET /api/sales-quotes/orders/{key}', 'key', ('order',)),
    'POST /api/sales-quotes/orders/{key}/quotes': _Route('sales', 'key', 'GET /api/sales-quotes/orders/{key}', 'key', ('order',), fixed_action='revise'),
    'POST /api/vehicle-income': _Route('vehicle_income', None, 'GET /api/vehicle-income/{key}', 'key', ('vehicle_income',)),
    'POST /api/vehicle-income/{key}/actions/{action}': _Route('vehicle_income', 'key', 'GET /api/vehicle-income/{key}', 'key', ('vehicle_income',)),
}
OPERATIONS = frozenset(_ROUTES)


@dataclass(frozen=True)
class _Command:
    family: str
    request_key: str
    digest: str
    target: int | None
    action: str
    payload_signature: str
    created_kind: str | None = None


def supports(operation_id):
    return type(operation_id) is str and operation_id in OPERATIONS


def _path(snapshot, route):
    expected = set()
    if route.path_key is not None:
        expected.add(route.path_key)
    if route.path_key is not None and route.fixed_action is None:
        expected.add('action')
    if (snapshot.query or type(snapshot.path_args) is not dict
            or set(snapshot.path_args) != expected or type(snapshot.body) is not dict
            or type(snapshot.request_id) is not str):
        invalid()
    target = snapshot.path_args[route.path_key] if route.path_key else None
    if target is not None and not positive_int(target):
        invalid()
    action = route.fixed_action or (snapshot.path_args['action'] if target else 'create')
    if type(action) is not str:
        invalid()
    return target, action


def _envelope(snapshot, schema):
    native = schema.model_validate(deepcopy(snapshot.body))
    if native.request_id != snapshot.request_id:
        invalid()
    return native


def _values(native, action, schemas, *, mode='python', exclude_none=False):
    schema = schemas.get(action)
    if schema is None:
        invalid()
    return schema.model_validate(native.values).model_dump(mode=mode, exclude_none=exclude_none)


def _json_dates(value):
    """Only the original JSON-default-str families call this normalization."""
    return json.loads(json.dumps(value, default=str, allow_nan=False))


def _native_command(snapshot):
    """Restore each original API envelope before computing its native digest."""
    from .flow_engine import request_digest
    route = _ROUTES.get(snapshot.operation_id)
    if route is None:
        return None
    target, action = _path(snapshot, route)
    family, created_kind = route.family, None
    try:
        if family == 'service':
            from . import service_orders_api as api
            native = _envelope(snapshot, api.Create if target is None else api.Command)
            if target is None:
                payload = native.model_dump(mode='json', exclude={'request_id'})
                created_kind = native.subtype
            else:
                values = _values(native, action, api.SCHEMAS, mode='json')
                payload = {'case_id': target, 'version': native.version, 'values': values}
            digest = request_digest('service_orders_' + action, payload)
        elif family == 'addon':
            from . import addon_api as api
            native = _envelope(snapshot, api.Create if target is None else api.Command)
            if target is None:
                payload = native.model_dump(mode='json', exclude={'request_id'})
            else:
                values = _values(native, action, api.SCHEMAS, mode='json')
                if values.get('member_pricing') is None:
                    values = {key: value for key, value in values.items() if key != 'member_pricing'}
                payload = {'case_id': target, 'version': native.version, 'values': values}
            digest = request_digest('addon_' + action, payload)
        elif family == 'insurance':
            from . import insurance_api as api
            native = _envelope(snapshot, api.Create if target is None else api.Command)
            if target is None:
                payload = native.model_dump(mode='json', exclude={'request_id'})
            else:
                values = _values(native, action, api.SCHEMAS, mode='json')
                payload = {'case_id': target, 'version': native.version, 'values': values}
            digest = request_digest('insurance_' + action, payload)
        elif family == 'claims':
            from . import claims_api as api
            native = _envelope(snapshot, api.Create if target is None else api.Command)
            if target is None:
                payload = native.model_dump(exclude={'request_id'})
            else:
                values = _values(native, action, api.SCHEMAS, mode='json')
                payload = {'case_id': target, 'version': native.version,
                           'source_version': native.source_version, 'values': values}
            digest = request_digest('claims_' + action, payload)
        elif family == 'aftercare':
            from . import aftercare_api as api
            native = _envelope(snapshot, api.Create if target is None else api.Command)
            if target is None:
                payload = native.model_dump(exclude={'request_id'})
            else:
                if any(not key.isdigit() or not positive_int(value)
                       for key, value in native.source_versions.items()):
                    invalid()
                values = _values(native, action, api.SCHEMAS)
                payload = {'id': target, 'version': native.version,
                           'source_versions': native.source_versions, 'values': values}
            digest = request_digest('aftercare_' + action, payload)
        elif family == 'vehicle_income':
            from . import vehicle_income_api as api
            native = _envelope(snapshot, api.Create if target is None else api.Command)
            if target is None:
                payload = native.model_dump(mode='json', exclude={'request_id'})
            else:
                values = _values(native, action, api.SCHEMAS, mode='json')
                payload = {'case_id': target, 'version': native.version, 'values': values}
            digest = request_digest('vehicle_income_' + action, payload)
        elif family == 'batch':
            from . import reconciliation_api as api
            from .reconciliation_service import digest as batch_digest
            native = _envelope(snapshot, api.BatchCreate if target is None else api.Command)
            if target is None:
                values = {'start': native.start, 'end': native.end, 'reason': native.reason}
                payload = {'action': 'batch_create', 'values': values}
            else:
                schemas = {'issue': api.Issue, 'resolve': api.Resolve, 'submit': api.Reason,
                           'seal': api.Proof, 'recalculate': api.Reason, 'reopen': api.Reason}
                values = _values(native, action, schemas)
                payload = {'action': 'batch:' + str(target) + ':' + action,
                           'values': {'version': native.version,
                                      'case_version': native.case_version, 'values': values}}
            digest = batch_digest(payload)
            payload = _json_dates(payload)
        elif family == 'finance':
            from . import business_finance_api as api
            from .business_finance_service import digest as finance_digest
            native = _envelope(snapshot, api.Create if target is None else api.Command)
            if target is None:
                schemas = {'advance': api.Advance, 'advance_apply': api.Apply,
                           'advance_refund': api.Refund, 'statement': api.Statement,
                           'correction': api.Correction, 'stored_correction': api.StoredCorrection,
                           'fee_correction': api.FeeCorrection, 'other_return': api.OtherReturn,
                           'other_return_adjust': api.ReturnAdjustment,
                           'other_return_refund': api.SupplierRefund}
                values = _values(native, native.purpose, schemas, exclude_none=True)
                if (native.purpose in {'correction', 'stored_correction'} and values['amount_cents']
                        and any(key not in values for key in ('account_id', 'reference'))):
                    invalid()
                payload = {'action': 'create', 'values': {'customer_id': native.customer_id,
                           'purpose': native.purpose, 'values': values, 'reason': native.reason}}
            else:
                schemas = {'approve': api.Evidence, 'execute': api.Posting, 'collect': api.Posting,
                           'cancel': api.Reason, 'reject': api.Reason, 'recalculate': api.Reason}
                values = _values(native, action, schemas, exclude_none=True)
                payload = {'action': str(target) + ':' + action,
                           'values': {'version': native.version,
                                      'case_version': native.case_version, 'values': values}}
            digest = finance_digest(payload)
            payload = _json_dates(payload)
        elif family == 'invoice':
            from . import invoice_api as api
            native = _envelope(snapshot, api.Create if target is None else api.Command)
            if target is None:
                payload = native.model_dump(exclude={'request_id'})
            else:
                schemas = {'approve': api.Proof, 'reject': api.Reason, 'cancel': api.Reason,
                           'submit': api.Submit, 'failure': api.Proof, 'difference': api.Difference,
                           'record': api.Actual, 'review_result': api.Proof}
                values = _values(native, action, schemas)
                values = {key: value.isoformat() if isinstance(value, date) else value
                          for key, value in values.items()}
                payload = {'id': target, 'version': native.version,
                           'source_version': native.source_version, 'values': values}
            payload = {key: value.isoformat() if isinstance(value, date) else value
                       for key, value in payload.items()}
            digest = request_digest('invoice_v3_' + action, payload)
        elif family == 'warehouse':
            from . import warehouse_api as api
            from .warehouse_service import digest as warehouse_digest
            native = _envelope(snapshot, api.Create if target is None else api.Envelope)
            if target is None:
                payload = native.model_dump(exclude={'request_id'})
            else:
                values = _values(native, action, api.SCHEMAS)
                payload = {'id': target, 'version': native.version, **values}
            digest = warehouse_digest('warehouse_' + action, payload)
            payload = _json_dates(payload)
        elif family == 'procurement':
            from . import procurement_api as api
            native = _envelope(snapshot, api.Create if target is None else api.Command)
            if target is None:
                payload = native.model_dump(exclude={'request_id'})
            else:
                if action == 'prepay_pay' and native.values.get('confirmed') is not True:
                    invalid()
                values = _values(native, action, api.SCHEMAS)
                payload = {'case_id': target, 'version': native.version, 'values': values}
            payload = _json_dates(payload)
            digest = request_digest('procurement_' + action, payload)
        elif family == 'retail':
            from . import retail_api as api
            native = _envelope(snapshot, api.Create if target is None else api.Command)
            if target is None:
                payload = native.model_dump(exclude={'request_id'})
                if payload.get('member_pricing') is None:
                    payload = {key: value for key, value in payload.items() if key != 'member_pricing'}
            else:
                values = _values(native, action, api.SCHEMAS)
                payload = {'case_id': target, 'version': native.version, 'values': values}
            digest = request_digest('retail_' + action, payload)
        elif family == 'bundle_sale':
            from .retail_bundle_api import Sale
            native = _envelope(snapshot, Sale)
            payload = native.model_dump(exclude={'request_id'})
            if payload.get('member_pricing') is None:
                payload = {key: value for key, value in payload.items() if key != 'member_pricing'}
            digest = request_digest('retail_bundle_create', payload)
        elif family == 'repair':
            from . import repair_api as api
            native = _envelope(snapshot, api.Create if target is None else api.Command)
            if target is None:
                payload = native.model_dump(mode='json', exclude={'request_id'})
            else:
                values = _values(native, action, api.SCHEMAS, mode='json')
                if values.get('member_pricing') is None:
                    values = {key: value for key, value in values.items() if key != 'member_pricing'}
                payload = {'id': target, 'version': native.version, 'values': values}
            digest = request_digest('repair_v3_' + action, payload)
        elif family == 'package_quote':
            from .repair_package_api import Command, PackageQuote
            native = _envelope(snapshot, Command)
            values = PackageQuote.model_validate(native.values).model_dump(mode='json')
            for line in values['lines']:
                if bool(line.get('package_lot_id')) != bool(line.get('package_lot_version')):
                    invalid()
                for key in ('charge_scope', 'source_line_id'):
                    if line.get(key) is None:
                        line.pop(key, None)
            if values.get('member_pricing') is None:
                values = {key: value for key, value in values.items() if key != 'member_pricing'}
            payload = {'id': target, 'version': native.version, 'values': values}
            digest = request_digest('repair_v3_quote', payload)
        elif family == 'rework_quote':
            from .rework_extension_api import Command, ScopeQuote
            native = _envelope(snapshot, Command)
            values = ScopeQuote.model_validate(native.values).model_dump(mode='json')
            if values.get('member_pricing') is None:
                values = {key: value for key, value in values.items() if key != 'member_pricing'}
            payload = {'id': target, 'version': native.version, 'values': values}
            digest = request_digest('repair_v3_quote', payload)
        elif family == 'vehicle_operation':
            from . import vehicle_operations_api as api
            native = _envelope(snapshot, api.Create if target is None else api.Command)
            if target is None:
                payload = native.model_dump(exclude={'request_id'})
            else:
                values = _values(native, action, api.SCHEMAS)
                payload = {'case_id': target, 'version': native.version, **values}
            payload = _json_dates(payload)
            digest = request_digest('vehicle_operation_' + action, payload)
        elif family == 'vehicle_purchase':
            from . import vehicle_procurement_api as api
            native = _envelope(snapshot, api.Create if target is None else api.Command)
            if target is None:
                payload = native.model_dump(exclude={'request_id'})
            else:
                values = _values(native, action, api.SCHEMAS)
                payload = {'case_id': target, 'version': native.version, **values}
            payload = _json_dates(payload)
            digest = request_digest('vehicle_purchase_' + action, payload)
        elif family == 'sales':
            from . import sales_quote_api as api
            native = _envelope(snapshot, api.Create if target is None else api.Revise)
            if target is None:
                payload = native.model_dump(mode='json', exclude={
                    'request_id', 'customer_name', 'customer_phone', 'confirm_new_customer'})
                if not native.customer_id or native.customer_name or native.customer_phone or native.confirm_new_customer:
                    payload.update(customer_name=native.customer_name, customer_phone=native.customer_phone,
                                   confirm_new_customer=native.confirm_new_customer)
                digest = request_digest('sales_quote_create', payload)
            else:
                payload = {'version': native.version, 'quote': native.quote.model_dump(mode='json')}
                digest = request_digest('sales_quote_propose:' + str(target), payload)
        else:
            invalid()
        return _Command(family, native.request_id, digest, target, action,
                        json_signature(payload), created_kind)
    except (ValueError, TypeError, OverflowError, RecursionError, KeyError):
        invalid()


def _receipt_model(family):
    # Fixed original classes, with no table-name reflection or arbitrary SQL.
    if family == 'service':
        from .service_orders_models import ServiceRequest
        return ServiceRequest
    if family == 'addon':
        from .addon_models import AddonReceipt
        return AddonReceipt
    if family == 'insurance':
        from .insurance_models import InsuranceRequest
        return InsuranceRequest
    if family == 'claims':
        from .claims_models import ClaimReceipt
        return ClaimReceipt
    if family == 'aftercare':
        from .aftercare_models import AftercareReceipt
        return AftercareReceipt
    if family == 'batch':
        from .reconciliation_models import ReconciliationReceipt
        return ReconciliationReceipt
    if family == 'finance':
        from .business_finance_models import FinanceReceipt
        return FinanceReceipt
    if family == 'vehicle_income':
        from .vehicle_income_models import VehicleIncomeReceipt
        return VehicleIncomeReceipt
    if family in {'invoice', 'warehouse', 'procurement', 'bundle_sale', 'retail',
                  'repair', 'package_quote', 'rework_quote', 'vehicle_operation',
                  'vehicle_purchase', 'sales'}:
        from .flow_models import RequestReceipt
        return RequestReceipt
    invalid()


def _scope(db, user, snapshot):
    from .business_assistant_service import require_preparation_read_phase
    from .tenancy import single_store
    require_preparation_read_phase(db)
    if (not positive_int(snapshot.actor_id) or not positive_int(snapshot.store_id)
            or user.id != snapshot.actor_id or single_store(db) != snapshot.store_id):
        raise HTTPException(404, '当前无法读取原提交回执')


def _rows(db, command, snapshot):
    model = _receipt_model(command.family)
    with db.no_autoflush:
        return list(db.scalars(select(model).where(model.store_id == snapshot.store_id,
            model.request_key == command.request_key).order_by(model.id)
            .execution_options(populate_existing=True)))


def _row_signature(row, family):
    base = (row.id, row.store_id, row.actor_id, row.request_key, row.digest)
    if family in {'invoice', 'warehouse', 'procurement', 'bundle_sale', 'retail',
                  'repair', 'package_quote', 'rework_quote', 'vehicle_operation',
                  'vehicle_purchase', 'sales'}:
        return (*base, row.case_id, row.created_at.isoformat() if row.created_at else None)
    source = json_signature(row.result)
    if family in {'insurance', 'vehicle_income'}:
        return (*base, source, row.created_at.isoformat() if row.created_at else None)
    return (*base, source)


def _pointer_source(db, command, snapshot):
    # A finance re-calculation points to a prior Statement.id, not prior Case.id.
    # This one original immutable relation is read in the same scoped snapshot
    # and retained in the central before/after signature.
    if command.family != 'finance' or command.action != 'recalculate':
        return ()
    from .business_finance_models import FinanceStatement
    with db.no_autoflush:
        rows = list(db.scalars(select(FinanceStatement).where(
            FinanceStatement.store_id == snapshot.store_id,
            FinanceStatement.case_id == command.target).order_by(FinanceStatement.id)
            .execution_options(populate_existing=True)))
        return tuple((row.id, row.store_id, row.case_id, row.customer_id,
                      row.starts_on.isoformat(), row.ends_on.isoformat(),
                      row.revision, row.previous_id, row.digest) for row in rows)


def read_source(db, user, snapshot):
    if not supports(snapshot.operation_id):
        return ()
    _scope(db, user, snapshot)
    command = _native_command(snapshot)
    rows = _rows(db, command, snapshot)
    return (command.family, command.request_key, command.digest, command.target,
            command.action, command.payload_signature, command.created_kind,
            tuple(_row_signature(row, command.family) for row in rows),
            _pointer_source(db, command, snapshot))


def read_operations(snapshot):
    route = _ROUTES.get(snapshot.operation_id)
    if route is None:
        return ()
    # The dedicated GET enforces the current family's role/row guard. Flow
    # additionally supplies the actual Case/store/kind when compact GETs omit it.
    return ((route.read_operation,) if route.object_type == 'reconciliation_batch'
            else (route.read_operation, _FLOW_READ))


def _allows_successor(command):
    return ((command.family == 'batch' and command.action in {'recalculate', 'reopen'})
            or (command.family == 'finance' and command.action == 'recalculate'))


def _receipt_result(row, command):
    """Copy only the exact native result; never expose its financial body."""
    if command.family in {'invoice', 'warehouse', 'procurement', 'bundle_sale', 'retail',
                          'repair', 'package_quote', 'rework_quote', 'vehicle_operation',
                          'vehicle_purchase', 'sales'}:
        return row.case_id, None
    data = deepcopy(row.result)
    json_signature(data)
    if type(data) is not dict:
        invalid()
    if command.family == 'finance':
        case = data.get('case')
        if type(case) is not dict:
            invalid()
        return case.get('id'), data
    return data.get('id'), data


async def lookup_visible(db, user, snapshot, native_reader):
    if not supports(snapshot.operation_id):
        return result('unsupported', 'receipt_family_not_registered')
    _scope(db, user, snapshot)
    try:
        command = _native_command(snapshot)
        rows = _rows(db, command, snapshot)
        if not rows:
            return result('not_found', 'native_receipt_not_found')
        if len(rows) != 1:
            return result('mismatch', 'ambiguous_native_receipt')
        receipt = rows[0]
        if (not positive_int(receipt.id) or receipt.actor_id != snapshot.actor_id
                or not positive_int(receipt.actor_id) or not positive_int(receipt.store_id)
                or receipt.store_id != snapshot.store_id
                or receipt.request_key != command.request_key
                or not digest_matches(receipt.digest, command.digest)):
            return result('mismatch', 'native_receipt_mismatch')
        object_id, original_result = _receipt_result(receipt, command)
        if (not positive_int(object_id) or command.target is not None
                and not _allows_successor(command) and object_id != command.target):
            return result('mismatch', 'native_result_target_mismatch')
        receipt_id = receipt.id
        previous_id = original_result.get('previous_id') if command.family == 'batch' else None
        statement_id = None
        if command.family == 'finance' and command.action == 'recalculate':
            pointers = _pointer_source(db, command, snapshot)
            statement = original_result.get('statement')
            if (len(pointers) != 1 or not positive_int(pointers[0][0])
                    or pointers[0][1:3] != (snapshot.store_id, command.target)
                    or object_id == command.target or type(statement) is not dict
                    or not positive_int(statement.get('id')) or statement.get('case_id') != object_id
                    or not positive_int(statement.get('previous_id'))
                    or statement['previous_id'] != pointers[0][0]):
                return result('mismatch', 'native_successor_mismatch')
            previous_id, statement_id = pointers[0][0], statement['id']
            del pointers, statement
        # No ORM object or shared result dict may be consulted after the await.
        del receipt, rows, original_result
        route = _ROUTES[snapshot.operation_id]
        data = await native_get(db, native_reader, route.read_operation,
                                path_args={route.read_key: object_id})
        if route.object_type == 'reconciliation_batch':
            if (not positive_int(data.get('id')) or data['id'] != object_id
                    or not positive_int(data.get('store_id')) or data['store_id'] != snapshot.store_id
                    or not positive_int(data.get('case_id')) or 'version' not in data
                    or data['version'] is not None and not positive_int(data['version'])):
                return result('mismatch', 'native_object_mismatch')
            if (command.target is not None and _allows_successor(command)
                    and (object_id == command.target or not positive_int(data.get('previous_id'))
                         or data['previous_id'] != command.target or not positive_int(previous_id)
                         or previous_id != command.target)):
                return result('mismatch', 'native_successor_mismatch')
            return success(snapshot, receipt_id, [('reconciliation_batch', object_id, data['version'])])
        case_data = data.get('case') if command.family == 'finance' else data
        if (type(case_data) is not dict or not positive_int(case_data.get('id'))
                or case_data['id'] != object_id or 'version' not in case_data
                or case_data['version'] is not None and not positive_int(case_data['version'])
                or 'store_id' in case_data and (not positive_int(case_data['store_id'])
                    or case_data['store_id'] != snapshot.store_id)):
            return result('mismatch', 'native_object_mismatch')
        if statement_id is not None:
            statement = data.get('statement')
            if (type(statement) is not dict or not positive_int(statement.get('id'))
                    or statement['id'] != statement_id or not positive_int(statement.get('case_id'))
                    or statement['case_id'] != object_id or not positive_int(statement.get('previous_id'))
                    or statement['previous_id'] != previous_id):
                return result('mismatch', 'native_successor_mismatch')
            del statement
        version = case_data['version']
        del data, case_data
        original = await native_get(db, native_reader, _FLOW_READ, path_args={'case_id': object_id})
        if (not positive_int(original.get('id')) or original['id'] != object_id
                or not positive_int(original.get('store_id')) or original['store_id'] != snapshot.store_id
                or original.get('kind') not in route.kinds
                or command.created_kind is not None and original.get('kind') != command.created_kind
                or 'version' not in original
                or original['version'] is not None and not positive_int(original['version'])):
            return result('mismatch', 'native_object_mismatch')
        if version is not None and original['version'] is not None and version != original['version']:
            return result('mismatch', 'native_object_changed_during_read')
        # The receipt is a historical command result. A later legal Case version
        # does not have to equal the submitted expected_version or old JSON body.
        return success(snapshot, receipt_id, [('case', object_id, original['version'])])
    except HTTPException as exc:
        if exc.status_code in {401, 403, 404}:
            return result('inaccessible', 'native_object_not_accessible')
        if exc.status_code == 409:
            return result('mismatch', 'invalid_native_submission_or_result')
        raise
    except (ValueError, TypeError, OverflowError, RecursionError, KeyError, AttributeError):
        return result('mismatch', 'invalid_native_submission_or_result')


def validate_lookup(snapshot, lookup):
    if not supports(snapshot.operation_id):
        return False
    try:
        command = _native_command(snapshot)
        route = _ROUTES[snapshot.operation_id]
        if not validate_evidence(snapshot, lookup, {route.object_type}, min_objects=1, max_objects=1):
            return False
        if command.target is not None and not _allows_successor(command):
            return lookup.object_refs[0].id == command.target
        return True
    except (HTTPException, ValueError, TypeError, OverflowError, RecursionError, KeyError, AttributeError):
        return False


__all__ = ['OPERATIONS', 'supports', 'read_source', 'read_operations', 'lookup_visible', 'validate_lookup']
