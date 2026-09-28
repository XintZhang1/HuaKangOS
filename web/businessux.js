'use strict';

// Presentation only. All buttons keep their original handlers and API guards.
// This module never invents a workflow transition, executes a business write,
// persists customer data in browser storage, or treats a task as a cash fact.
const UX_MODULES = Object.freeze(['整车销售','整车仓库','维修管理','物资管理','财务管理','客户管理','会员服务','统计分析','基础数据','系统管理']);
// Display budget only; search and module filters always inspect the full catalogue.
const UX_START_INITIAL_COUNT = 9;
// Labels are display metadata only. IDs, search aliases and destinations remain
// in the published catalogue; these names never select an operation or API.
const UX_ENTRY_NAMES = Object.freeze({
 'wf-reception':'展厅接待','wf-intent-followup':'意向客户跟进','wf-intent-callback':'意向客户回访',
 'wf-reservation-contract':'销售预订','wf-sale-delivery':'收款与交车','wf-sale-cancellation':'取消预订','wf-sale-aftercare':'退订退车',
 'wf-repair-intake':'维修接待','wf-repair-complete':'维修工单','wf-repair-materials':'维修领料与退料','wf-repair-rework':'返修',
 'wf-vehicle-purchase':'整车采购','wf-vehicle-batch-import':'采购批次导入','wf-vehicle-purchase-return':'整车采购退回',
 'wf-material-purchase':'物资采购','wf-material-purchase-return':'物资采购退回','wf-retail-return':'精品退货',
 'wf-cash-correction':'收款更正','wf-customer-advance':'客户预收款','wf-member-topup-refund':'会员充值与退款',
 'wf-member-principal':'会员充值与退款','wf-member-card':'会员卡','wf-member-points':'会员积分',
 'wf-member-renew-tier':'会员续会与等级','wf-customer-statement':'客户月结','wf-employee-store-roles':'员工账号',
 'wf-vehicle-catalog-one-form':'品牌车系车型','wf-questionnaire-design-and-answer':'回访问卷',
 'wf-sale-addon':'销售加装','wf-insurance-order':'保险业务','wf-agency-service':'代办服务',
 'wf-other-customer-income':'其他服务收入','wf-other-service-income':'其他服务收入','wf-vehicle-other-income':'整车其他收入',
 'wf-vehicle-catalog':'车型与库存','wf-vehicle-transfer':'整车调拨','wf-vehicle-other-out':'车辆其他出入库','wf-vehicle-local-move':'车辆移库',
 'wf-repair-claim':'理赔核价','wf-customer-reimbursement':'维修报销','wf-repair-package':'维修套餐',
 'wf-material-other-in':'物资其他入库','wf-consumable-issue-return':'耗材领退','wf-gift-issue-return':'礼品领退',
 'wf-material-other-out':'物资其他出库','wf-material-transfer':'物资调拨','wf-material-stock-query':'库存查询',
 'wf-material-local-move':'物资移库','wf-material-stock-count':'物资盘点','wf-retail-sale':'精品销售','wf-retail-bundle':'精品套餐',
 'wf-supplier-other-return-money':'退货收款','wf-transfer-clearing':'店间清算','wf-period-close':'月结','wf-invoice-issue-red':'开票与冲红',
 'wf-customer-profile':'客户资料','wf-customer-vehicle':'客户车辆','wf-sales-repair-callback':'销售维修回访',
 'wf-vehicle-reminders':'保养提醒','wf-customer-consultation-complaint-rescue':'咨询、投诉与救援',
 'wf-insurance-renewal':'续保跟进','wf-cross-store-service-history':'车辆服务历史',
 'wf-recharge-bundle':'充值套餐','wf-coupons-and-benefits':'消费券','wf-customer-repair-package':'客户维修套餐','wf-member-level-rules':'会员等级与优惠',
 'wf-dictionary-settings':'分类设置','wf-suppliers-and-insurers':'供应商与保险公司','wf-workshops-and-jobs':'车间与作业项目',
 'wf-warehouse-location-masters':'仓库与库位','wf-agency-project-master':'代办项目','wf-material-catalog-masters':'物资目录',
 'wf-store-management':'门店设置','wf-parameters-password-brand':'参数与账号设置','wf-audit-business-history':'操作记录'
});
const UX_ENTRY_ROUTES = Object.freeze({
 'cases/lead':['接待与跟进','查看接待'],'sales-quotes':['销售订单','查看订单'],
 'repair-orders':['维修工单','查看工单'],'membership':['会员服务','查看会员'],
 'business-finance':['客户收支','查看收支'],'procurement':['物资采购','查看采购单'],
 'warehouse':['物资收发','查看库存'],'vehicle-procurement':['整车采购','查看采购单'],
 'service-intake':['维修接待','查看接待'],'retail':['精品销售','查看销售单'],'vehicle-catalog':['车型与库存','查看车型']
});
function uxEntryTitle(item,grouped=false){return (grouped&&UX_ENTRY_ROUTES[item.entry.route]?.[0])||UX_ENTRY_NAMES[item.id]||item.title;}
function uxEntryOpenLabel(item){return UX_ENTRY_ROUTES[item.entry.route]?.[1]||item.entry.label.replace(/^打开/,'查看');}
function uxLabelCatalogue(data){
 // Add display names as search aliases without changing the published titles,
 // original requirement names, permissions or workflow IDs.
 return {...data,workflows:data.workflows.map(item=>({...item,keywords:[...new Set([...(item.keywords||[]),uxEntryTitle(item),uxEntryTitle(item,true)])]}))};
}
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
// M6.5：交给助手按钮。页面模块可能被单独加载（离线检查），拿不到共用实现就不渲染按钮。
function uxHandoffButton(ref,label){
 const workspace=globalThis.AssistantWorkspace;
 if(!workspace||typeof workspace.handoffButton!=='function')return '';
 return workspace.handoffButton({ref:ref,label:label});
}
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
 if(mine.length)return {kind:'mine',title:'待我处理',text:mine.map(t=>t.title).join('、'),mine,others,open,enabled};
 if(others.length){const unassigned=others.some(t=>!t.assignee_id||t.assignee_name==='待配置'),people=[...new Set(others.map(t=>t.assignee_name).filter(Boolean))];return {kind:'handoff',title:unassigned?'需要主管安排接手人':people.length===1?`接下来由${people[0]}办理`:'接下来由同事协同处理',text:unassigned?'有待办尚未落实接手人，请主管核对分工。':'',mine,others,open,enabled};}
 return {kind:'clear',title:'暂无待办',text:'',mine,others,open,enabled};
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
 return `<div class="ux-receipt" role="status"><div><strong>已保存：${E(r.title)}</strong>${r.number?`<p>单号 ${E(r.number)}</p>`:''}</div><button type="button" data-ux-action="dismiss-receipt" aria-label="收起本次保存结果">收起</button></div>`;
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
 add(primary);add(other,'更正、退回或取消');add(blocked,'暂不可用');
 if(!primary.length){const note=document.createElement('p');note.className='ux-muted';note.textContent='暂无可用操作。';host.prepend(note);}
}
function mountBusinessUX(){
 uxSyncContext();const main=document.getElementById('main');if(!main)return;
 main.classList.toggle('ux-assistant-page',state.route==='business-assistant');
 if(state.route==='start'){bindBusinessStart();return;}
 const row=uxCurrentCase();if(!row)return;
 const next=uxNextState(row,state.user.id);
 // Only general action panels are promoted. Refund/return/line-specific
 // controls stay attached to their original record and evidence.
 const actionPanel=main.querySelector('[data-panel-role="actions"]');
 if(actionPanel)uxGroupActions(actionPanel);
 const section=document.createElement('section');section.className='ux-now';section.setAttribute('aria-label','当前业务与下一步');
 const tasks=next.open.map(t=>`<div class="ux-handoff-row"><div><strong>${E(t.title)}</strong><p>${E(t.assignee_id===state.user.id?'您':t.assignee_name||'待安排')} · ${E(t.role_label||'')} · ${E(t.due_date||'日期待核对')}</p>${t.block_reason?`<p class="ux-block-reason">${E(t.block_reason)}</p>`:''}</div>${t.assignee_id===state.user.id?'<span class="pill info">我的待办</span>':'<span class="pill">待接手人办理</span>'}</div>`).join('');
 section.innerHTML=uxReceiptHTML(row)+`<div class="ux-now-head"><div><p class="ux-context">${E(row.kind_label||'当前业务')} · ${E(row.number||'')} · ${E(row.customer?.name||row.title||'')}</p><h2>${E(next.title)}</h2>${next.text?`<p>${E(next.text)}</p>`:''}</div><div class="ux-now-side">${pill(row.state,row.state_label)}${!state.route.startsWith('case/')?`<a href="#case/${row.id}" class="ux-source-link">单据详情</a>`:''}<a class="button" href="#work">我的待办</a></div></div>${tasks?`<details class="ux-handoff" ${next.kind==='handoff'?'open':''}><summary>${next.mine.length?`我的 ${next.mine.length} 项待办${next.others.length?` · 另有 ${next.others.length} 项由同事办理`:''}`:`当前接手事项 · ${next.others.length} 项`}</summary>${tasks}</details>`:''}<div class="ux-now-actions"></div>`;
 const heading=main.querySelector('.pagehead');if(heading)heading.insertAdjacentElement('afterend',section);else main.prepend(section);
 if(actionPanel){section.querySelector('.ux-now-actions').append(actionPanel);actionPanel.classList.add('ux-promoted-actions');const h=actionPanel.querySelector('h2');if(h)h.textContent='操作';}
 // Static reference stages must not look like authoritative completion state.
 for(const steps of [...main.querySelectorAll('.steps')]){
  const details=document.createElement('details');details.className='ux-history ux-process-reference';
  const summary=document.createElement('summary');summary.textContent='流程参考';
  steps.replaceWith(details);details.append(summary,steps);
 }
 // Historical evidence remains available, but is not the first screen of work.
 for(const p of [...main.querySelectorAll('[data-panel-role="history"]')]){
  const title=p.querySelector('.panelhead h2')?.textContent;
  const details=document.createElement('details');details.className='ux-history';
  const summary=document.createElement('summary');summary.textContent=title;details.append(summary);p.replaceWith(details);details.append(p);
 }
}
function uxWorkIntro(data){
 const open=state.taskStatus==='open',filtered=!!state.q||state.route.includes('/')||(typeof moduleUX!=='undefined'&&!!moduleUX.taskDue);
 return `<section class="ux-work-intro"><div><p class="ux-context">${E(state.stores.find(s=>String(s.id)===String(state.store))?.name||'当前范围')} · ${E(roleNames[state.user.role]||'')} · ${E(day())}</p><h2>${open?(data.total?'我的待办':(filtered?'暂无匹配待办':'暂无待办')):'查看以前的办理记录'}</h2></div><a class="button primary" href="#start">快捷操作</a></section><div class="ux-work-counts"><span>${open?'待处理':'当前记录'} <strong>${number(data.total)}</strong> 项</span>${open?`<span${data.overdue_count?' class="ux-overdue"':''}>超过计划日期 <strong>${number(data.overdue_count)}</strong> 项</span>`:''}<span>${state.taskScope==='mine'?'我的责任任务':'门店全部任务'}</span></div>`;
}
async function businessStartPage(){
 uxSyncContext();const data=await loadWorkflowGuides();
 return heading('快捷操作','',`<a class="button" href="#work">我的待办</a>`)+storeNotice()+`<section class="ux-start"><div class="ux-start-search"><label for="ux-start-query">搜索操作<input type="search" id="ux-start-query" placeholder="例如：展厅接待、洗车、退货、会员充值" value="${E(businessUX.startQuery)}" autocomplete="off"></label><label class="checklabel"><input type="checkbox" id="ux-start-all" ${businessUX.startAll?'checked':''}>同时查看其他岗位的功能</label></div><div class="ux-module-tabs" aria-label="需求表的十个模块"><button type="button" data-ux-module="" aria-pressed="${!businessUX.startModule}">常用操作</button>${UX_MODULES.map(m=>`<button type="button" data-ux-module="${E(m)}" aria-pressed="${businessUX.startModule===m}">${E(m)}</button>`).join('')}</div><p id="ux-start-count" role="status"></p><div class="ux-start-results" id="ux-start-results"></div><div id="ux-start-more" class="ux-start-more"></div></section>`;
}
function bindBusinessStart(){
 const input=document.getElementById('ux-start-query'),all=document.getElementById('ux-start-all');if(!input||!workflowCatalogue)return;
 const paint=()=>{
  const {items,shown,home}=uxStartItems(workflowCatalogue,businessUX,state.user.role,state.store);
  document.getElementById('ux-start-count').textContent=items.length?(home&&!businessUX.startExpanded?`常用操作 · ${shown.length} 项`:`找到 ${items.length} 项操作`):'没有找到当前范围内的业务。可以换个词，或勾选查看其他岗位。';
  document.getElementById('ux-start-more').innerHTML=home&&items.length>UX_START_INITIAL_COUNT?`<button type="button" id="ux-expand-start">${businessUX.startExpanded?'收起':`更多操作（${items.length}）`}</button>`:'';
  document.getElementById('ux-expand-start')?.addEventListener('click',()=>{businessUX.startExpanded=!businessUX.startExpanded;paint();if(!businessUX.startExpanded)input.focus();});
  document.getElementById('ux-start-results').innerHTML=shown.map(item=>{
   const {allowed:enter,form,direct,preferNew}=uxStartEntry(item,businessUX,state.user.role,state.store);
   const primary=preferNew?'start-form':'start-page',secondary=preferNew?'start-page':'start-form';
   return `<article class="ux-start-card"><div><span class="ux-context">${E((item.requirements?.[0]?.module||item.category).replace(/模块$/,''))}</span><h3>${E(uxEntryTitle(item))}</h3></div>${uxHandoffButton('workflow:'+item.id,item.title)}<div class="ux-start-card-actions"><button type="button" class="primary" data-ux-action="${primary}" data-id="${E(item.id)}" ${enter?'':'disabled'}>${E(preferNew?form.label:uxEntryOpenLabel(item))}</button>${direct?`<button type="button" data-ux-action="${secondary}" data-id="${E(item.id)}">${E(preferNew?uxEntryOpenLabel(item):form.label)}</button>`:''}<a href="#workflows/${E(item.id)}">操作指引</a></div>${!enter?`<p class="ux-muted">${E((item.entry.roles||[]).map(r=>roleNames[r]||r).join('、'))}的入口${state.store==='all'&&item.entry.mode==='write'?'；请先选择门店':''}</p>`:''}</article>`;
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
