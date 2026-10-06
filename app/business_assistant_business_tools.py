"""Business-facing tools. Native forms and employee-scoped HTTP remain authoritative.

Form references identify a native form, not a permission grant. Values are employee
input units; *_cents / *_milli conversion is performed here, not guessed by the LLM.
The legacy reviewed tools remain available for specialised native workflows.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from .assistant_runtime_schemas import BusinessObjectRef, Condition

PROFILE = 'business_v1'
MAX_ROWS = 200  # Same resource bound as existing proposals/tool batches.
LOOKUPS = {'employee','vehicle','account','file','signed_file','handover_file',
           'item','member','payment','stock_issue','billable_case','customer'}
MODULE_NAMES = {'sales':'整车销售','vehicles':'整车仓库','repairs':'维修管理',
                'materials':'物资管理','finance':'财务管理','customers':'客户管理',
                'members':'会员服务','analytics':'统计分析','masters':'基础数据','system':'系统管理'}

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class FindObjects(Strict):
    kind: Literal['case','customer','vehicle','employee','member','material','master']
    query: str = Field(default='', max_length=100)
    case_id: int | None = Field(default=None, gt=0)
    action: str = Field(default='', max_length=60,
        description='为原单选择接手员工时，传get_case给出的原动作key；一般员工目录不代表该动作的可选人。')
    business_kind: str = Field(default='', max_length=60)
    master_kind: str = Field(default='', max_length=60)
    page: int = Field(default=1, ge=1, le=10000)
    scope: Literal['mine','visible'] = 'visible'

class Discover(Strict):
    query: str = Field(default='', max_length=100)
    category: str = Field(default='', max_length=60)
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=30, ge=1, le=100)

class Inspect(Strict):
    form_ref: str = Field(min_length=1, max_length=160)

class Prepare(Inspect):
    values: dict = Field(default_factory=dict)
    selections: dict[str,str] = Field(default_factory=dict,
        description='字段key到员工已明确给出的名称。程序查真实候选；同名不自动选择。')
    summary: str = Field(min_length=1, max_length=600)
    step: str = Field(default='', max_length=120)
    step_order: int = Field(default=1, ge=1, le=99)

class BatchRow(Strict):
    values: dict = Field(default_factory=dict)
    selections: dict[str,str] = Field(default_factory=dict)
    summary: str = Field(min_length=1,max_length=600)

class Batch(Inspect):
    rows: list[BatchRow] = Field(min_length=1,max_length=MAX_ROWS)
    step: str = Field(default='',max_length=120)

class WorkStep(Strict):
    key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,50}$')
    title: str = Field(min_length=1,max_length=160)
    depends_on: list[str] = Field(default_factory=list,max_length=MAX_ROWS)
    proposal_id: str | None = Field(default=None,max_length=36)
    case_id: int | None = Field(default=None,gt=0)
    workflow_id: str | None = Field(default=None,max_length=100)
    wait_for: str = Field(default='',max_length=500,
        description='计划上待满足的事实，不是已完成声明；服务端状态优先。')
    object_ref: BusinessObjectRef | None = None
    form_ref: str | None = Field(default=None,min_length=1,max_length=160)
    conditions: list[Condition] = Field(default_factory=list,max_length=MAX_ROWS)
    completion_conditions: list[Condition] = Field(default_factory=list,max_length=MAX_ROWS)
    required: bool = True

    @model_validator(mode='after')
    def matching_case(self):
        if (self.case_id is not None and self.object_ref is not None
                and (self.object_ref.type != 'case' or self.object_ref.id != self.case_id)):
            raise ValueError('case_id and object_ref must name the same original Case')
        return self

class WorkPlan(Strict):
    plan_id: str|None = Field(default=None,max_length=36)
    goal: str = Field(min_length=1,max_length=300)
    steps: list[WorkStep] = Field(min_length=1,max_length=MAX_ROWS)
    expected_version: int | None = Field(default=None,ge=1)
    schema_version: Literal[1,2] = 1

    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_schema_version(cls,value):
        if type(value) is not int or value not in (1,2):
            raise ValueError('Expected plan schema version 1 or 2')
        return value

    @model_validator(mode='after')
    def explicit_runtime_schema(self):
        if self.schema_version == 1 and any(
                step.object_ref is not None or step.form_ref is not None or step.conditions
                or step.completion_conditions or step.required is not True for step in self.steps):
            raise ValueError('Structured Runtime fields require schema_version=2')
        return self

class WorkStatus(Strict):
    plan_id: str | None = Field(default=None,max_length=36)
    case_page: int = Field(default=1,ge=1,le=10000)

SPECS = {
    'find_business_objects': (FindObjects, '按姓名、车牌、单号或编码找真实业务对象。返回候选与分页，不能把同名第一项当选中。员工查询走业务选择器，不是管理员账号。'),
    'discover_business_forms': (Discover, '按员工目标找原生表单及原需求办事说明。表单引用由程序返回，不能编造；原单后续用get_case。未封装的专用业务仍可用原list_operations/inspect_operation。'),
    'inspect_business_form': (Inspect, '取得一张原生业务表单的中文字段、必要事实、单位和候选。form_ref来自发现结果或get_case；不创建卡片。'),
    'prepare_business_form': (Prepare, '准备已选表单：程序查最新版本、按姓名解析真实候选、自动生成集中缺项卡，金额按元输入。只准备，不执行。对象未选中/同名无法消歧时返回选择问题而不制卡。'),
    'prepare_business_batch': (Batch, '同类独立新建表单紧凑批量准备，逐项返回成功/复用/缺项/失败。不用于同一原单的互相依赖动作；不直接执行业务，不吞行。'),
    'save_work_plan': (WorkPlan, '为员工明确委托的多步骤目标保存办事计划。关联本会话真实卡片或可见原单；尚无原单的步骤必须关联已发布workflow_id。只保存计划，不代表完成或自动执行业务。'),
    'get_work_status': (WorkStatus, '不用再次调用模型推测下一步：读取本会话真实卡片、最新原单待办、接手人及办事计划。完成只由原卡执行结果认定；计划依赖不能替代后端状态。'),
}
PREPARE_NAMES = {'prepare_business_form','prepare_business_batch'}


def tool_definitions():
    return [{'type':'function','function':{'name':name,'description':description,
            'parameters':model.model_json_schema()}} for name,(model,description) in SPECS.items()]


def validate(name, args):
    if name not in SPECS: raise HTTPException(422,'未知业务工具')
    try:
        parsed=SPECS[name][0].model_validate(args)
        if name=='save_work_plan':
            if parsed.schema_version==2:
                # due_at has a validated datetime internally; tool arguments and
                # persisted plan JSON retain its canonical UTC string form.
                result=parsed.model_dump(mode='json')
                from .business_assistant_service import MODEL_ARGUMENT_CHARS
                # Defaults can expand a compact model call. Reject it during
                # whole-list preflight, before any earlier call is dispatched.
                if len(json.dumps(result,ensure_ascii=False,separators=(',',':'))) > MODEL_ARGUMENT_CHARS:
                    raise HTTPException(422,'计划内容超过本次工具参数容量，请缩小本次计划范围')
                return result
            result=parsed.model_dump()
            result.pop('schema_version')
            for step in result['steps']:
                for key in ('object_ref','form_ref','conditions','completion_conditions','required'):
                    step.pop(key)
            return result
        return parsed.model_dump()
    except ValidationError as exc:
        fields=', '.join('.'.join(map(str,e['loc'])) for e in exc.errors()[:6])
        raise HTTPException(422,'业务工具字段不正确，请核对：'+fields) from None


async def native(db,request,user,sid,config,operation,path=None,query=None):
    from .business_assistant_service import run_tools
    return await run_tools(db,request,user,sid,'read_data',
        {'operation_id':operation,'path_args':path or {},'query':query or {}},config)


def checked(result):
    if not isinstance(result,dict): raise HTTPException(502,'未取得业务查询结果')
    if result.get('status',500)>=400:
        data=result.get('data') or {}
        raise HTTPException(result.get('status',502),data.get('detail','本次查询失败，不能当作没有记录') if isinstance(data,dict) else '业务查询失败')
    data=result.get('data')
    if not isinstance(data,dict) or data.get('truncated'):
        raise HTTPException(409,'结果不完整，请缩小范围或到原页面核对')
    return data


async def find_objects(db,request,user,sid,c,args):
    kind=args['kind'];query=args['query']
    action=args.get('action','')
    if action and (kind!='employee' or not args['case_id']):
        raise HTTPException(422,'员工动作候选须同时指定原单与原动作')
    if kind=='employee' and args['case_id'] and not action:
        raise HTTPException(422,'请使用原单employee字段candidate_lookup中的action查询本动作接手员工')
    if kind=='case':
        from .business_assistant_case_tools import handle_case_tool
        return await handle_case_tool(db,request,user,sid,'find_cases',
            {'query':query,'kind':args['business_kind'],'scope':args['scope'],'page':args['page']},c)
    if kind=='master':
        if not re.fullmatch('[a-z_]{1,60}',args['master_kind']): raise HTTPException(422,'先选择基础资料类型')
        result=await native(db,request,user,sid,c,'GET /api/masters/{kind}',
                            {'kind':args['master_kind']},{'q':query,'page':args['page']})
    else:
        if args['page']!=1: raise HTTPException(422,'该业务选择器按关键词缩小范围，不支持页码；请补充姓名或编码')
        lookup='item' if kind=='material' else kind
        result=await native(db,request,user,sid,c,'GET /api/flow/lookup/{kind}',{'kind':lookup},
                            {'q':query,**({'case_id':args['case_id']} if args['case_id'] else {}),
                             **({'action':action} if action else {})})
    data=checked(result)
    items=data.get('items',[])
    more=bool(data.get('has_more') or data.get('truncated') or
              data.get('page',1)*data.get('page_size',30)<data.get('total',0))
    result['data']={**data,'selection_required':len(items)!=1 or more,
        'has_more':more,'notice':'仅在身份唯一且符合员工原意时选择；空页/部分候选不代表全库没有。'}
    return result


async def discover(db,request,user,sid,c,args):
    from . import business_assistant_service as s
    flow=checked(await native(db,request,user,sid,c,'GET /api/flow/catalog'))
    masters=checked(await native(db,request,user,sid,c,'GET /api/masters/catalog'))
    entries=[]
    for prefix,rows in [('flow',flow.get('kinds',{})),('crm',flow.get('master_types',{})),('master',masters.get('kinds',{}))]:
        for kind,info in rows.items():
            can=info.get('can_create') if prefix=='flow' else info.get('can_write')
            if not can: continue
            entries.append({'form_ref':prefix+':'+kind,'label':info['label'],
                'module':info.get('module','基础数据' if prefix=='master' else '客户与基础资料'),
                'creates_new_record':True})
    q=args['query'].strip()
    help_data=await s.run_tools(db,request,user,sid,'find_workflows',{'query':q,'category':args['category']},c) if q else {'items':[]}
    if q:
        guide_refs=set()
        for item in help_data.get('items',[]):
            route=item.get('entry',{}).get('route','')
            for route_prefix,form_prefix in [('cases/','flow:'),('master/','crm:'),('masters/','master:')]:
                if re.fullmatch(re.escape(route_prefix)+r'[a-z_]+',route):
                    guide_refs.add(form_prefix+route[len(route_prefix):])
        exact=[x for x in entries if x['form_ref'] in guide_refs or q in x['label'] or x['label'] in q or q==x['form_ref'].split(':')[-1]]
        if not exact:
            tokens=[x for x in re.split(r'[\s，,、/]+',q) if x]
            exact=[x for x in entries if any(t in x['label'] for t in tokens)]
        entries=exact
    entries.sort(key=lambda x:(x['module'],x['label'],x['form_ref']))
    offset,limit=args['offset'],args['limit'];page=entries[offset:offset+limit]
    result={'status':200,'forms':page,'total':len(entries),'has_more':offset+len(page)<len(entries),
        'next_offset':offset+len(page) if offset+len(page)<len(entries) else None,
        'workflows':help_data,'coverage':'表单封装不是整个系统的能力上限；专用订单、财务明细及报表仍可用原已评审工具。',
        'notice':'这些是新建表单。查进度/退回/后续办理应先找已有原单，不为问做法创建卡片。'}
    if not entries:
        # An empty wrapper match is not an authorization or native capability verdict.
        result['native_operation_discovery']={
            'status':'not_checked','next_tools':['list_operations','inspect_operation'],
            'notice':'本次只查了新建表单封装，尚未核对原业务操作目录。要判断该业务能否由助手准备，先用list_operations查原操作，再用inspect_operation核对；未核实前不能说助手不支持、不能代填或只能员工去页面提交。此说明不授权新业务，也不要求为了解做法创建卡片。'}
    return result


async def inspect_form(db,request,user,sid,c,ref):
    from .business_assistant_case_tools import _case
    match=re.fullmatch(r'case:([1-9][0-9]*):([a-zA-Z0-9_]+)',ref)
    if match:
        case_id=int(match[1]);result,_=await _case(db,request,user,sid,c,case_id,with_contact=False)
        data=checked(result);action=next((x for x in data.get('actions',[]) if x['key']==match[2]),None)
        if not action: raise HTTPException(403,'原单当前没有这项可办操作，请重新查看原单')
        if not action.get('enabled'): raise HTTPException(409,action.get('reason') or '尚未满足业务条件')
        return {'form_ref':ref,'label':action['label'],'fields':deepcopy(action.get('fields',[])),
            'kind':'action','case_id':case_id,'action':action['key'],'case_version':data['version'],
            'case_text':' · '.join(str(data[k]) for k in ('number','title') if data.get(k)),
            'operation_id':'POST /api/flow/cases/{case_id}/actions/{action}',
            'path_args':{'case_id':case_id,'action':action['key']},'input_units':'按字段注明的元/数量填写，不换算成分。'}
    match=re.fullmatch(r'(flow|master|crm):([a-z_]{1,60})',ref)
    if not match: raise HTTPException(422,'表单引用无效，请从业务目录选择，不要填写接口或网址')
    prefix,kind=match.groups()
    catalog=checked(await native(db,request,user,sid,c,'GET /api/masters/catalog' if prefix=='master' else 'GET /api/flow/catalog',
        query={'assistant_kind':kind}))
    info=catalog.get('master_types' if prefix=='crm' else 'kinds',{}).get(kind)
    if not info: raise HTTPException(403,'当前岗位没有这类表单，请选择本岗位可办事项')
    if not info.get('can_create' if prefix=='flow' else 'can_write'): raise HTTPException(403,'当前岗位不能新增这类业务')
    fields=deepcopy(info.get('fields',[]))
    for field in fields:
        if field['key'].endswith('_cents'):
            field['input_unit']='元';field['storage_unit']='分'
            field['label']=field['label'].replace('（分）','（元）')
        elif field['key'].endswith('_milli'):
            field['input_unit']='数量';field['storage_unit']='整数千分之一'
    operation={'flow':'POST /api/flow/cases','master':'POST /api/masters/{kind}',
               'crm':'POST /api/flow/master/{kind}'}[prefix]
    return {'form_ref':ref,'label':info['label'],'fields':fields,'kind':prefix,'business_kind':kind,
        'operation_id':operation,'path_args':{} if prefix=='flow' else {'kind':kind},
        'input_units':'*_cents按元、*_milli按实际数量输入，程序精确换算；不要预先乘100/1000。'}


def is_relation(field):
    return field.get('type') in LOOKUPS or (field.get('type')=='ref' and bool(field.get('ref_kind')))


def choices_from_native(data, *, master=False):
    options=[];more=bool(data.get('has_more') or data.get('truncated'))
    for row in data.get('items',[]):
        if not isinstance(row,dict) or type(row.get('id')) is not int or not isinstance(row.get('label'),str):
            more=True;continue
        label=row['label']
        if master and ' · ' in label:
            code,name=label.split(' · ',1);label=name+' · '+code
        options.append({'label':label,'value':row['id']})
    return options,more


async def candidates(db,request,user,sid,c,form,field,query='',selected_id=None):
    kind=field.get('type');case_id=form.get('case_id')
    if kind in LOOKUPS:
        # The same fresh get_case response already fetched eligible employees.
        if not query and isinstance(field.get('candidates'),list) and not field.get('candidates_has_more'):
            return deepcopy(field['candidates']),False
        result=await native(db,request,user,sid,c,'GET /api/flow/lookup/{kind}',{'kind':kind},
                            {'q':query,**({'case_id':case_id} if case_id else {}),
                             **({'action':field['lookup_action']} if kind=='employee' and field.get('lookup_action') else {})})
        return choices_from_native(checked(result))
    if kind=='ref' and field.get('ref_kind'):
        ref=field['ref_kind']
        data=checked(await native(db,request,user,sid,c,'GET /api/masters/lookup/{kind}',{'kind':ref},
            {'q':query,**({'selected_id':selected_id} if selected_id else {})}))
        return choices_from_native(data,master=ref!='employees')
    if kind=='select':
        return [{'label':str(x.get('label',x.get('value',''))),'value':x.get('value')} if isinstance(x,dict)
                else {'label':str(x),'value':x} for x in field.get('options',[])],False
    return [],False


def exact_selection(name, options, has_more):
    """A substring is only a search term, never proof of unique identity."""
    wanted=name.strip()
    matches=[o for o in options if wanted==o['label'].strip() or wanted==o['label'].split(' · ')[0].strip()]
    return matches[0]['value'] if len(matches)==1 and not has_more else None


def scale_value(value,scale,label):
    try:
        if isinstance(value,bool) or not isinstance(value,(str,int,float)): raise ValueError()
        n=Decimal(str(value))
        if not n.is_finite() or abs(n)>Decimal('1e15') or n*scale!=(n*scale).to_integral_value():raise ValueError()
        return int(n*scale)
    except (ValueError,InvalidOperation): raise HTTPException(422,label+'的精度不正确，不能自动四舍五入') from None


async def resolve_preparation(db,request,user,sid,c,args,form=None):
    """Resolve native facts and fields without creating or changing a proposal."""
    from . import business_assistant_service as s
    s.require_preparation_read_phase(db)
    from .business_assistant_case_tools import resolve_preparation as resolve_case_preparation
    form=form or await inspect_form(db,request,user,sid,c,args['form_ref'])
    values=deepcopy(args['values']);selected=args['selections'];fields={f['key']:f for f in form['fields']}
    if set(values)-set(fields) or set(selected)-set(fields): raise HTTPException(422,'只接受当前表单的字段，不接受版本、门店、接口或任意参数')
    if set(values)&set(selected): raise HTTPException(422,'同一字段不能既给编号又给名称，请保留一种明确选择')
    questions=[];unresolved=[];references={}
    for key,name in selected.items():
        options,more=await candidates(db,request,user,sid,c,form,fields[key],name)
        matched=exact_selection(name,options,more)
        if matched is None:
            unresolved.append({'field':key,'label':fields[key]['label'],'query':name,'candidates':options,'has_more':more})
        else:
            values[key]=matched;references[key]=next(o for o in options if o['value']==matched)
    for key,value in list(values.items()):
        if key in selected or value is None or value=='': continue
        f=fields[key]
        relation=is_relation(f)
        if not relation: continue
        if type(value) is not int or value<1:
            raise HTTPException(422,f['label']+'须选真实对象，不能填字符串或猜编号')
        options,more=await candidates(db,request,user,sid,c,form,f,selected_id=value)
        if not any(o['value']==value for o in options):
            if more:
                unresolved.append({'field':key,'label':f['label'],'candidates':options,'has_more':True,
                    'notice':'候选较多，请改用selections按准确名称查找，不能假定未列出的编号有权限。'})
            else: raise HTTPException(422,f['label']+'不是当前业务可选对象，请重新查询')
        else: references[key]=next(o for o in options if o['value']==value)
    if unresolved:
        return {'status':200,'outcome':'needs_selection','selections':unresolved,'prepared':False,
                'notice':'未创建卡片；请集中选择真实对象，不能给每个同名候选各建一张卡。'}
    if form['kind'] in {'flow','crm','action'}:
        # Native customer creation has an either/or condition not captured by required flags.
        if 'customer_name' in fields and not values.get('customer_name') and not values.get('customer_id'):
            fields['customer_name']={**fields['customer_name'],'required':True}
    for key,f in fields.items():
        if f.get('required') and 'default' not in f and (key not in values or values[key] is None or values[key]==''):
            options,more=await candidates(db,request,user,sid,c,form,f)
            if more:
                unresolved.append({'field':key,'label':f['label'],'candidates':options,'has_more':True})
                continue
            relation=is_relation(f)
            if relation and not options:
                unresolved.append({'field':key,'label':f['label'],'candidates':[],'has_more':False,
                                   'notice':'没有可选来源，需先核对原单；不让员工猜编号。'})
                continue
            questions.append({'key':'values.'+key,'label':f['label'],'options':options,'required':True})
    if unresolved:
        return {'status':200,'outcome':'needs_source','selections':unresolved,'prepared':False,
                'notice':'当前必要来源未确定，请先选择或核对；没有创建虚构来源卡片。'}
    if form['kind']=='master':
        for key,value in list(values.items()):
            if key.endswith('_cents'): values[key]=scale_value(value,100,fields[key]['label'])
            elif key.endswith('_milli'): values[key]=scale_value(value,1000,fields[key]['label'])
    if form['kind']=='action':
        resolved=await resolve_case_preparation(db,request,user,sid,'prepare_case_action',
            {'case_id':form['case_id'],'action':form['action'],'values':values,
             'questions':questions,'summary':args['summary']},c)
    else:
        body={'values':values}
        if form['kind']=='flow': body['kind']=form['business_kind']
        # Preserve the native dynamic validator for complete and incomplete forms.
        if form['kind'] in {'flow','crm'}:
            from .flow_specs import parse_fields
            from . import business_assistant_gateway as g
            probe=s.answer_probe(g,form['operation_id'],body,questions,form['path_args'],list(fields.values())) if questions else body
            parse_fields(list(fields.values()),probe['values'])
        resolved=s.resolve_preparation(db,user,sid,{'operation_id':form['operation_id'],'path_args':form['path_args'],
            'body':body,'summary':args['summary'],'step':args.get('step') or form['label'],
            'step_order':args.get('step_order',1),'questions':questions},
            question_fields=list(fields.values()) if form['kind'] in {'flow','crm'} else None)
    if not isinstance(resolved,s.ResolvedPreparation):
        return resolved
    from .business_assistant_presentation import snapshot
    return replace(resolved,label=form['label'],presentation=snapshot(form,references),
                   references=deepcopy(references),form_ref=form['form_ref'])


async def prepare(db,request,user,sid,c,args,form=None,*,resolve_only=False):
    """Keep the original prepare-and-commit API; Runtime can request facts only."""
    from . import business_assistant_service as s
    resolved=await resolve_preparation(db,request,user,sid,c,args,form)
    if not isinstance(resolved,s.ResolvedPreparation) or resolve_only:
        return resolved
    result=s.commit_preparation(db,user,sid,resolved)
    return {**result,'business_form_ref':resolved.form_ref,'requires_employee_confirmation':True}


async def handle(db,request,user,sid,name,args,c,*,resolve_only=False):
    from . import business_assistant_service as s
    if name in PREPARE_NAMES:s.require_preparation_read_phase(db)
    s.owned_session(db,user,sid)
    args=validate(name,args)
    if name=='find_business_objects': return await find_objects(db,request,user,sid,c,args)
    if name=='discover_business_forms': return await discover(db,request,user,sid,c,args)
    if name=='inspect_business_form':
        data=await inspect_form(db,request,user,sid,c,args['form_ref'])
        # No internal HTTP or source version is required from the model on this path.
        return {'status':200,'data':{k:v for k,v in data.items() if k not in {'operation_id','path_args','case_version'}}}
    if name=='prepare_business_form': return await prepare(db,request,user,sid,c,args,resolve_only=resolve_only)
    if name=='prepare_business_batch':
        if args['form_ref'].startswith('case:'): raise HTTPException(409,'同一原单的动作不能当成独立批量；请按真实依赖逐项准备')
        s.require_preparation_read_phase(db)
        form=await inspect_form(db,request,user,sid,c,args['form_ref'])
        if form['kind']=='action': raise HTTPException(409,'同一原单的动作不能当成独立批量；请按真实依赖逐项准备')
        if resolve_only:
            items=[]
            for index,row in enumerate(args['rows'],1):
                try:
                    result=await prepare(db,request,user,sid,c,
                        {**row,'form_ref':args['form_ref'],'step':args['step'],'step_order':1},
                        form,resolve_only=True)
                    items.append(result if isinstance(result,s.ResolvedPreparation) else {**result,'row':index})
                except HTTPException as exc:
                    items.append({'row':index,'status':exc.status_code,'error':s.safe_text(exc.detail,500)})
            return s.ResolvedBatchPreparation(kind='business',items=items,input_count=len(args['rows']))
        results=[];seen=set()
        for index,row in enumerate(args['rows'],1):
            try:
                result=await prepare(db,request,user,sid,c,{**row,'form_ref':args['form_ref'],'step':args['step'],'step_order':1},form)
                key=result.get('id');reused=key in seen if key else False
                if key:seen.add(key)
                results.append({'row':index,'id':key,'status':result.get('status'),
                    'outcome':'reused' if reused else 'prepared' if key else result.get('outcome','not_prepared'),
                    'missing':[q['label'] for q in result.get('questions',[])],
                    **({'selection':result.get('selections')} if not key else {})})
            except HTTPException as exc:
                results.append({'row':index,'status':exc.status_code,'error':s.safe_text(exc.detail,500)})
        return {'status':200,'input_count':len(args['rows']),'unique_prepared':len(seen),'items':results,
                'notice':'逐项真实结果；失败/未选来源的行没有草稿。确认仍由员工在原页面执行。'}
    from . import business_assistant_workboard as wb
    if name=='save_work_plan': return await wb.save_plan(db,request,user,sid,c,args)
    if name=='get_work_status': return await wb.work_status(db,request,user,sid,c,args)
    raise HTTPException(422,'未知业务工具')
