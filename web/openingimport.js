'use strict';
let openingImportUI={};
function clearOpeningImportSession(){openingImportUI={};}
function openingImportContext(){const key=String(state.user?.id)+':'+state.store;if(openingImportUI.key!==key)openingImportUI={key};return openingImportUI;}
const oiLabels={trial:'试导入并回滚',approve:'主管批准资料',verify_inventory:'核对实物',verify_finance:'核对金额',confirm:'确认启用',cancel:'取消未启用批次',reassign:'转交核验待办'};
const oiTotals={...openingLabels,vehicle_count:'车辆台数',vehicle_value_cents:'车辆原成本（元）',account_balance_cents:'账户期初余额（元）'};
function oiTotalHTML(t){return facts(Object.fromEntries(Object.entries(t).map(([k,v])=>[oiTotals[k]||k,k.endsWith('_cents')?money(v):v])));}
async function openingImportPage(){
 const c=openingImportContext(),catalog=await api('/api/opening-import/catalog');
 if(!catalog.can_read)return heading('正式期初核验')+'<div class="notice">请选择门店</div>';
 const data=await api('/api/opening-import/batches');
 const mapping=catalog.can_prepare?await api('/api/opening-import/example'):null;
 const accountGuide=mapping?.policy_enabled?panel('期初账户与批准配置',`<div class="notice">${E(mapping.notice)}</div>`+table(['明确账户编号 account_id','资料名称 name','类型 account_type'],mapping.approved_accounts.map(a=>[E(a.account_id),E(a.name),E(a.account_type)]))+b('open','查看本店主体与账户配置','data-route="business-entities"')):'';
 const editor=catalog.can_prepare?panel('准备核对后的原资料',`<p>仅用于本店客户、库存及真实业务为空的正式新库；启用主体策略后允许预配置的已批准账户。期初现金是已有余额，不会生成本期收款；车辆须为有来源、已经在店的可售库存。</p><div class="row"><label>选择 JSON 文件<input id="oi-file" type="file" accept="application/json,.json"></label>${b('oi-example','载入虚构示例')}</div><label>原始 JSON 资料<textarea id="oi-source" rows="12" maxlength="120000">${E(c.source||'')}</textarea></label><p>金额单位为整数分，物资数量为整数千分之一；不接受未定义的未结旧单、应收应付或预收字段。</p>${b('oi-preflight','逐行预检','','primary')}`):'';
 const errors=c.errors?.length?panel('逐行检查结果',c.errors.map(e=>`<div class="notice warn"><strong>${E({vehicles:'车辆',accounts:'账户',items:'物资',customers:'客户',target:'目标门店',source:'原资料'}[e.section]||e.section)} ${e.row?'第 '+e.row+' 行':'整体'}</strong><p>${E(e.message)}</p></div>`).join('')):'';
 return heading('正式期初核验','预检 → 回滚试导入 → 主管批准 → 分岗核验 → 一次启用',catalog.can_balances?b('open','账户余额核对','data-route="opening-balances"'):'')+accountGuide+editor+errors+panel('本店期初批次',table(['批次','来源','基准日','状态','办理'],data.items.map(r=>[E(r.number),E(r.source_reference),E(r.opening_date),E(r.status_label),b('open','打开',`data-route="opening-batch/${r.case_id}"`)])));
}
async function openingBatchPage(id){
 const c=openingImportContext(),row=await api('/api/opening-import/batches/'+id);c.row=row;state.row=await api('/api/flow/cases/'+id);
 let html=heading('期初资料核验 · '+row.status_label,'各岗位只确认本人核对的事项；试导入和批准不会创建可用库存或现金。',b('open','返回批次','data-route="opening-import"'));
 html+=panel('来源与核对汇总',facts({'批次':row.number,'来源':row.source_reference,'期初基准日':row.opening_date,'状态':row.status_label})+oiTotalHTML(row.totals)+`<details><summary>原资料摘要</summary><p class="wrap">${E(row.source_digest)}</p></details>`);
 if(row.status==='confirmed')html+='<div class="notice">期初已一次启用，原资料和分岗凭据已保留。后续资金使用实际收付款，车辆使用销售、移库或出退库流程，不能覆盖期初。</div>';
 html+=panel('车辆原资料',table(row.totals.vehicle_value_cents!==undefined?['VIN','车型编码','库位编码','原成本（元）']:['VIN','车型编码','库位编码'],row.vehicles.map(v=>[E(v.vin),E(v.model_code),E(v.location_code),...(v.cost_cents!==undefined?[money(v.cost_cents)]:[])])));
 html+=panel('物资原资料',table(row.totals.inventory_value_cents!==undefined?['编码','名称','数量','原价值（元）']:['编码','名称','数量'],row.items.map(i=>[E(i.sku),E(i.name),E((i.quantity_milli/1000)+' '+i.unit),...(i.value_cents!==undefined?[money(i.value_cents)]:[])])));
 if(row.accounts.length)html+=panel('账户期初核对',table(['账户','日初余额（元）','来源'],row.accounts.map(a=>[E(a.name),money(a.opening_balance_cents),E(a.source_reference)])));
 html+=actionPanel(row.actions.length?`<div class="row">${row.actions.map(a=>b('oi-action',oiLabels[a],`data-key="${a}"`)).join('')}</div>`:'本批次当前没有可办理动作。');
 html+=panel('分岗核验凭据',table(['核验事项','经办人','时间','说明'],row.proofs.map(p=>[E({approve:'主管复核',inventory:'实物核验',finance:'财务核验'}[p.kind]),E(p.actor_name),E(time(p.occurred_at)),E(p.reason)])));
 html+=panel('本单核验文件',b('upload','上传本人核验凭据')+fileList(state.row.files||[]));
 html+=panel('岗位责任与期限',table(['待办','负责人','期限'],(state.row.tasks||[]).filter(t=>t.status==='open').map(t=>[E(t.title),E(t.assignee_name),E(t.due_date)])));
 return html;
}
async function openingBalancesPage(){const info=await api('/api/opening-import/account-balances');return heading('期初与实际账户余额','期初余额和之后的实际收付款分别列示。',b('oi-export','导出核对明细'))+`<div class="notice">${E(info.basis)}</div>`+(info.items.length?info.items.map(r=>panel(r.account_name,facts({'期初基准日':r.opening_date,'期初余额（元）':money(r.opening_cents),'实际收入（元）':money(r.in_cents),'实际支出（元）':money(r.out_cents),'当前余额（元）':money(r.balance_cents),'资料检查':r.pre_opening_cash_count?'存在早于期初流水，须核对':'无早于期初流水'}))).join(''):empty('尚无期初账户余额','完成本店正式期初核验后显示。'));}
async function oiAction(action){
 const c=openingImportContext(),row=c.row,key=requestKey(),session=c.key;if(!row)throw new Error('请重新打开本店期初批次。');
 const needsFile=['trial','approve','verify_inventory','verify_finance'].includes(action),category=action==='verify_finance'?'receipt':'evidence';
 const files=(state.row.files||[]).filter(f=>!f.generated&&f.security?.can_use&&f.category===category&&row.own_file_ids.includes(f.id));
 if(needsFile&&!files.length)throw new Error('请先上传本人本次'+(category==='receipt'?'收付款凭据类型的财务核对表':'业务凭据类型的核验资料')+'并通过文件检查。');
 let html=action==='trial'?'<div class="notice">试导入将实际检查全批资料和关联约束，然后回滚所有客户、账户、库存及 VIN 保管记录。</div>':action==='confirm'?`<div class="notice warn">核验通过后一次启用本店期初。不能再次覆盖导入。</div>${oiTotalHTML(row.totals)}<label class="checklabel"><input type="checkbox" name="confirmed" required>已核对原资料摘要、各岗凭据及汇总</label>`:'';
 if(action==='verify_inventory'){
  html+='<div class="notice">对照当前实车和物资实盘清单输入。数量或 VIN 不一致时应取消批次重新核对，不会按差额自动调整。</div>';
  row.vehicles.forEach((v,i)=>{html+=`<label>第 ${i+1} 台 VIN · ${E(v.vin)}<input name="vin_${i}" required minlength="17" maxlength="17" placeholder="对照实车重新输入"></label><label>实车库位编码<input name="loc_${i}" required placeholder="资料库位 ${E(v.location_code)}"></label>`;});
  row.items.filter(i=>i.quantity_milli).forEach((v,i)=>{html+=`<label>${E(v.sku+' '+v.name)} 实盘数量（${E(v.unit)}）<input name="qty_${i}" inputmode="decimal" required placeholder="如 2.5"></label>`;});
 }
 if(action==='verify_finance'){
  html+=oiTotalHTML(row.totals)+'<p>分别核对每个账户，账户之间不能用一增一减互相抵销。</p>';
  row.accounts.forEach((a,i)=>{html+=`<label>${E(a.name)} 核对日初余额（元）<input name="balance_${i}" inputmode="decimal" required></label>`;});
  html+='<label>核对物资价值合计（元）<input name="material_value" inputmode="decimal" required></label><label>核对车辆原成本合计（元）<input name="vehicle_value" inputmode="decimal" required></label>';
 }
 if(action==='reassign'){const users=await api('/api/flow/lookup/employee');html+=`<label>当前核验待办<select name="task_id">${row.tasks.map(t=>`<option value="${t.id}">${E(t.title)}</option>`).join('')}</select></label><label>接手员工<select name="assignee_id">${users.items.map(u=>`<option value="${u.id}">${E(u.label)}</option>`).join('')}</select></label>`;}
 html+='<label>本人核对依据与说明<textarea name="reason" required minlength="3" maxlength="500"></textarea></label>';
 if(needsFile)html+=`<label>本人本单核验凭据<select name="evidence_id">${files.map(f=>`<option value="${f.id}">${E(f.name)}</option>`).join('')}</select></label>`;
 modal(oiLabels[action],`<form>${html}<div class="formerror" role="alert"></div><div class="modalfoot">${b('close','返回核对')}<button type="submit" class="primary">确认本人办理</button></div></form>`,async form=>{
  if(openingImportContext().key!==session)throw new Error('门店或账号已改变，请重新核对。');
  const f=form.elements,v={reason:f.reason.value};if(needsFile)v.evidence_id=Number(f.evidence_id.value);
  if(action==='verify_inventory')v.observed={vehicles:row.vehicles.map((r,i)=>({vin:f['vin_'+i].value.trim().toUpperCase(),location_code:f['loc_'+i].value.trim()})),items:row.items.filter(i=>i.quantity_milli).map((r,i)=>{const s=f['qty_'+i].value.trim();if(!/^\d+(\.\d{1,3})?$/.test(s))throw new Error('数量最多三位小数。');const[a,d='']=s.split('.');const q=Number(a)*1000+Number(d.padEnd(3,'0'));if(!Number.isSafeInteger(q))throw new Error('数量超出范围。');return{sku:r.sku,quantity_milli:q};})};
  if(action==='verify_finance'){const accounts=row.accounts.map((r,i)=>({name:r.name,opening_balance_cents:masterFen(f['balance_'+i].value)}));v.observed={totals:{...row.totals,account_balance_cents:accounts.reduce((a,r)=>a+r.opening_balance_cents,0),inventory_value_cents:masterFen(f.material_value.value),vehicle_value_cents:masterFen(f.vehicle_value.value)},accounts};}
  if(action==='confirm'){v.expected_totals=row.totals;v.confirmed=f.confirmed.checked;}
  if(action==='reassign'){v.task_id=Number(f.task_id.value);v.assignee_id=Number(f.assignee_id.value);}
  await api(`/api/opening-import/batches/${row.case_id}/actions/${action}`,{method:'POST',body:{request_id:key,version:row.version,source_digest:row.source_digest,values:v}});closeModal();await render();
 });
}
document.addEventListener('change',async event=>{if(event.target.id!=='oi-file'||!event.target.files?.length)return;try{const c=openingImportContext(),file=event.target.files[0];if(file.size>120000)throw new Error('期初 JSON 超过120KB。');const source=await file.text();if(c!==openingImportContext())return;c.source=source;$('#oi-source').value=source;}catch(error){toast(error.message,true);}});
document.addEventListener('click',async event=>{const el=event.target.closest('[data-act]');if(!el?.dataset.act.startsWith('oi-'))return;try{const c=openingImportContext();if(el.dataset.act==='oi-example'){c.source=JSON.stringify((await api('/api/opening-import/example')).source,null,2);await render();}if(el.dataset.act==='oi-preflight'){c.source=$('#oi-source').value;const r=await api('/api/opening-import/preflight',{method:'POST',body:{request_id:requestKey(),source_text:c.source}});c.errors=r.errors;if(r.valid)go('opening-batch/'+r.batch.case_id);else await render();}if(el.dataset.act==='oi-action')await oiAction(el.dataset.key);if(el.dataset.act==='oi-export'){const response=await fetch('/api/opening-import/account-balances/export',{headers:{'X-Store-Id':String(state.store)}});if(!response.ok)throw new Error('当前岗位不能导出账户核对表。');const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download='huakangos-期初账户余额.csv';a.click();URL.revokeObjectURL(url);}}catch(error){toast(error.message,true);}});
