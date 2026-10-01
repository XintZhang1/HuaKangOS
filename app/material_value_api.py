"""One scoped dataset serves finance tables, charts and CSV."""
import csv
import io
from datetime import date
from urllib.parse import quote
from fastapi import APIRouter, Depends, Query, HTTPException, Response
from .db import get_db, get_audited_read_db
from .security import get_user
from .services import audit
from .material_value_analytics import build_material_values

router = APIRouter(prefix='/api/material-value', tags=['物资收入成本对照'])


@router.get('')
def report(date_from:date|None=None, date_to:date|None=None, source:str|None=None,
           item_id:int|None=Query(None,gt=0), case_id:int|None=Query(None,gt=0),
           db=Depends(get_db), user=Depends(get_user)):
    return build_material_values(db,user,date_from,date_to,source,item_id,case_id)


@router.get('/export/{key}')
def export(key:str, date_from:date|None=None, date_to:date|None=None, source:str|None=None,
           item_id:int|None=Query(None,gt=0), case_id:int|None=Query(None,gt=0),
           db=Depends(get_audited_read_db), user=Depends(get_user)):
    result=build_material_values(db,user,date_from,date_to,source,item_id,case_id)
    if key not in result['tables']:raise HTTPException(404,'没有此物资收入成本明细')
    t=result['tables'][key];buf=io.StringIO(newline='');writer=csv.writer(buf)
    def safe(value):
        text=str(value);numeric=text.replace('-','',1).replace('.','',1).isdigit()
        return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r','\n')) and not numeric else text
    writer.writerow(t['headers'])
    for row in t['rows']:writer.writerow([safe(v) for v in row['values']])
    audit(db,user.id,'export','material_value_report',None,reason=result['date_from']+'至'+result['date_to']+' '+key);db.commit()
    return Response(('\ufeff'+buf.getvalue()).encode(),media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote('huakangos_'+t['title']+'.csv')})
