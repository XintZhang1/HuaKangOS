"""Read-only reconstruction of insurance principal and independently confirmed income."""
import json,hashlib
from collections import defaultdict
from datetime import datetime,timezone

TABLES=('insurance_orders','insurance_quotes','insurance_reviews','insurance_consents','insurance_quote_cancellations','insurance_submissions','insurance_results','insurance_renewal_links','insurance_tenders','insurance_pass_entries','insurance_direct_entries','insurance_terminations','insurance_termination_reviews','insurance_termination_consents','insurance_termination_cancellations','insurance_termination_applications','insurance_customer_refunds','insurance_commissions','insurance_commission_reviews','insurance_commission_payments','insurance_requests')
def fail(text):raise ValueError('保险恢复检查：'+text)
def data(value):return json.loads(value) if isinstance(value,str) else value
def stamp(value):
    if not value:return datetime.min
    result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return result.astimezone(timezone.utc).replace(tzinfo=None) if result.tzinfo else result
def same(a,b):return bool(a and b and a['store_id']==b['store_id'])
def digest(action,value):
    return hashlib.sha256(json.dumps({'operation':action,'payload':value},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def load(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not set(TABLES)&names:return None
    if not set(TABLES)<=names:fail('独立保险表不完整')
    allnames=TABLES+('flow_cases','flow_events','flow_files','flow_payment_links','cash_entries','flow_accounts','business_finance_credit_links','business_finance_advance_entries','business_finance_advances','business_finance_cash_batches','business_finance_cash_allocations','business_finance_corrections','care_customer_vehicles','care_vehicle_observations','care_cases','master_insurers')
    result={}
    for name in allnames:
        fields='id,store_id,case_id,category,generated,sha256' if name=='flow_files' else '*'
        cursor=connection.execute('SELECT '+fields+' FROM '+name);cols=[c[0] for c in cursor.description]
        result[name]={r['id'] if 'id' in r else r['case_id']:r for row in cursor for r in [dict(zip(cols,row))]}
    return result
def items(b,name,**filters):return [r for r in b[name].values() if all(r[k]==v for k,v in filters.items())]
def first(b,name,**filters):return next(iter(items(b,name,**filters)),None)
def proof(b,fact,case_id,financial=False,central=False):
    file=b['flow_files'].get(fact['evidence_id']);case=b['flow_cases'].get(case_id)
    if not same(file,fact) or not same(case,fact) or file['generated'] or file['category']!=('receipt' if financial else 'authorization'):fail('实际凭据门店或类别不一致')
    if file['case_id']!=case_id:
        allocations=b['business_finance_cash_allocations'].values();batches=b['business_finance_cash_batches'];entries=b['business_finance_advance_entries']
        allowed=central and any(a['case_id']==case_id and batches.get(a['batch_id'],{}).get('evidence_id')==file['id'] and batches[a['batch_id']]['case_id']==file['case_id'] for a in allocations)
        allowed=allowed or central and any(c['case_id']==case_id and entries.get(c['entry_id'],{}).get('evidence_id')==file['id'] and entries[c['entry_id']]['case_id']==file['case_id'] for c in b['business_finance_credit_links'].values())
        if not allowed:fail('实际凭据不是本单或明确原资金分配的原件')
def case_for(b,quote_id):
    q=b['insurance_quotes'].get(quote_id)
    if not q:fail('报价来源不存在')
    return b['flow_cases'].get(q['case_id'])
def _credit(b,credit_id):
    t=first(b,'insurance_tenders',credit_link_id=credit_id)
    if not t or t['amount_cents']>=0:return False
    f=first(b,'insurance_customer_refunds',reversal_tender_id=t['id']);original=b['insurance_tenders'].get(t['original_id']);credit=b['business_finance_credit_links'].get(credit_id)
    if not f or not original or not original['credit_link_id'] or not credit:fail('保险原预收退回缺少原撤保分配')
    p=b['insurance_terminations'].get(f['plan_id']);review=first(b,'insurance_termination_reviews',plan_id=p['id']) if p else None;consent=first(b,'insurance_termination_consents',plan_id=p['id']) if p else None;applied=first(b,'insurance_termination_applications',plan_id=p['id']) if p else None
    if not all(same(x,t) for x in (f,original,credit,p,review,consent,applied)) or review['decision']!='approved' or review['actor_id']==p['actor_id'] or consent['digest']!=p['digest'] or p['case_id']!=t['case_id'] or original['case_id']!=t['case_id']:fail('预收退回的独立批准、客户本版同意或生效来源不一致')
    old=b['business_finance_credit_links'].get(original['credit_link_id']);entry=b['business_finance_advance_entries'].get(credit['entry_id']);old_entry=b['business_finance_advance_entries'].get(old['entry_id']) if old else None;advance=b['business_finance_advances'].get(entry['advance_id']) if entry else None
    if not all(same(x,t) for x in (old,entry,old_entry,advance)) or credit['original_id']!=old['id'] or entry['purpose']!='return' or entry['original_id']!=old_entry['id'] or entry['advance_id']!=old_entry['advance_id'] or credit['application_id']!=old['application_id'] or credit['amount_cents']!=t['amount_cents'] or entry['amount_cents']!=-t['amount_cents'] or f['amount_cents']!=-t['amount_cents'] or advance['customer_id']!=b['flow_cases'][t['case_id']]['customer_id'] or entry['evidence_id']!=t['evidence_id']:fail('原预收、抵用、回退金额或客户不守恒')
    if f['amount_cents']>sum(x['amount_cents'] for x in data(p['returns']) if x['tender_id']==original['id']):fail('预收回退超过本版原款分配')
    return True
def validate_insurance_credit_return(connection,credit_id):
    b=load(connection)
    return _credit(b,credit_id) if b else False

def validate_insurance_sqlite(connection):
    b=load(connection)
    if not b:return {'verified_insurance_orders':0}
    cases=b['flow_cases'];orders=b['insurance_orders'];quotes=b['insurance_quotes'];files=b['flow_files'];tenders=b['insurance_tenders'];passes=b['insurance_pass_entries'];plans=b['insurance_terminations'];cash=b['cash_entries'];payments=b['flow_payment_links'];credits=b['business_finance_credit_links'];accounts=b['flow_accounts']
    for o in orders.values():
        c=cases.get(o['id']);cv=b['care_customer_vehicles'].get(o['customer_vehicle_id']);snapshot=data(o['vehicle_snapshot'])
        if not same(c,o) or (c['kind'],c['flow_version'])!=('insurance',3) or len(o['vin'])!=17 or snapshot.get('vin')!=o['vin']:fail('原单身份或冻结 VIN 不一致')
        if cv and (not same(cv,c) or cv['customer_id']!=c['customer_id'] or cv['vin']!=o['vin']):fail('客户车辆身份不一致')
        parent=cases.get(o['source_order_id'])
        if o['source_order_id'] and (not same(parent,c) or parent['kind']!='order' or parent['customer_id']!=c['customer_id'] or c['parent_id']!=parent['id']):fail('保险关联销售跨客户或门店')
        if o['delivery_blocking'] and not parent:fail('交车门禁缺少原销售')
        renewal=first(b,'insurance_renewal_links',case_id=o['id']);previous=b['insurance_results'].get(renewal['previous_policy_id']) if renewal else None
        if renewal and (not same(renewal,c) or not same(previous,c) or previous['outcome']!='issued' or cases[previous['case_id']]['customer_id']!=c['customer_id'] or orders[previous['case_id']]['vin']!=o['vin']):fail('续保原保单不属于同客户 VIN')
        care=b['care_cases'].get(o['renewal_task_id'])
        if o['renewal_task_id'] and (not same(care,c) or care['subtype']!='renewal' or not cv or care['vehicle_id']!=cv['id'] or cases[care['case_id']]['customer_id']!=c['customer_id']):fail('续保原任务关联不一致')
    for q in quotes.values():
        c=cases.get(q['case_id']);o=orders.get(q['case_id']);lines=data(q['lines']);snap=data(q['insurer_snapshot'])
        if not same(c,q) or not o or not lines or any(type(x['premium_cents']) is not int or x['premium_cents']<=0 for x in lines) or len({x['name'].casefold() for x in lines})!=len(lines) or sum(x['premium_cents'] for x in lines)!=q['premium_cents'] or snap['id']!=q['insurer_id'] or not same(b['master_insurers'].get(q['insurer_id']),q):fail('险种保费或冻结保险公司不一致')
        facts={k:q[k] for k in ('expected_commission_cents','collection_mode','start_date','end_date','valid_until','terms','reason','premium_cents','revision')};facts.update(lines=lines,insurer_snapshot=snap,vin=o['vin'])
        if digest('insurance_quote',facts)!=q['digest'] or q['end_date']<q['start_date'] or (q['collection_mode']=='store_collect' and (not snap.get('account_name') or not snap.get('account_reference'))):fail('保险核价摘要、期间或收款户不一致')
    for r in b['insurance_reviews'].values():
        q=quotes.get(r['quote_id']);c=case_for(b,r['quote_id']);proof(b,r,c['id'])
        if not same(q,r) or q['actor_id']==r['actor_id']:fail('报价未独立审批')
    for r in b['insurance_consents'].values():
        q=quotes.get(r['quote_id']);review=first(b,'insurance_reviews',quote_id=r['quote_id']);proof(b,r,q['case_id'])
        if not same(q,r) or not same(review,r) or review['decision']!='approved' or r['digest']!=q['digest']:fail('客户授权不属于当前已批准报价摘要')
    for r in b['insurance_submissions'].values():
        q=quotes.get(r['quote_id']);proof(b,r,q['case_id'])
        if not same(q,r) or not first(b,'insurance_consents',quote_id=q['id']):fail('实际投保没有客户本版授权')
    for r in b['insurance_results'].values():
        submission=b['insurance_submissions'].get(r['submission_id']);q=quotes.get(submission['quote_id']) if submission else None;proof(b,r,r['case_id'])
        if not same(q,r) or q['case_id']!=r['case_id'] or q['insurer_id']!=r['insurer_id'] or bool(r['policy_number'])!=(r['outcome']=='issued'):fail('保险公司实际结果来源不一致')
        if r['observation_id']:
            obs=b['care_vehicle_observations'].get(r['observation_id']);o=orders[r['case_id']]
            if not same(obs,r) or obs['vehicle_id']!=o['customer_vehicle_id'] or obs['kind']!='insurance' or obs['valid_until']!=q['end_date'] or obs['evidence_id']!=r['evidence_id']:fail('新保单没有对应原期限登记')
    for t in tenders.values():
        proof(b,t,t['case_id'],True,True);c=cases.get(t['case_id']);link=payments.get(t['payment_link_id']) if t['payment_link_id'] else credits.get(t['credit_link_id'])
        amount=link['amount_cents']*(1 if link.get('direction','in')=='in' else -1) if link else 0
        if not same(link,t) or not same(c,t) or link['case_id']!=t['case_id'] or amount!=t['amount_cents']:fail('保费分配与原现金或预收金额不一致')
        if t['amount_cents']<0:
            old=tenders.get(t['original_id'])
            if not same(old,t) or old['case_id']!=t['case_id'] or old['amount_cents']<=0:fail('原客户款冲正来源不一致')
            if t['credit_link_id']:_credit(b,t['credit_link_id'])
            elif link['original_id']!=old['payment_link_id']:fail('客户退款未追原现金')
            elif not first(b,'insurance_customer_refunds',reversal_tender_id=t['id']):
                batch=first(b,'business_finance_cash_batches',cash_id=link['cash_id'])
                if not batch or not first(b,'business_finance_corrections',reversing_batch_id=batch['id']):fail('负保费既无撤保原退也无明确原收款更正')
    categories={'disburse':'workflow_ins_disburse','insurer_return':'workflow_ins_insurer_return','commission_receive':'workflow_ins_commission_in','commission_return':'workflow_ins_commission_out'}
    def check_cash(f,category,direction):
        record=cash.get(f['cash_id']);account=accounts.get(f['account_id'])
        if not same(record,f) or not same(account,f) or record['category']!=categories[category] or record['direction']!=direction or record['amount_cents']!=f['amount_cents'] or record['account']!=account['name'] or record['voucher_no']!=f['reference'] or record['business_date']!=f['business_date']:fail('实际现金与保险原事项不一致')
    for e in passes.values():
        t=tenders.get(e['tender_id']);proof(b,e,e['case_id'],True)
        if not same(t,e) or t['case_id']!=e['case_id'] or t['amount_cents']<=0:fail('代缴未使用本客户原资金')
        if t['payment_link_id']:account=payments[t['payment_link_id']]['account_id']
        else:account=b['business_finance_advances'][b['business_finance_advance_entries'][credits[t['credit_link_id']]['entry_id']]['advance_id']]['account_id']
        if e['account_id']!=account:fail('代缴账户未追原客户资金账户')
        check_cash(e,e['purpose'],'out' if e['purpose']=='disburse' else 'in')
        if e['purpose']=='insurer_return':
            old=passes.get(e['original_id'])
            if not same(old,e) or old['purpose']!='disburse' or old['tender_id']!=e['tender_id']:fail('保险公司退款没有追原代缴')
    for t in tenders.values():
        if t['amount_cents']<=0:continue
        refunded=-sum(x['amount_cents'] for x in tenders.values() if x['original_id']==t['id']);spent=sum(x['amount_cents']*(1 if x['purpose']=='disburse' else -1) for x in passes.values() if x['tender_id']==t['id'])
        if not 0<=spent<=t['amount_cents']-refunded:fail('原客户款、实际代缴及退回不守恒')
    for e in passes.values():
        if e['purpose']=='disburse' and sum(x['amount_cents'] for x in passes.values() if x['original_id']==e['id'])>e['amount_cents']:fail('保险公司超退原代缴')
    for p in plans.values():
        q=quotes.get(p['quote_id']);proof(b,p,p['case_id']);returns=data(p['returns']);v={k:p[k] for k in ('retained_cents','external_result','reason','evidence_id')};v.update(returns=returns,quote_id=p['quote_id'])
        if not same(q,p) or q['case_id']!=p['case_id'] or not 0<=p['retained_cents']<=q['premium_cents'] or len({x['tender_id'] for x in returns})!=len(returns) or digest('insurance_termination',v)!=p['digest']:fail('撤保方案摘要、保留额或原分配不一致')
        for x in returns:
            t=tenders.get(x['tender_id'])
            if not same(t,p) or t['case_id']!=p['case_id'] or t['amount_cents']<=0 or not 0<x['amount_cents']<=t['amount_cents']:fail('撤保原款分配不一致')
    for r in b['insurance_termination_reviews'].values():
        p=plans.get(r['plan_id']);proof(b,r,p['case_id'])
        if not same(p,r) or p['actor_id']==r['actor_id']:fail('撤保未独立审批')
    for r in b['insurance_termination_consents'].values():
        p=plans.get(r['plan_id']);review=first(b,'insurance_termination_reviews',plan_id=p['id']);proof(b,r,p['case_id'])
        if not same(p,r) or not same(review,r) or review['decision']!='approved' or p['digest']!=r['digest']:fail('客户撤保同意不是本版已批准方案')
    for a in b['insurance_termination_applications'].values():
        p=plans.get(a['plan_id']);proof(b,a,p['case_id'],True)
        if not same(a,p) or not first(b,'insurance_termination_consents',plan_id=p['id']) or first(b,'insurance_termination_cancellations',plan_id=p['id']):fail('未取得客户同意或已撤回却生效撤保')
        issued=[r for r in b['insurance_results'].values() if r['case_id']==p['case_id'] and r['outcome']=='issued' and stamp(r['created_at'])<=stamp(a['created_at'])]
        if issued and p['external_result']!='terminated':fail('已出保却按未出保终止')
    for f in b['insurance_customer_refunds'].values():
        p=plans.get(f['plan_id']);t=tenders.get(f['original_tender_id']);reverse=tenders.get(f['reversal_tender_id']);proof(b,f,p['case_id'],True)
        if not all(same(x,f) for x in (p,t,reverse)) or reverse['original_id']!=t['id'] or reverse['case_id']!=p['case_id'] or reverse['amount_cents']!=-f['amount_cents'] or not first(b,'insurance_termination_applications',plan_id=p['id']):fail('客户实退没有已生效原款方案')
        if sum(x['amount_cents'] for x in items(b,'insurance_customer_refunds',plan_id=p['id'],original_tender_id=t['id']))>sum(x['amount_cents'] for x in data(p['returns']) if x['tender_id']==t['id']):fail('客户原款退回超批准金额')
    for r in b['insurance_direct_entries'].values():
        proof(b,r,r['case_id'],True);q=quotes.get(data(cases[r['case_id']]['data']).get('insurance_quote_id'))
        if not same(q,r) or q['collection_mode']!='customer_direct':fail('非直付模式登记无现金直付')
        consent=first(b,'insurance_consents',quote_id=q['id'])
        if not consent or stamp(consent['created_at'])>stamp(r['created_at']):fail('客户直付登记早于本版授权')
        prior=sorted([x for x in items(b,'insurance_direct_entries',case_id=r['case_id']) if x['id']<r['id']],key=lambda x:x['id'])
        before=sum(x['amount_cents']*(1 if x['purpose']=='paid' else -1) for x in prior)
        effective=[p for p in items(b,'insurance_terminations',case_id=r['case_id']) if any(a['plan_id']==p['id'] and stamp(a['created_at'])<=stamp(r['created_at']) for a in b['insurance_termination_applications'].values())]
        if r['purpose']=='paid' and (effective or before+r['amount_cents']>q['premium_cents']):fail('客户直付超过授权保费或发生在撤保生效后')
        if r['purpose']=='returned':
            old=b['insurance_direct_entries'].get(r['original_id'])
            if not same(old,r) or old['case_id']!=r['case_id'] or old['purpose']!='paid' or sum(x['amount_cents'] for x in items(b,'insurance_direct_entries',original_id=old['id']))>old['amount_cents']:fail('客户直付退款超过原支付')
            if not effective or before-r['amount_cents']<effective[-1]['retained_cents']:fail('客户直退没有当时已生效撤保或超过应退额')
    for r in b['insurance_commissions'].values():
        proof(b,r,r['case_id'],True)
        prior=[c for c in items(b,'insurance_commissions',case_id=r['case_id']) if c['id']<r['id'] and first(b,'insurance_commission_reviews',confirmation_id=c['id'],decision='approved')]
        if r['previous_cents']!=(prior[-1]['target_cents'] if prior else 0):fail('佣金确认未追原累计结算额')
    for r in b['insurance_commission_reviews'].values():
        c=b['insurance_commissions'].get(r['confirmation_id']);proof(b,r,c['case_id'],True)
        if not same(c,r) or c['actor_id']==r['actor_id']:fail('实际佣金未独立审批')
    for r in b['insurance_commission_payments'].values():
        c=b['insurance_commissions'].get(r['confirmation_id']);review=first(b,'insurance_commission_reviews',confirmation_id=c['id']) if c else None;proof(b,r,r['case_id'],True)
        if not same(c,r) or c['case_id']!=r['case_id'] or not review or review['decision']!='approved':fail('佣金实际收退缺少独立确认依据')
        available=[x for x in items(b,'insurance_commissions',case_id=r['case_id']) if any(v['confirmation_id']==x['id'] and v['decision']=='approved' and stamp(v['created_at'])<=stamp(r['created_at']) for v in b['insurance_commission_reviews'].values())]
        if not available or available[-1]['id']!=c['id']:fail('佣金收退不是当时最近一次已批准实际结算')
        before=sum(x['amount_cents']*(1 if x['direction']=='in' else -1) for x in items(b,'insurance_commission_payments',case_id=r['case_id']) if x['id']<r['id'])
        if (r['direction']=='in' and before+r['amount_cents']>c['target_cents']) or (r['direction']=='out' and before-r['amount_cents']<c['target_cents']):fail('佣金收退超过当时已批准累计金额')
        check_cash(r,'commission_receive' if r['direction']=='in' else 'commission_return',r['direction'])
        if r['direction']=='out':
            old=b['insurance_commission_payments'].get(r['original_id'])
            if not same(old,r) or old['case_id']!=r['case_id'] or old['direction']!='in' or old['account_id']!=r['account_id'] or sum(x['amount_cents'] for x in items(b,'insurance_commission_payments',original_id=old['id']))>old['amount_cents']:fail('佣金退款未追原账户和实收金额')
    for o in orders.values():
        c=cases[o['id']];active=data(c['data']).get('insurance_quote_id');q=quotes.get(active)
        if active and (not same(q,c) or q['case_id']!=c['id'] or first(b,'insurance_quote_cancellations',quote_id=active) or c['amount_cents']!=(q['premium_cents'] if q['collection_mode']=='store_collect' else 0)):fail('当前保险报价指针或保费不一致')
        own=items(b,'insurance_tenders',case_id=c['id']);net=sum(t['amount_cents'] for t in own)
        if q and (net<0 or net>q['premium_cents'] or (q['collection_mode']=='customer_direct' and own)):fail('客户保费超过报价或直付混入门店资金')
    return {'verified_insurance_orders':len(orders),'verified_insurance_tenders':len(tenders),'verified_insurance_commissions':len(b['insurance_commissions'])}

def validate_parent_aftercare_exclusions(connection,parent_id,excluded_ids,requested_at=None):
    b=load(connection)
    if not b:
        if excluded_ids:fail('售后排除保险来源不存在')
        return True
    limit=stamp(requested_at) if requested_at else datetime.max;parent=b['flow_cases'].get(parent_id)
    if not parent or parent['kind']!='order':fail('保险售后排除缺少原销售')
    expected=[o['id'] for o in b['insurance_orders'].values() if o['source_order_id']==parent_id and stamp(b['flow_cases'][o['id']]['created_at'])<=limit]
    if sorted(expected)!=sorted(excluded_ids) or len(set(excluded_ids))!=len(excluded_ids):fail('保险排除清单与售后申请当时全部原保险不一致')
    for key in excluded_ids:
        o=b['insurance_orders'].get(key);c=b['flow_cases'].get(key)
        if not same(o,parent) or not same(c,parent) or o['source_order_id']!=parent_id or c['parent_id']!=parent_id or c['customer_id']!=parent['customer_id'] or stamp(c['created_at'])>limit:fail('售后排除不是当时已关联的保险')
        def before(name,**filters):return [r for r in items(b,name,**filters) if stamp(r.get('created_at'))<=limit]
        cancelled=any(e['case_id']==key and e['action']=='insurance_cancel' and stamp(e['occurred_at'])<=limit for e in b['flow_events'].values())
        own_quotes={q['id'] for q in before('insurance_quotes',case_id=key)}
        if cancelled:
            if before('insurance_tenders',case_id=key) or before('insurance_direct_entries',case_id=key) or any(s['quote_id'] in own_quotes for s in before('insurance_submissions')):fail('普通取消保险在当时已有实际资金或外部提交')
            continue
        plans=[p for p in before('insurance_terminations',case_id=key) if any(a['plan_id']==p['id'] for a in before('insurance_termination_applications'))]
        if not plans:fail('售后申请前保险尚未独立终止')
        for pending in before('insurance_terminations',case_id=key):
            if pending in plans or any(x['plan_id']==pending['id'] for x in before('insurance_termination_cancellations')) or any(x['plan_id']==pending['id'] and x['decision']=='rejected' for x in before('insurance_termination_reviews')):continue
            fail('申请时仍有未生效撤保方案')
        for plan in plans:
            reviews=[a for a in before('insurance_termination_reviews') if a['plan_id']==plan['id'] and a['decision']=='approved' and a['actor_id']!=plan['actor_id']]
            consents=[a for a in before('insurance_termination_consents') if a['plan_id']==plan['id'] and a['digest']==plan['digest']]
            if not reviews or not consents:fail('申请时撤保缺少独立复核或客户本版同意')
        retained=plans[-1]['retained_cents'];q=b['insurance_quotes'][plans[-1]['quote_id']]
        paid=sum(r['amount_cents'] for r in before('insurance_tenders',case_id=key));spent=sum(r['amount_cents']*(1 if r['purpose']=='disburse' else -1) for r in before('insurance_pass_entries',case_id=key));direct=sum(r['amount_cents']*(1 if r['purpose']=='paid' else -1) for r in before('insurance_direct_entries',case_id=key))
        if (q['collection_mode']=='store_collect' and (paid!=retained or spent!=retained)) or (q['collection_mode']=='customer_direct' and direct!=retained):fail('售后申请当时客户款或保险公司款未结清')
        approved=[r for r in before('insurance_commissions',case_id=key) if any(a['confirmation_id']==r['id'] and a['decision']=='approved' for a in before('insurance_commission_reviews'))]
        if any(not any(a['confirmation_id']==r['id'] for a in before('insurance_commission_reviews')) for r in before('insurance_commissions',case_id=key)):fail('申请时仍有未复核佣金结算')
        if not approved or stamp(approved[-1]['created_at'])<stamp(first(b,'insurance_termination_applications',plan_id=plans[-1]['id'])['created_at']):fail('售后前没有撤保后的实际佣金结算依据')
        net=sum(r['amount_cents']*(1 if r['direction']=='in' else -1) for r in before('insurance_commission_payments',case_id=key))
        if net!=approved[-1]['target_cents']:fail('售后申请当时佣金尚未结清')
    return True
