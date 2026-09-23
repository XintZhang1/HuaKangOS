'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'../..');
function sandbox(){
 const ctx={console,URLSearchParams,Date,Number,Math,Set,JSON,Promise,document:{addEventListener:()=>{}},window:{},api:async()=>{throw new Error('unexpected')},storeNotice:()=>'',searchBar:()=>'',pager:()=>'',render:()=>{},toast:()=>{}};
 vm.createContext(ctx);const app=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
 vm.runInContext(app.slice(0,app.indexOf('async function api(')),ctx);
 vm.runInContext('function facts(x){return Object.entries(x).map(([k,v])=>E(k)+E(v)).join("<br>");}',ctx);
 for(const name of ['dictionaries','parameters'])vm.runInContext(fs.readFileSync(path.join(root,'web/'+name+'.js'),'utf8'),ctx);
 vm.runInContext("state.user={id:1,role:'manager'};state.store='1';state.q='';state.page=1;globalThis.s=state;",ctx);return ctx;
}
const groups={repair:{category:'维修字典',label:'维修字典'},public:{category:'公共字典',label:'公共字典'}};
test('dictionary names, details and settings labels are escaped',async()=>{
 const ctx=sandbox();ctx.api=async p=>p.endsWith('/catalog')?{groups,can_write:true,notice:'说明'}:{items:[{id:1,version:1,name:'<script>bad</script>',detail:'<img src=x>',active:true}],total:1,label:'维修字典',notice:'说明',can_write:true};
 const h=await vm.runInContext("dictionariesPage('repair')",ctx);assert(!h.includes('<script>'));assert(h.includes('&lt;script&gt;'));assert(!h.includes('<img src=x>'));assert(h.includes('dictionary-edit'));
});
test('dictionary group overview and readonly scope do not invent writers',async()=>{
 const ctx=sandbox();ctx.api=async()=>({groups,can_write:false,notice:'只读'});
 const h=await vm.runInContext('dictionariesPage()',ctx);assert(h.includes('维修字典'));assert(!h.includes('dictionary-new'));
 ctx.s.store='all';const body=await vm.runInContext("dictionariesPage('repair')",ctx);assert(body.includes('具体门店'));assert(!body.includes('dictionary-edit'));
});
test('late dictionary load is discarded after a store change',async()=>{
 const ctx=sandbox();let release;const pending=new Promise(r=>release=r);ctx.api=async p=>p.endsWith('/catalog')?{groups,can_write:true}:pending;
 const render=vm.runInContext("dictionariesPage('repair')",ctx);await new Promise(r=>setImmediate(r));ctx.s.store='2';release({items:[]});await assert.rejects(render,/门店或账号已切换/);
});
test('parameters use password action and original internal editors without write requests',async()=>{
 const ctx=sandbox(),paths=[];ctx.api=async p=>{paths.push(p);return {entries:[{route:'service-intake/resources',label:'工位',description:'<img src=x>',can_write:true}],notice:'原规则',deployment:{timezone:'Asia/Shanghai',private_file_root:'SHOULD_NOT_RENDER'},aggregate_scope:false};};
 const h=await vm.runInContext('parametersPage()',ctx);assert(h.includes('data-act="password"'));assert(h.includes('data-route="service-intake/resources"'));assert(!h.includes('<img src=x>'));assert(!h.includes('SHOULD_NOT_RENDER'));assert.deepEqual(paths,['/api/parameters/catalog']);
});
test('aggregate parameters keep only personal action and no local editor',async()=>{
 const ctx=sandbox();ctx.api=async()=>({entries:[],notice:'选择门店',deployment:null,aggregate_scope:true});
 const h=await vm.runInContext('parametersPage()',ctx);assert(h.includes('data-act="password"'));assert(!h.includes('进入原配置'));
});
