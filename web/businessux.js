'use strict';

// Presentation only. All buttons keep their original handlers and API guards.
// This module never invents a workflow transition, executes a business write,
// persists customer data in browser storage, or treats a task as a cash fact.
const UX_MODULES = Object.freeze(['整车销售','整车仓库','维修管理','物资管理','财务管理','客户管理','会员服务','统计分析','基础数据','系统管理']);
// Display budget only; search and module filters always inspect the full catalogue.
const UX_START_INITIAL_COUNT = 9;
const UX_COMMON_WORKFLOWS = Object.freeze({
 default:['wf-reception','wf-intent-followup','wf-reservation-contract','wf-repair-intake','wf-repair-complete','wf-retail-sale','wf-customer-advance','wf-member-card','wf-vehicle-catalog'],
 sales:['wf-reception','wf-intent-followup','wf-reservation-contract','wf-sale-delivery','wf-vehicle-catalog','wf-retail-sale','wf-insurance-order','wf-sale-addon','wf-agency-service'],
 reception:['wf-reception','wf-repair-intake','wf-customer-profile','wf-customer-vehicle','wf-member-card','wf-member-principal','wf-customer-advance'],
 service:['wf-repair-intake','wf-repair-complete','wf-repair-materials','wf-repair-claim','wf-customer-vehicle','wf-retail-sale','wf-insurance-renewal','wf-sales-repair-callback','wf-member-card'],
 technician:['wf-repair-complete','wf-repair-materials','wf-sale-addon','wf-retail-sale','wf-sale-delivery'],
 inventory:['wf-vehicle-catalog','wf-vehicle-purchase','wf-material-purchase','wf-material-stock-query','wf-repair-materials','wf-material-transfer','wf-vehicle-transfer','wf-material-stock-count','wf-sale-delivery'],
 finance:['wf-sale-delivery','wf-repair-complete','wf-retail-sale','wf-customer-advance','wf-customer-statement','wf-invoice-issue-red','wf-member-principal','wf-period-close','wf-report-160'],
 customer_service:['wf-sales-repair-callback','wf-vehicle-reminders','wf-insurance-renewal','wf-customer-consultation-complaint-rescue','wf-customer-profile','wf-member-card','wf-member-points','wf-repair-intake','wf-customer-vehicle'],
 auditor:['wf-period-close','wf-audit-business-history','wf-report-160','wf-report-137','wf-report-147','wf-report-154','wf-report-145','wf-report-152','wf-report-169']
});
// A workflow may include both creation and later settlement/returns. A search
// must not turn a follow-up request into a new document. Both native entrances
// remain explicit; only an unambiguous common "new business" tile leads with a form.
const UX_CREATE_FIRST = new Set(['wf-reception','wf-reservation-contract','wf-repair-intake','wf-vehicle-purchase','wf-material-purchase','wf-insurance-order','wf-sale-addon','wf-agency-service','wf-vehicle-other-income','wf-vehicle-catalog-one-form','wf-customer-profile']);
function uxStartEntry(item,options,role,store){
 const allowed=WorkflowGuides.canEnter(item,role,store),form=WORKFLOW_QUICK_FORMS[item.id];
 const direct=allowed&&form&&store!=='all';
 return {allowed,form,direct,preferNew:!!direct&&!options.startQuery.trim()&&UX_CREATE_FIRST.has(item.id)};
}
function uxStartItems(catalogue,options,role,store){
 const items=WorkflowGuides.search(catalogue.workflows,options.startQuery,role).filter(item=>
  (!options.startModule||(item.requirements||[]).some(r=>r.module===options.startModule+'模块'))&&
  (options.startAll||WorkflowGuides.canEnter(item,role,store)));
 const home=!options.startQuery.trim()&&!options.startModule;
 if(home){const order=UX_COMMON_WORKFLOWS[role]||UX_COMMON_WORKFLOWS.default;
  const rank=id=>{const n=order.indexOf(id);return n<0?order.length:n;};
  items.sort((a,b)=>rank(a.id)-rank(b.id));
 }
 return {items,shown:home&&!options.startExpanded?items.slice(0,UX_START_INITIAL_COUNT):items,home};
}
let businessUX = {context:null,receipt:null,startQuery:'',startModule:'',startAll:false,startExpanded:false};
function uxContext(){return `${storeContextVersion}:${state.user?.id||''}:${state.store||''}`;}
function clearBusinessUXContext(){if(typeof clearModuleUX==='function')clearModuleUX();businessUX={context:uxContext(),receipt:null,startQuery:'',startModule:'',startAll:false,startExpanded:false};}
function uxSyncContext(){if(businessUX.context!==uxContext())clearBusinessUXContext();}
function uxCurrentCase(){
 const [root,key,id]=state.route.split('/'),row=state.row;
 if(!row||!Array.isArray(row.tasks)||!Array.isArray(row.actions))return null;
 const caseRoutes=new Set(['case','sales-quotes','repair-orders','procurement','vehicle-procurement','retail','service-orders','insurance-orders','addon-orders','aftercare','warehouse','membership-order','business-finance-order','recharge-bundle-order','invoices','vehicle-income','claims','customer-service','vehicle-operation','opening-batch','retail-group-rule','business-entity']);
 const direct=caseRoutes.has(root)&&Number(key)>0&&Number(key)===row.id;
 const intake=root==='service-intake'&&Number(id)>0&&state.intakeRecord?.id===Number(id)&&state.intakeRecord?.case_id===row.id;
 if(!direct&&!intake)return null;
 return row;
}
function uxTaskRoute(task){
 // entry_route is produced by the server from the actual case/version. An old
 // backend is still usable: its generic case page remains the fallback.
 const route=task.entry_route;
 return typeof route==='string'&&/^[a-z][a-z-]*(?:\/[a-zA-Z0-9_-]+)+$/.test(route)?route:'case/'+task.case_id;
}
function uxNextState(row,userId){
 const open=(row.tasks||[]).filter(t=>t.status==='open');
 const mine=open.filter(t=>t.assignee_id===userId),others=open.filter(t=>t.assignee_id!==userId);
 const enabled=(row.actions||[]).filter(a=>a.enabled);
 if(mine.length)return {kind:'mine',title:'接下来由您处理',text:mine.map(t=>t.title).join('、'),mine,others,open,enabled};
 if(others.length){const unassigned=others.some(t=>!t.assignee_id||t.assignee_name==='待配置'),people=[...new Set(others.map(t=>t.assignee_name).filter(Boolean))];return {kind:'handoff',title:unassigned?'需要主管安排接手人':people.length===1?`接下来由${people[0]}办理`:'接下来由同事协同处理',text:unassigned?'有待办尚未落实接手人，请主管核对分工。':'您的名下没有未完成待办，下面列出本单的接手人。',mine,others,open,enabled};}
 return {kind:'clear',title:'本单目前没有未完成待办',text:'以当前业务状态为准；没有待办不等于款项、实物或外部手续已全部完成。',mine,others,open,enabled};
}
function uxRecordSuccess(path,method,value){
 if(method==='GET'||!state.user)return;
 // Capture only successful native business responses, never assistant wording.
 if(!/^\/api\/(flow\/cases|sales-quotes\/orders|repair-orders|procurement\/orders|vehicle-procurement\/orders|retail\/orders|service-orders|insurance-orders|addon-orders|aftercare\/orders|warehouse\/cases|membership|business-finance|service-intake|customer-service|invoices)(?:\/|$)/.test(path))return;
 const title=document.querySelector('#modal[open] #modal-title')?.textContent;
 if(!title)return;
 uxSyncContext();
 const current=uxCurrentCase();
 const caseId=Number.isSafeInteger(value?.case_id)?value.case_id:(value?.kind&&Number.isSafeInteger(value.id)?value.id:current?.id||null);
 businessUX.receipt={context:uxContext(),title,caseId,number:value?.number||current?.number||'',route:state.route};
}
function uxReceiptHTML(row=null){
 uxSyncContext();const r=businessUX.receipt;
 if(!r||r.context!==uxContext())return '';
 if(row&&(r.caseId?r.caseId!==row.id:r.route!==state.route))return '';
 if(!row&&r.route!==state.route)return '';
 return `<div class="ux-receipt" role="status"><div><strong>已保存：${E(r.title)}</strong><p>${E(r.number?`单号 ${r.number}。`:'')}这次提交已返回成功；下一步请看下方当前进度。</p></div><button type="button" data-ux-action="dismiss-receipt" aria-label="收起本次保存结果">收起</button></div>`;
}
function uxGroupActions(panelElement){
 const cards=[...panelElement.querySelectorAll('.actioncard')];if(!cards.length)return;
 const host=panelElement.querySelector('.panelbody');if(!host)return;
 const secondaryKeys=new Set(['cancel','cancel_request','reject','cancel_reject','revise','quote_cancel','return_cancel','termination_cancel','quote_reject','quote_withdraw']);
 const primary=[],other=[],blocked=[];
 for(const card of cards){
  const button=card.querySelector('button');if(!button)continue;
  if(button.disabled)blocked.push(card);
  else if(secondaryKeys.has(button.dataset.key))other.push(card);
  else primary.push(card);
 }
 // Move the original nodes; no cloned buttons or duplicate event listeners.
 if(primary.length+other.length+blocked.length!==cards.length)return;
 host.replaceChildren();
 const add=(nodes,title)=>{
  if(!nodes.length)return;
  const box=document.createElement(title?'details':'div');box.className=title?'ux-action-disclosure':'ux-action-options';
  if(title){const summary=document.createElement('summary');summary.textContent=`${title}（${nodes.length}）`;box.append(summary);}
  nodes.forEach(node=>box.append(node));host.append(box);
 };
 add(primary);add(other,'更正、退回或取消');add(blocked,'暂不能办理 · 查看缺少的条件');
 if(!primary.length){const note=document.createElement('p');note.className='ux-muted';note.textContent='暂时没有可直接推进的动作，请先查看接手人或缺少的条件；更正与撤回可展开下方选项。';host.prepend(note);}
}
function mountBusinessUX(){
 uxSyncContext();const main=document.getElementById('main');if(!main)return;
 main.classList.toggle('ux-assistant-page',state.route==='business-assistant');
 if(state.route==='start'){bindBusinessStart();return;}
 const row=uxCurrentCase();if(!row)return;
 const next=uxNextState(row,state.user.id);
 // Only general action panels are promoted. Refund/return/line-specific
 // controls stay attached to their original record and evidence.
 const actionTitles=new Set(['现在可以做什么','办理本步骤','本次办理','本次可以办理','当前办理','当前责任']);
 const actionPanel=[...main.querySelectorAll('section.panel')].find(p=>actionTitles.has(p.querySelector('.panelhead h2')?.textContent));
 if(actionPanel)uxGroupActions(actionPanel);
 const section=document.createElement('section');section.className='ux-now';section.setAttribute('aria-label','当前业务与下一步');
 const tasks=next.open.map(t=>`<div class="ux-handoff-row"><div><strong>${E(t.title)}</strong><p>${E(t.assignee_id===state.user.id?'您':t.assignee_name||'待安排')} · ${E(t.role_label||'')} · ${E(t.due_date||'日期待核对')}</p>${t.block_reason?`<p class="ux-block-reason">${E(t.block_reason)}</p>`:''}</div>${t.assignee_id===state.user.id?'<span class="pill info">我的待办</span>':'<span class="pill">待接手人办理</span>'}</div>`).join('');
 section.innerHTML=uxReceiptHTML(row)+`<div class="ux-now-head"><div><p class="ux-context">${E(row.kind_label||'当前业务')} · ${E(row.number||'')} · ${E(row.customer?.name||row.title||'')}</p><h2>${E(next.title)}</h2><p>${E(next.text)}</p></div><div class="ux-now-side">${pill(row.state,row.state_label)}${!state.route.startsWith('case/')?`<a href="#case/${row.id}" class="ux-source-link">完整业务资料</a>`:''}<a class="button" href="#work">回到我的工作</a></div></div>${tasks?`<details class="ux-handoff" ${next.kind==='handoff'?'open':''}><summary>${next.mine.length?`我的 ${next.mine.length} 项待办${next.others.length?` · 另有 ${next.others.length} 项由同事办理`:''}`:`当前接手事项 · ${next.others.length} 项`}</summary>${tasks}</details>`:''}<div class="ux-now-actions"></div>`;
 const heading=main.querySelector('.pagehead');if(heading)heading.insertAdjacentElement('afterend',section);else main.prepend(section);
 if(actionPanel){section.querySelector('.ux-now-actions').append(actionPanel);actionPanel.classList.add('ux-promoted-actions');const h=actionPanel.querySelector('h2');if(h)h.textContent=next.mine.length?'选择本次要办理的事':next.others.length?'需要协助时可办理的事项':'本岗位仍可办理的事项';if(!next.mine.length&&next.others.length){const note=document.createElement('p');note.className='ux-muted';note.textContent='当前待办由上方接手人负责。以下是本账号仍有权办理的动作，不必逐一点击。';actionPanel.querySelector('.panelbody')?.prepend(note);}}
 // Static reference stages must not look like authoritative completion state.
 for(const steps of [...main.querySelectorAll('.steps')]){
  const details=document.createElement('details');details.className='ux-history ux-process-reference';
  const summary=document.createElement('summary');summary.textContent='查看流程参考（当前进度以上方待办为准）';
  steps.replaceWith(details);details.append(summary,steps);
 }
 // Historical evidence remains available, but is not the first screen of work.
 for(const p of [...main.querySelectorAll('section.panel')]){
  const title=p.querySelector('.panelhead h2')?.textContent;
  if(!['操作留痕','报价历史'].includes(title))continue;
  const details=document.createElement('details');details.className='ux-history';
  const summary=document.createElement('summary');summary.textContent=title;details.append(summary);p.replaceWith(details);details.append(p);
 }
}
function uxWorkIntro(data){
 const open=state.taskStatus==='open',filtered=!!state.q||state.route.includes('/')||(typeof moduleUX!=='undefined'&&!!moduleUX.taskDue);
 return `<section class="ux-work-intro"><div><p class="ux-context">${E(state.stores.find(s=>String(s.id)===String(state.store))?.name||'当前范围')} · ${E(roleNames[state.user.role]||'')} · ${E(day())}</p><h2>${open?(data.total?'从待办接着办，不必重新建单':(filtered?'当前筛选没有匹配待办，可调整筛选条件':'当前没有待办，可以开始一笔新业务')):'查看以前的办理记录'}</h2><p>接已有业务，点下方待办；登记新业务，点“办一件新事”。</p></div><a class="button primary" href="#start">办一件新事</a></section><div class="ux-work-counts"><span>${open?'待处理':'当前记录'} <strong>${number(data.total)}</strong> 项</span>${open?`<span${data.overdue_count?' class="ux-overdue"':''}>超过计划日期 <strong>${number(data.overdue_count)}</strong> 项</span>`:''}<span>${state.taskScope==='mine'?'我的责任任务':'门店全部任务'}</span></div>`;
}
async function businessStartPage(){
 uxSyncContext();const data=await loadWorkflowGuides();
 return heading('办一件事','',`<a class="button" href="#work">接着处理待办</a>`)+storeNotice()+`<section class="ux-start"><div class="ux-start-intro"><h2>这次要办什么？</h2><p>直接填写新单，或先找到要处理的原单。不需要先阅读完整流程。</p></div><div class="ux-start-search"><label for="ux-start-query">搜索业务或需求表中的名称<input type="search" id="ux-start-query" placeholder="例如：展厅接待、洗车、退货、会员充值" value="${E(businessUX.startQuery)}" autocomplete="off"></label><label class="checklabel"><input type="checkbox" id="ux-start-all" ${businessUX.startAll?'checked':''}>同时查看其他岗位的功能</label></div><div class="ux-module-tabs" aria-label="需求表的十个模块"><button type="button" data-ux-module="" aria-pressed="${!businessUX.startModule}">常用入口</button>${UX_MODULES.map(m=>`<button type="button" data-ux-module="${E(m)}" aria-pressed="${businessUX.startModule===m}">${E(m)}</button>`).join('')}</div><p id="ux-start-count" role="status"></p><div class="ux-start-results" id="ux-start-results"></div><div id="ux-start-more" class="ux-start-more"></div><p class="ux-muted">保留全部 ${data.requirements?.length||193} 项原始需求的检索入口。页面按岗位和门店筛选；具体办理仍由原接口核验权限。</p></section>`;
}
function bindBusinessStart(){
 const input=document.getElementById('ux-start-query'),all=document.getElementById('ux-start-all');if(!input||!workflowCatalogue)return;
 const paint=()=>{
  const {items,shown,home}=uxStartItems(workflowCatalogue,businessUX,state.user.role,state.store);
  document.getElementById('ux-start-count').textContent=items.length?(home&&!businessUX.startExpanded?`先显示 ${shown.length} 个常用入口。已有单据请从待办或原单接着办理，不要重复新建。`:`找到 ${items.length} 条办理路径。已有单据请在原单继续，不要重复新建。`):'没有找到当前范围内的业务。可以换个词，或勾选查看其他岗位。';
  document.getElementById('ux-start-more').innerHTML=home&&items.length>UX_START_INITIAL_COUNT?`<button type="button" id="ux-expand-start">${businessUX.startExpanded?'收起，回到常用入口':`显示全部 ${items.length} 条办理路径`}</button>`:'';
  document.getElementById('ux-expand-start')?.addEventListener('click',()=>{businessUX.startExpanded=!businessUX.startExpanded;paint();if(!businessUX.startExpanded)input.focus();});
  document.getElementById('ux-start-results').innerHTML=shown.map(item=>{
   const {allowed:enter,form,direct,preferNew}=uxStartEntry(item,businessUX,state.user.role,state.store);
   const primary=preferNew?'start-form':'start-page',secondary=preferNew?'start-page':'start-form';
   return `<article class="ux-start-card"><div><span class="ux-context">${E((item.requirements?.[0]?.module||item.category).replace(/模块$/,''))}</span><h3>${E(item.title)}</h3><p>${E(item.summary)}</p></div><div class="ux-start-card-actions"><button type="button" class="primary" data-ux-action="${primary}" data-id="${E(item.id)}" ${enter?'':'disabled'}>${E(preferNew?form.label:item.entry.label)}</button>${direct?`<button type="button" data-ux-action="${secondary}" data-id="${E(item.id)}">${E(preferNew?'查看已有业务':form.label)}</button>`:''}<a href="#workflows/${E(item.id)}">查看办理步骤</a></div>${!enter?`<p class="ux-muted">${E((item.entry.roles||[]).map(r=>roleNames[r]||r).join('、'))}的入口${state.store==='all'&&item.entry.mode==='write'?'；请先选择门店':''}</p>`:''}</article>`;
  }).join('');
 };
 input.addEventListener('input',event=>{businessUX.startQuery=input.value;if(!event.isComposing)paint();});input.addEventListener('compositionend',()=>{businessUX.startQuery=input.value;paint();});
 all.addEventListener('change',()=>{businessUX.startAll=all.checked;paint();});
 document.querySelectorAll('[data-ux-module]').forEach(button=>button.addEventListener('click',()=>{const module=typeof moduleForName==='function'?moduleForName(button.dataset.uxModule):null;if(module){go('module/'+module.key);return;}businessUX.startModule=button.dataset.uxModule;document.querySelectorAll('[data-ux-module]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));paint();}));paint();
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-ux-action]');if(!button||button.disabled)return;
 const action=button.dataset.uxAction;
 if(action==='dismiss-receipt'){businessUX.receipt=null;button.closest('.ux-receipt')?.remove();return;}
 if(state.route!=='start'||!state.user||state.storeSwitch)return;
 const item=workflowCatalogue?.workflows.find(w=>w.id===button.dataset.id);
 if(!item||!WorkflowGuides.canEnter(item,state.user.role,state.store))return;
 try{if(action==='start-form')await workflowOpenForm(item.id);else if(action==='start-page')workflowNavigate(item.entry.route);}catch(error){toast(error.message,true);}
});
