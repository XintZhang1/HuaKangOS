"""Business-only capability gateway. Never runs model code or arbitrary URLs.

All calls re-enter the ordinary HTTP endpoints with the current session, CSRF and
store, so their role checks, versions, ledgers and transactions remain authoritative.
"""
import copy
import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote
import httpx
from fastapi import HTTPException
from fastapi.routing import APIRoute
from pydantic import BaseModel, ValidationError
from starlette.routing import Match

DOMAINS = {
 'flow':'业务流程与本店资料', 'masters':'车型与基础资料', 'customer-choice':'查找客户',
 'vehicle-catalog':'车型展示与归属', 'sales-quotes':'车辆报价',
 'vehicle-procurement':'整车采购', 'procurement':'物资采购', 'warehouse':'仓储作业',
 'retail':'精品销售', 'retail-bundles':'精品套餐', 'repair-orders':'维修工单',
 'service-intake':'维修预约与到店', 'customer-service':'客户服务与车辆',
 'group':'集团会员本金', 'membership':'会员卡与续会', 'recharge-bundles':'充值套餐',
 'member-pricing':'会员价格', 'repair-packages':'维修套餐', 'retail-group':'会员精品付款',
 'aftercare':'退订退车', 'claims':'理赔与索赔', 'service-orders':'代办服务',
 'insurance-orders':'保险办理', 'addon-orders':'销售加装', 'vehicle-income':'厂家收入',
 'vehicle-operations':'整车出退库', 'transfers':'物资调拨', 'vehicle-transfers':'车辆调拨',
 'transfer-exceptions':'物资运输异常', 'transfer-goods-recoveries':'物资找回',
 'vehicle-transport-exceptions':'车辆运输异常', 'rework-extensions':'售后返修',
 'business-finance':'业务财务', 'invoices':'发票办理', 'reconciliation':'业务对账月结',
 'gate-visits':'车辆进出厂', 'dossier-grants':'跨店协同',
 'dictionaries':'分类设置', 'observation-corrections':'车辆信息更正',
 'inventory-reports':'整车库存报表', 'stock-reports':'物资库存报表',
 'repair-material-reports':'维修领退料报表', 'visit-activity-reports':'来访回访报表',
 'material-value':'物资成本报表', 'parameters':'设置入口', 'stores':'门店资料',
 'users':'员工账号', 'audit':'操作记录', 'business-entities':'经营主体与账户归属',
 'findings':'数据复核', 'reports':'每日汇总', 'dashboard':'经营看板',
 'records':'原有单据', 'lookup':'原有单据查询', 'vehicle-imports':'整车请款与批量导入',
 'escalations':'评审申请',
}
# Never exposed to the assistant, not even for reading: credentials, sessions, deployment
# settings, brand images, raw files, exports and initial-balance imports stay manual.
CLOSED_DOMAINS = {'auth', 'local-preview', 'branding', 'settings', 'business-assistant',
                  'export', 'health', 'workflow-guides', 'opening-import', 'records-download'}
# Static projection of the real checks for the management pages, so the assistant can answer
# "can I do this?" instead of guessing. None means the endpoint itself decides by role/store.
MANAGEMENT_READERS = {
 'users': {'admin'},
 'audit': {'admin', 'manager', 'auditor'},
 'business-entities': {'admin', 'manager', 'finance', 'auditor'},
 'findings': {'admin', 'manager', 'finance', 'auditor'},
 'reports': {'admin', 'manager', 'finance', 'auditor'},
 'dashboard': {'admin', 'manager', 'finance', 'auditor'},
 'stores': {'admin', 'manager', 'sales', 'inventory', 'service', 'finance', 'auditor',
            'reception', 'technician', 'customer_service'},
 'parameters': {'admin', 'manager', 'sales', 'inventory', 'service', 'finance', 'auditor',
                'reception', 'technician', 'customer_service'},
 'vehicle-imports': {'admin', 'manager', 'inventory', 'finance', 'auditor'},
}
# Credentials, external integrations, deployments, arbitrary legacy CRUD, raw file
# contents, initial balance imports and formal entity policy editors stay manual. `/example`
# covers the downloadable sample/template endpoints (text/csv attachments) that carry no
# export token in their path; tests/test_business_assistant_scope.py re-scans every GET
# handler and fails when a new file/CSV route is added without being excluded here.
DENIED = re.compile(r'/(?:files|download|export|opening|example)(?:/|$)|(?:\.csv|\.docx|\.pdf)$')
# Owner ruling 2026-09-25（覆盖 2026-09-24 的风险分级写法）：助手就以**员工本人身份**调用已评审的
# 业务接口，能办的就办、该连起来做的就连起来做；**权限由接口判定**，不再由助手的白名单/禁用词
# 预先代替接口做决定。被接口拒绝时提示"这一步需要更高权限，要不要提交评审申请"。仍然不放开的只有
# 两类**非业务**面（凭据与部署、原始文件与导出）和三个明确的人工动作位（见 CLASSIFIED_BLOCKED_WRITES）：
# 这些不是"步骤"，而是安全边界本身。原生接口的岗位、门店、状态、版本、证据与幂等始终是权威。
COMMITMENT_HINT = ('服务器已记录{reason}（被挡记录 {refusal_id}）。'
                   '请在原评审页面核对这条记录后由本人提交申请；评审不改变权限，也不代为执行业务。')
# Writes that are deliberately outside the assistant even though they are registered routes:
# accounts/credentials, store and legal-entity configuration, parameter rules, finding review,
# daily-report generation and the arbitrary legacy record CRUD.
CLASSIFIED_BLOCKED_WRITES = frozenset({
    'POST /api/users', 'POST /api/users/batch', 'PUT /api/users/{user_id}',
    'POST /api/users/{user_id}/password', 'POST /api/stores', 'PUT /api/stores/{store_id}',
    'POST /api/business-entities/applications',
    'POST /api/business-entities/applications/{case_id}/actions/{action}',
    'POST /api/findings/{finding_id}/review', 'POST /api/reports/generate', 'POST /api/reports/preview',
    'POST /api/records/{module}', 'PUT /api/records/{module}/{record_id}',
    'POST /api/records/{module}/{record_id}/actions/{action}',
    # Multipart upload of the imported document itself: files stay on the original page.
    'POST /api/vehicle-imports/orders/{case_id}/batches',
    # An employee may *submit* an escalation request; handling one (claim/done/reject/cancel) is
    # the superior's own act on the escalation page and is never prepared for them.
    'POST /api/escalations/{escalation_id}/actions/{action}',
})


def refusal_metadata(status, data):
    """Consume only the native HTTP handler's persisted refusal envelope."""
    if status not in {403,422} or not isinstance(data,dict):return None
    refusal=data.get('refusal')
    if not isinstance(refusal,dict):return None
    ident=refusal.get('id');category=refusal.get('category');allowed=refusal.get('can_escalate')
    if (type(ident) is not int or ident<=0 or type(category) is not str
            or category not in {'authority','amount','rule'} or type(allowed) is not bool):
        return None
    if category=='rule' and allowed:return None
    return {'id':ident,'category':category,'can_escalate':allowed}


def permission_hint(status, detail=''):
    """No text inference: an audited, eligible refusal is required for a hint."""
    refusal=refusal_metadata(status,detail)
    if not refusal or refusal['can_escalate'] is not True:return ''
    reason='岗位权限不足' if refusal['category']=='authority' else '金额或额度限制'
    return COMMITMENT_HINT.format(reason=reason,refusal_id=refusal['id'])

SECRET_KEYS = {'password','password_hash','new_password','current_password','api_key',
               'deepseek_key','token','access_token','refresh_token','authorization',
               'cookie','csrf','csrf_hash','session_id','content','blob','object_key','storage_path'}
FIELD_LABELS = {
 'values':'填写内容','quote':'报价','lines':'明细','kind':'业务类型','name':'名称','code':'代码',
 'customer_name':'客户姓名','customer_phone':'联系电话','phone':'联系电话','customer_id':'客户编号',
 'model':'车型','model_id':'车型编号','brand':'品牌','brand_id':'品牌编号','series_id':'车系编号',
 'model_year':'年款','fuel_type':'动力类型','seats':'座位数','battery_wh':'电池容量（瓦时）',
 'displacement_ml':'排量（毫升）','source':'客户来源','due_date':'办理日期','delivery_due':'交付日期',
 'valid_until':'有效期','amount':'金额（元）','amount_cents':'金额（分）','guide_price_cents':'指导价（分）',
 'quantity':'数量','quantity_milli':'数量（千分之一）','unit_cost_cents':'采购单价（分）',
 'unit_price_cents':'销售单价（分）','reason':'原因','note':'备注','result':'办理结果','terms':'约定',
 'assignee_id':'接手员工编号','account_id':'账户编号','evidence_id':'凭据编号',
 'reference':'流水或凭证号','version':'记录版本','request_id':'提交标识','active':'启用',
 'refund_policy':'退款政策','allowed_store_ids':'适用门店编号','discount_bearer':'优惠承担方',
 'validity_days':'有效天数','components':'套餐组件','specification':'规格或作业内容',
 'credit_cents':'面值（分）','paid_cents':'实付原价分摊（分）','settlement_cents':'结算金额（分）',
 'sale_starts_on':'发行开始日期','sale_ends_on':'发行结束日期','refund_terms':'退款条款',
 'mandatory_terms':'必须确认的条款','rule_id':'规则编号','rule_version':'规则版本',
 'dispatch_id':'原出库批次','payer_id':'核赔单位编号',
}
ROUTES = {
 'flow':'work','masters':'masters','vehicle-catalog':'vehicle-catalog','sales-quotes':'sales-quotes',
 'customer-service':'customer-service','customer-choice':'master/customers','group':'group',
 'membership':'membership','parameters':'parameters','stores':'stores',
}

@lru_cache(maxsize=1)
def _reviewed_operations():
    """Static reviewed capability boundary; adding an API never grants model access."""
    try:
        policy=json.loads(Path(__file__).with_name('business_assistant_capabilities.json').read_text(encoding='utf-8'))
        entries=policy['operations']
        if policy.get('version')!=1 or not isinstance(entries,list) or not entries or len(entries)!=len(set(entries)):
            raise ValueError('invalid policy')
        if any(not isinstance(item,str) or not re.fullmatch(r'(GET|POST|PUT) /api/[A-Za-z0-9_/{\}-]+',item) for item in entries):
            raise ValueError('invalid capability')
        return frozenset(entries)
    except (OSError,ValueError,TypeError,KeyError):
        raise HTTPException(503,'业务助手操作目录配置有误，请联系管理员检查') from None


@lru_cache(maxsize=1)
def _operations():
    """Queries follow the employee's own role scope; write operations stay reviewed-only.

    Everything a role can read in its own pages may be read by the assistant (the endpoint still
    enforces role, store scope and tenancy). Preparing writes beyond the reviewed list is a later,
    risk-classified step; approval/void actions stay on the original page.
    """
    from .main import app
    reviewed=_reviewed_operations()
    result={}
    for route in app.routes:
        if not isinstance(route,APIRoute) or not route.path.startswith('/api/'):continue
        domain=route.path.split('/')[2]
        if domain not in DOMAINS or domain in CLOSED_DOMAINS or DENIED.search(route.path):continue
        for method in sorted(route.methods & {'GET','POST','PUT'}):
            op_id=method+' '+route.path
            if method=='GET':
                if route.body_field:continue
            elif op_id not in reviewed:continue
            if domain in {'stores','parameters','users'} and method!='GET':continue
            if route.body_field and 'multipart/' in getattr(route.body_field.field_info,'media_type',''):continue
            # Structured financial/stock operations live in dedicated domains, not
            # legacy record edits; only declared JSON request bodies are accepted.
            if method!='GET' and route.body_field and not issubclass(route.body_field.type_,BaseModel):continue
            body_schema=route.body_field.type_.model_json_schema() if route.body_field else None
            props=(body_schema or {}).get('properties',{})
            module=route.path.split('/')[3] if domain in {'records','lookup'} and len(route.path.split('/'))>3 else None
            manual=ROUTES.get(domain,domain)
            if domain=='records' and module:manual='legacy/'+module
            elif domain=='lookup':manual='work'
            label=DOMAINS[domain]+' · '+('查询' if method=='GET' else '办理' if '/actions/' in route.path else '修改' if method=='PUT' else '新增')
            result[op_id]={'id':op_id,'label':label,'domain':domain,'description':route.summary or route.name,
                'method':method,'path':route.path,'write':method!='GET','module':module,
                'idempotent':method=='GET' or 'request_id' in props,
                'body_schema':body_schema,'route':route,
                'manual_route':manual}
    return result


def role_may_read(role,op):
    """True/False when a static rule exists; None when the endpoint decides by role and store."""
    if op['method']!='GET':return None
    if op['domain'] in {'records','lookup'}:
        from .security import READ
        module=op.get('module')
        if not module or module.startswith('{'):return None
        return module in READ.get(role,set())
    allowed=MANAGEMENT_READERS.get(op['domain'])
    if allowed is None:return None
    return role in allowed


def role_note(role,op):
    allowed=MANAGEMENT_READERS.get(op['domain'])
    if allowed is None:return ''
    if role in allowed:return ''
    from .security import ROLES
    return '这个入口只对%s开放。' % '、'.join(sorted(ROLES.get(item,item) for item in allowed))


def _declared_dispatch(op,path):
    """A wildcard must not resolve to a newer static route with broader powers."""
    from .main import app
    if DENIED.search(path):raise HTTPException(403,'此操作请在原业务页面办理，助手不能调用')
    scope={'type':'http','method':op['method'],'path':path,'root_path':''}
    for route in app.routes:
        match,_=route.matches(scope)
        if match is Match.FULL:
            if route is not op['route']:raise HTTPException(403,'实际操作与已审核目录不一致，请在原业务页面办理')
            return
    raise HTTPException(422,'此操作当前不可用，请刷新业务目录')

# 员工的说法 → 领域。目的只有一个：让助手先用员工的原话找到入口，而不是因为搜不到就回答
# "系统没有这个入口"（试用 R01 的 XC-ISSUE-003 与 2026-09-25 口语化探针 P15/P18/P19/P24/P25
# 都栽在这里）。这只是检索别名，不代表任何权限。
DOMAIN_ALIASES = {
    'procurement': ('采购', '买', '下单给供应商', '应付', '进货'),
    'transfers': ('调拨', '借', '调货', '调过去', '店间物资'),
    'vehicle-transfers': ('整车调拨', '车调过去', '调车'),
    'invoices': ('开票', '发票', '红冲', '抬头'),
    'users': ('账号', '员工账号', '停用账号', '离职', '权限'),
    'stores': ('门店', '门店设置'),
    'dashboard': ('销量', '卖得最好', '排行', '看板', '经营'),
    'reports': ('报表', '汇总', '日报', '统计'),
    'analytics': ('数据可视化', '图表', '统计'),
    'warehouse': ('仓库', '库位', '入库', '出库'),
    'stock-reports': ('库存报表', '进销存'),
    'inventory-reports': ('整车库存', '在库'),
    'repair-orders': ('维修', '工单', '开单', '修车'),
    'service-intake': ('预约', '到店', '洗车', '返修'),
    'sales-quotes': ('报价', '折扣', '定金', '合同', '订单'),
    'insurance-orders': ('保险', '续保', '保单'),
    'addon-orders': ('加装', '精品安装'),
    'retail': ('精品', '配件销售'),
    'membership': ('会员卡', '充值', '退卡', '会员'),
    'aftercare': ('退订', '退车', '退款'),
    'claims': ('理赔', '索赔', '报销'),
    'business-finance': ('收款', '付款', '记账', '财务'),
    'reconciliation': ('对账', '月结', '封账'),
    'dictionaries': ('字典', '分类设置'),
    'masters': ('主数据', '供应商', '保险公司', '班组', '作业项目'),
    'escalations': ('评审', '申请', '上级'),
    'flow': ('盘点', '领料', '退料', '报损', '借出', '归还', '工单动作'),
}


def catalog(domain='',query='',role=None):
    words=str(query).lower().strip().split()
    items=[]
    for op in _operations().values():
        if domain and domain not in {op['domain'],DOMAINS[op['domain']]}:continue
        aliases=' '.join(DOMAIN_ALIASES.get(op['domain'],()))
        hay=(op['id']+' '+op['label']+' '+op['description']+' '+DOMAINS.get(op['domain'],'')+' '+aliases).lower()
        if words and not all(w in hay for w in words):continue
        row={k:op[k] for k in ('id','label','domain','description','write','idempotent','manual_route')}
        if role:
            may=role_may_read(role,op)
            if may is not None:row['role_may_read']=may
            note=role_note(role,op)
            if note:row['role_note']=note
        items.append(row)
    # The model can narrow by domain; return discovery info rather than quietly
    # dropping operations beyond a result cap.
    return items

def _operation(operation_id):
    op=_operations().get(operation_id)
    if not op:
        # A wrong placeholder name is a model input error, not absence of the
        # business capability. Return an exact declared candidate, never execute
        # the guessed URL or silently change its arguments.
        shape=re.sub(r'\{[^{}]+\}','{}',str(operation_id))
        candidates=[key for key in _operations() if re.sub(r'\{[^{}]+\}','{}',key)==shape]
        if candidates:
            raise HTTPException(422,'操作名称填写不正确。请使用目录中的准确操作：'+'；'.join(candidates[:3])+'，并按字段说明填写 path_args；本次未执行')
        raise HTTPException(422,'没有找到此操作名称，请重新查找当前业务的操作目录；不要据此判断业务不支持。本次未执行')
    return op

def _native_action_schemas(op):
    """Reuse reviewed command validators; this does not grant action authority."""
    if op['path']=='/api/retail/orders/{key}/actions/{action}':
        from .retail_api import SCHEMAS
        return SCHEMAS
    if op['path']=='/api/claims/{case_id}/actions/{action}':
        from .claims_api import SCHEMAS
        return SCHEMAS
    return {}


def _native_purpose_schemas(op):
    if op['method']=='POST' and op['path']=='/api/membership/orders':
        from .membership_api import PURPOSE_SCHEMAS
        return PURPOSE_SCHEMAS
    return {}


def inspect_operation(operation_id):
    op=_operation(operation_id);route=op['route']
    result={k:copy.deepcopy(v) for k,v in op.items() if k!='route'}
    params=[]
    for field in route.dependant.path_params+route.dependant.query_params:
        item={'name':field.alias,'in':'path' if field in route.dependant.path_params else 'query','required':field.required,
              'type':'integer' if field.type_ is int else 'boolean' if field.type_ is bool else 'string'}
        if not field.required:item['default']=str(field.default) if field.default is not None else None
        params.append(item)
    result['parameters']=params
    if op['path']=='/api/flow/catalog':
        result['parameters'].append({'name':'assistant_kind','in':'query','type':'string','required':False})
        result['hint']='业务用assistant_kind=lead/order；客户主档用assistant_kind=customers（复数），不是customer。动作先读原单actions；客户联系电话另在客户主档编辑，未知事实先问员工。'
    elif op['path']=='/api/masters/catalog':
        result['parameters'].append({'name':'assistant_kind','in':'query','type':'string','required':False})
        result['hint']='传assistant_kind=vehicle_models/vehicle_brands/vehicle_series等，查询该类资料字段。金额输入以字段单位为准。'
    elif op['path'].endswith('/actions/{action}'):
        result['hint']='先读取同一原单和当前可用actions字段；不猜version、动作名、凭据或实际完成情况。'
    elif op['path']=='/api/claims' and op['write']:
        result['hint']='厂家payer_id来自GET /api/flow/master/{kind}（kind=references）中category=厂家且active的真实候选；保险公司用GET /api/masters/{kind}（kind=insurers）。外部核赔必须选择真实payer_id；内部核价必须填写payer_name。查不到候选先核对，不能用名字或猜测编号代替。'
    schemas=_native_action_schemas(op)
    if schemas:
        result['action_schemas']={key:schema.model_json_schema() for key,schema in schemas.items()}
        result['hint']=result.get('hint','')+' 按action_schemas中本次action的定义填写values；顶层原因与明细行不可混用。'
    purposes=_native_purpose_schemas(op)
    if purposes:
        result['purpose_schemas']={key:schema.model_json_schema() for key,schema in purposes.items()}
        result['hint']=result.get('hint','')+' 按body.purpose对应的purpose_schemas填写values。正向积分赠送用benefit_issue/grant及units，先由GET /api/group/benefits/rules核对真实kind=points规则；原规则版本、发行门店、适用门店和零售价须满足原接口。查不到适用积分规则先等待核对，不猜规则编号。points_adjust/adjust是扣减，不是增加；不能填写values.points代替units。'
    if not purposes and op['body_schema'] and 'values' in op['body_schema'].get('properties',{}):
        result['hint']=result.get('hint','')+' values字段定义由对应catalog或原单当前actions给出。'
    if op['path'].startswith('/api/flow/master/{kind}'):
        from .flow_api import MASTERS
        result['kind_names']={key:value['label'] for key,value in MASTERS.items() if key!='templates'}
        result['hint']=result.get('hint','')+' kind必须用准确的资料类别键，客户为customers；单数customer是参数错误，不代表员工无权。'
    return result


def _validate_catalog_kind(path,kind,subset=False):
    """Reject wrong catalogue names before native APIs conflate them with 403."""
    from .flow_api import MASTERS
    from .flow_specs import SPECS
    from .master_data import CATALOG
    if path.startswith('/api/flow/master/{kind}') or path=='/api/flow/catalog':
        choices=set(MASTERS)|(set(SPECS) if subset else set())
    elif path.startswith('/api/masters/{kind}') or path=='/api/masters/catalog':
        choices=set(CATALOG)
    else:return
    if kind in choices:return
    aliases={'customer':'customers','item':'items','member':'members','account':'accounts','reference':'references',
             'supplier':'suppliers','insurer':'insurers','vehicle_model':'vehicle_models'}
    correct=aliases.get(kind)
    detail=('请使用 '+correct if correct in choices else '请先查询对应目录中的准确类别键')
    raise HTTPException(422,'资料类别填写不正确，'+detail+'；这是类别参数错误，不代表没有权限。本次未执行')

def _parameters(op,path_args,query):
    if not isinstance(path_args,dict) or not isinstance(query,dict):raise HTTPException(422,'请核对查询条件格式')
    result_path={};result_query={}
    for supplied,fields,out in [(path_args,op['route'].dependant.path_params,result_path),(query,op['route'].dependant.query_params,result_query)]:
        allowed={f.alias for f in fields}
        if out is result_query and op['path'] in {'/api/flow/catalog','/api/masters/catalog'}:allowed.add('assistant_kind')
        if set(supplied)-allowed:raise HTTPException(422,'查询条件包含不支持的字段；此处可用字段：'+('、'.join(sorted(allowed)) or '无'))
        for f in fields:
            if f.alias not in supplied:
                if f.required:raise HTTPException(422,'请补充 '+f.alias)
                continue
            value,error=f.validate(supplied[f.alias],{},loc=('query',f.alias))
            if error:raise HTTPException(422,'请检查 '+f.alias+' 的格式')
            if isinstance(value,(dict,list)) or len(str(value))>500:raise HTTPException(422,'请缩小查询条件')
            if out is result_path and (not re.fullmatch(r'[A-Za-z0-9_.-]+',str(value)) or '..' in str(value)):
                raise HTTPException(422,'业务编号或类型不正确')
            out[f.alias]=value
        if 'assistant_kind' in supplied and 'assistant_kind' in allowed:out['assistant_kind']=str(supplied['assistant_kind'])[:60]
    if result_path.get('kind')=='templates':
        raise HTTPException(422,'合同模板请在单据模板页面核对后修改')
    # A newly added static handler is outside the reviewed capability boundary,
    # even when its final path segment also looks like an invalid catalogue kind.
    dispatch_path=op['path']
    for key,value in result_path.items():dispatch_path=dispatch_path.replace('{'+key+'}',quote(str(value),safe=''))
    if '{' not in dispatch_path:_declared_dispatch(op,dispatch_path)
    if 'kind' in result_path:_validate_catalog_kind(op['path'],result_path['kind'])
    if result_query.get('assistant_kind'):_validate_catalog_kind(op['path'],result_query['assistant_kind'],subset=True)
    return result_path,result_query

def validate_operation(operation_id,path_args=None,query=None,body=None):
    # Pure validation: request IDs are fixed once when a proposal is prepared.
    # Revalidating employee answers must never replace the native idempotency key.
    # 2026-09-25 业主裁定：不再用白名单/禁用词替接口做判断——动作名只要在已评审的接口上，
    # 就按员工本人身份准备；能不能办由原接口的岗位、门店、状态与版本决定，被拒时再走评审申请。
    op=_operation(operation_id);path_args,query=_parameters(op,path_args or {},query or {})
    value=copy.deepcopy(body)
    purposes=_native_purpose_schemas(op) if op['write'] else {}
    purpose_validated=False
    if op['method']=='GET':
        if value not in (None,{}):raise HTTPException(422,'查询操作不能提交修改内容')
        value=None
    elif op['route'].body_field:
        if not isinstance(value,dict):raise HTTPException(422,'请补充办理内容')
        # Validate a selected purpose before missing outer facts trigger a probe.
        if isinstance(value.get('purpose'),str) and value['purpose'] in purposes:
            from .membership_api import validate_purpose_values
            value['values']=validate_purpose_values(value['purpose'],value.get('values',{}))
            purpose_validated=True
        try:value=op['route'].body_field.type_.model_validate(value).model_dump(mode='json',exclude_unset=True)
        except ValidationError as exc:
            # The rejected envelope may contain a malformed kind/object. Only
            # use fixed labels until its structure has passed native validation.
            labels=FIELD_LABELS
            fields=['.'.join(str(x) for x in error['loc'])+'（'+labels.get(str(error['loc'][-1]),str(error['loc'][-1]))+'）' if error['loc'] else '办理内容' for error in exc.errors()]
            raise HTTPException(422,'请补充或核对：'+'、'.join(fields[:8])) from None
    elif value not in (None,{}):raise HTTPException(422,'该操作不接受额外字段')
    # These generic envelopes have dynamic fields. Validate them now so missing
    # facts trigger a question before confirmation; the native API validates again.
    schemas=_native_action_schemas(op) if op['write'] else {}
    if op['write'] and isinstance(value,dict) and (schemas or purposes or isinstance(value.get('values'),dict)):
        from .master_data import CATALOG
        from .flow_api import MASTERS
        from .flow_specs import SPECS,parse_fields
        kind=path_args.get('kind')
        try:
            if purposes:
                if not purpose_validated:
                    from .membership_api import validate_purpose_values
                    value['values']=validate_purpose_values(value.get('purpose'),value.get('values',{}))
            elif schemas:
                schema=schemas.get(path_args.get('action'))
                if schema is None:raise HTTPException(422,'本次办理动作不存在，请先核对原单当前可用动作')
                schema.model_validate(value.get('values',{}))
            elif op['path'].startswith('/api/masters/') and kind in CATALOG:
                CATALOG[kind][1].model_validate(value['values'])
            elif op['path'].startswith('/api/flow/master/') and kind in MASTERS:
                parse_fields(MASTERS[kind]['fields'],value['values'])
            elif op['path']=='/api/flow/cases' and value.get('kind') in SPECS:
                if (any(field['key']=='customer_name' for field in SPECS[value['kind']]['fields'])
                    and not value['values'].get('customer_id') and not value['values'].get('customer_name')):
                    raise HTTPException(422,'请填写新客户姓名，或选择已有客户；联系电话可稍后补充')
                parse_fields(SPECS[value['kind']]['fields'],value['values'])
        except ValidationError as exc:
            labels=_field_labels({'path_args':path_args,'body':value},operation_id)
            missing=[('values.'+'.'.join(str(x) for x in e['loc'])+'（'+labels.get(str(e['loc'][-1]),str(e['loc'][-1]))+'）'+('不在本次表单中' if e['type']=='extra_forbidden' else '') if e['loc'] else '办理内容') for e in exc.errors()]
            raise HTTPException(422,'请补充或核对：'+'、'.join(missing[:8])) from None
    if len(json.dumps(value,ensure_ascii=False).encode())>60000:raise HTTPException(422,'办理内容太多，请分次处理')
    operation={k:v for k,v in op.items() if k not in {'route','body_schema'}}
    if isinstance(value,dict):
        from .master_data import CATALOG
        from .flow_api import MASTERS
        from .flow_specs import SPECS
        kind=path_args.get('kind')
        if '/masters/' in op['path'] and kind in CATALOG:operation['label']=('新增' if op['method']=='POST' else '修改')+CATALOG[kind][2]
        elif '/flow/master/' in op['path'] and kind in MASTERS:operation['label']=('新增' if op['method']=='POST' else '修改')+MASTERS[kind]['label']
        elif op['path']=='/api/flow/cases' and value.get('kind') in SPECS:operation['label']='新建'+SPECS[value['kind']]['label']
    return {'operation':operation,'path_args':path_args,'query':query,'body':value,
            'prerequisites':prerequisite_notes(op,path_args,value)}


# Owner ruling 2026-09-25（第二条限制）：中间单据不能凭空建。流程里的后一步必须先补齐前序事实，
# 助手要把"这一步依赖什么"讲清楚并逐项问过员工，而不是替员工假设。
LINK_FIELD_WORDS = ('customer', 'vehicle', 'member', 'source', 'original', 'related', 'quote',
                    'lead', 'case', 'intake')


def prerequisite_notes(op,path_args,body):
    """列出这一步依赖的前序事实，供助手逐项向员工确认；不做业务判断。"""
    notes=[];path=op['path']
    if not op['write']:return notes
    if path=='/api/flow/cases' and isinstance(body,dict) and body.get('kind'):
        from .flow_specs import SPECS
        spec=SPECS.get(body['kind'])
        if spec:
            values=body.get('values') or {}
            links=[field for field in spec['fields'] if field['key'].endswith('_id')
                   and (field.get('required') or values.get(field['key']))]
            if links:
                labels='、'.join(field['label'] for field in links[:4])
                notes.append('核对本单关联的%s；已由原记录查到或员工提供的事实不重复询问，缺少真实关联时不能编编号。' % labels)
            else:
                notes.append('按员工已提供的事实新建%s；不凭空补做未发生的接待、沟通或审批。' % spec['label'])
        if body['kind']=='stock_count':
            # 2026-09-27 实测：员工要"按库位盘点"，助手准备了旧的按物资盘点卡，原页面看不到这张单
            # （仓储侧列表只列 warehouse 作业），助手却回报"已成功建立 1 项"。这条提示让员工在确认前
            # 就分清两种盘点，避免做出无法在库位视图办结的单。
            notes.append('注意：这是按物资的全店盘点（旧口径），不落到具体库位。若要按库位实盘，'
                         '请改用仓储作业的“库位盘点”，不要用这张卡代替。')
    elif path.endswith('/actions/{action}'):
        notes.append('按原单当前可办事项办理；前置事实未完成时等待对应岗位，不重复索要已查到的资料。')
    elif op['method']=='POST' and ('/orders' in path or path.endswith('/applications')):
        notes.append('新建这类单据前先确认它依赖的前序单据（原单、来源单、客户或车辆）已经存在并选到对应记录。')
    return notes


def _field_labels(payload,operation_id=''):
    from .master_data import CATALOG,COMMON
    from .flow_api import MASTERS
    from .flow_specs import SPECS
    labels=dict(FIELD_LABELS)
    body=payload.get('body') or {};path=payload.get('path_args') or {}
    kind=path.get('kind') or body.get('kind')
    fields=[]
    if '/masters/' in operation_id and kind in CATALOG:fields=COMMON+CATALOG[kind][4]
    elif '/flow/master/' in operation_id and kind in MASTERS:fields=MASTERS[kind]['fields']
    elif kind in SPECS:fields=SPECS[kind]['fields']
    elif '/actions/' in operation_id:
        for spec in SPECS.values():
            for action in spec['actions']:
                if action.key==path.get('action'):fields.extend(action.fields)
    labels.update({f['key']:f['label'] for f in fields})
    return labels


def display_fields(payload,operation_id='',*,field_labels=None):
    """Show the exact immutable submission, including every line and unit."""
    from .master_data import CATALOG
    from .flow_api import MASTERS
    from .flow_specs import SPECS
    labels=dict(field_labels) if field_labels is not None else _field_labels(payload,operation_id);rows=[]
    enums={'petrol':'汽油','diesel':'柴油','electric':'纯电','hybrid':'混动','plugin_hybrid':'插混',
           'vehicles':'整车','materials':'物资','mixed':'混合','bank':'银行','cash':'现金','job':'次','hour':'小时'}
    term_enums={
        'refund_policy':{'none':'不可退款','unused_before_expiry':'仅有效期内未使用部分可退',
                         'unused_anytime':'未使用部分可退（含到期后）',
                         'whole_unused_before_expiry':'仅有效期内未使用的完整份额可退',
                         'whole_unused_anytime':'未使用的完整份额可退（含到期后）'},
        'discount_bearer':{'group':'集团承担优惠','service_store':'履约门店承担优惠'},
    }
    def walk(value,prefix=''):
        if not isinstance(value,dict):return
        for key,item in value.items():
            if key in {'request_id','version'} or key.lower() in SECRET_KEYS:continue
            label=labels.get(key,key)
            if isinstance(item,dict):walk(item,prefix if key=='values' else prefix+label+' · ')
            elif isinstance(item,list):
                if not item:rows.append({'label':prefix+label,'value':'无'})
                for i,entry in enumerate(item,1):
                    if isinstance(entry,dict):walk(entry,prefix+label+f' · 第{i}项 · ')
                    else:rows.append({'label':prefix+label+f' · 第{i}项','value':str(entry)})
            else:
                if key.endswith('_cents') and type(item) is int:
                    label=label.replace('（分）','（元）');amount=abs(item)
                    shown=('-' if item<0 else '')+f'{amount//100}.{amount%100:02d}'
                elif key.endswith('_milli') and type(item) is int:
                    label=label.replace('（千分之一）','');amount=abs(item)
                    shown=('-' if item<0 else '')+f'{amount//1000}.{amount%1000:03d}'.rstrip('0').rstrip('.')
                elif isinstance(item,bool):shown='是' if item else '否'
                elif key in term_enums:shown=term_enums[key].get(str(item),str(item))
                elif key in {'fuel_type','warehouse_type','account_type','billing_unit','unit'}:shown=enums.get(str(item),str(item))
                elif key=='kind' and '/repair-packages/' in operation_id and item in {'work','part'}:shown={'work':'实际作业','part':'实际配件'}[item]
                elif key=='kind' and item in SPECS:shown=SPECS[item]['label']
                elif key=='kind' and item in CATALOG:shown=CATALOG[item][2]
                elif key=='kind' and item in MASTERS:shown=MASTERS[item]['label']
                else:shown=str(item) if item is not None else '未填写'
                rows.append({'label':prefix+label,'value':shown})
    for part in ('path_args','query','body'):walk(payload.get(part) or {})
    return rows


def manual_route(operation_id,path_args=None,data=None):
    op=_operation(operation_id);path_args=path_args or {}
    if '/flow/master/' in op['path']:return 'master/'+str(path_args.get('kind','customers'))
    if op['domain']=='masters' and path_args.get('kind'):return 'masters/'+str(path_args['kind'])
    if '/flow/cases' in op['path']:
        ident=path_args.get('case_id') or (data.get('id') if isinstance(data,dict) else None)
        if type(ident) is int:return 'case/'+str(ident)
    return op['manual_route']

def sanitize(value,depth=0):
    if depth>16:return '[内容过深，请查看原单]'
    if isinstance(value,dict):return {str(k):sanitize(v,depth+1) for k,v in value.items() if str(k).lower() not in SECRET_KEYS}
    if isinstance(value,list):return [sanitize(v,depth+1) for v in value[:100]]+([{'more':'其余记录请缩小查询条件'}] if len(value)>100 else [])
    if isinstance(value,str):return re.sub(r'(?:sk|tp|ttp)-[A-Za-z0-9_-]{12,}','[密钥已隐藏]',value[:4000])
    return value

async def _internal_get(request, user, op, path, query, body):
    """Private ASGI GET through the full app and its ordinary authorization."""
    from .assistant_runtime_principal import (
        _SCOPE_KEY, _InternalCall, _check_call, _caller_matches,
        runtime_request_context, revalidate_principal, internal_base_url,
    )
    from fastapi import Request
    context = runtime_request_context(request)
    if context is None or op['method'] != 'GET' or op['write'] or body not in (None, {}):
        raise HTTPException(403, '内部助手只能调用已登记的原业务查询')
    principal = context.principal
    _caller_matches(user, principal, principal.session_id)
    revalidate_principal(context.db, principal)
    if role_may_read(principal.role, op) is False:
        raise HTTPException(403, '当前岗位不能使用此原业务查询')
    call = _InternalCall(context, op['id'], path, str(httpx.QueryParams(query)).encode('ascii'))
    from .main import app

    async def bound_app(scope, receive, send):
        scope = dict(scope)
        scope[_SCOPE_KEY] = call
        _check_call(Request(scope), call)
        await app(scope, receive, send)

    factory = context.client_factory or httpx.AsyncClient
    async with factory(transport=httpx.ASGITransport(app=bound_app, raise_app_exceptions=False),
                       base_url=internal_base_url(), timeout=30, follow_redirects=False,
                       trust_env=False) as client:
        response = await client.get(path, params=query,
            headers={'X-App-Request': '1', 'X-Store-ID': str(principal.store_id)})
    # The route's transaction has ended. Observe committed revocations/lease
    # changes now, before even exposing an error body or a query result.
    revalidate_principal(context.db, principal)
    return response


async def invoke(request,user,operation_id,path_args=None,query=None,body=None):
    op=_operation(operation_id)
    if getattr(user,'_aggregate_scope',False):raise HTTPException(409,'请先选择办理门店')
    path_args,query=_parameters(op,path_args or {},query or {})
    # Never derive credentials/store from model arguments. Native get_user checks
    # revocation and role/store changes again inside the destination API.
    path=op['path']
    for k,v in path_args.items():path=path.replace('{'+k+'}',quote(str(v),safe=''))
    if '{' in path:raise HTTPException(422,'请补充业务编号')
    _declared_dispatch(op,path)
    subset=query.pop('assistant_kind',None)
    if '_huakang_runtime' in request.scope:
        response=await _internal_get(request,user,op,path,query,body)
    else:
        headers={'X-App-Request':'1','X-Store-ID':str(getattr(user,'_active_store_id','')),
                 'Cookie':request.headers.get('cookie',''),'X-CSRF-Token':request.headers.get('x-csrf-token','')}
        from .main import app
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,raise_app_exceptions=False),base_url=str(request.base_url),timeout=30) as client:
            response=await client.request(op['method'],path,params=query,headers=headers,json=body if op['write'] else None)
    if 'application/json' not in response.headers.get('content-type',''):
        return {'status':response.status_code if response.status_code>=400 else 422,'data':{'detail':'文件请在原业务页面查看或下载'}}
    try:data=response.json()
    except ValueError:return {'status':502,'data':{'detail':'业务服务返回异常，请到原单核对'}}
    refusal=refusal_metadata(response.status_code,data)
    if subset and op['path'] in {'/api/flow/catalog','/api/masters/catalog'} and response.status_code<400:
        selections={name:{subset:data[name][subset]} for name in ('kinds','master_types')
                    if isinstance(data.get(name),dict) and subset in data[name]}
        if not selections:
            return {'status':403,'data':{'detail':'当前岗位不能查看此类资料，请在对应门店页面核对'},
                    'error_category':'refused','route':manual_route(operation_id,path_args)}
        data={name:selections.get(name,{}) for name in ('kinds','master_types')}
    data=sanitize(data)
    encoded=json.dumps(data,ensure_ascii=False)
    if len(encoded)>55000:
        # Never pretend a clipped JSON fragment is a complete business result.
        data={'detail':'结果较多，请指定资料类型、客户或单号查询','truncated':True,'top_level_fields':list(data) if isinstance(data,dict) else [],'total':data.get('total') if isinstance(data,dict) else None}
    result={'status':response.status_code,'data':data,'route':manual_route(operation_id,path_args,data)}
    if refusal is not None:result['refusal']=refusal
    if response.status_code>=400:
        category=refusal['category'] if refusal else None
        if response.status_code in {403,422} and category:
            result['error_category']={'authority':'permission','amount':'amount','rule':'business_rule'}[category]
        else:
            result['error_category']=('input' if response.status_code==422 else 'permission' if response.status_code==401
                else 'refused' if response.status_code==403 else 'not_found' if response.status_code==404
                else 'business_rule' if response.status_code==409 else 'system')
        hint=permission_hint(response.status_code,{'refusal':refusal})
        # The legacy confirmation consumer appends fixed authority wording for
        # every 403 hint. Preserve an amount refusal without mislabelling it.
        # Its native detail and audited category remain available to the caller.
        if hint and not (op['write'] and response.status_code==403 and category=='amount'):
            result['hint']=hint
    return result
