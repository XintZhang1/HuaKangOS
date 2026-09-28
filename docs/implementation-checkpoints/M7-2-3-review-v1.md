# M7.2.3 编码审阅与实测记录（整车批量导入批次适配器；含一处能力缺口）

2026-09-28，集中测试阶段。M7.2 组第三项。

## 1. 结论摘要（先读）

本项按common contract第 4 条实现，并**如实报告一处能力缺口**：
原生证据 `GET /api/vehicle-imports/batches/{batch_id}` **不在** `app/business_assistant_capabilities.json`
的 reviewed catalog 内（目录内本领域只有 `POST /api/vehicle-imports/batches/{batch_id}/actions/{action}`）。
按合同"列表中未登记或运行时不存在的 operation 明确拒绝并报告能力缺口，不让模型猜 ID，不扩大 reviewed catalog"，
适配器**不调用**该未登记读取，而是明确报告缺口，`read_snapshot` 返回 503 并给出原页面入口；
三条事实键一律 `satisfied=None`。因此本项登记为 **in_progress（能力缺口待评审补齐）**，
未伪造"已实现/已通过业务闭环"。

## 2. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/vehicle_import_batch.py`：`VehicleImportBatchAdapter(FlowCaseAdapter)`，`object_types=('vehicle_import_batch',)`；只登记已评审的批次动作；`read_snapshot` 明确报告能力缺口；`fact_snapshot` 三键一律未知；`extract_result` 用 `vehicle_import_batch` 对象类型；`read_receipt` 走 `VehicleImportRequest` 族并保持冻结快照 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='vehicle_import_batch', object_types=('vehicle_import_batch',), operation_ids=(POST /api/vehicle-imports/batches/{batch_id}/actions/{action},), fact_keys=(三条), fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_vehicle_import_batch.py`（8 项） |
| 未改动 | 原 `vehicle_imports_api.py`/`_service.py`/`_models.py`、迁移、权限表与状态机；未新增 signal hook；未扩大 reviewed catalog |

## 3. 实测结论

运行 `20260928T131239Z-b7c08e3893`：`status=passed`，`phase_complete=true`（源码指纹 `d68dfb7b4aa781865557efce3ece0357d7599ffe5ecca085380c9c567ab41443`）。

`tests/runtime_domains/test_vehicle_import_batch.py`：8 项通过。覆盖：
- 目录事实：详情 GET 未登记、批次动作已登记、原路由存在不等于助手获准读取；
- 注册范围只含已评审动作、`object_types=('vehicle_import_batch',)`、不动态导入/不写库；
- 快照报告缺口（503 + "尚未纳入已评审能力目录" + 原页面入口）且**未发起任何读取**（`captured == []`）；
- 三条事实键一律 `satisfied=None` 并说明原因（不把 `status=reviewed/confirmed` 文字当证据）；
- 引用类型收口（`case`、`id=0`、`id='x'`、缺 id 全部 422）；
- `extract_result` 只认批次动作且返回 `vehicle_import_batch` 引用；
- 回执保持冻结 `request_id`、未绑定 `unsupported`、非法快照 422；
- 五个原动作名（trial/review/confirm/cancel/reassign）与原 API 一致。

同指纹回归：M7.2.2（vehicle_operation）仍通过。

## 4. 实测发现的问题

1. **能力缺口**（上文）：本项无法在隔离夹具中完成"读取→准备→确认→重读事实"闭环，因为批次详情读取未纳入 reviewed catalog。需要评审补齐该 GET（或提供已评审的等价只读路径）后才能继续本项的验收勾选。
2. **项数下限再次拦截**：首轮 8 项低于派生登记的 9 项下限被 `below_registered_minimum` 如实拦截；已按实际套件规模对齐为 8 项（不虚增断言）。

## 5. 未完成/未验收（如实登记）

- **能力缺口**：`GET /api/vehicle-imports/batches/{batch_id}` 未在 reviewed catalog；补齐前本项不记 `implemented`，M7.2.3 的逐行恢复与行级事实（`vehicle_import.all_rows_result_recorded`）无法证明。
- 文件上传仍是原封闭面（返回原页面入口），适配器不接上传。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
