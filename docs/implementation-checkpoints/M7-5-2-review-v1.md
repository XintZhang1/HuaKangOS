# M7.5.2 编码审阅与实测记录（物资采购预付适配器）

2026-09-28，集中测试阶段。M7.5 组第二项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/procurement_prepayment.py`：`ProcurementPrepaymentAdapter(FlowCaseAdapter)`，`object_types=('case',)`；快照只读 `GET /api/procurement/orders/{case_id}`（原采购详情已挂预付款面）；预付款动作仍挂在原采购动作上；`read_receipt` 继续沿采购 flow_req 族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='procurement_prepayment', object_types=('case',), operation_ids=(GET /api/procurement/orders/{case_id}, POST /api/procurement/orders/{case_id}/actions/{action}), fact_keys=PREPAY_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_procurement_prepayment.py`（7 项） |
| 未改动 | 原 `procurement_prepayment_api.py`/`_service.py`/`_models.py`、`procurement_api.py`、迁移、权限表、金额公式、状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/procurement/orders/{case_id}` | `{'case_id': <Case.id>}` | 原采购详情 + 预付款面（`requests[]` 含 `paid_cents`/`valid_until`/`expired`/`decisions[]`、`original_cash[]`、`allocations[]`） |
| result / receipt | `POST /api/procurement/orders/{case_id}/actions/{action}` | `{'case_id','action'}` | 原动作响应（`prepay_request`/`prepay_approve`/`prepay_reject`/`prepay_cancel`/`prepay_expire`/`prepay_pay`）；回执沿采购 flow_req 族 |

事实键与满足条件（**每笔事实保留申请 ID，不能串到另一申请**）：
- `prepayment.approval_recorded`：本单原 `PurchasePrepaymentDecision.action='approve'`；理由带申请 ID 并明确"批准不等于已实际付款"；拒绝决定不满足。
- `prepayment.disbursement_recorded`：该申请已有原实际预付（`paid_cents>0`，对应原 `PurchasePrepaymentDisbursement`/`allocations` 指向真实 `payment_id`）；只证明该申请的一笔，不证明整单结清。
- `prepayment.expiration_recorded`：必须有原 `expire` 决定/成功结果；**仅 `valid_until` 已过（`expired=True`）不制造业务已过账事实**。

## 3. 实测结论

运行 `20260928T133942Z-36bb9fca5b`：`status=passed`，`phase_complete=true`（源码指纹 `febd9b70876c3648f3d32ef106987d25fc9bcd5ff9d535bafcff1354025c2749`）。

- `tests/runtime_domains/test_procurement_prepayment.py`：**8 项通过**。覆盖两条 operation 在 reviewed catalog、四个原 service 守卫/计算函数与六个 `prepay_*` 动作、四个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照单次 GET、跨店/ID 不一致 502、无门店身份 403、上游 503、六个动作可用性 `unknown`；三条事实的满足/未满足分支（含"批准不等于实际付款""拒绝不满足批准键""仅凭日期过期不制造已过账事实""每笔保留申请 ID"四条显式断言）；未登记事实不猜；`extract_result` 边界；回执族保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `procurement_prepayment` 一个适配器；M7.5.3 起 36 个小项仍为 `todo`，按编号串行。
- 预付款面的可见性沿用原服务的门店启用判定（未启用时采购详情不含该面）。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
