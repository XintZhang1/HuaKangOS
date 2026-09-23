"""Regression scenarios for handoff, evidence, precision and management reporting."""
import io,uuid,zipfile
from datetime import datetime,timedelta
from sqlalchemy import select
from app.db import SessionLocal,today
from app.models import User,UserStore
from app.flow_models import Case,Task,Customer,Item,Member,MemberEntry,FileAsset
from app.flow_documents import validate_upload
from app.analytics import build_snapshot,external_payload,source_revision
from app.reports import deterministic_text
from app.tenancy import set_scope
from fastapi import HTTPException
from tests.conftest import login,PASSWORD_HASH
from tests.test_workflow import create,action,detail,master,evidence,order,account,seed_car,approved_doc
import pytest

def add_user(role,name=None):
    with SessionLocal() as db:
        u=User(username=name or role,display_name='测试员工',role=role,password_hash=PASSWORD_HASH,must_change_password=False)
        db.add(u);db.flush();db.add(UserStore(user_id=u.id,store_id=1));db.commit();return u.id

def repair(c,payer='客户'):
    r=create(c,'repair',{'customer_name':'会员车主','customer_phone':'13900000055','plate':'沪A99999','repair_type':'一般维修','problem':'检查','due_date':today().isoformat()})
    r=action(c,r,'quote',{'labor':'100','parts':'0','discount':'0','labor_cost':'10','payer':payer,'work':'检查'})
    r=action(c,r,'authorize',{'evidence_id':evidence(c,r)});r=action(c,r,'start');r=action(c,r,'finish',{'result':'完成'});return action(c,r,'quality',{'evidence_id':evidence(c,r)})

def member(c):
    customer=master(c,'customers',{'name':'会员车主','phone':'13900000055','contact_allowed':True})
    m=master(c,'members',{'customer_id':customer['id'],'active':True})
    a=account(c);r=create(c,'member_topup',{'member_id':m['id'],'amount':'1000'})
    action(c,r,'topup_receive',{'account_id':a,'reference':uuid.uuid4().hex,'evidence_id':evidence(c,r)})
    return m,a

def test_new_roles_database_constraint(client):
    for role in ['reception','technician','customer_service']:
        add_user(role);assert login(client,role)['role']==role

def test_reassigned_sales_task_access(client):
    uid=add_user('sales','second_sales');x=order(client);x=action(client,x,'approve')
    t=next(t for t in detail(client,x)['tasks'] if t['key']=='sign')
    r=client.post(f"/api/flow/tasks/{t['id']}/assign",json={'version':t['version'],'assignee_id':uid,'reason':'调整接手人员'})
    assert r.status_code==200,r.text
    login(client,'second_sales');assert detail(client,x)['id']==x['id']
    assert client.get('/api/flow/tasks?scope=mine').json()['total']>=1
    assert any(r['id']==x['id'] for r in client.get('/api/flow/cases?kind=order').json()['items'])

def test_technician_can_open_inspection_task(client):
    add_user('technician');x=order(client);x=action(client,x,'approve');x=action(client,x,'allocate',{'vehicle_id':seed_car()})
    login(client,'technician');d=detail(client,x)
    assert 'amount_cents' not in d
    assert any(a['key']=='inspect' for a in d['actions'])

def test_finance_task_cannot_assign_to_manager(client):
    x=action(client,order(client),'approve');t=next(t for t in detail(client,x)['tasks'] if t['key']=='receive')
    with SessionLocal() as db:uid=db.scalar(select(User.id).where(User.role=='manager'))
    assert client.post(f"/api/flow/tasks/{t['id']}/assign",json={'version':t['version'],'assignee_id':uid,'reason':'不应成功'}).status_code==422

def test_report_combined_new_order_and_private_payload(client):
    x=order(client);x=action(client,x,'approve');x=action(client,x,'receive',{'amount':'100','account_id':account(client),'reference':'private-voucher','evidence_id':evidence(client,x)})
    with SessionLocal() as db:
        set_scope(db,[1],1);snap=build_snapshot(db,today());text=deterministic_text(snap)
        assert snap['workflow']['metrics']['cash_in_cents']==10000
        assert snap['workflow']['metrics']['new_orders']==1
        assert '新流程和既有记录合并' in text
        out=str(external_payload(snap));assert '测试客户' not in out and '13900000001' not in out and 'private-voucher' not in out

def test_report_revision_changes_on_non_cash_transition(client):
    x=order(client)
    with SessionLocal() as db:set_scope(db,[1],1);old=source_revision(db)
    action(client,x,'approve')
    with SessionLocal() as db:set_scope(db,[1],1);assert source_revision(db)>old

def test_internal_repair_not_customer_revenue_or_receivable(client):
    x=repair(client,'内部');action(client,x,'internal_settle',{'reason':'内部维护'});action(client,x,'release',{'evidence_id':evidence(client,x)})
    data=client.get('/api/flow/analytics').json();assert data['metrics']['repair_cents']==0 and data['metrics']['receivable_cents']==0

def test_repair_settlement_drilldown_matches_metric(client):
    x=repair(client);x=action(client,x,'receive',{'amount':'100','account_id':account(client),'reference':'r-001','evidence_id':evidence(client,x)})
    action(client,x,'release',{'evidence_id':evidence(client,x)})
    data=client.get('/api/flow/analytics').json();assert data['metrics']['repair_cents']==10000
    assert len(data['tables']['repair_settlements']['rows'])==1
    assert next(c for c in data['charts'] if c['id']=='repair_value')['table']=='repair_settlements'

def test_credit_due_updates_finance_task(client):
    x=repair(client);due=(today()+timedelta(days=30)).isoformat();action(client,x,'credit',{'due_date':due,'reason':'约定月结'})
    d=detail(client,x);t=next(t for t in d['tasks'] if t['key']=='receive');assert t['due_date']==due
    action(client,x,'release',{'evidence_id':evidence(client,x)});assert detail(client,x)['state']=='credit_open'

def test_member_approved_refund_reserves_spendable_balance(client):
    m,a=member(client);r=create(client,'member_refund',{'member_id':m['id'],'amount':'950','reason':'申请退款'});action(client,r,'approve')
    x=repair(client);action(client,x,'apply_balance',{'member_id':m['id'],'amount':'100','evidence_id':evidence(client,x)},409)
    action(client,r,'member_refund_pay',{'account_id':a,'reference':'member-refund','evidence_id':evidence(client,r)})
    row=client.get('/api/flow/master/members').json()['items'][0];assert row['balance_cents']==5000

def test_member_payment_is_not_second_cash_receipt(client):
    m,a=member(client);x=repair(client);action(client,x,'apply_balance',{'member_id':m['id'],'amount':'100','evidence_id':evidence(client,x)})
    d=client.get('/api/flow/analytics').json();assert d['metrics']['cash_in_cents']==100000
    assert d['metrics']['member_balance_cents']==90000 and d['metrics']['receivable_cents']==0
    assert len(d['tables']['member_entries']['rows'])==2

def test_member_date_uses_business_timezone(client):
    m,a=member(client)
    with SessionLocal() as db:
        # Core update only in test fixture: ledger remains immutable through product ORM.
        from sqlalchemy import text
        stamp=datetime.combine(today()-timedelta(days=1),datetime.min.time())+timedelta(hours=20)
        db.execute(text('UPDATE flow_member_entries SET occurred_at=:stamp'),{'stamp':stamp.isoformat(sep=' ')});db.commit()
    d=client.get('/api/flow/analytics?date_from='+today().isoformat()+'&date_to='+today().isoformat()).json()
    assert len(d['tables']['member_entries']['rows'])==1

def test_upload_duplicate_does_not_duplicate_file(client):
    x=order(client);url=f"/api/flow/cases/{x['id']}/files";data={'category':'evidence'}
    r=client.post(url,data=data,files={'file':('照片说明.txt',b'same content','text/plain')});assert r.status_code==200
    r2=client.post(url,data=data,files={'file':('照片说明.txt',b'same content','text/plain')});assert r2.json()['id']==r.json()['id']

def test_signature_cannot_reference_other_order(client):
    x=order(client);y=order(client);source=approved_doc(client,x,'contract')
    r=client.post(f"/api/flow/cases/{y['id']}/files",data={'category':'signed_contract','source_file_id':str(source)},files={'file':('签回.txt',b'evidence','text/plain')})
    assert r.status_code==422

@pytest.mark.parametrize('name,content',[('run.html',b'<html>bad</html>'),('fake.png',b'not an image'),('invalid.docx',b'not a zip'),('bad.txt',b'\x00binary')])
def test_bad_evidence_types_rejected(name,content):
    with pytest.raises(HTTPException):validate_upload(name,content)

def test_cannot_change_fen_precision(client):
    create(client,'order',{'customer_name':'客户','model':'车型','amount':'10.001','delivery_due':today().isoformat()},422)

def test_stock_count_stale_rejected(client):
    item=master(client,'items',{'sku':'COUNT','name':'盘点物资','unit':'件','reorder':'0','active':True})
    count=create(client,'stock_count',{'item_id':item['id'],'counted':'2','reason':'清点'})
    p=create(client,'purchase',{'item_id':item['id'],'quantity':'3','unit_cost':'1','supplier':'供货商'});action(client,p,'approve');action(client,p,'stock_in',{'evidence_id':evidence(client,p)})
    action(client,count,'count_approve',{'evidence_id':evidence(client,count)},409)

def test_invoice_cumulative_amount_capped(client):
    x=order(client,amount='100');v={'related_case_id':x['id'],'invoice_title':'测试客户','amount':'80'}
    create(client,'invoice',v);create(client,'invoice',v,409)

def test_no_contact_customer_can_only_close_callback(client):
    cb=create(client,'callback',{'customer_name':'勿联系','customer_phone':'13900000000','topic':'购车回访','due_date':today().isoformat()})
    with SessionLocal() as db:
        cust=db.get(Customer,cb['customer_id']);cust.contact_allowed=False;db.commit()
    action(client,cb,'callback_later',{'due_date':today().isoformat(),'result':'不得强制安排'},409)
    action(client,cb,'close',{'reason':'客户不愿继续联系'})


def test_default_workflow_mode_blocks_legacy_business_writes(client,monkeypatch):
    from dataclasses import replace
    import app.main as module
    monkeypatch.setattr(module,'settings',replace(module.settings,legacy_business_write=False))
    for kind in ['vehicles','sales','repairs','policies']:
        assert client.post('/api/records/'+kind,json={}).status_code==409

def test_production_forbids_legacy_write_switch():
    from dataclasses import replace
    from app.config import settings
    with pytest.raises(ValueError):replace(settings,environment='production',cookie_secure=True,allowed_hosts=('example.com',),legacy_business_write=True)
