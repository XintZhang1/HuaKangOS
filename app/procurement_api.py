"""Typed purchase commands; state, posted value and cash links are server-owned."""
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from sqlalchemy import select,func,or_
import csv,io
from .db import get_db,get_write_db
from .security import get_user
from .flow_models import Case
from . import procurement_service as service

router=APIRouter(prefix='/api/procurement',tags=['采购与供应商结算'])


class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Quantity(Strict):quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
class Line(Quantity):
    item_id:int=Field(gt=0,strict=True)
    unit_cost_cents:int=Field(ge=0,le=1_000_000_000,strict=True)
class Create(Request):
    supplier_id:int=Field(gt=0,strict=True)
    reason:str=Field(min_length=2,max_length=500)
    lines:list[Line]=Field(min_length=1,max_length=100)
class Command(Request):
    version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
class Reason(Strict):reason:str=Field(min_length=2,max_length=500)
class Evidence(Strict):evidence_id:int=Field(gt=0,strict=True)
class ReceiveLine(Quantity):line_id:int=Field(gt=0,strict=True)
class Receive(Evidence):lines:list[ReceiveLine]=Field(min_length=1,max_length=100)
class ReturnLine(Quantity):receipt_id:int=Field(gt=0,strict=True)
class ReturnRequest(Reason,Evidence):lines:list[ReturnLine]=Field(min_length=1,max_length=100)
class ReturnRef(Strict):
    return_id:int=Field(gt=0,strict=True)
    return_version:int=Field(gt=0,strict=True)
class ReturnReview(ReturnRef,Reason):pass
class ReturnDispatch(ReturnRef,Evidence):pass
class Pay(Evidence):
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=1,max_length=100)
class Refund(Pay):original_payment_id:int=Field(gt=0,strict=True)
SCHEMAS={'approve':Strict,'reject':Reason,'cancel':Reason,'close_receiving':Reason,'receive':Receive,'pay':Pay,
    'return_request':ReturnRequest,'return_approve':ReturnReview,'return_cancel':ReturnReview,'return_dispatch':ReturnDispatch,'refund':Refund}
from .procurement_prepayment_api import SCHEMAS as PREPAYMENT_SCHEMAS
SCHEMAS.update(PREPAYMENT_SCHEMAS)


@router.get('/orders')
def list_orders(page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),q:str=Query('',max_length=100),db=Depends(get_db),user=Depends(get_user)):
    if user.role not in service.READ_ROLES:raise HTTPException(403,'当前岗位不能查看采购')
    query=select(Case).where(Case.kind=='procurement')
    if q:query=query.where(or_(Case.number.contains(q,autoescape=True),Case.title.contains(q,autoescape=True)))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=list(db.scalars(query.order_by(Case.id.desc()).offset((page-1)*page_size).limit(page_size)))
    return {'items':[service.describe(db,user,row) for row in rows],'total':total,'page':page,'page_size':page_size}


@router.post('/orders',status_code=201)
def create(body:Create,db=Depends(get_write_db),user=Depends(get_user)):
    return service.create(db,user,body.request_id,body.model_dump(exclude={'request_id'}))


@router.get('/orders/{case_id}')
def detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):
    row,_=service.get_order(db,user,case_id);return service.describe(db,user,row)


@router.post('/orders/{case_id}/actions/{action}')
def command(case_id:int,action:str,body:Command,db=Depends(get_write_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'采购动作不存在')
    if action=='prepay_pay' and body.values.get('confirmed') is not True:
        raise HTTPException(422,'请本人明确勾选已核对实际付款及原始凭据；批准申请不代表已经付款')
    try:values=schema.model_validate(body.values).model_dump()
    except ValidationError:raise HTTPException(422,'请核对采购办理字段；金额为整数分、数量为整数千分位，不能提交状态或过账金额')
    return service.command(db,user,case_id,body.request_id,body.version,action,values)


def _payables(db,user):
    if user.role not in service.MONEY_ROLES:raise HTTPException(403,'供应商结算与金额明细限管理、财务和审计岗位')
    rows=list(db.scalars(select(Case).where(Case.kind=='procurement').order_by(Case.id).limit(10001)))
    if len(rows)>10000:raise HTTPException(422,'采购对账超过本版一万单上限，请先按部署规模升级分期对账；未返回截断合计')
    return [service.describe(db,user,row) for row in rows]


@router.get('/payables')
def payables(db=Depends(get_db),user=Depends(get_user)):
    rows=_payables(db,user)
    return {'items':rows,'payable_cents':sum(r['totals']['payable_cents'] for r in rows),
        'supplier_refund_due_cents':sum(r['totals']['supplier_refund_due_cents'] for r in rows),
        'prepaid_cents':sum(r['totals'].get('prepaid_cents',0) for r in rows),
        'definition':'当前应付来自实际验收到货净额扣除净已付。已启用预付款的原单，将有效采购余量对应预付与终止余量/实退后的供应商应退分开；申请、批准和到货抵用不另记现金。'}


@router.get('/payables/export')
def export(db=Depends(get_db),user=Depends(get_user)):
    rows=_payables(db,user);buffer=io.StringIO();writer=csv.writer(buffer)
    writer.writerow(['huakangos采购单号','门店ID','供应商','已验收（分）','已退货（分）','已付净额（分）','当前应付（分）','供应商应退（分）','有效预付（分）','未付申请占额（分）','到货原款抵用（分）'])
    for row in rows:
        supplier=row['supplier_name']
        if supplier.startswith(('=','+','-','@')):supplier="'"+supplier
        writer.writerow([row['number'],row['store_id'],supplier,*[row['totals'].get(k,0) for k in ['received_cents','returned_cents','paid_net_cents','payable_cents','supplier_refund_due_cents','prepaid_cents','prepayment_reserved_cents','applied_cents']]])
    return Response(buffer.getvalue().encode('utf-8-sig'),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="huakangos-supplier-payables.csv"','Cache-Control':'no-store'})
