"""Original Chromium UI against an isolated real backend and synthetic model.

Native and fixture transports are explicit and reported separately. Tests keep
the application CSP intact; asynchronous state waits are polled from Python,
not evaluated through an injected in-page eval/timer loop.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fixture_env
import asyncio,json,sqlite3,unittest
from contextlib import closing
from uuid import uuid4
from browser_harness import BrowserHarness

class BrowserUI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h=await BrowserHarness().start();self.page=self.h.page
        try:await self.h.login()
        except BaseException:
            print("SETUP",self.h.requests[-8:],flush=True)
            await self.h.close();raise
    async def asyncTearDown(self):
        try:
            await self.page.screenshot(path=str(fixture_env.VALIDATION/'evidence'/f'{self._testMethodName}.png'),full_page=True)
            (fixture_env.VALIDATION/'evidence'/f'{self._testMethodName}.json').write_text(json.dumps({'page_errors':self.h.errors,'requests':self.h.requests},ensure_ascii=False,indent=2))
            self.assertEqual(self.h.errors,[])
        finally:await self.h.close()
    async def send(self,text):
        await self.page.locator('#business-assistant-input').fill(text)
        await self.page.locator('#business-assistant-form [type=submit]').click()
    async def wait_state(self, expression, *, arg=None, timeout=8000):
        """Poll a read-only DevTools expression without an in-page eval loop."""
        deadline = asyncio.get_running_loop().time() + timeout / 1000
        while True:
            if await self.page.evaluate(expression, arg):
                return
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("Browser state did not settle: " + expression)
            await asyncio.sleep(0.05)

    async def settled(self):
        await self.wait_state('!!businessAssistantState.runStop && !businessAssistantState.busy && !businessAssistantState.runId',timeout=15000)
    def customer_count(self,name):
        with closing(sqlite3.connect('file:'+str(fixture_env.RUNTIME/'browser.sqlite')+'?mode=ro',uri=True)) as db:
            return db.execute('select count(*) from flow_customers where name=?',(name,)).fetchone()[0]
    def posts(self):return [r for r in self.h.requests if r['method']=='POST' and r['path'].startswith('/api/business-assistant/')]
    async def test_01_empty_page_and_suggestion_do_not_send(self):
        if self.h.mode == "native":
            self.assertIn("script-src 'self'", self.h.csp)
            self.assertNotIn("unsafe-eval", self.h.csp)
            self.assertNotIn("unsafe-inline", self.h.csp.split("script-src", 1)[1].split(";", 1)[0])
            self.assertIn("[native code]", await self.page.evaluate("Function.prototype.toString.call(window.fetch)"))
        self.assertNotIn('[object Promise]',await self.page.locator('#main').inner_text())
        before=len(self.posts());suggestions=self.page.locator('[data-ba-action="suggestion"]')
        self.assertGreater(await suggestions.count(),0);self.assertLessEqual(await suggestions.count(),4)
        await suggestions.first.click();self.assertTrue(await self.page.locator('#business-assistant-input').input_value())
        draft=await self.page.locator('#business-assistant-input').input_value()
        await suggestions.last.click();self.assertEqual(await self.page.locator('#business-assistant-input').input_value(),draft)
        self.assertEqual(len(self.posts()),before)
    async def test_02_shift_enter_keeps_newline_without_sending(self):
        before=len(self.posts());text=self.page.locator('#business-assistant-input')
        await text.fill('第一行');await text.press('Shift+Enter');await text.type('第二行')
        self.assertEqual(await text.input_value(),'第一行\n第二行');self.assertEqual(len(self.posts()),before)
    async def test_03_query_finishes_with_actual_conversation_and_no_card(self):
        await self.send('查询本店张姓客户，只读');await self.settled()
        self.assertIn('已核对本店客户资料',await self.page.locator('#main').inner_text())
        self.assertEqual(await self.page.evaluate('businessAssistantState.session.proposals.length'),0)
        self.assertEqual(len([r for r in self.posts() if r['path'].endswith('/runs')]),1)
        self.assertFalse(any('/confirm' in r['path'] for r in self.posts()))
    async def test_04_prepare_confirm_and_history_preserve_exactly_once(self):
        name='离线浏览器客户'+uuid4().hex[:10]
        await self.send('新建客户'+name+'，暂不允许联系。');await self.settled()
        self.assertEqual(self.customer_count(name),0)
        self.assertEqual(await self.page.evaluate('businessAssistantState.session.proposals[0].status'),'pending')
        self.assertGreater(await self.page.locator('#business-assistant-messages').evaluate('e=>e.clientHeight'),80)
        confirm=self.page.locator('[data-ba-action="confirm"]')
        rect=await confirm.bounding_box();layout=await self.page.locator('#business-assistant').bounding_box()
        self.assertLessEqual(rect['y']+rect['height'],layout['y']+layout['height'])
        await confirm.click()
        await self.wait_state('businessAssistantState.session?.proposals?.[0]?.status==="succeeded"',timeout=15000)
        self.assertEqual(self.customer_count(name),1)
        # A real refresh and history reopen must not repeat the native command.
        await self.page.locator('[data-ba-action="refresh"]').click()
        await self.page.locator('#business-assistant-input').wait_for()
        self.assertEqual(self.customer_count(name),1)
        self.assertEqual(len([r for r in self.posts() if r['path'].endswith('/confirm')]),1)
    async def test_05_leave_and_return_during_run_does_not_lose_result(self):
        await self.send('慢速查询本店张姓客户')
        await self.wait_state('!!businessAssistantState.runId',timeout=15000)
        await self.page.locator('a[href="#work"]').click()
        await self.wait_state('state.route==="work"')
        await self.page.locator('a[href="#business-assistant"]').click()
        await self.settled()
        self.assertIn('已核对本店客户资料',await self.page.locator('#main').inner_text())
        self.assertEqual(len([r for r in self.posts() if r['path'].endswith('/runs')]),1)
    async def test_06_switch_store_drops_old_run_and_draft(self):
        await self.send('慢速查询旧门店张姓客户')
        await self.wait_state('!!businessAssistantState.runId',timeout=15000)
        await self.page.locator('#store').select_option('2')
        await self.wait_state('String(state.store)==="2" && !state.storeSwitch',timeout=15000)
        await self.page.locator('a[href="#business-assistant"]').click()
        await self.page.locator('#business-assistant-input').wait_for()
        await self.page.wait_for_timeout(2500)
        self.assertEqual(await self.page.locator('#business-assistant-input').input_value(),'')
        self.assertNotIn('旧门店张姓客户',await self.page.locator('#main').inner_text())
        self.assertTrue(await self.page.evaluate('!!state.user'))
    async def test_07_malformed_model_output_never_creates_card(self):
        await self.send('模拟异常，尝试新建客户离线浏览器客户Invalid');await self.settled()
        self.assertEqual(self.customer_count('离线浏览器客户Invalid'),0)
        self.assertEqual(await self.page.evaluate('businessAssistantState.session.proposals.length'),0)
        self.assertEqual(await self.page.evaluate('businessAssistantState.runView.status'),'failed')
        self.assertIn('未完成',await self.page.locator('#main').inner_text())
    async def test_08_responsive_input_and_drawer_are_operable(self):
        for width in [1440,768,390]:
            await self.page.set_viewport_size({'width':width,'height':960})
            await self.page.locator('#business-assistant-input').fill('保留草稿')
            self.assertTrue(await self.page.locator('#business-assistant-input').is_visible())
            self.assertLessEqual(await self.page.evaluate('document.documentElement.scrollWidth'),width+1)
            await self.page.screenshot(path=str(fixture_env.VALIDATION/'evidence'/f'assistant-{width}.png'),full_page=True)
        await self.page.locator('[data-baws-action="drawer"]').click()
        self.assertTrue(await self.page.locator('.ba-runtime-workspace').evaluate('e=>e.classList.contains("drawer-open")'))
        await self.page.locator('[data-baws-action="drawer-close"]').click(position={'x':350,'y':100})
        self.assertEqual(await self.page.locator('#business-assistant-input').input_value(),'保留草稿')

    async def test_09_mobile_card_tab_and_confirmation_are_accessible(self):
        name='离线浏览器客户'+uuid4().hex[:10]
        await self.page.set_viewport_size({'width':390,'height':960})
        await self.send('新建客户'+name+'，暂不允许联系。');await self.settled()
        self.assertEqual(self.customer_count(name),0)
        await self.page.locator('[data-ba-action="pane-cards"]').click()
        self.assertFalse(await self.page.locator('#business-assistant-input').is_visible())
        confirm=self.page.locator('[data-ba-action="confirm"]');self.assertTrue(await confirm.is_visible())
        rect=await confirm.bounding_box();layout=await self.page.locator('#business-assistant').bounding_box()
        self.assertLessEqual(rect['y']+rect['height'],layout['y']+layout['height'])
        await confirm.click()
        await self.wait_state('businessAssistantState.session?.proposals?.[0]?.status==="succeeded"',timeout=15000)
        self.assertEqual(self.customer_count(name),1)
        await self.page.locator('[data-ba-action="pane-chat"]').click()
        self.assertTrue(await self.page.locator('#business-assistant-input').is_visible())
    async def test_10_explicit_stop_never_prepares_a_card(self):
        await self.send('慢速查询本店客户')
        await self.wait_state('!!businessAssistantState.runId',timeout=15000)
        await self.page.locator('[data-ba-action="stop"]').click()
        # Progress can change the optimistic version; the UI then reads it back.
        try:await self.wait_state('businessAssistantState.runView?.status==="cancelled"',timeout=1000)
        except Exception:
            if await self.page.locator('[data-ba-action="stop"]').count():await self.page.locator('[data-ba-action="stop"]').click()
        await self.settled()
        self.assertEqual(await self.page.evaluate('businessAssistantState.runView.status'),'cancelled')
        self.assertEqual(await self.page.evaluate('businessAssistantState.session.proposals.length'),0)
        self.assertFalse(any('/confirm' in r['path'] for r in self.posts()))

    async def create_followup_plan(self):
        headers={'X-App-Request':'1','X-Store-ID':'1','X-CSRF-Token':self.h.http.cookies.get('dealer_csrf')}
        ids=[]
        for _ in range(2):
            r=await self.h.http.post('/api/flow/cases',headers=headers,json={
                'request_id':'fixture_'+uuid4().hex,'kind':'lead',
                'values':{'customer_name':'合成浏览器接待'+uuid4().hex[:8],'source':'展厅到店'}})
            self.assertEqual(r.status_code,201,r.text);ids.append(r.json()['id'])
        users=await self.h.http.get('/api/users',headers=headers)
        employee=next(u['id'] for u in users.json()['items'] if u['username']=='demo_sales')
        await self.send(f'离线接待计划：依次分派接待单 {ids[0]} 和 {ids[1]}，接手员工 {employee}，每一步都由我确认。')
        await self.settled()
        self.assertEqual(await self.page.evaluate('businessAssistantState.session.work_plans.length'),1)
        return ids, await self.page.evaluate('businessAssistantState.session.id'), await self.page.evaluate('businessAssistantState.session.work_plans[0].id')

    async def test_11_new_plan_offers_followup_without_manual_navigation(self):
        await self.create_followup_plan()
        # No page refresh or hidden test-side loadPlan: the real conversation
        # must expose its new Plan and explicit human grant entry by itself.
        enable=self.page.locator('[data-baws-followup="enable"]')
        await enable.wait_for(state='visible',timeout=5000)
        self.assertTrue(await enable.is_enabled())
        self.assertFalse(any('/followup' in r['path'] for r in self.posts()))
        self.assertEqual(await self.page.evaluate('businessAssistantState.session.proposals.length'),0)


    async def wait_browser_db(self, sql, params, predicate, timeout=45):
        deadline=asyncio.get_running_loop().time()+timeout
        while True:
            with closing(sqlite3.connect('file:'+str(fixture_env.RUNTIME/'browser.sqlite')+'?mode=ro',uri=True)) as db:
                rows=db.execute(sql,params).fetchall()
            if predicate(rows):return rows
            if asyncio.get_running_loop().time()>=deadline:self.fail('Database wait failed: '+sql+' '+repr(rows))
            await asyncio.sleep(.15)

    async def test_12_explicit_followup_notifications_and_each_confirmation(self):
        ids,sid,pid=await self.create_followup_plan()
        enable=self.page.locator('[data-baws-followup="enable"]');await enable.wait_for()
        await enable.click()
        await self.wait_state('AssistantWorkspace.snapshot().plan?.grant==="active"')
        await self.page.locator('#business-assistant-input').fill('不要覆盖我的草稿')
        for index in range(2):
            rows=await self.wait_browser_db(
                'select id,status from business_assistant_proposals where session_id=? order by created_at',
                (sid,),lambda rows:len(rows)==index+1 and rows[-1][1]=='pending')
            card=rows[-1][0]
            # Merely preparing the card must leave this original task open.
            with closing(sqlite3.connect(fixture_env.RUNTIME/'browser.sqlite')) as db:
                self.assertEqual(db.execute("select status from flow_tasks where case_id=? and key='assign'",(ids[index],)).fetchone()[0],'open')
            notices=await self.wait_browser_db(
                'select id from business_assistant_notifications where session_id=? and proposal_id=? order by created_at desc',
                (sid,card),bool)
            notice_id=notices[0][0]
            button=self.page.locator('[data-baws-action="notices"]')
            if await button.get_attribute('aria-expanded')=='true':await button.click()
            await button.click()
            notice=self.page.locator('[data-baws-action="notice-open"][data-notice-id="'+notice_id+'"]')
            await notice.wait_for();await notice.click()
            await self.wait_state('(id)=>businessAssistantState.session?.proposals?.some(c=>c.id===id)',arg=card)
            self.assertEqual(await self.page.locator('#business-assistant-input').input_value(),'不要覆盖我的草稿')
            await self.page.locator('[data-ba-action="confirm"][data-id="'+card+'"]').click()
            await self.wait_state('(id)=>businessAssistantState.session?.proposals?.some(c=>c.id===id&&c.status==="succeeded")',arg=card)
        await self.wait_browser_db('select status from business_assistant_work_plans where id=?',(pid,),lambda r:r and r[0][0]=='completed')
        await self.page.locator('[data-baw-action="refresh"]').click()
        await self.wait_state('AssistantWorkspace.snapshot().plan?.status==="completed"')
        self.assertEqual(await self.page.locator('#business-assistant-input').input_value(),'不要覆盖我的草稿')
        self.assertEqual(len([r for r in self.posts() if r['path'].endswith('/followup')]),1)
        self.assertEqual(len([r for r in self.posts() if r['path'].endswith('/confirm')]),2)
        self.assertEqual(len([r for r in self.posts() if r['path'].endswith('/runs')]),1)
        self.assertEqual(await self.page.locator('[data-baws-followup="enable"]').count(),0)

    async def test_13_sales_v4_sign_and_delivery_require_separate_human_confirmation(self):
        """Original v4 order/documents/actions with a synthetic provider only."""
        import httpx
        from datetime import date,timedelta
        headers=lambda client:{'X-App-Request':'1','X-Store-ID':'1','X-CSRF-Token':client.cookies.get('dealer_csrf')}
        admin=self.h.http
        async def post(path,body,client=admin,status=200):
            response=await client.post(path,headers=headers(client),json=body)
            self.assertEqual(response.status_code,status,response.text)
            return response.json()
        model=(await post('/api/vehicle-catalog/entry',{'request_id':'fixture_'+uuid4().hex,
            'brand_name':'合成浏览器品牌','series_name':'合成浏览器车系','name':'合成浏览器报价车型',
            'model_year':2026,'fuel_type':'petrol','seats':5,'displacement_ml':1500}))['model']
        with closing(sqlite3.connect('file:'+str(fixture_env.RUNTIME/'browser.sqlite')+'?mode=ro',uri=True)) as db:
            customer=db.execute('select id from flow_customers where store_id=1 order by id limit 1').fetchone()[0]
            account=db.execute('select id from flow_accounts where store_id=1 and active=1 order by id limit 1').fetchone()[0]
            car=db.execute('select id,version,vin from vehicles where store_id=1 '
                'and id not in (select vehicle_id from flow_vehicle_holds) '
                'and id not in (select active_vehicle_id from sales where active_vehicle_id is not null) order by id limit 1').fetchone()
        self.assertIsNotNone(car)
        await post('/api/vehicle-catalog/vehicle-assignment',{'request_id':'fixture_'+uuid4().hex,
            'version':0,'reason':'合成浏览器车型核对','vehicle_id':car[0],'vehicle_version':car[1],'vin':car[2],'model_id':model['id']})
        order=await post('/api/sales-quotes/orders',{'request_id':'fixture_'+uuid4().hex,'customer_id':customer,
            'quote':{'model_id':model['id'],'model_version':model['version'],'amount_cents':100000,
                'delivery_due':(date.today()+timedelta(days=5)).isoformat(),
                'valid_until':(date.today()+timedelta(days=3)).isoformat(),
                'addon':False,'insurance':False,'agency':False,'terms':'合成浏览器销售条款','reason':'合成首次报价'}},status=201)
        ident=order['id'];self.assertEqual(order['flow_version'],4)
        async def detail(client=admin):
            response=await client.get(f'/api/sales-quotes/orders/{ident}',headers=headers(client))
            self.assertEqual(response.status_code,200,response.text);return response.json()
        async def action(key,values,client=admin):
            current=await detail(client)
            return await post(f'/api/flow/cases/{ident}/actions/{key}',
                {'request_id':'fixture_'+uuid4().hex,'version':current['version'],'values':values},client)
        async def upload(category,source=None):
            data={'category':category}
            if source is not None:data['source_file_id']=str(source)
            response=await admin.post(f'/api/flow/cases/{ident}/files',headers=headers(admin),data=data,
                files={'file':('synthetic.txt',('合成凭据，不是真实签名 '+uuid4().hex).encode(),'text/plain')})
            self.assertEqual(response.status_code,200,response.text);return response.json()['id']
        async def signed_file(kind):
            source=await post(f'/api/flow/cases/{ident}/documents',{'kind':kind})
            return await upload('signed_contract' if kind=='contract' else 'signed_handover',source['id'])
        reviewer_name='sales_browser_'+uuid4().hex[:12];password=fixture_env.PASSWORD.read_text()
        await post('/api/users',{'username':reviewer_name,'display_name':'合成独立报价审核人','role':'manager',
            'password':password+'Initial','store_ids':[1],'store_roles':[{'store_id':1,'role':'manager'}]},status=201)
        async with httpx.AsyncClient(base_url='http://127.0.0.1:8765',trust_env=False,timeout=30) as reviewer:
            response=await reviewer.post('/api/auth/login',headers={'X-App-Request':'1'},
                json={'username':reviewer_name,'password':password+'Initial'})
            self.assertEqual(response.status_code,200,response.text)
            await post('/api/auth/password',{'current_password':password+'Initial','new_password':password},reviewer)
            response=await reviewer.post('/api/auth/login',headers={'X-App-Request':'1'},
                json={'username':reviewer_name,'password':password})
            self.assertEqual(response.status_code,200,response.text)
            await action('quote_approve',{'reason':'独立批准合成报价'},reviewer)
        await action('allocate',{'vehicle_id':car[0]})
        signed=await signed_file('contract')
        await self.send(f'离线销售计划：销售单 {ident}，合同签回 {signed}，先签回后提车，每一步都由我确认。')
        await self.settled()
        self.assertEqual(await self.page.evaluate('businessAssistantState.session.work_plans.length'),1)
        sid=await self.page.evaluate('businessAssistantState.session.id')
        pid=await self.page.evaluate('businessAssistantState.session.work_plans[0].id')
        await self.page.locator('[data-baws-followup="enable"]').click()
        await self.wait_state('AssistantWorkspace.snapshot().plan?.grant==="active"')
        await self.page.locator('#business-assistant-input').fill('保留销售跟进草稿')
        async def confirm_notice(index):
            rows=await self.wait_browser_db(
                'select id,status from business_assistant_proposals where session_id=? order by created_at',
                (sid,),lambda rows:len(rows)==index+1 and rows[-1][1]=='pending',timeout=70)
            card=rows[-1][0]
            notices=await self.wait_browser_db(
                'select id from business_assistant_notifications where session_id=? and proposal_id=? order by created_at desc',
                (sid,card),bool)
            button=self.page.locator('[data-baws-action="notices"]')
            if await button.get_attribute('aria-expanded')=='true':await button.click()
            await button.click()
            notice=self.page.locator('[data-baws-action="notice-open"][data-notice-id="'+notices[0][0]+'"]')
            await notice.wait_for();await notice.click()
            await self.wait_state('(id)=>businessAssistantState.session?.proposals?.some(c=>c.id===id)',arg=card)
            self.assertEqual(await self.page.locator('#business-assistant-input').input_value(),'保留销售跟进草稿')
            current=await detail()
            if index==0:self.assertIsNone(current['active_quote_id'])
            else:
                self.assertNotEqual(current['state'],'delivered')
                self.assertIsNot(current['business_facts']['facts']['sales.delivery_recorded'],True)
            await self.page.locator('[data-ba-action="confirm"][data-id="'+card+'"]').click()
            await self.wait_state('(id)=>businessAssistantState.session?.proposals?.some(c=>c.id===id&&c.status==="succeeded")',arg=card,timeout=15000)
        await confirm_notice(0)
        current=await detail();self.assertIs(current['business_facts']['facts']['sales.active_quote_consented'],True)
        self.assertIsNot(current['business_facts']['facts']['sales.delivery_recorded'],True)
        # Upload alone proves neither signature acceptance nor actual handover.
        await signed_file('handover')
        current=await detail();self.assertIsNot(current['business_facts']['facts']['sales.delivery_recorded'],True)
        await action('receive',{'amount':'1000.00','account_id':account,'reference':'fixture_'+uuid4().hex,
            'evidence_id':await upload('receipt')})
        await action('inspect',{'outcome':'合格','evidence_id':await upload('inspection'),'result':'合成逐项检查合格'})
        await action('dispatch',{'evidence_id':await upload('evidence')})
        await confirm_notice(1)
        current=await detail();self.assertEqual(current['state'],'delivered')
        self.assertIs(current['business_facts']['facts']['sales.delivery_recorded'],True)
        await self.wait_browser_db('select status from business_assistant_work_plans where id=?',(pid,),lambda r:r and r[0][0]=='completed',timeout=70)
        self.assertEqual(len([r for r in self.posts() if r['path'].endswith('/followup')]),1)
        self.assertEqual(len([r for r in self.posts() if r['path'].endswith('/confirm')]),2)
        self.assertEqual(len([r for r in self.posts() if r['path'].endswith('/runs')]),1)
        await self.page.locator('[data-baw-action="refresh"]').click()
        await self.wait_state('AssistantWorkspace.snapshot().plan?.status==="completed"')
        self.assertEqual(await self.page.locator('#business-assistant-input').input_value(),'保留销售跟进草稿')

    async def test_14_sidebar_retry_keeps_known_work_and_unsent_draft(self):
        """HTTP read failure is not an empty queue and never resends business work."""
        import httpx
        await self.wait_state('!AssistantWorkspace.snapshot().loading && !!AssistantWorkspace.snapshot().counts')
        before = await self.page.locator('#ba-sidebar-root .ba-side-group').all_text_contents()
        before_posts = len(self.posts())
        workspace_path = '/api/business-assistant/workspace'
        original_request = self.h.http.request

        async def unavailable(route):
            await route.fulfill(status=503, content_type='application/json',
                                body=json.dumps({'detail':'合成暂时读取失败'}))

        async def fixture_request(method, url, **kwargs):
            if method == 'GET' and str(url).split('?')[0] == workspace_path:
                return httpx.Response(503, json={'detail':'合成暂时读取失败'})
            return await original_request(method, url, **kwargs)

        if self.h.mode == 'native':
            await self.page.route('**/api/business-assistant/workspace*', unavailable)
        else:
            self.h.http.request = fixture_request
        try:
            await self.page.locator('[data-ba-action="refresh"]').click()
            await self.page.locator('#ba-sidebar-root .ba-side-error').wait_for()
            self.assertEqual(await self.page.locator('#ba-sidebar-root .ba-side-group').all_text_contents(), before)
            self.assertNotIn('这不是空列表', await self.page.locator('#ba-sidebar-root').inner_text())
        finally:
            if self.h.mode == 'native':
                await self.page.unroute('**/api/business-assistant/workspace*', unavailable)
            else:
                self.h.http.request = original_request
        draft = '保留侧栏重试草稿'
        await self.page.locator('#business-assistant-input').fill(draft)
        await self.page.locator('[data-baws-action="retry-sidebar"]').click()
        await self.wait_state('!AssistantWorkspace.snapshot().loading && !AssistantWorkspace.snapshot().error')
        self.assertEqual(await self.page.locator('#business-assistant-input').input_value(), draft)
        self.assertEqual(await self.page.locator('#ba-sidebar-root .ba-side-group').all_text_contents(), before)
        self.assertEqual(len(self.posts()), before_posts)
        statuses = [r['status'] for r in self.h.requests if r['method'] == 'GET' and r['path'].split('?')[0] == workspace_path]
        self.assertIn(503, statuses)
        self.assertEqual(statuses[-1], 200)

if __name__=='__main__':unittest.main()
