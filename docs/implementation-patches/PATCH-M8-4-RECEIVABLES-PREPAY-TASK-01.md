# PATCH-M8-4-RECEIVABLES-PREPAY-TASK-01

2026-10-01，53/f45b817a四关联CLI全退出1后，当前连续点击授权内先登记。

应收02的补材料采购Case118请款Request2原UI成功，审核原Task293归员工2；候选主管12提交原prepay_approve正确403。只在receivables_business.py补材料两个MAT.procurement_command参数：审批task_key为procurement_prepay_review_{实际Request.id}，后继付款task_key为procurement_prepay_pay_{实际Request.id}。复用原responsible可见交接、原AssignInput/Task版本/有限旧行保护及真实本人核对，不改后端、不借管理员、不SQL赋权/改任务、不自批。付款尚未执行，后继参数是补原合同；新VIN已有逐原Task交接不改。旧请求/拒绝保留、不重放，新fresh真实前序复验。
