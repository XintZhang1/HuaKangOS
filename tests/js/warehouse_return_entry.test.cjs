'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'../..'),tick=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};}
function original(id=31){return {original_move_id:id,operation:'gift_return',item_id:7,item_name:'测试礼品',sku:'GIFT-7',unit:'件',source_number:'WH-ORIGINAL-'+id,business_date:'2026-09-23',original_quantity_milli:3000,returned_quantity_milli:1000,remaining_quantity_milli:2000,can_return:true};}
function control(value=''){return {value,disabled:false,listeners:{},addEventListener(name,fn){this.listeners[name]=fn;},dispatchEvent(event){return this.listeners[event.type]?.(event);},removeAttribute(key){delete this[key];}};}
function setup(){
 const elements={original:control(),quantity:control(),location:control(),reason:control('实际原批次退回'),due_date:control('2026-09-24')},summary={innerHTML:''},status={textContent:''},button={disabled:true};
 const form={elements,isConnected:true,querySelector:selector=>selector==='[data-return-summary]'?summary:selector==='[data-return-status]'?status:button};
 const dialog={open:true,querySelector:()=>form};
 const c={state:{user:{id:6},store:'1'},storeContextVersion:1,console,Promise,Map,Number,Date,URLSearchParams,Event:class{constructor(type){this.type=type;}},
  document:{addEventListener(){}},E:value=>String(value).replaceAll('<','&lt;'),b:()=>'',whQty:value=>String(value/1000),facts:rows=>JSON.stringify(rows),day:()=> '2026-09-24',requestKey:()=> 'same-original-return-request',
  calls:[],dialog,form,summary,status,button,modal:(_title,_html,submit)=>{c.submit=submit;c.opened=true;return dialog;},closeModal:()=>{dialog.open=false;},go:route=>c.route=route,
  requireStoreContext:version=>{if(version!==c.storeContextVersion)throw new Error('门店已切换');},registerLiveChoiceLoader:(select,loader)=>{select.loader=loader;}};
 vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(root,'web/procurement.js'),'utf8'),c);
 c.procurementAll=async url=>url.includes('/locations')?[{id:5,name:'接收库位',warehouse_id:9}]:[{id:9,name:'测试物资仓',warehouse_type:'materials'}];
 c.api=async(url,options)=>{c.calls.push({url,options});if(options)return {id:99};if(url.endsWith('/catalog'))return {can_create:true};return {items:[original()],total:1};};
 vm.runInContext(fs.readFileSync(path.join(root,'web/warehousereturns.js'),'utf8'),c);c.run=js=>vm.runInContext(js,c);return c;
}

test('original batch opens with real quantities and date but never assumes actual location or amount',async()=>{
 const c=setup();await c.run("whReturnNew('gift_return',{originalMoveId:31})");await tick();
 assert.equal(c.form.elements.original.value,'31');assert(c.summary.innerHTML.includes('2026-09-23'));assert(c.summary.innerHTML.includes('尚可退'));
 assert.equal(c.form.elements.quantity.max,'2');assert.equal(c.form.elements.quantity.value,'');assert.equal(c.form.elements.location.value,'');assert.equal(c.button.disabled,false);
});

test('one application preserves original item/source and exact milli; no cost or execute command is sent',async()=>{
 const c=setup();await c.run("whReturnNew('gift_return',{originalMoveId:31})");await tick();
 c.form.elements.quantity.value='1.251';c.form.elements.location.value='5';await c.submit(c.form);
 const posts=c.calls.filter(r=>r.options);assert.equal(posts.length,1);assert.equal(posts[0].url,'/api/warehouse/cases');const body=posts[0].options.body;
 assert.equal(body.original_move_id,31);assert.equal(body.item_id,7);assert.equal(body.quantity_milli,1251);assert.equal(body.destination_location_id,5);assert(!('source_location_id' in body));assert(!Object.keys(body).some(key=>/cost|value/.test(key)));assert.equal(c.route,'warehouse/99');
});

test('outbound original return uses employee-selected departure bin and rejects excessive or malformed amounts',()=>{
 const c=setup();c.source={...original(),operation:'other_in_return'};c.form.elements.original.value='31';c.form.elements.location.value='5';c.form.elements.quantity.value='1.999';
 const body=c.run("whReturnValues(form,source,'other_in_return','request-123456789')");assert.equal(body.quantity_milli,1999);assert.equal(body.source_location_id,5);assert(!('destination_location_id' in body));
 for(const amount of ['2.001','0','1.0001']){c.form.elements.quantity.value=amount;assert.throws(()=>c.run("whReturnValues(form,source,'other_in_return','request-123456789')"));}
 c.form.elements.quantity.value='1';c.form.elements.location.value='';assert.throws(()=>c.run("whReturnValues(form,source,'other_in_return','request-123456789')"),/实际库位/);
});

test('search uses domain-limited source route; a changed choice ignores earlier remainder results',async()=>{
 const c=setup();await c.run("whReturnNew('gift_return')");const found=await c.form.elements.original.loader('礼品 / 原单');assert.equal(found.items[0].id,31);assert(c.calls.at(-1).url.includes('operation=gift_return&q='+encodeURIComponent('礼品 / 原单')));
 const old=deferred(),fresh=deferred();c.api=url=>url.endsWith('=31')?old.promise:fresh.promise;
 c.form.elements.original.value='31';const first=c.form.elements.original.listeners.change();c.form.elements.original.value='32';const second=c.form.elements.original.listeners.change();
 fresh.resolve({items:[{...original(32),remaining_quantity_milli:500}]});await second;old.resolve({items:[original(31)]});await first;
 assert.equal(c.form.elements.quantity.max,'0.5');assert(c.summary.innerHTML.includes('WH-ORIGINAL-32'));assert(!c.summary.innerHTML.includes('WH-ORIGINAL-31'));
 c.form.elements.original.value='';await c.form.elements.original.listeners.change();assert.equal(c.summary.innerHTML,'');assert.equal(c.button.disabled,true);
});

test('double submit creates once and failed save retains request and employee inputs',async()=>{
 const c=setup();await c.run("whReturnNew('gift_return',{originalMoveId:31})");await tick();c.form.elements.quantity.value='1';c.form.elements.location.value='5';
 const gate=deferred();c.api=async(url,options)=>{c.calls.push({url,options});return gate.promise;};const first=c.submit(c.form);await c.submit(c.form);assert.equal(c.calls.filter(r=>r.options).length,1);
 gate.resolve({id:99});await first;
 const retry=setup();await retry.run("whReturnNew('gift_return',{originalMoveId:31})");await tick();retry.form.elements.quantity.value='1.250';retry.form.elements.location.value='5';
 retry.api=async(url,options)=>{retry.calls.push({url,options});throw new Error('连接中断');};await assert.rejects(retry.submit(retry.form));await assert.rejects(retry.submit(retry.form));
 assert.equal(retry.form.elements.quantity.value,'1.250');assert.equal(retry.dialog.open,true);const requests=retry.calls.filter(r=>r.options);assert.equal(requests[0].options.body.request_id,requests[1].options.body.request_id);
});

test('store switch blocks old source reading and actual submission; returned-out source cannot apply',async()=>{
 const c=setup(),gate=deferred();c.api=()=>gate.promise;const opening=c.run("whReturnNew('gift_return')");c.storeContextVersion++;gate.resolve({can_create:true,items:[original()],total:1});await assert.rejects(opening,/门店已切换/);assert(!c.opened);
 const stale=setup();await stale.run("whReturnNew('gift_return',{originalMoveId:31})");await tick();stale.storeContextVersion++;await assert.rejects(stale.submit(stale.form),/门店已切换/);
 const closed=setup();closed.source={...original(),remaining_quantity_milli:0,can_return:false};closed.form.elements.original.value='31';assert.throws(()=>closed.run("whReturnValues(form,source,'gift_return','request-123456789')"),/已无可退数量/);
});
