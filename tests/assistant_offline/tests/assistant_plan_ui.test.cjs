'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const ROOT=process.env.HUAKANGOS_SOURCE||'/mnt/data/HuaKangOS';
function setup(){
 const box={console,AbortController,Set,Map,setTimeout,clearTimeout,storeContextVersion:1,
  document:{addEventListener(){},removeEventListener(){},getElementById(){return null},querySelector(){return null}},
  state:{user:{id:1,role:'sales'},store:1,route:'business-assistant',storeSwitch:false},
  E:v=>String(v??''),heading:()=>'',time:()=>'',toast(){},$:()=>null};
 vm.createContext(box);
 for(const file of ['businessassistant.js','businessassistantwork.js','assistantworkspace.js'])
  vm.runInContext(fs.readFileSync(path.join(ROOT,'web',file),'utf8'),box);
 const run=s=>vm.runInContext(s,box);
 run('businessAssistantState.context=businessAssistantContext();businessAssistantState.status={ready:true};businessAssistantState.session={id:"s",messages:[],proposals:[],work_plans:[]}');
 box.paintBusinessAssistant=()=>{};
 box.businessAssistantRequest=async p=>{throw Error('Unexpected request '+p)};
 return {box,run,ws:box.AssistantWorkspace};
}
const plan=id=>({id,status:'active',version:1,goal:'事项',allowed_actions:['enable'],grant:{enabled:false},steps:[]});
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};}
async function enabled(h){h.box.businessAssistantRequest=async()=>({features:{runtime:true,followup:true,notifications:false},groups:[]});await h.ws.load();}

test('new plan work-status refresh also loads its PlanView without an explicit selection',async()=>{
 const h=setup(),calls=[];h.run('businessAssistantState.session.work_plans=[{id:"p"}]');
 h.box.businessAssistantRequest=async p=>{calls.push(p);return p.includes('work-status')?{plan:{id:'p'},plans:[]}:plan('p')};
 await h.run('businessAssistantRefreshWork()');assert.equal(h.ws.snapshot().plan?.id,'p');assert.ok(calls.includes('/plans/p'));
});
test('a no-plan conversation clears old followup controls',async()=>{
 const h=setup();h.box.businessAssistantRequest=async()=>plan('old');await h.ws.loadPlan('old');
 await h.run('businessAssistantRefreshWork()');assert.equal(h.ws.snapshot().plan,null);
});
test('new matter immediately clears the previous plan controls',async()=>{
 const h=setup();h.box.businessAssistantRequest=async()=>plan('old');await h.ws.loadPlan('old');
 await h.run('businessAssistantNewMatter()');assert.equal(h.ws.snapshot().plan,null);
});
test('terminal run session triggers a readonly plan refresh',async()=>{
 const h=setup();let callback,refreshes=0;h.box.AssistantRuntime={subscribeRun(id,fn){callback=fn;return()=>{}}};
 h.box.businessAssistantRefreshWork=async()=>{refreshes++};h.run('businessAssistantWatchRuntimeRun("r")');
 callback({type:'view',view:{id:'r',status:'succeeded'},session:{id:'s',messages:[],proposals:[],work_plans:[{id:'p'}]}});
 await new Promise(setImmediate);assert.equal(refreshes,1);
});
for(const kind of ['loadPlan','load','loadNotifications']){
 test(kind+' cannot apply a prior context response with a reused serial',async()=>{
  const h=setup(),d=deferred();h.box.businessAssistantRequest=()=>d.promise;
  const old=kind==='loadPlan'?h.ws.loadPlan('old'):kind==='loadNotifications'?h.ws.loadNotifications({force:true}):h.ws.load();
  h.ws.disposeContext();h.box.state.store=2;
  h.box.businessAssistantRequest=async()=>kind==='loadPlan'?plan('new'):kind==='loadNotifications'?{items:[{id:'new'}],unread_count:1}:{groups:[{key:'following',items:[{key:'new'}]}],counts:{native_tasks:1}};
  await (kind==='loadPlan'?h.ws.loadPlan('new'):kind==='loadNotifications'?h.ws.loadNotifications({force:true}):h.ws.load());
  d.resolve(kind==='loadPlan'?plan('old'):kind==='loadNotifications'?{items:[{id:'old'}],unread_count:99}:{groups:[],counts:{native_tasks:99}});await old;
  const snap=h.ws.snapshot();if(kind==='loadPlan')assert.equal(snap.plan.id,'new');else if(kind==='loadNotifications')assert.equal(snap.noticeUnread,1);else assert.equal(snap.counts.native_tasks,1);
 });
}
test('duplicate followup click performs one POST and does not repeat authorization',async()=>{
 const h=setup();await enabled(h);h.box.businessAssistantRequest=async()=>plan('p');await h.ws.loadPlan('p');
 let posts=0;const d=deferred();h.box.businessAssistantRequest=()=>{posts++;return d.promise};
 const first=h.ws.setFollowup('enable'),second=h.ws.setFollowup('enable');
 d.resolve({...plan('p'),version:2,allowed_actions:['pause'],grant:{enabled:true,status:'active'}});
 await Promise.all([first,second]);assert.equal(posts,1);
});
test('same-session notification refreshes cards, retains a draft and only then marks read',async()=>{
 const h=setup(),calls=[];h.run('businessAssistantState.draft="未发草稿";businessAssistantState.answers={old:{a:"保留"}}');
 h.box.businessAssistantRequest=async()=>({items:[{id:'n',status:'unread',session_id:'s'}],unread_count:1});await h.ws.loadNotifications({force:true});
 h.box.businessAssistantRequest=async(p,o)=>{calls.push(p);if(p==='/sessions/s')return {id:'s',messages:[],proposals:[{id:'card',status:'pending'}],work_plans:[]};if(p==='/notifications/n/read')return {id:'n',status:'read'};throw Error(p)};
 assert.equal(await h.ws.openNotification('n'),true);
 assert.deepEqual(calls,['/sessions/s','/notifications/n/read']);assert.equal(h.run('businessAssistantState.session.proposals[0].id'),'card');
 assert.equal(h.run('businessAssistantState.draft'),'未发草稿');assert.equal(h.run('businessAssistantState.answers.old.a'),'保留');
});
test('failed notification target read keeps notification unread',async()=>{
 const h=setup(),calls=[];h.box.businessAssistantRequest=async()=>({items:[{id:'n',status:'unread',session_id:'s'}],unread_count:1});await h.ws.loadNotifications({force:true});
 h.box.businessAssistantRequest=async p=>{calls.push(p);throw Error('offline')};
 assert.equal(await h.ws.openNotification('n'),false);assert.deepEqual(calls,['/sessions/s']);assert.equal(h.ws.snapshot().noticeUnread,1);
});
test('notification cannot abandon a draft to switch to another session',async()=>{
 const h=setup();h.run('businessAssistantState.draft="我的草稿"');h.box.businessAssistantRequest=async()=>({items:[{id:'n',status:'unread',session_id:'other'}],unread_count:1});await h.ws.loadNotifications({force:true});
 let calls=0;h.box.businessAssistantRequest=async()=>{calls++;throw Error('must not request')};
 assert.equal(await h.ws.openNotification('n'),false);assert.equal(calls,0);assert.equal(h.run('businessAssistantState.session.id'),'s');
});
for (const replacement of ['context', 'selection']) {
 test('opening a sidebar item cannot resume after another '+replacement,async()=>{
  const h=setup(),items=[{key:'a',kind:'plan',plan_id:'p-a',session_id:'s-a'},
   {key:'b',kind:'plan',plan_id:'p-b',session_id:'s-b'}];
  h.box.businessAssistantRequest=async()=>({groups:[{key:'following',items}]});await h.ws.load();
  const d=deferred(),chosen=[];
  h.box.businessAssistantChooseSession=async id=>{chosen.push(id);return true};
  h.box.businessAssistantRefreshWork=async()=>{};
  h.box.businessAssistantRequest=p=>p==='/plans/p-a'?d.promise:Promise.resolve(plan('p-b'));
  const opening=h.ws.openItem('a');
  if(replacement==='context'){h.ws.disposeContext();h.box.state.store=2;}
  else await h.ws.openItem('b');
  d.resolve(plan('p-a'));assert.equal(await opening,false);
  assert.deepEqual(chosen,replacement==='context'?[]:['s-b']);
 });
}


test('unloaded sidebar does not invent empty groups or zero counts',()=>{
 const h=setup(),html=h.ws.renderSidebar();
 assert.doesNotMatch(html,/ba-side-count|ba-side-empty/);
});
test('initial sidebar loading cannot be presented as no work',async()=>{
 const h=setup(),d=deferred();h.box.businessAssistantRequest=()=>d.promise;
 const loading=h.ws.load();const html=h.ws.renderSidebar();
 assert.match(html,/正在读取/);assert.doesNotMatch(html,/ba-side-count|ba-side-empty/);
 d.resolve({groups:[],counts:{}});await loading;
});
test('initial sidebar failure has an actionable retry instead of a fake empty result',async()=>{
 const h=setup();h.box.businessAssistantRequest=async()=>{throw Error('连接失败')};await h.ws.load();
 const html=h.ws.renderSidebar();assert.match(html,/data-baws-action="retry-sidebar"/);
 assert.doesNotMatch(html,/ba-side-count|ba-side-empty|这不是空列表/);
});
test('sidebar refresh failure preserves previously read work and counts',async()=>{
 const h=setup();h.box.businessAssistantRequest=async()=>({counts:{attention:3,native_tasks:3},
  groups:[{key:'attention',items:[{key:'t',kind:'native_task',title:'仍须处理的原业务',status:'open'}]}]});
 await h.ws.load();h.box.businessAssistantRequest=async()=>{throw Error('暂时不可用')};await h.ws.load();
 const html=h.ws.renderSidebar();assert.match(html,/仍须处理的原业务/);
 assert.match(html,/data-count="attention">3</);assert.match(html,/data-baws-action="retry-sidebar"/);
});
test('only a successfully read empty sidebar shows zero counts',async()=>{
 const h=setup();h.box.businessAssistantRequest=async()=>({counts:{attention:0,following:0,finished:0},
  groups:['attention','following','finished'].map(key=>({key,items:[]}))});await h.ws.load();
 assert.match(h.ws.renderSidebar(),/data-count="attention">0</);
 assert.match(h.ws.renderSidebar(),/当前没有待你处理的事项/);
});

// 等待原因只显示服务器给的固定中文；内部状态机标识不得出现在员工界面上。
const INTERNAL_WAIT_CODES=['employee_continue','native_prerequisite','external_fact',
 'completion_conditions_missing','source_inaccessible','result_unknown'];
function waitItem(extra){
 return {counts:{attention:1,native_tasks:1},groups:[{key:'attention',items:[
  {key:'t',kind:'native_task',title:'仍须处理的原业务',status:'open',...extra}]}]};
}
for(const code of INTERNAL_WAIT_CODES){
 test('sidebar never shows the internal wait code '+code,async()=>{
  const h=setup();h.box.businessAssistantRequest=async()=>waitItem({waiting_reason:code,waiting_label:'等你继续办理'});
  await h.ws.load();const html=h.ws.renderSidebar();
  assert.doesNotMatch(html,new RegExp(code));
  assert.match(html,/等待：等你继续办理/);
 });
}
test('sidebar hides the wait line when the server sends no fixed label',async()=>{
 const h=setup();h.box.businessAssistantRequest=async()=>waitItem({waiting_reason:'employee_continue'});
 await h.ws.load();const html=h.ws.renderSidebar();
 assert.doesNotMatch(html,/等待：/);assert.doesNotMatch(html,/employee_continue/);
});
test('waitingText only returns a server-provided label',()=>{
 const h=setup();
 assert.equal(h.ws.waitingText({waiting_label:'等你继续办理'}),'等你继续办理');
 assert.equal(h.ws.waitingText({waiting_reason:'employee_continue'}),'');
 assert.equal(h.ws.waitingText({waiting_label:null}),'');
 assert.equal(h.ws.waitingText(null),'');
 assert.equal(h.ws.waitingText({waiting_label:7}),'');
});

