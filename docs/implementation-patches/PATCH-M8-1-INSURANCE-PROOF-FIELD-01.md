# PATCH-M8-1-INSURANCE-PROOF-FIELD-01：保险原件字段类别

2026-10-01，当前M8.1，完整28场景实例已退出0后实施。源码范围仅 `web/insuranceorders.js` 原generic动作的evidence_id字段；原静态审阅与独立审阅确认现有固定evidence和原API类别不符，尚未称实际422。

原monetary八项receive/disburse/insurer_return/direct_paid/direct_return/refund/commission_receive/commission_return及termination_apply/commission/commission_review使用receipt；其余非取消原动作review/authorize/submit/result/termination_review/termination_consent使用authorization。直付、预收余额退款与零佣金确认仍按原financial合同取receipt，不以是否有现金判断。独立撤保方案已筛authorization，报价及取消无原件，保持原样。

仅让上传预选及当前单安全可用原件候选沿原后端严格类别。原文件权限、安全、非生成、独立SHA、摘要/版本/幂等、各资金/佣金/实物事实和Task守卫不改，不放宽后端。先语法及独立短审，再按BUSINESS-193-14冻结候选注册保险场景，在全新外部镜像走原UI；未实际执行前无业务成绩。
