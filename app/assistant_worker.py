"""Single-slot assistant Runtime worker for the Windows preview and Linux process.

Importing this module starts nothing: no thread, no connection and no claim. The
reviewed local preview embeds one ``Worker`` only after its own marker is
verified; an independent deployment runs ``python -m app.assistant_worker``
beside the Web image with the same explicit database configuration.

Nothing in this module performs a business write. The worker dispatches committed
signals, checks explicitly granted due plans, recovers expired leases and drives
one authorized Run through the runtime's reviewed paths; a confirmed business submission stays an employee click
on the original API. Feature switches stay default-off, and a disabled runtime
never claims work.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import signal
import threading
import uuid
from datetime import datetime, timedelta, timezone

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import make_url

from .config import ROOT, settings
from .db import SessionLocal, engine, get_write_db, utcnow
from .models import AppMetadata

log = logging.getLogger(__name__)

WORKER_KEY_PREFIX = 'assistant_runtime_worker:'
WORKER_KEY_MAX = 60
CHECK_SECONDS = 5
HEARTBEAT_SECONDS = 20
HEALTH_SECONDS = 60
STALE_SECONDS = 7 * 24 * 60 * 60
CLEANUP_SECONDS = 3600
RUNTIME_REVISION = 'h53k_assistant_runtime'
RUNTIME_TABLES = (
    'business_assistant_plan_steps',
    'business_assistant_work_items',
    'business_assistant_runs',
    'business_assistant_run_items',
    'business_assistant_run_events',
    'business_assistant_context_snapshots',
    'business_assistant_followup_grants',
    'business_assistant_wake_events',
    'business_assistant_notifications',
)
SOURCE_PATTERNS = ('assistant_runtime_*.py', 'assistant_worker.py', 'business_assistant_*.py')
_SOURCE_CACHE: dict = {}
_INSTANCE_CACHE: dict = {}


class WorkerError(RuntimeError):
    """A start-up precondition failed; the message is a stable code, not data."""

    def __init__(self, code):
        self.code = str(code)
        super().__init__(self.code)


def _time(value):
    """Database timestamps are UTC-naive; every comparison uses that form."""
    if not isinstance(value, datetime):
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _clock_now(clock=None):
    value = _time((clock or utcnow)())
    if value is None:
        raise WorkerError('clock_not_datetime')
    return value


def _iso(value):
    moment = _time(value)
    return None if moment is None else moment.isoformat(timespec='seconds')


def _error_code(exc):
    """Only a stable code: never exception text, SQL, arguments or content."""
    from fastapi import HTTPException
    if isinstance(exc, WorkerError):
        return exc.code
    if isinstance(exc, HTTPException):
        return 'http_' + str(exc.status_code)
    return type(exc).__name__


def worker_key(worker_id):
    """The reserved metadata key; a 32-character id keeps the whole key <= 60."""
    if type(worker_id) is not str or not re.fullmatch(r'[0-9a-f]{32}', worker_id):
        raise WorkerError('worker_identity_invalid')
    key = WORKER_KEY_PREFIX + worker_id
    limit = AppMetadata.__table__.c.key.type.length or WORKER_KEY_MAX
    if len(key) > min(WORKER_KEY_MAX, limit):
        raise WorkerError('worker_key_too_long')
    return key


def new_worker_id():
    return uuid.uuid4().hex


def source_fingerprint(root=ROOT):
    """Hash of the reviewed assistant source names and bytes; no content is stored."""
    cached = _SOURCE_CACHE.get(str(root))
    if cached:
        return cached
    path = root / 'app'
    names = set()
    for pattern in SOURCE_PATTERNS:
        names.update(item.name for item in path.glob(pattern) if item.is_file())
    rows = [name + ':' + hashlib.sha256((path / name).read_bytes()).hexdigest()
            for name in sorted(names)]
    value = hashlib.sha256('\n'.join(rows).encode('utf-8')).hexdigest()[:16]
    _SOURCE_CACHE[str(root)] = value
    return value


def instance_identity(database_url=None):
    """A short, non-reversible database identity; no URL or credential is stored."""
    url = database_url or settings.database_url
    cached = _INSTANCE_CACHE.get(url)
    if cached:
        return cached
    try:
        parsed = make_url(url)
        safe = '|'.join([parsed.drivername, parsed.host or '', str(parsed.port or ''),
                         parsed.database or ''])
    except Exception:
        raise WorkerError('database_configuration_invalid') from None
    value = hashlib.sha256(safe.encode('utf-8')).hexdigest()[:16]
    _INSTANCE_CACHE[url] = value
    return value


def _revision_chain(current):
    """Ancestors of the instance revision from this checkout's migration scripts."""
    script = ScriptDirectory.from_config(AlembicConfig(str(ROOT / 'alembic.ini')))
    heads = set(script.get_heads())
    try:
        chain = {revision.revision for revision in script.iterate_revisions(current, 'base')}
    except Exception:
        raise WorkerError('migration_revision_unknown') from None
    chain.add(current)
    return chain, heads


def verify_instance(*, bound_engine=None, session_factory=None):
    """Refuse to start against a missing, unreachable or unprepared instance.

    Read-only: this never migrates, never initializes and never creates a
    database file. An instance must already be prepared at this code's migration
    head and must already contain the Runtime tables.
    """
    if not os.getenv('DATABASE_URL', '').strip():
        raise WorkerError('database_configuration_missing')
    bound = bound_engine if bound_engine is not None else engine
    factory = session_factory if session_factory is not None else SessionLocal
    try:
        with bound.connect() as connection:
            connection.execute(text('SELECT 1'))
            tables = set(inspect(connection).get_table_names())
            current = (connection.execute(text('SELECT version_num FROM alembic_version')).scalar()
                       if 'alembic_version' in tables else None)
    except WorkerError:
        raise
    except Exception:
        raise WorkerError('database_unreachable') from None
    if [name for name in RUNTIME_TABLES if name not in tables]:
        raise WorkerError('runtime_migration_missing')
    if not current:
        raise WorkerError('migration_head_unknown')
    chain, heads = _revision_chain(current)
    if RUNTIME_REVISION not in chain:
        raise WorkerError('runtime_migration_missing')
    if current not in heads:
        raise WorkerError('migration_head_mismatch')
    try:
        with factory() as db:
            db.execute(text('SELECT 1'))
    except Exception:
        raise WorkerError('database_unreachable') from None
    return {'revision': str(current), 'runtime_revision': RUNTIME_REVISION,
            'tables': len(tables), 'source': source_fingerprint(),
            'instance': instance_identity()}


def _heartbeat_value(*, now, error=None):
    """Exactly the reviewed fields; no user, business, session or database detail."""
    return {'at': _iso(now), 'source': source_fingerprint(),
            'instance': instance_identity(), 'error': None if error is None else str(error)}


def beat(*, worker_id, session_factory=None, clock=None, error=None, now=None):
    """Upsert this worker's own heartbeat row; never touches another worker's."""
    factory = session_factory if session_factory is not None else SessionLocal
    moment = _time(now) if now is not None else _clock_now(clock)
    key = worker_key(worker_id)
    value = _heartbeat_value(now=moment, error=error)
    with factory() as db:
        get_write_db(db)
        row = db.get(AppMetadata, key)
        if row is None:
            db.add(AppMetadata(key=key, value=value))
        else:
            row.value = value
        db.commit()
    return value


def beat_cleanup(*, session_factory=None, now=None, keep=None, stale_seconds=STALE_SECONDS):
    """Delete only expired rows under this worker's reserved key prefix."""
    factory = session_factory if session_factory is not None else SessionLocal
    moment = _time(now) if now is not None else utcnow()
    limit = moment - timedelta(seconds=stale_seconds)
    kept = worker_key(keep) if keep else None
    removed = []
    with factory() as db:
        get_write_db(db)
        rows = list(db.scalars(select(AppMetadata).where(
            AppMetadata.key.startswith(WORKER_KEY_PREFIX, autoescape=True))))
        for row in rows:
            if kept is not None and row.key == kept:
                continue
            value = row.value if isinstance(row.value, dict) else {}
            try:
                seen = _time(datetime.fromisoformat(str(value.get('at'))))
            except (TypeError, ValueError):
                seen = None
            if seen is None or seen < limit:
                removed.append(row.key)
                db.delete(row)
        if removed:
            db.commit()
    return removed


def heartbeats(*, session_factory=None, now=None, window_seconds=HEALTH_SECONDS):
    """Read-only view of the reserved prefix; no other metadata key is read."""
    factory = session_factory if session_factory is not None else SessionLocal
    moment = _time(now) if now is not None else utcnow()
    with factory() as db:
        rows = list(db.scalars(select(AppMetadata).where(
            AppMetadata.key.startswith(WORKER_KEY_PREFIX, autoescape=True))))
    seen = []
    for row in rows:
        value = row.value if isinstance(row.value, dict) else {}
        try:
            at = _time(datetime.fromisoformat(str(value.get('at'))))
        except (TypeError, ValueError):
            at = None
        age = None if at is None else (moment - at).total_seconds()
        seen.append({'worker': row.key[len(WORKER_KEY_PREFIX):], 'at': _iso(at),
                     'age_seconds': None if age is None else round(age, 1),
                     'fresh': bool(age is not None and 0 <= age <= window_seconds),
                     'source': value.get('source'), 'instance': value.get('instance'),
                     'error': value.get('error')})
    seen.sort(key=lambda item: (item['age_seconds'] is None, item['age_seconds'] or 0, item['worker']))
    return seen


def queue_counts(*, session_factory=None, now=None):
    """Aggregate counts only: no run, employee, session or content detail."""
    from .assistant_runtime_models import Run
    factory = session_factory if session_factory is not None else SessionLocal
    moment = _time(now) if now is not None else utcnow()
    with factory() as db:
        queued = db.scalar(select(func.count()).select_from(Run).where(Run.status == 'queued')) or 0
        running = db.scalar(select(func.count()).select_from(Run).where(Run.status == 'running')) or 0
        expired = db.scalar(select(func.count()).select_from(Run).where(
            Run.status == 'running', Run.lease_until.is_not(None), Run.lease_until <= moment)) or 0
        last = db.scalar(select(func.max(Run.finished_at)).where(
            Run.status.in_(('succeeded', 'failed', 'cancelled'))))
    return {'queued': int(queued), 'running': int(running), 'expired_leases': int(expired),
            'last_completed_at': _iso(last)}


def health_report(*, session_factory=None, now=None, bound_engine=None):
    """Read-only aggregate: fresh heartbeats, queue counts and last completion.

    It never writes, never claims and never prints a database URL, account,
    customer or Run content. ``healthy`` requires an enabled runtime, one fresh
    heartbeat and no expired lease still waiting for recovery.
    """
    moment = _time(now) if now is not None else utcnow()
    report = {'at': _iso(moment), 'runtime_enabled': bool(settings.assistant_runtime_enabled),
              'followup_enabled': bool(settings.assistant_followup_enabled),
              'source': source_fingerprint(), 'instance': instance_identity(),
              'workers': [], 'fresh_workers': 0, 'queued': None, 'running': None,
              'expired_leases': None, 'last_completed_at': None, 'issues': []}
    try:
        verify_instance(bound_engine=bound_engine, session_factory=session_factory)
    except WorkerError as exc:
        report['issues'].append(exc.code)
    except Exception as exc:
        report['issues'].append(_error_code(exc))
    try:
        report['workers'] = heartbeats(session_factory=session_factory, now=moment)
        report['fresh_workers'] = sum(1 for item in report['workers'] if item['fresh'])
        report.update(queue_counts(session_factory=session_factory, now=moment))
    except Exception as exc:
        report['issues'].append(_error_code(exc))
    if not report['runtime_enabled']:
        report['issues'].append('runtime_disabled')
    if not report['fresh_workers']:
        report['issues'].append('worker_heartbeat_stale')
    if report['expired_leases']:
        report['issues'].append('expired_lease_pending')
    report['healthy'] = not report['issues']
    return report


class Worker:
    """One slot: recover expired leases, claim at most one Run, drive it.

    ``start`` embeds ``run`` in a separate thread with its own asyncio loop;
    the caller only waits for that thread. ``run`` also owns the standalone
    process loop. Every state change is stopped -> running -> stopping -> stopped,
    and a stop only ends
    claiming: an execution already claimed finishes at its own safe boundary.
    """

    def __init__(self, *, worker_id=None, lease_owner=None, session_factory=None, clock=None,
                 runner=None, queue=None, config=None, check_seconds=CHECK_SECONDS,
                 heartbeat_seconds=HEARTBEAT_SECONDS, cleanup_seconds=CLEANUP_SECONDS,
                 stop_event=None, read_session_factory=None, bound_engine=None, outbox=None):
        self.worker_id = worker_id or new_worker_id()
        worker_key(self.worker_id)
        self.lease_owner = lease_owner or ('worker:' + self.worker_id)
        if not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,80}', self.lease_owner):
            raise WorkerError('lease_owner_invalid')
        self.session_factory = session_factory or SessionLocal
        self.clock = clock or utcnow
        self.read_session_factory = read_session_factory
        self.bound_engine = bound_engine
        self._runner = runner
        self._queue = queue
        self._outbox = outbox
        self.config = config
        self.check_seconds = check_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.cleanup_seconds = cleanup_seconds
        self.state = 'stopped'
        self._stop = stop_event or threading.Event()
        self._task = None
        self._thread = None
        self._thread_error = None
        self._lifecycle_lock = threading.Lock()
        self._owner_loop = None
        self._serve_task = None
        self._cancel_requested = False
        self._beater = None
        self.last_beat = None
        self.last_error = None
        self.cycles = 0
        self.executed = 0
        self._last_cleanup = None

    # -- reviewed dependencies -------------------------------------------------
    @property
    def queue(self):
        if self._queue is None:
            from . import assistant_runtime_queue as queue
            self._queue = queue
        return self._queue

    @property
    def runner(self):
        if self._runner is None:
            from .assistant_runtime_runner import run_once
            self._runner = run_once
        return self._runner

    @property
    def outbox(self):
        if self._outbox is None:
            from . import assistant_runtime_outbox as outbox
            self._outbox = outbox
        return self._outbox

    async def _check_signals(self, result):
        """Bound each cycle to one event and one due plan, in separate Sessions.

        The existing outbox owns reauthorization, fact reads, deduplication and
        short write transactions. A failed/deferred check must not starve an
        already queued employee Run, and never authorizes a business command.
        Notifications have their own switch even when Run execution is off.
        """
        checks = []
        followup = settings.assistant_runtime_enabled and settings.assistant_followup_enabled
        if followup or settings.assistant_notifications_enabled:
            checks.append(('dispatch', self.outbox.dispatch_one))
        if followup:
            checks.append(('poll', self.outbox.poll_due_plan))
        for name, check in checks:
            if self._stop.is_set():
                break
            try:
                with self.session_factory() as db:
                    outcome = await check(db, clock=self.clock,
                        read_session_factory=self.read_session_factory)
                if outcome is not None:
                    # Only scheduler status belongs in operational telemetry.
                    result[name] = outcome.state
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                result.setdefault('maintenance_errors', {})[name] = _error_code(exc)
                self._record_failure(result, exc)

    # -- heartbeat and maintenance --------------------------------------------
    def beat_now(self, *, error=None, now=None):
        value = beat(worker_id=self.worker_id, session_factory=self.session_factory,
                     error=error, now=now or _clock_now(self.clock))
        self.last_beat = value['at']
        self.last_error = value['error']
        return value

    def _heartbeat_due(self, now):
        if self.last_beat is None:
            return True
        try:
            previous = datetime.fromisoformat(self.last_beat)
        except (TypeError, ValueError):
            return True
        return (now - previous).total_seconds() >= self.heartbeat_seconds

    def _maintain(self, *, now):
        """Own-prefix cleanup and the periodic heartbeat; never another key."""
        if (self._last_cleanup is None or
                (now - self._last_cleanup).total_seconds() >= self.cleanup_seconds):
            try:
                beat_cleanup(session_factory=self.session_factory, now=now, keep=self.worker_id)
            except Exception as exc:
                self.last_error = _error_code(exc)
            self._last_cleanup = now
        if self._heartbeat_due(now):
            try:
                self.beat_now(now=now)
            except Exception as exc:
                self.last_error = _error_code(exc)

    async def _beat_loop(self):
        """Keep the heartbeat alive while one long execution is being driven."""
        while not self._stop.is_set():
            await asyncio.sleep(self.heartbeat_seconds)
            if self._stop.is_set():
                return
            now = _clock_now(self.clock)
            if self._heartbeat_due(now):
                try:
                    self.beat_now(now=now)
                except Exception as exc:
                    self.last_error = _error_code(exc)

    # -- one cycle ------------------------------------------------------------
    def _recover(self):
        """Recover at most one expired claim in its own fresh Session."""
        with self.session_factory() as db:
            return self.queue.reclaim_expired(db, clock=self.clock,
                                              read_session_factory=self.read_session_factory)

    def _claim(self):
        """Claim at most one globally eligible Run; no claim when disabled."""
        with self.session_factory() as db:
            return self.queue.claim_next(db, self.lease_owner, clock=self.clock,
                                         read_session_factory=self.read_session_factory)

    async def _execute(self, principal):
        with self.session_factory() as db:
            outcome = await self.runner(db, principal, self.config, stream=False)
        return getattr(outcome, 'status', None)

    def _record_failure(self, result, exc):
        result['error'] = _error_code(exc)
        self.last_error = result['error']
        try:
            self.beat_now(error=result['error'])
        except Exception:
            pass
        return result

    async def tick(self):
        """One maintenance cycle: at most one execution slot, never two Runs."""
        self.cycles += 1
        now = _clock_now(self.clock)
        self._maintain(now=now)
        result = {'cycle': self.cycles, 'at': _iso(now), 'worker': self.worker_id,
                  'state': self.state, 'claimed': False, 'run_id': None, 'status': None,
                  'reason': None, 'error': None}
        if self._stop.is_set():
            result['reason'] = 'stopping'
            return result
        await self._check_signals(result)
        if not settings.assistant_runtime_enabled:
            result['reason'] = 'runtime_disabled'
            return result
        if self._stop.is_set():
            result['reason'] = 'stopping'
            return result
        try:
            recovered = self._recover()
            if recovered is not None:
                result['recovered'] = recovered.id
        except Exception as exc:
            return self._record_failure(result, exc)
        if self._stop.is_set():
            result['reason'] = 'stopping'
            return result
        try:
            principal = self._claim()
        except Exception as exc:
            return self._record_failure(result, exc)
        if principal is None:
            result['reason'] = 'idle'
            return result
        result['claimed'] = True
        result['run_id'] = principal.run_id
        try:
            result['status'] = await self._execute(principal)
        except asyncio.CancelledError:
            # Shutdown never enters a business POST: the reviewed runner saves
            # its own retry/cancel boundary before this propagates.
            self.last_error = 'cancelled'
            raise
        except Exception as exc:
            result['error'] = _error_code(exc)
            self.last_error = result['error']
        self.executed += 1
        try:
            self.beat_now(error=result['error'])
        except Exception:
            pass
        return result

    # -- lifecycle ------------------------------------------------------------
    async def _serve(self, *, once=False):
        loop, task = asyncio.get_running_loop(), asyncio.current_task()
        with self._lifecycle_lock:
            self._owner_loop, self._serve_task = loop, task
            self.state = 'stopping' if self._stop.is_set() else 'running'
            # stop() may time out before this thread has installed its loop.
            if self._cancel_requested:
                loop.call_soon(task.cancel)
        try:
            try:
                self._maintain(now=_clock_now(self.clock))
            except Exception as exc:
                self.last_error = _error_code(exc)
            self._beater = asyncio.ensure_future(self._beat_loop())
            while not self._stop.is_set():
                began = asyncio.get_running_loop().time()
                result = None
                try:
                    result = await self.tick()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.last_error = _error_code(exc)
                if once:
                    break
                spent = asyncio.get_running_loop().time() - began
                # A cycle consumes only one event/plan/Run. Drain committed
                # backlog without imposing five seconds per item; due timestamps
                # already enforce each source's retry and polling backoff.
                progress = result and not result.get('error') and (
                    result.get('claimed') or result.get('recovered')
                    or result.get('dispatch') in {'dispatched', 'pending'}
                    or result.get('poll') in {'checked', 'invalidated', 'deferred'})
                if progress:
                    await asyncio.sleep(0)  # Give Web, heartbeats and stop a turn.
                if await self._pause(0.0 if progress else max(0.0, self.check_seconds - spent)):
                    break
        finally:
            self.state = 'stopping'
            if self._beater is not None:
                self._beater.cancel()
                try:
                    await self._beater
                except BaseException:
                    pass
                self._beater = None
            try:
                self.beat_now(error=self.last_error)
            except Exception:
                pass
            with self._lifecycle_lock:
                if self._serve_task is task:
                    self._owner_loop, self._serve_task = None, None
                # Embedded completion is published only after thread.join().
                if self._thread is None:
                    self.state = 'stopped'

    async def _pause(self, seconds):
        """Wait up to ``seconds``; True as soon as a stop was requested."""
        deadline = asyncio.get_running_loop().time() + seconds
        while not self._stop.is_set():
            if asyncio.get_running_loop().time() >= deadline:
                return False
            await asyncio.sleep(min(0.25, max(0.0, deadline - asyncio.get_running_loop().time())))
        return True

    def start(self, *, once=False):
        """Run the embedded worker off the Web loop; never share a Session."""
        loop = asyncio.get_running_loop()
        with self._lifecycle_lock:
            if (self._thread is not None and self._thread.is_alive()
                    or self._task is not None and not self._task.done()
                    or self.state != 'stopped'):
                return self
            self._stop.clear()
            self._cancel_requested = False
            self._thread_error = None
            self.state = 'running'
            thread = threading.Thread(target=self._run_embedded, kwargs={'once': once},
                                      name='assistant-runtime-' + self.worker_id)
            self._thread = thread
            try:
                thread.start()
            except BaseException:
                self._thread = None
                self.state = 'stopped'
                raise
            self._task = loop.create_task(self._join_embedded(thread))
        return self

    def _run_embedded(self, *, once=False):
        """Create and close the entire worker loop inside its owning thread."""
        try:
            self.run(once=once)
        except BaseException as exc:
            # Do not let a thread traceback expose database arguments. stop()
            # observes the original failure after the real thread has ended.
            with self._lifecycle_lock:
                self._thread_error = exc

    async def _join_embedded(self, thread):
        await asyncio.to_thread(thread.join)
        with self._lifecycle_lock:
            if self._thread is thread:
                self.state = 'stopped'

    async def stop(self, *, timeout=60.0):
        """Stop claiming, then cancel on the owner loop only after the timeout.

        The join proxy is never cancelled instead of the actual worker. Even
        after forced cancellation, wait for its loop and Sessions to close.
        """
        self._stop.set()
        with self._lifecycle_lock:
            if self.state == 'running':
                self.state = 'stopping'
            thread = self._thread
            if thread is None:
                if self._serve_task is None:
                    self.state = 'stopped'
                return self.state
        await asyncio.to_thread(thread.join, max(0.0, timeout))
        if thread.is_alive():
            with self._lifecycle_lock:
                cancel = not self._cancel_requested
                self._cancel_requested = True
                loop, task = self._owner_loop, self._serve_task
            if cancel and loop is not None and task is not None:
                try:
                    loop.call_soon_threadsafe(task.cancel)
                except RuntimeError:
                    # The owner loop may already be closing; join still proves
                    # actual completion, never the cancellation of a proxy.
                    pass
            await asyncio.to_thread(thread.join)
        with self._lifecycle_lock:
            if self._thread is thread:
                error = self._thread_error
                self._thread_error = None
                self._thread = None
                self._task = None
                self.state = 'stopped'
            else:
                error = None
        if error is not None and not isinstance(error, asyncio.CancelledError):
            raise error
        return self.state

    def run(self, *, once=False):
        """Blocking entry point for the standalone process."""
        asyncio.run(self._serve(once=once))

    def stop_signal(self):
        """Safe to call from a signal handler: only sets the stop flag."""
        self._stop.set()


def _install_signals(worker, loop_signals=('SIGINT', 'SIGTERM')):
    installed = []
    for name in loop_signals:
        number = getattr(signal, name, None)
        if number is None:
            continue
        try:
            signal.signal(number, lambda *_: worker.stop_signal())
        except (ValueError, OSError):
            continue
        installed.append(name)
    return installed


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='huakangos 业务助手 Runtime worker（单执行槽；不执行任何业务提交）')
    parser.add_argument('--once', action='store_true', help='只执行一个周期后退出')
    parser.add_argument('--health', action='store_true', help='只读输出健康信息，不领取执行')
    parser.add_argument('--worker-id', default=None, help='固定本进程的32位十六进制worker编号')
    parser.add_argument('--lease-owner', default=None, help='固定租约持有者编号（排障用）')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    if args.health:
        report = health_report()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['healthy'] else 1
    try:
        state = _startup_check()
    except WorkerError as exc:
        print(json.dumps({'status': 'refused', 'code': exc.code}, ensure_ascii=False))
        return 2
    worker = Worker(worker_id=args.worker_id, lease_owner=args.lease_owner)
    _install_signals(worker)
    log.info('Assistant runtime worker %s starting: revision=%s source=%s',
             worker.worker_id, state['revision'], state['source'])
    try:
        worker.run(once=args.once)
    except KeyboardInterrupt:
        worker.stop_signal()
    log.info('Assistant runtime worker %s stopped: cycles=%s executed=%s last_error=%s',
             worker.worker_id, worker.cycles, worker.executed, worker.last_error)
    return 0


def _startup_check():
    report = verify_instance()
    if not settings.assistant_runtime_enabled:
        log.warning('Assistant runtime is disabled; the worker will not claim work')
    return report


if __name__ == '__main__':
    raise SystemExit(main())
