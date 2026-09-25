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
test('leaving the assistant keeps the turn running and records the result for when the employee returns',async()=>{
 const c=sandbox(),gate=deferred();c.run("toast=()=>{};businessAssistantState.session={id:11,messages:[],proposals:[]};businessAssistantState.draft='登记张先生的接待';");c.respond=()=>gate.promise;
 const pending=c.run('businessAssistantSend()');await tick();
 c.run("state.route='work';leaveBusinessAssistantView();");
 assert.equal(c.calls[0].options.signal.aborted,false,'离开页面不再中止这一轮：员工会一边用助手一边办别的事');
 assert.equal(c.a.background,true);
 gate.resolve(response({id:11,messages:[{role:'assistant',content:'接待已登记，待你核对。'}],proposals:[{id:4,status:'pending',digest:'h'}]}));await pending;
 assert.equal(c.a.busy,false);assert.equal(c.a.error,'');
 assert.equal(c.a.session.messages[0].content,'接待已登记，待你核对。','结果在后台收下，回来就能看到');
 assert.equal(c.a.session.proposals.length,1);
 c.run("state.route='business-assistant';");
 assert(c.run('businessAssistantMessages()').includes('接待已登记'),'回到助手页时这一轮的结果还在');
});
test('switching stores still stops the turn and drops the conversation',async()=>{
 const c=sandbox(),gate=deferred();c.run("businessAssistantState.session={id:11,messages:[{role:'assistant',content:'一店客户'}],proposals:[]};businessAssistantState.draft='一店电话';");c.respond=()=>gate.promise;
 const pending=c.run('businessAssistantSend()');c.run("storeContextVersion++;clearBusinessAssistantSession();state.store='2';globalThis.next=businessAssistantState;");
 assert.equal(c.calls[0].options.signal.aborted,true,'换门店必须停下并丢弃（助手按门店隔离）');
 gate.resolve(response({id:11,messages:[{role:'assistant',content:'旧店晚到信息'}],proposals:[]}));await pending;
 assert.equal(c.next.session,null);assert.equal(c.next.draft,'');assert.equal(c.next.error,'');assert.equal(c.next.busy,false);
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
function cards(count,patch={}){
 return JSON.stringify(Array.from({length:count},(_item,index)=>Object.assign({
  id:'card-'+(index+1),turn:'turn-1',status:'pending',label:'新增车型 '+(index+1),summary:'新增车型：第 '+(index+1)+' 行',
  digest:String(index+1).padStart(64,'a'),details:{body:{name:'车型'+(index+1)}}},patch)));
}
test('one turn of many cards is folded into a pager instead of a wall of cards',()=>{
 const c=sandbox();
 c.run("businessAssistantState.session={id:11,messages:[{role:'assistant',content:'本轮共准备 60 张。'}],proposals:"+cards(60)+"};");
 const folded=c.run('businessAssistantCards()');
 assert(folded.includes('60</strong> 张本轮卡片'));assert(folded.includes('>1 / 60<'));
 assert(folded.includes('全部确认（60 张）'));
 assert(folded.includes('ba-cardgroup folded'));
 assert.equal((folded.match(/class="ba-proposal"/g)||[]).length,1,'only the current card is rendered while folded');
 assert(folded.includes('新增车型：第 1 行'));
 c.run('businessAssistantState.cards[businessAssistantCardGroups(businessAssistantState.session.proposals)[0].key]=4;businessAssistantState.folded[businessAssistantCardGroups(businessAssistantState.session.proposals)[0].key]=false;');
 const open=c.run('businessAssistantCards()');
 assert.equal((open.match(/class="ba-proposal"/g)||[]).length,60,'展开全部 shows every card of the turn');
 const other=c.run("businessAssistantState.session.proposals.push({id:'card-x',status:'pending',label:'单人卡',digest:'b'.repeat(64)});businessAssistantCards()");
 assert(other.includes('单人卡'),'a card without a turn still renders on its own');
});
test('one turn of a whole prerequisite chain is grouped by step, in order',()=>{
 const c=sandbox();
 const chain=[{turn:'turn-1',step:'售前接待',step_order:1,id:'a',status:'pending',label:'新建售前接待',digest:'a'.repeat(64)},
              {turn:'turn-1',step:'分派接待回访',step_order:2,id:'b',status:'pending',label:'分派接待回访',digest:'b'.repeat(64)},
              {turn:'turn-1',step:'新建订单',step_order:3,id:'c',status:'pending',label:'新建订单',digest:'c'.repeat(64)},
              {turn:'turn-1',step:'新建订单',step_order:3,id:'d',status:'pending',label:'订单明细',digest:'d'.repeat(64)},
              {turn:'turn-1',step:'生成订单合同',step_order:4,id:'e',status:'pending',label:'生成订单合同',digest:'e'.repeat(64)}];
 c.run("businessAssistantState.session={id:11,messages:[{role:'assistant',content:'一共 4 步，请分组核对。'}],proposals:"+JSON.stringify(chain)+"};");
 const html=c.run('businessAssistantCards()');
 assert(html.includes('1 · 售前接待'));assert(html.includes('2 · 分派接待回访'));assert(html.includes('3 · 新建订单'));assert(html.includes('4 · 生成订单合同'));
 assert(html.indexOf('1 · 售前接待')<html.indexOf('2 · 分派接待回访'),'步骤按顺序排列');
 assert(html.indexOf('2 · 分派接待回访')<html.indexOf('3 · 新建订单'));
 assert.equal((html.match(/class="ba-proposal"/g)||[]).length,4,'每一步只展开当前一张卡：4 步 → 4 张');
 const groups=c.run('businessAssistantCardGroups(businessAssistantState.session.proposals).map(group=>({step:group.step,order:group.order,cards:group.cards.length}))');
 assert.deepEqual(JSON.parse(JSON.stringify(groups)),[{'step':'售前接待','order':1,'cards':1},{'step':'分派接待回访','order':2,'cards':1},{'step':'新建订单','order':3,'cards':2},{'step':'生成订单合同','order':4,'cards':1}],groups);
 const bar=c.run('businessAssistantCardsPanel()');
 assert(bar.includes('按顺序全部确认（5 张）'),'一条链可以一次按顺序办完');
});
test('cards live in their own column so the conversation is never pushed off screen',()=>{
 const c=sandbox();
 c.run("businessAssistantState.session={id:11,messages:[{role:'user',content:'把这张表导进车型目录'},{role:'assistant',content:'本轮共准备 3 张待确认卡。'}],proposals:"+cards(3)+"};");
 const transcript=c.run('businessAssistantMessages()');
 assert(transcript.includes('把这张表导进车型目录'));assert(transcript.includes('本轮共准备 3 张待确认卡'));
 assert(!transcript.includes('class="ba-proposal"'),'the transcript must not carry cards any more');
 assert(!transcript.includes('ba-cardnav'));
 const panel=c.run('businessAssistantCardsPanel()');
 assert(panel.includes('id="business-assistant-cards"'));assert(panel.includes('待确认卡片'));
 assert(panel.includes('>1 / 3<'));assert((panel.match(/class="ba-proposal"/g)||[]).length===1);
 const page=c.run('businessAssistantWorkspace()');
 assert(page.includes('ba-workspace'));assert(page.indexOf('id="business-assistant-cards"')>page.indexOf('id="business-assistant-messages"'),'cards render beside, after the transcript');
 c.run("businessAssistantState.session.proposals=[];businessAssistantCardsPanel()");
 assert(c.run('businessAssistantWorkspace()').includes('ba-workspace no-cards'),'no cards: the conversation takes the full width');
 c.run("businessAssistantState.panelFolded=true;businessAssistantState.session.proposals="+cards(3)+";");
 assert(c.run('businessAssistantCardsPanel()').includes('hidden'),'the panel can be folded away by hand');
});
test('the pager arrows move between this turn\'s cards without touching the server',()=>{
 const c=sandbox(),handler=c.handlers.click;
 c.run("businessAssistantState.session={id:11,messages:[],proposals:"+cards(3)+"};businessAssistantState.folded={};");
 const click=dataset=>({target:{closest:()=>({dataset,disabled:false})}});
 handler(click({baAction:'card-next',key:'turn-1'}));
 assert.equal(c.run('businessAssistantState.cards["turn-1"]'),1);
 assert.equal(c.calls.length,0,'paging is local, it must not call the API');
 handler(click({baAction:'card-prev',key:'turn-1'}));
 assert.equal(c.run('businessAssistantState.cards["turn-1"]'),0);
 handler(click({baAction:'card-fold',key:'turn-1'}));
 assert.equal(c.run('businessAssistantGroupFolded("turn-1")'),false,'折叠是默认，点一下展开全部');
 handler(click({baAction:'card-fold',key:'turn-1'}));
 assert.equal(c.run('businessAssistantGroupFolded("turn-1")'),true,'再点一下收起');
});
test('全部确认 posts one reviewed batch and reports per-card outcomes',async()=>{
 const c=sandbox();
 c.run("toast=()=>{};globalThis.submitBatch=null;modal=(title,body,onSubmit)=>{globalThis.modalTitle=title;globalThis.submitBatch=onSubmit;return{addEventListener(){}};};");
 c.run("businessAssistantState.session={id:11,messages:[],proposals:"+cards(3)+"};");
 c.respond=async()=>({ok:true,status:200,json:async()=>({id:11,messages:[],proposals:JSON.parse(c.run('JSON.stringify(businessAssistantState.session.proposals)')).map(card=>Object.assign({},card,{status:'succeeded'})),batch:{total:3,done:3,items:[{id:'card-1',status:'succeeded'},{id:'card-2',status:'failed',summary:'新增车型 2',message:'已有同名年款，但参数不同，请在车型目录核对'},{id:'card-3',status:'succeeded'}]}}),headers:{get:()=> 'application/json'}});
 const pending=c.run('businessAssistantDecideAll(businessAssistantCardGroups(businessAssistantState.session.proposals)[0].key,true)');
 await tick();
 assert(c.run('globalThis.modalTitle').includes('全部确认'),'the employee confirms the batch explicitly');
 await c.run('globalThis.submitBatch()');
 await pending;
 const call=c.calls.find(item=>item.url.includes('/proposals/batch'));
 assert(call,'one click posts one batch request');
 const body=JSON.parse(call.options.body);
 assert.equal(body.action,'confirm');assert.equal(body.items.length,3);
 assert.deepEqual(body.items.map(item=>item.id),['card-1','card-2','card-3']);
 assert(body.items.every(item=>/^a{64}$|^[a-f0-9]{64}$/.test(item.digest)),'every card keeps its own frozen digest');
 assert(c.run('businessAssistantState.error').includes('未办成的'),'failed cards are reported, not hidden');
 assert(c.run('businessAssistantState.error').includes('参数不同'));
});
test('after a confirmation the page offers 继续处理 for the next round',async()=>{
 const c=sandbox();
 c.run("businessAssistantState.session={id:11,messages:[{role:'assistant',content:'本轮共生成 3 张待确认卡。'}],proposals:"+cards(3,{status:'succeeded'})+"};");
 const settleAll=c.run('businessAssistantNextStep()');
 assert(settleAll==='','nothing pending and nothing asked: no continue bar');
 c.run("businessAssistantState.session.proposals[2].status='pending';");
 const bar=c.run('businessAssistantNextStep()');
 assert(bar.includes('还有 1 张待确认'));assert(bar.includes('data-ba-action="continue"'));
 c.run("businessAssistantState.session.proposals[2].status='succeeded';businessAssistantState.session.messages.push({role:'assistant',content:'还有几行缺少电池容量，补齐后请发送继续。'});");
 assert(c.run('businessAssistantNextStep()').includes('data-ba-action="continue"'),'a turn that stopped mid-way still offers the next round');
 c.run("businessAssistantState.lastAction='confirm';businessAssistantState.session.proposals[0].status='pending';");
 assert(c.run('businessAssistantNextStep()').includes('已办理'),'after a confirmation the bar says what happened and what to do next');
 c.respond=async()=>({ok:true,status:200,json:async()=>({id:11,messages:[],proposals:[]}),headers:{get:()=> 'text/event-stream'},body:{getReader:()=>({read:async()=>({done:true}),cancel:async()=>{}})}});
 const before=c.calls.length;
 await c.run('businessAssistantContinue()');
 const sent=c.calls.slice(before).find(item=>item.url.includes('/messages/stream'));
 assert(sent,'继续处理 sends the next-round message');assert.equal(JSON.parse(sent.options.body).content,'继续处理下一步');
});
