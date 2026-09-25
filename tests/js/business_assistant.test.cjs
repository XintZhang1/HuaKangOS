'use strict';
// Isolated UI/state checks; a real browser remains a separate acceptance step.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};}
function response(value,status=200){let sent=false;return {ok:status<400,status,json:async()=>value,headers:{get:()=> 'text/event-stream'},body:{getReader:()=>({read:async()=>sent?{done:true}:(sent=true,{value:new TextEncoder().encode('event: done\ndata: '+JSON.stringify({session:value})+'\n\n'),done:false}),cancel:async()=>{}})}};}
function sandbox(){
 const calls=[],handlers={},ctx={console,Promise,Intl,Date,Number,Math,JSON,URLSearchParams,FormData,Set,AbortController,DOMException,TextDecoder,setTimeout,clearTimeout,
  document:{cookie:'dealer_csrf=csrf-example',querySelector:()=>null,querySelectorAll:()=>[],addEventListener:(name,fn)=>handlers[name]=fn},window:{addEventListener(){}},
  fetch:async(url,options)=>{calls.push({url,options});return ctx.respond(url,options);}};
 vm.createContext(ctx);
 const app=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
 vm.runInContext(app.slice(0,app.indexOf('async function api(')),ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'web/businessassistant.js'),'utf8'),ctx);
 ctx.run=code=>vm.runInContext(code,ctx);ctx.calls=calls;ctx.handlers=handlers;
 ctx.run("state.user={id:7,role:'sales',display_name:'合成销售'};state.store='1';state.route='business-assistant';state.stores=[{id:1,name:'合成一店'},{id:2,name:'合成二店'}];businessAssistantState.context=businessAssistantContext();businessAssistantState.status={ready:true,limits:{max_message_chars:6000}};paintBusinessAssistant=()=>{};let requestSequence=0;requestKey=()=>`request-${++requestSequence}`;globalThis.s=state;globalThis.a=businessAssistantState;");
 ctx.respond=async()=>response({id:11,messages:[],proposals:[]});
 return ctx;
}
test('model text and proposal fields are escaped and cannot introduce executable links',()=>{
 const c=sandbox();c.run(`businessAssistantState.session={messages:[{role:'assistant',content:'<img src=x onerror=alert(1)>',links:[{label:'恶意',route:'javascript:alert(1)'},{label:'单据',route:'case/42'}]}],proposals:[]};`);
 const html=c.run('businessAssistantMessages()');assert(html.includes('&lt;img'));assert(!html.includes('<img'));assert(!html.includes('javascript:'));assert(html.includes('href="#case/42"'));
 const p=c.run("businessAssistantProposal({id:1,status:'pending',label:'<script>x</script>',summary:'<svg/onload=x>',display_fields:[{label:'客户',value:'<img src=x>'}],digest:'hash'})");
 assert(!p.includes('<script>'));assert(!p.includes('<svg'));assert(!p.includes('<img'));assert(p.includes('确认办理'));assert(p.includes('合成销售'));assert(p.includes('合成一店'));
 assert.equal(c.run("businessAssistantRoute('parameters/../users')"),'');assert.equal(c.run("businessAssistantRoute('https://evil.example')"),'');assert.equal(c.run("businessAssistantRoute('//evil.example')"),'');
});
test('sending twice while pending posts once and preserves text until a result arrives',async()=>{
 const c=sandbox(),gate=deferred();c.run("businessAssistantState.session={id:11,messages:[],proposals:[]};businessAssistantState.draft='登记张先生的接待';");c.respond=()=>gate.promise;
 const first=c.run('businessAssistantSend()');await c.run('businessAssistantSend()');assert.equal(c.calls.length,1);assert.equal(c.a.draft,'登记张先生的接待');assert.equal(c.a.busy,true);
 const options=c.calls[0].options;assert.equal(options.headers['X-Store-ID'],'1');assert.equal(options.headers['X-CSRF-Token'],'csrf-example');assert.equal(options.credentials,'same-origin');assert.equal(JSON.parse(options.body).content,'登记张先生的接待');
 gate.resolve(response({id:11,messages:[{role:'assistant',content:'请补充电话。'}],proposals:[]}));await first;assert.equal(c.a.draft,'');assert.equal(c.a.busy,false);assert.equal(c.a.session.messages[0].content,'请补充电话。');
});
test('aborted or failed send retains draft and reuses request ID for the same retry',async()=>{
 const c=sandbox();c.run("businessAssistantState.session={id:11,messages:[],proposals:[]};businessAssistantState.draft='安排回访';");
 c.respond=(_url,options)=>new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Stopped','AbortError'))));
 const first=c.run('businessAssistantSend()');await tick();c.run('for(const controller of businessAssistantState.controllers)controller.abort()');await first;
 assert.equal(c.a.draft,'安排回访');assert.match(c.a.error,/已停止等待.*核对结果/);const original=JSON.parse(c.calls[0].options.body).request_id;
 await c.run('businessAssistantSend()');assert.equal(c.calls.length,1);c.run('businessAssistantState.needsRefresh=false');
 c.respond=async()=>response({id:11,messages:[],proposals:[]});await c.run('businessAssistantSend()');assert.equal(JSON.parse(c.calls[1].options.body).request_id,original);assert.equal(c.a.retry,null);
});
test('switching stores aborts requests and discards chat, drafts and a late response',async()=>{
 const c=sandbox(),gate=deferred();c.run("businessAssistantState.session={id:11,messages:[{role:'assistant',content:'一店客户'}],proposals:[]};businessAssistantState.draft='一店电话';");c.respond=()=>gate.promise;
 const pending=c.run('businessAssistantSend()');c.run("storeContextVersion++;clearBusinessAssistantSession();state.store='2';globalThis.next=businessAssistantState;");
 assert.equal(c.calls[0].options.signal.aborted,true);gate.resolve(response({id:11,messages:[{role:'assistant',content:'旧店晚到信息'}],proposals:[]}));await pending;
 assert.equal(c.next.session,null);assert.equal(c.next.draft,'');assert.equal(c.next.error,'');assert.equal(c.next.busy,false);
});
test('leaving the assistant discards in-flight updates without changing the next page',async()=>{
 const c=sandbox(),gate=deferred();c.run("businessAssistantState.session={id:11,messages:[],proposals:[]};businessAssistantState.draft='接待';");c.respond=()=>gate.promise;
 const pending=c.run('businessAssistantSend()');c.run("state.route='work';leaveBusinessAssistantView();");gate.resolve(response({id:11,messages:[{role:'assistant',content:'晚到回复'}],proposals:[]}));await pending;
 assert.equal(c.a.session.messages.length,0);assert.equal(c.a.busy,false);assert.equal(c.s.route,'work');
});
test('confirm posts only the server proposal digest and cannot double submit',async()=>{
 const c=sandbox(),gate=deferred();c.run("businessAssistantState.session={id:11,messages:[],proposals:[{id:4,status:'pending',digest:'server-frozen',details:{body:{amount:'100'}}}]};");c.respond=()=>gate.promise;
 const pending=c.run('businessAssistantDecide(4,true)');await c.run('businessAssistantDecide(4,true)');assert.equal(c.calls.length,1);assert.equal(c.calls[0].url,'/api/business-assistant/sessions/11/proposals/4/confirm');assert.deepEqual(JSON.parse(c.calls[0].options.body),{digest:'server-frozen'});
 gate.resolve(response({id:11,messages:[],proposals:[{id:4,status:'confirmed'}]}));await pending;assert.equal(c.a.session.proposals[0].status,'confirmed');
});
test('expired and unconfigured actions remain disabled; amounts and quantities are explicit',()=>{
 const c=sandbox();const html=c.run("businessAssistantProposal({id:2,status:'pending',expires_at:'2000-01-01T00:00:00',details:{body:{amount_cents:12345,quantity_milli:2500}}})");assert.match(html,/data-ba-action="confirm"[^>]*disabled/);assert(html.includes('123.45 元'));assert(html.includes('2.5'));assert(html.includes('已过期'));
 c.run("businessAssistantState.status={ready:false};businessAssistantState.draft='内容';");assert.match(c.run('businessAssistantCompose()'),/type="submit"[^>]*disabled/);
});
test('aggregate store never requests an assistant session or reveals previous contents',async()=>{
 const c=sandbox();c.run("state.store='all';businessAssistantState.session={id:11,messages:[{role:'assistant',content:'某店私有信息'}]};");const html=await c.run('businessAssistantPage()');assert.equal(c.calls.length,0);assert(!html.includes('某店私有信息'));assert(html.includes('具体门店'));
});
test('manual links resolve real pages and do not navigate to domains that require missing IDs',()=>{
 const c=sandbox();
 const cases=[
  [{manual_route:'work',operation_id:'POST /api/flow/master/{kind}',details:{path_args:{kind:'customers'}}},'master/customers'],
  [{manual_route:'work',operation_id:'POST /api/flow/cases/{case_id}/actions/{action}',details:{path_args:{case_id:42}}},'case/42'],
  [{manual_route:'retail-group'},'retail'],
  [{manual_route:'retail-group',operation_id:'POST /api/retail-group/orders/{case_id}/actions/{action}',details:{path_args:{case_id:45}}},'retail-group/45'],
  [{manual_route:'retail-group',operation_id:'POST /api/retail-group/rules'},'retail-group-rules'],
  [{manual_route:'vehicle-transport-exceptions'},'vehicle-transfers'],
  [{manual_route:'inventory-reports',details:{path_args:{kind:'warehouses'}}},'warehouse-period'],
  [{manual_route:'stock-reports'},'stock-period'],
  [{manual_route:'membership',operation_id:'POST /api/membership/orders',result:{data:{id:52},route:'membership'}},'membership-order/52'],
  [{manual_route:'customer-service',operation_id:'POST /api/customer-service/vehicles/{vehicle_id}/observations',details:{path_args:{vehicle_id:19}}},'customer-vehicles/19'],
  [{manual_route:'https://external.example'},''],
 ];
 for(const [proposal,expected] of cases){c.p=proposal;assert.equal(c.run('businessAssistantManualRoute(p)'),expected);}
 const links=c.run("businessAssistantLinks([{route:'case/42',label:'单据'},{route:'case/42',label:'重复'}])");assert.equal((links.match(/href=/g)||[]).length,1);
});
test('a pending card shows the prerequisite facts the system returned, escaped',()=>{
 const c=sandbox();
 const html=c.run("businessAssistantProposal({id:9,status:'pending',label:'新建维修工单',result:{prerequisites:['相关业务：客户到店接待','客户：<img src=x onerror=alert(1)>']},digest:'hash'})");
 assert(html.includes('办理前请先确认'));assert(html.includes('相关业务：客户到店接待'));assert(!html.includes('<img'));
 const settled=c.run("businessAssistantProposal({id:9,status:'succeeded',label:'新建维修工单',result:{prerequisites:['相关业务：客户到店接待']},digest:'hash'})");
 assert(!settled.includes('办理前请先确认'),'a finished card no longer asks for prerequisites');
 const absent=c.run("businessAssistantProposal({id:9,status:'pending',label:'新建资料',result:{},digest:'hash'})");
 assert(!absent.includes('办理前请先确认'));
});
