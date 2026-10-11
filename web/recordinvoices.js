'use strict';
// Invoice originals, model suggestions and receipt facts are separate actions.
let recordInvoiceContext=null;
let recordInvoiceRun=0;
function clearRecordInvoices(){recordInvoiceContext=null;recordInvoiceRun++;}
function recordInvoiceCurrent(context){return Boolean(context&&context.ctx===brContext()&&context.epoch===renderId&&state.route==='records-sales/'+context.contract.id&&brState.detail?.id===context.contract.id);}
function recordInvoiceButton(action,label){return `<button type="button" data-record-invoice="${E(action)}">${E(label)}</button>`;}
async function brInvoiceSection(contract){
 if(contract.status!=='approved'||brCaps().read_invoice!==true)return '';
 const ctx=brContext(),epoch=renderId,data=await api(`${BR_API}/contracts/${contract.id}/invoice`);
 const context={contract,data,ctx,epoch};if(!recordInvoiceCurrent(context))return '';
 recordInvoiceContext=context;
 const r=data.invoice,editable=brCaps().upload_invoice===true&&state.store!=='all',f=r?.fields||{},quarantined=(data.files||[]).some(file=>file.current&&!file.available);
 return `<section class="panel"><div class="panelhead spread"><h2>合同发票${r?.confirmed_at?' · 收银已确认':''}</h2><div class="row">${editable?recordInvoiceButton('upload',r?'替换发票并识别':'上传发票并识别')+(r?recordInvoiceButton('recognize','重新识别')+recordInvoiceButton('edit','核对 / 确认发票'):''):''}</div></div><div class="panelbody">${quarantined?'<p class="notice warn">当前原件尚未通过文件检查，请由收银重新上传同一原件重试检查。上传记录已保留。</p>':''}${r?brFacts([['发票号码',f.invoice_number],['开票日期',f.issued_on],['购买方',f.buyer_name],['销售方',f.seller_name],['发票VIN',f.vin],['价税合计',f.total_amount_cents==null?'待核对':brAmount(f.total_amount_cents)],['税额',f.tax_amount_cents==null?'待核对':brAmount(f.tax_amount_cents)],['收银确认时间',r.confirmed_at?time(r.confirmed_at):'尚未确认'],['备注',r.note]]):'<p class="empty">尚未上传发票。</p>'}${r?`<div class="tablewrap">${table(['原件','状态','上传时间','操作'],(data.files||[]).map(x=>[E(x.filename),E(x.current?'当前发票':'替换前留档'),time(x.created_at),x.available?`<button type="button" data-record-invoice="download" data-file="${x.id}" data-name="${E(x.filename)}">下载原件</button>`:'原件隔离中']))}</div>`:''}<p class="fieldhelp">每合同一张当前发票，由收银核对确认；识别只填建议，不会确认到账。替换前的原件与确认记录保留。</p></div></section>`;
}
function recordInvoiceFields(){return [F('invoice_number','发票号码'),F('invoice_code','发票代码','text',false),F('invoice_type','发票类型','text',false),F('issued_on','开票日期','date'),F('buyer_name','购买方','text',false),F('buyer_tax_id','购买方识别号','text',false),F('seller_name','销售方','text',false),F('seller_tax_id','销售方识别号','text',false),F('vin','车辆识别号VIN','text',false),F('vehicle_model','车辆型号','text',false),F('total_amount','价税合计（元）','money_zero'),F('tax_amount','税额（元）','money_zero',false),F('net_amount','不含税金额（元）','money_zero',false),F('note','核对备注','textarea',false)];}
async function recordInvoiceEdit(context,suggestion=null,notice='请核对原件与下列信息后确认。'){
 if(!recordInvoiceCurrent(context))return;
 const row=context.data.invoice;if(!row)throw new Error('请先上传发票。');
 const fields=recordInvoiceFields(),raw=suggestion||context.suggestion||row.fields||{},values={...Object.fromEntries(fields.map(field=>[field.key,''])),...raw,note:row.note||''},requestId=requestKey();
 for(const key of ['total_amount','tax_amount','net_amount'])values[key]=raw[key+'_cents']==null?'':brInputAmount(raw[key+'_cents']);
 const marker=$('#modal').firstElementChild,html=(await Promise.all(fields.map(field=>fieldHTML(field,values[field.key]??'')))).join('');
 if(!recordInvoiceCurrent(context)||$('#modal').firstElementChild!==marker)return;
 modal('收银核对发票',`<form><div class="notice">${E(notice)} 确认发票不会自动记录实际到账。</div><div class="formgrid">${html}</div><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button type="submit" class="primary">收银确认发票</button></div></form>`,async form=>{
  if(!recordInvoiceCurrent(context))throw new Error('合同、门店或账号已变化，请重新打开核对。');
  const v=formValues(form,fields),payload={...v};delete payload.note;
  for(const key of ['total_amount','tax_amount','net_amount']){payload[key+'_cents']=v[key]===''?null:moneyFen(v[key],{label:key==='total_amount'?'价税合计':key==='tax_amount'?'税额':'不含税金额',allowZero:true});delete payload[key];}
  const result=await api(`${BR_API}/contracts/${context.contract.id}/invoice/confirm`,{method:'POST',body:{request_id:requestId,version:row.version,fields:payload,note:v.note}});
  if(!recordInvoiceCurrent(context))return;context.data=result;delete context.suggestion;
  if($('#modal form')===form&&$('#modal').open){closeModal();await render();}
  toast('合同 '+context.contract.number+' 的发票已由收银确认，到账记录未变更');
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
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-record-invoice]');if(!button||button.disabled||state.storeSwitch)return;
 const context=recordInvoiceContext;if(!recordInvoiceCurrent(context))return;
 button.disabled=true;
 try{
  const action=button.dataset.recordInvoice;
  if(action!=='download'&&brCaps().upload_invoice!==true)throw new Error('当前岗位仅可查看发票。');
  if(action==='upload')await recordInvoiceUpload(context);
  if(action==='recognize')await recordInvoiceRecognize(context);
  if(action==='edit')await recordInvoiceEdit(context);
  if(action==='download')await download(`${BR_API}/contracts/${context.contract.id}/invoice/files/${button.dataset.file}/download`,button.dataset.name);
 }catch(error){toast(error.message,true);}
 finally{if(button.isConnected)button.disabled=false;}
});
