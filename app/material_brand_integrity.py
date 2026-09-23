"""Independent validation of current classification, not historical repricing."""

def validate(connection):
    tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    profile='master_item_profiles';brand='master_material_brands'
    profile_columns={r[1] for r in connection.execute(f'PRAGMA table_info({profile})')}
    has_column='brand_id' in profile_columns
    if brand not in tables and not has_column:
        return {'material_brands':0,'material_brand_bindings':0}
    if brand not in tables or not has_column:
        raise ValueError('物资品牌表或品牌引用列缺失，不能恢复不完整域')
    for row in connection.execute(f'SELECT id,store_id,code,name,active,version FROM {brand}'):
        if not row[2] or not str(row[2]).strip() or not str(row[3]).strip() or row[4] not in (0,1) or row[5]<1:
            raise ValueError('物资品牌资料损坏')
        if not connection.execute('SELECT 1 FROM stores WHERE id=?',(row[1],)).fetchone():
            raise ValueError('物资品牌所属门店不存在')
    bindings=connection.execute('''SELECT p.id,p.store_id,p.active,b.id,b.store_id,b.active,i.store_id
        FROM master_item_profiles p LEFT JOIN master_material_brands b ON b.id=p.brand_id
        LEFT JOIN flow_items i ON i.id=p.item_id WHERE p.brand_id IS NOT NULL''').fetchall()
    if any(r[3] is None or r[1]!=r[4] or r[1]!=r[6] or (r[2] and not r[5]) for r in bindings):
        raise ValueError('物资品牌引用越店、失效或原物资不匹配')
    return {'material_brands':connection.execute(f'SELECT COUNT(*) FROM {brand}').fetchone()[0],
            'material_brand_bindings':len(bindings)}
