"""Small synthetic spreadsheet fixture; no customer files or model calls."""
import io
import zipfile
from xml.sax.saxutils import escape


VEHICLE_ROW = {
    'family': '合成车系', 'series': '合成系列', 'model': '合成配置',
    'guide_price_cents': 12000000, 'control_price_cents': 10000000,
    'note': '合成限价条件',
    'gift_policy': {'text': '合成赠品总成本额度，允许替换', 'cost_limit_cents': 10000},
}


def vehicle_xlsx():
    """A real, visible XLSX sheet accepted by the original upload validator."""
    rows = [['车系', '系列', '车型', '指导价', '销售管控价', '赠品政策'],
            ['合成车系', '合成系列', '合成配置', '120000', '100000', '赠品总成本限100元，允许替换']]
    cells = ''.join('<row r="%s">%s</row>' % (number, ''.join(
        '<c r="%s%s" t="inlineStr"><is><t>%s</t></is></c>' %
        (chr(65 + column), number, escape(value)) for column, value in enumerate(row)))
        for number, row in enumerate(rows, 1))
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        original_write = archive.writestr
        def deterministic_write(name, value):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            original_write(info, value)
        archive.writestr = deterministic_write
        archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="合成限价" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + cells + '</sheetData></worksheet>')
    return output.getvalue()


def gift_csv():
    return ('名称,品牌,成本,售价,单位,适用车型\n'
            '合成脚垫,合成品牌,40,60,套,合成配置\n'
            '合成礼盒,合成品牌,75,90,套,合成配置\n'
            '合成水杯,合成品牌,10,20,个,通用\n').encode('utf-8-sig')
