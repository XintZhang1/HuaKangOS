'use strict';
// Prepare only positions. The original action remains the sole physical posting.
function warehouseSourceStamp(source){const {version,updated_at,...facts}=source;return JSON.stringify(facts);}
function warehousePreparationLines(lines){
 const unique=new Map();
 for(const line of lines){
  if(!Number.isSafeInteger(line.item_id)||line.item_id<=0||!Number.isSafeInteger(line.quantity_milli)||line.quantity_milli<=0)throw new Error('请先填写本次物资和数量。');
  if(unique.has(line.item_id))throw new Error('同一物资有多个原批次，请每次办理一个批次并分别分配库位。');
  unique.set(line.item_id,{...line});
 }
 if(!unique.size)throw new Error('请先填写本次数量。');return [...unique.values()];
}
function warehouseLocationChoices(locations,warehouses){
 const names=new Map(warehouses.filter(w=>w.active&&w.warehouse_type==='materials').map(w=>[w.id,w.name]));
 return locations.filter(l=>l.active&&names.has(l.warehouse_id)).map(l=>({...l,label:names.get(l.warehouse_id)+' · '+l.name}));
}
function warehouseAllocationValues(root,lines){
 return lines.map(line=>{
  const section=root.querySelector(`[data-prep-item="${line.item_id}"]`),locations=[];
  for(const slot of section.querySelectorAll('[data-prep-location]')){
   const id=Number(slot.querySelector('[data-prep-bin]').value),raw=slot.querySelector('[data-prep-quantity]').value.trim();
   if(!raw)continue;
   const quantity=purchaseScaled(raw,3);if(!quantity)continue;
   if(!Number.isSafeInteger(id)||id<=0)throw new Error('请选择实际库位。');
   if(locations.some(l=>l.location_id===id))throw new Error('同一库位请合并为一行。');
   locations.push({location_id:id,quantity_milli:quantity});
  }
  const total=locations.reduce((sum,l)=>sum+l.quantity_milli,0);
  if(total!==line.quantity_milli)throw new Error(line.label+'：'+(total>line.quantity_milli?'超分配 ':'还差 ')+whQty(Math.abs(total-line.quantity_milli))+'，请核对库位数量。');
  return {item_id:line.item_id,quantity_milli:line.quantity_milli,locations};
 });
}
function mountWarehousePreparation(form,config){
 if(!['admin','inventory'].includes(state.user?.role))return {assertReady:async()=>{}};
 const context=storeContextVersion,sourceStamp=warehouseSourceStamp(config.source),root=document.createElement('section');
 root.className='warehouse-inline';root.innerHTML='<div class="row"><strong>实际库位</strong><button type="button" data-prep-open>分配库位</button></div><div data-prep-body hidden></div><div data-prep-status role="status"></div>';
 form.querySelector('.modalfoot').before(root);
 const status=root.querySelector('[data-prep-status]'),body=root.querySelector('[data-prep-body]'),open=root.querySelector('[data-prep-open]');
 let options,loading,loadingError,busy=false,blocked=false,lines=[],saved='',choices=[],locks;
 const check=()=>{requireStoreContext(context);if(!form.isConnected)throw new Error('表单已关闭，请重新打开。');};
 const selected=()=>{const relevant=config.getLines(form).filter(l=>options.items.some(i=>i.id===l.item_id&&i.enabled));return relevant.length?warehousePreparationLines(relevant):[];};
 const signature=()=>JSON.stringify(selected().map(l=>[l.item_id,l.quantity_milli]));
 const sourceCheck=async()=>{const fresh=await config.readSource();check();if(fresh.version!==config.getVersion()||warehouseSourceStamp(fresh)!==sourceStamp){blocked=true;throw new Error('原单已变化，请关闭本表，刷新核对后再办理。');}};
 const load=()=>{loadingError=null;loading=api('/api/warehouse/allocations/'+config.caseId).then(value=>{check();options=value;if(!options.purposes.includes(config.purpose))throw new Error('当前原单不能准备这项收发。');root.hidden=!options.items.some(i=>i.enabled);}).catch(error=>{loadingError=error;if(root.isConnected)status.textContent=error.message;});return loading;};
 load();
 const lock=()=>{locks=new Map([...form.querySelectorAll('input,select,textarea,button')].map(c=>[c,c.disabled]));for(const c of locks.keys())c.disabled=true;};
 const unlock=()=>{for(const [c,disabled]of locks||[])if(c.isConnected)c.disabled=disabled;locks=null;};
 const slot=(line,initial)=>`<div data-prep-location class="warehouse-bin-row"><label>库位<select data-prep-bin data-search-select><option value="">请选择库位</option>${choices.map(c=>`<option value="${c.id}" ${initial&&choices.length===1?'selected':''}>${E(c.label)}</option>`).join('')}</select></label><label>数量<input data-prep-quantity inputmode="decimal" value="${initial&&choices.length===1?whQty(line.quantity_milli):''}" placeholder="本库位数量"></label><button type="button" data-prep-remove>移除</button></div>`;
 const totals=()=>{for(const line of lines){const section=root.querySelector(`[data-prep-item="${line.item_id}"]`);if(!section)continue;let total=0,error=false;for(const input of section.querySelectorAll('[data-prep-quantity]'))try{total+=input.value.trim()?purchaseScaled(input.value,3):0;}catch{error=true;}const difference=line.quantity_milli-total;section.querySelector('[data-prep-total]').textContent=error?'数量最多三位小数':difference===0?'已分配完整':(difference>0?'还差 ':'超分配 ')+whQty(Math.abs(difference));}};
 root.addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button||button.disabled||busy)return;
  try{
   check();if(blocked)throw new Error('请关闭本表，刷新核对原单。');
   if(button.hasAttribute('data-prep-open')){
    busy=true;button.disabled=true;await loading;if(loadingError){await load();if(loadingError)throw loadingError;}
    await sourceCheck();lines=selected();if(!lines.length){status.textContent='本次物资无需分配库位。';return;}
    const [locations,warehouses]=await Promise.all([procurementAll('/api/masters/locations?active=true'),procurementAll('/api/masters/warehouses?active=true')]);check();
    choices=warehouseLocationChoices(locations,warehouses);if(!choices.length)throw new Error('请先配置物资仓库和库位。');
    saved='';body.innerHTML=lines.map(line=>`<div data-prep-item="${line.item_id}" class="warehouse-prep-item"><strong>${E(line.label)} · 本次 ${whQty(line.quantity_milli)}</strong><div data-prep-slots>${slot(line,true)}</div><div class="row"><button type="button" data-prep-add>增加库位</button><span data-prep-total role="status"></span></div></div>`).join('')+'<div class="row"><button type="button" data-prep-save>保存库位</button><button type="button" data-prep-dismiss>收起</button></div>';
    body.hidden=false;status.textContent='';totals();
   }else if(button.hasAttribute('data-prep-add')){const section=button.closest('[data-prep-item]'),line=lines.find(l=>l.item_id===Number(section.dataset.prepItem));section.querySelector('[data-prep-slots]').insertAdjacentHTML('beforeend',slot(line,false));totals();}
   else if(button.hasAttribute('data-prep-remove')){const section=button.closest('[data-prep-item]');if(section.querySelectorAll('[data-prep-location]').length<=1)throw new Error('至少保留一个库位。');button.closest('[data-prep-location]').remove();totals();}
   else if(button.hasAttribute('data-prep-dismiss'))body.hidden=true;
   else if(button.hasAttribute('data-prep-save')){
    const current=selected();if(JSON.stringify(current.map(l=>[l.item_id,l.quantity_milli]))!==JSON.stringify(lines.map(l=>[l.item_id,l.quantity_milli])))throw new Error('本次数量已变化，请重新点“分配库位”。');
    const prepared=warehouseAllocationValues(root,lines),beforeSignature=signature();busy=true;lock();
    if(typeof requireInlineFileIdle==='function')requireInlineFileIdle(root);
    await sourceCheck();
    for(const item of prepared){
     check();let result;
     try{result=await api('/api/warehouse/allocations/'+config.caseId,{method:'POST',body:{request_id:requestKey(),version:config.getVersion(),values:{...item,quantity_milli:item.quantity_milli*(config.purpose==='procurement_receipt'||config.purpose==='repair_return_v3'?1:-1),purpose:config.purpose}}});}
     catch(error){if(!error.status||error.status>=500)blocked=true;throw error;}
     check();config.setVersion(result.version);
    }
    await sourceCheck();saved=beforeSignature;body.hidden=true;status.textContent='库位已保存。核对本表后，再确认实际收发。';
    const formError=form.querySelector('.formerror');if(formError&&['请先分配并保存本次数量的实际库位。','正在保存库位，请稍候。'].includes(formError.textContent))formError.textContent='';
   }
  }catch(error){if(root.isConnected)status.textContent=blocked?'原单或保存结果需核对，请关闭本表并刷新原单。':error.message;}
  finally{busy=false;unlock();if(open.isConnected)open.disabled=false;}
 });
 const changed=event=>{if(event.target.closest('.warehouse-inline')){totals();saved='';return;}if(saved){try{if(signature()!==saved){saved='';status.textContent='数量已变化，请重新分配库位。';}}catch{saved='';}}};
 form.addEventListener('input',changed);form.addEventListener('change',changed);
 const controller={assertReady:async()=>{check();await loading;if(loadingError)throw loadingError;if(blocked)throw new Error('原单或保存结果需核对，请关闭本表并刷新原单。');if(busy)throw new Error('正在保存库位，请稍候。');if(selected().length&&saved!==signature())throw new Error('请先分配并保存本次数量的实际库位。');}};
 return controller;
}
