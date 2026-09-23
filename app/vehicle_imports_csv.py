"""Bounded, deterministic CSV parser. No spreadsheet execution or header guessing."""
import csv,io,re
from datetime import date
from fastapi import HTTPException

MAX_BYTES=128*1024
HEADERS={'funds':['source_row','line_id','vin','amount_cents'],
         'ship':['source_row','manifest_row_id','vin','shipped_date','expected_date'],
         'receive':['source_row','manifest_row_id','vin','received_date','location_id']}
LABELS={'funds':'车辆请款清单','ship':'请款车辆发运清单','receive':'请款车辆到货清单'}


def parse(kind,content):
    if kind not in HEADERS:raise HTTPException(422,'请选择请款、发运或到货清单')
    if len(content)>MAX_BYTES:raise HTTPException(413,'CSV 不得超过 128 KiB（131072 字节）')
    try:
        text=content.decode('utf-8-sig')
        if '\x00' in text:raise ValueError()
        values=list(csv.reader(io.StringIO(text,newline=''),strict=True))
    except (UnicodeError,ValueError,csv.Error) as exc:raise HTTPException(422,'请上传严格 UTF-8 编码的 CSV 文件') from exc
    if not values or values[0]!=HEADERS[kind]:raise HTTPException(422,'CSV 表头须严格为：'+','.join(HEADERS[kind]))
    if not 1<=len(values)-1<=200:raise HTTPException(422,'每批须有 1 至 200 行资料，不能含空行')
    rows=[]
    for number,raw in enumerate(values[1:],2):
        errors=[];v={}
        if len(raw)!=len(HEADERS[kind]):errors.append('字段数量与表头不一致')
        else:
            for name,value in zip(HEADERS[kind],raw):
                if value!=value.strip() or not value or len(value)>100:errors.append(name+' 不得为空、过长或带首尾空格');continue
                if name in {'line_id','manifest_row_id','amount_cents','location_id'}:
                    if not re.fullmatch(r'[1-9][0-9]{0,11}',value):errors.append(name+' 须为正整数（金额单位分）');continue
                    v[name]=int(value)
                elif name.endswith('_date'):
                    try:
                        parsed=date.fromisoformat(value)
                        if parsed.isoformat()!=value:raise ValueError()
                        v[name]=value
                    except ValueError:errors.append(name+' 须为 YYYY-MM-DD 日期')
                elif name=='vin':
                    if not re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}',value):errors.append('VIN 须为 17 位大写字母和数字，不含 I/O/Q')
                    else:v[name]=value
                elif name=='source_row':
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',value):errors.append('source_row 须为 1 至 80 位来源行编号（字母、数字、下划线、短横线）')
                    else:v[name]=value
        rows.append({'number':number,'values':v,'errors':errors})
    return rows
