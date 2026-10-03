# PATCH-M8-1-WAKE-OBSERVATION-01

2026-10-03，M8.1收口。完整CI37000183906实际57执行/56通过/1失败，唯一失败是reports-complete-source-hk152-153授权阶段的旧唤醒行全值比较；原件下载在外部closeout-20261003/prior-ci。

允许仅修改 `tests/browser_click/report_complete_source_business.py` 的旧WakeEvent保护断言：不可变信号来源、员工门店引用、信号内容及created_at必须保持；原后台正常分发允许state/attempt/version/next_attempt_at/dispatched_at按状态机改变。保留新访问回执信号准确门店/数量、原业务全部行及审计回执断言，不扩大允许的原业务写入，不关闭worker，不把后台调度暂停以掩盖并发。

这是执行器观察合同修正，不改变产品，也不覆盖旧失败。新完整场景必须运行后方可登记通过；如仍出现新无关source信号另行定位，不删断言求绿。
