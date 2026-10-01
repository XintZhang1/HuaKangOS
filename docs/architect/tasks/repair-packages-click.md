# 原混合维修套餐四项点击候选

2026-10-01，test_inventory。按 PATCH-M8-4-BUSINESS-193-25 与 packages-remaining-scope.md（59fbc5bf650a9c09e7e087a2429a8bca9b6c1cfffd16b020e111e0ca1aced4c4）新增 repair_packages_business.py。候选未注册、未执行；仅这份源码及本页写入，未修改生产、fixture、共享 helper、runner、目录或计划，也未导入 app、启动实例或浏览器。本页不是四项通过报告。

入口 repair-packages-hk043-133-126-127，导出 REPAIR_PACKAGES_SCENARIOS 原三元组，固定1500秒。沿既有 Evidence、原登录／表单／附件／Task交接 helper 与独立 checkpoint，不另建执行框架。

| 完整候选 check | 原输入到结果断言 |
| --- | --- |
| HK-043-business 维修套餐设置 | 新混合作业＋材料 PackageRule、不同主管批准及两个真实本店 Mapping；新同会员v4修单报价绑定原Lot，独立核价、本版授权、实际进位／施工／领料、独立质检、原费用分摊、finance核销及实际接车。只提规则不记通过。 |
| HK-133-business 套餐卡类型 | 冻结每组件规格、单位、数量和C/P/S；另提同code的v2并独立批准，原v1停止新购买。已售contract、QuoteSnapshot、Lot、实际核销、原退款及现金全保留。 |
| HK-126-business 会员套餐购买 | 原会员同客户新未终态宿主申请1套→客户本版authorization→finance本人接原pay Task并实际到账2400分→两Lot发行。proposed/authorized均无Lot或现金。 |
| HK-127-business 会员套餐退款 | 真实消费各1000milli后，原UI分别申请剩余work及part各1000milli；不同主管批准，finance本人接各pay Task，以原账户实退800、400分。Claim占额／Entry注销与原现金分开核。已耗材料不回库。 |

## 有限同轮来源和必要前置更正

要求 membership-hk117-128-118-089-094、materials-hk069-045-054-083-070-072-073-051-061、master-data原15项及repair-selfpay原六项在本轮runner和各checkpoint实际complete/passed，catalog与五路径provenance一致，镜像snapshot稳定且相关脚本逐文件SHA一致。只读核有限membership_sources客户／会员／原卡／普通充值退款Entry／账户、material_sources.primary的Item／Enrollment／原采购Receipt与StockMove／仓／明确source_location_id、实际HK175 WorkItem及HK031 Resource；无旧DB扫描择优、静态候选降级或fixture业务成果。

原repair前序车辆客户与会员来源客户不同。补丁25已明确授权仅本候选由原客户车辆页面，以sales_peer原客户负责人本人新建同会员客户的17位新VIN／明确关系资料与GroupVehicleIdentity；保留既有GroupCustomerIdentityLink。原repair仅复用真实已释放工位及合同，不复用旧CV／客户／终态工单。service在原现场接待walk_in→核VIN、里程、本次原件arrive→convert，实际生成本客户未报价v4修单、IntakeContext、Binding与Task。

即时重验本人UserStore1的sales/service/manager/technician/inventory/finance、客户仍属sales_peer、会员／卡／主档／账户启用、工位空闲，有限材料实位及库存真实数量不少于1000milli且原成本已知。当前不代经营主体策略或现金主体验收；存在本店business_entity_policy时明确停止。附件全由原UI选择仓库外独立合成TXT，实际存储字节只内存length/SHA核对，证据仅metadata，不输出BLOB、密码／会话或其他秘密。

## 实际样例和原事实分账

新Rule适用本店1、30天、unused_before_expiry、service_store承担。work为当前真实job作业两完整次，quantity=2000milli、C/P/S=2000/1600/1600；part为原采购Item升，quantity=2000milli、C/P/S=1000/800/800。每套C/P/S=3000/2400/2400。本次各1000milli施工／领料，capture的C/P/S=1500/1200/1200；真实未用两笔退款800＋400，购买净现金1200。

金额全为整数分，数量全为整数milli；job1000代表一完整次。购买实收产生原Cash(category=repair_package_purchase)、事件及两Lot；quote只有两Hold／ReservationLink／Snapshot，占额不计实际消费。manager1500最低价、service授权、technician start/finish、inventory原位置prepare后实际issue1000、不同service质检、manager客户全承担1500及明确合成人工成本0，材料成本沿实际Item平均成本算法和原StockMove。库位准备不扣库存；发料可在该Item其他库位追加零数量再分摊价值Entry，旧行只放行有限该Item Balance的value/version及明确源位quantity，全部数量／成本合计守恒。

finance在原package-capture确认本版实际履约，生成两正区间PackageEntry、两PaymentLink及四内部Settlement(center负S/store正S)，释放原Hold／ReservationLink；这次核销不另收现金，也不编造package_capture Task。原客户应收真实归零后，service本人repair_release确认实际接车，工位释放、新修单completed且原Task结束。内部中心仅记账，不进行集团真实支付或银行动作。

未用退款从completed宿主原UI分别提出，不伪造selections数组批量提交。request仅冻结原剩余[1000,2000]，approve才产生PackageRefundClaim.reserved；finance原pay Task和原购买账户实退后Claim.applied、正数量Entry.refund注销剩余区间、Cash(category=repair_package_refund)各800/400。原已消费[0,1000]、两PaymentLink、四内部Settlement、原Lot数量/C/P/S/snapshot以及原修单状态保持；最终可用量两批均0。普通会员本金balance/reserved不变，没有GroupEntry充值抵用，也没有材料实际回库。

PackageRule与repair_package_*是混合作业／材料合同；BenefitRule(kind=package)是独立旧按次权益。本候选不借旧fixture package1、不倒贴原已授权报价、不把旧组合券用途改成新组件，也不把PackageRefundClaim当RechargeBundle RefundHold或售后AftercareHold。

## 版本、回执和保护

每个业务动作只有单次原UI点击，等待原GET与可见／enabled表单。新CV和新预约GET按唯一POST返回ID绑定native response listener/Future，包含先到GET竞争与finally清理；未发额外HTTP或重放。登录和原Task交接完成后取全库baseline。交接沿原AssignInput三字段，先原generic Case GET和真实DOM再点击；记录本人当前门店、Cookie/CSRF/x-app-request、request_id摘要、来源版本及原返回事实。

规则／Mapping／购买／退款／capture严格GroupReceipt；quote、原维修动作和库位准备严格FlowReceipt；book/arrive/convert严格IntakeCommandReceipt。摘要按原执行器规范化实际完整输入，保存结果等于原POST响应。购买／退款核Purchase/Refund及当前Case双CAS，原报价Lot当前version、授权当前Quote digest、原库位Case版本与独立原Task均逐动作核对。

Guard对全业务表哈希、全部旧行逐列比较，只允许本次有限ID／准确追加数。Group动作的宿主通常只version/updated_at，接待state、quote state/data及原维修state/data/cost/completed_date按动作收窄；原closed Task保护，当前open Task仅合法完成列。Purchase／Lot／Hold／ReservationLink／Refund／Claim、Member／Account、明确Item／Balance／Allocation／Resource／新CV均有限列。旧现金、库存Move、会员本金／权益、事件、回执、来源客户车辆与旧报价不覆盖删除；附件正文内存比较保留但脱离JSON。

若本会员已有会期，强制读取本轮已实际passed的member-points-tier有限来源和当前冻结规则，不把它的静态候选当证据。新授权产生真实PointsClaim；接车后基于实际履约P1200、原规则100分获1的整数算法核12消费积分、新PointsChange／Wallet／Entry。无有效会期时保持null-rule Claim及0变更。购买款与未用退款不赚消费积分；不为了本候选禁用正常积分。

## 交接与未测范围

成功末尾才输出 repair_package_sources及report_sources：customer/member/account、新CV/VIN、工位／作业／Item／明确源位、预约／接待／新repair、Rule v1/v2／Mapping、Purchase／原Cash、两个Lot／Quote／Hold、capture Entry／PaymentLink／Settlement、两Refund／Claim／Entry及现金、实际RepairStock／StockMove／成本、PointsClaim／新Change有限ID。任一失败保留当项failed、已开始其他项partial、未执行项not_tested；manual、人类体验及193全验收均pending/false。

未运行：原UI时序／lookup／上传、有限1500秒预算、首次完整四项。已耗材料售后实退与权益恢复、逐组件停工和保留费、过期／跨店／并发／全部异常、零对价注销、经营主体、真实银行、ClamAV、PostgreSQL、员工验收均not_tested。本候选不以未用退款证明已耗实物退回，不以静态审阅记四项通过。

静态审阅：本源码AST、七处DB调用均SELECT-only（动态表名限制在有限已审集合）、无app导入／直接HTTP业务写；既有helper导出符号、原四题名/check、三元组1500及空白已核。自审改正同会员CV来源、原walk_in标题、无策略时不产生EntityContext、原Hold摘要、平均成本库位再分摊、原占额与应收区分，并收窄Closed Task／宿主列。这些是候选写作阶段合同核对，未记实测失败或通过。

当前人工审阅源37路径集合SHA256=dfbb977d157fa00754f7274ac4a4237619a5e7043ff762e51307e224df5dd43c；算法为路径排序各文件bytes SHA组成path:sha及LF（末LF保留）后SHA。集合为app下customer_service.py/customer_service_api.py/customer_service_models.py/repair_package_api.py/repair_package_service.py/repair_package_models.py/repair_package_aftercare.py/repair_package_integrity.py/repair_service.py/repair_api.py/repair_models.py/group_service.py/group_benefits_service.py/group_benefits_models.py/membership_points.py/membership_service.py/member_pricing_service.py/service_intake_api.py/service_intake_service.py/service_intake_models.py/flow_engine.py/warehouse_stock.py；web下repairpackages.js/repair.js/serviceintake.js/customerservice.js/memberpricing.js；tests/browser_click下business_acceptance_catalog.json/repair_business.py/master_data_business.py/material_business.py/membership_business.py/member_followon_business.py/member_points_tier_business.py/finance_business.py/sales_order_business.py/vehicle_purchase_business.py。该源指纹是静态审阅事实，实际运行仍须新的镜像provenance全部同轮核对。

根独立静态审阅（2026-10-01）：候选c75a0168及作者交接cdc94b94字节核准；阅读新增同会员CV/intake、规则与Mapping、购买/issue、原Lot报价/双CAS/独立授权、真实发料及平均成本、capture/四内部记账、未用两退款及v2历史保护，复核实际API/web/models及复用helper。四check只正向有限合同，未用退款不冒充售后实物返修；经营主体策略/跨店/过期/异常/真实条件仍明确待测。AST及七直接SQL SELECT、无app import核对通过，未见确定静态阻断。当前根三个关联复验仍有两项运行，因此不注册、不执行，不记四项passed。首次动态UI和1500秒预算尚待新实例验证。
