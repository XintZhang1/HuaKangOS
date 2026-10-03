# PATCH-M8-1-SQLITE-WRITER-BOUNDARY-01

2026-10-03，当前唯一在办里程碑 M8.1。按业主持续收口授权修复真实隔离执行发现的 SQLite 短写事务边界，不改变原业务、权限、确认或版本合同。

core04 的外部原报告和失败保留：所选 7 场完整执行，2 通过、5 失败，CLI 1、服务 0、forced=false。server.log 记录 SQLite OperationalError code=5 的 UPDATE，04:35:56 的表为 business_assistant_sessions，原发送 Run 返回 409。04:32:40 的表标为 other，原脱敏表名白名单不足以据此精确归因，不称已修 outbox 四处再次失败。静态源码确认当前发送 Run、员工跟进控制及通知已读均可在 SQLite 的同一延迟读事务中先 SELECT 再 UPDATE；FOR UPDATE 在 SQLite 不预留写入，另一个写者提交后原读快照不能提升为写事务。

精确允许生产范围：

- root 负责 `app/assistant_runtime_queue.py` 的 `enqueue_run`：原 native 入口核对完成后、原 try 内主写会话读取控制行前，复用既有 `_sqlite_writer(db)`，保留原请求编号/digest、Session/Plan 范围与版本、同事务 Message/Run/Event 和最终权限重验。
- 本实施者负责 `app/assistant_runtime_plans.py` 的 `followup_transition`。实际服务文件为此名，仓库没有 `app/business_assistant_plans.py`。仅在现有 try 开头、主写会话读取 Session/Plan/Step/Grant 前调用同一 helper。
- 本实施者负责 `app/assistant_runtime_workspace.py` 的 `mark_notification_read`。仅在现有 try 开头、主写会话 scope/Notification 查询前调用同一 helper。
- 本补丁记录由本实施者维护；不扩到相邻 Runtime 入口、UI、实施计划、测试、runner、共享 fixture 或数据库配置。

既有 helper 只在 SQLite 上验证干净读阶段、rollback 关闭之前的读事务，保持原 Engine 身份，在新事务的首条业务 SQL 执行固定 Run 表零行 UPDATE 以预留写入。它不修改 Run 行、scope、权限或请求编号；PostgreSQL 不改变。不能在已有未提交产物时回滚调用者，不把 helper 放在主写会话 SELECT 之后，不通过更改 WAL/timeout、自动重试或换 request_id 修复。

原独立当前登录/员工门店权限、Cookie/CSRF、Session/Plan/Step 版本与 Grant 生命周期、停止语义及原 ORM/CAS 检查保持。helper 等待后仍执行原当前权限重验，变更或竞争继续由原 403/404/409 合同拒绝。两处短写范围均没有模型、网络或 native await；Workspace GET 保持只读，来源在 await 后变化的 409 不取消。revoke 原二次确认在版本/授权范围变化时解除，不能强留确认状态或自动重放动作。

本补丁先登记后实施。实施者只做 Python AST、差异/空白检查及源码人工审阅，不导入 app、不启动服务/浏览器/数据库/验证、不调用真实模型、不 commit/push。静态检查不等于动态通过；root 负责新外部候选验证和唯一实施计划状态记录。

2026-10-03 实施与静态审阅：上述本实施者两处仅增加 local helper import 与原 try 开头的一次 `_sqlite_writer(db)`，未修改其他控制行、权限、scope 或版本条件。人工核对 helper 保留原 Engine、先验证干净读阶段再 rollback、首条写事务 SQL 是固定 Run 零行 UPDATE，原当前权限和版本读取均在此之后；原 scope 信息保持，独立授权 reader 不继承写事务选项。两处函数及写阶段调用链没有 native/model await；已变更的跟进在原 commit 后返回，幂等 no-op 由原 API 在返回后立即 rollback，再进入异步 PlanView 读取，通知已读也在原 commit 后进行最后独立身份读取。两生产文件 AST、原 git diff --check 和新补丁逐行空白检查退出 0；静态检查没有业务验收含义，core04 失败不覆盖，候选待 root 动态复验。
