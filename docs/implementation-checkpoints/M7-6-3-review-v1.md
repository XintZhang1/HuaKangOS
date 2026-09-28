# M7.6.3 编码审阅与实测记录（客户提醒来源适配器）

2026-09-28，集中测试阶段。M7.6 组第三项，CP-23 收官项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/care_reminder.py`：`CareReminderAdapter(FlowCaseAdapter)`，`object_types=('reminder_rule',)`；快照只读 `GET /api/customer-service/reminders/rules`（集合读取按真实 ID 精确匹配）；`read_receipt` 由已评审 resolver 绑定 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='care_reminder', object_types=(REMINDER_OBJECT_TYPE,), operation_ids=(GET /api/customer-service/reminders/rules, POST /api/customer-service/reminders/rules, POST /api/customer-service/reminders/generate), fact_keys=REMINDER_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_care_reminder.py`（7 项） |
| 未改动 | 原 `customer_service_api.py`/`customer_service.py`/`observation_corrections_service.py`、迁移、权限表、提醒周期公式与状态机；未新增 signal hook；未调用 reminders/generate 写接口 |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/customer-service/reminders/rules` | — | 原规则清单 `{'items': [...]}`（`id`/`kind`/`name`/`interval_*`/`lead_*`/`assignee_id`/`active`/`version`） |
| result / receipt | `POST /api/customer-service/reminders/rules`、`POST /api/customer-service/reminders/generate` | — | 原写接口响应（后台仅准备其卡，不自动提交）；回执由已评审 resolver 绑定 |

四种原 kind：`first_service` / `maintenance` / `warranty` / `renewal`（套件逐项断言原 service 中存在）。

事实键与满足条件：
- `reminder.rule_active`：原清单中**按真实 ID 精确匹配**到该规则且 `active=true`（同名不同 ID 不匹配，套件显式验证）；未生效明确未满足。
- `reminder.generated_case_recorded`：需要原 generate 成功结果或带同规则、同车辆/周期与 care case 引用的已生成记录；**原规则清单读法不暴露该关联，故一律返回未知——不从文字或日期自行断言已生成**。

## 3. 实测结论

运行 `20260928T134539Z-db53035e2c`：`status=passed`，`phase_complete=true`（源码指纹 `68e6089bbfa2eaba873ffe4ef4dd38ca720e5b1c5d6378bac9b1f1c4972dde97`）。

- `tests/runtime_domains/test_care_reminder.py`：**7 项通过**。覆盖三条 operation 在 reviewed catalog、两个原 service 函数与四种 kind、原模型存在、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照集合读取（零 path_args）、**同名不同 ID 不匹配（404）**、未登记 kind 502、无门店身份 403、上游 503、`state` 随原 `active` 变化；引用类型四类非法输入 422；两条事实的满足/未满足/未知分支（含"读法不暴露生成关联时必须未知"）；`extract_result` 边界（清单读不绑定、缺 id 不绑定）；回执保持冻结 `request_id`、未绑定 `unsupported`、只读规则清单 422。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- CP-23（M7.6.1—M7.6.3）三项适配器均已 implemented 并实测；`released` 仍不记，因为真实原库、真实模型、浏览器与员工试用属 M8.x。
- `reminder.generated_case_recorded` 在缺少已评审的生成记录读取路径前保持未知（需补 care case 侧的生成关联读法）。
- 其余 M7 小项（M7.7.1 起）与 M8.x 按编号串行。
