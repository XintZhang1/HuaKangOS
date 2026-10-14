'use strict';
let brDashboardTimer=null,brDashboardDetail=null;
function brCanDashboard(){const allowed=brCaps().read_dashboard;return typeof allowed==='boolean'?allowed:['admin','chairman','group_deputy_manager','general_manager'].includes(state.user?.role);}
function brDashboardHome(){return brCanDashboard()?'records-dashboard':state.user?.role==='finance'?'records-finance':state.user?.role==='clerk'?'records-office':state.user?.role==='service'?'records-after-sales':'records-sales';}
function brDashboardPanelFilter(panel){const composition=brState.dashboardComposition||'all';return composition==='all'||(composition==='sales'?['orders','sales','vehicle_amount','cash_count','cash_amount'].includes(panel.panel_id):composition==='extended'?!['orders','sales','vehicle_amount','cash_count','cash_amount','profit'].includes(panel.panel_id):panel.panel_id==='profit');}
// Dashboard totals are already calculated and permission-filtered by the server.
function brDashboardNumber(value){const text=String(value),match=text.match(/^(-?)(\d+)(\.\d+)?$/);return match?match[1]+match[2].replace(/\B(?=(\d{3})+(?!\d))/g,',')+(match[3]||''):text;}
// Format only the projection. Rounded display values never feed accounting.
function brDashboardFixed(value,precision=2){
 if(value==null||value==='')return '待审核';
 const match=String(value).match(/^(-?)(\d+)(?:\.(\d+))?$/);if(!match)return '待审核';
 const fraction=(match[3]||'').padEnd(precision+1,'0'),scale=10n**BigInt(precision);
 let units=BigInt(match[2])*scale+BigInt(fraction.slice(0,precision)||'0');if(fraction[precision]>='5')units++;
 const raw=units.toString().padStart(precision+1,'0');return brDashboardNumber((match[1]&&units?'-':'')+(precision?raw.slice(0,-precision)+'.'+raw.slice(-precision):raw));
}
function brDashboardValue(item){return item.value==null?E(item.status_label||'待审核'):E(item.unit==='元'?brDashboardFixed(item.value):brDashboardNumber(item.value));}
function brDashboardDelta(delta){if(delta.value==null)return delta.status_label||'待审核';const text=String(delta.value),zero=/^-?0+(?:\.0+)?$/.test(text);return (zero?'0':(text.startsWith('-')?'':'+')+((delta.formatUnit||delta.unit)==='元'?brDashboardFixed(text):brDashboardNumber(text)))+(delta.unit?' '+delta.unit:'');}
function brDashboardPeriod(result,mode){const start=result.overview_date_from||result.date_from,end=result.overview_date_to||result.date_to;return start+(start===end?'':' 至 '+end)+' · '+(mode==='daily'?'月内累计':'期间累计');}
function brDashboardCard(item,today){
 const missing=item.value==null,rate=Object.hasOwn(item,'penetration_rate')?`<span class="br-metric-rate">渗透率 <b>${item.penetration_rate==null?E(item.penetration_status_label||'待审核'):E(brDashboardFixed(item.penetration_rate))+'%'}</b></span>`:'';
 const delta=item.daily_delta,daily=delta?`<span class="br-metric-delta" data-br-daily-delta>${delta.date===today?'今日':'当日'} <b>${E(brDashboardDelta({...delta,unit:'',formatUnit:delta.unit}))}</b>${delta.value!=null&&delta.unit?` <small>${E(delta.unit)}</small>`:''}</span>`:'';
 const average=Object.hasOwn(item,'average_profit')?`<div class="br-metric-average"><span>平均单车毛利</span><b>${item.average_profit==null?'待核定':E(brDashboardFixed(item.average_profit))}<small>${item.average_profit==null?'':'元 / 台'}</small></b><span>同口径净台数 ${item.profit_vehicle_count==null?'待核对':E(brDashboardNumber(item.profit_vehicle_count))}</span></div>`:'';
 const related=(item.related_metrics||[]).map(metric=>`<button type="button" class="br-related-metric" data-br-flow="dashboard-detail" data-panel="${E(metric.panel_id)}"><span>${E(metric.label)}</span><b>${brDashboardValue(metric)}<small>${metric.value==null?'':E(metric.unit||'')}</small></b>${metric.daily_delta?`<span class="br-related-delta">${metric.daily_delta.date===today?'今日':'当日'} ${E(brDashboardDelta(metric.daily_delta))}</span>`:''}<span class="br-related-link">明细 ↗</span></button>`).join('');
 return `<article class="br-metric-card${missing?' br-metric-pending':''}"><button type="button" class="br-metric-primary" data-br-flow="dashboard-detail" data-panel="${E(item.panel_id)}"><span class="br-metric-label">${E(item.label.replace(/^期间累计|^当日/,''))}<span aria-hidden="true">↗</span></span>${daily}<span class="br-metric-total-label">期间累计</span><strong>${brDashboardValue(item)}${missing?'':`<small>${E(item.unit||'')}</small>`}</strong>${rate}${average}</button>${related?`<div class="br-related-metrics">${related}</div>`:''}<span class="br-metric-note">${E(item.note||item.status_label||'')}</span></article>`;
}
const BR_CHART_PALETTE=['#386fa4','#4b9b8a','#d8ac57','#877aaf','#69a9be','#bd8075','#6e87a3','#9fa967'];
function brDashboardModelChart(panel){
 const rows=panel.summary_rows||[],items=rows.filter(row=>row.c04!=null).map((row,i)=>({label:row.label,value:Number(row.c04),exact:row.c04,rate:row.c06,color:BR_CHART_PALETTE[i%BR_CHART_PALETTE.length]})),unknown=rows.filter(row=>row.c04==null).length;
 if(!items.length)return '<p class="br-dashboard-empty">车型毛利待核定，审核后显示贡献结构。</p>';
 if(items.some(item=>item.value<0)||unknown)return brDashboardSignedBars(items,'车型毛利（元）')+`<p class="br-caption">${unknown?unknown+' 个车型尚待核定。':''}负毛利或未核定项以条形明细呈现。</p>`;
 const total=items.reduce((sum,item)=>sum+item.value,0);if(total<=0)return '<p class="br-dashboard-empty">当前范围毛利合计为零，暂无贡献占比。</p>';
 let offset=0;const ring=items.filter(item=>item.value>0).map(item=>{const share=item.value/total*100,svg=`<circle cx="112" cy="112" r="83" pathLength="100" fill="none" stroke="${item.color}" stroke-width="25" stroke-dasharray="${share} ${100-share}" stroke-dashoffset="${-offset}" transform="rotate(-90 112 112)"><title>${E(item.label)}：${E(brDashboardFixed(item.exact))} 元</title></circle>`;offset+=share;return svg;}).join('');
 return `<div class="br-contribution"><svg viewBox="0 0 224 224" role="img" aria-label="车型毛利贡献图">${ring}<text x="112" y="103" text-anchor="middle" class="br-ring-caption">车型毛利合计</text><text x="112" y="130" text-anchor="middle" class="br-ring-total">${E(brDashboardFixed(panel.grand_total?.c04??total))}</text><text x="112" y="150" text-anchor="middle" class="br-ring-caption">元</text></svg><div class="br-chart-legend">${items.map(item=>`<div><i style="--br-chart-color:${item.color}"></i><span>${E(item.label)}</span><b>${E(brDashboardFixed(item.exact))}<small>${item.rate==null?'':E(brDashboardFixed(item.rate))+'%'}</small></b></div>`).join('')}</div></div>`;
}
function brDashboardSignedBars(items,label){
 const max=Math.max(...items.map(item=>Math.abs(item.value)),1),negative=items.some(item=>item.value<0);
 return `<div class="br-composition-bars" aria-label="${E(label)}">${items.map(item=>`<div><span>${E(item.label)}</span><svg viewBox="0 0 240 16" preserveAspectRatio="none" role="img" aria-label="${E(item.label+' '+brDashboardFixed(item.exact))}"><line x1="${negative?120:0}" x2="${negative?120:0}" y1="0" y2="16" stroke="#b9c9d6"/><rect x="${item.value<0?120-Math.abs(item.value)/max*120:negative?120:0}" y="3" width="${Math.abs(item.value)/max*(negative?120:240)}" height="10" rx="3" fill="${item.value<0?'#bd655e':item.color||'#4b8cad'}"/></svg><b>${E(brDashboardFixed(item.exact))}</b></div>`).join('')}</div>`;
}
function brDashboardPerformanceChart(rows){
 if(!rows.length)return '<p class="br-dashboard-empty">当前范围暂无记录</p>';
 const max=Math.max(1,...rows.flatMap(row=>[Number(row.c03)||0,Number(row.c04)||0]));
 return `<div class="br-performance-chart">${rows.map(row=>`<div class="br-performance-row"><div><b>${E(row.label)}</b><span>实绩 ${row.c04==null?'待核对':E(brDashboardNumber(row.c04))} / 目标 ${row.c03==null?'未设置':E(brDashboardNumber(row.c03))} 台</span></div><svg viewBox="0 0 400 18" preserveAspectRatio="none" role="img" aria-label="${E(row.label)}目标与实绩"><rect x="0" y="3" width="${Math.max(0,Number(row.c03)||0)/max*400}" height="12" rx="4" fill="#e3ecf3"/><rect x="0" y="5" width="${Math.max(0,Number(row.c04)||0)/max*400}" height="8" rx="3" fill="#4b8cad"/></svg><div class="br-performance-values"><span>完成率 <b>${row.c05==null?'待核对':E(brDashboardFixed(row.c05))+'%'}</b></span><span>平均毛利 <b>${row.c06==null?'待核定':E(brDashboardFixed(row.c06))+' 元'}</b></span><span>总毛利 <b>${row.c07==null?'待核定':E(brDashboardFixed(row.c07))+' 元'}</b></span></div></div>`).join('')}</div>`;
}
function brDashboardAnalyses(result){
 if(!['all','profit'].includes(brState.dashboardComposition||'all'))return '';
 return `<div class="br-priority-analyses">${(result.analyses||[]).map(panel=>{
  const p=panel.comparison,personal=panel.panel_id==='individual_profit',composition=panel.panel_id==='profit_composition',keys=composition?['label','value']:personal?['label','c03','c04','c05','c06','c07']:['label','c03','c04','c05','c06'],columns=p.summary_columns.filter(c=>keys.includes(c.key));
  const renderRows=rows=>rows.length?table(columns.map(c=>c.label+(c.unit?'（'+c.unit+'）':'')),rows.map(row=>columns.map(c=>E(row[c.key]==null?(c.type==='text'?'—':'待审核'):['money','percent','decimal'].includes(c.type)?brDashboardFixed(row[c.key]):row[c.key])))):'<p class="br-dashboard-empty">当前范围暂无记录</p>';
  const body=personal?['retail','wholesale'].map(group=>`<div class="br-analysis-group"><h3>${group==='retail'?'展厅个人':'批发渠道'}</h3>${brDashboardPerformanceChart(p.summary_rows.filter(row=>row.performance_group===group))}</div>`).join(''):composition?brDashboardSignedBars(p.summary_rows.filter(row=>row.value!=null&&Number(row.value)!==0).map((row,i)=>({label:row.label,value:Number(row.value),exact:row.value,color:BR_CHART_PALETTE[i%BR_CHART_PALETTE.length]})),'核定公式正负贡献')+`<p class="br-caption">毛利合计 ${E(brDashboardFixed(p.grand_total?.value))} 元；金额为零的项目在完整统计表中查看。</p>`+(p.summary_rows.some(row=>row.value==null)?'<p class="notice">部分公式项目未核定，保留为空。</p>':''):brDashboardModelChart(p);
  return `<section class="panel br-priority-analysis"><div class="panelhead spread"><h2>${E(panel.panel_title)}</h2>${brFlowButton('dashboard-detail','查看明细与导出',`data-panel="${E(panel.panel_id)}"`)}</div><div class="panelbody"><p class="br-caption">${E(p.date_from)} 至 ${E(p.date_to)} · ${composition?'按批准快照中的公式正负项展示':personal?'总经理已审核毛利；批发不计个人业绩':'总经理已审核车型毛利'}</p>${body}<details class="br-disclosure"><summary>查看完整统计表</summary>${renderRows(p.summary_rows)}</details></div></section>`;
 }).join('')}</div>`;
}
function brDashboardCards(result){
 const overview=(result.overview||[]).filter(brDashboardPanelFilter),extended=(result.extension_overview||[]).filter(brDashboardPanelFilter),champion=result.champion,showChampion=champion&&['all','sales'].includes(brState.dashboardComposition||'all');
 return `${overview.length?`<section class="br-live-overview" aria-label="经营数字概览">${overview.map(item=>brDashboardCard(item,result.today)).join('')}</section>`:''}${brDashboardAnalyses(result)}${showChampion?`<button type="button" class="br-champion-card" data-br-flow="dashboard-detail" data-panel="${E(champion.panel_id)}" data-champion="true"><span class="br-champion-label">${E(champion.label||'销冠')}</span><strong>${champion.names?.length?champion.names.map(E).join('、'):E(champion.status_label||'待审核')}</strong><span class="br-champion-count">${champion.names?.length?E(brDashboardNumber(champion.count))+' 台实销'+(champion.names.length>1?' · 并列':''):''}</span><span class="br-champion-link">查看顾问表现 ↗</span></button>`:''}${extended.length?`<section class="br-extension-section" aria-label="延伸业务"><div class="br-dashboard-sectionhead"><h2>延伸业务</h2><p>点击查看比较、来源明细与趋势</p></div><div class="br-live-overview br-extension-overview">${extended.map(item=>brDashboardCard(item,result.today)).join('')}</div></section>`:''}`;
}
async function brRealtimeDashboard(mode='daily'){
 if(!brCanDashboard())return heading('业务工作台','',brLink(brDashboardHome(),'进入业务'));
 const epoch=renderId,context=brContext(),selected=brState.dashboardDay,month=brState.reportMonth||day().slice(0,7),range=brState.liveRange||{date_from:day().slice(0,8)+'01',date_to:day()};
 // The default page asks the server for its current month-to-date window.
 const query=new URLSearchParams({mode:mode==='daily'?'monthly':mode,group_by:(brState.dashboardGroup==='salesperson'?'performance':brState.dashboardGroup)||(state.store==='all'?'store':'performance')});
 if(mode==='daily'&&selected){query.set('date_from',selected.slice(0,8)+'01');query.set('date_to',selected);}
 if(mode==='monthly'){const [y,m]=month.split('-').map(Number);query.set('date_from',month+'-01');query.set('date_to',month+'-'+String(new Date(y,m,0).getDate()).padStart(2,'0'));}
 if(mode==='range'){query.set('date_from',range.date_from);query.set('date_to',range.date_to);}
 const result=await api(BR_API+'/dashboard-panels?'+query);if(epoch!==renderId||context!==brContext())return '';
 brState.liveDashboard=result;brState.liveDashboardContext=context;brState.liveDashboardMode=mode;brState.liveDashboardQuery=query.toString();brState.livePanelPages={};
 const tools=brLink('records-daily','日报核对')+(brCaps().record_statistics?brFlowButton('daily-observation','填写每日观察'):'')+((brCaps().manage_targets||brInternalRead())?brLink('records-targets','月度目标'):'')+brFlowButton('dashboard-fullscreen','全屏');
 return `<div id="br-live-dashboard">${huakangPageHeading(mode==='monthly'?'月度经营看板':mode==='range'?'范围经营看板':'经营累计看板','',tools)}<form class="br-live-controls" id="br-live-controls">${mode==='monthly'?`<label>查看月份<input type="month" name="month" value="${E(month)}" required></label>`:mode==='range'?`<label>开始日期<input type="date" name="date_from" value="${E(range.date_from)}" required></label><label>结束日期<input type="date" name="date_to" value="${E(range.date_to)}" required></label>`:`<label>截止日期<input type="date" name="day" value="${E(result.day)}" required></label>`}<label>明细比较<select name="group">${brOptions([{value:'performance',label:'展厅个人与批发渠道'},{value:'store',label:'授权门店'},{value:'brand',label:'品牌'}],query.get('group_by'))}</select></label><label>展示内容<select name="composition">${brOptions([{value:'all',label:'全部经营概览'},{value:'sales',label:'销售与现金车'},{value:'extended',label:'延伸业务'},...(brInternalRead()?[{value:'profit',label:'核定毛利'}]:[])],brState.dashboardComposition||'all')}</select></label>${brFlowButton('dashboard-refresh','刷新数据')}<span class="br-live-stamp" role="status"><i></i>更新于 ${E(time(result.updated_at))}</span></form><p class="br-dashboard-period">${E(brDashboardPeriod(result,mode))}</p><div id="br-dashboard-cards">${brDashboardCards(result)}</div></div>`;
}
function mountRealtimeDashboard(){
 const root=$('#br-live-dashboard');if(!root||!brState.liveDashboard||!brCanDashboard())return;
 const controls=$('#br-live-controls'),context=brContext(),route=state.route,query=brState.liveDashboardQuery;
 controls.onsubmit=event=>event.preventDefault();
 controls.onchange=event=>{const v=Object.fromEntries(new FormData(controls));if(!controls.reportValidity())return;if(v.date_from&&v.date_to&&v.date_from>v.date_to){toast('开始日期不能晚于结束日期。',true);return;}if(v.day&&event.target.name==='day')brState.dashboardDay=v.day;if(v.month)brState.reportMonth=v.month;if(v.date_from)brState.liveRange={date_from:v.date_from,date_to:v.date_to};brState.dashboardGroup=v.group;brState.dashboardComposition=v.composition;render();};
 clearTimeout(brDashboardTimer);
 brDashboardTimer=setTimeout(async()=>{
  if(context!==brContext()||route!==state.route||!root.isConnected||!brCanDashboard())return;
  if($('#modal').open||document.hidden){mountRealtimeDashboard();return;}
  try{
   const fresh=await api(BR_API+'/dashboard-panels?'+query);
   if(context!==brContext()||route!==state.route||!root.isConnected||!brCanDashboard())return;
   brState.liveDashboard=fresh;root.querySelector('#br-dashboard-cards').innerHTML=brDashboardCards(fresh);root.querySelector('.br-dashboard-period').textContent=brDashboardPeriod(fresh,brState.liveDashboardMode);if(controls.elements.day&&!brState.dashboardDay)controls.elements.day.value=fresh.day;root.querySelector('.br-live-stamp').innerHTML='<i></i>更新于 '+E(time(fresh.updated_at));mountRealtimeDashboard();
  }catch(error){if(context===brContext()&&route===state.route&&root.isConnected){root.querySelector('.br-live-stamp').textContent='刷新失败：'+error.message;mountRealtimeDashboard();}}
 },60000);
}
function brDisposeDashboardDetail(){document.querySelectorAll('[data-live-chart]').forEach(node=>RecordsCharts.dispose(node));$('#modal')?.classList.remove('br-dashboard-modal');brDashboardDetail=null;}
function leaveRealtimeDashboard(){clearTimeout(brDashboardTimer);brDashboardTimer=null;const dialog=$('#modal');if(brDashboardDetail&&dialog?.open)dialog.close();brDisposeDashboardDetail();}
function brLiveTable(panel,view,projection='comparison'){
 const summary=view==='summary',columns=(summary?panel.summary_columns:panel.columns)||[],all=(summary?panel.summary_rows:panel.rows)||[],pages=brState.livePanelPages||(brState.livePanelPages={}),id=brDashboardDetail?.id||panel.panel_id,key=id+'-'+projection+'-'+view,page=Math.min(pages[key]||1,Math.max(1,Math.ceil(all.length/100))),rows=all.slice((page-1)*100,page*100);
 const body=table(columns.map(c=>c.label+(c.unit?'（'+c.unit+'）':'')),[...rows,...(summary&&panel.grand_total?[panel.grand_total]:[])].map(row=>columns.map(c=>!summary&&['number','contract_number'].includes(c.key)&&row.contract_id?brLink('records-sales/'+row.contract_id,row[c.key]||'查看合同'):E(row[c.key]==null?(c.unit?'待审核':'—'):['money','percent','decimal'].includes(c.type)?brDashboardFixed(row[c.key]):row[c.key]))));
 return (!all.length?'<p class="br-dashboard-empty">'+E(panel.status_label||'待审核')+'</p>':'')+body+`<div class="pagination"><span>${all.length} 条 · 第 ${page} 页</span><div class="row">${brFlowButton('dashboard-page','上一页',`data-panel="${E(id)}" data-projection="${projection}" data-view="${view}" data-page="${page-1}" ${page<=1?'disabled':''}`)}${brFlowButton('dashboard-page','下一页',`data-panel="${E(id)}" data-projection="${projection}" data-view="${view}" data-page="${page+1}" ${page*100>=all.length?'disabled':''}`)}</div></div>`;
}
function brDashboardProjectionTools(id,projection){return `<div class="row">${brFlowButton('dashboard-export','导出统计表',`data-panel="${E(id)}" data-projection="${projection}" data-view="summary"`)}${brFlowButton('dashboard-export','导出来源明细',`data-panel="${E(id)}" data-projection="${projection}" data-view="details"`)}</div>`;}
function brDashboardPanelDetail(id,champion=false){
 if(!brCanDashboard()||brState.liveDashboardContext!==brContext())return;
 let panel=brState.liveDashboard?.panels.find(p=>p.panel_id===id);if(!panel)return;
 if(champion){panel={...panel,panel_title:'销冠 · 顾问实销',comparison:brState.liveDashboard.champion.comparison};id='champion';}
 brDisposeDashboardDetail();brDashboardDetail={id,panel,context:brContext(),route:state.route};
 const trend=panel.trend,comparison=panel.comparison,daily=champion?null:panel.daily,dailyLabel=daily?.date_to===brState.liveDashboard.today?'今日':'当日',group={salesperson:'销售顾问',performance:'展厅个人与批发渠道',category:'车型',store:'授权门店',brand:'品牌'}[comparison.group_by]||'分组';
 const dailySection=daily?`<details class="br-disclosure br-detail-section"><summary>${dailyLabel}变化 · ${E(daily.date_to)} · ${E(brDashboardDelta({value:daily.grand_total?.[daily.metric],unit:daily.unit,status_label:daily.status_label}))}</summary><div class="br-detail-heading"><p class="br-caption">仅包含 ${E(daily.date_to)} 当日记录</p>${brDashboardProjectionTools(id,'daily')}</div><div data-live-table="daily-details">${brLiveTable(daily,'details','daily')}</div></details>`:'';
 const dialog=modal(panel.panel_title||panel.title,`<div class="br-dashboard-detail"><p class="br-caption">${E(panel.period_basis||'')} · ${E(panel.status_label||'待审核')}</p>${dailySection}<section class="br-detail-section"><div class="br-detail-heading"><div><h3>${E(group)}比较</h3><p class="br-caption">${E(comparison.date_from)} 至 ${E(comparison.date_to)}</p></div>${brDashboardProjectionTools(id,'comparison')}</div><div class="br-live-chart" data-live-chart="comparison" aria-label="${E(group)}比较"></div><details class="br-disclosure"><summary>比较统计表</summary><div data-live-table="comparison-summary">${brLiveTable(comparison,'summary')}</div></details></section><details open class="br-disclosure br-detail-section"><summary>业务来源明细 · ${E(comparison.date_from)} 至 ${E(comparison.date_to)}</summary><div data-live-table="comparison-details">${brLiveTable(comparison,'details')}</div></details>${champion?'':`<section class="br-detail-section"><div class="br-detail-heading"><div><h3>每日趋势</h3><p class="br-caption">${E(trend.date_from)} 至 ${E(trend.date_to)}</p></div>${brDashboardProjectionTools(id,'trend')}</div><div class="br-live-chart" data-live-chart="trend" aria-label="每日趋势"></div><details class="br-disclosure"><summary>趋势统计表</summary><div data-live-table="trend-summary">${brLiveTable(trend,'summary','trend')}</div></details></section>`}</div>`);
 dialog.classList.add('br-dashboard-modal');dialog.addEventListener('close',brDisposeDashboardDetail,{once:true});
 for(const [name,projection] of [['trend',trend],['comparison',comparison]]){
  const chart=dialog.querySelector(`[data-live-chart="${name}"]`),points=projection.series||[];if(!chart)continue;
  if(!points.some(item=>item.value!==null&&item.value!==undefined&&String(item.value).trim()!=='')){chart.innerHTML=`<p class="rc-empty">${E(projection.status_label||'待审核')}</p>`;continue;}
  RecordsCharts.render(chart,{type:name==='trend'?'line':'rank',title:name==='trend'?'每日趋势':group+'比较',unit:projection.unit,precision:projection.precision??2,items:points,interval:'day',scope:'summary',compact:true});
 }
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-br-flow]');if(!button||button.disabled||state.storeSwitch)return;
 const action=button.dataset.brFlow;if(!['dashboard-fullscreen','dashboard-refresh','dashboard-detail','dashboard-export','dashboard-page','daily-observation'].includes(action))return;
 if(action!=='daily-observation'&&(!brCanDashboard()||brState.liveDashboardContext!==brContext()))return;
 button.disabled=true;
 try{
  if(action==='dashboard-fullscreen'){if(document.fullscreenElement)await document.exitFullscreen();else await $('#br-live-dashboard').requestFullscreen();}
  if(action==='dashboard-refresh')await render();
  if(action==='dashboard-detail')brDashboardPanelDetail(button.dataset.panel,button.dataset.champion==='true');
  if(action==='dashboard-page'||action==='dashboard-export'){
   const detail=brDashboardDetail;if(!detail||detail.context!==brContext()||detail.route!==state.route||detail.id!==button.dataset.panel)return;
   const projection=button.dataset.projection,view=button.dataset.view;if(!['trend','comparison','daily'].includes(projection)||!['summary','details'].includes(view))return;
   const panel=detail.panel[projection];if(!panel)return;
   if(action==='dashboard-page'){(brState.livePanelPages||(brState.livePanelPages={}))[detail.id+'-'+projection+'-'+view]=Number(button.dataset.page);document.querySelector(`[data-live-table="${projection}-${view}"]`).innerHTML=brLiveTable(panel,view,projection);}
   else{const query=new URLSearchParams(Object.entries({...panel.query,view}).filter(([,v])=>v!=null&&v!==''));await download(BR_API+'/reports/export?'+query,(detail.panel.panel_title||detail.panel.title)+'-'+({trend:'每日趋势',comparison:'期间比较',daily:'当日变化'}[projection])+'.csv');}
  }
  if(action==='daily-observation')await brNewManual('daily_operations');
 }catch(error){toast(error.message,true);}finally{if(button.isConnected)button.disabled=false;}
});
