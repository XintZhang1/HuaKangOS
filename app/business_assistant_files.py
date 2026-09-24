"""Bounded, memory-only previews of explicitly uploaded files.

No paths are opened, files saved, formulas evaluated, relationships fetched or
model/business commands invoked. The result is untrusted data for staff review.
"""
import csv
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import posixpath
import re
import stat
import unicodedata
import zipfile
import zlib
from xml.etree import ElementTree as ET

from fastapi import HTTPException
from python_multipart import MultipartParser
from python_multipart.multipart import parse_options_header

from . import file_security
from .business_assistant_service import safe_text

LIMITS = {
    'files': 20, 'file_bytes': 5 * 1024 * 1024, 'total_bytes': 20 * 1024 * 1024,
    'request_bytes': 21 * 1024 * 1024, 'rows_per_file': 1000, 'columns': 50,
    'cell_characters': 2000, 'preview_characters_per_file': 1_000_000,
    'preview_characters_total': 2_000_000, 'zip_members': 256,
    'warning_characters_per_file': 250_000, 'warnings_per_file': 6000,
    'zip_expanded_bytes': 25 * 1024 * 1024, 'zip_member_bytes': 8 * 1024 * 1024,
    'zip_ratio': 200,
}
SUPPORTED = {'csv', 'tsv', 'xlsx', 'docx', 'txt'}
SS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'
RID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
SECRET_HEADERS = {'password', 'passwordhash', 'apikey', 'secret', 'token', 'authorization',
    'cookie', 'csrf', 'accesstoken', 'refreshtoken', 'privatekey', 'clientsecret',
    '密码', '口令', '验证码', '密钥', '私钥', '访问令牌', '刷新令牌', '接口密钥', '登录密码'}


class PreviewError(ValueError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def fail(code, message):
    raise PreviewError(code, message)


def clean_text(value):
    # Do not use the assistant's recursive scrub: it intentionally clips lists.
    value = re.sub(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----',
                   '[私钥已隐藏]', value, flags=re.S)
    value = re.sub(r'(?im)^(\s*(?:密码|口令|验证码|密钥|私钥|password|api[_ -]?key|secret|access[_ -]?token|refresh[_ -]?token)\s*[:：=]\s*)[^\r\n]+',
                   r'\1[敏感信息已隐藏]', value)
    return safe_text(value, max(len(value) * 2 + 100, 6000))


class Warnings(list):
    def __init__(self):
        super().__init__()
        self.seen, self.characters = set(), 0

    def append(self, value):
        if value in self.seen:
            return
        if (len(self) >= LIMITS['warnings_per_file']
                or self.characters+len(value) > LIMITS['warning_characters_per_file']):
            fail('warning_limit', '需要核对的特殊单元格过多，请拆分或另存为纯值表格后重试')
        self.seen.add(value)
        self.characters += len(value)
        super().append(value)


def safe_name(name):
    if not isinstance(name, str) or not name or len(name) > 500:
        fail('invalid_name', '文件名无效或过长')
    name = name.replace('\\', '/')
    if name.startswith('/') or ':' in name or any(ord(c) < 32 for c in name):
        fail('invalid_name', '请选择本地文件，不接受绝对路径或网址')
    parts = name.split('/')
    if any(p in {'', '.', '..'} for p in parts):
        fail('invalid_name', '文件名不能包含上级目录或空目录')
    return name, any(p.startswith('.') or p.startswith('~$') for p in parts)


def decode_text(content, warnings):
    try:
        value = content.decode('utf-8-sig', 'strict')
    except UnicodeDecodeError:
        try:
            value = content.decode('gb18030', 'strict')
        except UnicodeDecodeError:
            fail('encoding', '文字编码无法识别，请另存为 UTF-8 后重试')
        warnings.append('按 GB18030 编码读取，请核对中文。')
    if any(ord(c) < 32 and c not in '\t\r\n' for c in value):
        fail('binary_text', '文件包含非文本内容，请另存为纯文本或标准表格')
    return value


def parse_multipart(body, content_type):
    """python-multipart callbacks avoid UploadFile's on-disk spool entirely."""
    if len(body) > LIMITS['request_bytes']:
        raise HTTPException(413, '本次文件总大小超过 20 MiB，请分批选择')
    media, options = parse_options_header(content_type)
    boundary = options.get(b'boundary', b'')
    if media != b'multipart/form-data' or not boundary or len(boundary) > 200:
        raise HTTPException(422, '请选择要读取的文件')
    files, part = [], {}
    names, ended, total = None, False, 0

    def begin():
        part.clear()
        part.update(headers={}, header_name=bytearray(), header_value=bytearray(),
                    data=bytearray(), size=0, digest=hashlib.sha256(), header_bytes=0)

    def header_field(data, start, end):
        part['header_name'].extend(data[start:end])
        check_headers(end-start)

    def header_value(data, start, end):
        part['header_value'].extend(data[start:end])
        check_headers(end-start)

    def check_headers(size):
        part['header_bytes'] += size
        if part['header_bytes'] > 8192:
            raise HTTPException(422, '文件请求头过长')

    def header_end():
        key = bytes(part['header_name']).lower()
        if key in part['headers']:
            raise HTTPException(422, '文件请求头重复')
        part['headers'][key] = bytes(part['header_value'])
        part['header_name'].clear(); part['header_value'].clear()

    def headers_finished():
        disposition, params = parse_options_header(part['headers'].get(b'content-disposition', b''))
        if disposition != b'form-data' or b'content-transfer-encoding' in part['headers']:
            raise HTTPException(422, '文件请求格式不正确')
        field = params.get(b'name')
        if field == b'files' and b'filename' in params:
            if len(files) >= LIMITS['files']:
                raise HTTPException(413, '一次最多选择 20 个文件')
            try:
                part['name'] = params[b'filename'].decode('utf-8', 'strict')
            except UnicodeDecodeError:
                raise HTTPException(422, '文件名编码无效') from None
            part['kind'] = 'file'
        elif field == b'relative_names' and b'filename' not in params:
            if names is not None:
                raise HTTPException(422, '相对文件名不能重复提交')
            part['kind'] = 'names'
        else:
            raise HTTPException(422, '仅支持上传文件和相对文件名，不接受服务器路径')

    def data_received(data, start, end):
        nonlocal total
        block = data[start:end]
        part['size'] += len(block)
        if part['kind'] == 'file':
            total += len(block)
            if total > LIMITS['total_bytes']:
                raise HTTPException(413, '本次文件总大小超过 20 MiB，请分批选择')
            part['digest'].update(block)
            if part['size'] <= LIMITS['file_bytes']:
                part['data'].extend(block)
            else:
                part['data'].clear()
        else:
            if part['size'] > 16384:
                raise HTTPException(422, '相对文件名过长')
            part['data'].extend(block)

    def part_end():
        nonlocal names
        if part['kind'] == 'file':
            files.append({'name': part['name'], 'content': bytes(part['data']),
                'id': part['digest'].hexdigest(), 'oversized': part['size'] > LIMITS['file_bytes']})
        else:
            try:
                names = json.loads(bytes(part['data']).decode('utf-8', 'strict'))
            except (ValueError, UnicodeError):
                raise HTTPException(422, '相对文件名格式不正确') from None
            if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
                raise HTTPException(422, '相对文件名应为文字列表')

    def end():
        nonlocal ended
        ended = True

    parser = MultipartParser(boundary, {'on_part_begin': begin, 'on_header_field': header_field,
        'on_header_value': header_value, 'on_header_end': header_end,
        'on_headers_finished': headers_finished, 'on_part_data': data_received,
        'on_part_end': part_end, 'on_end': end})
    try:
        for start in range(0, len(body), 65536):
            parser.write(body[start:start+65536])
        parser.finalize()
    except HTTPException:
        raise
    except (ValueError, KeyError):
        raise HTTPException(422, '文件请求不完整或格式不正确') from None
    if not ended or not files:
        raise HTTPException(422, '没有收到完整文件，请重新选择')
    if names is not None:
        if len(names) != len(files):
            raise HTTPException(422, '相对文件名数量与文件数量不一致')
        for file, name in zip(files, names):
            file['name'] = name
    return files


def xml_root(raw):
    # Removing NUL also catches UTF-16/32 declarations before any XML expansion.
    if re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b', raw.replace(b'\x00', b''), re.I):
        fail('unsafe_xml', '文件包含不支持的 XML 声明，请另存为标准文档')
    try:
        return ET.fromstring(raw)
    except (ET.ParseError, LookupError, ValueError):
        fail('invalid_xml', '文档结构损坏，请另存后重试')


def read_package(content, kind, warnings):
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > LIMITS['zip_members']:
                fail('zip_limit', '文档内部文件过多，请拆分文档')
            total, contents = 0, {}
            for member in members:
                name = member.filename
                if (name.startswith(('/', '\\')) or '\\' in name or ':' in name
                        or '..' in name.split('/') or name in contents or '\x00' in name):
                    fail('unsafe_zip', '文档内部路径无效或重复')
                if member.flag_bits & 1 or stat.S_ISLNK(member.external_attr >> 16):
                    fail('unsafe_zip', '不支持加密文档或链接文件')
                if member.is_dir():
                    continue
                total += member.file_size
                if (member.file_size > LIMITS['zip_member_bytes'] or total > LIMITS['zip_expanded_bytes']
                        or member.file_size > max(1, member.compress_size) * LIMITS['zip_ratio']):
                    fail('zip_limit', '文档展开后过大，请拆分或另存后重试')
                if any(s in name.lower() for s in ('vbaproject', '/activex/', '/embeddings/', 'macrosheets/')):
                    fail('macros', '不支持宏或嵌入程序，请另存为不含宏的文档')
                raw = archive.read(member)
                if len(raw) != member.file_size:
                    fail('unsafe_zip', '文档内部大小不一致')
                contents[name] = xml_root(raw) if name.endswith(('.xml', '.rels')) else None
            types = contents.get('[Content_Types].xml')
            if types is None:
                fail('invalid_package', '不是标准 Office 文档')
            if any('macroenabled' in e.attrib.get('ContentType', '').lower()
                   or 'vba' in e.attrib.get('ContentType', '').lower() for e in types):
                fail('macros', '不支持宏，请另存为不含宏的文档')
            for name, root in contents.items():
                if kind == 'xlsx' and name.startswith('xl/externalLinks/'):
                    fail('external_links', '表格包含外部链接，请移除链接后重试')
                if root is not None and name.endswith('.rels'):
                    for relation in root:
                        if relation.attrib.get('TargetMode', '').lower() == 'external':
                            if kind == 'xlsx':
                                fail('external_links', '表格包含外部链接，请移除链接后重试')
                            warnings.append('外部链接未读取。')
            return contents
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, zlib.error):
        fail('invalid_package', '文档损坏、加密或压缩格式不支持')


class Preview:
    def __init__(self, result):
        self.result, self.rows, self.characters = result, 0, 0

    def cell(self, value):
        if len(value) > LIMITS['cell_characters']:
            fail('cell_limit', '单元格文字超过 2000 字，请拆分后重试')
        self.characters += len(value)
        if self.characters > LIMITS['preview_characters_per_file']:
            fail('preview_limit', '文件预览内容过多，请拆分后重试')
        return clean_text(value)

    def table(self, name, source):
        source = [(n, values) for n, values in source if values]
        if not source:
            return
        width = max(len(values) for _, values in source)
        if width > LIMITS['columns']:
            fail('column_limit', '表格超过 50 列，请拆分后重试')
        self.rows += len(source)-1
        if self.rows > LIMITS['rows_per_file']:
            fail('row_limit', '文件数据超过 1000 行，请分批选择')
        header = source[0][1] + [''] * (width-len(source[0][1]))
        columns = [self.cell(v) if v else f'列{i+1}' for i, v in enumerate(header)]
        if any(not v for v in header):
            self.result['warnings'].append(f'{name}：空表头已显示为列号，请核对。')
        if len(set(columns)) < len(columns):
            self.result['warnings'].append(f'{name}：存在同名列，请按列顺序核对。')
        secret = {i for i, v in enumerate(header)
                  if re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', v).lower()) in SECRET_HEADERS}
        for index in sorted(secret):
            self.result['redacted_columns'].append({'table': name, 'column': index+1,
                                                    'column_name': columns[index]})
        rows = []
        for number, values in source[1:]:
            values = values + [''] * (width-len(values))
            checked = [self.cell(v) for v in values]
            rows.append({'row_number': number, 'values': [
                '[敏感信息已隐藏]' if i in secret and v else v for i, v in enumerate(checked)]})
        self.result['tables'].append({'name': clean_text(name), 'columns': columns, 'rows': rows})

    def text(self, value):
        self.characters += len(value)
        if self.characters > LIMITS['preview_characters_per_file']:
            fail('preview_limit', '文件文字过多，请拆分后重试')
        self.result['text'] = clean_text(value)


def csv_preview(content, kind, preview):
    raw = decode_text(content, preview.result['warnings'])
    delimiter = '\t' if kind == 'tsv' else ','
    source, number = [], 1
    try:
        reader = csv.reader(io.StringIO(raw, newline=''), delimiter=delimiter, strict=True)
        for values in reader:
            if len(values) > LIMITS['columns']:
                fail('column_limit', '表格超过 50 列，请拆分后重试')
            if any(len(v) > LIMITS['cell_characters'] for v in values):
                fail('cell_limit', '单元格文字超过 2000 字，请拆分后重试')
            if any(v != '' for v in values):
                source.append((number, values))
                if len(source) > LIMITS['rows_per_file']+1:
                    fail('row_limit', '文件数据超过 1000 行，请分批选择')
            number = reader.line_num+1
    except csv.Error:
        fail('invalid_csv', '表格分隔符或引号不完整，请另存为标准 CSV 或 TSV')
    preview.table('数据', source)
    preview.result['warnings'].append('使用制表符分隔。' if kind == 'tsv' else '使用英文逗号分隔。')


def col_index(reference):
    match = re.fullmatch(r'([A-Z]+)([1-9][0-9]*)', reference)
    if not match:
        fail('invalid_cell', '表格单元格位置无效')
    index = 0
    for letter in match[1]:
        index = index*26+ord(letter)-64
    if index > LIMITS['columns']:
        fail('column_limit', '表格超过 50 列，请拆分后重试')
    return index-1, int(match[2])


def xlsx_preview(content, preview):
    warnings = preview.result['warnings']
    package = read_package(content, 'xlsx', warnings)
    book, relationships = package.get('xl/workbook.xml'), package.get('xl/_rels/workbook.xml.rels')
    if book is None or relationships is None:
        fail('invalid_package', '缺少工作簿信息')
    targets = {r.attrib.get('Id'): r.attrib.get('Target', '') for r in relationships}
    strings = package.get('xl/sharedStrings.xml')
    shared = []
    if strings is not None:
        shared = [''.join(t.text or '' for child in item for t in
                          ([child] if child.tag == SS+'t' else child.findall(SS+'t') if child.tag == SS+'r' else []))
                  for item in strings]
    styles = package.get('xl/styles.xml')
    formats, style_ids = {}, []
    if styles is not None:
        formats = {int(x.attrib['numFmtId']): x.attrib.get('formatCode', '')
                   for x in styles.findall(f'{SS}numFmts/{SS}numFmt')}
        style_ids = [int(x.attrib.get('numFmtId', '0')) for x in styles.findall(f'{SS}cellXfs/{SS}xf')]
    properties = book.find(SS+'workbookPr')
    date1904 = properties is not None and properties.attrib.get('date1904') in {'true', '1'}
    sheets = book.findall(f'{SS}sheets/{SS}sheet')
    if len(sheets) > LIMITS['zip_members'] or len({s.attrib.get(RID) for s in sheets}) != len(sheets):
        fail('invalid_package', '工作表过多或位置重复')
    for sheet in sheets:
        name = sheet.attrib.get('name', '工作表')
        if not name or len(name) > 100 or any(ord(c) < 32 for c in name):
            fail('invalid_sheet', '工作表名称无效或过长')
        if sheet.attrib.get('state', 'visible') != 'visible':
            warnings.append(f'{name}：隐藏工作表未读取。'); continue
        target = targets.get(sheet.attrib.get(RID), '')
        path = target.lstrip('/') if target.startswith('/xl/') else posixpath.normpath('xl/'+target)
        if not path.startswith('xl/worksheets/') or '..' in target.split('/') or path not in package:
            fail('invalid_package', '工作表位置无效')
        root = package[path]
        if root is None or root.tag != SS+'worksheet':
            fail('invalid_package', '工作表格式不正确')
        hidden_cols = set()
        for col in root.findall(f'{SS}cols/{SS}col'):
            if col.attrib.get('hidden') in {'1', 'true'}:
                low, high = int(col.attrib.get('min', 0)), int(col.attrib.get('max', 0))
                hidden_cols.update(range(max(low, 1)-1, min(high, LIMITS['columns'])))
        if hidden_cols:
            warnings.append(f'{name}：隐藏列未读取，保留空列位置。')
        source, seen_rows = [], set()
        for row in root.findall(f'{SS}sheetData/{SS}row'):
            number = int(row.attrib.get('r', len(source)+1))
            if number < 1 or number in seen_rows:
                fail('invalid_cell', '表格行号无效或重复')
            seen_rows.add(number)
            if row.attrib.get('hidden') in {'1', 'true'}:
                warnings.append(f'{name}第{number}行：隐藏行未读取。'); continue
            values, seen_cells, notes = [], set(), {}
            def note(label):
                notes.setdefault(label, []).append(reference)
            for cell in row.findall(SS+'c'):
                reference = cell.attrib.get('r', '')
                index, cell_row = col_index(reference)
                if cell_row != number or index in seen_cells:
                    fail('invalid_cell', '表格单元格位置无效或重复')
                seen_cells.add(index)
                if index in hidden_cols:
                    continue
                value = cell.findtext(SS+'v', '')
                kind = cell.attrib.get('t', 'n')
                if cell.find(SS+'f') is None and len(value) > LIMITS['cell_characters']:
                    fail('cell_limit', '单元格文字超过 2000 字，请拆分后重试')
                if cell.find(SS+'f') is not None:
                    value = ''; note('公式留空，未使用缓存值。')
                elif kind == 's':
                    pointer = int(value)
                    if pointer < 0 or pointer >= len(shared):
                        fail('invalid_cell', '表格共享文字位置无效')
                    value = shared[pointer]
                elif kind == 'inlineStr':
                    value = ''.join(t.text or '' for t in cell.findall(f'{SS}is//{SS}t'))
                elif kind == 'b':
                    if value not in {'0', '1'}:
                        fail('invalid_cell', '表格真假值无效')
                    value = 'TRUE' if value == '1' else 'FALSE'
                elif kind == 'e':
                    value = ''; note('错误单元格留空。')
                elif kind == 'n' and value:
                    number_value = Decimal(value)
                    if not number_value.is_finite() or abs(number_value.adjusted()) > LIMITS['cell_characters']:
                        fail('invalid_cell', '表格包含无效数值')
                    style = int(cell.attrib.get('s', 0))
                    if style < 0 or style_ids and style >= len(style_ids):
                        fail('invalid_cell', '表格数字格式无效')
                    format_id = style_ids[style] if style_ids else 0
                    format_code = formats.get(format_id, '')
                    if re.fullmatch('0{2,50}', format_code) and number_value == number_value.to_integral():
                        integer = int(number_value)
                        value = ('-' if integer < 0 else '')+str(abs(integer)).zfill(len(format_code))
                    elif format_id in {14, 15, 16, 17, 22} and (date1904 or number_value != 60):
                        # ISO output is explicit and does not depend on OS locale.
                        serial = float(number_value)
                        epoch = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 30)
                        if not date1904 and 0 < serial < 60:
                            serial += 1
                        date = epoch+timedelta(days=serial)
                        value = date.isoformat(sep=' ', timespec='seconds')
                        note('日期已转为年月日和时间，请核对。')
                    elif format_id not in {0, 1, 2, 3, 4}:
                        note('保留原数值，未套用显示格式，请核对。')
                elif kind not in {'str', 'd', 'n'}:
                    fail('invalid_cell', '表格单元格类型不支持')
                if len(value) > LIMITS['cell_characters']:
                    fail('cell_limit', '单元格文字超过 2000 字，请拆分后重试')
                values.extend([''] * (index+1-len(values)))
                values[index] = value
            for label, references in notes.items():
                warnings.append(f'{name}!'+', '.join(references)+'：'+label)
            if any(v != '' for v in values) or notes:
                source.append((number, values))
                if len(source) + preview.rows > LIMITS['rows_per_file']+1:
                    fail('row_limit', '文件数据超过 1000 行，请分批选择')
        preview.table(name, source)


def word_text(element):
    if element.tag in {W+'del', W+'instrText'}:
        return ''
    if element.tag == W+'r' and element.find(f'{W}rPr/{W}vanish') is not None:
        return ''
    if element.tag == W+'t':
        return element.text or ''
    if element.tag in {W+'tab', W+'br', W+'cr'}:
        return '\t' if element.tag == W+'tab' else '\n'
    return ''.join(word_text(child) for child in element)


def docx_preview(content, preview):
    package = read_package(content, 'docx', preview.result['warnings'])
    root = package.get('word/document.xml')
    if root is None:
        fail('invalid_package', '缺少文档正文')
    body = root.find(W+'body')
    if body is None:
        fail('invalid_package', '缺少文档正文')
    paragraphs, table_number = [], 0
    for element in body:
        if element.tag == W+'p':
            paragraphs.append(word_text(element))
        elif element.tag == W+'tbl':
            table_number += 1
            source = []
            for i, row in enumerate(element.findall(W+'tr'), 1):
                values = []
                for cell in row.findall(W+'tc'):
                    if cell.find(W+'tbl') is not None:
                        fail('nested_table', '暂不支持嵌套表格，请拆分为普通表格')
                    if cell.find(f'{W}tcPr/{W}gridSpan') is not None or cell.find(f'{W}tcPr/{W}vMerge') is not None:
                        fail('merged_table', '文档表格存在合并单元格，请拆分为普通表格后重试')
                    values.append('\n'.join(word_text(p) for p in cell.findall(W+'p')))
                source.append((i, values))
            preview.table(f'表格{table_number}', source)
    preview.text('\n'.join(paragraphs))
    if next(root.iter(W+'drawing'), None) is not None or next(root.iter(W+'pict'), None) is not None:
        preview.result['warnings'].append('图片未识别，请单独填写其中的信息。')
    if next(root.iter(W+'fldChar'), None) is not None or next(root.iter(W+'fldSimple'), None) is not None:
        preview.result['warnings'].append('文档字段未计算，请核对显示内容。')


def preview_file(upload):
    result = {'id': upload['id'], 'name': clean_text(upload['name']), 'format': '',
              'tables': [], 'text': '', 'warnings': Warnings(), 'error': None, 'redacted_columns': []}
    try:
        name, hidden = safe_name(upload['name'])
        kind = name.rsplit('.', 1)[-1].lower() if '.' in name.rsplit('/', 1)[-1] else ''
        result['format'] = kind
        if upload.get('oversized') or len(upload['content']) > LIMITS['file_bytes']:
            fail('file_limit', '文件超过 5 MiB，请拆分后重试')
        if hidden:
            result['warnings'].append('隐藏文件或临时文件未读取。')
            return result
        if kind not in SUPPORTED:
            fail('unsupported', '暂不支持此格式，请使用 CSV、TSV、XLSX、DOCX 或 TXT；图片和扫描件需先整理为文字')
        mode = file_security.policy_mode()
        if mode == 'quarantine':
            fail('quarantine', '当前文件扫描设置为隔离，请联系管理员启用扫描后重试')
        if mode == 'clamav':
            settings = file_security.settings
            scanned = file_security.scan_clamav(upload['content'], settings.clamav_host,
                                                settings.clamav_port, settings.clamav_timeout_seconds)
            if (scanned.state, scanned.engine, scanned.code) != ('clean', 'clamav', 'clean'):
                fail('scan_failed', file_security.MESSAGES.get(scanned.code, '文件扫描未通过，请稍后重试'))
        else:
            result['warnings'].append('仅完成结构检查，未查毒。')
        preview = Preview(result)
        if kind in {'csv', 'tsv'}:
            csv_preview(upload['content'], kind, preview)
        elif kind == 'xlsx':
            xlsx_preview(upload['content'], preview)
        elif kind == 'docx':
            docx_preview(upload['content'], preview)
        else:
            preview.text(decode_text(upload['content'], result['warnings']))
        result['warnings'].append('预览仅供核对，尚未录入业务，也不作为凭据或签名认证。')
    except HTTPException as exc:
        result['error'] = {'code': 'scan_policy', 'message': str(exc.detail)}
    except PreviewError as exc:
        result['error'] = {'code': exc.code, 'message': exc.message}
    except (ValueError, OverflowError, InvalidOperation, IndexError, KeyError, RecursionError):
        result['error'] = {'code': 'invalid_document', 'message': '文档结构或数据无效，请另存为标准文档后重试'}
    if result['error']:
        result['tables'], result['text'], result['redacted_columns'], result['warnings'] = [], '', [], []
    # Warnings can contain source sheet names; never relay a supplied key.
    result['warnings'] = list(dict.fromkeys(clean_text(w) for w in result['warnings']))
    return result


def preview_multipart(body, content_type):
    files, total = [], 0
    for upload in parse_multipart(body, content_type):
        result = preview_file(upload)
        size = len(result['text']) + sum(len(w) for w in result['warnings']) + sum(len(c) for t in result['tables'] for c in t['columns']) + sum(
            len(v) for t in result['tables'] for r in t['rows'] for v in r['values'])
        if total+size > LIMITS['preview_characters_total']:
            result.update(tables=[], text='', redacted_columns=[],
                          error={'code': 'preview_total_limit', 'message': '本次预览文字过多，请分批选择'})
        else:
            total += size
        files.append(result)
    return {'files': files, 'limits': dict(LIMITS)}
