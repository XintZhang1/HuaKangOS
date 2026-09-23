"""Independent SQLite replay of immutable search and reappearance sources.

These are workflow facts only; no new loss, stock or actual cash is synthesized.
The checks establish internal consistency, not an external signature against a
privileged administrator rewriting all originals and their verification data.
"""
from collections import defaultdict
from datetime import datetime


def validate_transfer_goods_searches(connection):
    names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required = {'transfer_goods_searches', 'transfer_goods_search_reviews',
        'transfer_goods_search_outcomes', 'transfer_goods_reappearances'}
    empty = {'found_searches': 0, 'found_reappearances': 0}
    if not names & required:
        if 'transfer_goods_recoveries' in names and connection.execute(
            "SELECT id FROM transfer_goods_recoveries WHERE status='unlocated' LIMIT 1").fetchone():
            raise ValueError('原物资查找：结束查找状态缺少原查找表')
        return empty
    if not required <= names:
        raise ValueError('原物资查找：来源表不完整')

    def rows(name):
        cursor = connection.execute('SELECT * FROM "' + name + '"')
        keys = [r[0] for r in cursor.description]
        return [dict(zip(keys, r)) for r in cursor]
    def index(name):
        return {r['id']: r for r in rows(name)}
    def check(ok, message):
        if not ok:
            raise ValueError('原物资查找：' + message)
    def at(value):
        return datetime.fromisoformat(value)

    headers = index('transfer_goods_recoveries'); parents = index('material_transfers')
    facts = index('transfer_goods_facts'); cases = index('flow_cases'); files = index('flow_files')
    searches = index('transfer_goods_searches'); reviews = index('transfer_goods_search_reviews')
    outcomes = index('transfer_goods_search_outcomes'); links = index('transfer_goods_reappearances')
    postings = rows('transfer_goods_postings')
    by_root = defaultdict(list); by_search = defaultdict(list); ended = {}
    for search in searches.values(): by_root[search['recovery_id']].append(search)
    for review in reviews.values(): by_search[review['search_id']].append(review)
    for result in outcomes.values():
        check(result['search_id'] not in ended, '同一查找有两个结束结果')
        ended[result['search_id']] = result
    check(all(r['search_id'] in searches for r in reviews.values()), '独立复核无原查找')
    check(all(r['search_id'] in searches for r in outcomes.values()), '结束结果无原查找')

    def own_case(record, parent):
        party_cases = {parent['from_store_id']: parent['from_case_id'], parent['to_store_id']: parent['to_case_id']}
        case = cases.get(record['case_id'])
        check(record['store_id'] in party_cases and party_cases[record['store_id']] == record['case_id']
            and case and case['store_id'] == record['store_id'], '查找来源原单或门店不一致')
    def proof(record, parent):
        own_case(record, parent)
        file = files.get(record['evidence_id'])
        check(file and not file['generated'] and file['case_id'] == record['case_id']
            and file['store_id'] == record['store_id'] and file['category'] in {'evidence', 'inspection', 'authorization'},
            '查找或复核使用了其他原单、他店或非实际物理原件')

    for rid, history in by_root.items():
        root = headers.get(rid); parent = parents.get(root['transfer_id']) if root else None
        check(root and parent, '查找无原找回或原调拨')
        ordered = sorted(history, key=lambda r: r['revision'])
        check([r['revision'] for r in ordered] == list(range(1, len(ordered) + 1)), '查找版本断裂')
        own = [f for f in facts.values() if f['recovery_id'] == rid]
        shipped = [f for f in own if f['kind'] == 'ship']
        received = [f for f in own if f['kind'] == 'receive']
        check(len(shipped) == 1, '查找没有唯一实际原退运')
        previous_end = None
        for search in ordered:
            proof(search, parent)
            check(at(shipped[0]['created_at']) <= at(search['created_at']) and
                not any(at(f['created_at']) <= at(search['created_at']) for f in received), '查找早于原退运或已实际到货')
            if search['revision'] > 1:
                check(previous_end and previous_end['kind'] == 'rejected' and
                    at(previous_end['created_at']) <= at(search['created_at']), '新查找未接原未批准版本')
            rs = sorted(by_search[search['id']], key=lambda r: r['id'])
            check(len(rs) <= 2 and len({r['store_id'] for r in rs}) == len(rs)
                and len({r['actor_id'] for r in rs}) == len(rs), '两店复核重复或同一人员代签')
            blocked = {root['requested_by'], search['requested_by']} | {
                f['actor_id'] for f in own if at(f['created_at']) <= at(search['created_at'])}
            end = ended.get(search['id'])
            for review in rs:
                proof(review, parent)
                check(review['actor_id'] not in blocked and review['decision'] in {'end_search', 'keep_searching'}
                    and at(review['created_at']) >= at(search['created_at']), '主管复核与事实申报不独立或早于申报')
                check(not end or at(review['created_at']) <= at(end['created_at']), '查找结束后又补复核')
            if end is None:
                check(search == ordered[-1] and root['status'] == 'transit' and not received
                    and len(rs) < 2 and all(r['decision'] == 'end_search' for r in rs), '在办查找与原到货状态冲突')
            else:
                own_case(end, parent)
                check(at(end['created_at']) >= at(search['created_at']), '结果早于实际查找')
                if end['kind'] == 'arrived':
                    fact = facts.get(end['receive_fact_id'])
                    check(fact and end['review_id'] is None and fact['recovery_id'] == rid and fact['kind'] == 'receive'
                        and (fact['store_id'], fact['actor_id'], fact['business_date']) ==
                        (end['store_id'], end['actor_id'], end['business_date'])
                        and at(fact['created_at']) >= at(search['created_at'])
                        and at(end['created_at']) >= at(fact['created_at'])
                        and len(rs) < 2 and all(r['decision'] == 'end_search' for r in rs), '实际到货结束查找没有原接收事实')
                else:
                    check(end['kind'] in {'unlocated', 'rejected'} and rs and end['receive_fact_id'] is None,
                        '结束查找结果类型或批准来源不一致')
                    last = rs[-1]
                    check(end['review_id'] == last['id'] and
                        (end['store_id'], end['case_id'], end['actor_id'], end['business_date']) ==
                        (last['store_id'], last['case_id'], last['actor_id'], last['business_date']), '查找结果未追最后一次实际独立复核')
                    if end['kind'] == 'unlocated':
                        check(len(rs) == 2 and {r['store_id'] for r in rs} == {parent['from_store_id'], parent['to_store_id']}
                            and all(r['decision'] == 'end_search' for r in rs) and not received
                            and root['status'] == 'unlocated' and root['active_transfer_id'] is None
                            and not any(p['recovery_id'] == rid for p in postings), '结束查找缺双方批准或伪装库存恢复/新损失')
                    else:
                        check(last['decision'] == 'keep_searching' and all(r['decision'] == 'end_search' for r in rs[:-1])
                            and not any(at(f['created_at']) <= at(end['created_at']) for f in received), '退回查找没有对应独立拒绝')
            previous_end = end
    for root in headers.values():
        if root['status'] == 'unlocated':
            history = by_root[root['id']]
            check(history and ended.get(max(history, key=lambda r: r['revision'])['id'], {}).get('kind') == 'unlocated',
                '仍未找到状态缺少本次双方独立查找结果')

    children = defaultdict(list); seen = set()
    for link in sorted(links.values(), key=lambda r: r['id']):
        previous = headers.get(link['previous_recovery_id']); child = headers.get(link['recovery_id'])
        search = searches.get(link['search_id']); end = ended.get(link['search_id'])
        check(previous and child and search and end and end['kind'] == 'unlocated'
            and search['recovery_id'] == previous['id'] and previous['status'] == 'unlocated'
            and (previous['transfer_id'], previous['loss_id']) == (child['transfer_id'], child['loss_id'])
            and previous['id'] < child['id'] and child['id'] not in seen, '再次找到未关联同一损失原查找或形成循环重复来源')
        parent = parents[previous['transfer_id']]; proof(link, parent)
        found = [f for f in facts.values() if f['recovery_id'] == child['id'] and f['kind'] == 'found']
        check(len(found) == 1 and link['quantity_milli'] == child['quantity_milli'] > 0
            and (link['store_id'], link['actor_id'], link['evidence_id'], link['business_date']) ==
            (found[0]['store_id'], found[0]['actor_id'], found[0]['evidence_id'], found[0]['business_date'])
            and at(end['created_at']) <= at(child['created_at']) <= at(link['created_at']), '再次找到数量、时间或本人实际原件不一致')
        prior_links = children[previous['id']]
        used = link['quantity_milli']
        for prior in prior_links:
            cancellations = [f for f in facts.values() if f['recovery_id'] == prior['recovery_id'] and f['kind'] == 'cancel']
            if not any(at(f['created_at']) <= at(link['created_at']) for f in cancellations):
                used += prior['quantity_milli']
        check(used <= previous['quantity_milli'], '同次原查找的再次找到数量被重复消耗')
        prior_links.append(link); seen.add(child['id'])
    return {'found_searches': len(searches), 'found_reappearances': len(links)}
