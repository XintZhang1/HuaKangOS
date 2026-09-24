"""What the assistant may read follows the employee's own role; writes stay reviewed-only."""
import asyncio
from types import SimpleNamespace

import pytest

from app import business_assistant_gateway as gateway
from app.business_assistant_service import SYSTEM_PROMPT, run_tools


def ids():
    return set(gateway._operations())


def test_management_reads_follow_the_employees_own_scope():
    visible = ids()
    for operation in ('GET /api/users', 'GET /api/audit', 'GET /api/stores',
                      'GET /api/parameters/catalog', 'GET /api/reports', 'GET /api/findings',
                      'GET /api/business-entities/configuration', 'GET /api/records/{module}'):
        assert operation in visible, operation


def test_preparing_writes_beyond_the_reviewed_list_is_still_closed():
    visible = ids()
    assert 'POST /api/flow/cases' in visible                      # reviewed business write
    for operation in ('POST /api/users', 'POST /api/users/batch', 'POST /api/stores',
                      'PUT /api/stores/{store_id}', 'PUT /api/users/{user_id}'):
        assert operation not in visible, operation


def test_credentials_files_exports_and_deployment_are_never_visible():
    visible = ids()
    for operation in ('GET /api/auth/me', 'POST /api/auth/password', 'GET /api/local-preview/status',
                      'POST /api/branding/photo', 'GET /api/flow/files/{file_id}',
                      'GET /api/flow/analytics/export', 'GET /api/export/{module}',
                      'GET /api/opening-import/catalog', 'GET /api/health'):
        assert operation not in visible, operation
    assert not any('/files' in item or '/export' in item for item in visible)


def test_an_administrator_sees_the_staff_page_as_readable():
    rows = gateway.catalog(domain='users', role='admin')
    assert [row['id'] for row in rows] == ['GET /api/users']
    assert rows[0]['role_may_read'] is True and 'role_note' not in rows[0]


def test_another_role_is_told_which_post_the_entry_belongs_to():
    rows = gateway.catalog(domain='users', role='sales')
    assert rows and rows[0]['role_may_read'] is False
    assert '系统管理员' in rows[0]['role_note']


@pytest.mark.parametrize('role,expected', [('admin', True), ('manager', True), ('auditor', True),
                                           ('finance', False), ('service', False), ('sales', False)])
def test_audit_visibility_matches_the_real_page_rule(role, expected):
    rows = gateway.catalog(domain='audit', role=role)
    assert rows[0]['role_may_read'] is expected


def test_business_domains_leave_the_decision_to_the_endpoint():
    rows = gateway.catalog(domain='flow', role='sales')
    assert rows and all('role_may_read' not in row for row in rows)
    legacy = gateway._operations()['GET /api/records/{module}']
    assert gateway.role_may_read('sales', legacy) is None


def test_the_operation_list_hands_the_role_through_the_normal_tool_path():
    result = asyncio.run(run_tools(None, None, SimpleNamespace(role='sales'), None,
                                   'list_operations', {'domain': 'users'}, None))
    assert result[0]['role_may_read'] is False and '系统管理员' in result[0]['role_note']


def test_the_prompt_uses_the_authority_field_and_keeps_approvals_manual():
    assert 'role_may_read' in SYSTEM_PROMPT and 'role_note' in SYSTEM_PROMPT
    assert '只在原业务页面' in SYSTEM_PROMPT
    assert '不要把接口错误解释成系统故障' in SYSTEM_PROMPT


def test_every_visible_operation_still_resolves_to_its_own_registered_route():
    from fastapi.routing import APIRoute
    from app.main import app
    registered = {(route.path, method) for route in app.routes if isinstance(route, APIRoute)
                  for method in route.methods & {'GET', 'POST', 'PUT'}}
    for operation, op in gateway._operations().items():
        assert (op['path'], op['method']) in registered, operation
        assert op['manual_route'] and not op['manual_route'].startswith('/')


def test_no_file_or_csv_producing_route_is_offered_to_the_model():
    """Fail-closed: a new download/CSV endpoint must be excluded before it can be advertised.

    Media type lives in the handler body (`Response(..., media_type='text/csv')`) rather than on
    the route, so the catalogue cannot see it: scan the handler source and require every such GET
    to be kept out of the operation catalogue by DENIED or an explicit exclusion.
    """
    import inspect
    import re
    from fastapi.routing import APIRoute
    from app.main import app
    marker = re.compile(r"media_type\s*=\s*['\"]text/csv|FileResponse\(|StreamingResponse\(")
    visible = set(gateway._operations())
    leaked = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith('/api/') or 'GET' not in route.methods:
            continue
        try:
            source = inspect.getsource(route.endpoint)
        except (OSError, TypeError):
            continue
        if not marker.search(source):
            continue
        operation = 'GET ' + route.path
        if operation in visible:
            leaked.append(operation)
    assert not leaked, leaked


def test_the_known_sample_download_route_is_not_advertised():
    assert 'GET /api/vehicle-imports/orders/{case_id}/example/{kind}' not in gateway._operations()
    assert gateway.DENIED.search('/api/vehicle-imports/orders/1/example/vehicles')
