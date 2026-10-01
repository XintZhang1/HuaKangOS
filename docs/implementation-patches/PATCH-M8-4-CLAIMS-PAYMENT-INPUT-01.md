# PATCH-M8-4-CLAIMS-PAYMENT-INPUT-01

2026-10-01，M8.1。当前四组验证已退出。为后继原需求HK081更正提供真实输入，仅 tests/browser_click/repair_claims_business.py 在新修单任何第一笔到账之前于本轮外部 synthetic-inputs 声明客户1000分原银行BANK编号与故意录入ENTRY编号、当前原修单/客户/账户和日期；客户凭据明确真实BANK，原表可见 reference 填ENTRY。保险2000/厂家4000/内部5000及原核赔流程保持，数据库仅SELECT，不更正、不重放、不更改旧证据或生产代码。

同轮完整父结果返回该声明路径/摘要以及精确客户PaymentLink/Cash/凭据ID和两编号。原完整checks和全旧行保护不放宽；原claims04已通过的正确款不称错误，旧报告独立保留。该补丁只有以后全新原生点击完整通过后可供HK081；尚未执行更正、人工和全193仍待测。
