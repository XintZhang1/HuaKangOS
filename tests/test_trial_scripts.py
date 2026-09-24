"""The XC trial scripts must keep matching the real catalogue, roles, routes and search index."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('trial_guide_builder', ROOT / 'scripts/build_trial_guides.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def source_with_change(monkeypatch, name, change):
    original = builder.read

    def read(path):
        value = original(path)
        if Path(path).name == name:
            value = copy.deepcopy(value)
            change(value)
        return value

    monkeypatch.setattr(builder, 'read', read)


def test_41_rounds_cover_every_colon_group_and_all_193_requirements():
    data = builder.make_data()
    assert len(data['rounds']) == 41
    assert [item['id'] for item in data['rounds']] == ['R%02d' % n for n in range(1, 42)]
    assert {(item['module'], item['group']) for item in data['rounds']} == set(data['groups'])
    assert len(data['requirements']) == 193
    covered = [row['id'] for item in data['rounds'] for row in item['requirements']]
    assert sorted(covered) == ['HK-%03d' % n for n in range(1, 194)]
    assert all(item['workflows'] for item in data['rounds'])
    assert all(item['prerequisites'] and item['scenario'] for item in data['rounds'])


def test_builder_roles_match_the_application_catalogue():
    from app.security import ROLES
    assert set(ROLES) == builder.ROLES


def test_world_logins_are_unique_and_use_known_roles():
    world = builder.read(builder.SOURCE / 'world.json')
    logins = [account['username'] for account in world['accounts']]
    assert len(logins) == len(set(logins))
    assert {account['role'] for account in world['accounts']} <= builder.ROLES
    assert {'admin', 'manager', 'sales', 'inventory', 'service', 'technician', 'finance',
            'auditor', 'reception', 'customer_service'} == {account['role'] for account in world['accounts']}


def test_search_terms_in_scripts_reach_the_named_workflow():
    data = builder.make_data()
    checked = 0
    for item in data['rounds']:
        for step in item.get('steps') or []:
            if not step['search']:
                continue
            checked += 1
            workflow = data['workflows'][step['workflow']]
            assert builder.search_hits(step['search'], workflow, data['requirements']), step['no']
    assert checked >= 4, 'the ready round must exercise the search box'


def test_every_ready_round_offers_a_search_entry():
    for item in builder.make_data()['detailed']:
        assert any(step['search'] for step in item['steps']), item['id']


def test_a_search_word_leading_elsewhere_is_rejected(monkeypatch):
    def change(rounds):
        for item in rounds['rounds']:
            for step in item.get('steps') or []:
                if step['search'] == '操作记录':
                    step['search'] = '客户'
    source_with_change(monkeypatch, 'rounds.json', change)
    with pytest.raises(AssertionError):
        builder.make_data()


def test_an_invented_search_word_is_rejected(monkeypatch):
    def change(rounds):
        for item in rounds['rounds']:
            for step in item.get('steps') or []:
                if step['search'] == '门店设置':
                    step['search'] = '量子传送门'
    source_with_change(monkeypatch, 'rounds.json', change)
    with pytest.raises(AssertionError):
        builder.make_data()


def test_an_invented_page_route_is_rejected(monkeypatch):
    def change(rounds):
        for item in rounds['rounds']:
            for step in item.get('steps') or []:
                if step['route'] == 'stores':
                    step['route'] = 'secret-admin'
    source_with_change(monkeypatch, 'rounds.json', change)
    with pytest.raises(AssertionError):
        builder.make_data()


def test_a_sub_page_of_a_real_page_is_accepted(monkeypatch):
    """The front end dispatches on the first segment: dictionaries/public, masters/suppliers."""
    def change(rounds):
        for item in rounds['rounds']:
            for step in item.get('steps') or []:
                if step['route'] == 'stores':
                    step['route'] = 'stores/some-sub-page'
    source_with_change(monkeypatch, 'rounds.json', change)
    assert builder.make_data()


def test_sub_page_keys_exist_in_the_real_catalogues():
    """A sub-page must name a real group/kind, not just a real root."""
    from types import SimpleNamespace
    from app.dictionary_api import DICTIONARIES
    from app.master_data import public_catalog
    kinds = set(public_catalog(SimpleNamespace(role='admin'))['kinds'])
    checked = 0
    for item in builder.make_data()['rounds']:
        for step in item.get('steps') or []:
            parts = step['route'].split('/')
            if len(parts) != 2:
                continue
            checked += 1
            root, key = parts
            if root == 'dictionaries':
                assert key in DICTIONARIES, step['no']
            elif root == 'masters':
                assert key in kinds, step['no']
    assert checked >= 3, 'the ready rounds must exercise sub-pages'


def test_an_unknown_account_or_role_is_rejected(monkeypatch):
    def change(rounds):
        for item in rounds['rounds']:
            for step in item.get('steps') or []:
                if step['account'] == 'xc-sales':
                    step['account'] = 'xc-outsider'
    source_with_change(monkeypatch, 'rounds.json', change)
    with pytest.raises(AssertionError):
        builder.make_data()


def test_a_detailed_round_without_steps_or_observations_is_rejected(monkeypatch):
    for field in ('steps', 'observations', 'checks', 'data'):
        def change(rounds, field=field):
            for item in rounds['rounds']:
                if item['status'] == 'detailed':
                    item.pop(field, None)
        source_with_change(monkeypatch, 'rounds.json', change)
        with pytest.raises(AssertionError):
            builder.make_data()


def test_a_round_claiming_an_unknown_group_is_rejected(monkeypatch):
    def change(rounds):
        rounds['rounds'][1]['group'] = '并不存在的分组'
    source_with_change(monkeypatch, 'rounds.json', change)
    with pytest.raises(AssertionError):
        builder.make_data()


def test_the_same_group_cannot_be_trialled_twice(monkeypatch):
    def change(rounds):
        rounds['rounds'][1]['group'] = rounds['rounds'][0]['group']
        rounds['rounds'][1]['module'] = rounds['rounds'][0]['module']
    source_with_change(monkeypatch, 'rounds.json', change)
    with pytest.raises(AssertionError):
        builder.make_data()


def test_committed_scripts_match_their_sources():
    builder.build(check=True)


def test_the_portable_page_carries_every_ready_round():
    text = builder.page(builder.make_data())
    assert text.startswith('<!doctype html>')
    assert 'XC 逐轮试用脚本' in text
    for item in builder.make_data()['detailed']:
        assert 'id="%s"' % item['id'] in text
