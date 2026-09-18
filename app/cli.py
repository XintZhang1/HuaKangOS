"""Run from project root: python -m app.cli --help"""
import argparse
from datetime import datetime, date
from getpass import getpass
import os
from pathlib import Path
import re
import sqlite3
from sqlalchemy import select, func
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config
from .config import ROOT, settings
from .db import SessionLocal, engine
from .models import User, MODULES, Store
from .security import hash_password


def migrate(url=None):
    cfg = Config(str(ROOT/'alembic.ini'))
    if url: cfg.attributes['url_override']=url
    command.upgrade(cfg,'head')


def initialize(args):
    migrate()
    if settings.database_url.startswith('sqlite'):
        path = make_url(settings.database_url).database
        with sqlite3.connect(path) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
    with SessionLocal() as db:
        if not db.get(Store,1):
            db.add(Store(id=1,code='MAIN',name='默认门店')); db.commit()
        if db.scalar(select(func.count()).select_from(User)):
            if args.demo:
                raise SystemExit('已存在用户：不会追加演示数据。请为演示环境使用全新独立数据库。')
            print('数据库已初始化，保留现有数据与账号。'); return
        username = args.admin_user.lower()
        if not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}',username): raise SystemExit('管理员用户名格式无效')
        password = os.getenv('DEALER_INITIAL_PASSWORD')
        if not password:
            password=getpass('请设置管理员密码（至少12位，不回显）: ')
            if password != getpass('再次输入密码: '): raise SystemExit('两次密码不一致')
        user=User(username=username,display_name='门店管理员',role='admin',password_hash=hash_password(password),must_change_password=False)
        db.add(user); db.commit()
        if args.demo:
            from .seed import seed_demo
            seed_demo(db,user)
            print('已创建独立的虚构演示数据；正式经营请使用新的空数据库。')
        print(f'初始化完成，管理员账号：{username}。密码不会写入源码或日志。')


def backup(output):
    if not settings.database_url.startswith('sqlite'):
        raise SystemExit('此命令用于SQLite在线备份。PostgreSQL请使用 pg_dump，并验证恢复。')
    source=Path(make_url(settings.database_url).database).resolve()
    if not source.exists(): raise SystemExit('数据库不存在')
    target=Path(output).resolve() if output else ROOT/'backups'/f'dealer-{datetime.now():%Y%m%d-%H%M%S}.sqlite'
    if target.exists(): raise SystemExit('目标文件已存在，拒绝覆盖')
    target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(f'file:{source.as_posix()}?mode=ro',uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise SystemExit('备份完整性检查失败')
    try: target.chmod(0o600)
    except OSError: pass
    print(f'已完成一致性备份：{target}。该文件包含敏感数据，请加密和限制访问。')


def main():
    parser=argparse.ArgumentParser(description='DealerDesk 本地管理工具')
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init',help='迁移数据库并交互创建第一个管理员')
    init.add_argument('--admin-user',default='admin'); init.add_argument('--demo',action='store_true')
    sub.add_parser('migrate',help='应用版本化数据库迁移')
    bak=sub.add_parser('backup',help='SQLite一致性在线备份'); bak.add_argument('--output')
    report=sub.add_parser('report',help='立即生成指定业务日的日报')
    report.add_argument('--store-id',type=int,default=1); report.add_argument('--date',required=True); report.add_argument('--ai',action='store_true'); report.add_argument('--retry-ai',action='store_true')
    sub.add_parser('check',help='检查数据库与配置，不显示密钥')
    args=parser.parse_args()
    if args.command=='init': initialize(args)
    elif args.command=='migrate': migrate(); print('数据库迁移完成')
    elif args.command=='backup': backup(args.output)
    elif args.command=='report':
        from .reports import generate_report
        from .schemas import ReportInput
        with SessionLocal() as db:
            store=db.get(Store,args.store_id)
            if not store or not store.active: raise SystemExit('门店不存在或已停用')
        req=ReportInput(business_date=date.fromisoformat(args.date),use_ai=args.ai,retry_ai=args.retry_ai)
        print('日报 ID:',generate_report(req.business_date,req.use_ai,req.retry_ai,store_id=args.store_id))
    elif args.command=='check':
        with SessionLocal() as db:
            print('账号数:',db.scalar(select(func.count()).select_from(User)))
            print('业务记录:',{m:db.scalar(select(func.count()).select_from(model)) for m,model in MODULES.items()})
        print('外发AI允许:',settings.allow_ai,'密钥已配置:',bool(settings.deepseek_key),'模型:',settings.deepseek_model)
        print('定时日报:',settings.scheduler_enabled,settings.timezone,f'{settings.report_hour:02}:{settings.report_minute:02}')

if __name__=='__main__': main()
