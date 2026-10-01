# PATCH-M8-4-MEMBER-CANCEL-IDENTITY-01

2026-10-01，M8.1。member-boutique01积分兑换负例在真实422后由finance点击取消，本次Order由service申请，原membership_service仅申请人/manager/admin可撤销，实际403“仅申请人或主管可撤销”正确；候选混用办理finance与撤销申请人身份。

全部关联进程退出后，允许只改 tests/browser_click/member_points_tier_business.py 中 rejected_exchange 的撤销前身份：原read_as(service)实际登录并读取本单，严格requested_by==本人、重读原Case/Order/Member版本，登录完成后才Guard基线，原UI点击cancel。原财务execute本人Task、422/409拒绝及精确原refusal与旧行保护不改；不增加权限、admin代办或API快捷提交。原UI向finance仍显示cancel属于资格展示边界另待精确评估，不将按钮存在当授权。AST/独立短审后同新九场景实际复验，原failed/局部诊断与未测131保留。
