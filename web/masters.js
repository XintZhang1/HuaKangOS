'use strict';
// Fixed schemas come from the backend; imported source text stays in this session only.
let masterUI={};
function clearMastersSession(){masterUI={};}
function masterContext(){const key=String(state.user?.id)+':'+state.store;if(masterUI.key!==key)masterUI={key};return masterUI;}
const masterOptions={vehicles:'整车',materials:'物资',mixed:'整车与物资',job:'按项',hour:'按小时',petrol:'汽油',diesel:'柴油',electric:'纯电',hybrid:'混合动力',plugin_hybrid:'插电混合动力',bank:'银行账户',cash:'现金账户'};
async function typedCatalog(){const c=masterContext();if(!c.catalog)c.catalog=await api('/api/masters/catalog');return c.catalog;}
async function mastersPage(kind){
 const c=masterContext(),catalog=await typedCatalog();
 if(!kind){
  const groups=[['来往单位',['suppliers','insurers']],['车辆目录',['vehicle_brands','vehicle_series','vehicle_models']],['物资目录',['material_brands','material_categories','item_profiles']],['仓库与库位',['warehouses','locations']],['服务项目与会员规则',['teams','work_items','agency_projects','member_tiers']]];
  const covered=new Set(groups.flatMap(g=>g[1])),extra=Object.keys(catalog.kinds).filter(k=>!covered.has(k));if(extra.length)groups.push(['其他基础资料',extra]);
  return heading('基础资料','先查已有资料，确实没有时再新增；历史业务与库存流水不会随名称更改。')+storeNotice()+groups.map(([title,keys])=>{const items=keys.filter(k=>catalog.kinds[k]);return items.length?panel(title,`<div class="mux-cards">${items.map(key=>{const spec=catalog.kinds[key];return `<article class="mux-card"><h3>${E(spec.label)}</h3><p>查询已有${E(spec.label)}及有效引用。</p><div class="row">${b('open','查找已有资料',`data-route="masters/${key}"`)}${spec.can_write?b('typed-new','新增'+spec.label,`data-kind="${key}"`):''}</div></article>`;}).join('')}</div>`):'';}).join('');
 }
 const spec=catalog.kinds[kind];if(!spec)throw new Error('经营主资料类型不存在。');
 const query=new URLSearchParams({q:state.q,page:state.page});
 if(kind==='vehicle_models'&&c.vehicleFilters)for(const [key,value]of Object.entries(c.vehicleFilters))if(value!=='')query.set(key,value);
 const d=await api('/api/masters/'+kind+'?'+query);c.rows=d.items;c.kind=kind;
 const columns=spec.fields.filter(f=>f.type!=='bool');
 const headingButtons=spec.can_write?b('typed-new','新增'+spec.label,`data-kind="${kind}"`,'primary'):'';
 const filters=kind==='vehicle_models'?`<form id="typed-model-filters" class="filterbar"><label>动力类型<select name="fuel_type"><option value="">不限</option>${['petrol','diesel','electric','hybrid','plugin_hybrid'].map(v=>`<option value="${v}" ${c.vehicleFilters?.fuel_type===v?'selected':''}>${masterOptions[v]}</option>`).join('')}</select></label><label>最少座位<input name="min_seats" inputmode="numeric" value="${E(c.vehicleFilters?.min_seats||'')}" placeholder="例如 5"></label><label>指导价上限（元）<input name="max_price" inputmode="decimal" value="${E(c.vehicleMaxPrice||'')}" placeholder="例如 150000"></label><button type="submit" class="primary">筛选车型</button></form>`:'';
 return heading(spec.label,'资料变更保留操作记录；停用不改变已记录的历史业务。',headingButtons)+storeNotice()+(kind==='member_tiers'?`<div class="notice">这里的等级和比例仅作参考。本店独立批准会员价格后，才能用于新的实际报价。${!state.user.aggregate_scope&&full()&&state.catalog?.kinds.member_pricing_rule?b('open','办理会员等级实际定价','data-route="member-pricing"'):''}</div>`:'')+filters+searchBar()+panel('资料列表',table([...columns.map(f=>f.label),'状态','操作'],d.items.map(row=>[...columns.map(f=>E(f.type==='money_cents'?money(row[f.key]):f.type==='ref'?row.reference_labels?.[f.key]||'—':masterOptions[row[f.key]]??row[f.key]??'—')),pill(row.active?'done':'cancelled',row.active?'启用':'停用'),spec.can_write?b('typed-edit','编辑',`data-kind="${kind}" data-id="${row.id}"`):'只读']))+pager(d.total));
}
function masterFen(value){const s=String(value).trim();if(!/^\d+(\.\d{1,2})?$/.test(s))throw new Error('金额须为非负数字，最多两位小数。');const [yuan,fen='']=s.split('.');const n=Number(yuan)*100+Number(fen.padEnd(2,'0'));if(!Number.isSafeInteger(n))throw new Error('金额超出允许范围。');return n;}
async function masterDataDialog(kind,id){
 if(kind==='vehicle_models'&&!id)return catalogEntryDialog();
 const c=masterContext(),spec=(await typedCatalog()).kinds[kind];if(!spec?.can_write||!canWrite())throw new Error('当前门店岗位不能维护此资料。');
 const row=id?c.rows?.find(r=>r.id===id):null;if(id&&!row)throw new Error('请刷新后重新打开资料。');
 const rendered=await Promise.all(spec.fields.map(async f=>{
  let value=row?.[f.key]??f.default??(f.type==='int'||f.type==='money_cents'?0:'');
  if(f.type==='money_cents')return fieldHTML({...f,type:'money_zero'},(Number(value)/100).toFixed(2));
  if(f.type==='select')return `<label>${E(f.label)}<select name="${f.key}" ${f.required?'required':''}><option value="">请选择</option>${f.options.map(o=>`<option value="${E(o)}" ${o===value?'selected':''}>${E(masterOptions[o]||o)}</option>`).join('')}</select></label>`;
  if(f.type==='ref'){const choices=await api(`/api/masters/lookup/${f.ref_kind}`+(value?'?selected_id='+value:''));return `<label>${E(f.label)}<div class="typed-ref" data-kind="${f.ref_kind}"><div class="lookuprow"><input type="search" data-typed-query placeholder="输入关键词查找" aria-label="查找${E(f.label)}">${b('typed-lookup','查找')}</div><select name="${f.key}" ${f.required?'required':''}><option value="">请选择</option>${choices.items.map(o=>`<option value="${o.id}" ${String(o.id)===String(value)?'selected':''}>${E(o.label)}</option>`).join('')}</select>${choices.has_more?'<small>结果超过100条，请输入关键词查找。</small>':''}</div></label>`;}
  return fieldHTML(f,value);
 }));
 const request_id=requestKey();
 modal((row?'编辑':'新增')+spec.label,`<form><div class="notice">修改后用于新业务。</div>${kind==='member_tiers'?'<p class="fieldhelp">本页比例是参考值；保存资料不会批准或修改会员实际报价，请另行办理本店会员价格独立批准。</p>':''}<div class="formgrid">${rendered.join('')}</div><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button type="submit" class="primary">确认保存</button></div></form>`,async form=>{
  const fd=new FormData(form),values={};for(const f of spec.fields){const value=fd.get(f.key);values[f.key]=f.type==='bool'?value!==null:f.type==='money_cents'?masterFen(value):['ref','int'].includes(f.type)?value?Number(value):null:String(value??'').trim();}
  await api('/api/masters/'+kind+(row?'/'+row.id:''),{method:row?'PUT':'POST',body:{request_id,...(row?{version:row.version}:{}),values}});
  closeModal();await render();toast('经营主资料已保存');
 });
}
const openingLabels={customer_count:'客户行数',account_count:'账户行数',item_count:'物资行数',stock_row_count:'有库存物资行数',quantity_milli:'库存数量合计（千分位）',inventory_value_cents:'库存价值合计（元）'};
const openingErrorLabels={items:'物资',customers:'客户',accounts:'账户',source:'原资料',store:'门店',opening_quantity_milli:'期初数量（千分位）',opening_value_cents:'期初价值（分）',source_reference:'来源凭据',opening_date:'期初日期',owner_username:'客户负责人',sku:'物资编码',name:'名称',phone:'电话',existing_data:'已有数据',rows:'资料行',JSON:'资料格式'};
function openingTotals(t){return facts(Object.fromEntries(Object.entries(t).map(([k,v])=>[openingLabels[k]||k,k==='inventory_value_cents'?money(v):v])));}
async function openingPage(){
 const c=masterContext(),catalog=await typedCatalog();
 if(state.store==='all')return heading('期初资料导入')+storeNotice()+'<div class="notice">期初导入与库存核对请先选择具体门店。</div>';
 const result=await api('/api/masters/opening/batches');c.batches=result.items;
 const batch=c.errors?.length?null:c.batch||result.items.find(r=>r.status!=='confirmed')||result.items[0];if(batch)c.batch=batch;
 if(batch&&batch.status!=='confirmed'&&catalog.can_import&&!c.source)c.source=(await api(`/api/masters/opening/${batch.id}/source`)).source_text;
 const editor=catalog.can_import?panel('准备原资料',`<p>仅适用于本店尚无业务及客户、账户、物资主档的独立空数据。不会导入账户现金余额或推断未结旧单。所有数量用整数千分位、金额用整数分。</p><div class="row mt15"><label>选择 JSON 文件<input id="opening-file" type="file" accept=".json,application/json"></label>${b('opening-example','载入虚构示例')}</div><label class="mt15">原始 JSON 资料<textarea id="opening-source" rows="12" maxlength="85000" placeholder="粘贴公司核对后的期初清单">${E(c.source||'')}</textarea></label><div class="row mt15">${b('opening-preflight','预检原资料','','primary')}</div>`):'';
 const errors=c.errors?.length?panel('逐行检查结果',c.errors.map(r=>`<div class="notice warn mt15"><strong>${E(openingErrorLabels[r.section]||r.section)} · ${r.row?'第 '+r.row+' 行':'整体'} · ${E(openingErrorLabels[r.field]||r.field||'资料')}</strong><p>${E(r.message)}</p></div>`).join('')):'';
 const review=batch?panel('预检与核对',`<p>来源：${E(batch.source_reference)} · 期初日期 ${E(batch.opening_date)} · ${E({prepared:'已预检',trial_passed:'试导入通过',confirmed:'已确认入账'}[batch.status])}</p><details><summary>查看原资料校验摘要</summary><p class="wrap">${E(batch.source_digest)}</p></details>${openingTotals(batch.totals)}${catalog.can_import&&batch.status!=='confirmed'?`<div class="row mt20">${b('opening-trial','试导入并回滚',`data-id="${batch.id}"`)}${batch.status==='trial_passed'?b('opening-confirm','核对后确认入账',`data-id="${batch.id}"`,'primary'):''}</div>`:''}`):'';
 return heading('期初资料导入','先预检，再试导入；最后按原资料摘要和数量金额确认整批入账。',b('open','查看库存流水','data-route="opening-stock"'))+editor+errors+review+panel('本店导入记录',table(['批次','来源','日期','状态'],result.items.map(r=>[r.id,E(r.source_reference),E(r.opening_date),E({prepared:'已预检',trial_passed:'试导入通过',confirmed:'已确认入账'}[r.status])])));
}
function openingInputSource(){const c=masterContext(),display=$('#opening-source')?.value??c.source??'';return display===String(c.source??'').replace(/\r\n?/g,'\n')?c.source:display;}
async function openingPreflight(){const c=masterContext();c.source=openingInputSource();const result=await api('/api/masters/opening/preflight',{method:'POST',body:{request_id:requestKey(),source_text:c.source}});c.errors=result.errors;c.batch=result.batch;await render();if(result.valid)toast('预检通过；请继续试导入并核对汇总');}
async function assertOpeningSource(){const c=masterContext();const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(openingInputSource()||''));const digest=Array.from(new Uint8Array(hash),v=>v.toString(16).padStart(2,'0')).join('');if(digest!==c.batch.source_digest)throw new Error('原资料已改变，请先重新预检，不能按旧批次确认。');}
async function openingTrial(){await assertOpeningSource();const c=masterContext(),b=c.batch;const r=await api(`/api/masters/opening/${b.id}/trial`,{method:'POST',body:{request_id:requestKey(),version:b.version,digest:b.source_digest}});c.batch=r.batch;await render();toast('试导入通过，业务数据已全部回滚');}
async function openingConfirm(){await assertOpeningSource();const c=masterContext(),batch=c.batch,request_id=requestKey();modal('确认本店期初资料',`<form><div class="notice warn">确认后建立本店客户、账户、物资与期初库存账，不能再次覆盖导入。请先核对下列数量和金额。</div>${openingTotals(batch.totals)}<label class="checklabel mt20"><input name="confirmed" type="checkbox" required>已核对原资料、行数、库存数量和库存价值</label><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','返回核对')}<button type="submit" class="primary">确认入账</button></div></form>`,async form=>{if(!form.elements.confirmed.checked)throw new Error('请先完成原资料核对。');const r=await api(`/api/masters/opening/${batch.id}/confirm`,{method:'POST',body:{request_id,version:batch.version,digest:batch.source_digest,expected_totals:batch.totals,confirmed:true}});c.batch=r.batch;c.source='';closeModal();await render();toast('期初资料已整批入账');});}
async function openingStockPage(){
 const d=await api('/api/masters/opening/stockflow'),scope=d.can_money?'数量、价值':'数量';
 return heading('期初与库存流水',`从期初来源到后续出入库，逐笔核对${scope}。`,b('opening-stock-export','导出同口径流水'))+storeNotice()+`<div class="notice ${d.all_reconciled?'':'warn'}">${d.all_reconciled?`库存流水与当前${scope}全部一致。`:'发现没有期初来源或流水的历史库存差额，请人工核对；系统不会补造历史。'}</div>`
 +'<p class="fieldhelp">手机可左右滑动表格，查看全部数量、凭据和核对结果。</p>'
 +panel('物资核对',table(['物资编码','流水数量','当前数量',...(d.can_money?['流水价值（元）','当前价值（元）']:[]),'核对结果'],d.totals.map(r=>[E(r.sku),number(r.quantity_milli/1000),number(r.current_quantity_milli/1000),...(d.can_money?[money(r.value_cents),money(r.current_value_cents)]:[]),r.reconciled?'一致':'需核对'])))
 +panel('逐笔流水',table(['物资','日期','来源','凭据','变动数量',...(d.can_money?['变动价值（元）']:[]),'结存数量',...(d.can_money?['结存价值（元）']:[])],d.rows.map(r=>[E(r.name),E(r.date),E(r.source),E(r.reference),number(r.quantity_milli/1000),...(d.can_money?[money(r.value_cents)]:[]),number(r.running_quantity_milli/1000),...(d.can_money?[money(r.running_value_cents)]:[])])));
}
document.addEventListener('click',async event=>{const el=event.target.closest('[data-act]');if(!el||el.disabled)return;const action=el.dataset.act;if(!['typed-new','typed-edit','typed-lookup','opening-example','opening-preflight','opening-trial','opening-confirm','opening-stock-export'].includes(action))return;el.disabled=true;try{
 if(action==='typed-new'||action==='typed-edit')await masterDataDialog(el.dataset.kind,Number(el.dataset.id)||null);
 else if(action==='typed-lookup'){
  const root=el.closest('.typed-ref'),query=$('[data-typed-query]',root),select=$('select',root),submit=root.closest('form')?.querySelector('[type=submit]');
  const previousDisabled=submit?.disabled;query.disabled=true;select.disabled=true;if(submit)submit.disabled=true;
  try{const d=await api('/api/masters/lookup/'+root.dataset.kind+'?q='+encodeURIComponent(query.value));select.innerHTML='<option value="">请选择</option>'+d.items.map(o=>'<option value="'+o.id+'">'+E(o.label)+'</option>').join('');if(!d.items.length)toast('没有符合条件的启用资料');}
  finally{query.disabled=false;select.disabled=false;if(submit)submit.disabled=previousDisabled;}
 }
 else if(action==='opening-example'){const c=masterContext(),example=await api('/api/masters/opening/example');c.source=example.source_text;c.batch=null;c.errors=[];await render();toast('已载入虚构示例；正式经营请换成公司确认的资料');}
 else if(action==='opening-preflight')await openingPreflight();
 else if(action==='opening-trial')await openingTrial();
 else if(action==='opening-confirm')await openingConfirm();
 else if(action==='opening-stock-export')await download('/api/masters/opening/stockflow/export','huakangos库存流水.csv');
 }catch(error){toast(error.message,true);}finally{if(el.isConnected)el.disabled=false;}});
document.addEventListener('submit',async event=>{if(event.target.id!=='typed-model-filters')return;event.preventDefault();try{const fd=new FormData(event.target),c=masterContext();c.vehicleMaxPrice=fd.get('max_price');c.vehicleFilters={fuel_type:fd.get('fuel_type'),min_seats:fd.get('min_seats'),max_price_cents:c.vehicleMaxPrice?masterFen(c.vehicleMaxPrice):''};state.page=1;await render();}catch(error){toast(error.message,true);}});
document.addEventListener('change',async event=>{if(event.target.id!=='opening-file')return;try{const file=event.target.files[0];if(!file)return;if(file.size>85000)throw new Error('单份期初资料不能超过85KB，请核对并精简到本次清单。');const source=await file.text();masterContext().source=source;$('#opening-source').value=source;}catch(error){toast(error.message,true);}});
