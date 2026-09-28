# M7.9.2 编码审阅与实测记录（库存期间报表适配器）

2026-09-28，集中测试阶段。M7.9 组第二项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/stock_period_report.py`：`StockPeriodReportAdapter(FlowCaseAdapter)`，`object_types=('report_query',)`；受控只读读取原语 `read_period_report(principal, date_from, date_to, item_id)`；`fact_keys=()` |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='stock_period_report', object_types=(PERIOD_OBJECT_TYPE,), operation_ids=(GET /api/stock-reports/period,), fact_keys=(), fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_stock_period_report.py`（6 项） |
| 未改动 | 原 `stock_report_api.py`、`stock_reports.py`、`warehouse_period_analytics.py`、迁移、权限表与报表口径；未新增 signal hook；**未注册任何写 operation** |

## 2. 结论摘要（先读）

本领域在 reviewed catalog 内**只有一条只读 operation**（`GET /api/stock-reports/period`）；
原 `/period/export` **未登记**，适配器只把它写成常量与说明，**绝不调用**（套件断言不出现该调用）。
按计划 **`fact_keys=()`**：不注册任何事实键，**期末数字不生成库存交接完成事实**。
`read_snapshot` 对员工本人的查询对象明确报告"**冻结期间与筛选由核心运行时提供**"（503 + 零读取）。

## 3. 确定映射表（从 reviewed catalog 与原签名核对）

| 用途 | operation_id | path_args / query | 原响应 |
|---|---|---|---|
| 期间报表读取 | `GET /api/stock-reports/period` | 无 path_args；query 可选 `date_from` / `date_to` / `item_id`（原签名 `item_id: int | None = Query(None, gt=0)`） | 原期间报表结果 |

参数只做**形状校验**（日期 `YYYY-MM-DD`、起止顺序、`item_id` 正整数），语义由原 API 裁定；
**未传参数时不臆造筛选**（套件断言空 query）。更多原筛选须由评审扩展参数，不在运行时编造。

## 4. 实测结论

运行 `20260928T140646Z-f87991977b`：`status=passed`，`phase_complete=true`（源码指纹 `3e4693403218a744b98875d407b3f81d8f13828f1da41744db10ea218eadd2d7`）。

- `tests/runtime_domains/test_stock_period_report.py`：**6 项通过**。覆盖：目录内只有期间报表读取、**export 未登记**、无写 operation；原 API 路由与三个参数存在；适配器不动态导入/不写库，**未登记的 export 只作说明、不被调用**；注册 spec 为 `fact_keys=()`、只含期间读取、不抢回退；三个已核对筛选原样透传（含 `item_id`）、空参数不臆造；参数形状六类非法日期 + 四类非法 `item_id` 422、期间顺序 422、无门店身份 403；快照的核心提供查询边界（503 + 零读取 + 引用类型 422）；零事实键与结果恒空、写形状提交 422。

## 5. 实测发现并修复的问题（如实保留）

- 首轮套件把"未使用 export"写成对**源码文本**的否定断言，而适配器在**文档字符串**里正当地说明了该未登记路由，导致误判失败 → 改为断言**不存在该调用**（`_native_reader(PERIOD_UNREGISTERED_EXPORT`）且只调用一次已评审读取；产品代码未改。

## 6. 未完成/未验收（如实登记）

- 本项只完成 `stock_period_report` 一个适配器；M7.9.3 起 22 个小项仍为 `todo`，按编号串行。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
