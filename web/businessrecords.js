'use strict';
// V2 records are independent from the historical inventory/accounting workflows.
// Capabilities and available actions come from the server; every mutation still
// rechecks identity, store, version and idempotency in its own transaction.
const BR_API='/api/business-records';
const BR_STATUS={submitted:'待内勤核价',priced:'待管理审批',approved:'审批通过',rejected:'退回修改'};
let brState={drafts:{},report:null,detail:null,settings:null,filters:null,view:'auto',customerView:null};
function clearBusinessRecords(){brState={drafts:{},report:null,detail:null,settings:null,filters:null,view:'auto',customerView:null};state.recordCatalog=null;}
function brCaps(){return state.recordCatalog?.capabilities||{};}
function brButton(action,label,extra='',cls=''){return `<button type="button" data-br="${E(action)}" ${extra} class="${E(cls)}">${E(label)}</button>`;}
function brLink(route,label){return `<a class="button" href="#${E(route)}">${E(label)}</a>`;}
function brAmount(value){return value==null?'待核定':money(value)+' 元';}
function brInputAmount(value){return value==null?'':(value/100).toFixed(2);}
function brSignedAmount(value,label){const text=moneyDigits(value);return text.startsWith('-')?-moneyFen(text.slice(1),{label,allowZero:true}):moneyFen(text,{label,allowZero:true});}
function brPercentage(value){if(String(value).trim()==='')return null;const result=moneyFen(value,{label:'车价比例',allowZero:true});if(result>10000)throw new Error('车价比例不能超过 100%。');return result;}
function brOptions(items,value){return items.map(item=>`<option value="${E(item.value)}" ${String(item.value)===String(value)?'selected':''}>${E(item.label)}</option>`).join('');}
function brFacts(entries){return `<dl class="br-facts">${entries.map(([label,value])=>`<div><dt>${E(label)}</dt><dd>${E(value==null||value===''?'—':value)}</dd></div>`).join('')}</dl>`;}
function brContext(){return `${state.user?.id||''}:${state.store||''}:${storeContextVersion}`;}
function businessRecordsShell(){
 const u=state.user,caps=brCaps();
 const financeAllowed=caps.confirm_receipt||caps.price||caps.approve||['admin','manager','general_manager','chairman','auditor'].includes(u.role);
 const links=[['records-sales','销售业务','▤'],['records-after-sales','售后业务','◇'],...(financeAllowed?[['records-finance','财务流水','¥']]:[]),['records-customers','客户信息','▧']];
 const navHTML=links.map(([route,label,icon])=>`<a class="navlink ${state.route===route||state.route.startsWith(route+'/')?'active':''}" href="#${route}"${state.route===route?' aria-current="page"':''}><span class="navicon">${icon}</span>${label}</a>`).join('');
 const assistantNav=`<div class="navsection"><a class="navlink ${state.route==='business-assistant'?'active':''}" href="#business-assistant"${state.route==='business-assistant'?' aria-current="page"':''}><span class="navicon">✧</span>AI 助手</a></div>`;
 const management=u.can_users?'<a href="#users">员工账号</a><a href="#stores">门店设置</a>':'';
 const accountMenu=`<details class="br-account-menu"><summary aria-label="账号与管理"><span class="avatar">${E(u.display_name?.[0]||'')}</span><span class="br-account-name">${E(u.display_name)}<small>${E(u.role_label)}</small></span><span class="br-account-chevron" aria-hidden="true">⌄</span></summary><div class="br-account-popover">${management}${u.can_audit?'<a href="#audit">操作记录</a>':''}<a href="#feedback">意见反馈</a>${b('password','修改密码','','ghost')}${b('logout','退出登录','','ghost')}</div></details>`;
 $('#app').innerHTML=`<div class="layout br-layout"><aside class="sidebar"><a class="br-home-brand" href="#records-dashboard" aria-label="返回经营看板">${huakangBrand()}</a><div class="br-product">业务记录</div><nav class="nav" aria-label="业务导航">${navHTML}${assistantNav}</nav><div class="sidefoot"><span class="statusdot"></span>${E(u.role_label)}</div></aside><div class="workspace"><header class="topbar"><div class="row storeline">${b('menu','☰','aria-label="打开业务导航"','iconbtn ghost mobilemenu')}<a class="br-dashboard-link" href="#records-dashboard"${state.route==='records-dashboard'?' aria-current="page"':''}>经营看板</a><span class="hk-store-label">当前门店</span><select id="store" aria-label="当前门店">${state.stores.filter(s=>s.active!==false).map(s=>`<option value="${s.id}" ${String(s.id)===String(state.store)?'selected':''}>${E(s.name)}</option>`).join('')}${u.can_group_summary?`<option value="all" ${state.store==='all'?'selected':''}>已授权门店汇总</option>`:''}</select></div><div class="row br-top-tools">${accountMenu}</div></header><main id="main"><div class="loading">正在读取…</div></main></div></div>`;
 $('#store').onchange=e=>switchStore(e.target.value);
 $('.br-account-popover').onclick=event=>{if(event.target.closest('a,button'))$('.br-account-menu').open=false;};
}
async function brCatalog(){if(!state.recordCatalog)state.recordCatalog=await api(BR_API+'/catalog');return state.recordCatalog;}
function brListFilters(status=false){return `<form id="br-list-filter" class="br-filter"><label>查找记录<input name="q" type="search" value="${E(state.q)}" placeholder="合同号、客户或车辆"></label>${status?`<label>合同状态<select name="status"><option value="">全部状态</option>${brOptions(Object.entries(BR_STATUS).map(([value,label])=>({value,label})),state.status)}</select></label>`:''}<button class="primary" type="submit">查询</button></form>`;}
function brPageURL(path,extra={}){return BR_API+path+'?'+new URLSearchParams({q:state.q,page:state.page,page_size:30,...extra});}
async function businessRecordsPage(type,id){
 await brCatalog();brState.detail=null;
 if(type==='records-dashboard')return brDashboard();
 if(type==='records-sales')return id?brContract(Number(id)):brContracts(false);
 if(type==='records-finance')return brContracts(true);
 if(type==='records-after-sales')return brAfterSales();
 if(type==='records-customers')return id?brCustomer(Number(id)):brCustomers();
 if(type==='records-manual')return brManualReports();
 if(type==='records-settings')return brSettings();
 throw new Error('记录页面不存在。');
}
async function brContracts(finance){
 const d=await api(brPageURL('/contracts',{status:finance?'approved':state.status}));
 const headers=['合同号','客户 / 车辆','所属销售','状态','应到账','实到账','到账日期','操作'];
 const rows=d.items.map(r=>[E(r.number),`<strong>${E(r.customer_name)}</strong><div class="muted">${E([r.brand,r.model].filter(Boolean).join(' '))}</div>`,E(r.salesperson_name),pill(r.status,BR_STATUS[r.status]),brAmount(r.expected_amount_cents),r.actual_amount_cents==null?'未确认':brAmount(r.actual_amount_cents),E(r.received_on||'—'),brLink('records-sales/'+r.id,finance?'核对合同':'查看合同')]);
 return heading(finance?'财务流水':'销售业务',finance?'按合同号人工核对到账。应到账与实到账分别记录。':'填单 → 内勤核价 → 管理审批 → 打印合同',(!finance&&brCaps().manage_settings?brLink('records-settings','赠品审批设置'):'')+(!finance&&brCaps().create_sales?brButton('new-contract',brState.drafts.contract?'继续填写合同':'填写销售合同','','primary'):''))+storeNotice()+brListFilters(!finance)+`<section class="panel">${table(headers,rows)}${pager(d.total)}</section>`;
}
async function brContract(id){
 const epoch=renderId,r=await api(BR_API+'/contracts/'+id);if(epoch!==renderId)return '';brState.detail=r;
 const actionLabels={edit:'修改合同',price_review:'内勤核价',approve:'管理审批通过',reject:'退回修改',receipt:'确认合同到账',print:'打印合同'};
 const actions=(r.actions||[]).map(action=>brButton('contract-action',actionLabels[action]||action,`data-action="${E(action)}"`,['price_review','approve','receipt','print'].includes(action)?'primary':'')).join('');
 const steps=[['submitted','销售填单'],['priced','内勤核价'],['approved','管理审批']];const index=steps.findIndex(([status])=>status===r.status);
 const progress=`<div class="br-steps">${steps.map(([status,label],i)=>`<span class="${i<=index?'complete':''}">${i+1}. ${label}</span>`).join('')}<span class="${r.actual_amount_cents!=null?'complete':''}">4. 财务确认到账</span></div>`;
 const form=r.form_data||{},customerLink=r.customer_id?brLink('records-customers/'+r.customer_id,'查看客户档案'):'';
 return heading('销售合同 '+r.number,[r.customer_name,r.brand,r.model].filter(Boolean).join(' · '),customerLink+brLink('records-sales','返回销售业务'))+progress+`<section class="panel"><div class="panelhead spread"><h2>${E(BR_STATUS[r.status]||r.status)}</h2><div class="row">${actions}</div></div><div class="panelbody">${r.status==='rejected'?'<p class="notice warn">合同已退回，请根据核对记录修改后重新提交。</p>':''}${brFacts([['合同号',r.number],['合同日期',r.contract_date],['所属门店',r.store_name],['所属销售',r.salesperson_name],['客户姓名',r.customer_name],['联系电话',r.customer_phone],['品牌',r.brand],['车型',r.model],['车辆识别号 VIN',r.vin],['销售金额',brAmount(r.sale_price_cents)],['应到账金额',brAmount(r.expected_amount_cents)],['核定成本',brAmount(r.cost_cents)],['核定利润',brAmount(r.profit_cents)],['赠品核定成本',brAmount(r.gift_cost_cents)],['实到账金额',r.actual_amount_cents==null?'未确认':brAmount(r.actual_amount_cents)],['实际到账日期',r.received_on],['内勤核价说明',r.price_note],['审批 / 退回说明',r.approval_note],['到账核对说明',r.receipt?.note]])}<div class="br-note"><strong>赠品约定</strong><p>${E(r.gift_description||'未填写')}</p></div></div></section><details class="panel br-disclosure"><summary>合同填单内容</summary>${brFacts(brContractExtraFields().map(f=>[f.label,form[f.key]]))}</details>${Array.isArray(r.events)&&r.events.length?`<details class="panel br-disclosure"><summary>核对与操作记录</summary>${table(['时间','操作人','操作','说明'],r.events.map(e=>[time(e.created_at),E(e.actor_name),E(e.action),E(e.note||'—')]))}</details>`:''}<p class="br-caption">审批通过后打印，两份合同线下签字流转；系统保留合同号和核定记录供人工核对。</p>`;
}
function brContractExtraFields(){return [
 F('seller_name','卖方名称'),F('seller_phone','卖方联系电话','text',false),F('seller_address','卖方地址','text',false),F('seller_agent','卖方委托代理人','text',false),
 F('buyer_document_name','买方证件名称','text',false),F('buyer_id_number','买方证件号码','text',false),F('buyer_address','买方地址','text',false),F('buyer_postcode','买方邮编','text',false),F('buyer_agent','买方委托代理人','text',false),F('buyer_agent_id_number','代理人证件号码','text',false),F('buyer_email','买方电子邮箱','text',false),
 F('exterior_color','车身颜色','text',false),F('interior_color','内饰颜色','text',false),F('quantity','购车数量（每合同一辆）','int'),F('subsidy_deposit','置换补贴押金（元）','money_zero',false),F('corporate_subsidy_deposit','大客户补贴押金（元）','money_zero',false),F('deposit','定金（元）','money_zero',false),F('balance','余款（元）','money_zero',false),
 F('payment_method','付款方式','select',true,[{value:'全款',label:'全款'},{value:'贷款',label:'贷款'}]),F('payment_bank','贷款银行','text',false),F('loan_amount','贷款金额（元）','money_zero',false),F('delivery_date','提车日期','date',false),F('delivery_place','提车地点','text',false),F('signature_date','签订日期','date'),F('other_terms','其他约定','textarea',false)
 ];}
async function brForm(title,groups,values,save,{draftKey,submit='确认保存',notice='',nextRoute}={}){
 const context=brContext(),fields=groups.flatMap(group=>group.fields),existing=brState.drafts[draftKey];
 const initial=existing?.context===context?existing.values:values;const request_id=existing?.request_id||requestKey();
 const body=(await Promise.all(groups.map(async group=>`<fieldset class="br-form-section"><legend>${E(group.title)}</legend><div class="formgrid">${(await Promise.all(group.fields.map(f=>fieldHTML(f,initial[f.key]??(!f.required?'':defaultValue(f)))))).join('')}</div></fieldset>`))).join('');
 if(context!==brContext())throw new Error('门店或账号已切换，请重新打开填单。');
 const dialog=modal(title,`<form data-br-form="${E(draftKey)}">${notice?`<div class="notice">${E(notice)}</div>`:''}${body}<p class="br-caption">未提交内容只保留在当前页面会话，换店、退出或刷新后清除。</p><div class="formerror" role="alert"></div><div class="modalfoot">${brButton('defer-form','稍后再填')}<button class="primary" type="submit">${E(submit)}</button></div></form>`,async form=>{
  if(context!==brContext())throw new Error('门店或账号已切换，请重新打开填单。');
  brState.drafts[draftKey]={context,request_id,values:formValues(form,fields)};
  const result=await save(formValues(form,fields),request_id);
  delete brState.drafts[draftKey];closeModal();if(nextRoute){go(nextRoute(result));}else await render();toast('已保存');
 });
 const form=$('form',dialog),remember=()=>{brState.drafts[draftKey]={context,request_id,values:formValues(form,fields)};};
 form.addEventListener('input',remember);form.addEventListener('change',remember);
 return dialog;
}
async function brNewContract(edit=false){
 const r=edit?brState.detail:null;if(edit&&!r)throw new Error('请先重新读取合同。');
 const people=(state.recordCatalog.sales_people||[]).map(p=>({value:p.id,label:p.label}));
 const main=[F('customer_name','客户姓名'),F('customer_phone','客户联系电话'),F('salesperson_id','所属销售','select',true,people),F('contract_date','合同日期','date'),F('brand','车辆品牌'),F('model','车型'),F('vin','车辆识别号 VIN'),F('sale_price','销售金额（元）','money'),F('gift_description','赠品及赠送约定','textarea',false)];
 const extra=brContractExtraFields();
 const dialog=await brForm(edit?'修改销售合同':'填写销售合同',[{title:'客户与销售业务',fields:main},{title:'合同双方资料',fields:extra.slice(0,11)},{title:'交付与付款约定',fields:extra.slice(11)}],{...(r?.form_data||{}),...(r||{}),sale_price:brInputAmount(r?.sale_price_cents),salesperson_id:r?.salesperson_id||(state.user.role==='sales'?state.user.id:''),quantity:r?.form_data?.quantity||1,signature_date:r?.form_data?.signature_date||day()},async(v,request_id)=>{
  const form_data=Object.fromEntries(extra.map(f=>[f.key,v[f.key]]));
  for(const f of extra.filter(f=>f.type==='money_zero'))if(form_data[f.key]!=='')form_data[f.key]=(moneyFen(form_data[f.key],{label:f.label,allowZero:true})/100).toFixed(2);
  if(form_data.quantity!==1)throw new Error('每份合同记录一辆车及其 VIN，请分别填单。');
  form_data.quantity=String(form_data.quantity);
  return api(BR_API+'/contracts'+(r?'/'+r.id:''),{method:r?'PUT':'POST',body:{request_id,...(r?{version:r.version}:{}),customer_name:v.customer_name,customer_phone:v.customer_phone,salesperson_id:Number(v.salesperson_id),contract_date:v.contract_date,brand:v.brand,model:v.model,vin:v.vin,sale_price_cents:moneyFen(v.sale_price,{label:'销售金额'}),gift_description:v.gift_description,form_data}});
 },{draftKey:r?'contract-'+r.id:'contract',submit:'提交内勤核价',notice:'直接填写客户与车辆信息，保存时自动建立或关联客户档案。提交后先由内勤人工核价，再由管理人员审批。',nextRoute:result=>'records-sales/'+result.id});
 const quantity=dialog.querySelector('[name=quantity]');quantity.readOnly=true;
}
async function brContractAction(action){
 const r=brState.detail;if(!r||(r.actions||[]).includes(action)===false)throw new Error('当前合同不能执行此操作，请刷新核对。');
 if(action==='edit')return brNewContract(true);
 if(action==='print')return download(BR_API+'/contracts/'+r.id+'/print',r.number+'.pdf');
 let fields,title,path=action,values={},notice='';
 if(action==='price_review'){title='内勤人工核价';path='price-review';fields=[F('expected_amount','应到账金额（元）','money_zero'),F('cost','核定成本（元）','money_zero'),F('profit','核定利润（元）'),F('gift_cost','赠品核定成本（元）','money_zero'),F('note','核价说明','textarea',false)];values={expected_amount:brInputAmount(r.expected_amount_cents??r.sale_price_cents),cost:brInputAmount(r.cost_cents),profit:brInputAmount(r.profit_cents),gift_cost:brInputAmount(r.gift_cost_cents)};notice='逐项填写人工核定结果。核价通过后仍需管理审批，才可打印。';}
 else if(action==='receipt'){title='确认合同到账';fields=[F('actual_amount','人工核实的实际到账金额（元）','money'),F('received_on','实际到账日期','date'),F('note','核对说明','textarea',false)];notice='请先按合同号线下核对。每份合同仅确认一次汇总到账金额，业绩按所填实际到账日期统计。';}
 else if(action==='approve'){title='管理审批通过';fields=[F('note','审批说明','textarea',false)];notice=`确认合同 ${r.number} 的金额和赠品核价后放行打印。审批不代表客户已签字或款项已到账。`;}
 else if(action==='reject'){title='退回修改';fields=[F('note','退回原因','textarea')];}
 else throw new Error('不支持的合同操作。');
 await brForm(title,[{title:r.number,fields}],values,(v,request_id)=>{
  const body={request_id,version:r.version,note:v.note};
  if(action==='price_review')Object.assign(body,{expected_amount_cents:moneyFen(v.expected_amount,{allowZero:true}),cost_cents:moneyFen(v.cost,{allowZero:true}),profit_cents:brSignedAmount(v.profit,'核定利润'),gift_cost_cents:moneyFen(v.gift_cost,{allowZero:true})});
  if(action==='receipt')Object.assign(body,{actual_amount_cents:moneyFen(v.actual_amount),received_on:v.received_on});
  return api(BR_API+'/contracts/'+r.id+'/'+path,{method:'POST',body});
 },{draftKey:`${action}-${r.id}-${r.version}`,submit:title,notice});
}
function brCustomerTabs(){return [...(state.user.role==='service'?[]:[{key:'contracts',label:'销售合同',count:'contract_count'}]),{key:'after-sales',label:'售后记录',count:'after_sales_count'}];}
function brCustomerCount(value){return value==null?'—':number(value);}
async function brCustomers(){
 const d=await api(brPageURL('/customers')),tabs=brCustomerTabs();
 const rows=d.items.map(r=>[E(r.name),E(r.phone||'—'),E(r.owner_name||'—'),...tabs.map(t=>brCustomerCount(r[t.count])),`<span class="wrap">${E(r.note||'—')}</span>`,brLink('records-customers/'+r.id,'查看业务')]);
 return heading('客户信息','销售合同和售后记录保存时自动建档，按客户查看已关联业务。',brCaps().manage_customers?brButton('new-customer',brState.drafts.customer?'继续填写客户信息':'新增客户','','primary'):'')+storeNotice()+brListFilters()+`<section class="panel">${table(['客户姓名','联系电话','所属人员',...tabs.map(t=>t.label+'数'),'备注','操作'],rows)}${pager(d.total)}</section>`;
}
function brCustomerView(id){
 const context=brContext(),tabs=brCustomerTabs();let view=brState.customerView;
 if(!view||view.id!==id||view.context!==context)view=brState.customerView={id,context,tab:tabs[0].key,pages:{contracts:1,'after-sales':1}};
 if(!tabs.some(t=>t.key===view.tab))view.tab=tabs[0].key;
 return view;
}
function brCustomerPager(data,tab){return `<div class="pagination"><span>共 ${number(data.total)} 条 · 第 ${number(data.page)} 页</span><div class="row">${brButton('customer-page','上一页',`data-tab="${tab}" data-page="${data.page-1}" ${data.page<=1?'disabled':''}`)}${brButton('customer-page','下一页',`data-tab="${tab}" data-page="${data.page+1}" ${data.page*data.page_size>=data.total?'disabled':''}`)}</div></div>`;}
async function brCustomer(id){
 const epoch=renderId,context=brContext(),view=brCustomerView(id),tab=view.tab,page=view.pages[tab];
 // Fetch just the selected business page; each endpoint applies its own scope.
 const [customer,data]=await Promise.all([api(BR_API+'/customers/'+id),api(BR_API+'/'+tab+'?'+new URLSearchParams({customer_id:id,page,page_size:20}))]);
 if(epoch!==renderId||context!==brContext()||brState.customerView!==view)return '';
 view.pages[tab]=data.page;
 const tabs=brCustomerTabs(),types=Object.fromEntries((state.recordCatalog.service_types||[]).map(s=>[s.value,s.label]));
 const headers=tab==='contracts'?['合同号','合同日期','车辆','所属销售','状态','销售金额','应到账','实到账']:['业务日期','业务类型','车辆','服务项目','材料费','工时费','核定成本','经办人'];
 const rows=tab==='contracts'?data.items.map(r=>[`<a class="br-record-link" href="#records-sales/${E(r.id)}">${E(r.number)}</a>`,E(r.contract_date),E([r.brand,r.model].filter(Boolean).join(' ')),E(r.salesperson_name),pill(r.status,BR_STATUS[r.status]),brAmount(r.sale_price_cents),brAmount(r.expected_amount_cents),r.actual_amount_cents==null?'未确认':brAmount(r.actual_amount_cents)]):data.items.map(r=>[E(r.business_date),E(types[r.service_type]||r.service_type),E(r.vehicle),`<span class="wrap">${E(r.service_items)}</span>`,brAmount(r.materials_cents),brAmount(r.labor_cents),brAmount(r.cost_cents),E(r.handler_name)]);
 const controls=tabs.map(t=>brButton('customer-tab',t.label+' · '+brCustomerCount(customer[t.count]),`data-tab="${t.key}" aria-pressed="${tab===t.key}"`)).join('');
 return heading('客户信息 · '+customer.name,'查看该客户在当前授权范围内的关联业务。',brLink('records-customers','返回客户列表'))+`<section class="panel"><div class="panelhead"><h2>客户资料</h2></div><div class="panelbody">${brFacts([['客户姓名',customer.name],['联系电话',customer.phone],['所属人员',customer.owner_name],['所属门店',customer.store_name],['备注',customer.note]])}</div></section><section class="panel" id="br-customer-business"><div class="panelhead"><h2>关联业务</h2><div class="br-customer-tabs" role="group" aria-label="客户关联业务">${controls}</div></div>${table(headers,rows)}${brCustomerPager(data,tab)}</section>`;
}
async function brChangeCustomerView(action,button){
 const view=brState.customerView;if(!view||view.context!==brContext()||state.route!=='records-customers/'+view.id)throw new Error('请重新打开客户信息。');
 const tab=button.dataset.tab;if(!brCustomerTabs().some(t=>t.key===tab))throw new Error('当前岗位不可查看该业务。');
 if(action==='customer-tab'){if(view.tab===tab)return;view.tab=tab;}else{const page=Number(button.dataset.page);if(tab!==view.tab||!Number.isInteger(page)||page<1)return;view.pages[tab]=page;}
 await render();
 if(view===brState.customerView&&view.context===brContext())$('#br-customer-business [data-br="customer-tab"][data-tab="'+tab+'"]')?.focus();
}
async function brNewCustomer(){return brForm('填写客户信息',[{title:'客户资料',fields:[F('name','客户姓名'),F('phone','联系电话','text',false),F('note','备注','textarea',false)]}],{},(v,request_id)=>api(BR_API+'/customers',{method:'POST',body:{...v,request_id}}),{draftKey:'customer'});}
async function brAfterSales(){const d=await api(brPageURL('/after-sales'));const types=Object.fromEntries((state.recordCatalog.service_types||[]).map(s=>[s.value,s.label]));return heading('售后业务','维修、保养、事故维修、续保、延保及精品销售记录。',brCaps().create_after_sales?brButton('new-after-sales',brState.drafts.afterSales?'继续填写售后':'登记售后业务','','primary'):'')+storeNotice()+brListFilters()+`<section class="panel">${table(['业务日期','业务类型','客户 / 车辆','服务项目','材料费','工时费','核定成本','经办人'],d.items.map(r=>[E(r.business_date),E(types[r.service_type]||r.service_type),E(r.customer_name+' / '+r.vehicle),`<span class="wrap">${E(r.service_items)}</span>`,brAmount(r.materials_cents),brAmount(r.labor_cents),brAmount(r.cost_cents),E(r.handler_name)]))}${pager(d.total)}</section>`;}
async function brNewAfterSales(){const fields=[F('service_type','业务类型','select',true,state.recordCatalog.service_types),F('business_date','业务日期','date'),F('customer_name','客户姓名'),F('customer_phone','联系电话','text',false),F('vehicle','车辆信息'),F('brand','品牌','text',false),F('service_items','服务项目','textarea'),F('materials','材料费（元）','money_zero'),F('labor','工时费（元）','money_zero'),F('cost','核定成本（元）','money_zero',false),F('handler_name','经办人')];return brForm('登记售后业务',[{title:'业务记录',fields}],{handler_name:state.user.display_name},(v,request_id)=>{const {materials,labor,cost,...rest}=v;return api(BR_API+'/after-sales',{method:'POST',body:{...rest,request_id,materials_cents:moneyFen(materials,{allowZero:true}),labor_cents:moneyFen(labor,{allowZero:true}),cost_cents:cost===''?null:moneyFen(cost,{allowZero:true})}});},{draftKey:'afterSales',notice:'直接填写客户与车辆信息，保存时自动建立或关联客户档案。'});}
async function brSettings(){const epoch=renderId,r=await api(BR_API+'/settings');if(epoch!==renderId)return '';brState.settings=r;const modes={all:'全部合同审批',fixed:'单笔固定金额',ratio:'车价比例'};return heading('赠品审批设置','阈值用于核对提示，当前全部合同仍须管理审批。',brLink('records-sales','返回销售业务')+(brCaps().manage_settings?brButton('edit-settings','设置赠品阈值','','primary'):''))+panel('赠品审批规则',brFacts([['阈值方式',modes[r.approval_mode]],['固定金额',r.threshold_amount_cents==null?'未设置':brAmount(r.threshold_amount_cents)],['车价比例',r.threshold_basis_points==null?'未设置':(r.threshold_basis_points/100).toFixed(2)+'%'],['合同放行','内勤人工核价后，管理审批通过方可打印']]))+panel('标准价格',`<p>后续由内勤上传和维护标准价格。当前采用人工核价。</p><button type="button" disabled>标准价格上传 · 暂未开放</button>`);}
async function brEditSettings(){const r=brState.settings;return brForm('设置赠品阈值',[{title:'审批规则',fields:[F('approval_mode','阈值方式','select',true,[{value:'all',label:'全部合同审批'},{value:'fixed',label:'单笔固定金额'},{value:'ratio',label:'车价比例'}]),F('threshold_amount','固定金额（元）','money_zero',false),F('threshold_ratio','车价比例（%）','text',false)]}],{approval_mode:r.approval_mode,threshold_amount:brInputAmount(r.threshold_amount_cents),threshold_ratio:r.threshold_basis_points==null?'':(r.threshold_basis_points/100).toFixed(2)},(v,request_id)=>api(BR_API+'/settings',{method:'PUT',body:{request_id,version:r.version,approval_mode:v.approval_mode,threshold_amount_cents:v.approval_mode==='fixed'?moneyFen(v.threshold_amount,{allowZero:true}):null,threshold_basis_points:v.approval_mode==='ratio'?brPercentage(v.threshold_ratio):null}}),{draftKey:'settings-'+r.version,notice:'本次设置不免除任何合同的管理审批。'});}
// Reports and manual columns are supplied by the same server catalog that
// defines aggregation and export. Never infer a financial result from a chart.
function brReportDefinitions(){return state.recordCatalog?.reports||[];}
function brReportFilters(){const today=day();return brState.filters||(brState.filters={report:'profit',metric:'',date_from:today.slice(0,8)+'01',date_to:today,group_by:'salesperson',brand:'',salesperson_id:''});}
function brReportQuery(){const {metric,...filters}=brReportFilters();if(metric)filters.report+=':'+metric;return new URLSearchParams(Object.entries(filters).filter(([,v])=>v!==''));}
// Each pair refers to columns in one fixed server report definition. No target
// is inferred from a percentage or joined across records, dates or people.
const BR_PROGRESS_PAIRS={
 after_sales_monthly:[['c02','c03','c04']],
 after_sales_targets:[['c01','c05','c06'],['c02','c09','c10'],['c14','c12','c15'],['c03','c16','c17']],
 sales_overview:[['c02','c04','c05']],
 insurance_renewal:[['c06','c07','c08']],
 individual_profit:[['c03','c04','c05']]
};
function brProgressPair(report){
 const pair=(BR_PROGRESS_PAIRS[report.report]||[]).find(keys=>keys.includes(report.metric));
 if(!pair)return null;
 const columns=report.columns||[],target=columns.find(c=>c.key===pair[0]),actual=columns.find(c=>c.key===pair[1]);
 if(!target||!actual||target.type!==actual.type||target.unit!==actual.unit)return null;
 return {target,actual,rate:columns.find(c=>c.key===pair[2])};
}
function brPresentation(report){
 const definition=brReportDefinitions().find(r=>r.key===report.report),manual=definition?.source==='manual';
 const monthly=brReportFilters().group_by==='month',pair=manual?brProgressPair(report):null;
 const views=[{value:'auto',label:'自动展示'},{value:'rank',label:manual?'记录对比':monthly?'数值对比':'业绩排行'}];
 if(!manual&&monthly)views.push({value:'line',label:'月度趋势'});
 if(pair)views.push({value:'progress',label:'目标进度'});
 views.push({value:'table',label:'明细表'});
 const selected=views.some(v=>v.value===brState.view)?brState.view:'auto';
 return {definition,manual,pair,views,selected,type:selected==='auto'?(pair?'progress':!manual&&monthly?'line':'rank'):selected};
}
function brExactTotal(rows,precision){
 const scale=10n**BigInt(precision);let total=0n,unknown=0;
 for(const row of rows){
  if(row.value==null){unknown++;continue;}
  const match=/^(-?)(\d+)(?:\.(\d+))?$/.exec(String(row.value));
  if(!match||(match[3]||'').length>precision)return null;
  const amount=BigInt(match[2])*scale+BigInt((match[3]||'').padEnd(precision,'0')||'0');
  total+=match[1]?-amount:amount;
 }
 const negative=total<0n,absolute=negative?-total:total;
 return {value:(negative?'-':'')+String(absolute/scale).replace(/\B(?=(\d{3})+(?!\d))/g,',')+(precision?'.'+String(absolute%scale).padStart(precision,'0'):''),unknown};
}
function brReportSummary(report){
 const {manual}=brPresentation(report),rows=report.rows||[],precision=report.precision??2;
 const total=manual?null:brExactTotal(rows,precision),known=rows.filter(r=>r[report.metric]!=null).length;
 const label=manual?'已填指标记录':total?.unknown?'已核定部分合计':'当前范围合计';
 const value=manual?`${known} / ${rows.length}`:rows.length===0||total?.unknown===rows.length?'—':total?.value??'—';
 const note=manual?'逐条展示，不跨记录累加':total?.unknown?`${total.unknown} 条未核定，未计入合计`:report.metric_label||report.title;
 const filters=brReportFilters();
 return `<div class="br-summary" aria-label="当前报表摘要"><div class="br-summary-card"><span>${E(label)}</span><strong data-summary="total">${E(value)}${manual?'':`<small>${E(report.unit||'')}</small>`}</strong><p>${E(note)}</p></div><div class="br-summary-card"><span>来源记录</span><strong data-summary="records">${rows.length}<small>条</small></strong><p>与明细、导出范围一致</p></div><div class="br-summary-card br-summary-period"><span>统计范围</span><strong data-summary="coverage">${E(filters.date_from)} — ${E(filters.date_to)}</strong><p>${E(report.period_basis||'')}</p></div></div>`;
}
function brReportResult(report){
 const p=brPresentation(report),progress=p.type==='progress';
 const title=progress?`${report.title} · ${p.pair.actual.label}完成情况`:`${report.title}${report.metric_label&&report.metric_label!==report.title?' · '+report.metric_label:''}`;
 const unit=progress?p.pair.actual.unit:report.unit;
 const explanation=progress?'同一条填报记录内比较目标与实际；填报完成率保持原值。':p.type==='line'?'按统计月份展示；缺月或未核定值留空，不连接为连续业绩。':p.manual?'按每条人工记录对比，不代表人员累计业绩。':'按当前指标排序，相同数值并列；未核定项不参与排名。';
 return `<section class="panel br-chart-panel"><div class="panelhead br-report-head"><div><h2>${E(title)}</h2><p class="br-caption">${E(report.period_basis||'')} · 单位：${E(unit||'数值')}</p></div><span class="br-updated">${report.updated_at?'数据更新于 '+E(time(report.updated_at)):'尚无记录'}</span></div><div class="br-view-tools" role="group" aria-label="展示方式">${p.views.map(v=>`<button type="button" data-br="report-view" data-view="${v.value}" aria-pressed="${p.selected===v.value}">${E(v.label)}</button>`).join('')}</div>${p.type==='table'?`<div id="br-report-table" class="br-report-table">${brReportTable(report)}</div>`:`<div id="br-chart" class="br-chart" aria-label="${E(title)}"></div>`}<p class="br-caption br-chart-notice">${E(p.type==='table'?'与当前筛选一致的原始记录，可按合同号查看原单。':explanation)}</p></section>${p.type==='table'?'':`<details class="panel br-disclosure"><summary>查看来源明细 · ${number((report.rows||[]).length)} 条</summary>${brReportTable(report)}</details>`}`;
}
async function brDashboard(){
 const filters=brReportFilters(),definitions=brReportDefinitions();if(definitions.length&&!definitions.some(r=>(r.key||r.value)===filters.report))filters.report=definitions[0].key||definitions[0].value;
 const definition=definitions.find(r=>r.key===filters.report);if(definition&&!definition.metrics.some(m=>m.key===filters.metric))filters.metric=definition.default_metric||definition.metrics[0]?.key||'';
 const epoch=renderId,report=await api(BR_API+'/reports?'+brReportQuery());if(epoch!==renderId)return '';brState.report=report;
 const controls=`<form id="br-report-filter" class="br-filter br-report-filter"><label>报表<select name="report">${brOptions(definitions.map(r=>({value:r.key||r.value,label:r.title||r.label})),filters.report)}</select></label><label>指标<select name="metric">${brOptions((definition?.metrics||[]).map(m=>({value:m.key,label:m.label})),filters.metric)}</select></label><label>开始日期<input name="date_from" type="date" required value="${E(filters.date_from)}"></label><label>结束日期<input name="date_to" type="date" required value="${E(filters.date_to)}"></label><label>查看维度<select name="group_by">${brOptions([{value:'salesperson',label:'人员排名'},{value:'store',label:'门店排名'},{value:'brand',label:'品牌排名'},{value:'month',label:'月度趋势'}],filters.group_by)}</select></label><label>品牌<input name="brand" value="${E(filters.brand)}" placeholder="全部品牌"></label><label>销售<select name="salesperson_id"><option value="">权限内全部</option>${brOptions((state.recordCatalog.sales_people||[]).map(p=>({value:p.id,label:p.label})),filters.salesperson_id)}</select></label><button class="primary" type="submit">查看图表</button></form>`;
 return heading('经营看板','看排名、看趋势、看目标完成情况。',(brCaps().record_statistics?brLink('records-manual','填写统计数据'):'')+brButton('export-report','导出当前明细'))+controls+brReportSummary(report)+`<div id="br-report-result">${brReportResult(report)}</div>`;
}
function brReportTable(report){
 const columns=report.columns||[],source=brReportDefinitions().find(r=>r.key===report.report)?.source;
 return table(columns.map(c=>c.label+(c.unit?'（'+c.unit+'）':'')),(report.rows||[]).map(row=>columns.map(c=>{
  const value=row[c.key];if(value==null)return '—';
  if(c.key==='number'&&source==='contracts')return brLink('records-sales/'+row.id,value);
  return E(value);
 })));
}
async function brManualReports(){
 const d=await api(brPageURL('/manual-reports',{report_key:state.status}));const definitions=brReportDefinitions();
 const controls=`<form id="br-list-filter" class="br-filter"><label>统计报表<select name="status"><option value="">全部报表</option>${brOptions(definitions.filter(r=>r.source==='manual').map(r=>({value:r.key,label:r.title})),state.status)}</select></label><button type="submit" class="primary">查询</button></form>`;
 return heading('统计填报','按原报表项目录入人工核对数据。',brLink('records-dashboard','返回经营看板')+(brCaps().record_statistics?brButton('new-manual','填写统计数据','','primary'):''))+storeNotice()+controls+`<section class="panel">${table(['统计日期','报表','品牌','已填数据'],d.items.map(r=>{const spec=definitions.find(x=>x.key===r.report_key);return [E(r.period),E(spec?.title||r.report_key),E(r.brand||'—'),`<details><summary>查看填写内容</summary><div class="br-manual-values">${(spec?.columns||[]).filter(c=>r.values?.[c.key]!=null).map(c=>`${E(c.label)}：${E(r.values[c.key])}`).join('<br>')}</div></details>`];}))}${pager(d.total)}</section>`;
}
async function brNewManual(reportKey){
 const definitions=brReportDefinitions().filter(r=>r.source==='manual');
 if(!reportKey){modal('选择统计报表',`<p class="br-caption">选择原报表，再填写本次人工核对数据。空白表示未提供，不会按零补齐。</p><div class="br-report-picker">${definitions.map(r=>brButton('manual-report-select',r.title,`data-report="${E(r.key)}"`)).join('')}</div>`);return;}
 const spec=definitions.find(r=>r.key===reportKey);if(!spec)throw new Error('统计报表不存在，请刷新目录。');
 const fields=spec.columns.map(c=>F('value_'+c.key,c.label+(c.type==='money'?'（元）':c.type==='percent'?'（%）':''),c.type==='date'?'date':'text',false));
 const meta=[F('period','统计日期','date'),F('brand','所属品牌','text',false),F('salesperson_id','所属销售','select',false,(state.recordCatalog.sales_people||[]).map(p=>({value:p.id,label:p.label})))];
 return brForm(spec.title,[{title:'统计归属',fields:meta},{title:'人工填报数据',fields}],{},(v,request_id)=>api(BR_API+'/manual-reports',{method:'POST',body:{request_id,report_key:reportKey,period:v.period,brand:v.brand,salesperson_id:v.salesperson_id?Number(v.salesperson_id):null,values:Object.fromEntries(spec.columns.map(c=>[c.key,v['value_'+c.key]===''?null:v['value_'+c.key]]))}}),{draftKey:'manual-'+reportKey,notice:'金额按元填写，比例填写百分数（如 10 表示 10%）。系统保留人工填写的数据，不代算成本或利润。'});
}
function leaveBusinessRecordsChart(){const node=$('#br-chart');if(node){if(typeof Charts!=='undefined')Charts.dispose(node);if(typeof RecordsCharts!=='undefined')RecordsCharts.dispose(node);}}
function mountBusinessRecordsChart(){
 const chart=$('#br-chart'),report=brState.report;if(!chart||!report)return;
 const p=brPresentation(report),spec=p.definition?.metrics.find(m=>m.key===report.metric);
 let unit=spec?.unit||report.unit||'',precision=spec?.precision??report.precision??2,items=report.series||[];
 if(p.type==='progress'){
  unit=p.pair.actual.unit;precision=p.pair.actual.precision;
  const categories=(report.columns||[]).filter(c=>/^c\d+$/.test(c.key)&&c.type==='text').slice(0,2);
  items=(report.rows||[]).map(row=>({label:[row.store,row.salesperson,row.brand,...categories.map(c=>row[c.key]),row.period].filter(Boolean).join(' · ')+' · #'+row.id,period:row.period,
   actual:row[p.pair.actual.key]==null?null:Number(row[p.pair.actual.key]),actual_exact:row[p.pair.actual.key],
   target:row[p.pair.target.key]==null?null:Number(row[p.pair.target.key]),target_exact:row[p.pair.target.key],reported_rate:p.pair.rate?row[p.pair.rate.key]:null}));
 }
 RecordsCharts.render(chart,{type:p.type,title:report.title,unit,precision,items});
}
function mountBusinessRecords(){
 const f=$('#br-list-filter');if(f)f.onsubmit=event=>{event.preventDefault();const data=Object.fromEntries(new FormData(f));state.q=data.q||'';state.status=data.status||'';state.page=1;render();};
 const filter=$('#br-report-filter');if(filter)filter.elements.report.onchange=()=>{const spec=brReportDefinitions().find(r=>r.key===filter.elements.report.value);filter.elements.metric.innerHTML=brOptions((spec?.metrics||[]).map(m=>({value:m.key,label:m.label})),spec?.default_metric);};if(filter)filter.onsubmit=event=>{event.preventDefault();const next=Object.fromEntries(new FormData(filter));if(next.date_from>next.date_to){toast('开始日期不能晚于结束日期。',true);return;}brState.filters=next;render();};
 mountBusinessRecordsChart();
}
document.addEventListener('click',event=>{
 const button=event.target.closest('[data-br=report-view]');if(!button||button.disabled||state.storeSwitch||!brState.report)return;
 const result=$('#br-report-result');if(!result)return;
 leaveBusinessRecordsChart();brState.view=button.dataset.view;
 result.innerHTML=brReportResult(brState.report);mountBusinessRecordsChart();
 result.querySelector(`[data-view="${brState.view}"]`)?.focus();
});
document.addEventListener('click',async event=>{
 const el=event.target.closest('[data-br]');if(!el||el.dataset.br==='report-view'||el.disabled||state.storeSwitch)return;
 el.disabled=true;try{const action=el.dataset.br;if(action==='defer-form'){if($('#modal form')?.dataset.submitting==='true')throw new Error('正在提交，请等待本次返回结果。');closeModal();}else if(action==='new-contract')await brNewContract();else if(action==='contract-action')await brContractAction(el.dataset.action);else if(action==='new-customer')await brNewCustomer();else if(action==='customer-tab'||action==='customer-page')await brChangeCustomerView(action,el);else if(action==='new-after-sales')await brNewAfterSales();else if(action==='edit-settings')await brEditSettings();else if(action==='new-manual')await brNewManual();else if(action==='manual-report-select')await brNewManual(el.dataset.report);else if(action==='export-report')await download(BR_API+'/reports/export?'+brReportQuery(),'经营报表.csv');}catch(error){toast(error.message,true);}finally{if(el.isConnected)el.disabled=false;}
});
window.addEventListener('beforeunload',event=>{if(Object.keys(brState.drafts).length){event.preventDefault();event.returnValue='';}});

document.addEventListener('click',event=>{if(!event.target.closest('[data-wfx-discard]'))return;const key=$('#modal form')?.dataset.brForm;if(key)delete brState.drafts[key];},true);
