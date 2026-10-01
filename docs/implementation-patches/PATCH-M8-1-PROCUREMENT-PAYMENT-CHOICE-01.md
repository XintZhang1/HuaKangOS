# PATCH-M8-1-PROCUREMENT-PAYMENT-CHOICE-01

2026-10-01，M8.1，延续原193项代码与浏览器点击授权。全部关联验证进程已收尾；business-member-boutique-20261001-04 的失败原件保留。

精确范围仅 app/procurement_service.py 的 describe 付款只读投影，以及 tests/browser_click/boutique_business.py 对原退款选择项的核对。原 UI procurementRefundOptions 已要求付款日期和账户，实际后端未返回这两个字段；因此严格40元原款选项检查失败。不是将缺字段解释为成功。

在原 money 权限分支内，按原 PurchasePayment.cash_id 与原单 store_id 查询真实 CashEntry，返回 business_date 和该现金原事实冻结的 account 作为 account_name。不能从当前账户名称猜历史，不创建、更新或删除现金/付款，不改权限、金额、原款约束、版本、回执或原退款事务。关联现金缺失则明确拒绝读取，不静默省略原款。脚本保留实际日期、账户、凭证、原40元及可退余额/付款ID可辨识核对，并只从原可见组合框选择该原款。非金额岗位仍无付款投影。

完成静态审查后用全新外部隔离目录复验本次两笔40元采购付款及原10元供应商退款，再继续原零售流程；原款选项显示、实际退款、库存和现金分别核对。静态通过不登记业务 passed，银行/PG/Linux/员工及全193人工评价仍待测。
