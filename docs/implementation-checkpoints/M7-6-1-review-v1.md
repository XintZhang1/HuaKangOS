# M7.6.1 编码审阅与实测记录（客户档案与服务单适配器）

2026-09-28，集中测试阶段。M7.6 组首项，CP-23 起点。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/customer_vehicle.py`：`CustomerVehicleAdapter(FlowCaseAdapter)`，`object_types=('customer_vehicle',)`；快照只读 `GET /api/customer-service/vehicles/{vehicle_id}`；历史关联只读同族 `.../history`；`read_receipt` 沿客户服务族回执 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='customer_vehicle', object_types=(VEHICLE_OBJECT_TYPE,), operation_ids=(vehicles/{vehicle_id}, vehicles/{vehicle_id}/history, POST vehicles, observations, history-links), fact_keys=VEHICLE_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_customer_vehicle.py`（9 项） |
| 未改动 | 原 `customer_service_api.py`/`customer_service.py`/`customer_service_models.py`、迁移、权限表、观察纠正规则与状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/customer-service/vehicles/{vehicle_id}` | `{'vehicle_id': <CustomerVehicle.id>}` | 原车辆详情（`vin`/`status`/`customer_id` + 客户名与联系方式 + 经原观察纠正后的有效值） |
| 事实（历史关联） | `GET /api/customer-service/vehicles/{vehicle_id}/history` | `{'vehicle_id'}` | 原历史关联清单（`ServiceHistoryLink`） |
| result / receipt | `POST /api/customer-service/vehicles`、`POST .../vehicles/{vehicle_id}/observations`、`POST .../vehicles/{vehicle_id}/history-links` | — | 原创建/观察/关联响应；客户服务族回执 |

事实键与满足条件：
- `customer_vehicle.customer_linked`：原详情 `customer_id` 为正整数（详情同时带客户名/联系方式即表示可读）；缺失明确未满足。
- `customer_vehicle.history_link_recorded`：`.../history` 返回与该车辆一致的 `ServiceHistoryLink`；**理由明确"历史关联不证明仍能读取关联原单正文"**；不一致的关联不满足；返回形状无法判定时未知。
- `customer_vehicle.observation_recorded`：必须原 `VehicleObservation` 且保留**观察类型/日期/来源**；**车辆详情未提供观察清单时返回未知**（不猜），缺日期不视为完整。

## 3. 实测结论

运行 `20260928T134244Z-c02e2075c7`：`status=passed`，`phase_complete=true`（源码指纹 `589f175fc1df52a3ce06f3a7c230361097801a3ce4cfae8d05d065e6fc83c176`）。

- `tests/runtime_domains/test_customer_vehicle.py`：**9 项通过**。覆盖五条 operation 在 reviewed catalog、四个原 service 函数、四个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照单次 GET、ID 不一致 502、无门店身份 403、上游 503、动作可用性 `unknown`；引用类型四类非法输入 422；三条事实的满足/未满足/未知分支（含"历史关联不证明可读原单正文""不一致关联不满足""详情未提供观察清单必须未知""缺观察日期不算完整"四条显式断言）；未登记事实不猜；`extract_result` 边界（历史读不作为结果 operation、缺 id 不绑定）；回执族保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `customer_vehicle` 一个适配器；M7.6.2 起 34 个小项仍为 `todo`，按编号串行。
- 观察记录事实在车辆详情未暴露观察清单时按合同未知；需要评审补一条已评审的观察读取路径后才可判定。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
