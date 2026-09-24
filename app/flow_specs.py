"""Executable workflow catalogue. UI forms and backend validation share these definitions.
No action accepts arbitrary state names or evaluates user-provided expressions.
"""
from dataclasses import dataclass, field
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from fastapi import HTTPException
from .db import today


def f(key, label, type='text', required=True, **kw):
    return dict(key=key,label=label,type=type,required=required,**kw)

NAME=f('customer_name','客户姓名'); PHONE=f('customer_phone','联系电话',required=False)
NOTE=f('note','说明','textarea',False)
REASON=f('reason','原因','textarea')
WHEN=f('due_date','下次处理日期','future_date')
ASSIGNEE=f('assignee_id','接手员工','employee')
MONEY=f('amount','金额（元）','money')
ACCOUNT=f('account_id','收付款账户','account')
VOUCHER=f('reference','银行流水号或凭证号')
EVIDENCE=f('evidence_id','到账凭据','file')
PAY_FIELDS=[MONEY,ACCOUNT,VOUCHER,EVIDENCE]
CUSTOMER_FIELDS=[NAME,PHONE]
ITEM=f('item_id','物资','item'); QTY=f('quantity','数量','quantity')
MEMBER=f('member_id','会员','member')

@dataclass(frozen=True)
class Action:
    key:str
    label:str
    roles:tuple
    states:tuple
    fields:list=field(default_factory=list)
    task:str=''
    confirm:str=''


def a(key,label,roles,states,fields=None,task='',confirm=''):
    return Action(key,label,tuple(roles.split(',')),tuple(states.split(',')),fields or [],task,confirm)

# Administrative overrides are explicit in engine.can_role; financial facts are not bypassed.
SPECS_V1={
'lead':dict(label='售前接待',module='sales',create_roles=['reception','sales','manager','admin'],
 fields=CUSTOMER_FIELDS+[f('model','关注车型',required=False),f('source','客户来源','select',options=['展厅到店','电话咨询','网络咨询','转介绍']),NOTE],initial='unassigned',
 actions=[a('assign','分派接待','reception,manager','unassigned',[ASSIGNEE],task='assign'),
 a('intent','转意向客户','sales,reception','contacting,reminder',[f('need','购车需求','textarea'),WHEN],task='contact'),
 a('remind','安排接待回访','sales,reception','contacting,reminder',[PHONE,WHEN,f('result','本次沟通结果','textarea')],task='contact'),
 a('follow','记录意向跟进','sales','intent',[f('result','本次沟通结果','textarea'),WHEN],task='follow'),
 a('reserve','转车辆预订','sales','intent',[f('model','订购车型'),f('amount','车辆约定金额（元）','money'),f('delivery_due','预计交付日期','future_date'),f('addon','需要精品加装','bool',False),f('insurance','本店办理保险','bool',False),f('agency','需要代办服务','bool',False),NOTE],task='follow'),
 a('close','结束跟进','sales,reception','contacting,reminder,intent',[REASON,f('no_contact','客户不希望后续联系','bool',False)],confirm='结束后不再安排本次业务的跟进任务。'),
 a('reopen','重新跟进','sales','closed',[REASON,WHEN])]),
'order':dict(label='车辆订单',module='sales',create_roles=['sales','admin','manager'],
 fields=CUSTOMER_FIELDS+[f('model','订购车型'),f('amount','车辆约定金额（元）','money'),f('delivery_due','预计交付日期','future_date'),f('addon','需要精品加装','bool',False),f('insurance','本店办理保险','bool',False),f('agency','需要代办服务','bool',False),NOTE],initial='reserved',
 actions=[a('approve','确认订单','manager','reserved',task='approve'),
 a('revise','修改待确认订单','sales','reserved',[f('model','订购车型'),f('amount','车辆约定金额（元）','money'),REASON]),
 a('allocate','选择配车','inventory','executing',[f('vehicle_id','可用车辆','vehicle')],task='allocate'),
 a('sign','确认合同签回','sales','executing',[f('evidence_id','已签合同','signed_file')],task='sign'),
 a('receive','登记实际收款','finance','executing',PAY_FIELDS,task='receive'),
 a('inspect','确认交车检查','technician,service','executing',[f('evidence_id','检测记录','file'),f('result','检查结论','textarea')],task='inspect'),
 a('dispatch','确认车辆出库','inventory','executing',[f('evidence_id','出库凭据','file')],task='dispatch'),
 a('deliver','确认客户提车','sales','executing',[f('evidence_id','提车签回件','handover_file')],task='deliver',confirm='确认客户已经接车。本操作记录实际交接，不可用来预先推进流程。'),
 a('cancel_request','申请退订','sales','reserved,executing',[REASON]),
 a('cancel_approve','批准退订','manager','cancel_review',task='cancel_approve'),
 a('cancel_reject','退回退订申请','manager','cancel_review',[REASON],task='cancel_approve'),
 a('refund','登记退订退款','finance','refund_pending',[f('original_id','原收款','payment')]+PAY_FIELDS,task='refund')]),
'repair':dict(label='维修工单',module='repair',create_roles=['service','admin','manager'],
 fields=CUSTOMER_FIELDS+[f('plate','车牌号'),f('repair_type','业务类型','select',options=['一般维修','保养','洗车','保险理赔','厂家索赔','返修','新车检测']),f('problem','客户描述','textarea'),f('due_date','预计完工日期','future_date')],initial='assessment',
 actions=[a('quote','登记报价','service','assessment',[f('labor','工时金额（元）','money_zero'),f('parts','配件金额（元）','money_zero'),f('discount','优惠金额（元）','money_zero'),f('labor_cost','工时直接成本（元）','money_zero'),f('payer','结算方','select',options=['客户','保险公司','厂家','内部']),f('work','施工项目','textarea')],task='quote'),
 a('authorize','确认客户授权','service','authorization',[f('evidence_id','客户授权凭据','file')],task='authorize'),
 a('start','接车开工','technician,service','working',task='work'),
 a('material','申请领料','technician,service','working',[ITEM,QTY,NOTE]),
 a('return_material','退回未用材料','technician,service','working,quality',[f('move_id','原领料记录','stock_issue'),QTY,REASON]),
 a('finish','报完工','technician,service','working',[f('result','施工结果','textarea')],task='work'),
 a('quality','通过质检','service','quality',[f('evidence_id','质检记录','file')],task='quality'),
 a('rework','退回返工','service','quality',[REASON],task='quality'),
 a('receive','登记实际收款','finance','settling',PAY_FIELDS,task='receive'),
 a('apply_balance','使用会员余额','finance','settling',[MEMBER,MONEY,EVIDENCE]),
 a('internal_settle','确认内部承担','manager','settling',[REASON],task='internal_settle'),
 a('credit','批准月结交车','manager','settling',[f('due_date','约定付款日','future_date'),REASON]),
 a('release','确认客户接车','service','settling',[f('evidence_id','接车凭据','file')],task='release'),
 a('late_receive','登记月结到账','finance','credit_open',PAY_FIELDS,task='receive'),
 a('cancel','取消未授权工单','service','assessment,authorization',[REASON])]),
'addon':dict(label='精品加装',module='sales',create_roles=[],fields=[],initial='pending',
 actions=[a('service_quote','确认加装金额','sales','pending',[f('amount','加装收费（元）','money_zero'),f('work','加装项目','textarea')],task='service'),
 a('material','申请领料','technician,service','working',[ITEM,QTY,NOTE]),
 a('service_finish','确认加装完成','technician,service','working',[f('evidence_id','完工凭据','file')],task='work'),
 a('receive','登记实际收款','finance','settling',PAY_FIELDS,task='receive')]),
'insurance':dict(label='车辆保险',module='sales',create_roles=['service','admin','manager'],
 fields=CUSTOMER_FIELDS+[f('plate','车牌号',required=False),NOTE],initial='pending',
 actions=[a('service_quote','确认保险方案','service','pending',[f('amount','代收保费（元）','money_zero'),f('insurer','保险公司'),f('commission','预计佣金（元）','money_zero')],task='service'),
 a('policy_issue','登记已出保单','service','working',[f('policy_number','保单号'),f('start_date','生效日期','date'),f('end_date','到期日期','date'),f('evidence_id','保单文件','file')],task='work'),
 a('receive','登记代收保费','finance','settling',PAY_FIELDS,task='receive')]),
'agency':dict(label='代办服务',module='sales',create_roles=[],fields=[],initial='pending',
 actions=[a('service_quote','确认代办项目','service','pending',[f('amount','代办服务收费（元）','money_zero'),f('work','办理内容','textarea')],task='service'),
 a('service_finish','确认办理完成','service','working',[f('evidence_id','办理凭据','file')],task='work'),
 a('receive','登记实际收款','finance','settling',PAY_FIELDS,task='receive')]),
'purchase':dict(label='物资采购入库',module='materials',create_roles=['inventory','manager','admin'],
 fields=[ITEM,QTY,f('unit_cost','单价（元）','money_zero'),f('supplier','供应商'),NOTE],initial='approval',
 actions=[a('approve','批准采购','manager','approval',task='approve'),a('reject','退回采购','manager','approval',[REASON],task='approve'),
 a('stock_in','确认实际到货','inventory','receiving',[f('evidence_id','到货验收凭据','file')],task='stock_in')]),
'material_issue':dict(label='维修领料',module='materials',create_roles=[],fields=[],initial='approval',
 actions=[a('issue','确认发料','inventory','approval',[f('evidence_id','领料凭据','file')],task='issue'),a('reject','退回领料申请','inventory','approval',[REASON],task='issue')]),
'material_return':dict(label='维修退料',module='materials',create_roles=[],fields=[],initial='approval',
 actions=[a('return_in','确认退料入库','inventory','approval',[f('evidence_id','退料验收凭据','file')],task='return_in'),a('reject','退回退料申请','inventory','approval',[REASON],task='return_in')]),
'stock_count':dict(label='物资盘点',module='materials',create_roles=['inventory','admin','manager'],
 fields=[ITEM,f('counted','实盘数量','quantity_zero'),REASON],initial='approval',
 actions=[a('count_approve','复核并登记差异','manager','approval',[f('evidence_id','盘点凭据','file')],task='approve'),a('reject','退回盘点','manager','approval',[REASON],task='approve')]),
'callback':dict(label='客户回访',module='customers',create_roles=['customer_service','sales','service','manager','admin'],
 fields=CUSTOMER_FIELDS+[f('topic','回访事项'),WHEN],initial='pending',
 actions=[a('callback_done','记录回访结果','customer_service,sales,service','pending',[f('result','回访结果','textarea')],task='callback'),
 a('callback_later','再次安排回访','customer_service,sales,service','pending',[WHEN,f('result','本次联系结果','textarea')],task='callback'),
 a('new_intent','转购车意向','customer_service,sales,service','pending',[f('need','购车需求','textarea'),WHEN],task='callback'),
 a('new_complaint','转客户投诉','customer_service,sales,service','pending',[f('problem','投诉内容','textarea')],task='callback'),
 a('close','结束本次联系','customer_service,sales,service','pending',[REASON])]),
'complaint':dict(label='客户投诉',module='customers',create_roles=['customer_service','service','sales','manager','admin'],
 fields=CUSTOMER_FIELDS+[f('problem','投诉内容','textarea')],initial='pending',
 actions=[a('plan','登记处理方案','manager','pending',[f('plan','处理方案','textarea'),WHEN],task='plan'),
 a('resolve','确认处理结果','customer_service,service','resolving',[f('result','处理结果','textarea'),f('evidence_id','处理凭据','file')],task='resolve'),
 a('reopen','重新处理','manager','completed',[REASON])]),
'member_topup':dict(label='会员充值',module='members',create_roles=['customer_service','service','finance','manager','admin'],
 fields=[MEMBER,MONEY,NOTE],initial='pending',
 actions=[a('topup_receive','登记充值到账','finance','pending',[ACCOUNT,VOUCHER,EVIDENCE],task='topup_receive'),a('cancel','取消未到账充值','finance,service,customer_service','pending',[REASON])]),
'member_refund':dict(label='会员余额退款',module='members',create_roles=['customer_service','service','finance','manager','admin'],
 fields=[MEMBER,MONEY,REASON],initial='approval',
 actions=[a('approve','批准余额退款','manager','approval',task='approve'),a('reject','退回退款申请','manager','approval',[REASON],task='approve'),
 a('member_refund_pay','登记退款到账','finance','refund_pending',[ACCOUNT,VOUCHER,EVIDENCE],task='member_refund_pay')]),
'invoice':dict(label='开票登记',module='finance',create_roles=['finance','admin','manager'],
 fields=[f('related_case_id','关联业务','billable_case'),f('invoice_title','发票抬头'),f('tax_number','税号',required=False),MONEY],initial='pending',
 actions=[a('invoice_issue','登记开票结果','finance','pending',[f('invoice_number','发票号码'),f('evidence_id','发票文件','file')],task='invoice_issue'),a('cancel','取消未开票申请','finance','pending',[REASON])]),
}

# Version 1 is the preserved catalogue for existing cases. Never edit its business
# semantics to introduce a new flow: copy it into an explicitly registered version.
CURRENT_FLOW_VERSION=2
SPECS_V2=deepcopy(SPECS_V1)
for _spec in SPECS_V2.values():
    if any(_field['key']=='customer_name' for _field in _spec['fields']):
        for _field in _spec['fields']:
            if _field['key']=='customer_name':_field['required']=False
        _spec['fields']+=[f('customer_id','已有客户','customer',False),f('confirm_new_customer','已核对另建独立档案','bool',False)]
INSPECTION_FIELDS=[f('evidence_id','检测记录','file'),
    f('outcome','检查结果','select',options=['合格','不合格']),
    f('result','检查发现与结论','textarea')]
SPECS_V2['order']['actions']=[
    a('inspect','登记交车检查','technician,service','executing',INSPECTION_FIELDS,task='inspect')
    if action.key=='inspect' else action for action in SPECS_V2['order']['actions']]
SPECS_V2['order']['actions'][6:6]=[
    a('rectify','登记缺陷处理','technician,service','executing',
      [f('result','缺陷处理结果','textarea'),f('evidence_id','缺陷处理凭据','file')],task='rectify'),
    a('reinspect','登记交车复检','technician,service','executing',INSPECTION_FIELDS,task='reinspect')]
SPECS_V2['purchase']['actions'].append(a('cancel','取消未到货采购','manager','receiving',[REASON],
    confirm='仅限尚未发生实际到货或付款的采购，取消后关闭到货待办。'))
SPECS_V2['member_refund']['actions'].append(a('cancel','撤销未支付退款','manager,finance','refund_pending',[REASON],
    confirm='确认尚未实际退款。撤销只释放本申请占用的余额，不产生资金或会员流水。'))
SPECS_V2['procurement']=dict(label='采购与供应商结算',module='materials',create_roles=[],fields=[],initial='approval',actions=[])
SPECS_V2['material_transfer']=dict(label='物资调拨',module='materials',create_roles=[],fields=[],initial='approval',actions=[])
SPECS_V2['vehicle_transfer']=dict(label='整车调拨',module='warehouse',create_roles=[],fields=[],initial='approval',actions=[])
SPECS_V2['customer_care']=dict(label='客户服务任务',module='customers',create_roles=[],fields=[],initial='pending',actions=[])
SPECS_V2['vehicle_procurement']=dict(label='整车采购与付款',module='warehouse',create_roles=[],fields=[],initial='approval',actions=[])
SPECS_V2['vehicle_operations']=dict(label='整车库位与出退库',module='warehouse',create_roles=[],fields=[],initial='approval',actions=[])
SPECS_V2['aftercare']=dict(label='退订退车与原单退费',module='sales',create_roles=[],fields=[],initial='approval',actions=[])
SPECS_V2['business_finance']=dict(label='预收、月结与收款更正',module='finance',create_roles=[],fields=[],initial='approval',actions=[])
SPECS_V2['retail']=dict(label='精品销售与退货',module='materials',create_roles=[],fields=[],initial='approval',actions=[])
SPECS_V2['reconciliation']=dict(label='业务对账与月结',module='finance',create_roles=[],fields=[],initial='pending',actions=[])
SPECS_V2['interstore_clearing']=dict(label='门店往来结算',module='finance',create_roles=[],fields=[],initial='pending',actions=[])
SPECS_V2['warehouse']=dict(label='仓储作业',module='materials',create_roles=[],fields=[],initial='pending',actions=[])
SPECS_V2['membership']=dict(label='集团会员办理',module='members',create_roles=[],fields=[],initial='pending',actions=[])
SPECS_V2['opening_import']=dict(label='正式期初核验',module='system',create_roles=[],fields=[],initial='approval',actions=[])
SPECS_V2['recharge_bundle']=dict(label='会员组合充值',module='members',create_roles=[],fields=[],initial='pending',actions=[])
SPECS_V2['claim']=dict(label='理赔索赔与客户报销',module='repair',create_roles=[],fields=[],initial='assessment',actions=[])
SPECS_V2['service_intake']=dict(label='维修接待与返修',module='repair',create_roles=[],fields=[],initial='pending',actions=[])
SPECS_V2['other_income']=dict(label='其它客户服务收入',module='sales',create_roles=[],fields=[],initial='pending',actions=[])
SPECS_V3={'repair':dict(label='维修明细工单',module='repair',create_roles=[],fields=[],initial='assessment',actions=[])}
SPECS_V3['procurement']=dict(label='采购与原单退货',module='materials',create_roles=[],fields=[],initial='approval',actions=[])
SPECS_V3['material_transfer']=dict(label='物资调拨与运输差异',module='materials',create_roles=[],fields=[],initial='approval',actions=[])
from .insurance_specs import spec as insurance_spec
SPECS_V3['insurance']=insurance_spec()
SPECS_V3['addon']=dict(label='销售精品加装明细',module='sales',create_roles=[],fields=[],initial='pending',actions=[])
SPECS_V3['agency']=dict(label='代办明细服务',module='sales',create_roles=[],fields=[],initial='pending',actions=[])
SPECS_V3['invoice']=dict(label='开票与原票冲红',module='finance',create_roles=[],fields=[],initial='approval',actions=[])
SPECS_V4={'repair':dict(label='维修明细工单',module='repair',create_roles=[],fields=[],initial='assessment',actions=[])}
from .sales_quote_specs import order_spec
SPECS_V3['order']=order_spec(SPECS_V2['order'])
SPECS_V4['order']=order_spec(SPECS_V2['order'])
SPECS_V4['order']['label']='车辆报价与明细服务交付'
SPECS_V1['business_entity']=dict(label='经营主体配置',module='system',create_roles=[],fields=[],initial='draft',actions=[])
SPECS_V2['business_entity']=deepcopy(SPECS_V1['business_entity'])
SPECS_V2['observation_correction']=dict(label='日期里程纠正',module='customers',create_roles=[],fields=[],initial='pending',actions=[])
SPECS_V2['retail_group_rule']=dict(label='精品权益商品规则',module='members',create_roles=[],fields=[],initial='draft',actions=[])
from .vehicle_income_specs import spec as vehicle_income_spec
SPECS_V1['vehicle_income']=vehicle_income_spec()
from .member_pricing_specs import spec as member_pricing_spec
SPECS_V1['member_pricing_rule']=member_pricing_spec()
FLOW_CATALOGUES={1:SPECS_V1,2:SPECS_V2,3:SPECS_V3,4:SPECS_V4}
# Metadata-only compatibility export; persisted cases must use flow_spec.
SPECS={**SPECS_V2,'vehicle_income':SPECS_V1['vehicle_income'],'member_pricing_rule':SPECS_V1['member_pricing_rule']}


def flow_spec(kind,version):
    spec=FLOW_CATALOGUES.get(version,{}).get(kind)
    if spec is None:raise HTTPException(409,'此业务的流程版本不受支持，请由管理员核对升级状态；没有执行任何操作')
    return spec

STATES={'draft':'待提交','unassigned':'待分派','contacting':'待接待反馈','reminder':'接待回访中','intent':'意向跟进中','converted':'已转订单','closed':'已结束',
'reserved':'订单待确认','executing':'交付准备中','delivered':'已提车','cancel_review':'退订待审批','refund_pending':'待退款','cancelled':'已取消',
'assessment':'待检查报价','authorization':'待客户授权','working':'处理中','quality':'待质检','settling':'待结算交接','credit_open':'已交车待月结',
'completed':'已完成','pending':'待办理','approval':'待复核','receiving':'待到货','rejected':'已退回','resolving':'处理中'}
MODULES=[('sales','整车销售'),('warehouse','整车仓库'),('repair','维修管理'),('materials','物资管理'),('finance','财务管理'),('customers','客户管理'),('members','会员服务'),('analytics','数据可视化'),('reference','基础数据'),('system','系统管理')]
STATES.update(approved='已批准待办理',ready='待实际办理',counting='现场实盘中',review='待复核差异',transit='店内在途',returning='拒收待实际返回')
TERMINAL={'completed','delivered','cancelled','closed','converted','rejected'}


def parse_fields(fields,values):
    if not isinstance(values,dict): raise HTTPException(422,'填写内容格式不正确')
    allowed={x['key'] for x in fields}
    if set(values)-allowed: raise HTTPException(422,'提交中含有当前操作不允许修改的字段')
    result={}
    for spec in fields:
        key,kind=spec['key'],spec['type'];value=values.get(key)
        if value is None or value=='':
            if spec['required']: raise HTTPException(422,f"请填写{spec['label']}")
            result[key]=False if kind=='bool' else '';continue
        try:
            if kind=='bool':
                if not isinstance(value,bool): raise ValueError()
            elif kind in {'money','money_zero','quantity','quantity_zero'}:
                if isinstance(value,bool):raise ValueError()
                n=Decimal(str(value));scale=1000 if kind.startswith('quantity') else 100
                if not n.is_finite() or n<0 or n>Decimal('9999999999.99') or n*scale!=(n*scale).to_integral_value():raise ValueError()
                if kind in {'money','quantity'} and n==0:raise ValueError()
                value=int(n*scale)
            elif kind in {'date','future_date'}:
                value=date.fromisoformat(str(value))
                if value<date(2000,1,1) or value.year>2100:raise ValueError()
                if kind=='future_date' and value<today():raise HTTPException(422,f"{spec['label']}不能早于今天")
                value=value.isoformat()
            elif kind in {'employee','vehicle','account','file','signed_file','handover_file','item','member','payment','stock_issue','billable_case','customer'}:
                if isinstance(value,bool) or str(value).strip()!=str(int(value)) or int(value)<=0:raise ValueError()
                value=int(value)
            else:
                if not isinstance(value,str):raise ValueError()
                value=value.strip()
                if not value or len(value)>(2000 if kind=='textarea' else 180):raise ValueError()
                if key=='customer_phone' and not re.fullmatch(r'[0-9+() \-]{3,30}',value):raise ValueError()
                if kind=='select' and value not in spec.get('options',[]):raise ValueError()
        except (ValueError,TypeError,InvalidOperation):
            raise HTTPException(422,f"{spec['label']}填写不正确，请检查格式和数值范围")
        result[key]=value
    return result
