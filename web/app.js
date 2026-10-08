'use strict';
// Workflow forms and choices come from server definitions. All authorization,
// state checks and accounting happen again in the transaction on the server.
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const E=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function requestKey(){
 if(globalThis.crypto?.randomUUID)return globalThis.crypto.randomUUID();
 if(!globalThis.crypto?.getRandomValues)throw new Error('当前浏览器不支持安全请求标识，请更新浏览器后重试。');
 const bytes=new Uint8Array(16);globalThis.crypto.getRandomValues(bytes);bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
 const h=[...bytes].map(x=>x.toString(16).padStart(2,'0')).join('');return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;
}
// 一次表单操作保留同一请求编号。业务失败会连同回执一起回滚，可修正后沿用；
// 网络中断或响应读取失败不能证明未入账，必须保留编号让服务端回放已提交结果。
// 不在 catch 中换号，也不自动重试；版本冲突须先重新核对原单。
const state={user:null,store:null,stores:[],catalog:null,page:1,q:'',status:'',taskScope:'mine',taskStatus:'open',analytics:null,dates:{},auditFilters:{entity_type:'',entity_id:''},row:null,rows:[],route:'work'};
function clearBusinessViews(){
 if(typeof clearBusinessRecords==='function')clearBusinessRecords();
 if(typeof clearFeedbackSession==='function')clearFeedbackSession();
 state.auditFilters={entity_type:'',entity_id:''};
 if(typeof clearBusinessUXContext==='function')clearBusinessUXContext();
 if(typeof clearModuleUX==='function')clearModuleUX();
 if(typeof clearLiveChoices==='function')clearLiveChoices();
 if(typeof clearBusinessAssistantSession==='function')clearBusinessAssistantSession();
 if(typeof clearDossierGrantsSession==='function')clearDossierGrantsSession();
 if(typeof clearObservationCorrectionsSession==='function')clearObservationCorrectionsSession();
 if(typeof clearRetailGroupSession==='function')clearRetailGroupSession();
 if(typeof clearTransferGoodsRecoverySession==='function')clearTransferGoodsRecoverySession();
 state.claimOrder=null;state.serviceOrder=null;state.serviceOrderCatalog=null;
 if(typeof clearVehicleImportsSession==='function')clearVehicleImportsSession();
 if(typeof clearRetailBundlesSession==='function')clearRetailBundlesSession();
 if(typeof clearRechargeBundleSession==='function')clearRechargeBundleSession();
 if(typeof clearOpeningImportSession==='function')clearOpeningImportSession();
 state.openingCatalog=null;
 if(typeof clearBusinessFinanceSession==='function')clearBusinessFinanceSession();
 state.aftercareOrder=null;
 if(typeof clearVehicleOperationsSession==='function')clearVehicleOperationsSession();
 for(const key of ['row','group','benefits','repairOrder','repairLineHtml','retailOrder','retailLineHtml','invoiceOrder','membershipMember','membershipOrder','membershipRules','reconciliation','clearing','clearingOrigins','intakeRecord','intakeSection','intakeCatalog','intakeList','accountData'])state[key]=null;
 state.rows=[];state.analytics=null;state.invoiceSourcePage=1;state.invoiceOrdersPage=1;
 if(typeof clearWarehouseSession==='function')clearWarehouseSession();
 if(typeof clearMembershipSession==='function')clearMembershipSession();
 if(typeof clearVehicleProcurementSession==='function')clearVehicleProcurementSession();
 if(typeof clearVehicleTransferSession==='function')clearVehicleTransferSession();if(typeof clearVehicleTransportSession==='function')clearVehicleTransportSession();
 if(typeof clearCustomerServiceSession==='function')clearCustomerServiceSession();
 if(typeof clearMastersSession==='function')clearMastersSession();if(typeof clearDictionariesSession==='function')clearDictionariesSession();if(typeof clearVehicleCatalogSession==='function')clearVehicleCatalogSession();if(typeof clearInventoryReportsSession==='function')clearInventoryReportsSession();if(typeof clearRepairMaterialsSession==='function')clearRepairMaterialsSession();if(typeof clearVisitActivitySession==='function')clearVisitActivitySession();if(typeof clearBusinessEntitiesSession==='function')clearBusinessEntitiesSession();if(typeof clearMaterialValueSession==='function')clearMaterialValueSession();if(typeof clearInsuranceSession==='function')clearInsuranceSession();delete state.addonOrder;delete state.addonCatalog;delete state.vehicleIncome;delete state.memberPriceRule;if(typeof clearRepairPackagesSession==='function')clearRepairPackagesSession();delete state.reworkGrant;delete state.reworkLineHtml;if(typeof clearSalesQuotesSession==='function')clearSalesQuotesSession();
 if(typeof clearTransferSession==='function')clearTransferSession();if(typeof clearTransferExceptionsSession==='function')clearTransferExceptionsSession();
 if(typeof clearProcurementSession==='function')clearProcurementSession();
}
function rememberStore(){try{if(state.user&&state.store)sessionStorage.setItem('huakangos.active-store',JSON.stringify({user_id:state.user.id,store:String(state.store)}));}catch(_){/* Storage is optional; API authorization remains authoritative. */}}
function forgetStore(){try{sessionStorage.removeItem('huakangos.active-store');}catch(_){}}
function savedStore(user){try{const value=JSON.parse(sessionStorage.getItem('huakangos.active-store')||'null');if(value?.user_id!==user.id)return null;return value.store==='all'&&user.can_group_summary||user.stores?.some(s=>String(s.id)===value.store)?value.store:null;}catch(_){return null;}}
const roleNames={admin:'系统管理员',clerk:'内勤',general_manager:'总经理',chairman:'董事长',manager:'店长',sales:'销售',inventory:'库管',service:'服务顾问',finance:'财务',auditor:'审计',reception:'前台接待',technician:'维修技师',customer_service:'客服'};
const labels={transfer_reserved:'调拨占用',purchase_return:'采购退车占用',draft:'草稿',submitted:'待审核',approved:'已审核',rejected:'已退回',void:'已作废',available:'可售',reserved:'已预订',sold:'已交车',inactive:'未生效',ordered:'待交车',delivered:'已交车',open:'待处理',done:'已完成',cancelled:'已取消',completed:'已完成',bank:'银行账户',cash:'现金账户',wechat:'微信',alipay:'支付宝',other:'其他',in:'收入',out:'支出',none:'不关联',success:'摘要已生成',not_requested:'规则汇总',failed:'摘要未生成',disabled:'仅本地汇总',pending:'处理中',unconfigured:'未配置摘要服务',reviewing:'复核中',confirmed:'确认问题',dismissed:'正常',resolved:'已处理',high:'优先复核',medium:'建议复核',low:'提醒'};
const legacyNames={vehicles:'整车库存',sales:'原有销售单',repairs:'原有维修单',policies:'原有保险单',cash:'财务流水'};
const categories={sale_collection:'原销售单收款',repair_collection:'原维修单收款',premium_collection:'保费代收',commission:'佣金收款',vehicle_purchase:'车辆采购付款',operating_expense:'经营支出',refund:'原业务单退款',capital:'出资或撤资',loan:'借款或还款',transfer:'内部转账',group_member_topup:'集团会员本金充值',group_member_refund:'集团会员本金退款'};
const sections={overview:'经营总览',sales:'整车销售',inventory:'整车库存',repair:'维修服务',materials:'物资周转',finance:'财务收支',customers:'客户跟进',members:'会员储值',efficiency:'工作协同'};
const b=(act,text,data='',cls='')=>`<button type="button" class="${cls}" data-act="${act}" ${data}>${E(text)}</button>`;
const nav=(url,text,icon='')=>{const active=state.route===url||(url==='analytics/overview'&&(state.route.startsWith('analytics/')||state.route==='module/analytics'));return `<a class="navlink ${active?'active':''}" href="#${url}"${active?' aria-current="page"':''}>${icon?`<span class="navicon">${icon}</span>`:''}${E(text)}</a>`;};
const pill=(key,text)=>`<span class="pill ${['done','completed','approved','available','success'].includes(key)?'good':['cancelled','void','rejected','failed'].includes(key)?'bad':['submitted','refund_pending','cancel_review','overdue'].includes(key)?'warning':'info'}">${E(text||state.catalog?.states[key]||labels[key]||key)}</span>`;
const money=v=>v==null?'—':new Intl.NumberFormat('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(v)/100);
// 金额输入的单一解析口径：屏幕上显示给用户的金额（千分位、货币符号、全角字符）必须能被原样提交。
// 修复前各模块各自用 /^\d+(\.\d{1,2})?$/ 校验，用户按默认值提交（如 145,500.00）必被拒。
const moneyDigits=v=>{
 const s=String(v??'').trim()
  .replace(/[\uFF10-\uFF19]/g,c=>String.fromCharCode(c.charCodeAt(0)-0xFEE0))
  .replace(/[\uFF0E\u3002]/g,'.').replace(/\uFF0C/g,',').replace(/^[¥￥$]\s*/,'');
 // 只去掉完整千分组；1,5、1 2、1.2,3 不能悄悄变成 15、12、1.23。
 if(/^\d{1,3}(?:,\d{3})+(?:\.\d+)?$/.test(s))return s.replaceAll(',','');
 if(/^\d{1,3}(?:[ \u00A0\u202F]\d{3})+(?:\.\d+)?$/.test(s))return s.replace(/[ \u00A0\u202F]/g,'');
 return s;
};
const moneyFen=(value,{label='金额',allowZero=false}={})=>{
 const s=moneyDigits(value).trim();
 if(!/^\d+(\.\d{1,2})?$/.test(s))throw new Error(`${label}应为${allowZero?'非负':'正'}数字，最多两位小数；千分位请按 1,234.56 格式填写。`);
 const [whole,fraction='']=s.split('.');
 const cents=Number(whole)*100+Number(fraction.padEnd(2,'0'));
 if(!Number.isSafeInteger(cents)||cents<0||(!allowZero&&cents<=0)||cents>100000000000)throw new Error(`${label}超出允许范围。`);
 return cents;
};

const number=v=>new Intl.NumberFormat('zh-CN',{maximumFractionDigits:3}).format(Number(v));
const day=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const relativeDay=(n,from=day())=>{const d=new Date(from+'T12:00:00+08:00');d.setUTCDate(d.getUTCDate()+n);return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(d);};
const time=v=>{
 // API timestamp columns are UTC-naive unless an explicit offset is present.
 // Local datetime inputs use their own conversion; business dates stay dates.
 if(typeof v!=='string')return '—';
 const m=/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?(Z|[+-]\d{2}:\d{2})?)?$/.exec(v);
 if(!m)return '—';
 const year=Number(m[1]),month=Number(m[2]),date=Number(m[3]);
 const leap=year%4===0&&(year%100!==0||year%400===0);
 if(year<1||month<1||month>12||date<1||date>[31,leap?29:28,31,30,31,30,31,31,30,31,30,31][month-1])return '—';
 if(m[4]===undefined)return v;
 if(Number(m[4])>23||Number(m[5])>59||Number(m[6]||0)>59)return '—';
 const zone=m[8];
 if(zone&&zone!=='Z'&&(Number(zone.slice(1,3))>23||Number(zone.slice(4,6))>59))return '—';
 const stamp=new Date(v+(zone?'':'Z'));
 return Number.isNaN(stamp.getTime())?'—':stamp.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
};
const heading=(title,subtitle='',right='')=>`<div class="pagehead spread"><div><h1>${E(title)}</h1>${subtitle?`<p class="ux-page-subtitle">${E(subtitle)}</p>`:''}</div><div class="row">${right}</div></div>`;
const panel=(title,body,right='')=>`<section class="panel"><div class="panelhead spread"><h2>${E(title)}</h2>${right}</div><div class="panelbody">${body}</div></section>`;
// Stable roles keep presentation independent of translated headings.
const actionPanel=(body,right='')=>panel('操作',body,right).replace('class="panel"','class="panel" data-panel-role="actions"');
const historyPanel=(title,body,right='')=>panel(title,body,right).replace('class="panel"','class="panel" data-panel-role="history"');
const empty=(title='暂无记录',desc='')=>`<div class="empty"><strong>${E(title)}</strong>${E(desc)}</div>`;
const table=(headers,rows)=>rows.length?`<div class="tablewrap"><table><thead><tr>${headers.map(h=>`<th>${E(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(c=>`<tr>${c.map(v=>`<td>${v??'—'}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:empty();
const pager=(total,page=state.page,size=30)=>`<div class="pagination"><span>共 ${number(total)} 条 · 第 ${page} 页</span><div class="row">${b('page','上一页',`data-page="${page-1}" ${page===1?'disabled':''}`)}${b('page','下一页',`data-page="${page+1}" ${page*size>=total?'disabled':''}`)}</div></div>`;
const storeNotice=()=>state.store==='all'?'<div class="notice">当前为多门店汇总。办理业务时请先选择具体门店。</div>':'';
const full=()=>['admin','manager','finance','auditor'].includes(state.user?.role);
const canWrite=()=>!state.storeSwitch&&state.store!=='all'&&state.user?.role!=='auditor';
const csrf=()=>document.cookie.split('; ').find(x=>x.startsWith('dealer_csrf='))?.split('=').slice(1).join('=')||'';
let toastTimer,renderId=0,storeContextVersion=0;
function requireStoreContext(version,method='GET'){if(version!==storeContextVersion){const error=new Error(method==='GET'?'门店或账号已切换，请在当前门店重新读取。':'门店或账号已切换。原门店的操作可能已提交，请回原门店核对办理结果，勿重复提交。');error.staleContext=true;error.staleMutation=method!=='GET';throw error;}}
function toast(text,error=false){const t=$('#toast');t.textContent=text;t.className='visible'+(error?' error':'');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.className='',6000);}
async function api(path,{method='GET',body,raw=false,store=state.store,storeRequest=false}={}){
 const version=storeContextVersion;
 if(state.storeSwitch&&!storeRequest&&!path.includes('/auth/logout'))throw new Error('正在切换门店，请稍后再办理。');
 const h={'X-App-Request':'1'};if(store!==null&&!path.includes('/auth/login'))h['X-Store-ID']=String(store);
 if(method!=='GET'){h['X-CSRF-Token']=csrf();if(!(body instanceof FormData))h['Content-Type']='application/json';}
 let r;try{r=await fetch(path,{method,credentials:'same-origin',headers:h,body:method==='GET'?undefined:body instanceof FormData?body:JSON.stringify(body||{})});}catch{requireStoreContext(version,method);const error=new Error(method==='GET'?'未连接到服务，请稍后重新读取。':'连接中断，尚不能确认本次办理结果。请保留当前表单和请求编号，先核对原单，勿另建重复操作。');error.unknownResult=method!=='GET';throw error;}
 requireStoreContext(version,method);
 if(!r.ok){let obj;try{obj=await r.json();}catch{obj={detail:'操作未成功，请刷新后核对。'};}
  requireStoreContext(version,method);
  if(r.status===401&&!path.includes('/auth/login')){state.user=null;loginPage();}
  const error=new Error(typeof obj.detail==='string'?obj.detail:'填写内容有误，请核对后提交。');error.status=r.status;
  // The store this page is working in was deactivated (or removed) elsewhere: recover instead of
  // showing a permission error the employee cannot act on.
  if(r.status===409&&typeof obj.detail==='string'&&obj.detail.includes('当前门店已停用'))error.storeUnavailable=true;
  throw error;
 }
 let value;try{value=raw?r:await r.json();}catch{requireStoreContext(version,method);const error=new Error(method==='GET'?'未能读取服务响应，请重新读取。':'服务已响应，但未能读取办理结果。请保留当前表单和请求编号，先核对原单，勿另建重复操作。');error.unknownResult=method!=='GET';throw error;}
 requireStoreContext(version,method);if(!raw&&typeof uxRecordSuccess==='function'){try{uxRecordSuccess(path,method,value);}catch(error){console.warn('提交已成功，但结果提示未能更新。');}}return value;
}
async function download(path,filename){const version=storeContextVersion,r=await api(path,{raw:true});const name=r.headers.get('content-disposition')?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];const blob=await r.blob();requireStoreContext(version);const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name?decodeURIComponent(name):filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1200);}
function modal(title,body,onSubmit){const d=$('#modal');if(typeof disposeWorkForm==='function')disposeWorkForm(d);d.innerHTML=`<div class="modalhead"><h2 id="modal-title">${E(title)}</h2>${b('close','×','','iconbtn ghost')}</div><div class="modalbody">${body}</div>`;if(typeof enhanceWorkForm==='function')enhanceWorkForm(d,title);if(!d.open)d.showModal();if(onSubmit){const form=$('form',d);form.onsubmit=async e=>{e.preventDefault();if(form.dataset.submitting==='true')return;form.dataset.submitting='true';form.setAttribute('aria-busy','true');const submit=$('[type=submit]',form);submit.disabled=true;$('.formerror',form).textContent='';try{await onSubmit(form);}catch(err){$('.formerror',form).textContent=err.message;if(typeof workFormShowError==='function')workFormShowError(form);if(err.staleMutation)toast(err.message,true);}finally{delete form.dataset.submitting;form.removeAttribute('aria-busy');submit.disabled=false;}};}return d;}
function closeModal(){$('#modal').close();}
function loginPage(){storeContextVersion++;if(typeof clearBusinessRecords==='function')clearBusinessRecords();if(typeof clearFeedbackSession==='function')clearFeedbackSession();if(typeof clearBusinessUXContext==='function')clearBusinessUXContext();if(typeof clearLiveChoices==='function')clearLiveChoices();if(typeof clearBusinessAssistantSession==='function')clearBusinessAssistantSession();state.storeSwitch=null;if(typeof clearDossierGrantsSession==='function')clearDossierGrantsSession();state.claimOrder=null;state.serviceOrder=null;state.serviceOrderCatalog=null;if(typeof clearVehicleImportsSession==='function')clearVehicleImportsSession();if(typeof clearRetailBundlesSession==='function')clearRetailBundlesSession();if(typeof clearRechargeBundleSession==='function')clearRechargeBundleSession();if(typeof clearOpeningImportSession==='function')clearOpeningImportSession();state.openingCatalog=null;if(typeof clearBusinessFinanceSession==='function')clearBusinessFinanceSession();state.aftercareOrder=null;if(typeof clearVehicleOperationsSession==='function')clearVehicleOperationsSession();if(typeof clearVehicleProcurementSession==='function')clearVehicleProcurementSession();state.invoiceOrder=null;state.invoiceSourcePage=1;state.invoiceOrdersPage=1;state.membershipOrder=null;state.membership=null;state.membershipRules=null;if(typeof clearMembershipSession==='function')clearMembershipSession();state.intakeRecord=null;state.intakeSection=null;state.intakeCatalog=null;state.intakeList=null;if(typeof clearWarehouseSession==='function')clearWarehouseSession();state.retailOrder=null;state.retailLineHtml=null;state.reconciliation=null;state.clearing=null;state.clearingOrigins=[];forgetStore();if(typeof clearVehicleTransferSession==='function')clearVehicleTransferSession();if(typeof clearVehicleTransportSession==='function')clearVehicleTransportSession();if(typeof clearCustomerServiceSession==='function')clearCustomerServiceSession();if(typeof clearMastersSession==='function')clearMastersSession();if(typeof clearDictionariesSession==='function')clearDictionariesSession();if(typeof clearVehicleCatalogSession==='function')clearVehicleCatalogSession();if(typeof clearInventoryReportsSession==='function')clearInventoryReportsSession();if(typeof clearRepairMaterialsSession==='function')clearRepairMaterialsSession();if(typeof clearVisitActivitySession==='function')clearVisitActivitySession();if(typeof clearBusinessEntitiesSession==='function')clearBusinessEntitiesSession();if(typeof clearMaterialValueSession==='function')clearMaterialValueSession();if(typeof clearInsuranceSession==='function')clearInsuranceSession();delete state.addonOrder;delete state.addonCatalog;delete state.vehicleIncome;delete state.memberPriceRule;if(typeof clearRepairPackagesSession==='function')clearRepairPackagesSession();delete state.reworkGrant;delete state.reworkLineHtml;if(typeof clearSalesQuotesSession==='function')clearSalesQuotesSession();if(typeof clearTransferSession==='function')clearTransferSession();if(typeof clearTransferExceptionsSession==='function')clearTransferExceptionsSession();if(typeof clearProcurementSession==='function')clearProcurementSession();state.typedCatalog=null;state.careCatalog=null;state.procurement=null;closeModal();$('#modal').innerHTML='';state.user=null;state.row=null;state.rows=[];state.group=null;state.benefits=null;state.repairOrder=null;state.repairLineHtml=null;state.accountData=null;state.catalog=null;state.analytics=null;state.stores=[];state.store=null;renderId++;document.title='huakangos · 华慷集团';$('#app').innerHTML=huakangLogin();
 $('form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget,btn=$('button',form);btn.disabled=true;$('.formerror',form).textContent='';try{state.user=await api('/api/auth/login',{method:'POST',body:Object.fromEntries(new FormData(form))});state.store=String(state.user.active_store_id||state.user.stores?.[0]?.id||'');const destination=location.hash.slice(1);history.replaceState(null,'',location.pathname+location.search+('#'+normalizeAppRoute(destination)));await boot();}catch(err){$('.formerror',form).textContent=err.message;}finally{btn.disabled=false;}};}
// 原业务页面保留调用兼容；助手统一由员工进入业务助手后输入。
function handoffButtonHTML(ref,label){
 const workspace=globalThis.AssistantWorkspace;
 if(!workspace||typeof workspace.handoffButton!=='function')return '';
 return workspace.handoffButton({ref:ref,label:label});
}
function shell(){
 leaveBusinessRecordsChart();
 if(state.storeSwitch){storeSwitchShell();return;}
 businessRecordsShell();
}
async function readStoreCatalog(store,storeRequest=false){
 const recordCatalog=await api('/api/business-records/catalog',{store,storeRequest});
 return {recordCatalog,catalog:{kinds:{},master_types:{},states:{},capabilities:{}},typedCatalog:{kinds:{}},careCatalog:{},openingCatalog:{},dossierCatalog:{},legacyCatalogLoaded:false};
}
async function loadCatalog(){Object.assign(state,await readStoreCatalog(state.store));}
function storeSwitchShell(){
 const pending=state.storeSwitch;if(!pending)return;
 const options=state.stores.filter(s=>s.active!==false).map(s=>`<option value="${s.id}" ${String(s.id)===pending.target?'selected':''}>${E(s.name)}</option>`).join('')+(state.user?.can_group_summary?`<option value="all" ${pending.target==='all'?'selected':''}>已授权门店汇总</option>`:'');
 const title=pending.failed?'暂时无法切换门店':pending.recovering?'正在恢复原门店':'正在切换门店';
 $('#app').innerHTML=`<div class="workspace"><header class="topbar"><label class="row storeline">当前门店<select id="store" aria-label="当前门店">${options}</select></label>${b('logout','退出','','ghost')}</header><main id="main" aria-busy="${!pending.failed}">${heading(title)}<div class="notice" role="status">${E(pending.error||'正在重新核对本店岗位和可用业务，完成后打开您选择的页面。')}</div>${pending.failed?b('store-retry','重新读取原门店','','primary'):''}</main></div>`;
 $('#store').onchange=e=>switchStore(e.target.value);
 document.title=title+' · huakangos 华慷集团';
}
async function readStoreContext(store){const user=await api('/api/auth/me',{store,storeRequest:true}),catalogs=await readStoreCatalog(store,true);return {user,...catalogs};}
async function switchStore(target,route=null,notice=''){
 if(!state.user)return;
 const pending={version:++storeContextVersion,target:String(target),previous:String(state.store),route};
 state.storeSwitch=pending;renderId++;closeModal();clearBusinessViews();shell();
 const current=()=>state.storeSwitch===pending&&storeContextVersion===pending.version;
 const commit=async(context,store,nextRoute)=>{if(!current())return;Object.assign(state,context);state.store=store;state.storeSwitch=null;state.page=1;state.q='';state.status='';state.taskScope='mine';state.route=nextRoute;history.replaceState(null,'','#'+nextRoute);rememberStore();shell();await render();if(notice)toast(notice);};
 try{const context=await readStoreContext(pending.target);if(current()){await loadAssistantFeatures({store:pending.target,storeRequest:true});if(current())await commit(context,pending.target,pending.route||assistantDefaultRoute({store:pending.target}));}}
 catch(error){
  if(!current())return;
  // A failed target must not reuse its identity or any partially loaded catalog.
  pending.target=pending.previous;pending.recovering=true;pending.error='切换未完成，正在重新核对原门店。';shell();
  try{const context=await readStoreContext(pending.previous);if(current()){await loadAssistantFeatures({store:pending.previous,storeRequest:true});if(current()){await commit(context,pending.previous,assistantDefaultRoute({store:pending.previous}));toast('切换未完成，已返回原门店。'+error.message,true);}}}
  catch(recoveryError){if(current()){pending.failed=true;pending.recovering=false;pending.error='原门店也暂时无法读取，请重试或重新登录。'+recoveryError.message;shell();}}
 }
}
function activeStoreOptions(list){return (list||[]).filter(store=>store.active!==false);}
function reconcileStore(list){
 // Used while a fresh context is being established (boot, saving a store): pick a usable store
 // before anything is in flight. Runtime recovery goes through switchStore instead, so the
 // context epoch, cached views and role catalogues are reset together.
 const options=activeStoreOptions(list);
 if(!options.length)return null;
 if(options.some(store=>String(store.id)===String(state.store)))return null;
 const fallback=options[0];
 state.store=String(fallback.id);rememberStore();
 return fallback;
}
async function reReadStores(){const user=await api('/api/auth/me',{store:null,storeRequest:true});state.user=user;state.stores=user.stores||[];return activeStoreOptions(state.stores);}
async function boot(){
 state.store=String(state.user.active_store_id||state.user.stores?.[0]?.id||'');
 const previousStore=savedStore(state.user);
 if(previousStore&&previousStore!==state.store&&!state.user.must_change_password){const fallback=state.store;state.store=previousStore;try{state.user=await api('/api/auth/me');}catch(error){if(![403,409].includes(error.status))throw error;state.store=fallback;state.user=await api('/api/auth/me');history.replaceState(null,'','#records-dashboard');}}
 state.taskScope='mine';state.route=currentAppRoute();
 state.dates={date_from:relativeDay(-29),date_to:day()};
 if(state.user.must_change_password){state.stores=state.user.stores||[];state.store=String(state.user.active_store_id||state.stores[0]?.id||'');state.catalog={kinds:{},master_types:{}};shell();$('#main').innerHTML=heading('设置个人密码','首次登录，请先修改初始密码。');await passwordDialog(true);return;}
 await loadAssistantFeatures();
 const stores=await api('/api/stores',{store:null});state.stores=stores.items;if(!state.store)state.store=String(stores.active_store_id||stores.items.find(s=>s.active)?.id||'');const moved=reconcileStore(state.stores);await loadCatalog();rememberStore();shell();await render();if(moved)toast(`原门店已停用，已切换到「${moved.name}」。请核对右上角门店后再办理。`);
}
// V2: the operating dashboard is the default; AI remains an explicit entry.
function assistantFeatures(){return state.assistantFeatures||null;}
function assistantDefaultRoute(){return 'records-dashboard';}
async function loadAssistantFeatures(options={}){
 const version=storeContextVersion;
 try{const view=await api('/api/business-assistant/workspace',options);if(version===storeContextVersion){state.assistantFeatures=(view&&view.features)||{};state.assistantFeaturesError='';}}
 catch(error){if(version===storeContextVersion){state.assistantFeatures=null;state.assistantFeaturesError=(error&&error.message)||'读取工作区开关失败';}}
 return state.assistantFeatures;
}
async function bootDefaultRoute(){await loadAssistantFeatures();return assistantDefaultRoute();}
// Old bookmarks cannot reopen retired modules or load their catalogues.
function normalizeAppRoute(route){
 return /^(?:records-(?:dashboard|sales(?:\/\d+)?|after-sales|customers|finance|manual|settings)|business-assistant|feedback|users|stores|audit)$/.test(route)?route:'records-dashboard';
}
function currentAppRoute(){
 const route=normalizeAppRoute(location.hash.slice(1));
 if(location.hash!=='#'+route)history.replaceState(null,'',location.pathname+location.search+'#'+route);
 return route;
}
function go(requested){const route=normalizeAppRoute(requested);if(state.storeSwitch){state.storeSwitch.route=route;history.replaceState(null,'','#'+route);return;}if(location.hash==='#'+route){state.route=route;state.page=1;state.q='';state.status='';render();}else location.hash=route;}
window.addEventListener('hashchange',()=>{if(!state.user)return;const route=currentAppRoute();if(state.storeSwitch){state.storeSwitch.route=route;return;}state.route=route;state.page=1;state.q='';state.status='';state.auditFilters={entity_type:'',entity_id:''};state.analytics=null;closeModal();shell();render();});
async function render(){if(typeof leaveBusinessRecordsChart==='function')leaveBusinessRecordsChart();if(state.storeSwitch){storeSwitchShell();return;}const current=++renderId;const [type,key]=state.route.split('/');if(type!=='business-assistant'&&typeof leaveBusinessAssistantView==='function')leaveBusinessAssistantView();$('#main').innerHTML='<div class="loading">正在读取…</div>';state.row=null;try{let html;
 if(type.startsWith('records-'))html=await businessRecordsPage(type,key);
 else if(type==='business-assistant')html=await businessAssistantPage();
 else if(type==='feedback')html=await feedbackPage();
 else if(type==='users')html=await usersPage();
 else if(type==='stores')html=await storesPage();
 else if(type==='audit')html=await auditPage();
 else throw new Error('页面已停用，请返回经营看板。');
 if(current!==renderId)return;
 $('#main').innerHTML=html;
 if(type.startsWith('records-'))mountBusinessRecords();
 bindFilters();
 if(type==='feedback')bindFeedbackPage();
 if(type==='audit')bindAuditFilters();
 if(type==='business-assistant')bindBusinessAssistantPage();
 document.title=($('h1')?.textContent||'经营看板')+' · huakangos 华慷集团';

 }catch(err){if(current===renderId&&state.user){
  if(err.storeUnavailable){
   try{
    const options=await reReadStores();if(current!==renderId)return;
    if(options.length){
     await switchStore(String(options[0].id),state.route,`当前门店已停用，已切换到「${options[0].name}」。请核对右上角门店后再办理。`);
     return;
    }
    $('#main').innerHTML=`<div class="panel errorpage"><h2>暂时无法显示</h2><p class="notice error">当前账号还没有可用门店：请在“门店设置”启用门店，或让管理员分配门店。</p>${b('refresh','重新读取')}</div>`;return;
   }catch(recoveryError){if(current!==renderId)return;$('#main').innerHTML=`<div class="panel errorpage"><h2>暂时无法显示</h2><p class="notice error">${E(recoveryError.message)}</p>${b('refresh','重新读取')}</div>`;return;}
  }
  $('#main').innerHTML=`<div class="panel errorpage"><h2>暂时无法显示</h2><p class="notice error">${E(err.message)}</p>${b('refresh','重新读取')}</div>`;}}}
function searchBar(extra=''){return `<form id="filters" class="filterbar"><label class="search">搜索<input name="q" value="${E(state.q)}" placeholder="输入姓名、单号或关键词"></label>${extra}${b('clearfilter','重置')}</form>`;}
function bindFilters(){const f=$('#filters');if(f){let timer;const input=f.elements.q;if(input){input.addEventListener('input',e=>{state.q=input.value;clearTimeout(timer);if(e.isComposing)return;timer=setTimeout(()=>{if(f.isConnected)f.requestSubmit();},300);});input.addEventListener('compositionend',()=>{clearTimeout(timer);state.q=input.value;timer=setTimeout(()=>{if(f.isConnected)f.requestSubmit();},300);});}f.addEventListener('change',e=>{if(e.target.tagName==='SELECT')f.requestSubmit();});}if(f)f.onsubmit=async e=>{e.preventDefault();const values=Object.fromEntries(new FormData(f));state.q=values.q||'';state.status=values.state||'';state.page=1;const focus=document.activeElement===f.elements.q;await render();if(focus){const input=$('#filters [name=q]');if(input){input.value=state.q;input.focus();}}};const df=$('#datefilters');if(df)df.onsubmit=e=>{e.preventDefault();state.dates=Object.fromEntries(new FormData(df));state.analytics=null;state.page=1;render();};}
function employeeQuickActions(){
 const kinds=state.catalog?.kinds||{},role=state.user.role;
 const order={sales:['lead','order','insurance','addon','agency'],reception:['lead','repair','callback'],service:['repair','insurance','callback'],inventory:['vehicle_procurement','procurement','material_issue','material_return','stock_count'],finance:['invoice','business_finance'],customer_service:['callback','complaint']}[role]||['lead','order','repair','procurement','invoice'];
 const names={lead:'登记接待',order:'新建预订合同',repair:'开维修工单',procurement:'物资采购',vehicle_procurement:'整车采购',invoice:'申请开票'};
 return order.filter(k=>kinds[k]?.can_create).map(k=>b('newcase',names[k]||'新建'+kinds[k].label,`data-kind="${k}" ${canWrite()?'':'disabled'}`)).join('')+(state.typedCatalog?.kinds.vehicle_models?.can_write&&['admin','manager','inventory'].includes(role)?b('catalog-entry','新增车型',canWrite()?'':'disabled'):'');
}
async function workPage(){const data=await api('/api/flow/tasks?'+moduleTaskQuery());state.rows=data.items;const quick=employeeQuickActions();
 return huakangPageHeading('我的工作','',b('refresh','刷新'),'work')+storeNotice()+uxWorkIntro(data)+moduleWorkFilters()+searchBar()+
 `<div class="spread filterbar"><div class="row">${b('taskscope','我的任务','data-scope="mine"',state.taskScope==='mine'?'primary':'')}${full()?b('taskscope','全部任务','data-scope="all"',state.taskScope==='all'?'primary':''):''}<select id="taskstatus" aria-label="任务状态"><option value="open" ${state.taskStatus==='open'?'selected':''}>待处理</option><option value="done" ${state.taskStatus==='done'?'selected':''}>已处理</option><option value="cancelled" ${state.taskStatus==='cancelled'?'selected':''}>已取消</option></select></div><div class="row">${quick}</div></div>`+
 `<section class="panel work-table">${table(['需要做什么','关联业务','负责人','计划日期','当前进度','操作'],data.items.map(t=>[`<strong>${E(t.title)}</strong>${t.blocked?`<span class="cellsecond wrap">${E(t.block_reason)}</span>`:''}`,`<span class="wrap">${E(t.case_title)}</span><span class="cellsecond">${E(t.case_number)}</span>`,E(t.assignee_name),`${E(t.due_date)} ${t.overdue?pill('overdue','已过计划日期'):''}`,pill('',t.state_label),b('open',t.blocked?'查看缺少的条件':'接着办理',`data-route="${E(uxTaskRoute(t))}"`,'primary')]))}${pager(data.total)}</section><div class="work-cards">${data.items.map(t=>`<article class="panel work-card"><div class="spread"><h2>${E(t.title)}</h2>${t.overdue?pill('overdue','已过计划日期'):pill(t.status)}</div><p>${E(t.case_title)}</p><div class="spread"><span>${E(t.assignee_name)}</span><span>${E(t.due_date)}</span></div>${t.blocked?`<div class="notice">${E(t.block_reason)}</div>`:''}${b('open',t.blocked?'查看缺少的条件':'接着办理',`data-route="${E(uxTaskRoute(t))}"`,'primary')}</article>`).join('')||empty('目前没有待处理任务')}${pager(data.total)}</div>`;
}
async function casesPage(kind){const spec=state.catalog.kinds[kind];if(!spec)throw new Error('当前账号无法查看此业务。');const data=await api(`/api/flow/cases?kind=${encodeURIComponent(kind)}&q=${encodeURIComponent(state.q)}&state=${encodeURIComponent(state.status)}&page=${state.page}`);state.rows=data.items;
 return heading(spec.label,'',spec.can_create?b('newcase','新建'+spec.label,`data-kind="${kind}" ${canWrite()?'':'disabled'}`,'primary'):'')+storeNotice()+searchBar(`<label>进度<select name="state"><option value="">全部</option><option value="open" ${state.status==='open'?'selected':''}>未完成</option>${Object.entries(state.catalog.states).map(([k,v])=>`<option value="${k}" ${state.status===k?'selected':''}>${E(v)}</option>`).join('')}</select></label>`)+`<section class="panel">${table(['业务单号','客户或事项','门店','负责人','日期','状态',...(data.items.some(x=>'amount_cents'in x)?['约定金额（元）']:[]),'操作'],data.items.map(r=>[b('open',r.number,`data-route="case/${r.id}"`,'link'),`<span class="wrap">${E(r.title)}</span>`,E(r.store_name),E(r.owner_name),E(r.business_date),pill(r.state,r.state_label),...(data.items.some(x=>'amount_cents'in x)?[`<span class="numeric">${money(r.amount_cents)}</span>`]:[]),b('open','办理',`data-route="case/${r.id}"`)]))}${pager(data.total)}</section>`;
}
const dataLabels={labor:'工时金额（元）',parts:'配件金额（元）',discount:'优惠（元）',labor_cost:'工时直接成本（元）',commission:'预计佣金（元）',quantity:'数量',counted:'实盘数量',unit_cost:'采购单价（元）',released_date:'实际接车日期',model:'订购车型',need:'购车需求',source:'客户来源',note:'说明',result:'处理结果',problem:'客户描述',repair_type:'维修类型',plate:'车牌号',work:'施工或办理项目',payer:'结算方',insurer:'保险公司',policy_number:'保单号',start_date:'保险生效日',end_date:'保险到期日',supplier:'供应商',topic:'回访事项',plan:'处理方案',reason:'原因',credit_due:'月结付款日',delivery_due:'预计交付日',release_date:'实际接车日',quantity_milli:'数量',unit_cost_cents:'单价（元）',labor_cents:'工时金额（元）',parts_cents:'配件金额（元）',discount_cents:'优惠（元）',labor_cost_cents:'工时直接成本（元）',commission_cents:'预计佣金（元）',addon:'精品加装',insurance:'本店保险',agency:'代办服务',amount_cents:'约定金额（元）',counted_milli:'实盘数量',started:'已开工',invoice_number:'发票号码',invoice_date:'开票日期'};
function facts(obj,whitelist=null){return `<div class="facts">${Object.entries(obj).filter(([k,v])=>v!==null&&v!==''&&typeof v!=='object'&&(!whitelist||whitelist[k])).map(([k,v])=>`<div class="fact"><div class="key">${E(whitelist?.[k]||dataLabels[k]||k)}</div><div class="value">${E(typeof v==='boolean'?(v?'是':'否'):(k.endsWith('_cents')||['labor','parts','discount','labor_cost','commission','unit_cost'].includes(k))?money(v):(k.endsWith('_milli')||['quantity','counted'].includes(k))?number(v/1000):v)}</div></div>`).join('')}</div>`;}
function taskList(tasks){return `<div class="tasklist">${tasks.map(t=>`<div class="taskitem"><span class="taskstate ${t.status}">${t.status==='done'?'✓':t.status==='cancelled'?'－':'○'}</span><div class="description"><strong>${E(t.title)}</strong><p>${E(t.assignee_name)} · ${E(t.role_label)} · ${E(t.due_date)}</p>${t.block_reason?`<p>${E(t.block_reason)}</p>`:''}</div>${pill(t.status)}${t.status==='open'?handoffButtonHTML('task:'+t.id,t.title):''}${t.status==='open'&&['admin','manager'].includes(state.user.role)&&canWrite()?b('assign','转交',`data-id="${t.id}"`,'ghost'):''}</div>`).join('')}</div>`;}
function fileList(files){return files.length?files.map(f=>`<div class="filerecord managed-file"><span class="fileicon">文</span><div class="filetext"><strong>${E(f.name)}</strong><p>${E(state.catalog.upload_categories[f.category]||state.catalog.document_types[f.category]||'业务文件')} · ${f.generated?'系统生成':'上传留档'} · ${time(f.created_at)}</p>${f.generated?`<p>${f.template_approved?'已启用模板':'样式草稿'} · 模板版本 ${f.template_version}</p>`:''}${f.source_file_id?`<p>签回对应文件编号：${f.source_file_id}</p>`:''}</div>${f.security?`<div class="stack"><span class="muted">${E(f.security.label)}</span>${b('filescaninfo','扫描记录',`data-id="${f.id}"`)}</div>`:''}${b('downloadfile','下载',`data-id="${f.id}" ${f.security&&!f.security.can_use?'disabled':''}`)}</div>`).join(''):empty('暂无文件','上传业务凭据或生成确认单。');}
function inspectionBanner(row){
 if(row.kind!=='order'||!['reserved','executing'].includes(row.state))return '';
 if(row.flow_version===1)return '<div class="notice error"><strong>旧版订单交付已暂停</strong><p>旧文本检查不能作为合格依据，请管理员评审升级及重新检查方案。</p></div>';
 const outcome=row.data.inspection_status,inspection=row.data.inspection||{};
 const status={failed:['error','检查不合格，禁止出库','请先处理缺陷，再由检查岗位复检。'],awaiting_reinspection:['warn','缺陷已处理，等待复检','整改记录不等于检查合格，复检通过前不能出库。'],passed:['','交车检查合格','仍需完成合同、收款及相关服务，方可办理出库。']}[outcome];
 if(!status)return row.state==='executing'?'<div class="notice"><strong>尚未完成交车检查</strong><p>检查明确合格后才可办理出库。</p></div>':'';
 return `<div class="notice ${status[0]}"><strong>${E(status[1])}</strong><p>${E(status[2])}</p>${inspection.result?`<p>第 ${E(inspection.round)} 轮检查：${E(inspection.result)}</p>`:''}</div>`;
}
async function casePage(id){const r=await api('/api/flow/cases/'+id);state.row=r;const basic={门店:r.store_name,负责人:r.owner_name,客户:r.customer?.name||'',联系电话:r.customer?.phone||'',业务日期:r.business_date,计划日期:r.due_date||''};const actions=r.actions||[];const primary=actions.filter(a=>!['close','cancel','cancel_request','reject','rework','cancel_reject','revise'].includes(a.key)),secondary=actions.filter(a=>!primary.includes(a));
 const actionHTML=list=>list.map(a=>`<div class="actioncard">${b('caseaction',a.label,`data-key="${a.key}" ${!canWrite()||!a.enabled?'disabled':''}`,a.enabled?'primary':'')}<p>${E(a.reason||a.confirm||'')}</p></div>`).join('');
 const docKinds=r.kind==='order'?['contract','handover','business']:r.kind==='repair'?['repair_sheet','business']:['business'];const allowedDoc=docKinds.filter(k=>!['inventory','technician','reception','customer_service'].includes(state.user.role)||k==='business');
 const flow=r.kind==='lead'?['接待登记','分派沟通','回访或意向','车辆预订']:r.kind==='order'?['订单确认','配车与并行办理','交付检查','出库提车']:r.kind==='repair'?['报价授权','领料施工','完工质检','结算接车']:[];
 return `<div class="back">${b('open','‹ 返回'+r.kind_label,`data-route="cases/${r.kind}"`,'link')}</div>`+heading(r.title,r.number,`${pill(r.state,r.state_label)}${handoffButtonHTML('object:case:'+r.id,r.title)}${b('refresh','刷新')}`)+inspectionBanner(r)+storeNotice()+
 (state.store==='all'?`<div class="notice">${E(r.store_name)}的业务单。${b('switchcase','切换到此门店办理',`data-store="${r.store_id}" data-id="${r.id}"`,'link')}</div>`:'')+
 (r.kind==='member_pricing_rule'&&r.flow_version===1&&r.data.member_price_rule_id?panel('会员价格办理',b('open','核对本店价格版本及独立批准',`data-route="member-pricing/${r.data.member_price_rule_id}"`)):'')+(r.kind==='vehicle_income'&&r.flow_version===1?panel('整车其他收入办理',b('open','查看原往来依据、批准及实际收退',`data-route="vehicle-income/${r.id}"`)):'')+(r.kind==='observation_correction'?panel('资料纠正办理',b('open','查看原依据及独立复核',`data-route="observation-corrections/cases/${r.id}"`)):'')+(r.kind==='retail_group_rule'?panel('精品权益商品规则',b('open','查看适用范围及独立复核',`data-route="retail-group-rule/${r.id}"`)):'')+(r.kind==='business_entity'?panel('经营主体配置',b('open','查看来源资料及独立复核',`data-route="business-entity/${r.id}"`)):'')+(r.kind==='insurance'&&r.flow_version===3?panel('保险明细办理',b('open','查看原保单、实际保费与佣金结算','data-route="insurance-orders/'+r.id+'"')):'')+(r.kind==='addon'&&r.flow_version===3?panel('加装明细办理',b('open','查看商品、安装、检查及原路退回','data-route="addon-orders/'+r.id+'"')):'')+(r.kind==='order'&&[3,4].includes(r.flow_version)?panel('车辆报价与预订',b('open','查看当前报价、客户确认与交车','data-route="sales-quotes/'+r.id+'"')):'')+((r.kind==='agency'&&r.flow_version===3||r.kind==='other_income'&&r.flow_version===2)?panel('明细服务办理',b('open','查看授权报价、办理与原款结算','data-route="service-orders/'+r.id+'"')):'')+(r.kind==='claim'?panel('理赔办理',b('open','查看核价、外部结果及原款报销',`data-route="claims/${r.id}"`)):'')+(r.kind==='recharge_bundle'?panel('会员组合充值',b('open','查看原本金与赠品整份办理',`data-route="recharge-bundle-order/${r.id}"`)):'')+(r.kind==='opening_import'?panel('正式期初核验',b('open','查看分岗核验与原资料',`data-route="opening-batch/${r.id}"`)):'')+(r.kind==='business_finance'?panel('业务财务办理',b('open','查看原预收、月结分配与更正',`data-route="business-finance-order/${r.id}"`)):'')+(r.kind==='aftercare'?panel('售后办理',b('open','查看保留费用、实物与原路退回',`data-route="aftercare/${r.id}"`)):'')+(r.kind==='vehicle_operations'?panel('整车出退库办理',b('open','查看实车位置与原单',`data-route="vehicle-operation/${r.id}"`)):'')+(r.kind==='vehicle_procurement'?panel('整车采购办理',b('open','查看计划、请款与实际到货',`data-route="vehicle-procurement/${r.id}"`)+b('open','车辆请款与交接清单',`data-route="vehicle-imports/${r.id}"`)):'')+(r.kind==='service_intake'&&r.data.gate_visit_id?panel('实际进出厂',b('open','查看原事实与继续办理',`data-route="gate-visits/${r.data.gate_visit_id}"`)):'')+(r.kind==='service_intake'&&(r.data.rework_id||r.data.appointment_id)?panel('维修接待',b('open','查看到店或原单返修',`data-route="service-intake/${r.data.rework_id?'reworks':'appointments'}/${r.data.rework_id||r.data.appointment_id}"`)):'')+(r.kind==='membership'?panel('会员独立办理',b('open','查看卡、续会及本单进度',`data-route="membership-order/${r.id}"`)):'')+(r.kind==='warehouse'?panel('仓储作业',b('open','办理实物库位与差异',`data-route="warehouse/${r.id}"`)):'')+((['purchase','material_issue','material_return','stock_count','procurement','material_transfer','repair','retail'].includes(r.kind)||r.kind==='addon'&&r.flow_version===3)&&canWrite()&&['admin','inventory'].includes(state.user.role)?panel('实际收发库位',b('open','准备物资库位',`data-route="warehouse-allocation/${r.id}"`)):'')+(r.kind==='invoice'&&r.flow_version===3?panel('发票协同',b('open','办理外部结果与原票冲红',`data-route="invoices/${r.id}"`)):'')+(['order','repair','addon','agency','retail','other_income','vehicle_income'].includes(r.kind)&&full()?panel('原单发票',(invoiceFinance()?b('invoice-new','申请本业务开票',`data-source="${r.id}" ${canWrite()?'':'disabled'}`):'')+b('open','查看已有申请与冲红','data-route="invoices"')):'')+(r.kind==='retail'?panel('精品办理',b('open','查看报价、交付及退货',`data-route="retail/${r.id}"`)):'')+(r.kind==='reconciliation'&&r.data.reconciliation_id?panel('对账办理',b('open','查看冻结来源与差异',`data-route="reconciliation/${r.data.reconciliation_id}"`)):'')+(r.kind==='interstore_clearing'&&r.data.clearing_id?panel('店间清算办理',b('open','查看双方实际收付款',`data-route="clearing/${r.data.clearing_id}"`)):'')+(r.kind==='customer_care'?panel('客户服务办理',b('open','查看诉求、跟进与结案',`data-route="customer-service/${r.id}"`)):'')+(r.kind==='repair'&&[3,4].includes(r.flow_version)?panel('维修明细办理',b('open','查看报价、施工与多方结算',`data-route="repair-orders/${r.id}"`)):'')+(r.kind==='vehicle_transfer'&&r.data.vehicle_transfer_id?panel('整车调拨办理',b('open','查看车辆与双方交接',`data-route="vehicle-transfers/${r.data.vehicle_transfer_id}"`)):'')+(r.kind==='procurement'?panel('采购办理',b('open','查看采购明细、验收与收付款',`data-route="procurement/${r.id}"`)):'')+(r.kind==='material_transfer'&&r.data.transfer_id?panel('调拨办理',b('open','查看双方调拨与实物验收',`data-route="transfers/${r.data.transfer_id}"`)):'')+(flow.length?`<div class="steps">${flow.map(s=>`<span class="step">${E(s)}</span>`).join('')}</div>`:'')+
 `<div class="detailgrid"><div class="stack">${panel('业务资料',facts(basic)+('amount_cents'in r?`<div class="pair-totals kpis"><div><div class="muted">约定金额（元）</div><h2>${money(r.amount_cents)}</h2></div>${r.kind==='procurement'?'':`<div><div class="muted">累计已收或已结（元）</div><h2>${money(r.paid_cents)}</h2></div>`}</div>`:'')+(Object.keys(r.data).some(k=>dataLabels[k])?'<hr class="separator">'+facts(r.data,dataLabels):'')+(r.parent_id?`<p class="mt18">${b('open','查看来源业务',`data-route="case/${r.parent_id}"`,'link')}</p>`:''))}
 ${r.customer_id&&['admin','manager','service','customer_service','finance','auditor','sales','reception'].includes(state.user.role)?panel('集团会员',b('open','查询会员与办理本金结算',`data-route="group/${r.customer_id}/${r.id}"`)):''}
 ${(r.aftercare_links||[]).length?panel('关联退订退车与退费',r.aftercare_links.map(c=>`<div class="listrow"><div><strong>${E(c.number)}</strong><p>${pill(c.state,c.state_label)}</p></div>${b('open','查看售后进度',`data-route="aftercare/${c.id}"`)}</div>`).join('')):''}
 ${r.children.length?panel('关联业务',table(['事项','状态','负责人',''],r.children.map(c=>[E(c.kind_label),pill(c.state,c.state_label),E(c.owner_name),b('open','查看',`data-route="case/${c.id}"`)]))):''}
 ${panel('文件与凭据',`<div class="filetools">${typeof dossierCaseLink==='function'?dossierCaseLink(r):''}${canWrite()?b('upload','上传文件','','primary'):''}${canWrite()?allowedDoc.map(k=>b('generatedoc','生成'+state.catalog.document_types[k],`data-kind="${k}"`)).join(''):''}</div>${fileList(r.files)}`)}
 ${r.payments?.length?panel('实际收退款记录',table(['凭证号','方向','金额（元）','登记时间'],r.payments.map(p=>[E(p.reference),E(labels[p.direction]),money(p.amount_cents),E(p.business_date)]))):''}
 ${historyPanel('操作留痕',`<div class="timeline">${r.events.map(e=>`<div class="timelineitem"><strong>${E(e.label)}</strong><div class="time">${E(e.actor_name)} · ${time(e.occurred_at)}</div>${e.from!==e.to?`<p>${E(e.from)} → ${E(e.to)}</p>`:''}${Object.keys(e.detail||{}).some(k=>dataLabels[k])?`<details><summary>查看记录</summary><div class="detailsbody">${facts(e.detail,dataLabels)}</div></details>`:''}</div>`).join('')}</div>${r.event_total>100?`<p class="muted">显示最近100条，共${r.event_total}条；完整记录见操作记录。</p>`:''}`)}
 </div><div class="stack">${actionPanel(actions.length?`<div class="actions">${actionHTML(primary)}${secondary.length?`<details><summary>其他操作</summary><div class="detailsbody actions">${actionHTML(secondary)}</div></details>`:''}</div>`:empty('当前没有待执行动作','可查看关联任务的进度。'))}${panel('分工与交接',taskList(r.tasks))}</div></div>`;
}
const lookupTypes=new Set(['employee','vehicle','file','signed_file','handover_file','payment','stock_issue','billable_case','account','item','member','customer']);
// 动作字段可以声明它接受的凭据类别（app/flow_specs.py 的 file_category），界面据此预选并说明。
const fileRequirementKeys=f=>Array.isArray(f.file_category)?f.file_category.join(','):(f.file_category||'');
const uploadCategoryLabel=key=>state.catalog?.upload_categories?.[key]||labels[key]||key;
const fileRequirementHint=f=>{const keys=fileRequirementKeys(f).split(',').filter(Boolean);return keys.length?`<div class="fieldhelp">本步需要“${keys.map(uploadCategoryLabel).join('、')}”类别的凭据。</div>`:'';};
const defaultValue=f=>f.type==='future_date'?relativeDay(1):f.type==='date'?day():f.type==='bool'?['active','contact_allowed'].includes(f.key):f.type==='money_zero'||f.type==='quantity_zero'?'0':'';
async function fieldHTML(f,value=defaultValue(f),caseId=null){const req=f.required?'required':'',id='field-'+f.key,wide=['textarea'].includes(f.type);let control;
 if(f.type==='bool')return `<label class="checklabel ${wide?'wide':''}"><input type="checkbox" name="${f.key}" ${value?'checked':''}>${E(f.label)}</label>`;
 if(f.type==='textarea')control=`<textarea id="${id}" name="${f.key}" ${req} maxlength="${f.max_length||2000}" rows="${f.key==='clauses'?10:4}">${E(value)}</textarea>`;
 else if(f.type==='select')control=`<select id="${id}" name="${f.key}" ${req} ${f.searchable?'data-search-select':''}><option value="">请选择</option>${(f.options||[]).map(o=>{const val=typeof o==='object'?o.value:o,label=typeof o==='object'?o.label:labels[o]||o;return `<option value="${E(val)}" ${String(val)===String(value)?'selected':''}>${E(label)}</option>`;}).join('')}</select>`;
 else if(lookupTypes.has(f.type)){
   const p=new URLSearchParams();if(caseId)p.set('case_id',caseId);if(f.lookup_action)p.set('action',f.lookup_action);let items=[],warning='';try{const data=await api(`/api/flow/lookup/${f.type}?${p}`);items=data.items;if(data.has_more)warning='可输入关键词查找更多记录。';}catch(err){warning=err.message;}
   control=`<div class="lookup" data-kind="${f.type}" data-case="${caseId||''}"${f.lookup_action?` data-action="${E(f.lookup_action)}"`:''}><input type="search" data-lookup-query autocomplete="off" role="combobox" aria-expanded="false" aria-controls="${id}-options" placeholder="查找${E(f.label)}" aria-label="查找${E(f.label)}" value="${E(items.find(i=>String(i.id)===String(value))?.label||'')}" ${req}><select hidden id="${id}" name="${f.key}"><option value=""></option>${items.map(i=>`<option value="${i.id}" ${String(i.id)===String(value)?'selected':''}>${E(i.label)}</option>`).join('')}</select><div class="lookup-options" id="${id}-options" role="listbox" hidden></div>${['file','signed_file','handover_file'].includes(f.type)&&caseId?inlineFileControls(caseId,f.type,fileRequirementKeys(f)):''}${warning?`<div class="fieldhelp">${E(warning)}</div>`:''}${fileRequirementHint(f)}</div>`;
 }else{const numeric=['money','money_zero','quantity','quantity_zero','int','number'].includes(f.type);const date=['date','future_date'].includes(f.type);control=`<input id="${id}" name="${f.key}" type="${date?'date':f.type==='password'?'password':'text'}" value="${E(value)}" ${req} ${numeric?'inputmode="decimal"':''} ${f.type==='future_date'?`min="${day()}"`:''} ${f.type==='password'?'minlength="12" maxlength="128" autocomplete="new-password"':'maxlength="180"'}>`;}
 // 凭据字段就地说明本步需要哪一类，界面下拉与后端校验使用同一批词（app/flow_specs.UPLOAD_CATEGORY_LABELS）。
 if(!lookupTypes.has(f.type))control+=fileRequirementHint(f);
 return `<label class="${wide?'wide':''}">${E(f.label)}${f.required?' <span class="required" aria-hidden="true">*</span>':''}${control}</label>`;
}
function formValues(form,fields){const fd=new FormData(form),out={};for(const f of fields){const value=fd.get(f.key);out[f.key]=f.type==='bool'?value!==null:lookupTypes.has(f.type)||['int','number'].includes(f.type)?value?Number(value):null:String(value??'').trim();}return out;}
async function formDialog(title,fields,values,onSave,options={}){
 const html=(await Promise.all(fields.map(f=>fieldHTML(f,values[f.key]??defaultValue(f),options.caseId)))).join('');
 let warehouse;
 const dialog=modal(title,`<form>${options.notice?`<div class="notice ${options.warn?'warn':''}">${E(options.notice)}</div>`:''}<div class="formgrid">${html}</div>${options.extra||''}<div class="mt18 formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button type="submit" class="primary">${E(options.submit||'确认保存')}</button></div></form>`,async form=>{if(warehouse)await warehouse.assertReady();const result=await onSave(formValues(form,fields),form);closeModal();state.analytics=null;const nextRoute=options.nextRoute?.(result);if(nextRoute){state.row=null;go(nextRoute);}else if(state.user)await render();toast((typeof options.success==='function'?options.success(result):options.success)||'已保存');});
 if(typeof enhanceOptionalNotes==='function')enhanceOptionalNotes(dialog,fields,values);
 if(options.warehouse)warehouse=mountWarehousePreparation(dialog.querySelector('form'),options.warehouse);
 return dialog;
}
async function createCase(kind){if(kind==='procurement')return procurementNew();if(kind==='vehicle_procurement')return vpNew();if(kind==='invoice')return go('invoices');if(kind==='business_finance')return go('business-finance');if(kind==='insurance')return insuranceOrderNew();if(kind==='addon')return addonNew();if(kind==='agency')return serviceOrderNew();if(kind==='order')return salesQuoteNew();if(!canWrite())throw new Error('请先选择具体门店。');const spec=state.catalog.kinds[kind];if(!spec?.can_create)throw new Error('当前岗位不能新建此业务。');if(spec.fields.some(f=>f.key==='customer_name'))return createCustomerChoiceCase(kind);const request_id=requestKey();await formDialog('新建'+spec.label,spec.fields,{},async values=>{const r=await api('/api/flow/cases',{method:'POST',body:{request_id,kind,values}});go('case/'+r.id);},{submit:'建立业务'});}
async function caseAction(key){const row=state.row,a=row?.actions.find(x=>x.key===key);if(!a||!a.enabled)throw new Error(a?.reason||'此动作当前不可执行。');if(row.kind==='lead'&&row.flow_version===2&&key==='reserve')return salesQuoteNew(row.id);const request_id=requestKey();const defaults={};if(row.kind==='lead'&&key==='remind'){defaults.customer_phone=row.customer?.phone||'';a.fields=a.fields.map(f=>f.key==='customer_phone'?{...f,required:!row.customer?.phone}:f);}if(a.fields.some(f=>f.key==='amount'))defaults.amount=((row.amount_cents-row.paid_cents)/100).toFixed(2);await formDialog(a.label,a.fields,defaults,values=>api(`/api/flow/cases/${row.id}/actions/${key}`,{method:'POST',body:{request_id,version:row.version,values}}),{caseId:row.id,notice:a.confirm||'',warn:!!a.confirm,submit:a.label,nextRoute:result=>result?.can_view===false?'cases/'+row.kind:null,success:result=>result?.can_view===false?`${a.label}已完成，后续由${result.owner_name||'接手员工'}办理；已返回业务列表。`:'操作已记录，相关任务已更新'});}
async function uploadDialog(initialCategory=null){const row=state.row;const categories=Object.entries(state.catalog.upload_categories).filter(([k])=> !(['receipt','invoice','procurement_contract'].includes(k)&&!['admin','manager','finance'].includes(state.user.role))&&!(['signed_contract','signed_handover'].includes(k)&&!['admin','manager','sales'].includes(state.user.role)));modal('上传业务文件',`<form><div class="formgrid"><label>文件类别<select name="category" id="file-category">${categories.map(([k,v])=>`<option value="${k}">${E(v)}</option>`).join('')}</select></label><label>对应生成版本<select name="source_file_id" id="file-source"><option value="">普通凭据无需选择</option>${row.files.filter(f=>f.generated).map(f=>`<option value="${f.id}" data-kind="${f.category}">${E(f.name)} · ${time(f.created_at)}</option>`).join('')}</select></label><label class="wide">选择文件<input type="file" name="file" required accept=".pdf,.jpg,.jpeg,.png,.docx,.txt"></label></div><p class="fieldhelp">支持文档和图片，单个文件不超过10兆字节。合同、提车签回件需选择对应的系统生成版本。</p><div class="mt15 formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button type="submit" class="primary">上传并留档</button></div></form>`,async form=>{const fd=new FormData(form);if(!fd.get('source_file_id'))fd.delete('source_file_id');await api(`/api/flow/cases/${row.id}/files`,{method:'POST',body:fd});closeModal();await render();toast('文件已留档');});
 $('#file-category').onchange=e=>{const kind=e.target.value==='signed_contract'?'contract':e.target.value==='signed_handover'?'handover':'';const select=$('#file-source');select.required=!!kind;select.value='';$$('option',select).forEach(o=>{if(o.value)o.hidden=!!kind&&o.dataset.kind!==kind;});};if(initialCategory&&categories.some(([key])=>key===initialCategory)){$('#file-category').value=initialCategory;$('#file-category').dispatchEvent(new Event('change'));}}
async function assignDialog(id){const row=state.row,t=row.tasks.find(t=>t.id===id);await formDialog('转交任务',[{key:'assignee_id',label:'接手员工',type:'employee',required:true},{key:'reason',label:'交接说明',type:'textarea',required:true}],{},v=>api('/api/flow/tasks/'+id+'/assign',{method:'POST',body:{version:t.version,...v}}),{caseId:row.id,notice:'仅可交给具有此项任务处理权限的在岗员工。'});}
const masterColumns={customers:[['name','客户'],['phone','联系电话'],['contact_allowed','允许后续联系']],accounts:[['name','账户名称'],['account_type','类别'],['active','状态']],items:[['sku','物资编码'],['name','名称'],['brand_name','物资品牌'],['quantity','账面库存'],['reserved_quantity','已占用'],['available_quantity','可用库存'],['unit','单位'],['inventory_value_cents','库存成本（元）'],['reorder','补货提醒量'],['active','状态']],members:[['number','会员号'],['customer_name','客户'],['balance_cents','储值余额（元）'],['available_cents','可用余额（元）'],['active','状态']],references:[['category','类别'],['name','名称'],['detail','说明'],['active','状态']],templates:[['title','文档名称'],['approved','公司已确认'],['version','模板版本']]};
async function masterPage(kind){const spec=state.catalog.master_types[kind];if(!spec)throw new Error('当前岗位无法查看此资料。');const data=await api(`/api/flow/master/${kind}?q=${encodeURIComponent(state.q)}&page=${state.page}`);state.rows=data.items;const cols=masterColumns[kind];return heading(spec.label,'',spec.can_write&&kind!=='templates'?b('newmaster','新增',`data-kind="${kind}" ${canWrite()?'':'disabled'}`,'primary'):'')+storeNotice()+(kind==='templates'?'<div class="notice warn">先由公司确认条款，再启用模板。启用前生成的文件会标为样式草稿；已生成的历史文件不会被覆盖。</div>':'')+searchBar()+`<section class="panel">${table([...cols.map(c=>c[1]),'操作'],data.items.map(r=>[...cols.map(([k])=>typeof r[k]==='boolean'?pill(r[k]?'done':'cancelled',r[k]?(k==='active'?'启用':'是'):(k==='active'?'停用':'否')):k.endsWith('_cents')?money(r[k]):E(labels[r[k]]||r[k]||'—')),spec.can_write?b('editmaster','编辑',`data-kind="${kind}" data-id="${r.id}" ${canWrite()?'':'disabled'}`):'—']))}${pager(data.total)}</section>`;}
async function masterDialog(kind,id){if(kind==='customers'&&!id)return createCustomerChoiceMaster();const spec=state.catalog.master_types[kind],row=id?state.rows.find(r=>r.id===id):null;if(id&&!row)throw new Error('请刷新后重试。');let fields=kind==='customers'?spec.fields.filter(f=>f.key!=='confirm_new_customer'):spec.fields;if(row&&kind==='members')fields=fields.filter(f=>f.key!=='customer_id');await formDialog((row?'编辑':'新增')+spec.label,fields,row||{},v=>api(`/api/flow/master/${kind}${row?'/'+row.id:''}`,{method:row?'PUT':'POST',body:{values:row&&kind==='members'?{customer_id:row.customer_id,...v}:v,version:row?.version}}),{notice:kind==='templates'?'可使用 {{客户}}、{{门店}}、{{单据编号}}、{{车型}} 等占位内容。模板只处理文字，不执行指令。':kind==='items'?'库存数量和库存成本由采购、领退料、盘点自动更新，不能直接修改。':''});}
const chartColors=['#0176d3','#032d60','#1b96ff','#2e844a'];
function chartSVG(chart){const labels=chart.labels,series=chart.series;if(!labels.length||!series.some(s=>s.values.some(v=>v!==0)))return empty('当前范围暂无可绘制数据','可查看明细或调整日期范围。');const w=Math.max(310,Math.min(670,(window.innerWidth<760?window.innerWidth-64:(window.innerWidth-320)/2)-36)),h=290,left=76,right=24,top=25,bottom=57,plotW=w-left-right,plotH=h-top-bottom;
 const raw=series.flatMap(s=>s.values),unitScale=chart.unit==='cents'?100:1;const vals=raw.map(x=>x/unitScale);let min=Math.min(0,...vals),max=Math.max(0,...vals);if(min===max)max=min+1;
 const mag=Math.pow(10,Math.floor(Math.log10((max-min)/4))),step=Math.max(chart.unit==='count'?1:0,Math.ceil((max-min)/4/mag)*mag);min=Math.floor(min/step)*step;max=Math.ceil(max/step)*step;if(max===min)max+=step;
 const y=v=>top+plotH-(v/unitScale-min)/(max-min)*plotH,zero=y(0);let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${E(chart.title)}"><title>${E(chart.title)}。${E(chart.caption||'')}可查看下方对应明细。</title>`;
 const fmt=n=>Math.abs(n)>=10000?(n/10000).toLocaleString('zh-CN',{maximumFractionDigits:1})+'万':n.toLocaleString('zh-CN',{maximumFractionDigits:2});
 const ticks=Math.round((max-min)/step);for(let i=0;i<=ticks;i++){const v=min+i*step,yy=y(v*unitScale);svg+=`<line x1="${left}" y1="${yy}" x2="${w-right}" y2="${yy}" stroke="${v===0?'#9cafbd':'#e5edf2'}"/><text x="${left-12}" y="${yy+5}" text-anchor="end" fill="#536577" font-size="15">${E(fmt(v))}</text>`;}
 svg+=`<text x="${left}" y="16" fill="#536577" font-size="15">${chart.unit==='cents'?'元':chart.unit==='minutes'?'分钟':'数量'}</text>`;
 const xLine=i=>left+(labels.length===1?plotW/2:i*plotW/(labels.length-1)),tickIndices=new Set();let previousLabelX=-Infinity;labels.forEach((label,i)=>{const x=chart.type==='bar'?left+(i+.5)*plotW/labels.length:xLine(i);if(x-previousLabelX>=145){tickIndices.add(i);previousLabelX=x;}});
 labels.forEach((label,i)=>{if(tickIndices.has(i)){const x=chart.type==='bar'?left+(i+.5)*plotW/labels.length:xLine(i);const text=String(label);svg+=`<text x="${x}" y="${h-bottom+27}" text-anchor="middle" fill="#536577" font-size="15">${E(text.length>9?text.slice(0,8)+'…':text)}<title>${E(text)}</title></text>`;}});
 series.forEach((s,si)=>{const color=chartColors[si%chartColors.length];if(chart.type==='bar'){const slot=plotW/labels.length,bw=Math.min(52,slot*.72/series.length);s.values.forEach((v,i)=>{const x=left+(i+.5)*slot+(si-series.length/2)*bw,yy=y(v);svg+=`<rect x="${x}" y="${Math.min(yy,zero)}" width="${Math.max(1,bw-4)}" height="${Math.max(0,Math.abs(zero-yy))}" rx="3" fill="${color}"><title>${E(labels[i])}：${E(s.name)} ${E(chart.unit==='cents'?money(v)+'元':number(v))}</title></rect>`;});}
 else{const pts=s.values.map((v,i)=>`${xLine(i)},${y(v)}`).join(' ');svg+=`<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>`;s.values.forEach((v,i)=>{svg+=`<circle cx="${xLine(i)}" cy="${y(v)}" r="${labels.length>60?1.5:3.2}" fill="${color}"><title>${E(labels[i])}：${E(s.name)} ${E(chart.unit==='cents'?money(v)+'元':number(v))}</title></circle>`;});}});
 return svg+'</svg>'+`<div class="chartlegend">${series.map((s,i)=>`<span><i class="legenddot series-${i%chartColors.length}"></i>${E(s.name)}</span>`).join('')}</div>`;
}
const metricDefinitions={new_orders:['新增车辆订单','单','orders'],delivery_count:['实际交付车辆','台','deliveries'],delivery_cents:['车辆交付金额','元','deliveries'],delivery_margin_cents:['车辆直接毛差','元','deliveries'],new_repairs:['新建维修工单','单','repairs'],repair_cents:['维修结算金额','元','repairs'],cash_in_cents:['实际收入','元','cash'],cash_out_cents:['实际支出','元','cash'],cash_net_cents:['收支净额','元','cash'],receivable_cents:['当前尚待收取','元','receivables'],overdue_receivable_cents:['超过约定付款日','元','receivables'],inventory_count:['当前库存车辆','台','inventory'],inventory_cost_cents:['当前车辆库存成本','元','inventory'],material_cost_cents:['当前物资库存成本','元','materials'],member_balance_cents:['当前储值余额','元','members'],member_count:['会员档案','人','members'],task_count:['当前未完成任务','项','tasks'],overdue_tasks:['超过计划日期','项','tasks'],cohort_receptions:['本期接待记录','次','leads'],cohort_orders:['同批转订单','次','leads'],cohort_rate:['同批接待转订单率','%','leads']};
const metricSets={overview:['delivery_cents','delivery_count','cash_net_cents','receivable_cents'],sales:['new_orders','delivery_cents','delivery_margin_cents','cohort_rate'],inventory:['inventory_count','inventory_cost_cents','delivery_count','new_orders'],repair:['new_repairs','repair_cents','task_count','overdue_tasks'],materials:['material_cost_cents','task_count'],finance:['cash_in_cents','cash_out_cents','cash_net_cents','receivable_cents'],members:['member_count','member_balance_cents'],customers:['cohort_receptions','cohort_orders','cohort_rate'],efficiency:['task_count','overdue_tasks']};
function kpis(keys,metrics){return `<div class="kpis">${keys.map(k=>{const [label,unit,dataset]=metricDefinitions[k],value=metrics[k];return `<div class="kpi"><div class="label">${E(label)}</div><div class="value">${value===null?'—':k.endsWith('_cents')?money(value):number(value)}<span class="unit">${unit}</span></div><div class="foot">${b('charttable','查看明细',`data-table="${dataset}"`,'link')}</div></div>`;}).join('')}</div>`;}
function dateFilters(){return `<form id="datefilters" class="filterbar"><label>开始日期<input type="date" name="date_from" required value="${state.dates.date_from}" max="${day()}"></label><label>结束日期<input type="date" name="date_to" required value="${state.dates.date_to}" max="${day()}"></label><button class="primary" type="submit">更新报表</button>${b('range','近7天','data-days="7"')}${b('range','近30天','data-days="30"')}${b('range','本月','data-days="month"')}</form>`;}
async function analyticData(){if(!state.analytics)state.analytics=await api('/api/flow/analytics?'+new URLSearchParams(state.dates));return state.analytics;}
function analyticalTable(key,d,limit=12){const t=d.tables[key];if(!t)return empty('暂无此类明细');const rows=t.rows.slice(0,limit);return table([...t.headers,'原单'],rows.map(r=>[...r.values.map(v=>E(v)),r.route?b('drill','查看',`data-table="${key}" data-index="${t.rows.indexOf(r)}"`,'link'):'—']))+(t.rows.length>limit?`<div class="pagination"><span>共 ${number(t.rows.length)} 条</span>${b('charttable','查看全部',`data-table="${key}"`)}</div>`:'');}
async function analyticsPage(section){if(!sections[section])section='overview';const d=await analyticData();const charts=d.charts.filter(c=>c.section===section);
 const emptyCharts=section==='finance'?charts.filter(c=>{const t=d.tables[c.table];return Array.isArray(t?.rows)&&t.rows.length===0&&c.labels.length===0&&c.series.every(s=>Array.isArray(s.values)&&s.values.length===0);}):[];
 const chartPanel=c=>`<section class="panel chartpanel"><div class="panelhead spread"><h2>${E(c.title)}</h2>${b('charttable','明细',`data-table="${c.table}"`,'link')}</div><div class="chartarea">${chartSVG(c)}</div>${c.caption?`<p class="caption">${E(c.caption)}</p>`:''}</section>`;
 return huakangPageHeading('数据可视化',d.scope_name,`${b('definitions','统计口径')}${b('exporttable','导出每日汇总','data-table="daily"')}`,'analytics')+`<nav class="tabs">${Object.entries(sections).map(([k,v])=>`<a class="${k===section?'active':''}" href="#analytics/${k}">${E(v)}</a>`).join('')}</nav>`+dateFilters()+`<div class="notice">期间：${E(d.date_from)} 至 ${E(d.date_to)}。库存、待办及余额为 ${E(d.stock_as_of)} 的当前记录。</div>`+kpis(metricSets[section],d.metrics)+
 (section==='overview'?`<div class="riskrow">${d.risks.map(r=>`<div class="risk"><span>${E(r.title)}</span><div class="row"><b>${r.value}</b>${b('charttable','查看',`data-table="${r.table}"`,'link')}</div></div>`).join('')}</div>`:'')+
 `<div class="chartgrid">${charts.filter(c=>!emptyCharts.includes(c)).map(chartPanel).join('')}</div>`+
 (emptyCharts.length?`<details class="analytics-empty-charts"><summary>暂无记录的专项 · ${number(emptyCharts.length)}</summary><div class="chartgrid">${emptyCharts.map(chartPanel).join('')}</div></details>`:'')+
 `<section class="panel"><div class="panelhead spread"><h2>${E(d.tables[section==='overview'?'stores':charts[0]?.table||'daily'].title)}</h2>${b('charttable','完整明细',`data-table="${section==='overview'?'stores':charts[0]?.table||'daily'}"`,'link')}</div>${analyticalTable(section==='overview'?'stores':charts[0]?.table||'daily',d)}</section>`+
 (section==='sales'&&d.tables.insurance_policy_facts?`<section class="panel"><div class="panelhead spread"><h2>${E(d.tables.insurance_policy_facts.title)}</h2>${b('charttable','完整明细','data-table="insurance_policy_facts"','link')}</div>${analyticalTable('insurance_policy_facts',d)}</section>`:'')+await analyticsReportDirectoryHTML();
}
async function analyticsTablePage(key){const d=await analyticData(),t=d.tables[key];if(!t)throw new Error('统计明细不存在。');const start=(state.page-1)*50;return heading(t.title,'与图表使用同一份有效数据。',`${b('open','返回可视化','data-route="analytics/overview"')}${b('exporttable','导出明细',`data-table="${key}"`,'primary')}`)+dateFilters()+`<section class="panel">${table([...t.headers,'原单'],t.rows.slice(start,start+50).map((r,i)=>[...r.values.map(v=>E(v)),r.route?b('drill','查看',`data-table="${key}" data-index="${start+i}"`,'link'):'—']))}${pager(t.rows.length,state.page,50)}</section>`;}
const F=(key,label,type='text',required=true,options)=>({key,label,type,required,options});
const commonFields=[F('doc_no','单据编号'),F('business_date','发生日期','date'),F('note','说明','textarea',false)];
const legacyFields={
 vehicles:[F('vin','车架号'),F('brand','品牌'),F('model','车型'),F('color','颜色','text',false),F('supplier','供应商','text',false),F('location','库位','text',false),F('purchase_cost','采购成本（元）','money_zero'),F('list_price','挂牌价（元）','money_zero')],
 cash:[F('direction','方向','select',true,['in','out']),F('category','收支分类','select',true,Object.keys(categories)),F('amount','金额（元）','money'),F('account','账户名称'),F('counter_account','转入账户','text',false),F('counterparty','对方名称','text',false),F('payment_method','支付方式','select',true,['bank','cash','wechat','alipay','other']),F('voucher_no','凭证号'),F('related_type','原有业务关联','select',true,['none','sales','repairs','policies','vehicles']),F('related_id','原有业务编号','int',false)],
 sales:[F('customer_name','客户'),F('customer_phone','联系电话','text',false),F('vehicle_id','车辆','vehicle'),F('salesperson','销售人员'),F('contract_amount','合同金额（元）','money'),F('sale_stage','交付状态','select',true,['ordered','delivered']),F('delivery_date','交车日期','date',false)],
 repairs:[F('customer_name','客户'),F('customer_phone','联系电话','text',false),F('plate_number','车牌号'),F('service_advisor','服务顾问'),F('repair_type','维修类型','select',true,['maintenance','repair','insurance']),F('repair_stage','完工状态','select',true,['open','completed']),F('policy_id','原保单编号','int',false),F('due_date','预计完工日','date',false),F('completion_date','完工日','date',false),F('labor_amount','工时金额（元）','money_zero'),F('parts_amount','配件金额（元）','money_zero'),F('discount','优惠（元）','money_zero'),F('cost_amount','直接成本（元）','money_zero')],
 policies:[F('customer_name','客户'),F('customer_phone','联系电话','text',false),F('policy_number','保单号'),F('insurer','保险公司'),F('plate_number','车牌号'),F('policy_type','保险类别','select',true,['commercial','compulsory','combined']),F('start_date','保险生效日','date'),F('end_date','保险到期日','date'),F('premium','保费（元）','money'),F('commission','佣金（元）','money_zero')]
};
Object.assign(labels,categories,legacyNames,{maintenance:'保养',repair:'维修',insurance:'保险维修',commercial:'商业险',compulsory:'交强险',combined:'组合保险'});
const legacyCols={vehicles:[['doc_no','入库单号'],['model','车型'],['vin','车架号'],['location','库位'],['stock_state','库存状态'],['approval_state','审核状态'],['stock_age_days','库龄（天）']],sales:[['doc_no','销售单号'],['customer_name','客户'],['contract_amount','约定金额（元）'],['sale_stage','交付状态'],['approval_state','审核状态']],repairs:[['doc_no','工单号'],['customer_name','客户'],['plate_number','车牌'],['billed_amount','结算金额（元）'],['repair_stage','进度'],['approval_state','审核状态']],policies:[['doc_no','单号'],['customer_name','客户'],['insurer','保险公司'],['end_date','到期日'],['premium','保费（元）'],['approval_state','审核状态']],cash:[['doc_no','流水单号'],['business_date','日期'],['direction','方向'],['category','分类'],['amount','金额（元）'],['account','账户'],['approval_state','状态']]};
function cashLabel(key){if(key==='claim_pass_through')return '理赔代收转付';if(key.startsWith('workflow_')){const kind=key.slice(9);return kind==='refund'?'业务退款':state.catalog.kinds[kind]?.label||'业务收款';}return labels[key]||key;}
function legacyCell(k,v){if(k==='approval_state'||k==='stock_state'||k.endsWith('_stage'))return pill(v,labels[v]||v);if(k==='category')return E(cashLabel(v));const text=labels[v]??v;return E(text===null||text===undefined||text===''?'—':text);}
async function legacyPage(mod){if(!legacyCols[mod])throw new Error('栏目不存在。');const data=await api(`/api/records/${mod}?q=${encodeURIComponent(state.q)}&state=${state.status}&page=${state.page}`);state.rows=data.items;const canCreate=canWrite()&&state.user.write_modules.includes(mod)&&['vehicles','cash'].includes(mod);const cols=legacyCols[mod];return heading(legacyNames[mod],'',canCreate?b('newlegacy',mod==='vehicles'?'登记车辆入库':'登记其他收支',`data-module="${mod}"`,'primary'):'')+storeNotice()+(mod==='cash'?'<div class="notice">车辆订单、维修、会员等收退款，请在对应业务的待办中办理。此处同步显示已登记流水；其他经营收支在此登记。</div>':!['vehicles','cash'].includes(mod)?'<div class="notice">这里保留原版本单据。新业务请从对应流程栏目建立，避免重复录入。</div>':'')+searchBar(`<label>审核状态<select name="state"><option value="">全部</option>${['draft','submitted','approved','rejected','void'].map(s=>`<option value="${s}" ${s===state.status?'selected':''}>${labels[s]}</option>`).join('')}</select></label>`)+`<section class="panel">${table([...cols.map(c=>c[1]),'操作'],data.items.map(r=>[...cols.map(([k])=>legacyCell(k,r[k])),b('open','查看',`data-route="legacy/${mod}/${r.id}"`)]))}${pager(data.total)}</section>`;}
async function legacyDetail(mod,id){const r=await api(`/api/records/${mod}/${id}`);state.row=r;const readonly=mod==='cash'&&(r.category.startsWith('workflow_')||r.category.startsWith('group_member_')||r.category.startsWith('procurement_')||r.category.startsWith('benefit_')||r.category.startsWith('vehicle_procurement_')||r.category==='interstore_clearing'||r.category.startsWith('business_finance_')||r.category.startsWith('claim_')),can=canWrite()&&state.user.write_modules.includes(mod),buttons=[];if(can&&!readonly){if(['draft','rejected'].includes(r.approval_state)){buttons.push(b('editlegacy','编辑',`data-module="${mod}"`));buttons.push(b('legacyaction','提交审核',`data-key="submit" data-module="${mod}"`,'primary'));}if(r.approval_state==='submitted'&&state.user.can_approve){buttons.push(b('legacyaction','审核通过',`data-key="approve" data-module="${mod}"`,'primary'),b('legacyaction','退回',`data-key="reject" data-module="${mod}"`));}if(r.approval_state==='approved'&&state.user.can_approve){if(['sales','repairs'].includes(mod))buttons.push(b('legacyaction',mod==='sales'?'确认交车':'确认完工',`data-key="advance" data-module="${mod}"`));buttons.push(b('legacyaction','申请作废',`data-key="void" data-module="${mod}"`,'danger'));}}
 const fields=Object.fromEntries([...commonFields,...legacyFields[mod]].map(f=>[f.key,f.label]));const mapped=Object.fromEntries(Object.entries(r).filter(([k])=>fields[k]).map(([k,v])=>[fields[k],labels[v]||v]));return `<div class="back">${b('open','‹ 返回'+legacyNames[mod],`data-route="legacy/${mod}"`,'link')}</div>`+heading(r.doc_no,'',pill(r.approval_state,labels[r.approval_state]||r.approval_state))+storeNotice()+(readonly?'<div class="notice">此笔收支由业务流程产生，不可从流水页修改或作废。退款需从原业务发起并关联原收款。</div>':'')+panel('单据记录',facts(mapped)+`<div class="mt22 row">${buttons.join('')}</div>`);}
async function legacyDialog(mod,edit=false){const row=edit?state.row:null;const fields=[...commonFields,...legacyFields[mod]],initial=row?{...row}:{doc_no:('vehicles'===mod?'入库':'收支')+'-'+day().replaceAll('-','')+'-'+requestKey().slice(0,6),business_date:day(),direction:'out',category:'operating_expense',related_type:'none',payment_method:'bank'};
 // Optional dates must remain empty instead of defaulting to today.
 for(const f of fields)if(f.type==='date'&&!f.required&&!initial[f.key])initial[f.key]='';
 await formDialog((row?'编辑':'新增')+legacyNames[mod],fields,initial,async v=>{for(const f of fields)if((f.type==='date'||f.type==='int')&&!f.required&&!v[f.key])v[f.key]=null;const r=await api(`/api/records/${mod}${row?'/'+row.id:''}`,{method:row?'PUT':'POST',body:row?{version:row.version,data:v}:v});go(`legacy/${mod}/${r.id}`);},{notice:'保存为草稿，提交并审核后生效。'});}
async function legacyAction(mod,key){const row=state.row;const fields=[F('reason','办理说明','textarea')];if(key==='advance')fields.push(F('effective_date','实际发生日期','date'));await formDialog(labels[key]||({submit:'提交审核',approve:'审核通过',reject:'退回单据',advance:'确认进度',void:'作废单据'}[key]),fields,{},v=>api(`/api/records/${mod}/${row.id}/actions/${key}`,{method:'POST',body:{version:row.version,...v}}),{notice:key==='void'?'作废会改变有效业务统计。存在关联款项或占用关系时，需要先处理原业务。':'请确认记录与实际情况一致。',warn:key==='void'});}
async function usersPage(){const d=await api('/api/users');state.rows=d.items;state.accountData=d;return heading('员工账号','',b('open','刷新员工列表','data-route="users"')+(state.user.can_users&&typeof staffBatchButton==='function'?staffBatchButton():'')+b('newuser','新增员工','','primary'))+`<section class="panel">${table(['员工','登录账号','默认岗位','授权门店与岗位','集团汇总','状态','操作'],d.items.map(r=>[E(r.display_name),E(r.username),E(r.role_label),`<span class="wrap">${r.role==='admin'?'全部门店':r.stores.map(s=>E(s.name)+' · '+E(roleNames[r.store_roles?.find(x=>x.store_id===s.id)?.role||r.role])).join('<br>')}</span>`,r.can_group_summary?'已授权':'未授权',pill(r.active?'done':'cancelled',r.active?'启用':'停用'),`<div class="row">${b('edituser','编辑',`data-id="${r.id}"`)}${r.id!==state.user.id?b('resetpassword','重置密码',`data-id="${r.id}"`):''}</div>`]))}</section>`;}
async function userDialog(id){
 const row=id?state.rows.find(r=>r.id===id):null;
 const editRequest=requestKey();
 const fields=[...(!row?[F('username','登录账号'),F('password','初始密码','password')]:[]),F('display_name','员工姓名'),F('role','账号默认岗位','select',true,Object.keys(roleNames)),F('can_group_summary','允许集团汇总查询','bool',false),...(row?[F('active','启用','bool',false)]:[])];
 Object.assign(labels,roleNames);
 const checks=`<div class="mt20"><h3>门店与岗位</h3><div class="store-role-list">${state.accountData.stores.filter(s=>s.active).map(s=>{const assigned=row?.store_roles?.find(x=>x.store_id===s.id);return `<div class="store-role-row"><label class="checklabel"><input type="checkbox" name="store_ids" value="${s.id}" ${(row?.store_ids||[]).includes(s.id)?'checked':''}>${E(s.name)}</label><label>本店岗位<select name="store_role_${s.id}">${Object.entries(roleNames).filter(([k])=>k!=='admin').map(([k,v])=>`<option value="${k}" ${k===(assigned?.role||(row?.role==='admin'?'manager':row?.role)||'sales')?'selected':''}>${E(v)}</option>`).join('')}</select></label></div>`;}).join('')}</div></div>`;
 const dialog=await formDialog(row?'编辑员工':'新增员工',fields,row||{role:'sales',can_group_summary:false},(v,form)=>{const fd=new FormData(form),ids=fd.getAll('store_ids').map(Number);return api('/api/users'+(row?'/'+row.id:''),{method:row?'PUT':'POST',body:{...v,...(row?{access_version:row.access_version,request_id:editRequest}:{}),store_ids:v.role==='admin'?[]:ids,store_roles:v.role==='admin'?[]:ids.map(id=>({store_id:id,role:fd.get('store_role_'+id)}))}});},{extra:checks,notice:'非管理员至少选择一家门店及对应岗位。集团汇总仅包含获授权的管理、财务或审计门店，办理业务需切回具体门店。变更授权后原登录会话失效；他人修改后须关闭窗口、刷新员工列表再核对，旧页面不会覆盖新授权。'});
 if(typeof mountStaffAccessSummary==='function')mountStaffAccessSummary(dialog);
}
async function storesPage(){const d=await api('/api/stores');state.rows=d.items;return heading('门店设置','',b('newstore','新增门店','','primary'))+`<section class="panel">${table(['门店','门店编码','状态','操作'],d.items.map(r=>[E(r.name),E(r.code),pill(r.active?'done':'cancelled',r.active?'启用':'停用'),b('editstore','编辑',`data-id="${r.id}"`)]))}</section>`;}
async function storeDialog(id){const row=id?state.rows.find(r=>r.id===id):null;const options={};await formDialog(row?'编辑门店':'新增门店',[F('name','门店名称'),F('code','门店编码'),F('active','启用','bool',false)],row||{active:true},async v=>{await api('/api/stores'+(row?'/'+row.id:''),{method:row?'PUT':'POST',body:v});const d=await api('/api/stores',{store:null});state.stores=d.items;const usable=activeStoreOptions(state.stores);const doomed=!usable.some(store=>String(store.id)===String(state.store));if(doomed&&usable.length){options.success=`当前门店已停用，已切换到「${usable[0].name}」。请核对右上角门店后再办理。`;await switchStore(String(usable[0].id),'stores');}else{reconcileStore(state.stores);shell();}},options);}
async function passwordDialog(required=false){await formDialog('修改个人密码',[F('current_password','当前密码','password'),F('new_password','新密码','password')],{},async v=>{await api('/api/auth/password',{method:'POST',body:v});state.user=null;loginPage();},{notice:required?'请设置至少12位的个人密码，完成后重新登录。':'修改密码后需要重新登录。'});}
const auditLabels={create:'建立记录',update:'修改记录',submit:'提交审核',approve:'审核通过',reject:'退回',void:'作废',advance:'确认进度',login:'登录',download:'下载文件',export:'导出',create_user:'新增员工',update_user:'修改员工',create_store:'新增门店',update_store:'修改门店',change_password:'修改密码',reset_password:'重置密码',review:'复核记录',flow_create:'建立流程业务',flow_action:'办理业务',document:'生成文件',upload:'上传凭据'};
const auditEntities={...legacyNames,flow:'业务流程',typed_master:'业务资料',dictionary:'分类设置',vehicle_catalog:'车型目录',customer_vehicle:'客户车辆',care_rule:'客户提醒规则',care_grant:'客户资料授权',users:'员工账号',stores:'门店',findings:'数据复核',feedback:'反馈',maintenance:'系统维护'};
function bindAuditFilters(){
 const form=$('#audit-filters');if(!form)return;
 const identifier=form.elements.entity_id;
 identifier.addEventListener('input',()=>identifier.setCustomValidity(''));
 form.onsubmit=async event=>{event.preventDefault();const value=identifier.value.trim();if(value&&(!/^[1-9]\d*$/.test(value)||!Number.isSafeInteger(Number(value)))){identifier.setCustomValidity('请输入有效的正整数编号。');identifier.reportValidity();return;}state.auditFilters={entity_type:form.elements.entity_type.value,entity_id:value};state.page=1;await render();};
}
async function auditPage(){
 const current=renderId,filters=state.auditFilters,query=new URLSearchParams({page:String(state.page)});if(filters.entity_type)query.set('entity_type',filters.entity_type);if(filters.entity_id)query.set('entity_id',filters.entity_id);
 const d=await api('/api/audit?'+query);if(current!==renderId)return '';state.rows=d.items;
 const controls=`<form id="audit-filters" class="filterbar"><label>业务类型<select name="entity_type"><option value="">全部</option>${Object.entries(auditEntities).map(([key,label])=>`<option value="${E(key)}" ${filters.entity_type===key?'selected':''}>${E(label)}</option>`).join('')}</select></label><label>原记录编号<input name="entity_id" inputmode="numeric" value="${E(filters.entity_id)}" placeholder="留空查看全部"></label><button type="submit" class="primary">查询</button>${b('audit-reset','重置')}</form>`;
 return heading('操作记录','')+controls+`<section class="panel audit-records">${table(['时间','操作人','操作','业务范围','原记录编号','说明','查看'],d.items.map(r=>[time(r.occurred_at),E(r.actor_name),E(auditLabels[r.action]||r.reason||'业务操作'),E(auditEntities[r.entity_type]||'资料管理'),E(r.entity_id??'—'),`<span class="wrap">${E(r.reason||'—')}</span>`,b('auditdetail','详情',`data-id="${r.id}"`)]))}${pager(d.total)}</section>`;
}
async function reportsPage(){const d=await api('/api/reports?page='+state.page);state.rows=d.items;return heading('每日汇总','',b('newreport','生成日报',canWrite()?'':'disabled','primary'))+storeNotice()+`<section class="panel">${table(['业务日期','门店','生成时间','摘要','待复核线索','版本状态','操作'],d.items.map(r=>[E(r.business_date),E(state.stores.find(s=>s.id===r.store_id)?.name||''),time(r.generated_at),pill(r.ai_status),r.finding_count,r.stale?pill('overdue','有后续变化'):r.provisional?pill('pending','当日记录'):pill('done','已保存'),b('open','查看',`data-route="reports/${r.id}"`)]))}${pager(d.total)}</section>`;}
async function reportPage(id){const r=await api('/api/reports/'+id);state.row=r;return heading(r.business_date+' 每日汇总','',b('open','返回日报','data-route="reports"'))+(r.stale?'<div class="notice warn">原业务已有后续变化，需要重新生成才能反映最新有效记录。</div>':'')+panel('经营摘要',`<div class="reporttext">${E(r.deterministic_summary||'')}</div>${r.ai_result?`<hr><h3>辅助审查摘要</h3><div class="reporttext">${E(r.ai_result.summary||'')}</div>`:''}`)+`<div class="mt20">${panel('流程经营汇总',r.snapshot?.workflow?facts(Object.fromEntries(Object.entries(r.snapshot.workflow.metrics||{}).filter(([k])=>metricDefinitions[k]).map(([k,v])=>[metricDefinitions[k][0],k.endsWith('_cents')?money(v)+'元':v===null?'—':v]))):'<p class="muted">此历史日报未纳入新流程数据。</p>')}</div>`;}
async function findingsPage(){const d=await api('/api/findings?status='+encodeURIComponent(state.status)+'&page='+state.page);state.rows=d.items;return heading('数据复核','线索用于人工核对，不直接认定为错误或违规。')+searchBar(`<label>复核状态<select name="state"><option value="">全部</option>${['open','reviewing','confirmed','dismissed','resolved'].map(s=>`<option value="${s}" ${state.status===s?'selected':''}>${labels[s]}</option>`).join('')}</select></label>`)+`<section class="panel">${table(['线索','级别','依据','处理状态','操作'],d.items.map(r=>[`<strong class="wrap">${E(r.title||r.rule_code)}</strong>`,pill(r.severity),`<span class="wrap">${E(r.suggested_action||'查看详情')}</span>`,pill(r.review_status),b('review','复核',`data-id="${r.id}" ${canWrite()?'':'disabled'}`)]))}${pager(d.total)}</section>`;}
document.addEventListener('change',e=>{if(e.target.id==='taskstatus'){state.taskStatus=e.target.value;state.page=1;render();}});
document.addEventListener('click',async e=>{const el=e.target.closest('[data-act]');if(!el||el.disabled)return;const a=el.dataset.act;try{
 if(state.storeSwitch&&a!=='logout'){if(a==='store-retry')await switchStore(state.store);else if(a==='open'&&el.dataset.route)go(el.dataset.route);return;}
 if(a==='bundle-create'){await rechargeBundleCreate(el.dataset.key,Number(el.dataset.id));return;}
 if(a==='bundle-action'){await rechargeBundleAction(el.dataset.key);return;}
 if(a==='bundle-rule'){await rechargeBundleRule(Number(el.dataset.id));return;}
 if(a==='business-finance-create'){await businessFinanceCreate(el.dataset.key,Number(el.dataset.id));return;}
 if(a==='business-finance-action'){await businessFinanceAction(el.dataset.key);return;}
 if(a==='business-finance-other'){await businessFinanceOther();return;}
 if(a==='open')go(el.dataset.route);
 else if(a==='menu')$('.sidebar').classList.toggle('shown');
 else if(a==='membership-create')await membershipCreate(el.dataset.key,Number(el.dataset.id)||null);
 else if(a==='membership-action')await membershipAction(el.dataset.key);
 else if(a==='membership-card-lookup')await membershipCardLookup();
 else if(a==='membership-rule')await membershipRule();
 else if(a==='reconcile-new')await reconciliationCreate();
 else if(a==='reconcile-action')await reconciliationAction(el.dataset.key,Number(el.dataset.id)||null,el.dataset.line);
 else if(a==='clearing-new')await clearingCreate(el.dataset.kind,Number(el.dataset.id));
 else if(a==='clearing-action')await clearingAction(el.dataset.key);
 else if(a==='close')closeModal();
 else if(a==='refresh'){state.analytics=null;await render();}
 else if(a==='page'){state.page=Number(el.dataset.page);await render();}
 else if(a==='clearfilter'){state.q='';state.status='';state.page=1;await render();}
 else if(a==='audit-reset'){state.auditFilters={entity_type:'',entity_id:''};state.page=1;await render();}
 else if(a==='taskscope'){state.taskScope=el.dataset.scope;state.page=1;await render();}
 else if(a==='logout'){await api('/api/auth/logout',{method:'POST'});state.user=null;state.catalog=null;state.analytics=null;loginPage();}
 else if(a==='password')await passwordDialog();
 else if(a==='newcase')await createCase(el.dataset.kind);
 else if(a==='caseaction')await caseAction(el.dataset.key);
 else if(a==='assign')await assignDialog(Number(el.dataset.id));
 else if(a==='upload')await uploadDialog(el.dataset.category);
 else if(a==='generatedoc'){el.disabled=true;await api(`/api/flow/cases/${state.row.id}/documents`,{method:'POST',body:{kind:el.dataset.kind}});await render();toast('文件已生成，可在本单下载');}
 else if(a==='downloadfile')await download('/api/flow/files/'+el.dataset.id,'业务文件');
 else if(a==='switchcase')await switchStore(el.dataset.store,'case/'+el.dataset.id);
 else if(a==='lookup'){const root=el.closest('.lookup'),q=$('[data-lookup-query]',root).value,p=new URLSearchParams({q});if(root.dataset.case)p.set('case_id',root.dataset.case);if(root.dataset.action)p.set('action',root.dataset.action);const d=await api('/api/flow/lookup/'+root.dataset.kind+'?'+p);$('select',root).innerHTML='<option value="">请选择</option>'+d.items.map(i=>`<option value="${i.id}">${E(i.label)}</option>`).join('');if(!d.items.length)toast('未找到符合条件的记录');else if(d.has_more)toast('结果较多，请进一步缩小关键词');}
 else if(a==='newmaster'||a==='editmaster')await masterDialog(el.dataset.kind,el.dataset.id?Number(el.dataset.id):null);
 else if(a==='newlegacy'||a==='editlegacy')await legacyDialog(el.dataset.module,a==='editlegacy');
 else if(a==='legacyaction')await legacyAction(el.dataset.module,el.dataset.key);
 else if(a==='group-link')await groupLinkDialog();
 else if(a==='group-issue')await groupIssue();
 else if(a==='filescaninfo')await fileScanDialog(Number(el.dataset.id));
 else if(a==='benefit-action')await benefitAction(el.dataset.key,Number(el.dataset.id)||null,Number(el.dataset.rule)||null);
 else if(a==='benefit-rule')await benefitRuleDialog();
 else if(a==='group-action')await groupAction(el.dataset.key,Number(el.dataset.id)||null);
 else if(a==='newuser'||a==='edituser')await userDialog(el.dataset.id?Number(el.dataset.id):null);
 else if(a==='batchusers'&&typeof staffBatchDialog==='function')await staffBatchDialog();
 else if(a==='resetpassword'){const id=Number(el.dataset.id);await formDialog('重置员工密码',[F('password','新的初始密码','password'),F('reason','重置原因','textarea')],{},v=>api('/api/users/'+id+'/password',{method:'POST',body:v}),{notice:'员工的现有登录会话将失效，首次重新登录必须改密。'});}
 else if(a==='newstore'||a==='editstore')await storeDialog(el.dataset.id?Number(el.dataset.id):null);
 else if(a==='auditdetail'){const r=state.rows.find(x=>x.id===Number(el.dataset.id));const known={...dataLabels,...Object.fromEntries([...commonFields,...Object.values(legacyFields).flat()].map(f=>[f.key,f.label])),active:'启用',display_name:'员工姓名',role:'岗位',name:'名称',code:'编码',contact_name:'联系人',phone:'联系电话',state:'进度',title:'事项',status:'状态'};const prettify=obj=>Object.fromEntries(Object.entries(obj||{}).filter(([k,v])=>known[k]&&typeof v!=='object').map(([k,v])=>[k,typeof v==='string'?(labels[v]||v):v]));modal('操作详情',`<div class="stack"><p>${E(r.reason||'业务操作')} · ${E(r.actor_name)} · ${time(r.occurred_at)}</p>${facts({业务范围:auditEntities[r.entity_type]||'资料管理',原记录编号:r.entity_id??'—'})}<h3>操作前</h3>${facts(prettify(r.before_data),known)}<h3>操作后</h3>${facts(prettify(r.after_data),known)}</div>`);}
 else if(a==='range'){state.dates={date_from:el.dataset.days==='month'?day().slice(0,8)+'01':relativeDay(1-Number(el.dataset.days)),date_to:day()};state.analytics=null;state.page=1;await render();}
 else if(a==='definitions'){const d=await analyticData();modal('统计口径',`<div class="definitions">${d.definitions.map(x=>`<p>${E(x)}</p>`).join('')}</div>`);}
 else if(a==='charttable')go('table/'+el.dataset.table);
 else if(a==='exporttable')await download('/api/flow/analytics/export?'+new URLSearchParams({...state.dates,dataset:el.dataset.table}),'经营明细.csv');
 else if(a==='drill'){const d=await analyticData(),r=d.tables[el.dataset.table].rows[Number(el.dataset.index)],route=r.route;if(route?.type==='case')go('case/'+route.id);else if(route?.type==='legacy')go(`legacy/${route.module}/${route.id}`);else if(route?.type==='master')go('master/'+route.module);else if(route?.type==='customer_vehicle')go('customer-vehicles/'+route.id);else if(route?.type==='customer_value')go('customer-value/'+route.id);}
 else if(a==='newreport'){await formDialog('生成每日汇总',[F('business_date','业务日期','date'),F('use_ai','请求外部模型辅助摘要','bool',false)],{business_date:relativeDay(-1)},async v=>{const r=await api('/api/reports/generate',{method:'POST',body:{...v,retry_ai:false}});go('reports/'+r.id);},{notice:'程序汇总始终保留。外部摘要仅在管理员启用并配置后调用，不参与业务流转。'});}
 else if(a==='review'){const r=state.rows.find(x=>x.id===Number(el.dataset.id));await formDialog(r.title||'处理复核线索',[F('status','处理结果','select',true,['reviewing','confirmed','dismissed','resolved']),F('note','复核说明','textarea')],{status:r.review_status==='open'?'reviewing':r.review_status},v=>api('/api/findings/'+r.id+'/review',{method:'POST',body:{version:r.version,...v}}),{notice:r.suggested_action||''});}
 }catch(err){if(!err.staleContext||err.staleMutation)toast(err.message,true);}finally{if(el.isConnected&&a==='generatedoc')el.disabled=false;}});
// Escape HTML on every data boundary; no eval, inline event handlers or external scripts.
let applicationBootStarted=false;
async function bootstrapAppOnce(){
 if(applicationBootStarted)return;
 applicationBootStarted=true;
 try{if(await window.maybeLocalPreviewSetup())return;state.user=await api('/api/auth/me');await boot();}
 catch(err){if(err.status===401||!state.user)loginPage();else $('#app').innerHTML=`<div class="errorpage"><h1>启动页面时遇到问题</h1><p>${E(err.message)}</p></div>`;}
}
// A defer script runs while readyState is interactive. Wait for every later
// defer module before rendering a bookmarked page with an existing login.
if(document.readyState==='complete')bootstrapAppOnce();
else document.addEventListener('DOMContentLoaded',bootstrapAppOnce,{once:true});
