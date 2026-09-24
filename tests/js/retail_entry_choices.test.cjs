'use strict';
// Actual retailNew handlers and submission contract, with synthetic transport.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..'),tick=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};}
function select(value=''){
 let html='';const control={value,listeners:{},addEventListener(type,fn){this.listeners[type]=fn;}};
 Object.defineProperty(control,'innerHTML',{get:()=>html,set:next=>{html=next;control.value='';}});return control;
}
function setup(){
 const handlers={},elements={customer:select('1'),related:select(),discount:{value:'0.00'}},status={textContent:''};
 const prices={item:{value:'7'},quantity:{value:'1.250'},price:{value:'100.50'},work:select(),install_price:{value:'0.00'}};
 const line={dataset:{},querySelector:selector=>prices[selector.slice(6,-1)]};prices.work.name='work';prices.work.closest=()=>line;
 const form={elements,isConnected:true,listeners:{},addEventListener(type,fn){this.listeners[type]=fn;},querySelector:()=>status,querySelectorAll:()=>[line]};
 const ctx={console,Intl,Date,Number,Math,Set,Map,JSON,Promise,URLSearchParams,
  document:{addEventListener:(name,fn)=>(handlers[name]??=[]).push(fn),querySelector:()=>form},window:{addEventListener(){}},
  setTimeout:()=>1,requestKey:()=> 'retail-test-request-123456',memberPriceField:async()=>'',memberPricePayload:()=>({}),bindMemberPriceCustomer:()=>{},
  closeModal:()=>{},go:route=>ctx.route=route,render:async()=>{},calls:[],form,prices,line,status};
 vm.createContext(ctx);const app=fs.readFileSync(path.join(root,'web/app.js'),'utf8');vm.runInContext(app.slice(0,app.indexOf('async function api(')),ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'web/retail.js'),'utf8'),ctx);
 vm.runInContext("state.user={id:6,role:'sales'};state.store='1';state.route='retail';state.catalog={};globalThis.s=state;",ctx);
 ctx.requestKey=()=> 'retail-test-request-123456';
 ctx.modal=(_title,html,save)=>{
  ctx.save=save;
  // Read controls emitted by the real dialog renderer, not source-code strings.
  for(const match of html.matchAll(/<(select|input|textarea)\b([^>]*)>/g)){
   const attrs={};for(const attr of match[2].matchAll(/([^\s=]+)(?:="([^"]*)")?/g))attrs[attr[1]]=attr[2]??true;
   if(attrs.name in prices){prices[attrs.name].required=Object.hasOwn(attrs,'required');prices[attrs.name].searchable=Object.hasOwn(attrs,'data-search-select');}
  }
 };
 ctx.repairs=async()=>({items:[],total:0});
 ctx.api=async(url,options)=>{
  ctx.calls.push({url,options});if(options)return {id:88};
  if(url.startsWith('/api/flow/master/customers'))return {items:[{id:1,name:'合成甲'},{id:2,name:'合成乙'}],total:2};
  if(url.startsWith('/api/retail/items'))return {items:[{id:7,sku:'ITEM7',name:'测试精品',active:true,available_quantity:'5'}],total:1};
  if(url.startsWith('/api/retail/installations'))return {items:[{id:3,code:'W3',name:'普通安装',standard_fee_cents:12999},{id:4,code:'W4',name:'另一安装',standard_fee_cents:18000}],total:2};
  return ctx.repairs(url);
 };
 ctx.run=code=>vm.runInContext(code,ctx);return ctx;
}
async function opened(){const ctx=setup();await ctx.run('retailNew()');await tick();return ctx;}

test('selecting installation changes reference fee; searching and reselecting same project retain manual price',async()=>{
 const c=await opened(),work=c.prices.work,change=c.form.listeners.change;
 work.value='3';change({target:work,liveChoiceReason:'select'});assert.equal(c.prices.install_price.value,'129.99');
 c.prices.install_price.value='118.80';work.value='';change({target:work,liveChoiceReason:'edit'});assert.equal(c.prices.install_price.value,'118.80');
 work.value='3';change({target:work,liveChoiceReason:'select'});assert.equal(c.prices.install_price.value,'118.80');
 work.value='4';change({target:work,liveChoiceReason:'select'});assert.equal(c.prices.install_price.value,'180.00');
});

test('explicit no-installation clears the fee while unrelated form changes preserve it',async()=>{
 const c=await opened(),work=c.prices.work,change=c.form.listeners.change;
 work.value='3';change({target:work,liveChoiceReason:'select'});c.prices.install_price.value='99.99';
 change({target:{name:'quantity',value:'2'}});assert.equal(c.prices.install_price.value,'99.99');
 work.value='';change({target:work,liveChoiceReason:'clear'});assert.equal(c.prices.install_price.value,'0.00');assert.equal(c.line.dataset.pricedWork,'');
 work.value='3';change({target:work,liveChoiceReason:'select'});assert.equal(c.prices.install_price.value,'129.99');
});

test('rendered item choice is required and actual save keeps selected IDs plus manually edited installation fee',async()=>{
 const c=await opened();assert.equal(c.prices.item.required,true);assert.equal(c.prices.item.searchable,true);
 c.prices.work.value='3';c.form.listeners.change({target:c.prices.work,liveChoiceReason:'select'});c.prices.install_price.value='118.80';
 await c.save(c.form);const write=c.calls.find(call=>call.options);assert.equal(write.url,'/api/retail/orders');assert.equal(write.options.body.customer_id,1);
 const row=write.options.body.lines[0];assert.equal(row.item_id,7);assert.equal(row.quantity_milli,1250);assert.equal(row.unit_price_cents,10050);assert.equal(row.work_item_id,3);assert.equal(row.installation_unit_price_cents,11880);
 assert.equal(c.route,'retail/88');
});

test('changing customer clears old repair immediately and stale reply cannot repopulate another customer repairs',async()=>{
 const c=setup(),old=deferred(),newer=deferred();c.repairs=url=>url.includes('customer_id=1')?old.promise:newer.promise;
 await c.run('retailNew()');c.form.elements.related.value='101';c.form.elements.customer.value='2';const second=c.form.elements.customer.listeners.change();
 assert.equal(c.form.elements.related.value,'');assert(!c.form.elements.related.innerHTML.includes('101'));
 newer.resolve({items:[{id:202,number:'R202',title:'乙客户维修',state_label:'待办理'}],total:1});await second;
 old.resolve({items:[{id:101,number:'R101',title:'甲客户维修',state_label:'待办理'}],total:1});await tick();
 assert(c.form.elements.related.innerHTML.includes('R202'));assert(!c.form.elements.related.innerHTML.includes('R101'));
 c.form.elements.related.value='202';await c.save(c.form);const body=c.calls.find(call=>call.options).options.body;assert.equal(body.customer_id,2);assert.equal(body.related_repair_id,202);
});

test('clearing customer or changing stores prevents pending repairs from returning',async()=>{
 const c=setup(),gate=deferred();c.repairs=()=>gate.promise;await c.run('retailNew()');
 c.form.elements.related.value='101';c.form.elements.customer.value='';await c.form.elements.customer.listeners.change();gate.resolve({items:[{id:101,number:'STALE',title:'旧客户',state_label:'待办理'}],total:1});await tick();
 assert.equal(c.form.elements.related.value,'');assert(!c.form.elements.related.innerHTML.includes('STALE'));
 const moved=setup(),late=deferred();moved.repairs=()=>late.promise;await moved.run('retailNew()');moved.run('storeContextVersion++');late.resolve({items:[{id:404,number:'OLD-STORE',title:'原门店',state_label:'待办理'}],total:1});await tick();
 assert(!moved.form.elements.related.innerHTML.includes('OLD-STORE'));assert.equal(moved.form.elements.related.value,'');
});

test('a removed dialog never receives an outstanding customer repair list',async()=>{
 const c=setup(),gate=deferred();c.repairs=()=>gate.promise;await c.run('retailNew()');c.form.isConnected=false;
 gate.resolve({items:[{id:901,number:'DETACHED',title:'旧弹窗',state_label:'待办理'}],total:1});await tick();assert(!c.form.elements.related.innerHTML.includes('DETACHED'));
});
