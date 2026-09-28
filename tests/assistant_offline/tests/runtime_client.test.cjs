'use strict';
// Execute the complete production module. Only network, timers and app context are fixtures.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(process.env.HUAKANGOS_SOURCE || '/mnt/data/HuaKangOS', 'web/assistantruntime.js'), 'utf8');
const RUN = '11111111-1111-4111-8111-111111111111';
const OTHER = '22222222-2222-4222-8222-222222222222';
const SESSION = '33333333-3333-4333-8333-333333333333';
function view(status='running', version=2) {
  return {id:RUN, session_id:SESSION, plan_id:null, status, version, last_seq:0,
    display:{phase:status,text:status,revision:version}, result_refs:[], allowed_actions:[]};
}
function event(seq, type='run.progress', runId=RUN) {
  return {seq, type, run_id:runId, payload:{display:{revision:seq,text:'核对中'}}};
}
function frame(value) { return 'data: '+JSON.stringify(value)+'\n\n'; }
function stream(chunks) {
  return new Response(new ReadableStream({start(c){
    for (const chunk of chunks) c.enqueue(typeof chunk === 'string' ? new TextEncoder().encode(chunk) : chunk);
    c.close();
  }}), {headers:{'content-type':'text/event-stream'}});
}
function deferred() { let resolve,reject; const promise=new Promise((a,b)=>{resolve=a;reject=b;}); return {promise,resolve,reject}; }
async function settle() { for (let i=0;i<5;i++) await new Promise(setImmediate); }
function setup({fetch,request}={}) {
  const timers=new Map(), calls=[], requests=[], events=[];
  let timerId=0, loginCount=0;
  const document={visibilityState:'visible',listeners:{},addEventListener(name,fn){this.listeners[name]=fn;}};
  const sandbox={console,AbortController,DOMException,TextDecoder,TextEncoder,Response,Headers,ReadableStream,document,
    state:{user:{id:7},store:1,storeSwitch:false},epoch:'1:7:1',businessAssistantState:{generation:0},
    businessAssistantContext(){return sandbox.epoch;},
    businessAssistantAlive(current,generation){return current===sandbox.businessAssistantState && generation===current.generation && !sandbox.state.storeSwitch;},
    loginPage(){loginCount++;},
    setTimeout(fn,delay){const id=++timerId;timers.set(id,{fn,delay});return id;},clearTimeout(id){timers.delete(id);},
    fetch(url,options){calls.push({url,options});return fetch ? fetch(url,options) : Promise.resolve(stream([]));},
    businessAssistantRequest(route,options){requests.push({route,options});return request ? request(route,options) : Promise.resolve(route.startsWith('/sessions/') ? {id:SESSION,messages:[],proposals:[]} : view());}
  };
  vm.runInNewContext(source,sandbox,{filename:'web/assistantruntime.js'});
  const api=sandbox.AssistantRuntime;
  return {api,sandbox,timers,calls,requests,events,loginCount:()=>loginCount,
    subscribe:()=>api.subscribeRun(RUN,e=>events.push(e)),
    flushTimer:async()=>{const entry=timers.entries().next().value;if(entry){timers.delete(entry[0]);entry[1].fn();await settle();}}};
}

test('late 401 from a disposed store cannot log out the current account',async()=>{
  const d=deferred(), h=setup({fetch:()=>d.promise}); h.subscribe();
  h.api.disposeContext(); h.sandbox.epoch='2:9:2';h.sandbox.state.user={id:9};h.sandbox.state.store=2;
  d.resolve(new Response('',{status:401}));await settle();
  assert.equal(h.sandbox.state.user?.id,9);assert.equal(h.loginCount(),0);assert.equal(h.timers.size,0);
});
test('wrong-run events never advance the replay cursor',async()=>{
  const h=setup({fetch:async()=>stream([frame(event(1,'run.progress',OTHER))])});h.subscribe();await settle();
  assert.equal(h.api.snapshot(RUN).lastAppliedSeq,0);assert.equal(h.events.filter(e=>e.type==='event').length,0);
});
test('an older GET cannot overwrite the version returned by explicit cancel',async()=>{
  const d=deferred(),h=setup({request:async(route)=>route.startsWith('/sessions/')?{id:SESSION,messages:[],proposals:[]}:route.endsWith('/cancel')?view('cancelled',3):d.promise});
  const old=h.api.getRun(RUN);await h.api.cancelRun(RUN,2);d.resolve(view('running',2));await old;
  assert.equal(h.api.snapshot(RUN).view.status,'cancelled');assert.equal(h.api.snapshot(RUN).view.version,3);
});
test('terminal subscriptions and visibility changes do not reopen the event stream',async()=>{
  const h=setup({request:async()=>view('succeeded',4)});await h.api.getRun(RUN);h.subscribe();await settle();
  h.sandbox.document.listeners.visibilitychange();await settle();
  assert.equal(h.calls.length,0);assert.equal(h.timers.size,0);
});
test('CRLF split across chunks is one delimiter, including multi-line event JSON',async()=>{
  const raw=JSON.stringify(event(1));const split=raw.indexOf(',')+1;
  const h=setup({fetch:async()=>stream(['data: '+raw.slice(0,split)+'\r','\ndata: '+raw.slice(split)+'\r','\n\r','\n'])});
  h.subscribe();await settle();assert.equal(h.api.snapshot(RUN).lastAppliedSeq,1);
  assert.equal(h.events.filter(e=>e.type==='event').length,1);
});
test('an unterminated SSE event is not accepted at EOF',async()=>{
  const h=setup({fetch:async()=>stream(['data: '+JSON.stringify(event(1))])});h.subscribe();await settle();
  assert.equal(h.api.snapshot(RUN).lastAppliedSeq,0);assert.equal(h.events.filter(e=>e.type==='event').length,0);
});
test('current 403 notifies subscribers before disposing and stops reconnecting',async()=>{
  const h=setup({fetch:async()=>new Response('',{status:403})});h.subscribe();await settle();
  assert.ok(h.events.some(e=>e.type==='connection'&&e.state==='closed'&&e.error));assert.equal(h.timers.size,0);
});
test('an aborted old fetch cannot log out the resubscribed current reader',async()=>{
  const first=deferred(),second=deferred();let calls=0;
  const h=setup({fetch:()=>++calls===1?first.promise:second.promise});const off=h.subscribe();off();h.subscribe();
  first.resolve(new Response('',{status:401}));await settle();
  assert.equal(h.loginCount(),0);assert.equal(h.sandbox.state.user?.id,7);
  second.resolve(stream([]));await settle();assert.ok(h.api.snapshot(RUN));
});
test('unknown event types reconcile the canonical RunView before reconnecting',async()=>{
  const h=setup({fetch:async()=>stream([frame(event(1,'future.event'))])});h.subscribe();await settle();
  assert.ok(h.requests.some(r=>r.route==='/runs/'+RUN));assert.equal(h.api.snapshot(RUN).unsupported,'future.event');
});
test('repeated events are delivered once and reconnect uses the last accepted cursor',async()=>{
  const h=setup({fetch:async()=>stream([frame(event(1))+frame(event(1))])});h.subscribe();await settle();
  assert.equal(h.events.filter(e=>e.type==='event').length,1);await h.flushTimer();
  assert.ok(h.calls[1].url.endsWith('after_seq=1'));
});
test('event gaps do not skip missing records',async()=>{
  const h=setup({fetch:async()=>stream([frame(event(2))])});h.subscribe();await settle();
  assert.equal(h.api.snapshot(RUN).lastAppliedSeq,0);await h.flushTimer();assert.ok(h.calls[1].url.endsWith('after_seq=0'));
});
test('terminal session readback must match the run session',async()=>{
  const h=setup({fetch:async()=>stream([frame(event(1,'run.completed'))]),request:async route=>route.startsWith('/sessions/')?{id:OTHER,messages:[{content:'other thread'}],proposals:[]}:view('succeeded',4)});
  h.subscribe();await settle();assert.equal(h.api.snapshot(RUN).session,null);
});
test('UTF-8 split inside a Chinese character is decoded losslessly',async()=>{
  const bytes=new TextEncoder().encode(frame(event(1)));const chunks=Array.from(bytes,x=>new Uint8Array([x]));
  const h=setup({fetch:async()=>stream(chunks)});h.subscribe();await settle();
  assert.equal(h.events.find(e=>e.type==='event')?.event.payload.display.text,'核对中');
});
test('dispose and unsubscription only stop local reads; they never confirm or cancel business',async()=>{
  const h=setup();const off=h.subscribe();await settle();off();h.api.disposeContext();await settle();
  assert.ok(h.requests.every(r=>!r.options.method||r.options.method==='GET'));
  assert.ok(h.calls.every(c=>c.options.method==='GET'));assert.equal(h.timers.size,0);
});

test('terminal consumers receive the conversation and cards before they unsubscribe',async()=>{
  const session={id:SESSION,messages:[{role:'assistant',content:'已准备'}],proposals:[{id:'card',status:'pending'}]};
  const h=setup({fetch:async()=>stream([frame(event(1,'run.completed'))]),request:async route=>route.startsWith('/sessions/')?session:view('succeeded',4)});
  let received=null,off;off=h.api.subscribeRun(RUN,e=>{if(e.type==='view'&&e.view.status==='succeeded'){received=e;off();}});
  await settle();assert.deepEqual(received.session,session);assert.equal(h.api.snapshot(RUN).subscribers,0);
});
test('failed terminal session retrieval is explicit and never replays a command',async()=>{
 const h=setup({fetch:async()=>stream([frame(event(1,'run.completed'))]),request:async route=>{if(route.startsWith('/sessions/'))throw Error('offline');return view('succeeded',4);}});
 h.subscribe();await settle();assert.ok(h.events.some(e=>e.sessionReadFailed===true));
 assert.equal(h.api.snapshot(RUN).view.status,'succeeded');assert.equal(h.api.snapshot(RUN).session,null);
 assert.ok(h.requests.every(r=>!r.options.method||r.options.method==='GET'));
});
test('returning with a new page generation replaces the stale reader safely',async()=>{
 const d=deferred();let count=0;const h=setup({fetch:()=>++count===1?d.promise:Promise.resolve(stream([]))});
 const old=h.subscribe();h.sandbox.businessAssistantState.generation++;old();h.subscribe();
 d.resolve(new Response('',{status:401}));await settle();
 assert.equal(h.calls.length,2);assert.equal(h.loginCount(),0);assert.equal(h.api.snapshot(RUN).subscribers,1);
});
