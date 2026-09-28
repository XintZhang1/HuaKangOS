# M7.1.1 编码审阅与实测记录（售前接待与意向跟进适配器）

2026-09-28，集中测试阶段。M7 章节首项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/lead.py`：`LeadAdapter(FlowCaseAdapter)`，`kind='lead'`、`flow_version=1`；实现 `read_snapshot` / `extract_result` / `read_receipt`（复用父类合同的 reviewed operation 与回执族）与三条登记事实 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='lead', …)`，`operation_ids=(GET /api/flow/cases/{case_id}, POST /api/flow/cases, POST /api/flow/cases/{case_id}/actions/{action})`，`kind_versions=(('case','lead',1),)`、`fact_kind_versions=(('case','lead',1),)`、`fallback_object_types=()`（不抢通用 case 回退） |
| 外部套件 | `V/tests/runtime_domains/test_lead.py`（10 项） |
| 未改动 | 原 `flow_specs.py`/`flow_api.py`/`flow_engine.py`/`flow_case.py`、迁移、权限表、业务公式与状态机；本项不新增 signal hook（复用既有 FlowEvent/Proposal/Grant 唤醒与五分钟补漏） |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应/回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/flow/cases/{case_id}` | `{'case_id': <Case.id>}` | 原 Case 详情（`data` 为原生 payload，导航键由核心保留） |
| result | `POST /api/flow/cases` | — | 原 Case 创建响应（顶层 Case） |
| result / receipt | `POST /api/flow/cases/{case_id}/actions/{action}` | `{'case_id','action'}` | 原动作响应；回执族 `flow_request_receipts`（`flow.request_digest`/`prior_request` 规则） |

事实键与满足条件：`lead.customer_linked`（原详情 `customer_id`/`customer.id` 为正整数才满足，同名客户不默选）、`lead.owner_assigned`（原详情 `owner_id`，缺失时只有真实分派待办的 `assignee_id` 才算）、`lead.reserve_recorded`（必须由原 reserve 结果的车辆订单引用；`follow` 待办结束、状态文字、动作可用性都不能代替，无引用即 `satisfied=None`）。

## 3. 实测结论

运行 `20260928T125128Z-3f52688e9d`：`status=passed`（源码指纹 `c04dde7ea3ec10d8c915e9e0c2e922a6ec919fb68fc9780b3e7476b3f70cd36b`）。

- `tests/runtime_domains/test_lead.py`：10 项通过。覆盖映射在当前 reviewed catalog 与活跃路由中可解析且仍是 `METHOD + route` 形式、动作键与原 `flow_specs` 的 lead 定义一致；注册为静态显式且不动态导入、不写库、不抢通用回退；快照只经单次受控 GET 且只接受 lead（其它 kind 422）；跨店 404、无门店身份 403、上游 502；三条事实的满足/未满足/未知分支与证据引用类型；未登记事实不猜；`extract_result` 只对登记 operation 且仅接受真实成功顶层响应；未绑定回执族时返回 `unsupported`、非法提交快照 422。
- 同指纹回归：M1.4（ORM/迁移一致性）、M0.1、以及 M0.2.B 的 `b04-check_assistant_business`、`b04-check_assistant_plan_upgrade`、`b05-business-02` 全部通过（`20260928T125313Z-26f81596b3`）。

## 4. 实测发现并修复的问题

1. **`read_snapshot` 未按 kind 收口**：首版只重写了事实分支，`read_snapshot` 仍走父类、会把 `order` 等其它 kind 当作 lead 投影。已改为单次受控 GET + `kind` 校验（其它 kind 明确 422）。
2. **reserve 事实读错层级**：原订单引用在详情的内层原生 payload（`data.data.*`），首版只看了顶层，导致真实证据被误判为未知。已同时接受内层原生键与顶层 `links`（仅 `order`/`case` 且为正整数 ID）。
3. **回执夹具缺少冻结提交标识**：`SubmissionSnapshot` 要求 `request_id` 与原生 body 内的值一致；夹具已按真实冻结快照构造。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `lead` 一个适配器；M7.1.2 起与其后 51 个小项仍为 `todo`，按编号串行。
- 真实原库/真实模型/浏览器验收不在本项：属 M8.x。
- `lead.reserve_recorded` 在缺少原 reserve 结果或原事件时按合同返回未知（不会猜成功）；真实回执族绑定由已评审的 flow receipt resolver 提供，本项未新增绑定路径。
