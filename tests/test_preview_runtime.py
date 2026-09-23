"""Launcher decisions use synthetic folders, sockets and controlled command results."""
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import uuid

import pytest
from app import preview_runtime as runtime

ROOT = Path(__file__).resolve().parents[1]


def powershell(tmp_path, commands):
    if os.name != 'nt':
        pytest.skip('Windows launcher contract')
    script = tmp_path / 'probe.ps1'
    script.write_text("$ErrorActionPreference='Stop'\nSet-StrictMode -Version Latest\n"
                      "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)\n"
                      ". '" + str(ROOT / 'scripts' / 'preview_launcher.ps1').replace("'", "''") + "'\n" + commands,
                      encoding='utf-8-sig')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(script)],
                            capture_output=True, encoding='utf-8', errors='replace', timeout=20,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_two_repository_folders_have_distinct_identity_and_identical_content_hash(tmp_path):
    first = tmp_path / '原目录'; second = tmp_path / '候选目录'
    (first / 'app').mkdir(parents=True)
    (first / 'app' / 'main.py').write_text('original', encoding='utf-8')
    shutil.copytree(first, second)
    a, b = runtime.source_identity(first), runtime.source_identity(second)
    assert a['repository_id'] != b['repository_id']
    assert a['source_fingerprint'] == b['source_fingerprint']
    assert runtime.source_identity(first / 'app' / '..') == a
    (second / 'app' / '__pycache__').mkdir()
    (second / 'app' / '__pycache__' / 'runtime.pyc').write_bytes(b'cache')
    assert runtime.source_identity(second) == b
    (second / 'app' / 'main.py').write_text('modified', encoding='utf-8')
    assert runtime.source_identity(second)['source_fingerprint'] != b['source_fingerprint']


def test_powershell_and_python_directory_identity_match(tmp_path):
    target = tmp_path / '含空格 source'; target.mkdir()
    result = powershell(tmp_path, "Get-PreviewRepositoryId '" + str(target).replace("'", "''") + "' | ConvertTo-Json")
    assert result == runtime.source_identity(target)['repository_id']


@pytest.mark.parametrize('field,value', [('repository_id', 'different'),
                                      ('source_fingerprint', 'old-code'),
                                      ('instance_id', 'another-instance'),
                                      ('local_preview', False)])
def test_running_instance_cannot_be_relabelled(tmp_path, field, value):
    health = {'local_preview': True, 'instance_id': 'instance', 'repository_id': 'repo', 'source_fingerprint': 'code'}
    health[field] = value
    serialized = json.dumps(health)
    result = powershell(tmp_path, "$health = '" + serialized + "' | ConvertFrom-Json\n"
                        "$manifest = [pscustomobject]@{instance_id='instance'}\n"
                        "$identity = [pscustomobject]@{repository_id='repo';source_fingerprint='code'}\n"
                        "$refused=$false;try { Assert-PreviewIdentity $health $manifest $identity } catch { $refused=$true }\n"
                        "@{refused=$refused;health=$health} | ConvertTo-Json -Depth 4")
    assert result['refused'] is True
    assert result['health'] == health


def test_identical_running_instance_is_reusable(tmp_path):
    assert powershell(tmp_path, """
$identity=[pscustomobject]@{repository_id='repo';source_fingerprint='code'}
$health=[pscustomobject]@{repository_id='repo';source_fingerprint='code';instance_id='instance';local_preview=$true}
Assert-PreviewIdentity $health ([pscustomobject]@{instance_id='instance'}) $identity
$true | ConvertTo-Json
""") is True


def test_occupied_default_port_advances_and_explicit_port_refuses(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen()
        port = listener.getsockname()[1]
        result = powershell(tmp_path, f"""
$automatic=Select-PreviewPort {port} $false
$refused=$false;try {{ Select-PreviewPort {port} $true | Out-Null }} catch {{ $refused=$true }}
@{{automatic=$automatic;refused=$refused}} | ConvertTo-Json
""")
        assert port < result['automatic'] <= 65535
        assert result['refused'] is True


def test_partial_install_failure_is_retried_on_next_launch(tmp_path):
    result = powershell(tmp_path, r"""
$script:results=[Collections.Generic.Queue[int]]::new()
# First launch: valid Python, missing imports, failed install. Next launch repairs it.
@(0,1,1,0,1,0,0) | ForEach-Object {$script:results.Enqueue($_)}
$script:calls=@()
function Invoke-PreviewPython([string]$Python,[string[]]$Arguments,[string]$Log) {
    $script:calls += ($Arguments -join ' ')
    return $script:results.Dequeue()
}
$refused=$false;try {Ensure-PreviewDependencies 'python' 'C:\synthetic' 'test.log'} catch {$refused=$true}
Ensure-PreviewDependencies 'python' 'C:\synthetic' 'test.log'
@{refused=$refused;remaining=$script:results.Count;calls=$script:calls} | ConvertTo-Json
""")
    assert result['refused'] is True and result['remaining'] == 0
    assert len([call for call in result['calls'] if 'pip install' in call]) == 2


def test_wrong_python_version_never_installs_dependencies(tmp_path):
    result = powershell(tmp_path, r"""
$script:calls=0
function Invoke-PreviewPython([string]$Python,[string[]]$Arguments,[string]$Log) {$script:calls++;return 1}
$refused=$false;try {Ensure-PreviewDependencies 'python' 'C:\synthetic' 'test.log'} catch {$refused=$true}
@{refused=$refused;calls=$script:calls} | ConvertTo-Json
""")
    assert result == {'refused': True, 'calls': 1}


def test_dependency_checker_rejects_missing_wrong_and_unimportable(tmp_path, monkeypatch):
    (tmp_path / 'requirements.txt').write_text('present==1\nwrong==2\nmissing==3\n', encoding='utf-8')
    def version(name):
        if name == 'missing':
            raise runtime.metadata.PackageNotFoundError(name)
        return '1'
    monkeypatch.setattr(runtime.metadata, 'version', version)
    monkeypatch.setattr(runtime, 'IMPORTS', ('good', 'broken'))
    def load(name):
        if name == 'broken':
            raise ImportError('synthetic failure')
    monkeypatch.setattr(runtime.importlib, 'import_module', load)
    assert runtime.dependency_problems(tmp_path) == ['wrong 版本不匹配', 'missing 尚未安装', 'broken 无法加载']


@pytest.mark.parametrize('partial_database', [False, True])
def test_interrupted_initial_prepare_preserves_files_and_new_directory_works(tmp_path, partial_database):
    leftover = tmp_path / 'huakangos' / 'interrupted'; leftover.mkdir(parents=True)
    (leftover / 'preview.json').write_text(json.dumps({'instance_id': str(uuid.uuid4()), 'schema': 1}), encoding='utf-8')
    if partial_database:
        with sqlite3.connect(leftover / 'preview.sqlite') as conn:
            conn.execute('CREATE TABLE unfinished_example(id INTEGER PRIMARY KEY)')
    before = {p.name: p.read_bytes() for p in leftover.iterdir()}
    env = {**os.environ, 'LOCALAPPDATA': str(tmp_path), 'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1'}
    def prepare(directory):
        return subprocess.run([sys.executable, '-m', 'app.local_preview', 'prepare', '--root', str(directory)],
                              cwd=ROOT, env=env, capture_output=True, encoding='utf-8', timeout=90,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    refused = prepare(leftover)
    assert refused.returncode != 0
    assert 'start-preview.ps1 -DataDirectory' in refused.stderr
    assert '现有资料已保留' in refused.stderr
    assert {p.name: p.read_bytes() for p in leftover.iterdir()} == before
    fresh = tmp_path / 'huakangos' / 'new-independent-preview'
    result = prepare(fresh)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['bootstrap_required'] is True
    with sqlite3.connect(fresh / 'preview.sqlite') as conn:
        assert conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
        assert conn.execute("SELECT value FROM app_metadata WHERE key='huakangos_local_preview'").fetchone()
    assert {p.name: p.read_bytes() for p in leftover.iterdir()} == before
