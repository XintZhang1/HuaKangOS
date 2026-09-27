'use strict';
function clearSalesQuotesSession(){delete state.salesQuoteOrder;}
const salesQuoteCanWrite=()=>canWrite()&&['admin','manager','sales'].includes(state.user.role);
const salesQuoteOutcome={activated:'客户已确认并生效',rejected:'主管退回',withdrawn:'已撤回'};
async function salesQuotesPage(id){
 if(state.store==='all')return heading('车辆报价与预订')+storeNotice();
 if(!id){const d=await api('/api/flow/cases?kind=order&page='+state.page+'&q='+encodeURIComponent(state.q));return heading('车辆报价与预订','',salesQuoteCanWrite()?b('sales-quote-new','新建预订合同','','primary'):'')+storeNotice()+workRecordSearch('客户姓名或订单号',100)+panel('本店车辆订单',table(['客户与订单','报价流程','状态',''],d.items.map(r=>[E(r.title)+'<br>'+E(r.number),[3,4].includes(r.flow_version)?'版本报价':'原流程 '+r.flow_version,pill(r.state,r.state_label),b('open','办理',`data-route="${[3,4].includes(r.flow_version)?'sales-quotes':'case'}/${r.id}"`)])))+pager(d.total);}
 const r=await api('/api/sales-quotes/orders/'+id);state.salesQuoteOrder=r;state.row=r;
 const active=r.quotes.find(q=>q.id===r.active_quote_id),pending=r.quotes.find(q=>q.id===r.pending_quote_id),selected=pending||active;
 const quoteCard=q=>`<p><strong>第 ${q.revision} 版 · ${E(q.model_snapshot.name)}</strong></p><p>${q.amount_cents!==undefined?'车辆价款 '+money(q.amount_cents)+' 元 · ':''}预计交付 ${E(q.delivery_due)}</p><p>新确认有效期至 ${E(q.valid_until)} · ${E(q.resolution?salesQuoteOutcome[q.resolution.outcome]:q.review?'主管已批准，待客户签回':'待独立主管复核')}</p><p>另单服务：${[['addon','精品加装'],['insurance','本店保险'],['agency','代办服务']].filter(([k])=>q.services[k]).map(([,label])=>label).join('、')||'无'}</p>${q.terms!==undefined?`<p class="wrap">本版约定：${E(q.terms)}</p>`:''}${q.review?`<p>价格复核意见：${E(q.review.reason)}</p>`:''}`;
 let html=heading('预订合同 · '+r.number,r.customer?.name||'',b('open','返回车辆订单','data-route="sales-quotes"'))+storeNotice();
 const contract=r.files.filter(f=>f.generated&&f.category==='contract').sort((a,b)=>b.id-a.id)[0];
 html+=panel('预订合同',`<p><strong>${E(r.customer?.name||r.title)}</strong> · ${E(r.number)}</p><div class="row">${contract?b('downloadfile','下载合同',`data-id="${contract.id}"`):''}${canWrite()&&['admin','manager','sales'].includes(state.user.role)?b('upload','上传已签合同','data-category="signed_contract"'):''}</div>`);
 if(pending)html+=panel('当前待确认报价',quoteCard(pending)+'<p>此版本尚未生效，暂停实际收款、PDI 和交车。原有效报价及文件保留，主管批准后须按本版与当前 VIN 重新签回。</p>');
 if(active)html+=panel('当前有效报价',quoteCard(active));
 if(!selected)html+=panel('等待重新报价','<p>当前没有可继续执行的报价，请销售提交新版本。</p>');
 html+=panel('报价变更',`<p>车辆尚未实际出库时可提出新版本。已执行的配套服务、已出库或已提车辆，须按原单售后处理。换车由库管先确认释放原占用，重新配车和检查。</p>`+(r.can_propose&&canWrite()?b('sales-quote-revise','提交新的报价版本','','primary'):'')+b('open','查看退订退车与原款退回','data-route="aftercare"'));
 if(r.amount_cents!==undefined)html+=panel('车辆款项',`<div class="cards">${[['当前约定价款',r.amount_cents],['已收及已抵用',r.paid_cents],['降价后待退差额',r.excess_cents||0]].map(([label,value])=>`<div class="card"><span>${label}（元）</span><strong>${money(value)}</strong></div>`).join('')}</div><p>车辆价款不包含另单服务。已抵用预收的超额部分回原预收账，实际超收现金由财务按原收款退回；退款完成前不能出库。</p>`);
 html+=actionPanel((r.actions||[]).map(a=>`<div class="actioncard">${b('sales-quote-action',a.label,`data-key="${a.key}" ${!canWrite()||!a.enabled?'disabled':''}`,a.enabled?'primary':'')}<p>${E(a.reason||a.confirm||'')}</p></div>`).join('')||'<p>等待相关岗位办理。</p>');
 const docKinds=['inventory','technician','reception','customer_service'].includes(state.user.role)?['business']:['contract','handover','business'];
 html+=panel('本版文档与实际凭据',(canWrite()?b('upload','上传实际凭据')+docKinds.map(k=>b('generatedoc','生成'+state.catalog.document_types[k],`data-kind="${k}"`)).join(''):'')+fileList(r.files));
 if(r.children.length)html+=panel('配套及后续业务',r.children.map(c=>`<div class="listrow"><div><strong>${E(c.kind_label)}</strong><p>${pill(c.state,c.state_label)}</p></div>${b('open','查看办理',`data-route="case/${c.id}"`)}</div>`).join(''));
 if(r.payments?.length)html+=panel('实际原款与退款',table(['方向／凭证','金额（元）','日期'],r.payments.map(p=>[E(p.direction==='in'?'收款':'原款退款')+'<br>'+E(p.reference),money(p.amount_cents),E(p.business_date)])));
 html+=historyPanel('报价历史',r.quotes.map(q=>`<details ${q.id===r.pending_quote_id?'open':''}><summary>第 ${q.revision} 版 · ${E(q.model_snapshot.name)}</summary>${quoteCard(q)}</details>`).join(''));
 html+=panel('岗位交接',taskList(r.tasks));
 return html;
}
async function salesQuoteNew(leadId=null){
 if(!salesQuoteCanWrite())throw new Error('请切换到有销售办理权限的具体门店。');
 const lead=leadId?await api('/api/flow/cases/'+leadId):null;
 return salesQuoteForm(null,lead);
}
async function salesQuoteForm(row=null,lead=null,draft=null){
 const context=storeContextVersion,identity=`${state.user?.id}:${state.store}`;
 const guard=()=>{requireStoreContext(context);if(identity!==`${state.user?.id}:${state.store}`)throw new Error('门店已变化，请重新打开预订。');};
 const [models,catalog]=await Promise.all([retailAll('/api/vehicle-catalog'),typedCatalog()]);guard();
 const old=row?.quotes.find(q=>q.id===row.active_quote_id)||row?.quotes.at(-1),request_id=draft?.request_id||requestKey();
 const initial={model:old?.model_id||'',amount:old?(old.amount_cents/100).toFixed(2):'',due:old?.delivery_due||relativeDay(7),expires:relativeDay(7),terms:old?.terms||'',reason:'',...old?.services,...draft};
 let selected=lead?{id:lead.customer_id,name:lead.customer?.name||lead.title,phone:lead.customer?.phone||''}:draft?.selectedCustomer||null;
 let queryRevision=0,confirmedPhone='',timer,frozenSubmission=null;const disabledFields=new Map();
 const modelOptions='<option value="">输入车型、车系或品牌</option>'+models.map(m=>`<option value="${m.id}" ${String(initial.model)===String(m.id)?'selected':''}>${E(m.brand_name)} · ${E(m.series_name)} · ${E(m.name)} · ${m.model_year}款</option>`).join('');
 const customer=!row?`<div class="formgrid"><label>客户姓名<input name="customer_name" autocomplete="off" maxlength="100" placeholder="姓名或电话，输入后查找" required value="${E(selected?.name||initial.customer_name||'')}" ${lead?'readonly':''}></label><label>联系电话<input name="customer_phone" maxlength="30" inputmode="tel" value="${E(selected?.phone||initial.customer_phone||'')}" ${lead?'readonly':''}></label></div><div data-quote-customers></div><label class="checklabel" data-quote-new-confirm hidden><input type="checkbox" data-quote-new-checkbox>已核对，仍新建客户</label>`:'';
 modal(row?'修改报价':'新建预订合同',`<form id="sales-quote-form">${customer}<label>车型<select name="model" required data-search-select>${modelOptions}</select></label>${catalog.kinds.vehicle_models?.can_write?b('quote-inline-model','新增车型'):''}${!models.length?'<p class="fieldhelp">暂无车型，请由主管或库管添加。</p>':''}<label>车辆成交价（元）<input name="amount" inputmode="decimal" value="${E(initial.amount)}" required></label><div class="formgrid"><label>预计交车日期<input name="due" type="date" value="${E(initial.due)}" min="${day()}" required></label><label>客户确认截止日期<input name="expires" type="date" value="${E(initial.expires)}" min="${day()}" required></label></div><label>合同约定<textarea name="terms" minlength="2" maxlength="1500" required>${E(initial.terms)}</textarea></label><details ${['addon','insurance','agency'].some(k=>initial[k])?'open':''}><summary>配套服务</summary>${[['addon','精品加装'],['insurance','本店保险'],['agency','代办服务']].map(([k,label])=>`<label class="checklabel"><input type="checkbox" name="${k}" ${initial[k]?'checked':''}>${label}</label>`).join('')}<p class="fieldhelp">配套服务另行报价，不含在车辆成交价内。</p></details>${row?`<label>修改原因<textarea name="reason" minlength="2" maxlength="500" required>${E(initial.reason)}</textarea></label>`:''}<p class="fieldhelp">提交后由主管核价，再由客户签字确认。</p><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button type="submit" class="primary">${row?'提交修改':'提交预订'}</button></div></form>`,async form=>{
  guard();queryRevision++;clearTimeout(timer);
  let body=frozenSubmission;
  if(!body){
   const f=form.elements,model=models.find(m=>m.id===Number(f.model.value));if(!model)throw new Error('请选择车型。');
   const quote={model_id:model.id,model_version:model.version,amount_cents:retailScaled(f.amount.value,2),delivery_due:f.due.value,valid_until:f.expires.value,terms:f.terms.value,reason:row?f.reason.value:'首次录入客户预订'};
   for(const k of ['addon','insurance','agency'])quote[k]=f[k].checked;
   const phone=!row?f.customer_phone.value.trim():'';
   const customerValues=row?{}:selected?{customer_id:selected.id}:{customer_name:f.customer_name.value.trim(),customer_phone:phone,confirm_new_customer:!!phone&&confirmedPhone===phone&&form.querySelector('[data-quote-new-checkbox]').checked};
   body=row?{request_id,version:row.version,quote}:{request_id,...customerValues,lead_id:lead?.id||null,lead_version:lead?.version||null,quote};
  }
  lockFields(true);
  try{
   if(!frozenSubmission){
    if(body.customer_phone&&!body.customer_id){const d=await api('/api/customer-choice/matches?phone='+encodeURIComponent(body.customer_phone));guard();if(d.items.length&&!body.confirm_new_customer){showCustomers(d,true);throw new Error('请选择已有客户，或核对后勾选新建客户。');}}
    frozenSubmission=body;
   }
   const result=await api('/api/sales-quotes/orders'+(row?'/'+row.id+'/quotes':''),{method:'POST',body:frozenSubmission});closeModal();go('sales-quotes/'+result.id);
  }catch(error){
   if(error.status&&error.status<500){frozenSubmission=null;lockFields(false);}
   else if(!frozenSubmission)lockFields(false);
   else if(!error.staleContext)error.message='提交结果尚未确认。请再次点提交核对结果；系统会沿用上次内容，不会重复建单。';
   throw error;
  }

 });
 const form=document.querySelector('#sales-quote-form');
 function lockFields(locked){
  if(locked){form.querySelectorAll('input,select,textarea,button').forEach(el=>{if(el.type==='submit'||el.dataset.act==='close')return;if(!disabledFields.has(el))disabledFields.set(el,el.disabled);el.disabled=true;});}
  else{for(const [el,disabled]of disabledFields)if(el.isConnected)el.disabled=disabled;disabledFields.clear();}
 }

 function showCustomers(data,samePhone=false){
  if(!form.isConnected)return;
  const list=form.querySelector('[data-quote-customers]');list.innerHTML=data.items.length?data.items.map(c=>`<button type="button" class="customer-suggestion" data-customer-id="${c.id}"><strong>${E(c.name)}</strong><span>${E(c.phone||'未留电话')}</span></button>`).join('')+(data.has_more?'<p class="fieldhelp">请继续输入，缩小查找范围。</p>':''):'<p class="fieldhelp">未找到客户，提交时新建。</p>';
  form.querySelector('[data-quote-new-confirm]').hidden=!samePhone||!data.items.length;
  if(samePhone){confirmedPhone=form.elements.customer_phone.value.trim();form.querySelector('[data-quote-new-checkbox]').checked=false;}
  list.querySelectorAll('[data-customer-id]').forEach(button=>button.onclick=()=>{guard();queryRevision++;selected=data.items.find(c=>c.id===Number(button.dataset.customerId));form.elements.customer_name.value=selected.name;form.elements.customer_phone.value=selected.phone||'';form.elements.customer_phone.readOnly=true;list.innerHTML='<p class="fieldhelp">已选择客户</p>';form.querySelector('[data-quote-new-confirm]').hidden=true;});
 }
 if(!row&&!lead){
  if(selected)form.elements.customer_phone.readOnly=true;
  const search=()=>{clearTimeout(timer);selected=null;confirmedPhone='';form.querySelector('[data-quote-new-confirm]').hidden=true;const rev=++queryRevision,q=form.elements.customer_name.value.trim();if(!q){form.querySelector('[data-quote-customers]').innerHTML='';return;}timer=setTimeout(async()=>{try{guard();const data=await api('/api/customer-choice/matches?q='+encodeURIComponent(q));guard();if(form.isConnected&&rev===queryRevision)showCustomers(data);}catch(e){if(form.isConnected&&rev===queryRevision)form.querySelector('.formerror').textContent=e.message;}},250);};
  form.elements.customer_name.addEventListener('input',e=>{if(selected){form.elements.customer_phone.value='';form.elements.customer_phone.readOnly=false;}selected=null;queryRevision++;if(!e.isComposing)search();});form.elements.customer_name.addEventListener('compositionend',search);
  form.elements.customer_phone.addEventListener('input',()=>{selected=null;queryRevision++;confirmedPhone='';form.querySelector('[data-quote-new-confirm]').hidden=true;});
 }
 form.elements.model.addEventListener('change',()=>{const model=models.find(m=>m.id===Number(form.elements.model.value));form.elements.amount.placeholder=model?'指导价 '+money(model.guide_price_cents):'';});
 form.querySelector('[data-act=quote-inline-model]')?.addEventListener('click',()=>{
  guard();const saved={...Object.fromEntries(new FormData(form)),selectedCustomer:selected,request_id};for(const k of ['addon','insurance','agency'])saved[k]=form.elements[k].checked;
  catalogEntryDialog({onSaved:async result=>{guard();await salesQuoteForm(row,lead,{...saved,model:result.model.id});},onCancel:async()=>{guard();await salesQuoteForm(row,lead,saved);}}).catch(e=>toast(e.message,true));
 });
}

async function salesQuoteAction(key){
 const row=state.salesQuoteOrder,a=row?.actions.find(x=>x.key===key);if(!a?.enabled)throw new Error(a?.reason||'当前不能办理此动作。');
 const request_id=requestKey(),defaults={},fields=a.fields.map(f=>({...f}));let vehicles=[];
 if(key==='refund_excess')defaults.amount=((row.excess_cents||0)/100).toFixed(2);
 else if(fields.some(f=>f.key==='amount'))defaults.amount=(Math.max(0,row.amount_cents-row.paid_cents)/100).toFixed(2);
 if(key==='allocate'){vehicles=(await api('/api/sales-quotes/orders/'+row.id+'/vehicles')).items;if(!vehicles.length)throw new Error('本版车型暂无可用且已明确归属的本店车辆。');fields[0]={...fields[0],key:'vehicle',type:'select',options:vehicles.map(x=>x.label)};}
 await formDialog(a.label,fields,defaults,values=>{if(key==='allocate'){values.vehicle_id=vehicles.find(v=>v.label===values.vehicle)?.id;delete values.vehicle;}return api(`/api/flow/cases/${row.id}/actions/${key}`,{method:'POST',body:{request_id,version:row.version,values}});},{caseId:row.id,notice:a.confirm||'确认本人已核对实际事实；报价审批和签回均与当前版本绑定。',submit:a.label});
}
document.addEventListener('click',async event=>{const el=event.target.closest('[data-act]');if(!el?.dataset.act.startsWith('sales-quote-'))return;try{if(el.dataset.act==='sales-quote-new')await salesQuoteNew();else if(el.dataset.act==='sales-quote-revise')await salesQuoteForm(state.salesQuoteOrder);else if(el.dataset.act==='sales-quote-action')await salesQuoteAction(el.dataset.key);}catch(error){toast(error.message,true);}});
