# 会员组合充值与真实消费下一批只读范围

2026-10-01，test_inventory。本页仅为根授权的只读研究产物，尚无新脚本、注册、业务实例或运行成绩。现有财务后继候选 8850917f 保持冻结；根另行复验核账写事务。HEAD 为 8993ca8c755194a42a48e7323fe355e80c6bf9ae，工作树另有根负责的补丁，不以 HEAD 代替当前源。当前会员五项 HK117/128/118/089/094 的实际通过来自根报告；HK124/125 普通本金仅 partial，不能直接继承为完整验收。

## 推荐六项及计数边界

建议下一精确补丁只授权新增 tests/browser_click/member_followon_business.py 与 docs/architect/tasks/member-followon-click.md；拟单个原生入口 member-followon-hk123-124-125-129-130-132。先把下述原输入、有限前序、权限和结果合同交根登记，再编码、短审、接线及外部实际运行；本页不预先授权两个候选文件。无新角色、fixture、生产改动或共享计划写入。

| 完整候选 check／原标题 | 必须发生的本轮原输入与结果 |
| --- | --- |
| HK-123-business 会员卡充值套餐设置 | 原管理员页面发布默认未启用版本，再追加明确启用的新版本；每份本金与 bonus/points/coupon/package 四种零售价、不可单独退款赠品各引用独立冻结规则，门店/期间/整份退款条款一致。实际购买本版后再追加后续版本，旧购买和四批赠品不变，新申请只能选当前启用版。 |
| HK-124-business 会员储值卡充值 | 同轮原 membership 已发生的普通 topup/财务 execute/唯一本金与 Cash 作为显式局部前序；本批另由服务顾问在原组合页确认条款、申请两份组合，财务上传本单 receipt、选择原账户并实际收款发行。实收全部记本金，一条原现金及本金来源、一个 Purchase、四个独立 Component/Wallet/发行 Entry，同事务一致。只在本批组合支路和同轮普通前序均真实完成时才计完整。 |
| HK-125-business 会员储值卡退款请求 | 同轮普通原款申请、独立批准和实际退款的既有 partial 前序逐源核对；本批真实消费后向原组合申请剩余一整份，不同主管批准占本金和四赠品，先撤销一单证明完整释放，再独立申请/批准/财务原账户退款回收。已耗赠品使两份申请真实拒绝；原实收/已耗来源不可覆盖，不用其他批次凑退款。 |
| HK-129-business 消费券类型 | 主管发布本店零价赠券和独立付费券冻结版本，逐核 C/P/S、承担方、期限、适用店及退款规则；付费批次发行后追加同编号新版本，旧钱包仍按原版面值/售价/结算/到期及商品用途履约，原页面可选当前发行版本。BenefitRule 没有 enabled 字段，不伪造启停。 |
| HK-130-business 消费券生成 | 原会员“购买券或套餐”生成 benefit_issue/purchase 独立单，两份付费券由本店财务本人任务 execute，真实收款生成唯一购买 Cash、Wallet、purchase Entry 和原内部往来；零售价组合附赠不能代替本项。 |
| HK-132-business 消费券信息查询 | 本人客户的原集团权益页在发行、占额、实际核销、原付费券未用份退款各时点真实打开/刷新并核对非空规则、有效期、可用/占用、Reservation、Entry、BenefitRefund；返回原组合查看整份回收另有来源，不伪造普通券退款记录。只读页面和刷新不得新增款项或业务。 |

普通 HK124/125 前序只接受同轮完整已 passed 的 membership 场景和其中原 partial 原件；不得拼历史运行。若根要求每项在本新场景独立重演普通支路，先登记范围再增加另一原 topup/原款退款，不能默默把静态前序算成功。全 193、人工简洁度/文案、所有条件异常仍 pending。组合自动赠送没有实际原 grant 订单，不提交 HK131 check；其他余额页导航、混合付款辅助步骤不产生额外 check。

## 唯一同轮前序与岗位

1. membership-hk117-128-118-089-094/business-checkpoint.json 的 membership_sources：customer_id、identity_id、identity_link_id、member_id、active_card_id、account_id、topup_case_id/topup_entry_id/topup_cash_id、refund_request_id/refund_entry_id/refund_cash_id。核客户仍为原 sales_peer 本人、门店1身份已明确关联且启用、卡历史不变，普通本金净6000分且占额0；具体普通 partial 载荷须对应同原件，不能仅看顶层 passed。
2. materials-hk069-045-054-083-070-072-073-051-061/business-checkpoint.json 的 material_sources.primary：item_id、warehouse_id、source_location_id、location_ids、enrollment_id、purchase_order_id、receipt_ids、stock_move_ids、entry_ids。重核此当前原 Item/Enrollment/本店 materials 仓及确切 source_location_id，可用量至少1000 milli；上游记录的库存快照可能已被同轮维修真实领用，不能直接当当前可用量。成本读取当前真实平均成本及原 StockMove，不猜填、不造余额。
3. master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187/business-checkpoint.json 中 HK175 已 passed 的 acceptance_checks[0].evidence.row.id/code：该同轮实际启用 WorkItem 仅作为旧次数赠品的明确作业编码；不扫描 demo 作业、不推定该赠品已施工。
4. 每份依赖须在当前外部 browser-click-report.json 注册且 passed，checkpoint complete/passed/全部逐 check 实际完成，source_contract_sha256 与当前目录一致，origin/source/runtime/evidence/database 五项路径和脚本指纹同轮一致。只取上述有限ID并再次核原DB事实，不取最新整表记录。

复用 business_fixtures.sales_order 的 store_id、sales_key=sales_peer、service_key、manager_key、inventory_key、finance_key，另用现有随机 admin 只办理原 admin-only 组合配置及作为不同获权规则审批人；主管申请的商品用途由原管理员独立批准，二者同店身份重核，不能借管理员替员工消费/收退款。原 finance 任务若归其他合成员工，主管真实通用任务表单交给已知随机财务；等原 GET、准确标题和按钮 visible/enabled 后再唯一点击。AssignInput 仅 version/assignee_id/reason；集团财务待办专属 reassign 另按原 plan_version/task_key/due_date 合同。

## 最短原操作顺序与金额合同

1. 本店主管在 benefits/{customer_id} 原规则表单发布五个不同编码规则：赠金每分 C=1/P=0/S=0；积分每积分 C=1/P=0/S=0；赠券每张 C=500/P=0/S=0；旧次数赠品每次 C=500/P=0/S=0 且 service_code=上述原 WorkItem.code；付费券每张 C=500/P=400/S=400。均由履约门店承担优惠、仅门店1、有效期30天；四赠品 refund_policy=none，付费券 unused_before_expiry。仅 coupon/bonus/paid-coupon 三种实际精品用途须进入下一步；积分不能直接精品抵款、旧次数赠品本批保留而不假施工。
2. **必须先于发行**：主管进入 retail-group-rules，对赠券、赠金、付费券各建原商品用途申请，上传独立公司规则 evidence、选择原 Item 的 goods 范围，显式选择 accumulate_original_unit / original_expiry / none，提交后由不同获权管理员原本人任务批准。RetailGroupEligibility/Scope/Decision 与冻结 Item SKU/单位一致。原发行同事务追加 RetailGroupWallet 并引用本次 Decision/原发行 Entry；已经发行的钱包不能补授用途。旧维修规则、名称相似、只有余额都不算精品资格。
3. 原管理员 recharge-bundle-rules 发布组合V1，保留 enabled=false，原购买页无可售组合；通过“以此追加新版本”发布V2 enabled=true，本金每份5000分，四赠品份额分别为 bonus200分、points100积分、coupon1张、package1次。按真实业务日设发行期间，并确认原 mandatory_terms 和冻结整份退款期限。服务顾问购买2份，terms_accepted=true；财务原 execute receipt/account/reference 总实收10000分，全记通用本金，四钱包余额400/200/2/2。此时本金6000+10000=16000，不宣称该余额按原充值分隔使用。
4. 服务顾问原会员页申请购买上述付费券2张，会员 benefit_issue/purchase 单原财务 execute 收800分。不从已完工维修、已交车销售或 retail 单直接调用 benefits.purchase：原 _source 只支持有效未结束的 lead/order/repair/membership。本批新建 membership 源单满足原守卫。随后主管发布付费券V2（例如C600/P450/S450），原已付钱包V1不改、仍按500/400/400实际消费；未来选旧版的后端拒绝不能宽松或改旧记录。原 membership 购买选择目前包含旧版本，服务端 _current_rule 拒绝旧版，动态易用性待实跑，不预先称硬bug。
5. sales_peer 在 retail 原页面选择该本人客户及原 Item，1.000数量、25.00元商品单价、无安装、无手工优惠、不选会员价、不关联已完工维修。原冻结报价→主管价格授权→销售上传本版 authorization 并确认→库管实际准备确切原库位 allocation、dispatch→销售实际 accept。前端按钮、Case/revision、原占用、StockMove/平均成本、WarehouseEntry/Balance 与真实出库1000 milli 一致。不得在集团方案前点击 receive，亦不得把 authorize 当客户已接收。
6. 在 retail-group/{case_id} 原冻结付款表单上传客户付款 authorization，选择本金1300分、赠金200分、组合赠券1张、付费券1张；只冻结方案，既不占额也不扣款。财务本人对四个原 Tender 分别 reserve 再 capture，每步带原 Case/Plan/Member/Wallet/Reservation 当前版本、原 evidence，逐次核可用→占额→实际扣减。C总2500/P总1700/S总1700，集团核销2500、实际履约对价1700、履约店优惠800、集团承担优惠0、现金份额0、原本金剩14700分。纯集团付款不产生 RetailPayment、Flow PaymentLink 或零额 Cash；四个真实 Capture、原 GroupEntry/BenefitEntry、对应 GroupPaymentLink/BenefitPaymentLink 不可省略。本金和付费券非零内部价产生等额双边往来，赠券/赠金S=0不虚构零金额结算行。
7. 组合当前可退1整份，尝试2份原 POST409且全业务不变，明确放弃原未保存表单。申请1份→另一主管 approve，先占5000本金与四赠品原份额→原 cancel 完整释放、零退款现金→另建1份原申请/独立批准→财务以原购买账户和独立 receipt/reference execute。唯一实际退款5000分、四回收 Entry 都引用各原 grant，RefundPosting/原本金负账准确；本金9700，组合四钱包余额0/100/0/1，占额全0，再无可退整份。原购买不改。再发布组合V3并在原新申请表单核当前选择；不补造第三次成交。
8. 付费券原批次剩1张，前端申请其原款退款→另一主管批准先占1张→财务原本人退款任务上传原 membership 来源单 evidence、按原购买账户 actual refund 400分；BenefitRefund executed、负退款 Entry 原 purchase 引用、原 CashEntry out 和内部往来匹配，原到期日不延长。原钱包归0，无现金退500券面值、不能回收已耗1张。权益原页面核发行/占额/核销/退回各状态及同人同店客户姓名、规则版本。新现金仅10000+800-5000-400=5400分，与本金9700和履约1700分别记，不相加为营业收入。

上述精品出退库仅为真实消费依赖，不计未完整执行的精品采购/退货需求；本批不制造任意库存或费用来源，不创建集团中心真实付款。新现金净额仅本批有限ID，不能对整个本店现金表硬断言5400。

## 原 API、证据及不可省略的守卫

发布及读取沿 /api/group/benefits/rules、/members?customer_id、/members/{member_id}；组合沿 /api/recharge-bundles/rules、/purchases?customer_id、/orders 和 /orders/{case_id}/actions/{approve|execute|cancel|reject}。组合动作 envelope 为 request_id/version/case_version/member_version/values；创建 literal terms_accepted=True，四赠品须 latest、零售价、refund none、同门店集合且 kind 不重复。only admin 发布组合；不同申请人才能批准组合退款，admin 也不能自批。普通 Group/Benefit 旧退款 admin 例外保持原样，本批用不同普通员工，不假称该例外已经验证。

商品用途沿 /api/retail-group/rules 及 /rules/{case_id}/actions/{submit|approve}；本次精品沿 /api/retail/orders 与 /orders/{case_id}/actions/{approve|authorize|dispatch|accept}，库位准备沿 /api/warehouse/allocations/{case_id}；混合付款沿 /api/retail-group/orders/{case_id}/catalog、原详情及 /actions/{authorize|reserve|capture|release|restore|reassign}，主链只调用 authorize/reserve/capture，其他能力不能计已做。新方案必须 actual accept、无进行中退货、无已收 Cash/预收抵用/旧付款、无实退重分；原 API不接受再分历史支付。

普通付费券使用 /api/membership/orders purpose=benefit_issue/action=purchase，execute 委托原 Benefit command；未用原款退款从 benefits 原按钮走 /api/group/benefits/members/{member_id}/actions/{refund_request|refund_approve|refund}，钱包/原请求/原单/会员各当前版本独立携带。费用、原本金与赠金单位均整数分，券/积分/次数为整数份，物资为整数milli；没有字段把 points 当券份数，零售价赠品不存在单独现金退款。

逐次真正原 UI submit/上传/任务交接后，核原JSON载荷及 native Cookie/CSRF、当前店、请求号摘要和原回执/FlowEvent/GroupEvent/MembershipEvent；无 HTTP/SQL 写入、Cookie桥接、DOM赋值或重放。有限新增/更新范围须逐动作声明，而不是允许整个表变化：原 group_member 仅当前ID的balance/reserved/version/updated_at；原当前wallet仅balance/reserved/version/updated_at；原Item当前库存数量/价值/平均成本/version/updated_at与对应本次WarehouseBalance、原finite Case/Task/Order/Refund 合法列。规则、Scope/Decision、发行/支付/退款/库存原账只允许追加；attach_issuance 会触碰本次 eligibility Case 的 version/updated_at，须精确登记此合法来源更新。其他所有旧行逐列保护且不删除，包括旧会员卡/期间/债务、旧批次与旧现金、历史库存、原修销单。正常登录 Audit 在基线前，不排除整audit表。

原 retail authorize 还会合法追加本次 membership_points_claims，member_id 指上述现有会员、rule_id=null（尚无会期），不能把这个无积分来源的 claim 当得分或禁止整个合法动作。只准本次有限 claim；组合积分 grant/回收各真实留 BenefitEntry，当前无欠分则不新增 PointsDebtPayment，本批无消费赠分 PointsChange。invoice_service.sync_source 只同步本次合法原待办，不自动制造发票申请/结果；其实际触及的本次有限 Task 保持逐源声明。

只读表/API定位须限以上 finite IDs；全库保护仍对全原行做内存比较。新附件正文只内存核实字节/SHA，证据只 metadata/长度/hash，不输出密码hash、会话hash、credentials或原正文。report_sources 要保留本批原 customer/member、规则/版本、四赠品及付费钱包/原 grant/purchase/capture/refund Entry、三商品eligibility/decision/binding、bundle原购买/退款/本金/现金、retail原 Case/line/dispatch/stock_move/warehouse_entry/plan/tender/reservation/capture及后续有限券退款ID；给 HK168/169 后继真实积分/券统计，不用金额或“非空列表”猜来源。

## 后继 price／mixed package／groupclear 缺前序，不能计本批完整

- HK119 会员积分兑换、HK120 会员积分调整：本批组合 points 有真实 grant 与回收，但未走 points_adjust/exchange/adjust 原订单、未消费积分、未验证债务阻止与先抵原债。本批不提交这两check。下一条需本人有效 membership 源单、独立 points 钱包及冻结兑换率的零价券/次数规则；exact integer multiple、PointsDebt>0 时禁止新增消费/兑换、赠分先抵原消费欠额不可省略。
- HK121 会员级别调整／HK122 会员续会：现有同轮会员无 MembershipPeriod，因此不能用 MemberTier 参考比例或给新表单填 rule_id 宣称会员价。先 admin 在 membership-rules 发布明确启用 MembershipRule，再原 tier_change/renew 订单独立批准并由相应本人 execute，期间/自然月/费用/原续会未开始退款独立留证。会员价格 /api/member-pricing/rules 原提出→submit→另一主管approve；真实新 repair/retail/addon 报价显式选择 current rule_id/rule_version、当前会期与冻结具体source/component/rate，member_then_benefits 与 exclusive_benefits 两口径分别办，已授权报价不会随等级/版本重算；本金仍可用、权益不能绕互斥。本批普通价已明确选不用会员价，不把候选列表读取当优惠发生。
- HK133 套餐卡类型／HK126 会员套餐购买／HK127 会员套餐退款：组合旧 BenefitRule(kind=package) 是作业次数赠品，不能替代原 mixed PackageRule。下一独立链须至少一个真实 WorkItem 与一个当前物资 Item，规格/单位明确，/api/repair-packages/rules 创建 work+part 的 C>=S>=P 且承担守恒规则→不同主管 approve→原 mappings；同客户未结束 lead/membership/order/repair 源单真实 purchase→客户本版 authorize→finance 全额 issue 后才生成 Lot/原Cash。实际维修 quote 才能原 Lot/版本/interval hold/capture，未issued不会造核销；退款原 unused/unreserved intervals→独立approve→finance **pay**（不是refund action），零价组件只注销无Cash，旧合同/区间/原到期不覆盖。当前已交车/已完工 source 不满足新购买前序，须新建有效源单，不能fixture造lot或拆组合同。
- groupclear 不是新需求名或集团中心付款入口：原前端 group-reconciliation→GET /api/group/reconciliation 只有本店 GroupEntry 与 GroupSettlementEntry 的双边内部往来；另 BenefitSettlement/RetailGroup C/P/S 仍分别核对，不能把普通group页当全部权益清算。统计 /api/group/benefits/reconciliation 为只读；center/store 双边和为0不是银行支付。本批仅核真实有限来源的内部守恒，不计 HK084 跨店调拨实际清算，也不开放他店原单/文件，不新造集团中心现金。
- 精品按原实际部分退回累计整张恢复、保持原期限、零头不可消费且待恢复负债不清零，规则本批确实先独立批准，但没有实际退货/restore；此异常支路及过期、跨店、不同C/P/S、现金混合、安装、库存不足/并发、付费券旧admin自批例外仍 not_tested，不能宣称所有权益规则验收。首批实际消费及组合未用份退款只覆盖本店清晰正向事实和明确的两份不足拒绝。

## 当前源指纹与冻结交接

原193目录 SHA256=eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff；requirements_manifest=19840f4fc5fd816d94ea35a4602a31bde4674105e44621eeb4cfe42bdad27a1f；原DOCX源 ddf297678e5d6d35e1dbfffc5c232c3d56748934eb22b58bbb9f9d5343689aae。已读前序脚本 membership=f2897c762cbb9b0de213679afe47e86297a55fe7cdbeb986f20bd65ba0e649f8、material=15d58e9ee4e2a555cca529f1bd8f87d35c5ca182465d2643db46c55f1e0d7972、master_data=e599184ff67bb93fcb332e39c555985a83a6c6f795096b432f0111b0d2d98a6b；这些是当前源，非动态成绩。

只读研究源集合摘要 SHA256=9ccdd54bb68ab3e94a46776f124007c09cf70b82d64422a03c6e1b93a73fe696。算法：以下路径排序，各取原文件bytes SHA256，以 path:sha256 加 LF 拼接并在末尾加LF后再SHA256。路径为 app/group_api.py、app/group_benefits_api.py、app/group_benefits_models.py、app/group_benefits_service.py、app/group_service.py、app/member_pricing_api.py、app/member_pricing_service.py、app/membership_api.py、app/membership_points.py、app/membership_service.py、app/recharge_bundle_api.py、app/recharge_bundle_models.py、app/recharge_bundle_service.py、app/repair_package_api.py、app/repair_package_service.py、app/retail_api.py、app/retail_group_api.py、app/retail_group_models.py、app/retail_group_rules.py、app/retail_group_service.py、app/retail_service.py、tests/browser_click/business_acceptance_catalog.json、tests/browser_click/master_data_business.py、tests/browser_click/material_business.py、tests/browser_click/membership_business.py、tests/browser_click/requirements_manifest.json、web/benefits.js、web/group.js、web/memberpricing.js、web/membership.js、web/rechargebundles.js、web/repairpackages.js、web/retail.js、web/retailgroup.js。未导入app、未读取真实库/.env、未执行浏览器；本页hash由交接另报，不自引用。
