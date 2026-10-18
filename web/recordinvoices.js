'use strict';
// Invoice originals, model suggestions and delivery confirmation are separate facts.
let recordInvoiceContext=null;
let recordInvoiceRun=0;
function clearRecordInvoices(){recordInvoiceContext=null;recordInvoiceRun++;}
function recordInvoiceCurrent(context){return Boolean(context&&context.ctx===brContext()&&context.epoch===renderId&&state.route==='records-sales/'+context.contract.id&&brState.detail?.id===context.contract.id);}
function recordInvoiceButton(action,label){return `<button type="button" data-record-invoice="${E(action)}">${E(label)}</button>`;}
function recordSignedDocumentSection(data){
 const labels={signed_contract:'客户签字盖章合同',signed_delivery:'交车确认单签字版'},seen=new Set();
 const files=(data.files||[]).map(file=>{const current=!seen.has(file.kind);seen.add(file.kind);return [E(labels[file.kind]||file.kind),E(file.filename),E(current?'最新上传':'历史留档'),time(file.created_at),file.available?`<button type="button" data-record-invoice="signed-download" data-file="${file.id}" data-name="${E(file.filename)}">下载原件</button>`:'原件受限或尚未通过文件检查'];});
 return `<div class="panelhead spread"><h3>签字材料留档</h3><div class="row">${data.can_upload?recordInvoiceButton('signed-contract','上传客户签字盖章合同')+recordInvoiceButton('signed-delivery','上传交车确认单签字版'):''}</div></div>${files.length?`<div class="tablewrap">${table(['材料类型','原件','留档状态','上传时间','操作'],files)}</div>`:'<p class="empty">尚未上传签字材料。</p>'}<p class="fieldhelp">签字材料按合同分别留存，更正请追加上传，历史原件保留。上传后仍按原流程由财务主动确认交车。</p>`;
}
async function brInvoiceSection(contract){
 if(contract.status!=='approved'||brCaps().read_invoice!==true)return '';
 const ctx=brContext(),epoch=renderId,[data,signedData]=await Promise.all([api(`${BR_API}/contracts/${contract.id}/invoice`),api(`${BR_API}/contracts/${contract.id}/signed-documents`)]);
 const context={contract,data,signedData,ctx,epoch};if(!recordInvoiceCurrent(context))return '';
 recordInvoiceContext=context;
 const r=data.invoice,editable=brCaps().upload_invoice===true&&state.store!=='all',f=r?.fields||{},quarantined=(data.files||[]).some(file=>file.current&&!file.available);
 const delivery=contract.workflow_version==='trial-v210'?contract.delivery_state:null,gift=delivery?.gift_document;
 const giftTools=delivery?.actions?.includes('upload_gift_document')?brFlowButton('gift-upload',gift?'追加更正盖章赠品单':'上传盖章赠品单'):'';
 const giftStatus=delivery?brFacts([['盖章赠品单',gift?.filename||'待上传'],['赠品单文件状态',gift?(gift.available?'已通过文件检查':'尚未通过文件检查，请重新上传或联系管理员'):'待上传盖章后的 PDF 或图片']]):'';
 return `<section class="panel" data-record-invoice-section><div class="panelhead spread"><h2>${delivery?'交车材料':'合同发票与签字材料'}${r?.confirmed_at?(delivery?' · 发票已核实':' · 收银已确认'):''}</h2><div class="row">${editable?recordInvoiceButton('upload',r?'替换发票并识别':'上传发票并识别')+(r?recordInvoiceButton('recognize','重新识别')+recordInvoiceButton('edit','核对 / 确认发票'):''):''}${giftTools}</div></div><div class="panelbody">${quarantined?'<p class="notice warn">当前原件尚未通过文件检查，请由收银重新上传同一原件重试检查。上传记录已保留。</p>':''}${r?brFacts([['发票号码',f.invoice_number],['开票日期',f.issued_on],['购买方',f.buyer_name],['销售方',f.seller_name],['发票VIN',f.vin],['开票价（含税）',f.total_amount_cents==null?'待核对':brAmount(f.total_amount_cents)],['业务上传时间',r.uploaded_at?time(r.uploaded_at):'历史记录未提供'],['财务核对时间',r.confirmed_at?time(r.confirmed_at):'尚未确认'],['备注',r.note]]):'<p class="empty">尚未上传发票。</p>'}${r?`<div class="tablewrap">${table(['原件','状态','上传时间','操作'],(data.files||[]).map(x=>[E(x.filename),E(x.current?'当前发票':'替换前留档'),time(x.created_at),x.available?`<button type="button" data-record-invoice="download" data-file="${x.id}" data-name="${E(x.filename)}">下载原件</button>`:'原件隔离中']))}</div>`:''}${giftStatus}<p class="fieldhelp">${delivery?'发票须由收银核实，盖章赠品单须上传并通过文件检查；两项材料齐备后，由财务主动确认交车。两份原件分别上传、分别留档。':'每合同一张当前发票，由收银核对确认；识别只填建议，核对后还须财务主动确认交车。'}替换前的原件与确认记录保留。</p>${recordSignedDocumentSection(signedData)}</div>${delivery&&state.user.role==='finance'?brDeliverySection(contract,true):''}</section>`;
}
function recordInvoiceFields(){return [F('invoice_number','发票号码'),F('invoice_code','发票代码','text',false),F('invoice_type','发票类型','text',false),F('issued_on','开票日期','date'),F('buyer_name','购买方','text',false),F('buyer_tax_id','购买方识别号','text',false),F('seller_name','销售方','text',false),F('seller_tax_id','销售方识别号','text',false),F('vin','车辆识别号VIN','text',false),F('vehicle_model','车辆型号','text',false),F('total_amount','开票价（含税，元）','money_zero'),F('note','核对备注','textarea',false)];}
async function recordInvoiceEdit(context,suggestion=null,notice='请核对原件与下列信息后确认。'){
 if(!recordInvoiceCurrent(context))return;
 const row=context.data.invoice;if(!row)throw new Error('请先上传发票。');
 const fields=recordInvoiceFields(),raw=suggestion||context.suggestion||row.fields||{},values={...Object.fromEntries(fields.map(field=>[field.key,''])),...raw,note:row.note||''},requestId=requestKey();
 values.total_amount=raw.total_amount_cents==null?'':brInputAmount(raw.total_amount_cents);
 const marker=$('#modal').firstElementChild,html=(await Promise.all(fields.map(field=>fieldHTML(field,values[field.key]??'')))).join('');
 if(!recordInvoiceCurrent(context)||$('#modal').firstElementChild!==marker)return;
 modal('收银核对发票',`<form><div class="notice">${E(notice)} 确认发票后再由财务确认交车；上传日作为核算日期。</div><div class="formgrid">${html}</div><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button type="submit" class="primary">收银确认发票</button></div></form>`,async form=>{
  if(!recordInvoiceCurrent(context))throw new Error('合同、门店或账号已变化，请重新打开核对。');
  const v=formValues(form,fields),payload={...v};delete payload.note;
  payload.total_amount_cents=v.total_amount===''?null:moneyFen(v.total_amount,{label:'开票价',allowZero:true});delete payload.total_amount;
  const result=await api(`${BR_API}/contracts/${context.contract.id}/invoice/confirm`,{method:'POST',body:{request_id:requestId,version:row.version,fields:payload,note:v.note}});
  if(!recordInvoiceCurrent(context))return;context.data=result;delete context.suggestion;
  if($('#modal form')===form&&$('#modal').open){closeModal();await render();}
  toast('合同 '+context.contract.number+' 的发票已核实，请从合同页面确认交车');
 });
}
async function recordInvoiceRecognize(context){
 const row=context.data.invoice;if(!row||!recordInvoiceCurrent(context))return;
 const run=++recordInvoiceRun,marker=$('#modal').firstElementChild,wasOpen=$('#modal').open;
 toast('正在识别发票，请稍候…');
 try{
  const result=await api(`${BR_API}/contracts/${context.contract.id}/invoice/recognize`,{method:'POST',body:{request_id:requestKey(),version:row.version}});
  if(!recordInvoiceCurrent(context)||run!==recordInvoiceRun)return;
  context.suggestion=result.fields;
  if($('#modal').firstElementChild!==marker||$('#modal').open!==wasOpen){toast('识别完成。当前填写内容已保留，请稍后点击“核对 / 确认发票”查看建议。');return;}
  await recordInvoiceEdit(context,result.fields,'DeepSeek识别结果待核对。请以原件为准，错误或空缺可直接修改。');
 }catch(error){
  if(!recordInvoiceCurrent(context)||run!==recordInvoiceRun)return;
  if([401,403,409].includes(error.status))throw error;
  if($('#modal').firstElementChild!==marker||$('#modal').open!==wasOpen){toast(error.message+' 可稍后点击“核对 / 确认发票”手动填写。',true);return;}
  await recordInvoiceEdit(context,null,error.message+' 也可以在此手动填写。');
 }
}
async function recordInvoiceUpload(context){
 const requestId=requestKey();
 modal('上传合同发票',`<form><label>发票原件<input type="file" name="file" accept=".pdf,.png,.jpg,.jpeg" required></label><p class="fieldhelp">PDF、PNG或JPEG，最多10MB。所选发票将发送给DeepSeek识别，结果仍由收银核对。替换原件将清空本张发票的待确认字段，旧原件及已确认记录保留。</p><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button type="submit" class="primary">上传并识别</button></div></form>`,async form=>{
  if(!recordInvoiceCurrent(context))throw new Error('合同、门店或账号已变化，请重新打开合同。');
  const file=form.elements.file.files[0];if(!file||file.size>10*1024*1024)throw new Error('请选择不超过 10 MB 的发票文件。');
  const body=new FormData(form);body.set('request_id',requestId);body.set('version',String(context.data.invoice?.version||0));
  const result=await api(`${BR_API}/contracts/${context.contract.id}/invoice`,{method:'POST',body});
  if(!recordInvoiceCurrent(context))return;context.data=result;
  if($('#modal form')!==form||!$('#modal').open){toast('发票上传已完成，请重新打开合同核对；当前窗口未改变。');return;}
  closeModal();await render();
  if(recordInvoiceCurrent(recordInvoiceContext)&&recordInvoiceContext.contract.id===context.contract.id){try{await recordInvoiceRecognize(recordInvoiceContext);}catch(error){if(context.ctx===brContext())toast(error.message,true);}}
 });
}
async function recordSignedDocumentUpload(context,kind){
 if(!recordInvoiceCurrent(context)||!context.signedData?.can_upload)throw new Error('当前岗位不能上传签字材料，请刷新合同后核对。');
 const label=kind==='signed_contract'?'客户签字盖章合同':'交车确认单签字版',requestId=requestKey();
 modal('上传'+label,`<form><label>${E(label)}<input type="file" name="file" accept=".pdf,.png,.jpg,.jpeg" required></label><p class="fieldhelp">PDF、PNG或JPEG，每份最多10MB。请上传签字后的完整原件；追加上传会保留此前原件。此材料仅作留档。</p><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button type="submit" class="primary">上传留档</button></div></form>`,async form=>{
  if(!recordInvoiceCurrent(context))throw new Error('合同、门店或账号已变化，请重新打开合同。');
  const file=form.elements.file.files[0];if(!file||file.size>10*1024*1024)throw new Error('请选择不超过 10 MB 的签字材料。');
  const body=new FormData(form);body.set('request_id',requestId);body.set('version',String(context.signedData.contract_version));body.set('kind',kind);
  const result=await api(`${BR_API}/contracts/${context.contract.id}/signed-documents`,{method:'POST',body});
  if(!recordInvoiceCurrent(context))return;context.signedData=result;
  if($('#modal form')!==form||!$('#modal').open){toast('合同 '+context.contract.number+' 的'+label+'已上传留档。');return;}
  closeModal();await render();toast('合同 '+context.contract.number+' 的'+label+'已上传留档');
 });
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-record-invoice]');if(!button||button.disabled||state.storeSwitch)return;
 const context=recordInvoiceContext;if(!recordInvoiceCurrent(context))return;
 button.disabled=true;
 try{
  const action=button.dataset.recordInvoice;
  if(!['download','signed-download'].includes(action)&&brCaps().upload_invoice!==true)throw new Error('当前岗位仅可查看交车材料。');
  if(action==='upload')await recordInvoiceUpload(context);
  if(action==='recognize')await recordInvoiceRecognize(context);
  if(action==='edit')await recordInvoiceEdit(context);
  if(action==='download')await download(`${BR_API}/contracts/${context.contract.id}/invoice/files/${button.dataset.file}/download`,button.dataset.name);
  if(action==='signed-contract')await recordSignedDocumentUpload(context,'signed_contract');
  if(action==='signed-delivery')await recordSignedDocumentUpload(context,'signed_delivery');
  if(action==='signed-download')await download(`${BR_API}/contracts/${context.contract.id}/signed-documents/files/${button.dataset.file}/download`,button.dataset.name);
 }catch(error){toast(error.message,true);}
 finally{if(button.isConnected)button.disabled=false;}
});
