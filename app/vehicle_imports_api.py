"""Atomic CSV source registration, row review and native purchase actions."""
import csv,io
from typing import Literal,Annotated
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File,Form,Response
from pydantic import Field,ValidationError
from sqlalchemy import select
from .db import get_db,get_write_db,today
from .security import get_user
from .master_data import Strict
from . import vehicle_imports_service as service
from .vehicle_imports_csv import HEADERS,MAX_BYTES
from .vehicle_imports_models import VehicleImportBatch as Batch,VehicleImportRow as Row

router=APIRouter(prefix='/api/vehicle-imports',tags=['车辆请款与批量交接导入'])

class Action(Strict):
    request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    version:int=Field(strict=True,gt=0)
    source_case_version:int=Field(strict=True,gt=0)
    values:dict=Field(default_factory=dict)

class Reason(Strict):
    reason:str=Field(min_length=3,max_length=500)

class Confirm(Reason):
    confirmed:Literal[True]

class Reassign(Reason):
    task_id:int=Field(strict=True,gt=0)
    assignee_id:int=Field(strict=True,gt=0)


@router.get('/catalog',summary='读取整车导入目录及按kind固定的CSV列、单位和字段含义（csv_headers/csv_field_notes）；列格式不按采购单变化，具体行引用另与原采购单核对')
def catalog(user=Depends(get_user),db=Depends(get_db)):
    allowed=not getattr(user,'_aggregate_scope',False) and user.role in service.READ
    return {'can_read':allowed,'prepare_kinds':[k for k,r in service.PREP.items() if allowed and user.role in r],'kinds':service.LABELS if allowed else {},
        'prepare_role_permissions':{kind:{'role_can_prepare':user.role in roles,'preparer_roles':sorted(roles)}
            for kind,roles in service.PREP.items()} if allowed else {},
        'permission_notice':'能读取CSV格式不表示本人能编制该类清单。各类role_can_prepare只核当前岗位；不允许时须由该类原岗位办理，不能指导当前员工本人确认。允许也仍须核原采购、版本和任务；试执行及正式确认均由同批原编制人按原守卫办理，另须主管独立复核。' if allowed else '',
        'csv_headers':{kind:list(fields) for kind,fields in HEADERS.items()} if allowed else {},
        'csv_field_notes':{
            'source_row':'来源文件中的行编号，不是采购明细行ID。',
            'line_id':'本张原采购单的采购明细行ID。',
            'manifest_row_id':'本张原采购单已确认请款清单的行ID，须从原manifest读取，不是采购明细行ID。',
            'location_id':'本店实际整车仓或混合仓的库位ID，须读取并核对真实库位。',
            'amount_cents':'请款金额，须为正整数，单位为分，不是元。',
            'shipped_date':'实际发运日期，须为 YYYY-MM-DD。',
            'expected_date':'预计到货日期，须为 YYYY-MM-DD。',
            'received_date':'实际验收日期，须为 YYYY-MM-DD。'} if allowed else {}}


@router.get('/orders/{case_id}/batches')
def batches(case_id:int,user=Depends(get_user),db=Depends(get_db)):
    with service.access(db,user):
        case,_=service.purchase.get_order(db,user,case_id)
        query=select(Batch).where(Batch.case_id==case.id).order_by(Batch.id.desc())
        if user.role not in service.purchase.MONEY:query=query.where(Batch.kind!='funds')
        return {'items':[service.describe(db,user,b,case) for b in db.scalars(query.limit(100))]}


@router.get('/orders/{case_id}/manifest')
def manifest(case_id:int,user=Depends(get_user),db=Depends(get_db)):
    with service.access(db,user):
        case,_=service.purchase.get_order(db,user,case_id)
        # Explicit declassification: only identifiers/VIN needed for the stock job, no source file, prices, fund amounts or notes.
        return {'items':[{'id':r.id,'batch_id':r.batch_id,'line_id':r.line_id,'vin':r.vin,'source_row':r.source_row} for r in db.scalars(select(Row).join(Batch,Batch.id==Row.batch_id).where(Batch.case_id==case.id,Batch.kind=='funds',Batch.status=='confirmed').order_by(Row.id))]}


@router.get('/orders/{case_id}/example/{kind}')
def example(case_id:int,kind:Literal['funds','ship','receive'],user=Depends(get_user),db=Depends(get_db)):
    with service.access(db,user,service.PREP[kind]):
        case,_=service.purchase.get_order(db,user,case_id);line=service.purchase.rows(db,service.purchase.Line,case_id=case.id)[0]
        text=io.StringIO(newline='');writer=csv.writer(text);writer.writerow(HEADERS[kind])
        if kind=='funds':writer.writerow(['ROW-001',line.id,'LTEST000000000201',100])
        else:
            candidates=manifest(case_id,user,db)['items'];r=candidates[0] if candidates else {'id':1,'vin':'LTEST000000000201'}
            writer.writerow(['ROW-001',r['id'],r['vin'],today().isoformat(),today().isoformat() if kind=='ship' else 1])
        return Response(('\ufeff'+text.getvalue()).encode('utf-8'),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="huakangos-{kind}-example.csv"'})


@router.post('/orders/{case_id}/batches',status_code=201)
async def prepare(case_id:int,file:Annotated[UploadFile,File()],kind:Annotated[Literal['funds','ship','receive'],Form()],
    request_id:Annotated[str,Form(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')],version:Annotated[int,Form(gt=0)],
    source_reference:Annotated[str,Form(min_length=1,max_length=100)],replacement_batch_id:Annotated[int|None,Form(gt=0)]=None,
    db=Depends(get_write_db),user=Depends(get_user)):
    content=await file.read(MAX_BYTES+1)
    if not source_reference.strip() or source_reference!=source_reference.strip():raise HTTPException(422,'来源清单编号不能为空或带首尾空格')
    return service.prepare(db,user,case_id,request_id,version,kind,source_reference,file.filename or '',content,replacement_batch_id)


@router.get('/batches/{batch_id}')
def detail(batch_id:int,user=Depends(get_user),db=Depends(get_db)):
    with service.access(db,user):return service.describe(db,user,*service.load(db,user,batch_id))


@router.post('/batches/{batch_id}/actions/{action}')
def command(batch_id:int,action:Literal['trial','review','confirm','cancel','reassign'],body:Action,db=Depends(get_write_db),user=Depends(get_user)):
    try:values=({'confirm':Confirm,'reassign':Reassign}.get(action,Reason)).model_validate(body.values).model_dump()
    except ValidationError as exc:raise HTTPException(422,'请按本动作填写本人核对说明和必要确认，不能附带其它状态或金额') from exc
    return service.command(db,user,body.request_id,batch_id,body.version,body.source_case_version,action,values)
