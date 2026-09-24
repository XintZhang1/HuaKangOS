'use strict';
const inlineFileUploads=new WeakMap();
function inlineFileUploadScope(root){return root.closest('form')||root;}
function requireInlineFileIdle(root){if(inlineFileUploads.has(inlineFileUploadScope(root)))throw new Error('文件正在上传，请稍候。');}
function beginInlineFileUpload(root){
 const scope=inlineFileUploadScope(root);requireInlineFileIdle(root);
 const controls=new Map(Array.from(scope.querySelectorAll('[type="submit"], .inline-file-tools button, .inline-file-tools input, .inline-file-tools select'),control=>[control,control.disabled]));
 const lock={controls};inlineFileUploads.set(scope,lock);for(const control of controls.keys())control.disabled=true;
 return ()=>{if(inlineFileUploads.get(scope)!==lock)return;inlineFileUploads.delete(scope);for(const [control,disabled]of controls)if(control.isConnected)control.disabled=disabled;};
}
function inlineFileControls(caseId,kind='file'){
 return `<div class="inline-file-tools" data-file-case="${E(caseId)}" data-file-kind="${E(kind)}">${b('inline-file-open','上传文件')}<div data-inline-file-panel class="inline-upload" hidden></div><div data-inline-file-status role="status"></div></div>`;
}
function caseFilePickerHTML(name,caseId,files=[]){
 return `<div data-file-picker><select name="${E(name)}" required data-search-select><option value="">选择或上传文件</option>${files.filter(f=>!f.generated&&f.security?.can_use).map(f=>`<option value="${f.id}">${E(f.name)} · ${E(f.label)}</option>`).join('')}</select>${inlineFileControls(caseId)}</div>`;
}
function inlineUploadCategories(kind){
 const role=state.user.role;
 return Object.entries(state.catalog.upload_categories).filter(([key])=>
  (!['receipt','invoice','procurement_contract'].includes(key)||['admin','manager','finance'].includes(role))&&
  (!['signed_contract','signed_handover'].includes(key)||['admin','manager','sales'].includes(role))&&
  (!['signed_file','handover_file'].includes(kind)||key===(kind==='signed_file'?'signed_contract':'signed_handover')));
}
async function openInlineFile(button){
 const root=button.closest('.inline-file-tools'),panel=root.querySelector('[data-inline-file-panel]'),context=storeContextVersion;
 requireInlineFileIdle(root);
 const row=await api('/api/flow/cases/'+root.dataset.fileCase);requireStoreContext(context);if(!root.isConnected)return;requireInlineFileIdle(root);
 const categories=inlineUploadCategories(root.dataset.fileKind),files=row.files.filter(f=>f.generated&&f.security?.can_use);
 panel.innerHTML=`<div>文件用途<select data-inline-category aria-label="文件用途">${categories.map(([key,label])=>`<option value="${E(key)}">${E(label)}</option>`).join('')}</select></div><div data-inline-source-wrap hidden>对应合同或交接单<select data-inline-source aria-label="对应合同或交接单"></select></div><input type="file" data-inline-file aria-label="选择上传文件" accept=".pdf,.jpg,.jpeg,.png,.docx,.txt"><div class="row">${b('inline-file-upload','上传并选用','','primary')}${b('inline-file-dismiss','收起')}</div>`;
 panel.hidden=false;
 const category=panel.querySelector('[data-inline-category]'),source=panel.querySelector('[data-inline-source]');
 const preferred=root.dataset.fileKind==='signed_file'?'signed_contract':root.dataset.fileKind==='handover_file'?'signed_handover':'evidence';
 if(categories.some(([key])=>key===preferred))category.value=preferred;
 const update=()=>{const signed=category.value.startsWith('signed_');panel.querySelector('[data-inline-source-wrap]').hidden=!signed;source.innerHTML='<option value="">请选择对应版本</option>'+files.filter(f=>f.category===(category.value==='signed_contract'?'contract':'handover')).map(f=>`<option value="${f.id}">${E(f.name)} · ${time(f.created_at)}</option>`).join('');};
 category.onchange=update;update();
}
async function sendInlineFile(button){
 const root=button.closest('.inline-file-tools'),panel=root.querySelector('[data-inline-file-panel]'),status=root.querySelector('[data-inline-file-status]'),context=storeContextVersion;
 requireInlineFileIdle(root);
 const file=panel.querySelector('[data-inline-file]').files[0];if(!file)throw new Error('请选择要上传的文件。');
 if(file.size>10*1024*1024)throw new Error('文件不能超过10兆字节。');
 const category=panel.querySelector('[data-inline-category]').value,source=panel.querySelector('[data-inline-source]').value;
 if(category.startsWith('signed_')&&!source)throw new Error('请选择对应的合同或交接单版本。');
 const body=new FormData();body.append('file',file);body.append('category',category);if(category.startsWith('signed_'))body.append('source_file_id',source);
 const finish=beginInlineFileUpload(root);
 try{
  const picker=root.closest('.lookup,[data-file-picker]'),selection=picker.querySelector('select');
  selection.value='';selection.dispatchEvent(new Event('change',{bubbles:true}));
  const query=picker.querySelector('[data-lookup-query]');if(query){query.value='';query.setCustomValidity('');}
  const asset=await api('/api/flow/cases/'+root.dataset.fileCase+'/files',{method:'POST',body});requireStoreContext(context);if(!root.isConnected)return;
  root.dataset.uploadedId=String(asset.id);status.textContent='文件已上传，正在检查…';
  if(state.row?.id===Number(root.dataset.fileCase)&&!state.row.files.some(f=>f.id===asset.id))state.row.files.push(asset);
  await selectUploadedFile(root,context);
 }finally{finish();}
}
async function selectUploadedFile(root,context=storeContextVersion){
 const data=await api('/api/flow/lookup/'+root.dataset.fileKind+'?case_id='+root.dataset.fileCase);requireStoreContext(context);if(!root.isConnected)return;
 const item=data.items.find(f=>String(f.id)===root.dataset.uploadedId),status=root.querySelector('[data-inline-file-status]');
 if(!item){status.innerHTML='文件已保存，检查通过后可选用。'+b('inline-file-check','检查上传结果');return;}
 const select=root.closest('.lookup,[data-file-picker]').querySelector('select');select.innerHTML=`<option value=""></option><option value="${item.id}" selected>${E(item.label)}</option>`;
 const input=root.closest('.lookup')?.querySelector('[data-lookup-query]');if(input){input.value=item.label;input.setCustomValidity('');}
 select.dispatchEvent(new Event('change',{bubbles:true}));status.textContent='已选用：'+item.label;root.querySelector('[data-inline-file-panel]').hidden=true;
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-act]');if(!button||button.disabled||!button.dataset.act.startsWith('inline-file-'))return;
 const root=button.closest('.inline-file-tools'),priorDisabled=button.disabled;button.disabled=true;try{
  requireInlineFileIdle(root);
  if(button.dataset.act==='inline-file-open')await openInlineFile(button);
  else if(button.dataset.act==='inline-file-upload')await sendInlineFile(button);
  else if(button.dataset.act==='inline-file-check')await selectUploadedFile(root);
  else root.querySelector('[data-inline-file-panel]').hidden=true;
 }catch(error){if(root.isConnected)root.querySelector('[data-inline-file-status]').textContent=error.message;}finally{
  if(button.isConnected){const lock=inlineFileUploads.get(inlineFileUploadScope(root));if(lock){lock.controls.set(button,priorDisabled);button.disabled=true;}else button.disabled=priorDisabled;}
 }
});
