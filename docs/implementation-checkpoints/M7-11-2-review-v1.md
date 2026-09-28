# M7.11.2 编码审阅与实测记录（字典条目适配器）

2026-09-28，集中测试阶段。M7.11 组第二项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/dictionary_entry.py`：`DictionaryEntryAdapter(FlowCaseAdapter)`，`object_types=('dictionary_entry',)`（**原 `flow Reference.id`**）；受控只读原语 `read_group(principal, group, q, page)` 与 `read_entry(principal, group, entry_id)`；事实 `dictionary.record_exists` / `dictionary.active` |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='dictionary_entry', object_types=(DICT_OBJECT_TYPE,), operation_ids=(GET /api/dictionaries/{group}, GET /api/dictionaries/catalog, POST /api/dictionaries/{group}, PUT /api/dictionaries/{group}/{record_id}), fact_keys=DICT_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_dictionary_entry.py`（7 项） |
| 未改动 | 原 `dictionary_api.py`、`master_data.py`、网关、迁移、权限表与既有枚举；未新增 signal hook |

## 2. 结论摘要（先读）

1. `BusinessObjectRef` 只有 `(type, id)`，而原字典分组是 `{group}` 路径参数：
   **group 属"由核心提供的冻结输入"**（原 category 固定映射 dictionary group）——
   核心未提供时快照/事实**明确报告边界且零读取**，适配器**不猜 group、不跨组扫描**；
2. 原分组列表**确有分页**：`listing(group, q=Query('',max_length=120), page:int=Query(1,ge=1), page_size:int=Query(30,ge=1,le=100), ...)`
   → 命中必须**按 page 完整翻页**；只有翻到不满一页（或超窗口前不得）才能判"不存在"，否则**未知**；
3. `dictionary.active` 只认原记录 `active` 字段（缺字段未知）；**原条目字段只有 name/detail/active，
   不把显示中文猜成业务 value 或状态枚举**。

## 3. 实测结论

运行 `20260928T143211Z-6b5cf8772c`：`status=passed`，`phase_complete=true`（源码指纹 `39fae5e8daee3a06000b6f43d78f206e6164ba2c410d4b21854b9acbfe6dd74e`）。

- `tests/runtime_domains/test_dictionary_entry.py`：**7 项通过**。覆盖四条 operation 在 reviewed catalog、原 `@router.get('/{group}')` 与 `q`（`max_length=120`）+ `page`/`page_size` 分页参数、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；非法 group 六类输入 422 **且零读取**；快照与事实在 group 未提供时 503/未知**且零读取**（不跨组扫描）；只读指定 group（断言 path_args 与 `page`/`page_size` 查询）；**第 2 页的记录能被翻页命中**；未返回 `items` → 未知；`active` 三态与字段保真（不派生 `label`）；写结果绑定（`POST`/`PUT`）、分组读与目录读不绑定；回执保持冻结 `request_id`、未绑定 `unsupported`、只读 operation 422；未登记事实未知且点名"不把显示中文猜成枚举"。

## 4. 实测发现并修复的问题（全部如实保留）

1. 首轮套件用**源码字面签名**断言原列表函数而失败 → 改为断言**路由装饰器 + 参数切片**（更稳且仍是真实契约）。
2. **真实产品缺陷**：我最初按截断的签名以为分组列表没有分页，套件随即指出原接口**带 `page`/`page_size`**；
   已把 `read_entry` 改为**按页完整翻页**（`page_size=100`、最多 50 页），并把"不满一页才算翻完、
   否则未知"写成显式断言——否则第 2 页之后的条目会被误判为"不存在"。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `dictionary_entry` 一个适配器；M7.11.3 起 15 个小项仍为 `todo`，按编号串行。
- 快照/事实的 group 由核心冻结输入提供这一接线仍需在 M8.x 集成阶段核对；真实原库与真实模型属 M8.x。
