# PATCH-M8-4-CUSTOMER-MODAL-READY-01

2026-10-01，M8.1。全部关联验证已收尾，精确仅 customer_followon_business.py 本地form helper。

customer-reports05第二次打开同名“关联本店服务摘要”，原异步fetch结束前旧closed dialog保留同title和旧form，标题断言提前满足；fields读旧隐藏select后误求details。实际121-failure.png新表单已正常显示原生select，不能误按搜索组合框改变字段合同。点击之后先等待原modal实际可见，再核标题和原字段；所有原源选择/201/回执/全库守卫不变。不是放宽hidden输入或注入值，旧失败保留，新实例七项与五报表再办。
