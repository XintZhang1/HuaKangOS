# M7.3.2 编码审阅与实测记录（维修工单接车与施工进度适配器）

2026-09-28，集中测试阶段。M7.3 组第二项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/repair_order.py`：`RepairOrderAdapter(FlowCaseAdapter)`，`object_types=('case',)`；快照只读 `GET /api/repair-orders/{case_id}`；`extract_result` 覆盖维修族 operation；`read_receipt` 走 `repair_v3_` 前缀回执族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='repair_order', object_types=('case',), operation_ids=(GET /api/repair-orders/{case_id}, POST /api/repair-orders, POST /api/repair-orders/{case_id}/actions/{action}), fact_keys=REPAIR_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_repair_order.py`（9 项） |
| 未改动 | 原 `repair_api.py`/`repair_service.py`/`repair_models.py`/`repair_material_analytics.py`、迁移、权限表、金额与状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/repair-orders/{case_id}` | `{'case_id': <Case.id>}` | 原维修详情（`state`、`data`（岗位安全投影）、`quotes[]`（含 `revision`/`cancelled`/`authorized`/`price_approved`）、`quality[]`（含 `quote_id`/`passed`）） |
| result | `POST /api/repair-orders` | — | 原维修单创建响应 |
| result / receipt | `POST /api/repair-orders/{case_id}/actions/{action}` | `{'case_id','action'}` | 原动作响应；回执族 `request_digest('repair_v3_'+operation, payload)` |

十一个原动作：`quote` / `price_approve` / `authorize` / `start` / `issue` / `return_material` / `finish` / `quality` / `allocate` / `receive` / `release`。

事实键与满足条件：
- `repair.current_quote_authorized`：当前报价（未取消版本中 `revision` 最大者）有原授权事实；**已取消的高版本不得顶替当前报价**。
- `repair.passed_quality_recorded`：必须当前报价对应的原 `RepairQuality.passed=true`；旧报价的质检记录不算，质检未记录/未通过分别明确未满足。
- `repair.release_recorded`：必须原 `data.released_date` 与 `release_evidence_id` **同时**存在；**质检通过、收款完成、旧版记录都不能替代实际交车**；字段岗位不可见时返回未知而非断言未交车。

## 3. 实测结论

运行 `20260928T132339Z-95f7d86681`：`status=passed`，`phase_complete=true`（源码指纹 `eda2ac9fb122bffad9d548579402e5deb24e8810afeb2b0092677893c7ed2137`）。

- `tests/runtime_domains/test_repair_order.py`：**9 项通过**。覆盖三条 operation 在 reviewed catalog、`repair_v3_` 回执前缀与十一个原动作、`RepairQuote`/`RepairAuthorization`/`RepairQuality` 模型存在、不动态导入/不写库；注册范围与不抢通用回退；快照单次 GET、跨店/ID 不一致 502、无门店身份 403、上游 503，动作名字保留但可用性一律 `unknown`；三条事实的满足/未满足/未知分支（含"已取消高版本不顶替""旧报价质检不算""字段不可见返回未知"三条显式反例）；未登记事实不猜；`extract_result` 边界；回执族保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422；**注册真的到达运行时注册表**（Spy 捕获 `DomainAdapterSpec` 断言对象类型/事实键/operation/不抢回退）。
- 同指纹回归：M7.3.1（service_intake）仍通过。

## 4. 实测发现并修复的问题

1. **项数下限**：首轮 8 项低于登记的 9 项下限，被 `below_registered_minimum` 如实拦截；补"注册到达运行时注册表"的接线断言后为 9 项（该断言比源码文本扫描更强，直接校验注册对象）。
2. **套件真实 NameError**：新断言先后漏导入 `REPAIR_FACTS`、`REPAIR_READ`/`REPAIR_ACTION`，两次由运行器如实判失败；补齐导入后通过（未放宽任何断言）。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `repair_order` 一个适配器；M7.3.3 起 44 个小项仍为 `todo`，按编号串行。
- 原详情不返回动作可用性，十一个动作一律 `unknown`，最终由原 API 裁定。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
