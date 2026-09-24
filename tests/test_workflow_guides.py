"""The published manual must match the original register and reviewed sources."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('workflow_guide_builder', ROOT / 'scripts/build_workflow_guides.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_published_guides_cover_every_original_requirement_with_both_paths_and_real_images():
    data, images = builder.make_data()
    assert len(data['requirements']) == 193
    assert {r['id'] for r in data['requirements']} == {f'HK-{n:03}' for n in range(1, 194)}
    assert all(r['workflow_ids'] for r in data['requirements'])
    assert len({r['id'] for r in data['requirements'] if r['module'] == '统计分析模块'}) == 36
    assert data['business_accepted'] is False
    assert data['screenshots_synthetic_only'] is True
    for guide in data['workflows']:
        assert guide['screenshot']['src'] in images
        assert guide['manual'] and guide['assistant']['steps']
        assert guide['exceptions'] and guide['completion']
    builder.build(check=True)


def source_with_change(monkeypatch, change):
    original = builder.read
    def read(path):
        value = original(path)
        if path.name == 'business.json':
            value = copy.deepcopy(value)
            change(value)
        return value
    monkeypatch.setattr(builder, 'read', read)


def test_duplicate_workflow_ids_are_rejected(monkeypatch):
    source_with_change(monkeypatch, lambda rows: rows.append(copy.deepcopy(rows[0])))
    with pytest.raises(AssertionError):
        builder.make_data()


def test_missing_original_requirement_is_rejected(monkeypatch):
    source_with_change(monkeypatch, lambda rows: [r['requirement_ids'].remove('HK-001') for r in rows if 'HK-001' in r['requirement_ids']])
    with pytest.raises(AssertionError):
        builder.make_data()


@pytest.mark.parametrize('route', ['https://external.test/', 'javascript:alert(1)', '../users', 'cases/lead?store=other'])
def test_navigation_cannot_be_replaced_by_a_url_or_cross_store_query(monkeypatch, route):
    source_with_change(monkeypatch, lambda rows: rows[0]['entry'].update(route=route))
    with pytest.raises(AssertionError):
        builder.make_data()


def test_unreviewed_or_missing_screenshots_cannot_be_published(monkeypatch):
    original = builder.read
    def read(path):
        value = original(path)
        if path.name == 'screenshots.json':
            value = copy.deepcopy(value)
            for shot in value.values():
                shot['synthetic_only'] = False
        return value
    monkeypatch.setattr(builder, 'read', read)
    with pytest.raises(AssertionError):
        builder.make_data()


def test_embedded_catalogue_treats_instruction_markup_as_text():
    value = {'title': '</script><script>alert(1)</script>&'}
    encoded = builder.json_text(value)
    assert '</script>' not in encoded and '<script>' not in encoded
    assert json.loads(encoded) == value
