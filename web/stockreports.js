'use strict';
async function stockPeriodPage(){
 const query=new URLSearchParams(state.dates),d=await api('/api/stock-reports/period?'+query);
 const quantity=v=>v===null?'—':number(v/1000),stages=[['opening','期初'],['in','期间入库'],['out','期间出库'],['closing','期末']];
 const cards=d.rows.map(r=>panel(E(r.name),`<p>${E(r.sku)} · ${E(r.unit)}</p><div class="stock-period-grid">${stages.map(([key,label])=>`<div><span class="muted">${label}</span><strong>${quantity(r[key].quantity_milli)} ${E(r.unit)}</strong>${d.can_money?`<span>${r[key].value_cents===null?'—':money(r[key].value_cents)} 元</span>`:''}</div>`).join('')}</div><p class="${r.reconciled?'muted':'notice error'}">${E(r.status)}</p>${b('open','核对原始流水','data-route="opening-stock"')}`)).join('');
 const details=d.details.slice((state.page-1)*25,state.page*25);
 return heading('物资期间入出存','按已保存的期初和原始库存流水重建。',b('stock-period-export','导出本表'))+storeNotice()+dateFilters()+`<div class="notice ${d.complete?'':'error'}">${E(d.definition)}</div>`+
 (d.chart?panel(d.chart.title,chartSVG(d.chart)):'')+
 `<div class="work-table">${panel('逐物资核对',table([...d.table.headers,'原始流水'],d.table.rows.map(r=>[...r.values.map(E),b('open','查看',`data-route="opening-stock"`)])))}</div><div class="work-cards">${cards||empty('当前门店暂无物资')}</div>`+
 panel('期间原始记录',table(['日期','物资','来源','数量','单位',...(d.can_money?['价值（元）']:[]),'原单'],details.map(r=>[E(r.date),E(r.name),E(r.reference),E(r.quantity_milli/1000),E(r.unit),...(d.can_money?[money(r.value_cents)]:[]),r.case_id?b('open','查看',`data-route="case/${r.case_id}"`):'期初资料']))+pager(d.details.length));
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-act="stock-period-export"]');if(!button)return;
 button.disabled=true;try{await download('/api/stock-reports/period/export?'+new URLSearchParams(state.dates),'huakangos_物资入出存.csv');}catch(error){toast(error.message,true);}finally{button.disabled=false;}
});
