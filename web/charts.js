/* DealerDesk 数据可视化：依赖为零的 SVG 图表模块（CSP: script-src 'self'；无 CDN、无内联脚本）。
   服务器契约：金额一律是整数分（cents），unit 为 "money" 或 "count"；trends[].dates 与每条
   series.values 等长且已补零，本模块仍容忍长度不一致。所有颜色与字号写在元素属性上，
   导出的 SVG / PNG 不依赖外部样式表；无 innerHTML、无 eval、无外部请求，交互一律 addEventListener。 */
'use strict';
(function(global){
const SVG_NS='http://www.w3.org/2000/svg';
const FONT='Inter,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif';
const COLORS=['#0d7465','#c9882e','#4a6fa5','#a2608f','#5b8f6d','#b3543f','#7d8a3c','#5f6f80','#8d6a4f'];
const INK='#24493d',MUTED='#8b9a92',FAINT='#aab7b1',GRID='#e8eeea',AXIS='#cfdcd6';
const EMPTY_TEXT='所选期间暂无数据';
const MAX_SLICES=9;
const TIP_CSS='position:absolute;z-index:6;pointer-events:none;background:#112d32;color:#fff;padding:7px 10px;border-radius:8px;font-size:12px;line-height:1.65;white-space:nowrap;box-shadow:0 6px 20px #112d3240;transform:translate(-50%,-108%);left:0;top:0;opacity:0;visibility:hidden;transition:opacity .12s';
const mounted=new WeakMap();

/* ---------- 元素、数值与文本 ---------- */
function num(value){const n=Number(value);return isFinite(n)?n:0;}
function f(value){return Math.round(num(value)*100)/100;}
function toCents(value){return Math.round(num(value));}
function grouped(digits){return digits.replace(/\B(?=(\d{3})+(?!\d))/g,',');}
function money(cents){
  const value=toCents(cents),sign=value<0?'-':'',abs=Math.abs(value);
  return sign+'¥'+grouped(String(Math.floor(abs/100)))+'.'+String(abs%100).padStart(2,'0');
}
function count(value){return grouped(String(Math.round(num(value))));}
function trimmed(text){return text.indexOf('.')<0?text:text.replace(/0+$/,'').replace(/\.$/,'');}
function compactYuan(yuan){
  const value=num(yuan),sign=value<0?'-':'',abs=Math.abs(value);
  if(abs>=1e8)return sign+trimmed((abs/1e8).toFixed(2))+'亿';
  if(abs>=1e4)return sign+trimmed((abs/1e4).toFixed(abs>=1e5?0:1))+'万';
  return sign+grouped(String(Math.round(abs)));
}
function compactCount(value){
  const v=num(value),sign=v<0?'-':'',abs=Math.abs(v);
  if(abs>=1e8)return sign+trimmed((abs/1e8).toFixed(2))+'亿';
  if(abs>=1e4)return sign+trimmed((abs/1e4).toFixed(1))+'万';
  return sign+grouped(String(Math.round(abs)));
}
function decimal(value){return new Intl.NumberFormat('zh-CN',{maximumFractionDigits:3}).format(num(value));}
function valueText(value,unit){return unit==='count'?count(value):unit==='yuan'?'¥'+new Intl.NumberFormat('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}).format(num(value)):unit==='percent'?decimal(value)+'%':unit==='decimal'?decimal(value):money(value);}
function tickText(value,unit){return unit==='percent'?decimal(value)+'%':unit==='decimal'?decimal(value):unit==='count'?(Number.isInteger(value)?compactCount(value):decimal(value)):compactYuan(value);}
function compactValue(value,unit){return unit==='yuan'?compactYuan(value):['percent','decimal'].includes(unit)?valueText(value,unit):unit==='count'?compactCount(value):compactYuan(num(value)/100);}
function toDisplay(value,unit){return unit==='money'?num(value)/100:num(value);}
function textWidth(text,size){
  let width=0;
  for(const ch of String(text))width+=/[\u2e80-\u9fff\uff00-\uffef]/.test(ch)?size:size*0.58;
  return width;
}
function truncate(text,size,maxWidth){
  const source=String(text===null||text===undefined?'':text);
  if(textWidth(source,size)<=maxWidth)return source;
  let out='';
  for(const ch of source){if(textWidth(out+ch+'…',size)>maxWidth)break;out+=ch;}
  return out?out+'…':'…';
}
function shortDate(value,index){const text=value===null||value===undefined?'':String(value);return text?(text.length>=10?text.slice(5):text):('#'+(index+1));}
function longDate(value,index){const text=value===null||value===undefined?'':String(value);return text||('第 '+(index+1)+' 个数据点');}
function el(tag,attrs,text){
  const node=document.createElementNS(SVG_NS,tag);
  if(attrs)for(const key in attrs){const value=attrs[key];if(value===null||value===undefined||value===false)continue;node.setAttribute(key,String(value));}
  if(text!==undefined&&text!==null)node.textContent=String(text);
  return node;
}
function div(cls,text){const node=document.createElement('div');if(cls)node.className=cls;if(text!==undefined&&text!==null)node.textContent=String(text);return node;}
// 内联样式一律走 CSSOM：本应用开启 style-src 'self'，style 属性可能被 CSP 拒绝，
// 而 node.style 的赋值不受 CSP 限制（SVG 的颜色/字号仍写在表现属性上，导出时不依赖 CSS）。
function css(node,value){
  if(node.style&&typeof node.style.cssText==='string'){node.style.cssText=value;return node;}
  node.setAttribute('style',value);
  return node;
}
function clear(node){while(node.firstChild)node.removeChild(node.firstChild);return node;}
function kids(node){return node&&node.childNodes?Array.prototype.slice.call(node.childNodes):[];}
function resolve(container){return typeof container==='string'?document.querySelector(container):container;}
function remember(node,spec){if(node&&typeof node==='object')node.__chartMeta={title:String(spec.title||''),subtitle:String(spec.subtitle||'')};}

/* ---------- 刻度与布局 ---------- */
function niceNumber(range,round){
  if(!(range>0))return 1;
  const exponent=Math.floor(Math.log10(range)),fraction=range/Math.pow(10,exponent);
  let nice;
  if(round)nice=fraction<1.5?1:fraction<3?2:fraction<7?5:10;
  else nice=fraction<=1?1:fraction<=2?2:fraction<=5?5:10;
  return nice*Math.pow(10,exponent);
}
function niceTicks(min,max,countTarget){
  let lo=num(min),hi=num(max);
  if(!(hi>lo)){if(lo===0)return [0,1];const pad=Math.abs(lo)*0.5||1;lo-=pad;hi+=pad;}
  const step=niceNumber(niceNumber(hi-lo,false)/(Math.max(2,num(countTarget))-1),true);
  const start=Math.floor(lo/step)*step,end=Math.ceil(hi/step)*step;
  const ticks=[];
  for(let value=start;value<=end+step*1e-6&&ticks.length<24;value+=step)ticks.push(Number(value.toFixed(10)));
  return ticks.length>1?ticks:[start,start+step];
}
function xLabelIndexes(points,plotW){
  if(points<2)return points===1?[0]:[];
  const maxLabels=Math.max(2,Math.floor(plotW/76)),step=Math.max(1,Math.ceil(points/maxLabels)),out=[];
  for(let index=0;index<points;index+=step)out.push(index);
  const last=out[out.length-1];
  if(last!==points-1&&(points-1-last)*plotW/(points-1)>=44)out.push(points-1);
  return out;
}
function measureWidth(container,spec){
  const fallback=num(spec&&spec.width)||720;
  if(container&&typeof container.getBoundingClientRect==='function'){
    const rect=container.getBoundingClientRect();
    if(rect&&num(rect.width)>0)return Math.max(280,Math.round(rect.width));
  }
  return fallback;
}
function chartLabel(spec){
  const parts=[spec&&spec.title?String(spec.title):'图表'];
  if(spec&&spec.subtitle)parts.push(String(spec.subtitle));
  return parts.join(' · ');
}
function baseSvg(width,height,spec){
  const label=chartLabel(spec);
  const svg=el('svg',{viewBox:'0 0 '+width+' '+height,role:'img','aria-label':label,'font-family':FONT});
  css(svg,'display:block;width:100%;height:auto;overflow:visible');
  svg.__chartMeta={title:String(spec&&spec.title||''),subtitle:String(spec&&spec.subtitle||'')};
  svg.appendChild(el('title',null,label));
  return svg;
}
function emptySvg(width,height,spec,message,hint){
  const svg=baseSvg(width,height,spec);
  const left=Math.min(52,width*0.16),right=14,top=14,bottom=32;
  const plotW=Math.max(10,width-left-right);
  const dates=Array.isArray(spec&&spec.dates)?spec.dates:[];
  const series=Array.isArray(spec&&spec.series)?spec.series:[];
  const points=Math.max(dates.length,0);
  const wide=Math.max(points,...series.map(item=>item&&Array.isArray(item.values)?item.values.length:0));
  const x=index=>wide>1?left+plotW*index/(wide-1):left+plotW/2;
  svg.appendChild(el('line',{x1:left,x2:width-right,y1:height-bottom,y2:height-bottom,stroke:AXIS,'stroke-width':1}));
  for(const index of xLabelIndexes(points,plotW))svg.appendChild(el('text',{x:f(x(index)),y:height-bottom+16,'text-anchor':'middle','font-size':10,fill:MUTED},shortDate(dates[index],index)));
  const centerY=top+(height-top-bottom)/2;
  svg.appendChild(el('text',{x:f(width/2),y:f(centerY),'text-anchor':'middle','font-size':13,fill:INK},message||EMPTY_TEXT));
  if(hint)svg.appendChild(el('text',{x:f(width/2),y:f(centerY+20),'text-anchor':'middle','font-size':11,fill:FAINT},hint));
  return svg;
}/* ---------- 悬停提示 ---------- */
function tipNode(){const node=div('chart-tooltip');node.setAttribute('role','status');return css(node,TIP_CSS);}
function tipRows(tip,title,rows){
  clear(tip);
  if(title)tip.appendChild(css(div('chart-tooltip-title',String(title)),'font-weight:650;margin-bottom:4px'));
  for(const row of rows){
    const line=div('chart-tooltip-row');
    css(line,'display:flex;align-items:center;gap:7px');
    if(row.color){
      const dot=div('chart-tooltip-dot');
      css(dot,'width:8px;height:8px;border-radius:50%;flex:0 0 auto;background:'+row.color);
      line.appendChild(dot);
    }
    line.appendChild(css(div('chart-tooltip-label',String(row.label)),'opacity:.85'));
    line.appendChild(css(div('chart-tooltip-value',String(row.value)),'margin-left:auto;font-variant-numeric:tabular-nums;font-weight:650'));
    tip.appendChild(line);
  }
}
function tipPlace(tip,x,y,width){
  if(!tip)return;
  const limit=Math.max(52,width-52),left=Math.max(52,Math.min(limit,num(x)));
  css(tip,TIP_CSS+';left:'+f(left)+'px;top:'+f(Math.max(30,num(y)))+'px;opacity:1;visibility:visible');
}
function tipHide(tip){if(tip)css(tip,TIP_CSS);}
function pointerLocal(event,svg,container,logicalWidth){
  const box=typeof svg.getBoundingClientRect==='function'?svg.getBoundingClientRect():null;
  const outer=container&&typeof container.getBoundingClientRect==='function'?container.getBoundingClientRect():null;
  const scale=box&&num(box.width)?logicalWidth/num(box.width):1;
  return {x:(num(event.clientX)-num(box&&box.left))*scale,y:(num(event.clientY)-num(box&&box.top))*scale,
    tipX:num(event.clientX)-num(outer&&outer.left),tipY:num(event.clientY)-num(outer&&outer.top)};
}
function legendRow(color,label,meta){
  const row=div('chart-legend-row');
  css(row,'display:flex;align-items:center;gap:8px;min-width:0');
  const dot=div('chart-legend-dot');
  css(dot,'width:9px;height:9px;border-radius:3px;flex:0 0 auto;background:'+color);
  row.appendChild(dot);
  row.appendChild(css(div('chart-legend-label',String(label)),'flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'));
  if(meta)row.appendChild(css(div('chart-legend-value',String(meta)),'flex:0 0 auto;font-variant-numeric:tabular-nums;color:#5d7a6e'));
  return row;
}
function legendBox(rows){
  const box=div('chart-legend');
  for(const row of rows)box.appendChild(row);
  return box;
}

/* ---------- 挂载：按容器宽度绘制，容器尺寸变化时重绘 ---------- */
function mount(container,spec,build){
  const node=resolve(container);
  if(!node||typeof node.appendChild!=='function')throw new Error('图表容器不可用。');
  const previous=mounted.get(node);
  if(previous&&previous.observer)previous.observer.disconnect();
  const state={spec:spec,width:0,observer:null};
  mounted.set(node,state);
  if(node.getAttribute&&!node.getAttribute('style'))css(node,'position:relative;min-width:0');
  const paint=width=>{
    const built=build(width,node)||{};
    clear(node);
    if(built.svg)node.appendChild(built.svg);
    if(built.extra)for(const extra of built.extra)node.appendChild(extra);
    if(built.tip)node.appendChild(built.tip);
    state.width=width;
    return built;
  };
  const built=paint(measureWidth(node,spec));
  if(typeof ResizeObserver==='function'){
    const observer=new ResizeObserver(()=>{
      if(mounted.get(node)!==state)return;
      const width=measureWidth(node,spec);
      if(Math.abs(width-state.width)<4)return;
      paint(width);
    });
    state.observer=observer;
    try{observer.observe(node);}catch(error){}
  }
  return built.svg||null;
}

/* ---------- 折线图：多系列，x 轴为日期 ---------- */
function line(container,spec){
  spec=spec||{};
  const node=resolve(container);
  const series=(Array.isArray(spec.series)?spec.series:[]).filter(item=>item&&Array.isArray(item.values));
  const dates=Array.isArray(spec.dates)?spec.dates:[];
  const unit=['count','percent','decimal','yuan'].includes(spec.unit)?spec.unit:'money';
  remember(node,spec);
  return mount(container,spec,width=>{
    const points=Math.max(dates.length,...series.map(item=>item.values.length),0);
    const height=num(spec.height)||(width<470?252:300);
    const magnitude=series.reduce((total,item)=>total+item.values.reduce((sum,value)=>sum+Math.abs(num(value)),0),0);
    if(!points||!series.length||magnitude===0){
      return {svg:emptySvg(width,height,spec,EMPTY_TEXT,!points?'没有可绘制的数据点':'所有数值均为 0，未绘制折线')};
    }
    const left=Math.max(46,Math.min(66,width*0.11)),right=16,top=16,bottom=34;
    const plotW=Math.max(10,width-left-right),plotH=Math.max(10,height-top-bottom);
    const values=series.map(item=>{
      const row=[];
      for(let index=0;index<points;index++)row.push(toDisplay(item.values[index],unit));
      return row;
    });
    const flat=values.reduce((all,row)=>all.concat(row),[]);
    const ticks=niceTicks(Math.min(0,Math.min.apply(null,flat)),Math.max(0,Math.max.apply(null,flat)),5);
    const yMin=ticks[0],yMax=ticks[ticks.length-1];
    const x=index=>points>1?left+plotW*index/(points-1):left+plotW/2;
    const y=value=>top+plotH*(1-(value-yMin)/(yMax-yMin));
    const svg=baseSvg(width,height,spec);
    for(const tick of ticks){
      const gridY=f(y(tick));
      svg.appendChild(el('line',{x1:left,x2:width-right,y1:gridY,y2:gridY,stroke:tick===0?AXIS:GRID,'stroke-width':1}));
      svg.appendChild(el('text',{x:left-8,y:f(y(tick)+3.5),'text-anchor':'end','font-size':10,fill:MUTED},tickText(tick,unit)));
    }
    for(const index of xLabelIndexes(points,plotW)){
      svg.appendChild(el('text',{x:f(x(index)),y:height-bottom+17,'text-anchor':'middle','font-size':10,fill:MUTED},shortDate(dates[index],index)));
    }
    series.forEach((item,index)=>{
      const color=COLORS[index%COLORS.length];
      const path=values[index].map((value,position)=>(position?'L':'M')+' '+f(x(position))+' '+f(y(value))).join(' ');
      svg.appendChild(el('path',{d:path,fill:'none',stroke:color,'stroke-width':2,'stroke-linejoin':'round','stroke-linecap':'round'}));
      if(points<=48)values[index].forEach((value,position)=>svg.appendChild(el('circle',{cx:f(x(position)),cy:f(y(value)),r:2.6,fill:'#ffffff',stroke:color,'stroke-width':1.6})));
    });
    const layer=el('g',{'data-chart-ui':'1'});
    const guide=el('line',{x1:0,x2:0,y1:top,y2:top+plotH,stroke:'#b9cbc3','stroke-width':1,'stroke-dasharray':'3 3',visibility:'hidden'});
    layer.appendChild(guide);
    const markers=series.map((item,index)=>el('circle',{r:3.8,fill:COLORS[index%COLORS.length],stroke:'#ffffff','stroke-width':1.4,visibility:'hidden'}));
    for(const marker of markers)layer.appendChild(marker);
    svg.appendChild(layer);
    const catcher=el('rect',{x:left,y:top,width:plotW,height:plotH,fill:'transparent','pointer-events':'all','data-chart-ui':'1'});
    svg.appendChild(catcher);
    const tip=tipNode();
    const move=event=>{
      const point=pointerLocal(event,svg,node,width);
      const raw=points>1?Math.round((point.x-left)/(plotW/(points-1))):0;
      const index=Math.max(0,Math.min(points-1,raw)),guideX=x(index);
      guide.setAttribute('x1',f(guideX));guide.setAttribute('x2',f(guideX));guide.setAttribute('visibility','visible');
      const rows=series.map((item,position)=>{
        markers[position].setAttribute('cx',f(guideX));
        markers[position].setAttribute('cy',f(y(values[position][index])));
        markers[position].setAttribute('visibility','visible');
        return {color:COLORS[position%COLORS.length],label:item.label||item.key||('系列 '+(position+1)),value:valueText(item.values[index],unit)};
      });
      tipRows(tip,longDate(dates[index],index),rows);
      tipPlace(tip,point.tipX,point.tipY,width);
    };
    const leave=()=>{
      guide.setAttribute('visibility','hidden');
      for(const marker of markers)marker.setAttribute('visibility','hidden');
      tipHide(tip);
    };
    catcher.addEventListener('pointermove',move);
    catcher.addEventListener('pointerdown',move);
    catcher.addEventListener('pointerleave',leave);
    catcher.addEventListener('pointercancel',leave);
    const extra=series.length>1?[legendBox(series.map((item,index)=>legendRow(COLORS[index%COLORS.length],item.label||item.key||('系列 '+(index+1)),'')))]:null;
    return {svg:svg,tip:tip,extra:extra};
  });
}/* ---------- 柱状图：单系列 ---------- */
function bar(container,spec){
  spec=spec||{};
  const node=resolve(container);
  const items=(Array.isArray(spec.items)?spec.items:[]).filter(item=>item);
  const unit=['count','percent','decimal','yuan'].includes(spec.unit)?spec.unit:'money';
  const horizontal=spec.horizontal===undefined?items.length>7:!!spec.horizontal;
  remember(node,spec);
  return mount(container,spec,width=>{
    const values=items.map(item=>toDisplay(item.value,unit));
    const magnitude=values.reduce((total,value)=>total+Math.abs(value),0);
    if(!items.length||magnitude===0){
      const height=num(spec.height)||(horizontal?Math.max(160,items.length*30+46):280);
      return {svg:emptySvg(width,height,spec,EMPTY_TEXT,items.length?'所有数值均为 0':'没有可绘制的分类')};
    }
    return horizontal?barHorizontal(node,width,spec,items,values,unit):barVertical(node,width,spec,items,values,unit);
  });
}
function barTip(node,svg,width,tip,item,unit){
  const label=String(item.label||item.key||'');
  return event=>{
    const point=pointerLocal(event,svg,node,width);
    tipRows(tip,label,[{color:COLORS[0],label:label,value:valueText(item.value,unit)}]);
    tipPlace(tip,point.tipX,point.tipY,width);
  };
}
function barHover(bar,tip){
  bar.addEventListener('pointerenter',()=>bar.setAttribute('fill','#095c50'));
  bar.addEventListener('pointerleave',()=>{bar.setAttribute('fill',COLORS[0]);tipHide(tip);});
}
function barVertical(node,width,spec,items,values,unit){
  const height=num(spec.height)||280;
  const left=Math.max(46,Math.min(66,width*0.11)),right=14,top=26,bottom=56;
  const plotW=Math.max(10,width-left-right),plotH=Math.max(10,height-top-bottom);
  const ticks=niceTicks(Math.min(0,Math.min.apply(null,values)),Math.max(0,Math.max.apply(null,values)),5);
  const yMin=ticks[0],yMax=ticks[ticks.length-1];
  const y=value=>top+plotH*(1-(value-yMin)/(yMax-yMin));
  const base=f(y(0)),band=plotW/items.length,barW=Math.max(3,Math.min(46,band*0.62));
  const svg=baseSvg(width,height,spec);
  for(const tick of ticks){
    const gridY=f(y(tick));
    svg.appendChild(el('line',{x1:left,x2:width-right,y1:gridY,y2:gridY,stroke:tick===0?AXIS:GRID,'stroke-width':1}));
    svg.appendChild(el('text',{x:left-8,y:f(y(tick)+3.5),'text-anchor':'end','font-size':10,fill:MUTED},tickText(tick,unit)));
  }
  const tip=tipNode();
  items.forEach((item,index)=>{
    const value=values[index],center=left+band*(index+0.5),barY=y(value);
    const rectTop=f(Math.min(barY,base)),rectHeight=f(Math.abs(barY-base));
    const bar=el('rect',{x:f(center-barW/2),y:rectTop,width:f(barW),height:rectHeight<0.6?0:rectHeight,rx:2,fill:COLORS[0]});
    bar.appendChild(el('title',null,String(item.label||item.key||'')+'：'+valueText(item.value,unit)));
    svg.appendChild(bar);
    barHover(bar,tip);
    const move=barTip(node,svg,width,tip,item,unit);
    bar.addEventListener('pointermove',move);
    bar.addEventListener('pointerdown',move);
    if(value!==0&&band>=30){
      const exact=valueText(item.value,unit),label=textWidth(exact,10)<=band-6?exact:compactValue(item.value,unit);
      if(textWidth(label,10)<=band-4)svg.appendChild(el('text',{x:f(center),y:f(Math.min(barY,base)-5),'text-anchor':'middle','font-size':10,fill:'#5d7a6e'},label));
    }
    svg.appendChild(el('text',{x:f(center),y:height-bottom+17,'text-anchor':'middle','font-size':10,fill:MUTED},truncate(item.label===undefined?item.key:item.label,10,Math.max(18,band-4))));
  });
  return {svg:svg,tip:tip};
}
function barHorizontal(node,width,spec,items,values,unit){
  const rowHeight=30,height=num(spec.height)||Math.max(160,items.length*rowHeight+46);
  const labelWidth=Math.min(150,Math.max(56,Math.max.apply(null,items.map(item=>textWidth(item.label===undefined?item.key:item.label,10)))+16));
  const valueWidth=Math.max.apply(null,items.map(item=>textWidth(valueText(item.value,unit),10)));
  const left=labelWidth,right=Math.max(58,Math.min(150,valueWidth+20)),top=14,bottom=30;
  const plotW=Math.max(10,width-left-right),plotH=Math.max(10,height-top-bottom);
  const hi=Math.max(0,Math.max.apply(null,values)),lo=Math.min(0,Math.min.apply(null,values)),span=hi-lo||1;
  const x=value=>left+plotW*(value-lo)/span;
  const band=plotH/items.length,barH=Math.max(4,Math.min(20,band*0.6));
  const svg=baseSvg(width,height,spec);
  for(const tick of niceTicks(lo,hi,4)){
    const gridX=f(x(tick));
    svg.appendChild(el('line',{x1:gridX,x2:gridX,y1:top,y2:height-bottom,stroke:tick===0?AXIS:GRID,'stroke-width':1}));
    svg.appendChild(el('text',{x:gridX,y:height-bottom+16,'text-anchor':'middle','font-size':10,fill:MUTED},tickText(tick,unit)));
  }
  const tip=tipNode();
  items.forEach((item,index)=>{
    const value=values[index],center=top+band*(index+0.5),barWidth=f(Math.abs(x(value)-x(0)));
    const bar=el('rect',{x:f(Math.min(x(0),x(value))),y:f(center-barH/2),width:barWidth<0.6?0:barWidth,height:f(barH),rx:2,fill:COLORS[0]});
    bar.appendChild(el('title',null,String(item.label||item.key||'')+'：'+valueText(item.value,unit)));
    svg.appendChild(bar);
    barHover(bar,tip);
    const move=barTip(node,svg,width,tip,item,unit);
    bar.addEventListener('pointermove',move);
    bar.addEventListener('pointerdown',move);
    svg.appendChild(el('text',{x:left-8,y:f(center+3.5),'text-anchor':'end','font-size':10,fill:MUTED},truncate(item.label===undefined?item.key:item.label,10,Math.max(20,left-14))));
    if(value!==0){
      const text=valueText(item.value,unit),outside=textWidth(text,10)<=plotW-barWidth-8;
      svg.appendChild(el('text',{x:f(outside?x(value)+6:x(value)-6),y:f(center+3.5),'text-anchor':outside?'start':'end','font-size':10,fill:outside?'#5d7a6e':'#ffffff'},text));
    }
  });
  return {svg:svg,tip:tip};
}

/* ---------- 饼图 / 环形图 ---------- */
function arcPath(cx,cy,outer,inner,start,end){
  const large=end-start>Math.PI?1:0;
  const x0=f(cx+outer*Math.cos(start)),y0=f(cy+outer*Math.sin(start));
  const x1=f(cx+outer*Math.cos(end)),y1=f(cy+outer*Math.sin(end));
  if(inner<=0)return 'M '+f(cx)+' '+f(cy)+' L '+x0+' '+y0+' A '+f(outer)+' '+f(outer)+' 0 '+large+' 1 '+x1+' '+y1+' Z';
  const ix1=f(cx+inner*Math.cos(end)),iy1=f(cy+inner*Math.sin(end));
  const ix0=f(cx+inner*Math.cos(start)),iy0=f(cy+inner*Math.sin(start));
  return 'M '+x0+' '+y0+' A '+f(outer)+' '+f(outer)+' 0 '+large+' 1 '+x1+' '+y1+' L '+ix1+' '+iy1+' A '+f(inner)+' '+f(inner)+' 0 '+large+' 0 '+ix0+' '+iy0+' Z';
}
function foldSlices(items){
  if(items.length<=MAX_SLICES)return items.slice(0);
  const sorted=items.slice(0).sort((a,b)=>num(b.value)-num(a.value));
  const head=sorted.slice(0,MAX_SLICES-1),tail=sorted.slice(MAX_SLICES-1);
  head.push({key:'__other__',label:'其他（'+tail.length+' 项）',value:tail.reduce((sum,item)=>sum+num(item.value),0)});
  return head;
}
function shareText(item,total){
  const share=item.share===null||item.share===undefined?num(item.value)/total:num(item.share);
  return Math.round(share*100)+'%';
}
function pie(container,spec){
  spec=spec||{};
  const node=resolve(container);
  const source=(Array.isArray(spec.items)?spec.items:[]).filter(item=>item&&num(item.value)>0);
  const unit=['count','percent','decimal','yuan'].includes(spec.unit)?spec.unit:'money';
  remember(node,spec);
  return mount(container,spec,width=>{
    const height=num(spec.height)||(width<470?250:280);
    if(!source.length)return {svg:emptySvg(width,height,spec,EMPTY_TEXT,'没有可绘制的分类')};
    const items=foldSlices(source);
    const total=items.reduce((sum,item)=>sum+num(item.value),0);
    if(total<=0)return {svg:emptySvg(width,height,spec,EMPTY_TEXT,'所有数值均为 0')};
    const size=Math.min(width,height);
    const cx=f(width/2),cy=f(size/2-4),outer=Math.max(42,Math.min(104,size/2-26)),inner=f(outer*0.56);
    const svg=baseSvg(width,height,spec);
    const wedges=[];
    let angle=-Math.PI/2;
    items.forEach((item,index)=>{
      const span=Math.PI*2*num(item.value)/total;
      const start=angle,end=Math.min(angle+span,angle+Math.PI*2-0.0001);
      angle+=span;
      const wedge=el('path',{d:arcPath(cx,cy,outer,inner,start,end),fill:COLORS[index%COLORS.length],stroke:'#ffffff','stroke-width':1.5});
      wedge.appendChild(el('title',null,String(item.label||'')+'：'+valueText(item.value,unit)+' · '+shareText(item,total)));
      svg.appendChild(wedge);
      wedges.push(wedge);
    });
    const totalText=valueText(total,unit);
    const center=textWidth(totalText,17)<=inner*1.9?totalText:compactValue(total,unit);
    svg.appendChild(el('text',{x:cx,y:f(cy+1),'text-anchor':'middle','font-size':17,'font-weight':650,fill:INK},center));
    svg.appendChild(el('text',{x:cx,y:f(cy+19),'text-anchor':'middle','font-size':10,fill:MUTED},'合计'));
    const tip=tipNode();
    wedges.forEach((wedge,index)=>{
      const item=items[index],label=String(item.label||'');
      const highlight=()=>{for(const other of wedges)other.setAttribute('opacity',other===wedge?'1':'0.4');};
      const restore=()=>{for(const other of wedges)other.setAttribute('opacity','1');tipHide(tip);};
      const move=event=>{
        const point=pointerLocal(event,svg,node,width);
        tipRows(tip,label,[{color:COLORS[index%COLORS.length],label:valueText(item.value,unit),value:shareText(item,total)}]);
        tipPlace(tip,point.tipX,point.tipY,width);
      };
      wedge.addEventListener('pointerenter',highlight);
      wedge.addEventListener('pointermove',event=>{highlight();move(event);});
      wedge.addEventListener('pointerdown',event=>{highlight();move(event);});
      wedge.addEventListener('pointerleave',restore);
      wedge.addEventListener('pointercancel',restore);
    });
    const legend=legendBox(items.map((item,index)=>legendRow(COLORS[index%COLORS.length],String(item.label||''),valueText(item.value,unit)+' · '+shareText(item,total))));
    return {svg:svg,tip:tip,extra:[legend]};
  });
}/* ---------- 导出：SVG 文本与 2 倍图 PNG ---------- */
function resolveSvg(target){
  let node=target;
  if(typeof node==='string')node=document.querySelector(node);
  if(!node)return null;
  if(node.tagName&&String(node.tagName).toLowerCase()==='svg')return node;
  if(typeof node.querySelector==='function')return node.querySelector('svg');
  return null;
}
function svgTitleText(svg){
  for(const child of kids(svg)){
    const name=String(child.nodeName||child.tagName||'').toLowerCase();
    if(name==='title')return child.textContent||'';
  }
  return '';
}
function exportMeta(target){
  const svg=resolveSvg(target);
  if(!svg)return null;
  const node=typeof target==='string'?document.querySelector(target):target;
  const meta=(node&&node.__chartMeta)||svg.__chartMeta||null;
  return {svg:svg,title:String(meta&&meta.title?meta.title:svgTitleText(svg)||'')};
}
function svgBox(svg){
  const viewBox=svg.getAttribute?String(svg.getAttribute('viewBox')||''):'';
  const parts=viewBox.split(/[\s,]+/).map(num);
  if(parts.length===4&&parts[2]>0&&parts[3]>0)return {width:Math.round(parts[2]),height:Math.round(parts[3])};
  const width=svg.getAttribute?num(svg.getAttribute('width')):0,height=svg.getAttribute?num(svg.getAttribute('height')):0;
  return {width:Math.round(width||720),height:Math.round(height||300)};
}
function stripUi(node){
  for(const child of kids(node)){
    if(child.getAttribute&&child.getAttribute('data-chart-ui'))node.removeChild(child);
    else stripUi(child);
  }
}
function cloneForExport(svg,title){
  const clone=svg.cloneNode(true);
  stripUi(clone);
  const box=svgBox(svg),head=title?34:0,height=box.height+head;
  clone.setAttribute('xmlns',SVG_NS);
  clone.setAttribute('width',String(box.width));
  clone.setAttribute('height',String(height));
  clone.setAttribute('viewBox','0 0 '+box.width+' '+height);
  css(clone,'display:block;width:'+box.width+'px;height:'+height+'px');
  const group=el('g',{transform:'translate(0 '+head+')'});
  while(clone.firstChild)group.appendChild(clone.firstChild);
  if(title){
    clone.appendChild(el('text',{x:16,y:22,'font-size':14,'font-weight':650,fill:INK,'font-family':FONT},title));
    clone.appendChild(el('line',{x1:16,x2:box.width-16,y1:29,y2:29,stroke:GRID,'stroke-width':1}));
  }
  clone.appendChild(group);
  return {svg:clone,width:box.width,height:height};
}
function serialize(svg,title){
  const built=cloneForExport(svg,title);
  let text='';
  if(typeof XMLSerializer==='function')text=new XMLSerializer().serializeToString(built.svg);
  else if(typeof built.svg.outerHTML==='string')text=built.svg.outerHTML;
  else throw new Error('当前环境无法序列化 SVG。');
  if(text.indexOf('xmlns=')<0)text=text.replace(/<svg/,'<svg xmlns="'+SVG_NS+'"');
  return {text:text,width:built.width,height:built.height};
}
function safeName(name){
  const text=String(name||'图表').replace(/[\\/:*?"<>|\u0000-\u001f]+/g,'_').replace(/\s+/g,' ').trim();
  return text.slice(0,110)||'chart';
}
function fileName(name,extension){
  const base=safeName(name),lower=base.toLowerCase();
  return lower.indexOf(extension)===lower.length-extension.length?base:base+extension;
}
function download(href,name){
  const link=document.createElement('a');
  link.setAttribute('href',href);
  link.setAttribute('download',name);
  link.setAttribute('rel','noopener');
  const parent=document.body||document.documentElement;
  if(parent&&typeof parent.appendChild==='function')parent.appendChild(link);
  if(typeof link.click==='function')link.click();
  if(link.parentNode&&typeof link.parentNode.removeChild==='function')link.parentNode.removeChild(link);
  else if(typeof link.remove==='function')link.remove();
  return href;
}
function textHref(text){
  try{
    if(typeof Blob==='function'&&global.URL&&typeof global.URL.createObjectURL==='function')return global.URL.createObjectURL(new Blob([text],{type:'image/svg+xml;charset=utf-8'}));
  }catch(error){}
  return 'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(text);
}
function exportSvg(target,filename){
  const meta=exportMeta(target);
  if(!meta)throw new Error('没有可导出的图表。');
  const built=serialize(meta.svg,meta.title);
  download(textHref(built.text),fileName(filename||meta.title||'chart','.svg'));
  return built.text;
}
function rasterize(markup,width,height,scale){
  return new Promise((resolve,reject)=>{
    const canvas=document.createElement('canvas');
    if(!canvas||typeof canvas.getContext!=='function'){reject(new Error('当前浏览器不支持画布导出，请改用“导出 SVG”。'));return;}
    const context=canvas.getContext('2d');
    if(!context){reject(new Error('当前浏览器不支持画布导出，请改用“导出 SVG”。'));return;}
    canvas.width=Math.max(1,Math.round(width*scale));
    canvas.height=Math.max(1,Math.round(height*scale));
    const image=new global.Image();
    image.onload=()=>{
      try{
        if(typeof context.setTransform==='function')context.setTransform(1,0,0,1,0,0);
        context.fillStyle='#ffffff';
        context.fillRect(0,0,canvas.width,canvas.height);
        if(typeof context.setTransform==='function')context.setTransform(scale,0,0,scale,0,0);
        context.drawImage(image,0,0,width,height);
        const url=canvas.toDataURL('image/png');
        if(!url||url.indexOf('data:image/png')!==0)throw new Error('画布未返回 PNG 数据。');
        resolve(url);
      }catch(error){reject(error);}
    };
    image.onerror=()=>reject(new Error('图表光栅化失败，请改用“导出 SVG”。'));
    image.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(markup);
  });
}
function exportPng(target,filename){
  const meta=exportMeta(target);
  if(!meta)return Promise.reject(new Error('没有可导出的图表。'));
  const built=serialize(meta.svg,meta.title);
  const scale=Math.max(1,Math.min(2,4096/Math.max(built.width,built.height)));
  return rasterize(built.text,built.width,built.height,scale).then(url=>{
    download(url,fileName(filename||meta.title||'chart','.png'));
    return url;
  });
}
function dispose(container){const node=resolve(container),current=node&&mounted.get(node);if(current?.observer)current.observer.disconnect();if(node)mounted.delete(node);}
global.Charts={dispose:dispose,line:line,bar:bar,pie:pie,exportSvg:exportSvg,exportPng:exportPng,money:money,count:count,
  formatValue:valueText,compact:compactValue,colors:COLORS.slice(0),
  svgText:target=>{const meta=exportMeta(target);return meta?serialize(meta.svg,meta.title).text:'';}};
})(typeof window!=='undefined'?window:globalThis);
