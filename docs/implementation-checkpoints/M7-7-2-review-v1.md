# M7.7.2 编码审阅与实测记录（集团本金与权益适配器）

2026-09-28，集中测试阶段。M7.7 组第二项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/group_principal.py`：`GroupPrincipalAdapter(FlowCaseAdapter)`，`object_types=('group_member',)`；快照只读 `GET /api/group/members/{member_id}`；`read_receipt` 走集团回执族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='group_principal', object_types=(MEMBER_OBJECT_TYPE,), operation_ids=(GET /api/group/members/{member_id}, POST /api/group/benefits/members/{member_id}/actions/{action}), fact_keys=MEMBER_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_group_principal.py`（9 项） |
| 未改动 | 原 `group_api.py`/`group_service.py`/`group_models.py`、迁移、权限表、金额公式与状态机；未新增 signal hook；未改 `store_id` |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/group/members/{member_id}` | `{'member_id': <GroupMember.id>}` | 原会员详情（`member`、`entries[]`、`reservations[]`、退款记录；流水按原 `limit(100)` 截断） |
| result / receipt | `POST /api/group/benefits/members/{member_id}/actions/{action}` | `{'member_id','action'}` | 原动作响应；集团回执族 `GroupReceipt` |

八个原 command：`topup` / `reserve` / `capture` / `release` / `reverse` / `refund_request` / `refund_approve` / `refund`（以原 service 为准，套件逐项断言）。

事实键与满足条件（**任意一笔流水只证明存在，不能当作某单已结清**）：
- `group_principal.entry_recorded`：该会员原 `GroupEntry` 且保留 `kind`/金额与来源；缺 kind 时未知；**达到原 100 条分页上限时在理由中如实说明截断**。
- `group_principal.reservation_recorded`：该会员原 `GroupReservation`；理由明确"占用不代表已核销或已结清"。
- `group_principal.refund_recorded`：**原 refund 成功结果与原资金退回账目必须一致**；仅申请/审批（无可见资金账目）返回未知，不冒充实际退回。

## 3. 实测结论

运行 `20260928T134846Z-28b9dc6c02`：`status=passed`，`phase_complete=true`（源码指纹 `acebc011468eaf5b7a1dce7ed7d804c55265bfd745fbbe3064f48c5e4ac71f92`）。

- `tests/runtime_domains/test_group_principal.py`：**9 项通过**。覆盖两条 operation 在 reviewed catalog、四个原 service 函数与八个 command、原 `limit(100)` 分页事实、五个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照单次 GET、ID 不一致 502、无门店身份 403、上游 503、动作可用性 `unknown`；引用类型四类非法输入 422；三条事实的满足/未满足/未知分支（含"一笔不代表已结清""缺 kind 必须未知""分页上限必须如实说明""仅批准不满足实际退回键"四条显式断言）；未登记事实不猜；`extract_result` 边界；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `group_principal` 一个适配器；M7.7.3 起 28 个小项仍为 `todo`，按编号串行。
- 资金类事实只到"单笔存在/实际退回"，整单结清仍以原财务事实为准；详情分页上限以原 `limit(100)` 为准。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
