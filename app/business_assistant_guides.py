"""Read-only help lookup for the business assistant.

The assistant may look up the published workflow guides (entry, roles, prerequisites, steps and
the limits already written for employees). This module returns help content only: no business
record, no file, no permission and no state change. It reuses the same catalogue loader and the
same matching rules as the in-page search, so a hit here means a hit in the search box.
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


def search(query, role='', category='', limit=MAX_RESULTS):
    """Published guides matching the employee's words, best first. Never raises for a bad query."""
    rows = load_catalogue()
    raw = str(query or '').strip()[:200]
    clean = SUFFIX.sub('', PREFIX.sub('', raw))
    words = [word for word in (normalize(part) for part in re.split(r'\s+', clean or raw)) if word]
    wanted_category = normalize(category) if category else ''
    scored = []
    for row in rows:
        if wanted_category:
            haystack_category = normalize(row.get('category', '')) + normalize(row.get('title', ''))
            if wanted_category not in haystack_category:
                continue
        haystack = normalize(' '.join(str(value or '') for value in _fragments(row)))
        if words and not all(word in haystack for word in words):
            continue
        scored.append((_score(normalize(clean or raw), row), row))
    scored.sort(key=lambda item: (-item[0], item[1]['title']))
    return [project(row, role) for score, row in scored[:max(1, min(int(limit or MAX_RESULTS), MAX_RESULTS))]]


def find_workflows(query, role='', category=''):
    """Tool result for the assistant: matching guides plus what to do with none."""
    try:
        items = search(query, role, category)
    except Exception:  # Catalogue missing or unreadable must not break the conversation.
        return {'items': [], 'notice': '操作指引暂时读不到；请告诉员工按左侧“操作指引”或搜索框自己查找，不要凭记忆编入口。'}
    if not items:
        return {'items': [], 'notice': '操作指引里没有匹配的入口。可以说清楚你能帮员工整理哪些资料，但不要编造页面或按钮。'}
    for item in items:
        item['next'] = ('告诉员工入口、岗位和本次要准备的资料；需要账号、密码或审批的操作只指路，不代提交。'
                        if item['entry']['can_enter'] else item['entry']['role_note'])
    return {'items': items}
