"""Read-only restore checks for account authorization history and current grants."""
import hashlib
import json


STORE_STAFF_ROLES = frozenset({'sales', 'manager', 'clerk', 'finance'})


def receipt_action(source):
    action = source.get('account_action', 'update')
    if action not in {'update', 'archive', 'restore'}:
        raise ValueError('账号回执操作无效')
    return {'update': 'update_user', 'archive': 'archive_user', 'restore': 'restore_user'}[action]


def validate_archive_transition(source, before, result):
    if not isinstance(before, dict) or not isinstance(result, dict):
        raise ValueError('账号审计修改前后快照缺失')
    action = receipt_action(source)
    if action == 'update_user':
        if before.get('archived_at') != result.get('archived_at'):
            raise ValueError('普通账号修改不能改变员工删除状态')
        return
    unchanged = ('id', 'username', 'display_name', 'account_role', 'role', 'store_ids',
                 'store_roles', 'can_group_summary')
    if (any(before.get(key) != result.get(key) for key in unchanged)
            or result.get('active') is not False or not isinstance(source.get('reason'), str)
            or len(source['reason']) < 3):
        raise ValueError('员工删除或恢复不能改写身份及授权')
    if action == 'archive_user':
        if before.get('archived_at') is not None or not result.get('archived_at'):
            raise ValueError('员工删除状态不一致')
    elif not before.get('archived_at') or result.get('archived_at') is not None:
        raise ValueError('员工恢复状态不一致')


def receipt_digest(target_id, source, store_id=0):
    payload = {'target_id': target_id, 'values': source}
    if store_id:
        payload['store_id'] = store_id
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_store_snapshot(snapshot, store_id):
    if (not isinstance(snapshot, dict) or snapshot.get('store_id') != store_id
            or snapshot.get('store_ids') != [store_id]
            or snapshot.get('role') not in STORE_STAFF_ROLES
            or snapshot.get('account_role') not in STORE_STAFF_ROLES
            or snapshot.get('can_group_summary') is not False):
        raise ValueError('门店账号回执包含跨店或非普通岗位')
    roles = snapshot.get('store_roles')
    if (not isinstance(roles, list) or len(roles) != 1 or not isinstance(roles[0], dict)
            or roles[0].get('store_id') != store_id or roles[0].get('role') not in STORE_STAFF_ROLES):
        raise ValueError('门店账号回执岗位不一致')


def receipt_scope(audit, source, result, before):
    """Validate a durable scope without requiring the actor's later/current role."""
    if audit['entity_type'] == 'users' and audit['store_id'] == 0:
        return 0
    store_id = audit['store_id']
    if audit['entity_type'] != 'store_account' or type(store_id) is not int or store_id < 1:
        raise ValueError('账号审计归属范围不正确')
    for snapshot in (before, result):
        validate_store_snapshot(snapshot, store_id)
    if receipt_action(source) != 'update_user':
        validate_archive_transition(source, before, result)
        return store_id
    if source.get('role') not in STORE_STAFF_ROLES or source.get('can_group_summary') not in (None, False):
        raise ValueError('门店账号回执含越权请求')
    if source.get('store_ids') is not None and source['store_ids'] != [store_id]:
        raise ValueError('门店账号回执请求跨店')
    roles = source.get('store_roles')
    if roles is not None and (not isinstance(roles, list) or len(roles) != 1
            or not isinstance(roles[0], dict) or roles[0].get('store_id') != store_id
            or roles[0].get('role') not in STORE_STAFF_ROLES):
        raise ValueError('门店账号回执请求岗位不一致')
    return store_id


def validate(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    columns={r[1] for r in connection.execute('PRAGMA table_info(users)')}
    if 'user_access_receipts' not in names:
        if 'access_version' in columns:raise ValueError('账号授权修改回执表缺失')
        return {'user_access_receipts':0}
    if 'access_version' not in columns:raise ValueError('账号授权版本字段缺失')
    def records(table):
        cur=connection.execute('SELECT * FROM '+table);keys=[c[0] for c in cur.description]
        return [dict(zip(keys,row)) for row in cur]
    def decoded(value):return json.loads(value) if isinstance(value,str) else value
    users={u['id']:u for u in records('users')};audits={a['id']:a for a in records('audit_logs')}
    mappings={}
    for m in records('user_stores'):mappings.setdefault(m['user_id'],[]).append(m)
    histories={}
    for receipt in records('user_access_receipts'):
        source=decoded(receipt['request_data']);result=decoded(receipt['result']);audit=audits.get(receipt['audit_id'])
        before=decoded(audit['before_data']) if audit else None
        if not isinstance(source,dict) or not isinstance(result,dict):raise ValueError('账号授权回执内容不完整')
        if any(k in source or k in result for k in ('password','password_hash','csrf_hash','session_id')):
            raise ValueError('账号授权回执包含不应保存的登录凭据')
        if not audit:raise ValueError('账号审计回执缺失')
        scope=receipt_scope(audit,source,result,before)
        if not isinstance(before,dict):raise ValueError('账号审计修改前快照缺失')
        validate_archive_transition(source,before,result)
        expected=receipt_digest(receipt['target_id'],source,scope)
        prior=receipt['previous_version']
        if (receipt['actor_id'] not in users or receipt['target_id'] not in users or prior < 1
            or type(source.get('access_version')) is not int or source.get('access_version') != prior or receipt['digest'] != expected
            or result.get('id') != receipt['target_id'] or result.get('access_version') != prior+1
            or not audit or audit['actor_id'] != receipt['actor_id'] or audit['action'] != receipt_action(source)
            or audit['entity_id'] != receipt['target_id']
            or decoded(audit['after_data']) != result
            or not isinstance(before,dict) or before.get('access_version') != prior
            or not {'display_name','account_role','active','store_roles','can_group_summary'} <= result.keys()):
            raise ValueError('账号授权版本、请求或审计回执不一致')
        history=histories.setdefault(receipt['target_id'],{})
        if prior in history:raise ValueError('同一账号授权版本存在重复修改回执')
        history[prior]=result
    for uid,user in users.items():
        version=user['access_version'];history=histories.get(uid,{})
        if version < 1 or set(history) != set(range(1,version)):
            raise ValueError('账号授权版本与修改回执链不完整')
        if not history:
            if user.get('archived_at') is not None:
                raise ValueError('员工删除状态缺少对应审计回执')
            continue
        last=history[version-1]
        own=sorted([{'store_id':m['store_id'],'role':m['role'] or user['role'],
                     'legacy_fallback':m['role'] is None} for m in mappings.get(uid,[])],key=lambda m:m['store_id'])
        if (last['display_name'] != user['display_name'] or last['account_role'] != user['role']
            or bool(last['active']) != bool(user['active']) or last['store_roles'] != own
            or bool(last['can_group_summary']) != (user['role']=='admin' or bool(user['can_group_summary']))):
            raise ValueError('当前账号岗位或门店授权与最后一次审计修改不一致')
        if 'archived_at' in columns:
            from datetime import datetime
            current = datetime.fromisoformat(user['archived_at']) if user['archived_at'] else None
            recorded = datetime.fromisoformat(last['archived_at'].removesuffix('Z')) if last.get('archived_at') else None
            if current != recorded or (current is not None and user['active']):
                raise ValueError('当前员工删除状态与最后一次审计修改不一致')
    from .employee_handover_integrity import validate as validate_handovers
    validate_handovers(connection)
    return {'user_access_receipts':sum(len(h) for h in histories.values())}
