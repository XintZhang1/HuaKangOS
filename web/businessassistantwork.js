'use strict';
// Native reads only. No model call, no automatic confirmation, no browser storage.
function businessAssistantWorkHTML(){
 const current=businessAssistantState,data=current.workboard,plan=data?.plan;
 if(!current.session?.work_plans?.length&&!current.workError)return '';
 const available=data?.plans||current.session?.work_plans||[];
 const selector=available.length>1?`<label class="ba-work-select">办理进度<select data-baw-plan aria-label="选择办事计划">${available.map(p=>`<option value="${E(p.id)}" ${p.id===(plan?.id||current.workPlanId)?'selected':''}>${E(p.goal)}</option>`).join('')}</select></label>`:'';
 const recordMap=new Map((data?.cases||[]).map(r=>[r.case_id,r]));
 const stepHTML=step=>{
  const record=recordMap.get(step.case_id),route=businessAssistantRoute(step.route),guide=businessAssistantRoute(step.workflow_route);
  let handoff='';
  if(record?.error)handoff=`<p class="ba-work-error">${E(record.error)}</p>`;
  else if(record){
   const my=(record.mine||[]).map(t=>t.title||'原单待办');
   const others=(record.others||[]).map(t=>`${t.assignee_name||'接手同事'}：${t.title||'原单待办'}`);
   handoff=`<div class="ba-work-handoff"><p>原单进度：${E(record.state_label||record.state||'请核对')}</p>${my.length?`<p><strong>现在轮到你：</strong>${E(my.join('；'))}</p>`:''}${others.length?`<p>同事接手：${E(others.join('；'))}</p>`:''}${record.unassigned?.length?'<p>还有待办尚未分派，请由原单负责人处理。</p>':''}${!my.length&&!others.length&&!record.unassigned?.length?'<p>原单当前没有未完成待办；外部手续仍以实际记录为准。</p>':''}</div>`;
  }else if(step.case_id)handoff='<p>原单即时进度尚未载入，请打开原单核对。</p>';
  const missing=step.missing?.length?`<p>还需填写：${E(step.missing.join('、'))}</p>`:'';
  const wait=step.wait_for&&step.status!=='step_completed'?`<p>计划中待满足：${E(step.wait_for)}</p>`:'';
  return `<li class="ba-work-step" data-work-status="${E(step.status)}"><div class="spread"><strong>${E(step.title)}</strong><span>${E(step.status_label)}</span></div>${missing}${wait}${handoff}<div class="row">${step.proposal_id&&['awaiting_confirmation','needs_input','failed','uncertain','expired'].includes(step.status)?`<button type="button" data-baw-card="${E(step.proposal_id)}">${step.status==='needs_input'?'补充信息':'查看内容'}</button>`:''}${route?`<a class="ba-record-link" href="#${E(route)}">查看单据</a>`:guide?`<a class="ba-record-link" href="#${E(guide)}">操作指引</a>`:''}</div></li>`;
 };
 const steps=plan?.steps||[],visible=steps.slice(0,2),rest=steps.slice(2);
 return `<section class="ba-workboard" aria-label="办理进度"><div class="spread"><strong>办理进度</strong><button type="button" data-baw-action="refresh" ${current.workLoading||current.busy?'disabled':''}>${current.workLoading?'正在核对…':'刷新进度'}</button></div>${selector}${plan?`<h3>${E(plan.goal)}</h3><ol>${visible.map(stepHTML).join('')}</ol>${rest.length?`<details><summary>其余 ${rest.length} 个步骤</summary><ol start="3">${rest.map(stepHTML).join('')}</ol></details>`:''}`:'<p>正在读取计划与原单状态。</p>'}${current.workError?`<p role="alert" class="ba-work-error">${E(current.workError)} 已有办理结果不变，请不要重复提交。</p>`:''}${data?.next_case_page?'<p>部分原单未在本页刷新；请打开对应原单查看实时进度。</p>':''}</section>`;
}
function paintBusinessAssistantWork(){
 if(state.route!=='business-assistant'||businessAssistantState.context!==businessAssistantContext())return;
 const host=document.getElementById('business-assistant-workboard');
 if(host)host.innerHTML=businessAssistantWorkHTML();
}
async function businessAssistantRefreshWork(current=businessAssistantState,generation=current.generation,planId=null){
 if(!current.session||!businessAssistantAlive(current,generation))return;
 if(!current.session.work_plans?.length){current.workboard=null;current.workError='';paintBusinessAssistantWork();return;}
 const sid=current.session.id,serial=(current.workSerial||0)+1;
 current.workSerial=serial;current.workLoading=true;current.workError='';
 if(planId)current.workPlanId=planId;
 const selected=current.workPlanId;paintBusinessAssistantWork();
 try{
  const path='/sessions/'+encodeURIComponent(sid)+'/work-status'+(selected?'?plan_id='+encodeURIComponent(selected):'');
  const data=await businessAssistantRequest(path);
  if(!businessAssistantAlive(current,generation)||current.session?.id!==sid||serial!==current.workSerial)return;
  current.workboard=data;current.workPlanId=data.plan?.id||null;
 }catch(error){
  if(businessAssistantAlive(current,generation)&&current.session?.id===sid&&serial===current.workSerial)
   current.workError='交接进度暂未读取成功，请刷新或打开原单核对。';
 }finally{
  if(businessAssistantAlive(current,generation)&&current.session?.id===sid&&serial===current.workSerial){current.workLoading=false;paintBusinessAssistantWork();}
 }
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-baw-action],[data-baw-card]');
 if(!button||button.disabled||state.route!=='business-assistant')return;
 const current=businessAssistantState;if(current.busy)return;
 if(button.dataset.bawAction==='refresh'){await businessAssistantRefreshWork();return;}
 const card=current.session?.proposals?.find(p=>String(p.id)===String(button.dataset.bawCard));
 if(!card){toast('这张历史卡已不在当前窗口，请通过原单核对结果。',true);return;}
 current.queueFilter=businessAssistantBucket(card);current.activeCardId=card.id;current.mobilePane='cards';
 paintBusinessAssistantCards();document.querySelector('#business-assistant-cards h3')?.focus({preventScroll:true});
});
document.addEventListener('change',event=>{
 if(event.target.matches('[data-baw-plan]')&&state.route==='business-assistant'&&!businessAssistantState.busy)
  void businessAssistantRefreshWork(businessAssistantState,businessAssistantState.generation,event.target.value);
});
