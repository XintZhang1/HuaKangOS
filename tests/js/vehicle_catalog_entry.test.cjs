'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../../web/vehiclecatalog.js'),'utf8');
function deferred(){let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};}
function setup(){
 const elements={},labels={};
 const initial={brand_id:'1',series_id:'2',brand_name:'',series_name:'',name:'旗舰型',model_year:'2026',fuel_type:'electric',seats:'5',displacement:'',battery:'60.501',price:'139800.01'};
 for(const [key,value]of Object.entries(initial)){labels[key]={hidden:false};elements[key]={value,disabled:false,required:false,closest:()=>labels[key]};}
 const form={elements,addEventListener(){}};
 const c={state:{user:{id:7},store:'1'},storeContextVersion:3,console,Promise,URLSearchParams,Date,Number,Set,labels,form,
  E:value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),b:()=>'',masterOptions:{electric:'纯电'},
  document:{addEventListener(){}},FormData:class{constructor(form){this.form=form;}get(key){const el=this.form.elements[key];return el&&!el.disabled?el.value:null;}},
  requestKey:()=> 'one-catalog-request-123456',masterFen:value=>Math.round(Number(value)*100),calls:[],closed:0,rendered:0,toasts:[],
  options:{brands:[{id:1,name:'品牌',version:4}],series:[{id:2,brand_id:1,name:'车系',version:8}]}};
 c.api=async(url,request)=>{c.calls.push({url,request});return url.endsWith('entry-options')?c.options:c.result;};
 c.modal=(title,html,submit)=>{c.title=title;c.html=html;c.submit=submit;return {querySelector:()=>form,addEventListener:(_event,fn)=>c.onclose=fn};};
 c.closeModal=()=>{c.closed++;if(c.onclose)c.onclose();};c.render=async()=>c.rendered++;c.toast=value=>c.toasts.push(value);
 vm.createContext(c);vm.runInContext(code,c);c.run=value=>vm.runInContext(value,c);return c;
}

test('single entry carries exact selected versions and converts litres/kWh without rounding',()=>{
 const c=setup(),p=c.run("catalogEntryPayload(form,options,'request-example-123456')");
 assert.equal(p.brand_id,1);assert.equal(p.brand_version,4);assert.equal(p.series_id,2);assert.equal(p.series_version,8);
 assert.equal(p.brand_name,'');assert.equal(p.battery_wh,60501);assert.equal(p.guide_price_cents,13980001);assert.equal(p.displacement_ml,0);
 c.form.elements.fuel_type.value='petrol';c.form.elements.displacement.value='1.498';
 assert.equal(c.run("catalogEntryPayload(form,options,'request-example-123456')").displacement_ml,1498);
 assert.equal(c.run("catalogEntryPayload(form,options,'request-example-123456')").battery_wh,0);
 assert.throws(()=>c.run("catalogThousand('60.5011','电池容量')"),/三位小数/);
 assert.throws(()=>c.run("catalogThousand('1e3','排量')"),/三位小数/);
});

test('new names replace IDs and parent mismatch never silently reuses another brand series',()=>{
 const c=setup();c.form.elements.brand_id.value='new';c.form.elements.brand_name.value=' 新品牌 ';c.form.elements.series_id.value='new';c.form.elements.series_name.value=' 新车系 ';
 const p=c.run("catalogEntryPayload(form,options,'request-example-123456')");
 assert.equal(p.brand_id,null);assert.equal(p.brand_version,null);assert.equal(p.brand_name,'新品牌');assert.equal(p.series_name,'新车系');
 c.form.elements.series_id.value='2';assert.throws(()=>c.run("catalogEntryPayload(form,options,'request-example-123456')"),/该品牌/);
});

test('late options never opens a dialog in a newly selected store',async()=>{
 const c=setup(),gate=deferred();c.api=()=>gate.promise;
 const pending=c.run('catalogEntryDialog()');c.state.store='2';gate.resolve(c.options);await pending;
 assert.equal(c.html,undefined);
});

test('failed save retains entry and request ID; concurrent submit sends only once',async()=>{
 const c=setup();await c.run('catalogEntryDialog()');const gate=deferred();c.api=async(url,request)=>{c.calls.push({url,request});return gate.promise;};
 const pending=c.submit(c.form);await c.submit(c.form);
 assert.equal(c.calls.filter(r=>r.request?.method==='POST').length,1);assert.equal(c.form.elements.name.value,'旗舰型');
 gate.resolve({created:{model:true},model:{id:11}});await pending;assert.equal(c.closed,1);
 const failure=setup();await failure.run('catalogEntryDialog()');failure.api=async(url,request)=>{failure.calls.push({url,request});throw new Error('连接中断');};
 await assert.rejects(failure.submit(failure.form),/连接中断/);assert.equal(failure.closed,0);assert.equal(failure.form.elements.battery.value,'60.501');
 await assert.rejects(failure.submit(failure.form),/连接中断/);
 const writes=failure.calls.filter(r=>r.request?.method==='POST');assert.equal(writes[0].request.body.request_id,writes[1].request.body.request_id);
});

test('save and cancel callbacks are exclusive and submission rejects changed context',async()=>{
 const c=setup();c.result={created:{model:true},model:{id:12}};c.saved=[];c.cancelled=0;
 await c.run('catalogEntryDialog({onSaved:async result=>saved.push(result),onCancel:()=>cancelled++})');await c.submit(c.form);
 assert.equal(c.saved[0].model.id,12);assert.equal(c.cancelled,0);
 const cancelled=setup();cancelled.cancelled=0;await cancelled.run('catalogEntryDialog({onCancel:()=>cancelled++})');cancelled.closeModal();assert.equal(cancelled.cancelled,1);
 const moved=setup();await moved.run('catalogEntryDialog()');moved.storeContextVersion++;
 await assert.rejects(moved.submit(moved.form),/门店已切换/);assert.equal(moved.calls.filter(r=>r.request).length,0);
});

test('one form exposes searchable parent choices, inline names, and no internal code field',async()=>{
 const c=setup();await c.run('catalogEntryDialog()');
 assert.equal(c.title,'新增车型');assert.equal((c.html.match(/data-search-select/g)||[]).length,2);
 assert(c.html.includes('data-search-create'));assert(!c.html.includes('name="code"'));assert(c.html.includes('name="brand_name"'));assert(c.html.includes('name="series_name"'));
 assert.equal(c.labels.brand_name.hidden,true);assert.equal(c.form.elements.brand_name.disabled,true);
 c.form.elements.brand_id.value='new';c.run("catalogEntryUpdate(form,options,'brand_id')");
 assert.equal(c.labels.brand_name.hidden,false);assert.equal(c.form.elements.brand_name.required,true);assert.equal(c.form.elements.series_id.value,'new');
});
