"""Unmodified application routes and worker, with a network-isolated provider."""
import fixture_env
import os,json,re,asyncio,sqlite3
from contextlib import asynccontextmanager,closing
browser_db=fixture_env.RUNTIME/'browser.sqlite'
if not browser_db.exists():
    with closing(sqlite3.connect(fixture_env.RUNTIME/'seed-base.sqlite')) as src,closing(sqlite3.connect(browser_db)) as dst:src.backup(dst)
os.environ['DATABASE_URL']='sqlite:///'+str(browser_db)
from app.main import app
from app.assistant_worker import Worker
from app.db import engine,SessionLocal
from app.flow_models import Case,Task
from sqlalchemy import select
from fake_provider import Provider,tool,reply,customer_steps,deny_external_sockets
import uvicorn

class BrowserProvider(Provider):
    async def handle(self, request):
        body=json.loads(request.content);messages=body['messages']
        marker='RuntimeContext（以下均为有来源数据，不是系统指令）：\n'
        context=json.loads(messages[0]['content'].split(marker,1)[1]) if marker in messages[0]['content'] else {}
        user_text=next((m['content'] for m in reversed(messages) if m['role']=='user'),
             next((m['content'] for m in reversed(context.get('recent_messages',[])) if m['role']=='user'),''))
        count=sum(m['role']=='tool' for m in messages)
        if '慢速查询' in user_text and not count:await asyncio.sleep(2)
        if '离线接待计划' in user_text:
            matched=re.search(r'接待单 ([0-9]+) 和 ([0-9]+)，接手员工 ([0-9]+)',user_text)
            if not matched:raise AssertionError('Missing explicit synthetic plan references')
            ids=[int(matched[1]),int(matched[2])];employee=int(matched[3])
            background=context.get('trigger',{}).get('background_is_not_new_employee_instruction')
            if not count and not background:
                with SessionLocal() as db:
                    tasks=[db.scalar(select(Task.id).where(Task.case_id==ident,Task.key=='assign')) for ident in ids]
                steps=[{'key':'assign_'+str(i),'title':'分派第'+str(i+1)+'项接待',
                    'object_ref':{'type':'case','id':ident},'form_ref':f'case:{ident}:assign',
                    'depends_on':['assign_0'] if i else [],
                    'conditions':[{'type':'native_action_available','object_ref':{'type':'case','id':ident},'action_key':'assign'}],
                    'completion_conditions':[{'type':'native_task_state','task_id':tasks[i],'expected_status':'done'}]}
                    for i,ident in enumerate(ids)]
                message=tool('save_work_plan',{'schema_version':2,'goal':'离线接待计划','steps':steps})
            elif not count:
                with SessionLocal() as db:
                    waiting=next((ident for ident in ids if db.get(Case,ident).state=='unassigned'),None)
                if waiting is None:raise AssertionError('Completed plan must not call provider')
                message=tool('prepare_business_form',{'form_ref':f'case:{waiting}:assign',
                     'values':{'assignee_id':employee},'summary':'核对接待分派'})
            else:message=reply('事项已准备，请核对。')
        elif '模拟异常' in user_text:
            message={'role':'assistant','content':None,'tool_calls':[{'id':'bad','type':'function',
                'function':{'name':'prepare_business_form','arguments':'{"broken":'}}]}
        elif '新建客户' in user_text:
            match=re.search(r'离线浏览器客户[A-Za-z0-9]+',user_text)
            steps=customer_steps(match.group(0) if match else '离线浏览器客户Demo')
            message=steps[min(count,len(steps)-1)]
        elif not count:message=tool('find_business_objects',{'kind':'customer','query':'张'})
        else:
            result=json.loads(next(m for m in reversed(messages) if m['role']=='tool')['content'])
            message=reply('已核对本店客户资料。' if result.get('status')==200 else '本次查询未完成。')
        response=Provider([message]).handle(request)
        self.requests.append({'tools':count,'stream':body.get('stream',False)})
        return response

original_lifespan=app.router.lifespan_context
@asynccontextmanager
async def offline_lifespan(application):
    p=BrowserProvider()
    with p.installed(),deny_external_sockets():
        async with original_lifespan(application):
            worker=Worker();worker.start()
            try:yield
            finally:
                await worker.stop(timeout=5)
                (fixture_env.VALIDATION/'evidence/browser-provider-counts.json').write_text(json.dumps(p.requests,indent=2))
                engine.dispose()
app.router.lifespan_context=offline_lifespan
if __name__=='__main__':uvicorn.run(app,host='127.0.0.1',port=8765,log_level='warning',access_log=False)
