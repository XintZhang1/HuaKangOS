# M7.8.1 编码审阅与实测记录（预收与结算适配器）

2026-09-28，集中测试阶段。M7.8 组首项，CP-27 起点。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/business_finance_order.py`：`BusinessFinanceOrderAdapter(FlowCaseAdapter)`，`object_types=('case',)`；快照只读 `GET /api/business-finance/orders/{key}`；`read_receipt` 由已评审 resolver 绑定 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='business_finance_order', object_types=('case',), operation_ids=(orders/{key}, POST orders, orders/{key}/actions/{action}), fact_keys=FINANCE_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_business_finance_order.py`（7 项） |
| 未改动 | 原 `business_finance_api.py`/`_service.py`/`_sources.py`/`_models.py`、迁移、权限表、金额与分配公式、状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/business-finance/orders/{key}` | `{'key': <Case.id>}` | 原财务详情 `{'case':…, 'order':…, 'events':[…], 'application'/'advance':…}` |
| 只读来源 | `GET /api/business-finance/sources`（另 advances/receipts/other-returns 已登记） | — | 原来源读取（登记为只读来源，不作为结果 operation） |
| result | `POST /api/business-finance/orders` | — | 原创建响应 |
| result / receipt | `POST /api/business-finance/orders/{key}/actions/{action}` | `{'key','action'}` | 原动作响应（recalculate/approve/execute/cancel）；回执由已评审 resolver 绑定 |

**key 语义**：API 的 `key` 是**原 `Case.id`**（`FinanceOrder.case_id` 指向它）；
套件断言 `path_args={'key': 31}` 即 Case.id，并**显式验证用 `FinanceOrder.id`（501）作 key 会 502**。

事实键与满足条件（**依 purpose 选择实际存在的原事实；不适用键为 unknown**）：
- `finance.executed`：**原 execute 事件与原状态必须吻合**；只有其一返回未知；理由保留原 purpose 且明确"执行成功不代表所有款项完成"。
- `finance.cash_batch_recorded`：本单原 `FinanceCashBatch` 及对应分配；详情未提供（或该 purpose 不适用）时返回**未知**，不推断为未完成。
- `finance.correction_recorded`：本单原 `FinanceCorrection` 或原明确更正结果；同上按未知处理。

## 3. 实测结论

运行 `20260928T135629Z-7d6fb61959`：`status=passed`，`phase_complete=true`（源码指纹 `ba748f5b4030bde5a1f9b78d89df53840388ed3a0db8886fc9015ca396dc8882`）。

- `tests/runtime_domains/test_business_finance_order.py`：**7 项通过**。覆盖四条 operation 在 reviewed catalog、四个原 service 函数、四个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照 key 语义（Case.id）与"订单 id 作 key 判 502"、无门店身份 403、上游 503；三条事实的满足/未满足/未知分支（含"只有事件或只有状态必须未知""执行成功不代表所有款项完成且保留 purpose""不适用键不推断为未完成"三条显式断言）；引用类型四类非法输入 422；未登记事实不猜；`extract_result` 边界（来源读不绑定）；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮**一次如实拦截 + 一次返工**：首轮 7 项低于派生登记的 8 项下限，被 `below_registered_minimum` 判不完整；按实际规模对齐为 7 后通过（未虚增断言）。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `business_finance_order` 一个适配器；M7.8.2 起 26 个小项仍为 `todo`，按编号串行。
- 现金批次与更正事实在详情未提供时按合同未知；金额与分配仍以原接口为准。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
