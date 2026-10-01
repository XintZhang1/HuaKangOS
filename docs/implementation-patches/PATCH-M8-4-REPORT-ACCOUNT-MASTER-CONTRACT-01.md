# PATCH-M8-4-REPORT-ACCOUNT-MASTER-CONTRACT-01

2026-10-01，当前浏览器点击连续授权内先登记。reports-complete-source02 的原新银行账户 POST201/列表 GET200 成功，实际 Account3/store3/本人主管12 与唯一 Audit833 成立；候选套用了强制 request_id 的 Dossier helper，事后误报“原请求缺员工此次请求编号”。原 flow_api.MasterInput 只有 values/可空 version，extra=forbid；原新建账户 UI 不发送 request_id，也没有 FlowReceipt。它不是后端未生成幂等编号的缺陷。

其余三个关联实例仍运行，生产/registered/runner冻结，全部退出前只登记不实施。只修改 report_complete_source_business.py 的这一个银行账户保存：复用已有 master_data_business.submit_original 的原 POST201/固定列表 GET200/Cookie/CSRF/当前店和零资金库存变更合同；额外监听同一原提交检查 x-app-request，严格请求键和值、原响应/数据库/列表/可见行一致，唯一原 master_create/flow_master 审计和全部旧行保护。元数据 request_id_sha256 必须为 None，不能伪造编号或回执、全局放宽 ACCESS.meta、修改生产 schema、重放已成功 Account3 或任何直接正向HTTP/SQL写。

原供应商 typed master、Item、原动作及原幂等回执保持。新镜像从真实新店和原角色前序重新建立银行账户与后续采购；失败原件与旧指纹保留。AST/独立精确源审后只复验这个报表最小闭包，之后完整注册联合按当前指纹执行。原193人工/真实日期/历史期间与环境门槛、四默认关闭开关不变。
