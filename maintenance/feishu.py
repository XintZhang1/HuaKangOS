"""Feishu self-built application bot. Outbound HTTP + authenticated SDK WebSocket.
No custom-bot webhook and no public inbound endpoint.
"""
import hashlib
import json
import time
import uuid
import httpx
from .config import GateError
from .decisions import decide


class FeishuBot:
    def __init__(self,cfg): self.cfg=cfg;self.token='';self.expires=0
    def tenant_token(self):
        if time.monotonic()<self.expires: return self.token
        try:
            r=httpx.post('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
                json={'app_id':self.cfg.app_id,'app_secret':self.cfg.app_secret},timeout=15)
            r.raise_for_status();result=r.json()
            if result.get('code')!=0 or not result.get('tenant_access_token'): raise ValueError('provider')
            self.token=result['tenant_access_token'];self.expires=time.monotonic()+max(30,int(result.get('expire',7200))-120)
            return self.token
        except (httpx.HTTPError,ValueError,TypeError,KeyError) as exc: raise GateError('飞书应用认证失败，请检查应用凭据和状态') from exc
    def send(self,card,dedupe_key):
        receive=self.cfg.receive_id or self.cfg.approvers[0]
        message_id=str(uuid.uuid5(uuid.NAMESPACE_URL,dedupe_key))
        try:
            r=httpx.post('https://open.feishu.cn/open-apis/im/v1/messages',
                params={'receive_id_type':self.cfg.receive_id_type},headers={'Authorization':'Bearer '+self.tenant_token()},
                json={'receive_id':receive,'msg_type':'interactive','content':json.dumps(card,ensure_ascii=False),'uuid':message_id},timeout=20)
            r.raise_for_status();data=r.json()
            if data.get('code')!=0: raise ValueError('provider')
            return data.get('data',{}).get('message_id','')
        except (httpx.HTTPError,ValueError,TypeError) as exc: raise GateError('飞书卡片发送失败；任务保留，不会自动批准') from exc


def approval_card(row,token,rollback=False):
    def button(label,action,kind='default'):
        return {'tag':'button','text':{'tag':'plain_text','content':label},'type':kind,
            'value':{'job_id':row.id,'sha':row.head_sha,'token':token,'decision':action},
            'confirm':{'title':{'tag':'plain_text','content':'确认操作'},'text':{'tag':'plain_text','content':f'仅操作反馈 #{row.id} 的提交 {row.head_sha[:12]}，不代表允许其他改动。'}}}
    lines=[f'反馈 #{row.id} · {row.title}',f'候选提交：{row.head_sha}',f'基线：{row.base_sha}',
        '自动测试：通过（隔离执行；不能保证没有业务缺陷）', '修改文件：'+', '.join(row.proposal.get('files',[])),
        '改动摘要：'+row.proposal.get('summary',''), '批准只绑定此提交；主分支变化会阻止部署。',
        '操作：恢复上一运行版本（不会回退数据库）。' if rollback else '操作：批准后备份数据库、检查新版服务，再快进主分支并切换访问；异常恢复旧代码。']
    # User/model prose is plain text, never card-markdown or executable action data.
    actions=[button('回滚到上一版本','rollback','danger')] if rollback else [button('批准并发布','approve','primary'),button('拒绝','reject','danger')]
    if row.review_url.startswith('https://'):
        actions.insert(0,{'tag':'button','text':{'tag':'plain_text','content':'查看 Git Diff'},'url':row.review_url})
    return {'config':{'wide_screen_mode':True},'header':{'template':'green' if rollback else 'orange',
        'title':{'tag':'plain_text','content':'DealerDesk · 已发布 / 可回滚' if rollback else 'DealerDesk · 等待代码发布审批'}},
        'elements':[{'tag':'div','text':{'tag':'plain_text','content':'\n\n'.join(lines)[:6500]}},{'tag':'action','actions':actions}]}


STATUS_LABEL={'proposing':'DeepSeek 分析中','testing':'隔离测试中','approved':'已自动审核通过，等待维护时段发布',
    'deploying':'发布中','deployed':'已发布','manual':'超出自动维护范围，需要人工开发','failed':'处理失败',
    'rejected':'已拒绝','expired':'审批已过期','superseded':'基线已变化，需重做','rolled_back':'已回滚','new':'已收集','queued':'等待处理'}


def status_card(row):
    summary=(row.proposal or {}).get('summary','') if isinstance(row.proposal,dict) else ''
    files=(row.proposal or {}).get('files') or [] if isinstance(row.proposal,dict) else []
    lines=[f'反馈 #{row.id} · {row.title}',
        '状态：'+(STATUS_LABEL.get(row.status,row.status)),
        (row.last_error or summary or '').strip(),
        ('改动文件：'+', '.join(files)) if files else '',
        '当前系统未获批准时不会被覆盖。' if row.status not in {'deployed','rolled_back'} else '发布与回滚都不会改动业务数据库。']
    elements=[{'tag':'div','text':{'tag':'plain_text','content':'\n'.join(x for x in lines if x)[:4000]}}]
    actions=[]
    if str(getattr(row,'review_url','') or '').startswith('https://'):
        actions.append({'tag':'button','text':{'tag':'plain_text','content':'查看 Git 改动 / 建 MR'},
                        'url':row.review_url})
    if actions: elements.append({'tag':'action','actions':actions})
    return {'config':{'wide_screen_mode':True},
        'header':{'template':'blue' if row.status not in {'failed','manual'} else 'orange',
                  'title':{'tag':'plain_text','content':f'DealerDesk · 反馈 #{row.id} 处理结果'}},
        'elements':elements}


def listen(cfg):
    try:
        import lark_oapi as lark
        from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse
    except ImportError as exc: raise GateError('请安装 requirements-maintenance.txt 中的飞书 SDK') from exc
    def on_card(data):
        try:
            event=data.event;value=event.action.value
            if not isinstance(value,dict): raise GateError('无效卡片数据')
            header=getattr(data,'header',None)
            # SDK event headers normally carry event_id; callback token is a stable
            # fallback for duplicate delivery. It is NOT used as authentication.
            callback_id=getattr(header,'event_id',None) or getattr(event,'token',None)
            if not callback_id: raise GateError('回调缺少去重标识')
            result=decide(cfg,event.operator.open_id,int(value['job_id']),str(value['sha']),str(value['token']),
                str(value['decision']),str(callback_id),getattr(header,'tenant_key','') or '')
            return P2CardActionTriggerResponse({'toast':{'type':'success','content':result}})
        except (GateError,ValueError,KeyError,AttributeError,TypeError) as exc:
            message=str(exc) if isinstance(exc,GateError) else '卡片请求无效'
            return P2CardActionTriggerResponse({'toast':{'type':'error','content':message}})
        except Exception:
            return P2CardActionTriggerResponse({'toast':{'type':'error','content':'审批写入暂时失败，请刷新核对状态后重试'}})
    handler=lark.EventDispatcherHandler.builder('','').register_p2_card_action_trigger(on_card).build()
    client=lark.ws.Client(cfg.app_id,cfg.app_secret,event_handler=handler,log_level=lark.LogLevel.WARNING)
    client.start()
