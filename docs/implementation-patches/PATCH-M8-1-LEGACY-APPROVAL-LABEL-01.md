# PATCH-M8-1-LEGACY-APPROVAL-LABEL-01：库存审核与工作流状态分别显示

日期：2026-10-01。全新隔离 `business-vehicle-purchase-20261001-02` 同次完成采购、独立付款、两VIN验收及目录参数筛选，但HK-029失败：车辆真实 `approval_state=approved`，列表审核列显示“已批准待办理”，而原审核合同及原筛选标签应为“已审核”。本轮保留failed及真实入库事实，不降低候选断言。

根因：通用 `pill` 优先读取 `state.catalog.states`，其中工作流的 `approved` 是“已批准待办理”；原库存/现金审核同名枚举经 `legacyCell` 调用时被工作流词义覆盖。`legacyDetail`标题同样受影响。原原单金额、库存、审核/权限守卫及API状态没有错误。

精确范围：`web/app.js`仅原记录 `approval_state`单元格与 `legacyDetail`审核标题显式传入已有原 `labels` 的展示文字。通用 `pill`顺序、工作流待办理状态、库存可售字段、原审核状态API/权限及生产开关均不改；未知原审核值仍明确展示原值。相关实施记录及审阅说明追加事实。

验证：保留采购候选严格“已审核”断言，全新外部实测；IAB实际原库存列表/详情复核与数据库 `approved` 一致，工作流批准后的待办理说明仍原合同。源码语法和定向差异检查后运行当前注册链。完整193业务、银行/实物真实性、ClamAV、PG/Linux和员工试用仍另有条件。
