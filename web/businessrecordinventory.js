'use strict';
// Inventory is published by its uploader after explicit store and field review.
// All transient file and row values stay in this modal, never browser storage.
const BR_INVENTORY_API=BR_API+'/inventory';
const BR_INVENTORY_FIELDS=[['vin','车架号 / VIN'],['model','车型 / 车系'],['configuration','配置及外观和内饰颜色'],['exterior_color','独立外观颜色'],['interior_color','独立内饰颜色'],['guide_price','指导价（元）'],['production_on','生产日期'],['owner','所属店'],['location','所在地'],['funding','监管银行 / 资金性质']];
function brInventoryDate(){return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());}
function brInventoryTable(items){return table(['VIN','车型与配置','外观 / 内饰','指导价','资金性质','核对状态'],items.map(row=>[E(row.vin),E([row.model,row.configuration,row.extra_configuration].filter(Boolean).join(' · ')),E([row.exterior_color||'待补齐',row.interior_color||'待补齐'].join(' / ')),brAmount(row.guide_price_cents),E(row.is_cash_vehicle===true?'现金车':row.is_cash_vehicle===false?'非现金车':'待核对'),row.occupied?'已有合同占用':row.selectable?'可选车辆':E(row.issues.join('；'))]));}
async function renderRecordInventory(){
 const context=brContext(),catalog=await api(BR_INVENTORY_API+'/catalog');if(context!==brContext())return '';
 if(brState.inventory?.context!==context)brState.inventory={context,q:'',page:1};
 const current=brState.inventory,params=new URLSearchParams({q:current.q,page:current.page}),data=await api(BR_INVENTORY_API+'/candidates?'+params);if(context!==brContext())return '';
 const history=catalog.can_manage?await api(BR_INVENTORY_API+'/history'):{items:[]};if(context!==brContext())return '';
 return heading('车辆库存','按完整 VIN 或后 6 位查找本店当前库存',catalog.can_upload?'<button type="button" data-inventory-upload class="primary">上传并核对库存</button>':'')+
 `<section class="panel"><div class="panelbody">${brFacts([['品牌',catalog.brand],['当前版本',catalog.current?'第 '+catalog.version+' 版':'尚未发布'],['核算日期',catalog.current?.as_of_date],['当前车辆',catalog.current?.row_count??0],['本次排除',catalog.current?.excluded_count??0],['待核对未发布',catalog.current?.pending_count??0]])}<p class="br-caption">${E(catalog.notice)} 超过 180 天的车辆按核算日期与生产日期排除；缺少可靠生产日期的行暂不发布，须上传者补齐日期后重新核对。</p></div></section>`+
 `<section class="panel"><div class="panelbody"><form data-inventory-search class="br-filter"><label>车架号<input name="q" value="${E(current.q)}" maxlength="17" placeholder="完整 VIN 或后 6 位"></label><button type="submit">查询车辆</button></form>${data.notice?`<p class="notice">${E(data.notice)}</p>`:''}</div>${brInventoryTable(data.items||[])}<div class="panelbody spread"><span>共 ${data.total} 辆 · 第 ${data.page} 页</span><div class="row"><button type="button" data-inventory-page="${data.page-1}" ${data.page<=1?'disabled':''}>上一页</button><button type="button" data-inventory-page="${data.page+1}" ${data.page*data.page_size>=data.total?'disabled':''}>下一页</button></div></div></section>`+
 (catalog.can_manage?`<details class="panel br-disclosure"><summary>库存发布历史</summary>${table(['批次','工作表','核算日期','已发布','待核对未发布','排除'],history.items.map(row=>[String(row.id),E(row.sheet),E(row.as_of_date),String(row.row_count),String(row.pending_count??0),String(row.excluded_count)]))}</details>`:'');
}
async function brInventoryUpload(){
 const context=brContext(),catalog=await api(BR_INVENTORY_API+'/catalog');if(context!==brContext())return;
 if(!catalog.can_upload)throw new Error('请由本店内勤、总经理或系统管理员上传库存。');
 let upload=null,proposal=null,preview=null,reviewed=null,busy=false,uploadRequest=requestKey(),publicationRequest=requestKey();
 let groupPrices=new Map();
 const dialog=modal('上传并核对库存',`<form class="br-inventory-upload"><p class="notice">${E(catalog.brand)} · ${E(state.stores.find(s=>String(s.id)===String(catalog.store_id))?.name||'当前门店')} · 原表由上传者核对后发布。</p><label>库存 Excel<input name="file" type="file" accept=".xlsx" required></label><button type="button" data-inventory-read>读取工作表</button><p data-inventory-status role="status"></p><div data-inventory-mapping hidden><fieldset class="br-form-section"><legend>核对工作表与字段</legend><div class="formgrid"><label>车辆明细表<select name="sheet"></select></label><label>表头所在行<input name="header_row" type="number" min="1" max="20" required></label><label>库龄核算日期<input name="as_of_date" type="date" value="${E(brInventoryDate())}" required></label></div><p class="br-caption">超过 180 天按核算日期减生产日期计算。额外的 180 天明细表和汇总表不参与发布；筛选范围外的有效 VIN 也会读取。</p><div class="formgrid" data-inventory-columns></div><label><input name="configuration_contains_colors" type="checkbox">配置文本按“配置_外观_内饰_附加配置”分段读取</label><p class="br-caption">四段及以上保留附加配置，不会把附加配置误当内饰。</p></fieldset><fieldset class="br-form-section"><legend>核对所属店与资金性质</legend><p class="br-caption">只勾选本次归入当前门店的来源。监管银行、现金车、前置现金车及空白值分别核定，空白不视为非现金车。</p><div data-inventory-owners></div><div class="formgrid" data-inventory-funds></div></fieldset><button type="button" data-inventory-preview>预览并核对本批车辆</button><div data-inventory-results></div><label data-inventory-confirm-label hidden><input type="checkbox" data-inventory-confirm>已核对所属店、资金性质、车型关联、内外饰颜色及排除明细，确认替换本店当前库存</label></div><div class="formerror" role="alert"></div><div class="modalfoot"><button type="submit" class="primary" disabled>确认发布库存</button></div></form>`,async form=>{
  if(context!==brContext())throw new Error('账号或门店已切换，请重新上传。');
  if(!upload||!reviewed||!preview?.publishable)throw new Error('请先预览并解决本批错误。');
  if(JSON.stringify(readMapping())!==reviewed)throw new Error('核对内容已修改，请重新预览后发布。');
  if(!$('[data-inventory-confirm]',form).checked)throw new Error('请确认已核对本店库存及排除明细。');
  const result=await api(BR_INVENTORY_API+'/uploads/'+upload.id+'/publish',{method:'POST',body:{request_id:publicationRequest,version:catalog.version,mapping:JSON.parse(reviewed),confirmed:true,confirmed_brand:catalog.brand,confirmed_store_id:catalog.store_id}});
  if(context!==brContext())return;closeModal();await render();toast(result.notice);
 });
 const form=$('form',dialog),status=$('[data-inventory-status]',form),error=$('.formerror',form),submit=$('[type=submit]',form),mappingBox=$('[data-inventory-mapping]',form),results=$('[data-inventory-results]',form);
 const discover=document.createElement('button');discover.type='button';discover.textContent='按当前字段读取所属店与资金选项';mappingBox.querySelector('fieldset').append(discover);
 const mappingNotes=document.createElement('p');mappingNotes.className='br-caption';$('[data-inventory-columns]',form).after(mappingNotes);
 const active=()=>context===brContext()&&form.isConnected;
 const groupKey=row=>JSON.stringify([row.model,row.configuration]);
 const changed=()=>{reviewed=null;publicationRequest=requestKey();submit.disabled=true;$('[data-inventory-confirm]',form).checked=false;};
 const setBusy=value=>{busy=value;form.querySelectorAll('button,input,select').forEach(control=>{control.disabled=value;});if(!value)submit.disabled=!reviewed||!preview?.publishable;};
 const readMapping=()=>({sheet:form.elements.sheet.value,header_row:Number(form.elements.header_row.value),as_of_date:form.elements.as_of_date.value,columns:Object.fromEntries([...form.querySelectorAll('[data-inventory-column]')].filter(el=>el.value).map(el=>[el.dataset.inventoryColumn,el.value])),configuration_contains_colors:form.elements.configuration_contains_colors.checked,source_owners:[...form.querySelectorAll('[data-inventory-owner]:checked')].map(el=>el.value),funding_map:Object.fromEntries([...form.querySelectorAll('[data-inventory-fund]')].map(el=>[el.dataset.inventoryFund,el.value])),overrides:[...form.querySelectorAll('[data-inventory-row]')].map(el=>({source_row:Number(el.dataset.inventoryRow),production_on:$('[data-production]',el).value||null,exterior_color:$('[data-exterior]',el).value.trim(),interior_color:$('[data-interior]',el).value.trim(),vehicle_price_id:groupPrices.get(el.dataset.group)||null}))});
 const drawOwnership=(data,mapping)=>{
  $('[data-inventory-owners]',form).innerHTML=`<p>原表所属店（须明确勾选）</p><div class="formgrid">${data.source_owners.map(value=>`<label><input type="checkbox" data-inventory-owner value="${E(value)}" ${mapping.source_owners.includes(value)?'checked':''}>${E(value||'原表空白所属店')}</label>`).join('')}</div>`;
  const fundField=value=>`<label>${E(value||'原表空白资金性质')}<select data-inventory-fund="${E(value)}">${[['unknown','待核对'],['cash','现金车（本店自有资金购回）'],['third_party','非现金车（第三方资金）']].map(([key,label])=>`<option value="${key}" ${(mapping.funding_map[value]||'unknown')===key?'selected':''}>${label}</option>`).join('')}</select></label>`;
  const known=data.funding_values.filter(value=>['cash','third_party'].includes(mapping.funding_map[value])),unknown=data.funding_values.filter(value=>!known.includes(value));
  $('[data-inventory-funds]',form).innerHTML=unknown.map(fundField).join('')+(known.length?`<details class="br-disclosure"><summary>已核对资金性质 · ${known.length} 项（可展开修改）</summary><div class="formgrid">${known.map(fundField).join('')}</div></details>`:'');
 };
 const drawResult=data=>{
  const allRows=[...data.rows,...(data.pending||[])],groups=[...new Map(allRows.map(row=>[groupKey(row),row])).entries()];
  const defaults=data.review_defaults;
  for(const row of defaults?.model_groups||[]){const key=groupKey(row);if(!groupPrices.has(key))groupPrices.set(key,row.vehicle_price_id);}
  const unlinked=groups.filter(([key])=>!groupPrices.get(key)).length,unknownFunds=data.rows.filter(row=>row.funding_kind==='unknown').length,missingColors=data.rows.filter(row=>!row.exterior_color||!row.interior_color).length;
  const blockers=data.publication_blockers||data.errors.map(item=>item.message);
  const options=(key)=>'<option value="">待关联限价车型</option>'+data.prices.map(price=>`<option value="${price.id}" ${groupPrices.get(key)===price.id?'selected':''}>${E([price.family,price.series,price.model].join(' · '))}</option>`).join('');
  results.innerHTML=`<div class="notice"><strong>${data.publishable?'本批可以发布库存':'本批尚不能发布'}</strong><p>本次保存 ${data.row_count} 辆；生产日期待核对 ${data.pending_count||0} 辆暂不发布；排除 ${data.excluded_count} 辆。</p><p>限价车型待关联 ${unlinked} 组，资金待核对 ${unknownFunds} 辆，颜色待补齐 ${missingColors} 辆。这些车辆可以先保留库存记录，补齐前不能用于新合同。</p>${defaults?.version?`<p>已带入本店第 ${defaults.version} 版中仍有效的核对结果，请核对本次变化。</p>`:''}</div>${blockers.length?`<div role="alert"><strong>发布前须处理</strong>${blockers.map(message=>`<p class="notice warn">${E(message)}</p>`).join('')}</div>`:''}${groups.length?`<details class="br-disclosure"><summary>限价车型关联 · 待关联 ${unlinked} / 共 ${groups.length} 组（可稍后补齐）</summary><p class="br-caption">指导价不是销售管控价。只选择实际对应的已发布限价车型；没有对应车型可保持待关联，仍可发布库存。</p><label><input type="checkbox" data-inventory-unlinked checked>只看待关联配置</label>${table(['原表车型 / 配置','对应限价车型'],groups.map(([key,row])=>[E(row.model+' · '+row.configuration),`<select data-inventory-group="${E(key)}" aria-label="${E(row.model+' '+row.configuration)}">${options(key)}</select>`]))}</details>`:''}<details class="br-disclosure"><summary>车辆、颜色及生产日期 · ${allRows.length} 辆（可展开核对）</summary><div class="br-price-edit-table">${table(['原行','VIN','车型 / 配置','外观','内饰','附加配置','生产日期 / 库龄','资金','待核对'],allRows.map(row=>{const key=groupKey(row);return [String(row.source_row),E(row.vin),E(row.model+' · '+row.configuration),`<span data-inventory-row="${row.source_row}" data-group="${E(key)}"><input data-exterior maxlength="100" value="${E(row.exterior_color)}" aria-label="第 ${row.source_row} 行外观颜色"><input data-interior type="hidden" value="${E(row.interior_color)}"><input data-production type="hidden" value="${E(row.production_on||'')}"></span>`,`<input data-interior-edit="${row.source_row}" maxlength="100" value="${E(row.interior_color)}" aria-label="第 ${row.source_row} 行内饰颜色">`,E(row.extra_configuration||'—'),`<input data-production-edit="${row.source_row}" type="date" value="${E(row.production_on||'')}" aria-label="第 ${row.source_row} 行生产日期"><div class="br-caption">${row.age_days==null?'待核对，未发布':row.age_days+' 天'}</div>`,E({cash:'现金车',third_party:'非现金车',unknown:'待核对'}[row.funding_kind]),E(row.issues.join('；')||'已核对')];}))}</div></details><details class="br-disclosure"><summary>排除明细 · ${data.excluded_count} 辆</summary><p class="br-caption">${E(data.notice)}</p>${table(['原行','VIN','原因'],data.excluded.map(row=>[String(row.source_row),E(row.vin),E(row.reason)+(row.age_days==null?'':' · '+row.age_days+' 天')]))}</details>`;
  results.querySelectorAll('[data-inventory-group]').forEach(control=>{control.closest('tr').hidden=!!control.value;});
  const confirmLabel=$('[data-inventory-confirm-label]',form);confirmLabel.hidden=!data.publishable;confirmLabel.lastChild.textContent=`已核对所属店及待补齐事项：本次仅发布 ${data.row_count} 辆，待核对 ${data.pending_count||0} 辆不发布，排除 ${data.excluded_count} 辆；确认替换当前库存，缺行不代表已售`;
 };
 const previewMapping=async(discover=false)=>{
  if(!active()||busy)return;setBusy(true);error.textContent='';changed();
  try{let mapping=readMapping();if(discover)mapping={...mapping,source_owners:[],funding_map:{},overrides:[]};
   status.textContent='正在核对来源与车辆…';const data=await api(BR_INVENTORY_API+'/uploads/'+upload.id+'/preview',{method:'POST',body:mapping});if(!active())return;
   if(discover){const defaults=data.review_defaults;mapping={...mapping,source_owners:defaults?.source_owners||[],funding_map:defaults?.funding_map||{}};}
   preview=data;drawOwnership(data,mapping);drawResult(data);reviewed=discover?null:JSON.stringify(readMapping());
   // A first preview adds explicit colour overrides. Revalidate those values
   // before enabling publication, rather than publishing an unseen request.
   if(!discover&&JSON.stringify(mapping)!==reviewed){const finalData=await api(BR_INVENTORY_API+'/uploads/'+upload.id+'/preview',{method:'POST',body:JSON.parse(reviewed)});if(!active())return;preview=finalData;drawResult(finalData);}
   status.textContent=discover?'请核对所属店与资金性质，然后预览；已发布过的相同来源会带入上次选择。':preview.publishable?'本批可以发布；未关联车型等可后续补齐，请勾选确认后发布。':'请处理“发布前须处理”中的事项后重新预览。';
  }catch(e){if(active()){error.textContent=e.message;reviewed=null;}}finally{if(active())setBusy(false);}
 };
 const selectSheet=()=>{
  proposal=upload.sheets.find(item=>item.sheet===form.elements.sheet.value);if(!proposal)return;
  mappingNotes.textContent=(proposal.mapping_notes||[]).join(' ');
  form.elements.header_row.value=proposal.header_row||1;form.elements.configuration_contains_colors.checked=proposal.configuration_contains_colors===true;
  $('[data-inventory-columns]',form).innerHTML=BR_INVENTORY_FIELDS.map(([key,label])=>`<label>${E(label)}<select data-inventory-column="${key}"><option value="">未提供</option>${Object.entries(proposal.headers).map(([column,name])=>`<option value="${column}" ${proposal.columns[key]===column?'selected':''}>${E(column+' · '+name)}</option>`).join('')}</select></label>`).join('');
  groupPrices=new Map();preview=null;results.replaceChildren();$('[data-inventory-owners]',form).replaceChildren();$('[data-inventory-funds]',form).replaceChildren();changed();
 };
 $('[data-inventory-read]',form).onclick=async()=>{if(busy)return;setBusy(true);changed();error.textContent='';try{
  const file=form.elements.file.files[0];if(!file||!file.size||file.size>10*1024*1024||!file.name.toLowerCase().endsWith('.xlsx'))throw new Error('请选择不超过 10MB 的库存 xlsx 文件。');
  const body=new FormData();body.set('file',file);body.set('request_id',uploadRequest);status.textContent='正在读取库存原表…';const saved=await api(BR_INVENTORY_API+'/uploads',{method:'POST',body});if(!active())return;upload=saved;
  if(!saved.available)throw new Error('原件已保存但尚未通过文件检查，当前不能发布。');
  form.elements.sheet.innerHTML=saved.sheets.map(item=>`<option value="${E(item.sheet)}" ${item.auxiliary?'disabled':''}>${E(item.sheet+(item.auxiliary?'（辅助表，不发布）':''))}</option>`).join('');
  const first=saved.sheets.find(item=>!item.auxiliary&&item.columns.vin)||saved.sheets.find(item=>!item.auxiliary);if(!first)throw new Error('没有可发布的原始车辆明细表。');form.elements.sheet.value=first.sheet;
  mappingBox.hidden=false;selectSheet();status.textContent='已读取工作表，请核对字段。';
 }catch(e){if(active())error.textContent=e.message;}finally{if(active())setBusy(false);}if(upload?.available&&active())await previewMapping(true);};
 $('[data-inventory-preview]',form).onclick=()=>previewMapping(false);
 discover.onclick=()=>previewMapping(true);
 form.elements.sheet.onchange=async()=>{selectSheet();await previewMapping(true);};
 form.elements.file.onchange=()=>{upload=null;preview=null;reviewed=null;uploadRequest=requestKey();publicationRequest=requestKey();mappingBox.hidden=true;results.replaceChildren();submit.disabled=true;status.textContent='';error.textContent='';};
 form.addEventListener('input',event=>{if(event.target.matches('[data-inventory-confirm],[data-inventory-unlinked],input[type=file]'))return;if(event.target.dataset.productionEdit){const row=form.querySelector(`[data-inventory-row="${event.target.dataset.productionEdit}"]`);$('[data-production]',row).value=event.target.value;}if(event.target.dataset.interiorEdit){const row=form.querySelector(`[data-inventory-row="${event.target.dataset.interiorEdit}"]`);$('[data-interior]',row).value=event.target.value;}changed();});
 form.addEventListener('change',event=>{if(event.target.hasAttribute('data-inventory-unlinked')){results.querySelectorAll('[data-inventory-group]').forEach(control=>{control.closest('tr').hidden=event.target.checked&&!!control.value;});return;}if(event.target.hasAttribute('data-inventory-group'))groupPrices.set(event.target.dataset.inventoryGroup,Number(event.target.value)||null);if(!event.target.matches('[data-inventory-confirm],input[type=file]'))changed();});
 return dialog;
}
document.addEventListener('submit',async event=>{const form=event.target.closest('[data-inventory-search]');if(!form)return;event.preventDefault();const context=brContext();brState.inventory={context,q:form.elements.q.value.trim().toUpperCase(),page:1};try{await render();}catch(e){toast(e.message,true);}});
document.addEventListener('click',async event=>{const button=event.target.closest('[data-inventory-upload],[data-inventory-page]');if(!button||button.disabled||state.storeSwitch)return;button.disabled=true;try{if(button.hasAttribute('data-inventory-upload'))await brInventoryUpload();else{brState.inventory.page=Number(button.dataset.inventoryPage);await render();}}catch(e){toast(e.message,true);}finally{if(button.isConnected)button.disabled=false;}});
