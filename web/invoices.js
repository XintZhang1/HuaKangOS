'use strict';
const invoiceStates={approval:'待独立复核',pending:'待外部办理',working:'外部办理中',resolving:'实际结果差异待复核',completed:'结果已登记',cancelled:'已取消',rejected:'申请已退回'};
const invoiceNames={approve:'独立复核批准',reject:'退回申请',cancel:'取消未办理申请',submit:'登记已提交外部办理',failure:'登记外部失败',difference:'记录票据差异',record:'登记实际发票',review_result:'独立复核结果差异'};
const invoiceFinance=()=>canWrite()&&['admin','finance'].includes(state.user.role);
const invoiceManager=()=>canWrite()&&['admin','manager'].includes(state.user.role);
async function invoicesPage(id){
 if(!id){
  const [orders,sources]=await Promise.all([api('/api/invoices/orders?page='+(state.invoiceOrdersPage||1)),api('/api/invoices/sources?page='+(state.invoiceSourcePage||1))]);
  const page=(data,kind)=>'<div class="pager">'+b('invoice-page','上一页','data-kind="'+kind+'" data-page="'+(data.page-1)+'" '+(data.page===1?'disabled':''))+'<span>第 '+data.page+' 页 · 共 '+data.total+' 条</span>'+b('invoice-page','下一页','data-kind="'+kind+'" data-page="'+(data.page+1)+'" '+(data.page*data.page_size>=data.total?'disabled':''))+'</div>';
  const sourcesTable=table(['原单／当前上限','已开净额／待处理','办理'],sources.items.map(s=>[
   E(s.number)+'<br>'+E(s.title)+'<br>'+E(s.source_basis?.label||'已确认')+' '+money(s.invoiceable_cents)+' 元',
   money(s.actual_net_cents)+' 元'+(s.correction_cents?'<p class="notice error">待冲红核对 '+money(s.correction_cents)+' 元</p>':''),
   s.available_cents&&invoiceFinance()?b('invoice-new','申请开票','data-source="'+s.id+'"'):b('open','查看原业务','data-route="case/'+s.id+'"')]));
  const ordersTable=table(['申请／原业务','类型／金额／状态','操作'],orders.items.map(r=>[
   E(r.number)+'<br>'+E(r.source_number),(r.direction==='blue'?'蓝票':'原票冲红')+' · '+money(r.amount_cents)+' 元<br>'+E(invoiceStates[r.state]),
   b('open','办理与核对','data-route="invoices/'+r.id+'"')]));
  return heading('开票与原票冲红','按照原业务办理申请、外部结果及原票冲红。')+storeNotice()+panel('原业务开票依据',sourcesTable+page(sources,'source'))+panel('开票办理记录',ordersTable+page(orders,'orders'));
 }
 const r=await api('/api/invoices/orders/'+id);state.invoiceOrder=r;let actions=[];
 if(invoiceManager()&&r.state==='approval')actions.push('approve','reject');
 if(invoiceManager()&&r.state==='resolving')actions.push('review_result');
 if(invoiceFinance()&&r.state==='pending')actions.push('submit');
 if(invoiceFinance()&&r.state==='working')actions.push('record','failure','difference');
 if((invoiceFinance()||invoiceManager())&&['approval','pending'].includes(r.state))actions.push('cancel');
 let buttons=actions.map(k=>b('invoice-action',invoiceNames[k],`data-key="${k}"`,['approve','submit','record'].includes(k)?'primary':'')).join('');
 if(invoiceFinance()&&r.red_available_cents>0)buttons+=b('invoice-red','申请本票部分或全部冲红');
 buttons+=b('open','本单凭据与待办',`data-route="case/${r.id}"`)+b('open','原业务',`data-route="case/${r.source_case_id}"`);
 return heading(r.direction==='blue'?'开票申请':'原票冲红',`${r.number} · ${invoiceStates[r.state]}`,buttons)+storeNotice()+panel('冻结的申请依据',`<p>原单 ${E(r.source_number)}；申请 ${money(r.amount_cents)} 元；计划 ${E(r.due_date)}。</p><p>销售方：${E(r.issuer_name)} · ${E(r.issuer_tax_id)}</p><p>购买方：${E(r.buyer_name)}${r.buyer_tax_id?' · '+E(r.buyer_tax_id):''}</p><p>${E(r.reason)}</p>`)+panel('原单当前核对',`<div class="stock-period-grid"><div>业务开票上限<strong>${money(r.balance.invoiceable_cents)} 元</strong></div><div>实际蓝票减红票<strong>${money(r.balance.actual_net_cents)} 元</strong></div><div>未登记结果蓝票额度<strong>${money(r.balance.pending_blue_cents)} 元</strong></div><div>超原业务待核对<strong>${money(r.balance.correction_cents)} 元</strong></div></div><p>办理期间原业务变更后，仍记录实际外部票据，并保留冲红核对待办。申请不代表开票成功，冲红不产生退款。</p>`)+panel('实际外部结果',r.result?`<p>${E(r.result.invoice_number)} · ${E(r.result.issued_on)}</p><p><strong>${money(r.result.amount_cents)} 元</strong></p>${b('downloadfile','下载实际发票',`data-id="${r.result.evidence_id}"`)}`:empty('尚未登记实际发票'))+panel('办理与异常记录',r.events.map(e=>`<article><strong>${E(e.label)}</strong><p>${E(e.detail.reason||'')} ${e.detail.reference?' · '+E(e.detail.reference):''}</p>${e.detail.observed_amount_cents!=null?`<p>外部待核对金额 ${money(e.detail.observed_amount_cents)} 元</p>`:''}<p class="muted">${E(time(e.occurred_at))}</p></article>`).join(''));
}
async function invoiceNew(sourceId,original=null){
 const source=await api('/api/invoices/sources/'+sourceId),request_id=requestKey();
 const sourceKind=source.source_basis?.kind,isIncome=sourceKind==='vehicle_income',isCorporate=isIncome||sourceKind==='insurance_commission';
 const fields=[F('amount','本次申请金额（元）','money')];
 if(!original){if(!source.issuer)fields.push(F('issuer_name','实际销售经营主体全称'),F('issuer_tax_id','实际销售方税号'));fields.push(F('buyer_name','购买方抬头'),F('buyer_tax_id',isIncome?'原厂家或供应商冻结税号':isCorporate?'原保险公司实际开票税号':'购买方税号（个人可空）','text',isCorporate));}
 fields.push(F('due_date','计划办理日期','date'),F('reason','本次开票或冲红依据','textarea'));
 const initial={amount:((original?original.red_available_cents:source.available_cents)/100).toFixed(2),due_date:state.catalog.today};
 if(!original&&isCorporate){initial.buyer_name=source.source_basis.buyer_name;if(isIncome)initial.buyer_tax_id=source.source_basis.buyer_tax_id;}
 await formDialog(original?'申请关联原票冲红':isIncome?'申请厂家及供应商整车收入开票':isCorporate?'申请保险佣金开票':'申请原业务开票',fields,initial,async v=>{
  const values={...v};delete values.amount;
  if(!original&&source.issuer){values.issuer_name=source.issuer.legal_name;values.issuer_tax_id=source.issuer.tax_identifier;}
  if(original)for(const key of ['issuer_name','issuer_tax_id','buyer_name','buyer_tax_id'])values[key]=original[key];
  const r=await api('/api/invoices/orders',{method:'POST',body:{request_id,...values,amount_cents:groupFen(v.amount),source_case_id:source.id,source_version:source.version,direction:original?'red':'blue',original_case_id:original?.id||null}});go('invoices/'+r.id);
 },{notice:original?'冲红使用原票销售方和购买方，金额占用原票可冲余额；外部红票和退款分别留证。':(isIncome?'本次按独立批准的门店开票版本办理，购买方须匹配原厂家或供应商冻结名称和税号。原收入修订不自动冲红，发票与资金分别留证。':isCorporate?'本次只开已独立确认的保险佣金，购买方为原保险公司，须核对其实际税号。客户保费不计入佣金开票额度。':'')+(source.issuer?'销售方沿用原单冻结主体：'+source.issuer.legal_name+'（'+source.issuer.tax_identifier+'）。请核对购买方及原业务；本单须独立复核。':'请填写实际经营主体和票据抬头。品牌名称不自动代表合同销售方；本单需要另一位主管复核。')});
}
async function invoiceAction(key){
 const r=state.invoiceOrder,fields=[],request_id=requestKey();
 if(key==='submit')fields.push(F('reference','实际外部申请编号或办理凭证号'));
 if(key==='record')fields.push(F('invoice_number','实际票号'),F('issued_on','实际开票日期','date'),F('amount','实际票面金额（元）','money'));
 if(key==='difference')fields.push(F('external_number','待核对外部票号或申请号','text',false),F('observed_amount','外部待核对金额（元，可空）','money_zero',false));
 if(!['cancel','reject'].includes(key))fields.push(F('evidence_id',key==='record'?'本单发票类别文件':'本单实际办理凭据','file'));
 fields.push(F('reason','本人办理结果或核对依据','textarea'));
 await formDialog(invoiceNames[key],fields,{issued_on:state.catalog.today,amount:(r.amount_cents/100).toFixed(2)},async v=>{
  const values={...v};if(key==='record'){values.amount_cents=groupFen(v.amount);delete values.amount;}
  if(key==='difference'){values.observed_amount_cents=v.observed_amount===''||v.observed_amount==null?null:retailScaled(v.observed_amount,2);delete values.observed_amount;}
  return api(`/api/invoices/orders/${r.id}/actions/${key}`,{method:'POST',body:{request_id,version:r.version,source_version:r.source_version,values}});
 },{caseId:r.id,notice:key==='record'?'填写实际票面金额，上传发票类别文件。与批准金额或原业务不一致时保留真实结果并转独立复核。':key==='submit'?'仅在本人已实际向外部办理后登记编号和凭据，系统不会向税务平台发起请求。':'办理或复核留存事实；已经开出的原票保留，须另建关联冲红申请。'});
}
document.addEventListener('click',async event=>{const el=event.target.closest('[data-act]');if(!el?.dataset.act.startsWith('invoice-'))return;try{if(el.dataset.act==='invoice-page'){state[el.dataset.kind==='source'?'invoiceSourcePage':'invoiceOrdersPage']=Number(el.dataset.page);await render();}else if(el.dataset.act==='invoice-new')await invoiceNew(Number(el.dataset.source));else if(el.dataset.act==='invoice-red')await invoiceNew(state.invoiceOrder.source_case_id,state.invoiceOrder);else if(el.dataset.act==='invoice-action')await invoiceAction(el.dataset.key);}catch(error){toast(error.message,true);}});
