"""构建机传输层测试：无网络、无 SSH、无真实凭据，全部是假 runner。

transport 的安全主张只有一条：请求永远只是「一个 argv 元素」——ssh 的
key/port/user/host 各自独立，最后一项是 `verb base64(json)` 这整条强制命令。
实测形状：令牌是最后一项的第二个词，不是独立元素；倒数第二项是 user@host。
模型产出的元字符既不会在本机被 shell 解释，也不会在对端被解释。
"""
import base64
import io
import json
import subprocess
from types import SimpleNamespace
import pytest
from maintenance.config import GateError
from maintenance.transport import (BuilderClient, MAX_PAYLOAD, NotNow, STDERR_TAIL, VERBS,
    decode, encode)

BASE='a'*40;HEAD='b'*40;BRANCH='maint/2026-01-01-abc';KEY='/home/ops/.ssh/builder_ed25519'
HOSTILE={'note':'"; rm -rf / #','cmd':'$(whoami)','multi':'第一行\n第二行','tick':'`id`','and':'&& curl http://evil.example'}


def cfg(**overrides):
    values={'sg_key':KEY,'sg_port':2222,'sg_user':'huakang','sg_host':'builder.example','sg_timeout':900}
    values.update(overrides);return SimpleNamespace(**values)


def words(argv):
    """argv 的真实形状：最后一项是 `verb base64`，令牌是它的第二个词。"""
    return argv[-1].split(' ')


def token_of(argv):
    return words(argv)[1]


class FakeRunner:
    """subprocess.run 的替身：记录 argv/kwargs，返回预设字节或抛预设异常。"""
    def __init__(self,stdout=b'{"ok": true, "value": 3}',stderr=b'',returncode=0,fail=None):
        self.stdout=stdout;self.stderr=stderr;self.returncode=returncode;self.fail=fail;self.calls=[]
    def __call__(self,argv,**kwargs):
        self.calls.append((list(argv),kwargs))
        if self.fail is not None:raise self.fail
        return SimpleNamespace(returncode=self.returncode,stdout=self.stdout,stderr=self.stderr)


def build(runner=None,**overrides):
    runner=FakeRunner() if runner is None else runner
    return BuilderClient(cfg(**overrides),runner=runner),runner


def fake_pipe(data=b''):
    class Pipe(io.BytesIO):
        def close(self):pass  # 传输层会关掉写端；假管道保留字节供断言
    pipe=Pipe(data);pipe.seek(0);return pipe


class FakeProc:
    def __init__(self,argv,stdout=b'',stderr=b'',returncode=0,timeout=False,call_kwargs=None):
        self.argv=list(argv);self.kwargs=call_kwargs or {};self.returncode=returncode;self.killed=False;self.timeout=timeout
        self.stdout=fake_pipe(stdout);self.stderr=fake_pipe(stderr)
    def communicate(self,timeout=None):
        if self.timeout:raise subprocess.TimeoutExpired(cmd=self.argv[0],timeout=timeout)
        return self.stdout.getvalue(),self.stderr.getvalue()
    def wait(self,timeout=None):return self.returncode
    def kill(self):self.killed=True


class FakePopen:
    """两次 Popen 调用：第一次是构建机 ssh，第二次是本机 docker load。"""
    def __init__(self,source_out=b'',source_err=b'',source_rc=0,loaded=b'',sink_rc=0,fail_at=None,sink_timeout=False):
        self.source_out=source_out;self.source_err=source_err;self.source_rc=source_rc
        self.loaded=loaded;self.sink_rc=sink_rc;self.fail_at=fail_at;self.sink_timeout=sink_timeout;self.procs=[]
    def __call__(self,argv,**kwargs):
        if len(self.procs)==self.fail_at:raise OSError('docker/ssh 不可用')
        first=not self.procs
        proc=FakeProc(argv,stdout=self.source_out if first else self.loaded,stderr=self.source_err if first else b'',
            returncode=self.source_rc if first else self.sink_rc,timeout=(not first) and self.sink_timeout,call_kwargs=kwargs)
        self.procs.append(proc);return proc


# --- 1. 编解码往返 --------------------------------------------------------

@pytest.mark.parametrize('payload',[
    {'a':1,'b':[1,2,{'c':None}]},
    {'ok':True,'no':False,'nothing':None},
    ['列表',{'中文键':'中文值'},None,True],
    {'空字符串':'','emoji':'🚀','引号':'"\'`'},
    {}])
def test_encode_decode_round_trip(payload):
    token=encode(payload)
    assert isinstance(token,str) and token==token.strip()
    assert decode(token)==payload


def test_encode_is_ascii_text_never_multiline():
    token=encode({'中文':'值\n换行','x':'\x00'})
    token.encode('ascii')  # 必须是纯 ASCII：argv 里不允许出现裸字节/换行
    assert not any(ch.isspace() for ch in token)
    assert decode(token)=={'中文':'值\n换行','x':'\x00'}


# --- 2. decode 拒绝非法载荷（并如实记录 json 标量会被接受） ---------------

@pytest.mark.parametrize('token',['','!!!!','not base64 at all',
    base64.b64encode(b'not json').decode('ascii'),
    base64.b64encode(b'\xff\xfe\xfa').decode('ascii'),
    None,5,['x'],b'eyJhIjoxfQ=='],ids=['empty','junk','plain-text','not-json','bad-utf8','none','int','list','bytes'])
def test_decode_rejects_empty_junk_or_wrong_type(token):
    with pytest.raises(GateError):decode(token)


def test_decode_rejects_an_over_long_token():
    # 超长令牌在 base64 解码之前就被拒绝（上限是 MAX_PAYLOAD*2）。
    with pytest.raises(GateError):decode('A'*(MAX_PAYLOAD*2+1))
    with pytest.raises(GateError):decode('A'*(MAX_PAYLOAD*2+4))


def test_decode_accepts_a_bare_json_scalar():
    # json.loads 接受标量，所以「严格 base64(JSON)」约束的是编码而不是取值形状：
    # b'5' 确实会解码成 5。如实钉住真实行为，避免有人误以为这里只放行 dict。
    assert decode(base64.b64encode(b'5').decode('ascii'))==5
    assert decode(base64.b64encode(b'[1,2]').decode('ascii'))==[1,2]
    assert decode(base64.b64encode(b'null').decode('ascii')) is None


# --- 3. encode 超预算 -----------------------------------------------------

def test_encode_refuses_a_payload_over_the_budget():
    with pytest.raises(GateError):encode({'text':'x'*MAX_PAYLOAD})
    with pytest.raises(GateError):encode({'text':'中'*MAX_PAYLOAD})  # 按 UTF-8 字节数算
    inside={'text':'x'*(MAX_PAYLOAD-64)}
    assert decode(encode(inside))==inside  # 预算内的正常请求不受影响


# --- 4. argv 形状：一个 ssh 调用，整条强制命令在最后 ----------------------

def test_argv_is_one_ssh_invocation_with_the_command_last():
    token=encode({'x':1});client,_=build()
    argv=client.argv('publish',token)
    assert argv[0]=='ssh'
    assert argv[-2]=='huakang@builder.example'          # 倒数第二项是主机
    assert argv[-1]=='publish '+token                   # 最后一项是整条强制命令
    assert words(argv)==['publish',token]               # 令牌是它的第二个词
    assert token not in argv                            # 令牌不是独立 argv 元素
    assert argv[argv.index('-i')+1]==KEY
    assert argv[argv.index('-p')+1]=='2222'
    assert argv[argv.index('-o')+1]=='BatchMode=yes'
    assert argv[argv.index('StrictHostKeyChecking=yes')-1]=='-o'


def test_argv_without_a_token_has_nothing_appended():
    argv=build()[0].argv('status')
    assert argv[-1]=='status' and not any(' ' in a for a in argv)


def test_argv_never_splits_or_glues_a_second_command():
    token=encode({'x':1});argv=build()[0].argv('status',token)
    # 只有最后一个元素含空格：动词与 base64 令牌之间那一个空格，不是 shell 分隔
    assert [a for a in argv if ' ' in a]==[argv[-1]]
    assert argv[-1].count(' ')==1
    assert [a for a in argv if token in a]==[argv[-1]]
    # ssh 的每个选项都是独立元素，绝没有 "-o BatchMode=yes" 这种拼接
    assert not any(a.startswith('-o ') or 'BatchMode=yes -o' in a for a in argv)
    assert not any(ch in ' '.join(argv[:-1]) for ch in [';','|','&','$','`','\n'])


# --- 5. 未知动词 ----------------------------------------------------------

@pytest.mark.parametrize('verb',['deploy','Status','status; rm -rf /','status --force','','image ','/bin/sh','status\x00'])
def test_argv_refuses_unknown_verbs(verb):
    with pytest.raises(GateError):build()[0].argv(verb)


def test_declared_verb_interface_is_frozen():
    assert isinstance(VERBS,frozenset)
    assert VERBS==frozenset({'status','context','candidate','publish','revert','prune','image'})
    for verb in VERBS:build()[0].argv(verb)  # 声明的动词必须都可用


# --- 6-10. call 的结果与拒绝语义 ------------------------------------------

def test_call_returns_the_parsed_document_and_passes_a_strict_invocation():
    runner=FakeRunner(stdout=b'{"ok": true, "value": 3}')
    client,_=build(runner)
    assert client.call('status')=={'ok':True,'value':3}
    argv,kwargs=runner.calls[0]
    assert argv[-1]=='status'
    assert kwargs['stdin']==subprocess.DEVNULL and kwargs['stdout']==subprocess.PIPE and kwargs['stderr']==subprocess.PIPE
    assert kwargs['check'] is False and kwargs['timeout']==900  # 默认取 cfg.sg_timeout


def test_call_tolerates_utf8_and_trailing_whitespace():
    runner=FakeRunner(stdout='{"ok":true,"detail":"已完成"}\n'.encode('utf-8'))
    client,_=build(runner)
    assert client.prune()['detail']=='已完成'
    assert runner.calls[0][1]['timeout']==300  # prune 自带更长的预算


def test_call_raises_not_now_when_the_builder_declines_politely():
    out=json.dumps({'ok':False,'code':'not_now','detail':'窗口外'},ensure_ascii=False).encode('utf-8')
    client,_=build(FakeRunner(stdout=out))
    with pytest.raises(NotNow) as exc:client.call('publish',{'a':1})
    assert '窗口外' in str(exc.value)
    # 调用方必须能分开捕获这两种结果：NotNow 不是 GateError
    assert issubclass(NotNow,RuntimeError) and not issubclass(NotNow,GateError)


def test_call_maps_a_plain_refusal_to_a_gate_error_not_not_now():
    out='{"ok": false, "code": "refused", "detail": "base_sha 不是主分支当前提交"}'.encode('utf-8')
    client,_=build(FakeRunner(stdout=out))
    try:
        client.call('revert',{'a':1})
        pytest.fail('普通拒绝必须抛 GateError')
    except NotNow:pytest.fail('not_now 只用于窗口外/占用让行，普通拒绝不能走这条路')
    except GateError as exc:
        assert 'base_sha 不是主分支当前提交' in str(exc)


def test_call_reports_the_stderr_tail_on_failure():
    client,_=build(FakeRunner(returncode=3,stderr='  构建机内部错误：磁盘已满  '.encode('utf-8')))
    with pytest.raises(GateError) as exc:client.call('prune')
    message=str(exc.value)
    assert '磁盘已满' in message and 'prune' in message


def test_call_keeps_only_the_tail_of_a_long_stderr():
    text='HEADMARK'+'x'*2000+'TAIL'
    client,_=build(FakeRunner(returncode=3,stderr=text.encode('utf-8')))
    with pytest.raises(GateError) as exc:client.call('image')
    tail=str(exc.value).split('：',1)[1]
    assert tail.endswith('TAIL') and len(tail)==STDERR_TAIL and 'HEADMARK' not in tail


def test_call_mentions_the_exit_code_when_stderr_is_empty():
    client,_=build(FakeRunner(returncode=9,stderr=b'   \n  '))
    with pytest.raises(GateError) as exc:client.call('status')
    assert '退出码 9' in str(exc.value)


@pytest.mark.parametrize('stdout',[b'',b'   \n ',b'not json',b'<html>502 Bad Gateway</html>',b'[1,2,3]',b'"ok"',b'null'])
def test_call_refuses_an_empty_or_non_document_result(stdout):
    client,_=build(FakeRunner(stdout=stdout))
    with pytest.raises(GateError):client.call('status')


@pytest.mark.parametrize('fail',[
    subprocess.TimeoutExpired(cmd='ssh',timeout=900),
    FileNotFoundError('ssh 不存在'),
    OSError('no route to host')])
def test_call_maps_transport_failures_to_one_gate_error(fail):
    client,_=build(FakeRunner(fail=fail))
    with pytest.raises(GateError) as exc:client.call('publish',{'a':1})
    message=str(exc.value)
    assert '超时' in message or '不可达' in message
    assert '未执行任何发布动作' in message and 'publish' in message


# --- 12. 元字符只以 base64 形式出现 ---------------------------------------

def test_shell_metacharacters_stay_inside_one_opaque_base64_argument():
    client,_=build()
    token=encode(HOSTILE);argv=client.argv('publish',token)
    assert [a for a in argv if ' ' in a]==[argv[-1]]
    assert words(argv)==['publish',token]
    assert [a for a in argv if token in a]==[argv[-1]]
    assert decode(token_of(argv))==HOSTILE  # 原文一字不差地回来了
    base64.b64decode(token.encode('ascii'),validate=True)  # 令牌是纯 base64
    joined=' '.join(argv)
    for raw in [';','$(',')','`','&&','#','\n','rm -rf','whoami','curl http://evil.example','"']:
        assert raw not in joined


def test_call_sends_the_payload_only_as_the_encoded_argument():
    runner=FakeRunner();client,_=build(runner)
    client.call('candidate',HOSTILE)
    argv,kwargs=runner.calls[0]
    assert words(argv)[0]=='candidate'
    assert decode(token_of(argv))==HOSTILE
    assert 'rm -rf' not in ' '.join(argv) and 'whoami' not in ' '.join(argv)
    assert not any(HOSTILE['note'] in str(v) for v in kwargs.values())


# --- 包装方法：载荷字段必须与构建机约定一致 ------------------------------

@pytest.mark.parametrize('verb,invoke,payload',[
    ('status',lambda c:c.status(),None),
    ('context',lambda c:c.context(BASE),{'base_sha':BASE}),
    ('candidate',lambda c:c.candidate('42',BASE,BRANCH,{'summary':'x','risk':'low'}),
        {'job_id':42,'base_sha':BASE,'branch':BRANCH,'proposal':{'summary':'x','risk':'low'}}),
    ('publish',lambda c:c.publish(BASE,HEAD,BRANCH),{'base_sha':BASE,'head_sha':HEAD,'branch':BRANCH}),
    ('revert',lambda c:c.revert(BASE,HEAD,'7'),{'base_sha':BASE,'head_sha':HEAD,'job_id':7}),
    ('prune',lambda c:c.prune(),None)])
def test_wrappers_build_the_documented_payload(verb,invoke,payload):
    runner=FakeRunner();client,_=build(runner)
    invoke(client)
    argv,kwargs=runner.calls[0]
    if payload is None:
        assert argv[-1]==verb  # 无载荷：动词之后什么都没有
    else:
        assert words(argv)[0]==verb
        decoded=decode(token_of(argv))
        assert decoded==payload
        if verb in {'candidate','revert'}:assert type(decoded['job_id']) is int


def test_job_ids_are_normalised_to_int_and_bad_ones_fail_loudly():
    runner=FakeRunner();client,_=build(runner)
    client.candidate('0042',BASE,BRANCH,{})
    assert decode(token_of(runner.calls[0][0]))['job_id']==42
    # 非数字 job_id 抛的是 ValueError 而不是 GateError：任务号来自本地数据库，
    # 不会来自模型或飞书，所以这里选择「响亮地崩」；改动此行为需同步改测试。
    with pytest.raises(ValueError):client.revert(BASE,HEAD,'7; rm -rf /')


# --- 镜像流：ssh docker save | 本机 docker load ---------------------------

def test_stream_image_pipes_the_builder_save_straight_into_local_load():
    popen=FakePopen(loaded=b'Loaded image: dealerdesk-app:0.2\n')
    client=BuilderClient(cfg(),runner=FakeRunner(),popen=popen)
    assert 'Loaded image' in client.stream_image_into('dealerdesk-app:0.2')
    source,sink=popen.procs
    assert words(source.argv)[0]=='image'
    assert decode(token_of(source.argv))=={'image_tag':'dealerdesk-app:0.2'}
    assert sink.argv==['docker','load'] and sink.kwargs['stdin'] is source.stdout


def test_stream_image_accepts_an_explicit_load_argv_and_never_touches_disk():
    popen=FakePopen(loaded=b'ok')
    client=BuilderClient(cfg(),runner=FakeRunner(),popen=popen)
    client.stream_image_into('dealerdesk-app:0.2',load_argv=['docker','load','--quiet'],timeout=30)
    assert popen.procs[1].argv==['docker','load','--quiet']


@pytest.mark.parametrize('popen,word',[
    (FakePopen(source_rc=1,source_err=b'Error: No such image: dealerdesk-app:0.2'),'No such image'),
    (FakePopen(loaded=b'Error response from daemon: manifest unknown',sink_rc=1),'manifest unknown'),
    (FakePopen(sink_timeout=True),'超时')])
def test_stream_image_fails_closed_and_reports_why(popen,word):
    client=BuilderClient(cfg(),runner=FakeRunner(),popen=popen)
    with pytest.raises(GateError) as exc:client.stream_image_into('dealerdesk-app:0.2')
    assert word in str(exc.value)


def test_stream_image_kills_the_ssh_pipe_when_docker_load_cannot_start():
    popen=FakePopen(fail_at=1)
    client=BuilderClient(cfg(),runner=FakeRunner(),popen=popen)
    with pytest.raises(GateError) as exc:client.stream_image_into('dealerdesk-app:0.2')
    assert 'docker load' in str(exc.value) and popen.procs[0].killed