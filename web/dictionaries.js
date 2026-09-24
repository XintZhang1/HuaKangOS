'use strict';
// Store dictionaries are descriptive data, never executable state/permission rules.
let dictionaryUI={};
function clearDictionariesSession(){dictionaryUI={};}
function dictionaryContext(group){const key=[state.user?.id,state.store,group].join(':');if(dictionaryUI.key!==key)dictionaryUI={key,group};return dictionaryUI;}
async function dictionariesPage(group){
 const catalog=await api('/api/dictionaries/catalog');
 if(!group)return heading('分类设置',catalog.notice)+storeNotice()+`<div class="chartgrid">${Object.entries(catalog.groups).map(([key,value])=>panel(value.label,`<p>本店条目的名称、说明与启停。</p>${b('open','进入字典',`data-route="dictionaries/${E(key)}"`)}${catalog.can_write?b('dictionary-new','新增',`data-group="${E(key)}"`,'primary'):''}`)).join('')}</div>`;
 if(!catalog.groups[group])throw new Error('字典类别不存在。');
 if(state.store==='all')return heading(catalog.groups[group].label)+storeNotice()+'<div class="notice">请选择具体门店查看和维护字典。</div>';
 const context=dictionaryContext(group),result=await api('/api/dictionaries/'+encodeURIComponent(group)+'?'+new URLSearchParams({q:state.q||'',page:state.page||1}));
 if(context.key!==[state.user?.id,state.store,group].join(':'))throw new Error('门店或账号已切换，请重新读取。');
 context.rows=result.items;context.canWrite=result.can_write;context.label=result.label;
 return heading(result.label,result.notice,b('open','全部字典','data-route="dictionaries"')+(result.can_write?b('dictionary-new','新增条目',`data-group="${E(group)}"`,'primary'):''))+storeNotice()+searchBar()+panel('本店条目',table(['名称','说明','状态','操作'],result.items.map(row=>[E(row.name),E(row.detail),row.active?'启用':'停用',result.can_write?b('dictionary-edit','编辑',`data-group="${E(group)}" data-id="${row.id}"`):'只读'])))+pager(result.total);
}
async function dictionaryDialog(group,id){
 const context=dictionaryContext(group),identity=context.key,catalog=await api('/api/dictionaries/catalog');
 if(identity!==[state.user?.id,state.store,group].join(':'))throw new Error('账号或门店已变化，请重新打开。');
 if(!catalog.groups[group]||!catalog.can_write)throw new Error('当前岗位没有本店字典维护权限。');
 const row=id?context.rows?.find(item=>item.id===id):null;if(id&&!row)throw new Error('请回到原字典刷新后再编辑。');
 const request_id=requestKey();
 modal((row?'编辑':'新增')+catalog.groups[group].label,`<form><p class="notice">${E(catalog.notice)}</p><label>名称<input name="name" required maxlength="120" value="${E(row?.name||'')}"></label><label>说明<textarea name="detail" maxlength="2000" rows="4">${E(row?.detail||'')}</textarea></label><label class="checklabel"><input type="checkbox" name="active" ${row?.active!==false?'checked':''}>启用</label><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button class="primary" type="submit">确认保存</button></div></form>`,async form=>{
  if(identity!==[state.user?.id,state.store,group].join(':'))throw new Error('账号或门店已变化，请关闭后重新打开。');
  const fd=new FormData(form),values={name:String(fd.get('name')||'').trim(),detail:String(fd.get('detail')||'').trim(),active:fd.has('active')};
  await api('/api/dictionaries/'+group+(row?'/'+row.id:''),{method:row?'PUT':'POST',body:{request_id,...(row?{version:row.version}:{}),values}});
  closeModal();await render();toast('本店字典条目已保存');
 });
}
document.addEventListener('click',async event=>{const el=event.target.closest('[data-act]');if(!el||el.disabled||!['dictionary-new','dictionary-edit'].includes(el.dataset.act))return;el.disabled=true;try{await dictionaryDialog(el.dataset.group,Number(el.dataset.id)||null);}catch(error){toast(error.message,true);}finally{if(el.isConnected)el.disabled=false;}});
