'use strict';
let transferContext=null;
function clearTransferSession(){transferContext=null;}
const transferActions={approve:'批准本店安排',reject_request:'拒绝调拨申请',cancel:'撤销申请',dispatch:'确认实物发出',receive:'分批验收',return_ship:'拒收物资发运退回',return_receive:'确认退回入库'};
function transferQty(value,allowZero=false){const s=String(value).trim();if(!/^\d+(\.\d{1,3})?$/.test(s))throw new Error('数量最多保留三位小数。');const [a,b='']=s.split('.');const n=Number(a)*1000+Number(b.padEnd(3,'0'));if(!Number.isSafeInteger(n)||n>(10**9)||n<(allowZero?0:1))throw new Error('数量超出允许范围。');return n;}
const transferQuantity=n=>(n/1000).toLocaleString('zh-CN',{maximumFractionDigits:3});
function transferLinesHTML(lines){const columns=['quantity_milli','sent_milli','accepted_milli','uninspected_milli','return_pending_milli','return_in_transit_milli','returned_milli'];const labels=['申请','已发出','已入库','待验收','拒收待退','退回在途','已退回'];if(lines.some(l=>l.lost_milli!==undefined)){columns.push('lost_milli');labels.push('原损失已确认');}return `<div class="transfer-desktop">${table(['物资','单位',...labels],lines.map(l=>[E(l.name)+'<br><span class="muted">'+E(l.sku)+'</span>',E(l.unit),...columns.map(k=>transferQuantity(l[k]))]))}</div><div class="transfer-mobile">${lines.map(l=>`<article class="transfer-mobile-line"><strong>${E(l.name)}</strong><p class="muted">${E(l.sku)} · ${E(l.unit)}</p><dl>${columns.map((k,i)=>`<div><dt>${labels[i]}</dt><dd>${transferQuantity(l[k])}</dd></div>`).join('')}</dl></article>`).join('')}</div>`;}
async function transfersPage(id){
 if(state.store==='all')return heading('跨店物资调拨')+storeNotice()+'<div class="notice">请选择本店查看调出与调入事项。集团内部往来不作为对外收入。</div>';
 if(!id){const d=await api('/api/transfers');return heading('跨店物资调拨','',canWrite()&&['admin','manager','inventory'].includes(state.user.role)?b('transfer-new','申请调拨','','primary'):'')+panel('本店调拨',table(['单号','方向','对方门店','状态','计划日期',''],d.items.map(r=>[E(r.number),r.side==='source'?'调出':'调入',E(r.side==='source'?r.to_store_name:r.from_store_name),E(r.status_label),E(r.due_date),b('open','办理',`data-route="transfers/${r.id}"`)])));}
 const r=await api('/api/transfers/'+id);transferContext=r;
 return heading('物资调拨',r.number+' · '+r.from_store_name+' → '+r.to_store_name,b('open','返回调拨','data-route="transfers"'))+
 panel('当前安排',`<div class="spread"><strong>${E(r.status_label)}</strong>${b('open','业务任务与上传凭据',`data-route="case/${r.case_id}"`)}</div><p>调出方${r.source_approved?'已批准':'待批准'} · 调入方${r.destination_approved?'已批准':'待批准'} · 计划 ${E(r.due_date)}</p><p>${E(r.reason)}</p>${r.active_exception_id?`<div class="notice">本调拨有在办运输差异，所有收发暂时暂停。${b('open','继续差异核对',`data-route="transfer-exceptions/${r.active_exception_id}"`)}</div>`:''}<div class="row">${canWrite()?r.actions.map(a=>b('transfer-action',transferActions[a],`data-key="${a}"`,['receive','dispatch','approve'].includes(a)?'primary':'')).join(''):''}</div>`)+
 panel('实物明细',transferLinesHTML(r.lines))+(r.flow_version===3?panel('运输差异',`<p>先记实际合格入库与原退，再核对剩余短缺或在手坏件；已入库物资不在此减少。</p><div class="row">${canWrite()&&r.status==='transit'&&!r.active_goods_recovery_id&&['admin','inventory'].includes(state.user.role)?b('transfer-exception-new',r.active_exception_id?'继续当前差异':'核对剩余原批次',`data-transfer="${r.id}"`):''}${(r.exception_ids||[]).map(id=>b('open','差异与原追偿 '+id,`data-route="transfer-exceptions/${id}"`)).join('')}</div>`):'')+
 (r.flow_version===3&&r.lines.some(l=>l.lost_milli>0)?panel('原物资找回',`${r.active_goods_recovery_id?'<div class="notice">原物资找回正在处理，原调拨收发、赔付和新增划款暂停；请从本次找回入口继续核对。</div>':'<p>实际找到原损失物资后，关联原批次复验；原损失保持可查，恢复库存及承担另有记录。</p>'}<div class="row">${canWrite()&&['admin','inventory'].includes(state.user.role)?b('transfer-goods-new','登记本人实际找到',`data-transfer="${r.id}"`):''}${(r.goods_recovery_ids||[]).map(id=>b('open','找回处理 '+id,`data-route="transfer-goods-recoveries/${id}"`)).join('')}</div>`):'')+
 (full()?panel('库存价值及往来',table(['物资','发出价值（元）','已验收价值（元）','退回价值（元）',...(r.flow_version===3?['原损失（元）']:[]),'仍在途价值（元）'],r.lines.map(l=>[E(l.name),money(l.sent_value_cents),money(l.accepted_value_cents),money(l.returned_value_cents),...(r.flow_version===3?[money(l.lost_value_cents)]:[]),money(l.in_transit_value_cents)])))+'<p class="muted">验收入库价值形成双方等额往来；集团汇总抵销。这里没有登记银行划款。</p>':'')+
 panel('交接记录',table(['日期','物资','动作','数量','说明','凭据'],r.movements.map(m=>[E(m.business_date),E(r.lines.find(l=>l.id===m.line_id)?.name),E(m.label),transferQuantity(m.quantity_milli),E(m.reason),m.evidence_id?b('downloadfile','本店凭据',`data-id="${m.evidence_id}"`):'由对方保管'])));
}
async function transferNew(){
 const [destinations,items]=await Promise.all([api('/api/transfers/destinations'),api('/api/flow/lookup/item')]);
 const choices=items.items||items;
 const option=choices.map(x=>`<option value="${x.id}">${E(x.label)}</option>`).join('');
 const lineHTML=()=>`<div class="transfer-input-line"><label>本店物资<select name="item_id" required><option value="">请选择</option>${option}</select></label><label>调拨数量<input name="quantity" inputmode="decimal" required></label>${b('transfer-remove-line','删除此行')}</div>`;
 const html=`<form><div class="formgrid"><label>调入门店<select name="destination" required><option value="">请选择</option>${destinations.items.map(x=>`<option value="${x.id}">${E(x.name)}</option>`).join('')}</select></label><label>计划日期<input name="due_date" type="date" value="${day()}" required></label><label class="wide">申请原因<textarea name="reason" required minlength="2" maxlength="500"></textarea></label></div><div id="transfer-lines">${lineHTML()}</div>${b('transfer-add-line','增加物资行')}<div class="formerror" role="alert"></div><button type="submit" class="primary">提交双方审批</button></form>`;
 const request_id=requestKey();const d=modal('申请跨店物资调拨',html,async form=>{const lines=[...form.querySelectorAll('.transfer-input-line')].map(el=>({item_id:Number(el.querySelector('[name=item_id]').value),quantity_milli:transferQty(el.querySelector('[name=quantity]').value)}));const result=await api('/api/transfers',{method:'POST',body:{request_id,destination_store_id:Number(form.elements.destination.value),due_date:form.elements.due_date.value,reason:form.elements.reason.value,lines}});closeModal();location.hash='transfers/'+result.id;});
 d.querySelector('[data-act=transfer-add-line]').onclick=()=>{if(d.querySelectorAll('.transfer-input-line').length>=80)return;d.querySelector('#transfer-lines').insertAdjacentHTML('beforeend',lineHTML());};
 d.addEventListener('click',e=>{if(e.target.closest('[data-act=transfer-remove-line]')&&d.querySelectorAll('.transfer-input-line').length>1)e.target.closest('.transfer-input-line').remove();},{signal:(()=>{const c=new AbortController();d.addEventListener('close',()=>c.abort(),{once:true});return c.signal;})()});
}
async function transferAction(key){
 const r=transferContext,request_id=requestKey();const basic=[F('reason','本次确认说明','textarea')];if(!['approve','reject_request','cancel'].includes(key))basic.unshift({...F('evidence_id','本单实际交接凭据','file'),file_category:'evidence'});
 let extra='';let targets=[];
 if(key==='receive'){
  const lookup=await api('/api/flow/lookup/item'),items=lookup.items||lookup;
  extra=r.lines.filter(l=>l.uninspected_milli>0).map(l=>`<div class="transfer-receive-line" data-id="${l.id}"><strong>${E(l.name)} · 待验收 ${transferQuantity(l.uninspected_milli)} ${E(l.unit)}</strong><div class="formgrid"><label>验收合格数量<input name="accept_${l.id}" value="0" inputmode="decimal" required></label><label>拒收数量<input name="reject_${l.id}" value="0" inputmode="decimal" required></label><label class="wide">本店接收物资<select name="item_${l.id}"><option value="">合格入库时选择</option>${items.map(x=>`<option value="${x.id}">${E(x.label)}</option>`).join('')}</select></label></div></div>`).join('');
  if(!extra)throw new Error('本次调拨已无待验收物资；拒收件请办理退回。');
 }
 if(['return_ship','return_receive'].includes(key)){
  targets=r.movements.filter(m=>m.kind===(key==='return_ship'?'reject':'return_ship')).map(m=>({...m,left:m.remaining_milli??(m.quantity_milli-r.movements.filter(x=>x.original_id===m.id&&x.kind===(key==='return_ship'?'return_ship':'return_receive')).reduce((sum,x)=>sum+x.quantity_milli,0))})).filter(m=>m.left>0);
  if(!targets.length)throw new Error('当前没有尚未退回或尚未处理的原批次；已核销损失不会再次发运。');
  extra=`<label>选择退回批次<select name="target" required>${targets.map(m=>`<option value="${m.id}">${E(r.lines.find(l=>l.id===m.line_id)?.name)} · ${transferQuantity(m.left)}</option>`).join('')}</select></label>`+(key==='return_receive'?'<label>本次实际入库数量<input name="returned_qty" inputmode="decimal" required></label>':'');
  if(key==='return_receive'&&r.flow_version===3)extra+='<label><input name="passed" type="checkbox" required>本人已核对本次实际退回物资质量合格、可入库；坏件另按运输差异处理。</label>';
 }
 const fields=(await Promise.all(basic.map(f=>fieldHTML(f,defaultValue(f),r.case_id)))).join('');
 modal(transferActions[key],`<form><p class="muted">${E(r.number)}。请先在本店业务单上传实际凭据；系统不会代替实际运输和交接。</p><div class="formgrid">${fields}</div>${extra}<div class="formerror" role="alert"></div><button type="submit" class="primary">确认${E(transferActions[key])}</button></form>`,async form=>{
  const values={reason:form.elements.reason.value};if(form.elements.evidence_id)values.evidence_id=Number(form.elements.evidence_id.value);
  if(key==='receive'){values.lines=[...form.querySelectorAll('.transfer-receive-line')].map(el=>{const id=Number(el.dataset.id);return {line_id:id,item_id:Number(form.elements['item_'+id].value)||null,accept_milli:transferQty(form.elements['accept_'+id].value,true),reject_milli:transferQty(form.elements['reject_'+id].value,true)};}).filter(l=>l.accept_milli+l.reject_milli>0);if(!values.lines.length)throw new Error('请填写至少一行本次实际验收或拒收数量。');}
  if(key==='return_ship')values.rejection_id=Number(form.elements.target.value);
  if(key==='return_receive'){values.shipment_id=Number(form.elements.target.value);values.quantity_milli=transferQty(form.elements.returned_qty.value);if(r.flow_version===3)values.passed=form.elements.passed.checked;}
  await api(`/api/transfers/${r.id}/actions/${key}`,{method:'POST',body:{request_id,version:r.version,case_version:r.case_version,values}});closeModal();await render();
 });
}
document.addEventListener('click',async e=>{const el=e.target.closest('[data-act]');if(!el||el.disabled)return;try{if(el.dataset.act==='transfer-new')await transferNew();if(el.dataset.act==='transfer-action')await transferAction(el.dataset.key);}catch(error){toast(error.message,true);}});
