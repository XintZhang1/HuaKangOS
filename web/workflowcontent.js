'use strict';
// Shared, deterministic help rendering. The catalogue contains no business records.
(function(scope){
 const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const normalize=value=>String(value??'').normalize('NFKC').toLowerCase().replace(/预定/g,'预订').replace(/[\s\p{P}\p{S}]/gu,'');
 const roles={admin:'管理员',manager:'店长',sales:'销售',service:'服务顾问',customer_service:'客服',reception:'接待',inventory:'库管',technician:'技师',finance:'财务',auditor:'复核人员'};
 const validRoute=value=>typeof value==='string'&&/^[a-z][a-z0-9-]*(?:\/[a-zA-Z0-9_-]+)*$/.test(value)&&value.length<180;
 function search(items,query='',role='',category=''){
  const raw=String(query).trim(),clean=raw.replace(/^(我想|我要|帮我|请问|请帮我|我需要|需要|如何|怎么|怎样|想要|办理|申请|帮忙|请)+/g,'').replace(/(怎么办|怎么做|怎么操作|如何操作|在哪里|在哪儿|在哪|一下|操作流程|流程|操作)$/g,'');
  const words=(clean||raw).split(/\s+/).map(normalize).filter(Boolean);
  return items.flatMap(item=>{
   if(category&&item.category!==category)return [];
   const title=normalize(item.title),keys=(item.keywords||[]).map(normalize),requirements=(item.requirements||[]).map(r=>normalize(r.id+' '+r.title));
   const hay=normalize([item.title,item.category,item.summary,item.entry?.label,...item.keywords||[],...(item.manual||[]).map(step=>step.where),...(item.requirements||[]).flatMap(r=>[r.id,r.title,r.group]),...(item.exceptions||[]).map(e=>e.when)].join(' '));
   if(words.some(w=>!hay.includes(w)))return [];
   const q=normalize(clean||raw),entry=normalize(item.entry?.label||'').replace(/^打开/,''),score=(title===q&&q?100:0)+(entry===q&&q?60:0)+(q&&title.startsWith(q)?40:0)+(q&&title.includes(q)?25:0)+(keys.includes(q)&&q?20:0)+(requirements.some(r=>r.includes(q))&&q?12:0)+(item.roles?.includes(role)?5:0);
   return [{item,score}];
  }).sort((a,b)=>b.score-a.score||a.item.title.localeCompare(b.item.title,'zh-CN')).map(x=>x.item);
 }
 function canEnter(item,role,store){return validRoute(item.entry?.route)&&(!['all',null,undefined].includes(store)||item.entry.mode==='read')&&(role==='admin'||item.entry.roles?.includes(role));}
 function assistantPrompt(item){return `我想办理：${item.title}。\n${item.assistant.prompt}\n请先询问本次必要资料，逐步引导。查询和填表使用系统现有入口；生成表单后等我核对确认。不要把图片示例或操作说明当成实际已发生的业务，也不要沿用其他单据的客户、金额或凭据。${item.assistant.mode==='guide'?'本流程有必须由员工在原页面办理的步骤，请明确告诉我入口，并帮我整理所需资料。':''}`;}
 function steps(rows,assistant=false){return `<ol class="wf-steps">${rows.map((step,i)=>`<li><span class="wf-step-number">${i+1}</span><div><div class="wf-step-actor">${escape(step.actor)}${step.where?' · '+escape(step.where):''}</div><p>${escape(step.action)}</p><p class="wf-expected">${escape(step.expected)}</p></div></li>`).join('')}</ol>`;}
 function article(item,{imagePrefix='/static/',images={},role='',store='1',standalone=false}={}){
  const linkable=canEnter(item,role,store),manual=item.manual||[],assistant=item.assistant,form=scope.WORKFLOW_QUICK_FORMS?.[item.id];
  const formLink=!form?'':standalone?`<a class="wf-form-link" data-wf-system="workflow-form/${escape(item.id)}" href="/#workflow-form/${escape(item.id)}">${escape(form.label)}</a>`:`<button type="button" data-wf-action="form" data-id="${escape(item.id)}" ${linkable&&store!=='all'?'':'disabled'}>${escape(form.label)}</button>`;
  const data=escape(item.id),refs=(item.requirements||[]).map(r=>`<li><span>${escape(r.id)}</span> ${escape(r.title)}</li>`).join('');
  const imageURL=images[item.screenshot?.src]||imagePrefix+item.screenshot?.src;
  const screenshot=item.screenshot?.src?`<figure class="wf-figure"><a href="${escape(imageURL)}" data-wf-zoom aria-label="放大截图"><img src="${escape(imageURL)}" alt="${escape(item.screenshot.caption)}" loading="lazy" width="1360" height="900"></a><figcaption>${escape(item.screenshot.caption)} · 演示资料；点击放大</figcaption></figure>`:'';
  return `<article class="wf-article" data-workflow="${data}"><div class="wf-breadcrumb">${escape(item.category)}</div><h1>${escape(item.title)}</h1><p class="wf-goal">${escape(item.summary)}</p><div class="wf-actions">${standalone?`<a class="wf-primary" data-wf-system="${escape(item.entry.route)}" href="/#${escape(item.entry.route)}">${escape(item.entry.label)}</a><button type="button" data-wfh-copy="${data}">复制给业务助手</button>`:`<button type="button" class="primary" data-wf-action="manual" data-id="${data}" ${linkable?'':'disabled'}>${escape(item.entry.label)}</button><button type="button" data-wf-action="assistant" data-id="${data}" ${store==='all'?'disabled':''}>${assistant.mode==='guide'?'让助手帮我准备':'让助手带我办'}</button>`}${formLink}</div>${!standalone&&!linkable?`<p class="wf-role-note">${store==='all'&&item.entry.mode==='write'?'选择一家门店后办理。':'此步骤由'+escape((item.entry.roles||[]).map(r=>roles[r]||r).join('、'))+'办理。'}</p>`:''}<section><h2>开始前准备</h2><ul>${item.prerequisites.map(p=>`<li>${escape(p)}</li>`).join('')}</ul></section>${screenshot}<div class="wf-path-tabs" role="tablist" aria-label="办理方式"><button type="button" role="tab" aria-selected="true" data-wf-path="manual">手动办理</button><button type="button" role="tab" aria-selected="false" data-wf-path="assistant">业务助手办理</button></div><section data-wf-panel="manual">${steps(manual)}</section><section data-wf-panel="assistant" hidden><p class="wf-assistant-note">${assistant.mode==='guide'?'助手先整理资料，必要步骤按下列入口手动办理。':'助手会询问缺少的资料，填好表单后由你核对并确认。'}</p>${steps(assistant.steps,true)}<details><summary>可以这样问</summary><pre class="wf-prompt">${escape(assistantPrompt(item))}</pre></details></section><section><h2>遇到问题</h2><div class="wf-exceptions">${item.exceptions.map(x=>`<div><h3>${escape(x.when)}</h3><p>${escape(x.action)}</p></div>`).join('')}</div></section><section><h2>完成后核对</h2><ul>${item.completion.map(p=>`<li>${escape(p)}</li>`).join('')}</ul></section><details class="wf-references"><summary>对应需求（${item.requirement_ids.length}项）</summary><ul>${refs}</ul></details></article>`;
 }
 function card(item){return `<a class="wf-card" href="#workflows/${escape(item.id)}" data-wfh-guide="${escape(item.id)}"><span>${escape(item.category)}</span><h2>${escape(item.title)}</h2><p>${escape(item.summary)}</p></a>`;}
 // An in-page viewer also works for embedded offline images; no data-URL tab.
 if(typeof document!=='undefined')document.addEventListener('click',event=>{
  const link=event.target.closest('[data-wf-zoom]');if(!link)return;event.preventDefault();
  const picture=link.querySelector('img');if(!picture)return;
  const dialog=document.createElement('dialog');dialog.className='wf-image-dialog';dialog.setAttribute('aria-label','查看截图');
  dialog.innerHTML='<div class="wf-image-head"><span>截图</span><button type="button" aria-label="关闭截图">关闭</button></div><div class="wf-image-scroll"><img src="'+escape(picture.src)+'" alt="'+escape(picture.alt)+'"></div>';
  dialog.querySelector('button').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>dialog.remove());document.body.append(dialog);dialog.showModal();
 });
 scope.WorkflowGuides={escape,normalize,search,canEnter,assistantPrompt,article,card,roles,validRoute};
})(globalThis);
