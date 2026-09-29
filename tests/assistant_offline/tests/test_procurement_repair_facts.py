"""Regression tests for procurement return and repair re-quality facts."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asyncio
import unittest
from types import SimpleNamespace

from app.assistant_runtime_domains.material_procurement import MaterialProcurementAdapter
from app.assistant_runtime_domains.repair_order import RepairOrderAdapter
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


if __name__=='__main__':unittest.main()
