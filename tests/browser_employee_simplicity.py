"""Isolated real-browser checks for employee wording and recovery interactions."""
import io,secrets,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from playwright.sync_api import expect
from tests import browser_huakangos as h

def exercise(browser,base,password,output):
    context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN')
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    steps=[]
    try:
        page.goto(base)
        expect(page.locator('.hk-login-message')).to_have_count(0)
        expect(page.locator('.hk-eyebrow')).to_have_count(0)
        h.take_screenshot(page,output,'login.png')
        h.login_page(page,base,'admin',password)
        h.navigate(page,'parameters','参数与个人密码')
        page.locator('[data-act=brand-photo]').click()
        stream=io.BytesIO();Image.new('RGB',(1000,600),'#789abc').save(stream,format='PNG')
        page.locator('#modal [name=file]').set_input_files({'name':'trial.png','mimeType':'image/png','buffer':stream.getvalue()})
        h.save_modal(page)
        expect(page.locator('.brand-photo-preview')).to_be_visible()
        page.locator('[data-act=brand-photo-reset]').click()
        expect(page.locator('#toast')).to_have_text('已恢复默认图片')
        steps.append('管理员通过页面更换并恢复登录图片')
        ep=secrets.token_urlsafe(24);np=secrets.token_urlsafe(24)
        user=h.checked_request(page,'/api/users','POST',{'username':'simple-sales','display_name':'试用销售','password':ep,'role':'sales','store_ids':[1],'store_roles':[{'store_id':1,'role':'sales'}]},status=201)
        x=h.checked_request(page,'/api/flow/cases','POST',{'kind':'lead','request_id':secrets.token_hex(16),'values':{'customer_name':'无电话客户','source':'展厅到店'}},status=201)
        h.navigate(page,'case/'+str(x['id']),x['title'])
        page.locator('[data-act=caseaction][data-key=assign]').click()
        search=page.locator('#modal [data-lookup-query]')
        search.fill('试用销售')
        expect(page.locator('#modal .lookup-options button')).to_have_count(1)
        search.press('ArrowDown');page.keyboard.press('Enter')
        h.save_modal(page)
        steps.append('单框实时查找员工，键盘选择并分派接待')
        h.checked_request(page,'/api/auth/logout','POST',{})
        h.login_page(page,base,'simple-sales',ep)
        h.checked_request(page,'/api/auth/password','POST',{'current_password':ep,'new_password':np})
        h.login_page(page,base,'simple-sales',np)
        page.set_viewport_size({'width':390,'height':844})
        h.navigate(page,'case/'+str(x['id']),x['title'])
        page.locator('[data-act=caseaction][data-key=remind]').click()
        expect(page.locator('#modal [name=customer_phone]')).to_have_attribute('required','')
        page.locator('#modal [name=customer_phone]').fill('13900007777')
        page.locator('#modal [name=result]').fill('补电话后回访')
        h.assert_fits_mobile(page);h.take_screenshot(page,output,'callback-phone.png')
        h.save_modal(page)
        detail=h.checked_request(page,'/api/flow/cases/'+str(x['id']))
        assert detail['customer']['phone']=='13900007777' and detail['state']=='reminder'
        steps.append('390px销售账号补电话并安排回访')
        h.navigate(page,'work','我的工作')
        page.locator('[data-act=newcase][data-kind=order]').click()
        expect(page.locator('#modal-title')).to_have_text('新建预订合同')
        expect(page.locator('#modal')).to_contain_text('暂无车型')
        page.locator('#modal [data-act=close]').first.click()
        steps.append('无车型时保留预订表单并显示添加车型指引')
        page.locator('[data-act=newcase][data-kind=lead]').click()
        page.locator('#modal [name=customer_name]').fill('无电话')
        expect(page.locator('[data-act=choice-select]')).to_have_count(1)
        expect(page.locator('#modal [name=choice_query]')).to_have_count(0)
        page.locator('[data-act=choice-select]').click()
        expect(page.locator('#modal [name=customer_phone]')).to_have_value('13900007777')
        page.locator('#modal [data-act=close]').first.click()
        h.assert_fits_mobile(page);h.take_screenshot(page,output,'work-mobile.png')
        steps.append('客户姓名实时显示匹配结果，选择后带入电话，无第二个搜索框')
        assert not errors,errors
        return {'mode':'real Windows Chrome HTTP','steps':steps,'javascript_errors':errors,'company_accepted':False}
    except Exception:
        h.take_screenshot(page,output,'failure.png');raise
    finally:context.close()

h.exercise=exercise
if __name__=='__main__':h.main()
