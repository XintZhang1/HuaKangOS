"""Shared legacy/Runtime provider transport and safe, truthful usage counters.

No SDK, persistence, logging, model fallback or business execution lives here.
Reasoning stays in the returned in-memory current tool chain, never in usage.
Service imports are deliberately lazy to retain its compatibility wrappers and
the existing fixtures' dynamic provider_request/constants/httpx interception.
"""
import asyncio
from dataclasses import dataclass, field
import json
import math
import re
from time import monotonic

import httpx
from fastapi import HTTPException


class ModelProtocolError(HTTPException):
    """A rejected provider reply must not be classified as a transport retry.

    Retain the legacy HTTP 503 boundary, without attaching raw model content.
    Runtime can stop this attempt while preserving already validated cards.
    """
    def __init__(self, detail):
        super().__init__(status_code=503, detail=detail)


class ModelToolArgumentsInvalid(ModelProtocolError):
    """One complete non-stream reply rejected only for argument JSON syntax."""
    def __init__(self):
        super().__init__('工具参数JSON语法无效，整个片段的工具未执行。')


class SafeDeltas:
    """Hold partial credential tokens until they can be redacted as a whole."""
    def __init__(self,sanitize):self.pending='';self.sanitize=sanitize
    def feed(self,text,final=False):
        self.pending+=text
        cut=len(self.pending)
        if not final:
            # Ordinary Chinese characters can leave immediately. Hold only the
            # current ASCII token and a possible credential-label prefix.
            tail=re.search(r'[A-Za-z0-9_+\-]+$',self.pending)
            if tail:cut=min(cut,tail.start())
            lowered=self.pending.lower()
            for keyword in ('密码','口令','验证码','password','api_key','api-key','api key','secret','bearer','sk-','tp-'):
                for length in range(1,min(len(keyword),len(lowered))+1):
                    if lowered.endswith(keyword[:length]):cut=min(cut,len(lowered)-length)
            label=re.search(r'(?i)(?:Bearer\s*|(?:密码|口令|验证码|password|api[_ -]?key|secret)\s*(?:[:：=]|是)?\s*)$',self.pending)
            if label:cut=min(cut,label.start())
            pattern=r'(?i)(?:\b(?:sk|tp)-[A-Za-z0-9_-]*|Bearer\s+[^\s"\']*|(?:密码|口令|验证码|password|api[_ -]?key|secret)\s*(?:[:：=]|是)\s*[^\s,，;；"\']*)'
            for match in re.finditer(pattern,self.pending):
                if match.start()<cut<match.end() or match.end()==len(self.pending):cut=min(cut,match.start())
        ready,self.pending=self.pending[:cut],self.pending[cut:]
        return self.sanitize(ready,max(1,len(ready))) if ready else ''


def provider_error(status):
    if status in {401,403}:return '业务助手连接凭据无效，请联系管理员检查'
    if status==402:return '业务助手额度不足，请联系管理员补充额度'
    if status==429:return '业务助手暂时繁忙，请稍后再试'
    return '业务助手暂时无法连接，请稍后再试'


def provider_request(config, messages, thinking=False, stream=False):
    """Original fixed endpoints/body; never impose a generation-token limit."""
    from . import business_assistant_service as service
    body={'model':config.model,'messages':messages,'tools':service.tools_for_config(config),
          'tool_choice':'auto','thinking':{'type':'enabled' if thinking else 'disabled'}}
    if stream:body['stream']=True
    # Business answers must reconcile native facts across tools. The low-effort
    # DeepSeek comparison still confused candidate lists with current inventory.
    if thinking:body['reasoning_effort']='high' if config.provider=='deepseek' else 'low'
    else:body['temperature']=0.3 if config.provider=='mimo' else 0.1
    if config.provider=='deepseek':
        endpoint='https://api.deepseek.com/chat/completions'
    elif config.provider=='mimo' and config.api_kind in {'token_plan','pay_as_you_go'}:
        host='token-plan-cn.xiaomimimo.com' if config.api_kind=='token_plan' else 'api.xiaomimimo.com'
        endpoint='https://'+host+'/v1/chat/completions'
    else:
        raise HTTPException(503,'业务助手服务配置有误，请联系管理员检查')
    return endpoint,body


@dataclass(frozen=True)
class ProviderReply:
    message: dict = field(repr=False)
    usage: dict


_TOKEN_KEYS = ('prompt_tokens', 'completion_tokens', 'total_tokens',
               'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens', 'reasoning_tokens')


@dataclass
class _Usage:
    background: bool
    started: float = field(default_factory=monotonic)
    http_requests: int = 0
    retries: int = 0
    tool_count: int = 0
    reports: list = field(default_factory=list, repr=False)

    def request_started(self):
        # Count each HTTP attempt, including retries, after the immediate guard
        # and before POST; a model round or successful reply is not this count.
        self.http_requests += 1
        self.retries = max(0, self.http_requests - 1)
        self.reports.append({})

    def observe(self, value):
        if type(value) is not dict or not self.reports:
            return
        report = self.reports[-1]
        for key in _TOKEN_KEYS:
            if key in value:
                count = value[key]
                report[key] = count if type(count) is int and count >= 0 else None
        details = value.get('completion_tokens_details')
        if type(details) is dict and 'reasoning_tokens' in details:
            count = details['reasoning_tokens']
            report['reasoning_tokens'] = count if type(count) is int and count >= 0 else None

    def snapshot(self):
        # A failed/unreported attempt is not free. A total is known only when
        # every actual request supplied that counter; no estimates or coercion.
        tokens = {key: sum(report[key] for report in self.reports)
                  if self.reports and all(report.get(key) is not None for report in self.reports)
                  else None for key in _TOKEN_KEYS}
        known = [value is not None for value in tokens.values()]
        status = ('known' if all(tokens[key] is not None for key in _TOKEN_KEYS[:3])
                  else 'partial' if any(known) else 'unknown')
        return {'http_requests': self.http_requests, 'retries': self.retries,
                'elapsed_ms': max(0, int((monotonic() - self.started) * 1000)),
                'tool_count': self.tool_count, 'background': self.background,
                'token_usage_status': status, 'tokens': tokens}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('tool arguments')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('tool arguments')


def _finite(value):
    if value is None or type(value) in (bool, int):
        return
    if type(value) is str:
        value.encode('utf-8')
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _finite(item)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError('tool arguments')
            _finite(key)
            _finite(item)
        return
    raise ValueError('tool arguments')


def _complete_tools(calls, service, *, allow_index=False, argument_error_names=None):
    """Validate the whole response without rewriting its native argument JSON."""
    if type(calls) is not list or len(calls) > service.HARD_TOOLS:
        raise ValueError('tools')
    seen = set()
    normalized = []
    for position, call in enumerate(calls):
        # Non-stream replies may carry the provider's array index. Validate it
        # before removing this transport metadata from our internal tool calls.
        if allow_index and type(call) is dict and 'index' in call:
            index = call['index']
            if type(index) is not int or not 0 <= index < service.HARD_TOOLS or index != position:
                raise ValueError('tool index')
            call = {key: value for key, value in call.items() if key != 'index'}
        if type(call) is not dict or set(call) != {'id', 'type', 'function'}:
            raise ValueError('incomplete tool')
        ident = call['id']
        if type(ident) is not str or not ident.strip():
            raise ValueError('tool id')
        ident.encode('utf-8')
        if ident in seen:
            raise ValueError('duplicate tool id')
        seen.add(ident)
        if call['type'] != 'function':
            raise ValueError('tool type')
        function = call['function']
        if type(function) is not dict or set(function) != {'name', 'arguments'}:
            raise ValueError('tool function')
        name, arguments = function['name'], function['arguments']
        if type(name) is not str or not name.strip() or len(name) > 100:
            raise ValueError('tool name')
        name.encode('utf-8')
        if type(arguments) is not str or not arguments.strip() or len(arguments) > service.MODEL_ARGUMENT_CHARS:
            raise ValueError('tool arguments')
        arguments.encode('utf-8')
        normalized.append(call)
    # Check every envelope first; a syntax error must not hide another invalid tool.
    invalid_arguments = False
    for call in normalized:
        try:
            decoded = json.loads(call['function']['arguments'], object_pairs_hook=_pairs,
                                 parse_constant=_invalid_constant)
        except json.JSONDecodeError:
            if argument_error_names is None:
                raise
            invalid_arguments = True
            continue
        if type(decoded) is not dict:
            raise ValueError('tool arguments')
        _finite(decoded)
    if invalid_arguments:
        if any(call['function']['name'] not in argument_error_names for call in normalized):
            raise ValueError('tool name')
        # No reply, argument text or reasoning is attached to this fixed exception.
        raise ModelToolArgumentsInvalid()
    return normalized if allow_index else calls


def _complete_reply(reply, finish, service, *, require_finish, allow_tool_index=False,
                    argument_error_names=None):
    if finish == 'length':
        raise service.ModelOutputTruncated()
    if finish not in ({'stop', 'tool_calls'} if require_finish else {None, 'stop', 'tool_calls'}):
        raise ValueError('incomplete finish')
    if type(reply) is not dict:
        raise ValueError('incomplete reply')
    content = reply.get('content')
    if content is not None:
        if type(content) is not str or len(content) > service.MODEL_TEXT_CHARS:
            raise ValueError('content limit')
        content.encode('utf-8')
    reasoning = reply.get('reasoning_content')
    if reasoning is not None:
        if type(reasoning) is not str or len(reasoning) > service.MODEL_REASONING_CHARS:
            raise ValueError('reasoning limit')
        reasoning.encode('utf-8')
    calls = reply.get('tool_calls')
    calls = [] if calls is None else _complete_tools(calls, service, allow_index=allow_tool_index,
                                                    argument_error_names=argument_error_names)
    if finish is not None and (finish == 'tool_calls') != bool(calls):
        raise ValueError('tool finish mismatch')
    return calls


async def _before_request(callback):
    """Internal authorization hook; never route its failures through retries."""
    if callback is None:
        return
    from inspect import isawaitable
    result = callback()
    if isawaitable(result):
        result = await result
    if result is not None:
        raise TypeError('The pre-request guard must return None')


async def _nonstream(config, messages, thinking, usage, before_request=None, *, allow_tools=True):
    from . import business_assistant_service as service
    attempt = 0
    while True:
        attempt += 1
        # Includes the existing transport/5xx retry. This is outside the HTTP
        # retry handler: a revoked or expired worker must not send another POST.
        await _before_request(before_request)
        try:
            # Keep the old dynamic fixture hook. The service wrapper delegates
            # only construction to provider_request, so this is not recursion.
            endpoint, body = service.provider_request(config, messages, thinking=thinking)
            if not allow_tools:
                body['tool_choice'] = 'none'
            definitions = body.get('tools')
            published_names = frozenset(tool['function']['name'] for tool in definitions
                if type(tool) is dict and tool.get('type') == 'function'
                and type(tool.get('function')) is dict
                and type(tool['function'].get('name')) is str) if type(definitions) is list else frozenset()
            async with httpx.AsyncClient(timeout=config.timeout_seconds, follow_redirects=False, trust_env=False) as client:
                usage.request_started()
                response = await client.post(endpoint, headers={'Authorization': 'Bearer ' + config.api_key}, json=body)
            if response.status_code in {401, 403, 402, 429}:
                raise HTTPException(503, provider_error(response.status_code))
            if response.status_code >= 500 and attempt == 1:
                await asyncio.sleep(1.0)
                continue
            if response.status_code >= 400:
                raise HTTPException(503, provider_error(response.status_code))
            if len(response.content) > service.MODEL_RESPONSE_BYTES:
                raise ValueError('response too large')
            data = response.json()
            if type(data) is not dict or data.get('error'):
                raise ValueError('provider error')
            usage.observe(data.get('usage'))
            choices = data['choices']
            if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
                raise ValueError('choices')
            choice = choices[0]
            if type(choice.get('index', 0)) is not int or choice.get('index', 0) != 0:
                raise ValueError('choices')
            reply = choice['message']
            safe_usage = usage.snapshot()
            tokens = safe_usage['tokens']
            # Only an explicit complete, single billed non-stream reply can re-express syntax.
            argument_error_names = published_names if (response.status_code == 200 and allow_tools
                and choice.get('finish_reason') == 'tool_calls' and type(reply) is dict
                and reply.get('role') == 'assistant' and safe_usage['http_requests'] == 1
                and safe_usage['retries'] == 0 and safe_usage['token_usage_status'] == 'known'
                and tokens['total_tokens'] == tokens['prompt_tokens'] + tokens['completion_tokens']) else None
            try:
                calls = _complete_reply(reply, choice.get('finish_reason'), service,
                    require_finish=False, allow_tool_index=True, argument_error_names=argument_error_names)
            except ModelToolArgumentsInvalid:
                usage.tool_count = len(reply['tool_calls'])
                raise
            if reply.get('tool_calls') is not None:
                reply = dict(reply, tool_calls=calls)
            usage.tool_count = len(calls)
            return reply
        except httpx.TimeoutException:
            if attempt == 1:
                await asyncio.sleep(1.0)
                continue
            raise HTTPException(503, '业务助手响应超时，请稍后重试；尚未确认的操作不会执行') from None
        except httpx.TransportError as exc:
            if attempt == 1:
                await asyncio.sleep(1.0)
                continue
            raise HTTPException(503, '业务助手连接异常，请稍后再试（%s）' % type(exc).__name__) from None
        except httpx.HTTPError:
            raise HTTPException(503, '业务助手连接异常，请稍后再试') from None
        except (ValueError, KeyError, IndexError, TypeError, OverflowError, RecursionError):
            raise ModelProtocolError('回复未完整通过校验，请核对已有卡片。') from None


async def _stream(config, messages, thinking, emit, usage, before_request=None, *, allow_tools=True):
    from . import business_assistant_service as service
    endpoint,body=service.provider_request(config,messages,thinking=thinking,stream=True)
    if not allow_tools:
        body['tool_choice'] = 'none'
    tools={};content='';reasoning='';finish=None;done=False;size=0;phase=None
    safe=SafeDeltas(service.safe_text)
    async def status(next_phase):
        nonlocal phase
        if phase!=next_phase:
            phase=next_phase
            await emit('status',{'phase':phase})
    async def packet(raw):
        nonlocal content,reasoning,finish,done
        if done:raise ValueError('data after done')
        if raw=='[DONE]':done=True;return
        data=json.loads(raw)
        if type(data) is not dict or data.get('error'):raise ValueError('provider error')
        # A usage-only empty-choices tail is metadata, not a finish or DONE.
        usage.observe(data.get('usage'))
        choices=data.get('choices',[])
        if type(choices) is not list:raise ValueError('choices')
        if not choices:return
        if len(choices)!=1 or type(choices[0]) is not dict:raise ValueError('choices')
        choice=choices[0]
        if type(choice.get('index',0)) is not int or choice.get('index',0)!=0:raise ValueError('choices')
        delta=choice.get('delta')
        delta={} if delta is None else delta
        if type(delta) is not dict:raise ValueError('delta')
        if finish is not None and delta:raise ValueError('delta after finish')
        thought=delta.get('reasoning_content')
        if thought is not None:
            if type(thought) is not str:raise ValueError('reasoning')
            reasoning+=thought
            if len(reasoning)>service.MODEL_REASONING_CHARS:raise ValueError('reasoning limit')
            if thought:await status('thinking')
        text=delta.get('content')
        if text is not None:
            if type(text) is not str:raise ValueError('content')
            content+=text
            if len(content)>service.MODEL_TEXT_CHARS:raise ValueError('content limit')
            if text:
                await status('responding')
                clean=safe.feed(text)
                if clean:await emit('delta',{'text':clean})
        calls=delta.get('tool_calls')
        calls=[] if calls is None else calls
        if type(calls) is not list:raise ValueError('tools')
        for fragment in calls:
            if type(fragment) is not dict:raise ValueError('tool fragment')
            index=fragment.get('index')
            if type(index) is not int or not 0<=index<service.HARD_TOOLS:raise ValueError('tool index')
            target=tools.setdefault(index,{'id':'','type':'function','function':{'name':'','arguments':''}})
            if fragment.get('type') not in {None,'function'}:raise ValueError('tool type')
            ident=fragment.get('id')
            if ident is not None:
                if type(ident) is not str:raise ValueError('tool id')
                target['id']+=ident
            function=fragment.get('function')
            function={} if function is None else function
            if type(function) is not dict:raise ValueError('tool function')
            for key in ('name','arguments'):
                value=function.get(key)
                if value is not None:
                    if type(value) is not str:raise ValueError('tool fragment')
                    target['function'][key]+=value
                    if len(target['function'][key])>(service.MODEL_ARGUMENT_CHARS if key=='arguments' else 100):raise ValueError('tool size')
        if calls:await status('tool')
        reason=choice.get('finish_reason')
        if reason is not None:
            if reason=='length':raise service.ModelOutputTruncated()
            if reason not in {'stop','tool_calls'}:raise ValueError('incomplete finish')
            if finish is not None and reason!=finish:raise ValueError('incomplete finish')
            finish=reason
    await _before_request(before_request)
    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds,follow_redirects=False,trust_env=False) as client:
            usage.request_started()
            async with client.stream('POST',endpoint,headers={'Authorization':'Bearer '+config.api_key},json=body) as response:
                if response.status_code!=200:raise HTTPException(503,provider_error(response.status_code))
                if 'text/event-stream' not in response.headers.get('content-type',''):raise ValueError('not SSE')
                data_lines=[]
                async for line in response.aiter_lines():
                    size+=len(line.encode('utf-8'))
                    if size>service.MODEL_RESPONSE_BYTES:raise ValueError('stream limit')
                    if line=='':
                        if data_lines:await packet('\n'.join(data_lines));data_lines=[]
                    elif line.startswith('data:'):data_lines.append(line[5:].lstrip(' '))
                if data_lines:await packet('\n'.join(data_lines))
        if not done or finish is None:raise ValueError('incomplete stream')
        reply={'role':'assistant','content':content,'reasoning_content':reasoning,
               'tool_calls':[tools[index] for index in sorted(tools)],'finish_reason':finish}
        calls=_complete_reply(reply,finish,service,require_finish=True)
        usage.tool_count=len(calls)
        clean=safe.feed('',final=True)
        if clean:await emit('delta',{'text':clean})
        return reply
    except httpx.TimeoutException:raise HTTPException(503,'业务助手响应超时；已确认前的操作不会执行') from None
    except httpx.HTTPError:raise HTTPException(503,'上游连接中断；本段未完整校验的工具未执行，请核对已有卡片') from None
    except (ValueError,KeyError,TypeError,IndexError,OverflowError,RecursionError):
        raise ModelProtocolError('回复未完整通过校验，请核对已有卡片。') from None


async def call_model(config, messages, thinking=False, *, stream=False, emit=None, background=False,
                     before_request=None, allow_tools=True):
    """One complete reply and sanitized counters, with no durable side effects."""
    if (type(stream) is not bool or type(background) is not bool or type(thinking) is not bool
            or type(allow_tools) is not bool):
        raise TypeError('Provider flags must be server-owned booleans')
    if stream and not callable(emit):
        raise TypeError('Streaming requires an async event callback')
    if before_request is not None and not callable(before_request):
        raise TypeError('The pre-request guard must be a server callback')
    usage = _Usage(background=background)
    try:
        reply = (await _stream(config, messages, thinking, emit, usage, before_request, allow_tools=allow_tools) if stream
                 else await _nonstream(config, messages, thinking, usage, before_request, allow_tools=allow_tools))
        # Both transports have already validated the entire original reply.
        if not allow_tools and reply.get('tool_calls'):
            raise ModelProtocolError('收尾回复仍含工具调用，请核对已有卡片。')
    except BaseException as exc:
        # Only safe integers/status reach the worker. Never attach the response,
        # messages, credential, raw exception body or reasoning to telemetry.
        exc.runtime_usage = usage.snapshot()
        raise
    return ProviderReply(message=reply, usage=usage.snapshot())


async def model_reply(config, messages, thinking=False):
    return (await call_model(config, messages, thinking=thinking)).message


async def model_reply_stream(config, messages, thinking, emit):
    return (await call_model(config, messages, thinking=thinking, stream=True, emit=emit)).message
