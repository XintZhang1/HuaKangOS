"""Synthetic local objects only: no external storage, company DB or real scanner."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,os,sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app import private_files as storage,file_security
from app.private_file_models import PrivateFileObject
from app.private_file_backup import validate_connection_files,create_bundle,validate_bundle,restore_bundle
from app.flow_models import FileAsset,Case
from app.models import Store,User
from app.db import SessionLocal,make_engine
from app.tenancy import set_scope
from tests.conftest import TEST_DIR,login
from tests.test_workflow import order,action,approved_doc,seed_car
from tests.test_file_security import upload,scan


@pytest.fixture
def private(monkeypatch,tmp_path):
    root=tmp_path/'original-objects'
    monkeypatch.setattr(storage,'settings',SimpleNamespace(file_storage_mode='private_local',private_file_root=str(root)))
    return root


def reference(file):
    with SessionLocal() as db:
        obj=db.scalar(select(PrivateFileObject).where(PrivateFileObject.file_id==file['id']))
        assert obj is not None
        return obj


def test_private_upload_dedup_blob_compatibility_and_scoped_original_bytes(client,private,monkeypatch):
    case=order(client);file=upload(client,case,b'private original')
    obj=reference(file)
    assert upload(client,case,b'private original')['id']==file['id']
    assert client.get('/api/flow/files/'+str(file['id'])).content==b'private original'
    with SessionLocal() as db:
        assert db.scalar(select(FileAsset.content).where(FileAsset.id==file['id']))==b''
        assert db.scalar(select(func.count()).select_from(PrivateFileObject).where(PrivateFileObject.file_id==file['id']))==1
        db.add(Store(id=2,code='OBJECT-SECOND',name='合成对象二店'));db.commit()
    assert client.get('/api/flow/files/'+str(file['id']),headers={'X-Store-ID':'2'}).status_code==404
    assert client.get('/api/flow/files/'+str(file['id']),headers={'X-Store-ID':'all'}).status_code==200
    assert str(private) not in json.dumps(file,ensure_ascii=False) and obj.object_key not in json.dumps(file)
    monkeypatch.setattr(storage,'settings',SimpleNamespace(file_storage_mode='blob',private_file_root=str(private)))
    legacy=upload(client,case,b'legacy BLOB compatible')
    assert client.get('/api/flow/files/'+str(legacy['id'])).content==b'legacy BLOB compatible'
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        result=validate_connection_files(db,private)
        assert result['verified_private_objects']>=1 and result['verified_blob_files']==1
        with pytest.raises(ValueError,match='配套对象目录'):validate_connection_files(db)


def test_quarantine_actual_object_and_tamper_fail_closed(client,private,monkeypatch):
    monkeypatch.setattr(file_security,'settings',replace(file_security.settings,file_scan_mode='quarantine'))
    case=order(client);file=upload(client,case,b'quarantine bytes')
    obj=reference(file);assert storage.read_object(private,obj.object_key,1,obj.size,obj.sha256)==b'quarantine bytes'
    assert file['security']['state']=='quarantined'
    assert client.get('/api/flow/files/'+str(file['id'])).status_code==409
    monkeypatch.setattr(file_security,'settings',replace(file_security.settings,file_scan_mode='structure_only'))
    assert scan(client,file['id'])['security']['can_use']
    path=storage.object_path(private,obj.object_key,1);path.write_bytes(b'changed')
    assert client.get('/api/flow/files/'+str(file['id'])).status_code==409
    result=scan(client,file['id']);assert result['security']['state']=='rejected' and not result['security']['can_use']
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        with pytest.raises(ValueError,match='摘要'):validate_connection_files(db,private)


def test_original_generated_object_is_required_for_signature_confirmation(client,private):
    case=action(client,order(client),'approve');case=action(client,case,'allocate',{'vehicle_id':seed_car()})
    source_id=approved_doc(client,case,'contract')
    signed=upload(client,case,b'actual synthetic signature','signed_contract',source_id)
    obj=reference({'id':source_id});path=storage.object_path(private,obj.object_key,1)
    original=path.read_bytes();path.unlink()
    result=action(client,case,'sign',{'evidence_id':signed['id']},409)
    assert '附件' in result['detail']
    path.write_bytes(original)
    assert action(client,case,'sign',{'evidence_id':signed['id']})['state'] in {'executing','awaiting_execution'}
    login(client,'inventory');assert client.get('/api/flow/files/'+str(source_id)).status_code==403


def test_publication_failure_never_persists_file_or_scan(client,private,monkeypatch):
    case=order(client)
    with SessionLocal() as db:before=db.scalar(select(func.count()).select_from(FileAsset))
    def unavailable(*args,**kwargs):raise OSError('synthetic disk failure')
    monkeypatch.setattr(storage.os,'link',unavailable)
    upload(client,case,b'failed disk',status=503)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(FileAsset))==before
    assert not list((private/'staging').glob('*'))


def test_rollback_leaves_only_auditable_orphan_never_committed_reference(client,private):
    case=order(client)
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='admin'))
        content=b'rollback-only';asset=FileAsset(case_id=case['id'],category='evidence',name='回滚凭据.txt',media_type='text/plain; charset=utf-8',
            sha256=hashlib.sha256(content).hexdigest(),size=len(content),content=content,created_by=user.id)
        storage.store_content(db,asset,content);obj=db.scalar(select(PrivateFileObject).where(PrivateFileObject.file_id==asset.id));key=obj.object_key
        db.rollback()
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        orphan=storage.audit_orphans(db,private)
        assert key in {x['object_key'] for x in orphan['orphans']}
        assert db.execute('SELECT count(*) FROM private_file_objects WHERE object_key=?',(key,)).fetchone()[0]==0
    assert storage.object_path(private,key,1).exists()


@pytest.mark.parametrize('key',['../escape','objects/store-1/../../escape','objects/store-2/'+'a'*32+'.blob','/absolute','objects\\store-1\\x.blob'])
def test_path_traversal_and_cross_store_object_keys_rejected(private,key):
    private.mkdir()
    with pytest.raises(ValueError):storage.read_object(private,key,1,1,hashlib.sha256(b'x').hexdigest())


def test_symlink_file_and_root_rejected(private,tmp_path):
    root=private;root.mkdir();content=b'x';digest=hashlib.sha256(content).hexdigest()
    key=storage.publish(root,1,content,1,digest);path=storage.object_path(root,key,1)
    outside=tmp_path/'outside';outside.write_bytes(content);path.unlink()
    try:path.symlink_to(outside)
    except OSError:pytest.skip('This Windows host does not permit symlink creation')
    with pytest.raises(ValueError,match='链接|重解析'):storage.read_object(root,key,1,1,digest)
    alias=tmp_path/'linked-root';alias.symlink_to(root,target_is_directory=True)
    with pytest.raises(ValueError,match='链接|重解析'):storage.private_root(alias)


@pytest.mark.skipif(os.name!='nt',reason='Windows junction guard')
def test_windows_junction_directory_is_rejected(private,tmp_path):
    import _winapi
    private.mkdir();alias=tmp_path/'junction-root'
    _winapi.CreateJunction(str(private),str(alias))
    try:
        with pytest.raises(ValueError,match='链接|重解析'):storage.private_root(alias)
        # A redirected parent inside the otherwise valid root is also refused.
        outside=tmp_path/'outside-directory';outside.mkdir()
        _winapi.CreateJunction(str(outside),str(private/'objects'))
        with pytest.raises(ValueError,match='链接|重解析'):storage.publish(private,1,b'x',1,hashlib.sha256(b'x').hexdigest())
    finally:
        # Remove only the link itself, never recursively traverse its target.
        if alias.exists():os.rmdir(alias)
        if (private/'objects').exists():os.rmdir(private/'objects')


def test_object_reference_immutable_and_offline_tamper_rejected(client,private):
    file=upload(client,order(client));obj=reference(file)
    with SessionLocal() as db:
        original=db.scalar(select(PrivateFileObject).where(PrivateFileObject.id==obj.id));original.size+=1
        with pytest.raises(HTTPException):db.flush()
        db.rollback()
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as db:
        source.backup(db);validate_connection_files(db,private)
        db.execute('UPDATE private_file_objects SET store_id=2 WHERE id=?',(obj.id,))
        with pytest.raises(ValueError,match='门店'):validate_connection_files(db,private)


def test_complete_bundle_restore_from_new_root_and_missing_corrupt_manifest_refused(client,private,tmp_path,monkeypatch):
    case=order(client);file=upload(client,case,b'restored original bytes');obj=reference(file)
    result=create_bundle((TEST_DIR/'test.sqlite').resolve(),private,tmp_path/'bundle')
    assert result['verified_private_objects']>=2
    assert validate_bundle(tmp_path/'bundle')['verified_files']==result['verified_files']
    restored=restore_bundle(tmp_path/'bundle',tmp_path/'restored')
    assert Path(restored['object_root'])!=private
    restored_engine=make_engine('sqlite:///'+restored['database_path'])
    from sqlalchemy.orm import Session
    with Session(restored_engine) as db:
        set_scope(db,[1],1);asset=db.scalar(select(FileAsset).where(FileAsset.id==file['id']))
        assert storage.read_content(db,asset,restored['object_root'])==b'restored original bytes'
        assert file_security.security_info(db,asset)['can_use']
        assert db.scalar(select(Case).where(Case.id==case['id'])).number==case['number']
    restored_engine.dispose()
    with pytest.raises(ValueError,match='已存在'):restore_bundle(tmp_path/'bundle',tmp_path/'restored')
    stored=storage.object_path(tmp_path/'bundle'/'object_store',obj.object_key,1);stored.write_bytes(b'tamper')
    with pytest.raises(ValueError,match='摘要'):validate_bundle(tmp_path/'bundle')
    stored.write_bytes(b'restored original bytes');(tmp_path/'bundle'/'COMPLETE').unlink()
    with pytest.raises(ValueError):validate_bundle(tmp_path/'bundle')


def test_sqlalchemy_transfer_verification_requires_same_original_objects(client,private):
    upload(client,order(client))
    from app.db import engine
    with engine.connect() as conn:
        assert validate_connection_files(conn,private)['verified_private_objects']>=2
        with pytest.raises(ValueError,match='配套对象目录'):validate_connection_files(conn)


def test_signed_source_restore_refuses_other_case_and_wrong_generated_kind(client,private):
    first=order(client);source=approved_doc(client,first,'contract');signed=upload(client,first,b'signed source','signed_contract',source)
    second=order(client);other=approved_doc(client,second,'contract')
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as db:
        original.backup(db);validate_connection_files(db,private)
        db.execute('UPDATE flow_files SET source_file_id=? WHERE id=?',(other,signed['id']))
        with pytest.raises(ValueError,match='签回'):validate_connection_files(db,private)
        db.execute('UPDATE flow_files SET source_file_id=? WHERE id=?',(source,signed['id']))
        db.execute("UPDATE flow_files SET category='handover' WHERE id=?",(source,))
        with pytest.raises(ValueError,match='签回'):validate_connection_files(db,private)


def test_competing_publications_never_overwrite_original_objects(private):
    content=b'concurrent synthetic file';digest=hashlib.sha256(content).hexdigest()
    with ThreadPoolExecutor(max_workers=2) as pool:keys=list(pool.map(lambda _:storage.publish(private,1,content,len(content),digest),range(2)))
    assert len(set(keys))==2
    for key in keys:assert storage.read_object(private,key,1,len(content),digest)==content


def test_published_key_collision_does_not_replace_original_or_delete_other_staging(private,monkeypatch):
    token='a'*32;monkeypatch.setattr(storage.uuid,'uuid4',lambda:SimpleNamespace(hex=token))
    digest=hashlib.sha256(b'original').hexdigest();key=storage.publish(private,1,b'original',8,digest)
    with pytest.raises(OSError):storage.publish(private,1,b'changed!',8,hashlib.sha256(b'changed!').hexdigest())
    assert storage.read_object(private,key,1,8,digest)==b'original'
    stage=private/'staging'/(token+'.part');stage.write_bytes(b'other in-flight operation')
    with pytest.raises(OSError):storage.publish(private,1,b'changed!',8,hashlib.sha256(b'changed!').hexdigest())
    assert stage.read_bytes()==b'other in-flight operation'


def test_legacy_blob_verification_memory_is_bounded_by_one_file():
    import tracemalloc
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE flow_files(sha256 TEXT,size INTEGER,content BLOB)')
        content=b'x'*(1024*1024);digest=hashlib.sha256(content).hexdigest()
        db.executemany('INSERT INTO flow_files VALUES(?,?,?)',[(digest,len(content),content)]*16)
        tracemalloc.start()
        try:
            assert validate_connection_files(db)['verified_blob_files']==16
            assert tracemalloc.get_traced_memory()[1]<6*1024*1024
        finally:tracemalloc.stop()


def test_private_root_rejects_project_and_relative_paths(private):
    for path in ['relative/files',storage.ROOT/'web'/'files',storage.ROOT.parent]:
        with pytest.raises(ValueError):storage.private_root(path,True)
