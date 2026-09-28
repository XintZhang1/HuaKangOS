# M7.3.4 编码审阅与实测记录（理赔核赔受理适配器）

2026-09-28，集中测试阶段。M7.3 组第四项，CP-20 起点。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/claim_order.py`：`ClaimOrderAdapter(FlowCaseAdapter)`，`object_types=('case',)`；快照只读 `GET /api/claims/{case_id}`；`extract_result` 覆盖理赔族 operation；`read_receipt` 走 `ClaimReceipt` 族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='claim_order', object_types=('case',), operation_ids=(GET /api/claims/{case_id}, GET /api/claims/{case_id}/options/{action}, POST /api/claims, POST /api/claims/{case_id}/actions/{action}), fact_keys=CLAIM_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_claim_order.py`（8 项） |
| 未改动 | 原 `claims_api.py`/`_service.py`/`_models.py`、迁移、权限表、金额公式与状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/claims/{case_id}` | `{'case_id': <Case.id>}` | 原理赔详情（`state`、`phase`、`amount_cents`、`order`、`data`、来源维修引用、`assessments`/`transmissions`/`results`/`bindings`/`resolutions`） |
| 动作可用性（只读） | `GET /api/claims/{case_id}/options/{action}` | `{'case_id','action'}` | 原动作选项读取，登记为本项可用的只读来源 |
| result | `POST /api/claims` | — | 原理赔单创建响应 |
| result / receipt | `POST /api/claims/{case_id}/actions/{action}` | `{'case_id','action'}` | 原动作响应；回执族 `ClaimReceipt` |

六个原动作：`assess` / `approve` / `transmit` / `result` / `bind` / `resolution`。

事实键与满足条件：
- `claim.transmission_recorded`：本单存在原 `ClaimTransmission`。
- `claim.external_result_recorded`：本单对应提交存在原 `ClaimResult`，**保留原 outcome**，并在理由中明确"结果本身不代表已批准或已收款"——**不把任意结果当批准**。
- `claim.binding_recorded`：原 `ClaimBinding` 必须指明 `payment_route`；缺去向返回未知，且理由明确**核赔或绑定不代表现金已收**。

## 3. 实测结论

运行 `20260928T132759Z-33150cb5d2`：`status=passed`，`phase_complete=true`（源码指纹 `d5c4f445b1d001fdb398cfb01d9b32566d245f3b4069abe0c9e8492031ac843a`）。

- `tests/runtime_domains/test_claim_order.py`：**8 项通过**。覆盖四条 operation 在 reviewed catalog、`claims_` 回执前缀与六个原动作、`ClaimTransmission`/`ClaimResult`/`ClaimBinding`/`ClaimReceipt` 模型存在、不动态导入/不写库；**注册到达运行时注册表**（Spy 捕获 spec，断言对象类型/事实键/operation/不抢回退）；快照单次 GET、ID 不一致 502、**缺原维修来源 502（不补默认值）**、无门店身份 403、上游 503、动作可用性 `unknown`；三条事实的满足/未满足/未知分支（含"保留 outcome 且不代表批准""缺 payment_route 未知""核赔不代表现金已收"三条显式断言）；未登记事实不猜；`extract_result` 边界（只读 options 不属结果 operation）；回执族保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。

## 4. 实测发现并修复的问题

- 派生登记脚本的 `minimum_tests` 未随本项套件规模更新（沿用上一项的 9），首轮被 `below_registered_minimum` 如实拦截；按本项实际 8 项对齐后通过，**未虚增断言**。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `claim_order` 一个适配器；M7.3.5 起 42 个小项仍为 `todo`，按编号串行。
- 动作可用性仍由原 API 裁定（详情只给岗位筛选的动作名）。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
