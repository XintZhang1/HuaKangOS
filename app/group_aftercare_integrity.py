"""Offline explicit evidence bridge; no blanket cross-case attachment exemption."""
def aftercare_evidence_allowed(connection,kind,entry_id,source_case_id,evidence_id,store_id):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'group_aftercare_postings' not in names:return False
    row=connection.execute('''SELECT h.aftercare_case_id,h.source_case_id,h.store_id,h.status,p.evidence_id,p.store_id,
        f.case_id,f.store_id,f.generated,c.customer_id,s.customer_id,a.case_id
        FROM group_aftercare_postings p JOIN group_aftercare_holds h ON h.id=p.hold_id
        JOIN flow_files f ON f.id=p.evidence_id JOIN flow_cases c ON c.id=h.aftercare_case_id
        JOIN flow_cases s ON s.id=h.source_case_id JOIN aftercare_plans a ON a.id=h.plan_id
        WHERE p.kind=? AND p.entry_id=?''',(kind,entry_id)).fetchone()
    return bool(row and row[1]==source_case_id and row[2]==row[5]==row[7]==store_id and row[3]=='applied'
        and row[4]==evidence_id and row[0]==row[6]==row[11] and not row[8] and row[9]==row[10])


def validate_group_aftercare_sqlite(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'group_aftercare_holds' not in names:return {'verified_group_aftercare_returns':0}
    def rows(name):
        c=connection.execute('SELECT * FROM '+name);keys=[v[0] for v in c.description];return [dict(zip(keys,r)) for r in c]
    def keyed(name):return {r['id']:r for r in rows(name)}
    holds=keyed('group_aftercare_holds');postings=rows('group_aftercare_postings');cases=keyed('flow_cases');files=keyed('flow_files')
    plans=keyed('aftercare_plans');sources=keyed('aftercare_sources');tenders=rows('aftercare_tenders')
    originals={'principal':keyed('group_entries'),'benefit':keyed('benefit_entries')};rules=keyed('benefit_rules');wallets=keyed('benefit_wallets')
    for hold in holds.values():
        source=cases.get(hold['source_case_id']);case=cases.get(hold['aftercare_case_id']);plan=plans.get(hold['plan_id']);file=files.get(hold['evidence_id'])
        if not source or not case or not plan or not file or plan['case_id']!=case['id'] or file['case_id']!=case['id'] or source['customer_id']!=case['customer_id'] or any(r['store_id']!=hold['store_id'] for r in (source,case,file,plan)):
            raise ValueError('原核销退回方案、客户或批准凭据越店串单')
        tender=[t for t in tenders if t['plan_id']==hold['plan_id'] and t['kind']==hold['kind'] and t['original_id']==hold['original_id'] and sources[t['source_id']]['source_case_id']==source['id']]
        if len(tender)!=1 or (tender[0]['units'],tender[0]['credit_cents'])!=(hold['units'],hold['credit_cents']):raise ValueError('原核销退回占额偏离批准原路方案')
        original=originals[hold['kind']].get(hold['original_id'])
        if not original or original['purpose']!='capture' or (original['case_id'],original['store_id'])!=(source['id'],hold['store_id']):raise ValueError('原核销退回未关联本店原capture')
        if hold['kind']=='principal':expected_credit=hold['units'];discount=0;initial=-original['amount_cents']
        else:
            wallet=wallets[original['wallet_id']];rule=rules[wallet['rule_id']];initial=-original['units']
            expected_credit=hold['units']*rule['credit_cents_per_unit'];discount=hold['units']*(rule['credit_cents_per_unit']-(rule['sale_cents_per_unit'] if wallet['source_kind']=='purchase' else 0))
        if (hold['credit_cents'],hold['discount_cents'])!=(expected_credit,discount):raise ValueError('原核销退回未沿用冻结单位或优惠承担')
        related=[p for p in postings if p['hold_id']==hold['id']]
        if (hold['status']=='applied')!=(len(related)==1):raise ValueError('原核销退回状态与单次过账不一致')
        if related:
            p=related[0];entry=originals[p['kind']].get(p['entry_id'])
            if not entry or p['kind']!=hold['kind'] or entry['purpose']!='reverse' or entry['original_id']!=original['id'] or (entry['amount_cents'] if p['kind']=='principal' else entry['units'])!=hold['units'] or not aftercare_evidence_allowed(connection,p['kind'],p['entry_id'],source['id'],p['evidence_id'],hold['store_id']):
                raise ValueError('原核销售后实际回退流水、单位或执行凭据不一致')
        reversed_units=sum((e['amount_cents'] if hold['kind']=='principal' else e['units']) for e in originals[hold['kind']].values() if e['purpose']=='reverse' and e['original_id']==original['id'])
        reserved=sum(h['units'] for h in holds.values() if (h['kind'],h['original_id'],h['status'])==(hold['kind'],original['id'],'reserved'))
        if reversed_units+reserved>initial:raise ValueError('原核销已退回及在批额度超过原使用量')
    if any(p['hold_id'] not in holds for p in postings):raise ValueError('原核销退回无批准占额')
    return {'verified_group_aftercare_returns':len(postings)}
