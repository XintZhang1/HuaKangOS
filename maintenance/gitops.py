"""Git CLI with fixed argument lists. AI-generated code never runs on this host.
Only a dedicated clone is modified; production files are immutable releases.
"""
from pathlib import Path, PurePosixPath
import hashlib
import io
import os
import re
import subprocess
import tarfile
from .config import GateError
from .policy import EDITABLE

SHA=re.compile(r'^[0-9a-f]{40}$')
FORBIDDEN_DIRS={'data','backups','.git','.venv','node_modules','__pycache__','.pytest_cache'}


def run(argv, cwd=None, timeout=90, binary=False):
    env=os.environ.copy();env['GIT_TERMINAL_PROMPT']='0'
    env['GIT_LFS_SKIP_SMUDGE']='1'
    try:
        result=subprocess.run(argv,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise GateError(f'{Path(argv[0]).name} 不可用或超时；未执行后续发布') from exc
    if result.returncode: raise GateError(f'{Path(argv[0]).name} 操作失败（退出码 {result.returncode}）；请检查认证、分支保护或工具配置')
    return result.stdout if binary else result.stdout.decode('utf-8','replace').strip()


class Repository:
    def __init__(self,cfg):
        self.cfg=cfg; self.path=cfg.runtime/'repository'
        self.hooks=cfg.runtime/'no-hooks';self.hooks.mkdir(parents=True,exist_ok=True)
    def git(self,*args,binary=False):
        return run(['git','-c',f'core.hooksPath={self.hooks}','-c','protocol.file.allow=never',*args],cwd=self.path,binary=binary)
    def sync(self):
        fresh=not self.path.exists()
        if fresh:
            run(['git','-c',f'core.hooksPath={self.hooks}','-c','protocol.file.allow=never','clone','--no-checkout','--',self.cfg.repo_url,str(self.path)],timeout=120)
        if self.git('remote','get-url','origin')!=self.cfg.repo_url: raise GateError('专用克隆的远程地址与配置不一致')
        self.git('fetch','--prune','origin',self.cfg.base_branch)
        base=self.git('rev-parse','FETCH_HEAD')
        if not SHA.fullmatch(base): raise GateError('无法确认 Git 提交')
        if fresh: self.git('checkout','--detach',base)
        return base
    def files(self,sha):
        if not SHA.fullmatch(sha): raise GateError('提交格式无效')
        records=self.git('ls-tree','-rz',sha,binary=True).split(b'\0')
        names=[]
        for record in records:
            if not record: continue
            meta,raw=record.split(b'\t',1);mode,kind,_=meta.decode().split()
            name=raw.decode('utf-8');parts=PurePosixPath(name).parts
            if mode not in {'100644','100755'} or kind!='blob': raise GateError('仓库包含符号链接或子模块，自动维护拒绝执行')
            if not parts or (name!='data/.gitkeep' and any(x in FORBIDDEN_DIRS for x in parts)) or '..' in parts or '\\' in name or ':' in name:
                raise GateError('仓库提交了运行数据/不安全路径；请先清理专用代码仓库')
            lower=parts[-1].lower()
            if (lower.startswith('.env') and lower!='.env.example') or lower.endswith(('.pem','.key','.sqlite','.db','.p12')) or lower in {'id_rsa','id_ed25519','credentials.json'}:
                raise GateError('仓库包含疑似凭据或数据库文件，禁止发送或部署')
            names.append(name)
        if len(names)>2000: raise GateError('仓库过大，超出此轻量维护器的范围')
        return names
    def export(self,sha,destination):
        allowed=set(self.files(sha));destination=Path(destination)
        if destination.exists(): raise GateError('发布目录已存在，拒绝覆盖')
        archive=self.git('archive','--format=tar',sha,binary=True)
        if len(archive)>25_000_000: raise GateError('代码归档超过25MB限制')
        destination.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(archive),mode='r:') as tar:
            for entry in tar:
                if entry.isdir(): continue
                if not entry.isfile() or entry.name not in allowed: raise GateError('代码归档含不安全条目')
                target=destination.joinpath(*PurePosixPath(entry.name).parts)
                if not target.resolve().is_relative_to(destination.resolve()): raise GateError('归档路径越界')
                target.parent.mkdir(parents=True,exist_ok=True)
                source=tar.extractfile(entry)
                with target.open('wb') as out: out.write(source.read())
        return destination
    def checkout(self,base,branch):
        if not re.fullmatch(r'dealerdesk/change-\d+-\d+',branch): raise GateError('候选分支名称无效')
        if self.git('status','--porcelain'): raise GateError('专用克隆有未提交修改，请人工检查；不会清理未知文件')
        self.git('checkout','--detach',base)
        self.git('switch','-c',branch)
    def commit(self,files,job_id):
        if not set(files)<=EDITABLE: raise GateError('候选代码修改了保护区')
        self.git('add','--',*files)
        self.git('-c','user.name=DealerDesk Maintenance','-c','user.email=dealerdesk-bot@localhost',
            '-c','commit.gpgsign=false','commit','-m',f'DealerDesk: feedback #{job_id} (pending human approval)')
        return self.git('rev-parse','HEAD')
    def verify_candidate(self,base,head):
        if not SHA.fullmatch(base) or not SHA.fullmatch(head): raise GateError('审批提交格式无效')
        parents=self.git('rev-list','--parents','-n','1',head).split()
        if parents!=[head,base]: raise GateError('候选不是已审核基线上的单一提交')
        changed=self.git('diff','--name-only',base,head).splitlines()
        if not changed or not set(changed)<=EDITABLE: raise GateError('候选提交修改了受保护文件')
        self.files(head)
        return changed
    def push_candidate(self,branch):
        self.git('push','origin',f'HEAD:refs/heads/{branch}')
    def remote_head(self,branch):
        result=self.git('ls-remote','--heads','origin',f'refs/heads/{branch}')
        return result.split()[0] if result else ''
    def publish(self,base,head,branch):
        self.verify_candidate(base,head)
        if self.remote_head(branch)!=head: raise GateError('远端候选分支已变化，原审批失效')
        current=self.remote_head(self.cfg.base_branch)
        if current==head: return  # Idempotent recovery after a successful push.
        if current!=base: raise GateError('主分支已有新提交，须重新生成、测试和审批；不会强制覆盖')
        # Normal fast-forward push; never force-push or bypass server branch protection.
        self.git('push','origin',f'{head}:refs/heads/{self.cfg.base_branch}')
        if self.remote_head(self.cfg.base_branch)!=head: raise GateError('主分支状态变动，停止自动部署')
    def revert_published(self,base,head,job_id):
        """Mechanical inverse of a previously approved single commit; no force push."""
        self.git('fetch','origin',self.cfg.base_branch)
        current=self.remote_head(self.cfg.base_branch)
        if current!=head: raise GateError('主分支已变化，不能回滚旧卡片；请审核最新运行版本')
        if self.git('status','--porcelain'): raise GateError('专用克隆有未提交修改，停止回滚')
        self.git('checkout','--detach',head)
        self.git('-c','user.name=DealerDesk Maintenance','-c','user.email=dealerdesk-bot@localhost',
            '-c','commit.gpgsign=false','revert','--no-edit',head)
        reverted=self.git('rev-parse','HEAD')
        if self.git('rev-parse',f'{reverted}^{{tree}}')!=self.git('rev-parse',f'{base}^{{tree}}'):
            raise GateError('回滚树与原版本不一致，拒绝推送')
        self.git('push','origin',f'{reverted}:refs/heads/{self.cfg.base_branch}')
        if self.remote_head(self.cfg.base_branch)!=reverted: raise GateError('无法确认回滚后的远端状态')
        return reverted
    def compare_url(self,base,head):
        return self.cfg.repo_web_url+f'/compare/{base}...{head}'


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_matches(repo,sha,root):
    # Verify every tracked file, not only editable files. Excludes untracked runtime data.
    for name in repo.files(sha):
        file=Path(root)/name
        if not file.is_file() or file.is_symlink(): return False
        raw=repo.git('show',f'{sha}:{name}',binary=True)
        if hashlib.sha256(raw).hexdigest()!=file_digest(file): return False
    return True
