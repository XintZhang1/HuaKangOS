'use strict';
const businessFinanceNames={advance:'客户预收款',advance_apply:'预收抵用原单',advance_refund:'未用预收退款',statement:'客户期间月结',correction:'原收款误记更正',stored_correction:'预收／会员原充值误记更正',other_return:'其他入库退货应收',other_return_adjust:'供应方应退目标更正',other_return_refund:'供应方超收原款退款'};
const businessFinanceStates={draft:'待复核',approved:'已批准待办理',completed:'已完成',cancelled:'已取消',superseded:'已追加新版本'};
businessFinanceNames.fee_correction='续会费同额登记更正';
const businessFinanceFront=()=>canWrite()&&['admin','manager','finance','sales','service','reception','customer_service'].includes(state.user.role);
const businessFinanceCash=()=>canWrite()&&['admin','finance'].includes(state.user.role);
const businessFinanceManager=()=>canWrite()&&['admin','manager'].includes(state.user.role);
const businessFinanceZero=v=>/^0(?:\.0{1,2})?$/.test(String(v||'0'))?0:groupFen(v);
const businessFinanceReceiptLabel=r=>`${r.business_date} · ${r.account} · ${r.reference} · ${money(r.amount_cents)}元`+(r.bundle_name?` · ${r.bundle_name}（每份${money(r.bundle_principal_per_share)}元）`:'')+(r.refunded_cents?` · 已实退${money(r.refunded_cents)}元，剩余${money(r.net_amount_cents)}元`:'');
async function businessFinancePage(customerId){
 if(state.store==='all')return heading('业务财务结算')+storeNotice();
 const orders=await api('/api/business-finance/orders');
 if(!customerId){const customers=await api(`/api/flow/master/customers?q=${encodeURIComponent(state.q)}&page=${state.page}`);return heading('业务财务结算','本店客户预收、原单月结及实际到账逐单分配。',businessFinanceCash()?b('business-finance-other','建立其他入库退货应收'):'')+searchBar()+panel('选择本店客户',table(['客户','电话','办理'],customers.items.map(c=>[E(c.name),E(c.phone),b('open','查看预收与月结',`data-route="business-finance/${c.id}"`)]))+pager(customers.total))+businessFinanceOrders(orders.items);}
 const [sources,advances]=await Promise.all([api('/api/business-finance/sources?customer_id='+customerId),api('/api/business-finance/advances?customer_id='+customerId)]);state.businessFinanceCustomer={customerId:Number(customerId),sources:sources.items,advances:advances.items};
 const buttons=businessFinanceFront()?b('business-finance-create','登记实际预收','data-key="advance"','primary')+(businessFinanceCash()?b('business-finance-create','建立期间月结','data-key="statement"')+b('business-finance-create','更正业务收款','data-key="correction"')+b('business-finance-create','更正预收／会员充值','data-key="stored_correction"')+(state.catalog?.capabilities?.member_fee_corrections?b('business-finance-create','更正续会费登记','data-key="fee_correction"'):''):''):'';
 return heading('业务财务结算','每笔预收保留原款；批准抵用形成支付关联，不再记一笔现金。',buttons+b('open','返回客户','data-route="business-finance"'))+panel('本店原预收余额',table(['原款／余额','批准占额／可用','办理'],advances.items.map(a=>[`${money(a.initial_cents)} / ${money(a.balance_cents)} 元`,`${money(a.reserved_cents)} / ${money(a.available_cents)} 元`,b('open','原预收凭据',`data-route="business-finance-order/${a.case_id}"`)+(businessFinanceFront()&&a.available_cents>0?b('business-finance-create','申请抵用',`data-key="advance_apply" data-id="${a.id}"`)+b('business-finance-create','申请原款退款',`data-key="advance_refund" data-id="${a.id}"`):'')])) )+panel('可结算客户原单',table(['原业务','客户当前未结','来源'],sources.items.map(s=>[E(s.number),money(s.due_cents),b('open','查看原单',`data-route="case/${s.case_id}"`)])))+businessFinanceOrders(orders.items.filter(o=>o.customer_id===Number(customerId)));
}
function businessFinanceOrders(items){return panel('本店财务办理',table(['事项','状态','原办理单'],items.map(o=>[E(o.title),E(o.state==='pending'?'待办理':businessFinanceStates[o.state]||o.state),b('open','待办与原始凭据',`data-route="business-finance-order/${o.case_id}"`)])));}
async function businessFinanceOrderPage(id){
 if(state.store==='all')return heading('财务业务办理')+storeNotice();
 const [d,source]=await Promise.all([api('/api/business-finance/orders/'+id),api('/api/flow/cases/'+id)]);state.businessFinanceOrder=d;state.row=source;
 const o=d.order,buttons=[],assigned=key=>source.tasks.some(t=>t.key===key&&t.status==='open'&&(state.user.role==='admin'||t.assignee_id===state.user.id));
 if(o.status==='draft'&&o.purpose!=='advance'&&businessFinanceManager()&&o.requested_by!==state.user.id&&assigned('business_finance_review'))buttons.push(b('business-finance-action','独立复核批准','data-key="approve"','primary'),b('business-finance-action','退回申请','data-key="reject"'));
 if((o.status==='approved'||o.purpose==='advance'&&o.status==='draft')&&businessFinanceCash()&&assigned('business_finance_execute')&&!(o.purpose==='other_return'&&d.return_target?.overpayment_cents>0))buttons.push(b('business-finance-action',o.purpose==='advance_apply'?'确认抵用原单':['correction','stored_correction','fee_correction','other_return_adjust'].includes(o.purpose)?'按批准内容追加更正':'登记本次实际收付款',`data-key="${['statement','other_return'].includes(o.purpose)?'collect':'execute'}"`,'primary'));
 if(o.purpose==='other_return'&&d.return_target&&businessFinanceCash())buttons.push(b('business-finance-create','更正供应方应退目标','data-key="other_return_adjust"'));
 if(o.purpose==='other_return'&&d.return_target?.overpayment_cents>d.return_target?.refund_reserved_cents&&businessFinanceCash())buttons.push(b('business-finance-create','申请退回供应方超收款','data-key="other_return_refund"'));
 if(['draft','approved'].includes(o.status)&&!(o.purpose==='other_return'&&o.status==='approved')&&businessFinanceFront()&&(o.requested_by===state.user.id||businessFinanceManager()))buttons.push(b('business-finance-action','取消未完成办理','data-key="cancel"'));
 if(o.purpose==='statement'&&!['cancelled','superseded'].includes(o.status)&&businessFinanceCash())buttons.push(b('business-finance-action','重算并追加账单版本','data-key="recalculate"'));
 let facts=`<p>${E(businessFinanceNames[o.purpose])} · ${E(o.purpose==='advance'&&o.status==='draft'?'待财务确认':businessFinanceStates[o.status])}</p><p>申请金额：${money(d.case.amount_cents)} 元</p>`;
 if(d.advance)facts+=`<p>原登记预收账户：${E(d.advance.account_name)}；原登记 ${money(d.advance.initial_cents)} 元，累计误记更正 ${money(d.advance.correction_cents||0)} 元。</p><p>当前原款账户：${E(d.advance.effective_account_name||d.advance.account_name)}；余额 ${money(d.advance.balance_cents)} 元；已批准占额 ${money(d.advance.reserved_cents)} 元。</p>`;
 if(d.application?.target_case_id){const target=d.source_cases.find(s=>s.id===d.application.target_case_id);facts+=`<p>明确抵用原单：${E(target?.number||'请核对原单')} · ${money(d.application.amount_cents)} 元。</p>`+b('open','查看抵用原业务',`data-route="case/${d.application.target_case_id}"`);}
 if(d.original_cash){const original=d.original_cash;facts+=`<p>已查明原误记：${E(original.account)} · ${E(original.reference)} · ${E(original.business_date)} · ${money(original.amount_cents)} 元。</p>`+(o.values.amount_cents?`<p>批准后正确重记：${E(d.corrected_account_name)} · ${E(o.values.reference)} · ${money(o.values.amount_cents)} 元。</p>`:'<p>正确到账为零：仅追加原误记冲正，不生成零元收款，也不表示实际退款。</p>')+(o.values.allocations?.length?table(['正确分配的原业务','金额（元）'],o.values.allocations.map(a=>[E(d.source_cases.find(s=>s.id===a.source_case_id)?.number||'原单'),money(a.amount_cents)])):'');}
 if(d.stored_request)facts+=`<p>本金更正差额：${money(d.stored_request.corrected_amount_cents-d.stored_request.original_amount_cents)} 元；本次当前占额：${money(d.stored_request.status==='reserved'?d.stored_request.reserved_cents:0)} 元。已消费、已抵用和实际退款保留原始记录。</p>`;
 if(d.fee_correction_request)facts+=`<p>原续会费同额更正：${money(d.fee_correction_request.amount_cents)} 元，原到账日 ${E(d.fee_correction_request.business_date)}。会员、会期、等级及权益保持原记录；这里不登记实际退款。</p>`+(d.fee_correction_request.refunded_fee_id?'<p>原续会费已经实际退款；该笔退款的账户、凭证和会期作废记录继续保留。</p>':'');
 if(d.bundle_correction){const x=d.bundle_correction;facts+=`<p>原充值组合：本次将有效 ${x.original_shares} 份更正为 ${x.corrected_shares} 份，原发行记录保留。以下赠品按原规则一并更正，有效期不延长。</p>`+table(['原赠品','每份单位','单位差额','原到期日'],x.components.map(p=>[E(p.name),number(p.units_per_share)+' '+E(p.unit_label),number(p.delta_units)+' '+E(p.unit_label),E(p.expires_on)]));}
 if(d.partial_correction){const x=d.partial_correction;facts+=`<p>已经真实退款 ${money(x.refunded_cents)} 元保留原记录；剩余业务款由 ${money(x.original_net_cents)} 元更正为 ${money(x.corrected_net_cents)} 元。总原款记账冲回与剩余业务分配分开，不再次退款。</p>`+table(['原退款业务','实际退款（元）','原退款账户','凭证','日期'],x.refunds.map(r=>[E(r.number),money(r.amount_cents),E(r.account),E(r.reference),E(r.business_date)]));}
 if(d.return_target){const r=d.return_target;facts+=`<p>供应方原批准目标 ${money(r.original_amount_cents)} 元；当前有效应退目标 ${money(r.target_cents)} 元；当前净收款 ${money(r.received_cents)} 元。</p><p>超收应退 ${money(r.overpayment_cents||0)} 元；已批准退款占额 ${money(r.refund_reserved_cents||0)} 元。调整目标不代替实际退款。</p>`+table(['修订','原目标（元）','新目标（元）','修订时净收（元）'],r.revisions.map(x=>[String(x.revision),money(x.original_amount_cents),money(x.amount_cents),money(x.received_cents)]));}
 if(d.supplier_refund)facts+=`<p>本次按原收款退回：${money(d.supplier_refund.amount_cents)} 元；原账户 ${E(d.supplier_refund_account_name||'由获权财务核对')}。须核对已实际退款凭据后登记。</p>`;
 if(d.return_source){const r=d.return_source;facts+=`<p>经核对供应方：${E(r.supplier_name)}</p><p>实际退货：${E(r.item_name)} · ${number(r.quantity_milli/1000)} ${E(r.unit)}，原成本 ${money(r.value_cents)} 元。</p>`+b('open','查看原实物退货凭据',`data-route="case/${r.case_id}"`);}
 if(o.values.actual_business_date&&o.values.amount_cents>0)facts+=`<p>明确更正后的真实到账日：${E(o.values.actual_business_date)}</p>`;
 if(d.statement)facts+=`<p>${E(d.statement.starts_on)} 至 ${E(d.statement.ends_on)} · 账单版本 ${d.statement.revision}。账单不是实际收款凭证；晚到收款仍归原业务。</p>`;
 if(d.fee_correction_request)d.batches=(d.fee_correction_fact?[{id:null,kind:'fee_correction',amount_cents:d.fee_correction_request.amount_cents}]:[]);
 return heading('财务业务办理',d.case.title,buttons.join('')+b('open','返回结算入口',`data-route="business-finance${d.case.customer_id?'/'+d.case.customer_id:''}"`))+panel('冻结申请与原款',facts)+(d.lines?panel('冻结逐单客户余额',table(['原单','冻结应收','本账单已分配'],d.lines.map(l=>[E(l.snapshot.number),money(l.due_cents),money(d.allocations.filter(a=>a.statement_line_id===l.id).reduce((n,a)=>n+a.amount_cents,0))]))):'')+panel(d.fee_correction_request?'原会费登记更正事实':'资金记录与原单分配',table(['批次','记录金额','逐单分配'],d.batches.map(t=>[E({collection:'实际收款',correction_reverse:'原误记反向调整',correction_record:'正确重记',supplier_refund:'供应方原款实际退款',fee_correction:'已追加同额登记更正（非退款）'}[t.kind]),money(t.amount_cents),d.allocations.filter(a=>a.batch_id===t.id).map(a=>`${money(a.amount_cents)} 元 ${b('open','原业务',`data-route="case/${a.case_id}"`)}`).join('<br>')])) )+panel('本次凭据',`${businessFinanceFront()?b('upload','上传本次凭据','','primary'):''}${fileList(source.files)}`)+panel('责任与待办',table(['事项','负责人','状态'],source.tasks.map(t=>[E(t.title),E(t.assignee_name||t.assignee_id),E({open:'待办理',done:'已完成',cancelled:'已结束'}[t.status]||t.status)])))+panel('办理记录',table(['时间','办理事实'],d.events.map(e=>[time(e.occurred_at),E(e.reason)])));
}
async function businessFinanceCreate(key,id){
 if(key==='fee_correction')return businessFinanceFeeCorrection();
 if(key==='other_return_adjust')return businessFinanceReturnAdjust();
 if(key==='other_return_refund')return businessFinanceSupplierRefund();
 const context=state.businessFinanceCustomer,fields=[],initial={},request_id=requestKey();let advance,receipts,targets=[];
 if(['advance','advance_apply','advance_refund'].includes(key))fields.push(F('amount','本次金额（元）','money'));
 if(key==='advance_apply'){advance=context.advances.find(a=>a.id===Number(id));targets=context.sources;if(!targets.length)throw new Error('本客户没有通过原业务关口的可抵用客户应收。');fields.push(F('source','原单及当前未结','select',true,targets.map(s=>`${s.number} · ${money(s.due_cents)}元`)));}
 if(key==='advance_refund')advance=context.advances.find(a=>a.id===Number(id));
 if(key==='statement'){fields.push(F('starts_on','月结起始日期','date'),F('ends_on','月结截止日期','date'));initial.starts_on=day().slice(0,8)+'01';initial.ends_on=day();}
 if(['correction','stored_correction'].includes(key)){
  receipts=(await api('/api/business-finance/receipts?customer_id='+context.customerId)).items.filter(r=>key==='stored_correction'?!!r.source_kind&&r.source_kind!=='membership_fee':!r.source_kind);if(!receipts.length)throw new Error(key==='stored_correction'?'暂无可更正的本店独立预收或会员充值。组合原款按原完整份额一并更正本金和赠品。':'暂无可更正的本店业务收款；在办退款或更正须先完成或取消。');
  targets=[...context.sources];for(const r of receipts)for(const s of r.sources)if(!targets.some(t=>t.case_id===s.case_id))targets.push({case_id:s.case_id,number:s.number,due_cents:0});
  fields.push(F('original','已查明误记的原收款','select',true,receipts.map(businessFinanceReceiptLabel)),F('actual_business_date','正确真实到账日期（空白保留原日期）','date',false),F('account_id','正确实际账户（零元撤错可留空）','account',false),F('reference','正确银行流水或收款凭证号（零元可留空）','text',false));
  if(key==='stored_correction')fields.push(F('amount','正确原收款金额（元，完全误记填0）','money_zero'));
  else for(const t of targets){fields.push(F('allocation_'+t.case_id,'更正后剩余分配：'+t.number+'（元，未分配填0）','money_zero'));initial['allocation_'+t.case_id]='0';}
 }
 fields.push(F('reason',['correction','stored_correction'].includes(key)?'误记原因及正确收款依据':'客户申请及本次办理原因','textarea'));
 await formDialog(businessFinanceNames[key],fields,initial,async v=>{let values={};if(v.amount&&key!=='stored_correction')values.amount_cents=groupFen(v.amount);
  if(advance)Object.assign(values,{advance_id:advance.id,advance_version:advance.version});
  if(key==='advance_apply'){const t=targets.find(s=>v.source===`${s.number} · ${money(s.due_cents)}元`);Object.assign(values,{target_case_id:t.case_id,target_version:t.version});}
  if(key==='statement')values={starts_on:v.starts_on,ends_on:v.ends_on};
  if(['correction','stored_correction'].includes(key)){const r=receipts.find(r=>v.original===businessFinanceReceiptLabel(r));if(key==='correction'){const allocations=targets.map(t=>({source_case_id:t.case_id,amount_cents:businessFinanceZero(v['allocation_'+t.case_id])})).filter(a=>a.amount_cents>0);values={original_cash_id:r.cash_id,amount_cents:allocations.reduce((n,a)=>n+a.amount_cents,0)+(r.refunded_cents||0),allocations,allocation_basis:'remaining_after_refunds'};}else values={original_cash_id:r.cash_id,amount_cents:businessFinanceZero(v.amount),source_version:r.source_version,...(r.bundle_purchase_id?{bundle_purchase_id:r.bundle_purchase_id}:{})};if(values.amount_cents)Object.assign(values,{account_id:v.account_id,reference:v.reference});if(v.actual_business_date)values.actual_business_date=v.actual_business_date;}
  const d=await api('/api/business-finance/orders',{method:'POST',body:{request_id,customer_id:context.customerId,purpose:key,values,reason:v.reason}});go('business-finance-order/'+d.case.id);
 },{notice:key==='correction'?'只更正录入错误。填写各原业务在扣除已实际退款后正确的剩余分配；系统自动加回已退款，得到正确总原款。剩余分配全部为0且没有旧退款才表示完全未到账。原退款账户和事实始终保留，不再次退款。':key==='stored_correction'?'仅更正录入错误。系统保留原现金及原分配，追加冲正和可选正确重记；正确金额填0表示完全未到账。已消费或已批准占用的本金不会被抹除。组合须为原每份本金的整数倍，逐项同步原赠品，保留原到期日。这里不登记实际退款。':'申请先保留来源及理由；抵用、退款和月结须独立复核，真实到账须由财务凭据确认。'});
}
async function businessFinanceFeeCorrection(){
 if(!state.catalog?.capabilities?.member_fee_corrections)throw new Error('本次服务尚未启用续会费登记更正，请刷新后核对。');
 const context=state.businessFinanceCustomer,request_id=requestKey();
 const rows=(await api('/api/business-finance/receipts?customer_id='+context.customerId)).items.filter(r=>r.source_kind==='membership_fee');
 if(!rows.length)throw new Error('暂无可更正的本店正数续会费；在办原款更正或实际退款须先完成或取消。');
 await formDialog('续会费同额登记更正',[F('original','已核对的原续会费','select',true,rows.map(businessFinanceReceiptLabel)),F('account_id','正确的原收款账户','account'),F('reference','正确银行流水或收款凭证号'),F('reason','登记错误及核对依据','textarea')],{},async v=>{
  const source=rows.find(r=>businessFinanceReceiptLabel(r)===v.original);
  const result=await api('/api/business-finance/orders',{method:'POST',body:{request_id,customer_id:context.customerId,purpose:'fee_correction',values:{fee_id:source.fee_id,original_cash_id:source.cash_id,source_version:source.source_version,account_id:v.account_id,reference:v.reference},reason:v.reason}});
  go('business-finance-order/'+result.case.id);
 },{notice:'仅更正原会费账户、凭证和证据。金额、会员、会期、等级、权益及原到账日不变。上传本次凭据后由另一位主管批准，财务追加登记更正；已有真实退款继续保留，不再退款。'});
}
async function businessFinanceReturnAdjust(){
 const d=state.businessFinanceOrder,r=d.return_target,request_id=requestKey();
 await formDialog('供应方应退目标更正',[F('amount','新的应退目标总额（元）','money_zero'),F('reason','供应方确认及目标更正依据','textarea')],{amount:money(r.target_cents).replaceAll(',','')},async v=>{const result=await api('/api/business-finance/orders',{method:'POST',body:{request_id,customer_id:null,purpose:'other_return_adjust',values:{receivable_id:r.receivable_id,source_version:d.case.version,amount_cents:businessFinanceZero(v.amount)},reason:v.reason}});go('business-finance-order/'+result.case.id);},{notice:'保留原批准目标，独立复核后追加修订。新目标低于净收款时形成供应方超收应退，另行申请并确认原款实际退款。已有批准退款须先完成或取消。'});
}
async function businessFinanceSupplierRefund(){
 const d=state.businessFinanceOrder,r=d.return_target,sources=d.supplier_refund_sources||[],request_id=requestKey();
 if(!sources.length)throw new Error('没有未占用的本店供应方原款可退，请刷新核对在办退款。');
 const label=s=>`${s.account_name} · ${s.reference} · 本笔可退${money(s.available_cents)}元`;
 await formDialog('供应方超收原款退款',[F('source','本店原实际收款','select',true,sources.map(label)),F('amount','本次申请退回金额（元）','money'),F('reason','供应方确认与原款退款依据','textarea')],{},async v=>{const source=sources.find(s=>label(s)===v.source);const result=await api('/api/business-finance/orders',{method:'POST',body:{request_id,customer_id:null,purpose:'other_return_refund',values:{receivable_id:r.receivable_id,original_payment_id:source.original_payment_id,source_version:d.case.version,amount_cents:groupFen(v.amount)},reason:v.reason}});go('business-finance-order/'+result.case.id);},{notice:'独立批准后占用超收待退额度。财务按本笔原账户实际退回并上传凭据；不会自动向银行转账，不能用记账冲正代替真实退款。'});
}
async function businessFinanceOther(){
 const [source,suppliers]=await Promise.all([api('/api/business-finance/other-returns'),procurementAll('/api/masters/suppliers?active=true')]);const sources=source.items;
 if(!sources.length)throw new Error('没有已实际执行且尚未建立应收的其他入库原单退货。');const request_id=requestKey();
 await formDialog('其他入库退货应收',[F('source','已实际执行的原退货','select',true,sources.map(s=>`${s.number} · ${s.item_name} · 原成本${money(s.value_cents)}元`)),F('supplier','经核对的原供应方','select',true,suppliers.map(s=>s.name)),F('amount','明确应收退货款（元）','money'),F('reason','原供应方及应收依据','textarea')],{},async v=>{const s=sources.find(s=>v.source===`${s.number} · ${s.item_name} · 原成本${money(s.value_cents)}元`),supplier=suppliers.find(s=>s.name===v.supplier);const d=await api('/api/business-finance/orders',{method:'POST',body:{request_id,customer_id:null,purpose:'other_return',values:{stock_move_id:s.stock_move_id,source_version:s.source_version,supplier_id:supplier.id,amount_cents:groupFen(v.amount)},reason:v.reason}});go('business-finance-order/'+d.case.id);},{notice:'实物退货、原成本和待收金额分别留存。独立复核后仍须财务记录真实到账，申请不生成现金。'});
}
async function businessFinanceAction(key){
 const d=state.businessFinanceOrder,o=d.order,fields=[],initial={},cash=['execute','collect'].includes(key)&&['advance','advance_refund','statement','other_return','other_return_refund'].includes(o.purpose),sources=new Set();
 if(['approve','execute','collect'].includes(key))fields.push(F('evidence_id','本次批准／实际收退款凭据','file'));
 if(cash)fields.push(F('account_id','本店实际收退款账户','account'),F('reference','真实银行流水或收款凭证号'));
 if(cash&&o.purpose==='other_return_refund')initial.account_id=o.values.original_account_id;
 if(key==='collect'&&o.purpose==='statement')for(const l of d.lines){fields.push(F('allocation_'+l.source_case_id,l.snapshot.number+' 本次分配（元）','money_zero'));initial['allocation_'+l.source_case_id]=money(l.due_cents-d.allocations.filter(a=>a.statement_line_id===l.id).reduce((n,a)=>n+a.amount_cents,0)).replaceAll(',','');sources.add(l.source_case_id);}
 if(key==='collect'&&o.purpose==='other_return')fields.push(F('amount','本次实际收到退货款（元）','money'));
 if(d.application?.target_case_id)sources.add(d.application.target_case_id);
 if(o.purpose==='correction'){for(const a of o.values.allocations)sources.add(a.source_case_id);for(const s of d.source_cases||[])sources.add(s.id);}
 if(['other_return_adjust','other_return_refund'].includes(o.purpose))sources.add(o.values.source_case_id);
 fields.push(F('reason','本人核对的事实与依据','textarea'));const request_id=requestKey(),source_versions={};
 if(['approve','execute','collect'].includes(key))for(const id of sources){const source=await api('/api/flow/cases/'+id);source_versions[String(id)]=source.version;}
 await formDialog({approve:'独立复核批准',execute:'确认批准内容及实际办理',collect:'登记真实到账并分配',cancel:'取消未完成办理',reject:'退回申请',recalculate:'重算并追加账单版本'}[key],fields,initial,async v=>{const values={reason:v.reason};if(v.evidence_id)values.evidence_id=v.evidence_id;if(cash)Object.assign(values,{account_id:v.account_id,reference:v.reference});if(v.amount)values.amount_cents=groupFen(v.amount);
  if(['approve','execute','collect'].includes(key))values.source_versions=source_versions;
  if(key==='collect'&&o.purpose==='statement'){values.allocations=d.lines.map(l=>({source_case_id:l.source_case_id,amount_cents:businessFinanceZero(v['allocation_'+l.source_case_id])})).filter(a=>a.amount_cents>0);values.amount_cents=values.allocations.reduce((n,a)=>n+a.amount_cents,0);}
  const result=await api(`/api/business-finance/orders/${d.case.id}/actions/${key}`,{method:'POST',body:{request_id,version:o.version,case_version:d.case.version,values}});if(key==='recalculate')go('business-finance-order/'+result.case.id);
 },{caseId:d.case.id,notice:key==='recalculate'?'原账单保留，按当前原业务追加新版本，已经收到的现金保持原来源。':cash?'请在核对真实到账或退款完成后登记。多原单分配合计对应一笔实际现金。':key==='approve'?'须与申请人不同的主管复核。预收申请批准后占用原款，未完成可取消释放。':'系统重新校验本店原客户、业务前置条件、版本及原款余额。'});
}
function clearBusinessFinanceSession(){for(const key of ['businessFinanceCustomer','businessFinanceOrder'])delete state[key];}
