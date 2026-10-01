# 客户预收、更正、应收与期间月结原点击候选

2026-10-01，负责人 test_inventory。精确范围为 PATCH-M8-4-BUSINESS-193-13，依据已冻结 finance-next-scope.md（f7c9c637595f0af8fa79310b07d603b1f0c8945190eb013f9f5a9e08c4610ffc）。仅新增本页和 tests/browser_click/finance_business.py；生产、fixture、注册、runner、共享目录及计划均未修改。候选尚未注册或执行，不记运行成绩。

## 五项范围与原事实

原入口 finance-hk087-090-091-093-096，函数 finance_business，导出 FINANCE_SCENARIOS 一个场景，候选超时600秒。复用原 Evidence、随机本人登录、原员工选择器、原lookup和确定拒绝后明确放弃填写；不另建执行平台，不用API/SQL造业务结果。

| 原 check | 输入及必须产生的原结果 |
| --- | --- |
| HK-087-business 财务预收款 | 服务顾问建立明确合成误录100元的预收，财务原任务实际登记唯一入款10000分。后续客户明确抵用40元到本轮服务A，另一主管先批准占额，财务生成负预收Entry及正CreditLink/ServiceTender，抵用不追加Cash或PaymentLink。 |
| HK-090-business 其他收款单调整 | 财务从当前客户原款明细精确选上述Cash，声明正确90元、原账户、正确日期与独立流水。另一主管独立批准占差额1000分；财务执行追加原10000分冲回及正确9000分重记，AdvanceEntry correction为-1000。原Cash及receive Entry不可覆盖，集团本金及组合均不动。 |
| HK-091-business 客户应收款查询 | 先原UI真正产生A/B两张服务应收各6000分，再核非空原应收API/页面/ServiceTender一致；抵用后A2000/B6000，第一月结实收后A1000/B4000，第二笔后两源应收0。每阶段明确刷新整业务不变；初始空列表只作前置，不能代替本项通过。 |
| HK-096-business 客户月结处理 | 财务选择包含两服务业务日的明确期间，冻结两行A2000/B6000、版本1及原digest；另一主管独立批准。财务实际到账3000分分配A1000/B2000，再到账5000分分配A1000/B4000。每批只有一个Cash/Batch、两个PaymentLink/Allocation/ServiceTender，旧冻结行不变，原源本人任务及CAS必须当前有效。 |
| HK-093-business 预收款退款 | 余额5000分时实际申请6000分，必须原409且全部业务不变，原关闭及明确放弃填写后才提交新的5000分申请。另一主管批准先占5000分，财务用更正后当前有效原账户及独立流水实际退款。负refund Entry引用原receive，出款Cash唯一，Advance余额及占额均0。 |

HK017/HK088仅记录本轮客户其它服务来源支路为 partial，绝不提交它们的完整business check；厂家原收入及原款退回支路未执行。HK090会员/组合原款、已实退原款更正，HK096晚到款冲突、追加重算版本、跨期与跨店等均 conditional/not_tested；不拿本批正路径声称这些条件通过。

## 同轮有限来源及新前序

只取本轮 browser-click-report.json 已注册且 passed 的销售 sales-order-hk008-009-011-022/report_sources.customer_id，以及采购 vehicle-purchase-hk171-177-178-026-021-018-029 中HK021原payment.account_id。两个 checkpoint 必须完整通过、目录摘要和 origin/source/runtime/evidence/database 五字段一致；本候选与目录、售前、销售、采购脚本须匹配当前稳定镜像。数据库必须在本轮外部runtime，未读工作区库或.env。

复用 business_fixtures.sales_order 的 service、manager、finance身份及store1真实UserStore；新增角色、fixture及预置资金成果均为零。核实际客户归属sales_peer、启用本店银行账户。当前原合成实例无经营主体策略，候选明确核此条件，并照常调用原主体守卫；有实际策略即停止，不关闭守卫继续。

原UI新增一个 service_income_items 收费项目（单位次、标准6000分），不是HK185财务字典或维修项目。服务顾问原UI建立A/B各一张other_income v2，明确不关联旧销售、不关联车辆、不阻塞交车，避免改变无关已成交原单。每单仅本轮项目一行、1000数量、6000分单价、零折扣；冻结原项目代码/名称/单位及报价摘要。另一主管批准原价格，服务顾问分别上传客户授权及实际履约原件并办结。本批这些均是外部合成输入，不表示真实公司履约。

每单原 serviceorder_quote/approve/authorize/handle/receive 和财务原 business_finance_review/execute 均核真实任务本人；若默认归其它合成同岗员工，只由随机主管原UI明确转交。AssignInput只有version/assignee_id/reason，不编造request_id。实际收款任务提前交同财务本人，只有财务办理任务获权不能代替原源单任务。

## 原接口、版本与结果核对

正向提交只有原按钮及原表单确认；捕获本次POST及成功后的原GET，核同源Cookie、CSRF、x-app-request、当前门店、请求号摘要及状态。所有原按钮唯一、可见且可用；更正secondary栏目先真实点击原details summary，无force、DOM注入或HTTP业务写。确定409拒绝保持原响应和完整无写入，再点击原“放弃填写”；不重放未知结果或替换失败请求号求绿。

服务原接口 /api/service-orders/income-items、/api/service-orders、/api/service-orders/{id}/actions/{quote|approve|authorize|fulfill}；财务原接口 /api/business-finance/sources、advances、receipts、orders、orders/{id}/actions/{approve|execute|collect}。文件及任务仍用 /api/flow/cases/{id}/files、/api/flow/tasks/{id}/assign。

服务动作使用当前Case.version；财务动作分别携带当前Order.version、Case.version及原UI实时读取的source_versions，抵用申请还携带Advance/目标Case版本，误记更正携带当前原钱包版本。Statement冻结版本、期间、两行及digest保持；首笔未收足不能提前完成，后笔才能关原月结及两个源单待办。API Case/Order/Advance/Application/StoredRequest/Statement/Lines/Batches/Allocations与当前DB关键原字段逐项一致，仅数据库/JSON时间展示格式不按字符串比较。

ServiceRequest核原operation/payload规范化摘要，包括API Line默认空字段及master默认active；FinanceReceipt核action/完整values摘要。两者均要求本店本人、唯一原request_key，保存result等于本次原响应。FlowEvent及AuditLog严格一个事件对应一条审计，财务另有唯一FinanceEvent；不能只凭弹窗关闭或成功文案计通过。

## 数据与文件保护

每次原登录和待办交接后再取该业务动作基线。完整快照保护全部原业务表；仅本次明确追加表允许准确新增数，更新仅有限Case/Task/Order/Advance/Application/StoredRequest/Account ID及合法列。Service报价才准修改Case金额/data；财务Case只准版本/更新时间/状态/完成日。不删除旧行，不宽排除audit、Cash、库存、会员或附件。

服务新Quote/Line/Approval/Authorization/Fulfillment与原ServiceOrder冻结。每次抵用和月结只追加Credit/Tender/Payment/Allocation，旧事实逐行逐列保护；原预收、原Cash及原receive Entry在终局再次相等。会员身份、卡、期间、积分、权益、组合、本金及内部往来全表不在允许清单，每步保持完整不变。other_income不触发支持范围外的积分claim，无已有发票差额不放宽开票表。

服务批准/授权/履约各用独立authorization原件；财务批准用evidence，实际登记、更正执行、分笔收款及退款用receipt。每份外部合成TXT由员工真实选文件上传；核原类别、原单、本人、结构扫描、安全可用、完整实际blob等于所选字节及大小/SHA。正文bytes仅内存及旧行比较，证据只metadata/stored_blob.length/sha；无default=str/base64、User.password_hash、会话hash或随机密码输出。结构检查不是ClamAV或真实客户签字。

终局必须 AdvanceEntry 10000-1000-4000-5000=0；六份独立Cash净额10000-10000+9000+3000+5000-5000=12000；预收抵用4000加月结实收8000等于两已履约服务12000分。正确重记、误记冲回、预收抵用、实际退款分别保留，不用会员本金或任意资本/借款凑现金守恒。

## 状态、输出与交接

五check初始not_tested，实际对应动作及原DB/UI核对后才写passed；中途切换仍running的项保留步骤，失败时当前项failed、其它未终结running项partial，其余not_tested。只有五项实际完整完成，checkpoint.complete/passed才为true；193全业务、人体验、真实银行/履约/经营主体、ClamAV、员工试用、PG/Linux及生产保持pending/false。尚未运行不能声称没有浏览器或产品硬bug。

最终 finance_sources 只输出当轮有限ID：customer/account/income_item、两service_case/quote、advance_case/advance/original_advance_cash、stored_correction_case/fact/corrected_cash、apply_case/credit_link、statement_case/statement/batches/payment_links、refund_case/refund_cash。后继须读取同轮实际passed检查点，不扫全库挑最新资金。输入、截图、日志、拒绝原件和checkpoint均留原外部Evidence目录。

本候选已完成AST和有限SELECT-only、五目录原标题/check及原UI/API/schema/service/models的静态核对；未导入app、未启动实例、未调用浏览器。源码冻结指纹及独立短审结论由交接消息追加，根统一接线和新镜像实际执行。

作者静态收尾：1082行候选AST通过，7处DB调用全部SELECT-only（有限动态表/字段人工核准），32个允许表均在当前原模型实际存在，5个标题/source_reviewed/check与原目录精确一致，全部跨脚本helper存在，无app导入、业务HTTP写入、DOM注入或尾随空白。源码冻结SHA256为71152135cc82695572f57cd098096dfd4dd03cdae8212567b528c7a98c006763。独立交叉短审与实际执行尚待根协调；本页hash另报，避免自引用。
