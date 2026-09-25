'use strict';
// The assistant proposes existing business commands. This page never executes
// model-produced JavaScript, HTML, URLs or arbitrary HTTP requests.
let businessAssistantState;
function freshBusinessAssistantState(){return {context:null,generation:0,controllers:new Set(),status:null,sessions:[],session:null,issues:[],tab:'chat',draft:'',error:'',busy:false,needsRefresh:false,retry:null,files:null,thinking:false,stream:null,cards:{},folded:{},panelFolded:false,lastAction:null};}
businessAssistantState=freshBusinessAssistantState();
function businessAssistantContext(){return `${storeContextVersion}:${state.user?.id||''}:${state.store||''}`;}
function clearBusinessAssistantSession(){
 if(typeof clearWorkflowContext==='function')clearWorkflowContext();
 const previous=businessAssistantState;
 for(const controller of previous.controllers)controller.abort();
 businessAssistantState=freshBusinessAssistantState();businessAssistantState.generation=previous.generation+1;
}
function leaveBusinessAssistantView(){
 // 业主 2026-09-25：员工会一边让助手办着，一边去别的页面看资料/接单，离开这一页不该把这一轮掐断。
 // 真正要停的场景是换门店或退出登录，它们走 clearBusinessAssistantSession()（会 abort 全部请求）。
 if(businessAssistantState.controllers.size)businessAssistantState.background=true;
}
// "还活着"= 还是同一个会话对象、同一个门店账号、没有在切门店：离开助手页面不影响这一轮。
// 只有"要不要画到屏幕上"才看 state.route（见 businessAssistantCurrent / paintBusinessAssistant）。
function businessAssistantAlive(current,generation){return current===businessAssistantState&&current.context===businessAssistantContext()&&current.generation===generation&&!state.storeSwitch;}
function businessAssistantCurrent(current,generation){return businessAssistantAlive(current,generation)&&state.route==='business-assistant';}
async function businessAssistantRequest(path,{method='GET',body}={}){
 const current=businessAssistantState,version=storeContextVersion,context=businessAssistantContext(),controller=new AbortController();
 if(state.storeSwitch)throw new Error('正在切换门店，请稍后再试。');
 if(!state.user||state.store==='all')throw new Error('请先选择门店。');

 const headers={'X-App-Request':'1','X-Store-ID':String(state.store)};
 const multipart=typeof FormData!=='undefined'&&body instanceof FormData;
 if(multipart&&(path!=='/file-preview'||method!=='POST'))throw new Error('文件入口不正确。');
 current.controllers.add(controller);
 if(method!=='GET'){headers['X-CSRF-Token']=csrf();if(!multipart)headers['Content-Type']='application/json';}
 const check=()=>{requireStoreContext(version,method);if(current!==businessAssistantState||context!==businessAssistantContext())throw Object.assign(new Error('门店或账号已切换。'),{staleContext:true});};
 try{
  const response=await fetch('/api/business-assistant'+path,{method,credentials:'same-origin',headers,signal:controller.signal,body:method==='GET'?undefined:multipart?body:JSON.stringify(body||{})});
  check();let value;try{value=await response.json();}catch(error){if(error.name==='AbortError')throw error;throw new Error('暂时无法读取结果，请刷新对话。');}check();
  if(!response.ok){if(response.status===401){state.user=null;loginPage();}throw Object.assign(new Error(typeof value.detail==='string'?value.detail:'操作未完成，请检查填写内容。'),{status:response.status});}
  return value;
 }catch(error){check();if(error.name==='AbortError')throw error;if(error instanceof TypeError)throw new Error('连接中断，请刷新对话核对结果。已填写的内容会保留。');throw error;}
 finally{current.controllers.delete(controller);}
}
function businessAssistantStoreName(){return state.stores.find(item=>String(item.id)===String(state.store))?.name||'当前门店';}
// Decode UTF-8 before framing SSE: a network chunk may split a Chinese character,
// CRLF pair, JSON string, or event. Only the documented event fields are consumed.
async function businessAssistantReadEvents(reader,onEvent,check=()=>{}){
 const decoder=new TextDecoder('utf-8',{fatal:true});let pending='',event='',data=[],size=0,finished=false;
 const dispatch=()=>{if(!data.length){event='';return;}let value;try{value=JSON.parse(data.join('\n'));}catch{throw new Error('回复格式不完整，请刷新对话核对结果。');}const kind=event||'message';event='';data=[];size=0;check();if(onEvent(kind,value)===false)finished=true;};
 const line=value=>{if(!value){dispatch();return;}if(value[0]===':')return;const split=value.indexOf(':'),field=split<0?value:value.slice(0,split);let content=split<0?'':value.slice(split+1);if(content[0]===' ')content=content.slice(1);if(field==='event')event=content;if(field==='data'){size+=content.length;if(size>2000000)throw new Error('回复过长，请刷新对话核对结果。');data.push(content);}};
 const consume=final=>{while(!finished){const end=pending.search(/[\r\n]/);if(end<0)break;if(pending[end]==='\r'&&end===pending.length-1&&!final)break;const count=pending[end]==='\r'&&pending[end+1]==='\n'?2:1;const value=pending.slice(0,end);pending=pending.slice(end+count);line(value);}if(pending.length>2000000)throw new Error('回复过长，请刷新对话核对结果。');if(final&&!finished){if(pending)line(pending);pending='';dispatch();}};
 try{while(!finished){const chunk=await reader.read();check();if(chunk.done){pending+=decoder.decode();consume(true);break;}pending+=decoder.decode(chunk.value,{stream:true});consume(false);}}
 finally{try{await reader.cancel();}catch{}reader.releaseLock?.();}
}
async function businessAssistantStreamRequest(path,body,onEvent){
 const current=businessAssistantState,version=storeContextVersion,context=businessAssistantContext(),generation=current.generation,controller=new AbortController();
 if(state.storeSwitch||!state.user||state.store==='all')throw new Error('请先选择门店。');
 const check=()=>{requireStoreContext(version,'POST');if(!businessAssistantAlive(current,generation)||context!==businessAssistantContext())throw Object.assign(new Error('门店或账号已切换。'),{staleContext:true});if(controller.signal.aborted)throw new DOMException('Stopped','AbortError');};
 current.controllers.add(controller);let result=null,problem='';
 try{
  const response=await fetch('/api/business-assistant'+path,{method:'POST',credentials:'same-origin',headers:{'X-App-Request':'1','X-Store-ID':String(state.store),'X-CSRF-Token':csrf(),'Content-Type':'application/json','Accept':'text/event-stream'},signal:controller.signal,body:JSON.stringify(body)});check();
  if(!response.ok){let value;try{value=await response.json();}catch{}check();if(response.status===401){state.user=null;loginPage();}throw Object.assign(new Error(typeof value?.detail==='string'?value.detail:'发送未完成，请刷新对话后重试。'),{status:response.status});}
  if(!response.headers.get('content-type')?.includes('text/event-stream')||!response.body?.getReader)throw new Error('暂时无法读取回复，请刷新对话核对结果。');
  await businessAssistantReadEvents(response.body.getReader(),(kind,value)=>{
   if(kind==='status'&&['thinking','responding','tool'].includes(value?.phase))onEvent(kind,{phase:value.phase,round:Number.isSafeInteger(value.round)?value.round:0});
   else if(kind==='delta'&&typeof value?.text==='string')onEvent(kind,{text:value.text});
   else if(kind==='error')problem=typeof value?.message==='string'?value.message:'回复中断，请刷新对话核对结果。';
   else if(kind==='done'){
    const session=value?.session;if(!session||String(session.id)!==String(current.session?.id)||!Array.isArray(session.messages)||!Array.isArray(session.proposals))throw new Error('对话结果不完整，请刷新后核对。');
    result=session;return false;
   }
  },check);check();
  if(!result)throw new Error(problem||'连接中断，请刷新对话核对结果。已填写的内容会保留。');
  if(problem)throw Object.assign(new Error(problem),{assistantSession:result});
  return result;
 }catch(error){if(error.name==='AbortError'||error.staleContext)throw error;if(error instanceof TypeError)throw new Error('连接中断，请刷新对话核对结果。已填写的内容会保留。');throw error;}
 finally{current.controllers.delete(controller);}
}
function businessAssistantReconcileRequest(){
 const current=businessAssistantState,last=current.session?.last_request,retry=current.retry;
 if(!current.session?.busy&&retry&&last?.request_id===retry.request_id&&['completed','interrupted'].includes(last.status)){
  if(current.draft.trim()===retry.content)current.draft='';current.retry=null;
  if(last.status==='interrupted')current.error='上次回复已停止，请核对已有内容后再发送。';
 }
 current.stream=null;
}
function businessAssistantRoute(route){
 if(typeof route!=='string'||!route||route.length>180||!/^[a-z][a-z0-9-]*(?:\/[a-zA-Z0-9_-]+)*$/.test(route))return '';
 const allowed=new Set(['work','case','cases','master','masters','vehicle-catalog','sales-quotes','procurement','repair-orders','service-intake','customer-service','customer-vehicles','warehouse','warehouse-item','vehicle-procurement','vehicle-operations','membership','membership-order','group','benefits','retail','service-orders','insurance-orders','addon-orders','invoices','business-finance','business-finance-order','aftercare','dictionaries','parameters','users','stores','transfers','transfer-exceptions','transfer-goods-recoveries','vehicle-transfers','vehicle-transport-exceptions','rework-extensions','retail-group','retail-bundles','recharge-bundles','recharge-bundle-order','member-pricing','repair-packages','vehicle-income','vehicle-operation','reconciliation','clearing','gate-visits','dossier-grants','observation-corrections','group-reconciliation','membership-rules','customer-reminders','customer-history-grants','customer-questionnaires','business-entities','vehicle-period','stock-period','warehouse-period','repair-materials','visit-activity','material-value','retail-group-rules','retail-group-rule','customer-questionnaire-report','procurement-cohort','vehicle-transport-report']);
 return allowed.has(route.split('/')[0])?route:'';
}
function businessAssistantLinks(links){const seen=new Set();return (Array.isArray(links)?links:[]).flatMap(link=>{const route=businessAssistantRoute(link?.route);if(!route||seen.has(route))return [];seen.add(route);return [`<a class="ba-record-link" href="#${E(route)}">${E(link.label||'查看单据')}</a>`];}).join('');}
function businessAssistantManualRoute(proposal){
 const path=String(proposal.operation_id||'').split(' ')[1]||'',args=proposal.details?.path_args||{},data=proposal.result?.data||{};
 let route=proposal.result?.route||proposal.manual_route||'';
 const positive=value=>Number.isSafeInteger(value)&&value>0?value:null;
 const id=positive(args.case_id)||positive(args.key)||positive(args.exception_id)||positive(args.order_id)||positive(args.id)||positive(data.id);
 if(path.startsWith('/api/flow/master/')&&typeof args.kind==='string')route='master/'+args.kind;
 else if(path.startsWith('/api/masters/')&&typeof args.kind==='string')route='masters/'+args.kind;
 else if(path.startsWith('/api/flow/cases')&&id)route='case/'+id;
 else if(route==='inventory-reports')route=({'vehicles':'vehicle-period','procurement':'procurement-cohort','warehouses':'warehouse-period','vehicle-transport':'vehicle-transport-report'})[args.kind]||'vehicle-period';
 else if(route==='stock-reports')route='stock-period';
 else if(route==='repair-material-reports')route='repair-materials';
 else if(route==='visit-activity-reports')route='visit-activity';
 else if(route==='retail-group')route=path.includes('/rules')?(id?'retail-group-rule/'+id:'retail-group-rules'):(id?'retail-group/'+id:'retail');
 else if(route==='vehicle-transport-exceptions')route=id?'vehicle-transport-exceptions/'+id:'vehicle-transfers';
 else if(route==='reconciliation'&&path.includes('/clearing'))route='clearing'+(id?'/'+id:'');
 else if(route==='membership'&&path.includes('/orders'))route=id?'membership-order/'+id:'membership';
 else if(route==='recharge-bundles'&&path.includes('/orders'))route=id?'recharge-bundle-order/'+id:'recharge-bundles';
 else if(route==='business-finance'&&path.includes('/orders'))route=id?'business-finance-order/'+id:'business-finance';
 else if(route==='customer-service'&&path.includes('/vehicles'))route='customer-vehicles'+(positive(args.vehicle_id)?'/'+args.vehicle_id:'');
 else if(route==='customer-service'&&path.includes('/reminders'))route='customer-reminders';
 else if(route==='customer-service'&&path.includes('/history/grants'))route='customer-history-grants';
 else if(route==='customer-service'&&path.includes('/questionnaires'))route=path.includes('/report')?'customer-questionnaire-report':'customer-questionnaires';
 return businessAssistantRoute(route);
}
const businessAssistantFieldNames={name:'名称',title:'事项',display_name:'姓名',customer_name:'客户姓名',customer_phone:'联系电话',phone:'联系电话',customer_id:'客户编号',case_id:'业务单编号',id:'记录编号',owner_id:'负责人编号',assignee_id:'办理人编号',amount:'金额（元）',amount_cents:'金额',quantity:'数量',quantity_milli:'数量',unit:'单位',price:'单价（元）',price_cents:'单价',unit_price_cents:'单价',business_date:'业务日期',due_date:'计划日期',delivery_due:'交车日期',result:'沟通结果',note:'说明',reason:'原因',model:'车型',brand:'品牌',series:'车系',code:'编码',model_id:'车型编号',item_id:'物资编号',supplier_id:'供应商编号',account_id:'账户编号',kind:'业务类型',version:'单据版本',action:'办理事项',payment_method:'收付方式',source:'来源',values:'填写内容',lines:'明细',store_id:'门店编号',business:'业务',vin:'车架号',plate:'车牌号',date:'日期',planned_at:'计划时间',appointment_at:'预约时间',scheduled_at:'安排时间',contact_allowed:'接受联系',active:'启用',confirm_new_customer:'另建客户',owner_name:'负责人',assignee_name:'办理人'};
function businessAssistantValue(key,value){
 if(value===null||value===undefined||value==='')return '未填写';
 if(typeof value==='boolean')return value?'是':'否';
 if(key.endsWith('_cents')&&Number.isSafeInteger(value))return money(value)+' 元';
 if(key.endsWith('_milli')&&Number.isSafeInteger(value))return number(value/1000);
 return String(value);
}
function businessAssistantFallbackFields(value,prefix='',depth=0){
 if(!value||typeof value!=='object'||depth>5)return [];
 return Object.entries(value).flatMap(([key,item])=>{
  if(['request_id','password','api_key','token','secret'].includes(key))return [];
  const label=prefix+(businessAssistantFieldNames[key]||key);
  if(item&&typeof item==='object')return businessAssistantFallbackFields(item,Array.isArray(value)?`${prefix}第 ${Number(key)+1} 项 / `:label+' / ',depth+1);
  return [{label,value:businessAssistantValue(key,item)}];
 });
}
function prerequisiteLine(proposal){
 // 中间单据不能凭空建：这一步依赖的前序事实随卡显示，员工确认前先看到要补哪一项。
 const notes=proposal.result?.prerequisites;
 if(!Array.isArray(notes)||!notes.length)return '';
 return `<p class="ba-text">办理前请先确认：${E(notes.join('；'))}</p>`;
}
function businessAssistantProposal(proposal){
 const statuses={pending:'待确认',confirmed:'已完成',executed:'已完成',completed:'已完成',succeeded:'已完成',executing:'办理中',uncertain:'待核对结果',cancelled:'已取消',expired:'已过期',failed:'未完成',rejected:'未执行'};
 const pending=proposal.status==='pending',disabled=businessAssistantState.busy||businessAssistantState.session?.busy||businessAssistantState.needsRefresh;
 const expired=proposal.expires_at&&new Date(proposal.expires_at.endsWith('Z')||/[+-]\d\d:\d\d$/.test(proposal.expires_at)?proposal.expires_at:proposal.expires_at+'Z').getTime()<=Date.now();
 const fields=Array.isArray(proposal.display_fields)?proposal.display_fields:businessAssistantFallbackFields(proposal.details?.body||{});
 const links=[...(proposal.links||[]),...(proposal.result?.links||[])],manualRoute=businessAssistantManualRoute(proposal);if(manualRoute)links.push({route:manualRoute,label:proposal.result?'查看单据':'打开原页面'});
 return `<section class="ba-proposal" data-proposal="${E(proposal.id)}"><div class="spread"><h3>${E(proposal.label||'待办理事项')}</h3><span class="pill ${pending?'warning':'info'}">${E(expired&&pending?'已过期':statuses[proposal.status]||'待核对')}</span></div>${proposal.summary?`<p class="ba-text">${E(proposal.summary)}</p>`:''}<dl class="ba-facts"><div><dt>门店</dt><dd>${E(businessAssistantStoreName())}</dd></div><div><dt>办理人</dt><dd>${E(state.user?.display_name||'本人')}</dd></div>${fields.map(field=>`<div><dt>${E(field.label)}</dt><dd>${E(field.value)}</dd></div>`).join('')}</dl>${proposal.result?.message?`<p class="ba-text">${E(proposal.result.message)}</p>`:''}${pending?prerequisiteLine(proposal):''}${businessAssistantLinks(links)}<button type="button" data-baf-action="export-proposal" data-id="${E(proposal.id)}">导出填写内容</button>${pending?`<div class="ba-proposal-actions"><button type="button" class="primary" data-ba-action="confirm" data-id="${E(proposal.id)}" ${disabled||expired?'disabled':''}>确认办理</button><button type="button" data-ba-action="cancel-proposal" data-id="${E(proposal.id)}" ${disabled?'disabled':''}>取消</button></div>`:''}</section>`;
}
function businessAssistantTurnKey(proposal){return String(proposal?.turn||'')||('card-'+String(proposal?.id||''));}
// 一轮对话里可能准备整条前序链（业主 2026-09-25 的“连续批量确认”）：先按步骤分组，再在每一步里分页。
// 分组事实来自服务端（step_order/step），没有步骤信息的旧卡片按"本轮未分步"归一组。
function businessAssistantStepKey(proposal){return String(proposal?.step||'').trim()||'';}
function businessAssistantCardGroups(proposals){
 const groups=[],seen=new Map();
 for(const proposal of proposals||[]){
  const turn=businessAssistantTurnKey(proposal),step=businessAssistantStepKey(proposal);
  const key=turn+'|'+step;
  if(!seen.has(key)){
   seen.set(key,groups.length);
   groups.push({key,turn,step,order:Number(proposal?.step_order)||0,cards:[]});
  }
  groups[seen.get(key)].cards.push(proposal);
 }
 return groups.sort((left,right)=>{
  const leftPending=left.cards.some(card=>card.status==='pending')?0:1;
  const rightPending=right.cards.some(card=>card.status==='pending')?0:1;
  if(leftPending!==rightPending)return leftPending-rightPending;
  if((left.order||0)!==(right.order||0))return (left.order||0)-(right.order||0);
  return String(left.cards[0]?.created_at||'').localeCompare(String(right.cards[0]?.created_at||''));
 });
}
function businessAssistantCardIndex(group){return Math.min(Math.max(Number(businessAssistantState.cards[group.key])||0,0),group.cards.length-1);}
// 默认折叠：一轮几十张卡先只显示当前这一张，需要通读时再"展开全部"。
function businessAssistantGroupFolded(key){return businessAssistantState.folded[key]!==false;}
function businessAssistantPager(group,index){
 const total=group.cards.length,pending=group.cards.filter(card=>card.status==='pending').length;
 const current=group.cards[index],state=String(current?.status||'');
 const busy=businessAssistantState.busy||businessAssistantState.session?.busy||businessAssistantState.needsRefresh;
 const batch=pending>1?`<button type="button" class="primary" data-ba-action="card-confirm-all" data-key="${E(group.key)}" ${busy?'disabled':''}>全部确认（${pending} 张）</button><button type="button" data-ba-action="card-cancel-all" data-key="${E(group.key)}" ${busy?'disabled':''}>全部取消</button>`:'';
 const title=group.step?`<span class="ba-stepname">${E((group.order?group.order+' · ':'')+group.step)}</span>`:'';
 return `<div class="ba-cardnav"><div class="ba-cardnav-count">${title}<strong>${total}</strong> 张${group.step?'':(group.turn?'本轮卡片':'待确认卡片')}${pending?` · 还有 ${pending} 张待确认`:' · 已全部办理'}</div><div class="row"><button type="button" class="ba-cardnav-step" data-ba-action="card-prev" data-key="${E(group.key)}" aria-label="上一张卡片" ${index<=0?'disabled':''}>‹</button><span class="ba-cardnav-pos" aria-live="polite">${index+1} / ${total}</span><button type="button" class="ba-cardnav-step" data-ba-action="card-next" data-key="${E(group.key)}" aria-label="下一张卡片" ${index>=total-1?'disabled':''}>›</button><button type="button" class="ba-cardnav-fold" data-ba-action="card-fold" data-key="${E(group.key)}">${businessAssistantGroupFolded(group.key)?'展开全部':'收起全部'}</button>${batch}</div></div><p class="ba-cardnav-hint">${state==='pending'?'核对无误后点“确认办理”（或整组“全部确认”），系统才会真正新增或修改；每张仍会单独按岗位、门店、版本和业务规则校验。':`这张已${E(({succeeded:'办理成功',failed:'未办成',cancelled:'取消',expired:'过期',uncertain:'待核对',executing:'办理中'})[state]||'结束')}。`}</p>`;
}
function businessAssistantCardGroup(group){
 // 有步骤名的组一律带组头（"第 N 步 · 步骤名"），哪怕这一步只有一张卡——否则整条链里
 // 单张卡的步骤会看不出顺序（业主 2026-09-25 要的就是按步骤分组）。
 if(group.cards.length===1&&!group.step)return businessAssistantProposal(group.cards[0]);
 const index=businessAssistantCardIndex(group);
 if(group.cards.length===1||businessAssistantGroupFolded(group.key))return `<div class="ba-cardgroup folded">${businessAssistantPager(group,index)}${businessAssistantProposal(group.cards[index])}</div>`;
 return `<div class="ba-cardgroup">${businessAssistantPager(group,index)}${group.cards.map(businessAssistantProposal).join('')}</div>`;
}
function businessAssistantCards(){
 const session=businessAssistantState.session;
 return businessAssistantCardGroups(session?.proposals||[]).map(businessAssistantCardGroup).join('');
}
// 业主 2026-09-25：卡片原来堆在对话最底部，把对话内容顶没了。现在卡片是**与对话平行的一栏**，
// 自己滚动，对话区只放对话。
function businessAssistantCardsPanel(){
 const proposals=businessAssistantState.session?.proposals||[];
 const pending=proposals.filter(card=>card.status==='pending').length;
 const working=proposals.filter(card=>['executing','uncertain'].includes(card.status)).length;
 const groups=businessAssistantCardGroups(proposals);
 const steps=groups.filter(group=>group.step).length;
 const folded=businessAssistantState.panelFolded===true;
 const busy=businessAssistantState.busy||businessAssistantState.session?.busy||businessAssistantState.needsRefresh;
 const all=pending>1?`<button type="button" class="primary" data-ba-action="cards-confirm-stepwise" ${busy?'disabled':''}>按顺序全部确认（${pending} 张）</button>`:'';
 const head=`<div class="ba-cards-head"><div><strong>待确认卡片</strong><span>${proposals.length?`${proposals.length} 张${steps?` · ${steps} 个步骤`:''}${pending?` · 待确认 ${pending}`:''}${working?` · 办理中 ${working}`:''}`:'还没有卡片'}</span></div><div class="row">${all}${proposals.length?`<button type="button" class="ba-cards-fold" data-ba-action="panel-fold" aria-expanded="${!folded}">${folded?'展开':'收起'}</button>`:''}</div></div>`;
 const empty=proposals.length?'':'<p class="ba-cards-empty">助手准备好表单后会放在这里，对话内容不会再被卡片顶走。</p>';
 return `<aside class="ba-cards" id="business-assistant-cards" aria-label="待确认卡片">${head}<div class="ba-cards-list" ${folded?'hidden':''}>${businessAssistantCards()}${empty}</div></aside>`;
}
function paintBusinessAssistantCards(){
 const host=$('#business-assistant-cards');
 if(!host||state.route!=='business-assistant'||businessAssistantState.context!==businessAssistantContext())return false;
 const panel=businessAssistantCardsPanel(),slice=panel.slice(panel.indexOf('>')+1,panel.lastIndexOf('</aside>'));
 host.innerHTML=slice;
 return true;
}
function businessAssistantNextStep(){
 const current=businessAssistantState,session=current.session;if(!session)return '';
 const proposals=session.proposals||[];
 const pending=proposals.filter(card=>card.status==='pending').length;
 const working=proposals.filter(card=>['executing','uncertain'].includes(card.status)).length;
 const last=[...(session.messages||[])].reverse().find(message=>message.role==='assistant');
 const asked=!!last&&/(继续|接着|下一步)/.test(last.content||'')&&/(发送|回复|告诉我|点击|点一)/.test(last.content||'');
 const confirmed=current.lastAction==='confirm';
 if(!pending&&!working&&!asked&&!confirmed)return '';
 const disabled=current.busy||session.busy||current.needsRefresh;
 const note=pending?`还有 ${pending} 张待确认`:(working?'有操作在办理或待核对':'刚才这一步还没办完');
 const action=businessAssistantState.lastAction==='confirm'?'已办理。接着办下一批，点这里让助手继续。':'让助手接着办下一步。';
 return `<div class="ba-nextstep"><div><strong>${E(note)}</strong><span>${E(action)}</span></div><button type="button" class="primary" data-ba-action="continue" ${disabled?'disabled':''}>继续处理</button></div>`;
}
function businessAssistantMessages(){
 const session=businessAssistantState.session,stream=businessAssistantState.stream;
 if(!session?.messages?.length&&!stream)return `<div class="ba-welcome"><h2>今天需要办什么？</h2><div class="ba-suggestions">${[
  ['建立车型目录','帮我建立本店车型目录，缺少哪些资料请逐项问我。'],['登记客户接待','帮我登记一次售前接待。'],['安排客户回访','帮我安排客户回访。'],['办理物资采购','帮我办理一次物资采购。'],['开维修工单','帮我开一张维修工单。']
 ].map(([label,prompt])=>`<button type="button" data-ba-action="suggestion" data-prompt="${E(prompt)}" ${businessAssistantState.busy?'disabled':''}>${E(label)}</button>`).join('')}</div></div>`;
 const messages=[...(session?.messages||[])];
 if(stream){if(!messages.some(message=>message.role==='user'&&message.request_id===stream.request_id))messages.push({role:'user',content:stream.content});if(stream.text)messages.push({role:'assistant',content:stream.text});}
 return messages.filter(message=>['user','assistant'].includes(message.role)).map(message=>`<article class="ba-message ba-${message.role}"><div class="ba-message-name">${message.role==='user'?'我':'业务助手'}</div><div class="ba-text">${message.role==='user'&&typeof businessAssistantFileMessage==='function'?businessAssistantFileMessage(message.content)||E(message.content):E(message.content)}</div>${businessAssistantLinks(message.links)}</article>`).join('');
}
function businessAssistantWorking(){
 const current=businessAssistantState;
 if(current.busy){const round=Number(current.stream?.round)||0;const text=({thinking:'正在思考…',responding:'正在回复…',tool:'正在准备表单…'})[current.stream?.phase]||'正在处理…';
  return `<p class="ba-working" role="status">${text}${round>1?`（第 ${round} 轮，一轮准备好的卡片会在本轮结束时一起列出）`:''}</p>`;}
 return current.session?.busy?'<p class="ba-working">这段对话正在处理，请稍后刷新。</p>':'';
}
function paintBusinessAssistantStream(){
 if(state.route!=='business-assistant'||businessAssistantState.context!==businessAssistantContext())return;
 const transcript=$('#business-assistant-messages');if(!transcript)return;const follow=transcript.scrollHeight-transcript.scrollTop-transcript.clientHeight<100;
 transcript.innerHTML=businessAssistantMessages()+businessAssistantWorking();if(follow)transcript.scrollTop=transcript.scrollHeight;
}
function businessAssistantCompose(){
 const current=businessAssistantState,ready=current.status?.ready&&!current.session?.busy&&!current.needsRefresh,disabled=current.busy||!ready;
 return `<form class="ba-compose" id="business-assistant-form"><label class="ba-input-label" for="business-assistant-input">说说要办的事</label><textarea id="business-assistant-input" name="message" rows="3" maxlength="${Number(current.status?.limits?.max_message_chars)||6000}" placeholder="例如：给张先生安排明天下午的回访" ${current.busy||current.retry?'readonly':''}>${E(current.draft)}</textarea><div class="ba-compose-bottom"><div class="row ba-compose-tools"><button type="button" data-baf-action="open" ${current.busy||current.retry?"disabled":""}>从文件填表</button><button type="button" class="ba-thinking-toggle" data-ba-action="thinking" role="switch" aria-checked="${current.thinking}" ${current.busy||current.retry?'disabled':''}>思考：${current.thinking?'开':'关'}</button><span class="ba-keyboard">Enter 发送 · Shift + Enter 换行</span></div><div class="row">${current.busy?'<button type="button" data-ba-action="stop">停止等待</button>':''}<button type="submit" class="primary" ${disabled||!current.draft.trim()?'disabled':''}>${current.busy?'处理中…':current.retry?'重试':'发送'}</button></div></div></form>`;
}
function businessAssistantChat(){
 const current=businessAssistantState;
 const notice=!current.status?.ready?`<div class="notice">${E(current.status?.message||'助手尚未启用，请联系管理员。')}</div>`:'';
 return `<div class="ba-chat">${notice}<div class="ba-transcript" id="business-assistant-messages" role="log" aria-label="业务助手对话" aria-live="polite" aria-busy="${current.busy}">${businessAssistantMessages()}${businessAssistantWorking()}</div>${businessAssistantNextStep()}<div id="business-assistant-error" class="ba-error" role="alert">${E(current.error)}</div>${businessAssistantCompose()}</div>`;
}
function businessAssistantWorkspace(){
 return `<div class="ba-workspace${(businessAssistantState.session?.proposals||[]).length?'':' no-cards'}">${businessAssistantChat()}${businessAssistantCardsPanel()}</div>`;
}
function businessAssistantIssues(){
 const categories={input:'资料填写',rule:'业务限制',system:'操作问题',model:'助手理解',unsupported:'尚不支持'};
 return `<section class="ba-issues"><div class="spread"><h2>问题清单</h2><div class="row"><button type="button" data-ba-action="report" ${!businessAssistantState.session||businessAssistantState.busy?'disabled':''}>记录问题</button><button type="button" data-ba-action="export-issues">导出</button></div></div>${businessAssistantState.issues.length?businessAssistantState.issues.map(issue=>`<article class="ba-issue"><div class="spread"><span class="pill info">${E(categories[issue.category]||'操作问题')}</span><span class="ba-date">${E(time(issue.created_at))}</span></div><p class="ba-text">${E(issue.summary)}</p>${issue.session_id?`<button type="button" class="link" data-ba-action="issue-session" data-id="${E(issue.session_id)}">查看对话</button>`:''}</article>`).join(''):empty('还没有记录问题')}</section>`;
}
function businessAssistantHTML(){
 const current=businessAssistantState;
 return heading('业务助手','',`<button type="button" data-ba-action="refresh" ${current.busy?'disabled':''}>刷新对话</button>`)+`<section class="ba-layout" id="business-assistant"><aside class="ba-history"><button type="button" class="primary ba-new" data-ba-action="new" ${current.busy?'disabled':''}>新对话</button><div class="ba-tabs"><button type="button" data-ba-action="chat" class="${current.tab==='chat'?'selected':''}">对话</button><button type="button" data-ba-action="issues" class="${current.tab==='issues'?'selected':''}" ${current.busy?'disabled':''}>问题清单</button></div><button type="button" class="ba-files-tab" data-baf-action="open" ${current.busy||current.retry?"disabled":""}>资料整理</button><nav class="ba-sessions" aria-label="对话记录">${current.sessions.map(session=>`<button type="button" data-ba-action="session" data-id="${E(session.id)}" class="${current.session?.id===session.id?'selected':''}" ${current.busy?'disabled':''}><span>${E(session.title||'新对话')}${session.busy?'<em class="ba-busy">处理中</em>':''}</span><time>${E(time(session.updated_at||session.created_at))}</time></button>`).join('')||'<p class="ba-no-history">暂无对话</p>'}</nav></aside><div class="ba-body">${current.tab==='files'&&typeof businessAssistantFilesHTML==='function'?businessAssistantFilesHTML():current.tab==='issues'?businessAssistantIssues():businessAssistantWorkspace()}</div></section>`;
}
async function businessAssistantPage(){
 if(state.store==='all')return heading('业务助手')+storeNotice();
 if(businessAssistantState.context!==businessAssistantContext()){clearBusinessAssistantSession();businessAssistantState.context=businessAssistantContext();}
 const current=businessAssistantState,generation=++current.generation;
 const [status,sessions]=await Promise.all([businessAssistantRequest('/status'),businessAssistantRequest('/sessions')]);
 if(!businessAssistantCurrent(current,generation))return '';
 current.status=status;current.sessions=sessions.items||[];
 if(current.session){const session=await businessAssistantRequest('/sessions/'+encodeURIComponent(current.session.id));if(!businessAssistantCurrent(current,generation))return '';current.session=session;}
 if(current.tab==='issues'){const issues=await businessAssistantRequest('/issues');if(!businessAssistantCurrent(current,generation))return '';current.issues=issues.items||[];}
 businessAssistantReconcileRequest();current.needsRefresh=false;if(typeof applyWorkflowAssistantIntent==='function')applyWorkflowAssistantIntent();return businessAssistantHTML();
}
function paintBusinessAssistant({focus=false}={}){
 if(state.route!=='business-assistant'||businessAssistantState.context!==businessAssistantContext())return;
 const main=$('#main');if(!main)return;main.innerHTML=businessAssistantHTML();bindBusinessAssistantPage();
 const transcript=$('#business-assistant-messages');if(transcript)transcript.scrollTop=transcript.scrollHeight;
 if(focus){const input=$('#business-assistant-input');if(input&&!input.readOnly){input.focus();input.setSelectionRange(input.value.length,input.value.length);}}
}
function bindBusinessAssistantPage(){
 if(typeof bindBusinessAssistantFiles==='function')bindBusinessAssistantFiles();
 const form=$('#business-assistant-form');if(!form)return;
 const input=form.elements.message,send=$('[type=submit]',form);
 input.addEventListener('input',()=>{businessAssistantState.draft=input.value;send.disabled=businessAssistantState.busy||!businessAssistantState.status?.ready||businessAssistantState.session?.busy||businessAssistantState.needsRefresh||!input.value.trim();});
 input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&event.keyCode!==229){event.preventDefault();if(!send.disabled)form.requestSubmit();}});
 form.addEventListener('submit',event=>{event.preventDefault();businessAssistantSend();});
 const transcript=$('#business-assistant-messages');if(transcript)transcript.scrollTop=transcript.scrollHeight;
}
function businessAssistantRememberSession(session){
 businessAssistantState.session=session;
 businessAssistantState.sessions=[session,...businessAssistantState.sessions.filter(item=>item.id!==session.id)];
}
async function businessAssistantTask(work){
 const current=businessAssistantState;if(current.busy)return;
 const generation=current.generation;current.busy=true;current.error='';paintBusinessAssistant();
 try{await work(current,generation);}catch(error){if(businessAssistantAlive(current,generation)){if(error.assistantSession){businessAssistantRememberSession(error.assistantSession);current.stream=null;}current.needsRefresh=true;current.error=error.name==='AbortError'?'已停止等待。请刷新对话核对结果，再继续办理。':error.message;}}
 finally{if(businessAssistantAlive(current,generation)){const finished=current.busy;current.busy=false;paintBusinessAssistant();if(finished&&state.route!=='business-assistant'&&!current.error)toast('业务助手已处理完这一轮，回到助手页可以看结果。');}}
}
async function businessAssistantSend(){
 const text=businessAssistantState.draft.trim();if(!text||!businessAssistantState.status?.ready||businessAssistantState.session?.busy||businessAssistantState.needsRefresh)return;
 businessAssistantState.lastAction=null;
 await businessAssistantTask(async(current,generation)=>{
  if(!current.session){const session=await businessAssistantRequest('/sessions',{method:'POST',body:{}});if(!businessAssistantCurrent(current,generation))return;businessAssistantRememberSession(session);}
  if(!current.retry||current.retry.session_id!==current.session.id)current.retry={session_id:current.session.id,request_id:requestKey(),content:text,thinking:current.thinking};
  const request=current.retry;current.thinking=request.thinking;current.draft=request.content;
  current.stream={request_id:request.request_id,content:request.content,text:'',phase:request.thinking?'thinking':'responding',round:0};paintBusinessAssistant();
  const session=await businessAssistantStreamRequest('/sessions/'+encodeURIComponent(current.session.id)+'/messages/stream',{request_id:request.request_id,content:request.content,thinking:request.thinking},(kind,value)=>{
   if(!businessAssistantAlive(current,generation))return;
   if(kind==='status'){if(value.phase==='responding'&&value.round&&value.round!==current.stream.round){current.stream.text='';current.stream.round=value.round;}current.stream.phase=value.phase;}
   else if(kind==='delta'){if(current.stream.text.length+value.text.length>200000)throw new Error('回复过长，请刷新对话核对结果。');current.stream.text+=value.text;current.stream.phase='responding';}
   paintBusinessAssistantStream();
  });
  if(!businessAssistantAlive(current,generation))return;businessAssistantRememberSession(session);current.draft='';current.retry=null;current.stream=null;
 });
}
async function businessAssistantChooseSession(id){
 await businessAssistantTask(async(current,generation)=>{const session=await businessAssistantRequest('/sessions/'+encodeURIComponent(id));if(!businessAssistantCurrent(current,generation))return;businessAssistantRememberSession(session);current.draft='';current.retry=null;current.stream=null;current.needsRefresh=false;current.tab='chat';});
}
async function businessAssistantDecide(id,confirm){
 const proposal=businessAssistantState.session?.proposals?.find(item=>String(item.id)===String(id));
 if(!proposal||proposal.status!=='pending'||businessAssistantState.needsRefresh)return;
 await businessAssistantTask(async(current,generation)=>{const session=await businessAssistantRequest(`/sessions/${encodeURIComponent(current.session.id)}/proposals/${encodeURIComponent(id)}/${confirm?'confirm':'cancel'}`,{method:'POST',body:{digest:proposal.digest}});if(!businessAssistantCurrent(current,generation))return;businessAssistantRememberSession(session);current.lastAction='confirm';businessAssistantAdvance(String(proposal.turn||'')||('card-'+String(proposal.id)),session);});
}
// 一组卡片里找下一张还没办的（同一轮内顺延，到底了就找这一组里第一张待确认）。
function businessAssistantAdvance(key,session){
 const group=businessAssistantCardGroups(session?.proposals||[]).find(item=>item.key===key);if(!group)return;
 const current=Math.min(Math.max(Number(businessAssistantState.cards[key])||0,0),group.cards.length-1);
 const after=group.cards.findIndex((card,index)=>index>current&&card.status==='pending');
 const first=group.cards.findIndex(card=>card.status==='pending');
 const target=after>=0?after:first;
 businessAssistantState.cards[key]=target>=0?target:current;
 businessAssistantState.lastAction='confirm';
}
async function businessAssistantDecideAll(key,confirm){
 const group=businessAssistantCardGroups(businessAssistantState.session?.proposals||[]).find(item=>item.key===key);
 const cards=(group?.cards||[]).filter(card=>card.status==='pending');
 if(!cards.length||businessAssistantState.needsRefresh)return;
 await businessAssistantConfirmCards(cards,confirm?{verb:'全部确认',key}:{verb:'全部取消',key});
}
// 一次点击办完一组（或按顺序办完所有步骤）：仍是逐张校验、逐张原接口，只把"点很多次"合成一次。
async function businessAssistantConfirmCards(cards,{verb,key}={}){
 if(!cards.length||businessAssistantState.needsRefresh)return;
 if(cards.length>1&&!await businessAssistantConfirmMany(cards.length,verb))return;
 await businessAssistantTask(async(current,generation)=>{
  const session=await businessAssistantRequest(`/sessions/${encodeURIComponent(current.session.id)}/proposals/batch`,
   {method:'POST',body:{action:verb==='全部取消'?'cancel':'confirm',items:cards.map(card=>({id:card.id,digest:card.digest}))}});
  if(!businessAssistantAlive(current,generation))return;
  const batch=session.batch||{};
  businessAssistantRememberSession(session);
  if(key)businessAssistantAdvance(key,session);
  const failed=(batch.items||[]).filter(item=>!['succeeded','cancelled'].includes(String(item.status)));
  current.lastAction='confirm';
  current.error=failed.length?`${verb} ${batch.done||0}/${batch.total||cards.length} 张；未办成的：`+failed.slice(0,5).map(item=>`${item.summary||''}（${item.message||''}）`).join('；')+(failed.length>5?` 等 ${failed.length} 张`:''):'';
  if(!failed.length&&verb!=='全部取消')toast(`${verb} ${batch.done||cards.length} 张已完成`);
 });
 if(!businessAssistantState.error)await businessAssistantAutoContinue();
}
// 业主 2026-09-25：确认完就该顺着上下文往下走，不该让员工再点一次。
// 只在"刚确认完、这一轮结束、还有未办完的事"时自动触发一次，绝不自动办理任何业务（仍然只准备卡片）。
async function businessAssistantAutoContinue(){
 const current=businessAssistantState,session=current.session;
 if(!session||current.busy||current.error||current.needsRefresh||!current.status?.ready)return;
 const proposals=session.proposals||[];
 const pending=proposals.filter(card=>card.status==='pending').length;
 const working=proposals.filter(card=>['executing','uncertain'].includes(card.status)).length;
 if(pending||working)return;                     // 还有卡要员工核对时，不抢着让模型往下走
 const last=[...(session.messages||[])].reverse().find(message=>message.role==='assistant');
 // 模型说"还有下一步"的常见说法都要认（"确认后一并准备""接下来""还需要…"），否则自动续办会漏。
 const asked=!!last&&/(继续|接着|接下来|下一步|再准备|还需要|确认后|等确认|一并准备|补齐)/.test(last.content||'');
 if(!asked)return;
 toast('已自动让助手接着办下一步。');
 await businessAssistantContinue('继续处理下一步');
}
function businessAssistantConfirmMany(count,verb){
 return new Promise(resolve=>{
  let settled=false;const finish=value=>{if(!settled){settled=true;resolve(value);}};
  const close=()=>{if(typeof closeModal==='function')closeModal();};
  const dialog=modal(`${verb}前请再核对一次`,
   `<form class="stack"><p class="ba-text">这 ${count} 张卡会逐张按原接口办理：每张仍单独校验岗位、门店、版本、过期时间和业务规则；办不成的会单独列出来，不影响其它张。</p><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','再核对一下')}<button type="submit" class="primary">确认${E(verb)}</button></div></form>`,
   async()=>{finish(true);close();});
  dialog.addEventListener('close',()=>finish(false),{once:true});
 });
}
async function businessAssistantContinue(text='继续处理下一步'){
 const current=businessAssistantState;
 if(current.busy||!current.status?.ready||current.session?.busy||current.needsRefresh)return;
 current.draft=text;
 await businessAssistantSend();
}
async function businessAssistantReport(){
 const current=businessAssistantState,session=current.session,context=businessAssistantContext();if(!session||current.busy)return;
 modal('记录问题',`<form class="stack"><label>遇到什么问题<select name="category"><option value="system">操作无法完成</option><option value="input">不知道怎么填写</option><option value="rule">业务条件不满足</option><option value="model">助手理解有误</option><option value="unsupported">缺少所需功能</option></select></label><label>问题说明<textarea name="summary" required maxlength="1000" rows="4" placeholder="想办什么、卡在哪一步"></textarea></label><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button type="submit" class="primary">保存</button></div></form>`,async form=>{
  if(current!==businessAssistantState||context!==businessAssistantContext())throw new Error('门店或账号已切换，请重新记录。');
  await businessAssistantRequest(`/sessions/${encodeURIComponent(session.id)}/issues`,{method:'POST',body:Object.fromEntries(new FormData(form))});
  if(current!==businessAssistantState||context!==businessAssistantContext())return;closeModal();current.tab='issues';await render();toast('问题已记录');
 });
}
document.addEventListener('click',async event=>{
 const element=event.target.closest('[data-ba-action]');if(!element||element.disabled||state.route!=='business-assistant')return;
 const action=element.dataset.baAction,current=businessAssistantState;
 try{
  if(action==='stop'){for(const controller of current.controllers)controller.abort();return;}
  // 翻页/折叠只是看的方式，处理中的时候也允许（不触发任何业务写入）。
  if(action==='card-prev'||action==='card-next'){const key=element.dataset.key,step=action==='card-next'?1:-1;current.cards[key]=Math.max(0,(Number(current.cards[key])||0)+step);if(!paintBusinessAssistantCards())paintBusinessAssistant();return;}
  if(action==='card-fold'){const key=element.dataset.key;current.folded[key]=!businessAssistantGroupFolded(key);if(!paintBusinessAssistantCards())paintBusinessAssistant();return;}
  if(action==='card-jump'){const key=element.dataset.key;current.cards[key]=Math.max(0,Number(element.dataset.index)||0);if(!paintBusinessAssistantCards())paintBusinessAssistant();return;}
  if(action==='panel-fold'){current.panelFolded=current.panelFolded!==true;if(!paintBusinessAssistantCards())paintBusinessAssistant();return;}
  if(current.busy)return;
  if(action==='new'){current.session=null;current.draft='';current.error='';current.needsRefresh=false;current.retry=null;current.stream=null;current.thinking=false;current.tab='chat';paintBusinessAssistant({focus:true});}
  else if(action==='thinking'){if(!current.retry){current.thinking=!current.thinking;paintBusinessAssistant();}}
  else if(action==='suggestion'){if(!current.retry){current.draft=element.dataset.prompt||'';paintBusinessAssistant({focus:true});}}
  else if(action==='chat'){current.tab='chat';paintBusinessAssistant();}
  else if(action==='session'||action==='issue-session')await businessAssistantChooseSession(element.dataset.id);
  else if(action==='confirm'||action==='cancel-proposal')await businessAssistantDecide(element.dataset.id,action==='confirm');
  else if(action==='card-confirm-all'||action==='card-cancel-all')await businessAssistantDecideAll(element.dataset.key,action==='card-confirm-all');
  else if(action==='cards-confirm-stepwise'){
   // “按顺序全部确认”：按步骤顺序把还没办的卡一次提交（服务端逐张、按顺序办理）。
   const pending=[...(current.session?.proposals||[])].filter(card=>card.status==='pending');
   const order=businessAssistantCardGroups(pending);
   const ordered=order.flatMap(group=>group.cards);
   await businessAssistantConfirmCards(ordered,{verb:'按顺序全部确认'});
  }
  else if(action==='continue')await businessAssistantContinue();
  else if(action==='refresh'){current.error='';await render();}
  else if(action==='issues')await businessAssistantTask(async(previous,generation)=>{const data=await businessAssistantRequest('/issues');if(!businessAssistantCurrent(previous,generation))return;previous.issues=data.items||[];previous.tab='issues';});
  else if(action==='report')await businessAssistantReport();
  else if(action==='export-issues')await download('/api/business-assistant/issues/export','业务助手问题清单.json');
 }catch(error){if(current===businessAssistantState&&current.context===businessAssistantContext()){current.error=error.message;paintBusinessAssistant();toast(error.message,true);}}
});
