from dataclasses import dataclass, field
from pathlib import Path
import os
import re
from urllib.parse import urlparse
from app.config import ROOT, settings, flag
from .window import WindowError, parse_bans, parse_hhmm


class GateError(RuntimeError):
    """Operator-readable, credential-free error. Fail closed."""


def _list_env(key, default=''):
    return tuple(item.strip() for item in os.getenv(key, default).split(',') if item.strip())


def _bans_env(key):
    try:
        return parse_bans(os.getenv(key, ''))
    except WindowError as exc:
        raise GateError('禁运区间配置无效：' + str(exc)) from exc


LOCAL_TARGET = 'local'
SPLIT_TARGET = 'docker-split'


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
    approvers: tuple = field(default_factory=lambda: _list_env('FEISHU_APPROVER_OPEN_IDS'))
    receive_id: str = field(default_factory=lambda: os.getenv('FEISHU_RECEIVE_ID',''))
    receive_id_type: str = field(default_factory=lambda: os.getenv('FEISHU_RECEIVE_ID_TYPE','open_id'))
    tenant_key: str = field(default_factory=lambda: os.getenv('FEISHU_TENANT_KEY',''))
    # An application bot, not a custom webhook bot. No public HTTP callback endpoint.

    # --- split-mode / window settings -------------------------------------
    # local        : build, test and run the app on this machine (Windows dev).
    # docker-split : build+test on the Singapore builder, run the app in a
    #                container on this host. See docs/MAINTENANCE.md.
    deploy_target: str = field(default_factory=lambda: os.getenv('MAINT_DEPLOY_TARGET', LOCAL_TARGET).strip().lower())
    auto_publish: bool = field(default_factory=lambda: flag('MAINT_AUTO_PUBLISH','true'))
    window_tz: str = field(default_factory=lambda: os.getenv('MAINT_WINDOW_TZ','Asia/Shanghai').strip())
    window_start: str = field(default_factory=lambda: os.getenv('MAINT_WINDOW_START','22:00').strip())
    window_end: str = field(default_factory=lambda: os.getenv('MAINT_WINDOW_END','06:00').strip())
    window_bans: tuple = field(default_factory=lambda: _bans_env('MAINT_WINDOW_BANS'))
    min_segment_minutes: int = field(default_factory=lambda: int(os.getenv('MAINT_MIN_SEGMENT_MINUTES','20')))
    slot_attempts: int = field(default_factory=lambda: int(os.getenv('MAINT_SLOT_ATTEMPTS','10')))
    slot_pause_seconds: int = field(default_factory=lambda: int(os.getenv('MAINT_SLOT_PAUSE_SECONDS','60')))
    quant_units: tuple = field(default_factory=lambda: _list_env('MAINT_QUANT_UNITS'))
    sg_host: str = field(default_factory=lambda: os.getenv('MAINT_SG_HOST','').strip())
    sg_user: str = field(default_factory=lambda: os.getenv('MAINT_SG_USER','hkbuild').strip())
    sg_key: str = field(default_factory=lambda: os.getenv('MAINT_SG_KEY','').strip())
    sg_port: int = field(default_factory=lambda: int(os.getenv('MAINT_SG_PORT','22')))
    sg_timeout: int = field(default_factory=lambda: int(os.getenv('MAINT_SG_TIMEOUT','900')))
    app_container: str = field(default_factory=lambda: os.getenv('MAINT_APP_CONTAINER','huakangos-app'))
    app_image_prefix: str = field(default_factory=lambda: os.getenv('MAINT_APP_IMAGE_PREFIX','huakangos-app'))
    app_port: int = field(default_factory=lambda: int(os.getenv('MAINT_APP_PORT','8000')))
    app_publish_host: str = field(default_factory=lambda: os.getenv('MAINT_APP_PUBLISH_HOST','127.0.0.1'))
    app_publish_port: int = field(default_factory=lambda: int(os.getenv('MAINT_APP_PUBLISH_PORT','8000')))
    app_data_dir: str = field(default_factory=lambda: os.getenv('MAINT_APP_DATA_DIR',''))
    app_memory: str = field(default_factory=lambda: os.getenv('MAINT_APP_MEMORY','512m'))
    app_cpus: str = field(default_factory=lambda: os.getenv('MAINT_APP_CPUS','1'))

    @property
    def split(self) -> bool:
        return self.deploy_target == SPLIT_TARGET

    def validate(self):
        if not self.code_external_allowed: raise GateError('请明确设置 ALLOW_CODE_EXTERNAL=true；意见与白名单源码才会外发')
        if not self.key or not self.api_url.startswith('https://'): raise GateError('DeepSeek 编码接口必须配置密钥和 HTTPS 地址')
        if self.deploy_target not in {LOCAL_TARGET, SPLIT_TARGET}:
            raise GateError('MAINT_DEPLOY_TARGET 只能是 local 或 docker-split')
        if not self.split and not (re.fullmatch(r'https://[^\s@]+',self.repo_url) or re.fullmatch(r'git@[A-Za-z0-9.-]+:[A-Za-z0-9_./-]+',self.repo_url)):
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
        self._validate_window()
        if self.split: self._validate_split()

    def _validate_window(self):
        if self.window_start == self.window_end:
            raise GateError('维护时段的开始与结束不能相同')
        try:
            parse_hhmm(self.window_start); parse_hhmm(self.window_end)
        except WindowError as exc:
            raise GateError('维护时段配置无效：'+str(exc)) from exc
        if not 1 <= self.min_segment_minutes <= 480:
            raise GateError('MAINT_MIN_SEGMENT_MINUTES 必须在 1-480 之间')
        if not 1 <= self.slot_attempts <= 120 or not 5 <= self.slot_pause_seconds <= 600:
            raise GateError('让行重试次数或间隔超出支持范围（1-120 次，5-600 秒）')

    def _validate_split(self):
        if not self.sg_host or not re.fullmatch(r'[A-Za-z0-9.:_-]{1,120}', self.sg_host):
            raise GateError('docker-split 模式必须配置 MAINT_SG_HOST（构建机地址）')
        if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', self.sg_user):
            raise GateError('MAINT_SG_USER 必须是合法的 Linux 用户名')
        if not self.sg_key or not Path(self.sg_key).is_file():
            raise GateError('MAINT_SG_KEY 必须指向构建机私钥文件')
        if not (self.app_data_dir and Path(self.app_data_dir).is_dir()):
            raise GateError('docker-split 模式必须配置 MAINT_APP_DATA_DIR（业务数据目录，保存 SQLite）')
        if self.app_publish_host not in {'127.0.0.1','0.0.0.0'}:
            raise GateError('MAINT_APP_PUBLISH_HOST 只能是 127.0.0.1 或 0.0.0.0')
        if not 1 <= self.app_publish_port <= 65535 or not 1 <= self.app_port <= 65535:
            raise GateError('应用端口超出范围')
        if not re.fullmatch(r'\d{1,4}[mg]', self.app_memory):
            raise GateError('MAINT_APP_MEMORY 形如 512m')
        if not re.fullmatch(r'[0-9.]{1,6}', self.app_cpus):
            raise GateError('MAINT_APP_CPUS 形如 1 或 1.5')


def _docker_cli_present():
    from .gitops import run
    run(['docker','version','--format','{{.Server.Version}}'],timeout=20)


def preflight(cfg):
    """Local capability checks only; no model call and no live message."""
    import importlib.util
    from .gitops import run
    if importlib.util.find_spec('lark_oapi') is None:
        raise GateError('飞书 SDK 尚未安装；先运行 setup-maintenance，业务服务仍可使用')
    if cfg.split:
        # The isolated test image lives on the builder; here we only need the
        # docker CLI to run the application container itself.
        try: _docker_cli_present()
        except GateError as exc: raise GateError('本机 Docker 不可用，无法运行应用容器；自动维护暂停，业务服务仍可使用') from exc
    else:
        try: run(['docker','image','inspect',cfg.test_image,'--format','{{.Id}}'],timeout=20)
        except GateError as exc: raise GateError('Docker 隔离测试镜像未就绪；自动维护暂停，业务服务仍可使用') from exc


@dataclass(frozen=True)
class BuilderConfig:
    """Configuration for the Singapore build agent (forced-command entry point)."""

    repo_url: str = field(default_factory=lambda: os.getenv('HKB_REPO_URL',''))
    web_url: str = field(default_factory=lambda: os.getenv('HKB_REPO_WEB_URL','').rstrip('/'))
    base_branch: str = field(default_factory=lambda: os.getenv('HKB_BASE_BRANCH','main'))
    root: Path = field(default_factory=lambda: Path(os.getenv('HKB_ROOT','/opt/huakangos-builder')).resolve())
    test_image: str = field(default_factory=lambda: os.getenv('HKB_TEST_IMAGE','dealerdesk-tests:0.2'))
    app_image_prefix: str = field(default_factory=lambda: os.getenv('HKB_APP_IMAGE_PREFIX','huakangos-app'))
    git_ssh_key: str = field(default_factory=lambda: os.getenv('HKB_GIT_SSH_KEY',''))
    test_timeout: int = field(default_factory=lambda: int(os.getenv('HKB_TEST_TIMEOUT','1800')))
    build_timeout: int = field(default_factory=lambda: int(os.getenv('HKB_BUILD_TIMEOUT','3600')))
    min_free_gb: int = field(default_factory=lambda: int(os.getenv('HKB_MIN_FREE_GB','3')))
    window_tz: str = field(default_factory=lambda: os.getenv('HKB_WINDOW_TZ','Asia/Shanghai').strip())
    window_start: str = field(default_factory=lambda: os.getenv('HKB_WINDOW_START','22:00').strip())
    window_end: str = field(default_factory=lambda: os.getenv('HKB_WINDOW_END','06:00').strip())
    window_bans: tuple = field(default_factory=lambda: _bans_env('HKB_WINDOW_BANS'))
    min_segment_minutes: int = field(default_factory=lambda: int(os.getenv('HKB_MIN_SEGMENT_MINUTES','20')))
    quant_units: tuple = field(default_factory=lambda: _list_env('HKB_QUANT_UNITS'))
    trusted_sha: str = field(default_factory=lambda: os.getenv('HKB_TRUSTED_SHA','').strip())

    @property
    def clone(self) -> Path:
        return self.root/'repository'

    @property
    def runtime(self) -> Path:
        """Shape expected by Repository/sandbox, which key off cfg.runtime."""
        return self.root

    @property
    def state(self) -> Path:
        return self.root/'state'

    def validate(self):
        if not (re.fullmatch(r'https://[^\s@]+',self.repo_url) or re.fullmatch(r'git@[A-Za-z0-9.-]+:[A-Za-z0-9_./-]+',self.repo_url)):
            raise GateError('HKB_REPO_URL 只接受无内嵌凭据的 HTTPS 或 git@host:path SSH 仓库')
        parsed=urlparse(self.web_url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
            raise GateError('HKB_REPO_WEB_URL 必须是无凭据的 HTTPS 仓库页面')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,99}',self.base_branch) or '..' in self.base_branch:
            raise GateError('HKB_BASE_BRANCH 无效')
        if not re.fullmatch(r'[A-Za-z0-9_./:@-]+',self.test_image) or not re.fullmatch(r'[A-Za-z0-9_./-]+',self.app_image_prefix):
            raise GateError('镜像名称无效')
        if not 1 <= self.min_free_gb <= 200:
            raise GateError('HKB_MIN_FREE_GB 超出支持范围')
        if self.window_start == self.window_end:
            raise GateError('维护时段的开始与结束不能相同')
        try:
            parse_hhmm(self.window_start); parse_hhmm(self.window_end)
        except WindowError as exc:
            raise GateError('维护时段配置无效：'+str(exc)) from exc
        if not 1 <= self.min_segment_minutes <= 480:
            raise GateError('HKB_MIN_SEGMENT_MINUTES 必须在 1-480 之间')
        if self.trusted_sha and not re.fullmatch(r'[0-9a-f]{40}', self.trusted_sha):
            raise GateError('HKB_TRUSTED_SHA 必须是完整的 40 位提交号')