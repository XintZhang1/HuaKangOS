import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fixture_env
import asyncio, json, sqlite3, unittest
from contextlib import closing
from uuid import uuid4
from datetime import timedelta
from unittest.mock import patch
from sqlalchemy import select,func,text
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine,SessionLocal,utcnow
from app.models import User,Store,LoginSession,CashEntry
from app.flow_models import Customer,Case,StockMove
from app.business_assistant_models import AssistantMessage,AssistantProposal
from app.assistant_runtime_models import Run,RunItem,WorkItem
from app.assistant_worker import Worker
from app.assistant_runtime_registry import domain_registry,DomainRegistry,DomainAdapterSpec
from app import assistant_runtime_queue as queue
from app import business_assistant_gateway as gateway
from fake_provider import Provider,tool,reply,customer_steps,deny_external_sockets

BASE='/api/business-assistant'

class RuntimeIntegration(unittest.TestCase):
    def setUp(self):
        engine.dispose()
        # Sole destination is our explicitly named disposable synthetic database.
        destination=fixture_env.RUNTIME/'synthetic.sqlite'
        assert destination.parent==fixture_env.RUNTIME and not destination.is_relative_to(fixture_env.ROOT)
        for suffix in ('','-wal','-shm'):
            destination.with_name(destination.name+suffix).unlink(missing_ok=True)
        with closing(sqlite3.connect(str(fixture_env.RUNTIME/'seed-base.sqlite'))) as src, closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
        self.network=deny_external_sockets();self.network.start();self.addCleanup(self.network.stop)
        self.client=TestClient(app);self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)
        self.login(self.client)
    def login(self,client,username='offline_admin'):
        client.headers.update({'X-App-Request':'1','X-Store-ID':'1'})
        result=client.post('/api/auth/login',json={'username':username,'password':fixture_env.PASSWORD.read_text()})
        self.assertEqual(result.status_code,200,result.text)
        client.headers['X-CSRF-Token']=client.cookies.get('dealer_csrf')
        return result.json()
    def new_run(self,content='查询姓张的客户',client=None):
        client=client or self.client
        r=client.post(BASE+'/sessions',json={'title':'离线回归'});self.assertEqual(r.status_code,201,r.text)
        sid=r.json()['id'];body={'request_id':'test_'+uuid4().hex,'content':content}
        r=client.post(BASE+f'/sessions/{sid}/runs',json=body);self.assertEqual(r.status_code,202,r.text)
        return sid,r.json(),body
    def tick(self,provider):
        with provider.installed(): return asyncio.run(Worker().tick())
    def session(self,sid):
        r=self.client.get(BASE+'/sessions/'+sid);self.assertEqual(r.status_code,200,r.text);return r.json()
    def count(self,model):
        with SessionLocal() as db:return db.scalar(select(func.count()).select_from(model))
    def prepare(self,name='离线客户甲'):
        sid,run,_=self.new_run('新建客户'+name+'，暂不允许联系。')
        p=Provider(customer_steps(name));result=self.tick(p)
        self.assertIsNone(result['error'],result)
        self.assertEqual(result['status'],'succeeded',result)
        cards=self.session(sid)['proposals'];self.assertEqual(len(cards),1,cards)
        self.assertEqual(cards[0]['status'],'pending',cards)
        return sid,cards[0],run,p
    def confirm(self,sid,card):
        return self.client.post(BASE+f"/sessions/{sid}/proposals/{card['id']}/confirm",json={'digest':card['digest']})

    def test_registry_complete_and_unique(self):
        registry=domain_registry();self.assertEqual(len(registry._specs),49)
        for name,spec in registry._specs.items():
            for operation in spec.operation_ids:self.assertIs(registry.spec_for_operation(operation),spec)
            for key in spec.fact_keys:self.assertIs(registry.spec_for_fact(key),spec)
        self.assertEqual(registry.spec_for_operation('POST /api/flow/cases').name,'flow_case')
        self.assertEqual(registry.spec_for_operation('POST /api/procurement/orders/{case_id}/actions/{action}').name,'material_procurement')
        self.assertEqual(registry.spec_for_operation('POST /api/group/benefits/members/{member_id}/actions/{action}').name,'group_benefit')
    def test_case_fact_applicability_remains_exact(self):
        reg=domain_registry()
        for spec in reg._specs.values():
            if 'case' not in spec.object_types:continue
            for fact in spec.fact_keys:
                for _,kind,version in spec.fact_kind_versions+spec.kind_versions:
                    self.assertTrue(reg.supports_fact(fact,'case',kind=kind,flow_version=version))
                self.assertFalse(reg.supports_fact(fact,'case',kind='unknown',flow_version=1))
                self.assertFalse(reg.supports_fact(fact,'case',kind='repair',flow_version=999))
                self.assertFalse(reg.supports_fact(fact,'case',kind='repair',flow_version=True))
    def test_registry_still_rejects_duplicate_and_unscoped_facts(self):
        reg=DomainRegistry();spec=domain_registry()._specs['flow_case'];reg.register(spec)
        with self.assertRaises(ValueError):reg.register(DomainAdapterSpec(name='duplicate',factory=spec.factory,object_types=('case',),operation_ids=spec.operation_ids))
        with self.assertRaises(ValueError):reg.register(DomainAdapterSpec(name='unscoped',factory=spec.factory,object_types=('case',),fact_keys=('x.y',)))
    def test_http_acceptance_and_request_idempotency(self):
        sid,run,body=self.new_run()
        again=self.client.post(BASE+f'/sessions/{sid}/runs',json=body)
        self.assertEqual(again.status_code,202,again.text);self.assertEqual(again.json()['id'],run['id'])
        self.assertEqual(self.count(Run),1);self.assertEqual(self.count(AssistantMessage),1)
        with SessionLocal() as db:
            row=db.get(Run,run['id']);self.assertIsNotNone(db.get(LoginSession,row.login_session_ref))
    def test_reused_request_with_changed_content_is_rejected(self):
        sid,_,body=self.new_run();body['content']='另一个目标'
        result=self.client.post(BASE+f'/sessions/{sid}/runs',json=body)
        self.assertEqual(result.status_code,409,result.text);self.assertEqual(self.count(Run),1)
    def test_cookie_login_does_not_bypass_csrf(self):
        sid,_,_=self.new_run();self.client.headers.pop('X-CSRF-Token')
        result=self.client.post(BASE+f'/sessions/{sid}/runs',json={'request_id':'csrf_'+uuid4().hex,'content':'新请求'})
        self.assertEqual(result.status_code,403,result.text)
    def test_run_is_not_visible_in_other_store(self):
        _,run,_=self.new_run();self.client.headers['X-Store-ID']='2'
        result=self.client.get(BASE+'/runs/'+run['id']);self.assertEqual(result.status_code,404,result.text)
    def test_read_tool_loop_uses_original_api_without_business_writes(self):
        counts=[self.count(m) for m in (Customer,Case,CashEntry,StockMove)]
        sid,run,_=self.new_run();p=Provider();result=self.tick(p)
        self.assertEqual(result['run_id'],run['id']);self.assertEqual(result['status'],'succeeded',result)
        self.assertEqual(len(p.requests),2)
        messages=p.requests[1]['messages'];tool_message=next(m for m in messages if m['role']=='tool')
        self.assertEqual(json.loads(tool_message['content'])['status'],200)
        self.assertEqual([self.count(m) for m in (Customer,Case,CashEntry,StockMove)],counts)
        self.assertEqual(self.session(sid)['proposals'],[])
    def test_prepare_never_writes_original_business(self):
        before=[self.count(m) for m in (Customer,Case,CashEntry,StockMove)]
        sid,card,run,p=self.prepare()
        self.assertEqual(len(p.requests),3)
        self.assertEqual([self.count(m) for m in (Customer,Case,CashEntry,StockMove)],before)
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(RunItem).where(RunItem.kind=='confirmation')),0)
    def test_employee_confirm_is_idempotent(self):
        sid,card,_,_=self.prepare();before=self.count(Customer)
        result=self.confirm(sid,card);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['proposals'][0]['status'],'succeeded',result.text)
        self.assertEqual(self.count(Customer),before+1)
        again=self.confirm(sid,card);self.assertEqual(again.status_code,200,again.text)
        self.assertEqual(self.count(Customer),before+1)
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(RunItem).where(RunItem.kind=='confirmation')),1)
    def test_tampered_digest_never_creates_business(self):
        sid,card,_,_=self.prepare();before=self.count(Customer);card['digest']='0'*64
        result=self.confirm(sid,card);self.assertEqual(result.status_code,409,result.text)
        self.assertEqual(self.count(Customer),before)
    def test_logout_before_claim_stops_without_model(self):
        _,run,_=self.new_run();logout=self.client.post('/api/auth/logout',json={});self.assertEqual(logout.status_code,200,logout.text);p=Provider();result=self.tick(p)
        self.assertFalse(result['claimed']);self.assertEqual(p.requests,[])
        with SessionLocal() as db:self.assertEqual(db.get(Run,run['id']).status,'cancelled')
    def test_queued_cancel_stops_without_model(self):
        _,run,_=self.new_run();result=self.client.post(BASE+'/runs/'+run['id']+'/cancel',json={'expected_version':run['version']})
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['status'],'cancelled')
        p=Provider();self.tick(p);self.assertEqual(p.requests,[])
    def test_model_response_after_cancel_is_discarded(self):
        sid,run,_=self.new_run();before=self.count(Customer)
        def cancel(index,body):
            status=self.client.get(BASE+'/runs/'+run['id']).json()
            result=self.client.post(BASE+'/runs/'+run['id']+'/cancel',json={'expected_version':status['version']})
            self.assertEqual(result.status_code,200,result.text)
        p=Provider([tool('prepare_business_form',{'form_ref':'crm:customers','values':{'name':'禁止迟到写入'},'summary':'禁止迟到写入'})],before_response=cancel)
        self.tick(p);self.assertEqual(len(p.requests),1)
        self.assertEqual(self.count(Customer),before);self.assertEqual(self.count(AssistantProposal),0)
        self.assertNotIn('禁止迟到写入',json.dumps(self.session(sid),ensure_ascii=False))
    def test_unknown_confirmation_outcome_never_reposts_native_command(self):
        sid,card,_,_=self.prepare();before=self.count(Customer);calls=[];native=gateway.invoke
        async def lose_response(*args,**kwargs):
            operation=args[2]
            result=await native(*args,**kwargs)
            if operation.startswith('POST '):calls.append(operation);raise TimeoutError('synthetic response loss')
            return result
        with patch.object(gateway,'invoke',lose_response):first=self.confirm(sid,card)
        self.assertEqual(first.status_code,200,first.text);self.assertEqual(first.json()['proposals'][0]['status'],'uncertain',first.text)
        self.assertEqual(self.count(Customer),before+1);self.assertEqual(len(calls),1)
        with patch.object(gateway,'invoke',lose_response):second=self.confirm(sid,card)
        self.assertEqual(second.status_code,200,second.text);self.assertEqual(len(calls),1);self.assertEqual(self.count(Customer),before+1)
    def test_expired_lease_cannot_heartbeat_or_overwrite_new_claim(self):
        _,run,_=self.new_run();now=utcnow()
        with SessionLocal() as db:old=queue.claim_next(db,'old-worker',clock=lambda:now)
        later=now+timedelta(seconds=queue.LEASE_SECONDS+1)
        with SessionLocal() as db:recovered=queue.reclaim_expired(db,clock=lambda:later)
        self.assertEqual(recovered.status,'queued')
        latest=later+timedelta(seconds=queue.RETRY_DELAYS[0]+1)
        with SessionLocal() as db:new=queue.claim_next(db,'new-worker',clock=lambda:latest)
        self.assertIsNotNone(new);self.assertGreater(new.fence,old.fence)
        with SessionLocal() as db:
            with self.assertRaises(HTTPException):queue.heartbeat(db,old,clock=lambda:latest)
        with SessionLocal() as db:
            with self.assertRaises(HTTPException):queue.release(db,old,outcome='succeeded',clock=lambda:latest)
        with SessionLocal() as db:
            row=db.get(Run,run['id']);self.assertEqual(row.status,'running');self.assertEqual(row.lease_owner,'new-worker');self.assertEqual(row.fence,new.fence)

    def test_malformed_tool_arguments_stop_instead_of_requeue(self):
        sid,run,_=self.new_run();before=self.count(Customer)
        bad=tool('prepare_business_form',{},'bad');bad['tool_calls'][0]['function']['arguments']='{"broken":'
        p=Provider([bad]);result=self.tick(p)
        self.assertEqual(result['status'],'failed',result);self.assertEqual(len(p.requests),1)
        self.assertEqual(self.count(Customer),before);self.assertEqual(self.count(AssistantProposal),0)
        self.tick(p);self.assertEqual(len(p.requests),1)
        self.assertEqual(self.session(sid)['last_request']['status'],'completed')
    def test_duplicate_tool_ids_reject_whole_reply_before_any_preparation(self):
        _,run,_=self.new_run();before=self.count(Customer)
        bad=tool('prepare_business_form',{'form_ref':'crm:customers','values':{'name':'不能部分准备'},'summary':'不能部分准备'})
        bad['tool_calls'].append(dict(bad['tool_calls'][0]))
        result=self.tick(Provider([bad]));self.assertEqual(result['status'],'failed',result)
        self.assertEqual(self.count(Customer),before);self.assertEqual(self.count(AssistantProposal),0)
    def test_one_bad_call_prevents_valid_call_in_same_reply(self):
        _,_,_=self.new_run();before=self.count(Customer)
        calls=tool('prepare_business_form',{'form_ref':'crm:customers','values':{'name':'同片段不可写'},'summary':'同片段不可写'},'first')
        bad=tool('prepare_business_form',{},'second')['tool_calls'][0];bad['function']['arguments']='[]';calls['tool_calls'].append(bad)
        result=self.tick(Provider([calls]));self.assertEqual(result['status'],'failed',result)
        self.assertEqual(self.count(Customer),before);self.assertEqual(self.count(AssistantProposal),0)
    def test_logout_during_provider_response_discards_late_content(self):
        _,_,_=self.new_run();before=self.count(Customer)
        def logout(index,body):
            result=self.client.post('/api/auth/logout',json={});self.assertEqual(result.status_code,200,result.text)
        p=Provider([tool('prepare_business_form',{'form_ref':'crm:customers','values':{'name':'已退出不得准备'},'summary':'已退出不得准备'})],before_response=logout)
        result=self.tick(p)
        self.assertEqual(result['status'],'cancelled',result);self.assertEqual(len(p.requests),1)
        self.assertEqual(self.count(Customer),before);self.assertEqual(self.count(AssistantProposal),0)
    def test_stream_protocol_failure_is_typed_without_tool_execution(self):
        from app.assistant_runtime_provider import call_model,ModelProtocolError
        from app.business_assistant_service import load_config
        p=Provider([reply('unused')],stream_chunks=['data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"a","type":"function","function":{"name":"prepare_business_form","arguments":"{"}}]},"finish_reason":"tool_calls"}]}\n\n','data: [DONE]\n\n'])
        async def emit(kind,payload):pass
        with p.installed(),self.assertRaises(ModelProtocolError) as caught:
            asyncio.run(call_model(load_config(),[{'role':'user','content':'离线协议测试'}],stream=True,emit=emit))
        self.assertEqual(caught.exception.status_code,503);self.assertEqual(caught.exception.runtime_usage['http_requests'],1)
        self.assertEqual(self.count(AssistantProposal),0)
    def test_complete_stream_retains_protocol_and_usage(self):
        from app.assistant_runtime_provider import call_model
        from app.business_assistant_service import load_config
        p=Provider([reply('中文响应')]);events=[]
        async def emit(kind,payload):events.append((kind,payload))
        with p.installed():result=asyncio.run(call_model(load_config(),[{'role':'user','content':'离线协议测试'}],stream=True,emit=emit))
        self.assertEqual(result.message['content'],'中文响应');self.assertEqual(result.usage['tokens']['total_tokens'],120)
        self.assertEqual(''.join(e[1]['text'] for e in events if e[0]=='delta'),'中文响应')

    def test_login_restarts_only_busy_snapshot_before_session_commit(self):
        from app import security
        from app.models import AppMetadata, AuditLog
        from sqlalchemy import event
        original=security.verify_password;checks=[];codes=[]
        def concurrent_commit(password,encoded):
            valid=original(password,encoded);checks.append(valid)
            if len(checks)==1:
                with SessionLocal() as writer:
                    writer.add(AppMetadata(key='offline_concurrent_login',value={'synthetic':True}));writer.commit()
            return valid
        def capture(context):
            codes.append(getattr(context.original_exception,'sqlite_errorcode',None))
        before_sessions=self.count(LoginSession);before_audits=self.count(AuditLog)
        event.listen(engine,'handle_error',capture)
        try:
            with patch.object(security,'verify_password',concurrent_commit):
                response=self.client.post('/api/auth/login',json={'username':'offline_admin','password':fixture_env.PASSWORD.read_text()})
        finally:event.remove(engine,'handle_error',capture)
        self.assertEqual(response.status_code,200,{'status':response.status_code,'sqlite_codes':codes})
        self.assertEqual(codes,[sqlite3.SQLITE_BUSY_SNAPSHOT]);self.assertEqual(checks,[True,True])
        self.assertEqual(self.count(LoginSession),before_sessions+1);self.assertEqual(self.count(AuditLog),before_audits+1)

    def test_bad_password_busy_snapshot_keeps_exactly_one_failure(self):
        from app import security
        from app.models import AppMetadata,LoginAttempt
        original=security.verify_password;checks=[];sessions=self.count(LoginSession)
        def concurrent_commit(password,encoded):
            valid=original(password,encoded);checks.append(valid)
            if len(checks)==1:
                with SessionLocal() as writer:
                    writer.add(AppMetadata(key='offline_invalid_login',value={'synthetic':True}));writer.commit()
            return valid
        with patch.object(security,'verify_password',concurrent_commit):
            response=self.client.post('/api/auth/login',json={'username':'offline_admin','password':'INVALID-SYNTHETIC-PASSWORD'})
        self.assertEqual(response.status_code,401,response.text);self.assertEqual(checks,[False,False])
        self.assertEqual(self.count(LoginAttempt),1);self.assertEqual(self.count(LoginSession),sessions)
        self.assertNotIn('set-cookie',response.headers)

    def test_login_snapshot_retry_is_bounded_and_never_sets_cookies(self):
        from app import security
        from app.models import AppMetadata,AuditLog
        original=security.verify_password;checks=[];sessions=self.count(LoginSession);audits=self.count(AuditLog)
        def concurrent_commit(password,encoded):
            valid=original(password,encoded);checks.append(valid)
            with SessionLocal() as writer:
                writer.add(AppMetadata(key='offline_busy_'+str(len(checks)),value={'synthetic':True}));writer.commit()
            return valid
        with patch.object(security,'verify_password',concurrent_commit):
            response=self.client.post('/api/auth/login',json={'username':'offline_admin','password':fixture_env.PASSWORD.read_text()})
        self.assertEqual(response.status_code,503,response.text);self.assertEqual(checks,[True,True])
        self.assertEqual(self.count(LoginSession),sessions);self.assertEqual(self.count(AuditLog),audits)
        self.assertNotIn('set-cookie',response.headers)

    def test_login_retry_rechecks_new_account_disable(self):
        from app import security
        original=security.verify_password;checks=[];sessions=self.count(LoginSession)
        def revoke_during_verify(password,encoded):
            valid=original(password,encoded);checks.append(valid)
            if len(checks)==1:
                with SessionLocal() as writer:
                    user=writer.scalar(select(User).where(User.username=='offline_admin'));user.active=False;writer.commit()
            return valid
        with patch.object(security,'verify_password',revoke_during_verify):
            response=self.client.post('/api/auth/login',json={'username':'offline_admin','password':fixture_env.PASSWORD.read_text()})
        self.assertEqual(response.status_code,401,response.text);self.assertEqual(checks,[True,True])
        self.assertEqual(self.count(LoginSession),sessions);self.assertNotIn('set-cookie',response.headers)

if __name__=='__main__':unittest.main(verbosity=2)

