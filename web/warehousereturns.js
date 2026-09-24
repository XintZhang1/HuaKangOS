'use strict';
// Originals and quantities come from the scoped warehouse ledger; this form only applies.
const whReturnTitles={other_in_return:'其他入库退回',consumable_return:'耗材退回',gift_return:'礼品退回'};
function whReturnLabel(row){return row.item_name+' · '+row.business_date+' · 可退 '+whQty(row.remaining_quantity_milli)+' '+row.unit+' · '+row.source_number;}
function whReturnSummary(row){return facts({'物资':row.item_name+' · '+row.sku,'原日期':row.business_date,'原单':row.source_number,'原数量':whQty(row.original_quantity_milli)+' '+row.unit,'已退数量':whQty(row.returned_quantity_milli)+' '+row.unit,'尚可退':whQty(row.remaining_quantity_milli)+' '+row.unit});}
function whReturnValues(form,source,operation,request_id){
 if(!source||Number(form.elements.original.value)!==source.original_move_id||source.operation!==operation)throw new Error('请先选择原批次。');
 if(!source.can_return||source.remaining_quantity_milli<=0)throw new Error('该批次已无可退数量，请重新选择。');
 const quantity=purchaseScaled(form.elements.quantity.value,3);if(quantity<=0||quantity>source.remaining_quantity_milli)throw new Error('本次数量须大于零，且不能超过 '+whQty(source.remaining_quantity_milli)+' '+source.unit+'。');
 const location=Number(form.elements.location.value);if(!Number.isInteger(location)||location<=0)throw new Error('请选择本次实际库位。');
 return {request_id,operation,item_id:source.item_id,original_move_id:source.original_move_id,quantity_milli:quantity,
  ...(operation==='other_in_return'?{source_location_id:location}:{destination_location_id:location}),reason:form.elements.reason.value,due_date:form.elements.due_date.value};
}
async function whReturnNew(operation,{originalMoveId}={}){
 if(!whReturnTitles[operation])throw new Error('请选择原仓储退回类型。');
 const context=storeContextVersion,query='/api/warehouse/return-sources?operation='+operation;
 const [catalog,initial,locations,warehouses]=await Promise.all([api('/api/warehouse/catalog'),api(query+(originalMoveId?'&original_move_id='+Number(originalMoveId):'')),procurementAll('/api/masters/locations?active=true'),procurementAll('/api/masters/warehouses?active=true')]);
 requireStoreContext(context);if(!catalog.can_create)throw new Error('请由本店库管办理退回。');
 const warehouseMap=new Map(warehouses.filter(r=>['materials','mixed'].includes(r.warehouse_type)).map(r=>[r.id,r]));
 const locs=locations.filter(r=>warehouseMap.has(r.warehouse_id));if(!locs.length)throw new Error('请先配置物资仓库和库位。');
 const key=requestKey();let source=null,revision=0,busy=false;
 const dialog=modal(whReturnTitles[operation],'<form id="warehouse-return-entry"><label>原批次<select name="original" required data-search-select data-search-placeholder="物资名称、编码或原单号"><option value="">查找原批次</option>'+initial.items.map(r=>'<option value="'+r.original_move_id+'">'+E(whReturnLabel(r))+'</option>').join('')+'</select></label><div data-return-summary></div><p data-return-status role="status"></p><label>本次实际退回数量<input name="quantity" type="number" step="0.001" min="0.001" required inputmode="decimal"></label><label>'+(operation==='other_in_return'?'本次退回出库位':'本次接收库位')+'<select name="location" required data-search-select data-search-placeholder="仓库或库位"><option value="">请选择实际库位</option>'+locs.map(r=>'<option value="'+r.id+'">'+E(warehouseMap.get(r.warehouse_id).name+' / '+r.name)+'</option>').join('')+'</select></label><label>退回原因<textarea name="reason" required minlength="2" maxlength="500"></textarea></label><label>办理期限<input name="due_date" type="date" required value="'+day()+'"></label><div class="formerror" role="alert"></div><div class="modalfoot">'+b('close','取消')+'<button type="submit" class="primary" disabled>提交退回申请</button></div></form>',async form=>{
  if(busy)return;requireStoreContext(context);const values=whReturnValues(form,source,operation,key);busy=true;
  try{const row=await api('/api/warehouse/cases',{method:'POST',body:values});requireStoreContext(context,'POST');closeModal();go('warehouse/'+row.id);}finally{busy=false;}
 });
 const form=dialog.querySelector('form'),select=form.elements.original,summary=form.querySelector('[data-return-summary]'),status=form.querySelector('[data-return-status]'),submit=form.querySelector('[type=submit]');
 const current=()=>context===storeContextVersion&&form.isConnected&&dialog.open;
 registerLiveChoiceLoader(select,async text=>{const data=await api(query+'&q='+encodeURIComponent(text));return {items:data.items.map(r=>({id:r.original_move_id,label:whReturnLabel(r)})),has_more:data.total>data.items.length};});
 select.addEventListener('change',async()=>{
  const run=++revision,id=Number(select.value);source=null;summary.innerHTML='';submit.disabled=true;form.elements.quantity.removeAttribute('max');form.elements.quantity.placeholder='';status.textContent='';
  if(!id)return;status.textContent='正在核对原批次…';
  try{const result=await api(query+'&original_move_id='+id);if(!current()||run!==revision)return;
   source=result.items.find(r=>r.original_move_id===id)||null;if(!source)throw new Error('未找到原批次，请重新选择。');
   summary.innerHTML=whReturnSummary(source);form.elements.quantity.max=String(source.remaining_quantity_milli/1000);form.elements.quantity.placeholder='最多 '+whQty(source.remaining_quantity_milli)+' '+source.unit;
   submit.disabled=!source.can_return;status.textContent=source.can_return?'':'该批次已无可退数量或暂不能办理。';
  }catch(error){if(current()&&run===revision){source=null;status.textContent=error.message;}}
 });
 if(originalMoveId){select.value=String(originalMoveId);select.dispatchEvent(new Event('change',{bubbles:true}));}
 else if(!initial.items.length)status.textContent='暂无可退批次，可输入物资或原单号查找。';
}
document.addEventListener('click',async event=>{const el=event.target.closest('[data-act="wh-original-return"]');if(!el||el.disabled)return;el.disabled=true;try{await whReturnNew(el.dataset.operation,{originalMoveId:Number(el.dataset.original)});}catch(error){toast(error.message,true);}finally{if(el.isConnected)el.disabled=false;}});
