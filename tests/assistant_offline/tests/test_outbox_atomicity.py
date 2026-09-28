"""Faults after notification flush must not commit half an outbox delivery."""
import sys,asyncio,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fixture_env
import test_runtime_integration as baseline
from unittest.mock import patch
from datetime import timedelta
from sqlalchemy import select,func
from fastapi import HTTPException
from app.db import SessionLocal,utcnow
from app.assistant_runtime_models import Notification,WakeEvent
from app import assistant_runtime_outbox as outbox
from app.assistant_worker import Worker
from fake_provider import Provider

class OutboxAtomicity(unittest.TestCase):
    setUp=baseline.RuntimeIntegration.setUp
    login=baseline.RuntimeIntegration.login
    new_run=baseline.RuntimeIntegration.new_run
    tick=baseline.RuntimeIntegration.tick
    session=baseline.RuntimeIntegration.session
    count=baseline.RuntimeIntegration.count
    prepare=baseline.RuntimeIntegration.prepare
    confirm=baseline.RuntimeIntegration.confirm

    def test_failed_dispatch_rolls_back_notification_and_retries_once(self):
        sid,card,_,_=self.prepare()
        with SessionLocal() as db:
            event=db.scalar(select(WakeEvent).where(WakeEvent.proposal_id==card['id']))
            ident=event.id
        original=outbox._event_cas
        def crash(db,event,**kwargs):
            if event['id']==ident and kwargs['state']=='dispatched':
                raise HTTPException(409,'synthetic failure after notification flush')
            return original(db,event,**kwargs)
        quiet=Provider([AssertionError('Dispatch must never invoke the model')])
        with patch.object(outbox,'_event_cas',side_effect=crash):
            result=self.tick(quiet)
        self.assertEqual(result['dispatch'],'pending',result)
        self.assertEqual(self.count(Notification),0,'The failed delivery left a committed notification')
        with SessionLocal() as db:
            event=db.get(WakeEvent,ident);self.assertEqual(event.state,'pending');self.assertEqual(event.attempt,1)
            later=event.next_attempt_at+timedelta(seconds=1)
        with quiet.installed():
            outcome=asyncio.run(Worker(clock=lambda:later).tick())
        self.assertEqual(outcome['dispatch'],'dispatched',outcome)
        self.assertEqual(self.count(Notification),1)
        for _ in range(3):self.tick(quiet)
        self.assertEqual(self.count(Notification),1);self.assertEqual(quiet.requests,[])
        self.assertEqual(self.session(sid)['proposals'][0]['status'],'pending')

if __name__=='__main__':unittest.main()
