# M7.6.2 编码审阅与实测记录（客户关怀服务单适配器）

2026-09-28，集中测试阶段。M7.6 组第二项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/customer_care.py`：`CustomerCareAdapter(FlowCaseAdapter)`，`object_types=('care_case',)`；快照只读 `GET /api/customer-service/cases/{case_id}`；`read_receipt` 走 `CareReceipt` 族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='customer_care', object_types=(CARE_OBJECT_TYPE,), operation_ids=(cases/{case_id}, POST cases, cases/{case_id}/actions/{action}), fact_keys=CARE_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_customer_care.py`（9 项） |
| 未改动 | 原 `customer_service_api.py`/`customer_service.py`/`customer_service_models.py`、迁移、权限表、提醒依据规则与状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/customer-service/cases/{case_id}` | `{'case_id': <CareCase.id>}` | 原关怀详情（`subtype`、`state`、`assignee_*`、`result`（原联系结果）、`records[]`（CareRecord）、`reminder_basis`、动作 key） |
| result | `POST /api/customer-service/cases` | — | 原创建响应（案件在 `case` 键下） |
| result / receipt | `POST /api/customer-service/cases/{case_id}/actions/{action}` | `{'case_id','action'}` | 原动作响应；回执族 `CareReceipt` |

七种原 subtype：`questionnaire` / `consultation` / `complaint` / `rescue` / `sales_callback` / `repair_callback` / `renewal`。

事实键与满足条件：
- `care.followup_recorded`：原 `CareRecord` 且可识别为 `followup`；**联系不到/拒绝联系仍保留原 `contact_result`，不能冒充成功联系**（理由回显原联系结果）；记录缺可识别动作类型时未知。
- `care.handoff_recorded`：原 `handoff` 记录**且**当前有可读负责人；仅跟进记录不满足；负责人缺失时未知。
- `care.closed`：原状态确为 `closed`。

## 3. 实测结论

运行 `20260928T134415Z-01d36b4163`：`status=passed`，`phase_complete=true`（源码指纹 `a880c46be8eb7a42afbb943bdba43d567555404122c1972691e94f3bfd87204d`）。

- `tests/runtime_domains/test_customer_care.py`：**9 项通过**。覆盖三条 operation 在 reviewed catalog、三个原 service 函数与七种 subtype、三个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照单次 GET、ID 不一致 502、**未登记 subtype 502**、无门店身份 403、上游 503、动作可用性 `unknown`；引用类型四类非法输入 422；三条事实的满足/未满足/未知分支（含"联系不到仍保留原结果但不得冒充成功联系""跟进记录不满足交接键""缺负责人必须未知""记录缺动作类型必须未知"四条显式断言）；未登记事实不猜；`extract_result` 边界（创建响应取 `case` 键）；回执族保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `customer_care` 一个适配器；M7.6.3 起 33 个小项仍为 `todo`，按编号串行。
- 记录动作类型以原 `CareRecord` 实际提供的判别字段为准；缺判别字段时按合同未知。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
