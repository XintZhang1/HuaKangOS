# M7.10.1 编码审阅与实测记录（物资调拨适配器）

2026-09-28，集中测试阶段。M7.10 组首项，CP-30 起点。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/material_transfer.py`：`MaterialTransferAdapter(FlowCaseAdapter)`，`object_types=('material_transfer',)`；快照只读 `GET /api/transfers/{key}`（**key 即原 MaterialTransfer.id**）；`read_receipt` 走 `TransferReceipt` 族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='material_transfer', object_types=(TRANSFER_OBJECT_TYPE,), operation_ids=(GET /api/transfers/{key}, POST /api/transfers, POST /api/transfers/{key}/actions/{action}), fact_keys=TRANSFER_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_material_transfer.py`（8 项） |
| 未改动 | 原 `transfer_api.py`/`_service.py`/`_models.py`、迁移、权限表、数量与结算公式、状态机；未新增 signal hook；未改 `store_id` |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/transfers/{key}` | `{'key': <MaterialTransfer.id>}` | 原调拨单详情（`status`、`lines[]`、`movements[]`（原 `TransferMovement`）） |
| 只读目的店 | `GET /api/transfers/destinations` | — | 原目的店读取（登记为只读来源，不作为结果 operation） |
| result | `POST /api/transfers` | — | 原创建响应 |
| result / receipt | `POST /api/transfers/{key}/actions/{action}` | `{'key','action'}` | 原动作响应（dispatch/receive/return_ship/return_receive）；回执族 `TransferReceipt`（原 `execute` 的 action/payload 摘要） |

五种原状态：`requested` / `approved` / `transit` / `completed` / `cancelled`（未知状态 422，不当可用单）。

事实键与满足条件（**至少一行记录不代表整批齐收**）：
- `material_transfer.dispatch_recorded`：本单原 `TransferMovement` 的 dispatch 来源；
- `material_transfer.receive_recorded`：本单原 receive movement；
- `material_transfer.return_receive_recorded`：本单原 return_receive movement；
- 三者都要求**可识别的流水类型 + 行引用 `line_id` + 正数量**，并保留**双方店**；缺行/缺数量/双方店引用不完整一律未知；详情未提供流水时未知；无类型流水不能满足任一具名事实。

## 3. 实测结论

运行 `20260928T141606Z-dabed5535d`：`status=passed`，`phase_complete=true`（源码指纹 `189eb61cfbaf4bd8295744452f47e543a735ee170c2f1daee56b274e8adc3bd9`）。

- `tests/runtime_domains/test_material_transfer.py`：**8 项通过**。覆盖四条 operation 在 reviewed catalog、四个原 service 函数与回执族、四个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照 key 即调拨单 id、ID 不一致 502、**未登记状态 422**、无门店身份 403、上游 503、动作可用性 `unknown`；引用类型四类非法输入 422；三条事实的满足/未满足/未知分支（含"只有 dispatch 时接收与退回接收明确未满足""双方店必须保留""缺 line_id/数量不完整必须未知""无类型流水不满足任一事实"四条显式断言）；未登记事实不猜；`extract_result` 边界（目的店读不绑定）；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `material_transfer` 一个适配器；M7.10.2 起 22 个小项仍为 `todo`，按编号串行。
- 流水类型/双方店的判定沿用原详情实际提供的字段；未提供时按合同未知。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
