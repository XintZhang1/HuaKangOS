"""Bounded private local objects. No HTTP/static route or user-supplied filename.

Publication precedes the database reference. A rolled back transaction may leave
an orphan; missing committed bytes never fall back to another file or the BLOB.
Filesystem administrators remain privileged. ACL setup is deployment work.
"""
from contextlib import contextmanager
from pathlib import Path
import hashlib,os,re,stat,uuid
from fastapi import HTTPException
from sqlalchemy import select,inspect as sa_inspect
from .config import ROOT,settings
# models is the registry entry point; importing flow_models first would recurse
# through its StoreScoped dependency while Versioned is still being defined.
from . import models as _models
from .flow_models import FileAsset,Case
from .private_file_models import PrivateFileObject
from .tenancy import single_store

MAX_BYTES=10*1024*1024
KEY=re.compile(r'objects/store-([1-9][0-9]*)/([0-9a-f]{32})\.blob\Z')


def _plain(path):
    """Reject links and Windows junction/reparse components before any IO."""
    for part in [*reversed(path.parents),path]:
        try:info=part.lstat()
        except FileNotFoundError:continue
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400):
            raise ValueError('附件目录或对象含符号链接/重解析点，拒绝访问')
    return path


def private_root(root=None,create=False):
    value=root if root is not None else getattr(settings,'private_file_root','')
    if not value:raise ValueError('尚未配置私有附件目录')
    path=Path(value)
    if not path.is_absolute() or str(path).startswith(('\\\\','//')):
        raise ValueError('私有附件目录须为本机绝对路径')
    path=Path(os.path.abspath(path));_plain(path)
    repo=ROOT.resolve()
    if path==Path(path.anchor) or path.is_relative_to(repo) or repo.is_relative_to(path):
        raise ValueError('私有附件目录不能位于项目、公开静态目录或其父目录')
    if create:path.mkdir(parents=True,exist_ok=True,mode=0o700);_plain(path)
    if not path.is_dir():raise ValueError('私有附件目录不存在')
    return path


def object_path(root,key,store_id=None):
    match=KEY.fullmatch(key) if isinstance(key,str) else None
    if not match or (store_id is not None and int(match.group(1))!=store_id):
        raise ValueError('附件对象编号或门店归属无效')
    base=private_root(root);path=base.joinpath(*key.split('/'));_plain(path)
    if not path.is_relative_to(base):raise ValueError('附件对象超出私有目录')
    return path


def checked_bytes(content,size,digest):
    if isinstance(content,(memoryview,bytearray)):content=bytes(content)
    if not isinstance(content,bytes) or type(size) is not int or not 0<size<=MAX_BYTES or len(content)!=size or hashlib.sha256(content).hexdigest()!=digest:
        raise ValueError('附件原字节大小或摘要不匹配')
    return content


def read_object(root,key,store_id,size,digest):
    path=object_path(root,key,store_id)
    try:
        flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0)
        with os.fdopen(os.open(path,flags),'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('附件对象不是常规文件')
            content=stream.read(MAX_BYTES+1)
    except OSError as exc:raise ValueError('私有附件对象缺失或不可读取') from exc
    return checked_bytes(content,size,digest)


def _sync_directory(path):
    # Windows cannot open a directory through os.open; file fsync and NTFS
    # atomic hard-link publication still apply. Power-loss guarantees need the
    # deployment filesystem/backup policy; do not claim POSIX directory fsync.
    if os.name=='nt':return
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try:os.fsync(fd)
    finally:os.close(fd)


def publish(root,store_id,content,size,digest):
    checked_bytes(content,size,digest)
    if type(store_id) is not int or store_id<=0:raise ValueError('附件门店无效')
    base=private_root(root,True);token=uuid.uuid4().hex
    stage=base/'staging';folder=base/'objects'/('store-'+str(store_id))
    for directory in (stage,folder):_plain(directory);directory.mkdir(parents=True,exist_ok=True,mode=0o700);_plain(directory)
    temporary=stage/(token+'.part');key='objects/store-'+str(store_id)+'/'+token+'.blob';target=object_path(base,key,store_id)
    created=False
    try:
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0),0o600);created=True
        with os.fdopen(fd,'wb') as stream:
            stream.write(content);stream.flush();os.fsync(stream.fileno())
        # link is atomic, cannot replace an existing target, and stays on the
        # same filesystem. Unsupported filesystems fail before DB publication.
        os.link(temporary,target);_sync_directory(folder)
        read_object(base,key,store_id,size,digest)
        return key
    finally:
        if created and temporary.exists():temporary.unlink()


@contextmanager
def _authority(db):
    old=db.info.get('_private_file_authority');db.info['_private_file_authority']=True
    try:yield
    finally:
        if old is None:db.info.pop('_private_file_authority',None)
        else:db.info['_private_file_authority']=old


def store_content(db,asset,content):
    """Replace the caller's initial add/flush, before any scan. Never commits."""
    sid=single_store(db)
    if not sa_inspect(asset).transient and asset not in db.new:raise HTTPException(409,'已有附件不可迁移或改写存储位置')
    with db.no_autoflush:
        case=db.scalar(select(Case).where(Case.id==asset.case_id))
    if not case or case.store_id!=sid or asset.store_id not in {None,sid}:raise HTTPException(403,'不能为其他门店保存附件')
    asset.store_id=sid
    try:
        checked_bytes(content,asset.size,asset.sha256)
        mode=getattr(settings,'file_storage_mode','blob')
        if mode not in {'blob','private_local'}:raise ValueError('附件存储模式无效')
        key=publish(None,sid,content,asset.size,asset.sha256) if mode=='private_local' else None
        asset.content=b'' if key else content
        db.add(asset);db.flush()
        if key:
            with _authority(db):
                db.add(PrivateFileObject(store_id=sid,file_id=asset.id,object_key=key,sha256=asset.sha256,size=asset.size));db.flush()
        return asset
    except (ValueError,OSError) as exc:
        raise HTTPException(503,'私有附件保存未完成，请联系管理员检查存储；业务尚未提交') from exc


def read_content(db,asset,root=None):
    """Only a byte resolver: caller must enforce original case/role/scan access."""
    own=db.scalar(select(FileAsset).where(FileAsset.id==asset.id,FileAsset.store_id==asset.store_id))
    if own is None:raise HTTPException(404,'附件不存在或当前门店不可访问')
    reference=db.scalar(select(PrivateFileObject).where(PrivateFileObject.file_id==asset.id,PrivateFileObject.store_id==asset.store_id))
    try:
        if reference:
            if own.content!=b'' or reference.sha256!=own.sha256 or reference.size!=own.size:raise ValueError('附件对象引用与原文件不一致')
            return read_object(root,reference.object_key,own.store_id,own.size,own.sha256)
        return checked_bytes(own.content,own.size,own.sha256)
    except (ValueError,OSError) as exc:raise HTTPException(409,'附件原字节不可用，保持隔离；请核对对象存储或完整恢复来源') from exc


def audit_orphans(connection,root):
    """Read-only maintenance inventory. Never delete a live or in-flight object."""
    base=private_root(root)
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    referenced={r[0] for r in connection.execute('SELECT object_key FROM private_file_objects')} if 'private_file_objects' in names else set()
    from .private_file_backup import RECORD_FILE_TABLES
    for table, _, _ in RECORD_FILE_TABLES:
        if table in names:
            referenced.update(r[0] for r in connection.execute("SELECT object_key FROM " + table + " WHERE object_key != ''"))
    result=[]
    for directory,dirs,files in os.walk(base,followlinks=False):
        current=Path(directory);_plain(current)
        for name in dirs:_plain(current/name)
        for name in files:
            path=current/name;_plain(path);key=path.relative_to(base).as_posix()
            if key not in referenced:
                result.append({'object_key':key,'size':path.stat().st_size,'kind':'staging' if key.startswith('staging/') else 'unreferenced'})
    return {'referenced_count':len(referenced),'orphans':sorted(result,key=lambda r:r['object_key']),
        'policy':'仅清单；未引用可能属于尚未提交事务，不会自动删除。'}
