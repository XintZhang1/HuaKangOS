"""Scoped case discovery and native form preparation, never direct business writes.

The assistant receives the same actions as the case page. Customer contact edits
are a separate related form, not invented state transitions. All reads re-enter
the ordinary authenticated API; confirmation remains in the proposal service.
"""
import copy
from fastapi import HTTPException
from .flow_specs import parse_fields, flow_spec
from .customer_choice import normalized_phone


async def _read(db,request,user,thread_id,config,operation,path=None,query=None):
    from .business_assistant_service import run_tools
    return await run_tools(db,request,user,thread_id,'read_data',{
        'operation_id':operation,'path_args':path or {},'query':query or {}},config)


def _case_id(args):
    value=args.get('case_id')
    if type(value) is not int or value<1:raise HTTPException(422,'请选择要办理的业务')
    return value


def project_case_read(operation_id,result):
    """Keep recorded actors and the case's own workflow version explicit.

    Both assistant read lanes use this projection. Native API responses and
    business adapters keep the original task contract and all historical facts.
    """
    if (operation_id!='GET /api/flow/cases/{case_id}' or result.get('status')!=200
            or not isinstance(result.get('data'),dict)):
        return result
    projected=copy.deepcopy(result)
    data=projected['data']
    money_fields={}
    for key in ('amount_cents','paid_cents','cost_cents'):
        value=data.get(key)
        if type(value) is not int:continue
        # Format only values the native API already disclosed. Integer quotient
        # and remainder preserve cents exactly, including negative adjustments.
        display=f'{"-" if value<0 else ""}{abs(value)//100}.{abs(value)%100:02d}'
        money_fields[key]={'storage_unit':'分','scale':100,'display':display,'unit':'元'}
    if money_fields:data['money_fields']=money_fields
    kind,version=data.get('kind'),data.get('flow_version')
    spec=None
    if isinstance(kind,str) and type(version) is int:
        try:spec=flow_spec(kind,version)
        except HTTPException as exc:
            # An unknown version has no definition to publish. Never borrow the
            # current catalogue or another version for a historical case.
            if exc.status_code!=409:raise
    if spec and spec['actions']:
        data['workflow_definition']={
            'kind':kind,'flow_version':version,'label':spec['label'],
            'notice':'本原单固定版本的动作与输入表单定义，不是当前可办清单。fields.label属于动作输入表单，不能作为原data数值的存储单位；金额展示使用money_fields/data_fields明确的单位与换算值。roles/states是定义范围，不表示当前授权、任务负责人、执行顺序或前后依赖；本人现在能否办理仍看原actions的enabled/reason及原接口守卫。其它版本指引的额外步骤不能直接套到本单。',
            'actions':[{'key':action.key,'label':action.label,
                'roles':list(action.roles),'states':list(action.states),
                'fields':[{'key':field['key'],'label':field['label']} for field in action.fields]}
                for action in spec['actions']]}
    responsibility_records=[]
    for task in data.get('tasks',[]):
        if task.get('status') not in {'done','cancelled'}:continue
        # A finished task keeps its recorded actor beside its action title.
        # Preserve former responsibility separately, linked by the native task
        # ID; it is neither the event actor nor an action's business recipient.
        assignment={key:task.pop(key) for key in ('role','role_label','assignee_id','assignee_name') if key in task}
        if assignment:responsibility_records.append({'task_id':task['id'],**assignment})
    if responsibility_records:data['task_responsibility_records']=responsibility_records
    return projected


def _guidance(data):
    """下一步推荐：用原单自己的进度、可办事项和待办任务说话，不猜流程、不编造。

    每种业务的可办事项来自它自己的动作目录（页面上的按钮就是这份清单），所以这里不需要
    为每个模块写死流程；状态机变了，推荐跟着变。
    """
    notes=[]
    actions=[item for item in (data.get('actions') or []) if isinstance(item,dict) and item.get('key')]
    ready=[item for item in actions if item.get('enabled')]
    waiting=[item for item in actions if not item.get('enabled')]
    tasks=[item for item in (data.get('tasks') or []) if isinstance(item,dict) and item.get('status')=='open']
    if ready:
        notes.append('本单当前动作条件满足：'+ '、'.join('「%s」' % (item.get('label') or item['key']) for item in ready[:3])
                     +'。这不表示员工已选定本单或要求办理；仅对员工明确选定且属于本次目标的原单准备，确认前不要声称已经办理。')
    if waiting:
        first=waiting[0]
        reason=str(first.get('reason') or '').strip()
        notes.append('「%s」当前还不能办%s；先说明这个前置条件，不要绕开或改权限。'
                     % (first.get('label') or first['key'], ('：'+reason) if reason else ''))
    if tasks:
        notes.append('本单待办：'+ '、'.join('%s%s' % (item.get('title') or item.get('key') or '',
                     ('（%s）' % item['assignee_name']) if item.get('assignee_name') else '') for item in tasks[:2]) + '。仅凭任务与动作的显示顺序无法核实依赖，既不能认定必须依次办理，也不能排除它们是后续必需条件；未核实保持未知。本人的可办性看actions的enabled/reason，其它岗位的任务状态不代替该岗位的原业务条件。')
    if not actions:
        state=str(data.get('state_label') or data.get('state') or '').strip()
        notes.append('这一状态下没有需要你办的事项%s，不要凭空建议下一步。' % (('（当前进度：'+state+'）') if state else ''))
    completed=[item for item in (data.get('tasks') or []) if isinstance(item,dict) and item.get('status')=='done']
    if completed:
        # Keep the recorded actor beside the completed action. Its assignee is
        # a responsibility field and may never have performed that action.
        notes.append('本单已完成任务的原记录：'+'；'.join(
            '%s：实际完成人=%s，完成时间=%s' % (item.get('title') or item.get('key') or '未记录任务名称',
            item.get('done_by_name') or '未记录',item.get('done_at') or '未记录') for item in completed)+'。')
    notes.append('任务的assignee或assignee_name只说明分派负责人，不能代替上述实际完成人或推断为当前员工本人；未记录的完成者和时间保持未知。status为cancelled时done_by、done_by_name及done_at记录终止任务的人和时间，不表示完成业务；其它历史动作仅引用确切对应的事件actor_name。')
    if data.get('kind')!='lead':
        return notes
    state=data.get('state')
    if state=='unassigned':notes.append('先分派接待员工，分派确认后再安排回访；不要猜接手员工。')
    elif state in {'contacting','reminder'}:
        notes.append('安排接待回访可同时补充尚未填写的联系电话；电话已有值时，更正电话请使用客户资料入口。')
    elif state=='intent':
        notes.append('客户正在意向跟进中。“记录意向跟进”确认后保存本次真实沟通结果，并按下次处理日期继续保留意向跟进待办，不表示本单跟进任务或客户跟进已经结束。“结束跟进”是另一个原动作。补充或更正电话请使用客户资料入口，不要退回售前接待。')
    elif state=='closed':notes.append('接待已结束。需要继续联系时，先按原单重新跟进；不能绕过客户的联系意愿。')
    notes.append('沟通结果必须来自员工本次提供的真实沟通事实。只说安排明天回访不代表已经联系；若员工明确今天尚未联系，不要建议用“未联系、计划明日回访”冒充本次沟通结果。先查是否有独立提醒动作；当前动作只能登记已发生沟通时，应说明等待实际结果，不能生成假反馈或联系成功。')
    return notes


async def _customer_record(db,request,user,thread_id,config,data):
    customer=data.get('customer') or {};customer_id=customer.get('id')
    if type(customer_id) is not int:return None,'原单尚未关联客户资料',409
    catalog=await _read(db,request,user,thread_id,config,'GET /api/flow/catalog',query={'assistant_kind':'customers'})
    if catalog.get('status',500)>=400:return None,catalog.get('data',{}).get('detail') or '暂时无法读取客户资料',catalog.get('status',503)
    if not catalog.get('data',{}).get('master_types',{}).get('customers',{}).get('can_write'):
        return None,'请由本店客户负责人维护联系电话',403
    # The native master list enforces both active-store and customer ownership.
    # It has no ID detail endpoint; query the known name and match the exact ID.
    query={'q':str(customer.get('name') or '')[:100]}
    for page in range(1,11):
        result=await _read(db,request,user,thread_id,config,'GET /api/flow/master/{kind}',{'kind':'customers'},{**query,'page':page})
        if result.get('status',500)>=400:return None,result.get('data',{}).get('detail') or '暂时无法读取客户资料，请到客户档案核对',result.get('status',503)
        listing=result.get('data',{})
        if listing.get('truncated'):return None,'同名客户资料较多，请在客户档案中选择本单客户后修改电话',409
        rows=listing.get('items',[])
        row=next((r for r in rows if r.get('id')==customer_id),None)
        if row is not None:
            # The ordinary assistant read boundary redacts secrets. Never write
            # a redacted display back over an unchanged field of the customer.
            if any(marker in str(row.get(key) or '') for key in ('name','note')
                   for marker in ('[密钥已隐藏]','[已隐藏]','[内容过长]','[其余内容请查看原记录]')):
                return None,'客户资料包含隐藏内容，请在客户档案中修改电话，以完整保留原资料',409
            return row,'',200
        if page*listing.get('page_size',30)>=listing.get('total',0):
            return None,'当前客户资料不在本人可维护范围，请由客户负责人处理',403
    return None,'同名客户较多，请在客户档案选择本单客户后修改电话',409


async def _employee_choices(db,request,user,thread_id,config,data):
    found=False
    for action in data.get('actions',[]):
        fields=[field for field in action.get('fields',[]) if field.get('type')=='employee']
        if not fields:continue
        found=True
        # Candidate eligibility belongs to this native action, not to every
        # employee who can be found in the store's general directory.
        query={'case_id':data['id'],'action':action['key']}
        result=await _read(db,request,user,thread_id,config,'GET /api/flow/lookup/{kind}',
                           {'kind':'employee'},query)
        lookup={'operation_id':'GET /api/flow/lookup/{kind}','path_args':{'kind':'employee'},'query':query}
        listing=result.get('data') if result.get('status')==200 else None
        for field in fields:
            field['lookup_action']=action['key']
            field['candidate_lookup']=lookup
            if isinstance(listing,dict):
                field['candidates']=[{'label':x['label'],'value':x['id']} for x in listing.get('items',[])
                                     if type(x.get('id')) is int and isinstance(x.get('label'),str)]
                field['candidates_has_more']=bool(listing.get('has_more') or listing.get('truncated'))
            else:
                field['candidate_lookup_error']='本次员工候选未读取成功；不要冒充没有员工，也不要猜编号。'
    if not found:return data
    data.setdefault('assistant_guidance',[]).append(
        '员工候选来自本店原动作的接手选择器，不是一般员工或管理员账号目录；已给姓名可在真实候选中唯一匹配后填写编号，'
        '未选人则用中文候选缺项卡。同名或候选未列完须进一步查找，不自动选第一项。')
    return data


async def _case(db,request,user,thread_id,config,case_id,with_contact=True):
    result=await _read(db,request,user,thread_id,config,'GET /api/flow/cases/{case_id}',{'case_id':case_id})
    if result.get('status',500)>=400:return result,None
    data=result.get('data')
    if not isinstance(data,dict):raise HTTPException(409,'未能读取业务资料，请重新查询')
    if data.get('truncated'):raise HTTPException(409,'原单资料较多，请在原业务页面核对当前步骤')
    data['assistant_guidance']=_guidance(data)
    await _employee_choices(db,request,user,thread_id,config,data)
    customer=None
    if with_contact and data.get('customer',{}):
        customer,reason,status=await _customer_record(db,request,user,thread_id,config,data)
        data['related_operations']=[{
            'key':'customer_contact','label':'更正联系电话' if data['customer'].get('phone') else '补充联系电话',
            'tool':'prepare_customer_contact','enabled':customer is not None,'reason':reason,'status':status,
            'fields':[{'key':'phone','label':'联系电话','type':'text','required':True}],
            'manual_route':'master/customers',
            'notice':'只修改本单客户的电话；姓名、联系意愿和备注保持原值，确认后保存。',
        }]
    return result,customer


async def resolve_preparation(db,request,user,thread_id,name,args,config):
    """Complete authorized reads and validation without persisting a draft."""
    from . import business_assistant_service as s
    s.require_preparation_read_phase(db)
    allowed={
        'find_cases':{'query','kind','scope','page'},'get_case':{'case_id'},
        'prepare_case_action':{'case_id','action','values','summary','questions'},
        'prepare_customer_contact':{'case_id','phone','summary'},
    }
    if name not in allowed or not isinstance(args,dict) or set(args)-allowed[name]:
        raise HTTPException(422,'请按本项业务工具填写，不要提供接口地址、门店或版本')
    if name=='find_cases':
        query=args.get('query','');kind=args.get('kind','');scope=args.get('scope','mine');page=args.get('page',1)
        if not isinstance(query,str) or len(query)>100 or not isinstance(kind,str) or len(kind)>60:
            raise HTTPException(422,'请使用姓名、业务单号或业务类别查找，查询词不超过100字')
        if scope not in {'mine','visible'} or type(page) is not int or not 1<=page<=10000:
            raise HTTPException(422,'请核对业务查询范围和页码')
        result=await _read(db,request,user,thread_id,config,'GET /api/flow/cases',query={'q':query.strip(),'kind':kind,'page':page,'page_size':30})
        if result.get('status',500)>=400:return result
        listing=result.get('data',{})
        if listing.get('truncated'):raise HTTPException(409,'查询结果较多，请补充客户姓名或单号缩小范围')
        rows=listing.get('items',[])
        if scope=='mine':rows=[r for r in rows if r.get('owner_id')==user.id]
        more=page*listing.get('page_size',30)<listing.get('total',0)
        fields=('id','number','title','kind','kind_label','state','state_label','owner_id','owner_name','customer_id','business_date','due_date')
        items=[{**{key:row.get(key) for key in fields},
                **{key:row[key] for key in ('flow_version','version','parent_id') if key in row},
                'route':'case/'+str(row['id'])} for row in rows]
        notice=('结果仅覆盖本次员工、门店、业务类别、关键词和页码；单一类别或筛选为空，不代表本店全部业务都没有记录。'
                '候选只证明本次可检索，未核本单可办动作或父单权限；选定后必须以本人get_case返回的动作、字段和拒绝原因判断能否准备，不能承诺凭单号即可办理。'
                '子单可见不表示本人可以读取或办理父单，父单须按本人当前权限单独核对。')
        if kind in {'purchase','procurement'}:
            notice+='物资采购同时保留purchase（物资采购入库）和procurement（采购与原单退货）原单类别。查询总体采购及入库情况需分别查这两类并核对原单，不得把一类为空当作没有采购，也不得把付款当作到货。'
        return {'status':200,'data':{'items':items,'scope':scope,'page':page,'has_more':more,
            'business_kind':kind,'notice':notice,
            'next_page':page+1 if more else None,'selection_required':len(items)>1 or more,
            'next':('有后续查询页；本页没有匹配不代表全部没有，请继续查询。' if more else
                    '找到一个候选，可读取原单核对后继续，无需重复索要编号。' if len(items)==1 else
                    '这些候选用于确定本次要办的原单；员工尚未明确选定本次原单、也未明确要求全部或逐个办理时，请先列出姓名、单号和状态让其选择。不要自动选第一条，也不要给各候选分别建卡让员工事后取舍。' if len(items)>1 else
                    '本次未找到本人负责记录，可用visible查询本店当前可见记录。' if scope=='mine' else
                    '未找到记录，请补充客户姓名或业务单号。')},'route':'cases/'+kind if kind else 'work'}
    case_id=_case_id(args)
    result,customer=await _case(db,request,user,thread_id,config,case_id,with_contact=name!='prepare_case_action')
    if name=='get_case' or result.get('status',500)>=400:return result
    data=result['data']
    if name=='prepare_customer_contact':
        if customer is None:
            related=data.get('related_operations') or [{}]
            raise HTTPException(related[0].get('status',409),related[0].get('reason') or '未能读取本单客户资料，请重新核对')
        phone=args.get('phone')
        if not isinstance(phone,str) or not phone.strip():raise HTTPException(422,'请提供客户的联系电话')
        phone=normalized_phone(phone)
        if phone==customer.get('phone'):return {'status':200,'data':{'unchanged':True,'message':'当前已是这个电话，无需重复修改'},'route':'master/customers'}
        if type(customer.get('version')) is not int:raise HTTPException(409,'未能读取客户资料版本，请重新查询')
        values={key:copy.deepcopy(customer.get(key)) for key in ('name','contact_allowed','note')}
        values['phone']=phone;values['note']=values.get('note') or ''
        return s.resolve_preparation(db,user,thread_id,{
            'operation_id':'PUT /api/flow/master/{kind}/{record_id}',
            'path_args':{'kind':'customers','record_id':customer['id']},
            'body':{'version':customer['version'],'values':values},
            'summary':args.get('summary') or '更新'+str(customer['name'])+'的联系电话',
        })
    if type(data.get('version')) is not int or not isinstance(data.get('actions'),list):
        raise HTTPException(409,'未能读取这项业务的最新可办事项，请刷新原单')
    key=args.get('action');action=next((item for item in data['actions'] if item.get('key')==key),None)
    if action is None:
        if data.get('kind')=='lead' and data.get('state')=='intent' and key=='remind':
            raise HTTPException(409,'客户正在意向跟进中，请用“记录意向跟进”安排下次日期；补电话可在客户资料中填写')
        try:known=next((a for a in flow_spec(data['kind'],data['flow_version'])['actions'] if a.key==key),None)
        except (KeyError,HTTPException):known=None
        if known and data.get('state') not in known.states:raise HTTPException(409,'当前进度不能办理此步骤，请按原单列出的事项继续')
        raise HTTPException(403 if known else 422,'当前没有这项可办事项，请按原单列出的事项继续')
    if action.get('enabled') is not True:raise HTTPException(409,action.get('reason') or '请先完成前置步骤')
    values=args.get('values')
    if not isinstance(values,dict):raise HTTPException(422,'请填写本次办理内容')
    # Parsing validates missing facts but must not replace submitted yuan / qty
    # strings with their native integer conversions before the API parses again.
    question_fields=action.get('fields',[])
    args=copy.deepcopy(args)
    if args.get('questions'):
        for question in args['questions']:
            field=next((f for f in question_fields if 'values.'+f['key']==question.get('key')),None)
            if field and field.get('type')=='employee':
                if not question.get('options'):
                    if field.get('candidates_has_more') or not field.get('candidates'):
                        raise HTTPException(422,'员工候选未完整确定，请按已提供的candidate_lookup按姓名缩小查询，不要让员工手抄编号')
                    question['options']=field['candidates']
                elif not isinstance(question['options'],list):
                    raise HTTPException(422,'员工候选必须按列表提供，请按candidate_lookup重新核对')
                elif not field.get('candidates_has_more') and 'candidates' in field:
                    # A model-supplied list may be a valid subset, but cannot
                    # add people from the broader directory or relabel them.
                    from .business_assistant_forms import option_value
                    choices={option_value(item):item for item in field['candidates']}
                    if any(option_value(item) not in choices for item in question['options']):
                        raise HTTPException(422,'员工选项不属于本动作的真实接手候选，请按candidate_lookup重新核对')
                    question['options']=[choices[option_value(item)] for item in question['options']]
        from . import business_assistant_gateway as gateway
        from .business_assistant_service import sanitize_questions,answer_probe
        questions=sanitize_questions(args['questions'])
        allowed_keys={'values.'+field['key'] for field in question_fields}
        if any(q['key'] not in allowed_keys for q in questions):
            raise HTTPException(422,'缺项必须是当前原单动作中列出的字段')
        probe=answer_probe(gateway,'POST /api/flow/cases/{case_id}/actions/{action}',
                           {'values':values},questions,{'case_id':case_id,'action':action['key']},question_fields)
        parse_fields(question_fields,probe['values'])
    else:
        parse_fields(question_fields,values)
    return s.resolve_preparation(db,user,thread_id,{
        'operation_id':'POST /api/flow/cases/{case_id}/actions/{action}',
        'path_args':{'case_id':case_id,'action':action['key']},
        'body':{'version':data['version'],'values':values},
        'summary':args.get('summary') or action.get('label') or '办理当前业务',
        'questions':args.get('questions'),
    },question_fields=question_fields)


async def handle_case_tool(db,request,user,thread_id,name,args,config,*,resolve_only=False):
    """Keep the original tool result; Runtime may request only resolved intent."""
    from . import business_assistant_service as s
    result = await resolve_preparation(db,request,user,thread_id,name,args,config)
    if resolve_only or not isinstance(result,s.ResolvedPreparation):
        return result
    return s.commit_preparation(db,user,thread_id,result)
