# M8.1 剩余清单检查点 v1（旧租约、零写入、延迟注入、撤权信号）

2026-09-30；开发候选。**M8.1 保持 `in_progress`**：本轮把 `M8-1-partial-review-v1.md` 列出的剩余项
逐条落地并实测。不部署、不默认开启四个功能开关、不调用真实模型。

## 1. 本轮完成与既有覆盖的对照

| 清单项 | 本轮处置 | 证据 |
|---|---|---|
| ③ 旧租约不得覆盖新状态的 **DB 跃迁演练** | **本轮完成** | `test_lease_transition_db.py`（5 项） |
| ② 确认前原业务写入计数 = 0 | **本轮完成（强证明）** | `test_prepare_zero_write.py`（2 项） |
| ③ 批量部分失败即暂停 | **已由既有套件覆盖，不重复造** | `test_batch_confirmation.py`（7 项，见 §3） |
| ⑤ 延迟注入 | **本轮完成** | `test_delay_injection.py`（2 项） |
| ③ access_signals 两条事件路径端到端发射 | **本轮完成**（真实路由路径） | `test_access_signals_emit.py`（4 项） |
| ③ 撤权后既有会话不得继续 | 上一轮已完成 | `test_revocation_session.py`（5 项） |

生产代码：**无改动**。本轮只新增测试。

## 2. 旧租约不得覆盖新状态（DB 跃迁）

`_append_queue_transition` 通过**独立读取会话**证明已提交前态，因此用例必须真实安排时序：先提交旧状态，
再在另一事务提交新状态，最后才让过期写方调用该守卫。用例 5 项：

1. **过期租约不得推进后一租约已提交的状态**：已提交为 `running`，过期写方仍以为 `queued` 并要落
   `succeeded` → `409`；数据库仍是 `running`、版本未变，**且没有追加生命周期事件**；
2. **版本未前进即拒绝**（`run.version <= old['version']`）；
3. **重复目标态不产生第二个事件**（心跳/停止请求不得落事件）；
4. **身份漂移被拒**（owner/store/session 与已提交记录不一致 → 409，参数化三种字段）；
5. **同一不变量经真实队列动词验证**：`claim_next` 旧租约 → 过期 `reclaim_expired` → 新租约 `claim_next`
   且 `fence` 前进 → 旧租约 `release` 被 `409` 拒绝，最终行仍是新租约的 `running`。

`Run` 行由**真实登录会话**派生：`ck_assistant_run_login_ref` 要求 `login_session_ref` 与真实登录会话哈希
对应（恰好 64 字符），所以用例从原登录写入的 `login_sessions.id` 取值，不拼字符串。

> **与 V 根 `staging/test_m8_1_lease_cas.py` 的关系（如实登记）**：该文件是早期尝试，未登记进 manifest，
> 且其夹具把 `login_session_ref` 内联成 32 字符、建 `Run` 时也未设门店 scope，按真实约束会失败。
> 本轮的仓库套件是它的**取代实现**：同一不变量、真实登录会话派生、5 项（含真实队列动词），且随
> `run_isolated.py` 与 CI 一起执行。

## 3. 批量部分失败即暂停：既有覆盖（本轮核对，未新造）

`tests/assistant_offline/tests/test_batch_confirmation.py` 已覆盖：第二张摘要错误 → 结果恰为
`succeeded/refused/skipped`、第一张已提交不被回滚、第三张保持 `pending` 且需员工**再次点击**；第二张
不存在 → 同样暂停且不吞行；第二张响应丢失（提交后）→ 记为 `uncertain` 并暂停、重复批量**不重放**、
调用次数不增加；取消动作同样在首个拒绝处停止；重复选择与跨步骤批量在**任何原业务写入前**返回 422。
本轮逐条核对后**不再新增重复用例**，避免用重复计数充数。

## 4. 确认前原业务写入 = 0（强证明）

既有用例只对 4 个模型计数。本轮改为对**整个隔离合成库的每一张原业务表**做行数＋内容摘要比对：

- 表清单从真实 sqlite schema 读取，排除助手自有表；
- 每张表按**主键以外的全部列**计算顺序无关摘要（`sha256`，逐行拼接），因此新增、删除或改写任一列
  都会被检出，而不只是行数变化；
- 助手自有状态按**行键**而非表名排除：worker 心跳写在共享的 `app_metadata` 表里
  （键 `assistant_runtime_worker:<实例>`），它不是业务写入——这一点是本轮实测发现的，先前按表名判断
  会把心跳误判为业务写入；
- 二进制列（附件 blob）按字节处理，不按文本解码。

两项断言：① 准备全过程（含真实 worker tick 与原 API 读取）后，**全部原业务表摘要不变**，同时断言确实
存在卡片（否则空 delta 无意义）、且确认项仍为 0；② 提交**错误摘要**被 `409` 拒绝后整库仍不变，只有
员工用**正确摘要**点击那一次才使原业务表发生变化，且重复点击不再新增。

## 5. 延迟注入

在真实确认卡上注入真实延时（模型应答前 `time.sleep`）：

1. 准备轮延时 1.5s 仍恰好完成：模型请求数等于步骤数（**延时没有变成额外模型轮或重放**）、准备后原业务
   仍为 0、员工点击后才新增 1 行、**重复点击不再新增**；
2. 终态 Run 不被再次执行：连续两次 worker tick 期间**模型请求数为 0**、不新增 Run 行、终态的
   `status/attempt/fence` 完全不变。

> **本轮放弃的一种写法（如实保留）**：我最初想用「把 `run.started_at` 挪到过去」制造 `time_budget`
> 终态，但 `started_at` 由真实流程在开轮时写入，人为清空并不能复现该终态，属**猜错机制**；该写法已删除，
> 未据此登记任何通过项。

## 6. access_signals 两条事件路径

真实管理员编辑（`PUT /api/users/{id}`）→ 写入不可变 `UserAccessReceipt` 与配套审计 → **同一事务内**
消费该 receipt → 写事务性唤醒发件箱。用例 4 项：

1. 真实编辑确实产生信号：`topic='access.changed'`、`source_ref` 指向该 receipt、
   `signal_key` 以 `user_access_receipt:<id>` 开头；账号 `access_version` 恰为 +1；第二次不同编辑
   **不复用**前一个 receipt 的键；
2. **已提交的 receipt 不能在事后重新发射**（`409`）——这是真实契约 `state.pending`，即信号只能来自创建
   其来源的那个事务；同时断言该拒绝**既不删除也不重复**已产生的真实信号；
3. 账号状态漂移（再改一次版本）后消费旧 receipt → `409`；
4. 审计链完整：receipt 指向真实 `AuditLog`（`action='update_user'`、`entity_id` 为员工、前后像的
   `access_version` 与 `role` 与 receipt 一致）。

## 7. 本轮顺带修好的两个装置缺陷（如实保留）

1. **步骤挂起保护会在慢机上误报失败**：`run_validation.py` 的 `run()` 固定 `timeout=420`，而页面套件在
   负载下会超过它，报出的却只是「timeout」，与页面无关。现改为按步骤类型给默认值（浏览器 900、其余
   420），并可用 `HUAKANGOS_BROWSER_GUARD_SECONDS` / `HUAKANGOS_STEP_GUARD_SECONDS` 覆盖；
   `run_browser.py` 的内层保护同样可通过 `HUAKANGOS_BROWSER_GUARD_SECONDS` 调整。
2. **超时留下的孤儿夹具服务会毒化后续运行**：`subprocess.run` 只终止直接子进程，被超时放弃的
   `browser_server.py` 继续占用 8765 端口，之后每次运行都会按设计拒绝启动（`Port 8765 is already in
   use`）。现于超时分支按平台（Windows `taskkill /T`、POSIX `kill -9`）终止该步骤**自身**的进程树，只按
   命令尾部匹配，不误杀其它进程。

## 8. 本批实测（完整回归）

命令（唯一入口，测试源码复制到仓库外全新目录）：

```powershell
python tests/assistant_offline/run_browser_pipeline.py --source E:\HuaKangOS --browser-mode fixture
```

| 层次 | 用例数 | 结果 |
|---|---:|---|
| 后端领域与集成（20 个已版本化套件） | 224 | 全部通过 |
| 前端模块行为（Node） | 55 | 全部通过 |
| Chromium 页面操作（`fixture` 传输，**不构成原生验收**） | 14 | 全部通过 |
| 合计 | **293** | 全部命令退出码 0 |

其中本批涉及的 5 个套件共 **18 项**：`test_lease_transition_db` 5、`test_prepare_zero_write` 2、
`test_delay_injection` 2、`test_access_signals_emit` 4、`test_revocation_session` 5（上一轮新增）。

`run-summary.json`：`complete=true`、`scope=full`、`browser_transport=fixture`、`real_model_calls=0`、
`release_accepted=false`。生产源码指纹
`a7c0cd8fe38d8eb5101ffcf92fba07e1780f59b29e6bf368acf522fbf38ae8e4`（与上一轮一致：本轮未改生产代码）；
测试套件指纹 `4849cd5ba84ac8cb03a78dbe67718867aedc36511f9974be263ced980e760660`。证据目录（仓库外）
`C:\Users\tiefu\.codex\HuaKangOS-agent-validation\runtime-v1\browser\browser-fixture-20260930T012840Z\evidence`。

## 9. 本轮实测暴露并修好的第三个装置缺陷（我自己引入的）

我上一轮为避免与登录渲染竞争而引入的 `expect_response` 等待**只在 native 模式成立**：`fixture` 模式用显式
桥接替换了 `window.fetch`，浏览器因此**不会**产生网络响应事件，该等待每次都 30s 超时，把 14 个页面全部
报成 `Timeout 30000ms exceeded while waiting for event "response"`——一个与页面无关的失败。现改为读取
**装置自己的请求账本**（两种模式都记录真实发出的 `POST /api/auth/login` 及其状态），不再依赖浏览器网络
事件；`fixture` 与 `native` 两模式因此共用同一条判定路径。

同一轮核对保留的附带事实：`run_validation.py` 原文用 `except (OSError, TimeoutExpired)` 合并处理，无法
区分「超时」与「无法启动」；上面的进程树终止只挂在超时分支上。

## 10. 仍未完成 / 明确不声称


- 本轮**不**把 M8.1 记为 `done`：原完成检查中「每个稳定 WorkItem 至多一个有效准备版本、批量无遗漏」的
  完整批量行核对仍以既有套件与外部套件为准，「故障重复执行稳定同一结果」的跨套件重复运行亦未在本轮
  重做；M8.1 的整体判定仍待集中测试阶段收口。
- 未执行 M8.3（独立 PostgreSQL、h52j 合成旧库升级、联合备份恢复）与 M8.4 的遗留项。
- 真实模型调用 0；四个功能开关默认关闭；未部署、未接真实客户数据。
- 本记录不把 `fixture` 传输的页面结果写成原生浏览器验收。