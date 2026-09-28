# M7.7.4 编码审阅与实测记录（组合退回与履约适配器）

2026-09-28，集中测试阶段。M7.7 组第四项，CP-26 起点。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/recharge_bundle.py`：`RechargeBundleAdapter(FlowCaseAdapter)`，`object_types=('case',)`；快照只读 `GET /api/recharge-bundles/orders/{key}`；`read_receipt` 由已评审 resolver 绑定 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='recharge_bundle', object_types=('case',), operation_ids=(GET /api/recharge-bundles/orders/{key}, POST /api/recharge-bundles/orders, POST /api/recharge-bundles/orders/{key}/actions/{action}), fact_keys=RECHARGE_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_recharge_bundle.py`（8 项） |
| 未改动 | 原 `recharge_bundle_api.py`/`_service.py`/`_models.py`、迁移、权限表、组件与金额公式、状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/recharge-bundles/orders/{key}` | `{'key': <Case.id>}` | 原组合单详情 `{'case':…, 'order':…, 'member':…, 'rule':…, 'purchase':…, 'refund':…}` |
| 只读清单 | `GET /api/recharge-bundles/purchases` | — | 原购买清单（登记为只读来源，不作为结果 operation） |
| result | `POST /api/recharge-bundles/orders` | — | 原组合单创建响应 |
| result / receipt | `POST /api/recharge-bundles/orders/{key}/actions/{action}` | `{'key','action'}` | 原动作响应（approve/execute/cancel）；回执由已评审 resolver 绑定 |

两个 purpose：`purchase` / `refund`。

**key 语义**：API 的 `key` 是**原 `Case.id`**（`RechargeBundleOrder.case_id` 指向它）；
套件断言 `path_args={'key': 41}` 即 Case.id，并**显式验证用订单自己的 id（701）作 key 会 502**。

事实键与满足条件：
- `recharge_bundle.purchase_recorded`：本单原 execute 结果指向原 `RechargeBundlePurchase`（须有可识别 id）；缺 id 未知；一笔不代表整单结清。
- `recharge_bundle.refund_posted`：本单原 `RechargeBundleRefundPosting`；**原退款记录未提供过账标记时返回未知**，不把退款申请当过账。
- `recharge_bundle.cancelled`：原 cancel 成功结果与当前原订单状态一致（`state='cancelled'`）。

## 3. 实测结论

运行 `20260928T135125Z-b3855d9148`：`status=passed`，`phase_complete=true`（源码指纹 `a58a284c690dac1a36f34a9a6c3b7c55bee1c829f77f1453ab0a2825ee6fc22b`）。

- `tests/runtime_domains/test_recharge_bundle.py`：**8 项通过**。覆盖四条 operation 在 reviewed catalog、四个原 service 函数、两个 purpose、四个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照 key 语义（Case.id）与"订单 id 作 key 判 502"、未登记 purpose 422、无门店身份 403、上游 503；三条事实的满足/未满足/未知分支（含"缺可识别标识必须未知""无过账标记必须未知且点名 posting""一笔不代表结清"三条显式断言）；未登记事实不猜；`extract_result` 边界（只读清单不绑定）；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `recharge_bundle` 一个适配器；M7.7.5 起 27 个小项仍为 `todo`，按编号串行。
- 退回过账在详情未提供过账标记时按合同未知；金额与组件拆分仍以原接口为准。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
