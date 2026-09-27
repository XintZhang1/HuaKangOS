"""Read-only navigation derived from a case's real kind and flow version.

These are existing native routes, not new capabilities or workflow transitions.
Unknown/legacy versions always retain the generic case page. No permissions are
relaxed: the caller first scopes the case and each destination API reauthorizes.
"""

def case_entry_route(row):
    fallback = f"case/{row.id}"
    kind, version = row.kind, row.flow_version
    data = row.data or {}
    versioned = {
        'order': ({3, 4}, 'sales-quotes'),
        'repair': ({3, 4}, 'repair-orders'),
        'insurance': ({3}, 'insurance-orders'),
        'addon': ({3}, 'addon-orders'),
        'agency': ({3}, 'service-orders'),
        'other_income': ({2}, 'service-orders'),
        'invoice': ({3}, 'invoices'),
    }
    if kind in versioned:
        versions, route = versioned[kind]
        return f'{route}/{row.id}' if version in versions else fallback
    direct = {
        'procurement': 'procurement', 'vehicle_procurement': 'vehicle-procurement',
        'retail': 'retail', 'warehouse': 'warehouse', 'aftercare': 'aftercare',
        'business_finance': 'business-finance-order', 'membership': 'membership-order',
        'recharge_bundle': 'recharge-bundle-order', 'vehicle_operations': 'vehicle-operation',
        'customer_care': 'customer-service', 'claim': 'claims',
    }
    if kind in direct:
        return f'{direct[kind]}/{row.id}'
    linked = {
        'vehicle_transfer': ('vehicle_transfer_id', 'vehicle-transfers'),
        'material_transfer': ('transfer_id', 'transfers'),
        'reconciliation': ('reconciliation_id', 'reconciliation'),
        'interstore_clearing': ('clearing_id', 'clearing'),
    }
    if kind in linked:
        key, route = linked[kind]
        value = data.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return f'{route}/{value}'
    if kind == 'service_intake':
        for key, route in [('gate_visit_id', 'gate-visits'),
                           ('rework_id', 'service-intake/reworks'),
                           ('appointment_id', 'service-intake/appointments')]:
            value = data.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return f'{route}/{value}'
    return fallback
