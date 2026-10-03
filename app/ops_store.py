"""Durable operations workflow, separate from every business database.

Only the deployment CLI initializes this database. Web requests cannot create it.
No model messages, reasoning, credentials, or business records are stored here.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def stamp():
    return datetime.now(timezone.utc).isoformat()


class OpsStore:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_absolute() or not self.path.is_file() or self.path.is_symlink():
            raise RuntimeError('Operations storage is not initialized')

    @staticmethod
    def initialize(path):
        path = Path(path)
        if not path.is_absolute() or path.exists():
            raise RuntimeError('Choose a new absolute operations database path')
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE jobs (
                    id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL, store_id INTEGER NOT NULL,
                    request_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
                    title TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
                    route TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'received',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    lease_token TEXT, lease_until REAL, attempts INTEGER NOT NULL DEFAULT 0,
                    release_id TEXT, report TEXT, mail TEXT, error_code TEXT,
                    UNIQUE(owner_id, store_id, request_id)
                );
                CREATE INDEX jobs_queue ON jobs(status, created_at);
                CREATE TABLE events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(id),
                    kind TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
                    release_id TEXT NOT NULL, verdict TEXT NOT NULL, summary TEXT NOT NULL,
                    pr_url TEXT NOT NULL, created_at TEXT NOT NULL
                );
                PRAGMA user_version=1;
            ''')
        path.chmod(0o600)

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            if db.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise RuntimeError('Unsupported operations database schema')
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        finally:
            db.close()

    @staticmethod
    def event(db, job_id, kind, detail):
        db.execute('INSERT INTO events(job_id,kind,detail,created_at) VALUES (?,?,?,?)',
                   (job_id, kind, encoded(detail), stamp()))

    def submit(self, *, owner_id, store_id, title, description, category, request_id, route):
        request_id = str(uuid.UUID(request_id))
        if owner_id < 1 or store_id < 1 or category not in {'bug', 'improvement', 'feature'}:
            raise ValueError('Invalid feedback')
        payload = dict(title=title, description=description, category=category, route=route)
        digest = hashlib.sha256(encoded(payload).encode()).hexdigest()
        with self.connect(True) as db:
            row = db.execute('SELECT * FROM jobs WHERE owner_id=? AND store_id=? AND request_id=?',
                             (owner_id, store_id, request_id)).fetchone()
            if row:
                if row['payload_hash'] != digest:
                    raise ValueError('Request identifier belongs to different feedback')
                return dict(id=row['id'], created_at=row['created_at'], status=row['status'], duplicate=True)
            job_id, now = str(uuid.uuid4()), stamp()
            db.execute('''INSERT INTO jobs(id,owner_id,store_id,request_id,payload_hash,title,
                          description,category,route,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                       (job_id, owner_id, store_id, request_id, digest, title, description, category, route, now, now))
            self.event(db, job_id, 'received', {'consent_analysis': True})
            return dict(id=job_id, created_at=now, status='received', duplicate=False)

    def receipts(self, *, owner_id, store_id, limit=20):
        with self.connect() as db:
            return [dict(r) for r in db.execute('''SELECT id,title,created_at,status FROM jobs
                WHERE owner_id=? AND store_id=? ORDER BY created_at DESC,id LIMIT ?''',
                (owner_id, store_id, max(1, min(limit, 50))))]

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                raise ValueError('Unknown job')
            result = dict(row)
            for field in ('report', 'mail'):
                result[field] = json.loads(result[field]) if result[field] else None
            # Leases and employee identifiers are not part of the MCP review contract.
            for field in ('lease_token', 'request_id', 'payload_hash', 'owner_id', 'store_id'):
                result.pop(field, None)
            result['events'] = [dict(r) for r in db.execute('''SELECT seq,kind,detail,created_at FROM events
                WHERE job_id=? ORDER BY seq DESC LIMIT 30''', (job_id,))]
            return result

    def list_jobs(self, limit=20):
        with self.connect() as db:
            return [dict(r) for r in db.execute('''SELECT id,title,status,release_id,created_at,updated_at
                FROM jobs ORDER BY created_at DESC,id LIMIT ?''', (max(1, min(limit, 50)),))]

    def claim(self, release_id, lease_seconds=900):
        now = time.time()
        with self.connect(True) as db:
            expired = db.execute("SELECT id FROM jobs WHERE status='analyzing' AND lease_until<? AND attempts>=3", (now,)).fetchall()
            for row in expired:
                db.execute("UPDATE jobs SET status='needs_attention',error_code='analysis_attempts_exhausted',updated_at=? WHERE id=?", (stamp(), row['id']))
                self.event(db, row['id'], 'needs_attention', {'reason': 'analysis_attempts_exhausted'})
            # BEGIN IMMEDIATE makes this shared slot check and the claim atomic
            # across worker instances, including after a process restart.
            if db.execute("SELECT 1 FROM jobs WHERE status='analyzing' AND lease_until>=? LIMIT 1", (now,)).fetchone():
                return None
            row = db.execute("""SELECT * FROM jobs WHERE status='received' OR
                (status='analyzing' AND lease_until<? AND attempts<3)
                ORDER BY created_at,id LIMIT 1""", (now,)).fetchone()
            if row is None:
                return None
            token = str(uuid.uuid4())
            # A retry is bound to its original source release; do not silently rebase evidence.
            if row['release_id'] and row['release_id'] != release_id:
                db.execute("UPDATE jobs SET status='needs_attention',error_code='source_release_changed',updated_at=? WHERE id=?", (stamp(), row['id']))
                self.event(db, row['id'], 'needs_attention', {'reason': 'source_release_changed'})
                return None
            db.execute("""UPDATE jobs SET status='analyzing',lease_token=?,lease_until=?,
                attempts=attempts+1,release_id=?,updated_at=? WHERE id=?""",
                (token, now + lease_seconds, release_id, stamp(), row['id']))
            self.event(db, row['id'], 'analyzing', {'release_id': release_id, 'attempt': row['attempts'] + 1})
            return dict(row) | {'lease_token': token, 'release_id': release_id}

    def analysis_result(self, job_id, token, report=None, error=None):
        with self.connect(True) as db:
            status = 'needs_attention' if error else 'review_ready'
            changed = db.execute("""UPDATE jobs SET status=?,report=?,error_code=?,lease_token=NULL,
                lease_until=NULL,updated_at=? WHERE id=? AND status='analyzing' AND lease_token=? AND lease_until>?""",
                (status, encoded(report) if report else None, error, stamp(), job_id, token, time.time())).rowcount
            if changed != 1:
                raise RuntimeError('Analysis lease was lost')
            self.event(db, job_id, status, {'error_code': error} if error else {'release_id': report['release_id']})

    def model_event(self, job_id, token, kind, detail):
        if kind not in {'provider_request', 'provider_usage'}:
            raise ValueError('Invalid model event')
        with self.connect(True) as db:
            row = db.execute("SELECT id FROM jobs WHERE id=? AND status='analyzing' AND lease_token=? AND lease_until>?",
                             (job_id, token, time.time())).fetchone()
            if not row:
                raise RuntimeError('Analysis lease was lost')
            self.event(db, job_id, kind, detail)

    def retry_analysis(self, job_id, expected_error, reason):
        # Explicit reviewer action after a code/config correction, never automatic
        # retry of a mailed proposal or an uncertain external side effect.
        if not isinstance(reason, str) or not 10 <= len(reason) <= 1000:
            raise ValueError('A concrete correction reason is required')
        with self.connect(True) as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if (not row or row['status'] != 'needs_attention' or row['report'] or row['mail']
                    or row['error_code'] != expected_error or row['attempts'] >= 3):
                raise ValueError('Only an unmailed failed analysis may be explicitly retried')
            self.event(db, job_id, 'analysis_retry_requested', {'previous_release_id': row['release_id'],
                'previous_error': expected_error, 'reason': reason, 'actor': 'authenticated_reviewer'})
            db.execute("UPDATE jobs SET status='received',release_id=NULL,error_code=NULL,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                       (stamp(), job_id))
            return {'id': job_id, 'status': 'received'}

    def notification_jobs(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT id,status FROM jobs WHERE status IN ('review_ready','notifying') ORDER BY created_at LIMIT 10")]

    def begin_notification(self, job_id):
        with self.connect(True) as db:
            row = db.execute('SELECT status,report FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row or row['status'] != 'review_ready' or not row['report']:
                return False
            db.execute("UPDATE jobs SET status='notifying',lease_until=?,updated_at=? WHERE id=?", (time.time() + 180, stamp(), job_id))
            self.event(db, job_id, 'notifying', {'event_id': 'huakangos-ops:' + job_id})
            return True

    def notification_result(self, job_id, result):
        result = {key: result[key] for key in ('status', 'event_id', 'provider_message_id', 'error_code', 'reason') if key in result}
        delivery = result.get('status')
        # Provider acceptance proves submission, not arrival or Cutie action.
        status = 'awaiting_cutie' if delivery == 'sent' else 'needs_attention'
        with self.connect(True) as db:
            changed = db.execute("UPDATE jobs SET status=?,mail=?,updated_at=?,lease_until=NULL WHERE id=? AND status='notifying'",
                                 (status, encoded(result), stamp(), job_id)).rowcount
            if changed:
                self.event(db, job_id, status, result)

    def search_memory(self, query, limit=5):
        with self.connect() as db:
            return [dict(r) for r in db.execute('''SELECT * FROM memory
                WHERE instr(summary,?)>0 ORDER BY id DESC LIMIT ?''', (query, max(1, min(limit, 10))))]

    def record_review(self, job_id, verdict, summary, pr_url):
        import re
        if verdict not in {'pr_opened', 'needs_information', 'declined'} or not 5 <= len(summary) <= 4000:
            raise ValueError('Invalid review')
        if verdict == 'pr_opened' and not re.fullmatch(r'https://github\.com/XintZhang1/HuaKangOS/pull/[1-9][0-9]*', pr_url):
            raise ValueError('Expected a HuaKangOS pull request URL')
        if verdict != 'pr_opened' and pr_url:
            raise ValueError('Unexpected pull request URL')
        with self.connect(True) as db:
            row = db.execute('SELECT status,release_id FROM jobs WHERE id=?', (job_id,)).fetchone()
            existing = db.execute('SELECT verdict,summary,pr_url FROM memory WHERE job_id=?', (job_id,)).fetchone()
            if existing:
                if dict(existing) != dict(verdict=verdict, summary=summary, pr_url=pr_url):
                    raise ValueError('Review already recorded; history cannot be overwritten')
                return {'recorded': True, 'duplicate': True}
            if not row or row['status'] != 'awaiting_cutie':
                raise ValueError('Job is not awaiting Cutie')
            db.execute('INSERT INTO memory(job_id,release_id,verdict,summary,pr_url,created_at) VALUES(?,?,?,?,?,?)',
                       (job_id, row['release_id'], verdict, summary, pr_url, stamp()))
            db.execute("UPDATE jobs SET status='reviewed',updated_at=? WHERE id=?", (stamp(), job_id))
            self.event(db, job_id, 'reviewed', {'verdict': verdict, 'pr_url': pr_url, 'source': 'authenticated_cutie_review'})
            return {'recorded': True, 'duplicate': False}
