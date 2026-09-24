'use strict';
// This standalone handbook contains only instructions and synthetic screenshots.
const handbookData=JSON.parse(document.getElementById('workflow-data').textContent);
const handbookEscape=WorkflowGuides.escape;
function handbookRender(){
 const id=location.hash.slice(1).replace(/^workflows\//,''),item=handbookData.workflows.find(x=>x.id===id),root=document.getElementById('workflow-handbook-main');
 if(item){
  root.innerHTML=`<div class="wf-back"><a href="#">‹ 全部流程</a><button type="button" data-wfh-print>打印此流程</button></div>`+WorkflowGuides.article(item,{imagePrefix:'',images:handbookData.images||{},standalone:true});
  root.querySelectorAll('[data-wf-system]').forEach(link=>{link.href=(location.protocol==='file:'?'http://127.0.0.1:8000/':'/')+'#'+link.dataset.wfSystem;});
  document.title=item.title+' · huakangos 操作指引';
 }else{
  root.innerHTML=`<h1>huakangos 工作流手册</h1><p class="wf-offline-notice">${handbookData.workflows.length} 个典型流程 · 对应 ${handbookData.requirements.length} 项需求 · 截图使用演示资料</p>${location.protocol==='file:'?'<p class="wf-offline-notice">这是离线手册，业务入口默认打开本机系统。部署后请从系统内的“操作指引”进入对应业务。</p>':''}<div class="wf-index-search"><label>查找流程<input type="search" id="handbook-query" autocomplete="off" placeholder="业务名称、原需求名称或编号"></label><label>业务分类<select id="handbook-category"><option value="">全部</option>${[...new Set(handbookData.workflows.map(x=>x.category))].map(c=>`<option>${handbookEscape(c)}</option>`).join('')}</select></label></div><p id="handbook-count" role="status"></p><div id="handbook-results" class="wf-grid"></div><details class="wf-handbook-coverage"><summary>按原需求查找（${handbookData.requirements.length}项）</summary><ul>${handbookData.requirements.map(r=>`<li><a href="#${handbookEscape(r.workflow_ids[0])}">${handbookEscape(r.id)} · ${handbookEscape(r.title)}</a></li>`).join('')}</ul></details>`;
  const paint=()=>{const rows=WorkflowGuides.search(handbookData.workflows,document.getElementById('handbook-query').value,'',document.getElementById('handbook-category').value);document.getElementById('handbook-count').textContent=`共 ${rows.length} 个流程`;document.getElementById('handbook-results').innerHTML=rows.map(WorkflowGuides.card).join('');};
  document.getElementById('handbook-query').addEventListener('input',event=>{if(!event.isComposing)paint();});document.getElementById('handbook-query').addEventListener('compositionend',paint);document.getElementById('handbook-category').addEventListener('change',paint);paint();document.title='huakangos 工作流手册';
 }
 window.scrollTo(0,0);
}
document.addEventListener('click',async event=>{
 const path=event.target.closest('[data-wf-path]');if(path){const article=path.closest('.wf-article');article.querySelectorAll('[data-wf-path]').forEach(button=>button.setAttribute('aria-selected',String(button===path)));article.querySelectorAll('[data-wf-panel]').forEach(panel=>{panel.hidden=panel.dataset.wfPanel!==path.dataset.wfPath;});return;}
 const print=event.target.closest('[data-wfh-print]');if(print){window.print();return;}
 const button=event.target.closest('[data-wfh-copy]');if(!button)return;
 const item=handbookData.workflows.find(x=>x.id===button.dataset.wfhCopy);if(!item)return;
 const prompt=WorkflowGuides.assistantPrompt(item);let success=false;
 try{await navigator.clipboard.writeText(prompt);success=true;}catch{}
 let result=button.closest('.wf-article').querySelector('.wf-copy-result');if(!result){result=document.createElement('div');result.className='wf-copy-result';result.setAttribute('role','status');button.parentElement.after(result);}
 if(success)result.textContent='已复制，打开系统的业务助手后粘贴发送。';else{result.innerHTML='<label>请复制后粘贴到业务助手<textarea rows="6" readonly></textarea></label>';const input=result.querySelector('textarea');input.value=prompt;input.focus();input.select();}
});
window.addEventListener('hashchange',handbookRender);handbookRender();
