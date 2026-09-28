# M7.9.5 编码审阅与实测记录（到店活动统计适配器）

2026-09-28，集中测试阶段。M7.9 组第五项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/visit_activity_report.py`：`VisitActivityReportAdapter(FlowCaseAdapter)`，`object_types=('report_query',)`；受控只读读取原语 `read_visit_report(principal, date_from, date_to, case_id)`；`fact_keys=()` |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='visit_activity_report', object_types=(VISIT_OBJECT_TYPE,), operation_ids=(GET /api/visit-activity-reports,), fact_keys=(), fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_visit_activity_report.py`（6 项） |
| 未改动 | 原 `visit_activity_api.py`、`visit_activity_analytics.py`、迁移、权限表与口径；未新增 signal hook；**未注册任何写 operation** |

## 2. 结论摘要（先读）

本领域在 reviewed catalog 内**只有一条只读 operation**（`GET /api/visit-activity-reports`）；
原 `/export/{key}` **未登记**，适配器只作常量与说明、**绝不被调用**。
按计划 **`fact_keys=()`**：不注册任何事实键——**统计数字不生成接待、成交或结清事实**。
`read_snapshot` 对员工本人的查询对象明确报告"**冻结范围与期间由核心运行时提供**"（503 + 零读取）。

## 3. 确定映射表（从 reviewed catalog 与原签名核对）

| 用途 | operation_id | path_args / query | 原响应 |
|---|---|---|---|
| 到店活动统计读取 | `GET /api/visit-activity-reports` | 无 path_args；query 可选 `date_from` / `date_to` / `case_id`（原签名 `case_id: int | None = Query(None, gt=0)`） | 原统计结果 |

**原接口只有这三个筛选参数**（已逐字核对签名，没有额外的范围参数）；参数只做形状校验（日期 `YYYY-MM-DD`、
起止顺序、`case_id` 正整数），语义由原 API 裁定；**未传参数时不臆造筛选**（套件断言空 query）。

## 4. 实测结论

运行 `20260928T141041Z-caa5c83e3b`：`status=passed`，`phase_complete=true`（源码指纹 `da31c73f92afb4541e6c1235f6135c773182924307bbd3a492a42f3fc1233c08`）。

- `tests/runtime_domains/test_visit_activity_report.py`：**6 项通过**。覆盖：目录内只有统计读取、**export 未登记**、无写 operation；原 API 路由与三个参数存在；不动态导入/不写库、export 不被调用且只调用一次已评审读取；注册 spec 为 `fact_keys=()`、只含统计读取、不抢回退；三个筛选原样透传、空参数不臆造；参数形状（五类非法日期 + 四类非法 case_id）422、期间顺序 422、无门店身份 403；快照的核心提供查询边界（503 + 零读取 + 引用类型 422）；零事实键、结果恒空、**统计数字不生成接待/成交/结清事实**、写形状提交 422。
- 本轮**一次通过，无返工**。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `visit_activity_report` 一个适配器；M7.9.6 起 19 个小项仍为 `todo`，按编号串行。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
