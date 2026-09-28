# M7.9.1 编码审阅与实测记录（库存报表查询适配器）

2026-09-28，集中测试阶段。M7.9 组首项，CP-28 起点。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/inventory_report.py`：`InventoryReportAdapter(FlowCaseAdapter)`，`object_types=('report_query',)`；受控只读读取原语 `read_report(principal, kind, date_from=None, date_to=None)`；`fact_keys=()` |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='inventory_report', object_types=(REPORT_OBJECT_TYPE,), operation_ids=(GET /api/inventory-reports/{kind}, GET /api/inventory-reports/warehouses/options/{kind}), fact_keys=(), fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_inventory_report.py`（6 项） |
| 未改动 | 原 `inventory_reports_api.py`、`vehicle_operations_analytics.py`、`vehicle_procurement_service.py`、迁移、权限表与报表口径；未新增 signal hook；**未注册任何写 operation** |

## 2. 结论摘要（先读）

本领域**只有只读报表 operation**（套件断言目录内无 `POST/PUT/DELETE`），因此：
- 按计划 **`fact_keys=()`** —— 不注册任何事实键（不注册库存完成、交车或入出库事实）；
- `read_snapshot` 对 `report_query`（员工本人的查询对象）**明确报告边界**：冻结的 kind 与筛选由**核心运行时**提供，
  适配器不读助手自己的对象表、不猜 kind（503 + 说明，套件断言零读取）；
- `extract_result` 恒为空（无写结果可绑定）；`read_receipt` 对写形状提交先按快照校验（GET 不属写回执族 → 422），
  真正的写回执族返回 `unsupported / read_only_report`。

## 3. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args / query | 原响应 |
|---|---|---|---|
| 报表读取 | `GET /api/inventory-reports/{kind}` | `{'kind': <原报表类别>}`，可选 `date_from`/`date_to` | 原报表结果（期间筛选由原 API 裁定） |
| 仓库选项 | `GET /api/inventory-reports/warehouses/options/{kind}` | `{'kind'}`，可选 `q` | 原选项读取 |

**kind 存在性由原 API 裁定**（套件验证 404 原样透传）；适配器只做形状校验（`^[a-z0-9][a-z0-9_-]{0,63}$`），不枚举业务类别、不扩大目录。

## 4. 实测结论

运行 `20260928T140448Z-8a94844e89`：`status=passed`，`phase_complete=true`（源码指纹 `842a1d8a6b01a389b8666cffd1189678ccc5415f08b2115ba25904bb4b16d286`）。

- `tests/runtime_domains/test_inventory_report.py`：**6 项通过**。覆盖：目录内两条只读路由且无写 operation、原路由存在与期间参数；注册 spec 为 `fact_keys=()`、只含两条只读 operation、不抢回退；`read_report` 原样透传 kind 与期间（可选参数为空时不传）；kind 形状校验六类非法输入 422、期间顺序 422、无门店身份 403、**未知 kind 由原 API 裁定（404 透传）**；快照的核心提供查询边界（503 + 零读取 + 引用类型 422）；零事实键、结果恒空、写形状提交 422。

## 5. 实测发现并修复的问题（全部如实保留）

1. 首轮套件用**源码字面签名**断言原 API（`def report( kind: str, date_from`），实际格式不同而失败 → 改为断言**路由装饰器与期间参数存在**（更稳且仍是真实契约）。
2. 首轮把只读报表的回执期望写成 `unsupported`；实际上写形状提交会在**快照校验**阶段被 422 拒绝（GET 不属写回执族）→ 按真实契约修正断言（产品代码未改）。

## 6. 未完成/未验收（如实登记）

- 本项只完成 `inventory_report` 一个适配器；M7.9.2 起 23 个小项仍为 `todo`，按编号串行。
- CP-28 行在计划中引用 **M7.8.4—M7.8.5**，而正文 M7.8 组只有 M7.8.1—M7.8.3（与 CP-24 同类不一致）；按正文编号顺序继续，不虚构缺失条目。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
