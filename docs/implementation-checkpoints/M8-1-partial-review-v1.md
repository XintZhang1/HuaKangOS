# M8.1 部分验收记录（综合故障与恢复，**尚未完成**）

2026-09-28，集中测试阶段。前置侦察见 `M8-1-recon-note.md`。**本文件是部分证据，M8.1 仍为未完成。**

## 1. 本轮可执行并已通过的部分

外部套件 `$ValidationRoot/tests/runtime_domains/test_m8_1_fault_recovery.py`（7 项通过，
run `20260928T144342Z-875dbfaa7d`，`phase_complete=true`，源码指纹 `9bebdcdcd6a215a4550c4c69b16d21783bf00c047319dd2c36d26263438812b1`）。

| 断言 | 本轮证据 |
|---|---|
| ② 每个稳定 WorkItem 至多一个有效准备版本 | **真实调用** `assistant_runtime_runner._work_key`：同一 scope+输入项恒等、不同输入项/不同 `plan_id`/不同 `step_key` 各不相同、无计划时锚定 `origin_request_id`；`_work_key` 需 `scope.intent_version` 参与摘要（本轮实测发现） |
| ⑤ 故障重复执行结果稳定 | 同一输入重复 20 次仅得 1 个键；`inspect.getsource` 断言源码不含 `now(`/`utcnow`/`random`/`uuid`/`time(` 等非确定输入 |
| ④ 未知写入绝不重放（冻结与防篡改） | **真实构造**确认项并计算 `submission_snapshot_digest`：`_checked_snapshot` 返回快照、`frozen_payload` 返回脱离副本；**篡改 `body.values` 后两者都必须抛错**；非确认项（`kind='result'`/缺 `proposal_id`）必须被拒 |
| ④ 无回执不得猜成功 | 源码逐字断言：`_lookup_receipt_once` 只按"exact, durable confirmation only"读取，且"no HTTP route or background identity bypass" |
| ① 确认前不得发原请求 | 源码逐字断言：`freeze_confirmation` 文档串要求"a new item together with Proposal.status=executing **before sending the native request**"，且"an existing item is never rewritten"、"created=False does not authorize" |
| ③ 旧租约不得覆盖新状态 | 真实读取签名：`_state_event(db, run, previous_status, *, clock)` 的 `previous_status` **无默认值**，并转交 `_append_queue_transition(previous_status=…)`；文档串要求跃迁"already made in this same transaction"；通知分支（`assistant_notifications_enabled`）**不得再改业务状态** |

## 1b. 第二轮新增：真实子进程注入证据（本轮）

同一套件扩充到 **11 项**，新增 4 项全部在**独立子进程**中执行（run `20260928T144440Z-08c209b393`，
`phase_complete=true`，源码指纹 `a92bcb275e99dab0446621c2cc974926bd8a202c0fe2ec24f9f935d2cd3901ba`）：

| 断言 | 子进程证据 |
|---|---|
| ⑤ 结果级稳定性（跨进程） | 两个**独立子进程**各自计算 40 个输入项的 `_work_key`，键序列**逐字节相同**（此前只验证同进程纯函数级） |
| ② 批量无遗漏 + 隔离 | 子进程内同一 scope 的 1..25 项得到 **25 个互不相同**的键；换 `plan_id` 的另一 scope 与前者**交集为 0**（不复用准备键） |
| ④ 模型协议异常 | 子进程内把 `'{"a": 1'`、`'not-json'`、`'[]'`、`'null'` 四类畸形工具参数交给 `assistant_runtime_registry._parse_arguments`，**没有任何一类被接受**（全部抛错） |
| ① 中断注入 | 子进程在打印一个键后 `SystemExit(3)`：**退出码非零**（不伪装成功），且输出中 `prepare:` 仅出现 1 次（**中断前内容不被重放或补写**） |

## 2. 仍然未完成、因此 M8.1 不登记 done 的部分（更新后）

1. **重复事件注入**：向真实事件/发件箱层注入重复投递（需完整 DB 夹具），验证幂等与不重复准备；
2. **端到端零写入计数**："确认前原业务写入 0、资金/库存等重复事实 0"需完整 DB 与原业务夹具逐笔计数；
3. **批量部分失败即暂停**：真实批量（多行、某行失败即暂停、不跨组）在队列层的核对；
4. **撤权即停**：会话级演练（含 `access_signals.emit_user_access_changed`/`emit_store_access_changed` 路径），
   验证撤权后不继续也不泄露结果；
5. **延迟注入**：慢响应/超时下的状态与"未知结果不自动重试"行为。

## 2. 尚未完成

1. **独立子进程故障注入**：中断、延迟、重复事件、模型协议异常四类注入（清单"允许"范围）尚未实现；
2. **端到端零写入计数**："确认前原业务写入 0、资金/库存等重复事实 0"需完整 DB 与原业务夹具逐笔计数；
3. **批量无遗漏**：真实批量（多行、部分失败即暂停）与"每个稳定 WorkItem 至多一个有效准备版本"的 DB 级核对；
4. **撤权即停**："无授权/撤权不能继续或泄露结果"的会话级演练（含 `access_signals` 事件路径）；
5. **同断言结果稳定性**：同一故障脚本重复运行的**结果级**稳定性（本轮仅覆盖纯函数级稳定性）。

## 2b. 剩余项的夹具条件（本轮已核对，纠正此前假设）

此前记录称 “`V/tests/runtime|integration|fault` 均不存在→故障注入套件需新建”，这一条只说明目录不存在，
**不代表没有 DB 夹具**。本轮核对 `$ValidationRoot/tests/baseline/overlay/tests/conftest.py`（3754 字节），
其中已提供以下夹具：

- `isolated_database`：Base.metadata.drop_all(engine); Base.metadata.create_all(engine) with sqlite3.connect(TEST_DATABASE) as c: c.execute('PRAGMA journal_mode=WAL') with SessionLocal() as db: db.add(Store(id=1,code='MAIN',name='默认门店')); db.
- `client`：with TestClient(app) as client: login(client) yield client
- `login`：r=client.post('/api/auth/login',json={'username':username,'password':password},headers={'X-App-Request':'1'}) assert r.status_code==200,r.text client.headers['X-CSRF-Token']=client.cookies.get('dealer_csrf') return r.json()
- `registered_subprocess_fixture`、`_provenance_sqlite_connect`：分别用于登记子进程夹具与来源库连接。

→ 因此第 2 节剩余 5 项中的 **重复事件注入、批量部分失败即暂停、端到端零写入计数、撤权即停、延迟注入**
**均可**在既有 overlay 夹具上落地（新增用例放在同一 M8.1 套件内即可），无需另起运行环境；
下一轮按此路径继续，不降低断言。

## 2c. HTTP 路由清单与确认入口（本轮逐字核对）

`app/assistant_runtime_api.py` 已注册的路由：`POST /sessions/{session_id}/runs`（202）、`GET /runs/{run_id}`、
`POST /runs/{run_id}/cancel`、`GET /plans/{plan_id}`、`POST /plans/{plan_id}/followup`、`GET /workspace`、
`GET /notifications`、`POST /notifications/{notification_id}/read`、
`GET /sessions/{session_id}/proposals/{proposal_id}/execution-result`、`GET /runs/{run_id}/events`。

**关键定位（本轮新增）**：运行时面**没有确认路由**；真正的业务确认入口在助手侧——
`app/business_assistant_api.py` → **`POST /sessions/{session_id}/proposals/{proposal_id}/confirm`**
（另一处 `master_api.py` 的 `/opening/{batch_id}/confirm` 属期初导入，与本项无关）。
`execution-result` 只**读取**已冻结确认的执行结果。

因此 DB/HTTP 级用例的落点已明确：

1. **确认入口**：`POST /sessions/{session_id}/proposals/{proposal_id}/confirm`（重复提交即验证幂等与不重放）；
2. **准备路径**：卡片/确认项由 `_work_key(scope, input_item_id)`（scope 需 `intent_version`）驱动写入
   `RunItem(kind='confirmation')`；确认时 `freeze_confirmation` 冻结快照并要求 `created=True` 才发原请求；
3. **夹具**：`isolated_database`（每个用例干净合成库）+ `client`/`login`（真实 HTTP 与已登录员工会话）；
   模型侧一律用桩，禁真实联网。

尚未落地，故本轮**不**登记任何新的通过项，也不把 M8.1 记为 done。

## 3. 本轮实测发现的真实事实（已纳入套件）

- `_work_key` 的 scope 还要求 **`intent_version`**（首轮因缺该键直接 `KeyError`）→ 已写入夹具，
  并说明准备键的摘要输入是 `{plan_id|origin_request_id, step_key, input_item_id, intent_version}`。

## 4. 状态登记

`### M8.1` 登记为 **`in_progress`**（唯一在办项）：已具备可执行的部分证据，但上节 5 项未完成前不得 `done`。
