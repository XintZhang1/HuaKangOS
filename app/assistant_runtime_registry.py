"""Static assistant tools and domain adapters; never a business permission grant.

The tool catalogue retains its original schemas and handlers. Native operations
still belong to the reviewed gateway/OpenAPI catalogue and original API guards.
Adapters are registered by application code, never loaded from model arguments.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from functools import lru_cache
import json
import math
import re
from typing import Callable, Literal, Protocol, get_args

from fastapi import HTTPException

from .assistant_runtime_schemas import BusinessObjectType


ToolKind = Literal['read', 'prepare', 'plan']


def _invalid():
    raise HTTPException(422, '工具调用格式不完整或字段不正确，请重新核对') from None


def _json_copy(value):
    """Detach finite JSON without coercing native values or truncating rows."""
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            _invalid()
        return value
    if type(value) is str:
        try:
            value.encode('utf-8')
        except UnicodeEncodeError:
            _invalid()
        return value
    if type(value) is list:
        return [_json_copy(item) for item in value]
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            _invalid()
        return {_json_copy(key): _json_copy(item) for key, item in value.items()}
    _invalid()


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


def _parse_arguments(value, limit):
    if type(value) is not str or not value.strip() or len(value) > limit:
        _invalid()
    try:
        value.encode('utf-8')
        result = json.loads(value, object_pairs_hook=_unique_pairs,
                            parse_constant=lambda _: _invalid())
        if type(result) is not dict:
            _invalid()
        return _json_copy(result)
    except (ValueError, TypeError, OverflowError, RecursionError):
        _invalid()


def _field_matches(value, schema):
    """The small, fixed subset used by the existing legacy tool envelopes."""
    kind = schema.get('type')
    kinds = {'string': str, 'object': dict, 'integer': int,
             'array': list, 'boolean': bool}
    if kind is not None and (kind not in kinds or type(value) is not kinds[kind]):
        return False
    if 'enum' in schema and not any(type(value) is type(item) and value == item for item in schema['enum']):
        return False
    if 'minimum' in schema and (type(value) is not int or value < schema['minimum']):
        return False
    if 'maximum' in schema and (type(value) is not int or value > schema['maximum']):
        return False
    if 'minItems' in schema and (type(value) is not list or len(value) < schema['minItems']):
        return False
    if 'maxItems' in schema and (type(value) is not list or len(value) > schema['maxItems']):
        return False
    return True


def _legacy_arguments(name, args, schema):
    properties = schema['properties']
    if (set(args) - set(properties) or set(schema.get('required', ())) - set(args)
            or any(not _field_matches(value, properties[key]) for key, value in args.items())):
        _invalid()
    # Preserve the native legacy batch boundary: the entire row envelope is
    # checked first, but questions and native fields fail within their own row.
    # Questions are still checked/normalized by the original forms helpers.
    if name == 'prepare_operations':
        for row in args['rows']:
            if (type(row) is not dict or set(row) - {'body', 'summary', 'questions'}
                    or type(row.get('body')) is not dict
                    or type(row.get('summary')) is not str or not row['summary'].strip()):
                _invalid()
    return args


@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: ToolKind
    schema: dict
    handler: Callable
    description: str = ''
    argument_validator: Callable | None = None


@dataclass(frozen=True)
class ValidatedToolCall:
    id: str
    name: str
    arguments: dict
    kind: ToolKind


class ToolRegistry:
    def __init__(self, *, max_calls=200, max_argument_chars=60000):
        self._specs = {}
        self._sealed = False
        self.max_calls = max_calls
        self.max_argument_chars = max_argument_chars

    def register(self, spec: ToolSpec):
        if self._sealed:
            raise ValueError('Tool registry is sealed')
        if (not isinstance(spec, ToolSpec) or type(spec.name) is not str or not spec.name
                or spec.kind not in {'read', 'prepare', 'plan'} or not callable(spec.handler)
                or type(spec.schema) is not dict or spec.schema.get('type') != 'object'
                or spec.schema.get('additionalProperties') is not False):
            raise ValueError('Invalid static tool registration')
        if spec.name in self._specs:
            raise ValueError('Duplicate static tool registration')
        self._specs[spec.name] = replace(spec, schema=deepcopy(spec.schema))

    def seal(self):
        self._sealed = True
        return self

    def spec(self, name):
        if type(name) is not str or name not in self._specs:
            raise HTTPException(422, '业务助手只能查询资料、保存计划和准备业务表单，不支持此工具')
        item = self._specs[name]
        return replace(item, schema=deepcopy(item.schema))

    def definitions(self):
        return [{'type': 'function', 'function': {
            'name': spec.name, 'description': spec.description,
            'parameters': deepcopy(spec.schema),
        }} for spec in self._specs.values()]

    def validate_arguments(self, name, args):
        spec = self.spec(name)
        if type(args) is not dict:
            _invalid()
        try:
            checked = _json_copy(args)
            if len(json.dumps(checked, ensure_ascii=False, separators=(',', ':'), allow_nan=False)) > self.max_argument_chars:
                _invalid()
            if spec.argument_validator is not None:
                return spec.argument_validator(name, checked)
            return _legacy_arguments(name, checked, spec.schema)
        except (ValueError, TypeError, OverflowError, RecursionError):
            _invalid()

    def validate_calls(self, calls):
        """Validate the complete model response before dispatching any call.

        Single-call server/MCP callers use validate_arguments and need no model
        tool-call ID. Native business field failures remain with the old handler.
        """
        if type(calls) is not list or len(calls) > self.max_calls:
            _invalid()
        seen = set()
        result = []
        for call in calls:
            if (type(call) is not dict or set(call) != {'id', 'type', 'function'}
                    or type(call['id']) is not str or not call['id'].strip()
                    or call['id'] in seen or call['type'] != 'function'):
                _invalid()
            _json_copy(call['id'])
            seen.add(call['id'])
            fn = call['function']
            if type(fn) is not dict or set(fn) != {'name', 'arguments'}:
                _invalid()
            spec = self.spec(fn['name'])
            args = self.validate_arguments(spec.name, _parse_arguments(fn['arguments'], self.max_argument_chars))
            result.append(ValidatedToolCall(call['id'], spec.name, args, spec.kind))
        return tuple(result)


def _handler(name):
    async def registered(db, request, user, thread_id, args, config, *, resolve_only=False):
        from .business_assistant_service import _run_registered_tool
        return await _run_registered_tool(db, request, user, thread_id, name, args, config,
                                          resolve_only=resolve_only)
    return registered


# These classify model tools, not native business action names or permissions.
# record_issue writes only assistant issue records. Kind does not redefine the
# existing MCP readOnlyHint or promise that a read leaves assistant metadata idle.
_TOOL_KINDS = {
    'list_operations': 'read', 'inspect_operation': 'read', 'read_data': 'read',
    'find_cases': 'read', 'get_case': 'read', 'find_workflows': 'read',
    'prepare_case_action': 'prepare', 'prepare_customer_contact': 'prepare',
    'prepare_operation': 'prepare', 'prepare_operations': 'prepare',
    'record_issue': 'plan', 'find_business_objects': 'read',
    'discover_business_forms': 'read', 'inspect_business_form': 'read',
    'prepare_business_form': 'prepare', 'prepare_business_batch': 'prepare',
    'save_work_plan': 'plan', 'get_work_status': 'read',
}


@lru_cache(maxsize=2)
def _registry_for_profile(profile):
    from .business_assistant_service import TOOLS, HARD_TOOLS, MODEL_ARGUMENT_CHARS
    from .business_assistant_business_tools import SPECS, tool_definitions, validate
    definitions = (tool_definitions() if profile == 'business_v1' else []) + TOOLS
    registry = ToolRegistry(max_calls=HARD_TOOLS, max_argument_chars=MODEL_ARGUMENT_CHARS)
    for definition in definitions:
        fn = definition['function']
        name = fn['name']
        if name not in _TOOL_KINDS:
            raise ValueError('Unclassified static assistant tool')
        registry.register(ToolSpec(name=name, kind=_TOOL_KINDS[name],
            schema=fn['parameters'], description=fn['description'], handler=_handler(name),
            argument_validator=validate if name in SPECS else None))
    return registry.seal()


def registry_for_config(config):
    # Only this static profile affects the catalogue; credentials/config objects
    # never become cache keys or persist in registry closures.
    return _registry_for_profile('business_v1' if config.tool_profile == 'business_v1' else 'legacy')


async def dispatch(db, request, user, thread_id, name, args, config, *, resolve_only=False):
    if type(resolve_only) is not bool:
        raise TypeError('resolve_only must be a server boolean')
    registry = registry_for_config(config)
    checked = registry.validate_arguments(name, args)
    return await registry.spec(name).handler(db, request, user, thread_id, checked, config,
                                            resolve_only=resolve_only)


class DomainAdapter(Protocol):
    async def read_snapshot(self, principal, ref): ...
    def extract_result(self, operation_id, response): ...
    async def read_receipt(self, principal, submission): ...
    async def fact_snapshot(self, principal, ref, fact_key): ...


@dataclass(frozen=True)
class DomainAdapterSpec:
    name: str
    factory: Callable
    object_types: tuple[str, ...]
    operation_ids: tuple[str, ...] = ()
    fact_keys: tuple[str, ...] = ()
    kind_versions: tuple[tuple[str, str, int], ...] = ()
    fallback_object_types: tuple[str, ...] = ()
    # Fact applicability does not claim the shared object's snapshot selector.
    fact_kind_versions: tuple[tuple[str, str, int], ...] = ()


class DomainRegistry:
    """Static provider keys; unknown lookups return None, explicitly unsupported.

    A selector's kind/version must come from an authorized original read, never
    the model. Shared object namespaces do not themselves choose a provider.
    A generic provider opts into fallback_object_types explicitly. Fact/operation
    selection uses exact registered keys and never silently falls back.
    """
    def __init__(self):
        self._specs = {}
        self._objects = {}
        self._operations = {}
        self._facts = {}
        self._selectors = {}
        self._sealed = False

    def register(self, spec: DomainAdapterSpec):
        if self._sealed:
            raise ValueError('Domain registry is sealed')
        if (not isinstance(spec, DomainAdapterSpec) or type(spec.name) is not str or not spec.name
                or not callable(spec.factory) or spec.name in self._specs):
            raise ValueError('Invalid or duplicate domain registration')
        fields = (spec.object_types, spec.operation_ids, spec.fact_keys,
                  spec.kind_versions, spec.fallback_object_types, spec.fact_kind_versions)
        if any(type(values) is not tuple or len(values) != len(set(values)) for values in fields):
            raise ValueError('Domain keys must be unique static tuples')
        if not spec.object_types or any(value not in get_args(BusinessObjectType) for value in spec.object_types):
            raise ValueError('Unsupported object type registration')
        if any(type(key) is not str or not re.fullmatch(r'(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /api/[^\s?#]+', key)
               for key in spec.operation_ids):
            raise ValueError('Invalid operation registration')
        if any(type(key) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*', key)
               for key in spec.fact_keys):
            raise ValueError('Invalid fact registration')
        if any(value not in spec.object_types for value in spec.fallback_object_types):
            raise ValueError('Fallback outside registered object types')
        for selector in spec.kind_versions + spec.fact_kind_versions:
            if (type(selector) is not tuple or len(selector) != 3
                    or selector[0] not in spec.object_types or type(selector[1]) is not str or not selector[1]
                    or type(selector[2]) is not int or selector[2] < 1):
                raise ValueError('Invalid native kind/version selector')
        if (spec.fact_keys and 'case' in spec.object_types
                and not any(selector[0] == 'case'
                            for selector in spec.kind_versions + spec.fact_kind_versions)):
            raise ValueError('Case facts require explicit native kind/version applicability')
        assignments = ((self._objects, spec.fallback_object_types),
                       (self._operations, spec.operation_ids), (self._facts, spec.fact_keys),
                       (self._selectors, spec.kind_versions))
        if any(key in mapping for mapping, keys in assignments for key in keys):
            raise ValueError('Domain provider key already registered')
        # All conflicts are checked before any index changes.
        self._specs[spec.name] = spec
        for mapping, keys in assignments:
            for key in keys:
                mapping[key] = spec
        return spec

    def seal(self):
        self._sealed = True
        return self

    def spec_for_object(self, object_type, *, kind=None, flow_version=None):
        if type(object_type) is not str:
            return None
        if type(kind) is str and type(flow_version) is int:
            selected = self._selectors.get((object_type, kind, flow_version))
            if selected is not None:
                return selected
        return self._objects.get(object_type)

    def spec_for_operation(self, operation_id):
        return self._operations.get(operation_id) if type(operation_id) is str else None

    def spec_for_fact(self, fact_key):
        return self._facts.get(fact_key) if type(fact_key) is str else None

    def supports_fact(self, fact_key, object_type, *, kind=None, flow_version=None):
        """Check a fixed fact provider against an authorized native identity."""
        spec = self.spec_for_fact(fact_key)
        if spec is None or type(object_type) is not str or object_type not in spec.object_types:
            return False
        if object_type != 'case':
            return True
        if type(kind) is not str or type(flow_version) is not int:
            return False
        return (object_type, kind, flow_version) in spec.kind_versions + spec.fact_kind_versions

    def build(self, spec, *, native_reader, receipt_reader=None):
        if (not isinstance(spec, DomainAdapterSpec) or self._specs.get(spec.name) is not spec
                or not callable(native_reader) or receipt_reader is not None and not callable(receipt_reader)):
            raise ValueError('Adapter requires a registered provider and controlled readers')
        return spec.factory(native_reader=native_reader, receipt_reader=receipt_reader)


@lru_cache(maxsize=1)
def domain_registry():
    """The application-owned provider catalogue, fixed before first use.

    Later domain milestones add reviewed registrations here before sealing.
    Model input cannot supply factories, selector kinds or registration keys.
    """
    from .assistant_runtime_domains import register_adapters
    registry = DomainRegistry()
    register_adapters(registry)
    return registry.seal()


def make_native_reader(transport, user, allowed_operations):
    """Bind a server-controlled GET transport to a finite adapter read surface.

    The transport must revalidate the principal and execute the original route;
    static role checks here are not a substitute for tenant/object authorization.
    This wrapper neither commits nor uses legacy read_data's committing helper.
    """
    if (not callable(transport) or type(allowed_operations) not in (tuple, frozenset)
            or any(type(op) is not str or not re.fullmatch(r'GET /api/[^\s?#]+', op)
                   for op in allowed_operations)):
        raise ValueError('Native reader requires fixed server GET operations')
    allowed = frozenset(allowed_operations)

    async def read(operation_id, *, path_args=None, query=None, body=None):
        from . import business_assistant_gateway as gateway
        if type(operation_id) is not str or operation_id not in allowed or body not in (None, {}):
            raise HTTPException(403, '此读取器只允许已登记的原业务查询')
        if path_args is not None and type(path_args) is not dict or query is not None and type(query) is not dict:
            _invalid()
        declared = gateway.inspect_operation(operation_id)
        if declared['method'] != 'GET' or declared['write'] or gateway.role_may_read(user.role, declared) is False:
            raise HTTPException(403, '当前岗位不能使用此原业务查询')
        try:
            path = _json_copy(path_args if path_args is not None else {})
            params = _json_copy(query if query is not None else {})
        except (ValueError, TypeError, OverflowError, RecursionError):
            _invalid()
        checked = gateway.validate_operation(operation_id, path, params, None)
        return await transport(operation_id, path_args=deepcopy(checked['path_args']),
                               query=deepcopy(checked['query']), body=None)

    return read
