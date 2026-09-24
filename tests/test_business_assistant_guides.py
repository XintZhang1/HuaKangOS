"""The assistant may look up published help, and only published help."""
import asyncio
from types import SimpleNamespace

import pytest

from app import business_assistant_guides as guides
from app.business_assistant_service import SYSTEM_PROMPT, TOOLS, run_tools


def find(query, role='admin', category=''):
    return guides.search(query, role, category)


def test_employee_account_question_finds_the_real_entry_and_roles():
    items = find('员工账号')
    assert items and items[0]['workflow_id'] == 'wf-employee-store-roles'
    top = items[0]
    assert top['entry']['route'] == 'users' and top['entry']['can_enter'] is True
    assert top['steps'] and any('批量新增员工' in step['action'] for step in top['steps'])
    assert any('密码' in note for note in top['prerequisites'])


def test_the_batch_button_wording_also_finds_it():
    assert find('批量新增员工')[0]['workflow_id'] == 'wf-employee-store-roles'
    assert find('批量建账号')[0]['workflow_id'] == 'wf-employee-store-roles'


@pytest.mark.parametrize('query,expected', [
    ('门店设置', 'wf-store-management'),
    ('修改密码', 'wf-parameters-password-brand'),
    ('操作记录', 'wf-audit-business-history'),
    ('申请跨店协同', 'wf-cross-store-service-history'),
])
def test_other_system_management_questions_reach_their_own_guide(query, expected):
    assert find(query)[0]['workflow_id'] == expected


def test_a_non_administrator_sees_the_same_guide_but_not_a_usable_entry():
    items = find('员工账号', role='sales')
    top = items[0]
    assert top['workflow_id'] == 'wf-employee-store-roles'
    assert top['entry']['can_enter'] is False and '系统管理员' in top['entry']['role_note']
    assert guides.find_workflows('员工账号', 'sales')['items'][0]['next'] == top['entry']['role_note']


def test_the_administrator_gets_an_instruction_to_point_at_the_page():
    result = guides.find_workflows('员工账号', 'admin')
    assert result['items'][0]['entry']['can_enter'] is True
    assert '只指路' in result['items'][0]['next']


def test_an_unknown_question_says_so_without_inventing_an_entry():
    result = guides.find_workflows('量子传送门', 'admin')
    assert result['items'] == [] and '没有匹配' in result['notice']


def test_category_narrows_the_same_catalogue():
    items = find('新增', category='系统管理')
    assert items and all(item['category'] == '系统管理' for item in items)


def test_help_results_carry_no_business_fields():
    allowed = {'workflow_id', 'title', 'category', 'summary', 'entry', 'prerequisites', 'steps',
               'assistant_note', 'exceptions', 'completion', 'next'}
    for item in find('维修工单'):
        assert set(item) <= allowed
        assert all(key in {'label', 'route', 'mode', 'roles', 'can_enter', 'role_note'} for key in item['entry'])


def test_the_tool_is_registered_and_reachable():
    names = [item['function']['name'] for item in TOOLS]
    assert 'find_workflows' in names
    assert 'find_workflows' in SYSTEM_PROMPT


def test_the_tool_returns_help_through_the_normal_dispatcher():
    result = asyncio.run(run_tools(None, None, SimpleNamespace(role='admin'), None,
                                   'find_workflows', {'query': '员工账号'}, None))
    assert result['items'][0]['workflow_id'] == 'wf-employee-store-roles'


def test_unsupported_arguments_are_refused():
    with pytest.raises(Exception):
        asyncio.run(run_tools(None, None, SimpleNamespace(role='admin'), None,
                              'find_workflows', {'query': '员工账号', 'password': 'x'}, None))


def test_a_broken_catalogue_does_not_break_the_conversation(monkeypatch):
    def explode():
        raise OSError('catalogue missing')
    monkeypatch.setattr(guides, 'load_catalogue', explode)
    result = guides.find_workflows('员工账号', 'admin')
    assert result['items'] == [] and '暂时读不到' in result['notice']
