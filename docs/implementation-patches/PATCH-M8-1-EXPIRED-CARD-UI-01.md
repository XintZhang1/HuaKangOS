# PATCH-M8-1-EXPIRED-CARD-UI-01

2026-10-03；M8.1 验证器适配。允许范围仅 `tests/browser_click/runtime_followup_closeout.py` 的 `followup_natural_expiry` UI断言和对应证据字段。

原 UI 对 expired 卡隐藏 ConfirmBar，且 ConfirmBar 是卡 section 的相邻元素。正式80场与独立26场重复均实际等到原30分钟截止后，脚本错误地要求 section 内保留 disabled 确认按钮而失败；此前结果不改写。

改为同原卡 ID 的唯一可见 section 显示“已过期”和“不能继续提交”，全页该 ID 的 confirm 和 ConfirmBar 均为0。保留真实原30分钟、未修改时钟/截止/卡状态、同源 Cookie/CSRF 原 confirm HTTP409、原卡/Step唯一性、依赖等待、无替代卡、原业务整行摘要和同 worker 后续 tick 断言。证据明确写隐藏且不可提交，不把隐藏写成 disabled。独立静态审阅通过；外部候选正进行实际期限验证，正式复验待执行。
