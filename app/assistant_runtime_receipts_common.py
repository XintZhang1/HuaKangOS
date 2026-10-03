"""Read-only helpers for the explicitly registered native receipt families.

These functions do not choose business models, reconstruct command payloads,
submit operations, or decide which native objects belong to a receipt.
Each fixed family keeps those original contracts in its own module.
"""
import hmac
import json

from fastapi import HTTPException

from .assistant_runtime_schemas import (
    BusinessObjectRef, EvidenceRef, NativeReceiptRef, ReceiptLookup,
)


def positive_int(value):
    return type(value) is int and value > 0


def invalid():
    raise HTTPException(409, '原提交或回执依据不完整，请先核对原业务结果') from None


def digest_matches(actual, expected):
    return (type(actual) is str and type(expected) is str
            and len(actual) == len(expected) == 64
            and all(char in '0123456789abcdef' for char in actual + expected)
            and hmac.compare_digest(actual, expected))


def json_signature(value):
    """Keep a detached JSON source in a stable, immutable read signature.

    This is not a native command digest. Native defaults, dates, separators and
    operation names remain the responsibility of the original fixed family.
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def result(status, reason=None, *, objects=None, evidence=None, checked_at=None):
    from .db import utcnow
    return ReceiptLookup(status=status, reason_code=reason,
                         checked_at=checked_at or utcnow(),
                         object_refs=objects or [], evidence_refs=evidence or [])


async def native_get(db, reader, operation, *, path_args, query=None):
    """Use the server's fixed GET reader after closing the clean read snapshot."""
    if reader is None or type(operation) is not str or not operation.startswith('GET '):
        raise HTTPException(503, '原业务只读核对暂时不可用，请稍后再查')
    from .business_assistant_service import require_preparation_read_phase
    require_preparation_read_phase(db)
    db.rollback()
    response = await reader(operation, path_args=path_args, query=query or {}, body=None)
    if type(response) is not dict or type(response.get('status')) is not int:
        raise HTTPException(503, '原业务核对返回不完整，请稍后再查')
    status = response['status']
    if status in {401, 403, 404}:
        raise HTTPException(404, '当前无法读取原业务记录')
    if not 200 <= status < 300 or response.get('truncated'):
        raise HTTPException(503, '原业务核对暂时不可用，请稍后再查')
    data = response.get('data')
    if type(data) is not dict or data.get('truncated'):
        raise HTTPException(503, '原业务核对返回不完整，请稍后再查')
    return data


def success(snapshot, receipt_id, objects):
    """Build evidence only from a checked command receipt and original GETs.

    Objects are (native type, original ID, observed native version) tuples.
    A family must separately restrict cardinality and any legal empty result.
    """
    from .db import utcnow
    if not positive_int(receipt_id):
        invalid()
    checked_at = utcnow()
    refs, observations, seen = [], [], set()
    for object_type, object_id, version in objects:
        if not positive_int(object_id) or version is not None and not positive_int(version):
            invalid()
        key = (object_type, object_id)
        if key in seen:
            invalid()
        seen.add(key)
        ref = BusinessObjectRef(type=object_type, id=object_id)
        refs.append(ref)
        observations.append(EvidenceRef(source_type='object', source_id=ref,
                                        native_version=version, observed_at=checked_at))
    receipt = EvidenceRef(source_type='receipt', source_id=NativeReceiptRef(
        operation_id=snapshot.operation_id, id=receipt_id), native_version=None,
        observed_at=checked_at)
    return result('confirmed_success', objects=refs, evidence=[receipt, *observations],
                  checked_at=checked_at)


def validate_evidence(snapshot, lookup, allowed_types, min_objects=1, max_objects=None):
    """Check the common evidence shape; the family checks native targets too."""
    try:
        checked = ReceiptLookup.model_validate(lookup)
        count = len(checked.object_refs)
        if (checked.status != 'confirmed_success' or checked.reason_code is not None
                or count < min_objects or max_objects is not None and count > max_objects
                or len(checked.evidence_refs) != count + 1):
            return False
        keys = [(ref.type, ref.id) for ref in checked.object_refs]
        if len(set(keys)) != count or any(ref.type not in allowed_types for ref in checked.object_refs):
            return False
        receipts = [ref for ref in checked.evidence_refs if ref.source_type == 'receipt']
        if (len(receipts) != 1 or type(receipts[0].source_id) is not NativeReceiptRef
                or receipts[0].source_id.operation_id != snapshot.operation_id
                or not positive_int(receipts[0].source_id.id) or receipts[0].native_version is not None):
            return False
        observed = [ref for ref in checked.evidence_refs if ref.source_type == 'object']
        return (len(observed) == count
                and sorted((ref.source_id.type, ref.source_id.id) for ref in observed) == sorted(keys)
                and all(ref.native_version is None or positive_int(ref.native_version) for ref in observed))
    except (ValueError, TypeError, AttributeError):
        return False
