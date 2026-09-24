'use strict';
// 评审申请：把被岗位权限挡住的事交本店店长或集团管理员。这里只提交与查看请求，
// 不改变任何权限、也不执行业务动作——上级在原业务页面本人办理，系统只留痕。
// 提交时必须选择"系统自己记下的被挡记录"：类别由服务端判定，业务规则不允许的事项无法绕过。
const ESC_STATUS={open:'待处理',claimed:'已接手',done:'已办理',rejected:'已驳回',cancelled:'已撤回'};
const ESC_CATEGORY={authority:'岗位权限不足',amount:'金额或额度超出',rule:'业务规则不允许'};
function escRole(){return state.user?.role||state.user?.account_role;}
function escReviewer(){return ['manager','admin'].includes(escRole());}
function escStatusPill(status){
 return pill({open:'pending',claimed:'submitted',done:'done',rejected:'cancelled',cancelled:'cancelled'}[status]||'info',ESC_STATUS[status]||status);
}
function escActions(row){
 const mine=String(row.requester_id)===String(state.user.id),reviewer=escReviewer()&&!mine;
 if(['open','claimed'].includes(row.status)){
  if(mine)return b('esccancel','撤回',`data-id="${row.id}"`)+b('escview','查看',`data-id="${row.id}"`);
  if(reviewer&&row.status==='open')return b('escclaim','接手',`data-id="${row.id}"`)+b('escview','查看',`data-id="${row.id}"`);
  if(reviewer)return b('escdone','已办理',`data-id="${row.id}"`)+b('escreject','驳回',`data-id="${row.id}"`)+b('escview','查看',`data-id="${row.id}"`);
 }
 return b('escview','查看',`data-id="${row.id}"`);
}
function escRefusalRows(items){
 return items.map(row=>[`<div class="wrap"><strong>${E(row.operation_id)}</strong><div class="cellsecond">${E(row.category_label)}</div></div>`,
  `<div class="wrap">${E((row.message||'').slice(0,80))}</div>`,E(time(row.created_at)),
  b('escnew','用它提交评审',`data-refusal="${row.id}"`,'primary')]);
}
async function escalationsPage(){
 const scope=state.escScope||'mine';
 const data=await api('/api/escalations?scope='+scope);
 state.rows=data.items;state.escRows=data.items;
 // Narrow screens: the subject keeps a readable min-width (block .wrap) and the table scrolls.
 const rows=data.items.map(row=>[`<div class="wrap"><strong>${E(row.subject)}</strong><div class="cellsecond">${E(row.case_reference||'—')} · ${E(row.category_label)}</div></div>`,
  E(row.target_label),`${escStatusPill(row.status)}<div class="cellsecond">${E(time(row.created_at))}</div>`,
  `<div class="row">${escActions(row)}</div>`]);
 const tabs=(escReviewer()?b('esctab','待我评审',`data-scope="to_review" ${scope==='to_review'?'disabled':''}`):'')
  +b('esctab','我提交的',`data-scope="mine" ${scope==='mine'?'disabled':''}`)+b('escnew','提交评审申请','','primary');
 const hint=scope==='to_review'
  ?'这些申请来自本店同事：请在本人的原业务页面办理，或在这里写明驳回原因；办理结果只会记到这条申请上。'
  :'被岗位权限或额度挡住时，先按页面提示办理一次；系统挡住你的那一步会出现在下面，选它提交评审。业务规则明确不允许的事不能通过评审绕过。';
 let blocked='';
 if(scope==='mine'){
  const refusals=await api('/api/escalations/refusals');
  state.escRefusals=refusals.items;
  blocked=refusals.items.length
   ?`<section class="panel"><h2>系统刚挡住的这一步</h2><div class="notice">${E(refusals.notice)}</div>${table(['被挡的操作','系统提示','时间','操作'],escRefusalRows(refusals.items))}</section>`
   :`<section class="panel"><div class="notice">目前没有可引用的被挡记录：先按页面提示办理，被系统挡住后这里会出现记录，再回来提交评审。</div></section>`;
 }
 return heading('评审申请',hint,tabs)+storeNotice()+blocked
  +`<section class="panel">${table(['事项','收件人','状态','操作'],rows)}</section>`;
}
function escDialogRow(id){return (state.escRows||[]).find(row=>String(row.id)===String(id));}
async function escNewDialog(refusalId=null){
 const data=await api('/api/escalations/refusals');
 if(!data.items.length){
  modal('提交评审申请',`<div class="stack"><p class="notice">还没有可以引用的被挡记录：请先按页面提示办理一次，被系统挡住后再回来提交。</p></div>`);
  return;
 }
 const chosen=String(refusalId||data.items[0].id);
 const options=data.items.map(row=>`<option value="${row.id}" ${String(row.id)===chosen?'selected':''}>${E(row.operation_id)} · ${E(row.category_label)} · ${E((row.message||'').slice(0,40))}</option>`).join('');
 modal('提交评审申请',`<form><div class="notice">${E(data.notice)}</div><div class="formgrid">
  <label class="wide">被系统挡住的那一步<select name="refusal_id" required>${options}</select></label>
  <label>要办的事<input name="subject" required minlength="5" maxlength="160" placeholder="例如：给这张单批准 5% 折扣"></label>
  <label>原单号或对象<input name="case_reference" maxlength="80" placeholder="例如 XC-R09-01"></label>
  </div><p class="fieldhelp">类别、操作和系统提示由服务端按这条记录填写，不能自己改成"权限不足"。</p>
  <div class="mt15 formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button type="submit" class="primary">提交申请</button></div></form>`,
 async form=>{
  const fd=new FormData(form);
  await api('/api/escalations',{method:'POST',body:{refusal_id:Number(fd.get('refusal_id')),
   subject:String(fd.get('subject')||'').trim(),case_reference:String(fd.get('case_reference')||'').trim()}});
  closeModal();await render();toast('评审申请已提交给上级');
 });
}
function escDetail(row){
 const events=(row.events||[]).map(event=>`<li>${E(event.action)} · ${E(time(event.created_at))}${event.note?' · '+E(event.note):''}</li>`).join('');
 modal('评审申请 #'+row.id,`<div class="stack"><p><strong>${E(row.subject)}</strong></p>
  ${facts({'原单或对象':row.case_reference||'—','类别':row.category_label,'收件人':row.target_label,'状态':row.status_label,
           '申请人岗位':row.requester_role_label,'被挡的操作':row.operation_id||'—','系统提示原文':row.blocked_message,
           '处理结果':row.decision_note||'—'})}
  <h3>处理轨迹</h3><ul>${events}</ul></div>`);
}
async function escAction(id,action){
 const row=escDialogRow(id);if(!row)throw new Error('请刷新后再试。');
 if(action==='claim'){await api(`/api/escalations/${id}/actions/claim`,{method:'POST',body:{version:row.version,note:''}});await render();toast('已接手，请到原业务页面办理');return;}
 if(action==='cancel'){await api(`/api/escalations/${id}/actions/cancel`,{method:'POST',body:{version:row.version,note:''}});await render();toast('已撤回');return;}
 await formDialog(action==='done'?'登记已办理':'驳回申请',[F('note',action==='done'?'办理结果说明':'驳回原因','textarea')],{},
  values=>api(`/api/escalations/${id}/actions/${action}`,{method:'POST',body:{version:row.version,note:values.note}}),
  {notice:action==='done'?'请先在原业务页面本人办理，再把结果写在这里；本页不会代替你办理。':'驳回后申请人会看到原因。',
   submit:action==='done'?'登记已办理':'确认驳回'});
}
document.addEventListener('click',async event=>{
 const el=event.target.closest('[data-act]');if(!el||el.disabled)return;
 const action=el.dataset.act;if(!['esctab','escnew','escview','escclaim','escdone','escreject','esccancel'].includes(action))return;
 try{
  if(action==='esctab'){state.escScope=el.dataset.scope;await render();}
  else if(action==='escnew')await escNewDialog(el.dataset.refusal);
  else if(action==='escview'){const row=escDialogRow(el.dataset.id);if(row)escDetail(row);}
  else await escAction(el.dataset.id,action==='escclaim'?'claim':action==='escdone'?'done':action==='escreject'?'reject':'cancel');
 }catch(error){toast(error.message,true);}
});
