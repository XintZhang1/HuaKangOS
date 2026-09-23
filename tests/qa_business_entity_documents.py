"""Synthetic layout QA using exact production builders and the bundled document runtime.

Run with the Python returned by load_workspace_dependencies. No app database is
opened. Source builders are compiled from their AST to avoid loading application
dependencies into the document runtime; their bodies are not copied or modified.
Use --renderer for the documents skill's render_docx.py and put native soffice.exe
and Poppler on PATH. Output is private synthetic evidence, never company approval.
"""
import argparse,ast,hashlib,io,json,subprocess,sys,tempfile
from pathlib import Path
from docx import Document
from docx.shared import Cm,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parents[1]
FIELDS=('经营主体法定名称','主体识别号','登记地址','主体资料版本编号')

def builder(module):
    path=ROOT/'app'/module;text=path.read_text(encoding='utf-8');tree=ast.parse(text)
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_docx')
    scope=dict(globals());scope['ENTITY_FIELDS']=FIELDS
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(path),'exec'),scope)
    return scope['build_docx'],hashlib.sha256(text.encode()).hexdigest()

def snapshots(long):
    legal={'经营主体法定名称':(('纯合成经营主体名称用于确认文字换行及文档分页的有限责任公司'*8)[:180] if long else '纯合成华慷测试经营有限公司'),
        '主体识别号':'SYNTHETIC000000001','登记地址':('纯合成测试市示例区文档测试路一百八十号资料核验办公楼，仅供版式验证。'*5 if long else '纯合成测试市示例路一号'),
        '主体资料版本编号':712}
    base={'单据编号':'HK-DOC-QA-'+('LONG' if long else 'SHORT'),'门店':'纯合成门店','客户':'纯合成文档客户','联系电话':'13900000000',**legal}
    sales={**base,'报价版本':2,'报价校验摘要':'a1b2c3d4'*8,'品牌 / 车系':'合成品牌 / 城市车系','订购车型':'合成舒适版','车型目录编码':'SYNTH-VEHICLE-001',
        '车型资料版本':3,'车型参数':'2026 年 / 纯电动 / 5 座','车架号':'LSYNTHETIC0000001','车辆约定金额（元）':'128000.01','预计交付日期':'2026-09-30','本版确认有效期':'2026-09-25',
        '另单办理服务':'精品加装、代办服务','金额口径':'车辆价款不含另单确认的精品加装、保险和代办费用；配套服务须分别批准和客户确认。',
        '本版约定':'\n'.join(f'{i+1}. 本项为纯合成客户约定：经办人核对本版车型、车架号与交付安排。变更须重新确认相应版本，文件中的条款不代替实车交接或真实收款。' for i in range(18 if long else 1))}
    repair={**base,'车型':'合成车型','车架号':'LSYNTHETIC0000001','车牌号':'合成测123','约定金额（元）':'109.97','预计办理日期':'2026-09-22',
        '办理内容':'\n'.join(f'{i+1}. 合成维修项目：检查连接固定件，按获客户确认的版本施工，并分别记录原领料、实际退料及质检结果。此处文字只用于长单分页校验。' for i in range(16 if long else 1))}
    retail={**base,'报价内容':'请核对本版套餐组成及分摊金额，授权、安装、交付和款项由各岗位分别确认。','套餐名称':'纯合成精品原价分摊套餐','套餐版本':'SYNTH-KIT 第 3 版',
        '购买套数':'1','每套成交额（元）':'99.97','本单合计（元）':'99.97','退货与安装规则':'商品按原单冻结分摊退货；已实际履约的安装费按原明确规则保留。'}
    for i in range(24 if long else 2):retail[f'商品 {i+1}']=f'SYNTH-{i+1:03d} · 合成车内用品；数量 0.333 件；套餐商品分摊 3.00 元'
    retail['安装 1']='INSTALL-QA · 合成安装；套餐安装分摊 0.50 元'
    retail['每套成交额（元）']=retail['本单合计（元）']='72.50' if long else '6.50'
    for i in range(5 if long else 1):retail[f'套餐补充条款 {i+1}']='原单部分退货须核对商品实物状态、数量和原分摊金额，退款追溯原款，不把代缴、内部清算或尚未执行的业务愿望当作实际收支。'
    return sales,repair,retail

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--renderer',type=Path)
    args=parser.parse_args();out=args.output or Path(tempfile.mkdtemp(prefix='huakangos-entity-docqa-'));out.mkdir(parents=True,exist_ok=True)
    modules=['sales_quote_documents.py','flow_documents.py','retail_bundle_documents.py'];names=['sales','repair','retail'];titles=['车辆订购确认书','维修项目确认单','精品套餐报价确认单']
    manifest={'synthetic_only':True,'company_template_approved':False,'bundled_python':sys.executable,'documents':[]}
    for long in (False,True):
        for name,module,title,info in zip(names,modules,titles,snapshots(long)):
            build,source_sha=builder(module);content=build(info,title,'本单经营主体：{{经营主体法定名称}}。\n请双方核对本单记载内容后签署，实际收支与履约分别以原业务事实为准。',True,4)
            path=out/(name+('_long' if long else '_short')+'.docx');path.write_bytes(content)
            record={'path':str(path),'source_module':module,'source_sha256':source_sha,'sha256':hashlib.sha256(content).hexdigest(),'legal_name_length':len(info[FIELDS[0]])}
            if args.renderer:
                target=out/path.stem;result=subprocess.run([sys.executable,str(args.renderer),str(path),'--output_dir',str(target),'--emit_pdf'],text=True,capture_output=True,timeout=100)
                if result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
                record['pages']=[str(p) for p in sorted(target.glob('page-*.png'))]
                if not record['pages']:raise RuntimeError('Renderer produced no pages for '+path.name)
            manifest['documents'].append(record);print(path.name+' '+str(len(record.get('pages',[])))+' pages',flush=True)
    (out/'acceptance.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print(out,flush=True)

if __name__=='__main__':main()
