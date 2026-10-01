from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from fastapi import Depends
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import ROOT, settings


def utcnow() -> datetime:
    # Database timestamps are UTC-naive; API explicitly serializes them with Z.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    args = {'check_same_thread': False, 'timeout': 30} if url.startswith('sqlite') else {}
    options = {'isolation_level': 'REPEATABLE READ'} if url.startswith('postgresql') else {}
    engine = create_engine(url, connect_args=args, pool_pre_ping=True, **options)
    if url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def sqlite_setup(conn, _):
            conn.isolation_level = None
            cursor = conn.cursor()
            cursor.execute('PRAGMA foreign_keys=ON')
            cursor.execute('PRAGMA busy_timeout=30000')
            cursor.close()
        @event.listens_for(engine, 'begin')
        def sqlite_begin(connection):
            # Only a server-owned short write transaction may reserve the WAL
            # writer before reading. Ordinary business/read transactions keep
            # their established BEGIN and version guards.
            immediate = connection.get_execution_options().get('huakangos_sqlite_write_transaction') is True
            connection.exec_driver_sql('BEGIN IMMEDIATE' if immediate else 'BEGIN')
    return engine


(ROOT / 'data').mkdir(exist_ok=True)
engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        try:
            yield db
        finally:
            db.rollback()


def get_write_db(db=Depends(get_db)):
    """Reserve SQLite's writer before a writing endpoint's auth/read snapshot.

    This includes reports that append one audit in their read transaction.
    A deferred WAL reader cannot promote after a concurrent writer commits.
    This explicit dependency starts before get_user and shares its get_db
    session; no read or audit write is retried. Other reads keep get_db.
    """
    if db.get_bind().dialect.name == 'sqlite':
        db.connection(execution_options={'huakangos_sqlite_write_transaction': True})
    return db


get_audited_read_db = get_write_db
