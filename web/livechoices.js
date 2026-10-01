'use strict';
// The original select remains the form value and change-event contract.
const liveChoiceStates=new WeakMap();
let liveChoiceSequence=0;
let liveChoicePointerId=null;
function liveChoiceContext(){return typeof storeContextVersion==='undefined'?0:storeContextVersion;}
function liveChoiceItems(select){return Array.from(select.options).filter(option=>option.value&&!option.disabled&&!option.parentElement?.disabled).map(option=>({id:option.value,label:option.label??option.textContent,create:option.hasAttribute('data-search-create')}));}
function liveChoiceMatch(items,query){const terms=String(query).trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);return items.filter(item=>item.create||terms.every(term=>String(item.label).toLocaleLowerCase().includes(term)));}
function liveChoiceState(root){return root&&liveChoiceStates.get(root);}
function liveChoiceChanged(s,reason){const event=new Event('change',{bubbles:true});event.liveChoiceReason=reason;s.select.dispatchEvent(event);}
function liveChoiceInvalidate(s){clearTimeout(s.timer);s.timer=null;s.run={};}
function lookupClose(root){const s=liveChoiceState(root);if(!s)return;s.pointerClosePending=false;s.list.hidden=true;s.input.setAttribute('aria-expanded','false');s.input.removeAttribute('aria-activedescendant');s.active=-1;}
function liveChoiceCancelPointer(){liveChoicePointerId=null;document.querySelectorAll('.lookup').forEach(root=>{if(liveChoiceState(root)?.pointerClosePending)lookupClose(root);});}
function liveChoiceValidity(s){s.input.required=s.select.required||s.inputRequired;s.input.disabled=s.select.matches(':disabled');s.input.setCustomValidity(!s.input.disabled&&s.input.value&&!s.select.value?'请从列表中选择':'');}
function liveChoiceSync(s){
 const option=s.select.selectedOptions[0],value=s.select.value;
 if(value!==s.value||!s.editing){s.input.value=value?(option?.label??option?.textContent??''):'';s.editing=false;}
 s.value=value;liveChoiceValidity(s);
 if(s.input.disabled)lookupClose(s.root);
}
function liveChoiceClear(s){liveChoiceInvalidate(s);s.context=liveChoiceContext();s.input.value='';s.select.replaceChildren(document.createElement('option'));s.value='';s.items=[];s.editing=false;s.list.replaceChildren();lookupClose(s.root);liveChoiceValidity(s);}
function liveChoiceCheck(s){if(s.context===liveChoiceContext())return true;liveChoiceClear(s);return false;}
function clearLiveChoices(){document.querySelectorAll('.lookup').forEach(root=>{const s=liveChoiceState(root);if(s)liveChoiceClear(s);});}
function liveChoiceShow(s){s.list.hidden=false;s.input.setAttribute('aria-expanded','true');s.active=-1;s.input.removeAttribute('aria-activedescendant');}
function liveChoiceMessage(s,message,retry=false){
 s.items=[];s.list.replaceChildren();const text=document.createElement('div');text.className='fieldhelp';text.setAttribute('role','status');text.textContent=message;s.list.append(text);
 if(retry){const button=document.createElement('button');button.type='button';button.textContent='重试';button.dataset.lookupRetry='';s.list.append(button);}
 liveChoiceShow(s);
}
function lookupResults(root,items,hasMore=false){
 const s=liveChoiceState(root);if(!s||!liveChoiceCheck(s)||s.input.disabled)return;
 s.items=Array.isArray(items)?items.filter(item=>item&&item.id!==null&&item.id!==undefined).map(item=>({...item,id:String(item.id),label:String(item.label??'')})):[];
 if(s.select.dataset.searchAll&&(!s.editing||!s.input.value))s.items.unshift({id:'',label:s.select.dataset.searchAll});
 s.list.replaceChildren();
 for(const [index,item]of s.items.slice(0,100).entries()){const button=document.createElement('button');button.type='button';button.setAttribute('role','option');button.tabIndex=-1;button.id=s.list.id+'-'+index;button.dataset.lookupIndex=String(index);button.textContent=item.label;button.setAttribute('aria-selected',String(item.id===s.select.value));s.list.append(button);}
 if(!s.items.length||hasMore||s.items.length>100){const note=document.createElement('div');note.className='fieldhelp';note.setAttribute('role','status');note.textContent=s.items.length?'继续输入可缩小范围':'未找到记录';s.list.append(note);}
 liveChoiceShow(s);
}
function liveChoiceChoose(s,index){
 if(!liveChoiceCheck(s)||s.input.disabled)return;const item=s.items[index];if(!item)return;
 liveChoiceInvalidate(s);
 if(s.remote&&item.id){let option=Array.from(s.select.options).find(option=>option.value===item.id);if(!option){option=document.createElement('option');option.value=item.id;s.select.append(option);}option.textContent=item.label;}
 s.select.value=item.id;
 if(s.select.value!==item.id)return;
 s.value=item.id;s.input.value=item.id?(s.select.selectedOptions[0]?.label??s.select.selectedOptions[0]?.textContent??item.label):'';s.editing=false;liveChoiceValidity(s);lookupClose(s.root);
 liveChoiceChanged(s,item.id?'select':'clear');
 if(s.input.isConnected&&document.activeElement!==s.input){s.suppressFocus=true;s.input.focus();}
}
function liveChoiceLocal(s){lookupResults(s.root,liveChoiceMatch(liveChoiceItems(s.select),s.editing?s.input.value:''));}
function lookupSearch(input,immediate=false){
 const s=liveChoiceState(input.closest('.lookup'));if(!s||!liveChoiceCheck(s)||input.disabled)return;
 liveChoiceInvalidate(s);const hadValue=Boolean(s.select.value);s.select.value='';s.value='';s.editing=true;liveChoiceValidity(s);lookupClose(s.root);
 if(hadValue||!input.value)liveChoiceChanged(s,input.value?'edit':'clear');
 if(s.composing)return;
 if(!s.remote){liveChoiceLocal(s);return;}
 const run=s.run,context=s.context,query=input.value;
 s.timer=setTimeout(async()=>{
  if(!s.root.isConnected||s.run!==run||context!==liveChoiceContext()||input.disabled)return;
  liveChoiceMessage(s,'正在查找…');
  try{const p=new URLSearchParams({q:query});if(s.root.dataset.case)p.set('case_id',s.root.dataset.case);
   const data=s.loader?await s.loader(query):await api((s.root.dataset.typed==='1'?'/api/masters/lookup/':'/api/flow/lookup/')+s.root.dataset.kind+'?'+p);
   if(s.root.isConnected&&s.run===run&&context===liveChoiceContext()&&!input.disabled)lookupResults(s.root,data.items,data.has_more);
  }catch(error){if(s.root.isConnected&&s.run===run&&context===liveChoiceContext()&&!input.disabled)liveChoiceMessage(s,error.message||'查找失败，请重试',true);}
 },immediate?0:250);
}
function liveChoiceAttach(root,input,select,remote){
 if(liveChoiceState(root))return;
 root.classList.add('lookup');root.dataset.liveChoice='1';select.hidden=true;
 input.dataset.lookupQuery='';input.type='search';input.autocomplete='off';input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-expanded','false');
 if(remote&&input.maxLength<0)input.maxLength=100;
 let list=root.querySelector('.lookup-options');if(!list){list=document.createElement('div');list.className='lookup-options';root.append(list);}
 if(!list.id)list.id='live-choice-'+(++liveChoiceSequence);list.setAttribute('role','listbox');list.hidden=true;input.setAttribute('aria-controls',list.id);
 const s={root,input,select,list,remote,inputRequired:input.required&&!select.required,context:liveChoiceContext(),value:null,editing:false,active:-1,items:[],run:{}};liveChoiceStates.set(root,s);
 if(!input.hasAttribute('aria-label')&&!input.hasAttribute('aria-labelledby')){const label=select.labels?.[0]||root.closest('label');const text=select.getAttribute('aria-label')||label?.childNodes[0]?.textContent?.trim()||select.dataset.searchPlaceholder||'查找';input.setAttribute('aria-label',text);}
 for(const label of Array.from(select.labels||[])){if(label.htmlFor===select.id&&select.id){if(!input.id)input.id=list.id+'-input';label.htmlFor=input.id;}}
 if(!input.placeholder)input.placeholder=select.dataset.searchPlaceholder||'输入名称查找';
 select.addEventListener('invalid',event=>{event.preventDefault();liveChoiceValidity(s);input.focus();input.reportValidity();});
 liveChoiceSync(s);
}
function enhanceTypedChoices(){document.querySelectorAll('.typed-ref').forEach(root=>{
 const input=root.querySelector('[data-typed-query], [data-lookup-query]'),select=root.querySelector('select');if(!input||!select||liveChoiceState(root))return;
 root.dataset.typed='1';root.querySelector('[data-act=typed-lookup]')?.remove();input.removeAttribute('data-typed-query');
 root.querySelectorAll('small').forEach(note=>{if(/100|关键词|查找/.test(note.textContent))note.remove();});
 liveChoiceAttach(root,input,select,true);
 });
 document.querySelectorAll('.lookup').forEach(root=>{const input=root.querySelector('[data-lookup-query]'),select=root.querySelector('select');if(input&&select)liveChoiceAttach(root,input,select,root.dataset.localChoice!=='1');});
}
function enhanceSearchChoices(){document.querySelectorAll('select[data-search-select]').forEach(select=>{
 if(select.multiple||select.closest('[data-live-choice]'))return;
 const root=document.createElement('div');root.dataset.localChoice='1';const input=document.createElement('input');select.before(root);root.append(input,select);liveChoiceAttach(root,input,select,false);
 });}
function registerLiveChoiceLoader(target,loader){
 if(typeof loader!=='function')throw new TypeError('查找方法无效');
 enhanceLiveChoices();const root=target.matches('.lookup')?target:target.closest('.lookup')||target.querySelector('.lookup'),s=liveChoiceState(root);
 if(!s)throw new Error('查找输入尚未准备好');liveChoiceInvalidate(s);s.loader=loader;s.remote=true;if(s.input.maxLength<0)s.input.maxLength=100;return s;
}
 document.addEventListener('compositionstart',event=>{const s=liveChoiceState(event.target.closest?.('.lookup'));if(s&&event.target===s.input){s.composing=true;liveChoiceInvalidate(s);}});
 document.addEventListener('compositionend',event=>{const s=liveChoiceState(event.target.closest?.('.lookup'));if(s&&event.target===s.input){s.composing=false;lookupSearch(s.input);}});
 document.addEventListener('input',event=>{if(event.target.matches?.('[data-lookup-query]')){const s=liveChoiceState(event.target.closest('.lookup'));if(s){s.composing=event.isComposing||s.composing;lookupSearch(event.target);}}});
 document.addEventListener('change',event=>{if(event.target.tagName==='SELECT'){const s=liveChoiceState(event.target.closest('.lookup'));if(s){liveChoiceInvalidate(s);liveChoiceSync(s);if(!s.list.hidden&&!s.remote)liveChoiceLocal(s);}}});
 document.addEventListener('focusin',event=>{if(!event.target.matches?.('[data-lookup-query]'))return;const s=liveChoiceState(event.target.closest('.lookup'));if(!s||!liveChoiceCheck(s)||s.input.disabled)return;if(s.suppressFocus){s.suppressFocus=false;return;}liveChoiceSync(s);const items=liveChoiceItems(s.select);if(!s.remote)liveChoiceLocal(s);else if(items.length)lookupResults(s.root,items);else lookupSearch(s.input,true);});
 document.addEventListener('pointerdown',event=>{if(event.isPrimary)liveChoicePointerId=event.pointerId;},true);
 document.addEventListener('pointerup',event=>{if(event.pointerId===liveChoicePointerId)liveChoicePointerId=null;},true);
 document.addEventListener('pointercancel',event=>{if(event.pointerId===liveChoicePointerId)liveChoiceCancelPointer();},true);
 window.addEventListener('blur',liveChoiceCancelPointer);
 document.addEventListener('focusout',event=>{const s=liveChoiceState(event.target.closest?.('.lookup'));if(s&&!s.root.contains(event.relatedTarget)){liveChoiceInvalidate(s);
  // Keep inline results in place until the pointer click activates its target.
  // The existing outside-click handler then closes them; ordinary focus still closes now.
  if(liveChoicePointerId!==null&&event.relatedTarget)s.pointerClosePending=true;else lookupClose(s.root);
 }});
 document.addEventListener('keydown',event=>{
 const s=liveChoiceState(event.target.closest?.('.lookup'));if(!s||event.target!==s.input||!liveChoiceCheck(s)||event.isComposing||s.composing)return;
 if(event.key==='Escape'||event.key==='Tab'){liveChoiceInvalidate(s);lookupClose(s.root);return;}
 if(['ArrowDown','ArrowUp'].includes(event.key)){
  event.preventDefault();if(s.list.hidden){if(s.remote){const items=liveChoiceItems(s.select);if(items.length)lookupResults(s.root,items);else lookupSearch(s.input,true);}else liveChoiceLocal(s);}
  const buttons=Array.from(s.list.querySelectorAll('[data-lookup-index]'));if(!buttons.length)return;
  s.active=s.active<0?(event.key==='ArrowDown'?0:buttons.length-1):(s.active+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length;
  buttons.forEach((button,index)=>button.classList.toggle('lookup-active',index===s.active));s.input.setAttribute('aria-activedescendant',buttons[s.active].id);buttons[s.active].scrollIntoView({block:'nearest'});
 }else if(event.key==='Enter'&&!s.list.hidden){event.preventDefault();if(s.items.length)liveChoiceChoose(s,s.active<0?0:s.active);}
 });
 document.addEventListener('click',event=>{const root=event.target.closest?.('.lookup'),s=liveChoiceState(root);if(s){const option=event.target.closest('[data-lookup-index]');if(option)liveChoiceChoose(s,Number(option.dataset.lookupIndex));else if(event.target.closest('[data-lookup-retry]')){s.suppressFocus=true;s.input.focus();lookupSearch(s.input,true);}}document.querySelectorAll('.lookup').forEach(item=>{if(!item.contains(event.target))lookupClose(item);});});
 document.addEventListener('reset',event=>{setTimeout(()=>event.target.querySelectorAll('.lookup').forEach(root=>{const s=liveChoiceState(root);if(s){liveChoiceInvalidate(s);s.editing=false;liveChoiceSync(s);lookupClose(root);}}),0);});
 function enhanceLiveChoices(){enhanceTypedChoices();enhanceSearchChoices();}
 const liveChoiceObserver=new MutationObserver(changes=>{
 enhanceLiveChoices();
 const roots=new Set();for(const change of changes){const element=change.target.nodeType===1?change.target:change.target.parentElement;if(!element)continue;const select=element.closest('select');if(select)roots.add(select.closest('.lookup'));if(element.tagName==='FIELDSET')element.querySelectorAll('.lookup').forEach(root=>roots.add(root));}
 for(const root of roots){const s=liveChoiceState(root);if(s){liveChoiceSync(s);if(!s.list.hidden&&!s.remote)liveChoiceLocal(s);}}
 });
 liveChoiceObserver.observe(document.documentElement,{childList:true,subtree:true,attributes:true,characterData:true,attributeFilter:['disabled','required','selected','label','value','data-search-select','data-search-placeholder']});
 enhanceLiveChoices();
