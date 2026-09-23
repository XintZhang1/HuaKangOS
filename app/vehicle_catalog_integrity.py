"""Read-only restore checks for explicit store-local classifications."""

def validate_catalogue(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    tables={'catalog_vehicle_brands','catalog_vehicle_series','catalog_model_classifications','catalog_vehicle_classifications'}
    if not names&tables:return {'verified_vehicle_classifications':0}
    if not tables<=names:raise ValueError('车型目录恢复表不完整')
    checks=[
        ("SELECT s.id FROM catalog_vehicle_series s LEFT JOIN catalog_vehicle_brands b ON b.id=s.brand_id WHERE b.id IS NULL OR s.store_id!=b.store_id LIMIT 1",'车系与品牌跨店或来源缺失'),
        ("SELECT c.id FROM catalog_model_classifications c LEFT JOIN master_vehicle_models m ON m.id=c.model_id LEFT JOIN catalog_vehicle_series s ON s.id=c.series_id WHERE m.id IS NULL OR s.id IS NULL OR c.store_id!=m.store_id OR c.store_id!=s.store_id LIMIT 1",'车型与车系跨店或来源缺失'),
        ("SELECT c.id FROM catalog_vehicle_classifications c LEFT JOIN vehicles v ON v.id=c.vehicle_id LEFT JOIN master_vehicle_models m ON m.id=c.model_id WHERE v.id IS NULL OR m.id IS NULL OR c.store_id!=v.store_id OR c.store_id!=m.store_id LIMIT 1",'实车车型归属跨店或来源缺失')]
    for sql,message in checks:
        if connection.execute(sql).fetchone():raise ValueError(message)
    if 'opening_vehicle_entries' in names:
        if connection.execute("SELECT c.id FROM catalog_vehicle_classifications c JOIN opening_vehicle_entries e ON e.vehicle_id=c.vehicle_id WHERE e.model_id!=c.model_id OR e.store_id!=c.store_id LIMIT 1").fetchone():
            raise ValueError('实车归属覆盖了原期初车型')
    if 'vehicle_purchase_receipts' in names:
        if connection.execute("SELECT c.id FROM catalog_vehicle_classifications c JOIN vehicle_purchase_receipts r ON r.vehicle_id=c.vehicle_id JOIN vehicle_purchase_shipments s ON s.id=r.shipment_id JOIN vehicle_purchase_lines l ON l.id=s.line_id WHERE l.model_id!=c.model_id OR r.store_id!=c.store_id LIMIT 1").fetchone():
            raise ValueError('实车归属覆盖了原采购车型')
    return {'verified_vehicle_classifications':connection.execute("SELECT COUNT(*) FROM catalog_vehicle_classifications").fetchone()[0]}
