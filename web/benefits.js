'use strict';
const benefitNames={bonus:'赠送金额',points:'积分',coupon:'消费券',package:'作业次数套餐'};
const benefitActions={correction:'原组合误记更正',purchase:'购买权益',grant:'赠送权益',reserve:'占用权益',capture:'确认核销',release:'释放占额',reverse:'撤销原核销',adjust:'调减积分',exchange:'积分兑换券包',refund_request:'申请原款退款',refund_approve:'批准并占额',refund_reject:'退回退款申请',refund_cancel:'撤销退款申请',refund:'登记实际退款'};
const benefitUnit=k=>({bonus:'分',points:'积分',coupon:'张',package:'次'}[k]);
function benefitNumber(value){const n=Number(value);if(!Number.isSafeInteger(n)||n<=0||n>100000000)throw new Error('权益数量必须为正整数，不能填小数。');return n;}
function benefitMoney(value){return String(value).trim()==='0'?0:groupFen(value);}
function currentBenefitRules(items){return items.filter(r=>r.issuer_store_id===Number(state.store)&&!items.some(x=>x.issuer_store_id===r.issuer_store_id&&x.code===r.code&&x.rule_version>r.rule_version));}
async function benefitsPage(customerId,caseId){
 if(state.store==='all')return heading('集团权益')+storeNotice();
 if(!customerId){
  state.benefits=null;
  const catalog=await api('/api/group/benefits/rules'),current=currentBenefitRules(catalog.items);
  return heading('集团权益','本店冻结规则；客户权益办理请从原会员和业务单进入。',b('open','选择客户','data-route="group"'))+
   panel('本店可发行规则',(groupApprover()?b('benefit-rule','新增冻结规则版本'):'')+
    table(['名称／编码／版本','发行条件','使用与结算'],current.map(r=>[
     `${E(r.name)} · ${E(r.code)} · ${r.rule_version}`,
     `${E(benefitNames[r.kind]||r.kind)} · 每${benefitUnit(r.kind)}抵 ${money(r.credit_cents_per_unit)} 元；售价 ${money(r.sale_cents_per_unit)} 元；有效 ${r.validity_days} 天${r.kind==='package'?`；作业编码 ${E(r.service_code)}`:''}`,
     `适用门店 ${E(r.allowed_store_ids.join('、'))}；${E({group:'集团',service_store:'履约门店'}[r.discount_bearer]||r.discount_bearer||'按当前岗位查看承担方')}${r.settlement_cents_per_unit==null?'':`承担差额；每单位内部结算 ${money(r.settlement_cents_per_unit)} 元`}`
    ])));
 }
 const d=await api(`/api/group/benefits/members?customer_id=${customerId}`),catalog=await api('/api/group/benefits/rules');
 const source=caseId?await api(`/api/flow/cases/${caseId}`):null;if(source&&source.customer_id!==customerId)throw new Error('办理来源与当前客户不一致。');
 state.benefits={customerId,caseId,source,detail:d,rules:catalog.items};
 let html=heading('集团权益',d.customer?.name||'本店客户',b('open','查看会员本金',`data-route="group/${customerId}${caseId?'/'+caseId:''}"`));
 if(!d.member)return html+panel('尚未开通集团会员',b('open','核对身份与开通会员',`data-route="group/${customerId}${caseId?'/'+caseId:''}"`));
 if(source)html+=panel('本次业务',`<strong>${E(source.number)}</strong> ${b('open','查看业务与凭据',`data-route="case/${source.id}"`)}<p>券、积分、赠送金额和套餐各自记账，仅抵本单客户承担的费用。</p>`);
 else html+='<div class="notice">购买、赠送、积分调整及占额须从对应业务单进入；已存在的核销、释放和退款可沿原记录继续办理。</div>';
 const finance=groupFinance(),manager=groupApprover();
 html+=panel('会员现有权益',table(['权益与版本','可用／占用','有效期','操作'],d.wallets.map(w=>{const r=w.rule,unit=benefitUnit(r.kind);let buttons=w.bundle_origin&&w.source_case_id?b('open','原组合条件',`data-route="recharge-bundle-order/${w.source_case_id}"`):'';if(finance&&source&&!w.expired&&w.usable_in_store&&w.available_units>0)buttons+=b('benefit-action','用于本单',`data-key="reserve" data-id="${w.id}"`,'primary');if(manager&&source&&r.kind==='points'&&!w.bundle_origin&&w.available_units>0)buttons+=b('benefit-action','调减积分',`data-key="adjust" data-id="${w.id}"`);if(finance&&source&&r.kind==='points'&&w.available_units>0)buttons+=b('benefit-action','积分兑换',`data-key="exchange" data-id="${w.id}"`);if(groupRequester()&&w.source_case_id&&w.source_kind==='purchase'&&r.refund_policy!=='none'&&w.available_units>0)buttons+=b('benefit-action','申请退款',`data-key="refund_request" data-id="${w.id}"`);return [`<strong>${E(r.name)}</strong><br><span class="muted">${E(benefitNames[r.kind])} · 规则 ${r.rule_version} · 每${unit}抵 ${money(r.credit_cents_per_unit)} 元</span>`,`${w.available_units} / ${w.reserved_units} ${unit}`,`${E(w.expires_on)}${w.expired?' · 已过期':''}${!w.usable_in_store?' · 本店不适用':''}`,`<div class="row">${buttons||'—'}</div>`];})));
 html+=panel('本店待核销',table(['占额','单位与抵扣','状态','操作'],d.reservations.map(r=>[E(r.id),`${r.units} 单位 / ${money(r.credit_cents)} 元`,E({reserved:'待核销',captured:'已核销',released:'已释放'}[r.status]),r.status==='reserved'&&finance?`<div class="row">${b('benefit-action','确认核销',`data-key="capture" data-id="${r.id}"`,'primary')}${b('benefit-action','释放占额',`data-key="release" data-id="${r.id}"`)}</div>`:'—'])));
 html+=panel('原款退款',table(['申请','份数','状态','操作'],d.refunds.map(r=>{let buttons='';if(r.status==='requested'&&manager)buttons+=b('benefit-action','批准并占额',`data-key="refund_approve" data-id="${r.id}"`)+b('benefit-action','退回',`data-key="refund_reject" data-id="${r.id}"`);if(r.status==='approved'&&finance)buttons+=b('benefit-action','登记实际退款',`data-key="refund" data-id="${r.id}"`,'primary');if(['requested','approved'].includes(r.status)&&canWrite()&&(manager||r.requested_by===state.user.id))buttons+=b('benefit-action','撤销',`data-key="refund_cancel" data-id="${r.id}"`);return [E(r.id),r.units,E({requested:'待复核',approved:'已占额待退款',rejected:'已退回',cancelled:'已撤销',executed:'已退款'}[r.status]),`<div class="row">${buttons||'—'}</div>`];})));
 html+=panel('本店权益流水',table(['记录','动作','单位变化','本单抵扣（元）','操作'],d.entries.map(e=>[E(e.id),E(benefitActions[e.purpose]||{exchange_in:'兑换获得',exchange_out:'兑换扣减'}[e.purpose]||e.purpose),e.units,money(e.credit_cents),e.purpose==='capture'&&finance?b('benefit-action','原核销撤销',`data-key="reverse" data-id="${e.id}"`):'—'])));
 const current=currentBenefitRules(catalog.items);
 html+=panel('本店可发行规则',(manager?b('benefit-rule','新增冻结规则版本'):'')+table(['名称／版本','固定规则','办理'],current.map(r=>[`${E(r.name)} · ${r.rule_version}`,`每${benefitUnit(r.kind)}抵 ${money(r.credit_cents_per_unit)} 元；有效 ${r.validity_days} 天${r.kind==='package'?'<br>作业编码 '+E(r.service_code):''}`,source?`<div class="row">${finance&&r.sale_cents_per_unit>0?b('benefit-action',`购买（${money(r.sale_cents_per_unit)}元/份）`,`data-key="purchase" data-rule="${r.id}"`):''}${manager&&r.sale_cents_per_unit===0?b('benefit-action','赠送',`data-key="grant" data-rule="${r.id}"`):''}</div>`:'从业务单进入办理'])));
 return html+'<p class="muted">这里只显示本店最近100条记录。每批权益保留发行时的使用门店、兑换率、退款和内部结算规则；新版本不修改原批次。次数套餐仅用于对应已授权作业。</p>';
}
async function benefitAction(key,id,ruleId){
 const c=state.benefits,d=c.detail;let reservation=null,refund=null,entry=null,wallet=null;
 if(['capture','release'].includes(key))reservation=d.reservations.find(x=>x.id===id);
 if(['refund_approve','refund_reject','refund_cancel','refund'].includes(key))refund=d.refunds.find(x=>x.id===id);
 if(key==='reverse')entry=d.entries.find(x=>x.id===id);
 if(id)wallet=d.wallets.find(x=>x.id===(reservation?.wallet_id||refund?.wallet_id||entry?.wallet_id||id));
 const rule=ruleId?c.rules.find(x=>x.id===ruleId):wallet?.rule;
 const caseId=reservation?.case_id||refund?.case_id||entry?.case_id||(key==='refund_request'?wallet?.source_case_id:c.caseId);
 if(!caseId)throw new Error('请从正确的来源业务进入办理。');
 const source=await api(`/api/flow/cases/${caseId}`),request_id=requestKey(),fields=[];
 if(['purchase','grant','reserve','adjust','exchange','refund_request','reverse'].includes(key))fields.push(F('units',key==='adjust'?'调减积分数':key==='exchange'?'本次兑换扣除的积分':`数量（${benefitUnit(rule.kind)}）`,'int'));
 if(key==='exchange'){const targets=c.rules.filter(r=>r.issuer_store_id===Number(state.store)&&r.exchange_points_per_unit>0&&r.sale_cents_per_unit===0);if(!targets.length)throw new Error('本店尚未配置可兑换的券包规则。');fields.push(F('target_rule_id','兑换规则','select',true,targets.map(r=>String(r.id))));}
 if(['purchase','refund'].includes(key))fields.push(F('account_id','实际收退款账户','account'),F('reference','实际流水或凭证号'));
 if(!['release','refund_approve','refund_reject','refund_cancel'].includes(key))fields.push({...F('evidence_id','本单实际凭据','file'),file_category:'evidence'});
 fields.push(F('reason','办理依据与原因','textarea'));
 const notice=source.number+' · '+(rule?`${rule.name}：每${benefitUnit(rule.kind)}抵${money(rule.credit_cents_per_unit)}元；`:'')+(key==='exchange'?c.rules.filter(r=>r.exchange_points_per_unit>0&&r.sale_cents_per_unit===0).map(r=>`${r.id}：${r.name}，${r.exchange_points_per_unit}积分/份`).join('；'):key==='refund'?'金额按已批准份数和原购买单价自动计算，只能使用原账户。':'确认实际事实后办理；不会自动操作银行。');
 await formDialog(benefitActions[key],fields,{account_id:wallet?.account_id},v=>{const values={case_version:source.version,reason:v.reason};if(wallet)Object.assign(values,{wallet_id:wallet.id,wallet_version:wallet.version});if(['purchase','grant'].includes(key))values.rule_id=ruleId;if(['purchase','grant','reserve','adjust','exchange'].includes(key))values.case_id=caseId;if(v.units!==undefined)values.units=benefitNumber(v.units);if(reservation)Object.assign(values,{reservation_id:reservation.id,reservation_version:reservation.version});if(refund)Object.assign(values,{refund_id:refund.id,refund_version:refund.version});if(entry)values.original_id=entry.id;for(const k of ['account_id','reference','evidence_id','target_rule_id'])if(v[k]!==undefined)values[k]=k==='target_rule_id'?Number(v[k]):v[k];return api(`/api/group/benefits/members/${d.member.id}/actions/${key}`,{method:'POST',body:{request_id,version:d.member.version,values}});},{caseId,notice});
}
async function benefitRuleDialog(){
 const fields=[F('code','规则编码'),F('name','权益名称'),F('kind','独立权益种类','select',true,Object.keys(benefitNames)),F('stores','适用门店编号（逗号分隔）'),F('credit','每单位抵扣金额（元）','money'),F('settlement','每单位内部结算金额（元）','money'),F('sale','每份购买价格（元，赠金/积分填0）','money'),F('exchange_points_per_unit','每份兑换积分（0表示不可兑换）','int'),F('refund_policy','未用权益退款规则','select',true,['none','unused_before_expiry','unused_anytime']),F('discount_bearer','优惠差额承担方','select',true,['group','service_store']),F('validity_days','自发行日起有效天数','int'),F('service_code','次数套餐作业编码','text',false)];
 Object.assign(labels,benefitNames,{none:'不允许现金退款',unused_before_expiry:'未用且未过期可申请',unused_anytime:'未用份允许申请',group:'集团',service_store:'履约门店'});
 const request_id=requestKey();await formDialog('发布权益规则新版本',fields,{kind:'coupon',stores:String(state.store),credit:'10',settlement:'8',sale:'8',exchange_points_per_unit:0,refund_policy:'unused_before_expiry',discount_bearer:'service_store',validity_days:365,service_code:''},v=>api('/api/group/benefits/rules',{method:'POST',body:{request_id,values:{code:v.code,name:v.name,kind:v.kind,allowed_store_ids:v.stores.split(/[,，]/).map(x=>benefitNumber(x.trim())),credit_cents_per_unit:benefitMoney(v.credit),settlement_cents_per_unit:benefitMoney(v.settlement),sale_cents_per_unit:benefitMoney(v.sale),exchange_points_per_unit:Number(v.exchange_points_per_unit),refund_policy:v.refund_policy,discount_bearer:v.discount_bearer,validity_days:benefitNumber(v.validity_days),service_code:v.service_code||''}}}),{notice:'保存即冻结新版本。同编码再次发布会创建下一版本，原已发权益保持原规则。跨店规则仅集团管理员可发布。赠金单位为分，抵扣金额须填0.01元。门店：'+state.user.stores.map(s=>s.id+' '+s.name).join('；')});
}
