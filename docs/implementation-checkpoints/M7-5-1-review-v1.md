# M7.5.1 编码审阅与实测记录（物资采购、预付与仓储适配器）

2026-09-28，集中测试阶段。M7.5 组首项，CP-22 起点。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/material_procurement.py`：`MaterialProcurementAdapter(FlowCaseAdapter)`，`object_types=('case',)`；快照只读 `GET /api/procurement/orders/{case_id}`；`extract_result` 覆盖采购族 operation；`read_receipt` 走 `procurement_` 前缀回执族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='material_procurement', object_types=('case',), operation_ids=(GET /api/procurement/orders/{case_id}, POST /api/procurement/orders, POST /api/procurement/orders/{case_id}/actions/{action}), fact_keys=PROC_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_material_procurement.py`（8 项） |
| 未改动 | 原 `procurement_api.py`/`_service.py`/`_models.py`、迁移、权限表、金额与数量公式、状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/procurement/orders/{case_id}` | `{'case_id': <Case.id>}` | 原采购详情（`state`、`receiving_closed`、`lines[]` 含 `received_milli`、`receipts[]` 含 `stock_move_id`/`returnable_milli`、`returns[]`、付款明细按岗位可见性） |
| result | `POST /api/procurement/orders` | — | 原采购单创建响应 |
| result / receipt | `POST /api/procurement/orders/{case_id}/actions/{action}` | `{'case_id','action'}` | 原动作响应；回执族 `request_digest('procurement_'+operation, payload)` |

八个原动作：`approve` / `close_receiving` / `receive` / `pay` / `return_request` / `return_approve` / `return_dispatch` / `refund`。

事实键与满足条件：
- `procurement.receipt_recorded`：必须**同时**有原 `PurchaseReceipt` 与原 `StockMove`（`stock_move_id` 为正整数）；**关闭收货余量不满足实收键**；理由明确"一笔不等于全部行完成"。
- `procurement.return_posted`：本单原退货过账且**指向原收货批次**；引用形状未登记时返回未知，不猜。
- `procurement.payment_recorded`：本单原 `PurchasePayment` 且带**实际付款来源**；收货或应付不满足本键，金额岗位不可见时未知。

## 3. 实测结论

运行 `20260928T133741Z-092a9feee6`：`status=passed`，`phase_complete=true`（源码指纹 `d04af44e4200d64bc3b474d9edf1bbda6b32ec3e65abe4b03f74f171ff507819`）。

- `tests/runtime_domains/test_material_procurement.py`：**8 项通过**。覆盖三条 operation 在 reviewed catalog、`procurement_` 回执前缀与八个原动作、四个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照单次 GET、跨店/ID 不一致 502、无门店身份 403、上游 503、动作可用性 `unknown`；三条事实的满足/未满足/未知分支（含"只有收货单没有库存移动不算实收""关闭收货余量不满足实收键""退货引用形状未登记必须未知""收货或应付不满足实际付款键"四条显式断言）；未登记事实不猜；`extract_result` 边界；回执族保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 同指纹回归：M7.4.3（retail_group_payment）仍通过。本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `material_procurement` 一个适配器；M7.5.2 起 37 个小项仍为 `todo`，按编号串行。
- 付款类事实只到"单笔实际付款来源"，整单付清仍以原财务事实为准；退货引用键以原详情实际提供的为准。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
