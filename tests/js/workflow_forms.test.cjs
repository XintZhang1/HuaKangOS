'use strict';
// Run the real help entry, static allowlist and render hook with a fake page.
// No API write, employee record, native form submission or external model is used.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'../..');
const catalogue=['business.json','services.json'].flatMap(name=>JSON.parse(fs.readFileSync(path.join(root,'docs/workflow-source',name),'utf8')));
const leadID='wf-reception';

function setup(){
 const handlers={},queries=[],requests=[],navigations=[],notices=[];
 let modal=false,clicks=0,visible=true,present=true,buttonError=null;
 const button={tagName:'BUTTON',type:'button',disabled:false,hidden:false,isConnected:true,
  getClientRects:()=>visible?[{width:120,height:36}]:[],
  click(){assert.equal(c.run('workflowFormIntent'),null,'Clear the intent before opening a native form');clicks++;if(buttonError)throw buttonError;}};
 const main={innerHTML:'',querySelector(selector){queries.push({scope:'main',selector});return present&&selector===c.allowedSelector?button:null;}};
 const document={title:'',cookie:'dealer_csrf=synthetic',
  querySelector(selector){queries.push({scope:'document',selector});if(selector==='#main')return main;if(selector==='#modal[open]')return modal?{}:null;return null;},
  getElementById:()=>null,querySelectorAll:()=>[],addEventListener:(name,callback)=>(handlers[name]||=[]).push(callback)};
 const c={console,Set,Map,Promise,JSON,Intl,Date,Number,Math,URLSearchParams,FormData,AbortController,setTimeout,clearTimeout,
  document,window:{addEventListener(){}},catalogue:structuredClone(catalogue),
  fetch:async(url,options={})=>{requests.push({url,options});assert.equal(url,'/static/workflow-guides.json','Opening help must never call a business or model API');assert.equal(options.method||'GET','GET');return c.transport(url,options);},
  transport:async()=>({ok:true,json:async()=>({schema_version:1,workflows:c.catalogue})})};
 vm.createContext(c);
 const app=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
 vm.runInContext(app.slice(0,app.indexOf('async function api(')),c);
 for(const name of ['businessassistant.js','workflowactions.js','workflowcontent.js','workflowguides.js'])vm.runInContext(fs.readFileSync(path.join(root,'web',name),'utf8'),c);
 // Exercise the production render success and failure paths too, with the page
 // reader stubbed. The form click itself still uses the real help implementation.
 vm.runInContext(app.slice(app.indexOf('async function render(){'),app.indexOf('\nfunction searchBar(')),c);
 c.run=code=>vm.runInContext(code,c);
 c.bindFilters=()=>{};c.casesPage=async()=>'<h1>售前接待</h1>';c.pageCalls=0;
 c.run("state.user={id:7,role:'sales'};state.store='1';state.storeSwitch=null;state.route='workflows/wf-reception';workflowCatalogue={schema_version:1,workflows:catalogue};businessAssistantState.context=businessAssistantContext();businessAssistantState.draft='未发送的原草稿';businessAssistantState.session={id:81,proposals:[{id:9,status:'pending'}]};globalThis.assistantBefore=JSON.stringify(businessAssistantState);leaveBusinessAssistantView=()=>{};go=route=>recordNavigation(route);toast=message=>recordNotice(message);");
 c.recordNavigation=route=>navigations.push(route);c.recordNotice=message=>notices.push(message);
 c.allowedSelector=c.run("WORKFLOW_QUICK_FORMS['wf-reception'].selector");
 c.open=()=>c.run("workflowOpenForm('wf-reception')");
 c.apply=()=>c.run('applyWorkflowFormIntent()');
 c.arrive=()=>c.run("state.route='cases/lead'");
 c.clicks=()=>clicks;c.setModal=value=>{modal=value;};c.setVisible=value=>{visible=value;};c.setPresent=value=>{present=value;};c.failButton=()=>{buttonError=new Error('模拟原表单暂时无法打开');};
 c.button=button;c.main=main;c.requests=requests;c.queries=queries;c.navigations=navigations;c.notices=notices;
 c.intent=()=>JSON.parse(c.run('JSON.stringify(workflowFormIntent)'));
 c.assertReadOnly=()=>{assert.equal(c.run('JSON.stringify(businessAssistantState)'),c.run('assistantBefore'));assert(requests.every(r=>r.url==='/static/workflow-guides.json'&&(r.options.method||'GET')==='GET'));};
 return c;
}

test('quick form definitions are frozen, known workflow IDs and fixed action selectors',()=>{
 const c=setup(),map=c.run('WORKFLOW_QUICK_FORMS');assert(Object.isFrozen(map));assert(Object.keys(map).length>0);
 for(const [id,form] of Object.entries(map)){
  assert(c.catalogue.some(row=>row.id===id),id);assert(Object.isFrozen(form),id);assert.match(form.selector,/^\[data-act="[a-z0-9_-]+"\](?:\[data-[a-z-]+="[a-z0-9_-]+"\])*$/,id);assert.equal(typeof form.label,'string');
 }
 c.assertReadOnly();
});

test('opening a permitted guide first navigates, then clicks its existing form entry once',async()=>{
 const c=setup();await c.open();assert.deepEqual(c.navigations,['cases/lead']);assert.equal(c.clicks(),0);
 assert.equal(c.intent().context,c.run('workflowContext()'));assert.equal(c.intent().route,'cases/lead');assert.equal(c.intent().selector,c.allowedSelector);
 c.arrive();c.apply();c.apply();assert.equal(c.clicks(),1);assert.equal(c.intent(),null);
 assert(c.queries.some(q=>q.scope==='main'&&q.selector===c.allowedSelector));assert(!c.queries.some(q=>q.scope==='document'&&q.selector===c.allowedSelector));assert.equal(c.requests.length,0);c.assertReadOnly();
});

test('the real successful render opens a pending form after its page is ready',async()=>{
 const c=setup();await c.open();c.arrive();await c.run('render()');assert.equal(c.clicks(),1);assert.equal(c.intent(),null);await c.run('render()');assert.equal(c.clicks(),1);c.assertReadOnly();
});

test('forbidden roles, aggregate or missing stores, logout and switching reject form shortcuts',async()=>{
 for(const change of ["state.user.role='auditor'","state.user.role='technician'","state.store='all'","state.store=null","state.user=null","state.storeSwitch={target:'2'}"]){
  const c=setup();c.run(change);await c.open();c.arrive();c.apply();assert.deepEqual(c.navigations,[],change);assert.equal(c.clicks(),0,change);assert.equal(c.intent(),null,change);c.assertReadOnly();
 }
});

test('an existing form is preserved rather than navigating or opening another',async()=>{
 const c=setup();c.setModal(true);await c.open();assert.equal(c.clicks(),0);assert.deepEqual(c.navigations,[]);assert.equal(c.intent(),null);assert.match(c.notices.join(' '),/关闭|完成/);c.assertReadOnly();
});

test('workflow IDs cannot carry arbitrary selectors, routes or model actions',async()=>{
 const c=setup();for(const value of ['#delete-all','javascript:attack()','__proto__','constructor',{id:leadID,selector:'[type="submit"]'}]){
  c.badID=value;await c.run('workflowOpenForm(badID)');assert.equal(c.intent(),null);assert.deepEqual(c.navigations,[]);
 }
 c.run("catalogue.find(w=>w.id==='wf-reception').selector='[type=submit]';catalogue.find(w=>w.id==='wf-reception').quick_form={selector:'[type=submit]'}");
 await c.run("workflowOpenForm('wf-reception','[type=submit]','users')");assert.equal(c.intent().selector,c.allowedSelector);assert.equal(c.intent().route,'cases/lead');c.arrive();c.apply();assert.equal(c.clicks(),1);c.assertReadOnly();
});

test('original-record returns, refunds, corrections and import confirmations have no shortcut',async()=>{
 const c=setup();for(const id of ['wf-sale-cancellation','wf-vehicle-batch-import','wf-vehicle-purchase-return','wf-material-purchase-return','wf-retail-return','wf-cash-correction','wf-member-topup-refund']){
  assert(c.catalogue.some(row=>row.id===id),id);c.recordID=id;assert.equal(c.run('WORKFLOW_QUICK_FORMS[recordID]'),undefined,id);await c.run('workflowOpenForm(recordID)');assert.equal(c.intent(),null,id);
 }
 assert.deepEqual(c.navigations,[]);assert.equal(c.clicks(),0);c.assertReadOnly();
});

test('changing store or route between navigation and rendering discards the form intent',async()=>{
 for(const change of ["storeContextVersion++;state.store='2'","state.route='cases/repair'","state.storeSwitch={target:'2'}","state.user=null"]){
  const c=setup();await c.open();c.arrive();c.run(change);c.apply();assert.equal(c.clicks(),0,change);assert.equal(c.intent(),null,change);c.assertReadOnly();
 }
 const c=setup();await c.open();c.run('clearWorkflowContext()');c.arrive();c.apply();assert.equal(c.clicks(),0);assert.equal(c.intent(),null);
});

test('leaving through another slow page and returning cannot revive an old form request',async()=>{
 const c=setup();await c.open();c.arrive();let finishFirstPage,finishOtherPage;
 c.casesPage=()=>new Promise(resolve=>{finishFirstPage=resolve;});
 const firstRender=c.run('render()');assert.equal(c.clicks(),0);assert(c.intent());
 // Neither page has completed. Changing pages must discard the old intent now,
 // since waiting until the other page finishes would let a quick return reuse it.
 c.salesQuotesPage=()=>new Promise(resolve=>{finishOtherPage=resolve;});
 c.run("state.route='sales-quotes'");const otherRender=c.run('render()');
 c.arrive();c.casesPage=async()=>'<h1>售前接待</h1>';await c.run('render()');
 assert.equal(c.clicks(),0,'Returning manually must not reopen the abandoned form');assert.equal(c.intent(),null);
 finishOtherPage('<h1>预订合同</h1>');await otherRender;
 finishFirstPage('<h1>售前接待旧回复</h1>');await firstRender;
 assert.equal(c.clicks(),0);assert.equal(c.main.innerHTML,'<h1>售前接待</h1>');assert.equal(c.intent(),null);c.assertReadOnly();
});

test('a different modal appearing while the page loads consumes the intent without opening it',async()=>{
 const c=setup();await c.open();c.arrive();c.setModal(true);c.apply();assert.equal(c.clicks(),0);assert.equal(c.intent(),null);c.setModal(false);c.apply();assert.equal(c.clicks(),0);c.assertReadOnly();
});

test('missing, disabled, hidden and nonvisible native entries cannot be clicked',async()=>{
 for(const unavailable of [c=>c.setPresent(false),c=>{c.button.disabled=true;},c=>{c.button.hidden=true;},c=>c.setVisible(false)]){
  const c=setup();await c.open();c.arrive();unavailable(c);c.apply();assert.equal(c.clicks(),0);assert.equal(c.intent(),null);assert.match(c.notices.join(' '),/页面|办理/);c.assertReadOnly();
 }
});

test('a page render failure clears the intent so retry does not unexpectedly open a form',async()=>{
 const c=setup();await c.open();c.arrive();c.casesPage=async()=>{throw new Error('模拟页面读取失败');};await c.run('render()');assert.equal(c.clicks(),0);assert.equal(c.intent(),null);assert.match(c.main.innerHTML,/暂时无法显示|模拟页面读取失败/);
 c.casesPage=async()=>'<h1>售前接待</h1>';await c.run('render()');assert.equal(c.clicks(),0);c.assertReadOnly();
});

test('an exception from the native entry does not retain or repeat the form intent',async()=>{
 const c=setup();await c.open();c.arrive();c.failButton();await c.run('render()');assert.equal(c.clicks(),1);assert.equal(c.intent(),null);await c.run('render()');assert.equal(c.clicks(),1);c.assertReadOnly();
});

test('a late catalogue reply after a store switch cannot navigate or open the old form',async()=>{
 const c=setup();let resolve;c.transport=()=>new Promise(done=>{resolve=done;});c.run('workflowCatalogue=null');const pending=c.open();
 c.run("storeContextVersion++;state.store='2';clearWorkflowContext()");resolve({ok:true,json:async()=>({schema_version:1,workflows:c.catalogue})});await pending;c.arrive();c.apply();
 assert.deepEqual(c.navigations,[]);assert.equal(c.clicks(),0);assert.equal(c.intent(),null);assert.equal(c.requests.length,1);c.assertReadOnly();
});

test('an unavailable catalogue reports failure without creating an intent or a write request',async()=>{
 const c=setup();c.transport=async()=>({ok:false,status:503});c.run('workflowCatalogue=null');await assert.rejects(c.open(),/读取|重试/);assert.equal(c.intent(),null);assert.deepEqual(c.navigations,[]);assert.equal(c.clicks(),0);c.assertReadOnly();
});
