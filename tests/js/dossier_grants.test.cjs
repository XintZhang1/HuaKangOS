'use strict';
// Pure rendering/state tests with mocked transport; not a real-browser pass.
const test=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const root=path.resolve(__dirname,'../..');
function sandbox(){
 const handlers={};const calls=[];
 const ctx={console,URLSearchParams,URL,Intl,Date,Number,Math,Set,JSON,Promise,FormData:class{},
  setTimeout:()=>1,clearTimeout:()=>{},document:{cookie:'',hidden:false,addEventListener:(k,f)=>handlers[k]=f,querySelector:()=>({open:false}),querySelectorAll:()=>[]},
  window:{addEventListener:()=>{}},api:async p=>{calls.push(p);throw new Error('Unexpected request '+p);},render:()=>{},toast:()=>{}};
 vm.createContext(ctx);
 // Execute the real shared escaping, table and heading helpers, not substitutes.
 const app=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
 vm.runInContext(app.slice(0,app.indexOf('async function api(')),ctx);
 vm.runInContext("function facts(x){return Object.entries(x).map(([k,v])=>E(k)+': '+E(v)).join('<br>');}",ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'web/dossiergrants.js'),'utf8'),ctx);
 vm.runInContext("state.user={id:30,role:'sales'};state.store='2';state.route='dossier-grants/received/4';state.catalog={};globalThis.s=state;",ctx);
 return {ctx,calls,handlers};
}
const record={definition_version:1,case:{number:'O<&"1',kind_label:'合成原单',state_label:'已授权',title:'<script>alert(1)</script>',version:2,business_date:'2026-09-22'},customer:{name:'<img src=x onerror=alert(1)>'},events:[],events_omitted:0};
const grant={id:4,version:2,source_side:false,can_read:true,include_record:true,from_store_name:'来源店',to_store_name:'接收店',status_label:'已批准',expires_at:'2099-01-01T00:00:00Z'};

test('snapshot fields and file names are escaped; no native URL on receiver files',()=>{
 const {ctx}=sandbox();ctx.input=record;
 const h=vm.runInContext('dossierRecord(input)',ctx);
 assert(!h.includes('<script>'));assert(h.includes('&lt;script&gt;'));assert(!h.includes('<img src=x'));
 ctx.g=grant;ctx.files=[{id:5,name:'"><img src=x>',category:'evidence',size:10}];
 const list=vm.runInContext('dossierFiles(g,files,true)',ctx);
 assert(list.includes('dossier-download'));assert(!list.includes('downloadfile'));assert(!list.includes('/api/flow/'));
 assert(list.includes('&lt;img'));
});

test('unknown original cost is labelled separately from an explicitly recorded zero',()=>{
 const {ctx}=sandbox();
 ctx.input={...record,financials:{amount_cents:10000,paid_cents:10000,cost_cents:null,basis:'批准前原单记账快照'}};
 const unknown=vm.runInContext('dossierRecord(input)',ctx);
 assert(unknown.includes('原成本: 原单未记录成本'));
 assert(!unknown.includes('原成本: 0.00 元'));
 ctx.input.financials.cost_cents=0;
 const zero=vm.runInContext('dossierRecord(input)',ctx);
 assert(zero.includes('原成本: 0.00 元'));
 assert(!zero.includes('原单未记录成本'));
 ctx.input.financials.cost_cents=12345;
 assert(vm.runInContext('dossierRecord(input)',ctx).includes('原成本: 123.45 元'));
});

test('receiver loads only fresh named-grant endpoints, never original routes',async()=>{
 const {ctx,calls}=sandbox();ctx.api=async p=>{calls.push(p);if(p.endsWith('/catalog'))return {can_read:true};if(p.endsWith('/record'))return {record,files:[]};if(p.endsWith('/4'))return grant;throw new Error(p);};
 const html=await vm.runInContext("dossierPage('received',4)",ctx);
 assert(html.includes('已冻结的原单快照'));assert.deepEqual(calls,['/api/dossier-grants/catalog','/api/dossier-grants/4','/api/dossier-grants/4/record']);
 assert(ctx.s.dossierSnapshot.record);
});

test('pending or revoked receiver does not request or retain payload',async()=>{
 const {ctx,calls}=sandbox();ctx.s.dossierSnapshot={record};ctx.api=async p=>{calls.push(p);return p.endsWith('/catalog')?{can_read:true}:{...grant,can_read:false,status_label:'已撤销'};};
 const html=await vm.runInContext("dossierPage('received',4)",ctx);
 assert(html.includes('当前不可读取'));assert(!html.includes('O&lt;'));assert.equal(ctx.s.dossierSnapshot,null);assert.equal(calls.length,2);
});

test('file-only scope calls directory and never record route',async()=>{
 const {ctx,calls}=sandbox();ctx.api=async p=>{calls.push(p);if(p.endsWith('/catalog'))return {can_read:true};if(p.endsWith('/files'))return {files:[]};return {...grant,include_record:false};};
 await vm.runInContext("dossierPage('received',4)",ctx);
 assert(calls.includes('/api/dossier-grants/4/files'));assert(!calls.some(p=>p.endsWith('/record')));
});

test('account/store switch discards late in-flight content',async()=>{
 const {ctx}=sandbox();let release;const waiting=new Promise(r=>release=r);ctx.api=async p=>p.endsWith('/catalog')?{can_read:true}:p.endsWith('/record')?waiting:grant;
 const rendering=vm.runInContext("dossierPage('received',4)",ctx);
 await new Promise(r=>setImmediate(r));
 vm.runInContext("clearDossierGrantsSession();state.store='3';state.user={id:31,role:'sales'};",ctx);
 release({record,files:[]});assert.equal(await rendering,'');assert.equal(ctx.s.dossierSnapshot,null);assert.equal(ctx.s.dossierGrant,null);
});

test('leaving grant page invalidates pending view without discarding menu catalog',async()=>{
 const {ctx}=sandbox();ctx.s.dossierCatalog={can_read:true};ctx.s.dossierSnapshot={record};ctx.s.dossierGrant=grant;
 vm.runInContext('leaveDossierGrantsView()',ctx);
 assert.equal(ctx.s.dossierSnapshot,null);assert.equal(ctx.s.dossierGrant,null);assert(ctx.s.dossierCatalog.can_read);
});

test('rejected recheck shows no cached record',async()=>{
 const {ctx}=sandbox();ctx.s.dossierSnapshot={record};ctx.api=async p=>{if(p.endsWith('/catalog'))return {can_read:true};if(p.endsWith('/record'))throw new Error('授权已撤销');return grant;};
 const html=await vm.runInContext("dossierPage('received',4)",ctx);
 assert(html.includes('授权已撤销'));assert(!html.includes('O&lt;'));assert.equal(ctx.s.dossierSnapshot,null);
});
