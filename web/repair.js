'use strict';
const repairNames={quote:'报价／授权增项',stop:'协商停工保留费用',quote_cancel:'撤销待授权版本',price_approve:'主管价格授权',authorize:'记录客户当前版本授权',start:'确认实际开工',issue:'按授权配件发料',return_material:'原领料退回',finish:'提交施工结果',quality:'检查维修质量',allocate:'确认费用承担',receive:'登记实际到账',release:'确认客户接车',cancel:'取消未开工维修'};
const repairPayers={customer:'客户',insurer:'保险公司',manufacturer:'厂家',internal:'内部承担'};
function repairScaled(value,digits){const text=String(value).trim();if(!new RegExp('^\\d+(\\.\\d{1,'+digits+'})?$').test(text))throw new Error('金额最多两位、数量最多三位小数，请核对。');const [a,b='']=text.split('.'),n=Number(a)*10**digits+Number(b.padEnd(digits,'0'));if(!Number.isSafeInteger(n))throw new Error('数值超出允许范围。');return n;}
async function repairAll(path){let items=[];for(let p=1;p<=100;p++){const data=await api(path+(path.includes('?')?'&':'?')+'page='+p);items.push(...data.items);if(items.length>=data.total)return items;}throw new Error('主档数量超过当前选择上限，请联系管理员缩小范围。');}
function repairCurrent(row){return row.quotes.find(q=>q.id===row.data.quote_id);}
function repairSourcePrice(select){
 if(!select?.matches?.('select[data-repair-source]')||select.disabled||!select.value||select.value===select.dataset.priceSource)return;
 const price=select.closest('[data-repair-line]')?.querySelector('[name=price]'),raw=select.selectedOptions[0]?.dataset.referencePrice,cents=Number(raw);
 if(!price||price.readOnly||raw===undefined||!Number.isSafeInteger(cents)||cents<0)return;
 // Only an explicit item change applies the already-loaded reference price.
 price.value=(cents/100).toFixed(2);select.dataset.priceSource=select.value;
}
async function repairReturnOptions(row){
 const stocks=row.stock.filter(s=>s.returnable_milli>0),lines=stocks.map(s=>row.quotes.find(q=>q.id===s.quote_id)?.lines.find(l=>l.line_key===s.line_key)||repairCurrent(row)?.lines.find(l=>l.line_key===s.line_key));
 const itemIds=[...new Set(lines.map(l=>l?.item_id).filter(Boolean))],dates=new Map();
 const reports=await Promise.allSettled(itemIds.map(id=>api('/api/masters/opening/stockflow?item_id='+id)));
 reports.forEach((result,index)=>{if(result.status!=='fulfilled')return;for(const m of result.value.rows||[]){if(m.source==='业务'&&m.case_id===row.id&&m.item_id===itemIds[index])dates.set(m.id,m.date);}});
 return stocks.map((s,index)=>{const line=lines[index],date=dates.get(s.stock_move_id),parts=[line?[line.code,line.name].filter(Boolean).join(' · '):'配件',date?'领用 '+date:'','可退 '+number(s.returnable_milli/1000)+(line?.unit?' '+line.unit:''),'领料 '+s.id];return {value:String(s.id),label:parts.filter(Boolean).join(' · ')};});
}
async function repairPage(id){
 if(!id){const d=await api('/api/repair-orders?page='+state.page+'&q='+encodeURIComponent(state.q));return heading('维修明细工单','',canWrite()&&['admin','service'].includes(state.user.role)?b('repair-new','建立维修明细工单','','primary'):'')+storeNotice()+workRecordSearch('客户姓名、车牌或工单号',100)+panel('维修业务',table(['工单／客户','状态','当前授权金额（元）','尚欠（元）',''],d.items.map(r=>[`${E(r.number)}<br>${E(r.title)}`,pill(r.state),money(r.amount_cents),money(r.receivable_cents),b('open','办理',`data-route="repair-orders/${r.id}"`)])))+pager(d.total);}
 const row=await api('/api/repair-orders/'+id);state.repairOrder=row;state.row=await api('/api/flow/cases/'+id);
 const q=repairCurrent(row),allowed=k=>canWrite()&&row.actions.includes(k),button=(key,extra='')=>b('repair-action',repairNames[key],`data-key="${key}" ${extra}`),buttons=[];
 if(state.catalog?.capabilities?.repair_packages&&['assessment','working'].includes(row.state)&&!row.data.stopping&&allowed('quote')&&!q?.repair_package&&!row.service_intake?.rework_extension)buttons.push(b('package-quote','使用已购作业配件套餐'));
 if(state.catalog?.capabilities?.repair_packages&&row.settled&&row.state==='settling'&&q?.repair_package&&packageFinance())buttons.push(b('package-capture','按实际履约核销原套餐'));
 if(['assessment','working'].includes(row.state)&&!row.settled&&!row.data.stopping&&allowed('quote')){buttons.push(button('quote'));if(row.data.started)buttons.push(button('stop'));}
 if(['approval','authorization'].includes(row.state)){if(row.state==='approval'&&allowed('price_approve'))buttons.push(button('price_approve'));if(row.state==='authorization'&&allowed('authorize'))buttons.push(button('authorize'));if(allowed('quote_cancel'))buttons.push(button('quote_cancel'));}
 if(row.state==='working'&&q?.authorized){if(!row.data.started&&allowed('start'))buttons.push(button('start'));if(row.data.started){if(allowed('finish'))buttons.push(button('finish'));if(!row.data.stopping&&allowed('issue')&&q.lines.some(l=>l.kind==='part'&&l.quantity_milli>l.issued_milli))buttons.push(button('issue'));}}
 if(row.data.started&&!row.settled&&!row.data.released_date&&row.stock.some(s=>s.returnable_milli>0)&&allowed('return_material'))buttons.push(button('return_material'));
 if(row.state==='quality'&&allowed('quality'))buttons.push(button('quality'));
 if(row.state==='settling'){if(!row.settled&&allowed('allocate'))buttons.push(button('allocate'));if(row.settled&&allowed('release'))buttons.push(button('release'));}
 if(!row.data.started&&!row.settled&&!['cancelled','completed'].includes(row.state)&&allowed('cancel'))buttons.push(button('cancel'));
 let html=heading(row.title,row.number,b('open','返回工单','data-route="repair-orders"'))+storeNotice()+`<div class="row">${pill(row.state)}<span>${E(row.data.plate)}${row.data.stopping?' · 已约定停工保留费用':''}</span></div><div class="stack">`;
 if(row.amount_cents!==undefined)html+=`<div class="kpis"><div class="kpi"><div class="label">当前授权（元）</div><div class="value">${money(row.amount_cents)}</div></div><div class="kpi"><div class="label">外部承担（元）</div><div class="value">${money(row.revenue_cents)}</div></div><div class="kpi"><div class="label">客户尚欠（元）</div><div class="value">${money(row.customer_due_cents)}</div></div><div class="kpi"><div class="label">全部尚欠（元）</div><div class="value">${money(row.receivable_cents)}</div></div></div>`;
 html+=serviceIntakeRepairPanel(row)+actionPanel(`<p>${E(row.data.problem)}</p><div class="row">${buttons.join('')||'当前岗位等待其他员工完成前置步骤。'}</div>`);
 if(q&&['admin','manager','service','finance','auditor'].includes(state.user.role))html+=panel('理赔索赔与客户报销',b('open','核对理赔申请','data-route="claims"')+(canWrite()&&['admin','service'].includes(state.user.role)?b('claim-new','从本维修申请核赔',`data-source="${row.id}"`):'')+'<p>外部核价、实际赔付及客户报销另行留档，批准不代表到账；已冻结承担只可追加明确纠正。</p>');
 if(q){html+=panel(`当前报价 · 第 ${q.revision} 版`,`${q.purpose==='stop'?'<div class="notice warn">保留原施工和领退料事实，本版本明确客户协商的已履约费用。</div>':''}<p>${E(q.reason)}</p><p class="fieldhelp">${q.price_approved?'主管已确认价格':'等待主管价格授权'} · ${q.authorized?'客户授权已关联本版本':'等待当前版本客户授权'}</p>`+repairLines(q));}
 html+=historyPanel('报价历史',row.quotes.map(q=>`<details><summary>第 ${q.revision} 版 · ${q.purpose==='stop'?'停工保留费':'项目与配件'} · ${q.cancelled?'已撤销':q.authorized?'已授权':q.price_approved?'待客户授权':'待价格审批'}</summary><div class="detailsbody">${repairLines(q)}<p class="fieldhelp">版本摘要：${E(q.digest.slice(0,20))}</p></div></details>`).join('')||'<p>尚未形成报价版本。</p>');
 html+=panel('实际领退料',table(['原领料／退料','配件行','数量','原单可退'],row.stock.map(s=>[s.original_id?'退原领料 '+s.original_id:'领料 '+s.id,E(q?.lines.find(l=>l.line_key===s.line_key)?.name||s.line_key),number(s.quantity_milli/1000),s.returnable_milli===undefined?'—':number(s.returnable_milli/1000)])));
 html+=panel('质检记录',row.quality.map(x=>`<div class="taskitem"><div class="description"><strong>${x.passed?'合格':'不合格，需处理并复检'}</strong><p>${E(x.result)}</p></div></div>`).join('')||'<p>尚未提交质检。</p>');
 if(row.amount_cents!==undefined)html+=panel('各承担方与实际到账',row.settled?row.allocations.map(a=>`<div class="taskitem"><div class="description"><strong>${E(repairPayers[a.payer_type])} · ${E(a.payer_name)}</strong><p>原承担 ${money(a.amount_cents)} 元 · 当前承担 ${money(a.net_cents??a.amount_cents)} 元 · 尚欠 ${money(a.due_cents)} 元 · 到期 ${E(a.due_date)}</p>${a.payments.map(p=>`<p>${p.direction==='out'?'实际退款':'已到账'} ${money(p.amount_cents)} 元 · 流水关联 ${p.payment_link_id}</p>`).join('')}${a.due_cents&&allowed('receive')?button('receive',`data-id="${a.id}"`):''}</div></div>`).join('')+'<p class="fieldhelp">内部承担不生成现金，不计外部维修收入；客户结清后，保险与厂家可后到账。</p>':'<p>待质检通过后由主管确认承担，当前尚未形成各方应收。</p>');
 if(row.claims_internal_absorption?.length)html+=panel('核赔差额内部吸收',row.claims_internal_absorption.map(a=>`<p>${E(a.payer_name)} · ${money(a.amount_cents)} 元（追加责任，不产生现金）</p>`).join(''));
 if(row.settled&&['admin','manager','finance','service'].includes(state.user.role))html+=panel('集团权益',b('open','办理客户集团会员及权益',`data-route="group/${row.customer_id}/${row.id}"`)+'<p>权益只能抵扣客户承担，保险、厂家和内部承担分别核对。</p>');
 html+=panel('本单实际凭据',(canWrite()?b('upload','上传客户授权、施工与收款凭据'):'')+state.row.files.map(f=>`<div class="filerecord"><div class="filetext"><strong>${E(f.name)}</strong><p>${E(f.label)} · ${E(f.security?.label||'等待检查')}</p><div class="row">${b('filescaninfo','检查记录',`data-id="${f.id}"`)}${f.security?.can_use?b('download','下载',`data-id="${f.id}"`):'检查通过后可使用'}</div></div></div>`).join(''));
 html+=panel('岗位交接',state.row.tasks.map(t=>`<div class="taskitem"><div class="description"><strong>${E(t.title)}</strong><p>${E(t.assignee_name)} · ${pill(t.status)}</p>${t.status==='open'&&canWrite()&&['admin','manager'].includes(state.user.role)?b('assign','交接给其他员工',`data-id="${t.id}"`):''}</div></div>`).join(''));
 return html+'</div>';
}
function repairLines(q){const moneyFields=q.amount_cents!==undefined,split=q.lines.some(l=>l.charge_scope);return memberPriceSummary(q.member_pricing)+(q.rework_scope?`<p>原责任 ${money(q.rework_scope.original_liability_cents)} 元 · 本次新增自费 ${money(q.rework_scope.customer_extra_cents)} 元</p>`:'')+table(['项目／配件',...(split?['责任类别']:[]),'数量','当前净领用',...(moneyFields?['单价（元）','分摊优惠（元）','金额（元）']:[])],q.lines.map(l=>[`${E(l.code)} · ${E(l.name)}<br>${E(l.unit==='job'?'次':l.unit==='hour'?'小时':l.unit)}`,...(split?[E(l.charge_scope==='original_liability'?'原责任，免客户收费':'本次新增自费')]:[]),number(l.quantity_milli/1000),l.kind==='part'?number(l.issued_milli/1000):'—',...(moneyFields?[money(l.unit_price_cents),money(l.discount_cents),money(l.amount_cents)]:[])]));}
async function repairNew(){const request_id=requestKey();await formDialog('建立维修明细工单',[F('customer_id','客户档案','customer'),F('plate','车牌号'),F('problem','报修问题','textarea'),F('due_date','预计交接日期','date')],{},v=>api('/api/repair-orders',{method:'POST',body:{request_id,...v}}).then(r=>go('repair-orders/'+r.id)));}
async function repairQuoteDialog(stop=false){
 if(state.catalog?.capabilities?.repair_packages&&repairCurrent(state.repairOrder)?.repair_package)return packageQuoteDialog(state.repairOrder,stop);
 if(state.repairOrder.service_intake?.rework_extension)return reworkQuoteDialog(state.repairOrder,stop);
 const row=state.repairOrder,q=repairCurrent(row),request_id=requestKey(),send=values=>api(`/api/repair-orders/${row.id}/actions/quote`,{method:'POST',body:{request_id,version:row.version,values}});
 if(stop){await formDialog('协商停工保留费用',[F('retained','约定已履约保留金额（元）','money_zero'),F('reason','已完成项目、退料安排与保留费用约定','textarea')],{},v=>send({purpose:'stop',retained_amount_cents:repairScaled(v.retained,2),reason:v.reason,lines:[]}),{notice:'保留原报价与全部领退料事实。新保留费需主管复核和客户重新授权，之后核对未用料退回及安全交接。'});return;}
 const [work,parts]=await Promise.all([repairAll('/api/masters/work_items?active=true'),repairAll('/api/flow/master/items?page_size=100')]);
 const sources=[...work.map(w=>({key:'work:'+w.id,name:'项目 · '+w.code+' '+w.name,price:w.standard_fee_cents})),...parts.filter(p=>p.active).map(p=>({key:'part:'+p.id,name:'配件 · '+p.sku+' '+p.name,price:0}))];
 for(const old of q?.lines||[]){const key=old.kind+':'+(old.work_item_id||old.item_id);if(!sources.some(s=>s.key===key))sources.push({key,name:old.code+' · '+old.name+'（已冻结主档）',price:old.unit_price_cents});}
 if(!sources.length)throw new Error('请先配置启用的作业项目和配件主档。');
 const line=l=>`<div class="panelbody" data-repair-line data-line-key="${row.data.started&&l?E(l.line_key):''}"><label>项目／配件<select name="source" required data-search-select data-repair-source data-price-source="${E(l?l.kind+':'+(l.work_item_id||l.item_id):sources[0].key)}" ${row.data.started&&l?'disabled':''}>${sources.map(s=>`<option value="${s.key}" data-reference-price="${s.price}" ${l&&s.key===l.kind+':'+(l.work_item_id||l.item_id)?'selected':''}>${E(s.name)}</option>`).join('')}</select></label><div class="formgrid"><label>数量<input name="quantity" inputmode="decimal" required value="${l?(l.quantity_milli/1000).toFixed(3):'1.000'}"></label><label>单价（元）<input name="price" inputmode="decimal" required value="${l?(l.unit_price_cents/100).toFixed(2):(sources[0].price/100).toFixed(2)}" ${row.data.started&&l?'readonly':''}></label></div>${!row.data.started||!l?b('repair-remove-line','删除此行'):''}</div>`;
 state.repairLineHtml=line(null);
 modal('维修报价与授权增项',`<form>${await memberPriceField(row.id)}<p>已有施工的授权行保留数量和价格；追加数量或项目必须再次获得价格审批及客户授权。本次优惠仅分摊到新增部分。</p><div id="repair-lines">${q?q.lines.map(line).join(''):line(null)}</div>${b('repair-add-line','增加项目／配件')}<label>本次新增优惠（元）<input name="discount" inputmode="decimal" value="0.00" required></label><label>诊断、方案及增项原因<textarea name="reason" required minlength="2" maxlength="1000"></textarea></label><div class="formerror" role="alert"></div><div class="modalfoot"><button type="submit" class="primary">提交本版本价格审批</button></div></form>`,async form=>{
  const lines=[...form.querySelectorAll('[data-repair-line]')].map(el=>{const [kind,id]=el.querySelector('[name=source]').value.split(':');return {kind,source_id:Number(id),...(el.dataset.lineKey?{line_key:el.dataset.lineKey}:{}),quantity_milli:repairScaled(el.querySelector('[name=quantity]').value,3),unit_price_cents:repairScaled(el.querySelector('[name=price]').value,2)};});
  await send({purpose:'service',...memberPricePayload(form),reason:form.elements.reason.value,discount_cents:repairScaled(form.elements.discount.value,2),lines});closeModal();await render();
 });
}
function repairAllocationContext(row){
 const context=[state.store,state.user?.id,state.user?.role,state.route,typeof storeContextVersion==='undefined'?0:storeContextVersion];
 return form=>{if(state.repairOrder!==row||context.some((v,i)=>v!==[state.store,state.user?.id,state.user?.role,state.route,typeof storeContextVersion==='undefined'?0:storeContextVersion][i])||(form&&!form.isConnected))throw new Error('页面已变化，请重新打开本单办理。');if(!canWrite()||!row.actions?.includes('allocate'))throw new Error('当前不能确认费用承担，请刷新本单。');};
}
function repairAllocationClaims(row,claims){
 return claims.filter(c=>c.state!=='cancelled'&&['repair_receivable','internal'].includes(c.order.payment_route)).map(c=>{
  const assessment=c.assessments.find(a=>a.id===c.data.assessment_id),result=c.results.find(r=>r.id===c.data.result_id);
  // The original API remains authoritative for approval, source version and binding.
  const current=c.source_id===row.id&&c.source_quote_id===row.data.quote_id&&assessment?.quote_id===row.data.quote_id&&['ready','bound','completed'].includes(c.phase);
  const amount=current?(c.order.party_type==='internal'?assessment.amount_cents:result?.assessment_id===assessment.id&&['approved','partial','rejected'].includes(result.outcome)?result.amount_cents:null):null;
  return {id:c.id,number:c.number,name:c.order.party_name,amount,phase:c.phase_label};
 });
}
function repairAllocationAmounts(form){
 return Object.keys(repairPayers).flatMap(k=>{const input=form.elements['amount_'+k];if(input.disabled||input.closest('[data-repair-payer]')?.disabled||!input.value.trim())return [];const amount_cents=repairScaled(input.value,2);return amount_cents>0?[{payer_type:k,amount_cents}]:[];});
}
function repairAllocationValues(form,total){
 const allocations=repairAllocationAmounts(form),sum=allocations.reduce((s,a)=>s+a.amount_cents,0);
 if(sum!==total)throw new Error(sum<total?`还需分配 ${money(total-sum)} 元。`:`已超出 ${money(sum-total)} 元，请核对。`);
 return allocations.map(a=>{
  const k=a.payer_type,due_date=form.elements['due_'+k].value;if(!due_date)throw new Error('请填写'+repairPayers[k]+'的到期日。');
  if(['insurer','manufacturer'].includes(k)){const payer_id=Number(form.elements['payer_'+k].value);if(!Number.isSafeInteger(payer_id)||payer_id<=0)throw new Error('请选择'+repairPayers[k]+'。');return {...a,due_date,payer_id};}
  if(k==='internal'){const payer_name=form.elements.internal_name.value.trim();if(payer_name.length<2)throw new Error('请填写内部承担单位。');return {...a,due_date,payer_name};}
  return {...a,due_date};
 });
}
function repairAllocationUpdate(form,total){
 let sum=0,invalid=false;try{sum=repairAllocationAmounts(form).reduce((s,a)=>s+a.amount_cents,0);}catch{invalid=true;}
 form.querySelector('[data-repair-allocation-total]').textContent=invalid?'请核对金额，最多两位小数。':`已分配 ${money(sum)} 元 · `+(sum===total?'已分配完整':sum<total?`尚需分配 ${money(total-sum)} 元`:`超出 ${money(sum-total)} 元`);
 for(const k of Object.keys(repairPayers)){const input=form.elements['amount_'+k],positive=!input.disabled&&!input.closest('[data-repair-payer]')?.disabled&&Number(input.value)>0;for(const name of ['due_'+k,'payer_'+k,...(k==='internal'?['internal_name']:[])])if(form.elements[name])form.elements[name].required=positive;}
}
async function repairAllocationLoadPayer(form,kind,guard){
 if(!['insurer','manufacturer'].includes(kind))return;
 const section=form.querySelector(`[data-repair-payer="${kind}"]`),status=section.querySelector('[data-repair-payer-status]'),select=form.elements['payer_'+kind];
 if(section.dataset.loading||section.dataset.loaded)return;guard(form);section.dataset.loading='true';status.textContent='正在读取…';
 try{
  const records=kind==='insurer'?await repairAll('/api/masters/insurers?active=true'):(await repairAll('/api/flow/master/references?page_size=100')).filter(r=>r.category==='厂家'&&r.active);
  guard(form);const selected=select.value;select.innerHTML='<option value="">请选择</option>'+records.map(r=>`<option value="${r.id}">${E(r.name)}</option>`).join('');select.value=selected;section.dataset.loaded='true';status.textContent=records.length?'':'暂无可选单位，请联系管理员添加。';
 }catch(error){try{guard(form);}catch{return;}status.textContent=error.message+' ';const retry=document.createElement('button');retry.type='button';retry.dataset.repairLoadPayer=kind;retry.textContent='重新读取';status.append(retry);}
 finally{delete section.dataset.loading;}
}
async function repairAllocate(){
 if(state.repairOrder.service_intake?.rework_extension)return reworkAllocate(state.repairOrder);
 const row=state.repairOrder,request_id=requestKey(),guard=repairAllocationContext(row);guard();
 if(row.service_intake?.internal_only){const name=row.service_intake.internal_name;await formDialog('确认内部返修承担',[F('labor_cost','本次确认人工成本（元）','money_zero'),F('evidence_id','本次内部承担凭据','file')],{},v=>{guard();return api(`/api/repair-orders/${row.id}/actions/allocate`,{method:'POST',body:{request_id,version:row.version,values:{allocations:row.amount_cents?[{payer_type:'internal',payer_name:name,amount_cents:row.amount_cents,due_date:day()}]:[],labor_cost_cents:repairScaled(v.labor_cost,2),evidence_id:v.evidence_id}}});},{caseId:row.id,notice:`本次 ${money(row.amount_cents)} 元全部由 ${name} 承担，不产生客户应收与现金。`});return;}
 const detail=await api('/api/flow/cases/'+row.id);guard();if(detail.version!==row.version)throw new Error('本单已更新，请刷新后核对费用。');
 const claims=await Promise.all((detail.children||[]).filter(c=>c.kind==='claim'&&c.flow_version===2&&c.state!=='cancelled').map(c=>api('/api/claims/'+c.id)));guard();
 if(claims.some(c=>c.source_id!==row.id||c.source_version!==row.version))throw new Error('核赔资料已更新，请刷新本单后核对。');
 const checks=repairAllocationClaims(row,claims),allCustomer=checks.every(c=>c.amount===0);
 const claimNotice=checks.length?`<div class="notice">${checks.map(c=>`<p>${E(c.name)} · ${c.amount===null?E(c.phase||'等待核赔结果'):`核赔金额 ${money(c.amount)} 元`} <a href="#claims/${c.id}">查看理赔</a></p>`).join('')}</div>`:'';
 const section=(k,label)=>`<fieldset data-repair-payer="${k}" ${k==='customer'?'':'hidden disabled'}><legend>${label}</legend><label>承担金额（元）<input name="amount_${k}" inputmode="decimal" placeholder="不承担留空或填0"></label>${['insurer','manufacturer'].includes(k)?`<label>承担单位<select name="payer_${k}" data-search-select><option value="">请选择</option></select></label><div data-repair-payer-status role="status"></div>`:k==='internal'?'<label>内部承担单位<input name="internal_name" maxlength="120"></label>':''}<label>到期日<input type="date" name="due_${k}" value="${day()}"></label>${k==='customer'?'':`<button type="button" data-repair-remove-payer="${k}">取消此承担方</button>`}</fieldset>`;
 const dialog=modal('确认费用承担',`<form><p>当前授权合计 ${money(row.amount_cents)} 元</p>${claimNotice}<button type="button" data-repair-customer-all ${allCustomer?'':'disabled'}>客户全额承担</button>${allCustomer?'':'<p class="fieldhelp">请按核赔结果分配费用。</p>'}${Object.entries(repairPayers).map(([k,label])=>section(k,label)).join('')}<div class="row">${Object.entries(repairPayers).filter(([k])=>k!=='customer').map(([k,label])=>`<button type="button" data-repair-add-payer="${k}">添加${label}</button>`).join('')}</div><p data-repair-allocation-total role="status" aria-live="polite"></p><label>本次人工成本（元）<input name="labor_cost" inputmode="decimal" placeholder="无人工成本填0" required></label><div>承担确认凭据${caseFilePickerHTML('evidence',row.id,detail.files||[])}</div><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button class="primary" type="submit">确认承担并交财务</button></div></form>`,async form=>{
  guard(form);const allocations=repairAllocationValues(form,row.amount_cents),evidence_id=Number(form.elements.evidence.value);if(!Number.isSafeInteger(evidence_id)||evidence_id<=0)throw new Error('请选择或上传承担确认凭据。');
  await api(`/api/repair-orders/${row.id}/actions/allocate`,{method:'POST',body:{request_id,version:row.version,values:{allocations,labor_cost_cents:repairScaled(form.elements.labor_cost.value,2),evidence_id}}});guard(form);closeModal();await render();
 });
 const form=dialog.querySelector('form');repairAllocationUpdate(form,row.amount_cents);
 form.addEventListener('input',()=>repairAllocationUpdate(form,row.amount_cents));
 form.addEventListener('click',async event=>{
  const button=event.target.closest('[data-repair-customer-all],[data-repair-add-payer],[data-repair-remove-payer],[data-repair-load-payer]');if(!button||button.disabled)return;
  try{guard(form);if(button.hasAttribute('data-repair-customer-all')){if(!allCustomer)return;for(const k of Object.keys(repairPayers))form.elements['amount_'+k].value=k==='customer'?(row.amount_cents/100).toFixed(2):'';}
   const kind=button.dataset.repairAddPayer||button.dataset.repairRemovePayer||button.dataset.repairLoadPayer;
   if(kind){const section=form.querySelector(`[data-repair-payer="${kind}"]`),remove=!!button.dataset.repairRemovePayer;section.hidden=remove;section.disabled=remove;form.querySelector(`[data-repair-add-payer="${kind}"]`).hidden=!remove;if(remove)form.elements['amount_'+kind].value='';else await repairAllocationLoadPayer(form,kind,guard);}
   guard(form);repairAllocationUpdate(form,row.amount_cents);
  }catch(error){if(form.isConnected)form.querySelector('.formerror').textContent=error.message;}
 });
}
function repairWarehousePreparation(row,key,issueLines,issueLabels){
 if(!['issue','return_material'].includes(key)||!['admin','inventory'].includes(state.user?.role))return undefined;
 return {caseId:row.id,purpose:key==='issue'?'repair_issue_v3':'repair_return_v3',source:row,getVersion:()=>row.version,setVersion:version=>{row.version=version;},readSource:()=>api('/api/repair-orders/'+row.id),getLines:form=>{
  let line;if(key==='issue')line=issueLines[issueLabels.indexOf(form.elements.line_label.value)];
  else{const stock=row.stock.find(s=>s.id===Number(form.elements.original_id.value)&&!s.original_id&&s.returnable_milli>0);line=stock&&row.quotes.find(q=>q.id===stock.quote_id)?.lines.find(l=>l.line_key===stock.line_key);}
  if(!line||line.kind!=='part'||!line.item_id)throw new Error('请先选择本次领退的配件。');
  const quantity_milli=repairScaled(form.elements.quantity.value,3);if(quantity_milli<=0)throw new Error('请填写本次实际数量。');
  return [{item_id:line.item_id,quantity_milli,label:[line.code,line.name].filter(Boolean).join(' · ')}];
 }};
}
async function repairAction(key,id){
 if(key==='quote'||key==='stop')return repairQuoteDialog(key==='stop');if(key==='allocate')return repairAllocate();
 const row=state.repairOrder,q=repairCurrent(row),request_id=requestKey(),fields=[],initial={},extra={};
 if(['price_approve','authorize','quote_cancel'].includes(key))extra.quote_id=q.id;
 if(key==='price_approve'){fields.push(F('minimum','本次主管确认最低金额（元）','money_zero'),F('allow_below_minimum','明确批准低于最低金额的例外','bool'),F('reason','价格确认／低价例外原因','textarea'));initial.minimum=(q.amount_cents/100).toFixed(2);}
 if(['quote_cancel','cancel'].includes(key))fields.push(F('reason','办理原因','textarea'));
 if(['start','finish','quality'].includes(key))fields.push(F('result','本人实际办理情况','textarea'));
 if(key==='quality')fields.push(F('outcome','检查结果','select',true,['合格','不合格']));
 const issueLines=q?.lines.filter(l=>l.kind==='part'&&l.quantity_milli>l.issued_milli)||[],issueLabels=issueLines.map(l=>`${l.code} · ${l.name} · 尚可领 ${number((l.quantity_milli-l.issued_milli)/1000)}`);
 if(key==='issue'){fields.push({...F('line_label','领取配件','select',true,issueLabels),searchable:true},F('quantity','本次实际数量','quantity'));}
 if(key==='return_material'){
  const context=[state.store,state.user?.id,state.user?.role,state.route,typeof storeContextVersion==='undefined'?0:storeContextVersion],options=await repairReturnOptions(row);
  if(state.repairOrder!==row||context.some((v,i)=>v!==[state.store,state.user?.id,state.user?.role,state.route,typeof storeContextVersion==='undefined'?0:storeContextVersion][i]))return;
  fields.push({...F('original_id','退回配件','select',true,options),searchable:true},F('quantity','本次退回数量','quantity'));
 }
 if(key==='receive'){const allocation=row.allocations.find(a=>a.id===id);extra.allocation_id=id;fields.push(F('amount','本次实际到账（元）','money'),F('account_id','实际资金账户','account'),F('reference','流水或凭证号'));initial.amount=(allocation.due_cents/100).toFixed(2);}
 if(['authorize','issue','return_material','quality','receive','release'].includes(key))fields.push(F('evidence_id','本单实际凭据','file'));
 await formDialog(repairNames[key],fields,initial,v=>{const values={...v,...extra};if('line_label'in v){values.line_key=issueLines[issueLabels.indexOf(v.line_label)].line_key;delete values.line_label;}if('minimum'in v){values.minimum_total_cents=repairScaled(v.minimum,2);delete values.minimum;}if('quantity'in v){values.quantity_milli=repairScaled(v.quantity,3);delete values.quantity;}if('amount'in v){values.amount_cents=repairScaled(v.amount,2);delete values.amount;}if('outcome'in v){values.passed=v.outcome==='合格';delete values.outcome;}if(v.original_id)values.original_id=Number(v.original_id);return api(`/api/repair-orders/${row.id}/actions/${key}`,{method:'POST',body:{request_id,version:row.version,values}});},{caseId:row.id,warehouse:repairWarehousePreparation(row,key,issueLines,issueLabels),notice:key==='authorize'?`请核对客户授权确实对应第 ${q.revision} 版；旧版本授权文件不能重复用于增项。`:'请只确认本人核对的事实，后台会校验版本、前置条件、金额和原单关联。'});
}
document.addEventListener('click',async event=>{const el=event.target.closest('[data-act]');if(!el?.dataset.act.startsWith('repair-'))return;try{switch(el.dataset.act){case'repair-new':await repairNew();break;case'repair-action':await repairAction(el.dataset.key,Number(el.dataset.id));break;case'repair-add-line':$('#repair-lines').insertAdjacentHTML('beforeend',state.repairLineHtml);break;case'repair-remove-line':if(document.querySelectorAll('[data-repair-line]').length<=1)throw new Error('报价至少保留一行。');el.closest('[data-repair-line]').remove();break;}}catch(error){toast(error.message,true);}});
document.addEventListener('change',event=>repairSourcePrice(event.target));
