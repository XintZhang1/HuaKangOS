"""The XC staff tool must stay tied to the trial world, refuse non-local targets and leak no secrets."""
import importlib.util
import json
import typing
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('xc_staff_tool', ROOT / 'scripts/create_xc_staff.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class StubClient:
    """Stands in for the running preview; records exactly what would be sent."""

    def __init__(self, existing=(), fail_for=()):
        self.existing = [dict(row) if isinstance(row, dict) else {'username': row, 'role': None}
                         for row in existing]
        self.fail_for = set(fail_for)
        self.created = []

    def users(self):
        return list(self.existing)

    def create_user(self, store_id, row, password, store_role):
        if row['username'] in self.fail_for:
            raise tool.PreviewError('422 该登录账号已存在')
        self.created.append({'store_id': store_id, 'row': dict(row), 'password': password,
                             'store_role': store_role})


def test_staff_rows_come_from_the_trial_world():
    world = json.loads((ROOT / 'docs/trial-source/world.json').read_text('utf-8-sig'))
    staff = tool.load_staff()
    assert staff == [{'username': a['username'], 'display_name': a['display_name'], 'role': a['role'],
                      'store': a['store'], 'purpose': a['purpose']}
                     for a in world['accounts'] if a['role'] != 'admin']
    assert len(staff) == 9
    assert {row['store'] for row in staff} == {'XC-CD'}


def test_staff_roles_are_valid_store_roles_for_the_account_api():
    from app.schemas import StoreRole
    assert set(row['role'] for row in tool.load_staff()) <= set(typing.get_args(StoreRole))


def test_only_loopback_http_previews_are_accepted():
    assert tool.check_base('http://127.0.0.1:8000') == 'http://127.0.0.1:8000'
    assert tool.check_base('http://localhost:8123/') == 'http://localhost:8123'
    assert tool.check_base('http://[::1]:9000') == 'http://[::1]:9000'
    for refused in ('http://10.0.0.5:8000', 'https://preview.example.com', 'http://0.0.0.0:8000',
                    'file:///c:/preview.sqlite', 'http://127.0.0.1'):
        with pytest.raises(tool.PreviewError):
            tool.check_base(refused)


def test_a_non_preview_server_is_refused_before_any_login():
    class NotPreview(tool.PreviewClient):
        def request(self, method, path, payload=None, headers=None):
            return {'status': 'ok'}

    with pytest.raises(tool.PreviewError):
        NotPreview('http://127.0.0.1:8000').status()


def test_only_missing_accounts_are_created_with_the_store_role():
    client = StubClient(existing=[{'username': 'xc-sales', 'role': 'sales', 'active': True, 'stores': [{'id': 7}]}])
    store = {'id': 7, 'name': '星驰汽车城东店', 'code': 'XC-CD'}
    results = tool.run(client, store, tool.load_staff(), 'Xc-Trial-Password-01', reporter=lambda *_: None)
    assert [row['result'] for row in results].count('created') == 8
    assert [row['result'] for row in results].count('skipped') == 1
    assert all(item['store_id'] == 7 and item['store_role'] == item['row']['role'] for item in client.created)
    assert all(item['row']['username'] != 'xc-sales' for item in client.created)


@pytest.mark.parametrize('existing,expected', [
    ({'username': 'xc-sales', 'role': 'manager', 'active': True, 'stores': [{'id': 7}]}, '岗位为 manager'),
    ({'username': 'xc-sales', 'role': 'sales', 'active': False, 'stores': [{'id': 7}]}, '账号已停用'),
    ({'username': 'xc-sales', 'role': 'sales', 'active': True, 'stores': [{'id': 9}]}, '未分配到本次门店'),
])
def test_an_existing_account_with_a_different_configuration_is_reported(existing, expected):
    """R01 asks for one manual account first; a typo there must not pass silently."""
    client = StubClient(existing=[existing])
    store = {'id': 7, 'name': '星驰汽车城东店', 'code': 'XC-CD'}
    results = tool.run(client, store, tool.load_staff(), 'Xc-Trial-Password-01', reporter=lambda *_: None)
    conflicts = [row for row in results if row['result'] == 'conflict']
    assert len(conflicts) == 1 and conflicts[0]['username'] == 'xc-sales'
    assert expected in conflicts[0]['note']
    assert all(item['row']['username'] != 'xc-sales' for item in client.created)


def test_the_default_base_follows_this_candidates_recorded_port(monkeypatch, tmp_path):
    import json as jsonlib
    assert tool.repository_id() == tool.repository_id().lower() and len(tool.repository_id()) == 20
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    assert tool.recorded_preview_base() == tool.DEFAULT_BASE          # nothing recorded yet
    directory = tmp_path / 'huakangos' / ('preview-' + tool.repository_id())
    directory.mkdir(parents=True)
    (directory / 'process.json').write_text(jsonlib.dumps({'port': 8123}), encoding='utf-8')
    assert tool.recorded_preview_base() == 'http://127.0.0.1:8123'


def test_a_preview_belonging_to_another_source_tree_is_refused():
    class OtherCandidate(tool.PreviewClient):
        def request(self, method, path, payload=None, headers=None):
            return {'local_preview': True, 'bootstrap_required': False, 'repository_id': 'deadbeefdeadbeefdead',
                    'instance_id': 'x'}
    client = OtherCandidate('http://127.0.0.1:8000')
    state = client.status('')                                          # no expectation: allowed
    assert state['repository_id'] == 'deadbeefdeadbeefdead'
    with pytest.raises(tool.PreviewError) as refused:
        client.status(tool.repository_id())
    assert '属于另一份源码' in str(refused.value)


def test_one_failure_does_not_stop_the_others_and_is_reported():
    client = StubClient(fail_for={'xc-tech'})
    store = {'id': 1, 'name': '星驰汽车城东店', 'code': 'XC-CD'}
    results = tool.run(client, store, tool.load_staff(), 'Xc-Trial-Password-01', reporter=lambda *_: None)
    failed = [row for row in results if row['result'] == 'failed']
    assert [row['username'] for row in failed] == ['xc-tech']
    assert '422' in failed[0]['note']
    assert [row['result'] for row in results].count('created') == 8


def test_dry_run_writes_nothing():
    client = StubClient()
    store = {'id': 1, 'name': '星驰汽车城东店', 'code': 'XC-CD'}
    results = tool.run(client, store, tool.load_staff(), '', dry_run=True, reporter=lambda *_: None)
    assert client.created == []
    assert {row['result'] for row in results} == {'planned'}


def test_the_initial_password_never_enters_results_or_output():
    sentinel = 'Xc-Trial-Password-DoNotPrint'
    printed = []
    client = StubClient()
    store = {'id': 3, 'name': '星驰汽车城东店', 'code': 'XC-CD'}
    results = tool.run(client, store, tool.load_staff(), sentinel, reporter=lambda text='': printed.append(str(text)))
    assert sentinel not in json.dumps(results, ensure_ascii=False)
    assert sentinel not in ''.join(printed)
    assert all(item['password'] == sentinel for item in client.created)


def test_passwords_cannot_be_passed_on_the_command_line():
    parser = tool.build_parser()
    assert not any(action.dest == 'password' for action in parser._actions)
    assert '--password' not in parser.format_help()


def test_store_resolution_prefers_the_trial_code_then_the_only_store_then_asks():
    trial = {'id': 1, 'name': '星驰汽车城东店', 'code': 'XC-CD', 'active': True}
    other = {'id': 2, 'name': '星驰汽车城西店', 'code': 'XC-CX', 'active': True}
    store, why = tool.resolve_store([other, trial], 'XC-CD')
    assert store['id'] == 1 and '编码' in why
    store, why = tool.resolve_store([other], 'XC-CD', interactive=False)
    assert store['id'] == 2 and '只有一家' in why
    with pytest.raises(tool.PreviewError):
        tool.resolve_store([trial, other], 'XC-XX', interactive=False)
    store, why = tool.resolve_store([trial, other], 'XC-XX', ask=lambda _: '2')
    assert store['id'] == 2 and '选择' in why
    with pytest.raises(tool.PreviewError):
        tool.resolve_store([], 'XC-CD')


def test_inactive_stores_are_not_used_for_new_accounts():
    active = {'id': 1, 'name': '星驰汽车城东店', 'code': 'XC-CD', 'active': True}
    closed = {'id': 9, 'name': '已停用门店', 'code': 'OLD', 'active': False}
    store, _ = tool.resolve_store([closed, active], 'XC-CD')
    assert store['id'] == 1
    with pytest.raises(tool.PreviewError):
        tool.resolve_store([closed], 'XC-CD', interactive=False)
