"""Read-only work-area filters. They narrow, never replace, the authorized query.

A task may belong to both its source business and a collaborating work area.
For example a finance task on a vehicle order belongs to sales AND finance.
These categories are navigation aids, not new business states or permissions.
"""
from sqlalchemy import and_, or_, select
from .flow_models import Case, Task
from .flow_specs import SPECS

WORK_AREAS = frozenset({'sales', 'warehouse', 'repair', 'materials', 'finance',
                        'customers', 'members', 'analytics', 'reference', 'system'})
COLLABORATING_KINDS = {
    'warehouse': ('inventory', frozenset({'order', 'aftercare', 'vehicle_procurement', 'vehicle_transfer', 'vehicle_operations'})),
    'materials': ('inventory', frozenset({'repair', 'addon', 'retail', 'purchase', 'procurement', 'material_transfer', 'warehouse', 'material_issue', 'material_return', 'stock_count'})),
    'repair': ('technician', frozenset({'repair', 'addon', 'retail', 'order'})),
}


def work_area_predicate(area):
    """Return a SQL condition; caller must retain the existing tenancy filter."""
    if area not in WORK_AREAS:
        raise ValueError('未知工作模块')
    kinds = [kind for kind, spec in SPECS.items() if spec['module'] == area]
    conditions = [Task.case_id.in_(select(Case.id).where(Case.kind.in_(kinds)))]
    if area == 'finance':
        conditions.append(Task.role == 'finance')
    if area == 'customers':
        conditions.append(Task.role == 'customer_service')
    if area in COLLABORATING_KINDS:
        role, related = COLLABORATING_KINDS[area]
        conditions.append(and_(Task.role == role, Task.case_id.in_(select(Case.id).where(Case.kind.in_(sorted(related))))))
    return or_(*conditions)


def filter_task_view(query, *, area='', text='', due='', business_date):
    if area:
        query = query.where(work_area_predicate(area))
    if text:
        # Treat SQL wildcard characters as text, just as the search label says.
        cases = select(Case.id).where(or_(Case.title.contains(text, autoescape=True), Case.number.contains(text, autoescape=True)))
        query = query.where(or_(Task.title.contains(text, autoescape=True), Task.case_id.in_(cases)))
    if due == 'overdue':
        query = query.where(Task.due_date < business_date)
    elif due == 'today':
        query = query.where(Task.due_date == business_date)
    elif due:
        raise ValueError('未知到期筛选')
    return query
