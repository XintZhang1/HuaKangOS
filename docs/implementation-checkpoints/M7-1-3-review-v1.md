# M7.1.3 编码审阅与实测记录（退订退车及维修退款纠正适配器）

2026-09-28，集中测试阶段。M7 章节第三项，CP-17 收官项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/aftercare.py`：`AftercareAdapter(FlowCaseAdapter)`，`kind='aftercare'`、`flow_version=2`；`read_snapshot` 只读 `GET /api/aftercare/orders/{case_id}`；`extract_result` 覆盖售后族 operation；`read_receipt` 走售后族回执（`aftercare_service._execute` 摘要） |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='aftercare', …)`，`operation_ids=(GET /api/aftercare/orders/{case_id}, POST /api/aftercare/orders, POST /api/aftercare/orders/{case_id}/actions/{action})`，`kind_versions=fact_kind_versions=(('case','aftercare',2),)`、`fallback_object_types=()` |
| 外部套件 | `V/tests/runtime_domains/test_aftercare.py`（9 项） |
| 未改动 | 原 `aftercare_api.py`/`aftercare_service.py`/`aftercare_models.py`/`group_aftercare.py`、迁移、权限表、金额公式与状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/aftercare/orders/{case_id}` | `{'case_id': <Case.id>}` | 原售后单详情（`scenario`、`applied`、`plans[]`、`sources[]` 及执行/金额字段，按原岗位可见性） |
| result | `POST /api/aftercare/orders` | — | 原售后单创建响应（顶层 Case） |
| result / receipt | `POST /api/aftercare/orders/{case_id}/actions/{action}` | `{'case_id','action'}` | 原动作响应；回执族 `AftercareReceipt`（`aftercare_service._execute` 的 `request_digest('aftercare_'+operation, payload)`） |

事实键与满足条件：
- `aftercare.plan_applied`：原详情 `applied === true`（即存在原 `AftercareApplication`）且能引用方案编号；已批准但未生效明确未满足。
- `aftercare.customer_consent_recorded`：原详情存在 `AftercareConsent` 引用（`consent_id`/方案上的 `consent_id`）；缺失即未知。
- `aftercare.cash_refund_recorded`：必须存在本单原 `AftercareCashRefund` 引用；**方案批准、方案生效、集团本金或权益退回都不满足本键**，缺失即未知并提示原单核对。

## 3. 实测结论

运行 `20260928T130312Z-302fe6b28e`：`status=passed`，`phase_complete=true`（源码指纹 `cb48b2d9ef1b2f87300685e47981b5ae227ad02f4404e5a1f9f8a09af3089c87`）。

- `tests/runtime_domains/test_aftercare.py`：9 项通过。覆盖映射在当前 reviewed catalog 与活跃路由中可解析、四个原模型（Application/CashRefund/Consent/Receipt）存在、适配器不动态导入/不写库；注册只按 `flow_version=2` 且不抢通用回退；快照单次 GET、kind 422、scenario 非法 502、ID 不一致 502；跨店 404、无门店身份 403、上游错误透传；三条事实的满足/未满足/未知分支（含"批准或生效不满足实际退款键"的显式断言）；未登记事实不猜；`extract_result` 边界；回执族保持冻结 `request_id`、未绑定为 `unsupported`、非法快照 422。
- 同指纹回归：M7.1.1、M7.1.2 均通过。

## 4. 未完成/未验收（如实登记）

- CP-17（M7.1.1—M7.1.3）三项适配器均已 implemented 并实测；`released` 仍不记，因为真实原库、真实模型、浏览器与员工试用属 M8.x。
- 后续 M7.2.1 起 49 个小项仍为 `todo`，按编号串行。
- 集团本金/权益退回与现金退回是不同事实；本适配器不为前者提供满足键，也不改装机处置等其它领域。
