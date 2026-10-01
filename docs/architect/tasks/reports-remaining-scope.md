# 剩余报表的非空来源与最小增量范围

2026-10-01，只读范围审阅；本页是实施建议，不新增脚本、不改目录或生产，不登记任何报表通过。HEAD 为 `8993ca8c755194a42a48e7323fe355e80c6bf9ae`，保留当前未提交工作树。193目录 SHA256 为 `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`。

**编号核准**：原 HK156 是“精品销售施工统计”，入口 `#table/retail_installation`。车辆库存查询是 HK029；`#table/inventory`／`#analytics/inventory` 的库存快照可作补充核对，不能改称 HK156 或再计一项原需求。HK029 本轮前序采购检查已通过，后继仍须读取当前实车状态。

**当前证据**：已读外置 `automatic-business-20261001-10/evidence/browser-click-report.json`：32组执行、31组通过、100个完整自动check，整轮 `passed=false`。核账后继因读取白名单缺少 users/stores 在零动作前置失败；根补丁 `RECONCILIATION-READ-REFERENCES-01` 后候选 `e2c5123c1149d75326d24fdc90e94094c0f87c1aff14f2c90b4546698cb4dc8b` 已独立只读核对，AST通过、Guard可写TABLES未扩、账号行及密码hash不输出，尚未因此记复验通过。四财务报表候选 `1a536320d071d8a4099dad819b336fcbfc2b30ab58dc64f0d1aae1fd780bb6b1` 保持冻结；本页不向其追加169。

## 原合同、有限来源及缺条件

各项完整检查沿原 `HK-xxx-business`，查询身份使用本店 manager；finance/auditor/admin 的原阅读合同保留。以下“可读取”只表示来源已存在或可规划，不表示该报表已经执行或验收。

| 原需求／实际UI | 精确源码与字段依据 | 最小同轮非空来源／仍缺条件 |
| --- | --- | --- |
| HK156 精品销售施工统计；`table/retail_installation` | `app/service_analytics.py:83–113`：唯一 `FlowEvent.action=retail_install` 的当地完工日；RetailLine.work_item_id、原dispatch、完工前已验收退回数量与安装费；表quantity_milli、amount_cents，指标 `retail_installation_basis_cents` | 当前加装不是Retail安装；会员六项候选只销售商品，无work，不能替代。新增原Retail商品＋已知安装作业→独立approve→authorization原件→inventory dispatch→technician本人install→sales accept；收费依据是原冻结安装报价，不冒充实际收入。可与HK157同一新单组合。 |
| HK157 物资应收账统计；`table/receivables` | `app/flow_analytics.py:153–158,178–189`：Retail totals／获原授权的AddOn totals；原价、已生效退货、累计结算与due；`app/retail_service.py:46–70` 分charge/net_paid/receivable与C/P/S | 现材料采购、加装和已全额集团结算的Retail终局不能给非零应收。最小新Retail明确本店商品＋安装价，原批准和客户授权后完成实际出库/安装/接收，finance仅实收已明确的一部分，保留正due；读后再由本人原账户收齐。不把采购应付、other_return供方应收或假定中间状态代替商品客户应收。 |
| HK158 整车相关应收账统计；同一receivables表 | `app/flow_analytics.py:159–189`：原order净约定−结算；原关联agency fee/pass、insurance authorized保费/已确认佣金、addon授权价各自取真实来源；financeCredit、Group/Benefit/Package付款与现金分别核 | 现已交付订单已收齐，第二订单退订原款已退，关联服务也已结清。另建同轮原客户/车型报价→不同manager复核→本版签回/原确认，在足额收款之前读取真实待收；原流程需要VIN时只用当时经GET/DB核准的可配车，不能复用已交付旧车或SQL解Hold。关联服务须本订单真实关联与报价/授权，不能拿同客户other_income替代；未完成交付不能声明销售完整链。 |
| HK159 维修应收账统计；同一receivables表 | `app/repair_service.py:113–123` 的RepairAllocation、原RepairPayment/PaymentLink和权益净额；`flow_analytics.py:146–152`仅外部payer正due；内部承担单独核，不计现金应收 | 首维修、洗车、quick终局已结清。最小复用当前CV和已启用有限库存，新增原到店/Repair→报价/同意→施工/质检→主管冻结Settlement/客户Allocation，finance部分实收后读正due，随后原收齐及service接车。接车前客户尚欠被原守卫阻止；不得用完成态倒推中途应收。若只工作项目，无物料领用不造StockMove。 |
| HK164 客户车辆统计；`table/customer_vehicle_stats` | `app/customer_analytics.py:25–44`：active care_customer_vehicles 按vehicle_identity_id去重，当前登记车型、获权关联门店、有效关系数；`customer_vehicle_identity_count/relation_count`与车型图一致 | 可直接取同轮CS检查点 `partial_requirements[HK099].evidence.vehicle/vehicle_identity/identity_link` 的明确ID，再读当前有效关系。run10确有本轮CV原件；保险与维修可能更新其version/里程，不能要求旧整行相等。完整获权范围按DB独立归集，旧样例只是背景；从表内原钻取 `customer-vehicles/{id}`→GET `/api/customer-service/vehicles/{id}`核VIN/identity。不是库存或产权统计。 |
| HK165 客户回访统计；`table/callbacks` | `app/callback_analytics.py:16–48`：以Case.business_date选择callback与CareCase sales_callback/repair_callback；每任务一次，due/state/result/count；finance/集团汇总隐藏原单与原文 | 同轮销售HK009/HK011 evidence.callback_sources确有原交车产生的唯一pending callback，parent为本次delivered_order_id。可直接核当前Task/Case、图表/表/CSV；不得把咨询或续保当回访。当前没有明确新Care回访来源时，该支正确为空且不宣称已测其办理；如需覆盖，service或本店销售从原客户服务UI建立相同客户已交付/完工原单的callback→接手/真实跟进/结案，保留独立有限ID。finance只核分类/状态计数、无route/原文。 |
| HK166 进出厂统计；`visit-activity` | `app/visit_activity_analytics.py:82–176`：ArrivalFact＋原预约/RepairIntake/Binding/file，唯一repair_v4_release＋本单release_evidence_id；真实UTC转业务当地日，闭合时长；`gate_visit_reporting.py:17–65`另外纳入GateFact/RepairGateExit/纠正 | 同轮首维修的report_sources已给appointment_id/intake_case_id/repair_case_id/CV/VIN，真实到店和客户接车可配对。先读全获权范围，原旧维修缺到店保留issues及complete=false；再用原 `#visit-activity-filters [name=case_id]` 选本次repair_case_id，核关联预约的2条movement/1闭合cohort、实际时长/原件及同筛选CSV。只证明明示原单范围，不把筛选后的完整性说成历史全店完整。无GateVisit/RepairGateExit/纠正来源时分支未测，不为报表手造进出事实。 |
| HK168 会员积分统计；`analytics/members` | `flow_analytics.py:385–398` benefit_points；`operations_analytics.py:91–109` membership_points/membership_points_debts；`membership_points.py:26–42,75–104,123–158` freezes claim、消费净基数、target/delta、Recovery/Debt/Payment | 当前赠积分200/回收100只属BenefitEntry；会员六项明确 `points_consumption_or_points_change=false`，不能完整通过。最小先原UI发布有效points-enabled MembershipRule＋独立points BenefitRule及有效MembershipPeriod，随后新建支持的Repair/Retail，在首次客户授权前冻规则，实际履约并支付后才有PointsChange。已授权旧单rule_id=None不追赠。当前债务为0可正确核空表，待追回分支只有真实积分已使用/占额导致原退款不足追回时才产生，不强造Debt。 |
| HK169 消费券统计；`table/benefit_coupon` | `flow_analytics.py:385–398`：BenefitEntry.kind=coupon、occurred_at业务当地日、purpose原映射、signed units、rule_name/version、case route；占额独立不计余额变动 | 等会员六项 `member-followon-hk123-124-125-129-130-132` 在同一新run整场complete/passed。然后只取其最终report_sources：gift/paid wallet、bundle_grant/recovery、benefit_capture_entry_ids、paid_coupon_purchase_entry_id/refund_entry_id及有限原case。实际逐Entry读purpose与单位，不按计划硬填“回收”动作；gift与paid原价/优惠承担分开。该候选当前冻结 `2c8777cf…` 没有执行结果，本页和冻结四报表不新增169成绩。 |

## 原入口与复用边界

- 普通flow报表原GET `/api/flow/analytics?date_from&date_to`；CSV `/api/flow/analytics/export?dataset={原表键}&date_from&date_to`。HK157/158/159共享完整receivables，原UI没有kind筛选；当前待收快照不随日期重建，不声称历史期末数。finance页“当前尚待收取”KPI及原表没有专属应收SVG，不虚构图。
- 可复用 `report_business.py` 的 `passed_checkpoint/native_response/refresh_report/verify_table/graph/export_csv/flow_chart/drill_original`，保留flow 50条、visit 25条实际分页及全CSV。`open_report`支持table/*；不能将其现有标题算法原样用于analytics/members。HK164钻取是CustomerVehicle GET而不是FlowCase GET，需小型专用适配；其他原Case钻取仍核ID/number/current role。
- 每次真实原登录审计后取全原业务摘要；GET、筛选、分页、钻取不改变任何原行。每次原CSV只允许唯一对应Audit新增：flow_analytics.reason=原表title；visit_activity_report.reason=日期范围＋原key，SQL JSONnull先解码再严格核None。全旧Audit、资金、库存、会员、他店旧行与BLOB原样保护，产物只记hash/length/有限来源，不能输出账号行或凭据。
- 后继只能读同次manifest.evidence_root固定报告和完整passed前序checkpoint，重验origin/镜像/catalog/脚本指纹及有限ID当前事实；父完整联合失败不能声明整轮passed，局部父场景passed也不能拼入另一run。原用户、CV、账户及物料余额当前重读，不继承旧版本/原零余额。

## 建议次序与来源缺口

1. 先登记独立只读查询增量HK164/165/166；无需新业务预置。HK166同时保留全范围来源不足和本次原单筛选范围，Gate纠正/取消维修离场仅条件未测。车辆inventory快照可顺带核本轮有限VIN/已交付剔除/可售与原Position/Custody，不再映射成HK156。
2. 会员六项实际同轮通过并获根精确授权后，独立HK169查询。不能从静态六项候选或不同run复制券事实。
3. 登记最小原Retail带安装＋部分实收链，形成HK156/HK157非空，再查三个原应收来源并逐原款收齐。HK158/HK159分别新原订单／维修原承担来源；表查询可共用一次完整响应/CSV，各check仍独立证明自己的非零来源。
4. 最后续会规则／有效期间／支持消费／退款积分链形成HK168；需真实points claim与delta，礼品赠分不能节省该前序。并行新业务角色可复用现有sales/service/manager/technician/inventory/finance；所有任务负载分给demo员工时仅原manager UI交接，不借admin替代本人。

仓储作者已确认未执行HK085候选的other_return应收200分只在中间stages[0]出现，终局collect200后due0；其未来warehouse_sources.other_return_finance可追溯原件，但不能供下一报表断言非零，更不能当商品客户待收。上述新增写入链仍需根另登记范围后编码。人工体验/文案、全193、生产银行/实物/扫描、PostgreSQL和员工试用均保持未验收。
