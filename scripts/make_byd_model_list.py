"""生成"比亚迪车型清单"xlsx，用于试用业务助手的表格导入。

python scripts/make_byd_model_list.py [输出路径]

只写 OOXML 最小包（inline string），不依赖 openpyxl——业务助手的表格解析器本身就是
zipfile+XML 读的，写完用它的 xlsx_preview 回读校验。

数据来源（2026-09-25 抓取，均为公开经销商/车型库页面，价格是"厂商指导价"）：
- 王朝网经销商报价页：https://dealer.yiche.com/100018768/news/202609/1468241855.html
- 海洋网车型库（车系与起步价）：https://newcar.xcar.com.cn/b30/car_t3_o2.htm
没有可靠来源的价格一律留空并在备注里写明，不编造数字。
"""
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / 'docs/试用记录/比亚迪车型清单_导入用_20260925.xlsx'
HEADERS = ['品牌', '品牌编码', '车系', '车系编码', '车型', '车型编码', '年款', '动力类型', '动力代码',
           '座位数', '排量(ml)', '电池容量(Wh)', '指导价(元)', '备注']
PURE, PLUG = '纯电', '插电混动'
BRAND_CODE = 'BYD'
# 车系编码：助手试用时如果系统要求编码，直接按这张表填，不用临时发明。
SERIES_CODE = {
    '元UP': 'YUANUP', '元PLUS': 'YUANPLUS', '秦L': 'QINL', '秦MAX': 'QINMAX', '宋Pro': 'SONGPRO',
    '宋L': 'SONGL', '宋Ultra': 'SONGULTRA', '汉': 'HAN', '夏': 'XIA', '唐': 'TANG',
    '大唐': 'DATANG', '大汉': 'DAHAN', '海狮07': 'HAISHI07', '海狮06': 'HAISHI06',
    '海狮05': 'HAISHI05', '护卫舰07': 'HUWEIJIAN07', '海豹': 'HAOBAO', '海豹06': 'HAOBAO06',
    '海豹07': 'HAOBAO07', '海豚': 'HAITUN', '海鸥': 'HAIQIU', '驱逐舰05': 'QUZHUJIAN05',
}
# (车系, 车型, 年款, 动力, 座位数, 排量ml, 指导价元或None, 备注)
DYNASTY = [
    ('元UP', '元UP 飞驰版 301km 领航型', 2027, PURE, 5, 0, 74800, ''),
    ('元UP', '元UP 飞驰版 401km 领航型', 2027, PURE, 5, 0, 81800, ''),
    ('元UP', '元UP 飞驰版 401km 活力型', 2027, PURE, 5, 0, 89800, ''),
    ('元UP', '元UP 飞驰版 501km 超越型', 2027, PURE, 5, 0, 94800, ''),
    ('元UP', '元UP 飞驰版 501km 卓越型', 2027, PURE, 5, 0, 104800, ''),
    ('秦L', '秦L DM-i 1.5L 128km 进取型', 2026, PLUG, 5, 1498, 96800, ''),
    ('秦L', '秦L DM-i 1.5L 128km 领先型', 2026, PLUG, 5, 1498, 106800, ''),
    ('秦L', '秦L DM-i 1.5L 210km 超越型', 2026, PLUG, 5, 1498, 116800, ''),
    ('秦L', '秦L DM-i 1.5L 210km 云辇型', 2026, PLUG, 5, 1498, 126800, ''),
    ('秦MAX', '秦MAX DM-i 1.5L 230km 领先型', 2026, PLUG, 5, 1498, 99900, ''),
    ('秦MAX', '秦MAX DM-i 1.5L 230km 超越型', 2026, PLUG, 5, 1498, 109900, ''),
    ('秦MAX', '秦MAX DM-i 1.5L 320km 超越型', 2026, PLUG, 5, 1498, 119900, ''),
    ('秦MAX', '秦MAX DM-i 1.5L 320km 卓越型', 2026, PLUG, 5, 1498, 129900, ''),
    ('秦MAX', '秦MAX EV 530km 领先型', 2026, PURE, 5, 0, 109900, ''),
    ('秦MAX', '秦MAX EV 530km 超越型', 2026, PURE, 5, 0, 119900, ''),
    ('秦MAX', '秦MAX EV 530km 卓越型', 2026, PURE, 5, 0, 129900, ''),
    ('秦MAX', '秦MAX EV 630km 超越型', 2026, PURE, 5, 0, 132900, ''),
    ('秦MAX', '秦MAX EV 630km 卓越型', 2026, PURE, 5, 0, 143900, ''),
    ('宋Pro', '宋Pro DM-i 1.5L 133km 进取型', 2026, PLUG, 5, 1498, 102800, ''),
    ('宋Pro', '宋Pro DM-i 1.5L 133km 超越型', 2026, PLUG, 5, 1498, 112800, ''),
    ('宋Pro', '宋Pro DM-i 1.5L 220km 超越型', 2026, PLUG, 5, 1498, 122800, ''),
    ('宋Pro', '宋Pro DM-i 1.5L 220km 卓越型', 2026, PLUG, 5, 1498, 130800, ''),
    ('宋Pro', '宋Pro DM-i 飞驰版 1.5L 220km 领先型', 2026, PLUG, 5, 1498, 102900, ''),
    ('宋Pro', '宋Pro DM-i 飞驰版 1.5L 220km 超越型', 2026, PLUG, 5, 1498, 115900, ''),
    ('宋Pro', '宋Pro DM-i 飞驰版 1.5L 301km 超越型', 2026, PLUG, 5, 1498, 118900, ''),
    ('宋Pro', '宋Pro DM-i 飞驰版 1.5L 301km 卓越型', 2026, PLUG, 5, 1498, 132900, ''),
    ('宋L', '宋L DM-i 1.5L 130km 超越型', 2026, PLUG, 5, 1498, 139800, ''),
    ('宋L', '宋L DM-i 1.5L 200km 超越型', 2026, PLUG, 5, 1498, 146800, ''),
    ('宋L', '宋L DM-i 1.5L 200km 卓越型', 2026, PLUG, 5, 1498, 156800, ''),
    ('宋Ultra', '宋Ultra DM-i 1.5L 205km 领先型', 2026, PLUG, 5, 1498, 129900, ''),
    ('宋Ultra', '宋Ultra DM-i 1.5L 205km 超越型', 2026, PLUG, 5, 1498, 139900, ''),
    ('宋Ultra', '宋Ultra DM-i 1.5L 310km 领先型', 2026, PLUG, 5, 1498, 139900, ''),
    ('宋Ultra', '宋Ultra DM-i 1.5L 310km 超越型', 2026, PLUG, 5, 1498, 149900, ''),
    ('宋Ultra', '宋Ultra DM-i 1.5L 310km 卓越型', 2026, PLUG, 5, 1498, 159900, ''),
    ('宋Ultra', '宋Ultra EV 605km 领先型', 2026, PURE, 5, 0, 151900, ''),
    ('宋Ultra', '宋Ultra EV 605km 超越型', 2026, PURE, 5, 0, 159900, ''),
    ('宋Ultra', '宋Ultra EV 710km 超越型', 2026, PURE, 5, 0, 169900, ''),
    ('宋Ultra', '宋Ultra EV 710km 卓越型', 2026, PURE, 5, 0, 179900, ''),
    ('元PLUS', '元PLUS 540km 领先型', 2026, PURE, 5, 0, 119900, ''),
    ('元PLUS', '元PLUS 540km 超越型', 2026, PURE, 5, 0, 129900, ''),
    ('元PLUS', '元PLUS 630km 超越型', 2026, PURE, 5, 0, 142900, ''),
    ('元PLUS', '元PLUS 630km 卓越型', 2026, PURE, 5, 0, 149900, ''),
    ('汉', '汉 EV 智驾版 705km 闪充尊贵型', 2026, PURE, 5, 0, 179800, ''),
    ('汉', '汉 EV 智驾版 705km 闪充尊荣型', 2026, PURE, 5, 0, 187800, ''),
    ('夏', '夏 DM-i 1.5T 100km 进取型', 2026, PLUG, 7, 1497, 206800, 'MPV'),
    ('夏', '夏 DM-i 1.5T 100km 超越型', 2026, PLUG, 7, 1497, 219800, 'MPV'),
    ('唐', '唐 EV 730km 后驱标准版 5座', 2026, PURE, 5, 0, None, '官方未公布指导价（可预订）'),
    ('唐', '唐 EV 830km 后驱高配版 7座', 2026, PURE, 7, 0, None, '官方未公布指导价（可预订）'),
    ('唐', '唐 EV 850km 后驱高配版 5座', 2026, PURE, 5, 0, None, '官方未公布指导价（可预订）'),
    ('大唐', '大唐 EV 800km 后驱激光雷达尊荣型', 2026, PURE, 5, 0, 239900, ''),
    ('大唐', '大唐 DM-i 前驱标准版', 2026, PLUG, 5, 1498, None, '官方未公布指导价（可预订）'),
    ('大唐', '大唐 DM-p 四驱高配版', 2026, PLUG, 5, 1497, None, '官方未公布指导价（可预订）'),
    ('大汉', '大汉 DM 前驱标准型', 2026, PLUG, 5, 1498, None, '官方未公布指导价（可预订）'),
    ('宋Pro', '宋Pro DM-i 1.5L 激光雷达标准版', 2026, PLUG, 5, 1498, None, '官方未公布指导价（可预订）'),
    ('宋Pro', '宋Pro DM-i 1.5L 激光雷达高配版', 2026, PLUG, 5, 1498, None, '官方未公布指导价（可预订）'),
]
# 海洋网：车型库只给了车系与"厂商指导价 x 万起"，逐款价格未核实。
OCEAN = [
    ('海狮07', '海狮07 EV（车系，待选具体配置）', 2026, PURE, 5, 0, 189800, '车系起步指导价 18.98 万起'),
    ('海狮07', '海狮07 DM-i（车系，待选具体配置）', 2026, PLUG, 5, 1497, 169800, '车系起步指导价 16.98 万起'),
    ('海狮06', '海狮06（车系，待选具体配置）', 2026, PURE, 5, 0, 139800, '车系起步指导价 13.98 万起'),
    ('海狮05', '海狮05 EV（车系，待选具体配置）', 2026, PURE, 5, 0, 117800, '车系起步指导价 11.78 万起'),
    ('海狮05', '海狮05 DM-i（车系，待选具体配置）', 2026, PLUG, 5, 1498, 102800, '车系起步指导价 10.28 万起'),
    ('护卫舰07', '护卫舰07（车系，待选具体配置）', 2026, PLUG, 5, 1497, 179800, '车系起步指导价 17.98 万起'),
    ('海豹', '海豹（在售车系，价格未核实）', 2026, PURE, 5, 0, None, '在售车系；指导价未核实，以官网为准'),
    ('海豹06', '海豹06（在售车系，价格未核实）', 2026, PLUG, 5, 1498, None, '在售车系；指导价未核实，以官网为准'),
    ('海豹07', '海豹07（在售车系，价格未核实）', 2026, PLUG, 5, 1498, None, '在售车系；指导价未核实，以官网为准'),
    ('海豚', '海豚（在售车系，价格未核实）', 2026, PURE, 5, 0, None, '在售车系；指导价未核实，以官网为准'),
    ('海鸥', '海鸥（在售车系，价格未核实）', 2026, PURE, 4, 0, None, '在售车系；指导价未核实，以官网为准'),
    ('驱逐舰05', '驱逐舰05（在售车系，价格未核实）', 2026, PLUG, 5, 1498, None, '在售车系；指导价未核实，以官网为准'),
]
NOTES = [
    ['比亚迪车型清单 · 导入用（试用数据，不是真实报价单）'],
    ['生成时间', '2026-09-25'],
    ['用途', '喂给业务助手，让它按表准备"车型目录"新增确认卡（POST /api/vehicle-catalog/entry）'],
    ['数据来源-王朝网', 'https://dealer.yiche.com/100018768/news/202609/1468241855.html（2026-09-25 抓取，价格=厂商指导价）'],
    ['数据来源-海洋网', 'https://newcar.xcar.com.cn/b30/car_t3_o2.htm（2026-09-25 抓取，车系与起步价）'],
    ['口径', '价格取自公开页面上的厂商指导价；未公布指导价的"可预订"车型留空；不含补贴、优惠与地区差异'],
    ['为什么有空白', '电池容量与部分车系价格没有可靠来源，宁可留空也不编造；导入后可在车型页补齐'],
    ['列说明·动力代码', '必须是系统选项之一：electric（纯电）/ plugin_hybrid（插电混动）'],
    ['列说明·编码', '品牌编码固定 BYD；车系编码用拼音缩写（YUANUP/QINL/SONGULTRA…）；车型编码=车系编码-年款-序号，例如 YUANUP-2027-01'],
    ['列说明·排量', '1.5L=1498，1.5T=1497，纯电=0；座位数：轿车/SUV=5，夏 MPV=7，海鸥=4'],
    ['电池容量留空的原因', '没有可靠来源的每款电池容量；系统按 0 存并在车型页补齐，避免编造数值'],
    ['导入建议', '先让助手读表并列出"将新建哪些品牌/车系/车型"，确认分批后再逐张点确认卡；同名先查再建'],
    ['范围', '本表只含比亚迪品牌（王朝网+海洋网）；腾势、方程豹、仰望属集团其他品牌，未列入'],
]


def sheet_xml(rows):
    body = []
    for row_number, row in enumerate(rows, start=1):
        cells = []
        for index, value in enumerate(row):
            column = chr(ord('A') + index)
            reference = '%s%d' % (column, row_number)
            if value is None or value == '':
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append('<c r="%s"><v>%s</v></c>' % (reference, value))
            else:
                cells.append('<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                             % (reference, escape(str(value))))
        body.append('<row r="%d">%s</row>' % (row_number, ''.join(cells)))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData>%s</sheetData></worksheet>' % ''.join(body))


def build(path):
    data = [HEADERS]
    counters = {}
    for series, model, year, power, seats, displacement, price, note in DYNASTY + OCEAN:
        code = SERIES_CODE[series]
        counters[code] = counters.get(code, 0) + 1
        data.append(['比亚迪', BRAND_CODE, series, code, model, '%s-%d-%02d' % (code, year, counters[code]),
                     year, power, 'electric' if power == PURE else 'plugin_hybrid',
                     seats, displacement, None, price, note])
    sheets = [('车型清单', sheet_xml(data)), ('说明与来源', sheet_xml(NOTES))]
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                     + ''.join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1) for i in range(len(sheets)))
                     + '</Types>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                 '</Relationships>')
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                + ''.join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (name, i + 1, i + 1)
                          for i, (name, _) in enumerate(sheets))
                + '</sheets></workbook>')
    workbook_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                     + ''.join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1)
                               for i in range(len(sheets)))
                     + '</Relationships>')
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('_rels/.rels', root_rels)
        archive.writestr('xl/workbook.xml', workbook)
        archive.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
        for index, (_, xml) in enumerate(sheets, start=1):
            archive.writestr('xl/worksheets/sheet%d.xml' % index, xml)
    return path, len(data) - 1


if __name__ == '__main__':
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    written, rows = build(target)
    print('written %s (%d 行数据)' % (written, rows))
