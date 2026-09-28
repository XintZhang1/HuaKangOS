"""Authorized object snapshots and exact native response bindings.

Callers supply a server-bound GET reader, never a URL or a model-provided
principal. Resolution is read-only and cannot imply a business submission or
completion. Identity revalidation belongs to the native transport.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException
from pydantic import ValidationError

from .assistant_runtime_registry import DomainRegistry, domain_registry
from .assistant_runtime_schemas import BusinessObjectRef, BusinessObjectSnapshot


def object_ref(value) -> BusinessObjectRef:
    """Validate a native namespace/ID without guessing from a path or table."""
    try:
        if isinstance(value, BusinessObjectRef):
            value = value.model_dump()
        return BusinessObjectRef.model_validate(value)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, '业务对象类型或原编号不正确，请重新核对') from None


def _snapshot(value, ref):
    try:
        if isinstance(value, BusinessObjectSnapshot):
            value = value.model_dump()
        result = BusinessObjectSnapshot.model_validate(value)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(502, '原业务快照不完整，请到原页面核对') from None
    if result.ref != ref:
        raise HTTPException(502, '原业务返回的对象与所查原单不一致')
    return result


async def read_object(principal, ref, *, native_reader, receipt_reader=None,
                      registry: DomainRegistry | None = None) -> BusinessObjectSnapshot:
    """Dispatch only after proving shared Case selectors by the original GET.

    registry/readers are application dependencies, not HTTP or model arguments.
    A specialized provider must still perform its own authorized read; the
    generic read is only evidence for choosing a fixed provider.
    """
    ref = object_ref(ref)
    providers = domain_registry() if registry is None else registry
    spec = providers.spec_for_object(ref.type)
    if spec is None:
        raise HTTPException(501, '此类原业务对象尚未接入助手读取，请使用原业务页面')
    adapter = providers.build(spec, native_reader=native_reader, receipt_reader=receipt_reader)
    if ref.type == 'case':
        # A shared Case ID says nothing about a sales/repair/etc. subtype.
        # read_record is the registered generic Case adapter's native GET, not
        # model text or an arbitrary data field recursively searched for IDs.
        record = await adapter.read_record(principal, ref)
        selected = providers.spec_for_object('case', kind=record.get('kind'),
                                             flow_version=record.get('flow_version'))
        if selected is spec:
            return _snapshot(adapter.snapshot_from_record(ref, record), ref)
        if selected is None:
            raise HTTPException(501, '原单类型暂未接入助手，请使用原业务页面')
        adapter = providers.build(selected, native_reader=native_reader, receipt_reader=receipt_reader)
    return _snapshot(await adapter.read_snapshot(principal, ref), ref)


@dataclass(frozen=True)
class ResultResolution:
    """Internal binding outcome; never a command/receipt success result.

    An unbound successful response remains a successful native command. It must
    be shown as requiring original-page checking, never retried to obtain an ID.
    """
    status: Literal['resolved', 'unbound', 'unsupported']
    object_refs: tuple[BusinessObjectRef, ...]
    reason_code: str | None = None


async def _no_result_reads(*args, **kwargs):
    raise RuntimeError('Result extraction cannot perform native reads')


def resolve_result(operation_id, response, *, registry: DomainRegistry | None = None) -> ResultResolution:
    """Bind only an exact registered operation's native response structure.

    The caller must already own/authorize the response. This pure projection
    does not verify a receipt or prove funds, goods, signatures or task closure.
    """
    providers = domain_registry() if registry is None else registry
    spec = providers.spec_for_operation(operation_id)
    if spec is None:
        return ResultResolution('unsupported', (), 'operation_not_registered')
    adapter = providers.build(spec, native_reader=_no_result_reads)
    try:
        values = adapter.extract_result(operation_id, response)
        if type(values) is not list:
            return ResultResolution('unbound', (), 'invalid_native_result')
        refs = tuple(object_ref(value) for value in values)
        if any(ref.type not in spec.object_types for ref in refs):
            return ResultResolution('unbound', (), 'unexpected_object_type')
        if len({(ref.type, ref.id) for ref in refs}) != len(refs):
            return ResultResolution('unbound', (), 'duplicate_object_reference')
    except (HTTPException, ValidationError, ValueError, TypeError):
        return ResultResolution('unbound', (), 'invalid_native_result')
    if not refs:
        return ResultResolution('unbound', (), 'native_object_id_unavailable')
    return ResultResolution('resolved', refs)
