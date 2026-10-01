# 任务：原收款更正及其余财务需求范围

2026-10-01，root 只读研究。当前四组浏览器运行冻结生产和已注册脚本；本文不执行、不注册、不改变来源。原需求为 HK076 代办服务收款、HK078 整车收款单调整、HK081 维修收款单调整、HK086 物资收款单调整、HK088 其它收入单收款、HK092 收款单退款申请，共六个完整 business check 的候选范围；实际结果、体验和全193验收仍待测。

## 有限同轮来源

所有父场景必须在同一全新镜像和隔离库实际 complete/passed，逐完整 check passed，源、脚本、manifest/catalog 指纹一致。后继消费当前原单版本并保护历史事实；不从其他 run 拼数据、不用局部父结果、不 SELECT latest 补来源。

- HK078：待实现并实际通过的 sales-pdi-addon-hk037-065-075 新销售单第一笔收款。父必须在首次原款提交前，外部合成输入明确实际 BANK 编号与故意录入的不同 ENTRY 编号、金额和原账户；后继只修真实预声明的误录。绑定新单、VIN、PaymentLink/Cash、原凭据路径与摘要，第二笔原收款和交车原件保护。
- HK081：不能使用首维修已经用于报销的原款，claims_service.guard_source_adjustment 会拒绝已有报销使用或批准待生效责任调整。候选来源为本轮新 repair-claims 的客户承担1000分；保险2000、厂家4000、内部5000互不替代。当前注册 claims 的三个原流水都正确，不能事后称其误录。需要另登记并在所有当前进程结束后实施极小父输入补丁：在任何首次客户款提交前预声明 BANK/ENTRY 差异，原 UI 填 ENTRY，原凭据明确实际 BANK，返回有限来源；再在全新 run 重做完整 claims。当前仅研究，没有修改 claims。
- HK086：待实现并实际通过的 retail-remaining 新 A 独立 Retail 原款2500分，已原路退1000，剩余1500；父同样在提交前预声明 BANK/ENTRY 差异。不能改采购供应方付款或 RetailGroup 原款冒充客户收款。保留实际部分退货、原退款账户及 original_id、安装保留费和历史成本。
- HK076：sales-followon 的 agency_case_id。HK015 已实际完成原当前二版报价、服务费2500与代缴本金1000的独立分桶实收，以及本金1000的真实 disburse；后继原页面核同一完整链，不能把 fulfill 当到账、不能重复收款。
- HK088：customer-followon 的实际客户 other_income 6000分与 sales-followon 的 manufacturer_income_case_id。后者已经有明确供应商、原已配车/交付销售、allocation_event、原应收两版与实际 receive/退款链；消费原真实来源即可，不为计数重复造新收入。核客户和非客户收入分别由其原接口、本人、账户、日期、独立凭据和整数金额产生。
- HK092：sales-cancellation HK010 同轮第二单，300000分原 deposit 与逐 original_id 原账户全额退款，净款0、解除占车、没有实车出库；消费该完整父的明确 deposit/refund metadata，不能用预收退款、服务余款或已交付单的零状态替代。

## 三笔实际更正的原流程

财务本人原 #business-finance/{customerId} 点“更正业务收款”，原 receipts GET 核 current cash_id/business_date/account/reference/金额/原 source。原选择 `original` 使用唯一可见完整 label，不猜 index；选择真正原账户，填预声明正确 BANK reference、理由，保留原日期。只给当前对应原单 `allocation_{caseId}` 正确剩余金额，其他真实原候选零值不产生分配。

原 POST /api/business-finance/orders 201，purpose=correction，values={original_cash_id,amount_cents,allocations,allocation_basis:"remaining_after_refunds",account_id,reference}；UI 自动把已退款加回 gross amount。不同 manager 从原任务独立批准，原财务任务上传真实已核 BANK 凭据再 execute。原 source_versions 由该对话实际 GET 当前所有 affected 原单取得，Case/Order CAS、request_id 与独立事务不放宽。modal 可见再核 title，异步最终原 GET/标题完成后再继续。

HK078/081 没有原退款，gross/net 与原第一笔客户款同额；冲正原 gross 和正确重记各一新 Cash，相应 PaymentLink、FinanceCashBatch/Allocation、FinanceCorrection 和原来源合法同步均精确核对。HK086 必须 original_amount=corrected_amount=2500、refunded=1000、original_net=corrected_net=1500；追加 FinanceCorrectionBasis+精确原 RefundSlice，reverse/new Cash 各2500但实际分配只1500。原退款1000不再执行、不改 Cash/PaymentLink/原 original_id。原 source due、net_cash、原币种/日期/账户与三层退款切片守恒；不会重新施工、出库、安装或交车。

所有业务写入来自可见原 UI，DB 只 SELECT；每步新增和可变行由实际原合同有限声明，全部其他旧行/原 Event、Audit、Receipt、文件 bytes、Cash、StockMove、钱包流水保护。更正原 cash 仍 immutable。同步可能更新有限 Source Case/Task、原支付后继投影等，必须读具体 service 合同，不豁免整表或只核总额。原请求失败保留真实 refusal/错误/未知结果，不能换 request_id 重放、原地重试求绿。

## 原只读财务显示核对

复用三已完整父的 HK076/088/092 时仍实际登录对应本人、原入口读取详细现金/付款/第三方支付/退款事实及原文件 metadata，分页和数字来源核当前有限原记录；屏幕、图表或 completed 文案不能替代款。页面实际 GET 只读不新增业务，即便登录会话不计业务基线也须在登录完成后冻结。零欠额须连实际本金、账户、origin 和对应现金方向，而非只检查终态。

未测试分支包括零元撤错、跨原单改分配、原账户停用、日期改期、已批准占额冲突、同时退款/更正竞争、后继再纠错、集团/预收/充值纠错、真实银行到账、员工体验、PG/Linux、真实模型和生产启用；分别保留，不由本六完整候选或原193导航成绩继承。建议后续仅新增 finance_remaining_business.py 与 finance-remaining-click.md，有限单场景六 checks；待根明确登记和两个新父完成后实现/注册，当前没有脚本或实际运行。
