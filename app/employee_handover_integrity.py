"""Read-only consistency checks for additive employee handover evidence."""
import hashlib
import json


def validate(connection):
    names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    tables = {'employee_handovers', 'employee_handover_records'}
    if not tables.intersection(names):
        return
    if not tables <= names:
        raise ValueError('员工交接证据表缺失')
    def rows(table):
        cursor = connection.execute('SELECT * FROM ' + table)
        fields = [column[0] for column in cursor.description]
        return [dict(zip(fields, value)) for value in cursor]
    def decoded(value):
        return json.loads(value) if isinstance(value, str) else value
    receipts = {row['id']: row for row in rows('user_access_receipts')}
    audits = {row['id']: row for row in rows('audit_logs')}
    users = {row['id'] for row in rows('users')}
    stores = {row['id'] for row in rows('stores')}
    customers = {row['id']: row['store_id'] for row in rows('business_record_customers')}
    contracts = {row['id']: row['store_id'] for row in rows('business_record_contracts')}
    handovers = {row['id']: row for row in rows('employee_handovers')}
    details = {}
    for row in rows('employee_handover_records'):
        header = handovers.get(row['handover_id'])
        if not header or (row['customer_id'] is None) == (row['contract_id'] is None):
            raise ValueError('员工交接原记录关联无效')
        store = customers.get(row['customer_id']) if row['customer_id'] is not None else contracts.get(row['contract_id'])
        if store != header['store_id'] or row['can_continue'] not in (0, 1):
            raise ValueError('员工交接不得跨店或伪造办理范围')
        details.setdefault(header['id'], []).append(row)
    grouped = {}
    for header in handovers.values():
        receipt = receipts.get(header['receipt_id'])
        if (not receipt or receipt['target_id'] != header['source_id'] or header['source_id'] == header['successor_id']
                or header['successor_id'] not in users or header['store_id'] not in stores
                or header['successor_access_version'] < 1):
            raise ValueError('员工交接账号或归档回执不一致')
        entry = {key: header[key] for key in ('store_id','successor_id','successor_role','successor_access_version')}
        for name, key in (('customers','customer_id'),('contracts','contract_id')):
            entry[name] = sorted([{'id': item[key], 'can_continue': bool(item['can_continue'])}
                for item in details.get(header['id'], []) if item[key] is not None], key=lambda item: item['id'])
        grouped.setdefault(header['receipt_id'], []).append(entry)
    for ident, receipt in receipts.items():
        source, result = decoded(receipt['request_data']), decoded(receipt['result'])
        plan = sorted(grouped.get(ident, []), key=lambda entry: entry['store_id'])
        requested = source.get('handovers', [])
        if not plan and not requested and not result.get('handover_digest'):
            continue  # Old V2.16 archival evidence stays valid without invented handovers.
        offered = sorted(requested, key=lambda item: item['store_id'])
        if source.get('account_action') != 'archive' or offered != [
            {key: entry[key] for key in ('store_id','successor_id','successor_access_version')} for entry in plan]:
            raise ValueError('逐店员工交接与确认请求不一致')
        audit = audits.get(receipt['audit_id'])
        before = decoded(audit['before_data']) if audit else {}
        roles = {item['store_id']: item['role'] for item in before.get('store_roles', [])}
        if before.get('account_role') in {'admin', 'group_deputy_manager'}:
            roles.update({item['id']: before['account_role'] for item in before.get('stores', [])})
        if {entry['store_id']: entry['successor_role'] for entry in plan} != roles:
            raise ValueError('员工交接门店及岗位与归档前身份不一致')
        digest = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        summary = [{'store_id': entry['store_id'], 'successor_id': entry['successor_id'],
            'customer_count': len(entry['customers']), 'contract_count': len(entry['contracts'])} for entry in plan]
        if result.get('handover_digest') != digest or result.get('handover_summary') != summary:
            raise ValueError('员工交接内容与不可改写的归档回执不一致')
