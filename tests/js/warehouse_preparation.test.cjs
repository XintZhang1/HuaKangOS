'use strict';
// Actual warehouse preparation controller with synthetic transport and DOM only.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const rootPath=path.resolve(__dirname,'../..'),plain=x=>JSON.parse(JSON.stringify(x));
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
function fixture({purpose='procurement_receipt',count=1,role='inventory'}={}){
 const calls=[],listeners={},sections=new Map(),status={textContent:''},fields=[{isConnected:true,disabled:false,value:'1.251'},{isConnected:true,disabled:true}],footer={before(){}};
 const control=attrs=>({isConnected:true,disabled:false,attrs,hasAttribute:k=>attrs.includes(k),closest:s=>s==='button'?null:null});
 const open=control(['data-prep-open']);let root;
 function slot(bin='',qty=''){
  const selection={isConnected:true,disabled:false,value:bin},quantity={isConnected:true,disabled:false,value:qty};
  const row={selection,quantity,querySelector:s=>s==='[data-prep-bin]'?selection:quantity,remove(){const owner=[...sections.values()].find(section=>section.slots.includes(row));owner.slots.splice(owner.slots.indexOf(row),1);}};
  return row;
 }
 function section(id,bin='',qty=''){
  const totals={textContent:''},node={dataset:{prepItem:String(id)},slots:[slot(bin,qty)],totals};
  node.querySelectorAll=s=>s==='[data-prep-location]'?node.slots:s==='[data-prep-quantity]'?node.slots.map(s=>s.quantity):[];
  node.querySelector=s=>s==='[data-prep-total]'?totals:{insertAdjacentHTML:()=>node.slots.push(slot())};sections.set(Number(id),node);return node;
 }
 const body={hidden:true,set innerHTML(html){this.html=html;sections.clear();for(const match of html.matchAll(/data-prep-item="(\d+)"/g)){const part=html.slice(match.index).split('<div data-prep-item=')[0];section(Number(match[1]),part.match(/<option value="(\d+)" selected>/)?.[1]||'',part.match(/data-prep-quantity[^>]*value="([^"]*)"/)?.[1]||'');}},get innerHTML(){return this.html||'';}};
 root={isConnected:true,hidden:false,querySelector:s=>s==='[data-prep-status]'?status:s==='[data-prep-body]'?body:s==='[data-prep-open]'?open:sections.get(Number(s.match(/"(\d+)"/)?.[1])),addEventListener:(kind,fn)=>listeners['root-'+kind]=fn,closest:s=>s==='form'?form:null};
 const form={isConnected:true,querySelector:()=>footer,querySelectorAll:()=>[...fields,open,...[...sections.values()].flatMap(s=>s.slots.flatMap(t=>[t.selection,t.quantity]))],addEventListener:(kind,fn)=>listeners['form-'+kind]=fn};
 let currentVersion=5,epoch=1;
 const source={id:80,version:5,state:'receiving',facts:['original']},lines=Array.from({length:count},(_,i)=>({item_id:i+1,label:'物资'+(i+1),quantity_milli:1251}));
 const config={caseId:80,purpose,source,getVersion:()=>source.version,setVersion:v=>{source.version=v;},getLines:()=>lines,readSource:async()=>({...source,version:currentVersion})};
 const ctx={console,Map,Set,JSON,Number,Math,state:{user:{id:8,role}},storeContextVersion:epoch,document:{createElement:()=>root},E:v=>String(v),
  purchaseScaled:(s,n)=>{if(!/^\d+(\.\d{1,3})?$/.test(s))throw new Error('数量最多三位小数');const [a,b='']=s.split('.');return Number(a)*10**n+Number(b.padEnd(n,'0'));},whQty:n=>(n/1000).toFixed(3),
  requestKey:()=> 'synthetic-'+calls.length,requireStoreContext:v=>{if(v!==ctx.storeContextVersion)throw new Error('门店已切换');},
  procurementAll:async url=>url.includes('locations')?[{id:10,name:'甲库位',active:true,warehouse_id:20}]:[{id:20,name:'物资仓',active:true,warehouse_type:'materials'}],
  api:async(url,options)=>{calls.push({url,options});if(!options)return {purposes:[purpose],items:lines.map(l=>({id:l.item_id,enabled:true}))};currentVersion++;return {version:currentVersion};}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(rootPath,'web/warehouseprep.js'),'utf8'),ctx);
 const controller=ctx.mountWarehousePreparation(form,config);
 async function click(attr,id,slotIndex=0){const button=attr==='data-prep-open'?open:control([attr]);button.closest=s=>s==='button'?button:s==='[data-prep-item]'?sections.get(id):s==='[data-prep-location]'?sections.get(id).slots[slotIndex]:null;return listeners['root-click']({target:button});}
 function changed(inside=false){listeners['form-input']({target:{closest:()=>inside?root:null}});}
 return {ctx,config,source,lines,root,form,sections,fields,body,status,open,calls,listeners,controller,click,changed,slot,section,setServerVersion:v=>{currentVersion=v;}};
}
test('exact milli allocation preserves 1.251 across multiple bins and rejects missing/excess/duplicate/overprecision',()=>{
 const f=fixture();f.section(1,'10','1.000').slots.push(f.slot('11','0.251'));
 assert.deepEqual(plain(f.ctx.warehouseAllocationValues(f.root,f.lines)),[{item_id:1,quantity_milli:1251,locations:[{location_id:10,quantity_milli:1000},{location_id:11,quantity_milli:251}]}]);
 const second=f.sections.get(1).slots[1];second.quantity.value='0.250';assert.throws(()=>f.ctx.warehouseAllocationValues(f.root,f.lines),/还差 0.001/);second.quantity.value='0.252';assert.throws(()=>f.ctx.warehouseAllocationValues(f.root,f.lines),/超分配 0.001/);second.quantity.value='0.251';second.selection.value='10';assert.throws(()=>f.ctx.warehouseAllocationValues(f.root,f.lines),/同一库位/);second.selection.value='11';second.quantity.value='0.2511';assert.throws(()=>f.ctx.warehouseAllocationValues(f.root,f.lines),/最多三位/);
});
test('blank/zero location rows do not change quantity; negative and missing positive bin are rejected',()=>{
 const f=fixture();f.section(1,'10','1.251').slots.push(f.slot('',''),f.slot('','0'));assert.equal(f.ctx.warehouseAllocationValues(f.root,f.lines)[0].locations.length,1);
 const first=f.sections.get(1).slots[0];first.selection.value='';assert.throws(()=>f.ctx.warehouseAllocationValues(f.root,f.lines),/选择实际库位/);first.selection.value='10';first.quantity.value='-1';assert.throws(()=>f.ctx.warehouseAllocationValues(f.root,f.lines),/最多三位/);
});
test('only active material locations are shown, with warehouse names; duplicate original item batches stay separate',()=>{
 const f=fixture();const locations=[{id:1,name:'甲',warehouse_id:10,active:true},{id:2,name:'乙',warehouse_id:11,active:true},{id:3,name:'停用',warehouse_id:10,active:false}],warehouses=[{id:10,name:'配件库',active:true,warehouse_type:'materials'},{id:11,name:'车辆库',active:true,warehouse_type:'vehicles'}];
 assert.deepEqual(plain(f.ctx.warehouseLocationChoices(locations,warehouses)).map(l=>l.label),['配件库 · 甲']);assert.throws(()=>f.ctx.warehousePreparationLines([...f.lines,...f.lines]),/多个原批次/);
});
test('single bin prefill uses exact requested quantity; preparation alone updates version and does not call physical action',async()=>{
 const f=fixture();await f.click('data-prep-open');assert.equal(f.sections.get(1).slots[0].quantity.value,'1.251');await f.click('data-prep-save');await f.controller.assertReady();
 const sent=f.calls.filter(c=>c.options);assert.equal(sent.length,1);assert.equal(sent[0].url,'/api/warehouse/allocations/80');assert.equal(sent[0].options.body.version,5);assert.equal(sent[0].options.body.values.quantity_milli,1251);assert.equal(f.source.version,6);assert.match(f.status.textContent,/库位已保存/);assert.equal(f.fields[1].disabled,true);
});
test('issue signs are negative and return signs positive without changing split quantities',async()=>{
 for(const [purpose,sign]of [['repair_issue_v3',-1],['repair_return_v3',1]]){const f=fixture({purpose});await f.click('data-prep-open');await f.click('data-prep-save');const values=f.calls.find(c=>c.options).options.body.values;assert.equal(values.quantity_milli,1251*sign);assert.equal(values.locations[0].quantity_milli,1251);}
});
test('changing requested quantity invalidates saved preparation and requires exact new amount',async()=>{
 const f=fixture();await f.click('data-prep-open');await f.click('data-prep-save');f.lines[0].quantity_milli=2251;f.changed();assert.match(f.status.textContent,/数量已变化/);await assert.rejects(f.controller.assertReady(),/先分配并保存/);
 await f.click('data-prep-open');assert.equal(f.sections.get(1).slots[0].quantity.value,'2.251');await f.click('data-prep-save');await f.controller.assertReady();assert.equal(f.source.version,7);
});
test('source version conflict and nonversion business changes block before preparation writes',async()=>{
 for(const mutate of [f=>f.setServerVersion(6),f=>{f.config.readSource=async()=>({...f.source,state:'cancelled'});}]){const f=fixture();await f.click('data-prep-open');mutate(f);await f.click('data-prep-save');assert.equal(f.calls.filter(c=>c.options).length,0);assert.match(f.status.textContent,/关闭本表并刷新/);await assert.rejects(f.controller.assertReady(),/需核对/);}
});
test('async directory request cannot reopen old-store UI; main input changes cannot submit old requested amount',async()=>{
 const f=fixture(),pending=deferred();f.ctx.procurementAll=async()=>pending.promise;const opened=f.click('data-prep-open');await tick();f.ctx.storeContextVersion++;pending.resolve([]);await opened;assert.equal(f.body.innerHTML,'');await assert.rejects(f.controller.assertReady(),/门店已切换/);
 const g=fixture(),slow=deferred(),base=g.ctx.procurementAll;g.ctx.procurementAll=async url=>{await slow.promise;return base(url);};const opening=g.click('data-prep-open');await tick();g.lines[0]={...g.lines[0],quantity_milli:2251};slow.resolve();await opening;await g.click('data-prep-save');assert.equal(g.calls.filter(c=>c.options).length,0);assert.match(g.status.textContent,/本次数量已变化/);
});
test('partial definite save failure keeps successful CAS version but cannot submit physical action until all saves succeed',async()=>{
 const f=fixture({count:2});await f.click('data-prep-open');const api=f.ctx.api;let fail=true;
 f.ctx.api=async(url,options)=>{if(options?.body.values.item_id===2&&fail){const error=new Error('第二物资校验失败');error.status=422;throw error;}return api(url,options);};
 await f.click('data-prep-save');assert.equal(f.source.version,6);assert.match(f.status.textContent,/第二物资/);await assert.rejects(f.controller.assertReady(),/先分配并保存/);assert.equal(f.fields[0].disabled,false);assert.equal(f.fields[1].disabled,true);
 fail=false;await f.click('data-prep-save');await f.controller.assertReady();assert.equal(f.source.version,8);assert.deepEqual(f.calls.filter(c=>c.options).map(c=>c.options.body.version),[5,6,7]);
});
test('uncertain save blocks all retry and original submission; disabled controls are restored',async()=>{
 const f=fixture({count:2});await f.click('data-prep-open');const api=f.ctx.api;f.ctx.api=async(url,options)=>{if(options?.body.values.item_id===2)throw new Error('网络中断');return api(url,options);};
 await f.click('data-prep-save');assert.equal(f.source.version,6);assert.match(f.status.textContent,/保存结果需核对/);await assert.rejects(f.controller.assertReady(),/需核对/);const writes=f.calls.length;await f.click('data-prep-save');assert.equal(f.calls.length,writes);assert.equal(f.fields[0].disabled,false);assert.equal(f.fields[1].disabled,true);
});
test('while saving, controls and duplicate saves are blocked; closed form cannot receive late update',async()=>{
 const f=fixture();await f.click('data-prep-open');const api=f.ctx.api,pending=deferred();let posts=0;f.ctx.api=async(url,options)=>{if(options){posts++;await pending.promise;}return api(url,options);};
 const saving=f.click('data-prep-save');await tick();assert(f.fields[0].disabled);await f.click('data-prep-save');assert.equal(posts,1);await assert.rejects(f.controller.assertReady(),/正在保存/);f.form.isConnected=false;pending.resolve();await saving;assert.equal(f.source.version,5);
});
test('nonphysical role cannot mount warehouse controls',async()=>{const f=fixture({role:'finance'});await f.controller.assertReady();assert.equal(f.calls.length,0);assert.equal(f.listeners['root-click'],undefined);});
