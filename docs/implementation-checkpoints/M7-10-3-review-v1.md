# M7.10.3 编码审阅与实测记录（调拨差异处置适配器）

2026-09-28，集中测试阶段。M7.10 组第三项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/transfer_exception.py`：`TransferExceptionAdapter(FlowCaseAdapter)`，`object_types=('transfer_exception',)`；快照只读 `GET /api/transfer-exceptions/{key}`（**key 即原 TransferException.id**）；`read_receipt` 走 `TransferExceptionReceipt` 族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='transfer_exception', object_types=(EXC_OBJECT_TYPE,), operation_ids=(GET /api/transfer-exceptions/{key}, POST /api/transfer-exceptions, POST /api/transfer-exceptions/{key}/actions/{action}), fact_keys=EXC_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_transfer_exception.py`（7 项） |
| 未改动 | 原 `transfer_exception_api.py`/`_service.py`/`_models.py`/`transfer_exception_recovery.py`、迁移、权限表、数量与损失公式、状态机；未新增 signal hook；未改 `store_id` |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/transfer-exceptions/{key}` | `{'key': <TransferException.id>}` | 原差异单详情（`status`、`transfer_id`、`observations`/`disposals`/`loss_postings`/`plan`（按原详情提供）） |
| 只读来源 | `GET /api/transfer-exceptions/origins/{transfer_id}` | `{'transfer_id'}` | 原可处置来源读取（登记为只读来源，不作为结果 operation） |
| result | `POST /api/transfer-exceptions` | — | 原创建响应 |
| result / receipt | `POST /api/transfer-exceptions/{key}/actions/{action}` | `{'key','action'}` | 原动作响应（observe/plan/approve/reject_plan/dispose/post_loss/cancel）；回执族 `TransferExceptionReceipt` |

事实键与满足条件（**方案批准不等于处置或过账**）：
- `transfer_exception.observation_recorded`：本单原 `TransferExceptionObservation`；
- `transfer_exception.disposal_recorded`：本单原 `TransferExceptionDisposal`；
- `transfer_exception.loss_posted`：本单原 `TransferLossPosting`；
- 三者只在原详情确实提供对应记录时满足；**只看到方案（plan）时返回未知**并点名该规则；完全没有则明确未满足。

## 3. 实测结论

运行 `20260928T141958Z-778dc94ded`：`status=passed`，`phase_complete=true`（源码指纹 `a70755e2b77a8f9aea31b5d9d3ed67b7c67edb5786b9011c3f7db6c7af282488`）。

- `tests/runtime_domains/test_transfer_exception.py`：**7 项通过**。覆盖四条 operation 在 reviewed catalog、四个原 service 函数与七个原动作、四个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照 key 即差异单 id、ID 不一致 502、**缺原调拨单引用 502**、无门店身份 403、动作可用性 `unknown`；三条事实的满足/未满足/未知分支（含"只有方案时未知且点名方案批准不等于处置或过账""观察记录缺失明确未满足"两条显式断言）；未登记事实不猜；`extract_result` 边界（来源读不绑定）；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `transfer_exception` 一个适配器；M7.10.4 起 20 个小项仍为 `todo`，按编号串行。
- 观察/处置/过账记录的判定沿用原详情实际提供的字段；未提供时按合同未知。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
