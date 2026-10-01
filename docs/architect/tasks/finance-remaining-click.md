# 任务：六项原财务闭包点击候选

2026-10-01，PATCH-M8-4-BUSINESS-193-35。新增 `tests/browser_click/finance_remaining_business.py`；只写本候选及本文，没有修改原业务、夹具、既有 helper、runner、注册、目录或计划。代码已落盘并静态自审，尚未运行或注册，不能记六项或全193通过。

入口为 `finance-remaining-hk076-078-081-086-088-092`，函数 `finance_remaining_business(e, context, credentials)`；`FINANCE_REMAINING_SCENARIOS` 是一个三元组，有限超时1500秒。沿用原 Evidence 动作、截图、同源浏览器请求和只读 SQLite，不新增通用框架。

## 完整检查及原事实

- HK076 代办服务收款：消费 sales-followon 的完整HK015原代办单，实际打开本店原服务页。原服务费2500分与代缴本金1000分各自 Tender，客户3500分真实收款及代缴1000分实际出款分别核对；保留核价、授权、补件、外部结果和实际办结。不开新代办单或再次收付。
- HK078 整车收款单调整：消费同轮PDI完整HK037/HK075的第一笔5000000分原Cash/PaymentLink。首次原款前已外置声明正确BANK与故意录入ENTRY；实际原签回、交车VIN和第二笔8000000分原款保护。财务原UI同额申请、不同主管批准、财务本人凭据执行。
- HK081 维修收款单调整：消费同轮新核赔五项完整父的客户承担1000分，不能借首维修已用于客户报销的原款。原客户凭据类别为业务凭据，与原维修到账合同一致；保险2000分、厂家4000分、内部5000分不混成客户款。正确BANK/误录ENTRY事前说明与原施工、质检、承担、接车保护。
- HK086 物资收款单调整：消费 Retail A完整HK063/HK067原总款2500分及原实退1000分。原剩余1500分；冲正和正确重记Cash各2500分，FinanceCashAllocation及PaymentLink各1500分，追加唯一FinanceCorrectionBasis与精确旧RefundSlice。旧退款原Cash、account/original_id、金额及实物退货不改变，不再次退款、出库或安装。
- HK088 其它收入单收款：原客户服务其它收入6000分与独立厂家收入分别打开原页面；后者实际收10000分、两版独立批准改目标7000分、按原款及原账户退3000分。客户履约及ServiceTender与厂家VehicleIncomeCash分别核对，不用一个终态替代两种来源。
- HK092 收款单退款申请：消费同轮取消销售的完整HK010。定金300000分及同原账户、original_id实际退款300000分各自原款保护；原申请、不同主管批准、净额0和该取消单没有实车出库。后来PDI合法复用取消VIN不改本次原退订历史，不要求该车现在仍在库。

## 固定依赖与输入边界

六个直接父必须在当前 `evidence_root/browser-click-report.json` 中唯一注册且实际passed；其固定 `场景/business-checkpoint.json` 必须complete/passed、所需原business check准确通过。使用同manifest的source/runtime/database路径、catalog摘要与完整父candidate SHA，并核 `provenance.json` 的冻结镜像和当前候选/helper字节；不存在从上轮或扫描latest寻找替代来源。

父为 PDI `sales-pdi-addon-hk037-065-075`、核赔 `repair-claims-hk035-036-039-040-041`、Retail `retail-repair-return-bundle-hk063-066-067-068`、销售后续 `sales-followon-hk012-015-016-017`、客服后续 `customer-followon-hk100-101-102-103-104-110-111`、取消销售 `sales-cancellation-hk010`。这些父各自的原来源链也必须完整，局部成功不继承。

更正声明路径必须精确位于当前父场景的外置 `synthetic-inputs`，核原JSON bytes SHA、schema、原customer/account/VIN或case及原款有限ID。当前原Cash/PaymentLink必须与完整父原记录一致，原凭据bytes含事前正确BANK，保存报告只含文件metadata及长度/SHA。声明不等于银行认证，原输入文件仅是合成凭据。

复用现有 sales_order 夹具的store1 manager/finance随机本人身份，核真实UserStore、启用用户和店；原登录响应必须是当前一店真实岗位、非汇总。任务若原负载均衡选其他人，只由manager通过原三字段AssignInput明确转交，再本人办理。不能admin借办、自批、SQL造款或正向HTTP重放。

## 原请求与守卫

三更正原页面 `#business-finance/{customerId}` → 原可见完整收款label → POST `/api/business-finance/orders` 201，purpose=correction、原日期保留、`allocation_basis=remaining_after_refunds`，只给明确原单剩余款分配，其它可见候选保持0。大额label按原UI千分位显示，输入仍精确整数分换元。

不同manager原review Task上传独立业务凭据，finance原execute Task另上传正确BANK收退款凭据。动作各使用原Order/Case版本与实际原FlowCase GET得到的source_versions、原request_id/Cookie/CSRF、服务器真实回执和同次最终GET；原拒绝、未知结果或版本冲突停止，不生成新请求重放。

每次真实登录后再建立动作基线。有限Guard核全原业务表摘要、准确新增数量及有限当前财务单/Source Case/Task/account允许列；其余所有旧客户、现金、会员、库存、他店、事件、审计、回执与附件bytes不变。HK086批准时原source版本触碰单列声明，三execute按原source_sync允许实际有限变化，不豁免整表。三个新FinanceCorrection、六个Cash/PaymentLink/批次/分配与维修或Retail两个附属Payment各自精确核对。

原更正页资金表按两条实际批次逐列核gross总款及net原单分配、原业务按钮可见可点；HK086原退款文案和原凭证保留。原只读来源在本人登录后刷新核同GET、真实Cookie/门店和全库零追加；完成更正刷新核原资金与回执不重复。

## 静态审阅及待测

自审已逐项对照原business_finance_api/service/models、partial_corrections、source_sync、原web表单和各父实际helper参数/返回层级。只读发现PDI交车状态为delivered，而原source_details只接受executing/completed；已报根并由根另登记 DELIVERED-CORRECTION-01 窄修。原常规collect、advance_apply、statement仍不扩，原报价/售后与业务receive守卫保留；本候选保持delivered及交付事实不变。该生产补丁和候选均须新镜像真实执行，静态审阅不计通过。

尚未执行浏览器、后端业务、PostgreSQL、Linux、真实银行、真实模型或生产验证。未测条件包括零元撤错、跨单重分配、改期、停用账户、竞争占额/退款、更正后继、集团/预收/本金纠错、经营主体策略及ClamAV。人工显示、流程简易、文案、后端事实、硬bug和统一标准另行留证；人工体验pending，`business_accepted=false`、`full_193_business_acceptance=false`。
