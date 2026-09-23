from datetime import timedelta, datetime, time
from decimal import Decimal
from dataclasses import replace
import json
from unittest.mock import patch
from pathlib import Path
import csv
import io
import httpx
import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient
from app.db import SessionLocal, today, make_engine
from app.main import app
from app.models import User, Vehicle, Sale, DailyReport, Finding, LoginSession, AuditLog, MODULES
from app.analytics import load_data, daily_metrics, build_snapshot, external_payload, detect, source_revision
from app.reports import generate_report, ask_deepseek
from app import reports, analytics
from tests.conftest import login, PASSWORD, TEST_DIR


def vehicle_body(**updates):
    result={'doc_no':'TEST-V-001','business_date':str(today()-timedelta(days=15)),
        'vin':'LDD00000000000001','brand':'测试品牌','model':'测试车型','purchase_cost':'100000.00','list_price':'120000.00'}
    result.update(updates);return result


def sale_body(vehicle_id,**updates):
    result={'doc_no':'TEST-S-001','business_date':str(today()-timedelta(days=5)),'vehicle_id':vehicle_id,
        'customer_name':'客户机密','customer_phone':'13800000000','salesperson':'销售机密','sale_stage':'delivered',
        'delivery_date':str(today()-timedelta(days=4)),'contract_amount':'110000.00','note':'绝不应外发的自由文本'}
    result.update(updates);return result


def cash_body(**updates):
    result={'doc_no':'TEST-C-001','business_date':str(today()),'direction':'out','category':'operating_expense','amount':'100.00',
        'account':'账户机密','counterparty':'交易对方机密','payment_method':'bank','voucher_no':'凭证机密','related_type':'none'}
    result.update(updates);return result


def policy_body(**updates):
    result={'doc_no':'TEST-P-001','business_date':str(today()),'policy_number':'保单编号机密','insurer':'保险机构机密',
        'plate_number':'沪A12345','customer_name':'客户机密','start_date':str(today()),'end_date':str(today()+timedelta(days=365)),
        'premium':'10000.00','commission':'1000.00'}
    result.update(updates);return result


def create(client,module,body):
    r=client.post('/api/records/'+module,json=body)
    assert r.status_code==201,r.text
    return r.json()


def action(client,module,row,name,**kwargs):
    r=client.post(f'/api/records/{module}/{row["id"]}/actions/{name}',json={'version':row['version'],'reason':'测试已核对原始资料',**kwargs})
    assert r.status_code==200,r.text
    return r.json()


def approve(client,module,body):
    row=create(client,module,body);row=action(client,module,row,'submit');return action(client,module,row,'approve')


def car(client,**kwargs): return approve(client,'vehicles',vehicle_body(**kwargs))


def sale(client,**kwargs):
    v=car(client)
    return approve(client,'sales',sale_body(v['id'],**kwargs))


def test_authenticated_health_and_shell(client):
    assert client.get('/api/health').json()['status']=='ok'
    r=client.get('/');assert r.status_code==200 and '门店经营台' in r.text
    assert "script-src 'self'" in r.headers['content-security-policy']


@pytest.mark.parametrize('path',['/api/records/sales','/api/records/cash','/api/dashboard','/api/reports','/api/findings','/api/audit','/api/users'])
def test_auth_required(client,path):
    client.cookies.clear();assert client.get(path).status_code==401


def test_password_and_tokens_hashed(client):
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.username=='admin'))
        session=db.scalar(select(LoginSession).where(LoginSession.user_id==user.id))
        assert user.password_hash.startswith('$argon2id$') and PASSWORD not in user.password_hash
        assert session.id != client.cookies.get('dealer_session')
        assert session.csrf_hash != client.cookies.get('dealer_csrf')
    assert 'HttpOnly' in client.post('/api/auth/login',headers={'X-App-Request':'1'},json={'username':'admin','password':PASSWORD}).headers.get('set-cookie','')


def test_login_throttled(client):
    for _ in range(10):
        r=client.post('/api/auth/login',headers={'X-App-Request':'1'},json={'username':'nobody','password':'wrong'})
        assert r.status_code==401
    assert client.post('/api/auth/login',headers={'X-App-Request':'1'},json={'username':'nobody','password':'wrong'}).status_code==429


def test_csrf_required(client):
    client.headers.pop('X-CSRF-Token');assert client.post('/api/records/vehicles',json=vehicle_body()).status_code==403


def test_cross_origin_denied(client):
    r=client.post('/api/records/vehicles',json=vehicle_body(),headers={'Origin':'https://attacker.invalid'})
    assert r.status_code==403


def test_non_json_denied(client):
    r=client.post('/api/records/vehicles',content='{}',headers={'Content-Type':'text/plain'})
    assert r.status_code==415


def test_oversized_body_denied(client):
    r=client.post('/api/records/vehicles',json={'note':'x'*100001})
    assert r.status_code==413


@pytest.mark.parametrize('role,module',[('sales','cash'),('finance','vehicles'),('service','sales'),('inventory','policies'),('auditor','cash')])
def test_backend_write_rbac(client,role,module):
    login(client,role)
    assert client.post('/api/records/'+module,json={}).status_code==403


@pytest.mark.parametrize('path',['/api/dashboard','/api/reports','/api/findings','/api/audit','/api/users','/api/settings','/api/export/sales'])
def test_sales_cannot_access_whole_store(client,path):
    login(client,'sales');assert client.get(path).status_code==403


def test_cost_redaction_and_inventory_scope(client):
    v=car(client);s=approve(client,'sales',sale_body(v['id']))
    draft=create(client,'vehicles',vehicle_body(doc_no='DRAFT-V',vin='LDD00000000000002'))
    login(client,'sales')
    vehicle=client.get(f'/api/records/vehicles/{v["id"]}').json()
    assert 'purchase_cost_cents' not in vehicle and 'purchase_cost' not in vehicle and 'note' not in vehicle
    record=client.get(f'/api/records/sales/{s["id"]}').json()
    assert 'purchase_cost_snapshot_cents' not in record and 'purchase_cost_snapshot' not in record
    assert client.get(f'/api/records/vehicles/{draft["id"]}').status_code==404


@pytest.mark.parametrize('field,value',[('created_by',99),('approval_state','approved'),('active_vehicle_id',1)])
def test_mass_assignment_denied(client,field,value):
    body=vehicle_body(**{field:value});assert client.post('/api/records/vehicles',json=body).status_code==422


def test_staff_only_edits_own_draft(client):
    v=create(client,'vehicles',vehicle_body())
    login(client,'inventory')
    assert client.put(f'/api/records/vehicles/{v["id"]}',json={'version':v['version'],'data':vehicle_body(model='侵入修改')}).status_code==403


def test_separation_of_entry_and_approval(client):
    login(client,'manager');v=create(client,'vehicles',vehicle_body());v=action(client,'vehicles',v,'submit')
    r=client.post(f'/api/records/vehicles/{v["id"]}/actions/approve',json={'version':v['version'],'reason':'审核自己的单据'})
    assert r.status_code==403
    login(client,'admin');v=action(client,'vehicles',v,'approve');assert v['approval_state']=='approved'


def test_admin_self_approval_explicitly_logged(client):
    v=car(client)
    logs=client.get('/api/audit').json()['items']
    assert any('[管理员自审]' in x['reason'] and x['entity_id']==v['id'] for x in logs)


def test_approved_money_immutable(client):
    v=car(client)
    assert client.put(f'/api/records/vehicles/{v["id"]}',json={'version':v['version'],'data':vehicle_body(purchase_cost='1.00')}).status_code==409
    assert client.get(f'/api/records/vehicles/{v["id"]}').json()['purchase_cost_cents']==10000000


@pytest.mark.parametrize('amount',['NaN','Infinity','-1.00','1.234','10000000000.00'])
def test_invalid_money_rejected(client,amount):
    assert client.post('/api/records/vehicles',json=vehicle_body(purchase_cost=amount)).status_code==422


def test_integer_fen_exact(client):
    v=create(client,'vehicles',vehicle_body(purchase_cost='0.29',list_price='0.30'))
    assert v['purchase_cost_cents']==29 and v['list_price_cents']==30 and v['purchase_cost']=='0.29'


def test_unique_vin(client):
    create(client,'vehicles',vehicle_body())
    assert client.post('/api/records/vehicles',json=vehicle_body(doc_no='ANOTHER')).status_code==409


def test_no_duplicate_live_sale(client):
    v=car(client)
    first=approve(client,'sales',sale_body(v['id']))
    other=create(client,'sales',sale_body(v['id'],doc_no='TEST-S-002'))
    other=action(client,'sales',other,'submit')
    r=client.post(f'/api/records/sales/{other["id"]}/actions/approve',json={'version':other['version'],'reason':'并发第二次尝试'})
    assert r.status_code==409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Sale).where(Sale.active_vehicle_id==v['id']))==1


def test_database_allocation_check(client):
    v=car(client)
    with SessionLocal() as db:
        admin=db.scalar(select(User).where(User.role=='admin'))
        db.add(Sale(doc_no='INVALID',business_date=today(),vehicle_id=v['id'],active_vehicle_id=None,
            customer_name='x',salesperson='x',sale_stage='ordered',contract_amount_cents=100,
            approval_state='approved',created_by=admin.id))
        with pytest.raises(IntegrityError):db.commit()


def test_stock_reservation_delivery_and_release(client):
    v=car(client)
    s=approve(client,'sales',sale_body(v['id'],sale_stage='ordered',delivery_date=None))
    assert client.get(f'/api/records/vehicles/{v["id"]}').json()['stock_state']=='reserved'
    s=action(client,'sales',s,'advance',effective_date=str(today()))
    assert client.get(f'/api/records/vehicles/{v["id"]}').json()['stock_state']=='sold'
    s=action(client,'sales',s,'void')
    assert client.get(f'/api/records/vehicles/{v["id"]}').json()['stock_state']=='available'


def test_stale_edit_does_not_overwrite(client):
    v=create(client,'vehicles',vehicle_body())
    r=client.put(f'/api/records/vehicles/{v["id"]}',json={'version':v['version'],'data':vehicle_body(model='第一个修改')})
    assert r.status_code==200
    r=client.put(f'/api/records/vehicles/{v["id"]}',json={'version':v['version'],'data':vehicle_body(model='覆盖尝试')})
    assert r.status_code==409
    assert client.get(f'/api/records/vehicles/{v["id"]}').json()['model']=='第一个修改'


def test_unapproved_vehicle_not_sellable(client):
    v=create(client,'vehicles',vehicle_body())
    assert client.post('/api/records/sales',json=sale_body(v['id'])).status_code==422


def test_future_business_date_rejected(client):
    assert client.post('/api/records/vehicles',json=vehicle_body(business_date=str(today()+timedelta(days=1)))).status_code==422


def test_delivery_date_semantics(client):
    v=car(client)
    assert client.post('/api/records/sales',json=sale_body(v['id'],delivery_date=None)).status_code==422
    assert client.post('/api/records/sales',json=sale_body(v['id'],sale_stage='ordered')).status_code==422


@pytest.mark.parametrize('changes',[
    {'category':'sale_collection','direction':'out','related_type':'none'},
    {'category':'transfer','direction':'in','counter_account':'B'},
    {'category':'transfer','direction':'out','counter_account':''},
    {'category':'transfer','direction':'out','counter_account':'账户机密'},
    {'category':'refund','direction':'in'},
    {'category':'operating_expense','amount':'-1.00'},
    {'category':'loan','direction':'in','related_type':'sales','related_id':1},
])
def test_cash_category_validation(client,changes):
    assert client.post('/api/records/cash',json=cash_body(**changes)).status_code==422


def test_transfer_excluded_from_store_total(client):
    approve(client,'cash',cash_body(category='transfer',counter_account='另外账户',amount='50000.00'))
    m=client.get('/api/dashboard?days=1').json()['totals']
    assert m['cash_in_cents']==0 and m['cash_out_cents']==0 and m['net_cash_cents']==0
    assert m['internal_transfer_cents']==5000000


def test_loan_separate_from_operating_cash(client):
    approve(client,'cash',cash_body(category='loan',direction='in',amount='50000.00'))
    m=client.get('/api/dashboard?days=1').json()['totals']
    assert m['cash_in_cents']==5000000 and m['operating_net_cash_cents']==0


def test_premium_not_commission_or_sales(client):
    p=approve(client,'policies',policy_body())
    approve(client,'cash',cash_body(direction='in',category='premium_collection',related_type='policies',related_id=p['id'],amount='10000.00'))
    m=client.get('/api/dashboard?days=1').json()['totals']
    assert m['cash_in_cents']==1000000 and m['expected_commission_cents']==100000
    assert m['delivery_amount_cents']==0 and m['gross_difference_cents']==0


def test_refund_reduces_net_collections(client):
    s=sale(client)
    approve(client,'cash',cash_body(direction='in',category='sale_collection',related_type='sales',related_id=s['id'],amount='110000.00'))
    approve(client,'cash',cash_body(doc_no='REFUND',voucher_no='REFUND-V',direction='out',category='refund',related_type='sales',related_id=s['id'],amount='2000.00'))
    m=client.get('/api/dashboard?days=1').json()['totals']
    assert m['sales_receivable_cents']==200000 and m['cash_out_cents']==200000


def test_drafts_not_counted(client):
    create(client,'cash',cash_body(amount='1234.56'))
    assert client.get('/api/dashboard?days=1').json()['totals']['cash_out_cents']==0


def test_linked_cash_blocks_void_business(client):
    s=sale(client)
    approve(client,'cash',cash_body(direction='in',category='sale_collection',related_type='sales',related_id=s['id'],amount='1.00'))
    r=client.post(f'/api/records/sales/{s["id"]}/actions/void',json={'version':s['version'],'reason':'不能孤立作废业务'})
    assert r.status_code==409


def test_missing_relation_rejected(client):
    assert client.post('/api/records/cash',json=cash_body(direction='in',category='sale_collection',related_type='sales',related_id=999)).status_code==422


def test_void_cash_not_deleted_and_logged(client):
    row=approve(client,'cash',cash_body())
    row=action(client,'cash',row,'void')
    assert row['approval_state']=='void' and row['amount_cents']==10000
    assert client.get('/api/dashboard?days=1').json()['totals']['cash_out_cents']==0
    logs=client.get('/api/audit').json()['items']
    assert any(x['action']=='void' and x['before_data']['approval_state']=='approved' for x in logs)


def test_rules_duplicate_and_privacy_allowlist(client):
    s=sale(client,contract_amount='80000.00')
    approve(client,'cash',cash_body(doc_no='SECRET-DOC-1',amount='60000.00',payment_method='cash'))
    approve(client,'cash',cash_body(doc_no='SECRET-DOC-2',amount='60000.00',payment_method='cash'))
    with SessionLocal() as db: snap=build_snapshot(db,today())
    codes={f['rule_code'] for f in snap['rule_findings']}
    assert {'DUPLICATE_VOUCHER','SIMILAR_PAYMENT','LARGE_CASH','SALE_LOW_MARGIN'}<=codes
    payload=json.dumps(external_payload(snap),ensure_ascii=False)
    for secret in ['客户机密','13800000000','销售机密','绝不应外发','账户机密','交易对方机密','凭证机密','SECRET-DOC','LDD00000000000001']:
        assert secret not in payload


def test_ai_cap_does_not_truncate_totals(client,monkeypatch):
    for i in range(5):approve(client,'cash',cash_body(doc_no=f'R-{i}',voucher_no=f'V-{i}',amount='100.00'))
    monkeypatch.setattr(analytics,'settings',replace(analytics.settings,ai_max_records=2))
    with SessionLocal() as db:snap=build_snapshot(db,today())
    assert len(snap['records'])==2 and snap['ai_omitted_record_count']==3
    assert snap['metrics']['cash_out_cents']==50000


def test_report_idempotency_and_stale_snapshot(client):
    v=create(client,'vehicles',vehicle_body())
    body={'business_date':str(today())}
    r1=client.post('/api/reports/generate',json=body).json()['id']
    r2=client.post('/api/reports/generate',json=body).json()['id'];assert r1==r2
    r=client.put(f'/api/records/vehicles/{v["id"]}',json={'version':v['version'],'data':vehicle_body(model='改变')});assert r.status_code==200
    r3=client.post('/api/reports/generate',json=body).json()['id'];assert r3!=r1
    old=client.get('/api/reports/'+str(r1)).json();assert old['stale'] is True


def test_export_does_not_stale_report(client):
    car(client)
    with SessionLocal() as db:before=source_revision(db)
    assert client.get('/api/export/vehicles').status_code==200
    with SessionLocal() as db:assert source_revision(db)==before


def test_provisional_final_separate_snapshots(client,monkeypatch):
    car(client)
    day=today();first=generate_report(day)
    monkeypatch.setattr(analytics,'today',lambda:day+timedelta(days=1))
    second=generate_report(day)
    assert first!=second
    with SessionLocal() as db:
        assert db.get(DailyReport,first).snapshot['provisional'] is True
        assert db.get(DailyReport,second).snapshot['provisional'] is False


def test_no_ai_key_never_sends(client,monkeypatch):
    monkeypatch.setattr(reports,'settings',replace(reports.settings,allow_ai=True,deepseek_key=''))
    with patch('app.reports.httpx.Client') as http:
        status,result,error=ask_deepseek({})
        assert status=='unconfigured' and result is None
        http.assert_not_called()


def test_disabled_ai_never_sends(client):
    with patch('app.reports.httpx.Client') as http:
        status,_,_=ask_deepseek({});assert status=='disabled';http.assert_not_called()


def mock_ai_response(monkeypatch,content,finish='stop',status=200):
    monkeypatch.setattr(reports,'settings',replace(reports.settings,allow_ai=True,deepseek_key='secret-key-test'))
    body={'choices':[{'finish_reason':finish,'message':{'content':content}}]}
    return httpx.Response(status,json=body,request=httpx.Request('POST','https://api.deepseek.com/chat/completions'))


def test_valid_ai_json_and_reference(client,monkeypatch):
    car(client)
    with SessionLocal() as db:snap=build_snapshot(db,today())
    result={'summary':'仅根据汇总生成的摘要','highlights':['库存情况需关注'],'reviews':[{'ref':'V-1','reason':'可能需要核对库龄','action':'核对实车入库单'}],'limitations':'模型输出需人工核实'}
    response=mock_ai_response(monkeypatch,json.dumps(result,ensure_ascii=False))
    with patch('app.reports.httpx.Client') as http:
        http.return_value.__enter__.return_value.post.return_value=response
        status,data,_=ask_deepseek(snap)
    assert status=='success' and data['summary']==result['summary']


@pytest.mark.parametrize('content,finish',[
    ('','stop'),('not json','stop'),('{}','stop'),('{"summary":"x"}','length'),
    (json.dumps({'summary':'x','highlights':[],'reviews':[{'ref':'S-9999','reason':'x','action':'y'}],'limitations':'z'}),'stop'),
])
def test_invalid_ai_output_not_adopted(client,monkeypatch,content,finish):
    with SessionLocal() as db:snap=build_snapshot(db,today())
    response=mock_ai_response(monkeypatch,content,finish)
    with patch('app.reports.httpx.Client') as http:
        http.return_value.__enter__.return_value.post.return_value=response
        status,result,error=ask_deepseek(snap)
    assert status=='failed' and result is None and 'secret-key-test' not in error


def test_provider_error_does_not_leak_key(client,monkeypatch):
    with SessionLocal() as db:snap=build_snapshot(db,today())
    response=mock_ai_response(monkeypatch,'secret-key-test',status=401)
    with patch('app.reports.httpx.Client') as http:
        http.return_value.__enter__.return_value.post.return_value=response
        status,result,error=ask_deepseek(snap)
    assert status=='failed' and 'HTTP 401' in error and 'secret-key-test' not in error


def test_report_fallback_saved_before_network(client,monkeypatch):
    car(client)
    def network(snapshot):
        with SessionLocal() as db:
            report=db.scalar(select(DailyReport));assert report and report.snapshot and report.ai_status=='pending'
        return 'failed',None,'模拟超时'
    monkeypatch.setattr(reports,'ask_deepseek',network)
    report_id=generate_report(today(),use_ai=True)
    with SessionLocal() as db:
        r=db.get(DailyReport,report_id);assert r.ai_status=='failed' and r.deterministic_summary


def test_review_log_and_version(client):
    sale(client,contract_amount='80000.00')
    generate_report(today())
    f=client.get('/api/findings').json()['items'][0]
    body={'version':f['version'],'status':'dismissed','note':'已核对，属于已批准促销'}
    r=client.post(f'/api/findings/{f["id"]}/review',json=body);assert r.status_code==200
    assert client.post(f'/api/findings/{f["id"]}/review',json=body).status_code==409
    assert any(x['action']=='review' for x in client.get('/api/audit').json()['items'])


def test_csv_formula_safety(client):
    create(client,'vehicles',vehicle_body(note='=HYPERLINK("https://bad.invalid")'))
    r=client.get('/api/export/vehicles');assert r.status_code==200
    rows=list(csv.DictReader(io.StringIO(r.content.decode('utf-8-sig'))))
    assert rows[0]['note'].startswith("'=HYPERLINK")


def test_password_change_revokes_other_sessions(client):
    with TestClient(app) as other:
        login(other)
        r=client.post('/api/auth/password',json={'current_password':PASSWORD,'new_password':'NewTestingPassword!2026'})
        assert r.status_code==200
        assert other.get('/api/auth/me').status_code==401
    login(client,password='NewTestingPassword!2026')


def test_new_user_forced_password_change(client):
    r=client.post('/api/users',json={'username':'sales-new','display_name':'新员工','role':'sales','store_ids':[1],'password':'TemporaryPassword!2026'})
    assert r.status_code==201
    login(client,'sales-new','TemporaryPassword!2026')
    assert client.get('/api/records/sales').status_code==403
    assert client.post('/api/auth/password',json={'current_password':'TemporaryPassword!2026','new_password':'PersonalPassword!2026'}).status_code==200
    login(client,'sales-new','PersonalPassword!2026');assert client.get('/api/records/sales').status_code==200


def test_role_change_revokes_sessions(client):
    with TestClient(app) as other:
        user=login(other,'sales')
        current=next(u for u in client.get('/api/users').json()['items'] if u['id']==user['id'])
        r=client.put(f'/api/users/{user["id"]}',json={'request_id':'role-change-1','access_version':current['access_version'],'role':'auditor','display_name':'转岗人员','active':True});assert r.status_code==200
        assert other.get('/api/auth/me').status_code==401


def test_admin_cannot_disable_self(client):
    u=client.get('/api/auth/me').json()
    current=next(r for r in client.get('/api/users').json()['items'] if r['id']==u['id'])
    assert client.put(f'/api/users/{u["id"]}',json={'request_id':'self-disable-1','access_version':current['access_version'],'role':'admin','display_name':'admin','active':False}).status_code==409


def test_real_migration_and_database_transfer(client,tmp_path):
    from scripts.migrate_database import transfer
    target='sqlite:///'+str(tmp_path/'target.sqlite')
    car(client)
    source=str(__import__('app.config',fromlist=['settings']).settings.database_url)
    counts=transfer(source,target)
    assert counts['vehicles']==1 and counts['users']==7
    e=make_engine(target)
    with e.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(LoginSession))==0
        assert conn.scalar(select(Vehicle.purchase_cost_cents))==10000000
    with pytest.raises(ValueError):transfer(source,target)
    e.dispose()


def test_scheduler_previous_day_and_catchup(client,monkeypatch):
    from app import scheduler
    car(client,business_date=str(today()-timedelta(days=10)))
    class FixedDatetime(datetime):
        @classmethod
        def now(cls,tz=None): return datetime.combine(today(),time(0,20),tzinfo=tz)
    monkeypatch.setattr(scheduler,'datetime',FixedDatetime)
    scheduler.tick()
    with SessionLocal() as db:
        rows=list(db.scalars(select(DailyReport)))
        assert len(rows)==scheduler.settings.catchup_days
        assert max(r.business_date for r in rows)==today()-timedelta(days=1)
        assert not any(r.snapshot['provisional'] for r in rows)
    scheduler.tick()
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(DailyReport))==scheduler.settings.catchup_days
