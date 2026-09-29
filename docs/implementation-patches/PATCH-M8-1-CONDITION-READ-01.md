# PATCH-M8-1-CONDITION-READ-01：单次计划核查内复用已授权读取

2026-09-29，接续销售事实修复。只改变一次核查的重复读取，不更改事实语义、原业务写入或跨轮新鲜性要求。

## 范围与原因

生产：`app/assistant_runtime_conditions.py`、`app/assistant_runtime_plans.py`。测试：`tests/assistant_offline/tests/test_condition_reads.py`、现有销售计划用例与隔离 runner。实施计划 M8.1 追加本补丁记录。

原计划对同一原单每个步骤分别创建准备/完成 evaluator，通用对象、原报价快照和不同事实又分别重复 GET。真实销售两步闭环单例在合成响应下执行约 199 秒，过程中大量事件仅重新证明同一原单。先对确切 GET 次数作回归，不靠放宽执行时限或删除否定断言。

## 不变量

复用仅在 `_evaluate_plan_facts` 一次只读调用的局部 evaluator 内，以完整 operation/path/query/body 为键。只保留成功、未截断的原 GET 返回，返回脱离副本；异常、缺权限、失败和截断不记为已缓存成功。每次命中仍重新核验当前登录/授权/门店/租约，不共享给其他用户或 store，不写持久缓存。

下一次公开条件核查、worker tick、工具准备前重核或确认后重核必须新建 evaluator，重新执行原 GET。原请求回执核查与 read WorkItem 完成的 original_get 保持独立重新读取。原 Plan/Step/Run 版本、原 API 版本守卫、确认与业务权限保持不变；不把一次局部快照当成跨步骤业务提交授权。

## 验证

相同原单的多个条件/步骤每次证明只读一次相同 GET；新核查看到原业务变化；缓存副本不可污染；撤权/退出后即使已有缓存仍拒绝；请求参数隔离、失败/截断不缓存。原销售正反例、完整跟进、批量失败即停、全部现有前端和原生浏览器随后复验。默认功能开关不变，零真实模型调用。
