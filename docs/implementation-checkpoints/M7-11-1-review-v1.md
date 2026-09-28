# M7.11.1 编码审阅与实测记录（类型化主数据适配器）

2026-09-28，集中测试阶段。M7.11 组首项。前置侦察见 `M7-11-1-recon-note.md`（含 14 类 kind 逐字对照表）。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/typed_master.py`：`TypedMasterAdapter(FlowCaseAdapter)`，`object_types` = 计划登记的 **14 类**；事实 `master.record_exists` / `master.active`；写结果绑定 `POST`/`PUT`；**计划未登记回执族** → 写 operation 回执 `unsupported` |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='typed_master', object_types=MASTER_OBJECT_TYPES, operation_ids=(GET /api/masters/{kind}, GET /api/masters/catalog, GET /api/masters/lookup/{kind}, POST /api/masters/{kind}, PUT /api/masters/{kind}/{record_id}), fact_keys=MASTER_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_typed_master.py`（9 项） |
| 未改动 | 原 `master_api.py`/`master_data.py`/`master_models.py`、网关、迁移、权限表、CATALOG schema 与角色；未新增 signal hook；`/opening/*` 未触碰 |

## 2. 确定映射表（固定字典，逐字核对的 14 类）

`vehicle_brand→vehicle_brands`、`vehicle_series→vehicle_series`、`supplier→suppliers`、`insurer→insurers`、
`warehouse→warehouses`、`storage_location→locations`、`material_brand→material_brands`、
`material_category→material_categories`、**`master_work_item→work_items`**、`team→teams`、
`agency_project→agency_projects`、`vehicle_model→vehicle_models`、`member_tier→member_tiers`、
`item_profile→item_profiles`。

**原业务作业 WorkItem 映射为 `master_work_item`，不混为 Runtime WorkItem**（套件断言反向映射里不存在 `work_item`）。

## 3. 事实与边界

- `master.record_exists`：按 `page` **完整分页**精确命中真实 ID；
- `master.active`：只认命中记录的 `active` 字段，**缺字段/类型不可判 → unknown**，不用 `active` 过滤参数反推；
- **只有分页信息确认翻完**（`has_next=false`，或 `total` 与 `page_size` 推出已到末页）才判定"不存在"；
  空页但无可确认的分页信息、或列表未返回 `items`、或超过 50 页窗口 → **一律未知**，不判定为不存在；
- 快照只读列表并逐页命中；候选读取（catalog/lookup）**不绑定结果**。

## 4. 实测结论

运行 `20260928T142931Z-9eac096fd3`：`status=passed`，`phase_complete=true`（源码指纹 `e2d715d19af90e7dbeb8a486368fab182dc248d175a6320197e726d05a47c0aa`）。

- `tests/runtime_domains/test_typed_master.py`：**9 项通过**。覆盖 14 类映射与 `CATALOG` 顶层键集合完全一致（不多不少）、五条 operation 在 reviewed catalog、原签名含 `page`/`active`、不动态导入/不写库/不抢回退、注册 spec 含 14 类；**命中在第 3 页时确实翻了 3 页并用原 kind**；完整翻完 → 快照 404 且事实明确未满足；分页信息不可用 / 未返回 `items` → 未知；`active` 三态（真/假/缺字段未知）；引用类型四类非法输入 422、无门店身份 403、上游 503；写结果绑定（`work_items` → `master_work_item`、未知 kind 与失败态不绑定）、候选读不绑定；回执 `unsupported / receipt_family_not_registered`、非法快照 422；未登记事实未知。
- 本轮**一次如实拦截 + 一处产品修复**：首轮"空页且无分页信息"被判成"不存在"，合同要求未知 → 改为**只有分页信息确认翻完**才判定不存在（真实产品缺陷）。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `typed_master` 一个适配器；M7.11.2 起 16 个小项仍为 `todo`，按编号串行。
- 主数据写入未登记回执族（计划未列），如需回执须由评审新增；真实原库与真实模型属 M8.x。
