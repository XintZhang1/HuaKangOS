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
HEADERS = ['行号', '品牌', '车系', '车型', '年款', '动力类型', '动力代码', '座位数', '排量(ml)',
           '电池容量(Wh)', '指导价(元)', '备注']
PURE, PLUG = '纯电', '插电混动'
# 电池容量（Wh）：只填能从公开参数页读到的值，读不到留空。纯电车型留空会被系统拒绝
# （VehicleModelInput 要求 electric 必须 battery_wh>0），所以纯电行必须有值。
# 键＝车系 + 车型名里出现的续航/配置片段（取最长匹配）；值为该配置的电池能量。
# 来源（2026-09-25 由三个核对子任务从参数页原文读取，逐条标注）：
#   58汽车 product.58che.com（元UP 飞驰版、秦MAX、元PLUS 630km、汉EV 705km、宋Pro、宋L、宋Ultra）
#   车300 che300.com（秦L 128km）、太平洋汽车 pcauto（秦L 210km、夏、海狮/护卫舰/海豹/海豚/海鸥/驱逐舰05）
BATTERY_BY_SERIES_TOKEN = {
    '元UP': {'301km': 32000, '401km': 45120, '501km': 51130},
    '秦L': {'128km': 15870, '210km': 25280},
    '秦MAX': {'EV 530km': 52868, 'EV 630km': 64315, '230km': 25287, '320km': 34275},
    '宋Pro': {'133km': 18300, '220km': 26600, '301km': 34270},
    '宋L': {'130km': 18300, '200km': 26600},
    '宋Ultra': {'205km': 26600, '310km': 38000, '605km': 69070, '710km': 82700},
    '元PLUS': {'630km': 68547},                      # 540km 各参数页均未见到，留空
    '汉': {'705km': 69070},
    '夏': {'100km': 20390},
    '海狮07': {'DM-i': 26600, 'EV': 71800},
    '海狮06': {'车系': 65280},                        # 2025款 EV 520领航版 65.28 kWh
    '海狮05': {'EV': 50050, 'DM-i': 26628},
    '护卫舰07': {'车系': 18300},                      # 2024款荣耀版 DM-i 100KM 精英型
    '海豹06': {'车系': 15870},
    '海豹07': {'车系': 17600},
    '海豚': {'车系': 45120},
    '海鸥': {'车系': 38880},
    '驱逐舰05': {'车系': 8300},
}


def battery_for(series, model):
    options = BATTERY_BY_SERIES_TOKEN.get(series) or {}
    for token in sorted(options, key=len, reverse=True):
        if token in model:
            return options[token]
    return None
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
    ['列说明·单位', '排量单位毫升（1.5L=1498、1.5T=1497、纯电=0）；电池容量单位 Wh（1 kWh=1000 Wh）；指导价单位元（提交接口时按分，×100）'],
    ['列说明·为什么没有编码', '车型目录的新增接口 POST /api/vehicle-catalog/entry 不接受编码字段（严格模式会拒绝多余字段），品牌/车系/车型编码由系统自动生成'],
    ['车型挂车系由同一次提交完成', 'entry 接口一次提交就带品牌名称+车系名称+车型参数：系统会按名称查找或新建品牌与车系，并写入车型与车系的归属关系，不需要先建车系再挂'],
    ['纯电车型的硬要求', '系统校验：纯电车型排量必须为 0 且电池容量 > 0；燃油车型相反。插混不限'],
    ['为什么还有空白', '2026/2027 款部分配置（尤其"可预订"车型）官方参数未公布，电池容量留空并在备注标注，不编造'],
    ['导入建议', '一次一张确认卡（每行一张）；先让助手读表列出计划，再按行号分批；每张卡确认前核对车型名、年款、动力、电池容量与指导价'],
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
    for number, (series, model, year, power, seats, displacement, price, note) in enumerate(DYNASTY + OCEAN, start=1):
        battery = battery_for(series, model)
        if power == PURE and battery is None:
            note = (note + '；电池容量未查到（纯电必填，导入前需补）').strip('；')
        data.append([number, '比亚迪', series, model, year, power,
                     'electric' if power == PURE else 'plugin_hybrid',
                     seats, displacement, battery, price, note])
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
