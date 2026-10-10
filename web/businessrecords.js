'use strict';
// V2 records are independent from the historical inventory/accounting workflows.
// Capabilities and available actions come from the server; every mutation still
// rechecks identity, store, version and idempotency in its own transaction.
const BR_API='/api/business-records';
const BR_STATUS={submitted:'待销售经理审批',manager_approved:'待总经理审批',deputy_pending:'待集团副总经理审批',priced:'历史合同待审批',approved:'合同审批通过',rejected:'合同退回修改'};
const BR_OFFICE_STATUS={not_started:'待销售内勤填报',draft:'销售内勤核对中',submitted:'待总经理审核资料',approved:'资料已审批',rejected:'资料退回修改'};
let brState={drafts:{},report:null,detail:null,settings:null,filters:null,view:'auto',customerView:null,manualHistory:false,manualContract:null};
function clearBusinessRecords(){brState={drafts:{},report:null,detail:null,settings:null,filters:null,view:'auto',customerView:null,manualHistory:false,manualContract:null};state.recordCatalog=null;}
function brCaps(){return state.recordCatalog?.capabilities||{};}
function brInternalRead(){return ['admin','clerk','chairman'].includes(state.user?.role);}
function brButton(action,label,extra='',cls=''){return `<button type="button" data-br="${E(action)}" ${extra} class="${E(cls)}">${E(label)}</button>`;}
function brLink(route,label){return `<a class="button" href="#${E(route)}">${E(label)}</a>`;}
function brAmount(value){return value==null?'未填写':money(value)+' 元';}
function brInputAmount(value){return value==null?'':(value/100).toFixed(2);}
function brSignedAmount(value,label){const text=moneyDigits(value);return text.startsWith('-')?-moneyFen(text.slice(1),{label,allowZero:true}):moneyFen(text,{label,allowZero:true});}
function brPercentage(value){if(String(value).trim()==='')return null;const result=moneyFen(value,{label:'车价比例',allowZero:true});if(result>10000)throw new Error('车价比例不能超过 100%。');return result;}
function brOptions(items,value){return items.map(item=>{const key=item.value??item.key;return `<option value="${E(key)}" ${String(key)===String(value)?'selected':''}>${E(item.label)}</option>`;}).join('');}
function brFacts(entries){return `<dl class="br-facts">${entries.map(([label,value])=>`<div><dt>${E(label)}</dt><dd>${E(value==null||value===''?'—':value)}</dd></div>`).join('')}</dl>`;}
function brContext(){return `${state.user?.id||''}:${state.store||''}:${storeContextVersion}`;}
function businessRecordsShell(){
 const u=state.user,caps=brCaps();
 const financeAllowed=caps.confirm_receipt||caps.price||caps.approve||['admin','manager','general_manager','chairman','auditor'].includes(u.role);
 const links=[['records-dashboard','可视化看板','▥'],['records-sales','销售业务','▤'],['records-after-sales','售后业务','◇'],...(financeAllowed?[['records-finance','财务流水','¥']]:[]),['records-customers','客户信息','▧']];
 const navHTML=links.map(([route,label,icon])=>route==='records-dashboard'?`<div class="br-dashboard-nav"><a class="navlink ${state.route.startsWith(route)?'active':''}" href="#records-dashboard"><span class="navicon">${icon}</span>${label}</a><div class="br-dashboard-subnav" aria-label="看板分类">${[['records-dashboard','每日报表'],['records-dashboard/range','自定义范围数据'],['records-dashboard/monthly','月报统计']].map(([href,name])=>`<a href="#${href}" class="${state.route===href||(href==='records-dashboard'&&state.route==='records-dashboard/daily')?'active':''}">${name}</a>`).join('')}</div></div>`:`<a class="navlink ${state.route===route||state.route.startsWith(route+'/')?'active':''}" href="#${route}"${state.route===route?' aria-current="page"':''}><span class="navicon">${icon}</span>${label}</a>`).join('');
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
 if(type==='records-dashboard')return id==='targets'?brMonthlyTargets():brDashboard(id==='range'?'range':id==='monthly'?'monthly':'daily');
 if(type==='records-sales')return id==='daily'?brDailyVehicles():id?brContract(Number(id)):brContracts(false);
 if(type==='records-finance')return brContracts(true);
 if(type==='records-after-sales')return brAfterSales();
 if(type==='records-customers')return id?brCustomer(Number(id)):brCustomers();
 if(type==='records-manual')return brManualReports();
 if(type==='records-settings')return brSettings();
 throw new Error('记录页面不存在。');
}
async function brContracts(finance){
 const d=await api(brPageURL('/contracts',{status:finance?'approved':state.status,office_status:brState.officeFilter||''}));
 const headers=['合同号','客户 / 车辆','所属销售','合同审批','销售内勤资料','应到账','实到账','操作'];
 const rows=d.items.map(r=>[E(r.number),`<strong>${E(r.customer_name)}</strong><div class="muted">${E([r.brand,r.model].filter(Boolean).join(' '))}</div>`,E(r.salesperson_name),pill(r.status,r.status_label||BR_STATUS[r.status]),E(BR_OFFICE_STATUS[r.office_status]||'历史记录'),brAmount(r.expected_amount_cents),r.actual_amount_cents==null?'未确认':brAmount(r.actual_amount_cents),brLink('records-sales/'+r.id,finance?'查看 / 上传发票':'打开办理')]);
 const tools=(!finance&&(brCaps().price||brCaps().approve)?brLink('records-sales/daily','今日车辆更新'):'')+(!finance&&brCaps().record_statistics?brLink('records-manual','销售内勤日常表格'):'')+(!finance&&(brCaps().manage_settings||brCaps().price)?brLink('records-settings','价格与审批设置'):'')+(!finance&&brCaps().create_sales?brButton('new-contract',brState.drafts.contract?'继续填写合同':'预填销售合同','','primary'):'');
 const officeFilter=!finance?`<div class="br-work-tabs" role="group" aria-label="销售内勤资料筛选">${[['','全部资料'],['not_started','待销售内勤填报'],['draft','核对中'],['submitted','待资料审批'],['rejected','资料已退回'],['approved','资料已通过']].map(([key,label])=>brButton('office-filter',label,`data-status="${key}" aria-pressed="${(brState.officeFilter||'')===key}"`)).join('')}</div>`:'';
 return heading(finance?'财务流水':'销售业务',finance?'在对应车辆中上传发票并核对识别结果。发票与实际到账分别留存。':'销售顾问填单 → 销售经理 → 总经理；超限价或超赠送时再由集团副总经理审批，通过后打印。销售内勤随后核价并补齐资料，再交总经理审核。',tools)+storeNotice()+brListFilters(!finance)+officeFilter+`<section class="panel">${table(headers,rows)}${pager(d.total)}</section>`;
}
async function brContract(id){
 const epoch=renderId,r=await api(BR_API+'/contracts/'+id);if(epoch!==renderId)return '';brState.detail=r;
 const actionLabels={edit:'修改合同',price_review:'历史合同销售内勤核价',manager_approve:'销售经理审批通过',approve:'总经理审批通过',deputy_approve:'集团副总经理审批通过',reject:'退回合同',receipt:'确认合同到账',print:'下载 / 打印合同',office_edit:'填写 / 核对销售内勤资料',office_submit:'提交资料审批',office_approve:'资料审批通过',office_reject:'退回销售内勤资料'};
 const actionHTML=action=>brButton('contract-action',actionLabels[action]||action,`data-action="${E(action)}"`,['manager_approve','approve','print','office_edit','office_approve','office_submit'].includes(action)?'primary':'');
 const actions=(r.actions||[]).filter(action=>action in actionLabels&&!action.startsWith('office_')).map(actionHTML).join('');
 const officeActions=(r.actions||[]).filter(action=>action.startsWith('office_')).map(actionHTML).join('');
 const stage=r.status==='approved'?4:r.status==='deputy_pending'?3:r.status==='manager_approved'?2:1;
 const needsDeputy=r.approval_limits?.requires_deputy;
 const progress=r.workflow_version==='legacy-v2'?'<div class="notice">历史合同保留原审批记录。</div>':`<div class="br-steps"><span class="complete">销售顾问填单</span><span class="${stage>=2?'complete':''}">销售经理审批</span><span class="${stage>=3?'complete':''}">总经理审批</span>${needsDeputy?`<span class="${stage>=4?'complete':''}">集团副总经理审批</span>`:''}<span class="${r.status==='approved'?'complete':''}">合同审批通过后打印</span><span class="${['submitted','approved'].includes(r.office_status)?'complete':''}">销售内勤核价与资料</span><span class="${r.office_status==='approved'?'complete':''}">总经理审核资料</span></div>`;
 const form=r.form_data||{},customerLink=r.customer_id?brLink('records-customers/'+r.customer_id,'查看客户档案'):'';
 const invoice=typeof brInvoiceSection==='function'?await brInvoiceSection(r):'';if(epoch!==renderId)return '';
 return heading('销售合同 '+r.number,[r.customer_name,r.brand,r.model].filter(Boolean).join(' · '),customerLink+brLink('records-sales','返回销售业务'))+progress+`<section class="panel"><div class="panelhead spread"><h2>${E(r.status_label||BR_STATUS[r.status]||r.status)}</h2><div class="row">${actions}</div></div><div class="panelbody">${r.status==='rejected'?'<p class="notice warn">合同已退回，请根据核对记录修改后重新提交。</p>':r.status==='approved'?'<p class="br-caption">已审批合同锁定。需要调整合同内容时，请重新预填一份合同并走审批流程。</p>':''}${brFacts([['合同号',r.number],['合同日期',r.contract_date],['所属门店',r.store_name],['所属销售',r.salesperson_name],['客户姓名',r.customer_name],['联系电话',r.customer_phone],['品牌',r.brand],['车型',r.model],['车辆识别号 VIN',r.vin],['销售金额',brAmount(r.sale_price_cents)],['应到账金额',brAmount(r.expected_amount_cents)],['实到账金额',r.actual_amount_cents==null?'未确认':brAmount(r.actual_amount_cents)],['实际到账日期',r.received_on],['合同审批说明',r.approval_note],['到账核对说明',r.receipt?.note]])}<div class="br-note"><strong>赠品与附加约定</strong><p>${E(r.gift_description||'未填写')}</p></div></div></section><details class="panel br-disclosure"><summary>合同填单内容</summary>${brFacts(brContractExtraFields().map(f=>[f.label,form[f.key]]))}</details>${brApprovalLimits(r)}${brOfficeSection(r,officeActions)}${invoice}${Array.isArray(r.events)&&r.events.length?`<details class="panel br-disclosure"><summary>核对与操作记录</summary>${table(['时间','操作人','操作','说明'],r.events.map(e=>[time(e.created_at),E(e.actor_name),E(actionLabels[e.action]||e.action),E(e.note||'—')]))}</details>`:''}<p class="br-caption">合同审批和销售内勤资料审批分别留痕。合同打印后线下签字；资料审批通过后进入逐车报表，销售内勤更新后按月份自动统计。</p>`;
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
 },{draftKey:r?'contract-'+r.id:'contract',submit:'提交销售经理审批',notice:'按合同模板预填客户、车辆、付款及附加约定，不在这里填写保险等延伸业务资料。销售经理、总经理依次审批，超限价或超赠送时还需集团副总经理审批，通过后方可打印。',nextRoute:result=>'records-sales/'+result.id});
 const quantity=dialog.querySelector('[name=quantity]');quantity.readOnly=true;
}
async function brContractAction(action){
 const r=brState.detail;if(!r||(r.actions||[]).includes(action)===false)throw new Error('当前合同不能执行此操作，请刷新核对。');
 if(action==='edit')return brNewContract(true);
 if(action==='print')return download(BR_API+'/contracts/'+r.id+'/print',r.number+'.pdf');
 if(action==='office_edit')return brOfficeEdit();
 let fields,title,path=action,values={},notice='';
 if(action==='price_review'){title='销售内勤核价';path='price-review';fields=[F('expected_amount','应到账金额（元）','money_zero'),F('cost','此车销售总成本（元）','money_zero'),F('profit','此车销售利润（元）'),F('gift_cost','赠品成本（元）','money_zero'),F('note','核价说明','textarea',false)];values={expected_amount:brInputAmount(r.expected_amount_cents??r.sale_price_cents),cost:brInputAmount(r.cost_cents),profit:brInputAmount(r.profit_cents),gift_cost:brInputAmount(r.gift_cost_cents)};notice='逐项填写已核对的销售结果。核价通过后仍需管理审批，才可打印。';}
 else if(action==='receipt'){title='确认合同到账';fields=[F('actual_amount','人工核实的实际到账金额（元）','money'),F('received_on','实际到账日期','date'),F('note','核对说明','textarea',false)];notice='请先按合同号线下核对。每份合同仅确认一次汇总到账金额，业绩按所填实际到账日期统计。';}
 else if(action==='manager_approve'){values={minimum_sale_price:'',gift_limit:'',offered_gift_value:''};title='销售经理审批通过';path='manager-approve';fields=[...(r.workflow_version==='trial-v30'?[F('minimum_sale_price','本车最低成交限价（元）','money_zero'),F('gift_limit','本车赠送额度上限（元）','money_zero'),F('offered_gift_value','本单赠送金额（元）','money_zero'),F('approval_basis','限价及赠送额度依据','textarea')]:[]),F('note','审批说明','textarea',false)];notice=`核对合同 ${r.number} 的客户、车辆、金额和赠品约定。按实际政策填写限价和额度，赠送金额使用销售口径，不是赠品成本；零表示确实为零。低于限价或超过赠送额度时，总经理批准后还须集团副总经理审批。`;}
 else if(action==='approve'){title='总经理审批通过';fields=[F('note','审批说明','textarea',false)];notice=`确认合同 ${r.number}。${r.approval_limits?.requires_deputy?'本单超出限价或赠送额度，将继续交集团副总经理审批，通过后才能打印。':'通过后可打印合同。'}销售内勤资料另行审核，审批不代表客户已签字或款项已到账。`;}
 else if(action==='deputy_approve'){title='集团副总经理审批通过';path='deputy-approve';fields=[F('note','审批说明','textarea',false)];notice=`请核对合同 ${r.number} 的超限项目及额度依据。通过后才可打印合同，审批不代表客户已签字或款项已到账。`;}
 else if(action==='reject'){title='退回修改';fields=[F('note','退回原因','textarea')];}
 else if(action==='office_submit'){title='提交销售内勤资料审批';path='office-submit';fields=[F('note','提交说明','textarea',false)];notice='请先核对本车全部已填资料。未知数据保留空白，提交后由总经理审核。';}
 else if(action==='office_approve'){title='销售内勤资料审批通过';path='office-approve';fields=[F('note','审批说明','textarea',false)];notice='审批通过后生成逐车报表数据；月度看板按最新已核实数据统计。';}
 else if(action==='office_reject'){title='退回销售内勤资料';path='office-reject';fields=[F('note','退回原因','textarea')];}
 else throw new Error('不支持的合同操作。');
 await brForm(title,[{title:r.number,fields}],values,(v,request_id)=>{
  const body={request_id,version:r.version,note:v.note};
  if(action==='price_review')Object.assign(body,{expected_amount_cents:moneyFen(v.expected_amount,{allowZero:true}),cost_cents:moneyFen(v.cost,{allowZero:true}),profit_cents:brSignedAmount(v.profit,'此车销售利润'),gift_cost_cents:moneyFen(v.gift_cost,{allowZero:true})});
  if(action==='receipt')Object.assign(body,{actual_amount_cents:moneyFen(v.actual_amount),received_on:v.received_on});
  if(action==='manager_approve'&&r.workflow_version==='trial-v30')Object.assign(body,{minimum_sale_price_cents:moneyFen(v.minimum_sale_price,{allowZero:true}),gift_limit_cents:moneyFen(v.gift_limit,{allowZero:true}),offered_gift_value_cents:moneyFen(v.offered_gift_value,{allowZero:true}),approval_basis:v.approval_basis});
  return api(BR_API+'/contracts/'+r.id+'/'+path,{method:'POST',body});
 },{draftKey:`${action}-${r.id}-${r.version}`,submit:title,notice});
}
function brOfficeSection(r,actions){
 if(!r.office_status&&!r.office_data)return '';
 const data=r.office_data||{},approved=r.office_approved_data||{},spec=brReportDefinitions().find(s=>s.key===data.report_key),columns=data.columns||spec?.columns||[];
 const filled=columns.filter(c=>data.values?.[c.key]!=null&&data.values[c.key]!=='');
 const amountKeys=[['应到账金额','expected_amount_cents'],['此车销售总成本','cost_cents'],['此车销售利润','profit_cents'],['赠品成本','gift_cost_cents']];
 const facts=[['资料状态',BR_OFFICE_STATUS[r.office_status]||r.office_status],['资料表',data.report_title||spec?.title||'尚未选择'],['统计日期',data.period],...('note' in data?[['核对说明',data.note]]:[]),...amountKeys.filter(([,key])=>key in data).map(([label,key])=>[label,brAmount(data[key])])];
 const reviewNote=r.office_status==='draft'?'已保存，尚未提交资料审批。':r.office_status==='submitted'?'以下为本次提交的资料，审批通过后进入逐车报表。':r.office_status==='approved'?'以下资料已审批，报表按对应统计日期读取。':r.office_status==='rejected'?'资料已退回，修改后需重新提交。':'尚未填写核价及附带资料。';
 return `<section class="panel br-office-panel"><div class="panelhead spread"><div><h2>销售内勤核价与附带信息</h2><p class="br-caption">${E(reviewNote)}</p></div><div class="row">${actions}</div></div><div class="panelbody">${brFacts(facts)}${data.sensitive_fields_hidden?'<p class="notice">按当前岗位权限显示业务资料；成本、利润、返佣及核价备注不在本页展示。敏感项目由有权限的销售内勤、董事长或维护管理员核对。</p>':''}${filled.length?`<h3>已填写原表明细 · ${filled.length} 项</h3>${table(['原表项目','当前填写值'],filled.map(c=>[E(c.label+(c.unit?'（'+c.unit+'）':'')),E(data.values[c.key])]))}`:'<p class="br-caption">暂无已填写且当前岗位可见的原表明细。</p>'}${columns.length>filled.length?`<details class="br-disclosure"><summary>查看尚未填写的原表项目 · ${columns.length-filled.length} 项</summary>${table(['原表项目','当前填写值'],columns.filter(c=>!filled.includes(c)).map(c=>[E(c.label+(c.unit?'（'+c.unit+'）':'')),'未填写']))}</details>`:''}${approved.report_key&&r.office_status!=='approved'?'<p class="notice">当前资料正在修订。已通过的上一版保留，待本次审批后更新报表。</p>':''}</div></section>`;
}
function brApprovalLimits(r){
 const limits=r.approval_limits;if(!limits)return '';
 const reasons=[limits.price_exceeded?'成交价低于限价':'',limits.gift_exceeded?'赠送金额超出额度':''].filter(Boolean);
 return `<section class="panel"><div class="panelhead"><h2>合同限价与赠送额度</h2></div><div class="panelbody">${brFacts([['本车最低成交限价',brAmount(limits.minimum_sale_price_cents)],['本车赠送额度上限',brAmount(limits.gift_limit_cents)],['本单赠送金额',brAmount(limits.offered_gift_value_cents)],['限价及赠送额度依据',limits.approval_basis],['审批要求',reasons.length?reasons.join('；')+'，须集团副总经理审批':'未超出已核对额度，按销售经理、总经理流程审批']])}<p class="br-caption">赠送金额使用销售口径，与销售内勤填写的赠品成本分别记录。</p></div></section>`;
}
function brOfficeGroups(columns){
 const groups=[['车辆与客户',[]],['金融与分期',[]],['保险与延保',[]],['精品、赠品与服务',[]],['成本、毛利与其他资料',[]]];
 for(const c of columns){const i=/保险|承保|商业险|新保|全损|车小安|延保/.test(c.label)?2:/贷款|金融|放款|贴息|分期|银行|客户返佣/.test(c.label)?1:/精品|赠送|贴膜|选装|上牌|服务费/.test(c.label)?3:/序号|台数|车系|车型|车辆型号|车架号|销售顾问|开票日期|颜色|内饰|客户名称|客户电话|地址|订单类型|现金或三方/.test(c.label)?0:4;groups[i][1].push(F('value_'+c.key,c.label+(c.unit?'（'+c.unit+'）':''),c.type==='date'?'date':'text',false));}
 return groups.filter(([,fields])=>fields.length).map(([title,fields])=>({title,fields}));
}
async function brOfficeEdit(reportKey){
 const r=brState.detail;if(!r?.actions?.includes('office_edit'))throw new Error('当前合同不能填写销售内勤资料。');
 const existing=r.office_data||{},definitions=brReportDefinitions().filter(s=>s.supports_contract);
 const key=existing.report_key||reportKey;
 if(!key){modal('选择本车明细表',`<p class="br-caption">按车辆实际类型选择一张原表，后续核对和修订沿用这张表。</p><div class="br-report-picker">${definitions.map(s=>brButton('office-report-select',s.title,`data-report="${E(s.key)}"`)).join('')}</div>`);return;}
 const spec=definitions.find(s=>s.key===key);if(!spec)throw new Error('没有可填写的车辆明细表。');
 const context=brContext(),prefill=await api(BR_API+'/report-prefill?'+new URLSearchParams({report_key:key,contract_id:r.id}));if(context!==brContext())return;
 const priorAmount=field=>Object.hasOwn(existing,field)?existing[field]:r[field];
 const initial={period:existing.period||prefill.period||r.contract_date,note:existing.note||'',expected_amount:brInputAmount(Object.hasOwn(existing,'expected_amount_cents')?existing.expected_amount_cents:(r.expected_amount_cents??r.sale_price_cents)),cost:brInputAmount(priorAmount('cost_cents')),profit:brInputAmount(priorAmount('profit_cents')),gift_cost:brInputAmount(priorAmount('gift_cost_cents')),...Object.fromEntries(Object.entries({...prefill.values,...existing.values}).map(([k,v])=>['value_'+k,v??'']))};
 const meta=[F('period','逐车统计日期','date'),F('expected_amount','应到账金额（元）','money_zero',false),F('cost','此车销售总成本（元）','money_zero',false),F('profit','此车销售利润（元）','text',false),F('gift_cost','赠品成本（元）','money_zero',false),F('note','核对说明 / 待补内容','textarea',false)];
 const dialog=await brForm('销售内勤核对 · '+spec.title,[{title:'此车销售结果',fields:meta},...brOfficeGroups(spec.columns)],initial,(v,request_id)=>api(BR_API+'/contracts/'+r.id+'/office-review',{method:'PUT',body:{request_id,version:r.version,report_key:key,period:v.period,note:v.note,expected_amount_cents:v.expected_amount===''?null:moneyFen(v.expected_amount,{allowZero:true}),cost_cents:v.cost===''?null:moneyFen(v.cost,{allowZero:true}),profit_cents:v.profit===''?null:brSignedAmount(v.profit,'此车销售利润'),gift_cost_cents:v.gift_cost===''?null:moneyFen(v.gift_cost,{allowZero:true}),values:Object.fromEntries(spec.columns.map(c=>[c.key,v['value_'+c.key]===''?null:v['value_'+c.key]]))}}),{draftKey:`office-${r.id}-${key}-${r.version}`,submit:'保存销售内勤资料',notice:'总成本和利润请填写已核对的结果，下方明细不会自动计算这两个金额。利润、赠品成本会同步到原表对应项目，不重复计入。未知留空，零只表示确实为零。金额单位为元，比例 10 表示 10%。保存后还需提交总经理审核。'});
 const form=$('form',dialog),editable=['精品成本（赠送）','单车利润','核定单车利润','单车利润2','单车利润22'];
 for(const key of prefill.locked_fields||[]){const col=spec.columns.find(c=>c.key===key),input=form.elements['value_'+key];if(input&&!editable.includes(col?.label)){input.readOnly=true;input.closest('label').classList.add('br-field-locked');}}
 const finalProfit={vehicle_details:'核定单车利润',hail_vehicle_details:'单车利润22',secondary_vehicle_details:'单车利润',vehicle_details_sheet2:'单车利润'}[key];
 for(const [name,label] of [['profit',finalProfit],['gift_cost','精品成本（赠送）']]){const column=spec.columns.find(c=>c.label===label),target=column&&form.elements['value_'+column.key],source=form.elements[name];if(!target)continue;if(!Object.hasOwn(existing,name+'_cents')&&source.value===''&&target.value!=='')source.value=target.value;target.value=source.value;target.readOnly=true;target.closest('label').classList.add('br-office-mirrored');const hint=document.createElement('small');hint.className='fieldhelp';hint.textContent=name==='profit'?'与上方此车销售利润一致；请在上方修改。':'与上方赠品成本一致；请在上方修改。';target.closest('label').append(hint);source.addEventListener('input',()=>{target.value=source.value;form.dispatchEvent(new Event('input',{bubbles:true}));});}
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
 const headers=tab==='contracts'?['合同号','合同日期','车辆','所属销售','状态','销售金额','应到账','实到账']:['业务日期','业务类型','车辆','服务项目','材料费','工时费',...(brInternalRead()?['此车销售总成本']:[]),'经办人'];
 const rows=tab==='contracts'?data.items.map(r=>[`<a class="br-record-link" href="#records-sales/${E(r.id)}">${E(r.number)}</a>`,E(r.contract_date),E([r.brand,r.model].filter(Boolean).join(' ')),E(r.salesperson_name),pill(r.status,r.status_label||BR_STATUS[r.status]),brAmount(r.sale_price_cents),brAmount(r.expected_amount_cents),r.actual_amount_cents==null?'未确认':brAmount(r.actual_amount_cents)]):data.items.map(r=>[E(r.business_date),E(types[r.service_type]||r.service_type),E(r.vehicle),`<span class="wrap">${E(r.service_items)}</span>`,brAmount(r.materials_cents),brAmount(r.labor_cents),...(brInternalRead()?[brAmount(r.cost_cents)]:[]),E(r.handler_name)]);
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
async function brAfterSales(){const d=await api(brPageURL('/after-sales'));const types=Object.fromEntries((state.recordCatalog.service_types||[]).map(s=>[s.value,s.label]));return heading('售后业务','维修、保养、事故维修、续保、延保及精品销售记录。',brCaps().create_after_sales?brButton('new-after-sales',brState.drafts.afterSales?'继续填写售后':'登记售后业务','','primary'):'')+storeNotice()+brListFilters()+`<section class="panel">${table(['业务日期','业务类型','客户 / 车辆','服务项目','材料费','工时费',...(brInternalRead()?['此车销售总成本']:[]),'经办人'],d.items.map(r=>[E(r.business_date),E(types[r.service_type]||r.service_type),E(r.customer_name+' / '+r.vehicle),`<span class="wrap">${E(r.service_items)}</span>`,brAmount(r.materials_cents),brAmount(r.labor_cents),...(brInternalRead()?[brAmount(r.cost_cents)]:[]),E(r.handler_name)]))}${pager(d.total)}</section>`;}
async function brNewAfterSales(){const fields=[F('service_type','业务类型','select',true,state.recordCatalog.service_types),F('business_date','业务日期','date'),F('customer_name','客户姓名'),F('customer_phone','联系电话','text',false),F('vehicle','车辆信息'),F('brand','品牌','text',false),F('service_items','服务项目','textarea'),F('materials','材料费（元）','money_zero'),F('labor','工时费（元）','money_zero'),...(brInternalRead()?[F('cost','此车销售总成本（元）','money_zero',false)]:[]),F('handler_name','经办人')];return brForm('登记售后业务',[{title:'业务记录',fields}],{handler_name:state.user.display_name},(v,request_id)=>{const {materials,labor,cost,...rest}=v;return api(BR_API+'/after-sales',{method:'POST',body:{...rest,request_id,materials_cents:moneyFen(materials,{allowZero:true}),labor_cents:moneyFen(labor,{allowZero:true}),cost_cents:cost==null||cost===''?null:moneyFen(cost,{allowZero:true})}});},{draftKey:'afterSales',notice:'直接填写客户与车辆信息，保存时自动建立或关联客户档案。'});}
async function brSettings(){
 const internal=brInternalRead(),epoch=renderId,[r,prices]=await Promise.all([api(BR_API+'/settings'),internal?api(BR_API+'/standard-prices?'+new URLSearchParams({q:brState.priceQuery||'',page:brState.pricePage||1,page_size:50})):Promise.resolve(null)]);if(epoch!==renderId)return '';brState.settings=r;brState.prices=prices;
 const modes={all:'全部合同审批',fixed:'单笔固定金额',ratio:'车价比例'};
 return heading('价格与审批设置','标准价格由销售内勤维护，作为核价参考；未知价格仍需人工核实。参考阈值不跳过销售经理和总经理审批。',brLink('records-sales','返回销售业务')+(brCaps().manage_settings?brButton('edit-settings','设置赠品参考阈值'):''))+
 panel('审批规则',brFacts([['阈值方式',modes[r.approval_mode]],['固定金额',r.threshold_amount_cents==null?'未设置':brAmount(r.threshold_amount_cents)],['车价比例',r.threshold_basis_points==null?'未设置':(r.threshold_basis_points/100).toFixed(2)+'%'],['合同放行','销售经理和总经理依次审批后方可打印'],['销售内勤资料','核价及附带信息另交总经理审核']]))+
 (prices?`<section class="panel"><div class="panelhead spread"><h2>本店标准物品价格</h2><div class="row">${brCaps().price?brButton('new-price','录入物品')+brButton('import-prices','上传 / 粘贴价格表')+brButton('estimate-prices','参考计算'):''}</div></div><form id="br-price-filter" class="br-filter"><label>物品名称<input name="q" type="search" value="${E(brState.priceQuery||'')}" placeholder="查找物品"></label><button type="submit">查询</button></form>${table(['物品','标准售价','内部成本','备注'],prices.items.map(p=>[E(p.name),brAmount(p.sale_price_cents),brAmount(p.cost_cents),E(p.note)]))}<div class="pagination"><span>共 ${number(prices.total)} 项 · 第 ${prices.page} 页</span><div class="row">${brButton('price-page','上一页',`data-page="${prices.page-1}" ${prices.page<=1?'disabled':''}`)}${brButton('price-page','下一页',`data-page="${prices.page+1}" ${prices.page*prices.page_size>=prices.total?'disabled':''}`)}</div></div></section>`:'');
}
async function brPriceVersions(q=''){
 const items=[];let page=1,total=0;do{const result=await api(BR_API+'/standard-prices?'+new URLSearchParams({q,page,page_size:500}));items.push(...result.items);total=result.total;page++;}while(items.length<total);return new Map(items.map(item=>[item.name,item.version]));
}
async function brNewPrice(){return brForm('录入标准物品价格',[{title:'标准参考价格',fields:[F('name','物品名称'),F('sale_price','标准售价（元）','money_zero',false),F('cost','内部成本（元）','money_zero',false),F('note','备注','textarea',false)]}],{},async(v,request_id)=>{
 const known=await brPriceVersions(v.name);if(known.has(v.name))throw new Error('已有同名物品，请使用“上传 / 粘贴价格表”，核对现有版本后更新。');
 return api(BR_API+'/standard-prices/import',{method:'POST',body:{request_id,rows:[{name:v.name,sale_price_cents:v.sale_price===''?null:moneyFen(v.sale_price,{allowZero:true}),cost_cents:v.cost===''?null:moneyFen(v.cost,{allowZero:true}),note:v.note}]}});
 },{draftKey:'standard-price',notice:'录入本店新的标准物品。已有同名物品请从价格表核对更新；已经核定的合同金额不随价格更新。'});}
function brParsePriceTable(text){
 text=String(text).replace(/^\uFEFF/,'');const separator=text.includes('\t')?'\t':',';let rows=[],row=[],cell='',quoted=false;
 for(let i=0;i<text.length;i++){const ch=text[i];if(ch==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}else if(!quoted&&(ch===separator||ch==='\n'||ch==='\r')){row.push(cell.trim());cell='';if(ch!==separator){if(ch==='\r'&&text[i+1]==='\n')i++;if(row.some(Boolean))rows.push(row);row=[];}}else cell+=ch;}
 if(quoted)throw new Error('表格中有未闭合的引号，请检查文件。');row.push(cell.trim());if(row.some(Boolean))rows.push(row);
 if(!rows.length)throw new Error('请先上传或粘贴价格表。');
 if(rows[0][0]==='物品名称')rows.shift();if(!rows.length||rows.length>500)throw new Error('一次请填写 1 至 500 个物品。');
 const names=new Set();return rows.map((r,i)=>{if(!r[0]||r.length<3||r.length>4)throw new Error('第 '+(i+1)+' 行应为物品名称、标准售价、内部成本、备注四列。');if(names.has(r[0]))throw new Error('物品名称重复：'+r[0]);names.add(r[0]);return {name:r[0],sale_price_cents:r[1]===''?null:moneyFen(r[1],{allowZero:true,label:r[0]+'标准售价'}),cost_cents:r[2]===''?null:moneyFen(r[2],{allowZero:true,label:r[0]+'内部成本'}),note:r[3]||''};});
}
async function brImportPrices(){
 const context=brContext(),known=await brPriceVersions();if(context!==brContext())return;let request_id=requestKey(),rows=null;
 const dialog=modal('上传或粘贴物品价格表',`<form><p class="notice">按“物品名称、标准售价、内部成本、备注”四列填写，金额单位为元。支持 UTF-8 CSV / TSV，或直接粘贴 Excel 四列内容。同名物品更新本店参考价。</p><label>选择价格文件<input type="file" accept=".csv,.tsv,.txt" data-br-price-file></label><label>价格表内容<textarea rows="8" data-br-price-text placeholder="物品名称,标准售价,内部成本,备注"></textarea></label><button type="button" data-br-price-preview>预览待导入物品</button><div data-br-price-preview-table></div><div class="formerror" role="alert"></div><div class="modalfoot"><button class="primary" type="submit" disabled>核对无误，确认导入</button></div></form>`,async()=>{if(context!==brContext())throw new Error('门店或账号已切换。');if(!rows)throw new Error('请先预览价格表。');await api(BR_API+'/standard-prices/import',{method:'POST',body:{request_id,rows}});closeModal();await render();toast('标准价格已导入');});
 const form=$('form',dialog),input=$('[data-br-price-text]',form),preview=$('[data-br-price-preview-table]',form),submit=$('[type=submit]',form),error=$('.formerror',form);
 const reset=()=>{rows=null;submit.disabled=true;preview.innerHTML='';};input.oninput=reset;
 $('[data-br-price-file]',form).onchange=async event=>{try{const file=event.target.files[0];if(!file)return;if(file.size>1024*1024)throw new Error('价格文件请控制在 1 MB 以内。');input.value=await file.text();reset();}catch(e){error.textContent=e.message;}};
 $('[data-br-price-preview]',form).onclick=()=>{try{rows=brParsePriceTable(input.value).map(row=>({...row,...(known.has(row.name)?{version:known.get(row.name)}:{})}));request_id=requestKey();preview.innerHTML=table(['物品','本次操作','标准售价','内部成本','备注'],rows.map(r=>[E(r.name),r.version?'更新参考价 · 版本 '+r.version:'新增',brAmount(r.sale_price_cents),brAmount(r.cost_cents),E(r.note)]));submit.disabled=false;error.textContent='';}catch(e){reset();error.textContent=e.message;}};
}
async function brEstimatePrices(){
 const context=brContext(),prices=await api(BR_API+'/standard-prices?'+new URLSearchParams({q:brState.priceQuery||'',page_size:500}));if(context!==brContext())return;if(prices.total>500)throw new Error('匹配物品超过 500 项，请先在价格列表按名称缩小范围，再参考计算。');
 const dialog=modal('物品参考计算',`<form><p class="br-caption">在需要的物品后填写整数数量，其他留空。每次最多选择 100 项。结果供销售内勤核对，不自动写入合同。</p>${table(['物品','单项售价','单项成本','数量'],prices.items.map(p=>[E(p.name),brAmount(p.sale_price_cents),brAmount(p.cost_cents),`<input type="number" min="1" max="10000" step="1" name="quantity_${p.id}" aria-label="${E(p.name)}数量">`]))}${prices.total>500?'<p class="notice">仅展示前 500 个物品，请按批次核对。</p>':''}<div class="formerror" role="alert"></div><div class="modalfoot"><button type="submit" class="primary">计算参考金额</button></div><div data-br-estimate-result aria-live="polite"></div></form>`,async form=>{if(context!==brContext())throw new Error('门店或账号已切换。');const items=prices.items.filter(p=>form.elements['quantity_'+p.id].value!=='').map(p=>({price_id:p.id,quantity:Number(form.elements['quantity_'+p.id].value)}));if(!items.length)throw new Error('请填写至少一个物品的数量。');if(items.length>100)throw new Error('每次最多选择 100 个物品。');const result=await api(BR_API+'/standard-prices/estimate',{method:'POST',body:{items}});if(context!==brContext())return;$('[data-br-estimate-result]',form).innerHTML=brFacts([['参考售价合计',brAmount(result.sale_price_cents)],['参考成本合计',brAmount(result.cost_cents)]])+`<p class="notice">${E(result.note)}</p>`;});
}
async function brEditSettings(){const r=brState.settings;return brForm('设置赠品阈值',[{title:'审批规则',fields:[F('approval_mode','阈值方式','select',true,[{value:'all',label:'全部合同审批'},{value:'fixed',label:'单笔固定金额'},{value:'ratio',label:'车价比例'}]),F('threshold_amount','固定金额（元）','money_zero',false),F('threshold_ratio','车价比例（%）','text',false)]}],{approval_mode:r.approval_mode,threshold_amount:brInputAmount(r.threshold_amount_cents),threshold_ratio:r.threshold_basis_points==null?'':(r.threshold_basis_points/100).toFixed(2)},(v,request_id)=>api(BR_API+'/settings',{method:'PUT',body:{request_id,version:r.version,approval_mode:v.approval_mode,threshold_amount_cents:v.approval_mode==='fixed'?moneyFen(v.threshold_amount,{allowZero:true}):null,threshold_basis_points:v.approval_mode==='ratio'?brPercentage(v.threshold_ratio):null}}),{draftKey:'settings-'+r.version,notice:'本次设置不免除任何合同的管理审批。'});}
// Reports and manual columns are supplied by the same server catalog that
// defines aggregation and export. Never infer a financial result from a chart.
function brReportDefinitions(){return state.recordCatalog?.reports||[];}
function brReportFilters(){const today=day();return brState.filters||(brState.filters={report:'profit',metric:'',date_from:today.slice(0,8)+'01',date_to:today,group_by:'salesperson',brand:'',salesperson_id:'',category_field:'',category_value:'',service_type:'',handler_name:'',source_mode:'combined'});}
function brReportQuery(view){const {metric,...filters}=brReportFilters();if(metric)filters.report+=':'+metric;if(view)filters.view=view;if(brState.dashboardMode==='daily'){filters.day=brState.confirmedDailyDate||day();if(brState.trendActive)filters.days=brState.periodCounts?.daily||7;delete filters.date_from;delete filters.date_to;delete filters.source_mode;}return new URLSearchParams(Object.entries(filters).filter(([,v])=>v!==''&&v!=null));}
function brReportPath(){return brState.dashboardMode==='daily'?(brState.trendActive?'/daily-reports/trend':brState.dailyPreview?'/daily-reports/preview':'/daily-reports'):'/reports';}
function brGroupingOptions(definition){return [{value:'salesperson',label:definition?.source==='after_sales'?'经办人排名':'人员排名'},{value:'store',label:'门店排名'},{value:'brand',label:'品牌排名'},{value:'month',label:brState.dashboardMode==='daily'?'每日趋势':'月度趋势'},{value:'group',label:'集团合计'},...(definition?.grouping_fields||[]).map(c=>({value:'category:'+c.key,label:c.label}))];}
function brGroupControlValue(filters){return filters.group_by==='category'?'category:'+filters.category_field:filters.group_by;}
// Each pair refers to columns in one fixed server report definition. No target
// is inferred from a percentage or joined across records, dates or people.
const BR_PROGRESS_PAIRS={
 sales_targets:[['c02','c06','c10'],['c05','c09','c11']],
 after_sales_monthly:[['c02','c03','c04']],
 after_sales_targets:[['c01','c05','c06'],['c02','c09','c10'],['c14','c12','c15'],['c03','c16','c17']],
 sales_overview:[['c02','c04','c05']],
 insurance_renewal:[['c06','c07','c08']],
 individual_profit:[['c03','c04','c05']]
};
function brProgressPair(report){
 const pair=(BR_PROGRESS_PAIRS[report.report]||[]).find(keys=>keys.includes(report.metric));
 if(!pair)return null;
 const columns=report.summary_columns||[],target=columns.find(c=>c.key===pair[0]),actual=columns.find(c=>c.key===pair[1]);
 if(!target||!actual||target.type!==actual.type||target.unit!==actual.unit)return null;
 return {target,actual,rate:columns.find(c=>c.key===pair[2])};
}
function brPresentation(report){
 const definition=brReportDefinitions().find(r=>r.key===report.report),manual=definition?.source==='manual';
 const monthly=brState.trendActive||brReportFilters().group_by==='month',pair=manual&&!brState.trendActive?brProgressPair(report):null;
 const views=[{value:'auto',label:'自动展示'},{value:'bar',label:'柱状图'},{value:'rank',label:monthly?'数值对比':'指标排行'}];
 if(monthly)views.push({value:'line',label:'折线图'});
 if(pair)views.push({value:'progress',label:'目标进度'});
 views.push({value:'summary',label:'统计表'},{value:'details',label:'来源明细'});
 const selected=views.some(v=>v.value===brState.view)?brState.view:'auto';
 return {definition,manual,pair,views,selected,type:selected==='auto'?(monthly?'line':pair?'progress':'bar'):selected};
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
 const rows=report.rows||[],value=report.grand_total?.[report.metric];
 const label=brState.dashboardMode==='daily'&&brState.trendActive?'所选日期日报值':'当前范围合计',note=value==null?'未提供或不适合合计的指标显示为空':report.metric_label||report.title;
 const filters=brReportFilters();
 return `<div class="br-summary" aria-label="当前报表摘要"><div class="br-summary-card"><span>${E(label)}</span><strong data-summary="total">${E(value==null?'—':value)}<small>${E(report.unit||'')}</small></strong><p>${E(note)}</p></div><div class="br-summary-card"><span>${brState.dashboardMode==='daily'&&brState.trendActive?'趋势数据点':'来源记录'}</span><strong data-summary="records">${number(rows.length)}<small>条</small></strong><p>${number((report.summary_rows||[]).length)} 个统计分组${report.legacy_count?' · 历史记录另列':''}</p></div><div class="br-summary-card br-summary-period"><span>统计范围</span><strong data-summary="coverage">${E(filters.date_from)} — ${E(filters.date_to)}</strong><p>${E(report.period_basis||'')}</p></div></div>`;
}
function brPeriodComparison(report){
 if(!brState.trendActive)return '';
 let comparison=report.comparison;
 if(!comparison&&brState.dashboardMode==='monthly'){
  const currentLabel=brState.reportMonth,[y,m]=currentLabel.split('-').map(Number),previousLabel=new Date(Date.UTC(y,m-2,1)).toISOString().slice(0,7),items=report.series||[],now=items.find(item=>item.label===currentLabel),before=items.find(item=>item.label===previousLabel),current=now?.exact_value??now?.value??null,previous=before?.exact_value??before?.value??null;
  comparison={current,previous,difference:null,change_percent:null};
  const parts=value=>value==null?null:/^(-?)(\d+)(?:\.(\d+))?$/.exec(String(value)),a=parts(current),b=parts(previous);
  if(a&&b){const precision=Math.max(a[3]?.length||0,b[3]?.length||0),scale=10n**BigInt(precision),scaled=match=>(match[1]?-1n:1n)*BigInt(match[2]+(match[3]||'').padEnd(precision,'0')),av=scaled(a),bv=scaled(b),diff=av-bv,absolute=diff<0n?-diff:diff;comparison.difference=(diff<0n?'-':'')+(absolute/scale).toString()+(precision?'.'+(absolute%scale).toString().padStart(precision,'0'):'');if(bv!==0n){const denominator=bv<0n?-bv:bv,rate=(absolute*10000n+denominator/2n)/denominator;comparison.change_percent=(diff<0n?'-':'')+(rate/100n).toString()+'.'+(rate%100n).toString().padStart(2,'0');}}
 }
 if(!comparison)return '';
 const value=v=>v==null?'—':String(v)+(report.unit?' '+report.unit:'');
 return `<div class="br-period-comparison" aria-label="本期与前期对比">${[['本期',value(comparison.current)],['前期',value(comparison.previous)],['较前期差额',value(comparison.difference)],['较前期变化率',comparison.change_percent==null?'不计算':String(comparison.change_percent)+'%']].map(([label,v])=>`<div><span>${E(label)}</span><strong>${E(v)}</strong></div>`).join('')}<p class="br-caption">与紧邻前一期比较；缺值或前期为零时不计算变化率。变化率以差额除以上期绝对值计算。</p></div>`;
}
function brReportResult(report){
 const p=brPresentation(report),progress=p.type==='progress',tabular=['summary','details'].includes(p.type);
 const title=progress?`${report.title} · ${p.pair.actual.label}完成情况`:`${report.title}${report.metric_label&&report.metric_label!==report.title?' · '+report.metric_label:''}`;
 const unit=progress?p.pair.actual.unit:report.unit;
 const explanation=progress?'比较同一统计分组的目标与实际。':p.type==='line'?'按时间顺序展示；未确认或未核定值保留断点。':p.type==='bar'?'逐项对比数值；未确认或未核定值留空。':p.type==='summary'?'按当前维度生成统计表；比例、单价和累计数按各自口径处理。':p.type==='details'?'当前筛选的来源记录，合同号可打开原单。':'按当前指标排序，相同数值并列；未核定项不参与排名。';
 const notice=Array.isArray(report.notice)?report.notice.join('；'):report.notice||'';
 return `<section class="panel br-chart-panel"><div class="panelhead br-report-head"><div><h2>${E(title)}</h2><p class="br-caption">${E(report.period_basis||'')} · 单位：${E(unit||'数值')}</p></div><span class="br-updated">${report.updated_at?'数据更新于 '+E(time(report.updated_at)):'尚无记录'}</span></div><div class="br-view-tools" role="group" aria-label="展示方式">${p.views.map(v=>`<button type="button" data-br="report-view" data-view="${v.value}" aria-pressed="${p.selected===v.value}">${E(v.label)}</button>`).join('')}</div>${tabular?`<div id="br-report-table" class="br-report-table">${brReportTable(report,p.type)}</div>`:`<div id="br-chart" class="br-chart" aria-label="${E(title)}"></div>`}<p class="br-caption br-chart-notice">${E(explanation)}${notice?'<br>'+E(notice):''}</p></section>${p.type==='details'&&report.legacy_count?`<details class="panel br-disclosure"><summary>历史记录 · ${number(report.legacy_count)} 条（不计入当前成绩）</summary>${brReportTable({...report,rows:report.legacy_rows||[]},'details','legacy')}</details>`:''}`;
}
async function brDashboard(mode='monthly'){
 const wasTrend=brState.trendActive;brState.dashboardMode=mode;brState.trendActive=['daily','monthly'].includes(mode)&&brState.periodViews?.[mode]==='trend';if(!brCaps().price||brState.trendActive)brState.dailyPreview=false;
 const filters=brReportFilters(),definitions=brReportDefinitions();if(definitions.length&&!definitions.some(r=>(r.key||r.value)===filters.report))filters.report=definitions[0].key||definitions[0].value;
 const definition=definitions.find(r=>r.key===filters.report);if(definition&&!definition.metrics.some(m=>m.key===filters.metric))filters.metric=definition.default_metric||definition.metrics[0]?.key||'';
 const count=brState.periodCounts?.[mode]||(mode==='daily'?7:6);if(brState.trendActive){filters.group_by='month';}else if(wasTrend)filters.group_by='salesperson';
 const month=brState.reportMonth||day().slice(0,7),dailyDate=brState.confirmedDailyDate||day();brState.reportMonth=month;
 if(mode==='monthly'){const [y,m]=month.split('-').map(Number);filters.date_from=brState.trendActive?new Date(Date.UTC(y,m-count,1)).toISOString().slice(0,10):month+'-01';filters.date_to=month+'-'+new Date(y,m,0).getDate();}
 else if(mode==='daily'){if(brState.dailyPreview)for(const key of ['brand','salesperson_id','category_field','category_value','service_type','handler_name'])filters[key]='';filters.date_from=brState.trendActive?new Date(Date.parse(dailyDate+'T00:00:00Z')-(count-1)*86400000).toISOString().slice(0,10):dailyDate;filters.date_to=dailyDate;filters.source_mode='combined';}
 else {const range=brState.rangeDates||{date_from:day().slice(0,8)+'01',date_to:day()};filters.date_from=range.date_from;filters.date_to=range.date_to;}
 const epoch=renderId,report=await api(BR_API+brReportPath()+'?'+brReportQuery());if(epoch!==renderId)return '';brState.report=report;brState.reportPages={summary:1,details:1,legacy:1};
 const confirmed=report.publication?.status==='confirmed',preview=mode==='daily'&&brState.dailyPreview;
 const publication=mode==='daily'?`<section class="br-publication"><div><strong>${brState.trendActive?'已确认日报的每日趋势':preview?'销售内勤日报预览':confirmed?'销售内勤已确认的每日报表':'当日报表尚未确认'}</strong><p>${brState.trendActive?'仅采用销售内勤已确认日报，缺少确认的日期保留断点。':preview?'当前展示完整门店当日数据。请核对后确认整张报表，确认会追加一个日报版本。':confirmed?'展示销售内勤最后确认的版本；后续补录需要销售内勤重新核对确认。':'暂无可展示的确认版本。销售内勤先查看预览、核对，再确认日报。'}</p>${report.publication?.confirmed_at?`<p>确认时间：${E(time(report.publication.confirmed_at))}</p>`:''}</div><div class="row"><label>报表日期<input id="br-confirmed-daily-date" type="date" value="${E(dailyDate)}" required></label>${brCaps().price&&!brState.trendActive?brButton('daily-preview',preview?'返回已确认日报':'查看最新数据预览'):''}${preview&&report.confirmation?.source_digest?brButton('confirm-daily','核对并确认日报','','primary'):''}</div></section>`:mode==='monthly'?`<section class="br-publication"><div><strong>月度经营统计</strong><p>销售内勤更新业务资料和统计表后自动汇总。选择月份查看当前结果，未核定的数据保留空白。</p></div><label>统计月份<input id="br-report-month" type="month" value="${E(month)}" required></label></section>`:'<p class="notice">按自定义日期范围读取当前业务和人工填报数据，可筛选并查看一张图表。</p>';
 const periodTools=['daily','monthly'].includes(mode)?`<form id="br-period-window" class="br-period-window"><label>对比范围<select name="display">${brOptions([{value:'current',label:mode==='daily'?'当前日报':'当前月份'},{value:'trend',label:mode==='daily'?'过去 N 日趋势':'过去 N 月趋势'}],brState.trendActive?'trend':'current')}</select></label><label>期数 N<input type="number" name="count" min="2" max="${mode==='daily'?90:36}" step="1" value="${count}" aria-label="趋势期数" required></label><button type="submit">应用范围</button><span class="br-caption">含当前${mode==='daily'?'日':'月'}，最多 ${mode==='daily'?90:36} ${mode==='daily'?'日':'月'}。</span></form>`:'';
 const controls=`<form id="br-report-filter" class="br-filter br-report-filter"><label>报表<select name="report">${brOptions(definitions.map(r=>({value:r.key||r.value,label:r.title||r.label})),filters.report)}</select></label><label>指标<select name="metric">${brOptions((definition?.metrics||[]).map(m=>({value:m.key,label:m.label})),filters.metric)}</select></label><label>开始日期<input name="date_from" type="date" required value="${E(filters.date_from)}"></label><label>结束日期<input name="date_to" type="date" required value="${E(filters.date_to)}"></label><label>查看维度<select name="group_by">${brOptions(brGroupingOptions(definition),brGroupControlValue(filters))}</select></label><label>数据来源<select name="source_mode">${brOptions([{value:'combined',label:'自动生成 + 人工补充'},{value:'generated',label:'自动生成'},{value:'manual',label:'人工填报'}],filters.source_mode||'combined')}</select></label><label>品牌<input name="brand" value="${E(filters.brand)}" placeholder="全部品牌"></label><label>销售<select name="salesperson_id"><option value="">权限内全部</option>${brOptions((state.recordCatalog.sales_people||[]).map(p=>({value:p.id,label:p.label})),filters.salesperson_id)}</select></label><label>分类字段<select name="category_field"><option value="">不筛选分类</option>${brOptions(definition?.grouping_fields||[],filters.category_field)}</select></label><label>分类内容<input name="category_value" value="${E(filters.category_value||'')}" placeholder="如保险公司、银行、车型"></label><label>售后业务类型<select name="service_type"><option value="">全部类型</option>${brOptions(state.recordCatalog.service_types||[],filters.service_type)}</select></label><label>售后经办人<input name="handler_name" value="${E(filters.handler_name||'')}" placeholder="全部经办人"></label><button class="primary" type="submit">生成报表</button></form>`;
 return heading(({daily:'每日报表',range:'自定义范围数据',monthly:'月报统计'})[mode],'每次查看一张报表，可切换指标、维度和展示方式。',(mode==='monthly'&&['admin','manager','general_manager','group_deputy_manager','chairman','clerk'].includes(state.user.role)?brLink('records-dashboard/targets','月度目标'):'')+(brCaps().record_statistics?brLink('records-manual','销售内勤日常表格'):'')+(!preview?brButton('export-report',brPresentation(report).type==='details'?'导出来源明细':'导出统计表',mode==='daily'&&!brState.trendActive&&!confirmed?'disabled':''):''))+publication+periodTools+controls+brReportSummary(report)+brPeriodComparison(report)+`<div id="br-report-result">${brReportResult(report)}</div>`;
}
async function brConfirmDaily(){
 const report=brState.report,confirmation=report?.confirmation;if(!brCaps().price||!brState.dailyPreview||!confirmation?.source_digest)throw new Error('请先打开最新日报预览并核对。');
 return brForm('确认销售内勤日报',[{title:report.title+' · '+confirmation.day,fields:[F('note','本次确认说明','textarea',false)]}],{},(v,request_id)=>api(BR_API+'/daily-reports/confirm',{method:'POST',body:{day:confirmation.day,report:confirmation.report,expected_version:confirmation.expected_version,source_digest:confirmation.source_digest,request_id,note:v.note}}).then(result=>{brState.dailyPreview=false;return result;}),{draftKey:'daily-confirm-'+confirmation.day+'-'+confirmation.report+'-'+confirmation.source_digest,submit:'确认整张日报',notice:'确认的是本门店当日完整报表。若预览后来源数据发生变化，系统会要求重新预览；再次确认保留旧版本。'});
}
async function brDailyVehicles(){
 const selected=brState.dailyDate||day(),epoch=renderId,d=await api(BR_API+'/daily-vehicle-reports?'+new URLSearchParams({day:selected}));if(epoch!==renderId)return '';brState.dailyReport=d;
 const columns=d.columns||[],rows=d.rows||[];
 const draw=table(columns.map(c=>c.label+(c.unit?'（'+c.unit+'）':'')),rows.map(row=>columns.map(c=>c.key==='number'||c.key==='contract_number'?brLink('records-sales/'+(row.contract_id||row.id),row[c.key]||'查看合同'):E(row[c.key]??'—'))));
 return heading('今日车辆更新','查看指定日期发生状态变化的车辆，提醒销售内勤整理当日逐车汇总。',brLink('records-sales','返回销售业务')+brButton('export-daily','导出车辆更新记录'))+`<form id="br-daily-filter" class="br-filter"><label>查看日期<input type="date" name="day" required value="${E(selected)}"></label><button type="submit" class="primary">查看车辆更新</button></form><div class="notice">${E(Array.isArray(d.notice)?d.notice.join('；'):d.notice||'本页是车辆更新提醒，请销售内勤自行核对、整理日报。')}</div><section class="panel"><div class="panelhead"><h2>当日更新车辆 · ${number(d.counts?.changed_vehicles??rows.length)} 辆</h2><p class="br-caption">${number(d.counts?.changes??0)} 次状态变更</p></div><div class="br-report-table">${draw}</div></section>`;
}
function brReportTable(report,view='details',pageKey=view){
 const summary=view==='summary',columns=(summary?report.summary_columns:report.columns)||[],source=brReportDefinitions().find(r=>r.key===report.report)?.source;
 const allRows=(summary?report.summary_rows:report.rows)||[],pages=brState.reportPages||(brState.reportPages={}),page=Math.min(Math.max(1,pages[pageKey]||1),Math.max(1,Math.ceil(allRows.length/100)));pages[pageKey]=page;
 const rows=[...allRows.slice((page-1)*100,page*100),...(summary&&report.grand_total?[report.grand_total]:[])];
 const paging=allRows.length>100?`<div class="pagination"><span>共 ${number(allRows.length)} 条 · 第 ${page} / ${Math.ceil(allRows.length/100)} 页 · 每页 100 条</span><div class="row">${brButton('report-page','上一页',`data-view="${E(pageKey)}" data-page="${page-1}" ${page<=1?'disabled':''}`)}${brButton('report-page','下一页',`data-view="${E(pageKey)}" data-page="${page+1}" ${page*100>=allRows.length?'disabled':''}`)}</div></div>`:'';
 return table(columns.map(c=>c.label+(c.unit?'（'+c.unit+'）':'')),rows.map(row=>columns.map(c=>{
  const value=row[c.key];if(value==null)return '—';
  if(!summary&&['number','contract_number'].includes(c.key)&&(row.contract_id||source==='contracts'))return brLink('records-sales/'+(row.contract_id||row.id),value);
  return row===report.grand_total?`<strong>${E(value)}</strong>`:E(value);
 })))+paging;
}
async function brManualReports(){
 const d=await api(brPageURL('/manual-reports',{report_key:state.status,include_history:brState.manualHistory}));const definitions=brReportDefinitions();
 const controls=`<form id="br-list-filter" class="br-filter"><label>统计报表<select name="status"><option value="">全部报表</option>${brOptions(definitions.filter(r=>r.source==='manual').map(r=>({value:r.key,label:r.title})),state.status)}</select></label><label>记录范围<select name="include_history">${brOptions([{value:'false',label:'当前有效记录'},{value:'true',label:'包含修订历史'}],String(brState.manualHistory))}</select></label><button type="submit" class="primary">查询</button></form>`;
 return heading('销售内勤日常表格','保留原截图全部表项。逐车资料从合同核对；任务、营销、外部核算利润等在这里填报。',brLink('records-sales','返回销售业务')+brLink('records-sales/daily','今日车辆更新')+brLink('records-dashboard/monthly','月报统计')+(brCaps().record_statistics?brButton('import-manual','上传统计表')+brButton('new-manual','填写统计数据','','primary'):''))+storeNotice()+controls+`<p class="br-caption">月内累计取同口径最新记录，单笔明细逐笔汇总。空白表示未提供，此车销售利润按实际结果填写；修订保留历史。</p><section class="panel">${table(['统计日期','报表','品牌','填报方式','关联合同','状态','已填数据','操作'],d.items.map(r=>{const spec=definitions.find(x=>x.key===r.report_key);return [E(r.period),E(spec?.title||r.report_key),E(r.brand||'—'),E(brEntryModeLabel(r.entry_mode)),r.contract_id?brLink('records-sales/'+r.contract_id,r.contract_number||'查看合同'):'—',E(r.is_current===false?'历史版本':'有效'),`<details><summary>查看填写内容</summary><div class="br-manual-values">${(spec?.columns||[]).filter(c=>r.values?.[c.key]!=null).map(c=>`${E(c.label)}：${E(r.values[c.key])}`).join('<br>')}${r.note?'<br>备注：'+E(r.note):''}</div></details>`,brButton('manual-detail',r.can_correct?'查看 / 修订':'查看',`data-id="${E(r.id)}"`)];}))}${pager(d.total)}</section>`;
}
function brEntryModeLabel(mode){return ({snapshot:'月内累计 / 截至日',detail:'单笔明细',legacy:'历史记录',target:'月度目标'})[mode]||mode||'历史记录';}
async function brManualDetail(id){
 const context=brContext(),r=await api(BR_API+'/manual-reports/'+id);if(context!==brContext())return;
 const spec=brReportDefinitions().find(s=>s.key===r.report_key);if(!spec)throw new Error('当前岗位不可查看该报表。');
 const history=r.history||[],body=brFacts([['统计日期',r.period],['品牌',r.brand],['填报方式',brEntryModeLabel(r.entry_mode)],['状态',r.is_current===false?'历史版本':'当前有效'],['关联合同',r.contract_number],['备注',r.note]])+`<div class="br-manual-detail">${table(['原表项目','数据'],spec.columns.map(c=>[E(c.label+(c.unit?'（'+c.unit+'）':'')),E(r.values?.[c.key]??'—')]))}</div>`+(history.length?`<details class="br-disclosure"><summary>修订历史 · ${history.length} 版</summary>${table(['版本','统计日期','状态','说明'],history.map((h,index)=>[E('第 '+(index+1)+' 版'),E(h.period),E(h.is_current===false?'历史版本':'有效'),E(h.note||'—')]))}</details>`:'')+`<div class="modalfoot">${r.can_correct?brButton('manual-correct','修订这份记录',`data-id="${E(r.id)}"`,'primary'):''}</div>`;
 modal(spec.title,body);
}
async function brNewManual(reportKey,{contractId=brState.manualContract,revision=null}={}){
 const definitions=brReportDefinitions().filter(r=>r.source==='manual'&&(!contractId||r.supports_contract));
 if(!reportKey){modal('选择统计报表',`<p class="br-caption">${contractId?'选择要补充的原表，合同已有信息将自动带出。':'选择原报表，可关联合同补充资料，也可独立填写统计数据。'}空白表示未提供。</p><div class="br-report-picker">${definitions.map(r=>brButton('manual-report-select',r.title,`data-report="${E(r.key)}"`)).join('')}</div>`);return;}
 const spec=definitions.find(r=>r.key===reportKey);if(!spec)throw new Error('统计报表不存在，请刷新目录。');
 const context=brContext(),draftKey=revision?'manual-revision-'+revision.id:'manual-'+reportKey+(contractId?'-contract-'+contractId:''),draft=brState.drafts[draftKey];
 const initial={period:revision?.period||day(),brand:revision?.brand||'',salesperson_id:revision?.salesperson_id||'',entry_mode:revision?.entry_mode||spec.default_entry_mode||'snapshot',contract_id:revision?.contract_id||contractId||'',contract_version:revision?.contract_version||'',note:revision?.note||'',...Object.fromEntries(Object.entries(revision?.values||{}).map(([k,v])=>['value_'+k,v??'']))};
 const fields=spec.columns.map(c=>F('value_'+c.key,c.label+(c.unit?'（'+c.unit+'）':''),c.type==='date'?'date':'text',false));
 const meta=[F('contract_id','关联合同编号','text',false),F('contract_version','合同版本','int',false),F('period','统计日期','date'),F('brand','所属品牌','text',false),F('salesperson_id','所属销售','select',false,(state.recordCatalog.sales_people||[]).map(p=>({value:p.id,label:p.label}))),F('entry_mode','填报方式','select',true,[{value:'snapshot',label:'月内累计 / 截至日'},{value:'detail',label:'单笔明细'}]),F('note',revision?'修订说明':'备注（如无任务）','textarea',Boolean(revision))];
 let bindingReady=true;
 const dialog=await brForm((revision?'修订 · ':'')+spec.title,[{title:'统计归属',fields:meta},{title:'原表项目',fields}],initial,(v,request_id)=>{
  if(!bindingReady)throw new Error('请先完成合同信息核对。');
  return api(BR_API+'/manual-reports',{method:'POST',body:{request_id,report_key:reportKey,period:v.period,brand:v.brand,salesperson_id:v.salesperson_id?Number(v.salesperson_id):null,entry_mode:v.entry_mode,contract_id:v.contract_id?Number(v.contract_id):null,contract_version:v.contract_id?Number(v.contract_version):null,...(revision?{supersedes_id:revision.id,supersedes_version:revision.version}:{}),note:v.note,values:Object.fromEntries(spec.columns.map(c=>[c.key,v['value_'+c.key]===''?null:v['value_'+c.key]]))}});
 },{draftKey,submit:revision?'保存修订':'保存统计数据',notice:(spec.supports_contract?'合同已有信息自动带出；其余项目按人工核对结果填写。':'按人工核对结果填写原表项目。')+'月内累计取同口径最新记录，单笔明细按笔汇总。金额以元填写，比例 10 表示 10%。'+(spec.input_notice||'')});
 if(context!==brContext())return;
 const form=$('form',dialog),idInput=form.elements.contract_id,versionInput=form.elements.contract_version;
 idInput.closest('label').hidden=true;versionInput.closest('label').hidden=true;
 if(!spec.supports_contract)return dialog;
 const holder=document.createElement('div');holder.className='br-contract-picker wide';holder.innerHTML=`<label>关联合同（可选）<div class="br-contract-search"><input type="search" data-br-contract-search placeholder="按合同号、客户或车辆查找" aria-label="查找关联合同" autocomplete="off"><button type="button" data-br-contract-find>查找</button></div></label><p class="br-caption" data-br-contract-current>未关联合同</p><div class="br-contract-options" data-br-contract-options></div><p class="br-caption" data-br-contract-status aria-live="polite"></p><div class="row"><button type="button" data-br-contract-refresh>重新核对合同信息</button>${revision?'':brButton('clear-manual-contract','取消关联合同')}</div>`;
 idInput.closest('label').before(holder);
 const search=$('[data-br-contract-search]',holder),options=$('[data-br-contract-options]',holder),current=$('[data-br-contract-current]',holder),status=$('[data-br-contract-status]',holder),submit=$('[type=submit]',form);
 let requestEpoch=0,locked=[];
 const active=()=>context===brContext()&&form.isConnected;
 const remember=()=>form.dispatchEvent(new Event('input',{bubbles:true}));
 const controlFor=key=>form.elements['value_'+key]||form.elements[key];
 const lock=(keys)=>{for(const key of locked){const control=controlFor(key);if(control){control.readOnly=false;control.removeAttribute('aria-readonly');control.closest('label')?.classList.remove('br-field-locked');if(control.tagName==='SELECT'){control.style.pointerEvents='';control.onkeydown=null;control.removeAttribute('tabindex');}}}locked=keys||[];for(const key of locked){const control=controlFor(key);if(control){control.readOnly=true;control.setAttribute('aria-readonly','true');control.closest('label')?.classList.add('br-field-locked');if(control.tagName==='SELECT'){control.style.pointerEvents='none';control.onkeydown=event=>event.preventDefault();control.tabIndex=-1;}}}};
 const selectContract=async(id,{restore=false}={})=>{
  const epoch=++requestEpoch;bindingReady=false;submit.disabled=true;status.textContent='正在读取合同及核价信息…';
  try{
   const [contract,prefill]=await Promise.all([api(BR_API+'/contracts/'+id),api(BR_API+'/report-prefill?'+new URLSearchParams({report_key:reportKey,contract_id:id}))]);if(!active()||epoch!==requestEpoch)return;
   const stale=restore&&versionInput.value&&String(versionInput.value)!==String(prefill.contract_version);form.elements.entry_mode.value='detail';
   if(!restore){
    for(const key of locked){const control=controlFor(key);if(control&&key.startsWith('c'))control.value='';}
    for(const [key,value] of Object.entries(prefill.values||{})){const control=controlFor(key);if(control)control.value=value??'';}
    for(const key of ['period','brand','salesperson_id'])if(prefill[key]!=null)form.elements[key].value=prefill[key];
    idInput.value=prefill.contract_id;versionInput.value=prefill.contract_version;form.elements.entry_mode.value='detail';
   }
   lock([...(prefill.locked_fields||[]),...(prefill.locked_metadata||[]),'entry_mode']);current.textContent=[contract.number,contract.customer_name,contract.brand,contract.model].filter(Boolean).join(' · ');options.replaceChildren();
   status.textContent=stale?'合同已更新，请重新选择这份合同并核对带出内容。':'合同和核价已有信息已锁定，其余原表项目请人工补充。';bindingReady=!stale;if(!restore)remember();
  }catch(error){if(active()&&epoch===requestEpoch){status.textContent=error.message;bindingReady=false;}}
  finally{if(active()&&epoch===requestEpoch)submit.disabled=!bindingReady;}
 };
 const find=async()=>{
  const epoch=++requestEpoch;status.textContent='正在查找…';
  try{const result=await api(BR_API+'/contracts?'+new URLSearchParams({q:search.value.trim(),page:1,page_size:20}));if(!active()||epoch!==requestEpoch)return;options.innerHTML=result.items.map(c=>`<button type="button" data-contract-id="${E(c.id)}"><strong>${E(c.number)}</strong><span>${E([c.customer_name,c.brand,c.model,c.salesperson_name].filter(Boolean).join(' · '))}</span></button>`).join('');status.textContent=result.total>20?'显示前 20 份，请输入更准确的关键词。':result.items.length?'选择要关联的合同。':'未找到可选合同。';}catch(error){if(active()&&epoch===requestEpoch)status.textContent=error.message;}
 };
 $('[data-br-contract-find]',holder).onclick=find;search.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();find();}};
 options.onclick=event=>{const button=event.target.closest('[data-contract-id]');if(button)selectContract(Number(button.dataset.contractId));};
 $('[data-br-contract-refresh]',holder).onclick=()=>{if(idInput.value)selectContract(Number(idInput.value));else status.textContent='请先查找并选择合同。';};
 const clear=$('[data-br=clear-manual-contract]',holder);if(clear)clear.onclick=()=>{requestEpoch++;for(const key of locked){const control=controlFor(key);if(control&&key.startsWith('c'))control.value='';}lock([]);idInput.value='';versionInput.value='';current.textContent='未关联合同';status.textContent='';options.replaceChildren();bindingReady=true;submit.disabled=false;remember();};
 if(revision){search.disabled=true;$('[data-br-contract-find]',holder).disabled=true;}
 if(idInput.value)await selectContract(Number(idInput.value),{restore:Boolean(draft||revision)});
}
function brDelimitedRows(text){
 text=String(text).replace(/^\uFEFF/,'');const first=text.split(/\r?\n/,1)[0],separator=first.includes('\t')?'\t':',';let rows=[],row=[],cell='',quoted=false;
 for(let i=0;i<text.length;i++){const ch=text[i];if(ch==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}else if(!quoted&&(ch===separator||ch==='\n'||ch==='\r')){row.push(cell.trim());cell='';if(ch!==separator){if(ch==='\r'&&text[i+1]==='\n')i++;if(row.some(Boolean))rows.push(row);row=[];}}else cell+=ch;}
 if(quoted)throw new Error('表格含未闭合引号，请检查文件。');row.push(cell.trim());if(row.some(Boolean))rows.push(row);return rows;
}
function brSaveCSV(name,rows){
 const cell=value=>{let text=String(value??'');if(/^[=+@-]/.test(text)&&!/^[-+]?\d+(?:\.\d+)?$/.test(text))text="'"+text;return '"'+text.replaceAll('"','""')+'"';};const text='\uFEFF'+rows.map(row=>row.map(cell).join(',')).join('\r\n')+'\r\n';
 const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'})),link=document.createElement('a');link.href=url;link.download=name;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function brImportManual(){
 const definitions=brReportDefinitions().filter(s=>s.source==='manual'),context=brContext();let entries=[],spec=null,started=false,binding=null;
 if(!brCaps().record_statistics)throw new Error('当前岗位不能导入销售内勤统计数据。');
 const dialog=modal('上传销售内勤统计表',`<form><p class="notice">选择原报表，下载 CSV 模板填写，或直接粘贴包含标题行的 Excel 内容。每次最多 500 行，金额为元、比例 10 表示 10%，未知值留空。逐车合同附带资料请在合同内核对审批。</p><div class="formgrid"><label>统计报表<select name="report_key">${brOptions(definitions.map(s=>({value:s.key,label:s.title})),state.status)}</select></label><label>统一统计日期<input name="period" type="date" value="${day()}" required></label><label>所属品牌<input name="brand" placeholder="未分品牌可留空"></label><label>所属销售<select name="salesperson_id"><option value="">不指定销售</option>${brOptions((state.recordCatalog.sales_people||[]).map(p=>({value:p.id,label:p.label})), '')}</select></label><label>填报口径<select name="entry_mode"><option value="snapshot">月内累计 / 截至日</option><option value="detail">单笔明细</option></select></label><label>统一备注<input name="note" placeholder="例如：销售内勤核定的月度最终数据"></label></div><div class="row br-import-tools"><button type="button" data-br-manual-template>下载本表 CSV 模板</button><label>选择 UTF-8 CSV / TSV<input type="file" accept=".csv,.tsv,.txt" data-br-manual-file></label></div><label>粘贴 Excel 内容（含标题行）<textarea rows="8" data-br-manual-text></textarea></label><button type="button" data-br-manual-preview>预览列对应和数据</button><div data-br-manual-mapping></div><div data-br-manual-preview-table></div><p data-br-manual-progress aria-live="polite"></p><p class="br-caption">本次新增记录，不按客户或车型自动覆盖。更正已存记录请回到列表选择“修订”，保留原记录。每行独立保存，失败即暂停，已成功的行不会重复提交。</p><div class="formerror" role="alert"></div><div class="modalfoot"><button type="button" data-br-manual-result hidden>下载提交结果</button><button type="submit" class="primary" disabled>核对无误，确认逐行导入</button></div></form>`,async form=>{
  if(context!==brContext())throw new Error('门店或账号已切换，请重新核对。');if(!entries.length||!spec||!binding)throw new Error('请先预览表格并核对列对应。');
  started=true;for(const input of form.querySelectorAll('input,textarea,select,[data-br-manual-preview],[data-br-manual-template]'))input.disabled=true;
  const progress=$('[data-br-manual-progress]',form),submit=$('[type=submit]',form);$('[data-br-manual-result]',form).hidden=false;
  for(let index=0;index<entries.length;index++){
   const entry=entries[index];if(entry.result)continue;if(context!==brContext())throw new Error('门店已切换，已停止后续行。');
   progress.textContent=`正在保存第 ${index+1} / ${entries.length} 行；已成功 ${entries.filter(e=>e.result).length} 行。`;
   try{entry.result=await api(BR_API+'/manual-reports',{method:'POST',body:{...binding,request_id:entry.request_id,report_key:spec.key,values:entry.values}});entry.error='';}
   catch(error){entry.error=error.message;progress.textContent=`导入暂停：已成功 ${entries.filter(e=>e.result).length} / ${entries.length} 行，第 ${index+1} 行未完成。`;submit.textContent='重试未完成行（成功行不再提交）';renderPreview();throw error;}
   renderPreview();
  }
  progress.textContent=`导入完成：${entries.length} 行均已保存。返回列表即可核对，月度看板会读取更新后的数据。`;submit.textContent='全部已导入';toast('统计表已导入');
 });
 const form=$('form',dialog),input=$('[data-br-manual-text]',form),preview=$('[data-br-manual-preview-table]',form),mapping=$('[data-br-manual-mapping]',form),error=$('.formerror',form),submit=$('[type=submit]',form);
 const label=c=>c.label+(c.unit?'（'+c.unit+'）':''),current=()=>definitions.find(s=>s.key===form.elements.report_key.value);
 function reset(){if(started)return;entries=[];binding=null;submit.disabled=true;preview.innerHTML='';mapping.innerHTML='';}
 function renderPreview(){if(!spec)return;preview.innerHTML=table(['行号','保存状态',...spec.columns.map(label)],entries.map((entry,i)=>[String(i+1),E(entry.result?'已保存 #'+entry.result.id:entry.error?'暂停：'+entry.error:'待确认'),...spec.columns.map(c=>E(entry.values[c.key]??'—'))]));}
 form.addEventListener('input',reset);form.addEventListener('change',reset);
 form.elements.report_key.onchange=()=>{reset();form.elements.entry_mode.value=current()?.default_entry_mode||'snapshot';};
 $('[data-br-manual-template]',form).onclick=()=>{const selected=current();if(selected)brSaveCSV(selected.title+'-填报模板.csv',[selected.columns.map(label)]);};
 $('[data-br-manual-file]',form).onchange=async event=>{try{const file=event.target.files[0];if(!file)return;if(file.size>5*1024*1024)throw new Error('统计文件请控制在 5 MB 以内。');input.value=await file.text();reset();}catch(e){error.textContent=e.message;}};
 $('[data-br-manual-preview]',form).onclick=()=>{try{
  if(!form.reportValidity())return;spec=current();const rows=brDelimitedRows(input.value);if(rows.length<2)throw new Error('请提供标题行和至少一行数据。');if(rows.length>501)throw new Error('一次最多导入 500 行，请拆分文件后重试；未截取或提交任何数据。');
  const headers=rows.shift(),seen=new Set(),keys=headers.map(header=>{const column=spec.columns.find(c=>header===c.label||header===label(c));if(!column)throw new Error('无法对应原表列：'+header+'。请使用下载模板的标题。');if(seen.has(column.key))throw new Error('重复列：'+header);seen.add(column.key);return column.key;});
  entries=rows.map((row,i)=>{if(row.length!==headers.length)throw new Error('第 '+(i+1)+' 行列数与标题不一致。');return {request_id:requestKey(),values:Object.fromEntries(spec.columns.map(c=>{const index=keys.indexOf(c.key);return [c.key,index<0||row[index]===''?null:row[index]];})),result:null,error:''};});
  binding={period:form.elements.period.value,brand:form.elements.brand.value.trim(),salesperson_id:form.elements.salesperson_id.value?Number(form.elements.salesperson_id.value):null,entry_mode:form.elements.entry_mode.value,note:form.elements.note.value};
  mapping.innerHTML=`<p class="notice">已识别 ${entries.length} 行、${headers.length} 列，统一归属 ${E(binding.period)} / ${E(brEntryModeLabel(binding.entry_mode))}。未提供的 ${spec.columns.length-headers.length} 列保留空白。</p><details><summary>查看列对应</summary>${table(['文件标题','原表项目'],headers.map((h,i)=>[E(h),E(label(spec.columns.find(c=>c.key===keys[i])))]))}</details>`;renderPreview();submit.disabled=false;error.textContent='';
 }catch(e){reset();error.textContent=e.message;}};
 $('[data-br-manual-result]',form).onclick=()=>brSaveCSV((spec?.title||'统计表')+'-提交结果.csv',[['原行号','结果','记录编号','错误说明',...spec.columns.map(label)],...entries.map((entry,i)=>[i+1,entry.result?'已保存':'未完成',entry.result?.id||'',entry.error,...spec.columns.map(c=>entry.values[c.key])])]);
}
function leaveBusinessRecordsChart(){const node=$('#br-chart');if(node){if(typeof Charts!=='undefined')Charts.dispose(node);if(typeof RecordsCharts!=='undefined')RecordsCharts.dispose(node);}}
function mountBusinessRecordsChart(){
 const chart=$('#br-chart'),report=brState.report;if(!chart||!report)return;
 const p=brPresentation(report),spec=p.definition?.metrics.find(m=>m.key===report.metric);
 let unit=spec?.unit||report.unit||'',precision=spec?.precision??report.precision??2,items=report.series||[];
 if(p.type==='progress'){
  unit=p.pair.actual.unit;precision=p.pair.actual.precision;
  items=(report.summary_rows||[]).map(row=>({label:row.label,period:row.period,
   actual:row[p.pair.actual.key]==null?null:Number(row[p.pair.actual.key]),actual_exact:row[p.pair.actual.key],
   target:row[p.pair.target.key]==null?null:Number(row[p.pair.target.key]),target_exact:row[p.pair.target.key],reported_rate:p.pair.rate?row[p.pair.rate.key]:null}));
 }
 RecordsCharts.render(chart,{type:p.type,title:report.title,unit,precision,items,scope:'summary',interval:brState.dashboardMode==='daily'&&brState.trendActive?'day':'month'});
}
function mountBusinessRecords(){
 const f=$('#br-list-filter');if(f)f.onsubmit=event=>{event.preventDefault();const data=Object.fromEntries(new FormData(f));state.q=data.q||'';state.status=data.status||'';if('include_history'in data)brState.manualHistory=data.include_history==='true';state.page=1;render();};
 const filter=$('#br-report-filter');if(filter){
  for(const name of ['date_from','date_to'])filter.elements[name].closest('label').hidden=brState.dashboardMode!=='range';filter.elements.source_mode.closest('label').hidden=brState.dashboardMode==='daily';filter.elements.group_by.disabled=Boolean(brState.trendActive);
  const configure=(reset=false)=>{const spec=brReportDefinitions().find(r=>r.key===filter.elements.report.value),fields=spec?.grouping_fields||[],service=spec?.source==='after_sales'||spec?.key?.startsWith('after_sales_'),mixed=spec?.key==='sales_targets';
   if(reset){filter.elements.metric.innerHTML=brOptions((spec?.metrics||[]).map(m=>({value:m.key,label:m.label})),spec?.default_metric);filter.elements.group_by.innerHTML=brOptions(brGroupingOptions(spec),'salesperson');filter.elements.category_field.innerHTML='<option value="">不筛选分类</option>'+brOptions(fields.map(c=>({value:c.key,label:c.label})), '');filter.elements.category_value.value='';filter.elements.service_type.value='';filter.elements.handler_name.value='';}
   filter.elements.category_field.disabled=!fields.length;filter.elements.category_value.disabled=!fields.length;filter.elements.service_type.disabled=!service&&!mixed;filter.elements.handler_name.disabled=!service&&!mixed;filter.elements.salesperson_id.disabled=service;if(brState.dashboardMode==='daily'&&brState.dailyPreview)for(const name of ['brand','salesperson_id','category_field','category_value','service_type','handler_name'])filter.elements[name].disabled=true;
  };
  filter.elements.report.onchange=()=>configure(true);configure();
  filter.onsubmit=event=>{event.preventDefault();const next={category_field:'',category_value:'',service_type:'',handler_name:'',salesperson_id:'',group_by:brState.trendActive?'month':'salesperson',...Object.fromEntries(new FormData(filter))};if(next.date_from>next.date_to){toast('开始日期不能晚于结束日期。',true);return;}if(next.group_by.startsWith('category:')){next.category_field=next.group_by.slice(9);next.group_by='category';}if(next.category_value&&!next.category_field){toast('请先选择分类字段。',true);return;}brState.filters=next;if(brState.dashboardMode==='range')brState.rangeDates={date_from:next.date_from,date_to:next.date_to};render();};
 }
 const periodWindow=$('#br-period-window');if(periodWindow)periodWindow.onsubmit=event=>{event.preventDefault();const count=Number(periodWindow.elements.count.value),max=brState.dashboardMode==='daily'?90:36;if(!Number.isInteger(count)||count<2||count>max){toast('期数须为 2 至 '+max+' 的整数。',true);return;}(brState.periodViews||(brState.periodViews={}))[brState.dashboardMode]=periodWindow.elements.display.value;(brState.periodCounts||(brState.periodCounts={}))[brState.dashboardMode]=count;brState.view='auto';render();};
 const prices=$('#br-price-filter');if(prices)prices.onsubmit=event=>{event.preventDefault();brState.priceQuery=prices.elements.q.value; brState.pricePage=1;render();};
 const month=$('#br-report-month');if(month)month.onchange=()=>{if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(month.value))return;brState.reportMonth=month.value;render();};
 const confirmedDaily=$('#br-confirmed-daily-date');if(confirmedDaily)confirmedDaily.onchange=()=>{if(!confirmedDaily.value)return;brState.confirmedDailyDate=confirmedDaily.value;brState.dailyPreview=false;render();};
 const daily=$('#br-daily-filter');if(daily)daily.onsubmit=event=>{event.preventDefault();brState.dailyDate=daily.elements.day.value;render();};
 mountBusinessRecordsChart();
}
document.addEventListener('click',event=>{
 const button=event.target.closest('[data-br=report-view],[data-br=report-page]');if(!button||button.disabled||state.storeSwitch||!brState.report)return;
 const result=$('#br-report-result');if(!result)return;
 const pageChange=button.dataset.br==='report-page';leaveBusinessRecordsChart();if(pageChange){const page=Number(button.dataset.page);if(!Number.isInteger(page)||page<1)return;(brState.reportPages||(brState.reportPages={}))[button.dataset.view]=page;}else brState.view=button.dataset.view;
 result.innerHTML=brReportResult(brState.report);mountBusinessRecordsChart();
 if(pageChange&&button.dataset.view==='legacy')result.querySelector('details')?.setAttribute('open','');
 const exportButton=$('[data-br=export-report]');if(exportButton)exportButton.textContent=brPresentation(brState.report).type==='details'?'导出来源明细':'导出统计表';
 result.querySelector(`[data-view="${brState.view}"]`)?.focus();
});
document.addEventListener('click',async event=>{
 const el=event.target.closest('[data-br]');if(!el||['report-view','report-page','clear-manual-contract'].includes(el.dataset.br)||el.disabled||state.storeSwitch)return;
 el.disabled=true;try{const action=el.dataset.br;if(action==='defer-form'){if($('#modal form')?.dataset.submitting==='true')throw new Error('正在提交，请等待本次返回结果。');closeModal();}else if(action==='new-contract')await brNewContract();else if(action==='contract-action')await brContractAction(el.dataset.action);else if(action==='new-price')await brNewPrice();else if(action==='import-prices')await brImportPrices();else if(action==='estimate-prices')await brEstimatePrices();else if(action==='price-page'){brState.pricePage=Number(el.dataset.page);await render();}else if(action==='office-report-select')await brOfficeEdit(el.dataset.report);else if(action==='office-filter'){brState.officeFilter=el.dataset.status;state.page=1;await render();}else if(action==='daily-preview'){brState.dailyPreview=!brState.dailyPreview;await render();}else if(action==='confirm-daily')await brConfirmDaily();else if(action==='export-daily')await download(BR_API+'/daily-vehicle-reports/export?'+new URLSearchParams({day:brState.dailyDate||day()}),'车辆更新记录.csv');else if(action==='new-customer')await brNewCustomer();else if(action==='customer-tab'||action==='customer-page')await brChangeCustomerView(action,el);else if(action==='new-after-sales')await brNewAfterSales();else if(action==='edit-settings')await brEditSettings();else if(action==='import-manual')await brImportManual();else if(action==='new-manual'){brState.manualContract=null;await brNewManual();}else if(action==='contract-statistics'){brState.manualContract=brState.detail?.id;await brNewManual();}else if(action==='manual-report-select')await brNewManual(el.dataset.report);else if(action==='manual-detail')await brManualDetail(Number(el.dataset.id));else if(action==='manual-correct'){const r=await api(BR_API+'/manual-reports/'+Number(el.dataset.id));if(!r.can_correct)throw new Error('这份记录已修订或当前岗位不可修订，请重新查询。');await brNewManual(r.report_key,{contractId:r.contract_id,revision:r});}else if(action==='export-report')await download(BR_API+brReportPath()+'/export?'+brReportQuery(brPresentation(brState.report).type==='details'?'details':'summary'),'经营报表.csv');}catch(error){toast(error.message,true);}finally{if(el.isConnected)el.disabled=false;}
});
window.addEventListener('beforeunload',event=>{if(Object.keys(brState.drafts).length){event.preventDefault();event.returnValue='';}});

document.addEventListener('click',event=>{if(!event.target.closest('[data-wfx-discard]'))return;const key=$('#modal form')?.dataset.brForm;if(key)delete brState.drafts[key];},true);
