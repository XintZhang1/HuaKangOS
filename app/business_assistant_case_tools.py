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


def _guidance(data):
    if data.get('kind')!='lead':return []
    state=data.get('state');notes=[]
    if state=='unassigned':notes.append('先分派接待员工，分派确认后再安排回访；不要猜接手员工。')
    elif state in {'contacting','reminder'}:
        notes.append('安排接待回访可同时补充尚未填写的联系电话；电话已有值时，更正电话请使用客户资料入口。')
    elif state=='intent':
        notes.append('客户正在意向跟进中。“记录意向跟进”可以登记下次处理日期；补充或更正电话请使用客户资料入口，不要退回售前接待。')
    elif state=='closed':notes.append('接待已结束。需要继续联系时，先按原单重新跟进；不能绕过客户的联系意愿。')
    notes.append('沟通结果必须来自员工本次提供的事实。只说安排明天回访不代表已经联系，缺少结果时只询问这一项；不能编造客户反馈或联系成功。')
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


async def _case(db,request,user,thread_id,config,case_id,with_contact=True):
    result=await _read(db,request,user,thread_id,config,'GET /api/flow/cases/{case_id}',{'case_id':case_id})
    if result.get('status',500)>=400:return result,None
    data=result.get('data')
    if not isinstance(data,dict):raise HTTPException(409,'未能读取业务资料，请重新查询')
    if data.get('truncated'):raise HTTPException(409,'原单资料较多，请在原业务页面核对当前步骤')
    data['assistant_guidance']=_guidance(data)
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


async def handle_case_tool(db,request,user,thread_id,name,args,config):
    """Entry for service.run_tools. Only prepare_proposal can persist a draft."""
    from .business_assistant_service import prepare_proposal
    allowed={
        'find_cases':{'query','kind','scope','page'},'get_case':{'case_id'},
        'prepare_case_action':{'case_id','action','values','summary'},
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
        items=[{**{key:row.get(key) for key in fields},'route':'case/'+str(row['id'])} for row in rows]
        return {'status':200,'data':{'items':items,'scope':scope,'page':page,'has_more':more,
            'next_page':page+1 if more else None,'selection_required':len(items)>1 or more,
            'next':('有后续查询页；本页没有匹配不代表全部没有，请继续查询。' if more else
                    '找到一个候选，可读取原单核对后继续，无需重复索要编号。' if len(items)==1 else
                    '请让员工从姓名、单号和状态中选择，不要自动选第一条。' if len(items)>1 else
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
        return prepare_proposal(db,user,thread_id,{
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
    parse_fields(action.get('fields',[]),values)
    return prepare_proposal(db,user,thread_id,{
        'operation_id':'POST /api/flow/cases/{case_id}/actions/{action}',
        'path_args':{'case_id':case_id,'action':action['key']},
        'body':{'version':data['version'],'values':values},
        'summary':args.get('summary') or action.get('label') or '办理当前业务',
    })
