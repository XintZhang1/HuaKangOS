# PATCH-M8-4-CANCELLATION-CASH-PROJECTION-01

2026-10-01，M8.1 当前浏览器候选精确补丁，实施前登记。fresh3全部终局、关联Python及63713–63715监听已结束，允许修改窗口重新打开。finance10完整17执行16通过，财务三原款更正/刷新与其它收入都实际通过；HK092原退订只读闭包比较失败，未产生新的退款写。CLI真实exit3、场景exit1，不能称全套通过。

原sales_order_business.facts203–204只记录固定十列Cash投影，当前cancellation_closure却将SELECT*完整Cash与投影直接比较。原合成Case91 cancelled、两Payment完整行相同、原存退各300000分/同账户1、两Cash原十列全部相同、无本单位置流水/开放任务。Cash额外日期/版本/备注等列存在不是业务变化；与此前PDI的父投影边界相同，不能修改正确生产行为求绿。

仅允许 tests/browser_click/finance_remaining_business.py cancellation_closure：声明与原父相同固定十列，明确要求deposit/refund两父Cash keys恰等该集合，当前同十列严格比较；原两Payment仍全行相等、金额/方向/原款/原账户/当前单/唯一两记录/无位置出库/无待办保持。保留当前完整两Cash到结果，另保留原父十列投影说明；原本人读取/刷新全业务摘要不变/原POST native回执不动，不改父checkpoint或其它域比较，不猜缺字段、不默认零。

仅候选合同适配，生产/目录/runner/CI不改；独立原字节/AST审后新外置原17闭包再跑，随后同版本full53。所有失败、193逐项人工/真实Date与原独立门槛保留。
