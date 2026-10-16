"""Bounded XLS extraction through xlrd; no Excel process, macros or link refresh.

The source contract matches XLSX extraction: original cell addresses and values,
visible rows, merged ranges and cell notes. xlrd exposes stored formula results,
not formula expressions; this reader never computes or invents an expression.
"""
import io
import json
import struct
from decimal import Decimal

from fastapi import HTTPException
import xlrd
from xlrd.compdoc import CompDocError
from xlrd.formula import cellname


def _value(cell):
    if cell.ctype in {xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK}:
        return ''
    if cell.ctype == xlrd.XL_CELL_ERROR:
        return xlrd.error_text_from_code[cell.value]
    if cell.ctype in {xlrd.XL_CELL_NUMBER, xlrd.XL_CELL_DATE}:
        # Retain the Excel numeric value, including date serials, just as the
        # XLSX reader does. No display rounding or business-money arithmetic.
        number = Decimal(str(cell.value))
        if not number.is_finite():
            raise ValueError()
        return format(number, 'f')
    return str(cell.value)


def legacy_spreadsheet_source(content):
    """Return the visible legacy workbook as the existing source JSON contract."""
    try:
        if not content or len(content) > 10 * 1024 * 1024:
            raise ValueError()
        # Diagnostics may include source content; keep them out of server logs.
        with xlrd.open_workbook(file_contents=content, formatting_info=True,
                on_demand=True, ragged_rows=True, logfile=io.StringIO()) as workbook:
            result, count, characters = [], 0, 0
            for sheet_index in range(workbook.nsheets):
                sheet = workbook.sheet_by_index(sheet_index)
                if sheet.visibility != 0:
                    workbook.unload_sheet(sheet_index)
                    continue
                hidden_rows = {index for index, info in sheet.rowinfo_map.items() if info.hidden}
                hidden_columns = {index for index, info in sheet.colinfo_map.items() if info.hidden}
                rows = []
                for row_index in range(sheet.nrows):
                    if row_index in hidden_rows:
                        continue
                    cells = []
                    for column_index in range(sheet.row_len(row_index)):
                        if column_index in hidden_columns:
                            continue
                        value = _value(sheet.cell(row_index, column_index))
                        if value == '':
                            continue
                        characters += len(value)
                        if len(value) > 12000 or characters > 250000:
                            raise ValueError()
                        cells.append({'cell': cellname(row_index, column_index), 'value': value})
                    if cells:
                        rows.append({'row': row_index + 1, 'cells': cells})
                        count += 1
                        if count > 2500:
                            raise ValueError()
                notes = []
                for (row_index, column_index), note in sorted(sheet.cell_note_map.items()):
                    if row_index in hidden_rows or column_index in hidden_columns:
                        continue
                    text = note.text
                    characters += len(text)
                    if len(text) > 12000 or characters > 250000:
                        raise ValueError()
                    notes.append({'cell': cellname(row_index, column_index), 'text': text})
                result.append({'sheet': sheet.name, 'rows': rows, 'notes': notes,
                    'merges': [cellname(first_row, first_column) + ':'
                        + cellname(last_row - 1, last_column - 1)
                        for first_row, last_row, first_column, last_column in sheet.merged_cells]})
                workbook.unload_sheet(sheet_index)
            if not result:
                raise ValueError()
            text = json.dumps(result, ensure_ascii=False)
            if len(text) > 250000:
                raise ValueError()
            return text
    except (xlrd.XLRDError, CompDocError, ValueError, KeyError, IndexError,
            AttributeError, struct.error, AssertionError, OSError):
        raise HTTPException(422, '旧版Excel损坏、加密或过大；请使用不超过2500行的普通xls价格表，或另存为xlsx后上传') from None
