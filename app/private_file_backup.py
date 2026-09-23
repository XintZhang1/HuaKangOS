"""SQLite + immutable local object bundles, never a database-only restore.

Publication uses a new directory and a checked completion marker. No old database
or object directory is overwritten, no configuration is silently switched, and
orphan objects are intentionally excluded from backups and retained at source.
"""
from pathlib import Path
from contextlib import closing
import hashlib,json,os,sqlite3,uuid
from .private_files import private_root,read_object,checked_bytes,object_path,_plain,_sync_directory


def _query(connection,sql):
    return connection.exec_driver_sql(sql) if hasattr(connection,'exec_driver_sql') else connection.execute(sql)


def _rows(connection,table):
    cursor=_query(connection,'SELECT * FROM '+table)
    keys=list(cursor.keys()) if hasattr(cursor,'keys') else [c[0] for c in cursor.description]
    return [dict(zip(keys,row)) for row in cursor]


def _names(connection):
    if hasattr(connection,'dialect'):
        from sqlalchemy import inspect
        return set(inspect(connection).get_table_names())
    return {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _file_rows(connection,content=False):
    if hasattr(connection,'dialect'):
        from sqlalchemy import inspect
        columns={c['name'] for c in inspect(connection).get_columns('flow_files')}
    else:columns={r[1] for r in connection.execute('PRAGMA table_info(flow_files)')}
    if not {'sha256','size','content'}<=columns:raise ValueError('原附件记录结构不完整')
    selected=[name for name in ('id','store_id','case_id','category','generated','sha256','size','source_file_id') if name in columns]
    selected.append('content' if content else 'length(content) AS content_length')
    sql='SELECT '+','.join(selected)+' FROM flow_files'+(' ORDER BY id' if 'id' in columns else '')
    # At most one BLOB is materialized by this loop; manifest construction never
    # selects BLOB bytes. Server cursors keep PostgreSQL reads bounded as well.
    options=connection.get_execution_options() if hasattr(connection,'get_execution_options') else None
    source=connection.execution_options(stream_results=True,max_row_buffer=1,yield_per=1) if options is not None else connection
    cursor=_query(source,sql)
    keys=list(cursor.keys()) if hasattr(cursor,'keys') else [c[0] for c in cursor.description]
    try:
        for row in cursor:yield dict(zip(keys,row))
    finally:
        cursor.close()
        if options is not None:connection.execution_options(stream_results=options.get('stream_results',False),max_row_buffer=options.get('max_row_buffer',1000),yield_per=options.get('yield_per'))


def file_manifest(connection):
    names=_names(connection)
    if 'flow_files' not in names:
        if 'private_file_objects' in names and _rows(connection,'private_file_objects'):raise ValueError('私有附件缺少原文件表')
        return []
    objects=_rows(connection,'private_file_objects') if 'private_file_objects' in names else []
    byfile={}
    for obj in objects:
        if not {'id','file_id','store_id','object_key','sha256','size'}<=set(obj):raise ValueError('私有附件引用结构不完整')
        if obj['file_id'] in byfile:raise ValueError('同一附件存在多个对象引用')
        byfile[obj['file_id']]=obj
    if len({obj['object_key'] for obj in objects})!=len(objects):raise ValueError('不同附件不能共享对象引用')
    result=[];seen=set();sources={}
    for i,file in enumerate(_file_rows(connection)):
        key=file.get('id',i+1);seen.add(key);ref=byfile.get(key)
        if ref and (ref['store_id']!=file.get('store_id') or ref['sha256']!=file['sha256'] or ref['size']!=file['size'] or file['content_length']!=0):
            raise ValueError('私有附件与原文件门店、大小、摘要或 BLOB 不一致')
        item={'file_id':key,'store_id':file.get('store_id'),'sha256':file['sha256'],'size':file['size'],
              'storage':'private_local' if ref else 'blob','object_key':ref['object_key'] if ref else None,
              'source_file_id':file.get('source_file_id'),'case_id':file.get('case_id'),'category':file.get('category'),
              'generated':bool(file.get('generated'))}
        sources[key]=item
        result.append(item)
    if set(byfile)-seen:raise ValueError('私有对象引用缺少原附件')
    for item in result:
        expected={'signed_contract':'contract','signed_handover':'handover'}.get(item['category'])
        source=sources.get(item['source_file_id']) if item['source_file_id'] else None
        if expected or item['source_file_id']:
            if not expected or not source or not source['generated'] or source['category']!=expected or item['generated'] or (source['store_id'],source['case_id'])!=(item['store_id'],item['case_id']):
                raise ValueError('签回附件须绑定同店同单对应类别的原生成文档')
    return sorted(result,key=lambda r:r['file_id'])


def validate_connection_files(connection,object_root=None):
    """DBAPI SQLite or SQLAlchemy SQLite/PostgreSQL connection. Read-only.

    pg_dump/transfer callers must pass the matching immutable object root; an
    empty BLOB never proves external bytes survived. This is byte verification,
    not a replacement for PostgreSQL business-ledger/scan restore validation.
    """
    manifest=file_manifest(connection);private=[f for f in manifest if f['storage']=='private_local']
    if private and object_root is None:raise ValueError('此数据库引用私有附件；必须提供配套对象目录，数据库单文件不是完整备份')
    byfile={entry['file_id']:entry for entry in manifest}
    for i,file in enumerate(_file_rows(connection,content=True) if manifest else []):
        entry=byfile[file.get('id',i+1)]
        if entry['storage']=='private_local':read_object(object_root,entry['object_key'],entry['store_id'],entry['size'],entry['sha256'])
        else:checked_bytes(file['content'],entry['size'],entry['sha256'])
    return {'verified_files':len(manifest),'verified_private_objects':len(private),'verified_blob_files':len(manifest)-len(private)}


def _json_bytes(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')
def _sha(path):
    result=hashlib.sha256();size=0
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):result.update(chunk);size+=len(chunk)
    return {'sha256':result.hexdigest(),'size':size}


def _write(path,content):
    _plain(path.parent);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);_plain(path.parent)
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0),0o600),'wb') as stream:
        stream.write(content);stream.flush();os.fsync(stream.fileno())


def _new_stage(target):
    target=Path(target)
    if not target.is_absolute():raise ValueError('备份或恢复目标须使用绝对路径')
    target=Path(os.path.abspath(target));_plain(target)
    # This also prevents storing backup evidence anywhere under public source.
    parent=private_root(target.parent)
    if target.exists():raise ValueError('目标已存在，拒绝覆盖数据库或附件')
    stage=parent/('.'+target.name+'.incomplete-'+uuid.uuid4().hex)
    stage.mkdir(mode=0o700);return target,stage


def _publish(stage,target):
    if target.exists():raise ValueError('目标已存在，保留未发布副本供核对')
    _plain(target);os.rename(stage,target);_sync_directory(target.parent)


def _full_validate(connection,root):
    from .backup_integrity import validate_sqlite
    return validate_sqlite(connection,object_root=root)


def _copy_references(manifest,source_root,target_root):
    for item in manifest:
        if item['storage']!='private_local':continue
        content=read_object(source_root,item['object_key'],item['store_id'],item['size'],item['sha256'])
        destination=object_path(target_root,item['object_key'],item['store_id'])
        _write(destination,content)


def create_bundle(database_path,object_root,output):
    """One online SQLite snapshot; collect only referenced immutable objects."""
    source=Path(database_path)
    if not source.is_absolute():raise ValueError('备份源数据库须使用绝对路径')
    _plain(source)
    if not source.is_file():raise ValueError('备份源数据库不存在')
    target,stage=_new_stage(output);database=stage/'database.sqlite';objects=stage/'object_store';objects.mkdir(mode=0o700)
    # Failure deliberately leaves the .incomplete directory without a complete
    # marker. Do not delete evidence or report a partial copy as recoverable.
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as original,closing(sqlite3.connect(database)) as copy:
        original.backup(copy)
        manifest=file_manifest(copy);validate_connection_files(copy,object_root)
        _copy_references(manifest,object_root,objects)
        verified=_full_validate(copy,objects)
    try:database.chmod(0o600)
    except OSError:pass
    with database.open('r+b') as stream:os.fsync(stream.fileno())
    body={'format':'huakangos-private-files','version':1,'database':_sha(database),'files':manifest}
    raw=_json_bytes(body);_write(stage/'manifest.json',raw)
    _write(stage/'COMPLETE',hashlib.sha256(raw).hexdigest().encode('ascii'))
    _sync_directory(stage);_publish(stage,target)
    return {'bundle':str(target),**verified}


def validate_bundle(bundle):
    base=private_root(bundle);manifest=base/'manifest.json';complete=base/'COMPLETE';database=base/'database.sqlite';objects=base/'object_store'
    for path in (manifest,complete,database,objects):_plain(path)
    try:
        with manifest.open('rb') as stream:raw=stream.read(32*1024*1024+1)
        if len(raw)>32*1024*1024:raise ValueError('附件备份清单超过上限')
        if complete.read_bytes()!=hashlib.sha256(raw).hexdigest().encode('ascii'):raise ValueError('附件备份尚未完成或清单摘要不一致')
        body=json.loads(raw)
        if set(body)!={'format','version','database','files'} or body['format']!='huakangos-private-files' or body['version']!=1:raise ValueError('附件备份格式或版本无效')
        if body['database']!=_sha(database):raise ValueError('备份数据库字节与冻结清单不一致')
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as db:
            if body['files']!=file_manifest(db):raise ValueError('附件备份清单与数据库对象引用不一致')
            verified=_full_validate(db,objects)
        return {'bundle':str(base),'database_path':str(database),'object_root':str(objects),**verified}
    except (OSError,KeyError,TypeError,json.JSONDecodeError) as exc:raise ValueError('附件备份缺少完整文件或清单格式无效') from exc


def restore_bundle(bundle,output):
    """Restore into a fresh sibling directory, then validate before publication."""
    checked=validate_bundle(bundle);source=Path(bundle);target,stage=_new_stage(output)
    objects=stage/'object_store';objects.mkdir(mode=0o700);database=stage/'database.sqlite'
    with closing(sqlite3.connect((source/'database.sqlite').as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(database)) as dst:
        src.backup(dst);manifest=file_manifest(dst);_copy_references(manifest,source/'object_store',objects);verified=_full_validate(dst,objects)
    try:database.chmod(0o600)
    except OSError:pass
    with database.open('r+b') as stream:os.fsync(stream.fileno())
    body={'format':'huakangos-private-files','version':1,'database':_sha(database),'files':manifest};raw=_json_bytes(body)
    _write(stage/'manifest.json',raw);_write(stage/'COMPLETE',hashlib.sha256(raw).hexdigest().encode('ascii'))
    validate_bundle(stage);_publish(stage,target)
    return {'restored_directory':str(target),'database_path':str(target/'database.sqlite'),'object_root':str(target/'object_store'),**verified}
