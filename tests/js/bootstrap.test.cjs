'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.resolve(__dirname,'../../web/app.js'),'utf8');
const startup=source.slice(source.indexOf('let applicationBootStarted=false;'));
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function sandbox(readyState,{setup=false,error=null}={}){
 const calls={setup:0,api:0,boot:0,login:0,assistant:0},listeners={},app={innerHTML:''};
 const context={Promise,document:{readyState,addEventListener(name,fn,options){listeners[name]={fn,options};}},state:{user:null},
  window:{maybeLocalPreviewSetup:async()=>{calls.setup++;return setup;}},
  api:async()=>{calls.api++;if(error)throw error;return {id:1};},
  boot:async()=>{calls.boot++;await context.businessAssistantPage();},loginPage:()=>{calls.login++;},
  $:()=>app,E:value=>String(value).replaceAll('<','&lt;'),};
 vm.createContext(context);vm.runInContext(startup,context);
 return {context,calls,listeners,app,loadAssistant(){context.businessAssistantPage=async()=>{calls.assistant++;};},run:code=>vm.runInContext(code,context)};
}
test('interactive waits until later defer modules load and DOMContentLoaded fires',async()=>{
 const x=sandbox('interactive');await tick();assert.deepEqual(x.calls,{setup:0,api:0,boot:0,login:0,assistant:0});
 assert.equal(x.listeners.DOMContentLoaded.options.once,true);
 x.loadAssistant();await x.listeners.DOMContentLoaded.fn();
 assert.deepEqual(x.calls,{setup:1,api:1,boot:1,login:0,assistant:1});assert.equal(x.app.innerHTML,'');
});
test('loading also waits and repeated DOM events cannot start a second bootstrap',async()=>{
 const x=sandbox('loading');x.loadAssistant();
 const first=x.listeners.DOMContentLoaded.fn(),second=x.listeners.DOMContentLoaded.fn();await Promise.all([first,second]);
 await x.listeners.DOMContentLoaded.fn();assert.deepEqual(x.calls,{setup:1,api:1,boot:1,login:0,assistant:1});
});
test('complete starts immediately and explicit repeated starts remain harmless',async()=>{
 const x=sandbox('complete');assert.equal(x.calls.setup,1);assert.equal(x.listeners.DOMContentLoaded,undefined);
 x.loadAssistant();await tick();await x.run('bootstrapAppOnce()');await x.run('bootstrapAppOnce()');
 assert.deepEqual(x.calls,{setup:1,api:1,boot:1,login:0,assistant:1});
});
test('first setup still ends bootstrap before ordinary login initialization',async()=>{
 const x=sandbox('interactive',{setup:true});x.loadAssistant();await x.listeners.DOMContentLoaded.fn();
 assert.deepEqual(x.calls,{setup:1,api:0,boot:0,login:0,assistant:0});
});
test('expired login still opens login page without trying a business module',async()=>{
 const x=sandbox('interactive',{error:{status:401,message:'请先登录'}});x.loadAssistant();await x.listeners.DOMContentLoaded.fn();
 assert.deepEqual(x.calls,{setup:1,api:1,boot:0,login:1,assistant:0});
});
