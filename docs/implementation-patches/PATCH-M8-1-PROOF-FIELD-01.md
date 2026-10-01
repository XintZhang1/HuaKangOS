# PATCH-M8-1-PROOF-FIELD-01：代办和厂家原件字段类别接线

2026-10-01。当前M8.1修复范围仅`web/serviceorders.js`、`web/vehicleincome.js`。只读源码审阅已确认两处原表单默认类别与原API严格类别不符，尚未称实际422。后端规则、原件安全、重复SHA拒绝、岗位、金额、状态、版本及事务均保持原合同。

代办原approve/authorize/submit/external_result/fulfill/termination_approve/consent使用authorization；receive/disburse/thirdparty_return/termination_apply/refund使用receipt；cancel/termination_cancel无原件。termination独立方案已使用authorization，沿原表单。厂家propose/approve/reject使用后端已允许的evidence；receive/refund保持receipt；cancel/withdraw无原件。上传预选和本单原件候选沿相同实际类别，不放宽后端来接收错误类别。

两个精确字段接线后先语法检查，再以已登记HK015/016/017原点击候选实际复验；没有执行对应原流程前不得登记已通过。保险相似静态缺口留待独立范围，不在本补丁实施。
