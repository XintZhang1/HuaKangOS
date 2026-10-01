# 会员组合、消费券及真实消费六项候选

2026-10-01，test_inventory，当前 M8.1。精确授权为 PATCH-M8-4-BUSINESS-193-18，冻结研究页 `member-followon-scope.md` SHA256 `5a32b54a076ef5b80fe8e03c8cfcc94ba700af962e47aa35572231d6c0194f76`。本次只新增 `tests/browser_click/member_followon_business.py` 和本页；无生产、注册、runner、fixture、共享计划改动，无新岗位，没有导入 app、启动实例或运行浏览器。候选尚未注册、未执行，以下均是源码合同及将来执行断言，零新增通过成绩。

## 精确入口与完整 check

入口 `member-followon-hk123-124-125-129-130-132`，函数 `member_followon_business`，导出 `MEMBER_FOLLOWON_SCENARIOS=((SCENARIO, member_followon_business, 1200),)`。复用既有 Evidence/native 表单辅助函数，未增加执行框架或 HTTP/SQL 业务写入。六个 check 与原目录标题逐一静态核对：

| check | 原标题 | 将来必须实际发生的输入与结果 |
| --- | --- | --- |
| HK-123-business | 会员卡充值套餐设置 | admin 原配置发布默认未启用 V1、显式启用 V2，两份真实购买后追加每份6000分 V3；新申请仅当前版、原 V2 购买及四赠品不变。 |
| HK-124-business | 会员储值卡充值 | 同轮普通本金 partial 原件逐源核验；service 本人申请组合两份，finance 本人原任务及 receipt/account/reference 实收10000分，唯一本金/Cash/Purchase、四独立赠品 Wallet/Component/Entry 同事务一致。 |
| HK-125-business | 会员储值卡退款请求 | 同轮普通原款 partial 原件及本批组合支路共同闭合；真实消费后两份退款 POST409 全业务不变、明确放弃；一份独立批准占额→撤销完整释放→另申请/批准→财务原账户退5000分且原四赠品回收。 |
| HK-129-business | 消费券类型 | manager 原发布零价赠券、付费券 C500/P400/S400，发行后追加同编码 V2 C600/P450/S450；原钱包仍按 V1 面值、实款、结算、用途及到期消费。规则没有 enabled 字段。 |
| HK-130-business | 消费券生成 | service 原会员 benefit_issue/purchase 单两张付费券→finance 本人 execute 收800分，实际 Wallet/purchase Entry/Cash/非零内部双边与原发行绑定齐全；组合自动赠品不代替付费生成。 |
| HK-132-business | 消费券信息查询 | 五个非空真实读阶段覆盖组合发行、付费发行、实际精品核销、未用券退款占额、退款完成；原页面姓名、冻结规则、期限、可用/占用和 API/DB Entry/Reservation/Refund 一致，读取不写业务。 |

HK124/125 的普通前序只接受本次同轮 membership 已完整 passed 的场景与其中明确 partial 原件，不拼历史运行。自动赠品没有独立原 grant 订单，不提交 HK131；仅上列六项 check。最终 checkpoint 必须六项全部实际 passed 才设置 complete/passed，失败保留现场；先前尚未闭合的 running 项记 partial，未进入项保持 not_tested。人工简洁度、文案、193全业务验收仍 pending/false。

## 同轮有限前序及本人岗位

- `membership-hk117-128-118-089-094/business-checkpoint.json` 的 membership_sources：customer/member/active_card/account、原普通 topup10000分和 refund4000分的 Entry/Cash/原引用；HK124/125 partial 原证据必须对应同一 Entry。当前启用会员余额6000、占额0，无会期、无本批预置权益，卡与原普通本金旧行保留。
- `materials-hk069-045-054-083-070-072-073-051-061/business-checkpoint.json` 的 material_sources.primary：精确 Item/Enrollment/materials Warehouse/Location；重新核当前 source_location_id 属于 location_ids、本店启用、实际当前数量至少1000 milli，成本取当前原平均成本。上游快照不当当前余额，不扫描 demo Item。
- `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187/business-checkpoint.json` 的 HK175 已 passed evidence.row.id/code，原启用 WorkItem 只作为旧次数赠品作业编码，不假造施工。

三依赖均须当前 browser-click-report 注册且 passed、逐项 passed、检查点 complete/passed、目录 hash、五路径 provenance 一致；镜像 provenance 必须 snapshot_stable 且候选/八个复用或前序脚本/目录与当前镜像 bytes 指纹一致。数据库仍是该 evidence 同级 runtime 下外置合成库。

复用 business_fixtures.sales_order 的 sales_peer/service/manager/inventory/finance 真实门店1 UserStore，原本人客户归 sales_peer；现有随机 admin 只办 admin-only 组合配置与不同获权商品规则审批。正常登录在 Guard 基线前，登录审计不从全表保护排除。原任务如归 demo 员工，只由 manager 在原 generic Case 明确转交给已知随机岗位；等待真实 GET、h1、唯一按钮 visible/enabled，再原员工选择和三字段 AssignInput 提交。不同申请人与审批人、当前店、原本人 Task/CAS 保留。

## 实际操作与分账断言

1. manager 发布五个原 BenefitRule：赠金 C1/P0/S0、积分 C1/P0/S0、赠券和旧次数赠品 C500/P0/S0、付费券 C500/P400/S400；仅门店1/30天/履约店承担。赠品 refund none；付费券 unused_before_expiry。旧次数赠品冻结原作业码。
2. **发行前** manager 为 bonus/coupon/paid 各创建原商品用途申请，上传公司来源 evidence、实际勾选本轮原 Item goods、显式 accumulate_original_unit/original_expiry/none；提交后原任务转交不同随机 admin 独立批准并上传复核原件。Eligibility/Scope/Decision 与原 SKU/单位一致，发行同事务 Binding 引用原决定和新原 grant/purchase Entry。
3. admin 原组合配置 V1 默认 disabled、原购买按钮真实查目录且提示无启用组合、零 POST；V2明确 enabled，每份本金5000分加 bonus200/points100/coupon1/package1。service 明确条款购买两份、finance 原 receipt 实收10000分全部本金，会员16000，四赠品余额400/200/2/2。原 mandatory terms 与欠分补充条款保留。
4. service 原 membership benefit_issue/purchase 两张付费券→本人 finance 收800；随后 manager 追加付费券 V2，原两张钱包保持 V1 C/P/S。
5. sales_peer 原精品选择本人客户、本次 Item 1.000数量/25.00元/无安装、维修关联、会员价或手工优惠；原 lookup 通过可见 combobox 搜索和原 option 点击，底层隐藏 select 只读核值。等待客户关联维修 GET 和会员价加载完成。主管价格授权→本版客户 authorization→inventory 明确原 source_location 库位准备、实际 dispatch1000 milli→sales 本人 accept。Case/revision、平均成本、StockMove、WarehouseEntry/Balance 守恒；prepare 不算交接完成。
6. 原精品集团方案实际客户 authorization，明确本金1300分、赠金200分、赠券1张、付费券1张；仅冻结，无占用或扣款。finance 本人对四 Tender 各 reserve/capture 共八次实际点击，Case/Plan/Member/Wallet/Reservation 当前版本逐次核验。四原单位及原 goods 行 Allocation 分别严格 C/P/S、原来源；总 C2500/P1700/S1700、本店优惠800、集团优惠0/现金0。本金14700；四 Capture/原账/PaymentLink 齐全，只有本金和付费券非零内部双边，赠金/赠券不造零往来。零 RetailPayment/FlowPaymentLink/新增消费 Cash。
7. 剩1整份组合可退，原两份申请拒绝409且全业务不变、提交结束后原 ×→放弃填写；独立批准一份占5000本金+四赠品→原撤销完整释放、零现金→新一份申请/不同 manager 批准→finance 原账户 receipt/ref 退5000。四 adjust Entry 都引用各原 grant、四 RefundPosting 对应本批回收；本金9700，组合余额0/100/0/1、占额0、可退0，旧购买不可覆盖。发布V3只核当前申请选项，放弃不造第三次成交。
8. 原付费券尚未用1张，service 原请求→不同 manager 独立批准先占1张→finance 原本人退款任务、原 membership evidence、原购买账户退400分。负 Entry 引用旧 purchase；不退券面值500分、不回收已耗券、不延长期限。付费钱包归0。本批有限四 Cash 净10000+800−5000−400=5400分，本金9700及消费履约1700分别记，不当全店收入或中心实际支付。

原接口族为 /api/group/benefits、/api/recharge-bundles、/api/membership、/api/retail、/api/retail-group 和原 /api/warehouse/allocations；每写仅单次原 UI。新实体 helper 绑定唯一次 POST 响应 ID 对应实际原 GET，原 response listener/Future 同时覆盖渲染竞争并 finally 清理，不接受旧实体 GET、无重放或额外 HTTP。正式回执按实际 parsed defaults 核 digest（Selection/TenderAct 含原 None 默认）、result 与服务器响应一致；会员 execute 的宿主/权益两 FlowEvent/audit 各留原事实。

## 旧行保护、附件及输出合同

每个实际 write 使用全原业务 snapshot 和有限表逐旧行/列比较；禁止删除旧行或整个表豁免。有限新增计数逐动作声明，原当前 Member/Wallet 的 balance/reserved/version/updated_at、当前 Case/Task/Order/Refund 合法列、当前 Item 数量/价值/平均成本与有限 WarehouseBalance/Allocation 合法列才允许变。Case.data 正向只追加事实，已有键值不得覆盖。资格发行触碰本次 Eligibility Case version/updated_at 精确允许；当前零会期 retail authorize 合法新增本次 member_id/rule_id=null PointsClaim，不能当消费积分或阻止合法动作。旧卡、期间、欠分、其它会员、原现金与库存流水全保护。

合成 TXT 只写 Evidence 外部 synthetic-inputs，员工原选择上传并核真实原 DB bytes/size/SHA/security/structure_only；JSON 只附件 metadata、length/hash，不保存正文 bytes、密码/会话/hash或 credential，不使用 default=str/base64。structure_only 不能冒 ClamAV 或真实外部签字。原集团中心不实际支付。

仅六项 complete/passed 后输出相同 member_followon_sources/report_sources：

- customer_id/member_id/account_id/ordinary_membership_sources；benefit_rule_ids 与 wallet_ids 使用 bonus/points/coupon/package/paid 固定键；eligibility_case_ids/eligibility_ids/decision_ids 使用 bonus/coupon/paid；retail_binding_ids。
- bundle_rule_ids(V1/V2/V3)、bundle_purchase_id/bundle_case_id/bundle_component_ids/bundle_grant_entry_ids/bundle_topup_entry_id；bundle_refund_case_id/bundle_refund_id/bundle_refund_component_ids/bundle_refund_posting_ids/bundle_recovery_entry_ids/bundle_refund_entry_id；cancelled_bundle_refund_case_id。
- paid_next_rule_id/paid_coupon_case_id/paid_coupon_purchase_entry_id/paid_coupon_refund_id/paid_coupon_refund_entry_id；cash_ids四份、cash_net_cents5400/member_balance_cents9700；points_grant_entry_id/points_recovery_entry_id，points_consumption_or_points_change=false。
- primary_item_id/source_location_id、retail_case_id/retail_line_ids/retail_dispatch_ids/stock_move_ids/warehouse_entry_ids、retail_plan_id/tender_ids/retail_unit_ids/retail_allocation_ids/reservation_link_ids/principal_reservation_ids/benefit_reservation_ids/capture_ids/group_capture_entry_ids/benefit_capture_entry_ids/group_payment_link_ids/benefit_payment_link_ids/group_settlement_ids/benefit_settlement_ids。所有编号由本轮真实原结果得来，未执行时无输出可当成绩。

可供后继 HK168/169 精确引用，但没有消费赠分 PointsChange，也没有集团 clearing/bank 动作。积分兑换/调整/欠分、会员等级/会期/会员价、mixed PackageRule/Lot 购买核销退回、精品实退与 restore/原单位零头负债/到期/跨店/现金混合/安装/并发不足等保持 not_tested，不以余额查询代替这些结果。

## 静态交接与当前指纹

作者已人工核 source UI/API/model/回执：原字段与 Pydantic defaults、任务、两本金支路、三独立资格、四 Tender 与占额核销、原款/四赠品回收及旧行有限保护。轻量 AST 已通过，复用 helper 符号匹配；七处 DB 读取均 SELECT-only（其中三个限定白名单表/字段的 f-string）；六 check 精确目录绑定及空白检查通过。没有 app import、测试或浏览器运行；独立短审、root接线、原页面动态/render/文件选择/时间预算及所有原异常尚待实际复验，静态不算通过。

候选 code SHA256 `2c8777cff4246b549c88be55cd7a7a95532ecb20493a497ac10b65fcb142fdb2`，1418行。目录 SHA256 `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`，requirements_manifest `19840f4fc5fd816d94ea35a4602a31bde4674105e44621eeb4cfe42bdad27a1f`。前序 membership `f2897c762cbb9b0de213679afe47e86297a55fe7cdbeb986f20bd65ba0e649f8`、material `15d58e9ee4e2a555cca529f1bd8f87d35c5ca182465d2643db46c55f1e0d7972`、master `e599184ff67bb93fcb332e39c555985a83a6c6f795096b432f0111b0d2d98a6b`；finance helper `71152135cc82695572f57cd098096dfd4dd03cdae8212567b528c7a98c006763`。只为当前源码，不代表运行成绩。

本次只读源码集合摘要 `5f4feeee3383efc565389409f40b36e4d44fd96796170cc4b762f7733f895c6a`：各下列路径按字典顺序取 bytes SHA256，以 path:sha256+LF（末尾LF）拼接再SHA256。集合为 app/group_api.py、group_benefits_api.py、group_benefits_models.py、group_benefits_service.py、group_models.py、group_service.py、membership_api.py、membership_models.py、membership_points.py、membership_service.py、recharge_bundle_api.py、recharge_bundle_models.py、recharge_bundle_service.py、retail_api.py、retail_group_api.py、retail_group_models.py、retail_group_rules.py、retail_group_service.py、retail_models.py、retail_service.py、warehouse_api.py；tests/browser_click/business_acceptance_catalog.json、finance_business.py、master_data_business.py、material_business.py、membership_business.py、requirements_manifest.json、sales_business.py、sales_order_business.py、vehicle_purchase_business.py；web/benefits.js、livechoices.js、memberpricing.js、membership.js、rechargebundles.js、retail.js、retailgroup.js、warehouse.js。省略相邻文件前缀时均沿该组原目录；非本页自引用。最终文件hash由交接另报，之后作者冻结，仅由根协调新的写入窗口。
