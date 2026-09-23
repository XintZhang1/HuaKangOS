import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func
from fastapi import HTTPException
from app.db import SessionLocal, today
from app.models import Store, User, UserStore, CashEntry
from app.flow_models import Item, Case, StockMove, FileAsset, Task
from app.tenancy import set_scope, project_user
from app.transfer_models import MaterialTransfer, TransferLine, TransferMovement, TransferSettlement
from app import transfer_service as svc
from app.file_security import initialize_file_security
from .conftest import login, PASSWORD_HASH


@pytest.fixture(autouse=True)
def historical_second_version(monkeypatch):
    # This module protects the already-published v2 contract. The public create
    # API now always uses v3; only this synthetic history fixture pins v2.
    monkeypatch.setattr(svc,'NEW_TRANSFER_VERSION',2)


def seed():
    with SessionLocal() as db:
        db.add_all([Store(id=2,code='SECOND',name='调入门店'),Store(id=3,code='THIRD',name='无关门店')]);db.flush()
        for user in db.scalars(select(User)):
            db.add(UserStore(user_id=user.id,store_id=2,role=user.role if user.role!='admin' else None))
        a=Item(store_id=1,sku='PART-A',name='测试滤芯',unit='件',quantity_milli=3000,inventory_value_cents=100,unit_cost_cents=33)
        b=Item(store_id=2,sku='LOCAL-A',name='测试滤芯',unit='件',quantity_milli=0,inventory_value_cents=0,unit_cost_cents=0)
        db.add_all([a,b]);db.commit();return a.id,b.id


def switch(client,sid):client.headers['X-Store-ID']=str(sid)
def get(client,row):return client.get(f"/api/transfers/{row['id']}").json()
def create(client,item,status=201):
    response=client.post('/api/transfers',json={'request_id':uuid.uuid4().hex,'destination_store_id':2,
        'due_date':today().isoformat(),'reason':'调剂两店备件','lines':[{'item_id':item,'quantity_milli':3000}]})
    assert response.status_code==status,response.text
    return response.json()
def command(client,row,action,values=None,status=200,key=None,original=None):
    latest=original or get(client,row)
    if action=='return_receive' and latest.get('flow_version')==3:
        values={**(values or {}),'passed':(values or {}).get('passed',True)}
    body={'request_id':key or uuid.uuid4().hex,'version':latest['version'],'case_version':latest['case_version'],'values':values or {'reason':'本店核对确认'}}
    response=client.post(f"/api/transfers/{row['id']}/actions/{action}",json=body)
    assert response.status_code==status,response.text
    return response.json()
def upload(client,row):
    cid=get(client,row)['case_id']
    response=client.post(f'/api/flow/cases/{cid}/files',files={'file':('交接凭据.txt','模拟实际交接凭据'.encode(),'text/plain')},data={'category':'evidence'})
    assert response.status_code==200,response.text
    return response.json()['id']
def approved(client,item):
    login(client,'inventory');row=create(client,item)
    login(client,'manager');command(client,row,'approve')
    switch(client,2);command(client,row,'approve')
    switch(client,1);login(client,'inventory');return row


def test_transfer_two_store_partial_accept_reject_return_value_conservation(client):
    a,b=seed();row=approved(client,a);proof=upload(client,row)
    dispatched=command(client,row,'dispatch',{'evidence_id':proof,'reason':'实物已交物流'})
    assert dispatched['status']=='transit'
    switch(client,2);proof_b=upload(client,row);line=get(client,row)['lines'][0]['id']
    received=command(client,row,'receive',{'evidence_id':proof_b,'reason':'两件合格一件破损',
        'lines':[{'line_id':line,'item_id':b,'accept_milli':1000,'reject_milli':1000}]})
    assert received['lines'][0]['accepted_milli']==1000 and received['lines'][0]['uninspected_milli']==1000
    rejected=next(m for m in received['movements'] if m['kind']=='reject')
    shipped=command(client,row,'return_ship',{'evidence_id':proof_b,'reason':'拒收件退回原店','rejection_id':rejected['id']})
    shipment=next(m for m in shipped['movements'] if m['kind']=='return_ship')
    command(client,row,'receive',{'evidence_id':proof_b,'reason':'其余实物验收完毕',
        'lines':[{'line_id':line,'item_id':b,'accept_milli':1000,'reject_milli':0}]})
    switch(client,1)
    partial=command(client,row,'return_receive',{'evidence_id':proof,'reason':'先接收半件测试量','shipment_id':shipment['id'],'quantity_milli':500})
    assert partial['status']=='transit'
    final=command(client,row,'return_receive',{'evidence_id':proof,'reason':'余量已接收','shipment_id':shipment['id'],'quantity_milli':500})
    assert final['status']=='completed'
    with SessionLocal() as db:
        items=list(db.scalars(select(Item)))
        assert sum(x.quantity_milli for x in items)==3000
        assert sum(x.inventory_value_cents for x in items)==100
        assert db.scalar(select(Item.inventory_value_cents).where(Item.id==a))==33
        assert db.scalar(select(Item.inventory_value_cents).where(Item.id==b))==67
        assert db.scalar(select(func.sum(StockMove.value_cents)))==0
        assert db.scalar(select(func.sum(StockMove.quantity_milli)))==0
        assert db.scalar(select(func.sum(TransferSettlement.amount_cents)))==0
        assert db.scalar(select(func.count()).select_from(CashEntry))==0
        assert db.scalar(select(func.sum(TransferSettlement.amount_cents)).where(TransferSettlement.store_id==1))==67


def test_transfer_permissions_approval_cancel_and_tenant_boundaries(client):
    a,b=seed();login(client,'sales');create(client,a,403)
    login(client,'inventory');row=create(client,a);proof=upload(client,row)
    command(client,row,'dispatch',{'evidence_id':proof,'reason':'提前发出不允许'},409)
    command(client,row,'approve',status=403)
    switch(client,2);command(client,row,'cancel',status=403)
    login(client,'manager');command(client,row,'reject_request')
    switch(client,1);assert get(client,row)['status']=='cancelled'
    login(client,'admin');switch(client,3)
    assert client.get(f"/api/transfers/{row['id']}").status_code==404
    assert client.get(f'/api/flow/files/{proof}').status_code==404
    switch(client,'all');assert client.get('/api/transfers').status_code==409
    assert client.post('/api/transfers',json={}).status_code==409
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(StockMove))==0


def test_transfer_duplicate_stale_and_over_receive_do_not_post_twice(client):
    a,b=seed();row=approved(client,a);proof=upload(client,row);before=get(client,row);key=uuid.uuid4().hex
    values={'evidence_id':proof,'reason':'正常发出确认'}
    first=command(client,row,'dispatch',values,key=key,original=before)
    assert command(client,row,'dispatch',values,key=key,original=before)==first
    command(client,row,'dispatch',values,status=409,original=before)
    switch(client,2);proof_b=upload(client,row);line=get(client,row)['lines'][0]['id']
    command(client,row,'receive',{'evidence_id':proof_b,'reason':'超额验收不得过账',
        'lines':[{'line_id':line,'item_id':b,'accept_milli':3001,'reject_milli':0}]},409)
    command(client,row,'receive',{'evidence_id':proof_b,'reason':'不能引用他店物资',
        'lines':[{'line_id':line,'item_id':a,'accept_milli':1000,'reject_milli':0}]},422)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(StockMove))==1
        assert db.scalar(select(Item.quantity_milli).where(Item.id==b))==0


def test_transfer_competing_dispatch_and_stock_issue_preserve_quantity(client):
    a,b=seed();row=approved(client,a);proof=upload(client,row)
    # Another operation changes the stock after approval. Dispatch cannot invent it.
    with SessionLocal() as db:
        item=db.scalar(select(Item).where(Item.id==a));item.quantity_milli=2000;item.inventory_value_cents=67;db.commit()
    command(client,row,'dispatch',{'evidence_id':proof,'reason':'审批后库存不足'},409)
    assert get(client,row)['status']=='approved'
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(StockMove))==0


def test_transfer_concurrent_receivers_only_one_can_confirm_same_version(client):
    a,b=seed();row=approved(client,a);proof=upload(client,row)
    command(client,row,'dispatch',{'evidence_id':proof,'reason':'先发货再验收'})
    switch(client,2);proof_b=upload(client,row);current=get(client,row)
    values={'evidence_id':proof_b,'reason':'并发验收测试','lines':[{'line_id':current['lines'][0]['id'],'item_id':b,'accept_milli':3000,'reject_milli':0}]}
    def run(_):
        with SessionLocal() as db:
            set_scope(db,[2],2);user=project_user(db.scalar(select(User).where(User.username=='inventory')),'inventory')
            try:
                svc.command(db,user,row['id'],uuid.uuid4().hex,current['version'],current['case_version'],'receive',values)
                return 200
            except HTTPException as error:return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(run,range(2)))==[200,409]
    with SessionLocal() as db:
        assert db.scalar(select(Item.quantity_milli).where(Item.id==b))==3000
        assert db.scalar(select(func.count()).select_from(TransferSettlement))==2


def test_transfer_central_access_and_immutable_facts(client):
    a,b=seed();row=approved(client,a)
    with SessionLocal() as db:
        with pytest.raises(HTTPException):db.scalar(select(MaterialTransfer))
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='admin'))
        with svc.authority(db,user):
            line=db.scalar(select(TransferLine).where(TransferLine.transfer_id==row['id']));line.quantity_milli=1
            with pytest.raises(HTTPException):db.flush()
        db.rollback()


def test_transfer_report_chart_table_csv_and_internal_elimination(client):
    a,b=seed();row=approved(client,a);proof=upload(client,row)
    command(client,row,'dispatch',{'evidence_id':proof,'reason':'有在途价值待验收'})
    login(client,'manager')
    result=client.get('/api/flow/analytics').json()
    chart=next(c for c in result['charts'] if c['id']=='transfer_transit')
    assert sum(chart['series'][0]['values'])==100==sum(r['amount_cents'] for r in result['tables']['transfer_transit']['rows'])
    assert result['metrics']['material_in_transit_cents']==100
    switch(client,2);login(client,'inventory');proof_b=upload(client,row);line=get(client,row)['lines'][0]['id']
    command(client,row,'receive',{'evidence_id':proof_b,'reason':'部分合格入库',
        'lines':[{'line_id':line,'item_id':b,'accept_milli':1000,'reject_milli':0}]})
    login(client,'admin');switch(client,'all');result=client.get('/api/flow/analytics').json()
    assert result['metrics']['material_in_transit_cents']==67
    assert result['metrics']['material_cost_cents']==33
    assert result['metrics']['interstore_material_net_cents']==0
    assert result['metrics']['cash_in_cents']==result['metrics']['cash_out_cents']==0
    assert sum(r['amount_cents'] for r in result['tables']['transfer_clearing']['rows'])==0
    exported=client.get('/api/flow/analytics/export?dataset=transfer_transit')
    assert exported.status_code==200 and '0.67' in exported.text


def test_transfer_restore_preserves_nonempty_transit_and_detects_tampering(client):
    import sqlite3
    from app.backup_integrity import validate_sqlite
    from .conftest import TEST_DIR
    a,b=seed();row=approved(client,a);proof=upload(client,row)
    command(client,row,'dispatch',{'evidence_id':proof,'reason':'保留在途与已验收'})
    switch(client,2);proof_b=upload(client,row);line=get(client,row)['lines'][0]['id']
    command(client,row,'receive',{'evidence_id':proof_b,'reason':'部分验收及拒收',
        'lines':[{'line_id':line,'item_id':b,'accept_milli':1000,'reject_milli':1000}]})
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored)
        assert validate_sqlite(restored)['verified_files']==2
        restored.execute('UPDATE material_transfer_settlements SET amount_cents=999 WHERE id=(SELECT MIN(id) FROM material_transfer_settlements)')
        with pytest.raises(ValueError,match='往来不配对'):validate_sqlite(restored)


def test_transfer_partial_receipt_and_other_store_return_preserve_explicit_assignee(client):
    a,b=seed()
    with SessionLocal() as db:
        extra=User(username='second-stock',display_name='第二名库管',role='inventory',password_hash=PASSWORD_HASH,must_change_password=False)
        db.add(extra);db.flush();db.add(UserStore(user_id=extra.id,store_id=2,role='inventory'));db.commit();extra_id=extra.id
    row=approved(client,a);proof=upload(client,row)
    command(client,row,'dispatch',{'evidence_id':proof,'reason':'保持办理责任人'})
    switch(client,2);proof_b=upload(client,row);detail=get(client,row);line=detail['lines'][0]['id']
    task=next(t for t in client.get(f"/api/flow/cases/{detail['case_id']}").json()['tasks'] if t['key']=='transfer_receive')
    received=command(client,row,'receive',{'evidence_id':proof_b,'reason':'分批验收保留责任人',
        'lines':[{'line_id':line,'item_id':b,'accept_milli':1000,'reject_milli':1000}]})
    current=next(t for t in client.get(f"/api/flow/cases/{detail['case_id']}").json()['tasks'] if t['key']=='transfer_receive')
    assert current['assignee_id']==task['assignee_id'] and current['due_date']==task['due_date']
    rejection=next(m for m in received['movements'] if m['kind']=='reject')
    shipped=command(client,row,'return_ship',{'evidence_id':proof_b,'reason':'拒收后发运退回','rejection_id':rejection['id']})
    shipment=next(m for m in shipped['movements'] if m['kind']=='return_ship')
    login(client,'manager');current=next(t for t in client.get(f"/api/flow/cases/{detail['case_id']}").json()['tasks'] if t['key']=='transfer_receive')
    result=client.post(f"/api/flow/tasks/{current['id']}/assign",json={'version':current['version'],'assignee_id':extra_id,'reason':'交班给另一名库管'})
    assert result.status_code==200,result.text
    switch(client,1);login(client,'inventory')
    command(client,row,'return_receive',{'evidence_id':proof,'reason':'另一门店退回已到','shipment_id':shipment['id'],'quantity_milli':1000})
    switch(client,2);current=next(t for t in client.get(f"/api/flow/cases/{detail['case_id']}").json()['tasks'] if t['key']=='transfer_receive')
    assert current['assignee_id']==extra_id
    values={'evidence_id':proof_b,'reason':'交班后接收剩余量','lines':[{'line_id':line,'item_id':b,'accept_milli':1000,'reject_milli':0}]}
    command(client,row,'receive',values,403)
    login(client,'second-stock');assert command(client,row,'receive',values)['status']=='completed'
