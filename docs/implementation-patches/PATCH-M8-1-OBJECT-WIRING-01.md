# PATCH-M8-1-OBJECT-WIRING-01：补齐非 Case 对象实际分派

日期：2026-09-30。依据：本轮热重载实际代码确认 `read_object` 只查 `fallback_object_types`/Case kind，而大部分非 Case 适配器仅登记 object_types，导致公开条件读取在精确 fact provider 之前固定 501。逐域直接调用的旧测试未验证此接线。

顺序：M7.7.3/M7.7.5 补齐后，重开 M8.1 集成补丁；一次仅一项 in_progress。

## 精确范围

- `app/assistant_runtime_domains/__init__.py`：为已存在唯一 provider 的以下对象明确登记同名快照分派，不改变 registry 选择算法或新增 provider：typed_master 的 vehicle_brand/vehicle_series/supplier/insurer/warehouse/storage_location/material_brand/material_category/master_work_item/team/agency_project/vehicle_model/member_tier/item_profile；customer_care 的 care_case；customer_vehicle；dossier_grant；escalation_request 的 escalation/refusal；gate_visit；transfer_goods_recovery 的 goods_recovery；material_transfer；member_price 的 member_pricing_rule；care_reminder 的 reminder_rule；retail_bundle 的 retail_bundle_rule/retail_bundle_sale；rework_grant 的 rework_source_grant；service_intake 的 service_appointment；transfer_exception；vehicle_import_batch；vehicle_transfer；vehicle_transport_exception；reconciliation_batch。
- group_member 的唯一快照为 group_principal、package_purchase 为 repair_package，已在前补丁接线；共享 report_query、需冻结查询/目录上下文的 dictionary_entry、封闭 daily_report 不盲绑通用对象入口，继续明确不支持。
- 同文件补登记 `vehicle_import_batch` 已实现的 `IMPORT_READ`；原适配器已使用原活跃只读路由，GET 目录由原 OpenAPI 发现，registry 漏登导致有限 reader 拒绝。写操作仍要求 reviewed capabilities，不把只读发现称为新增写入评审。
- `app/assistant_runtime_domains/group_principal.py`：原详情流水字段为 purpose，事实却读取 kind，修为 purpose 并保留存在性/截断说明；会员编号使用原 number，不猜姓名或业务完成。
- 更新本项计划记录、审阅报告与必要新浏览器合成场景。其它生产文件、原工作流/迁移/总计划只读。

## 边界与验证

每个适配器仍重走原受控 GET 的即时身份、门店、岗位、对象与资源守卫；fallback 仅确定固定 provider，绝不授权。未知对象、旧 flow_version、共享 Case 与任意 report_query 不能静默选第一个。不能把旧直接 adapter 测试计数继承为新公开路径验收；新脚本以原 API/浏览器点击及数据库事实核对覆盖代表路径，其余域完整实环境验收仍按原计划保留。
