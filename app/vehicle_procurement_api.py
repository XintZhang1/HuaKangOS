"""Typed, store-scoped vehicle procurement commands and original-ledger reconciliation."""
from datetime import date
import csv,io
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from pydantic import BaseModel,ConfigDict,Field,ValidationError,field_validator
from sqlalchemy import select,func,or_
from .db import get_db,get_write_db
from .security import get_user
from .flow_models import Case
from . import vehicle_procurement_service as svc

router=APIRouter(prefix='/api/vehicle-procurement',tags=['整车采购与付款'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Line(Strict):
    model_id:int=Field(gt=0,strict=True)
    color:str=Field(min_length=1,max_length=40)
    quantity:int=Field(gt=0,le=1000,strict=True)
class Create(Request):
    supplier_id:int=Field(gt=0,strict=True)
    contracting_party:str=Field(min_length=2,max_length=180)
    reason:str=Field(min_length=2,max_length=500)
    due_date:date
    lines:list[Line]=Field(min_length=1,max_length=100)
class Command(Request):
    version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
class Reason(Strict):reason:str=Field(min_length=2,max_length=500)
class Evidence(Strict):evidence_id:int=Field(gt=0,strict=True)
class Price(Strict):
    line_id:int=Field(gt=0,strict=True)
    unit_cost_cents:int=Field(gt=0,le=1_000_000_000,strict=True)
    list_price_cents:int=Field(ge=0,le=1_000_000_000,strict=True)
class Approve(Evidence):prices:list[Price]=Field(min_length=1,max_length=100)
class ReasonEvidence(Reason,Evidence):pass
class Amount(Strict):amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
class FundsRequest(ReasonEvidence,Amount):pass
class FundsCancel(Reason):
    funds_request_id:int=Field(gt=0,strict=True)
    funds_version:int=Field(gt=0,strict=True)
class Pay(Amount,Evidence):
    funds_request_id:int=Field(gt=0,strict=True)
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=1,max_length=100)
class Refund(Amount,Evidence):
    original_payment_id:int=Field(gt=0,strict=True)
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=1,max_length=100)
class VIN(Strict):
    vin:str=Field(pattern=r'^[A-HJ-NPR-Z0-9]{17}$')
    @field_validator('vin',mode='before')
    @classmethod
    def uppercase(cls,v):return v.upper() if isinstance(v,str) else v
class Ship(VIN,Evidence):
    line_id:int=Field(gt=0,strict=True)
    shipped_date:date
    expected_date:date
class Receive(VIN,Evidence):
    shipment_id:int=Field(gt=0,strict=True)
    location_id:int=Field(gt=0,strict=True)
class ReturnRequest(ReasonEvidence):shipment_id:int=Field(gt=0,strict=True)
class ReturnRef(Strict):
    return_id:int=Field(gt=0,strict=True)
    return_version:int=Field(gt=0,strict=True)
class ReturnReview(ReturnRef,Reason):pass
class ReturnDispatch(ReturnRef,ReasonEvidence):pass
SCHEMAS={'approve':Approve,'reject':Reason,'cancel_remaining':ReasonEvidence,'request_funds':FundsRequest,'cancel_funds':FundsCancel,
    'pay':Pay,'refund':Refund,'ship':Ship,'receive':Receive,'return_request':ReturnRequest,'return_approve':ReturnReview,'return_cancel':ReturnReview,'return_dispatch':ReturnDispatch}

@router.get('/catalog')
def catalog(db=Depends(get_db),user=Depends(get_user)):
    allowed=user.role in svc.READ and not getattr(user,'_aggregate_scope',False)
    party=None
    if allowed:
        from . import business_entity_service as entities
        from .business_entity_models import EntityPolicy
        with entities.authority(db,user):
            binding=entities.current_store_binding(db)
            if binding and db.scalar(select(EntityPolicy.id)):party=entities.legal_info(db,binding.revision_id)['legal_name']
    return {'operating_party':party,'can_read':allowed,'can_create':allowed and user.role in {'admin','manager','inventory'},'can_money':allowed and user.role in svc.MONEY,
        'actions':svc.LABELS if allowed else {}}

@router.get('/orders')
def listing(page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),q:str=Query('',max_length=80),db=Depends(get_db),user=Depends(get_user)):
    with svc.authority(db,user,svc.READ):
        query=select(Case).where(Case.kind=='vehicle_procurement')
        if q:query=query.where(or_(Case.number.contains(q,autoescape=True),Case.title.contains(q,autoescape=True)))
        total=db.scalar(select(func.count()).select_from(query.subquery()))
        rows=db.scalars(query.order_by(Case.id.desc()).offset((page-1)*page_size).limit(page_size))
        return {'items':[svc.describe(db,user,row) for row in rows],'total':total,'page':page,'page_size':page_size}
@router.post('/orders',status_code=201)
def create(body:Create,db=Depends(get_write_db),user=Depends(get_user)):
    return svc.create(db,user,body.request_id,body.model_dump(exclude={'request_id'}))
@router.get('/orders/{case_id}')
def detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):
    with svc.authority(db,user,svc.READ):return svc.describe(db,user,svc.get_order(db,user,case_id)[0])
@router.post('/orders/{case_id}/actions/{action}')
def command(case_id:int,action:str,body:Command,db=Depends(get_write_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'整车采购动作不存在')
    try:values=schema.model_validate(body.values).model_dump()
    except ValidationError:raise HTTPException(422,'请核对整车采购办理字段；VIN须17位，金额为整数分，数量为整数，不可提交状态或库存价值')
    return svc.command(db,user,case_id,body.request_id,body.version,action,values)

def reconciliation_rows(db,user):
    if user.role not in svc.MONEY:raise HTTPException(403,'整车采购资金对账限主管、财务和审计岗位')
    rows=list(db.scalars(select(Case).where(Case.kind=='vehicle_procurement').order_by(Case.id).limit(10001)))
    if len(rows)>10000:raise HTTPException(413,'整车对账超过本版一万单上限，未返回截断合计')
    return [svc.describe(db,user,r) for r in rows]
TOTAL_KEYS=['commitment_cents','received_cents','returned_cents','paid_net_cents','payable_cents','prepaid_cents','supplier_refund_due_cents']
@router.get('/reconciliation')
def reconciliation(db=Depends(get_db),user=Depends(get_user)):
    with svc.authority(db,user,svc.MONEY):
        rows=reconciliation_rows(db,user)
        return {'items':rows,'totals':{k:sum(r['totals'][k] for r in rows) for k in TOTAL_KEYS},
            'definition':'有效约定扣除未发运取消和实际退车；应付仅来自实物验收。已付超过已验收部分在有效约定内列预付，超过有效约定列供应商应退；均逐单计算后汇总。'}
@router.get('/reconciliation/export')
def export(db=Depends(get_db),user=Depends(get_user)):
    with svc.authority(db,user,svc.MONEY):
        rows=reconciliation_rows(db,user);buffer=io.StringIO();writer=csv.writer(buffer)
        writer.writerow(['huakangos整车采购单号','门店','供应商','有效约定分','实际验收分','实际退车分','已付净额分','当前应付分','采购预付分','供应商应退分'])
        for row in rows:
            name=row['supplier_name'];name="'"+name if name.startswith(('=','+','-','@')) else name
            writer.writerow([row['number'],row['store_id'],name,*[row['totals'][k] for k in TOTAL_KEYS]])
        return Response(buffer.getvalue().encode('utf-8-sig'),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="huakangos-vehicle-purchases.csv"','Cache-Control':'no-store'})
