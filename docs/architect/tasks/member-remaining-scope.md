# 剩余会员原业务只读范围

2026-10-01，test_inventory；仅本页写入。九项均为原目录的未验收合同，未创建候选、注册或运行实例。会员六项首次联合仍由根执行，不能预先继承 passed；仓储导出已窄修为三元组加固定720秒并冻结。本页建议先登记六项等级／积分／直接赠券，再登记三项混合套餐，均不新增 fixture、岗位或集团中心真实支付。

| 原需求／完整 check | 原输入至结果、页面及接口合同 |
| --- | --- |
| HK119 会员积分兑换／HK-119-business | `#membership/{customer_id}` 新 points_adjust／exchange 单；`POST /api/membership/orders` → `/orders/{id}/actions/execute`，finance 本人任务。真实可用 points 钱包，目标本发行店零售价 coupon/package、正 exchange_points_per_unit、精确整数倍；原 BenefitEntry(exchange_out) 减源积分、新 Wallet/Entry(exchange) 引用原扣减，MembershipOrder/Event 完成，零现金。 |
| HK120 会员积分调整／HK-120-business | 同原页 points_adjust／adjust，由 manager 本人 execute 原扣减单；只减可用原积分、追加负 BenefitEntry。正向另建 benefit_issue／grant 的新 points 批次，不改旧 Wallet/Entry；settle_debt 属独立原欠额清偿，有真实债才办理。 |
| HK121 会员级别调整／HK-121-business | admin 在 `#membership-rules` 发布冻结等级版本；服务顾问新 tier_change 单→不同 manager approve→service 本人 execute。MembershipPeriod 从原业务今日起至当前有效期终止，无有效期才用规则自然月；旧会期不覆盖，实际客户等级与新报价候选同步，不能拿价格规则 CRUD 代替。 |
| HK122 会员续会／HK-122-business | 服务顾问 renew 单独立批准→finance execute，原 MembershipPeriod 起日为 max(今日、全部旧有效期终止次日)，自然月终止；收费产生 MembershipFee/Cash。未来未开始、允许退款的最新续会另 renew_refund 单独立批准→finance 原账户整笔退款；负 Fee 引原 Fee、追加 PeriodVoid，旧会期与已消费本金不改。 |
| HK126 会员套餐购买／HK-126-business | `#repair-packages/{member_id}`，`POST /api/repair-packages/purchases` 选择真实非终态 lead/membership/order/repair 宿主；`/purchases/{id}/actions/authorize` 原客户授权→finance issue 全额到账。PackagePurchase/Contract/Event、两个实际 work/part Lot 和原 Cash 一致；仅申请／授权未发行无 Lot，组合次数赠品不能替代。 |
| HK127 会员套餐退款／HK-127-business | 原 purchase 的 refund_request 选择未用未占的原 Lot 区间→`/api/repair-packages/refunds/{id}/actions/approve` 不同 manager→finance **pay** 原账户。PackageRefund/Claim、退款 Cash、PackageEntry(purpose=refund) 消耗原区间并保留原分摊／到期；取消只释放 Claim，不能删除。使用过的配件须另从原领料实际退回，不能冒充未用。 |
| HK131 消费券赠送／HK-131-business | 主管在原 benefits 发布零售价 coupon 规则；原 membership 新 benefit_issue／grant 单→manager execute，或原 benefits grant 明确真实宿主、原因、凭据。独立 Wallet、BenefitEntry(grant)、Order/Event，零现金；组合附赠与付费 purchase 均不算本项。 |
| HK133 套餐卡类型／HK-133-business | `#repair-packages` 原拟定新套餐；`POST /api/repair-packages/rules` → `/rules/{id}/actions/approve` 不同 manager → `/rules/{id}/mappings` 本店真实 WorkItem/Item。至少1 work＋1 part，C≥S≥P，group 承担时 S=C、service_store 承担时 S=P；冻结规则／Decision／Mapping／单位／规格／source version。新版本或 revoke 不改已售合同。 |
| HK188 会员级别／HK-188-business | `#member-pricing` 原提出→`POST /api/member-pricing/rules`→`/rules/{id}/actions/submit`→不同 manager/admin approve；冻结 MembershipRule、可选 MemberTier 参考版本、scope/component/source/日期/stack_mode。实际有效会员新 retail/repair/addon 明确选择原 rule_id/version 并冻结报价应用、履约核对；参考等级 CRUD 或空 candidates 不计。 |

## 六项最短链：有效会期 → 实际消费积分 → 原扣赠兑

仅接受同轮 passed 的 `membership-hk117-128-118-089-094` 有限 membership_sources(customer_id/member_id/account_id/active_card_id/原充值与退款账ID)，`materials-hk069-045-054-083-070-072-073-051-061` 的 material_sources.primary(item_id/warehouse_id/source_location_id/enrollment_id/receipt_ids/stock_move_ids)，以及 master-data 的 HK175 实际 WorkItem 和 HK187 参考等级（可选）。依赖须完整报告、逐 check、checkpoint、五镜像路径、目录与源指纹同轮匹配，再按有限ID核当前版本／本店／原所有者；库存余额重读，不把上游快照当剩余实物。当前 member_followon_sources 的 points_consumption_or_points_change=false；原组合 points 受 component guard，不作为普通兑换／调整钱包。

1. 本店 admin 原规则表单发布独立 points BenefitRule 和两份启用 MembershipRule（自然月、明确收费与 before_start 退款；启用真实消费赠分，例如分母100分、分子1）。服务顾问 tier_change A→不同主管批准→service 实办，再改 B 保持当前终止日，真实 HK121；本批实际等级与来源字段不可省略。B 规则启用积分须在新消费单创建之前已成为当前 MembershipPeriod，不能事后给既有 null-rule PointsClaim 补规则。
2. B 续会收费300分，独立批准、财务实际到账，核未来新会期与 MembershipFee；随后原续会未开始退款300分，独立批准／原账户 actual refund、PeriodVoid。当前 B 会期保留，续会净现金0；错误账户、开始后或后继会期存在的退款保持原拒绝。HK122 不由续会申请／批准代替。
3. manager 提出本店 goods 会员价9000 basis points，绑定 B 和有限 Item、明确日期／member_then_benefits；原 submit、admin 独立 approve。sales_peer 原新 retail 选择本人客户，1.000件、原价10.00元、明确该会员价，核冻结价900分；走原价格审批／客户授权／库管准备确切库位与发运／财务现金900／客户实际接收。才有本次原 PointsClaim(basis=900)、PointsChange(+9) 和对应积分 Wallet/Entry；金额公式为整数、积分按原规则向下取整。该原零售价消费同一实物 StockMove、Cash、Quote 与会员价授权分别核对，不能用授权当接收。追加后续价格版本不重算旧已授权报价，HK188 必须包含本次实际应用。
4. manager 对上述真实赚取批次原 adjust 扣1；另 benefit_issue／grant 新发5积分，两个来源分别记录，不覆盖原9积分来源。finance 从赚取批次 exchange4（目标券每份2积分，发2份），原剩余4分、独立赠分批次5分、原扣兑零现金；奇数不整倍／超额原拒绝全业务不变。HK120 与 HK119 分别留原订单、原源Entry、钱包版本和整数守恒。欠分时禁止消费／兑换及新分先抵债，须有后续真实退款债源才能验，不能造 PointsDebt。
5. manager 原新 grant 单直接赠1张零售价 coupon，记录本次新 Wallet/Entry、零现金，不引用组合 Component；HK131 独立留证。其实际后续券消费若本批未走原用途审批及 reserve/capture，只记未执行，不能把赠送当核销。

## 三项混合套餐：真购买 → 真作业／领料／核销 → 原未用退款

需上述客户/member、当次 master WorkItem(id/code/billing_unit/version)、material Item/本店材料仓确切库位与当前可用至少1000milli；可用 `repair-selfpay-hk031-034-044-049-053-079` 的 report_sources(customer_id/customer_vehicle_id/vin) 作真实客户车辆来源，但旧已交车 repair_case_id 只读，不能用于新购买宿主。service 原新预约→到店→转换产生本客户真实非终态 repair；保持 CV 当前版本／实际进厂凭据，购买与报价都引用它。

原 service 拟 work2000milli(C2000/P1600/S1600分)＋part2000milli(C1000/P800/S800分)，service_store 承担、组件单位分别为当次 WorkItem 的 job 与原 Item 的升；manager 独立批准、本店 mapping，原同客户宿主购买1套、客户本版授权、finance 实际2400分到账发行两个 Lot。真实维修 quote 选各1000milli原 Lot/version，冻结 Hold 区间：C1500/P1200/S1200；原主管价格审批／客户授权→inventory 正确 prepare 和领1000milli→technician 真开工完工→独立质检→finance 原 capture→接车。PackageEntry/PaymentLink/Settlement 各对 C/P/S、净领料及原平均成本，核销不第二次收现金；有效积分规则若由这次完成维修合法生成 PointsClaim/Change，须完整纳入本次有限允许范围，不能禁止或忽略。原剩余各1000milli按原分摊退款1200分，真实 request→独立 approve→finance pay 原账户，购退净现金1200分，未用物资从未领出，不虚构库存退回。保留原购买合同、Lot 总量和到期；退回区间靠 purpose/refund 与 spans 生效，PackageEntry 数值本身不冒写负数。

## 权限、原版本与全部旧行边界

复用 store1 的 sales_peer/service/manager/finance/inventory/technician 及随机 admin；仅 admin 发布集团会期规则，独立 admin 只作合法规则复核，不替员工收款／施工。会员原 create 含 request_id/customer_id/purpose/reason/values，动作同时携带 order version/case_version/member_version，积分另 wallet_version；membership_review 与 membership_execute 原本人 Task 必须真实交接。会员价动作 version 是其原 Case version；package purchase/refund 是各自身 version＋宿主 case_version，映射冻结原 source_version；原授权 quote/lot/hold 版本逐次取真值。Task 交接仅原 AssignInput(version/assignee_id/reason)，等原 GET 与真实表单 visible/enabled 后唯一点击，不绕 loading 或强点隐藏操作。集团会期和权益均按当前店／原来源授权，sales 本人客户守卫保留。

每次真实 UI 写入前后保护全部旧行、未授权表和库存／现金原账，不宽免整表：只准当前有限 Member/Wallet balance,reserved,version,updated_at；当前 finite Case/Task/Order/Quote/repair/retail/Lot/Hold/Refund/Claim 的原动作合法列；实际本次 Item/Balance 数量、价值、平均成本、版本；原 Account.updated_at。规则版本、Period/Fee/Void、权益账、PointsClaim/Change/Recovery/Debt/DebtPayment、会员价快照／Authorization、套餐合同／Entry／支付／结算、Cash／StockMove／WarehouseEntry／事件／回执／审计均按本次准确来源追加或原定义有限合法更新，所有旧来源逐列不变、绝不删除。全库 Guard 用完整内存行比较，附件只输出metadata/长度/SHA，正文仅内存校验，不持久化密码／会话hash。金额整数分、物资与混合组件整数milli、积分／券整数份；现金、会员本金、权益面值C／实付P／内部结算S及物资成本分别记，内部双方和0不表示银行结算。

拒绝证据优先原 self-approve403、CAS409、原钱包不可用／欠分／过期／不足409及非整倍422；旧等级报价、已占／已耗套餐区间、未发行套餐、异客户／异店、原退款账户、原凭据类别和扫描状态保持原服务判定。真实消费退款后的积分追回／债务／清偿、混合套餐已领材料的售后原退（`/api/repair-packages/aftercare/{id}/return-material` 引原 StockMove、inspection、Aftercare/source version、实际接受才恢复库存）、已做工时退费、过期零对价注销、跨店、价格互斥权益及其他条件分支仍明确 not_tested，不能用未用区间退款冒充这些成果。九项源审阅不等于九项通过，人工体验与193完整验收仍 pending。

研究源摘要 SHA256=3b3a97a9b01d429bce9f6442e1e474d7e5408c4e9841237c8fd428fb00341163；目录 eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff、manifest 19840f4fc5fd816d94ea35a4602a31bde4674105e44621eeb4cfe42bdad27a1f。摘要算法为路径排序的 path:文件bytes SHA256 加LF（含末LF）再SHA256；源为 app/group_service.py、group_benefits_api.py、group_benefits_models.py、group_benefits_service.py、member_pricing_api.py、member_pricing_models.py、member_pricing_service.py、membership_api.py、membership_models.py、membership_points.py、membership_service.py、repair_package_api.py、repair_package_models.py、repair_package_service.py、retail_service.py；tests/browser_click/business_acceptance_catalog.json、member_followon_business.py、membership_business.py、master_data_business.py、material_business.py、repair_business.py；web/membership.js、memberpricing.js、benefits.js、repairpackages.js。HEAD 8993ca8c；未读真实库／.env，未导入app或启动运行。本页只提出后继范围，两个作者候选文件须根另登记精确补丁后方可写。
