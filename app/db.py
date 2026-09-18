from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import ROOT, settings


def utcnow() -> datetime:
    # Database timestamps are UTC-naive; API explicitly serializes them with Z.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def start_of_today_utc() -> datetime:
    """UTC-naive instant of 00:00 today in the configured timezone.

    Database timestamps are UTC-naive while today() is timezone-local. Comparing
    them directly silently disables any daily quota between 00:00 and 08:00
    Shanghai, because the local date is then a day ahead of the UTC date.
    """
    midnight = datetime.now(ZoneInfo(settings.timezone)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc).replace(tzinfo=None)


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
            connection.exec_driver_sql('BEGIN')
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
