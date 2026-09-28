# M7.11.1 编码前置侦察记录（typed_master，未完成实现）

2026-09-28，集中测试阶段。M7.11 组首项。**本文件只记录侦察事实与缺口，不表示该项已实现。**

## 1. 已核对的原始面（只读事实）

`app/business_assistant_capabilities.json` 中与主数据相关的已评审 operation：

| operation_id | 说明 |
|---|---|
| `GET /api/masters/catalog` | 原主数据目录 |
| `GET /api/masters/{kind}` | 原某类主数据列表（`q` 模糊查询，`max_length=100`） |
| `GET /api/masters/lookup/{kind}` | 原候选项查找 |
| `POST /api/masters/{kind}` | 原新增（`status_code=201`） |
| `PUT /api/masters/{kind}/{record_id}` | 原更新 |

`app/master_api.py` 另存在 `/opening/*` 系列（期初批次、试算、确认、stockflow 导出）路由，**未在本项范围内使用**。

## 2. 已核对的原 kind（来自 `app/master_data.py` 的 `CATALOG`）

`vehicle_brands`、`vehicle_series`、`suppliers`、`insurers`、`warehouses`、`locations`、
`material_brands`、`material_categories`、`work_items`、`teams`（共 10 个，按顺序取自 `CATALOG` 顶层）。

计划 `**注册合同**` 要求登记 14 个对象类型（单数命名）：
`vehicle_brand`、`vehicle_series`、`supplier`、`insurer`、`warehouse`、`storage_location`、
`material_brand`、`material_category`、`master_work_item`、`team`、`agency_project`、
`vehicle_model`、`member_tier`、`item_profile`。

## 3. 尚未核对、因此**未登记**的部分（缺口，不得猜写）

- `agency_project`、`vehicle_model`、`member_tier`、`item_profile` 四类的**原 kind 字符串未核对**：
  初次提取 `CATALOG` 顶层键时正则未命中（`master_data.py` 的字典排版与假设不符），
  也未在本次预算内逐字确认这四类是否确实存在于 `CATALOG`、以及它们的单复数命名。
- `master.active` 事实要求"同一原记录 `active=true`，**缺字段为 unknown**"；
  `master.record_exists` 要求"原对应 kind 的授权详情/**完整分页**精确命中该 ID"——
  因此实现前必须确认原列表接口的**分页语义与命中方式**（是否返回 `items`、是否有 `total`/游标）。

## 4. 结论与下一步（不虚构完成）

- 本项**未实现、未注册、未实测**；计划中 `### M7.11.1` 不登记为 `implemented`。
- 下一步（下一轮第一件事）：逐字读取 `app/master_data.py` 的 `CATALOG` 顶层键与 `app/master_api.py`
  的列表返回结构，确认 14 类 kind 与分页字段，然后按本仓库既有适配器范式实现
  `app/assistant_runtime_domains/typed_master.py`（固定字典映射、不混 Runtime WorkItem）、
  注册 14 个对象类型，并补外部套件 `$ValidationRoot/tests/runtime_domains/test_typed_master.py`。
- 边界不变：**原业务作业 WorkItem 映射为 `master_work_item`，不混为 Runtime WorkItem**；
  写入只走已评审 POST/PUT 与 CATALOG schema。
