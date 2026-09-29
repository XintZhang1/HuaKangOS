"""Regression tests for procurement return and repair re-quality facts."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env
import asyncio
import unittest
from types import SimpleNamespace

from app.assistant_runtime_domains.material_procurement import MaterialProcurementAdapter
from app.assistant_runtime_domains.repair_order import RepairOrderAdapter
from app.assistant_runtime_domains.retail_order import RetailOrderAdapter
from fastapi import HTTPException
from app.assistant_runtime_schemas import BusinessObjectRef


PRINCIPAL = SimpleNamespace(store_id=1)
REF = BusinessObjectRef(type='case', id=7)


def run_fact(adapter, key):
    return asyncio.run(adapter.fact_snapshot(PRINCIPAL, REF, key))


def reader(data):
    async def read(*args, **kwargs):
        return {'status': 200, 'data': data}
    return read


class ProcurementReturnFacts(unittest.TestCase):
    def base(self):
        return {'id':7,'store_id':1,'version':3,'number':'P7','state':'receiving',
                'lines':[],'receipts':[],'returns':[],'payments':[]}

    def fact(self, data):
        return run_fact(MaterialProcurementAdapter(native_reader=reader(data)),
                        'procurement.return_posted')

    def test_requested_return_is_not_posted(self):
        data=self.base();data['returns']=[{'id':11,'status':'requested',
            'lines':[{'id':1,'receipt_id':5,'quantity_milli':1000}]}]
        self.assertIs(self.fact(data).satisfied,False)

    def test_approved_return_is_not_posted(self):
        data=self.base();data['returns']=[{'id':11,'status':'approved',
            'lines':[{'id':1,'receipt_id':5,'quantity_milli':1000}]}]
        self.assertIs(self.fact(data).satisfied,False)

    def test_dispatched_return_with_receipt_link_is_posted(self):
        data=self.base();data['returns']=[{'id':11,'status':'dispatched',
            'lines':[{'id':1,'receipt_id':5,'quantity_milli':1000}]}]
        result=self.fact(data)
        self.assertIs(result.satisfied,True,result)

    def test_dispatched_return_without_receipt_link_is_unknown(self):
        data=self.base();data['returns']=[{'id':11,'status':'dispatched',
            'lines':[{'id':1,'quantity_milli':1000}]}]
        self.assertIsNone(self.fact(data).satisfied)


class RepairQualityFacts(unittest.TestCase):
    def base(self, state='settling'):
        return {'id':7,'store_id':1,'version':4,'number':'R7','state':state,
                'quotes':[{'id':21,'revision':1,'authorized':True,'cancelled':False}],
                'quality':[{'id':31,'quote_id':21,'passed':True,'result':'合格','evidence_id':41}],
                'actions':[],'data':{}}

    def fact(self, data):
        return run_fact(RepairOrderAdapter(native_reader=reader(data)),
                        'repair.passed_quality_recorded')

    def test_passed_quality_is_current_while_settling(self):
        result=self.fact(self.base())
        self.assertIs(result.satisfied,True,result)

    def test_old_pass_is_invalid_after_material_return_reopens_quality(self):
        result=self.fact(self.base('quality'))
        self.assertIs(result.satisfied,False,result)

    def test_new_failed_quality_is_false(self):
        data=self.base('working')
        data['quality'].append({'id':32,'quote_id':21,'passed':False,
                                'result':'需返工','evidence_id':42})
        self.assertIs(self.fact(data).satisfied,False)

    def test_new_pass_after_requality_is_true(self):
        data=self.base('settling')
        data['quality'].append({'id':32,'quote_id':21,'passed':True,
                                'result':'复检合格','evidence_id':42})
        self.assertIs(self.fact(data).satisfied,True)



class RetailReadErrors(unittest.TestCase):
    def test_native_conflict_keeps_human_readable_detail(self):
        async def conflict(*args, **kwargs):
            return {'status':409,'data':{'detail':'native conflict'}}
        adapter=RetailOrderAdapter(native_reader=conflict)
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(adapter.read_snapshot(PRINCIPAL,REF))
        self.assertEqual(raised.exception.status_code,409)
        self.assertEqual(raised.exception.detail,'原业务暂不能读取此精品单，请到原页面核对')


class ProcurementNativeFlow(unittest.TestCase):
    """Real original procurement API proves requested/approved/dispatched boundaries."""
    @classmethod
    def setUpClass(cls):
        import fixture_env
        import test_runtime_integration as baseline
        cls._baseline=baseline

    def login(self, client, username='offline_admin'):
        return self._baseline.RuntimeIntegration.login(self,client,username)

    def new_run(self, content, client=None):
        return self._baseline.RuntimeIntegration.new_run(self,content,client)

    def setUp(self):
        self._baseline.RuntimeIntegration.setUp(self)

    def login_employee(self, role):
        import fixture_env
        from fastapi.testclient import TestClient
        from app.main import app
        from uuid import uuid4
        password=fixture_env.PASSWORD.read_text();name='proc_fact_'+role+'_'+uuid4().hex[:8]
        r=self.client.post('/api/users',json={'username':name,'display_name':'合成采购事实'+role,
            'role':role,'password':password+'Initial','store_ids':[1],
            'store_roles':[{'store_id':1,'role':role}]})
        self.assertEqual(r.status_code,201,r.text)
        client=TestClient(app);client.__enter__();self.addCleanup(client.__exit__,None,None,None)
        client.headers.update({'X-App-Request':'1','X-Store-ID':'1'})
        r=client.post('/api/auth/login',json={'username':name,'password':password+'Initial'})
        self.assertEqual(r.status_code,200,r.text)
        client.headers['X-CSRF-Token']=client.cookies.get('dealer_csrf')
        r=client.post('/api/auth/password',json={'current_password':password+'Initial','new_password':password})
        self.assertEqual(r.status_code,200,r.text)
        self._baseline.RuntimeIntegration.login(self,client,name)
        return client

    def request_id(self):
        from uuid import uuid4
        return 'proc_'+uuid4().hex

    def upload(self, case_id, client=None):
        from uuid import uuid4
        client=client or self.client
        r=client.post(f'/api/flow/cases/{case_id}/files',data={'category':'evidence'},
            files={'file':('synthetic.txt',('合成采购凭据 '+uuid4().hex).encode(),'text/plain')})
        self.assertEqual(r.status_code,200,r.text);return r.json()['id']

    def detail(self, case_id, client=None):
        r=(client or self.client).get(f'/api/procurement/orders/{case_id}')
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def action(self, case_id, action, values, client=None):
        client=client or self.client;current=self.detail(case_id,client)
        r=client.post(f'/api/procurement/orders/{case_id}/actions/{action}',json={
            'request_id':self.request_id(),'version':current['version'],'values':values})
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def fact(self, case_id, key):
        import asyncio
        from app.db import SessionLocal
        from app.assistant_runtime_queue import claim_next
        from app.assistant_runtime_principal import native_reader_for_principal
        from app.assistant_runtime_domains.material_procurement import PROC_READ
        from app.assistant_runtime_schemas import BusinessObjectRef
        self._baseline.RuntimeIntegration.new_run(self,'核对采购事实')
        with SessionLocal() as db:
            principal=claim_next(db,'proc-facts-'+self.request_id())
        with SessionLocal() as db:
            native=native_reader_for_principal(db,principal,(PROC_READ,))
            return asyncio.run(MaterialProcurementAdapter(native_reader=native).fact_snapshot(
                principal,BusinessObjectRef(type='case',id=case_id),key))

    def create_received_order(self):
        from sqlalchemy import select
        from app.db import SessionLocal
        from app.master_models import Supplier
        from app.flow_models import Item, Account
        with SessionLocal() as db:
            supplier=db.scalar(select(Supplier).where(Supplier.store_id==1,Supplier.active.is_(True)))
            item=db.scalar(select(Item).where(Item.store_id==1,Item.active.is_(True)))
            account=db.scalar(select(Account).where(Account.store_id==1,Account.active.is_(True)))
            self.assertIsNotNone(supplier);self.assertIsNotNone(item);self.assertIsNotNone(account)
            supplier_id,item_id,account_id=supplier.id,item.id,account.id
        r=self.client.post('/api/procurement/orders',json={'request_id':self.request_id(),
            'supplier_id':supplier_id,'reason':'合成采购事实验证',
            'lines':[{'item_id':item_id,'quantity_milli':1000,'unit_cost_cents':1000}]})
        self.assertEqual(r.status_code,201,r.text);case_id=r.json()['id']
        manager=self.login_employee('manager')
        self.action(case_id,'approve',{},manager)
        line=self.detail(case_id)['lines'][0]
        self.action(case_id,'receive',{'evidence_id':self.upload(case_id),
            'lines':[{'line_id':line['id'],'quantity_milli':1000}]})
        return case_id,account_id

    def test_original_return_flow_only_becomes_posted_after_dispatch(self):
        case_id,_=self.create_received_order();receipt=self.detail(case_id)['receipts'][0]
        self.action(case_id,'return_request',{'reason':'合成采购退货',
            'evidence_id':self.upload(case_id),'lines':[{'receipt_id':receipt['id'],'quantity_milli':1000}]})
        self.assertIs(self.fact(case_id,'procurement.return_posted').satisfied,False)
        manager=self.login_employee('manager');returned=self.detail(case_id)['returns'][0]
        self.action(case_id,'return_approve',{'return_id':returned['id'],'return_version':returned['version'],
            'reason':'合成批准退货'},manager)
        self.assertIs(self.fact(case_id,'procurement.return_posted').satisfied,False)
        returned=self.detail(case_id)['returns'][0]
        self.action(case_id,'return_dispatch',{'return_id':returned['id'],'return_version':returned['version'],
            'evidence_id':self.upload(case_id)})
        result=self.fact(case_id,'procurement.return_posted')
        self.assertIs(result.satisfied,True,result)

    def test_original_payment_with_cash_link_proves_payment(self):
        case_id,account_id=self.create_received_order()
        self.action(case_id,'pay',{'evidence_id':self.upload(case_id),'amount_cents':1000,
            'account_id':account_id,'reference':self.request_id()})
        result=self.fact(case_id,'procurement.payment_recorded')
        self.assertIs(result.satisfied,True,result)


if __name__=='__main__':unittest.main()
