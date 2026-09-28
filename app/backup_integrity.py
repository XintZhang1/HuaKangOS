"""Read-only SQLite restore checks; do not log business rows or file contents."""
import hashlib


def validate_sqlite(connection,object_root=None):
    if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('备份数据库完整性检查未通过')
    if connection.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('备份存在不完整的关联记录')
    names={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    from .business_assistant_plan_integrity import validate as validate_assistant_plans
    assistant_plans=validate_assistant_plans(connection)
    from .private_file_backup import validate_connection_files
    files=validate_connection_files(connection,object_root)
    if {'group_entries','group_settlement_entries'} <= names:
        inconsistent=connection.execute('''SELECT e.id FROM group_entries e
            LEFT JOIN group_settlement_entries s ON s.entry_id=e.id
            GROUP BY e.id HAVING COUNT(s.id)!=2 OR SUM(s.amount_cents)!=0
              OR COUNT(DISTINCT s.side)!=2 LIMIT 1''').fetchone()
        if inconsistent:
            raise ValueError('集团会员往来配对检查未通过')
    if {'group_members','group_entries','group_reservations'} <= names:
        refund_holds = (' + COALESCE((SELECT SUM(f.amount_cents) FROM group_refund_requests f '
                        "WHERE f.member_id=m.id AND f.status='approved'),0)") if 'group_refund_requests' in names else ''
        if 'recharge_bundle_refunds' in names:
            refund_holds += " + COALESCE((SELECT SUM(f.amount_cents) FROM recharge_bundle_refunds f WHERE f.member_id=m.id AND f.status='reserved'),0)"
        if 'business_finance_stored_correction_requests' in names:
            refund_holds += " + COALESCE((SELECT SUM(f.reserved_cents) FROM business_finance_stored_correction_requests f WHERE f.member_id=m.id AND f.status='reserved'),0)"
        inconsistent=connection.execute('''SELECT m.id FROM group_members m WHERE
            m.balance_cents != COALESCE((SELECT SUM(e.amount_cents) FROM group_entries e WHERE e.member_id=m.id),0)
            OR m.reserved_cents != (COALESCE((SELECT SUM(r.amount_cents) FROM group_reservations r WHERE r.member_id=m.id AND r.status='reserved'),0)'''
            + refund_holds + ') OR m.reserved_cents<0 OR m.balance_cents<m.reserved_cents LIMIT 1').fetchone()
        if inconsistent:
            raise ValueError('集团会员本金或占额与账本不一致')
    if {'material_transfers','material_transfer_movements','material_transfer_settlements'} <= names:
        inconsistent=connection.execute('''SELECT m.id FROM material_transfer_movements m
            JOIN material_transfers t ON t.id=m.transfer_id
            LEFT JOIN material_transfer_settlements s ON s.movement_id=m.id
            WHERE m.kind='accept' GROUP BY m.id
            HAVING COUNT(s.id)!=2 OR SUM(s.amount_cents)!=0 OR COUNT(DISTINCT s.store_id)!=2
              OR SUM(CASE WHEN s.store_id=t.from_store_id AND s.counterparty_store_id=t.to_store_id AND s.amount_cents=m.value_cents THEN 1
                          WHEN s.store_id=t.to_store_id AND s.counterparty_store_id=t.from_store_id AND s.amount_cents=-m.value_cents THEN 1 ELSE 0 END)!=2 LIMIT 1''').fetchone()
        if inconsistent:raise ValueError('物资调拨双方往来不配对')
        inconsistent=connection.execute('''SELECT m.id FROM material_transfer_movements m
            JOIN material_transfers t ON t.id=m.transfer_id
            LEFT JOIN flow_stock_moves s ON s.id=m.stock_move_id
            WHERE m.kind IN ('dispatch','accept','return_receive') AND
              (s.id IS NULL OR s.store_id!=m.store_id OR
               s.quantity_milli!=CASE WHEN m.kind='dispatch' THEN -m.quantity_milli ELSE m.quantity_milli END OR
               s.value_cents!=CASE WHEN m.kind='dispatch' THEN -m.value_cents ELSE m.value_cents END OR
               s.case_id!=CASE WHEN m.kind='accept' THEN t.to_case_id ELSE t.from_case_id END)
            LIMIT 1''').fetchone()
        if inconsistent:raise ValueError('物资调拨实物记录与库存账不一致')
        loss_filter='AND l.id NOT IN (SELECT line_id FROM transfer_loss_postings)' if 'transfer_loss_postings' in names else ''
        inconsistent=connection.execute(f'''SELECT t.id FROM material_transfers t
            JOIN material_transfer_lines l ON l.transfer_id=t.id
            LEFT JOIN material_transfer_movements m ON m.line_id=l.id
            GROUP BY l.id HAVING
              SUM(CASE WHEN m.kind IN ('accept','reject') THEN m.quantity_milli ELSE 0 END) > SUM(CASE WHEN m.kind='dispatch' THEN m.quantity_milli ELSE 0 END)
              OR SUM(CASE WHEN m.kind='return_receive' THEN m.quantity_milli ELSE 0 END) > SUM(CASE WHEN m.kind='return_ship' THEN m.quantity_milli ELSE 0 END)
              OR SUM(CASE WHEN m.kind='return_ship' THEN m.quantity_milli ELSE 0 END) > SUM(CASE WHEN m.kind='reject' THEN m.quantity_milli ELSE 0 END)
              OR SUM(CASE WHEN m.kind IN ('accept','return_receive') THEN m.value_cents ELSE 0 END) > SUM(CASE WHEN m.kind='dispatch' THEN m.value_cents ELSE 0 END)
              OR (t.status='completed' {loss_filter} AND (SUM(CASE WHEN m.kind IN ('accept','return_receive') THEN m.quantity_milli ELSE 0 END)!=l.quantity_milli
                  OR SUM(CASE WHEN m.kind IN ('accept','return_receive') THEN m.value_cents ELSE 0 END)!=SUM(CASE WHEN m.kind='dispatch' THEN m.value_cents ELSE 0 END))) LIMIT 1''').fetchone()
        if inconsistent:raise ValueError('物资调拨在途数量或价值不守恒')
    from .transfer_exception_integrity import validate_transfer_exceptions_sqlite
    transfer_exceptions=validate_transfer_exceptions_sqlite(connection)
    from .user_access_integrity import validate as validate_access
    access=validate_access(connection)
    from .procurement_cost_integrity import validate as validate_purchase_cost
    purchase_cost=validate_purchase_cost(connection)
    from .file_security import validate_file_security_sqlite
    scanning=validate_file_security_sqlite(connection)
    from .vehicle_backup_integrity import validate_vehicle_custody
    vehicles=validate_vehicle_custody(connection)
    from .benefit_backup_integrity import validate_benefits_sqlite
    benefits=validate_benefits_sqlite(connection)
    from .reconciliation_backup_integrity import validate_reconciliation_sqlite
    reconciliation=validate_reconciliation_sqlite(connection)
    from .retail_backup_integrity import validate_retail_sqlite
    retail=validate_retail_sqlite(connection)
    from .invoice_backup_integrity import validate_invoices_sqlite
    invoices=validate_invoices_sqlite(connection)
    from .warehouse_backup_integrity import validate_warehouse_integrity
    warehouse=validate_warehouse_integrity(connection)
    from .membership_backup_integrity import validate_membership_sqlite
    membership=validate_membership_sqlite(connection)
    from .membership_fee_correction_integrity import validate as validate_membership_fee_corrections
    membership.update({key:value for key,value in validate_membership_fee_corrections(connection).items() if key!='cash_ids'})
    from .service_intake_backup_integrity import validate as validate_service_intake
    intake=validate_service_intake(connection)
    from .vehicle_operations_backup_integrity import validate_vehicle_operations
    positions=validate_vehicle_operations(connection)
    from .group_aftercare_integrity import validate_group_aftercare_sqlite
    group_returns=validate_group_aftercare_sqlite(connection)
    from .aftercare_backup_integrity import validate as validate_aftercare
    aftercare=validate_aftercare(connection)
    from .payment_cash_integrity import validate_payment_cash
    payments=validate_payment_cash(connection)
    from .business_finance_integrity import validate_business_finance_sqlite
    finance=validate_business_finance_sqlite(connection)
    from .procurement_prepayment_integrity import validate as validate_prepayments
    prepayments=validate_prepayments(connection)
    from .vehicle_income_integrity import validate as validate_vehicle_income
    vehicle_income=validate_vehicle_income(connection)
    from .member_pricing_integrity import validate as validate_member_pricing
    member_pricing=validate_member_pricing(connection)
    from .repair_package_integrity import validate as validate_repair_packages
    repair_packages=validate_repair_packages(connection)
    from .opening_import_backup_integrity import validate_opening_import
    opening=validate_opening_import(connection)
    from .recharge_bundle_integrity import validate_recharge_bundles_sqlite
    bundles=validate_recharge_bundles_sqlite(connection)
    from .claims_backup_integrity import validate as validate_claims
    claims=validate_claims(connection)
    from .vehicle_imports_integrity import validate_vehicle_imports
    vehicle_imports=validate_vehicle_imports(connection)
    from .retail_bundle_integrity import validate_retail_bundles_sqlite
    retail_bundles=validate_retail_bundles_sqlite(connection)
    from .vehicle_catalog_integrity import validate_catalogue
    catalogue=validate_catalogue(connection)
    from .service_orders_backup_integrity import validate as validate_service_orders
    service_orders=validate_service_orders(connection)
    from .sales_quote_integrity import validate_sales_quotes_sqlite
    sales_quotes=validate_sales_quotes_sqlite(connection)
    from .insurance_backup_integrity import validate_insurance_sqlite
    insurance=validate_insurance_sqlite(connection)
    from .addon_backup_integrity import validate as validate_addon
    addon=validate_addon(connection)
    from .business_entity_integrity import validate_business_entities
    entities=validate_business_entities(connection)
    from .observation_corrections_integrity import validate as validate_observations
    from .retail_group_integrity import validate_retail_group
    from .transfer_goods_recovery_integrity import validate_transfer_goods_recovery_sqlite
    observations=validate_observations(connection)
    retail_group=validate_retail_group(connection)
    found_goods=validate_transfer_goods_recovery_sqlite(connection)
    from .transfer_goods_search_integrity import validate_transfer_goods_searches
    found_searches=validate_transfer_goods_searches(connection)
    from .questionnaire_integrity import validate as validate_questionnaires
    questionnaires=validate_questionnaires(connection)
    from .gate_visit_integrity import validate as validate_gate_visits
    gate_visits=validate_gate_visits(connection)
    from .dossier_grant_integrity import validate as validate_dossiers
    dossiers=validate_dossiers(connection)
    from .material_brand_integrity import validate as validate_material_brands
    material_brands=validate_material_brands(connection)
    return {**assistant_plans,**repair_packages,**member_pricing,**vehicle_income,**prepayments,**material_brands,**dossiers,**gate_visits,**questionnaires,**found_searches,**observations,**retail_group,**found_goods,**transfer_exceptions,**entities,**addon,**insurance,**access,**purchase_cost,'integrity':'ok','foreign_keys':'ok',**files,**scanning,**vehicles,**benefits,**reconciliation,**retail,**invoices,**warehouse,**membership,**intake,**positions,**group_returns,**aftercare,**payments,**finance,**opening,**bundles,**claims,**vehicle_imports,**retail_bundles,**catalogue,**service_orders,**sales_quotes}
