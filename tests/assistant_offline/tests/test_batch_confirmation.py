"""Original batch confirmation API, original records and injected response loss."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fixture_env
import test_runtime_integration as baseline
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import select,func
from app.db import SessionLocal
from app.flow_models import Customer
from app.assistant_runtime_models import RunItem
from app import business_assistant_gateway as gateway
from fake_provider import Provider,tool,reply
BASE=baseline.BASE

class BatchConfirmation(unittest.TestCase):
    setUp=baseline.RuntimeIntegration.setUp
    login=baseline.RuntimeIntegration.login
    new_run=baseline.RuntimeIntegration.new_run
    tick=baseline.RuntimeIntegration.tick
    session=baseline.RuntimeIntegration.session
    count=baseline.RuntimeIntegration.count

    def prepare_batch(self,n=3):
        self.names=['合成批量'+uuid4().hex[:8] for _ in range(n)]
        sid,_,_=self.new_run('为以下客户分别建档，全部暂不允许联系：'+'、'.join(self.names))
        before=self.count(Customer)
        provider=Provider([tool('prepare_business_batch',{'form_ref':'crm:customers','rows':[
            {'values':{'name':name,'contact_allowed':False},'summary':'建档 '+name} for name in self.names]}),reply('请核对本组客户。')])
        result=self.tick(provider);self.assertEqual(result['status'],'succeeded',result)
        cards=self.session(sid)['proposals'];self.assertEqual(len(cards),n,cards)
        self.assertTrue(all(c['status']=='pending' for c in cards));self.assertEqual(self.count(Customer),before)
        return sid,cards

    def batch(self,sid,cards,action='confirm'):
        return self.client.post(BASE+'/sessions/'+sid+'/proposals/batch',json={
            'action':action,'items':[{'id':c['id'],'digest':c['digest']} for c in cards]})

    def created(self):
        with SessionLocal() as db:return db.scalar(select(func.count()).select_from(Customer).where(Customer.name.in_(self.names)))

    def test_successful_batch_uses_independent_original_confirmations_once(self):
        sid,cards=self.prepare_batch();r=self.batch(sid,cards)
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['batch']['done'],3)
        self.assertEqual(self.created(),3)
        repeat=self.batch(sid,cards);self.assertEqual(repeat.status_code,200,repeat.text)
        self.assertEqual(self.created(),3)
        with SessionLocal() as db:self.assertEqual(db.scalar(select(func.count()).select_from(RunItem).where(RunItem.kind=='confirmation')),3)

    def test_bad_second_digest_pauses_third_without_rolling_back_first(self):
        sid,cards=self.prepare_batch();bad=[dict(c) for c in cards];bad[1]['digest']='0'*64
        r=self.batch(sid,bad);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual([x['status'] for x in r.json()['batch']['items']],['succeeded','refused','skipped'])
        self.assertEqual(r.json()['batch']['total'],3);self.assertEqual(self.created(),1)
        self.assertEqual([c['status'] for c in self.session(sid)['proposals']],['succeeded','pending','pending'])
        # Only this new, explicit employee click authorizes the remaining cards.
        r=self.batch(sid,cards[1:]);self.assertEqual(r.status_code,200,r.text);self.assertEqual(self.created(),3)

    def test_missing_second_card_pauses_remaining_without_swallowing_rows(self):
        sid,cards=self.prepare_batch();bad=[dict(c) for c in cards];bad[1]['id']=str(uuid4())
        r=self.batch(sid,bad);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual([x['status'] for x in r.json()['batch']['items']],['succeeded','refused','skipped'])
        self.assertEqual(self.created(),1)

    def test_lost_second_response_freezes_unknown_and_never_replays(self):
        sid,cards=self.prepare_batch();original=gateway.invoke;calls=[]
        async def lose_after_commit(request,user,operation_id,**kwargs):
            result=await original(request,user,operation_id,**kwargs)
            if operation_id==cards[0]['operation_id']:
                calls.append(operation_id)
                if len(calls)==2:raise ConnectionError('synthetic lost response after real commit')
            return result
        with patch.object(gateway,'invoke',side_effect=lose_after_commit):
            r=self.batch(sid,cards);self.assertEqual(r.status_code,200,r.text)
            self.assertEqual([x['status'] for x in r.json()['batch']['items']],['succeeded','uncertain','skipped'])
            self.assertEqual(self.created(),2)
            repeat=self.batch(sid,cards);self.assertEqual(repeat.status_code,200,repeat.text)
        self.assertEqual(len(calls),2);self.assertEqual(self.created(),2)
        self.assertEqual(self.session(sid)['proposals'][2]['status'],'pending')

    def test_cancellation_also_stops_at_first_refusal(self):
        sid,cards=self.prepare_batch();bad=[dict(c) for c in cards];bad[1]['digest']='0'*64
        r=self.batch(sid,bad,'cancel');self.assertEqual(r.status_code,200,r.text)
        self.assertEqual([x['status'] for x in r.json()['batch']['items']],['cancelled','refused','skipped'])
        self.assertEqual(self.created(),0)

    def test_duplicate_selection_is_rejected_before_any_native_write(self):
        sid,cards=self.prepare_batch();r=self.batch(sid,[cards[0],cards[0]])
        self.assertEqual(r.status_code,422,r.text);self.assertEqual(self.created(),0)

    def test_cross_step_batch_is_rejected_before_any_native_write(self):
        sid,_,_=self.new_run('给甲和乙分别建档，分成两步给我确认。');self.names=['合成甲'+uuid4().hex[:8],'合成乙'+uuid4().hex[:8]]
        a=tool('prepare_business_form',{'form_ref':'crm:customers','values':{'name':self.names[0],'contact_allowed':False},'summary':'建档甲','step':'甲','step_order':1},'a')
        b=tool('prepare_business_form',{'form_ref':'crm:customers','values':{'name':self.names[1],'contact_allowed':False},'summary':'建档乙','step':'乙','step_order':2},'b')
        a['tool_calls'].extend(b['tool_calls']);result=self.tick(Provider([a,reply('两步分别核对。')]))
        self.assertEqual(result['status'],'succeeded',result);cards=self.session(sid)['proposals'];self.assertEqual(len(cards),2)
        r=self.batch(sid,cards);self.assertEqual(r.status_code,422,r.text);self.assertEqual(self.created(),0)

if __name__=='__main__':unittest.main()
