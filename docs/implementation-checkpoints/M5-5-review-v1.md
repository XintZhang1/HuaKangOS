# M5.5 编码审阅与实测记录（MCP 草稿工具兼容及共享互斥）

2026-09-28，集中测试阶段。本报告记录 M5.5 的源码审阅、外部实测套件、发现与修复，
以及仍未由运行证据覆盖的边界。原编码由 Astra 批次提交（`a40f7f4`），本报告不覆盖其历史。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 产品实现 | `app/assistant_runtime_mcp.py`（无模型工具执行入口）、`app/assistant_runtime_queue.py`（`enqueue_mcp_run`/`claim_mcp_run`/`safe_retry`/定向领取）、`app/assistant_runtime_runner.py`（`run_once` 分流）、`app/business_assistant_api.py`（`/tools`、`/sessions/{id}/tools/call`）、`app/business_assistant_workboard.py`（解析/flush 拆分）、`app/assistant_runtime_plans.py`（受限 v2 计划保存）、`app/assistant_runtime_registry.py` |
| 合同补丁 | `docs/implementation-patches/PATCH-M5-5-01.md`（原编码合同）、`PATCH-M5-5-02.md`（本轮实测修复与范围登记） |
| 外部套件 | `V/tests/runtime/test_m5_5.py`（7 项），另加受影响原回归 20 项 |

## 2. 实测结论（真实运行，非静态）

运行 `20260928T060804Z-7aa5208e93`：`status=passed`，`phase_complete=true`。

- `m55-mcp-compatibility`：7 passed。
  1. 工具目录保持 `business_v1` 旧结构，18 个工具，无 confirm/approve/submit/followup/grant/execute 类工具；
  2. 未知工具 422、超长参数（> `MODEL_ARGUMENT_CHARS`）413，且不产生任何 Run/RunItem；
  3. 只读工具经真实 HTTP 端点执行：1 个 Run（`trigger_kind=manual`、`auth_kind=login`、无 plan/grant）、
     1 个 tool 型 RunItem、**无 model/confirmation 型 RunItem**、无卡片；同请求号重放返回 200 且不新增行；
  4. 同请求号不同参数（`case_page` 1→2）409，换工具名同样 409，Run 数不变；
  5. 关闭 Runtime 后同请求号返回 503 且带 `accepted=true` 与原 `run_id`，行数不变；
     新请求号不受该保护影响（走原 legacy 路径）；
  6. 全部工具调用后仍无任何卡片、无 confirmation 行（"只准备不执行"）；
  7. `_intent_matches_card` 绑定判据：正确内容为真；篡改卡片 payload、篡改 questions、
     篡改 intent 摘要、篡改 operation_id 全部为假（覆盖 PATCH-M5-5-02 §2.1 的修复）。
- `m55-affected-tool-regression`：20 passed（`test_business_assistant_case_tools.py`、
  `test_business_assistant_capabilities.py`），含因本轮修复而恢复的
  `test_case_tool_rejects_model_supplied_version_or_raw_url`。

模型调用次数：0（测试用替身会在任何模型调用点抛错；工具型 RunItem 集合本身也不含 model 项）。

## 3. 人工代码审查要点

- **无模型、无 Grant、无确认**：MCP 分流发生在 `run_once` 构造上下文/provider 之前；
  registry 的 read/prepare/plan 分类中不含确认或授权工具；`_frame` 不接受 confirmation 型 RunItem。
- **身份与租约**：请求身份与每次 lease/fence 分离；`_released`/`_leased` 校验 fence 与 lease_owner，
  旧请求无法晚写或释放新租约；释放只清自己持有的 busy token。
- **定向领取**：`claim_mcp_run` 只在该请求同时是全局最高优先候选时领取，否则返回 None，
  不跳过更高优先级的用户请求，也不领取邻项。
- **事务边界**：卡/计划/issue 与各自完成检查点位于同一 fence 事务；完整批量输入先落库，
  恢复只处理未完成行；重放不重建已有、终态或结果不明卡。
- **legacy 只读保护**：Runtime 关闭时先核真实登录与当前会话，存在同 owner/store/session/请求键的
  旧 Run 即 503+accepted+原 run_id；检测/查询失败按 503 处理，不会被当作"无记录"而重放。

## 4. 修复项（详见 PATCH-M5-5-02）

1. `_frame` 的意图校验由自比改为"意图自洽 + 与卡片 payload/questions/operation 绑定"；
2. claim 之后的全部前置步骤移入 fence 保护范围，失败即释放，不再泄漏租约；
3. 重放提示不再覆盖工具自身的批量 notice；
4. 批量计数自洽；错误行文案写明容量原因；
5. legacy 工具循环：整表预校验被拒时按每个 tool_call_id 回一条 422 工具结果并继续下一轮
   （仍不执行任何调用），恢复被 M3.1 预校验打断的原契约。

## 5. 已登记但未改动的边界

- v2 计划保存会暂停**同员工同计划**的既有 Grant（`plans.py:629-637`）；这是"目标已变化即停旧授权"
  的原语义，非跨员工影响。若业主希望 MCP 路径禁止暂停授权，需另立合同与补丁。
- 卡容量拒绝保持 legacy 的终态失败语义（legacy 同样以 409 拒绝整请求），不做"可续办行"改造。
- 合同"同请求号不同完整参数"按服务端规范化后的有效参数比较（省略默认值与显式默认值视为同一请求）。

## 6. 尚未由运行证据覆盖（待集中测试继续）

- 两个 HTTP 调用者真正并发（同/异请求号）时的唯一卡与领取竞态；PG 与 SQLite 的行锁差异。
- 跨进程：worker 与 HTTP 同时竞争同一 MCP Run；超时后 30/120/600 秒退避窗口内的重发时序。
- `_frame` 的负例全集（伪造 outcome、跨 session 复用卡、`manifest_id` 指向其它 run 等）逐条实测。
- 真实 MCP 客户端（`scripts/huakangos_mcp.py`）在网络超时后自动重试时与"同请求号"保护的端到端行为。
- 准备类工具在真实表单/原单上的完整建卡与去重（本轮只覆盖只读工具与意图绑定判据）。

源码指纹：`fce9783476ef263f4e55782afccc2e104f5ab0053db34d341621a7885492444b`。
