# 剩余报表最终增量的原来源与验收范围

2026-10-01，只读源码研究。只新增本页；没有编辑生产、目录、候选脚本、runner、计划或旧scope，没有导入app或运行验证。读取时HEAD为`8993ca8c755194a42a48e7323fe355e80c6bf9ae`，当前未提交修改全部保留。以下是下一批实施建议，不是执行结果；所有新check仍未测，人工体验和文案待审，`business_accepted=false`、全193未完成。

原目录的14个编号、中文标题和`HK-xxx-business`已逐项核对。六类criteria仍含显示、流程、文案、后端匹配、硬bug、来源完整性；`source_integrity`明确允许未知成本为null、来源不全为`complete=false`，禁止补零。正确展示缺源不等于原业务历史完整，自动断言也不等于六类标准全通过。原PATCH-M8-4-PROCUREMENT-HISTORY-SCOPE-01登记的152/153 partial保持，不由本页晋级。

## 14项精确来源与最小边界

| 原需求／固定check／原入口 | 原表、列与事实 | 同轮有限来源和仍需条件 |
| --- | --- | --- |
| HK139 加装单分析；HK-139-business；`#table/addon_actual_facts` | `sales_service_analytics.py:20–29`，列原单/门店/实际发生日/事实/业务净额/商品成本。只有AddonAcceptance及已验收原单的AddonReturnPosting，按实际事实日取数；验收金额、StockMove原成本，退回净额为负的商品＋安装−保留费用、退回原成本为负。图`addon_actual_facts`按店归集。 | 销售后继`report_sources.addon_case_id`及其验收、领退物和原成本；原库存发出或技师安装不能当收入。原退回来源若没有，正确核空且保留该分支未测，不制造退货。 |
| HK140 代办单分析；HK-140-business；`#table/service_fee_facts` | `service_orders_analytics.py:14–44`，列原单/门店/发生日期/服务类型/项目/事实/金额。ServiceLine与`service_orders_service.actual_income_rows`的fulfillment、fee_reduction、retained_fee；各行含fact_kind/fact_id/original_fact_id。图`service_fee_facts`，指标`service_fee_net_cents/service_fee_receivable_cents/service_pass_receivable_cents`。 | 销售后继agency_case_id已逐项目真实办结及客户other_income来源，或客服后继income_case_id。报价、代缴本金、预收和现金都不自动成为服务收入；厂家收入属于另一原域，不能混入本表。 |
| HK152 物资仓库入出存统计；HK-152-business；`#warehouse-period` | `warehouse_period_analytics.py:109–205`，原tables`warehouse_period_balances/baselines/entries`；余额按Item＋WarehouseBalance＋WarehouseEnrollment＋原启用基准＋WarehouseEntry归集。列物资/单位/仓库/库位或店内在途、期初/期间入/期间出/已知期末数量及价值、均价分摊调整、期间/期末是否完整、来源说明；基准表列实际启用UTC时刻及分配量/价值，流水表列实际日/业务/原库位和原库存流水/有符号量与价值。 | 可用本轮material或精品零分配启用后实际入库的Item、仓库、库位及Entry；原UI选择真实item_id/warehouse_id，核未知期初与已知期末。详见下节：同日基准不应要求period_complete=true；可有真实期末图和同范围CSV。 |
| HK153 物资采购订货统计；HK-153-business；`#procurement-cohort` | `procurement_analytics.py:18–139`，tables`procurement_cohort_lines/postings/issues`。新PurchaseOrder/Line以唯一procurement_create事件当地日选订货批次并核Case.business_date；期间选批次，履约累计截至当前as_of。列采购单/申请日期/供应商/物资/单位/当前进度，订货、已收、已退、保留、未收、已关闭、待处理七数量/金额与来源核对；posting列实际日/原确认/StockMove/有符号量及价值。 | material或精品的新两行采购及实际Receipt、ReturnPosting；完整枚举同范围旧kind=purchase及其原reason。历史缺不可变逐行来源时不混合金额、不补零。仅三静态CSV可实际导出，正向单位图分支仍缺真实无历史差异批次，详见下节。 |
| HK154 精品销售统计；HK-154-business；`#table/retail_settlements` | `commercial_analytics.py:22–55`，列单号/门店/客户/日期/事实/对外结算/商品成本。RetailDispatch、真正retail_accept、RetailReturnPosting；验收日净额和原商品成本，后来退回另负行。集团优惠由`retail_group_reporting.discounts`的C−P另扣一次。图同表；指标`retail_revenue_cents/retail_goods_cost_cents`。 | 精品retail_case_id、line_ids、dispatch_ids、accept_event_id及真实GroupPlan/Capture/CashAllocation；积分候选Retail也纳入全范围。C、P、S、本金、券和现金分开，不按收款额直接认收入，不重减优惠或把权益恢复当第二次退款收入。 |
| HK156 精品销售施工统计；HK-156-business；`#table/retail_installation` | `service_analytics.py:83–113`，唯一FlowEvent.action=retail_install当地实际完工日；RetailLine.work_item_id、原作业code/name和冻结安装收费，扣除完工前真实退回数量/安装费。列原单/门店/实际完工日/商品/安装项目/实际安装数量/单位/当时安装收费依据；图同表，指标`retail_installation_basis_cents`。 | 精品installation_event_id及两条商品明细、work_item_id/work_code、原dispatch；实装收费依据不是收入或库存量。会员六项无安装作业的Retail、车辆加装不是本项来源。完工后的退回不抹掉已发生安装。 |
| HK157 物资应收账统计；HK-157-business；`#table/receivables` | `flow_analytics.py:153–158,178–189`，Retail totals和真实授权AddOn净charge/net_paid/due。共同列业务单号/门店/客户/业务/约定金额/累计已收/尚待收取/应收状态；仅正gap入表。 | 终局精品和集团付款已结清不能供正余额。需新实际商品客户原单，原批准/授权、发出/安装/接收、部分实际结算后读取正due；供方应付/原退应收不冒充本项。 |
| HK158 整车相关应收账统计；HK-158-business；同一receivables | `flow_analytics.py:159–189`，原order净约定与结算，原关联服务fee/pass余额、授权保险/确认佣金和加装分别用其来源；共同列同上，原FinanceCredit及权益付款与现金分开。 | 原交付订单已收齐、退订单已原退，不能用零值占位。新报价要本版独立复核、当前车型VIN配车与生成字节绑定签回，取得active_quote/sales_consent后部分实收；另真实关联agency可核整车相关服务余额，不拿同客户无关联other_income替代。 |
| HK159 维修应收账统计；HK-159-business；同一receivables | `repair_service.py:113–123`及`flow_analytics.py:146–152`，RepairAllocation/原RepairPayment/PaymentLink与权益净额，分别payer amount/paid/due/due_date，内部承担被明确排除应收和现金。 | 新实际到店Repair、授权施工/独立质检/冻结客户承担后部分实收，原外部payer正due；当前已释放维修终局不能还原旧中间余额。可显式另配内部承担以核排除，不造内部现金。 |
| HK164 客户车辆统计；HK-164-business；`#table/customer_vehicle_stats` | `customer_analytics.py:25–44`，当前active CustomerVehicle按vehicle_identity_id明确去重；列共享车辆编号/登记车型/关联门店/有效关系数/车型资料；指标identity_count/relation_count，车型图同范围。关系车型不一致保留待核对，不按姓名/VIN模糊合并。 | 客服099local的vehicle/vehicle_identity/identity_link有限ID及客服后继customer_vehicle_id/repair_customer_vehicle_id；可消费local事实，不宣称HK099全验收。维修/保险可能更新版本，重读当前关系。原CustomerVehicle钻取`/api/customer-service/vehicles/{id}`核VIN/identity；当前关系统计不是库存、产权或历史期末。 |
| HK165 客户回访统计；HK-165-business；`#table/callbacks` | `callback_analytics.py:16–48`，按Case.business_date选建立任务批次，旧callback及新CareCase.sales_callback/repair_callback；列业务单号/门店/回访事项/计划日期/当前状态/结果/数量。图callback_state，指标task/completed/cancelled_count；一次任务计一次，多次CareRecord不重复增量。 | 最短由销售callback_sources提供交付后原callback；更充分可加已完整passed客服后继sales_callback_id/repair_callback_id，各自真实办理留痕。咨询/投诉/问卷/续保不计本表。finance/集团汇总仅分类/状态/计数，无客户原文和route；主管钻取仍原授权。 |
| HK166 进出厂统计；HK-166-business；`#visit-activity` | `visit_activity_analytics.py:80–190`及gate_visit_reporting，tables`service_gate_movements/service_visit_cohort/gate_corrections/visit_source_issues`。实际ArrivalFact＋预约/Intake/Binding/file、唯一repair_v4_release与release_evidence；列实际时间/方向/来源类型及编号/核对VIN，批次实际到店/截至期末离场/状态/闭合分钟，纠正与缺源分别列。图service_gate_movements，指标actual_arrivals/departures/cohort_without_departure。 | 首维修report_sources的appointment_id/intake_case_id/repair_case_id/CV/VIN配对真实进出。全店历史缺源保留complete=false/issues；原case_id筛本次维修可闭合2原进出、1cohort并导出同范围CSV，不能把筛后完整说成全历史完整。无真实Gate/纠正来源的支路未测，不猜仍在厂/时长。 |
| HK168 会员积分统计；HK-168-business；`#analytics/members` | `flow_analytics.py:385–398`的benefit_points及`operations_analytics.py:91–109`的membership_points/membership_points_debts三表/三图。列发生日/店/来源单/原规则版/动作/积分单位；消费表另变更后符合规则消费基数，债务表原应追回/当前未追回。指标`membership_points_change_units/debt_units`；赠分、消费增量、欠额是不同事实。 | 新积分候选points_claim_id/points_change_id/earned_points_wallet_id/entry_id：实际有效会期及冻结规则下Retail履约实收才生PointsChange9；原扣1、独立赠5、兑4各Entry独立，不能用组合赠分替代消费积分。当前无真实Debt可严格核空表，非空欠额及清偿支路待真实使用/追回不足来源。 |
| HK169 消费券统计；HK-169-business；`#table/benefit_coupon` | `flow_analytics.py:385–398`，BenefitEntry.kind=coupon按occurred_at当地日、原purpose、有符号units和冻结rule_name/version；列发生日/店/来源单/规则及版本/动作/变动张数。图同表按purpose计单位；purchase/grant/capture/reverse/refund/adjust/exchange_in/out沿原映射，不跨单位相加。 | member6的付费/组合赠券、实核销和退款回收原Entry；精品coupon_purchase_entry_id/benefit_capture_entry_ids；积分候选exchange_in Entry的2券及独立direct_coupon_grant_entry_id的1券。积分exchange_out不是券、Reservation不变账面、Cash不变券数量；没有的返还purpose正确为空而非宣称已办理。 |

## 152／153能否完整核报表而不假称来源完整

HK152原公式严格区分`period_complete`与`closing_complete`：`start > bridge_day`才能完整期初，`end >= bridge_day`可以已知期末。原`inventory_report_common.period`不允许未来截止日。当天原UI零分配启用的新Item，即使随后真实采购/移库/盘点，期初及启用前收发仍未知；同日不得断言期间完整，也不得改时钟或回填旧启用日。完整的报表功能路径可以核：选非空本店Item＋Warehouse → 原GET200 → `complete=false/closing_complete=true`、opening/in/out/value未知为null、覆盖说明与issues原样 → 真实Entry守恒/期末quantity/value → `warehouse_period_closing`期末图 → 该图原表`warehouse_period_balances`及三张表CSV → 原启用和Entry单钻取。原图只在closing_complete且有金额权限时出现，没有“完整期间收发”图可假补。全店视图可能closing也不全，须核真实不显示并和所选具体仓图区分。这个功能范围与目录source_integrity相容；若根另登记HK152完整功能check，必须明确其数据覆盖仍不完整、完整历史期初支路未测；原已注册partial不变。

HK153历史kind=purchase缺不可变逐行来源时，原issue明确“历史简表采购：仅按原登记日期列出，缺少不可变逐行订货来源，不混入新订货履约合计”。`complete=false`时七金额指标为None，`charts=[]`，`procurement_cohort_unit_N`动态图表原表键根本不生成。原UI只有日期，没有case/item排除历史筛选。可以完整核新行七数量守恒、真实Receipt/ReturnPosting/StockMove、旧原单与准确issues、金额未知、三静态CSV及抑图；不能点击不存在的动态图按钮，不能称正向数量图/动态图CSV已验收。当前153保留partial是准确的；如后续根以“缺源时正确抑图”登记功能check，仍必须把完整正向图支路列not_tested。正向图的最小条件是实际另一天原UI新采购建立在无历史kind=purchase的日期批次内、所有逐行履约来源闭合，再按原日期查；不迁移旧单、不制造日期或更改定义。

153每次动态枚举当前本店所选批次内全部旧kind=purchase与新procurement，不继承旧run“4旧单/2行/5原账”的数量常量。精品、跨店和后来原退可增加真实来源。7阶段数量按单位分组，金额None仍为None；当前累计履约不当作期间到货。152同理按当前Item＋仓真实Balance/Enrollment/Entry核，零分配基准不是入库。

## 三项应收的必须新原单中间状态

原receivables只列正gap，原UI没有kind筛选。它是当前净待收快照，日期不重建历史余额；finance“当前尚待收取”KPI与表相符，源码没有应收专属SVG，不能为满足图要求虚构。当前销售、精品、积分和已释放维修终局结清后，正确不在表内不能作为157/158/159的非空验收。

1. HK157：从当前真实物资/库位可用量重读，原`#retail`→POST`/api/retail/orders`新单；非建单人主管approve、客户authorization原件、inventory真实prepare/dispatch、需要安装则technician本人install、sales/service本人accept。finance从原账户实际收一部分，留下`0 < net_paid < charge`，核本原单正due；读后原收齐再核其行消失/KPI减少。当前会期会冻结PointsClaim时按实际冻结来源保护，不粗放全积分表。
2. HK158：原`#sales-quotes`→POST`/api/sales-quotes/orders`支持无lead的新报价，但要明确本人客户和真实Model。不同主管quote_approve、inventory从当前本店已审核且无Hold的同Model车辆allocate、sales生成本版车型/VIN/价款/条款合同并实际签回sign，才有active_quote_id/sales_consent_id。随后原finance部分receive保留正due；不能仅待批proposal冒充有效客户约定。已售车/调拨中的VIN不能借用；若缺可配车，必须另原UI采购入库或列待前置。需要整车关联服务时原`#service-orders`创建本订单/客户/当前版本的agency，逐行报价、独立approve、authorization后保留fee/pass正余额，外部手续没有实际结果时不假fulfill。可读后继续原收齐，交付未发生不把新单记完整销售检查。
3. HK159：当前CustomerVehicle从原接待UI另实际Arrival→Repair v4，真实Quote/不同员工price_approve/Authorization、技师start/finish、独立质检、主管allocate冻结外部客户和可选内部承担。原finance仅部分receive；逐RepairAllocation核amount/paid/due及对应原PaymentLink/Cash，内部承担不进cash/应收。全额收齐后service真实release；欠客户款时原release守卫不能被跳过。若选择纯作业不造物料流水，若有part必须当前库存/原领退成本闭合。

三个新原单在同一时刻均保留正due时，读取一次同范围完整receivables、KPI、CSV，各check独立核自己的原ID/业务类型/payer/金额并钻取；全表还有别的真实来源则按完整获权DB集合归集，不能断言只有三行或全店金额只等本次三单。未知提交立即停止，不换request_id重放。此写读候选须根另登记准确补丁，本页不实施。

## 固定同轮来源及建议最短批次

来源只有同次manifest.evidence_root中的固定场景checkpoint可用，必须complete/passed且每check通过；复核origin、源码/目录/脚本指纹及当时有限原ID。静态候选、另一run或父失败片段不能转成当前来源。全部新业务正向由原UI发生，DB仅SELECT核事实；已有源仅给编号与关系，当前库存、身份、金额和版本重新读。

- A五项139/140/164/165/166：固定父`sales-presales-hk001-007`→`vehicle-purchase-hk171-177-178-026-021-018-029`，`master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187`→`materials-hk069-045-054-083-070-072-073-051-061`，`customer-service-hk098-107-108-109`→`repair-selfpay-hk031-034-044-049-053-079`，`sales-order-hk008-009-011-022`→`sales-followon-hk012-015-016-017`，八父闭包。139加装实际验收、140代办逐项履约、164本店CV、165交付callback、166真实到店/接车都有有限原件。建议加第九父`customer-followon-hk100-101-102-103-104-110-111`，使165同时核新sales/repair两类真实回访及140其它服务，不用旧callback替代已存在新来源。
- B四项154/156/168/169：固定售前/采购/主档/物资/销售五父→`membership-hk117-128-118-089-094`→`member-followon-hk123-124-125-129-130-132`→`boutique-purchase-retail-hk074-052-058-062-064-082`→`member-points-tier-hk121-122-188-120-119-131`，九父闭包。精品必须先于有效会期/积分候选，避免其coupon购买资格前置被后来会期改变。精品report_sources保留Item/profile/activation/warehouse/StockMove、retail_line/dispatch/install/accept、Group/Benefit/Cash有限IDs；积分保留Claim/Change/原钱包与每个adjust/grant/exchange Entry、原会期和现金。只消费本轮整场通过来源，不继承旧总余额常量。
- B可追加152报表功能候选，真实具体物资＋仓过滤核未知期初/已知非零期末及图/三CSV；需根先明确新check范围，旧partial保持。153继续精确缺源partial；其正向图单独待实际无旧简表批次条件。
- C三项157/158/159：另登记新商品、新整车有效约定及相关服务、新维修承担的中间正due链。最短基础复用售前/采购/主档/物资/销售/客服/维修有限关系；没有可售车/库存则扩实际采购前序，不借会员终局或供方退款应收代替客户欠款。可独立于A/B先运行此三写读链，但不预记任何新流程或报表通过。

## 原API、显示与只读保护合同

普通原UI一次GET`/api/flow/analytics?date_from&date_to`，CSV`/api/flow/analytics/export?dataset={真实表键}&date_from&date_to`；table/*原表每页50，图“查看全部”仍真实同表，CSV是全量。`analytics/members`原标题为数据可视化，不能照table标题算法硬套。native日期submit应清state.analytics缓存后重读，尤其应收在两次真实收款前后；无kind参数。原table drill沿返回route；164是CustomerVehicle而非FlowCase，finance/汇总不造不可见钻取。

152原GET`/api/inventory-reports/warehouses`及`/warehouses/export/{key}`，同date/item/warehouse过滤、候选包含停用历史；153原GET`/api/inventory-reports/procurement`及`/procurement/export/{key}`，仅date。166原GET`/api/visit-activity-reports`及`/export/{key}`，同date/case_id。原门店manager足够读上述完整业务和金额；finance/auditor/admin保持各实际授权，集团只读且隐私限制不能借admin越过。

每次登录原审计完成后才取只读baseline。GET/筛选/分页/钻取保持全部业务、旧Audit、Cash/Stock/会员/FileAsset原字节不变。一次可见CSV click只允许一次原GET和精确一条本用户本店export Audit：flow_analytics的reason=原表title；inventory的entity_type={warehouses|procurement}_inventory_report且reason=日期范围＋原key；visit_activity_report同日期范围/key。旧审计全部逐列保护，不粗排除audit_logs或登录行。JSONnull先按原JSON解码；各CSV对照原table.values而非自行重新格式化：flow数字保持数值、None为空，inventory/visit使用其原str与数值识别规则；表格金额分→元、数量千分→实际量，未知期初已显示为“—”，API未知字段仍null，字符串安全前缀沿各原导出。File BLOB只内存对比，证据仅长度/SHA/有限元信息，不序列化正文或凭据。

原SQLite审计型导出依赖get_audited_read_db/get_write_db、先BEGIN IMMEDIATE再授权读写，无自动重试；不扩大普通GET写锁。本次不改现金定义7、月结当前定义22或旧1..21冻结定义。真实缺源.notice.error是业务覆盖说明，专用断言应核准确HTTP200/原因/原issues，不能通用断言“没有error notice”迫使隐去事实；原API失败仍不能当覆盖提示通过。

除14项上述明确源合同外，跨店重复计量、退回/纠正、积分欠额清偿、车型冲突、历史完整期间/正向采购图和非空新应收流程等条件，未真实执行仍not_tested；人工流程简洁和文案、PostgreSQL、真实银行/实物/附件扫描、员工试用与生产门禁不由此静态研究替代。
