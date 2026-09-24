'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..');
function sample(overrides={}){return {id:'wf-sale',title:'预订车辆与签订合同',category:'整车销售',summary:'录入客户和预订',keywords:['订车','合同','定金'],roles:['sales'],requirement_ids:['HK-004'],requirements:[{id:'HK-004',title:'销售合同',group:'整车销售'}],entry:{route:'sales-quotes',label:'打开预订与合同',roles:['sales','manager'],mode:'write'},prerequisites:['客户与车型'],manual:[{actor:'销售',where:'预订与合同',action:'新建预订',expected:'等待核价'}],assistant:{mode:'prepare',prompt:'帮我登记预订，缺信息先问我。',steps:[{actor:'本人',action:'补充资料',expected:'待确认表单'}]},exceptions:[{when:'缺车型',action:'在原表补车型'}],completion:['核对单据'],screenshot:{src:'workflow-assets/sale.png',caption:'销售入口'},...overrides};}
function setup(){
 const handlers={};const c={console,Set,Map,Promise,JSON,Intl,Date,Number,Math,URLSearchParams,FormData,AbortController,setTimeout,clearTimeout,
 document:{cookie:'dealer_csrf=test',querySelector:()=>null,querySelectorAll:()=>[],getElementById:()=>null,addEventListener:(name,handler)=>(handlers[name]||=[]).push(handler)},window:{addEventListener(){}},fetch:async()=>{throw new Error('Unexpected fetch');}};
 vm.createContext(c);const app=fs.readFileSync(path.join(root,'web/app.js'),'utf8');vm.runInContext(app.slice(0,app.indexOf('async function api(')),c);
 for(const file of ['businessassistant.js','workflowcontent.js','workflowguides.js'])vm.runInContext(fs.readFileSync(path.join(root,'web',file),'utf8'),c);
 c.run=code=>vm.runInContext(code,c);c.handlers=handlers;c.item=sample();
 c.run("state.user={id:7,role:'sales'};state.store='1';state.route='workflows/wf-sale';state.stores=[{id:1,name:'合成一店'}];businessAssistantState.context=businessAssistantContext();globalThis.a=businessAssistantState;globalThis.s=state;workflowCatalogue={schema_version:1,workflows:[item]};go=route=>{globalThis.destination=route};toast=message=>{globalThis.notice=message};paintBusinessAssistant=()=>{};");
 return c;
}
test('search accepts employee aliases, requirement titles and stable IDs',()=>{
 const c=setup();c.rows=[sample(),sample({id:'wf-refund',title:'原单退款',keywords:['退钱'],requirements:[{id:'HK-083',title:'采购入库退货收款'}]})];
 for(const q of ['订车','我要预定车辆','HK-004','销售合同']){c.q=q;assert.equal(c.run('WorkflowGuides.search(rows,q)[0].id'),'wf-sale');}
 c.q='采购入库退货收款';assert.equal(c.run('WorkflowGuides.search(rows,q)[0].id'),'wf-refund');
 c.q='不存在的功能';assert.equal(c.run('WorkflowGuides.search(rows,q).length'),0);
 c.rows=[sample({id:'wf-other',title:'其他业务',summary:'需要员工账号'}),sample({id:'wf-users',title:'新增员工',entry:{route:'users',label:'打开员工账号',roles:['admin'],mode:'write'}})];
 assert.equal(c.run("WorkflowGuides.search(rows,'员工账号')[0].id"),'wf-users');
});
test('category filters and current-role ranking never manufacture permission',()=>{
 const c=setup();c.rows=[sample(),sample({id:'wf-finance',title:'财务收款',category:'财务',roles:['finance'],entry:{route:'business-finance',roles:['finance'],mode:'write'}})];
 assert.equal(c.run("WorkflowGuides.search(rows,'','sales')[0].id"),'wf-sale');assert.equal(c.run("WorkflowGuides.search(rows,'','sales','财务')[0].id"),'wf-finance');
 assert.equal(c.run("WorkflowGuides.canEnter(rows[1],'sales','1')"),false);assert.equal(c.run("WorkflowGuides.canEnter(rows[1],'admin','all')"),false);assert.equal(c.run("WorkflowGuides.canEnter(rows[1],'finance','1')"),true);
});
test('illustrated dual paths escape source labels and never execute instruction text',()=>{
 const c=setup();c.item=sample({title:'<script>evil</script>',manual:[{actor:'<img>',where:'<svg>',action:'<iframe>',expected:'<script>'}],entry:{route:'sales-quotes',roles:['sales'],label:'打开<svg>',mode:'write'}});
 const html=c.run("WorkflowGuides.article(item,{role:'sales',store:'1'})");assert(html.includes('手动办理'));assert(html.includes('业务助手办理'));assert(html.includes('workflow-assets/sale.png'));assert(!html.includes('<script>'));assert(!html.includes('<iframe>'));assert(html.includes('&lt;script&gt;'));assert(html.includes('data-wf-panel="assistant" hidden'));
 for(const route of ['javascript:evil','//evil.example','https://example.test','sales-quotes/../users','sales-quotes?x=1']){c.route=route;assert.equal(c.run('WorkflowGuides.validRoute(route)'),false);}
});
test('assistant entry fills a new draft only; no network call or business confirmation',async()=>{
 const c=setup();c.run("businessAssistantState.session={id:77,messages:[],proposals:[{id:8,status:'pending'}]};businessAssistantState.sessions=[businessAssistantState.session]");
 await c.run("workflowAsk('wf-sale')");assert.equal(c.destination,'business-assistant');assert.equal(c.a.session.id,77);
 c.run('applyWorkflowAssistantIntent()');assert.equal(c.a.session,null);assert(c.a.draft.includes('预订车辆'));assert(c.a.draft.includes('等我核对确认'));assert.equal(c.a.sessions[0].proposals[0].status,'pending');assert.equal(c.a.tab,'chat');
});
test('existing draft or pending processing is preserved when starting a workflow',async()=>{
 const c=setup();c.run("businessAssistantState.draft='客户资料尚未发送'");await c.run("workflowAsk('wf-sale')");assert.equal(c.a.draft,'客户资料尚未发送');assert.match(c.notice,/未发送/);c.run('applyWorkflowAssistantIntent()');assert.equal(c.a.draft,'客户资料尚未发送');
 c.run("businessAssistantState.draft='';businessAssistantState.busy=true");await c.run("workflowAsk('wf-sale')");assert.match(c.notice,/正在处理/);assert.equal(c.a.draft,'');
});
test('store switch or logout discards a pending guide prompt and closes search',async()=>{
 const c=setup();await c.run("workflowAsk('wf-sale')");c.run("storeContextVersion++;state.store='2';clearBusinessAssistantSession();applyWorkflowAssistantIntent();globalThis.next=businessAssistantState");assert.equal(c.next.draft,'');assert.equal(c.run('workflowAssistantIntent'),null);
});
test('an unfinished original form cannot be discarded through help navigation',async()=>{
 const c=setup();c.document.querySelector=selector=>selector==='#modal[open]'?{}:null;
 c.run("workflowNavigate('workflows/wf-sale')");assert.equal(c.destination,undefined);assert.match(c.notice,/先完成/);
 await c.run("workflowAsk('wf-sale')");assert.equal(c.destination,undefined);assert.equal(c.a.draft,'');
});
test('read-only aggregate mode does not start a business assistant draft',async()=>{
 const c=setup();c.run("state.store='all'");await c.run("workflowAsk('wf-sale')");assert.equal(c.destination,undefined);assert.equal(c.a.draft,'');
});
test('a late catalogue response cannot start the old stores assistant intent',async()=>{
 const c=setup();let resolve;c.fetch=()=>new Promise(done=>resolve=done);c.run('workflowCatalogue=null');const pending=c.run("workflowAsk('wf-sale')");c.run("storeContextVersion++;state.store='2';clearBusinessAssistantSession()");resolve({ok:true,json:async()=>({schema_version:1,workflows:[sample()]})});await pending;assert.equal(c.destination,undefined);assert.equal(c.run('workflowAssistantIntent'),null);
});

test('top search can reopen by clicking or typing after Escape keeps its focus',async()=>{
 const c=setup();c.run('globalThis.opened=[];openWorkflowSearch=query=>opened.push(query)');
 const target={id:'workflow-top-search',value:'收款',closest:()=>null};
 for(const handle of c.handlers.click)await handle({target});assert.equal(c.run('opened[0]'),'收款');
 for(const handle of c.handlers.input)handle({target,isComposing:false});assert.equal(c.run('opened.length'),2);
 for(const handle of c.handlers.input)handle({target,isComposing:true});assert.equal(c.run('opened.length'),2);
 for(const handle of c.handlers.compositionend)handle({target});assert.equal(c.run('opened.length'),3);
 for(const handle of c.handlers.focusin||[])handle({target});assert.equal(c.run('opened.length'),3);
 for(const handle of c.handlers.keydown)handle({target,key:'Enter',preventDefault(){}});assert.equal(c.run('opened.length'),4);
 target.selectionStart=0;target.selectionEnd=2;
 for(const handle of c.handlers.keydown)handle({target,key:'H',preventDefault(){}});assert.equal(c.run('opened[4]'),'H');
 for(const handle of c.handlers.keydown)handle({target,key:'a',isComposing:true,preventDefault(){}});assert.equal(c.run('opened.length'),5);
 for(const handle of c.handlers.keydown)handle({target,key:'v',ctrlKey:true,preventDefault(){}});assert.equal(c.run('opened.length'),5);
});
