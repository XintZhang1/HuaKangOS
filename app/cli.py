"""Run from project root: python -m app.cli --help"""
import argparse
from datetime import datetime, date
from getpass import getpass
import os
from pathlib import Path
import re
import sqlite3
import json
from sqlalchemy import select, func
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config
from .config import ROOT, settings
from .branding import PRODUCT_TITLE
from .db import SessionLocal, engine
from .models import User, MODULES, Store
from .security import hash_password


def migrate(url=None):
    cfg = Config(str(ROOT/'alembic.ini'))
    if url: cfg.attributes['url_override']=url
    command.upgrade(cfg,'head')


def initialize(args):
    if args.demo and settings.environment=='production':
        raise SystemExit('正式环境禁止灌入演示数据，请使用新的独立本地试用库。')
    if args.demo and settings.file_scan_mode=='quarantine':
        raise SystemExit('演示业务需要可用的合成凭据。请明确配置 FILE_SCAN_MODE=structure_only（仅本地虚构试用，未查毒）或可用的 ClamAV 后重试；尚未写入数据。')
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
        password = os.getenv('HUAKANGOS_INITIAL_PASSWORD') or os.getenv('DEALER_INITIAL_PASSWORD')
        if not password:
            password=getpass('请设置管理员密码（至少12位，不回显）: ')
            if password != getpass('再次输入密码: '): raise SystemExit('两次密码不一致')
        user=User(username=username,display_name='门店管理员',role='admin',password_hash=hash_password(password),must_change_password=False)
        db.add(user); db.commit()
        if args.demo:
            from .seed import seed_demo
            seed_demo(db,user)
            from .flow_seed import seed_flow_demo
            seed_flow_demo(db,user)
            print('已创建独立的虚构演示数据；正式经营请使用新的空数据库。')
        print(f'初始化完成，管理员账号：{username}。密码不会写入源码或日志。')


def backup(output):
    if not settings.database_url.startswith('sqlite'):
        raise SystemExit('此命令用于SQLite在线备份。PostgreSQL请使用 pg_dump，并验证恢复。')
    source=Path(make_url(settings.database_url).database).resolve()
    if not source.exists(): raise SystemExit('数据库不存在')
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as check:
        names={r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        private=bool(check.execute('SELECT 1 FROM private_file_objects LIMIT 1').fetchone()) if 'private_file_objects' in names else False
    if private or settings.file_storage_mode=='private_local':
        if not output:raise SystemExit('私有附件须与数据库一同备份；请用 --output 指定仓库外的全新绝对目录')
        from .private_file_backup import create_bundle
        result=create_bundle(source,settings.private_file_root or None,output)
        print('数据库与私有附件完整备份：'+json.dumps(result,ensure_ascii=False));return
    target=Path(output).resolve() if output else ROOT/'backups'/f'huakangos-{datetime.now():%Y%m%d-%H%M%S}.sqlite'
    if target.exists(): raise SystemExit('目标文件已存在，拒绝覆盖')
    target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(f'file:{source.as_posix()}?mode=ro',uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
        from .backup_integrity import validate_sqlite
        try:
            validate_sqlite(dst)
        except ValueError as error:
            raise SystemExit(str(error)+'；已保留目标文件供核查，不可用作已验证备份')
    try: target.chmod(0o600)
    except OSError: pass
    print(f'已完成一致性备份：{target}。该文件包含敏感数据，请加密和限制访问。')


def main():
    parser=argparse.ArgumentParser(description=PRODUCT_TITLE+' 本地管理工具')
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init',help='迁移数据库并交互创建第一个管理员')
    init.add_argument('--admin-user',default='admin'); init.add_argument('--demo',action='store_true')
    sub.add_parser('migrate',help='应用版本化数据库迁移')
    bak=sub.add_parser('backup',help='SQLite一致性在线备份'); bak.add_argument('--output')
    verify=sub.add_parser('verify-backup',help='核对数据库与私有附件完整备份目录');verify.add_argument('bundle')
    restore=sub.add_parser('restore-backup',help='恢复完整备份到全新目录，不切换配置');restore.add_argument('bundle');restore.add_argument('--output',required=True)
    sub.add_parser('files-audit',help='只读列出私有对象未引用文件，不自动删除')
    report=sub.add_parser('report',help='立即生成指定业务日的日报')
    report.add_argument('--store-id',type=int,default=1); report.add_argument('--date',required=True); report.add_argument('--ai',action='store_true'); report.add_argument('--retry-ai',action='store_true')
    sub.add_parser('check',help='检查数据库与配置，不显示密钥')
    args=parser.parse_args()
    if args.command=='init': initialize(args)
    elif args.command=='migrate': migrate(); print('数据库迁移完成')
    elif args.command=='backup': backup(args.output)
    elif args.command=='verify-backup':
        from .private_file_backup import validate_bundle
        print(json.dumps(validate_bundle(args.bundle),ensure_ascii=False))
    elif args.command=='restore-backup':
        from .private_file_backup import restore_bundle
        print(json.dumps(restore_bundle(args.bundle,args.output),ensure_ascii=False))
    elif args.command=='files-audit':
        if not settings.database_url.startswith('sqlite'):raise SystemExit('此只读清单命令目前仅支持SQLite；PostgreSQL对象须核对对应清单')
        from .private_files import audit_orphans
        source=Path(make_url(settings.database_url).database).resolve()
        with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as db:
            print(json.dumps(audit_orphans(db,settings.private_file_root),ensure_ascii=False))
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
        print('附件扫描策略:',settings.file_scan_mode,'附件存储:',settings.file_storage_mode,'日报运行模式:',settings.scheduler_mode)

if __name__=='__main__': main()
