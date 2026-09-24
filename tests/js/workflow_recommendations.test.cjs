'use strict';
// Separate local and explicit AI search: fake transport and time, actual application search
// and rendering. No external model, employee records or business API are used.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'../..');
const endpoint='/api/workflow-guides/recommendations';

function guide(id,title,keywords,route){
 return {id,title,category:'演示流程',summary:title+'的人工与助手办理步骤',keywords,roles:['sales'],requirement_ids:['HK-001'],requirements:[{id:'HK-001',title,group:'演示'}],entry:{route,label:'打开'+title,roles:['sales'],mode:'write'},prerequisites:['核对资料'],manual:[{actor:'本人',where:title,action:'核对后办理',expected:'原单保留'}],assistant:{mode:'prepare',prompt:'先问必要资料。',steps:[]},exceptions:[{when:'缺少资料',action:'补齐再办'}],completion:['查看原单'],screenshot:{}};
}
const catalogue=[guide('wf-sale','登记预订合同',['订车','合同'],'sales-quotes'),guide('wf-refund','原款退款',['退钱','退费'],'business-finance')];
const success=(items=[{workflow_id:'wf-refund',title:'服务端名称',summary:'服务端摘要',route:'workflows/wf-refund'}])=>({ok:true,status:200,json:async()=>({items,local_exists:false,source:'deepseek',message:'已找到可参考的操作指引。'})});

function setup(query='不知道这件事去哪里办'){
 const nodes=new Map(),handlers={},requests=[],timers=new Map(),asyncErrors=[];
 let connected=true,now=0,timerId=0;
 class Element{
  constructor(selector=''){this.selector=selector;this.textContent='';this._html='';this.value='';this.attrs={};this.isConnected=true;this.disabled=false;this.open=true;this.handlers={};}
  set innerHTML(value){this._html=value;for(const match of String(value).matchAll(/id="([^"]+)"/g))getNode('#'+match[1]);}
  get innerHTML(){return this._html;}
  querySelector(selector){return getNode(selector);}
  querySelectorAll(){return [];}
  setAttribute(name,value){this.attrs[name]=String(value);}
  removeAttribute(name){delete this.attrs[name];}
  getAttribute(name){return this.attrs[name];}
  addEventListener(name,callback){(this.handlers[name]||=[]).push(callback);}
  focus(){} scrollIntoView(){} setSelectionRange(){} showModal(){this.open=true;}
  close(){this.open=false;}
  remove(){this.isConnected=false;if(this===dialog)connected=false;}
  getBoundingClientRect(){return {left:0,right:800,top:0,bottom:600};}
 }
 function getNode(selector){if(!nodes.has(selector))nodes.set(selector,new Element(selector));return nodes.get(selector);}
 const dialog=getNode('#workflow-search-dialog');
 const document={cookie:'dealer_csrf=synthetic-token',activeElement:null,
  getElementById:id=>id==='workflow-search-dialog'?(connected?dialog:null):getNode('#'+id),
  querySelector:selector=>selector==='#modal[open]'?null:selector==='#workflow-search-dialog'?(connected?dialog:null):getNode(selector),
  querySelectorAll:()=>[],addEventListener:(name,callback)=>(handlers[name]||=[]).push(callback),
  createElement:name=>new Element(name),body:{append(){connected=true;dialog.isConnected=true;}}};
 const c={console,Set,Map,Promise,JSON,Intl,Date,Number,Math,URLSearchParams,FormData,AbortController,document,window:{addEventListener(){}},
  setTimeout:(callback,delay=0)=>{const id=++timerId;timers.set(id,{callback,at:now+delay});return id;},clearTimeout:id=>timers.delete(id),
  fetch:async(url,options={})=>{requests.push({url,options});assert.equal(url,endpoint,'Search must not call an assistant or business endpoint');assert.equal(options.method,'POST');return c.response(url,options);},
  response:()=>success(),catalogue};
 vm.createContext(c);
 const app=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
 vm.runInContext(app.slice(0,app.indexOf('async function api(')),c);
 for(const name of ['businessassistant.js','workflowcontent.js','workflowguides.js'])vm.runInContext(fs.readFileSync(path.join(root,'web',name),'utf8'),c);
 c.run=code=>vm.runInContext(code,c);c.query=query;c.defaultMode=c.run('workflowSearchState.mode');
 c.run("state.user={id:7,role:'sales'};state.store='1';state.storeSwitch=null;state.route='work';workflowCatalogue={schema_version:1,workflows:catalogue};workflowSearchState={context:workflowContext(),query,mode:'normal',index:0,results:[],opener:null,aiStatus:'idle',aiItems:[],aiError:''};businessAssistantState.context=businessAssistantContext();businessAssistantState.draft='不要覆盖的原草稿';businessAssistantState.session={id:81,messages:[{role:'user',content:'旧对话'}],proposals:[{id:9,status:'pending'}]};globalThis.sessionBefore=JSON.stringify(businessAssistantState);go=route=>{globalThis.destination=route};toast=message=>{globalThis.notice=message};");
 c.flush=async()=>{for(let i=0;i<15;i++)await Promise.resolve();};
 c.tick=async ms=>{const end=now+ms;let loops=0;while(true){const next=[...timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;assert(++loops<50,'Recommendation timer keeps rescheduling');const [id,t]=next;timers.delete(id);now=t.at;try{const result=t.callback();if(result&&typeof result.catch==='function')result.catch(error=>asyncErrors.push(error));}catch(error){asyncErrors.push(error);}await c.flush();}now=end;await c.flush();if(asyncErrors.length)throw asyncErrors.shift();};
 c.requests=requests;c.nodes=nodes;c.dialog=dialog;c.isOpen=()=>connected;
 c.ai=()=>JSON.parse(c.run('JSON.stringify(workflowSearchState.aiItems||[])'));
 c.status=()=>c.run('workflowSearchState.aiStatus');
 c.results=()=>JSON.parse(c.run('JSON.stringify(workflowSearchState.results.map(row=>row.id))'));
 c.chooseAI=async(search=true)=>{await c.run(`setWorkflowSearchMode('ai',${search})`);await c.flush();};
 c.open=async()=>{await c.run('closeWorkflowSearch(false);openWorkflowSearch(query)');await c.flush();};
 c.press=async(key,extra={})=>{for(const handler of getNode('input').handlers.keydown||[])await handler({key,preventDefault(){},stopPropagation(){},...extra});await c.flush();};
 c.assertReadOnly=()=>{assert.equal(c.run('JSON.stringify(businessAssistantState)'),c.run('sessionBefore'),'Search must preserve the existing assistant session, proposals and draft');assert.equal(c.destination,undefined,'Recommendation must not navigate or submit a form');for(const request of requests){assert.equal(request.url,endpoint);assert.equal(request.options.method,'POST');}};
 return c;
}


test('search starts in normal mode and opening it never calls the model',async()=>{
 const c=setup();assert.equal(c.defaultMode,'normal');await c.open();assert.equal(c.run('workflowSearchState.mode'),'normal');await c.tick(5000);assert.equal(c.requests.length,0);c.assertReadOnly();
});

test('ordinary search stays local with or without keyword results and rejects model calls',async()=>{
 for(const query of ['订车','不知道这件事去哪里办','','   ','x','a'.repeat(201)]){
  const c=setup(query);c.run('paintWorkflowSearch();changeWorkflowQuery(query)');await c.tick(5000);
  await c.run('recommendWorkflowGuides(false)');await c.run('recommendWorkflowGuides(true)');await c.flush();
  assert.equal(c.requests.length,0,query);assert.equal(c.run('workflowSearchState.mode'),'normal');assert.deepEqual(c.ai(),[]);c.assertReadOnly();
 }
});

test('AI mode does not call the model merely because input changed or painting occurs',async()=>{
 const c=setup();await c.chooseAI(false);c.run("changeWorkflowQuery('车辆之前收的钱如何处理');paintWorkflowSearch()");await c.tick(5000);
 await c.run('recommendWorkflowGuides(false)');await c.flush();assert.equal(c.requests.length,0);assert.equal(c.run('workflowSearchState.mode'),'ai');assert.deepEqual(c.ai(),[]);c.assertReadOnly();
});

test('selecting AI search explicitly submits one manual request even when local matches exist',async()=>{
 const c=setup('订车');await c.chooseAI();assert.equal(c.requests.length,1);
 assert.deepEqual(JSON.parse(c.requests[0].options.body),{query:'订车',trigger:'manual'});assert.equal(c.status(),'done');assert.deepEqual(c.results(),['wf-refund'],'AI results must not be mixed with ordinary keyword matches');
 await c.tick(5000);assert.equal(c.requests.length,1);c.assertReadOnly();
});

test('selecting AI with empty, too short or too long input makes no request',async()=>{
 for(const query of ['', '   ','x','a'.repeat(201)]){
  const c=setup(query);await c.chooseAI();await c.run('recommendWorkflowGuides(true)');await c.tick(5000);assert.equal(c.requests.length,0,query);c.assertReadOnly();
 }
});

test('Enter submits edited AI input only after composition has completed',async()=>{
 const c=setup();await c.open();await c.chooseAI(false);c.run("changeWorkflowQuery('想处理这辆车之前收的钱')");await c.tick(5000);assert.equal(c.requests.length,0);
 await c.press('Enter',{isComposing:true});await c.press('Enter',{keyCode:229});assert.equal(c.requests.length,0);
 await c.press('Enter');assert.equal(c.requests.length,1);assert.deepEqual(JSON.parse(c.requests[0].options.body),{query:'想处理这辆车之前收的钱',trigger:'manual'});assert.equal(c.status(),'done');c.assertReadOnly();
});

test('repeated AI submits while one request is pending send only one request',async()=>{
 const c=setup();await c.chooseAI(false);let resolve;c.response=()=>new Promise(done=>{resolve=done;});
 const pending=c.run('recommendWorkflowGuides(true)');await c.flush();await c.run('recommendWorkflowGuides(true)');await c.tick(2000);
 assert.equal(c.requests.length,1);assert.equal(JSON.parse(c.requests[0].options.body).trigger,'manual');resolve(success());await pending;assert.equal(c.status(),'done');c.assertReadOnly();
});

test('the same context and query reuse completed AI results when selected again',async()=>{
 const c=setup();await c.chooseAI();assert.equal(c.requests.length,1);
 await c.run('recommendWorkflowGuides(true)');await c.run("setWorkflowSearchMode('normal')");assert.deepEqual(c.ai(),[]);await c.chooseAI();await c.tick(1500);
 assert.equal(c.requests.length,1);assert.deepEqual(c.ai().map(x=>x.id),['wf-refund']);c.assertReadOnly();
});

test('editing an AI query clears results and waits for another explicit submit',async()=>{
 const c=setup();await c.chooseAI();assert.equal(c.requests.length,1);
 c.run("changeWorkflowQuery('新的业务问题')");assert.deepEqual(c.ai(),[]);await c.tick(5000);assert.equal(c.requests.length,1);
 await c.run('recommendWorkflowGuides()');assert.equal(c.requests.length,2);assert.deepEqual(c.ai().map(x=>x.id),['wf-refund']);
 c.run("changeWorkflowQuery('合同')");assert.deepEqual(c.ai(),[]);await c.tick(5000);assert.equal(c.requests.length,2);c.assertReadOnly();
});

test('a late result from an old AI query is ignored even if transport ignores abort',async()=>{
 const c=setup();await c.chooseAI(false);let resolve;c.response=()=>new Promise(done=>{resolve=done;});const pending=c.run('recommendWorkflowGuides(true)');await c.flush();assert.equal(c.requests.length,1);
 c.run("changeWorkflowQuery('订车')");assert.equal(c.requests[0].options.signal.aborted,true);resolve(success());await pending;await c.tick(5000);
 assert.equal(c.requests.length,1);assert.deepEqual(c.ai(),[]);assert.notEqual(c.status(),'done');c.assertReadOnly();
});

test('returning to ordinary search aborts AI and restores only the local result list',async()=>{
 const c=setup('订车');await c.chooseAI(false);let resolve;c.response=()=>new Promise(done=>{resolve=done;});const pending=c.run('recommendWorkflowGuides(true)');await c.flush();
 await c.run("setWorkflowSearchMode('normal')");assert.equal(c.requests[0].options.signal.aborted,true);assert.deepEqual(c.ai(),[]);assert.deepEqual(c.results(),['wf-sale']);
 resolve(success());await pending;await c.tick(5000);assert.equal(c.requests.length,1);assert.equal(c.run('workflowSearchState.mode'),'normal');assert.deepEqual(c.ai(),[]);assert.deepEqual(c.results(),['wf-sale']);c.assertReadOnly();
});

test('switching stores rejects late AI results and does not reuse the previous store cache',async()=>{
 const c=setup();await c.chooseAI(false);let resolve;c.response=()=>new Promise(done=>{resolve=done;});const pending=c.run('recommendWorkflowGuides(true)');await c.flush();
 c.run("storeContextVersion++;state.store='2';clearWorkflowContext()");resolve(success());await pending;assert.deepEqual(c.ai(),[]);assert.notEqual(c.status(),'done');assert.equal(c.isOpen(),false);
 assert.equal(c.run('workflowSearchState.mode'),'normal');
 // A separate context cannot borrow a completed or late response from the old store.
 c.document.body.append(c.dialog);c.response=()=>success();c.run("workflowSearchState={context:workflowContext(),query:'不知道这件事去哪里办',mode:'normal',index:0,results:[],opener:null,aiStatus:'idle',aiItems:[],aiError:''}");
 await c.chooseAI();assert.equal(c.requests.length,2);assert.equal(c.status(),'done');
});

test('closing search prevents requests and discards an in-flight AI response',async()=>{
 const idle=setup();await idle.chooseAI(false);idle.run('closeWorkflowSearch(false)');await idle.run('recommendWorkflowGuides(true)');await idle.tick(5000);assert.equal(idle.requests.length,0);
 const c=setup();await c.chooseAI(false);let resolve;c.response=()=>new Promise(done=>{resolve=done;});const pending=c.run('recommendWorkflowGuides(true)');await c.flush();
 c.run('closeWorkflowSearch(false)');assert.equal(c.requests[0].options.signal.aborted,true);resolve(success());await pending;assert.equal(c.isOpen(),false);assert.deepEqual(c.ai(),[]);assert.notEqual(c.status(),'done');c.assertReadOnly();
});

test('logout cancels an in-flight request and prevents new model requests',async()=>{
 const c=setup();await c.chooseAI(false);let resolve;c.response=()=>new Promise(done=>{resolve=done;});const pending=c.run('recommendWorkflowGuides(true)');await c.flush();
 c.run('storeContextVersion++;state.user=null;clearWorkflowContext()');assert.equal(c.requests[0].options.signal.aborted,true);resolve(success());await pending;
 await c.run('recommendWorkflowGuides(true)');await c.tick(5000);assert.equal(c.requests.length,1);assert.deepEqual(c.ai(),[]);assert.equal(c.isOpen(),false);c.assertReadOnly();
});

test('model IDs are resolved through the local catalogue and supplied URLs or markup are discarded',async()=>{
 const c=setup();await c.chooseAI(false);c.response=()=>success([{workflow_id:'wf-refund',title:'<img src=x onerror=attack()>',summary:'REMOTE_CONTENT',route:'https://untrusted.invalid/'},{workflow_id:'wf-invented',route:'users'},{workflow_id:'javascript:attack()'},{workflow_id:'wf-refund',route:'https://duplicate.invalid/'}]);
 await c.run('recommendWorkflowGuides(true)');const items=c.ai();assert.deepEqual(items.map(x=>x.id),['wf-refund']);assert.equal(items[0].title,'原款退款');assert.equal(items[0].entry.route,'business-finance');
 const rendered=[...c.nodes.values()].map(e=>e.innerHTML+' '+e.textContent).join('\n');assert(!rendered.includes('untrusted.invalid'));assert(!rendered.includes('REMOTE_CONTENT'));assert(!rendered.includes('onerror=attack'));c.assertReadOnly();
});

test('a failed AI search can be explicitly retried without modifying business or assistant state',async()=>{
 const c=setup();await c.chooseAI(false);c.response=()=>({ok:false,status:503,json:async()=>({detail:'服务暂不可用，请重试。'})});await c.run('recommendWorkflowGuides(true)');assert.equal(c.status(),'error');assert.match(c.run('workflowSearchState.aiError'),/重试|不可用/);
 c.response=()=>success();await c.run('recommendWorkflowGuides(true)');assert.equal(c.requests.length,2);assert.equal(c.status(),'done');assert.deepEqual(c.ai().map(x=>x.id),['wf-refund']);c.assertReadOnly();
});
