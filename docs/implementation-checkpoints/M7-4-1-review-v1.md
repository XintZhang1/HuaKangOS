# M7.4.1 编码审阅与实测记录（精品销售与套餐适配器）

2026-09-28，集中测试阶段。M7.4 组首项，CP-21 起点。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/retail_order.py`：`RetailOrderAdapter(FlowCaseAdapter)`，`object_types=('case',)`；快照只读 `GET /api/retail/orders/{key}`；`extract_result` 覆盖精品族三条 operation；`read_receipt` 走 `retail_` 前缀回执族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='retail_order', object_types=('case',), operation_ids=(GET /api/retail/orders/{key}, POST /api/retail/orders, POST /api/retail/orders/{key}/actions/{action}), fact_keys=RETAIL_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_retail_order.py`（9 项） |
| 未改动 | 原 `retail_api.py`/`retail_service.py`/`retail_models.py`、迁移、权限表、金额公式与状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/retail/orders/{key}` | `{'key': <Case.id>}` | 原精品详情（`state`、`lines[]`、`dispatches[]` 含 `line_id`/`quantity_milli`/`returned_milli`、`returns[]`、`data`、`installation_policy`） |
| result | `POST /api/retail/orders` | — | 原精品单创建响应 |
| result / receipt | `POST /api/retail/orders/{key}/actions/{action}` | `{'key','action'}` | 原动作响应；回执族 `request_digest('retail_'+operation, payload)` |

十一个原动作：`approve` / `authorize` / `dispatch` / `install` / `accept` / `receive` / `return_request` / `return_approve` / `return_handback` / `return_rectify` / `return_receive`。

事实键与满足条件：
- `retail.dispatch_recorded`：本单存在原 `RetailDispatch` 且带原行引用（`line_id`）；理由明确"**至少一行，整单是否出齐以原单逐行为准**"。
- `retail.accept_recorded`：必须原单实际接收事实（登记键 `accepted_at`/`accepted_date`/`accepted`/`received_at`）；**该详情未提供或岗位不可见时返回未知**，不用出库或安装代替。
- `retail.return_posted`：必须原 `RetailReturnPosting` 确证的退回数量（详情 `returned_milli > 0`）；仅出库未退回明确未满足。

## 3. 实测结论

运行 `20260928T133123Z-01de12d08c`：`status=passed`，`phase_complete=true`（源码指纹 `d15f568c5517a70997600159af85d13e660f6293f4110b1b727e32e64e171b31`）。

- `tests/runtime_domains/test_retail_order.py`：**9 项通过**。覆盖三条 operation 在 reviewed catalog、`retail_` 回执前缀与十一个原动作、`RetailDispatch`/`RetailReturnPosting`/`RetailReturn`/`RetailLine` 模型存在、不动态导入/不写库/不抢通用回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照单次 GET、跨店/ID 不一致 502（不补默认门店）、无门店身份 403、上游 503、动作可用性 `unknown`；引用类型四类非法输入 422；三条事实的满足/未满足/未知分支（含"一行不代表整单出齐""缺原单接收事实必须未知""仅出库不满足退回键"三条显式断言）；未登记事实不猜；`extract_result` 边界；回执族保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 同指纹回归：M7.3.5（gate_visit）仍通过。本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `retail_order` 一个适配器；M7.4.2 起 40 个小项仍为 `todo`，按编号串行。
- 动作可用性仍由原 API 裁定（详情只给岗位筛选的动作名）。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
