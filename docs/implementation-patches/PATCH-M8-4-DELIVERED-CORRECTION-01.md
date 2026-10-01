# PATCH-M8-4-DELIVERED-CORRECTION-01

2026-10-01，M8.1。四关联原生运行已收尾。HK078新原已交车收款更正来源审阅发现确定接线缺口：本轮实际销售及PDI合同交车状态是delivered，原order.receive.states仅executing；business_finance_sources.source_details的allow_correcting额外仅放completed，会在独立更正execute读取正确原单时拒绝。此项来源矛盾由当前已实际delivered父和两现行状态合同核定，没有伪造金融HTTP失败或改变原交车状态。

仅 app/business_finance_sources.py 此校验允许 allow_correcting=true 且 kind=order/flow_version=3或4/state=delivered；历史completed例外保留，常规收款/预收抵用/客户月结默认allow_correcting=false不扩大。前置原岗位/本店/价格版本/aftercare与Cash原源、独立review/CAS/正确净分配/原退款切片及实际执行守卫全部保留，原交付/占车/实物不能重开。仅追加原错误款冲正和正确重记，不新增客户退钱或第二次到账。代码审阅/AST不记实际金融通过；六项新镜像严格原完整父后复验，原全193/环境/人工门槛保持。
