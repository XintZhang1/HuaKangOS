"""Only explicit validated finance batches may distribute one cash fact across cases."""
from collections import defaultdict
import json


def validate_payment_cash(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'flow_payment_links' not in names:return {'verified_payment_cash_links':0}
    from .business_finance_partial_integrity import validate_partial_corrections_sqlite
    retained=validate_partial_corrections_sqlite(connection)['batch_retained']
    def rows(name):
        cursor=connection.execute('SELECT * FROM '+name);keys=[c[0] for c in cursor.description]
        return [dict(zip(keys,row)) for row in cursor]
    def fail(condition):
        if not condition:raise ValueError('实际现金与业务分配不守恒或归属不一致')
    cash={r['id']:r for r in rows('cash_entries')};cases={r['id']:r for r in rows('flow_cases')};accounts={r['id']:r for r in rows('flow_accounts')}
    links=rows('flow_payment_links');groups=defaultdict(list)
    by_link={r['id']:r for r in links};refund_totals=defaultdict(int)
    member_entries=rows('flow_member_entries');members={r['id']:r for r in rows('flow_members')}
    for p in links:
        if p['direction']=='in':fail(p['original_id'] is None);continue
        fail(p['direction']=='out')
        if p['original_id'] is not None:
            original=by_link.get(p['original_id'])
            fail(original and original['direction']=='in' and original['case_id']==p['case_id'] and original['store_id']==p['store_id'] and original['account_id']==p['account_id'])
            refund_totals[original['id']]+=p['amount_cents']
        else:
            case=cases.get(p['case_id']);fail(case and case['kind']=='member_refund' and case['flow_version'] in {1,2})
            member_id=json.loads(case['data']).get('member_id');member=members.get(member_id)
            facts=[e for e in member_entries if e['case_id']==case['id'] and e['purpose']=='refund']
            own=[r for r in links if r['case_id']==case['id']]
            fail(member and member['customer_id']==case['customer_id'] and member['store_id']==case['store_id']==p['store_id'] and len(facts)==len(own)==1
                and facts[0]['member_id']==member_id and facts[0]['store_id']==case['store_id'] and -facts[0]['amount_cents']==p['amount_cents']==case['amount_cents'])
    for key,total in refund_totals.items():fail(total<=by_link[key]['amount_cents'])
    for p in links:groups[p['cash_id']].append(p)
    batches={r['cash_id']:r for r in rows('business_finance_cash_batches')} if 'business_finance_cash_batches' in names else {}
    allocations=defaultdict(list)
    if 'business_finance_cash_allocations' in names:
        for r in rows('business_finance_cash_allocations'):allocations[r['batch_id']].append(r)
    files={r['id']:r for r in rows('flow_files')}
    for cash_id,own in groups.items():
        original=cash.get(cash_id);fail(original is not None and original['approval_state']=='approved')
        for p in own:
            account=accounts.get(p['account_id']);case=cases.get(p['case_id'])
            fail(account and case and original['store_id']==p['store_id']==case['store_id']==account['store_id'] and p['amount_cents']>0
                and account['name']==original['account'] and p['direction']==original['direction'] and p['reference']==original['voucher_no'] and p['business_date']==original['business_date'])
        batch=batches.get(cash_id)
        if not batch:fail(len(own)==1 and own[0]['amount_cents']==original['amount_cents']);continue
        case=cases.get(batch['case_id']);file=files.get(batch['evidence_id']);assigned=allocations[batch['id']]
        fail(case and case['kind']=='business_finance' and case['flow_version']==2 and case['store_id']==batch['store_id']==original['store_id'])
        fail(file and file['case_id']==case['id'] and file['store_id']==case['store_id'] and not file['generated'] and file['category']=='receipt')
        fail(batch['amount_cents']==original['amount_cents']==sum(p['amount_cents'] for p in own)+retained.get(batch['id'],0))
        fail(len(assigned)==len(own) and {a['payment_link_id'] for a in assigned}=={p['id'] for p in own})
        byid={p['id']:p for p in own}
        for a in assigned:
            p=byid[a['payment_link_id']];fail(a['store_id']==p['store_id'] and a['case_id']==p['case_id'] and a['amount_cents']==p['amount_cents'])
        fail(batch['kind'] in {'collection','correction_record','correction_reverse','supplier_refund'} and original['direction']==('out' if batch['kind'] in {'correction_reverse','supplier_refund'} else 'in'))
    fail(set(batches)<=set(groups)|{key for key,b in batches.items() if retained.get(b['id'])==b['amount_cents']})
    return {'verified_payment_cash_links':len(links)}


def finance_payment_evidence_allowed(connection,payment_link_id,case_id,evidence_id):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'business_finance_cash_allocations' not in names:return False
    return bool(connection.execute('''SELECT a.id FROM business_finance_cash_allocations a
        JOIN business_finance_cash_batches b ON b.id=a.batch_id JOIN flow_payment_links p ON p.id=a.payment_link_id
        JOIN flow_cases c ON c.id=a.case_id JOIN flow_files f ON f.id=b.evidence_id
        WHERE a.payment_link_id=? AND a.case_id=? AND b.evidence_id=? AND b.cash_id=p.cash_id
        AND a.amount_cents=p.amount_cents AND a.case_id=p.case_id AND a.store_id=p.store_id
        AND b.store_id=a.store_id AND c.store_id=a.store_id AND f.store_id=a.store_id AND f.case_id=b.case_id''',
        (payment_link_id,case_id,evidence_id)).fetchone())
