# M7.7.1 编码审阅与实测记录（会员业务单适配器）

2026-09-28，集中测试阶段。M7.7 组首项，CP-25 起点。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/membership_order.py`：`MembershipOrderAdapter(FlowCaseAdapter)`，`object_types=('case',)`；快照只读 `GET /api/membership/orders/{key}`；`read_receipt` 由已评审 resolver 绑定 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='membership_order', object_types=('case',), operation_ids=(GET /api/membership/orders/{key}, POST /api/membership/orders, POST /api/membership/orders/{key}/actions/{action}), fact_keys=MEMBERSHIP_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_membership_order.py`（8 项） |
| 未改动 | 原 `membership_api.py`/`_service.py`/`_models.py`/`membership_points.py`、迁移、权限表、积分与金额公式、状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/membership/orders/{key}` | `{'key': <Case.id>}` | 原会员业务单详情 `{'case':…, 'order':…, 'member':…, 'events':[…]}`（事件按岗位脱敏） |
| result | `POST /api/membership/orders` | — | 原业务单创建响应 |
| result / receipt | `POST /api/membership/orders/{key}/actions/{action}` | `{'key','action'}` | 原动作响应；回执由已评审 resolver 绑定 |

九个原 purpose：`topup` / `benefit_issue` / `card_issue` / `card_loss` / `card_replace` / `renew` / `tier_change` / `renew_refund` / `points_adjust`；三个动作 `approve`/`execute`/`cancel`。

**key 语义（本项关键）**：API 的 `key` 是**原 `Case.id`**（`MembershipOrder.case_id` 指向它）；
套件断言传给原生读取的 `path_args={'key': 51}` 即 Case.id，并显式验证用 `MembershipOrder.id`（901）作 key 会 502。

事实键与满足条件：
- `membership.executed`：**原执行事件与原单状态必须吻合**；只有其一返回未知，两者都无明确未满足。
- `membership.fee_refund_basis_recorded`：原 `MembershipEvent.action='fee_refund_basis'`；**原权限脱敏（仅 `detail.recorded`）时仍承认事实，但理由只复述登记结论，不替原权限开口**。
- `membership.period_linked`：原结果必须明确关联实际周期（`period_id` 等登记键）；未提供即未知。

## 3. 实测结论

运行 `20260928T134722Z-58418d55d4`：`status=passed`，`phase_complete=true`（源码指纹 `985c6bd47496c7fdc5c7cf4c11d194d6e921ed09850907406299d2fb4750f4a5`）。

- `tests/runtime_domains/test_membership_order.py`：**8 项通过**。覆盖三条 operation 在 reviewed catalog、四个原 service 函数与九个 purpose、两个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照用 Case.id 作 key、**用 Order.id 作 key 被判 502**、未登记 purpose 422、无门店身份 403、上游 503；三条事实的满足/未满足/未知分支（含"只有事件或只有状态必须未知""脱敏仍承认事实且不替原权限开口""无周期关联必须未知"三条显式断言）；未登记事实不猜；`extract_result` 边界；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `membership_order` 一个适配器；M7.7.2 起 29 个小项仍为 `todo`，按编号串行。
- 执行/周期的判定沿用原详情的可见字段；`membership.period_linked` 在原详情未提供周期关联时按合同未知。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
