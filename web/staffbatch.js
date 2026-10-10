'use strict';
// Batch staff creation. The server owns the current store/account scope, every row rule and the
// single transaction; this file only parses the paste, previews it and reports server messages.
const STAFF_BATCH_LIMIT=50;
const STAFF_BATCH_ROLE_ALIASES={
 库存管理员:'inventory',库管:'inventory',仓管:'inventory',
 售后:'service',售后保险:'service',服务:'service',
 前台:'reception',前台接待:'reception',接待:'reception',
 技师:'technician',维修技师:'technician',维修:'technician',
 客服:'customer_service',客户服务:'customer_service',客户服务专员:'customer_service',
 审计:'auditor',复核:'auditor',复核审计:'auditor',
 店长:'manager',销售经理:'manager',销售顾问:'sales',内勤:'clerk',销售内勤:'clerk',财务:'finance',收银:'finance',
 系统管理员:'admin',管理员:'admin',门店管理员:'store_admin',
};
const staffBatchUsername=/^[a-zA-Z0-9_.-]{3,40}$/;
function staffBatchRole(value){
 const raw=String(value||'').trim();
 if(!raw)return '';
 if(recordAccountRoles.includes(raw))return raw;
 if(STAFF_BATCH_ROLE_ALIASES[raw]&&recordAccountRoles.includes(STAFF_BATCH_ROLE_ALIASES[raw]))return STAFF_BATCH_ROLE_ALIASES[raw];
 const lower=raw.toLowerCase();
 for(const [code,label] of Object.entries(roleNames)){if(recordAccountRoles.includes(code)&&(label===raw||code===lower))return code;}
 return '';
}
function staffBatchFields(line){
 if(/[|｜\t,，]/.test(line))return line.split(/[|｜\t,，]/).map(x=>x.trim());
 return line.split(/ {2,}/).map(x=>x.trim());
}
function staffBatchAllowedRoles(){return accountAssignableRoles().filter(role=>role!=='admin');}
function staffBatchParse(text,existing=[]){
 const rows=[];const taken=new Set(existing.map(name=>String(name).toLowerCase()));const seen=new Set(),allowed=staffBatchAllowedRoles();
 const lines=String(text||'').split(/\r?\n/).map(line=>line.trim()).filter(Boolean);
 lines.forEach((line,index)=>{
  const number=index+1,fields=staffBatchFields(line),row={number,line,display_name:'',username:'',role:'',error:''};
  if(fields.length!==3){row.error='每行要三段：员工姓名｜登录账号｜岗位';rows.push(row);return;}
  const looks=value=>staffBatchUsername.test(value);
  if(looks(fields[0])&&!looks(fields[1])){[row.username,row.display_name]=[fields[0],fields[1]];}
  else{[row.display_name,row.username]=[fields[0],fields[1]];}
  const role=staffBatchRole(fields[2]);
  row.role=role||fields[2];
  if(!row.display_name)row.error='员工姓名不能为空';
  else if(!staffBatchUsername.test(row.username))row.error='登录账号只能填 3–40 位字母、数字、下划线、点或短横线';
  else if(role==='admin'&&accountCapabilities().scope==='global')row.error='系统管理员账号请用“新增员工”单独建立';
  else if(!role||!allowed.includes(role))row.error='岗位“'+fields[2]+'”不在可分配范围；可选'+allowed.map(code=>roleNames[code]).join('、');
  else if(seen.has(row.username.toLowerCase()))row.error='登录账号在本批里重复了';
  else if(taken.has(row.username.toLowerCase()))row.error='登录账号已经存在';
  if(!row.error)seen.add(row.username.toLowerCase());
  rows.push(row);
 });
 return {rows,tooMany:lines.length>STAFF_BATCH_LIMIT};
}
function staffBatchButton(){return b('batchusers','批量新增员工');}
function staffBatchPreview(target,parsed){
 const {rows,tooMany}=parsed;
 if(!rows.length){target.innerHTML='<p class="fieldhelp">还没有内容。每行填一条：员工姓名｜登录账号｜岗位。</p>';return false;}
 const bad=rows.filter(row=>row.error);
 const body=rows.map(row=>`<tr><td>${row.number}</td><td>${E(row.display_name||'—')}</td><td>${E(row.username||'—')}</td><td>${E(roleNames[row.role]||row.role||'—')}</td><td>${row.error?`<span class="formerror">${E(row.error)}</span>`:pill('done','可以建立')}</td></tr>`).join('');
 target.innerHTML=`<h3>核对名单</h3><div class="tablewrap"><table><thead><tr><th>行</th><th>员工姓名</th><th>登录账号</th><th>岗位</th><th>检查</th></tr></thead><tbody>${body}</tbody></table></div>`+
  `<p class="${bad.length||tooMany?'formerror':'fieldhelp'}">共 ${rows.length} 行${bad.length?`，其中 ${bad.length} 行要先改好`:'，都可以建立'}${tooMany?`；一次最多 ${STAFF_BATCH_LIMIT} 行`:''}。</p>`;
 return !bad.length&&!tooMany;
}
function staffBatchDialog(){
 const caps=accountCapabilities(),local=caps.scope==='store';
 if(!state.user?.can_users||caps.batch!==true)throw new Error('当前岗位没有批量新增员工的权限。');
 if(local&&String(caps.store_id)!==String(state.store))throw new Error('门店授权已变化，请刷新员工列表。');
 const stores=(state.accountData?.stores||[]).filter(store=>store.active!==false&&(!local||store.id===caps.store_id));
 if(!stores.length)throw new Error('没有可分配的门店，请刷新员工列表。');
 const options=stores.map(store=>`<option value="${store.id}" ${String(store.id)===String(state.store)?'selected':''}>${E(store.name)}</option>`).join('');
 const existing=(state.accountData?.items||[]).map(row=>row.username);
 const allowed=staffBatchAllowedRoles().map(code=>roleNames[code]).join('、');
 const dialog=modal('批量新增员工',`<form><div class="notice">每行一条：<strong>员工姓名｜登录账号｜岗位</strong>。可分配岗位：${E(allowed)}。本次账号共用一个初始密码，每人首次登录必须自己改；本人改密前不要把初始密码转告他人，建好后尽快让本人登录改密。${local?'本次只分配当前门店，不授予集团汇总。':'系统管理员账号请用“新增员工”单独建立。'}</div><div class="formgrid"><label class="wide">粘贴名单<textarea name="rows" rows="7" placeholder="示例员工｜demo-sales｜销售"></textarea></label></div><div id="staff-batch-preview" class="mt15"></div><div class="formgrid mt18"><label>本次分配门店<select name="store_id" ${local?'disabled':''}>${options}</select></label><label>初始密码（12 位以上，输入时不显示）<input name="password" type="password" minlength="12" maxlength="128" autocomplete="new-password"></label></div><div class="mt15 formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button type="submit" class="primary" disabled>确认新增</button></div></form>`,async form=>{
  try{
   const parsed=staffBatchParse(form.elements.rows.value,existing);
   const bad=parsed.rows.filter(row=>row.error);
   if(!parsed.rows.length)throw new Error('请先粘贴名单。');
   if(bad.length)throw new Error('第 '+bad[0].number+' 行：'+bad[0].error);
   if(parsed.tooMany)throw new Error(`一次最多 ${STAFF_BATCH_LIMIT} 行，请分两次办理。`);
   if((form.elements.password.value||'').length<12)throw new Error('初始密码至少 12 位。');
   const result=await api('/api/users/batch',{method:'POST',body:{store_id:local?caps.store_id:Number(form.elements.store_id.value),password:form.elements.password.value,rows:parsed.rows.map(row=>({username:row.username,display_name:row.display_name,role:row.role}))}});
   closeModal();await render();
   toast(`已新增 ${result.count} 个账号；把初始密码交给本人，首次登录必须改密。`);
  }catch(error){refreshPreview();throw error;}
 });
 const form=dialog.querySelector('form'),preview=dialog.querySelector('#staff-batch-preview'),submit=dialog.querySelector('button[type=submit]');
 function refreshPreview(){const ok=staffBatchPreview(preview,staffBatchParse(form.elements.rows.value,existing));submit.disabled=!ok;return ok;}
 form.elements.rows.addEventListener('input',refreshPreview);
 refreshPreview();
}
