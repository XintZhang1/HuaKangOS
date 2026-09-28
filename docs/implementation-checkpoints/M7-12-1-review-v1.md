# M7.12.1 编码审阅与实测记录（保险单适配器）

2026-09-28，集中测试阶段。M7.12 组首项。前置侦察见 `M7-12-1-recon-note.md`。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/insurance_order.py`：`InsuranceOrderAdapter(FlowCaseAdapter)`，`object_types=('case',)`（**key 即原 `Case.id`**）；快照只读 `GET /api/insurance-orders/{case_id}`；三条事实 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='insurance_order', object_types=(INS_OBJECT_TYPE,), operation_ids=(GET /api/insurance-orders/{case_id}, POST /api/insurance-orders, POST /api/insurance-orders/{case_id}/actions/{action}), fact_keys=INS_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_insurance_order.py`（7 项） |
| 未改动 | 原 `insurance_api.py`/`_service.py`/`_models.py`/`insurance_finance.py`、迁移、权限表、资金事实与佣金口径；未新增 signal hook；**未使用** `POST /api/observation-corrections/insurance/{case_id}/sync` |

## 2. 确定映射表（逐字核对源码）

| 用途 | operation_id | path_args | 依据 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/insurance-orders/{case_id}` | `{'case_id': <原 Case.id>}` | `@router.get('/{case_id}')` → `describe(get_order(db,user,case_id))`；`get_order` 内 `flow.get_case(db,user,key)` → `_one(db, InsuranceOrder, row.id)` |
| result | `POST /api/insurance-orders` | — | 原创建 |
| result / receipt | `POST /api/insurance-orders/{case_id}/actions/{action}` | `{'case_id','action'}` | 原动作（quote/review/authorize/submit/result/receive/disburse/direct_paid/termination/refund/commission_review） |

## 3. 事实与边界（**附件不参与判定**）

- `insurance.current_quote_consented`：以 `row.data.insurance_quote_id` 指向的**当前报价**为准，
  在 `history[]` 中找到同 `quote.id` 的条目并要求 `authorized is True`；
  **历史里别的报价不能当当前报价的同意**；缺 `authorized`/缺历史/摘要不可判 **一律未知**；无报价引用则**明确未满足**；
- `insurance.external_result_recorded`：需原 `InsuranceResult` 的 `submission_id` 与 `outcome` 同时存在；
  **任意外部结果不能满足已出保**（理由始终声明）；
- `insurance.policy_issued`：**`outcome=issued` 且存在真实 `policy_number`**（空白串不算）；
  `outcome` 非 issued → 明确未满足；issued 但缺保单号 → **未知**；**保费/佣金保持各自原资金事实**；
- 附件证明（`authorization`/`receipt`）**不作为任何事实的满足条件**（侦察记录已固定该边界）。

## 4. 实测结论

运行 `20260928T143757Z-fb0f49b108`：`status=passed`，`phase_complete=true`（源码指纹 `6c6ef7dce093e260053a3958322c5ca97a55098e79a6ca3ddf73561feba1b7ab`）。

- `tests/runtime_domains/test_insurance_order.py`：**7 项通过**。覆盖三条 operation 在目录内、详情路由按 `case_id`、`get_order` 确实经原 case 查询、不动态导入/不写库/不抢回退、**未登记的观察更正同步不被调用**；注册 spec 恰为三条 operation 且 `fallback_object_types=()`；快照以 **Case.id** 为 path_args、ID 不一致 502、无门店身份 403、**对象类型必须是 case**（用 `insurance_order` 类型 422）、动作 `unknown`；同意事实四态（真/未同意假/缺 `authorized` 未知/**历史里别的报价未知**/无报价引用假）；外部结果三态（真/缺 `submission_id` 未知/无结果未知）；出保四态（真/未 issued 假/issued 缺保单号未知/**空白保单号未知**）；结果只绑定保险族写入；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422；未登记事实未知。
- 本轮经历 **1 次如实拦截**：套件断言理由必须含字面 `policy_number`，而实现用中文表述"存在真实保单号" → 按语义修正断言（**产品代码未改**）。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `insurance_order` 一个适配器；M7.12.2、M7.12.3 仍为 `todo`，按编号串行。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
