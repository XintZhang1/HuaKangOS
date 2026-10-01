# HK038 原责任与新增自费返修点击候选

2026-10-01；精确范围 `PATCH-M8-4-BUSINESS-193-30`。仅新增本任务页及 `tests/browser_click/repair_rework_business.py`；生产、夹具、目录、注册、共享 helper、计划和其它脚本均只读。候选未注册、未执行，不登记业务通过，不继承父项或静态审阅成绩。

## 原合同与最小代表例

原题名为 **HK-038 返修单**，稳定检查 `HK-038-business`。原已实际接车维修的唯一明确作业行作为责任源；复用其当前本店客车、共享身份、VIN 和已释放工位。主管通过原主档表单新增一项明确 20 元自费 `job` 作业，原责任金额取该真实原行，本例没有材料领退、未知成本或虚构余额。

1. 服务顾问在原已完成维修上传本次责任核验原件，由“原责任与新增自费返修”原入口明确原单、原行、原店、原客车及真实本人接收人，填原责任限额及两天接收期限。原 `POST /api/rework-extensions/grants` 创建冻结授权。
2. 不同主管按原授权页独立批准；指定服务顾问通过原“核对并建立本店返修申请”按钮领用，建立本次 `ReworkRequest` 和 `ReworkExtension`。授权批准与消耗决定独立保留，不能直接生成维修、现金或库存。
3. 本店另一主管原任务复核责任，冻结主体沿已批准授权；服务顾问原任务记录同 VIN、明确现场里程 37000、独立凭据及交接日期，通过原返修转换建立新的 v4 `repair`。
4. 两行 `ScopeQuote` 明确 `original_liability` 和 `customer_extra`，原行引用获准责任项目，新自费行不填原责任 ID。冻结摘要、分类及金额对应，另一主管独立价格审批、客户本版授权，技师实际开工/完成，服务顾问独立合格质检。
5. 主管原“核对冻结行承担”将原责任分给冻结内部主体、20 元新增费用分给客户，明确本次人工成本 10 元。财务当前原任务登记唯一新增自费 20 元实收，形成独立 `RepairPayment/PaymentLink/CashEntry`；内部责任无现金。服务顾问另行记录实际接车，完成新维修和父返修申请、释放工位。刷新真实页面并校验零重复事实。

原扩展返修入口的 `ReworkConvert` 将现场核 VIN、里程和凭据保存在 `intake_rework_convert` 原事件，并生成 `RepairVehicleBinding`，**不产生预约的 `intake_arrivals` 行**。候选精确验该原返修现场核验和转换合同，不伪造预约、ArrivalFact 或 GateVisit；公开报告包含此区别。原预约维修的 ArrivalFact 不继承为本次到店。

## 同轮有限前置与接线

父项均须当前 `evidence_root/browser-click-report.json` 中真实 `passed`，各固定 `business-checkpoint.json` 完整通过，目录和本次来源指纹一致。七父：售前、车辆采购、主档、客服、整车交付、物资、首维修。首维修 `report_sources` 明确原维修/报价/承担/原款、客车/VIN；客服 HK099 仅本店已实测局部车辆来源；没有把 HK099 全项升级。原客车和物料余额按当前事实重读，不要求等于旧版本/旧全行。

依赖现有 `business_fixtures.repair`：`store_id/service_key/manager_key/technician_key/finance_key/inventory_key`。分别核登录身份、本店真实 `UserStore` 原岗位及启用状态。原任务由负载路由给其他演示员工时，主管通过原三字段 `AssignInput(version,assignee_id,reason)` 明确交接，再由选定岗位本人办理；不改 SQL、不借管理员替身、不添加随机角色。

导出 `REPAIR_REWORK_SCENARIOS=(("repair-rework-hk038", repair_rework_business, 600),)`。根须在镜像白名单包含新文件并在七父之后注册；单选缺父明确失败。本候选不依赖尚未实测的核赔新来源，不跨 run 扫描历史原单。无需共享框架或 fixture 业务结果。

## 证据与保护

每次正向提交都通过可见原表单；采集同源原 Cookie/CSRF/门店响应、真实 POST、原 GET、当前 CAS、实际 Task 和原回执。授权回执精确核 `digest([action,payload])`，接待回执核 `intake_*` 家族及保存结果，维修回执保留原 `repair_v3_*` 家族（v4 仍使用该家族）；仅按当前 schema 恢复默认字段和 UTC 序列化，不更换请求编号重放。

原全业务摘要对照覆盖旧行更新而非仅计数。追加表逐项受限，已存在行只允许本次新 Case/Task/ReworkRequest、当前授权状态、当前工位/客车、实际账户等有限 ID 和列；原责任、报价分类、原款和历史不覆盖。原来源责任附件/事件合法追加后固定原维修完整事实基线，之后新维修全程不得再改原源。其它会员、现金、库存和他店旧行保持。上传字节由原文件流程验 sha/size、原结构检查；BLOB 仅守卫内存比较，报告只存元数据、长度和哈希。

外部 `business-checkpoint.json` 逐阶段保存 `HK-038`、原责任授权、接收与转换、双行报价、实际施工质检、分摊、原款和接车事实。任何错误停止并终结为失败，不留 `running` 或未知结果成功。只有此一项实际完整通过后输出 `rework_sources/report_sources`：客户/客车/VIN、原维修/报价/行、授权、新申请/接待/维修/报价/工位、两承担、实际原款及新作业有限 ID、`actual_new_selfpay_cents=2000`。

## 静态交付与未测边界

完成原 `rework_extension_api/service/models`、`service_intake_api/service/models`、`repair_api/service/models` 与实际 `web/reworkextensions.js/serviceintake.js` 选择器/字段合同核对。仅做 AST、三元导出、源码导入边界、只读 SQL/无正向 API 或浏览器状态注入、空白检查；未导入应用或运行实例。实际页面时序、HTTP、施工/到账与 Guard 动态结果均待根独立短审及全新隔离执行。

条件未测：跨店接收、所有拒绝/撤销/过期、材料和外部责任款、PDI、现金误记更正、真实银行/现场/公司主体策略、ClamAV、PostgreSQL、Linux、员工试用。`full_193_business_acceptance=false/business_accepted=false/human_acceptance=pending`；前端预期/后端事实/硬 bug/来源完整性由此次实际链证明，简易流程和简洁文案仍需独立人工审阅，不声称效率提升。
