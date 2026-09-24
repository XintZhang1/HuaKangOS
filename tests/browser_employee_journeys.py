"""Real employee clicks for simplified entry; fresh synthetic database only."""
import re,secrets,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import expect
from tests import browser_huakangos as h

def choose(page,name,query,match=None):
    root=page.locator(f'#modal select[name="{name}"]').locator('..')
    root.locator('[data-lookup-query]').fill(query)
    option=root.get_by_role('option',name=re.compile(match or re.escape(query))).first
    expect(option).to_be_visible();option.click()

def exercise(browser,base,password,output):
    context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN')
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    steps=[];screenshots=[]
    try:
        h.login_page(page,base,'admin',password)
        employee_passwords={}
        for role in ['manager','sales','finance']:
            initial=secrets.token_urlsafe(24);new=secrets.token_urlsafe(24)
            h.checked_request(page,'/api/users','POST',{'username':'entry-'+role,'display_name':'试用'+role,'password':initial,'role':role,'store_ids':[1],'store_roles':[{'store_id':1,'role':role}]},status=201)
            employee_passwords[role]=(initial,new)
        repair=h.create_repair_source(page,1)
        def as_employee(role):
            h.checked_request(page,'/api/auth/logout','POST',{})
            initial,new=employee_passwords[role]
            h.login_page(page,base,'entry-'+role,initial)
            h.checked_request(page,'/api/auth/password','POST',{'current_password':initial,'new_password':new})
            h.login_page(page,base,'entry-'+role,new)
        as_employee('manager')
        page.locator('[data-act=catalog-entry]').click()
        page.locator('#modal [name=brand_name]').fill('试用品牌')
        page.locator('#modal [name=series_name]').fill('试用车系')
        page.locator('#modal [name=name]').fill('纯电旗舰型')
        page.locator('#modal [name=fuel_type]').select_option('electric')
        expect(page.locator('#modal [name=displacement]')).not_to_be_visible()
        page.locator('#modal [name=battery]').fill('60.5')
        page.locator('#modal [name=price]').fill('139800')
        screenshots.append(h.take_screenshot(page,output,'01-one-model-form.png'))
        h.save_modal(page)
        catalogue=h.checked_request(page,'/api/vehicle-catalog')
        assert catalogue['total']==1 and catalogue['items'][0]['series_name']=='试用车系'
        steps.append('主管在一张表完成品牌、车系、车型，保存即有明确归属')
        page.locator('[data-act=newcase][data-kind=order]').click()
        page.locator('#modal [name=customer_name]').fill('草稿客户')
        page.locator('#modal [name=amount]').fill('133000')
        page.locator('#modal [name=terms]').fill('客户约定车价，其他服务另计')
        page.locator('[data-act=quote-inline-model]').click()
        choose(page,'brand_id','试用品牌')
        choose(page,'series_id','试用车系')
        page.locator('#modal [name=name]').fill('纯电舒适型')
        page.locator('#modal [name=fuel_type]').select_option('electric')
        page.locator('#modal [name=battery]').fill('50')
        page.locator('#modal button[type=submit]').click()
        expect(page.locator('#modal-title')).to_have_text('新建预订合同')
        expect(page.locator('#modal [name=customer_name]')).to_have_value('草稿客户')
        expect(page.locator('#modal [name=amount]')).to_have_value('133000')
        expect(page.locator('#modal select[name=model]')).not_to_have_value('')
        page.locator('[data-act=quote-inline-model]').click()
        page.locator('#modal [data-act=close]').first.click()
        expect(page.locator('#modal-title')).to_have_text('新建预订合同')
        expect(page.locator('#modal [name=terms]')).to_have_value('客户约定车价，其他服务另计')
        page.locator('#modal [data-act=close]').first.click()
        assert h.checked_request(page,'/api/flow/cases?kind=order')['total']==0
        steps.append('预订中补建车型或取消补建后返回原表，客户、金额、约定保留；取消预订不创建客户订单')
        as_employee('sales');page.set_viewport_size({'width':390,'height':844})
        # The reservation entrance belongs to sales, not inventory.
        nav=page.locator('.sidebar details').filter(has=page.locator('summary',has_text='整车销售'))
        expect(nav.locator('a[href="#sales-quotes"]')).to_have_text('预订与合同')
        page.locator('[data-act=newcase][data-kind=order]').click()
        page.locator('#modal [name=customer_name]').fill('一步预订客户')
        page.locator('#modal [name=customer_phone]').fill('13900009625')
        choose(page,'model','旗舰型')
        page.locator('#modal [name=amount]').fill('139000')
        page.locator('#modal [name=terms]').fill('客户约定车辆价款，不包含另单服务')
        h.assert_fits_mobile(page);screenshots.append(h.take_screenshot(page,output,'02-mobile-reservation.png'))
        attempts=[]
        def uncertain_once(route):
            if route.request.method!='POST':route.continue_();return
            attempts.append(route.request.post_data_json)
            if len(attempts)==1:
                response=route.fetch();assert response.status==201
                route.abort('failed')
            else:route.continue_()
        page.route('**/api/sales-quotes/orders',uncertain_once)
        page.locator('#modal button[type=submit]').click()
        expect(page.locator('#modal .formerror')).to_contain_text('提交结果尚未确认')
        expect(page.locator('#modal [name=customer_name]')).to_be_disabled()
        assert h.checked_request(page,'/api/flow/cases?kind=order')['total']==1
        h.save_modal(page)
        assert len(attempts)==2 and attempts[0]==attempts[1]
        page.unroute('**/api/sales-quotes/orders',uncertain_once)
        expect(page.locator('#main h1')).to_have_text(re.compile('预订合同 ·'))
        expect(page.locator('[data-act=downloadfile]').first).to_be_visible()
        orders=h.checked_request(page,'/api/flow/cases?kind=order')['items'];assert len(orders)==1
        detail=h.checked_request(page,'/api/sales-quotes/orders/'+str(orders[0]['id']))
        assert detail['pending_quote_id'] and not detail['active_quote_id']
        assert detail['customer']['name']=='一步预订客户'
        page.locator('[data-act=upload][data-category=signed_contract]').click()
        expect(page.locator('#file-category')).to_have_value('signed_contract')
        page.locator('#modal [data-act=close]').first.click()
        h.navigate(page,'sales-quotes','车辆报价与预订')
        page.locator('[data-act=sales-quote-new]').click()
        page.locator('#modal [name=customer_name]').fill('一步预订')
        page.locator('[data-customer-id]').click()
        expect(page.locator('#modal [name=customer_name]')).to_have_value('一步预订客户')
        page.locator('#modal [data-act=close]').first.click()
        steps.append('销售390px同屏新客户预订；服务端成功但首个响应丢失后，原请求原内容重试取回唯一订单；已有客户实时匹配')
        as_employee('finance')
        h.navigate(page,'case/'+str(repair['case']['id']),repair['case']['title'])
        page.locator('[data-act=caseaction][data-key=receive]').click()
        page.locator('#modal [name=amount]').fill('100.00')
        choose(page,'account_id','集团验收账户')
        page.locator('#modal [name=reference]').fill('INLINE-TRIAL-RECEIPT')
        page.locator('[data-act=inline-file-open]').click()
        page.locator('[data-inline-category]').select_option('receipt')
        page.locator('[data-inline-file]').set_input_files({'name':'合成收款.txt','mimeType':'text/plain','buffer':'虚构试用收款凭据'.encode()})
        page.locator('[data-act=inline-file-upload]').click()
        expect(page.locator('[data-inline-file-status]')).to_contain_text('已选用')
        expect(page.locator('#modal [name=reference]')).to_have_value('INLINE-TRIAL-RECEIPT')
        expect(page.locator('#modal [name=amount]')).to_have_value('100.00')
        h.assert_fits_mobile(page);screenshots.append(h.take_screenshot(page,output,'03-inline-receipt.png'))
        h.save_modal(page)
        result=h.checked_request(page,'/api/flow/cases/'+str(repair['case']['id']))
        assert sum(p['amount_cents'] for p in result['payments'] if p['direction']=='in')==10000
        steps.append('财务在收款表内上传并选用凭据，金额账户流水不丢失，原接口登记唯一100元收款')
        assert not errors,errors
        return {'mode':'real Windows Chrome HTTP, synthetic employee accounts','steps':steps,'screenshots':screenshots,'javascript_errors':errors,'provider_calls':0,'company_accepted':False}
    except Exception:
        h.take_screenshot(page,output,'failure.png');raise
    finally:context.close()

h.exercise=exercise
if __name__=='__main__':h.main()
