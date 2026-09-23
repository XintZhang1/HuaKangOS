'use strict';
async function customerValuePage(key){
 const data=await analyticData(),summary=data.tables.customer_value.rows.find(r=>r.customer_key===key);
 if(!summary)throw new Error('当前授权门店和期间没有该客户业务。');
 const source=data.tables.customer_value_details,rows=source.rows.filter(r=>r.customer_key===key),start=(state.page-1)*50;
 return heading('客户业务 · '+summary.values[1],'按已确认身份归集；姓名和电话相同不会自动合并。',b('customer-value-export','导出本客户明细',`data-key="${E(key)}"`,'primary')+b('open','返回客户分析','data-route="analytics/customers"'))+dateFilters()+
 panel('本期已记录业务',`<div class="stock-period-grid"><div>业务金额<strong>${money(summary.amount_cents)} 元</strong></div><div>涉及原单<strong>${summary.values[3]} 单</strong></div></div><p>这里展示交付、对外结算及已办理服务的核价事实。充值、预收和代收保费另查现金账；本表不预测未来价值。</p>`)+
 panel('可追溯的原业务','<div class="stack">'+rows.slice(start,start+50).map(r=>`<article class="customer-fact"><div class="spread"><strong>${E(r.values[5])}</strong><strong>${money(r.amount_cents)} 元</strong></div><p class="muted">${E(r.values[2])} · ${E(r.values[4])}</p><p>${E(r.values[3])}</p>${b('open','查看原单',`data-route="case/${r.route.id}"`)}</article>`).join('')+'</div>'+pager(rows.length,state.page,50));
}
document.addEventListener('click',async event=>{
 const el=event.target.closest('[data-act="customer-value-export"]');if(!el)return;
 try{await download('/api/flow/analytics/export?'+new URLSearchParams({dataset:'customer_value_details',customer_key:el.dataset.key,...state.dates}),'huakangos-客户业务明细.csv');}catch(error){toast(error.message,true);}
});
