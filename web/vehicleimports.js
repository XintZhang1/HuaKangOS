'use strict';
let vehicleImportUI={};
function clearVehicleImportsSession(){vehicleImportUI={};}
function viContext(){const key=String(state.user?.id)+':'+state.store;if(vehicleImportUI.key!==key)vehicleImportUI={key};return vehicleImportUI;}
const viLabels={trial:'试执行并回滚',review:'主管复核清单',confirm:'确认本人实际办理',cancel:'取消未执行批次',reassign:'转交复核待办'};
const viFieldLabels={source_row:'来源行编号',line_id:'采购车型行',vin:'VIN',amount_cents:'请款额（元）',manifest_row_id:'原请款清单行',shipped_date:'实际发运日期',expected_date:'预计到货日期',received_date:'实际验收日期',location_id:'实际库位编号'};
async function vehicleImportsPage(id){
 const c=viContext(),catalog=await api('/api/vehicle-imports/catalog');
 if(!catalog.can_read)return heading('车辆清单导入')+'<div class="notice">请选择获权的具体门店。</div>';
 const [order,batches,manifest]=await Promise.all([api('/api/vehicle-procurement/orders/'+id),api(`/api/vehicle-imports/orders/${id}/batches`),api(`/api/vehicle-imports/orders/${id}/manifest`)]);
 c.order=order;c.catalog=catalog;c.manifest=manifest.items;
 return heading('车辆请款与批量交接',E(order.number))+panel('原单与责任',`<p>每份清单只对应本采购单。预检和试执行不办理业务；另一主管复核后，由编制人确认自己的实际动作。请款不会付款，发运不会自动验收入库。</p><div class="row">${b('open','原采购单与实际付款',`data-route="vehicle-procurement/${order.id}"`)}${catalog.prepare_kinds.map(k=>b('vi-new','导入'+catalog.kinds[k],`data-kind="${k}"`)).join('')}</div>`)
 +panel('本单车型行',table(order.totals?['采购行编号','车型／颜色','计划台数','冻结单车成本（元）']:['采购行编号','车型／颜色','计划台数'],order.lines.map(l=>{const r=[l.id,E(l.model_name+' / '+l.color),l.quantity];if(order.totals)r.push(money(l.unit_cost_cents));return r;})))
 +panel('已确认请款车辆清单',manifest.items.map(r=>`<div class="panelbody">${facts({'清单行编号':r.id,'采购车型行':r.line_id})}<p>VIN：${E(r.vin)}</p></div>`).join('')+`<p>发运与到货 CSV 使用“清单行编号”。这里的清单只表示请款关联，不代表付款、发运或入库完成。</p>`)
 +panel('本单导入批次',table(['批次／来源编号','类别','进度',''],batches.items.map(r=>[`${r.id} / ${E(r.source_reference)}`,E(r.kind_label),E(r.status_label),b('open','核对办理',`data-route="vehicle-import/${r.id}"`)])));
}
async function vehicleImportPage(id){
 const c=viContext(),row=await api('/api/vehicle-imports/batches/'+id);c.batch=row;state.row=await api('/api/flow/cases/'+row.case_id);
 const summary={'原采购单':row.case_number,'来源编号':row.source_reference,'清单类别':row.kind_label,'进度':row.status_label,'车辆行数':row.row_count};if(row.amount_cents!==undefined)summary['请款合计（元）']=row.status==='invalid'?'待修正原资料':money(row.amount_cents);
 let html=heading('车辆导入批次 '+row.id)+panel('核对摘要',facts(summary)+`<p>${row.status==='confirmed'?'原单动作已完成。实际付款或退回继续在原采购单分别办理。':'整批校验，整批办理；任一行不满足原单条件，全部不执行。'}${row.case_version!==row.source_case_version&&row.status!=='confirmed'?' 原采购单已有后续变化，请取消并准备有替代关联的新清单。':''}</p><div class="row">${row.actions.map(k=>b('vi-action',viLabels[k],`data-key="${k}"`)).join('')}${b('open','返回本单清单',`data-route="vehicle-imports/${row.case_id}"`)}${b('open','原采购单与实际付款',`data-route="vehicle-procurement/${row.case_id}"`)}</div>`);
 if(row.status==='cancelled'&&((await api('/api/vehicle-imports/catalog')).prepare_kinds||[]).includes(row.kind))html+=panel('纠正来源',b('vi-replace','关联本批次重新准备')+'<p>仅未执行批次可以关联替代；新资料重新预检、试执行和复核。</p>');
 if(row.errors.length)html+=panel('逐行错误',table(['CSV 行号','需要修正'],row.errors.map(e=>[e.row_number,E(e.errors.join('；'))])));
 html+=panel('冻结逐行资料',row.rows.map(r=>`<div class="panelbody"><strong>CSV 第 ${r.row_number} 行 · 清单行编号 ${r.id}</strong>${r.values.vin?`<p>VIN：${E(r.values.vin)}</p>`:''}${facts(Object.fromEntries(Object.entries(r.values).filter(([k])=>k!=='vin').map(([k,v])=>[viFieldLabels[k]||k,k==='amount_cents'?money(v):v])))}${r.errors.length?`<p class="notice">${E(r.errors.join('；'))}</p>`:''}${r.result?`<p>原单结果：${Object.entries(r.result).map(([k,v])=>E({funds_request_id:'请款',shipment_id:'发运',receipt_id:'实际验收'}[k]+' #'+v)).join('，')}</p>`:''}</div>`).join(''));
 html+=panel('原始来源文件',fileList([row.file]))+panel('内部核验待办',table(['责任事项','经办人编号','期限'],row.tasks.map(t=>[E(t.title),t.assignee_id,E(t.due_date)+(t.overdue?' · 已逾期，请主管交接':'')]))+'<p>提醒仅在系统内部显示，不发送外部消息。</p>');return html;
}
async function viNew(kind,replacement=null){
 const c=viContext(),session=c.key,order=await api('/api/vehicle-procurement/orders/'+(c.order?.id||c.batch.case_id)),key=requestKey();
 modal('导入'+({funds:'车辆请款清单',ship:'车辆发运清单',receive:'车辆到货清单'}[kind]),`<form><p>使用 UTF-8 CSV，最多 200 行、128 KiB。表头固定，金额单位为分。请保留真实来源文件；导入会将源文件和批次一并留档。</p><div class="row">${b('vi-example','下载本类别虚构示例',`data-kind="${kind}" data-case="${order.id}"`)}</div><label>供应方或内部来源清单编号<input name="source_reference" required maxlength="100"></label><label>原始 CSV 文件<input name="file" type="file" accept=".csv,text/csv" required></label>${replacement?`<p>替代已取消批次 ${replacement.id}；历史来源保留。</p>`:''}<div class="formerror" role="alert"></div><div class="modalfoot">${b('close','返回核对')}<button type="submit" class="primary">上传并逐行预检</button></div></form>`,async form=>{
  if(viContext().key!==session)throw new Error('门店或账号已变化，请重新核对。');const fd=new FormData(form),file=fd.get('file');if(file.size>131072)throw new Error('CSV 不得超过 128 KiB（131072 字节）。');fd.append('kind',kind);fd.append('request_id',key);fd.append('version',order.version);if(replacement)fd.append('replacement_batch_id',replacement.id);
  const r=await api(`/api/vehicle-imports/orders/${order.id}/batches`,{method:'POST',body:fd});closeModal();go('vehicle-import/'+r.id);
 });
}
async function viAction(action){
 const c=viContext(),row=c.batch,session=c.key,key=requestKey();if(!row)throw new Error('请刷新批次。');let html='';
 if(action==='trial')html='<p>使用同一采购校验实际试执行后全部回滚，不产生请款、发运、车辆库存或现金事实。</p>';
 if(action==='review')html='<p>复核来源文件、原采购车型行、VIN 和逐行结果。复核不代替编制人确认实物动作。</p>';
 if(action==='confirm')html=`<p>${row.kind==='funds'?'本次只建立请款，实际付款由财务另行登记。':row.kind==='ship'?'本人已核对供应方逐 VIN 实际发运，本次仅登记发运在途。':'本人已核对现场 VIN 和真实库位，本次按原冻结成本逐车验收入库。'}</p><label class="check"><input name="confirmed" type="checkbox" required>我确认这是本人核对的本次实际办理</label>`;
 if(action==='cancel')html='<p>取消整个未执行批次，释放清单占用并保留来源；已执行的原单事实不会被删除。</p>';
 if(action==='reassign'){const employees=(await api('/api/flow/lookup/employee')).items;html=`<label>核验待办<select name="task_id">${row.tasks.map(t=>`<option value="${t.id}">${E(t.title)}</option>`).join('')}</select></label><label>接手主管<select name="assignee_id">${employees.map(u=>`<option value="${u.id}">${E(u.label)}</option>`).join('')}</select></label><p>仅主管复核可转交另一主管；更换实际编制人须取消并重新核对替代资料。</p>`;}
 modal(viLabels[action],`<form>${html}<label>本人核对依据与说明<textarea name="reason" required minlength="3" maxlength="500"></textarea></label><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','返回核对')}<button type="submit" class="primary">确认本人办理</button></div></form>`,async form=>{
  if(viContext().key!==session)throw new Error('门店或账号已变化，请重新核对。');const values={reason:form.elements.reason.value};if(action==='confirm')values.confirmed=form.elements.confirmed.checked;if(action==='reassign'){values.task_id=Number(form.elements.task_id.value);values.assignee_id=Number(form.elements.assignee_id.value);}
  await api(`/api/vehicle-imports/batches/${row.id}/actions/${action}`,{method:'POST',body:{request_id:key,version:row.version,source_case_version:row.case_version,values}});closeModal();await render();
 });
}
document.addEventListener('click',async event=>{const el=event.target.closest('[data-act]');if(!el?.dataset.act.startsWith('vi-'))return;try{if(el.dataset.act==='vi-new')await viNew(el.dataset.kind);if(el.dataset.act==='vi-replace')await viNew(viContext().batch.kind,viContext().batch);if(el.dataset.act==='vi-action')await viAction(el.dataset.key);if(el.dataset.act==='vi-example'){const r=await fetch(`/api/vehicle-imports/orders/${el.dataset.case}/example/${el.dataset.kind}`,{headers:{'X-Store-ID':String(state.store)}});if(!r.ok)throw new Error('当前岗位不能下载该示例。');const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download='huakangos-'+el.dataset.kind+'-example.csv';a.click();URL.revokeObjectURL(url);}}catch(error){toast(error.message,true);}});
