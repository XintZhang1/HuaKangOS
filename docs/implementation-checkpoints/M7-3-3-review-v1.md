# M7.3.3 编码审阅与实测记录（维修领退料与返修适配器）

2026-09-28，集中测试阶段。M7.3 组第三项，CP-19 收官项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/rework_grant.py`：`ReworkGrantAdapter(FlowCaseAdapter)`，`object_types=('rework_source_grant',)`；快照只读 `GET /api/rework-extensions/grants/{key}`；`extract_result` 覆盖授权族五条 operation；`read_receipt` 走 `ReworkGrantReceipt` 族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='rework_grant', object_types=('rework_source_grant',), operation_ids=(GET /api/rework-extensions/grants/{key}, POST .../grants, POST .../grants/{key}/actions/{action}, POST /api/rework-extensions/requests, POST /api/rework-extensions/orders/{key}/quote), fact_keys=GRANT_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_rework_grant.py`（10 项） |
| 未改动 | 原 `rework_extension_api.py`/`_service.py`/`_models.py`、迁移、权限表、范围摘要与状态机；未新增 signal hook；未改 `store_id` |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/rework-extensions/grants/{key}` | `{'key': <ReworkSourceGrant.id>}` | 原授权详情（`status`、`expires_at`、`can_receive`、`original_liability_limit_cents`、`source_*`，按来源店/有效范围裁剪） |
| result | `POST /api/rework-extensions/grants`；`POST /api/rework-extensions/requests`；`POST /api/rework-extensions/orders/{key}/quote` | — | 原创建/申请/报价准备响应 |
| result / receipt | `POST /api/rework-extensions/grants/{key}/actions/{action}` | `{'key','action'}` | 原动作响应；回执族 `ReworkGrantReceipt`（`grant_digest` 范围摘要） |

四个原动作：`approve` / `reject` / `cancel` / `revoke`。

事实键与满足条件：
- `rework.approval_recorded`：原状态已离开 `pending`/`rejected`（只有 approve 决定才会如此）；**批准历史不证明当前未撤销或尚有可用范围**，理由中明确写出。
- `rework.revocation_recorded`：原状态确为 `revoked`；已批准明确不等于已撤销。
- `rework.extension_recorded`：必须有原 `ReworkExtension` 确证本授权与承接维修单的关系；**该详情不提供承接关系，故一律返回未知**，绝不用批准历史代替。

责任授权额度只投影原 `original_liability_limit_cents`；**客户自费部分（customer_extra）不推断**（套件断言源码中不出现该字段）。

## 3. 实测结论

运行 `20260928T132534Z-b69cd96f4f`：`status=passed`，`phase_complete=true`（源码指纹 `71ecab9e9cce1353da696460c6d02e7968412fce159cbc9182d082c6026f6156`）。

- `tests/runtime_domains/test_rework_grant.py`：**10 项通过**。覆盖五条 operation 在 reviewed catalog、`ReworkGrantReceipt`/`grant_digest` 与原四动作、四个原模型存在、不动态导入/不写库；**注册真的到达运行时注册表**（Spy 捕获 `DomainAdapterSpec`）；快照单次 GET、ID 不一致 502、跨店授权字段非法 502（不补默认门店）、无门店身份 403、上游 503、动作可用性 `unknown`；引用类型四类非法输入 422；三条事实的满足/未满足/未知分支（含"批准历史不证明当前有效""已批准不等于已撤销""承接关系必须未知"三条显式反例）；未登记事实不猜；`extract_result` 边界；回执族保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422；责任额度投影与客户自费隔离。
- 同指纹回归：M7.3.2（repair_order）仍通过。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- CP-19（M7.3.1—M7.3.3）三项适配器均已 implemented 并实测；`released` 仍不记，因为真实原库、真实模型、浏览器与员工试用属 M8.x。
- `rework.extension_recorded` 在缺少已评审的承接关系读取前保持未知；派生接待命令的回执仍走 `IntakeReceipt`，不在本适配器范围。
- 其余 M7 小项与 M8.x 按编号串行。
