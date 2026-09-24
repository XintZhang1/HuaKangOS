'use strict';
let inventoryReportContext={};
function clearInventoryReportsSession(){inventoryReportContext={};}
function warehouseReportContext(){const key=String(state.user?.id)+':'+state.store;if(inventoryReportContext.key!==key)inventoryReportContext={key,filters:{}};return inventoryReportContext;}

function irTable(kind,key,t){
 const action=b('inventory-report-export','导出本表',`data-kind="${kind}" data-key="${key}"`);
 const selected=t.rows.slice((state.page-1)*25,state.page*25);
 const rowLink=r=>r.route?.type==='case'?b('open','查看原单',`data-route="case/${r.route.id}"`):'—';
 const html=table([...t.headers,'原单'],selected.map(r=>[...r.values.map(E),rowLink(r)]));
 return panel(t.title,action+`<div class="work-table">${html}</div><div class="work-cards">`+selected.map(r=>`<article class="card">${t.headers.map((h,i)=>`<p><span class="muted">${E(h)}：</span>${E(r.values[i])}</p>`).join('')}${rowLink(r)}</article>`).join('')+'</div>'+(t.rows.length?pager(t.rows.length,state.page,25):empty('本表暂无记录')));
}

function irPeriodError(title,error){return heading(title,'修改查询期间后可以重新生成报表。')+storeNotice()+dateFilters()+`<div class="notice error" role="alert">${E(error.message)}</div>`;}

async function vehiclePeriodPage(){
 let d;try{d=await api('/api/inventory-reports/vehicles?'+new URLSearchParams(state.dates));}catch(error){if(error.status===422)return irPeriodError('整车期间入出存',error);throw error;}
 return heading('整车期间入出存','每台车按原库存编号与代次核对实际出入库。')+storeNotice()+dateFilters()+
 `<div class="notice ${d.complete?'':'error'}">库内库存来源：${d.complete?'本次所列代次均可核对':'存在不完整来源；不展示完整期末合计'}。<br>在途来源：${d.transit_complete?'本次授权范围内可核对':'存在对店历史确认不可读的调拨，不能确认其历史在途数量'}。</div>`+
 `<p class="muted">${E(d.definition)}</p><p class="muted">查询时间：${time(d.as_of)}</p>`+
 d.charts.map(c=>panel(c.title,chartSVG(c)+b('inventory-report-export','导出此图原始行',`data-kind="vehicles" data-key="${c.table}"`))).join('')+
 Object.entries(d.tables).map(([key,t])=>irTable('vehicles',key,t)).join('');
}

async function procurementCohortPage(){
 let d;try{d=await api('/api/inventory-reports/procurement?'+new URLSearchParams(state.dates));}catch(error){if(error.status===422)return irPeriodError('物资采购订货统计',error);throw error;}
 return heading('物资采购订货统计','日期选择原订货批次，累计到退货查询到现在。')+storeNotice()+dateFilters()+
 `<div class="notice ${d.complete?'':'error'}">${d.complete?'原订货与到退货来源可核对':'存在来源差异或历史简表；不展示完整履约合计'}。此处不是期间到货统计。</div>`+
 `<p class="muted">${E(d.definition)}</p><p class="muted">累计履约截至本次查询：${time(d.as_of)}</p>`+
 d.charts.map(c=>panel(c.title,chartSVG(c)+b('inventory-report-export','导出此图原始行',`data-kind="procurement" data-key="${c.table}"`))).join('')+
 Object.entries(d.tables).filter(([,t])=>!t.chart_only).map(([key,t])=>irTable('procurement',key,t)).join('');
}

async function warehousePeriodPage(){
 const ctx=warehouseReportContext(),options=await Promise.all(['items','warehouses'].map((kind,i)=>api('/api/inventory-reports/warehouses/options/'+kind+(ctx.filters[i?'warehouse_id':'item_id']?'?selected_id='+ctx.filters[i?'warehouse_id':'item_id']:''))));
 const filterHTML=`<form id="warehouse-report-filters" class="filterbar">${[['items','item_id','物资'],['warehouses','warehouse_id','仓库']].map(([kind,key,label],i)=>`<label>${label}<select name="${key}" data-search-select data-warehouse-report-kind="${kind}" data-search-all="全部${label}" data-search-placeholder="全部${label}（输入名称或编码）"><option value="">全部${label}</option>${options[i].items.map(o=>`<option value="${o.id}" ${String(o.id)===String(ctx.filters[key])?'selected':''}>${E(o.label)}</option>`).join('')}</select></label>`).join('')}${b('warehouse-report-clear','清除筛选')}</form>`;
 let d;try{d=await api('/api/inventory-reports/warehouses?'+new URLSearchParams({...state.dates,...ctx.filters}));}catch(error){if([422,409].includes(error.status))return irPeriodError('库位期间入出存',error)+filterHTML;throw error;}
 return heading('库位期间入出存','基于真实启用桥接、库位收发和店内在途的原始账。')+storeNotice()+dateFilters()+filterHTML+
 `<div class="notice ${d.complete?'':'error'}">全期间来源：${d.complete?'完整':'有未知期初或覆盖缺口'}。<br>期末来源：${d.closing_complete?'已知并可核对；这不代表全期间完整':'来源不足，不能生成完整期末图'}。</div>`+
 `<p class="muted">${E(d.definition)}</p><p class="muted">${E(d.filters.note)}</p>`+
 d.charts.map(c=>panel(c.title,chartSVG(c)+b('inventory-report-export','导出此图原始行',`data-kind="warehouses" data-key="${c.table}"`))).join('')+
 Object.entries(d.tables).map(([key,t])=>irTable('warehouses',key,t)).join('');
}

document.addEventListener('submit',event=>{if(event.target.id!=='warehouse-report-filters')return;event.preventDefault();warehouseReportContext().filters=Object.fromEntries([...new FormData(event.target)].filter(([,v])=>v!==''));state.page=1;render();});

// History filters deliberately retain their own scoped endpoint, including inactive records.
function warehouseHistoryLookup(kind,query){if(!['items','warehouses'].includes(kind))throw new Error('筛选类型无效');return api('/api/inventory-reports/warehouses/options/'+kind+'?'+new URLSearchParams({q:query}));}
function enhanceWarehouseReportChoices(){
 if(typeof registerLiveChoiceLoader!=='function')return;
 document.querySelectorAll('#warehouse-report-filters select[data-warehouse-report-kind]:not([data-warehouse-choice-ready])').forEach(select=>{
  const kind=select.dataset.warehouseReportKind;registerLiveChoiceLoader(select,query=>warehouseHistoryLookup(kind,query));select.dataset.warehouseChoiceReady='1';
 });
}
new MutationObserver(enhanceWarehouseReportChoices).observe(document.documentElement,{childList:true,subtree:true});
document.addEventListener('DOMContentLoaded',enhanceWarehouseReportChoices);
document.addEventListener('change',event=>{
 const select=event.target;if(!select.matches?.('#warehouse-report-filters select[data-warehouse-report-kind]')||event.liveChoiceReason==='edit')return;
 const filters=warehouseReportContext().filters;if(select.value)filters[select.name]=select.value;else delete filters[select.name];state.page=1;render();
});

document.addEventListener('click',async event=>{
 const clear=event.target.closest('[data-act="warehouse-report-clear"]');if(clear){warehouseReportContext().filters={};state.page=1;render();return;}
 const button=event.target.closest('[data-act="inventory-report-export"]');if(!button)return;
 button.disabled=true;
 try{await download(`/api/inventory-reports/${button.dataset.kind}/export/${button.dataset.key}?`+new URLSearchParams({...state.dates,...(button.dataset.kind==='warehouses'?warehouseReportContext().filters:{})}),'huakangos_库存采购统计.csv');}
 catch(error){toast(error.message,true);}finally{button.disabled=false;}
});
