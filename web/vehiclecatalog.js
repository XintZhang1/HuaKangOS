'use strict';
let vehicleCatalogUI={};
function clearVehicleCatalogSession(){vehicleCatalogUI={};}
function vehicleCatalogContext(){const key=String(state.user?.id)+':'+state.store;if(vehicleCatalogUI.key!==key)vehicleCatalogUI={key,filters:{},page:1,unclassifiedPage:1};return vehicleCatalogUI;}
function vcOption(id,label,current){return '<option value="'+E(id)+'" '+(String(id)===String(current)?'selected':'')+'>'+E(label)+'</option>';}
async function vehicleCatalogPage(){
 const c=vehicleCatalogContext();
 if(state.store==='all')return heading('车型展示与可选库存')+storeNotice()+'<div class="notice">请先选择具体门店查看车型及可选配车辆。</div>';
 const params=new URLSearchParams({page:c.page,unclassified_page:c.unclassifiedPage});for(const[k,v]of Object.entries(c.filters))if(v!==''&&v!==false)params.set(k,v);
 const d=await api('/api/vehicle-catalog?'+params);c.data=d;
 const filters='<form id="vehicle-catalog-filters" class="formgrid"><label>车型关键词<input name="q" maxlength="100" value="'+E(c.filters.q||'')+'"></label><label>品牌<select name="brand_id"><option value="">所有品牌</option>'+d.brands.map(r=>vcOption(r.id,r.name,c.filters.brand_id)).join('')+'</select></label><label>车系<select name="series_id"><option value="">所有车系</option>'+d.series.filter(r=>!c.filters.brand_id||String(r.brand_id)===String(c.filters.brand_id)).map(r=>vcOption(r.id,r.name,c.filters.series_id)).join('')+'</select></label><label>动力<select name="fuel_type"><option value="">所有动力</option>'+['petrol','diesel','electric','hybrid','plugin_hybrid'].map(v=>vcOption(v,masterOptions[v],c.filters.fuel_type)).join('')+'</select></label><label>最少座位<input name="min_seats" type="number" min="1" max="60" value="'+E(c.filters.min_seats||'')+'"></label><label>指导价上限（元）<input name="max_price" inputmode="decimal" value="'+E(c.maxPrice||'')+'"></label><label class="checklabel"><input name="available_only" type="checkbox" '+(c.filters.available_only?'checked':'')+'>仅看当前可选配</label><div><button type="submit" class="primary">筛选车型</button></div></form>';
 const cards=d.items.map(r=>panel(r.name,
  '<p>'+E(r.brand_name)+' · '+E(r.series_name)+' · '+r.model_year+'款</p>'+facts({'指导价':money(r.guide_price_cents),'动力':masterOptions[r.fuel_type],'座位':r.seats,'排量（毫升）':r.displacement_ml,'电池容量（千瓦时）':number(r.battery_wh/1000),'本店在库车辆':r.stock_count,'当前可选配':r.available_count})+
  (d.can_manage?b('catalog-classify-model','核对车系归属','data-id="'+r.id+'"'):'')+
  '<details class="mt15"><summary>查看本店车辆（'+r.stock_count+'）</summary>'+r.vehicles.map(v=>'<div class="notice mt15"><strong class="wrap">'+E(v.vin)+'</strong><p>'+E(v.color||'未填写颜色')+' · '+(v.available?'当前可选配':'已有占用或待办')+'</p><small>'+E(v.source)+'</small></div>').join('')+'</details>')).join('');
 const pages=Math.max(1,Math.ceil(d.total/12)),paging='<div class="row mt20">'+b('catalog-page','上一页','data-page="'+(c.page-1)+'" '+(c.page<=1?'disabled':''))+'<span>'+c.page+' / '+pages+' · '+d.total+'款</span>'+b('catalog-page','下一页','data-page="'+(c.page+1)+'" '+(c.page>=pages?'disabled':''))+'</div>';
 const unclassified=d.unclassified_total?panel('待确认车型的本店车辆',
  '<p>同名不等于同一车型。请按VIN与原资料明确归属，目录不会修改采购成本或历史业务。</p>'+d.unclassified.map(v=>'<div class="notice mt15"><strong class="wrap">'+E(v.vin)+'</strong><p>'+E(v.model_text)+'</p>'+(d.can_manage?b('catalog-classify-vehicle','按原资料确认车型','data-id="'+v.id+'"'):'待主管或库管核对')+'</div>').join('')+'<div class="row mt20">'+b('catalog-unclassified-page','上一页','data-page="'+(c.unclassifiedPage-1)+'" '+(c.unclassifiedPage<=1?'disabled':''))+'<span>'+c.unclassifiedPage+' / '+Math.ceil(d.unclassified_total/12)+' · 共'+d.unclassified_total+'辆</span>'+b('catalog-unclassified-page','下一页','data-page="'+(c.unclassifiedPage+1)+'" '+(c.unclassifiedPage*12>=d.unclassified_total?'disabled':''))+'</div>'):'';
 return heading('车型展示与可选库存','按品牌、车系及参数查车型，再核对本店当前车辆。',d.can_manage?b('open','维护品牌与车系','data-route="masters"'):'')+storeNotice()+panel('查找车型',filters)+'<div class="notice">'+E(d.notice)+'</div><div class="chartgrid mt20">'+cards+'</div>'+paging+unclassified;
}
async function catalogClassify(kind,id){
 const c=vehicleCatalogContext(),d=c.data,row=kind==='model'?d.items.find(r=>r.id===id):d.unclassified.find(r=>r.id===id);if(!row||!d.can_manage)throw new Error('请刷新并由本店主管或库管核对。');
 const choices=await api('/api/masters/lookup/'+(kind==='model'?'vehicle_series':'vehicle_models')+(kind==='model'&&row.series_id?'?selected_id='+row.series_id:'')),values=choices.items;
 const request_id=requestKey();
 modal(kind==='model'?'明确车型所属车系':'按VIN确认库存车型','<form><p>'+E(kind==='model'?row.name:row.vin+' · '+row.model_text)+'</p><label>'+ (kind==='model'?'选择车系':'选择已核对车型')+'<div class="typed-ref" data-kind="'+(kind==='model'?'vehicle_series':'vehicle_models')+'"><div class="lookuprow"><input type="search" data-typed-query placeholder="输入关键词查找" aria-label="查找归属资料">'+b('typed-lookup','查找')+'</div><select name="target" required><option value="">请选择</option>'+values.map(v=>vcOption(v.id,v.label,kind==='model'?row.series_id:'')).join('')+'</select>'+(choices.has_more?'<small>超过100项，请输入关键词查找。</small>':'')+'</div></label>'+ (kind==='vehicle'?'<label>再核对完整VIN<input name="vin" required minlength="17" maxlength="17"></label>':'')+'<label>核对依据<textarea name="reason" required minlength="2" maxlength="500"></textarea></label><div class="formerror" role="alert"></div><div class="modalfoot">'+b('close','取消')+'<button type="submit" class="primary">确认归属</button></div></form>',async form=>{
 const fd=new FormData(form),base={request_id,version:row.classification_version,reason:String(fd.get('reason'))};
 const payload=kind==='model'?{...base,model_id:row.id,model_version:row.version,series_id:Number(fd.get('target'))}:{...base,vehicle_id:row.id,vehicle_version:row.version,vin:String(fd.get('vin')),model_id:Number(fd.get('target'))};
 await api('/api/vehicle-catalog/'+kind+'-assignment',{method:'POST',body:payload});closeModal();await render();toast('已保存明确归属，原业务快照保持原内容');});
}
document.addEventListener('submit',async event=>{
 if(event.target.id!=='vehicle-catalog-filters')return;event.preventDefault();try{
 const c=vehicleCatalogContext(),fd=new FormData(event.target);c.maxPrice=String(fd.get('max_price')||'');
 c.filters={q:String(fd.get('q')||''),brand_id:fd.get('brand_id'),series_id:fd.get('series_id'),fuel_type:fd.get('fuel_type'),min_seats:fd.get('min_seats'),max_price_cents:c.maxPrice?masterFen(c.maxPrice):'',available_only:fd.get('available_only')!==null};c.page=1;await render();
 }catch(error){toast(error.message,true);}
});
document.addEventListener('change',event=>{
 if(event.target.form?.id!=='vehicle-catalog-filters'||event.target.name!=='brand_id')return;
 const d=vehicleCatalogContext().data,brand=event.target.value,select=event.target.form.elements.series_id;
 select.innerHTML='<option value="">所有车系</option>'+d.series.filter(r=>!brand||String(r.brand_id)===brand).map(r=>vcOption(r.id,r.name,'')).join('');
});
document.addEventListener('click',async event=>{
 const el=event.target.closest('[data-act]');if(!el||el.disabled||!['catalog-classify-model','catalog-classify-vehicle','catalog-page','catalog-unclassified-page'].includes(el.dataset.act))return;
 el.disabled=true;try{if(el.dataset.act==='catalog-page'){vehicleCatalogContext().page=Number(el.dataset.page);await render();}else if(el.dataset.act==='catalog-unclassified-page'){vehicleCatalogContext().unclassifiedPage=Number(el.dataset.page);await render();}else await catalogClassify(el.dataset.act==='catalog-classify-model'?'model':'vehicle',Number(el.dataset.id));}catch(error){toast(error.message,true);}finally{if(el.isConnected)el.disabled=false;}
});
