"""Opt-in real PostgreSQL acceptance; creates only disposable local databases.

Run: python tests/postgres_acceptance.py --pg-bin <trusted PostgreSQL bin>
No existing server, database URL, or company source is accepted. Binary acquisition
is deliberately outside this script. It never installs a Windows service.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
EXCLUDED = {'login_sessions', 'login_attempts', 'job_leases'}


def run_binary(binary, args, work, env=None, timeout=60):
    # A detached postgres child may inherit handles on Windows. File handles,
    # unlike PIPE, cannot keep communicate() waiting after pg_ctl has exited.
    output = work / (binary.stem + '-command.log')
    with output.open('wb') as log:
        result = subprocess.run([str(binary), *map(str, args)], cwd=work, env=env,
            stdout=log, stderr=subprocess.STDOUT, creationflags=HIDDEN, timeout=timeout)
    if result.returncode:
        raise RuntimeError(binary.stem + ' failed; details retained in temporary log')
    return output.read_bytes().decode('utf-8', 'replace').strip()


@contextmanager
def temporary_postgres(binaries, work):
    import psycopg
    names = ['initdb', 'pg_ctl', 'pg_dump', 'pg_restore', 'postgres']
    executables = {n: binaries / (n + ('.exe' if os.name == 'nt' else '')) for n in names}
    if any(not p.is_file() for p in executables.values()):
        raise ValueError('The supplied directory is missing PostgreSQL server/client binaries')
    with socket.socket() as candidate:
        candidate.bind(('127.0.0.1', 0))
        port = candidate.getsockname()[1]
    password, user = secrets.token_urlsafe(40), 'hk_' + uuid.uuid4().hex[:12]
    password_file = work / 'initdb-password.tmp'
    password_file.write_text(password, encoding='utf-8')
    password_file.chmod(0o600)
    cluster = work / 'cluster'
    started = False
    # Do not inherit PG service/address settings that could redirect client tools.
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('PG')}
    env.update(PGHOST='127.0.0.1', PGPORT=str(port), PGUSER=user, PGPASSWORD=password)
    try:
        version = run_binary(executables['postgres'], ['--version'], work)
        run_binary(executables['initdb'], ['-D', cluster, '-U', user, '--encoding=UTF8',
            '--locale=C', '--auth=scram-sha-256', '--pwfile', password_file], work)
        password_file.unlink()
        with (cluster / 'postgresql.conf').open('a', encoding='utf-8') as config:
            config.write(f"\nlisten_addresses='127.0.0.1'\nport={port}\nmax_connections=20\n")
        started = True
        run_binary(executables['pg_ctl'], ['-D', cluster, '-l', work / 'postgres.log', '-w', 'start'], work, env)
        with psycopg.connect(host='127.0.0.1', port=port, user=user, password=password,
                             dbname='postgres', autocommit=True) as db:
            for name in ('hk_transfer', 'hk_restored'):
                db.execute('CREATE DATABASE ' + name)
        from sqlalchemy.engine import URL
        urls = {name: URL.create('postgresql+psycopg', username=user, password=password,
            host='127.0.0.1', port=port, database=name).render_as_string(hide_password=False)
            for name in ('hk_transfer', 'hk_restored')}
        yield executables, env, urls, version
    finally:
        if password_file.exists():
            password_file.unlink()
        if started:
            run_binary(executables['pg_ctl'], ['-D', cluster, '-m', 'fast', '-w', 'stop'], work, env)


def synthetic_source(object_root=None):
    # Import this fixture first: it force-selects a new external temp SQLite file
    # before any app settings/session import. No user .env database is opened.
    from tests import conftest as cf
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from tests import test_group_membership as group
    from tests import test_master_data as masters
    from tests import test_procurement as purchase
    from tests import test_transfers as transfer
    from app.models import User, UserStore
    from app.flow_models import Item
    from app.db import SessionLocal, engine
    fixture = cf.isolated_database.__wrapped__()
    next(fixture)
    # Stamps/upgrades through the same frozen revisions after fixture schema setup
    # are not valid; source uses fixture schema, PG target runs actual Alembic head.
    with TestClient(cf.app) as client:
        cf.login(client)
        checked = masters.preflight(client)
        assert checked['valid']
        trial = masters.review(client, checked['batch'])['batch']
        masters.review(client, trial, confirm=True)
        a, b = group.seed(), group.seed(2)
        with SessionLocal() as db:
            for user in db.scalars(select(User)):
                if not db.scalar(select(UserStore.user_id).where(UserStore.user_id == user.id, UserStore.store_id == 2)):
                    db.add(UserStore(user_id=user.id, store_id=2, role=None if user.role == 'admin' else user.role))
            db.commit()
        member = group.issue(client, a)
        topup = group.cmd(client, member, 'topup', group.topup_values(a, 20000))
        group.switch(client, 2)
        group.link(client, b, member['identity_id'])
        reserved = group.cmd(client, member, 'reserve', group.reserve_values(b, 5000))
        group.cmd(client, member, 'capture', group.reservation_values(b, reserved))
        group.cmd(client, member, 'reserve', group.reserve_values(b, 1000))
        group.switch(client, 1)
        requested = group.cmd(client, member, 'refund_request', group.refund_request_values(a, topup, 1000))
        group.cmd(client, member, 'refund_approve', group.refund_review_values(a, requested))
        order, items, _ = purchase.setup(client)
        order = purchase.command(client, order, 'approve')
        order = purchase.receive(client, order)
        purchase.pay(client, order, purchase.bank(client), 100)
        with SessionLocal() as db:
            destination = Item(store_id=2, sku='PG-RECEIVE', name=items[0]['name'], unit='件')
            db.add(destination)
            db.commit()
            destination_id = destination.id
        response = client.post('/api/transfers', json={'request_id': uuid.uuid4().hex,
            'destination_store_id': 2, 'reason': '合成PG在途验收验证',
            'due_date': group.today().isoformat(),
            'lines': [{'item_id': items[0]['id'], 'quantity_milli': 1000}]})
        assert response.status_code == 201, response.text
        row = response.json()
        transfer.command(client, row, 'approve')
        transfer.switch(client, 2)
        transfer.command(client, row, 'approve')
        transfer.switch(client, 1)
        transfer.command(client, row, 'dispatch', {'evidence_id': transfer.upload(client, row), 'reason': '合成实物发出'})
        transfer.switch(client, 2)
        current = transfer.get(client, row)
        transfer.command(client, row, 'receive', {'evidence_id': transfer.upload(client, row), 'reason': '保留部分在途',
            'lines': [{'line_id': current['lines'][0]['id'], 'item_id': destination_id,
                       'accept_milli': 400, 'reject_milli': 200}]})
        extended_synthetic_source(client,a,b,member)
        latest_finance_source(client)
        from tests.postgres_wave6 import seed as wave6_source
        wave6_source(client)
        from tests.postgres_wave7 import seed as wave7_source
        wave7_source(client)
        from tests.postgres_wave8 import seed as wave8_source
        wave8_source(client)
        from tests.postgres_wave9 import seed as wave9_source
        from unittest.mock import patch
        from app import sales_quote_service
        with patch.object(sales_quote_service,'CURRENT_ORDER_VERSION',3):wave9_source(client)
        from tests.postgres_wave10 import seed as wave10_source
        wave10_source(client)
        from tests.postgres_wave11 import seed as wave11_source
        wave11_source(client)
        from tests.postgres_entity_opening import seed as entity_opening_source
        entity_opening_source(client)
        from tests.postgres_wave12 import seed as wave12_source
        wave12_source(client)
        if object_root:
            from dataclasses import replace
            from unittest.mock import patch
            from app import private_files
            from tests.test_workflow import create as flow_create,evidence
            with patch.object(private_files,'settings',replace(private_files.settings,file_storage_mode='private_local',private_file_root=str(object_root))):
                cf.login(client);client.headers['X-Store-ID']='1'
                private_case=flow_create(client,'order',{'customer_name':'合成私有附件恢复客户','model':'合成验证车型','amount':'10.00','delivery_due':group.today().isoformat()})
                evidence(client,private_case)
        # Freeze the current definition after all new domain facts and private
        # object references exist, while retaining the earlier v1 snapshot.
        latest_operations_source(client,expect_private=bool(object_root))
        from tests.postgres_user_access import seed as user_access_source
        user_access_source(client)
    try:
        next(fixture)
    except StopIteration:
        pass
    engine.dispose()
    import sqlite3
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(cf.TEST_DIR / 'test.sqlite') as source:
        validate_sqlite(source,object_root=object_root)
    return 'sqlite:///' + (cf.TEST_DIR / 'test.sqlite').as_posix()


def extended_synthetic_source(client,a,b,member):
    """Latest business graphs are produced through guarded APIs, using synthetic facts."""
    from tests import test_group_membership as group
    from tests import test_group_benefits as benefits
    from tests import test_repair_orders as repair
    from tests import test_customer_service as care
    from tests import test_vehicle_transfers as vehicles
    from app.db import SessionLocal,today
    from app.models import Vehicle
    from app.master_models import Warehouse,StorageLocation
    from app.tenancy import set_scope
    # Keep both service reservations and approved partial-refund reservations,
    # alongside a completed original refund; principal records stay separate.
    group.switch(client,1)

    coupon=benefits.rule(client)
    wallet=benefits.issuance(client,member,a,coupon,5)
    group.switch(client,2)
    benefits.capture(client,member,b,wallet,benefits.reserve(client,member,b,wallet))
    benefits.reserve(client,member,b,wallet)
    group.switch(client,1)
    refund=benefits.refund_request(client,member,a,wallet)
    approved=benefits.command(client,member,'refund_approve',benefits.refund_values(client,a,wallet,refund))
    benefits.command(client,member,'refund',benefits.refund_values(client,a,wallet,approved)|{
        'account_id':a['account_id'],'reference':'PG-BENEFIT-REFUND','evidence_id':a['evidence_id']})
    pending=benefits.refund_request(client,member,a,wallet)
    benefits.command(client,member,'refund_approve',benefits.refund_values(client,a,wallet,pending))
    points=benefits.issuance(client,member,a,benefits.rule(client,'points'),500,'grant')
    benefits.command(client,member,'adjust',benefits.wvalues(client,a,points)|benefits.source(a)|{'units':50})
    gift=benefits.rule(client,sale_cents_per_unit=0,settlement_cents_per_unit=0,refund_policy='none')
    benefits.command(client,member,'exchange',benefits.wvalues(client,a,points)|benefits.source(a)|{
        'units':200,'target_rule_id':gift['id']})

    # Actual authorized work and part lines, partial multi-party late receivable.
    row,item,work,customer=repair.setup(client)
    row=repair.ready(client,row,item,work)
    insurer=repair.typed(client,'insurers',{'code':'PG-INS','name':'合成PG保险承担方'})
    manufacturer=repair.master(client,'references',{'category':'厂家','name':'合成PG厂家承担方','detail':'合成厂家结算','active':True})
    row=repair.allocate(client,row,[{'payer_type':'customer','amount_cents':6000},
        {'payer_type':'insurer','payer_id':insurer['id'],'amount_cents':3000},
        {'payer_type':'manufacturer','payer_id':manufacturer['id'],'amount_cents':999},
        {'payer_type':'internal','payer_name':'合成集团内部承担','amount_cents':998}])
    source={'case_id':row['id'],'customer_id':customer['id'],'account_id':repair.bank(client),
        'evidence_id':repair.evidence(client,row),'store_id':1}
    other_member=group.issue(client,source)
    package=benefits.rule(client,'package',allowed_store_ids=[1],service_code=work['code'],
        credit_cents_per_unit=3000,sale_cents_per_unit=2400,settlement_cents_per_unit=2400)
    pw=benefits.issuance(client,other_member,source,package,2)
    benefits.capture(client,other_member,source,pw,benefits.reserve(client,other_member,source,pw))
    bonus=benefits.rule(client,'bonus',allowed_store_ids=[1])
    bw=benefits.issuance(client,other_member,source,bonus,1000,'grant')
    benefits.capture(client,other_member,source,bw,benefits.reserve(client,other_member,source,bw,1000))
    cw=benefits.issuance(client,other_member,source,benefits.rule(client,allowed_store_ids=[1],
        credit_cents_per_unit=2000,sale_cents_per_unit=1600,settlement_cents_per_unit=1600),2)
    benefits.capture(client,other_member,source,cw,benefits.reserve(client,other_member,source,cw))
    row=repair.cmd(client,row,'release',{'evidence_id':repair.evidence(client,row)})
    assert row['state']=='credit_open' and row['receivable_cents']==3999
    insurer_allocation=next(x for x in row['allocations'] if x['payer_type']=='insurer')
    row=repair.receive(client,row,insurer_allocation,1000,source['account_id'])
    assert row['receivable_cents']==2999

    # Same identity and VIN are insufficient to see another store's case; only
    # a specific approved, revocable summary grant permits this shared summary.
    va=care.vehicle(client,a['customer_id'])
    va=care.observe(client,va,km=1200)['vehicle']
    case=care.care(client,a['customer_id'],va['id'])
    case=care.action(client,case,'start')['case']
    case=care.action(client,case,'close',{'result':'resolved','note':'合成客户确认检查说明完成'})['case']
    care.post(client,f'/vehicles/{va["id"]}/history-links',{'case_id':case['id'],'summary':'合成PG服务摘要授权测试',
        'source_reference':'客户明确确认服务摘要','confirmed':True},status=201)
    group.switch(client,2)
    vb=care.vehicle(client,b['customer_id'],customer_identity_id=va['customer_identity_id'])
    assert client.get(care.API+f'/vehicles/{vb["id"]}/history').json()['items']==[]
    group.switch(client,1)
    care.post(client,'/history/grants',{'from_vehicle_id':va['id'],'to_store_id':2,'to_vehicle_id':vb['id'],
        'valid_until':today().isoformat(),'source_reference':'客户明确授权仅共享服务摘要','confirmed':True},status=201)
    group.switch(client,2)
    assert len(client.get(care.API+f'/vehicles/{vb["id"]}/history').json()['items'])==1
    assert client.get('/api/flow/cases/'+str(case['id'])).status_code==404

    # One vehicle has arrived at B, another is still in physical transit. Legacy
    # synthetic opening vehicles are immutable source generations thereafter.
    locations={}
    for sid in [1,2]:
        with SessionLocal() as db:
            set_scope(db,[sid],sid)
            warehouse=Warehouse(store_id=sid,code='PG-CARS',name='合成整车仓',warehouse_type='vehicles')
            db.add(warehouse);db.flush()
            location=StorageLocation(store_id=sid,code='PG-PARK',name='合成停车区',warehouse_id=warehouse.id)
            db.add(location);db.commit();locations[sid]=location.id
    for index,vin in enumerate(['LHGCM82633A123456','LHGCM82633A123457']):
        group.switch(client,1)
        with SessionLocal() as db:
            set_scope(db,[1],1)
            car=Vehicle(vin=vin,brand='合成品牌',model='合成车型',color='白',supplier='合成供应方',
                purchase_cost_cents=10000001+index,list_price_cents=12000000,store_id=1,
                doc_no='PG-CAR-'+str(index),business_date=today(),approval_state='approved',created_by=care.user_id())
            db.add(car);db.commit();car_id=car.id
        transfer=vehicles.create(client,car_id)
        vehicles.command(client,transfer,'approve');group.switch(client,2);vehicles.command(client,transfer,'approve')
        group.switch(client,1)
        vehicles.command(client,transfer,'dispatch',{'evidence_id':vehicles.upload(client,transfer),'vin':vin,'reason':'合成实际发车确认'})
        if index==0:
            group.switch(client,2)
            vehicles.command(client,transfer,'accept',{'evidence_id':vehicles.upload(client,transfer),'vin':vin,
                'reason':'合成实际验收进店','location_id':locations[2]})
    group.switch(client,1)


def latest_finance_source(client):
    """Vehicle procurement, retail original returns and real statement/cash graphs."""
    from tests import test_vehicle_procurement as purchase
    from tests import test_retail as retail
    from tests import test_reconciliation as recon
    from tests import test_group_membership as group
    from tests.conftest import login
    login(client,'admin');group.switch(client,1)
    row,loc=purchase.approved(client,quantity=1)
    row=purchase.funds(client,row,10000001);purchase.pay(client,row,purchase.bank(client),10000001)
    row=purchase.ship(client,row,vin='LHGCM82633A223456');purchase.receive(client,row,loc)
    items,customer,work,_=retail.setup(client)
    sale=retail.authorize(client,retail.approve(client,retail.create(client,items,customer)))
    account=retail.bank(client);sale=retail.pay(client,sale,sale['amount_cents'],account)
    sale=retail.dispatch(client,sale)
    sale,returned=retail.request_return(client,sale,sale['dispatches'][0],500)
    retail.ret_cmd(client,sale,returned,'return_approve');sale=retail.ret_cmd(client,sale,returned,'return_receive')
    retail.refund(client,sale,sale['payments'][0],account,sale['totals']['refund_due_cents'])
    group.switch(client,2);login(client,'finance')
    origin=next(x for x in client.get('/api/reconciliation/origins').json()['items'] if x['origin_kind']=='material')
    assert origin['available_cents']>=30
    settled=recon.clear(client,origin,20)
    recon.cmd(client,settled,'pay',recon.payvalues(client,settled),kind='clearing')
    group.switch(client,1);recon.cmd(client,settled,'receive',recon.payvalues(client,settled),kind='clearing')
    group.switch(client,2);pending=recon.clear(client,origin,10)
    recon.cmd(client,pending,'pay',recon.payvalues(client,pending),kind='clearing')
    statement=recon.batch(client)
    fid=recon.proof(client,statement)
    line=next(x for x in statement['manifest'] if x['source']=='cash_entries')
    statement=recon.cmd(client,statement,'issue',{'line_key':line['key'],'difference_cents':0,'evidence_id':fid,'reason':'合成银行实际回单待复核'})
    issue=statement['issues'][0]
    statement=recon.cmd(client,statement,'resolve',{'issue_id':issue['id'],'issue_version':issue['version'],'evidence_id':fid,'reason':'银行回单与原现金一致'})
    statement=recon.cmd(client,statement,'submit');login(client,'manager')
    statement=recon.cmd(client,statement,'seal',{'evidence_id':fid,'reason':'独立店长确认本期冻结来源'})
    reopened=recon.cmd(client,statement,'reopen',{'reason':'保留封存版本并演练新增后继对账'})
    assert reopened['revision']==2 and recon.get(client,statement)['status']=='sealed'
    group.switch(client,1);login(client,'admin')


def latest_operations_source(client,expect_private=False):
    # The caller selects isolated synthetic settings before app imports.
    from app.reconciliation_service import CURRENT_DEFINITION_VERSION
    """Nonempty frozen membership, physical bins, v4 reception and invoice facts."""
    from tests import test_membership_lifecycle as member
    from tests import test_group_membership as group
    from tests import test_group_benefits as benefits
    from tests import test_retail as retail
    from tests import test_warehouse as warehouse
    from tests import test_service_intake as intake
    from tests import test_customer_service as care
    from tests import test_invoices as invoice
    from tests.conftest import login
    from tests.test_workflow import evidence,master
    login(client,'admin');group.switch(client,1)
    point_rule=benefits.rule(client,'points',allowed_store_ids=[1])
    level=member.rule(client,points_enabled=True,points_benefit_rule_id=point_rule['id'])
    items,customer,_,_=retail.setup(client)
    group.issue(client,{'customer_id':customer['id']})
    member.renew(client,customer,level);login(client,'admin')
    card=member.create(client,customer,'card_issue');member.cmd(client,card,'execute')
    original=member.info(client,customer)['cards'][0]
    loss=member.create(client,customer,'card_loss',{'card_id':original['id']});member.cmd(client,loss,'execute')
    replacement=member.create(client,customer,'card_replace',{'card_id':original['id']});member.cmd(client,replacement,'execute')
    fee_rule=member.rule(client,fee_cents=19900)
    account=retail.bank(client)
    fee=member.create(client,customer,'renew',{'rule_id':fee_rule['id']})
    login(client,'manager');member.cmd(client,fee,'approve');login(client,'finance')
    member.cmd(client,fee,'execute',{'evidence_id':member.proof(client,fee),'account_id':account,'reference':'PG-MEMBER-FEE','reason':'合成未来期间实际续费'})
    period=member.info(client,customer)['periods'][-1]
    refund=member.create(client,customer,'renew_refund',{'period_id':period['id']})
    login(client,'manager');member.cmd(client,refund,'approve');login(client,'finance')
    member.cmd(client,refund,'execute',{'evidence_id':member.proof(client,refund),'account_id':account,'reference':'PG-MEMBER-FEE-REFUND','reason':'合成未生效原费退还'})
    login(client,'admin')
    sale=retail.authorize(client,retail.approve(client,retail.create(client,items,customer)))
    sale=retail.pay(client,sale,101,account);sale=retail.pay(client,sale,899,account)
    sale=retail.dispatch(client,sale);sale=retail.cmd(client,sale,'accept',{'evidence_id':evidence(client,sale)})
    wallet=benefits.info(client,{'customer_id':customer['id']})['wallets'][0]
    assert wallet['balance_units']==10
    login(client,'finance');blue=invoice.actual(client,sale['id'],1000);login(client,'admin')
    coupon=benefits.rule(client,'coupon',allowed_store_ids=[1],sale_cents_per_unit=0,settlement_cents_per_unit=0,exchange_points_per_unit=1)
    exchange=member.create(client,customer,'points_adjust',{'action':'exchange','wallet_id':wallet['id'],'target_rule_id':coupon['id'],'units':10})
    login(client,'finance');member.cmd(client,exchange,'execute',{'evidence_id':member.proof(client,exchange),'wallet_version':wallet['version'],'reason':'合成客户明确兑换积分'})
    login(client,'admin');sale,returned=retail.request_return(client,sale,sale['dispatches'][0],500)
    retail.ret_cmd(client,sale,returned,'return_approve');sale=retail.ret_cmd(client,sale,returned,'return_receive')
    retail.refund(client,sale,sale['payments'][1],account,sale['totals']['refund_due_cents'])
    assert member.info(client,customer)['points_debt_units']==3
    login(client,'finance');red=invoice.actual(client,sale['id'],250,blue['id']);assert red['balance']['correction_cents']==0
    login(client,'admin');grant=member.create(client,customer,'benefit_issue',{'action':'grant','rule_id':point_rule['id'],'units':1})
    login(client,'manager');member.cmd(client,grant,'execute')
    assert member.info(client,customer)['points_debt_units']==2

    login(client,'admin')
    item,a,b=warehouse.setup(client)
    outgoing=warehouse.create(client,'consumable',item,3000,src=a);warehouse.approve(client,outgoing);outgoing=warehouse.execute(client,outgoing)
    returned=warehouse.create(client,'consumable_return',item,1000,dest=b,original=outgoing['stock_moves'][0]['id'])
    warehouse.approve(client,returned);warehouse.execute(client,returned)
    moving=warehouse.create(client,'local_move',item,2000,src=a,dest=b);warehouse.approve(client,moving)
    moving=warehouse.command(client,moving,'dispatch',{'evidence_id':evidence(client,moving)})
    warehouse.command(client,moving,'accept',{'quantity_milli':1000,'evidence_id':evidence(client,moving)})
    warehouse.conserved(client,item)

    customer=master(client,'customers',{'name':'PG接待会员客户','phone':'13900998855','contact_allowed':True,'note':''})
    group.issue(client,{'customer_id':customer['id']})
    car=care.vehicle(client,customer['id'],vin='LFV2A21K9J3234567')
    member.renew(client,customer,level);login(client,'admin')
    resource=intake.resource(client);appointment=intake.appointment(client,car,resource)
    appointment=intake.arrive(client,appointment);repair=intake.convert(client,appointment)
    repair,_=intake.work_quote(client,repair,1000)
    repair=intake.repair_cmd(client,repair,'start',{'result':'合成实际开始施工'})
    repair=intake.released(client,repair)
    assert sum(w['balance_units'] for w in benefits.info(client,{'customer_id':customer['id']})['wallets'])==10
    rework=intake.approve_rework(client,intake.request_rework(client,repair,car,resource))
    rework=intake.convert_rework(client,rework);rework,_=intake.work_quote(client,rework,600)
    rework=intake.repair_cmd(client,rework,'start',{'result':'合成原单责任修复'})
    intake.released(client,rework,internal=True)
    assert sum(w['balance_units'] for w in benefits.info(client,{'customer_id':customer['id']})['wallets'])==10
    # A separate customer's unspent source points can actually be recovered;
    # do not reuse the first customer's balance or conceal its outstanding debt.
    items,_,_,_=retail.setup(client)
    customer=master(client,'customers',{'name':'PG原批次积分追回客户','phone':'13900335577','contact_allowed':True,'note':''})
    group.issue(client,{'customer_id':customer['id']});member.renew(client,customer,level);login(client,'admin')
    sale=retail.authorize(client,retail.approve(client,retail.create(client,items,customer)))
    sale=retail.pay(client,sale,1000,account);sale=retail.dispatch(client,sale)
    sale=retail.cmd(client,sale,'accept',{'evidence_id':evidence(client,sale)})
    sale,returned=retail.request_return(client,sale,sale['dispatches'][0],500)
    retail.ret_cmd(client,sale,returned,'return_approve');retail.ret_cmd(client,sale,returned,'return_receive')
    assert sum(w['balance_units'] for w in benefits.info(client,{'customer_id':customer['id']})['wallets'])==7
    assert member.info(client,customer)['points_debt_units']==0
    # Exercise a synthetic pre-upgrade producer without rewriting a frozen row.
    # The same supported v1 function builds the initial manifest; current APIs
    # then seal it and create a v6 successor that includes all new domain facts.
    from unittest.mock import patch
    from tests import test_reconciliation as recon
    from app import reconciliation_service as recon_service
    original_snapshot=recon_service.snapshot
    def historical_snapshot(db,user,start,end,definition_version=1):
        return original_snapshot(db,user,start,end,definition_version)
    login(client,'finance')
    with patch.object(recon_service,'snapshot',historical_snapshot):statement=recon.batch(client)
    assert statement['definition_version']==1
    fid=recon.proof(client,statement);statement=recon.cmd(client,statement,'submit');login(client,'manager')
    statement=recon.cmd(client,statement,'seal',{'reason':'独立核对合成历史口径冻结来源','evidence_id':fid})
    successor=recon.cmd(client,statement,'reopen',{'reason':'按当前新口径新增后继，不修改旧定义'})
    assert successor['definition_version']==CURRENT_DEFINITION_VERSION and recon.get(client,statement)['definition_version']==1
    sources={x['source'] for x in successor['manifest']}
    assert {'membership_fees','membership_points_changes','membership_points_debt_payments'}<=sources
    assert {'recharge_bundle_purchases','recharge_bundle_components','recharge_bundle_refunds',
        'recharge_bundle_refund_components','recharge_bundle_refund_postings'}<=sources
    if expect_private:
        assert 'private_file_objects' in sources


def database_manifest(engine,object_root=None):
    from sqlalchemy import select, func, text
    from app.db import Base
    from app.flow_models import FileAsset
    from scripts.migrate_database import table_fingerprint
    with engine.connect() as db:
        result = {table.name: {'rows': db.scalar(select(func.count()).select_from(table)),
            'sha256': table_fingerprint(db, table)} for table in Base.metadata.sorted_tables if table.name not in EXCLUDED}
        from app.private_file_backup import validate_connection_files
        files=validate_connection_files(db,object_root)
        assert files['verified_files']
        return result, files['verified_files']


def concurrency_checks(engine):
    from sqlalchemy import select, text
    from sqlalchemy.orm import Session
    from sqlalchemy.orm.exc import StaleDataError
    from sqlalchemy.exc import OperationalError, IntegrityError
    from app.flow_models import Item
    from app.tenancy import set_scope
    # Two physical connections select the same Item version before either commits.
    with Session(engine) as first, Session(engine) as second:
        set_scope(first, [1], 1)
        set_scope(second, [1], 1)
        a = first.scalar(select(Item).where(Item.quantity_milli > 0).order_by(Item.id))
        b = second.scalar(select(Item).where(Item.id == a.id))
        original = a.quantity_milli
        a.quantity_milli -= 1
        first.commit()
        b.quantity_milli -= 2
        refused = False
        try:
            second.commit()
        except (StaleDataError, OperationalError) as error:
            if isinstance(error, OperationalError):
                assert getattr(error.orig, 'sqlstate', None) in {'40001', '40P01'}
            second.rollback()
            refused = True
        assert refused
        assert first.scalar(select(Item.quantity_milli).where(Item.id == a.id)) == original - 1
    # Actual PostgreSQL row locking (second connection hits bounded lock_timeout).
    with engine.connect() as first, engine.connect() as second:
        member_id = first.scalar(text('SELECT id FROM group_members ORDER BY id LIMIT 1 FOR UPDATE'))
        second.execute(text("SET LOCAL lock_timeout = '300ms'"))
        try:
            second.execute(text('SELECT id FROM group_members WHERE id=:id FOR UPDATE'), {'id': member_id})
            raise AssertionError('Second connection bypassed held member row lock')
        except OperationalError as error:
            assert getattr(error.orig, 'sqlstate', None) == '55P03'
            second.rollback()
        first.rollback()
    # A unique-key failure rolls back an earlier mutation in the same transaction.
    with engine.connect() as db:
        before = db.scalar(text('SELECT quantity_milli FROM flow_items ORDER BY id LIMIT 1'))
        db.rollback()
        try:
            with db.begin():
                db.execute(text('UPDATE flow_items SET quantity_milli=quantity_milli+77 WHERE id=(SELECT MIN(id) FROM flow_items)'))
                db.execute(text('INSERT INTO stores SELECT * FROM stores LIMIT 1'))
        except IntegrityError as error:
            assert getattr(error.orig, 'sqlstate', None) == '23505'
        else:
            raise AssertionError('Duplicate primary key was accepted')
        assert db.scalar(text('SELECT quantity_milli FROM flow_items ORDER BY id LIMIT 1')) == before
    return ['item_competing_version_refused', 'member_two_connection_row_lock', 'unique_failure_atomic_rollback']


def verify_sequences(engine):
    from sqlalchemy import select, func, text
    from app.db import Base
    checked = 0
    with engine.begin() as db:
        for table in Base.metadata.sorted_tables:
            if 'id' not in table.c or table.name in EXCLUDED:
                continue
            sequence = db.scalar(text('SELECT pg_get_serial_sequence(:table, :column)'),
                                 {'table': table.name, 'column': 'id'})
            if not sequence:
                continue
            maximum = db.scalar(select(func.max(table.c.id))) or 0
            value = db.scalar(text('SELECT nextval(CAST(:sequence AS regclass))'), {'sequence': sequence})
            assert value > maximum, 'Imported serial sequence would reuse an existing ID: ' + table.name
            checked += 1
    assert checked
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pg-bin', required=True, type=Path)
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix='huakangos-pg-acceptance-')).resolve()
    if work.is_relative_to(ROOT):
        raise ValueError('Acceptance temporary directory must be outside repository')
    report = {'status': 'running', 'temporary_directory': str(work)}
    print('Acceptance artifacts: ' + str(work), flush=True)
    try:
        with temporary_postgres(args.pg_bin.resolve(), work) as (exe, env, urls, version):
            report['server_version'] = version
            print(version + ': isolated server ready', flush=True)
            object_root=work/'source-objects'
            source = synthetic_source(object_root)
            from app.private_file_backup import create_bundle,restore_bundle
            from sqlalchemy.engine import make_url
            bundle=create_bundle(Path(make_url(source).database),object_root,work/'combined-backup')
            restored_objects=restore_bundle(bundle['bundle'],work/'combined-restored')
            target_object_root=Path(restored_objects['object_root'])
            report['private_object_restore']=restored_objects['verified_private_objects']
            from app.db import make_engine
            from scripts.migrate_database import transfer
            report['copied_rows'] = transfer(source, urls['hk_transfer'],object_root,target_object_root)
            print('Alembic head and synthetic SQLite transfer passed', flush=True)
            target = make_engine(urls['hk_transfer'])
            try:
                from sqlalchemy import text
                with target.connect() as db:
                    report['alembic_revision'] = db.scalar(text('SELECT version_num FROM alembic_version'))
                expected, report['verified_files'] = database_manifest(target,target_object_root)
                report['table_manifest'] = expected
            finally:
                target.dispose()
            dump = work / 'synthetic-backup.dump'
            run_binary(exe['pg_dump'], ['-Fc', '-d', 'hk_transfer', '-f', dump], work, env)
            run_binary(exe['pg_restore'], ['--exit-on-error', '-d', 'hk_restored', dump], work, env)
            restored = make_engine(urls['hk_restored'])
            try:
                actual, files = database_manifest(restored,target_object_root)
                assert actual == expected and files == report['verified_files']
                report['restored_tables'] = len(actual)
                report['verified_serial_sequences'] = verify_sequences(restored)
                report['concurrency_checks'] = concurrency_checks(restored)
                from tests.postgres_user_access import concurrency_checks as account_concurrency
                report['user_access_concurrency'] = account_concurrency(restored)
            finally:
                restored.dispose()
            report['status'] = 'passed'
        print('PostgreSQL acceptance passed; temporary server stopped', flush=True)
    except Exception as error:
        report.update(status='failed', failure_type=type(error).__name__)
        (work / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
        print('Acceptance failed (' + type(error).__name__ + '); see temporary failure.txt', flush=True)
    finally:
        (work / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
