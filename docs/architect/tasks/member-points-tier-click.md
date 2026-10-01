# 会员有效等级、真实消费积分与直接赠券候选

2026-10-01，test_inventory；依据 PATCH-M8-4-BUSINESS-193-23 与冻结 member-remaining-scope.md（7efc554c7ca423286899b9f4b408163ec54bb1ad2ecbc85074d16ef2dfec06a3）。只新增本页及 tests/browser_click/member_points_tier_business.py；原会员六项、仓储候选、生产、fixture、目录、helper、注册、runner 与共享计划均只读。当前为未注册候选，未导入 app、未启动服务／浏览器或执行场景，以下全是待实际验证合同，不是 passed 成绩。

入口 member-points-tier-hk121-122-188-120-119-131，导出 MEMBER_POINTS_TIER_SCENARIOS=((SCENARIO, member_points_tier_business, 1200),)，有限预算1200秒；沿现有 Evidence、原 native HTTP/UI、Checkpoint、同轮固定来源，无另建执行框架。原六 check 逐原标题绑定 catalog：HK121会员级别调整、HK122会员续会、HK188会员级别、HK120会员积分调整、HK119会员积分兑换、HK131消费券赠送。父实际执行后才可更新外部逐 check 结果；任何来源／操作／Guard失败终止，保留已办事实和 failed／partial。

## 唯一真实前序与原身份

- 原会员 membership-hk117-128-118-089-094 完整同轮 passed checkpoint 的 membership_sources：本人 customer_id/member_id/active_card_id/account_id、普通 topup/refund 原 Entry/Cash ID。只校验原10000与-4000真实关系；当前本金可已受其他同轮合法消费影响，先读基线，再证明本批不变，不误断仍为6000。
- 原 materials-hk069-045-054-083-070-072-073-051-061 的 material_sources.primary：有限 Item/Enrollment/warehouse/source_location_id/location_ids/原 purchase/receipt/stock_move。当前本店 materials 仓／库位活跃、原 Item 与真实本位量≥1000milli，取当前实际平均成本，不借库存旧快照。原 master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187 的实际 HK175 WorkItem 校验保持有限主档来源；本批无安装，不假造它的施工。
- 三份来源在当前 browser-click-report.json registered/passed，checkpoint complete/passed、全部逐 check、目录SHA及 origin/source/runtime/evidence/database 五路径一致，provenance.snapshot_stable 与当前候选/各直接helper/来源脚本 SHA匹配。没有跨 run 或旧历史成绩补位。
- 复用 store1 的 service、manager、finance、sales_peer、inventory 和随机 admin；逐岗位实际 UserStore 核对，客户仍为 sales_peer 本人。admin 只原 admin-only 会期规则及不同申请人的会员价独立复核；财务／库管／销售都实际本人操作。无新 fixture 或预置会期／积分／券／现金／库存结果；原主体策略若尚无完整前序则硬停，不能绕过。

## 六项实际输入与源结果合同

1. HK121：manager 原 benefits 发布独立零售价 points 规则，admin 原 membership-rules 发布 A/B 两个启用版本、自然月1个月、收费300分、before_start退款、每100分真实消费获1分。service 原 tier_change A→manager独立 approve→service execute；再原改 B，当前终止日保留，A/B旧 MembershipPeriod 不覆盖。起日用原 Case.business_date，自然月按月末截日算法精确核，原页面 active_period_id/B规则和期间一致。
2. HK122：service 原 renew B，manager独立批准，finance 本人原 Task上传本单 evidence、原账户／唯一流水，实际收300分，未来 MembershipPeriod、MembershipFee、Cash关联；尚未开始原期间另 renew_refund→独立批准→finance 原账户实退300。追加原负 Fee、MembershipFeeRefundBasis、PeriodVoid；原续会 Case 仅允许 guard_refund 的 version/updated_at 触碰，原会期／收款不改，当前 B仍有效，续会净Cash0。
3. HK188：manager 原提出本店 retail goods 9000bp，冻结 B原版本、有限本次 Item/version、日期、member_then_benefits；原 submit→原申请人实际自批403，仅追加一条原业务规则拒绝，其余业务与全部旧行不变→admin作为不同本人经原 Task交接独立 approve。sales_peer 原新 Retail：1.000件、普通单价1000分、无安装、无手工优惠、不关联维修，明确选择本版会员价；冻结价900、折扣100、Snapshot/两component Line准确。原主管审批／客户授权、inventory实际位置准备和发运、finance收900、本人客户实际接收；只有接收后 Claim.basis900/target9、PointsChange+9和独立 earned Wallet/Entry才成立。授权前 freezes当前B积分规则，旧 null-rule claim完全不动。再原同编号新停用价格版本、submit／独立approve，新报价候选无旧规则，取消未提交表单不写业务；旧批准报价／Snapshot／商品行／Cash逐列不改。
4. HK120：原 points_adjust／adjust 订单 manager本人 execute，从该赚取批次扣1，负 Entry、不覆盖原 grant或PointsChange；另原 benefit_issue／grant 新赠5分、独立钱包和原订单，不能冒称消费赚取。API与原权益页面分别核赚取8、独立赠5，本批零现金，原本金不变。
5. HK119：manager 原新零售价 coupon，固定每份2积分。finance按原会员订单实际核对3分兑换422非整倍、10分兑换409不足，拒绝全库不变，明确放弃填写并原 cancel保留被拒绝申请。另原实际 exchange4：源负exchange_out -4、新Wallet2份、exchange_in +2引用原out Entry，赚取批次剩4、赠分仍5，无Cash或假清算。所有会员、订单、Case、钱包当前版本及本人Task精确提交。
6. HK131：manager 原新 benefit_issue／grant 同原零售价券1张，独立Grant Case/Wallet/Entry，无original_id/现金，source_kind=grant；与兑换2张和组合附赠完全分列。原页面四有限批次逐余额／占额／有效期／原账API/SELECT核对。末尾当前本金／占额与本批基线完全一致；净Cash只有300-300+900=900分，不把积分面值或券面值计收入。

## 原动作、旧行与证据保护

原UI/接口为 /api/membership/rules、/members、/orders及/actions/approve|execute|cancel；原会员动作 order.version/case_version/member_version、积分另wallet_version。会期create/command原GroupReceipt准确 action/payload/result；权益execute委托 benefit:member:grant|adjust|exchange，完整宿主+权益两事件、GroupEvent、MembershipEvent与原结果一起核。会员价 /api/member-pricing/rules、/rules/{id}/actions/submit|approve，version为原Case；Create receipt纳入原schema的allow_contract_pricing=False默认值。精品 /api/retail/orders与原approve/authorize/dispatch/receive/accept，FlowReceipt含原完整payload；库位准备只原 /api/warehouse/allocations/{case_id}，prepare不是实物出库。

Task交接复用原 AssignInput 三字段（version/assignee_id/reason），先等实际 genericCase GET、标题和唯一按钮 visible/enabled，原 Task确实交到随机本人；折叠操作通过实际 details summary展开，绝不force／重放／改DOM事实。成功只单次原form submit，Cookie/CSRF/currentstore/request_id摘要随原响应记录，新实体GET由原唯一POST返回ID绑定防旧读竞态；拒绝保留原服务器refusal，放弃填写与取消申请分开核。

自有 Guard 每次全business snapshot比对，仅明确追加数及有限ID/列允许改变；其余所有表/旧行逐列不变、不可删除。Member只version/updated_at，本金不准变；本次钱包只balance/reserved/version/updated_at；本次Order批准/终态、原Case正向state/data/cost/completed_date、原Task终态有限列。原续会FeeBasis只引正确原Cash，规则/Period/Fee/Void/PriceRule/Scope/Decision/Snapshot/Authorization/BenefitEntry/PointsChange/Cash/StockMove/Receipt/Event/Audit都按本次有限来源追加；PointsClaim只本次原ID的basis/target/version合法变动。实物只本Item/Balance/准备Allocation原数量价值版本，整数平均成本和原位置账合计一致；现金只本次原Account.updated_at。登录发生在写入／只读刷新基线前，审计表整表不排除。原上传helper核所选TXT实际BLOB/size/SHA与structure_only，本证据仅metadata，不输出正文bytes、User.password_hash、会话hash或凭据。

report_sources/member_points_tier_sources 仅成功完整尾部写：customer/member/account/primary Item/原位；points_rule与A/B等级/Case/Period/active_period；续会Case/Period/Fee/Cash和原退款Fee/Cash/Case/Void/FeeBasis；批准与停用PriceRule、PriceSnapshot/Line/Authorization；Retail Case/Line/StockMove/Cash/PaymentLink；真正PointsClaim/Change/earned Wallet/Entry、负调整Case/Entry、独立赠分Case/Wallet/Entry；兑换目标Rule/Case/out/in Entry/券Wallet、原拒绝Case；直接赠券Case/Wallet/Entry；分列9赚取/4剩余/5赠分/2兑换券/1直接赠券与净Cash900。未来HK168可按有限PointsChange真来源核，不继承本页静态成绩。

HK133/126/127、原消费退回/PointsRecovery/Debt/清偿、已耗材料售后原退、过期/跨店/价格互斥/全部条件、会员本金消费和直接赠券后续商品用途核销均未执行，不增check。人工流程简洁度／文案及完整193验收仍pending；structure_only不是ClamAV、合成Cash不是银行支付、Group内部往来不是集团真实付款。

静态自查：候选AST、原helper符号、六个标题/check绑定、所有八处DB调用SELECT-only（有限常量表/字段白名单，另三处只读原拒绝表）、三元组形状/固定预算、差异空白核对；均未执行应用／浏览器。源与候选最终SHA由冻结交接另外报告，本页不自引用。真实渲染、livechoice、Task时序、原natural-month/refund side effects、全流程预算和实际Guard仍待根新鲜联合运行。

追加窄修 PATCH-M8-4-MEMBER-PRICE-REFUSAL-OBSERVATION-01：独立静态短审发现108b77ef原自批403观察误把服务器正常追加的 escalation_refusals 当作业务写入失败，尚未实际执行，不登记实测失败或通过。仅该分支单次原UI提交，精确核完整原文“申请人不能自批会员价格，管理员也不例外”、403响应refusal.id/category=rule/can_escalate=false及同ID本人／manager／store1／原POST approve路径／source=page／consumed_at与consumed_by_id均null的新行；全表哈希仅允许此表改变，原拒绝旧行逐列保护且恰一条新增，其他所有表包含价规／Task／会员／现金均不变。放弃填写以后相对拒绝后基线再次全库不变，不新建评审。原422非整倍与409超额继续原 rejected_submit 的零业务写要求；shared helper、生产、目录与注册未改。

当前只读合同源集合 SHA256=ea17e11ffd4e4c1d4b0a4d4dc04bf8e59e698e837bedbbb4386fbadc0cc285b0。算法为下列33路径排序，各取bytes SHA256，path:sha加LF（含末LF）后再SHA256：app/membership_api.py、membership_service.py、membership_models.py、membership_points.py、membership_fee_corrections.py、membership_fee_correction_models.py、group_service.py、group_benefits_service.py、group_benefits_api.py、group_benefits_models.py、member_pricing_api.py、member_pricing_service.py、member_pricing_models.py、retail_api.py、retail_service.py、flow_engine.py、retail_group_service.py、retail_group_rules.py、invoice_service.py；web/membership.js、memberpricing.js、benefits.js、retail.js；tests/browser_click/business_acceptance_catalog.json、requirements_manifest.json、membership_business.py、material_business.py、master_data_business.py、member_followon_business.py、finance_business.py、vehicle_purchase_business.py、sales_business.py、sales_order_business.py。原会员六项2c8777cf与仓储1d1372b0复读保持，没有改动这些冻结文件。
