/* Records-only display components. Values and permissions remain server-owned. */
(function(global){
'use strict';
const NS='http://www.w3.org/2000/svg', mounted=new WeakMap();
function node(tag,className,text){const n=document.createElement(tag);if(className)n.className=className;if(text!==undefined)n.textContent=String(text);return n;}
function svgNode(tag,attrs,text){const n=document.createElementNS(NS,tag);for(const [key,value] of Object.entries(attrs||{}))n.setAttribute(key,String(value));if(text!==undefined)n.textContent=String(text);return n;}
function resolve(container){return typeof container==='string'?document.querySelector(container):container;}
function numeric(value){return value!==null&&value!==undefined&&String(value).trim()!==''&&['number','string'].includes(typeof value)&&Number.isFinite(Number(value))?Number(value):null;}
function decimal(value){
 if(value===null||value===undefined)return null;
 const match=String(value).trim().match(/^([+-]?)(\d+)(?:\.(\d+))?$/);if(!match)return null;
 const integer=match[2].replace(/^0+(?=\d)/,''),fraction=match[3]||'';
 return {negative:match[1]==='-'&&/[1-9]/.test(integer+fraction),integer,fraction};
}
function exact(raw,supplied){return decimal(supplied)||decimal(raw);}
function compareDecimal(a,b){
 if(a.negative!==b.negative)return a.negative?-1:1;
 const length=Math.max(a.fraction.length,b.fraction.length);
 const x=a.integer+a.fraction.padEnd(length,'0'),y=b.integer+b.fraction.padEnd(length,'0');
 const direction=x.length===y.length?(x===y?0:x>y?1:-1):x.length>y.length?1:-1;
 return a.negative?-direction:direction;
}
function digits(spec){return Number.isInteger(spec.precision)?Math.max(0,Math.min(12,spec.precision)):2;}
function valueText(raw,supplied,spec){
 if(numeric(raw)===null)return '未知';
 const d=exact(raw,supplied);if(!d)return String(raw);
 const fraction=d.fraction.padEnd(digits(spec),'0');
 return (d.negative?'-':'')+d.integer.replace(/\B(?=(\d{3})+(?!\d))/g,',')+(fraction?'.'+fraction:'');
}
function withUnit(text,spec){return text==='未知'?text:text+(spec.unit?' '+spec.unit:'');}
function amount(raw,supplied,spec){return withUnit(valueText(raw,supplied,spec),spec);}
function originalRate(value){const text=String(value).trim();return text.endsWith('%')?text:text+'%';}
function rateText(actual,target,actualExact,targetExact){
 // This is a display ratio, never a replacement for the manually reported rate.
 const a=exact(actual,actualExact),t=exact(target,targetExact);
 if(a&&t){
  const scale=Math.max(a.fraction.length,t.fraction.length);
  const av=BigInt(a.integer+a.fraction.padEnd(scale,'0'));
  const tv=BigInt(t.integer+t.fraction.padEnd(scale,'0'));
  if(tv===0n||t.negative)return null;
  const rate=(av*10000n+tv/2n)/tv;
  return (a.negative&&rate!==0n?'-':'')+(rate/100n).toString()+'.'+(rate%100n).toString().padStart(2,'0')+'%';
 }
 const rate=actual/target*100;return Number.isFinite(rate)?rate.toFixed(2)+'%':'超出可绘制范围';
}
function picture(width,height,label,className){
 const svg=svgNode('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':label,class:className});
 svg.appendChild(svgNode('title',{},label));return svg;
}
function note(root,text,className='rc-note'){root.appendChild(node('p',className,text));}
function valueMeta(item){const parts=[];if(Number.isInteger(item.record_count))parts.push(item.record_count+' 条记录');if(item.unknown_count>0)parts.push(item.unknown_count+' 条数值未知');return parts.join(' · ');}
function rank(root,spec){
 const rows=spec.items.map((item,index)=>({...item,index,n:numeric(item.value),d:exact(item.value,item.exact_value)}));
 rows.sort((a,b)=>a.n===null?(b.n===null?a.index-b.index:1):b.n===null?-1:a.d&&b.d?-compareDecimal(a.d,b.d)||a.index-b.index:b.n-a.n||a.index-b.index);
 const values=rows.filter(r=>r.n!==null).map(r=>r.n),scale=Math.max(1,...values.map(Math.abs));
 const low=Math.min(0,...values.map(v=>v/scale)),high=Math.max(0,...values.map(v=>v/scale));
 const span=high-low||1,x=value=>1000*((value/scale)-low)/span,zero=x(0);
 const list=node('div','rc-rank-list');list.setAttribute('role','list');let previous=null,lastRank=0;
 rows.forEach((item,index)=>{
  let place=null;
  if(item.n!==null){const same=previous&&(item.d&&previous.d?compareDecimal(item.d,previous.d)===0:item.n===previous.n);place=same?lastRank:index+1;lastRank=place;previous=item;}
  const row=node('div','rc-rank-row'+(place!==null&&place<=3?' rc-top-'+place:''));row.setAttribute('role','listitem');if(place!==null)row.dataset.rank=String(place);
  const badge=node('span','rc-rank-badge',place===null?'—':place);badge.setAttribute('aria-label',place===null?'数值未知，不参与排名':'第 '+place+' 名');
  const body=node('div','rc-rank-body'),head=node('div','rc-rank-head');
  head.append(node('span','rc-item-label',item.label||'未命名'),node('strong','rc-exact',amount(item.value,item.exact_value,spec)));body.appendChild(head);
  if(item.n!==null){
   const chart=picture(1000,14,`${item.label}：${amount(item.value,item.exact_value,spec)}`,'rc-rank-bar');
   chart.appendChild(svgNode('line',{x1:0,y1:7,x2:1000,y2:7,class:'rc-bar-track'}));
   chart.appendChild(svgNode('line',{x1:zero,y1:0,x2:zero,y2:14,class:'rc-zero-line'}));
   if(item.n===0)chart.appendChild(svgNode('circle',{cx:zero,cy:7,r:3,class:'rc-zero-point'}));
   else chart.appendChild(svgNode('rect',{x:Math.min(zero,x(item.n)),y:3,width:Math.abs(x(item.n)-zero),height:8,rx:3,class:item.n<0?'rc-negative-fill':'rc-positive-fill'}));
   body.appendChild(chart);
  }else body.appendChild(node('div','rc-unknown','数值未知，不参与排名'));
  const meta=valueMeta(item);if(meta)body.appendChild(node('div','rc-row-meta',meta));
  row.append(badge,body);list.appendChild(row);
 });root.appendChild(list);
 note(root,'按数值从高到低排列；数值相同并列，未知值不参与排名。');
}
function monthNumber(label){const match=String(label).match(/^(\d{4})-(0[1-9]|1[0-2])$/);return match?Number(match[1])*12+Number(match[2])-1:null;}
function monthLabel(month){return String(Math.floor(month/12)).padStart(4,'0')+'-'+String(month%12+1).padStart(2,'0');}
function axisText(value){return new Intl.NumberFormat('zh-CN',{maximumFractionDigits:10}).format(Object.is(value,-0)?0:value);}
function line(root,spec,width){
 const byMonth=new Map(),invalid=[];
 for(const item of spec.items){const month=monthNumber(item.label);if(month===null){invalid.push(item);continue;}const existing=byMonth.get(month);if(existing)existing.duplicates.push(item);else byMonth.set(month,{...item,month,duplicates:[]});}
 if(!byMonth.size){note(root,'没有有效的月份数据。月份须为 YYYY-MM。','rc-empty');return;}
 const ordered=Array.from(byMonth.keys()).sort((a,b)=>a-b),first=ordered[0],last=ordered[ordered.length-1],points=[];
 for(let month=first;month<=last;month++){
  const item=byMonth.get(month);points.push(item?{...item,n:item.duplicates.length?null:numeric(item.value),missing:false}:{label:monthLabel(month),month,n:null,missing:true,duplicates:[]});
 }
 const values=points.filter(p=>p.n!==null).map(p=>p.n),scale=Math.max(1,...values.map(Math.abs));
 let low=Math.min(0,...values.map(v=>v/scale)),high=Math.max(0,...values.map(v=>v/scale));if(low===high)high=low+1;
 const ticks=Array.from({length:5},(_,i)=>low+(high-low)*i/4);
 const left=Math.max(64,...ticks.map(t=>axisText(t*scale).length*7+14)),right=36,top=24,bottom=48,height=304;
 const chartWidth=Math.max(width,left+right+Math.max(1,points.length-1)*80),plot=chartWidth-left-right;
 const x=index=>left+(points.length===1?plot/2:index*plot/(points.length-1)),y=value=>top+(high-value/scale)/(high-low)*(height-top-bottom);
 const chart=picture(chartWidth,height,spec.title||'月度趋势','rc-line-svg');chart.setAttribute('width',String(chartWidth));chart.setAttribute('height',String(height));
 ticks.forEach(tick=>{const yy=y(tick*scale);chart.appendChild(svgNode('line',{x1:left,x2:chartWidth-right,y1:yy,y2:yy,class:tick===0?'rc-zero-line':'rc-grid-line'}));chart.appendChild(svgNode('text',{x:left-12,y:yy+4,'text-anchor':'end',class:'rc-axis-label'},axisText(tick*scale)));});
 let segment=[];
 const flush=()=>{if(segment.length>1)chart.appendChild(svgNode('polyline',{points:segment.join(' '),class:'rc-line-segment'}));segment=[];};
 points.forEach((item,index)=>{if(item.n===null){flush();return;}segment.push(x(index)+','+y(item.n));});flush();
 const descriptions=node('div','rc-month-values');
 points.forEach((item,index)=>{
  chart.appendChild(svgNode('text',{x:x(index),y:height-14,'text-anchor':'middle',class:'rc-axis-label'},item.label));
  const status=item.missing?'无记录':item.duplicates.length?'多条记录，未合并':item.n===null?'数值未知':amount(item.value,item.exact_value,spec);
  if(item.n!==null){const point=svgNode('circle',{cx:x(index),cy:y(item.n),r:4.5,class:'rc-line-point','data-month':item.label,tabindex:0,'aria-label':item.label+'：'+status});point.appendChild(svgNode('title',{},item.label+'：'+status));chart.appendChild(point);}
  else chart.appendChild(svgNode('text',{x:x(index),y:height-bottom+20,'text-anchor':'middle',class:'rc-gap-label'},item.missing?'无记录':'未知'));
  const cell=node('div','rc-month-value'+(item.n===null?' rc-month-unknown':''));cell.dataset.month=item.label;
  cell.append(node('span','rc-month-label',item.label),node('strong','rc-exact',status));
  if(item.duplicates.length)cell.appendChild(node('span','rc-row-meta',[item,...item.duplicates].map(row=>amount(row.value,row.exact_value,spec)).join(' / ')));
  const meta=valueMeta(item);if(meta)cell.appendChild(node('span','rc-row-meta',meta));descriptions.appendChild(cell);
 });
 const scroll=node('div','rc-line-scroll');scroll.setAttribute('tabindex','0');scroll.setAttribute('aria-label','按月份横向滚动查看趋势');scroll.appendChild(chart);root.append(scroll,descriptions);
 note(root,'月份按时间顺序排列；无记录和未知值保留断点，不补零。'+(byMonth.size!==spec.items.length-invalid.length?'同月份的多条记录未擅自合并。':''));
 if(invalid.length)note(root,'以下月份格式无法绘制：'+invalid.map(item=>String(item.label)+'（'+amount(item.value,item.exact_value,spec)+'）').join('；'),'rc-warning');
}
function progress(root,spec,width){
 const list=node('div','rc-progress-list');
 for(const item of spec.items){
  const actual=numeric(item.actual),target=numeric(item.target),row=node('section','rc-progress-row');
  const head=node('div','rc-progress-head');head.appendChild(node('strong','rc-item-label',item.label||'未命名'));if(item.period)head.appendChild(node('span','rc-period',item.period));row.appendChild(head);
  const facts=node('div','rc-progress-facts'),actualFact=node('div'),targetFact=node('div');
  actualFact.append(node('span','rc-fact-label','实际'),node('strong','rc-actual',amount(item.actual,item.actual_exact,spec)));
  targetFact.append(node('span','rc-fact-label','目标'),node('strong','rc-target',amount(item.target,item.target_exact,spec)));facts.append(actualFact,targetFact);row.appendChild(facts);
  if(target!==null&&target>0&&actual!==null){
   const rate=rateText(actual,target,item.actual_exact,item.target_exact),rateRow=node('div','rc-progress-result');
   rateRow.append(node('span','rc-fact-label','按实际 / 目标计算'),node('strong','rc-progress-rate',rate));
   if(actual>target)rateRow.appendChild(node('span','rc-over-target','超过目标'));row.appendChild(rateRow);
   const chartWidth=Math.max(240,width-44),scale=Math.max(Math.abs(actual),target),low=Math.min(0,actual/scale),high=Math.max(target/scale,actual/scale),x=v=>12+(v/scale-low)/(high-low)*(chartWidth-24);
   const chart=picture(chartWidth,42,`${item.label}，实际 ${amount(item.actual,item.actual_exact,spec)}，目标 ${amount(item.target,item.target_exact,spec)}，达成率 ${rate}`,'rc-progress-svg');
   chart.appendChild(svgNode('line',{x1:12,x2:chartWidth-12,y1:15,y2:15,class:'rc-progress-track'}));
   if(actual===0)chart.appendChild(svgNode('circle',{cx:x(0),cy:15,r:4,class:'rc-zero-point'}));
   else chart.appendChild(svgNode('rect',{x:Math.min(x(0),x(actual)),y:9,width:Math.abs(x(actual)-x(0)),height:12,rx:4,class:actual<0?'rc-negative-fill':'rc-positive-fill'}));
   chart.appendChild(svgNode('line',{x1:x(0),x2:x(0),y1:4,y2:25,class:'rc-zero-line'}));
   chart.appendChild(svgNode('line',{x1:x(target),x2:x(target),y1:1,y2:28,class:'rc-target-marker'}));
   chart.appendChild(svgNode('text',{x:x(target),y:41,'text-anchor':x(target)>chartWidth-70?'end':x(target)<70?'start':'middle',class:'rc-target-label'},'目标 100%'));row.appendChild(chart);
  }else note(row,target===null?'未填写目标，不计算达成率。':target===0?'目标为 0，不计算达成率。':target<0?'目标为负，不计算达成率。':'未填写实际值，不计算达成率。','rc-progress-unavailable');
  if(item.reported_rate!==null&&item.reported_rate!==undefined&&String(item.reported_rate).trim()!=='')row.appendChild(node('div','rc-reported-rate','填报完成率：'+originalRate(item.reported_rate)+'（原表人工填写）'));
  list.appendChild(row);
 }root.appendChild(list);note(root,'每项仅对比同一条记录的实际与目标；图形按实际 / 目标绘制，超额完整显示。');
}
function dispose(container){const target=resolve(container);if(!target)return;const state=mounted.get(target);if(state){if(state.observer)state.observer.disconnect();if(state.listener)global.removeEventListener('resize',state.listener);mounted.delete(target);}target.replaceChildren();}
function render(container,options){
 const target=resolve(container);if(!target||typeof target.replaceChildren!=='function')throw new Error('图表容器不可用。');
 const spec={...options,items:Array.isArray(options?.items)?options.items.filter(item=>item&&typeof item==='object'):[]};
 if(!['rank','line','progress'].includes(spec.type))throw new Error('不支持的记录图表类型。');dispose(target);
 const state={width:0,observer:null,listener:null};mounted.set(target,state);
 const paint=()=>{
  if(mounted.get(target)!==state)return;
  const style=global.getComputedStyle(target);
  const width=Math.max(280,Math.floor(target.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight)));if(state.width===width)return;state.width=width;
  const root=node('section','records-chart');root.dataset.chartType=spec.type;root.setAttribute('aria-label',spec.title||'业务记录图表');
  if(spec.unit)note(root,'单位：'+spec.unit,'rc-unit');
  if(!spec.items.length)note(root,'所选范围暂无记录。','rc-empty');else if(spec.type==='rank')rank(root,spec);else if(spec.type==='line')line(root,spec,width);else progress(root,spec,width);
  target.replaceChildren(root);
 };paint();
 if(typeof global.ResizeObserver==='function'){state.observer=new global.ResizeObserver(paint);state.observer.observe(target);}else{state.listener=paint;global.addEventListener('resize',paint);}
 return target.firstElementChild;
}
global.RecordsCharts=Object.freeze({render,dispose});
})(window);
