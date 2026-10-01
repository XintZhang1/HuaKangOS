# 当前同步审计读取事务审阅

2026-10-01；归属当前 M8.1 浏览器交付的只读诊断子任务。本文不是新里程碑、测试通过报告或功能放行。未导入 app、运行服务/测试、读取真实环境/业务数据；仅解析当前源码及既有外部合成 run08 的报告、日志。工作树已有他人修改，未改生产源码、测试脚本、共享索引或原失败证据。

记录时点说明：下面12项“4已接线/8未接线”与源码hash为补丁实施前的只读诊断快照；后续主任务已登记并实施8项精确接线，实施后独立原字节/AST审阅另见 `audited-read-writers-review-a.md`，不能把下面实施前状态误称最新源码。work-status动态分派边界的补充修正保留在本文对应行。

## 结论与 file86

当前 app 全部 228 个 GET 注册中，221 个为同步函数，7 个为 async；无 `api_route`、`add_api_route` 或其他动态 GET 注册。按入口本地调用链逐一追踪实际审计、访问记录及 commit，确认 **12 个同步 GET 在成功读取时追加审计/访问日志并提交**。其中 4 个已使用 `get_audited_read_db`，8 个仍使用 `get_db`。不是依据 GET/CSV/download 名称猜测 writer。

`flow_api.download:215` 的 `GET /api/flow/files/{file_id}` 仍为 `db=Depends(get_db), user=Depends(get_user)`。同一 cached Session 在 `security.get_user:91` 先读取登录、用户、当前门店，再读取原件/原单/扫描记录/字节，最后在 `flow_api.py:223` 调用 `services.audit` 追加 AuditLog 并 `db.commit()`。普通 SQLite BEGIN 的 WAL 读快照随后升写，会受并发提交影响；最小修改候选是该入口采用已经导入的 `get_audited_read_db`，保持 db→auth、原读权限、scan/bytes、审计/提交次数及失败响应，不改 helper、不重放。

隐藏链已逐行核对：`require_usable:185 → security_info:151 → _records:141` 仅查询 FileSecurity/FileScanEvent 并判定扫描；`require_usable` 另调 `private_files.read_content:139`；路由随后再次调用 `read_content`。`read_content` 仅查询 FileAsset/PrivateFileObject，读取并核对 BLOB/私有对象大小与摘要，**没有 add/flush/commit 或写字节**。本 GET 的实际写入来自末尾审计，不能称为扫描/存储 helper 偷写。扫描初始化/重扫另在原写入口执行。

既有合成 `V/browser-click/business-receivables-20261001-08/evidence/sales-order-hk008-009-011-022/network.json` 记录 file86：same_origin=true、cookie_present=true、GET 返回 503/application/json。`server.log` 有 `Database operation failed (OperationalError)`，同时出现 code=5 和 code=517；日志无请求 ID/时戳，不能将某条 517 精确归给 file86。`main.operational_error:202` 将 OperationalError 转为 503；扫描/字节异常原为 409、权限异常原为 403。可确认该入口有未预留 writer 的审计升写缺口，最终是否为本次 517 必须保留上述归因边界。原场景的 expect_download 超时不能替代对真实 GET 错误的诊断；本文未修改它。

## 共同 Session 与原鉴权顺序

以下 12 个入口的 db 形参均在 user 前，未发现入口 decorator、router 或 app 全局的抢先认证依赖。FastAPI 先取得 `get_db` 的 cached Session，writer 依赖在 `get_user` 首次 SQL 前设定本请求 OptionEngine 并取得 connection；`get_user` 继续依赖原 `get_db`，两者共享该 Session。`get_audited_read_db` 在 `app/db.py:72` 是 `get_write_db` 的别名；SQLite 才使用 `huakangos_sqlite_write_transaction=True`，OptionEngine 保持该请求后续 commit/rollback 的 begin 合同；PostgreSQL 保留原事务隔离/锁与版本校验。

`services.audit:25` 只 `db.add(AuditLog(...))`，不自行提交；下面直接 commit 才持久化。`tenancy.attach_scope:64` 只查岗位/门店并设置 Session.info，不写业务或会话。`get_db` 收尾 rollback 不构成业务提交。`get_user` 不为 GET 添加 CSRF 写入，也不续期/刷新 LoginSession。

## 12 个真实审计读取入口

所有表内条目均为同步 `def`，本地读取、审计与 commit 中没有 await 或 streaming。

| 文件/函数（行） | HTTP 方法与完整路由 | 当前 db 依赖；顺序 | 原写入与实际 commit 来源 |
|---|---|---|---|
| `app/customer_service_api.py:290 questionnaire_export` | `GET /api/customer-service/questionnaires/export/{table_key}` | **已 writer** `get_audited_read_db`；db→get_user | questionnaire_analytics.report/select_table 读取原范围，`audit(export, questionnaire_report)` 后 **路由307 commit** |
| `app/inventory_reports_api.py:58 export` | `GET /api/inventory-reports/{kind}/export/{table_key}` | **已 writer** `get_audited_read_db`；db→get_user | build 分派原 vehicle/procurement/warehouse/transport 报表，`audit(export, kind+'_inventory_report')` 后 **路由70 commit** |
| `app/visit_activity_api.py:18 export` | `GET /api/visit-activity-reports/export/{key}` | **已 writer** `get_audited_read_db`；db→get_user | build_visit_activity 读取原数据，`audit(export, visit_activity_report)` 后 **路由27 commit** |
| `app/flow_api.py:436 analytics_export` | `GET /api/flow/analytics/export` | **已 writer** `get_audited_read_db`；db→get_user | build_analytics 与原客户筛选读取，`audit(export, flow_analytics)` 后 **路由453 commit** |
| `app/flow_api.py:215 download` | `GET /api/flow/files/{file_id}` | **未 writer** `get_db`；db→get_user | 原单/逐文件权限、扫描/摘要核验后 `audit(download, flow)`，**路由223 commit** |
| `app/dossier_grant_api.py:114 record` | `GET /api/dossier-grants/{grant_id}/record` | **未 writer** `get_db`；db→get_user | `service.read_record:556 → _record_access:542`，追加 DossierAccess(action=record)+AuditLog(dossier_read_record)，**service553 commit** |
| `app/dossier_grant_api.py:119 files` | `GET /api/dossier-grants/{grant_id}/files` | **未 writer** `get_db`；db→get_user | `service.received_files:577 → _record_access:542`，追加 DossierAccess(action=directory)+AuditLog(dossier_read_directory)，**service553 commit** |
| `app/dossier_grant_api.py:124 download` | `GET /api/dossier-grants/{grant_id}/files/{file_id}` | **未 writer** `get_db`；db→get_user | `service.download:596 → _record_access:542`，授权指定原件及源门店/扫描/字节核验后追加 DossierAccess(action=file)+AuditLog(dossier_read_file)，**service553 commit** |
| `app/stock_report_api.py:20 export` | `GET /api/stock-reports/period/export` | **未 writer** `get_db`；db→get_user | build_stock_period 读取原期间物资，`audit(export, stock_period)` 后 **路由27 commit** |
| `app/material_value_api.py:23 export` | `GET /api/material-value/export/{key}` | **未 writer** `get_db`；db→get_user | build_material_values 读取原收入/成本，`audit(export, material_value_report)` 后 **路由34 commit** |
| `app/repair_material_api.py:21 export` | `GET /api/repair-material-reports/export/{key}` | **未 writer** `get_db`；db→get_user | build_repair_materials 读取原实际领退料，`audit(export, repair_material_report)` 后 **路由31 commit** |
| `app/main.py:425 export_csv` | `GET /api/export/{module}` | **未 writer** `get_db`；db→get_user | 原 require_full、filtered_query/readable_query 与 serialize 读取，`audit(export, module)` 后 **路由439 commit**；保留 legacy 闭面和最多10000行拒绝 |

Dossier 的 `_grant/_live_access(lock=True)`、`authority/_source_scope` 仍逐项验证当前接收员工、岗位/access_version、原店/接收店、独立批准范围、到期/撤销、原文件快照等；原 service 在响应之前提交访问日志，IntegrityError/OperationalError/StaleDataError 原转换为 409，不能改为 best-effort 审计或提前返回 bytes。writer 接线不能改跨店授权、授予确认能力、去掉上述锁/守卫或放宽 Runtime 能力。

## 未纳入上述审计候选的实际条件 writer

`app/flow_api.py:327 master_list`，`GET /api/flow/master/{kind}`，db=get_db→get_user。只有 `kind=='templates' and db.info.get('write_store')` 时，`flow_documents.ensure_templates:40` 查询后为缺失 kind 新增 `DocTemplate(approved=False)`，在46 flush，随后路由330 commit。这是已有模板初始化写，**不是 audit/access log，也不是纯读**；单独登记，不混入下列8项审计补丁候选。当前门店在 aggregate 模式 write_store=None，不执行初始化。所有 kind 共用此入口，不宜未经独立精确补丁登记把全部 master 浏览升格为 writer，亦不应删除原初始化或自行新增 API。

因此 221 个同步 GET 的分类为：12 个审计/访问提交、1 个条件模板初始化提交、208 个未发现成功读取路径的实际持久化写入。失败拒绝证据另见下段，不能据此给所有 GET 一律加 writer。

## 纯读排除与独立闭面

- 原 `GET /api/flow/files/{file_id}/security` 的 file_security_detail/security_info 只查扫描凭据；不扫描、不写 scan event，不纳入 writer。
- Dossier `catalog/source/listing/detail` 只查授权/快照/权限；访问日志只在表内 record/files/download 调用 `_record_access`，不能给所有 dossier GET 一律加 writer。
- 原报表 JSON（stock period、material-value、repair-material、visit-activity、questionnaire、inventory、flow analytics）只查与计算；写审计的是表内 CSV 入口。`GET /api/reconciliation/batches/{key}/export` 经 svc.get_batch 只读取冻结 manifest 并生成 CSV；`GET /api/vehicle-procurement/reconciliation/export` 经 reconciliation_rows/authority 只读取原采购对账数据；`GET /api/business-assistant/issues/export` 只调 issues/read view 并生成 JSON。三者没有 audit/access/commit，不因 export 名称纳入。
- `main.note_refusal:151–181` 在真实403/指定422失败后另开 SessionLocal，record_refusal 后177 commit；这是异步 HTTP exception handler 调用的独立拒绝记录事务，不能由成功 GET 的 request-local writer 接线概括修复。不要给所有纯查询 GET 持锁，也不扩权限/忽略原拒绝。
- 认证、管理/配置、multipart upload/scan、日报模型、助手 prepare/confirm、Runtime command、Worker 与其他另开 Session 的事务是独立闭面；本文的8候选不覆盖、不开放、不宣称修复全应用 busy/517。此前127同步 POST/PUT审阅与本文不互相替代。

## 7 个 async/stream GET（单独闭面，不加本候选 writer）

| 文件/函数 | 完整路由 | 当前本地事务/异步边界 |
|---|---|---|
| `assistant_runtime_api.py:288 get_run` | `GET /api/business-assistant/runs/{run_id}` | get_db→get_user；_capture结束原读事务，独立_reader即时重验、原native GET投影；无本入口审计commit |
| `assistant_runtime_api.py:383 get_plan` | `GET /api/business-assistant/plans/{plan_id}` | get_db→get_user；同源独立_reader/原计划投影与native查询；无本入口审计commit |
| `assistant_runtime_api.py:449 get_workspace` | `GET /api/business-assistant/workspace` | get_db→get_user；read_workspace独立读取与即时重验；无本入口审计commit |
| `assistant_runtime_api.py:477 get_notifications` | `GET /api/business-assistant/notifications` | get_db→get_user；read_notifications:910只读取现有通知并重验；随后mark_notification_read:955的commit991属于原POST，不误归给此GET |
| `assistant_runtime_api.py:498 execution_result` | `GET /api/business-assistant/sessions/{session_id}/proposals/{proposal_id}/execution-result` | get_db→get_user；原 receipt lookup + native只读投影/独立授权核对；无本入口审计commit |
| `assistant_runtime_api.py:716 run_events` | `GET /api/business-assistant/runs/{run_id}/events` | SSE；open_event_stream在独立anchor/_reader读取并持续授权重验，iterator/断开负责关闭；不能持SQLite writer等待流/heartbeat |
| `business_assistant_api.py:193 work_status` | `GET /api/business-assistant/sessions/{session_id}/work-status` | get_db→get_user；workboard.work_status:307经 business_tools.native:156 → service.run_tools/registry → _run_registered_tool(read_data) 查询原GET /api/flow/cases/{case_id}，末尾重验。read_data 在 service.py:933 先 db.commit 结束原读取事务，再 await gateway；返回status>=400时调用 record_issue:381–389，新增 AssistantIssue 并经 commit 提交诊断。成功读取不追加 audit/access，但**不能称全无 commit 或失败写入**；含 await 的独立边界不并入8同步审计候选 |

`assistant_runtime_principal._reader:95` 使用同 Engine 的独立 Session(autoflush=False)，结束 close；不是提交器。Runtime 域目录既有 `DG_RECORD = GET /api/dossier-grants/{grant_id}/record`（dossier_grant.py:21、_call:68、read_fact链167），按原定义可产生表内子入口访问审计；本次子入口依赖修复仍由原请求 Session 负责，不能把有 await/native/SSE 的外层 GET 改成持续 writer，不能改该已审阅能力目录或把审计叫业务确认。本文没有宣称所有异步嵌套读取全无副作用。

2026-10-01 补充审阅修正：首轮 work-status 行未穿透 run_tools 的 registry 动态分派，遗漏 read_data 的读事务 commit 与失败 AssistantIssue 持久化；上行已按本地实际调用链改正。这里是明确独立的异步诊断 writer 边界，不通过把该外层 GET 改成 get_audited_read_db/get_write_db解决，也不把它算作成功文件/CSV审计读取；原8同步候选集合不变。

## 精确修改候选与验证边界

只列以下8函数的 `db=Depends(get_db) → Depends(get_audited_read_db)`，及 dossier_grant_api/stock_report_api/material_value_api/repair_material_api/main 必要导入。全部原db→user顺序已正确，不移动/修改service或权限/业务能力/模型目录。

结构化清单 `V/browser-click/launches/audited-read-writers-candidates.json` 为 top-level array，8项，字段严格为 file/function/method/path；若既存则不覆盖。补丁由主任务先登记，再实施/审阅。

静态范围只确认源码调用链与依赖；未启动服务、导入 app、跑测试或重试请求，不能记 passed。后续真实浏览器新外部合成镜像至少核对原文件下载、各CSV原数据范围/内容、Dossier记录/目录/逐件下载成功与原过期/撤销/账号/岗位/扫描/摘要拒绝、在数据返回前原审计已commit、真实503/409错误可见、SQLite并发写/提交后下一事务及普通read/PG/async闭面。保持原193/111、full53、101/283、PG、员工试用/生产门槛；本文不继承旧成绩，不将8接线称为193业务完成。

## 当前源码指纹

下面为本文读取时原字节 SHA256（不是旧候选/HEAD的替代）；每项函数 hash 使用其 def 至 end_lineno 的原字节文本，UTF-8编码，保留源码换行。正文行号对应这些文件。

当前 Git HEAD：`8993ca8c755194a42a48e7323fe355e80c6bf9ae`；工作树有既有未提交修改。

| 文件 | 原字节 SHA256 |
|---|---|
| `app/assistant_runtime_api.py` | `98b7273881f2a21f9989c7ae50f071c37758627ed7565a92b309112247cc2d7c` |
| `app/assistant_runtime_domains/dossier_grant.py` | `9de1bf5ae2a72f9011b031aff0479bb7f8507dd8e3469ce259b547bb4191cd35` |
| `app/assistant_runtime_principal.py` | `797cb91f13436e6aa84796fe75cd521070adb37335095b727704c3d9d9ac0eef` |
| `app/assistant_runtime_workspace.py` | `4032130c90153010b1e6ff689b5974e9d5a0abca9f42b7af6f849da5cd444bf0` |
| `app/business_assistant_workboard.py` | `f2132cf608d15eba0680c5071146b5fa8707ef643b25e3ec47279c8f436a8e13` |
| `app/customer_service_api.py` | `eb500bead91e3e8584d9c603e3e8830b0adffb5a451aa4d2b895af911b760857` |
| `app/db.py` | `d7d9143dcfec6eb663dc1fe9f3aad77aa79462b4bd06e685fcd517803399ed89` |
| `app/dossier_grant_api.py` | `a8ec3e4c56cc36d1c3dd8069c7f4dcbcd5a3691f1de2e34a31505d60692dd8b6` |
| `app/dossier_grant_service.py` | `3c919aa4686968daef8b6b8e4ebb050476876c4e16097e094793905ca16825af` |
| `app/file_security.py` | `430fa17eee8c84a5d305e90c9b6932608c66d95abd94b38103dac9d20301fa9e` |
| `app/flow_api.py` | `e6b2a3b8442da3bcef3b45d701e0304930ff5127f5fca22a613e00c43b9139c3` |
| `app/flow_documents.py` | `657f81096f3f9791cf427d2d090afbb53dfb8764920adcc52e7158b53aaad290` |
| `app/inventory_reports_api.py` | `6e8a39836df7e7a83350208b5aee019a4e2002a7a9616cccf981bf93ce37a3f3` |
| `app/main.py` | `9f21f180c1c53513dae2bfcb55b14e43f677d46a776ef0a694a2124e1e09e274` |
| `app/material_value_api.py` | `610876f43c2d14ce5e28eb007896a544f67fa8f016c428e53de8bb099167061d` |
| `app/private_files.py` | `e81f6334cab67c5648cbccbf7cb6c76df303d6b0250168b87ae863dc2ebb529d` |
| `app/repair_material_api.py` | `ce2c7799385ba5bc6cbeba23ddde5e288f151591ebe8424a89cb1ba8d289c33d` |
| `app/security.py` | `1d893b9a6c5a71f1d38cd8e0ecf741fe6edd7cf75ca5e3620d1b824bd21f7e76` |
| `app/services.py` | `b36bd51c2d9f5b1ebcbc94e3bf6d30daa1cabc59e3d77f1f6b52a4ea02cc84b4` |
| `app/stock_report_api.py` | `a061442aaea938a8e9817528d74439e5392c8e4927d1945e5b896ddd640f3684` |
| `app/tenancy.py` | `7c39d67e6af3e719dc8f9dc4040394297ea360daa048a41968d3a789373606a8` |
| `app/visit_activity_api.py` | `ea3a68be9e2e546f03a51f1df414c46add06b25fb030a2b0fcf48ae020e0c158` |

| 审计入口函数 | 函数原文 SHA256 |
|---|---|
| `app/customer_service_api.py:290 questionnaire_export` | `562a254179e2898a3189cc2f44c4d25be70b9416e3922b18485e7df53cbd749b` |
| `app/inventory_reports_api.py:58 export` | `ab17c20874d0c9264c3190609916448e6b9c092bfbf327f62e88fb42bf8d07f9` |
| `app/visit_activity_api.py:18 export` | `447c915bb9c162da6c066ca4e466931f6a6470286687f4d77debf7981510c63f` |
| `app/flow_api.py:436 analytics_export` | `b8c5815b2fb4baad1965db7d9970f3b1a929c71bcab2eb84188e1ce7ab6425c2` |
| `app/flow_api.py:215 download` | `974f28f6fe5ebe3350e5507a31b71bdf2bc169dad8cc5e515e24fb7d41cc6281` |
| `app/dossier_grant_api.py:114 record` | `362c168f8a4cb15e46c4e90e0024a27bdc614e04130e62428e2c2a0f48af5e0e` |
| `app/dossier_grant_api.py:119 files` | `db0505c698537cba02363f12dc39335960903ac9fd5f741de22e7b43024db46d` |
| `app/dossier_grant_api.py:124 download` | `9bc2912b73392a01bb8017335b78be0015a2c699b271fc9f17c880c164f4ff45` |
| `app/stock_report_api.py:20 export` | `44c93f09f12b2c68df577a4525c715448a3e1e3ee5c1fe65ee84acbb0607f674` |
| `app/material_value_api.py:23 export` | `6c2fa1249fbc478e9d6d51f4c7a2f6120d1685f041f0396cfaf4884861999078` |
| `app/repair_material_api.py:21 export` | `0c32853a6c2c385cb1d02495f1ca508988968ff831b4c02c22af85257dd9967d` |
| `app/main.py:425 export_csv` | `614b2653bc743fe3a9ad65af78a0662461e09ec328c3f6f91b7c7e9985b1e061` |

结构化8候选 JSON SHA256：`fcea48139db0128f40cc76358847efd1afd72536b86fa588ba158940f7e3063d`；处置 `created`。
