# PATCH-M8-1-REGISTRY-01 · 修复真实 Runtime 注册阻断

真实 HTTP 登录后 POST sessions/{id}/runs 在构建 RunView 时触发 DomainRegistry.register ValueError。当前完整注册入口不是可用状态；历史单域/源码断言不证明整体入口可运行。

本次保持 Registry 严格唯一性和版本适用性校验不变，仅修正静态登记：

- 对已有 Case 事实提供者补全原 native service 明确支持的 kind/flow_version 适用性。只登记 fact_kind_versions，不自动把未经本轮逐域验证的专用快照改为 Case 默认读取器。
- lead 的共享 Flow operation 仍唯一归 flow_case，lead 只登记版本对象选择器。
- 采购预付只登记事实适用性，公共采购 operation 唯一归 material_procurement。原共享回执族不变。
- 集团本金不抢占属于权益的 benefit action；原本金 adapter 仅登记其已评审 GET。不新增本金支付或清算入口。

原版本依据：service_orders_service.is_detailed；addon_service.is_detailed；insurance_service.is_detailed；invoice_service 的 v3；business_finance_service v2；membership_service v2；recharge_bundle_service v2；warehouse_service v2；procurement_service v2/v3（预付仅 v3）；retail_service v2；claims_service v2；repair_service.is_detailed v3/v4。

复验：完整 sealed registry、共享 operation 的唯一所有者、错误 kind/version 不能满足事实、真实 HTTP Run 创建和重复提交、真实 worker/模拟 provider 流程。测试数据和脚本均在仓库外；不接触原预览库/真实密钥。
