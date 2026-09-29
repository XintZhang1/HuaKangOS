"""Pure Runtime contracts; validation never opens a database or authorizes a user.

Native payloads are already validated by their original API. This module preserves
their values, keeps unknown facts explicit, and freezes the confirmation envelope.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
from types import MappingProxyType
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer,
    ValidationInfo, field_validator, model_validator,
)


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, validate_default=True,
                              validate_assignment=True)


def _utf8_text(value: Any) -> str:
    if type(value) is not str:
        raise ValueError('Expected text')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError('Text must contain valid Unicode scalar values') from None
    return value


PositiveId = Annotated[int, Field(strict=True, gt=0)]
Version = Annotated[int, Field(strict=True, ge=1)]
Counter = Annotated[int, Field(strict=True, ge=0)]
MoneyCents = Annotated[int, Field(strict=True)]
QuantityMilli = Annotated[int, Field(strict=True)]
NonEmptyText = Annotated[str, BeforeValidator(_utf8_text), Field(strict=True, min_length=1)]
OperationId = Annotated[str, Field(
    strict=True, max_length=180,
    pattern=r'^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /api/[^\s?#]+$',
)]
WriteOperationId = Annotated[str, Field(
    strict=True, max_length=180, pattern=r'^(POST|PUT) /api/[^\s?#]+$',
)]
ActionKey = Annotated[str, Field(strict=True, min_length=1, max_length=180)]
FactKey = Annotated[str, Field(
    strict=True, max_length=180,
    pattern=r'^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$',
)]
WorkflowId = Annotated[str, Field(strict=True, min_length=1, max_length=100)]
StepKey = Annotated[str, Field(strict=True, pattern=r'^[A-Za-z0-9_-]{1,50}$')]
MessageRequestId = Annotated[str, Field(strict=True, min_length=16, max_length=80,
                                       pattern=r'^[A-Za-z0-9_-]+$')]
NativeRequestId = Annotated[str, Field(strict=True, min_length=8, max_length=80,
                                      pattern=r'^[A-Za-z0-9_-]+$')]
SHA256Text = Annotated[str, Field(strict=True, pattern=r'^[a-f0-9]{64}$')]


def _uuid_text(value: Any) -> str:
    if type(value) is not str:
        raise ValueError('UUID must be a canonical string')
    try:
        canonical = str(UUID(value))
    except (ValueError, AttributeError):
        raise ValueError('UUID must be a canonical string') from None
    if canonical != value:
        raise ValueError('UUID must be a canonical string')
    return value


UUIDText = Annotated[str, BeforeValidator(_uuid_text)]


def _utc(value: Any) -> datetime:
    if type(value) is str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError('Expected an ISO datetime with a timezone') from None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('HTTP datetime strings must include a timezone')
    elif isinstance(value, datetime):
        # Existing database columns use UTC-naive datetime objects.
        parsed = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    else:
        raise ValueError('Datetime must not be a numeric timestamp')
    return parsed.astimezone(timezone.utc)


def utc_text(value: datetime) -> str:
    """Canonical UTC representation, including all six microsecond digits."""
    return _utc(value).isoformat(timespec='microseconds').replace('+00:00', 'Z')


UTCDateTime = Annotated[datetime, BeforeValidator(_utc),
                        PlainSerializer(utc_text, return_type=str, when_used='json')]


def _calendar_date(value: Any) -> date:
    if type(value) is date:
        return value
    if type(value) is str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise ValueError('Expected an ISO calendar date') from None
        if parsed.isoformat() == value:
            return parsed
    raise ValueError('Expected a calendar date, without inferred timezone')


CalendarDate = Annotated[date, BeforeValidator(_calendar_date)]


def _json_copy(value: Any) -> Any:
    """Validate finite JSON without coercing units, IDs, keys or native values."""
    if type(value) is str:
        return _utf8_text(value)
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError('Non-finite JSON numbers are forbidden')
        return value
    if type(value) is list:
        return [_json_copy(item) for item in value]
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError('JSON object keys must be strings')
        return {_utf8_text(key): _json_copy(item) for key, item in value.items()}
    raise ValueError('Only native JSON values are allowed')


def _json_object(value: Any) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError('Expected a JSON object')
    return _json_copy(value)


JsonValue = Annotated[Any, BeforeValidator(_json_copy)]
JsonObject = Annotated[dict[str, Any], BeforeValidator(_json_object)]

PlanStatus = Literal['active', 'paused', 'completed', 'cancelled']
StepStatus = Literal['waiting', 'needs_input', 'awaiting_confirmation', 'completed',
                     'failed', 'uncertain', 'cancelled']
RunStatus = Literal['queued', 'running', 'succeeded', 'failed', 'cancelled']
RunItemStatus = Literal['pending', 'running', 'succeeded', 'failed', 'uncertain', 'skipped']
WorkItemStatus = Literal['planned', 'prepared', 'settled', 'uncertain']
GrantStatus = Literal['active', 'paused', 'revoked']
NotificationStatus = Literal['unread', 'read', 'resolved']
WakeEventStatus = Literal['pending', 'dispatched']
NativeTaskStatus = Literal['open', 'done', 'cancelled']
ProposalStatus = Literal['pending', 'executing', 'succeeded', 'failed', 'uncertain',
                         'cancelled', 'expired']
Availability = Literal['enabled', 'disabled', 'unknown']
RunItemKind = Literal['model', 'tool', 'batch_row', 'confirmation']
WorkItemKind = Literal['read', 'prepare']
TriggerKind = Literal['user', 'signal', 'manual']
AuthKind = Literal['login', 'grant']
WorkspaceGroupKey = Literal['attention', 'following', 'finished']

# This is a namespace, not an authorization or a claim that an adapter exists.
# Runtime registry services must resolve the exact operation and registered type.
BusinessObjectType = Literal[
    'case', 'customer', 'vehicle', 'employee', 'member', 'material', 'master',
    'vehicle_import_batch', 'service_appointment', 'rework_source_grant', 'gate_visit',
    'retail_bundle_rule', 'retail_bundle_sale', 'customer_vehicle', 'care_case', 'reminder_rule',
    'questionnaire_version', 'observation_correction', 'group_member',
    'package_purchase', 'member_pricing_rule', 'reconciliation_batch', 'clearing_order',
    'report_query', 'daily_report', 'material_transfer', 'vehicle_transfer',
    'transfer_exception', 'goods_recovery', 'vehicle_transport_exception',
    'dossier_grant', 'vehicle_brand', 'vehicle_series', 'supplier', 'insurer',
    'warehouse', 'storage_location', 'material_brand', 'material_category',
    'master_work_item', 'team', 'agency_project', 'vehicle_model', 'member_tier',
    'item_profile', 'dictionary_entry', 'escalation', 'refusal',
]


class BusinessObjectRef(StrictDTO):
    type: BusinessObjectType
    id: PositiveId | UUIDText

    @model_validator(mode='after')
    def check_native_id(self) -> BusinessObjectRef:
        if self.type == 'report_query':
            if type(self.id) is not str:
                raise ValueError('report_query must reference a WorkItem UUID')
        elif type(self.id) is not int:
            raise ValueError('Native object IDs must be positive integers')
        return self


ObjectRef = BusinessObjectRef


class NativeReceiptRef(StrictDTO):
    operation_id: OperationId
    id: PositiveId | UUIDText


class EvidenceRef(StrictDTO):
    source_type: Literal['message', 'object', 'proposal', 'task', 'receipt']
    source_id: PositiveId | UUIDText | BusinessObjectRef | NativeReceiptRef
    native_version: Version | None
    observed_at: UTCDateTime

    @model_validator(mode='after')
    def check_source(self) -> EvidenceRef:
        expected = {'message': int, 'task': int, 'proposal': str,
                    'object': BusinessObjectRef, 'receipt': NativeReceiptRef}
        if type(self.source_id) is not expected[self.source_type]:
            raise ValueError('Evidence reference does not match its source type')
        return self


class TaskSnapshot(StrictDTO):
    id: PositiveId
    case_id: PositiveId | None = None
    key: str | None = None
    title: str | None = None
    role: str | None = None
    assignee_id: PositiveId | None = None
    status: NativeTaskStatus | None = None
    due_date: CalendarDate | None = None
    version: Version | None = None
    done_by: PositiveId | None = None
    done_at: UTCDateTime | None = None


class AvailableAction(StrictDTO):
    action_key: ActionKey
    availability: Availability
    reason: str | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class BusinessObjectSnapshot(StrictDTO):
    ref: BusinessObjectRef
    native_version: Version | None
    display_number: str | None
    state: str | None
    tasks: list[TaskSnapshot]
    available_actions: list[AvailableAction]
    evidence_refs: list[EvidenceRef]
    manual_route: str | None
    observed_at: UTCDateTime


Snapshot = BusinessObjectSnapshot


class FactSnapshot(StrictDTO):
    fact_key: FactKey
    satisfied: bool | None
    evidence_refs: list[EvidenceRef]
    reason: str | None


class ReceiptLookup(StrictDTO):
    status: Literal['confirmed_success', 'not_found', 'unsupported', 'inaccessible', 'mismatch']
    checked_at: UTCDateTime
    object_refs: list[BusinessObjectRef]
    evidence_refs: list[EvidenceRef]
    reason_code: str | None


class ProposalSucceeded(StrictDTO):
    type: Literal['proposal_succeeded']
    proposal_id: UUIDText


class NativeActionAvailable(StrictDTO):
    type: Literal['native_action_available']
    object_ref: BusinessObjectRef
    action_key: ActionKey


class NativeTaskState(StrictDTO):
    type: Literal['native_task_state']
    task_id: PositiveId
    expected_status: NativeTaskStatus
    expected_assignee_id: PositiveId | None = None


class FactExists(StrictDTO):
    type: Literal['fact_exists']
    object_ref: BusinessObjectRef
    fact_key: FactKey


class DueAt(StrictDTO):
    type: Literal['due_at']
    at: UTCDateTime
    source_message_id: PositiveId


Condition = Annotated[
    ProposalSucceeded | NativeActionAvailable | NativeTaskState | FactExists | DueAt,
    Field(discriminator='type'),
]
EntryIntent = Literal['query_status', 'explain_prerequisites', 'prepare_action']


class TaskEntryContext(StrictDTO):
    source_type: Literal['task']
    intent: EntryIntent
    task_id: PositiveId


class ObjectEntryContext(StrictDTO):
    source_type: Literal['object']
    intent: EntryIntent
    object_ref: BusinessObjectRef


class WorkflowEntryContext(StrictDTO):
    source_type: Literal['workflow']
    intent: EntryIntent
    workflow_id: WorkflowId


EntryContext = Annotated[TaskEntryContext | ObjectEntryContext | WorkflowEntryContext,
                         Field(discriminator='source_type')]


class RunCreate(StrictDTO):
    request_id: MessageRequestId
    content: Annotated[str, Field(min_length=1, max_length=12000)]
    thinking: bool = False
    plan_id: UUIDText | None = None
    entry_context: EntryContext | None = None

    @field_validator('content')
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('A Run requires non-blank employee input')
        # Preserve the exact accepted text for request_digest and recovery.
        return value


class RunCancel(StrictDTO):
    expected_version: Version


class FollowupAction(StrictDTO):
    action: Literal['enable', 'pause', 'resume', 'revoke']
    expected_version: Version


class WorkspaceQuery(StrictDTO):
    group: WorkspaceGroupKey | None = None
    cursor: str | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 30


class NotificationQuery(StrictDTO):
    cursor: str | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 30


RuntimeErrorCode = Literal['invalid_input', 'not_found', 'permission_denied',
                           'version_conflict', 'request_conflict',
                           'precondition_conflict', 'runtime_unavailable']
ERROR_HTTP_STATUS = MappingProxyType({
    'invalid_input': 422, 'not_found': 404, 'permission_denied': 403,
    'version_conflict': 409, 'request_conflict': 409,
    'precondition_conflict': 409, 'runtime_unavailable': 503,
})


class ErrorDetail(StrictDTO):
    # Preserve the original detail shape, including FastAPI validation lists.
    detail: JsonValue
    code: RuntimeErrorCode


class RunDisplay(StrictDTO):
    phase: RunStatus
    text: str
    revision: Counter


class RunView(StrictDTO):
    id: UUIDText
    session_id: UUIDText
    plan_id: UUIDText | None
    status: RunStatus
    version: Version
    last_seq: Counter
    display: RunDisplay
    result_refs: list[BusinessObjectRef]
    error: ErrorDetail | None = None
    allowed_actions: list[ActionKey] = Field(default_factory=list)


class PlanStepView(StrictDTO):
    key: StepKey
    position: Counter
    title: Annotated[str, Field(min_length=1, max_length=160)]
    wait_for: Annotated[str, Field(max_length=500)]
    status: StepStatus
    wait_reason: str | None
    # 与侧栏同一份固定中文等待文案，避免把内部标识直接显示给员工。
    waiting_label: str | None = None
    proposal_id: UUIDText | None = None
    proposal_ids: list[UUIDText] = Field(default_factory=list)
    object_ref: BusinessObjectRef | None = None
    manual_route: str | None = None

    @model_validator(mode='after')
    def check_proposals(self) -> PlanStepView:
        if len(self.proposal_ids) != len(set(self.proposal_ids)):
            raise ValueError('Current proposal IDs must not be duplicated')
        if self.proposal_id is not None and self.proposal_id not in self.proposal_ids:
            raise ValueError('The compatible single proposal belongs in proposal_ids')
        return self


class GrantView(StrictDTO):
    status: GrantStatus | None
    enabled: bool
    stop_reason: str | None

    @model_validator(mode='after')
    def check_enabled(self) -> GrantView:
        if self.enabled != (self.status == 'active'):
            raise ValueError('Only an active followup grant can be enabled')
        return self


class PlanView(StrictDTO):
    id: UUIDText
    session_id: UUIDText
    version: Version
    goal_version: Version
    goal: Annotated[str, Field(min_length=1, max_length=300)]
    status: PlanStatus
    steps: list[PlanStepView]
    grant: GrantView
    allowed_actions: list[ActionKey] = Field(default_factory=list)


class RuntimeFeatures(StrictDTO):
    home: bool = False
    runtime: bool = False
    followup: bool = False
    notifications: bool = False

    @model_validator(mode='after')
    def require_runtime_for_followup(self) -> RuntimeFeatures:
        if self.followup and not self.runtime:
            raise ValueError('Follow-up requires Runtime')
        return self


class WorkspaceCounts(StrictDTO):
    native_tasks: Counter
    pending_proposals: Counter
    attention: Counter
    following: Counter
    finished: Counter


class WorkspaceItem(StrictDTO):
    key: NonEmptyText
    kind: Literal['native_task', 'proposal', 'plan']
    session_id: UUIDText | None = None
    plan_id: UUIDText | None = None
    task_id: PositiveId | None = None
    proposal_id: UUIDText | None = None
    object_ref: BusinessObjectRef | None = None
    title: str
    status: str
    status_label: str
    waiting_reason: str | None = None
    # 固定中文等待文案；不提供内部状态机标识给员工。未知原因保持为 None。
    waiting_label: str | None = None
    due_at: UTCDateTime | None = None
    manual_route: str | None = None
    allowed_actions: list[ActionKey] = Field(default_factory=list)
    updated_at: UTCDateTime

    @model_validator(mode='after')
    def check_stable_key(self) -> WorkspaceItem:
        identity = {'native_task': ('task', self.task_id),
                    'proposal': ('proposal', self.proposal_id),
                    'plan': ('plan', self.plan_id)}[self.kind]
        if identity[1] is None or self.key != f'{identity[0]}:{identity[1]}':
            raise ValueError('Workspace key must identify its actual source record')
        return self


class WorkspaceGroup(StrictDTO):
    key: WorkspaceGroupKey
    items: list[WorkspaceItem]
    next_cursor: str | None


class WorkspaceView(StrictDTO):
    features: RuntimeFeatures
    counts: WorkspaceCounts
    groups: list[WorkspaceGroup]
    checked_at: UTCDateTime


class NotificationView(StrictDTO):
    id: UUIDText
    kind: NonEmptyText
    safe_summary: str
    status: NotificationStatus
    created_at: UTCDateTime
    read_at: UTCDateTime | None
    session_id: UUIDText | None = None
    plan_id: UUIDText | None = None
    proposal_id: UUIDText | None = None
    task_id: PositiveId | None = None
    manual_route: str | None = None


class NotificationList(StrictDTO):
    items: list[NotificationView]
    next_cursor: str | None
    unread_count: Counter


class RunProgressPayload(StrictDTO):
    display: RunDisplay


class RunLifecyclePayload(StrictDTO):
    plan_id: UUIDText | None = None


class ToolFinishedPayload(StrictDTO):
    run_item_id: UUIDText
    work_item_id: UUIDText | None = None
    result_refs: list[BusinessObjectRef] = Field(default_factory=list)


class ProposalPreparedPayload(StrictDTO):
    proposal_id: UUIDText
    work_item_id: UUIDText | None = None
    plan_id: UUIDText | None = None


class PlanUpdatedPayload(StrictDTO):
    plan_id: UUIDText


RunEventType = Literal['run.queued', 'run.started', 'run.progress', 'tool.finished',
                       'proposal.prepared', 'plan.updated', 'run.completed',
                       'run.failed', 'run.cancelled']
_EVENT_PAYLOADS = {
    'run.queued': RunLifecyclePayload, 'run.started': RunLifecyclePayload,
    'run.progress': RunProgressPayload, 'tool.finished': ToolFinishedPayload,
    'proposal.prepared': ProposalPreparedPayload, 'plan.updated': PlanUpdatedPayload,
    'run.completed': RunLifecyclePayload, 'run.failed': RunLifecyclePayload,
    'run.cancelled': RunLifecyclePayload,
}


class RunEventView(StrictDTO):
    run_id: UUIDText
    seq: PositiveId
    type: RunEventType
    payload: (RunProgressPayload | RunLifecyclePayload | ToolFinishedPayload
              | ProposalPreparedPayload | PlanUpdatedPayload)
    created_at: UTCDateTime

    @field_validator('payload', mode='before')
    @classmethod
    def parse_payload(cls, value: Any, info: ValidationInfo) -> Any:
        payload_type = _EVENT_PAYLOADS.get(info.data.get('type'))
        if payload_type is None:
            raise ValueError('Unknown Runtime event type')
        if isinstance(value, BaseModel):
            value = value.model_dump(mode='python')
        return payload_type.model_validate(value)

    @model_validator(mode='after')
    def check_payload_type(self) -> RunEventView:
        if type(self.payload) is not _EVENT_PAYLOADS[self.type]:
            raise ValueError('Payload does not match its Runtime event type')
        return self


class SubmissionSnapshot(StrictDTO):
    """Internal only: never expose through Run/Plan/Event/Workspace views."""
    model_config = ConfigDict(extra='forbid', strict=True, validate_default=True,
                              frozen=True, revalidate_instances='always')

    operation_id: WriteOperationId
    path_args: JsonObject
    query: JsonObject
    body: JsonObject | None
    request_id: NativeRequestId | None
    actor_id: PositiveId
    store_id: PositiveId
    role: NonEmptyText
    access_version: Version
    confirmed_at: UTCDateTime

    @model_validator(mode='after')
    def check_request_id(self) -> SubmissionSnapshot:
        native_id = self.body.get('request_id') if self.body is not None else None
        if self.request_id != native_id:
            raise ValueError('Frozen request_id must equal the actual native body request_id')
        return self


def canonical_submission_bytes(snapshot: SubmissionSnapshot | dict[str, Any]) -> bytes:
    """Revalidate and detach all nested payloads before canonical serialization."""
    values = snapshot.model_dump(mode='python') if isinstance(snapshot, SubmissionSnapshot) else deepcopy(snapshot)
    checked = SubmissionSnapshot.model_validate(values)
    return json.dumps(checked.model_dump(mode='json'), sort_keys=True,
                      separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def submission_snapshot_digest(snapshot: SubmissionSnapshot | dict[str, Any]) -> str:
    return sha256(canonical_submission_bytes(snapshot)).hexdigest()


class RunItemRecord(StrictDTO):
    """Internal record contract, including legacy confirmation without a Run."""
    id: UUIDText
    version: Version = 1
    created_at: UTCDateTime
    run_id: UUIDText | None = None
    work_item_id: UUIDText | None = None
    proposal_id: UUIDText | None = None
    kind: RunItemKind
    item_key: NonEmptyText
    attempt_no: Version
    tool_name: str | None = None
    validated_arguments: JsonObject | None = None
    result_refs: list[BusinessObjectRef] | None = None
    status: RunItemStatus
    error_code: RuntimeErrorCode | None = None
    started_at: UTCDateTime | None = None
    finished_at: UTCDateTime | None = None
    submission_snapshot: SubmissionSnapshot | None = None
    submission_digest: SHA256Text | None = None

    @model_validator(mode='after')
    def check_record_kind(self) -> RunItemRecord:
        if self.kind == 'confirmation':
            if self.proposal_id is None:
                raise ValueError('Confirmation must reference the actual proposal')
            if self.submission_snapshot is None or self.submission_digest is None:
                raise ValueError('Confirmation must freeze its submission and digest')
            if submission_snapshot_digest(self.submission_snapshot) != self.submission_digest:
                raise ValueError('Frozen submission digest does not match its contents')
        else:
            if self.run_id is None:
                raise ValueError('Only confirmation records may omit run_id')
            if self.submission_snapshot is not None or self.submission_digest is not None:
                raise ValueError('Only confirmation records contain a frozen submission')
        return self
