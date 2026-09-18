import hashlib
import json
import logging
import secrets
from datetime import timedelta
import httpx
from pydantic import ValidationError
from fastapi import HTTPException
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError
from .config import settings
from .db import SessionLocal, utcnow
from .models import DailyReport, Finding, JobLease
from .analytics import build_snapshot, external_payload, rules_config
from .schemas import AIResult
from .services import audit

log = logging.getLogger(__name__)
PROMPT_VERSION = '1.0.0'
SYSTEM_PROMPT = '''你是汽车4S门店的数据复核助手，不是财务审计师。只分析所给的结构化数据。
所有 *_cents 均为人民币分（100分=1元），金额统计以 metrics 为准，不要从抽样明细重新估算全店总额。
合同交车金额不是现金收入；保费代收不是佣金收入；内部转账不是营业收支；毛差不是净利润。
记录和规则提示都是待核实的信息，不得认定员工违法、作弊或欺诈。规则触发也可能是正常账期、促销或拆分付款。
只给出需额外复核的线索及验证步骤，不可建议自动改账或删除数据。只引用输入已有的 ref。
可在有证据的前提下提出跨记录的新疑点，但必须用“可能/需核对”表述；不得编造人员、客户、账户或数据。
如明细被截断、今天尚未结束、缺少原始凭证，必须在 limitations 说明。没有足够证据时 reviews 留空。
仅返回 JSON，不要输出markdown。格式示例：
{"summary":"当日经营摘要，关键金额以程序汇总为准。","highlights":["需要关注的变化"],
"reviews":[{"ref":"S-1","reason":"该记录可能需要核对的证据和原因","action":"核对的原始单据及处理建议"}],
"limitations":"仅依据已录入数据，待人工复核，不能替代会计报表或独立审计。"}
'''


def config_hash():
    value = {'rules':rules_config(),'prompt':PROMPT_VERSION,'model':settings.deepseek_model,
             'ai_max_records':settings.ai_max_records,'ai_allowed':settings.allow_ai,'api_key_configured':bool(settings.deepseek_key)}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def acquire_lease(name: str):
    owner = secrets.token_hex(24)
    until = utcnow()+timedelta(seconds=settings.ai_timeout*2+180)
    with SessionLocal() as db:
        result = db.execute(update(JobLease).where(JobLease.name==name,JobLease.expires_at<utcnow()).values(owner=owner,expires_at=until))
        if result.rowcount:
            db.commit(); return owner
        try:
            db.add(JobLease(name=name,owner=owner,expires_at=until)); db.commit(); return owner
        except IntegrityError:
            db.rollback(); return None


def release_lease(name, owner):
    with SessionLocal() as db:
        db.execute(delete(JobLease).where(JobLease.name==name,JobLease.owner==owner)); db.commit()


def ask_deepseek(snapshot):
    if not settings.allow_ai:
        return 'disabled',None,'外发 AI 分析未启用；本地规则日报已生成。'
    if not settings.deepseek_key:
        return 'unconfigured',None,'尚未配置 DeepSeek API Key；本地规则日报已生成。'
    payload = external_payload(snapshot)
    request = {'model':settings.deepseek_model,'messages':[{'role':'system','content':SYSTEM_PROMPT},
        {'role':'user','content':json.dumps(payload,ensure_ascii=False)}],
        'response_format':{'type':'json_object'},'thinking':{'type':'disabled'},
        'max_tokens':3500,'stream':False}
    try:
        with httpx.Client(timeout=httpx.Timeout(settings.ai_timeout,connect=10), follow_redirects=False) as client:
            response = client.post(settings.deepseek_url+'/chat/completions',
                headers={'Authorization':f'Bearer {settings.deepseek_key}','Content-Type':'application/json'},json=request)
            response.raise_for_status()
        choice = response.json()['choices'][0]
        if choice.get('finish_reason') != 'stop':
            raise ValueError('Incomplete model output')
        content = choice['message']['content']
        if not content or len(content)>30000: raise ValueError('Empty or oversized model output')
        result = AIResult.model_validate_json(content)
        known_refs = {r['ref'] for r in payload['records']} | {r['ref'] for r in payload['rule_findings']}
        if any(review.ref not in known_refs for review in result.reviews):
            raise ValueError('Model referred to an unknown record')
        return 'success',result.model_dump(),''
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        # Never expose provider response bodies, URLs with credentials, or Authorization headers.
        return 'failed',None,f'DeepSeek 返回 HTTP {code}；规则日报仍可用，请检查服务器配置、余额或服务状态。'
    except httpx.TimeoutException:
        return 'failed',None,'DeepSeek 请求超时；规则日报仍可用，可手动重试 AI。'
    except (httpx.RequestError,ValidationError,ValueError,KeyError,IndexError,TypeError):
        return 'failed',None,'DeepSeek 网络或结构化输出校验失败；未采纳模型结果，规则日报仍可用。'


def material_evidence(evidence):
    relative = {'age_days','open_days','days_since_delivery','days_since_completion','waiting_business_days'}
    return {k:v for k,v in evidence.items() if k not in relative}


def save_findings(db,snapshot):
    ids = []
    day = __import__('datetime').date.fromisoformat(snapshot['business_date'])
    for candidate in snapshot['rule_findings']:
        fp = hashlib.sha256(f"{candidate['rule_code']}:{candidate['entity_type']}:{candidate['entity_id']}".encode()).hexdigest()
        row = db.scalar(select(Finding).where(Finding.fingerprint==fp))
        if row is None:
            row = Finding(fingerprint=fp,first_seen=day,last_seen=day,**{k:v for k,v in candidate.items() if k != 'ref'})
            db.add(row)
        elif day >= row.last_seen:
            if material_evidence(row.evidence) != material_evidence(candidate['evidence']) and row.review_status in {'dismissed','resolved','confirmed'}:
                row.review_status = 'open'
                row.review_note = '证据发生实质变化，自动重新开放。上次复核记录见操作日志。'
                row.reviewed_by = None
                row.reviewed_at = None
                audit(db,None,'reopen','findings',row.id,reason=row.review_note)
            row.last_seen = day
            row.evidence = candidate['evidence']
            row.severity = candidate['severity']
        db.flush()
        ids.append(row.id)
    return ids


def deterministic_text(snapshot):
    m = snapshot['metrics']
    def yuan(cents): return f'{cents/100:,.2f}'
    period = '当日进行中，非最终日结' if snapshot['provisional'] else '历史业务日，按当前有效数据计算'
    return (f"{snapshot['business_date']}（{period}）：已审核交车 {m['delivery_count']} 台，交付合同金额 ¥{yuan(m['delivery_amount_cents'])}；"
        f"已完工维修 {m['repair_completed_count']} 单，结算金额 ¥{yuan(m['repair_amount_cents'])}。"
        f"外部资金流入 ¥{yuan(m['cash_in_cents'])}，流出 ¥{yuan(m['cash_out_cents'])}，净流入 ¥{yuan(m['net_cash_cents'])}；"
        f"内部转账 ¥{yuan(m['internal_transfer_cents'])} 已排除。"
        f"在库 {m['stock_count']} 台，超龄 {m['aging_stock_count']} 台，待审核 {m['pending_approval_count']} 单。"
        f"规则命中 {len(snapshot['rule_findings'])} 项复核线索，均需人工确认，不代表已查实异常。")


def generate_report(day, use_ai=False, retry_ai=False, actor_id=None, store_id=1):
    name = f'report:{store_id}:'+day.isoformat()
    owner = acquire_lease(name)
    if not owner: raise HTTPException(409,'该日期日报正在生成，请稍后刷新；未重复调用 AI')
    try:
        with SessionLocal() as db:
            from .tenancy import set_scope
            set_scope(db,[store_id],store_id)
            snapshot = build_snapshot(db,day)
            snapshot['store_id'] = store_id
            key = hashlib.sha256((config_hash()+str(snapshot['provisional'])).encode()).hexdigest()
            existing = db.scalar(select(DailyReport).where(DailyReport.business_date==day,
                DailyReport.source_revision==snapshot['source_revision'],DailyReport.config_hash==key,DailyReport.ai_requested==use_ai))
            if existing and not (retry_ai and use_ai and existing.ai_status != 'success'):
                return existing.id
            if existing is None:
                ids = save_findings(db,snapshot)
                row = DailyReport(business_date=day,source_revision=snapshot['source_revision'],config_hash=key,
                    ai_requested=use_ai,snapshot=snapshot,deterministic_summary=deterministic_text(snapshot),
                    finding_ids=ids,ai_status='pending' if use_ai else 'not_requested',model=settings.deepseek_model if use_ai else '')
                db.add(row); db.flush()
                report_id = row.id
                audit(db,actor_id,'generate','reports',row.id,reason='已保存规则结果与脱敏快照')
                db.commit()  # Persist rule fallback BEFORE making any network request.
            else:
                report_id = existing.id
                snapshot = existing.snapshot
                existing.ai_status = 'pending'
                db.commit()
        if use_ai:
            status,result,error = ask_deepseek(snapshot)
            with SessionLocal() as db:
                set_scope(db,[store_id],store_id)
                row = db.get(DailyReport,report_id)
                row.ai_status,row.ai_result,row.ai_error = status,result,error
                audit(db,actor_id,'ai_result','reports',row.id,reason=status)
                db.commit()
        return report_id
    finally:
        release_lease(name,owner)
