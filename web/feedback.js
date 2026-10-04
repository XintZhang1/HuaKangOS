'use strict';
// Drafts and unresolved request identifiers live only in this login/store's memory.
const FEEDBACK_MODULES={'business-assistant':'业务助手',work:'我的工作',sales:'整车销售',inventory:'整车仓库',repair:'维修服务',materials:'物资管理',finance:'财务管理',customers:'客户管理',members:'会员服务',system:'系统管理',other:'其他页面'};
const FEEDBACK_CATEGORIES={bug:'使用问题',improvement:'改进意见',feature:'功能建议'};
const FEEDBACK_CONSENT='意见将交给 DeepSeek 分析，并发送给 Cutie 审阅；请勿填写客户隐私或密码';
function newFeedbackState(){return {draft:{title:'',description:'',category:'improvement',route:'other',consent_analysis:false},requestId:null,pending:null,busy:false,uncertain:false,message:'',error:'',receipts:[],receiptError:'',receiptRevision:0};}
let feedbackState=newFeedbackState();
function clearFeedbackSession(){feedbackState=newFeedbackState();}
function feedbackContext(){return `${state.user?.id||''}:${state.store||''}:${storeContextVersion}`;}
function feedbackCurrent(current,context){return current===feedbackState&&context===feedbackContext()&&!!state.user;}
function feedbackOptions(values,selected){return Object.entries(values).map(([value,label])=>`<option value="${E(value)}" ${value===selected?'selected':''}>${E(label)}</option>`).join('');}
function feedbackReceipts(current){
 return (current.receiptError?`<p class="notice error">${E(current.receiptError)}</p>`:'')+
  table(['意见','提交时间','回执'],current.receipts.map(row=>[`<div class="wrap">${E(row.title)}</div>`,E(time(row.created_at)),pill('info','已收到')]))+
  '<p class="fieldhelp">显示本人在当前门店最近 20 条提交。收到意见不表示问题已经修复。</p>';
}
async function feedbackPage(){
 if(state.store==='all')return heading('意见反馈')+'<p class="notice">请先选择一家门店，再提交或查看意见。</p>';
 const current=feedbackState,context=feedbackContext(),revision=current.receiptRevision;
 try{const result=await api('/api/feedback');if(feedbackCurrent(current,context)&&revision===current.receiptRevision){current.receipts=result.items;current.receiptError='';}}
 catch(error){if(feedbackCurrent(current,context))current.receiptError=error.message;}
 const draft=current.draft,locked=current.busy||current.uncertain;
 return heading('意见反馈','写下遇到的问题、操作步骤或希望改进的地方。')+storeNotice()+
  panel('提交意见',`<form id="feedback-form" class="stack" aria-busy="${current.busy}">
   <div class="formgrid">
    <label>意见类型<select name="category" ${locked?'disabled':''}>${feedbackOptions(FEEDBACK_CATEGORIES,draft.category)}</select></label>
    <label>相关页面<select name="route" ${locked?'disabled':''}>${feedbackOptions(FEEDBACK_MODULES,draft.route)}</select></label>
    <label class="wide">标题<input name="title" required minlength="3" maxlength="160" autocomplete="off" value="${E(draft.title)}" ${locked?'disabled':''}></label>
    <label class="wide">具体说明<textarea name="description" required minlength="10" maxlength="12000" rows="6" autocomplete="off" ${locked?'disabled':''}>${E(draft.description)}</textarea></label>
   </div>
   <label><input type="checkbox" name="consent_analysis" required ${draft.consent_analysis?'checked':''} ${locked?'disabled':''}>我同意：${E(FEEDBACK_CONSENT)}</label>
   <p class="fieldhelp">仅发送本次填写的意见、所选页面分类和提交归属，不附带原单、客户档案或聊天记录。</p>
   <div class="formerror" role="alert">${E(current.error)}</div><p data-feedback-message role="status">${E(current.message)}</p>
   <div class="row"><button type="submit" class="primary" ${current.busy?'disabled':''}>${current.busy?'正在提交…':current.uncertain?'核对本次提交':'提交意见'}</button></div>
  </form>`)+panel('本人提交回执',`<div id="feedback-receipts">${feedbackReceipts(current)}</div>`);
}
function readFeedbackDraft(form,current){
 if(current.busy||current.uncertain)return;
 current.draft={title:form.elements.title.value,description:form.elements.description.value,
  category:form.elements.category.value,route:form.elements.route.value,consent_analysis:form.elements.consent_analysis.checked};
}
function feedbackFormState(form,current){
 const locked=current.busy||current.uncertain;
 for(const field of form.querySelectorAll('input,select,textarea'))field.disabled=locked;
 const submit=form.querySelector('[type="submit"]');submit.disabled=current.busy;
 submit.textContent=current.busy?'正在提交…':current.uncertain?'核对本次提交':'提交意见';
 form.setAttribute('aria-busy',String(current.busy));
 form.querySelector('.formerror').textContent=current.error;
 form.querySelector('[data-feedback-message]').textContent=current.message;
}
function updateFeedbackView(current,reset=false){
 if(current!==feedbackState||state.route!=='feedback')return;
 const form=document.getElementById('feedback-form');
 if(form){
  if(reset){form.elements.title.value=current.draft.title;form.elements.description.value=current.draft.description;
   form.elements.category.value=current.draft.category;form.elements.route.value=current.draft.route;form.elements.consent_analysis.checked=current.draft.consent_analysis;}
  feedbackFormState(form,current);
 }
 const target=document.getElementById('feedback-receipts');if(target)target.innerHTML=feedbackReceipts(current);
}
function bindFeedbackPage(){
 const form=document.getElementById('feedback-form');if(!form)return;
 const current=feedbackState,context=feedbackContext();
 const remember=()=>{if(feedbackCurrent(current,context))readFeedbackDraft(form,current);};
 form.addEventListener('input',remember);form.addEventListener('change',remember);
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(!feedbackCurrent(current,context)||current.busy)return;
  readFeedbackDraft(form,current);
  if(!current.pending){
   if(!form.reportValidity())return;
   current.requestId=current.requestId||requestKey();
   current.pending={...current.draft,title:current.draft.title.trim(),description:current.draft.description.trim(),request_id:current.requestId};
  }
  const submitted=current.pending;let resetView=false;current.busy=true;current.error='';current.message='';feedbackFormState(form,current);
  try{
   const receipt=await api('/api/feedback',{method:'POST',body:submitted});
   if(!feedbackCurrent(current,context))return;
   // A successful collection receipt is final even if later list refresh fails.
   current.receiptRevision++;current.receiptError='';
   current.receipts=[{...receipt,title:submitted.title},...current.receipts.filter(row=>row.id!==receipt.id)].slice(0,20);
   current.draft=newFeedbackState().draft;current.requestId=null;current.pending=null;current.uncertain=false;
   current.message=receipt.duplicate?'已核对：这条意见已收到。':'意见已收到，谢谢反馈。';
   resetView=true;
  }catch(error){
   if(!feedbackCurrent(current,context))return;
   // A response failure or server error may follow a committed insert. Freeze
   // the original payload and request id until an explicit same-id replay.
   current.uncertain=!!error.unknownResult||!error.status||error.status>=500||error.status===409;
   if(!current.uncertain)current.pending=null;
   current.error=current.uncertain?'尚未确认本次提交结果，填写内容和请求编号已保留。点击“核对本次提交”查询同一次提交，勿另建重复意见。':error.message;
  }finally{
   if(feedbackCurrent(current,context)){current.busy=false;updateFeedbackView(current,resetView);}
  }
 });
}
// This entry never closes an unfinished native business form.
document.addEventListener('click',event=>{
 const link=event.target.closest('a[href="#feedback"]');if(!link)return;
 if(document.getElementById('modal')?.open){event.preventDefault();event.stopImmediatePropagation();toast('请先完成或取消当前业务表单，再打开意见反馈。',true);}
},true);
window.addEventListener('beforeunload',event=>{
 if(feedbackState.draft.title||feedbackState.draft.description||feedbackState.pending){event.preventDefault();event.returnValue='';}
});
