'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function sandbox(){
 const calls=[],downloads=[],handlers={};
 const ctx={URLSearchParams,console,Promise,FormData,Set,MutationObserver:class{observe(){}},
  document:{documentElement:{},querySelectorAll:()=>[],addEventListener:(name,fn)=>(handlers[name]??=[]).push(fn)},state:{user:{id:7},store:'1',page:1,dates:{start:'2026-09-01',end:'2026-09-24'}},
  E:value=>String(value),b:(action,label)=>`<button data-act="${action}">${label}</button>`,heading:title=>`<h1>${title}</h1>`,storeNotice:()=>'',dateFilters:()=>'',time:value=>value,panel:()=>'',
  api:async url=>{calls.push(url);return url.includes('/options/')?{items:[{id:9,label:'停用历史资料'}],has_more:true}:{complete:true,closing_complete:true,filters:{note:'历史'},charts:[],tables:{},as_of:'today'};},
  download:async(url,name)=>downloads.push({url,name}),toast:()=>{},render:()=>ctx.renders++,renders:0};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/inventoryreports.js'),'utf8'),ctx);ctx.run=code=>vm.runInContext(code,ctx);ctx.calls=calls;ctx.downloads=downloads;ctx.handlers=handlers;return ctx;
}
test('warehouse search retains scoped inactive-history endpoint and refuses unknown domain',async()=>{
 const c=sandbox();await c.run("warehouseHistoryLookup('items','旧件 01')");const url=new URL(c.calls[0],'https://fixture.invalid');assert.equal(url.pathname,'/api/inventory-reports/warehouses/options/items');assert.equal(url.searchParams.get('q'),'旧件 01');assert.throws(()=>c.run("warehouseHistoryLookup('customers','张')"),/筛选类型无效/);
});
test('rendered warehouse filters use one searchable select each and preserve selected historical records',async()=>{
 const c=sandbox();c.run("warehouseReportContext().filters={item_id:'9'}");const html=await c.run('warehousePeriodPage()');assert.equal((html.match(/data-search-select/g)||[]).length,2);assert(html.includes('data-search-all="全部物资"'));assert(html.includes('停用历史资料'));assert(html.includes('value="9" selected'));assert(!html.includes('warehouse-report-lookup'));assert(!html.includes('type="search"'));assert(c.calls.includes('/api/inventory-reports/warehouses/options/items?selected_id=9'));
});
test('typing keeps the displayed report scope; selecting or clearing refreshes it immediately',()=>{
 const c=sandbox();c.run("warehouseReportContext().filters={item_id:'9'}");const select={name:'item_id',value:'',matches:()=>true};const handle=c.handlers.change[0];handle({target:select,liveChoiceReason:'edit'});assert.equal(c.renders,0);assert.equal(c.run('warehouseReportContext().filters.item_id'),'9');select.value='12';handle({target:select,liveChoiceReason:'select'});assert.equal(c.renders,1);assert.equal(c.run('warehouseReportContext().filters.item_id'),'12');select.value='';handle({target:select,liveChoiceReason:'clear'});assert.equal(c.renders,2);assert.equal(c.run('warehouseReportContext().filters.item_id'),undefined);
});
test('chart request and CSV use the exact same confirmed date and history filters',async()=>{
 const c=sandbox();c.run("warehouseReportContext().filters={item_id:'9',warehouse_id:'6'}");await c.run('warehousePeriodPage()');const button={disabled:false,dataset:{kind:'warehouses',key:'closing'}};await c.handlers.click[0]({target:{closest:selector=>selector==='[data-act="inventory-report-export"]'?button:null}});const report=new URL(c.calls.find(url=>url.startsWith('/api/inventory-reports/warehouses?')),'https://fixture.invalid');const csv=new URL(c.downloads[0].url,'https://fixture.invalid');assert.deepEqual([...csv.searchParams],[...report.searchParams]);assert.equal(csv.pathname,'/api/inventory-reports/warehouses/export/closing');assert.equal(button.disabled,false);
});
