# 第二批维修业务点击范围设计

2026-10-01，只读来源审阅。HEAD 为 `5069b2bcc9f580ebb9d70780769049a14a6de946`，工作树已有其他实施者改动；本页只新增设计记录，没有修改测试、生产、fixture 或目录，没有启动应用或执行浏览器。本页五项均为 `not_tested`，不更新里程碑、不继承普通维修六项成绩。

优先安排 **HK032 洗车开单、HK080 洗车收款、HK033 快捷开单、HK042 客户报销** 四个检查。HK081 原收款更正已有原接口和有限付款来源，但冻结首单没有已声明的误记事实；该项保持待前置，不能为测试冲正一笔正确收款。原目录 SHA256 为 `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`，稳定 check ID 分别为 `HK-032-business`、`HK-080-business`、`HK-033-business`、`HK-042-business`、`HK-081-business`。

## 同次首单来源

固定依赖 `repair-selfpay-hk031-034-044-049-053-079/business-checkpoint.json`，当前冻结候选 SHA256 为 `018051e5581597bde33a8395552329b00c741cb1d4d9f54f6261a44838d5647e`。文件存在和静态短审不是执行通过；后继必须先确认同一 evidence_root 的 `browser-click-report.json` 中该前序场景 passed、checkpoint complete/passed 且六个原 check passed，并核本轮源码、脚本、目录 provenance。单选后继而缺前序时明确失败，不扫描数据库挑旧单，不跨 fresh 借结果。

冻结首单输出的顶层 `report_sources` 只有以下有限键：

`customer_id`、`customer_vehicle_id`、`vin`、`appointment_id`、`intake_case_id`、`repair_case_id`、`quote_id`、`allocation_id`、`payment_link_id`、`cash_id`、`material_item_id`。

按这些 ID SELECT 重验当前本店原客户、CV/VIN/身份、接待与维修关系、当前报价、客户承担、RepairPayment→PaymentLink→Cash 来源及原 release 事件。工位 ID 从该 `repair_case_id` 的 `intake_repair_contexts` 或 HK031 的已观察 resource 取得，不扫全店工位。原 Cash、PaymentLink、RepairPayment、Quote/Line、授权、领退料、历史事件作为不可覆盖旧事实保护。

首单到店、开工和离场已经改变 CV 的版本；后继只比较客户/VIN/身份等稳定来源字段，读取当前 version/updated_at 后按原 UI 提交，不能要求客服旧 checkpoint 的整行 CV 仍相等。物料的当前版本、数量和价值也已被采购、盘点、移库及首单净领 1250 milli 改变；不继承主档零库存或材料 checkpoint 的旧余额/整行。若后续确需配件，只从同轮材料 `material_sources.primary` 的明确 item_id、source_location_id、enrollment_id、原 Receipt/StockMove ID 取源并重验当前原余额。本批建议洗车/快捷均为作业行，不为凑覆盖再消耗材料，不声称另一次领料检查。

客户报销另依赖同轮原主档场景 passed，取 HK172 的实际保险公司 row ID，核当前本店启用状态。原五个 repair 角色合同继续使用 manager/service/technician/inventory/finance；不新增登录身份，不借 admin。若任务负载分派给 demo 员工，manager 从该原单“岗位交接”真实选择同岗位随机员工，提交原 `/api/flow/tasks/{id}/assign` 的 version/assignee_id/reason。

## 新洗车与快捷单：从配置到实际离场

原入口为 `#service-intake/resources`、`#service-intake/appointments`、`#service-intake/appointments/{id}`、`#repair-orders/{id}`。原源码为 `web/serviceintake.js`、`app/service_intake_api.py`、`app/service_intake_service.py`、`app/service_intake_models.py`、`web/repair.js`、`app/repair_service.py`，工作流来源为 `wf-repair-intake`、`wf-repair-complete`。洗车和快捷各产生一个新原单，不能拿首单 regular profile 重复判三个需求通过。

1. manager 原 UI 点 `[data-act=intake-resource-new]`，分别建立洗车工位 `resource_type=wash` 和维修工位 `resource_type=repair`。POST `/api/service-intake/resources` 的真实返回给出 ID，不预置工位或写 active_case_id。
2. 为作业含义明确，建议在原 `#masters/work_items` UI 建立本批“合成洗车”“合成快捷检查”两项作业，实际 billing_unit=job、启用、标准数量 1000 milli，标准费用分别显式声明为 10.00/20.00 元。它们是本次原 UI 配置来源，不新增 HK175 通过数；不把既有通用“合成按项检查”改一个 profile 就宣称已测试洗车项目。具体合成费用在候选中输入前固定，不从毛利反推工资成本。
3. manager 点 `[data-act=intake-preset-new]`，在“新增快捷项目预填”原 modal 分别选 `profile=wash` 与 `profile=quick`，只填对应实际 WorkItem 的 `[data-work-id]` 数量 `1.000`，其他作业留空；POST `/api/service-intake/presets` 产生 QuickPreset/QuickPresetLine。核当前启用组合、profile、原工位类别、实际项目/数量。组合与作业在转换期间不得被修改；预设行只保存 WorkItem ID/数量，不能虚称它冻结了 WorkItem 的价格版本。
4. service 点原“现场来访／当天排队”或预约入口，选择首单实际 CV、当前空闲的新工位、明确的新 preset、计划时段及实际诉求，POST `/api/service-intake/appointments`。两个新单依次完成，第一张新单实际 release 后才记录下一次到店。时间按 Asia/Shanghai 和页面实际可接受时段输入，不用 host UTC 日期或固定 sleep。
5. service 在该接待原单真实上传本次独立核验文件，点 `arrive`，填写同一实际 VIN、非回退且已声明的本次里程、原文件，POST `/api/service-intake/appointments/{id}/actions/arrive`。核唯一 `intake_arrivals`、原 CV 与新 appointment，之前的实际来访区间已经结束。不得由 fixture/SQL 创建 ArrivalFact 或 GateVisit。
6. 同原接待点 `convert`，给当前 version/request_id 和实际预计交接日期；唯一新 Repair Case 必须 flow_version=4、profile=wash/quick、绑定同 CV/VIN、context 引用本次 preset/appointment。转换由原 service 同事务生成初版 RepairQuote/RepairLine，按转换时启用 WorkItem 的标准费和 preset 数量核逐行 digest；不再提交另一个 quote 去覆盖这张自动生成报价。
7. manager 独立 `price_approve` → service 上传本版客户授权并 `authorize` → technician `start`/实际工位 acquire → technician `finish` → service 本版 `quality(passed)` → manager `allocate` 客户全额承担。分别留当前 Quote、Approval、Authorization、RepairWork、ResourceUse、Quality、Allocation 原事实。纯作业预设没有配件，不伪造 issue/return/StockMove。两单工资成本可分别显式声明为 2.00/3.00 元，并核原分值；它们是已知合成输入，不是猜算原库存成本。
8. finance 本人 `receive`，选择页面真实启用账户、独立收款凭证、实际金额及本次文件；service 在款项/质检满足后点 `release`。每单原收款、任务结束和实际接车分别核对，并刷新确认没有重复现金、报价或工位 release。

`app/service_intake_service.py:80` 拒绝 wash preset 配维修工位或 quick 配洗车工位；`:164–180` 是原转换及预填报价事务；`:333–366` 以原 ResourceUse/active_case_id 管施工占用。`app/gate_attendance.py:41–84` 以本次 ArrivalFact 和实际 `repair_v4_release` 关闭来访区间，`:103–114` 校验同 VIN 无重叠。计划结束时间不释放实际工位，Case state 本身不替代离场来源，本批不声称保安 GateVisit 流程通过。

| 独立 check | 必需新事实与显示 | 不足以通过的结果 |
| --- | --- | --- |
| HK032 | 新 wash Resource/Preset/Appointment/Arrival、唯一 wash Repair/当前预填行；主管授权、客户授权、实际施工/质检/接车及工位释放。原页面显示本次洗车及同 VIN/原单。 | 一张预约、转换成功、打开普通维修页或原 regular 首单完成。 |
| HK080 | 该 wash 原 Allocation→RepairPayment→PaymentLink→Cash，当前本店真实账户、原金额/凭证/日期/actor；到账前后 customer_due、款与实际接车各自有据。 | 计划收款、任务结束、服务顾问接车、会员核销或普通维修的旧 Cash。 |
| HK033 | 另一张 quick Resource/Preset/Appointment/Arrival/Repair；转换原 Quote/Line 精确对应本次固定组合及转换时原费用，完整授权/施工/质检/承担/到账/接车。 | 仅快捷预填、洗车单的共享步骤或覆盖旧 Quote。 |

## HK042：首单实际自付款的客户直接报销

最短路线选 `customer_direct`，不同时扩 `customer_via_store` 或原维修第三方应收；完整外部核损、核价、提交、结果与独立报销批准仍是必要步骤。原源码为 `web/claims.js`、`app/claims_api.py`、`app/claims_service.py`、`app/claims_models.py`、`wf-customer-reimbursement`。

1. service 从首单 `#repair-orders/{repair_case_id}` 的 `[data-act=claim-new][data-source]` 建立新核赔申请。明确选择首单当前源 version、HK172 真实保险公司、中文“第三方直接报销给客户”。POST `/api/claims` body 携带 `source_case_id/source_version/party_type=insurer/payer_id/payment_route=customer_direct`；新 Claim Case parent/source_snapshot 绑定首单同客户及报价，不能默认挑 sources 第一项。
2. service 原 `assess` 只选首单当前 Quote 的明确作业行。按已声明合成核价、原数量和原金额上限填逐行金额；其他配件行取消选择。POST `/api/claims/{id}/actions/assess` 产生本版 ClaimAssessment，保留原 quote_id/digest/lines，不更改首单 RepairLine 或客户承担。
3. manager 以不同于申请/核价人的身份 `approve`；service `transmit` 记录明确的合成外部受理号/实际提交日，再 `result` 记录独立合成外部核准结果、实际日期、对应 transmission/assessment/逐行金额。不得由一句“保险已批准”或上传文件跳过这三个原事实；合成文件不认证真实保险公司结论。
4. manager 独立 `reimbursement_approve`，必须不同于申请人、核价人及 result.actor，实际金额大于零且不超过 `customer_reimbursement_available`。原净额为首单客户实际现金净付款，扣其他批准/已付客户报销占额，会员权益不能折现。
5. finance 当前 `claim_reimburse` 本人 `direct_confirm`，引用本次实际第三方付客户的合成凭据及精确金额。POST 的 Direct 合同只有 amount_cents/evidence_id，没有门店 account/reference。核唯一新 `claims_customer_payments(purpose=reimbursement)`、business_date/actor/result/approval 关系和 Claim completed。该步骤 **不得新增 CashEntry、PaymentLink、RepairPayment 或 ClaimCash**；首单到账和原分配不改变。刷新后不能重复客户报销记录。

Claim 命令同时携带新 Claim.version 与首单当前 source_version，源码会 touch 两张 Case。每步按页面原 GET 的当前版本办理，不用冻结首单旧整行强等，不盲重放 409。首单其他客户、库存、会员、付款旧行保持；允许有限本源 Case/version/tasks/events/新 Claim 事实，不能粗排除整个资金表。

每个核价批准、外部提交、外部结果、报销批准、实际直接付款的文件必须本 Claim 新上传、可用、不同字节，不能借首单旧文件或重传同字节当新事实。非财务步骤后端 `_proof` 要求 `authorization`，实际付款要求 `receipt`（`app/claims_service.py:52–60`）；原页面“本理赔单原件”的说明也如此。当前 `web/claims.js:77` 动作表单却统一声明 `file_category=evidence`，导致就地上传提示/可选上传类别与守卫不一致。原通用 file lookup 没有按该 hint 限制全部既有候选，因此候选可从原文件面板按正确类别实际上传，再通过可见 file lookup 明确选用；不能注入隐藏 ID 或把错误 evidence 接受为正确。此静态提示差异需实际点击留证后由负责人判断产品补丁，不在本只读任务修改生产。

`customer_via_store` 留 `conditional/not_tested`：将来须独立 pass_receive 原到店现金，再 pass_pay 引用该 ClaimCash 的 original_id 按原账户转付；不能引用首单 RepairPayment 冒充报销款到店，也不能以 direct_confirm 代门店现金。拒赔、补件、第三方调减、返还及跨店分支均不继承通过。

## HK081：现有首款能定位，但误记条件尚缺

首单的 report_sources.cash_id/payment_link_id/allocation_id 足以定位原款、已退切片及实际净分配。当前首候选在 receive 已核收款金额、账户、凭证、日期和文件一致，没有声明真实错误。因此 **不直接执行更正，不把正确凭证换一个字符串就写“误记”**，也不先 API/SQL 造错再修。HK081 本批保持 `not_tested`，reason 为“缺已声明的合成误记与正确收款依据”。若负责人下一批明确要覆盖，应在一笔新原 UI 收款提交前声明已知的合成正确凭据与错误录入字段，保留两边事实；此替代方案不能追溯改写当前冻结首单的事实或成绩。

条件满足后，最窄更正仅针对已知账户/凭证/日期录入错误、保持原正确实际金额和同维修分配，避免无依据新增未到账、退款、客户欠款或重新施工。原路径为 `#business-finance/{customer_id}` 的“其他操作/原收款记错了，需要更正” → 新 `#business-finance-order/{id}`。原源码为 `web/businessfinance.js`、`app/business_finance_api.py`、`app/business_finance_service.py`、`app/business_finance_partial_corrections.py`、`wf-cash-correction`。

1. finance 或 service 原 UI 提申请。GET `/api/business-finance/receipts?customer_id={明确客户}` 必须出现该现金的当前有效可更正来源；选择精确已查明误记款，按原剩余分配输入唯一首单金额、正确账户/凭证/日期及实际理由，POST `/api/business-finance/orders` purpose=correction。`allocations[].source_case_id` 是原维修 Case；`allocation_basis=remaining_after_refunds`，总 amount_cents 是正确剩余分配合计加已实际退款，不二次退款。
2. manager 原 `approve` 不得等于申请人，保留独立证据；finance 原 `execute` 用 FinanceOrder.version、FinanceCase.case_version 和 affected source_versions。当前源变化、在办退款、更正或已批准报销占额须按原拒绝处理，不自动取消别人的流程。
3. 核 `business_finance_correction_bases`/真实退款切片、`business_finance_corrections`、reverse/corrected batch、allocation 和新反向/重记 Cash/PaymentLink/RepairPayment 的原关系。旧 Cash/PaymentLink/RepairPayment 不改不删，真实退款仍只保留原笔；反向调整不是新实际银行退款。更正后有效客户净付款必须匹配已声明的正确依据，原 completed/released 维修不能重复施工或接车。

原执行 `app/business_finance_service.py:610–643` 按冻结有效来源和原账户追加反向调整、正确重记，再 sync 原维修；`app/business_finance_partial_corrections.py:44–69` 校验原额、已退切片、有限 source IDs。没有实际旧退款时只证明该分支退款集合为空，不宣称“已有退款仍正确更正”也通过。

若 HK081 与 HK042 使用同一款项，合法顺序是**先有明确误记并完成更正，再按有效后继款源办理报销**；反过来已批准报销占额会被 `claims_service.guard_source_adjustment` 保护。不得为了跑更正把正常已报销 Claim 回滚、抹占额或猜填返还事实。

## 接线与证据建议

下一补丁可先授权独立候选，复用 Evidence 与第一批小型 UI/只读 Guard，不增加通用框架：一组洗车/快捷三检查（拟 `repair-wash-quick-hk032-080-033`，timeout 300），一组首单客户直接报销（拟 `repair-customer-reimbursement-hk042`，timeout 180）。首单与主档同轮已通过是硬依赖；4–5 项增量的耗时仅是设计预算，尚无实测。不注册缺误记条件的 HK081 空场景，不用 skip 记通过。

各 check 单独 acceptance_checks、真实 click/actions/native responses、精确本源 DB 事实、失败截图和 terminal status；HK080 允许引用同新 wash 单的实际收款证据，但不能以 HK032 的最终 completed 代收款检查。每个正向 submit 保护其他原业务旧行/他店来源，读页/刷新做全业务摘要零写入；历史事件/资金/库存只允许当前明确源追加及原状态机有限 mutable 列。每张新 Case 的 Task 负责人、文件、授权、现金、Quality 和 ResourceUse 都分别记录，不用 counts 替代旧行摘要。

后继 checkpoint 建议有限输出 `wash_sources`、`quick_sources`：customer_id/customer_vehicle_id/vin/resource_id/preset_id/appointment_id/intake_case_id/repair_case_id/quote_id/allocation_id/payment_link_id/cash_id；`claim_sources`：source_repair_case_id/source_quote_id/source_allocation_id/source_payment_link_id/source_cash_id/claim_case_id/assessment_id/transmission_id/result_id/reimbursement_approval_id/customer_payment_id。它们是待编码合同，当前没有生成结果。若之后更正已改变有效现金，应另外保存 correction Case 与有效后继现金/付款 ID，不把旧 report_sources 偷换成新 ID。

人工简单流程、文案简洁/误导提示、员工效率仍 pending；`business_accepted=false`、`full193=false`。本轮不声称真实保险审批、真实银行付款、保安进出厂、ClamAV、经营主体策略、PostgreSQL 或员工试用通过。洗车/快捷施工与付款均为隔离环境中员工原 UI 对明确合成事实的记录，未来须由负责人统一实际运行后据证判定。
