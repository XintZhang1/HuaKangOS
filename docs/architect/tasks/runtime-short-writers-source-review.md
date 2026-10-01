# Runtime 短写事务独立源码审阅

- 任务：PATCH-M8-1-RUNTIME-SHORT-WRITERS-01，M8.1 当前候选，2026-10-02。
- 范围：独立只读审阅三个已实施文件；本审阅者仅写本报告。没有导入 app、执行应用、SQL、浏览器或测试，没有读取真实环境配置或密码。
- 结论：实际源码符合事前有限范围，可交根代理冻结后复验。下述结果是静态代码审阅，不能记业务测试 passed、full53 通过、193 项验收或生产放行。

## 原件与指纹

事前原件位于 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/launches/runtime-short-writers-before-20261002/`，保持原字节；登记记录为同 launches 下 `runtime-short-writers-edit-20261002.json`，SHA-256 为 `62a2565158a372382d5e8710045ce7c578093526cbf9f15f3e6fb0ac830a0afe`。

| 文件 | before SHA-256 | 当前 after SHA-256 |
| --- | --- | --- |
| app/assistant_runtime_queue.py | 7953ca68f54cea9e76e45b92eb37bd1ee6f2b3a01c55c26541f34ea9aa013e7c | 49f8195d3d5847812e962028df02b653d5caf6c59112785296c458a1523530f6 |
| app/assistant_worker.py | 59e6d51d389c03137e8073667ff7feaa1130938cb501b9b7b8074d71304bdc26 | 94c5b0d814bc3ae3112959e58fdd4fb74dede6307a8206b48673d0e55c491fdc |
| tests/browser_click/scenarios.py | aeca15df8a419f6ec08ce9d7dd914c4b35ef3543fee719a8cd4cc7d6a0a7bde0 | c51593227fc4c4c767d257d5ad351f6a9469eed60458eb849b7e2a81a3a415db |

三项 before/after 均与 edit JSON 相符。审阅只在内存按明确新增文本逆改：三个整文件均逐字节等于事前原件，含原换行；没有将规范化文本相等冒充字节相等。另分别删去新增 AST 节点，三个整个模块 AST 均与原件相同。其它函数、装饰器、调用参数、常量及场景注册未变。

## Queue 四个短写入口

新增 `_sqlite_writer`（553 行）先判断方言。仅 SQLite 执行 `_clean`、`db.rollback()`、既有 `_slot_lock`；没有修改 `db.bind`、Engine、Connection 执行选项、租约时间、fence 或重试分类。PostgreSQL 整个 helper 分支跳过，原事务及表锁行为不增加。

既有 `_slot_lock` 的 SQLite 路径先取得连接，再对固定 Run 表执行 `WHERE false` 的 UPDATE，不改任何行或版本；本补丁复用其在首次主会话读取前预约 writer 的机制。它消除这四处先建立主会话读快照、再尝试升级写入的窗口，仍可能在另一个 writer 竞争时遇到原 busy timeout；没有失败写重放。

四处唯一接线为：

| 原入口 | helper 调用行 | 保留边界 |
| --- | --- | --- |
| heartbeat | 641 | 原 `_clean`、独立身份重验、单店范围之后，try 内首次 `_lock_rows` 之前 |
| lock_for_write | 1132 | 原参数/control 校验、身份重验、原 run_id 及 `_scope` 之后，首次 `_lock_rows` 之前 |
| release | 1867 | 原 outcome/appender 校验及 guard、范围之后，try 内首次 `_lock_rows` 之前 |
| reclaim_expired | 2019 | 原 fresh worker Session、独立过期来源快照之后，try 内首次 `_lock_rows` 之前 |

这些入口在新接线之前没有本函数构造的主会话写片段。`_clean` 仍先拒绝 ORM new/dirty/deleted 或当前 preparation transaction，才允许 rollback 结束干净读阶段；不会把半张卡、事件或其它待提交写入悄悄丢掉。rollback 保留 Session 的门店 scope info；`_lock_rows` 原 `populate_existing` 重读及版本、来源、busy token、lease、fence 检查仍原样。原最后独立 fresh guard、commit 和异常 rollback 保留。

主 Session 保留原 Engine，RuntimePrincipal 的同 Engine 校验不变；独立身份 reader 不继承 writer 选项，仍用独立连接并在读取结束时关闭。新增 helper、四入口的 AST 均无 await。`release` 原同步 appender 的 awaitable 拒绝仍在，不扩大为持锁网络或模型等待。`lock_for_write` 原由调用方负责失败 rollback 的合同也未改。

## Worker 两个独立 Session

仅 `.db` import 增加 `get_write_db`，`beat` 213 行、`beat_cleanup` 231 行各在 `with factory() as db` 后、首次 metadata 读取前调用一次。

这两个 Session 由函数自己新建和关闭，没有 RuntimePrincipal 参数、没有将自己的 bind 传给运行执行或授权 reader。既有 get_write_db 仅为 SQLite 在该 Session 首读前预约 writer；OptionEngine 不会修改 SessionLocal 工厂或其它 Session。PostgreSQL helper 不做变更。

`beat` 原本 worker 自有 metadata key、字段、写入和 commit 完全不变。`beat_cleanup` 原前缀筛选、保留自身 key、过期条件、删除范围及有删除才 commit 原样；没有删除时 with 结束关闭 Session 并回滚释放预约。两个函数均同步，无 await，因此没有把 metadata writer 持到异步等待。

## 原 UI 退出场景

`slow_logout` 只在原 Cookie 清除、登录页迟到内容保护、原 counts 与全业务摘要不变检查之后，截图之前增加 11 行。原创建 Run、等待 running、员工实际点击注销及 3 秒等待未动。

新增 nested `cancelled` 仅通过原只读 Database 读取 `e.latest_run` 的真实 Run，必须唯一且 status 为 cancelled；`e.wait` 沿用未修改的默认 timeout=25 秒（原 344 行），没有延长等待到 90 秒，也没有调用 API 取消或修改数据库状态。

终态必须满足 lease_owner/lease_until 都为空、finished_at 存在；同一 Run 的事件末项为 run.cancelled 且 seq 等于原 Run event_seq。原 owner/session 的 proposals 必须为空，并再次核对同一个前序业务全行摘要无变化，才记录有限原 Run/事件/零卡观察并截图。输出 card_count=0 有真实零行断言支撑。

整个 scenarios 模块逆去这段后 AST 和字节都与事前相同：其它场景、Evidence 的 `finish`/context 生命周期、SCENARIOS/BUSINESS 注册、时间预算及 full53/193 汇总规则未变。新增终态异常会让原场景失败，不把局部诊断并入完整业务通过。

## 因果与待验证边界

full14 的原 SQL_BUSY5 日志缺少具体语句边界。90 秒租约以及迟到终态只能说明前序占槽与恢复时序，不能据此确定某一 API 或本补丁解决该次实际竞争。四处读转写窗口及两处 metadata 窗口是代码可见的范围；本报告未将其写成已定位 full14 因果。

此前 9/9 核心诊断的未复现不继承为补丁通过。五次外置 logout probe 发生执行期间 helper 字节改变，原报告必须保留为混合 helper 条件下的诊断，不能记正式冻结复验；原 b072 启动字节已另存 started 文件，本补丁没有改写其报告。

后续由根代理完成当前三文件、测试、执行器的冻结及完整本轮复验。实际通过前仍保留 full53、193 项人工体验、生产与其它原环境门槛；不把本静态结论写成动态 passed。
