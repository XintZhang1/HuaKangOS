'use strict';
// Catalogs are shared by the store's configured brand; profiles remain store-local.
// A preview is never a publication. Publish against the version originally reviewed.
async function brPricingCatalog(contractId){return api(BR_API+'/pricing/catalog'+(contractId?'?contract_id='+contractId:''));}
function brBrandPublication(catalog){
 if(!catalog.brand)throw new Error('本店尚未设置经营品牌，请联系系统管理员在门店设置中补齐。');
 if(!Number.isInteger(catalog.brand_version)||catalog.brand_version<0)throw new Error('未能读取品牌目录版本，请刷新后重新核对。');
 return {brand:catalog.brand,brand_version:catalog.brand_version};
}
function brFlowButton(action,label,extra='',cls=''){return `<button type="button" data-br-flow="${E(action)}" ${extra} class="${E(cls)}">${E(label)}</button>`;}
async function brPricingSettings(){
 const context=brContext(),data=await brPricingCatalog();if(context!==brContext())return '';brState.pricing=data;
 const profile=data.profile||{},vehicles=data.vehicles||[],gifts=data.gifts||[],vehicleNotes=vehicles.some(v=>v.note);
 return heading('品牌车型与价格目录','同品牌门店共用车系车型、精品赠品和限价。发布后本品牌全部门店生效；已提交合同继续使用冻结版本。',brLink('records-sales','返回销售业务'))+
 `<section class="panel"><div class="panelhead spread"><h2>门店与合同卖方资料</h2><div class="row">${data.can_manage_profile?brFlowButton('store-profile','维护门店资料')+brFlowButton('vehicle-variant','补充品牌车系车型',data.brand?'':'disabled'):''}</div></div><div class="panelbody">${brFacts([['共享品牌',data.brand||'未设置'],['目录版本',data.brand?'版本 '+data.brand_version:'待设置品牌'],['发布范围',data.brand?data.brand+' · 全部同品牌门店':'待设置品牌'],['本店地址',profile.address],['本店卖方公司',(profile.sellers||[]).map(s=>s.name).join('、')]])}<p class="br-caption">经营品牌由系统管理员在门店设置中维护；地址、卖方公司及销售联系方式仅用于本店合同。</p></div></section>`+
 `<section class="panel"><div class="panelhead spread"><div><h2>纯车价限价 · ${vehicles.length} 款</h2><p class="br-caption">${vehicles.length?'请同时核对原表适用条件。车价低于销售管控价须经集团副总经理特殊审批。':data.brand?'本品牌尚未发布车型限价。任一同品牌门店的销售经理或总经理核对发布后，全部同品牌门店共享。':'请先在门店设置中指定经营品牌。'}</p></div>${data.can_import_vehicle?brFlowButton('price-upload','上传限价 Excel','data-kind="vehicle"','primary'):''}</div>${table(['车系','年款 / 系列','车型配置','指导价','销售管控价',...(vehicleNotes?['条件与来源']:[])],vehicles.map(v=>[E(v.family),E(v.series),E(v.model),brAmount(v.guide_price_cents),brAmount(v.control_price_cents),...(vehicleNotes?[v.note?`<details><summary>查看原表说明</summary><p class="br-source-note">${E(v.note)}</p></details>`:'—']:[])]))}</section>`+
 `<section class="panel"><div class="panelhead spread"><div><h2>赠品目录 · ${gifts.length} 项</h2><p class="br-caption">成本与售价分别记录，空白表示待补齐；无系统赠品限额，销售经理判断超价并填写特殊申请。</p></div>${data.can_import_gifts?brFlowButton('price-upload','上传赠品成本 / 售价表','data-kind="gift"','primary'):''}</div>${table(['赠品','品牌','单位','适用车型',...(data.can_view_gift_amounts?['售价']:[]),...(data.can_view_gift_costs?['成本','说明']:[])],gifts.map(g=>[E(g.name),E(g.brand||profile.brand),E(g.unit||'—'),E(g.applicable_models||'—'),...(data.can_view_gift_amounts?[g.unit_price_cents==null?'待补齐':brAmount(g.unit_price_cents)]:[]),...(data.can_view_gift_costs?[g.unit_cost_cents==null?'待补齐':brAmount(g.unit_cost_cents),E(g.note||'—')]:[])]))}</section>`;
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
 if(!rows.length||rows.length>2000)throw new Error('核对表需要 1 至 2000 行车型。');
 const seen=new Set();rows.forEach((row,i)=>{const key=JSON.stringify([row.family,row.series,row.model]);if(seen.has(key))throw new Error('第 '+(i+1)+' 行车型重复，请核对车系、年款 / 系列和车型配置。');seen.add(key);});return rows;
}
function brParseVehicleReviewTable(source){
 // Excel clipboard TSV can quote cells containing tabs, newlines or quotes.
 // Keep multiline source policies in the sixth cell instead of splitting rows.
 const text=String(source).replace(/^\uFEFF/,'').replace(/\r\n?/g,'\n'),table=[];let row=[],cell='',quoted=false,closed=false;
 const field=()=>{row.push(cell);cell='';closed=false;};
 const line=()=>{field();if(row.some(value=>value.trim()))table.push(row);row=[];};
 for(let i=0;i<text.length;i++){
  const ch=text[i];
  if(quoted){if(ch==='"'){if(text[i+1]==='"'){cell+='"';i++;}else{quoted=false;closed=true;}}else cell+=ch;continue;}
  if(ch==='\t'){field();continue;}if(ch==='\n'){line();continue;}
  if(closed)throw new Error('核对表的引号格式不完整，请直接从 Excel 复制六列。');
  if(ch==='"'&&!cell){quoted=true;continue;}cell+=ch;
 }
 if(quoted)throw new Error('核对表有未结束的引号，请重新复制完整内容。');
 if(cell||row.length||closed)line();
 if(table[0]?.length===6&&table[0][0].trim()==='车系'&&table[0][3].includes('指导价')&&table[0][4].includes('销售管控价'))table.shift();
 return brUniqueVehicleReviewRows(table.map((cells,i)=>{
  if(cells.length!==6)throw new Error('第 '+(i+1)+' 行需要六列：车系、年款 / 系列、车型、指导价、销售管控价、说明；请用制表符分隔，空说明保留第六列。');
  return brVehicleReviewRow(Object.fromEntries(['family','series','model','guide_price_cents','control_price_cents','note'].map((key,j)=>[key,cells[j]])),i);
 }));
}
async function brPricingUpload(kind){
 const context=brContext(),catalog=await brPricingCatalog();let requestId=requestKey();if(context!==brContext())return;
 if(!(kind==='vehicle'?catalog.can_import_vehicle:catalog.can_import_gifts))throw new Error('当前岗位不能上传此价格目录。');
 const scope=brBrandPublication(catalog);let upload=null,rows=null,publicationId=requestKey(),reviewFileVersion=0;
 const reviewTable=kind==='vehicle'?`<details><summary>人工核对表：批量填写</summary><p class="notice">先上传原始 Excel 留档，再从核对表复制六列：车系、年款 / 系列、车型、指导价（元）、销售管控价（元）、说明。列之间用制表符分隔，可包含表头；多行说明可直接从 Excel 复制。载入后仍须核对并点击发布。</p><label>选择已核对的制表符表格文件<input type="file" data-price-review-file accept=".tsv,text/tab-separated-values" disabled></label><p class="br-caption">此文件只在当前页面读取，不会上传；原始 Excel 仍作为发布依据留档。</p><label>或粘贴核对表<textarea data-price-review rows="8" placeholder="车系&#9;年款 / 系列&#9;车型&#9;指导价（元）&#9;销售管控价（元）&#9;说明"></textarea></label><button type="button" data-price-review-load disabled>载入核对表</button></details>`:'';
 const dialog=modal(kind==='vehicle'?'上传品牌纯车价限价表':'上传品牌赠品成本 / 售价表',`<form><p class="notice">当前品牌：${E(scope.brand)} · 目录版本 ${scope.brand_version}。${kind==='vehicle'?'可仅上传原表后人工填写核对表，也可使用 DeepSeek Flash 按 max 思考识别销售管控价。空白价格和特殊条件请逐项核实并补齐。':'本地解析明确的成本、售价两列，无需模型。成本和售价不相互替代，未知留空。复杂合并表或xls请先整理为分品牌标准CSV。'}确认后整批替换本品牌有效目录，影响全部同品牌门店。已提交合同保留冻结价格。如果其他门店已发布新版本，请刷新并重新核对。</p><label>选择 Excel / CSV 文件<input type="file" name="file" accept="${kind==='vehicle'?'.xlsx':'.xlsx,.csv'}" required></label>${kind==='vehicle'?'<button type="button" data-price-upload-only>仅上传原表</button>':''}<button type="button" data-price-recognize>${kind==='vehicle'?'上传并识别':'上传并预览'}</button><p data-price-status role="status"></p>${reviewTable}<div data-price-warnings></div><div class="br-price-edit-table" data-price-rows></div><div class="formerror" role="alert"></div><div class="modalfoot"><button type="submit" class="primary" disabled>已逐项核对，发布到全部同品牌门店</button></div></form>`,async form=>{
  if(context!==brContext())throw new Error('账号或门店已切换，请重新上传。');
  if(!upload||!rows)throw new Error('请先上传原表并载入核对表，或完成识别。');
  const text=(i,key)=>form.querySelector(`[data-price-index="${i}"][data-price-key="${key}"]`).value.trim();
  const optionalAmount=(i,key)=>text(i,key)===''?null:moneyFen(text(i,key),{label:'第 '+(i+1)+' 行金额',allowZero:true});
  const confirmed=rows.map((_,i)=>kind==='vehicle'?brVehicleReviewRow(Object.fromEntries(['family','series','model','guide_price_cents','control_price_cents','note'].map(key=>[key,text(i,key)])),i):{name:text(i,'name'),brand:text(i,'brand'),unit:text(i,'unit'),applicable_models:text(i,'applicable_models'),unit_price_cents:optionalAmount(i,'unit_price_cents'),...(catalog.can_view_gift_costs?{unit_cost_cents:optionalAmount(i,'unit_cost_cents'),source_ref:text(i,'source_ref'),note:text(i,'note')}:{} )});
  if(kind==='vehicle')brUniqueVehicleReviewRows(confirmed);
  await api(BR_API+'/pricing/'+(kind==='vehicle'?'vehicle':'gifts')+'/import',{method:'POST',body:{request_id:publicationId,version:catalog.version,...scope,file_id:upload.id,rows:confirmed}});
  if(context!==brContext())return;closeModal();await render();toast(scope.brand+'全部同品牌门店目录已更新，已提交合同的价格版本保持不变');
 });
 const form=$('form',dialog),recognize=$('[data-price-recognize]',form),uploadOnly=$('[data-price-upload-only]',form),reviewLoad=$('[data-price-review-load]',form),reviewFile=$('[data-price-review-file]',form),submit=$('[type=submit]',form),status=$('[data-price-status]',form),error=$('.formerror',form);
 const keys=kind==='vehicle'?[['family','车系'],['series','年款 / 系列'],['model','车型配置'],['guide_price_cents','指导价（元）'],['control_price_cents','销售管控价（元）'],['note','条件 / 核对说明']]:[['name','赠品名称'],['brand','品牌'],['unit','单位'],['applicable_models','适用车型'],['unit_price_cents','售价（元，未知留空）'],...(catalog.can_view_gift_costs?[['unit_cost_cents','成本（元，未知留空）'],['source_ref','来源位置'],['note','说明']]:[])];
 const input=(row,i,key,label)=>{
  const attrs=`data-price-index="${i}" data-price-key="${key}" aria-label="第 ${i+1} 行${E(label)}"`;
  if(key==='note')return `<textarea ${attrs} rows="3" maxlength="2000">${E(row[key]??'')}</textarea>`;
  return `<input ${attrs} value="${E(key.endsWith('_cents')?brInputAmount(row[key]):row[key]??(key==='brand'?catalog.profile?.brand||'':''))}" ${(kind==='vehicle'?key!=='note':['name','brand'].includes(key))?'required':''} ${key.endsWith('_cents')?'inputmode="decimal"':''}>`;
 };
 const draw=()=>{$('[data-price-rows]',form).innerHTML=table(['行',...keys.map(k=>k[1])],rows.map((row,i)=>[String(i+1)+(row.source?'<small class="br-caption">'+E(row.source)+'</small>':''),...keys.map(([key,label])=>input(row,i,key,label))]));submit.disabled=!rows.length;};
 const manual=document.createElement('button');manual.type='button';manual.textContent='人工补录一行';manual.hidden=true;recognize.after(manual);manual.onclick=()=>{try{if(!upload)return;const previous=rows||[];rows=previous.map((row,i)=>Object.fromEntries(keys.map(([key])=>{const v=form.querySelector(`[data-price-index="${i}"][data-price-key="${key}"]`).value.trim();return [key,key.endsWith('_cents')?(v===''?null:moneyFen(v,{allowZero:true,label:'第 '+(i+1)+' 行金额'})):v];})));rows.push({});draw();}catch(e){error.textContent=e.message;}};
 const busy=value=>{recognize.disabled=value;manual.disabled=value;if(uploadOnly)uploadOnly.disabled=value;if(reviewLoad)reviewLoad.disabled=value||!upload||upload.available!==true;if(reviewFile)reviewFile.disabled=value||!upload||upload.available!==true;};
 const uploadOriginal=async()=>{
  if(context!==brContext())throw new Error('门店已切换。');const file=form.elements.file.files[0];if(!file)throw new Error('请选择价格表文件。');
  if(!upload){const activeRequest=requestId,body=new FormData();body.set('file',file);body.set('kind',kind);body.set('request_id',activeRequest);status.textContent='正在上传原表…';const saved=await api(BR_API+'/pricing/uploads',{method:'POST',body});if(context!==brContext()||!form.isConnected)return false;if(activeRequest!==requestId||file!==form.elements.file.files[0])throw new Error('原表已更换，请重新上传当前文件。');upload=saved;}
  if(context!==brContext()||!form.isConnected)return false;
  if(upload.available!==true)throw new Error('原表尚不可用于发布，请联系管理员检查文件状态。');manual.hidden=false;return true;
 };
 form.elements.file.onchange=()=>{upload=null;rows=null;requestId=requestKey();publicationId=requestKey();manual.hidden=true;submit.disabled=true;if(reviewLoad)reviewLoad.disabled=true;if(reviewFile){reviewFile.disabled=true;reviewFile.value='';reviewFileVersion++;}$('[data-price-rows]',form).replaceChildren();$('[data-price-warnings]',form).replaceChildren();status.textContent='';};
 if(uploadOnly)uploadOnly.onclick=async()=>{busy(true);error.textContent='';try{if(await uploadOriginal())status.textContent='原表已留档，尚未发布。请载入人工核对表，或逐行填写后核对。';}catch(e){error.textContent=e.message;status.textContent='尚未生效，原有效目录不变。';}finally{if(form.isConnected)busy(false);}};
 const loadReview=content=>{if(context!==brContext())throw new Error('账号或门店已切换，请重新上传。');if(!upload||upload.available!==true)throw new Error('请先上传原表。');const parsed=brParseVehicleReviewTable(content);rows=parsed;publicationId=requestKey();draw();$('[data-price-warnings]',form).replaceChildren();status.textContent=`已载入 ${rows.length} 项人工核对内容，尚未发布。请核实车型、金额及适用条件，再点击发布。`;};
 if(reviewLoad)reviewLoad.onclick=()=>{error.textContent='';try{loadReview($('[data-price-review]',form).value);}catch(e){error.textContent=e.message;}};
 if(reviewFile)reviewFile.onchange=async()=>{const file=reviewFile.files[0],version=++reviewFileVersion,originalId=upload?.id;if(!file)return;error.textContent='';try{const content=await file.text();if(!form.isConnected||context!==brContext()||version!==reviewFileVersion||file!==reviewFile.files[0]||originalId!==upload?.id)return;loadReview(content);$('[data-price-review]',form).value=content;}catch(e){error.textContent=e.message;}};
 recognize.onclick=async()=>{busy(true);submit.disabled=true;error.textContent='';try{
  if(!await uploadOriginal())return;
  status.textContent=kind==='vehicle'?'正在识别销售管控价，完成后请逐项核对…':'正在识别赠品目录…';
  const activeUpload=upload.id,result=await api(BR_API+'/pricing/uploads/'+activeUpload+'/recognize',{method:'POST',body:{request_id:requestKey(),version:upload.version}});
  if(context!==brContext()||!form.isConnected)return;if(upload?.id!==activeUpload)throw new Error('原表已更换，请重新核对当前文件。');if(!Array.isArray(result.rows)||!result.rows.length)throw new Error('没有完整的可核对项目，请检查原表后重新上传。');rows=result.rows;
  draw();
  $('[data-price-warnings]',form).innerHTML=(result.warnings||[]).map(w=>`<p class="notice warn">${E(typeof w==='string'?w:JSON.stringify(w))}</p>`).join('');status.textContent=`已解析 ${rows.length} 项。${kind==='gift'?'逐项核对品牌与金额，每项至少有成本或售价。':'所有空缺必填项补齐后才能生效。'}`;submit.disabled=false;publicationId=requestKey();
 }catch(e){error.textContent=e.message;status.textContent='尚未生效，原有效目录不变。';}finally{if(form.isConnected)busy(false);}};
}
async function brStoreProfileEdit(){
 const context=brContext(),data=await api(BR_API+'/store-profile');if(context!==brContext())return;
 const p=data.profile||data,people=state.recordCatalog.sales_people||[],fields=[F('address','本店地址'),F('sellers','卖方公司列表（一行一个：公司名称 | 地址）','textarea'),...people.map(s=>F('contact_'+s.id,s.label+' · 联系电话','text',false))];
 return brForm('维护门店与卖方资料',[{title:'合同默认资料',fields}],{address:p.address,sellers:(p.sellers||[]).map(s=>s.name+' | '+(s.address||'')).join('\n'),...Object.fromEntries(people.map(s=>['contact_'+s.id,p.sales_contacts?.[String(s.id)]||'']))},(v,request_id)=>{
  const sellers=v.sellers.split('\n').filter(x=>x.trim()).map(line=>{const [name,...rest]=line.split('|');return {name:name.trim(),address:rest.join('|').trim()};});
  return api(BR_API+'/store-profile',{method:'PUT',body:{request_id,version:data.version,brand:p.brand,address:v.address,sellers,sales_contacts:Object.fromEntries(people.map(s=>[String(s.id),v['contact_'+s.id]]))}});
 },{draftKey:'store-profile-'+p.brand+'-'+data.version,notice:'经营品牌：'+(p.brand||'未设置')+'（来自门店设置，由系统管理员维护）。以下卖方名称、地址和销售顾问联系电话仅用于本店合同，不修改其他同品牌门店。'});
}
async function brVehicleVariant(){const context=brContext(),data=await brPricingCatalog();if(context!==brContext())return;const scope=brBrandPublication(data);return brForm('补充品牌车型',[{title:'车系车型目录',fields:[F('family','车系'),F('series','年款 / 系列'),F('model','车型配置')]}],{},(v,request_id)=>api(BR_API+'/vehicle-variants',{method:'POST',body:{...v,request_id,version:data.version,...scope}}),{draftKey:'vehicle-variant-'+scope.brand+'-'+scope.brand_version,notice:'当前品牌：'+scope.brand+' · 目录版本 '+scope.brand_version+'。新增车系车型对全部同品牌门店生效。车型目录与价格分开维护，完成限价表确认发布后，该配置才能用于新合同；已提交合同保持原版本。'});}
document.addEventListener('click',async event=>{const el=event.target.closest('[data-br-flow]');if(!el||el.disabled||state.storeSwitch)return;const a=el.dataset.brFlow;if(!['price-upload','store-profile','vehicle-variant'].includes(a))return;el.disabled=true;try{if(a==='price-upload')await brPricingUpload(el.dataset.kind);if(a==='store-profile')await brStoreProfileEdit();if(a==='vehicle-variant')await brVehicleVariant();}catch(error){toast(error.message,true);}finally{if(el.isConnected)el.disabled=false;}});
