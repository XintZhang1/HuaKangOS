# M7.9.4 编码审阅与实测记录（物资价值统计适配器）

2026-09-28，集中测试阶段。M7.9 组第四项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/material_value_report.py`：`MaterialValueReportAdapter(FlowCaseAdapter)`，`object_types=('report_query',)`；受控只读读取原语 `read_value_report(principal, date_from, date_to, source, item_id)`；`fact_keys=()` |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='material_value_report', object_types=(VALUE_OBJECT_TYPE,), operation_ids=(GET /api/material-value,), fact_keys=(), fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_material_value_report.py`（6 项） |
| 未改动 | 原 `material_value_api.py`、`material_value_analytics.py`、`retail_bundle_analytics.py`、迁移、权限表与口径；未新增 signal hook；**未注册任何写 operation** |

## 2. 结论摘要（先读）

本领域在 reviewed catalog 内**只有一条只读 operation**（`GET /api/material-value`）；
原 `/export/{key}` **未登记**（计划亦明确"不调用 /export"），适配器只作常量与说明、**绝不被调用**。
按计划 **`fact_keys=()`**：不注册任何事实键——**报表数字不生成结算、收款或结清事实**。
`read_snapshot` 对员工本人的查询对象明确报告"**冻结筛选由核心运行时提供**"（503 + 零读取）。

## 3. 确定映射表（从 reviewed catalog 与原签名核对）

| 用途 | operation_id | path_args / query | 原响应 |
|---|---|---|---|
| 价值聚合读取 | `GET /api/material-value` | 无 path_args；query 可选 `date_from` / `date_to` / `source` / `item_id`（原签名 `item_id: int | None = Query(None, gt=0)`） | 原聚合结果 |

参数只做**形状校验**（日期 `YYYY-MM-DD`、起止顺序、`source` 短横线小写 slug、`item_id` 正整数），语义由原 API 裁定；
**未传参数时不臆造筛选**（套件断言空 query）。

## 4. 实测结论

运行 `20260928T140923Z-9ead0950e4`：`status=passed`，`phase_complete=true`（源码指纹 `1fe93990def9ea126d163368efe3bf66ed77652d4f0dbceba279d64be7144a20`）。

- `tests/runtime_domains/test_material_value_report.py`：**6 项通过**。覆盖：目录内只有聚合读取、**export 未登记**、无写 operation；原 API 路由与四个参数存在；不动态导入/不写库、export 不被调用且只调用一次已评审读取；注册 spec 为 `fact_keys=()`、只含聚合读取、不抢回退；四个筛选原样透传、空参数不臆造；参数形状（五类非法日期 + 五类非法 source + 四类非法 item_id）422、期间顺序 422、无门店身份 403；快照的核心提供查询边界（503 + 零读取 + 引用类型 422）；零事实键、结果恒空、**报表数字不生成结算/收款/结清事实**、写形状提交 422。
- 本轮**一次通过，无返工**。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `material_value_report` 一个适配器；M7.9.5 起 20 个小项仍为 `todo`，按编号串行。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
