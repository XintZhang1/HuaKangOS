/* Gift quantities come from the approved contract; each confirmation uses one unit. */
async function brBenefitSection(r){
 if(brCaps().read_invoice!==true||r.status!=='approved')return '';
 const context=brContext(),data=await api(BR_API+'/contracts/'+r.id+'/benefits');if(context!==brContext())return '';
 r.benefits=data;
 const button=(action,label,extra='')=>`<button type="button" data-br-benefit="${action}" ${extra}>${E(label)}</button>`;
 return `<section class="panel" id="br-benefits"><div class="panelhead"><h2>赠送保养 / 项目兑换</h2></div><div class="panelbody"><p class="br-caption">核对客户本次实际完成的服务与赠送条件后，每次兑换 1 次或 1 份。首保不打印、NPS在客户联隐藏，均保留兑换记录。</p>${table(['赠送项目','赠送数量','已兑换','剩余','办理'],data.items.map(item=>[E(item.name),E(item.total+' '+item.unit),E(item.used+' '+item.unit),E(item.remaining+' '+item.unit),data.can_redeem&&item.remaining>0?button('redeem','兑换 1 '+item.unit,`data-source="${E(item.key)}"`):'—']))}${!data.items.length?'<p class="br-caption">本合同没有可确认数量的赠送项目。</p>':''}<details class="br-disclosure"><summary>兑换及误录撤销记录（${data.history.length}条）</summary>${table(['兑换日期','项目','本次变动','经办人','说明','操作'],data.history.map(item=>[E(item.redeemed_on),E(item.name),E((item.quantity>0?'兑换 1 ':'撤销恢复 1 ')+item.unit),E(item.created_by_name),E(item.note||'—'),item.can_reverse?button('reverse','误录撤销',`data-event="${item.id}"`):'—']))}</details></div></section>`;
}

document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-br-benefit]');if(!button||button.disabled||state.storeSwitch)return;
 const r=brState.detail,data=r?.benefits,context=brContext();if(!data)return;
 button.disabled=true;
 try{
  if(button.dataset.brBenefit==='redeem'){
   const item=data.items.find(x=>x.key===button.dataset.source);if(!item||!data.can_redeem||item.remaining<1)throw new Error('赠送权益已变化，请刷新核对。');
   await brForm('兑换 1 '+item.unit,[{title:item.name+' · 剩余 '+item.remaining+' '+item.unit,fields:[F('redeemed_on','实际兑换日期','date'),F('note','服务记录 / 说明','textarea',false),F('confirmed','已核对本次服务已完成，并符合此项目赠送条件','bool',false)]}],{redeemed_on:day()},(v,request_id)=>{
    if(context!==brContext()||brState.detail?.id!==r.id)throw new Error('账号、门店或合同已变化，请重新打开。');
    if(!v.confirmed)throw new Error('请先核对并勾选本次服务及赠送条件。');
    return api(BR_API+'/contracts/'+r.id+'/benefits/redeem',{method:'POST',body:{request_id,version:data.version,source_key:item.key,redeemed_on:v.redeemed_on,note:v.note,confirmed:true}});
   },{draftKey:'benefit-redeem-'+r.id+'-'+item.key+'-'+data.version,submit:'确认兑换 1 '+item.unit,notice:'本次确认只扣减此项目 1 '+item.unit+'。请勿重复办理。'});
  }else{
   const item=data.history.find(x=>x.id===Number(button.dataset.event));if(!item?.can_reverse)throw new Error('该记录已撤销或不可办理，请刷新。');
   await brForm('撤销误录兑换',[{title:item.name+' · '+item.redeemed_on,fields:[F('note','误录原因','textarea')]}],{},(v,request_id)=>{
    if(context!==brContext()||brState.detail?.id!==r.id)throw new Error('账号、门店或合同已变化，请重新打开。');
    return api(BR_API+'/contracts/'+r.id+'/benefits/'+item.id+'/reverse',{method:'POST',body:{request_id,version:data.version,note:v.note}});
   },{draftKey:'benefit-reverse-'+r.id+'-'+item.id+'-'+data.version,submit:'确认误录撤销',notice:'追加撤销记录并恢复 1 '+item.unit+'，原兑换记录继续保留。'});
  }
 }catch(error){toast(error.message,true);}finally{if(button.isConnected)button.disabled=false;}
});
