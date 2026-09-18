from pathlib import Path
import os
import subprocess
import uuid
from .config import GateError
from .gitops import run


def host_cpus(limit: int = 2) -> str:
    """A --cpus value docker will accept on this host.

    The Singapore builder has one vCPU, and docker refuses `--cpus 2` there with
    "range of CPUs is from 0.01 to 1.00", which would fail every isolated test.
    """
    try:
        available = os.cpu_count() or 1
    except Exception:
        available = 1
    return str(max(1, min(int(limit), int(available))))


def docker_arguments(source: Path, image: str, name: str, cpus=None):
    return ['docker','run','--rm','--pull=never','--name',name,'--network','none','--read-only',
        '--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit','256','--memory','1g','--cpus',str(cpus or host_cpus()),
        '--user','65534:65534','--tmpfs','/tmp:rw,nosuid,nodev,size=268435456',
        '--mount',f'type=bind,src={source.resolve()},dst=/source,readonly',
        '--workdir','/source','--env','PYTHONDONTWRITEBYTECODE=1','--env','SCHEDULER_ENABLED=false',
        '--env','APP_ENV=test','--env','ALLOW_AI_EXTERNAL=false',image]


def test_candidate(source: Path,cfg):
    try: run(['docker','image','inspect',cfg.test_image,'--format','{{.Id}}'],timeout=20)
    except GateError as exc: raise GateError('隔离测试不可用：请先启动 Docker 并运行 setup-maintenance；绝不退回宿主机执行 AI 代码') from exc
    name='dealerdesk-test-'+uuid.uuid4().hex
    # No shell supplied by the model; the container has no DB, .env, Git metadata,
    # network, host credentials, Docker socket, or writable source tree.
    argv=docker_arguments(source,cfg.test_image,name)
    # The trusted image entrypoint, not a command from the candidate repository.
    with __import__('tempfile').TemporaryFile() as log:
        try:
            result=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=cfg.test_timeout,check=False)
            log.seek(0,os.SEEK_END);length=log.tell();log.seek(max(0,length-8000));tail=log.read().decode('utf-8','replace')
            return {'passed':result.returncode==0,'exit_code':result.returncode,'runner':'docker-no-network',
                    'image':cfg.test_image,'tail':tail[-8000:]}
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise GateError('隔离测试启动失败或超时；不提交可发布版本') from exc
        finally:
            # A client timeout may leave the daemon-side container running.
            try: subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,check=False)
            except (OSError,subprocess.TimeoutExpired): pass
