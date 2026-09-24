'use strict';
// Only the explicit grant endpoints serve receiving employees. There is no
// shortcut to native source URLs or automatic related-record/file traversal.
let dossierEpoch=0,dossierExpiryTimer;
const dossierDecisions={approve:'独立批准',reject:'不予批准',cancel:'取消申请',revoke:'撤销授权'};
function clearDossierGrantsSession(){dossierEpoch++;clearTimeout(dossierExpiryTimer);state.dossierGrant=null;state.dossierCatalog=null;state.dossierSnapshot=null;}
function leaveDossierGrantsView(){dossierEpoch++;clearTimeout(dossierExpiryTimer);state.dossierGrant=null;state.dossierSnapshot=null;}
function dossierGuard(epoch,store,user){return epoch===dossierEpoch&&String(state.store)===store&&state.user?.id===user;}
function dossierCaseLink(row){return state.dossierCatalog?.can_propose&&!['business_entity','opening_import','reconciliation','interstore_clearing','retail_group_rule','business_finance'].includes(row.kind)?b('dossier-new','申请跨店协同',`data-case="${row.id}"`):'';}
function dossierForm(body,submit){return `<form><div class="stack">${body}</div><div class="formerror mt18" role="alert"></div><div class="modalfoot">${b('close','取消')}<button class="primary" type="submit">${E(submit)}</button></div></form>`;}
function dossierConfirm(){return '<label class="checkrow"><input type="checkbox" name="confirmed" required>我已核对指定员工、原单范围及逐件文件内容，确认本次决定。</label>';}
function dossierRecord(record){
 if(!record||!record.case)return empty('此授权不包含原单快照','仅可读取明确勾选的文件。');
 const c=record.case;
 let h=panel('已冻结的原单快照',facts({单据号:c.number,事项:c.kind_label,状态:c.state_label,标题:c.title,原版本:c.version,业务日期:c.business_date,计划日期:c.due_date||'—',完成日期:c.completed_date||'—'}));
 if(record.customer)h+=panel('本单客户',facts({姓名:record.customer.name,...('phone'in record.customer?{电话:record.customer.phone,允许联系:record.customer.contact_allowed?'是':'否'}:{})}));
 if(record.vehicle)h+=panel('本单车辆',facts({VIN:record.vehicle.vin,车型:record.vehicle.model,颜色:record.vehicle.color}));
 if(record.financials)h+=panel('明确批准的金额快照',facts({约定金额:money(record.financials.amount_cents)+' 元',已收或已结:money(record.financials.paid_cents)+' 元',原成本:record.financials.cost_cents==null?'原单未记录成本':money(record.financials.cost_cents)+' 元'})+`<p class="fieldhelp">${E(record.financials.basis)}</p>`);
 h+=panel('原办理事件',table(['原发生时间','已记录事项','原状态','后状态'],record.events.map(e=>[time(e.occurred_at),E(e.label),E(e.from_state),E(e.to_state)]))+(record.events_omitted?`<p class="fieldhelp">仅含提交前最近200条事件摘要；更早 ${Number(record.events_omitted)} 条和事件内部明细不在此范围。</p>`:''));
 return h;
}
function dossierFiles(grant,files,receiver){return panel('逐件文件',files.length?table(['原文件编号','文件名与类别','大小','操作'],files.map(f=>[String(Number(f.id)),E(f.name)+'<br><span class="muted">'+E(state.catalog?.upload_categories?.[f.category]||state.catalog?.document_types?.[f.category]||f.category)+'</span>',number(f.size)+' 字节',receiver?b('dossier-download','核验并下载',`data-grant="${grant.id}" data-file="${f.id}"`):b('downloadfile','核对原文件',`data-id="${f.id}"`)])):empty('没有授权文件','后续上传不会自动加入，关联的签回件也不会自动开放。'));}
async function dossierPage(box='received',id=null){
 const epoch=++dossierEpoch,store=String(state.store),user=state.user?.id;
 clearTimeout(dossierExpiryTimer);state.dossierGrant=null;state.dossierSnapshot=null;
 const catalog=await api('/api/dossier-grants/catalog');
 if(!dossierGuard(epoch,store,user))return '';
 state.dossierCatalog=catalog;
 if(!catalog.can_read)return heading('档案授权')+empty('请先选择本人有权限的具体门店','集团汇总不开放原单或附件。');
 const tabs=`<nav class="tabs">${[['received','收到的授权'],['sent','本店发出'],...(catalog.can_review?[['review','待我复核']]:[])].map(([key,name])=>`<a href="#dossier-grants/${key}" class="${box===key?'active':''}">${E(name)}</a>`).join('')}</nav>`;
 const top=heading('档案授权','只读原单快照和指定文件，不开放整份客户档案，也不修改原业务。',catalog.can_propose?b('dossier-pick','选择本店原业务','','primary'):'')+tabs;
 if(!id){
  const d=await api('/api/dossier-grants?'+new URLSearchParams({box,page:state.page||1}));
  if(!dossierGuard(epoch,store,user))return '';
  return top+panel(box==='review'?'等待原店不同人员复核':box==='sent'?'本店发出记录':'指定给我的授权',table(['授权编号','门店','接收员工','状态','到期时间',''],d.items.map(r=>[String(r.id),E(r.from_store_name)+' → '+E(r.to_store_name),E(r.recipient_name||'本人'),pill(r.effective_status,r.status_label),time(r.expires_at),b('open','查看',`data-route="dossier-grants/${box}/${r.id}"`)]))+pager(d.total,d.page,d.page_size));
 }
 const g=await api('/api/dossier-grants/'+id);
 if(!dossierGuard(epoch,store,user))return '';
 state.dossierGrant=g;
 let h=top+panel('授权 '+g.id,facts({来源门店:g.from_store_name,接收门店:g.to_store_name,接收员工:g.recipient_name||'本人',状态:g.status_label,到期时间:time(g.expires_at)})+`<div class="row">${Object.keys(dossierDecisions).filter(k=>k==='approve'||k==='reject'?g.can_review:k==='cancel'?g.can_cancel:g.can_revoke).map(k=>b('dossier-decision',dossierDecisions[k],`data-key="${k}"`,k==='approve'?'primary':'')).join('')}${b('refresh','重新核验')}</div>`);
 if(g.source_side){
  h+=panel('本次明确范围',facts({用途:g.purpose,原单版本:g.source_case_version,原单快照:g.include_record?'包含':'不包含',联系电话:g.include_contact?'明确包含':'不包含',金额成本:g.include_financials?'明确包含':'不包含'})+'<p class="fieldhelp">请核对要分享的资料。提交后资料有变化，请重新申请。</p>')+dossierRecord(g.preview)+dossierFiles(g,g.files,false);
  h+=panel('决定记录',table(['时间','决定','员工编号','说明'],g.decisions.map(d=>[time(d.occurred_at),E(dossierDecisions[d.action]),String(d.actor_id),E(d.reason)])));
 }else if(g.can_read){
  try{
   const content=await api(`/api/dossier-grants/${g.id}/${g.include_record?'record':'files'}`);
   if(!dossierGuard(epoch,store,user))return '';
   state.dossierSnapshot=content;
   h+='<div class="notice">这里显示申请时的资料。</div>'+dossierRecord(content.record)+dossierFiles(g,content.files,true);
   // Clear live DOM at expiry. Long-lived pages revalidate on focus/visibility.
   const ms=Math.max(0,new Date(g.expires_at).getTime()-Date.now());
   dossierExpiryTimer=setTimeout(()=>{if(dossierGuard(epoch,store,user)&&state.route.startsWith('dossier-grants/')){state.dossierSnapshot=null;render();}},Math.min(ms+10,2147483000));
  }catch(error){if(!dossierGuard(epoch,store,user))return '';state.dossierSnapshot=null;h+=empty('当前不可读取',error.message);}
 }else h+=empty('当前不可读取','等待原店复核，或因到期、撤销、账号及岗位变化停止读取。未开放的原单和文件不会展示。');
 return h;
}
async function dossierPick(){
 const epoch=dossierEpoch,store=String(state.store),user=state.user?.id;
 modal('选择本店原业务','<form id="dossier-search"><label>原单号或标题<input name="q" type="search" required minlength="2" maxlength="100" placeholder="输入单号或标题关键词"></label><div class="formerror" role="alert"></div><div class="modalfoot">'+b('close','关闭')+'<button type="submit" class="primary">查找</button></div></form><div id="dossier-search-results" class="mt18"></div>',async form=>{
  const d=await api('/api/flow/cases?'+new URLSearchParams({q:form.elements.q.value,page:1}));
  if(!dossierGuard(epoch,store,user)||!$('#dossier-search-results'))return;
  const items=d.items.filter(r=>!['business_entity','opening_import','reconciliation','interstore_clearing','retail_group_rule','business_finance'].includes(r.kind));
  $('#dossier-search-results').innerHTML=table(['单号','标题',''],items.map(r=>[E(r.number),E(r.title),b('dossier-new','选择此原单',`data-case="${r.id}"`)]))+(d.total>d.items.length?'<p class="fieldhelp">仅显示首批结果，请缩小关键词。</p>':'');
 });
}
async function dossierNew(caseId){
 const epoch=dossierEpoch,store=String(state.store),user=state.user?.id;
 const options=await api('/api/dossier-grants/source/'+caseId);
 if(!dossierGuard(epoch,store,user))return;
 const request_id=requestKey();let selected=null,selectionEpoch=0;
 const localDate=new Date(Date.now()+7*86400000);localDate.setMinutes(localDate.getMinutes()-localDate.getTimezoneOffset());
 modal('跨店协同',dossierForm(`<p class="notice">${E(options.notice)}</p><p>原单 ${E(options.case.number)} · 版本 ${options.case.version}</p><label>接收门店<select name="to_store_id" required><option value="">请选择</option>${options.stores.map(s=>`<option value="${s.id}">${E(s.label)}</option>`).join('')}</select></label><label>接收人<select name="recipient_id" required disabled><option value="">先选择门店</option></select></label><label>协同事项<textarea name="purpose" required minlength="3" maxlength="500"></textarea></label><label>到期时间<input name="expires_at" type="datetime-local" required value="${localDate.toISOString().slice(0,16)}"></label><label class="checkrow"><input name="include_record" type="checkbox" checked>分享业务信息</label><label class="checkrow"><input name="include_contact" type="checkbox">分享联系电话</label><label class="checkrow"><input name="include_financials" type="checkbox" disabled>分享金额及成本</label><div id="dossier-file-choices">先选择接收员工，再逐件选择文件。</div><p class="fieldhelp">文件不默认勾选。正文和截图可能包含敏感信息，请实际核对，不依赖文件类别自动脱敏。</p>${dossierConfirm()}`,'提交原店独立复核'),async form=>{
  if(!selected||Number(form.elements.recipient_id.value)!==selected.recipient_id)throw new Error('请重新选择接收员工并核对范围。');
  const values={source_case_id:caseId,source_case_version:options.case.version,to_store_id:Number(form.elements.to_store_id.value),recipient_id:Number(form.elements.recipient_id.value),purpose:form.elements.purpose.value,expires_at:new Date(form.elements.expires_at.value).toISOString(),include_record:form.elements.include_record.checked,include_contact:form.elements.include_contact.checked,include_financials:form.elements.include_financials.checked,file_ids:$$('[name=dossier_file]:checked',form).map(x=>Number(x.value)),confirmed:form.elements.confirmed.checked};
  if(!dossierGuard(epoch,store,user))throw new Error('门店或账号已变化，请重新打开申请。');
  const r=await api('/api/dossier-grants',{method:'POST',body:{request_id,values}});if(!dossierGuard(epoch,store,user))return;closeModal();go('dossier-grants/sent/'+r.grant.id);await render();
 });
 const form=$('#modal form');
 function scopeCheckboxes(){const record=form.elements.include_record.checked;for(const key of ['include_contact','include_financials']){const input=form.elements[key];input.disabled=!record||key==='include_financials'&&!selected?.can_financials;if(input.disabled)input.checked=false;}}
 form.elements.include_record.onchange=scopeCheckboxes;
 form.elements.to_store_id.onchange=async()=>{
  const seq=++selectionEpoch;selected=null;form.elements.recipient_id.disabled=true;form.elements.recipient_id.innerHTML='<option value="">请选择员工</option>';$('#dossier-file-choices').textContent='先选择接收员工。';scopeCheckboxes();
  const sid=Number(form.elements.to_store_id.value);if(!sid)return;
  try{const d=await api(`/api/dossier-grants/source/${caseId}?to_store_id=${sid}`);if(seq!==selectionEpoch||!dossierGuard(epoch,store,user)||!form.isConnected)return;form.elements.recipient_id.innerHTML='<option value="">请选择员工</option>'+d.recipients.map(r=>`<option value="${r.id}">${E(r.label)} · ${E(roleNames[r.role])}</option>`).join('');form.elements.recipient_id.disabled=false;}catch(error){if(form.isConnected)$('.formerror',form).textContent=error.message;}
 };
 form.elements.recipient_id.onchange=async()=>{
  const seq=++selectionEpoch;selected=null;$('#dossier-file-choices').textContent='正在核对可授权文件…';scopeCheckboxes();const rid=Number(form.elements.recipient_id.value);if(!rid)return;
  try{const d=await api(`/api/dossier-grants/source/${caseId}?to_store_id=${Number(form.elements.to_store_id.value)}&recipient_id=${rid}`);if(seq!==selectionEpoch||!dossierGuard(epoch,store,user)||!form.isConnected)return;selected={recipient_id:rid,can_financials:d.can_financials};$('#dossier-file-choices').innerHTML=d.files.length?'<h3>逐件选择原文件</h3>'+d.files.map(f=>`<label class="checkrow"><input type="checkbox" name="dossier_file" value="${f.id}"><span>${E(f.name)} · 原编号 ${f.id} · ${number(f.size)} 字节</span></label>`).join(''):'没有双方岗位均可读取且检查通过的文件。';scopeCheckboxes();}catch(error){if(form.isConnected)$('.formerror',form).textContent=error.message;}
 };
}
async function dossierDecision(action){
 const g=state.dossierGrant,request_id=requestKey(),epoch=dossierEpoch,store=String(state.store),user=state.user?.id;if(!g)throw new Error('授权已变化，请刷新。');
 modal(dossierDecisions[action],dossierForm(`<p>${E(g.recipient_name)} · ${E(g.to_store_name)} · 到期 ${time(g.expires_at)}</p><p class="fieldhelp">${action==='approve'?'只批准页面展示的原版本和逐件清单，后续内容不自动加入。':action==='revoke'?'提交后阻止后续读取。已经合法下载的副本不能远程删除。':'原申请、原单和文件均保留，不改变原业务。'}</p><label>核对说明<textarea name="reason" required minlength="3" maxlength="500"></textarea></label>${dossierConfirm()}`,dossierDecisions[action]),async form=>{
  if(!dossierGuard(epoch,store,user))throw new Error('门店或账号已变化，请重新打开授权。');
  await api(`/api/dossier-grants/${g.id}/actions/${action}`,{method:'POST',body:{request_id,version:g.version,values:{reason:form.elements.reason.value,confirmed:form.elements.confirmed.checked}}});if(!dossierGuard(epoch,store,user))return;closeModal();await render();
 });
}
document.addEventListener('click',async event=>{const el=event.target.closest('[data-act]');if(!el?.dataset.act.startsWith('dossier-'))return;try{switch(el.dataset.act){case'dossier-pick':await dossierPick();break;case'dossier-new':await dossierNew(Number(el.dataset.case));break;case'dossier-decision':await dossierDecision(el.dataset.key);break;case'dossier-download':await download(`/api/dossier-grants/${Number(el.dataset.grant)}/files/${Number(el.dataset.file)}`,'已批准文件');break;}}catch(error){toast(error.message,true);if(['dossier-download'].includes(el.dataset.act)&&state.route.startsWith('dossier-grants/')){state.dossierSnapshot=null;await render();}}});
function dossierRecheckVisible(){if(state.user&&state.route.startsWith('dossier-grants/')&&!document.hidden&&!$('#modal')?.open){state.dossierSnapshot=null;render();}}
window.addEventListener('focus',dossierRecheckVisible);
document.addEventListener('visibilitychange',dossierRecheckVisible);
