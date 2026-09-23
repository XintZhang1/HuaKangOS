"""Upgrade an explicitly old, nonempty schema; never guess a historical brand."""
import sqlite3
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData,select,inspect
from app.db import Base,engine,make_engine,SessionLocal
from app.backup_integrity import validate_sqlite
from scripts.migrate_database import table_fingerprint
from tests.conftest import login
from tests.test_master_data import create,update
from tests.test_dossier_grant_native import native_source


def test_nonempty_s91f_upgrade_preserves_original_profile_and_files_then_binds_brand(client,tmp_path):
    data=native_source(client);login(client,'admin')
    category=create(client,'material_categories',{'code':'OLD-C','name':'原分类'})
    warehouse=create(client,'warehouses',{'code':'OLD-W','name':'原仓库','warehouse_type':'materials'})
    location=create(client,'locations',{'code':'OLD-L','name':'原库位','warehouse_id':warehouse['id']})
    res=client.post('/api/flow/master/items',json={'values':{'sku':'OLD-ITEM','name':'原无品牌物资','unit':'件','reorder':'0','active':True}})
    assert res.status_code==201,res.text
    values={'item_id':res.json()['id'],'category_id':category['id'],'location_id':location['id']}
    profile=create(client,'item_profiles',values)
    path=tmp_path/'old-s91f.sqlite';url='sqlite:///'+path.as_posix()
    cfg=Config('alembic.ini');cfg.attributes['url_override']=url
    command.upgrade(cfg,'s91f_dossier_grants')
    target=make_engine(url);old=MetaData();old.reflect(target)
    originals=[table for table in old.sorted_tables if table.name!='alembic_version']
    try:
        with target.connect() as db:
            db.exec_driver_sql('PRAGMA foreign_keys=OFF');db.commit()
            with db.begin(),engine.connect() as source:
                for table in originals:
                    rows=[dict(r) for r in source.execute(select(table)).mappings()]
                    if rows:db.execute(table.insert(),rows)
                assert db.exec_driver_sql('PRAGMA foreign_key_check').fetchone() is None
            db.exec_driver_sql('PRAGMA foreign_keys=ON');db.commit()
            before={t.name:table_fingerprint(db,t) for t in originals}
        with sqlite3.connect(path) as db:
            assert validate_sqlite(db)['material_brands']==0
            assert 'brand_id' not in {r[1] for r in db.execute('PRAGMA table_info(master_item_profiles)')}
            content=db.execute('SELECT content FROM flow_files WHERE id=?',(data['file_id'],)).fetchone()[0]
            assert content==b'Synthetic exact original file'
        command.upgrade(cfg,'head')
        with target.connect() as db:
            assert before=={t.name:table_fingerprint(db,t) for t in originals}
            assert db.exec_driver_sql('SELECT brand_id FROM master_item_profiles WHERE id=?',(profile['id'],)).scalar() is None
            assert db.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()==ScriptDirectory.from_config(cfg).get_current_head()
        schema=inspect(target)
        for name in ('master_material_brands','master_item_profiles'):
            assert {c['name'] for c in schema.get_columns(name)}==set(Base.metadata.tables[name].columns.keys())
        assert any(fk['referred_table']=='master_material_brands' and fk['constrained_columns']==['brand_id'] for fk in schema.get_foreign_keys('master_item_profiles'))
        SessionLocal.configure(bind=target)
        brand=create(client,'material_brands',{'code':'NEW-B','name':'后来核实品牌'})
        bound=update(client,'item_profiles',profile,values|{'brand_id':brand['id']})
        assert bound['brand_id']==brand['id']
        # An old client resaving known fields does not erase the newly explicit brand.
        assert update(client,'item_profiles',bound,values)['brand_id']==brand['id']
        with sqlite3.connect(path) as db:
            report=validate_sqlite(db)
            assert report['material_brands']==1 and report['material_brand_bindings']==1
            assert db.execute('SELECT content FROM flow_files WHERE id=?',(data['file_id'],)).fetchone()[0]==content
    finally:
        SessionLocal.configure(bind=engine);target.dispose()
