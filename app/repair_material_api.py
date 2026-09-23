"""Scoped read-only repair material reports and exact-table exports."""
import csv,io
from datetime import date
from urllib.parse import quote
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from .db import get_db
from .security import get_user
from .services import audit
from .repair_material_analytics import build_repair_materials

router=APIRouter(prefix='/api/repair-material-reports',tags=['实际维修领退料分析'])


@router.get('')
def report(date_from:date|None=None,date_to:date|None=None,case_id:int|None=Query(None,gt=0),item_id:int|None=Query(None,gt=0),
           model_name:str|None=Query(None,min_length=1,max_length=120),work_item_id:int|None=Query(None,gt=0),db=Depends(get_db),user=Depends(get_user)):
    return build_repair_materials(db,user,date_from,date_to,case_id,item_id,model_name,work_item_id)


@router.get('/export/{key}')
def export(key:str,date_from:date|None=None,date_to:date|None=None,case_id:int|None=Query(None,gt=0),item_id:int|None=Query(None,gt=0),
           model_name:str|None=Query(None,min_length=1,max_length=120),work_item_id:int|None=Query(None,gt=0),db=Depends(get_db),user=Depends(get_user)):
    result=build_repair_materials(db,user,date_from,date_to,case_id,item_id,model_name,work_item_id)
    if key not in result['tables']:raise HTTPException(404,'此维修领料报表没有该明细')
    data=result['tables'][key];buf=io.StringIO(newline='');writer=csv.writer(buf)
    def safe(v):
        text=str(v);numeric=text.replace('-','',1).replace('.','',1).isdigit()
        return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r','\n')) and not numeric else text
    writer.writerow(data['headers'])
    for row in data['rows']:writer.writerow([safe(v) for v in row['values']])
    audit(db,user.id,'export','repair_material_report',None,reason=result['date_from']+'至'+result['date_to']+' '+key);db.commit()
    return Response(('\ufeff'+buf.getvalue()).encode(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote('huakangos_'+data['title']+'.csv')})
