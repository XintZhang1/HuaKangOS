# M7.2.1 编码审阅与实测记录（整车采购逐 VIN 进度适配器）

2026-09-28，集中测试阶段。M7.2 组首项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/vehicle_purchase.py`：`VehiclePurchaseAdapter(FlowCaseAdapter)`，`kind='vehicle_procurement'`、`flow_version=2`；`read_snapshot` 只读 `GET /api/vehicle-procurement/orders/{case_id}`；`extract_result` 覆盖采购族 operation；`read_receipt` 走 `vehicle_purchase_` 前缀回执族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='vehicle_purchase', …)`，`operation_ids=(GET /api/vehicle-procurement/orders/{case_id}, POST /api/vehicle-procurement/orders, POST /api/vehicle-procurement/orders/{case_id}/actions/{action})`，`kind_versions=fact_kind_versions=(('case','vehicle_procurement',2),)`、`fallback_object_types=()` |
| 外部套件 | `V/tests/runtime_domains/test_vehicle_purchase.py`（9 项） |
| 未改动 | 原 `vehicle_procurement_api.py`/`_service.py`/`_models.py`、迁移、权限表、金额公式与状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/vehicle-procurement/orders/{case_id}` | `{'case_id': <Case.id>}` | 原采购详情（`lines[]` 含 `unshipped_quantity`、`shipments[]`、`receipts[]`、`payments[]`、`funds_requests[]`、`returns[]`、`movements[]`；金额按岗位可见性） |
| result | `POST /api/vehicle-procurement/orders` | — | 原采购单创建响应（顶层 Case） |
| result / receipt | `POST /api/vehicle-procurement/orders/{case_id}/actions/{action}` | `{'case_id','action'}` | 原动作响应；回执族 `flow_request_receipts`（`vehicle_procurement_service.execute` 的 `request_digest('vehicle_purchase_'+action, payload)`） |

事实键与满足条件（**三个键都只证明至少一笔对应事实，不声明整批齐套**）：
- `vehicle_purchase.shipment_recorded`：本单存在原 `VehiclePurchaseShipment`；没有即明确未满足。
- `vehicle_purchase.receipt_recorded`：必须存在原 `VehiclePurchaseReceipt` 且同时带 `shipment_id` 与 `vehicle_id`（逐 VIN 验收）；引用不全返回未知；金额可见性不影响本键。
- `vehicle_purchase.payment_recorded`：必须存在 `direction='out'` 的原 `VehiclePurchasePayment`；付款申请、价格版本、`direction='in'` 都不满足；岗位看不到付款明细时返回未知并提示原单核对。

## 3. 实测结论

运行 `20260928T130552Z-33d5660f42`：`status=passed`，`phase_complete=true`（源码指纹 `936951adca48b39bbfecb6af8306eef828c17cb8b169e7cdec1dc44bdaf5bcd9`）。

- `tests/runtime_domains/test_vehicle_purchase.py`：9 项通过。覆盖映射在 reviewed catalog 与活跃路由可解析、`vehicle_purchase_` 回执前缀与九个原动作存在、三个原模型存在、适配器不动态导入/不写库；注册只按 `flow_version=2` 且不抢通用回退；快照单次 GET、旧/未知版本 404（按原页面兜底）、ID 不一致 502；跨店 404、无门店身份 403、上游 503、原岗位 403 不暴露旧快照；三条事实的满足/未满足/未知分支（含"付款申请不满足实际付款键"与"引用不全逐 VIN 核对"）；未登记事实不猜；`extract_result` 版本与状态边界；回执保持冻结 `request_id`、未绑定 `unsupported`、非法快照 422。
- 同指纹回归：M7.1.3（aftercare）仍通过。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `vehicle_purchase` 一个适配器；M7.2.2 起 48 个小项仍为 `todo`，按编号串行。
- 一张总卡成功不代表整批车辆入库：事实键只到"至少一笔"，齐套判断仍以原单逐 VIN 为准。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
