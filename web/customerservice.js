'use strict';
let customerServiceUI={};
function clearCustomerServiceSession(){customerServiceUI={};}
function careContext(){const key=String(state.user?.id)+':'+state.store;if(customerServiceUI.key!==key)customerServiceUI={key};return customerServiceUI;}
async function careCatalog(){const c=careContext();if(!c.catalog)c.catalog=await api('/api/customer-service/catalog');if(!c.catalog.can_read)throw new Error('请选择门店');return c.catalog;}
const careAPI='/api/customer-service';
const careActionNames={start:'接手办理',followup:'登记跟进',handoff:'交接给同事',close:'登记结案',cancel:'取消本次服务'};
const careLocalLabels={internal:'内部核对',in_person:'当面反馈',phone:'电话跟进',progress:'处理有进展',contacted:'已联系确认',unreachable:'未联系到',declined:'客户不需要',normal:'普通',urgent:'紧急',active:'有效',revoked:'已撤销'};
function careSelect(name,label,items,value='',required=true){return `<label>${E(label)}<select name="${name}" ${required?'required':''}><option value="">请选择</option>${items.map(r=>`<option value="${E(r.id)}" ${String(r.id)===String(value)?'selected':''}>${E(r.label)}</option>`).join('')}</select></label>`;}
function careOptions(values){return Object.entries(values).map(([id,label])=>({id,label}));}
async function careField(name,label,type='text',value='',required=true){return fieldHTML({key:name,label,type,required},value);}
async function careChoices(kind,params={}){return (await api(careAPI+'/lookup/'+kind+'?'+new URLSearchParams(params))).items;}
function careForm(content){return `<form><div class="formgrid">${content}</div><div class="formerror mt15" role="alert"></div><div class="modalfoot">${b('close','取消')}<button class="primary" type="submit">确认保存</button></div></form>`;}
function careInteger(fd,name,nullable=false){const value=fd.get(name);if(nullable&&!value)return null;const n=Number(value);if(!Number.isSafeInteger(n))throw new Error('请填写整数。');return n;}

async function customerServicePage(caseId){
 const c=careContext(),catalog=await careCatalog();
 if(caseId){
  const row=await api(careAPI+'/cases/'+caseId);c.case=row;
  const actions=row.actions.map(a=>b('care-action',careActionNames[a],`data-action="${a}"`,a==='start'?'primary':'')).join('');
  return heading(row.subtype_label+' · '+row.number,row.topic,actions)+(row.reminder_basis?.status==='pending_review'?'<div class="notice warn">本车提醒基准正在独立复核。本任务可接手、内部核对、转交或取消，暂不能外联或按旧基准结案。</div>':row.reminder_basis?.status==='invalidated'?'<div class="notice warn">原提醒基准已失效，原办理记录保留。请查看本车有效来源和明确关联的替代任务。</div>':'')+(row.reminder_basis?.replacement_case_ids?.length?`<div class="row">${row.reminder_basis.replacement_case_ids.map(id=>b('open','查看替代提醒',`data-route="customer-service/${id}"`)).join('')}</div>`:'')+(row.generation_mode==='rule_worker'?'<div class="notice">系统按已批准规则自动生成内部任务。创建者表示规则批准责任归属，不表示本人已点击、联系客户或确认服务完成。</div>':'')+(row.overdue?'<div class="notice warn">此任务已逾期，请记录进展或明确交接；交接保留原到期日。</div>':'')
  +panel('客户诉求与责任',facts({'客户':row.customer_name,'联系电话':row.customer_phone||'未留电话','后续联系':row.contact_allowed?'已允许':'未允许主动后续联系','状态':row.state_label,'经办人':row.assignee_name,'办理期限':row.due_date,'优先程度':careLocalLabels[row.priority],'诉求':row.description,'救援位置':row.location||'—','结案结果':row.result_label||'尚未结案'})+`<div class="row mt15">${row.vehicle_id?b('open','客户车辆与来源',`data-route="customer-vehicles/${row.vehicle_id}"`):''}${b('open','本单附件与凭据',`data-route="case/${row.id}"`)}</div>`)
  +(row.questionnaire?careQuestionnaireOriginal(row.questionnaire):'')
  +panel('办理记录',row.records.length?row.records.map(r=>`<article class="notice mt15"><strong>${E(careActionNames[r.action]||'建立服务')} · ${E(time(r.created_at))}</strong><p>${E(r.note)}</p>${r.details.channel?`<p>${E(careLocalLabels[r.details.channel])} · ${E(careLocalLabels[r.details.contact_result])}</p>`:''}${r.details.satisfaction!==null&&r.details.satisfaction!==undefined?`<p>原问卷 v1：满意度 ${E(r.details.satisfaction)} / 5；${r.details.recommend===true?'愿意推荐':r.details.recommend===false?'暂不推荐':'未回答推荐题'}</p>`:''}${r.details.questionnaire_version?`<p>回答已绑定发放版本 v${E(r.details.questionnaire_version)}；详见原题与回答。</p>`:''}${r.details.was_overdue?`<p>交接前已逾期，原办理期限 ${E(r.details.previous_due_date)}</p>`:''}</article>`).join(''):empty());
 }
 const params=new URLSearchParams({page:state.page,q:c.query||'',subtype:c.subtype||'',status:c.status||''}),d=await api(careAPI+'/cases?'+params);c.rows=d.items;
 const create=Object.keys(catalog.create_types).length?`<div class="row">${careSelect('care_create_type','服务类型',careOptions(catalog.create_types),Object.keys(catalog.create_types)[0])}${b('care-new','登记客户服务','','primary')}</div>`:'';
 return heading('客户服务工作台','咨询、投诉、救援与回访按责任人办理。提醒只建立内部待办，不发送外部消息。',create)
 +`<form id="care-filters" class="filterbar"><label>搜索<input name="q" value="${E(c.query||'')}" placeholder="主题或服务单号"></label>${careSelect('subtype','服务类型',careOptions(catalog.types),c.subtype||'',false)}${careSelect('status','状态',[{id:'open',label:'未结案'},...careOptions(catalog.states)],c.status||'',false)}<button class="primary" type="submit">查询</button></form>`
 +panel('服务任务',table(['客户','服务','主题','状态','责任人','到期','操作'],d.items.map(r=>[E(r.customer_name),E(r.subtype_label),E(r.topic),pill(r.overdue?'overdue':r.state,r.overdue?'已逾期 · '+r.state_label:r.state_label),E(r.assignee_name),E(r.due_date),b('open','办理',`data-route="customer-service/${r.id}"`)]))+pager(d.total));
}

async function careNewDialog(subtype,customerId=null,vehicleId=null){
 const catalog=await careCatalog();if(!catalog.create_types[subtype])throw new Error('当前岗位不能登记此服务。');
 const customers=await careChoices('customers'),people=await careChoices('employees',{subtype}),vehicles=customerId?await careChoices('vehicles',{customer_id:customerId}):[];
 const source=subtype==='sales_callback'||subtype==='repair_callback';
 const fields=careSelect('customer_id','客户',customers,customerId||'')+careSelect('vehicle_id','关联客户车辆',vehicles,vehicleId||'',false)
 +(source?careSelect('source_case_id','已交付或完工原单',customerId?await careChoices('source_cases',{subtype,customer_id:customerId}):[]):'')
 +await careField('topic','本次主题')+await careField('description','客户诉求与已知情况','textarea')
 +(subtype==='rescue'?await careField('location','客户提供的救援位置','textarea'):'')
 +careSelect('priority','优先程度',careOptions({normal:'普通',urgent:'紧急'}),'normal')
 +careSelect('assignee_id','经办人',people,people.some(p=>p.id===state.user.id)?state.user.id:people[0]?.id)
 +await careField('due_date','办理期限','future_date',day());
 const request_id=requestKey();
 modal('登记'+catalog.types[subtype],careForm(fields),async form=>{const fd=new FormData(form);const r=await api(careAPI+'/cases',{method:'POST',body:{request_id,values:{customer_id:careInteger(fd,'customer_id'),vehicle_id:careInteger(fd,'vehicle_id',true),subtype,
  source_case_id:source?careInteger(fd,'source_case_id'):null,topic:fd.get('topic'),description:fd.get('description'),location:fd.get('location')||'',priority:fd.get('priority'),assignee_id:careInteger(fd,'assignee_id'),due_date:fd.get('due_date')}}});closeModal();go('customer-service/'+r.case.id);});
 $('#modal [name=customer_id]').onchange=async event=>{try{const id=event.target.value;const choices=id?await careChoices('vehicles',{customer_id:id}):[];$('#modal [name=vehicle_id]').innerHTML='<option value="">请选择</option>'+choices.map(r=>`<option value="${r.id}">${E(r.label)}</option>`).join('');if(source){const rows=id?await careChoices('source_cases',{subtype,customer_id:id}):[];$('#modal [name=source_case_id]').innerHTML='<option value="">请选择</option>'+rows.map(r=>`<option value="${r.id}">${E(r.label)}</option>`).join('');}}catch(error){$('#modal .formerror').textContent=error.message;}};
}

async function careActionDialog(action){
 const row=careContext().case;if(!row?.actions.includes(action))throw new Error('当前责任人或状态不能执行此操作。');
 let fields='';
 if(action==='start')fields='<p>确认由你接手，并记录实际办理进展。</p>';
 if(action==='followup')fields=careSelect('channel','本次方式',careOptions(Object.fromEntries(Object.entries({internal:'内部核对',in_person:'当面反馈',phone:'电话跟进'}).filter(([k])=>!row.followup_channels||row.followup_channels.includes(k)))),'internal')+careSelect('contact_result','进展',careOptions({progress:'处理有进展',contacted:'已联系确认',unreachable:'未联系到',declined:'客户不需要'}),'progress')+await careField('note','实际进展与客户反馈','textarea')+await careField('next_due_date','下一次办理日期','future_date','',false);
 if(action==='handoff')fields=careSelect('assignee_id','接手同事',await careChoices('employees',{subtype:row.subtype}))+await careField('due_date','新的办理期限','future_date',day())+await careField('reason','交接内容与原因','textarea');
 if(action==='cancel')fields=await careField('reason','取消原因','textarea');
 if(action==='close'){
  const results={...(await careCatalog()).results};if(row.subtype!=='renewal')delete results.renewed;
  fields=careSelect('result','实际结果',careOptions(results),'resolved')+await careField('note','结果依据及后续约定','textarea');
  if(row.subtype==='questionnaire'){if(!row.questionnaire)throw new Error('原发放题目缺失，请刷新核对，不能套用新问卷。');fields+=`<div class="notice">按原发放版本 v${E(row.questionnaire.number)} 填写。选择已解决时须回答全部必答题；其余结果可保留部分回答。留空不表示否或0。</div>`+row.questionnaire.questions.map(careQuestionAnswerField).join('');}
 }
 const request_id=requestKey();modal(careActionNames[action],careForm(fields),async form=>{
  const fd=new FormData(form),values={};for(const [key,value]of fd.entries())values[key]=value;
  if(action==='followup')values.next_due_date=values.next_due_date||null;
  if(action==='handoff')values.assignee_id=careInteger(fd,'assignee_id');
  if(action==='close'){
   values.satisfaction=null;values.recommend=null;
   if(row.subtype==='questionnaire'){
    values.answers={};for(const q of row.questionnaire.questions){const key='answer__'+q.key,raw=fd.get(key);delete values[key];if(raw===null||raw==='')continue;
     if(q.kind==='integer'){if(!/^-?\d+$/.test(raw)||!Number.isSafeInteger(Number(raw)))throw new Error('请在'+q.label+'填写完整整数。');values.answers[q.key]=Number(raw);}
     else if(q.kind==='boolean')values.answers[q.key]=raw==='yes';else values.answers[q.key]=raw.trim();
    }
   }
  }
  await api(careAPI+`/cases/${row.id}/actions/${action}`,{method:'POST',body:{request_id,version:row.version,values}});closeModal();await render();toast('办理记录已保存');
 });
}

async function customerVehiclesPage(id){
 const c=careContext(),catalog=await careCatalog();
 if(id){const d=await api(careAPI+'/vehicles/'+id),row=d.vehicle;c.vehicle=row;const history=await api(careAPI+`/vehicles/${id}/history`);
  return heading('客户车辆 · '+(row.plate||row.vin),row.customer_name+' · '+row.model_name,(catalog.can_write?b('care-observe','登记日期与里程','','primary')+' '+b('care-vehicle-edit','维护关系'):'')+' '+b('open','原观察纠错与有效版本',`data-route="observation-corrections/vehicles/${row.id}"`))
  +panel('身份与本店关系',facts({'客户':row.customer_name,'联系电话':row.customer_phone||'未留电话','VIN':row.vin,'本店车辆关系编号':row.id,'集团客户身份编号':row.customer_identity_id,'关系来源':row.identity_source,'状态':row.active?'启用':'停用','最近里程':row.odometer_km===null?'尚未登记':row.odometer_km+' 公里','实际观察日期':row.observed_date||'尚无实测来源'})+`<div class="row mt15">${catalog.can_write?b('care-new-vehicle-case','登记本车咨询')+' '+b('care-history-link','关联本店服务摘要'):''}</div>`)
  +panel('日期与里程来源',d.observations.length?d.observations.map(o=>{const effective=(d.effective_observations||[]).find(e=>e.id===o.id);return `<article class="notice mt15"><strong>${E(catalog.observation_types[o.kind])} · 原登记 ${E(o.observed_date)}</strong><p>${effective?.odometer_measured===false?'本条没有独立实测里程':`原记录 ${number(o.odometer_km)} 公里`}${o.valid_until?' · 原截止 '+E(o.valid_until):''}</p><p>原来源：${E(o.source_reference)}</p>${effective&&!effective.active?'<p>原观察已失效，不再驱动提醒；历史记录保留。</p>':effective?.effect_id?`<p>有效纠正 ${effective.effect_id}：${E(effective.observed_date)} · ${number(effective.odometer_km)} 公里${effective.valid_until?' · 截止 '+E(effective.valid_until):''}</p>`:''}</article>`;}).join(''):empty('尚无日期里程来源','登记实际数据后才能据此产生保养、首保或续保提醒。'))
  +panel('获准服务历史',`<p>${E(history.notice)}</p>`+(history.items.length?history.items.map(r=>`<article class="notice mt15"><strong>${E(r.store_name)} · ${E(r.business_date)} ${r.external?' · 已授权跨店摘要':''}</strong><p>${E(r.summary)}</p><small>${E(r.number)}</small>${r.case_id?`<div class="mt15">${b('open','本店原单',`data-route="${r.kind==='customer_care'?'customer-service':'case'}/${r.case_id}"`)}</div>`:''}</article>`).join(''):empty('暂无获准服务摘要')));
 }
 const d=await api(careAPI+'/vehicles?'+new URLSearchParams({page:state.page,q:state.q}));c.vehicles=d.items;
 return heading('客户车辆档案','客户车辆与整车库存分开；VIN 共享不会自动开放别店业务。',catalog.can_write?b('care-vehicle-new','登记客户车辆','','primary')+' '+b('open','客户档案','data-route="master/customers"'):'')+searchBar()+panel('本店客户车辆',table(['客户','车牌','VIN','车型','里程','状态','操作'],d.items.map(r=>[E(r.customer_name),E(r.plate||'未登记'),E(r.vin),E(r.model_name),r.odometer_km??'未登记',r.active?'启用':'停用',b('open','查看',`data-route="customer-vehicles/${r.id}"`)]))+pager(d.total));
}

async function careVehicleDialog(edit=false){
 const c=careContext(),row=edit?c.vehicle:null;
 let fields=edit?'':careSelect('customer_id','本店客户',await careChoices('customers'))+await careField('vin','VIN（17位）')+await careField('customer_identity_id','已有集团客户身份编号（可选）','int','',false);
 fields+=await careField('plate','车牌','text',row?.plate||'',false)+await careField('model_name','车型','text',row?.model_name||'');
 if(edit)fields+=await careField('active','此客户车辆关系启用','bool',row.active)+await careField('reason','修改原因','textarea');
 else fields+=await careField('source_reference','核对身份及车辆的来源凭据','text')+await careField('confirmed','已核对客户本人及 VIN；选择已有身份时已确认是同一个人','bool',false);
 const request_id=requestKey();modal(edit?'维护客户车辆关系':'登记客户车辆',`<p class="notice">客户无电话或电话相同都不会自动合并。不确定是同一人时保留独立身份。</p>`+careForm(fields),async form=>{
  const fd=new FormData(form),values={plate:fd.get('plate'),model_name:fd.get('model_name')};
  if(edit)Object.assign(values,{active:fd.has('active'),reason:fd.get('reason')});
  else Object.assign(values,{customer_id:careInteger(fd,'customer_id'),customer_identity_id:careInteger(fd,'customer_identity_id',true),vin:fd.get('vin'),source_reference:fd.get('source_reference'),confirmed:fd.has('confirmed')});
  const result=await api(careAPI+'/vehicles'+(edit?'/'+row.id:''),{method:edit?'PUT':'POST',body:{request_id,...(edit?{version:row.version}:{}),values}});closeModal();go('customer-vehicles/'+result.vehicle.id);
 });
}

async function careObservationDialog(){
 const row=careContext().vehicle,catalog=await careCatalog();
 const fields=careSelect('kind','登记事项',careOptions(catalog.observation_types),'odometer')+await careField('observed_date','实际发生日期','date',day())+await careField('odometer_km','当时里程（公里）','int',row.odometer_km??'')+await careField('valid_until','保险或保修截止日期（其他事项留空）','date','',false)+await careField('source_reference','日期与里程来源凭据')+await careField('evidence_id','本店业务附件编号（可选）','int','',false)+await careField('confirmed','已核对实际日期、里程和来源','bool',false);
 const request_id=requestKey();modal('登记日期与里程来源',careForm(fields),async form=>{const fd=new FormData(form);await api(careAPI+`/vehicles/${row.id}/observations`,{method:'POST',body:{request_id,version:row.version,values:{kind:fd.get('kind'),observed_date:fd.get('observed_date'),odometer_km:careInteger(fd,'odometer_km'),valid_until:fd.get('valid_until')||null,source_reference:fd.get('source_reference'),evidence_id:careInteger(fd,'evidence_id',true),confirmed:fd.has('confirmed')}}});closeModal();await render();toast('来源记录已保存');});
}

async function careHistoryLinkDialog(){
 const row=careContext().vehicle,choices=await careChoices('source_cases',{customer_id:row.customer_id});
 const fields=careSelect('case_id','本客户原单',choices)+await careField('summary','可提供的服务内容摘要（不填费用与隐私资料）','textarea')+await careField('source_reference','确认原单与此 VIN 关系的依据')+await careField('confirmed','已核对原单属于此客户及车辆','bool',false);
 const request_id=requestKey();modal('关联本店服务摘要',careForm(fields),async form=>{const fd=new FormData(form);await api(careAPI+`/vehicles/${row.id}/history-links`,{method:'POST',body:{request_id,values:{case_id:careInteger(fd,'case_id'),summary:fd.get('summary'),source_reference:fd.get('source_reference'),confirmed:fd.has('confirmed')}}});closeModal();await render();});
}

async function customerReminderPage(){
 const catalog=await careCatalog();const d=await api(careAPI+'/reminders/rules');careContext().rules=d.items;
 return heading('车辆提醒与续保提取','仅用已登记的日期、里程及来源计算；生成内部任务后，由经办人跟进。',(catalog.can_generate?b('care-generate','检查并生成到期任务','','primary')+' ':'')+b('care-renewals','查看续保跟进'))
 +panel('提醒规则',`<div class="row">${catalog.can_manage?careSelect('care_rule_kind','规则类型',careOptions(Object.fromEntries(['first_service','maintenance','warranty','renewal'].map(k=>[k,catalog.types[k]]))))+b('care-rule-new','建立规则'):''}</div>`+table(['规则','周期天数','周期公里','提前天数','提前公里','状态','操作'],d.items.map(r=>[E(r.name),r.interval_days,r.interval_km,r.lead_days,r.lead_km,r.active?'启用':'停用',catalog.can_manage?b('care-rule-edit','修改',`data-id="${r.id}"`):'只读'])))
 +(careContext().generation?panel('本次检查结果',`<p>新建 ${careContext().generation.created.length} 条内部任务；${careContext().generation.skipped.length} 条规则需核对经办人。</p><p>${E(careContext().generation.notice)}</p>`):'');
}

async function careRuleDialog(id=null){
 const catalog=await careCatalog(),row=id?careContext().rules.find(r=>r.id===id):null,kind=row?.kind||$('[name=care_rule_kind]').value;
 const people=await careChoices('employees',{subtype:kind});let fields=await careField('name','规则名称','text',row?.name||catalog.types[kind]);
 if(['first_service','maintenance'].includes(kind))fields+=await careField('interval_days','周期天数（不按日期填0）','int',row?.interval_days??90)+await careField('interval_km','周期公里（不按里程填0）','int',row?.interval_km??5000)+await careField('lead_km','提前公里数','int',row?.lead_km??100);
 fields+=await careField('lead_days','提前天数','int',row?.lead_days??7)+careSelect('assignee_id','默认经办人',people,row?.assignee_id||people[0]?.id)+await careField('active','启用规则','bool',row?.active??true);
 const request_id=requestKey();modal('维护'+catalog.types[kind]+'规则',careForm(fields),async form=>{const fd=new FormData(form);await api(careAPI+'/reminders/rules'+(id?'/'+id:''),{method:id?'PUT':'POST',body:{request_id,...(id?{version:row.version}:{}),values:{name:fd.get('name'),kind,interval_days:Number(fd.get('interval_days')||0),interval_km:Number(fd.get('interval_km')||0),lead_days:careInteger(fd,'lead_days'),lead_km:Number(fd.get('lead_km')||0),assignee_id:careInteger(fd,'assignee_id'),active:fd.has('active')}}});closeModal();await render();});
}

async function customerHistoryGrantsPage(){
 const catalog=await careCatalog();if(!catalog.can_manage)throw new Error('服务历史授权由门店主管办理。');
 const d=await api(careAPI+'/history/grants');careContext().grants=d.items;
 return heading('跨店服务历史授权','只对明确的客户身份及车辆授予服务摘要读取权；不开放原单办理、费用或任何附件。',b('care-grant-new','登记授权','','primary'))
 +panel('本店作为授权方或接收方的记录',table(['授权编号','来源门店','接收门店','本店/对方车辆关系','截止日期','状态','操作'],d.items.map(r=>[r.id,r.from_store_id,r.to_store_id,r.from_vehicle_id+' / '+r.to_vehicle_id,E(r.valid_until),r.status==='active'&&r.valid_until<day()?'已过期':E(careLocalLabels[r.status]),r.status==='active'?b('care-grant-revoke','撤销',`data-id="${r.id}"`):'—'])));
}

async function careGrantDialog(id=null){
 const row=id?careContext().grants.find(r=>r.id===id):null;
 const fields=row?await careField('reason','撤销原因','textarea'):careSelect('from_vehicle_id','本店客户车辆',await careChoices('vehicles'))+careSelect('to_store_id','接收门店',await careChoices('stores'))+await careField('to_vehicle_id','对方提供的客户车辆关系编号','int')+await careField('valid_until','授权截止日','future_date',relativeDay(30))+await careField('source_reference','客户确认授权的依据')+await careField('confirmed','已确认仅将该客户该车辆的服务摘要提供给所选门店','bool',false);
 const request_id=requestKey();modal(row?'撤销服务历史授权':'登记跨店服务历史授权',careForm(fields),async form=>{const fd=new FormData(form);await api(careAPI+'/history/grants'+(row?'/'+id+'/revoke':''),{method:'POST',body:{request_id,...(row?{version:row.version}:{}),values:row?{reason:fd.get('reason')}:{from_vehicle_id:careInteger(fd,'from_vehicle_id'),to_store_id:careInteger(fd,'to_store_id'),to_vehicle_id:careInteger(fd,'to_vehicle_id'),valid_until:fd.get('valid_until'),source_reference:fd.get('source_reference'),confirmed:fd.has('confirmed')}}});closeModal();await render();toast(row?'授权已撤销':'服务历史授权已记录');});
}

document.addEventListener('click',async event=>{const el=event.target.closest('[data-act]');if(!el||el.disabled||!el.dataset.act.startsWith('care-'))return;el.disabled=true;try{
 const action=el.dataset.act;
 if(action==='care-new')await careNewDialog($('[name=care_create_type]').value);
 else if(action==='care-action')await careActionDialog(el.dataset.action);
 else if(action==='care-vehicle-new')await careVehicleDialog();
 else if(action==='care-vehicle-edit')await careVehicleDialog(true);
 else if(action==='care-observe')await careObservationDialog();
 else if(action==='care-new-vehicle-case'){const row=careContext().vehicle;await careNewDialog('consultation',row.customer_id,row.id);}
 else if(action==='care-history-link')await careHistoryLinkDialog();
 else if(action==='care-rule-new'||action==='care-rule-edit')await careRuleDialog(Number(el.dataset.id)||null);
 else if(action==='care-generate'){careContext().generation=await api(careAPI+'/reminders/generate',{method:'POST',body:{request_id:requestKey()}});await render();toast('到期检查完成，未发送外部消息');}
 else if(action==='care-renewals'){careContext().subtype='renewal';careContext().status='open';go('customer-service');}
 else if(action==='care-grant-new'||action==='care-grant-revoke')await careGrantDialog(Number(el.dataset.id)||null);
 else if(action==='care-q-propose')await careQuestionnaireProposalDialog();
 else if(action==='care-q-review')await careQuestionnaireReviewDialog(Number(el.dataset.id),el.dataset.decision);
 else if(action==='care-q-add'){const target=document.querySelector('#care-question-editors');if(target&&target.children.length<30)target.insertAdjacentHTML('beforeend',careQuestionEditor({key:'question_'+(++careContext().questionCounter),label:'',kind:'boolean',required:true}));else throw new Error('最多30题，请先删除不需要的题目。');}
 else if(action==='care-q-remove')el.closest('.care-question-editor')?.remove();
 else if(action==='care-q-export')await download(careQuestionnaireExportURL(el.dataset),'huakangos_原题问卷统计.csv');

 }catch(error){toast(error.message,true);}finally{if(el.isConnected)el.disabled=false;}});
document.addEventListener('submit',async event=>{if(event.target.id!=='care-filters')return;event.preventDefault();const fd=new FormData(event.target),c=careContext();c.query=fd.get('q');c.subtype=fd.get('subtype');c.status=fd.get('status');state.page=1;await render();});


const careQuestionKinds={integer:'整数',boolean:'是或否',text:'文字',choice:'单选'};
function careQuestionValue(q,answer){if(answer===undefined)return '未回答';if(q.kind==='boolean')return answer===true?'是':answer===false?'否':'来源需核对';if(q.kind==='choice')return q.choices.find(x=>x.key===answer)?.label||'来源需核对';return String(answer);}
function careQuestionnaireOriginal(q){const answer=q.response?.answers||{};return panel(`本次原问卷 v${q.number} · ${E(q.name)}`,`<p class="muted">发放时间：${E(time(q.issued_at))}。本页始终显示原题；后续发布不会改写这份问卷。</p>`+table(['原题','题型','必答','原回答'],q.questions.map(x=>[E(x.label),careQuestionKinds[x.kind],x.required?'是':'否',E(careQuestionValue(x,answer[x.key]))])));}
function careQuestionAnswerField(q){const name='answer__'+q.key,label=q.label+(q.required?'（已解决时必答）':'（可不答）');
 if(q.kind==='boolean')return careSelect(name,label,[{id:'yes',label:'是'},{id:'no',label:'否'}],'',false);
 if(q.kind==='choice')return careSelect(name,label,q.choices.map(o=>({id:o.key,label:o.label})),'',false);
 if(q.kind==='integer')return `<label>${E(label)}<input name="${E(name)}" type="number" step="1" min="${q.min_value}" max="${q.max_value}" inputmode="numeric" placeholder="${q.min_value} 至 ${q.max_value}；不答留空"></label>`;
 return `<label class="wide">${E(label)}<textarea name="${E(name)}" maxlength="${q.max_length}" placeholder="不答留空"></textarea></label>`;
}
function careQuestionSchema(schema){return table(['题目编号','题目','题型/范围','必答'],schema.map(q=>[E(q.key),E(q.label),E(careQuestionKinds[q.kind]+(q.kind==='integer'?` · ${q.min_value} 至 ${q.max_value}`:q.kind==='choice'?' · '+q.choices.map(x=>x.label).join(' / '):q.kind==='text'?` · 最多${q.max_length}字`:'')),q.required?'是':'否']));}
async function careQuestionnairePage(){
 await careCatalog();const d=await api(careAPI+'/questionnaires/versions');careContext().questionnaireCatalog=d;
 const labels={active:'当前后续发放使用',superseded:'已被新版本替代',pending:'待独立复核',rejected:'未批准'};
 return heading('问卷题目版本','员工只填写本次发放的原题；新题先经独立复核，再用于后续发放。',(d.can_manage?b('care-q-propose','提出新的题目版本','','primary')+' ':'')+b('open','查看原题统计',`data-route="customer-questionnaire-report"`))
 +`<div class="notice">${E(d.notice)} 当前后续发放使用 v${d.active_number}。本店未发布新题时，保留原满意度与推荐意愿 v1。</div>`
 +panel('原v1题目（不会被覆盖）',careQuestionSchema(d.legacy.questions))
 +d.items.map(row=>panel(`v${row.number} · ${E(row.name)}`,`<p>${E(labels[row.state])} · 提出理由：${E(row.reason)}</p><details><summary>查看此版本完整题目</summary>${careQuestionSchema(row.questions)}</details>${row.review?`<p class="muted">独立处理记录：${row.review.decision==='approve'?'批准':'未批准'} · ${E(row.review.reason)}</p>`:''}${row.can_review?`<div class="row mt15">${b('care-q-review','逐题复核后批准',`data-id="${row.id}" data-decision="approve"`,'primary')}${b('care-q-review','记录不批准',`data-id="${row.id}" data-decision="reject"`)}</div>`:''}`)).join('');
}
function careQuestionEditor(q){const choices=(q.choices||[]).map(o=>o.key+'|'+o.label).join('\n');
 return `<section class="notice care-question-editor mt15"><div class="formgrid"><label>唯一题目编号<input name="q_key" value="${E(q.key)}" pattern="[a-z][a-z0-9_]{0,39}" maxlength="40" required></label><label>显示给员工和客户的题目<input name="q_label" value="${E(q.label)}" maxlength="180" required></label>${careSelect('q_kind','题型',careOptions(careQuestionKinds),q.kind)}<label>已解决时必答<input name="q_required" type="checkbox" ${q.required?'checked':''}></label><label>整数最小值（整数题填写）<input name="q_min" type="number" step="1" value="${q.min_value??''}"></label><label>整数最大值（整数题填写）<input name="q_max" type="number" step="1" value="${q.max_value??''}"></label><label>文字最大长度（文字题填写，1至2000）<input name="q_length" type="number" min="1" max="2000" step="1" value="${q.max_length??''}"></label><label class="wide">单选选项（每行一个：英文编号|显示名称，2至20行）<textarea name="q_choices">${E(choices)}</textarea></label></div>${b('care-q-remove','移除此题')}</section>`;
}
async function careQuestionnaireProposalDialog(){
 const d=await api(careAPI+'/questionnaires/versions');if(!d.can_manage)throw new Error('题目版本由本店主管提出。');
 const active=d.items.find(r=>r.id===d.active_version_id),schema=active?.questions||d.active_questions||d.legacy.questions;careContext().questionCounter=schema.length;
 const fields=await careField('name','新版本名称','text',active?.name||d.active_name||d.legacy.name)+await careField('reason','提出新题的业务理由','textarea')+`<div class="wide"><p>题目编号用于绑定原答案；相同题意可沿用编号。满意度和推荐编号保留原含义。新版本不会更改旧问卷。</p><div id="care-question-editors">${schema.map(careQuestionEditor).join('')}</div>${b('care-q-add','增加一道题')}</div>`;
 const request_id=requestKey();modal('提出新的问卷版本',careForm(fields),async form=>{
  const get=(el,name)=>el.querySelector(`[name="${name}"]`).value.trim();
  const integer=(el,name)=>{const s=get(el,name);if(!/^-?\d+$/.test(s)||!Number.isSafeInteger(Number(s)))throw new Error('整数范围和长度必须明确填写完整整数。');return Number(s);};
  const questions=[...form.querySelectorAll('.care-question-editor')].map(el=>{const kind=get(el,'q_kind');const q={key:get(el,'q_key'),label:get(el,'q_label'),kind,required:el.querySelector('[name=q_required]').checked};
   if(kind==='integer'){q.min_value=integer(el,'q_min');q.max_value=integer(el,'q_max');}
   if(kind==='text')q.max_length=integer(el,'q_length');
   if(kind==='choice')q.choices=get(el,'q_choices').split(/\r?\n/).filter(s=>s.trim()).map(line=>{const parts=line.split('|');if(parts.length!==2)throw new Error('每个选项按 英文编号|显示名称 填写。');return {key:parts[0].trim(),label:parts[1].trim()};});return q;});
  await api(careAPI+'/questionnaires/versions',{method:'POST',body:{request_id,values:{policy_version:d.policy_version,name:get(form,'name'),reason:get(form,'reason'),questions}}});closeModal();await render();toast('新题已登记，等待另一位主管独立复核');
 });
}
async function careQuestionnaireReviewDialog(id,decision){
 const d=await api(careAPI+'/questionnaires/versions'),row=d.items.find(r=>r.id===id);if(!row||!row.can_review)throw new Error('当前人员或版本不允许独立复核，请刷新。');
 const fields=`<div class="wide">${careQuestionSchema(row.questions)}</div>`+await careField('reason','逐题复核意见','textarea')+await careField('confirmed','我已核对完整题目、范围与必答规则，且不是该版本提出人','bool',false);
 const request_id=requestKey();modal(decision==='approve'?'批准后仅用于后续发放':'记录不批准',careForm(fields),async form=>{const fd=new FormData(form);await api(careAPI+`/questionnaires/versions/${id}/review`,{method:'POST',body:{request_id,values:{policy_version:d.policy_version,decision,reason:fd.get('reason'),confirmed:fd.has('confirmed')}}});closeModal();await render();});
}
function careQuestionnaireExportURL(dataset){
 const params=new URLSearchParams(state.dates);
 for(const [parameter,attribute] of [['version_number','versionNumber'],['schema_digest','schemaDigest'],['question_key','questionKey']])if(dataset[attribute]!==undefined)params.set(parameter,dataset[attribute]);
 return careAPI+'/questionnaires/export/'+encodeURIComponent(dataset.key)+'?'+params;
}
function careQuestionnaireExportAttributes(key,filters=null){
 return `data-key="${E(key)}"`+(filters?` data-version-number="${E(filters.version_number)}" data-schema-digest="${E(filters.schema_digest)}" data-question-key="${E(filters.question_key)}"`:'');
}
function careQuestionnaireRows(t,filters){
 return t.rows.filter(row=>['version_number','schema_digest','question_key'].every(key=>row[key]===filters[key]));
}
async function careQuestionnaireReportPage(){
 await careCatalog();const d=await api(careAPI+'/questionnaires/report?'+new URLSearchParams(state.dates));
 const show=(key,t)=>{const rows=t.rows.slice((state.page-1)*25,state.page*25);return panel(t.title,b('care-q-export','导出本表',`data-key="${key}"`)+table([...t.headers,'原单'],rows.map(r=>[...r.values.map(E),r.route?b('open','原问卷',`data-route="customer-service/${r.route.id}"`):'—']))+(t.rows.length?pager(t.rows.length,state.page,25):empty('没有本期原记录')));};
 const showChart=c=>{
  const filters=c.table_filters,distribution=d.tables[c.table],answers=d.tables.questionnaire_answers;
  const rows=careQuestionnaireRows(distribution,filters),originals=careQuestionnaireRows(answers,filters),page=originals.slice((state.page-1)*25,state.page*25);
  return panel(c.title,chartSVG(c)+b('care-q-export','导出同源表',careQuestionnaireExportAttributes(c.table,filters))
   +`<details class="mt15"><summary>查看本题同源明细</summary>`+table(['回答','记录数'],rows.map(r=>[E(r.values[4]),E(r.count)]))
   +b('care-q-export','导出本题原答案',careQuestionnaireExportAttributes('questionnaire_answers',filters))
   +table(['原回答','回答状态','结案日期','实际结果','原单'],page.map(r=>[...([7,6,2,3].map(index=>E(r.values[index]))),b('open','原问卷',`data-route="customer-service/${r.route.id}"`)]))+(originals.length?pager(originals.length,state.page,25):empty('没有本期原记录'))+'</details>');
 };
 return heading('原题问卷统计','发放与回答按各自实际日期统计，不把未回答算作否或0。',b('open','题目版本',`data-route="customer-questionnaires"`))+dateFilters()+`<div class="notice">${d.definitions.map(x=>`<p>${E(x)}</p>`).join('')}</div>`+d.charts.map(showChart).join('')+Object.entries(d.tables).map(([key,t])=>show(key,t)).join('');
}
