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

## 3. 补齐核对（本轮第二次读取，缺口已全部确认）

`CATALOG` 的真实排版是 `'<kind>':(<Model>, <Input>, '<中文名>', <ROLE>, [<fields>])`（此前正则按 `{` 匹配故未命中）。
按正确格式提取，**顶层 kind 恰为 14 个**，与计划注册合同的 14 类一一对应：

| 计划 object_type | 原 kind | 中文名（CATALOG） |
|---|---|---|
| `vehicle_brand` | `vehicle_brands` | 车辆品牌 |
| `vehicle_series` | `vehicle_series` | 车辆车系 |
| `supplier` | `suppliers` | 供应商 |
| `insurer` | `insurers` | 保险公司 |
| `warehouse` | `warehouses` | 仓库 |
| `storage_location` | `locations` | 库位 |
| `material_brand` | `material_brands` | 物资品牌 |
| `material_category` | `material_categories` | 物资分类 |
| `master_work_item` | `work_items` | 作业项目 |
| `team` | `teams` | 班组 |
| `agency_project` | `agency_projects` | 代办项目 |
| `vehicle_model` | `vehicle_models` | 车型 |
| `member_tier` | `member_tiers` | 会员等级 |
| `item_profile` | `item_profiles` | 物资档案 |

原接口签名（已核对）：`list_master(kind, q=Query('',max_length=100), active: bool|None=None,
fuel_type: str|None=None, min_seats: int|None=Query(ge=1,le=60), max_price_cents: int|None=Query(ge=0),
page: int=Query(1,ge=1), db, user)`；
`lookup(kind, q=Query('',max_length=100), selected_id: int|None=Query(gt=0), db, user)`。

由此确定的实现口径：
- `master.record_exists`：在**原对应 kind 的列表**中按 `page` 翻页直至命中或翻完（**完整分页**），
  按真实 ID 精确命中才算存在；
- `master.active`：只认命中记录的 `active` **字段**；**记录缺该字段时为 unknown**，
  不以 `active` 过滤参数反推。

## 4. 结论与下一步（不虚构完成）

- 本项**未实现、未注册、未实测**；计划中 `### M7.11.1` 不登记为 `implemented`。
- 下一轮第一步：按上表实现 `app/assistant_runtime_domains/typed_master.py`（**固定字典映射**、
  原业务作业 WorkItem 映射为 `master_work_item`、**不混为 Runtime WorkItem**），在
  `app/assistant_runtime_domains/__init__.py` 显式注册 14 个对象类型（`fallback_object_types=()`）；
  写入只走已评审 `POST /api/masters/{kind}` 与 `PUT /api/masters/{kind}/{record_id}`，
  并补外部套件 `$ValidationRoot/tests/runtime_domains/test_typed_master.py`。
