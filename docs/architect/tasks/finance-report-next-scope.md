# 任务：财务与保险报表下一批有限来源

**任务与负责人**：`finance-report-next-scope`；`click_scenarios`。2026-10-01。本次只读核对193目录、原工作流、当前源码、外置结果和未注册来源设计；唯一写入文件是本页。未修改生产、测试、夹具、运行入口、目录或计划，未导入应用、启动实例、浏览器或执行业务。本页不是新增通过记录。

**目标与架构**：沿原专用业务模块及 DSH Architect 最近连贯增量，给下一批原生点击明确原来源与缺条件。每项仍使用 `HK-xxx-business` 和原标题；图、明细、原单、CSV同店同范围，现金、实物、集团本金、权益与内部往来分开。前端体验与文案判断仍需人工；自动检查不设置 `business_accepted`、`full_flow_tested` 或完整193验收。

**代码快照**：HEAD `8993ca8c755194a42a48e7323fe355e80c6bf9ae`，同时核对当前未提交工作树。目录为 `tests/browser_click/business_acceptance_catalog.json`，SHA256 `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`，14项均已有源码绑定。原API/UI存在不表示运行通过；未来执行须重新冻结整份联合镜像，不能仅凭同HEAD继承结果。

## 当前结果与下一批的边界

- `automatic-business-20261001-09` 外置报告是完整28/28、84个自动业务check的同轮结果。其中 `membership-hk117-128-118-089-094` 已独立完整检查 HK089/HK094；原11项报表已检查 HK160。三项无需再作为新增成绩。其人工标准及完整193仍未完成。
- `business-insurance-20261001-01` 是另一轮 selected 4/4，含保险七项。不能将它与28/84合成一次完整联合通过，也不能据此将下述保险报表记通过。
- 根报告 finance03 五组4过1失败；HK097局部已完成，HK095第三版由制备者本人封存被原403拒绝。整个财务后继场景未通过，故其局部原件目前不能满足新场景的 passed 依赖。根窄修使用已有本店 admin 独立封存第三版，原第二版仍 manager；原 `reconcile_seal` Task.role 保持 manager，实际接手者为 manifest.admin。脚本 `355e49520f3c323760996824ac062c0b2e5ecc8eebd88956d3d0ea128493d95e` 已只读核对接线和AST，尚不代表复验通过。
- `member-followon-hk123-124-125-129-130-132` 是作者正在实现的六项来源候选，已有部分代码及顶层来源输出声明，尚未冻结完整实现，也无执行成绩。本文消费券计划只使用其将来真正完成的有限原件；具体字段以作者最终落盘合同为准。赠积分不是消费积分。
- 原报表后继 probe 目前存在采购旧简表来源不足，整场未完成。根处理其局部来源口径；本文不继承局部 passed，也不改旧历史、日期或原来源。

未来完整33组是计划中的新同轮清单，而非当前已通过事实。最少先保证本文直接前序 complete/passed、来源与脚本指纹一致；任何缺项明确失败，不寻找另一个run补足。

## 逐项原合同与建议归属

| check／原标题 | 原UI／实际读取 | 本次判定与必需非空事实 |
|---|---|---|
| HK-088-business 其它收入单收款 | `#service-orders`、`#vehicle-income`；原各业务详情、原收款动作 | 尚无本check完整成绩。28同轮已有客户 other_income 与厂家 vehicle_income 两种真实支路，可作为明确有限来源；必须分别核创建、批准、本人 receive、原账户与实收，不能将 HK017 或五项财务通过自动映射成本项。 |
| HK-089-business 会员储值卡充值收款 | `#membership`；原 Membership topup→finance Task execute→Group topup | 28同轮已有完整自动check。原本金 GroupEntry、发行店、唯一 Cash 与余额一次；赠品不作本金或第二笔现金。后继只保护原件，不再报新增。 |
| HK-092-business 收款单退款申请 | `#sales-quotes`／`#aftercare`；原 cancel 或 Aftercare、原退款 | 尚无本check提交。28的 HK010 有真实未出库订单 deposit→取消申请→另一主管批准→逐 original_id／原账户退款，可明确复用此同轮完整支路，须另登记逐动作证据复用和本check的原款、保留费、实际出款校验。已履约售后分支无来源时仍 conditional 未测；不为凑数冲退正确账。 |
| HK-094-business 会员储值卡退款 | `#membership`；原 Group refund_request／approve／refund | 28同轮已有完整自动check，主管占本金与财务实际退回分开，未用未占额度、负向 Entry、原Cash关系保留。新组合整份回收不能覆盖原普通退款事实。 |
| HK-141-business 保险单分析 | `#analytics/sales`；flow GET，dataset=`insurance_policy_facts`／`insurance_commission_facts`／`insurance_commission_cash` | 推荐完整候选1。原 issued Result＋冻结 Quote 保费、独立 approved CommissionReview 目标差额、CommissionPayment 实际收退均须非空。保费220元代收／代付与佣金12元分开。 |
| HK-157-business 物资应收账统计 | `#table/receivables`；flow GET／CSV dataset=`receivables` | 现终局来源均已结清，不提交。需真实精品或加装商品／安装费未收来源，原价、已确认退货、净收、剩余一致；别用采购应付或其它收入欠款代替。 |
| HK-158-business 整车相关应收账统计 | 同原 `#table/receivables`，无kind参数 | 现车辆和关联服务终局已结清，不提交。至少有真实车辆订单未收及明确关联服务来源，含尚未到收款点的约定；同店原单、到期、累计结算、未收金额分别核对。 |
| HK-159-business 维修应收账统计 | 同原 `#table/receivables`，无维修专用伪参数 | 现首维修／洗车／quick皆已付款接车，不提交。需维修原 payer Allocation 下实际尚欠；内部承担另外核，不把服务报价、应收状态或任务结束当付款。 |
| HK-160-business 收款统计 | `#table/cash`／`#analytics/finance`；flow CSV dataset=`cash` | 28同轮已完整自动检查。未来联合可扩大原来源对照，仍同一项；实际 Cash 定义7＋关联唯一来源，不能加入第二笔本金、抵用或往来现金。 |
| HK-161-business 物资收入成本对照表 | `#material-value`；GET `/api/material-value`，CSV `/api/material-value/export/{key}` | 推荐完整候选2。同轮 AddOn、Repair、Retail 实际履约／原退及 StockMove 原成本；七张原表同范围，商品＋服务＋未分配调整＝对外净额，未履约领料成本独立。未知成本原409保持失败。 |
| HK-162-business 预收款统计 | `#table/finance_advances`；另 `#table/finance_advance_movements` | 推荐完整候选3。真实 Advance／Entry／Hold／StoredCorrection 非空；当前未用、占额、可用与期间实际变动分开。现最终余额0有完整100→90更正／40抵用／50退款来源，不要求造新非零余额。 |
| HK-163-business 财务结算统计 | `#reconciliation/{本次id}`；GET batch，CSV `/api/reconciliation/batches/{id}/export` | 推荐完整候选4，但依赖财务后继整场复验通过。原非空 Batch／Issue／Event／Receipt、definition22、manifest／summary／digest／CSV对应；版本1..21冻结。查询不重演或替代HK095办理。 |
| HK-168-business 会员积分统计 | `#analytics/members`；datasets=`benefit_points`、`membership_points`、`membership_points_debts` | 仅可计划赠积分局部读取；组合赠200／回收100不会产生原消费 PointsChange。缺有效会员服务期、消费积分规则冻结和真实支持的消费来源，不能完整通过。 |
| HK-169-business 消费券统计 | `#table/benefit_coupon`／`#analytics/members`；flow CSV dataset=`benefit_coupon` | 推荐完整候选5。作者计划真实 grant／capture／recover 与 purchase／capture／refund 有 signed units、原rule/version/wallet/source；占额≠核销。依赖六项会员完整passed，未执行不得填预计结果。 |

上述“已有完整自动check”仅引用同轮已实际结果，不表示人工验收已完成。“完整候选”指未来必须执行完整目录标准，并非本页登记passed。HK088/HK092若采用同轮来源复用，需根另登记精确 check 与原动作证据，不能因金额恰好相同、静态映射或打开详情自动增加两项成绩。

## 最小下一链：五个报表check

建议先新增一个独立原生报表场景，只有 HK141/161/162/163/169 五个完整候选；HK160为既有口径的联合复核，HK168明确 partial。无需新增随机身份、业务预置、通用框架或修改报表计算。只有根另登记候选范围后才能编码。

按原业务依赖执行同一次新run的售前→采购／主档→客服→销售／退订／加装→财务五项→财务开票核账→物资／首维修→普通会员→会员后继；保险七项也在此run内完成。实际注册顺序由根安排，依赖缺失就停止。再由当前店 manager 真正从帮助目录检索对应编号、点原入口，提交实际日期／筛选、看图、分页看明细、点原单、点原导出。预收财务、会员消费和保险终止后最终值可以是零，但原事实明细必须非空且按源全部留存。

消费来源只用本轮 `evidence/browser-click-report.json` 的已追加父场景 passed 行及以下固定 checkpoint 路径；均核 complete/passed、相同origin/source/scripts/catalog指纹，再只读重验有限ID。禁止扫描全库默选demo、取上一轮最新单或跨run凑源。

| 固定场景checkpoint | 有限字段及当前重验 |
|---|---|
| `insurance-renewal-hk013-014-077-113-114-115-116/business-checkpoint.json` | 当前实际SCENARIO；只取顶层 `report_sources` 的 customer_id/customer_vehicle_id/insurer_id/account_id、first_insurance_case_id/first_issued_result_id、new_insurance_case_id/new_issued_result_id，再沿有限Case读原 Quote／Submission／CommissionConfirmation／Review／Payment。 |
| `sales-followon-hk012-015-016-017/business-checkpoint.json` | `report_sources` 的 delivered_order_id/vehicle_id/addon_case_id/customer_other_case_id/manufacturer_income_case_id 及 material_item_id/material_warehouse_id/material_location_id/work_item_id/agency_project_id/supplier_id/account_id；保持原报价／授权／质检／履约／收退与全部旧附件，不从近似字段构造ID。 |
| `repair-selfpay-hk031-034-044-049-053-079/business-checkpoint.json` | 首维修 `report_sources` 的 intake_case_id/repair_case_id/quote_id/allocation_id/payment_link_id/cash_id/customer_vehicle_id/material_item_id；有限领1250→退250→补领250三条原 RepairStock／StockMove 与真实接车日。 |
| `materials-hk069-045-054-083-070-072-073-051-061/business-checkpoint.json` | `material_sources.primary/secondary` 明确 item_id/receipt_ids/stock_move_ids/entry_ids/warehouse_id/source_location_id；实际物料余额／版本可能已被维修、加装、会员零售改变，按有限ID现场读取，不要求仍等旧快照。 |
| `finance-hk087-090-091-093-096/business-checkpoint.json` | `finance_sources` 的 advance_id/original_advance_cash_id/stored_correction_id/corrected_cash_id/credit_link_id/statement_id/collection_batch_ids/payment_link_ids/refund_cash_id/service_case_ids/account_id。实际10000→更正9000→抵用4000→原款退5000分，剩余0；六原Cash保留，现金定义7排原误记与纯冲正，本批有效净12000分。 |
| `finance-followon-hk095-097/business-checkpoint.json` | `finance_followon_sources` 的 reconciliation_batch_ids/reconciliation_case_ids/issue_id/period/definition_version22/cash_definition_version7；取明确3版，不扫描店内最新批次。每版原manifest／summary／digest／前版关系保持。 |
| `member-followon-hk123-124-125-129-130-132/business-checkpoint.json` | 作者拟 `member_followon_sources`／`report_sources` 的明确member/customer、五Rule、四赠品与付费Wallet、Entry／Purchase／Capture／Refund、bundle原Posting、retailPlan/Tender/Capture、Eligibility/Decision/Binding。代码尚未定稿，本批先等待作者冻结实际键，不能在作者未产生事实时填计划IDs或余额。 |

最后两个尚未通过父场景不能作为本次执行来源；本文不先造这些检查点。已落盘原候选常量与字段经过只读核对；会员候选最终输出键尚未冻结，编码前须接收作者正式合同。

## 五项查询的精确源码条件

1. **保险分析**：原 `sales_service_analytics.py` 中 policy 表来自 `InsuranceResult.outcome=issued` 的实际 business_date 与对应 Submission.quote_id。政策事实表本身没有专属图，不能强造图。`insurance_commission_facts` 图／表来自独立 approved Review 的 target−previous；`insurance_commission_cash` 来自 CommissionPayment signed cents，日期分别沿各自原事实。原第一保费22000分的代收和代付不是佣金；实际佣金1200分，后续真实原款退回−1200分使净0但两条明细非空。新直收客户保费30000分不产生门店保费Cash。撤保后旧 issued Result仍是历史出保事实，不把它当当前仍有效保单；终局0图允许原“当前范围暂无可绘制数据”，不可删除负向事实或造非零图。
2. **物资收入成本**：原 `materialvalue.js` 的 `#material-value-filters` 只有 source/item_id/case_id，source原值 retail/addon/repair/stock。真实点击单一来源、物资、原单，再组合筛选；API回date/filter与当前店一致。七表是 `material_goods/material_services/material_unallocated/material_sources/material_actual_stock/material_other_stock/material_unfulfilled`。原源表保留相关原单全部商品、服务与未分配调整，选item不能将整单调整当该物资利润。会员纯集团零售计划 C=2500/P=S=1700 与800优惠只在真实parent完成后读取；原Cash0与外部履约对价非0分别核，不能再将集团内部双边往来加成现金或收入。原UI每表20条，需真实分页。专用CSV必须用本人适配器，现 flow helper 的else指向 visit-activity，不能误传material-value复用。
3. **预收款**：`business_finance_analytics.py` 当前表展示 original/balance/reserved/available/correction/effective，不随日期假重建历史。期间 `finance_advance_movements` 的有cash行用原Cash.business_date，无cash行用原event本地日；receive/apply/refund/return/correction各沿 Entry。原40元抵用是CreditLink，无新增Cash；100元误记→冲回→90元正确现金三笔保留。最终余额0不等于空来源。当前advance占额0可匹配无活动Hold，但不声称已测试非零占额；该异常仍条件未测。
4. **结算**：核原1→2重算、2→3复开关系、version/previous_id/status及精确Issue处理，逐版完整manifest重算原digest，再从实际浏览器下载九列CSV逐顺序核 revision/key/source/basis/case_id/amount或value/quantity/units/data。页面最多前200条，原提示保留；CSV核完整清单，不声称UI显示全部。后继会员或保险真业务若发生在封存以后，最新GET `source_changed=true`是实际晚到变化，应核原提示并保留冻结旧版；不能为了绿灯自动重算／封存，不强求false或拿当前现金替代原冻结摘要。原definition22，cashbasis7，与1..21历史冻结分开。原下载无export审计，前后业务摘要完全不变。
5. **消费券**：原 `flow_analytics.py` `benefit_coupon`按Entry.occurred_at UTC转换APP_TIMEZONE本地日，字段原rule_name/version、purpose映射、signed units与case路由。组合gift grant2/capture1/recover1、paid purchase2/capture1/refund1目前仅作者设计，不作为已执行值；实际消费后核原冻结rule版本与原wallet，未用申请占額另Reservation。单位张不与bonus分、points、package次相加；恢复、原退与退款按原purpose读，不把回收gift伪称现金退款。

通用 flow 原 GET `/api/flow/analytics?date_from&date_to`；CSV `/api/flow/analytics/export?dataset={原key}&date_from&date_to`。原UI不传tables，不应加kind/customer过滤伪造后端合同。HK157/158/159共享整张receivables表，当前待收是当前快照；日期表单与响应范围仍需核，但不能声称历史期末应收。`#analytics/finance`有“当前尚待收取”KPI→receivables，现没有专属receivables图，不强制不存在的SVG；现金原图 `cash_category`／`cash_trend`分别分类和期间走势。

flow CSV仅允许当前员工／当前店一条 `AuditLog(action=export,entity_type=flow_analytics,reason=原table.title)`；其余业务摘要／旧行不变。专用material-value导出原审计类别 `material_value_report`、reason为期间＋原key，使用源原格式，不能放宽整个audit表。其原API仍用get_db读取后追加审计，SQLite读后写事务风险需真实执行判断，静态不称已发现产品故障。CSV从原按钮下载后保存解析，不能额外读取下载response.body或再GET伪造一次下载。三类原CSV公式防护实现分别核，不以通用假定转义所有负金额。

## 仍缺来源的真实输入到结果链

### 三种应收：下一独立写入范围再登记

原28与未来33终局多为已paid/accepted/delivered/released，期间有中途欠款不能自动继承为后继报表证据。最小可复验路线是在新限定场景中各建立一张明确未收原单，完成其原批准／真实履约后暂停在实际未收点，manager真实查询／分页／原单／CSV校验非空due，再由财务真实逐原账户收齐并完成实物接车／交付。可以在一组内复用一次共享表导出，但三个HK独立核对应类型非空事实。

- **物资**：使用同轮当前Item/Enrollment/材料库位余额，原Retail或AddOn建立实际商品／安装行→独立主管approve→原授权→库存dispatch／实际accept，但在收费前检查净未收，再财务原收款闭合。不预置库存、承接上游已变余额、造另一个“采购应付”当物资应收，零集团现金且全集团结算的会员零售不能充当该未收源。
- **整车**：客户从同轮明确 finite customer读当前负责人，新订单可沿原 sales-quote-new选择原客户与车型，Create允许不附已converted的旧lead；不可重复使用旧intent版本。真实报价、独立批准、签回及原确认到确切未收点后，核车辆约定与累计paid/due。现原两车一辆已交付、一辆取消，不能把原released/cancelled位置当可分配；如要真实后续交付须先新增真实采购第三车，不能fixture预置或直接SQL解Hold。仅做未出库报价／定金／取消退款路线时，原单与未收来源真实后再闭合，不宣称该路线完成整车交付。若同时建立原关联服务待收，须实际自己的报价/授权来源；不靠同客户另一个other_income类型代替整车服务。
- **维修**：同轮 finite CareCustomerVehicle现场读当前version/观察，原到店及新Repair→报价/独立确认→领料／施工／质检→当前分摊Settlement，保留customer payer欠款；原内部承担另行匹配。实际领退料成本来自当前有限库存和原StockMove，不继承旧余额。manager在财务收款前查真实未收，再财务本人收款及service实际接车终结；接车完成不倒推未测应收。

这些写入未获本页编码授权、没有结果，不纳入上述五报表候选计数；新单所需附件／原任务交接／request_id/CAS/各原Guard沿既有原UI。不得直接API写或改数据库造未收。读全店响应时背景照原范围保留，针对有限新ID独立筛其类型；原图与CSV仍对整个响应核算，不悄悄排除其他店或旧源不全的目标行。

### 消费积分：HK168仍partial

原 `membership_points.py` 只支持详细维修和retail；原 PointsClaim 无member或rule_id时，sync直接return。当前组合GiftPoints产生BenefitEntry，但没有Consumption PointsChange。因此仅赠／回收200/100与benefit_points一致最多局部覆盖。

完整目标首先需要原UI设置 points_enabled、明确points_benefit_rule_id／numerator／denominator_fen的 MembershipRule，原有效MembershipPeriod与实际续会费来源，之后再创建并完成支持的真实Repair／Retail，冻结claim规则、原实付净消费基数与整数目标。维修用实际released_date，retail用accepted_date；礼品面值、未用权益购买和内部结算不等于符合规则的消费。退费后的负目标与原批次Recovery分别保存；只有真实积分先已消费而不足追回时才能产生PointsDebt，再实际后续积分抵补产生DebtPayment。无该事实时当前debt表空可作为“无待追回”正确结果，但不能称已测债务分支，更不能SQL造Debt为非空。

上述有效规则／期间未在新六项会员链建立，故本页不提交HK168完整check。需根另核原续会/消费/退款输入范围与依赖，不能追溯给已经履约的旧retail自动补奖励或把储值member_entries当积分。

## 守卫、失败与待办

每次原登录审计完成后取全业务基线。普通GET／筛选／分页／原单只读全表摘要不变；导出仅精确允许对应原单条Audit新增，原旧Audit仍逐字保护。所有后继原资金／库存／集团／会员旧来源及他店旧行不覆盖删除，文件报告仅length/SHA/metadata，无BLOB／凭据；JSON SQL NULL和JSONnull分别正确解码，不把raw文本当模型None。

只等待原响应对象、当前h1及精确唯一可见DOM，不固定sleep、force或泛化retry。来源complete=false、原409/403/422、CSV不同范围、接口失败、父场景失败或未注册都保存失败/partial，不降标准到页面打开。0净图正确时保留原提示＋非空原明细，不强造SVG。预计五项报表读取与全CSV约60–150秒，实际受原行数／分页／来源完整性影响；时间不是运行证明，不能为时限截断。

**当前产物**：本scope已完成源码和有限历史证据审阅；下一步先由根完成财务后继复验及作者会员六项冻结，确定新同轮父场景清单、精确固定键与指纹，再登记五项候选范围。三类应收／消费积分／HK088及HK092显式check分别留下一原输入链。这里没有完整193、真实税务／银行、员工效率提升、ClamAV、PostgreSQL、Linux或生产验收结论。

**复核源位置**：`app/flow_analytics.py:93,120–188,347–398`；`app/flow_api.py:405,436`；`web/app.js:337–350`；`app/sales_service_analytics.py`；`app/business_finance_analytics.py`；`app/material_value_api.py`／`app/material_value_analytics.py:232–305`／`web/materialvalue.js:5–10`；`app/reconciliation_api.py:48–57`／`app/reconciliation_service.py`／`web/reconciliation.js:30–55`；`app/operations_analytics.py:91–108`／`app/membership_points.py:75–159`；`app/sales_quote_api.py:24–43`／`app/sales_quote_service.py:105–128`。逐check合同来自现193目录，原文及来源不足历史保持。
