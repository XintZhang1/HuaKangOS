import csv
import io
from datetime import date
from urllib.parse import quote
from fastapi import APIRouter,Depends,Query,Response
from .db import get_db, get_audited_read_db
from .security import get_user
from .services import audit
from .stock_reports import build_stock_period

router=APIRouter(prefix='/api/stock-reports',tags=['期间物资入出存'])


@router.get('/period')
def period(date_from:date|None=None,date_to:date|None=None,item_id:int|None=Query(None,gt=0),db=Depends(get_db),user=Depends(get_user)):
    return build_stock_period(db,user,date_from,date_to,item_id)


@router.get('/period/export')
def export(date_from:date|None=None,date_to:date|None=None,item_id:int|None=Query(None,gt=0),db=Depends(get_audited_read_db),user=Depends(get_user)):
    report=build_stock_period(db,user,date_from,date_to,item_id)
    buf=io.StringIO(newline='');writer=csv.writer(buf);writer.writerow(report['table']['headers'])
    def safe(value):
        text=str(value)
        return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r','\n')) and not text.replace('-','',1).replace('.','',1).isdigit() else text
    for row in report['table']['rows']:writer.writerow([safe(v) for v in row['values']])
    audit(db,user.id,'export','stock_period',None,reason=report['date_from']+'至'+report['date_to']);db.commit()
    name='huakangos_物资入出存_'+report['date_from']+'_'+report['date_to']+'.csv'
    return Response(('\ufeff'+buf.getvalue()).encode(),media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(name)})
