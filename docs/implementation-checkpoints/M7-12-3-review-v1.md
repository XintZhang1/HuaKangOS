# M7.12.3 编码审阅与实测记录（代办及其他客户服务单适配器）

2026-09-28，集中测试阶段。**M7.12 组收官项，也是索引中最后一个可领取的实现项。**

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/service_order.py`：`ServiceOrderAdapter(FlowCaseAdapter)`，`object_types=('case',)`（**key 即原 `Case.id`**）；快照只读 `GET /api/service-orders/{case_id}`；三条事实 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='service_order', object_types=(SVC_OBJECT_TYPE,), operation_ids=(GET /api/service-orders/{case_id}, POST /api/service-orders, POST /api/service-orders/{case_id}/actions/{action}), fact_keys=SVC_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_service_order.py`（7 项） |
| 未改动 | 原 `service_orders_api.py`/`_service.py`/`_models.py`、迁移、权限表、行净额/已付与代收代付口径；未新增 signal hook |

## 2. 确定映射表（字段名逐字取自原 `describe()` 投影）

| 用途 | operation_id | path_args | 依据 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/service-orders/{case_id}` | `{'case_id': <原 Case.id>}` | 投影含 `state`/`version`、`lines[]`（`line_key`、`charge_cents`、`paid_cents`、`fulfilled`）、`tenders[]`、`plans[]`（含 `refunds`）、`submissions[]` |
| result | `POST /api/service-orders` | — | 原创建 |
| result / receipt | `POST /api/service-orders/{case_id}/actions/{action}` | `{'case_id','action'}` | 原动作（quote/approve/authorize/submit/external_result/fulfill/receive/disburse/termination/refund）；回执族 **ServiceRequest** |
| 不登记 | `POST /api/service-orders/income-items`、`POST /api/service-orders/payees` | — | 虽已评审但**非本单作用域**：适配器不登记、**不调用**（收入项/收款方属对应能力） |

## 3. 事实与边界

- `service.submission_recorded`：`submissions[]` 有可识别原提交；空 → 未满足；缺明细 → 未知；
- `service.external_approved`：**只认最新提交**（`id` 最大者）的结果为 `approved`；
  最新提交结果非 approved → **未满足**（**旧提交的 approved 不能当当前项目结果**，套件显式验证）；
  结果的 `submission_id` 与最新提交不一致 → **未知**；缺结果明细/缺 outcome → 未知；
- `service.fulfillment_recorded`：`lines[]` 中 `fulfilled=true` **且带可识别 `line_key`**；缺 `line_key` → 未知；
- 三条事实理由均带 **"至少一项履约不代表全部项目或款项完成"**；
- **无回执不得猜成功**：未绑定 resolver 即 `unsupported`；写回执使用**冻结的最终提交快照**，`request_id` 绝不重新生成。

## 4. 实测结论

运行 `20260928T144109Z-1e2bcfe806`：`status=passed`，`phase_complete=true`（源码指纹 `c98db01ad64bedea17d0770cf518a8e9c2ea0b0c915e1470bbc3ade9697f17ac`）。

- `tests/runtime_domains/test_service_order.py`：**7 项通过**。覆盖本单族三条 operation 在目录内、原投影字段与五个原模型、不动态导入/不写库/不抢回退、**income-items/payees 不被调用**；注册 spec 恰为本单三条 operation；快照以 **Case.id** 为 path_args、ID 不一致 502、无门店身份 403、对象类型必须 `case`；三条事实的满足/未满足/未知分支（含"旧提交 approved 不算""submission_id 不一致未知""缺 line_key 未知"三条显式断言）；结果只绑定本单族写入；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422；未登记事实未知。
- 本轮经历 **2 次如实拦截**（1 处夹具笔误 + 1 处源码字面断言过严），均按真实契约修正（**产品代码未改**）。

## 5. 里程碑意义与未验收边界（如实登记）

- **M7.1.1—M7.12.3 全部实现并逐项外部实测通过**；索引中不再有 `###` 级实现项。
- 剩余 `todo` 条目均为 **M8.x 验收/交接类**（真实浏览器、真实模型、PostgreSQL、Linux、故障演练、
  员工试用、发布候选等），按 AGENTS.md 属**集中测试阶段与真实环境条件**，需对应环境与人员；
  本阶段不虚构其完成。
- 真实原库、真实模型、浏览器与员工试用仍属 M8.x。
