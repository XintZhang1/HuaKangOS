# M8.1 离线事实纠错、待办文案与执行器修复检查点 v5

2026-09-29；开发候选。M8.1 保持 `in_progress`。不部署、不默认开启四个功能开关、不调用真实模型。
本记录接续 `docs/implementation-checkpoints/M8-1-native-checkpoint-v4.md` 的下一执行点：
“按原业务族补齐维修、仓库与跨店授权的实际事实核对；继续核对所有事实适配器；清理既有等待原因文案”。

## 1. 为什么先做这一轮

v4 结尾列明三件事：维修／仓库／跨店授权的真实事实核对、继续核对所有事实适配器、把侧栏里
直接透出的 `employee_continue` 之类的等待原因改成中文。本轮先做这三件，并把挡住本地复验的
执行器缺口一并修好，因为不修执行器就无法在 Windows 上真正执行原页面回归。

## 2. 已复现的真实缺陷

四个都是“在真实原业务数据上永远无法成立或显示错误”的缺陷，不是风格问题：

| # | 位置 | 现象 | 原业务事实 |
|---|---|---|---|
| 1 | `warehouse_document.py` | `warehouse.count_posted` 查找用途 `count_adjust` | 原仓储盘差流水用途是 `PURPOSES['count']`，当前 `wh_count`；`operations_analytics`、`warehouse_period_analytics` 同样按 `wh_count` 筛选 |
| 2 | `dossier_grant.py` | 接收店的 `dossier.approval_recorded` / `dossier.revocation_recorded` 恒为未知 | 原 `_detail` 只在发起店下发 `decisions`；接收店只有 `status` / `effective_status` / `can_read` |
| 3 | `customer_care.py` | `care.closed` 比较状态 `closed` | 原关怀服务单 `close` 置 `completed`、`cancel` 置 `cancelled`，从未有 `closed` |
| 4 | `web/assistantworkspace.js` + 投影 | 侧栏显示 `等待：employee_continue` 等状态机标识 | 等待原因应显示为固定中文 |

修复范围与异常路径分别见 `PATCH-M8-1-WAREHOUSE-COUNT-01`、`PATCH-M8-1-DOSSIER-RECEIVER-01`、
`PATCH-M8-1-CARE-CLOSED-01`、`PATCH-M8-1-WAIT-TEXT-01`。四者都不改原业务状态机、资金库存事实、
人工确认接口或功能开关默认值。

同时修复挡路的执行器缺陷（`PATCH-M8-1-OFFLINE-HARNESS-01`）：
`run_browser.py` 只捕获 `httpx.ConnectError`，而本机回环探测抛 `ConnectTimeout`（不是其子类），
浏览器套件在启动夹具服务器前即失败；`browser_harness.py` 用 `Path.read_text()` 读取 `web/**` 资产，
落到本机 GBK 编码后抛 `UnicodeDecodeError`；`run_validation.py` 读日志同样未指定编码，且
Node 24 的测试汇总标记由 `#` 变为 `ℹ`，使计数守卫拒绝一次全绿运行。修正后本机可按
`native` / `fixture` 分别执行原页面套件。以上都不改断言、CSP、浏览器策略或传输语义。

## 3. 本批实际改动文件

生产：`app/assistant_runtime_labels.py`（新增）、`app/assistant_runtime_schemas.py`、
`app/assistant_runtime_workspace.py`、`app/assistant_runtime_plans.py`、`app/assistant_runtime_api.py`、
`app/assistant_runtime_domains/warehouse_document.py`、`app/assistant_runtime_domains/dossier_grant.py`、
`app/assistant_runtime_domains/customer_care.py`、`web/assistantworkspace.js`。

测试与执行器：`tests/assistant_offline/tests/test_repair_warehouse_grant_facts.py`（新增）、
`tests/assistant_offline/tests/assistant_plan_ui.test.cjs`、
`tests/assistant_offline/tests/test_validation_selection.py`、`tests/assistant_offline/browser_harness.py`、
`tests/assistant_offline/run_browser.py`、`tests/assistant_offline/run_isolated.py`、
`tests/assistant_offline/run_validation.py`。

## 4. 实际执行的完整回归

命令（唯一入口；测试源码先复制到仓库外全新目录）：

```powershell
python tests/assistant_offline/run_isolated.py --source <repo> --output <external-new-dir> --browser-mode fixture
```

| 层次 | 用例数 | 结果 |
|---|---:|---|
| 后端领域与集成（13 个套件） | 190 | 全部通过 |
| 前端模块行为（Node） | 55 | 全部通过 |
| Chromium 原页面控件 | 14 | 全部通过 |
| 合计 | **259** | 19 条命令退出码全部为 0 |

`run-summary.json`：`complete=true`、`selected_complete=true`、`scope=full`、
`browser_transport=fixture`、`real_model_calls=0`、`release_accepted=false`。
生产源码指纹 `b43b0fe69bd55ecee0eae31395656d55454f9a6ea967ff75e39dd5f647dc8c7c`；
测试套件指纹 `1bec0ba7ccc4d99ee634d3eac1b6e77041d7cf0ab456738c6c0f13fcf8229db3`。
证据目录 `E:\HuaKangOS-validation-m81-final\evidence`（仓库外，含逐步骤日志、逐页面截图与请求记录）。

本批新增套件 `test_repair_warehouse_grant_facts.py` 共 39 项：等待文案映射与 DTO 契约、
仓储盘差过账判定、跨店授权决定动作与接收店等价事实、维修交车键、关怀结案键，以及三项
**真实 `/api/dossier-grants` HTTP 用例**（待复核未批准、批准后发起店与接收店分别得到等价事实、
撤销后接收店 `/record` 被原接口 403 拒绝且有效状态为 `revoked`）。

### 保留的失败与不重复计数

- 完整序列首跑时 `test_07_malformed_model_output_never_creates_card` 因
  `Locator.click` 8 秒超时失败（在全部后端套件之后启动第 7 个 Chromium 实例）。同指纹下单独
  复跑浏览器套件 14/14 通过，第二次完整序列也 14/14 通过，故记为资源竞争下的点击时序抖动，
  **不删除该用例、不放宽超时断言、不改浏览器策略**，并在本记录保留该次失败。
- 本记录不与 v4 的 211 项、也不与本地早前复跑累加为不同用例。

## 5. 本轮明确未覆盖的边界

- 仍为 `fixture` 传输：本机 Chromium 网络策略此前拒绝原生 HTTP 导航，本轮未修改系统或浏览器
  安全策略，因此**没有**宣称原生 Cookie/CSP/SSE 验收。原生结果按 v4 的 CI 记录单独保留。
- 真实模型调用为 0；模型响应仍是确定性合成内容。
- 未执行 PostgreSQL、独立 Windows/Linux 恢复演练、指定 MCP 客户端与真实员工试用。
- 本批只覆盖维修交车键、仓储盘点过账键、关怀结案键与跨店授权三项事实；其余领域适配器的**静态**
  对照本轮完成（逐项比对适配器内联字面量与原业务服务的状态/用途常量，另见第 2 节表），
  但未逐个建立真实 HTTP 闭环用例。
- 193 项需求整体业务验收、原 101/283 模型场景、111 条发布工作流检查仍按下述 CP 表分别待验。

## 6. 下一执行点

继续 M8.1：按剩余业务族补齐真实 HTTP 事实闭环（优先仍未有任何真实接口用例的适配器），
并保留会话级撤权、旧租约晚写、确认前原业务写入计数、批量部分失败与延迟注入等原清单项。
M8.2 及以后不在本轮授权范围内。
