# M7.2.3 编码审阅与实测记录（整车批量导入批次适配器）

2026-09-28，集中测试阶段。M7.2 组第三项。**本项先经一次错误判断后更正并实测通过，过程如实保留。**

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/vehicle_import_batch.py`：`VehicleImportBatchAdapter(FlowCaseAdapter)`，`object_types=('vehicle_import_batch',)`；快照只读 `GET /api/vehicle-imports/batches/{batch_id}`（活跃路由发现），动作走已评审 `POST .../actions/{action}` |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='vehicle_import_batch', object_types=('vehicle_import_batch',), operation_ids=(POST /api/vehicle-imports/batches/{batch_id}/actions/{action},), fact_keys=IMPORT_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_vehicle_import_batch.py`（9 项） |
| 未改动 | 原 `vehicle_imports_api.py`/`_service.py`/`_models.py`、迁移、权限表与状态机；未新增 signal hook；未扩大任何目录 |

## 2. 目录规则（本项关键判据，实测）

`app/business_assistant_gateway._operations()`：**写操作须在 reviewed catalog 内；GET 由活跃路由发现**，并受 `DOMAINS`/`CLOSED_DOMAINS`/`DENIED`/body 过滤与调用时授权。隔离镜像实测 `GET /api/vehicle-imports/batches/{batch_id}` → `discovered: True`。

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/vehicle-imports/batches/{batch_id}` | `{'batch_id': <Batch.id>}` | 原批次详情（`status`、`row_count`、`rows[]` 含每行稳定 `id` 与 `result`） |
| result / receipt | `POST /api/vehicle-imports/batches/{batch_id}/actions/{action}` | `{'batch_id','action'}` | 原动作响应；回执族 `VehicleImportRequest` |

事实键与满足条件：`vehicle_import.reviewed`（原 `status='reviewed'`）、`vehicle_import.confirmed`（原 `status='confirmed'`，**已审阅不等于已确认**）、`vehicle_import.all_rows_result_recorded`（`len(rows)==row_count` 且每行按 `kind` 有真实 `funds_request_id`/`shipment_id`/`receipt_id`；缺行、重复行标识、未登记类别、缺结果字段一律 `unknown`）。

## 3. 实测结论

运行 `20260928T131640Z-e250f94ef3`：`status=passed`，`phase_complete=true`（源码指纹 `46229e32526130166d92e4ba72828d3053f0c33f8c3774206c9bc7adc7ef9bcd`）。

- `tests/runtime_domains/test_vehicle_import_batch.py`：**9 项通过**。覆盖目录规则（写操作在 JSON 目录内、GET 由路由发现、原过滤存在）、注册范围（只登记已评审写操作、对象类型、事实键、不抢回退）、快照单次 GET（返回 `vehicle_import_batch` 引用与 `native_version`）、ID 不一致 502、无门店身份 403、上游 503、引用类型四类非法输入 422、`reviewed`/`confirmed` 各自满足与未满足、`all_rows` 的完整/缺行/未完成行/重复行/未登记类别五分支、未登记事实不猜、`extract_result` 边界、回执族保持冻结 `request_id`（只读详情 422 不属回执族）、五个原动作名与行结果字段映射与原 API 一致。
- 同指纹回归：M7.2.2、M7.2.1 均通过。

## 4. 实测发现并修复的问题

1. **我自己的错误判断（已撤回）**：先前把 JSON 目录当作读取白名单，误报"批次详情不在 reviewed catalog → 能力缺口"。实测 `_operations()` 后更正：GET 由活跃路由发现；据此实现真实读取。撤回说明见 `docs/implementation-checkpoints/M7-2-3-capability-gap.md`。
2. **批次对象不是 Case**：父类 `snapshot_from_record` 会按 `case` 校验引用（实测 422）。现由适配器直接投影统一快照 DTO：任务按原字段严格校验（重复/非法 ID 502），动作可用性一律 `unknown`（原批次只返回岗位筛选的动作名，不当作已验证可用）。
3. **项数下限**：首轮 8 项低于登记下限被运行器如实拦截；本项现为 9 项（含目录规则项）。

## 5. 未完成/未验收（如实登记）

- 文件上传仍是原封闭面，助手只返回原页面入口；不接上传、不新增自动确认。
- 批次动作的准备/确认链路依赖核心运行时与员工点击原确认，属集中测试阶段的范围；真实原库、真实模型、浏览器与员工试用属 M8.x。
