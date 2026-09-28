# M7.4.2 编码审阅与实测记录（精品套餐核销与安装适配器）

2026-09-28，集中测试阶段。M7.4 组第二项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/retail_bundle.py`：`RetailBundleAdapter(FlowCaseAdapter)`，`object_types=('retail_bundle_rule', 'retail_bundle_sale')`；规则快照只读 `GET /api/retail-bundles/rules/{key}/preview`；`extract_result` 覆盖规则/销售族 operation；`read_receipt` 走规则版本族摘要 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='retail_bundle', object_types=(RULE_OBJECT_TYPE, SALE_OBJECT_TYPE), operation_ids=(GET /api/retail-bundles/rules, GET /api/retail-bundles/rules/{key}/preview, POST /api/retail-bundles/rules, POST /api/retail-bundles/sales), fact_keys=BUNDLE_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_retail_bundle.py`（9 项） |
| 未改动 | 原 `retail_bundle_api.py`/`_service.py`/`_models.py`、迁移、权限表、金额与分摊公式、状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args / query | 原响应 / 回执族 |
|---|---|---|---|
| 规则快照 / 事实 | `GET /api/retail-bundles/rules/{key}/preview` | `{'key': <RetailBundleRule.id>}`，`query={'sets': 1}` | 原规则预览（`name`/`status`/`version`、冻结 `components` 含每套数量与商品/安装分摊） |
| result（规则） | `POST /api/retail-bundles/rules` | — | 原规则版本创建响应；摘要 `request_digest('retail_bundle_rule', …)` |
| result（销售） | `POST /api/retail-bundles/sales` | — | 原套餐销售响应；`extract_result` 绑定其派生的原 retail Case |

事实键与满足条件（合同：**前一键只用于规则，后一键只用于 sale，不适用类型返回 unknown**）：
- `retail_bundle.rule_snapshot_readable`：规则预览返回该真实规则且冻结组件/分摊完整（组件缺 `item_id` 或每套数量即未知）。
- `retail_bundle.sale_linked`：需要原套餐销售详情核对派生 retail Case；**该读取路径既未评审也未被活跃路由发现**（目录与 `_operations()` 均只有 `POST /sales`），故一律返回未知，销售对象不编造读取路径（`read_snapshot` 返回 503 并给原页面入口，夹具断言零读取）。

## 3. 实测结论

运行 `20260928T133417Z-862fad401d`：`status=passed`，`phase_complete=true`（源码指纹 `a94a84a4d03cf866c6f11abbe89bc001c2285629679a32571f4ed3438197c107`）。

- `tests/runtime_domains/test_retail_bundle.py`：**9 项通过**。覆盖四条 operation 在 reviewed catalog、规则版本摘要与 `rule_info`/`preview`/`create_sale` 存在、四个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec，覆盖两个对象类型）；规则快照单次预览读取（含 `sets=1`）、ID 不一致 502、**冻结组件缺失 502**、无门店身份 403；**销售对象零读取 + 503 缺口说明**与 `sale_linked` 未知；规则事实的完整/不完整/不适用类型三分支；形状错误引用 422；`extract_result` 对销售返回**派生 retail Case**、对规则返回规则引用、列表读不属于结果 operation、失败响应不绑定；未登记事实不猜；回执族保持冻结 `request_id`、未绑定 `unsupported`、只读预览 422。
- 同指纹回归未单独重跑（本项仅新增适配器文件与注册项，未触碰既有适配器）。

## 4. 实测发现并修复的问题

- 首轮套件的"引用类型"断言把**不适用对象类型**当成形状错误（期望 422），与计划合同"不适用类型返回 unknown"冲突。按合同修正断言（不适用类型 → unknown；形状错误 → 422），产品代码未改宽；这是套件适配缺陷，不是产品缺陷。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `retail_bundle` 一个适配器；M7.4.3 起 39 个小项仍为 `todo`，按编号串行。
- 套餐销售的核销/安装事实（`retail_bundle.sale_linked`）在缺少已评审读取路径前保持未知；需要评审补一条销售详情 GET 或等价只读路径。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
