'use strict';
// Catalogs are shared by the store's configured brand; profiles remain store-local.
// A preview is never a publication. Publish against the version originally reviewed.
async function brPricingCatalog(contractId){return api(BR_API+'/pricing/catalog'+(contractId?'?contract_id='+contractId:''));}
function brBrandPublication(catalog){
 if(!catalog.brand)throw new Error('本店未设置品牌，请联系系统管理员。');
 if(!Number.isInteger(catalog.brand_version)||catalog.brand_version<0)throw new Error('未能读取品牌目录版本，请刷新后重新核对。');
 return {brand:catalog.brand,brand_version:catalog.brand_version};
}
function brFlowButton(action,label,extra='',cls=''){return `<button type="button" data-br-flow="${E(action)}" ${extra} class="${E(cls)}">${E(label)}</button>`;}
function brVehiclePolicySummary(policy,canViewAmounts){
 if(!policy)return '未设置金额限制';
 const amount=canViewAmounts&&policy.cost_limit_cents!=null?'成本额度 '+brAmount(policy.cost_limit_cents):policy.has_cost_limit?'已设置赠品政策':'';
 const standard=(policy.standard_gifts||[]).map(g=>`${g.name} × ${g.quantity}${g.unit?' '+g.unit:''}`).join('、');
 return `${amount?`<div>${E(amount)}</div>`:''}${standard?`<div>标准赠品：${E(standard)}</div>`:''}${policy.standard_gift_note?`<p class="br-source-note">${E(policy.standard_gift_note)}</p>`:''}${policy.standard_gifts_status==='outdated'?'<div class="br-caption">标准赠品目录已更新，需重新核对关联。</div>':''}${policy.text?`<details><summary>政策内容</summary><p class="br-source-note">${E(policy.text)}</p></details>`:''}`;
}
function brVehicleGiftPolicy(values,index,standardGifts=[]){
 const label='第 '+(index+1)+' 行';
 if(!['none','limit'].includes(values.policy_mode))throw new Error(label+'请选择赠品政策。');
 const text=String(values.policy_text??'');if([...text].length>3000)throw new Error(label+'的赠品政策不能超过 3000 字。');
 const standard_gift_note=String(values.standard_gift_note??'').trim();if([...standard_gift_note].length>3000)throw new Error(label+'的销售可见适用说明不能超过 3000 字。');
 if(standardGifts.length>100)throw new Error(label+'的标准赠品不能超过 100 项。');
 const seen=new Set(),standard_gifts=standardGifts.map(g=>{
  const id=String(g.price_id??''),count=String(g.quantity??'');
  if(!/^[1-9]\d*$/.test(id)||!Number.isSafeInteger(Number(id)))throw new Error(label+'请选择标准赠品。');
  if(!/^[1-9]\d*$/.test(count)||Number(count)>10000)throw new Error(label+'的标准赠品数量须为 1 至 10000 的整数。');
  const price_id=Number(id);if(seen.has(price_id))throw new Error(label+'的标准赠品重复，请合并数量。');seen.add(price_id);return {price_id,quantity:Number(count)};
 });
 if(values.policy_mode==='none')return standard_gifts.length||standard_gift_note?{text,cost_limit_cents:null,standard_gifts,standard_gift_note}:null;
 const amount=String(values.policy_limit??'').trim();if(!amount)throw new Error(label+'请填写赠品成本额度，零额度请填 0。');
 return {text,cost_limit_cents:moneyFen(amount,{label:label+' 赠品成本额度',allowZero:true}),standard_gifts,standard_gift_note};
}
function brPricingSection(kind,title,body,upload,caption=''){
 const context=brContext();if(brState.pricingSections?.context!==context)brState.pricingSections={context};
 const expanded=brState.pricingSections[kind]===true,id='br-pricing-'+kind;
 return `<section class="panel br-pricing-section"><div class="panelhead spread"><div><h2><button type="button" class="br-pricing-toggle" data-price-toggle="${kind}" aria-expanded="${expanded}" aria-controls="${id}"><span>${E(title)}</span><span class="br-pricing-toggle-label">${expanded?'收起':'展开'}</span></button></h2>${caption?`<p class="br-caption">${E(caption)}</p>`:''}</div>${upload}</div><div id="${id}" ${expanded?'':'hidden'}>${body}</div></section>`;
}
async function brPricingSettings(){
 const context=brContext(),data=await brPricingCatalog();if(context!==brContext())return '';brState.pricing=data;
 const profile=data.profile||{},vehicles=data.vehicles||[],gifts=data.gifts||[],vehicleNotes=vehicles.some(v=>v.note);
 return heading('门店基础资料','',brLink('records-sales','返回销售业务'))+
 `<section class="panel"><div class="panelhead spread"><h2>门店与卖方</h2><div class="row">${data.can_manage_profile?brFlowButton('store-profile','编辑资料')+brFlowButton('vehicle-variant','添加车型',data.brand?'':'disabled'):''}</div></div><div class="panelbody">${brFacts([['经营品牌',data.brand||'未设置'],['目录版本',data.brand?'版本 '+data.brand_version:'待设置品牌'],['发布范围',data.brand?'同品牌门店':'待设置品牌'],['本店地址',profile.address],['卖方公司',(profile.sellers||[]).map(s=>s.name).join('、')]])}</div></section>`+
 brPricingSection('vehicle',`车型限价 · ${vehicles.length} 款`,table(['车系','年款 / 系列','车型配置','指导价','销售管控价','赠品政策',...(vehicleNotes?['条件与来源']:[])],vehicles.map(v=>[E(v.family),E(v.series),E(v.model),brAmount(v.guide_price_cents),brAmount(v.control_price_cents),brVehiclePolicySummary(v.gift_policy,data.can_view_gift_amounts),...(vehicleNotes?[v.note?`<details><summary>查看说明</summary><p class="br-source-note">${E(v.note)}</p></details>`:'—']:[])])),data.can_import_vehicle?brFlowButton('price-upload','上传限价表','data-kind="vehicle"','primary'):'',vehicles.length?'':data.brand?'暂无已发布限价':'本店未设置品牌')+
 brPricingSection('gift',`赠品目录 · ${gifts.length} 项`,table(['赠品','品牌','单位','适用车型',...(data.can_view_gift_amounts?['售价']:[]),...(data.can_view_gift_costs?['成本','说明']:[])],gifts.map(g=>[E(g.name),E(g.brand||profile.brand),E(g.unit||'—'),E(g.applicable_models||'—'),...(data.can_view_gift_amounts?[g.unit_price_cents==null?'待补齐':brAmount(g.unit_price_cents)]:[]),...(data.can_view_gift_costs?[g.unit_cost_cents==null?'待补齐':brAmount(g.unit_cost_cents),E(g.note||'—')]:[])])),data.can_import_gifts?brFlowButton('price-upload','上传赠品表','data-kind="gift"','primary'):'');
}
function brValidatePricingFile(file,kind){
 if(!file)throw new Error('请选择价格表文件。');
 if(!file.size||file.size>10*1024*1024)throw new Error('价格文件不能为空且不得超过 10MB。');
 if(!file.name||[...file.name].length>180||/[\\/\x00-\x1f:]/.test(file.name))throw new Error('请使用简短有效的文件名。');
 if(!(kind==='vehicle'?/\.xlsx$/i:/\.(xlsx|csv)$/i).test(file.name))throw new Error(kind==='vehicle'?'限价表请上传 Excel（.xlsx）文件。':'赠品表请上传 Excel（.xlsx）或 UTF-8 CSV 文件。');
 return file;
}
function brVehicleReviewRow(values,index){
 const row=Object.fromEntries(['family','series','model','note'].map(key=>[key,String(values[key]??'').trim()])),label='第 '+(index+1)+' 行';
 for(const [key,name,maximum] of [['family','车系',100],['series','年款 / 系列',160],['model','车型配置',160],['note','说明',2000]]){
  if(key!=='note'&&!row[key])throw new Error(label+'的'+name+'不能为空。');
  if([...row[key]].length>maximum)throw new Error(label+'的'+name+'不能超过 '+maximum+' 字。');
 }
 if([...(row.series+' '+row.model)].length>160)throw new Error(label+'的年款 / 系列与车型配置合计不能超过 160 字。');
 for(const [key,name] of [['guide_price_cents','指导价'],['control_price_cents','销售管控价']]){
  const value=String(values[key]??'').trim();if(!value)throw new Error(label+'的'+name+'不能为空。');
  row[key]=moneyFen(value,{label:label+' '+name});if(row[key]<=0)throw new Error(label+'的'+name+'必须大于零。');
 }
 return row;
}
function brUniqueVehicleReviewRows(rows){
 if(!rows.length||rows.length>2000)throw new Error('请保留 1 至 2000 行车型。');
 const seen=new Set();rows.forEach((row,i)=>{const key=JSON.stringify([row.family,row.series,row.model]);if(seen.has(key))throw new Error('第 '+(i+1)+' 行车型重复，请核对车系、年款 / 系列和车型配置。');seen.add(key);});return rows;
}
async function brPricingUpload(kind){
 if(!['vehicle','gift'].includes(kind))throw new Error('价格表用途不正确。');
 const context=brContext(),catalog=await brPricingCatalog();let requestId=requestKey();if(context!==brContext())return;
 if(!(kind==='vehicle'?catalog.can_import_vehicle:catalog.can_import_gifts))throw new Error('当前岗位不能上传此价格目录。');
 const scope=brBrandPublication(catalog);let upload=null,rows=null,edits=[],publicationId=requestKey(),pending=false;
 const policyFields=(prefix)=>`<label>赠品政策<select data-${prefix}-mode><option value="">待确认</option><option value="limit">按成本额度</option><option value="none">无金额限制</option></select></label><label>政策内容<textarea data-${prefix}-text rows="3" maxlength="3000"></textarea></label><label>成本额度（元）<input data-${prefix}-limit inputmode="decimal"></label>`;
 const giftReference=kind==='vehicle'&&catalog.can_view_gift_amounts?`<details class="br-disclosure"><summary>赠品售价参考 · ${(catalog.gifts||[]).length} 项</summary>${table(['赠品','适用车型','单位','售价'],(catalog.gifts||[]).map(g=>[E(g.name),E(g.applicable_models||'—'),E(g.unit||'—'),g.unit_price_cents==null?'待补齐':brAmount(g.unit_price_cents)]))}</details>`:'';
 const dialog=modal(kind==='vehicle'?'上传限价表':'上传赠品表',`<form class="br-pricing-upload"><p class="notice">${E(scope.brand)} · 版本 ${scope.brand_version} · 同品牌门店共享</p><label>${kind==='vehicle'?'选择 Excel 文件':'选择 Excel / CSV 文件'}<input type="file" name="file" accept="${kind==='vehicle'?'.xlsx':'.xlsx,.csv'}" required></label><p class="br-caption">单个文件不超过 10MB；上传后核对并确认发布才会生效。</p><button type="button" data-price-recognize>${kind==='vehicle'?'上传并识别':'上传并预览'}</button><p data-price-status role="status"></p><div data-price-warnings></div>${kind==='vehicle'?`<div data-policy-tools hidden><details><summary>批量设置赠品政策</summary><div class="formgrid">${policyFields('policy-bulk')}</div><button type="button" data-policy-apply>应用到勾选车型</button></details>${giftReference}</div>`:''}<div class="br-price-edit-table" data-price-rows></div>${kind==='vehicle'?'<label data-policy-confirm-label hidden><input type="checkbox" data-policy-confirm>已逐行核对车价、标准赠品、销售可见说明及成本额度</label>':''}<div class="formerror" role="alert"></div><div class="modalfoot"><button type="submit" class="primary" disabled>确认发布</button></div></form>`,async form=>{
  if(context!==brContext())throw new Error('账号或门店已切换，请重新上传。');
  if(!upload||!rows)throw new Error('请先上传并核对价格表。');
  const text=(i,key)=>form.querySelector(`[data-price-index="${i}"][data-price-key="${key}"]`).value.trim();
  const optionalAmount=(i,key)=>text(i,key)===''?null:moneyFen(text(i,key),{label:'第 '+(i+1)+' 行金额',allowZero:true});
  const confirmed=rows.map((_,i)=>kind==='vehicle'?{...brVehicleReviewRow(Object.fromEntries(['family','series','model','guide_price_cents','control_price_cents','note'].map(key=>[key,text(i,key)])),i),gift_policy:brVehicleGiftPolicy(Object.fromEntries(['policy_mode','policy_text','policy_limit','standard_gift_note'].map(key=>[key,form.querySelector(`[data-price-index="${i}"][data-price-key="${key}"]`).value])),i,readStandardGifts(i))}:{name:text(i,'name'),brand:text(i,'brand'),unit:text(i,'unit'),applicable_models:text(i,'applicable_models'),unit_price_cents:optionalAmount(i,'unit_price_cents'),...(catalog.can_view_gift_costs?{unit_cost_cents:optionalAmount(i,'unit_cost_cents'),source_ref:text(i,'source_ref'),note:text(i,'note')}:{} )});
  if(kind==='vehicle'){brUniqueVehicleReviewRows(confirmed);if(!$('[data-policy-confirm]',form).checked)throw new Error('请勾选确认已核对车价及赠品政策。');}
  await api(BR_API+'/pricing/'+(kind==='vehicle'?'vehicle':'gifts')+'/import',{method:'POST',body:{request_id:publicationId,version:catalog.version,...scope,file_id:upload.id,rows:confirmed,...(kind==='vehicle'?{policy_confirmed:true}:{})}});
  if(context!==brContext())return;closeModal();await render();toast(scope.brand+'目录已更新');
 });
 const form=$('form',dialog),recognize=$('[data-price-recognize]',form),submit=$('[type=submit]',form),status=$('[data-price-status]',form),error=$('.formerror',form),rowArea=$('[data-price-rows]',form);
 const keys=kind==='vehicle'?[['family','车系'],['series','年款 / 系列'],['model','车型配置'],['guide_price_cents','指导价（元）'],['control_price_cents','销售管控价（元）'],['note','条件 / 核对说明']]:[['name','赠品名称'],['brand','品牌'],['unit','单位'],['applicable_models','适用车型'],['unit_price_cents','售价（元，未知留空）'],...(catalog.can_view_gift_costs?[['unit_cost_cents','成本（元，未知留空）'],['source_ref','来源位置'],['note','说明']]:[])];
 const policyKeys=['policy_mode','policy_text','policy_limit','standard_gift_note'];
 const policyValue=(row,i,key)=>edits[i]?.[key]??(key==='policy_text'?row.gift_policy_suggestion?.text||'':key==='policy_limit'?brInputAmount(row.gift_policy_suggestion?.cost_limit_cents):'');
 const standardGiftRow=gift=>`<div data-standard-gift-row><label>标准赠品<select data-standard-gift-id required><option value="">请选择赠品</option>${(catalog.gifts||[]).map(g=>`<option value="${g.id}" ${String(gift.price_id??'')===String(g.id)?'selected':''}>${E([g.name,g.applicable_models,g.unit].filter(Boolean).join(' · '))}</option>`).join('')}</select></label><label>数量<input data-standard-gift-quantity type="number" min="1" max="10000" step="1" required value="${E(gift.quantity??1)}"></label><button type="button" data-standard-gift-remove>移除赠品</button></div>`;
 const readStandardGifts=i=>[...form.querySelectorAll(`[data-standard-gifts="${i}"] [data-standard-gift-row]`)].map(row=>({price_id:$('[data-standard-gift-id]',row).value,quantity:$('[data-standard-gift-quantity]',row).value}));
 const policyCell=(row,i)=>{const mode=policyValue(row,i,'policy_mode'),attrs=key=>`data-price-index="${i}" data-price-key="${key}" aria-label="第 ${i+1} 行${({policy_mode:'赠品政策',policy_text:'政策内容',policy_limit:'成本额度（元）',standard_gift_note:'销售可见适用说明'})[key]}"`;
  return `${row.gift_policy_suggestion?.text?`<details><summary>识别原文参考</summary><p class="br-source-note">${E(row.gift_policy_suggestion.text)}</p></details>`:''}<label>赠品政策<select ${attrs('policy_mode')} required>${[['','待确认'],['limit','按成本额度'],['none','无金额限制']].map(([value,label])=>`<option value="${value}" ${mode===value?'selected':''}>${label}</option>`).join('')}</select></label><label>政策内容<textarea ${attrs('policy_text')} rows="4" maxlength="3000">${E(policyValue(row,i,'policy_text'))}</textarea></label><label>成本额度（元）<input ${attrs('policy_limit')} inputmode="decimal" value="${E(policyValue(row,i,'policy_limit'))}" ${mode==='limit'?'required':'disabled'}></label><details><summary>标准赠品</summary><p class="br-caption">从当前赠品目录人工选择；合同默认勾选，填写合同时可取消或调整数量。</p><label>销售可见适用说明<textarea ${attrs('standard_gift_note')} rows="3" maxlength="3000" placeholder="例如首保或 NPS 条件；勿填写金额、成本或内部返佣">${E(policyValue(row,i,'standard_gift_note'))}</textarea></label><div data-standard-gifts="${i}">${(edits[i]?.standard_gifts||[]).map(standardGiftRow).join('')}</div><button type="button" data-standard-gift-add="${i}" ${(catalog.gifts||[]).length?'':'disabled'}>添加标准赠品</button>${(catalog.gifts||[]).length?'':'<p class="br-caption">请先发布赠品目录，再关联标准赠品。</p>'}</details>`;};
 const resetConfirmation=()=>{const check=$('[data-policy-confirm]',form);if(check)check.checked=false;};
 const input=(row,i,key,label)=>{
  const attrs=`data-price-index="${i}" data-price-key="${key}" aria-label="第 ${i+1} 行${E(label)}"`;
  const value=edits[i]?.[key]??(key.endsWith('_cents')?brInputAmount(row[key]):row[key]??(key==='brand'?catalog.profile?.brand||'':''));
  if(key==='note')return `<textarea ${attrs} rows="3" maxlength="2000">${E(value)}</textarea>`;
  return `<input ${attrs} value="${E(value)}" ${(kind==='vehicle'?key!=='note':['name','brand'].includes(key))?'required':''} ${key.endsWith('_cents')?'inputmode="decimal"':''}>`;
 };
 const captureEdits=()=>{edits=(rows||[]).map((_,i)=>({...Object.fromEntries([...keys.map(([key])=>key),...(kind==='vehicle'?policyKeys:[])].map(key=>[key,form.querySelector(`[data-price-index="${i}"][data-price-key="${key}"]`).value])),...(kind==='vehicle'?{selected:!!form.querySelector(`[data-policy-select="${i}"]`)?.checked,standard_gifts:readStandardGifts(i)}:{})}));};
 const draw=()=>{rowArea.innerHTML=table([...(kind==='vehicle'?['选择']:[]),'行',...keys.map(k=>k[1]),...(kind==='vehicle'?['赠品政策','操作']:[])],rows.map((row,i)=>[...(kind==='vehicle'?[`<input type="checkbox" data-policy-select="${i}" aria-label="选择第 ${i+1} 行车型" ${edits[i]?.selected?'checked':''}>`]:[]),String(i+1)+(row.source?'<small class="br-caption">'+E(row.source)+'</small>':''),...keys.map(([key,label])=>input(row,i,key,label)),...(kind==='vehicle'?[policyCell(row,i),`<button type="button" data-price-remove="${i}" aria-label="移除预览第 ${i+1} 行" ${pending?'disabled':''}>移除</button>`]:[])]));if(kind==='vehicle'){rowArea.insertAdjacentHTML('afterbegin','<label><input type="checkbox" data-policy-select-all>全选车型</label>');$('[data-policy-tools]',form).hidden=!rows.length;$('[data-policy-confirm-label]',form).hidden=!rows.length;resetConfirmation();}submit.disabled=pending||!rows.length;status.textContent='待核对 '+rows.length+' 项';};
 const manual=document.createElement('button');manual.type='button';manual.textContent=kind==='vehicle'?'手工添加车型':'手工添加赠品';manual.hidden=true;recognize.after(manual);manual.onclick=()=>{if(!upload||pending||form.dataset.submitting==='true')return;captureEdits();rows=rows||[];rows.push({});edits.push({});draw();};
 rowArea.addEventListener('click',event=>{const button=event.target.closest('[data-price-remove]');if(!button||button.disabled||pending)return;captureEdits();const index=Number(button.dataset.priceRemove);rows.splice(index,1);edits.splice(index,1);draw();});
 rowArea.addEventListener('click',event=>{const button=event.target.closest('[data-standard-gift-add],[data-standard-gift-remove]');if(!button||button.disabled||pending||form.dataset.submitting==='true')return;if(button.hasAttribute('data-standard-gift-add')){const group=form.querySelector(`[data-standard-gifts="${button.dataset.standardGiftAdd}"]`);group.insertAdjacentHTML('beforeend',standardGiftRow({}));group.lastElementChild.querySelector('select').focus();}else button.closest('[data-standard-gift-row]').remove();resetConfirmation();});
 rowArea.addEventListener('input',event=>{if(event.target.matches('[data-price-key],[data-standard-gift-id],[data-standard-gift-quantity]'))resetConfirmation();});
 rowArea.addEventListener('change',event=>{if(event.target.matches('[data-standard-gift-id],[data-standard-gift-quantity]'))resetConfirmation();if(event.target.matches('[data-policy-select-all]'))rowArea.querySelectorAll('[data-policy-select]').forEach(check=>{check.checked=event.target.checked;});if(event.target.dataset.priceKey==='policy_mode'){const i=event.target.dataset.priceIndex,mode=event.target.value,limit=form.querySelector(`[data-price-index="${i}"][data-price-key="policy_limit"]`);limit.disabled=mode!=='limit';limit.required=mode==='limit';resetConfirmation();}});
 if(kind==='vehicle'){
  const mode=$('[data-policy-bulk-mode]',form),limit=$('[data-policy-bulk-limit]',form),text=$('[data-policy-bulk-text]',form);
  const updateBulk=()=>{limit.disabled=mode.value!=='limit';text.disabled=mode.value==='none';};mode.onchange=updateBulk;updateBulk();
  $('[data-policy-apply]',form).onclick=()=>{if(pending||form.dataset.submitting==='true')return;try{captureEdits();const selected=edits.map((edit,i)=>edit.selected?i:-1).filter(i=>i>=0);if(!selected.length)throw new Error('请先勾选车型。');const values={policy_mode:mode.value,policy_text:text.value,policy_limit:limit.value};brVehicleGiftPolicy(values,selected[0]);for(const i of selected)Object.assign(edits[i],values);draw();error.textContent='';}catch(e){error.textContent=e.message;}};
 }
 const busy=value=>{pending=value;recognize.disabled=value;manual.disabled=value;form.elements.file.disabled=value;submit.disabled=value||!rows?.length;rowArea.querySelectorAll('[data-price-remove]').forEach(button=>{button.disabled=value;});};
 const uploadOriginal=async()=>{
  if(context!==brContext())throw new Error('门店已切换。');const file=brValidatePricingFile(form.elements.file.files[0],kind);
  if(!upload){const activeRequest=requestId,body=new FormData();body.set('file',file);body.set('kind',kind);body.set('request_id',activeRequest);status.textContent='正在上传原表…';const saved=await api(BR_API+'/pricing/uploads',{method:'POST',body});if(context!==brContext()||!form.isConnected)return false;if(activeRequest!==requestId||file!==form.elements.file.files[0])throw new Error('原表已更换，请重新上传当前文件。');upload=saved;}
  if(context!==brContext()||!form.isConnected)return false;
  if(upload.available!==true)throw new Error('原表尚不可用于发布，请联系管理员检查文件状态。');manual.hidden=false;return true;
 };
 form.elements.file.onchange=()=>{upload=null;rows=null;edits=[];requestId=requestKey();publicationId=requestKey();manual.hidden=true;submit.disabled=true;rowArea.replaceChildren();if(kind==='vehicle'){$('[data-policy-tools]',form).hidden=true;$('[data-policy-confirm-label]',form).hidden=true;resetConfirmation();}$('[data-price-warnings]',form).replaceChildren();status.textContent='';error.textContent='';};
 recognize.onclick=async()=>{if(pending||form.dataset.submitting==='true')return;busy(true);submit.disabled=true;error.textContent='';try{
  if(!await uploadOriginal())return;
  status.textContent=kind==='vehicle'?'正在识别销售管控价…':'正在读取赠品目录…';
  const activeUpload=upload.id,result=await api(BR_API+'/pricing/uploads/'+activeUpload+'/recognize',{method:'POST',body:{request_id:requestKey(),version:upload.version}});
  if(context!==brContext()||!form.isConnected)return;if(upload?.id!==activeUpload)throw new Error('原表已更换，请重新核对当前文件。');if(!Array.isArray(result.rows)||!result.rows.length)throw new Error('未识别到项目，请手工补充或更换原表。');rows=result.rows;edits=[];
  draw();
  $('[data-price-warnings]',form).innerHTML=(result.warnings||[]).map(w=>`<p class="notice warn">${E(typeof w==='string'?w:JSON.stringify(w))}</p>`).join('');publicationId=requestKey();
 }catch(e){error.textContent=e.message;status.textContent=rows?.length?'本次识别未完成，已保留当前核对内容；尚未发布。':upload?.available===true?'原表已保存，尚未发布；可重试或手工添加并核对。':'尚未生效，原有效目录不变。';}finally{if(form.isConnected)busy(false);}};
}
async function brStoreProfileEdit(){
 const context=brContext(),data=await api(BR_API+'/store-profile');if(context!==brContext())return;
 const p=data.profile||data,people=state.recordCatalog.sales_people||[],fields=[F('address','本店地址'),...people.map(s=>F('contact_'+s.id,s.label+' · 联系电话','text',false))];
 const draftKey='store-profile-'+p.brand+'-'+data.version,existing=brState.drafts[draftKey],draft=existing?.context===context?existing:null,request_id=draft?.request_id||requestKey();
 const initial=draft?.values||{address:p.address,sellers:p.sellers||[],...Object.fromEntries(people.map(s=>['contact_'+s.id,p.sales_contacts?.[String(s.id)]||'']))};
 const controls=await Promise.all(fields.map(f=>fieldHTML(f,initial[f.key]||'')));
 if(context!==brContext())return;
 const sellerRow=seller=>`<div class="br-form-section" data-seller-row><div class="formgrid"><label>公司名称<input data-seller-name value="${E(seller.name||'')}" maxlength="160" required></label><label>公司地址<input data-seller-address value="${E(seller.address||'')}" maxlength="500"></label></div><button type="button" data-seller-remove>移除公司</button></div>`;
 const collect=form=>({...formValues(form,fields),sellers:[...form.querySelectorAll('[data-seller-row]')].map(row=>({name:$('[data-seller-name]',row).value.trim(),address:$('[data-seller-address]',row).value.trim()}))});
 const dialog=modal('门店基础资料',`<form data-br-form="${E(draftKey)}"><p class="notice">经营品牌：${E(p.brand||'未设置')}</p><fieldset class="br-form-section"><legend>门店地址</legend><div class="formgrid">${controls[0]}</div></fieldset><fieldset class="br-form-section"><legend>卖方公司</legend><div data-sellers>${(Array.isArray(initial.sellers)?initial.sellers:[]).map(sellerRow).join('')}</div><button type="button" data-seller-add>添加公司</button></fieldset>${people.length?`<fieldset class="br-form-section"><legend>销售联系方式</legend><div class="formgrid">${controls.slice(1).join('')}</div></fieldset>`:''}<div class="formerror" role="alert"></div><div class="modalfoot">${brButton('defer-form','稍后再填')}<button type="submit" class="primary">保存</button></div></form>`,async form=>{
  if(context!==brContext())throw new Error('门店或账号已切换，请重新打开。');
  const v=collect(form);brState.drafts[draftKey]={context,request_id,values:v};
  if(v.sellers.some(s=>!s.name))throw new Error('请填写公司名称。');
  await api(BR_API+'/store-profile',{method:'PUT',body:{request_id,version:data.version,brand:p.brand,address:v.address,sellers:v.sellers,sales_contacts:Object.fromEntries(people.map(s=>[String(s.id),v['contact_'+s.id]]))}});
  if(context!==brContext())return;delete brState.drafts[draftKey];closeModal();await render();toast('已保存');
 });
 const form=$('form',dialog),sellers=$('[data-sellers]',form),add=$('[data-seller-add]',form),remember=()=>{brState.drafts[draftKey]={context,request_id,values:collect(form)};};
 const updateLimit=()=>{add.disabled=sellers.querySelectorAll('[data-seller-row]').length>=50;};
 add.onclick=()=>{if(form.dataset.submitting==='true'||add.disabled)return;sellers.insertAdjacentHTML('beforeend',sellerRow({}));updateLimit();remember();sellers.lastElementChild.querySelector('[data-seller-name]').focus();};
 sellers.addEventListener('click',event=>{const button=event.target.closest('[data-seller-remove]');if(!button||form.dataset.submitting==='true')return;button.closest('[data-seller-row]').remove();updateLimit();remember();});
 form.addEventListener('input',remember);form.addEventListener('change',remember);updateLimit();return dialog;
}
async function brVehicleVariant(){const context=brContext(),data=await brPricingCatalog();if(context!==brContext())return;const scope=brBrandPublication(data);return brForm('添加车型',[{title:'车型',fields:[F('family','车系'),F('series','年款 / 系列'),F('model','车型配置')]}],{},(v,request_id)=>api(BR_API+'/vehicle-variants',{method:'POST',body:{...v,request_id,version:data.version,...scope}}),{draftKey:'vehicle-variant-'+scope.brand+'-'+scope.brand_version,notice:scope.brand+' · 版本 '+scope.brand_version+' · 同品牌门店共享'});}
document.addEventListener('click',async event=>{
 const toggle=event.target.closest('[data-price-toggle]');if(toggle&&!state.storeSwitch){const body=document.getElementById(toggle.getAttribute('aria-controls'));if(!body)return;const expanded=toggle.getAttribute('aria-expanded')!=='true';toggle.setAttribute('aria-expanded',String(expanded));toggle.querySelector('.br-pricing-toggle-label').textContent=expanded?'收起':'展开';body.hidden=!expanded;const context=brContext();if(brState.pricingSections?.context!==context)brState.pricingSections={context};brState.pricingSections[toggle.dataset.priceToggle]=expanded;return;}
 const el=event.target.closest('[data-br-flow]');if(!el||el.disabled||state.storeSwitch)return;const a=el.dataset.brFlow;if(!['price-upload','store-profile','vehicle-variant'].includes(a))return;el.disabled=true;try{if(a==='price-upload')await brPricingUpload(el.dataset.kind);if(a==='store-profile')await brStoreProfileEdit();if(a==='vehicle-variant')await brVehicleVariant();}catch(error){toast(error.message,true);}finally{if(el.isConnected)el.disabled=false;}
});
