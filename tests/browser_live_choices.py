"""Standalone real Chromium DOM acceptance of live search controls; no business DB or model."""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import expect, sync_playwright
from tests.browser_huakangos import chromium_path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('浏览器证据必须保存到源码目录之外')
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    steps = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium_path(), headless=True)
        context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_content('''<!doctype html><html lang="zh-CN"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>
        <form id="form"><label id="local">车型<select name="model" required data-search-select><option value="">请选择</option><option value="1" selected>比亚迪 秦 PLUS</option><option value="2">大众 朗逸</option><option value="3" disabled>停用车型</option><option value="new" data-search-create>+ 新增车型</option></select></label>
        <label id="remote">客户<div class="typed-ref" data-kind="customers"><div class="lookuprow"><input type="search" data-typed-query><button type="button" data-act="typed-lookup">查找</button></div><select name="customer" required><option value="">请选择</option><option value="10" selected>原客户</option></select></div></label>
        <label>状态<select name="status"><option value="new">新建</option><option value="done">完成</option></select></label>
        <button type="submit">保存</button><button type="reset">重置</button></form><div id="outside" tabindex="0">其他区域</div><div id="modal"></div></body></html>''')
        page.add_style_tag(content=(ROOT/'web/styles.css').read_text(encoding='utf-8-sig')+'body{padding:16px}label{display:block}button{min-height:44px}.lookup-active{background:#fce8ec}')
        page.add_script_tag(content='''let storeContextVersion=1;window.calls=[];window.failure=false;window.slow=false;
        async function api(url){calls.push(url);const q=new URL(url,'https://fixture.invalid').searchParams.get('q');if(window.slow&&q==='旧查询')await new Promise(r=>setTimeout(r,650));if(window.failure)throw new Error('网络暂不可用');return {items:[{id:q==='新查询'?22:21,label:q+'客户'}]};}
        document.querySelector('#form').addEventListener('submit',e=>e.preventDefault());window.changeCount=0;document.querySelector('#local select').addEventListener('change',()=>changeCount++);''')
        page.add_script_tag(content=(ROOT/'web/livechoices.js').read_text(encoding='utf-8-sig'))
        local = page.locator('#local input')
        remote = page.locator('#remote input')
        try:
            expect(local).to_have_value('比亚迪 秦 PLUS')
            expect(remote).to_have_value('原客户')
            expect(page.locator('#remote [data-act=typed-lookup]')).to_have_count(0)
            expect(page.locator('#remote select')).to_be_hidden()
            expect(page.locator('select[name=status]')).to_be_visible()
            steps.append('页面内原 typed-ref 自动变单框，已有值保留，普通状态枚举不改变')

            local.fill('朗逸')
            expect(page.locator('#local .lookup-options [role=option]')).to_have_count(2)
            local.press('ArrowDown')
            local.press('Enter')
            expect(local).to_have_value('大众 朗逸')
            assert page.locator('#local select').input_value() == '2'
            assert page.evaluate("new FormData(document.querySelector('#form')).get('model')") == '2'
            assert page.evaluate('changeCount') == 2
            local.fill('找不到的型号')
            expect(page.locator('#local [role=option]')).to_have_text('+ 新增车型')
            local.press('Enter')
            assert page.locator('#local select').input_value() == 'new'
            steps.append('键盘选择同步原 ID 和 change；新增入口保留；FormData 使用原选择值')

            local.fill('')
            assert page.evaluate("document.querySelector('#local input').validity.valueMissing")
            assert page.evaluate("document.querySelector('#local select').required")
            assert not page.evaluate("document.querySelector('#form').checkValidity()")
            page.evaluate("document.querySelector('#form').reset()")
            page.wait_for_timeout(100)
            expect(local).to_have_value('比亚迪 秦 PLUS')
            page.evaluate("document.querySelector('#local select').innerHTML='<option value=\"\">请选择</option><option value=\"9\" selected>动态车型</option>'")
            expect(local).to_have_value('动态车型')
            page.evaluate("document.querySelector('#local select').disabled=true")
            expect(local).to_be_disabled()
            page.evaluate("document.querySelector('#local select').disabled=false;document.querySelector('#local select').required=false")
            expect(local).to_be_enabled()
            assert not page.locator('#local input').evaluate('(el)=>el.required')
            steps.append('清空必选、表单重置、动态选项、required 和 disabled 均保留原语义')

            page.evaluate('calls=[]')
            remote.evaluate("el=>{el.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));el.value='zhang';el.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:true}));}")
            page.wait_for_timeout(300)
            assert page.evaluate('calls.length') == 0
            remote.evaluate("el=>{el.value='张三';el.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}));}")
            expect(page.locator('#remote [role=option]')).to_have_text('张三客户')
            page.locator('#remote [role=option]').tap()
            assert page.locator('#remote select').input_value() == '21'
            expect(remote).to_have_value('张三客户')
            steps.append('中文输入完成才查询，手机触屏选择写入原客户 ID')

            page.evaluate('window.slow=true')
            remote.fill('旧查询')
            page.wait_for_function("calls.some(url=>decodeURIComponent(url).includes('旧查询'))")
            remote.fill('新查询')
            expect(page.locator('#remote [role=option]')).to_have_text('新查询客户')
            page.wait_for_timeout(700)
            expect(page.locator('#remote [role=option]')).to_have_text('新查询客户')
            steps.append('先发后到的旧查询不覆盖新结果')

            page.evaluate('window.failure=true')
            remote.fill('重试')
            expect(page.locator('#remote [data-lookup-retry]')).to_be_visible()
            page.evaluate('window.failure=false')
            page.locator('#remote [data-lookup-retry]').tap()
            expect(page.locator('#remote [role=option]')).to_have_text('重试客户')
            steps.append('查询失败可就地重试，不恢复已失效的旧选择')

            page.evaluate('calls=[]')
            remote.fill('店一客户')
            page.evaluate('storeContextVersion++;clearLiveChoices()')
            page.wait_for_timeout(350)
            assert page.evaluate('calls.length') == 0
            expect(remote).to_have_value('')
            expect(page.locator('#remote .lookup-options')).to_be_hidden()
            assert page.locator('#remote select option').all_text_contents() == ['']
            steps.append('切店使定时查询、输入、旧候选和选择一起失效')

            page.evaluate("document.querySelector('#modal').innerHTML='<form><label>新增搜索<select name=\"part\" data-search-select><option value=\"\">请选择</option><option value=\"90\">合成配件</option></select></label></form>'")
            late = page.locator('#modal input')
            expect(late).to_be_visible()
            late.fill('合成')
            page.locator('#modal [role=option]').tap()
            assert page.locator('#modal select').input_value() == '90'
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
            steps.append('后插入页面或弹窗的实体选择自动接入，390px 无横向溢出')

            page.add_script_tag(content="""let state={user:{id:7},store:'1',page:1,dates:{start:'2026-09-01',end:'2026-09-24'}};window.renderCount=0;function render(){renderCount++}function toast(){}
            api=async url=>{calls.push(url);return {items:[{id:44,label:'已停用历史配件'}],has_more:false}};""")
            page.add_script_tag(content=(ROOT/'web/inventoryreports.js').read_text(encoding='utf-8-sig'))
            page.evaluate("document.querySelector('#modal').innerHTML='<form id=\"warehouse-report-filters\"><label>物资<select name=\"item_id\" data-search-select data-warehouse-report-kind=\"items\" data-search-all=\"全部物资\" data-search-placeholder=\"全部物资\"><option value=\"\">全部物资</option><option value=\"9\" selected>旧配件</option></select></label></form>';warehouseReportContext().filters={item_id:'9'};calls=[]")
            history = page.locator('#warehouse-report-filters input')
            expect(history).to_have_value('旧配件')
            history.fill('历史')
            expect(page.locator('#warehouse-report-filters [role=option]')).to_have_text(['已停用历史配件'])
            assert page.evaluate('renderCount') == 0
            assert '/api/inventory-reports/warehouses/options/items?q=' in page.evaluate('calls[0]')
            page.locator('#warehouse-report-filters [role=option]').tap()
            assert page.evaluate('warehouseReportContext().filters.item_id') == '44'
            assert page.evaluate('renderCount') == 1
            history.fill('')
            expect(page.locator('#warehouse-report-filters [role=option]')).to_have_text(['全部物资', '已停用历史配件'])
            assert page.evaluate('warehouseReportContext().filters.item_id===undefined')
            page.locator('#warehouse-report-filters [role=option]').first.tap()
            expect(history).to_have_value('')
            assert page.evaluate("document.querySelector('#warehouse-report-filters').checkValidity()")
            steps.append('库位历史筛选走原停用资料接口；选择即刷新，全部选项与清空一致')
            assert not errors, errors
            page.screenshot(path=str(output/'live-choices-mobile.png'),full_page=True)
            result={'passed':True,'mode':'standalone real Chromium DOM; synthetic API fixture; no business database or model','steps':steps,'javascript_errors':errors}
            (output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'passed':True,'checks':len(steps),'output':str(output)},ensure_ascii=False))
        except Exception:
            page.screenshot(path=str(output/'failure.png'),full_page=True)
            (output/'errors.json').write_text(json.dumps(errors,ensure_ascii=False),encoding='utf-8')
            raise
        finally:
            context.close()
            browser.close()


if __name__=='__main__':
    main()



