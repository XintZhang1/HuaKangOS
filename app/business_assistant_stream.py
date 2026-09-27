"""Bounded upstream SSE transport and downstream events; never emit raw reasoning."""
import asyncio
import json
import re
import httpx
from fastapi import HTTPException
from starlette.responses import StreamingResponse


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


async def model_reply_stream(config,messages,thinking,emit):
    from . import business_assistant_service as service
    endpoint,body=service.provider_request(config,messages,thinking=thinking,stream=True)
    tools={};content='';reasoning='';finish=None;done=False;size=0;phase=None
    safe=SafeDeltas(service.safe_text)
    async def status(next_phase):
        nonlocal phase
        if next_phase!=phase:
            phase=next_phase;await emit('status',{'phase':phase})
    async def packet(raw):
        nonlocal content,reasoning,finish,done,size
        if raw=='[DONE]':done=True;return
        if done:raise ValueError('data after done')
        data=json.loads(raw)
        if not isinstance(data,dict) or data.get('error'):raise ValueError('provider error')
        choices=data.get('choices',[])
        if not choices:return
        if not isinstance(choices,list) or len(choices)!=1 or choices[0].get('index',0)!=0:raise ValueError('choices')
        choice=choices[0];delta=choice.get('delta') or {}
        if finish is not None and delta:raise ValueError('delta after finish')
        if not isinstance(delta,dict):raise ValueError('delta')
        thought=delta.get('reasoning_content')
        if thought:
            if not isinstance(thought,str):raise ValueError('reasoning')
            reasoning+=thought
            if len(reasoning)>service.MODEL_REASONING_CHARS:raise ValueError('reasoning limit')
            await status('thinking')
        text=delta.get('content')
        if text:
            if not isinstance(text,str):raise ValueError('content')
            content+=text
            if len(content)>service.MODEL_TEXT_CHARS:raise ValueError('content limit')
            await status('responding')
            clean=safe.feed(text)
            if clean:await emit('delta',{'text':clean})
        calls=delta.get('tool_calls') or []
        if not isinstance(calls,list):raise ValueError('tools')
        for fragment in calls:
            index=fragment.get('index')
            if type(index) is not int or not 0<=index<service.HARD_TOOLS:raise ValueError('tool index')
            target=tools.setdefault(index,{'id':'','type':'function','function':{'name':'','arguments':''}})
            if fragment.get('type') not in {None,'function'}:raise ValueError('tool type')
            if fragment.get('id'):
                if not isinstance(fragment['id'],str):raise ValueError('tool id')
                target['id']+=fragment['id']
            function=fragment.get('function') or {}
            if not isinstance(function,dict):raise ValueError('tool function')
            for key in ('name','arguments'):
                value=function.get(key)
                if value:
                    if not isinstance(value,str):raise ValueError('tool fragment')
                    target['function'][key]+=value
                    if len(target['function'][key])>(service.MODEL_ARGUMENT_CHARS if key=='arguments' else 100):raise ValueError('tool size')
        if calls:await status('tool')
        reason=choice.get('finish_reason')
        if reason is not None:
            if reason=='length':raise service.ModelOutputTruncated()
            if reason not in {'stop','tool_calls'}:raise ValueError('incomplete finish')
            finish=reason
    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds,follow_redirects=False,trust_env=False) as client:
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
        if (finish=='tool_calls')!=bool(tools):raise ValueError('tool finish mismatch')
        calls=[tools[index] for index in sorted(tools)]
        if len({call['id'] for call in calls})!=len(calls):raise ValueError('duplicate tool id')
        for call in calls:
            if not call['id'] or not call['function']['name'] or not isinstance(json.loads(call['function']['arguments']),dict):raise ValueError('incomplete tool')
        clean=safe.feed('',final=True)
        if clean:await emit('delta',{'text':clean})
        return {'role':'assistant','content':content,'reasoning_content':reasoning,'tool_calls':calls,'finish_reason':finish}
    except httpx.TimeoutException:raise HTTPException(503,'业务助手响应超时；已确认前的操作不会执行') from None
    except httpx.HTTPError:raise HTTPException(503,'上游连接中断；本段未完整校验的工具未执行，请核对已有卡片') from None
    except (ValueError,KeyError,TypeError) as exc:
        known={'data after done','provider error','choices','delta after finish','delta','reasoning','reasoning limit',
               'content','content limit','tools','tool index','tool id','tool type','tool function','tool fragment','tool size',
               'incomplete finish','not SSE','stream limit','incomplete stream','tool finish mismatch',
               'duplicate tool id','tool arguments','tool name','incomplete tool'}
        # Only fixed parser codes, never an upstream body, credential or raw reasoning.
        code=str(exc) if type(exc) is ValueError and str(exc) in known else type(exc).__name__
        raise HTTPException(503,'模型流式协议校验未通过（'+code+'）；本段未执行，请核对已有卡片') from None


async def streaming_response(db,request,user,session_id,request_id,content,thinking):
    from . import business_assistant_service as service
    queue=asyncio.Queue(maxsize=128)
    async def emit(event,data):await queue.put((event,data,None))
    async def run():
        try:
            result=await service.conversation(db,request,user,session_id,request_id,content,thinking=thinking,emit=emit)
            await emit('done',{'session':result})
        except HTTPException as exc:
            await queue.put(('error',{'message':service.safe_text(exc.detail,1000)},exc.status_code))
        except asyncio.CancelledError:raise
        except Exception:
            await queue.put(('error',{'message':'回复中断，请刷新对话核对结果'},500))
        finally:
            if not asyncio.current_task().cancelling():await queue.put(None)
    task=asyncio.create_task(run())
    async def stop():
        if not task.done():task.cancel()
        try:await asyncio.shield(task)
        except (asyncio.CancelledError,Exception):pass
    try:first=await queue.get()
    except BaseException:
        await stop();raise
    if first and first[0]=='error' and first[2]:
        await stop();raise HTTPException(first[2],first[1]['message'])
    async def events():
        item=first
        try:
            while item is not None:
                event,data,_=item
                yield 'event: '+event+'\ndata: '+json.dumps(data,ensure_ascii=False)+'\n\n'
                item=await queue.get()
        finally:await stop()
    class ManagedStream(StreamingResponse):
        async def __call__(self,scope,receive,send):
            # ASGI 2.4 signals disconnect through send(OSError), which need not
            # close a suspended body iterator immediately. Own task cleanup here.
            try:await super().__call__(scope,receive,send)
            finally:await stop()
    return ManagedStream(events(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
