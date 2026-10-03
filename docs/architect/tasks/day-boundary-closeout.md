# 自然日界两项独立原业务条件

当前目标：给主任务提供 M8.1 中 HK099 的实际 Shanghai Date 截止和 HK152 的完整历史期初/期间条件候选。M8.1 仍唯一 in_progress；本任务不推进其他里程碑、不维护共享索引、不写生产或正式 runner。

2026-10-03 接续检查未发现原 queue_faults 已落盘的 day_boundary 候选，保留所有现有修改后新增 `tests/browser_click/day_boundary_business.py`。复用了原客户提醒/仓储/报表 helper，候选没有新框架、app 导入、SQL 业务写入或伪造时钟。

阶段行为已静态完成：D 原 UI 新 active grant、明确原零库存库位启用、非零原入库；封存同实例原件/指纹。D+1 原登录和原 GET/列表核授权整行保留及摘要自然排除；原报表从真实旧流水重建 5.000/20.00 的历史期初，三次原收发及引用原领用退回得到期末 5.625/22.50；API、明细、CSV、期末图和原单同范围。开始日为 D 的历史缺口继续保留。

发现并报告主任务的最小生产接线缺口：仓储原 reason `wh_consume_return/wh_other_return` 未出现在期间 label 表。主任务已登记另一个精确补丁并追加 labels，本候选保留严格真实名称断言。

下一步由主任务审阅导出并在正式入口接线：只镜像脚本不把两个 phase 一起放入同日 full 注册；利用同一外部 manifest 原启动/关闭与浏览器生命周期，stage 后正常停服务保留库，D+1 原 mirror 重启且不 initialize。原 full 汇总和 stage 原件保留独立引用。正式全量开始后当前候选及本记录也须停止修改。

静态检查：Python AST 解析通过；5 个直接 `db.rows` 调用均为固定 SELECT；未导入 app、SQL 客户端、进程或 HTTP 库；三张原表全部 literal 字段与当前生产源码匹配。模块 SHA256 为 `5b4de7d5fd03b6a4facfa6a48e72c4e03b9ebd11872d263ca6972657d8ea9643`。

原 `fixture_server` 退出会覆盖原根 `provider.json`，worker controller 也有固定证据 sink；正式 resume 必须给 phase 独立接线并保留原 full 文件，不以改 evidence 根/数据库根绕开实例绑定。已有 `runtime/stop-requested` 由主任务按明确外部 marker 所有权归档后重启，不能重建数据库来避开停机标记。

状态为 candidate/static reviewed，运行及跨日成绩均未执行。原 HK099 文件授权、HK152 其他业务范围、193 项验收和员工试用没有由本候选代替。

## 窄阶段入口接线候选

2026-10-03 主任务批准新增未注册的 `day_boundary_entry.py`，已有 59 个镜像脚本及生产源码仍冻结。该入口不改 `run.py`、`fixture_server.py` 或既有 day 模块；主任务在短回归结束后独立审阅，并只把新入口纳入镜像白名单，普通 80 场注册不包含自然等待。

入口必须从已完成、通过、`full_registered` 且正常退出的原外部实例 scripts 目录运行，示例为该固定目录中的 `day_boundary_entry.py --manifest <原 manifest.json> --phase stage`，实际上海 D+1 同路径运行 `--phase verify`。它拒绝 phase 目录已有原件、未登记脚本、任何 source/scripts 清单变化、缺失/失败 full、真实模型配置或其他监听服务占用原端口，不自动覆盖或重试。

服务子入口仅复用 `fixture_server.read_instance/configure_environment(initialize=False)` 的原配置与原 app/uvicorn/lifespan，不调用共享 `main`、不初始化或迁移。源码核实：`app/main.py` 的 `_embedded_runtime_worker` 在 `HUAKANGOS_LOCAL_PREVIEW != 1` 时直接返回，`app/scheduler.py` 的 `ReportScheduler.start` 在 `scheduler_enabled=false/mode=off` 时直接返回。入口在原 lifespan 前、启动后及退出后分别核实 `_EMBEDDED_WORKER is None` 和 `scheduler.thread is None`，阶段前后 SELECT 读取旧 worker marker 及全部 Run 整行指纹必须完全相同。此纯原业务日期/流水阶段明确不计 Runtime worker 部署验收。

阶段控制只用 `runtime/day-boundary-entry/<phase>/stop-requested`，与旧 runtime 根 stop marker 分离，不移动或删旧文件；复用原 `run.stop_server(server, phase_control)` 正常退出算法。服务日志、provider 计数、生命周期和汇总写 `evidence/day-boundary-entry-<phase>`；原浏览器场景写既有 day 函数规定的独立场景目录，不调用整个 `scenarios.run`，因此不会覆盖原 full `browser-click-report.json`、`provider.json`、worker/controller 证据或汇总。

启动前封存所有已存在 evidence 文件和 runtime 配置/控制文件的 SHA256；退出后每个旧文件必须保留原指纹，新增文件仅在明确 phase 目录（数据库及其 SQLite 事务辅助文件允许原 UI 正常变化）。原 manifest/source/scripts 指纹再次核对，模型 provider 必须 0 real、0 synthetic、0 blocked external；原生页面异常/外网尝试/5xx、服务非零或强制退出均为失败。Windows venv 子服务沿用原 queue CLI 的 base interpreter/`__PYVENV_LAUNCHER__` 方式，启动证明绑定实际 owned PID 和本次随机 nonce，不能误接既有服务。

stage 退出码 0 仅表示准备阶段按原 UI 完成，独立汇总仍 `complete=false/passed=false/natural_boundary_verified=false`；只有实际 D+1 两个合同及完整清理检查都通过后 verify 才记本技术范围通过。当前入口只完成 AST/SELECT/禁止初始化调用的静态检查，未启动服务或浏览器。入口 SHA256 为 `67d5e8da1a9c84ca17adb3ae1512c1ea5390c5b18b142fb80aa822af991933fd`，既有 day 业务模块仍为 `5b4de7d5fd03b6a4facfa6a48e72c4e03b9ebd11872d263ca6972657d8ea9643`。
