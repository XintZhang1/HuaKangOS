# PATCH-M5-5-02：MCP 工具入口的实测修复与范围登记

2026-09-28，集中测试阶段。M5.5 编码完成后先做独立源码审计，再在外部验证根建立
`tests/runtime/test_m5_5.py` 实测；本补丁记录实测发现的缺陷、修复与两条需要登记的边界。

## 1. 审计发现与处置

| 编号 | 发现 | 处置 |
|---|---|---|
| D1 | `assistant_runtime_mcp.py` 的 `_frame` 用 `_same_intent(work.validated_intent, work.validated_intent)` 自比，等于只做自洽检查，不能证明 WorkItem 的意图与卡片内容一致 | 已修复（下表 §2.1） |
| D2 | 卡容量拒绝被记成终态错误行，投影文案只说"核对资料或原业务条件" | 部分处置：保持与 legacy 一致的终态语义（legacy 同样以 409 拒绝整个请求），但投影文案明确写出容量这一真实原因（§2.4） |
| D3 | claim 之后、`try` 之前的失败（读相位/复核/帧/spec/心跳构造）不会释放租约，Run 会停在 running 直到 90 秒租约过期 | 已修复（§2.2） |
| D4 | MCP 保存 v2 计划会走 `_stop_old_runs`，把**同一员工同一计划**的既有 Grant 置为 paused | 不修改：`plans.py:629-637` 只作用于 `grant.plan_id == plan.id`，即员工本人这次被改写的计划；"目标变化即停旧授权"是原设计语义。已在 M5-5 审阅文档登记 |
| D5 | 重放时 `{**result,'notice':…}` 整体替换工具自身的批量 notice | 已修复（§2.3） |
| D6 | 批量计数把"已复用但员工已确认"的卡算进 rejected，`prepared_or_reused + rejected != requested` | 已修复（§2.4） |
| C1 | 合同"不得创建 Grant"未覆盖"改计划会暂停既有 Grant" | 以本条登记语义，不改合同文字 |
| C2 | 合同"同请求号不同完整参数 409"实际按服务端规范化后的有效参数比较 | 实现合理（有效参数相同即同一请求）；已在审阅文档写明复验口径 |
| C3 | 批量 `status` 返回卡片真实状态，legacy 固定 `'pending'` | 实现更真实，保留；差异记入复验清单 |
| C4 | M5.5 允许范围未列 `business_assistant_service.py`，但 `legacy_session_busy` 保护在该文件 | 本补丁登记该文件的授权范围（§3） |

未采纳的写法：不把 D2 改成"可续办行"（会改变 legacy 已发布的返回形状与失败语义），
也不删除任何断言。

## 2. 精确改动（`app/assistant_runtime_mcp.py`）

1. **意图与卡片内容绑定**：删除自比调用，新增 `_intent_matches_card(card, work)`，
   证明 `work.validated_intent` 自洽（键集合完整且 `intent_digest` 可重算）**并且**
   与卡片的 `payload`（只允许缺服务端生成的 `request_id`）及 `questions` 归一化结果一致，
   与 `operation_id` 一致。判据与 `build_proposal` 复用时使用的判据相同，不会拒绝真实来源。
2. **领取即受 fence 保护**：`_config`、读相位、`revalidate_principal`、`_load`、状态检查、
   `registry_for_config(...).spec(...)`、`_RunHeartbeat` 构造全部移入 `try`；
   `except` 与 `finally` 对 `heartbeat is None` 做保护。任何失败都走原有 release 分支，
   不再把 Run 留到租约过期。
3. **notice 不覆盖**：重放的"未全部完成"提示与工具自身 notice 以空格拼接保留两者。
4. **投影与计数**：错误行文案写明"若提示待确认卡已达上限，请先处理原卡后用同一请求号继续"；
   批量计数改为 `prepared_or_reused = 有真实卡片的行数`、`rejected = 无卡片的行数`，
   两者恒等于 `requested`，且不再把员工已确认的复用卡当成拒绝。

## 3. legacy 工具循环的回归修复（`app/business_assistant_service.py`）

外部回归 `tests/test_business_assistant_case_tools.py::test_case_tool_rejects_model_supplied_version_or_raw_url`
在候选源码上失败（run `20260928T060601Z-04316ad3a7`：19 passed / 1 failed，IndexError）。
原因：M3.1 引入的 `registry.validate_calls(calls)` 抛出的 422 直接冒泡到 `except HTTPException`，
整轮变成错误答复，模型拿不到任何 tool 结果，也就无法按原契约纠正。

修复：整表预校验保留（**任何调用都不执行**，不产生部分准备），但被拒绝的整表按每个原始
`tool_call_id` 追加一条 `{'status': 422, 'error': …}` 工具消息并继续下一轮，
同时保留原有 `record_issue(..., 'model', …)` 记录。新增的拒绝分支不改变真实工具调用的任何路径。

## 4. 范围登记

- `app/business_assistant_service.py`：M5.5 的 legacy 忙租约保护（`legacy_session_busy`）
  与本补丁 §3 的拒绝回合修复都在该文件。原 M5.5/Astra 实施未在计划中登记该文件，
  本补丁补齐授权说明；改动仅限工具循环的拒绝分支，未改业务规则、状态机或提交语义。
- 未新增迁移、未新增功能开关、未触碰公司库/原预览库、未调用真实模型。

## 5. 复验证据（同一源码指纹）

| 运行 | 内容 | 结果 |
|---|---|---|
| `20260928T060445Z-fb23b94eea` | M5.5 首次实测（含大小写/超长参数用例） | failed：1（用例断言写错，已改） |
| `20260928T060601Z-04316ad3a7` | M5.5 套件通过；受影响回归 1 项失败（§3） | failed |
| `20260928T060804Z-7aa5208e93` | §2/§3 修复后 | **passed**：7 + 20 |

指纹 `fce9783476ef263f4e55782afccc2e104f5ab0053db34d341621a7885492444b`；
`M1.4`、`M5.6` 在同一指纹上另有通过记录。
