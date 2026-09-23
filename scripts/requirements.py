"""Validate and render the original 193 requirements without inflating acceptance.

Run `python scripts/requirements.py check` after each delivery. The JSON register
is the editable source of tracking status; source wording and IDs stay stable.
"""
from collections import Counter
import ast
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / 'docs' / 'requirements.json'
OUTPUT = ROOT / 'docs' / '需求验收台账.md'
IMPLEMENTATION = {'已实现', '部分', '待开发'}
VERIFICATION = {'未验证', '通过', '未通过'}


def read_register():
    register = json.loads(REGISTER.read_text(encoding='utf-8'))
    rows = register['requirements']
    assert len(rows) == 193, '原始需求应为193项'
    assert len({row['id'] for row in rows}) == 193, '需求编号重复'
    assert [row['id'] for row in rows] == [f'HK-{n:03}' for n in range(1,194)], '稳定需求编号或顺序被改变'
    source = ROOT / register['source']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == register['source_sha256'], '源需求变更，须显式评审后更新基线'
    with zipfile.ZipFile(source) as archive:
        source_text = re.sub(r'\s+', '', ''.join(ET.fromstring(archive.read('word/document.xml')).itertext()))
    parsed_tests = {}
    for row in rows:
        assert re.sub(r'\s+', '', row['title']) in source_text, f"{row['id']}标题未定位到原始需求表"
        assert row['implementation'] in IMPLEMENTATION, row['id']
        for stage in ('automated', 'business', 'production'):
            assert row['validation'][stage]['status'] in VERIFICATION, row['id']
            if row['validation'][stage]['status'] == '通过':
                assert row['validation'][stage]['evidence'], f"{row['id']}缺少{stage}证据"
        for reference in row['implementation_refs']:
            assert (ROOT / reference).is_file(), f"{row['id']}实现引用不存在: {reference}"
        for reference in row['test_refs']:
            assert (ROOT / reference.split('::')[0]).is_file(), f"{row['id']}测试引用不存在: {reference}"
            path, *selectors = reference.split('::')
            if selectors:
                if path not in parsed_tests:
                    parsed_tests[path] = ast.parse((ROOT/path).read_text(encoding='utf-8-sig')).body
                body = parsed_tests[path]
                for selector in selectors:
                    name = selector.split('[')[0]
                    node = next((n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name), None)
                    assert node is not None, f"{row['id']}测试场景引用不存在: {reference}"
                    body = node.body
    return register


def render(register):
    lines = ['# huakangos 需求验收台账', '',
             '原始功能清单与实现、自动验证、业务验收、正式启用分别追踪。历史“已实现”不是本轮验收通过；实现引用仅用于定位，不证明范围完整。', '',
             '来源为 `原始功能需求表.docx`；稳定编号按首次登记顺序分配，后续不得重新排序编号。维护 `requirements.json` 后执行 `python scripts/requirements.py render`。', '',
             '| 编号 | 模块 / 分组 | 原始条目 | 实现 | 自动验证 | 业务验收 | 正式启用 | 当前范围与缺口 | 实现与用例定位 |',
             '|---|---|---|---|---|---|---|---|---|']
    for row in register['requirements']:
        values = [row['id'], row['module']+' / '+row['group'], row['title'], row['implementation'],
                  *(row['validation'][stage]['status'] for stage in ('automated', 'business', 'production')), row['notes'],
                  '<br>'.join('['+ref+'](../'+ref.split('::')[0]+')' for ref in row['implementation_refs']+row['test_refs']) or '待建立场景与用例']
        lines.append('|'+'|'.join(str(v).replace('|', '／').replace('\n', ' ') for v in values)+'|')
    lines += ['', '## 需求边界与验证层次', '',
              '以原始功能需求表与用户明确修订为准；最新范围核对见《原始需求范围复核》。集团会员仅记账，不建设集团实际资金清算或门店合作关系审批。跨店原单与逐件附件只按明确批准范围读取。实现、自动回归、本机浏览器/数据库验证、公司业务验收分别记录，不相互代替。', '']
    return '\n'.join(lines)


def render_coverage(register):
    rows=register['requirements'];counts=Counter(row['implementation'] for row in rows)
    lines=['# 原始需求逐项覆盖表','',
        '当前追踪源为 `requirements.json`，以 HK 编号保持原条目含义。实现状态不代表自动验证、公司验收或正式启用通过；细分状态和代码/用例定位见《需求验收台账》。','',
        '原交接基线：48 已实现、77 部分、68 待开发。以下为建设中实际范围；不得将条目数作为工期或完成率。','']
    previous=None
    for row in rows:
        if row['module']!=previous:
            previous=row['module'];lines += ['## '+previous,'','| 编号 | 原表分组 | 原表条目 | 实现 | 当前范围与缺口 |','|---|---|---|---|---|']
        lines.append('|'+ '|'.join(str(row[k]).replace('|','／').replace('\n',' ') for k in ('id','group','title','implementation','notes'))+'|')
    lines += ['','## 范围统计','',f"共193项：已实现{counts['已实现']}；部分{counts['部分']}；待开发{counts['待开发']}。尚未取得公司业务验收或正式启用确认。",'',
        '原需求与用户明确修订优先于旧开发计划。会员中心只记账；集团实际资金清算和门店合作关系审批不进入缺口。真实浏览器和PostgreSQL的已执行/待验收状态以当前《验收与限制》为准，不用历史结果替代。条目数量不是完成率；最新范围复核见《原始需求范围复核》。','']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='huakangos 需求基线校验')
    parser.add_argument('command', choices=['check', 'render', 'audit'])
    parser.add_argument('--checkpoint', help='audit 输出检查点，默认读取 CHECKPOINT_STATUS.json')
    args = parser.parse_args()
    register = read_register()
    expected = render(register)
    coverage=render_coverage(register)
    counts=json.dumps({'source_items':193,'baseline_counts':dict(Counter(r['baseline_implementation'] for r in register['requirements'])),
        'counts':dict(Counter(r['implementation'] for r in register['requirements']))},ensure_ascii=False,indent=2)+'\n'
    if args.command == 'audit':
        checkpoint = args.checkpoint or json.loads((ROOT/'CHECKPOINT_STATUS.json').read_text(encoding='utf-8'))['checkpoint']
        assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', checkpoint), '检查点名称无效'
        audit = {'checkpoint': checkpoint, 'source_sha256': register['source_sha256'],
                 'method': '逐项检查原文标题、稳定编号、实现文件、测试文件与明确场景定位；不是逐项业务验收或覆盖率证明。',
                 'excluded_extensions': ['集团会员中心实际资金清算和支付到账审批', '直营门店合作关系准入审批'],
                 'requirements': [{'id': r['id'], 'title': r['title'], 'source_title_verified': True,
                                   'implementation': r['implementation'], 'implementation_refs_verified': r['implementation_refs'],
                                   'test_refs_verified': r['test_refs'], 'current_scope_and_limits': r['notes'],
                                   'validation': r['validation']} for r in register['requirements']]}
        (ROOT/'docs'/('需求逐项核对-'+checkpoint+'.json')).write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    elif args.command == 'render':
        OUTPUT.write_text(expected, encoding='utf-8')
        (ROOT/'docs/需求覆盖表.md').write_text(coverage,encoding='utf-8')
        (ROOT/'docs/coverage.json').write_text(counts,encoding='utf-8')
    else:
        assert OUTPUT.read_text(encoding='utf-8') == expected, '台账与JSON不同步，请重新render'
        assert (ROOT/'docs/需求覆盖表.md').read_text(encoding='utf-8')==coverage,'覆盖表与JSON不同步'
        assert (ROOT/'docs/coverage.json').read_text(encoding='utf-8')==counts,'覆盖计数与JSON不同步'
    print(json.dumps({'requirements': len(register['requirements']), 'implementation': dict(Counter(r['implementation'] for r in register['requirements']))}, ensure_ascii=False))


if __name__ == '__main__':
    main()
