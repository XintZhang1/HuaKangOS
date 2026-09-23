"""Synthetic trial scenarios. Only called by `init --demo` on an empty database.
Random employee passwords are intentionally not printed. Administrator resets
accounts individually before role-based trials. Never import this into real data.
"""
from datetime import timedelta
from decimal import Decimal
import secrets
from sqlalchemy import select,func
from .db import today
from .models import Store,User,UserStore,Vehicle,Sale,CashEntry
from .flow_models import Case,Task,Account,Customer,Item,Member,Reference,DocTemplate
from .flow_engine import new_case,process_action,children
from .flow_documents import ensure_templates,generate_document,upload_file
from .tenancy import set_scope
from .security import hash_password
from .services import audit,plain


def seed_flow_demo(db,admin):
    if db.scalar(select(func.count()).select_from(Case)):
        raise ValueError('流程库不为空，拒绝追加演示记录')
    first=db.get(Store,1);first.name='滨江门店（演示）';first.code='RIVERSIDE'
    second=Store(name='城北门店（演示）',code='NORTH');db.add(second);db.flush()
    day=today();stores=[first,second]
    roles=[('manager','店长'),('sales','销售小林'),('reception','前台小周'),('service','服务顾问小宋'),('technician','技师小陈'),('inventory','库管小赵'),('finance','财务小许'),('customer_service','客服小李')]
    users={}
    # A shared random hash for inaccessible demo initial credentials saves setup time.
    random_hash=hash_password(secrets.token_urlsafe(28))
    for role,name in roles:
        u=User(username='demo_'+role,display_name=name+'（演示）',role=role,password_hash=random_hash,must_change_password=True)
        db.add(u);db.flush();users[role]=u
        db.add_all([UserStore(user_id=u.id,store_id=s.id) for s in stores])
    db.flush()
    serial=0
    def proof(row,category='evidence',source=None):
        nonlocal serial
        serial+=1
        return upload_file(db,admin,row,f'演示凭据-{serial}.txt',f'仅用于流程演示，不是实际签约或到账证据。单号：{row.number}，序号：{serial}'.encode(),category,source).id
    def act(row,key,values=None):
        process_action(db,admin,row,key,values or {},row.version);db.flush();return row
    def new(kind,values):return new_case(db,admin,kind,values)
    for sn,store in enumerate(stores,1):
        set_scope(db,[store.id],store.id)
        ensure_templates(db)
        for t in db.scalars(select(DocTemplate)):
            t.approved=True;t.reviewed_by=admin.id;t.clauses='本模板仅供虚构数据试用，不能用于实际签约。\n'+t.clauses
        bank=Account(name='门店结算账户（演示）',account_type='bank',active=True);db.add(bank);db.flush()
        def receive(row,amount=None,key='receive'):
            nonlocal serial
            amount=row.amount_cents if amount is None else amount
            return act(row,key,{'amount':format(Decimal(amount)/100,'.2f'),'account_id':bank.id,'reference':f'演示到账-{sn}-{row.id}-{serial}', 'evidence_id':proof(row,'receipt')})
        for cat,name in [('供应商','华景配件（演示）'),('保险公司','示例保险机构'),('品牌车型','都市轿车 晨光'),('车间班组','综合维修组'),('作业项目','基础保养'),('仓库库位','新车一区')]:db.add(Reference(category=cat,name=name,active=True))
        cars=[]
        for i in range(12):
            v=Vehicle(doc_no=f'演示入库-{sn}-{i+1:03}',business_date=day-timedelta(days=10+i*8),created_by=admin.id,approval_state='approved',vin=f'LWF{sn:02}{i+1:012}',brand='示例品牌',model='都市轿车 晨光',color='珍珠白',supplier='演示车辆供应商',location=f'新车一区-{i+1:02}',purchase_cost_cents=14500000+(i%3)*50000,list_price_cents=16980000,note='纯虚构演示库存')
            db.add(v);db.flush();audit(db,admin.id,'seed','vehicles',v.id,after=plain(v),reason='虚构流程演示车辆');cars.append(v)
        if sn==2:
            # Legacy historical entries demonstrate safe coexistence and group charts.
            for i,v in enumerate(cars[8:]):
                sold=day-timedelta(days=2+i*4)
                sale=Sale(doc_no=f'演示既有销售-{sn}-{i}',business_date=sold-timedelta(days=2),created_by=admin.id,approval_state='approved',vehicle_id=v.id,active_vehicle_id=v.id,customer_name=f'城北历史客户{i+1}（演示）',salesperson='销售小林（演示）',sale_stage='delivered',delivery_date=sold,contract_amount_cents=15880000,purchase_cost_snapshot_cents=v.purchase_cost_cents)
                db.add(sale);db.flush()
                db.add(CashEntry(doc_no=f'演示历史收款-{sn}-{i}',business_date=sold,created_by=admin.id,approval_state='approved',direction='in',category='sale_collection',amount_cents=sale.contract_amount_cents,account=bank.name,payment_method='bank',voucher_no=f'演示历史凭证-{sn}-{i}',sale_id=sale.id))
        leads=[];orders=[]
        for i in range(12 if sn==1 else 8):
            lead=new('lead',{'customer_name':f'{"滨江" if sn==1 else "城北"}客户{i+1:02}（演示）','customer_phone':f'190{sn:02}{i+1:06}', 'model':'都市轿车 晨光','source':['展厅到店','电话咨询','转介绍','网络咨询'][i%4]})
            leads.append(lead)
            if i==11:continue
            act(lead,'assign',{'assignee_id':users['sales'].id})
            if i in (6,9):
                act(lead,'remind',{'due_date':(day+timedelta(days=2)).isoformat(),'result':'客户正在对比车型，同意后续联系。'})
            elif i in (7,10):act(lead,'close',{'reason':'本次随朋友到访，无购车需求。','no_contact':True})
            else:
                act(lead,'intent',{'need':'家庭日常通勤，关注用车成本与后排空间。','due_date':(day+timedelta(days=1)).isoformat()})
                if i<4:
                    act(lead,'reserve',{'model':'都市轿车 晨光','amount':'158800.00','delivery_due':(day+timedelta(days=5)).isoformat(),'addon':i==1,'insurance':i==1,'agency':i==1})
                    order=next(c for c in children(db,lead) if c.kind=='order');orders.append(order)
                    if i==3:continue
                    act(order,'approve');act(order,'allocate',{'vehicle_id':cars[i].id})
                    contract=generate_document(db,admin,order,'contract')
                    act(order,'sign',{'evidence_id':proof(order,'signed_contract',contract.id)})
                    receive(order,order.amount_cents if i!=1 else 3000000)
                    if i==1:
                        for c in children(db,order):
                            if c.kind=='addon':act(c,'service_quote',{'amount':'2800.00','work':'行车记录仪与脚垫安装'})
                            elif c.kind=='insurance':act(c,'service_quote',{'amount':'5600.00','insurer':'示例保险机构','commission':'420.00'})
                        continue
                    act(order,'inspect',{'evidence_id':proof(order,'inspection'),'outcome':'合格','result':'车辆外观、功能与随车物品检查通过。'})
                    if i==2:continue
                    act(order,'dispatch',{'evidence_id':proof(order)})
                    handover=generate_document(db,admin,order,'handover')
                    act(order,'deliver',{'evidence_id':proof(order,'signed_handover',handover.id)})
        itemlist=[]
        for i,(name,unit,qty,cost,reorder) in enumerate([('发动机机油','升','80','48.50',12),('机油滤芯','件','24','28.00',5),('空气滤芯','件','4','46.00',5),('雨刮器','对','10','68.00',3)]):
            item=Item(sku=f'WZ-{sn}-{i+1:03}',name=name,unit=unit,reorder_milli=reorder*1000,active=True);db.add(item);db.flush();itemlist.append(item)
            purchase=new('purchase',{'item_id':item.id,'quantity':qty,'unit_cost':cost,'supplier':'华景配件（演示）'})
            act(purchase,'approve');act(purchase,'stock_in',{'evidence_id':proof(purchase)})
        for i in range(6 if sn==1 else 3):
            r=new('repair',{'customer_name':f'{"滨江" if sn==1 else "城北"}售后客户{i+1}（演示）','customer_phone':f'190{sn:02}8{i+1:05}','plate':f'沪示例{i+1:03}','repair_type':['保养','一般维修','保险理赔'][i%3],'problem':['常规保养并检查制动','车辆行驶异响','车身轻微剐蹭修复'][i%3],'due_date':(day+timedelta(days=1)).isoformat()})
            if i==5:continue
            act(r,'quote',{'labor':'300.00','parts':'238.00','discount':'38.00','labor_cost':'120.00','payer':'保险公司' if i==2 else '客户','work':'基础检查、更换机油与滤芯。'})
            if i==4:continue
            act(r,'authorize',{'evidence_id':proof(r,'authorization')});act(r,'start')
            act(r,'material',{'item_id':itemlist[0].id,'quantity':'4'})
            issue=next(c for c in children(db,r) if c.kind=='material_issue')
            if i==3:continue
            act(issue,'issue',{'evidence_id':proof(issue)})
            if i==1:continue
            act(r,'finish',{'result':'完成规定项目，自检无异常。'});act(r,'quality',{'evidence_id':proof(r,'inspection')})
            if i==2:act(r,'credit',{'due_date':(day+timedelta(days=14)).isoformat(),'reason':'示例保险结算协议，待保险公司付款。'})
            else:receive(r)
            act(r,'release',{'evidence_id':proof(r)})
        for i in range(3):
            customer=new('callback',{'customer_name':f'{"滨江" if sn==1 else "城北"}会员{i+1}（演示）','customer_phone':f'190{sn:02}9{i+1:05}','topic':'会员服务咨询','due_date':day.isoformat()})
            member=Member(customer_id=customer.customer_id,number=f'演示会员-{sn}-{i+1:03}',active=True);db.add(member);db.flush()
            topup=new('member_topup',{'member_id':member.id,'amount':str((i+1)*1000)})
            act(topup,'topup_receive',{'account_id':bank.id,'reference':f'演示充值-{sn}-{i}','evidence_id':proof(topup,'receipt')})
            if i==1:
                refund=new('member_refund',{'member_id':member.id,'amount':'300','reason':'演示：客户申请退回部分未消费储值。'})
                act(refund,'approve')
        complaint=new('complaint',{'customer_name':'服务意见客户（演示）','customer_phone':f'190{sn:02}999999','problem':'接车等待时间较长，希望改进预约安排。'})
        act(complaint,'plan',{'plan':'客服联系客户说明情况，服务顾问调整预约时段。','due_date':(day+timedelta(days=2)).isoformat()})
        # Demonstration of current workload, not backdated employee performance.
        open_tasks=list(db.scalars(select(Task).where(Task.status=='open').order_by(Task.id)))
        for i,t in enumerate(open_tasks[:4]):t.due_date=day-timedelta(days=1+i%2)
        audit(db,admin.id,'seed','flow',None,reason='建立虚构流程试用场景')
        db.commit()
    set_scope(db,[1],1)
