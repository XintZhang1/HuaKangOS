"""Real local Chrome UI checks with deterministic, explicitly mocked assistant replies.

The employee login, store switch, application and CSS use real HTTP. Only the
assistant endpoints are mocked here; this is not DeepSeek/business acceptance.
"""
import json
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import expect
from tests import browser_huakangos as h


def exercise(browser,base,password,output):
    context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN')
    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    steps=[];screenshots=[];sessions={};issues=[];messages=[];confirmations=[]
    try:
        h.login_page(page,base,'admin',password)
        second=h.checked_request(page,'/api/stores','POST',{'name':'助手合成二店','code':'ASSISTANT-UI-2'},status=201)
        initial,next_password=secrets.token_urlsafe(24),secrets.token_urlsafe(24)
        h.checked_request(page,'/api/users','POST',{'username':'assistant-ui-sales','display_name':'助手试用销售','password':initial,'role':'sales',
            'store_ids':[1,second['id']],'store_roles':[{'store_id':1,'role':'sales'},{'store_id':second['id'],'role':'sales'}]},status=201)
        h.checked_request(page,'/api/auth/logout','POST',{})
        h.login_page(page,base,'assistant-ui-sales',initial)
        h.checked_request(page,'/api/auth/password','POST',{'current_password':initial,'new_password':next_password})
        h.login_page(page,base,'assistant-ui-sales',next_password)

        def assistant(route):
            request=route.request;path=urlsplit(request.url).path.removeprefix('/api/business-assistant');store=request.headers.get('x-store-id','1')
            body=request.post_data_json if request.method=='POST' else {};session=sessions.get(store)
            status=200;result={}
            if path=='/status':result={'enabled':True,'ready':True,'model':'deterministic-ui-fixture','message':'可以开始办理业务','limits':{'max_message_chars':6000}}
            elif path=='/sessions' and request.method=='GET':result={'items':[session] if session else []}
            elif path=='/sessions' and request.method=='POST':
                status=201;session={'id':'synthetic-session-'+store,'title':'接待试用','created_at':'2026-09-23T09:00:00Z','updated_at':'2026-09-23T09:00:00Z','busy':False,'messages':[],'proposals':[]};sessions[store]=session;result=session
            elif path.endswith('/messages/stream'):
                messages.append(body);session['messages'].append({'role':'user','content':body['content']})
                if len(messages)==1:answer='请补充客户姓名和电话。'
                else:
                    answer='请确认下面的接待信息。\n<img src=x onerror="alert(1)">'
                    session['proposals']=[{'id':'synthetic-proposal','label':'登记售前接待','status':'pending','digest':'f'*64,'summary':'为合成客户登记一次展厅接待。',
                        'expires_at':'2099-01-01T00:00:00Z','display_fields':[{'label':'客户姓名','value':'合成客户'},{'label':'联系电话','value':'13900000001'},{'label':'客户来源','value':'展厅到店'}]}]
                session['messages'].append({'role':'assistant','content':answer});result=session
            elif path.endswith('/confirm'):
                confirmations.append(body);session['proposals'][0].update(status='succeeded',result={'message':'已办理','links':[{'label':'查看接待','route':'cases/lead'}]});result=session
            elif path.endswith('/issues') and request.method=='POST':
                status=201;issue={'id':1,'session_id':session['id'],'category':body['category'],'summary':body['summary'],'created_at':'2026-09-23T09:00:00Z'};issues.append(issue);result=issue
            elif path=='/issues':result={'items':issues}
            elif path.startswith('/sessions/'):result=session
            else:raise AssertionError({'unexpected_assistant_request':path})
            if path.endswith('/messages/stream'):
                route.fulfill(status=status,content_type='text/event-stream',body='event: done\ndata: '+json.dumps({'session':result},ensure_ascii=False)+'\n\n')
            else:
                route.fulfill(status=status,content_type='application/json',body=json.dumps(result,ensure_ascii=False))

        page.route('**/api/business-assistant/**',assistant)
        h.navigate(page,'business-assistant','业务助手')
        expect(page.locator('.identity .role')).to_have_text('销售')
        expect(page.locator('.navlink[href="#business-assistant"]')).to_be_visible()
        page.locator('[data-ba-action=suggestion]').filter(has_text='登记客户接待').click()
        expect(page.locator('#business-assistant-input')).to_have_value('帮我登记一次售前接待。')
        page.locator('#business-assistant-input').press('Enter')
        expect(page.locator('#business-assistant-messages')).to_contain_text('请补充客户姓名和电话。')
        page.locator('#business-assistant-input').fill('合成客户，13900000001，展厅到店')
        page.locator('#business-assistant-form button[type=submit]').click()
        expect(page.locator('.ba-proposal')).to_contain_text('合成客户')
        expect(page.locator('#business-assistant-messages img')).to_have_count(0)
        assert len(messages)==2 and messages[0]['request_id']!=messages[1]['request_id']
        steps.append('实际销售账号通过独立业务助手入口完成两轮补充问答；回复按纯文字显示')
        screenshots.append(h.take_screenshot(page,output,'assistant-desktop.png'))

        page.set_viewport_size({'width':390,'height':844})
        h.assert_fits_mobile(page)
        page.locator('[data-ba-action=confirm]').scroll_into_view_if_needed()
        screenshots.append(h.take_screenshot(page,output,'assistant-mobile-confirm.png'))
        page.locator('[data-ba-action=confirm]').click()
        expect(page.locator('.ba-proposal')).to_contain_text('已完成')
        expect(page.locator('[data-ba-action=confirm]')).to_have_count(0)
        assert confirmations==[{'digest':'f'*64}]
        expect(page.locator('.ba-record-link')).to_have_attribute('href','#cases/lead')
        steps.append('390px窄屏完整展示待办详情，显式确认只发送一次冻结凭据，完成后提供原页面入口')

        page.locator('[data-ba-action=issues]').click()
        page.locator('[data-ba-action=report]').click()
        page.locator('#modal [name=summary]').fill('合成试用：需要更清楚的客户来源选项')
        h.assert_fits_mobile(page)
        h.save_modal(page)
        expect(page.locator('.ba-issues')).to_contain_text('合成试用：需要更清楚的客户来源选项')
        steps.append('销售可记录问题并从问题清单返回原对话')
        page.locator('[data-ba-action=issue-session]').click()
        expect(page.locator('#business-assistant-input')).to_be_visible()
        page.locator('#business-assistant-input').fill('一店未发送的客户资料')
        page.locator('#store').select_option(str(second['id']))
        expect(page.locator('#main h1')).to_have_text('我的工作')
        h.navigate(page,'business-assistant','业务助手')
        expect(page.locator('#business-assistant-input')).to_have_value('')
        expect(page.locator('#main')).not_to_contain_text('一店未发送的客户资料')
        expect(page.locator('#main')).not_to_contain_text('合成客户')
        steps.append('切换门店后对话和输入草稿全部清空，不展示原店内容')
        h.assert_fits_mobile(page)
        assert not errors,errors
        return {'mode':'real Windows Chrome employee UI; assistant responses mocked','steps':steps,'screenshots':screenshots,'javascript_errors':errors,
                'limitations':['仅验证问答前端交互和显示；不证明DeepSeek调用或业务入账成功','真实登录与岗位切换使用独立合成数据库']}
    except Exception:
        h.take_screenshot(page,output,'assistant-ui-failure.png');raise
    finally:context.close()


h.exercise=exercise
if __name__=='__main__':h.main()
