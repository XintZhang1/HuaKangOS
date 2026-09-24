'use strict';
// Actual upload controller with synthetic DOM and transport, without business or file writes.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.resolve(__dirname,'../../web/formhelpers.js'),'utf8');
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
function fixture(){
 const handlers={},calls=[],submit={disabled:false,isConnected:true},controls=[submit];
 const form={querySelector:()=>submit,querySelectorAll:()=>controls};
 const makePicker=caseId=>{
  const selection={value:'old-proof',innerHTML:'',dispatchEvent(){}},status={textContent:'',innerHTML:''};
  const file={files:[{size:10,name:'合成凭据.txt'}],disabled:false,isConnected:true},category={value:'evidence',disabled:false,isConnected:true},original={value:'',disabled:false,isConnected:true};
  const panel={hidden:false,innerHTML:'original panel',querySelector:s=>s==='[data-inline-file]'?file:s==='[data-inline-category]'?category:s==='[data-inline-source]'?original:{hidden:true}};
  const picker={querySelector:s=>s==='select'?selection:null};
  const root={dataset:{fileCase:String(caseId),fileKind:'file'},isConnected:true,querySelector:s=>s==='[data-inline-file-panel]'?panel:status,closest:s=>s==='form'?form:s==='.lookup'?null:picker};
  const button=act=>({dataset:{act},disabled:false,isConnected:true,closest:s=>s==='[data-act]'?null:root});
  const open=button('inline-file-open'),upload=button('inline-file-upload');for(const b of [open,upload])b.closest=s=>s==='[data-act]'?b:root;
  controls.push(open,upload,file,category,original);return {root,panel,status,file,category,original,selection,open,upload};
 };
 const first=makePicker(10),second=makePicker(10);
 const ctx={console,WeakMap,Map,Array,Event:class{},FormData:class{constructor(){this.entries=[];}append(k,v){this.entries.push([k,v]);}},
  storeContextVersion:1,state:{user:{role:'finance'},catalog:{upload_categories:{evidence:'业务凭据',receipt:'收款凭据'}},row:{id:10,files:[]}},
  requireStoreContext:version=>{if(version!==ctx.storeContextVersion)throw new Error('门店或账号已切换');},E:v=>String(v??''),b:()=>'',time:v=>v,
  document:{addEventListener:(name,fn)=>handlers[name]=fn},api:async(url,options)=>{calls.push({url,options});return options?{id:101}:{items:[{id:101,label:'合成凭据'}],files:[]};}};
 vm.createContext(ctx);vm.runInContext(source,ctx);return {ctx,handlers,calls,submit,controls,first,second};
}
test('upload locks every entry in the same form and rejects a direct concurrent upload before transport',async()=>{
 const f=fixture(),pending=deferred();let posted=0;
 f.ctx.api=async(url,options)=>{if(options){posted++;return pending.promise;}return {items:[{id:101,label:'合成凭据'}]};};
 const run=f.ctx.sendInlineFile(f.first.upload);assert.equal(f.submit.disabled,true);assert.equal(f.first.open.disabled,true);assert.equal(f.second.open.disabled,true);
 await assert.rejects(f.ctx.sendInlineFile(f.second.upload),/文件正在上传/);assert.equal(posted,1);
 await assert.rejects(f.ctx.openInlineFile(f.first.open),/文件正在上传/);
 await f.handlers.click({target:f.second.open});assert.equal(f.second.panel.innerHTML,'original panel');
 pending.resolve({id:101});await run;assert.equal(f.submit.disabled,false);assert.equal(f.first.open.disabled,false);assert.equal(f.second.upload.disabled,false);
 assert.match(f.first.status.textContent,/已选用/);
});
test('an earlier pending open cannot rebuild a panel during upload or release its entry early',async()=>{
 const f=fixture(),opening=deferred(),uploading=deferred();
 f.ctx.api=async(url,options)=>options?uploading.promise:url.endsWith('/cases/10')?opening.promise:{items:[{id:101,label:'合成凭据'}]};
 const openingRun=f.handlers.click({target:f.first.open});assert.equal(f.first.open.disabled,true);
 const uploadRun=f.handlers.click({target:f.first.upload});opening.resolve({files:[]});await openingRun;
 assert.equal(f.first.panel.innerHTML,'original panel');assert.equal(f.first.open.disabled,true);assert.equal(f.submit.disabled,true);
 uploading.resolve({id:101});await uploadRun;assert.equal(f.first.open.disabled,false);assert.equal(f.first.upload.disabled,false);assert.equal(f.submit.disabled,false);
});
test('failed upload unlocks the form and permits one subsequent retry',async()=>{
 const f=fixture();let attempts=0;
 f.ctx.api=async(url,options)=>{if(options){if(++attempts===1)throw new Error('上传连接中断');return {id:102};}return {items:[{id:102,label:'重试凭据'}]};};
 await f.handlers.click({target:f.first.upload});assert.match(f.first.status.textContent,/上传连接中断/);assert.equal(f.submit.disabled,false);assert.equal(f.first.open.disabled,false);assert.equal(f.first.upload.disabled,false);
 await f.handlers.click({target:f.first.upload});assert.equal(attempts,2);assert.equal(f.submit.disabled,false);assert.match(f.first.status.textContent,/已选用：重试凭据/);
});
test('pre-existing disabled submit and upload controls remain disabled after success and failure',async()=>{
 for(const fail of [false,true]){
  const f=fixture();f.submit.disabled=true;f.second.open.disabled=true;
  f.ctx.api=async(url,options)=>{if(fail)throw new Error('检查失败');return options?{id:101}:{items:[{id:101,label:'合成凭据'}]};};
  if(fail)await assert.rejects(f.ctx.sendInlineFile(f.first.upload),/检查失败/);else await f.ctx.sendInlineFile(f.first.upload);
  assert.equal(f.submit.disabled,true);assert.equal(f.second.open.disabled,true);assert.equal(f.first.open.disabled,false);
 }
});
test('lookup failure after storing the file still unlocks and keeps the saved file available for checking',async()=>{
 const f=fixture();f.ctx.api=async(url,options)=>{if(options)return {id:103};throw new Error('检查连接中断');};
 await assert.rejects(f.ctx.sendInlineFile(f.first.upload),/检查连接中断/);
 assert.equal(f.submit.disabled,false);assert.equal(f.first.root.dataset.uploadedId,'103');assert.equal(f.ctx.state.row.files[0].id,103);
});
test('context switch rejects a late upload result and always releases original controls',async()=>{
 const f=fixture(),pending=deferred();f.ctx.api=async()=>pending.promise;
 const run=f.ctx.sendInlineFile(f.first.upload);f.ctx.storeContextVersion=2;pending.resolve({id:101});
 await assert.rejects(run,/门店或账号已切换/);assert.equal(f.ctx.state.row.files.length,0);assert.equal(f.first.root.dataset.uploadedId,undefined);assert.equal(f.submit.disabled,false);assert.equal(f.first.open.disabled,false);
});
test('invalid signed-file association does not acquire an upload lock or send any request',async()=>{
 const f=fixture();f.first.category.value='signed_contract';
 await assert.rejects(f.ctx.sendInlineFile(f.first.upload),/请选择对应/);assert.equal(f.calls.length,0);assert.equal(f.submit.disabled,false);
 f.first.category.value='evidence';await f.ctx.sendInlineFile(f.first.upload);assert.match(f.first.status.textContent,/已选用/);
});
