# M7.10.2 编码审阅与实测记录（整车调拨适配器）

2026-09-28，集中测试阶段。M7.10 组第二项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/vehicle_transfer.py`：`VehicleTransferAdapter(FlowCaseAdapter)`，`object_types=('vehicle_transfer',)`；快照只读 `GET /api/vehicle-transfers/{key}`（**key 即原 VehicleTransfer.id**）；`read_receipt` 由已评审 resolver 绑定 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='vehicle_transfer', object_types=(VT_OBJECT_TYPE,), operation_ids=(GET /api/vehicle-transfers/{key}, POST /api/vehicle-transfers, POST /api/vehicle-transfers/{key}/actions/{action}), fact_keys=VT_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_vehicle_transfer.py`（8 项） |
| 未改动 | 原 `vehicle_transfer_api.py`/`_service.py`/`_models.py`、迁移、权限表、车辆保管与结算规则、状态机；未新增 signal hook；未改 `store_id` |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/vehicle-transfers/{key}` | `{'key': <VehicleTransfer.id>}` | 原整车调拨详情（`status`、`vin`、`movements[]`（原 `VehicleMovement`）） |
| 只读目的店 | `GET /api/vehicle-transfers/destinations` | — | 原目的店读取（登记为只读来源，不作为结果 operation） |
| result | `POST /api/vehicle-transfers` | — | 原创建响应 |
| result / receipt | `POST /api/vehicle-transfers/{key}/actions/{action}` | `{'key','action'}` | 原动作响应（dispatch/accept/return_ship/return_receive）；回执由已评审 resolver 绑定 |

十种原状态：`requested`/`approved`/`transit`/`rejected`/`return_transit`/`accepted`/`returned`/`cancelled`/`lost`/`recovered`（未知状态 422）。

事实键与满足条件：
- `vehicle_transfer.accepted`：**原状态 `accepted` 且原 accept/`VehicleMovement` 同 VIN**；状态吻合但无车移动事实 → 未满足；流水缺失 → 未知；VIN 不一致 → **未知**（不当作已完成）。
- `vehicle_transfer.returned`：**原状态 `returned` 且原 return_receive/原车移动事实吻合**；**`rejected` 明确不能满足 returned**（理由点名）。
- `vehicle_transfer.lost`：原状态 `lost`；理由明确"找回或赔偿以原单后续事实为准"，不推断。

## 3. 实测结论

运行 `20260928T141837Z-f0a1a48ba2`：`status=passed`，`phase_complete=true`（源码指纹 `fcc650a6327d5e6396997bbbc5921d2f455e8eb6abf67d75080450d40808dec9`）。

- `tests/runtime_domains/test_vehicle_transfer.py`：**8 项通过**。覆盖四条 operation 在 reviewed catalog、四个原 service 函数、十种原状态、三个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照 key 即调拨单 id、ID 不一致 502、**未登记状态 422**、无门店身份 403；三条事实的满足/未满足/未知分支（含"状态吻合但无车移动不算""流水缺失必须未知""VIN 不一致必须未知""rejected 不能冒充 returned""丢失不推断找回"五条显式断言）；未登记事实不猜；`extract_result` 边界；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮经历 **2 次如实拦截与修复**（见下节），最终通过。

## 4. 实测发现并修复的问题（全部如实保留）

1. 套件把快照展示编号写成 VIN，而实现按原单号（`HKVT41`）展示 → 按实现契约修正断言（产品代码未改）。
2. 修正该断言时的补丁把字面 `\n` 写进了套件文件，`ast.parse` 在同一脚本内立即报错；已用文件式修复脚本还原为两行（**仓库产品代码全程未被污染**）。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `vehicle_transfer` 一个适配器；M7.10.3 起 21 个小项仍为 `todo`，按编号串行。
- 车移动类型/VIN 的判定沿用原详情实际提供的字段；未提供时按合同未知。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
