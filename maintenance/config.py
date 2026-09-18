from dataclasses import dataclass, field
from pathlib import Path
import os
import re
from urllib.parse import urlparse
from app.config import ROOT, settings, flag


class GateError(RuntimeError):
    """Operator-readable, credential-free error. Fail closed."""


@dataclass(frozen=True)
class MaintenanceConfig:
    enabled: bool = field(default_factory=lambda: flag('MAINTENANCE_ENABLED'))
    code_external_allowed: bool = field(default_factory=lambda: flag('ALLOW_CODE_EXTERNAL'))
    runtime: Path = field(default_factory=lambda: Path(os.getenv('MAINT_RUNTIME_DIR', str(ROOT/'data'/'maintenance'))).resolve())
    repo_url: str = field(default_factory=lambda: os.getenv('MAINT_REPO_URL',''))
    repo_web_url: str = field(default_factory=lambda: os.getenv('MAINT_REPO_WEB_URL','').rstrip('/'))
    base_branch: str = field(default_factory=lambda: os.getenv('MAINT_BASE_BRANCH','main'))
    model: str = field(default_factory=lambda: (os.getenv('DEEPSEEK_CODE_MODEL') or settings.deepseek_model))
    key: str = field(default_factory=lambda: (os.getenv('DEEPSEEK_CODE_API_KEY') or settings.deepseek_key))
    api_url: str = field(default_factory=lambda: settings.deepseek_url)
    max_jobs_per_day: int = field(default_factory=lambda: int(os.getenv('MAINT_MAX_JOBS_PER_DAY','3')))
    approval_hours: int = field(default_factory=lambda: int(os.getenv('MAINT_APPROVAL_HOURS','24')))
    test_image: str = field(default_factory=lambda: os.getenv('MAINT_TEST_IMAGE','dealerdesk-tests:0.2'))
    test_timeout: int = 300
    ai_timeout: int = 180
    app_id: str = field(default_factory=lambda: os.getenv('FEISHU_APP_ID',''))
    app_secret: str = field(default_factory=lambda: os.getenv('FEISHU_APP_SECRET',''))
    approvers: tuple = field(default_factory=lambda: tuple(x.strip() for x in os.getenv('FEISHU_APPROVER_OPEN_IDS','').split(',') if x.strip()))
    receive_id: str = field(default_factory=lambda: os.getenv('FEISHU_RECEIVE_ID',''))
    receive_id_type: str = field(default_factory=lambda: os.getenv('FEISHU_RECEIVE_ID_TYPE','open_id'))
    tenant_key: str = field(default_factory=lambda: os.getenv('FEISHU_TENANT_KEY',''))
    # An application bot, not a custom webhook bot. No public HTTP callback endpoint.

    def validate(self):
        if not self.code_external_allowed: raise GateError('请明确设置 ALLOW_CODE_EXTERNAL=true；意见与白名单源码才会外发')
        if not self.key or not self.api_url.startswith('https://'): raise GateError('DeepSeek 编码接口必须配置密钥和 HTTPS 地址')
        if not (re.fullmatch(r'https://[^\s@]+',self.repo_url) or re.fullmatch(r'git@[A-Za-z0-9.-]+:[A-Za-z0-9_./-]+',self.repo_url)):
            raise GateError('MAINT_REPO_URL 只接受无内嵌凭据的 HTTPS 或 git@host:path SSH 仓库')
        parsed=urlparse(self.repo_web_url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise GateError('MAINT_REPO_WEB_URL 必须是无凭据的 HTTPS 仓库页面')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,99}',self.base_branch) or '..' in self.base_branch or '@{' in self.base_branch:
            raise GateError('主分支名称无效')
        if not self.app_id or not self.app_secret or not self.approvers:
            raise GateError('需配置飞书应用 App ID、Secret 和审批人 open_id 白名单')
        if not all(re.fullmatch(r'ou_[A-Za-z0-9_-]{5,100}',a) for a in self.approvers): raise GateError('审批人必须填写此飞书应用下的 open_id，不能填姓名')
        if self.receive_id_type not in {'open_id','chat_id'}: raise GateError('FEISHU_RECEIVE_ID_TYPE 只能是 open_id 或 chat_id')
        if self.receive_id_type=='open_id' and self.receive_id and self.receive_id not in self.approvers:
            raise GateError('私聊接收人必须属于审批人白名单')
        if self.receive_id_type=='chat_id' and not self.receive_id: raise GateError('群卡片需要 FEISHU_RECEIVE_ID=oc_xxx')
        if not 1<=self.max_jobs_per_day<=20 or not 1<=self.approval_hours<=72: raise GateError('调用预算或审批有效期超出支持范围')
        if not re.fullmatch(r'[A-Za-z0-9_./:@-]+',self.test_image): raise GateError('测试镜像名称无效')


def preflight(cfg):
    """Local capability checks only; no model call and no live message."""
    import importlib.util
    from .gitops import run
    if importlib.util.find_spec('lark_oapi') is None:
        raise GateError('飞书 SDK 尚未安装；先运行 setup-maintenance，业务服务仍可使用')
    try: run(['docker','image','inspect',cfg.test_image,'--format','{{.Id}}'],timeout=20)
    except GateError as exc: raise GateError('Docker 隔离测试镜像未就绪；自动维护暂停，业务服务仍可使用') from exc
