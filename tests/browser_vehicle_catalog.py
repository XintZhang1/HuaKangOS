"""Real employee Chrome catalogue acceptance, only an independent synthetic DB."""
import os,secrets,subprocess,sys
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login,take_screenshot,create_on_page

def prepare_database(env,work):
    script="""
from app.db import SessionLocal,today
from app.models import Vehicle,User
from sqlalchemy import select
from app.tenancy import set_scope
with SessionLocal() as db:
    set_scope(db,[1],1)
    admin=db.scalar(select(User).where(User.role=='admin'))
    db.add(Vehicle(store_id=1,doc_no='SYNTH-CATALOG',business_date=today(),approval_state='approved',created_by=admin.id,
        vin='LCA7AL0G000000001',brand='旧文本品牌',model='合成待核对车辆',purchase_cost_cents=8000001,list_price_cents=10000000))
    db.commit()
"""
    result=subprocess.run([sys.executable,'-X','utf8','-c',script],env=env,cwd=harness.ROOT,capture_output=True,text=True,encoding='utf-8')
    if result.returncode:raise RuntimeError(result.stderr)

def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];images=[];req=harness.checked_request
    def page():
        ctx=browser.new_context(viewport={'width':390,'height':844},locale='zh-CN');contexts.append(ctx)
        p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    admin=page()
    try:
        harness.login_page(admin,base,'admin',password)
        second=req(admin,'/api/stores','POST',{'code':'CAT-B','name':'合成车型乙店','active':True},status=201)
        people={}
        for role in ['manager','inventory','sales']:
            initial=secrets.token_urlsafe(28);username='catalog-'+role
            req(admin,'/api/users','POST',{'username':username,'display_name':'合成目录'+role,'password':initial,
                'role':role,'store_roles':[{'store_id':1,'role':role},{'store_id':second['id'],'role':role}]},status=201)
            p=page();employee_login(p,base,username,initial);people[role]=p
        manager,inventory,sales=[people[r] for r in ['manager','inventory','sales']]
        brand=create_on_page(manager,'vehicle_brands','车辆品牌',{'code':'CAT-B','name':'合成明确品牌'})
        series=create_on_page(manager,'vehicle_series','车辆车系',{'code':'CAT-S','name':'合成城市车系','brand_id':brand['id']})
        model=create_on_page(manager,'vehicle_models','车型参数',{'code':'CAT-E','name':'合成纯电五座','brand':'合成品牌文本','model_year':2026,'fuel_type':'electric','seats':5,'battery_wh':60000,'guide_price_cents':'120000'})
        harness.navigate(manager,'vehicle-catalog','车型展示与可选库存')
        expect(manager.locator('#main')).to_contain_text('待确认车型的本店车辆')
        manager.locator('[data-act=catalog-classify-model]').click();manager.locator('#modal [name=target]').select_option(str(series['id']))
        manager.locator('#modal [name=reason]').fill('合成原车系目录逐项核对');harness.save_modal(manager)
        expect(manager.locator('#main')).to_contain_text('合成城市车系')
        steps.append('主管真实页面建立品牌车系和车型，明确关联，旧同名库存未自动绑定')
        harness.navigate(inventory,'vehicle-catalog','车型展示与可选库存')
        inventory.locator('[data-act=catalog-classify-vehicle]').click()
        inventory.locator('#modal [data-typed-query]').fill('纯电');inventory.locator('#modal [data-act=typed-lookup]').click()
        inventory.locator('#modal [name=target]').select_option(str(model['id']))
        inventory.locator('#modal [name=vin]').fill('LCA7AL0G000000002');inventory.locator('#modal [name=reason]').fill('按虚构实车VIN及原资料逐项核对')
        inventory.locator('#modal button[type=submit]').click();expect(inventory.locator('#modal .formerror')).to_contain_text('VIN')
        harness.assert_fits_mobile(inventory);images.append(take_screenshot(inventory,output,'01_catalog_vin_refused.png'))
        inventory.locator('#modal [name=vin]').fill('LCA7AL0G000000001');harness.save_modal(inventory)
        expect(inventory.locator('#main')).not_to_contain_text('待确认车型的本店车辆')
        steps.append('库管按关键词查目录，错误VIN拒绝，正确VIN明确绑定而不改原采购金额')
        harness.navigate(sales,'vehicle-catalog','车型展示与可选库存')
        sales.locator('#vehicle-catalog-filters [name=brand_id]').select_option(str(brand['id']))
        sales.locator('#vehicle-catalog-filters [name=series_id]').select_option(str(series['id']))
        sales.locator('#vehicle-catalog-filters [name=fuel_type]').select_option('electric')
        sales.locator('#vehicle-catalog-filters [name=min_seats]').fill('5')
        sales.locator('#vehicle-catalog-filters [name=max_price]').fill('130000')
        sales.locator('#vehicle-catalog-filters [name=available_only]').check()
        sales.locator('#vehicle-catalog-filters button[type=submit]').click()
        expect(sales.locator('#main')).to_contain_text('合成纯电五座')
        sales.locator('#main details summary').click();expect(sales.locator('#main')).to_contain_text('LCA7AL0G000000001')
        expect(sales.locator('[data-act=catalog-classify-model]')).to_have_count(0)
        assert 'purchase_cost_cents' not in str(req(sales,'/api/vehicle-catalog'))
        harness.assert_fits_mobile(sales);images.append(take_screenshot(sales,output,'02_catalog_sales_filters.png'))
        # A new tenant selection clears filters and cached vehicle identities.
        sales.locator('#store').select_option(str(second['id']))
        expect(sales.locator('#main')).not_to_contain_text('LCA7AL0G000000001')
        expect(sales.locator('#main')).not_to_contain_text('合成纯电五座')
        expect(sales.locator('#main h1')).to_have_text('我的工作')
        harness.navigate(sales,'vehicle-catalog','车型展示与可选库存')
        expect(sales.locator('#vehicle-catalog-filters [name=brand_id]')).to_have_value('')
        assert req(sales,'/api/vehicle-catalog',store=second['id'])['total']==0
        steps.append('销售390px按品牌车系参数及可配状态筛选，成本未下发；切换门店后原店缓存清除')
        assert not errors,errors
        return {'passed':True,'employee_roles':['manager','inventory','sales'],'steps':steps,'screenshots':images,'js_errors':errors}
    finally:
        for ctx in contexts:ctx.close()

if __name__=='__main__':
    harness.prepare_database=prepare_database;harness.exercise=exercise;harness.main()
