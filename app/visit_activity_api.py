"""Read-only same-population visit reports and CSV exports."""
import csv,io
from datetime import date
from urllib.parse import quote
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from .db import get_db,get_audited_read_db
from .security import get_user
from .services import audit
from .visit_activity_analytics import build_visit_activity

router=APIRouter(prefix='/api/visit-activity-reports',tags=['售前跟进与维修进出厂统计'])

@router.get('')
def report(date_from:date|None=None,date_to:date|None=None,case_id:int|None=Query(None,gt=0),db=Depends(get_db),user=Depends(get_user)):
    return build_visit_activity(db,user,date_from,date_to,case_id)

@router.get('/export/{key}')
def export(key:str,date_from:date|None=None,date_to:date|None=None,case_id:int|None=Query(None,gt=0),db=Depends(get_audited_read_db),user=Depends(get_user)):
    data=build_visit_activity(db,user,date_from,date_to,case_id)
    if key not in data['tables']:raise HTTPException(404,'此统计没有该原始明细表')
    t=data['tables'][key];buf=io.StringIO(newline='');writer=csv.writer(buf)
    def safe(v):
        text=str(v);numeric=text.replace('-','',1).replace('.','',1).isdigit()
        return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r','\n')) and not numeric else text
    writer.writerow(t['headers'])
    for row in t['rows']:writer.writerow([safe(v) for v in row['values']])
    audit(db,user.id,'export','visit_activity_report',None,reason=data['date_from']+'至'+data['date_to']+' '+key);db.commit()
    return Response(('\ufeff'+buf.getvalue()).encode(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote('huakangos_'+t['title']+'.csv')})
