"""Model output cannot become arbitrary code, guessed controls, or options."""
import json
import pytest

from scripts.assistant_simulation import load_provider, safe_text, validate_actions


CONTROLS = [
    {'id': 0, 'tag': 'input', 'type': 'text'},
    {'id': 1, 'tag': 'select', 'options': [{'value': '7', 'label': '合成品牌'}]},
    {'id': 2, 'tag': 'button'},
    {'id': 3, 'tag': 'input', 'type': 'password'},
    {'id': 4, 'tag': 'input', 'type': 'checkbox'},
]


def test_observed_form_batch():
    actions = [{'op': 'fill', 'id': 0, 'value': '合成客户'}, {'op': 'select', 'id': 1, 'value': '7'},
               {'op': 'check', 'id': 4, 'value': True}, {'op': 'click', 'id': 2}]
    assert validate_actions({'status': 'act', 'actions': actions}, CONTROLS) == actions


@pytest.mark.parametrize('action', [
    {'op': 'evaluate', 'id': 0, 'value': 'fetch("/api/users")'},
    {'op': 'fill', 'id': 99, 'value': '没有这个控件'},
    {'op': 'fill', 'id': True, 'value': '不是编号'},
    {'op': 'select', 'id': 1, 'value': '888'},
    {'op': 'fill', 'id': 3, 'value': '不得读取或填写密码'},
    {'op': 'check', 'id': 4, 'value': 'true'},
])
def test_reject_unobserved_or_unsupported_action(action):
    with pytest.raises(ValueError):
        validate_actions({'status': 'act', 'actions': [action]}, CONTROLS)


def test_validate_whole_batch_before_click():
    with pytest.raises(ValueError):
        validate_actions({'status': 'act', 'actions': [{'op': 'click', 'id': 2}, {'op': 'fill', 'id': 0, 'value': '迟到输入'}]}, CONTROLS)


def test_secret_redaction():
    assert 'sk-abcdefghijk' not in safe_text('sk-abcdefghijk dealer_session=secret; dealer_csrf=also-secret')
    assert 'secret' not in safe_text('dealer_session=secret; dealer_csrf=also-secret')


@pytest.mark.parametrize('base', ['http://api.deepseek.com', 'https://not-deepseek.example', 'https://api.deepseek.com@not-deepseek.example'])
def test_provider_refuses_untrusted_destination(tmp_path, base):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'api_key': 'synthetic-placeholder', 'base_url': base}), encoding='utf-8')
    with pytest.raises(ValueError, match='官方'):
        load_provider(path)


def test_mimo_token_plan_uses_verified_endpoint_and_token_parameter(tmp_path):
    path = tmp_path / 'mimo.json'
    path.write_text(json.dumps({'provider': 'mimo', 'api_kind': 'token_plan', 'api_key': 'synthetic-placeholder'}), encoding='utf-8')
    config = load_provider(path)
    assert config.endpoint == 'https://token-plan-cn.xiaomimimo.com/v1/chat/completions'
    assert config.model == 'mimo-v2.6-flash'
    assert config.max_tokens_key == 'max_completion_tokens'
    assert 'synthetic-placeholder' not in repr(config)


def test_mimo_does_not_silently_switch_api_kind(tmp_path):
    path = tmp_path / 'mimo.json'
    path.write_text(json.dumps({'provider': 'mimo', 'api_kind': 'unknown', 'api_key': 'synthetic-placeholder'}), encoding='utf-8')
    with pytest.raises(ValueError, match='计费接口'):
        load_provider(path)
