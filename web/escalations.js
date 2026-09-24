'use strict';
// 评审申请：把被岗位权限挡住的事交本店店长或集团管理员。这里只提交与查看请求，
// 不改变任何权限、也不执行业务动作——上级在原业务页面本人办理，系统只留痕。
const ESC_STATUS={open:'待处理',claimed:'已接手',done:'已办理',rejected:'已驳回',cancelled:'已撤回'};
const ESC_CATEGORY={authority:'岗位权限不足',amount:'金额或额度超出'};
function escRole(){return state.user?.account_role||state.user?.role;}
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
async function escalationsPage(){
 const scope=state.escScope||'mine';
 const data=await api('/api/escalations?scope='+scope);
 state.rows=data.items;state.escRows=data.items;
 const rows=data.items.map(row=>[`<strong class="wrap">${E(row.subject)}</strong>`,E(row.case_reference||'—'),
  E(row.category_label),E(row.target_label),escStatusPill(row.status),time(row.created_at),`<div class="row">${escActions(row)}</div>`]);
 const tabs=(escReviewer()?b('esctab','待我评审',`data-scope="to_review" ${scope==='to_review'?'disabled':''}`):'')
  +b('esctab','我提交的',`data-scope="mine" ${scope==='mine'?'disabled':''}`)+b('escnew','提交评审申请','','primary');
 const hint=scope==='to_review'
  ?'这些申请来自本店同事：请在本人的原业务页面办理，或在这里写明驳回原因；办理结果只会记到这条申请上。'
  :'被岗位权限或额度挡住时在这里提交；业务规则明确不允许的事（质检不合格、未收款出库等）不能通过评审绕过。';
 return heading('评审申请',hint,tabs)+storeNotice()
  +`<section class="panel">${table(['事项','原单或对象','类别','收件人','状态','提交时间','操作'],rows)}</section>`;
}
function escDialogRow(id){return (state.escRows||[]).find(row=>String(row.id)===String(id));}
async function escNewDialog(){
 await formDialog('提交评审申请',[
  F('subject','要办的事'),F('case_reference','原单号或对象'),
  F('blocked_message','系统提示原文','textarea'),F('reason_category','被挡住的原因','select',true,['authority','amount','rule'])],{},
  values=>api('/api/escalations',{method:'POST',body:values}),
  {notice:'原因请选：岗位权限不足 / 金额或额度超出 / 业务规则不允许。选“业务规则不允许”的系统会直接拒绝——规则不能靠评审绕过。',
   submit:'提交申请'});
}
function escDetail(row){
 const events=(row.events||[]).map(event=>`<li>${E(event.action)} · ${E(time(event.created_at))}${event.note?' · '+E(event.note):''}</li>`).join('');
 modal('评审申请 #'+row.id,`<div class="stack"><p><strong>${E(row.subject)}</strong></p>
  ${facts({'原单或对象':row.case_reference||'—','类别':row.category_label,'收件人':row.target_label,'状态':row.status_label,
           '申请人岗位':row.requester_role_label,'系统提示原文':row.blocked_message,'处理结果':row.decision_note||'—'})}
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
  else if(action==='escnew')await escNewDialog();
  else if(action==='escview'){const row=escDialogRow(el.dataset.id);if(row)escDetail(row);}
  else await escAction(el.dataset.id,action==='escclaim'?'claim':action==='escdone'?'done':action==='escreject'?'reject':'cancel');
 }catch(error){toast(error.message,true);}
});
