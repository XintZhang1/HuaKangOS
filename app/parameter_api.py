"""Configuration entry points; each original editor remains the write authority."""
from fastapi import APIRouter,Depends
from .security import get_user
from .config import settings
from .master_data import public_catalog

router=APIRouter(prefix='/api/parameters',tags=['参数与个人密码'])
# Fixed internal routes, not client-provided URLs or arbitrary environment settings.
# Manage roles match the native service, including admin-only group rule publication.
ENTRIES=(
    ('customer-reminders','保养与续保提醒','里程、日期与提醒窗口规则',{'admin','manager','service','customer_service','auditor'},{'admin','manager'}),
    ('customer-questionnaires','问卷题目版本','新增题目版本，经不同人员复核后用于新问卷',{'admin','manager','service','customer_service','auditor'},{'admin','manager'}),
    ('service-intake/resources','工位与快捷项目组合','维护服务工位和作业项目预填组合',{'admin','manager','service','reception','customer_service','finance','auditor'},{'admin','manager'}),
    ('membership-rules','集团等级、续会与消费积分','版本化的会员年费、积分与适用门店规则',{'admin','manager','service','reception','customer_service','finance','auditor','sales'},{'admin'}),
    ('benefits','会员券与套餐权益','冻结券包种类、适用范围、有效期及原路退回规则',{'admin','manager','service','reception','customer_service','finance','auditor','sales'},{'admin','manager'}),
    ('recharge-bundle-rules','充值组合套餐','本金、赠品及整份退回条款；仅会员记账，不连接资金接口',{'admin','manager','service','reception','customer_service','finance','auditor','sales'},{'admin'}),
    ('retail-bundle-rules','精品销售套餐','商品、安装作业、售价和退货条款',{'admin','manager','sales','service','finance','auditor'},{'admin','manager'}),
    ('retail-group-rules','精品会员混合支付规则','原单本金、赠金、券与套餐的分摊和记账规则',{'admin','manager','finance','auditor'},{'admin','manager'}),
)

@router.get('/catalog')
def catalog(user=Depends(get_user)):
    aggregate=bool(getattr(user,'_aggregate_scope',False))
    entries=[]
    if not aggregate:
        for route,label,description,read,write in ENTRIES:
            if user.role in read:
                entries.append({'route':route,'label':label,'description':description,'can_write':user.role in write})
        if public_catalog(user)['kinds']:
            entries.append({'route':'masters','label':'经营主数据与引用','description':'供应商、保险公司、物资品牌、库位等基础资料；不增加门店合作审批','can_write':user.role in {'admin','manager','inventory','service'}})
        entries.append({'route':'dictionaries','label':'公共与领域字典','description':'按业务领域分别维护名称和说明','can_write':user.role in {'admin','manager'}})
        if user.role in {'admin','manager'}:
            entries.append({'route':'master/templates','label':'单据模板','description':'公司确认后启用文字模板，不改写已生成原文件','can_write':True})
    deployment=None
    if user.role in {'admin','manager'} and not aggregate:
        # Explicit safe projection. Never dataclasses.asdict(settings), vars(), or os.environ.
        deployment={'timezone':settings.timezone,'session_hours':settings.session_hours,
            'inventory_aging_days':settings.inventory_aging,'repair_overdue_days':settings.repair_overdue,
            'receivable_grace_days':settings.receivable_grace,'low_margin_percent':settings.low_margin,
            'large_cash_yuan':settings.large_cash_yuan,'discount_review_percent':settings.discount_review,
            'daily_report_hour':settings.report_hour,'daily_report_minute':settings.report_minute}
    return {'entries':entries,'password_action':'password','aggregate_scope':aggregate,'deployment':deployment,
        'notice':'业务规则在各自原配置页面发布或复核，旧业务保持原版本。密码只由本人修改。部署级阈值在部署配置中维护；本页不显示密钥、连接串或私有文件路径。',
        'deployment_read_only':True}
