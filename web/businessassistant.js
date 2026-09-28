'use strict';
// The assistant proposes existing business commands. This page never executes
// model-produced JavaScript, HTML, URLs or arbitrary HTTP requests.
let businessAssistantState;
function freshBusinessAssistantState(){return {context:null,generation:0,controllers:new Set(),status:null,sessions:[],session:null,issues:[],tab:'chat',draft:'',error:'',busy:false,needsRefresh:false,retry:null,files:null,thinking:false,stream:null,cards:{},folded:{},panelFolded:false,answers:{},lastAction:null,queueFilter:'pending',activeCardId:null,historyOpen:false,mobilePane:'chat',receipt:null,workboard:null,workPlanId:null,workError:'',workLoading:false,workSerial:0,runtimeFeatures:null,runId:null,runView:null,runSubscription:null,runStop:''};}
function businessAssistantWorkspaceModule(){return globalThis.AssistantWorkspace||null;}
function businessAssistantAnswers(id){const key=String(id);if(!businessAssistantState.answers[key])businessAssistantState.answers[key]={};return businessAssistantState.answers[key];}
function businessAssistantCardQuestions(proposal){
 const questions=Array.isArray(proposal?.questions)?proposal.questions:[];
 if(!questions.length)return {html:'',missing:[],answers:{}};
 const answers=businessAssistantAnswers(proposal.id),missing=[];
 const html=questions.map(question=>{
  const key=String(question.key||''),value=String(answers[key]??'');
  const required=question.required!==false;
  if(required&&!value.trim())missing.push(String(question.label||key));
  const control=Array.isArray(question.options)&&question.options.length
   ? `<select data-baq-key="${E(key)}" ${required?'required':''}><option value="">请选择</option>${question.options.map(option=>{const optionValue=String(option&&typeof option==='object'?option.value:option),optionLabel=String(option&&typeof option==='object'?option.label:option);return `<option value="${E(optionValue)}"${value===optionValue?' selected':''}>${E(optionLabel)}</option>`;}).join('')}</select>`
   : `<input type="${question.input_type==='date'?'date':'text'}" inputmode="${question.input_type==='integer'?'numeric':question.input_type==='decimal'?'decimal':'text'}" data-baq-key="${E(key)}" maxlength="200" value="${E(value)}" ${required?'required':''} placeholder="请填写${E(question.label||'')}">`;
  return `<label class="ba-question"><span>${E(question.label||key)}${question.unit&&!String(question.label||'').includes(question.unit)?`（${E(question.unit)}）`:''}${required?'<em>必填</em>':''}</span>${control}</label>`;
 }).join('');
 return {html:`<div class="ba-questions" data-ba-questions="${E(proposal.id)}">${html}</div>`,missing,answers};
}
businessAssistantState=freshBusinessAssistantState();
function businessAssistantContext(){return `${storeContextVersion}:${state.user?.id||''}:${state.store||''}`;}
// 退出登录/换门店只清浏览器状态：不调用 cancel、不撤销 Grant、不删除卡片。
// 即时 Run 是否继续由服务端按当前会话与权限决定；持续跟进授权在退出后仍按原合同继续。
function businessAssistantReleaseRuntime(){
 const current=businessAssistantState;
 if(current?.runSubscription){try{current.runSubscription();}catch{}current.runSubscription=null;}
 if(typeof globalThis.AssistantRuntime?.disposeContext==='function')globalThis.AssistantRuntime.disposeContext();
 if(typeof businessAssistantWorkspaceModule()?.disposeContext==='function')businessAssistantWorkspaceModule().disposeContext();
 if(current){current.runId=null;current.runView=null;current.runStop='';}
}
function clearBusinessAssistantSession(){
 if(typeof clearWorkflowContext==='function')clearWorkflowContext();
 const previous=businessAssistantState;
 for(const controller of previous.controllers)controller.abort();
 businessAssistantReleaseRuntime();
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
function businessAssistantExpired(proposal){
 const stamp=proposal?.expires_at;
 if(!stamp)return false;
 return new Date(stamp.endsWith('Z')||/[+-]\d\d:\d\d$/.test(stamp)?stamp:stamp+'Z').getTime()<=Date.now();
}
function businessAssistantProposal(proposal){
 const status=businessAssistantDisplayStatus(proposal),pending=status==='pending';
 const disabled=businessAssistantState.busy||businessAssistantState.session?.busy||businessAssistantState.needsRefresh;
 const fields=Array.isArray(proposal.display_fields)?proposal.display_fields:businessAssistantFallbackFields(proposal.details?.body||{});
 const links=[...(proposal.links||[]),...(proposal.result?.links||[])],manualRoute=businessAssistantManualRoute(proposal);
 if(manualRoute)links.push({route:manualRoute,label:'查看单据'});
 const questions=businessAssistantCardQuestions(proposal),blocked=pending&&questions.missing.length>0;
 const outcomes={uncertain:'结果尚未确定：原单可能已经提交。请先查看原单核对，不要重复办理。',executing:'这项正在办理。请刷新对话核对结果，不要重复提交。',failed:'这项没有办成。请核对下方原因和原单，再决定如何处理。',expired:'这张卡已经过期，不能继续提交。请重新查询原单后准备新卡。',cancelled:'您已取消，没有因此执行该业务。',rejected:'这张卡未执行。'};
 return `<section class="ba-proposal" data-proposal="${E(proposal.id)}"><div class="spread"><h3 tabindex="-1">${E(proposal.label||'待办理事项')}</h3><span class="pill ${pending?'warning':status==='succeeded'?'good':['failed','uncertain'].includes(status)?'bad':'info'}">${E(businessAssistantStatusName(status))}</span></div>${proposal.summary?`<p class="ba-text">${E(proposal.summary)}</p>`:''}<p class="ba-card-context">${E(businessAssistantStoreName())} · ${E(state.user?.display_name||'本人')}办理${proposal.step?` · ${E(proposal.step)}`:''}</p>${outcomes[status]?`<p class="ba-outcome-note" role="status">${E(outcomes[status])}</p>`:''}<dl class="ba-facts">${fields.map(field=>`<div><dt>${E(field.label)}</dt><dd>${E(field.value)}</dd></div>`).join('')}</dl>${pending?questions.html:''}${proposal.result?.message?`<p class="ba-text">${E(proposal.result.message)}</p>`:''}${pending?prerequisiteLine(proposal):''}<div class="ba-card-links">${businessAssistantLinks(links)}</div>${pending?`<p class="ba-question-hint" data-ba-missing ${blocked?'':'hidden'}>请先填写：${E(questions.missing.join('、'))}。</p>`:''}<details class="ba-card-tools"><summary>其他工具</summary><button type="button" data-baf-action="export-proposal" data-id="${E(proposal.id)}">导出填写内容</button></details></section>`;
}
function businessAssistantConfirmBar(proposal){
 if(businessAssistantDisplayStatus(proposal)!=='pending')return '';
 const missing=businessAssistantCardQuestions(proposal).missing;
 const disabled=businessAssistantState.busy||businessAssistantState.session?.busy||businessAssistantState.needsRefresh;
 return `<div class="ba-confirm-bar" data-ba-confirm-bar="${E(proposal.id)}"><button type="button" class="ba-fill-link" data-ba-action="fill-missing" data-id="${E(proposal.id)}" ${missing.length?'':'hidden'}>填写必填项（${missing.length}）</button><div class="ba-proposal-actions"><button type="button" class="primary" data-ba-action="confirm" data-id="${E(proposal.id)}" ${disabled||missing.length?'disabled':''}>${missing.length?'补全必填项后确认':'确认办理'}</button><button type="button" data-ba-action="cancel-proposal" data-id="${E(proposal.id)}" ${disabled?'disabled':''}>取消</button></div></div>`;
}
function businessAssistantTurnKey(proposal){return String(proposal?.turn||'')||('card-'+String(proposal?.id||''));}
// 一轮对话里可能准备整条前序链（业主 2026-09-25 的“连续批量确认”）：先按步骤分组，再在每一步里分页。
// 分组事实来自服务端（step_order/step），没有步骤信息的旧卡片按"本轮未分步"归一组。
function businessAssistantStepKey(proposal){return String(proposal?.step||'').trim()||'';}
function businessAssistantCardGroups(proposals){
 const groups=[],seen=new Map(),turns=new Map();
 // Keep each conversation turn together, then order its steps. Do not sort by
 // status: completing one item must not reorder unrelated turns or branches.
 const ordered=[...(proposals||[])].sort((a,b)=>String(a.created_at||'').localeCompare(String(b.created_at||''))||String(a.id).localeCompare(String(b.id),undefined,{numeric:true}));
 for(const proposal of ordered){
  const turn=businessAssistantTurnKey(proposal),step=businessAssistantStepKey(proposal),key=JSON.stringify([turn,step]);
  if(!turns.has(turn))turns.set(turn,turns.size);
  if(!seen.has(key)){seen.set(key,groups.length);groups.push({key,turn,step,order:Number(proposal.step_order)||0,turnOrder:turns.get(turn),cards:[]});}
  groups[seen.get(key)].cards.push(proposal);
 }
 return groups.sort((a,b)=>a.turnOrder-b.turnOrder||a.order-b.order);
}
function businessAssistantDisplayStatus(card){
 if(card?.status==='pending'&&businessAssistantExpired(card))return 'expired';
 return ['confirmed','executed','completed'].includes(card?.status)?'succeeded':String(card?.status||'uncertain');
}
function businessAssistantStatusName(status){return ({pending:'待确认',succeeded:'已完成',executing:'办理中',uncertain:'待核对结果',cancelled:'已取消',expired:'已过期',failed:'未办成',rejected:'未执行'})[status]||'待核对';}
function businessAssistantBucket(card){
 const status=businessAssistantDisplayStatus(card);
 return status==='pending'?'pending':['succeeded','cancelled','rejected'].includes(status)?'history':'attention';
}
function businessAssistantQueue(){
 const groups=businessAssistantCardGroups(businessAssistantState.session?.proposals||[]),all=groups.flatMap(g=>g.cards);
 const buckets={pending:[],attention:[],history:[]};all.forEach(card=>buckets[businessAssistantBucket(card)].push(card));
 const filter=Object.hasOwn(buckets,businessAssistantState.queueFilter)?businessAssistantState.queueFilter:'pending';
 const visible=buckets[filter];
 const selected=visible.find(card=>String(card.id)===String(businessAssistantState.activeCardId))||visible[0]||null;
 businessAssistantState.activeCardId=selected?.id||null;
 const group=selected?groups.find(g=>g.cards.some(c=>c.id===selected.id)):null;
 return {groups,all,buckets,filter,visible,selected,group};
}
function businessAssistantCardsPanel(){
 const q=businessAssistantQueue(),current=businessAssistantState,selected=q.selected;
 const index=selected?q.visible.indexOf(selected):-1,busy=current.busy||current.session?.busy||current.needsRefresh;
 const groupPending=(q.group?.cards||[]).filter(c=>businessAssistantDisplayStatus(c)==='pending');
 const progress=q.group?`${q.group.step||'同一轮事项'} · 已完成 ${q.group.cards.filter(c=>businessAssistantDisplayStatus(c)==='succeeded').length} / ${q.group.cards.length} 项`:'';
 const chooser=selected?`<div class="ba-queue-navigation"><button type="button" data-ba-action="queue-prev" aria-label="查看上一项" ${index<=0?'disabled':''}>←</button><label class="ba-queue-choose"><span class="ba-visually-hidden">选择要查看的事项</span><select id="ba-queue-select" aria-label="选择要查看的事项">${q.visible.map((card,i)=>`<option value="${E(card.id)}" ${card.id===selected.id?'selected':''}>${i+1} / ${q.visible.length} · ${E(card.summary||card.label||'办理事项')}</option>`).join('')}</select></label><button type="button" data-ba-action="queue-next" aria-label="查看下一项" ${index>=q.visible.length-1?'disabled':''}>→</button></div><p class="ba-queue-progress">${E(progress)}</p>`:'';
 const batch=groupPending.length>1?`<details class="ba-batch-tools"><summary>本组有 ${groupPending.length} 项待确认 · 批量办理</summary><p>先逐项核对。本组按顺序逐项提交；遇到未办成或结果不明就暂停，已成功的不会回滚。</p><div class="row"><button type="button" data-ba-action="card-confirm-all" data-key="${E(q.group.key)}" ${busy?'disabled':''}>核对并办理本组</button><button type="button" data-ba-action="card-cancel-all" data-key="${E(q.group.key)}" ${busy?'disabled':''}>取消本组待确认卡</button></div></details>`:'';
 const emptyText=q.filter==='pending'?'目前没有待确认卡。已办完的在“已结束”，异常结果在“需处理”。':q.filter==='attention'?'目前没有需要核对或重新准备的卡片。':'目前没有已结束的卡片。';
 return `<aside class="ba-cards" id="business-assistant-cards" aria-label="办理事项"><div class="ba-cards-head"><div><strong>办理事项</strong></div></div><div class="ba-queue-tabs" aria-label="办理事项状态">${[['pending','待确认'],['attention','需处理'],['history','已结束']].map(([key,label])=>`<button type="button" data-ba-action="queue-filter" data-filter="${key}" aria-pressed="${q.filter===key}">${label} ${q.buckets[key].length}</button>`).join('')}</div><div class="ba-cards-list">${businessAssistantState.receipt?`<p class="ba-card-receipt" role="status">${E(businessAssistantState.receipt)}</p>`:''}${chooser}${selected?businessAssistantProposal(selected):`<p class="ba-cards-empty">${emptyText}</p>`}${batch}</div>${selected?businessAssistantConfirmBar(selected):''}</aside>`;
}
function paintBusinessAssistantCards(){
 const host=$('#business-assistant-cards');if(!host||state.route!=='business-assistant'||businessAssistantState.context!==businessAssistantContext())return false;
 const before=host.querySelector('[data-proposal]')?.dataset.proposal,top=host.querySelector('.ba-cards-list')?.scrollTop||0;
 const panel=businessAssistantCardsPanel();host.innerHTML=panel.slice(panel.indexOf('>')+1,panel.lastIndexOf('</aside>'));
 const list=host.querySelector('.ba-cards-list');if(list)list.scrollTop=before===String(businessAssistantState.activeCardId)?top:0;
 return true;
}
function businessAssistantNextStep(){
 const current=businessAssistantState,session=current.session;if(!session)return '';
 const q=businessAssistantQueue(),busy=current.busy||session.busy||current.needsRefresh;
 let title='',text='',action='',label='';
 if(q.buckets.pending.length){title=`需要您核对 ${q.buckets.pending.length} 项`;text='先看清填写内容，再确认办理；尚未提交的卡片不算已办好。';action='show-cards';label='查看待确认事项';}
 else if(q.buckets.attention.length){title=`有 ${q.buckets.attention.length} 项需要处理`;text='先核对未完成、已过期或结果不明的事项，不要重复提交。';action='show-attention';label='查看需要处理的事项';}
 else if(q.all.length){title='当前卡片已处理';text=`当前列表：成功 ${q.all.filter(c=>businessAssistantDisplayStatus(c)==='succeeded').length} 项；取消或未执行 ${q.all.filter(c=>['cancelled','rejected'].includes(businessAssistantDisplayStatus(c))).length} 项。下一步以原单待办为准。`;action='continue';label='请助手查询下一步';}
 if(!title)return '';
 const refreshPlan=action==='continue'&&Boolean(session.work_plans?.length);
 if(refreshPlan)label='刷新原单进度';
 const receipt=current.receipt?`<p class="ba-receipt" role="status">${E(current.receipt)}</p>`:'';
 return `<div class="ba-nextstep"><div>${receipt}<strong>${E(title)}</strong><span>${E(text)}</span></div><button type="button" ${action==='continue'&&busy?'disabled':''} class="primary" ${refreshPlan?'data-baw-action="refresh"':`data-ba-action="${action}"`}>${E(label)}</button></div>`;
}
// M6.4：欢迎示例最多四个，来自发布流程目录与岗位常用流程的交集，按真实可进入权限过滤；
// readonly 岗位与集团汇总只给查询示例；点击只预填草稿，不创建会话、不发模型。
function businessAssistantReadonlyRole(role){return ['auditor','readonly','statistics','finance_view','group_view'].includes(String(role||''));}
function businessAssistantWelcomeFallback(){
 return [['查我的待办','查一下现在需要我处理的原单待办和任务，只读取并说明。'],
         ['查客户资料','按客户姓名查一下他的车辆、接待、订单记录，只读取并说明。'],
         ['这项业务怎么办','说明这项业务当前还需要哪些资料和步骤，只读取不提交。'],
         ['查合同和收款','查一下这个客户的合同、收款与发票状态，只读取并说明。']];
}
async function businessAssistantWelcomeExamples(){
 const current=businessAssistantState,role=String(state.user?.role||''),store=String(state.store||'');
 if(Array.isArray(current.welcomeExamples))return current.welcomeExamples;
 const order=(typeof UX_COMMON_WORKFLOWS==='object'&&UX_COMMON_WORKFLOWS)
   ?(UX_COMMON_WORKFLOWS[role]||UX_COMMON_WORKFLOWS.default||[]):[];
 const rank=id=>{const index=order.indexOf(id);return index<0?order.length:index;};
 let picked=[];
 try{
  const response=await fetch('/static/workflow-guides.json',{credentials:'same-origin'});
  const data=response&&response.ok?await response.json():null;
  const items=Array.isArray(data&&data.workflows)?data.workflows:[];
  const guide=globalThis.WorkflowGuides;
  const readonly=businessAssistantReadonlyRole(role)||store==='all';
  picked=items.filter(item=>{
    if(!item||typeof item.id!=='string'||!item.assistant||!item.assistant.prompt)return false;
    if(readonly&&item.assistant.intent&&item.assistant.intent!=='query_status')return false;
    if(!guide||typeof guide.canEnter!=='function')return true;
    try{return guide.canEnter(item,role,store);}catch(error){return false;}
  }).sort((a,b)=>rank(a.id)-rank(b.id)).slice(0,4).map(item=>[String(item.title||item.id),String(guide&&guide.assistantPrompt?guide.assistantPrompt(item):item.assistant.prompt)]);
 }catch(error){picked=[];}
 current.welcomeExamples=picked.length?picked:businessAssistantWelcomeFallback().slice(0,4);
 return current.welcomeExamples;
}
function businessAssistantMessages(){
 const session=businessAssistantState.session,stream=businessAssistantState.stream;
 if(!session?.messages?.length&&!stream)return `<div class="ba-welcome"><h2>今天需要办什么？</h2><div class="ba-suggestions">${businessAssistantWelcomeExamples().map(([label,prompt])=>`<button type="button" data-ba-action="suggestion" data-prompt="${E(prompt)}" ${businessAssistantState.busy?'disabled':''}>${E(label)}</button>`).join('')}</div></div>`;
 const messages=[...(session?.messages||[])];
 if(stream){if(!messages.some(message=>message.role==='user'&&message.request_id===stream.request_id))messages.push({role:'user',content:stream.content});if(stream.text)messages.push({role:'assistant',content:stream.text});}
 return messages.filter(message=>['user','assistant'].includes(message.role)).map(message=>`<article class="ba-message ba-${message.role}"><div class="ba-message-name">${message.role==='user'?'我':'业务助手'}</div><div class="ba-text">${message.role==='user'&&typeof businessAssistantFileMessage==='function'?businessAssistantFileMessage(message.content)||E(message.content):E(message.content)}</div>${businessAssistantLinks(message.links)}</article>`).join('');
}
function businessAssistantWorking(){
 const current=businessAssistantState;
 if(current.busy){const round=Number(current.stream?.round)||0;const text=({thinking:'正在思考…',responding:'正在回复…',tool:'正在准备表单…'})[current.stream?.phase]||'正在处理…';
  return `<p class="ba-working" role="status">${text}${round>1?`（第 ${round} 轮，一轮准备好的卡片会在本轮结束时一起列出）`:''}</p>`;}
 // 局部发送结束不等于 Run 结束：运行期间按服务端事件显示进度，只有服务端终态才收尾。
 if(current.runId){const phase=({thinking:'正在思考…',responding:'正在回复…',tool:'正在准备表单…'})[current.stream?.phase]||'正在处理…';
  return `<p class="ba-working" role="status">${current.stream?.text?E(current.stream.text):phase}</p>`;}
 if(current.runStop)return `<p class="ba-working" role="status">${E(current.runStop)}</p>`;
 return current.session?.busy?'<p class="ba-working">这段对话正在处理，请稍后刷新。</p>':'';
}
function paintBusinessAssistantStream(){
 if(state.route!=='business-assistant'||businessAssistantState.context!==businessAssistantContext())return;
 const transcript=$('#business-assistant-messages');if(!transcript)return;const follow=transcript.scrollHeight-transcript.scrollTop-transcript.clientHeight<100;
 transcript.innerHTML=businessAssistantMessages()+businessAssistantWorking();if(follow)transcript.scrollTop=transcript.scrollHeight;
}
function businessAssistantCompose(){
 const current=businessAssistantState,ready=current.status?.ready&&!current.session?.busy&&!current.needsRefresh,disabled=current.busy||!ready;
 return `<form class="ba-compose" id="business-assistant-form"><label class="ba-input-label" for="business-assistant-input">说说要办的事</label><textarea id="business-assistant-input" name="message" rows="3" maxlength="${Number(current.status?.limits?.max_message_chars)||6000}" placeholder="例如：给张先生安排明天下午的回访" ${current.busy||current.retry?'readonly':''}>${E(current.draft)}</textarea><div class="ba-compose-bottom"><div class="row ba-compose-tools"><button type="button" data-baf-action="open" ${current.busy||current.retry?"disabled":""}>从文件填表</button><button type="button" class="ba-thinking-toggle" data-ba-action="thinking" role="switch" aria-checked="${current.thinking}" ${current.busy||current.retry?'disabled':''}>思考：${current.thinking?'开':'关'}</button><span class="ba-keyboard">Enter 发送 · Shift + Enter 换行</span></div><div class="row">${businessAssistantStopButtonHTML()}<button type="submit" class="primary" ${disabled||!current.draft.trim()?'disabled':''}>${current.busy?'处理中…':current.retry?'重试':'发送'}</button></div></div></form>`;
}
function businessAssistantChat(){
 const current=businessAssistantState;
 const notice=!current.status?.ready?`<div class="notice">${E(current.status?.message||'助手尚未启用，请联系管理员。')}</div>`:'';
 return `<div class="ba-chat">${notice}<div class="ba-transcript" id="business-assistant-messages" role="log" aria-label="业务助手对话" aria-live="polite" aria-busy="${current.busy}">${businessAssistantMessages()}${businessAssistantWorking()}</div>${businessAssistantNextStep()}<div id="business-assistant-error" class="ba-error" role="alert">${E(current.error)}</div>${businessAssistantCompose()}</div>`;
}
function businessAssistantWorkspace(){
 const current=businessAssistantState,q=businessAssistantQueue(),hasCards=q.all.length>0||Boolean(current.session?.work_plans?.length);
 const sidebar=businessAssistantWorkspaceModule()?.renderSidebar?.()||'';
 // M6.3：事项栏 + 当前事项两列；当前事项内固定为标题、计划、消息流、确认卡、输入区。
 return `<div class="ba-pane-tabs" aria-label="切换对话与办理事项"><button type="button" data-baws-action="drawer" aria-expanded="false" aria-controls="ba-sidebar-root">我的事项</button><button type="button" data-ba-action="pane-chat" aria-pressed="${current.mobilePane!=='cards'}">对话</button><button type="button" data-ba-action="pane-cards" aria-pressed="${current.mobilePane==='cards'}">办理事项 ${q.buckets.pending.length+q.buckets.attention.length}</button></div>`
  +`<div class="ba-runtime-workspace" data-pane="${E(current.mobilePane)}"><div class="ba-side-host" id="ba-sidebar-root" aria-label="我的事项">${sidebar}</div><div class="ba-side-mask" data-baws-action="drawer-close"></div>`
  +`<section class="ba-current" id="ba-current"><h2 id="ba-current-heading">${E(current.session?.title||'新对话')}</h2><div id="ba-current-plan"></div><div class="ba-current-flow${hasCards?'':' no-cards'}">${businessAssistantChat()}${businessAssistantCardsPanel()}</div></section></div>`;
}
function businessAssistantIssues(){
 const categories={input:'资料填写',rule:'业务限制',system:'操作问题',model:'助手理解',unsupported:'尚不支持'};
 return `<section class="ba-issues"><div class="spread"><h2>问题清单</h2><div class="row"><button type="button" data-ba-action="report" ${!businessAssistantState.session||businessAssistantState.busy?'disabled':''}>记录问题</button><button type="button" data-ba-action="export-issues">导出</button></div></div>${businessAssistantState.issues.length?businessAssistantState.issues.map(issue=>`<article class="ba-issue"><div class="spread"><span class="pill info">${E(categories[issue.category]||'操作问题')}</span><span class="ba-date">${E(time(issue.created_at))}</span></div><p class="ba-text">${E(issue.summary)}</p>${issue.session_id?`<button type="button" class="link" data-ba-action="issue-session" data-id="${E(issue.session_id)}">查看对话</button>`:''}</article>`).join(''):empty('还没有记录问题')}</section>`;
}
function businessAssistantHTML(){
 const current=businessAssistantState;
 return heading('业务助手','',`<button type="button" data-ba-action="refresh" ${current.busy?'disabled':''}>刷新结果</button>`)+`<section class="ba-layout" id="business-assistant"><div class="ba-toolbar"><div class="row"><button type="button" data-ba-action="new" ${current.busy?'disabled':''}>新对话</button><button type="button" data-ba-action="history" aria-expanded="${current.historyOpen}">历史对话（${current.sessions.length}）</button><span class="ba-current-title">${E(current.session?.title||'新对话')}</span></div><select class="ba-view-select" id="ba-view-select" aria-label="助手功能"><option value="chat" ${current.tab==='chat'?'selected':''}>办理业务</option><option value="files" ${current.tab==='files'?'selected':''}>资料整理</option><option value="issues" ${current.tab==='issues'?'selected':''}>问题清单</option></select><div class="ba-tabs"><button type="button" data-ba-action="chat" class="${current.tab==='chat'?'selected':''}">办理业务</button><button type="button" data-baf-action="open" ${current.busy||current.retry?'disabled':''}>资料整理</button><button type="button" data-ba-action="issues" ${current.busy?'disabled':''}>问题清单</button></div></div>${current.historyOpen?`<nav class="ba-history-popover" aria-label="历史对话"><div class="ba-sessions">${current.sessions.map(session=>`<button type="button" data-ba-action="session" data-id="${E(session.id)}" class="${current.session?.id===session.id?'selected':''}" ${current.busy?'disabled':''}><span>${E(session.title||'新对话')}${session.busy?' · 处理中':''}</span><time>${E(time(session.updated_at||session.created_at))}</time></button>`).join('')||'<p>暂无历史对话。</p>'}</div></nav>`:''}<div class="ba-body">${current.tab==='files'&&typeof businessAssistantFilesHTML==='function'?businessAssistantFilesHTML():current.tab==='issues'?businessAssistantIssues():businessAssistantWorkspace()}</div></section>`;
}
async function businessAssistantPage(){
 if(state.store==='all')return heading('业务助手')+storeNotice();
 if(businessAssistantState.context!==businessAssistantContext()){clearBusinessAssistantSession();businessAssistantState.context=businessAssistantContext();}
 const current=businessAssistantState;if(current.busy)return businessAssistantHTML();const generation=++current.generation;
 businessAssistantWorkspaceModule()?.load?.();businessAssistantWelcomeExamples();
 const [status,sessions]=await Promise.all([businessAssistantRequest('/status'),businessAssistantRequest('/sessions')]);
 if(!businessAssistantCurrent(current,generation))return '';
 current.status=status;current.sessions=sessions.items||[];
 if(current.session){const session=await businessAssistantRequest('/sessions/'+encodeURIComponent(current.session.id));if(!businessAssistantCurrent(current,generation))return '';current.session=session;}
 if(current.tab==='issues'){const issues=await businessAssistantRequest('/issues');if(!businessAssistantCurrent(current,generation))return '';current.issues=issues.items||[];}
 if(typeof businessAssistantRefreshWork==='function')await businessAssistantRefreshWork(current,generation);
 if(!businessAssistantCurrent(current,generation))return '';
 businessAssistantReconcileRequest();current.needsRefresh=false;if(typeof applyWorkflowAssistantIntent==='function')applyWorkflowAssistantIntent();return businessAssistantHTML();
}
function paintBusinessAssistant({focus=false}={}){
 if(state.route!=='business-assistant'||businessAssistantState.context!==businessAssistantContext())return;
 const main=$('#main');if(!main)return;
 const old=$('#business-assistant-messages'),follow=!old||old.scrollHeight-old.scrollTop-old.clientHeight<100,top=old?.scrollTop||0;
 const input=document.activeElement,restoreInput=input?.id==='business-assistant-input',selection=restoreInput?[input.selectionStart,input.selectionEnd]:null;
 main.innerHTML=businessAssistantHTML();bindBusinessAssistantPage();
 const transcript=$('#business-assistant-messages');if(transcript)transcript.scrollTop=follow?transcript.scrollHeight:top;
 if(focus||restoreInput){const text=$('#business-assistant-input');if(text&&!text.readOnly){text.focus({preventScroll:true});text.setSelectionRange(...(selection||[text.value.length,text.value.length]));}}
}
function bindBusinessAssistantPage(){
 if(typeof bindBusinessAssistantFiles==='function')bindBusinessAssistantFiles();
 businessAssistantWorkspaceModule()?.mount?.(document.getElementById('ba-sidebar-root'));
 const form=$('#business-assistant-form');if(!form)return;
 const input=form.elements.message,send=$('[type=submit]',form);
 input.addEventListener('input',()=>{businessAssistantState.draft=input.value;send.disabled=businessAssistantState.busy||!businessAssistantState.status?.ready||businessAssistantState.session?.busy||businessAssistantState.needsRefresh||!input.value.trim();});
 input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&event.keyCode!==229){event.preventDefault();if(!send.disabled)form.requestSubmit();}});
 form.addEventListener('submit',event=>{event.preventDefault();businessAssistantSend();});
}
function businessAssistantRememberSession(session){
 const previous=businessAssistantState.session,newest=session.work_plans?.[0]?.id;
 if(previous?.id!==session.id){businessAssistantState.workboard=null;businessAssistantState.workPlanId=null;businessAssistantState.workError='';businessAssistantState.workSerial++;}
 else if(newest&&newest!==previous.work_plans?.[0]?.id){businessAssistantState.workboard=null;businessAssistantState.workPlanId=newest;businessAssistantState.workError='';businessAssistantState.workSerial++;}
 businessAssistantState.session=session;
 businessAssistantState.sessions=[session,...businessAssistantState.sessions.filter(item=>item.id!==session.id)];
 // 刷新/重开后按服务器记录的 last_request.run_id 恢复；null 表示没有可恢复引用，不按消息位置猜。
 businessAssistantResumeRuntimeRun();
}
async function businessAssistantTask(work){
 const current=businessAssistantState;if(current.busy)return;
 const generation=current.generation;current.busy=true;current.error='';paintBusinessAssistant();
 try{await work(current,generation);}catch(error){if(businessAssistantAlive(current,generation)){if(error.assistantSession){businessAssistantRememberSession(error.assistantSession);current.stream=null;}current.needsRefresh=true;current.error=error.name==='AbortError'?'已停止等待。请刷新对话核对结果，再继续办理。':error.message;}}
 finally{if(businessAssistantAlive(current,generation)){if(typeof businessAssistantRefreshWork==='function')await businessAssistantRefreshWork(current,generation);if(!businessAssistantAlive(current,generation))return;const finished=current.busy;current.busy=false;paintBusinessAssistant();if(finished&&state.route!=='business-assistant'&&!current.error)toast('业务助手已处理完这一轮，回到助手页可以看结果。');}}
}
async function businessAssistantRuntimeFeatures(){
 const current=businessAssistantState;
 if(current.runtimeFeatures)return current.runtimeFeatures;
 try{const view=await businessAssistantRequest('/workspace');current.runtimeFeatures=view?.features||{};}
 catch(error){current.runtimeFeatures=null;}  // 读取失败绝不能改走另一个入口重发同一句话
 return current.runtimeFeatures;
}
// succeeded 的固定中文展示：只表示"本次准备已完成"，不代表业务已办理完成。
function businessAssistantRunText(status){return status==='succeeded'?'本次准备已完成':status==='cancelled'?'本次准备已停止':'本次准备未完成，请核对后继续。';}
function businessAssistantStopButtonHTML(){
 const current=businessAssistantState;
 const canCancel=current.runId&&Array.isArray(current.runView?.allowed_actions)&&current.runView.allowed_actions.includes('cancel');
 if(canCancel)return '<button type="button" data-ba-action="stop">停止本次准备</button>';
 return current.busy&&!current.runId?'<button type="button" data-ba-action="stop">停止等待</button>':'';
}
function businessAssistantWatchRuntimeRun(runId){
 const runtime=globalThis.AssistantRuntime,current=businessAssistantState;
 if(!runtime||!runId||current.runId===runId&&current.runSubscription)return;
 if(current.runSubscription){try{current.runSubscription();}catch{}current.runSubscription=null;}
 current.runId=String(runId);current.runStop='';
 current.runSubscription=runtime.subscribeRun(current.runId,event=>{
  if(!businessAssistantAlive(current,current.generation))return;
  if(event.type!=='view')return;
  current.runView=event.view;
  const display=event.view?.display;
  if(display&&typeof display.text==='string'&&display.text&&Number.isSafeInteger(display.revision)){
   current.stream={request_id:current.retry?.request_id||'',content:current.retry?.content||'',text:display.text,phase:display.phase||'responding',round:0};
  }
  if(event.session)businessAssistantRememberSession(event.session);
  const status=event.view?.status;
  if(['succeeded','failed','cancelled'].includes(status)){
   current.runStop=businessAssistantRunText(status);current.stream=null;current.retry=null;
   if(current.runSubscription){try{current.runSubscription();}catch{}current.runSubscription=null;}
   current.runId=null;
  }
  paintBusinessAssistant();
 });
}
async function businessAssistantResumeRuntimeRun(){
 const current=businessAssistantState;
 const runId=current.session?.last_request?.run_id;
 if(!runId||current.runId===String(runId)||!globalThis.AssistantRuntime)return;
 if(typeof businessAssistantRequest!=='function')return;
 const features=await businessAssistantRuntimeFeatures();
 if(!features?.runtime||!businessAssistantAlive(current,current.generation))return;
 businessAssistantWatchRuntimeRun(runId);
}
async function businessAssistantSendRuntime(text){
 if(!globalThis.AssistantRuntime?.submitRun)throw new Error('本页执行客户端未就绪，请刷新后重试。');
 await businessAssistantTask(async(current,generation)=>{
  if(!current.session){const session=await businessAssistantRequest('/sessions',{method:'POST',body:{}});if(!businessAssistantCurrent(current,generation))return;businessAssistantRememberSession(session);}
  if(!current.retry||current.retry.session_id!==current.session.id)current.retry={session_id:current.session.id,request_id:requestKey(),content:text,thinking:current.thinking};
  const request=current.retry;current.thinking=request.thinking;current.draft=request.content;
  current.stream={request_id:request.request_id,content:request.content,text:'',phase:request.thinking?'thinking':'responding',round:0};paintBusinessAssistant();
  let view;
  try{view=await globalThis.AssistantRuntime.submitRun(current.session.id,{request_id:request.request_id,content:request.content,thinking:request.thinking});}
  catch(error){current.stream=null;throw error;}  // 结果未知时保留同一 request_id 的提交记录供重试
  if(!businessAssistantCurrent(current,generation))return;
  current.runView=view;current.runStop='';
  if(current.draft.trim()===request.content.trim())current.draft='';  // 只清与已提交内容完全一致的输入
  paintBusinessAssistant();
  businessAssistantWatchRuntimeRun(view.id);
 });
}
async function businessAssistantSend(){
 const text=businessAssistantState.draft.trim();if(!text||!businessAssistantState.status?.ready||businessAssistantState.session?.busy||businessAssistantState.needsRefresh)return;
 businessAssistantState.lastAction=null;
 const features=await businessAssistantRuntimeFeatures();
 if(features?.runtime)return businessAssistantSendRuntime(text);
 return businessAssistantSendLegacy(text);
}
async function businessAssistantSendLegacy(text){
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
 if(businessAssistantState.draft.trim()||businessAssistantState.retry){toast('当前输入框里还有未发送的内容，请先发送或自行清空后再切换对话。',true);return;}
 await businessAssistantTask(async(current,generation)=>{const session=await businessAssistantRequest('/sessions/'+encodeURIComponent(id));if(!businessAssistantAlive(current,generation))return;businessAssistantRememberSession(session);current.retry=null;current.stream=null;current.needsRefresh=false;current.tab='chat';current.activeCardId=null;current.queueFilter='pending';current.receipt=null;current.historyOpen=false;});
}
async function businessAssistantDecide(id,confirm){
 const current=businessAssistantState,proposal=current.session?.proposals?.find(item=>String(item.id)===String(id));
 if(!proposal||proposal.status!=='pending'||current.needsRefresh||current.busy||current.session?.busy)return;
 if(confirm){const missing=businessAssistantCardQuestions(proposal).missing;if(missing.length){toast('请先填写：'+missing.join('、'),true);return;}if(businessAssistantExpired(proposal)){toast('这张卡已过期，请重新查询原单。',true);return;}}
 const answers=confirm?businessAssistantAnswers(proposal.id):undefined;
 const payload=confirm&&Array.isArray(proposal.questions)&&proposal.questions.length?{digest:proposal.digest,answers}:{digest:proposal.digest};
 await businessAssistantTask(async(previous,generation)=>{
  const session=await businessAssistantRequest(`/sessions/${encodeURIComponent(previous.session.id)}/proposals/${encodeURIComponent(id)}/${confirm?'confirm':'cancel'}`,{method:'POST',body:payload});
  if(!businessAssistantAlive(previous,generation))return;businessAssistantRememberSession(session);
  const settled=session.proposals?.find(c=>String(c.id)===String(id)),status=businessAssistantDisplayStatus(settled);
  previous.lastAction=confirm?'confirm':'cancel';previous.receipt=`${businessAssistantStatusName(status)}：${proposal.summary||proposal.label||'本次事项'}`;
  if(!settled){previous.needsRefresh=true;previous.error='未读取到这张卡的结果，请刷新后核对，不要重复办理。';return;}
  businessAssistantAdvance(id,session);
 });
}
function businessAssistantAdvance(id,session){
 const current=businessAssistantState,all=businessAssistantCardGroups(session?.proposals||[]).flatMap(g=>g.cards);
 const old=all.find(c=>String(c.id)===String(id));
 if(old&&businessAssistantBucket(old)==='attention'){current.queueFilter='attention';current.activeCardId=old.id;return;}
 const index=all.findIndex(c=>String(c.id)===String(id));
 const pending=all.find((c,i)=>i>index&&businessAssistantBucket(c)==='pending')||all.find(c=>businessAssistantBucket(c)==='pending');
 const next=pending||all.find(c=>businessAssistantBucket(c)==='attention')||old||all.at(-1);
 current.queueFilter=next?businessAssistantBucket(next):'pending';current.activeCardId=next?.id||null;
}
async function businessAssistantDecideAll(key,confirm){
 const group=businessAssistantCardGroups(businessAssistantState.session?.proposals||[]).find(item=>item.key===key);
 const cards=(group?.cards||[]).filter(card=>businessAssistantDisplayStatus(card)==='pending');
 if(!cards.length||businessAssistantState.needsRefresh)return;
 await businessAssistantConfirmCards(cards,confirm?{verb:'全部确认',key}:{verb:'全部取消',key});
}
async function businessAssistantConfirmCards(cards,{verb='全部确认',key}={}){
 const current=businessAssistantState,context=businessAssistantContext(),sessionId=current.session?.id,confirm=verb!=='全部取消';
 if(!cards.length||current.needsRefresh||current.busy||current.session?.busy)return;
 const live=new Map((current.session?.proposals||[]).map(c=>[String(c.id),c]));
 cards=cards.map(c=>live.get(String(c.id))).filter(c=>c&&businessAssistantDisplayStatus(c)==='pending');
 if(!cards.length)return;
 // No cross-turn or cross-step "confirm everything" operation. A displayed
 // step is not a dependency engine and cannot bind future-generated IDs.
 const groups=businessAssistantCardGroups(cards);if(groups.length!==1){toast('请分别核对每一组事项，不能跨步骤一键办理。',true);return;}
 const missing=confirm?cards.filter(card=>businessAssistantCardQuestions(card).missing.length>0):[];
 if(missing.length){current.queueFilter='pending';current.activeCardId=missing[0].id;current.mobilePane='cards';toast(`还有 ${missing.length} 项需要补充：${businessAssistantCardQuestions(missing[0]).missing.join('、')}`,true);paintBusinessAssistant();return;}
 if(cards.length>1&&!await businessAssistantConfirmMany(cards.length,verb,cards))return;
 if(current!==businessAssistantState||context!==businessAssistantContext()||sessionId!==current.session?.id)return;
 await businessAssistantTask(async(previous,generation)=>{
  let completed=0,lastId=null;
  // Existing single-card endpoints retain identity, expiry, digest, version and
  // idempotency checks. Pause at the first failure/unknown result. This also
  // avoids the old >100 item batch schema mismatch without blind retries.
  for(const original of cards){
   if(!businessAssistantAlive(previous,generation))return;
   const card=previous.session?.proposals?.find(c=>c.id===original.id);
   if(!card||businessAssistantDisplayStatus(card)!=='pending'){previous.error='卡片状态已经变化，已暂停。请核对剩余事项。';break;}
   const payload={digest:card.digest,...(confirm&&card.questions?.length?{answers:businessAssistantAnswers(card.id)}:{})};
   const session=await businessAssistantRequest(`/sessions/${encodeURIComponent(sessionId)}/proposals/${encodeURIComponent(card.id)}/${confirm?'confirm':'cancel'}`,{method:'POST',body:payload});
   if(!businessAssistantAlive(previous,generation))return;businessAssistantRememberSession(session);lastId=card.id;
   const result=session.proposals?.find(c=>c.id===card.id),status=businessAssistantDisplayStatus(result);
   if(status!==(confirm?'succeeded':'cancelled')){previous.error=`已${confirm?'成功办理':'取消'} ${completed} / ${cards.length} 项，当前项${businessAssistantStatusName(status)}，后续尚未提交。请先查看原单核对。`;previous.queueFilter='attention';previous.activeCardId=card.id;break;}
   completed++;previous.receipt=`已${confirm?'成功办理':'取消'} ${completed} / ${cards.length} 项。`;paintBusinessAssistant();
  }
  previous.lastAction=confirm?'confirm':'cancel';
  if(lastId)businessAssistantAdvance(lastId,previous.session);
  if(!previous.error)toast(`已${confirm?'成功办理':'取消'} ${completed} 项。`);
 });
}
async function businessAssistantAutoContinue(){
 // Intentionally no model call. A successful card is not evidence that an
 // arbitrary next business exists; the user explicitly requests a readback.
 return false;
}
function businessAssistantConfirmMany(count,verb,cards=[]){
 return new Promise(resolve=>{
  let settled=false;const finish=value=>{if(!settled){settled=true;resolve(value);}};
  const cancel=verb==='全部取消';
  const dialog=modal(cancel?'取消本组卡片':'核对本组办理事项',
   `<form class="stack"><p>${cancel?`将取消以下 ${count} 张未执行的卡片，不执行业务。`:`以下 ${count} 项会按显示顺序分别提交。任何一项未办成或结果不明时暂停后续；已经成功的不会回滚。`}</p><div class="ba-batch-review">${cards.map((card,i)=>`<p><strong>${i+1}. ${E(card.label||'办理事项')}</strong><br>${E(card.summary||'请核对原卡内容')}</p>`).join('')}</div><p>门店：${E(businessAssistantStoreName())} · 办理人：${E(state.user?.display_name||'本人')}</p><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','返回继续核对')}<button type="submit" class="primary">${cancel?'确认取消这些卡片':'已核对，逐项办理'}</button></div></form>`,async()=>{finish(true);closeModal();});
  dialog.addEventListener('close',()=>finish(false),{once:true});
 });
}
async function businessAssistantContinue(text='请查询刚才已成功办理的原单和当前待办，说明还需我做什么、哪些在等待其他同事。只读取和说明，不准备新卡片，不修改业务；没有后续待办时请明确告诉我。'){
 const current=businessAssistantState;
 if(current.busy||!current.status?.ready||current.session?.busy||current.needsRefresh)return;
 if(current.draft.trim()||current.retry){toast('输入框里还有未发送的内容，请先发送或自行清空。内容不会被覆盖。',true);paintBusinessAssistant({focus:true});return;}
 current.draft=text;current.mobilePane='chat';await businessAssistantSend();
}
async function businessAssistantReport(){
 const current=businessAssistantState,session=current.session,context=businessAssistantContext();if(!session||current.busy)return;
 modal('记录问题',`<form class="stack"><label>遇到什么问题<select name="category"><option value="system">操作无法完成</option><option value="input">不知道怎么填写</option><option value="rule">业务条件不满足</option><option value="model">助手理解有误</option><option value="unsupported">缺少所需功能</option></select></label><label>问题说明<textarea name="summary" required maxlength="1000" rows="4" placeholder="想办什么、卡在哪一步"></textarea></label><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button type="submit" class="primary">保存</button></div></form>`,async form=>{
  if(current!==businessAssistantState||context!==businessAssistantContext())throw new Error('门店或账号已切换，请重新记录。');
  await businessAssistantRequest(`/sessions/${encodeURIComponent(session.id)}/issues`,{method:'POST',body:Object.fromEntries(new FormData(form))});
  if(current!==businessAssistantState||context!==businessAssistantContext())return;closeModal();current.tab='issues';await render();toast('问题已记录');
 });
}
// 卡片必填项：输入即记入本地状态。**打字过程中绝不重画卡片栏**——重画会把输入框换掉，
// 光标就飞了（业主 2026-09-25 实测："输了一个 1 就跳出来了"）。所以：
//   打字(input) → 只更新"能不能点"的按钮状态（不动输入框）
//   选完/离开(change) → 才整栏重画，把提示文字也对齐
function businessAssistantQuestionInput(target,commit){
 if(state.route!=='business-assistant')return;
 const host=target?.closest?.('[data-ba-questions]'),key=target?.dataset?.baqKey;if(!host||!key)return;
 businessAssistantAnswers(host.dataset.baQuestions)[key]=target.value;
 // Neither input nor change replaces focused controls. In particular, a blur
 // immediately before clicking Confirm must not swallow that click.
 businessAssistantRefreshGates(host.dataset.baQuestions);
}
function businessAssistantRefreshGates(cardId){
 const panel=$('#business-assistant-cards');if(!panel)return;
 const proposal=businessAssistantState.session?.proposals?.find(c=>String(c.id)===String(cardId));if(!proposal)return;
 const element=[...panel.querySelectorAll('[data-proposal]')].find(c=>c.dataset.proposal===String(cardId));if(!element)return;
 const missing=businessAssistantCardQuestions(proposal).missing;
 const bar=panel.querySelector('[data-ba-confirm-bar]');
 const confirm=bar?.querySelector('[data-ba-action="confirm"]');
 if(confirm)confirm.textContent=missing.length?'补全必填项后确认':'确认办理';
 const fill=bar?.querySelector('[data-ba-action="fill-missing"]');if(fill){fill.hidden=!missing.length;fill.textContent=`填写必填项（${missing.length}）`;}
 if(confirm)confirm.disabled=Boolean(businessAssistantState.busy||businessAssistantState.session?.busy||businessAssistantState.needsRefresh||missing.length||businessAssistantExpired(proposal));
 const hint=element.querySelector('[data-ba-missing]');if(hint){hint.hidden=!missing.length;hint.textContent=`请先填写：${missing.join('、')}。`;}
}
document.addEventListener('input',event=>businessAssistantQuestionInput(event.target,false));
document.addEventListener('change',event=>businessAssistantQuestionInput(event.target,true));
document.addEventListener('change',event=>{
 if(event.target?.id!=='ba-queue-select'||state.route!=='business-assistant')return;
 businessAssistantState.activeCardId=event.target.value;paintBusinessAssistantCards();
});
document.addEventListener('click',async event=>{
 const element=event.target.closest('[data-ba-action]');if(!element||element.disabled||state.route!=='business-assistant')return;
 const action=element.dataset.baAction,current=businessAssistantState;
 try{
  if(action==='stop'){
   if(current.runId){
    const runtime=globalThis.AssistantRuntime,version=current.runView?.version;
    if(!runtime?.cancelRun||!Number.isSafeInteger(version)){toast('请先刷新执行状态，再停止本次准备。',true);return;}
    current.runStop='正在停止…';paintBusinessAssistant();
    try{await runtime.cancelRun(current.runId,version);}
    catch(error){
     if(error?.status===409){current.error='执行状态已变化，请核对后重试。';try{await runtime.getRun(current.runId);}catch{}}
     else current.error=error?.message||'停止未完成，请稍后重试。';
     paintBusinessAssistant();
    }
    return;
   }
   for(const controller of current.controllers)controller.abort();return;
  }
  if(action==='fill-missing'){const card=document.querySelector('#business-assistant-cards [data-proposal]');const input=[...(card?.querySelectorAll('[data-baq-key][required]')||[])].find(x=>!x.value.trim());if(input){input.scrollIntoView({block:'center',behavior:'instant'});input.focus({preventScroll:true});}return;}
  if(action==='history'){current.historyOpen=!current.historyOpen;paintBusinessAssistant();return;}
  if(action==='queue-filter'){current.queueFilter=element.dataset.filter;current.activeCardId=null;paintBusinessAssistantCards();return;}
  if(action==='queue-prev'||action==='queue-next'){const q=businessAssistantQueue(),index=q.visible.indexOf(q.selected)+(action==='queue-next'?1:-1);if(q.visible[index])current.activeCardId=q.visible[index].id;paintBusinessAssistantCards();return;}
  if(['pane-chat','pane-cards','show-cards','show-attention'].includes(action)){
   current.mobilePane=action==='pane-chat'?'chat':'cards';if(action==='show-cards')current.queueFilter='pending';if(action==='show-attention')current.queueFilter='attention';
   paintBusinessAssistant();if(current.mobilePane==='cards')document.querySelector('#business-assistant-cards h3')?.focus({preventScroll:true});return;
  }
  if(current.busy)return;
  if(action==='new'){
   if(current.draft.trim()||current.retry){toast('请先发送或自行清空当前输入，再开始新对话。',true);return;}
   current.session=null;current.workboard=null;current.workPlanId=null;current.workError='';current.workSerial++;current.error='';current.needsRefresh=false;current.retry=null;current.stream=null;current.thinking=false;current.tab='chat';current.historyOpen=false;current.activeCardId=null;current.queueFilter='pending';current.receipt=null;current.mobilePane='chat';paintBusinessAssistant({focus:true});
  }
  else if(action==='thinking'){if(!current.retry){current.thinking=!current.thinking;paintBusinessAssistant();}}
  else if(action==='suggestion'){if(!current.retry&&!current.draft.trim()){current.draft=element.dataset.prompt||'';paintBusinessAssistant({focus:true});}else toast('输入框中已有内容，请先处理当前草稿。',true);}
  else if(action==='chat'){current.tab='chat';paintBusinessAssistant();}
  else if(action==='session'||action==='issue-session')await businessAssistantChooseSession(element.dataset.id);
  else if(action==='confirm'||action==='cancel-proposal')await businessAssistantDecide(element.dataset.id,action==='confirm');
  else if(action==='card-confirm-all'||action==='card-cancel-all')await businessAssistantDecideAll(element.dataset.key,action==='card-confirm-all');
  else if(action==='continue')await businessAssistantContinue();
  else if(action==='refresh'){current.error='';await render();}
  else if(action==='issues')await businessAssistantTask(async(previous,generation)=>{const data=await businessAssistantRequest('/issues');if(!businessAssistantAlive(previous,generation))return;previous.issues=data.items||[];previous.tab='issues';});
  else if(action==='report')await businessAssistantReport();
  else if(action==='export-issues')await download('/api/business-assistant/issues/export','业务助手问题清单.json');
 }catch(error){if(current===businessAssistantState&&current.context===businessAssistantContext()){current.error=error.message;paintBusinessAssistant();toast(error.message,true);}}
});

document.addEventListener('change',event=>{
 if(event.target?.id!=='ba-view-select'||state.route!=='business-assistant')return;
 const value=event.target.value;
 const selector=value==='files'?'.ba-toolbar [data-baf-action="open"]':value==='issues'?'.ba-toolbar [data-ba-action="issues"]':'.ba-toolbar [data-ba-action="chat"]';
 const button=document.querySelector(selector);if(button&&!button.disabled)button.click();else event.target.value=businessAssistantState.tab;
});
