# PATCH-M8-5-SOURCE-DISCOVERY-12

2026-10-07；当前 M8.5。沿业主已授权真实模型复验的有限缺陷修复执行，不改变业务规则或验收口径。

## 实际问题与原因

冻结 `bd517e0` 的九例实测 `20261007T045227Z-11b4e3642f` 中，V03 正确等待真实采购原单和到货事实、没有制卡，但把批量清单导入的已确认请款行要求说成原生逐 VIN 验收入库的统一前置。原 `vehicle_procurement_service.py` 的 ship/receive 并无该请款前置；批导入另按 `vehicle_imports_service.py` 的来源行合同办理。

本例 `find_workflows(query="整车入库")` 实际返回调拨、批量导入、车辆目录三条，未返回 `wf-vehicle-purchase`。检索只在散文片段命中、同分按标题排序且上限为三条；原生采购指引缺少这个员工搜索关键词。不能仅因批导入指引可检索，就把其来源行规则推广至原生验收。

同轮 F05 在尚未选来源、也未读取购买方资料时，承诺买方抬头和税号会自动从客户/业务资料取得、无需员工提供。普通业务来源的 `source_basis` 只返回已确认金额依据，原开票页面仍要求明确购买方资料；保险佣金、整车其他收入和红票另按各自真实快照办理。原 `Create` schema 没有描述购买方事实来源，本例实际调用的 `inspect_operation` 已返回该原 schema，故在原字段补准确说明，不再增加全局提示词。

## 精确允许范围

- `docs/workflow-source/business.json`：只给 `wf-vehicle-purchase.keywords` 增加“整车入库”。
- `app/invoice_api.py`：仅在 `Create.buyer_name`、`buyer_tax_id` 原 Field 添加事实来源说明；类型、默认值、校验和业务守卫不变。红票沿用原票、特殊来源快照及普通个人税号可空保持。
- 通过既有 `scripts/build_workflow_guides.py` 同步 `web/workflow-guides.json`、`web/workflow-handbook.html`、`docs/全量工作流手册.html`。
- 本补丁、当前 M8.5/CP-37 登记、对应 checkpoint、两份 architect 进度文档。

不改变检索算法、结果上限、指引业务步骤、业务 API 的运行行为、确认/岗位守卫、原 283/101 场景或预算历史。V03 未确认实际到货仍须等待；添加关键词不证明原单存在或本人具备办理权限。购买方信息可以沿用已经核实的事实，但没有事实时必须由员工明确核对，不能猜填。

## 验证与状态

先按生成器核对发布产物和限定差异，经独立有限静审；冻结新源码后按原 runner 执行同输入隔离自检及受影响原例真实复验。原九例报告保留，不能拼入最终从零 283；结构和语义逐例分别记录。M8.5 保持 in_progress，M8.6 todo，CP-37 not_ready。
