'use strict';
const rechargeBundleStates={pending:'待办理',draft:'待办理',approved:'已批准待退款',completed:'已完成',cancelled:'已撤销'};
const rechargeBundleKinds={bonus:'赠送金额',points:'积分',coupon:'消费券',package:'服务套餐'};
const rechargeBundlePolicies={whole_unused_before_expiry:'原批次赠品到期前退回完整份额',whole_unused_anytime:'允许过期后退回仍完整的原份额'};
const rechargeBundleFront=()=>canWrite()&&['admin','manager','finance','service','customer_service','sales','reception'].includes(state.user.role);
const rechargeBundleFinance=()=>canWrite()&&['admin','finance'].includes(state.user.role);
const rechargeBundleManager=()=>canWrite()&&['admin','manager'].includes(state.user.role);
const rechargeBundleLabel=r=>`${r.name} · ${r.code} · 版本${r.rule_version}`;
const rechargeBundleUnits=(kind,units)=>kind==='bonus'?`${money(units)}元赠送金额`:`${number(units)}${{points:'积分',coupon:'张券',package:'次服务'}[kind]}`;
function rechargeBundleTerms(rule){return `<p>${E(rule.mandatory_terms)}</p><p><strong>${E(rechargeBundlePolicies[rule.refund_policy])}</strong></p><p>本版本补充条款：${E(rule.refund_terms)}</p>`;}
function rechargeBundleRuleFacts(rule,shares=1){const stores=state.stores.filter(s=>rule.allowed_store_ids.includes(s.id)).map(s=>s.name).join('、');return `<p><strong>${E(rule.name)} · 冻结版本${rule.rule_version}</strong></p><p>每份实收 ${money(rule.principal_cents_per_share)} 元，全部存入集团通用本金。${shares>1?`本次${shares}份，本金合计 ${money(rule.principal_cents_per_share*shares)} 元。`:''}</p><p>发行及赠品适用门店：${E(stores)}</p>`+rule.components.map(c=>`<p>${E(rechargeBundleKinds[c.benefit_rule.kind])}：每份 ${rechargeBundleUnits(c.benefit_rule.kind,c.units_per_share)} · ${E(c.benefit_rule.name)} · 版本${c.benefit_rule.rule_version} · 自发行起${c.benefit_rule.validity_days}天${c.benefit_rule.discount_bearer?` · ${c.benefit_rule.discount_bearer==='group'?'集团承担优惠':'履约门店承担优惠'}`:''}</p>`).join('');}
function rechargeBundleOrderList(items){return panel('本店最近组合办理',table(['业务','状态','办理'],items.map(o=>[E(o.title),E(rechargeBundleStates[o.state]||o.state),b('open','查看待办与凭据',`data-route="recharge-bundle-order/${o.id}"`)])));}
async function rechargeBundlesPage(customerId){
 if(state.store==='all')return heading('会员充值组合套餐')+storeNotice();
 const orders=await api('/api/recharge-bundles/orders');
 const ruleButton=state.user.role==='admin'?b('open','配置冻结组合规则','data-route="recharge-bundle-rules"'):'';
 if(!customerId){const customers=await api(`/api/flow/master/customers?q=${encodeURIComponent(state.q)}&page=${state.page}`);return heading('会员充值组合套餐','',ruleButton)+searchBar()+panel('选择本店客户',table(['客户','联系电话','办理'],customers.items.map(c=>[E(c.name),E(c.phone),b('open','组合购买与退款',`data-route="recharge-bundles/${c.id}"`)]))+pager(customers.total))+rechargeBundleOrderList(orders.items);}
 const d=await api('/api/recharge-bundles/purchases?customer_id='+customerId);state.rechargeBundles={...d,customerId:Number(customerId)};
 let html=heading('会员充值组合套餐',d.customer.name,ruleButton+b('open','返回客户列表','data-route="recharge-bundles"')+b('open','集团本金与权益',`data-route="membership/${customerId}"`));
 if(!d.member)return html+panel('先确认集团会员身份','<p>组合购买前，请关联本店客户并开通集团会员。</p>'+b('open','核对并开通会员',`data-route="group/${customerId}"`));
 html+=panel('集团本金',`<p>可用本金 <strong>${money(d.member.available_cents)} 元</strong>；已占额 ${money(d.member.reserved_cents)} 元。组合本金与普通充值使用同一集团通用余额。</p>${rechargeBundleFront()?b('bundle-create','申请购买组合','data-key="purchase"','primary'):''}`);
 for(const p of d.items){html+=panel('原购买组合',rechargeBundleRuleFacts(p.rule,p.shares)+`<p>原登记 ${p.shares} 份，当前有效 ${p.effective_shares??p.shares} 份，已退 ${p.refunded_shares} 份，退款已占 ${p.reserved_refund_shares} 份。</p><p><strong>当前最多可退 ${p.refundable_shares} 个完整份额</strong>。实际批准前会重新核对本金、原批次赠品与期限。</p>`+p.components.map(c=>`<p>${E(c.name)}：余额 ${rechargeBundleUnits(c.kind,c.balance_units)}，占额 ${rechargeBundleUnits(c.kind,c.reserved_units)}；到期 ${E(c.expires_on)}。</p>`).join('')+rechargeBundleTerms(p.rule)+b('open','查看原收款和赠品发行',`data-route="recharge-bundle-order/${p.case_id}"`)+(rechargeBundleFront()&&p.refundable_shares>0?b('bundle-create','申请整份原路退款',`data-key="refund" data-id="${p.id}"`):''));}
 return html+rechargeBundleOrderList(orders.items.filter(o=>o.customer_id===Number(customerId)));
}
async function rechargeBundleOrderPage(id){
 if(state.store==='all')return heading('充值组合办理')+storeNotice();
 const [d,source]=await Promise.all([api('/api/recharge-bundles/orders/'+id),api('/api/flow/cases/'+id)]);state.rechargeBundleOrder=d;state.row=source;
 const o=d.order,buttons=[],assigned=key=>source.tasks.some(t=>t.key===key&&t.status==='open'&&(state.user.role==='admin'||t.assignee_id===state.user.id));
 if(o.purpose==='refund'&&o.status==='draft'&&rechargeBundleManager()&&o.requested_by!==state.user.id&&assigned('bundle_review'))buttons.push(b('bundle-action','独立复核整份退款','data-key="approve"','primary'),b('bundle-action','退回申请','data-key="reject"'));
 if((o.purpose==='purchase'&&o.status==='draft'||o.purpose==='refund'&&o.status==='approved')&&rechargeBundleFinance()&&assigned('bundle_execute'))buttons.push(b('bundle-action',o.purpose==='purchase'?'确认实际收款并发行':'确认原路退款并回收赠品','data-key="execute"','primary'));
 if(['draft','approved'].includes(o.status)&&rechargeBundleFront()&&(o.requested_by===state.user.id||rechargeBundleManager()))buttons.push(b('bundle-action','撤销未完成办理','data-key="cancel"'));
 let facts=`<p>${o.purpose==='purchase'?'购买组合':'原组合退款'} · ${E(rechargeBundleStates[o.status])} · 本次 ${o.values.shares} 份 · ${money(d.case.amount_cents)} 元。</p>`+rechargeBundleRuleFacts(d.rule,o.values.shares);
 if(d.purchase){const p=d.purchase;facts+=`<p>原登记 ${p.shares} 份，当前有效 ${p.effective_shares??p.shares} 份；集团可用本金 ${money(d.member.available_cents)} 元；原组合当前可新申请退款 ${p.refundable_shares} 整份。</p>`;if(p.original_account)facts+=`<p>原收款账户：${E(p.original_account.name)}；原真实凭证：${E(p.original_reference)}。</p>`;if(p.effective_account)facts+=`<p>当前有效原款 ${money(p.effective_principal_cents)} 元；退款原账户：${E(p.effective_account.name)}；有效凭证：${E(p.effective_reference)}。</p>`;facts+=p.components.map(c=>`<p>${E(c.name)}：原批次余额 ${rechargeBundleUnits(c.kind,c.balance_units)}，已占 ${rechargeBundleUnits(c.kind,c.reserved_units)}，到期 ${E(c.expires_on)}。</p>`).join('');}
 return heading('充值组合办理',d.case.title,buttons.join('')+b('open','返回客户组合',`data-route="recharge-bundles/${d.case.customer_id}"`))+panel('冻结组合与当前原批次',facts)+panel('已确认的退款条件',rechargeBundleTerms(d.rule))+panel('本单凭据',`${rechargeBundleFront()?b('upload','上传本次凭据','','primary'):''}${fileList(source.files)}`)+panel('责任与待办',table(['事项','负责人','状态'],source.tasks.map(t=>[E(t.title),E(t.assignee_name||'待明确接手人'),E({open:'待办理',done:'已完成',cancelled:'已结束'}[t.status]||t.status)])));
}
async function rechargeBundleCreate(key,id){
 const context=state.rechargeBundles,fields=[],request_id=requestKey();let selected,choices=[];
 if(key==='purchase'){const catalog=(await api('/api/recharge-bundles/rules')).items;choices=catalog.filter(r=>r.enabled&&r.sale_starts_on<=day()&&day()<=r.sale_ends_on&&!catalog.some(x=>x.issuer_store_id===r.issuer_store_id&&x.code===r.code&&x.rule_version>r.rule_version));if(!choices.length)throw new Error('本店尚无当前启用的组合，请由集团管理员明确配置规则。');fields.push(F('rule','已冻结组合规则','select',true,choices.map(rechargeBundleLabel)));}
 else selected=context.items.find(p=>p.id===Number(id));
 fields.push(F('shares','本次完整份数','int'),F('terms_accepted','已向客户说明并确认整份退款条件','bool',true),F('reason','客户申请及本人说明的条件','textarea'));
 const terms=selected?`${selected.rule.mandatory_terms} ${selected.rule.refund_terms} 当前最多可退 ${selected.refundable_shares} 份。`:choices.map(r=>`${rechargeBundleLabel(r)}：每份本金${money(r.principal_cents_per_share)}元；${r.components.map(c=>rechargeBundleUnits(c.benefit_rule.kind,c.units_per_share)+'，有效'+c.benefit_rule.validity_days+'天').join('；')}。${r.mandatory_terms} ${rechargeBundlePolicies[r.refund_policy]}。${r.refund_terms}`).join('\n');
 await formDialog(key==='purchase'?'申请购买充值组合':'申请原组合整份退款',fields,{shares:1,terms_accepted:false},async v=>{if(v.terms_accepted!==true)throw new Error('请先向客户说明并确认完整份额退款条件。');const values={shares:v.shares,terms_accepted:true};if(selected)values.purchase_id=selected.id;else values.rule_id=choices.find(r=>rechargeBundleLabel(r)===v.rule).id;const d=await api('/api/recharge-bundles/orders',{method:'POST',body:{request_id,customer_id:context.customerId,purpose:key,values,reason:v.reason}});go('recharge-bundle-order/'+d.case.id);},{notice:terms});
}
async function rechargeBundleAction(key){
 const d=state.rechargeBundleOrder,fields=[],request_id=requestKey();
 if(key==='execute')fields.push(F('account_id',d.order.purpose==='refund'?'原收款门店原账户':'真实收款账户','account'),F('reference','实际银行流水或收退款凭证号'));
 if(['approve','execute'].includes(key))fields.push(F('evidence_id',key==='execute'?'本单实际收付款凭据':'本单客户申请与复核凭据','file'));
 fields.push(F('reason','本人核对的事实及办理依据','textarea'));
 await formDialog({approve:'独立复核完整份额',execute:d.order.purpose==='purchase'?'确认真实到账':'确认原账户实际退款',cancel:'撤销并释放原占额',reject:'退回组合申请'}[key],fields,d.order.purpose==='refund'?{account_id:d.purchase?.effective_account?.id}:{},v=>api(`/api/recharge-bundles/orders/${d.case.id}/actions/${key}`,{method:'POST',body:{request_id,version:d.order.version,case_version:d.case.version,member_version:d.member.version,values:v}}),{caseId:d.case.id,notice:`本次${d.order.values.shares}个完整份额，${money(d.case.amount_cents)}元。${key==='execute'?'先核对真实银行办理结果，系统不代为转账。':''}${d.rule.mandatory_terms} ${d.rule.refund_terms}`});
}
async function rechargeBundleRulesPage(){
 if(state.store==='all')return heading('充值组合规则')+storeNotice();
 const d=await api('/api/recharge-bundles/rules');state.rechargeBundleRules=d.items;
 return heading('充值组合规则','',state.user.role==='admin'?b('bundle-rule','发布组合新版本','','primary'):'')+d.items.map(r=>panel(`${r.enabled?'已启用':'未启用'} · ${r.name} · 版本${r.rule_version}`,rechargeBundleRuleFacts(r)+`<p>发行期间：${r.sale_starts_on} 至 ${r.sale_ends_on}</p>`+rechargeBundleTerms(r)+(state.user.role==='admin'?b('bundle-rule','以此追加新版本',`data-id="${r.id}"`):''))).join('');
}
async function rechargeBundleRule(id){
 const current=state.rechargeBundleRules?.find(r=>r.id===Number(id)),all=(await api('/api/group/benefits/rules')).items,stores=state.stores.filter(s=>s.active!==false),request_id=requestKey();
 const choices=all.filter(r=>r.sale_cents_per_unit===0&&r.refund_policy==='none'&&!all.some(x=>x.issuer_store_id===r.issuer_store_id&&x.code===r.code&&x.rule_version>r.rule_version));
 const fields=[F('code','组合规则编号（同编号追加新版本）'),F('name','组合名称'),F('principal','每份实收本金（元）','money'),...stores.map(s=>F('store_'+s.id,'发行及赠品适用门店：'+s.name,'bool',false)),F('sale_starts_on','允许发行起始日期','date'),F('sale_ends_on','允许发行截止日期','date')];
 const initial={enabled:false,sale_starts_on:day(),sale_ends_on:day(),refund_policy:rechargeBundlePolicies.whole_unused_before_expiry};
 if(current){Object.assign(initial,{code:current.code,name:current.name,principal:money(current.principal_cents_per_share),sale_starts_on:current.sale_starts_on,sale_ends_on:current.sale_ends_on,refund_policy:rechargeBundlePolicies[current.refund_policy],refund_terms:current.refund_terms});for(const sid of current.allowed_store_ids)initial['store_'+sid]=true;}
 for(const [kind,label] of Object.entries(rechargeBundleKinds)){const rs=choices.filter(r=>r.kind===kind);fields.push(F('gift_'+kind,label+'冻结权益规则','select',true,['不赠送',...rs.map(rechargeBundleLabel)]),F('units_'+kind,'每份'+label+(kind==='bonus'?'（元）':'数量'),kind==='bonus'?'money':'int',false));initial['gift_'+kind]='不赠送';const c=current?.components.find(c=>c.benefit_rule.kind===kind);if(c&&rs.some(r=>r.id===c.benefit_rule.id)){initial['gift_'+kind]=rechargeBundleLabel(c.benefit_rule);initial['units_'+kind]=kind==='bonus'?money(c.units_per_share):c.units_per_share;}}
 fields.push(F('refund_policy','明确整份退款期限','select',true,Object.values(rechargeBundlePolicies)),F('refund_terms','需向客户说明的补充退款条件（至少10字）','textarea'),F('enabled','启用本版本新申请','bool',false));
 await formDialog('发布充值组合规则',fields,initial,v=>{const components=[];for(const kind of Object.keys(rechargeBundleKinds)){if(v['gift_'+kind]!=='不赠送'){const rule=choices.find(r=>rechargeBundleLabel(r)===v['gift_'+kind]);components.push({benefit_rule_id:rule.id,units_per_share:kind==='bonus'?groupFen(v['units_'+kind]):v['units_'+kind]});}}if(!components.length)throw new Error('请至少选择一项明确的零售价赠品。');return api('/api/recharge-bundles/rules',{method:'POST',body:{request_id,values:{code:v.code,name:v.name,principal_cents_per_share:groupFen(v.principal),allowed_store_ids:stores.filter(s=>v['store_'+s.id]).map(s=>s.id),sale_starts_on:v.sale_starts_on,sale_ends_on:v.sale_ends_on,refund_policy:Object.keys(rechargeBundlePolicies).find(k=>rechargeBundlePolicies[k]===v.refund_policy),refund_terms:v.refund_terms,enabled:v.enabled,components}}});},{notice:'默认不启用。每个赠品规则须已配置为零售价、不单独现金退款，且适用店与本组合完全相同。赠品用后只能退仍完整的原份额，不能拆份折现或用其他批次补足；本金始终为集团通用余额。发布后只能追加新版本。'});
}
function clearRechargeBundleSession(){for(const key of ['rechargeBundles','rechargeBundleOrder','rechargeBundleRules'])delete state[key];}
