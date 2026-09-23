"""Read-only restore checks for account authorization history and current grants."""
import hashlib
import json


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
        expected=hashlib.sha256(json.dumps({'target_id':receipt['target_id'],'values':source},
                                         sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        prior=receipt['previous_version']
        if (receipt['actor_id'] not in users or receipt['target_id'] not in users or prior < 1
            or type(source.get('access_version')) is not int or source.get('access_version') != prior or receipt['digest'] != expected
            or result.get('id') != receipt['target_id'] or result.get('access_version') != prior+1
            or not audit or audit['actor_id'] != receipt['actor_id'] or audit['action'] != 'update_user'
            or audit['entity_type'] != 'users' or audit['entity_id'] != receipt['target_id']
            or audit['store_id'] != 0 or decoded(audit['after_data']) != result
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
        if not history:continue
        last=history[version-1]
        own=sorted([{'store_id':m['store_id'],'role':m['role'] or user['role'],
                     'legacy_fallback':m['role'] is None} for m in mappings.get(uid,[])],key=lambda m:m['store_id'])
        if (last['display_name'] != user['display_name'] or last['account_role'] != user['role']
            or bool(last['active']) != bool(user['active']) or last['store_roles'] != own
            or bool(last['can_group_summary']) != (user['role']=='admin' or bool(user['can_group_summary']))):
            raise ValueError('当前账号岗位或门店授权与最后一次审计修改不一致')
    return {'user_access_receipts':sum(len(h) for h in histories.values())}
