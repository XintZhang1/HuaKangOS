# M7.8.3 编码审阅与实测记录（月结冻结适配器）

2026-09-28，集中测试阶段。M7.8 组第三项，CP-27 收官项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/reconciliation_batch.py`：`ReconciliationBatchAdapter(FlowCaseAdapter)`，`object_types=('reconciliation_batch',)`；快照只读 `GET /api/reconciliation/batches/{key}`（**key 即原批次 id**）；`read_receipt` 由已评审 resolver 绑定 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='reconciliation_batch', object_types=(BATCH_OBJECT_TYPE,), operation_ids=(GET batches/{key}, POST batches, POST batches/{key}/actions/{action}), fact_keys=BATCH_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_reconciliation_batch.py`（7 项） |
| 未改动 | 原 `reconciliation_api.py`/`_service.py`/`_models.py`/`reconciliation_v21.py`、迁移、权限表、摘要与期间公式、状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/reconciliation/batches/{key}` | `{'key': <ReconciliationBatch.id>}` | 原批次详情（`status`/`status_label`、`case_version`、`definition_version`、`successor_id`、`source_changed`、`issues[]`） |
| result | `POST /api/reconciliation/batches` | — | 原批次创建响应 |
| result / receipt | `POST /api/reconciliation/batches/{key}/actions/{action}` | `{'key','action'}` | 原批次动作响应（issue/resolve/submit/reopen/recalculate）；回执由已评审 resolver 绑定 |

四种原状态：`draft` / `review` / `sealed` / `superseded`。

事实键与满足条件：
- `reconciliation.sealed`：原 `status='sealed'`。
- `reconciliation.superseded`：原 `status='superseded'`；理由带上后继批次号并明确**取代不冲销原差异记录**。
- `reconciliation.issue_recorded`：本批原 `ReconciliationIssue`；理由给出条数与**未解决条数**，并明确**原 issue 存在不等于差异已解决**。

## 3. 实测结论

运行 `20260928T140158Z-7bdbde8e27`：`status=passed`，`phase_complete=true`（源码指纹 `7f77ae424f3698ad0a45a77d7a5447678b627eb33db2406597ac2c2c8117d9ea`）。

- `tests/runtime_domains/test_reconciliation_batch.py`：**7 项通过**。覆盖目录内确存在 create/动作写 operation 与只读批次读取、三个原 service 函数、四种原状态、两个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec，含写 operation）；快照 key 即批次 id、ID 不一致 502、无门店身份 403、上游 503、动作可用性 `unknown`；引用类型四类非法输入 422；三条事实的满足/未满足分支（含"已封存不等于被取代""取代不冲销原差异""未解决条数如实呈现""issue 存在不等于差异已解决"四条显式断言）；未登记事实不猜；`extract_result` 边界；回执**保持冻结 `request_id`**、未绑定 `unsupported`、只读详情 422。
- 本轮经历**三次如实拦截与修复**（详见下节），最终通过。

## 4. 实测发现并修复的问题（全部如实保留）

1. **目录假设错误**：我最初据截断的目录输出判断"本对象在目录内没有写 operation"，套件随即判失败；核对完整目录后确认存在 `POST /api/reconciliation/batches` 与批次动作，遂改为登记真实写路径 + 回执绑定（**产品与套件都按真实证据修正**）。
2. **源码被写坏**：一次补丁把字面 `\n` 写进了适配器源码，`ast.parse` 立即报错、安装脚本中止（**仓库文件未被污染**）；用带断言的修复脚本还原为标准多行定义。
3. **注册残留**：首次安装已注册过只读版本，后续 `__init__.py` 因"已注册"被跳过，导致 spec 缺少写 operation；改为显式补丁注册项（import/`__all__`/`operation_ids` 三处同步）。
4. **执行器契约守护**：直接改覆盖层套件后运行被 `VALIDATION_REJECTED:overlay_addition_changed` 拒绝——**冻结指纹机制按设计生效**；重新登记 provenance 哈希后通过。

## 5. 未完成/未验收（如实登记）

- CP-27（M7.8.1—M7.8.3）三项适配器均已 implemented 并实测；`released` 仍不记，因为真实原库、真实模型、浏览器与员工试用属 M8.x。
- 其余 M7 小项（M7.9.1 起）与 M8.x 按编号串行。
