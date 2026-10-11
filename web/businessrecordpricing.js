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
 const profile=data.profile||{},vehicles=data.vehicles||[],gifts=data.gifts||[];
 return heading('品牌车型与价格目录','同品牌门店共用车系车型、精品赠品和限价。发布后本品牌全部门店生效；已提交合同继续使用冻结版本。',brLink('records-sales','返回销售业务'))+
 `<section class="panel"><div class="panelhead spread"><h2>门店与合同卖方资料</h2><div class="row">${data.can_manage_profile?brFlowButton('store-profile','维护门店资料')+brFlowButton('vehicle-variant','补充品牌车系车型',data.brand?'':'disabled'):''}</div></div><div class="panelbody">${brFacts([['共享品牌',data.brand||'未设置'],['目录版本',data.brand?'版本 '+data.brand_version:'待设置品牌'],['发布范围',data.brand?data.brand+' · 全部同品牌门店':'待设置品牌'],['本店地址',profile.address],['本店卖方公司',(profile.sellers||[]).map(s=>s.name).join('、')]])}<p class="br-caption">经营品牌由系统管理员在门店设置中维护；地址、卖方公司及销售联系方式仅用于本店合同。</p></div></section>`+
 `<section class="panel"><div class="panelhead spread"><div><h2>纯车价限价 · ${vehicles.length} 款</h2><p class="br-caption">只认销售管控价。车价低于此价须经集团副总经理特殊审批。</p></div>${data.can_import_vehicle?brFlowButton('price-upload','上传限价 Excel','data-kind="vehicle"','primary'):''}</div>${table(['车系','年款 / 系列','车型配置','指导价','销售管控价'],vehicles.map(v=>[E(v.family),E(v.series),E(v.model),brAmount(v.guide_price_cents),brAmount(v.control_price_cents)]))}</section>`+
 `<section class="panel"><div class="panelhead spread"><div><h2>赠品目录 · ${gifts.length} 项</h2><p class="br-caption">成本与售价分别记录，空白表示待补齐；无系统赠品限额，销售经理判断超价并填写特殊申请。</p></div>${data.can_import_gifts?brFlowButton('price-upload','上传赠品成本 / 售价表','data-kind="gift"','primary'):''}</div>${table(['赠品','品牌','单位','适用车型',...(data.can_view_gift_amounts?['售价']:[]),...(data.can_view_gift_costs?['成本','说明']:[])],gifts.map(g=>[E(g.name),E(g.brand||profile.brand),E(g.unit||'—'),E(g.applicable_models||'—'),...(data.can_view_gift_amounts?[g.unit_price_cents==null?'待补齐':brAmount(g.unit_price_cents)]:[]),...(data.can_view_gift_costs?[g.unit_cost_cents==null?'待补齐':brAmount(g.unit_cost_cents),E(g.note||'—')]:[])]))}</section>`;
}
async function brPricingUpload(kind){
 const context=brContext(),catalog=await brPricingCatalog();let requestId=requestKey();if(context!==brContext())return;
 if(!(kind==='vehicle'?catalog.can_import_vehicle:catalog.can_import_gifts))throw new Error('当前岗位不能上传此价格目录。');
 const scope=brBrandPublication(catalog);let upload=null,rows=null,publicationId=requestKey();
 const dialog=modal(kind==='vehicle'?'上传品牌纯车价限价表':'上传品牌赠品成本 / 售价表',`<form><p class="notice">当前品牌：${E(scope.brand)} · 目录版本 ${scope.brand_version}。${kind==='vehicle'?'DeepSeek Flash 将按 max 思考识别销售管控价。空白价格和特殊条件会保留为空，请逐项核实并补齐。':'本地解析明确的成本、售价两列，无需模型。成本和售价不相互替代，未知留空。复杂合并表或xls请先整理为分品牌标准CSV。'}确认后整批替换本品牌有效目录，影响全部同品牌门店。已提交合同保留冻结价格。如果其他门店已发布新版本，请刷新并重新核对。</p><label>选择 Excel / CSV 文件<input type="file" name="file" accept="${kind==='vehicle'?'.xlsx':'.xlsx,.csv'}" required></label><button type="button" data-price-recognize>上传并预览</button><p data-price-status role="status"></p><div data-price-warnings></div><div class="br-price-edit-table" data-price-rows></div><div class="formerror" role="alert"></div><div class="modalfoot"><button type="submit" class="primary" disabled>已逐项核对，发布到全部同品牌门店</button></div></form>`,async form=>{
  if(context!==brContext())throw new Error('账号或门店已切换，请重新上传。');
  if(!upload||!rows)throw new Error('请先完成上传及识别。');
  const text=(i,key)=>form.querySelector(`[data-price-index="${i}"][data-price-key="${key}"]`).value.trim();
  const optionalAmount=(i,key)=>text(i,key)===''?null:moneyFen(text(i,key),{label:'第 '+(i+1)+' 行金额',allowZero:true});
  const confirmed=rows.map((_,i)=>kind==='vehicle'?{family:text(i,'family'),series:text(i,'series'),model:text(i,'model'),guide_price_cents:moneyFen(text(i,'guide_price_cents'),{label:'第 '+(i+1)+' 行指导价'}),control_price_cents:moneyFen(text(i,'control_price_cents'),{label:'第 '+(i+1)+' 行销售管控价'}),note:text(i,'note')}:{name:text(i,'name'),brand:text(i,'brand'),unit:text(i,'unit'),applicable_models:text(i,'applicable_models'),unit_price_cents:optionalAmount(i,'unit_price_cents'),...(catalog.can_view_gift_costs?{unit_cost_cents:optionalAmount(i,'unit_cost_cents'),source_ref:text(i,'source_ref'),note:text(i,'note')}:{} )});
  await api(BR_API+'/pricing/'+(kind==='vehicle'?'vehicle':'gifts')+'/import',{method:'POST',body:{request_id:publicationId,version:catalog.version,...scope,file_id:upload.id,rows:confirmed}});
  if(context!==brContext())return;closeModal();await render();toast(scope.brand+'全部同品牌门店目录已更新，已提交合同的价格版本保持不变');
 });
 const form=$('form',dialog),recognize=$('[data-price-recognize]',form),submit=$('[type=submit]',form),status=$('[data-price-status]',form),error=$('.formerror',form);
 const keys=kind==='vehicle'?[['family','车系'],['series','年款 / 系列'],['model','车型配置'],['guide_price_cents','指导价（元）'],['control_price_cents','销售管控价（元）'],['note','条件 / 核对说明']]:[['name','赠品名称'],['brand','品牌'],['unit','单位'],['applicable_models','适用车型'],['unit_price_cents','售价（元，未知留空）'],...(catalog.can_view_gift_costs?[['unit_cost_cents','成本（元，未知留空）'],['source_ref','来源位置'],['note','说明']]:[])];
 const draw=()=>{$('[data-price-rows]',form).innerHTML=table(['行',...keys.map(k=>k[1])],rows.map((row,i)=>[String(i+1)+(row.source?'<small class="br-caption">'+E(row.source)+'</small>':''),...keys.map(([key,label])=>`<input data-price-index="${i}" data-price-key="${key}" aria-label="第 ${i+1} 行${E(label)}" value="${E(key.endsWith('_cents')?brInputAmount(row[key]):row[key]??(key==='brand'?catalog.profile?.brand||'':''))}" ${(kind==='vehicle'?key!=='note':['name','brand'].includes(key))?'required':''} ${key.endsWith('_cents')?'inputmode="decimal"':''}>`)]));submit.disabled=!rows.length;};
 const manual=document.createElement('button');manual.type='button';manual.textContent='人工补录一行';manual.hidden=true;recognize.after(manual);manual.onclick=()=>{try{if(!upload)return;const previous=rows||[];rows=previous.map((row,i)=>Object.fromEntries(keys.map(([key])=>{const v=form.querySelector(`[data-price-index="${i}"][data-price-key="${key}"]`).value.trim();return [key,key.endsWith('_cents')?(v===''?null:moneyFen(v,{allowZero:true,label:'第 '+(i+1)+' 行金额'})):v];})));rows.push({});draw();}catch(e){error.textContent=e.message;}};
 form.elements.file.onchange=()=>{upload=null;rows=null;requestId=requestKey();manual.hidden=true;submit.disabled=true;$('[data-price-rows]',form).replaceChildren();status.textContent='';};
 recognize.onclick=async()=>{recognize.disabled=true;submit.disabled=true;error.textContent='';try{
  if(context!==brContext())throw new Error('门店已切换。');const file=form.elements.file.files[0];if(!file)throw new Error('请选择价格表文件。');
  if(!upload){const body=new FormData();body.set('file',file);body.set('kind',kind);body.set('request_id',requestId);status.textContent='正在上传原表…';upload=await api(BR_API+'/pricing/uploads',{method:'POST',body});}if(context!==brContext()||!form.isConnected)return;manual.hidden=false;
  status.textContent=kind==='vehicle'?'正在识别销售管控价，完成后请逐项核对…':'正在识别赠品目录…';
  const result=await api(BR_API+'/pricing/uploads/'+upload.id+'/recognize',{method:'POST',body:{request_id:requestKey(),version:upload.version}});
  if(context!==brContext()||!form.isConnected)return;if(!Array.isArray(result.rows)||!result.rows.length)throw new Error('没有完整的可核对项目，请检查原表后重新上传。');rows=result.rows;
  draw();
  $('[data-price-warnings]',form).innerHTML=(result.warnings||[]).map(w=>`<p class="notice warn">${E(typeof w==='string'?w:JSON.stringify(w))}</p>`).join('');status.textContent=`已解析 ${rows.length} 项。${kind==='gift'?'逐项核对品牌与金额，每项至少有成本或售价。':'所有空缺必填项补齐后才能生效。'}`;submit.disabled=false;publicationId=requestKey();
 }catch(e){error.textContent=e.message;status.textContent='尚未生效，原有效目录不变。';}finally{if(recognize.isConnected)recognize.disabled=false;}};
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
