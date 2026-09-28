# M7.3.5 编码审阅与实测记录（维修出厂与真实进出厂时间适配器）

2026-09-28，集中测试阶段。M7.3 组第五项，CP-20 收官项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/gate_visit.py`：`GateVisitAdapter(FlowCaseAdapter)`，`object_types=('gate_visit',)`；快照只读 `GET /api/gate-visits/{key}`；`extract_result` 覆盖进出厂族六条 operation；`read_receipt` 由已评审的 flow receipt resolver 绑定 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='gate_visit', object_types=('gate_visit',), operation_ids=(GET /api/gate-visits/{key}, POST /api/gate-visits, POST /api/gate-visits/{key}/actions/{action}, POST /api/gate-visits/{key}/corrections, POST /api/gate-visits/corrections/{key}/actions/{action}, POST /api/gate-visits/repair-orders/{key}/departure), fact_keys=GATE_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_gate_visit.py`（8 项） |
| 未改动 | 原 `gate_visit_api.py`/`gate_visit_service.py`/`gate_visit_models.py`（含 `gate_attendance.py`/`gate_visit_integrity.py`/`gate_visit_reporting.py`）、迁移、权限表与状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/gate-visits/{key}` | `{'key': <GateVisit.id>}` | 原进出厂详情（`status`、纠正后有效 `arrived_at`/`left_at`、`voided`、`handoff_appointment_id`、`actions`） |
| result | `POST /api/gate-visits` | — | 原登记创建响应 |
| result / receipt | `POST /api/gate-visits/{key}/actions/{action}`、`POST /api/gate-visits/{key}/corrections`、`POST /api/gate-visits/corrections/{key}/actions/{action}`、`POST /api/gate-visits/repair-orders/{key}/departure` | `{'key','action'}` | 原动作/纠正/出厂响应；回执由已评审 resolver 绑定 |

五个原动作：`arrive` / `leave` / `cancel` / `handoff` / `correct`。

事实键与满足条件：
- `gate.arrival_recorded`：原 `arrive` 确证的 `arrived_at` 存在，且按原纠正读法仍有效（`voided` 为真即视为作废）；**计划日期不满足**。
- `gate.departure_recorded`：原 `leave` 确证的 `left_at` 存在且未被纠正作废；**取消或计划都不满足离场键**。
- `gate.handoff_recorded`：原 `GateHandoff` 引用的实际维修接待（接待引用为正整数）。

## 3. 实测结论

运行 `20260928T132917Z-2ce68f4fa8`：`status=passed`，`phase_complete=true`（源码指纹 `2b6f7a3af2fe7599c860745a9e867079395069d847a073527618c1414c7a3ab3`）。

- `tests/runtime_domains/test_gate_visit.py`：**8 项通过**。覆盖六条 operation 在 reviewed catalog、五个原动作与原纠正有效值读法（`effective(`）、`GateVisit`/`GateFact`/`GateCorrection`/`GateHandoff` 模型存在、不动态导入/不写库；**注册到达运行时注册表**（Spy 捕获 spec）；快照单次 GET、ID 不一致 502、**缺车辆引用 502（不补默认值）**、无门店身份 403、上游 503、动作可用性 `unknown`；引用类型四类非法输入 422；三条事实的满足/未满足分支（含"计划日期不满足到厂键""纠正作废优先""取消不满足离场键"三条显式断言）；未登记事实不猜；`extract_result` 边界；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 同指纹回归：M7.3.4（claim_order）仍通过。本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- CP-20（M7.3.4—M7.3.5）两项适配器均已 implemented 并实测；`released` 仍不记，因为真实原库、真实模型、浏览器与员工试用属 M8.x。
- 动作可用性仍由原 API 裁定（详情只给岗位筛选的动作名）。
- 其余 M7 小项（M7.4.1 起）与 M8.x 按编号串行。
