"""Actual employee Chrome and SSE, with a scripted provider in a fresh test DB.

The model adapter is synthetic. Original sessions, store checks, proposal gateway
and explicitly confirmed lead creation are real. Never contacts a paid provider.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
from playwright.sync_api import expect,sync_playwright
from tests import browser_huakangos as h
from scripts.capture_workflow_guides import employee,mark_demo


def serve(port,trace):
    assert os.environ.get('APP_ENV')=='test'
    assert 'huakangos-assistant-stream-' in os.environ.get('DATABASE_URL','')
    from app import business_assistant_service as service
    from app import business_assistant_stream as stream
    from app.main import app
    import uvicorn
    service.load_config=lambda:service.AssistantConfig(True,'synthetic-no-network','scripted-stream-fixture',5,True)
    def forbidden(*args,**kwargs):raise AssertionError('External provider is forbidden')
    service.provider_request=forbidden
    service.model_reply=forbidden

    async def reply(config,messages,thinking,emit):
        content=next(m['content'] for m in reversed(messages) if m['role']=='user')
        with Path(trace).open('a',encoding='utf-8') as log:log.write(json.dumps({'content':content,'thinking':thinking,'tool_round':messages[-1]['role']=='tool'},ensure_ascii=False)+'\n')
        if '停止' in content or '换店' in content:
            await emit('delta',{'text':'这是一段尚未完成的合成回复。'})
            await asyncio.sleep(8)
            return {'role':'assistant','content':'不应在停止或换店后出现的正文'}
        if '失败' in content:
            await emit('delta',{'text':'连接中断前的合成正文。'})
            await asyncio.sleep(.7)
            raise httpx.ReadError('synthetic upstream disconnect')
        if thinking and messages[-1]['role']!='tool':
            await asyncio.sleep(1.5)
            await emit('status',{'phase':'responding'})
            await emit('delta',{'text':'已核对合成资料，正在准备接待表单。'})
            await asyncio.sleep(.8)
            return {'role':'assistant','content':'已核对合成资料，正在准备接待表单。','reasoning_content':'PRIVATE_SYNTHETIC_REASONING_NEVER_SHOW',
                'tool_calls':[{'id':'synthetic-lead','type':'function','function':{'name':'prepare_operation','arguments':json.dumps({'operation_id':'POST /api/flow/cases','summary':'登记流式合成客户','body':{'kind':'lead','values':{'customer_name':'流式合成客户','customer_phone':'13900009991','source':'展厅到店'}}},ensure_ascii=False)}}]}
        if messages[-1]['role']=='tool':
            await emit('status',{'phase':'responding'})
            await emit('delta',{'text':'请核对下方表单。'})
            await asyncio.sleep(1)
            return {'role':'assistant','content':'请核对下方表单。点击确认后才会登记。','reasoning_content':'PRIVATE_SYNTHETIC_REASONING_NEVER_SHOW'}
        await emit('status',{'phase':'responding'})
        await emit('delta',{'text':'合成中文第一段😀。'})
        await asyncio.sleep(1.5)
        await emit('delta',{'text':'第二段<img src=x onerror=alert(1)>。'})
        await asyncio.sleep(.5)
        return {'role':'assistant','content':'合成中文第一段😀。第二段<img src=x onerror=alert(1)>。'}
    stream.model_reply_stream=reply
    uvicorn.run(app,host='127.0.0.1',port=port,log_level='warning')


def exercise(browser,base,password,output,work):
    admin_context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN')
    admin=admin_context.new_page();context=None;errors=[];steps=[];screenshots=[];requests=[];confirmations=[]
    try:
        h.login_page(admin,base,'admin',password)
        second=h.checked_request(admin,'/api/stores','POST',{'name':'流式合成二店','code':'STREAM-2'},status=201)
        context,page=employee(browser,admin,base,'sales',errors,viewport={'width':390,'height':844},store_ids=(1,second['id']))
        page.on('request',lambda request:requests.append(request.post_data_json) if request.method=='POST' and urlsplit(request.url).path.endswith('/messages/stream') else None)
        page.on('request',lambda request:confirmations.append(request.post_data_json) if request.method=='POST' and urlsplit(request.url).path.endswith('/confirm') else None)
        h.navigate(page,'business-assistant','业务助手');mark_demo(page,'sales')
        toggle=page.locator('[data-ba-action=thinking]');send=page.locator('#business-assistant-form button[type=submit]');draft=page.locator('#business-assistant-input');log=page.locator('#business-assistant-messages')
        def shot(name):
            h.assert_fits_mobile(page);page.screenshot(path=str(output/name),full_page=False);screenshots.append(str(output/name))
        def submit(text):draft.fill(text);send.click()
        def complete():expect(page.locator('[data-ba-action=stop]')).to_have_count(0,timeout=15000)
        def refresh():page.locator('[data-ba-action=refresh]').click();expect(send).to_have_text('发送',timeout=10000)
        def count():return h.checked_request(admin,'/api/flow/cases?kind=lead')['total']
        before=count()
        expect(toggle).to_have_attribute('aria-checked','false')
        submit('普通模式合成问答')
        expect(log).to_contain_text('合成中文第一段😀。')
        expect(page.locator('[data-ba-action=stop]')).to_be_visible()
        expect(log).not_to_contain_text('第二段')
        expect(log).to_contain_text('普通模式合成问答')
        shot('01_mobile_streaming.png');complete()
        expect(log).to_contain_text('第二段<img');expect(log.locator('img')).to_have_count(0)
        assert requests[0]['thinking'] is False and len(requests)==1
        steps.append('默认关闭思考；真实HTTP SSE分段到达，完成前已显示用户消息和第一段中文/表情；正文HTML不执行。')

        toggle.click();expect(toggle).to_have_attribute('aria-checked','true')
        submit('启用思考登记流式合成客户')
        expect(page.locator('.ba-working')).to_have_text('正在思考…')
        expect(page.locator('.ba-working')).to_be_in_viewport()
        expect(toggle).to_be_disabled();expect(page.locator('.ba-proposal')).to_have_count(0)
        shot('02_mobile_thinking.png')
        expect(log).to_contain_text('请核对下方表单。',timeout=10000)
        expect(page.locator('.ba-proposal')).to_have_count(0)
        complete();expect(page.locator('.ba-proposal')).to_contain_text('流式合成客户')
        expect(log).not_to_contain_text('PRIVATE_SYNTHETIC_REASONING_NEVER_SHOW')
        assert requests[1]['thinking'] is True and count()==before and not confirmations
        page.locator('[data-ba-action=confirm]').scroll_into_view_if_needed();shot('03_mobile_confirm.png')
        page.locator('[data-ba-action=confirm]').click();expect(page.locator('.ba-proposal')).to_contain_text('已完成',timeout=10000)
        assert len(confirmations)==1 and count()==before+1
        steps.append('明确开启思考只显示状态，不展示内部推理；正式done后出现确认卡，员工点击前0新增，点击后原API恰新增1笔接待。')

        page.locator('[data-ba-action=new]').click();expect(toggle).to_have_attribute('aria-checked','false')
        toggle.click();submit('停止这次合成回复')
        expect(log).to_contain_text('尚未完成的合成回复')
        page.locator('[data-ba-action=stop]').click();expect(page.locator('#business-assistant-error')).to_contain_text('已停止等待')
        expect(draft).to_have_value('停止这次合成回复');expect(toggle).to_be_disabled();expect(send).to_be_disabled()
        assert len(requests)==3
        # Refresh retrieves the persisted stop result, without sending again.
        page.wait_for_timeout(300);refresh()
        expect(log).to_contain_text('已停止本次回复');expect(draft).to_have_value('');expect(toggle).to_be_enabled()
        assert len(requests)==3
        steps.append('停止等待取消真实上游，保留输入并锁定模式；刷新读取停止记录和空闲状态，不自动重发。')

        submit('模拟失败连接')
        expect(log).to_contain_text('连接中断前');complete()
        expect(page.locator('#business-assistant-error')).not_to_be_empty()
        expect(send).to_be_disabled();expect(draft).to_have_value('模拟失败连接')
        refresh();assert len(requests)==4;expect(log).not_to_contain_text('PRIVATE_SYNTHETIC_REASONING_NEVER_SHOW')
        steps.append('模型连接失败保留草稿及正式错误结果，要求刷新核对；没有转非流式接口或自动重发。')

        page.locator('[data-ba-action=new]').click()
        def drop_done(route):
            # The actual service completes and persists, but the browser loses
            # the final event. This is a simulated transport fault, not a model.
            response=route.fetch()
            raw=response.text()
            assert 'event: done\n' in raw
            route.fulfill(response=response,body=raw.split('event: done\n')[0])
        page.route('**/api/business-assistant/sessions/*/messages/stream',drop_done,times=1)
        submit('最终事件丢失后核对')
        complete();expect(page.locator('#business-assistant-error')).to_contain_text('连接中断')
        expect(draft).to_have_value('最终事件丢失后核对');expect(toggle).to_be_disabled()
        assert len(requests)==5
        refresh();expect(draft).to_have_value('');expect(log).to_contain_text('合成中文第一段')
        assert len(requests)==5 and count()==before+1
        steps.append('模拟丢失最终事件：服务端已完成，界面保留草稿；刷新按同一请求读取既有结果，没有重发或新建第二张单。')

        submit('换店时隔离合成回复')
        expect(log).to_contain_text('尚未完成的合成回复')
        page.locator('#store').select_option(str(second['id']));expect(page.locator('#main h1')).to_have_text('我的工作')
        h.navigate(page,'business-assistant','业务助手');expect(toggle).to_have_attribute('aria-checked','false');expect(draft).to_have_value('')
        expect(log).not_to_contain_text('换店');expect(log).not_to_contain_text('不应在停止')
        assert len(requests)==6 and count()==before+1
        steps.append('回复期间切换门店取消连接，清空对话、输入和思考开关；旧回复不进入新店。')
        page.set_viewport_size({'width':1440,'height':1000});shot('04_desktop_compose.png')
        assert not errors,errors
        trace=[json.loads(line) for line in (work/'model-trace.jsonl').read_text(encoding='utf-8').splitlines()]
        (output/'scripted-model-trace.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2),encoding='utf-8')
        return {'status':'passed','synthetic_only':True,'steps':steps,'screenshots':screenshots,'employee_role':'sales','javascript_errors':errors,'stream_requests':requests,'confirmed_lead_increase':1,'confirm_requests':len(confirmations),'external_model_requests':0,'scripted_model_calls':len(trace),'limitations':['合成模型回复，不证明真实DeepSeek输出质量。','独立本机HTTP及合成业务，不替代生产HTTPS或公司验收。']}
    except Exception as error:
        if context:page.screenshot(path=str(output/'failure.png'),full_page=True)
        (output/'failure.json').write_text(json.dumps({'error':str(error),'steps':steps,'javascript_errors':errors,'requests':requests},ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    finally:
        if context:context.close()
        admin_context.close()


def main():
    sys.stdout.reconfigure(encoding='utf-8');parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--screenshots',type=Path,required=True);args=parser.parse_args()
    executable=h.chromium_path()
    if not executable:raise SystemExit('需要已安装Chrome/Edge。')
    output=args.screenshots.resolve()
    if output==ROOT or ROOT in output.parents:raise SystemExit('证据必须在源码外。')
    output.mkdir(parents=True,exist_ok=True);(output/'acceptance.json').unlink(missing_ok=True)
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    with tempfile.TemporaryDirectory(prefix='huakangos-assistant-stream-') as name:
        work=Path(name)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}';password=secrets.token_urlsafe(28);env=h.browser_environment(work,password);env.update(BUSINESS_ASSISTANT_CONFIG='',PYTHONDONTWRITEBYTECODE='1')
        initialized=subprocess.run([sys.executable,'-m','app.cli','init'],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',creationflags=flags)
        if initialized.returncode:raise RuntimeError(initialized.stderr)
        with (work/'server.log').open('w',encoding='utf-8') as log:
            server=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve',str(port),str(work/'model-trace.jsonl')],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=flags)
            try:
                with httpx.Client(base_url=base,timeout=2,trust_env=False) as client:
                    for _ in range(150):
                        if server.poll() is not None:raise RuntimeError((work/'server.log').read_text(encoding='utf-8'))
                        try:
                            if client.get('/api/health').status_code==200:break
                        except httpx.HTTPError:pass
                        time.sleep(.1)
                    else:raise RuntimeError('隔离服务未启动')
                with sync_playwright() as p:
                    browser=p.chromium.launch(executable_path=executable,headless=True)
                    try:
                        result=exercise(browser,base,password,output,work);(output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
                    finally:browser.close()
            finally:
                if os.name=='nt' and server.poll() is None:subprocess.run(['taskkill','/PID',str(server.pid),'/T','/F'],capture_output=True,creationflags=flags)
                elif server.poll() is None:server.terminate()
                server.wait(timeout=10)
                (output/'server.log').write_text((work/'server.log').read_text(encoding='utf-8'),encoding='utf-8')


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--serve':serve(int(sys.argv[2]),sys.argv[3])
    else:main()
