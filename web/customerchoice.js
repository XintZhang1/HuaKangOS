'use strict';
// Every candidate is obtained from the server's current-store/owner query.
async function customerChoiceDialog({title,fields,nameKey,phoneKey,onSave,allowExisting=true,submit='建立业务'}){
 const context=`${state.user?.id}:${state.store}`,nameFields=fields.filter(f=>!['customer_id','confirm_new_customer'].includes(f.key));
 const rendered=await Promise.all(nameFields.map(f=>fieldHTML({...f,required:f.key===nameKey?true:f.required})));
 let selected=null,phoneChecked='',confirmed=false,revision=0;
 const unchanged=()=>{if(context!==`${state.user?.id}:${state.store}`)throw new Error('门店或账号已变化，请重新打开客户业务表单。');};
 const controls=`<div data-customer-choice class="wide">${allowExisting?b('choice-open','选择已有客户'):''}<div data-choice-search hidden><label>查找本人获权的客户<input type="search" name="choice_query" placeholder="姓名或电话"></label>${b('choice-search','查找')}</div><div data-choice-results></div><div data-choice-decision hidden><p>联系电话相同只是匹配提示，不会合并身份。</p><label class="checklabel"><input type="checkbox" name="choice_confirm">已核对，确认另建独立客户档案</label></div></div>`;
 const html=nameFields.map((f,i)=>rendered[i]+(f.key===(phoneKey||nameKey)?controls:'')).join('');
 modal(title,`<form><div class="formgrid">${html}</div><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button type="submit" class="primary">${E(submit)}</button></div></form>`,async form=>{
  unchanged();const values=formValues(form,nameFields),phone=String(values[phoneKey]||'').trim();
  if(selected){delete values[nameKey];delete values[phoneKey];values.customer_id=selected.id;}
  else{
   if(phone){const d=await api('/api/customer-choice/matches?phone='+encodeURIComponent(phone));unchanged();
    if(d.items.length&&!(confirmed&&phoneChecked===phone)){showMatches(d,phone);throw new Error(allowExisting?'请明确选择复用客户，或核对后勾选另建独立档案。':'请核对匹配档案并明确勾选另建；新增不会覆盖原客户资料。');}
   }
   if(confirmed&&phoneChecked===phone)values.confirm_new_customer=true;
  }
  await onSave(values);closeModal();state.analytics=null;if(state.user)await render();toast('已保存，客户关联已按本次明确选择记录');
 });
 const form=$('#modal form'),nameInput=form.elements[nameKey],phoneInput=form.elements[phoneKey];
 function showMatches(data,phone='',search=false){
  if(!form.isConnected)return;
  const target=form.querySelector('[data-choice-results]');target.innerHTML=data.items.length?`<p>${search?'本次查找结果':'此电话匹配到的获权档案'}</p>${data.items.map(c=>`<div class="filerecord"><div class="filetext"><strong>${E(c.name)}</strong><p>${E(c.phone||'未填写电话')}</p>${allowExisting?b('choice-select','复用此客户',`data-id="${c.id}"`):''}</div></div>`).join('')}`+(data.has_more?'<p>匹配超过20条，请填写更明确的查找内容。</p>':''):'<p>没有找到当前获权的匹配档案。</p>';
  for(const button of target.querySelectorAll('[data-act=choice-select]'))button.addEventListener('click',()=>{
   unchanged();revision++;selected=data.items.find(c=>c.id===Number(button.dataset.id));nameInput.value=selected.name;nameInput.disabled=true;if(phoneInput){phoneInput.value=selected.phone;phoneInput.disabled=true;}
   confirmed=false;form.querySelector('[name=choice_confirm]').checked=false;form.querySelector('[data-choice-decision]').hidden=true;
   target.innerHTML=`<p><strong>已明确选择：${E(selected.name)}</strong> · ${E(selected.phone||'未填写电话')}</p><p>本次业务复用该档案，不改写姓名、电话或联系意愿。</p>${b('choice-clear','改为填写新客户')}`;
   target.querySelector('[data-act=choice-clear]').onclick=()=>{selected=null;nameInput.disabled=false;if(phoneInput)phoneInput.disabled=false;target.innerHTML='';confirmed=false;};
  });
  if(!search){phoneChecked=phone;confirmed=false;form.querySelector('[name=choice_confirm]').checked=false;form.querySelector('[data-choice-decision]').hidden=!data.items.length;}
 }
 if(phoneInput){phoneInput.addEventListener('input',()=>{revision++;confirmed=false;phoneChecked='';form.querySelector('[name=choice_confirm]').checked=false;form.querySelector('[data-choice-decision]').hidden=true;form.querySelector('[data-choice-results]').innerHTML='';});
  phoneInput.addEventListener('blur',async()=>{const stamp=++revision,phone=phoneInput.value.trim();if(!phone||selected)return;try{const data=await api('/api/customer-choice/matches?phone='+encodeURIComponent(phone));unchanged();if(stamp===revision&&form.isConnected)showMatches(data,phone);}catch(e){if(form.isConnected)form.querySelector('.formerror').textContent=e.message;}});
 }
 form.querySelector('[name=choice_confirm]').onchange=e=>{confirmed=e.target.checked;phoneChecked=phoneInput?.value.trim()||'';};
 if(allowExisting){form.querySelector('[data-act=choice-open]').onclick=()=>{const panel=form.querySelector('[data-choice-search]');panel.hidden=false;form.elements.choice_query.value=phoneInput?.value||nameInput.value;};
  form.querySelector('[data-act=choice-search]').onclick=async()=>{try{unchanged();const d=await api('/api/customer-choice/matches?q='+encodeURIComponent(form.elements.choice_query.value));showMatches(d,'',true);}catch(e){form.querySelector('.formerror').textContent=e.message;}};
 }
}

async function createCustomerChoiceCase(kind){
 const spec=state.catalog.kinds[kind];if(!canWrite()||!spec?.can_create)throw new Error('请选择具有新建权限的具体门店。');const request_id=requestKey();
 return customerChoiceDialog({title:'新建'+spec.label,fields:spec.fields,nameKey:'customer_name',phoneKey:'customer_phone',onSave:async values=>{const row=await api('/api/flow/cases',{method:'POST',body:{request_id,kind,values}});go('case/'+row.id);}});
}

async function createCustomerChoiceMaster(){
 const spec=state.catalog.master_types.customers;if(!canWrite()||!spec?.can_write)throw new Error('当前岗位不能新增客户档案。');
 return customerChoiceDialog({title:'新增客户档案',fields:spec.fields,nameKey:'name',phoneKey:'phone',allowExisting:false,submit:'建立独立客户档案',onSave:values=>api('/api/flow/master/customers',{method:'POST',body:{values}})});
}
