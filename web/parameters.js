'use strict';
const deploymentLabels={timezone:'业务时区',session_hours:'登录有效时长（小时）',inventory_aging_days:'库存库龄提醒（天）',repair_overdue_days:'维修超期提醒（天）',receivable_grace_days:'应收宽限（天）',low_margin_percent:'低毛利提醒（%）',large_cash_yuan:'大额收支提醒（元）',discount_review_percent:'折扣复核提醒（%）',daily_report_hour:'每日日报时刻（小时）',daily_report_minute:'每日日报时刻（分钟）'};
async function parametersPage(){
 const data=await api('/api/parameters/catalog');
 const entries=data.entries.map(item=>panel(item.label,`<p>${E(item.description)}</p><p class="fieldhelp">${item.can_write?'按当前岗位在原页面配置；需要复核的规则仍执行原复核。':'当前岗位只读；修改仍需对应管理岗位。'}</p>${b('open','进入原配置',`data-route="${E(item.route)}"`)}`)).join('');
 const deployment=data.deployment?panel('部署参数（只读）',facts(Object.fromEntries(Object.entries(data.deployment).filter(([key])=>Object.hasOwn(deploymentLabels,key)).map(([key,value])=>[deploymentLabels[key],String(value)])))+'<p class="fieldhelp">这些部署级参数由部署负责人在 .env 中维护并重启服务生效。业务规则在上方各自原页面修改，不接受任意键值配置。</p>'):'';
 return heading('参数与个人密码','规则留在原业务中管理，避免重复配置与历史数据被倒改。')+storeNotice()+panel('个人密码',`<p>验证原密码后设置新密码；其他登录会话失效。</p>${b('password','修改本人密码','','primary')}`)+`<div class="notice">${E(data.notice)}</div>`+(data.aggregate_scope?'<p class="notice">请切换到具体门店查看原业务配置入口。</p>':`<div class="chartgrid">${entries}</div>`)+deployment;
}
