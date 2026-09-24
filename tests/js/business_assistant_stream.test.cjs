'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..'),tick=()=>new Promise(resolve=>setImmediate(resolve));
const frame=(event,value)=>`event: ${event}\r\ndata: ${JSON.stringify(value)}\r\n\r\n`;
function reader(chunks){let index=0;return {read:async()=>index<chunks.length?{value:chunks[index++],done:false}:{done:true},cancel:async()=>{}};}
function response(text){return {ok:true,headers:{get:()=> 'text/event-stream'},body:{getReader:()=>reader([new TextEncoder().encode(text)])}};}
function setup(){
 const handlers={},calls=[],c={console,Promise,Intl,Date,Number,Math,JSON,URLSearchParams,FormData,Set,AbortController,DOMException,TextDecoder,setTimeout,clearTimeout,
 document:{cookie:'dealer_csrf=example',querySelector:()=>null,querySelectorAll:()=>[],addEventListener:(name,fn)=>handlers[name]=fn},window:{addEventListener(){}},
 fetch:async(url,options)=>{calls.push({url,options});return c.respond(url,options);}};
 vm.createContext(c);const app=fs.readFileSync(path.join(root,'web/app.js'),'utf8');vm.runInContext(app.slice(0,app.indexOf('async function api(')),c);vm.runInContext(fs.readFileSync(path.join(root,'web/businessassistant.js'),'utf8'),c);
 c.run=code=>vm.runInContext(code,c);c.calls=calls;c.handlers=handlers;
 c.run("state.user={id:7,role:'sales'};state.store='1';state.route='business-assistant';state.stores=[{id:1,name:'合成店'}];businessAssistantState.context=businessAssistantContext();businessAssistantState.status={ready:true};businessAssistantState.session={id:11,messages:[],proposals:[]};businessAssistantState.draft='登记合成接待';paintBusinessAssistant=()=>{};paintBusinessAssistantStream=()=>{};requestKey=()=> 'stream-request';globalThis.a=businessAssistantState;");return c;
}
function session(content='正式回复'){return {id:11,messages:[{role:'assistant',content}],proposals:[]};}
test('SSE frames survive every UTF8 byte boundary, CRLF and multiple data lines',async()=>{
 const c=setup(),events=[];c.reader=reader([...new TextEncoder().encode(': heartbeat\r\nevent: delta\r\ndata: {"text":\r\ndata: "中文😀"}\r\n\r\n'+frame('status',{phase:'tool'}))].map(b=>Uint8Array.of(b)));c.collect=(kind,data)=>events.push([kind,JSON.parse(JSON.stringify(data))]);await c.run('businessAssistantReadEvents(reader,collect)');assert.deepEqual(events,[['delta',{text:'中文😀'}],['status',{phase:'tool'}]]);
});
test('thinking is off by default and changes only on explicit switch',async()=>{
 const c=setup();assert.equal(c.a.thinking,false);assert.match(c.run('businessAssistantCompose()'),/role="switch" aria-checked="false"/);
 await c.handlers.click({target:{closest:()=>({dataset:{baAction:'thinking'}})}});assert.equal(c.a.thinking,true);
 c.a.retry={request_id:'x'};await c.handlers.click({target:{closest:()=>({dataset:{baAction:'thinking'}})}});assert.equal(c.a.thinking,true);
});
test('only safe status and content deltas display before done; internal reasoning ignored',async()=>{
 const c=setup(),seen=[];c.paint=()=>seen.push({html:c.run('businessAssistantMessages()'),status:c.run('businessAssistantWorking()')});c.run('paintBusinessAssistantStream=paint');
 c.respond=async()=>response(frame('status',{phase:'thinking',message:'SECRET THOUGHT',reasoning_content:'SECRET'})+frame('reasoning_content',{text:'SECRET'})+frame('delta',{text:'中文<img onerror=x>',reasoning_content:'SECRET'})+frame('done',{session:session('正式完成')}));await c.run('businessAssistantSend()');
 assert.equal(c.calls.length,1);assert.match(c.calls[0].url,/\/messages\/stream$/);assert.equal(JSON.parse(c.calls[0].options.body).thinking,false);assert(seen.some(row=>row.status.includes('正在思考')));assert(seen.some(row=>row.html.includes('中文&lt;img')));assert(seen.every(row=>!row.html.includes('SECRET')&&!row.html.includes('<img')));assert.equal(c.a.session.messages[0].content,'正式完成');assert.equal(c.a.stream,null);assert.equal(c.a.draft,'');
});
test('tool rounds clear temporary prior text; proposal appears only in persisted done snapshot',async()=>{
 const c=setup(),seen=[];c.paint=()=>seen.push(c.run('businessAssistantMessages()'));c.run('paintBusinessAssistantStream=paint');const final=session('请确认');final.proposals=[{id:3,status:'pending',label:'新增客户'}];
 c.respond=async()=>response(frame('status',{phase:'responding',round:1})+frame('delta',{text:'第一轮说明'})+frame('status',{phase:'tool'})+frame('status',{phase:'responding',round:2})+frame('delta',{text:'第二轮正文'})+frame('done',{session:final}));await c.run('businessAssistantSend()');assert(seen.some(html=>html.includes('第一轮说明')));assert(seen.at(-1).includes('第二轮正文'));assert(!seen.at(-1).includes('第一轮说明'));assert(seen.every(html=>!html.includes('确认办理')));assert(c.run('businessAssistantMessages()').includes('确认办理'));
});
test('EOF without done preserves frozen request, draft and thinking; never downgrades/reposts',async()=>{
 const c=setup();c.a.thinking=true;c.respond=async()=>response(frame('delta',{text:'部分回复'}));await c.run('businessAssistantSend()');assert.equal(c.calls.length,1);assert.equal(c.a.needsRefresh,true);assert.equal(c.a.draft,'登记合成接待');assert.equal(c.a.retry.thinking,true);assert.match(c.run('businessAssistantCompose()'),/readonly/);assert.match(c.run('businessAssistantCompose()'),/data-ba-action="thinking"[^>]*disabled/);
 await c.run('businessAssistantSend()');assert.equal(c.calls.length,1);c.a.needsRefresh=false;c.a.thinking=false;c.a.draft='另一个内容';c.respond=async()=>response(frame('done',{session:session()}));await c.run('businessAssistantSend()');assert.deepEqual(JSON.parse(c.calls[1].options.body),JSON.parse(c.calls[0].options.body));assert.equal(c.a.thinking,true);
});
test('explicit stream error plus done keeps official snapshot and requires refresh',async()=>{
 const c=setup();c.respond=async()=>response(frame('error',{message:'回复已停止'})+frame('done',{session:session('停止说明')}));await c.run('businessAssistantSend()');assert.equal(c.a.needsRefresh,true);assert.equal(c.a.session.messages[0].content,'停止说明');assert.equal(c.a.draft,'登记合成接待');assert(c.a.retry);assert.equal(c.a.stream,null);
 c.a.session.last_request={request_id:c.a.retry.request_id,status:'completed'};c.run('businessAssistantReconcileRequest()');assert.equal(c.a.retry,null);assert.equal(c.a.draft,'');
});
test('refresh reconciles only this exact request, never an older reply',()=>{
 const c=setup();c.a.retry={request_id:'new',content:c.a.draft};c.a.session.last_request={request_id:'old',status:'completed'};c.run('businessAssistantReconcileRequest()');assert.equal(c.a.retry.request_id,'new');
 c.a.session.last_request={request_id:'new',status:'processing'};c.run('businessAssistantReconcileRequest()');assert(c.a.retry);c.a.session.last_request.status='interrupted';c.run('businessAssistantReconcileRequest()');assert.equal(c.a.retry,null);assert.match(c.a.error,/核对/);
});
test('store switch during reader wait discards late chunks and resets thinking',async()=>{
 const c=setup();let resolve;c.respond=async()=>({ok:true,headers:{get:()=> 'text/event-stream'},body:{getReader:()=>({read:()=>new Promise(done=>resolve=done),cancel:async()=>{}})}});c.a.thinking=true;const pending=c.run('businessAssistantSend()');await tick();c.run("storeContextVersion++;clearBusinessAssistantSession();state.store='2';globalThis.next=businessAssistantState;");resolve({value:new TextEncoder().encode(frame('delta',{text:'旧店信息'}))});await pending;assert.equal(c.next.stream,null);assert.equal(c.next.thinking,false);assert.equal(c.next.draft,'');assert.equal(c.next.error,'');
});
test('malformed JSON or unexpected content type fails without a nonstream fallback',async()=>{
 for(const payload of ['event: delta\ndata: nope\n\n','event: done\ndata: {"session":{"id":99,"messages":[],"proposals":[]}}\n\n']){const c=setup();c.respond=async()=>response(payload);await c.run('businessAssistantSend()');assert(c.a.needsRefresh);assert.equal(c.calls.length,1);assert(c.a.retry);}
 const c=setup();c.respond=async()=>({ok:true,headers:{get:()=> 'application/json'}});await c.run('businessAssistantSend()');assert(c.a.needsRefresh);assert.equal(c.calls.length,1);
});
