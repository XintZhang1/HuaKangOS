'use strict';
const whNames={activate:'真实库位启用',other_in:'其他物资入库',other_in_return:'原其他入库退回',consumable:'耗材领用',consumable_return:'原耗材领用退回',gift:'礼品发出',gift_return:'原礼品退回',disposal:'其他处置出库',local_move:'店内移库',count:'库位盘点'};
const whPurposes={addon_dispatch_v3:'销售加装实际领出',addon_return_v3:'销售加装原料拆回',purchase:'采购实际入库',issue:'原流程领料出库',return:'原流程退料入库',count:'原流程盘点差异',procurement_receipt:'采购实际验收入库',procurement_return:'采购原单退回',transfer_out:'跨店实际发出',transfer_in:'跨店实际接收',transfer_return:'跨店退回入库',repair_issue_v3:'维修领料出库',repair_return_v3:'维修原料退回',retail_dispatch:'精品销售出库',retail_return:'精品原单退货'};
function clearWarehouseSession(){state.warehouse=null;state.whSession=null;state.whAllocation=null;state.whLocationHtml=null;}
function whContext(){return `${state.user?.id}:${state.store}`;}
function whQty(n){return Number.isFinite(n)?String(n/1000):'—';}
function whOptions(rows,label){return rows.map(r=>`<option value="${r.id}">${E(label(r))}</option>`).join('');}
function whStatus(s){return E({pending:'待主管批准',ready:'待实际办理',counting:'现场实盘中',review:'待复核差异',transit:'店内在途',returning:'拒收待实际返回',completed:'已完成',cancelled:'已撤销',rejected:'已拒绝'}[s]||s);}
function whReason(s){return E({activation:'启用定位',average_revaluation:'门店均价价值分配',local_dispatch:'店内实际移出',local_accept:'店内实际接收',local_return:'店内实际返回',wh_other_in:'其他入库',wh_other_return:'原其他入库退回',wh_consumable:'耗材领用',wh_consume_return:'原耗材退回',wh_gift:'礼品出库',wh_gift_return:'原礼品退回',wh_disposal:'其他处置',wh_count:'盘点差异'}[s]||whPurposes[s]||s);}
async function warehousePage(){
 const catalog=await api('/api/warehouse/catalog');if(!catalog.can_read)return empty('请切换到获权门店','仓储作业由本店库管、主管、财务与审计按岗位处理。');
 const [cases,items]=await Promise.all([api('/api/warehouse/cases?page='+state.page+'&q='+encodeURIComponent(state.q)),api('/api/warehouse/items?page_size=50&q='+encodeURIComponent(state.q))]);
 let html=heading('库位与仓储作业','先核对实际库位，再办理实物收发；盘点观察与差异审批分别留据。')+storeNotice();
 if(catalog.can_create){const buttons=keys=>keys.map(op=>b('wh-new',whNames[op],`data-operation="${op}"`)).join('');html+=panel('本次要处理什么实物',workActionGroups([
  {title:'收到物资',hint:'采购到货请回采购原单；这里只登记其他来源。',html:buttons(['other_in'])+b('open','采购原单收货','data-route="procurement"')},
  {title:'领用或发出',hint:'维修领料、销售出库回各自原单；其他用途在这里选择。',html:buttons(['consumable','gift','disposal'])},
  {title:'退回原收发',hint:'先选原批次，再核对实际退回数量；不会自动记财务退款。',html:buttons(['other_in_return','consumable_return','gift_return'])},
  {title:'移库与盘点',html:buttons(['local_move','count'])},
  {title:'首次启用库位',hint:'已有正常库位账不需要反复启用。',html:buttons(['activate']),secondary:true}
 ]));}html+=workRecordSearch('作业单号、物资名称或编码');
 html+=panel('本店待办与作业',table(['作业／物资','数量','状态',''],cases.items.map(r=>[`${E(r.operation_label)}<br>${E(r.item_name)}`,whQty(r.quantity_milli),whStatus(r.state),b('open','办理',`data-route="warehouse/${r.id}"`)])))+pager(cases.total);
 html+=panel('物资库位启用与可用量',table(['物资','库位账','账面／可用',''],items.items.map(i=>[E(i.name),i.enabled?'已启用':'历史未定位',`${whQty(i.quantity_milli)} / ${whQty(i.available_milli)} ${E(i.unit)}`,b('open','查看库位',`data-route="warehouse-item/${i.id}"`)]))+(items.total>items.items.length?'<p>本页展示前50项；可在具体作业中选择完整物资目录。</p>':''));return html;
}
async function warehouseCasePage(id){
 const row=await api('/api/warehouse/cases/'+id);state.warehouse=row;state.whSession=whContext();state.row=await api('/api/flow/cases/'+id);
 const locs=await procurementAll('/api/masters/locations'),name=key=>locs.find(l=>l.id===key)?.name||'—';
 let html=heading(row.operation_label,row.number,b('open','返回仓储','data-route="warehouse"'))+storeNotice()+panel('原始作业',`<div class="formgrid"><div>物资<p>${E(row.item_name)}</p></div><div>数量<p>${row.operation==='count'?'逐库位现场清点':whQty(row.quantity_milli)+' '+E(row.unit)}</p></div><div>原库位<p>${E(name(row.source_location_id))}</p></div><div>接收库位<p>${E(name(row.destination_location_id))}</p></div><div>状态<p>${whStatus(row.state)}</p></div><div>办理期限<p>${E(row.due_date)}</p></div></div><p>${E(row.reason)}</p>${row.recipient?`<p>领取人／班组：${E(row.recipient)}</p>`:''}${row.original_move_id?`<p>原始收发记录：${row.original_move_id}</p>`:''}${row.approved_value_cents!==undefined?`<p>来源批准价值：${money(row.approved_value_cents)} 元</p>`:''}`);
 if(row.operation==='local_move')html+=panel('实物在途',`<p>尚在途 ${whQty(row.transit_quantity_milli)} ${E(row.unit)}。发出后须实际接收或原位接回；不改变门店总库存。</p>`);
 if(row.count){const c=row.count;html+=panel('实盘观察与期间收发','<div class="formgrid">'+[['开始账面',c.baseline_quantity_milli],['现场实盘',c.counted_quantity_milli],['原观察差额',c.difference_milli],['期间净收发',c.movement_bridge_milli],['当前账面',c.current_book_milli],['差额处理后应有',c.projected_milli]].map(([name,n])=>`<div>${E(name)}<p><strong>${whQty(n)}</strong> ${E(row.unit)}</p></div>`).join('')+'</div>'+'<p>差额以本次实盘观察为准；后续正常收发逐笔衔接。若差额影响既有预占，先按原业务解除或核对，不能自动挪用。</p>'+table(['期间流水','原单','数量','原因'],c.entries.map(e=>[e.id,b('open','查看原单',`data-route="case/${e.case_id}"`),whQty(e.quantity_milli),whReason(e.reason)])));}
 html+=panel('办理本步骤','<div class="row">'+row.actions.map(a=>b('wh-action',a.label,`data-key="${a.key}"`)).join('')+(canWrite()?b('upload','上传本单实际凭据'):'')+b('open','查看实际库位',`data-route="warehouse-item/${row.item_id}"`)+'</div>');
 html+=panel('本单实物收发',table(row.can_money?['日期／流水','数量','价值（元）','原收发','办理']:['日期／流水','数量','原收发','办理'],row.stock_moves.map(m=>{
  const cells=[E(m.business_date||'')+'<br>'+m.id,whQty(m.quantity_milli)];if(row.can_money)cells.push(money(m.value_cents));cells.push(m.original_id||'—');
  cells.push(m.can_return?b('wh-original-return','退回这批',`data-operation="${m.return_operation}" data-original="${m.id}"`)+`<p>可退 ${whQty(m.returnable_milli)} ${E(row.unit)}</p>`:'—');return cells;
 })));
 html+=panel('已有凭据',(state.row.files||[]).map(f=>`<div class="filerecord"><div class="filetext"><strong>${E(f.name)}</strong><p>${E(f.label)} · ${E(f.security?.label||'等待检查')}</p>${f.security?.can_use?b('download','下载',`data-id="${f.id}"`):'检查通过后可使用'}</div></div>`).join('')||'<p>先上传本单凭据；其他入库核价使用受限的合同或收款凭据类别。</p>');
 html+=panel('岗位责任与交接',table(['任务','经办人','期限','状态'],state.row.tasks.map(t=>[E(t.title),E(t.assignee_name),E(t.due_date),pill(t.status)])));return html;
}
async function warehouseItemPage(id){
 const s=await api('/api/warehouse/items/'+id+'/stock'),moneyAllowed=s.value_cents!==undefined;
 return heading('物资真实库位',s.name+' · '+s.sku,b('open','返回仓储','data-route="warehouse"'))+storeNotice()+panel('门店库存',`<p>${s.enabled?'真实库位账已启用':'尚未定位：先核对原始期初与收发账，再由员工明确分配位置。'}</p><p>账面 ${whQty(s.quantity_milli)}，当前可用 ${whQty(s.available_milli)}，预占／在途／盘点保留 ${whQty(s.reserved_milli)} ${E(s.unit)}</p>${moneyAllowed?`<p>门店库存价值 ${money(s.value_cents)} 元</p>`:''}`)+panel('库位及店内在途',table(moneyAllowed?['位置','数量','价值（元）']:['位置','数量'],s.balances.map(b=>moneyAllowed?[E(b.location_name),whQty(b.quantity_milli),money(b.value_cents)]:[E(b.location_name),whQty(b.quantity_milli)])))+panel('不可变库位流水',table(moneyAllowed?['日期／原因','数量','价值（元）','原单']:['日期／原因','数量','原单'],s.entries.map(e=>{const r=[`${E(e.business_date)}<br>${whReason(e.reason)}`,whQty(e.quantity_milli)];if(moneyAllowed)r.push(money(e.value_cents));r.push(b('open','查看原单',`data-route="case/${e.case_id}"`));return r;})));
}
function whLocationLines(locs,qty='0'){return `<div data-wh-location class="panelbody"><label>实际库位<select name="location">${whOptions(locs,l=>l.name)}</select></label><label>该库位数量<input name="location_qty" required inputmode="decimal" value="${E(qty)}"></label>${b('wh-remove-location','删除该分配')}</div>`;}
async function whNew(op){
 if(['other_in_return','consumable_return','gift_return'].includes(op))return whReturnNew(op);
 const [all,locs]=await Promise.all([procurementAll('/api/warehouse/items?page_size=100'),procurementAll('/api/masters/locations?active=true')]);
 const items=all.filter(i=>op==='activate'?!i.enabled:i.enabled);if(!items.length)throw new Error(op==='activate'?'没有尚未定位的物资，请先建物资目录。':'请先完成物资真实库位启用。');if(!locs.length)throw new Error('请先配置物资仓及实际库位。');
 const outs=['other_in_return','consumable','gift','disposal','local_move'],returns=['other_in_return','consumable_return','gift_return'];let html=`<label>物资<select name="item_id">${whOptions(items,i=>`${i.name} · 当前账面 ${whQty(i.quantity_milli)} ${i.unit}`)}</select></label>`;
 if(op!=='count')html+='<label>本次数量<input name="quantity" required inputmode="decimal" value="'+(op==='activate'?whQty(items[0].quantity_milli):'1')+'"></label>';
 if(outs.includes(op)||op==='count')html+=`<label>原实际库位<select name="source">${whOptions(locs,l=>l.name)}</select></label>`;
 if(!outs.includes(op)&&!['activate','count'].includes(op)||op==='local_move')html+=`<label>接收实际库位<select name="destination">${whOptions(locs,l=>l.name)}</select></label>`;
 if(returns.includes(op))html+='<label>原始收发流水编号<input name="original" type="number" min="1" required placeholder="从原仓储作业的实物收发表查看"></label>';
 if(['gift','consumable'].includes(op))html+='<label>实际领取人／班组<input name="recipient" required maxlength="120"></label>';
 if(op==='activate'){state.whLocationHtml=whLocationLines(locs);html+='<p>按实物填写每个库位。分配和必须等于已对平账面数量，不能根据默认库位猜历史位置。</p><div id="wh-locations">'+whLocationLines(locs,whQty(items[0].quantity_milli))+'</div>'+b('wh-add-location','增加实际库位');}
 html+='<label>来源与作业原因<textarea name="reason" required minlength="2" maxlength="500"></textarea></label><label>办理期限<input type="date" name="due_date" required value="'+day()+'"></label>';
 const request_id=requestKey();modal(whNames[op],`<form>${html}<div class="formerror" role="alert"></div><div class="modalfoot"><button type="submit" class="primary">提交主管</button></div></form>`,async form=>{
  const v={request_id,operation:op,item_id:Number(form.elements.item_id.value),quantity_milli:op==='count'?0:purchaseScaled(form.elements.quantity.value,3),reason:form.elements.reason.value,due_date:form.elements.due_date.value};
  if(form.elements.source)v.source_location_id=Number(form.elements.source.value);if(form.elements.destination)v.destination_location_id=Number(form.elements.destination.value);if(form.elements.original)v.original_move_id=Number(form.elements.original.value);if(form.elements.recipient)v.recipient=form.elements.recipient.value;
  if(op==='activate')v.locations=whReadLocations(form);const row=await api('/api/warehouse/cases',{method:'POST',body:v});closeModal();go('warehouse/'+row.id);
 });
}
function whReadLocations(form){return [...form.querySelectorAll('[data-wh-location]')].map(el=>({location_id:Number(el.querySelector('[name=location]').value),quantity_milli:purchaseScaled(el.querySelector('[name=location_qty]').value,3)}));}
async function whAction(key){
 const row=state.warehouse;if(!row||state.whSession!==whContext())throw new Error('门店或账号已变化，请重新打开作业。');
 const financial=key==='approve'&&row.operation==='other_in',needsFile=!['cancel','reject','assign'].includes(key),files=(state.row.files||[]).filter(f=>!f.generated&&f.security?.can_use&&(!financial||['receipt','invoice','signed_contract','procurement_contract'].includes(f.category)));
 if(needsFile&&!files.length)throw new Error(financial?'请先上传受限的来源合同或核价凭据，再批准总价值。':'请先上传本单实际凭据并通过检查。');
 let html='';if(financial)html+='<label>批准本次来源总价值（元）<input name="value" required inputmode="decimal"></label>';
 if(['accept','return_transit'].includes(key))html+=`<label>本次实际接收数量<input name="quantity" required inputmode="decimal" value="${whQty(row.transit_quantity_milli)}"></label>`;
 if(key==='capture')html+='<p>本人已完成现场清点。提交后释放该库位围栏；主管复核差异期间允许正常收发并显示衔接流水。</p><label>现场实盘数量<input name="counted" required inputmode="decimal"></label>';
 if(key==='post_count')html+='<p>核对实盘凭据和期间收发后只追加本次差额。已预占数量不足时会拒绝，并保留实盘观察。</p>';
 if(['cancel','reject','reject_transit','assign','void_observation'].includes(key))html+='<label>原因／交接说明<textarea name="reason" required minlength="2" maxlength="500"></textarea></label>';
 if(key==='void_observation')html+='<p>仅用于有凭据证明实盘观察错误。原实盘记录完整保留，本动作不更改库存；需要重新盘点时另建作业。</p>';
 if(key==='assign'){const users=(await api('/api/flow/lookup/employee?case_id='+row.id)).items||[];html+=`<label>本单未完成待办<select name="task">${whOptions(state.row.tasks.filter(t=>t.status==='open'),t=>t.title)}</select></label><label>接手员工<select name="assignee">${whOptions(users,u=>u.label)}</select></label><label>新期限<input name="due" type="date" required value="${day()}"></label>`;}
 if(needsFile)html+=`<label>本单实际凭据<select name="evidence_id" required>${whOptions(files,f=>f.name)}</select></label>`;
 const request_id=requestKey(),label=row.actions.find(a=>a.key===key)?.label||key;modal(label,`<form>${html}<div class="formerror" role="alert"></div><div class="modalfoot"><button type="submit" class="primary">确认本人办理</button></div></form>`,async form=>{
  const values={};if(financial)values.value_cents=purchaseScaled(form.elements.value.value,2);if(form.elements.quantity)values.quantity_milli=purchaseScaled(form.elements.quantity.value,3);if(form.elements.counted)values.counted_quantity_milli=purchaseScaled(form.elements.counted.value,3);if(form.elements.reason)values.reason=form.elements.reason.value;if(needsFile)values.evidence_id=Number(form.elements.evidence_id.value);if(key==='assign')Object.assign(values,{task_id:Number(form.elements.task.value),assignee_id:Number(form.elements.assignee.value),due_date:form.elements.due.value});
  await api(`/api/warehouse/cases/${row.id}/commands/${key}`,{method:'POST',body:{request_id,version:row.version,values}});closeModal();await render();
 });
}
async function warehouseAllocationPage(id){
 const options=await api('/api/warehouse/allocations/'+id);state.whAllocation=options;state.whSession=whContext();
 return heading('准备物资库位',options.number,b('open','返回原单',`data-route="case/${id}"`))+storeNotice()+panel('按原单实际数量分配','<p>这里只准备位置，不确认实际收发，也不替代原业务批准。请逐物资选择原动作与本次精确数量，回到原业务完成实际确认。</p>'+table(['相关物资','库位账',''],options.items.map(i=>[E(i.name),i.enabled?'已启用':'尚未定位',i.enabled?b('wh-allocate','准备这项库位',`data-id="${i.id}"`):b('open','前往启用','data-route="warehouse"')])));
}
async function whAllocate(id){
 const row=state.whAllocation;if(!row||state.whSession!==whContext())throw new Error('请刷新原单和门店。');const locs=await procurementAll('/api/masters/locations?active=true');state.whLocationHtml=whLocationLines(locs);
 const html=`<label>原业务动作<select name="purpose">${row.purposes.map(p=>`<option value="${p}">${E(whPurposes[p])}</option>`).join('')}</select></label><label>本次原业务数量<input name="quantity" required inputmode="decimal" placeholder="正数；根据动作自动选择入出方向"></label>${row.purposes.includes('count')?'<label>本次盘点方向<select name="count_direction"><option value="-1">盘亏</option><option value="1">盘盈</option></select></label>':''}<div id="wh-locations">${whLocationLines(locs,'1')}</div>${b('wh-add-location','增加实际库位')}`;
 const request_id=requestKey();modal('准备库位（尚未实际收发）',`<form>${html}<div class="formerror" role="alert"></div><div class="modalfoot"><button type="submit" class="primary">保存本次库位准备</button></div></form>`,async form=>{
  const purpose=form.elements.purpose.value,sign=purpose==='count'?Number(form.elements.count_direction.value):['purchase','return','procurement_receipt','transfer_in','transfer_return','repair_return_v3','retail_return','addon_return_v3'].includes(purpose)?1:-1;
  await api('/api/warehouse/allocations/'+row.case_id,{method:'POST',body:{request_id,version:row.version,values:{item_id:id,quantity_milli:sign*purchaseScaled(form.elements.quantity.value,3),purpose,locations:whReadLocations(form)}}});closeModal();await render();toast('库位已准备，请回原业务确认实际收发');
 });
}
document.addEventListener('click',async e=>{const el=e.target.closest('[data-act]');if(!el?.dataset.act.startsWith('wh-'))return;try{const a=el.dataset.act;if(a==='wh-new')await whNew(el.dataset.operation);else if(a==='wh-action')await whAction(el.dataset.key);else if(a==='wh-allocate')await whAllocate(Number(el.dataset.id));else if(a==='wh-add-location')$('#wh-locations').insertAdjacentHTML('beforeend',state.whLocationHtml);else if(a==='wh-remove-location'){if(document.querySelectorAll('[data-wh-location]').length<=1)throw new Error('至少保留一个实际库位。');el.closest('[data-wh-location]').remove();}}catch(error){toast(error.message,true);}});
