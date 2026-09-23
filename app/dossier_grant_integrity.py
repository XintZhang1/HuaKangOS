"""Read-only historical provenance checks; current role changes stay restorable.

Checks originals, per-file identities, frozen scope, input receipts, independent
reviews and access ordering. Digests are internal consistency checks, NOT an
external signature against an administrator rewriting every matching source.
"""
import json
from . import dossier_grant_rules as rules

TABLES = {'dossier_grants', 'dossier_grant_files', 'dossier_decisions', 'dossier_accesses', 'dossier_receipts'}


def validate(connection):
    names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    empty = {'dossier_grants': 0, 'dossier_files': 0, 'dossier_decisions': 0, 'dossier_accesses': 0}
    if not TABLES & names:
        return empty  # An unmigrated, otherwise valid historical database.
    if not TABLES <= names:
        raise ValueError('档案授权恢复检查：授权表仅存在一部分')

    def rows(table):
        # This validator needs original metadata, not every private attachment's
        # bytes. The shared file validator independently checks content hashes.
        fields = ','.join('"' + k + '"' for k in (*rules.FILE_KEYS, 'created_at')) if table == 'flow_files' else '*'
        cursor = connection.execute('SELECT ' + fields + ' FROM "' + table + '"')
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def fail(message):
        raise ValueError('档案授权恢复检查：' + message)

    def obj(value):
        try:
            return json.loads(value) if isinstance(value, str) else value
        except (TypeError, ValueError):
            fail('JSON来源无法读取')

    grants, files, decisions, accesses, receipts = [rows(name) for name in
        ('dossier_grants', 'dossier_grant_files', 'dossier_decisions', 'dossier_accesses', 'dossier_receipts')]
    if not grants:
        if files or decisions or accesses or receipts:
            fail('授权来源缺失')
        return empty
    originals = {r['id']: r for r in rows('flow_cases')}
    assets = {r['id']: r for r in rows('flow_files')}
    events = {r['id']: r for r in rows('flow_events')}
    users = {r['id']: r for r in rows('users')}
    stores = {r['id']: r for r in rows('stores')}
    grant_map = {r['id']: r for r in grants}
    for child in files + decisions + accesses + receipts:
        if child['grant_id'] not in grant_map:
            fail('文件、决定或回执缺少原授权')

    for g in grants:
        created, expiry = rules.timestamp(g['created_at']), rules.timestamp(g['expires_at'])
        source = originals.get(g['source_case_id'])
        if (not source or source['store_id'] != g['from_store_id']
            or g['from_store_id'] == g['to_store_id'] or g['from_store_id'] not in stores
            or g['to_store_id'] not in stores or source['version'] < g['source_case_version'] or expiry <= created):
            fail('原单门店、版本或期限不一致')
        if g['recipient_id'] == g['requested_by'] or g['recipient_role'] not in rules.READ or g['requester_role'] not in rules.WRITE:
            fail('授权人员或历史岗位不合范围')
        for user_id, generation in [(g['recipient_id'], g['recipient_access_version']), (g['requested_by'], g['requester_access_version'])]:
            if user_id not in users or generation < 1 or users[user_id]['access_version'] < generation:
                fail('账号原权限版本缺失')
        if g['include_financials'] and (g['recipient_role'] not in rules.FINANCIAL or g['requester_role'] not in rules.FINANCIAL):
            fail('财务范围超出原双方岗位')
        record = obj(g['record_snapshot'])
        try:
            rules.validate_record(record, bool(g['include_record']), bool(g['include_contact']), bool(g['include_financials']))
        except (ValueError, TypeError, KeyError) as exc:
            fail('快照白名单或定义错误：' + str(exc))
        if record:
            header = record['case']
            if (header['id'] != source['id'] or header['store_id'] != source['store_id']
                or header['version'] != g['source_case_version'] or header['kind'] != source['kind']
                or header['number'] != source['number'] or header['flow_version'] != source['flow_version']):
                fail('快照不是原单的已批准历史版本')
            for event in record['events']:
                e = events.get(event['id'])
                if (not e or e['case_id'] != source['id'] or e['store_id'] != g['from_store_id']
                    or event['label'] != e['label'] or event['from_state'] != e['before_state']
                    or event['to_state'] != e['after_state']
                    or rules.timestamp(event['occurred_at']) != rules.timestamp(e['occurred_at'])
                    or rules.timestamp(e['occurred_at']) > created):
                    fail('冻结事件不是原单原时点的办理事实')
        gfiles = [f for f in files if f['grant_id'] == g['id']]
        ids = [f['file_id'] for f in gfiles]
        if len(ids) != len(set(ids)) or len(ids) > rules.MAX_FILES or not g['include_record'] and not ids:
            fail('逐件清单重复、过量或没有授权范围')
        manifests = []
        for f in gfiles:
            manifest = obj(f['metadata_snapshot'])
            asset = assets.get(f['file_id'])
            if (not isinstance(manifest, dict) or manifest.get('id') != f['file_id'] or not asset
                or asset['case_id'] != source['id'] or asset['store_id'] != g['from_store_id']):
                fail('逐件编号不是原单原门店文件，不能按同内容替换')
            expected = {key: asset[key] for key in rules.FILE_KEYS}
            for flag in ('generated', 'template_approved'):
                expected[flag] = bool(expected[flag])
            expected['created_at'] = rules.iso(asset['created_at'])
            if manifest != expected or rules.timestamp(asset['created_at']) > created:
                fail('逐件文件版本、类别或摘要与原件不一致')
            manifests.append(manifest)
        if rules.digest(rules.scope_payload(g, manifests)) != g['scope_digest']:
            fail('批准范围摘要不一致')
        gdecisions = sorted((r for r in decisions if r['grant_id'] == g['id']), key=lambda r: r['previous_version'])
        state, version, approval = 'pending', 1, None
        previous_time = created
        for d in gdecisions:
            occurred = rules.timestamp(d['occurred_at'])
            if (d['previous_version'] != version or d['scope_digest'] != g['scope_digest']
                or d['store_id'] != g['from_store_id'] or occurred < previous_time
                or d['actor_id'] not in users or d['actor_access_version'] < 1
                or users[d['actor_id']]['access_version'] < d['actor_access_version']):
                fail('独立决定的原人员、版本、时间或范围不一致')
            if d['action'] in {'approve', 'reject'}:
                if state != 'pending' or d['actor_id'] == g['requested_by'] or d['actor_role'] not in rules.MANAGE:
                    fail('原店不同人员独立复核缺失')
                state = 'approved' if d['action'] == 'approve' else 'rejected'
                if d['action'] == 'approve':
                    if occurred >= expiry:
                        fail('到期后补批')
                    approval = d
            elif d['action'] in {'cancel', 'revoke'}:
                if state != ('pending' if d['action'] == 'cancel' else 'approved'):
                    fail('取消或撤销顺序错误')
                if d['actor_id'] != g['requested_by'] and d['actor_role'] not in rules.MANAGE:
                    fail('非发起人或原店主管结束授权')
                state = 'cancelled' if d['action'] == 'cancel' else 'revoked'
            else:
                fail('未知决定')
            version += 1
            previous_time = occurred
        if g['status'] != state or g['version'] != version:
            fail('当前授权状态没有原决定支持')
        greceipts = [r for r in receipts if r['grant_id'] == g['id']]
        if len(greceipts) != 1 + len(gdecisions):
            fail('请求回执与原操作数量不一致')
        seen_actions = set()
        for receipt in greceipts:
            request = obj(receipt['request_data'])
            if (not isinstance(request, dict) or receipt['store_id'] != g['from_store_id']
                or receipt['scope_digest'] != g['scope_digest']
                or rules.digest({'action': receipt['action'], 'payload': request}) != receipt['digest']
                or request.get('confirmed') is not True or receipt['action'] in seen_actions):
                fail('请求回执的门店、范围或输入摘要不一致')
            seen_actions.add(receipt['action'])
            if receipt['action'] == 'propose':
                matching = ('source_case_id', 'source_case_version', 'to_store_id', 'recipient_id', 'purpose')
                if (any(request.get(k) != g[k] for k in matching) or receipt['actor_id'] != g['requested_by']
                    or sorted(request.get('file_ids', [])) != sorted(ids)
                    or rules.timestamp(request['expires_at']) != expiry
                    or any(request.get(k) is not bool(g[k]) for k in ('include_record', 'include_contact', 'include_financials'))):
                    fail('提交回执不是当前冻结范围')
            else:
                ds = [d for d in gdecisions if d['action'] == receipt['action']]
                if (len(ds) != 1 or request.get('grant_id') != g['id']
                    or request.get('version') != ds[0]['previous_version'] or receipt['actor_id'] != ds[0]['actor_id']
                    or request.get('reason') != ds[0]['reason']):
                    fail('复核回执不是原决定')
        if 'propose' not in seen_actions:
            fail('缺少原始申请回执')
        revoked = next((rules.timestamp(d['occurred_at']) for d in gdecisions if d['action'] == 'revoke'), None)
        for access in (r for r in accesses if r['grant_id'] == g['id']):
            occurred = rules.timestamp(access['occurred_at'])
            if (not approval or access['grant_version'] != approval['previous_version'] + 1
                or access['actor_id'] != g['recipient_id'] or access['store_id'] != g['to_store_id']
                or access['actor_role'] != g['recipient_role'] or access['actor_access_version'] != g['recipient_access_version']
                or access['scope_digest'] != g['scope_digest'] or occurred < rules.timestamp(approval['occurred_at'])
                or occurred >= expiry or revoked and occurred > revoked):
                fail('读取不是批准有效期内的指定员工')
            if access['action'] == 'file':
                if access['file_id'] not in ids:
                    fail('读取了未逐件批准的文件')
            elif access['action'] in {'record', 'directory'}:
                if access['file_id'] is not None or access['action'] == 'record' and not g['include_record']:
                    fail('仅文件范围读取了原单')
            else:
                fail('未知读取类型')
    return {'dossier_grants': len(grants), 'dossier_files': len(files),
            'dossier_decisions': len(decisions), 'dossier_accesses': len(accesses)}
