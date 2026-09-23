'use strict';
function clearSalesQuotesSession(){delete state.salesQuoteOrder;}
const salesQuoteCanWrite=()=>canWrite()&&['admin','manager','sales'].includes(state.user.role);
const salesQuoteOutcome={activated:'客户已确认并生效',rejected:'主管退回',withdrawn:'已撤回'};
async function salesQuotesPage(id){
 if(state.store==='all')return heading('车辆报价与预订')+storeNotice();
 if(!id){const d=await api('/api/flow/cases?kind=order&page='+state.page);return heading('车辆报价与预订','每次报价、价格批准、配车和客户签回分别留档。',salesQuoteCanWrite()?b('sales-quote-new','建立车辆报价','','primary'):'')+storeNotice()+panel('本店车辆订单',table(['客户与订单','报价流程','状态',''],d.items.map(r=>[E(r.title)+'<br>'+E(r.number),[3,4].includes(r.flow_version)?'版本报价':'原流程 '+r.flow_version,pill(r.state,r.state_label),b('open','办理',`data-route="${[3,4].includes(r.flow_version)?'sales-quotes':'case'}/${r.id}"`)])))+pager(d.total);}
 const r=await api('/api/sales-quotes/orders/'+id);state.salesQuoteOrder=r;state.row=r;
 const active=r.quotes.find(q=>q.id===r.active_quote_id),pending=r.quotes.find(q=>q.id===r.pending_quote_id),selected=pending||active;
 const quoteCard=q=>`<p><strong>第 ${q.revision} 版 · ${E(q.model_snapshot.name)}</strong> · ${E(q.model_snapshot.code)}</p><p>${q.amount_cents!==undefined?'车辆价款 '+money(q.amount_cents)+' 元 · ':''}预计交付 ${E(q.delivery_due)}</p><p>新确认有效期至 ${E(q.valid_until)} · ${E(q.resolution?salesQuoteOutcome[q.resolution.outcome]:q.review?'主管已批准，待客户签回':'待独立主管复核')}</p><p>另单服务：${[['addon','精品加装'],['insurance','本店保险'],['agency','代办服务']].filter(([k])=>q.services[k]).map(([,label])=>label).join('、')||'无'}</p>${q.terms!==undefined?`<p class="wrap">本版约定：${E(q.terms)}</p>`:''}${q.review?`<p>价格复核意见：${E(q.review.reason)}</p>`:''}`;
 let html=heading('车辆报价 · '+r.number,r.customer?.name||'',b('open','返回车辆订单','data-route="sales-quotes"'))+storeNotice();
 if(pending)html+=panel('当前待确认报价',quoteCard(pending)+'<p>此版本尚未生效，暂停实际收款、PDI 和交车。原有效报价及文件保留，主管批准后须按本版与当前 VIN 重新签回。</p>');
 if(active)html+=panel('当前有效报价',quoteCard(active));
 if(!selected)html+=panel('等待重新报价','<p>当前没有可继续执行的报价，请销售提交新版本。</p>');
 html+=panel('报价变更',`<p>车辆尚未实际出库时可提出新版本。已执行的配套服务、已出库或已提车辆，须按原单售后处理。换车由库管先确认释放原占用，重新配车和检查。</p>`+(r.can_propose&&canWrite()?b('sales-quote-revise','提交新的报价版本','','primary'):'')+b('open','查看退订退车与原款退回','data-route="aftercare"'));
 if(r.amount_cents!==undefined)html+=panel('车辆款项',`<div class="cards">${[['当前约定价款',r.amount_cents],['已收及已抵用',r.paid_cents],['降价后待退差额',r.excess_cents||0]].map(([label,value])=>`<div class="card"><span>${label}（元）</span><strong>${money(value)}</strong></div>`).join('')}</div><p>车辆价款不包含另单服务。已抵用预收的超额部分回原预收账，实际超收现金由财务按原收款退回；退款完成前不能出库。</p>`);
 html+=panel('现在可以做什么',(r.actions||[]).map(a=>`<div class="actioncard">${b('sales-quote-action',a.label,`data-key="${a.key}" ${!canWrite()||!a.enabled?'disabled':''}`,a.enabled?'primary':'')}<p>${E(a.reason||a.confirm||'')}</p></div>`).join('')||'<p>等待相关岗位办理。</p>');
 const docKinds=['inventory','technician','reception','customer_service'].includes(state.user.role)?['business']:['contract','handover','business'];
 html+=panel('本版文档与实际凭据',(canWrite()?b('upload','上传实际凭据')+docKinds.map(k=>b('generatedoc','生成'+state.catalog.document_types[k],`data-kind="${k}"`)).join(''):'')+fileList(r.files));
 if(r.children.length)html+=panel('配套及后续业务',r.children.map(c=>`<div class="listrow"><div><strong>${E(c.kind_label)}</strong><p>${pill(c.state,c.state_label)}</p></div>${b('open','查看办理',`data-route="case/${c.id}"`)}</div>`).join(''));
 if(r.payments?.length)html+=panel('实际原款与退款',table(['方向／凭证','金额（元）','日期'],r.payments.map(p=>[E(p.direction==='in'?'收款':'原款退款')+'<br>'+E(p.reference),money(p.amount_cents),E(p.business_date)])));
 html+=panel('报价历史',r.quotes.map(q=>`<details ${q.id===r.pending_quote_id?'open':''}><summary>第 ${q.revision} 版 · ${E(q.model_snapshot.name)}</summary>${quoteCard(q)}</details>`).join(''));
 html+=panel('岗位交接',taskList(r.tasks));
 return html;
}
async function salesQuoteNew(leadId=null){
 if(!salesQuoteCanWrite())throw new Error('请切换到有销售办理权限的具体门店。');
 const lead=leadId?await api('/api/flow/cases/'+leadId):null;
 return salesQuoteForm(null,lead);
}
async function salesQuoteForm(row=null,lead=null){
 const [models,customers]=await Promise.all([retailAll('/api/vehicle-catalog'),retailAll('/api/flow/master/customers')]);
 if(!models.length||(!row&&!customers.length))throw new Error('请先配置本店车型目录和本人负责客户。');
 const old=row?.quotes.find(q=>q.id===row.active_quote_id)||row?.quotes.at(-1);const request_id=requestKey();
 const modelOptions=models.map(m=>`<option value="${m.id}" ${old?.model_id===m.id?'selected':''}>${E(m.brand_name)} · ${E(m.series_name)} · ${E(m.name)} · ${E(m.code)}</option>`).join('');
 modal(row?'提交车辆报价新版本':'建立车辆报价',`<form>${!row?`<label>本店客户<select name="customer" required ${lead?'disabled':''}>${customers.map(c=>`<option value="${c.id}" ${c.id===lead?.customer_id?'selected':''}>${E(c.name)} · ${E(c.phone||'')}</option>`).join('')}</select></label>`:''}<label>明确订购车型<select name="model" required>${modelOptions}</select></label><p>车型参数按本次目录版本冻结；指导价是参考，车辆成交价须由另一位主管批准。</p><label>车辆约定价款（元）<input name="amount" inputmode="decimal" value="${old?(old.amount_cents/100).toFixed(2):''}" required></label><div class="formgrid"><label>预计交付日期<input name="due" type="date" value="${E(old?.delivery_due||relativeDay(7))}" min="${day()}" required></label><label>本版客户确认有效期<input name="expires" type="date" value="${relativeDay(7)}" min="${day()}" required></label></div><p>以下配套服务另单报价及结算，不包含在车辆金额中：</p>${[['addon','精品加装'],['insurance','本店保险'],['agency','代办服务']].map(([k,label])=>`<label><input type="checkbox" name="${k}" ${old?.services[k]?'checked':''}> ${label}</label>`).join('')}<label>本版具体约定<textarea name="terms" minlength="2" maxlength="1500" required>${E(old?.terms||'')}</textarea></label><label>建立或变更原因<textarea name="reason" minlength="2" maxlength="500" required></textarea></label><p>提交只生成待审批报价，不确认客户签字、不移动库存、不收取款项。</p><div class="formerror" role="alert"></div><div class="modalfoot"><button type="submit" class="primary">保存报价并交主管复核</button></div></form>`,async form=>{
  const model=models.find(m=>m.id===Number(form.elements.model.value));const quote={model_id:model.id,model_version:model.version,amount_cents:retailScaled(form.elements.amount.value,2),delivery_due:form.elements.due.value,valid_until:form.elements.expires.value,terms:form.elements.terms.value,reason:form.elements.reason.value};
  for(const k of ['addon','insurance','agency'])quote[k]=form.elements[k].checked;
  const r=await api('/api/sales-quotes/orders'+(row?'/'+row.id+'/quotes':''),{method:'POST',body:row?{request_id,version:row.version,quote}:{request_id,customer_id:lead?.customer_id||Number(form.elements.customer.value),lead_id:lead?.id||null,lead_version:lead?.version||null,quote}});closeModal();go('sales-quotes/'+r.id);
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
