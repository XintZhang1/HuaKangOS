"""凭据类别一致性检查：前后端声明的类别都必须是同一词表里的键。

前端约定：file_category 的“取值”位置只写词表里的类别字面量；动作键只出现在 ? 之前的条件里。
"""
import io, re, sys
from pathlib import Path
sys.path.insert(0, str(Path('E:/HuaKangOS')))
from app.flow_specs import UPLOAD_CATEGORY_LABELS, SPECS_V1, SPECS_V2

KNOWN = set(UPLOAD_CATEGORY_LABELS)
problems = []
declared = 0
for name, spec in list(SPECS_V1.items()) + list(SPECS_V2.items()):
    for action in spec.get('actions', []):
        for field in action.fields:
            cat = field.get('file_category')
            if not cat:
                continue
            declared += 1
            for key in (cat if isinstance(cat, (list, tuple)) else (cat,)):
                if key not in KNOWN:
                    problems.append(f'{name}.{action.key}.{field["key"]} -> 未知类别 {key}')
print('后端声明类别字段:', declared)


def expression_at(text, start):
    """从 file_category: 之后取到平衡的表达式（忽略字符串与括号里的逗号）。"""
    depth = 0
    quote = None
    i = start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in '\'"`':
            quote = ch
        elif ch in '([{':
            depth += 1
        elif ch in ')]}':
            if depth == 0:
                break
            depth -= 1
        elif ch == ',' and depth == 0:
            break
        elif ch == '\n':
            break
        i += 1
    return text[start:i]


def split_ternary(expr):
    depth = 0
    quote = None
    for index, ch in enumerate(expr):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in '\'"`':
            quote = ch
        elif ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif ch == '?' and depth == 0:
            rest = expr[index + 1:]
            d2 = 0
            q2 = None
            for j, c2 in enumerate(rest):
                if q2:
                    if c2 == q2:
                        q2 = None
                    continue
                if c2 in '\'"`':
                    q2 = c2
                elif c2 in '([{':
                    d2 += 1
                elif c2 in ')]}':
                    d2 -= 1
                elif c2 == ':' and d2 == 0:
                    return rest[:j], rest[j + 1:]
            problems.append('条件表达式缺少取值分支: ' + expr.strip()[:70])
            return None, None
    return None, expr


front_values = set()
for path in sorted(Path('E:/HuaKangOS/web').glob('*.js')):
    text = io.open(path, encoding='utf-8').read()
    for match in re.finditer(r'file_category\s*:', text):
        expr = expression_at(text, match.end()).strip()
        yes, no = split_ternary(expr)
        values = [no] if yes is None else [yes, no]
        for value in values:
            if value is None:
                continue
            for key in re.findall(r"'([a-z_]+)'", value):
                front_values.add(key)

unknown = sorted(k for k in front_values if k not in KNOWN)
if unknown:
    problems.append('前端取值位置出现词表外类别: ' + ', '.join(unknown))
print('前端声明的类别值:', sorted(front_values))

if problems:
    print('PROBLEMS:')
    for item in problems:
        print(' -', item)
    sys.exit(1)
print('凭据类别一致性检查: PASS')