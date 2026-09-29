"""Fact truth against real native Lead detail/actions, plus untrusted response cases."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fixture_env
import test_runtime_integration as baseline
import asyncio, unittest
from copy import deepcopy
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import aliased
from app.db import SessionLocal
from app.flow_models import Case,Task
from app.models import User
from app.assistant_runtime_domains.lead import LeadAdapter,FLOW_READ
from app.assistant_runtime_principal import native_reader_for_principal
from app.assistant_runtime_queue import claim_next
from app.assistant_runtime_schemas import BusinessObjectRef

class LeadFacts(unittest.TestCase):
    setUp=baseline.RuntimeIntegration.setUp
    login=baseline.RuntimeIntegration.login
    new_run=baseline.RuntimeIntegration.new_run

    def lead(self):
        r=self.client.post('/api/flow/cases',json={'request_id':'seed_'+uuid4().hex,'kind':'lead',
             'values':{'customer_name':'合成事实客户','source':'展厅到店'}})
        self.assertEqual(r.status_code,201,r.text)
        return r.json()['id']

    def fact(self,ident,key,transform=None):
        if not hasattr(self,'principal'):
            self.new_run('只读核对售前事实')
            with SessionLocal() as db:self.principal=claim_next(db,'fact-check')
        with SessionLocal() as db:
            native=native_reader_for_principal(db,self.principal,(FLOW_READ,))
            async def read(*args,**kwargs):
                response=await native(*args,**kwargs)
                if transform:
                    response=deepcopy(response)
                    transform(response['data'])
                return response
            return asyncio.run(LeadAdapter(native_reader=read).fact_snapshot(self.principal,
                 BusinessObjectRef(type='case',id=ident),key))

    def test_creator_owner_is_not_completed_reception_assignment(self):
        ident=self.lead()
        detail=self.client.get('/api/flow/cases/'+str(ident)).json()
        self.assertGreater(detail['owner_id'],0)
        self.assertEqual(detail['state'],'unassigned')
        self.assertEqual(next(t for t in detail['tasks'] if t['key']=='assign')['status'],'open')
        result=self.fact(ident,'lead.owner_assigned')
        self.assertFalse(result.satisfied,result)

    def test_original_assign_action_proves_assignment(self):
        ident=self.lead()
        detail=self.client.get('/api/flow/cases/'+str(ident)).json()
        with SessionLocal() as db: employee=db.scalar(select(User.id).where(User.username=='demo_sales'))
        r=self.client.post(f'/api/flow/cases/{ident}/actions/assign',json={
            'request_id':'action_'+uuid4().hex,'version':detail['version'],'values':{'assignee_id':employee}})
        self.assertEqual(r.status_code,200,r.text)
        result=self.fact(ident,'lead.owner_assigned')
        self.assertTrue(result.satisfied,result)
        self.assertTrue(result.evidence_refs)

    def test_visible_real_reserved_order_child_proves_reservation(self):
        child=aliased(Case)
        with SessionLocal() as db:
            pair=db.execute(select(Case.id,child.id).join(child,child.parent_id==Case.id).where(
                 Case.kind=='lead',child.kind=='order',Case.store_id==1,child.store_id==1)).first()
        self.assertIsNotNone(pair,'Migrated seed must include a real linked order')
        parent_id,order_id=pair
        native=self.client.get('/api/flow/cases/'+str(parent_id))
        self.assertEqual(native.status_code,200,native.text)
        self.assertTrue(any(c['id']==order_id and c['kind']=='order' for c in native.json()['children']))
        result=self.fact(parent_id,'lead.reserve_recorded')
        self.assertTrue(result.satisfied,result)
        self.assertTrue(any(getattr(e.source_id,'id',None)==order_id for e in result.evidence_refs))

    def test_unrelated_case_link_is_not_reservation_evidence(self):
        ident=self.lead()
        def bad_link(data):data['links']=[{'kind':'case','id':ident}]
        self.assertIsNot(self.fact(ident,'lead.reserve_recorded',bad_link).satisfied,True)

    def test_unproven_native_order_number_is_not_reservation_evidence(self):
        ident=self.lead()
        def unproven(data):data['data']={**(data.get('data') or {}),'order_id':ident}
        self.assertIsNot(self.fact(ident,'lead.reserve_recorded',unproven).satisfied,True)

    def test_foreign_store_or_parent_child_cannot_prove_reservation(self):
        ident=self.lead()
        for store,parent in ((2,ident),(1,ident+1)):
            def wrong_child(data):data['children']=[{'id':ident+100,'kind':'order','store_id':store,'parent_id':parent,'version':1,'flow_version':2}]
            with self.subTest(store=store,parent=parent):
                self.assertIsNot(self.fact(ident,'lead.reserve_recorded',wrong_child).satisfied,True)

    def test_lead_facts_are_reachable_through_the_registry(self):
        from app.assistant_runtime_registry import domain_registry
        from app.assistant_runtime_domains.lead import LEAD_FACTS
        for key in LEAD_FACTS:
            for version in (1,2):self.assertTrue(domain_registry().supports_fact(key,'case',kind='lead',flow_version=version),key)
            for kind,version in [('lead',3),('order',1),('lead',True)]:
                self.assertFalse(domain_registry().supports_fact(key,'case',kind=kind,flow_version=version))

    def test_public_condition_uses_native_assignment_not_creator_ownership(self):
        from app.assistant_runtime_conditions import evaluate_conditions
        ident=self.lead();self.fact(ident,'lead.owner_assigned')
        conditions=[{'type':'fact_exists','object_ref':{'type':'case','id':ident},'fact_key':'lead.owner_assigned'}]
        def check():
            with SessionLocal() as db:return asyncio.run(evaluate_conditions(db,self.principal,conditions,purpose='completion'))
        before=check();self.assertFalse(before.satisfied);self.assertFalse(before.unknown)
        detail=self.client.get('/api/flow/cases/'+str(ident)).json()
        with SessionLocal() as db:employee=db.scalar(select(User.id).where(User.username=='demo_sales'))
        response=self.client.post(f'/api/flow/cases/{ident}/actions/assign',json={
            'request_id':'action_'+uuid4().hex,'version':detail['version'],'values':{'assignee_id':employee}})
        self.assertEqual(response.status_code,200,response.text)
        after=check();self.assertTrue(after.satisfied,after);self.assertTrue(after.evidence)
        self.assertNotEqual(before.fingerprint,after.fingerprint)

    def test_public_condition_verifies_the_real_linked_order(self):
        from app.assistant_runtime_conditions import evaluate_conditions
        child=aliased(Case)
        with SessionLocal() as db:
            pair=db.execute(select(Case.id,child.id).join(child,child.parent_id==Case.id).where(
                Case.kind=='lead',child.kind=='order',Case.store_id==1,child.store_id==1)).first()
        self.assertIsNotNone(pair)
        self.fact(pair[0],'lead.reserve_recorded')
        with SessionLocal() as db:result=asyncio.run(evaluate_conditions(db,self.principal,[{
            'type':'fact_exists','object_ref':{'type':'case','id':pair[0]},'fact_key':'lead.reserve_recorded'}],purpose='completion'))
        self.assertTrue(result.satisfied,result)
        self.assertTrue(any(getattr(e.source_id,'id',None)==pair[1] for e in result.evidence))

    def test_historical_v1_assignment_uses_original_action_and_public_condition(self):
        from app.assistant_runtime_conditions import evaluate_conditions
        ident=self.lead()
        # Deliberate historical fixture: freeze v1 before any original action.
        with SessionLocal() as db:
            db.get(Case,ident).flow_version=1;db.commit()
            employee=db.scalar(select(User.id).where(User.username=='demo_sales'))
        detail=self.client.get('/api/flow/cases/'+str(ident)).json()
        self.assertEqual(detail['flow_version'],1)
        response=self.client.post(f'/api/flow/cases/{ident}/actions/assign',json={
            'request_id':'action_'+uuid4().hex,'version':detail['version'],'values':{'assignee_id':employee}})
        self.assertEqual(response.status_code,200,response.text)
        self.fact(ident,'lead.owner_assigned')
        with SessionLocal() as db:result=asyncio.run(evaluate_conditions(db,self.principal,[{
            'type':'fact_exists','object_ref':{'type':'case','id':ident},'fact_key':'lead.owner_assigned'}],purpose='completion'))
        self.assertTrue(result.satisfied,result)

if __name__=='__main__':unittest.main()
