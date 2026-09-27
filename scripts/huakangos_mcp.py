#!/usr/bin/env python3
"""Tools-only MCP stdio adapter, explicit 2025-11-25 compatibility profile.

No application/database imports. Never accepts an arbitrary URL, principal or
confirmation operation from tool arguments. Every call reuses the native user's
cookie+CSRF and is re-authorized by HuaKangOS. stdout is JSON-RPC only.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlsplit
from uuid import uuid4
import httpx

PROTOCOL_VERSION='2025-11-25'
SERVER_VERSION='R4-B1'
MAX_LINE_BYTES=2*1024*1024
MAX_HTTP_BYTES=4*1024*1024
ROOT=Path(__file__).resolve().parents[1]

class AdapterError(Exception):
    def __init__(self,message,status=503):super().__init__(message);self.status=status


def validate_url(value):
    if not isinstance(value,str) or len(value)>500 or any(ord(c)<33 for c in value):
        raise ValueError('invalid server URL')
    u=urlsplit(value)
    if (u.scheme not in {'http','https'} or not u.hostname or u.username or u.password
        or u.query or u.fragment or u.path not in {'','/'}):raise ValueError('server URL must be an origin')
    # Prevent accidentally putting authenticated traffic on an unencrypted LAN/public host.
    if u.scheme=='http' and u.hostname not in {'localhost','127.0.0.1','::1'}:
        raise ValueError('non-localhost requires HTTPS')
    if u.port is not None and not 1<=u.port<=65535:raise ValueError('invalid port')
    return value.rstrip('/')


def load_private_config(path=None):
    raw=path or os.environ.get('HUAKANGOS_MCP_CONFIG','')
    if not raw or not Path(raw).is_absolute():raise AdapterError('请先本地配置MCP登录会话，配置路径必须为绝对路径。')
    try:
        p=Path(raw).resolve(strict=True)
        if p.is_relative_to(ROOT) or not p.is_file() or p.stat().st_size>16384:
            raise ValueError('private file')
        if os.name!='nt' and stat.S_IMODE(p.stat().st_mode)&0o077:
            raise ValueError('private file permission')
        data=json.loads(p.read_text(encoding='utf-8-sig'))
        required={'base_url','session_cookie','csrf_token','store_id','assistant_session_id'}
        if not isinstance(data,dict) or set(data)!=required:raise ValueError('config keys')
        data['base_url']=validate_url(data['base_url'])
        if type(data['store_id']) is not int or data['store_id']<1:raise ValueError('store')
        if not re.fullmatch(r'[A-Za-z0-9_-]{20,200}',data['session_cookie']):raise ValueError('cookie')
        if not re.fullmatch(r'[A-Za-z0-9_-]{20,200}',data['csrf_token']):raise ValueError('csrf')
        if not re.fullmatch(r'[a-f0-9-]{36}',data['assistant_session_id']):raise ValueError('session')
        return data
    except (OSError,ValueError,TypeError,KeyError):
        raise AdapterError('MCP配置不可用：请重新登录配置；配置须位于项目外，且只允许本人读取。') from None


class NativeBackend:
    def __init__(self,config=None):
        self.config=config or load_private_config()
        self.client=httpx.Client(base_url=self.config['base_url'],timeout=httpx.Timeout(130,connect=10),
            follow_redirects=False,trust_env=False,
            cookies={'dealer_session':self.config['session_cookie'],'dealer_csrf':self.config['csrf_token']},
            headers={'X-CSRF-Token':self.config['csrf_token'],'X-Store-ID':str(self.config['store_id']),'X-App-Request':'1'})
    def close(self):self.client.close()
    def _request(self,method,path,body=None):
        try:
            with self.client.stream(method,path,json=body) as response:
                raw=bytearray()
                for block in response.iter_bytes():
                    raw.extend(block)
                    if len(raw)>MAX_HTTP_BYTES:raise AdapterError('业务返回过长，请缩小查询。',413)
                if response.is_redirect:raise AdapterError('拒绝重定向；请重新核对本地配置的系统地址。')
                if response.status_code in (401,403):raise AdapterError('登录已过期或当前岗位/门店无权限；请在原系统核对或重新登录。',response.status_code)
                try:data=json.loads(raw)
                except (ValueError,UnicodeDecodeError):raise AdapterError('原系统没有返回有效JSON；本次结果不明，请核对。') from None
                if response.status_code>=400:
                    # Only native sanitized detail, no raw HTTP headers, URLs or environment.
                    detail=data.get('detail','工具调用未完成，请在原系统核对。') if isinstance(data,dict) else '工具调用未完成。'
                    if not isinstance(detail,str):detail='参数校验未通过，请核对工具字段。'
                    for key in ('session_cookie','csrf_token'):
                        detail=detail.replace(self.config[key],'[已隐藏]')
                    raise AdapterError(detail[:1000],response.status_code)
                if not isinstance(data,dict):raise AdapterError('业务结果格式不正确，请核对。')
                return data
        except httpx.TimeoutException:
            raise AdapterError('网络等待中断，可能已有部分草稿；请先刷新对话，不要盲目重复请求。',504) from None
        except httpx.HTTPError:
            raise AdapterError('无法连接配置的系统；没有自动重试，请检查本地网络与服务。') from None
    def tools(self):
        data=self._request('GET','/api/business-assistant/tools')
        tools=[]
        readonly={'find_business_objects','discover_business_forms','inspect_business_form','get_work_status',
                  'find_cases','get_case','find_workflows','list_operations','inspect_operation','read_data'}
        for entry in data.get('tools',[]):
            f=entry['function']
            tools.append({'name':f['name'],'description':f['description'],'inputSchema':f['parameters'],
                'annotations':{'readOnlyHint':f['name'] in readonly,'openWorldHint':False}})
        return tools
    def call(self,name,arguments):
        sid=self.config['assistant_session_id']
        return self._request('POST',f'/api/business-assistant/sessions/{sid}/tools/call',
            {'request_id':'mcp-'+uuid4().hex,'name':name,'arguments':arguments})


class RPCServer:
    def __init__(self,backend_factory=NativeBackend):
        self.backend_factory=backend_factory;self.backend=None;self.phase='new'
    def close(self):
        if self.backend:self.backend.close()
    def native(self):
        if self.backend is None:self.backend=self.backend_factory()
        return self.backend
    @staticmethod
    def error(ident,code,message):return {'jsonrpc':'2.0','id':ident,'error':{'code':code,'message':message}}
    @staticmethod
    def result(ident,data):return {'jsonrpc':'2.0','id':ident,'result':data}
    def handle(self,message):
        if not isinstance(message,dict):return self.error(None,-32600,'Invalid Request; batching is not supported')
        ident=message.get('id');has_id='id' in message
        if (message.get('jsonrpc')!='2.0' or not isinstance(message.get('method'),str)
                or (has_id and (isinstance(ident,bool) or not isinstance(ident,(str,int))))
                or set(message)-{'jsonrpc','id','method','params'}):
            return self.error(None,-32600,'Invalid Request')
        method=message['method'];params=message.get('params',{})
        if not isinstance(params,dict):return self.error(ident,-32602,'Invalid params') if has_id else None
        if not has_id:
            if method=='notifications/initialized' and self.phase=='initializing':self.phase='ready'
            # Unknown notifications never receive a response. No tasks/subscriptions advertised.
            return None
        if method=='ping':return self.result(ident,{})
        if method=='initialize':
            client=params.get('clientInfo')
            if (self.phase!='new' or not isinstance(params.get('protocolVersion'),str)
                or not isinstance(params.get('capabilities'),dict) or not isinstance(client,dict)
                or not isinstance(client.get('name'),str) or not isinstance(client.get('version'),str)):
                return self.error(ident,-32602,'Invalid initialization or already initialized')
            self.phase='initializing'
            return self.result(ident,{'protocolVersion':PROTOCOL_VERSION,'capabilities':{'tools':{'listChanged':False}},
                'serverInfo':{'name':'huakangos-business-tools','version':SERVER_VERSION},
                'instructions':'当前员工和门店在本地配置中绑定。仅查询、准备草稿和保存计划，不提供确认工具。请在HuaKangOS原界面核对并确认。兼容协议2025-11-25，非2026新无状态协议。'})
        if self.phase!='ready':return self.error(ident,-32000,'Initialize and send notifications/initialized first')
        if method not in {'tools/list','tools/call'}:return self.error(ident,-32601,'Method not found')
        if '_meta' in params and not isinstance(params['_meta'],dict):
            return self.error(ident,-32602,'Invalid request metadata')
        if method=='tools/list' and (set(params)-{'cursor','_meta'} or params.get('cursor') is not None):
            return self.error(ident,-32602,'Invalid cursor; the small tools catalogue fits one page')
        if method=='tools/call' and (set(params)-{'name','arguments','_meta'} or not isinstance(params.get('name'),str)
                or not isinstance(params.get('arguments',{}),dict)):
            return self.error(ident,-32602,'Invalid tool call')
        try:
            tools=self.native().tools()
            if method=='tools/list':return self.result(ident,{'tools':tools})
            if params['name'] not in {t['name'] for t in tools}:return self.error(ident,-32602,'Unknown tool')
            value=self.native().call(params['name'],params.get('arguments',{}))
            # Only HTTP-style numeric status >=400 is an error; "pending" is a card state.
            status=value.get('status');failed=type(status) is int and status>=400
            return self.result(ident,{'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False,allow_nan=False)}],
                'structuredContent':value,'isError':failed})
        except AdapterError as exc:
            if method=='tools/list':return self.error(ident,-32001,str(exc))
            value={'status':exc.status,'error':str(exc),'business_executed':False,
                   'notice':'没有确认工具；异常不证明草稿完全没有生成，请到原对话核对。'}
            return self.result(ident,{'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}],
                'structuredContent':value,'isError':True})
        except Exception:
            # Never echo a Python traceback or an upstream response containing secrets to a model.
            return self.error(ident,-32603,'Internal adapter error; check the local configuration and native session')


def strict_json(raw):
    def pairs(items):
        obj={}
        for key,value in items:
            if key in obj:raise ValueError('duplicate JSON key')
            obj[key]=value
        return obj
    def constant(_):raise ValueError('non-finite JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)


def serve(inp=None,out=None,server=None):
    inp=inp or sys.stdin.buffer;out=out or sys.stdout.buffer;server=server or RPCServer()
    try:
        while True:
            raw=inp.readline(MAX_LINE_BYTES+1)
            if not raw:break
            if len(raw)>MAX_LINE_BYTES:
                if not raw.endswith(b'\n'):
                    while True:
                        tail=inp.readline(MAX_LINE_BYTES+1)
                        if not tail or tail.endswith(b'\n'):break
                response=server.error(None,-32700,'Message exceeds receive limit')
            else:
                try:response=server.handle(strict_json(raw))
                except (ValueError,UnicodeDecodeError,RecursionError):response=server.error(None,-32700,'Parse error')
            if response is not None:
                out.write((json.dumps(response,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8'))
                out.flush()
    finally:server.close()


if __name__=='__main__':serve()
