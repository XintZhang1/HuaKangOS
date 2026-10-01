# PATCH-M8-1-REVIEWED-SHORT-WRITERS-01

2026-10-01，M8.1 同一实施项，持续浏览器点击交付授权。财务07、应收06、报表05均已完整失败并自然收尾；本补丁登记前已核对对应 Python 与监听不存在。失败原件保留，不继承旧成绩、不重试或重放同一提交。

## 真实原因及精确范围

当前源码 57e90e30e2c5f5fa892beb26d7b57b0ded599b68422a9f6fa98795f469f410e0、脚本 02c316bac9eb1903554159c9bfab92620610ff7613ae0fd7d059a1da8fcd5307。财务07第二型号保存及客服开始、应收06采购审批、报表05采购付款均遇原同步业务写入口读后升级竞争；服务器记录 SQLite code5，部分 run 还有517，日志未含精确 SQL 路径，不把每条517强配给特定提交。原单、本人待办与旧事实守卫成立，失败完整回滚，非单号/CAS/岗位规则缺陷。Worker 已离开 Web loop；报表05原错密码负路已实际通过，该修复保留。

只修改 app/db.py 的 get_write_db SQLite 分支：在首次 Connection 前把同一个请求 Session.bind 换为原 bind.execution_options(huakangos_sqlite_write_transaction=True) 的 OptionEngine，再取得 db.connection()。原 Engine、共享 pool、SessionLocal 和默认 get_db 不改。该请求每次 commit/rollback 后下一事务仍保留 BEGIN IMMEDIATE，PG 不进入此分支。认证与原业务同 cached Session；get_audited_read_db alias 保持。

另只在下列 41 文件的 127 个精确原同步业务写函数中，将122个 get_db 参数换为 get_write_db，补各文件对应导入；已有5个保持。唯一 vehicle_imports_api.command 将 db 参数移到 user 前。仅此导入、签名依赖与顺序，函数体、decorator、schema、原服务、能力目录、权限/CAS/幂等/提交次数和事实不变。普通读、模型/SSE/await、Worker、管理闭面/扫描/异步上传及另开 Session 的 refusal 不是本127自动范围。

精确依据 docs/architect/tasks/reviewed-short-writers.md，SHA d264ecc5b3b7c6269c89b863ec5de13b1e595117391606c6834b46c58cfe2057；外部只读数据清单 V/browser-click/launches/reviewed-short-writers-127.json，SHA f368df1018df2a4eb2f662ceba3a859f1a78badc75e1f1b10ad36d847f2cc521。能力清单仍291操作/127真实写，未新增模型提交能力。全部同步/实际写/无await，41 router、127 decorator、56 include_router无提前认证依赖已人工审阅。

| 文件 | 函数 | 原业务操作 | 原依赖 |
|---|---|---|---|
| `app/addon_api.py` | `command` | `POST /api/addon-orders/{key}/actions/{action}` | `get_db` |
| `app/addon_api.py` | `create` | `POST /api/addon-orders` | `get_db` |
| `app/aftercare_api.py` | `command` | `POST /api/aftercare/orders/{case_id}/actions/{action}` | `get_db` |
| `app/aftercare_api.py` | `create` | `POST /api/aftercare/orders` | `get_db` |
| `app/business_finance_api.py` | `command` | `POST /api/business-finance/orders/{key}/actions/{action}` | `get_db` |
| `app/business_finance_api.py` | `create` | `POST /api/business-finance/orders` | `get_db` |
| `app/claims_api.py` | `command` | `POST /api/claims/{case_id}/actions/{action}` | `get_db` |
| `app/claims_api.py` | `create` | `POST /api/claims` | `get_db` |
| `app/customer_service_api.py` | `action` | `POST /api/customer-service/cases/{case_id}/actions/{action}` | `get_db` |
| `app/customer_service_api.py` | `edit_vehicle` | `PUT /api/customer-service/vehicles/{vehicle_id}` | `get_db` |
| `app/customer_service_api.py` | `generate` | `POST /api/customer-service/reminders/generate` | `get_db` |
| `app/customer_service_api.py` | `link_history` | `POST /api/customer-service/vehicles/{vehicle_id}/history-links` | `get_db` |
| `app/customer_service_api.py` | `new_case` | `POST /api/customer-service/cases` | `get_db` |
| `app/customer_service_api.py` | `new_grant` | `POST /api/customer-service/history/grants` | `get_db` |
| `app/customer_service_api.py` | `new_rule` | `POST /api/customer-service/reminders/rules` | `get_db` |
| `app/customer_service_api.py` | `new_vehicle` | `POST /api/customer-service/vehicles` | `get_db` |
| `app/customer_service_api.py` | `observation` | `POST /api/customer-service/vehicles/{vehicle_id}/observations` | `get_db` |
| `app/customer_service_api.py` | `questionnaire_propose` | `POST /api/customer-service/questionnaires/versions` | `get_db` |
| `app/customer_service_api.py` | `questionnaire_review` | `POST /api/customer-service/questionnaires/versions/{version_id}/review` | `get_db` |
| `app/customer_service_api.py` | `revoke` | `POST /api/customer-service/history/grants/{grant_id}/revoke` | `get_db` |
| `app/customer_service_api.py` | `update_rule` | `PUT /api/customer-service/reminders/rules/{rule_id}` | `get_db` |
| `app/dictionary_api.py` | `create` | `POST /api/dictionaries/{group}` | `get_db` |
| `app/dictionary_api.py` | `update` | `PUT /api/dictionaries/{group}/{record_id}` | `get_db` |
| `app/dossier_grant_api.py` | `action` | `POST /api/dossier-grants/{grant_id}/actions/{action}` | `get_db` |
| `app/dossier_grant_api.py` | `propose` | `POST /api/dossier-grants` | `get_db` |
| `app/escalation_api.py` | `submit` | `POST /api/escalations` | `get_db` |
| `app/flow_api.py` | `act` | `POST /api/flow/cases/{case_id}/actions/{action}` | `get_db` |
| `app/flow_api.py` | `add_master` | `POST /api/flow/master/{kind}` | `get_db` |
| `app/flow_api.py` | `assign_task` | `POST /api/flow/tasks/{task_id}/assign` | `get_db` |
| `app/flow_api.py` | `create_case` | `POST /api/flow/cases` | `get_db` |
| `app/flow_api.py` | `edit_master` | `PUT /api/flow/master/{kind}/{record_id}` | `get_db` |
| `app/flow_api.py` | `generate` | `POST /api/flow/cases/{case_id}/documents` | `get_write_db` |
| `app/gate_visit_api.py` | `command` | `POST /api/gate-visits/{key}/actions/{action}` | `get_db` |
| `app/gate_visit_api.py` | `correct` | `POST /api/gate-visits/{key}/corrections` | `get_db` |
| `app/gate_visit_api.py` | `create` | `POST /api/gate-visits` | `get_db` |
| `app/gate_visit_api.py` | `repair_exit` | `POST /api/gate-visits/repair-orders/{key}/departure` | `get_db` |
| `app/gate_visit_api.py` | `review` | `POST /api/gate-visits/corrections/{key}/actions/{action}` | `get_db` |
| `app/group_api.py` | `issue_member` | `POST /api/group/members` | `get_db` |
| `app/group_api.py` | `link_identity` | `POST /api/group/identities/link` | `get_db` |
| `app/group_api.py` | `member_action` | `POST /api/group/members/{member_id}/actions/{action}` | `get_db` |
| `app/group_benefits_api.py` | `command` | `POST /api/group/benefits/members/{member_id}/actions/{action}` | `get_db` |
| `app/group_benefits_api.py` | `create_rule` | `POST /api/group/benefits/rules` | `get_db` |
| `app/insurance_api.py` | `command` | `POST /api/insurance-orders/{case_id}/actions/{action}` | `get_db` |
| `app/insurance_api.py` | `create` | `POST /api/insurance-orders` | `get_db` |
| `app/invoice_api.py` | `action` | `POST /api/invoices/orders/{key}/actions/{action}` | `get_db` |
| `app/invoice_api.py` | `create` | `POST /api/invoices/orders` | `get_db` |
| `app/master_api.py` | `add_master` | `POST /api/masters/{kind}` | `get_db` |
| `app/master_api.py` | `update_master` | `PUT /api/masters/{kind}/{record_id}` | `get_db` |
| `app/member_pricing_api.py` | `command` | `POST /api/member-pricing/rules/{key}/actions/{action}` | `get_db` |
| `app/member_pricing_api.py` | `create` | `POST /api/member-pricing/rules` | `get_db` |
| `app/membership_api.py` | `command` | `POST /api/membership/orders/{key}/actions/{action}` | `get_db` |
| `app/membership_api.py` | `create` | `POST /api/membership/orders` | `get_db` |
| `app/membership_api.py` | `rule` | `POST /api/membership/rules` | `get_db` |
| `app/observation_corrections_api.py` | `command` | `POST /api/observation-corrections/cases/{case_id}/actions/{action}` | `get_db` |
| `app/observation_corrections_api.py` | `create` | `POST /api/observation-corrections/cases` | `get_db` |
| `app/observation_corrections_api.py` | `generate` | `POST /api/observation-corrections/reminders/generate` | `get_db` |
| `app/observation_corrections_api.py` | `sync` | `POST /api/observation-corrections/insurance/{case_id}/sync` | `get_db` |
| `app/procurement_api.py` | `command` | `POST /api/procurement/orders/{case_id}/actions/{action}` | `get_db` |
| `app/procurement_api.py` | `create` | `POST /api/procurement/orders` | `get_db` |
| `app/recharge_bundle_api.py` | `command` | `POST /api/recharge-bundles/orders/{key}/actions/{action}` | `get_db` |
| `app/recharge_bundle_api.py` | `create` | `POST /api/recharge-bundles/orders` | `get_db` |
| `app/recharge_bundle_api.py` | `create_rule` | `POST /api/recharge-bundles/rules` | `get_db` |
| `app/reconciliation_api.py` | `batch_action` | `POST /api/reconciliation/batches/{key}/actions/{action}` | `get_write_db` |
| `app/reconciliation_api.py` | `clearing_action` | `POST /api/reconciliation/clearing/{key}/actions/{action}` | `get_db` |
| `app/reconciliation_api.py` | `clearing_create` | `POST /api/reconciliation/clearing` | `get_db` |
| `app/reconciliation_api.py` | `create` | `POST /api/reconciliation/batches` | `get_write_db` |
| `app/repair_api.py` | `command` | `POST /api/repair-orders/{case_id}/actions/{action}` | `get_db` |
| `app/repair_api.py` | `create` | `POST /api/repair-orders` | `get_db` |
| `app/repair_package_api.py` | `capture` | `POST /api/repair-packages/orders/{key}/capture` | `get_db` |
| `app/repair_package_api.py` | `decision` | `POST /api/repair-packages/rules/{key}/actions/{action}` | `get_db` |
| `app/repair_package_api.py` | `mapping` | `POST /api/repair-packages/rules/{key}/mappings` | `get_db` |
| `app/repair_package_api.py` | `material_return` | `POST /api/repair-packages/aftercare/{key}/return-material` | `get_db` |
| `app/repair_package_api.py` | `purchase` | `POST /api/repair-packages/purchases` | `get_db` |
| `app/repair_package_api.py` | `purchase_action` | `POST /api/repair-packages/purchases/{key}/actions/{action}` | `get_db` |
| `app/repair_package_api.py` | `quote` | `POST /api/repair-packages/orders/{key}/quote` | `get_db` |
| `app/repair_package_api.py` | `refund_action` | `POST /api/repair-packages/refunds/{key}/actions/{action}` | `get_db` |
| `app/repair_package_api.py` | `rule` | `POST /api/repair-packages/rules` | `get_db` |
| `app/retail_api.py` | `command` | `POST /api/retail/orders/{key}/actions/{action}` | `get_db` |
| `app/retail_api.py` | `create` | `POST /api/retail/orders` | `get_db` |
| `app/retail_bundle_api.py` | `publish` | `POST /api/retail-bundles/rules` | `get_db` |
| `app/retail_bundle_api.py` | `sale` | `POST /api/retail-bundles/sales` | `get_db` |
| `app/retail_group_api.py` | `action` | `POST /api/retail-group/orders/{case_id}/actions/{action}` | `get_db` |
| `app/retail_group_api.py` | `create_rule` | `POST /api/retail-group/rules` | `get_db` |
| `app/retail_group_api.py` | `rule_action` | `POST /api/retail-group/rules/{case_id}/actions/{action}` | `get_db` |
| `app/rework_extension_api.py` | `accept` | `POST /api/rework-extensions/requests` | `get_db` |
| `app/rework_extension_api.py` | `decide` | `POST /api/rework-extensions/grants/{key}/actions/{action}` | `get_db` |
| `app/rework_extension_api.py` | `propose` | `POST /api/rework-extensions/grants` | `get_db` |
| `app/rework_extension_api.py` | `quote` | `POST /api/rework-extensions/orders/{key}/quote` | `get_db` |
| `app/sales_quote_api.py` | `create` | `POST /api/sales-quotes/orders` | `get_db` |
| `app/sales_quote_api.py` | `revise` | `POST /api/sales-quotes/orders/{key}/quotes` | `get_db` |
| `app/service_intake_api.py` | `appointment_action` | `POST /api/service-intake/appointments/{key}/actions/{action}` | `get_db` |
| `app/service_intake_api.py` | `appointment_create` | `POST /api/service-intake/appointments` | `get_db` |
| `app/service_intake_api.py` | `binding` | `POST /api/service-intake/bindings` | `get_db` |
| `app/service_intake_api.py` | `preset_active` | `POST /api/service-intake/presets/{key}/active` | `get_db` |
| `app/service_intake_api.py` | `preset_create` | `POST /api/service-intake/presets` | `get_db` |
| `app/service_intake_api.py` | `resource_action` | `POST /api/service-intake/orders/{key}/resource/{action}` | `get_db` |
| `app/service_intake_api.py` | `resource_active` | `POST /api/service-intake/resources/{key}/active` | `get_db` |
| `app/service_intake_api.py` | `resource_create` | `POST /api/service-intake/resources` | `get_db` |
| `app/service_intake_api.py` | `rework_action` | `POST /api/service-intake/reworks/{key}/actions/{action}` | `get_db` |
| `app/service_intake_api.py` | `rework_create` | `POST /api/service-intake/reworks` | `get_db` |
| `app/service_orders_api.py` | `command` | `POST /api/service-orders/{case_id}/actions/{action}` | `get_db` |
| `app/service_orders_api.py` | `create` | `POST /api/service-orders` | `get_db` |
| `app/service_orders_api.py` | `income` | `POST /api/service-orders/income-items` | `get_db` |
| `app/service_orders_api.py` | `payee` | `POST /api/service-orders/payees` | `get_db` |
| `app/transfer_api.py` | `command` | `POST /api/transfers/{key}/actions/{action}` | `get_db` |
| `app/transfer_api.py` | `create` | `POST /api/transfers` | `get_db` |
| `app/transfer_exception_api.py` | `command` | `POST /api/transfer-exceptions/{key}/actions/{action}` | `get_db` |
| `app/transfer_exception_api.py` | `create` | `POST /api/transfer-exceptions` | `get_db` |
| `app/transfer_goods_recovery_api.py` | `command` | `POST /api/transfer-goods-recoveries/{key}/actions/{action}` | `get_db` |
| `app/transfer_goods_recovery_api.py` | `create` | `POST /api/transfer-goods-recoveries` | `get_db` |
| `app/vehicle_catalog_api.py` | `entry` | `POST /api/vehicle-catalog/entry` | `get_db` |
| `app/vehicle_catalog_api.py` | `model_assignment` | `POST /api/vehicle-catalog/model-assignment` | `get_db` |
| `app/vehicle_catalog_api.py` | `vehicle_assignment` | `POST /api/vehicle-catalog/vehicle-assignment` | `get_db` |
| `app/vehicle_imports_api.py` | `command` | `POST /api/vehicle-imports/batches/{batch_id}/actions/{action}` | `get_db` |
| `app/vehicle_income_api.py` | `command` | `POST /api/vehicle-income/{key}/actions/{action}` | `get_db` |
| `app/vehicle_income_api.py` | `create` | `POST /api/vehicle-income` | `get_db` |
| `app/vehicle_operations_api.py` | `command` | `POST /api/vehicle-operations/orders/{case_id}/actions/{action}` | `get_db` |
| `app/vehicle_operations_api.py` | `create` | `POST /api/vehicle-operations/orders` | `get_db` |
| `app/vehicle_procurement_api.py` | `command` | `POST /api/vehicle-procurement/orders/{case_id}/actions/{action}` | `get_write_db` |
| `app/vehicle_procurement_api.py` | `create` | `POST /api/vehicle-procurement/orders` | `get_db` |
| `app/vehicle_transfer_api.py` | `command` | `POST /api/vehicle-transfers/{key}/actions/{action}` | `get_db` |
| `app/vehicle_transfer_api.py` | `create` | `POST /api/vehicle-transfers` | `get_db` |
| `app/vehicle_transport_api.py` | `command` | `POST /api/vehicle-transport-exceptions/{key}/actions/{action}` | `get_db` |
| `app/vehicle_transport_api.py` | `create` | `POST /api/vehicle-transport-exceptions` | `get_db` |
| `app/warehouse_api.py` | `allocate` | `POST /api/warehouse/allocations/{case_id}` | `get_write_db` |
| `app/warehouse_api.py` | `command` | `POST /api/warehouse/cases/{case_id}/commands/{action}` | `get_db` |
| `app/warehouse_api.py` | `create` | `POST /api/warehouse/cases` | `get_db` |

## 实施与复验

先保存外部原字节，再预计算全部机械改动，确认 AST 除精确 imports/default/order 和 get_write_db 目标分支之外一致，才写入。三路独立源码审阅、轻量 AST 后新目录重跑原财务17、应收11、报表6点击与旧行守卫；三组不拼全量成绩。之后同指纹全53联合与需求表193项可追踪证据及人工页面标准。静态审阅不是通过，当前真实业务/并发/提交后读仍待新实测。真实日期、PG/Linux、101/283真实模型、员工/外部手续/生产门禁保留，四开关生产默认关闭。不新增全局 Session hook、HTTP method 接线、重试、降守卫、改 request_id 或真实环境写入。
