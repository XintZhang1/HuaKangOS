"""Finite, read-only conditions evaluated against current authorized facts.

The returned fingerprint describes facts, not observation time. It is a change
detector, never a permission token or a replacement for checking conditions
again before preparation. No evaluation submits or reconciles business work.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select

from .assistant_runtime_objects import read_object
from .assistant_runtime_principal import (
    _reader, native_reader_for_principal, revalidate_principal,
)
from .assistant_runtime_registry import domain_registry
from .assistant_runtime_schemas import (
    BusinessObjectRef, Condition, EvidenceRef, FactSnapshot, UUIDText,
)


@dataclass(frozen=True)
class ConditionEvaluation:
    satisfied: bool
    unknown: bool
    reason: str | None
    evidence: tuple[EvidenceRef, ...]
    fingerprint: str


@dataclass(frozen=True)
class _Observation:
    satisfied: bool
    unknown: bool
    reason: str | None
    evidence: tuple[EvidenceRef, ...]
    facts: dict
    proves_completion: bool = False


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False)


def _digest(value):
    return sha256(_canonical(value).encode('utf-8')).hexdigest()


def _without_observed_at(value):
    if type(value) is dict:
        result = {key: _without_observed_at(item) for key, item in value.items() if key != 'observed_at'}
        # Evidence is a set of sources; adapter/native list ordering is not a
        # change in the underlying fact. Do not sort arbitrary business rows.
        if type(result.get('evidence_refs')) is list:
            unique = {_canonical(item): item for item in result['evidence_refs']}
            result['evidence_refs'] = [unique[key] for key in sorted(unique)]
        return result
    if type(value) is list:
        return [_without_observed_at(item) for item in value]
    return value


def _snapshot_facts(snapshot):
    values = _without_observed_at(snapshot.model_dump(mode='json'))
    values['tasks'] = sorted(values['tasks'], key=lambda item: item['id'])
    values['available_actions'] = sorted(values['available_actions'], key=lambda item: item['action_key'])
    return values


def _evidence(values):
    """Deduplicate by native identity/version, retaining the newest observation."""
    found = {}
    for value in values:
        item = EvidenceRef.model_validate(value.model_dump() if isinstance(value, EvidenceRef) else value)
        key = _canonical(_without_observed_at(item.model_dump(mode='json')))
        if key not in found or item.observed_at > found[key].observed_at:
            found[key] = item
    return tuple(found[key] for key in sorted(found))


def _utc(value):
    if not isinstance(value, datetime):
        raise TypeError('Condition clock must return a datetime')
    # ORM timestamps and the application's utcnow are explicitly naive UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _result(observations, purpose, *, missing_reason=None):
    ordered = sorted(observations, key=lambda item: _canonical(item.facts))
    satisfied = bool(ordered) and all(item.satisfied for item in ordered)
    unknown = any(item.unknown for item in ordered)
    reason = next((item.reason for item in ordered if not item.satisfied and item.reason), None)
    if not ordered:
        satisfied = purpose == 'preparation'
        unknown = purpose == 'completion'
        reason = None if satisfied else (missing_reason or 'completion_conditions_missing')
    elif purpose == 'completion' and satisfied and not any(item.proves_completion for item in ordered):
        satisfied, unknown, reason = False, True, 'completion_evidence_missing'
    elif purpose == 'completion' and satisfied and all(item.reason == 'read_completed' for item in ordered):
        reason = 'read_completed'
    if missing_reason is not None:
        satisfied, unknown, reason = False, True, missing_reason
    evidence = _evidence([item for observation in ordered for item in observation.evidence])
    facts = [{'facts': item.facts, 'satisfied': item.satisfied, 'unknown': item.unknown,
              'reason': item.reason,
              'evidence': [_without_observed_at(value.model_dump(mode='json')) for value in _evidence(item.evidence)]}
             for item in ordered]
    return ConditionEvaluation(satisfied, unknown, reason, evidence, _digest({
        'purpose': purpose, 'facts': facts, 'satisfied': satisfied, 'unknown': unknown, 'reason': reason}))


def _failure(condition, reason, *, unknown=True, facts=None, evidence=()):
    return _Observation(False, unknown, reason, tuple(evidence),
                        {'condition': condition.model_dump(mode='json'), **(facts or {})})


def _unavailable(condition, exc):
    # Authentication/lease failures are rechecked at the outer boundary and
    # propagate. Object failures expose no original record or exception text.
    reason = ('source_inaccessible' if exc.status_code in {401, 403, 404}
              else 'source_unsupported' if exc.status_code in {422, 501}
              else 'source_unavailable')
    return _failure(condition, reason, facts={'http_status': exc.status_code})


_CLOCK_PATTERN = (
    r'(?P<period>上午|下午|晚上|中午|凌晨)?\s*(?P<hour>[0-9]{1,2})'
    r'(?:(?::(?P<minute>[0-9]{2})(?::(?P<second>[0-9]{2})(?P<fraction>\.[0-9]{1,6})?)?)'
    r'|(?:(?:点|时)(?:(?P<cn_minute>[0-9]{1,2})分?)?(?P<half>半|整)?))'
    r'(?P<offset>Z|[+-][0-9]{2}:[0-9]{2}|\s+UTC)?'
    # Never accept the valid prefix of a malformed/longer time token.
    r'(?![0-9A-Za-z:.+\-]|分|秒|半|整|刻|差|一刻|三刻|多|左右|前后|\s*(?:UTC|GMT|[+-][0-9]))')
_EXPLICIT_TIME = re.compile(
    r'(?<![0-9])(?P<year>[0-9]{4})(?:-|年)(?P<month>[0-9]{1,2})(?:-|月)'
    r'(?P<day>[0-9]{1,2})(?:日\s*|[T\s]+)' + _CLOCK_PATTERN)
_RELATIVE_TIME = re.compile(r'(?P<day>今天|明天|后天)\s*' + _CLOCK_PATTERN)


def _unambiguous_local(local, zone):
    candidates = {local.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
                  for fold in (0, 1)
                  if local.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
                  .astimezone(zone).replace(tzinfo=None) == local}
    return candidates if len(candidates) == 1 else set()


def _source_clock(values, target_date, zone):
    hour = int(values['hour'])
    period = values['period']
    if period:
        if period in {'下午', '晚上'} and 1 <= hour <= 11:
            hour += 12
        elif period in {'下午', '中午'} and hour == 12:
            pass
        elif (period == '上午' and 0 <= hour < 12) or (period == '凌晨' and 0 <= hour <= 6):
            pass
        elif period == '凌晨' and hour == 12:
            hour = 0
        else:
            return set()
    if values['half'] == '半' and values['cn_minute'] is not None:
        return set()
    minute = 30 if values['half'] == '半' else int(values['minute'] or values['cn_minute'] or 0)
    microsecond = int((values['fraction'] or '.0')[1:].ljust(6, '0'))
    try:
        local = datetime(target_date.year, target_date.month, target_date.day, hour,
                         minute, int(values['second'] or 0), microsecond)
        offset = values['offset']
        if offset:
            offset = '+00:00' if offset.strip() in {'Z', 'UTC'} else offset
            if int(offset[1:3]) > 23 or int(offset[4:6]) > 59:
                return set()
            # A period plus an offset is still an explicit local wall time.
            local = datetime.fromisoformat(local.isoformat() + offset)
            return {local.astimezone(timezone.utc)}
        return _unambiguous_local(local, zone)
    except ValueError:
        return set()


def _source_times(content, timezone_name, created_at):
    """Only full dates or today/tomorrow plus explicit clock times are evidence.

    Relative dates use the original message date, never this evaluation date.
    Other natural-language/ambiguous dates are left for employee input.
    Local gaps/ambiguous DST times require an explicit numeric UTC offset.
    """
    results = set()
    zone = ZoneInfo(timezone_name)
    for match in _EXPLICIT_TIME.finditer(content):
        values = match.groupdict()
        try:
            target_date = datetime(int(values['year']), int(values['month']), int(values['day'])).date()
            results.update(_source_clock(values, target_date, zone))
        except ValueError:
            continue
    base_date = _utc(created_at).astimezone(zone).date()
    for match in _RELATIVE_TIME.finditer(content):
        values = match.groupdict()
        target_date = base_date + timedelta(days={'今天': 0, '明天': 1, '后天': 2}[values['day']])
        results.update(_source_clock(values, target_date, zone))
    return results


class _Evaluator:
    def __init__(self, db, principal, *, clock, registry, client_factory):
        self.db, self.principal = db, principal
        self.clock = clock
        self.registry = registry
        self.client_factory = client_factory
        self.objects, self.records = {}, {}

    def now(self):
        return _utc(self.clock())

    def guard(self):
        revalidate_principal(self.db, self.principal, clock=self.clock)

    async def native(self, operation_id, *, path_args=None, query=None, body=None):
        # Domain adapters can select only a GET in the static domain catalogue.
        if (type(operation_id) is not str or not operation_id.startswith('GET ')
                or self.registry.spec_for_operation(operation_id) is None):
            raise HTTPException(501, '此事实尚未登记原查询')
        return await self.original_get(operation_id, path_args=path_args, query=query, body=body)

    async def original_get(self, operation_id, *, path_args=None, query=None, body=None):
        self.guard()
        reader = native_reader_for_principal(self.db, self.principal, (operation_id,),
                                              client_factory=self.client_factory)
        result = await reader(operation_id, path_args=path_args, query=query, body=body)
        self.guard()
        return result

    async def object(self, ref):
        key = (ref.type, ref.id)
        if key not in self.objects:
            self.objects[key] = await read_object(self.principal, ref,
                                                  native_reader=self.native, registry=self.registry)
        self.guard()
        return self.objects[key]

    async def case_record(self, ref):
        key = (ref.type, ref.id)
        if key not in self.records:
            generic = self.registry.spec_for_object('case')
            if generic is None:
                raise HTTPException(501, '原单查询尚未登记')
            adapter = self.registry.build(generic, native_reader=self.native)
            self.records[key] = await adapter.read_record(self.principal, ref)
        self.guard()
        return self.records[key]

    async def proposal(self, condition):
        from .business_assistant_models import AssistantProposal
        from .assistant_runtime_models import RunItem, WorkItem
        from .assistant_runtime_receipts import _checked_snapshot, lookup_reconciliation
        from .assistant_runtime_objects import resolve_result
        from .assistant_runtime_domains import FLOW_ACTION
        p = self.principal
        with _reader(self.db, p._read_session_factory) as reader:
            card = reader.scalar(select(AssistantProposal).where(
                AssistantProposal.id == condition.proposal_id, AssistantProposal.owner_id == p.actor_id,
                AssistantProposal.store_id == p.store_id, AssistantProposal.session_id == p.session_id,
                AssistantProposal.owner_role == p.role, AssistantProposal.access_version == p.access_version))
            if card is None:
                return _failure(condition, 'source_inaccessible')
            evidence = (EvidenceRef(source_type='proposal', source_id=card.id,
                                    native_version=card.version, observed_at=self.now()),)
            state = 'expired' if card.status == 'pending' and _utc(card.expires_at) <= self.now() else card.status
            facts = {'status': state, 'version': card.version, 'result_digest': _digest(card.result)}
            if state != 'succeeded':
                reason = ('receipt_unresolved' if state in {'executing', 'uncertain'} else 'proposal_' + state)
                return _failure(condition, reason, unknown=state in {'executing', 'uncertain'},
                                facts=facts, evidence=evidence)
            result = card.result
            if card.finished_at is None or type(result) is not dict:
                return _failure(condition, 'confirmed_result_missing', facts=facts, evidence=evidence)
            recorded_response = type(result.get('status')) is int and 200 <= result['status'] < 300
            confirmations = list(reader.scalars(select(RunItem).where(
                RunItem.kind == 'confirmation', RunItem.proposal_id == card.id)))
            if not confirmations and card.source_work_item_id is not None:
                return _failure(condition, 'confirmation_missing', facts=facts, evidence=evidence)
            if not recorded_response and not confirmations:
                return _failure(condition, 'confirmed_result_missing', facts=facts, evidence=evidence)
            # Legacy already-succeeded cards predate frozen confirmations. They
            # retain their original result; no new audit history is fabricated.
            if confirmations:
                if len(confirmations) != 1:
                    return _failure(condition, 'confirmation_mismatch', facts=facts, evidence=evidence)
                item = confirmations[0]
                facts['confirmation'] = {'id': item.id, 'version': item.version, 'status': item.status}
                try:
                    submitted = _checked_snapshot(item)
                except HTTPException:
                    return _failure(condition, 'confirmation_mismatch', facts=facts, evidence=evidence)
                if (item.status != 'succeeded' or item.finished_at is None
                        or item.work_item_id != card.source_work_item_id
                        or (submitted.operation_id, submitted.actor_id, submitted.store_id,
                            submitted.role, submitted.access_version)
                        != (card.operation_id, card.owner_id, card.store_id, card.owner_role, card.access_version)):
                    return _failure(condition, 'receipt_unresolved', facts=facts, evidence=evidence)
            if card.source_work_item_id is not None:
                work = reader.scalar(select(WorkItem).where(WorkItem.id == card.source_work_item_id))
                if (work is None or work.item_kind != 'prepare' or work.operation_id != card.operation_id
                        or (work.owner_id, work.store_id, work.session_id)
                        != (p.actor_id, p.store_id, p.session_id)):
                    return _failure(condition, 'confirmation_source_mismatch', facts=facts, evidence=evidence)
            # A reconciled native receipt is not a reconstructed HTTP response.
            # Only the recorded-response path uses the legacy result resolver.
            refs = (list(resolve_result(card.operation_id, card.result, registry=self.registry).object_refs)
                    if recorded_response else [])
            card_version, target = card.version, None
            payload = submitted.model_dump() if confirmations else card.payload
            if card.operation_id == FLOW_ACTION:
                case_id = (payload.get('path_args') or {}).get('case_id') if type(payload) is dict else None
                if type(case_id) is not int or case_id <= 0:
                    return _failure(condition, 'confirmation_source_mismatch', facts=facts, evidence=evidence)
                target = BusinessObjectRef(type='case', id=case_id)
                if any(ref.type == 'case' and ref != target for ref in refs):
                    return _failure(condition, 'confirmation_source_mismatch', facts=facts, evidence=evidence)
                if target not in refs:
                    refs.append(target)
        receipt_evidence = []
        if not recorded_response:
            lookup = await lookup_reconciliation(self.db, p, condition.proposal_id,
                clock=self.clock, client_factory=self.client_factory)
            self.guard()
            if lookup.status != 'confirmed_success':
                return _failure(condition,
                    'source_inaccessible' if lookup.status == 'inaccessible' else 'receipt_unresolved',
                    facts={**facts, 'receipt_status': lookup.status}, evidence=evidence)
            refs = list(lookup.object_refs)
            if target is not None and target not in refs:
                return _failure(condition, 'confirmation_source_mismatch', facts=facts, evidence=evidence)
            # The receipt helper proves the current card. Do not combine a
            # newer proof with the earlier version of a concurrently edited card.
            with _reader(self.db, p._read_session_factory) as reader:
                current = reader.scalar(select(AssistantProposal).where(
                    AssistantProposal.id == condition.proposal_id, AssistantProposal.owner_id == p.actor_id,
                    AssistantProposal.store_id == p.store_id, AssistantProposal.session_id == p.session_id,
                    AssistantProposal.owner_role == p.role, AssistantProposal.access_version == p.access_version))
                if current is None or current.version != card_version or current.status != 'succeeded':
                    return _failure(condition, 'receipt_unresolved', facts=facts, evidence=evidence)
            receipt_evidence = list(lookup.evidence_refs)
            facts['receipt'] = {'status': lookup.status,
                'object_refs': [ref.model_dump(mode='json') for ref in refs],
                'evidence_refs': [_without_observed_at(value.model_dump(mode='json'))
                                  for value in _evidence(receipt_evidence)]}
        # Recheck every actual bound original object, but do not manufacture a
        # target or deny a recorded 2xx solely because its display data is null.
        facts['objects'] = []
        observed = [*evidence, *receipt_evidence]
        for ref in refs:
            snapshot = await self.object(ref)
            facts['objects'].append(_snapshot_facts(snapshot))
            observed.extend(snapshot.evidence_refs)
        facts['objects'].sort(key=lambda value: _canonical(value['ref']))
        return _Observation(True, False, None, _evidence(observed),
                            {'condition': condition.model_dump(mode='json'), **facts}, True)

    async def action(self, condition):
        snapshot = await self.object(condition.object_ref)
        actions = [value for value in snapshot.available_actions if value.action_key == condition.action_key]
        facts = {'object': _snapshot_facts(snapshot)}
        if len(actions) != 1:
            return _failure(condition, 'action_unknown', facts=facts, evidence=snapshot.evidence_refs)
        action = actions[0]
        if action.availability != 'enabled':
            return _failure(condition, 'action_' + action.availability,
                            unknown=action.availability == 'unknown', facts=facts,
                            evidence=action.evidence_refs)
        if not action.evidence_refs:
            return _failure(condition, 'action_evidence_missing', facts=facts)
        return _Observation(True, False, None, _evidence(action.evidence_refs),
                            {'condition': condition.model_dump(mode='json'), **facts})

    async def task(self, condition):
        from .flow_models import Task
        with _reader(self.db, self.principal._read_session_factory) as reader:
            # Only an opaque routing ID is read here. Status/assignee evidence
            # comes exclusively from the original authorized full Case GET.
            case_id = reader.scalar(select(Task.case_id).where(
                Task.id == condition.task_id, Task.store_id == self.principal.store_id))
        if case_id is None:
            return _failure(condition, 'source_inaccessible')
        snapshot = await self.object(BusinessObjectRef(type='case', id=case_id))
        tasks = [task for task in snapshot.tasks if task.id == condition.task_id and task.case_id == case_id]
        if len(tasks) != 1:
            return _failure(condition, 'source_inaccessible')
        task = tasks[0]
        evidence = _evidence([EvidenceRef(source_type='task', source_id=task.id,
            native_version=task.version, observed_at=snapshot.observed_at)] + snapshot.evidence_refs)
        facts = {'condition': condition.model_dump(mode='json'), 'task': task.model_dump(mode='json'),
                 'case_version': snapshot.native_version}
        if task.status is None:
            return _Observation(False, True, 'task_status_unknown', evidence, facts)
        if task.status == 'cancelled':
            return _Observation(False, False, 'task_cancelled', evidence, facts)
        if task.status != condition.expected_status:
            return _Observation(False, False, 'task_state_mismatch', evidence, facts)
        if condition.expected_assignee_id is not None and task.assignee_id != condition.expected_assignee_id:
            return _Observation(False, task.assignee_id is None, 'task_assignee_mismatch', evidence, facts)
        return _Observation(True, False, None, evidence, facts, task.status == 'done')

    async def fact(self, condition):
        ref = condition.object_ref
        spec = self.registry.spec_for_fact(condition.fact_key)
        if spec is None:
            return _failure(condition, 'fact_not_registered')
        record = await self.case_record(ref) if ref.type == 'case' else None
        if not self.registry.supports_fact(condition.fact_key, ref.type,
                kind=record['kind'] if record else None, flow_version=record['flow_version'] if record else None):
            return _failure(condition, 'fact_not_applicable')
        # Both the object and the provider's exact fact read use current native
        # authorization; a valid object ID alone cannot establish the fact.
        snapshot = await self.object(ref)
        adapter = self.registry.build(spec, native_reader=self.native)
        value = await adapter.fact_snapshot(self.principal, ref, condition.fact_key)
        value = FactSnapshot.model_validate(value.model_dump() if isinstance(value, FactSnapshot) else value)
        if value.fact_key != condition.fact_key:
            raise HTTPException(502, '原事实返回的标识不一致')
        facts = {'condition': condition.model_dump(mode='json'),
                 'object': _snapshot_facts(snapshot),
                 'fact': _without_observed_at(value.model_dump(mode='json'))}
        if value.satisfied is None or value.satisfied and not value.evidence_refs:
            return _Observation(False, True, 'fact_unknown', _evidence(value.evidence_refs), facts)
        return _Observation(value.satisfied, False, None if value.satisfied else 'fact_not_satisfied',
                            _evidence(value.evidence_refs), facts, value.satisfied)

    async def due(self, condition):
        from .business_assistant_models import AssistantMessage
        from .config import settings
        p = self.principal
        with _reader(self.db, p._read_session_factory) as reader:
            message = reader.scalar(select(AssistantMessage).where(
                AssistantMessage.id == condition.source_message_id,
                AssistantMessage.session_id == p.session_id, AssistantMessage.store_id == p.store_id,
                AssistantMessage.role == 'user'))
            if message is None:
                return _failure(condition, 'time_source_missing')
            content, created_at = message.content, message.created_at
        facts = {'condition': condition.model_dump(mode='json'), 'source_digest': _digest(content),
                 'timezone': settings.timezone}
        evidence = (EvidenceRef(source_type='message', source_id=condition.source_message_id,
                                native_version=None, observed_at=self.now()),)
        if condition.at not in _source_times(content, settings.timezone, created_at):
            return _Observation(False, True, 'explicit_time_missing', evidence, facts)
        reached = self.now() >= condition.at
        facts['reached'] = reached
        return _Observation(reached, False, None if reached else 'due_at_pending', evidence, facts)

    async def condition(self, condition):
        self.guard()
        handler = {'proposal_succeeded': self.proposal, 'native_action_available': self.action,
                   'native_task_state': self.task, 'fact_exists': self.fact, 'due_at': self.due}[condition.type]
        try:
            result = await handler(condition)
        except HTTPException as exc:
            result = _unavailable(condition, exc)
        except (ValidationError, ValueError, TypeError, OverflowError):
            result = _failure(condition, 'source_invalid')
        self.guard()
        return result


def _read_rows(evaluator, work_ids, plan_id, step_id):
    """Detach exact current read intents and successful attempt identities."""
    from .assistant_runtime_models import PlanStep, Run, RunItem, WorkItem
    from .business_assistant_models import AssistantProposal, AssistantWorkPlan
    p = evaluator.principal
    with _reader(evaluator.db, p._read_session_factory) as reader:
        plan = reader.scalar(select(AssistantWorkPlan).where(
            AssistantWorkPlan.id == plan_id, AssistantWorkPlan.owner_id == p.actor_id,
            AssistantWorkPlan.store_id == p.store_id, AssistantWorkPlan.session_id == p.session_id))
        step = reader.scalar(select(PlanStep).where(PlanStep.id == step_id, PlanStep.plan_id == plan_id))
        if (plan is None or step is None or plan.engine_version != 2 or plan.status != 'active'
                or p.plan_id is not None and (p.plan_id != plan.id or p.goal_version != plan.goal_version)):
            return None, 'read_scope_changed'
        rows = list(reader.scalars(select(WorkItem).where(
            WorkItem.plan_id == plan_id, WorkItem.step_id == step_id,
            WorkItem.intent_version == step.intent_version).order_by(WorkItem.id)))
        if not rows or {row.id for row in rows} != set(work_ids) or step.proposal_id is not None:
            return None, 'read_intent_changed'
        detached = []
        for work in rows:
            if ((work.owner_id, work.store_id, work.session_id) != (p.actor_id, p.store_id, p.session_id)
                    or work.item_kind != 'read' or work.status != 'settled'
                    or reader.scalar(select(AssistantProposal.id).where(
                        AssistantProposal.source_work_item_id == work.id)) is not None
                    or reader.scalar(select(WorkItem.id).where(WorkItem.supersedes_id == work.id)) is not None):
                return None, 'read_not_completed'
            item = reader.scalar(select(RunItem).where(RunItem.work_item_id == work.id)
                .order_by(RunItem.created_at.desc(), RunItem.attempt_no.desc(), RunItem.id.desc()).limit(1))
            run = reader.scalar(select(Run).where(Run.id == item.run_id)) if item is not None else None
            if (item is None or run is None or item.kind not in {'tool', 'batch_row'}
                    or item.status != 'succeeded' or item.finished_at is None or item.proposal_id is not None
                    or (run.owner_id, run.store_id, run.session_id, run.plan_id, run.goal_version)
                    != (p.actor_id, p.store_id, p.session_id, plan.id, plan.goal_version)):
                return None, 'read_attempt_unresolved'
            intent = deepcopy(work.validated_intent)
            if (type(intent) is not dict or intent.get('operation_id') != work.operation_id
                    or type(work.operation_id) is not str or not work.operation_id.startswith('GET ')
                    or type(intent.get('path_args')) is not dict or type(intent.get('query')) is not dict
                    or intent.get('body') not in (None, {})):
                return None, 'read_intent_invalid'
            # Original schemas, permissions and route dispatch are checked by
            # original_get. Never reinterpret a tool string as a URL or SQL.
            detached.append({'work_id': work.id, 'work_version': work.version,
                'intent_version': work.intent_version, 'intent': intent,
                'attempt_id': item.id, 'attempt_version': item.version,
                'plan_goal_version': plan.goal_version, 'step_intent_version': step.intent_version})
        return detached, None


async def _read_completion(evaluator, work_ids, plan_id, step_id):
    try:
        if type(work_ids) is not tuple or not work_ids or len(set(work_ids)) != len(work_ids):
            raise ValueError('Expected exact current read WorkItem tuple')
        uuid_adapter = TypeAdapter(UUIDText)
        plan_id, step_id = uuid_adapter.validate_python(plan_id), uuid_adapter.validate_python(step_id)
        work_ids = tuple(uuid_adapter.validate_python(value) for value in work_ids)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, '只读完成必须指定完整的当前事项步骤和读取记录') from None

    def failed(reason, facts=None):
        return [_Observation(False, True, reason, (), {'read_work_item_ids': sorted(work_ids), **(facts or {})})]

    rows, reason = _read_rows(evaluator, work_ids, plan_id, step_id)
    if rows is None:
        return failed(reason)
    observations = []
    for row in rows:
        intent = row['intent']
        try:
            response = await evaluator.original_get(intent['operation_id'],
                path_args=deepcopy(intent['path_args']), query=deepcopy(intent['query']), body=None)
        except HTTPException as exc:
            evaluator.guard()
            return failed('read_source_inaccessible' if exc.status_code in {401, 403, 404}
                          else 'read_source_unavailable', {'http_status': exc.status_code})
        if type(response) is not dict or type(response.get('status')) is not int:
            return failed('read_source_invalid')
        status = response['status']
        if not 200 <= status < 300:
            return failed('read_source_inaccessible' if status in {401, 403, 404}
                          else 'read_source_unavailable', {'http_status': status})
        if response.get('truncated') or type(response.get('data')) is dict and response['data'].get('truncated'):
            return failed('read_source_incomplete')
        try:
            # This is original business data, not our snapshot envelope. A
            # native field named observed_at may itself be meaningful, so only
            # Runtime evidence/snapshot observation timestamps are excluded.
            response_digest = _digest(response.get('data'))
            intent_digest = _digest(intent)
        except (ValueError, TypeError, OverflowError):
            return failed('read_source_invalid')
        evidence = (EvidenceRef(source_type='object',
            source_id=BusinessObjectRef(type='report_query', id=row['work_id']),
            native_version=row['work_version'], observed_at=evaluator.now()),)
        observations.append(_Observation(True, False, 'read_completed', evidence,
            {'read_work_item_id': row['work_id'], 'work_version': row['work_version'],
             'attempt_id': row['attempt_id'], 'attempt_version': row['attempt_version'],
             'intent_digest': intent_digest, 'result_digest': response_digest}, True))
    # Re-query committed private records after all awaits. A supersede, new
    # attempt or goal edit cannot turn earlier query results into current proof.
    current, reason = _read_rows(evaluator, work_ids, plan_id, step_id)
    if current != rows:
        return failed(reason or 'read_intent_changed')
    evaluator.guard()
    return observations


async def evaluate_conditions(db, principal, conditions, *, purpose: Literal['preparation', 'completion'] = 'preparation',
                              read_work_item_ids=None, plan_id=None, step_id=None,
                              clock=None, registry=None, client_factory=None):
    """Evaluate one AND set, always by fresh reads, without changing the caller TX.

    Dependencies/whole-step card states are additionally checked by plans. The
    optional empty-completion read exception needs the exact current WorkItem
    set and its persisted Plan/Step. It means query completion only.
    """
    from .business_assistant_service import require_preparation_read_phase
    require_preparation_read_phase(db)
    if purpose not in {'preparation', 'completion'} or type(conditions) is not list:
        raise HTTPException(422, '条件用途或列表不正确')
    try:
        checked = TypeAdapter(list[Condition]).validate_python(deepcopy(conditions))
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, '请使用已登记的有限条件类型') from None
    revalidate_principal(db, principal, clock=clock)
    evaluator = _Evaluator(db, principal, clock=clock or principal._clock,
                           registry=domain_registry() if registry is None else registry,
                           client_factory=client_factory)
    observations = []
    for condition in checked:
        observations.append(await evaluator.condition(condition))
    if purpose == 'completion' and not checked and read_work_item_ids is not None:
        observations = await _read_completion(evaluator, read_work_item_ids, plan_id, step_id)
    evaluator.guard()
    return _result(observations, purpose)
