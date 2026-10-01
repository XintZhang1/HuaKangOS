# PATCH-M8-4-BOUTIQUE-PROCUREMENT-AUDIT-01

2026-10-01，M8.1。member-boutique03 selected9为8passed/1failed：新精品主档074已局部完成、两批真实入库后原采购pay成功200，新一条Audit导致候选误期待两条而失败。procurement_service._cash只追加Cash/PurchasePayment，command结尾只flow.log_event产生一条 flow_procurement_pay/refund 审计；retail真实flow.post_cash则额外cash audit共两条，不能混用合同。旧failure/60局部/59完整及积分六整场passed保留。

全部关联验证进程退出后，仅 boutique_business.py.purchase_action 的pay/refund新增审计数从错误2改精确1；同时对本purchase动作核精确actor/store/action=flow_procurement_{action}/entity_type=flow/entity_id=原case。保留每笔Cash/ProcurementPayment/原FlowReceipt与整数金额/本单当前版本/Task/原款退款/库存守恒/全部旧行保护；不改retail_cash的真实双审计、不添加生产审计或范围0..2。AST及独立短审后新鲜同9场景复验。
