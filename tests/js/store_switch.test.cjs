'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.resolve(__dirname,'../../web/app.js'),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
function response(value,status=200){return {ok:status<400,status,json:async()=>value};}
function sandbox(){
 const nodes=Object.fromEntries(['#app','#main','#store','#modal','#toast'].map(k=>[k,{innerHTML:'old store business',close(){this.closed=true;}}]));
 const events={},requests=[],renders=[];
 const ctx={console,Promise,Intl,Date,Number,Math,JSON,URLSearchParams,FormData,TextEncoder,setTimeout,clearTimeout,location:{hash:'#parameters'},history:{replaceState(_a,_b,hash){ctx.location.hash=hash;}},sessionStorage:{setItem(){},removeItem(){}},document:{cookie:'',querySelector:q=>nodes[q],querySelectorAll:()=>[],addEventListener(){}},window:{addEventListener:(event,callback)=>events[event]=callback},fetch:async(url,options)=>{requests.push({url,store:options.headers['X-Store-ID']});return ctx.respond(url,options.headers['X-Store-ID']);}};
 ctx.respond=async(url,store)=>response(url==='/api/auth/me'?{id:1,role:store==='2'?'service':'manager',active_store_id:Number(store),can_group_summary:true}:{store,path:url,kinds:{},master_types:{},states:{}});
 vm.createContext(ctx);vm.runInContext(source.slice(0,source.indexOf('function searchBar(')),ctx);
 ctx.recordRender=()=>renders.push({store:ctx.s.store,role:ctx.s.user.role,activeStore:ctx.s.user.active_store_id,route:ctx.s.route,catalogs:Object.fromEntries(['catalog','typedCatalog','careCatalog','openingCatalog','dossierCatalog'].map(key=>[key,{store:ctx.s[key].store,path:ctx.s[key].path}]))});
 vm.runInContext("state.user={id:1,role:'manager',active_store_id:1,can_group_summary:true};state.store='1';state.stores=[{id:1,name:'原店'},{id:2,name:'二店'},{id:3,name:'三店'}];state.catalog={store:'1',kinds:{},master_types:{}};state.typedCatalog={store:'1'};state.row={id:999};globalThis.s=state;shell=()=>{if(state.storeSwitch)storeSwitchShell();else document.querySelector('#app').innerHTML='confirmed '+state.store;};render=async()=>recordRender();",ctx);
 return Object.assign(ctx,{nodes,events,requests,renders,run:code=>vm.runInContext(code,ctx)});
}
test('switch clears old content immediately and queues only latest navigation with atomic identity/catalog',async()=>{
 const c=sandbox(),gate=deferred(),respond=c.respond;c.respond=async(url,store)=>{if(url==='/api/auth/me'&&store==='2')await gate.promise;return respond(url,store);};
 const run=c.run("switchStore('2')");assert.match(c.nodes['#app'].innerHTML,/正在切换门店/);assert(!c.nodes['#app'].innerHTML.includes('old store business'));assert.equal(c.s.row,null);assert.equal(c.s.store,'1');assert.equal(c.s.user.role,'manager');assert.equal(c.run('canWrite()'),false);
 c.location.hash='#dictionaries/repair';c.events.hashchange();c.run("go('dictionaries/member')");assert.equal(c.renders.length,0);
 await assert.rejects(c.run("api('/api/dictionaries/repair')"),/正在切换/);assert.equal(c.requests.length,1);
 gate.resolve();await run;assert.equal(c.s.store,'2');assert.equal(c.s.user.role,'service');assert.equal(c.s.route,'dictionaries/member');assert.equal(c.s.storeSwitch,null);assert.equal(c.renders.length,1);
 const catalogs={catalog:'/api/flow/catalog',typedCatalog:'/api/masters/catalog',careCatalog:'/api/customer-service/catalog',openingCatalog:'/api/opening-import/catalog',dossierCatalog:'/api/dossier-grants/catalog'};
 assert.deepEqual(c.renders[0],{store:'2',role:'service',activeStore:2,route:'dictionaries/member',catalogs:Object.fromEntries(Object.entries(catalogs).map(([key,path])=>[key,{store:'2',path}]))});
 assert.equal(c.requests.length,6);assert.deepEqual(c.requests.map(r=>r.url).sort(),['/api/auth/me',...Object.values(catalogs)].sort());assert(c.requests.every(r=>r.store==='2'));
});
test('rapid repeated switches discard earlier response and preserve last target with its own headers',async()=>{
 const c=sandbox(),gate=deferred(),respond=c.respond;c.respond=async(url,store)=>{if(url==='/api/auth/me'&&store==='2')await gate.promise;return respond(url,store);};
 const first=c.run("switchStore('2')"),second=c.run("switchStore('3','dictionaries/public')");await second;gate.resolve();await first;
 assert.equal(c.s.store,'3');assert.equal(c.s.user.active_store_id,3);assert.equal(c.s.route,'dictionaries/public');assert.equal(c.renders.length,1);assert.equal(c.s.catalog.store,'3');assert.equal(c.requests.filter(r=>r.store==='2').length,1);
});
test('stale business data cannot write caches even if response headers arrived before switching',async()=>{
 const c=sandbox(),gate=deferred(),respond=c.respond;c.respond=async(url,store)=>url==='/old'?{ok:true,status:200,json:()=>gate.promise}:respond(url,store);
 const old=c.run("api('/old').then(value=>{state.row=value;})");const rejected=assert.rejects(old,/门店或账号已切换/);await tick();await c.run("switchStore('2')");gate.resolve({id:999,store:'1'});await rejected;assert.equal(c.s.row,null);assert.equal(c.s.store,'2');
});
test('stale failure does not log out the new store or replace it with a network message',async()=>{
 const c=sandbox(),gate=deferred(),respond=c.respond;c.respond=async(url,store)=>url==='/old'?gate.promise:respond(url,store);c.run('loginPage=()=>{throw new Error("unexpected logout")}');
 const old=c.run("api('/old')"),rejected=assert.rejects(old,/门店或账号已切换/);await c.run("switchStore('2')");gate.resolve(response({detail:'旧请求已过期'},401));await rejected;assert.equal(c.s.user.role,'service');
});
test('late completed original POST tells the user to verify original result and never resubmits it',async()=>{
 const c=sandbox(),gate=deferred(),respond=c.respond;c.respond=async(url,store)=>url==='/original-command'?gate.promise:respond(url,store);
 const command=c.run("api('/original-command',{method:'POST',body:{request_id:'one-original-request'}})"),rejected=assert.rejects(command,error=>error.staleMutation&&/原门店的操作可能已提交.*核对办理结果.*勿重复提交/.test(error.message));
 await c.run("switchStore('2')");gate.resolve(response({posted:true}));await rejected;
 assert.equal(c.requests.filter(r=>r.url==='/original-command').length,1);assert.equal(c.requests.find(r=>r.url==='/original-command').store,'1');assert.equal(c.s.store,'2');
});
test('an old attachment body cannot start a download after the store has changed',async()=>{
 const c=sandbox(),gate=deferred(),respond=c.respond;c.respond=async(url,store)=>url==='/old-file'?{ok:true,status:200,headers:{get:()=>null},blob:()=>gate.promise}:respond(url,store);
 let downloaded=false;c.URL={createObjectURL:()=>{downloaded=true;return 'blob:old-file';}};
 const file=c.run("download('/old-file','原店文件.txt')"),rejected=assert.rejects(file,/门店或账号已切换/);await tick();await c.run("switchStore('2')");gate.resolve({old:true});await rejected;assert.equal(downloaded,false);
});
test('target catalog failure rereads complete original scope and drops target-specific route',async()=>{
 const c=sandbox(),respond=c.respond;c.respond=async(url,store)=>store==='2'&&url==='/api/masters/catalog'?response({detail:'岗位已撤销'},403):respond(url,store);
 await c.run("switchStore('2','case/99')");assert.equal(c.s.store,'1');assert.equal(c.s.user.role,'manager');assert.equal(c.s.catalog.store,'1');assert.equal(c.s.typedCatalog.store,'1');assert.equal(c.s.route,'work');assert.match(c.nodes['#toast'].textContent,/已返回原门店.*岗位已撤销/);
 assert.equal(c.requests.filter(r=>r.store==='1').length,6);assert.equal(c.renders.length,1);
});
test('failed rollback stays blocked and retry can restore original context',async()=>{
 const c=sandbox(),respond=c.respond;c.respond=async()=>response({detail:'网络暂不可用'},503);
 await c.run("switchStore('2')");assert.equal(c.s.storeSwitch.failed,true);assert.equal(c.renders.length,0);assert.match(c.nodes['#app'].innerHTML,/重新读取原门店/);await assert.rejects(c.run("api('/api/flow/tasks')"),/正在切换/);
 c.respond=respond;await c.run("switchStore(state.store)");assert.equal(c.s.store,'1');assert.equal(c.s.storeSwitch,null);assert.equal(c.renders.length,1);
});
test('failure of superseded target never rolls back a successful later switch',async()=>{
 const c=sandbox(),gate=deferred(),respond=c.respond;c.respond=async(url,store)=>store==='2'&&url==='/api/auth/me'?gate.promise:respond(url,store);
 const first=c.run("switchStore('2')");await c.run("switchStore('3')");gate.resolve(response({detail:'二店拒绝'},403));await first;
 assert.equal(c.s.store,'3');assert.equal(c.renders.length,1);assert(!c.requests.some(r=>r.store==='1'));
});
