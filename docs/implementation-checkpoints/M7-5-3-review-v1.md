# M7.5.3 编码审阅与实测记录（仓储单据适配器）

2026-09-28，集中测试阶段。M7.5 组第三项，CP-22 收官项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/warehouse_document.py`：`WarehouseDocumentAdapter(FlowCaseAdapter)`，`object_types=('case',)`；快照只读 `GET /api/warehouse/cases/{case_id}`；`extract_result` 覆盖仓储族 operation；`read_receipt` 沿原 `digest(action, values)` 摘要族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='warehouse_document', object_types=('case',), operation_ids=(GET /api/warehouse/cases/{case_id}, POST /api/warehouse/cases, POST /api/warehouse/cases/{case_id}/commands/{action}), fact_keys=WH_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_warehouse_document.py`（7 项） |
| 未改动 | 原 `warehouse_api.py`/`_service.py`/`_models.py`/`warehouse_stock.py`、迁移、权限表、数量公式、状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/warehouse/cases/{case_id}` | `{'case_id': <Case.id>}` | 原仓储详情（`operation`、`stock_moves[]`、`entries[]`（如有）、`count`（盘点观察块）与动作 key/label） |
| result | `POST /api/warehouse/cases` | — | 原单据创建响应 |
| result / receipt | `POST /api/warehouse/cases/{case_id}/commands/{action}` | `{'case_id','action'}` | 原命令响应；回执族 `digest(action, values)` |

十个原 operation：`activate` / `other_in` / `other_in_return` / `consumable` / `consumable_return` / `gift` / `gift_return` / `disposal` / `local_move` / `count`。

事实键与满足条件：
- `warehouse.entry_recorded`：原详情提供本单出入库流水且至少一笔有可识别标识；详情未提供流水时**返回未知**（不猜）。
- `warehouse.count_observed`：原 `WarehouseCountObservation`（详情 `count` 块的实盘/账面对比）；理由明确"实盘观察不等于已过账"。
- `warehouse.count_posted`：必须**原 post_count 成功回执且存在实际盘差 StockMove**；**实盘观察、批准、准备分配都不满足本键**；该详情未提供盘差过账标记时返回未知；无差异时明确未满足。

## 3. 实测结论

运行 `20260928T134114Z-d3d89577cf`：`status=passed`，`phase_complete=true`（源码指纹 `024186c59cb2bc9972b26fd01218ea60e1dc07523de0fe670a695f329a260441`）。

- `tests/runtime_domains/test_warehouse_document.py`：**7 项通过**。覆盖三条 operation 在 reviewed catalog、原摘要规则与五个 service 函数、十个原 operation、四个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照单次 GET、ID 不一致 502、**未登记 operation 502**、无门店身份 403、上游 503、动作可用性 `unknown`；三条事实的满足/未满足/未知分支（含"流水缺失必须未知""实盘观察不等于已过账""无差异明确未满足"三条显式断言）；未登记事实不猜；`extract_result` 边界；回执族保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- CP-22（M7.5.1—M7.5.3）三项适配器均已 implemented 并实测；`released` 仍不记，因为真实原库、真实模型、浏览器与员工试用属 M8.x。
- `warehouse.count_posted` 与 `warehouse.entry_recorded` 在详情未提供对应标记时按合同返回未知（需评审补只读路径后才可判定），未伪造通过。
- 其余 M7 小项（M7.6.1 起）与 M8.x 按编号串行。
