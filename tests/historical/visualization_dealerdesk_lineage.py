"""历史遗留：DealerDesk 数据可视化线的测试，**不参与本目录测试集**。

为什么不能跑：它请求 `GET /api/visualization`，而 huakangos 线没有挂载该路由——`app/visualization.py`
里的 `visualization(db, day, days)` 在本线没有被任何 router 引用，前端 `web/` 也没有任何调用者
（本线的“数据可视化”是 `#analytics/overview` + `/api/flow/analytics`）。它此前让全量回归出现
26 项失败，因此按业主决定（2026-09-24：标注历史遗留并移出测试集）改名并移入 `tests/historical/`。

恢复条件：先决定“数据可视化”用哪一套（当前是 flow analytics），若确实要恢复这份逐日聚合接口，
需要重新挂载 router、接回前端页面、补岗位/门店范围校验，再把本文件改回 `test_` 名称。
""""""可视化数据层契约测试（服务端）。

浏览器模块按同一契约并行实现，因此这里断言的是精确载荷形状：
金额一律为整数分、数据集零填充不省略、排行降序封顶、GET 不产生任何写入。
"""
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from app.analytics import BASIS
from app.db import SessionLocal, today
from app.main import app
from app.models import MODULES, AuditLog, CashEntry, DailyReport, Finding, Policy, Repair, Sale, User, Vehicle
from tests.conftest import login

PAYLOAD_KEYS = {'end_date','start_date','days','currency','kpis','trends','breakdowns','rankings','notes'}
KPI_KEYS = ('delivery_amount','delivery_count','new_order_count','repair_completed_count','repair_amount',
            'gross_difference','policy_premium','expected_commission','net_cash','stock_count',
            'aging_stock_count','receivable')
TREND_IDS = ['money','volume','cashflow','stock']
BREAKDOWN_IDS = ['cash_category','stock_brand','repair_type','finding_severity']
RANKING_IDS = ['salesperson','brand_stock','insurer']
OTHER = {'key':'__other__','label':'其他'}


def payload(client,**params):
    response = client.get('/api/visualization',params=params)
    assert response.status_code == 200,response.text
    return response.json()


def dataset(body,section,dataset_id):
    return next(item for item in body[section] if item['id'] == dataset_id)


def scalars(node,path=()):
    if isinstance(node,dict):
        for key,value in node.items(): yield from scalars(value,path+(key,))
    elif isinstance(node,list):
        for index,value in enumerate(node): yield from scalars(value,path+(index,))
    else: yield path,node


def unit_of(body,path):
    if not path or not isinstance(path[0],str): return None
    if path[0] == 'kpis': return body['kpis'][path[1]]['unit']
    if path[0] == 'trends': return body['trends'][path[1]]['unit']
    if path[0] in {'breakdowns','rankings'}: return body[path[0]][path[1]]['unit']
    return None


def money_values(body):
    """递归取出所有金额标量并带路径，避免只检查 KPI 而漏掉 series / items。"""
    for path,value in scalars(body):
        if path[-1] == 'value' or (len(path) >= 2 and path[-2] == 'values'):
            if unit_of(body,path) == 'money': yield path,value


def check_dataset_items(body):
    for breakdown in body['breakdowns']:
        assert set(breakdown) == {'id','title','chart','unit','dimension','items'}
        assert breakdown['chart'] == 'pie' and breakdown['unit'] in {'money','count'}
        values = [item['value'] for item in breakdown['items']]
        assert values == sorted(values,reverse=True),breakdown['id']
        assert len(breakdown['items']) <= 9,breakdown['id']
        assert len([item for item in breakdown['items'] if item['key'] == OTHER['key']]) <= 1
        for item in breakdown['items']:
            assert set(item) == {'key','label','value','share'}
            assert isinstance(item['value'],int) and not isinstance(item['value'],bool)
            assert isinstance(item['share'],float) and 0.0 <= item['share'] <= 1.0
        shares = [item['share'] for item in breakdown['items']]
        assert (sum(shares) == pytest.approx(1.0)) if shares else shares == []
    for ranking in body['rankings']:
        assert set(ranking) == {'id','title','chart','unit','dimension','items'}
        assert ranking['chart'] == 'bar' and ranking['unit'] in {'money','count'}
        assert len(ranking['items']) <= 10,ranking['id']
        values = [item['value'] for item in ranking['items']]
        assert values == sorted(values,reverse=True),ranking['id']
        for item in ranking['items']:
            assert set(item) == {'key','label','value'}
            assert isinstance(item['value'],int) and not isinstance(item['value'],bool)
            assert item['key'] != OTHER['key'] and item['label']


def seed(db):
    """直接通过 ORM 写入已审核记录（造数方式与 tests/test_multistore.py 一致）。"""
    day = today()
    admin = db.scalar(select(User).where(User.role == 'admin'))

    def vehicle(suffix,brand,cost_cents,business_day):
        row = Vehicle(store_id=1,doc_no='VIZ-V-'+suffix,business_date=business_day,created_by=admin.id,
                      vin='LDDVIZ'+suffix+'0000000',brand=brand,model='可视化测试车',
                      purchase_cost_cents=cost_cents,list_price_cents=cost_cents*2,approval_state='approved')
        db.add(row); db.flush(); return row

    def delivered(car,salesperson,contract_cents,business_day):
        row = Sale(store_id=1,doc_no='VIZ-S-'+car.doc_no[-4:],business_date=business_day,created_by=admin.id,
                   vehicle_id=car.id,active_vehicle_id=car.id,customer_name='测试客户',salesperson=salesperson,
                   sale_stage='delivered',delivery_date=business_day+timedelta(days=1),
                   contract_amount_cents=contract_cents,purchase_cost_snapshot_cents=car.purchase_cost_cents,
                   approval_state='approved')
        db.add(row); db.flush(); return row

    first = vehicle('0001','测试豪华品牌',10_000_000,day-timedelta(days=10))
    second = vehicle('0002','测试经济品牌',20_000_000,day-timedelta(days=9))
    vehicle('0003','测试库存品牌',8_000_000,day-timedelta(days=8))       # 仍在库：库存构成只应出现它
    sale_one = delivered(first,'张三',11_000_000,day-timedelta(days=10))
    delivered(second,'李四',9_000_000,day-timedelta(days=9))
    db.add(CashEntry(store_id=1,doc_no='VIZ-C-0001',business_date=day-timedelta(days=8),created_by=admin.id,
                     direction='in',category='sale_collection',amount_cents=6_000_000,account='测试账户',
                     counterparty='测试往来',payment_method='bank',voucher_no='VIZ-VOUCHER-1',sale_id=sale_one.id,
                     approval_state='approved'))
    db.add(CashEntry(store_id=1,doc_no='VIZ-C-0002',business_date=day-timedelta(days=5),created_by=admin.id,
                     direction='out',category='operating_expense',amount_cents=2_000_000,account='测试账户',
                     payment_method='bank',voucher_no='VIZ-VOUCHER-2',approval_state='approved'))
    db.add(Repair(store_id=1,doc_no='VIZ-R-0001',business_date=day-timedelta(days=4),created_by=admin.id,
                  plate_number='沪A00001',customer_name='测试客户',service_advisor='测试顾问',repair_type='insurance',
                  repair_stage='completed',completion_date=day-timedelta(days=3),labor_amount_cents=500_000,
                  parts_amount_cents=200_000,discount_cents=100_000,cost_amount_cents=300_000,approval_state='approved'))
    db.add(Policy(store_id=1,doc_no='VIZ-P-0001',business_date=day-timedelta(days=6),created_by=admin.id,
                  policy_number='VIZ-POLICY-0001',insurer='测试保险公司',plate_number='沪A00002',customer_name='测试客户',
                  policy_type='commercial',start_date=day-timedelta(days=6),end_date=day+timedelta(days=359),
                  premium_cents=800_000,commission_cents=80_000,approval_state='approved'))
    db.commit()


def seed_many(db):
    """10 个收支分类（触发折叠）+ 12 名销售顾问（触发排行封顶）。"""
    day = today()
    admin = db.scalar(select(User).where(User.role == 'admin'))
    amounts = [1_000_000,900_000,800_000,700_000,600_000,500_000,400_000,300_000,150_000,100_000]
    categories = ['sale_collection','repair_collection','premium_collection','commission','vehicle_purchase',
                  'operating_expense','refund','capital','loan','transfer']
    for index,(category,amount) in enumerate(zip(categories,amounts)):
        db.add(CashEntry(store_id=1,doc_no=f'VIZ-MC-{index:02d}',business_date=day-timedelta(days=2),created_by=admin.id,
                         direction='in' if category != 'vehicle_purchase' else 'out',category=category,amount_cents=amount,
                         account='测试账户',payment_method='bank',voucher_no=f'VIZ-MV-{index:02d}',approval_state='approved'))
    for index in range(12):
        car = Vehicle(store_id=1,doc_no=f'VIZ-RV-{index:02d}',business_date=day-timedelta(days=20),created_by=admin.id,
                      vin=f'LDDVIZR{index:02d}0000000',brand='排行测试品牌',model='可视化测试车',
                      purchase_cost_cents=1_000_000,list_price_cents=2_000_000,approval_state='approved')
        db.add(car); db.flush()
        db.add(Sale(store_id=1,doc_no=f'VIZ-RS-{index:02d}',business_date=day-timedelta(days=20),created_by=admin.id,
                    vehicle_id=car.id,active_vehicle_id=car.id,customer_name='测试客户',salesperson=f'顾问{index+1:02d}',
                    sale_stage='delivered',delivery_date=day-timedelta(days=19),
                    contract_amount_cents=(12-index)*1_000_000,purchase_cost_snapshot_cents=1_000_000,
                    approval_state='approved'))
    db.commit()


def test_visualization_requires_login_and_full_view(client):
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/visualization').status_code == 401
    login(client,'sales')
    assert client.get('/api/visualization').status_code == 403


@pytest.mark.parametrize('days',[7,30,90,365])
def test_empty_database_shape_is_zero_filled(client,days):
    body = payload(client,days=days)
    assert set(body) == PAYLOAD_KEYS
    assert body['currency'] == 'CNY' and body['days'] == days
    assert body['end_date'] == today().isoformat()
    assert body['start_date'] == (today()-timedelta(days=days-1)).isoformat()
    assert isinstance(body['notes'],list) and BASIS in body['notes']
    assert any('分' in note for note in body['notes'])

    assert len(body['kpis']) >= 8
    assert tuple(kpi['key'] for kpi in body['kpis']) == KPI_KEYS
    for kpi in body['kpis']:
        assert set(kpi) == {'key','label','unit','value','hint'}
        assert kpi['unit'] in {'money','count'} and kpi['label'] and isinstance(kpi['hint'],str)
        assert isinstance(kpi['value'],int) and not isinstance(kpi['value'],bool)
        assert kpi['value'] == 0

    assert [trend['id'] for trend in body['trends']] == TREND_IDS
    expected_dates = [(today()-timedelta(days=offset)).isoformat() for offset in range(days-1,-1,-1)]
    for trend in body['trends']:
        assert set(trend) == {'id','title','unit','axis','dates','series'}
        assert trend['axis'] == 'date' and trend['unit'] in {'money','count'} and trend['title']
        assert trend['dates'] == expected_dates and len(trend['dates']) == days
        assert len(trend['series']) >= 3
        for series in trend['series']:
            assert set(series) == {'key','label','values'} and series['label']
            assert len(series['values']) == days
            assert all(isinstance(value,int) and not isinstance(value,bool) for value in series['values'])
            assert all(value == 0 for value in series['values'])

    assert [item['id'] for item in body['breakdowns']] == BREAKDOWN_IDS
    assert [item['id'] for item in body['rankings']] == RANKING_IDS
    for group in body['breakdowns']+body['rankings']:
        assert group['items'] == [] and isinstance(group['dimension'],str) and group['title']
    check_dataset_items(body)


def test_seeded_category_totals_breakdowns_and_rankings(client):
    with SessionLocal() as db: seed(db)
    body = payload(client,days=90)
    kpi = {item['key']:item['value'] for item in body['kpis']}
    assert kpi['delivery_amount'] == 20_000_000 and kpi['delivery_count'] == 2
    assert kpi['repair_amount'] == 600_000 and kpi['repair_completed_count'] == 1
    assert kpi['policy_premium'] == 800_000 and kpi['stock_count'] == 1
    assert kpi['net_cash'] == 4_000_000                       # 流入 6,000,000 - 流出 2,000,000
    assert kpi['receivable'] == 14_600_000                    # 销售 20,000,000 - 已收 6,000,000，加维修应收 600,000

    cash = dataset(body,'breakdowns','cash_category')
    items = {item['key']:item for item in cash['items']}
    assert cash['unit'] == 'money' and cash['dimension'] == 'category'
    assert items['sale_collection']['value'] == 6_000_000     # 已知分类合计必须精确出现
    assert items['sale_collection']['label'] == '销售收款'
    assert items['sale_collection']['share'] == pytest.approx(0.75)
    assert items['operating_expense']['value'] == 2_000_000
    assert sum(item['share'] for item in cash['items']) == pytest.approx(1.0)

    ranking = dataset(body,'rankings','salesperson')
    assert ranking['unit'] == 'money' and ranking['dimension'] == 'salesperson'
    assert [(item['key'],item['value']) for item in ranking['items']] == [('张三',11_000_000),('李四',9_000_000)]
    assert [item['key'] for item in dataset(body,'rankings','insurer')['items']] == ['测试保险公司']
    assert dataset(body,'rankings','insurer')['items'][0]['value'] == 800_000

    assert [(item['key'],item['value']) for item in dataset(body,'breakdowns','stock_brand')['items']] == [('测试库存品牌',8_000_000)]
    repair_items = dataset(body,'breakdowns','repair_type')['items']
    assert [(item['key'],item['label'],item['value']) for item in repair_items] == [('insurance','保险维修',1)]

    money = dataset(body,'trends','money')
    delivery = dict(zip(money['dates'],money['series'][0]['values']))
    assert money['series'][0]['key'] == 'delivery_amount'
    assert delivery[(today()-timedelta(days=9)).isoformat()] == 11_000_000
    assert delivery[(today()-timedelta(days=8)).isoformat()] == 9_000_000
    assert sum(money['series'][0]['values']) == 20_000_000
    check_dataset_items(body)


def test_folding_caps_breakdowns_and_rankings(client):
    with SessionLocal() as db: seed_many(db)
    body = payload(client,days=90)
    cash = dataset(body,'breakdowns','cash_category')
    assert len(cash['items']) == 9                              # 8 项 + 其他
    assert sum(item['value'] for item in cash['items']) == 5_450_000     # 折叠只合并、不丢失金额
    assert cash['items'][-1]['key'] == OTHER['key'] and cash['items'][-1]['label'] == OTHER['label']
    assert cash['items'][-1]['value'] == 250_000                # 尾部 150,000 + 100,000
    assert cash['items'][-1]['share'] == pytest.approx(250_000/5_450_000)
    ranking = dataset(body,'rankings','salesperson')
    assert len(ranking['items']) == 10                          # 封顶 10，不折叠
    assert [item['key'] for item in ranking['items']] == [f'顾问{index:02d}' for index in range(1,11)]
    assert [item['value'] for item in ranking['items']] == [(12-index)*1_000_000 for index in range(10)]
    check_dataset_items(body)


def test_every_money_value_is_integer_cents(client):
    with SessionLocal() as db: seed(db)
    body = payload(client,days=90)
    paths = list(money_values(body))
    assert paths
    for path,value in paths:
        assert isinstance(value,int) and not isinstance(value,bool),path
    sections = {path[0] for path,_ in paths}
    assert {'kpis','trends','breakdowns','rankings'} <= sections
    # 明细里的金额也是整数分：6,000,000 分而不是 60000.0 元
    assert dataset(body,'breakdowns','cash_category')['items'][0]['value'] == 6_000_000
    for group in body['breakdowns']+body['rankings']:
        for item in group['items']:
            assert 'cents' not in str(item['value']) and not isinstance(item['value'],str)


def test_share_is_the_only_float_in_the_payload(client):
    with SessionLocal() as db: seed(db)
    body = payload(client,days=90)
    floats = [(path,value) for path,value in scalars(body) if isinstance(value,float)]
    assert floats                                            # 折叠/占比确实产生了 share
    assert all(path[-1] == 'share' for path,_ in floats)
    assert all(0.0 <= value <= 1.0 for _,value in floats)


def test_kpis_and_series_match_dashboard(client):
    with SessionLocal() as db: seed(db)
    body = payload(client,days=90)
    totals = client.get('/api/dashboard',params={'days':90}).json()['totals']
    kpi = {item['key']:item['value'] for item in body['kpis']}
    assert kpi['delivery_amount'] == totals['delivery_amount_cents']
    assert kpi['delivery_count'] == totals['delivery_count']
    assert kpi['new_order_count'] == totals['new_order_count']
    assert kpi['repair_amount'] == totals['repair_amount_cents']
    assert kpi['repair_completed_count'] == totals['repair_completed_count']
    assert kpi['gross_difference'] == totals['gross_difference_cents']
    assert kpi['policy_premium'] == totals['policy_premium_cents']
    assert kpi['expected_commission'] == totals['expected_commission_cents']
    assert kpi['net_cash'] == totals['net_cash_cents']
    assert kpi['stock_count'] == totals['stock_count']
    assert kpi['aging_stock_count'] == totals['aging_stock_count']
    assert kpi['receivable'] == totals['sales_receivable_cents']+totals['repair_receivable_cents']
    week = client.get('/api/dashboard',params={'days':7}).json()['series']
    money = dataset(payload(client,days=7),'trends','money')
    assert money['dates'] == [row['date'] for row in week]
    assert money['series'][0]['values'] == [row['delivery_amount_cents'] for row in week]


@pytest.mark.parametrize('requested,expected',[(0,7),(-1,7),(1,7),(6,7),(7,7),(30,30),(365,365),(1000,365)])
def test_days_clamping(client,requested,expected):
    body = payload(client,days=requested)
    assert body['days'] == expected
    assert len(body['trends'][0]['dates']) == expected
    assert all(len(series['values']) == expected for trend in body['trends'] for series in trend['series'])
    assert body['start_date'] == (today()-timedelta(days=expected-1)).isoformat()


@pytest.mark.parametrize('bad_end',['not-a-date','2026-13-01','2026-02-30','19/09/2026',''])
def test_invalid_end_date_is_422(client,bad_end):
    # 选择 422：与应用其它接口一致（request_validation_error → 422），而不是 400。
    response = client.get('/api/visualization',params={'end':bad_end})
    assert response.status_code == 422,response.text


def test_future_end_date_is_422(client):
    response = client.get('/api/visualization',params={'end':(today()+timedelta(days=1)).isoformat()})
    assert response.status_code == 422,response.text


def test_explicit_end_window_is_inclusive(client):
    end = today()-timedelta(days=3)
    body = payload(client,end=end.isoformat(),days=7)
    assert body['days'] == 7 and body['end_date'] == end.isoformat()
    assert body['start_date'] == (end-timedelta(days=6)).isoformat()
    expected = [(end-timedelta(days=offset)).isoformat() for offset in range(6,-1,-1)]
    for trend in body['trends']:
        assert trend['dates'] == expected
        assert all(len(series['values']) == 7 for series in trend['series'])


def test_get_writes_no_business_or_audit_rows(client):
    with SessionLocal() as db: seed(db)
    models = [*MODULES.values(),AuditLog,DailyReport,Finding]
    def counts():
        with SessionLocal() as db:
            return {model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in models}
    before = counts()
    body = payload(client,days=30)
    assert {item['key']:item['value'] for item in body['kpis']}['delivery_count'] == 2
    assert counts() == before
    assert client.get('/api/visualization?days=7').status_code == 200
    assert counts() == before


def test_store_scope_matches_dashboard(client):
    """门店隔离复用 get_user→attach_scope 的请求级 scope：切店看不到别店数据。"""
    with SessionLocal() as db: seed(db)
    body = payload(client,days=90)
    assert {item['key']:item['value'] for item in body['kpis']}['delivery_count'] == 2
    second = client.post('/api/stores',json={'code':'EAST','name':'东店测试','active':True})
    assert second.status_code == 201,second.text
    client.headers['X-Store-ID'] = str(second.json()['id'])
    empty = payload(client,days=90)
    assert {item['key']:item['value'] for item in empty['kpis']}['delivery_count'] == 0
    assert dataset(empty,'breakdowns','cash_category')['items'] == []
    assert dataset(empty,'rankings','salesperson')['items'] == []
    assert all(value == 0 for value in dataset(empty,'trends','money')['series'][0]['values'])
    client.headers['X-Store-ID'] = 'all'
    combined = payload(client,days=90)
    assert {item['key']:item['value'] for item in combined['kpis']}['delivery_count'] == 2