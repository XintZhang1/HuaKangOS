# M7.10.6 编码审阅与实测记录（卷宗授权适配器）

2026-09-28，集中测试阶段。M7.10 组收官项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/dossier_grant.py`：`DossierGrantAdapter(FlowCaseAdapter)`，`object_types=('dossier_grant',)`；快照只读 `GET /api/dossier-grants/{grant_id}`；可读性事实**实测** `GET /api/dossier-grants/{grant_id}/record`；`read_receipt` 走 `DossierReceipt` 族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='dossier_grant', object_types=(DG_OBJECT_TYPE,), operation_ids=(GET /api/dossier-grants/{grant_id}, GET /api/dossier-grants/{grant_id}/record, POST /api/dossier-grants, POST /api/dossier-grants/{grant_id}/actions/{action}), fact_keys=DG_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_dossier_grant.py`（8 项） |
| 未改动 | 原 `dossier_grant_api.py`/`_service.py`/`_models.py`/`_rules.py`、迁移、权限表、源店审批与指定接收人规则；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 决定类事实 | `GET /api/dossier-grants/{grant_id}` | `{'grant_id': <DossierGrant.id>}` | 原授权详情（`status`、`decisions[]`（原 `DossierDecision`）） |
| 当前可读性事实 | `GET /api/dossier-grants/{grant_id}/record` | `{'grant_id'}` | 原授权摘要（**以本次读取为准**；不绑定结果） |
| result | `POST /api/dossier-grants` | — | 原创建响应 |
| result / receipt | `POST /api/dossier-grants/{grant_id}/actions/{action}` | `{'grant_id','action'}` | 原动作响应（propose/decide/read_record）；回执族 `DossierReceipt` |

事实键与满足条件：
- `dossier.approval_recorded`：本授权原 `DossierDecision` **批准**；理由明确**批准历史不满足当前可读**；
- `dossier.record_readable`：**本次原 /record 成功读取同一 grant 的授权摘要**（摘要指向别的授权 → 未知）；
  **403/404 无法区分"不存在"与"不可见" → 未知**（不推断为未授权）；
- `dossier.revocation_recorded`：原撤回/撤销决定明确存在；
- 明细缺失（`decisions` 为 `null`）→ 未知；明细为空列表 → 明确未满足；决定缺可识别动作类型 → 未知。

## 3. 实测结论

运行 `20260928T142648Z-069a04fbdd`：`status=passed`，`phase_complete=true`（源码指纹 `205391c7f3b4d92c392ab101401457fa299422f8edb7d3e964819f078facdab0`）。

- `tests/runtime_domains/test_dossier_grant.py`：**8 项通过**。覆盖四条 operation 在 reviewed catalog、五个原 service 函数、四个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照**只读一次详情**、ID 不一致 502、无门店身份 403；三条事实的满足/未满足/未知分支（含"批准历史不满足当前可读""/record 403 与 404 都必须未知""可读性必须实测 /record 且以本次为准""摘要指向别的授权必须未知""空决定明细明确未满足、缺动作类型必须未知"五条显式断言）；未登记事实不猜；`extract_result` 边界（摘要读不绑定结果）；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮经历 **2 次如实拦截 + 一处产品修复**：① 套件一行残留的三元表达式（`in model if False else`）在运行前被自查修掉；② "决定明细为空列表"被误判为未知，而合同要求**明确未满足** → 已区分"空明细（未满足）"与"有明细但缺类型（未知）"（真实产品缺陷）。

## 4. 未完成/未验收（如实登记）

- **M7.10 组（M7.10.1—M7.10.6）六项适配器全部落盘并实测**。
- 其余 M7 小项（M7.11.1 起）与 M8.x 按编号串行。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
