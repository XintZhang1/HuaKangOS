'use strict';
const vpNames={approve:'批准并冻结逐车价格',reject:'拒绝采购计划',cancel_remaining:'终止未发运余量',request_funds:'申请采购付款',cancel_funds:'取消请款未付余量',pay:'登记分笔实际付款',refund:'登记原款实际退回',ship:'登记供应商逐VIN发运',receive:'逐VIN验收入库',return_request:'申请原车退回',return_approve:'批准退车',return_cancel:'撤销未发出退车',return_dispatch:'确认实车已退回'};
function clearVehicleProcurementSession(){state.vehicleProcurement=null;state.vpSession=null;state.vpLineHtml=null;}
function vpContext(){return `${state.user?.id}:${state.store}`;}
function vpOptions(rows,label){return rows.map(r=>`<option value="${r.id}">${E(label(r))}</option>`).join('');}
function vpFileOptions(financial=false){return (state.row?.files||[]).filter(f=>!f.generated&&f.security?.can_use&&(!financial||['receipt','invoice','signed_contract','procurement_contract'].includes(f.category))).map(f=>({id:f.id,name:f.name}));}
function vpButton(key,extra=''){return b('vp-action',vpNames[key],`data-key="${key}" ${extra}`);}
function vpStatus(state){return E({approval:'待主管核价',receiving:'采购办理中',completed:'实物与采购款已结清',rejected:'已拒绝'}[state]||state);}
async function vehicleProcurementPage(id){
 const catalog=await api('/api/vehicle-procurement/catalog');if(!catalog.can_read)return empty('请选择门店','整车采购由本店主管、库管、财务及审计按岗位处理。');
 if(!id){const d=await api('/api/vehicle-procurement/orders?page='+state.page);return heading('整车采购与付款','计划、请款、实际到账、发运与验收分别留据。',catalog.can_create?b('vp-new','建立整车采购计划','','primary'):'')+storeNotice()+panel('本店整车采购',table(catalog.can_money?['采购单／供货方','状态','应付（元）','预付（元）','供应商应退（元）','']:['采购单／供货方','状态',''],d.items.map(r=>{const cells=[`${E(r.number)}<br>${E(r.supplier_name)}`,vpStatus(r.state)];if(catalog.can_money)cells.push(money(r.totals.payable_cents),money(r.totals.prepaid_cents),money(r.totals.supplier_refund_due_cents));cells.push(b('open','办理',`data-route="vehicle-procurement/${r.id}"`));return cells;})))+pager(d.total)+(catalog.can_money?panel('采购资金对账',b('vp-export','导出原账对账CSV')+'<p>预付对应尚未验收的有效约定；取消或实物退回导致的超付单列供应商应退。</p>'):'');}
 const row=await api('/api/vehicle-procurement/orders/'+id);state.vehicleProcurement=row;state.vpSession=vpContext();state.row=await api('/api/flow/cases/'+id);
 const can=k=>canWrite()&&row.actions.includes(k),buttons=[];
 if(row.state==='approval'){for(const k of ['approve','reject'])if(can(k))buttons.push(vpButton(k));}
 else if(row.state!=='rejected'){
  if(row.lines.some(l=>l.unshipped_quantity>0))for(const k of ['ship','cancel_remaining'])if(can(k))buttons.push(vpButton(k));
  if(row.shipments.some(s=>s.status==='transit'&&!row.returns.some(r=>r.shipment_id===s.id&&['requested','approved','dispatched'].includes(r.status)))&&can('receive'))buttons.push(vpButton('receive'));
  if(row.shipments.some(s=>s.status!=='returned'&&!row.returns.some(r=>r.shipment_id===s.id&&r.status!=='cancelled'))&&can('return_request'))buttons.push(vpButton('return_request'));
  if(row.totals?.commitment_cents>row.totals?.paid_net_cents&&can('request_funds'))buttons.push(vpButton('request_funds'));
  if(row.funds_requests.some(f=>f.status==='open')&&can('pay'))buttons.push(vpButton('pay'));
  if(row.totals?.supplier_refund_due_cents>0&&can('refund'))buttons.push(vpButton('refund'));
 }
 let html=heading('整车采购办理',row.number,b('open','返回采购','data-route="vehicle-procurement"'))+storeNotice()+panel('原始计划与责任',`<div class="formgrid"><div>供货方<p>${E(row.supplier_name)}</p></div><div>采购经营主体<p>${E(row.contracting_party)}</p></div><div>计划到货<p>${E(row.due_date)}</p></div><div>状态<p>${vpStatus(row.state)}</p></div></div><p>${E(row.reason)}</p>`);
 if(row.totals){const t=row.totals;html+='<div class="kpis">'+[['已付净额',t.paid_net_cents],['实际验收',t.received_cents],['当前应付',t.payable_cents],['采购预付',t.prepaid_cents],['供应商应退',t.supplier_refund_due_cents]].map(([label,v])=>`<div class="kpi"><div class="label">${label}（元）</div><div class="value">${money(v)}</div></div>`).join('')+'</div>';}
 html+=panel('当前办理',buttons.length?`<div class="row">${buttons.join('')}</div>`:'<p>当前岗位没有可办理步骤，请查看责任待办。</p>');
 html+=panel('车型及数量计划',table(row.totals?['车型／颜色','约定台数','尚未发运','冻结单车成本（元）','建议售价（元）']:['车型／颜色','约定台数','尚未发运'],row.lines.map(l=>{const cells=[`${E(l.brand)} · ${E(l.model_name)}<br>${E(l.model_year)}年款 · ${E(l.color)}`,l.quantity,l.unshipped_quantity];if(row.totals)cells.push(l.unit_cost_cents===undefined?'待核价':money(l.unit_cost_cents),l.list_price_cents===undefined?'待核价':money(l.list_price_cents));return cells;})));
 html+=panel('逐VIN发运及实车',table(['VIN','状态','发运日期','预计到货','库存记录'],row.shipments.map(s=>[E(s.vin),E({transit:'在途待验收',received:'已验收入库',returned:'已退回供应商'}[s.status]),E(s.shipped_date),E(s.expected_date),row.receipts.find(r=>r.shipment_id===s.id)?.vehicle_id||'尚未入库'])));
 html+=panel('原车退回与实物凭据',table(['VIN','退回状态','原因','办理'],row.returns.map(r=>{const acts=[];if(r.status==='requested'&&can('return_approve'))acts.push(vpButton('return_approve',`data-id="${r.id}"`));if(['requested','approved'].includes(r.status)&&can('return_cancel'))acts.push(vpButton('return_cancel',`data-id="${r.id}"`));if(r.status==='approved'&&can('return_dispatch'))acts.push(vpButton('return_dispatch',`data-id="${r.id}"`));return[E(row.shipments.find(s=>s.id===r.shipment_id)?.vin),E({requested:'待主管复核',approved:'待实际发出',dispatched:'已实际退回',cancelled:'已撤销'}[r.status]),E(r.reason),`<div class="row">${acts.join('')||'—'}</div>`];})));
 if(row.totals){html+=panel('请款安排',table(['编号','申请金额（元）','未付余量（元）','状态',''],row.funds_requests.map(f=>[f.id,money(f.amount_cents),money(f.unpaid_cents),E({open:'待分笔付款',closed:'已付清',cancelled:'余量已取消'}[f.status]),f.status==='open'&&can('cancel_funds')?vpButton('cancel_funds',`data-id="${f.id}"`):'—'])));
  html+=panel('原始付款及退款',table(['款项编号／原款','类型','实际金额（元）','流水凭证号'],row.payments.map(p=>[p.original_id?`${p.id} / 原款 ${p.original_id}`:p.id,p.direction==='out'?'实际付款':'原款退款',money(p.amount_cents),E(p.reference)])));
  if(row.totals.due_rows?.length)html+=panel('验收批次应付期限',table(['原验收批次','应付到期日','未付金额（元）'],row.totals.due_rows.map(d=>[d.receipt_id,E(d.due_date),money(d.amount_cents)])));}
 html+=panel('不可覆盖的实物记录',table(row.totals?['VIN','类型','库存台数变动','价值变动（元）']:['VIN','类型','库存台数变动'],row.movements.map(m=>{const r=[E(row.shipments.find(s=>s.id===m.shipment_id)?.vin),E({receive:'实际验收',return:'原车退回',transit_return:'未入库拒收退回'}[m.kind]),m.quantity];if(row.totals)r.push(money(m.value_cents));return r;})));
 html+=panel('本单文件',canWrite()?b('upload','上传核价、发运、验收或资金凭据'):'');
 html+=panel('已有凭据',(state.row.files||[]).map(f=>`<div class="filerecord"><div class="filetext"><strong>${E(f.name)}</strong><p>${E(f.label)} · ${E(f.security?.label||'等待检查')}</p><div class="row">${b('filescaninfo','检查记录',`data-id="${f.id}"`)}${f.security?.can_use?b('download','下载',`data-id="${f.id}"`):'检查通过后可使用'}</div></div></div>`).join('')||'<p>先上传本单实际凭据。核价与资金资料使用财务文件类别。</p>');
 html+=panel('岗位待办与交接',table(['责任事项','当前经办人','期限','状态'],state.row.tasks.map(t=>[E(t.title),E(t.assignee_name),E(t.due_date),pill(t.status)]))+b('open','查看原单与待办交接',`data-route="case/${row.id}"`));
 return html;
}
async function vpNew(){
 const [suppliers,models,catalog]=await Promise.all([procurementAll('/api/masters/suppliers?active=true'),procurementAll('/api/masters/vehicle_models?active=true'),api('/api/vehicle-procurement/catalog')]);
 if(!suppliers.length||!models.length)throw new Error('请先配置启用的供应商及车型参数主档。');
 const opts=vpOptions(models,r=>`${r.brand} · ${r.name} · ${r.model_year}年款`),line=()=>`<div class="panelbody" data-vp-line><label>车型<select name="model">${opts}</select></label><div class="formgrid"><label>颜色<input name="color" required maxlength="40"></label><label>台数<input name="quantity" required type="number" min="1" max="1000" step="1" value="1"></label></div>${b('vp-remove-line','删除这一行')}</div>`;
 state.vpLineHtml=line();const key=requestKey();modal('整车采购计划',`<form><label>供货方<select name="supplier_id">${vpOptions(suppliers,r=>r.name)}</select></label><label>实际采购经营主体<input name="contracting_party" required minlength="2" maxlength="180" value="${E(catalog.operating_party||'')}" ${catalog.operating_party?'readonly':''} placeholder="按真实合同抬头填写"></label><label>计划到货日期<input name="due_date" type="date" required value="${day()}"></label><label>采购原因<textarea name="reason" required minlength="2" maxlength="500"></textarea></label><div id="vp-lines">${line()}</div>${b('vp-add-line','增加车型行')}<p>此处只申请车型和台数；主管核对来源后确认并冻结价格。</p><div class="formerror" role="alert"></div><div class="modalfoot"><button type="submit" class="primary">提交主管</button></div></form>`,async form=>{
  const lines=[...form.querySelectorAll('[data-vp-line]')].map(el=>({model_id:Number(el.querySelector('[name=model]').value),color:el.querySelector('[name=color]').value,quantity:Number(el.querySelector('[name=quantity]').value)}));
  const r=await api('/api/vehicle-procurement/orders',{method:'POST',body:{request_id:key,supplier_id:Number(form.elements.supplier_id.value),contracting_party:form.elements.contracting_party.value,due_date:form.elements.due_date.value,reason:form.elements.reason.value,lines}});closeModal();go('vehicle-procurement/'+r.id);
 });
}
async function vpAction(key,id){
 const row=state.vehicleProcurement;if(!row||state.vpSession!==vpContext())throw new Error('门店或账号已变化，请重新打开采购单。');
 const request_id=requestKey(),send=values=>api(`/api/vehicle-procurement/orders/${row.id}/actions/${key}`,{method:'POST',body:{request_id,version:row.version,values}});
 const financial=['approve','request_funds','pay','refund'].includes(key),files=['pay','refund'].includes(key)?(state.row.files||[]).filter(f=>!f.generated&&f.security?.can_use&&f.category==='receipt').map(f=>({id:f.id,name:f.name})):vpFileOptions(financial);
 const fileField=()=>`<label>本单实际凭据<select name="evidence_id" required>${vpOptions(files,r=>r.name)}</select></label>`;
 const needsFile=!['reject','cancel_funds','return_approve','return_cancel'].includes(key);if(needsFile&&!files.length)throw new Error(financial?'请先上传通过检查的收退款凭据、发票或合同签回等财务文件。':'请先上传本单实际凭据并通过附件检查。');
 let html='',parse=form=>({}),extra={};
 if(key==='approve'){
  html='<p>核对真实采购约定后逐行确认；批准后价格不覆盖。库存岗位不会读取本表金额。</p>'+row.lines.map(l=>`<div class="panelbody"><strong>${E(l.model_name)} · ${E(l.color)} · ${l.quantity} 台</strong><label>单车成本（元）<input name="cost_${l.id}" inputmode="decimal" required></label><label>建议售价（元）<input name="price_${l.id}" inputmode="decimal" required></label></div>`).join('');
  parse=f=>({prices:row.lines.map(l=>({line_id:l.id,unit_cost_cents:purchaseScaled(f.elements['cost_'+l.id].value,2),list_price_cents:purchaseScaled(f.elements['price_'+l.id].value,2)}))});
 }else if(key==='ship'){
  html=`<label>实际发运车型行<select name="line_id">${vpOptions(row.lines.filter(l=>l.unshipped_quantity>0),l=>`${l.model_name} · ${l.color} · 待发运${l.unshipped_quantity}台`)}</select></label><label>供应方实际发运 VIN<input name="vin" required minlength="17" maxlength="17"></label><label>实际发运日期<input name="shipped_date" type="date" value="${day()}" required></label><label>预计到货日期<input name="expected_date" type="date" value="${row.due_date}" required></label>`;
  parse=f=>({line_id:Number(f.elements.line_id.value),vin:f.elements.vin.value,shipped_date:f.elements.shipped_date.value,expected_date:f.elements.expected_date.value});
 }else if(key==='receive'){
  const locs=await procurementAll('/api/masters/locations?active=true');html=`<label>待验收发运 VIN<select name="shipment_id">${vpOptions(row.shipments.filter(s=>s.status==='transit'),s=>s.vin)}</select></label><label>现场重新核对 VIN<input name="vin" required minlength="17" maxlength="17" placeholder="对照实车重新输入"></label><label>实际入库库位<select name="location_id">${vpOptions(locs,l=>l.name)}</select></label><p>请选择整车或混合仓库位；VIN不一致应核对或申请拒收退回。</p>`;
  parse=f=>({shipment_id:Number(f.elements.shipment_id.value),vin:f.elements.vin.value,location_id:Number(f.elements.location_id.value)});
 }else if(key==='return_request'){
  html=`<label>本次实际退回车辆<select name="shipment_id">${vpOptions(row.shipments.filter(s=>s.status!=='returned'&&!row.returns.some(r=>r.shipment_id===s.id&&r.status!=='cancelled')),s=>s.vin)}</select></label>`;parse=f=>({shipment_id:Number(f.elements.shipment_id.value)});
 }else if(key==='request_funds'){html='<label>本次请款金额（元）<input name="amount" required inputmode="decimal"></label>';parse=f=>({amount_cents:purchaseScaled(f.elements.amount.value,2)});
 }else if(['pay','refund'].includes(key)){
  const accounts=(await procurementAll('/api/flow/master/accounts?page_size=100')).filter(a=>a.active);
  html=key==='pay'?`<label>获准请款<select name="funds_request_id">${vpOptions(row.funds_requests.filter(f=>f.status==='open'),f=>`请款${f.id} · 待付 ${money(f.unpaid_cents)}元`)}</select></label>`:`<label>本次退款原付款<select name="original_payment_id">${vpOptions(row.payments.filter(p=>p.direction==='out'),p=>`原款${p.id} · ${money(p.amount_cents)}元 · ${p.reference}`)}</select></label>`;
  html+=`<label>本次实际金额（元）<input name="amount" inputmode="decimal" required></label><label>实际资金账户<select name="account_id">${vpOptions(accounts,a=>a.name)}</select></label><label>银行流水或现金凭证号<input name="reference" required maxlength="100"></label><p>只在真实款项发生后登记；退款须回原付款账户。</p>`;
  parse=f=>({[key==='pay'?'funds_request_id':'original_payment_id']:Number(f.elements[key==='pay'?'funds_request_id':'original_payment_id'].value),amount_cents:purchaseScaled(f.elements.amount.value,2),account_id:Number(f.elements.account_id.value),reference:f.elements.reference.value});
 }else if(key==='cancel_funds'){const f=row.funds_requests.find(r=>r.id===id);extra={funds_request_id:f.id,funds_version:f.version};html='<p>仅取消尚未实际支付的余量；已付款继续保留，退款需另行登记。</p>';}
 else if(key.startsWith('return_')){const r=row.returns.find(r=>r.id===id);extra={return_id:r.id,return_version:r.version};html=`<p>原车 VIN：${E(row.shipments.find(s=>s.id===r.shipment_id)?.vin)}</p>`+(key==='return_dispatch'?'<p>确认前应已完成原车交接并保存供应商收车或物流凭据；此动作不代表资金已退款。</p>':'');}
 const needsReason=['reject','cancel_remaining','request_funds','cancel_funds','return_request','return_approve','return_cancel','return_dispatch'].includes(key);
 if(needsReason)html+='<label>依据与原因<textarea name="reason" required minlength="2" maxlength="500"></textarea></label>';
 if(needsFile)html+=fileField();
 modal(vpNames[key],`<form>${html}<div class="formerror" role="alert"></div><div class="modalfoot"><button type="submit" class="primary">确认本人办理</button></div></form>`,async form=>{
  const values={...parse(form),...extra};if(needsReason)values.reason=form.elements.reason.value;if(needsFile)values.evidence_id=Number(form.elements.evidence_id.value);
  await send(values);closeModal();await render();
 });
}
document.addEventListener('click',async event=>{const el=event.target.closest('[data-act]');if(!el?.dataset.act.startsWith('vp-'))return;try{
 const action=el.dataset.act;if(action==='vp-new')await vpNew();else if(action==='vp-action')await vpAction(el.dataset.key,Number(el.dataset.id));
 else if(action==='vp-add-line')$('#vp-lines').insertAdjacentHTML('beforeend',state.vpLineHtml);
 else if(action==='vp-remove-line'){if(document.querySelectorAll('[data-vp-line]').length<=1)throw new Error('至少保留一行车型。');el.closest('[data-vp-line]').remove();}
 else if(action==='vp-export'){const response=await api('/api/vehicle-procurement/reconciliation/export',{raw:true}),url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download='huakangos-整车采购对账.csv';link.click();URL.revokeObjectURL(url);}
 }catch(error){toast(error.message,true);}});
