# M7.9.6 编码审阅与实测记录（经营报表与日报适配器）

2026-09-28，集中测试阶段。M7.9 组收官项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/management_report.py`：`ManagementReportAdapter(FlowCaseAdapter)`，`object_types=('report_query', 'daily_report')`；唯一受控只读原语 `read_flow_analytics(principal)`；`fact_keys=()` |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='management_report', object_types=(MGMT_QUERY_TYPE, MGMT_DAILY_TYPE), operation_ids=(GET /api/flow/analytics,), fact_keys=(), fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_management_report.py`（5 项） |
| 未改动 | 原网关 `business_assistant_gateway.py` 的封闭域与被挡写入清单、原报表/日报接口、迁移与权限表；未新增 signal hook；**未注册任何写 operation** |

## 2. 结论摘要（先读，全部经核对）

1. 计划点名的 `GET /api/dashboard`、`GET /api/reports`、`GET /api/reports/{report_id}` **都不在 reviewed catalog 内**
   （`dashboard`/`reports` 属原网关 `CLOSED_DOMAINS`，GET 亦被过滤）→ **没有已评审读取可用**；
2. 唯一可用已评审只读是 `GET /api/flow/analytics`，已作为受控原语实现；
3. **日报生成写属 `CLASSIFIED_BLOCKED_WRITES`**（原清单为 `POST /api/reports/generate` 与 `POST /api/reports/preview`），
   套件断言二者**真实存在于被挡清单且不在目录内**，适配器**只登记边界、绝不调用**；
4. `fact_keys=()`：不注册任何事实键——**报表/日报数字不生成经营、收款或结清事实**。

## 3. 实测结论

运行 `20260928T141435Z-73ca8ac3b9`：`status=passed`，`phase_complete=true`（源码指纹 `c8b9a19fdda1d481cb10abe25bb6161d4fe79f363dea2bab842717348477caf3`）。

- `tests/runtime_domains/test_management_report.py`：**5 项通过**。覆盖：封闭域三条读取不在目录内且网关确有 `CLOSED_DOMAINS`；被挡写入两条真实存在于清单且不在目录内、适配器不调用；注册 spec 仅含 `GET /api/flow/analytics`、`fact_keys=()`、两种对象类型、不抢回退；只读原语只发一次已评审读取；两条边界（查询对象 → 核心提供查询；日报 → 无读取且写被挡）**零读取**；引用类型四类非法输入 422、无门店身份 403；零事实键（理由含 `CLASSIFIED_BLOCKED_WRITES`）、结果恒空、被挡写入快照返回 `unsupported / read_only_report`、非法快照 422。
- 本轮经历 **4 次如实拦截与修复**（见下节），最终通过。

## 4. 实测发现并修复的问题（全部如实保留）

1. **被挡写入的路由名我猜错了**：先写成 `POST /api/reports/daily`，实际清单是 `POST /api/reports/generate` 与 `/preview` → 读原清单后更正适配器常量与套件断言（**以原清单为准**）。
2. 一次同步补丁把字面换行写进了安装脚本的字符串，`ast.parse` 立即拦截（**仓库与安装脚本未被污染**），改用文件式修复脚本。
3. 回执期望写错：形状合法的被挡写入**不抛异常**而是返回 `unsupported / read_only_report` → 按真实契约修正（产品代码未改）。
4. 首轮 5 项低于登记的 6 项下限，被 `below_registered_minimum` 如实拦截 → 按实际规模对齐为 5（**未虚增断言**）。

## 5. 未完成/未验收（如实登记）

- M7.9 组（M7.9.1—M7.9.6）六项适配器均已落盘并实测；经营报表正文（dashboard/reports）与日报生成按封闭域/被挡写入边界**明确不可用**，需评审决定是否放开（本项不擅自扩域）。
- 其余 M7 小项（M7.10.1 起）与 M8.x 按编号串行。
