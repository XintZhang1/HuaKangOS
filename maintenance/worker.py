"""Durable, budgeted proposal worker. No approval is inferred from model text."""
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
import json
import logging
import threading
import time
import tempfile
from sqlalchemy import select, func
from app.db import SessionLocal, utcnow
from app.models import Feedback, MaintenanceEvent
from .config import MaintenanceConfig, GateError, preflight
from .decisions import event, issue_token
from .feishu import FeishuBot, approval_card, status_card, listen
from .gitops import Repository, SHA, tree_matches
from .model import propose
from .policy import context_files, apply_proposal
from .sandbox import test_candidate

log=logging.getLogger('dealerdesk.maintenance')
ACTIVE={'proposing','testing','awaiting_approval','approved','deploying','rollback_requested'}
NOTIFY={'awaiting_approval','deployed','failed','manual','rejected','expired','rolled_back','superseded'}


def transition(job_id,status,error='',**values):
    with SessionLocal() as db:
        row=db.get(Feedback,job_id)
        if not row: raise GateError('改进任务不存在')
        row.status=status;row.updated_at=utcnow();row.last_error=error[:500];row.notification_sent=False
        for key,value in values.items(): setattr(row,key,value)
        event(db,job_id,status,detail=error)
        db.commit()


class Worker:
    def __init__(self,cfg,repo=None,bot=None,model=propose,tester=test_candidate):
        self.cfg=cfg;self.repo=repo or Repository(cfg);self.bot=bot or FeishuBot(cfg)
        self.model=model;self.tester=tester;self.last_notify={}

    def recover(self):
        # Only one worker is launched by the locked supervisor. Never repeat a
        # potentially paid model call silently after a process crash.
        with SessionLocal() as db:
            for row in db.scalars(select(Feedback).where(Feedback.status.in_(['proposing','testing']))):
                row.status='failed';row.last_error='处理进程中断；没有发布。管理员可核对后重新排队。';row.notification_sent=False
                event(db,row.id,'interrupted',detail=row.last_error)
            db.commit()

    def active_release(self):
        try:
            data=json.loads((self.cfg.runtime/'active.json').read_text(encoding='utf-8'))
            if not SHA.fullmatch(data['sha']): raise ValueError()
            return data
        except (OSError,KeyError,TypeError,ValueError) as exc:
            raise GateError('当前运行代码尚未绑定专用仓库基线；请完成维护器初始化') from exc

    def process_one(self):
        if (self.cfg.runtime/'PAUSED').exists(): return
        with SessionLocal() as db:
            now=utcnow()
            for row in db.scalars(select(Feedback).where(Feedback.status=='awaiting_approval',Feedback.approval_expires_at<now)):
                row.status='expired';row.last_error='审批已过期，未发布；重新排队需要重新生成及测试。';row.notification_sent=False
                event(db,row.id,'expired')
            db.commit()
            if db.scalar(select(Feedback.id).where(Feedback.status.in_(ACTIVE)).limit(1)): return
            count=db.scalar(select(func.count()).select_from(MaintenanceEvent).where(
                MaintenanceEvent.action=='ai_call',MaintenanceEvent.occurred_at>=datetime.combine(now.date(),dt_time.min)))
            if count>=self.cfg.max_jobs_per_day: return
            row=db.scalar(select(Feedback).where(Feedback.status=='queued').order_by(Feedback.id).limit(1))
            if not row: return
            job_id=row.id
        # All potentially long I/O happens outside a DB transaction.
        try:
            active=self.active_release()
            base=self.repo.sync()
            if base!=active['sha'] or not tree_matches(self.repo,base,Path(active['path'])):
                raise GateError('远程主分支与正在运行的代码不一致；不会把未经本机确认的新基线自动上线')
            with SessionLocal() as db:
                row=db.get(Feedback,job_id)
                if row.status!='queued': return
                if row.attempts>=3: raise GateError('本意见已达到3次生成上限，请另行人工处理')
                row.attempts+=1;row.status='proposing';row.base_sha=base
                row.branch=f'dealerdesk/change-{job_id}-{row.attempts}'
                row.head_sha='';row.test_result={};row.proposal={};row.last_error=''
                row.approval_token_hash='';row.approval_expires_at=None;row.notification_sent=False
                branch=row.branch;feedback={'title':row.title,'description':row.description,'category':row.category}
                db.commit()
            self.repo.checkout(base,branch)
            context=context_files(self.repo.path)
            with SessionLocal() as db:
                event(db,job_id,'ai_call',detail='仅提交意见文本与白名单源码；一次调用计入UTC自然日预算')
                db.commit()
            proposal=self.model(self.cfg,feedback['title'],feedback['description'],context)
            if proposal.risk=='manual':
                transition(job_id,'manual',proposal.manual_reason or '此意见超出自动维护白名单，需要人工开发',
                    proposal={'summary':proposal.summary,'files':[]})
                return
            changed=apply_proposal(self.repo.path,proposal)
            head=self.repo.commit(changed,job_id)  # Local commit only. No remote push yet.
            self.repo.verify_candidate(base,head)
            transition(job_id,'testing',head_sha=head,proposal={'summary':proposal.summary,'files':changed})
            with tempfile.TemporaryDirectory(prefix='dealerdesk-candidate-',dir=self.cfg.runtime) as tmp:
                source=self.repo.export(head,Path(tmp)/'source')
                result=self.tester(source,self.cfg)
            result={**result,'head_sha':head}
            if not result.get('passed'):
                transition(job_id,'failed','候选未通过隔离测试；未推送候选分支、未改动当前系统',test_result=result)
                return
            self.repo.push_candidate(branch)
            transition(job_id,'awaiting_approval',test_result=result,review_url=self.repo.compare_url(base,head))
        except GateError as exc:
            transition(job_id,'failed',str(exc))
        except Exception:
            # Never dump provider responses, environment values, or credentials.
            transition(job_id,'failed','维护任务出现未预期错误；未自动批准。请查看本地受控状态，核对后再试。')
            log.warning('Maintenance task %s stopped after an unexpected error',job_id)

    def notifications(self):
        with SessionLocal() as db:
            ids=list(db.scalars(select(Feedback.id).where(Feedback.status.in_(NOTIFY),Feedback.notification_sent.is_(False)).order_by(Feedback.id)))
        for job_id in ids:
            with SessionLocal() as db:
                row=db.get(Feedback,job_id);state=row.status
            notify_key=(job_id,state)
            if time.monotonic()-self.last_notify.get(notify_key,-1000)<60: continue
            self.last_notify[notify_key]=time.monotonic()
            try:
                token=issue_token(job_id,self.cfg,rollback=state=='deployed') if state in {'deployed','awaiting_approval'} else ''
                with SessionLocal() as db: row=db.get(Feedback,job_id)
                card=approval_card(row,token,rollback=state=='deployed') if token else status_card(row)
                self.bot.send(card,f'dealerdesk:{job_id}:{state}:{row.head_sha}:{row.approval_token_hash}')
                with SessionLocal() as db:
                    current=db.get(Feedback,job_id)
                    if current.status==state and current.approval_token_hash==row.approval_token_hash:
                        current.notification_sent=True
                        if state in {'awaiting_approval','deployed'} and current.last_error.startswith('飞书'): current.last_error=''
                        event(db,job_id,'feishu_sent',detail=state)
                        db.commit()
            except GateError as exc:
                with SessionLocal() as db:
                    row=db.get(Feedback,job_id)
                    if row.status in {'awaiting_approval','deployed'}: row.last_error=str(exc)[:500]
                    event(db,job_id,'notification_failed',detail=str(exc));db.commit()
            except Exception: log.warning('Feishu notification pending for task %s',job_id)

    def loop(self,stop):
        self.recover()
        while not stop.is_set():
            try:
                self.notifications();self.process_one();self.notifications()
            except Exception: log.warning('Maintenance tick paused; existing application remains unchanged')
            stop.wait(10)


def main():
    logging.basicConfig(level=logging.WARNING)
    cfg=MaintenanceConfig();cfg.validate();preflight(cfg);cfg.runtime.mkdir(parents=True,exist_ok=True)
    worker=Worker(cfg);stop=threading.Event()
    thread=threading.Thread(target=worker.loop,args=(stop,),daemon=True)
    thread.start()
    try: listen(cfg)  # SDK owns its asyncio event loop in this process's main thread.
    finally: stop.set();thread.join(timeout=2)

if __name__=='__main__': main()
