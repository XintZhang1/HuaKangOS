'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function sandbox(){
 const timers=new Map(),calls=[],handlers={};let timer=0;
 const ctx={console,URLSearchParams,Event,Set,WeakMap,Array,storeContextVersion:1,
  setTimeout(fn){timers.set(++timer,fn);return timer;},clearTimeout(id){timers.delete(id);},
  MutationObserver:class{observe(){}},document:{documentElement:{},querySelectorAll:()=>[],addEventListener:(name,handler)=>handlers[name]=handler},
  api:async url=>{calls.push(url);return {items:[]};}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/livechoices.js'),'utf8'),ctx);ctx.run=code=>vm.runInContext(code,ctx);ctx.calls=calls;ctx.handlers=handlers;
 ctx.flush=async()=>{const pending=[...timers.values()];timers.clear();for(const fn of pending)await fn();};
 ctx.run(`globalThis.observed=[];lookupClose=()=>{};liveChoiceMessage=(s,message,retry)=>observed.push({message,retry});lookupResults=(root,items)=>observed.push({items});
 globalThis.root={isConnected:true,dataset:{kind:'customers'},closest(){return this;}};
 globalThis.input={value:'',disabled:false,required:true,closest:()=>root,setCustomValidity(value){this.error=value;}};
 globalThis.select={value:'',required:true,matches:()=>false,dispatchEvent(event){this.events=(this.events||0)+1;}};
 globalThis.choice={root,input,select,remote:true,context:1,value:'',editing:false,run:{}};liveChoiceStates.set(root,choice);`);
 return ctx;
}
test('search matches Chinese and case-insensitive spaced terms while retaining explicit create',()=>{
 const c=sandbox();c.items=[{id:'1',label:'比亚迪 秦 PLUS'},{id:'2',label:'大众 朗逸'},{id:'new',label:'+ 新增车型',create:true}];
 assert.deepEqual(Array.from(c.run("liveChoiceMatch(items,'秦 plus').map(x=>x.id)")),['1','new']);
 assert.deepEqual(Array.from(c.run("liveChoiceMatch(items,'  不存在 ').map(x=>x.id)")),['new']);
});
test('disabled options and disabled option groups are never offered',()=>{
 const c=sandbox();c.options=[{value:'1',textContent:'可选',hasAttribute:()=>false,parentElement:{}},{value:'2',textContent:'停用',disabled:true},{value:'3',textContent:'停用组',parentElement:{disabled:true}},{value:'',textContent:'请选择'}];
 assert.deepEqual(Array.from(c.run('liveChoiceItems({options}).map(x=>x.id)')),['1']);
});
test('typing invalidates the prior selection and debounces multiple remote requests',async()=>{
 const c=sandbox();c.run("select.value='7';input.value='张';lookupSearch(input);input.value='张三';lookupSearch(input)");
 assert.equal(c.select.value,'');assert.equal(c.select.events,1);assert.equal(c.input.error,'请从列表中选择');await c.flush();assert.equal(c.calls.length,1);assert.equal(new URL(c.calls[0],'https://test.invalid').searchParams.get('q'),'张三');
});
test('Chinese composition never sends partial input and sends the committed query once',async()=>{
 const c=sandbox();c.run("choice.composing=true;input.value='zhang';lookupSearch(input)");await c.flush();assert.equal(c.calls.length,0);
 c.run("choice.composing=false;input.value='张三';lookupSearch(input)");await c.flush();assert.equal(c.calls.length,1);
});
test('store changes before debounce prevent any request under the new store',async()=>{
 const c=sandbox();c.run("input.value='旧店客户';lookupSearch(input);storeContextVersion++");await c.flush();assert.equal(c.calls.length,0);
});
test('late results cannot replace a newer query or survive a store switch',async()=>{
 const c=sandbox();let resolve;c.api=()=>new Promise(done=>resolve=done);c.run("input.value='旧';lookupSearch(input)");const first=c.flush();await Promise.resolve();
 c.run("input.value='新';lookupSearch(input)");resolve({items:[{id:1,label:'旧客户'}]});await first;assert(!c.observed.some(row=>row.items));
 c.api=()=>new Promise(done=>resolve=done);const second=c.flush();await Promise.resolve();c.run('storeContextVersion++');resolve({items:[{id:2,label:'新客户'}]});await second;assert(!c.observed.some(row=>row.items));
});
test('network error offers retry without restoring an invalid old selection',async()=>{
 const c=sandbox();c.api=async()=>{throw new Error('网络暂不可用');};c.run("input.value='客户';select.value='8';lookupSearch(input)");await c.flush();assert.equal(c.select.value,'');assert.deepEqual(JSON.parse(JSON.stringify(c.observed.at(-1))),{message:'网络暂不可用',retry:true});
});
test('clearing a required input leaves the original select empty and required',async()=>{
 const c=sandbox();c.run("input.value='';select.value='8';lookupSearch(input)");assert.equal(c.input.required,true);assert.equal(c.select.required,true);assert.equal(c.select.value,'');assert.equal(c.input.error,'');
});
