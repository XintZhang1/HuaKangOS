"""Read-only help lookup for the business assistant.

The assistant may look up the published workflow guides (entry, roles, prerequisites, steps and
the limits already written for employees). This module returns help content only: no business
record, no file, no permission and no state change. It reuses the same catalogue loader and the
published source as the in-page search. Its natural-language ranking may differ; all returned IDs remain original published guides.
"""
import re

from .workflow_guides_api import PREFIX, SUFFIX, load_catalogue, normalize

MAX_RESULTS = 3
MAX_STEPS = 6
MAX_TEXT = 300
ROLE_LABELS = {'admin': '系统管理员', 'manager': '店长', 'sales': '销售', 'inventory': '库管',
               'service': '服务顾问', 'finance': '财务', 'auditor': '审计', 'reception': '前台接待',
               'technician': '维修技师', 'customer_service': '客服'}


def _clip(value):
    text = str(value or '').strip()
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + '…'


def _fragments(row):
    parts = [row.get('title', ''), row.get('category', ''), row.get('summary', ''),
             (row.get('entry') or {}).get('label', '')]
    parts += list(row.get('keywords') or [])
    parts += [step.get('where', '') for step in row.get('manual') or []]
    parts += [issue.get('when', '') for issue in row.get('exceptions') or []]
    for requirement in row.get('requirements') or []:
        parts += [requirement.get('id', ''), requirement.get('title', ''), requirement.get('group', '')]
    return parts


def _score(query, row):
    """Keep in step with search() in web/workflowcontent.js."""
    title = normalize(row.get('title', ''))
    entry = normalize((row.get('entry') or {}).get('label', '')).removeprefix(normalize('打开'))
    keywords = [normalize(value) for value in row.get('keywords') or []]
    requirements = [normalize('%s %s' % (item.get('id', ''), item.get('title', '')))
                    for item in row.get('requirements') or []]
    return ((100 if query and title == query else 0)
            + (60 if query and entry == query else 0)
            + (40 if query and title.startswith(query) else 0)
            + (25 if query and query in title else 0)
            + (20 if query and query in keywords else 0)
            + (12 if query and any(query in text for text in requirements) else 0))


def _entry(row, role):
    entry = row.get('entry') or {}
    roles = list(entry.get('roles') or [])
    can_enter = role == 'admin' or role in roles
    note = '' if can_enter else '这个入口只对%s开放，当前岗位只能查看说明。' % '、'.join(
        ROLE_LABELS.get(item, item) for item in roles)
    return {'label': entry.get('label', ''), 'route': entry.get('route', ''),
            'mode': entry.get('mode', ''), 'roles': roles, 'can_enter': can_enter,
            'role_note': note}


def project(row, role=''):
    """Only published help fields; never business rows, ids, files or permissions."""
    return {'workflow_id': row['id'], 'title': _clip(row.get('title')), 'category': _clip(row.get('category')),
            'summary': _clip(row.get('summary')), 'entry': _entry(row, role),
            'prerequisites': [_clip(value) for value in (row.get('prerequisites') or [])[:4]],
            'steps': [{'actor': _clip(step.get('actor')), 'where': _clip(step.get('where')),
                       'action': _clip(step.get('action')), 'expected': _clip(step.get('expected'))}
                      for step in (row.get('manual') or [])[:MAX_STEPS]],
            'assistant_note': _clip((row.get('assistant') or {}).get('prompt')),
            'exceptions': [_clip('%s：%s' % (issue.get('when'), issue.get('action')))
                           for issue in (row.get('exceptions') or [])[:3]],
            'completion': [_clip(value) for value in (row.get('completion') or [])[:3]]}


# Retrieval synonyms only: these never grant an operation, choose a record or write data.
SEARCH_ALIASES = {
    '采购车辆退回': '车辆采购退回', '采购退车': '车辆采购退回',
    'pdi': '新车检测', '新车交付前检测': '新车检测',
    '换库位': '店内移库 移库', '跨店调拨': '调拨',
    '收款更正': '收款单调整', '收款金额记错': '收款单调整',
    '补卡': '会员换补卡', '会员卡丢失': '会员换补卡',
    '员工账号': '员工管理', '新建账号': '员工管理', '账号开通': '员工管理',
    '门店设置': '机构管理', '集团会员': '会员信息管理 会员储值卡充值',
    '跨店会员': '会员信息管理 会员储值卡充值', '会员中心': '会员信息管理 会员储值卡充值',
    '车辆目录': '品牌车系车型', 'vehicle-catalog': '品牌车系车型',
}
GENERIC_SEARCH_TERMS = {'查询','管理','记录','入口','维护','新增','办理','操作','字段','本店',
                        '基础数据','系统管理','流程','资料','模板','说明','名称'}


def _retrieval_score(raw, row):
    normalized = normalize(raw)
    expanded = normalized + ''.join(normalize(target) for source, target in SEARCH_ALIASES.items()
                                    if normalize(source) in normalized)
    title = normalize(row.get('title',''))
    requirements = [normalize(x.get('title','')) for x in row.get('requirements',[])]
    terms = [title, normalize((row.get('entry') or {}).get('label','')).removeprefix('打开')]
    terms += requirements + [normalize(x) for x in row.get('keywords',[])]
    if normalized == title or normalized in requirements:
        return 10000
    anchored = [t for t in terms if len(t)>=2 and t not in GENERIC_SEARCH_TERMS and t in expanded]
    # Literal published requirement names dominate partial keywords and prose.
    score = max([len(t)*25 + (250 if t in requirements else 0) for t in anchored] or [0])
    token_text = raw + ' ' + ' '.join(target for source,target in SEARCH_ALIASES.items() if normalize(source) in normalized)
    tokens = [normalize(t) for t in re.split(r'[\s，,。;；/]+',token_text) if normalize(t)]
    haystack = normalize(' '.join(str(t) for t in _fragments(row)))
    for token in tokens:
        if token not in GENERIC_SEARCH_TERMS and len(token)>=2 and token in haystack:
            score += min(len(token),12)*3
    if normalized and len(normalized)>=2 and normalized in haystack:
        score += 80
    return score


def search(query, role='', category='', limit=MAX_RESULTS):
    """Rank only published guides. Category is a hint, not a permission filter.

    The old all-word AND matcher lost exact names when a user appended '所需字段'.
    Keep exact identifiers strong; expose relaxed category matches explicitly.
    """
    raw = str(query or '').strip()[:200]
    if not raw:
        return []
    rows=load_catalogue()
    normalized=normalize(raw)
    # One exact published name can map to several guides; do not add adjacent topics.
    exact=[row for row in rows if normalized and (
        normalize(row.get('title',''))==normalized
        or any(normalize(item.get('title',''))==normalized
               for item in row.get('requirements',[])))]
    if exact:
        rows=exact
    category_text=normalize(category) if category else ''
    scored=[]
    for row in rows:
        score=_retrieval_score(raw,row)
        if score<=0:
            continue
        category_blob=row.get('category','')+row.get('title','')+' '.join(x.get('module','') for x in row.get('requirements',[]))
        in_category=not category_text or category_text in normalize(category_blob)
        # A wrong category must not hide a literally named requirement.
        scored.append((score+(35 if in_category else 0),row,in_category))
    scored.sort(key=lambda item:(-item[0],item[1]['title']))
    result=[]
    for score,row,in_category in scored[:max(1,min(int(limit or MAX_RESULTS),MAX_RESULTS))]:
        item=project(row,role)
        item['requirement_ids']=list(row.get('requirement_ids') or [])
        item['matched_requirements']=[{'id':x.get('id'),'title':x.get('title')} for x in row.get('requirements',[])]
        item['match_notice']=('按已发布名称/关键词检索的相关指引，请核对具体业务方向。' if in_category else
                              '本结果不在传入分类内；分类已放宽，实际模块以本条category为准，不表示岗位获得权限。')
        result.append(item)
    return result


def find_workflows(query, role='', category=''):
    """Tool result for the assistant: matching guides plus what to do with none."""
    try:
        items = search(query, role, category)
    except Exception:  # Catalogue missing or unreadable must not break the conversation.
        return {'items': [], 'notice': '操作指引暂时读不到；请告诉员工按左侧“操作指引”或搜索框自己查找，不要凭记忆编入口。'}
    if not items:
        return {'items': [], 'notice': '本次查询未匹配，不代表系统没有该功能。请缩短为原需求名称或核心业务词、去掉可能错误的category后重查；仍无结果再如实说明，不凭相邻接口猜流程。'}
    normalized=normalize(str(query or '').strip()[:200])
    exact_requirements=[]
    for item in items:
        for requirement in item['matched_requirements']:
            if normalize(requirement['title'])==normalized and requirement not in exact_requirements:
                exact_requirements.append(dict(requirement))
    exact_titles=[item['workflow_id'] for item in items if normalize(item['title'])==normalized]
    query_match={
        'kind':'exact_published_name' if exact_requirements or exact_titles else 'related_candidates',
        'query':str(query or '').strip()[:200],
        'exact_requirements':exact_requirements,
        'exact_workflow_titles':exact_titles,
        'returned_workflow_ids':[item['workflow_id'] for item in items]}
    for item in items:
        item['next'] = ('告诉员工入口、岗位和本次要准备的资料；其它业务能否准备按操作目录和原单权限判断，不按动作名称一概限制。'
                        if item['entry']['can_enter'] else item['entry']['role_note'])
    return {'items': items, 'query_match': query_match, 'notice': (
        '这是当前发布的工作流帮助，未读取或核对任何具体原单的kind、flow_version、当前版本及父单授权。'
        'entry.can_enter仅表示该帮助入口的岗位匹配，不证明本人能办理旧原单。'
        'entry.roles不是每一步办理、审批或收款的岗位清单；按steps.actor、action、expected及exceptions说明分工，多岗位并列不表示可互相替代。'
        'prerequisites是整条指引的准备说明，不自动成为每一步前置；同一指引收录多个事项时，只解释本次事项对应的动作和分支，不把其它事项的步骤或字段列为必备。'
        '按明确的步骤条件说明先后与等待；“包括”项不是唯一范围，不把列举项目缩成排他条件。'
        '已有原单应先按本人权限读取该业务领域的原详情，再核对原动作、必填项和拒绝原因；通用Flow动作与专门领域动作不互相替代。向员工说明原页面和岗位，不把工具名当作已验证的可办入口。指引不能替代原版本守卫。'
        '涉及父单步骤须先按本人权限读取父单；读取被拒时等待有权限岗位，'
        '不得承诺拿到单号即可准备，也不能按本指引猜填旧单字段。')}
