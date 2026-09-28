# M7.8.2 编码审阅与实测记录（发票适配器）

2026-09-28，集中测试阶段。M7.8 组第二项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/invoice.py`：`InvoiceAdapter(FlowCaseAdapter)`，`object_types=('case',)`（`InvoiceApplication.id` 与原 Case.id 相同）；快照只读 `GET /api/invoices/orders/{key}`；`read_receipt` 由已评审 resolver 绑定 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='invoice', object_types=('case',), operation_ids=(orders/{key}, POST orders, orders/{key}/actions/{action}), fact_keys=INVOICE_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_invoice.py`（7 项） |
| 未改动 | 原 `invoice_api.py`/`_service.py`/`_models.py`、迁移、权限表、金额与余额公式、状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/invoices/orders/{key}` | `{'key': <Case.id>}` | 原发票详情（申请字段、`source_case_id`/`source_version`、`balance`、`result`、岗位筛后动作名） |
| 只读来源 | `GET /api/invoices/sources`（另 `/sources/{key}` 已登记） | — | 原来源读取（登记为只读来源，不作为结果 operation） |
| result | `POST /api/invoices/orders` | — | 原创建响应 |
| result / receipt | `POST /api/invoices/orders/{key}/actions/{action}` | `{'key','action'}` | 原动作响应（approve/submit/failure/difference/record/review_result）；回执由已评审 resolver 绑定 |

事实键与满足条件：
- `invoice.submission_recorded`：原详情提供的对外提交记录；**详情未提供时未知**（不据文字/日期自行断言）；满足时明确"提交不等于开票成功"。
- `invoice.result_recorded`：本单原 `InvoiceResult`；**failure/difference 仍是原结果**（`satisfied=True` 并在理由中点名），**不代表发票已开具**；有发票号时正常满足。
- `invoice.result_reviewed`：必须原 `review_result` 复核事实；未提供即未知；满足时明确"复核不改变原开票结果本身"。

## 3. 实测结论

运行 `20260928T135748Z-2a3ce40540`：`status=passed`，`phase_complete=true`（源码指纹 `306fb1da92501149609e4eb94d42c4e05c448c20a477eed3eef9d9714e92e267`）。

- `tests/runtime_domains/test_invoice.py`：**7 项通过**。覆盖四条 operation 在 reviewed catalog、四个原 service 函数与六个原动作、三个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照单次 GET、ID 不一致 502、**缺原来源单 502**、无门店身份 403、上游 503、动作可用性 `unknown`；三条事实的满足/未满足/未知分支（含"failure/difference 仍是原结果但不代表已开具""提交缺证据必须未知""复核不改变原结果"三条显式断言）；引用类型四类非法输入 422；未登记事实不猜；`extract_result` 边界；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `invoice` 一个适配器；M7.8.3 起 25 个小项仍为 `todo`，按编号串行。
- 提交/复核事实在原详情未提供对应记录时按合同未知。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
