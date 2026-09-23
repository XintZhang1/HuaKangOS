"""Actual employee Chrome HTTP acceptance for typed masters and opening import.

python tests/browser_masters.py [--screenshots OUTSIDE_REPOSITORY]
Creates a new synthetic database, random passwords and an owned temporary server.
"""
from pathlib import Path
import argparse
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import httpx
from playwright.sync_api import sync_playwright,expect
from browser_huakangos import (chromium_path,request,checked_request,login_page,navigate,
    save_modal,assert_fits_mobile)

ROOT=Path(__file__).resolve().parents[1]


def take_screenshot(page,output,filename):
    expect(page.locator('#toast')).not_to_have_class(re.compile('visible'),timeout=7000)
    modal=page.locator('#modal').is_visible()
    if not modal:page.evaluate('()=>window.scrollTo(0,0)')
    path=output/filename;page.screenshot(path=str(path),full_page=not modal)
    return str(path)


def employee_login(page,base,username,password):
    login_page(page,base,username,password)
    expect(page.locator('#modal [name=current_password]')).to_be_visible()
    changed=secrets.token_urlsafe(28)
    page.locator('#modal [name=current_password]').fill(password)
    page.locator('#modal [name=new_password]').fill(changed)
    save_modal(page)
    login_page(page,base,username,changed)
    return changed


def create_on_page(page,kind,label,values):
    navigate(page,'masters/'+kind,label)
    page.locator('[data-act=typed-new]').click()
    expect(page.locator('#modal')).to_be_visible()
    for key,value in values.items():
        field=page.locator('#modal [name='+key+']')
        if field.evaluate('(el)=>el.tagName')=='SELECT':field.select_option(str(value))
        elif isinstance(value,bool):field.set_checked(value)
        else:field.fill(str(value))
    save_modal(page)
    return checked_request(page,'/api/masters/'+kind)['items'][0]


def exercise(browser,base,password,output):
    steps=[];images=[];errors=[]
    contexts=[browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN') for _ in range(4)]
    for context in contexts:context.on('page',lambda page:page.on('pageerror',lambda error:errors.append(str(error))))
    admin,manager,inventory,reception=[c.new_page() for c in contexts]
    try:
        login_page(admin,base,'admin',password)
        two=checked_request(admin,'/api/stores','POST',{'code':'OPEN-B','name':'虚构期初乙店','active':True},status=201)['id']
        accounts={}
        for username,role in [('opening-manager','manager'),('opening-stock','inventory'),('opening-front','reception')]:
            initial=secrets.token_urlsafe(28)
            checked_request(admin,'/api/users','POST',{'username':username,'display_name':'合成验收'+role,
                'password':initial,'role':role,'store_roles':[{'store_id':1,'role':role},{'store_id':two,'role':role}],
                'can_group_summary':role=='manager'},status=201)
            accounts[username]=initial
        employee_login(manager,base,'opening-manager',accounts['opening-manager'])
        expect(manager.locator('.identity .role')).to_have_text('店长 / 老板')
        supplier=create_on_page(manager,'suppliers','供应商',{'code':'SYNTH-S','name':'虚构耗材供应商','tax_identifier':'TEST-ONLY','payment_terms_days':30})
        warehouse=create_on_page(manager,'warehouses','仓库',{'code':'SYNTH-W','name':'虚构物资仓','warehouse_type':'materials'})
        location=create_on_page(manager,'locations','库位',{'code':'SYNTH-L','name':'虚构一号库位','warehouse_id':warehouse['id']})
        category=create_on_page(manager,'material_categories','物资分类',{'code':'SYNTH-C','name':'虚构耗材分类'})
        steps.append('店长账号经真实网页建立供应商、物资仓、库位及分类，库位选择本店启用仓库')

        create_on_page(manager,'vehicle_models','车型参数',{'code':'SYNTH-E','name':'虚构纯电五座','brand':'虚构品牌','model_year':2026,'fuel_type':'electric','seats':5,'displacement_ml':0,'battery_wh':60000,'guide_price_cents':'120000.00'})
        create_on_page(manager,'vehicle_models','车型参数',{'code':'SYNTH-P','name':'虚构燃油七座','brand':'虚构品牌','model_year':2026,'fuel_type':'petrol','seats':7,'displacement_ml':2000,'battery_wh':0,'guide_price_cents':'180000.00'})
        manager.locator('#typed-model-filters [name=fuel_type]').select_option('electric')
        manager.locator('#typed-model-filters [name=min_seats]').fill('5')
        manager.locator('#typed-model-filters [name=max_price]').fill('150000')
        manager.locator('#typed-model-filters button[type=submit]').click()
        expect(manager.locator('#main')).to_contain_text('虚构纯电五座')
        expect(manager.locator('#main')).not_to_contain_text('虚构燃油七座')
        steps.append('车型动力、座位、指导价筛选作用于实际列表，参考售价按元精确转分')

        manager.set_viewport_size({'width':390,'height':844})
        navigate(manager,'opening','期初资料导入')
        manager.locator('[data-act=opening-example]').click()
        expect(manager.locator('#opening-source')).not_to_have_value('')
        source=manager.locator('#opening-source').input_value();invalid=json.loads(source)
        invalid['items'][0]['opening_quantity_milli']=1.5
        manager.locator('#opening-source').fill(json.dumps(invalid,ensure_ascii=False))
        manager.locator('[data-act=opening-preflight]').click()
        expect(manager.locator('#main')).to_contain_text('逐行检查结果')
        assert manager.locator('[data-act=opening-trial]').count()==0
        assert checked_request(manager,'/api/flow/master/items')['items']==[]
        assert_fits_mobile(manager)
        images.append(take_screenshot(manager,output,'01_mobile_opening_row_errors.png'))
        steps.append('390px 店长页面逐行拒绝小数千分位，错误资料未建立任何物资或期初批次')

        source+='\r\n'  # A real file's trailing newline is part of its reviewed digest.
        manager.locator('#opening-file').set_input_files({'name':'合成期初清单.json','mimeType':'application/json','buffer':source.encode('utf-8')})
        expect(manager.locator('#opening-source')).to_have_value(source.replace('\r\n','\n'))
        # The display normalizes line endings, but unchanged uploaded source must be retained.
        manager.locator('[data-act=opening-preflight]').click()
        expect(manager.locator('[data-act=opening-trial]')).to_be_visible()
        prepared=checked_request(manager,'/api/masters/opening/batches')['items'][0]
        assert checked_request(manager,f'/api/masters/opening/{prepared["id"]}/source')['source_text']==source
        manager.locator('[data-act=opening-trial]').click()
        expect(manager.locator('[data-act=opening-confirm]')).to_be_visible()
        manager.locator('#opening-source').fill(source+' ')
        manager.locator('[data-act=opening-confirm]').click()
        expect(manager.locator('#toast')).to_contain_text('原资料已改变')
        expect(manager.locator('#modal')).not_to_be_visible()
        manager.locator('#opening-source').fill(source)
        assert checked_request(manager,'/api/flow/master/items')['items']==[]
        assert checked_request(manager,'/api/flow/master/customers')['items']==[]
        assert checked_request(manager,'/api/flow/master/accounts')['items']==[]
        images.append(take_screenshot(manager,output,'02_mobile_trial_rolled_back.png'))
        steps.append('真实网页预检及试导入后，客户、账户、物资均仍为空，页面保留原摘要与汇总')

        manager.locator('[data-act=opening-confirm]').click()
        expect(manager.locator('#modal')).to_contain_text('123.45')
        assert_fits_mobile(manager)
        images.append(take_screenshot(manager,output,'03_mobile_opening_confirmation.png'))
        manager.locator('#modal [name=confirmed]').check()
        save_modal(manager)
        expect(manager.locator('#main')).to_contain_text('已确认入账')
        assert len(checked_request(manager,'/api/flow/master/items')['items'])==2
        assert len(checked_request(manager,'/api/flow/master/customers')['items'])==1
        assert len(checked_request(manager,'/api/flow/master/accounts')['items'])==1
        navigate(manager,'opening-stock','期初与库存流水')
        expect(manager.locator('#main')).to_contain_text('123.45')
        ledger=checked_request(manager,'/api/masters/opening/stockflow')
        assert ledger['all_reconciled'] and ledger['rows'][0]['value_cents']==12345
        with manager.expect_download() as waiting:manager.locator('[data-act=opening-stock-export]').click()
        download=waiting.value;csvpath=output/'synthetic-stockflow.csv';download.save_as(str(csvpath))
        text=csvpath.read_text(encoding='utf-8-sig')
        assert '12345' in text and '合成盘点表-第1行' in text
        assert_fits_mobile(manager)
        images.append(take_screenshot(manager,output,'04_mobile_opening_stockflow.png'))
        steps.append('店长确认实际入账，2.5 单位与 123.45 元由期初原账可核对，真实下载 CSV 同口径')

        employee_login(inventory,base,'opening-stock',accounts['opening-stock'])
        inventory.set_viewport_size({'width':390,'height':844})
        item=next(r for r in checked_request(inventory,'/api/flow/master/items')['items'] if r['sku']=='TEST-OIL')
        create_on_page(inventory,'item_profiles','物资归类与库位',{'item_id':item['id'],'category_id':category['id'],'location_id':location['id'],'supplier_id':supplier['id']})
        navigate(inventory,'masters/warehouses','仓库')
        inventory.locator('[data-act=typed-edit]').click()
        inventory.locator('#modal [name=active]').uncheck()
        inventory.locator('#modal button[type=submit]').click()
        expect(inventory.locator('#modal .formerror')).to_contain_text('仍有启用的下游资料引用')
        assert_fits_mobile(inventory)
        images.append(take_screenshot(inventory,output,'05_mobile_active_reference_refusal.png'))
        inventory.locator('#modal [data-act=close]').first.click()
        steps.append('库管从期初目录建立真实分类库位绑定；被使用的仓库停用时网页显示中文拒绝原因')

        navigate(inventory,'masters/suppliers','供应商')
        expect(inventory.locator('#main')).not_to_contain_text('约定付款天数')
        expect(inventory.locator('#main')).not_to_contain_text('TEST-ONLY')
        navigate(inventory,'opening-stock','期初与库存流水')
        expect(inventory.locator('#main')).not_to_contain_text('价值')
        expect(inventory.locator('#main')).not_to_contain_text('NaN')
        expect(inventory.locator('#main')).not_to_contain_text('undefined')
        assert checked_request(inventory,'/api/masters/opening/stockflow')['can_money'] is False
        assert request(inventory,'/api/masters/opening/preflight','POST',{'request_id':secrets.token_hex(16),'source_text':source})['status']==403
        images.append(take_screenshot(inventory,output,'06_mobile_inventory_quantity_only.png'))
        steps.append('库管只能核对库存数量，API 与网页均无库存价值或供应商付款条件，不能导入期初')

        manager.locator('#store').select_option(str(two))
        expect(manager).to_have_url(re.compile(r'#work$'))
        navigate(manager,'masters/suppliers','供应商')
        expect(manager.locator('#main')).not_to_contain_text('虚构耗材供应商')
        refused=request(manager,'/api/masters/locations','POST',{'request_id':secrets.token_hex(16),
            'values':{'code':'BAD','name':'越店引用拒绝','warehouse_id':warehouse['id']}},store=two)
        assert refused['status']==422 and '当前门店' in refused['body']['detail']
        manager.locator('#store').select_option('all')
        expect(manager.locator('.identity .role')).to_have_text('集团汇总（只读）')
        assert request(manager,'/api/masters/suppliers','POST',{'request_id':secrets.token_hex(16),
            'values':{'code':'NO','name':'禁止汇总新建'}},store='all')['status']==409
        steps.append('切店看不到另一店供应商，跨店引用被 API 拒绝，集团汇总主数据写入被拒绝')

        employee_login(reception,base,'opening-front',accounts['opening-front'])
        assert checked_request(reception,'/api/masters/catalog')['kinds']=={}
        reception.evaluate("location.hash='masters/suppliers'")
        expect(reception.locator('#main')).to_contain_text('经营主资料类型不存在')
        assert request(reception,'/api/masters/suppliers')['status']==403
        assert request(reception,'/api/masters/lookup/suppliers')['status']==403
        steps.append('前台账号目录不提供经营设置，直接请求列表和查找均拒绝，权限不依赖菜单')
        assert not errors,errors
        return {'mode':'actual Chrome HTTP, isolated synthetic database','passed':len(steps),'steps':steps,
            'screenshots':images,'javascript_errors':errors,'limitations':['生产 HTTPS 与 PostgreSQL 尚需部署验证','全部资料为虚构，仅证明技术验收场景']}
    finally:
        for context in contexts:context.close()


def main():
    sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--screenshots',type=Path);args=parser.parse_args()
    executable=chromium_path()
    if not executable:raise SystemExit('请安装 Chrome/Edge 或设置 CHROMIUM_PATH。')
    output=(args.screenshots or Path(tempfile.mkdtemp(prefix='huakangos-masters-evidence-'))).resolve()
    if output==ROOT or ROOT in output.parents:raise SystemExit('截图和验收输出必须位于仓库之外。')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='huakangos-masters-db-') as directory:
        work=Path(directory)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}';password=secrets.token_urlsafe(28)
        env={**os.environ,'DATABASE_URL':'sqlite:///'+(work/'synthetic.sqlite').as_posix(),
            'FILE_STORAGE_MODE':'blob','PRIVATE_FILE_ROOT':'',
            'APP_ENV':'test','ALLOWED_HOSTS':'127.0.0.1,localhost','COOKIE_SECURE':'false',
            'SCHEDULER_ENABLED':'false','SCHEDULER_MODE':'off','FILE_SCAN_MODE':'structure_only','ALLOW_AI_EXTERNAL':'false',
            'DEEPSEEK_API_KEY':'','LEGACY_BUSINESS_WRITE':'false','HUAKANGOS_INITIAL_PASSWORD':password,
            'DEALER_INITIAL_PASSWORD':password,'PYTHONUTF8':'1'}
        initialized=subprocess.run([sys.executable,'-m','app.cli','init'],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
        if initialized.returncode:raise RuntimeError('隔离测试库初始化失败：'+initialized.stderr)
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        with (work/'server.log').open('w',encoding='utf-8') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=flags)
            try:
                with httpx.Client(base_url=base,timeout=2,trust_env=False) as client:
                    for _ in range(120):
                        if server.poll() is not None:raise RuntimeError('隔离测试服务启动失败。')
                        try:
                            if client.get('/api/health').status_code==200:break
                        except httpx.HTTPError:pass
                        time.sleep(.1)
                    else:raise RuntimeError('隔离测试服务未能就绪。')
                with sync_playwright() as p:
                    browser=p.chromium.launch(executable_path=executable,headless=True)
                    try:
                        result=exercise(browser,base,password,output)
                        (output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                        print(json.dumps(result,ensure_ascii=False,indent=2))
                    finally:browser.close()
            finally:
                if os.name=='nt' and server.poll() is None:subprocess.run(['taskkill','/PID',str(server.pid),'/T','/F'],capture_output=True,creationflags=flags)
                elif server.poll() is None:server.terminate()
                try:server.wait(timeout=10)
                except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)


if __name__=='__main__':main()
