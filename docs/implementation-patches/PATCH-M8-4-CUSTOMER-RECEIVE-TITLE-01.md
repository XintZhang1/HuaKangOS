# PATCH-M8-4-CUSTOMER-RECEIVE-TITLE-01

2026-10-01，M8.1。customer-followon01 本批other_income已原授权/实际办结并上传原收款凭据，但尚未提交receive；67失败图原弹窗与web/serviceorders.js均为“客户实际到账”，候选income期待“确认客户实际到账”误配。原四必填/财务当前岗位正确，无产品收款失败结论。

关联实例全退出后，只允许customer_followon_business.py的该income modal expected标题改为原文“客户实际到账”。不加兼容别名，不改生产文案或削弱金额6000/CAS/Task/原账号/ServiceReceipt/Payment/Tender/精确双Audit及全旧行。原source7父/source/runtime/provenance守卫保持，AST/独立短审后同新8场景首次收款与后继7项复验，旧失败原件不覆写。
