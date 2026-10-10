'use strict';
// Monthly targets are a manual manager action. The server rechecks the active
// store, role, predecessor version and request id for every submission.
function brTargetButton(action,label,id){return `<button type="button" data-br-target="${E(action)}"${id==null?'':` data-id="${E(id)}"`}>${E(label)}</button>`;}
function brTargetAmount(value,isCount=false){return value==='/'?'/（不适用）':value==null?'未下达':isCount?String(value)+' 台':money(value)+' 元';}
function brTargetInput(value,isCount=false){return value==='/'?'/':value==null?'':isCount?String(value):brInputAmount(value);}
function brTargetValue(value,label,isCount=false){
 const text=String(value??'').trim();if(text==='')return null;if(text==='/')return '/';
 if(isCount){if(!/^\d+$/.test(text)||!Number.isSafeInteger(Number(text))||Number(text)>999999999)throw new Error(label+'请填写非负整数、/ 或留空。');return Number(text);}
 return moneyFen(text,{label,allowZero:true});
}
async function brMonthlyTargets(){
 const month=brState.targetsMonth||brState.reportMonth||day().slice(0,7),context=brContext(),epoch=renderId;
 brState.targetsMonth=month;
 const data=await api(BR_API+'/monthly-targets?'+new URLSearchParams({month,include_history:String(!!brState.targetsHistory)}));
 if(context!==brContext()||epoch!==renderId)return '';
 brState.monthlyTargets={...data,context};
 const controls=`<form data-br-target-filter class="br-filter"><label>目标月份<input type="month" name="month" value="${E(month)}" required></label><label>记录范围<select name="history"><option value="current" ${!brState.targetsHistory?'selected':''}>当前目标</option><option value="all" ${brState.targetsHistory?'selected':''}>包含修订历史</option></select></label><button type="submit" class="primary">查看目标</button></form>`;
 const rows=data.items.map(row=>[E(row.month),E(row.store),E(row.brand||'未分品牌'),E(row.series),E(brTargetAmount(row.sales_units,true)),E(brTargetAmount(row.mechanical_cents)),E(brTargetAmount(row.accident_cents)),E(brTargetAmount(row.after_sales_cents)),E(row.issued_by),E(row.is_current?'当前目标':'历史版本'),E(row.note||'—'),row.can_correct?brTargetButton('revise','修订目标',row.id):'—']);
 return heading('月度目标','管理者按当前门店、月份、品牌和系列下达目标，内勤业务实绩另行汇总。',brLink('records-dashboard/monthly','返回月报统计')+(data.can_write?brTargetButton('new','下达月度目标'):''))+storeNotice()+controls+`<p class="notice">${E(data.notice)}</p>`+(!data.can_write&&state.store==='all'?'<p class="br-caption">当前为已授权门店汇总，只可查看；需要下达时请先切换到获授权的具体门店。</p>':'')+`<section class="panel">${table(['月份','门店','品牌','系列','实销台数目标','机电产值目标','事故产值目标','售后合计目标','下达人','状态','说明','操作'],rows)}</section>`;
}
async function brIssueMonthlyTarget(id){
 const current=brState.monthlyTargets;if(!current||current.context!==brContext()||!current.can_write)throw new Error('请先在获授权的具体门店打开月度目标。');
 const prior=id==null?null:current.items.find(row=>row.id===id&&row.can_correct);
 if(id!=null&&!prior)throw new Error('请刷新后选择当前目标版本。');
 const fields=[F('month','目标月份','month'),F('brand','品牌（不区分品牌可留空）','text',false),F('series','系列'),
  F('sales_units','实销台数目标（台）','text',false),F('mechanical','机电产值目标（元）','text',false),
  F('accident','事故产值目标（元）','text',false),F('after_sales','售后合计目标（元）','text',false),F('note','下达 / 修订说明','textarea',false)];
 const values={month:prior?.month||current.month,brand:prior?.brand||'',series:prior?.series||'',
  sales_units:brTargetInput(prior?.sales_units,true),mechanical:brTargetInput(prior?.mechanical_cents),
  accident:brTargetInput(prior?.accident_cents),after_sales:brTargetInput(prior?.after_sales_cents),note:prior?.note||''};
 const dialog=await brForm(prior?'修订月度目标':'下达月度目标',[{title:'按门店、月份、品牌和系列填写',fields}],values,(v,request_id)=>api(BR_API+'/monthly-targets',{method:'POST',body:{request_id,month:v.month,brand:v.brand,series:v.series,
  sales_units:brTargetValue(v.sales_units,'实销台数目标',true),mechanical_cents:brTargetValue(v.mechanical,'机电产值目标'),
  accident_cents:brTargetValue(v.accident,'事故产值目标'),after_sales_cents:brTargetValue(v.after_sales,'售后合计目标'),note:v.note,
  ...(prior?{supersedes_id:prior.id,supersedes_version:prior.version}:{})}}).then(result=>{brState.targetsMonth=v.month;return result;}),{draftKey:prior?'monthly-target-'+prior.id+'-'+prior.version:'monthly-target-new-'+current.month,submit:prior?'确认修订目标':'确认下达目标',notice:'目标按当前门店保存。空白表示未知，/ 表示不适用；只有明确的零目标才填 0。金额为元，最多两位小数。售后合计按下达值填写，未知分项不按零相加。保存即进入月报，修订保留旧版本。'});
 dialog.querySelector('[name="month"]').type='month';
 if(prior)for(const name of ['month','brand','series'])dialog.querySelector('[name="'+name+'"]').readOnly=true;
}
document.addEventListener('submit',async event=>{
 const form=event.target.closest('[data-br-target-filter]');if(!form)return;event.preventDefault();
 if(state.storeSwitch)return;
 brState.targetsMonth=form.elements.month.value;brState.targetsHistory=form.elements.history.value==='all';
 try{await render();}catch(error){toast(error.message,true);}
});
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-br-target]');if(!button||button.disabled||state.storeSwitch)return;
 button.disabled=true;
 try{await brIssueMonthlyTarget(button.dataset.brTarget==='revise'?Number(button.dataset.id):null);}
 catch(error){toast(error.message,true);}finally{if(button.isConnected)button.disabled=false;}
});
