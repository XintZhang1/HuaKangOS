# Runtime队列短事务的SQLite源码审阅

2026-10-02，manual_review_draft；仅源码读取/AST结构检查，未执行app、worker、数据库、模型或浏览器，未编辑生产/tests/runner。审阅 `app/assistant_runtime_queue.py` 实SHA256 `7953ca68f54cea9e76e45b92eb37bd1ee6f2b3a01c55c26541f34ea9aa013e7c`。第14轮协议异常/nativeCookie的Run终态超时由root报告并停止；以下是源码能证明的事务窗口，不能单独认定所有超时原因。

## 原合同和连接

queue模块声明每个队列方法拥有短事务，claim/reclaim必须新的无事务、无租户scope Session；原native读取先于enqueue写入；身份读取使用同Engine独立Session。`_fresh_worker_session:535–538`确实拒绝已有事务或scope，`_clean`仅拒绝new/dirty/deleted/未结束preparation transaction，不会排除一个普通只读事务。`_scope`只设置/核对原员工单店范围，`_version_cas`限制Run/AssistantSession控制表并逐项CAS owner/store/version、session/status/fence/lease/auth source/stop_requested，不开放业务bulk写。

`app/db.py:29–40`SQLite连接isolation_level=None，普通begin事件发BEGIN；仅连接执行选项huakangos_sqlite_write_transaction=True才发BEGIN IMMEDIATE。busy_timeout=30000不消除WAL既有读快照升写失效。PostgreSQL沿原REPEATABLE READ和行锁/CAS，不应按SQLite改事务规则。

`assistant_runtime_principal._reader:95–117`要求同一个Engine的新Session，autoflush=False，finally close释放独立读事务。revalidate_principal:253及control:448要求db.get_bind()与principal._bind严格对象同一；读取依据已提交Run/Grant/User/Store/UserStore/Session真实事实，不能改成看自己的未提交写来消除冲突。

## 首写与锁持有边界

|方法|自身读取到首写的实际路径|锁持有到结束|
|---|---|---|
|claim_next/claim_mcp_run→_claim_queued_run 565–625|fresh guard后573首先_slot_lock；SQLite548执行UPDATE Run WHERE false，首SQL即预占写者。然后575全局slot、583候选、597独立maintenance读、602_scope内Session/Plan/Run读、611busy CAS/612Run CAS。claim已有write-before-read，无同类先读升写窗口。|573起至621commit；无候选/已占用576/591/608rollback；异常_failure rollback。619独立授权读仍读取已提交queued，提交后624才构造principal。期间无模型/native await。|
|reclaim_expired 1988–2040|fresh guard后1998独立reader挑expired，2005独立maintenance均已关闭；本Session2009_lock_rows SELECT开始BEGIN，2018_safe_retry可读取RunItem/WorkItem/Proposal/完整历史，2023首CAS。这段存在本Session读后升写窗口。|成功首CAS2023至2037commit；2031仍用独立已提交maintenance验证原run_version/status/lease/auth，异常rollback。不复活权限；不重放confirmation/uncertain。|
|heartbeat 628–644|630独立身份重验后，634本Session_lock_rows读Session/Plan/Run，638首次Run lease CAS，639原busy heartbeat CAS。存在634→638读后升写窗口。|首CAS638至641commit；640独立重验，异常rollback。原fence/lease_owner及活租约不变；busy语义version原不变，不缩短后来租约。|
|release 1837–1896（实际finish方法）|1854独立身份/control重验，1858本Session锁读；success1861还读running项，retry1870_safe_retry读持久历史；1876才首Run CAS。存在读取→1876升写窗口。|1876至1893commit；1879busy释放同事务，1885仅允许同步已构造reply appender，1890 lifecycle/event/outbox，1891flush，1892独立重验。声明appender不能commit或模型/native网络I/O；awaitable被拒绝，异常rollback。|
|lock_for_write 1106–1135|1119独立授权重验，1124本SessionSession/Plan/Run读，1130Run空增量CAS首次写。存在1124→1130窗口；_clean不保证本Session此前没有其他只读快照。|1130起不在本函数commit，交调用者在保存artifacts/flush后立即独立重验并commit或rollback；本函数明确禁止这段跨native/model等待。1131标记preparation transaction，1134绑定fence事务。|
|_budget_transaction /finish_model_round 等1248–1259|调用lock_for_write，因此共享上述读后升写窗口；ledger读取/变更为本地持久预算事实，不是模型请求。|1250锁写后到1256commit，异常rollback；不得把reserve和真实模型请求放同一个未提交事务。|

`_safe_retry:1632–1711`只基于已存模型frame/RunItem/manifest/work/card/confirmation读取分类；多次同步查询扩大首写前窗口，未调用真实模型或native请求。安全重排仍保留有限退避30/120/600，不把confirmation或未知结果重放。本审没有建议增加自动SQL/业务请求重试。

## 最小修复方向和不可机械复用项

对确属worker自有、已确认fresh/no-transaction的短Session，应在本Session首条SQL之前预留SQLite写者，并保持原scope、CAS、fence和提交前独立身份重验。claim已经做到了，不能为统一格式再改变其公平global slot/MCP目标顺序。heartbeat/reclaim/release的Session fresh事实还需结合worker/runner调用者独立审阅；lock_for_write被多处调用，必须确认原读阶段已结束且无脏写，不能默默rollback调用者半成品事务。

不要直接把get_write_db套给这些Runtime Session：它把db.bind替换成带write=True的OptionEngine。既有principal若绑定原Engine，随后重验会因严格bind identity不同拒绝；即使principal从该OptionEngine签发，_reader沿相同bind再开独立Session会继承BEGIN IMMEDIATE，在本Session已占writer时争自己的写锁。只给新短写Session连接首SQL执行选项（而非换其Engine）可保留独立read的原Engine语义；已有事务时执行选项已经太晚，应由明确调用者结束只读阶段并开短新Session，不能修改权限判断/任意回滚/跨模型等待。

任何具体改动均由root登记补丁并实施，本审未改代码。需要本轮真实复验的范围包括：短Session首SQL日志、claim/heartbeat/release/expired reclaim实际Run与busy同事务、独立身份快照、原错误/未知/取消闭包及无新未处理异常。源码窗口消除不等于第14轮失败已通过，旧partial证据不能继承为全量成绩。
