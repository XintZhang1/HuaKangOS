"""Actual committed wake-event dispatch; no fabricated notification rows."""
import sys,traceback,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fixture_env
import test_followup_integration as baseline
from unittest.mock import patch
from sqlalchemy import select,func
from app.db import SessionLocal
from app.assistant_runtime_models import Notification,WakeEvent
from app import assistant_runtime_outbox as outbox
from fake_provider import Provider

class FollowupNotifications(unittest.TestCase):
    setUp=baseline.FollowupIntegration.setUp
    login=baseline.FollowupIntegration.login
    new_run=baseline.FollowupIntegration.new_run
    tick=baseline.FollowupIntegration.tick
    session=baseline.FollowupIntegration.session
    plan=baseline.FollowupIntegration.plan
    create_plan=baseline.FollowupIntegration.create_plan
    followup=baseline.FollowupIntegration.followup
    tick_until_run=baseline.FollowupIntegration.tick_until_run
    preparation=baseline.FollowupIntegration.preparation
    confirm=baseline.FollowupIntegration.confirm
    count=baseline.FollowupIntegration.count

    def test_prepared_card_gets_actual_deduplicated_notification(self):
        failures=[];cas=outbox._event_cas
        def capture(*args,**kwargs):
            if kwargs.get('state')=='pending' and sys.exception() is not None:
                failures.extend(traceback.format_exception(sys.exception()))
            return cas(*args,**kwargs)
        with patch.object(outbox,'_event_cas',side_effect=capture):
            sid,pid,steps=self.create_plan();self.followup(pid,'enable')
            result=self.tick_until_run(self.preparation(steps[0]));self.assertEqual(result['status'],'succeeded',result)
            card=self.session(sid)['proposals'][0]
            with SessionLocal() as db:pending=db.scalar(select(func.count()).select_from(WakeEvent).where(WakeEvent.state=='pending'))
            quiet=Provider([AssertionError('Waiting for employee confirmation')])
            for _ in range(pending+1):self.tick(quiet)
        self.assertEqual(failures,[],''.join(failures))
        with SessionLocal() as db:
            notices=list(db.scalars(select(Notification).where(Notification.proposal_id==card['id'])))
            self.assertEqual(len(notices),1)
            self.assertEqual(notices[0].kind,'proposal_ready')
            self.assertEqual(notices[0].status,'unread')
        response=self.client.get('/api/business-assistant/notifications')
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(any(n['proposal_id']==card['id'] for n in response.json()['items']))
        self.assertEqual(quiet.requests,[])

    def test_status_reports_switches_without_reading_changing_workspace(self):
        from app import assistant_runtime_workspace as workspace
        with patch.object(workspace,'read_workspace',side_effect=AssertionError('Status cannot depend on projections')):
            response=self.client.get('/api/business-assistant/status')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['features'],{'home':True,'runtime':True,'followup':True,'notifications':True})

if __name__=='__main__':unittest.main()
