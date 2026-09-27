'use strict';
// Read-only navigation and display metadata. Every action enters the original
// reviewed page or form; this module cannot submit a business transaction.
const MODULE_WORKSPACES = Object.freeze([
 {key:'sales',name:'整车销售',groups:[
  ['接待与跟进',['wf-reception','wf-intent-followup','wf-intent-callback']],
  ['预订与交车',['wf-reservation-contract','wf-sale-delivery','wf-vehicle-catalog']],
  ['加装、保险与代办',['wf-sale-addon','wf-insurance-order','wf-agency-service','wf-other-customer-income','wf-vehicle-other-income']],
  ['取消与售后退回',['wf-sale-cancellation','wf-sale-aftercare']]]},
 {key:'warehouse',name:'整车仓库',groups:[
  ['查车型与库存',['wf-vehicle-catalog']],
  ['采购、发运与到货',['wf-vehicle-purchase','wf-vehicle-batch-import']],
  ['交车、调拨与移库',['wf-sale-delivery','wf-vehicle-transfer','wf-vehicle-local-move','wf-vehicle-other-out']],
  ['采购退回',['wf-vehicle-purchase-return']]]},
 {key:'repair',name:'维修管理',groups:[
  ['预约与到店开单',['wf-repair-intake','wf-repair-complete']],
  ['施工、领料与交付',['wf-repair-complete','wf-repair-materials']],
  ['核赔、报销与返修',['wf-repair-claim','wf-customer-reimbursement','wf-repair-rework']],
  ['套餐设置',['wf-repair-package']]]},
 {key:'materials',name:'物资管理',groups:[
  ['采购与收货',['wf-material-purchase','wf-material-other-in']],
  ['领用、发出与调拨',['wf-repair-materials','wf-consumable-issue-return','wf-gift-issue-return','wf-material-other-out','wf-material-transfer']],
  ['精品销售与安装',['wf-retail-sale','wf-sale-addon','wf-retail-bundle']],
  ['原单退回',['wf-material-purchase-return','wf-retail-return','wf-consumable-issue-return','wf-gift-issue-return','wf-material-other-in']],
  ['查库存、移库与盘点',['wf-material-stock-query','wf-material-local-move','wf-material-stock-count']]]},
 {key:'finance',name:'财务管理',groups:[
  ['业务收款',['wf-sale-delivery','wf-repair-complete','wf-retail-sale','wf-agency-service','wf-insurance-order','wf-other-customer-income']],
  ['预收与会员充值',['wf-customer-advance','wf-member-topup-refund']],
  ['退款与记错更正',['wf-cash-correction','wf-customer-advance','wf-member-topup-refund','wf-supplier-other-return-money']],
  ['客户欠款、月结与发票',['wf-customer-statement','wf-period-close','wf-invoice-issue-red','wf-transfer-clearing']]]},
 {key:'customers',name:'客户管理',groups:[
  ['客户与车辆资料',['wf-customer-profile','wf-customer-vehicle','wf-cross-store-service-history']],
  ['回访、保养与续保',['wf-sales-repair-callback','wf-intent-callback','wf-vehicle-reminders','wf-insurance-renewal']],
  ['咨询、投诉与救援',['wf-customer-consultation-complaint-rescue','wf-other-service-income']],
  ['问卷设置',['wf-questionnaire-design-and-answer']]]},
 {key:'members',name:'会员服务',groups:[
  ['办卡与充值',['wf-member-card','wf-member-principal','wf-recharge-bundle']],
  ['积分、券与套餐',['wf-member-points','wf-coupons-and-benefits','wf-customer-repair-package']],
  ['续会、等级与规则',['wf-member-renew-tier','wf-member-level-rules']]]},
 {key:'analytics',name:'统计分析',groups:[
  ['销售与交车',['wf-report-134','wf-report-135','wf-report-136','wf-report-137','wf-report-138','wf-report-139','wf-report-140','wf-report-141','wf-report-142']],
  ['整车库存',['wf-report-143','wf-report-144','wf-report-145']],
  ['维修服务',['wf-report-146','wf-report-147','wf-report-148','wf-report-149']],
  ['物资与精品',['wf-report-150','wf-report-151','wf-report-152','wf-report-153','wf-report-154','wf-report-155','wf-report-156']],
  ['财务收支',['wf-report-157','wf-report-158','wf-report-159','wf-report-160','wf-report-161','wf-report-162','wf-report-163']],
  ['客户与会员',['wf-report-164','wf-report-165','wf-report-166','wf-report-167','wf-report-168','wf-report-169']]]},
 {key:'reference',name:'基础数据',groups:[
  ['来往单位与服务项目',['wf-suppliers-and-insurers','wf-workshops-and-jobs','wf-agency-project-master']],
  ['车型与物资目录',['wf-vehicle-catalog-one-form','wf-material-catalog-masters']],
  ['仓库、库位与分类',['wf-warehouse-location-masters','wf-dictionary-settings']]]},
 {key:'system',name:'系统管理',groups:[
  ['员工与门店',['wf-employee-store-roles','wf-store-management']],
  ['个人密码与业务参数',['wf-parameters-password-brand']],
  ['查询操作记录',['wf-audit-business-history']]]}
]);
let moduleUX = {context:null,views:{},intent:null,taskDue:''};
function clearModuleUX(){moduleUX={context:uxContext(),views:{},intent:null,taskDue:''};}
function moduleSync(){if(moduleUX.context!==uxContext())clearModuleUX();}
function moduleSpec(key){return MODULE_WORKSPACES.find(m=>m.key===key);}
function moduleForName(name){return MODULE_WORKSPACES.find(m=>m.name===name);}
function moduleView(key){moduleSync();return moduleUX.views[key]||(moduleUX.views[key]={query:'',group:null,otherRoles:false});}
function moduleCatalogue(spec,catalogue){
 // Include every original requirement mapped to this module, even if a future
 // catalogue adds a workflow not listed in the curated display groups.
 const curated=new Set(spec.groups.flatMap(g=>g[1]));
 return catalogue.workflows.filter(w=>curated.has(w.id)||(w.requirements||[]).some(r=>r.module===spec.name+'模块'));
}
function moduleGroups(spec,items){
 const ids=new Set(items.map(w=>w.id)),used=new Set(spec.groups.flatMap(g=>g[1]));
 const groups=spec.groups.map(([title,keys],index)=>({key:String(index),title,ids:keys.filter(id=>ids.has(id))})).filter(g=>g.ids.length);
 const rest=items.filter(w=>!used.has(w.id)).map(w=>w.id);
 if(rest.length)groups.push({key:'more',title:'其他操作',ids:rest});
 return groups;
}
function moduleItems(spec,catalogue,view,role,store){
 const all=moduleCatalogue(spec,catalogue),allowed=all.filter(w=>view.otherRoles||WorkflowGuides.canEnter(w,role,store));
 const groups=moduleGroups(spec,allowed);let selected=groups.find(g=>g.key===view.group)||groups[0];
 const items=view.query.trim()?WorkflowGuides.search(allowed,view.query,role):selected?selected.ids.map(id=>allowed.find(w=>w.id===id)).filter(Boolean):[];
 return {all,allowed,groups,selected,items};
}
function moduleTaskRows(data){return data.items.map(t=>`<div class="mux-task"><div><strong>${E(t.title)}</strong><p>${E(t.case_number)} · ${E(t.case_title)}</p><p>${E(t.assignee_name)} · 计划 ${E(t.due_date)}${t.overdue?' · 已逾期':''}</p>${t.blocked?`<p class="ux-block-reason">${E(t.block_reason)}</p>`:''}</div><a class="button ${t.blocked?'':'primary'}" href="#${E(uxTaskRoute(t))}">${t.blocked?'查看缺少的条件':'接着办理'}</a></div>`).join('');}
async function moduleWorkspacePage(key){
 const spec=moduleSpec(key);if(!spec)throw new Error('工作模块不存在，请从左侧重新选择。');
 moduleSync();const view=moduleView(key),catalogue=await loadWorkflowGuides();
 // A failed read is shown as a failure, never represented as an empty queue.
 let tasks=null,taskError='';
 if(!['analytics','reference','system'].includes(key)&&state.store!=='all'){
  try{tasks=await api('/api/flow/tasks?scope=mine&status=open&page_size=5&area='+encodeURIComponent(key));}catch(error){if(error.staleContext)throw error;taskError=error.message;}
 }
 const taskPanel=tasks?.total?`<section class="mux-my-work ${tasks.total?'':'mux-empty-work'}" aria-label="本模块我的待办"><div class="spread"><h2>${tasks.total?`我的待办 · ${number(tasks.total)}`:'本模块暂无我的待办'}</h2><a href="#work/${key}" class="button">我的待办</a></div>${tasks.total?moduleTaskRows(tasks):''}${tasks.total>tasks.items.length?`<p>这里只显示最早到期的 ${tasks.items.length} 项，共 ${number(tasks.total)} 项。</p>`:''}</section>`:taskError?`<div class="notice warn" role="alert">待办暂未读取成功：${E(taskError)} ${b('refresh','重试')}</div>`:'';
 return heading(spec.name,'',`${key==='analytics'?'<a class="button primary" href="#analytics/overview">经营总览</a>':`<a class="button" href="#${['reference','system'].includes(key)?'work':'work/'+key}">我的工作</a>`}<a class="button" href="#start">快捷操作</a>`)+storeNotice()+taskPanel+`<section class="mux-browser" data-module-workspace="${key}"><div class="mux-search"><label>搜索本模块业务<input id="mux-query" type="search" maxlength="100" placeholder="例如：${E(catalogue.requirements?.find(r=>r.module===spec.name+'模块')?.title||spec.name)}" value="${E(view.query)}" autocomplete="off"></label><details class="mux-extra-options" ${view.otherRoles?'open':''}><summary>其他岗位</summary><label class="checklabel"><input type="checkbox" id="mux-other" ${view.otherRoles?'checked':''}>显示其他岗位操作</label></details></div><div id="mux-groups" class="mux-groups" aria-label="选择本次办事目的"></div><p id="mux-results-title" role="status"></p><div id="mux-results" class="mux-results"></div></section>`;
}
function moduleCardGroups(items,role,store){
 const groups=new Map();
 for(const item of items){const key=item.entry.route+'|'+WorkflowGuides.canEnter(item,role,store);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(item);}
 return [...groups.values()];
}
function moduleCard(item,spec,related=[item]){
 const allowed=WorkflowGuides.canEnter(item,state.user.role,state.store);
 const title=uxEntryTitle(item,related.length>1);
 const newItem=related.find(w=>WorkflowGuides.canEnter(w,state.user.role,state.store)&&WORKFLOW_QUICK_FORMS[w.id]&&UX_CREATE_FIRST.has(w.id));const newForm=newItem&&WORKFLOW_QUICK_FORMS[newItem.id];
 // No default creation for follow-ups. New forms are explicitly labelled and
 // used only by the existing reviewed quick-form registry, after another click.
 const create=allowed&&state.store!=='all'&&newItem;
 return `<article class="mux-card"><h3>${E(title)}</h3><div class="row"><button type="button" class="primary" data-mux-open="${E(item.id)}" data-area="${spec.key}" ${allowed?'':'disabled'}>${E(uxEntryOpenLabel(item))}</button>${create?`<button type="button" data-mux-form="${E(newItem.id)}" data-area="${spec.key}">${E(newForm.label)}</button>`:''}</div><details class="mux-requirements"><summary>操作指引</summary><p>${E([...new Set(related.flatMap(w=>(w.requirements||[]).map(r=>r.title)))].join('、'))}</p>${related.map(w=>`<p><a href="#workflows/${E(w.id)}">${E(w.title)}</a></p>`).join('')}</details>${!allowed?`<p class="mux-role">${state.store==='all'&&item.entry.mode==='write'?'请先选择具体门店。':'此入口由 '+E((item.entry.roles||[]).map(r=>roleNames[r]||r).join('、'))+' 办理。'}</p>`:''}</article>`;
}
function bindModuleWorkspace(){
 const root=document.querySelector('[data-module-workspace]');if(!root||!workflowCatalogue)return;
 const spec=moduleSpec(root.dataset.moduleWorkspace),view=moduleView(spec.key),input=root.querySelector('#mux-query');
 const paint=()=>{
  const data=moduleItems(spec,workflowCatalogue,view,state.user.role,state.store),cards=moduleCardGroups(data.items,state.user.role,state.store);
  root.querySelector('#mux-groups').innerHTML=data.groups.map(g=>`<button type="button" data-mux-group="${g.key}" aria-pressed="${!view.query.trim()&&g===data.selected}">${E(g.title)}</button>`).join('');
  root.querySelector('#mux-results-title').textContent=view.query.trim()?`找到 ${cards.length} 项操作`:(data.selected?data.selected.title:'当前岗位没有可直接进入的功能，可查看其他岗位或返回我的工作。');
  root.querySelector('#mux-results').innerHTML=cards.map(items=>moduleCard(items[0],spec,items)).join('')||empty('当前条件下没有匹配入口','请调整关键词或筛选条件。');
 };
 input.addEventListener('input',event=>{view.query=input.value;if(!event.isComposing)paint();});input.addEventListener('compositionend',()=>{view.query=input.value;paint();});
 root.querySelector('#mux-other').addEventListener('change',event=>{view.otherRoles=event.target.checked;paint();});
 root.addEventListener('click',event=>{const button=event.target.closest('[data-mux-group]');if(!button)return;view.group=button.dataset.muxGroup;view.query='';input.value='';paint();root.querySelector(`[data-mux-group="${view.group}"]`)?.focus();});paint();
}
const MODULE_ROUTE_AREAS = Object.freeze({
 'sales-quotes':'sales','aftercare':'sales','addon-orders':'sales','insurance-orders':'sales','service-orders':'sales','vehicle-income':'sales',
 'vehicle-procurement':'warehouse','vehicle-transfers':'warehouse','vehicle-operations':'warehouse','vehicle-operation':'warehouse','vehicle-catalog':'warehouse','vehicle-imports':'warehouse','vehicle-import':'warehouse','vehicle-transport-exceptions':'warehouse',
 'repair-orders':'repair','service-intake':'repair','claims':'repair','rework-extensions':'repair',
 'procurement':'materials','retail':'materials','warehouse':'materials','warehouse-item':'materials','warehouse-allocation':'materials','transfers':'materials','transfer-exceptions':'materials','retail-bundles':'materials',
 'business-finance':'finance','business-finance-order':'finance','invoices':'finance','reconciliation':'finance','clearing':'finance',
 'customer-service':'customers','customer-vehicles':'customers','customer-reminders':'customers','customer-questionnaires':'customers','customer-history-grants':'customers','dossier-grants':'customers',
 'membership':'members','membership-order':'members','membership-rules':'members','recharge-bundles':'members','recharge-bundle-order':'members','group':'members','benefits':'members','repair-packages':'members','member-pricing':'members',
 'analytics':'analytics','table':'analytics','vehicle-period':'analytics','warehouse-period':'analytics','stock-period':'analytics','material-value':'analytics','visit-activity':'analytics','customer-value':'analytics','repair-materials':'analytics','procurement-cohort':'analytics',
 'masters':'reference','dictionaries':'reference','opening':'reference','opening-import':'reference','opening-balances':'reference','business-entities':'reference',
 'users':'system','stores':'system','audit':'system','parameters':'system'
});
function moduleRouteArea(){
 const [root,key]=state.route.split('/');if(root==='cases')return state.catalog?.kinds[key]?.module||null;
 if(root==='case')return state.row?.kind?state.catalog?.kinds[state.row.kind]?.module:null;
 if(root==='master')return {customers:'customers',members:'members',items:'materials'}[key]||'reference';
 if(root==='legacy')return key==='vehicles'?'warehouse':key==='cash'?'finance':null;
 return MODULE_ROUTE_AREAS[root]||null;
}
function mountModuleUX(){
 moduleSync();if(state.route.startsWith('module/')){bindModuleWorkspace();return;}
 const main=document.getElementById('main');if(!main)return;
 const area=moduleRouteArea(),spec=moduleSpec(area);if(!spec)return;
 const intent=moduleUX.intent,root=state.route.split('/')[0];
 const active=intent&&intent.context===uxContext()&&(root===intent.route.split('/')[0]);
 const bar=document.createElement('nav');bar.className='mux-contextbar';bar.setAttribute('aria-label','模块与本次办理意图');
 bar.innerHTML=`<a href="#module/${active?intent.area:area}">${E(moduleSpec(active?intent.area:area)?.name||spec.name)}</a>`;
 const head=main.querySelector('.pagehead');if(head)head.before(bar);else main.prepend(bar);
 mountModuleSectionIndex(main);mountReportPresets(main);mountNativeActionGroups(main);
}
function mountModuleSectionIndex(main){
 // Jump links, not hidden panels. Native controls and evidence remain in place.
 const sections=[...main.querySelectorAll('section.panel')].filter(p=>!p.closest('.ux-now')&&p.querySelector('.panelhead h2'));
 if(sections.length<4)return;
 const disclosure=document.createElement('details');disclosure.className='mux-section-disclosure';
 const summary=document.createElement('summary');summary.textContent='本页内容';disclosure.append(summary);
 const nav=document.createElement('nav');nav.className='mux-section-index';nav.setAttribute('aria-label','本页内容');disclosure.append(nav);
 sections.forEach((section,index)=>{section.id='mux-section-'+index;const button=document.createElement('button');button.type='button';button.textContent=section.querySelector('.panelhead h2').textContent;button.addEventListener('click',()=>{for(let d=section.parentElement?.closest('details');d;d=d.parentElement?.closest('details'))d.open=true;section.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});section.tabIndex=-1;section.focus({preventScroll:true});});nav.append(button);});
 const anchor=main.querySelector('.ux-now')||main.querySelector('.pagehead');anchor?.after(disclosure);
}
function moduleWorkFilters(){
 moduleSync();const current=state.route.split('/')[1]||'';
 return `<nav class="mux-work-filter" aria-label="筛选工作模块"><a class="button ${!current?'primary':''}" href="#work">全部模块</a>${MODULE_WORKSPACES.filter(m=>!['analytics','reference','system'].includes(m.key)).map(m=>`<a class="button ${m.key===current?'primary':''}" href="#work/${m.key}">${E(m.name)}</a>`).join('')}</nav>${state.taskStatus==='open'?`<div class="mux-work-due" aria-label="按计划日期筛选">${[['','全部日期'],['today','计划今天'],['overdue','已逾期']].map(([key,label])=>`<button type="button" data-mux-due="${key}" aria-pressed="${moduleUX.taskDue===key}">${label}</button>`).join('')}</div>`:''}`;
}
function moduleTaskQuery(){moduleSync();const area=state.route.split('/')[1]||'';return new URLSearchParams({scope:state.taskScope,status:state.taskStatus,page:state.page,area:moduleSpec(area)?area:'',q:state.q,due:state.taskStatus==='open'?moduleUX.taskDue:''});}
function workRecordSearch(placeholder,maxLength=100){
 return searchBar().replace('placeholder="输入姓名、单号或关键词"',`placeholder="${E(placeholder)}" maxlength="${Number(maxLength)}"`);
}
function workActionGroups(groups){return `<div class="mux-action-groups">${groups.filter(g=>g.html).map(g=>`<${g.secondary?'details':'section'} class="mux-action-group">${g.secondary?`<summary>${E(g.title)}</summary>`:`<h3>${E(g.title)}</h3>`}<div class="row">${g.html}</div></${g.secondary?'details':'section'}>`).join('')}</div>`;}
function mountNativeActionGroups(main){
 // Reviewed header-only exceptional actions. Original record-level return
 // buttons stay alongside the original line; nothing is inferred from text.
 const secondaryKeys=new Set(['cancel','reject','quote_cancel','return_cancel','termination_cancel','cancel_remaining','cancel_request','withdraw','quote_withdraw','reschedule','no_show','leave']);
 const knownActs=new Set(['membership-action','business-finance-action','intake-action','care-action','vp-action','repair-action']);
 const head=main.querySelector('.pagehead');if(!head)return;
 const buttons=[...head.querySelectorAll('button[data-act]')].filter(b=>knownActs.has(b.dataset.act)&&secondaryKeys.has(b.dataset.key||b.dataset.action));
 if(!buttons.length)return;
 const details=document.createElement('details');details.className='mux-secondary-actions';details.innerHTML='<summary>调整、退回或取消</summary>';buttons.forEach(b=>details.append(b));head.querySelector('.row')?.append(details);
}
function mountReportPresets(main){
 const form=main.querySelector('#datefilters');if(!form||!form.elements.date_from||!form.elements.date_to||form.querySelector('[data-act=range]'))return;
 const nav=document.createElement('div');nav.className='mux-date-presets';nav.setAttribute('aria-label','常用查询期间');
 for(const [key,label]of [['today','今天'],['week','近七天'],['month','本月']]){const button=document.createElement('button');button.type='button';button.textContent=label;button.addEventListener('click',()=>{const end=day();form.elements.date_to.value=end;form.elements.date_from.value=key==='month'?end.slice(0,8)+'01':key==='week'?relativeDay(-6,end):end;form.requestSubmit();});nav.append(button);}form.prepend(nav);
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-mux-open],[data-mux-form],[data-mux-due],[data-mux-clear]');if(!button||button.disabled||!state.user||state.storeSwitch)return;
 moduleSync();
 if(button.hasAttribute('data-mux-due')){moduleUX.taskDue=button.dataset.muxDue;state.page=1;await render();return;}
 if(button.hasAttribute('data-mux-clear')){moduleUX.intent=null;await render();return;}
 const id=button.dataset.muxOpen||button.dataset.muxForm,item=workflowCatalogue?.workflows.find(w=>w.id===id),area=button.dataset.area;
 if(!item||!moduleSpec(area)||!WorkflowGuides.canEnter(item,state.user.role,state.store))return;
 moduleUX.intent={context:uxContext(),id,title:item.title,route:item.entry.route,area};
 try{if(button.hasAttribute('data-mux-form'))await workflowOpenForm(id);else workflowNavigate(item.entry.route);}catch(error){toast(error.message,true);}
});
