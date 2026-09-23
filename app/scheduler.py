"""Single-process scheduler with persisted report idempotency and DB leases.
The machine must be awake and the app running. No external ChatGPT automation.
"""
import logging
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, func
from .config import settings
from .db import SessionLocal
from .models import DailyReport, MODULES, Store
from .tenancy import set_scope
from .reports import generate_report

log = logging.getLogger(__name__)


def tick_store(store_id):
    now = datetime.now(ZoneInfo(settings.timezone))
    ready = (now.hour,now.minute) >= (settings.report_hour,settings.report_minute)
    latest = now.date()-timedelta(days=1 if ready else 2)
    with SessionLocal() as db:
        set_scope(db,[store_id],store_id)
        first_dates = [db.scalar(select(func.min(model.business_date))) for model in MODULES.values()]
        first_dates = [d for d in first_dates if d is not None]
        if not first_dates: return
        first = min(first_dates)
        start = max(first, latest-timedelta(days=settings.catchup_days-1))
        saved = list(db.scalars(select(DailyReport).where(DailyReport.business_date>=start,DailyReport.business_date<=latest)))
        done = {r.business_date for r in saved if not r.snapshot.get('provisional',True)}
    day = start
    while day <= latest:
        if day not in done:
            generate_report(day,use_ai=settings.allow_ai and bool(settings.deepseek_key),store_id=store_id)
        day += timedelta(days=1)


def tick():
    with SessionLocal() as db:
        ids = list(db.scalars(select(Store.id).where(Store.active.is_(True))))
    for store_id in ids:
        try: tick_store(store_id)
        except Exception as exc: log.warning('Store report deferred: store=%s type=%s', store_id, type(exc).__name__)


class ReportScheduler:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None
    def start(self):
        if not settings.scheduler_enabled or settings.scheduler_mode != 'embedded': return
        def loop():
            # Let startup complete; run missed reports, then inspect schedule every 30 seconds.
            while not self.stop_event.wait(5 if self.thread is None else 30):
                try: tick()
                except Exception as exc:
                    # No credentials or record content in logs.
                    log.warning('Daily report scheduler deferred a run (%s)',type(exc).__name__)
        self.thread = threading.Thread(target=loop,name='daily-report-scheduler',daemon=True)
        self.thread.start()
    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=3)
