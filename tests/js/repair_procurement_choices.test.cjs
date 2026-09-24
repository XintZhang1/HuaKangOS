'use strict';
// Exercise actual page functions with synthetic transport; these are not browser or company acceptance results.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..');
function sandbox(){
 const handlers={},ctx={console,Intl,Date,Number,Math,Set,Map,JSON,Promise,URLSearchParams,
  document:{addEventListener:(name,fn)=>(handlers[name]??=[]).push(fn)},window:{addEventListener:()=>{}},
  setTimeout:()=>1,F:(key,label,type,required,options)=>({key,label,type,required,options}),
  requestKey:()=> 'synthetic-request',memberPriceField:async()=>'',memberPricePayload:()=>({}),closeModal:()=>{},render:async()=>{}};
 vm.createContext(ctx);const app=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
 vm.runInContext(app.slice(0,app.indexOf('async function api(')),ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'web/repair.js'),'utf8'),ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'web/procurement.js'),'utf8'),ctx);
 vm.runInContext("state.user={id:6,role:'inventory'};state.store='1';state.route='repair-orders/80';state.catalog={};globalThis.s=state;",ctx);
 ctx.requestKey=()=> 'synthetic-request';return {ctx,handlers};
}
function sourceSelect(price={value:'77.50',readOnly:false}){
 const source={value:'work:2',disabled:false,dataset:{priceSource:'work:1'},selectedOptions:[{dataset:{referencePrice:'12999'}}],
  matches:selector=>selector==='select[data-repair-source]',closest:()=>({querySelector:()=>price})};
 return {source,price};
}
function repairFixture(){return {id:80,version:9,data:{quote_id:12},quotes:[
 {id:11,lines:[{line_key:'old-part',kind:'part',item_id:3,code:'P003',name:'原机油滤芯',unit:'个'}]},
 {id:12,lines:[{line_key:'old-part',kind:'part',item_id:3,code:'P003',name:'现改名滤芯',unit:'个'}]}],stock:[
 {id:21,quote_id:11,line_key:'old-part',stock_move_id:91,returnable_milli:1750},
 {id:22,quote_id:11,line_key:'old-part',stock_move_id:92,returnable_milli:1000},
 {id:23,quote_id:11,line_key:'old-part',stock_move_id:93,returnable_milli:0}]};}
test('changing quote item applies corresponding fen reference synchronously; later manual edit and same choice survive',()=>{
 const {ctx,handlers}=sandbox(),{source,price}=sourceSelect();
 handlers.change[0]({target:source});assert.equal(price.value,'129.99');
 price.value='118.80';handlers.change[0]({target:source});assert.equal(price.value,'118.80');
 source.value='';handlers.change[0]({target:source});assert.equal(price.value,'118.80');
 source.value='work:2';handlers.change[0]({target:source});assert.equal(price.value,'118.80');
 source.value='part:9';source.selectedOptions[0].dataset.referencePrice='0';handlers.change[0]({target:source});assert.equal(price.value,'0.00');
 assert.equal(ctx.s.repairOrder,undefined);
});
test('frozen/disabled quote lines and malformed reference values never change approved prices',()=>{
 const {handlers}=sandbox(),{source,price}=sourceSelect();
 source.disabled=true;handlers.change[0]({target:source});assert.equal(price.value,'77.50');
 source.disabled=false;price.readOnly=true;handlers.change[0]({target:source});assert.equal(price.value,'77.50');
 price.readOnly=false;for(const raw of [undefined,'-1','1.001','9007199254740992']){
  source.selectedOptions[0].dataset.referencePrice=raw;handlers.change[0]({target:source});assert.equal(price.value,'77.50');
 }
});
test('return choices retain source IDs, original quote name, exact movement date and remaining quantity',async()=>{
 const {ctx}=sandbox(),calls=[];ctx.row=repairFixture();
 ctx.api=async url=>{calls.push(url);return {rows:[
  {id:91,case_id:80,item_id:3,source:'业务',date:'2026-09-22'},
  {id:92,case_id:999,item_id:3,source:'业务',date:'2099-01-01'},
  {id:92,case_id:80,item_id:999,source:'业务',date:'2099-01-02'},
  {id:92,case_id:80,item_id:3,source:'期初',date:'2099-01-03'}]};};
 const result=await vm.runInContext('repairReturnOptions(row)',ctx);
 assert.deepEqual(calls,['/api/masters/opening/stockflow?item_id=3']);assert.equal(result.length,2);
 assert.equal(result[0].value,'21');assert.match(result[0].label,/P003 · 原机油滤芯/);assert.match(result[0].label,/领用 2026-09-22/);assert.match(result[0].label,/可退 1.75 个/);
 assert.equal(result[1].value,'22');assert(!result[1].label.includes('2099'));assert(!result[1].label.includes('现改名'));
});
test('unavailable optional movement dates do not prevent returning an existing source',async()=>{
 const {ctx}=sandbox();ctx.row=repairFixture();ctx.api=async()=>{throw new Error('没有读取权限');};
 const result=await vm.runInContext('repairReturnOptions(row)',ctx);assert.equal(result.length,2);assert.equal(result[0].value,'21');assert.match(result[0].label,/可退 1.75 个/);assert(!result[0].label.includes('领用 '));
});
test('return form submits original stock ID, version, proof and milli quantity unchanged',async()=>{
 const {ctx}=sandbox();ctx.s.repairOrder=repairFixture();let posted;
 ctx.api=async(url,options)=>{if(!options)return {rows:[]};posted={url,body:options.body};return {};};
 ctx.formDialog=async(title,fields,initial,submit)=>{
  const field=fields.find(f=>f.key==='original_id');assert.equal(field.searchable,true);assert.equal(field.options[0].value,'21');
  await submit({original_id:'21',quantity:'1.250',evidence_id:34});
 };
 await vm.runInContext("repairAction('return_material')",ctx);
 assert.equal(posted.url,'/api/repair-orders/80/actions/return_material');assert.equal(posted.body.version,9);
 assert.equal(posted.body.values.original_id,21);assert.equal(posted.body.values.quantity_milli,1250);assert.equal(posted.body.values.evidence_id,34);
 assert(!('quantity'in posted.body.values));
});
test('store switch while optional return-date query is pending cannot reopen the old form',async()=>{
 const {ctx}=sandbox();ctx.s.repairOrder=repairFixture();let release,opened=false;
 ctx.api=()=>new Promise(resolve=>{release=resolve;});ctx.formDialog=async()=>{opened=true;};
 const pending=vm.runInContext("repairAction('return_material')",ctx);ctx.s.store='2';release({rows:[]});await pending;assert.equal(opened,false);
});
test('quote HTML exposes search IDs/reference prices while submitted edited price stays editable',async()=>{
 const {ctx}=sandbox();ctx.s.repairOrder={id:80,version:9,data:{},quotes:[]};let body,markup;
 ctx.api=async(url,options)=>{if(options){body=options.body;return {};}return url.includes('work_items')?{items:[{id:1,code:'W1',name:'作业A',standard_fee_cents:1000},{id:2,code:'W2',name:'作业B',standard_fee_cents:12999}],total:2}:{items:[],total:0};};
 ctx.modal=async(title,html,save)=>{markup=html;ctx.save=save;};
 await vm.runInContext('repairQuoteDialog()',ctx);assert.match(markup,/data-search-select data-repair-source/);assert.match(markup,/value="work:2" data-reference-price="12999"/);
 const values={source:'work:2',quantity:'1.250',price:'118.80'};
 await ctx.save({querySelectorAll:()=>[{dataset:{},querySelector:s=>({value:values[s.slice(6,-1)]})}],elements:{reason:{value:'客户确认报价'},discount:{value:'0.00'}}});
 assert.equal(body.values.lines[0].source_id,2);assert.equal(body.values.lines[0].unit_price_cents,11880);assert.equal(body.values.lines[0].quantity_milli,1250);assert.equal(body.version,9);
});
test('procurement refund choices use original receipts and authorised amounts without inventing dates',()=>{
 const {ctx}=sandbox();ctx.row={payments:[{id:4,direction:'out',amount_cents:20000,reference:'付款-A'},{id:5,direction:'in',amount_cents:3500,original_id:4},{id:6,direction:'out',amount_cents:7500,reference:'付款-B'}]};
 const options=vm.runInContext('procurementRefundOptions(row)',ctx);assert.equal(options.length,2);assert.equal(options[0].value,'4');
 assert.match(options[0].label,/凭证 付款-A/);assert.match(options[0].label,/原付 200.00 元/);assert.match(options[0].label,/本笔剩余 165.00 元/);assert(!options[0].label.includes('undefined'));
});
test('prepayment refunds retain exact available-source filter and submit original payment ID',async()=>{
 const {ctx}=sandbox();ctx.s.procurement={id:90,version:8,payments:[{id:4,direction:'out',amount_cents:20000,reference:'付款-A'},{id:6,direction:'out',amount_cents:7500,reference:'付款-B'}],prepayments:{original_cash:[{payment_id:4,available_cents:1200},{payment_id:6,available_cents:0}]},totals:{supplier_refund_due_cents:1200}};let posted;
 ctx.api=async(url,options)=>{posted=options.body;return {};};
 ctx.formDialog=async(title,fields,initial,submit)=>{const field=fields.find(f=>f.key==='original_payment_id');assert.equal(field.searchable,true);assert.equal(field.options.length,1);assert.equal(field.options[0].value,'4');assert.match(field.options[0].label,/本笔剩余 12.00 元/);assert.equal(initial.amount,'12.00');await submit({original_payment_id:'4',amount:'8.50',account_id:9,reference:'实际退款-1',evidence_id:35});};
 await vm.runInContext("procurementAction('refund')",ctx);assert.equal(posted.version,8);assert.equal(posted.values.original_payment_id,4);assert.equal(posted.values.amount_cents,850);assert.equal(posted.values.account_id,9);assert.equal(posted.values.evidence_id,35);
});
