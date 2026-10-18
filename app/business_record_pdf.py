"""Fill the approved two-page sales contract without rewriting its legal terms.

Only an approval snapshot is accepted by the HTTP caller. New paid accessories
append a separate sheet. Bytes are deterministic for the same snapshot and
template. No files or customer content are persisted.
"""
from datetime import date
from decimal import Decimal
import hashlib
from io import BytesIO
from pathlib import Path
import re

from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas

TEMPLATE_SHA256 = '65637e3acca81579cc3b576e93b225866941f4cd9b5de1cad1bb9f6d468f1449'
TEMPLATE_VERSION = 'sales-contract-2026-' + TEMPLATE_SHA256[:16]
TEMPLATE_PATH = Path(__file__).with_name('assets') / 'sales-contract-2026.pdf'
FONT = 'STSong-Light'
pdfmetrics.registerFont(UnicodeCIDFont(FONT))


def _text(value):
    if value is None:
        return ''
    if isinstance(value, (dict, list, bool)):
        raise ValueError('合同字段不是可打印文本。')
    value = str(value)
    if any(ord(char) < 32 and char not in '\n\t' for char in value):
        raise ValueError('合同字段包含不可打印字符。')
    return value.replace('\t', ' ')


def _amount(value):
    text = _text(value).strip()
    if not text:
        return None
    if not re.fullmatch(r'\d+(?:\.\d{1,2})?', text):
        raise ValueError('合同金额必须为非负数，最多保留两位小数。')
    amount = Decimal(text)
    if amount > Decimal('999999999999.99'):
        raise ValueError('合同金额超出范围。')
    return amount


def _chinese_money(amount):
    """Exact uppercase RMB including cents; never round to fit printed placeholders."""
    digits = '零壹贰叁肆伍陆柒捌玖'
    whole = int(amount)
    def block(value):
        out, zero = '', False
        for power, unit in ((1000, '仟'), (100, '佰'), (10, '拾'), (1, '')):
            number, value = divmod(value, power)
            if number:
                if zero and out:
                    out += '零'
                out += digits[number] + unit
                zero = False
            elif out and value:
                zero = True
        return out
    out = ''
    for divisor, unit in ((100000000, '亿'), (10000, '万'), (1, '')):
        part, remainder = divmod(whole, divisor)
        if part:
            if out and part < 1000:
                out += '零'
            out += block(part) + unit
        whole = remainder
    out = (out or '零') + '元'
    cents = int(amount * 100) % 100
    if not cents:
        return out + '整'
    jiao, fen = divmod(cents, 10)
    if jiao:
        out += digits[jiao] + '角'
    elif fen:
        out += '零'
    if fen:
        out += digits[fen] + '分'
    return out


def _lines(text, width, size):
    result = []
    for paragraph in text.split('\n'):
        line = ''
        for char in paragraph:
            if line and pdfmetrics.stringWidth(line + char, FONT, size) > width:
                result.append(line)
                line = char
            else:
                line += char
        result.append(line)
    return result


def _box(canvas, value, x, top, width, height, label, size=9, minimum=6.5):
    text = _text(value)
    if not text:
        return
    while size >= minimum:
        lines = _lines(text, width, size)
        if len(lines) * size * 1.15 <= height:
            canvas.setFont(FONT, size)
            for index, line in enumerate(lines):
                canvas.drawString(x, 841.89 - top - size - index * size * 1.15, line)
            return
        size -= 0.25
    raise ValueError(label + '内容超出合同可打印区域，请缩短后重新核对审批。')


def validate_contract_print_data(data):
    """Check printable bounds before manager approval, without storing a draft PDF."""
    snapshot = dict(data)
    snapshot['template_version'] = TEMPLATE_VERSION
    render_contract_pdf(snapshot)


def _accessory_attachment(data):
    """Print only frozen customer prices; internal costs never enter this sheet."""
    submission = (data.get('terms') or {}).get('submission_data') or {}
    items = submission.get('accessory_snapshot') or []
    if not items:
        return None
    if not isinstance(items, list):
        raise ValueError('有偿精品快照格式不正确。')
    rows, total = [], 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('有偿精品快照格式不正确。')
        quantity, unit_price, amount = (item.get(key) for key in ('quantity', 'unit_price_cents', 'amount_cents'))
        if (any(not isinstance(value, int) or isinstance(value, bool) for value in (quantity, unit_price, amount))
                or quantity < 1 or unit_price < 0 or amount != quantity * unit_price):
            raise ValueError('有偿精品数量或售价快照不正确。')
        name = _text(item.get('name')).strip()
        if not name:
            raise ValueError('有偿精品名称快照不能为空。')
        rows.append((name, str(quantity), format(Decimal(unit_price) / 100, '.2f'),
                     format(Decimal(amount) / 100, '.2f')))
        total += amount
    if submission.get('accessory_total_cents') != total:
        raise ValueError('有偿精品合计快照不一致。')
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=(595.276, 841.89), invariant=1, pageCompression=1)
    page_number = 0
    def heading():
        nonlocal page_number
        page_number += 1
        canvas.setFont(FONT, 16)
        canvas.drawCentredString(297.638, 795, '汽车销售合约书附件 · 有偿精品')
        canvas.setFont(FONT, 9)
        canvas.drawString(36, 770, '合同号：' + _text(data.get('number')))
        canvas.drawString(36, 752, '买方：' + _text(data.get('customer_name')))
        canvas.drawRightString(559, 752, '附件第 ' + str(page_number) + ' 页')
        canvas.drawString(36, 731, '以下为客户另行购买的精品，不计入合同纯车售价。')
        canvas.setFont(FONT, 10)
        for title, x in (('项目', 42), ('数量', 304), ('单价（元）', 355), ('金额（元）', 460)):
            canvas.drawString(x, 706, title)
        canvas.line(36, 696, 559, 696)
        return 684
    y = heading()
    for name, quantity, unit_price, amount in rows:
        lines = _lines(name, 245, 10)
        height = max(26, len(lines) * 14 + 12)
        if height > 570:
            raise ValueError('有偿精品名称超出可打印区域。')
        if y - height < 72:
            canvas.showPage()
            y = heading()
        canvas.setFont(FONT, 10)
        for index, line in enumerate(lines):
            canvas.drawString(42, y - 10 - index * 14, line)
        for value, x in ((quantity, 329), (unit_price, 438), (amount, 553)):
            canvas.drawRightString(x, y - 10, value)
        y -= height
        canvas.line(36, y, 559, y)
    if y < 132:
        canvas.showPage()
        y = heading()
    canvas.setFont(FONT, 11)
    canvas.drawRightString(553, y - 26, '精品合计：' + format(Decimal(total) / 100, '.2f') + ' 元')
    canvas.setFont(FONT, 10)
    canvas.drawString(42, y - 66, '买方签字：________________')
    canvas.drawString(325, y - 66, '卖方签字：________________')
    canvas.showPage()
    canvas.save()
    return stream.getvalue()


def render_contract_pdf(data: dict, *, output_mode='full', copy_kind='customer', offset_x_mm=0, offset_y_mm=0) -> bytes:
    if output_mode not in {'full', 'overprint'}:
        raise ValueError('请选择完整合同或预印纸套打。')
    if copy_kind not in {'customer', 'internal'}:
        raise ValueError('请选择客户联或门店留存联。')
    offsets = [Decimal(str(value)) for value in (offset_x_mm, offset_y_mm)]
    if any(not value.is_finite() or abs(value) > 20 for value in offsets):
        raise ValueError('套打位置偏移须在正负20毫米内。')
    overprint = output_mode == 'overprint'
    if not isinstance(data, dict) or data.get('template_version') != TEMPLATE_VERSION:
        raise ValueError('该合同绑定的模板版本不可用，请保留原审批记录并联系管理员。')
    template = TEMPLATE_PATH.read_bytes()
    if hashlib.sha256(template).hexdigest() != TEMPLATE_SHA256:
        raise ValueError('合同模板指纹不匹配，已停止打印。')
    form = data.get('form_data') or {}
    if not isinstance(form, dict):
        raise ValueError('合同填写快照格式不正确。')
    accessory_attachment = _accessory_attachment(data)
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=(595.276, 841.89), invariant=1, pageCompression=1)
    canvas.setTitle('汽车销售合约书')
    canvas.setAuthor('HuaKangOS')
    if overprint:
        canvas.setTitle('汽车销售合约书 · 预印纸填写层')
        canvas.translate(float(offsets[0]) * 72 / 25.4, -float(offsets[1]) * 72 / 25.4)
    def put(value, x, top, width, height, label, size=9):
        _box(canvas, value, x, top, width, height, label, size)

    put(data.get('number'), 435, 64, 113, 15, '合同号', 8)
    put(form.get('seller_name'), 89, 87, 457, 17, '卖方')
    put(data.get('customer_name'), 89, 107, 92, 17, '买方')
    put(form.get('buyer_document_name'), 245, 107, 107, 17, '证件名称', 8)
    put(form.get('buyer_id_number'), 429, 107, 118, 17, '证件号码', 8)
    put(data.get('customer_phone'), 89, 128, 92, 18, '客户电话', 8)
    put(form.get('buyer_address'), 244, 126, 108, 21, '客户地址', 7)
    put(form.get('buyer_email'), 429, 128, 118, 18, '电子邮件', 7.5)
    put(data.get('brand'), 89, 164, 92, 16, '车辆品牌', 8.5)
    put(data.get('model'), 244, 163, 64, 17, '车辆型号', 7)
    put(form.get('quantity', '1'), 448, 164, 36, 16, '数量')
    put(form.get('exterior_color'), 89, 180, 92, 16, '外观颜色', 8)
    put(form.get('interior_color'), 244, 180, 64, 16, '内饰颜色', 8)
    put(data.get('vin'), 429, 180, 118, 16, 'VIN', 8)

    cents = data.get('sale_price_cents')
    if not isinstance(cents, int) or isinstance(cents, bool) or cents <= 0:
        raise ValueError('购车价快照必须为正整数分。')
    sale = Decimal(cents) / 100
    amounts = ((sale, 215, False, '购车价'),
               (_amount(form.get('subsidy_deposit')), 238, False, '置换补贴押金'),
               (_amount(form.get('corporate_subsidy_deposit')), 261, False, '大客户补贴押金'),
               (_amount(form.get('deposit')), 305, True, '定金'),
               (_amount(form.get('balance')), 362, True, '余款'))
    for amount, top, payment, label in amounts:
        if amount is None:
            continue
        if overprint:
            # These seven spaces precede the preprinted 百/十/万/千/百/十/元.
            # White paint cannot erase ink on the customer's paper. Never round
            # a fractional amount to fit the integral-only printed template.
            if amount != amount.to_integral_value() or amount > 9999999:
                raise ValueError(label + '含角分或超过七位整数，当前预印纸金额格不适配；请使用完整合同或核对新的纸样。')
            digits = str(int(amount)).zfill(7)
            positions = (238, 274, 315, 350, 391, 431, 468) if payment else (286, 322, 363, 399, 439, 479, 516)
            digit_top = {215:215, 238:237, 261:262, 305:304, 362:361}[top]
            for digit, x in zip(digits, positions):
                put('零壹贰叁肆伍陆柒捌玖'[int(digit)], x, digit_top, 12, 14, label + '大写数位', 9)
            put(str(int(amount)) if payment else format(amount, '.2f'), 104 if payment else 130,
                (top + (1 if top == 362 else 5)) if payment else top, 35 if payment else 94, 15, label, 8 if payment else 8.5)
            continue
        # Replace only numeric input placeholders, leaving headings and legal text.
        x, width = (193, 349) if payment else (231, 317)
        canvas.setFillColorRGB(1, 1, 1)
        canvas.rect(x, 841.89 - top - 15, width, 17, fill=1, stroke=0)
        canvas.setFillColorRGB(0, 0, 0)
        put('人民币（大写）' + _chinese_money(amount), x + 2, top, width - 4, 15, label + '大写', 8)
        if payment:
            canvas.setFillColorRGB(1, 1, 1)
            canvas.rect(100, 841.89 - top - 19, 79, 18, fill=1, stroke=0)
            canvas.setFillColorRGB(0, 0, 0)
            put(format(amount, '.2f') + '元', 103, top + 2, 75, 16, label, 8)
        else:
            put(format(amount, '.2f'), 130, top, 94, 15, label, 8.5)

    payment = _text(form.get('payment_method'))
    if payment:
        if not overprint or payment not in {'现金', '刷卡'}:
            put(payment, 291, 329, 247, 16, '付款方式', 8)
            put(payment, 386, 408, 154, 15, '余款付款方式', 7.5)
        def mark(x, top):
            canvas.setLineWidth(0.7)
            y = 841.89 - top
            if overprint or data.get('print_layout_version') == 'full-v218':
                canvas.line(x, y - 2, x + 2, y - 5)
                canvas.line(x + 2, y - 5, x + 7, y + 2)
            else:
                canvas.line(x, y, x + 5, y - 5)
                canvas.line(x, y - 5, x + 5, y)
        if payment == '现金':
            mark(195, 335)
            mark(195, 396)
        elif payment == '刷卡':
            mark(227, 335)
            mark(308, 396)
        else:
            mark(259, 335)
            mark(307, 412)
    loan = _amount(form.get('loan_amount'))
    if loan is not None:
        put(format(loan, '.2f'), 223, 407, 48, 15, '按揭金额', 7)
        if loan > 0:
            canvas.setLineWidth(0.7)
            if overprint or data.get('print_layout_version') == 'full-v218':
                canvas.line(195, 428, 197, 425)
                canvas.line(197, 425, 202, 432)
            else:
                canvas.line(195, 430, 200, 425)
                canvas.line(195, 425, 200, 430)

    other = []
    if copy_kind == 'internal' and form.get('standard_benefits_version') == '1':
        if form.get('nps_participation') == '1':
            other.append('参与NPS调研，赠送保养1次')
    if accessory_attachment:
        other.append('有偿精品项目及售价详见本合同附件')
    if form.get('payment_method') == '贷款' and form.get('down_payment') not in (None, ''):
        other.append('分期首付：' + format(_amount(form['down_payment']), '.2f') + '元')
    if data.get('gift_description'):
        # New contracts have a separately printable, frozen gift list. Keep
        # its full names/quantities there instead of overflowing this fixed box.
        other.append('赠品详见本合同赠品单' if data.get('workflow_version') == 'trial-v210'
                     else '赠品约定：' + _text(data['gift_description']))
    if form.get('other_terms'):
        other.append(_text(form['other_terms']))
    for key, label in (('payment_institution_type', '贷款机构类别'), ('payment_bank', '贷款机构名称'), ('seller_address', '卖方地址'),
                       ('buyer_postcode', '买方邮编'), ('buyer_agent', '买方代理人'),
                       ('buyer_agent_id_number', '代理人证件号码')):
        if form.get(key):
            other.append(label + '：' + _text(form[key]))
    put('；'.join(other), 33, 447, 513, 49, '其他约定', 8)
    put(form.get('delivery_place'), 87, 519, 150, 21, '提车地点', 8)
    put(form.get('delivery_date'), 292, 519, 254, 21, '提车时间', 8)
    put(form.get('seller_agent') or data.get('salesperson_name'), 77, 697, 76, 18, '业务代表', 8)
    put(form.get('seller_phone'), 187, 697, 94, 18, '卖方电话', 8)
    signature = _text(form.get('signature_date') or data.get('contract_date'))
    if signature:
        try:
            signed = date.fromisoformat(signature)
        except ValueError:
            raise ValueError('签订日期请填写YYYY-MM-DD。') from None
        for x, y in ((76, 723), (415, 725)):
            put(str(signed.year), x, y, 25, 14, '签订年', 8)
            put(str(signed.month), x + 40, y, 20, 14, '签订月', 8)
            put(str(signed.day), x + (77 if x == 76 else 85), y, 20, 14, '签订日', 8)
    canvas.showPage()
    canvas.save()
    if overprint:
        # No background page, legal terms, white masks or accessory attachment
        # enter the customer's preprinted-paper queue.
        return stream.getvalue()
    overlay = PdfReader(BytesIO(stream.getvalue()))
    original = PdfReader(BytesIO(template))
    if len(original.pages) != 2:
        raise ValueError('合同模板页数不匹配。')
    original.pages[0].merge_page(overlay.pages[0])
    writer = PdfWriter()
    writer.add_page(original.pages[0])
    writer.add_page(original.pages[1])
    if accessory_attachment:
        for page in PdfReader(BytesIO(accessory_attachment)).pages:
            writer.add_page(page)
    writer.add_metadata({'/Title': '汽车销售合约书', '/Author': 'HuaKangOS',
                         '/Subject': TEMPLATE_VERSION, '/Creator': 'HuaKangOS'})
    result = BytesIO()
    writer.write(result)
    return result.getvalue()
