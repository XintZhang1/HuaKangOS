"""Sales facts use native writes and scoped native reads, never invented success receipts."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env
import test_runtime_integration as baseline
import asyncio
from copy import deepcopy
from datetime import timedelta
import unittest
from uuid import uuid4
from sqlalchemy import select, func, update
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal, today
from app.models import Vehicle, User, CashEntry, Sale
from app.flow_models import Case, Customer, VehicleHold, Account, Task, FlowEvent, RequestReceipt
from app.assistant_runtime_registry import domain_registry
from app.assistant_runtime_principal import native_reader_for_principal
from app.assistant_runtime_queue import claim_next
from app.assistant_runtime_schemas import BusinessObjectRef
from app.assistant_runtime_domains.sales_order import SalesOrderAdapter, SALES_READ, SALES_FACTS


def request_id(): return 'sales_' + uuid4().hex


class SalesFixture:
    setUp = baseline.RuntimeIntegration.setUp
    login = baseline.RuntimeIntegration.login
    new_run = baseline.RuntimeIntegration.new_run
    tick = baseline.RuntimeIntegration.tick
    session = baseline.RuntimeIntegration.session
    confirm = baseline.RuntimeIntegration.confirm

    def employee(self, role):
        password = fixture_env.PASSWORD.read_text()
        name = 'sales_fact_' + role
        r = self.client.post('/api/users', json={'username':name, 'display_name':'合成销售事实'+role,
            'role':role, 'password':password+'Initial', 'store_ids':[1],
            'store_roles':[{'store_id':1,'role':role}]})
        self.assertEqual(r.status_code,201,r.text)
        client=TestClient(app);client.__enter__();self.addCleanup(client.__exit__,None,None,None)
        client.headers.update({'X-App-Request':'1','X-Store-ID':'1'})
        r=client.post('/api/auth/login',json={'username':name,'password':password+'Initial'})
        self.assertEqual(r.status_code,200,r.text)
        client.headers['X-CSRF-Token']=client.cookies.get('dealer_csrf')
        r=client.post('/api/auth/password',json={'current_password':password+'Initial','new_password':password})
        self.assertEqual(r.status_code,200,r.text)
        self.login(client,name)
        return client

    def order(self):
        r=self.client.post('/api/vehicle-catalog/entry',json={'request_id':request_id(),
            'brand_name':'合成车型品牌','series_name':'合成测试车系','name':'合成报价车型',
            'model_year':2026,'fuel_type':'petrol','seats':5,'displacement_ml':1500})
        self.assertEqual(r.status_code,200,r.text)
        self.model=r.json()['model']
        with SessionLocal() as db:
            customer=db.scalar(select(Customer.id).where(Customer.store_id==1))
            self.account=db.scalar(select(Account.id).where(Account.store_id==1,Account.active.is_(True)))
            cars=list(db.scalars(select(Vehicle).where(Vehicle.store_id==1,
                Vehicle.id.notin_(select(VehicleHold.vehicle_id)),
                Vehicle.id.notin_(select(Sale.active_vehicle_id).where(Sale.active_vehicle_id.is_not(None)))
            ).order_by(Vehicle.id).limit(2)))
            self.cars=[{'id':c.id,'version':c.version,'vin':c.vin} for c in cars]
        self.assertEqual(len(self.cars),2)
        for car in self.cars:
            r=self.client.post('/api/vehicle-catalog/vehicle-assignment',json={
                'request_id':request_id(),'version':0,'reason':'合成实车归属核对',
                'vehicle_id':car['id'],'vehicle_version':car['version'],'vin':car['vin'],'model_id':self.model['id']})
            self.assertEqual(r.status_code,200,r.text)
        self.quote={'model_id':self.model['id'],'model_version':self.model['version'],
            'amount_cents':100000,'delivery_due':(today()+timedelta(days=5)).isoformat(),
            'valid_until':(today()+timedelta(days=3)).isoformat(),
            'addon':False,'insurance':False,'agency':False,'terms':'仅用于合成报价测试','reason':'合成首次报价'}
        r=self.client.post('/api/sales-quotes/orders',json={
            'request_id':request_id(),'customer_id':customer,'quote':self.quote})
        self.assertEqual(r.status_code,201,r.text)
        self.ident=r.json()['id'];self.assertEqual(r.json()['flow_version'],4)
        return self.ident

    def detail(self, client=None):
        r=(client or self.client).get(f'/api/sales-quotes/orders/{self.ident}')
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def action(self, key, values=None, client=None, expect=200):
        client=client or self.client
        detail=self.detail(client)
        r=client.post(f'/api/flow/cases/{self.ident}/actions/{key}',json={
            'request_id':request_id(),'version':detail['version'],'values':values or {}})
        self.assertEqual(r.status_code,expect,r.text)
        return r

    def approve(self):
        if not hasattr(self,'reviewer'):self.reviewer=self.employee('manager')
        self.action('quote_approve',{'reason':'独立核对合成报价'},self.reviewer)

    def upload(self, category='evidence', source=None):
        data={'category':category}
        if source is not None:data['source_file_id']=str(source)
        r=self.client.post(f'/api/flow/cases/{self.ident}/files',data=data,
            files={'file':('synthetic.txt',('合成凭据，不是真实签名 '+uuid4().hex).encode(),'text/plain')})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()['id']

    def signed_file(self, kind='contract'):
        r=self.client.post(f'/api/flow/cases/{self.ident}/documents',json={'kind':kind})
        self.assertEqual(r.status_code,200,r.text)
        return self.upload('signed_contract' if kind=='contract' else 'signed_handover',r.json()['id'])

    def sign(self):
        evidence=self.signed_file();self.action('sign',{'evidence_id':evidence});return evidence

    def activate(self):
        self.order();self.approve();self.action('allocate',{'vehicle_id':self.cars[0]['id']});self.sign()

    def revise(self):
        r=self.client.post(f'/api/sales-quotes/orders/{self.ident}/quotes',json={
            'request_id':request_id(),'version':self.detail()['version'],
            'quote':{**self.quote,'reason':'合成变更报价','terms':'合成新报价条款'}})
        self.assertEqual(r.status_code,201,r.text)

    def before_delivery(self):
        self.activate()
        self.action('receive',{'amount':'1000.00','account_id':self.account,
            'reference':request_id(),'evidence_id':self.upload('receipt')})
        self.action('inspect',{'outcome':'合格','evidence_id':self.upload('inspection'),
            'result':'合成逐项检查合格'})

    def fact(self,key,transform=None,client=None):
        client=client or self.client
        # A real LoginSession produces the principal; no self-reported role.
        if not hasattr(self,'principals'):self.principals={}
        if id(client) not in self.principals:
            self.new_run('只读核对销售事实',client)
            with SessionLocal() as db:self.principals[id(client)]=claim_next(db,'sales-facts-'+str(len(self.principals)))
        principal=self.principals[id(client)]
        with SessionLocal() as db:
            native=native_reader_for_principal(db,principal,(SALES_READ,))
            async def read(*args,**kwargs):
                response=await native(*args,**kwargs)
                if transform:
                    response=deepcopy(response);transform(response['data'])
                return response
            return asyncio.run(SalesOrderAdapter(native_reader=read).fact_snapshot(
                principal,BusinessObjectRef(type='case',id=self.ident),key))


class SalesFacts(SalesFixture, unittest.TestCase):
    def test_registration_matches_supported_native_versions(self):
        for key in SALES_FACTS:
            for version in (3,4):self.assertTrue(domain_registry().supports_fact(key,'case',kind='order',flow_version=version))
            for version in (1,2,5,True):self.assertFalse(domain_registry().supports_fact(key,'case',kind='order',flow_version=version))

    def test_unapproved_pending_quote_does_not_prove_active_approval(self):
        self.order()
        self.assertIsNot(self.fact(SALES_FACTS[0]).satisfied,True)

    def test_approved_but_unsigned_quote_is_not_active_or_consented(self):
        self.order();self.approve()
        self.assertIsNone(self.detail()['active_quote_id'])
        for key in SALES_FACTS[:2]:self.assertIsNot(self.fact(key).satisfied,True)

    def test_current_signed_quote_proves_approval_and_consent_but_not_delivery(self):
        self.activate()
        for key in SALES_FACTS[:2]:
            result=self.fact(key);self.assertIs(result.satisfied,True,result);self.assertTrue(result.evidence_refs)
        self.assertIsNot(self.fact(SALES_FACTS[2]).satisfied,True)

    def test_inflight_revision_cannot_reuse_previous_signed_quote(self):
        self.activate();self.revise()
        for key in SALES_FACTS[:2]:self.assertIsNot(self.fact(key).satisfied,True)

    def test_withdrawal_restores_proven_previous_quote(self):
        self.activate();original=self.detail()['active_quote_id'];self.revise()
        self.action('quote_withdraw',{'reason':'客户撤回本次合成报价变更'})
        self.assertEqual(self.detail()['active_quote_id'],original)
        for key in SALES_FACTS[:2]:self.assertIs(self.fact(key).satisfied,True)

    def test_stock_role_hidden_review_remains_unknown_not_false(self):
        self.activate();inventory=self.employee('inventory')
        detail=self.detail(inventory)
        self.assertNotIn('review',detail['quotes'][0])
        self.assertIsNone(self.fact(SALES_FACTS[0],client=inventory).satisfied)
        self.assertIsNone(self.fact(SALES_FACTS[1],client=inventory).satisfied)

    def test_uploading_handover_is_not_delivery(self):
        self.activate();self.signed_file('handover')
        self.assertIsNot(self.fact(SALES_FACTS[2]).satisfied,True)

    def test_unproven_timestamp_fields_are_not_delivery(self):
        self.activate()
        def forged(data):data['data']={**data['data'],'delivered_at':'2026-09-29T00:00:00Z','delivery_receipt_id':99}
        self.assertIsNot(self.fact(SALES_FACTS[2],forged).satisfied,True)

    def test_settlement_and_dispatch_are_not_delivery(self):
        self.before_delivery();self.action('dispatch',{'evidence_id':self.upload()})
        self.assertIsNot(self.fact(SALES_FACTS[2]).satisfied,True)

    def test_original_deliver_action_proves_delivery(self):
        self.before_delivery();self.action('dispatch',{'evidence_id':self.upload()})
        evidence=self.signed_file('handover');self.action('deliver',{'evidence_id':evidence})
        self.assertEqual(self.detail()['data']['handover_file'],evidence)
        result=self.fact(SALES_FACTS[2]);self.assertIs(result.satisfied,True,result)

    def test_same_quote_consent_survives_modelled_revision_and_resigning(self):
        self.activate();old_quote=self.detail()['active_quote_id'];self.revise();self.approve();self.sign()
        self.assertNotEqual(self.detail()['active_quote_id'],old_quote)
        self.assertIs(self.fact(SALES_FACTS[1]).satisfied,True)

    def test_reallocated_vehicle_needs_new_matching_signature(self):
        self.activate();old_signed=self.detail()['data']['signed_file'];self.revise();self.approve()
        self.action('release_vehicle',{'reason':'合成实车更换','evidence_id':self.upload()})
        self.action('allocate',{'vehicle_id':self.cars[1]['id']})
        self.action('sign',{'evidence_id':old_signed},expect=409)
        self.assertIsNot(self.fact(SALES_FACTS[1]).satisfied,True)
        self.sign();self.assertIs(self.fact(SALES_FACTS[1]).satisfied,True)

    def test_historical_v3_uses_the_same_native_evidence_rules(self):
        self.order()
        # Explicit historical-version fixture, not a claim that create emits v3.
        with SessionLocal() as db:
            row=db.get(Case,self.ident);row.flow_version=3;db.commit()
        self.approve();self.action('allocate',{'vehicle_id':self.cars[0]['id']});self.sign()
        self.assertEqual(self.detail()['flow_version'],3)
        for key in SALES_FACTS[:2]:self.assertIs(self.fact(key).satisfied,True)

    def test_consent_for_different_vehicle_is_not_current_evidence(self):
        self.activate()
        # Fault injection in this test's disposable DB, never a native write path.
        with SessionLocal() as db:
            row=db.get(Case,self.ident);row.vehicle_id=self.cars[1]['id'];db.commit()
        self.assertIsNot(self.fact(SALES_FACTS[1]).satisfied,True)

    def test_consent_pointer_cannot_reuse_an_unrelated_file(self):
        self.activate();other=self.upload('evidence')
        with SessionLocal() as db:
            row=db.get(Case,self.ident);row.data={**row.data,'signed_file':other};db.commit()
        self.assertIsNot(self.fact(SALES_FACTS[1]).satisfied,True)

    def test_quarantined_signature_is_unknown_not_a_new_business_instruction(self):
        from app.file_security_models import FileSecurity
        self.activate();signed=self.detail()['data']['signed_file']
        # Simulate a later failed scan. Do not weaken or call the scan authority.
        with SessionLocal() as db:
            db.execute(update(FileSecurity).where(FileSecurity.file_id==signed).values(state='quarantined'));db.commit()
        self.assertIsNone(self.fact(SALES_FACTS[1]).satisfied)
        self.assertIs(self.fact(SALES_FACTS[0]).satisfied,True)

    def test_pending_approval_and_withdrawn_fields_cannot_fake_active_approval(self):
        self.order();self.approve();self.action('quote_withdraw',{'reason':'合成撤回报价'})
        self.assertIsNot(self.fact(SALES_FACTS[0]).satisfied,True)

    def test_missing_projection_never_falls_back_to_guessing(self):
        self.activate()
        self.assertIsNone(self.fact(SALES_FACTS[1],lambda d:d.pop('business_facts')).satisfied)

    def test_projection_rejects_wrong_version_or_nonboolean_truth(self):
        self.activate()
        for name,value in [('schema_version',True),('schema_version',2),('case_version',True),('case_version',0)]:
            with self.subTest(name=name,value=value):
                def corrupt(data):data['business_facts'][name]=value
                self.assertIsNone(self.fact(SALES_FACTS[1],corrupt).satisfied)
        for value in ('true',1,{},[]):
            with self.subTest(value=value):
                def corrupt(data):data['business_facts']['facts'][SALES_FACTS[1]]=value
                self.assertIsNone(self.fact(SALES_FACTS[1],corrupt).satisfied)

    def test_stale_quote_projection_cannot_be_applied_to_new_quote(self):
        self.activate()
        def stale(data):data['business_facts']['active_quote_id']=data['active_quote_id']+1
        self.assertIsNone(self.fact(SALES_FACTS[1],stale).satisfied)

    def test_boolean_or_missing_quote_identity_is_never_proof(self):
        self.activate()
        def boolean(data):
            data['active_quote_id']=True;data['business_facts']['active_quote_id']=True
        def missing(data):
            data.pop('pending_quote_id');data['business_facts'].pop('pending_quote_id')
        def unsigned(data):
            data['active_quote_id']=None;data['business_facts']['active_quote_id']=None
        def pending(data):
            data['pending_quote_id']=99;data['business_facts']['pending_quote_id']=99
        for transform in (boolean,missing,unsigned,pending):
            with self.subTest(transform=transform.__name__):
                self.assertIsNone(self.fact(SALES_FACTS[1],transform).satisfied)

    def test_unknown_workflow_version_has_no_fact_support(self):
        self.activate()
        self.assertIsNone(self.fact(SALES_FACTS[1],lambda d:d.update(flow_version=99)).satisfied)

    def test_cross_store_fact_is_inaccessible(self):
        self.activate()
        def moved(data):data['store_id']=2
        with self.assertRaises(HTTPException) as raised:self.fact(SALES_FACTS[1],moved)
        self.assertEqual(raised.exception.status_code,404)

    def test_state_and_task_alone_are_not_delivery(self):
        self.activate();evidence=self.signed_file('handover')
        with SessionLocal() as db:
            row=db.get(Case,self.ident);row.state='delivered';row.data={**row.data,'handover_file':evidence}
            task=db.scalar(select(Task).where(Task.case_id==self.ident,Task.key=='deliver'));task.status='done'
            db.commit()
        self.assertIsNot(self.fact(SALES_FACTS[2]).satisfied,True)

    def test_reading_facts_has_no_business_side_effects(self):
        from app.sales_quote_models import SalesQuoteConsent, SalesQuoteReview, SalesQuote
        from app.business_assistant_models import AssistantProposal
        self.activate();self.fact(SALES_FACTS[0]) # Establish a real principal first.
        models=(CashEntry,FlowEvent,RequestReceipt,SalesQuoteConsent,SalesQuoteReview,SalesQuote,AssistantProposal)
        def snapshot():
            with SessionLocal() as db:
                return [db.scalar(select(func.count()).select_from(m)) for m in models]+[db.get(Case,self.ident).version]
        before=snapshot()
        for key in SALES_FACTS:self.fact(key)
        self.assertEqual(snapshot(),before)


class SalesPlan(SalesFixture, unittest.TestCase):
    def test_native_sales_facts_drive_sign_and_delivery_without_automatic_confirmation(self):
        from app.business_assistant_models import AssistantWorkPlan
        from test_followup_integration import FollowupIntegration
        from fake_provider import Provider, tool, reply
        self.order();self.approve();self.action('allocate',{'vehicle_id':self.cars[0]['id']})
        signed=self.signed_file()
        steps=[{'key':'sign','title':'确认本版客户签回',
                'object_ref':{'type':'case','id':self.ident},'form_ref':f'case:{self.ident}:sign',
                'conditions':[{'type':'native_action_available','object_ref':{'type':'case','id':self.ident},'action_key':'sign'}],
                'completion_conditions':[{'type':'fact_exists','object_ref':{'type':'case','id':self.ident},'fact_key':SALES_FACTS[1]}]},
               {'key':'deliver','title':'确认客户接车','depends_on':['sign'],
                'object_ref':{'type':'case','id':self.ident},'form_ref':f'case:{self.ident}:deliver',
                'conditions':[{'type':'fact_exists','object_ref':{'type':'case','id':self.ident},'fact_key':SALES_FACTS[1]},
                              {'type':'native_action_available','object_ref':{'type':'case','id':self.ident},'action_key':'deliver'}],
                'completion_conditions':[{'type':'fact_exists','object_ref':{'type':'case','id':self.ident},'fact_key':SALES_FACTS[2]}]}]
        sid,_,_=self.new_run('跟进客户本版签回和实际交车，两步分别由我确认。')
        outcome=self.tick(Provider([tool('save_work_plan',{'schema_version':2,'goal':'本版签回及客户接车','steps':steps}),reply('事项已保存。')]))
        self.assertEqual(outcome['status'],'succeeded',outcome)
        with SessionLocal() as db:
            plan=db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.session_id==sid))
            self.assertIsNotNone(plan);pid=plan.id
        FollowupIntegration.followup(self,pid,'enable')
        def prepare(step,evidence):
            return Provider([tool('prepare_business_form',{'form_ref':step['form_ref'],'values':{'evidence_id':evidence},'summary':step['title']}),reply('请核对后确认。')])
        result=FollowupIntegration.tick_until_run(self,prepare(steps[0],signed))
        self.assertEqual(result['status'],'succeeded',result)
        cards=self.session(sid)['proposals'];self.assertEqual(len(cards),1)
        self.assertIsNone(self.detail()['active_quote_id'])
        r=self.confirm(sid,cards[0]);self.assertEqual(r.status_code,200,r.text)
        quiet=Provider([AssertionError('Do not prepare delivery before native prerequisites')])
        self.assertFalse(FollowupIntegration.tick_until_run(self,quiet)['claimed']);self.assertEqual(quiet.requests,[])
        self.action('receive',{'amount':'1000.00','account_id':self.account,'reference':request_id(),'evidence_id':self.upload('receipt')})
        self.action('inspect',{'outcome':'合格','evidence_id':self.upload('inspection'),'result':'合成逐项检查合格'})
        self.action('dispatch',{'evidence_id':self.upload()});handover=self.signed_file('handover')
        result=FollowupIntegration.tick_until_run(self,prepare(steps[1],handover))
        self.assertEqual(result['status'],'succeeded',result)
        cards=self.session(sid)['proposals'];self.assertEqual(len(cards),2)
        self.assertNotEqual(self.detail()['state'],'delivered')
        r=self.confirm(sid,next(c for c in cards if c['status']=='pending'));self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.detail()['state'],'delivered')
        self.assertFalse(FollowupIntegration.tick_until_run(self,quiet)['claimed'])
        self.assertEqual(self.plan(pid)['status'],'completed')
        self.assertEqual(quiet.requests,[])

    def plan(self,plan_id):
        from test_followup_integration import FollowupIntegration
        return FollowupIntegration.plan(self,plan_id)

if __name__=='__main__':unittest.main()

