"""Static registration and scoped Node contracts; real browser evidence is separate."""
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]


def test_new_page_scripts_and_runtime_catalog_registered(client):
    for url in ['/','/static/app.js','/static/dossiergrants.js']:
        response=client.get(url)
        assert response.status_code==200,response.text
    assert '/static/dossiergrants.js' in client.get('/').text
    content=client.get('/static/app.js').text
    assert "'/api/dossier-grants/catalog'" in content
    assert "type==='dossier-grants'" in content
    assert 'dossierCaseLink(r)' in content
    assert 'clearDossierGrantsSession' in content
    assert 'leaveDossierGrantsView' in content
    assert client.get('/api/dossier-grants/catalog').json()['can_review']


def test_real_js_helpers_with_mocked_transport_not_browser_acceptance():
    node=shutil.which('node')
    if not node:pytest.skip('Node needed for local rendering assertions; not a browser prerequisite')
    result=subprocess.run([node,'--test','tests/js/dossier_grants.test.cjs','tests/js/store_switch.test.cjs'],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def test_forms_default_sensitive_scope_off_and_no_persistent_payload_cache():
    script=(ROOT/'web/dossiergrants.js').read_text()
    for name in ['include_contact','include_financials','dossier_file','confirmed']:
        for fragment in script.split('<input')[1:]:
            tag=fragment.split('>')[0]
            if 'name="'+name+'"' in tag:
                assert ' checked' not in tag
    assert 'localStorage' not in script and 'sessionStorage' not in script
