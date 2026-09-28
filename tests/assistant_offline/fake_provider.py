"""Offline model protocol fixture; real service, tool gateway and original APIs run unchanged."""
import json
import socket
from contextlib import contextmanager
from unittest.mock import patch
import httpx

RealAsyncClient = httpx.AsyncClient


def tool(name, arguments, ident='call_offline'):
    return {'role':'assistant', 'content':None, 'tool_calls':[
        {'id':ident,'type':'function','function':{'name':name,'arguments':json.dumps(arguments,ensure_ascii=False)}}]}


def reply(content):
    return {'role':'assistant','content':content}


def customer_steps(name='离线客户甲'):
    return [tool('inspect_business_form', {'form_ref':'crm:customers'}, 'call_inspect'),
            tool('prepare_business_form', {'form_ref':'crm:customers','values':{'name':name,'contact_allowed':False},
                    'summary':'新建客户档案：'+name}, 'call_prepare'),
            reply('客户档案已准备，请核对后确认。')]


class Provider:
    def __init__(self, steps=None, before_response=None, stream_chunks=None):
        self.steps=list(steps or [tool('find_business_objects',{'kind':'customer','query':'张'}),reply('已核对客户资料。')])
        self.requests=[]
        self.before_response=before_response
        self.stream_chunks=stream_chunks

    def handle(self, request):
        if request.url.scheme!='https' or request.url.host!='api.deepseek.com' or request.url.path!='/chat/completions':
            raise AssertionError('Only the synthetic provider endpoint is permitted')
        body=json.loads(request.content)
        self.requests.append(body)
        if self.before_response: self.before_response(len(self.requests),body)
        index=len(self.requests)-1
        if index>=len(self.steps): raise AssertionError('Unexpected model request: fixture exhausted')
        step=self.steps[index]
        if isinstance(step,httpx.Response): return step
        if isinstance(step,Exception): raise step
        if callable(step): step=step(body)
        finish='tool_calls' if step.get('tool_calls') else 'stop'
        envelope={'choices':[{'index':0,'message':step,'finish_reason':finish}],
            'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}}
        if body.get('stream'):
            if self.stream_chunks is not None:
                return httpx.Response(200,content=''.join(self.stream_chunks),headers={'content-type':'text/event-stream'})
            packets=[{'choices':[{'index':0,'delta':{'role':'assistant','content':step.get('content') or ''},'finish_reason':None}]}]
            for i,call in enumerate(step.get('tool_calls',[])):
                packets.append({'choices':[{'index':0,'delta':{'tool_calls':[{'index':i,**call}]},'finish_reason':None}]})
            packets.append({'choices':[{'index':0,'delta':{},'finish_reason':finish}],'usage':envelope['usage']})
            return httpx.Response(200,content=''.join('data: '+json.dumps(p,ensure_ascii=False)+'\n\n' for p in packets)+'data: [DONE]\n\n',
                                  headers={'content-type':'text/event-stream'})
        return httpx.Response(200,json=envelope)

    @contextmanager
    def installed(self):
        provider=self
        class OfflineClient(RealAsyncClient):
            def __init__(self,*args,**kwargs):
                # Preserve the original gateway's explicit same-process ASGI transport.
                if kwargs.get('transport') is None: kwargs['transport']=httpx.MockTransport(provider.handle)
                super().__init__(*args,**kwargs)
        with patch.object(httpx,'AsyncClient',OfflineClient):
            yield self


def deny_external_sockets():
    """Defense in depth. SQLite/ASGI and loopback browser traffic remain local."""
    real_connect=socket.socket.connect
    def connect(sock,address):
        if sock.family in (socket.AF_INET,socket.AF_INET6) and address[0] not in ('127.0.0.1','::1','localhost'):
            raise AssertionError('External sockets are disabled in offline validation')
        return real_connect(sock,address)
    return patch.object(socket.socket,'connect',connect)
