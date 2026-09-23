'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'../..');
function sandbox(){
 const events={};
 const ctx={console,URLSearchParams,Date,Number,Math,JSON,Promise,encodeURIComponent,
  document:{addEventListener:(type,fn)=>events[type]=fn},window:{},dateFilters:()=>'',chartSVG:()=>'<svg></svg>'};
 vm.createContext(ctx);const app=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
 vm.runInContext(app.slice(0,app.indexOf('async function api(')),ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'web/customerservice.js'),'utf8'),ctx);
 vm.runInContext("state.user={id:4,role:'sales'};state.store='1';state.page=1;state.dates={date_from:'2026-09-01',date_to:'2026-09-23'};globalThis.s=state;",ctx);
 ctx.events=events;return ctx;
}
const one={version_number:2,schema_digest:'a'.repeat(64),question_key:'first_visit'};
test('single-chart download carries every selector and ordinary table download carries none',async()=>{
 const ctx=sandbox(),downloads=[];ctx.download=async url=>downloads.push(url);
 for(const dataset of [{act:'care-q-export',key:'questionnaire_distribution',versionNumber:'2',schemaDigest:one.schema_digest,questionKey:'first_visit'},
  {act:'care-q-export',key:'questionnaire_distribution'}]){
  const el={dataset,disabled:false,isConnected:true};
  await ctx.events.click({target:{closest:()=>el}});assert.equal(el.disabled,false);
 }
 const first=new URL(downloads[0],'http://localhost');
 assert.equal(first.pathname,'/api/customer-service/questionnaires/export/questionnaire_distribution');
 assert.equal(first.searchParams.get('version_number'),'2');assert.equal(first.searchParams.get('schema_digest'),one.schema_digest);
 assert.equal(first.searchParams.get('question_key'),'first_visit');assert.equal(first.searchParams.get('date_from'),'2026-09-01');
 const whole=new URL(downloads[1],'http://localhost');
 for(const key of Object.keys(one))assert.equal(whole.searchParams.has(key),false);
});
test('single-question details require version, digest and key and keep false and zero rows',()=>{
 const ctx=sandbox();ctx.filters=one;
 ctx.t={rows:[{...one,answer:false},{...one,answer:0},{...one,version_number:3,answer:true},
  {...one,schema_digest:'b'.repeat(64),answer:true},{...one,question_key:'other',answer:true}]};
 const rows=vm.runInContext('careQuestionnaireRows(t,filters)',ctx);
 assert.equal(rows.length,2);assert.equal(rows[0].answer,false);assert.equal(rows[1].answer,0);
});
test('rendered chart includes only its own distribution and original rows with matching export buttons',async()=>{
 const ctx=sandbox();
 const data={definitions:['实际原题'],charts:[{title:'原题',table:'questionnaire_distribution',table_filters:one}],tables:{
  questionnaire_distribution:{title:'回答分布',headers:['回答','数量'],rows:[{...one,values:[2,one.schema_digest,'first_visit','原题','否',1],count:1},{...one,question_key:'other',values:[2,one.schema_digest,'other','别题','别题分布',9],count:9}]},
  questionnaire_answers:{title:'原答案',headers:['原回答'],rows:[{...one,values:['CC1',2,'2026-09-23','已解决','first_visit','原题','已回答','<img src=x>'],route:{id:42}},
   {...one,version_number:3,values:['CC2',3,'2026-09-23','已解决','first_visit','原题','已回答','另版本答案'],route:{id:43}}]}}};
 ctx.api=async url=>url.endsWith('/catalog')?{can_read:true}:data;
 const html=await vm.runInContext('careQuestionnaireReportPage()',ctx),detail=html.split('<details class="mt15">')[1].split('</details>')[0];
 assert(detail.includes('查看本题同源明细'));assert(!detail.includes('别题分布'));assert(!detail.includes('另版本答案'));
 assert(detail.includes('&lt;img src=x&gt;'));assert(!detail.includes('<img src=x>'));
 assert(detail.includes('data-route="customer-service/42"'));assert(!detail.includes('customer-service/43'));
 assert(html.includes('data-key="questionnaire_distribution" data-version-number="2" data-schema-digest="'+one.schema_digest+'" data-question-key="first_visit"'));
 assert(detail.includes('data-key="questionnaire_answers" data-version-number="2"'));
});
