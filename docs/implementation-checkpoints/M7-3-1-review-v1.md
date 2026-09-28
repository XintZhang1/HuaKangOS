# M7.3.1 编码审阅与实测记录（维修预约与实际到店接待适配器）

2026-09-28，集中测试阶段。M7.3 组首项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/service_intake.py`：`ServiceIntakeAdapter(FlowCaseAdapter)`，`object_types=('service_appointment',)`；快照只读 `GET /api/service-intake/appointments/{key}`；`extract_result` 覆盖预约族 operation；`read_receipt` 走 `IntakeReceipt` 族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='service_intake', object_types=('service_appointment',), operation_ids=(GET /api/service-intake/appointments/{key}, POST /api/service-intake/appointments, POST /api/service-intake/appointments/{key}/actions/{action}), fact_keys=INTAKE_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_service_intake.py`（9 项） |
| 未改动 | 原 `service_intake_api.py`/`_service.py`/`_models.py`、迁移、权限表、资源占用与状态机；未新增 signal hook；未占用任何资源 |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/service-intake/appointments/{key}` | `{'key': <ServiceAppointment.id>}` | 原预约详情（`status`、`arrived_at`（原 ArrivalFact）、`repair_case_id`、车辆与工位引用） |
| result | `POST /api/service-intake/appointments` | — | 原预约创建响应 |
| result / receipt | `POST /api/service-intake/appointments/{key}/actions/{action}` | `{'key','action'}` | 原动作响应；回执族 `IntakeReceipt`（`request_digest('intake_'+operation, payload)`） |

六个原动作：`reschedule` / `cancel` / `no_show` / `arrive` / `leave` / `convert`。

事实键与满足条件：
- `intake.arrival_recorded`：必须由原 `ArrivalFact` 确证（详情 `arrived_at` 非空），并保留到店时间；**资源占用不等于实际到店**。
- `intake.repair_converted`：必须与原维修单引用（`repair_case_id`）吻合；有预约、有资源占用都不算已转维修。
- `intake.cancelled`：重读原预约状态确为 `cancelled`；**`no_show`（未到）明确不等于取消**。

## 3. 实测结论

运行 `20260928T131920Z-f1898bd604`：`status=passed`，`phase_complete=true`（源码指纹 `2df2c8248fa906d35ccfc1ee7a7a2f4540dc2aca37ba1f89ca07895d4e79bb1e`）。

- `tests/runtime_domains/test_service_intake.py`：**9 项通过**。覆盖三条 operation 在 reviewed catalog 内、`intake_` 回执前缀与六个原动作、`ServiceAppointment`/`ArrivalFact`/`RepairIntake`/`IntakeReceipt` 模型存在、适配器不动态导入/不写库；注册范围与对象类型、不抢通用回退；快照单次 GET、引用 ID 不一致 502、**缺车辆引用 502（不补默认值）**、无门店身份 403、上游 503；引用类型四类非法输入 422；三条事实的满足/未满足分支（含"资源占用不等于到店"与"no_show 不等于取消"的显式断言）与转维修单的证据引用；未登记事实不猜；`extract_result` 边界；回执族保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 同指纹回归：M7.2.3（vehicle_import_batch）仍通过。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `service_intake` 一个适配器；M7.3.2 起 45 个小项仍为 `todo`，按编号串行。
- 原详情不返回动作可用性列表，因此快照的六个动作一律 `availability='unknown'`（合同第 6 条：仅岗位筛选的动作名不能当作已验证条件），最终可用性仍由原 API 裁定。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
