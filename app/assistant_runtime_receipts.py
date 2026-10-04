"""Freeze employee confirmations and read exact native receipts.

The caller owns the transaction and authorization of the original proposal.
Freeze/lookup helpers never flush, commit, submit business, or create a Run.
Receipt lookup optionally uses an injected, authorized GET-only native reader;
it never submits business or reconciles assistant states. Lookup accepts only
an owned proposal ID, not a client-provided actor, request key or snapshot.
The separately named reconciliation coordinator may save an already-proven
native success, under a short fenced Run or narrowly scoped Grant transaction.
"""
from copy import deepcopy
from dataclasses import dataclass
import hmac
import re
from time import monotonic
from uuid import uuid4
from weakref import WeakKeyDictionary, ref

from fastapi import HTTPException
from sqlalchemy import select

from .assistant_runtime_models import RunItem, WorkItem
from .assistant_runtime_schemas import (
    BusinessObjectRef, EvidenceRef, NativeReceiptRef, ReceiptLookup,
    SubmissionSnapshot, submission_snapshot_digest,
)


def _conflict():
    raise HTTPException(409, '确认提交内容不一致或记录不完整，请先核对原业务结果') from None


def _snapshot(proposal, execution, confirmed_at):
    if type(execution) is not dict or set(execution) != {'path_args', 'query', 'body'}:
        _conflict()
    body = execution['body']
    values = {
        'operation_id': proposal.operation_id,
        'path_args': deepcopy(execution['path_args']),
        'query': deepcopy(execution['query']),
        'body': deepcopy(body),
        'request_id': body.get('request_id') if type(body) is dict else None,
        'actor_id': proposal.owner_id,
        'store_id': proposal.store_id,
        'role': proposal.owner_role,
        'access_version': proposal.access_version,
        'confirmed_at': confirmed_at,
    }
    try:
        return SubmissionSnapshot.model_validate(values)
    except (ValueError, TypeError, OverflowError, RecursionError):
        _conflict()


def _checked_snapshot(item):
    if not isinstance(item, RunItem) or item.kind != 'confirmation' or item.proposal_id is None:
        _conflict()
    try:
        snapshot = SubmissionSnapshot.model_validate(deepcopy(item.submission_snapshot))
        digest = submission_snapshot_digest(snapshot)
        stored = item.submission_digest
        if (type(stored) is not str or len(stored) != 64
                or any(character not in '0123456789abcdef' for character in stored)
                or not hmac.compare_digest(digest, stored)):
            _conflict()
    except (ValueError, TypeError, OverflowError, RecursionError):
        _conflict()
    return snapshot


def _proposal_identity(proposal):
    return (proposal.operation_id, proposal.owner_id, proposal.store_id,
            proposal.owner_role, proposal.access_version)


def freeze_confirmation(db, user, proposal, execution, confirmed_at):
    """Return (confirmation item, created); an existing item is never rewritten.

    The caller must commit a new item together with Proposal.status=executing
    before sending the native request. created=False does not authorize replay.
    """
    if ((proposal.owner_id, proposal.owner_role, proposal.access_version)
            != (user.id, user.role, user.access_version)):
        raise HTTPException(409, '账号或岗位已变化，请重新核对这项操作')

    # Even the SELECTs must not implicitly flush caller-owned proposal changes.
    with db.no_autoflush:
        source_id = proposal.source_work_item_id
        if source_id is not None:
            work = db.scalar(select(WorkItem).where(WorkItem.id == source_id))
            if (work is None or work in db.deleted or work.item_kind != 'prepare'
                    or work.operation_id != proposal.operation_id
                    or (work.owner_id, work.store_id, work.session_id)
                    != (proposal.owner_id, proposal.store_id, proposal.session_id)):
                _conflict()
        existing = list(db.scalars(select(RunItem).where(
            RunItem.kind == 'confirmation', RunItem.proposal_id == proposal.id)))
        # Repeated use inside one caller-owned transaction must also find an
        # item added above the database boundary but not flushed yet.
        for item in db.new:
            if (isinstance(item, RunItem) and item.kind == 'confirmation'
                    and item.proposal_id == proposal.id
                    and all(item is not other for other in existing)):
                existing.append(item)
        if len(existing) > 1:
            _conflict()
        if existing:
            item = existing[0]
            if item in db.deleted or item.work_item_id != source_id:
                _conflict()
            stored = _checked_snapshot(item)
            if ((stored.operation_id, stored.actor_id, stored.store_id,
                 stored.role, stored.access_version) != _proposal_identity(proposal)):
                _conflict()
            # The original confirmation time is part of the immutable envelope.
            # A later duplicate click must not introduce a new timestamp/digest.
            current = _snapshot(proposal, execution, stored.confirmed_at)
            if not hmac.compare_digest(submission_snapshot_digest(current), item.submission_digest):
                _conflict()
            return item, False

        snapshot = _snapshot(proposal, execution, confirmed_at)
        item = RunItem(
            id=str(uuid4()), run_id=None, work_item_id=source_id,
            proposal_id=proposal.id, kind='confirmation',
            item_key='confirmation:' + proposal.id, attempt_no=1,
            status='running', started_at=confirmed_at, created_at=confirmed_at,
            submission_snapshot=snapshot.model_dump(mode='json'),
            submission_digest=submission_snapshot_digest(snapshot), version=1,
        )
        db.add(item)
        return item, True


def frozen_payload(item):
    """Return detached native arguments only after rechecking the frozen digest."""
    snapshot = _checked_snapshot(item)
    return {
        'operation_id': snapshot.operation_id,
        'path_args': deepcopy(snapshot.path_args),
        'query': deepcopy(snapshot.query),
        'body': deepcopy(snapshot.body),
    }


_FLOW_CREATE = 'POST /api/flow/cases'
_FLOW_ACTION = 'POST /api/flow/cases/{case_id}/actions/{action}'
_FLOW_READ = 'GET /api/flow/cases/{case_id}'
_FLOW_RECEIPT_OPERATIONS = frozenset({_FLOW_CREATE, _FLOW_ACTION})


def _native_family(operation_id):
    """Select only the fixed, server-reviewed native operation templates."""
    from . import assistant_runtime_receipts_commercial as commercial
    from . import assistant_runtime_receipts_care as care
    from . import assistant_runtime_receipts_inventory as inventory
    matches = [family for family in (commercial, care, inventory)
               if family.supports(operation_id)]
    if len(matches) > 1:
        _conflict()
    return matches[0] if matches else None


def _receipt_read_operations(snapshot):
    family = _native_family(snapshot.operation_id)
    operations = family.read_operations(snapshot) if family else (
        (_FLOW_READ,) if snapshot.operation_id in _FLOW_RECEIPT_OPERATIONS else ())
    if (type(operations) is not tuple or len(set(operations)) != len(operations)
            or any(type(operation) is not str or not operation.startswith('GET ')
                   for operation in operations)):
        _conflict()
    return operations


def validate_success_lookup(snapshot, lookup):
    """Validate a finite family's recovery evidence without querying or writing."""
    from .assistant_runtime_receipts_common import validate_evidence
    family = _native_family(snapshot.operation_id)
    if family is not None:
        return family.validate_lookup(snapshot, lookup)
    if snapshot.operation_id not in _FLOW_RECEIPT_OPERATIONS:
        return False
    if not validate_evidence(snapshot, lookup, ('case',), min_objects=1, max_objects=1):
        return False
    try:
        command = _flow_submission(snapshot)
    except (HTTPException, ValueError, TypeError):
        return False
    return (command is not None and (command.target_case_id is None
            or lookup.object_refs[0].id == command.target_case_id))


@dataclass(frozen=True)
class _FlowSubmission:
    request_key: str
    digest: str
    target_case_id: int | None
    created_kind: str | None


def _flow_submission(snapshot):
    """Pure native digest reconstruction, including native schema defaults.

    The API hashes model_dump(), not the gateway's exclude_unset body. In
    particular an omitted values field must hash as the native default {}.
    Never reuse the assistant proposal/submission digest as a native receipt key.
    """
    if snapshot.operation_id not in _FLOW_RECEIPT_OPERATIONS:
        return None
    from .flow_api import ActionInput, CreateInput
    from .flow_engine import request_digest
    if snapshot.query or snapshot.body is None or snapshot.request_id is None:
        _conflict()
    try:
        if snapshot.operation_id == _FLOW_CREATE:
            if snapshot.path_args:
                _conflict()
            native = CreateInput.model_validate(deepcopy(snapshot.body))
            operation = 'create'
            target = None
            kind = native.kind
        else:
            if set(snapshot.path_args) != {'case_id', 'action'}:
                _conflict()
            target = snapshot.path_args['case_id']
            action = snapshot.path_args['action']
            if (type(target) is not int or target < 1 or type(action) is not str
                    or not re.fullmatch(r'[A-Za-z0-9_.-]+', action) or '..' in action):
                _conflict()
            native = ActionInput.model_validate(deepcopy(snapshot.body))
            operation = f'{target}:{action}'
            kind = None
        if native.request_id != snapshot.request_id:
            _conflict()
        digest = request_digest(operation, native.model_dump(exclude={'request_id'}))
    except (ValueError, TypeError, OverflowError, RecursionError):
        _conflict()
    return _FlowSubmission(native.request_id, digest, target, kind)


def _lookup_result(status, reason_code=None, *, objects=None, evidence=None, checked_at=None):
    from .db import utcnow
    return ReceiptLookup(status=status, checked_at=checked_at or utcnow(),
                         object_refs=objects or [], evidence_refs=evidence or [],
                         reason_code=reason_code)


def _owned_lookup_context(db, user, session_id, proposal_id):
    """Check the original identity and project its actual current account."""
    from .business_assistant_models import AssistantProposal
    from .business_assistant_service import owned_session
    from .models import Store, User
    from .tenancy import RequestPrincipal, role_for_store, single_store
    user = _lookup_identity(user)
    store_id = single_store(db)
    scope = db.info.get('store_scope')
    if (type(store_id) is not int or store_id < 1 or type(scope) not in (tuple, list)
            or any(type(value) is not int or value < 0 for value in scope)
            or {value for value in scope if value > 0} != {store_id}
            or db.info.get('aggregate_scope') or getattr(user, '_aggregate_scope', False)):
        raise HTTPException(404, '当前无法核对这项操作')
    thread = owned_session(db, user, session_id)
    enabled_store = db.scalar(select(Store.id).where(
        Store.id == thread.store_id, Store.active.is_(True)))
    # A RuntimePrincipal deliberately is not an ORM account. Membership checks
    # must use the real current account rather than inventing active/role flags.
    account = db.scalar(select(User).where(User.id == user.id)
                        .execution_options(populate_existing=True))
    if (enabled_store is None or account is None or not account.active or account.must_change_password
            or account.access_version != user.access_version
            or role_for_store(db, account, thread.store_id) != user.role):
        raise HTTPException(404, '当前无法核对这项操作')
    proposal = db.scalar(select(AssistantProposal).where(
        AssistantProposal.id == proposal_id, AssistantProposal.session_id == thread.id,
        AssistantProposal.owner_id == user.id, AssistantProposal.store_id == thread.store_id,
        AssistantProposal.owner_role == user.role, AssistantProposal.access_version == user.access_version))
    if proposal is None:
        raise HTTPException(404, '当前无法核对这项操作')
    native_user = RequestPrincipal(account, user.role, id=user.id,
        access_version=user.access_version, _active_store_id=store_id,
        _aggregate_scope=False)
    return proposal, native_user


def _owned_lookup_proposal(db, user, session_id, proposal_id):
    """The already authenticated employee must still own this store/session."""
    return _owned_lookup_context(db, user, session_id, proposal_id)[0]


async def _visible_flow_case(db, user, case_id, native_reader):
    if native_reader is None:
        # Reuse exactly the original scoped read guard; no management identity,
        # direct unscoped Case lookup, or speculative write to probe visibility.
        from .flow_engine import get_case
        row = get_case(db, user, case_id)
        return {'id': row.id, 'store_id': row.store_id, 'kind': row.kind, 'version': row.version}
    # Only server code may inject this callable. M3.4 supplies a reader bound to
    # a revalidated principal; this is never a model-selected operation/URL.
    response = await native_reader(_FLOW_READ, path_args={'case_id': case_id}, query={}, body=None)
    if type(response) is not dict or type(response.get('status')) is not int:
        raise HTTPException(503, '原业务核对暂时不可用，请稍后再查')
    status = response['status']
    if status in {401, 403, 404}:
        raise HTTPException(404, '当前无法读取原业务记录')
    if not 200 <= status < 300 or type(response.get('data')) is not dict:
        raise HTTPException(503, '原业务核对暂时不可用，请稍后再查')
    data = response['data']
    return {key: data.get(key) for key in ('id', 'store_id', 'kind', 'version')}


async def _lookup_receipt_once(db, user, session_id, proposal_id, *, native_reader=None):
    """Read a receipt using the server's exact, durable confirmation only.

    Caller authenticates login/grant before entry and revalidates it before
    exposure. There is no HTTP route or background identity bypass here. The
    optional native_reader is the internal async GET transport, returning the
    gateway's {status, data} envelope; the default uses the original scoped
    get_case guard. Database/transport failures remain errors, not fake absence.

    confirmed_success proves that this original command committed. It does not
    prove payment, delivery, signatures, or other later completion conditions.
    Every result leaves Proposal, WorkItem and RunItem unchanged, including a
    previously recorded native success for an unsupported receipt family.
    """
    from .business_assistant_service import require_preparation_read_phase
    from .db import utcnow
    from .flow_models import RequestReceipt
    # A read helper cannot let a native reader commit unsaved assistant work.
    require_preparation_read_phase(db)
    with db.no_autoflush:
        try:
            proposal, native_user = _owned_lookup_context(db, user, session_id, proposal_id)
        except HTTPException as exc:
            if exc.status_code in {401, 403, 404, 409}:
                return _lookup_result('inaccessible', 'proposal_not_accessible')
            raise
        confirmations = list(db.scalars(select(RunItem).where(
            RunItem.kind == 'confirmation', RunItem.proposal_id == proposal.id)))
        if not confirmations:
            return _lookup_result('unsupported', 'missing_submission_snapshot')
        if len(confirmations) != 1:
            return _lookup_result('mismatch', 'ambiguous_confirmation')
        item = confirmations[0]
        try:
            snapshot = _checked_snapshot(item)
        except HTTPException:
            return _lookup_result('mismatch', 'invalid_submission_snapshot')
        if ((snapshot.operation_id, snapshot.actor_id, snapshot.store_id, snapshot.role,
             snapshot.access_version) != _proposal_identity(proposal)
                or item.work_item_id != proposal.source_work_item_id
                or proposal.status not in {'executing', 'uncertain', 'succeeded', 'failed'}):
            return _lookup_result('mismatch', 'confirmation_identity_mismatch')
        if item.work_item_id is not None:
            work = db.scalar(select(WorkItem).where(WorkItem.id == item.work_item_id))
            if (work is None or work.item_kind != 'prepare' or work.operation_id != proposal.operation_id
                    or (work.owner_id, work.store_id, work.session_id)
                    != (proposal.owner_id, proposal.store_id, proposal.session_id)):
                return _lookup_result('mismatch', 'confirmation_source_mismatch')
        family = _native_family(snapshot.operation_id)
        if family is not None:
            try:
                found = await family.lookup_visible(db, native_user, snapshot, native_reader)
                found = ReceiptLookup.model_validate(found)
                _owned_lookup_proposal(db, user, session_id, proposal_id)
            except HTTPException as exc:
                if exc.status_code in {401, 403, 404}:
                    return _lookup_result('inaccessible', 'native_object_not_accessible')
                if exc.status_code == 409:
                    return _lookup_result('mismatch', 'invalid_native_submission')
                raise
            if found.status == 'confirmed_success' and not validate_success_lookup(snapshot, found):
                return _lookup_result('mismatch', 'native_object_mismatch')
            return found
        try:
            command = _flow_submission(snapshot)
        except HTTPException:
            return _lookup_result('mismatch', 'invalid_native_submission')
        if command is None:
            return _lookup_result('unsupported', 'receipt_family_not_registered')
        receipt = db.scalar(select(RequestReceipt).where(
            RequestReceipt.store_id == snapshot.store_id,
            RequestReceipt.request_key == command.request_key))
        if receipt is None:
            return _lookup_result('not_found', 'native_receipt_not_found')
        if (receipt.actor_id != snapshot.actor_id or type(receipt.digest) is not str
                or len(receipt.digest) != 64 or any(value not in '0123456789abcdef' for value in receipt.digest)
                or not hmac.compare_digest(receipt.digest, command.digest)
                or type(receipt.id) is not int or receipt.id < 1
                or type(receipt.case_id) is not int or receipt.case_id < 1
                or command.target_case_id is not None and receipt.case_id != command.target_case_id):
            return _lookup_result('mismatch', 'native_receipt_mismatch')
        # End this read snapshot before awaiting the original GET. All values
        # needed below are immutable DTOs/scalars; the wrapper rechecks the
        # exact confirmation/receipt source from a new committed snapshot.
        receipt_id, case_id = receipt.id, receipt.case_id
        db.rollback()
        try:
            case = await _visible_flow_case(db, user, case_id, native_reader)
            # No cached conversation/snapshot is returned after access changes.
            _owned_lookup_proposal(db, user, session_id, proposal_id)
        except HTTPException as exc:
            if exc.status_code in {401, 403, 404, 409}:
                return _lookup_result('inaccessible', 'native_object_not_accessible')
            raise
        if (type(case['id']) is not int or case['id'] != case_id
                or type(case['store_id']) is not int or case['store_id'] != snapshot.store_id
                or type(case['kind']) is not str
                or command.created_kind is not None and case['kind'] != command.created_kind
                or case['version'] is not None and (type(case['version']) is not int or case['version'] < 1)):
            return _lookup_result('mismatch', 'native_object_mismatch')
        checked_at = utcnow()
        ref = BusinessObjectRef(type='case', id=case_id)
        evidence = [
            EvidenceRef(source_type='receipt', source_id=NativeReceiptRef(
                operation_id=snapshot.operation_id, id=receipt_id), native_version=None, observed_at=checked_at),
            EvidenceRef(source_type='object', source_id=ref,
                        native_version=case['version'], observed_at=checked_at),
        ]
        return _lookup_result('confirmed_success', objects=[ref], evidence=evidence, checked_at=checked_at)


def _lookup_source(db, user, session_id, proposal_id):
    """Private source signature; never expose the frozen body or old result."""
    from .flow_models import RequestReceipt
    user = _lookup_identity(user)
    proposal, native_user = _owned_lookup_context(db, user, session_id, proposal_id)
    db.refresh(proposal)
    items = list(db.scalars(select(RunItem).where(RunItem.kind == 'confirmation',
        RunItem.proposal_id == proposal.id).execution_options(populate_existing=True)))
    work = (db.scalar(select(WorkItem).where(WorkItem.id == proposal.source_work_item_id)
            .execution_options(populate_existing=True)) if proposal.source_work_item_id else None)
    receipts = []
    native_source = None
    if len(items) == 1:
        try:
            submission = _checked_snapshot(items[0])
            family = _native_family(submission.operation_id)
            if family is not None:
                native_source = (family.__name__, family.read_source(db, native_user, submission))
                command = None
            else:
                command = _flow_submission(submission)
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
            native_source = ('invalid_native_submission',)
            command = None
        if command is not None:
            receipts = list(db.scalars(select(RequestReceipt).where(
                RequestReceipt.store_id == proposal.store_id,
                RequestReceipt.request_key == command.request_key).execution_options(populate_existing=True)))
    return (proposal.version, proposal.status, proposal.digest, proposal.source_work_item_id,
        tuple((item.id, item.version, item.status, item.work_item_id, item.submission_digest)
              for item in items), (work.id, work.version) if work else None,
        native_source if native_source is not None else tuple(
            (row.id, row.store_id, row.actor_id, row.request_key, row.digest, row.case_id)
            for row in receipts))


def _lookup_identity(user, store_id=None):
    """Pin request identity before an ORM refresh/rollback can change its account.

    Keep the existing read projection and real account; do not invent enabled
    account flags or let delegated access_version change during this lookup.
    Every original ownership check still reloads and checks the actual account.
    """
    from .tenancy import RequestPrincipal
    return RequestPrincipal(user, user.role, id=user.id, access_version=user.access_version,
        _aggregate_scope=getattr(user, '_aggregate_scope', False),
        _active_store_id=store_id if store_id is not None else getattr(user, '_active_store_id', None))


async def lookup_receipt(db, user, session_id, proposal_id, *, native_reader=None):
    """Read only; independently recheck source/authority after an awaited GET."""
    from .assistant_runtime_principal import _reader
    from .business_assistant_service import require_preparation_read_phase
    from .tenancy import set_scope, single_store
    require_preparation_read_phase(db)
    user = _lookup_identity(user)
    try:
        store_id = single_store(db)
    except HTTPException as exc:
        if exc.status_code == 409:
            return _lookup_result('inaccessible', 'proposal_not_accessible')
        raise
    if user._active_store_id not in {None, store_id}:
        return _lookup_result('inaccessible', 'proposal_not_accessible')
    user = _lookup_identity(user, store_id)
    try:
        before = _lookup_source(db, user, session_id, proposal_id)
        result = await _lookup_receipt_once(db, user, session_id, proposal_id, native_reader=native_reader)
        db.rollback()
        with _reader(db) as fresh:
            set_scope(fresh, [store_id], store_id)
            after = _lookup_source(fresh, user, session_id, proposal_id)
        if after != before:
            return _lookup_result('mismatch', 'confirmation_source_changed')
        return result
    except HTTPException as exc:
        if exc.status_code in {401, 403, 404}:
            return _lookup_result('inaccessible', 'proposal_not_accessible')
        raise
    finally:
        # The entry guard prohibited pending caller writes. Close read-only
        # snapshots on every result/error, including absent/unsupported receipts.
        db.rollback()


def _reconciliation_record(proposal, item):
    """Validate a stored observation, never use it as a replacement receipt."""
    result = proposal.result
    record = result.get('reconciliation') if type(result) is dict else None
    if record is None:
        return None
    keys = {'schema_version', 'status', 'confirmation_id', 'submission_digest',
            'checked_at', 'object_refs', 'evidence_refs'}
    if (type(record) is not dict or set(record) != keys or type(record['schema_version']) is not int
            or record['schema_version'] != 1 or record['status'] != 'confirmed_success'
            or record['confirmation_id'] != item.id or record['submission_digest'] != item.submission_digest):
        _conflict()
    stored = ReceiptLookup.model_validate({**{key: deepcopy(record[key]) for key in
        ('status', 'checked_at', 'object_refs', 'evidence_refs')}, 'reason_code': None})
    snapshot = _checked_snapshot(item)
    if not validate_success_lookup(snapshot, stored):
        _conflict()
    return stored


def _run_card_source(db, principal, proposal):
    """Only complete accepted model/manifests of this actual Run can bind a card."""
    from .assistant_runtime_models import Run
    from .assistant_runtime_queue import _retry_model_frame
    from .assistant_runtime_runner import _owned_manifest, _completed_unbound_manifest, _work_key
    run = db.scalar(select(Run).where(Run.id == principal.run_id,
        Run.owner_id == principal.actor_id, Run.store_id == principal.store_id,
        Run.session_id == principal.session_id).execution_options(populate_existing=True))
    if run is None or (run.plan_id, run.goal_version) != (principal.plan_id, principal.goal_version):
        _conflict()
    items = list(db.scalars(select(RunItem).where(RunItem.run_id == run.id)
                           .execution_options(populate_existing=True)))
    found = False
    for model in (item for item in items if item.kind == 'model'):
        try:
            frame = _retry_model_frame(db, run, items, model.id)
        except (ValueError, TypeError, KeyError):
            _conflict()
        for parent in frame['parents']:
            data = frame['data'][parent.id]
            if data['manifest_id'] is None:
                continue
            thread, manifest, values = _owned_manifest(db, principal, principal.session_id, data['manifest_id'])
            scope = values['scope']
            if manifest.run_id != run.id:
                _conflict()
            historical = (scope['plan_id'] is None and principal.plan_id is not None
                          and _completed_unbound_manifest(db, principal, manifest, values))
            if not historical and (scope['plan_id'], scope['goal_version']) != (principal.plan_id, principal.goal_version):
                _conflict()
            for row in values['rows']:
                if row.get('proposal_id') != proposal.id:
                    continue
                work = db.scalar(select(WorkItem).where(WorkItem.id == row.get('work_item_id'))
                                 .execution_options(populate_existing=True))
                if (work is None or work.id != proposal.source_work_item_id
                        or work.item_kind != 'prepare' or work.operation_id != proposal.operation_id
                        or (work.owner_id, work.store_id, work.session_id) !=
                           (principal.actor_id, principal.store_id, principal.session_id)
                        or (work.plan_id, work.step_id, work.intent_version) !=
                           (scope['plan_id'], scope['step_id'], scope['intent_version'])
                        or work.input_item_id != row['input_item_id'] or work.intent_key != _work_key(scope, row['input_item_id'])
                        or row.get('carry_forward') is not None):
                    _conflict()
                attempts = [group[-1] for group in frame['groups'].values()
                            if frame['data'][group[-1].id]['manifest_id'] == manifest.id]
                if not any(item.work_item_id == work.id and item.proposal_id == proposal.id
                           and item.status == 'succeeded' and item.finished_at is not None for item in attempts):
                    _conflict()
                found = True
    return found, tuple(sorted((item.id, item.version) for item in items))


def _reconcile_source(db, principal, proposal_id):
    """Current Plan membership or this Run's complete accepted preparation."""
    from .assistant_runtime_plans import _condition_scope, _condition_snapshot, _snapshot_guard
    from .business_assistant_service import owned_session
    _condition_scope(db, principal)
    thread = owned_session(db, principal, principal.session_id)
    proposal = _owned_lookup_proposal(db, principal, principal.session_id, proposal_id)
    db.refresh(proposal)
    plan_guard, allowed = None, False
    if principal.plan_id is not None:
        snapshot = _condition_snapshot(db, principal)
        plan_guard = _snapshot_guard(snapshot)
        allowed = any(row['proposal_id'] == proposal.id for step in snapshot['steps'] for row in step['rows'])
    run_guard = None
    if principal.run_id is not None and not allowed:
        allowed, run_guard = _run_card_source(db, principal, proposal)
    if not allowed:
        raise HTTPException(404, '这项确认不属于当前执行或授权事项')
    items = list(db.scalars(select(RunItem).where(RunItem.kind == 'confirmation',
        RunItem.proposal_id == proposal.id).execution_options(populate_existing=True)))
    if len(items) != 1:
        return proposal, None, (thread.version, plan_guard, run_guard, _lookup_source(db, principal, principal.session_id, proposal.id))
    item = items[0]
    snapshot = _checked_snapshot(item)
    if ((snapshot.operation_id, snapshot.actor_id, snapshot.store_id, snapshot.role, snapshot.access_version)
            != _proposal_identity(proposal) or item.work_item_id != proposal.source_work_item_id
            or item.run_id is not None or item.item_key != 'confirmation:' + proposal.id or item.attempt_no != 1):
        _conflict()
    if proposal.source_work_item_id and db.scalar(select(WorkItem.id).where(
            WorkItem.supersedes_id == proposal.source_work_item_id).limit(1)):
        _conflict()
    return proposal, item, (thread.version, plan_guard, run_guard,
                            _lookup_source(db, principal, principal.session_id, proposal.id))


def _reconciliation_read_source(db, principal, proposal_id):
    # A condition may reference an owned earlier card without authorizing any
    # write to it. Preserve the original receipt-read scope; only the mutation
    # path above requires current manifest/single-card or accepted Run lineage.
    proposal = _owned_lookup_proposal(db, principal, principal.session_id, proposal_id)
    items = list(db.scalars(select(RunItem).where(RunItem.kind == 'confirmation',
        RunItem.proposal_id == proposal.id).execution_options(populate_existing=True)))
    item = items[0] if len(items) == 1 else None
    if item is not None:
        snapshot = _checked_snapshot(item)
        if (item.run_id is not None or item.work_item_id != proposal.source_work_item_id
                or (snapshot.operation_id, snapshot.actor_id, snapshot.store_id, snapshot.role, snapshot.access_version)
                   != _proposal_identity(proposal)):
            _conflict()
    return proposal, item, _lookup_source(db, principal, principal.session_id, proposal_id)


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class _ReconciliationProof:
    pass


_RECONCILIATIONS = WeakKeyDictionary()


def _proof(db, token, principal, *, consume=False):
    state = _RECONCILIATIONS.get(token) if type(token) is _ReconciliationProof else None
    if (state is None or state['principal'] is not principal or state['session']() is not db
            or state['bind'] is not db.get_bind() or state['consumed']
            or not 0 <= monotonic() - state['issued_at'] <= 60):
        _conflict()
    if consume:
        state['consumed'] = True
    return state


def _persist_reconciliation(db, principal, token, *, clock):
    from . import business_assistant_service as service
    from .assistant_runtime_models import FollowupGrant
    from .assistant_runtime_principal import revalidate_principal, _time
    from .assistant_runtime_plans import _condition_scope
    from .business_assistant_models import AssistantSession, AssistantWorkPlan, AssistantProposal
    from .assistant_runtime_queue import lock_for_write
    service.require_preparation_read_phase(db)
    state = _proof(db, token, principal)
    revalidate_principal(db, principal, clock=clock)
    _condition_scope(db, principal)
    with db.no_autoflush:
        if principal.run_id is not None:
            thread, _, _ = lock_for_write(db, principal, clock=clock)
        else:
            if principal.auth_kind != 'grant' or type(principal._probe_grant_version) is not int:
                _conflict()
            thread = db.scalar(select(AssistantSession).where(AssistantSession.id == principal.session_id,
                AssistantSession.owner_id == principal.actor_id, AssistantSession.store_id == principal.store_id)
                .with_for_update().execution_options(populate_existing=True))
            plan = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == principal.plan_id,
                AssistantWorkPlan.owner_id == principal.actor_id, AssistantWorkPlan.store_id == principal.store_id,
                AssistantWorkPlan.session_id == principal.session_id).with_for_update().execution_options(populate_existing=True))
            grant = db.scalar(select(FollowupGrant).where(FollowupGrant.id == principal.grant_id)
                              .with_for_update().execution_options(populate_existing=True))
            if (thread is None or plan is None or grant is None or plan.status != 'active' or plan.engine_version != 2
                    or plan.goal_version != principal.goal_version or grant.version != principal._probe_grant_version
                    or (grant.owner_id, grant.store_id, grant.session_id, grant.plan_id, grant.goal_version,
                        grant.owner_role, grant.access_version, grant.status, grant.revoked_at) !=
                       (principal.actor_id, principal.store_id, principal.session_id, principal.plan_id,
                        principal.goal_version, principal.role, principal.access_version, 'active', None)
                    or grant.expires_at is not None and _time(grant.expires_at) <= _time(clock())):
                _conflict()
        card = db.scalar(select(AssistantProposal).where(AssistantProposal.id == state['proposal_id'])
                         .with_for_update().execution_options(populate_existing=True))
        if card is None:
            _conflict()
        work = (db.scalar(select(WorkItem).where(WorkItem.id == card.source_work_item_id)
                .with_for_update().execution_options(populate_existing=True)) if card.source_work_item_id else None)
        item = db.scalar(select(RunItem).where(RunItem.id == state['item_id'])
                         .with_for_update().execution_options(populate_existing=True))
        _, checked_item, source = _reconcile_source(db, principal, card.id)
        if source != state['source'] or item is None or checked_item is not item:
            _conflict()
        _proof(db, token, principal, consume=True)
        revalidate_principal(db, principal, clock=clock)
        if (card.status not in {'executing', 'uncertain'} or item.status not in {'running', 'uncertain'}
                or work is not None and work.status not in {'prepared', 'uncertain', 'settled'}):
            _conflict()
        lookup = ReceiptLookup.model_validate(state['lookup'])
        card.result = service.receipt_success_result(card.result, item.id, item.submission_digest, lookup,
                                                     submission=_checked_snapshot(item))
        now = _time(clock())
        card.status, card.finished_at = 'succeeded', now
        item.status, item.finished_at, item.error_code = 'succeeded', now, None
        objects = [BusinessObjectRef.model_validate(value).model_dump(mode='json') for value in item.result_refs or []]
        for value in lookup.object_refs:
            if value.model_dump(mode='json') not in objects:
                objects.append(value.model_dump(mode='json'))
        item.result_refs = objects
        if work is not None:
            work.status, work.updated_at = 'settled', now
        thread.version += 1
        thread.updated_at = now
        service._emit_proposal_result(db, card)
        db.flush()
        revalidate_principal(db, principal, clock=clock)
        service.commit(db)


async def _read_reconciliation(db, principal, proposal_id, *, clock, client_factory, require_record=False):
    from .assistant_runtime_principal import _reader, revalidate_principal, native_reader_for_principal
    from .assistant_runtime_plans import _condition_scope
    from .business_assistant_service import require_preparation_read_phase
    require_preparation_read_phase(db)
    revalidate_principal(db, principal, clock=clock)
    started = monotonic()
    source_for = _reconciliation_read_source if require_record else _reconcile_source
    with _reader(db, principal._read_session_factory) as source_db:
        _condition_scope(source_db, principal)
        proposal, item, before = source_for(source_db, principal, proposal_id)
        if item is None:
            return _lookup_result('unsupported', 'missing_submission_snapshot'), None
        if require_record:
            try:
                record = _reconciliation_record(proposal, item)
            except (HTTPException, ValueError, TypeError):
                return _lookup_result('mismatch', 'invalid_reconciliation_record'), None
            if record is None:
                return _lookup_result('unsupported', 'missing_reconciliation_record'), None
            if proposal.status != 'succeeded' or item.status != 'succeeded' or item.finished_at is None:
                return _lookup_result('mismatch', 'reconciliation_state_mismatch'), None
        item_id = item.id
        read_operations = _receipt_read_operations(_checked_snapshot(item))
    _condition_scope(db, principal)
    native = native_reader_for_principal(db, principal, read_operations, client_factory=client_factory)
    lookup = await lookup_receipt(db, principal, principal.session_id, proposal_id, native_reader=native)
    revalidate_principal(db, principal, clock=clock)
    with _reader(db, principal._read_session_factory) as source_db:
        _condition_scope(source_db, principal)
        _, _, after = source_for(source_db, principal, proposal_id)
    if after != before:
        return _lookup_result('mismatch', 'confirmation_source_changed'), None
    if lookup.status != 'confirmed_success':
        return lookup, None
    if require_record:
        previous_receipts = {value.source_id.model_dump_json() for value in record.evidence_refs
                             if value.source_type == 'receipt'}
        current_receipts = {value.source_id.model_dump_json() for value in lookup.evidence_refs
                            if value.source_type == 'receipt'}
        if record.object_refs != lookup.object_refs or previous_receipts != current_receipts:
            return _lookup_result('mismatch', 'reconciliation_receipt_mismatch'), None
        return lookup, None
    token = _ReconciliationProof()
    _RECONCILIATIONS[token] = {'principal': principal, 'session': ref(db), 'bind': db.get_bind(),
        'issued_at': started, 'consumed': False, 'source': before, 'proposal_id': proposal_id,
        'item_id': item_id, 'lookup': lookup.model_dump(mode='json')}
    return lookup, token


async def lookup_reconciliation(db, principal, proposal_id, *, clock=None, client_factory=None):
    """Recheck stored recovery against the original receipt and current GET."""
    try:
        result, _ = await _read_reconciliation(db, principal, proposal_id,
            clock=clock or principal._clock, client_factory=client_factory, require_record=True)
        return result
    except HTTPException as exc:
        if exc.status_code in {401, 403, 404}:
            return _lookup_result('inaccessible', 'proposal_not_accessible')
        raise


async def reconcile_confirmation(db, principal, proposal_id, *, clock=None, client_factory=None):
    """Repair only an existing unknown confirmation, never resubmit business."""
    from .business_assistant_service import require_preparation_read_phase
    effective_clock = clock or principal._clock
    require_preparation_read_phase(db)
    db.rollback()
    try:
        lookup, token = await _read_reconciliation(db, principal, proposal_id,
            clock=effective_clock, client_factory=client_factory)
        if lookup.status != 'confirmed_success':
            return lookup
        state = _proof(db, token, principal)
        if state['source'][-1][1] == 'succeeded':
            return lookup
        db.rollback()
        _persist_reconciliation(db, principal, token, clock=effective_clock)
        from .assistant_runtime_principal import revalidate_principal
        revalidate_principal(db, principal, clock=effective_clock)
        return lookup
    except HTTPException as exc:
        db.rollback()
        if exc.status_code in {401, 403, 404}:
            return _lookup_result('inaccessible', 'proposal_not_accessible')
        raise
    except Exception:
        db.rollback()
        raise


async def reconcile_plan_confirmations(db, principal, *, clock=None, client_factory=None):
    """Check actual current single cards and complete manifest/carry rows only."""
    from .assistant_runtime_principal import _reader, revalidate_principal
    from .assistant_runtime_plans import _condition_scope, _condition_snapshot
    from .business_assistant_service import require_preparation_read_phase
    effective_clock = clock or principal._clock
    require_preparation_read_phase(db)
    db.rollback()
    revalidate_principal(db, principal, clock=effective_clock)
    if (principal.plan_id is None or principal.run_id is None
            and (principal.auth_kind != 'grant' or type(principal._probe_grant_version) is not int)):
        _conflict()
    with _reader(db, principal._read_session_factory) as reader:
        _condition_scope(reader, principal)
        snapshot = _condition_snapshot(reader, principal)
        ids = sorted({row['proposal_id'] for step in snapshot['steps'] for row in step['rows']
                      if row['proposal_id'] and row['status'] in {'executing', 'uncertain'}})
    summaries = []
    for proposal_id in ids:
        lookup = await reconcile_confirmation(db, principal, proposal_id,
            clock=effective_clock, client_factory=client_factory)
        if lookup.status == 'inaccessible':
            return ()
        summaries.append({'proposal_id': proposal_id, 'lookup': lookup.model_dump(mode='json')})
    revalidate_principal(db, principal, clock=effective_clock)
    return tuple(summaries)
