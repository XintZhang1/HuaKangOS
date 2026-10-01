# PATCH-M8-4-FROZEN-SOURCE-UI-FORMAT-01：冻结来源的原金额显示合同

2026-10-01，当前M8.1，仅tests/browser_click/finance_report_business.py的frozen_cell原UI金额格式，以及RECONCILIATION-COPY-01明示的有限来源枚举中文展示合同。automatic-business11已退出：34注册/执行、33passed/1failed、108完整check/111诊断，7709动作/3663点击/1299.56秒，源0ce46e44/脚本63e28f37稳定、0页面异常/外部、17合成/0真实。会员6与财务后继2本次整场passed；财务四报表前三项local passed，163首次遇cash_entries:1显示断言failed，原件保留，不计四项完整通过。

原web.money采用zh-CN两位小数和千位分隔；候选复用报告表yuan无分隔，实际136,000.00与期望136000.00不符，是格式观察缺口。只对冻结来源UI的金额用Decimal整数分生成逗号分隔两位小数；不去除金额/编号所有标点、不转浮点、不变DB/冻结manifest/CSV整分与九列字节验证。原报表原yuan保持，不改共享helper。

同时将已实际可见且源码核准的有限中文枚举按source分别期望；原真实reference/voucher_no必须原样优先，不能把恰为refund等凭据号码译成状态。未知来源/枚举仍依原值完整匹配，量/单位/CPS/原引用/前200及全CSV/差异/三版冻结守卫不降低。源名称UI映射只用于可读标签，原manifest key、source、CSV与数据库原键不改。关联手动实例也已正常退出，根才执行本修正；AST/独立短审后新鲜原链复验。
