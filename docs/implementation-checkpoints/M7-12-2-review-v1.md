# M7.12.2 编码审阅与实测记录（加装单适配器）

2026-09-28，集中测试阶段。M7.12 组第二项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/addon_order.py`：`AddonOrderAdapter(FlowCaseAdapter)`，`object_types=('case',)`（**key 即原 `Case.id`**）；快照只读 `GET /api/addon-orders/{key}`；三条事实 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='addon_order', object_types=(ADDON_OBJECT_TYPE,), operation_ids=(GET /api/addon-orders/{key}, POST /api/addon-orders, POST /api/addon-orders/{key}/actions/{action}), fact_keys=ADDON_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_addon_order.py`（7 项） |
| 未改动 | 原 `addon_api.py`/`_service.py`/`_models.py`、迁移、权限表、金额与角色可见性（`MONEY`/`COST`）；未新增 signal hook |

## 2. 确定映射表（字段名逐字取自原 `describe()` 投影）

| 用途 | operation_id | path_args | 依据 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/addon-orders/{key}` | `{'key': <原 Case.id>}` | 注册合同：`AddonOrder.id` 与原 `Case.id` 相同；投影含 `kind='addon'`、`flow_version=3`、`state`、`version`、`quote`、`lines`、`dispatches`、`installations`、`inspections`、`rectifications`、`plans`、`return_postings`、`payments`、`acceptances`、`handovers`、`tasks`、`actions` |
| result | `POST /api/addon-orders` | — | 原创建 |
| result / receipt | `POST /api/addon-orders/{key}/actions/{action}` | `{'key','action'}` | 原动作（quote/approve/authorize/dispatch/install/quality/rectify/accept/receive/resolution/return_receive/refund）；回执族 **AddonReceipt**（原 `addon_service._execute`） |

## 3. 事实与边界

- `addon.installation_recorded`：`installations[]` 中存在关联**真实 `dispatch_id`** 的记录（缺 `dispatch_id` → 未满足；缺明细 → 未知）；
- `addon.passed_inspection_recorded`：`inspections[]` 中 `passed=true` **且其 `installation_id` 确在 `installations` 内**（指向不存在的安装 → 未满足）；
- `addon.current_quote_accepted`：**当前报价**（`data.addon_quote_id`，回退 `quote.id`）在 `acceptances[]` 中有同 `quote_id` 条目（**别的报价的接受记录不算**）；
- 三条事实理由均带 **"单批合格不能冒充整版全部完成；处置变更后必须重读原事实"**；
  **每次事实读取都重新调用原详情**（套件断言连续两次事实 = 两次读取，不缓存）；
- **无回执不得猜成功**：未绑定 resolver 时回执为 `unsupported`；写回执使用**冻结的最终提交快照**，`request_id` 绝不重新生成；快照对 `kind != 'addon'` 的响应 422。

## 4. 实测结论

运行 `20260928T143916Z-6ae39360c0`：`status=passed`，`phase_complete=true`（源码指纹 `32f960081d87f1154631f2c91bb6c0d36931543e61a639d127e7c39c1b1f805b`）。

- `tests/runtime_domains/test_addon_order.py`：**7 项通过**。覆盖三条 operation 在目录内、原投影字段名与五个原模型、不动态导入/不写库/不抢回退；注册 spec 恰为三条 operation；快照以 **Case.id** 为 path_args、ID 不一致 502、**别的 kind 422**、无门店身份 403、动作 `unknown`；三条事实的满足/未满足/未知分支（含"缺 dispatch_id 不算安装""质检指向不存在的安装不算""别的报价的接受记录不算""明细缺失未知"四条显式断言）；**事实不缓存（两次读取）**；结果只绑定加装族写入；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422；未登记事实未知。
- 本轮**一次通过，无返工**。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `addon_order` 一个适配器；**M7.12.3 为索引中最后一个 `###` 实现项**，仍为 `todo`。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
