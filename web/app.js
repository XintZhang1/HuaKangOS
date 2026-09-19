// MAINT_PROTECTED_BEGIN:bootstrap-escaping
'use strict';
// Same-origin UI. No API key, business data or login token is stored in localStorage.
const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const E = escapeHTML;
const state = {user:null,route:'dashboard',page:1,filters:{q:'',state:'',date_from:'',date_to:''},rows:[],total:0,
  storeId:null,stores:[],allStores:[],days:30,end:'',reportId:null,report:null,reportPage:1,reviewStatus:'open',settings:null};
const names = {stores:'门店管理',feedback:'改进意见 / 版本发布',dashboard:'经营总览',vehicles:'新车库存',sales:'门店销售',repairs:'维修工单',policies:'保险保单',cash:'财务流水',reports:'每日审查日报',findings:'数据复核台',users:'账号与权限',audit:'操作日志',settings:'系统与统计口径'};
const roleNames = {admin:'系统管理员',manager:'店长 / 老板',sales:'销售',inventory:'库存管理员',service:'售后 / 保险',finance:'财务',auditor:'复核 / 审计'};
const statuses = {draft:'草稿',submitted:'待审核',approved:'已审核',rejected:'已退回',void:'已作废',available:'可售',reserved:'已预订',sold:'已交车',inactive:'未生效',ordered:'未交车',delivered:'已交车',completed:'已完工',open:'待复核',reviewing:'复核中',confirmed:'确认问题',dismissed:'正常 / 误报',resolved:'已处理',high:'优先复核',medium:'建议复核',low:'提醒',not_requested:'本地规则',disabled:'AI 未开启',unconfigured:'待配密钥',success:'AI 已完成',failed:'AI 失败 · 已保底',pending:'AI 处理中'};
const categories = {sale_collection:'销售收款',repair_collection:'维修收款',premium_collection:'保费代收',commission:'佣金收款',vehicle_purchase:'车辆采购',operating_expense:'经营支出',refund:'客户退款',capital:'出资 / 撤资',loan:'借款 / 还款',transfer:'内部转账'};
const paymentMethods = {bank:'银行',cash:'现金',wechat:'微信',alipay:'支付宝',other:'其他'};
const prefixModules = {V:'vehicles',S:'sales',R:'repairs',P:'policies',C:'cash'};
const icons = {
 dashboard:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
 vehicles:'M4 16H2V9l3-5h14l3 5v7h-2 M6 16h12 M4 9h16 M6 12h2 M16 12h2 M4 16v4h3v-4 M17 16v4h3v-4',
 sales:'M4 5h16v16H4z M8 5V3h8v2 M8 10h8 M8 14h5 M8 18h8',
 repairs:'M14 6a5 5 0 0 0-7 6L2 17l5 5 5-5a5 5 0 0 0 6-7l-4 4-4-4z',
 policies:'M12 2l8 4v6c0 6-8 10-8 10S4 18 4 12V6z M8 12l3 3 5-6',
 cash:'M3 5h18v15H3z M3 8h18 M15 12h6v5h-6z M17 14h1',
 reports:'M5 2h10l4 4v16H5z M15 2v5h4 M8 11h8 M8 15h8 M8 19h5',
 findings:'M12 3l10 18H2z M12 9v5 M12 17v1',
 users:'M16 21v-3c0-4-12-4-12 0v3 M15 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M18 11c3 0 4 2 4 4v5',
 audit:'M12 4a8 8 0 1 1-8 8 M3 3v6h6 M12 7v6l4 2',
 settings:'M12 3v3 M12 18v3 M3 12h3 M18 12h3 M5 5l3 3 M16 16l3 3 M5 19l3-3 M16 8l3-3 M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0'};
const icon = name=>`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${icons[name]||icons.dashboard}" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

// MAINT_PROTECTED_END:bootstrap-escaping
function badge(value, custom){return `<span class="badge ${E(value)}">${E(custom||statuses[value]||value)}</span>`;}
function money(cents=0){return new Intl.NumberFormat('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(cents||0)/100);}
function shortMoney(cents){return Math.abs(cents)>=1000000 ? `${(cents/1000000).toFixed(1)} 万` : money(cents);}
function localToday(){return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());}
function timestamp(value){return value ? new Date(value).toLocaleString('zh-CN',{hour12:false,timeZone:state.settings?.timezone||'Asia/Shanghai'}) : '—';}
// MAINT_PROTECTED_BEGIN:csrf
function csrf(){return document.cookie.split('; ').find(c=>c.startsWith('dealer_csrf='))?.split('=').slice(1).join('=')||'';}

// MAINT_PROTECTED_END:csrf
let toastTimer;
function toast(message,error=false){const node=$('#toast');node.textContent=message;node.className=`visible${error?' error':''}`;clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.className='',6000);}
// MAINT_PROTECTED_BEGIN:transport
async function api(path,{method='GET',body,raw=false}={}){
  const options={method,credentials:'same-origin',headers:{'X-App-Request':'1'}};
  if(state.storeId !== null && !path.startsWith('/api/auth/login')) options.headers['X-Store-ID']=String(state.storeId);
  if(method!=='GET'){options.headers['Content-Type']='application/json';options.headers['X-CSRF-Token']=csrf();options.body=JSON.stringify(body||{});}
  let response;
  try{response=await fetch(path,options);}catch{throw new Error('无法连接本地服务，请确认启动窗口仍在运行。');}
  if(!response.ok){let data;try{data=await response.json();}catch{data={detail:`请求失败 (${response.status})`};}
    if(response.status===401 && !path.includes('/auth/login')){state.user=null;renderLogin();}
    throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));}
  if(raw)return response;
  return response.json();
}

// MAINT_PROTECTED_END:transport
const actBtn=(action,label,extra='',cls='')=>`<button type="button" class="${cls}" data-action="${action}" ${extra}>${E(label)}</button>`;
function heading(title,subtitle,right='',eyebrow='DEALERDESK / WORKSPACE'){
  return `<div class="page-heading"><div><div class="eyebrow">${E(eyebrow)}</div><h1>${E(title)}</h1><p class="subtitle">${E(subtitle)}</p></div>${right}</div>`;
}
function errorPanel(error){return `<div class="inline-error">${E(error.message||error)}</div>`;}
function empty(title,desc){return `<div class="empty"><strong>${E(title)}</strong>${E(desc)}</div>`;}
function pagination(total,page,size=30){return `<div class="pagination"><span>共 ${total} 条 · 第 ${page} / ${Math.max(1,Math.ceil(total/size))} 页</span><div class="row">${actBtn('prev','上一页',page<=1?'disabled':'','small')}${actBtn('next','下一页',page*size>=total?'disabled':'','small')}</div></div>`;}
function getFilters(){const p=new URLSearchParams();for(const [k,v]of Object.entries(state.filters))if(v)p.set(k,v);return p;}
function downloadBlob(blob,filename){const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
// MAINT_PROTECTED_BEGIN:login-navigation
function renderLogin(){
  $('#modal').close();
  $('#app').innerHTML=`<div class="login-shell"><section class="login-art"><div class="brand"><div class="brand-mark">D</div><div><strong>DealerDesk</strong><small>门店经营 · 每日有数</small></div></div><div><h1>把每一笔业务，<br>变成看得见的经营。</h1><p>销售、库存、售后与财务，汇集在同一个工作台。让记录可追溯，让需要复核的问题被及时看见。</p></div><small>LOCAL FIRST &nbsp; / &nbsp; HUMAN REVIEW ALWAYS</small></section><section class="login-right"><form id="login-form" class="login-form"><div class="login-version">DEALERDESK · MULTI-STORE EDITION 0.2</div><h2>欢迎回到经营台</h2><p>使用管理员分配的门店账号登录。</p><label>账号<input name="username" required autocomplete="username" maxlength="40" placeholder="请输入账号"></label><label>密码<input name="password" type="password" required autocomplete="current-password" maxlength="128" placeholder="请输入密码"></label><div id="login-error" class="form-error" role="alert"></div><button class="primary" type="submit">登录工作台 →</button><div class="login-note">首次使用需在启动终端创建管理员。<br>本地服务运行期间，数据保存在你的数据库中。</div></form></section></div>`;
  $('#login-form').onsubmit=async event=>{event.preventDefault();const button=$('button',event.currentTarget);button.disabled=true;$('#login-error').textContent='';
    try{const fd=new FormData(event.currentTarget);state.user=await api('/api/auth/login',{method:'POST',body:Object.fromEntries(fd)});await boot();}
    catch(error){$('#login-error').textContent=error.message;}finally{button.disabled=false;}};
}
function shell(){
  const u=state.user;
  const nav=key=>`<button class="nav-item ${state.route===key?'active':''}" data-action="nav" data-route="${key}">${icon(key)}<span>${names[key]}</span></button>`;
  $('#app').innerHTML=`<div class="app-shell"><aside class="sidebar"><div class="brand"><div class="brand-mark">D</div><div><strong>DealerDesk</strong><small>门店经营工作台</small></div></div>${u.can_report?nav('dashboard'):''}<div class="nav-group">BUSINESS · 业务数据</div>${['sales','vehicles','repairs','policies','cash'].filter(x=>u.read_modules.includes(x)).map(nav).join('')}${u.can_report?`<div class="nav-group">REVIEW · 经营复核</div>${nav('reports')}${nav('findings')}`:''}<div class="nav-group">WORKSPACE · 工作空间</div>${u.can_users?nav('stores'):''}${u.can_users?nav('users'):''}${nav('feedback')}${u.can_audit?nav('audit'):''}${u.can_report?nav('settings'):''}<div class="sidebar-bottom"><strong><span class="dot"></span>多门店 · 授权数据空间</strong>人工确认，程序留痕。<br>v0.2.0 · CNY</div></aside><div class="workarea"><header class="topbar">${actBtn('mobile-menu','☰','','mobile-menu ghost')}<div class="breadcrumb">工作空间 &nbsp; / &nbsp; <strong>${E(names[state.route])}</strong></div><div class="topbar-right">${storeSelector()}<div class="user-menu"><span class="avatar">${E(u.display_name.slice(0,1))}</span><span class="user-text">${E(u.display_name)}<small>${E(u.role_label)}</small></span></div>${actBtn('password','改密','','small ghost')}${actBtn('logout','退出','','small ghost')}</div></header><main id="main"><div class="loading-line">正在读取门店数据…</div></main></div></div>`;
}
async function boot(){
  state.storeId=state.user.active_store_id; state.stores=state.user.stores||[];
  state.end=localToday();
  state.route=state.user.can_report?'dashboard':state.user.read_modules.includes('sales')?'sales':state.user.read_modules[0];
  shell();
  if(state.user.must_change_password){$('#main').innerHTML=heading('先设置你的个人密码','首次登录需修改管理员分配的临时密码。');passwordDialog(true);return;}
  if(state.user.can_report){try{state.settings=await api('/api/settings');state.end=state.settings.today;}catch(error){toast(error.message,true);}}
  await renderPage();
}
async function navigate(route){
  state.route=route;state.page=1;state.filters={q:'',state:'',date_from:'',date_to:''};shell();await renderPage();
}
let renderSequence=0;

// MAINT_PROTECTED_END:login-navigation
async function renderPage(){
  const sequence=++renderSequence;
  const node=$('#main');if(!node)return;
  ensureVizNav();
  node.innerHTML='<div class="loading-line">正在读取门店数据…</div>';
  try{
    let html;
    if(state.route==='dashboard')html=await dashboardPage();
    else if(state.route==='viz')html=await vizPage();
    else if(['vehicles','sales','repairs','policies','cash'].includes(state.route))html=await recordsPage();
    else if(state.route==='reports')html=await reportsPage();
    else if(state.route==='findings')html=await findingsPage();
    else if(state.route==='stores')html=await storesPage();
    else if(state.route==='feedback')html=await feedbackPage();
    else if(state.route==='users')html=await usersPage();
    else if(state.route==='audit')html=await auditPage();
    else html=await settingsPage();
    if(sequence===renderSequence&&state.user){node.innerHTML=html;if(state.route==='viz')drawVizCharts();}
  }catch(error){if(sequence===renderSequence&&state.user)node.innerHTML=errorPanel(error);}
}
function kpi(label,value,foot,accent=false,unit='CNY'){
  return `<div class="kpi ${accent?'accent':''}"><div class="kpi-label">${E(label)}<span class="unit">${unit}</span></div><div class="kpi-value">${value}</div><div class="kpi-foot">${foot}</div></div>`;
}
function chartBars(series){
  const width=770,height=240,left=48,right=12,top=25,bottom=32;
  const maximum=Math.max(...series.map(r=>r.delivery_amount_cents),1000000);
  const plotH=height-top-bottom,plotW=width-left-right,gap=plotW/series.length,barW=Math.max(2,gap*.52);
  let body='';
  for(let i=0;i<=3;i++){const y=top+plotH*i/3;body+=`<line class="axis" x1="${left}" x2="${width-right}" y1="${y}" y2="${y}"/><text x="${left-8}" y="${y+4}" text-anchor="end">${(maximum*(1-i/3)/1000000).toFixed(0)}万</text>`;}
  series.forEach((row,i)=>{const h=row.delivery_amount_cents/maximum*plotH;const x=left+i*gap+(gap-barW)/2;
    body+=`<rect class="bar" x="${x.toFixed(2)}" y="${(top+plotH-h).toFixed(2)}" width="${barW.toFixed(2)}" height="${Math.max(h,0).toFixed(2)}" rx="2"><title>${row.date}：交付 ${row.delivery_count} 台，¥${money(row.delivery_amount_cents)}</title></rect>`;
    if(i===0||i===series.length-1||i%Math.max(1,Math.floor(series.length/6))===0)body+=`<text x="${(x+barW/2).toFixed(2)}" y="${height-10}" text-anchor="middle">${row.date.slice(5)}</text>`;
  });
  return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="所选期间每日交付合同金额柱状图">${body}</svg>`;
}
function stockDonut(t){
  const radius=65,c=2*Math.PI*radius,ratio=t.stock_count?t.available_count/t.stock_count:0;
  return `<svg class="chart" viewBox="0 0 320 225" role="img" aria-label="在库车辆可售与已预订占比"><circle class="donut-bg" cx="160" cy="108" r="${radius}" stroke-width="17"/><circle class="donut-secondary" cx="160" cy="108" r="${radius}" stroke-width="17"/><circle class="donut-main" cx="160" cy="108" r="${radius}" stroke-width="17" stroke-dasharray="${c*ratio} ${c}" transform="rotate(-90 160 108)"/><text class="donut-number" x="160" y="108" text-anchor="middle">${t.stock_count}</text><text class="donut-label" x="160" y="132" text-anchor="middle">在库车辆 / 台</text></svg><div class="legend"><span><i class="legend-dot"></i>可售 ${t.available_count}</span><span><i class="legend-dot secondary"></i>已预订 ${t.reserved_count}</span></div>`;
}
async function dashboardPage(){
  const d=await api(`/api/dashboard?end=${state.end}&days=${state.days}`),t=d.totals;
  const controls=`<div class="date-controls"><select id="dashboard-days" aria-label="看板统计期间">${[[1,'当日'],[7,'近 7 日'],[30,'近 30 日'],[90,'近 90 日']].map(([v,l])=>`<option value="${v}" ${v===state.days?'selected':''}>${l}</option>`).join('')}</select><input id="dashboard-end" type="date" aria-label="看板结束日期" value="${state.end}" max="${localToday()}">${actBtn('dashboard-refresh','更新','','small')}</div>`;
  const monetary=(v)=>`<span class="currency">¥</span>${money(v)}`;
  return heading('经营总览',`${d.start_date} — ${d.end_date} · 流量按所选期间，库存与待收款按期末有效记录`,controls,'STORE OPERATIONS / 经营全景')+
    (state.settings?.demo_database?'<div class="banner warning">演示数据空间：本库含虚构样例。正式录入前，请按照 README 建立独立空库，勿混用。</div>':'')+
    `<div class="kpi-grid">${kpi('交付合同金额',monetary(t.delivery_amount_cents),`已审核交车 <span class="positive">${t.delivery_count} 台</span>`,true)}
    ${kpi('维修结算金额',monetary(t.repair_amount_cents),`已审核完工 ${t.repair_completed_count} 单`)}
    ${kpi('销售 + 维修毛差',monetary(t.gross_difference_cents),'基于录入直接成本 · 非会计净利润')}
    ${kpi('外部净现金流',monetary(t.net_cash_cents),`流入 ${shortMoney(t.cash_in_cents)} / 流出 ${shortMoney(t.cash_out_cents)}`)}
    ${kpi('在库车辆',`${t.stock_count}<span class="currency"> 台</span>`,`可售 ${t.available_count} · 已预订 ${t.reserved_count}`,false,'UNITS')}
    ${kpi('库存成本占用',monetary(t.stock_cost_cents),`超 ${state.settings?.rules.inventory_aging_days||90} 天库存 ${t.aging_stock_count} 台`)}
    ${kpi('已交付 / 完工待收款',monetary(t.sales_receivable_cents+t.repair_receivable_cents),'销售与维修净待收 · 不含未交付订金')}
    ${kpi('新保单预计佣金',monetary(t.expected_commission_cents),`保费 ${shortMoney(t.policy_premium_cents)} 单列，不混作营收`)}</div>
    <div class="chart-grid"><section class="panel"><div class="panel-head"><div><h2>每日交付走势</h2><small>按交车日统计 · 单据必须已审核</small></div>${badge('approved',`${d.days} 天`)}</div>${chartBars(d.series)}</section><section class="panel"><div class="panel-head"><div><h2>库存结构</h2><small>期末在库，不含已经交车的车辆</small></div></div>${stockDonut(t)}</section></div>
    <div class="split-panels"><section class="panel"><div class="panel-head"><div><h2>值得关注的信号</h2><small>规则实时计算；生成日报后进入复核台</small></div>${actBtn('nav','前往日报 →','data-route="reports"','small ghost')}</div>${[['high','优先复核线索','金额、凭证和关联关系需要核对'],['medium','建议复核线索','账期、折扣、库龄与业务状态'],['low','管理提醒','待审核或需解释的日期差异']].map(([s,title,desc])=>`<div class="attention-row"><div><strong>${title}</strong><small>${desc}</small></div>${badge(s,`${d.rule_counts[s]||0} 项`)}</div>`).join('')}</section>
    <section class="panel"><div class="panel-head"><div><h2>今日工作入口</h2><small>录入、审批、复核，各有记录</small></div></div><div class="attention-row"><div><strong>${t.pending_approval_count} 份单据等待审核</strong><small>待审核金额不会进入已审核经营指标</small></div>${actBtn('nav','查看单据','data-route="sales"','small')}</div><div class="attention-row"><div><strong>日报里的数字由程序计算</strong><small>DeepSeek 整理摘要与建议，不直接改账</small></div>${actBtn('nav','生成日报','data-route="reports"','small primary')}</div><div class="attention-row"><div><strong>所有变更都有操作留痕</strong><small>数据库本体与备份仍需限制访问</small></div>${state.user.can_audit?actBtn('nav','查看日志','data-route="audit"','small'):badge('approved','权限控制')}</div></section></div>${storeComparison(d)}<div class="basis">${E(d.basis)}</div>`;
}
const moduleDescriptions={vehicles:'一车一 VIN。生效销售订单自动预订库存，确认交车后自动出库。',sales:'管理订单与实际交车。收款单独录入财务流水，并关联销售单据。',repairs:'报修、工时配件、优惠与完工管理。保险维修可关联具体保单。',policies:'保费与预计佣金分别记录。保费代收不会自动当作门店收入。',cash:'录入经营收付款与资金往来。内部转账只录一笔，门店总收支中自动排除。'};
// MAINT_PROTECTED_BEGIN:record-authority
function canEdit(row,module){return state.user.write_modules.includes(module)&&(['admin','manager'].includes(state.user.role)||row.created_by===state.user.id);}
function rowActions(row,module){
  const attrs=`data-id="${row.id}" data-module="${module}"`;
  let out=actBtn('detail','详情',attrs,'small ghost');
  if(['draft','rejected'].includes(row.approval_state)&&canEdit(row,module))out+=actBtn('edit','编辑',attrs,'small')+actBtn('workflow','提交',attrs+' data-workflow="submit"','small');
  if(row.approval_state==='submitted'&&state.user.can_approve)out+=actBtn('workflow','通过',attrs+' data-workflow="approve"','small')+actBtn('workflow','退回',attrs+' data-workflow="reject"','small');
  if(row.approval_state==='approved'&&canEdit(row,module)&&((module==='sales'&&row.sale_stage==='ordered')||(module==='repairs'&&row.repair_stage==='open')))out+=actBtn('workflow',module==='sales'?'确认交车':'确认完工',attrs+' data-workflow="advance"','small');
  if(state.user.can_approve&&row.approval_state!=='void')out+=actBtn('workflow','作废',attrs+' data-workflow="void"','small ghost');
  return `<div class="actions">${out}</div>`;
}

// MAINT_PROTECTED_END:record-authority
function recordColumns(module){
  const doc=r=>`<strong>${E(r.doc_no)}</strong><small>ID ${r.id} · ${E(r.ref)}</small>`;
  const dateCell=r=>E(r.business_date);
  const columns={
    vehicles:[['入库单',doc],['车辆信息',r=>`<strong>${E(r.brand)} · ${E(r.model)}</strong><small class="mono">${E(r.vin)}</small>`],['入库日',dateCell],['库存状态',r=>badge(r.stock_state)],...(state.user.role!=='sales'?[['采购成本',r=>`<span class="amount">¥${money(r.purchase_cost_cents)}</span>`]]:[]),['挂牌价',r=>`¥${money(r.list_price_cents)}`]],
    sales:[['销售单',doc],['客户 / 销售顾问',r=>`<strong>${E(r.customer_name)}</strong><small>${E(r.salesperson)}</small>`],['关联车辆',r=>`<span class="mono">${E(r.vehicle_label)}</span>`],['订单日',dateCell],['交车状态',r=>badge(r.sale_stage)+(r.delivery_date?`<small>${r.delivery_date}</small>`:'')],['合同金额',r=>`<span class="amount">¥${money(r.contract_amount_cents)}</span>`]],
    repairs:[['维修工单',doc],['车辆 / 客户',r=>`<strong>${E(r.plate_number)}</strong><small>${E(r.customer_name)}</small>`],['服务顾问',r=>E(r.service_advisor)],['报修日',dateCell],['进度',r=>badge(r.repair_stage,r.repair_stage==='open'?'维修中':'已完工')],['结算金额',r=>`<span class="amount">¥${money(r.billed_amount_cents)}</span>`]],
    policies:[['录入单',doc],['保单号 / 保险机构',r=>`<strong>${E(r.policy_number)}</strong><small>${E(r.insurer)}</small>`],['车辆 / 客户',r=>`<strong>${E(r.plate_number)}</strong><small>${E(r.customer_name)}</small>`],['到期日',r=>E(r.end_date)],['保费',r=>`¥${money(r.premium_cents)}`],['预计佣金',r=>`<span class="amount">¥${money(r.commission_cents)}</span>`]],
    cash:[['流水单',doc],['发生日',dateCell],['收支分类',r=>`${E(categories[r.category])}<small>${r.related_type!=='none'?E(names[r.related_type])+' #'+r.related_id:'无业务关联'}</small>`],['账户 / 凭证',r=>`${E(r.account)}<small>${E(r.voucher_no)}</small>`],['方向',r=>badge(r.direction==='in'?'approved':'low',r.category==='transfer'?'内部转出':r.direction==='in'?'流入':'流出')],['金额',r=>`<span class="amount ${r.direction==='in'?'text-teal':''}">¥${money(r.amount_cents)}</span>`]]
  };
  return [...columns[module],['审核状态',r=>badge(r.approval_state)],['操作',r=>rowActions(r,module)]];
}
async function recordsPage(){
  const module=state.route,params=getFilters();params.set('page',state.page);
  const data=await api(`/api/records/${module}?${params}`);state.rows=data.items;state.total=data.total;
  const cols=recordColumns(module),f=state.filters;
  // P4 批量填单入口：AI 只生成待复核草稿，写入仍需人工逐条确认（实现见文件末尾 batch-* 部分）。
  const aiOff=!!state.settings&&state.settings.ai_allowed===false;
  const batchBtn=actBtn('batch-entry',aiOff?'批量填写（AI 未开启）':'批量填写',
    `data-module="${module}"${aiOff?' disabled title="服务器未开启 AI 外发（ALLOW_AI_EXTERNAL）：批量填单不可用，手工录入不受影响。"':''}`,'');
  const headingRight=state.user.write_modules.includes(module)?`<div class="row wrap">${batchBtn}${actBtn('new','＋ 新增录入',`data-module="${module}"`,'primary')}</div>`:'';
  const toolbar=`<div class="toolbar"><input id="filter-q" class="search" aria-label="搜索单据" placeholder="搜索编号、客户或车辆…" value="${E(f.q)}" maxlength="100"><select id="filter-state" aria-label="审核状态"><option value="">全部审核状态</option>${['draft','submitted','approved','rejected','void'].map(v=>`<option value="${v}" ${v===f.state?'selected':''}>${statuses[v]}</option>`).join('')}</select><input id="filter-start" type="date" aria-label="业务日期起" value="${f.date_from}"><span class="muted">至</span><input id="filter-end" type="date" aria-label="业务日期止" value="${f.date_to}">${actBtn('filter','查询')}<span class="spacer"></span>${state.user.can_report?actBtn('export','导出 CSV','','small'):''}</div>`;
  return heading(names[module],moduleDescriptions[module],headingRight)+toolbar+
    `<section class="panel table-panel">${data.items.length?`<div class="table-scroll"><table><thead><tr>${cols.map(c=>`<th>${c[0]}</th>`).join('')}</tr></thead><tbody>${data.items.map(r=>`<tr>${cols.map(c=>`<td>${c[1](r)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:empty('没有符合条件的单据','可以调整筛选条件，或新增一条业务记录。')}${pagination(data.total,state.page)}</section><div class="basis">${module==='cash'?'这是经营流水台账，不是复式记账总账。真实退款请新增退款支出；“作废”仅用于纠正错录，不能代替真实资金冲回。':'草稿 → 提交 → 审核。已审核金额锁定；交车与完工只能推进业务进度，不能修改原单金额。'} 搜索与导出日期按本模块的业务发生日，不按交车/完工日。</div>`;
}
const field=(name,label,type='text',extra={})=>({name,label,type,...extra});
const moneyField=(name,label,required=true)=>field(name,label,'money',{required,default:'0.00'});
const commonFields=[field('doc_no','内部单据号','text',{required:true,max:60}),field('business_date','业务发生日期','date',{required:true,default:'today'})];
const customers=[field('customer_name','客户姓名 / 简称','text',{required:true,max:100}),field('customer_phone','联系电话（可选）','tel',{max:30})];
const moduleFields={
 vehicles:[...commonFields,field('vin','VIN 车架号（17位）','text',{required:true,max:17}),field('brand','品牌','text',{required:true,max:80}),field('model','车型 / 配置','text',{required:true,max:120}),field('color','车身颜色'),field('supplier','供应商（可选）'),field('location','库位（可选）'),moneyField('purchase_cost','采购成本（元）'),moneyField('list_price','挂牌价格（元）')],
 sales:[...commonFields,field('vehicle_id','关联已审核库存','lookup',{required:true,module:'vehicles',hint:'输入 VIN / 车型检索，选择记录，或直接填写库存 ID。'}),field('salesperson','销售顾问','text',{required:true,max:80}),...customers,field('sale_stage','交车状态','select',{options:{ordered:'未交车',delivered:'已交车'},default:'ordered'}),field('delivery_date','实际交车日（已交车必填）','date'),moneyField('contract_amount','合同总金额（元）')],
 repairs:[...commonFields,field('plate_number','车牌号','text',{required:true,max:30}),field('service_advisor','服务顾问','text',{required:true,max:80}),...customers,field('repair_type','工单类型','select',{options:{maintenance:'保养',repair:'维修',insurance:'保险维修'},default:'maintenance'}),field('repair_stage','工单进度','select',{options:{open:'维修中',completed:'已完工'},default:'open'}),field('policy_id','关联保单（保险维修建议填）','lookup',{module:'policies'}),field('due_date','预计完工日期','date'),field('completion_date','实际完工日期（已完工必填）','date'),moneyField('labor_amount','工时费（元）'),moneyField('parts_amount','配件费（元）'),moneyField('discount','优惠金额（元）'),moneyField('cost_amount','直接成本（元）')],
 policies:[...commonFields,field('policy_number','保险公司保单号','text',{required:true,max:80}),field('insurer','保险机构','text',{required:true,max:100}),field('plate_number','车牌号','text',{required:true,max:30}),field('policy_type','险种','select',{options:{commercial:'商业险',compulsory:'交强险',combined:'组合保单'},default:'commercial'}),...customers,field('start_date','保险生效日期','date',{required:true,default:'today'}),field('end_date','保险到期日期','date',{required:true,default:'year'}),moneyField('premium','保费金额（元）'),moneyField('commission','预计佣金（元）')],
 cash:[...commonFields,field('direction','收支方向','select',{options:{in:'流入',out:'流出'},default:'in'}),field('category','收支分类','select',{options:categories,default:'sale_collection'}),moneyField('amount','流水金额（元）'),field('payment_method','支付方式','select',{options:paymentMethods,default:'bank'}),field('account','门店账户简称','text',{required:true,max:100,hint:'例如“基本户”“微信收款”；请勿录入完整银行账号。'}),field('counter_account','转入账户（仅内部转账填写）'),field('counterparty','交易对方简称（可选）'),field('voucher_no','银行流水号 / 原始凭证号','text',{required:true,max:100}),field('related_type','关联业务类型','select',{options:{none:'无关联',sales:'销售单',repairs:'维修单',policies:'保单',vehicles:'入库单'},default:'sales'}),field('related_id','关联已审核业务','lookup',{module:'sales',hint:'输入单据号检索并选择，或填写对应记录 ID。'})]
};
const noteField=field('note','备注（不要填写身份证号、银行卡号等敏感信息）','textarea',{max:2000,wide:true});
function defaultValue(f,module){
  if(f.name==='doc_no'){const p={vehicles:'RK',sales:'XS',repairs:'WX',policies:'BD',cash:'CW'}[module];const random=crypto.getRandomValues(new Uint32Array(1))[0].toString(16).slice(0,6).toUpperCase();return `${p}-${localToday().replaceAll('-','')}-${random}`;}
  if(f.default==='today')return localToday();
  if(f.default==='year'){const d=new Date();d.setFullYear(d.getFullYear()+1);return d.toISOString().slice(0,10);}
  return f.default??'';
}
function renderField(f,value){
  const attrs=`name="${f.name}" id="field-${f.name}" ${f.required?'required':''} ${f.max?`maxlength="${f.max}"`:''}`;
  let input;
  if(f.type==='select')input=`<select ${attrs}>${Object.entries(f.options).map(([v,l])=>`<option value="${v}" ${String(value)===v?'selected':''}>${E(l)}</option>`).join('')}</select>`;
  else if(f.type==='textarea')input=`<textarea ${attrs}>${E(value)}</textarea>`;
  else if(f.type==='lookup')input=`<input ${attrs} value="${E(value)}" list="lookup-${f.name}" data-lookup="${f.module}" autocomplete="off" placeholder="输入关键词搜索，或填记录 ID"><datalist id="lookup-${f.name}"></datalist>`;
  else input=`<input ${attrs} type="${f.type==='money'?'number':f.type}" ${f.type==='money'?'step="0.01" min="0" max="9999999999.99"':''} value="${E(value)}">`;
  return `<label class="field ${f.wide?'wide':''}"><span>${E(f.label)}${f.required?' <b class="required">*</b>':''}</span>${input}${f.hint?`<small>${E(f.hint)}</small>`:''}</label>`;
}
function openModal(title,subtitle,body,footer='',form=false){
  const modal=$('#modal');
  modal.innerHTML=`${form?'<form id="modal-form">':''}<div class="modal-head"><div><h2 id="modal-title">${E(title)}</h2>${subtitle?`<p>${E(subtitle)}</p>`:''}</div>${actBtn('close-modal','×','','close-modal')}</div><div class="modal-body">${body}<div id="modal-error" class="form-error" role="alert"></div></div><div class="modal-footer">${footer||actBtn('close-modal','关闭')}</div>${form?'</form>':''}`;
  if(!modal.open)modal.showModal();
  if(state.user?.must_change_password)modal.oncancel=event=>event.preventDefault();else modal.oncancel=null;
  return modal;
}
function bindForm(handler){
  $('#modal-form').onsubmit=async event=>{event.preventDefault();const buttons=$$('button[type=submit]',$('#modal'));buttons.forEach(b=>b.disabled=true);$('#modal-error').textContent='';
    try{await handler(new FormData(event.currentTarget),event.submitter?.value);}
    catch(error){$('#modal-error').textContent=error.message;}
    finally{buttons.forEach(b=>b.disabled=false);}};
}
// MAINT_PROTECTED_BEGIN:record-submit
function readRecordForm(fd,module){
  const values={};for(const f of [...moduleFields[module],noteField]){const raw=fd.get(f.name);const value=raw==null?'':String(raw).trim();
    if(f.type==='lookup'){if(!value){values[f.name]=null;}else{const match=value.match(/^\d+(?=\s|$)/);if(!match)throw new Error(`${f.label}：请从下拉建议中选择或输入正确的记录 ID。`);values[f.name]=Number(match[0]);}}
    else if(f.type==='date')values[f.name]=value||null;
    else if(f.type==='money')values[f.name]=value||'0.00';
    else values[f.name]=value;
  }return values;
}
function initializeLookups(){
  $$('[data-lookup]',$('#modal')).forEach(input=>{
    let timer,serial=0;
    const update=async()=>{if(input.disabled)return;const token=++serial;const module=input.dataset.lookup;const query=input.value.includes(' · ')?input.value.split(' · ')[0]:input.value;
      try{const data=await api(`/api/lookup/${module}?q=${encodeURIComponent(query)}`);if(token===serial){const list=$(`#lookup-${input.name}`);if(list)list.innerHTML=data.items.map(x=>`<option value="${E(x.label)}"></option>`).join('');}}
      catch(error){toast(error.message,true);}};
    input.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(update,250);});input.addEventListener('focus',update);
  });
  const related=$('#field-related_type');if(related){const sync=()=>{const input=$('#field-related_id');input.disabled=related.value==='none';input.dataset.lookup=related.value==='none'?'sales':related.value;if(input.disabled)input.value='';};related.addEventListener('change',()=>{$('#field-related_id').value='';sync();});sync();}
  const category=$('#field-category');if(category)category.addEventListener('change',()=>{
    const relation={sale_collection:['in','sales'],repair_collection:['in','repairs'],premium_collection:['in','policies'],commission:['in','policies'],vehicle_purchase:['out','vehicles'],operating_expense:['out','none'],transfer:['out','none'],capital:['in','none'],loan:['in','none']};
    if(relation[category.value]){const [direction,type]=relation[category.value];$('#field-direction').value=direction;$('#field-related_type').value=type;$('#field-related_type').dispatchEvent(new Event('change'));}
    else if(category.value==='refund')$('#field-direction').value='out';
    if(category.value!=='transfer')$('#field-counter_account').value='';
  });
}
async function recordDialog(module,id=null){
  const row=id?await api(`/api/records/${module}/${id}`):null;
  const fields=[...moduleFields[module],noteField];
  openModal(`${row?'编辑':'新增'}${names[module]}`,row?`${row.doc_no} · 数据版本 ${row.version}`:'保存后为草稿，提交并审核通过后计入经营汇总。',
    `<div class="form-grid">${fields.map(f=>renderField(f,row?row[f.name]??'':defaultValue(f,module))).join('')}</div>`,
    '<span class="hint">金额单位：人民币元</span>'+actBtn('close-modal','取消')+'<button type="submit" value="draft">保存草稿</button><button class="primary" type="submit" value="submit">保存并提交</button>',true);
  initializeLookups();
  bindForm(async(fd,intent)=>{
    const data=readRecordForm(fd,module);
    const saved=await api(`/api/records/${module}${row?'/'+row.id:''}`,{method:row?'PUT':'POST',body:row?{version:row.version,data}:data});
    if(intent==='submit'){
      try{await api(`/api/records/${module}/${saved.id}/actions/submit`,{method:'POST',body:{version:saved.version,reason:'录入后提交审核'}});}
      catch(error){$('#modal').close();await renderPage();toast('草稿已保存，但提交失败：'+error.message,true);return;}
    }
    $('#modal').close();toast(intent==='submit'?'已保存并提交审核。':'草稿已保存。');await renderPage();
  });
}
async function workflowDialog(module,id,action){
  const row=await api(`/api/records/${module}/${id}`);
  const titles={submit:'提交审核',approve:'审核通过',reject:'退回修改',void:'作废单据',advance:module==='sales'?'确认交车':'确认完工'};
  const description=action==='void'?'作废用于纠正错录，不等于退款或退车；不会删除原始单据，必须说明原因。':action==='approve'?'审核后金额不可直接修改。管理员自审会被专门标记留痕。':action==='advance'?'本操作仅记录实际完成日期，不修改金额。':'操作及说明会保存到审计日志。';
  openModal(titles[action],`${row.doc_no} · 版本 ${row.version}`,
    `<div class="banner ${action==='void'?'warning':''}">${description}</div>${action==='advance'?renderField(field('effective_date','实际完成日期','date',{required:true}),localToday()):''}${renderField(field('reason','操作说明（必填）','textarea',{required:true,max:1000}),action==='submit'?'已完成录入，提交审核':'')}`,
    actBtn('close-modal','取消')+`<button type="submit" class="${action==='void'?'danger':'primary'}">${titles[action]}</button>`,true);
  bindForm(async fd=>{const body={version:row.version,reason:fd.get('reason'),effective_date:fd.get('effective_date')||null};await api(`/api/records/${module}/${id}/actions/${action}`,{method:'POST',body});$('#modal').close();toast('操作已完成并留痕。');await renderPage();});
}

// MAINT_PROTECTED_END:record-submit
async function detailDialog(module,id){
  const r=await api(`/api/records/${module}/${id}`);
  const map=Object.fromEntries([...moduleFields[module],noteField].map(f=>[f.name,f.label]));
  const extras={approval_state:'审核状态',stock_state:'库存状态',created_by:'录入用户 ID',created_at:'录入时间',updated_at:'更新时间',version:'数据版本',purchase_cost_snapshot:'审核时采购成本快照（元）',billed_amount:'维修结算金额（元）'};
  const data={...map,...extras};
  const body=Object.entries(data).filter(([k])=>k in r).map(([k,label])=>{
    let value=r[k];if(k.endsWith('_at'))value=timestamp(value);if(k==='approval_state'||k==='stock_state')value=statuses[value]||value;
    const f=moduleFields[module].find(f=>f.name===k);if(f?.type==='select')value=f.options[value]||value;
    return `<div class="definition"><div class="label">${E(label)}</div><div class="value">${E(value??'—')}</div></div>`;
  }).join('');
  openModal(`${names[module]} · ${r.ref}`,r.doc_no,body);
}
const evidenceNames={age_days:'库龄 / 天',threshold_days:'阈值 / 天',purchase_cost_cents:'采购成本',contract_amount_cents:'合同金额',cost_snapshot_cents:'成本快照',gross_difference_cents:'毛差',threshold_percent:'比例阈值 / %',list_price_cents:'挂牌价',net_collected_cents:'累计净收款',excess_cents:'超收金额',uncollected_cents:'待收金额',days_since_delivery:'交车后天数',open_days:'报修天数',due_date:'预计完工日',billed_amount_cents:'结算金额',cost_amount_cents:'直接成本',before_discount_cents:'优惠前金额',discount_cents:'优惠金额',days_since_completion:'完工后天数',policy_ref:'关联保单',date_within_policy:'报修日处于保险期间',plate_matches:'车牌一致',premium_cents:'保费',commission_cents:'预计佣金',record_refs:'关联流水',record_count:'记录数',amount_cents:'金额',direction:'收支方向',threshold_cents:'金额阈值',payment_date:'流水日期',related_date:'业务日期',related_ref:'关联记录',business_date:'业务日期',waiting_business_days:'距业务日期天数'};
function evidenceText(evidence){return Object.entries(evidence||{}).map(([k,v])=>{
  let text=k.endsWith('_cents')?'¥'+money(v):Array.isArray(v)?v.join('、'):typeof v==='boolean'?(v?'是':'否'):k==='direction'?(v==='in'?'流入':'流出'):v??'未填写';
  return `${evidenceNames[k]||k}：${text}`;
}).join('；')||'请核对关联业务资料。';}
function reportBody(r){
  const s=r.snapshot,m=s.metrics,ai=r.ai_result;
  let content=`<section class="panel"><div class="panel-head"><div><div class="eyebrow">DAILY REVIEW / ${E(r.business_date)}</div><h2>经营汇总与规则审查</h2><small>生成于 ${timestamp(r.generated_at)} · 数据版本 ${r.source_revision} · 日报 #${r.id}</small></div>${badge(r.ai_status)}</div>${s.provisional?'<div class="banner warning">当日仍在进行中，这是一份实时快照，不是最终日结。</div>':''}${r.stale?'<div class="banner warning">生成后数据库内出现过业务变更（不一定影响本日）。此处保留旧快照；需要最新口径时请重新生成。</div>':''}<p class="report-summary">${E(r.deterministic_summary)}</p><div class="report-kpis">${[['交付合同金额',m.delivery_amount_cents],['维修结算金额',m.repair_amount_cents],['外部净现金流',m.net_cash_cents]].map(([l,v])=>`<div><small>${l}</small><div class="value">¥${money(v)}</div></div>`).join('')}</div></section>`;
  content+=`<section class="panel"><div class="panel-head"><div class="row"><span class="ai-mark">DEEPSEEK</span><h2>摘要与辅助复核建议</h2></div>${ai?'<small>模型观点 · 未经人工核实</small>':''}</div>`;
  if(ai){content+=`<p class="report-summary">${E(ai.summary)}</p>${ai.highlights.map(h=>`<div class="insight"><p>${E(h)}</p></div>`).join('')}${ai.reviews.length?`<h3>模型提出的待核实线索</h3>${ai.reviews.map(v=>`<div class="insight"><div class="row">${actBtn('ref',v.ref,`data-ref="${E(v.ref)}"`,'small')}${badge('medium','AI 假设')}</div><p>${E(v.reason)}</p><small>建议核对：${E(v.action)}</small></div>`).join('')}`:'<p class="subtitle">模型未提出额外复核线索。不能据此保证不存在问题。</p>'}<div class="basis">${E(ai.limitations)}</div>`;}
  else content+=`<p class="subtitle">${E(r.ai_error||(r.ai_status==='pending'?'模型请求尚未完成，或运行曾中断。规则日报已保存；可以重新生成 / 重试 AI。':'本次仅使用本地规则生成摘要，没有调用外部模型。'))}</p>`;
  content+=`<div class="basis">AI 明细覆盖 ${s.ai_record_count} / ${s.record_count_before_ai_cap} 条；省略 ${s.ai_omitted_record_count} 条明细、${s.ai_omitted_finding_count} 条规则线索。程序汇总和本地规则不受此截断影响。模型无权修改业务数据。</div></section>`;
  content+=`<section class="panel"><div class="panel-head"><div><h2>本次规则命中的复核线索</h2><small>每条提示都有对应记录和检查依据</small></div>${actBtn('nav','进入复核台','data-route="findings"','small')}</div>${s.rule_findings.length?s.rule_findings.map(f=>`<div class="insight"><div class="row wrap">${badge(f.severity)}<strong>${E(f.title)}</strong>${actBtn('ref',f.ref,`data-ref="${E(f.ref)}"`,'small ghost')}</div><p>${E(evidenceText(f.evidence))}</p><small>${E(f.suggested_action)}</small></div>`).join(''):empty('本次没有规则命中','规则覆盖有限，不等于独立审计通过。')}</section><div class="basis">${E(s.basis)}</div>`;
  return content;
}
async function reportsPage(){
  const data=await api(`/api/reports?page=${state.reportPage}`);
  if(!state.reportId&&data.items.length)state.reportId=data.items[0].id;
  const r=state.reportId?await api(`/api/reports/${state.reportId}`):null;state.report=r;
  const ready=state.settings?.ai_allowed&&state.settings?.ai_key_configured;
  return heading('每日审查日报','程序汇总，规则找线索，DeepSeek 整理摘要，最后由人复核。',r?actBtn('download-report','导出当前日报','','small'):'','DAILY INTELLIGENCE / 每日复核')+
    `<div class="toolbar"><input id="report-date" type="date" aria-label="日报业务日期" value="${state.end}" max="${localToday()}"><label class="checkbox-label"><input id="report-ai" type="checkbox" ${ready?'':'disabled'}>使用 DeepSeek（脱敏外发，消耗 API 额度）</label>${actBtn('generate-report','汇总并审查','','primary')}${actBtn('preview-report','预览将外发的数据')}<span id="report-progress" class="subtitle"></span></div>${!ready?'<div class="banner">当前为本地规则模式。启用 AI 需在 .env 中设置 ALLOW_AI_EXTERNAL=true 和 DEEPSEEK_API_KEY，并重启服务；前端不会保存密钥。</div>':''}
    <div class="report-layout"><section class="panel report-list">${data.items.length?data.items.map(x=>`<button class="report-item ${x.id===state.reportId?'active':''}" data-action="select-report" data-id="${x.id}"><strong>${x.business_date} ${x.provisional?'· 实时':''}</strong>${badge(x.ai_status)} <span class="badge">${x.finding_count} 项线索</span><small>#${x.id} · 版本 ${x.source_revision}${x.stale?' · 有后续变更':''}</small></button>`).join(''):empty('还没有日报','先生成一次业务日汇总。')}<div class="row wrap">${actBtn('report-prev','上一页',state.reportPage<=1?'disabled':'','small')}${actBtn('report-next','下一页',state.reportPage*30>=data.total?'disabled':'','small')}</div></section><div class="report-content">${r?reportBody(r):`<section class="panel">${empty('从今天开始，每日有数','选择业务日期后点击“汇总并审查”。未配置 API Key 也能生成规则日报。')}</section>`}</div></div>`;
}
// MAINT_PROTECTED_BEGIN:report-write
async function generateReport(preview=false){
  const day=$('#report-date').value;if(!day)throw new Error('请选择业务日期。');state.end=day;
  const useAI=$('#report-ai').checked;
  const body={business_date:day,use_ai:useAI,retry_ai:useAI};
  if(preview){const payload=await api('/api/reports/preview',{method:'POST',body});openModal('外发数据预览','这一步仅预览，不会向 DeepSeek 发起网络请求。',`<div class="banner warning">不含客户姓名、电话、VIN、车牌、原始账号、凭证号或备注。但金额与经营统计仍是敏感商业信息，请确认门店允许外发。</div><pre class="json-view">${E(JSON.stringify(payload,null,2))}</pre>`);return;}
  const button=$('[data-action=generate-report]'),progress=$('#report-progress');button.disabled=true;progress.textContent=useAI?'正在保存规则日报并请求 DeepSeek…':'正在计算并保存规则日报…';
  try{const data=await api('/api/reports/generate',{method:'POST',body});state.reportId=data.id;state.reportPage=1;await renderPage();toast('日报已保存。AI 是否完成请看报告状态。');}
  finally{if(button.isConnected)button.disabled=false;if(progress.isConnected)progress.textContent='';}
}

// MAINT_PROTECTED_END:report-write
function downloadReport(){
  const r=state.report;if(!r)return;let text=`# ${r.business_date} 门店经营审查日报\n\n生成于：${timestamp(r.generated_at)}\n\n数据版本：${r.source_revision}；日报 ID：${r.id}\n\n## 程序汇总\n\n${r.deterministic_summary}\n\n`;
  if(r.ai_result){text+=`## DeepSeek 摘要（未核实）\n\n${r.ai_result.summary}\n\n`+r.ai_result.highlights.map(h=>'- '+h).join('\n')+'\n\n';for(const v of r.ai_result.reviews)text+=`### AI 线索 ${v.ref}\n\n${v.reason}\n\n建议：${v.action}\n\n`;text+=r.ai_result.limitations+'\n\n';}
  text+='## 规则复核线索\n\n';for(const f of r.snapshot.rule_findings)text+=`### ${f.ref} · ${f.title}\n\n${evidenceText(f.evidence)}\n\n建议：${f.suggested_action}\n\n`;
  text+=`## 口径与限制\n\n${r.snapshot.basis}\n\nAI 明细覆盖 ${r.snapshot.ai_record_count}/${r.snapshot.record_count_before_ai_cap}。${r.snapshot.provisional?'当日进行中，不是最终日结。':''}\n`;
  downloadBlob(new Blob([text],{type:'text/markdown;charset=utf-8'}),`门店日报-${r.business_date}-${r.id}.md`);
}
async function findingsPage(){
  const data=await api(`/api/findings?status=${state.reviewStatus}&page=${state.page}`);state.rows=data.items;state.total=data.total;
  return heading('数据复核台','记录证据、核对原始单据、留下处理结论。规则提示不等于已经查实的问题。',actBtn('nav','生成 / 更新线索','data-route="reports"','primary'),'HUMAN IN THE LOOP / 人工复核')+
    `<div class="toolbar"><select id="review-status" aria-label="复核状态"><option value="">全部复核状态</option>${['open','reviewing','confirmed','dismissed','resolved'].map(s=>`<option value="${s}" ${s===state.reviewStatus?'selected':''}>${statuses[s]}</option>`).join('')}</select>${actBtn('filter-findings','查询')}<span class="subtitle">线索来自已生成日报；修正数据后需重新生成日报。旧提示不会自动被删除。</span></div>
    ${data.items.length?`<div class="finding-grid">${data.items.map(f=>`<section class="panel finding-card ${f.severity}"><div class="panel-head"><div><div class="row wrap">${badge(f.severity)}${badge(f.review_status)}</div><h2>${E(f.title)}</h2><small class="mono">${E(f.rule_code)} · ${E(names[f.entity_type])} #${f.entity_id}</small></div>${actBtn('detail','原单',`data-module="${f.entity_type}" data-id="${f.entity_id}"`,'small ghost')}</div><div class="finding-evidence">${E(evidenceText(f.evidence))}</div><p>${E(f.suggested_action)}</p>${f.review_note?`<p><strong>复核备注：</strong>${E(f.review_note)}</p>`:''}<div class="finding-footer"><small>首次 ${f.first_seen}<br>最近命中 ${f.last_seen}</small>${actBtn('review','记录复核结论',`data-id="${f.id}"`,'small')}</div></section>`).join('')}</div>`:`<section class="panel">${empty('此状态下没有复核项','先生成日报以运行规则，或切换复核状态查看已处理问题。')}</section>`}${pagination(data.total,state.page)}`;
}
// MAINT_PROTECTED_BEGIN:review-write
async function reviewDialog(id){
  const f=state.rows.find(r=>r.id===id);if(!f)throw new Error('请刷新复核列表。');
  openModal('记录复核结论',f.title,`<div class="finding-evidence">${E(evidenceText(f.evidence))}</div>${renderField(field('status','处理状态','select',{options:Object.fromEntries(['open','reviewing','confirmed','dismissed','resolved'].map(s=>[s,statuses[s]]))}),f.review_status)}${renderField(field('note','复核依据与处理说明（至少5字）','textarea',{required:true,max:2000}),f.review_note||'')}`,
    actBtn('close-modal','取消')+'<button class="primary" type="submit">保存复核记录</button>',true);
  bindForm(async fd=>{await api(`/api/findings/${id}/review`,{method:'POST',body:{version:f.version,status:fd.get('status'),note:fd.get('note')}});$('#modal').close();toast('复核记录已保存并留痕。');await renderPage();});
}

// MAINT_PROTECTED_END:review-write
async function usersPage(){
  const data=await api('/api/users');state.rows=data.items;state.allStores=data.stores;
  return heading('账号与权限','部门角色控制后端访问，员工只能编辑自己创建的草稿；角色变更后旧会话立即撤销。',actBtn('new-user','＋ 新建账号','','primary'))+
    '<div class="banner">店长不能审核自己录入的单据。系统管理员保留自审能力以支持小店初始化，但操作会明确标记。审计角色只读业务数据，可以处理复核项。</div>'+
    `<section class="panel table-panel"><div class="table-scroll"><table><thead><tr><th>账号</th><th>姓名 / 显示名</th><th>角色</th><th>门店授权</th><th>状态</th><th>首次改密</th><th>操作</th></tr></thead><tbody>${data.items.map(u=>`<tr><td class="mono">${E(u.username)}</td><td>${E(u.display_name)}</td><td>${E(u.role_label)}</td><td>${u.role==='admin'?'全部门店（含新建）':E(u.stores.map(s=>s.name).join('、')||'无可用门店')}</td><td>${badge(u.active?'approved':'void',u.active?'正常':'已停用')}</td><td>${u.must_change_password?'待修改':'已完成'}</td><td><div class="actions">${actBtn('edit-user','编辑权限',`data-id="${u.id}"`,'small')}${u.id!==state.user.id?actBtn('reset-password','重置密码',`data-id="${u.id}"`,'small ghost'):''}</div></td></tr>`).join('')}</tbody></table></div></section><div class="basis">默认同部门可以查看本部门单据；这里没有销售员“只能看自己的客户”的客户隔离策略。一个账号可授权多家门店，部门角色在所有授权门店一致；审批额度、自定义字段权限及单客户隔离尚未实现。</div>`;
}
// MAINT_PROTECTED_BEGIN:account-write
function userDialog(id=null){
  const row=id?state.rows.find(r=>r.id===id):null;
  const fields=[...(!row?[field('username','账号（英文、数字、下划线等）','text',{required:true,max:40})]:[]),field('display_name','显示名称','text',{required:true,max:80}),field('role','权限角色','select',{options:roleNames,default:'sales'}),...(!row?[field('password','初始密码（至少12位）','password',{required:true,max:128})]:[])];
  openModal(row?'修改账号权限':'创建员工账号',row?row.username:'新员工首次登录必须修改临时密码。',`<div class="form-grid">${fields.map(f=>renderField(f,row?row[f.name]:(f.default||''))).join('')}</div><fieldset><legend>门店授权（非管理员至少一家；管理员自动拥有所有门店）</legend>${(state.allStores||[]).filter(s=>s.active).map(s=>`<label class="checkbox-label"><input type="checkbox" name="store_ids" value="${s.id}" ${(row?.store_ids||[Number(state.storeId)]).includes(s.id)?'checked':''}>${E(s.name)} · ${E(s.code)}</label>`).join('')}</fieldset>${row?`<p><label class="checkbox-label"><input name="active" type="checkbox" ${row.active?'checked':''}>启用该账号</label></p>`:''}`,actBtn('close-modal','取消')+'<button type="submit" class="primary">保存账号</button>',true);
  bindForm(async fd=>{const body=Object.fromEntries(fd);body.store_ids=fd.getAll('store_ids').map(Number);if(row)body.active=fd.has('active');await api('/api/users'+(row?'/'+row.id:''),{method:row?'PUT':'POST',body});$('#modal').close();toast('账号已保存。');if(row?.id===state.user.id){state.user=null;renderLogin();toast('你的会话已撤销，请重新登录。');}else await renderPage();});
}
function resetPasswordDialog(id){
  const row=state.rows.find(r=>r.id===id);if(!row)throw new Error('用户不存在。');
  openModal('重置员工密码',row.username,`${renderField(field('password','新的临时密码（至少12位）','password',{required:true,max:128}),'')}${renderField(field('reason','重置原因','textarea',{required:true,max:1000}),'')}`,actBtn('close-modal','取消')+'<button class="primary" type="submit">重置并撤销旧会话</button>',true);
  bindForm(async fd=>{await api(`/api/users/${id}/password`,{method:'POST',body:Object.fromEntries(fd)});$('#modal').close();toast('密码已重置，员工下次登录须再次修改。');await renderPage();});
}
function passwordDialog(required=false){
  openModal('修改我的密码',required?'首次登录须完成密码修改。':'修改后所有旧会话都会退出。',`${renderField(field('current_password','当前密码','password',{required:true,max:128}),'')}${renderField(field('new_password','新密码（至少12位）','password',{required:true,max:128}),'')}${renderField(field('confirmation','再次输入新密码','password',{required:true,max:128}),'')}`,(!required?actBtn('close-modal','取消'):'')+'<button class="primary" type="submit">修改密码</button>',true);
  bindForm(async fd=>{if(fd.get('new_password')!==fd.get('confirmation'))throw new Error('两次输入的新密码不一致。');await api('/api/auth/password',{method:'POST',body:{current_password:fd.get('current_password'),new_password:fd.get('new_password')}});state.user=null;renderLogin();toast('密码已修改，请使用新密码登录。');});
}

// MAINT_PROTECTED_END:account-write
async function auditPage(){
  const data=await api(`/api/audit?page=${state.page}`);state.rows=data.items;state.total=data.total;
  const actions={create:'新增',update:'编辑',submit:'提交',approve:'审核通过',reject:'退回',advance:'交车 / 完工',void:'作废',seed:'虚构演示初始化',generate:'生成日报',ai_result:'AI 结果',review:'人工复核',reopen:'重新开放',login:'登录',export:'导出',create_user:'创建账号',update_user:'修改账号',change_password:'修改密码',reset_password:'重置密码'};
  return heading('操作日志','保留业务变更前后快照、操作者与理由。应用不提供删除日志接口。')+
    `<section class="panel table-panel"><div class="table-scroll"><table><thead><tr><th>时间</th><th>操作人</th><th>操作</th><th>对象</th><th>说明</th><th>变更内容</th></tr></thead><tbody>${data.items.map(r=>`<tr><td>${timestamp(r.occurred_at)}</td><td>${E(r.actor_name)}</td><td>${E(actions[r.action]||r.action)}</td><td>${E(names[r.entity_type]||r.entity_type)} ${r.entity_id?'#'+r.entity_id:''}</td><td><small>${E(r.reason||'—')}</small></td><td>${actBtn('audit-detail','查看快照',`data-id="${r.id}"`,'small')}</td></tr>`).join('')}</tbody></table></div>${pagination(data.total,state.page)}</section><div class="basis">这是应用级操作留痕，不是不可篡改的第三方审计存证；拥有数据库或服务器最高权限的人仍可能修改数据库。日志含业务敏感字段，仅允许管理员、店长和审计访问。</div>`;
}
async function settingsPage(){
  const s=await api('/api/settings');state.settings=s;
  const definitions=(data)=>Object.entries(data).map(([l,v])=>`<div class="definition"><div class="label">${E(l)}</div><div class="value">${E(v)}</div></div>`).join('');
  return heading('系统与统计口径','密钥和参数只在服务器环境变量配置。页面只显示配置状态，不显示任何密钥。')+
    `<div class="settings-grid"><section class="panel"><h2>每日任务</h2>${definitions({'应用版本':s.version,'门店时区':s.timezone,'定时日报':s.scheduler_enabled?'已启用':'已关闭','运行时间':s.daily_time+'，汇总前一业务日','最多补跑':s.catchup_days+' 个业务日','DeepSeek 外发':s.ai_allowed?'允许':'关闭','API Key':s.ai_key_configured?'已配置（不回传）':'未配置','模型名':s.ai_model})}<div class="basis">定时任务在应用进程内运行。关机、睡眠或关闭服务时不运行；重新启动后按补跑范围补齐。定时日报保存在系统中，本版不含微信、邮件或企业微信自动推送。</div></section>
    <section class="panel"><h2>复核阈值</h2>${definitions({'库存库龄':s.rules.inventory_aging_days+' 天','维修未完工':s.rules.repair_overdue_days+' 天，或晚于预计完工日','交付后未收款':s.rules.receivable_grace_days+' 天','销售毛差比例':s.rules.low_gross_margin_percent+' %','大额现金':'¥'+money(s.rules.large_cash_amount_cents),'高折扣':s.rules.discount_review_percent+' %','高佣金':s.rules.policy_commission_review_percent+' %'})}<div class="basis">这些是初始管理复核阈值，不是违法或财务舞弊的判定标准。除佣金比例目前在规则文件中固定外，其他阈值可在 .env 调整后重启。</div></section>
    <section class="panel"><h2>统计与数据边界</h2><div class="rules-list">业务发生日：订单 / 入库 / 报修 / 出单 / 流水实际发生日。<br>销售金额：已审核且在所选期间实际交车的合同总额。<br>维修金额：已审核且已完工的工时费 + 配件费 − 优惠。<br>保费与佣金：分别记录，保费代收不作为佣金或销售收入。<br>外部现金流：已审核流水，排除内部转账。<br>毛差：销售及维修结算金额 − 录入直接成本，不是净利润。<br>所有金额：数据库按人民币“分”的整数保存。<br>历史重算：使用当前有效业务状态；旧日报保留原快照。</div></section>
    <section class="panel"><h2>本地试用 → 服务器</h2><div class="rules-list">本地默认仅监听 127.0.0.1，不直接开放到公网。<br>数据库为 SQLite 文件，提供一致性备份命令。<br>已提供 Docker、数据库版本迁移和 PostgreSQL 转移脚本。<br>公网前须配置 HTTPS、强密码、备份恢复与最小权限。<br>完整业务凭证附件、复式总账、税务申报、退车/红冲、跨门店车辆调拨和跨门店资金对账不在本版范围。</div><div class="banner warning">先用独立演示库验证权限、口径与工作流，再录入真实数据。请勿把测试实例直接暴露到公网。</div></section></div>`;
}
// MAINT_PROTECTED_BEGIN:store-selection
function storeSelector(){
  const group=['admin','manager','finance','auditor'].includes(state.user.role);
  return `<label class="store-select"><span>当前门店</span><select id="store-switch">${group?`<option value="all" ${state.storeId==='all'||state.storeId===null?'selected':''}>已授权门店 · 汇总</option>`:''}${state.stores.map(s=>`<option value="${s.id}" ${Number(state.storeId)===s.id?'selected':''}>${E(s.name)}</option>`).join('')}</select></label>`;
}

// MAINT_PROTECTED_END:store-selection
function storeComparison(d){
  if((d.by_store||[]).length<2)return '';
  return `<section class="panel table-panel"><div class="panel-head"><div><h2>各门店经营对照</h2><small>${E(d.end_date)} 当日流量与日末库存，不是整个所选区间的累计</small></div></div><div class="table-scroll"><table><thead><tr><th>门店</th><th>当日交车</th><th>当日交付金额</th><th>在库车辆</th><th>库存成本占用</th><th>待审核</th></tr></thead><tbody>${d.by_store.map(s=>`<tr><td>${E(s.name)}</td><td>${s.metrics.delivery_count}</td><td>¥${money(s.metrics.delivery_amount_cents)}</td><td>${s.metrics.stock_count}</td><td>¥${money(s.metrics.stock_cost_cents)}</td><td>${s.metrics.pending_approval_count}</td></tr>`).join('')}</tbody></table></div></section>`;
}
async function storesPage(){
  const data=await api('/api/stores');state.rows=data.items;
  return heading('门店管理','各店独立录入、独立审批、独立日报；老板可汇总已授权门店。',actBtn('new-store','＋ 新建门店','','primary'))+
    `<section class="panel table-panel"><div class="table-scroll"><table><thead><tr><th>门店代码</th><th>名称</th><th>状态</th><th>操作</th></tr></thead><tbody>${data.items.map(r=>`<tr><td>${E(r.code)}</td><td>${E(r.name)}</td><td>${badge(r.active?'approved':'void',r.active?'启用':'停用')}</td><td>${actBtn('edit-store','编辑',`data-id="${r.id}"`,'small')}</td></tr>`).join('')}</tbody></table></div></section><div class="banner">门店代码用于识别，单据编号可在不同门店重复；VIN 保持集团内唯一。禁止跨店直接关联销售/维修/财务单据。此版本不自动调拨车辆，不进行集团内部交易抵销。</div>`;
}
// MAINT_PROTECTED_BEGIN:store-write
function storeDialog(id=null){
  const row=id?state.rows.find(r=>r.id===id):null;
  openModal(row?'编辑门店':'创建门店','创建后到“账号与权限”给员工授权。',`${renderField(field('code','门店代码（字母、数字、短横线）','text',{required:true,max:30}),row?.code||'')}${renderField(field('name','门店名称','text',{required:true,max:100}),row?.name||'')}<label class="checkbox-label"><input type="checkbox" name="active" ${!row||row.active?'checked':''}>启用门店</label>`,actBtn('close-modal','取消')+'<button class="primary" type="submit">保存</button>',true);
  bindForm(async fd=>{const body=Object.fromEntries(fd);body.active=fd.has('active');await api('/api/stores'+(id?'/'+id:''),{method:id?'PUT':'POST',body});$('#modal').close();state.storeId=null;state.user=await api('/api/auth/me');state.storeId=state.user.active_store_id;state.stores=state.user.stores;shell();await renderPage();toast('门店已保存。');});
}

// MAINT_PROTECTED_END:store-write
const changeStatuses={new:'已收集',queued:'等待处理',proposing:'DeepSeek 分析中',testing:'隔离测试中',awaiting_approval:'等待飞书审批',approved:'已批准 · 等待发布',deploying:'发布中',deployed:'已发布',rejected:'已拒绝',manual:'需人工开发',failed:'处理失败',expired:'审批已过期',superseded:'基线已变化，需重做',rollback_requested:'等待回滚',rolled_back:'已回滚'};
async function feedbackPage(){
  const data=await api('/api/feedback');state.rows=data.items;
  const maint=state.user.can_users?await api('/api/maintenance/status'):null;
  return heading('改进意见 / 版本发布','写下问题或导入 TXT / Markdown。意见不是命令：代码必须通过隔离测试，并由指定飞书账号批准。',actBtn('new-feedback','＋ 提交改进意见','','primary'),'HUMAN APPROVAL / 可控演进')+
    (maint?`<div class="banner"><strong>维护器：${maint.ready&&!maint.paused?'已就绪':maint.enabled?'待配置 / 已暂停':'未启用'}</strong> · ${E(maint.message)}${maint.ready?` · 飞书进程${maint.worker_running?'运行中':'未连接'}`:''}</div>`:'')+
    '<div class="banner warning">默认只自动修改界面与用户说明。权限、金额口径、数据库迁移、依赖和发布器不接受自动覆盖；超出范围的需求会转人工。未配置自动维护时仍能收集意见，不会外发。</div>'+
    `<section class="panel">${data.items.length?data.items.map(r=>`<article class="feedback-card"><div class="row wrap"><strong>#${r.id} ${E(r.title)}</strong>${badge(r.status,changeStatuses[r.status]||r.status)}<small>门店 #${r.store_id} · ${timestamp(r.created_at)}</small></div><p class="feedback-description">${E(r.description)}</p>${r.summary?`<p><strong>改动摘要：</strong>${E(r.summary)}</p>`:''}${r.head_sha?`<p class="mono">提交 ${E(r.head_sha)} · ${r.tests_passed?'测试通过':'未通过测试'}</p>`:''}${r.last_error?`<p class="form-error">${E(r.last_error)}</p>`:''}<div class="actions">${r.review_url&&/^https:\/\//.test(r.review_url)?`<a class="button-link" href="${E(r.review_url)}" target="_blank" rel="noopener noreferrer">查看 Git 改动</a>`:''}${actBtn('feedback-events','处理日志',`data-id="${r.id}"`,'small')}${state.user.can_users&&['new','failed','manual','expired','superseded','rejected'].includes(r.status)&&r.attempts<3?actBtn('queue-feedback','授权 AI 处理',`data-id="${r.id}"`,'small'):''}</div></article>`).join(''):empty('还没有改进意见','例：希望库存表增加更明显的超龄提示。')}</section><div class="basis">仅展示最近200条。普通员工仅看自己提交的意见；管理员可管理当前授权范围内的意见。发布批准只接受配置的飞书 open_id，不接受网页按钮代批。</div>`;
}
// MAINT_PROTECTED_BEGIN:feedback-and-dispatch
function feedbackDialog(){
  if(!state.storeId||state.storeId==='all')throw new Error('请先在右上角选择反馈所属门店。');
  openModal('提交改进意见','不要粘贴客户信息、账号密码、API Key 或真实财务明细。',`${renderField(field('title','标题','text',{required:true,max:160}),'')}${renderField(field('category','类型','select',{options:{improvement:'体验改进',bug:'错误报告',feature:'新功能'}}),'improvement')}${renderField(field('description','具体问题、复现步骤、期望效果','textarea',{required:true,max:12000}),'')}<label>导入纯文本意见（可选，UTF-8，最多48KB）<input id="feedback-file" type="file" accept=".txt,.md,text/plain,text/markdown"></label><label class="checkbox-label"><input type="checkbox" name="consent_code_review">允许将此意见及白名单源码发送给 DeepSeek（不发送数据库）</label>`,actBtn('close-modal','取消')+'<button class="primary" type="submit">提交意见</button>',true);
  $('#feedback-file').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(!/\.(txt|md)$/i.test(file.name)||file.size>49152)throw new Error('仅支持48KB以内的 .txt / .md 文本。');const text=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());if(text.length>12000)throw new Error('意见正文最多12000字符。');$('#modal [name=description]').value=text;}catch(error){toast(error.message,true);}};
  bindForm(async fd=>{const body=Object.fromEntries(fd);body.consent_code_review=fd.has('consent_code_review');await api('/api/feedback',{method:'POST',body});$('#modal').close();toast('意见已保存；未经飞书批准不会上线。');await renderPage();});
}
$('#app').addEventListener('change',async event=>{
  if(event.target.id!=='store-switch')return;
  const previous=state.storeId;state.storeId=event.target.value==='all'?'all':Number(event.target.value);
  try{state.user=await api('/api/auth/me');state.stores=state.user.stores;state.page=1;state.reportId=null;state.report=null;state.rows=[];state.filters={q:'',state:'',date_from:'',date_to:''};$('#modal').close();shell();await renderPage();}
  catch(error){state.storeId=previous;shell();await renderPage();toast(error.message,true);}
});
$('#app').addEventListener('click',async event=>{
  const button=event.target.closest('[data-action]');if(!button||button.disabled)return;
  const a=button.dataset.action,module=button.dataset.module,id=Number(button.dataset.id);
  try{
    if(a==='nav')await navigate(button.dataset.route);
    else if(a==='mobile-menu')$('.sidebar').classList.toggle('open');
    else if(a==='logout'){await api('/api/auth/logout',{method:'POST'});state.user=null;renderLogin();}
    else if(a==='password')passwordDialog();
    else if(a==='dashboard-refresh'){state.days=Number($('#dashboard-days').value);state.end=$('#dashboard-end').value;if(!state.end)throw new Error('请选择结束日期。');await renderPage();}
    else if(a==='filter'){state.filters={q:$('#filter-q').value.trim(),state:$('#filter-state').value,date_from:$('#filter-start').value,date_to:$('#filter-end').value};state.page=1;await renderPage();}
    else if(a==='new')await recordDialog(module);
    else if(a==='edit')await recordDialog(module,id);
    else if(a==='detail')await detailDialog(module,id);
    else if(a==='workflow')await workflowDialog(module,id,button.dataset.workflow);
    else if(a==='prev'||a==='next'){state.page+=a==='prev'?-1:1;await renderPage();}
    else if(a==='export'){button.disabled=true;const response=await api(`/api/export/${state.route}?${getFilters()}`,{raw:true});downloadBlob(await response.blob(),`${state.route}-${localToday()}.csv`);button.disabled=false;toast('CSV 已导出，包含敏感经营数据，请妥善保管。');}
    else if(a==='select-report'){state.reportId=id;await renderPage();}
    else if(a==='report-prev'||a==='report-next'){state.reportPage+=a==='report-prev'?-1:1;state.reportId=null;await renderPage();}
    else if(a==='generate-report')await generateReport();
    else if(a==='preview-report')await generateReport(true);
    else if(a==='download-report')downloadReport();
    else if(a==='ref'){const [prefix,num]=button.dataset.ref.split('-');await detailDialog(prefixModules[prefix],Number(num));}
    else if(a==='filter-findings'){state.reviewStatus=$('#review-status').value;state.page=1;await renderPage();}
    else if(a==='review')await reviewDialog(id);
    else if(a==='new-store')storeDialog();
    else if(a==='edit-store')storeDialog(id);
    else if(a==='new-feedback')feedbackDialog();
    else if(a==='queue-feedback'){if(!confirm('授权将这条改进意见与白名单源码发送到 DeepSeek？不要包含客户信息或密钥。'))return;await api(`/api/feedback/${id}/queue`,{method:'POST'});toast('已入队；仍需通过测试及飞书审批，才会应用。');await renderPage();}
    else if(a==='feedback-events'){const data=await api(`/api/feedback/${id}/events`);openModal('改进与发布记录','每一步单独留痕',`<div>${data.items.map(r=>`<div class="insight"><strong>${E(r.action)}</strong><small>${timestamp(r.occurred_at)} · ${E(r.actor)}</small><p>${E(r.detail)}</p></div>`).join('')||'暂未处理'}</div>`);}
    else if(a==='new-user')userDialog();
    else if(a==='edit-user')userDialog(id);
    else if(a==='reset-password')resetPasswordDialog(id);
    else if(a==='audit-detail'){const row=state.rows.find(r=>r.id===id);openModal('操作变更快照',`${timestamp(row.occurred_at)} · ${row.actor_name}`,`<p class="subtitle">${E(row.reason)}</p><div class="diff-grid"><div><h3>变更前</h3><pre class="json-view">${E(JSON.stringify(row.before_data,null,2))}</pre></div><div><h3>变更后</h3><pre class="json-view">${E(JSON.stringify(row.after_data,null,2))}</pre></div></div>`);}
  }catch(error){toast(error.message,true);if(button.isConnected)button.disabled=false;}
});
$('#modal').addEventListener('click',event=>{
  const button=event.target.closest('[data-action="close-modal"]');if(button){if(state.user?.must_change_password){toast('请先修改初始密码。',true);return;}$('#modal').close();}
});
$('#app').addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target.id==='filter-q'){event.preventDefault();$('[data-action=filter]').click();}});
(async()=>{try{state.user=await api('/api/auth/me');await boot();}catch{renderLogin();}})();

// MAINT_PROTECTED_END:feedback-and-dispatch

// ================= P4 批量填单：AI 只出草稿，人工复核后才写入 =================
// 本段全部在保护标记之外：不修改登录、权限、门店选择与既有写入流程，只调用它们。
// 服务器契约：POST /api/entry-draft/parse 只回草稿（rows / issues / proposed），绝不写业务表。
// 正式记录一律由人走既有的 POST /api/records/{module}（与 recordDialog 同一条提交路径），创建人即复核人。
const batchModules=['vehicles','sales','repairs','policies','cash'];
let batchState={module:null,fields:[],drafts:[],issues:[],orphans:[],text:'',proposed:0,written:0,summary:''};
const batchFieldName=(row,name)=>`r${row}__${name}`;
const batchInput=(row,name)=>$(`#modal [name="${batchFieldName(row,name)}"]`);
function batchRow(row){return batchState.drafts.find(d=>d.index===row);}
function batchRowIssues(row){return batchState.issues.filter(i=>i.row===row);}
// fields 契约：服务器的 normalise_options 只接受「允许取值的数组」，标签只存在于前端。
// 因此发送 options 的键（真实取值），不是 field().options 的 {值:标签} 对象；没有选项时发 null。
function batchFieldSpec(module){
  return [...moduleFields[module],noteField].map(f=>({name:f.name,label:f.label,kind:f.type,required:!!f.required,
    options:f.type==='select'&&f.options?Object.keys(f.options):null}));
}
// 只有「必填字段仍为空」算未处理：可选字段留空是记录的合法状态，由复核人决定；未知字段本来就不入库。
function batchIssueBlocks(d,issue){const f=batchState.fields.find(x=>x.name===issue.field);
  return !!f&&!!f.required&&!String(d.values[issue.field]??'').trim();}
function batchBlocking(d){return batchRowIssues(d.index).filter(i=>batchIssueBlocks(d,i));}
function batchSync(){for(const d of batchState.drafts)for(const f of batchState.fields){const input=batchInput(d.index,f.name);if(input)d.values[f.name]=input.value;}}
function batchFormData(row){const fd=new FormData();for(const f of batchState.fields){const input=batchInput(row,f.name);fd.set(f.name,input?input.value:'');}return fd;}
function batchCell(f,d){
  const name=batchFieldName(d.index,f.name),value=String(d.values[f.name]??'');
  const issues=batchState.issues.filter(i=>i.row===d.index&&i.field===f.name),blocking=issues.filter(i=>batchIssueBlocks(d,i));
  const reason=issues.length?`${blocking.length?'AI 提示':'AI 取值无效，已置空（可选）'}：`+issues.map(i=>i.reason).join('；'):'';
  const attrs=`name="${name}" id="batch-${name}" aria-label="${E(f.label)}"${f.max?` maxlength="${f.max}"`:''}`;
  let input;
  if(f.type==='select')input=`<select ${attrs}>${value===''||!(f.options||{})[value]?'<option value="">未填写</option>':''}${Object.entries(f.options||{}).map(([v,l])=>`<option value="${E(v)}" ${String(value)===v?'selected':''}>${E(l)}</option>`).join('')}</select>`;
  else if(f.type==='textarea')input=`<textarea ${attrs}>${E(value)}</textarea>`;
  else if(f.type==='lookup')input=`<input ${attrs} value="${E(value)}" ${f.module?`list="lookup-${name}" data-lookup="${E(f.module)}" autocomplete="off"`:''} placeholder="输入关键词搜索，或填记录 ID">${f.module?`<datalist id="lookup-${name}"></datalist>`:''}`;
  else input=`<input ${attrs} type="${f.type==='money'?'number':f.type}" ${f.type==='money'?'step="0.01" min="0" max="9999999999.99"':''} value="${E(value)}">`;
  return `<td class="batch-cell${blocking.length?' batch-cell-issue':''}" data-batch-cell="${name}" data-batch-row="${d.index}"><label class="field"><span>${E(f.label)}${f.required?' <b class="required">*</b>':''}</span>${input}<small class="batch-reason${blocking.length?'':' ok'}">${E(reason)}</small></label></td>`;
}
function batchIssuesHTML(d){
  const lines=[];
  for(const issue of batchRowIssues(d.index)){
    const f=batchState.fields.find(x=>x.name===issue.field),open=batchIssueBlocks(d,issue);
    const label=f?f.label:(issue.field?`未知字段「${issue.field}」`:'整行');
    lines.push(`<div class="batch-issue-line${open?' open':' ok'}">${E(label)}：${E(issue.reason)}（${open?'待你补填':f?'已置空 / 可选留空':'已丢弃，不作为记录字段'}）</div>`);
  }
  if(d.error)lines.push(`<div class="batch-issue-line open">写入失败：${E(d.error)}</div>`);
  if(!lines.length)lines.push('<div class="batch-issue-line ok">AI 未标出问题；金额、日期、VIN 与关联编号仍需你核对。</div>');
  return lines.join('');
}
function batchRowHTML(d){
  const blocking=batchBlocking(d).length;
  return `<tr class="batch-tr${blocking?' batch-row-issue':''}" data-batch-row="${d.index}"><td class="batch-index"><strong>第 ${d.index+1} 条</strong><span data-batch-status>${badge(blocking?'high':'approved',blocking?`待补必填 ${blocking} 项`:'可写入')}</span><div class="row wrap">${actBtn('batch-defaults','补全空缺默认值',`data-row="${d.index}"`,'small ghost')}${actBtn('batch-remove','删除本行',`data-row="${d.index}"`,'small ghost')}</div></td>${batchState.fields.map(f=>batchCell(f,d)).join('')}<td class="batch-issues" data-batch-issues="${d.index}">${batchIssuesHTML(d)}</td></tr>`;
}
function batchCountsHTML(){
  const blocked=batchState.drafts.filter(d=>batchBlocking(d).length).length;
  return `<span>待写入 <strong>${batchState.drafts.length}</strong> 条</span><span>仍缺必填 <strong>${blocked}</strong> 条（补齐前不会写入）</span>`;
}
function batchTableHTML(){
  if(!batchState.drafts.length)return empty('没有待写入的草稿','模型没有提出可复核的行，或已被你全部删除。请返回重新粘贴文本。');
  return `<div class="table-scroll batch-table-wrap"><table class="batch-table"><thead><tr><th># / 状态</th>${batchState.fields.map(f=>`<th>${E(f.label)}${f.required?' <b class="required">*</b>':''}</th>`).join('')}<th>AI 提示与写入结果</th></tr></thead><tbody>${batchState.drafts.map(batchRowHTML).join('')}</tbody></table></div>`;
}
function batchRefreshRow(row){
  const d=batchRow(row);if(!d)return;
  for(const f of batchState.fields){const input=batchInput(row,f.name);if(input)d.values[f.name]=input.value;}
  const tr=$(`#modal tr[data-batch-row="${row}"]`);if(!tr)return;
  const blocking=batchBlocking(d).length;
  const holder=$('[data-batch-status]',tr);if(holder)holder.innerHTML=badge(blocking?'high':'approved',blocking?`待补必填 ${blocking} 项`:'可写入');
  tr.classList.toggle('batch-row-issue',blocking>0);
  for(const f of batchState.fields){
    const cell=$(`[data-batch-cell="${batchFieldName(row,f.name)}"]`,tr);if(!cell)continue;
    const issues=batchState.issues.filter(i=>i.row===row&&i.field===f.name),open=issues.filter(i=>batchIssueBlocks(d,i));
    cell.classList.toggle('batch-cell-issue',open.length>0);
    const small=$('.batch-reason',cell);
    if(small){small.textContent=issues.length?`${open.length?'AI 提示':'AI 取值无效，已置空（可选）'}：`+issues.map(i=>i.reason).join('；'):'';small.className=`batch-reason${open.length?'':' ok'}`;}
  }
  const box=$(`[data-batch-issues="${row}"]`,tr);if(box)box.innerHTML=batchIssuesHTML(d);
  const counts=$('#batch-counts');if(counts)counts.innerHTML=batchCountsHTML();
  const confirm=$('#batch-confirm');if(confirm){confirm.disabled=!batchState.drafts.length;confirm.textContent=`确认写入 ${batchState.drafts.length} 条草稿`;}
}
function batchFillDefaults(row){
  for(const d of batchState.drafts){
    if(row!==null&&d.index!==row)continue;
    for(const f of batchState.fields){
      if(String(d.values[f.name]??'').trim())continue;
      const value=defaultValue(f,batchState.module);if(!value)continue;
      d.values[f.name]=String(value);const input=batchInput(d.index,f.name);if(input)input.value=String(value);
    }
  }
}
function renderBatchReview(){
  const module=batchState.module,n=batchState.drafts.length;
  $('#modal').classList.add('batch-modal');
  const orphan=batchState.orphans.length?`<div class="banner danger">模型返回的以下提示无法对应到具体草稿行（该条可能不是字段对象，或条数被上限截断），请人工核对：${E(batchState.orphans.map(i=>{const row=Number(i&&i.row);return `${Number.isInteger(row)&&row>=0?`第 ${row+1} 条`:'未标明行'} ${(i&&i.field)||'整行'}：${(i&&i.reason)||'模型输出异常，未给出原因'}`;}).join('；'))}</div>`:'';
  openModal(`复核 AI 草稿 · ${names[module]}`,`模型提出 ${batchState.proposed} 条草稿：请逐条核对，删掉不需要的行，补上标红的必填项。`,
    `${batchState.summary}<div class="banner warning">下表只是草稿，<strong>尚未写入任何业务记录</strong>。只有你点击“确认写入”后才会逐条调用普通录入接口保存；每条记录的创建人记录为 <strong>${E(state.user.display_name)}</strong>（${E(state.user.username)}），保存后仍是草稿，需按常规流程提交与审核。金额、日期、VIN 与关联编号一律以你的复核为准。</div>${orphan}
    <div class="batch-summary" id="batch-counts">${batchCountsHTML()}</div>
    <div class="batch-summary">${n?actBtn('batch-fill-all','为所有空缺字段补默认值','','small'):actBtn('batch-restart','返回重新粘贴','data-module="'+E(module)+'"','small')}<span class="hint">补默认值只填当前为空的字段，是否采纳由你决定。</span></div>
    ${batchTableHTML()}
    <details><summary>查看原始粘贴文本（对照用）</summary><pre class="json-view">${E(batchState.text||'')}</pre></details>
    <div id="batch-write-progress" class="subtitle" role="status"></div>`,
    '<span class="hint">AI 只出草稿；写入由你负责</span>'+actBtn('close-modal',batchState.written?`关闭（已写入 ${batchState.written} 条）`:'取消，不写入')+`<button id="batch-confirm" class="primary" type="submit" value="confirm"${n?'':' disabled'}>确认写入 ${n} 条草稿</button>`,true);
  initializeLookups();
  bindForm(async()=>{await batchWrite();});
}
async function batchWrite(){
  batchSync();
  const progress=$('#batch-write-progress'),targets=[],blocked=[];
  for(const d of batchState.drafts)(batchBlocking(d).length?blocked:targets).push(d);
  if(!targets.length){
    batchState.summary='<div class="banner warning">没有可写入的行：下表每一行都还有未补齐的必填字段。请补填、用“补全空缺默认值”，或删除该行。</div>';
    return renderBatchReview();
  }
  let ok=0,failed=0;
  for(const d of targets){
    if(progress)progress.textContent=`正在逐条写入第 ${ok+failed+1} / ${targets.length} 条…`;
    let body;
    // 与 recordDialog 完全相同的取值与校验路径：readRecordForm 负责 lookup / date / money 的转换。
    try{body=readRecordForm(batchFormData(d.index),batchState.module);}
    catch(error){d.error=error.message;failed++;continue;}
    try{
      const saved=await api(`/api/records/${batchState.module}`,{method:'POST',body});
      d.written=true;d.error='';d.savedId=saved&&saved.id;ok++;batchState.written++;
    }catch(error){d.error=error.message;failed++;}
  }
  batchState.drafts=batchState.drafts.filter(d=>!d.written);
  const parts=[`已写入 ${ok} 条草稿（创建人：你）`];
  if(failed)parts.push(`${failed} 条写入失败，已保留在下表，可修改后重试`);
  if(blocked.length)parts.push(`${blocked.length} 条因必填字段未补齐未提交`);
  batchState.summary=`<div class="banner${failed||blocked.length?' warning':''}">上次提交：${parts.join('；')}。写入的记录仍需按常规流程提交与审核。</div>`;
  try{await renderPage();}catch(error){toast(error.message,true);}
  renderBatchReview();
  toast(`批量填单：写入成功 ${ok} 条${failed?`，失败 ${failed} 条（见下表）`:''}${blocked.length?`，未提交 ${blocked.length} 条（缺必填）`:''}。`,failed>0||blocked.length>0);
  if(!batchState.drafts.length)$('#modal').close();
}
function batchReviewDialog(text,data){
  const rows=Array.isArray(data&&data.rows)?data.rows:[],raw=Array.isArray(data&&data.issues)?data.issues:[];
  const drafts=rows.map((row,index)=>{const values={};for(const f of batchState.fields){const raw=(row&&Object.prototype.hasOwnProperty.call(row,f.name))?row[f.name]:null;values[f.name]=raw==null?'':String(raw);}return {index,values,error:''};});
  // 服务器返回的 issue.row 是 rows 的下标；这里只认能对应到草稿行的提示，其余整条列出，绝不静默丢弃。
  batchState.issues=raw.filter(i=>i&&Number.isInteger(i.row)&&i.row>=0&&i.row<rows.length);
  batchState.orphans=raw.filter(i=>!batchState.issues.includes(i));
  batchState.drafts=drafts;batchState.text=text;batchState.proposed=Number(data&&data.proposed)||rows.length;
  renderBatchReview();
}
async function batchEntryDialog(module){
  if(!batchModules.includes(module)||!moduleFields[module])throw new Error('该模块不支持批量填单。');
  if(!state.user.write_modules.includes(module))throw new Error('你没有该模块的录入权限。');
  if(!state.storeId||state.storeId==='all')throw new Error('请先在右上角选择一家具体门店；批量填单不支持“全部门店汇总”。');
  if(state.settings&&state.settings.ai_allowed===false)throw new Error('服务器未开启 AI 外发（ALLOW_AI_EXTERNAL）；批量填单不可用，请继续手工录入。');
  $('#modal').classList.remove('batch-modal');
  batchState={module,fields:[...moduleFields[module],noteField],drafts:[],issues:[],orphans:[],text:'',proposed:0,written:0,summary:''};
  openModal(`AI 批量填写 · ${names[module]}`,'粘贴一段文字，由 DeepSeek 整理成待复核草稿；是否写入由你逐条确认。',
    `<div class="banner">AI 只做字段抽取，<strong>不会写入任何业务记录</strong>。草稿必须由你逐条复核、修改、删除后点击“确认写入”，才会通过普通录入接口保存；创建人记录为你（${E(state.user.display_name)}）。</div>
    <div class="banner warning">只发送你粘贴的文本与字段清单，不发送数据库内容或其他记录。粘贴前请自行去掉身份证号、银行卡号等敏感信息。</div>
    ${renderField(field('batch_text','粘贴文本（10–20000 字符，一行一条记录）','textarea',{required:true,max:20000}),'')}
    <label>导入纯文本（可选，UTF-8，最多48KB）<input id="batch-file" type="file" accept=".txt,.md,text/plain,text/markdown"></label>
    <div id="batch-parse-progress" class="subtitle" role="status"></div>`,
    '<span class="hint">AI 草稿不落库；核对后才逐条写入</span>'+actBtn('close-modal','取消')+'<button class="primary" type="submit">让 AI 生成草稿</button>',true);
  $('#batch-file').onchange=async event=>{
    try{
      const file=event.target.files[0];if(!file)return;
      if(!/\.(txt|md)$/i.test(file.name)||file.size>49152)throw new Error('仅支持48KB以内的 .txt / .md 文本。');
      const text=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
      if(text.length>20000)throw new Error('文本最多20000字符。');
      $('#modal [name=batch_text]').value=text;
    }catch(error){toast(error.message,true);}
  };
  bindForm(async fd=>{
    const text=String(fd.get('batch_text')??'').replace(/\r\n?/g,'\n').trim();
    if(text.length<10)throw new Error('请至少粘贴 10 个字符的文本。');
    if(text.length>20000)throw new Error('文本最多 20000 字符。');
    const progress=$('#batch-parse-progress');if(progress)progress.textContent='正在请求 DeepSeek 生成草稿，请稍候…';
    try{
      const data=await api('/api/entry-draft/parse',{method:'POST',body:{module,text,fields:batchFieldSpec(module)}});
      batchReviewDialog(text,data);
    }finally{const node=$('#batch-parse-progress');if(node)node.textContent='';}
  });
}
// 新监听器注册在保护标记之外，不改动既有的 `#app` 分发链（其中 new/edit/detail 等动作保持原样）。
$('#app').addEventListener('click',async event=>{
  const button=event.target.closest('[data-action="batch-entry"]');if(!button||button.disabled)return;
  try{await batchEntryDialog(button.dataset.module);}catch(error){toast(error.message,true);}
});
$('#modal').addEventListener('click',async event=>{
  const button=event.target.closest('[data-action]');if(!button||button.disabled)return;
  const action=button.dataset.action,row=Number(button.dataset.row);
  try{
    if(action==='batch-remove'){batchSync();batchState.drafts=batchState.drafts.filter(d=>d.index!==row);renderBatchReview();}
    else if(action==='batch-defaults'){batchSync();batchFillDefaults(row);renderBatchReview();}
    else if(action==='batch-fill-all'){batchSync();batchFillDefaults(null);renderBatchReview();}
    else if(action==='batch-restart')await batchEntryDialog(button.dataset.module);
  }catch(error){toast(error.message,true);}
});
$('#modal').addEventListener('input',event=>{const cell=event.target.closest('[data-batch-cell]');if(cell)batchRefreshRow(Number(cell.dataset.batchRow));});
$('#modal').addEventListener('change',event=>{const cell=event.target.closest('[data-batch-cell]');if(cell)batchRefreshRow(Number(cell.dataset.batchRow));});
$('#modal').addEventListener('close',()=>$('#modal').classList.remove('batch-modal'));

// ================= 数据可视化：依赖为零的 SVG 图表页（web/charts.js） =================
// 本段全部在保护标记之外：不改登录、权限、门店选择与既有写入流程，只调用它们。
// 导航：shell() 在保护区里，因此在每次 renderPage 后补一个同样的 .nav-item[data-route=viz]，
// 沿用既有 data-action="nav" 分发链与看板的 can_report 权限门，不另立第二套机制。
// 服务器契约：GET /api/visualization?end=YYYY-MM-DD&days=N；金额一律是整数分（cents）。
const vizNavLabel='数据可视化';
const vizIconPath='M4 20V4 M2 20h20 M8 20v-6 M12 20v-10 M16 20v-4 M20 20v-8';
// 服务器把 days 收敛到 7..365（app/visualization.py: clamp_days），所以这里不提供“当日”。
const vizDaysOptions=[[7,'近 7 日'],[30,'近 30 日'],[90,'近 90 日'],[180,'近 180 日'],[365,'近 365 日']];
const vizState={data:null,charts:[],exporting:false};
function vizIconNode(){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');
  const path=document.createElementNS('http://www.w3.org/2000/svg','path');
  path.setAttribute('d',vizIconPath);
  path.setAttribute('stroke-linecap','round');path.setAttribute('stroke-linejoin','round');
  svg.append(path);
  return svg;
}
function vizNavNode(){
  const button=document.createElement('button');
  button.type='button';button.className='nav-item';
  button.dataset.action='nav';button.dataset.route='viz';
  const label=document.createElement('span');label.textContent=vizNavLabel;
  button.append(vizIconNode(),label);
  return button;
}
// 权限门与看板一致：只有 can_report 的用户才看得到入口（后端同样以看板权限校验该接口）。
function ensureVizNav(){
  if(!state.user?.can_report)return;
  const sidebar=$('.sidebar');if(!sidebar)return;
  const active=state.route==='viz';
  let item=$('.nav-item[data-route="viz"]',sidebar);
  if(item)item.classList.toggle('active',active);
  else{
    const anchor=$('.nav-item[data-route="dashboard"]',sidebar);
    if(!anchor)return;
    item=vizNavNode();item.classList.toggle('active',active);
    anchor.insertAdjacentElement('afterend',item);
  }
  const crumb=$('.breadcrumb strong');
  if(crumb&&active&&crumb.textContent!==vizNavLabel)crumb.textContent=vizNavLabel;
}
function vizNumber(value){return new Intl.NumberFormat('zh-CN',{maximumFractionDigits:0}).format(Number(value||0));}
function vizUnitLabel(unit){return unit==='money'?'CNY':'COUNT';}
function vizUnitHint(unit){return unit==='money'?'金额 / 元':'数量 / 条 · 台';}
function vizKpiCard(item,accent){
  const value=item.unit==='money'?`<span class="currency">¥</span>${money(item.value)}`:`${vizNumber(item.value)}`;
  return kpi(item.label||item.key||'指标',value,E(item.hint||''),accent,vizUnitLabel(item.unit));
}
function vizCard(index,title,subtitle){
  return `<section class="panel viz-card"><div class="panel-head"><div><h2>${E(title)}</h2><small>${E(subtitle)}</small></div>${actBtn('viz-export','导出图片',`data-chart="${index}"`,'small ghost')}</div><div class="chart-holder" data-chart-holder="${index}"><div class="loading-line">正在绘制图表…</div></div></section>`;
}
function vizNotice(text){const node=document.createElement('div');node.className='inline-error';node.textContent=text;return node;}
function vizHolder(index){return $(`[data-chart-holder="${index}"]`);}
function vizFileName(chart){
  const data=vizState.data||{};
  return `${chart.title}-${data.start_date||''}_${data.end_date||''}`;
}
async function vizPage(){
  if(!state.user.can_report)throw new Error('你没有查看数据可视化的权限。');
  // 可视化接口把 days 收敛到 7..365（app/visualization.py: clamp_days），
  // 看板的“当日”（1 天）在这里回落为默认窗口，避免控件显示的天数与返回的天数不一致。
  if(!vizDaysOptions.some(([value])=>value===state.days))state.days=30;
  const controls=`<div class="date-controls"><select id="viz-days" aria-label="可视化统计期间">${vizDaysOptions.map(([value,label])=>`<option value="${value}" ${value===state.days?'selected':''}>${label}</option>`).join('')}</select><input id="viz-end" type="date" aria-label="可视化结束日期" value="${E(state.end||localToday())}" max="${localToday()}">${actBtn('viz-refresh','更新','','small')}${actBtn('viz-export-all','全部导出','','small ghost')}</div>`;
  const data=await api(`/api/visualization?end=${state.end}&days=${state.days}`);
  const kpis=Array.isArray(data.kpis)?data.kpis:[];
  const trends=Array.isArray(data.trends)?data.trends:[];
  const breakdowns=Array.isArray(data.breakdowns)?data.breakdowns:[];
  const rankings=Array.isArray(data.rankings)?data.rankings:[];
  const notes=(Array.isArray(data.notes)?data.notes:[]).filter(note=>String(note??'').trim());
  const range=`${data.start_date||''} 至 ${data.end_date||''}`;
  const charts=[],cards=[];
  trends.forEach(item=>{
    const title=item.title||'走势',index=charts.length;
    charts.push({index,kind:'line',title,spec:{title,subtitle:range,unit:item.unit,dates:Array.isArray(item.dates)?item.dates:[],series:Array.isArray(item.series)?item.series:[]}});
    cards.push(vizCard(index,title,`按日走势 · ${vizUnitHint(item.unit)}`));
  });
  breakdowns.forEach(item=>{
    const title=item.title||'构成',index=charts.length;
    charts.push({index,kind:'pie',title,spec:{title,subtitle:`${range} · 构成占比`,unit:item.unit,items:Array.isArray(item.items)?item.items:[]}});
    cards.push(vizCard(index,title,`分类构成 · ${vizUnitHint(item.unit)}`));
  });
  rankings.forEach(item=>{
    const title=item.title||'排行',index=charts.length;
    const items=Array.isArray(item.items)?item.items:[];
    charts.push({index,kind:'bar',title,spec:{title,subtitle:`${range} · 排行`,unit:item.unit,items}});
    cards.push(vizCard(index,title,`排行对比 · ${vizUnitHint(item.unit)}`));
  });
  vizState.data=data;vizState.charts=charts;
  const hasAny=!!(kpis.length||cards.length);
  const body=hasAny
    ?`${kpis.length?`<div class="kpi-grid viz-kpis">${kpis.map((item,index)=>vizKpiCard(item,index===0)).join('')}</div>`:''}${cards.length?`<div class="viz-grid">${cards.join('')}</div>`:empty('所选期间没有可绘制的图表','可以调整结束日期或统计窗口后重试。')}`
    :`<section class="panel">${empty('所选期间没有可视化数据','可以调整结束日期或统计窗口后重试。')}</section>`;
  return heading('数据可视化',`${range} · 共 ${data.days??0} 天 · 币种 ${data.currency||'CNY'}；图表在浏览器本地绘制，导出图片不包含客户信息`,controls,'VISUAL ANALYTICS / 数据可视化')
    +body
    +(notes.length?`<div class="basis viz-notes">${notes.map(note=>E(note)).join('<br>')}</div>`:'');
}
function drawVizCharts(){
  const charts=vizState.charts||[];
  if(!charts.length)return;
  const lib=window.Charts;
  for(const chart of charts){
    const holder=vizHolder(chart.index);if(!holder)continue;
    while(holder.firstChild)holder.removeChild(holder.firstChild);
    if(!lib){holder.appendChild(vizNotice('图表模块 /static/charts.js 未加载，无法绘制；请刷新页面重试。'));continue;}
    try{
      if(chart.kind==='pie')lib.pie(holder,chart.spec);
      else if(chart.kind==='bar')lib.bar(holder,chart.spec);
      else lib.line(holder,chart.spec);
    }catch(error){holder.appendChild(vizNotice(`图表绘制失败：${error.message||error}`));}
  }
}
async function vizExportOne(index,button){
  const chart=(vizState.charts||[])[index];
  if(!chart)throw new Error('图表已刷新，请重新点击导出。');
  if(!window.Charts)throw new Error('图表模块未加载，无法导出。');
  const holder=vizHolder(index);
  if(!holder||!holder.querySelector('svg'))throw new Error('这张图表还没有绘制完成。');
  if(button)button.disabled=true;
  try{await window.Charts.exportPng(holder,vizFileName(chart));toast(`已导出：${chart.title}`);}
  finally{if(button&&button.isConnected)button.disabled=false;}
}
async function vizExportAll(button){
  if(!window.Charts)throw new Error('图表模块未加载，无法导出。');
  const charts=vizState.charts||[];
  if(!charts.length)throw new Error('当前没有可导出的图表。');
  if(vizState.exporting)throw new Error('正在导出，请稍候。');
  vizState.exporting=true;if(button)button.disabled=true;
  let saved=0,failed=0;
  try{
    for(const chart of charts){
      const holder=vizHolder(chart.index);
      if(!holder||!holder.querySelector('svg')){failed++;continue;}
      try{await window.Charts.exportPng(holder,vizFileName(chart));saved++;}
      catch{failed++;}
      await new Promise(resolve=>setTimeout(resolve,180));
    }
  }finally{vizState.exporting=false;if(button&&button.isConnected)button.disabled=false;}
  toast(`已导出 ${saved} 张图表图片${failed?`，${failed} 张失败（可单独重试）`:''}。`,failed>0);
}
// 新监听器注册在保护标记之外，不改动既有 #app 分发链（viz-* 动作原本不在其中）。
$('#app').addEventListener('click',async event=>{
  const button=event.target.closest('[data-action]');
  if(!button||button.disabled)return;
  const action=button.dataset.action;
  if(action!=='viz-refresh'&&action!=='viz-export'&&action!=='viz-export-all')return;
  try{
    if(action==='viz-refresh'){
      state.days=Number($('#viz-days').value)||state.days;
      state.end=$('#viz-end').value;
      if(!state.end)throw new Error('请选择结束日期。');
      await renderPage();
    }
    else if(action==='viz-export')await vizExportOne(Number(button.dataset.chart),button);
    else await vizExportAll(button);
  }catch(error){toast(error.message,true);if(button.isConnected)button.disabled=false;}
});