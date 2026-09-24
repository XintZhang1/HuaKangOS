'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function sandbox(){
 const ctx={console,Set,URLSearchParams,Number,Event,document:{addEventListener(){},querySelector:()=>null},
 state:{claimOrder:{id:4,version:2,source_version:3,actions:['pass_receive','customer_return','party_return','resolution_apply'],order:{payment_route:'customer_via_store'},cash:[{id:666,purpose:'pass_receive',remaining_cents:999999}],return_plans:[{id:7,selections:[{original_id:666,amount_cents:999999}]}]},row:{files:[]}},
 requestKey:()=> 'fixed-request-key',money:n=>(n/100).toFixed(2),E:value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
 F:(key,label,type='text',required=true,options)=>({key,label,type,required,options}),b:(act,label,attrs='',style='')=>`<button data-act="${act}" ${attrs}>${label}</button>`,
 modal:(title,html,save)=>{ctx.modal={title,html,save};},formDialog:async(title,fields,initial,save,options)=>{ctx.dialog={title,fields,initial,save,options};},
 caseFilePickerHTML:(name,id)=>`<select name="${name}" required data-file-case="${id}"></select>`,repairScaled:(value,digits)=>Number(value)*10**digits,
 closeModal(){},render:async()=>{},day:()=> '2026-09-24',calls:[],api:async(url,options)=>{ctx.calls.push({url,options});return ctx.response;}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/claims.js'),'utf8'),ctx);ctx.run=code=>vm.runInContext(code,ctx);return ctx;
}
test('missing payment explains the exact next action on the same claim',async()=>{
 const c=sandbox();c.response={can_continue:false,items:[],version:5,source_version:6,message:'尚未登记报销款到店。',next_action:'pass_receive'};await c.run("claimAction('pass_pay')");assert.match(c.modal.html,/尚未登记报销款到店/);assert.match(c.modal.html,/data-key="pass_receive"/);assert(!c.dialog);assert.equal(c.calls[0].url,'/api/claims/4/options/pass_pay');
});
test('third-party return links customer receipt to the exact same return plan',async()=>{
 const c=sandbox();c.response={can_continue:false,items:[],version:5,source_version:6,message:'先登记本方案客户退款。',next_action:'customer_return',next_plan_id:7};await c.run("claimAction('party_return',7)");assert.match(c.modal.html,/data-key="customer_return" data-plan="7"/);assert.equal(c.calls[0].url,'/api/claims/4/options/party_return?plan_id=7');
});
test('mixed plan uses only action-specific server candidates with fixed IDs and source account',async()=>{
 const c=sandbox();c.response={can_continue:true,version:5,source_version:6,items:[{id:18,purpose:'pass_pay',reference:'原凭证A',business_date:'2026-09-01',account_id:9,account_name:'原银行',remaining_cents:600}]};await c.run("claimAction('customer_return',7)");
 const field=c.dialog.fields.find(x=>x.key==='original');assert(field.searchable);assert.equal(field.options.length,1);assert.equal(field.options[0].value,'18');assert.match(field.options[0].label,/原凭证A.*2026-09-01.*原银行.*6\.00/);assert.equal(c.dialog.initial.account_id,9);
 await c.dialog.save({original:'18',amount:'4.00',account_id:9,reference:'本次凭证',evidence_id:88});const sent=c.calls.at(-1).options.body;assert.equal(sent.version,5);assert.equal(sent.source_version,6);assert.equal(sent.values.original_id,18);assert.equal(sent.values.plan_id,7);assert.equal(sent.values.amount_cents,400);assert(!('original' in sent.values));
});
test('displayed remaining capacity rejects excessive amount before posting',async()=>{
 const c=sandbox();c.response={can_continue:true,version:5,source_version:6,items:[{id:2,reference:'原款',business_date:'2026-09-01',remaining_cents:300}]};await c.run("claimAction('unused_refund',7)");assert.throws(()=>c.dialog.save({original:'2',amount:'3.01'}),/超过.*可办理/);assert.equal(c.calls.length,1);
});
test('zero-refund resolution points to application without pretending it was applied',async()=>{
 const c=sandbox();c.response={can_continue:false,items:[],message:'本方案无需退款，请办理生效并上传凭据。',next_action:'resolution_apply'};await c.run("claimAction('thirdparty_refund')");assert.match(c.modal.html,/无需退款/);assert.match(c.modal.html,/data-key="resolution_apply"/);assert.equal(c.calls.length,1);
 await c.run("claimAction('resolution_apply')");assert(c.dialog.fields.some(x=>x.key==='evidence_id'&&x.required));assert.equal(c.calls.length,1);
});
test('return request displays true remaining amounts and no raw cash-balance fallback',async()=>{
 const c=sandbox();c.response={can_continue:true,version:5,source_version:6,items:[{id:21,purpose:'pass_receive',reference:'第三方原款',business_date:'2026-09-01',remaining_cents:400}]};await c.run("claimSelectionDialog('return_plan')");assert.match(c.modal.html,/未转付原款/);assert.match(c.modal.html,/本次最多 4\.00 元/);assert.match(c.modal.html,/data-id="21"/);assert(!c.modal.html.includes('9999.99'));assert(!c.modal.html.includes('data-id="666"'));
});
