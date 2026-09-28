# M5.6 编码审阅与实测记录（worker CLI、关闭和安全健康信息）

2026-09-28，集中测试阶段。Astra 批次未开始 M5.6；本轮由 Codex 侧实现 + 外部实测记录。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新增产品文件 | `app/assistant_worker.py`（629 行，唯一新增文件；不改 `config.py`、不新增迁移/开关） |
| 外部套件 | `V/tests/runtime/test_m5_6.py`（13 项）＋受影响原回归 `tests/test_app.py` |

实现要点：`Worker.start/stop` 与 `async tick`；5 秒检查、20 秒心跳、每周期最多一个执行槽；
`--once` 只跑一个周期；`--health` 只读聚合；`python -m app.assistant_worker` 为独立进程入口。
心跳落在既有 `app_metadata` 表，键前缀 `assistant_runtime_worker:` + 32 位十六进制 worker 编号
（键长 58 ≤ 60），值只有 `at/source/instance/error` 四个字段；清理只删本前缀 7 天前的记录。
`verify_instance()` 只读校验：必须显式配置 `DATABASE_URL`、库可达、九张 Runtime 表齐全、
`alembic_version` 位于本代码迁移头且包含 `h53k_assistant_runtime`；不做迁移、不建库、不初始化。

## 2. 实测结论（真实运行）

运行 `20260928T061011Z-d295c8ac6c`：`status=passed`，`phase_complete=true`。

- `m56-worker-contract`：13 passed。
  1. import 不启进程：无新线程、无心跳行、`Worker().state == 'stopped'`；
  2. 键长/身份/指纹有界且不含 URL、库名、`sqlite`、`@` 等敏感片段；
  3. 启动校验四类拒绝：缺 `DATABASE_URL`、空库缺表、无迁移历史（夹具库）、只到 `h52j`；
     正常迁移库返回 `revision=h53k_assistant_runtime`；
  4. 心跳负载恰为四个字段并写入本前缀键；清理只删本前缀过期行，保留自己、保留存活同伴、
     不触碰 `daily_report_state` 等非前缀键；
  5. 心跳可见且不重复（upsert，同一 worker 恒一行）；
  6. health 能分辨"worker 过期"与"租约过期待恢复"，Runtime 关闭时报 `runtime_disabled`；
     健康/不健康两态与 `healthy` 布尔一致，输出不含数据库 URL；
  7. tick 顺序为 reclaim → claim，空队列不执行；领取后只执行一次且 `stream=False`；
  8. Runtime 关闭时不领取、不执行，但仍写基础设施心跳（不访问新表业务数据）；
  9. 队列异常只记录稳定错误码（`RuntimeError` 等类型名），不落异常文本；
  10. 执行中 `CancelledError` 直接上抛、不产生第二次领取、不写业务提交；
  11. `start/stop` 状态机 stopped→running→stopping→stopped，停止后不再领取；
  12. `start()` 幂等（两次连续 start 只产生一个 serve 任务）、未启动时 stop 安全；
  13. CLI：`--once` 返回 0 且只跑一次、`--health` 健康 0 / 不健康 1、启动拒绝 2。
- `m56-affected-app-regression`：`tests/test_app.py` 40+ 项通过（应用导入、登录、权限、
  既有业务规则未受影响）。

## 3. 本轮实测发现并修复的缺陷

**worker 双启动**：`start()` 原先只检查 `state`，而 `_serve` 要等事件循环调度后才把状态置为
`running`，于是两次连续 `start()` 会创建两个 serve 任务（两个心跳循环、两个领取循环）。
实测用例 `test_start_is_idempotent_and_stop_without_start_is_safe` 首次运行即失败
（run `20260928T055716Z-7486d42373`）。修复：`start()` 在调度前同步占用状态并检查
未完成的任务，保证一个 worker 身份只有一个循环。

同轮另修正一条测试自身的伪签名（fake queue 的 `claim_next` 少一个位置参数），
不属于产品缺陷。

## 4. 人工代码审查要点

- 不自动迁移/初始化数据库；缺配置、缺迁移、库不通一律启动失败（退出码 2）。
- 不复用日报 Scheduler；import 无副作用；不常驻于 import。
- 健康输出只有计数、时间、指纹与错误码；无用户、客户、会话内容、数据库 URL 或密钥。
- 停止只停止领取；已领取的执行在自己的安全边界收尾；进程被杀后由租约过期 + CAS 恢复。
- 心跳使用独立 Session，与执行会话分离；执行期间的租约续期仍由 runner 的 `_RunHeartbeat` 负责。

## 5. 尚未由运行证据覆盖

- 两个真实进程（嵌入 + 独立）同时运行时的槽位竞争；真实 Ctrl+C/SIGTERM 的退出时序。
- 真实 PostgreSQL 上的 `alembic_version` 校验与 `--health` 输出。
- Windows 预览嵌入路径（M5.7）与 Linux 部署定义（M5.8）的实际启动、关闭与恢复。
- 心跳清理在跨 7 天边界和时钟回拨下的行为。

源码指纹：`fce9783476ef263f4e55782afccc2e104f5ab0053db34d341621a7885492444b`。
