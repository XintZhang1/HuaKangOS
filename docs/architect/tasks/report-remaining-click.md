# 九项剩余报表原生点击候选

2026-10-01，M8.1，依据 PATCH-M8-4-BUSINESS-193-29 及 reports-final-scope.md（6af1eba72ecc82d6f28ec84669665a4127799108eff4862a18f249638af72f6b）。只新增本页和 tests/browser_click/report_remaining_business.py；生产、fixture、共享helper、runner、注册、目录、计划、旧scope只读。候选未注册、未运行，不继承父场景或其它run成绩。

## 两个有限入口与独立合同

导出 `REPORT_REMAINING_SCENARIOS`，两个原三元组各720秒：

| 场景 | 完整check与原入口 |
| --- | --- |
| reports-sales-customer-hk139-140-164-165-166 | HK-139-business 加装单分析 table/addon_actual_facts；HK-140-business 代办单分析 table/service_fee_facts；HK-164-business 客户车辆统计 table/customer_vehicle_stats；HK-165-business 客户回访统计 table/callbacks；HK-166-business 进出厂统计 visit-activity |
| reports-boutique-points-hk154-156-168-169 | HK-154-business 精品销售统计 table/retail_settlements；HK-156-business 精品销售施工统计 table/retail_installation；HK-168-business 会员积分统计 analytics/members；HK-169-business 消费券统计 table/benefit_coupon |

每check从not_tested开始，执行失败只标当前项failed，后续仍not_tested。自动完成也保持 `business_accepted=false`、人工流程/文案pending、全193false；不把正确的空辅助表算成该业务支路已完成。原HK152/153 partial不晋级，HK157/158/159需新的真实正应收原单，不由本候选提交check。HK099的local客户车辆关系可作原来源，不宣称HK099全验收。

## 固定同轮父闭包与有限ID

A固定九父：sales-presales-hk001-007；vehicle-purchase-hk171-177-178-026-021-018-029；master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187；materials-hk069-045-054-083-070-072-073-051-061；customer-service-hk098-107-108-109；repair-selfpay-hk031-034-044-049-053-079；sales-order-hk008-009-011-022；sales-followon-hk012-015-016-017；customer-followon-hk100-101-102-103-104-110-111。

B固定九父：同轮售前/采购/主档/物资/销售五父；membership-hk117-128-118-089-094；member-followon-hk123-124-125-129-130-132；boutique-purchase-retail-hk074-052-058-062-064-082；member-points-tier-hk121-122-188-120-119-131。精品先于积分Retail原单，不能用后来会期给旧精品实购补资格。

父必须在本次browser-click-report的expected_scenarios内整场passed，固定目录checkpoint完整且每项passed，目录digest和含有的origin/source/runtime/evidence/database provenance与本次相同。所有父脚本、当前报表及共享helpers指纹对照同次稳定provenance；不扫历史run/latest。读取当前本店真实Case/CV/Entry，不冻结旧版本余额。报表日期包含有限来源的业务日/实际事件日，截至明确Asia/Shanghai业务今日，未来事实拒绝。

A消费 sales-followon.report_sources.addon_case_id/agency_case_id/customer_other_case_id；customer-followon的sales_callback_id/repair_callback_id/customer_vehicle_id/customer_id；首维修repair_case_id/appointment_id/intake_case_id/customer_vehicle_id/VIN。均核原kind和实际completed；客户车辆核active及当前客户关系。

B消费精品retail_case_id/installation_event_id/accept_event_id/coupon_purchase_entry_id/benefit_capture_entry_ids；积分points_claim_id/points_change_id/earned_points_entry_id、扣分/独立赠分/兑换出入Entry和独立赠券宿主Case。原PointsChange=9且Claim冻结rule_id，不能以普通Benefit grant替代消费积分。会员六项的组合赠送/回收、付费券purchase/refund和两独立Retail的capture Entry均有限核对；原付费券退回同钱包/原purchase、真实cash_id。真实未创建的reverse/restore仍未测。

## UI、原API与独立后端事实

原manager本店登录后才取业务只读baseline。通过原统计目录检索HK、原入口、可见日期提交进入每项。普通原GET `/api/flow/analytics?date_from&date_to`，图分类原tabs、实际SVG数值与同范围图明细、全部50行分页、原钻取和真实CSV下载；charttable hash导航捕获其当前新GET并核表/KPI与先前同范围一致。原可见KPI按页面实际销售/物资/客户/会员metricSets核值和单位，不为不存在的专用KPI补造控件。

139整店所选期间AddonAcceptance及有原acceptance_id的ReturnPosting，按实际日、净额和原商品成本逐行/整图/指标核；发出/安装/现金不作验收。140详细agency v3/other_income v2的ServiceLine/Fulfillment、已生效ChargeAdjustment、TerminationApplication逐行保留费差额，以原fact_id/original_fact_id核来源；本店服务费与代缴本金分开，完整归集图和service_fee_net_cents。当前已授权版本的ServiceLine/ChargeAdjustment/TenderSlice按两bucket独立核service_fee_receivable_cents和service_pass_receivable_cents，不能拿总代收余额替代服务费。

164当前active CustomerVehicle按明确vehicle_identity_id去重，核共享编号/车型一致性/关系数/图和两指标，按实际返回的原关系钻取 `/api/customer-service/vehicles/{id}` 的 `vehicle` 包装并核VIN/identity；不是库存、产权或期间历史。165整店原callback与新sales_callback/repair_callback按Case建立日选批次，当前state/result及两真实新回访分别核，多次CareRecord仍一个任务；整图callback_state与任务/已结案/取消计数一致。

166先保留原全店complete/issues覆盖事实，再原UI选择首维修case_id，仅该原来源读 `/api/visit-activity-reports?date_from&date_to&case_id`。ArrivalFact配原Appointment/Intake/RepairBinding及原到店文件，唯一repair_v4_release配原接车文件/实际日期；严格2进出行/1闭合cohort/原时间分钟、3可见KPI、service_gate_movements图、四原表与图导出、原维修钻取。没有GateFact/纠正不伪造；所选闭合不能声称全店历史完整。

154所有本店原Retail真实accepted_date、原Dispatch成本、验收前/后原退分别核；GroupAllocation C−P按实际Capture日扣一次、原实退优惠冲回一次，Restore不再计第二次收入。156唯一retail_install实际事件及冻结RetailLine安装项目/收费依据，扣完工前实际退回量价，后退不抹原完工；本轮双商品安装明确非空，整图/安装核价指标保持独立。

168原benefit_points、membership_points、membership_points_debts三表三图三CSV分别核：独立权益单位账、冻结消费目标变动/消费基数、当前未追回债务不是现金。DebtPayment按其原PointsChange所属店归集，不能按付款店遗漏。消费9、扣1、独立赠5、兑4的原Entry分别核；当前真实无Debt辅助表可严格为空，非空欠额/清偿支路仍未测。169券按本店Entry发生日、冻结Rule name/version和signed units核全表/全图，原实购/组合赠券/核销/原退/兑换2券/独立赠1券来源独立；积分、本金、占额和现金不当券。

所有独立DBoracle只使用显式表白名单的SELECT，25000条上限明确拒绝而不截断，并对完整获权期间归集，不能把全店总额硬等本轮目标原单。没有应用导入、直接HTTP写、SQL写、业务预置、浏览器状态注入或未知结果重放。

## 只读与CSV保护、静态交接

GET、筛选、图/明细导航、分页、钻取和展示检查均取全业务摘要，所有旧行/Cash/Stock/会员/文件字节不变。每次可见下载click只允许原CSV GET、精确当前本人本店一条export Audit；旧Audit逐列原样，其余全表摘要保持。CSV全部headers/values依原safe规则及同过滤核，真实文件长度/SHA记录；BLOB只内存校验，报告不含正文或凭据。

自审核原catalog九title/check/route、API/schema/model/JS/table/graph和共享helper字段；修正了原fixed_dependency要求的digest/provenance以及客户车辆详情vehicle包装，并收紧有限券Entry来源。候选源AST、SELECT-only及导入/调用/三元组结构、UTF-8/空白静态核对后冻结交根；本页不登记实测通过。独立短审和注册由根协调，随后全新同轮原UI执行。

待测：原动态渲染/实际下载/SQLite审计事务；finance/集团隐私与跨店授权、车型冲突、未发生的退回/纠正/欠额和完整历史窗口；其他尺寸人工流程/文案、PG/Linux、银行/实物/扫描、员工试用及生产门禁。真实失败原件保留，不能放宽单条导出审计或来源守卫求绿。
