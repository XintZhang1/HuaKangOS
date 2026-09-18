"""Local trusted release supervisor. Run this, not uvicorn, for automatic maintenance.
The supervisor and its credentials never come from an AI-generated release.
"""
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
import httpx
from sqlalchemy.engine import make_url
from app.config import ROOT, settings
from .config import MaintenanceConfig, GateError, preflight
from .gitops import Repository, SHA, tree_matches


def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)


def absolute_database_url(url):
    parsed=make_url(url)
    if parsed.get_backend_name()=='sqlite' and parsed.database and parsed.database!=':memory:':
        parsed=parsed.set(database=str(Path(parsed.database).resolve()))
    return parsed.render_as_string(hide_password=False)


@contextmanager
def process_lock(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    f=path.open('a+b');f.seek(0);f.write(b'0');f.flush();f.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except (OSError,IOError) as exc:
        f.close();raise GateError('另一个 DealerDesk 启动器正在运行，不能同时运行两个发布器') from exc
    try: yield
    finally: f.close()


def backup_sqlite(database_url,destination):
    url=make_url(database_url)
    if url.get_backend_name()!='sqlite' or not url.database or url.database==':memory:':
        raise GateError('此自动发布器只支持持久化 SQLite；PostgreSQL 发布须先配置专用备份流程')
    source=Path(url.database)
    if not source.is_file(): raise GateError('找不到现有业务数据库，拒绝创建空库并发布')
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Source is read-only. SQLite backup API includes committed WAL state.
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=30) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise GateError('发布前数据库备份一致性检查失败')
    return str(destination)


class AppProcess:
    def __init__(self,host,port,cfg):
        self.host=host;self.port=port;self.cfg=cfg;self.process=None
    def start(self,release):
        if self.process is not None and self.process.poll() is None: raise GateError('旧服务尚未停止，拒绝启动第二个写库进程')
        env=os.environ.copy()
        env['DATABASE_URL']=absolute_database_url(settings.database_url)
        env['DEALER_DEPLOYMENT_GATE']=str(self.cfg.runtime/'switching.lock')
        env['DEALER_RELEASE_SHA']=release['sha'];env['MAINT_RUNTIME_DIR']=str(self.cfg.runtime)
        env['PYTHONPATH']=str(Path(release['path']).resolve())
        # Business service has no need for code-push credentials or Feishu secrets.
        for key in list(env):
            if key.startswith(('FEISHU_','DEEPSEEK_CODE_','MAINT_REPO_')): env.pop(key,None)
        self.process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host',self.host,
            '--port',str(self.port),'--workers','1'],cwd=release['path'],env=env,stdin=subprocess.DEVNULL)
    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.kill();self.process.wait(timeout=10)
        self.process=None
    def healthy(self,sha,timeout=25):
        deadline=time.monotonic()+timeout
        host='127.0.0.1' if self.host=='0.0.0.0' else ('[::1]' if self.host in {'::','::1'} else self.host)
        with httpx.Client(timeout=2,trust_env=False) as client:
            while time.monotonic()<deadline:
                if self.process is None or self.process.poll() is not None: return False
                try:
                    r=client.get(f'http://{host}:{self.port}/api/health')
                    data=r.json()
                    if r.status_code==200 and data.get('status')=='ok' and data.get('release')==sha: return True
                except (httpx.HTTPError,ValueError): pass
                time.sleep(.4)
        return False


class Supervisor:
    def __init__(self,cfg,app,repo=None,root=ROOT,backup=backup_sqlite):
        self.cfg=cfg;self.app=app;self.repo=repo;self.root=Path(root).resolve();self.backup=backup
        self.cfg.runtime.mkdir(parents=True,exist_ok=True)
        self.pointer=self.cfg.runtime/'active.json';self.gate=self.cfg.runtime/'switching.lock'
        self.worker_process=None;self.ready=False;self.message='自动维护未启用';self.worker_restart_after=0
        self.active={'sha':'local','path':str(self.root)}

    def status(self,message=None):
        if message is not None: self.message=message
        atomic_json(self.cfg.runtime/'status.json',{'enabled':self.cfg.enabled,'ready':self.ready,
            'paused':(self.cfg.runtime/'PAUSED').exists(),'message':self.message,'release':self.active['sha'],
            'worker_running':bool(self.worker_process and self.worker_process.poll() is None),'updated_at':time.time()})

    def safe_release(self,data):
        path=Path(data['path']).resolve();releases=(self.cfg.runtime/'releases').resolve()
        if path!=self.root and not path.is_relative_to(releases): raise GateError('运行版本指针越界，拒绝加载')
        if not path.is_dir() or not (data['sha']=='local' or SHA.fullmatch(data['sha'])): raise GateError('运行版本指针无效')
        return {'sha':data['sha'],'path':str(path)}

    def bootstrap(self):
        if self.pointer.exists():
            try: self.active=self.safe_release(json.loads(self.pointer.read_text(encoding='utf-8')))
            except (OSError,ValueError,KeyError,TypeError) as exc: raise GateError('无法读取已保存的运行版本；不会猜测并覆盖') from exc
        if self.cfg.enabled:
            try:
                self.cfg.validate();preflight(self.cfg)
                if make_url(settings.database_url).get_backend_name()!='sqlite': raise GateError('自动发布暂只支持 SQLite 备份与回滚')
                self.repo=self.repo or Repository(self.cfg)
                base=self.repo.sync()
                if self.active['sha']=='local':
                    if not tree_matches(self.repo,base,self.root): raise GateError('请先将这份完整代码提交到专用仓库；当前源码与远程主分支不同')
                    self.active={'sha':base,'path':str(self.root)}
                if not tree_matches(self.repo,self.active['sha'],Path(self.active['path'])): raise GateError('已部署代码被手工修改，自动维护暂停')
                self.ready=True;self.message='等待意见；AI 候选仅在测试及指定审批后发布'
            except GateError as exc: self.ready=False;self.message=str(exc)
        atomic_json(self.pointer,self.active)
        self.recover_interrupted()
        self.status()
        self.app.start(self.active)
        if not self.app.healthy(self.active['sha']): self.app.stop();raise GateError('业务服务未通过启动检查，请查看终端错误；没有切换到未知版本')
        # After crash recovery, keep PAUSED but let users work on the known version.
        self.gate.unlink(missing_ok=True)

    def recover_interrupted(self):
        from app.db import SessionLocal
        from app.models import Feedback, Deployment
        from sqlalchemy import select
        from .decisions import event
        with SessionLocal() as db:
            rows=list(db.scalars(select(Deployment).where(Deployment.status.in_(['switching','rollback_switching']))))
            for dep in rows:
                # The saved previous code is trusted; do NOT restore the database.
                self.active=self.safe_release({'sha':dep.previous_sha,'path':dep.previous_path})
                atomic_json(self.pointer,self.active)
                dep.status='failed';dep.error='发布进程中断，恢复先前代码并暂停自动维护；需要核对 Git 主分支与运行版本'
                row=db.get(Feedback,dep.feedback_id);row.status='failed';row.last_error=dep.error;row.notification_sent=False
                event(db,row.id,'crash_recovery',detail=dep.error)
                (self.cfg.runtime/'PAUSED').write_text(dep.error,encoding='utf-8')
            db.commit()

    def approved(self,row,expected):
        from app.db import utcnow
        if row.status!=expected or row.approved_by not in self.cfg.approvers or row.approved_sha!=row.head_sha:
            raise GateError('没有匹配此版本的有效人工审批')
        if not row.approved_at or row.approved_at<utcnow()-timedelta(hours=self.cfg.approval_hours):
            raise GateError('已批准任务超过发布有效期；须重新测试审批')
        if not row.test_result.get('passed') or row.test_result.get('head_sha')!=row.head_sha:
            raise GateError('测试通过记录与批准提交不一致')

    def deploy(self,job_id):
        from app.db import SessionLocal, utcnow
        from app.models import Feedback, Deployment
        from .decisions import event
        from .worker import transition
        from sqlalchemy import select
        previous=dict(self.active);candidate=None;published=False;switched=False
        try:
            with SessionLocal() as db:
                row=db.get(Feedback,job_id);self.approved(row,'approved')
                if row.base_sha!=previous['sha']: raise GateError('运行基线已改变，原审批失效')
                base,head,branch=row.base_sha,row.head_sha,row.branch
            self.repo.sync();self.repo.verify_candidate(base,head)
            if self.repo.remote_head(self.cfg.base_branch)!=base or self.repo.remote_head(branch)!=head:
                raise GateError('远程分支已改变，不发布旧审批；请重新生成候选')
            if not tree_matches(self.repo,base,Path(previous['path'])): raise GateError('当前运行目录被手工修改，拒绝覆盖')
            target=self.cfg.runtime/'releases'/f'{head}-{uuid.uuid4().hex[:8]}'
            self.repo.export(head,target)
            candidate={'sha':head,'path':str(target)}
            with SessionLocal() as db:
                row=db.get(Feedback,job_id);self.approved(row,'approved')
                dep=db.scalar(select(Deployment).where(Deployment.feedback_id==job_id))
                if dep is None: dep=Deployment(feedback_id=job_id);db.add(dep)
                elif dep.status not in {'failed','rolled_back'}: raise GateError('此任务已经发布或正在发布，不能覆盖发布记录')
                dep.sha=head;dep.previous_sha=previous['sha'];dep.previous_path=previous['path'];dep.release_path=str(target);dep.status='switching';dep.error='';dep.backup_path=''
                row.status='deploying';event(db,job_id,'deploying',detail=head);db.commit()
            self.gate.write_text('Release switch in progress; business API temporarily read-disabled.',encoding='utf-8')
            self.app.stop();switched=True
            backup=self.backup(absolute_database_url(settings.database_url),self.cfg.runtime/'backups'/f'pre-{job_id}-{head[:12]}.sqlite')
            with SessionLocal() as db:
                dep=db.scalar(select(Deployment).where(Deployment.feedback_id==job_id));dep.backup_path=backup;db.commit()
            self.app.start(candidate)
            if not self.app.healthy(head): raise GateError('新版健康检查失败，已请求恢复旧版本')
            # Users are still gated. Remote main changes only after health succeeds.
            self.repo.publish(base,head,branch);published=True
            self.active=candidate;atomic_json(self.pointer,candidate)
            with SessionLocal() as db:
                dep=db.scalar(select(Deployment).where(Deployment.feedback_id==job_id));dep.status='deployed'
                row=db.get(Feedback,job_id);row.status='deployed';row.updated_at=utcnow();row.last_error='';row.notification_sent=False
                event(db,job_id,'deployed',detail=f'{head}; database not migrated');db.commit()
            self.gate.unlink(missing_ok=True)
            self.status('新版发布成功；飞书卡片提供回滚到上一代码版本')
        except Exception as exc:
            message=str(exc) if isinstance(exc,GateError) else '发布过程失败，自动维护暂停等待核对；未回退业务数据'
            if switched:
                self.app.stop();self.active=previous;atomic_json(self.pointer,previous)
                self.app.start(previous)
                if self.app.healthy(previous['sha']): self.gate.unlink(missing_ok=True)
                else: message+='；旧服务也未通过健康检查，保持维护门禁'
            # A network failure after git push may have an ambiguous result.
            # Pause rather than assume the remote was unchanged or force-reset it.
            if published or switched:
                (self.cfg.runtime/'PAUSED').write_text(message,encoding='utf-8')
            with SessionLocal() as db:
                dep=db.scalar(select(Deployment).where(Deployment.feedback_id==job_id))
                if dep: dep.status='failed';dep.error=message[:500]
                db.commit()
            transition(job_id,'failed',message)
            self.status(message)

    def rollback(self,job_id):
        from app.db import SessionLocal, utcnow
        from app.models import Feedback, Deployment
        from .decisions import event
        from .worker import transition
        from sqlalchemy import select
        current=dict(self.active);switched=False;target=None
        try:
            with SessionLocal() as db:
                row=db.get(Feedback,job_id);self.approved(row,'rollback_requested')
                dep=db.scalar(select(Deployment).where(Deployment.feedback_id==job_id))
                if not dep or dep.status!='deployed' or dep.sha!=current['sha']: raise GateError('只能回滚当前正在运行的最新版本，不能使用历史卡片')
                head,base=row.head_sha,row.base_sha
                target=self.safe_release({'sha':dep.previous_sha,'path':dep.previous_path})
                dep.status='rollback_switching';db.commit()
            self.repo.sync()
            if self.repo.remote_head(self.cfg.base_branch)!=head: raise GateError('主分支已有其他修改，停止旧版本回滚')
            if not tree_matches(self.repo,base,Path(target['path'])): raise GateError('先前版本目录发生变化，拒绝回滚')
            self.gate.write_text('Rollback in progress',encoding='utf-8');self.app.stop();switched=True
            self.backup(absolute_database_url(settings.database_url),self.cfg.runtime/'backups'/f'rollback-{job_id}-{uuid.uuid4().hex[:8]}.sqlite')
            self.app.start(target)
            if not self.app.healthy(target['sha']): raise GateError('旧版本健康检查失败，保留当前版本')
            reverted=self.repo.revert_published(base,head,job_id)
            # The code tree is exactly the old tree, Git history has a new revert commit.
            target['sha']=reverted;self.app.stop();self.app.start(target)
            if not self.app.healthy(reverted): raise GateError('回滚版本重新启动失败，请核对服务')
            self.active=target;atomic_json(self.pointer,target)
            with SessionLocal() as db:
                dep=db.scalar(select(Deployment).where(Deployment.feedback_id==job_id));dep.status='rolled_back'
                row=db.get(Feedback,job_id);row.status='rolled_back';row.notification_sent=False;row.last_error='';row.updated_at=utcnow()
                event(db,job_id,'rolled_back',detail=f'Git revert {reverted}; retained current business database');db.commit()
            self.gate.unlink(missing_ok=True);self.status('已回滚代码；期间新增的业务记录仍然保留')
        except Exception as exc:
            message=str(exc) if isinstance(exc,GateError) else '回滚中断，请核对运行版本与 Git；未恢复旧数据库'
            if switched:
                self.app.stop();self.active=current;atomic_json(self.pointer,current);self.app.start(current)
                if self.app.healthy(current['sha']): self.gate.unlink(missing_ok=True)
            (self.cfg.runtime/'PAUSED').write_text(message,encoding='utf-8')
            with SessionLocal() as db:
                dep=db.scalar(select(Deployment).where(Deployment.feedback_id==job_id))
                if dep: dep.status='deployed';dep.error=message[:500]
                db.commit()
            transition(job_id,'deployed',message);self.status(message)

    def tick(self):
        from app.db import SessionLocal
        from app.models import Feedback
        from sqlalchemy import select
        if self.ready and not (self.cfg.runtime/'PAUSED').exists():
            with SessionLocal() as db:
                row=db.scalar(select(Feedback).where(Feedback.status.in_(['approved','rollback_requested'])).order_by(Feedback.id).limit(1))
                work=(row.id,row.status) if row else None
            if work:
                if work[1]=='approved': self.deploy(work[0])
                else: self.rollback(work[0])
        if self.ready and (not self.worker_process or self.worker_process.poll() is not None) and time.monotonic()>=self.worker_restart_after:
            self.worker_restart_after=time.monotonic()+60
            env=os.environ.copy();env['DATABASE_URL']=absolute_database_url(settings.database_url)
            env['MAINT_RUNTIME_DIR']=str(self.cfg.runtime);env['PYTHONPATH']=str(self.root)
            self.worker_process=subprocess.Popen([sys.executable,'-m','maintenance.worker'],cwd=self.root,env=env,stdin=subprocess.DEVNULL)
        self.status()

    def stop(self):
        if self.worker_process and self.worker_process.poll() is None:
            self.worker_process.terminate()
            try: self.worker_process.wait(timeout=10)
            except subprocess.TimeoutExpired: self.worker_process.kill();self.worker_process.wait(timeout=5)
        self.app.stop()


def main():
    parser=argparse.ArgumentParser(description='DealerDesk trusted local supervisor')
    parser.add_argument('--host',default=os.getenv('BIND_HOST','127.0.0.1'))
    parser.add_argument('--port',type=int,default=int(os.getenv('PORT','8000')))
    args=parser.parse_args();cfg=MaintenanceConfig()
    os.chdir(ROOT);os.environ['DATABASE_URL']=absolute_database_url(settings.database_url)
    os.environ['MAINT_RUNTIME_DIR']=str(cfg.runtime)
    stopped=False
    def stop_signal(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGINT,stop_signal)
    if hasattr(signal,'SIGTERM'): signal.signal(signal.SIGTERM,stop_signal)
    controller=Supervisor(cfg,AppProcess(args.host,args.port,cfg))
    try:
        with process_lock(cfg.runtime/'supervisor.lock'):
            controller.bootstrap()
            print('DealerDesk: '+controller.message,flush=True)
            while not stopped:
                if controller.app.process.poll() is not None: raise GateError('业务服务意外退出；停止启动器，避免隐藏反复崩溃')
                controller.tick();time.sleep(2)
    except GateError as exc:
        print('DealerDesk: '+str(exc),file=sys.stderr);return 1
    finally: controller.stop()
    return 0

if __name__=='__main__': raise SystemExit(main())
