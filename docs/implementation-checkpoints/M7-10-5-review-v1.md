# M7.10.5 编码审阅与实测记录（整车运输异常适配器）

2026-09-28，集中测试阶段。M7.10 组第五项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/vehicle_transport_exception.py`：`VehicleTransportExceptionAdapter(FlowCaseAdapter)`，`object_types=('vehicle_transport_exception',)`；快照只读 `GET /api/vehicle-transport-exceptions/{key}`（**key 即原异常案 id**）；`read_receipt` 由已评审 resolver 绑定 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='vehicle_transport_exception', object_types=(VTE_OBJECT_TYPE,), operation_ids=(GET /api/vehicle-transport-exceptions/{key}, POST /api/vehicle-transport-exceptions, POST /api/vehicle-transport-exceptions/{key}/actions/{action}), fact_keys=VTE_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_vehicle_transport_exception.py`（8 项） |
| 未改动 | 原 `vehicle_transport_api.py`/`_service.py`/`_models.py`、迁移、权限表、损失与结算公式、状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/vehicle-transport-exceptions/{key}` | `{'key': <VehicleTransportException.id>}` | 原异常案详情（`status`、`vin`、`losses`/`found_receipts`/`found_unavailable`/`plan` 按原详情提供） |
| result | `POST /api/vehicle-transport-exceptions` | — | 原创建响应 |
| result / receipt | `POST /api/vehicle-transport-exceptions/{key}/actions/{action}` | `{'key','action'}` | 原动作响应（observe/observe_found/plan_resume/plan_found/dispose/post_loss/found_receive/found_unavailable）；回执由已评审 resolver 绑定 |

事实键与满足条件：
- `vehicle_transport.loss_posted`：本案原 `VehicleTransportLoss`；理由明确**过账不改变原实物状态**；
- `vehicle_transport.found_received`：本案原 `VehicleTransportFoundReceipt` **且原 VIN 一致**；本单缺 VIN 或 VIN 不一致 → 未知；
- `vehicle_transport.found_unavailable_recorded`：本案原 `VehicleTransportFoundUnavailable`；理由明确**不构成找回完成**；
- **计划找回不满足实际找到/接收键**：只有计划（plan）时三条都返回**未知**而非未满足；容器键存在但值为 `null` 视为**未提供**。

## 3. 实测结论

运行 `20260928T142422Z-e5b4d3eca8`：`status=passed`，`phase_complete=true`（源码指纹 `37c8822b57b2a02ee7cc66b12c3d8026dd3b75c58b6bf5983e9af86c416fa33a`）。

- `tests/runtime_domains/test_vehicle_transport_exception.py`：**8 项通过**。覆盖三条 operation 在 reviewed catalog、四个原 service 函数、三个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照 key 即异常案 id、ID 不一致 502、**缺原运输单引用 502**、无门店身份 403、动作可用性 `unknown`；三条事实的满足/未满足/未知分支（含"null 容器视为未提供必须未知""VIN 不一致/缺 VIN 必须未知""计划找回必须未知且点名规则""找回不可用不构成找回完成"四条显式断言）；未登记事实不猜；`extract_result` 边界；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮**一次如实拦截 + 一处产品修复**：首轮"只有计划（plan）"时返回 False，合同要求未知 → 已改为 `_unknown` 并保留规则说明（真实产品缺陷）。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `vehicle_transport_exception` 一个适配器；M7.10.6 起 18 个小项仍为 `todo`，按编号串行。
- 记录明细的判定沿用原详情实际提供的字段；未提供时按合同未知。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
