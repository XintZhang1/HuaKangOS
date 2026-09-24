'use strict';
// Actual repair controllers; synthetic DOM and transport, never a business database.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..'),plain=x=>JSON.parse(JSON.stringify(x));
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {resolve,reject,promise};}
function fixture(){
 const row={id:80,version:9,amount_cents:15001,data:{quote_id:12},actions:['allocate'],quotes:[],stock:[]},calls=[],handlers={};
 const sections={},addButtons={},elements={},total={textContent:''},error={textContent:''};
 for(const k of ['customer','insurer','manufacturer','internal']){
  const status={textContent:'',append(button){this.retry=button;}},section={hidden:k!=='customer',disabled:k!=='customer',dataset:{},querySelector:()=>status};sections[k]=section;addButtons[k]={hidden:false};
  for(const name of ['amount_'+k,'due_'+k,'payer_'+k])elements[name]={value:name.startsWith('due_')?'2026-09-24':'',disabled:false,required:false,innerHTML:'',closest:()=>section};
 }
 elements.internal_name={value:''};elements.labor_cost={value:'0'};elements.evidence={value:'44'};
 const form={elements,isConnected:true,addEventListener:(k,fn)=>handlers[k]=fn,querySelector:s=>s==='[data-repair-allocation-total]'?total:s==='.formerror'?error:s.startsWith('[data-repair-add-payer=')?addButtons[s.split('"')[1]]:sections[s.split('"')[1]]};
 const ctx={console,Intl,Date,Number,Math,Set,Map,JSON,Promise,URLSearchParams,setTimeout:()=>1,
  document:{addEventListener(){},createElement:()=>({dataset:{}})},window:{addEventListener(){}},
  F:(key,label,type,required,options)=>({key,label,type,required,options}),closeModal:()=>{ctx.closed=true;},render:async()=>{ctx.rendered=true;},
  caseFilePickerHTML:(name,id,files)=>{ctx.picker={name,id,files};return '<select name="evidence"></select><button data-act="inline-file-open">上传文件</button>';},
  modal:(title,html,save)=>{ctx.opened={title,html,save};return {querySelector:()=>form};},
  api:async(url,options)=>{calls.push({url,options});return {id:80,version:9,children:[],files:[]};}};
 vm.createContext(ctx);const app=fs.readFileSync(path.join(root,'web/app.js'),'utf8');vm.runInContext(app.slice(0,app.indexOf('async function api(')),ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'web/repair.js'),'utf8'),ctx);ctx.requestKey=()=> 'repair-test-request';ctx.row=row;
 vm.runInContext("state.user={id:6,role:'manager'};state.store='1';state.route='repair-orders/80';state.repairOrder=row;globalThis.s=state;",ctx);
 async function click(type,kind){const button={disabled:false,dataset:kind?{[type]:kind}:{},hasAttribute:n=>type==='all'&&n==='data-repair-customer-all'};return handlers.click({target:{closest:()=>button}});}
 return {ctx,row,calls,form,elements,sections,total,error,handlers,click};
}
test('ordinary repair opens without insurer/manufacturer requests or preselected customer amount and permits inline upload',async()=>{
 const f=fixture();await f.ctx.repairAllocate();assert.deepEqual(f.calls.map(c=>c.url),['/api/flow/cases/80']);assert.equal(f.elements.amount_customer.value,'');assert.match(f.ctx.opened.html,/data-act="inline-file-open"/);assert.equal(f.ctx.picker.id,80);assert.equal(f.ctx.opened.title,'确认费用承担');assert.match(f.total.textContent,/尚需分配 150.01/);
 await f.click('all');assert.equal(f.elements.amount_customer.value,'150.01');assert.match(f.total.textContent,/已分配完整/);
 await f.ctx.opened.save(f.form);const sent=f.calls.at(-1).options.body;assert.equal(sent.version,9);assert.equal(sent.request_id,'repair-test-request');assert.deepEqual(plain(sent.values),{allocations:[{payer_type:'customer',amount_cents:15001,due_date:'2026-09-24'}],labor_cost_cents:0,evidence_id:44});assert(f.ctx.closed&&f.ctx.rendered);
});
test('zero, decimal zero, blank and disabled payer amounts create no allocation rows or required metadata',()=>{
 const f=fixture();f.elements.amount_customer.value='150.01';f.sections.insurer.disabled=false;f.sections.manufacturer.disabled=false;f.sections.internal.disabled=false;
 f.elements.amount_insurer.value='0';f.elements.amount_manufacturer.value='0.00';f.elements.amount_internal.value=' ';f.elements.due_insurer.value='';
 f.ctx.repairAllocationUpdate(f.form,15001);assert.equal(f.elements.due_insurer.required,false);assert.equal(f.elements.payer_insurer.required,false);
 assert.equal(f.ctx.repairAllocationValues(f.form,15001).length,1);f.sections.insurer.disabled=true;f.elements.amount_insurer.value='19.00';assert.equal(f.ctx.repairAllocationValues(f.form,15001).length,1);
});
test('exact fen total is enforced with actionable difference; malformed and overprecise amounts fail before transport',()=>{
 const f=fixture();f.elements.amount_customer.value='150';assert.throws(()=>f.ctx.repairAllocationValues(f.form,15001),/还需分配 0.01/);
 f.elements.amount_customer.value='150.02';assert.throws(()=>f.ctx.repairAllocationValues(f.form,15001),/已超出 0.01/);
 for(const v of ['-1','150.001','1e2','abc']){f.elements.amount_customer.value=v;assert.throws(()=>f.ctx.repairAllocationValues(f.form,15001),/最多两位/);}assert.equal(f.calls.length,0);
});
test('positive external and internal payers retain IDs, dates, names and require their own metadata',()=>{
 const f=fixture();f.elements.amount_customer.value='100.01';f.sections.insurer.disabled=false;f.elements.amount_insurer.value='50';assert.throws(()=>f.ctx.repairAllocationValues(f.form,15001),/请选择保险公司/);
 f.elements.payer_insurer.value='87';assert.deepEqual(plain(f.ctx.repairAllocationValues(f.form,15001))[1],{payer_type:'insurer',amount_cents:5000,due_date:'2026-09-24',payer_id:87});
 f.elements.amount_insurer.value='0';f.sections.internal.disabled=false;f.elements.amount_internal.value='50';assert.throws(()=>f.ctx.repairAllocationValues(f.form,15001),/内部承担单位/);f.elements.internal_name.value=' 门店售后部 ';assert.equal(f.ctx.repairAllocationValues(f.form,15001)[1].payer_name,'门店售后部');
});
test('payer directory is loaded only on reveal, supports retry and never overwrites hand-entered amounts',async()=>{
 const f=fixture();await f.ctx.repairAllocate();const pending=deferred();f.ctx.api=async()=>pending.promise;
 const opened=f.click('repairAddPayer','insurer');f.elements.amount_customer.value='100.01';f.elements.amount_insurer.value='50';pending.resolve({items:[{id:87,name:'甲保险'}],total:1});await opened;
 assert.equal(f.elements.amount_insurer.value,'50');assert.equal(f.elements.amount_customer.value,'100.01');assert.match(f.elements.payer_insurer.innerHTML,/value="87"/);
 await f.click('repairRemovePayer','insurer');assert.equal(f.sections.insurer.hidden,true);assert.equal(f.elements.amount_insurer.value,'');
 f.ctx.api=async()=>{throw new Error('读取失败');};await f.click('repairAddPayer','manufacturer');assert.match(f.sections.manufacturer.querySelector().textContent,/读取失败/);assert.equal(f.sections.manufacturer.dataset.loaded,undefined);
 f.ctx.api=async()=>({items:[{id:1,name:'厂商',active:true,category:'厂家'},{id:2,name:'其他',active:true,category:'其他'}],total:2});await f.click('repairLoadPayer','manufacturer');assert.match(f.elements.payer_manufacturer.innerHTML,/厂商/);assert(!f.elements.payer_manufacturer.innerHTML.includes('其他'));
});
test('store switch during directory loading cannot display old-store data or submit original repair',async()=>{
 const f=fixture();await f.ctx.repairAllocate();const pending=deferred();f.ctx.api=async()=>pending.promise;
 const opened=f.click('repairAddPayer','insurer');f.ctx.s.store='2';pending.resolve({items:[{id:87,name:'原店资料'}],total:1});await opened;assert(!f.elements.payer_insurer.innerHTML.includes('原店资料'));await assert.rejects(f.ctx.opened.save(f.form),/页面已变化/);
});
test('late details and stale versions do not open a dialog',async()=>{
 const f=fixture(),pending=deferred();f.ctx.api=()=>pending.promise;const opened=f.ctx.repairAllocate();f.ctx.s.store='2';pending.resolve({version:9,files:[],children:[]});await assert.rejects(opened,/页面已变化/);assert.equal(f.ctx.opened,undefined);
 const g=fixture();g.ctx.api=async()=>({version:10,files:[],children:[]});await assert.rejects(g.ctx.repairAllocate(),/本单已更新/);assert.equal(g.ctx.opened,undefined);
});
function claim(overrides={}){return {id:91,source_id:80,source_version:9,source_quote_id:12,state:'working',phase:'ready',phase_label:'已取得核价结果',number:'CLAIM-1',order:{party_type:'insurer',party_name:'甲保险',payment_route:'repair_receivable'},data:{assessment_id:1,result_id:2},assessments:[{id:1,quote_id:12,amount_cents:6000}],results:[{id:2,assessment_id:1,outcome:'partial',amount_cents:5000}],...overrides};}
test('current noncustomer claim is shown with final amount and cannot be replaced by customer-full shortcut',async()=>{
 const f=fixture();f.ctx.api=async url=>url.includes('/claims/')?claim():{id:80,version:9,files:[],children:[{id:91,kind:'claim',flow_version:2,state:'working'}]};await f.ctx.repairAllocate();assert.match(f.ctx.opened.html,/甲保险 · 核赔金额 50.00 元/);assert.match(f.ctx.opened.html,/data-repair-customer-all disabled/);await f.click('all');assert.equal(f.elements.amount_customer.value,'');
});
test('pending/current-quote mismatch/supplement cannot present an approved amount; zero rejection and reimbursement remain distinct',()=>{
 const f=fixture();for(const c of [claim({phase:'approval'}),claim({source_quote_id:10}),claim({results:[{id:2,assessment_id:1,outcome:'need_documents',amount_cents:0}]})])assert.equal(f.ctx.repairAllocationClaims(f.row,[c])[0].amount,null);
 assert.equal(f.ctx.repairAllocationClaims(f.row,[claim({results:[{id:2,assessment_id:1,outcome:'rejected',amount_cents:0}]})])[0].amount,0);
 assert.equal(f.ctx.repairAllocationClaims(f.row,[claim({order:{payment_route:'customer_via_store'}})]).length,0);
});
test('zero total permits no payer rows; unchanged internal-only and rework paths retain original responsibility',async()=>{
 const f=fixture();f.row.amount_cents=0;assert.deepEqual(plain(f.ctx.repairAllocationValues(f.form,0)),[]);
 f.row.amount_cents=15001;f.row.service_intake={internal_only:true,internal_name:'原责任门店'};let sent;f.ctx.formDialog=async(title,fields,initial,save)=>{await save({labor_cost:'0',evidence_id:44});};f.ctx.api=async(url,options)=>{sent=options.body;return {};};await f.ctx.repairAllocate();assert.equal(sent.values.allocations[0].payer_name,'原责任门店');assert.equal(sent.values.allocations[0].amount_cents,15001);
 f.row.service_intake={rework_extension:true};f.ctx.reworkAllocate=async row=>{assert.equal(row,f.row);return 'original-rework';};assert.equal(await f.ctx.repairAllocate(),'original-rework');
});
test('warehouse issue hook uses selected authorised item and updates only captured version before original POST',async()=>{
 const f=fixture();f.ctx.s.user.role='inventory';f.row.actions=['issue'];f.row.quotes=[{id:12,revision:1,lines:[{kind:'part',item_id:3,line_key:'part-one',code:'A',name:'配件甲',quantity_milli:5000,issued_milli:0},{kind:'part',item_id:8,line_key:'part-two',code:'B',name:'配件乙',quantity_milli:2500,issued_milli:0}]}];let sent;
 f.ctx.api=async(url,options)=>{sent=options.body;return {};};
 f.ctx.formDialog=async(title,fields,initial,save,options)=>{const label=fields[0].options[1],form={elements:{line_label:{value:label},quantity:{value:'1.250'}}};assert.equal(options.warehouse.purpose,'repair_issue_v3');assert.deepEqual(plain(options.warehouse.getLines(form)),[{item_id:8,quantity_milli:1250,label:'B · 配件乙'}]);options.warehouse.setVersion(10);await save({line_label:label,quantity:'1.250',evidence_id:44});};
 await f.ctx.repairAction('issue');assert.equal(sent.version,10);assert.equal(sent.values.line_key,'part-two');assert.equal(sent.values.quantity_milli,1250);
});
test('warehouse return hook binds original quote item and does not expose controls to nonphysical roles',()=>{
 const f=fixture();f.row.quotes=[{id:11,lines:[{kind:'part',item_id:3,line_key:'old',code:'A',name:'原配件'}]},{id:12,lines:[{kind:'part',item_id:8,line_key:'old',code:'B',name:'新配件'}]}];f.row.stock=[{id:22,quote_id:11,line_key:'old',returnable_milli:1000}];
 assert.equal(f.ctx.repairWarehousePreparation(f.row,'return_material',[],[]),undefined);f.ctx.s.user.role='inventory';const config=f.ctx.repairWarehousePreparation(f.row,'return_material',[],[]),form={elements:{original_id:{value:'22'},quantity:{value:'0.500'}}};assert.equal(config.purpose,'repair_return_v3');assert.deepEqual(plain(config.getLines(form)),[{item_id:3,quantity_milli:500,label:'A · 原配件'}]);form.elements.original_id.value='99';assert.throws(()=>config.getLines(form),/选择本次领退/);form.elements.original_id.value='22';form.elements.quantity.value='0';assert.throws(()=>config.getLines(form),/实际数量/);
});
