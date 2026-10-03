# 原业务详情到既有领域快照的接线修复

2026-10-04，M8.2 当前收口发现的原 M7 实现缺陷；不是新增业务目标。v8 CI37149849322 双平台均已终局失败，旧输入及报告保留后才修改。当前仍只维护 M8.2 一个 in_progress。

只读对照真实 API 与已登记适配器确认：客户车辆 GET 返回 vehicle/observations/effective_observations，原观察日期为 observed_date，历史摘要只有本店 case_id/external 而无 link.id；售后 GET 已按员工/本店/aftercare-v2 校验，详情不返回 store_id/kind；整车操作详情的同原 Case open-task 摘要不返回 case_id。原模拟形状不能证明这些真实接线通过。

生产范围仅 app/assistant_runtime_domains/customer_vehicle.py、aftercare.py、vehicle_operation.py。客户车辆严格核原 vehicle.id、版本与两类观察的独立语义，创建/观察/关联结果取真实 vehicle.id；原更新常量按 reviewed PUT 核对。历史只按原已授权本车查询中 external=false 且 case_id 的真实本店来源证明关联，外店摘要不表示本车本店关联或原单/附件权限，不造 link.id。售后保留原身份、门店、类型及版本守卫，使用原专用 GET 合同及必要的已登记原 Flow 读取，不向原 API 填 mock 字段。整车操作只投影原 GET 已筛选的真实 Case→Task 关系，未提供的 key/status/version 保持未知，不猜业务完成。

外部验证范围仅 V/tests/baseline/overlay/tests/runtime_domains/test_customer_vehicle.py、test_aftercare.py、test_vehicle_operation.py 的已登记旧节点：按真实 API 返回调整夹具并保留原权限/ID/故障/事实断言，原 archive 不改。另在现有 V/tests/m82-closeout/shared-contracts/test_http_privacy_workspace.py 添加一个组合节点，经原员工 HTTP API 实际取得三个领域的详情/任务/观察/历史后走当前适配器，证明真实输入到结果，使用既有 contract_runtime 及隔离守卫，无新 runner/框架。只更新上述原来源 SHA、明确适配差异和实际 collector 数组，原 101 命令、每项原预算、全部其它节点不减。

售后同文件局部事实范围补记：原 describe 的当前方案是顶层 plan_id，plans[].customer_confirmed 是原 AftercareConsent 存在投影，refunds[].id/tender_id/payment_link_id/amount_cents 是本单原 AftercareCashRefund 与真实 PaymentLink 关联投影，按原 MONEY 读取权限提供。修现有三个 fact 与 extract_result 对伪 data/consent_id/cash_refund_id/store_id/kind 的依赖，不新增事实键；只核真实当前 plan_id 对应方案，不选择第一份历史方案、批准不算生效、已确认的旧取消方案不算当前同意、非现金权益不算实际退款。退款清单因岗位不可读时未知，不扩原 API 或权限。

root 静态注册配对补记：__init__.py 的 vehicle_operation、vehicle_purchase、aftercare 三项已有 fact_kind_versions，却漏传本来已 import 的 OPERATION_FACTS、PURCHASE_FACTS、AFTERCARE_FACTS，真实 spec_for_fact 不会找到它们。允许仅这三 spec 添加原 fact_keys，不新增任何键或操作。客户车辆旧 UPDATE 常量误指 CREATE；原 reviewed PUT 更新及原 CareReceipt 已存在，允许在同一个 __init__.py 的客户车辆 import/导出/spec 与 customer_vehicle.py 原 result/receipt 有限集合中补真实 VEHICLE_UPDATE，不改 gateway/catalog/API 或确认守卫。既有旧节点另核实际 registry 能找到原已声明 fact/provider 和 PUT，仍不减少原节点。

同时修本轮矩阵 generator 已观察的 KeyError: options：临时补填问题使用原描述函数的完整输入字段 options=[]，不修改生产表单边界、不改原矩阵断言。原失败/源/差异外置留存。所有修改后须新完整收集、同新五输入 strict 和双平台 full；旧 strict/局部结果不继承为新通过。四缺失正文合同及专用回执的独立审阅缺口继续登记，未完成不能记全 M7 或项目已达到人工验收。
