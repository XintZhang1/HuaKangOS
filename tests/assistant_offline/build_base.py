import fixture_env
import os
from argparse import Namespace
from pathlib import Path
base = fixture_env.RUNTIME/'seed-base.sqlite'
if base.exists(): raise SystemExit('Seed template already exists; refusing overwrite')
os.environ['DATABASE_URL'] = 'sqlite:///' + str(base)
# Seed legacy business data without fabricating Runtime history/signals. Tests
# enable the feature switches in their own fresh process after this template.
for key in ('ASSISTANT_HOME_ENABLED', 'ASSISTANT_RUNTIME_ENABLED',
            'ASSISTANT_FOLLOWUP_ENABLED', 'ASSISTANT_NOTIFICATIONS_ENABLED'):
    os.environ[key] = 'false'
from app.cli import initialize
initialize(Namespace(admin_user='offline_admin',demo=True))
from app.db import SessionLocal,engine
from app.models import Store,User,UserStore
from sqlalchemy import select
with SessionLocal() as db:
    admin=db.scalar(select(User).where(User.username=='offline_admin'))
    if db.get(Store,2) is None:db.add(Store(id=2,code='SYNTHETIC2',name='合成二店'))
    sales=User(username='offline_sales',display_name='合成销售',password_hash=admin.password_hash,
               role='sales',active=True,must_change_password=False)
    db.add(sales);db.flush();db.add(UserStore(user_id=sales.id,store_id=1,role='sales'));db.commit()
engine.dispose()
print('Created isolated template with migrated schema, demo business and synthetic identities.')
