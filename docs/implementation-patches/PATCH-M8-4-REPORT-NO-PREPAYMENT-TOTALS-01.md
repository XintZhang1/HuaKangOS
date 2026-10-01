# PATCH-M8-4-REPORT-NO-PREPAYMENT-TOTALS-01

2026-10-01，当前 M8.1 原浏览器候选精确修正，实施前登记。reports07 全6执行5父通过，最后实际同原账户供应商退款500已提交并核原回执，随后候选在最终守恒核对访问不存在prepaid_cents抛KeyError；失败原件保留。

原procurement_prepayment_service.adjust_totals在没有Facility时直接返回原普通采购totals；describe的prepayments为None。该普通采购合同包含paid_net_cents/payable_cents/supplier_refund_due_cents，不包含prepaid_cents，不能改生产补造预付款字段或把未知默认成0。

仅允许 tests/browser_click/report_complete_source_business.py procure 最终一处断言：保留库存数量/价值1500、两批余额500/1000、原单completed、原付款净额1500、两个普通应付/应退字段为0；另明确核prepayments is None且prepaid_cents不在totals。其余现金2000/500、原款/账户/店/本人、每次事实/全旧行/唯一回执与原范围均不变。不改生产、其他测试、runner/CI、目录或验收标准。

静态与独立审阅后新外置6闭包再核原退款/非空报表，不能拼不同指纹父结果成full53；193逐项体验及原独立门槛继续保留。
