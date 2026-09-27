from alembic import context
from app.db import Base, make_engine
from app.config import settings
from app import models

config = context.config
target_metadata = Base.metadata
url = config.attributes.get('url_override', settings.database_url)

if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={'paramstyle':'named'}, render_as_batch=url.startswith('sqlite'))
    with context.begin_transaction(): context.run_migrations()
else:
    engine = make_engine(url)
    try:
        with engine.connect() as connection:
            raw = connection.connection.driver_connection
            if url.startswith('sqlite'): raw.execute('PRAGMA foreign_keys=OFF')
            context.configure(connection=connection,target_metadata=target_metadata,render_as_batch=url.startswith('sqlite'),compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
                if url.startswith('sqlite') and connection.exec_driver_sql('PRAGMA foreign_key_check').fetchone():
                    raise RuntimeError('Migration foreign-key validation failed; no partial upgrade retained')
            if url.startswith('sqlite'): raw.execute('PRAGMA foreign_keys=ON')
    finally:
        # This is a separate engine from app.db.engine; release its pooled connections too.
        engine.dispose()
