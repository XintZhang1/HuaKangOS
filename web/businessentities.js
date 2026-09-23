'use strict';
let businessEntityUI={};
function clearBusinessEntitiesSession(){businessEntityUI={};}
function beContext(){const key=String(state.user?.id)+':'+state.store;if(businessEntityUI.key!==key)businessEntityUI={key};return businessEntityUI;}
const beOperations={revision:'主体资料版本',store_binding:'门店主体绑定',account_binding:'资金账户主体绑定',policy:'启用新业务主体冻结'};
const beActions={submit:'提交来源资料',approve:'独立批准生效',reject:'拒绝申请',cancel:'取消未生效申请',reassign:'转交复核待办'};
const beStates={draft:'待提交',approval:'待独立复核',completed:'已生效',rejected:'已拒绝',cancelled:'已取消'};
const beFields={code:'主体编码',tax_identifier:'主体识别号',legal_name:'主体法定名称',registered_address:'登记地址',contact_phone:'联系号码',entity_id:'原主体编号',expected_entity_version:'原主体版本',revision_id:'批准资料版本编号',effective_from:'生效日',account_id:'本店账户编号',expected_account_version:'原账户版本',holder_name:'实际户名',channel_type:'账户类型',channel_identifier:'实际账户 / 渠道标识',institution_name:'银行或渠道机构',binding_id:'本店批准绑定编号',policy_version:'冻结策略版本'};
function beLegal(entity){return entity?facts({'法定名称':entity.legal_name,'主体识别号':entity.tax_identifier,'资料版本':entity.revision,'登记地址':entity.registered_address}):'<div class="notice warn">尚未批准经营主体；“华慷集团”产品名称不能代替实际经营主体。</div>';}
async function businessEntitiesPage(){
 const c=beContext(),catalog=await api('/api/business-entities/catalog');
 if(!catalog.can_read)return heading('经营主体与账户归属')+'<div class="notice">请切换到获权的具体门店。</div>';
 const data=await api('/api/business-entities/configuration'),list=await api('/api/business-entities/applications');c.configuration=data;
 const buttons=catalog.can_create?Object.entries(beOperations).map(([key,label])=>b('be-new','申请'+label,`data-kind="${key}"`)).join(''):'';
 return heading('经营主体与账户归属','管理员提出来源资料，另一名主管独立核对批准。',buttons)+
 `<div class="notice warn">${E(data.limitation)}</div>`+panel('本店当前批准主体',beLegal(data.store_binding?.entity)+facts({'生效日':data.store_binding?.effective_from,'新业务冻结':data.policy?'已批准启用；原业务归属继续保留':'尚未启用，历史归属不会自动补填'}))+
 panel('实际资金账户',data.accounts.map(a=>`<div class="card">${facts({'账户':a.name,'状态':a.active?'启用':'停用','批准户名':a.binding?.holder_name||'尚未批准','渠道':a.binding?.channel_identifier||'尚未批准','资料版本编号':a.binding?.revision_id})}</div>`).join('')||'<p>尚无本店资金账户。</p>')+
 panel('切换为另一主体前的检查',data.switch_blockers.length?data.switch_blockers.map(r=>`<p class="notice warn">${E(r)}</p>`).join(''):'<p>当前基础检查未发现资金、库存或未结业务阻挡；批准时会再次检查。</p>')+
 panel('本店申请与处理',table(['申请','事项','状态','办理'],list.items.map(r=>[E(r.number),E(r.title),E(beStates[r.state]||r.state),b('open','打开',`data-route="business-entity/${r.id}"`)])));
}
async function businessEntityPage(id){
 const c=beContext(),row=await api('/api/business-entities/applications/'+id);c.row=row;state.row=await api('/api/flow/cases/'+id);
 let html=heading(beOperations[row.operation],row.number,b('open','返回主体配置','data-route="business-entities"'));
 const details={...row.details};if(details.channel_type)details.channel_type={bank:'银行账户',cash:'现金存放处',wallet:'电子钱包'}[details.channel_type]||details.channel_type;
 html+=panel('本次申请原资料',facts({'状态':beStates[row.state]||row.state,'申请说明':row.reason,'要求处理日期':row.due_date})+facts(details,beFields));
 if(row.state==='completed')html+='<div class="notice">本次配置已独立批准生效。原资料版本、原业务归属和原文件继续保留；变更须另提申请。</div>';
 if(row.state==='approval')html+='<div class="notice">待主管核对。申请与复核须为两个人；批准不是工商认证，也不会迁改历史经营账。</div>';
 html+=panel('本人当前办理',row.actions.length?'<div class="row">'+row.actions.map(a=>b('be-action',beActions[a],`data-key="${a}"`)).join('')+'</div>':'当前没有本人可办理动作。');
 html+=panel('本单实际资料与核对凭据',b('upload','上传本人来源或核对凭据')+fileList(state.row.files||[]));
 html+=panel('责任与期限',table(['待办','负责人','期限','状态'],(state.row.tasks||[]).map(t=>[E(t.title),E(t.assignee_name),E(t.due_date),E(t.status==='open'?(t.due_date<day()?'已逾期，需明确交接':'待本人办理'):t.status==='done'?'已完成':'已取消')])));
 if(row.decision)html+=panel('终态决议',facts({'结果':{approved:'批准',rejected:'拒绝',cancelled:'取消'}[row.decision.decision],'处理说明':row.decision.reason,'时间':time(row.decision.occurred_at)}));
 return html;
}
function beInput(key,required=true,value='',type='text'){return `<label>${E(beFields[key]||key)}<input name="${key}" type="${type}" value="${E(value)}" ${required?'required':''} maxlength="${key==='registered_address'?300:180}"></label>`;}
async function beNew(operation){
 const c=beContext(),session=c.key,cfg=await api('/api/business-entities/configuration'),request_id=requestKey();let html='';
 const revisions=cfg.revisions,options=revisions.map(r=>`<option value="${r.revision_id}">${E(r.legal_name+' · 资料版本 '+r.revision+' · '+r.code)}</option>`).join('');
 if(operation==='revision'){
  html=`<label>申请类型<select name="original"><option value="">建立新的独立主体</option>${revisions.filter((r,i,a)=>!a.some(x=>x.entity_id===r.entity_id&&x.revision>r.revision)).map(r=>`<option value="${r.revision_id}">${E('修订 '+r.legal_name+' · '+r.code)}</option>`).join('')}</select></label>`+['code','tax_identifier','legal_name','registered_address'].map(k=>beInput(k)).join('')+beInput('contact_phone',false)+'<p>请按实际来源填写。系统只作格式与重复校验，不代表工商认证。更换主体识别号须另建独立主体。</p>';
 }else if(operation==='store_binding'){
  if(!revisions.length)throw new Error('请先完成主体资料版本的独立批准。');
  html=`<label>使用已批准资料<select name="revision_id">${options}</select></label>`+beInput('effective_from',true,day(),'date')+'<p>本版仅批准当日生效。首次绑定只配置后续业务，既有历史仍为未知；换成另一主体必须核清资金、库存与未结业务。</p>';
 }else if(operation==='account_binding'){
  const accounts=cfg.accounts.filter(a=>a.active);if(!cfg.store_binding||!accounts.length)throw new Error('请先批准本店主体并建立本店实际资金账户。');
  html=`<label>本店资金账户<select name="account_id">${accounts.map(a=>`<option value="${a.id}">${E(a.name)}</option>`).join('')}</select></label><label>已批准主体资料<select name="revision_id">${revisions.filter(r=>r.entity_id===cfg.store_binding.entity.entity_id).map(r=>`<option value="${r.revision_id}">${E(r.legal_name+' · 版本 '+r.revision)}</option>`).join('')}</select></label>`+beInput('holder_name')+beInput('channel_identifier')+beInput('institution_name')+beInput('effective_from',true,day(),'date')+'<p>实际户名须与选定主体名称一致；不要把本店代收关系猜成别店账户所有权。</p>';
 }else{
  if(!cfg.store_binding)throw new Error('请先批准本店经营主体。');
  html=beLegal(cfg.store_binding.entity)+`<div class="notice warn">${E(cfg.limitation)}</div><p>批准时冻结历史编号界限。原业务和原现金仍保留未知，不会追溯认领。</p><label class="checklabel"><input name="ack" type="checkbox" required>已核对本店与全部启用资金账户的批准资料</label>`;
 }
 html+=`<label>申请说明<textarea name="reason" required minlength="2" maxlength="1000"></textarea></label><label>复核期限<input name="due_date" type="date" required value="${day()}"></label>`;
 modal('申请'+beOperations[operation],`<form>${html}<div class="formerror" role="alert"></div><div class="modalfoot">${b('close','返回核对')}<button type="submit" class="primary">保存申请后上传来源</button></div></form>`,async form=>{
  if(beContext().key!==session)throw new Error('门店或账号已改变，请重新打开配置。');
  const f=form.elements,v={};
  if(operation==='revision'){
   for(const k of ['code','tax_identifier','legal_name','registered_address','contact_phone'])v[k]=f[k].value.trim();v.code=v.code.toUpperCase();v.tax_identifier=v.tax_identifier.toUpperCase();
   if(f.original.value){const original=revisions.find(r=>r.revision_id===Number(f.original.value));v.entity_id=original.entity_id;v.expected_entity_version=original.entity_version;}
  }else if(operation==='store_binding'){v.revision_id=Number(f.revision_id.value);v.effective_from=f.effective_from.value;}
  else if(operation==='account_binding'){
   const account=cfg.accounts.find(a=>a.id===Number(f.account_id.value));Object.assign(v,{account_id:account.id,expected_account_version:account.version,channel_type:account.account_type,revision_id:Number(f.revision_id.value),effective_from:f.effective_from.value});
   for(const k of ['holder_name','channel_identifier','institution_name'])v[k]=f[k].value.trim();
  }else Object.assign(v,{binding_id:cfg.store_binding.id,policy_version:1});
  const row=await api('/api/business-entities/applications',{method:'POST',body:{request_id,operation,details:v,reason:f.reason.value,due_date:f.due_date.value}});closeModal();go('business-entity/'+row.id);
 });
 if(operation==='revision')$('#modal [name=original]').addEventListener('change',event=>{const r=revisions.find(r=>r.revision_id===Number(event.target.value));for(const k of ['code','tax_identifier','legal_name','registered_address','contact_phone'])$('#modal [name='+k+']').value=r?.[k]||'';for(const k of ['code','tax_identifier'])$('#modal [name='+k+']').readOnly=!!r;});
}
async function beAction(action){
 const c=beContext(),row=c.row,session=c.key,request_id=requestKey();if(!row)throw new Error('请重新打开本店主体申请。');let html='';
 if(['submit','approve'].includes(action)){
  const files=(state.row.files||[]).filter(f=>!f.generated&&f.security?.can_use&&row.own_file_ids.includes(f.id));
  if(!files.length)throw new Error('请先上传本人本单实际资料，并通过文件检查后再办理。');
  html=`<label>本人核对凭据<select name="evidence_id">${files.map(f=>`<option value="${f.id}">${E(f.name)}</option>`).join('')}</select></label>`;
  if(action==='approve')html+='<div class="notice warn">请独立核对本申请资料。批准后保留不可覆盖版本，不迁改历史业务。</div>';
 }else html='<label>本人处理说明<textarea name="reason" required minlength="2" maxlength="1000"></textarea></label>';
 if(action==='reassign'){
  const employees=await api('/api/flow/lookup/employee');html+=`<label>当前待办<select name="task_id">${row.tasks.filter(t=>t.status==='open').map(t=>`<option value="${t.id}">${E(t.title)}</option>`).join('')}</select></label><label>下一位本店主管<select name="assignee_id">${employees.items.map(u=>`<option value="${u.id}">${E(u.label)}</option>`).join('')}</select></label><label>处理期限<input type="date" name="due_date" required value="${day()}"></label>`;
 }
 modal(beActions[action],`<form>${html}<div class="formerror" role="alert"></div><div class="modalfoot">${b('close','返回核对')}<button type="submit" class="primary">确认本人办理</button></div></form>`,async form=>{
  if(beContext().key!==session)throw new Error('门店或账号已改变，请重新核对。');const f=form.elements,values={};
  if(f.evidence_id)values.evidence_id=Number(f.evidence_id.value);if(f.reason)values.reason=f.reason.value;
  if(action==='reassign')Object.assign(values,{task_id:Number(f.task_id.value),assignee_id:Number(f.assignee_id.value),due_date:f.due_date.value});
  await api(`/api/business-entities/applications/${row.id}/actions/${action}`,{method:'POST',body:{request_id,version:row.version,values}});closeModal();await render();
 });
}
document.addEventListener('click',async event=>{const el=event.target.closest('[data-act]');if(!el?.dataset.act.startsWith('be-'))return;try{if(el.dataset.act==='be-new')await beNew(el.dataset.kind);if(el.dataset.act==='be-action')await beAction(el.dataset.key);}catch(error){toast(error.message,true);}});
