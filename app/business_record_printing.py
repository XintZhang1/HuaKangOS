"""Anonymous printer alignment sheet; never a substitute for physical paper QA."""
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from .security import get_user

router = APIRouter(prefix='/api/business-records', tags=['预印纸套打校准'])


@router.get('/print-calibration')
def calibration(offset_x_mm: float = Query(0, ge=-20, le=20),
        offset_y_mm: float = Query(0, ge=-20, le=20), user=Depends(get_user)):
    if user.role not in {'finance', 'admin'} or getattr(user, '_aggregate_scope', False):
        raise HTTPException(403, '套打校准由当前门店财务执行')
    import math
    if not all(math.isfinite(v) for v in (offset_x_mm, offset_y_mm)):
        raise HTTPException(422, '请填写有效的毫米偏移')
    from reportlab.pdfgen.canvas import Canvas
    from .business_record_pdf import FONT
    output = BytesIO()
    canvas = Canvas(output, pagesize=(595.276, 841.89), invariant=1)
    canvas.setTitle('预印纸定位校准 · 无客户信息')
    canvas.translate(offset_x_mm * 72 / 25.4, -offset_y_mm * 72 / 25.4)
    canvas.setFont(FONT, 10)
    canvas.drawString(52, 790, 'A4 · 100%原始比例 · 先用普通纸试打后与预印纸叠放')
    canvas.drawString(52, 773, '三个十字应对准表格左上、右上、左下角；勿选择适合页面。')
    for x, top in ((28.56, 85.32), (553.32, 85.32), (28.56, 763.44)):
        y = 841.89 - top
        canvas.line(x - 6, y, x + 6, y)
        canvas.line(x, y - 6, x, y + 6)
    canvas.showPage(); canvas.save()
    return Response(output.getvalue(), media_type='application/pdf',
        headers={'Content-Disposition': 'inline; filename="contract-alignment.pdf"', 'Cache-Control': 'no-store'})
