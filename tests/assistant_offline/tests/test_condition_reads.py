"""Per-proof GET reuse; pure copy/key checks and real identity/fact regressions."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env
import asyncio
from collections import Counter
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from sqlalchemy import select
from app.db import SessionLocal, utcnow
from app.assistant_runtime_conditions import _Evaluator, evaluate_conditions
from app.assistant_runtime_registry import domain_registry
from app.assistant_runtime_domains import FLOW_READ, SALES_READ, SALES_FACTS
from app.assistant_runtime_plans import resolve_followup_check
from app.assistant_runtime_principal import principal_for_grant_probe
from app.assistant_runtime_models import FollowupGrant
from app.business_assistant_models import AssistantWorkPlan
from test_sales_facts import SalesFixture
from fake_provider import Provider,tool,reply


class ReadReuseUnit(unittest.TestCase):
    """Transport/key tests only; these stubs are not authorization evidence."""
    def reader(self):
        value=_Evaluator(None,SimpleNamespace(_clock=utcnow),clock=utcnow,
                         registry=domain_registry(),client_factory=None)
        value.guard=lambda:None
        value.original_get=AsyncMock(return_value={'status':200,'data':{'items':[{'id':1}]}})
        return value
    def test_duplicate_read_returns_independent_copy(self):
        async def check():
            e=self.reader();first=await e.native(FLOW_READ,path_args={'case_id':1})
            first['data']['items'][0]['id']=999
            second=await e.native(FLOW_READ,path_args={'case_id':1})
            self.assertEqual(second['data']['items'][0]['id'],1)
            self.assertEqual(e.original_get.await_count,1)
        asyncio.run(check())
    def test_full_query_and_path_are_part_of_identity(self):
        async def check():
            e=self.reader()
            for path,query,body in [({'case_id':1},{},None),({'case_id':2},{},None),
                    ({'case_id':1},{'page':2},None),({'case_id':1},{},{})]:
                await e.native(FLOW_READ,path_args=path,query=query,body=body)
            self.assertEqual(e.original_get.await_count,4)
        asyncio.run(check())
    def test_non_success_is_not_cached(self):
        async def check():
            e=self.reader();e.original_get.return_value={'status':503,'data':{}}
            for _ in range(2):await e.native(FLOW_READ,path_args={'case_id':1})
            self.assertEqual(e.original_get.await_count,2)
        asyncio.run(check())
    def test_truncated_top_level_is_not_cached(self):
        async def check():
            e=self.reader();e.original_get.return_value={'status':200,'truncated':True,'data':{}}
            for _ in range(2):await e.native(FLOW_READ,path_args={'case_id':1})
            self.assertEqual(e.original_get.await_count,2)
        asyncio.run(check())
    def test_truncated_native_object_is_not_cached(self):
        async def check():
            e=self.reader();e.original_get.return_value={'status':200,'data':{'truncated':True}}
            for _ in range(2):await e.native(FLOW_READ,path_args={'case_id':1})
            self.assertEqual(e.original_get.await_count,2)
        asyncio.run(check())
    def test_exception_is_not_cached(self):
        async def check():
            e=self.reader();e.original_get.side_effect=[HTTPException(503,'unavailable'),{'status':200,'data':{}}]
            with self.assertRaises(HTTPException):await e.native(FLOW_READ,path_args={'case_id':1})
            self.assertEqual((await e.native(FLOW_READ,path_args={'case_id':1}))['status'],200)
            self.assertEqual(e.original_get.await_count,2)
        asyncio.run(check())
    def test_separate_pass_cannot_reuse_a_previous_read(self):
        async def check():
            left,right=self.reader(),self.reader()
            right.original_get.return_value={'status':200,'data':{'id':2}}
            await left.native(FLOW_READ,path_args={'case_id':1})
            self.assertEqual((await right.native(FLOW_READ,path_args={'case_id':1}))['data']['id'],2)
            self.assertEqual(right.original_get.await_count,1)
        asyncio.run(check())
    def test_unregistered_operation_is_still_rejected(self):
        async def check():
            e=self.reader()
            with self.assertRaises(HTTPException):await e.native('POST /api/flow/cases',body={})
            with self.assertRaises(HTTPException):await e.native('GET /api/unregistered')
            self.assertEqual(e.original_get.await_count,0)
        asyncio.run(check())


class ReadReuseIntegration(SalesFixture,unittest.TestCase):
    def test_public_call_rejects_self_reported_identity_before_read(self):
        with SessionLocal() as db:
            with self.assertRaises(HTTPException) as error:
                asyncio.run(evaluate_conditions(db,SimpleNamespace(actor_id=1,store_id=1),[]))
            self.assertEqual(error.exception.status_code,403)

    def test_actual_logout_blocks_a_cached_response(self):
        self.activate();self.fact(SALES_FACTS[0]);principal=self.principals[id(self.client)]
        async def check():
            with SessionLocal() as db:
                e=_Evaluator(db,principal,clock=utcnow,registry=domain_registry(),client_factory=None)
                with patch.object(e,'original_get',wraps=e.original_get) as reads:
                    first=await e.native(SALES_READ,path_args={'key':self.ident},query={},body=None)
                    self.assertEqual(first['status'],200)
                    response=self.client.post('/api/auth/logout',json={})
                    self.assertEqual(response.status_code,200,response.text)
                    with self.assertRaises(HTTPException) as error:
                        await e.native(SALES_READ,path_args={'key':self.ident},query={},body=None)
                    self.assertIn(error.exception.status_code,(401,403,409))
                    self.assertEqual(reads.await_count,1)
        asyncio.run(check())

    def test_next_public_check_observes_original_business_changes(self):
        self.order();self.fact(SALES_FACTS[0]);principal=self.principals[id(self.client)]
        condition=[{'type':'fact_exists','object_ref':{'type':'case','id':self.ident},'fact_key':SALES_FACTS[1]}]
        def check():
            with SessionLocal() as db:return asyncio.run(evaluate_conditions(db,principal,condition,purpose='completion'))
        before=check();self.assertFalse(before.satisfied)
        self.approve();self.action('allocate',{'vehicle_id':self.cars[0]['id']});self.sign()
        after=check();self.assertTrue(after.satisfied,after)
        self.assertNotEqual(before.fingerprint,after.fingerprint)
        self.revise();current=check();self.assertFalse(current.satisfied,current)
        self.assertNotEqual(current.fingerprint,after.fingerprint)

    def test_one_plan_proof_reads_each_original_endpoint_once(self):
        self.activate()
        fact=lambda key:{'type':'fact_exists','object_ref':{'type':'case','id':self.ident},'fact_key':key}
        steps=[{'key':'signed','title':'核对本版签回','object_ref':{'type':'case','id':self.ident},
            'form_ref':f'case:{self.ident}:sign','conditions':[fact(SALES_FACTS[0])],
            'completion_conditions':[fact(SALES_FACTS[1])]},
            {'key':'delivered','title':'核对实车交付','depends_on':['signed'],
            'object_ref':{'type':'case','id':self.ident},'form_ref':f'case:{self.ident}:deliver',
            'conditions':[fact(SALES_FACTS[1])],'completion_conditions':[fact(SALES_FACTS[2])]}]
        sid,_,_=self.new_run('跟进本版客户签回与实际提车，由我分别确认。')
        result=self.tick(Provider([tool('save_work_plan',{'schema_version':2,'goal':'合成销售事实核查','steps':steps}),reply('事项已保存。')]))
        self.assertEqual(result['status'],'succeeded',result)
        with SessionLocal() as db:pid=db.scalar(select(AssistantWorkPlan.id).where(AssistantWorkPlan.session_id==sid))
        view=self.client.get('/api/business-assistant/plans/'+pid).json()
        response=self.client.post('/api/business-assistant/plans/'+pid+'/followup',json={'action':'enable','expected_version':view['version']})
        self.assertEqual(response.status_code,200,response.text)
        with SessionLocal() as db:gid=db.scalar(select(FollowupGrant.id).where(FollowupGrant.plan_id==pid,FollowupGrant.status=='active'))
        reads=[];original=_Evaluator.original_get
        async def counted(instance,operation_id,**kwargs):
            reads.append(operation_id)
            return await original(instance,operation_id,**kwargs)
        async def check():
            with SessionLocal() as db:
                principal=principal_for_grant_probe(db,gid)
                with patch.object(_Evaluator,'original_get',counted):
                    value=await resolve_followup_check(db,principal)
                self.assertFalse(value.required_complete)
        asyncio.run(check())
        self.assertEqual(Counter(reads),Counter({FLOW_READ:1,SALES_READ:1}),reads)

if __name__=='__main__':unittest.main()
