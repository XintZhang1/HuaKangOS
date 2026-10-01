# 原同步业务写事务依赖审阅

2026-10-01，M8.1 同一实施项的只读源码审阅。只新增此页；未导入 app、未启动实例或浏览器、未运行测试、未读取数据库或凭据。此页是明确候选清单，不是补丁登记、业务通过或全量验收。

## 当前依据与结论

读取当前工作树，HEAD `8993ca8c755194a42a48e7323fe355e80c6bf9ae`，不以 HEAD 代替未提交源码指纹。静态能力边界为 `app/business_assistant_capabilities.json` version 1：291 个操作，164 GET、127 POST/PUT。127 个操作均精确匹配真实路由，分布 41 个 API 文件；122 个使用普通 `get_db`，5 个已有 `get_write_db`。逐入口追至原服务：每项有真实 add/flush/delete 与 commit 路径，均为同步处理器；所追本地函数无 await。127 项未发现纯读 POST。幂等已提交结果、校验拒绝或 trial 某分支可不写，不能据此把包含实际写分支的整个端点归为纯读。

- `repair_package_api.quote` 实际调用 `repair_service.command(..., 'quote', ...)`，保存维修报价；`rework_extension_api.quote` 同样保存新报价，均非查询预览。
- `vehicle_imports_api.command` 是唯一 `get_user` 参数在 db 之前的入口。只换 db 的 Depends 不足；必须先解析写 db、再认证，保留请求模型、权限、动作、CAS、回执和响应。
- 未改变能力目录、助手权限、业务动作或 Worker。路径清单是已评审业务写入集合的静态筛选，不能用 HTTP method 自动接线其它端点。

- 原 `app/db.py` SHA256：`bf6df8b8db8812073ba1e15130a6c2c5537aa054481bc216aa062628d4b45d45`。
- 能力目录 SHA256：`f9446c0f0ffc35368b7cb5d87193d5493e6948ac1da191f39e59fe302ceaf8ed`。
- 127 项路径/函数/依赖/提交来源序列 SHA256：`4a2c8cbe8517f4266a54e8307a71d43c5263166240274526d12aa43e79d81b5d`。
- 本页静态追踪所读 183 个源码与目录文件的 `(相对路径, SHA256)` 排序序列 SHA256：`0527b881b3bbbf754edb3edcb09ea95fe308360f4bd95b5ed394678a28e39972`。读取到写页前复核文件字节一致；下表行号和依赖为本页捕获时的原字节。

## 同一个请求 Session 的事务合同

`app/db.py:49–54` 只构造 `SessionLocal(bind=engine, expire_on_commit=False)` 并 yield，创建 Session 不取得连接。`get_bind().dialect.name` 也不开始事务。`security.get_user:91–110` 的 LoginSession/User/current-store 查询才读取认证快照。API 没有先于签名参数的 router/decorator dependencies，main.include_router 也未追加认证依赖。

当前 `get_write_db:65–66` 将标志放在首次 Connection 上。它能令第一笔 SQLite 事务在认证前执行 `BEGIN IMMEDIATE`，但 **commit/rollback 后不保持此标志**。本机 SQLAlchemy 2.0.50 `orm/session.py:1157–1168/1191–1196` 说明已有连接上的 execution_options 会被忽略，新连接才应用；`1312–1330/1407–1423` 提交后关闭连接并清 SessionTransaction。因此后续同一请求的新事务仍从原 Engine 取得无标志 Connection。不能把一次设旗声称为跨提交保护。

根提出的最窄方案静态成立：仅 SQLite 的显式 `get_write_db`，在首次取得连接前把 **此 Session 的 bind** 换成 `db.get_bind().execution_options(huakangos_sqlite_write_transaction=True)` 返回的 OptionEngine，再 `db.connection()`；不修改原 Engine、SessionLocal 或全局 Session 事件。

1. `Session.get_bind:2782–2787`：当前 Session 无 mapper/table 分绑定，ORM 查询、flush 和后续 SQL 都返回此 Session.bind。同一个 db 对象、identity map、db.info 当前门店、CAS 和原事务提交保持。
2. `engine/base.py:3060–3077/3333–3360/3369`：execution_options 返回新 OptionEngine，共享原 pool，继承原 connect/begin 监听，选项更新在代理上，不改原 Engine。
3. `Connection.__init__:165–170`：新 Connection 继承其 Engine 的事件和 options；`SessionTransaction._connection_for_bind:1191/1244` 先从新 bind 取连接，再 begin。既有 `app/db.py:34–40` 检查该标志并选 IMMEDIATE。
4. Session.bind 不在 commit/rollback 中重置；以后每笔新事务继续带标志。返还池中的 DBAPI 连接不会把代理 Engine 的 execution_options 写到另一请求原 Engine 的新 Connection；普通 `get_db`/Worker 不因此变成 writer。
5. FastAPI 0.128.2 `dependencies/utils.py:280–313/603/639–659` 按签名顺序解析依赖，默认缓存同 callable 的 get_db。显式 db 在 user 之前时，get_write_db 的子 get_db 与 get_user 的 get_db 是同一 Session；vendor import 的 user-first 必须重排。

成立前提是 **首次连接前** 换 bind。已经由认证读取得旧 Connection 后再改 bind，会让同一 SessionTransaction 同时关联旧/new Engine Connection，不能修复旧快照；不得靠 after_begin 或全局 after_transaction_create/info hook补救。当前原 SessionLocal 是单 Engine 绑定，没有 bind_mapper/bind_table、multi-bind 或 get_bind 覆盖。PostgreSQL 分支不改 bind、不抢 SQLite writer，保留原 REPEATABLE READ。方案无重试、回放、降低 CAS 或更换 request_id。

写路由提交后用于 describe 的后续短读，也会在此请求的 OptionEngine 下保留 IMMEDIATE，到 get_db finally rollback 结束；不是新的全局读策略。生成文件原同步 I/O、较大的同步原动作仍需真实耗时/竞争复验，不应声称此静态审阅证明无锁等待。127 项没有模型 await、SSE 或长期流式响应混入。

## 127 个明确原写入口

所有行均“同步、真实写分支、提交链可达、所追函数无 await、非纯读 POST”。提交来源列给出实际原服务落盘的位置；仍须保留各操作原权限/CAS/幂等/原件/任务/流水。`get_db` 的 122 行是待登记候选；已有 5 行不得重复放宽或改成其它身份。

| 文件:行 / 函数 | 精确原操作 | 当前 db 依赖 | 认证顺序 | 原 commit 来源 |
|---|---|---|---|---|
| `app/addon_api.py:99` `create` | `POST /api/addon-orders` | `Depends(get_db)` | db→get_user | `app/addon_service.py:78` `_execute` |
| `app/addon_api.py:103` `command` | `POST /api/addon-orders/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/addon_service.py:78` `_execute` |
| `app/aftercare_api.py:51` `create` | `POST /api/aftercare/orders` | `Depends(get_db)` | db→get_user | `app/aftercare_service.py:75` `_execute` |
| `app/aftercare_api.py:55` `command` | `POST /api/aftercare/orders/{case_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/aftercare_service.py:75` `_execute` |
| `app/business_finance_api.py:99` `create` | `POST /api/business-finance/orders` | `Depends(get_db)` | db→get_user | `app/business_finance_service.py:54` `execute` |
| `app/business_finance_api.py:105` `command` | `POST /api/business-finance/orders/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/business_finance_service.py:54` `execute` |
| `app/claims_api.py:82` `create` | `POST /api/claims` | `Depends(get_db)` | db→get_user | `app/claims_service.py:96` `_execute` |
| `app/claims_api.py:91` `command` | `POST /api/claims/{case_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/claims_service.py:96` `_execute` |
| `app/customer_service_api.py:159` `new_vehicle` | `POST /api/customer-service/vehicles` | `Depends(get_db)` | db→get_user | `app/customer_service.py:97` `_execute` |
| `app/customer_service_api.py:172` `edit_vehicle` | `PUT /api/customer-service/vehicles/{vehicle_id}` | `Depends(get_db)` | db→get_user | `app/customer_service.py:97` `_execute` |
| `app/customer_service_api.py:176` `observation` | `POST /api/customer-service/vehicles/{vehicle_id}/observations` | `Depends(get_db)` | db→get_user | `app/customer_service.py:97` `_execute` |
| `app/customer_service_api.py:184` `link_history` | `POST /api/customer-service/vehicles/{vehicle_id}/history-links` | `Depends(get_db)` | db→get_user | `app/customer_service.py:97` `_execute` |
| `app/customer_service_api.py:204` `new_case` | `POST /api/customer-service/cases` | `Depends(get_db)` | db→get_user | `app/customer_service.py:97` `_execute` |
| `app/customer_service_api.py:214` `action` | `POST /api/customer-service/cases/{case_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/customer_service.py:97` `_execute` |
| `app/customer_service_api.py:226` `new_rule` | `POST /api/customer-service/reminders/rules` | `Depends(get_db)` | db→get_user | `app/customer_service.py:97` `_execute` |
| `app/customer_service_api.py:230` `update_rule` | `PUT /api/customer-service/reminders/rules/{rule_id}` | `Depends(get_db)` | db→get_user | `app/customer_service.py:97` `_execute` |
| `app/customer_service_api.py:234` `generate` | `POST /api/customer-service/reminders/generate` | `Depends(get_db)` | db→get_user | `app/observation_corrections_service.py:79` `_execute` |
| `app/customer_service_api.py:244` `new_grant` | `POST /api/customer-service/history/grants` | `Depends(get_db)` | db→get_user | `app/customer_service.py:97` `_execute` |
| `app/customer_service_api.py:248` `revoke` | `POST /api/customer-service/history/grants/{grant_id}/revoke` | `Depends(get_db)` | db→get_user | `app/customer_service.py:97` `_execute` |
| `app/customer_service_api.py:272` `questionnaire_propose` | `POST /api/customer-service/questionnaires/versions` | `Depends(get_db)` | db→get_user | `app/customer_service.py:97` `_execute` |
| `app/customer_service_api.py:278` `questionnaire_review` | `POST /api/customer-service/questionnaires/versions/{version_id}/review` | `Depends(get_db)` | db→get_user | `app/customer_service.py:97` `_execute` |
| `app/dictionary_api.py:85` `create` | `POST /api/dictionaries/{group}` | `Depends(get_db)` | db→get_user | `app/master_data.py:213` `_command` |
| `app/dictionary_api.py:89` `update` | `PUT /api/dictionaries/{group}/{record_id}` | `Depends(get_db)` | db→get_user | `app/master_data.py:213` `_command` |
| `app/dossier_grant_api.py:99` `propose` | `POST /api/dossier-grants` | `Depends(get_db)` | db→get_user | `app/dossier_grant_service.py:433` `_execute` |
| `app/dossier_grant_api.py:109` `action` | `POST /api/dossier-grants/{grant_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/dossier_grant_service.py:433` `_execute` |
| `app/escalation_api.py:43` `submit` | `POST /api/escalations` | `Depends(get_db)` | db→get_user | `app/escalation_service.py:139` `create` |
| `app/flow_api.py:96` `assign_task` | `POST /api/flow/tasks/{task_id}/assign` | `Depends(get_db)` | db→get_user | `app/flow_api.py:117` `assign_task` |
| `app/flow_api.py:140` `create_case` | `POST /api/flow/cases` | `Depends(get_db)` | db→get_user | `app/flow_api.py:145` `create_case` |
| `app/flow_api.py:172` `act` | `POST /api/flow/cases/{case_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/flow_api.py:186` `act` |
| `app/flow_api.py:196` `generate` | `POST /api/flow/cases/{case_id}/documents` | `Depends(get_write_db)` | db→get_user | `app/flow_api.py:201` `generate` |
| `app/flow_api.py:342` `add_master` | `POST /api/flow/master/{kind}` | `Depends(get_db)` | db→get_user | `app/flow_api.py:357` `add_master` |
| `app/flow_api.py:361` `edit_master` | `PUT /api/flow/master/{kind}/{record_id}` | `Depends(get_db)` | db→get_user | `app/flow_api.py:401` `edit_master` |
| `app/gate_visit_api.py:77` `create` | `POST /api/gate-visits` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/gate_visit_api.py:87` `command` | `POST /api/gate-visits/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/gate_visit_api.py:93` `correct` | `POST /api/gate-visits/{key}/corrections` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/gate_visit_api.py:98` `review` | `POST /api/gate-visits/corrections/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/gate_visit_api.py:103` `repair_exit` | `POST /api/gate-visits/repair-orders/{key}/departure` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/group_api.py:108` `link_identity` | `POST /api/group/identities/link` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/group_api.py:113` `issue_member` | `POST /api/group/members` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/group_api.py:128` `member_action` | `POST /api/group/members/{member_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/group_benefits_api.py:77` `create_rule` | `POST /api/group/benefits/rules` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/group_benefits_api.py:90` `command` | `POST /api/group/benefits/members/{member_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/insurance_api.py:100` `create` | `POST /api/insurance-orders` | `Depends(get_db)` | db→get_user | `app/insurance_service.py:67` `_execute` |
| `app/insurance_api.py:104` `command` | `POST /api/insurance-orders/{case_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/insurance_service.py:67` `_execute` |
| `app/invoice_api.py:53` `create` | `POST /api/invoices/orders` | `Depends(get_db)` | db→get_user | `app/invoice_service.py:168` `_execute` |
| `app/invoice_api.py:56` `action` | `POST /api/invoices/orders/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/invoice_service.py:168` `_execute` |
| `app/master_api.py:179` `add_master` | `POST /api/masters/{kind}` | `Depends(get_db)` | db→get_user | `app/master_data.py:213` `_command` |
| `app/master_api.py:184` `update_master` | `PUT /api/masters/{kind}/{record_id}` | `Depends(get_db)` | db→get_user | `app/master_data.py:213` `_command` |
| `app/member_pricing_api.py:77` `create` | `POST /api/member-pricing/rules` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/member_pricing_api.py:82` `command` | `POST /api/member-pricing/rules/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/membership_api.py:62` `rule` | `POST /api/membership/rules` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/membership_api.py:72` `create` | `POST /api/membership/orders` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/membership_api.py:78` `command` | `POST /api/membership/orders/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/observation_corrections_api.py:58` `create` | `POST /api/observation-corrections/cases` | `Depends(get_db)` | db→get_user | `app/observation_corrections_service.py:79` `_execute` |
| `app/observation_corrections_api.py:62` `command` | `POST /api/observation-corrections/cases/{case_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/observation_corrections_service.py:79` `_execute` |
| `app/observation_corrections_api.py:70` `generate` | `POST /api/observation-corrections/reminders/generate` | `Depends(get_db)` | db→get_user | `app/observation_corrections_service.py:79` `_execute` |
| `app/observation_corrections_api.py:73` `sync` | `POST /api/observation-corrections/insurance/{case_id}/sync` | `Depends(get_db)` | db→get_user | `app/observation_corrections_service.py:79` `_execute` |
| `app/procurement_api.py:60` `create` | `POST /api/procurement/orders` | `Depends(get_db)` | db→get_user | `app/procurement_service.py:112` `_execute` |
| `app/procurement_api.py:70` `command` | `POST /api/procurement/orders/{case_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/procurement_service.py:112` `_execute` |
| `app/recharge_bundle_api.py:57` `create_rule` | `POST /api/recharge-bundles/rules` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/recharge_bundle_api.py:67` `create` | `POST /api/recharge-bundles/orders` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/recharge_bundle_api.py:71` `command` | `POST /api/recharge-bundles/orders/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/reconciliation_api.py:59` `create` | `POST /api/reconciliation/batches` | `Depends(get_write_db)` | db→get_user | `app/reconciliation_service.py:64` `execute` |
| `app/reconciliation_api.py:62` `batch_action` | `POST /api/reconciliation/batches/{key}/actions/{action}` | `Depends(get_write_db)` | db→get_user | `app/reconciliation_service.py:64` `execute` |
| `app/reconciliation_api.py:72` `clearing_create` | `POST /api/reconciliation/clearing` | `Depends(get_db)` | db→get_user | `app/reconciliation_service.py:64` `execute` |
| `app/reconciliation_api.py:75` `clearing_action` | `POST /api/reconciliation/clearing/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/reconciliation_service.py:64` `execute` |
| `app/repair_api.py:89` `create` | `POST /api/repair-orders` | `Depends(get_db)` | db→get_user | `app/repair_service.py:159` `_execute` |
| `app/repair_api.py:95` `command` | `POST /api/repair-orders/{case_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/repair_service.py:159` `_execute` |
| `app/repair_package_api.py:82` `rule` | `POST /api/repair-packages/rules` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/repair_package_api.py:84` `decision` | `POST /api/repair-packages/rules/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/repair_package_api.py:86` `mapping` | `POST /api/repair-packages/rules/{key}/mappings` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/repair_package_api.py:93` `purchase` | `POST /api/repair-packages/purchases` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/repair_package_api.py:95` `purchase_action` | `POST /api/repair-packages/purchases/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/repair_package_api.py:100` `refund_action` | `POST /api/repair-packages/refunds/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/repair_package_api.py:102` `quote` | `POST /api/repair-packages/orders/{key}/quote` | `Depends(get_db)` | db→get_user | `app/repair_service.py:159` `_execute` |
| `app/repair_package_api.py:111` `capture` | `POST /api/repair-packages/orders/{key}/capture` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/repair_package_api.py:113` `material_return` | `POST /api/repair-packages/aftercare/{key}/return-material` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/retail_api.py:81` `create` | `POST /api/retail/orders` | `Depends(get_db)` | db→get_user | `app/retail_service.py:82` `_execute` |
| `app/retail_api.py:87` `command` | `POST /api/retail/orders/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/retail_service.py:82` `_execute` |
| `app/retail_bundle_api.py:49` `publish` | `POST /api/retail-bundles/rules` | `Depends(get_db)` | db→get_user | `app/retail_bundle_service.py:93` `create_rule` |
| `app/retail_bundle_api.py:55` `sale` | `POST /api/retail-bundles/sales` | `Depends(get_db)` | db→get_user | `app/retail_service.py:82` `_execute` |
| `app/retail_group_api.py:86` `action` | `POST /api/retail-group/orders/{case_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/retail_group_api.py:91` `create_rule` | `POST /api/retail-group/rules` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/retail_group_api.py:111` `rule_action` | `POST /api/retail-group/rules/{case_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/group_service.py:91` `_execute` |
| `app/rework_extension_api.py:45` `propose` | `POST /api/rework-extensions/grants` | `Depends(get_db)` | db→get_user | `app/rework_extension_service.py:162` `_execute` |
| `app/rework_extension_api.py:50` `decide` | `POST /api/rework-extensions/grants/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/rework_extension_service.py:162` `_execute` |
| `app/rework_extension_api.py:53` `accept` | `POST /api/rework-extensions/requests` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/rework_extension_api.py:56` `quote` | `POST /api/rework-extensions/orders/{key}/quote` | `Depends(get_db)` | db→get_user | `app/repair_service.py:159` `_execute` |
| `app/sales_quote_api.py:38` `create` | `POST /api/sales-quotes/orders` | `Depends(get_db)` | db→get_user | `app/sales_quote_service.py:100` `_execute` |
| `app/sales_quote_api.py:50` `revise` | `POST /api/sales-quotes/orders/{key}/quotes` | `Depends(get_db)` | db→get_user | `app/sales_quote_service.py:100` `_execute` |
| `app/service_intake_api.py:87` `resource_create` | `POST /api/service-intake/resources` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/service_intake_api.py:90` `resource_active` | `POST /api/service-intake/resources/{key}/active` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/service_intake_api.py:93` `preset_create` | `POST /api/service-intake/presets` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/service_intake_api.py:96` `preset_active` | `POST /api/service-intake/presets/{key}/active` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/service_intake_api.py:101` `appointment_create` | `POST /api/service-intake/appointments` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/service_intake_api.py:106` `appointment_action` | `POST /api/service-intake/appointments/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/service_intake_api.py:111` `binding` | `POST /api/service-intake/bindings` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/service_intake_api.py:116` `rework_create` | `POST /api/service-intake/reworks` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/service_intake_api.py:121` `rework_action` | `POST /api/service-intake/reworks/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/service_intake_api.py:126` `resource_action` | `POST /api/service-intake/orders/{key}/resource/{action}` | `Depends(get_db)` | db→get_user | `app/service_intake_service.py:60` `_execute` |
| `app/service_orders_api.py:96` `payee` | `POST /api/service-orders/payees` | `Depends(get_db)` | db→get_user | `app/service_orders_service.py:66` `_execute` |
| `app/service_orders_api.py:98` `income` | `POST /api/service-orders/income-items` | `Depends(get_db)` | db→get_user | `app/service_orders_service.py:66` `_execute` |
| `app/service_orders_api.py:100` `create` | `POST /api/service-orders` | `Depends(get_db)` | db→get_user | `app/service_orders_service.py:66` `_execute` |
| `app/service_orders_api.py:104` `command` | `POST /api/service-orders/{case_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/service_orders_service.py:66` `_execute` |
| `app/transfer_api.py:48` `create` | `POST /api/transfers` | `Depends(get_db)` | db→get_user | `app/transfer_service.py:184` `execute` |
| `app/transfer_api.py:53` `command` | `POST /api/transfers/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/transfer_service.py:184` `execute` |
| `app/transfer_exception_api.py:75` `create` | `POST /api/transfer-exceptions` | `Depends(get_db)` | db→get_user | `app/transfer_exception_service.py:306` `_execute` |
| `app/transfer_exception_api.py:78` `command` | `POST /api/transfer-exceptions/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/transfer_exception_service.py:306` `_execute` |
| `app/transfer_goods_recovery_api.py:65` `create` | `POST /api/transfer-goods-recoveries` | `Depends(get_db)` | db→get_user | `app/transfer_goods_recovery_service.py:335` `execute` |
| `app/transfer_goods_recovery_api.py:69` `command` | `POST /api/transfer-goods-recoveries/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/transfer_goods_recovery_service.py:335` `execute` |
| `app/vehicle_catalog_api.py:55` `entry` | `POST /api/vehicle-catalog/entry` | `Depends(get_db)` | db→get_user | `app/master_data.py:213` `_command` |
| `app/vehicle_catalog_api.py:68` `model_assignment` | `POST /api/vehicle-catalog/model-assignment` | `Depends(get_db)` | db→get_user | `app/master_data.py:213` `_command` |
| `app/vehicle_catalog_api.py:73` `vehicle_assignment` | `POST /api/vehicle-catalog/vehicle-assignment` | `Depends(get_db)` | db→get_user | `app/master_data.py:213` `_command` |
| `app/vehicle_imports_api.py:84` `command` | `POST /api/vehicle-imports/batches/{batch_id}/actions/{action}` | `Depends(get_db)` | **get_user→db，须重排** | `app/vehicle_imports_service.py:72` `run` |
| `app/vehicle_income_api.py:58` `create` | `POST /api/vehicle-income` | `Depends(get_db)` | db→get_user | `app/vehicle_income_service.py:59` `_execute` |
| `app/vehicle_income_api.py:62` `command` | `POST /api/vehicle-income/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/vehicle_income_service.py:59` `_execute` |
| `app/vehicle_operations_api.py:87` `create` | `POST /api/vehicle-operations/orders` | `Depends(get_db)` | db→get_user | `app/vehicle_operations_service.py:241` `execute` |
| `app/vehicle_operations_api.py:95` `command` | `POST /api/vehicle-operations/orders/{case_id}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/vehicle_operations_service.py:241` `execute` |
| `app/vehicle_procurement_api.py:92` `create` | `POST /api/vehicle-procurement/orders` | `Depends(get_db)` | db→get_user | `app/vehicle_procurement_service.py:112` `execute` |
| `app/vehicle_procurement_api.py:98` `command` | `POST /api/vehicle-procurement/orders/{case_id}/actions/{action}` | `Depends(get_write_db)` | db→get_user | `app/vehicle_procurement_service.py:112` `execute` |
| `app/vehicle_transfer_api.py:27` `create` | `POST /api/vehicle-transfers` | `Depends(get_db)` | db→get_user | `app/transfer_service.py:184` `execute` |
| `app/vehicle_transfer_api.py:31` `command` | `POST /api/vehicle-transfers/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/transfer_service.py:184` `execute` |
| `app/vehicle_transport_api.py:127` `create` | `POST /api/vehicle-transport-exceptions` | `Depends(get_db)` | db→get_user | `app/vehicle_transport_service.py:242` `execute` |
| `app/vehicle_transport_api.py:137` `command` | `POST /api/vehicle-transport-exceptions/{key}/actions/{action}` | `Depends(get_db)` | db→get_user | `app/vehicle_transport_service.py:242` `execute` |
| `app/warehouse_api.py:80` `create` | `POST /api/warehouse/cases` | `Depends(get_db)` | db→get_user | `app/warehouse_service.py:201` `create` |
| `app/warehouse_api.py:86` `command` | `POST /api/warehouse/cases/{case_id}/commands/{action}` | `Depends(get_db)` | db→get_user | `app/warehouse_service.py:236` `command` |
| `app/warehouse_api.py:94` `allocate` | `POST /api/warehouse/allocations/{case_id}` | `Depends(get_write_db)` | db→get_user | `app/warehouse_service.py:347` `prepare_external` |

## 原能力闭面及不自动纳入的入口

`business_assistant_gateway._reviewed_operations:141–152` 从静态目录读取精确条目；`_operations:168–179` 再限定领域、封闭面、文件/导出路径、管理写入、multipart 与声明 JSON schema。接线这些 db 依赖不得改目录、DOMAINS/CLOSED_DOMAINS、DENIED、CLASSIFIED_BLOCKED_WRITES 或恢复管理员/任意 CRUD。

- **明确纯读 POST，排除**：`main.preview_report:498` `POST /api/reports/preview` 只 `external_payload(build_snapshot(...))`；`analytics.build_snapshot:226` 只加载原数据并计算快照、无写入。助手 prepare/query、Runtime、模型、SSE、纯查询与 GET 不按 HTTP method 推成业务 writer。
- **其它真写但不在 127 目录，单独登记审阅才能补**：下列事实仅说明遗漏边界，绝不以“也是 POST”批量修改或开放给助手。

| 原入口/文件 | 边界与实际写入证据 |
|---|---|
| `main.add_user:264` `POST /api/users`；`add_users_batch:280` `POST /api/users/batch`；`edit_user:326` `PUT /api/users/{user_id}`；`reset_password:332` `POST /api/users/{user_id}/password` | 管理/凭据闭面，现 db→get_user。原 new User/UserStore/audit 后 commit 271/321/346；change_access 在 `user_access_service.py:82` commit。不在 reviewed business 列表。 |
| `main.add_store:599` `POST /api/stores`；`edit_store:607` `PUT /api/stores/{store_id}` | 管理门店闭面，原 Store/audit/安全信号提交，独立范围。 |
| `main.change_password:240` `POST /api/auth/password`；login/logout | 原认证闭面。password 已显式 get_write_db；login 的 authenticate 已有原写预留，logout 保留原短事务与完整重验；本页不改认证算法。 |
| `master_api.preflight:82`、`trial:96`、`confirm:101`；`opening_import_api.preflight:86`、`act:103`；`vehicle_imports_api.prepare:69` | 原导入闭面或 multipart；可能含真实 trial/登记/确认写入，不能拿读写能力目录漏项作为无副作用证明；不混入此同步 JSON 候选。 |
| `business_entity_api.create:73`、`command:83`；`escalation_api.command:48`；`file_security_api.scan:22` | 原经营主体管理、人工评审办理、附件扫描闭面，须独立精确授权/持锁阶段审查。 |
| `main.make_report:505`、`review:523`、legacy records writes；branding/parameters/local-preview | 日报模型/另一个 Session 的生成、人工 findings 管理、legacy/配置/预览边界不同；不属于 127，也不继承依赖修复或助手开放。 |
| 既有 audited GET/CSV/Dossier record/file 下载 | GET 可以有真实访问/导出审计；已采用 get_audited_read_db 的路由按原审计合同，不能用“GET 一定纯读”抹去审计，也不借本页扩域。 |

`main.note_refusal:151–181` 另开 SessionLocal 记录真实拒绝，不是复用此路由 get_db；本页的 request-local bind 不自动改变它。它及其它另开 Session、异步上传后的持锁阶段属于独立事务审阅，不能声称 127 接线已修复全应用一切 busy/517。

## 最小可审补丁与后续检查

只在精确登记范围内改 `app/db.py:get_write_db` 为请求级 SQLite OptionEngine，以及下表 122 函数的 db=Depends(get_write_db) 与各文件对应导入；原普通读仍 get_db。`vehicle_imports_api.command` 将 db 放到 user 前。当前已有的 5 writer 和 alias 同 Session 合同保持。服务方法、能力目录、工作流动作、账户/店/当前员工守卫、金额/数量、原件/审计/回执/提交次数不改。

静态交付应反向比对：127 精确路由集合不变、全部同步、db 写依赖在 auth 前、无意改任何 GET/纯读 POST/异步/封闭面，源码服务 diff 为零；本页路径集合与实际新 AST 可核对。运行阶段仍须在全新外部合成镜像验证并发写入、提交后下一事务、原失败响应与零业务变更、当前身份/门店和全旧行守卫、负路回执、普通 read/Worker/PG 边界；保持失败原件，不重试求绿，不用静态审阅记 passed。

结构化清单另存 `V/browser-click/launches/reviewed-short-writers-127.json`，top-level array，只有 `file/function/method/path` 四字段，127 项（41 文件），SHA256 `f368df1018df2a4eb2f662ceba3a859f1a78badc75e1f1b10ad36d847f2cc521`。额外静态复核全部 56 个 include_router、main.FastAPI 构造、41 个 API router 及 127 个路由 decorator 均无抢先 dependencies；没有新的全局认证依赖先取得该 cached Session 的 Connection。
