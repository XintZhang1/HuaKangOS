'use strict';
// Group identities are shared; every posting is tied to a local source case.
const groupPurpose={correction:'原充值误记更正（非退款）',topup:'本金充值',reserve:'占用本金',capture:'本金核销',release:'释放占额',refund:'本金退款',reverse:'核销冲正',refund_request:'申请本金退款',refund_approve:'批准并占用退款本金',refund_reject:'退回退款申请',refund_cancel:'撤销退款申请'};
const groupRequester=()=>canWrite()&&['admin','finance','service','customer_service'].includes(state.user.role);
const groupApprover=()=>canWrite()&&['admin','manager'].includes(state.user.role);
const groupFinance=()=>canWrite()&&['admin','finance'].includes(state.user.role);
function groupFen(value){return moneyFen(value,{label:'金额'});}
async function groupPage(customerId,caseId){
 if(state.store==='all')return heading('集团会员')+storeNotice()+'<div class="notice">请选择办理门店查看会员权益及本店结算记录。集团合并往来请在数据可视化中查看。</div>';
 if(!customerId){const customers=await api(`/api/flow/master/customers?q=${encodeURIComponent(state.q)}&page=${state.page}`);return heading('集团会员','从本店客户档案识别集团会员，跨店业务历史按授权保留。',(full()?b('open','本店会员对账','data-route="group-reconciliation"'):'')+(groupApprover()?b('open','本店权益规则','data-route="benefits"'):''))+searchBar()+panel('本店客户',table(['客户','联系电话',''],customers.items.map(c=>[E(c.name),E(c.phone),b('open','查询会员',`data-route="group/${c.id}"`)]))+pager(customers.total));}
 const response=await api(`/api/group/members?customer_id=${customerId}`);const source=caseId?await api(`/api/flow/cases/${caseId}`):null;
 if(source&&source.customer_id!==customerId)throw new Error('来源业务与所选客户不一致。');
 const data=response.member?await api(`/api/group/members/${response.member.id}`):null;
 state.group={customerId,caseId,source,identityId:response.identity_id,customer:response.customer,detail:data};
 let html=heading('集团会员',response.customer?.name||'本店客户',b('open','返回客户列表','data-route="group"'));
 if(source)html+=panel('办理来源',`<div class="spread"><span>${E(source.number)} · ${E(source.kind_label)}</span>${b('open','查看业务及上传凭据',`data-route="case/${source.id}"`)}</div><p>本次资金或权益操作关联该业务，单据的服务履约与客户交接仍须分别确认。</p>`);
 if(!response.identity_id)return html+panel('确认集团身份','<p>同一电话可能对应不同客户。请先核对本人信息，再选择已有集团身份或新建身份。</p>'+ (canWrite()?b('group-link','核对并关联集团身份','','primary'):''));
 if(!data)return html+panel('会员开通','<p>本店客户已关联集团身份，尚未开通集团会员。</p>'+(canWrite()?b('group-issue','开通集团会员','','primary'):''));
 html+=panel('积分、赠送金额、券与套餐',b('open','查询集团权益与办理结算',`data-route="benefits/${customerId}${caseId?'/'+caseId:''}"`));
 const m=data.member;
 html+=`<div class="kpis"><div class="kpi"><div class="label">集团会员号</div><div class="value-text">${E(m.number)}</div></div><div class="kpi"><div class="label">本金余额（元）</div><div class="value">${money(m.balance_cents)}</div></div><div class="kpi"><div class="label">已占用（元）</div><div class="value">${money(m.reserved_cents)}</div></div><div class="kpi"><div class="label">可用本金（元）</div><div class="value">${money(m.available_cents)}</div></div></div>`;
 if(source&&groupFinance()){const service=source.kind==='repair'&&['settling','credit_open'].includes(source.state)&&([3,4].includes(source.flow_version)||source.data.payer==='客户');html+=actionPanel(b('group-action','登记集团本金充值','data-key="topup"')+(service?' '+b('group-action','占用本金用于本单','data-key="reserve"','primary'):''));}
 if(!source)html+='<div class="notice">充值或结算请从对应业务单的“集团会员”入口办理，以便关联客户、授权及实际到账凭据。</div>';
 html+=panel('本店本金占用',table(['来源业务','金额（元）','状态','操作'],data.reservations.map(r=>[b('open','查看业务',`data-route="case/${r.case_id}"`,'link'),money(r.amount_cents),E({reserved:'待核销',captured:'已核销',released:'已释放'}[r.status]),r.status==='reserved'&&groupFinance()?`<div class="row">${b('group-action','确认核销',`data-key="capture" data-id="${r.id}"`,'primary')}${b('group-action','释放占额',`data-key="release" data-id="${r.id}"`)}</div>`:'—'])));
 const refunds=data.refund_requests||[];
 html+=panel('本金退款申请',table(['申请','金额（元）','状态','操作'],refunds.map(r=>{let buttons='';if(['requested','pending'].includes(r.status)&&groupApprover())buttons+=b('group-action','批准并占额',`data-key="refund_approve" data-id="${r.id}"`,'primary')+b('group-action','退回',`data-key="refund_reject" data-id="${r.id}"`);if(r.status==='approved'&&groupFinance())buttons+=b('group-action','登记实际退款',`data-key="refund" data-id="${r.id}"`,'primary');if(['requested','pending','approved'].includes(r.status)&&canWrite()&&(groupApprover()||r.requested_by===state.user.id))buttons+=b('group-action','撤销',`data-key="refund_cancel" data-id="${r.id}"`);return [E(r.id),money(r.amount_cents),E({requested:'待审批',pending:'待审批',approved:'已占额待退款',rejected:'已退回',cancelled:'已撤销',executed:'已退款',completed:'已退款'}[r.status]||r.status),`<div class="row">${buttons||'—'}</div>`];})));
 const effectiveTopups=data.effective_topups||[];
 const revised=effectiveTopups.filter(t=>t.corrected);
 if(revised.length)html+=panel('更正后的有效原款',table(['原充值记录','当前有效原款（元）','原款尚可申请退款（元）','当前账户'],revised.map(t=>[E(t.original_id),money(t.effective_amount_cents),money(t.available_refund_cents),t.account_name?E(t.account_name):t.effective_amount_cents===0?'已撤销误记':'由获权财务核对'])));
 html+=panel('本店权益流水',table(['发生时间','类型','本金变化（元）','来源业务','操作'],data.entries.map(e=>{const effective=effectiveTopups.find(t=>t.original_id===e.id);return [time(e.occurred_at),E(groupPurpose[e.purpose]),money(e.amount_cents),b('open','查看业务',`data-route="case/${e.case_id}"`,'link'),((e.purpose==='topup'&&groupRequester()&&(!effective||effective.direct_refund_allowed&&effective.available_refund_cents>0))||(e.purpose==='capture'&&groupFinance()))?b('group-action',e.purpose==='topup'?'申请原款退款':'核销冲正',`data-key="${e.purpose==='topup'?'refund_request':'reverse'}" data-id="${e.id}"`):'—'];})));
 return html+'<p class="muted">这里显示集团本金与本店最近100条记录。门店原有储值单独保留；积分、赠送、券和套餐在集团权益模块分别记账。</p>';
}
async function groupLinkDialog(){
 const context=state.group,phone=context.customer?.phone;if(!phone)throw new Error('请先在本店客户档案填写并核对联系电话。');
 const matches=await api('/api/group/identities?kind=customer&q='+encodeURIComponent(phone));const request_id=requestKey();
 const options=[{id:'new',label:'新建独立集团客户身份'},...matches.items.map(m=>({id:String(m.id),label:`${m.name} · 集团身份 ${m.id}`}))];
 await formDialog('核对客户身份',[{key:'identity',label:'关联结果',type:'select',required:true,options:options.map(o=>o.id)},{key:'confirmed',label:'已核对客户身份与本人确认结果',type:'bool',required:true}],{},async v=>{if(!v.confirmed)throw new Error('请先核对身份并确认，不能仅凭电话号码合并客户。');await api('/api/group/identities/link',{method:'POST',body:{request_id,kind:'customer',local_id:context.customerId,identity_id:v.identity==='new'?null:Number(v.identity)}});},{notice:options.map(o=>`${o.id}：${o.label}`).join('；')});
}
async function groupIssue(){const request_id=requestKey(),context=state.group;await formDialog('开通集团会员',[],{},()=>api('/api/group/members',{method:'POST',body:{request_id,identity_id:context.identityId}}),{notice:'开通会员只建立身份和本金账，不产生充值或消费。'});}
async function groupAction(key,id){
 const context=state.group,m=context.detail.member;let entry=null,reservation=null,refund=null;
 if(['capture','release'].includes(key))reservation=context.detail.reservations.find(r=>r.id===id);
 if(['refund_request','reverse'].includes(key))entry=context.detail.entries.find(r=>r.id===id);
 if(['refund','refund_approve','refund_reject','refund_cancel'].includes(key))refund=(context.detail.refund_requests||[]).find(r=>r.id===id);
 const caseId=refund?.case_id||reservation?.case_id||entry?.case_id||context.caseId;if(!caseId)throw new Error('请从来源业务进入办理。');
 const source=await api(`/api/flow/cases/${caseId}`),request_id=requestKey(),fields=[];
 if(['topup','reserve','refund_request','reverse'].includes(key))fields.push(F('amount','金额（元）','money'));
 if(['topup','refund'].includes(key))fields.push(F('account_id','实际收退款账户','account'),F('reference','银行流水号或凭证号'));
 if(!['release','refund_approve','refund_reject','refund_cancel'].includes(key))fields.push({...F('evidence_id','本单实际凭据','file'),file_category:'evidence'});
 if(['refund_request','reverse','release','refund_approve','refund_reject','refund_cancel'].includes(key))fields.push(F('reason','办理原因','textarea'));
 const original=entry||(refund?context.detail.entries.find(e=>e.id===refund.original_id):null);
 const effective=(context.detail.effective_topups||[]).find(t=>t.original_id===(entry?.id||refund?.original_id));
 const initial=original?{amount:money(effective&&key==='refund_request'?effective.available_refund_cents:Math.abs(original.amount_cents)).replaceAll(',',''),account_id:effective?.account_id||original.account_id}:effective?{account_id:effective.account_id}:{};
 const currentNotice=effective?.corrected?`原充值已有误记更正：当前有效原款 ${money(effective.effective_amount_cents)} 元，${effective.account_name?'当前原账户 '+effective.account_name+'；':''}已消费和实际退款仍保留原记录。`:'';
 await formDialog(groupPurpose[key],fields,initial,v=>{const values={case_version:source.version};if(v.amount!==undefined)values.amount_cents=groupFen(v.amount);if(['topup','reserve'].includes(key))values.case_id=caseId;if(reservation)Object.assign(values,{reservation_id:reservation.id,reservation_version:reservation.version});if(entry)values.original_id=entry.id;if(refund)Object.assign(values,{refund_request_id:refund.id,refund_request_version:refund.version});for(const k of ['account_id','reference','evidence_id','reason'])if(v[k]!==undefined)values[k]=v[k];return api(`/api/group/members/${m.id}/actions/${key}`,{method:'POST',body:{request_id,version:m.version,values}});},{caseId,notice:source.number+' · '+currentNotice+(refund?`本次申请退款 ${money(refund.amount_cents)} 元。`:'')+(['topup','refund'].includes(key)?'仅在核对真实到账或退款凭据后确认。系统不会执行银行转账。':key==='capture'?'确认本次实际核销，系统同时扣减集团本金并关联本单结算。':key==='refund_approve'?'批准后先占用本金，防止待退款金额再次消费。':'本次办理保留原记录，不覆盖历史。')});
}
async function groupReconciliationPage(){if(state.store==='all')return heading('会员往来对账')+storeNotice();const d=await api('/api/group/reconciliation');return heading('本店会员往来对账','正数为应收、负数为应付；这是内部往来记账，实际划款和结清尚需财务核对。')+panel('往来余额',table(['集团应收（元）','门店应收（元）','配对差额（元）'],[[money(d.center_receivable_cents),money(d.store_receivable_cents),money(d.clearing_sum_cents)]]))+panel('对应权益流水',table(['记录','类型','变动（元）','来源'],d.rows.map(r=>[E(r.id),E(groupPurpose[r.purpose]),money(r.amount_cents),b('open','查看业务',`data-route="case/${r.case_id}"`)])));}
