'use strict';
const BR_BASIC_COLORS=['红','橙','黄','绿','青','蓝','紫','白','灰','黑'];
function brChoice(values){return values.map(value=>({value,label:value}));}
function brSubmissionFields(){return [F('vehicle_invoice_price','机动车开票价（元）','money_zero',false),F('registration_fee','上牌服务费（元）','money_zero',false),F('payment_method','客户付款方式','select',true,brChoice(['全款','贷款'])),F('is_cash_vehicle','是否现金库存车（内部，不打印）','select',true,[{value:'',label:'请选择'},{value:'true',label:'是，门店自有现金购回／赎回'},{value:'false',label:'否，非现金库存车'}]),F('installment_fee','分期服务费（元）','money_zero',false),F('total_loss_product_description','全损换新（如一年）','text',false),F('trade_in_subsidy','置换补贴（元）','money_zero',false),F('used_car_commission','二手车佣金（元）','money_zero',false),F('finance_excess','金融超价（元）','money_zero',false),F('registration_excess','上牌费超价（元）','money_zero',false),F('transfer_store','调拨店端','text',false),F('towing_cost','拖车成本（元）','money_zero',false),F('department','所在部门','text',false)];}
function brCashVehicleLabel(value){return value===true?'现金库存车':value===false?'非现金库存车':'待核对';}
function brSubmissionValues(data){return Object.fromEntries(brSubmissionFields().map(f=>[f.key,f.key==='is_cash_vehicle'?(typeof data?.[f.key]==='boolean'?String(data[f.key]):''):f.type==='money_zero'?brInputAmount(data?.[f.key+'_cents']):data?.[f.key]??(f.key==='payment_method'?'全款':'')]));}
function brSubmissionPayload(values){return Object.fromEntries(brSubmissionFields().map(f=>{if(f.key==='is_cash_vehicle'){if(!['true','false'].includes(values[f.key]))throw new Error('请明确是否为现金库存车。');return [f.key,values[f.key]==='true'];}return [f.type==='money_zero'?f.key+'_cents':f.key,f.type==='money_zero'?(values[f.key]===''?null:moneyFen(values[f.key],{label:f.label,allowZero:true})):values[f.key]];}));}
function brGiftList(terms){
 if(!terms)return '';const monetary=Object.hasOwn(terms,'gift_total_cents'),cost=Object.hasOwn(terms,'gift_cost_total_cents'),amount=v=>v==null?'待补齐':brAmount(v);
 return `<div class="br-gift-summary">${table(['赠品','数量','单位','适用车型',...(monetary?['售价','售价金额']:[]),...(cost?['成本单价','成本金额']:[])],(terms.gifts_snapshot||[]).map(g=>[E(g.name),E(g.quantity),E(g.unit||'—'),E(g.applicable_models||'—'),...(monetary?[amount(g.unit_price_cents),amount(g.amount_cents)]:[]),...(cost?[amount(g.unit_cost_cents),amount(g.cost_cents)]:[])]))}${monetary?`<p class="br-gift-total">赠品售价合计 <strong>${E(amount(terms.gift_total_cents))}</strong></p>`:''}${cost?`<p class="br-gift-total">赠品成本合计 <strong>${E(amount(terms.gift_cost_total_cents))}</strong></p>`:''}</div>`;
}
function brGiftPolicyResult(check){
 if(!check||check.status==='no_policy')return '';
 const label=({within_limit:'赠品在额度内',exceeded:'赠品超额，需特殊审批',unknown_cost:'赠品成本未核定，需特殊审批'})[check.status]||'赠品政策待核对';
 return `<div class="notice ${check.requires_special?'br-special':''}"><strong>${E(label)}</strong>${Object.hasOwn(check,'cost_limit_cents')?`<div>赠品成本额度：${E(brAmount(check.cost_limit_cents))}</div>`:''}${Object.hasOwn(check,'gift_cost_total_cents')?`<div>已选赠品成本：${E(check.gift_cost_total_cents==null?'未核定':brAmount(check.gift_cost_total_cents))}</div>`:''}${check.text?`<details><summary>赠品政策</summary><p class="br-source-note">${E(check.text)}</p></details>`:''}</div>`;
}
function brMountGiftSearch(form,section,gifts,canViewAmounts){
 const grid=section.querySelector('.formgrid');
 // Keep the original controls mounted so filtering preserves quantities, drafts and submission values.
 const entries=gifts.map(g=>{
  const check=form.elements['gift_selected_'+g.id],quantity=form.elements['gift_quantity_'+g.id],row=document.createElement('div');
  row.className='br-gift-option';row.dataset.brGiftRow=String(g.id);row.append(check.closest('label'),quantity.closest('label'));
  const detail=document.createElement('small');detail.className='br-caption';detail.textContent=[g.unit&&'单位：'+g.unit,g.applicable_models&&'适用车型：'+g.applicable_models,canViewAmounts&&'单价 '+brAmount(g.unit_price_cents)].filter(Boolean).join(' · ');row.append(detail);
  quantity.min='1';quantity.max='10000';quantity.step='1';
  const enable=()=>{quantity.disabled=!check.checked;if(check.checked&&!quantity.value)quantity.value='1';};enable();
  return {check,quantity,row,enable,text:[g.name,g.applicable_models,g.unit,g.brand].filter(Boolean).join(' ').normalize('NFKC').toLocaleLowerCase()};
 });
 grid.className='br-gift-picker';
 grid.innerHTML='<div class="br-gift-search-controls"><label>搜索赠品<input type="search" data-br-gift-search placeholder="输入赠品名称或适用车型" autocomplete="off" aria-describedby="br-gift-search-hint"></label><button type="button" data-br-gift-search-clear>清空搜索</button></div><p id="br-gift-search-hint" class="br-caption">输入赠品名称或适用车型搜索；已选赠品会一直保留，可取消勾选。</p><p class="br-caption" data-br-gift-search-status role="status" aria-live="polite"></p><h3>已选赠品 <span data-br-gift-selected-count></span></h3><p class="br-caption" data-br-gift-selected-empty>尚未选择赠品。</p><div data-br-gift-selected></div><h3 data-br-gift-results-title hidden>搜索结果</h3><div data-br-gift-results></div>';
 const search=grid.querySelector('[data-br-gift-search]'),clear=grid.querySelector('[data-br-gift-search-clear]'),selectedList=grid.querySelector('[data-br-gift-selected]'),results=grid.querySelector('[data-br-gift-results]'),status=grid.querySelector('[data-br-gift-search-status]');
 const refresh=()=>{
  const words=search.value.normalize('NFKC').toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);let selected=0,matches=0;
  for(const entry of entries){
   const chosen=entry.check.checked,match=words.length>0&&words.every(word=>entry.text.includes(word)),destination=chosen?selectedList:results;
   if(chosen)selected++;else if(match)matches++;
   if(entry.row.parentNode!==destination)destination.append(entry.row);
   entry.row.hidden=!chosen&&!match;
  }
  grid.querySelector('[data-br-gift-selected-count]').textContent='（'+selected+' 项）';grid.querySelector('[data-br-gift-selected-empty]').hidden=selected>0;
  grid.querySelector('[data-br-gift-results-title]').hidden=!words.length;results.hidden=!words.length;clear.disabled=!search.value;
  status.textContent=!gifts.length?'本店尚无可选赠品，请联系销售经理维护。':words.length?(matches?'找到 '+matches+' 项未选赠品。':entries.some(entry=>words.every(word=>entry.text.includes(word)))?'匹配的赠品已在上方已选列表中。':'没有找到匹配赠品，请更换关键词。'):'未搜索时仅显示已选赠品。';
 };
 search.addEventListener('input',refresh);search.addEventListener('search',refresh);search.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.isComposing)event.preventDefault();});
 clear.addEventListener('click',()=>{search.value='';refresh();search.focus();});
 for(const entry of entries)entry.check.addEventListener('change',()=>{const focused=document.activeElement===entry.check;entry.enable();refresh();if(focused)(entry.row.hidden?search:entry.check).focus({preventScroll:true});});
 refresh();
 return ()=>{for(const entry of entries)entry.enable();refresh();};
}
function brSpecialFacts(r){const t=r.terms,p=t.price_snapshot||{},s=t.submission_data||{};return brFacts([['销售顾问',r.salesperson_name],['客户姓名',r.customer_name],['客户联系电话',r.customer_phone],['销售车型及配置',r.model],['车身 / 内饰颜色',[r.form_data?.exterior_color,r.form_data?.interior_color].filter(Boolean).join(' / ')],['VIN',r.vin],['指导价',brAmount(p.guide_price_cents)],['集团限价 / 销售管控价',brAmount(p.control_price_cents)],['优惠金额',brAmount(t.discount_cents)],['提交纯车价',brAmount(r.sale_price_cents)],['低于限价',brAmount(t.price_below_cents)],['机动车开票价',brAmount(s.vehicle_invoice_price_cents)],...brSubmissionFields().filter(f=>!['vehicle_invoice_price'].includes(f.key)).map(f=>[f.label.replace('（元）',''),f.key==='is_cash_vehicle'?brCashVehicleLabel(s[f.key]):f.type==='money_zero'?brAmount(s[f.key+'_cents']):s[f.key]]),...(Object.hasOwn(t,'gift_excess_cents')?[['赠送成本超价（经理填写）',brAmount(t.gift_excess_cents)]]:[]),['其他说明',t.special_note||s.note],['限价版本',p.batch_id],['限价发布时间',p.published_at?time(p.published_at):'']]);}
async function brNewContractV210(edit=false){
 const r=edit?brState.detail:null;if(edit&&!r)throw new Error('请重新打开合同。');if(r&&r.workflow_version!=='trial-v210')return brNewContractLegacy(edit);
 const context=brContext(),catalog=await brPricingCatalog(r?.id);if(context!==brContext())return;
 const draftKey=r?'contract-'+r.id:'contract',restoring=brState.drafts[draftKey]?.context===context;
 const profile=catalog.profile||{},vehicles=catalog.vehicles||[],gifts=catalog.gifts||[],people=state.recordCatalog.sales_people||[],sellers=profile.sellers||[];
 if(!vehicles.length||!profile.brand||!sellers.length)throw new Error('本店车型限价、车辆品牌或卖方公司资料尚未维护，请联系销售经理或内勤。');
 const main=[F('customer_name','客户姓名'),F('customer_phone','客户联系电话'),F('salesperson_id','所属销售顾问','select',true,people.map(p=>({value:p.id,label:p.label}))),F('contract_date','合同日期','date'),F('brand','车辆品牌'),F('vehicle_price_id','车系 / 年款 / 车型配置','select',true,[{value:'',label:'请选择车型'},...vehicles.map(v=>({value:v.id,label:[v.family,v.series,v.model].filter(Boolean).join(' / ')}))]),F('vin','车辆识别号 VIN'),F('sale_price','纯车销售金额（元）','money')];
 const extra=brContractExtraFields().filter(f=>!['quantity','payment_method'].includes(f.key)).map(f=>{
  if(f.key==='seller_name')return F(f.key,'卖方公司','select',true,sellers.map(s=>({value:s.name,label:s.name})));
  if(f.key==='buyer_document_name')return F(f.key,'买方证件类型','select',true,brChoice(['身份证','护照','驾照']));
  if(['exterior_color','interior_color'].includes(f.key))return F(f.key,f.label,'select',true,[{value:'',label:'请选择基础色'},...brChoice(BR_BASIC_COLORS)]);
  return f;
 });
 const giftFields=gifts.flatMap(g=>[F('gift_selected_'+g.id,g.name,'bool',false),F('gift_quantity_'+g.id,g.name+' · 数量','int',false)]),submission=brSubmissionFields(),initial={...r?.form_data,...r,brand:profile.brand,seller_name:r?.form_data?.seller_name||sellers[0]?.name,buyer_document_name:r?.form_data?.buyer_document_name||'身份证',buyer_agent:r?.form_data?.buyer_agent||'',sale_price:brInputAmount(r?.sale_price_cents),vehicle_price_id:r?.terms?.price_snapshot?.id||'',salesperson_id:r?.salesperson_id||(state.user.role==='sales'?state.user.id:people.length===1?people[0].id:''),signature_date:r?.form_data?.signature_date||day(),...brSubmissionValues(r?.terms?.submission_data)};
 for(const g of gifts){const selected=r?.terms?.gifts_snapshot?.find(x=>x.price_id===g.id);initial['gift_selected_'+g.id]=Boolean(selected);initial['gift_quantity_'+g.id]=selected?.quantity??1;}
 const dialog=await brForm(edit?'修改销售合同':'预填销售合同',[{title:'客户与车辆',fields:main},{title:'合同双方及交付约定',fields:extra},{title:'选择赠品',fields:giftFields},{title:'价格与特殊申请参考资料',fields:submission}],initial,(v,request_id)=>{
  const vehicle=vehicles.find(x=>x.id===Number(v.vehicle_price_id));if(!vehicle)throw new Error('请选择已发布限价中的车型。');
  const form_data=Object.fromEntries(extra.map(f=>[f.key,String(v[f.key]??'')]));form_data.quantity='1';form_data.payment_method=v.payment_method;
  if(!form_data.buyer_agent)form_data.buyer_agent=v.customer_name;
  for(const f of extra.filter(f=>f.type==='money_zero'))if(form_data[f.key]!=='')form_data[f.key]=brInputAmount(moneyFen(form_data[f.key],{label:f.label,allowZero:true}));
  const gift_items=gifts.filter(g=>v['gift_selected_'+g.id]).map(g=>{const quantity=v['gift_quantity_'+g.id];if(!Number.isInteger(quantity)||quantity<1||quantity>10000)throw new Error(g.name+'数量须为 1 至 10000 的整数。');return {price_id:g.id,quantity};});
  return api(BR_API+'/contracts'+(r?'/'+r.id:''),{method:r?'PUT':'POST',body:{request_id,...(r?{version:r.version}:{}),customer_name:v.customer_name,customer_phone:v.customer_phone,salesperson_id:Number(v.salesperson_id),contract_date:v.contract_date,brand:profile.brand,model:vehicle.series+' '+vehicle.model,vin:v.vin,sale_price_cents:moneyFen(v.sale_price,{label:'纯车销售金额'}),gift_description:'',form_data,vehicle_price_id:vehicle.id,gift_items,submission_data:brSubmissionPayload(v)}});
 },{draftKey,submit:'提交销售经理审批',notice:'低于销售管控价会进入特殊审批；赠品由销售经理查看金额并判断。批准后可打印，已提交合同保留当前限价及赠品版本。',nextRoute:result=>'records-sales/'+result.id});
 const form=$('form',dialog);for(const key of ['brand','seller_phone','seller_address','seller_agent'])form.elements[key].readOnly=true;
 const policyResult=document.createElement('div');policyResult.dataset.giftPolicyResult='';
 const giftSection=[...form.querySelectorAll('fieldset')].find(section=>section.querySelector('legend')?.textContent==='选择赠品');giftSection.querySelector('legend').after(policyResult);
 let policySequence=0,policyTimer;
 const checkGiftPolicy=async()=>{
  const sequence=++policySequence,vehicle=vehicles.find(x=>x.id===Number(form.elements.vehicle_price_id.value));
  if(!vehicle?.gift_policy){policyResult.replaceChildren();return;}
  const selected=gifts.filter(g=>form.elements['gift_selected_'+g.id].checked).map(g=>({price_id:g.id,quantity:Number(form.elements['gift_quantity_'+g.id].value)}));
  if(selected.some(g=>!Number.isSafeInteger(g.quantity)||g.quantity<1||g.quantity>10000)){policyResult.textContent='请填写有效赠品数量';return;}
  policyResult.textContent='正在核对赠品额度…';
  try{const check=await api(BR_API+'/pricing/gift-policy-check',{method:'POST',body:{vehicle_price_id:vehicle.id,gift_items:selected,...(r?{contract_id:r.id}:{})}});
   if(sequence!==policySequence||context!==brContext()||!form.isConnected)return;policyResult.innerHTML=brGiftPolicyResult(check);
  }catch(error){if(sequence===policySequence&&context===brContext()&&form.isConnected)policyResult.textContent=error.message;}
 };
 const schedulePolicyCheck=()=>{++policySequence;clearTimeout(policyTimer);policyTimer=setTimeout(()=>{if(form.isConnected&&context===brContext())checkGiftPolicy();},200);};
 form.addEventListener('input',event=>{if(event.target.name==='vehicle_price_id'||event.target.name?.startsWith('gift_'))schedulePolicyCheck();});
 checkGiftPolicy();
 const defaults=()=>{const person=people.find(p=>p.id===Number(form.elements.salesperson_id.value)),seller=sellers.find(s=>s.name===form.elements.seller_name.value);form.elements.seller_agent.value=person?.label||'';form.elements.seller_phone.value=profile.sales_contacts?.[String(person?.id)]||'';form.elements.seller_address.value=seller?.address||profile.address||'';};defaults();form.elements.salesperson_id.addEventListener('change',defaults);form.elements.seller_name.addEventListener('change',defaults);
 const priceNotice=document.createElement('p');priceNotice.className='notice';priceNotice.dataset.brVehiclePriceHint='';priceNotice.setAttribute('aria-live','polite');form.elements.sale_price.closest('label').after(priceNotice);
 const priceCheck=()=>{const v=vehicles.find(x=>x.id===Number(form.elements.vehicle_price_id.value));if(!v){priceNotice.textContent='请选择车型后查看指导价与销售管控价。';return;}let sale=null;try{sale=moneyFen(form.elements.sale_price.value,{label:'纯车销售金额'});}catch(_){}const below=sale!=null&&sale<v.control_price_cents;priceNotice.className='notice'+(below?' br-special':'');priceNotice.textContent='指导价 '+brAmount(v.guide_price_cents)+' · 销售管控价 '+brAmount(v.control_price_cents)+' · 本次售价 '+(sale==null?'待填写':brAmount(sale))+(below?' · 低于限价，需特殊审批':'');};priceCheck();form.elements.vehicle_price_id.addEventListener('change',priceCheck);form.elements.sale_price.addEventListener('input',priceCheck);
 let agentAutomatic=!r?.form_data?.buyer_agent;form.elements.buyer_agent.placeholder='本人办理，可填写其他代理人';form.elements.buyer_agent.addEventListener('input',()=>{agentAutomatic=false;});form.elements.customer_name.addEventListener('input',()=>{if(agentAutomatic)form.elements.buyer_agent.value=form.elements.customer_name.value;});
 const refreshGiftSearch=brMountGiftSearch(form,giftSection,gifts,catalog.can_view_gift_amounts),standardHint=document.createElement('div');standardHint.className='notice';standardHint.dataset.brStandardGifts='';giftSection.querySelector('legend').after(standardHint);
 // Remember user changes beside the in-memory draft. A restored draft or edited
 // contract never gets default selections applied again merely by opening it.
 let giftDefaults=null;
 if(!r){
  const previous=brState.contractGiftDefaults;
  giftDefaults=restoring&&previous?.context===context?previous:{context,manual:{},automatic:{}};
  if(restoring&&giftDefaults!==previous)for(const gift of gifts)giftDefaults.manual[gift.id]=true;
  brState.contractGiftDefaults=giftDefaults;
  const rememberGiftChoice=event=>{const match=event.target.name?.match(/^gift_(?:selected|quantity)_(\d+)$/);if(match)giftDefaults.manual[match[1]]=true;};
  form.addEventListener('input',rememberGiftChoice);form.addEventListener('change',rememberGiftChoice);
 }
 const standardsFor=vehicle=>{
  const policy=vehicle?.gift_policy,items=policy?.standard_gifts||[];
  const invalid=policy?.standard_gifts_status==='outdated'||!Array.isArray(items)||items.some(item=>!Number.isSafeInteger(item.price_id)||!gifts.some(g=>g.id===item.price_id)||!Number.isSafeInteger(item.quantity)||item.quantity<1||item.quantity>10000);
  return {items:invalid?[]:items,invalid,policy};
 };
 const showStandardGifts=()=>{
  const vehicle=vehicles.find(x=>x.id===Number(form.elements.vehicle_price_id.value));standardHint.hidden=!vehicle;if(!vehicle)return;
  const {items,invalid,policy}=standardsFor(vehicle);
  standardHint.innerHTML=`<strong>本车型标准赠品</strong><p>${invalid?'标准赠品目录已变更，请联系销售经理核对；当前选择保持不变。':items.length?items.map(item=>{const gift=gifts.find(g=>g.id===item.price_id);return E(gift.name)+' × '+E(item.quantity)+(gift.unit?' '+E(gift.unit):'');}).join('；'):'此车型未配置可默认勾选的标准赠品，请按政策核对后选择。'}</p>${items.length?'<p class="br-caption">标准赠品仅作初始默认，可取消、替换或修改数量；已手工调整的选择保持不变。</p>':''}${policy?.standard_gift_note?`<p class="br-source-note">${E(policy.standard_gift_note)}</p>`:''}${policy?.text?`<p class="br-source-note">${E(policy.text)}</p>`:''}`;
 };
 const applyStandardGifts=()=>{
  showStandardGifts();if(!giftDefaults||context!==brContext())return;
  const vehicle=vehicles.find(x=>x.id===Number(form.elements.vehicle_price_id.value)),{items,invalid}=standardsFor(vehicle);if(invalid)return;
  for(const id of Object.keys(giftDefaults.automatic))if(!giftDefaults.manual[id]&&form.elements['gift_selected_'+id])form.elements['gift_selected_'+id].checked=false;
  const automatic={};
  for(const item of items){const id=item.price_id;if(giftDefaults.manual[id])continue;const check=form.elements['gift_selected_'+id];if(check.checked&&!Object.hasOwn(giftDefaults.automatic,id))continue;check.checked=true;form.elements['gift_quantity_'+id].value=String(item.quantity);automatic[id]=item.quantity;}
  giftDefaults.automatic=automatic;refreshGiftSearch();form.dispatchEvent(new Event('input',{bubbles:true}));
 };
 showStandardGifts();form.elements.vehicle_price_id.addEventListener('change',()=>{applyStandardGifts();schedulePolicyCheck();});
}
async function brContractV210(id){
 const epoch=renderId,r=await api(BR_API+'/contracts/'+id);if(epoch!==renderId)return '';if(r.workflow_version!=='trial-v210')return brContractLegacy(id);brState.detail=r;
 const t=r.terms||{},special=t.special,labels={edit:'修改合同',manager_approve:'销售经理审核 / 提交申请',approve:special?'总经理同意，提交集团副总经理':'总经理审批通过',deputy_approve:'集团副总经理审批通过',reject:'退回合同',print:'下载 / 打印合同',office_edit:'填写 / 核对内勤资料',office_submit:'提交资料审批',office_approve:'资料审批通过',office_reject:'退回内勤资料'};
 const button=a=>brButton('contract-action',labels[a],`data-action="${a}"`,['approve','deputy_approve','manager_approve','print','office_edit','office_approve','office_submit'].includes(a)?'primary':'');
 const actions=(r.actions||[]).filter(a=>labels[a]&&!a.startsWith('office_')).map(button).join(''),officeActions=(r.actions||[]).filter(a=>labels[a]&&a.startsWith('office_')).map(button).join(''),stage=['submitted','rejected'].includes(r.status)?1:r.status==='manager_approved'?2:r.status==='deputy_pending'?3:4;
 const steps=[['销售预填',true],['销售经理审批',stage>1],['总经理审批',special?stage>2:r.status==='approved'],...(special?[['集团副总经理审批',r.status==='approved']]:[]),['财务确认交车',Boolean(r.delivery_state?.delivery)],['内勤延伸资料 / 总经理审核',r.office_status==='approved']];
 const invoice=await brInvoiceSection(r);if(epoch!==renderId)return '';
 return heading('销售合同 '+r.number,[r.customer_name,r.brand,r.model].join(' · '),(r.customer_id?brLink('records-customers/'+r.customer_id,'客户档案'):'')+brLink('records-sales','返回销售业务'))+
 `<div class="br-steps">${steps.map(([label,done],i)=>`<span class="${done?'complete':''}">${i+1}. ${E(label)}</span>`).join('')}</div><section class="panel ${special?'br-special-panel':''}"><div class="panelhead spread"><div><h2>${special?'<span class="br-special-label">特殊审批</span>':'普通审批'} · ${E(r.status_label||BR_STATUS[r.status])}</h2></div><div class="row">${actions}</div></div><div class="panelbody">${t.price_snapshot?brSpecialFacts(r):''}</div><div class="panelhead"><h2>赠品及赠送项目</h2></div>${brGiftPolicyResult(t.gift_policy_check)}${brGiftList(t)}</section>`+
 `<details class="panel br-disclosure"><summary>合同双方与交付约定</summary>${brFacts(brContractExtraFields().filter(f=>f.key!=='quantity').map(f=>[f.label,r.form_data?.[f.key]]))}</details>`+
 `<section class="panel"><div class="panelhead spread"><h2>申请证据附件</h2>${['submitted','rejected'].includes(r.status)&&(r.actions||[]).some(a=>['edit','manager_approve'].includes(a))?brFlowButton('contract-attachment','补充附件'):''}</div>${table(['文件','状态','操作'],(t.attachments||[]).map(f=>[E(f.filename),f.available?'可查阅':'文件检查中',f.available?brFlowButton('pricing-download','下载',`data-file="${f.id}" data-name="${E(f.filename)}"`):'—']))}</section>`+
 invoice+brDeliverySection(r)+brOfficeSectionV210(r,officeActions)+`<details class="panel br-disclosure"><summary>完整流转记录</summary>${table(['时间','操作人','动作','说明'],(r.events||[]).map(e=>[time(e.created_at),E(e.actor_name),E(labels[e.action]||e.action),E(e.note||'—')]))}</details>`;
}
async function brManagerApproval(){
 const r=brState.detail,t=r.terms,fields=[...brSubmissionFields(),F('gift_excess','其他赠品超价（元）','money_zero'),F('note','其他说明 / 特殊申请理由','textarea',false)],values={...brSubmissionValues(t.submission_data),gift_excess:brInputAmount(t.gift_excess_cents??0),note:t.special_note||t.submission_data?.note||''};
 const dialog=await brForm('销售经理审核 · 销售超限价政策申请',[{title:'审批申请表',fields}],values,(v,request_id)=>{
  const excess=moneyFen(v.gift_excess,{label:'赠送成本超价',allowZero:true});if((t.price_below_cents>0||excess>0||t.gift_policy_check?.requires_special)&&!v.note.trim())throw new Error('特殊审批须填写其他说明 / 申请理由。');
  return api(BR_API+'/contracts/'+r.id+'/manager-approve',{method:'POST',body:{request_id,version:r.version,gift_excess_cents:excess,note:v.note,submission_data:{...brSubmissionPayload(v),note:v.note}}});
 },{draftKey:'manager-special-'+r.id+'-'+r.version,submit:'确认审核并提交总经理',notice:'车价低于销售管控价，或您填写的赠送成本超价大于零，将转特殊审批：总经理 → 集团副总经理。金融费及上牌费不触发自动超限。'});
 const form=$('form',dialog),facts=document.createElement('div');facts.className='br-special-review';facts.innerHTML=brSpecialFacts(r)+brGiftPolicyResult(t.gift_policy_check)+`<h3>赠送成本超价参考 · 已选赠品清单</h3>`+brGiftList(t);form.querySelector('fieldset').before(facts);
}
async function brContractActionV210(action){
 const r=brState.detail;if(r?.workflow_version!=='trial-v210')return brContractActionLegacy(action);
 if(!r.actions?.includes(action))throw new Error('合同状态或岗位权限已变化，请刷新后办理。');
 if(action==='edit')return brNewContractV210(true);if(action==='manager_approve')return brManagerApproval();if(action==='office_edit')return brOfficeEditV210();
 if(action==='print')return download(BR_API+'/contracts/'+r.id+'/print',r.number+'.pdf');
 const specs={approve:['总经理审批',r.terms?.special?'本次同意后交集团副总经理终审，尚不能打印。':'本次批准后可正常打印合同。'],deputy_approve:['集团副总经理审批','特殊申请终审通过后可正常打印合同。'],reject:['退回合同','填写退回原因，由原销售顾问修改。'],office_submit:['提交内勤延伸资料','未核实项目保留待补齐；本次提交总经理审核。'],office_approve:['通过内勤资料审核','审批结果进入延伸统计，不改变财务交车事实。'],office_reject:['退回内勤资料','请说明待修改的内容。']};
 const spec=specs[action];if(!spec)throw new Error('不支持的合同动作。');return brForm(spec[0],[{title:r.number,fields:[F('note',action.includes('reject')?'退回原因':'审批说明','textarea',action.includes('reject'))]}],{},(v,request_id)=>api(BR_API+'/contracts/'+r.id+'/'+action.replaceAll('_','-'),{method:'POST',body:{request_id,version:r.version,note:v.note}}),{draftKey:action+'-'+r.id+'-'+r.version,submit:spec[0],notice:spec[1]});
}
async function brContractAttachment(){const r=brState.detail,context=brContext(),requestId=requestKey();modal('补充申请证据',`<form><label>附件<input type="file" name="file" accept=".pdf,.png,.jpg,.jpeg" required></label><div class="formerror" role="alert"></div><div class="modalfoot"><button type="submit" class="primary">上传附件</button></div></form>`,async form=>{if(context!==brContext())throw new Error('账号或门店已切换。');const body=new FormData(form);body.set('request_id',requestId);body.set('version',r.version);await api(BR_API+'/contracts/'+r.id+'/attachments',{method:'POST',body});if(context!==brContext())return;closeModal();await render();toast('申请附件已保存');});}
function brDeliverySection(r){
 const s=r.delivery_state;if(!s)return '';const d=s.delivery,actions=s.actions||[],gift=s.gift_document;
 return `<section class="panel"><div class="panelhead spread"><div><h2>财务交车与盖章赠品单</h2></div><div class="row">${r.status==='approved'?brFlowButton('gift-print','打印无价格赠品单'):''}${actions.includes('upload_gift_document')?brFlowButton('gift-upload',gift?'追加更正盖章赠品单':'上传盖章赠品单'):''}${actions.includes('confirm_delivery')?brFlowButton('delivery-confirm','财务确认交车','','primary'):''}</div></div><div class="panelbody">${brFacts([['交车事实',d?'财务已确认交车':'尚未确认交车'],['交车确认时间',d?time(d.confirmed_at):''],['核算日期',d?.accounting_on],['对应发票金额',d?brAmount(d.invoice_amount_cents):'待确认'],['盖章赠品单',gift?.filename||'待上传'],['内勤资料条件',s.materials_ready?'材料齐备，可填报延伸资料':'等待发票、交车及盖章赠品单材料']])}${gift?.available&&['admin','finance','clerk','manager','general_manager','group_deputy_manager','chairman','store_admin'].includes(state.user.role)?brFlowButton('gift-download','下载当前盖章赠品单',`data-file="${gift.id}" data-name="${E(gift.filename)}"`):''}</div></section>`+
 `<section class="panel"><div class="panelhead spread"><h2>退车与退款记录</h2>${actions.includes('request_return')?brFlowButton('return-request','销售顾问申请退车'):''}</div><div class="panelbody">${(s.returns||[]).map(item=>`<article class="br-return-card">${brFacts([['退车状态',({submitted:'待总经理批准',requested:'待总经理批准',pending:'待总经理批准',approved:'已批准退车',rejected:'已退回'})[item.status]||item.status],['申请原因',item.note],['请求退款金额',brAmount(item.requested_refund_cents)],['退车批准日',item.approved_on],['另行记录退款合计',brAmount(item.refunded_amount_cents)]])}<div class="row">${(item.actions||[]).map(a=>brFlowButton('return-'+a,({approve:'总经理批准退车',reject:'退回退车申请',refund:'记录已发生退款'})[a],`data-return="${item.id}"`)).join('')}</div>${item.refunds?.length?table(['退款日期','金额','说明'],item.refunds.map(x=>[E(x.refunded_on),brAmount(x.amount_cents),E(x.note)])):''}</article>`).join('')||'<p class="br-caption">暂无退车申请</p>'}</div></section>`;
}
async function brDeliveryAction(action,button){
 const r=brState.detail,context=brContext(),s=r?.delivery_state;if(!s)throw new Error('请刷新合同。');
 if(action==='gift-print')return download(BR_API+'/contracts/'+r.id+'/gift-document/print',r.number+'-赠品单.pdf');
 if(action==='gift-download')return download(BR_API+'/contracts/'+r.id+'/gift-document/files/'+button.dataset.file+'/download',button.dataset.name);
 if(action==='gift-upload'){
  if(!s.actions?.includes('upload_gift_document'))throw new Error('合同状态或岗位权限已变化，请刷新后办理。');
  const requestId=requestKey(),epoch=renderId,current=()=>context===brContext()&&epoch===renderId&&state.route==='records-sales/'+r.id&&brState.detail?.id===r.id;
  modal('上传盖章赠品单',`<form><p class="notice">合同 ${E(r.number)} · ${E(r.customer_name)}</p><label>盖章后的赠品单<input type="file" name="file" accept=".pdf,.png,.jpg,.jpeg" required></label><p class="fieldhelp">PDF、PNG 或 JPEG，单个文件不超过 10MB。请上传已盖章原件；发票另行上传并核实，两项材料齐备后才能确认交车。追加更正保留原件历史。</p><div class="formerror" role="alert"></div><div class="modalfoot">${b('close','取消')}<button type="submit" class="primary">上传并关联本合同</button></div></form>`,async form=>{
   if(!current()||$('#modal form')!==form||!$('#modal').open)throw new Error('合同、门店或账号已变化，请重新打开合同。');
   const file=form.elements.file.files[0];
   if(!file||!file.size||file.size>10*1024*1024)throw new Error('请选择非空且不超过 10MB 的盖章赠品单文件。');
   if(!/\.(pdf|png|jpe?g)$/i.test(file.name))throw new Error('盖章赠品单仅支持 PDF、PNG 或 JPEG 文件。');
   const body=new FormData(form);body.set('request_id',requestId);body.set('version',String(r.version));
   await api(BR_API+'/contracts/'+r.id+'/gift-document',{method:'POST',body});
   if(!current())return;
   if($('#modal form')!==form||!$('#modal').open){toast('盖章赠品单已保存，请刷新本合同查看；当前窗口未改变。');return;}
   closeModal();await render();toast('盖章赠品单已保存');
  });return;
 }
 let title,fields,path,version=r.version,notice;
 if(action==='delivery-confirm'){title='财务确认交车';fields=[F('note','交车确认说明','textarea',false)];path='/delivery-confirm';notice='确认后结束合同交付部分，并抄送总经理。基础销量按对应发票上传日统计，不记录实际到账。';}
 else if(action==='return-request'){title='申请退车';fields=[F('amount','请求退款金额（元）','money_zero',false),F('note','退车原因','textarea')];path='/returns';notice='退车申请交总经理批准；批准当月冲减，原销售事实保留。';}
 else{const item=s.returns.find(x=>x.id===Number(button.dataset.return));if(!item)throw new Error('退车记录已变化。');version=item.version;const suffix=action.slice(7);path='/returns/'+item.id+'/'+suffix;title=({approve:'总经理批准退车',reject:'退回退车申请',refund:'记录已发生退款'})[suffix];fields=suffix==='refund'?[F('amount','实际退款金额（元）','money'),F('refunded_on','实际退款日期','date'),F('note','退款说明','textarea',false)]:[F('note',suffix==='reject'?'退回原因':'审批说明','textarea',suffix==='reject')];notice=suffix==='refund'?'仅记录已经发生的退款事实，系统不执行支付。':'审批结果追加留痕，原合同和交车记录继续保留。';}
 return brForm(title,[{title:r.number,fields}],{},(v,request_id)=>{const body={request_id,version,note:v.note};if(action==='delivery-confirm')body.invoice_version=s.invoice_version;if(action==='return-request')body.requested_refund_cents=v.amount===''?null:moneyFen(v.amount,{allowZero:true});if(action==='return-refund'){body.amount_cents=moneyFen(v.amount);body.refunded_on=v.refunded_on;}return api(BR_API+'/contracts/'+r.id+path,{method:'POST',body});},{draftKey:action+'-'+r.id+'-'+version,submit:title,notice});
}
async function brDeliveryNotices(){const context=brContext(),result=await api(BR_API+'/delivery-notices');if(context!==brContext())return;modal('财务交车抄送 · 总经理查阅',`${table(['合同','车型','核算日期','财务确认时间'],result.items.map(x=>[brLink('records-sales/'+x.contract_id,x.number),E(x.model),E(x.accounting_on),time(x.confirmed_at)]))}`);}
function brProfitPanel(calculation){
 if(!calculation)return '<div class="br-profit-panel"><h3>核定单车大毛利</h3><p>填写延伸资料后自动汇总原表利润。</p></div>';
 const complete=calculation.status==='complete';return `<section class="br-profit-panel"><div class="br-profit-head"><div><h3>核定单车大毛利</h3><p>${complete?'全部计算项已核实':'待补齐 · '+calculation.missing.length+' 项尚未填写'}</p></div><strong class="br-profit-number">${complete?E(brAmount(calculation.total_cents)):'待补齐'}</strong></div>${!complete?`<p class="br-profit-subtotal">已填项目小计：${E(brAmount(calculation.known_subtotal_cents))}（不是最终利润）</p>`:''}<div class="br-profit-items">${calculation.items.map(item=>`<div class="${item.amount_cents==null?'br-profit-missing':''}"><span class="br-profit-sign">${item.sign<0?'−':'+'}</span><span>${E(item.label)}<small>原表 ${E(item.source_column)} 列</small></span><strong>${item.amount_cents==null?'待补齐':E(brAmount(item.amount_cents))}</strong></div>`).join('')}</div></section>`;
}
function brOfficeSectionV210(r,actions){const data=r.office_data||{};if(!r.office_status&&!r.office_data)return '';return `<section class="panel br-office-panel"><div class="panelhead spread"><div><h2>销售内勤延伸信息</h2><p class="br-caption">${E(BR_OFFICE_STATUS[r.office_status]||'等待财务材料')}</p></div><div class="row">${actions}</div></div><div class="panelbody">${brFacts([['车型',r.model],['客户',r.customer_name],['核算日期',r.delivery_state?.delivery?.accounting_on],['发票金额',brAmount(data.invoice_amount_cents??r.delivery_state?.delivery?.invoice_amount_cents)],['核对说明',data.note],['全损出单数量',data.extension_data?.total_loss_count??'待补齐'],['小产品出单数量',data.extension_data?.product_count??'待补齐'],['二手车置换数量',data.extension_data?.trade_in_count??'待补齐']])}${brInternalRead()?brProfitPanel(data.profit_calculation):''}${data.values?`<details class="br-disclosure"><summary>查看已填原表项目</summary>${table(['项目','填写值'],(brReportDefinitions().find(s=>s.key===data.report_key)?.columns||[]).filter(c=>data.values[c.key]!=null).map(c=>[E(c.label),E(data.values[c.key])]))}</details>`:''}</div></section>`;}
async function brOfficeEditV210(reportKey){
 const r=brState.detail;if(r?.workflow_version!=='trial-v210')return brOfficeEditLegacy(reportKey);if(!r.actions?.includes('office_edit'))throw new Error('请先完成财务交车及材料上传。');
 const existing=r.office_data||{},definitions=brReportDefinitions().filter(s=>s.supports_contract),key=existing.report_key||reportKey;
 if(!key){modal('选择本车原始明细表',`<div class="br-report-picker">${definitions.map(s=>brButton('office-report-select',s.title,`data-report="${E(s.key)}"`)).join('')}</div>`);return;}
 const spec=definitions.find(x=>x.key===key);if(!spec)throw new Error('当前岗位无法填写此表。');const context=brContext(),prefill=await api(BR_API+'/report-prefill?'+new URLSearchParams({report_key:key,contract_id:r.id}));if(context!==brContext())return;
 const values={...prefill.values,...existing.values},computed=await api(BR_API+'/contracts/'+r.id+'/profit-preview',{method:'POST',body:{report_key:key,values}});if(context!==brContext())return;
 const locked=new Set(prefill.locked_fields||[]),hidden=new Set([computed.profit_calculation.output_key,...(['vehicle_details','hail_vehicle_details'].includes(key)?['c06']:[])]);
 const columns=spec.columns.filter(c=>!hidden.has(c.key)&&!['序号','台数','车系'].includes(c.label)&&!locked.has(c.key));
 const groups=brOfficeGroups(columns).map(group=>({...group,fields:group.fields.map(f=>{const c=columns.find(c=>'value_'+c.key===f.key);if(c?.label==='订单类型')return F(f.key,c.label,'select',false,[{value:'',label:'待填写'},...brChoice(['自然进店成交','线上客户成交'])]);if(c?.label==='现金或三方')return F(f.key,'现金或三方','select',false,[{value:'',label:'待核对'},...brChoice(['现金','三方'])]);return f;})}));
 const extensionFields=[F('total_loss_count','全损出单数量（无此业务填0）','int',false),F('product_count','小产品出单数量（无此业务填0）','int',false),F('trade_in_count','二手车置换数量（无此业务填0）','int',false)],noteField=F('note','核对说明 / 待补资料','textarea',false);
 const initial={note:existing.note||'',...Object.fromEntries(extensionFields.map(f=>[f.key,existing.extension_data?.[f.key]??''])),...Object.fromEntries(Object.entries({...values,...computed.values}).map(([k,v])=>['value_'+k,v??'']))},allFields=[...extensionFields,noteField,...groups.flatMap(g=>g.fields)];
 const collect=v=>Object.fromEntries(spec.columns.map(c=>[c.key,locked.has(c.key)?prefill.values[c.key]??null:hidden.has(c.key)?null:v['value_'+c.key]??values[c.key]??null]));
 const dialog=await brForm('销售内勤核对 · '+spec.title,[{title:'延伸业务及资料核对',fields:[...extensionFields,noteField]},...groups],initial,(v,request_id)=>api(BR_API+'/contracts/'+r.id+'/office-review',{method:'PUT',body:{request_id,version:r.version,report_key:key,note:v.note,cash_consumption_cents:existing.cash_consumption_cents??null,extension_data:Object.fromEntries(extensionFields.map(f=>{const value=v[f.key];if(value!==''&&value!=null&&(!Number.isInteger(value)||value<0||value>10000))throw new Error(f.label+'须为0至10000的整数');return [f.key,value===''||value==null?null:value];})),values:collect(v)}}),{draftKey:'office-'+r.id+'-'+key+'-'+r.version,submit:'保存延伸资料',notice:'发票上传日作为核算日。返佣、小产品净额自行核算填写，空值表示待补齐；明确没有该项时填 0。最终单车利润由系统汇总。'});
 const form=$('form',dialog),top=document.createElement('div');top.className='br-office-fact-head';top.innerHTML=brFacts([['客户 / 车型',r.customer_name+' / '+r.model],['核算日期',prefill.period||r.delivery_state?.delivery?.accounting_on],['客户付款方式',r.terms?.submission_data?.payment_method],['库存资金性质',brCashVehicleLabel(r.terms?.submission_data?.is_cash_vehicle)],['现金车消化金额',r.terms?.submission_data?.is_cash_vehicle===true?brAmount(r.sale_price_cents):r.terms?.submission_data?.is_cash_vehicle===false?'不计现金车消化':'待核对现金车标记'],['财务核对发票金额',brAmount(r.delivery_state?.delivery?.invoice_amount_cents)],['自动带入赠品金额',brAmount(computed.gift_cost_cents)]]);form.querySelector('fieldset').before(top);
 const profit=document.createElement('div');profit.dataset.profitPreview='';profit.innerHTML=brProfitPanel(computed.profit_calculation);form.querySelector('.modalfoot').before(profit);
 let timer=null,sequence=0;form.addEventListener('input',()=>{clearTimeout(timer);const run=++sequence;timer=setTimeout(async()=>{if(!form.isConnected||context!==brContext())return;try{const result=await api(BR_API+'/contracts/'+r.id+'/profit-preview',{method:'POST',body:{report_key:key,values:collect(formValues(form,allFields))}});if(run!==sequence||!form.isConnected||context!==brContext())return;profit.innerHTML=brProfitPanel(result.profit_calculation);}catch(error){if(run===sequence&&form.isConnected)profit.innerHTML=`<div class="notice warn">利润待核对：${E(error.message)}</div>`;}},450);});
}
document.addEventListener('click',async event=>{const el=event.target.closest('[data-br-flow]');if(!el||el.disabled||state.storeSwitch)return;const a=el.dataset.brFlow;if(!['delivery-notices','contract-attachment','pricing-download','gift-print','gift-upload','gift-download','delivery-confirm','return-request','return-approve','return-reject','return-refund'].includes(a))return;el.disabled=true;try{if(a==='delivery-notices')await brDeliveryNotices();else if(a==='contract-attachment')await brContractAttachment();else if(a==='pricing-download')await download(BR_API+'/pricing/files/'+el.dataset.file+'/download',el.dataset.name);else await brDeliveryAction(a,el);}catch(error){toast(error.message,true);}finally{if(el.isConnected)el.disabled=false;}});
