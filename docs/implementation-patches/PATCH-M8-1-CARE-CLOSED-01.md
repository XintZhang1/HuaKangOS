# PATCH-M8-1-CARE-CLOSED-01

2026-09-29；M8.1 保持 `in_progress`。业主本轮授权继续实现并执行离线验证。

## 已复现缺陷

`app/assistant_runtime_domains/customer_care.py` 判定 `care.closed` 时比较
`data.get('state') == 'closed'`。原客户关怀服务单并不存在 `closed` 状态：
`customer_service.STATUS` 为 `pending/working/completed/cancelled`，`close` 动作把
`Case.state` 置为 `completed`，`cancel` 置为 `cancelled`。因此在真实数据上该事实键在已结案时
返回“未结案”，依赖它完成的后续条件永远不成立。

## 精确改动范围

仅 `app/assistant_runtime_domains/customer_care.py`：

1. 新增 `CARE_STATES`、`CARE_CLOSED_STATE`、`CARE_CANCELLED_STATE` 常量，取自原业务状态机，
   不内联自造状态名。
2. `care.closed` 改为：`completed` 成立；`cancelled` 返回不成立并说明“取消不是结案”；
   `pending`/`working` 返回尚未结案；未登记或非字符串状态返回未知，不推断。
3. 模块 docstring 同步说明结案口径。

## 保留的边界

- 不改原关怀状态机、结案/取消动作、任务结束语义或任何业务写入。
- 跟进、交接两条事实及其“联系不到不等于成功联系”的边界不变。
- 不把 `cancelled`、`pending`、`working` 任何一项当作已结案。

## 异常路径

- 原详情状态为未登记值或缺失：返回未知并要求到原页面核对，不猜已结案。
- 已取消的关怀单：返回不成立，提示取消与结案是两件事。
- 跟进/交接记录缺失：仍按原有逻辑返回不成立或未知，不受本次改动影响。

## 测试精确范围

`tests/assistant_offline/tests/test_repair_warehouse_grant_facts.py` 的 `CareClosedFact`：
原状态常量对照、`completed` 成立、`cancelled` 不成立且说明取消、`pending`/`working` 不成立、
未登记与非字符串状态返回未知。
