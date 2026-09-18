"""Singapore builder agent tests: guard, request validation, dispatcher, lock.

Offline and hermetic by construction. The repository, the system clock, systemctl,
the docker CLI and the filesystem root are all replaced by fakes or tripwires, and
every config points `root` at tmp_path, so no test here reads /opt, Docker, SSH or
the network. A tripwire that fires is a failure by design: ForbiddenRepo raises on
any repository attribute access, RecordingProcesses raises on any attempt to start
a process, and Sealed.assert_idle proves nothing was written under root.

Several real behaviours differ from the documented contract (or from the coverage
brief this file was written against); every test that pins one says so in a
CONTRADICTION comment next to the assertion -- see the payload, image and
dispatcher sections.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from maintenance import transport
from maintenance.builder import __main__ as builder_main
from maintenance.builder import verbs
from maintenance.builder.lock import BuildLock
from maintenance.builder.verbs import Builder, Refused
from maintenance.config import BuilderConfig, GateError
from maintenance.policy import Proposal
from maintenance.window import QuantState, WindowState, parse_bans, window_state

BASE = 'a'*40
REMOTE = 'f'*40
BRANCH = 'dealerdesk/change-7-2'
CLOSED_REASON = '当前不在维护时段 22:00-06:00（Asia/Shanghai）'
OPEN_WINDOW = WindowState(True, '', 300)
CLOSED_WINDOW = WindowState(False, CLOSED_REASON, 0, opens_in=200)
IDLE = QuantState()
BUSY_UNIT = 'quantumbit-trader@main.service'


def config(tmp_path, **fields):
    """BuilderConfig rooted in tmp_path: never the real /opt tree or the real clock."""
    fields.setdefault('root', tmp_path)
    fields.setdefault('quant_units', ())
    fields.setdefault('window_tz', 'Asia/Shanghai')
    fields.setdefault('window_start', '22:00')
    fields.setdefault('window_end', '06:00')
    fields.setdefault('window_bans', ())
    return replace(BuilderConfig(), **fields)


def edit(path='web/style.css'):
    return {'path': path, 'old': 'a', 'new': 'b'}


def proposal(path='web/style.css'):
    return {'summary': '调整卡片间距', 'risk': 'low', 'manual_reason': '', 'edits': [edit(path)]}


def candidate_payload(**fields):
    payload = {'job_id': 7, 'base_sha': BASE, 'branch': BRANCH, 'proposal': proposal()}
    payload.update(fields)
    return payload


def revert_payload(**fields):
    payload = {'base_sha': BASE, 'head_sha': REMOTE, 'job_id': 7}
    payload.update(fields)
    return payload


def window(monkeypatch, state=OPEN_WINDOW):
    """No wall clock: the guard sees exactly the state this test dictates."""
    monkeypatch.setattr(verbs, 'window_state', lambda cfg: state)


def quant(monkeypatch, state=IDLE):
    """No systemctl: the guard sees exactly the quant state this test dictates."""
    monkeypatch.setattr(verbs, 'quant_state', lambda units: state)


def healthy_host(monkeypatch, free_gb=100.0, trusted=True):
    """Docker and disk answers without docker, without the real filesystem."""
    monkeypatch.setattr(verbs, 'disk_free_gb', lambda path: free_gb)
    monkeypatch.setattr(verbs, 'trusted_test_image',
                        lambda cfg: (trusted, '' if trusted else '测试镜像不可用'))
    processes = RecordingProcesses()
    monkeypatch.setattr(verbs, 'subprocess', processes)
    return processes


class ForbiddenRepo:
    """Tripwire: touching the repository means work happened where it must not."""

    def __getattr__(self, name):
        raise AssertionError('请求被拒绝前不该访问仓库：' + name)


class RecordingRepo:
    """Minimal Repository stand-in that records exactly which calls it receives."""

    def __init__(self, root, sync_sha=REMOTE):
        self.path = Path(root)
        self.sync_sha = sync_sha
        self.calls = []

    def sync(self):
        self.calls.append('sync')
        return self.sync_sha

    def checkout_detached(self, base):
        self.calls.append('checkout_detached')

    def checkout(self, base, branch):
        self.calls.append('checkout')

    def commit(self, files, job_id):
        self.calls.append('commit')
        return BASE

    def export(self, head, destination):
        self.calls.append('export')
        return Path(destination)

    def push_candidate(self, branch):
        self.calls.append('push_candidate')

    def remote_head(self, branch):
        return self.sync_sha

    def compare_url(self, base, head):
        return 'https://example.invalid/compare'


class RecordingProcesses:
    """Tripwire: these tests may never start docker, gzip, git or a shell."""

    DEVNULL = None
    PIPE = None

    def __init__(self):
        self.calls = []

    def run(self, *args, **kwargs):
        self.calls.append(('run', args))
        raise AssertionError('测试不允许启动进程：%r' % (args,))

    def Popen(self, *args, **kwargs):
        self.calls.append(('Popen', args))
        raise AssertionError('测试不允许启动进程：%r' % (args,))


def snapshot(root):
    return sorted(str(path.relative_to(root)) for path in Path(root).rglob('*'))


class Sealed:
    """Sandbox for payload validation: guard, docker, git and files are tripwired."""

    def __init__(self, tmp_path, monkeypatch):
        self.root = Path(tmp_path)
        self.before = snapshot(self.root)
        self.repo = ForbiddenRepo()
        self.processes = RecordingProcesses()
        for name in ('window_state', 'quant_state', 'disk_free_gb', 'trusted_test_image'):
            monkeypatch.setattr(verbs, name, self._tripwire(name))
        monkeypatch.setattr(verbs, 'subprocess', self.processes)

    @staticmethod
    def _tripwire(name):
        def explode(*args, **kwargs):
            raise AssertionError('非法请求在拒绝前调用了 ' + name)
        return explode

    def builder(self, tmp_path):
        return Builder(config(tmp_path), repo=self.repo)

    def assert_idle(self):
        """Refused before any git, docker, systemctl or filesystem work."""
        assert self.processes.calls == []
        assert snapshot(self.root) == self.before


# --- A. the guard: fail closed on a closed window or a busy quant job ------

def test_guard_refuses_while_the_window_is_closed(tmp_path, monkeypatch):
    window(monkeypatch, CLOSED_WINDOW)
    quant(monkeypatch)
    with pytest.raises(Refused) as caught:
        Builder(config(tmp_path), repo=ForbiddenRepo()).guard()
    assert caught.value.code == 'not_now'
    assert str(caught.value) == CLOSED_REASON
    assert '维护时段' in str(caught.value)


def test_guard_checks_the_window_before_consulting_systemctl(tmp_path, monkeypatch):
    # Ordering is part of the contract: a closed window must not shell out at all.
    window(monkeypatch, CLOSED_WINDOW)
    monkeypatch.setattr(verbs, 'quant_state', Sealed._tripwire('quant_state'))
    with pytest.raises(Refused) as caught:
        Builder(config(tmp_path), repo=ForbiddenRepo()).guard()
    assert caught.value.code == 'not_now'


def test_guard_refuses_while_a_quant_unit_is_busy(tmp_path, monkeypatch):
    window(monkeypatch)
    quant(monkeypatch, QuantState(busy=(BUSY_UNIT,)))
    with pytest.raises(Refused) as caught:
        Builder(config(tmp_path), repo=ForbiddenRepo()).guard()
    assert caught.value.code == 'not_now'
    assert BUSY_UNIT in str(caught.value)
    assert '让行' in str(caught.value)


def test_guard_fails_closed_when_the_quant_state_is_unknown(tmp_path, monkeypatch):
    window(monkeypatch)
    quant(monkeypatch, QuantState(unknown=True))
    with pytest.raises(Refused) as caught:
        Builder(config(tmp_path), repo=ForbiddenRepo()).guard()
    assert caught.value.code == 'not_now'
    assert '无法确认' in str(caught.value)


def test_guard_passes_inside_the_window_with_idle_quant_units(tmp_path, monkeypatch):
    window(monkeypatch)
    quant(monkeypatch)
    assert Builder(config(tmp_path), repo=ForbiddenRepo()).guard() is None


def test_guard_follows_the_real_window_rules_without_the_wall_clock(tmp_path, monkeypatch):
    """The real window_state, fed a fixed instant instead of datetime.now()."""
    cfg = config(tmp_path)
    builder = Builder(cfg, repo=ForbiddenRepo())
    quant(monkeypatch)

    def at(moment):
        return lambda cfg: window_state(cfg, now=moment)

    # 2026-01-01T12:00Z == 20:00 Asia/Shanghai, before the 22:00-06:00 window.
    monkeypatch.setattr(verbs, 'window_state', at(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)))
    with pytest.raises(Refused) as caught:
        builder.guard()
    assert caught.value.code == 'not_now'
    assert '维护时段' in str(caught.value)

    # 2026-01-01T15:00Z == 23:00 Asia/Shanghai: open, 420 minutes of segment left.
    monkeypatch.setattr(verbs, 'window_state', at(datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc)))
    assert builder.guard() is None


def test_guard_honours_the_trader_ban_segments(tmp_path, monkeypatch):
    cfg = config(tmp_path, window_bans=parse_bans('23:50-00:30,03:50-04:30'))
    quant(monkeypatch)
    # 2026-01-01T16:01Z == 00:01 Asia/Shanghai, inside the outer window but banned:
    # the QuantBit traders fire at 00:01 and 04:01 Shanghai time.
    monkeypatch.setattr(verbs, 'window_state',
                        lambda c: window_state(c, now=datetime(2026, 1, 1, 16, 1, tzinfo=timezone.utc)))
    with pytest.raises(Refused) as caught:
        Builder(cfg, repo=ForbiddenRepo()).guard()
    assert caught.value.code == 'not_now'
    assert '保护时段' in str(caught.value)


def test_a_default_builder_keeps_every_path_inside_the_configured_root(tmp_path):
    # Hermeticity guard: Repository is only constructed for the default path, and
    # both its clone and its hooks directory live under root, never under /opt.
    builder = Builder(config(tmp_path))
    assert builder.repo.path == tmp_path/'repository'
    assert (tmp_path/'no-hooks').is_dir()
    assert not builder.repo.path.exists()   # construction runs no git command


# --- B. request validation happens before any git or docker work -----------

@pytest.mark.parametrize('value', ['nothex', '', 'a'*39, 'A'*40, BASE+'0', None, 12345])
def test_candidate_rejects_a_malformed_base_sha(tmp_path, monkeypatch, value):
    sealed = Sealed(tmp_path, monkeypatch)
    with pytest.raises(GateError) as caught:
        sealed.builder(tmp_path).candidate(candidate_payload(base_sha=value))
    assert 'base_sha' in str(caught.value)
    sealed.assert_idle()


@pytest.mark.parametrize('value', [0, -1, None, '0', '-3'])
def test_candidate_rejects_a_non_positive_job_id(tmp_path, monkeypatch, value):
    sealed = Sealed(tmp_path, monkeypatch)
    with pytest.raises(GateError) as caught:
        sealed.builder(tmp_path).candidate(candidate_payload(job_id=value))
    assert 'job_id' in str(caught.value)
    sealed.assert_idle()


@pytest.mark.parametrize('call', ['candidate', 'revert'])
def test_a_non_numeric_job_id_is_a_refusal_not_a_crash(tmp_path, monkeypatch, call):
    # Regression guard. job_id is coerced through _job_id(), so malformed input is
    # a refusal. Before that guard existed this raised a bare ValueError, which the
    # dispatcher reported as an internal crash (exit 3 plus crash.log) rather than
    # as a bad request.
    sealed = Sealed(tmp_path, monkeypatch)
    builder = sealed.builder(tmp_path)
    payload = candidate_payload(job_id='abc') if call == 'candidate' else revert_payload(job_id='abc')
    with pytest.raises(GateError) as caught:
        getattr(builder, call)(payload)
    assert 'job_id' in str(caught.value)
    sealed.assert_idle()


@pytest.mark.parametrize('value', ['main', 'dealerdesk/change-1', 'dealerdesk/change-1-2-3',
                                   'dealerdesk/change-x-1', 'DealerDesk/change-1-2', 'change-1-2',
                                   'dealerdesk/change-1-2 ', '', None])
def test_candidate_rejects_a_branch_outside_the_candidate_pattern(tmp_path, monkeypatch, value):
    # BRANCH_RE is dealerdesk/change-<digits>-<digits>; 'main' and a two-part
    # change branch are both refused before anything is checked out.
    sealed = Sealed(tmp_path, monkeypatch)
    with pytest.raises(GateError) as caught:
        sealed.builder(tmp_path).candidate(candidate_payload(branch=value))
    assert '分支' in str(caught.value)
    sealed.assert_idle()


def test_candidate_refuses_a_proposal_that_edits_a_protected_file(tmp_path, monkeypatch):
    window(monkeypatch)
    quant(monkeypatch)
    healthy_host(monkeypatch)
    # sync() agrees with the requested base, so the drift check cannot short-circuit
    # the run before apply_proposal() gets to veto the protected path.
    repo = RecordingRepo(tmp_path, sync_sha=BASE)
    payload = candidate_payload(proposal={'summary': 'x', 'risk': 'low', 'manual_reason': '',
                                          'edits': [{'path': 'app/analytics.py', 'old': 'a', 'new': 'b'}]})
    with pytest.raises(GateError) as caught:
        Builder(config(tmp_path), repo=repo).candidate(payload)
    assert 'app/analytics.py' in str(caught.value)
    assert '白名单外' in str(caught.value)
    # The whitelist veto now runs before any git work, so a hostile patch never even
    # causes a fetch or a checkout -- the repo is untouched. apply_proposal() still
    # re-checks it further down, so this is defence in depth rather than the only gate.
    assert repo.calls == []


BAD_PROPOSALS = [
    {'summary': 'x', 'risk': 'high', 'edits': []},                       # risk not in {low, manual}
    {'summary': 'x', 'risk': 'LOW', 'edits': []},
    {'summary': 'x', 'risk': 'low', 'edits': [], 'extra': 'boom'},       # extra key on Proposal
    {'summary': 'x', 'risk': 'low', 'edits': [dict(edit(), oops=1)]},    # extra key on Edit
    {'summary': 'x', 'risk': 'low', 'edits': 'not-a-list'},
    {'summary': 'x', 'risk': 'low', 'edits': [{'path': 'web/style.css', 'new': 'b'}]},
    {'summary': 'x', 'risk': 'low', 'edits': [{'path': 'web/style.css', 'old': '', 'new': 'b'}]},
    {'summary': 'x', 'risk': 'low', 'edits': [{'path': '', 'old': 'a', 'new': 'b'}]},
    {'summary': 'x', 'risk': 'low', 'edits': [{'path': 'p'*151, 'old': 'a', 'new': 'b'}]},
    {'summary': 'x', 'risk': 'low', 'edits': [edit()]*13},               # max_length 12
    {'summary': '', 'risk': 'low', 'edits': []},
    {'risk': 'low', 'edits': []},                                        # summary missing
    {'summary': 'x', 'risk': 'low', 'manual_reason': 'r'*1801, 'edits': []},
    'not-an-object',
    [],
    None,
]


@pytest.mark.parametrize('bad', BAD_PROPOSALS)
def test_candidate_rejects_a_structurally_invalid_proposal(tmp_path, monkeypatch, bad):
    sealed = Sealed(tmp_path, monkeypatch)
    with pytest.raises(GateError) as caught:
        sealed.builder(tmp_path).candidate(candidate_payload(proposal=bad))
    assert '候选补丁结构无效' in str(caught.value)
    sealed.assert_idle()


def test_a_proposal_without_edits_is_valid_and_only_the_guard_stops_it(tmp_path, monkeypatch):
    # CONTRADICTION with the requested coverage: an edit-less proposal is NOT
    # structurally invalid. policy.Proposal defaults edits to [] (max_length=12
    # only bounds the non-empty case), so candidate() accepts it and walks on to
    # the window guard. apply_proposal() is what later refuses `not proposal.edits`,
    # and it needs a real repository, so no GateError is raised at validation time.
    assert Proposal.model_validate({'summary': 'x', 'risk': 'low'}).edits == []
    window(monkeypatch, CLOSED_WINDOW)
    quant(monkeypatch)
    with pytest.raises(Refused) as caught:
        Builder(config(tmp_path), repo=ForbiddenRepo()).candidate(
            candidate_payload(proposal={'summary': 'x', 'risk': 'low'}))
    assert caught.value.code == 'not_now'


def test_a_manual_risk_proposal_is_valid_and_only_the_guard_stops_it(tmp_path, monkeypatch):
    # risk='manual' is inside the Literal policy.Proposal allows; apply_proposal()
    # is the layer that refuses it ("需要人工开发"), and that layer runs after git.
    window(monkeypatch, CLOSED_WINDOW)
    quant(monkeypatch)
    with pytest.raises(Refused) as caught:
        Builder(config(tmp_path), repo=ForbiddenRepo()).candidate(
            candidate_payload(proposal={'summary': 'x', 'risk': 'manual', 'edits': []}))
    assert caught.value.code == 'not_now'


@pytest.mark.parametrize('values,key', [
    ({'job_id': 0}, 'job_id'),
    ({'job_id': -1}, 'job_id'),
    ({'base_sha': 'nothex'}, 'base_sha'),
    ({'base_sha': BASE[:-1]}, 'base_sha'),
    ({'head_sha': 'zz'}, 'head_sha'),
    ({'head_sha': None}, 'head_sha'),
])
def test_revert_rejects_a_bad_job_id_or_sha(tmp_path, monkeypatch, values, key):
    sealed = Sealed(tmp_path, monkeypatch)
    with pytest.raises(GateError) as caught:
        sealed.builder(tmp_path).revert(revert_payload(**values))
    assert key in str(caught.value)
    sealed.assert_idle()


@pytest.mark.parametrize('tag', ['other-app:' + 'a'*40,        # right shape, wrong app
                                 'huakangos-app-evil:' + 'a'*40,
                                 'huakangos-app:main',          # not a 40-hex sha
                                 'huakangos-app:' + 'A'*40,
                                 'huakangos-app:' + 'a'*39,
                                 'huakangos-app:latest',
                                 'huakangos-app:',
                                 'huakangos-app',
                                 'huakangos-app-test:' + 'a'*40,
                                 '', None])
def test_image_export_refuses_foreign_or_unpinned_tags(tmp_path, monkeypatch, capsys, tag):
    sealed = Sealed(tmp_path, monkeypatch)
    with pytest.raises(GateError) as caught:
        sealed.builder(tmp_path).stream_image({'image_tag': tag})
    assert '拒绝导出' in str(caught.value)
    assert capsys.readouterr().out == ''   # nothing at all was written to stdout
    sealed.assert_idle()                   # no docker, no gzip, no process, no file


# --- C. base-branch drift is a polite re-queue, never a gate error ---------

@pytest.mark.parametrize('call', ['context', 'candidate'])
def test_base_drift_is_a_polite_refusal_naming_both_shas(tmp_path, monkeypatch, call):
    window(monkeypatch)
    quant(monkeypatch)
    healthy_host(monkeypatch)
    repo = RecordingRepo(tmp_path, sync_sha=REMOTE)
    builder = Builder(config(tmp_path), repo=repo)
    payload = {'base_sha': BASE} if call == 'context' else candidate_payload(base_sha=BASE)
    with pytest.raises(Refused) as caught:
        getattr(builder, call)(payload)
    assert not isinstance(caught.value, GateError)   # re-queue, not a hard failure
    assert caught.value.code == 'refused'
    assert BASE[:12] in str(caught.value) and REMOTE[:12] in str(caught.value)
    assert '重新排队' in str(caught.value)
    assert repo.calls == ['sync']    # refused before checkout/apply/commit/push


# --- D. the forced-command dispatcher --------------------------------------

class DispatcherConfig:
    """Only the BuilderConfig surface __main__ touches: a state dir + validate()."""

    def __init__(self, root):
        self.root = Path(root)
        self.validated = 0

    @property
    def state(self):
        return self.root/'state'

    def validate(self):
        self.validated += 1


class UnusedBuilder:
    """Tripwire: this request must be refused before a Builder is ever built."""

    def __getattr__(self, name):
        raise AssertionError('请求应当在构造 Builder 之前就被拒绝：' + name)


class FakeBuilder:
    def __init__(self, result=None, error=None):
        self.result = {'ok': True} if result is None else result
        self.error = error
        self.calls = []

    def status(self, payload=None):
        self.calls.append(('status', payload))
        if self.error is not None:
            raise self.error
        return self.result


def wire(monkeypatch, tmp_path, factory):
    """Point __main__ at a fake config and a fake Builder; no /opt, no git."""
    built = []
    monkeypatch.setattr(builder_main, 'BuilderConfig', lambda: DispatcherConfig(tmp_path))

    def build(cfg):
        built.append(cfg)
        return factory(cfg)

    monkeypatch.setattr(builder_main, 'Builder', build)
    return built


@pytest.fixture
def no_processes(monkeypatch):
    """Tripwire: a shell -- or any process at all -- must never be started."""
    started = []

    def forbidden(*args, **kwargs):
        started.append(args)
        raise AssertionError('测试不允许启动进程：%r' % (args,))

    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(os, 'system', forbidden)
    monkeypatch.setattr(os, 'popen', forbidden)
    return started


def stdout_json(capsys):
    return json.loads(capsys.readouterr().out)


def test_an_unknown_verb_is_refused_as_bad_request(tmp_path, monkeypatch, capsys):
    built = wire(monkeypatch, tmp_path, lambda cfg: UnusedBuilder())
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', 'frobnicate')
    assert builder_main.main() == 0
    result = stdout_json(capsys)
    assert result['ok'] is False and result['code'] == 'bad_request'
    assert '未知动词' in result['detail']
    assert built == []


@pytest.mark.parametrize('command', [None, '', '   ', '\t\n'])
def test_a_missing_or_empty_command_is_refused(tmp_path, monkeypatch, capsys, command):
    built = wire(monkeypatch, tmp_path, lambda cfg: UnusedBuilder())
    if command is None:
        monkeypatch.delenv('SSH_ORIGINAL_COMMAND', raising=False)
    else:
        monkeypatch.setenv('SSH_ORIGINAL_COMMAND', command)
    assert builder_main.main() == 0
    result = stdout_json(capsys)
    assert result['ok'] is False and result['code'] == 'bad_request'
    assert built == []


def test_two_arguments_are_refused_as_too_many(tmp_path, monkeypatch, capsys):
    built = wire(monkeypatch, tmp_path, lambda cfg: UnusedBuilder())
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', 'status extra1 extra2')
    assert builder_main.main() == 0
    result = stdout_json(capsys)
    assert result['ok'] is False and result['code'] == 'bad_request'
    assert '参数过多' in result['detail']
    assert built == []


def test_an_unparsable_command_is_refused(tmp_path, monkeypatch, capsys):
    built = wire(monkeypatch, tmp_path, lambda cfg: UnusedBuilder())
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', 'status "unterminated')
    assert builder_main.main() == 0
    result = stdout_json(capsys)
    assert result['ok'] is False and result['code'] == 'bad_request'
    assert built == []


def test_a_payload_that_is_not_base64_exits_nonzero_with_no_json(tmp_path, monkeypatch, capsys):
    built = wire(monkeypatch, tmp_path, lambda cfg: UnusedBuilder())
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', 'status !!!not-base64!!!')
    # REAL BEHAVIOUR, and it contradicts the module docstring ("JSON verbs print
    # one JSON document on stdout and exit 0, including when they refuse"): a
    # GateError from decode() is reported on stderr with exit code 1 and writes
    # NOTHING to stdout. Only Refused (closed window / busy quant unit) becomes a
    # JSON refusal document with exit 0. Nothing crashed here: exit 1, not 3.
    assert builder_main.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'base64' in captured.err
    assert not (tmp_path/'state'/'crash.log').exists()
    assert 'gate_error' in (tmp_path/'state'/'audit.log').read_text(encoding='utf-8')
    assert built == []


def test_shell_metacharacters_never_reach_a_shell(tmp_path, monkeypatch, capsys, no_processes):
    built = wire(monkeypatch, tmp_path, lambda cfg: UnusedBuilder())
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', 'status; rm -rf /tmp/should-not-exist')
    assert builder_main.main() == 0
    result = stdout_json(capsys)
    assert result['ok'] is False and result['code'] == 'bad_request'
    # shlex.split keeps 'status;' as one token, which is not in the allowlist.
    assert '未知动词' in result['detail']
    assert not Path('/tmp/should-not-exist').exists()
    assert no_processes == []
    assert built == []


def test_a_quoted_argument_with_a_space_is_never_split_or_executed(tmp_path, monkeypatch, capsys, no_processes):
    wire(monkeypatch, tmp_path, lambda cfg: UnusedBuilder())
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', 'status "a b"')
    # REAL BEHAVIOUR, and it contradicts the requested expectation: shlex groups
    # "a b" into ONE argv element, so len(args) == 1 and this is NOT "参数过多".
    # It is refused one layer later as a single invalid base64 payload (GateError
    # -> exit 1, no JSON on stdout). It never reaches a shell either way.
    assert builder_main.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'base64' in captured.err
    assert no_processes == []


def test_a_quoted_extra_argument_is_refused_as_too_many(tmp_path, monkeypatch, capsys, no_processes):
    built = wire(monkeypatch, tmp_path, lambda cfg: UnusedBuilder())
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', 'status "a b" "c d"')
    assert builder_main.main() == 0
    result = stdout_json(capsys)
    assert result['ok'] is False and result['code'] == 'bad_request'
    assert '参数过多' in result['detail']
    assert no_processes == [] and built == []


def test_a_window_refusal_is_json_on_stdout_with_exit_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(builder_main, 'BuilderConfig', lambda: DispatcherConfig(tmp_path))
    monkeypatch.setattr(builder_main, 'Builder',
                        lambda cfg: FakeBuilder(error=Refused(CLOSED_REASON, 'not_now')))
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', 'status')
    assert builder_main.main() == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {'ok': False, 'code': 'not_now', 'detail': CLOSED_REASON}
    assert CLOSED_REASON in captured.err


def test_a_successful_verb_result_is_emitted_as_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(builder_main, 'BuilderConfig', lambda: DispatcherConfig(tmp_path))
    monkeypatch.setattr(builder_main, 'Builder',
                        lambda cfg: FakeBuilder(result={'ok': True, 'host': 'builder-test'}))
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', 'status')
    assert builder_main.main() == 0
    assert json.loads(capsys.readouterr().out) == {'ok': True, 'host': 'builder-test'}


def test_a_non_numeric_job_id_is_refused_by_the_dispatcher(tmp_path, monkeypatch, capsys):
    # Regression guard for the dispatcher consequence: a malformed job_id used to
    # escape as ValueError, which __main__ mapped to the crash path -- exit 3,
    # CRASH_MESSAGE, crash.log. A bad request must be an ordinary refusal instead.
    monkeypatch.setattr(builder_main, 'BuilderConfig', lambda: DispatcherConfig(tmp_path))
    monkeypatch.setattr(builder_main, 'Builder', lambda cfg: Builder(cfg, repo=ForbiddenRepo()))
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND',
                       'candidate ' + transport.encode(candidate_payload(job_id='abc')))
    assert builder_main.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'job_id' in captured.err
    assert not (tmp_path/'state'/'crash.log').exists()


# --- E. the single-instance build lock -------------------------------------

def test_the_build_lock_refuses_a_second_holder_and_releases_on_exit(tmp_path):
    path = tmp_path/'state'/'build.lock'
    # Platform caveat: BuildLock takes an exclusive lock with msvcrt.locking
    # (LK_NBLCK) on Windows and fcntl.flock (LOCK_EX|LOCK_NB) elsewhere, and turns
    # the OSError into GateError. On Windows an overlapping lock requested through a
    # second handle -- even in the same process -- is refused by the OS, so the
    # second acquire raises here exactly as it does on the Linux builder. This is
    # asserted, not skipped: a silent skip would hide a regression on either side.
    with BuildLock(path):
        assert path.is_file()
        with pytest.raises(GateError) as caught:
            with BuildLock(path):
                pass
        assert '构建机正忙' in str(caught.value)
    # The outer lock is gone, so a later build may take it again.
    with BuildLock(path):
        pass
    with BuildLock(path):
        pass
