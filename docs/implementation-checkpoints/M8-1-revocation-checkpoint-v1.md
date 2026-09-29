# M8.1 会话级撤权检查点 v1

2026-09-30；开发候选。**M8.1 保持 `in_progress`**：本记录只完成计划清单第 ③ 项中
「撤权后既有会话不得继续／泄露结果」的**会话级真实 HTTP 演练**，其余四项仍未完成。
不部署、不默认开启四个功能开关、不调用真实模型。

## 1. 这一步补的是什么

`M8-1-partial-review-v1.md` 第 2i 节已记录第七轮证据：撤权/换岗后**原提案**确认被 `409` 拒绝，
两个撤权信号发射器都受功能开关约束。但该记录的「仍未完成」明确列出：

> ③ 的**会话级**演练（真实 HTTP 会话在撤权后不得继续/泄露结果，含 `access_signals` 的两条事件路径）

本检查点补的就是这一条：**真实登录会话 + 真实 HTTP 接口**，而不是直接调用
`freeze_confirmation`。

## 2. 本批实际改动文件

生产代码：**无**。只新增外部隔离套件 `tests/assistant_offline/tests/test_revocation_session.py`
（5 项）。

## 3. 先核对真实机制（本轮最重要的发现）

动手写断言前先读实现，得到两条与原假设**不同**的事实，故未按假设写断言：

1. **`workspace` / `notifications` 在撤权后返回 `200`，不是 `403`。**
   `AssistantSession.access_version` 与 `AssistantProposal.access_version` 在会话/提案建立时冻结，
   而 `assistant_runtime_workspace` 的读取按
   `AssistantSession.access_version == identity.access_version` 过滤
   （`assistant_runtime_workspace.py:216`、`:220`）。撤权后 epoch 变化，旧会话**直接被过滤掉**，
   所以正确结论是「**不可见**」而不是「拒绝」。我最初的 `403` 断言是**猜错契约**，已按真实行为改写。
2. **`GET /sessions/{id}` 在撤权后返回 `404`**（同上会话级过滤），而
   `POST /sessions/{id}/runs`、`POST …/proposals/{id}/confirm` 对旧 epoch 同样不可达。
   另外 `confirm` / `runs` 都有**请求体契约**（`digest` 64 位十六进制、`request_id` 必填），
   校验不过会在身份检查之前返回 `422`；因此用例必须给出形状合法的请求体，否则断言会
   「因为 422 而通过」，那是假绿。

以上两条已写入用例注释，避免后来者重复猜错。

## 4. 五项断言与真实结果

命令（唯一入口，测试源码先复制到仓库外全新目录）：

```powershell
python tests/assistant_offline/run_isolated.py --source E:\HuaKangOS `
  --output E:\HuaKangOS-validation\revoke-<UTC时间戳> --browser-mode off `
  --suite test_revocation_session.py
```

| 用例 | 断言 | 结果 |
|---|---|---|
| `test_revoked_epoch_loses_its_conversation_without_leaking_it` | 撤权前同一会话可读（防「因别的原因通过」）；撤权后旧会话 `404`、`workspace` 200 但**不含**旧会话 id 与标题 | ok |
| `test_revoked_epoch_cannot_confirm_or_read_its_proposal` | 形状合法的 `digest` 提交后 `confirm` 与 `execution-result` 均为拒绝（`403/404/409`），绝不返回新授权 | ok |
| `test_revoked_epoch_cannot_start_a_new_run_or_conversation` | 旧会话起 Run 被拒；**新**会话允许 `201`（员工仍在线），但旧会话仍不出现在 `/sessions` 列表 | ok |
| `test_notifications_after_revocation_do_not_serve_the_old_epoch` | 通知读取不返回旧 epoch 的会话 id/标题 | ok |
| `test_refusal_is_an_epoch_change_and_not_a_lost_account` | 撤权后账号仍 `active`、`must_change_password=False`、岗位不变，`access_version` 恰为 +1 —— 证明「停」来自 epoch 变化，不是账号损坏 | ok |

`Ran 5 tests`、`OK`、退出码 0；`real_model_calls=0`、`browser_transport=not_run`。
套件通过方式与被测事实一致：**撤权由真实已提交事务提升 `access_version` 实现**，不是 mock。

### 4.1 未按假设写断言的第三处

我最初把「撤权后新建会话」也算成必须被拒，实测返回 `201`。核对后确认这才是正确行为：
员工仍持有有效登录会话，撤权改变的是**授权 epoch**，新 epoch 下新建对话是合法的；
必须保证的是**旧 epoch 的东西不回来**，故用例改为断言
「新会话可见 + 旧会话不可见」。该用例第一次运行确实红过，红的原因是我的断言错，
产品代码未改，也未放宽其它断言。

## 5. 与本套件同时执行的完整回归

同批次完整回归（`fixture` 传输，供交叉确认新增套件未破坏既有行为）：

| 层次 | 用例数 | 结果 |
|---|---:|---|
| 后端领域与集成（17 个套件，含本批新增 `test_revocation_session.py` 5 项） | 208 | 全部通过 |
| 前端模块行为（Node） | 55 | 全部通过 |
| Chromium 页面操作（`fixture` 传输，**不构成原生验收**） | 14 | 全部通过 |
| 合计 | **277** | 全部命令退出码 0 |

`run-summary.json`：`complete=true`、`scope=full`、`real_model_calls=0`、`release_accepted=false`。

## 6. 仍未完成，因此 M8.1 不登记 done

按 `M8-1-partial-review-v1.md` 与本记录，M8.1 清单仍未完成的部分：

1. **旧租约不得覆盖新状态的 DB 跃迁演练**：`_append_queue_transition` 的严格 CAS
   （`run.version <= old['version']` → `_conflict()`）已逐字核对（§2j/§2j.1），但 `Run` 行受
   `ck_assistant_run_login_ref` 约束，`login_session_ref` 必须对应**真实登录会话的哈希**，
   不能凭字段拼装；需用真实登录夹具派生后再落地断言；
2. **确认前原业务写入计数**：需要完整原业务夹具逐笔计数「确认前原业务写入 0」；
3. **批量部分失败即暂停**：队列层多行批量的核对；
4. **延迟注入**：慢响应／超时下的状态与「未知结果不自动重试」。

以上四项不在本记录范围内，**不得**据本记录把 M8.1 记为 `done`，也不放行任何生产行为。

## 7. 明确不声称的事项

- 本记录**不**覆盖 `access_signals.emit_user_access_changed` / `emit_store_access_changed` 的
  两条事件路径端到端发射（发射器要求真实的 `UserAccessReceipt` 与配套审计前后像，与「撤权后既有
  会话不得继续」是两件事）；第七轮已记录两条发射器受功能开关约束。
- 未执行原生浏览器、PostgreSQL、真实模型、独立 Windows/Linux 恢复演练与员工试用。
- 未修改任何功能开关默认值；四个新功能开关仍默认关闭。