'use strict';
let retailGroupUI={};
function clearRetailGroupSession(){retailGroupUI={};}
function rgContext(){const key=String(state.user?.id)+':'+state.store;if(retailGroupUI.key!==key)retailGroupUI={key};return retailGroupUI;}
const rgKinds={principal:'集团本金',bonus:'集团赠金',coupon:'消费券',package:'次数套餐',cash:'原行现金份额'};
const rgStates={authorized:'仅已授权',reserved:'已占额，未核销',captured:'已实际核销',released:'已释放，余款待结',cash:'分笔现金待结'};
const rgActions={reserve:'占用原批次',capture:'确认实际核销',release:'释放未核销方案',restore:'恢复原额度',reassign:'交接待办'};
function rgMoneyCards(values){return '<div class="cards">'+values.map(([label,amount])=>`<div class="card"><span>${E(label)}（元）</span><strong>${money(amount)}</strong></div>`).join('')+'</div>';}
async function retailGroupPage(id){
 const c=rgContext(),catalog=await api(`/api/retail-group/orders/${id}/catalog`);c.catalog=catalog;c.caseId=Number(id);state.row=await api('/api/flow/cases/'+id);
 let html=heading('精品集团混合付款',catalog.number,b('open','返回精品原单',`data-route="retail/${id}"`));
 html+=`<div class="notice warn">${E(catalog.readiness_reason||catalog.limitation)}</div>`;
 if(!catalog.member)return html+panel('客户集团身份','请先明确关联本客户的集团身份并开通会员；姓名或电话相同不会自动合并。'+b('open','办理客户集团身份',`data-route="group/${state.row.customer_id}/${id}"`));
 if(!catalog.has_plan){
  html+=panel('原批次与明确使用范围',facts({'会员':catalog.member.number,'可用本金（元）':money(catalog.member.available_cents)})+catalog.wallets.map(w=>`<div class="card"><strong>${E(w.name)} · ${E(rgKinds[w.kind])}</strong><p>规则版本 ${w.rule_version} · 原到期日 ${E(w.expires_on)} · 可用 ${w.available_units} ${w.kind==='bonus'?'分':'份'}</p><p>${w.usable?'已具备发行时冻结的本店商品范围':E(w.reason)}</p>${(w.scopes||[]).map(s=>`<p>${E(s.sku)} · ${E(s.name)} · ${s.component==='goods'?'商品':'指定安装'}</p>`).join('')}</div>`).join(''));
  if(catalog.can_authorize)html+=panel('客户明确付款约定',b('rg-authorize','核对并冻结原付款方案')+'<p>此步骤只保存客户选择的原批次及原行份额，不占额、不扣款。财务分别核对集团核销和实际现金。</p>');
 }else{
  const row=await api('/api/retail-group/orders/'+id);c.row=row;
  const pending=row.totals.group_return_pending_cents;
  html+=panel('当前原付款与原退',rgMoneyCards([['集团净抵扣',row.totals.group_paid_cents],['剩余现金可收',row.totals.cash_collectable_cents],['原现金可退',row.totals.cash_refund_due_cents],['本金待恢复',pending.principal],['赠金待恢复',pending.bonus],['券待恢复负债',pending.coupon],['套餐待恢复负债',pending.package]])+`<p>${E(row.notice)}</p>`);
  if(row.totals.group_recognized_cents!==undefined)html+=panel('实际履约与优惠承担',rgMoneyCards([['集团原款净履约对价',row.totals.group_recognized_cents],['集团承担优惠',row.totals.group_discount_borne_cents],['本店承担优惠',row.totals.service_discount_borne_cents],['内部结算净额',row.totals.group_internal_settlement_cents]])+'<p>实际退货已即刻减少对应履约与内部往来。整份恢复只转换原权益负债，不再次冲减。内部结算记录不表示资金已清算。</p>');
  for(const t of row.tenders){
   const own=row.tasks.some(task=>task.key==='retail_group_payment'&&task.assignee_id===state.user.id),finance=['admin','finance'].includes(state.user.role);
   const controls=row.write_enabled&&finance&&own?(t.status==='authorized'?[b('rg-action','占用原批次',`data-key="reserve" data-id="${t.id}"`),b('rg-action','释放此方案',`data-key="release" data-id="${t.id}"`)]:t.status==='reserved'?[b('rg-action','确认实际核销',`data-key="capture" data-id="${t.id}"`),b('rg-action','释放未核销占额',`data-key="release" data-id="${t.id}"`)]:[]):[];
   let body=facts({'状态':rgStates[t.status],'原授权抵扣（元）':money(t.credit_cents),'原批次':t.wallet_id?`#${t.wallet_id} · ${t.rule_name} · 版本 ${t.rule_version}`:rgKinds[t.kind]});
   if(t.expires_on)body+=`<div class="notice ${t.expired?'warn':''}">原有效期 ${E(t.expires_on)}。${t.expired?'原批次已过期；恢复原单位不会延长到期日，恢复后也不可直接消费。':'恢复仍沿用此到期日。'}</div>`;
   if(t.consideration_cents!==undefined)body+=facts({'原发行实款分摊（元）':money(t.consideration_cents),'原内部结算（元）':money(t.settlement_cents)});
   body+='<div class="row">'+controls.join('')+'</div>';
   for(const unit of t.units_detail){
    body+=`<div class="card"><strong>原${['coupon','package'].includes(t.kind)?'整数单位':'额度'} ${unit.sequence}</strong>${facts({'原额度（元）':money(unit.credit_cents),'实退对应额度（元）':money(unit.returned_credit_cents),'已恢复（元）':money(unit.restored_credit_cents),'待恢复（元）':money(unit.pending_credit_cents)})}`;
    if(unit.pending_original_unit)body+='<p class="notice warn">尚未凑齐原完整单位。此额度保留为原权益负债，不可消费、不自动清零，也不是履约店现金应退。</p>';
    body+=table(['原商品行','组成','原抵扣（元）','实退对应（元）'],unit.allocations.map(a=>[`#${a.line_id}`,a.component==='goods'?'商品':'安装',money(a.credit_cents),money(a.returned_credit_cents)]));
    const canRestore=row.write_enabled&&finance&&row.tasks.some(task=>task.key==='retail_group_restore'&&task.assignee_id===state.user.id);
    if(unit.restorable&&canRestore)body+=b('rg-action','按原批次实际恢复',`data-key="restore" data-id="${unit.id}"`);
    body+='</div>';
   }
   if(t.original_issuance_case_id)body+=b('open','查看原发行及原款退款入口',`data-route="case/${t.original_issuance_case_id}"`);
   else if(t.issuer_store_id)body+=`<p>原发行门店 #${t.issuer_store_id}。涉及发行实款退款时，由获权原店人员从原批次办理；这里不开放对店原业务或文件。</p>`;
   html+=panel(rgKinds[t.kind],body);
  }
  html+=panel('明确责任与期限',row.tasks.map(t=>`<div class="card"><strong>${E(t.title)}</strong><p>负责人 #${t.assignee_id} · ${E(t.due_date)}${t.due_date<day()?' · 已逾期，需明确交接':''}</p>${row.write_enabled&&['admin','manager'].includes(state.user.role)?b('rg-reassign','交接财务待办',`data-key="${t.key}"`):''}</div>`).join('')||'<p>本次可执行待办已处理。</p>');
 }
 html+=panel('本单原件与办理记录',b('upload','补充原件')+'<p>可核对本单已有原件。上传人和本次办理人分别留痕，无需每岗重复上传。</p>'+fileList(state.row.files||[]));
 return html;
}
async function rgAuthorize(){
 const c=rgContext(),session=c.key,catalog=c.catalog,id=c.caseId,request_id=requestKey();
 const eligible=catalog.wallets.filter(w=>w.usable&&w.available_units>0),evidence=(state.row.files||[]).filter(f=>f.category==='authorization'&&!f.generated&&f.security?.can_use);
 if(!evidence.length)throw new Error('本单尚无可用的客户付款授权原件，请补充并完成检查。');
 const html=`<label>使用本金（元；不用可留空）<input name="principal" inputmode="decimal"></label>`+eligible.map(w=>`<label>${E(w.name)} · #${w.id} · ${w.kind==='bonus'?'赠金分':'整数份数'}<input name="wallet_${w.id}" type="number" min="1" max="${w.available_units}" step="1" placeholder="不用可留空"></label>`).join('')+`<label>本次核对的客户付款授权<select name="evidence" required><option value="">请选择实际凭据</option>${evidence.map(f=>`<option value="${f.id}">${E(f.name)}</option>`).join('')}</select></label><div class="notice warn">本金、赠金逐分原退；券和套餐按原单位累计退回，零头不可消费。原有效期不延期。已完成安装保留费仍按精品原单办理。</div><label class="checklabel"><input type="checkbox" name="confirmed" required>客户已明确选择以上原批次，并知悉原退与有效期规则</label>`;
 modal('冻结精品原付款方案',`<form>${html}<div class="formerror" role="alert"></div><div class="modalfoot">${b('close','返回核对')}<button type="submit" class="primary">只冻结授权，不扣款</button></div></form>`,async form=>{
  if(rgContext().key!==session)throw new Error('门店或账号已改变，请重新打开原单。');
  const selections=[];if(form.elements.principal.value.trim())selections.push({kind:'principal',amount_cents:retailScaled(form.elements.principal.value,2)});
  for(const w of eligible){const value=form.elements['wallet_'+w.id].value;if(value)selections.push({kind:w.kind,wallet_id:w.id,wallet_version:w.version,units:retailScaled(value,0)});}
  if(!selections.length)throw new Error('请明确选择至少一种本金或原权益；纯现金继续从精品原单办理。');
  await api(`/api/retail-group/orders/${id}/actions/authorize`,{method:'POST',body:{request_id,version:catalog.version,values:{member_id:catalog.member.id,member_version:catalog.member.version,evidence_id:Number(form.elements.evidence.value),selections}}});closeModal();await render();
 });
}
async function rgAction(action,id){
 const c=rgContext(),row=c.row,tender=row.tenders.find(t=>t.id===id&&action!=='restore'||t.units_detail.some(u=>u.id===id)&&action==='restore'),request_id=requestKey();
 const fields=[F('evidence_id','本次核对的本单原件','file')];if(action==='release')fields.push(F('reason','客户与原占额核对说明','textarea'));
 await formDialog(rgActions[action],fields,{},v=>{const values={...v,plan_version:row.plan_version,member_version:row.member_version};if(tender.wallet_version)values.wallet_version=tender.wallet_version;if(action==='restore')values.unit_id=id;else values.tender_id=id;if(action==='capture')values.reservation_version=tender.reservation_version;
  return api(`/api/retail-group/orders/${row.case_id}/actions/${action}`,{method:'POST',body:{request_id,version:row.version,values}});
 },{caseId:row.case_id,notice:action==='restore'?'只恢复原本金、赠金或已凑整的原券套餐；不产生现金。恢复保留原有效期。':action==='release'?'释放未核销占额，不制造退款或收款；原行剩余部分成为现金待结。':'请仅确认本人实际核对的原批次；占额与实际核销是两个独立步骤。'});
}
async function rgReassign(key){
 const row=rgContext().row,request_id=requestKey();await formDialog('明确交接集团财务待办',[F('assignee_id','新的财务接手人','employee'),F('due_date','处理期限','date'),F('reason','交接说明','textarea')],{due_date:day()},values=>api(`/api/retail-group/orders/${row.case_id}/actions/reassign`,{method:'POST',body:{request_id,version:row.version,values:{...values,task_key:key,plan_version:row.plan_version}}}),{caseId:row.case_id});
}
async function retailGroupRulesPage(){
 const c=rgContext(),data=await api('/api/retail-group/rules');c.rules=data;
 return (data.readiness_reason?`<div class="notice warn">${E(data.readiness_reason)}</div>`:'')+heading('精品权益商品规则','',data.can_create?b('rg-rule-new','申请商品适用规则'):'')+`<div class="notice warn">旧维修规则和旧钱包不会自动适用于商品。公司尚未确定部分退回与有效期规则时，不可发行商品用途的新批次。</div>`+panel('本店申请',table(['原申请','状态','办理'],data.items.map(r=>[E(r.title),E({draft:'待提交',approval:'待独立批准',completed:'已生效',cancelled:'已取消',rejected:'已拒绝'}[r.state]),b('open','查看',`data-route="retail-group-rule/${r.id}"`)])));
}
async function retailGroupRulePage(id){
 const c=rgContext(),row=await api('/api/retail-group/rules/'+id);c.rule=row;state.row=await api('/api/flow/cases/'+id);
 return (row.readiness_reason?`<div class="notice warn">${E(row.readiness_reason)}</div>`:'')+heading('精品权益商品规则',row.number,b('open','返回规则','data-route="retail-group-rules"'))+panel('原规则版本',facts({'规则':row.rule.name,'版本':row.rule.rule_version,'种类':rgKinds[row.rule.kind]}))+panel('明确公司约定',row.modes?'<p>部分退回：累计原完整单位；恢复沿用原有效期；待恢复非现金负债不自动清零。</p>':'<p>尚未提交，系统不预选公司规则。</p>')+panel('冻结商品范围',table(['门店','商品','用途'],row.scopes.map(s=>[`#${s.store_id}`,E(s.sku+' · '+s.name),s.component==='goods'?'商品':'安装 '+E(s.work_code)])))+panel('本人当前办理',row.actions.map(a=>b('rg-rule-action',{submit:'明确并提交规则',approve:'独立批准',reject:'拒绝申请',cancel:'取消申请'}[a],`data-key="${a}"`)).join('')||'当前没有本人可办理动作。')+panel('本单来源与复核记录',b('upload','补充本单原件')+fileList(state.row.files||[]));
}
async function rgRuleNew(){
 const choices=rgContext().rules.rules,request_id=requestKey();if(!choices.length)throw new Error('请先建立尚未发行的新集团赠金、券或套餐规则版本。');
 const labels=choices.map(r=>`${r.id} · ${r.name} · 版本 ${r.rule_version}`);await formDialog('建立新商品规则申请',[F('rule','本店原集团规则','select',true,labels)],{},async v=>{const result=await api('/api/retail-group/rules',{method:'POST',body:{request_id,rule_id:choices[labels.indexOf(v.rule)].id}});go('retail-group-rule/'+result.case_id);return result;});
}
async function rgRuleAction(action){
 const c=rgContext(),row=c.rule,request_id=requestKey();
 if(action!=='submit')return formDialog(action==='approve'?'独立批准公司商品规则':'结束未生效申请',[...(action==='cancel'?[]:[F('evidence_id','本次复核的本单原件','file')]),F('reason','本人的核对结果','textarea')],{},values=>api(`/api/retail-group/rules/${row.id}/actions/${action}`,{method:'POST',body:{request_id,version:row.version,values}}),{caseId:row.id,notice:'批准不会为旧批次补授商品用途；申请与批准必须由不同获权主管完成。'});
 const stores=(state.stores||[]).filter(s=>['admin','manager'].includes(s.role||state.user.role)&&row.rule.allowed_store_ids.includes(s.id));
 const datasets=await Promise.all(stores.map(async s=>({store:s,...await api('/api/retail-group/rule-items/'+s.id)})));
 const mode='<label>部分退回规则<select name="partial_return_mode" required><option value="">请明确选择</option><option value="accumulate_original_unit">按原整数单位累计恢复，零头不可消费</option></select></label><label>恢复有效期<select name="expiry_mode" required><option value="">请明确选择</option><option value="original_expiry">保留原有效期，不自动延期</option></select></label><label>待恢复负债<select name="pending_claim_expiry" required><option value="">请明确选择</option><option value="none">不自动清零，继续按原批次追溯</option></select></label>';
 let index=0,scopes=[];const items=datasets.map(d=>`<div class="card"><strong>${E(d.store.name)}</strong>${d.items.map(i=>{const n=index++;scopes.push({store_id:d.store.id,item_id:i.id,component:'goods',work_item_id:null});return `<label class="checklabel"><input type="checkbox" name="scope_${n}">${E(i.sku+' · '+i.name)} · 商品</label>`;}).join('')}${d.items.map(i=>{const n=index++;scopes.push({store_id:d.store.id,item_id:i.id,component:'installation',work_item_id:null});return `<label>${E(i.name)} 的安装用途<select name="install_${n}"><option value="">不包含安装</option>${d.works.map(w=>`<option value="${w.id}">${E(w.code+' · '+w.name)}</option>`).join('')}</select></label>`;}).join('')}</div>`).join('');
 const files=(state.row.files||[]).filter(f=>!f.generated&&f.security?.can_use);if(!files.length)throw new Error('本单尚无可用的公司规则来源原件，请补充并完成检查。');
 modal('明确商品范围与原退约定',`<form>${mode}${items}<label>本次核对的来源原件<select name="evidence" required><option value="">请选择</option>${files.map(f=>`<option value="${f.id}">${E(f.name)}</option>`).join('')}</select></label><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','返回')}<button type="submit" class="primary">提交给另一主管批准</button></div></form>`,async form=>{const selected=[];scopes.forEach((s,i)=>{if(s.component==='goods'&&form.elements['scope_'+i]?.checked)selected.push(s);if(s.component==='installation'&&form.elements['install_'+i]?.value)selected.push({...s,work_item_id:Number(form.elements['install_'+i].value)});});if(!selected.length)throw new Error('请明确选择实际适用的商品或安装项目。');const values={scopes:selected,evidence_id:Number(form.elements.evidence.value)};for(const key of ['partial_return_mode','expiry_mode','pending_claim_expiry'])values[key]=form.elements[key].value;await api(`/api/retail-group/rules/${row.id}/actions/submit`,{method:'POST',body:{request_id,version:row.version,values}});closeModal();await render();});
}
document.addEventListener('click',async event=>{const el=event.target.closest('[data-act]');if(!el?.dataset.act.startsWith('rg-'))return;try{if(el.dataset.act==='rg-authorize')await rgAuthorize();else if(el.dataset.act==='rg-action')await rgAction(el.dataset.key,Number(el.dataset.id));else if(el.dataset.act==='rg-reassign')await rgReassign(el.dataset.key);else if(el.dataset.act==='rg-rule-new')await rgRuleNew();else if(el.dataset.act==='rg-rule-action')await rgRuleAction(el.dataset.key);}catch(error){toast(error.message,true);}});
