'use strict';
const voLabels={approve:'批准作业',reject_request:'拒绝申请',cancel:'取消未执行作业',locate:'核对实车登记库位',dispatch:'核对实车实际发出',accept:'目的库位实际接收',reject:'目的库位拒收',return_receive:'原库位实际接回',receive:'原车实际退回入库',intake:'实车接收至隔离位',inspect:'登记本次检查结果',disposition:'主管判定后续处理',release:'合格实车转入可售库存',return_customer:'实车交还客户',reassign:'转交当前待办'};
const voKinds={locate:'现场库位登记',local_move:'整车店内移库',other_out:'整车其他出库',other_return:'其他出库原车退回',customer_return:'客户退车隔离验收'};
const voEntryNames={locate:'现场定位',local_dispatch:'移库发出',local_reject:'目的库位拒收',local_accept:'目的库位接收',local_return:'原库位退回',other_out:'其他实际出库',other_return:'原车退回新代次入库',customer_return:'客户退车合格新代次入库'};
function clearVehicleOperationsSession(){state.vehicleOperation=null;state.voSession=null;}
function voContext(){return `${state.user?.id}:${state.store}`;}
function voOptions(rows,label){return rows.map(r=>`<option value="${r.id}">${E(label(r))}</option>`).join('');}
async function voLocations(){const [locs,warehouses]=await Promise.all([procurementAll('/api/masters/locations?active=true'),procurementAll('/api/masters/warehouses?active=true')]);const allowed=warehouses.filter(w=>['vehicles','mixed'].includes(w.warehouse_type));return locs.filter(l=>allowed.some(w=>w.id===l.warehouse_id)).map(l=>({...l,label:allowed.find(w=>w.id===l.warehouse_id).name+' / '+l.name}));}
async function vehicleOperationsPage(){
 const catalog=await api('/api/vehicle-operations/catalog');if(!catalog.can_read)return empty('请先选择获权门店','整车作业依照本店岗位与实车凭据办理。');
 const d=await api('/api/vehicle-operations/orders?page='+state.page);
 return heading('整车库位与出退库','核对实车、明确库位；移库与原车退回分别留据。',catalog.can_create?b('vo-new','建立车辆作业','','primary'):'')+storeNotice()+panel('本店车辆作业',table(['单号／车辆','作业','状态',''],d.items.map(r=>[`${E(r.number)}<br>${E(r.vin)}<br>${E(r.model)}`,E(r.kind_label),E(r.status_label),b('open','办理',`data-route="vehicle-operation/${r.id}"`)])))+pager(d.total)+panel('使用范围','<p>其他出库用于经批准退出可售库存的实际处置、内部转用等。临时借车和试驾不通过该入口。旧地址没有明确库位时，须先现场定位。</p><p>客户退车从原销售售后方案进入；收车先隔离，经检查、主管判定和实车放行后建立新的库存代次。</p>');
}
async function vehicleOperationPage(id){
 const row=await api('/api/vehicle-operations/orders/'+id);state.vehicleOperation=row;state.voSession=voContext();state.row=await api('/api/flow/cases/'+id);
 let html=heading(row.kind_label,row.number,b('open','返回车辆作业','data-route="vehicle-operations"'))+storeNotice();
 html+=panel('原车与实际安排',`<div class="formgrid"><div>VIN<p><strong>${E(row.vin)}</strong></p></div><div>状态<p><strong>${E(row.status_label)}</strong></p></div><div>原库存代次<p>${row.source_generation} · 库存记录 ${row.source_vehicle_id}</p></div><div>来源库位<p>${E(row.source_location)}</p></div><div>目的库位<p>${E(row.destination_location)}</p></div><div>办理期限<p>${E(row.due_date)}</p></div></div><p>${E(row.reason)}</p>${row.recipient?`<p>实际去向：${E(row.recipient)}</p>`:''}${row.cost_cents!==undefined?`<p>原车成本：<strong>${money(row.cost_cents)} 元</strong></p>`:''}${row.received_vehicle_id?`<p>已生成新库存记录：<strong>${row.received_vehicle_id}</strong>，原记录及历史交付保留。</p>`:''}${row.aftercare_case_id?b('open','查看原售后方案',`data-route="aftercare/${row.aftercare_case_id}"`):''}`);
 if(row.kind==='customer_return'){const last=row.inspections.at(-1);html+=panel('隔离检查关口',`<p><strong>${row.status==='accepted'?'检查、主管批准与实车入库已完成':row.status==='returned_to_customer'?'拒收车辆已实际交还，未增加可售库存':last?(last.outcome==='pass'?'最近一次检查合格，待主管判定或库管实车入库':'最近一次检查不合格，禁止放行'):'尚未完成检查；实际收车不会增加可售库存'}</strong></p><p>授权、实际收车、检查与放行分别由经办岗位记录。售后退款从原方案办理。</p>`);}
 html+=panel('当前办理',row.actions.length?`<div class="row">${row.actions.map(k=>b('vo-action',voLabels[k],`data-key="${k}"`)).join('')}</div>`:'<p>本岗位当前没有待办理动作。</p>');
 html+=panel('不可覆盖的实物与库位记录',table(row.cost_cents!==undefined?['事实','库位','库位台数变动','门店库存台数变动','原成本变动（元）']:['事实','库位','库位台数变动','门店库存台数变动'],row.entries.map(e=>{const a=[E(voEntryNames[e.kind]||e.kind),E(e.location),e.quantity,e.inventory_delta];if(row.cost_cents!==undefined)a.push(money(e.value_cents));return a;})));
 if(row.kind==='customer_return'){
  html+=panel('隔离实车交接',table(['交接','隔离位置','说明'],row.quarantine.map(q=>[E({intake:'实际接收隔离',release:'实际解除隔离入库',return_to_customer:'实际交还客户'}[q.kind]),E(q.location),E(q.reason)])));
  html+=panel('历次检查',table(['检查编号','结果','实际发现'],row.inspections.map(i=>[i.id,i.outcome==='pass'?'合格':'不合格',E(i.findings)])));
 }
 html+=panel('主管复核记录',table(['判定','检查依据','说明'],row.reviews.map(r=>[E({approve:'批准作业',reject:'拒绝申请',release:'同意合格入库',rectify:'要求整改复检',return_to_customer:'拒收并实际交还'}[r.decision]),r.inspection_id||'作业申请',E(r.reason)])));
 html+=panel('本单文件',b('upload','上传本次交接、检查或批准凭据')+(state.row.files||[]).map(f=>`<div class="filerecord"><div class="filetext"><strong>${E(f.name)}</strong><p>${E(f.security?.label||'等待检查')}</p>${f.security?.can_use?b('download','下载',`data-id="${f.id}"`):''}</div></div>`).join(''));
 html+=panel('岗位待办与交接',table(['责任事项','经办人','期限'],(state.row.tasks||[]).filter(t=>t.status==='open').map(t=>[E(t.title),E(t.assignee_name),E(t.due_date)]))+b('open','查看原单与交接记录',`data-route="case/${id}"`));return html;
}
async function voNew(){
 const [vehicles,locs,orders]=await Promise.all([api('/api/vehicle-operations/vehicles'),voLocations(),procurementAll('/api/vehicle-operations/orders')]);
 const key=requestKey(),returns=orders.filter(r=>r.kind==='other_out'&&r.status==='completed');
 modal('建立车辆作业',`<form><label>作业类型<select name="kind"><option value="local_move">整车店内移库</option><option value="locate">现场库位登记</option><option value="other_out">整车其他出库</option><option value="other_return">其他出库原车退回</option></select></label><label data-vo-vehicle>本店车辆<select name="vehicle_id">${voOptions(vehicles.items,r=>r.vin+' · '+r.model+' · '+r.location)}</select></label><label data-vo-original hidden>原其他出库单<select name="original_operation_id">${voOptions(returns,r=>r.number+' · '+r.vin)}</select></label><label data-vo-location>明确目的库位<select name="location_id">${voOptions(locs,r=>r.label)}</select></label><label data-vo-recipient hidden>实际接收方或处置去向<input name="recipient" maxlength="180"></label><label>安排依据与原因<textarea name="reason" required minlength="2" maxlength="500"></textarea></label><label>办理期限<input name="due_date" type="date" value="${day()}" required></label><p>申请并不移动实车；批准后由库管核对VIN并记录实际动作。</p><div class="formerror" role="alert"></div><div class="modalfoot"><button class="primary" type="submit">提交主管复核</button></div></form>`,async form=>{
  const f=form.elements,kind=f.kind.value,v={request_id:key,kind,reason:f.reason.value,due_date:f.due_date.value};
  if(kind==='other_return')v.original_operation_id=Number(f.original_operation_id.value);else v.vehicle_id=Number(f.vehicle_id.value);
  if(kind==='other_out')v.recipient=f.recipient.value;else v.location_id=Number(f.location_id.value);
  const row=await api('/api/vehicle-operations/orders',{method:'POST',body:v});closeModal();go('vehicle-operation/'+row.id);
 });
}
async function voAction(action){
 const row=state.vehicleOperation;if(!row||state.voSession!==voContext())throw new Error('门店或账号已变化，请重新打开车辆作业。');
 const key=requestKey(),files=(state.row.files||[]).filter(f=>!f.generated&&f.security?.can_use),needFile=!['cancel','reassign'].includes(action),physical=['locate','dispatch','accept','reject','return_receive','receive','intake','release','return_customer'].includes(action);
 if(needFile&&!files.length)throw new Error('请先上传本单实际凭据并完成附件检查。');
 let html=physical?`<p>本单原车：<strong>${E(row.vin)}</strong></p><label>对照实车重新输入 VIN<input name="vin" minlength="17" maxlength="17" required placeholder="请核对实车，不自动填入"></label>`:'';
 if(['intake','release'].includes(action)){const locs=await voLocations();html+=`<label>${action==='intake'?'实际隔离库位':'合格实车入库库位'}<select name="location_id">${voOptions(locs,l=>l.label)}</select></label>`;}
 if(action==='inspect')html+='<label>本次实际检查结果<select name="outcome"><option value="fail">不合格</option><option value="pass">合格</option></select></label><label>实际发现及整改复检结果<textarea name="findings" required minlength="2" maxlength="1000"></textarea></label>';
 if(action==='disposition'){const last=row.inspections.at(-1);html+=`<p>最近检查 #${last.id}：<strong>${last.outcome==='pass'?'合格':'不合格，不能放行'}</strong></p><label>主管判定<select name="decision"><option value="rectify">整改后重新检查</option>${last.outcome==='pass'?'<option value="release">合格，安排实车入库</option>':''}<option value="return_to_customer">拒收，安排实际交还</option></select></label>`;}
 if(action==='reassign'){const users=await api('/api/flow/lookup/user');html+=`<label>本单当前待办<select name="task_id">${voOptions(row.tasks,t=>t.title)}</select></label><label>接手员工<select name="assignee_id">${voOptions(users.items,u=>u.label||u.name||u.display_name)}</select></label><label>新的办理期限<input name="due_date" type="date" required value="${day()}"></label>`;}
 html+='<label>本人核对的依据与说明<textarea name="reason" required minlength="2" maxlength="500"></textarea></label>';
 if(needFile)html+=`<label>本单本次实际凭据<select name="evidence_id">${voOptions(files,f=>f.name)}</select></label>`;
 modal(voLabels[action],`<form>${html}<div class="formerror" role="alert"></div><div class="modalfoot"><button type="submit" class="primary">确认本人办理</button></div></form>`,async form=>{
  const f=form.elements,v={reason:f.reason.value};if(needFile)v.evidence_id=Number(f.evidence_id.value);if(physical)v.vin=f.vin.value;
  if(['intake','release'].includes(action))v.location_id=Number(f.location_id.value);
  if(action==='inspect'){v.outcome=f.outcome.value;v.findings=f.findings.value;}
  if(action==='disposition'){v.decision=f.decision.value;v.inspection_id=row.inspections.at(-1).id;}
  if(action==='reassign'){v.task_id=Number(f.task_id.value);v.assignee_id=Number(f.assignee_id.value);v.due_date=f.due_date.value;}
  await api(`/api/vehicle-operations/orders/${row.id}/actions/${action}`,{method:'POST',body:{request_id:key,version:row.version,values:v}});closeModal();await render();
 });
}
document.addEventListener('change',event=>{if(event.target.name!=='kind'||!event.target.closest('form')?.querySelector('[data-vo-vehicle]'))return;const f=event.target.closest('form'),kind=event.target.value;f.querySelector('[data-vo-vehicle]').hidden=kind==='other_return';f.querySelector('[data-vo-original]').hidden=kind!=='other_return';f.querySelector('[data-vo-location]').hidden=kind==='other_out';f.querySelector('[data-vo-recipient]').hidden=kind!=='other_out';});
document.addEventListener('click',async event=>{const el=event.target.closest('[data-act]');if(!el?.dataset.act.startsWith('vo-'))return;try{if(el.dataset.act==='vo-new')await voNew();if(el.dataset.act==='vo-action')await voAction(el.dataset.key);}catch(error){toast(error.message,true);}});
