# 六个管理闭面写入与异步读取边界补核

**任务与负责人**：`audited-read-writers-review-c`；M8.1 主任务 `/root` 的只读子审阅，子代理 `/root/closed_writer_audit`。2026-10-01。

**目标与交付**：精确核对 `main` 的 Users 四项、Stores 两项同步管理写入，补核异步 GET/SSE 与文件下载安全失败链；产物仅此页及仓库外 `V/browser-click/launches/closed-short-writers-candidates.json`。不维护共享进度、不改源码或测试、不导入 app、不启动应用、不访问数据库、真实 `.env`、凭据或附件。

**结论**：六项均有真实写分支及提交链、同步处理器、本地追踪无 `await`，均明确属于管理闭面。初次审阅采用普通 `get_db` 且参数顺序已为 db→get_user；主任务随后独立登记并实施了精确依赖补丁。本页末尾的独立复核确认六项及 `flow.master_list` 仅替换 db 依赖，原 body/decorator/schema/CAS 保持。它们不在原 127 项业务写范围内，不因修复事务依赖而开放给助手；只有静态源码结论，没有动态通过结论。

## 依据、快照与授权范围

遵循 `AGENTS.md` 当前浏览器点击授权、§4 身份/确认边界、§5 模型闭面、§9 隔离与证据；补读当前计划 M8.1/CP-35、原交接及架构读取合同，沿用 `docs/architect/tasks/reviewed-short-writers.md` 的 OptionEngine 评审。DSH Architect 用于独立只读审阅与向主任务交接，不新增里程碑或审批。

本次实际 `git rev-parse HEAD` 为 `8993ca8c755194a42a48e7323fe355e80c6bf9ae`。工作树存在多处主任务修改；主任务提供的 `1cc5e944`/`a7f1422d` 是其源码/脚本快照标识，不写成 Git HEAD，也不把历史 127 评审中的原依赖当作当前源码。下文行号为本次读取字节；后续主任务的接线改动须另记新指纹。

| 本次读取文件 | SHA256 |
| --- | --- |
| `app/main.py` | `9f21f180c1c53513dae2bfcb55b14e43f677d46a776ef0a694a2124e1e09e274` |
| `app/db.py` | `d7d9143dcfec6eb663dc1fe9f3aad77aa79462b4bd06e685fcd517803399ed89` |
| `app/security.py` | `1d893b9a6c5a71f1d38cd8e0ecf741fe6edd7cf75ca5e3620d1b824bd21f7e76` |
| `app/user_access_service.py` | `34edda137dabb428e636e823c1a4d80431ae39fe4386481dac45c4fbb581bf77` |
| `app/assistant_runtime_access_signals.py` | `4c1641475edebb9eea842f6e99dfa654cf13b71518867bf6211437b5eab2df63` |
| `app/schemas.py` | `14bfa505a8df0e5b31911a3c2425c719f6e4f2a63093c0802e9006f58ac4b3ff` |
| `app/business_assistant_gateway.py` | `423d10581c670b741e4bc28c62af9df7e1e13575dbb2810fa2474c98dcc1cd7d` |
| `app/business_assistant_capabilities.json` | `f9446c0f0ffc35368b7cb5d87193d5493e6948ac1da191f39e59fe302ceaf8ed` |
| `app/flow_api.py` | `e6b2a3b8442da3bcef3b45d701e0304930ff5127f5fca22a613e00c43b9139c3` |
| `app/file_security.py` | `430fa17eee8c84a5d305e90c9b6932608c66d95abd94b38103dac9d20301fa9e` |
| `app/private_files.py` | `e81f6334cab67c5648cbccbf7cb6c76df303d6b0250168b87ae863dc2ebb529d` |
| `app/assistant_runtime_api.py` | `98b7273881f2a21f9989c7ae50f071c37758627ed7565a92b309112247cc2d7c` |
| `app/assistant_runtime_workspace.py` | `4032130c90153010b1e6ff689b5974e9d5a0abca9f42b7af6f849da5cd444bf0` |
| `app/business_assistant_workboard.py` | `f2132cf608d15eba0680c5071146b5fa8707ef643b25e3ec47279c8f436a8e13` |
| `app/business_assistant_service.py` | `22c52c2cb5d86a1332bf8fef3ed8317a3222bbf176c98168e5ffa54896e69901` |
| `app/assistant_runtime_receipts.py` | `b0b91a29b7040bd64836a715a2384033da887c174e51705dac3a7ae164043106` |
| `app/assistant_runtime_principal.py` | `797cb91f13436e6aa84796fe75cd521070adb37335095b727704c3d9d9ac0eef` |

## 六项同步管理 writer 的精确清单

六项均在 `app/main.py`，接线前为 `db=Depends(get_db),user=Depends(get_user)`，db 参数在认证参数之前；接线后只将此 db 依赖改为 `get_write_db`。

| 函数/行 | 完整方法与路径 | 原输入 | 真实写入与提交链 |
| --- | --- | --- | --- |
| `add_user:264` | `POST /api/users` | `UserInput` | `admin`→建立 User（密码哈希、首次改密）→add/flush 268→`assign_stores:572` 删除/新增 UserStore、flush 587–589→`audit` 270→`db.commit` 271→原 `account_info` 响应 |
| `add_users_batch:280` | `POST /api/users/batch` | `BatchUserInput` | `admin`→活跃门店、每行账号/姓名/岗位、重复与已占用账号全部先校验 289–311→每个 User add/flush 317→原门店岗位 `assign_stores` 318→每个 `audit` 319→整个原批次单笔 commit 321 |
| `edit_user:326` | `PUT /api/users/{user_id}` | `UserUpdate` | `admin`→`user_access_service.change_access:15`→按顺序锁管理员/目标、即时管理员检查、request_id/digest 回执及 access_version 校验→User CAS 53–57→可选成员替换→删除目标 LoginSession 65→audit/flush 68–70→UserAccessReceipt add 77→可选同事务 WakeEvent→commit 82 |
| `reset_password:332` | `POST /api/users/{user_id}/password` | `ResetPasswordInput` | `admin`→目标存在、拒绝重置自己→原密码哈希/首次改密 337–338→删除目标 LoginSession 339→audit 340→开关启用时 `emit_user_security_changed`→commit 346 |
| `add_store:599` | `POST /api/stores` | `StoreInput` | `admin`→Store add/flush 601→audit 602→commit 603 |
| `edit_store:607` | `PUT /api/stores/{store_id}` | `StoreInput` | `admin`→目标存在、不得停用最后活跃门店 609–612→更新 Store 614→audit 615→开关启用且 active 改变时 `emit_store_access_changed`→commit 621 |

`services.audit:25–29` 只 add AuditLog，Users/Stores 原审计 store_id=0；不自行 commit。`account_info:561`、`assign_stores:572`、`security.hash_password:32`、账号授权服务及三个安全信号 helper 均为同步函数；所追本地函数没有 await。信号 `assistant_runtime_access_signals._emit:79–109` 使用同 db 的 `begin_nested`/insert，同源 audit/receipt 校验，未新增外层 commit。savepoint 不替代父提交。

`edit_user` 的幂等 prior 分支返回旧 result 而不写/commit；拒绝路径亦可不写。这不改变其有实际写分支的分类。原 UserAccess CAS、最少一名活跃管理员、自身不得降权/停用、目标登录失效、回执 digest、权限变化信号都必须保留。其 HTTPException、OperationalError、IntegrityError 原 rollback 与 409 映射不能移除或重放。

原输入边界保持：`UserInput` 单账号/岗位/门店显式选择；`BatchUserInput` 原 1–50 行、共同指定活跃门店，批量拒绝管理员岗位；`UserUpdate` 原严格 access_version 与 request_id；密码原 12–128 字符及重置原因；`StoreInput` 原 code/name/active。不换 schema、不猜门店、不自动管理员化、不改变原批次事务。

`main.admin:252–253` 检查原 account_role；`get_user:91–115` 保留原 Cookie、LoginSession/User 活跃检查、CSRF、首次改密及 `attach_scope`。本页不扩大原管理员规则或新增旁路。

## db/auth 顺序与最小接线建议

get_db 只创建并 yield Session，接线前首个原认证查询通常是 `security.get_user:96/99`，随后 `attach_scope` 读取当前门店权限。由于六项 db 参数已经在 user 之前，独立登记后只把这六个 Depends 改为已有 `get_write_db`，不用重排其他参数。FastAPI 默认子依赖缓存沿已审阅合同复用同一个 get_db Session；不得额外新建认证/业务 Session。

当前 `app/db.py:get_write_db:58–72` 已采用只对 SQLite 的请求级 OptionEngine：首次连接前 `db.bind = db.get_bind().execution_options(huakangos_sqlite_write_transaction=True)`，然后 `db.connection()`。原 SQLite begin listener 依据 flag 选 BEGIN IMMEDIATE。此 Session 后续 commit/rollback 后新事务仍继承代理 bind；不是改原 Engine、SessionLocal 或全局事件。PostgreSQL 保持原 REPEATABLE READ；普通 GET/get_db、Worker 不接线。六项事务结束后的原响应读取也仍属于本请求 bind，最后原 get_db rollback 收尾。

`business_assistant_gateway.py:77–90` 的 `CLASSIFIED_BLOCKED_WRITES` 精确包括六项；capabilities JSON 的 GET stores 不是 Stores 写能力。修复后保持此集合与能力目录字节不变，不把六项加入 127 项业务目录，不按 POST/PUT 自动推导其他端点。

静态无 await 只证明没有协程/模型/SSE等待混入；批量账号的多次密码哈希与同步数据库/I/O 实际耗时尚未验证，不据此声称零锁等待。建议主任务先登记六项独立补丁再接线，继续通过原生浏览器隔离入口实际复验，不记 passed/done/released。

## 文件下载：安全检查不隐藏写入

当前不存在 `flow.download_file` 命名；实际处理器是 `app/flow_api.py:215 download`，`GET /api/flow/files/{file_id}`，返回已经读完的 `Response`，不是异步 GET/文件流。

1. `download:216–219` 先 scoped_get FileAsset、原 get_case、can_file 原角色与文件类别权限。
2. `require_usable:185–190`→`security_info:151–178` 查询 FileSecurity/FileScanEvent 并比较安全凭据；不可用抛 409。此链不调用 `scan_asset` 或 `_record_scan`，不新增扫描记录，不写 scan 状态、不 commit。
3. usable 时 `require_usable` 调用 `private_files.read_content:139–149`；路由 222 再读一次。read_content 查询原 FileAsset/PrivateFileObject，检查原 BLOB/对象引用、大小、摘要和对象读取。引用/字节损坏或丢失抛 409，无标记损坏、无 audit/add/flush/commit。检查动作不推断或制造业务证据。
4. 只有上述检查与读取成功，路由 223 才追加原 download AuditLog 并 commit，然后返回字节。此真实同步审计写路径由主任务另一审阅 `audited-read-writers-current.md` 负责；本页不重复拥有其候选清单。

`scan_asset:121`/_record_scan:207 的 FileScanEvent 追加发生在原上传/生成/重扫写入口；其存在不能证明 GET 会重扫。`security_info` 标签中的“已隔离”是读取既有安全结果或拒绝文案，不代表本次写入。

主任务报告 rcv08 `GET /api/flow/files/86 = 503` 是待解释的真实失败，本页未运行或读取该数据库。不能归因为“标记损坏并 commit”；当前字节损坏链原响应为 409。`main.operational_error:200–203` 将 OperationalError 变 503，成功下载审计 commit 是可达写位置，但需要有该请求关联的原异常/日志才能定位具体 SQL。不能仅因另处记录 5/517 就把该异常精确归给 file86。

## 七个 async GET/SSE 的实际写边界

只用 AST 解析当前 app 源码，不导入模块。直接注册的 async GET 共七项，均原 `get_db`，同前缀 `/api/business-assistant`。

| 函数 | 完整 GET 路径 | 静态边界 |
| --- | --- | --- |
| `assistant_runtime_api.get_run:288` | `/api/business-assistant/runs/{run_id}` | `_capture` 96 rollback 原读事务；`_run_view` 222–242 短 `_reading` 复制数据，退出后 await 对象读取，最后独立 guard；直接链无 audit/add/flush/commit |
| `assistant_runtime_api.get_plan:383` | `/api/business-assistant/plans/{plan_id}` | `shared_plan_view:338` 先短 reader 投影计划，退出后 await 原对象 GET，再 guard；仅修改返回字典，不保存 PlanStep 或状态 |
| `assistant_runtime_api.get_workspace:449` | `/api/business-assistant/workspace` | `read_workspace:411` 复制原任务/私有源，await 后重新读取比较，不生成通知/计划/卡；无直接提交 |
| `assistant_runtime_api.get_notifications:477` | `/api/business-assistant/notifications` | `read_notifications:910` 只读取已有 Notification、当前源及两次比较，不调用 `_upsert_notice`/persist/mark-read；无提交 |
| `assistant_runtime_api.execution_result:498` | `/api/business-assistant/sessions/{session_id}/proposals/{proposal_id}/execution-result` | 原 ownership、lookup_receipt 与源复核；`lookup_receipt:398–431` rollback/新 reader，保持 Proposal/WorkItem/RunItem 不变，不调用 reconcile 写入 |
| `assistant_runtime_api.run_events:716` | `/api/business-assistant/runs/{run_id}/events` | `open_event_stream:671` 使用 idle anchor 与短独立 reader；_event_batch/_public_event 退出 reader 后 await/yield；heartbeat 只读，关闭流不取消 Run/lease，不保存访问或事件日志 |
| `business_assistant_api.work_status:193` | `/api/business-assistant/sessions/{session_id}/work-status` | **有失败诊断写路径**，见下文；不能把这七项统称纯读或全部接同步写依赖 |

`assistant_runtime_principal._reader:95–117` 建立同 bind、autoflush=False 的独立 Session，在 finally close；`_capture` 先要求无 pending writes，再 rollback。Runtime 的 make_native_reader:390–419 自身不 commit，也不经旧 read_data helper。目标原生 GET 仍是独立请求/事务；外层异步视图不替代目标查询的权限或审计。例：DossierGrantAdapter.read_snapshot:93 只调用原 detail，`fact_snapshot` 的 dossier.record_readable:165–167 才调用原 `/record`；后者由原 `_record_access` 写 DossierAccess+AuditLog、commit，不能写成整个 Runtime 无任何间接审计。

工作进度失败链为：workboard.work_status:336→business_tools.native:156→service.run_tools:867/registry.dispatch→`_run_registered_tool(read_data):929–938`。933 在 await 原 GET 前 db.commit，目的是结束原读事务；正常成功分支没有新增审计/访问记录。原 GET 返回 status>=400 时，936–937→`record_issue:381–389`，以原本人会话写入 AssistantIssue 诊断摘要并 commit；它不是业务办理、DossierAccess 或业务审计事实。无计划/无本页 case 的分支可以不进入此链。

该异步 GET 不应因为有 commit 就混入六个闭面或八个同步审计 GET。已有 933 结束事务后才等待内部 HTTP，是必要边界；后续如需修复其诊断写，应独立登记并审阅等待前后的原快照、本人授权及短写阶段，避免全局或跨等待持有写锁。当前无此接线或诊断 writer 实测。本页不能把只追到七个处理器正文就写成“无写入”。

## 通用异常审计与排除项

`main.http_error:185–190` 是 async 异常处理器，不是 async GET writer。原 403/422 可经 `note_refusal:151–181` 在另一个 SessionLocal 调用 record_refusal 并 commit 177；只在原 request.state 本人/门店足够、原分类适用时追加真实拒绝。它不复用路由 get_db，当前请求 OptionEngine 不自动改变它。409 字节拒绝及 503 OperationalError 不走此拒绝审计分支。相关普通 GET 的拒绝可能有该独立审计，但不能因此把所有读取改为 writer。

首页 `main.home:683` 的 FileResponse 读取静态页面，无认证/业务写；app 的普通 GET、GET users、GET stores、助手已有通知读取、文件安全详情/lookup 的 `is_usable` 等都排除本次候选。模型聊天 POST SSE、异步上传 POST、Worker、日报模型/另一 Session 及普通只读 POST 不属于本页六项清单，不自动接线。

## 当前位置与下一步

本页和外部六候选 JSON 是静态审阅产物，已向主任务快报提交链、file86 归因限制和 work_status 失败诊断写。源/测试零改动，未运行 app、浏览器、数据库或测试，不继承旧成绩、不记 passed。主任务独立登记六闭面与另八同步审计 GET 的精确依赖补丁；原六管理 schema/权限/提交链/闭面、所有普通读、PG/Worker 不变。之后按同一 M8.1 的新外部镜像验证实际行为与原失败边界。

## 接线后独立逆向审阅（2026-10-01 追加）

主任务已先登记 `PATCH-M8-1-CLOSED-SHORT-WRITERS-01`（六管理 + 条件模板初始化共七项）与 `PATCH-M8-1-REMAINING-AUDITED-READ-WRITERS-01`（八个审计 GET），再实施 15 项依赖替换。本子任务只读复核自身七项；main.export_csv、flow.download 的相邻审计改动为已登记且另代理负责，不算额外未批准改动。

以外部 `V/browser-click/launches/audited-and-closed-writers-before-20261001/app/` 的接线前原字节为比较基准，同时核 `audited-and-closed-writers-edit-record-20261001.json` 前后 SHA256。并未用 HEAD diff 替代接线前工作树。

- 七个原函数全为同步 def，无 await；db 在 get_user 前。逐函数源码片段仅出现一次 `db=Depends(get_db)`→`db=Depends(get_write_db)`，完整函数 body 的原行字节和所有 decorator 源码均相同。参数注解、原输入类型、返回、管理员/门店/版本/CAS/回执/提交链、异常响应未改。
- main 全文件精确反向重建只撤销六项 db 依赖、已知 export_csv 的审计读依赖，以及 db 导入新增 `get_audited_read_db`；结果与备份原字节完全相同，逆向 AST 也相等。新 main SHA256 `c6df782f65a95ce6d24ffd4cde18b1e8a2581b9c57835341be90a9c02777862d`。
- flow_api 全文件精确反向重建只撤销 master_list 的写依赖和已知 download 的审计读依赖；结果与备份原字节完全相同，逆向 AST 也相等。新 flow_api SHA256 `ffbc5f2074bcabac473f66416263a7df2d45843d5e8201624b217d306ba83697`。
- schemas、user_access_service、assistant_runtime_access_signals、gateway、capabilities、db.py，以及 async 的 assistant_runtime_api/business_assistant_service 的 SHA256 均与上表初审原字节完全相同。models、user_access_models、flow_models、flow_documents、tenancy 无 HEAD 差异；没有改原数据模型/权限/CAS服务或模板生成规则。
- `flow.master_list:327` 原 `kind=='templates' and db.info.get('write_store')` 分支 330 才调用 `ensure_templates` 并 commit；`flow_documents.ensure_templates:40–46` 只为缺失 kind add `approved=False` DocTemplate 后 flush，无 await、无自身 commit。其他 kind 与聚合门店原 body 保持。依赖替换作用于此已有条件 writer 的整个处理器，不能称此处理器所有 kind 都写了业务记录，也不把初始化叫审计。

六候选外部 JSON 为 top-level array，严格只有 `file/function/method/path` 四字段，6 项全部为静态确认同步闭面，SHA256 `74a94d85eca1b7c9bca51d2268dd2df396fea3bf77ebbf5d807e9708162b290b`。它不包含 master_list 或八审计 GET，也不修改能力目录。

结论已交主任务：七项精确接线通过独立源码审阅，可进入主任务已授权 fresh3 原生浏览器闭包；这是 source 审阅，未运行 app/测试、未验证真实竞争或业务结果、未记动态 passed。async work_status 的失败诊断写及独立拒绝 Session 仍是本页记录的另行边界，当前 15 项修复不宣称解决它们或全应用所有 busy。
