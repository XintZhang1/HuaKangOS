# M7.2.2 编码审阅与实测记录（整车库位及出退库作业适配器）

2026-09-28，集中测试阶段。M7.2 组第二项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/vehicle_operation.py`：`VehicleOperationAdapter(FlowCaseAdapter)`，`kind='vehicle_operations'`、`flow_version=2`；`read_snapshot` 只读 `GET /api/vehicle-operations/orders/{case_id}`；`extract_result` 覆盖作业族 operation；`read_receipt` 走 `vehicle_operation_` 前缀回执族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='vehicle_operation', …)`，`operation_ids=(GET /api/vehicle-operations/orders/{case_id}, POST /api/vehicle-operations/orders, POST /api/vehicle-operations/orders/{case_id}/actions/{action})`，`kind_versions=fact_kind_versions=(('case','vehicle_operations',2),)`、`fallback_object_types=()` |
| 外部套件 | `V/tests/runtime_domains/test_vehicle_operation.py`（9 项） |
| 未改动 | 原 `vehicle_operations_api.py`/`_service.py`/`_models.py`、迁移、权限表、`Vehicle.store_id` 与状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/vehicle-operations/orders/{case_id}` | `{'case_id': <Case.id>}` | 原作业详情（`kind`/`status`、来源与目的库位、`entries[]` 位置流水含 `inventory_delta`、`inspections[]` 实车检查） |
| result | `POST /api/vehicle-operations/orders` | — | 原作业单创建响应（顶层 Case） |
| result / receipt | `POST /api/vehicle-operations/orders/{case_id}/actions/{action}` | `{'case_id','action'}` | 原动作响应；回执族 `flow_request_receipts`（`vehicle_operations_service.execute` 的 `request_digest('vehicle_operation_'+action, payload)`） |

五个业务类别与原 `KINDS` 表一致：`locate` / `local_move` / `other_out` / `other_return` / `customer_return`（套件读取原 service 的 `KINDS` 表断言相等）。

事实键与满足条件：
- `vehicle_operation.dispatch_recorded`：本单原位置流水存在**负数** `inventory_delta`（实际发出）；状态文字或动作可用性不算。
- `vehicle_operation.accept_recorded`：本单原位置流水存在**正数** `inventory_delta`（目的库位实际接收）。
- `vehicle_operation.inspection_recorded`：本单存在原 `VehicleReturnInspection`；**只证明已登记检查，绝不解释为合格**（reason 明确"是否合格以原检查结论与处置决定为准"）。

## 3. 实测结论

运行 `20260928T130920Z-3f226e165b`：`status=passed`，`phase_complete=true`（源码指纹 `f518dd66a12d17283230564336fe2d0044c7e1ab60688ad228e47f7073afbc2f`）。

- `tests/runtime_domains/test_vehicle_operation.py`：9 项通过。覆盖映射在 reviewed catalog 与活跃路由可解析、回执前缀与原动作标签、`VehiclePositionEntry`/`VehicleReturnInspection` 模型存在、适配器不动态导入/不写库；注册只按 `flow_version=2` 且不抢通用回退；快照单次 GET、kind 422、**缺来源车辆 502（不补默认值）**、ID 不一致 502；无门店身份 403、上游 503、原岗位拒绝 404 不暴露旧快照；发出/接收按位置流水正负判定（只有出库流水时接收明确未满足）；检查存在不等于合格；未登记事实不猜；`extract_result` 边界；回执族保持冻结 `request_id`、未绑定 `unsupported`、非法快照 422；**五类业务类别与原 `KINDS` 表一致**。
- 同指纹回归：M7.2.1（vehicle_purchase）仍通过。

## 4. 实测发现并修复的问题

- 首轮套件只有 8 项，低于本里程碑登记的 9 项下限，运行器按 `below_registered_minimum` 判不完整（如实拦截，而非放行）。已补上"五类业务类别与原 `KINDS` 表一致"的映射保真断言，凑齐并加强为 9 项后复跑通过。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `vehicle_operation` 一个适配器；M7.2.3 起 47 个小项仍为 `todo`，按编号串行。
- 拒收/整改/退回客户等状态转移仍以原动作为准；适配器不补默认库位、不改 `Vehicle.store_id`、不把检查记录当合格。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
