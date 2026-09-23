"""Owner-run real-browser brand/dictionary/configuration acceptance.

python tests/browser_master_completion.py [--screenshots OUTSIDE_REPOSITORY]
Only the standard harness's NEW synthetic database and owned local server.
This script has not been treated as passed merely because it compiles.
"""
import secrets
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import create_on_page


def exercise(browser,base,password,output):
    context=browser.new_context(viewport={'width':390,'height':844},locale='zh-CN')
    page=context.new_page();errors=[];steps=[];images=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    req=harness.checked_request;suffix=secrets.token_hex(4)
    try:
        harness.login_page(page,base,'admin',password)
        brand=create_on_page(page,'material_brands','物资品牌',{'code':'MB-'+suffix,'name':'合成零件品牌'+suffix})
        category=create_on_page(page,'material_categories','物资分类',{'code':'MC-'+suffix,'name':'合成耗材'})
        warehouse=create_on_page(page,'warehouses','仓库',{'code':'MW-'+suffix,'name':'合成仓库','warehouse_type':'materials'})
        location=create_on_page(page,'locations','库位',{'code':'ML-'+suffix,'name':'合成库位','warehouse_id':warehouse['id']})
        item=req(page,'/api/flow/master/items','POST',{'values':{'sku':'MI-'+suffix,'name':'合成配件','unit':'件','reorder':'0','active':True}},status=201)
        create_on_page(page,'item_profiles','物资归类与库位',{'item_id':item['id'],'category_id':category['id'],'location_id':location['id'],'brand_id':brand['id']})
        harness.navigate(page,'master/items','物资目录')
        expect(page.locator('#main')).to_contain_text(brand['name']);harness.assert_fits_mobile(page)
        images.append(harness.take_screenshot(page,output,'master_completion_01_brand_directory.png'))
        harness.navigate(page,'masters/material_brands','物资品牌')
        page.locator(f'[data-act=typed-edit][data-id="{brand["id"]}"]').click()
        page.locator('#modal [name=active]').uncheck();page.locator('#modal button[type=submit]').click()
        expect(page.locator('#modal .formerror')).to_contain_text('下游资料引用')
        page.locator('#modal').get_by_role('button', name='取消', exact=True).click()
        steps.append('真实页面维护物资品牌并绑定原目录；仍被启用物资引用的品牌不能停用')
        groups={'public':'公共字典','repair':'维修字典','vehicle':'整车字典','materials':'物资字典','finance':'财务字典','customer':'客户字典','member':'会员字典'}
        text='<script>window.__dictionary_injected=true</script>'
        for key,label in groups.items():
            harness.navigate(page,'dictionaries/'+key,label)
            page.locator('[data-act=dictionary-new]').click()
            page.locator('#modal [name=name]').fill('合成领域条目'+suffix)
            page.locator('#modal [name=detail]').fill(text)
            harness.save_modal(page)
            expect(page.locator('#main')).to_contain_text(text)
            assert page.evaluate('()=>window.__dictionary_injected') is None
            data=req(page,'/api/dictionaries/'+key)['items'][0]
            assert data['category']==label
        page.locator('[data-act=dictionary-edit]').click()
        page.locator('#modal [name=active]').uncheck();harness.save_modal(page)
        assert req(page,'/api/dictionaries/member')['items'][0]['active'] is False
        harness.assert_fits_mobile(page);images.append(harness.take_screenshot(page,output,'master_completion_02_separate_dictionary.png'))
        steps.append('七类字典分别保存；同名不串类，说明按文本显示而不执行脚本，支持停用')
        harness.navigate(page,'parameters','参数与个人密码')
        expect(page.locator('#main')).to_contain_text('部署参数（只读）')
        page.locator('#main [data-route="service-intake/resources"]').click()
        expect(page.locator('#main h1')).to_have_text('工位与快捷项目')
        harness.navigate(page,'parameters','参数与个人密码')
        page.locator('#main [data-act=password]').click()
        expect(page.locator('#modal [name=current_password]')).to_be_visible()
        page.locator('#modal').get_by_role('button', name='取消', exact=True).click()
        harness.assert_fits_mobile(page);images.append(harness.take_screenshot(page,output,'master_completion_03_parameter_entry.png'))
        steps.append('参数入口打开原工位配置与本人改密对话框，不生成另一套规则或资金接口')
        two=req(page,'/api/stores','POST',{'code':'MC2-'+suffix,'name':'合成第二门店','active':True},status=201)['id']
        page.reload();expect(page.locator('#store')).to_be_visible();page.locator('#store').select_option(str(two))
        harness.navigate(page,'dictionaries/repair','维修字典')
        expect(page.locator('#main')).not_to_contain_text('合成领域条目'+suffix)
        assert req(page,'/api/dictionaries/repair',store=two)['items']==[]
        steps.append('换店后领域字典不保留前店条目')
        assert not errors,errors
        return {'status':'passed','mode':'actual-browser-http','synthetic_only':True,
                'steps':steps,'screenshots':images,'javascript_errors':errors,'viewport':'390x844'}
    finally:context.close()


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
