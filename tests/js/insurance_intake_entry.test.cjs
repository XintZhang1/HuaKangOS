'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function deferred(){let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};}
function control(value=''){
 let html='';const el={value,disabled:false,checked:false,listeners:{},addEventListener(name,fn){this.listeners[name]=fn;},dispatchEvent(event){return this.listeners[event.type]?.(event);}};
 Object.defineProperty(el,'innerHTML',{get:()=>html,set:v=>{html=v;el.value='';}});return el;
}
function setup(file='insuranceorders.js'){
 const elements={};for(const name of ['customer','vehicle','source','previous','renewal','blocking','due_date','reason','mode','starts_at','ends_at','resource_id','customer_vehicle_id','preset_id','insurer','payee','payee_reference'])elements[name]=control();
 elements.due_date.value='2026-09-24';elements.reason.value='为客户办理保险';
 const status={textContent:''},submitButton={disabled:true},addLine={addEventListener(){}};
 const form={elements,isConnected:true,listeners:{},addEventListener(name,fn){this.listeners[name]=fn;},querySelector:selector=>selector==='[data-insurance-status]'?status:selector==='[type=submit]'?submitButton:null};
 const dialog={open:true,querySelector:selector=>selector==='form'?form:selector==='[data-insurance-add]'?addLine:null};
 const c={console,Promise,URLSearchParams,Date,Number,Map,Event:class{constructor(type){this.type=type;}},state:{user:{id:9,role:'service'},store:'1'},storeContextVersion:1,
  document:{addEventListener(){}},E:value=>String(value).replaceAll('<','&lt;').replaceAll('"','&quot;'),b:()=>'',day:()=> '2026-09-24',requestKey:()=> 'single-request-1234567890',
  registerLiveChoiceLoader:(target,loader)=>target.loader=loader,calls:[],modals:0,closed:0,form,status,submitButton,dialog,
  api:async()=>({customers:[],vehicles:[],sources:[],policies:[],renewals:[],resources:[],presets:[]}),
  modal:(title,html,submit)=>{c.title=title;c.html=html;c.submit=submit;c.modals++;return dialog;},closeModal:()=>{c.closed++;dialog.open=false;},go:route=>c.route=route,render:async()=>{}};
 vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web',file),'utf8'),c);c.run=js=>vm.runInContext(js,c);return c;
}
function catalog(customerId){return {customers:[{id:customerId,name:'客户'+customerId,phone:'1380000000'+customerId}],total:1,
 vehicles:[{id:customerId*10,customer_id:customerId,vin:'TESTVIN'+customerId,plate:'测试'+customerId}],
 sources:[{id:customerId*100,customer_id:customerId,number:'ORDER'+customerId,version:customerId+2}],
 policies:[{id:customerId*1000,policy_number:'POLICY'+customerId,vin:'TESTVIN'+customerId}],
 renewals:[{id:customerId*10000,customer_id:customerId,title:'续保'+customerId,version:customerId+3}]};}

test('insurance has one searchable customer field and uses scoped phone search API',async()=>{
 const c=setup();c.api=async(url,request)=>{c.calls.push({url,request});return catalog(1);};await c.run('insuranceOrderNew()');
 assert.equal(c.modals,1);assert(!c.html.includes('data-insurance-search'));assert(!c.html.includes('下一步'));assert(c.html.includes('data-search-placeholder="姓名或手机号"'));
 const found=await c.form.elements.customer.loader('138 00');assert.equal(c.calls.at(-1).url,'/api/insurance-orders/catalog?q=138%2000');
 assert.equal(found.items[0].id,1);assert(found.items[0].label.includes('13800000001'));
});

test('late customer details cannot overwrite a newer selection or its linked versions',async()=>{
 const c=setup(),one=deferred(),two=deferred();c.api=async(url,request)=>{
  c.calls.push({url,request});if(request)return {id:77};if(url.endsWith('customer_id=1'))return one.promise;if(url.endsWith('customer_id=2'))return two.promise;return catalog(1);
 };await c.run('insuranceOrderNew()');const e=c.form.elements;
 e.customer.value='1';const first=e.customer.listeners.change();e.customer.value='2';const second=e.customer.listeners.change();
 two.resolve(catalog(2));await second;one.resolve(catalog(1));await first;
 assert(e.vehicle.innerHTML.includes('TESTVIN2'));assert(!e.vehicle.innerHTML.includes('TESTVIN1'));assert.equal(e.vehicle.value,'20');
 e.source.value='200';e.previous.value='2000';e.renewal.value='20000';await c.submit(c.form);
 const posted=c.calls.find(r=>r.request)?.request.body;
 assert.equal(posted.customer_id,2);assert.equal(posted.customer_vehicle_id,20);assert.equal(posted.source_version,4);assert.equal(posted.renewal_version,5);assert.equal(c.route,'insurance-orders/77');
});

test('editing customer clears previous vehicle and prevents submitting stale customer data',async()=>{
 const c=setup(),pending=deferred();c.api=async url=>url.endsWith('customer_id=1')?pending.promise:catalog(1);await c.run('insuranceOrderNew()');
 const e=c.form.elements;e.customer.value='1';const selection=e.customer.listeners.change();e.customer.value='';await e.customer.listeners.change();
 pending.resolve(catalog(1));await selection;assert.equal(e.vehicle.value,'');assert.equal(e.vehicle.disabled,true);assert.equal(c.submitButton.disabled,true);
 await assert.rejects(c.submit(c.form),/请选择客户/);
});

test('insurance ignores catalogue after store switch and rejects old form submission',async()=>{
 const c=setup(),gate=deferred();c.api=()=>gate.promise;const opening=c.run('insuranceOrderNew()');c.state.store='2';gate.resolve(catalog(1));await opening;assert.equal(c.modals,0);
 const existing=setup();existing.api=async()=>catalog(1);await existing.run('insuranceOrderNew()');existing.storeContextVersion++;
 await assert.rejects(existing.submit(existing.form),/门店已切换/);assert.equal(existing.closed,0);
});

test('insurance requires real vehicle/source IDs and cannot submit stale lookup identifiers',()=>{
 const c=setup();c.catalog=catalog(1);const e=c.form.elements;e.customer.value='1';e.vehicle.value='999';
 assert.throws(()=>c.run("insuranceEntryValues(form,catalog,'same-request-123456')"),/请选择客户车辆/);
 e.vehicle.value='10';e.source.value='999';assert.throws(()=>c.run("insuranceEntryValues(form,catalog,'same-request-123456')"),/关联资料/);
 e.source.value='';e.blocking.checked=true;assert.throws(()=>c.run("insuranceEntryValues(form,catalog,'same-request-123456')"),/选择销售单/);
});

test('changing insurer never carries another company payee; returning restores that company draft',async()=>{
 const c=setup();c.state.insuranceOrder={quote:{insurer_id:1,insurer_snapshot:{account_name:'第一公司账户',account_reference:'FIRST-REF'},expected_commission_cents:0,lines:[]}};
 c.state.insuranceCatalog={insurers:[{id:1,name:'第一公司',license_number:'ONE'},{id:2,name:'第二公司',license_number:'TWO'}]};
 const e=c.form.elements;e.insurer.value='1';e.payee.value='第一公司账户';e.payee_reference.value='FIRST-REF';await c.run('insuranceQuote()');
 e.insurer.value='2';e.insurer.listeners.change();assert.equal(e.payee.value,'');assert.equal(e.payee_reference.value,'');
 e.payee.value='第二公司自填账户';e.payee_reference.value='SECOND-REF';e.insurer.value='1';e.insurer.listeners.change();assert.equal(e.payee.value,'第一公司账户');
 e.insurer.value='2';e.insurer.listeners.change();assert.equal(e.payee.value,'第二公司自填账户');assert.equal(e.payee_reference.value,'SECOND-REF');
});

test('walk-in uses current default start and keeps one-hour default end, without recording arrival',()=>{
 const c=setup('serviceintake.js'),e=c.form.elements;c.edited={starts_at:false,ends_at:false};c.now=Date.parse('2026-09-24T08:16:00Z');e.mode.value='walk_in';
 c.run('intakeDefaultTimes(form,edited,now)');assert.equal(new Date(e.starts_at.value).getTime(),c.now);assert.equal(new Date(e.ends_at.value)-new Date(e.starts_at.value),3600000);
 e.mode.value='appointment';c.run('intakeDefaultTimes(form,edited,now)');assert.equal(new Date(e.starts_at.value).getTime(),c.now+3600000);
 assert.equal(c.calls.length,0);assert.equal(c.state.intakeRecord,undefined);
});

test('manual start or end remains unchanged when reception mode changes',()=>{
 const c=setup('serviceintake.js'),e=c.form.elements;c.edited={starts_at:true,ends_at:true};c.now=Date.parse('2026-09-24T08:16:00Z');
 e.mode.value='walk_in';e.starts_at.value='2026-09-24T17:30';e.ends_at.value='2026-09-24T18:45';c.run('intakeDefaultTimes(form,edited,now)');
 assert.equal(e.starts_at.value,'2026-09-24T17:30');assert.equal(e.ends_at.value,'2026-09-24T18:45');
 c.edited.ends_at=false;c.run('intakeDefaultTimes(form,edited,now)');assert.equal(e.starts_at.value,'2026-09-24T17:30');assert.equal(e.ends_at.value,'2026-09-24T18:30');
});

test('intake ignores late store response and keeps appointment creation separate from actual arrival',async()=>{
 const late=setup('serviceintake.js'),gate=deferred();late.api=()=>gate.promise;const opening=late.run('intakeBook()');late.storeContextVersion++;gate.resolve({});await opening;assert.equal(late.modals,0);
 const c=setup('serviceintake.js');c.api=async(url,request)=>{c.calls.push({url,request});return request?{id:17}:{vehicles:[],resources:[],presets:[]};};await c.run('intakeBook()');
 const e=c.form.elements;e.resource_id.value='4';e.customer_vehicle_id.value='6';e.starts_at.value='2026-09-24T16:20';e.ends_at.value='2026-09-24T17:20';e.mode.value='walk_in';
 await c.submit(c.form);const write=c.calls.find(r=>r.request);assert.equal(write.url,'/api/service-intake/appointments');assert.equal(write.request.body.mode,'walk_in');assert(!('arrived_at' in write.request.body));
 assert.equal(c.calls.filter(r=>r.request).length,1);assert.equal(c.route,'service-intake/appointments/17');
});
