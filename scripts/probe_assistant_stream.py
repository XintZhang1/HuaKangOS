"""Opt-in real DeepSeek trial against fresh synthetic databases, never the preview.

Private configuration and evidence must be outside the repository. Two trials
exercise thinking off/on through actual HTTP streaming and native confirmations.
The probe stores public reply text and tool names only, never reasoning or keys.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.browser_huakangos import browser_environment


def serve(port,trace):
    assert os.environ.get('APP_ENV')=='test'
    assert 'huakangos-stream-probe-' in os.environ.get('DATABASE_URL','')
    from app import business_assistant_stream as stream
    from app import business_assistant_service as service
    from app.main import app
    import uvicorn
    original=stream.model_reply_stream
    calls=0
    async def recorded(config,messages,thinking,emit):
        nonlocal calls
        calls+=1
        if calls>20:raise RuntimeError('Synthetic probe provider budget exceeded')
        started=time.monotonic()
        reply=await original(config,messages,thinking,emit)
        entry={'thinking':thinking,'seconds':round(time.monotonic()-started,3),
               'tools':[item.get('function',{}).get('name') for item in reply.get('tool_calls',[])],
               'reasoning_present':bool(reply.get('reasoning_content'))}
        with Path(trace).open('a',encoding='utf-8') as target:target.write(json.dumps(entry)+'\n')
        return reply
    stream.model_reply_stream=recorded
    uvicorn.run(app,host='127.0.0.1',port=port,log_level='warning',access_log=False)


def run_trial(config,output,thinking):
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    with tempfile.TemporaryDirectory(prefix='huakangos-stream-probe-') as temp:
        work=Path(temp);password=secrets.token_urlsafe(24)
        private=work/'private.json'
        private.write_text(json.dumps({**config,'synthetic':True}),encoding='utf-8')
        env=browser_environment(work,password)
        env.update(BUSINESS_ASSISTANT_CONFIG=str(private),PYTHONDONTWRITEBYTECODE='1')
        initialized=subprocess.run([sys.executable,'-m','app.cli','init'],cwd=ROOT,env=env,capture_output=True,creationflags=flags)
        if initialized.returncode:raise RuntimeError('Synthetic database initialization failed')
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        trace=output/('thinking-on-model.jsonl' if thinking else 'thinking-off-model.jsonl')
        assert not trace.exists()
        with (work/'server.log').open('w',encoding='utf-8') as log:
            server=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve',str(port),str(trace)],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=flags)
            try:
                with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=210,headers={'X-App-Request':'1','X-Store-ID':'1'}) as client:
                    for _ in range(150):
                        try:
                            if client.get('/api/health',timeout=1).status_code==200:break
                        except httpx.HTTPError:pass
                        if server.poll() is not None:raise RuntimeError('Synthetic server failed')
                        time.sleep(.1)
                    else:raise RuntimeError('Synthetic server not ready')
                    def call(method,path,body=None,status=200):
                        result=client.request(method,path,json=body)
                        if result.status_code!=status:raise AssertionError((path,result.status_code,result.text[:500]))
                        return result.json()
                    admin=call('POST','/api/auth/login',{'username':'admin','password':password})
                    client.headers['X-CSRF-Token']=client.cookies.get('dealer_csrf')
                    catalog=call('GET','/api/flow/catalog');today=catalog['today']
                    from datetime import date,timedelta
                    tomorrow=(date.fromisoformat(today)+timedelta(days=1)).isoformat()
                    lead=call('POST','/api/flow/cases',{'request_id':uuid4().hex,'kind':'lead','values':{'customer_name':'合成接待甲','source':'展厅到店'}},201)
                    def action(key,values):
                        current=call('GET',f'/api/flow/cases/{lead["id"]}')
                        return call('POST',f'/api/flow/cases/{lead["id"]}/actions/{key}',{'request_id':uuid4().hex,'version':current['version'],'values':values})
                    action('assign',{'assignee_id':admin['id']})
                    action('intent',{'need':'合成购车意向','due_date':today})
                    before=call('GET',f'/api/flow/cases/{lead["id"]}')
                    assert before['state']=='intent' and not before['customer']['phone']
                    sid=call('POST','/api/business-assistant/sessions',{},201)['id']
                    turns=[];confirmed=set()
                    prompts=['我有一个接待的工单，你帮我填一下手机号13900008888，然后安排明天下午的接待回访',
                             '本次沟通结果是：客户希望明天下午继续沟通。记录这次意向跟进，下次处理日期设为明天。']
                    for prompt in prompts:
                        events=[];started=time.monotonic();event='';data=[];session=None
                        with client.stream('POST',f'/api/business-assistant/sessions/{sid}/messages/stream',json={'request_id':uuid4().hex,'content':prompt,'thinking':thinking}) as response:
                            assert response.status_code==200,response.status_code
                            for line in response.iter_lines():
                                if line.startswith('event:'):event=line[6:].strip()
                                elif line.startswith('data:'):data.append(line[5:].lstrip())
                                elif not line and data:
                                    payload=json.loads('\n'.join(data));elapsed=round(time.monotonic()-started,3)
                                    assert 'reasoning_content' not in payload
                                    if event=='done':session=payload['session'];events.append({'event':event,'seconds':elapsed})
                                    else:events.append({'event':event,'seconds':elapsed,'data':payload})
                                    data=[]
                        assert session is not None,'SSE did not deliver its final session'
                        replies=[m['content'] for m in session['messages'] if m['role']=='assistant']
                        turns.append({'prompt':prompt,'reply':replies[-1] if replies else '', 'events':events,
                                      'proposals':[{'id':p['id'],'operation_id':p['operation_id'],'status':p['status'],'details':p['details']} for p in session['proposals']]})
                        # Synthetic employee reviews only these two expected native forms.
                        for proposal in session['proposals']:
                            if proposal['id'] in confirmed or proposal['status']!='pending':continue
                            details=proposal['details'];body=details.get('body',{});path=details.get('path_args',{})
                            if proposal['operation_id']=='PUT /api/flow/master/{kind}/{record_id}':
                                assert path=={'kind':'customers','record_id':before['customer']['id']}
                                assert body['values']['phone']=='13900008888' and body['values']['name']=='合成接待甲'
                            else:
                                assert proposal['operation_id']=='POST /api/flow/cases/{case_id}/actions/{action}'
                                assert path=={'case_id':lead['id'],'action':'follow'}
                                assert body['values']['due_date']==tomorrow
                                assert '客户希望明天下午继续沟通' in body['values']['result']
                            posted=call('POST',f'/api/business-assistant/sessions/{sid}/proposals/{proposal["id"]}/confirm',{'digest':proposal['digest']})
                            assert next(p for p in posted['proposals'] if p['id']==proposal['id'])['status']=='succeeded'
                            confirmed.add(proposal['id'])
                    after=call('GET',f'/api/flow/cases/{lead["id"]}')
                    model=[json.loads(line) for line in trace.read_text('utf-8').splitlines()]
                    passed=(after['customer']['phone']=='13900008888' and after['due_date']==tomorrow and after['state']=='intent' and len(confirmed)==2 and model[0]['tools']==['find_cases'])
                    result={'passed':passed,'thinking':thinking,'synthetic_only':True,'turns':turns,'model_rounds':len(model),'confirmed_forms':len(confirmed),'phone_saved':after['customer']['phone']=='13900008888','follow_date_saved':after['due_date']==tomorrow,'first_tool':model[0]['tools'],'model':config['model']}
                    (output/('thinking-on.json' if thinking else 'thinking-off.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                    print(json.dumps({k:v for k,v in result.items() if k!='turns'},ensure_ascii=False),flush=True)
                    return passed
            finally:
                if server.poll() is None:
                    if os.name=='nt':subprocess.run(['taskkill','/PID',str(server.pid),'/T','/F'],capture_output=True,creationflags=flags)
                    else:server.terminate()
                    server.wait(timeout=15)
        if os.name=='nt':
            for _ in range(50):
                try:os.replace(work/'server.log',work/'server.log');break
                except PermissionError:time.sleep(.1)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mode',choices=['off','on','both'],default='both')
    args=parser.parse_args();config_path=args.config.resolve();output=args.output.resolve()
    if config_path.is_relative_to(ROOT) or output.is_relative_to(ROOT):parser.error('Config and evidence must be outside source')
    config=json.loads(config_path.read_text('utf-8-sig'))
    if config.get('provider','deepseek')!='deepseek' or not config.get('enabled') or not config.get('api_key'):parser.error('Enabled private DeepSeek config required')
    output.mkdir(parents=True,exist_ok=True)
    from scripts.verify_candidate import source_manifest
    before=source_manifest()
    (output/'source-before.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
    modes=[False,True] if args.mode=='both' else [args.mode=='on']
    results=[run_trial(config,output,mode) for mode in modes]
    after=source_manifest()
    (output/'source-after.json').write_text(json.dumps(after,indent=2),encoding='utf-8')
    summary={'passed':all(results) and before==after,'source_unchanged':before==after,
             'source_digest':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
             'modes':modes,'results':results,'synthetic_only':True}
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    raise SystemExit(0 if summary['passed'] else 1)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--serve':serve(int(sys.argv[2]),sys.argv[3])
    else:main()
