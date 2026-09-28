# M5.7 编码审阅与实测记录（Windows 预览嵌入同实例 worker）

2026-09-28，集中测试阶段。Astra 批次未开始 M5.7；本轮实现 + 外部实测。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 产品实现 | `app/main.py`：新增 `_embedded_runtime_worker()` / `_stop_embedded_runtime_worker()`，`lifespan` 在 `scheduler.start()` 之后按条件嵌入，在关闭时先停 worker 再停 scheduler；模块级 `_EMBEDDED_WORKER` 保证一个进程只有一个嵌入 worker |
| 外部套件 | `V/tests/runtime/test_m5_7.py`（7 项）＋受影响原回归 `tests/test_local_preview.py`（16 项） |
| 未改动 | `app/local_preview.py`、`app/preview_runtime.py`、`scripts/preview_launcher.ps1`、`start-preview.ps1`（原实例守卫与源码身份校验已满足本项合同，无需改动） |

实现顺序固定为：`HUAKANGOS_LOCAL_PREVIEW=1`（由 `local_preview.configure` 在本进程内设置）
→ `settings.assistant_runtime_enabled` → `HUAKANGOS_PREVIEW_ROOT` 存在 → `marker_from_disk(root)`
验证磁盘标记 → **之后才** import `app.assistant_worker` → `verify_instance()` 只读校验 →
`Worker(lease_owner='preview-embed').start()`（同一事件循环、同一 `SessionLocal`、同一库）。
关闭：`await worker.stop(timeout=20)`，只停止领取，已在执行的 Run 在自己的安全边界收尾。

## 2. 实测结论（真实运行）

运行 `20260928T062457Z-eb0d2c567c`：`status=passed`，`phase_complete=true`。

- `m57-preview-embedding`：7 passed。
  1. 普通 Web 部署（无 `HUAKANGOS_LOCAL_PREVIEW`）不嵌入：`_embedded_runtime_worker()` 返回 None，
     经真实 `TestClient(app)` 生命周期后仍为 None；
  2. 预览但 Runtime 开关关闭：不读标记、不校验实例、不启动（三项计数均为 0）；
  3. **标记先于 worker 导入**：标记校验抛错时 `verify_instance` 完全未被调用（用会失败的替身证明）；
  4. 预览环境缺少 `HUAKANGOS_PREVIEW_ROOT` 明确拒绝（RuntimeError）；
  5. 真实 lifespan：进入时启动一个 worker（`start` 一次、`lease_owner='preview-embed'`），
     重复调用返回同一对象，退出时 `stop` 一次且模块级引用清空；
  6. 预览目录只允许 `LOCALAPPDATA/huakangos` 之下：仓库路径与临时目录都被拒绝；
  7. Web 与 worker 的库标识/源码指纹一致：心跳行的 `instance`/`source` 与进程内
     `instance_identity()`/`source_fingerprint()` 完全相同，`health_report` 判定 healthy。
- `m57-affected-preview-regression`：`tests/test_local_preview.py` 16 passed（原预览目录校验、
  标记与实例匹配、拒绝接管未标记库等契约未变）。

## 3. 执行器边界（本轮查证，非产品缺陷）

`tests/test_preview_runtime.py` 的两个子进程节点带 `preview_prepare` 夹具授权，
而 `harness/fixture_profiles.py:38` 与 `:60` 明确要求命令属于 **M0.2 phase B**
（`contract['phase'] != 'B'` 即拒绝、`metadata['milestone'] != 'M0.2'` 直接 `GuardError`）。
因此这两个节点只能在 M0.2.B 登记下运行；本项不再重复选取它们（首次尝试时因缺少该授权，
子进程被隔离守卫以 `synthetic_database_marker_missing` 拒绝——属执行器合同，不属产品缺陷）。
M0.2.B 完整基线仍是这两个节点的唯一登记处。

## 4. 人工代码审查要点

- 只有"已配置 + 已开关 + 已标记 + 实例已就绪"四条同时成立才嵌入；普通 Web 部署路径完全不变。
- worker 不迁移、不初始化、不建库；`verify_instance()` 只读，缺迁移即拒绝。
- 一个进程最多一个嵌入 worker（模块级单例 + `Worker.start()` 幂等）。
- 关闭顺序：worker 停止领取 → scheduler 停止；不新开可见窗口、不改日报开关、不重置预览账号或数据。
- 预览实例的开关仍由运维显式打开（四个功能开关默认关闭），启动器不代填。

## 5. 尚未由运行证据覆盖

- 真实 Windows 预览实例的启动/退出/再启动（本轮全部在合成夹具上用替身跑生命周期）。
- 关闭电脑期间的行为、预览进程被强杀后的租约恢复。
- 预览实例上真实开启 Runtime 后的端到端执行（需 live gate 与合成数据，属 M8）。

源码指纹：`94da7d7cc30bfd49d978714035bce690a7b93808e34f0a569508cc06254b8c01`。
