"""Clearly labelled synthetic demo data, never loaded automatically."""
from datetime import timedelta
from sqlalchemy import select, func
from .db import today
from .models import User, Vehicle, Sale, Repair, Policy, CashEntry, MODULES, AppMetadata
from .services import plain, audit
from .config import ROOT


def seed_demo(db, admin: User):
    if any(db.scalar(select(func.count()).select_from(model)) for model in MODULES.values()):
        raise ValueError('拒绝混入演示数据：业务库不是空库。请使用独立 DATABASE_URL。')
    day = today()
    base = {'created_by':admin.id,'approval_state':'approved','note':'纯虚构演示数据，请勿作为真实业务数据使用。'}
    def insert(module,obj):
        db.add(obj); db.flush(); audit(db,admin.id,'seed',module,obj.id,after=plain(obj),reason='初始化虚构演示数据')
        return obj
    cars = []
    for i in range(48):
        cost = [148000,205000,238000,179000][i%4]*100
        cars.append(insert('vehicles',Vehicle(**base,doc_no=f'DEMO-V-{i+1:03}',business_date=day-timedelta(days=50+i*3),
            vin=f'LDD{i+1:014}',brand=f'演示品牌 {"AB"[i%2]}',model=['城市轿车 530','都市 SUV X7','纯电 E6','混动 H5'][i%4],
            color=['珍珠白','曜石黑','冰川银'][i%3],supplier='演示供应商',location=f'{"AB"[i%2]} 区 {i%12+1:02} 号位',
            purchase_cost_cents=cost,list_price_cents=cost+2500000)))
    sale_rows = []
    for i,v in enumerate(cars[:34]):
        delivered = i<28
        delivery = day-timedelta(days=i) if delivered else None
        business_day = delivery-timedelta(days=2) if delivered else day-timedelta(days=i-28)
        contract = v.purchase_cost_cents+([13500,17800,12000,19000][i%4]*100)
        if i==0: contract = v.purchase_cost_cents-1200000
        s = insert('sales',Sale(**base,doc_no=f'DEMO-S-{i+1:03}',business_date=business_day,vehicle_id=v.id,active_vehicle_id=v.id,
            customer_name=f'演示客户 {i+1:03}',customer_phone='',salesperson=['小林（演示）','小陈（演示）','小周（演示）'][i%3],
            sale_stage='delivered' if delivered else 'ordered',delivery_date=delivery,contract_amount_cents=contract,
            purchase_cost_snapshot_cents=v.purchase_cost_cents))
        sale_rows.append(s)
        paid = contract if delivered else 1000000
        if i==7: paid=contract//2
        if i==3: paid=contract+1000000
        insert('cash',CashEntry(**base,doc_no=f'DEMO-C-S-{i+1:03}',business_date=delivery or business_day,
            direction='in',category='sale_collection',amount_cents=paid,account='门店收款账户（演示）',
            counter_account='',counterparty=f'演示客户 {i+1:03}',payment_method='bank',voucher_no=f'DEMO-BANK-S-{i+1:03}',sale_id=s.id))
    policy_rows = []
    for i in range(18):
        issued = day-timedelta(days=i)
        premium = [4800,5600,6800][i%3]*100
        commission = premium//10 if i!=1 else premium//2
        p = insert('policies',Policy(**base,doc_no=f'DEMO-P-{i+1:03}',business_date=issued,policy_number=f'DEMO-POLICY-{i+1:04}',
            insurer='演示保险机构',plate_number=f'沪DEMO{i+1:03}',customer_name=f'演示续保客户 {i+1:03}',customer_phone='',
            policy_type='commercial',start_date=issued,end_date=issued+timedelta(days=364),premium_cents=premium,commission_cents=commission))
        policy_rows.append(p)
        insert('cash',CashEntry(**base,doc_no=f'DEMO-C-P-{i+1:03}',business_date=issued,direction='in',category='premium_collection',
            amount_cents=premium,account='门店收款账户（演示）',counter_account='',counterparty=f'演示续保客户 {i+1:03}',
            payment_method='wechat',voucher_no=f'DEMO-WX-P-{i+1:03}',policy_id=p.id))
    for i in range(28):
        completed = i<23
        completion = day-timedelta(days=i%20) if completed else None
        business_day = completion-timedelta(days=2) if completed else day-timedelta(days=10+i-23)
        labor = [400,800,1200,2400][i%4]*100
        parts = [200,1600,3800,10000][i%4]*100
        discount = 0 if i!=2 else (labor+parts)//2
        r = insert('repairs',Repair(**base,doc_no=f'DEMO-R-{i+1:03}',business_date=business_day,
            plate_number=f'沪DEMO{i+1:03}',customer_name=f'演示售后客户 {i+1:03}',customer_phone='',
            service_advisor=['小宋（演示）','小赵（演示）'][i%2],repair_type='insurance' if i%6==0 else 'maintenance',
            repair_stage='completed' if completed else 'open',policy_id=None if i%6==0 else None,
            due_date=business_day+timedelta(days=3),completion_date=completion,labor_amount_cents=labor,
            parts_amount_cents=parts,discount_cents=discount,cost_amount_cents=(labor+parts)*65//100))
        if completed and i!=5:
            insert('cash',CashEntry(**base,doc_no=f'DEMO-C-R-{i+1:03}',business_date=completion,direction='in',category='repair_collection',
                amount_cents=labor+parts-discount,account='门店收款账户（演示）',counter_account='',counterparty=f'演示售后客户 {i+1:03}',
                payment_method='alipay',voucher_no=f'DEMO-ALI-R-{i+1:03}',repair_id=r.id))
    for i in range(16):
        insert('cash',CashEntry(**base,doc_no=f'DEMO-C-E-{i+1:03}',business_date=day-timedelta(days=i//2),direction='out',
            category='operating_expense',amount_cents=8000000 if i<2 else (800+i*71)*100,
            account='门店经营账户（演示）',counter_account='',counterparty='演示租赁公司' if i<2 else '演示服务供应商',
            payment_method='cash' if i<2 else 'bank',voucher_no='DEMO-DUPLICATE-001' if i<2 else f'DEMO-EXP-{i+1:03}'))
    insert('cash',CashEntry(**base,doc_no='DEMO-C-TRANSFER',business_date=day,direction='out',category='transfer',amount_cents=10000000,
        account='门店收款账户（演示）',counter_account='门店经营账户（演示）',counterparty='',payment_method='bank',voucher_no='DEMO-TRANSFER-001'))
    pending = dict(base); pending['approval_state']='submitted'
    insert('cash',CashEntry(**pending,doc_no='DEMO-C-PENDING',business_date=day-timedelta(days=2),direction='out',category='operating_expense',
        amount_cents=120000,account='门店经营账户（演示）',counter_account='',counterparty='演示供应商',payment_method='bank',voucher_no='DEMO-PENDING-001'))
    db.add(AppMetadata(key='demo',value={'enabled':True}))
    db.commit()
