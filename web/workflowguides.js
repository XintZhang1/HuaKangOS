'use strict';
let workflowCatalogue=null,workflowCatalogueLoad=null,workflowAssistantIntent=null;
let workflowSearchState={context:null,query:'',mode:'normal',index:0,results:[],opener:null};
let workflowAIController=null,workflowAIRequestSeq=0,workflowFormIntent=null;
const workflowRecommendationCache=new Map();
async function loadWorkflowGuides(){
 if(workflowCatalogue)return workflowCatalogue;
 if(!workflowCatalogueLoad)workflowCatalogueLoad=fetch('/static/workflow-guides.json',{credentials:'same-origin'}).then(async r=>{if(!r.ok)throw new Error('暂时无法读取操作指引，请重试。');const data=await r.json();if(!Array.isArray(data.workflows)||data.schema_version!==1)throw new Error('操作指引版本不正确，请联系管理员。');workflowCatalogue=typeof uxLabelCatalogue==='function'?uxLabelCatalogue(data):data;return workflowCatalogue;}).finally(()=>{workflowCatalogueLoad=null;});
 return workflowCatalogueLoad;
}
function workflowContext(){return `${storeContextVersion}:${state.user?.id||''}:${state.store||''}`;}
function clearWorkflowContext(){workflowAssistantIntent=null;workflowFormIntent=null;closeWorkflowSearch(false);workflowRecommendationCache.clear();workflowSearchState={context:null,query:'',mode:'normal',index:0,results:[],opener:null};}
function workflowSearchBox(){return '<label class="wf-top-search"><span aria-hidden="true">⌕</span><input type="search" id="workflow-top-search" placeholder="搜索功能或操作" aria-label="搜索功能或操作" autocomplete="off"><kbd>Ctrl K</kbd></label>';}
function cancelWorkflowRecommendation(){workflowAIController?.abort();workflowAIController=null;workflowAIRequestSeq++;}
function closeWorkflowSearch(restore=true){cancelWorkflowRecommendation();const dialog=document.getElementById('workflow-search-dialog');if(dialog){dialog.close();dialog.remove();}if(restore&&workflowSearchState.opener?.isConnected&&workflowSearchState.opener.id!=='workflow-top-search')workflowSearchState.opener.focus();}
async function openWorkflowSearch(query=''){
 if(!state.user||state.storeSwitch)return;
 let dialog=document.getElementById('workflow-search-dialog');if(dialog){dialog.querySelector('input').focus();return;}
 workflowSearchState={context:workflowContext(),query,mode:'normal',index:0,results:[],opener:document.activeElement,aiStatus:'idle',aiItems:[],aiError:''};
 dialog=document.createElement('dialog');dialog.id='workflow-search-dialog';dialog.className='wf-search-dialog';dialog.setAttribute('aria-label','查找功能和操作');
 dialog.innerHTML=`<div class="wf-search-head"><label for="workflow-search-input">搜索</label><button type="button" data-wf-action="close-search" aria-label="关闭搜索">×</button></div><div class="wf-search-input"><span aria-hidden="true">⌕</span><input id="workflow-search-input" type="search" role="combobox" aria-expanded="true" aria-controls="workflow-search-results workflow-ai-results" aria-autocomplete="list" autocomplete="off" placeholder="搜索页面、表单或操作" maxlength="200" value="${E(query)}"><button type="button" data-wf-action="ai-search">搜索</button></div><div class="wf-search-tabs" role="tablist" aria-label="搜索方式"><button type="button" role="tab" data-wf-action="search-mode" data-mode="normal" aria-selected="true">普通搜索</button><button type="button" role="tab" data-wf-action="search-mode" data-mode="ai" aria-selected="false">AI 搜索</button></div><div id="workflow-normal-section"><div id="workflow-search-status" role="status">正在读取…</div><div id="workflow-search-results" role="listbox" aria-label="匹配的操作"></div><button id="workflow-try-ai" type="button" data-wf-action="search-mode" data-mode="ai" hidden>试试 AI 搜索</button></div><section id="workflow-ai-section" hidden><div id="workflow-ai-status" role="status"></div><div id="workflow-ai-results" role="listbox" aria-label="AI 推荐的操作指引"></div></section><div class="wf-search-foot"><button type="button" data-wf-action="browse">全部操作指引</button><span>↑↓ 选择 · Enter 打开 · Esc 关闭</span></div>`;
 document.body.append(dialog);dialog.showModal();const input=dialog.querySelector('input');input.focus();input.setSelectionRange(query.length,query.length);
 input.addEventListener('input',event=>{if(event.isComposing){cancelWorkflowRecommendation();return;}changeWorkflowQuery(input.value);});
 input.addEventListener('compositionstart',cancelWorkflowRecommendation);
 input.addEventListener('compositionend',()=>changeWorkflowQuery(input.value));
 input.addEventListener('keydown',event=>{if(event.isComposing||event.keyCode===229)return;if(event.key==='Escape'){event.preventDefault();event.stopPropagation();closeWorkflowSearch();return;}const s=workflowSearchState;if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();s.index=Math.max(0,Math.min(s.results.length-1,s.index+(event.key==='ArrowDown'?1:-1)));paintWorkflowSearch(false);}else if(event.key==='Enter'){event.preventDefault();if(s.results[s.index])workflowNavigate('workflows/'+s.results[s.index].id);else if(s.mode==='ai')recommendWorkflowGuides(true);} });
 dialog.addEventListener('cancel',event=>{event.preventDefault();closeWorkflowSearch();});
 dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeWorkflowSearch();}});
 try{await loadWorkflowGuides();if(workflowSearchState.context===workflowContext()&&dialog.isConnected)paintWorkflowSearch();}
 catch(error){if(dialog.isConnected)dialog.querySelector('#workflow-search-status').textContent=error.message;}
}
function paintWorkflowSearch(scroll=true){
 const dialog=document.getElementById('workflow-search-dialog');if(!dialog||!workflowCatalogue)return;
 if(workflowSearchState.context!==workflowContext()){closeWorkflowSearch(false);return;}
 const s=workflowSearchState,ai=s.mode==='ai',local=WorkflowGuides.search(workflowCatalogue.workflows,s.query,state.user?.role),shown=local.slice(0,12),recommendations=s.aiItems||[];s.results=ai?recommendations:shown;
 s.index=Math.max(ai?-1:0,Math.min(s.index,s.results.length-1));
 dialog.querySelector('#workflow-search-status').textContent=local.length?`找到 ${local.length} 项操作${local.length>12?'，先显示 12 个，请继续输入缩小范围':''}`:'没有找到匹配的操作。';
 const option=(item,index)=>{const allowed=WorkflowGuides.canEnter(item,state.user?.role,state.store),form=globalThis.WORKFLOW_QUICK_FORMS?.[item.id];return `<div class="wf-search-hit"><button type="button" role="option" id="wf-${ai?'ai':'local'}-${index}" aria-selected="${index===s.index}" data-wf-action="result" data-id="${E(item.id)}"><span class="wf-result-title">${E(typeof uxEntryTitle==='function'?uxEntryTitle(item):item.title)}</span><span>${E(item.category)}</span></button><div class="wf-hit-actions"><button type="button" data-wf-action="manual" data-id="${E(item.id)}" ${allowed?'':'disabled'}>进入页面</button>${form?`<button type="button" data-wf-action="form" data-id="${E(item.id)}" ${allowed&&state.store!=='all'?'':'disabled'}>${E(form.label)}</button>`:''}<button type="button" data-wf-action="result" data-id="${E(item.id)}">操作指引</button></div></div>`;};
 dialog.querySelector('#workflow-search-results').innerHTML=ai?'':shown.map(option).join('');
 dialog.querySelector('#workflow-normal-section').hidden=ai;dialog.querySelector('#workflow-search-results').hidden=ai;dialog.querySelector('#workflow-ai-section').hidden=!ai;
 dialog.querySelector('#workflow-try-ai').hidden=ai||local.length>0||s.query.trim().length<2;
 dialog.querySelector('#workflow-ai-status').textContent=s.aiStatus==='loading'?'AI 正在查找…':s.aiStatus==='error'?s.aiError:s.aiStatus!=='done'?'输入想办的事，按 Enter 或点搜索。':recommendations.length?`找到 ${recommendations.length} 个相关流程`:'没有找到相关指引，换个说法再试试。';
 dialog.querySelector('#workflow-ai-results').innerHTML=ai?recommendations.map(option).join(''):'';
 const submit=dialog.querySelector('[data-wf-action="ai-search"]');submit.textContent=ai?'AI 搜索':'搜索';submit.disabled=ai&&(s.aiStatus==='loading'||s.query.trim().length<2);
 dialog.querySelectorAll('.wf-search-tabs [data-mode]').forEach(button=>button.setAttribute('aria-selected',String(button.dataset.mode===(ai?'ai':'normal'))));
 const input=dialog.querySelector('input');input.placeholder=ai?'描述想办的事':'搜索页面、表单或操作';if(s.results[s.index])input.setAttribute('aria-activedescendant',`wf-${ai?'ai':'local'}-${s.index}`);else input.removeAttribute('aria-activedescendant');
 if(!scroll)dialog.querySelector('[role="option"][aria-selected="true"]')?.scrollIntoView({block:'nearest'});
}
function changeWorkflowQuery(value){cancelWorkflowRecommendation();Object.assign(workflowSearchState,{query:value,index:workflowSearchState.mode==='ai'?-1:0,aiStatus:'idle',aiItems:[],aiError:''});paintWorkflowSearch();}
async function setWorkflowSearchMode(mode,search=true){
 if(!['normal','ai'].includes(mode)||!state.user||state.storeSwitch||workflowSearchState.context!==workflowContext())return;
 if(mode==='ai'&&workflowSearchState.mode==='ai'&&workflowSearchState.aiStatus==='loading')return;
 cancelWorkflowRecommendation();Object.assign(workflowSearchState,{mode,index:mode==='ai'?-1:0,aiStatus:'idle',aiItems:[],aiError:''});paintWorkflowSearch();
 if(mode==='ai'&&search)await recommendWorkflowGuides(true);
}
async function recommendWorkflowGuides(manual=true){
 const s=workflowSearchState,context=workflowContext(),query=s.query.trim().normalize('NFKC');
 if(!workflowCatalogue||!state.user||state.storeSwitch||s.context!==context||!document.getElementById('workflow-search-dialog')||query.length<2||query.length>200)return;
 if(!manual||s.mode!=='ai')return;
 if(s.aiStatus==='loading')return;
 cancelWorkflowRecommendation();const key=context+'|'+query,cached=workflowRecommendationCache.get(key);
 if(cached){Object.assign(s,{aiStatus:'done',aiItems:cached,aiError:''});paintWorkflowSearch();return;}
 const sequence=workflowAIRequestSeq,controller=new AbortController();workflowAIController=controller;Object.assign(s,{aiStatus:'loading',aiItems:[],aiError:''});paintWorkflowSearch();
 const current=()=>sequence===workflowAIRequestSeq&&s===workflowSearchState&&context===workflowContext()&&s.query.trim().normalize('NFKC')===query&&!!document.getElementById('workflow-search-dialog');
 try{
  const headers={'Content-Type':'application/json','X-App-Request':'1','X-CSRF-Token':csrf()};if(state.store!==null)headers['X-Store-ID']=String(state.store);
  const response=await fetch('/api/workflow-guides/recommendations',{method:'POST',credentials:'same-origin',headers,signal:controller.signal,body:JSON.stringify({query,trigger:manual?'manual':'no_match'})});
  if(!current())return;const data=await response.json();if(!current())return;
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'AI 暂时无法查找，请稍后点“AI 搜索”重试。');
  const seen=new Set(),items=[];for(const row of Array.isArray(data.items)?data.items:[]){const item=workflowCatalogue.workflows.find(w=>w.id===row.workflow_id);if(item&&!seen.has(item.id)){items.push(item);seen.add(item.id);}if(items.length===5)break;}
  if(!data.local_exists){workflowRecommendationCache.set(key,items);if(workflowRecommendationCache.size>30)workflowRecommendationCache.delete(workflowRecommendationCache.keys().next().value);}
  Object.assign(s,{aiStatus:data.local_exists?'idle':'done',aiItems:items,aiError:''});
 }catch(error){if(!current()||error.name==='AbortError')return;Object.assign(s,{aiStatus:'error',aiItems:[],aiError:error.message||'AI 暂时无法查找，请重试。'});}
 finally{if(current()){workflowAIController=null;paintWorkflowSearch();}}
}
function workflowNavigate(route){
 if(!WorkflowGuides.validRoute(route)||!state.user||state.storeSwitch)return;
 if(document.querySelector('#modal[open]')){const status=document.getElementById('workflow-search-status');if(status)status.textContent='请先完成或关闭当前表单，再打开其他流程。';else toast('请先完成或关闭当前表单。',true);return;}
 closeWorkflowSearch(false);go(route);
}
async function workflowOpenForm(id){
 const context=workflowContext(),data=await loadWorkflowGuides();
 if(context!==workflowContext()||!state.user||state.storeSwitch)return;
 const item=data.workflows.find(x=>x.id===id),form=globalThis.WORKFLOW_QUICK_FORMS?.[id];
 if(!item||!form||state.store==='all'||!WorkflowGuides.canEnter(item,state.user.role,state.store)){toast('请从对应业务页面办理。',true);return;}
 if(document.querySelector('#modal[open]')){toast('请先完成或关闭当前表单。',true);return;}
 workflowFormIntent={context,route:item.entry.route,selector:form.selector};
 workflowNavigate(item.entry.route);
}
function applyWorkflowFormIntent(){
 const intent=workflowFormIntent;workflowFormIntent=null;
 if(!intent||intent.context!==workflowContext()||intent.route!==state.route||state.storeSwitch||document.querySelector('#modal[open]'))return;
 // Only reviewed native entry buttons can be opened. The employee submits the form.
 const button=document.querySelector('#main')?.querySelector(intent.selector);
 if(!button||button.disabled||button.hidden||button.getClientRects().length===0){toast('请在此页面选择要办理的业务。',true);return;}
 button.click();
}
async function workflowsPage(id){
 const context=workflowContext(),data=await loadWorkflowGuides();if(context!==workflowContext())return '';
 if(id){const item=data.workflows.find(x=>x.id===id);if(!item)throw new Error('没有找到这条操作指引。');return `<div class="wf-back"><button type="button" data-wf-action="browse">‹ 全部操作指引</button><a class="wf-document-link" href="/static/workflow-handbook.html#${E(item.id)}" target="_blank" rel="noopener">打开图文手册</a></div>`+WorkflowGuides.article(item,{role:state.user.role,store:state.store});}
 return heading('操作指引','',`<a class="wf-handbook-link" href="/static/workflow-handbook.html" target="_blank" rel="noopener">图文手册</a>`)+`<section class="wf-index"><div class="wf-index-search"><label>查找流程<input type="search" id="workflow-guide-query" placeholder="业务名称、原需求名称或编号" autocomplete="off"></label><label>业务分类<select id="workflow-guide-category"><option value="">全部</option>${[...new Set(data.workflows.map(x=>x.category))].map(c=>`<option>${E(c)}</option>`).join('')}</select></label></div><p id="workflow-guide-count" role="status"></p><div id="workflow-guide-results" class="wf-grid"></div></section>`;
}
function bindWorkflowGuides(){
 const input=document.getElementById('workflow-guide-query'),category=document.getElementById('workflow-guide-category');if(!input||!workflowCatalogue)return;
 const paint=()=>{const rows=WorkflowGuides.search(workflowCatalogue.workflows,input.value,state.user?.role,category.value);document.getElementById('workflow-guide-count').textContent=rows.length?`共 ${rows.length} 个流程`:'没有找到，换个业务名称试试。';document.getElementById('workflow-guide-results').innerHTML=rows.map(WorkflowGuides.card).join('');};input.addEventListener('input',event=>{if(!event.isComposing)paint();});input.addEventListener('compositionend',paint);category.addEventListener('change',paint);paint();
}
async function workflowAsk(id){
 const context=workflowContext(),data=await loadWorkflowGuides();if(context!==workflowContext()||!state.user||state.store==='all'||state.storeSwitch)return;
 const item=data.workflows.find(x=>x.id===id);if(!item)return;
 if(document.querySelector('#modal[open]')){toast('请先完成或关闭当前表单。',true);return;}
 if(businessAssistantState.context!==businessAssistantContext()){clearBusinessAssistantSession();businessAssistantState.context=businessAssistantContext();}
 if(businessAssistantState.busy||businessAssistantState.session?.busy){toast('助手正在处理，请完成后再开始新流程。',true);return;}
 if(businessAssistantState.draft.trim()){toast('对话中还有未发送内容，请先发送或清空，再开始新流程。',true);workflowNavigate('business-assistant');return;}
 workflowAssistantIntent={context,prompt:WorkflowGuides.assistantPrompt(item),workflowId:item.id};workflowNavigate('business-assistant');
}
function applyWorkflowAssistantIntent(){
 const intent=workflowAssistantIntent;workflowAssistantIntent=null;if(!intent||intent.context!==workflowContext())return;
 const current=businessAssistantState;if(current.busy||current.session?.busy||current.draft.trim())return;
 // M6.5：不再直接清空会话；交给唯一交接入口，只预填并登记 entry_context。
 const workspace=globalThis.AssistantWorkspace;
 current.tab='chat';current.error='';current.needsRefresh=false;current.retry=null;
 if(workspace&&typeof workspace.requestHandoff==='function'&&intent.workflowId){
  const result=workspace.requestHandoff({reference:{source_type:'workflow',workflow_id:intent.workflowId},
   intent:'prepare_action',prompt:intent.prompt,contextEpoch:intent.context,returnRoute:'workflows'});
  if(!result.ok)toast(result.reason,true);
  return;
 }
 current.draft=intent.prompt;   // 交接入口不可用时退化为只预填草稿
}
// A dialog restores focus to its opener on close. Focus alone must not reopen it.
document.addEventListener('input',event=>{if(event.target.id==='workflow-top-search'&&!event.isComposing)openWorkflowSearch(event.target.value);});
document.addEventListener('compositionend',event=>{if(event.target.id==='workflow-top-search')openWorkflowSearch(event.target.value);});
document.addEventListener('keydown',event=>{
 if(event.isComposing||event.keyCode===229)return;
 if(event.target.id==='workflow-top-search'){
  if(['Enter','ArrowDown'].includes(event.key)){event.preventDefault();openWorkflowSearch(event.target.value);return;}
  // Chrome may defer text insertion after closing a native modal. Transfer the
  // first ordinary key explicitly; paste and IME still use their input events.
  if(event.key.length===1&&!event.ctrlKey&&!event.metaKey&&!event.altKey){
   const field=event.target,start=field.selectionStart??field.value.length,end=field.selectionEnd??start;
   event.preventDefault();openWorkflowSearch(field.value.slice(0,start)+event.key+field.value.slice(end));return;
  }
 }
 if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){if(!state.user||state.storeSwitch)return;event.preventDefault();openWorkflowSearch();}
});
document.addEventListener('click',async event=>{
 if(event.target.id==='workflow-top-search'){openWorkflowSearch(event.target.value);return;}
 const path=event.target.closest('[data-wf-path]');if(path){const article=path.closest('.wf-article');article.querySelectorAll('[data-wf-path]').forEach(button=>button.setAttribute('aria-selected',String(button===path)));article.querySelectorAll('[data-wf-panel]').forEach(panel=>{panel.hidden=panel.dataset.wfPanel!==path.dataset.wfPath;});return;}
 const button=event.target.closest('[data-wf-action]');if(!button||button.disabled||!state.user)return;
 const action=button.dataset.wfAction;
 try{if(action==='close-search')closeWorkflowSearch();else if(action==='search-mode')await setWorkflowSearchMode(button.dataset.mode);else if(action==='ai-search'){if(workflowSearchState.mode==='ai')await recommendWorkflowGuides(true);else paintWorkflowSearch();}else if(action==='form')await workflowOpenForm(button.dataset.id);else if(action==='browse')workflowNavigate('workflows');else if(action==='result')workflowNavigate('workflows/'+button.dataset.id);else if(action==='assistant')await workflowAsk(button.dataset.id);else if(action==='manual'){const context=workflowContext(),item=(await loadWorkflowGuides()).workflows.find(x=>x.id===button.dataset.id);if(context===workflowContext()&&item&&WorkflowGuides.canEnter(item,state.user.role,state.store))workflowNavigate(item.entry.route);}}
 catch(error){toast(error.message,true);}
});
