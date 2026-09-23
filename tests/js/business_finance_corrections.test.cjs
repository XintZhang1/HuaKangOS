'use strict';
// Real UI functions with synthetic transport; these do not assert browser networking.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..');
function sandbox(){
 const ctx={console,Intl,Date,Number,Math,Set,JSON,Promise,URLSearchParams,
  document:{cookie:'',addEventListener:()=>{},querySelector:()=>({}),querySelectorAll:()=>[]},window:{addEventListener:()=>{}},setTimeout:()=>1,
  F:(name,label,type,required,options)=>({name,label,type,required,options}),requestKey:()=> 'synthetic-request-key-1234',go:route=>ctx.route=route};
 vm.createContext(ctx);
 const app=fs.readFileSync(path.join(root,'web/app.js'),'utf8');vm.runInContext(app.slice(0,app.indexOf('async function api(')),ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'web/group.js'),'utf8'),ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'web/businessfinance.js'),'utf8'),ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'web/rechargebundles.js'),'utf8'),ctx);
 ctx.requestKey=()=> 'synthetic-request-key-1234';
 vm.runInContext("state.user={id:2,role:'finance'};state.store='1';state.businessFinanceCustomer={customerId:7,sources:[],advances:[]};globalThis.s=state;",ctx);
 return ctx;
}
const original={cash_id:12,business_date:'2026-09-22',account:'本店收款账户',reference:'CORRECT-1',amount_cents:1000,source_version:4,source_kind:'advance',sources:[{case_id:8,number:'HK-001',amount_cents:1000}]};
test('stored zero correction sends zero and omits replacement account without invoking positive parser',async()=>{
 const ctx=sandbox();let submitted;
 ctx.api=async(p,o)=>{if(!o)return {items:[original]};submitted=o.body;return {case:{id:20}};};
 ctx.formDialog=async(title,fields,initial,submit,opts)=>{
  assert(title.includes('误记更正'));assert(opts.notice.includes('不登记实际退款'));
  assert.equal(fields.find(f=>f.name==='account_id').required,false);
  await submit({original:'2026-09-22 · 本店收款账户 · CORRECT-1 · 10.00元',amount:'0',reason:'银行确认完全误记'});
 };
 await vm.runInContext("businessFinanceCreate('stored_correction')",ctx);
 assert.equal(submitted.purpose,'stored_correction');assert.equal(submitted.values.amount_cents,0);
 assert.equal(submitted.values.source_version,4);assert.equal(submitted.values.original_cash_id,12);
 assert(!('account_id' in submitted.values));assert(!('allocations' in submitted.values));
});
test('ordinary zero correction preserves empty allocation rather than inventing replacement',async()=>{
 const ctx=sandbox();let submitted;ctx.api=async(p,o)=>{if(!o)return {items:[{...original,source_kind:undefined}]};submitted=o.body;return {case:{id:20}};};
 ctx.formDialog=async(t,f,i,submit)=>submit({original:'2026-09-22 · 本店收款账户 · CORRECT-1 · 10.00元',allocation_8:'0',reason:'重复录入并未到账'});
 await vm.runInContext("businessFinanceCreate('correction')",ctx);
 assert.equal(submitted.values.amount_cents,0);assert.equal(submitted.values.allocations.length,0);assert(!('reference' in submitted.values));
});

test('partial refund correction sends gross original but allocates remaining net only',async()=>{
 const ctx=sandbox();let submitted;ctx.api=async(p,o)=>{if(!o)return {items:[{...original,source_kind:undefined,refunded_cents:200,net_amount_cents:800}]};submitted=o.body;return {case:{id:20}};};
 ctx.formDialog=async(t,fields,i,submit,opts)=>{
  assert(opts.notice.includes('系统自动加回已退款'));assert(fields.find(f=>f.name==='allocation_8').label.includes('剩余分配'));
  await submit({original:'2026-09-22 · 本店收款账户 · CORRECT-1 · 10.00元 · 已实退2.00元，剩余8.00元',allocation_8:'3.00',account_id:9,reference:'NET-ONLY',reason:'正确总入款5元其中已实退2元'});
 };
 await vm.runInContext("businessFinanceCreate('correction')",ctx);
 assert.equal(submitted.values.amount_cents,500);assert.equal(submitted.values.allocations[0].amount_cents,300);
 assert.equal(submitted.values.allocation_basis,'remaining_after_refunds');
});

test('zero remaining allocation still retains positive already refunded original cash',async()=>{
 const ctx=sandbox();let submitted;ctx.api=async(p,o)=>{if(!o)return {items:[{...original,source_kind:undefined,refunded_cents:200,net_amount_cents:800}]};submitted=o.body;return {case:{id:20}};};
 ctx.formDialog=async(t,f,i,submit)=>submit({original:'2026-09-22 · 本店收款账户 · CORRECT-1 · 10.00元 · 已实退2.00元，剩余8.00元',allocation_8:'0',account_id:9,reference:'REFUNDED-ONLY',reason:'保留原已实退2元'});
 await vm.runInContext("businessFinanceCreate('correction')",ctx);
 assert.equal(submitted.values.amount_cents,200);assert.equal(submitted.values.allocations.length,0);assert.equal(submitted.values.account_id,9);
});
test('positive stored correction freezes explicitly selected source version and account',async()=>{
 const ctx=sandbox();let submitted;ctx.api=async(p,o)=>{if(!o)return {items:[original]};submitted=o.body;return {case:{id:20}};};
 ctx.formDialog=async(t,f,i,submit)=>submit({original:'2026-09-22 · 本店收款账户 · CORRECT-1 · 10.00元',amount:'7.25',account_id:9,reference:'NEW-1',actual_business_date:'2026-09-21',reason:'按原到账凭证复核'});
 await vm.runInContext("businessFinanceCreate('stored_correction')",ctx);
 assert.equal(submitted.values.amount_cents,725);assert.equal(submitted.values.account_id,9);assert.equal(submitted.values.actual_business_date,'2026-09-21');
});
test('supplier target correction sends original receivable and current source version',async()=>{
 const ctx=sandbox();let submitted;ctx.s.businessFinanceOrder={case:{id:22,version:6},return_target:{receivable_id:4,target_cents:800,received_cents:100}};
 ctx.api=async(p,o)=>{submitted=o.body;return {case:{id:23}};};ctx.formDialog=async(t,f,i,submit)=>submit({amount:'1.00',reason:'双方核对追加应退目标'});
 await vm.runInContext("businessFinanceCreate('other_return_adjust')",ctx);
 assert.equal(submitted.customer_id,null);assert.equal(submitted.values.receivable_id,4);assert.equal(submitted.values.source_version,6);assert.equal(submitted.values.amount_cents,100);
});
test('amount parser rejects fractions beyond fen and negative correction input',()=>{
 const ctx=sandbox();assert.equal(vm.runInContext("businessFinanceZero('0.00')",ctx),0);
 for(const v of ['1.001','-1','NaN'])assert.throws(()=>vm.runInContext(`businessFinanceZero(${JSON.stringify(v)})`,ctx));
});
test('member refund dialog prefills effective principal and account while history remains unchanged',async()=>{
 const ctx=sandbox();const original={id:41,purpose:'topup',amount_cents:1000,account_id:2,case_id:18};
 ctx.s.group={caseId:18,detail:{member:{id:3,version:7},entries:[original],reservations:[],refund_requests:[],effective_topups:[{original_id:41,effective_amount_cents:700,available_refund_cents:500,account_id:9,account_name:'更正后的原账户',corrected:true}]}};
 ctx.api=async()=>({id:18,version:4,number:'HK-SOURCE'});
 ctx.formDialog=async(title,fields,initial,submit,opts)=>{assert.equal(initial.amount,'5.00');assert.equal(initial.account_id,9);assert(opts.notice.includes('当前有效原款 7.00'));assert(opts.notice.includes('更正后的原账户'));};
 await vm.runInContext("groupAction('refund_request',41)",ctx);
 assert.equal(original.amount_cents,1000);assert.equal(original.account_id,2);
});
test('supplier refund request sends exact original receipt and strictly positive amount',async()=>{
 const ctx=sandbox();let submitted;
 ctx.s.businessFinanceOrder={case:{id:22,version:8},return_target:{receivable_id:4,target_cents:100,received_cents:400,overpayment_cents:300},supplier_refund_sources:[{original_payment_id:5,account_name:'原收款账户',reference:'REAL-1',available_cents:300}]};
 ctx.api=async(p,o)=>{submitted=o.body;return {case:{id:23}};};
 ctx.formDialog=async(t,f,i,submit,opts)=>{assert(opts.notice.includes('不能用记账冲正'));await submit({source:'原收款账户 · REAL-1 · 本笔可退3.00元',amount:'2.00',reason:'按原账户实际退回超收'});};
 await vm.runInContext("businessFinanceCreate('other_return_refund')",ctx);
 assert.equal(submitted.purpose,'other_return_refund');assert.equal(submitted.values.original_payment_id,5);assert.equal(submitted.values.source_version,8);assert.equal(submitted.values.amount_cents,200);
});
test('bundle correction sends explicit original purchase and original whole share explanation',async()=>{
 const ctx=sandbox();let submitted;
 const source={...original,source_kind:'bundle',bundle_purchase_id:31,bundle_name:'原冻结赠品组合',bundle_principal_per_share:1000};
 ctx.api=async(p,o)=>{if(!o)return {items:[source]};submitted=o.body;return {case:{id:22}};};
 ctx.formDialog=async(t,f,i,submit,opts)=>{assert(opts.notice.includes('同步原赠品'));assert(f.find(x=>x.name==='original').options[0].includes('每份10.00元'));await submit({original:f.find(x=>x.name==='original').options[0],amount:'20.00',account_id:9,reference:'BUNDLE-CORRECTED',reason:'原组合份数误记复核'});};
 await vm.runInContext("businessFinanceCreate('stored_correction')",ctx);
 assert.equal(submitted.values.bundle_purchase_id,31);assert.equal(submitted.values.amount_cents,2000);
});
test('bundle real refund prefills effective account and retains the original historical account',async()=>{
 const ctx=sandbox();ctx.s.rechargeBundleOrder={case:{id:18,version:2,amount_cents:1000},order:{purpose:'refund',version:3,values:{shares:1}},member:{version:5},rule:{mandatory_terms:'原整份条款',refund_terms:'保留原本金与赠品'},purchase:{original_account:{id:2},effective_account:{id:9}}};
 ctx.formDialog=async(t,f,i,submit,opts)=>{assert.equal(i.account_id,9);assert(opts.notice.includes('真实银行'));};
 await vm.runInContext("rechargeBundleAction('execute')",ctx);assert.equal(ctx.s.rechargeBundleOrder.purchase.original_account.id,2);
});
