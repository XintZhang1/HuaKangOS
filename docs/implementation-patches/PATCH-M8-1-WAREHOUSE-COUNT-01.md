# PATCH-M8-1-WAREHOUSE-COUNT-01

2026-09-29；M8.1 保持 `in_progress`。业主本轮授权继续实现并执行离线验证。

## 已复现缺陷

`app/assistant_runtime_domains/warehouse_document.py` 判定 `warehouse.count_posted` 时，查找
`stock_moves[].purpose == 'count_adjust'`。原仓储并不存在这个用途：`warehouse_service.post_count`
调用 `post(..., 'wh_count', ...)`，即 `PURPOSES['count']`；`operations_analytics` 与
`warehouse_period_analytics` 也都按 `wh_count` 筛选盘差流水。因此真实数据上该事实键永远
无法成立，只会在“无差异”或“未知”之间取值，依赖它完成的计划步骤会被永久挡住。

## 精确改动范围

仅 `app/assistant_runtime_domains/warehouse_document.py`：

1. 新增 `count_purpose()`，从原仓储模块的 `PURPOSES['count']` 取真实用途；首次调用时才
   导入，避免与原业务模块在 import 期形成循环依赖，并缓存结果。
2. `warehouse.count_posted` 改为与该真实用途比较，不再内联一个自造的标记名。
3. 原盘点观察存在时先核对其键类型：`counted_quantity_milli == baseline_quantity_milli` 才是
   “无差异、无需过账”；键缺失或非整数返回未知，不再把不可判定的观察当成无差异。
4. 模块 docstring 与 `__all__` 同步说明该用途来自原业务常量。

## 保留的边界

- 不新增、不改写任何仓储用途字符串；不改原 `PURPOSES`、原 `post_count` 动作或库存余额。
- 实盘观察、批准、准备库位分配仍然都不满足过账键；只有本单已出现原盘差库存流水才满足。
- 不回退原有的“非盘点单据不得声称已过账”行为。

## 异常路径

- 原详情 `count` 缺少数量字段：返回未知并要求到原页面核对，不猜测。
- 原详情 `stock_moves` 缺省或非列表：按空列表处理，保持未知。
- 用途常量与原模块漂移：契约测试同时核对 `count_purpose()` 与 `warehouse_service.PURPOSES['count']`，
  漂移会直接失败而不是静默不匹配。

## 测试精确范围

`tests/assistant_offline/tests/test_repair_warehouse_grant_facts.py` 的 `WarehouseCountPosted`：
真实用途常量一致性、自造用途名一律不成立、已过账流水成立、纯观察不成立、零差异不需要过账、
观察数据不完整返回未知、非盘点单据不声称过账、观察键本身仍独立成立、未登记事实键返回未知。
