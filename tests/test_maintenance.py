"""Controller security & lifecycle tests. Real Git; model/Docker/Feishu are fakes.
No credentials, production database, external request or user repository involved.
"""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import json
import subprocess
import pytest
from sqlalchemy import select
from app.db import SessionLocal, utcnow
from app.models import Feedback, Deployment, BotReceipt, MaintenanceEvent
from maintenance.config import MaintenanceConfig, GateError
from maintenance.policy import AUTO_APPROVER, Proposal, Edit, apply_proposal, safe_path, context_files
from maintenance.decisions import decide, issue_token, token_digest
from maintenance.feishu import approval_card
from maintenance.gitops import Repository, tree_matches
from maintenance.sandbox import docker_arguments
from maintenance.supervisor import Supervisor, atomic_json, backup_sqlite
from maintenance.worker import Worker
from maintenance import gitops

BASE='a'*40;HEAD='b'*40;APPROVER='ou_approved_test_owner'


def config(tmp_path,**kwargs):
    # auto_publish is deliberately OFF here: these tests cover the human approval
    # path. The auto-publish path has its own file (tests/test_policy_tier.py).
    fields={'enabled':True,'code_external_allowed':True,'runtime':tmp_path/'runtime','repo_url':'https://git.example/dealer.git',
        'repo_web_url':'https://git.example/dealer','key':'unit-test-not-real','app_id':'cli_test','app_secret':'not-real',
        'approvers':(APPROVER,),'receive_id':APPROVER,'auto_publish':False,'quant_units':()}
    fields.update(kwargs);cfg=replace(MaintenanceConfig(),**fields);cfg.runtime.mkdir(parents=True,exist_ok=True);return cfg


def job(state='awaiting_approval',**values):
    with SessionLocal() as db:
        row=Feedback(created_by=1,store_id=1,title='改进库存界面',description='请把库存卡片间距改得宽一点',status=state,
            base_sha=BASE,head_sha=HEAD,test_result={'passed':True,'head_sha':HEAD},**values)
        db.add(row);db.commit();return row.id


def get_job(id):
    with SessionLocal() as db:return db.get(Feedback,id)


@pytest.mark.parametrize('name',['../.env','/etc/passwd','web/../app/security.py','web\\app.js','C:/tmp/x','web//app.js'])
def test_patch_path_traversal_refused(tmp_path,name):
    with pytest.raises(GateError):safe_path(tmp_path,name)


@pytest.mark.parametrize('name',['app/security.py','app/analytics.py','app/models.py','maintenance/supervisor.py','requirements.txt','tests/test_app.py','.env','.github/workflows/deploy.yml'])
def test_protected_code_never_applied(tmp_path,name):
    proposal=Proposal(summary='恶意修改',risk='low',edits=[Edit(path=name,old='old',new='new')])
    with pytest.raises(GateError):apply_proposal(tmp_path,proposal)


def test_patch_exact_unique_and_atomic_validation(tmp_path):
    (tmp_path/'web').mkdir();p=tmp_path/'web/style.css';p.write_text('unique text; repeated; repeated')
    proposal=Proposal(summary='改样式',risk='low',edits=[Edit(path='web/style.css',old='unique text',new='new'),Edit(path='web/style.css',old='repeated',new='x')])
    with pytest.raises(GateError):apply_proposal(tmp_path,proposal)
    assert p.read_text().startswith('unique text')
    good=Proposal(summary='改样式',risk='low',edits=proposal.edits[:1]);assert apply_proposal(tmp_path,good)==['web/style.css']
    assert p.read_text().startswith('new')


def test_symlink_output_rejected(tmp_path):
    (tmp_path/'web').mkdir();outside=tmp_path/'actual';outside.write_text('old',encoding='utf-8')
    try:
        (tmp_path/'web/style.css').symlink_to(outside)
    except (OSError,NotImplementedError):
        # Windows without Developer Mode or admin rights cannot create symlinks.
        # Git entries that are symlinks are refused separately by gitops.files(),
        # and the Linux test image always exercises this path.
        pytest.skip('此平台不允许创建符号链接（Windows 需开发者模式或管理员权限）')
    with pytest.raises(GateError):apply_proposal(tmp_path,Proposal(summary='x',risk='low',edits=[Edit(path='web/style.css',old='old',new='new')]))


def test_manual_risk_output_rejected(tmp_path):
    with pytest.raises(GateError):apply_proposal(tmp_path,Proposal(summary='manual',risk='manual'))


def test_context_does_not_include_environment_database_or_backend(tmp_path):
    for name in ['web/style.css','app/security.py','.env','data/dealer.db','docs/USER_GUIDE.md']:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(name)
    assert set(context_files(tmp_path))=={'web/style.css','docs/USER_GUIDE.md'}


def test_docker_policy_is_fail_closed_no_network_no_secrets(tmp_path):
    args=docker_arguments(tmp_path,'dealerdesk-tests:0.2','test')
    assert args[args.index('--network')+1]=='none'
    assert '--read-only' in args and '--cap-drop=ALL' in args
    assert args[args.index('--user')+1]=='65534:65534'
    assert '--pull=never' in args and 'readonly' in args[args.index('--mount')+1]
    assert not any(s in ' '.join(args) for s in ['docker.sock','API_KEY','FEISHU','--privileged'])


@pytest.mark.parametrize('override',[{'code_external_allowed':False},{'approvers':()},{'approvers':('name-not-open-id',)},
    {'repo_url':'https://name:pass@example.com/x'},{'repo_url':'file:///tmp/repo'},{'repo_web_url':'http://example.com/x'},
    {'base_branch':'../main'},{'max_jobs_per_day':0},{'approval_hours':100},{'receive_id':'ou_not_permitted'}])
def test_configuration_safety(tmp_path,override):
    with pytest.raises(GateError):config(tmp_path,**override).validate()


def test_approval_bound_to_sha_operator_token_and_replay(tmp_path):
    cfg=config(tmp_path);id=job();token=issue_token(id,cfg)
    for operator,sha,tok in [('ou_attacker',HEAD,token),(APPROVER,BASE,token),(APPROVER,HEAD,'wrong')]:
        with pytest.raises(GateError):decide(cfg,operator,id,sha,tok,'approve','e-bad')
    assert get_job(id).status=='awaiting_approval'
    decide(cfg,APPROVER,id,HEAD,token,'approve','e-good')
    row=get_job(id);assert row.status=='approved' and row.approved_sha==HEAD
    assert token not in row.approval_token_hash
    assert '重复' in decide(cfg,APPROVER,id,HEAD,token,'approve','e-good')
    with SessionLocal() as db:assert len(list(db.scalars(select(BotReceipt))))==1
    with pytest.raises(GateError):decide(cfg,APPROVER,id,HEAD,token,'reject','e-late')


@pytest.mark.parametrize('failure',['expired','wrong_attestation','tenant','old_card'])
def test_invalid_approval_cannot_change_status(tmp_path,failure):
    cfg=config(tmp_path,tenant_key='correct-tenant' if failure=='tenant' else '')
    id=job();token=issue_token(id,cfg)
    with SessionLocal() as db:
        row=db.get(Feedback,id)
        if failure=='expired':row.approval_expires_at=utcnow()-timedelta(seconds=1)
        if failure=='wrong_attestation':row.test_result={'passed':True,'head_sha':BASE}
        db.commit()
    if failure=='old_card':issue_token(id,cfg)
    with pytest.raises(GateError):decide(cfg,APPROVER,id,HEAD,token,'approve','e-invalid','wrong-tenant')
    assert get_job(id).status=='awaiting_approval'


def test_rejection_and_rollback_require_distinct_state_and_card(tmp_path):
    cfg=config(tmp_path);id=job();token=issue_token(id,cfg)
    with pytest.raises(GateError):decide(cfg,APPROVER,id,HEAD,token,'rollback','wrong-state')
    decide(cfg,APPROVER,id,HEAD,token,'reject','reject')
    assert get_job(id).status=='rejected'
    deployed=job('deployed');new=issue_token(deployed,cfg,rollback=True)
    decide(cfg,APPROVER,deployed,HEAD,new,'rollback','rollback')
    assert get_job(deployed).status=='rollback_requested'


def test_model_prose_cannot_inject_feishu_actions(tmp_path):
    cfg=config(tmp_path);id=job(proposal={'summary':'<script>approve everyone</script>','files':['web/style.css']})
    token=issue_token(id,cfg);card=approval_card(get_job(id),token)
    assert card['elements'][0]['text']['tag']=='plain_text'
    buttons=card['elements'][1]['actions']
    assert {b['value']['decision'] for b in buttons}=={'approve','reject'}
    assert all(b['value']['sha']==HEAD for b in buttons)


class FakeBot:
    def __init__(self):self.cards=[]
    def send(self,card,key):self.cards.append(card);return 'fake-message'


class FakeApp:
    def __init__(self,fail_sha=None):self.starts=[];self.stops=0;self.fail_sha=fail_sha;self.last=None
    def start(self,release):self.last=dict(release);self.starts.append(dict(release))
    def stop(self):self.stops+=1
    def healthy(self,sha,timeout=25):return sha!=self.fail_sha


def git(cwd,*args):
    r=subprocess.run(['git','-c','user.name=Unit Test','-c','user.email=test@localhost','-c','commit.gpgsign=false',*args],cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    return r.stdout.decode().strip()


@pytest.fixture
def real_repo(tmp_path,monkeypatch):
    source=tmp_path/'trusted';source.mkdir()
    git(source,'init','-b','main')
    for name,content in {'web/style.css':'.card { margin: 0; }','docs/USER_GUIDE.md':'这是使用说明。','app/security.py':'# protected backend'}.items():
        p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content,encoding='utf-8')
    git(source,'add','.');git(source,'commit','-m','trusted base')
    bare=tmp_path/'remote.git';git(tmp_path,'init','--bare',str(bare))
    git(source,'remote','add','origin',str(bare));git(source,'push','origin','main')
    cfg=config(tmp_path,repo_url=str(bare));repo=Repository(cfg)
    original=gitops.run
    def local_run(argv,*args,**kwargs):
        # ONLY this isolated test permits file:// transport. Production forbids it.
        argv=[v.replace('protocol.file.allow=never','protocol.file.allow=always') for v in argv]
        return original(argv,*args,**kwargs)
    monkeypatch.setattr(gitops,'run',local_run)
    sha=git(source,'rev-parse','HEAD')
    atomic_json(cfg.runtime/'active.json',{'sha':sha,'path':str(source)})
    return cfg,repo,source,sha


def model_ok(cfg,title,description,files):
    assert '.env' not in files and 'app/security.py' not in files
    return Proposal(summary='扩大卡片间距',risk='low',edits=[Edit(path='web/style.css',old='.card { margin: 0; }',new='.card { margin: 8px; }')])


def candidate(real_repo,test_pass=True):
    cfg,repo,source,base=real_repo
    id=job('queued');bot=FakeBot()
    worker=Worker(cfg,repo,bot,model=model_ok,tester=lambda *a:{'passed':test_pass,'runner':'unit-test-fake-docker','exit_code':0 if test_pass else 1})
    worker.process_one();worker.notifications()
    return id,worker,bot


def approve_latest(cfg,id,bot,action='approve',event_id='approved-event'):
    values=next(b['value'] for b in bot.cards[-1]['elements'][1]['actions'] if b.get('value',{}).get('decision')==action)
    return decide(cfg,APPROVER,id,values['sha'],values['token'],action,event_id)


def fake_backup(url,path):path.parent.mkdir(parents=True,exist_ok=True);path.write_text('TEST-ONLY backup marker');return str(path)


def controller(real_repo,app):
    cfg,repo,source,base=real_repo
    ctl=Supervisor(cfg,app,repo,root=source,backup=fake_backup)
    ctl.active={'sha':base,'path':str(source)};ctl.ready=True
    return ctl


def test_full_git_candidate_approval_deploy_and_code_only_rollback(real_repo):
    cfg,repo,source,base=real_repo
    id,worker,bot=candidate(real_repo)
    row=get_job(id);head=row.head_sha
    assert row.status=='awaiting_approval' and row.test_result['head_sha']==head
    assert repo.remote_head('main')==base  # candidate must not reach main before approval
    assert repo.remote_head(row.branch)==head
    assert (source/'web/style.css').read_text()=='.card { margin: 0; }'
    approve_latest(cfg,id,bot)
    ctl=controller(real_repo,FakeApp());ctl.deploy(id)
    assert get_job(id).status=='deployed'
    assert ctl.active['sha']==head and repo.remote_head('main')==head
    assert (Path(ctl.active['path'])/'web/style.css').read_text()=='.card { margin: 8px; }'
    assert not ctl.gate.exists()
    worker.notifications();approve_latest(cfg,id,bot,'rollback','rollback-event')
    ctl.rollback(id)
    assert get_job(id).status=='rolled_back'
    assert ctl.active['sha'] not in {base,head}  # new Git revert, not force-reset history
    assert repo.remote_head('main')==ctl.active['sha']
    assert tree_matches(repo,ctl.active['sha'],Path(ctl.active['path']))
    with SessionLocal() as db:assert db.get(Feedback,id) is not None  # database was NOT rolled back


def test_failed_test_never_pushes_candidate_or_main(real_repo):
    cfg,repo,source,base=real_repo;id,worker,bot=candidate(real_repo,False)
    row=get_job(id)
    assert row.status=='failed' and not row.test_result['passed']
    assert repo.remote_head('main')==base and repo.remote_head(row.branch)==''


def test_without_approval_direct_deployment_is_blocked(real_repo):
    cfg,repo,source,base=real_repo;id,worker,bot=candidate(real_repo)
    app=FakeApp();ctl=controller(real_repo,app);ctl.deploy(id)
    assert get_job(id).status=='failed' and repo.remote_head('main')==base and not app.starts


def test_failed_health_restores_old_code_and_pauses(real_repo):
    cfg,repo,source,base=real_repo;id,worker,bot=candidate(real_repo);head=get_job(id).head_sha
    approve_latest(cfg,id,bot)
    app=FakeApp(fail_sha=head);ctl=controller(real_repo,app);ctl.deploy(id)
    assert get_job(id).status=='failed' and app.last['sha']==base
    assert repo.remote_head('main')==base
    assert (cfg.runtime/'PAUSED').exists() and not ctl.gate.exists()


def test_git_main_changed_after_approval_cannot_be_overwritten(real_repo):
    cfg,repo,source,base=real_repo;id,worker,bot=candidate(real_repo)
    approve_latest(cfg,id,bot)
    (source/'docs/USER_GUIDE.md').write_text('负责人更新的说明',encoding='utf-8')
    git(source,'add','.');git(source,'commit','-m','owner update');git(source,'push','origin','main')
    owner=git(source,'rev-parse','HEAD')
    app=FakeApp();controller(real_repo,app).deploy(id)
    assert get_job(id).status=='failed' and repo.remote_head('main')==owner and not app.starts


def test_daily_ai_budget_counts_calls_not_successes(real_repo):
    cfg,repo,source,base=real_repo
    with SessionLocal() as db:
        id=job('new')
        for _ in range(cfg.max_jobs_per_day):db.add(MaintenanceEvent(feedback_id=id,action='ai_call',actor='test'))
        db.commit()
    waiting=job('queued');calls=[]
    Worker(cfg,repo,FakeBot(),model=lambda *a:calls.append(1)).process_one()
    assert calls==[] and get_job(waiting).status=='queued'


def test_inflight_crash_not_silently_retried(real_repo):
    cfg,repo,source,base=real_repo;id=job('proposing')
    Worker(cfg,repo,FakeBot()).recover()
    assert get_job(id).status=='failed'


def test_failed_send_never_auto_approves(real_repo):
    cfg,repo,source,base=real_repo;id,worker,bot=candidate(real_repo)
    with SessionLocal() as db:r=db.get(Feedback,id);r.notification_sent=False;db.commit()
    class Broken:
        def send(self,*a):raise GateError('飞书未连接')
    worker.bot=Broken();worker.last_notify={};worker.notifications()
    assert get_job(id).status=='awaiting_approval' and not get_job(id).notification_sent
    assert repo.remote_head('main')==base


def test_real_consistent_backup_keeps_committed_rows(tmp_path):
    import sqlite3
    source=tmp_path/'business.sqlite'
    with sqlite3.connect(source) as db:
        db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE money (amount INTEGER)');db.execute('INSERT INTO money VALUES (12345)');db.commit()
        dest=tmp_path/'backup.sqlite';backup_sqlite('sqlite:///'+str(source),dest)
    with sqlite3.connect(dest) as db:assert db.execute('SELECT amount FROM money').fetchone()[0]==12345
    with pytest.raises(GateError):backup_sqlite('postgresql://unused',tmp_path/'other')


def test_protected_frontend_blocks_preserved(tmp_path):
    p=tmp_path/'web/app.js';p.parent.mkdir()
    p.write_text('// MAINT_PROTECTED_BEGIN:security\nconst safe = true;\n// MAINT_PROTECTED_END:security\nconst label = "old";')
    change=Proposal(summary='绕过前端保护',risk='low',edits=[Edit(path='web/app.js',old='const safe = true;',new='const safe = false;')])
    with pytest.raises(GateError):apply_proposal(tmp_path,change)
    assert 'true' in p.read_text()
    valid=Proposal(summary='调整文字',risk='low',edits=[Edit(path='web/app.js',old='const label = "old";',new='const label = "new";')])
    assert apply_proposal(tmp_path,valid)==['web/app.js']

# --- publish tiering ------------------------------------------------------
# The model's own "this needs a human" signal must win over the mechanical tier.
# worker.process_one checks risk=='manual' BEFORE the tier, and these tests pin
# that ordering: a manual verdict on a purely frontend proposal must never be
# auto-published, no matter how permissive the tier would be.

def manual_model(cfg,title,description,files):
    return Proposal(summary='建议重构统计口径',risk='manual',manual_reason='涉及金额口径，需人工开发',edits=[])


def test_manual_verdict_is_never_auto_published(real_repo):
    cfg,repo,source,base=real_repo;cfg=replace(cfg,auto_publish=True)
    id=job('queued');bot=FakeBot()
    Worker(cfg,repo,bot,model=manual_model).process_one()
    row=get_job(id)
    assert row.status=='manual'
    assert not row.approved_by and not row.approved_sha
    assert repo.remote_head('main')==base


def test_frontend_candidate_is_auto_approved_when_enabled(real_repo):
    cfg,repo,source,base=real_repo
    auto=replace(cfg,auto_publish=True)
    id=job('queued');bot=FakeBot()
    # Built inline: the shared candidate() helper deliberately pins auto_publish=False.
    Worker(auto,repo,bot,model=model_ok,tester=lambda *a:{'passed':True,'runner':'unit-test-fake-docker','exit_code':0}).process_one()
    row=get_job(id)
    assert row.status=='approved', 'frontend candidate should not wait for a click'
    assert row.approved_by==AUTO_APPROVER and row.approved_sha==row.head_sha
    assert repo.remote_head('main')==base, 'the tier gate must not push main by itself'


def test_auto_publish_disabled_still_requires_a_human(real_repo):
    cfg,repo,source,base=real_repo
    assert cfg.auto_publish is False
    id,worker,bot=candidate(real_repo)
    assert get_job(id).status=='awaiting_approval'

# --- repository helper used by the builder's context verb ----------------

def test_checkout_detached_lands_on_the_exact_commit(real_repo):
    """`context` needs a detached checkout; the method was missing and the
    builder crashed with AttributeError on the first real run."""
    cfg,repo,source,base=real_repo
    repo.sync()
    assert repo.checkout_detached(base)==base
    assert repo.git('rev-parse','HEAD')==base
    assert repo.git('rev-parse','--abbrev-ref','HEAD')=='HEAD', 'must be detached, not on a branch'
    with pytest.raises(GateError): repo.checkout_detached('not-a-sha')
