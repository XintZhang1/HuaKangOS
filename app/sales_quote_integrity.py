"""Read-only restore checks for frozen vehicle quotes and original money adjustments."""
import json,hashlib
from collections import defaultdict

TABLES=('sales_quotes','sales_quote_reviews','sales_quote_resolutions','sales_quote_consents','sales_vehicle_releases','sales_quote_adjustments')
def _rows(connection,table):
    cursor=connection.execute('SELECT * FROM '+table);names=[c[0] for c in cursor.description]
    return [dict(zip(names,row)) for row in cursor.fetchall()]
def _check(condition,message):
    if not condition:raise ValueError('车辆报价恢复校验：'+message)
def _same(*rows):return all(rows) and len({r['store_id'] for r in rows})==1
def _json(value):return json.loads(value) if isinstance(value,str) else value
def _context(connection):
    names=set(TABLES)|{'flow_cases','flow_files','vehicles','cash_entries','flow_payment_links','master_vehicle_models',
        'business_finance_credit_links','business_finance_advance_entries','business_finance_advances'}
    return {name:{r['id']:r for r in _rows(connection,name)} for name in names}

def _credit_return(data,credit_id):
    matches=[a for a in data['sales_quote_adjustments'].values() if a['credit_id']==credit_id]
    if not matches:return False
    _check(len(matches)==1,'同一预收抵用回退重复关联报价')
    adjustment=matches[0];quote=data['sales_quotes'].get(adjustment['quote_id']);credit=data['business_finance_credit_links'].get(credit_id)
    source=data['flow_cases'].get(quote['case_id']) if quote else None
    entry=data['business_finance_advance_entries'].get(credit['entry_id']) if credit else None
    original=data['business_finance_credit_links'].get(credit['original_id']) if credit else None
    advance=data['business_finance_advances'].get(entry['advance_id']) if entry else None
    approval=next((r for r in data['sales_quote_reviews'].values() if r['quote_id']==adjustment['quote_id']),None)
    activated=next((r for r in data['sales_quote_resolutions'].values() if r['quote_id']==adjustment['quote_id']),None)
    consent=next((r for r in data['sales_quote_consents'].values() if r['quote_id']==adjustment['quote_id'] and r['evidence_id']==adjustment['evidence_id']),None)
    evidence=data['flow_files'].get(adjustment['evidence_id'])
    _check(_same(adjustment,quote,source,credit,entry,original,advance,approval,activated,consent,evidence),'预收回退串店或缺少完整原单事实')
    _check(adjustment['kind']=='advance_return' and not adjustment['payment_id'] and credit['case_id']==source['id']==original['case_id']==entry['case_id'] and source['kind']=='order' and source['flow_version'] in (3,4),'预收回退原车辆业务不一致')
    _check(credit['amount_cents']==-adjustment['amount_cents'] and entry['amount_cents']==adjustment['amount_cents'] and entry['purpose']=='return' and not entry['cash_id'] and entry['original_id']==original['entry_id'] and original['amount_cents']>0 and advance['customer_id']==source['customer_id'],'预收回退未冲正确原客户原抵用')
    _check(approval['decision']=='approved' and approval['actor_id']!=quote['actor_id'] and activated['outcome']=='activated' and consent['actor_id']==adjustment['actor_id']==activated['actor_id'] and entry['evidence_id']==consent['evidence_id'],'预收回退缺少独立审批或本次客户签回')
    sourcefile=data['flow_files'].get(consent['source_file_id'])
    _check(_same(sourcefile,evidence) and sourcefile['generated'] and sourcefile['template_approved'] and evidence['case_id']==source['id'] and evidence['source_file_id']==sourcefile['id'] and evidence['category']=='signed_contract' and _json(sourcefile['snapshot']).get('报价校验摘要')==quote['digest'],'预收回退的客户签回未绑定批准报价')
    return True

def validate_sales_credit_return(connection,credit_id):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not set(TABLES)<=names:return False
    return _credit_return(_context(connection),credit_id)

def validate_sales_quotes_sqlite(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not set(TABLES)&names:return {'verified_sales_quotes':0}
    _check(set(TABLES)<=names,'报价表不完整')
    data=_context(connection);quotes=data['sales_quotes'];cases=data['flow_cases'];files=data['flow_files'];cars=data['vehicles']
    reviews={r['quote_id']:r for r in data['sales_quote_reviews'].values()};resolved={r['quote_id']:r for r in data['sales_quote_resolutions'].values()}
    consents=defaultdict(list);groups=defaultdict(list)
    for q in quotes.values():
        row=cases.get(q['case_id']);model=data['master_vehicle_models'].get(q['model_id']);snap=_json(q['model_snapshot'])
        _check(_same(q,row,model) and row['kind']=='order' and row['flow_version'] in (3,4) and snap['id']==q['model_id'] and snap['version']>0,'报价未关联同店车型和订单 v3')
        facts={k:q[k] for k in ('revision','prior_id','model_id','amount_cents','delivery_due','valid_until','terms','reason')}
        facts.update(model_snapshot=snap,services=_json(q['services']))
        _check(q['digest']==hashlib.sha256(json.dumps(facts,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'冻结报价摘要不一致')
        _check(q['amount_cents']>0 and set(facts['services'])=={'addon','insurance','agency'} and all(type(v) is bool for v in facts['services'].values()),'报价金额或配套服务冻结事实无效')
        groups[q['case_id']].append(q)
        r=reviews.get(q['id']);resolution=resolved.get(q['id'])
        if r:_check(_same(r,q) and r['actor_id']!=q['actor_id'] and r['decision'] in {'approved','rejected'},'缺少独立报价复核')
        if resolution:
            _check(_same(resolution,q) and resolution['outcome'] in {'activated','rejected','withdrawn'},'报价结果无效')
            if resolution['outcome']=='activated':_check(r and r['decision']=='approved','未经批准报价被激活')
            if resolution['outcome']=='rejected':_check(r and r['decision']=='rejected' and resolution['actor_id']==r['actor_id'],'报价退回与复核事实不一致')
    for consent in data['sales_quote_consents'].values():
        q=quotes.get(consent['quote_id']);source=files.get(consent['source_file_id']);proof=files.get(consent['evidence_id']);car=cars.get(consent['vehicle_id'])
        _check(_same(consent,q,source,proof,car),'客户确认串店或缺少报价、车辆、文件')
        snapshot=_json(source['snapshot']);resolution=resolved.get(q['id']);r=reviews.get(q['id'])
        _check(source['case_id']==proof['case_id']==q['case_id'] and source['category']=='contract' and source['generated'] and source['template_approved'] and not proof['generated'] and proof['category']=='signed_contract' and proof['source_file_id']==source['id'],'客户确认缺少真实签回和已批准源文件')
        _check(source['source_fingerprint']==consent['fingerprint']==hashlib.sha256(json.dumps(snapshot,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'签回文档快照摘要不一致')
        _check(snapshot.get('报价版本')==q['revision'] and snapshot.get('报价校验摘要')==q['digest'] and snapshot.get('车架号')==car['vin'] and snapshot.get('本版约定')==q['terms'],'签回未绑定本版车型、VIN及条款')
        _check(r and r['decision']=='approved' and resolution and resolution['outcome']=='activated','客户签回没有独立报价批准和激活')
        money=sum(p['amount_cents']*(1 if p['direction']=='in' else -1) for p in data['flow_payment_links'].values() if p['case_id']==q['case_id'] and data['cash_entries'][p['cash_id']]['created_at']<=consent['occurred_at'])
        credit=sum(c['amount_cents'] for c in data['business_finance_credit_links'].values() if c['case_id']==q['case_id'] and data['business_finance_advance_entries'][c['entry_id']]['occurred_at']<=consent['occurred_at'])
        _check(consent['paid_before_cents']==money+credit and consent['advance_before_cents']==credit,'客户签回时原款及预收快照与账本不一致')
        consents[q['id']].append(consent)
    for case_id,values in groups.items():
        row=cases[case_id];state=_json(row['data']);values.sort(key=lambda q:q['revision'])
        _check([q['revision'] for q in values]==list(range(1,len(values)+1)),'报价版本序列缺失')
        for q in values:
            previous=[p for p in values if p['id'] in resolved and resolved[p['id']]['outcome']=='activated' and resolved[p['id']]['occurred_at']<=q['occurred_at']]
            expected=max(previous,key=lambda p:resolved[p['id']]['occurred_at'])['id'] if previous else None
            _check(q['prior_id']==expected,'新报价未追溯当时有效的原版本')
        activated=[q for q in values if q['id'] in resolved and resolved[q['id']]['outcome']=='activated'];pending=[q for q in values if q['id'] not in resolved]
        _check(len(pending)<=1 and state.get('pending_quote_id')==(pending[0]['id'] if pending else None),'在办报价指针与历史不一致')
        latest=max(activated,key=lambda q:resolved[q['id']]['occurred_at']) if activated else None
        _check(state.get('active_quote_id')==(latest['id'] if latest else None),'生效报价指针与历史不一致')
        if latest:
            _check(row['amount_cents']==latest['amount_cents'] and row['due_date']==latest['delivery_due'] and state.get('model')==_json(latest['model_snapshot'])['name'],'原单车型或价格与最后生效报价不一致')
            _check(all(consents[q['id']] for q in activated),'生效报价缺少客户签回')
        if state.get('sales_consent_id'):
            c=data['sales_quote_consents'].get(state['sales_consent_id'])
            _check(c and latest and c['quote_id']==latest['id'] and c['vehicle_id']==row['vehicle_id'] and c['evidence_id']==state.get('signed_file'),'当前配车签回指针不一致')
    for release in data['sales_vehicle_releases'].values():
        q=quotes.get(release['quote_id']);r=reviews.get(release['quote_id']);proof=files.get(release['evidence_id']);car=cars.get(release['vehicle_id'])
        _check(_same(release,q,r,proof,car) and q['case_id']==release['case_id']==proof['case_id'] and r['decision']=='approved' and not proof['generated'],'配车释放缺少独立批准和本店实车凭据')
    for adjustment in data['sales_quote_adjustments'].values():
        q=quotes.get(adjustment['quote_id']);proof=files.get(adjustment['evidence_id'])
        _check(_same(adjustment,q,proof) and proof['case_id']==q['case_id'] and not proof['generated'],'报价调整缺少同店原业务凭据')
        if adjustment['kind']=='advance_return':_credit_return(data,adjustment['credit_id'])
        else:
            p=data['flow_payment_links'].get(adjustment['payment_id']);original=data['flow_payment_links'].get(p['original_id']) if p else None
            _check(_same(adjustment,p,original) and p['case_id']==original['case_id']==q['case_id'] and p['direction']=='out' and original['direction']=='in' and p['account_id']==original['account_id'] and p['amount_cents']==adjustment['amount_cents'],'退差额未按正确原款原账户处理')
    for q in quotes.values():
        own=[a for a in data['sales_quote_adjustments'].values() if a['quote_id']==q['id']]
        if not own:continue
        before=min(consents[q['id']],key=lambda c:c['occurred_at'])
        credit=sum(a['amount_cents'] for a in own if a['kind']=='advance_return')
        cash=sum(a['amount_cents'] for a in own if a['kind']=='cash_refund')
        _check(credit==max(0,before['advance_before_cents']-q['amount_cents']) and cash<=max(0,before['paid_before_cents']-credit-q['amount_cents']),'原款退差额超出本次确认价差或预收回退未守恒')
    return {'verified_sales_quotes':len(quotes),'verified_sales_quote_consents':len(data['sales_quote_consents'])}
