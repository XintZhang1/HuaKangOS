"""自动发布分级测试：tier 由「真实改动过的路径」决定，而不是模型的自我声明。

policy.EDITABLE 是唯一的自动发布白名单：整次改动都落在白名单内，并且运维
显式打开 auto_publish，才允许无人点击发布。本文件把「空改动、None、路径
穿越、伪装路径一律转人工」钉成回归测试，防止白名单被慢慢放宽。
"""
import re
import pytest
from maintenance.policy import (AUTO_APPROVER, EDITABLE, Edit, Proposal, TIER_AUTO, TIER_HUMAN,
    change_tier, tier_allows_auto_publish)

EDITABLE_FILES=sorted(EDITABLE)
# 受保护路径：任何一条被自动发布都是安全事故
PROTECTED=['app/analytics.py','app/models.py','app/main.py','migrations/versions/x.py','requirements.txt',
    'tests/test_app.py','maintenance/supervisor.py','maintenance/policy.py','maintenance/transport.py',
    'app/security.py','.env','Dockerfile','docs/AI_CONTEXT.md','.git/config']


# --- 1. 白名单内的改动才是 auto ------------------------------------------

@pytest.mark.parametrize('changed',[[name] for name in EDITABLE_FILES]+[EDITABLE_FILES,sorted(EDITABLE),set(EDITABLE),tuple(EDITABLE)])
def test_editable_files_are_tier_auto(changed):
    assert change_tier(changed)==TIER_AUTO


def test_the_whitelist_is_exactly_the_four_frontend_files():
    assert isinstance(EDITABLE,frozenset)
    assert EDITABLE==frozenset({'web/app.js','web/style.css','web/index.html','docs/USER_GUIDE.md'})
    # 文档上下文可读不可自动改：AI_CONTEXT 不在 EDITABLE 里
    assert 'docs/AI_CONTEXT.md' not in EDITABLE and EDITABLE<EDITABLE|{'docs/AI_CONTEXT.md'}


# --- 2. 受保护路径（含混合改动）一律 human -------------------------------

@pytest.mark.parametrize('changed',[[name] for name in PROTECTED]+[
    ['web/app.js','app/analytics.py'],
    ['docs/USER_GUIDE.md','.env'],
    ['web/style.css','requirements.txt','web/index.html'],
    PROTECTED])
def test_protected_or_mixed_changes_are_tier_human(changed):
    assert change_tier(changed)==TIER_HUMAN


def test_one_unknown_path_poisons_the_whole_commit():
    assert change_tier(['web/app.js','web/style.css'])==TIER_AUTO
    assert change_tier(['web/app.js','web/style.css','app/analytics.py'])==TIER_HUMAN


# --- 3. 关键安全属性：空/None/空字符串永远是 human ------------------------

@pytest.mark.parametrize('changed',[None,[],(),'',['',''],['',''],{},set(),frozenset(),0,False])
def test_empty_or_unknown_change_is_never_auto(changed):
    assert change_tier(changed)==TIER_HUMAN
    assert tier_allows_auto_publish(changed,True) is False


def test_a_bare_string_is_not_a_path_list_and_fails_closed():
    # 传字符串而不是列表时，迭代出来的是单个字符，集合不可能等于白名单 -> human
    assert change_tier('web/app.js')==TIER_HUMAN
    assert change_tier(EDITABLE_FILES[0])==TIER_HUMAN


def test_a_non_iterable_changed_value_fails_loudly_not_closed():
    # 如实记录边界：0/False 会走 `changed or ()` 变成空改动（human），
    # 但其他非可迭代对象会抛 TypeError（响亮地崩）——调用方必须传路径序列。
    with pytest.raises(TypeError):change_tier(1)
    with pytest.raises(TypeError):change_tier(3.5)


# --- 4. 路径穿越与伪装路径 ------------------------------------------------

@pytest.mark.parametrize('name',[
    'web/../app/security.py','web/../app/analytics.py','../web/app.js','web/./app.js','web//app.js',
    'web/app.js/../app.js','maintenance/../web/app.js','WEB/app.js','Web/App.js','web\\app.js',
    'web/app.js ',' web/app.js','web/app.js\n','web/app.js\x00','docs/USER_GUIDE.md.','./web/app.js'])
def test_traversal_and_lookalike_paths_are_never_auto(name):
    assert name not in EDITABLE
    assert change_tier([name])==TIER_HUMAN
    assert change_tier(['web/app.js',name])==TIER_HUMAN
    assert tier_allows_auto_publish([name],True) is False


# --- 5. 开关与白名单必须同时满足 -----------------------------------------

@pytest.mark.parametrize('changed',[None,[],['app/analytics.py'],['web/app.js','app/analytics.py'],
    ['web/../app/security.py'],PROTECTED])
def test_the_switch_off_wins_even_for_an_editable_change(changed):
    assert tier_allows_auto_publish(changed,False) is False
    assert tier_allows_auto_publish(changed,0) is False
    assert tier_allows_auto_publish(changed,None) is False


def test_auto_publish_is_true_only_for_editable_and_enabled():
    assert tier_allows_auto_publish(EDITABLE_FILES,True) is True
    assert tier_allows_auto_publish(['web/style.css'],True) is True
    assert tier_allows_auto_publish(EDITABLE_FILES,False) is False
    assert tier_allows_auto_publish(['web/style.css','app/main.py'],True) is False
    # 开关是配置读出来的，务先经过 config.flag() 变成 bool；'false' 这种非空
    # 字符串是真值，直接把原始字符串传进来会被当成「已开启」。
    assert tier_allows_auto_publish(EDITABLE_FILES,'false') is True
    assert tier_allows_auto_publish(EDITABLE_FILES,1) is True


def test_tier_values_are_the_two_documented_constants():
    assert (TIER_AUTO,TIER_HUMAN)==('auto','human')
    assert change_tier(EDITABLE_FILES) in {TIER_AUTO,TIER_HUMAN}
    assert change_tier(PROTECTED) in {TIER_AUTO,TIER_HUMAN}


# --- 6. 回归护栏：模型自报的 risk 永远不参与定级 --------------------------

def test_model_self_reported_low_risk_on_protected_code_is_still_human():
    proposal=Proposal(summary='把分析口径改成我认为对的样子',risk='low',
        edits=[Edit(path='app/analytics.py',old='old',new='new')])
    assert proposal.risk=='low'  # 模型自称低风险
    assert change_tier([e.path for e in proposal.edits])==TIER_HUMAN
    assert tier_allows_auto_publish([e.path for e in proposal.edits],True) is False


def test_tier_ignores_the_risk_field_in_both_directions():
    # 反向也要钉住：分级只看路径。模型自称 risk='manual' 并不额外抬高门槛，
    # 但白名单仍然只放行前端文件，且 apply_proposal 会因 risk!='low' 直接拒绝。
    cautious=Proposal(summary='我自己也不确定',risk='manual',manual_reason='涉及登录',
        edits=[Edit(path='web/style.css',old='old',new='new')])
    assert change_tier([e.path for e in cautious.edits])==TIER_AUTO
    assert tier_allows_auto_publish([e.path for e in cautious.edits],True) is True


def test_multi_file_proposal_needs_every_edit_inside_the_whitelist():
    mixed=Proposal(summary='顺手改后端',risk='low',edits=[
        Edit(path='web/app.js',old='old',new='new'),Edit(path='app/models.py',old='old',new='new')])
    assert change_tier([e.path for e in mixed.edits])==TIER_HUMAN


# --- 7. 自动审批人不是飞书身份 --------------------------------------------

def test_auto_approver_is_a_synthetic_label_never_a_feishu_open_id():
    assert isinstance(AUTO_APPROVER,str) and AUTO_APPROVER
    assert not AUTO_APPROVER.startswith('ou_')
    # config.validate() 用这个正则校验审批人白名单：自动审批人永远不可能混进去
    assert not re.fullmatch(r'ou_[A-Za-z0-9_-]{5,100}',AUTO_APPROVER)
    assert AUTO_APPROVER!=('ou_'+AUTO_APPROVER)