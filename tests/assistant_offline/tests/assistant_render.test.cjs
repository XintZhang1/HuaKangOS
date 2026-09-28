'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(process.env.HUAKANGOS_SOURCE||'/mnt/data/HuaKangOS','web/businessassistant.js'),'utf8');
function setup(){
 const box={console,AbortController,Set,Map,document:{addEventListener(){}},storeContextVersion:1,
  state:{user:{id:1,role:'sales'},store:1,route:'business-assistant',storeSwitch:false},
  E:v=>String(v??''),heading:()=>'',time:()=>'',fetch:async()=>({ok:true,json:async()=>({workflows:[]})})};
 vm.createContext(box);vm.runInContext(source,box);
 vm.runInContext('businessAssistantState.context=businessAssistantContext();businessAssistantState.status={ready:true}',box);
 return {box,run:code=>vm.runInContext(code,box)};
}
test('welcome renderer returns an array synchronously without fetching',()=>{
 const h=setup();let calls=0;h.box.fetch=async()=>{calls++;throw Error('unavailable')};
 assert.ok(Array.isArray(h.run('businessAssistantWelcomeExamples()')));
 assert.equal(calls,0);assert.doesNotThrow(()=>h.run('businessAssistantMessages()'));
});
test('composer returns real HTML rather than a Promise',()=>{
 const h=setup(),result=h.run('businessAssistantCompose()');
 assert.equal(typeof result,'string');assert.match(result,/id="business-assistant-input"/);
 assert.doesNotMatch(h.run('businessAssistantHTML()'),/\[object Promise\]/);
});
test('welcome catalogue is deduplicated and read-only fallback survives a fetch failure',async()=>{
 const h=setup();let calls=0;h.box.loadWorkflowGuides=async()=>{calls++;throw Error('offline')};
 await Promise.all([h.run('businessAssistantLoadWelcomeExamples()'),h.run('businessAssistantLoadWelcomeExamples()')]);
 assert.equal(calls,1);assert.equal(h.run('businessAssistantWelcomeExamples().length'),4);
});
test('welcome catalogue retains role permission filtering and maximum four',async()=>{
 const h=setup();h.box.WorkflowGuides={canEnter:x=>x.id!=='denied',assistantPrompt:x=>x.assistant.prompt};
 h.box.loadWorkflowGuides=async()=>({workflows:[{id:'denied',assistant:{prompt:'not allowed',intent:'prepare_action'}},...Array.from({length:8},(_,i)=>({id:'a'+i,title:'t'+i,assistant:{prompt:'p'+i,intent:'query_status'}}))]});
 await h.run('businessAssistantLoadWelcomeExamples()');
 const result=h.run('businessAssistantWelcomeExamples()');assert.equal(result.length,4);assert.equal(result[0][0],'t0');
});
test('late welcome catalogue does not overwrite a replacement store context',async()=>{
 const h=setup();let resolve;h.box.loadWorkflowGuides=()=>new Promise(r=>resolve=r);
 const pending=h.run('businessAssistantLoadWelcomeExamples()');
 h.run('businessAssistantState=freshBusinessAssistantState();state.store=2;businessAssistantState.context=businessAssistantContext()');
 resolve({workflows:[{id:'old',assistant:{prompt:'old-store'}}]});await pending;
 assert.equal(h.run('businessAssistantState.welcomeExamples'),undefined);
});
test('a fresh completed conversation never restores cached pre-confirmation cards',async()=>{
 const h=setup();let subscriptions=0;
 h.box.AssistantRuntime={subscribeRun(){subscriptions++;return ()=>{};}};
 h.run('businessAssistantState.session={id:"s",last_request:{run_id:"r",status:"completed"},proposals:[{id:"p",status:"succeeded"}]}');
 await h.run('businessAssistantResumeRuntimeRun()');assert.equal(subscriptions,0);
 assert.equal(h.run('businessAssistantState.session.proposals[0].status'),'succeeded');
});
test('a failed feature lookup cannot fall back to a second execution protocol',async()=>{
 const h=setup();let legacy=0,runtime=0;h.box.paintBusinessAssistant=()=>{};
 h.box.businessAssistantRequest=async()=>{throw Error('network')};
 h.box.businessAssistantSendLegacy=async()=>legacy++;h.box.businessAssistantSendRuntime=async()=>runtime++;
 h.run('businessAssistantState.draft="查询资料"');await h.run('businessAssistantSend()');
 assert.equal(legacy,0);assert.equal(runtime,0);assert.equal(h.run('businessAssistantState.draft'),'查询资料');
 assert.ok(h.run('businessAssistantState.error'));
});
test('an explicit runtime-disabled feature contract still uses the legacy path',async()=>{
 const h=setup();let legacy=0;h.box.businessAssistantSendLegacy=async()=>legacy++;
 h.run('businessAssistantState.runtimeFeatures={runtime:false};businessAssistantState.draft="查询资料"');
 await h.run('businessAssistantSend()');assert.equal(legacy,1);
});
test('a late feature lookup cannot send an old draft under a new store',async()=>{
 const h=setup();let resolve,calls=0;h.box.businessAssistantRequest=()=>new Promise(r=>resolve=r);
 h.box.businessAssistantSendRuntime=async()=>calls++;h.run('businessAssistantState.draft="旧门店资料"');
 const pending=h.run('businessAssistantSend()');
 h.run('businessAssistantState=freshBusinessAssistantState();state.store=2;businessAssistantState.context=businessAssistantContext()');
 resolve({features:{runtime:true}});await pending;assert.equal(calls,0);
});
test('a completed run found during a page refresh clears stale running UI without a replay',async()=>{
 const h=setup();h.box.paintBusinessAssistant=()=>{};let reads=0;
 h.box.AssistantRuntime={getRun:async()=>{reads++;return {id:'r',status:'succeeded',version:8}}};
 h.run('businessAssistantState.runId="r";businessAssistantState.session={id:"s",last_request:{run_id:"r",status:"completed"}}');
 await h.run('businessAssistantResumeRuntimeRun()');assert.equal(reads,1);assert.equal(h.run('businessAssistantState.runId'),null);
 assert.equal(h.run('businessAssistantState.runStop'),'本次准备已完成');
});
test('an accepted run is watched even when the user has left the assistant page',async()=>{
 const h=setup();h.box.paintBusinessAssistant=()=>{};h.box.toast=()=>{};h.box.requestKey=()=> 'offline-request-0123456789';
 h.box.businessAssistantRequest=async()=>({id:'s',messages:[],proposals:[],last_request:null});
 let resolve,watched=0;h.box.AssistantRuntime={submitRun:()=>new Promise(r=>resolve=r),subscribeRun(){watched++;return ()=>{};},disposeContext(){}};
 const pending=h.run('businessAssistantSendRuntime("查询本店")');
 await new Promise(setImmediate);h.box.state.route='work';resolve({id:'r',session_id:'s',status:'queued',version:1});await pending;
 assert.equal(watched,1);assert.equal(h.run('businessAssistantState.runId'),'r');
});

test('authenticated status features do not depend on a busy workspace projection',async()=>{
 const h=setup();h.run('businessAssistantState.status.features={home:true,runtime:true,followup:true,notifications:true};businessAssistantState.draft="查询本店"');
 let reads=0,sends=0;h.box.businessAssistantRequest=async()=>{reads++;throw Object.assign(Error('workspace changed'),{status:409})};
 h.box.businessAssistantSendRuntime=async()=>sends++;
 await h.run('businessAssistantSend()');assert.equal(reads,0);assert.equal(sends,1);
});
