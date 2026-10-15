"""Customer gift vouchers from an approved contract; never expose gift prices."""
from io import BytesIO

from reportlab.pdfgen.canvas import Canvas

from .business_record_pdf import FONT, _lines, _text


def _empty_gifts_confirmation(snapshot):
    """Keep the stamped-document delivery path available when no gift was agreed."""
    out = BytesIO()
    canvas = Canvas(out, pagesize=(595.276, 841.89), invariant=1)
    canvas.setTitle('赠送项目确认')
    canvas.setFont(FONT, 18)
    canvas.drawString(50, 785, '赠送项目确认')
    canvas.setFont(FONT, 11)
    y = 745
    for label, key in (('合同号', 'number'), ('客户', 'customer_name'), ('车辆', 'model'), ('车架号', 'vin')):
        for line in _lines(label + '：' + _text(snapshot.get(key)), 490, 11):
            if y < 120:
                canvas.showPage(); canvas.setFont(FONT, 11); y = 780
            canvas.drawString(50, y, line); y -= 22
    if y < 190:
        canvas.showPage(); canvas.setFont(FONT, 11); y = 780
    canvas.drawString(50, y - 20, '本合同无赠品，不另行出具赠送券。')
    canvas.drawString(50, y - 65, '客户确认：________________    日期：________________')
    canvas.drawString(50, y - 100, '门店盖章：________________')
    canvas.save()
    return out.getvalue()


def render_gift_vouchers(snapshot: dict) -> bytes:
    terms = snapshot.get('terms') or {}
    benefits = terms.get('submission_data') or {}
    items = []
    if benefits.get('first_service_count') == 1:
        items.append(('首次保养', '1 次', '首次保养免费赠送1次'))
    if benefits.get('nps_participation') is True:
        items.append(('NPS 保养赠送', '1 次', '参与NPS调研，赠送保养1次'))
    for item in terms.get('gifts_snapshot') or []:
        items.append((_text(item.get('name')), _text(item.get('quantity')) + ' ' + _text(item.get('unit')), ''))
    if not items:
        return _empty_gifts_confirmation(snapshot)
    out = BytesIO()
    canvas = Canvas(out, pagesize=(595.276, 841.89), invariant=1)
    canvas.setTitle('客户赠送券')
    canvas.setAuthor('HuaKangOS')
    blue, pale, ink = '#14577A', '#F0F7FA', '#17374A'
    seller = _text((snapshot.get('form_data') or {}).get('seller_name'))
    number = _text(snapshot.get('number'))

    def text(value, x, y, size=10, color=ink):
        canvas.setFillColor(color)
        canvas.setFont(FONT, size)
        canvas.drawString(x, y, value)

    def page():
        text('客户赠送券', 34, 806, 17, blue)
        canvas.setFont(FONT, 9)
        canvas.drawRightString(561, 808, '按虚线裁切 · 客户联')
        return 784

    top = page()
    for index, (name, quantity, condition) in enumerate(items, 1):
        title_lines = _lines(name, 394, 16)
        seller_lines = _lines(seller, 450, 9) if seller else []
        vehicle_lines = _lines('车辆：' + _text(snapshot.get('model')), 455, 9)
        number_lines = _lines('合同号：' + number, 455, 9)
        customer_lines = _lines('客户：' + _text(snapshot.get('customer_name')), 455, 10)
        height = 187 + len(title_lines) * 21 + (len(vehicle_lines) + len(number_lines) + len(customer_lines) - 3) * 14 + len(seller_lines) * 12
        if condition:
            height += 17
        if height > 730:
            raise ValueError('赠送项目名称或合同资料过长，请核对后再打印赠送券。')
        if top - height < 40:
            canvas.showPage()
            top = page()
        bottom = top - height
        canvas.setFillColor(pale)
        canvas.setStrokeColor(blue)
        canvas.setLineWidth(0.8)
        canvas.roundRect(34, bottom, 527, height, 9, stroke=1, fill=1)
        canvas.setFillColor(blue)
        canvas.roundRect(47, top - 39, 59, 24, 5, stroke=0, fill=1)
        text('赠送券', 58, top - 31, 12, '#FFFFFF')
        canvas.setFillColor(blue)
        canvas.setFont(FONT, 10)
        canvas.drawRightString(544, top - 30, '第 ' + str(index) + ' / ' + str(len(items)) + ' 项')
        y = top - 61
        for line in title_lines:
            text(line, 51, y, 16)
            y -= 21
        text('赠送数量：' + quantity.strip(), 51, y - 1, 10, blue)
        y -= 19
        if condition:
            text(condition, 51, y, 9)
            y -= 17
        canvas.setStrokeColorRGB(0.76, 0.85, 0.90)
        canvas.line(51, y + 3, 544, y + 3)
        y -= 12
        for lines in (customer_lines, vehicle_lines, number_lines,
                ['车架号：' + _text(snapshot.get('vin'))]):
            for line in lines:
                text(line, 51, y, 9)
                y -= 14
        for line in seller_lines:
            text(line, 51, y, 9)
            y -= 12
        text('门店盖章：_______________', 51, bottom + 35, 10)
        text('领取签字：_______________', 315, bottom + 35, 10)
        text('领取日期：_______年____月____日', 51, bottom + 16, 9)
        text('赠送内容以对应合同约定为准', 360, bottom + 16, 8, blue)
        top = bottom - 22
        if index < len(items):
            canvas.setStrokeColorRGB(0.64, 0.71, 0.75)
            canvas.setDash(3, 4)
            canvas.line(34, bottom - 11, 561, bottom - 11)
            canvas.setDash()
    canvas.save()
    return out.getvalue()
