"""Customer-supplied decoration gift notice and preprinted-paper filling layer.

The photographed form establishes relative positions, not physical paper size.
280 x 95 mm is an initial preview setting; staff supply measured dimensions and
offsets when needed. Prices and costs never enter this customer copy.
"""
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

from reportlab.pdfgen.canvas import Canvas

from .business_record_pdf import FONT, _lines, _text


TEMPLATE_VERSION = 'decoration-gift-notice-20261018-v2'
DEFAULT_WIDTH_MM = 280
DEFAULT_HEIGHT_MM = 95
_LOGO = Path(__file__).resolve().parents[1] / 'web' / 'assets' / 'huakang-logo-source.png'


def _setting(value, minimum, maximum, label):
    try:
        value = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(label + '必须为有效数字。') from None
    if not value.is_finite() or not minimum <= value <= maximum:
        raise ValueError(label + f'须在 {minimum} 至 {maximum} 毫米之间。')
    return float(value)


def _gift_rows(snapshot, copy_kind='customer'):
    terms = snapshot.get('terms') or {}
    benefits = terms.get('submission_data') or {}
    items = []
    # Standard benefits remain frozen and redeemable. Printing is a projection:
    # first service is omitted on all copies; NPS belongs only to the store copy.
    if copy_kind == 'internal' and benefits.get('nps_participation') is True:
        items.append('参与 NPS 调研，赠送保养 1 次')
    for item in terms.get('gifts_snapshot') or []:
        items.append(_text(item.get('name')) + ' × ' + _text(item.get('quantity'))
                     + ' ' + _text(item.get('unit')))
    # Four physical rows per sheet; long names continue instead of truncating.
    rows = []
    for value in items or ['本联无列示赠送项目']:
        lines = _lines(value, 367, 12)
        rows.extend(lines[start:start + 2] for start in range(0, len(lines), 2))
    return rows


def render_gift_vouchers(snapshot: dict, *, output_mode='full', copy_kind='customer',
        paper_width_mm=DEFAULT_WIDTH_MM, paper_height_mm=DEFAULT_HEIGHT_MM,
        offset_x_mm=0, offset_y_mm=0) -> bytes:
    """Render the current approved snapshot; keep the amount column empty."""
    if output_mode not in {'full', 'overprint'}:
        raise ValueError('请选择完整赠送通知单或预印纸套打。')
    if copy_kind not in {'customer', 'internal'}:
        raise ValueError('请选择客户联或门店留存联。')
    width = _setting(paper_width_mm, 150, 400, '纸张宽度')
    height = _setting(paper_height_mm, 60, 210, '纸张高度')
    offset_x = _setting(offset_x_mm, -20, 20, '水平偏移')
    offset_y = _setting(offset_y_mm, -20, 20, '垂直偏移')
    full = output_mode == 'full'
    rows = _gift_rows(snapshot, copy_kind)
    pages = (len(rows) + 3) // 4
    out = BytesIO()
    canvas = Canvas(out, pagesize=(width * 72 / 25.4, height * 72 / 25.4), invariant=1)
    canvas.setTitle('装饰赠送通知单' + ('' if full else ' · 预印纸填写层'))
    canvas.setAuthor('HuaKangOS')
    canvas.setSubject(TEMPLATE_VERSION)

    def text(value, x, top, size=12, centered=False):
        canvas.setFont(FONT, size)
        draw = canvas.drawCentredString if centered else canvas.drawString
        draw(x, 336 - top, value)

    def fit(value, left, top, cell_width, cell_height, label, size=12):
        value = _text(value)
        while size >= 8:
            lines = _lines(value, cell_width - 12, size)
            line_height = size * 1.1
            if len(lines) * line_height <= cell_height - 5:
                first = top + (cell_height - len(lines) * line_height) / 2 + size
                for index, line in enumerate(lines):
                    text(line, left + cell_width / 2, first + index * line_height, size, True)
                return
            size -= 0.5
        raise ValueError(label + '超出赠送通知单可打印区域，请核对后再打印。')

    for page in range(pages):
        canvas.saveState()
        if not full:
            canvas.translate(offset_x * 72 / 25.4, -offset_y * 72 / 25.4)
        canvas.scale(width * 72 / 25.4 / 1000, height * 72 / 25.4 / 336)
        canvas.setFillColorRGB(0, 0, 0)
        canvas.setStrokeColorRGB(0, 0, 0)
        if full:
            # Reuse the official mark and source crop already used by the site.
            # The existing bitmap is embedded unchanged; no customer photo is kept.
            canvas.saveState()
            clip = canvas.beginPath(); clip.rect(99, 270, 39.52, 40)
            canvas.clipPath(clip, stroke=0, fill=0)
            scale = 40 / 1320
            canvas.drawImage(str(_LOGO), 99 - 8 * scale, 270 - (2868 - 774 - 1320) * scale,
                width=1320 * scale, height=2868 * scale)
            canvas.restoreState()
            text('华慷集团', 148, 47, 22)
            canvas.setFont('Helvetica-Bold', 9)
            canvas.drawString(148, 336 - 62, 'HUAKANG GROUP')
            title = canvas.beginText(320, 336 - 60)
            title.setFont(FONT, 34); title.setCharSpace(20)
            title.textOut('装饰赠送通知单'); title.setCharSpace(0); canvas.drawText(title)
            canvas.setLineWidth(0.9)
            for top in (81, 113, 141, 169, 197, 225, 253, 282):
                canvas.line(75, 336 - top, 938, 336 - top)
            for x in (75, 178, 563, 938):
                canvas.line(x, 336 - 81, x, 336 - 282)
            for x in (352, 438, 663):
                canvas.line(x, 336 - 81, x, 336 - 113)
            for value, x in (('日  期', 126.5), ('车 型', 395), ('底盘号', 613)):
                text(value, x, 103, 17, True)
            text('装    饰    项    目', 370.5, 133, 17, True)
            text('金    额', 750.5, 133, 17, True)
            for row in range(4):
                text(str(row + 1), 126.5, 161 + row * 28, 17, True)
            text('合计金额', 126.5, 273, 17, True)
            text('业务员签字：', 78, 308, 20)
            text('经理签字：', 383, 308, 20)
        fit(snapshot.get('contract_date'), 178, 81, 174, 32, '日期')
        fit(snapshot.get('model'), 438, 81, 125, 32, '车型', 11)
        fit(snapshot.get('vin'), 663, 81, 275, 32, '底盘号')
        for index, lines in enumerate(rows[page * 4:page * 4 + 4]):
            top = 141 + index * 28
            first = top + (28 - len(lines) * 13.2) / 2 + 12
            for line_index, line in enumerate(lines):
                text(line, 187, first + line_index * 13.2)
        # Names are not signatures. Tracking information stays outside cells.
        footer = ('客户联' if copy_kind == 'customer' else '门店留存联') + '    合同号：' + _text(snapshot.get('number')) + f'    第 {page + 1}/{pages} 页'
        fit(footer, 75, 317, 863, 17, '合同号', 8)
        canvas.restoreState()
        canvas.showPage()
    canvas.save()
    return out.getvalue()


def render_gift_calibration(**settings) -> bytes:
    """Non-personal sample using the exact same coordinates as real overprinting."""
    return render_gift_vouchers({
        'number': 'CALIBRATION', 'contract_date': '2000-01-01',
        'model': '车型位置校准', 'vin': 'VIN-POSITION-CHECK',
        'terms': {'gifts_snapshot': [{'name': '项目位置校准 ' + str(n),
            'quantity': n, 'unit': '件'} for n in range(1, 5)]},
    }, output_mode='overprint', **settings)
