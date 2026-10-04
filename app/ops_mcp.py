"""Loopback Aliyun operations MCP: bounded reads, review records and mail handoff.

Fixed 2025-11-25 JSON tools profile; not an OAuth or public MCP gateway.
The model role cannot submit mail, change reviews, execute shell, or write code.
"""
import hmac
import json
import time
from functools import lru_cache
from pathlib import Path
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
import httpx

from .ops_config import load_config, private_json
from .ops_context import SourceContext
from .ops_store import OpsStore


def tool(name, description, properties, required=()):
    return {'name': name, 'description': description, 'inputSchema': {'type': 'object',
            'properties': properties, 'required': list(required), 'additionalProperties': False}}


TEXT = {'type': 'string'}
READ_TOOLS = [
    tool('source_snapshot', 'Read current deployed code release and architecture.', {}),
    tool('search_code', 'Literal search over hash-verified source, never secrets or data.', {'query': TEXT}, ['query']),
    tool('read_code', 'Read at most 100 lines of an exact source inventory path.',
         {'path': TEXT, 'start_line': {'type': 'integer'}, 'line_count': {'type': 'integer'}}, ['path']),
    tool('search_memory', 'Read previous authenticated Cutie review conclusions and PR references.', {'query': TEXT}, ['query']),
    tool('service_health', 'Read only the fixed HuaKangOS web health endpoint.', {}),
]
REVIEW_TOOLS = [
    tool('list_change_reviews', 'List operations requests awaiting review and their truthful workflow state.', {}),
    tool('get_change_review', 'Read one feedback, source-bound proposal and delivery receipt.', {'job_id': TEXT}, ['job_id']),
    tool('record_change_review', 'Append Cutie review result; records a PR, never merges or deploys.',
         {'job_id': TEXT, 'verdict': {'type': 'string', 'enum': ['pr_opened', 'needs_information', 'declined']},
          'summary': TEXT, 'pr_url': TEXT}, ['job_id', 'verdict', 'summary', 'pr_url']),
    tool('retry_analysis', 'Explicitly retry a failed, unmailed analysis after correcting its cause. Never retries mail.',
         {'job_id': TEXT, 'expected_error': TEXT, 'reason': TEXT}, ['job_id', 'expected_error', 'reason']),
]
SEND_TOOL = tool('enqueue_change_review', 'Deliver only an already validated durable proposal to the configured Cutie mailbox.',
                 {'job_id': TEXT}, ['job_id'])


@lru_cache(maxsize=1)
def runtime():
    config = load_config()
    return config, OpsStore(config['state_db']), SourceContext(config['source_root'])


class McpClient:
    def __init__(self, url, token, timeout=90):
        self.url, self.token, self.timeout = url, token, timeout

    async def rpc(self, method, params):
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False, trust_env=False) as client:
            response = await client.post(self.url, headers={'Authorization': 'Bearer ' + self.token,
                'Accept': 'application/json, text/event-stream',
                'MCP-Protocol-Version': '2025-11-25'}, json={'jsonrpc': '2.0', 'id': str(uuid.uuid4()),
                                                          'method': method, 'params': params})
        if response.status_code != 200 or len(response.content) > 250_000:
            raise RuntimeError('MCP service request failed')
        data = response.json()
        if 'error' in data or 'result' not in data:
            raise RuntimeError('MCP tool request failed')
        return data['result']

    async def call(self, name, arguments):
        result = await self.rpc('tools/call', {'name': name, 'arguments': arguments})
        if result.get('isError'):
            raise RuntimeError('MCP tool failed')
        if 'structuredContent' in result:
            return result['structuredContent']
        # Both bridges carry their same object in text for standard MCP clients.
        content = result.get('content', [])
        if len(content) == 1 and content[0].get('type') == 'text':
            return json.loads(content[0]['text'])
        raise RuntimeError('Invalid MCP tool response')


async def deliver(config, store, job_id):
    job = store.get(job_id)
    if job['status'] not in {'review_ready', 'notifying'}:
        return {'status': job['status'], 'mail': job['mail']}
    mail_config = private_json(config['mail_client_file'])
    client = McpClient(config['mail_mcp_url'], mail_config['token'])
    event_id = 'huakangos-ops:' + job_id
    first_attempt = store.begin_notification(job_id)
    if not first_attempt:
        current = store.get(job_id)
        if current['status'] != 'notifying':
            return {'status': current['status'], 'mail': current['mail']}
        if (current.get('lease_until') or 0) > time.time():
            return {'status': 'sending', 'event_id': event_id}
        # Reconcile ambiguous/crashed sends by stable ID; never enqueue a second send.
        result = await client.call('get_change_review', {'event_id': event_id})
        if result.get('status') in {'queued', 'sending'} or result.get('delivery_in_progress'):
            return result
        if result.get('status') in {'not_found', 'missing'}:
            result = {'status': 'uncertain', 'event_id': event_id, 'reason': 'notification_interrupted'}
    else:
        report = job['report']
        try:
            result = await client.call('enqueue_change_review', {'event_id': event_id, 'job_id': job_id,
                'title': job['title'], 'release_id': job['release_id'], 'base_sha': report['base_sha'],
                'report': {key: report[key] for key in ('summary', 'evidence', 'proposed_changes',
                                                       'acceptance_checks', 'risk', 'classification')}})
        except (RuntimeError, httpx.HTTPError, ValueError):
            # Keep notifying so the next pass queries the existing outbox instead of resending.
            return {'status': 'uncertain', 'event_id': event_id, 'reason': 'mail_response_unknown'}
    if result.get('status') not in {'queued', 'sending'}:
        store.notification_result(job_id, result)
    return result


async def dispatch(name, args, role):
    config, store, context = runtime()
    if name == 'source_snapshot':
        return context.snapshot()
    if name == 'search_code':
        return context.search(**args)
    if name == 'read_code':
        return context.read(**args)
    if name == 'search_memory':
        query = args['query']
        if not isinstance(query, str) or not 1 <= len(query) <= 120:
            raise ValueError('Invalid memory query')
        return {'records': store.search_memory(query), 'source': 'authenticated_cutie_reviews'}
    if name == 'service_health':
        async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client:
            response = await client.get(config['web_health_url'])
        return {'service': 'huakangos-web', 'http_status': response.status_code, 'healthy': response.status_code == 200}
    if name == 'list_change_reviews':
        return {'jobs': store.list_jobs()}
    if name == 'get_change_review':
        return store.get(str(uuid.UUID(args['job_id'])))
    if name == 'record_change_review' and role == 'reviewer':
        return store.record_review(**args)
    if name == 'retry_analysis' and role == 'reviewer':
        return store.retry_analysis(**args)
    if name == 'enqueue_change_review' and role == 'worker':
        return await deliver(config, store, str(uuid.UUID(args['job_id'])))
    raise ValueError('Tool is not available for this role')


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get('/health')
def health():
    _, _, context = runtime()
    return {'ok': True, 'release_id': context.release_id}


@app.post('/mcp')
async def mcp(request: Request):
    config, _, _ = runtime()
    authorization = request.headers.get('authorization', '')
    if not authorization.isascii():
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    role = next((role for role in ('agent', 'worker', 'reviewer')
                 if hmac.compare_digest(authorization, 'Bearer ' + config[role + '_token'])), None)
    if role is None:
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    if request.headers.get('origin') or request.headers.get('sec-fetch-site') == 'cross-site':
        return JSONResponse({'error': 'browser access is not supported'}, status_code=403)
    data = await request.body()
    if len(data) > 100_000:
        return JSONResponse({'error': 'request too large'}, status_code=413)
    message = {}
    try:
        message = json.loads(data)
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0':
            raise ValueError('Invalid RPC envelope')
        method, params = message.get('method'), message.get('params', {})
        if not isinstance(params, dict):
            raise ValueError('Invalid RPC parameters')
        available = READ_TOOLS + (REVIEW_TOOLS if role == 'reviewer' else [SEND_TOOL] if role == 'worker' else [])
        if method == 'initialize':
            result = {'protocolVersion': '2025-11-25', 'capabilities': {'tools': {}},
                      'serverInfo': {'name': 'huakangos-aliyun-ops', 'version': '1.0'}}
        elif method == 'notifications/initialized':
            return Response(status_code=202)
        elif method == 'ping':
            result = {}
        elif method == 'tools/list':
            result = {'tools': available}
        elif method == 'tools/call':
            name, args = params.get('name'), params.get('arguments', {})
            definition = next((t for t in available if t['name'] == name), None)
            if not definition or not isinstance(args, dict):
                raise ValueError('Unavailable tool')
            schema = definition['inputSchema']
            if set(args) - set(schema['properties']) or set(schema['required']) - set(args):
                raise ValueError('Invalid arguments')
            output = await dispatch(name, args, role)
            result = {'content': [{'type': 'text', 'text': json.dumps(output, ensure_ascii=False)}],
                      'structuredContent': output, 'isError': False}
        else:
            return JSONResponse({'jsonrpc': '2.0', 'id': message.get('id'),
                                 'error': {'code': -32601, 'message': 'Method not available'}})
        return JSONResponse({'jsonrpc': '2.0', 'id': message.get('id'), 'result': result})
    except (KeyError, TypeError, ValueError, RuntimeError, OSError, httpx.HTTPError):
        # No exception strings: providers may embed URLs, credentials or feedback.
        return JSONResponse({'jsonrpc': '2.0', 'id': message.get('id') if isinstance(message, dict) else None,
                             'error': {'code': -32602, 'message': 'Request rejected or service unavailable'}})
