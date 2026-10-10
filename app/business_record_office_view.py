"""Render office review data with authorized original-sheet column metadata.

The caller first enforces the contract's store scope and financial-read role.
General managers and store administrators can read the complete valuation
within their existing authorized stores. Return column metadata so the UI does
not depend on a separately loaded report catalog. Restricted projections keep
their sensitive-field filter for callers without financial-read access.
"""

import re

from .business_record_reports import CATALOG_BY_KEY
from .business_record_report_specs import SENSITIVE_REPORT_TERMS


def office_review_view(source, can_view_sensitive):
    definition = CATALOG_BY_KEY.get(source.get('report_key'), {})
    columns = definition.get('columns', [])
    if can_view_sensitive:
        data = dict(source)
    else:
        columns = [column for column in columns
                   if not any(term in column['label'] for term in SENSITIVE_REPORT_TERMS)
                   and not re.fullmatch(r'(补充)?列\s*\d+', column['label'])]
        # Free-text notes can contain cost/profit details and cannot be safely
        # filtered by keywords. Only the explicitly public summary is returned.
        data = {key: source[key] for key in
                ('report_key', 'period', 'manual_report_id', 'expected_amount_cents')
                if key in source}
    allowed = {column['key'] for column in columns}
    data['values'] = {key: value for key, value in source.get('values', {}).items()
                      if key in allowed}
    data['report_title'] = definition.get('title', '车辆明细表')
    data['columns'] = [{key: column[key] for key in ('key', 'label', 'type', 'unit')
                        if key in column} for column in columns]
    data['sensitive_fields_hidden'] = not can_view_sensitive
    return data
