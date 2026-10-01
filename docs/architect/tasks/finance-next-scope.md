# 下一条客户预收与期间结算原链

2026-10-01，负责人 test_inventory。根授权只读研究及本独立页；会员834行候选保持冻结。本页没有新增脚本、生产或fixture，没有注册、app导入、业务实例、浏览器或SQL写入，也不继承历史通过数。实施须根登记精确补丁与写入窗口。

## 推荐五个完整 check

建议仅 HK-087-business 财务预收款、HK-090-business 其他收款单调整、HK-091-business 客户应收款查询、HK-093-business 预收款退款、HK-096-business 客户月结处理。HK090本批选择独立客户预收更正支路；会员本金更正、已退原款更正及组合完整性分支仍另列未执行条件，不据此声称该域全部异常通过。HK017及HK088仅发生客户其它服务来源支路，厂家vehicle_income未办理，不能提交这两项完整business check。

原193目录财务23项为既有收款、退款、误记调整、预收、客户月结/期间核对及开票。没有借款、资本投入或任意内部转账的独立原需求check；serviceOrderNew原提示明确“其它客户服务仅用于有依据的客户服务收入，不登记借款、资产处置等非客户收入”。不得用legacy Cash新增或其它收入强行伪造这类链。实际店间调拨清算属HK084，另需两店原调拨和真实双方批准/支付/到账前序，不纳入本次最小链。

## 同轮最少来源与岗位

客户只取同轮 passed 的 sales-order-hk008-009-011-022 检查点 report_sources.customer_id；账户只取同轮 passed 的 vehicle-purchase-hk171-177-178-026-021-018-029 的 HK021 payment.account_id。核每轮完整注册、对应checkpoint完整通过、有限ID、来源五字段与镜像/脚本/目录指纹一致；只核该客户/账户的本店、当前有效及当前随机岗位，不挑全库最新Cash或demo。

复用 business_fixtures.sales_order 的 sales_peer/service/manager/finance 岗位和门店1 UserStore，新增角色及fixture成果均为零。真正的新业务前序由原UI产生：

1. manager进入 #service-orders，点 data-act=serviceorder-master/data-kind=income-items，原“新增其它服务项目”填本轮唯一code/name、unit=次、standard_fee=60.00；POST /api/service-orders/income-items 返回 ServiceIncomeItem ID。此表是 service_income_items，既有master财务字典或维修/代办项目不是其替代来源；不得借demo项目或通过fixture造主档。
2. service在原“建立客户服务”选择“其它客户服务”、明确该客户、“不关联销售”“不关联车辆”“允许后续办理”，使用原UI给出的业务日期/期限；POST /api/service-orders 生成A/B两张 other_income v2原单，保留各 Case/ServiceOrder ID。选择不关联销售，避免无关地改变已交车原单版本。
3. 各原“项目及报价版本”只选该新项目一个fee行，quantity=1.000、price=60.00、discount=0.00，其余原新增行保持不使用。quote/approve/authorize/fulfill按 service→另一manager→service办理；每项批准、授权及实际履约使用不同本单authorization原件，原任务必要时主管明确交接给当前本人。原 ServiceQuote/ServiceLine/ServicePriceApproval/ServiceAuthorization/ServiceFulfillment 冻结正确，各净服务费6000分，无pass代缴本金、资金及集团权益。办结和到账独立，履约后原收款task仍open。

原服务费用以及随后全部账目都是外部合成输入；不冒充真实公司履约或银行收付。两张源单未付足时不能写completed或人工验收通过。现销售及维修主链若已结清，不能把其空余额当本批应收来源；须先真实产生以上两张新来源，并核同一客户目前可结算来源正好为这两个有限ID。

## 顺序、整数金额与原接口

下表金额均整数分；前端输入元，服务数量1000为1.000。正确90元的合成款被故意误录为100元，再由独立原更正流程订正，这是本批明确错误录入情境，不是实际退款或增加另一笔客户到账。

| 顺序与 check | 原UI输入和API | 精确结果与守恒 |
| --- | --- | --- |
| 新源后非空查询 HK091 | #business-finance/{customer}；GET /api/business-finance/sources?customer_id。逐行原业务号、未结金额、原ID与UI一致，查询前后全部原业务快照不变。 | 首次A6000/B6000，不能把空列表记通过；抵用后A2000/B6000；两笔月结后两单应收0。原 PaymentLink、ServiceTenderSlice 与 FinanceCreditLink 分别计，不以任务关闭代款。 |
| HK087预收实际登记 | service原“申请登记客户预收” purpose=advance、amount=100.00及原因；POST /api/business-finance/orders。finance原“登记本次实际收付款”选同轮账户、唯一原流水及receipt原件，原actions/execute。 | FinanceAdvance initial=balance=10000、reserved=0；唯一receive Entry10000引用唯一Cash入款10000，原单/财务任务/FinanceEvent/Receipt一致。普通客户预收不增加 GroupMember 本金。 |
| HK090预收误记更正 | finance真实展开secondary“原收款记错了，需要更正”，点“更正预收／会员充值”；原receipts GET只选上述精确Cash ID对应日期/账户/流水标签，purpose=stored_correction，正确金额90.00、原账户、不同正确流水、原业务日期和明确误记依据。独立manager批准，finance按批准内容执行。 | source_version绑定当前FinanceAdvance；FinanceStoredCorrectionRequest保留原10000/正确9000，批准reserved=1000，执行追加原10000反向Cash及正确9000入款，AdvanceEntry correction=-1000；initial=10000/correction=-1000/balance=9000/reserved=0。原Cash、原receive及流水不可改写。不是advance_refund，集团本金/权益完全不动。 |
| HK087明确抵用A | service在该原预收“申请抵用”40.00，按原单号及当前未结明确选A；purpose=advance_apply含advance_id/advance_version/target_case_id/target_version。另一manager批准，finance本人execute时携带新的source_versions。 | 批准前不扣余额；批准占4000，执行负apply Entry4000与FinanceCreditLink A4000、ServiceTenderSlice信用分配；无Cash、无PaymentLink。Advance余额5000/占额0，A未收2000。原A的 serviceorder_receive 待办须由manager提前转给同finance本人。 |
| HK096两原单期间月结 | finance原“建立期间月结”填包含两源business_date且不超过今天的明确开始/结束日；purpose=statement。manager独立批准，finance原“登记真实到账并分配”两次3000与5000。 | 冻结两条 StatementLine：A2000/B6000，总8000及revision1/digest。第一笔分配A1000/B2000，第二笔A1000/B4000；两Cash分别3000/5000，各一个CashBatch、两个原PaymentLink/Allocation/ServiceTenderSlice。旧冻结行不覆盖，分笔累计8000，源当前版本、本人任务及剩余正确，最终月结及两服务原单各完成。 |
| HK093原未用预收退款 | service对上述原Advance“申请原款退款”50.00，purpose=advance_refund含原Advance ID/version；另一manager批准占5000，finance同当前有效原账户、不同退款流水与receipt实际execute。 | Application kind=refund/requested→reserved→applied，负refund Entry5000引用原receive；唯一Cash出款5000，使用更正后的有效原款账户。Advance balance=reserved=0；已抵用4000、月结实收8000、原预收及更正记录保留，不把抵用回退或会员本金当客户现金退款。 |

服务原动作 POST /api/service-orders/{case_id}/actions/{quote|approve|authorize|fulfill} 使用request_id/version/values。财务原动作 POST /api/business-finance/orders/{case_id}/actions/{approve|execute|collect} 使用request_id/order.version/case_version/values；approve/execute/collect的source_versions须按原UI真实GET生成，不能取旧checkpoint版本。Statement批准原服务比较当前due及amount与冻结line；collect逐源严格版本/当前未收/冻结剩余。旧结果未知或409即保留原件停止，不替换request_id盲重放。

source收款待办与财务办理待办分开：原A/B分别serviceorder_receive，财务办理分别business_finance_review及business_finance_execute。_source_assignee要求finance本人实际接手原源单任务，只有审批表单获权还不够；manager通过原AssignInput转交，不能fixture改Task或管理员绕过。Quote/授权/履约任务同样以当前实际本人守卫。

## 页面合同与尚无运行结论的缺口

上述页面和表单均存在，不需要新UI或产品设计。真实选择器为 serviceorder-new、serviceorder-master、serviceorder-action，business-finance-create和business-finance-action；财务原页面标题分别“业务财务结算”“财务业务办理”。更正入口secondary默认折叠，必须实际点击原details summary展开后点击，不能force；服务quote是原modal动态fieldset，不能用通用原单表单猜字段。

服务项目主档不属于现有master checkpoint的typed字典，故不能只拿HK185 Reference ID直接填income_item_id。这是前序数据缺口，应原UI新增一条，不是需要fixture成果或放宽后端。当前来源的实际Customer/Account/本人UserStore、无其他未收同客户来源及无经营主体策略须在新镜像重验；有新增策略或来源冲突则失败留证另登记精确范围。

文件类别必须沿每个原表单：服务批准/授权/履约用authorization，财务独立批准用evidence，财务实际收退款/collect用receipt。每本单/每事实文件不同SHA；实际上传不等于客户签字或病毒扫描。验证文件字节只能在内存与选中外部输入比较，checkpoint仅metadata/长度/SHA，拒绝bytes、密码hash或会话hash落证据。

暂未运行，不能确定原表单布局、响应等待及SQLite并发没有硬bug。若遇到原拒绝需区分产品/装置；必须保持原错误、完整DB不变判据。可在HK093申请前实际填60.00（余额50.00）验证原确定409且无业务改动，再原关闭/明确放弃后提交50.00新申请；不得将未知结果重放或取消当通过。实际自批/跨店/同request重放、重算追加账单、原已退更正等条件另保留，不以规划计成绩。

## 数据保护、输出与终局

允许事实仅本次原 ServiceIncomeItem/ServiceRequest、两源 Case/ServiceOrder/Quote/Line/PriceApproval/Authorization/Fulfillment/TenderSlice，明确原 FinanceOrder/Advance/AdvanceEntry/Application/CreditLink/StoredCorrectionRequest/StoredCorrection/Statement/Line/CashBatch/CashAllocation/Event/Receipt，所需原Case/Task/FlowEvent/Audit/File/扫描及当前同账户version/updated_at。每次先原登录，再取全原业务基线；只允许该动作有限ID/列变化及精确新增数，旧Cash、旧余额来源、原已付款/退款、他店及所有无关旧行保护，不全表排除audit。

本链不新增修配/库存/物资流水、销售交车或资金、代缴/第三方收支、会员本金/卡/有效期/积分/权益/组合流水。membership_points.supported仅详细repair和retail，本次other_income不产生积分claim；invoice.sync_source对这些新服务没有原发票差额时不新增开票，不能借“派生”放宽全域。已有会员候选若同轮已passed，完整Group及会员账表逐行/字段不变，包括金额和版本。

终局预期：AdvanceEntry 10000-1000-4000-5000=0；Cash净额10000-10000+9000+3000+5000-5000=12000，等于两已履约服务费合计12000；客户预收抵用4000加实际月结8000等于两服务应收12000。误记冲回、正确重记、实际退款分别保留，不按一张页面金额推事实。

未来checkpoint建议 finance_sources 明确 customer_id/account_id/income_item_id/service_case_ids/quote_ids/advance_case_id/advance_id/original_advance_cash_id/stored_correction_case_id/stored_correction_id/corrected_cash_id/apply_case_id/credit_link_id/statement_case_id/statement_id/collection_batch_ids/payment_link_ids/refund_case_id/refund_cash_id。这些均由本次UI生成，消费者只能依同轮已passed的有限输出读取，不从全库扫描。

人工简洁度/文案、员工试用、银行、真实履约、ClamAV、经营主体、PostgreSQL、跨店及193完整业务验收保持pending/false。这里的5项是候选范围，不是已执行成绩。

## 源核验指纹

原需求表source SHA256 ddf297678e5d6d35e1dbfffc5c232c3d56748934eb22b58bbb9f9d5343689aae；requirements_manifest为19840f4fc5fd816d94ea35a4602a31bde4674105e44621eeb4cfe42bdad27a1f，193项；business_acceptance_catalog为eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff。5个原标题/check已实际核对。

本次只读源码：business_finance_api 5d582589f56b8b9dbe047aafe1c9a496230b7a0f75b442151023b234ad28ccd5；business_finance_service 790f96d4f34694412faaab87aae867e1168a4c1cb5ea6bd6e5c11867aa2b2b7e；business_finance_sources 619ce61174da01ad254d314e98b6a70cbf63a8dd1f6a976d8ad2a34ef57166d9；business_finance_stored 27bb1dc5ffde0789203760d553a2c0aceac0fec4aed575a7b8420ecc6e55b97d。

service_orders_api 8f1145db0749807cb2a233ff55704442e789b6e10607bf9c88d622ab93e2fbd4；service_orders_service 47110414c7510e44b39a7d28c1416f43323310539774c1cf3b992b8ee66ec06a；web/businessfinance.js f34d7cc7636b0d259e24a76ccef423399ae88501cede0a1f59fac1a643f24c27；web/serviceorders.js 9883c488822e00a8d1bab03b3b42d716f49c717bd60aa8627e04a6085e5de3d3。本页只读设计，未创建finance_business.py。
