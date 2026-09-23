'use strict';
async function fileScanDialog(id){
 const data=await api(`/api/flow/files/${id}/security`),security=data.security;
 const row=state.row?.files?.find(f=>f.id===id);
 const role=state.user.role;
 const canScan=canWrite()&&role!=='auditor'&&(!row||(!['receipt','invoice'].includes(row.category)||['admin','manager','finance'].includes(role)))&&(!row||!row.category.startsWith('signed_')||['admin','manager','sales'].includes(role));
 const request_id=requestKey();
 modal('文件扫描与隔离',`<form><div class="notice ${security.can_use?'':'warn'}"><strong>${E(security.label)}</strong><p>${E(security.message)}</p></div>${table(['时间','结果','扫描引擎'],data.scans.map(x=>[time(x.occurred_at),E(x.label),E(x.engine_version||x.engine)]))}<div class="formerror" role="alert"></div><div class="modalfoot">${b('close','关闭')}${canScan?'<button type="submit" class="primary">重新扫描</button>':''}</div></form>`,async()=>{await api(`/api/flow/files/${id}/scan`,{method:'POST',body:{request_id,version:security.version}});closeModal();await render();toast('扫描结果已记录');});
}
