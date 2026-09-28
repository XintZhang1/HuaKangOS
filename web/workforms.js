'use strict';
// Form assistance only. No autosave, browser storage, guessed facts, default
// evidence, hidden transaction, or change to the original submit callback.
const workFormStates=new WeakMap();
// M6.5：未完成原表单不跳转、不覆盖。提交中直接拒绝；只有员工明确放弃才关表单并执行一次交接。
function workFormRequestHandoff(dialog,onDiscard){
 const form=dialog.querySelector('form'),ui=form&&workFormStates.get(form);
 if(!form||!ui)return false;
 if(form.dataset.submitting==='true'){toast('正在提交，请先核对本次返回结果，不要重复办理。',true);return false;}
 let prompt=dialog.querySelector('.wfx-handoff');
 if(prompt){prompt.querySelector('button').focus();return false;}   // 第二次点击不覆盖第一次待决定意图
 const last=ui.lastControl;
 prompt=document.createElement('div');prompt.className='wfx-handoff';prompt.setAttribute('role','alert');
 prompt.innerHTML='<strong>原表单还有没提交的填写内容</strong><div class="row"><button type="button" class="primary" data-wfh-keep>继续填写</button><button type="button" data-wfh-discard>放弃后打开助手</button></div>';
 prompt.querySelector('[data-wfh-keep]').addEventListener('click',()=>{prompt.remove();if(last&&last.focus)last.focus();});
 prompt.querySelector('[data-wfh-discard]').addEventListener('click',()=>{
  ui.dirty=false;ui.handoff=null;prompt.remove();
  if(typeof closeModal==='function')closeModal();
  if(typeof onDiscard==='function')onDiscard();   // 回调自己再校验一次 contextEpoch
 });
 form.appendChild(prompt);
 prompt.querySelector('button').focus();
 return true;
}
function workFormLabel(control){
 const label=control.labels?.[0]||control.closest('label');
 if(label){const copy=label.cloneNode(true);copy.querySelectorAll('input,select,textarea,button,.fieldhelp,.lookup-options,.inline-file-tools,details').forEach(n=>n.remove());return copy.textContent.replace(/\s*\*\s*$/,'').trim()||control.getAttribute('aria-label')||'此项';}
 return control.getAttribute('aria-label')||control.getAttribute('placeholder')||'此项';
}
function workFormControls(form){return [...form.querySelectorAll('input,select,textarea')].filter(el=>!el.disabled&&el.type!=='hidden'&&!el.closest('[hidden]'));}
function workFormMissing(form){
 const controls=workFormControls(form),seenRadio=new Set();
 return controls.filter(el=>{
  if(el.type==='radio'){
   const key=el.name||el;if(seenRadio.has(key))return false;seenRadio.add(key);
   const group=controls.filter(other=>other.type==='radio'&&(el.name?other.name===el.name:other===el));
   return group.some(other=>other.required)&&!group.some(other=>other.checked);
  }
  return el.required&&(el.type==='checkbox'?!el.checked:el.type==='file'?!el.files?.length:!String(el.value||'').trim());
 });
}
function disposeWorkForm(dialog){const form=dialog.querySelector('form'),ui=form&&workFormStates.get(form);if(ui?.dispose)ui.dispose();}
function workFormReveal(control){
 // Searchable selects are visually replaced by a real combobox input.
 if(control.hidden&&control.tagName==='SELECT')control=control.closest('.lookup')?.querySelector('[data-lookup-query]')||control;
 for(let details=control.closest('details');details;details=details.parentElement?.closest('details'))details.open=true;
 control.scrollIntoView({block:'center'});control.focus({preventScroll:true});
}
function workFormProgress(form){
 const ui=workFormStates.get(form);if(!ui)return;
 const required=workFormControls(form).filter(el=>el.required),missing=workFormMissing(form);
 const text=!required.length?'':missing.length?`还有 ${missing.length} 项必填`:'已填完整';
 if(ui.progress.textContent!==text)ui.progress.textContent=text;
 ui.progress.classList.toggle('is-ready',!missing.length);
 // Mark custom forms consistently without altering their constraints.
 required.forEach(el=>{
  const label=el.labels?.[0]||el.closest('label');if(!label||label.querySelector(':scope > .wfx-label')||['checkbox','radio'].includes(el.type))return;
  const textNodes=[...label.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE&&n.textContent.trim());if(!textNodes.length)return;
  const title=document.createElement('span');title.className='wfx-label';
  let mark=label.querySelector(':scope > .required');if(!mark){mark=document.createElement('span');mark.className='required wfx-required';mark.setAttribute('aria-hidden','true');mark.textContent=' *';}
  textNodes.forEach(node=>title.append(node));title.append(mark);label.prepend(title);
 });
 const lineSelectors=['[data-repair-line]','[data-retail-line]','[data-vp-line]','[data-purchase-line]','[data-addon-line]'];
 for(const selector of lineSelectors){const rows=[...form.querySelectorAll(selector)];rows.forEach((row,index)=>{let caption=row.querySelector(':scope > .wfx-line-caption');if(!caption){caption=document.createElement('div');caption.className='wfx-line-caption';row.prepend(caption);}const label=`第 ${index+1} 项 · 共 ${rows.length} 项`;if(caption.textContent!==label)caption.textContent=label;});}
}
function workFormValidationMessage(control){
 const v=control.validity||{};
 if(v.valueMissing)return control.tagName==='SELECT'||control.type==='radio'?'请选择一项。':control.type==='checkbox'?'请核对并勾选此项。':control.type==='file'?'请选择本次凭据文件。':'请填写此项。';
 if(v.tooShort)return `至少填写 ${control.minLength} 个字符。`;
 if(v.tooLong)return `最多填写 ${control.maxLength} 个字符。`;
 if(v.rangeUnderflow)return `不能早于或小于 ${control.min}。`;
 if(v.rangeOverflow)return `不能晚于或大于 ${control.max}。`;
 if(v.stepMismatch||v.badInput)return '请核对数值及允许的精度。';
 if(v.typeMismatch||v.patternMismatch)return '请按此项要求的格式填写。';
 if(v.customError&&/[\u4e00-\u9fff]/.test(control.validationMessage||''))return control.validationMessage;
 return '请核对此项后再提交。';
}
function workFormShowError(form){
 const error=form.querySelector('.formerror');if(!error||!error.textContent.trim())return;
 error.tabIndex=-1;error.scrollIntoView({block:'nearest'});error.focus({preventScroll:true});
}
function workFormCloseRequest(dialog){
 const form=dialog.querySelector('form'),ui=form&&workFormStates.get(form);if(!ui)return true;
 if(form.dataset.submitting==='true'){toast('正在提交，请先核对本次返回结果，不要重复办理。',true);return false;}
 if(!ui.dirty)return true;
 let warning=form.querySelector('.wfx-discard');if(warning){warning.querySelector('button').focus();return false;}
 warning=document.createElement('div');warning.className='wfx-discard';warning.setAttribute('role','alert');
 warning.innerHTML='<strong>还有未保存的填写内容</strong><div class="row"><button type="button" class="primary" data-wfx-keep>继续填写</button><button type="button" data-wfx-discard>放弃填写</button></div>';
 warning.querySelector('[data-wfx-keep]').addEventListener('click',()=>{warning.remove();const control=ui.lastControl;if(control?.isConnected)control.focus();});
 warning.querySelector('[data-wfx-discard]').addEventListener('click',()=>{ui.dirty=false;closeModal();});
 form.prepend(warning);warning.scrollIntoView({block:'start'});warning.querySelector('button').focus();return false;
}
function enhanceWorkForm(dialog,title){
 const form=dialog.querySelector('form');if(!form||!state.user||form.hasAttribute('data-wfx-ready'))return;
 form.dataset.wfxReady='true';const footer=form.querySelector('.modalfoot');if(!footer)return;
 // Context describes the operation, not an inferred parent document.
 const store=state.stores.find(s=>String(s.id)===String(state.store));
 const context=document.createElement('div');context.className='wfx-context';
 context.textContent=`${store?.name||'当前门店'} · ${roleNames[state.user.role]||'当前岗位'}`;
 form.prepend(context);
 const progress=document.createElement('span');progress.className='wfx-progress';progress.setAttribute('role','status');progress.setAttribute('aria-live','polite');footer.prepend(progress);
 const ui={dirty:false,lastControl:null,progress,observer:null,frame:0};workFormStates.set(form,ui);
 const schedule=()=>{if(ui.frame)return;ui.frame=requestAnimationFrame(()=>{ui.frame=0;if(form.isConnected)workFormProgress(form);});};
 const edit=event=>{if(event.target.closest('.wfx-discard'))return;ui.dirty=true;ui.lastControl=event.target;schedule();};
 form.addEventListener('input',edit);form.addEventListener('change',edit);
 // Adding/removing reviewed line rows is an edit even without typing.
 form.addEventListener('click',event=>{const button=event.target.closest('button[data-act]');if(button&&/^(repair|retail|vp|procurement)-(add|remove)-line$/.test(button.dataset.act)){ui.dirty=true;schedule();}});
 // Closed optional/details fields must never trap browser validation offscreen.
 form.addEventListener('invalid',event=>{event.preventDefault();const invalid=event.target;const error=form.querySelector('.formerror');if(error)error.textContent='请核对：'+workFormLabel(invalid)+'。'+workFormValidationMessage(invalid);if(!ui.invalidFrame){ui.invalidFrame=requestAnimationFrame(()=>{ui.invalidFrame=0;const first=[...form.elements].find(el=>el.willValidate&&!el.validity.valid);if(first)workFormReveal(first);});}},true);
 ui.observer=new MutationObserver(records=>{if(records.every(r=>r.target===progress||r.target.closest?.('.wfx-progress,.wfx-line-caption,.wfx-required')))return;schedule();});
 ui.observer.observe(form,{childList:true,subtree:true,attributes:true,attributeFilter:['required','disabled','hidden']});
 const dispose=()=>{ui.observer.disconnect();cancelAnimationFrame(ui.frame);cancelAnimationFrame(ui.invalidFrame);dialog.removeEventListener('close',dispose);};
 ui.dispose=dispose;dialog.addEventListener('close',dispose,{once:true});
 workFormProgress(form);
}
function enhanceOptionalNotes(dialog,fields,values){
 // A narrow, reviewed set: do not hide financial fields, sources, consent,
 // evidence, reasons, or any required value, even when initially empty.
 const optionalKeys=new Set(['note','notes','remark','remarks','comment']);
 for(const field of fields){if(field.required||field.type!=='textarea'||!optionalKeys.has(field.key)||String(values[field.key]||'').trim())continue;
  const input=[...dialog.querySelectorAll('textarea[name]')].find(e=>e.name===field.key),label=input?.closest('label');if(!label)continue;
  const details=document.createElement('details');details.className='wfx-optional wide';const summary=document.createElement('summary');summary.textContent=field.label+'（选填）';label.replaceWith(details);details.append(summary,label);
 }
}
// Capture only explicit employee cancellation. Programmatic close after a
// successful save (or a verified account/store switch) retains its semantics.
document.addEventListener('click',event=>{const button=event.target.closest('[data-act="close"]');if(!button)return;const dialog=button.closest('#modal');if(dialog&&!workFormCloseRequest(dialog)){event.preventDefault();event.stopImmediatePropagation();}},true);
document.addEventListener('cancel',event=>{if(event.target.id==='modal'&&!workFormCloseRequest(event.target))event.preventDefault();},true);
window.addEventListener('beforeunload',event=>{const form=document.querySelector('#modal[open] form');if(form&&workFormStates.get(form)?.dirty){event.preventDefault();event.returnValue='';}});

function mountStaffAccessSummary(dialog){
 const form=dialog.querySelector('form');if(!form?.elements.role)return;
 const summary=document.createElement('div');summary.className='notice wfx-access-summary';summary.setAttribute('role','status');summary.setAttribute('aria-live','polite');form.querySelector('.modalfoot').before(summary);
 const update=()=>{
  const admin=form.elements.role.value==='admin';
  const assignments=[...form.querySelectorAll('input[name="store_ids"]:checked')].map(input=>{const store=state.accountData.stores.find(s=>String(s.id)===input.value),role=form.elements['store_role_'+input.value]?.value;return (store?.name||'所选门店')+'：'+(roleNames[role]||'请核对岗位');});
  summary.textContent=admin?'请特别核对：管理员可管理全部门店，不受下方单店勾选限制。':assignments.length?'本次将授权：'+assignments.join('；')+'。'+(form.elements.can_group_summary.checked?'已勾选集团汇总，仅汇总符合管理岗位条件的授权门店。':'未额外授权集团汇总。'):'请至少选择一家门店，并核对该门店的岗位。尚未选择门店。';
 };form.addEventListener('change',update);update();
}
