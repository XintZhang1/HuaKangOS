# 精品维修附带销售、原退货与套餐后继范围

2026-10-01，只读源码研究；HEAD `8993ca8c755194a42a48e7323fe355e80c6bf9ae`。仅本文件新增，未编辑生产、已有脚本、夹具、目录、runner、注册表或计划，未导入 app、启动实例、运行浏览器或测试。本文没有新执行结果，全部建议 check 仍 `not_tested`，人工六类标准 `pending`、`business_accepted=false`、193 全量接受为 false。精品父脚本正在由 root 修复原汇总字段并复验；此前局部业务事实不能充当完整 passed 父报告。

## 1. 原标题与建议完整范围

| 原 ID / 固定 check | 原标题 | 本批独立通过所需原事实 |
| --- | --- | --- |
| HK-063 / HK-063-business | 维修精品销售单 | 新 Retail v2 单明确关联同客户原维修，独立冻结商品/安装报价、主管核价、本版客户授权、实物出库、技师安装、客户接收及纯现金实收；与原维修材料和款项分别核对。 |
| HK-066 / HK-066-business | 维修精品销售出库 | 上述新 Retail 的每行 RetailDispatch、负 StockMove、原库位准备消费、WarehouseEntry 与实际商品数量和当时原成本相符；原 repair_issue_v3 不能替代本项。 |
| HK-067 / HK-067-business | 精品销售退货 | 从该新单真实 dispatch 申请部分数量，另一主管批准、实际可售验收后恢复原数量/原成本，安装保留费分列，再按本单原入款/原账户真实退款；未验收不增库存或退款额度。 |
| HK-068 / HK-068-business | 精品销售套餐设置 | 新 RetailBundleRule 冻结商品、安装、每套参考金额/分摊、期间和条款并明确启用；按真实套数生成另一张 Retail v2，完成原核价/授权/出库/安装/接收/收款，逐组件和整数分守恒。 |

建议一个原生点击入口 `retail-repair-return-bundle-hk063-066-067-068`，完整需求仅以上四项，建议三元组超时 1200 秒。HK-063 与 HK-066 共用同一真实新单，但分别记录“完整办理”和“独立库存出库”证据，不能以一个总状态冒充二项。HK-067 原退货另有实际结果，HK-068 必须新规则和新套餐单，不复用旧精品单来冒认。

原源：`tests/browser_click/business_acceptance_catalog.json` 对应四项；`docs/workflow-source/business.json` 的 `wf-retail-sale`、`wf-retail-return`、`wf-retail-bundle`。发布规则不等于卖出套餐，出库不等于客户接收，现金不等于安装完成。

## 2. 最短同轮父闭包与有限 ID

直接父为 `boutique-purchase-retail-hk074-052-058-062-064-082` 和 `repair-selfpay-hk031-034-044-049-053-079`，两者须同轮完整场景 passed、所有必需原 check passed，证据和源码/脚本/目录指纹匹配当前镜像。最短完整闭包为售前、采购、主档、物资、客户、首维修、整车销售、会员卡、本金券组合后继、精品六项十场景。使用既有 fixed_dependency / Evidence 原合同；不能扫历史目录或继承另一运行结果。

- 精品 `report_sources`（`boutique_business.py:1051` 起）：只取 `store_id`、`item_ids` 两项、`profile_ids`、`warehouse_id`、`location_id`、`enrollment_ids`、`work_item_id/work_code`、`account_id`，保留该父 `purchase_case_id`、采购行/收货/原退/StockMove/WarehouseEntry、原 RetailGroup 单及款的有限 IDs 用作旧行保护。二项分别是真采购成本每单位 1000 / 2000 分的合成精品；父终态预期 A 数量 2000、价值 2000，B 数量 1000、价值 2000，但本批必须重读当前库存/可用量和库位，不把原终态数字当当前可用事实。
- 首维修 `report_sources`（`repair_business.py:954` 起）：`customer_id/customer_vehicle_id/vin/repair_case_id`，以及 `quote_id/allocation_id/payment_link_id/cash_id/material_item_id`。本批优先用该自费客户：原父建立了明确客户/车辆、无集团会员来源；提交前仍核对当前本店身份关系，不猜后续没有新增会员。原维修已 completed/released 允许关联（`retail_service.create:120–123` 只要求可读、kind=repair、同客户；无未完成状态要求）。本批不制造新维修事实或重开维修。
- 当前岗位使用既有 service、manager、inventory、technician、finance；service 可办理该本店原客户，sales 另有客户 owner 守卫，不借 admin 代办。Task 实际经办人必须是本次本人；必要交接沿原主管 UI 的 `/api/flow/tasks/{id}/assign`，封包仅 `version/assignee_id/reason`，没有 request_id。
- 精确新来源输出建议：两 Retail Case/Line/Dispatch IDs，原 repair ID，A 的 Return/ReturnLine/Posting/退库 Allocation/Entry/StockMove IDs，A 入款/原退款 PaymentLink/Cash/RetailPayment IDs，Bundle Rule/Component/Receipt/Sale/Allocation IDs、版号/套数及 B 入款 IDs；并保留原账户、商品/库位、授权/实物/现金附件元信息。原 bytes 只在内存做大小/SHA 对比，不放 JSON，不转换成字符串或 base64。

如当前可用库存低于明确方案、原库位/主档已停用、父非完整 passed、源指纹变化或相关会员/经营主体合同已改变，停止并报告准确前置；不把后台已完成采购变成新出库，不手工造余额/成本，也不盲换商品或身份。

## 3. 原 UI / API 与两张新单的最小输入

### A：维修附带销售、出库与部分原退

1. service 原 `#retail` →“新建精品订单”，明确选择首维修客户。原表单会 GET `/api/flow/cases?kind=repair&customer_id=<id>` 动态列同客户维修（`web/retail.js:41–54`）；须等真实候选并明确选择原 repair ID。新建 A：精品 A 数量 1.000，商品单价 20.00 元，原 WorkItem 安装单价 5.00 元，优惠 0，无会员价格/集团混合付款。POST `/api/retail/orders` 正整数 `quantity_milli=1000/unit_price_cents=2000/installation_unit_price_cents=500`，`related_repair_id` 真实绑定。冻结 goods=2000、installation=500、Case amount=2500，RetailReservation +1000；此时不造 StockMove、安装或 Cash。
2. manager 原“主管价格授权”，独立于开单人；service“记录客户报价确认”，原 revision=1、authorization 类本单可用文件。GET `/api/retail/orders/{id}` 和 `/api/flow/cases/{id}` 核当前版本/Task 后各原 POST `/api/retail/orders/{id}/actions/{approve|authorize}`，封包 `{request_id,version,values}`。价格最低金额/例外/原因按原表单，不把同 admin 自批路径当独立核价。
3. inventory 本单“准备物资库位” → `#warehouse-allocation/{id}`，GET/POST `/api/warehouse/allocations/{id}`，明确 `purpose=retail_dispatch, quantity_milli=-1000` 与原实际 location 一致；原准备只追加 Allocation/Line、事件/回执并 touch Case，库存和 Cash 不变。随后回 A 原页面“确认整单实际出库”，当前 CAS/本人 retail_dispatch Task，evidence 类本单凭据；真正产生 RetailDispatch/StockMove(-1000, 当时原均价成本)、消耗准备并追加 WarehouseEntry。库存价值按真实当前全店均价，不按售价或其他 repair 领料成本。
4. technician“确认实际安装”记录真实合成安装结果；service“确认客户接收”；finance“登记实际收款”2500 分，明确既有本店原账户和唯一 reference、receipt 类本单凭据。每步 Task 本人、原事件 actor/store/case、一次 FlowReceipt 和实际返回一致。`data.installed` / `accepted_date`、净实收与 receivable=0 分别核实，原维修 Cash/RepairStock/Quote/Allocation/车辆身份全保留。
5. service“申请原单部分退货”：从本 A 的真实 dispatch 选 0.500，evidence+reason；POST action=return_request，`lines[{dispatch_id,quantity_milli:500}]`。manager 另一人“批准退货”：当前 Case version + Return version，精确 `return_id/return_version/reason`；冻结 retain_installation=true。未实际验收阶段，库存、退款余额及安装保留费不得提前变化。
6. inventory 实际“检查退货可售性”，通过的 `passed=true`、结果/evidence；须在原退库前准备 A 的 `retail_return=+500` 本店真实位置。通过后 RetailReturnPosting 指向原 dispatch 和原 return line、正 StockMove.original_id 指原负 StockMove，恢复数量500和原成本剩余份额；商品减免1000，安装分摊250且保留250，Case charge=1500、净入款2500、应退1000。不把分摊保留250误作再次收入或 Cash。
7. finance“登记原款实际退款”1000 分，选 A 唯一原 PaymentLink、原账户和独立新 reference/receipt。原退款方向 out、`original_id=<A in payment>`；现金1000与商品减免对应，退款后 net_paid=charge=1500、due/refund=0、原 Task 闭合且刷新不追加重复事实。

HK-067 可在正式作者补丁中选取“首次检查不合格 → technician return_rectify → inventory 复检合格”作为该主退货的真实路径，检查不合格时须保持原库存/Cash/Posting/可退余额，不能把不合格直接视为实际退库。若选直接合格路径，整改/拒收/实物交回仍明确未测。建议至少一次原 UI 超过真实应退余额或原款剩余的拒绝，明确原 409/中文提示并核旧业务全行不变；不得放宽到权益退现金。该主单没有 RetailGroupPlan、advance_credit、Group/BenefitPaymentLink，因此纯现金选择是新单事前明确的实际付款方案，原 boutique 混合付款全部旧行仍严格保护；权益原路恢复分支尚未测，不冒称本批覆盖。

### B：发布新套餐与两套完整履约

1. manager 原 `#retail-bundles` →“配置套餐规则”→ `#retail-bundle-rules` →“发布新套餐”（`web/retailbundles.js:30–38`）。新随机代码、base_version=0，日期按 fixture Asia/Shanghai 业务日、明确补充退货条款，默认 enabled=false 须员工明确勾启用。组件：A 每套0.500、商品整组件参考10.00、安装参考3.00并选择原 WorkItem；B 每套0.500、商品参考20.00、无安装；每套成交30.00。原 POST `/api/retail-bundles/rules` 的组件参考金额是整套组件金额，不能误填单价。
2. 该接口只有本店 manager/admin 发布权限，没有独立“批准规则”动作（`retail_bundle_service.py:57–96`）；新增一条 RetailBundleReceipt（原request_id/actor/digest/rule），不能同时强计 FlowReceipt。组件按稳定顺序/最大余分冻结每套 goods_A=909、install_A=273、goods_B=1818，合计3000。旧 Rule/Component 不覆写；发布下一版是追加规则，不改旧售单。
3. service“核对客户与套数”选择同 A 客户、2 套，真实 GET `/api/retail-bundles/rules/{rule_id}/preview?sets=2` 核当前原版/当前 available_sets，展示分摊后明确勾选条款。POST `/api/retail-bundles/sales` 为 `{request_id,rule_id,rule_version,sets:2,customer_id,terms_accepted:true}`，无默认会员报价；实际 creates 新 Retail v2、Sale、Allocation和 FlowReceipt。B 各商品总数量1000，goods_A=1818、install_A=546、goods_B=3636、Case amount=6000；行冻结 unit_price_cents=0 不用于重算实际单价，退款使用原分摊。
4. B 沿相同原主管核价/客户 authorization → 双商品原 `retail_dispatch` 库位准备、inventory 真出库 → technician 实际安装 → service 客户接收 → finance 原账户现金6000的完整步骤。不能用 rule publication、Sale 创建、预占或每套售价当履约/实收。原生成 `retail_quote` 与本版分摊/模板快照可检查；生成件不等于签字，客户授权仍由员工原页面明确上传/引用本版 authorization 凭据。

重要 UI 边界：原 Bundle Sale 表单 `web/retailbundles.js:18–27` 没有关联维修选择，虽 API `Sale.related_repair_id` 支持，原 UI 当前不会发送。上述独立 A 用普通 Retail 真实候选选择，B 无 repair 关联，不扩生产也不直接补 body 冒充点击，因此 HK-063 不靠 B 来算。四项上述路径尚未发现明确阻断性生产字段缺口；动态 lookup、附件、渲染时序及 SQLite 并发仍须新鲜实际点击证明。

## 4. 状态、回执、成本与旧行保护

原普通 Retail 状态为 approval → authorization → pending → working → completed/settling；`_sync` 由真实 accepted_date、金额和 active return 算 state，不手写。Return requested → approved → accepted；异常可进入 rectification/reinspection/handback/rejected。`retail_service.py:174–326` 每步控制当前原 Case version，退货另 Return version；`_task:142–144` 要本人原任务，manager/admin 角色例外不能代替原独立岗位流程。

- 每登录及首次改密合法完成后才建立业务快照；原 login Audit/Session 不粗排除审计。读页面/查看原单/刷新只读，除了明确生成/上传业务动作，不允许业务表变化。提交只一次，未知结果停止保留原件，不忽略 response body，不自动重放。
- FlowRequestReceipt 原 digest：create 使用 retail_create，Bundle Sale 使用 retail_bundle_create，普通 commands 使用 retail_<action>，库位 prepare 用原 warehouse_allocation；以实际函数 request_digest 字节核对，禁止凭动作名称猜 family。Rule publish 只 RetailBundleReceipt。所有回执核本人/本店/原request/实际result和CAS。
- 对新 Case/Task/Return 仅放本次 action 的实际必要列；Task handoff 是精确同 Task 的版本/经办/原因。对当前两个 Item 仅准许原预占/实际 StockMove 的必要库存、价值、均价、version/updated_at；对目标 Item 的有限现有 WarehouseBalance 允许原 rebalance 的数量/价值/version/updated_at，含原门店均价零数量重估分录，其他店/其他 Item 不放宽。
- Allocation 从 prepared 到 consumed 必须绑定该 StockMove；return 不覆盖原 Dispatch/Line/Reservation/Posting，`_portion` 按原剩余数量/价值分摊，最后一次收尽余分。库存准备不得改变 quantity/value、无 StockMove/Cash；可售成功才正库存与减应收。若无外部写，本例最终 A quantity=500、B quantity=0；只作为本例整体收发守恒目标，实际 value 基于提交前原账计算，不借历史成本兜底。
- 原首维修整 Case/Task/Quote/Line/Approval/Authorization/RepairStock/Allocation/Payment/Cash/CV/Resource 全旧行不变；原 boutique 采购/原供方退款/旧 RetailGroup Plan/Tender/Unit/Allocation/Capture/Group/Benefit/本金/权益/Cash 旧行不变。新增关联只在新 RetailOrder.related_repair_id；不得把关联阅读变成原 repair 写入。
- Cash 每笔唯一实际正向收/退：正确本店账户、金额/方向/approved/支付方式/日期/reference/actor 与 PaymentLink、RetailPayment、原证据关联一致；`flow_engine.add_payment:560–586` 强制原款未退限额和原账户，Retail 先强制当前refund_due上限。无新 Group/Benefit/advance/invoice/PointsChange 等独立来源则不得允许其变化；如当前客户真的新增会员或其它原合同，必须明确新前置和精确原守卫，不能宽放所有表。
- 附件原流只保本单、本人可用类别；metadata/大小/SHA 比对原 file bytes，JSON 不含 BLOB。authorization 用 authorization，收/退款用 receipt，实物/退货实际凭据用 evidence（`web/retail.js:70–72` 与 backend `_evidence` 相符）。生成字节/模板版/分摊快照独立保留，不称普通上传为签回/扫描验收全部完成。

## 5. 为后继 HK-086 留真实新纯 Cash 来源，本批不办更正

建议在 A 收2500分前事前声明这是一条合成“款确已到、reference 误录”样例：金额、原账户、实际业务日和凭据真实合成事实一致；原正确流水 `RT-IN-CORRECT-<token>`，原 UI 本次故意误录为唯一 `RT-IN-MISRECORDED-<token>`。记录操作前样例声明、实际 typed reference 和独立凭据说明，错误标签是未更正事实，不能用后验改 DB、改日志或伪称当前 reference 正确。四业务动作自动断言证明输入/原状态/库存/金额相符，不能据此宣称所有源记录已正确或人工已接受。

按上述真实原退1000后，该来源仍 `CashEntry.category=workflow_retail/direction=in/approved/amount=2500`，PaymentLink in 指新 A；原真实 refund out=1000 指该原付款，净剩余1500。输出 `customer_id,case_id,original_cash_id,original_payment_id,refund_cash_id,refund_payment_id,original_account_id,business_date,entered_reference,correct_reference,gross_cents=2500,refunded_cents=1000,remaining_cents=1500`，连原文件元信息/sha。B 用完全正确新 reference；原 boutique Group 现金不能拿来替代。

`business_finance_service.receipt_sources:130–152` 可读取上述原款及已退款净切片；`_correction_origin:413–436` 接受有业务 PaymentLink 的 workflow_retail 原实收，之后更正需明确 `allocation_basis=remaining_after_refunds`、正确总原款2500及新 A 剩余 allocation1500（`create:274–280`、partial_corrections.freeze/guard）。Retail无混合方案/无在办退货是明确前置，来源不能属于其它客户。后继 HK-086 应在另一登记补丁中由 finance 申请、另一 manager 批准、finance 执行；保留原退款、不产生第二次收入/实物。本批只输出此候选来源，不创建 Correction、更正现金或记 HK-086 passed。

## 6. HK-071 评估：另批条件，当前四项不计第五项

原标题 **机构库存查询** / `HK-071-business`，原合同是“实际切另一授权店读取非空库存/位置/在途只本店，未授权不可读，汇总只读不是本店可用量”。GET `/api/warehouse/items?q&page&page_size`、`/api/warehouse/items/{id}/stock` 用 warehouse.authority READ=admin/manager/inventory/finance/auditor 和真实当前店 role；详细 balances 含 location/transit_case_id/数量，entries 原来源可钻取，金额仅管理/finance/auditor。`stock_view:142–155` 只展示 **店内移库在途**；跨店调拨待验收/拒收/返运在 `/api/transfers/{id}` 原 lines/movements，不能把跨店原在途自动算成本店可用或叫 WarehouseBalance 店内在途。

现 fixture 普通 manager/inventory/finance 仅一店，sales 虽两店但 warehouse READ 无 sales；interstore 新的三员工仅二店、账号默认sales/当前店岗位明确、无集团汇总（`fixture_server.py:89–116`、`interstore_business.py:345–363`）。因此不能拿账号默认岗位或一个店的权限推断其能切两店。可读 admin 查询两店并非业务代办，但作为员工授权准入的完整演示，建议另登记一名随机新只读用途员工，由 admin 原账号 UI 明确两个店的管理岗位及 can_group_summary、本人首改密真实登录；不修改已有账号、无 fixture/SQL 授权，秘密仅外部/runtime 全份 Evidence.scrub。

若同轮 **完整 passed** `interstore-original-hk020-024-047-055-084`，其有限 report_sources 提供 `source_item_id/destination_item_id/source_store_id/destination_store_id/destination_material_location_id/material_transfer_id/material_accept_movement_ids`；二店750实收数量/本地库位来自500+250实际验收，250原拒返保留，须重读当前值/成本。原链终局全部在途已经归零，零余额/非空历史发运不能冒称已核验非零当前在途。只切两店核这些真实库存、库位和在途0，是 HK071 局部证据，不提交完整 HK071-business。

如要一次完整 HK071，建议另登记新原二店 `local_move` 小数量(例如100)与第二真实库位：二店 inventory 原 UI 新库位/新作业，二店 manager 独立批准，inventory 实际 dispatch，在明确 transit 阶段授权员工原顶部 `#store` 切一店→二店，真实重读 `/api/auth/me` / stores / catalog 和原warehouse页面，核非零本地 transit Balance、原 Entry、book/available/reserved守恒；随后二店本人原 accept100闭合，原在途0、库存总量不变、无现金。此为真实前置原实物动作，不能用SQL造在途/改时钟；需要另补丁授权，当前范围不新增作业。

未授权阴性可用原一店 inventory：店选择器没有二店，原已知 destination Item 深链在一店读取404、本店其它库存可读；若要额外验证 X-Store-ID=2 的 tenancy403，须另说明合法的真实 browser 请求观察方式，不能注入隐藏 fetch/Cookie桥来冒原 UI。汇总选择 all 原 warehouse.catalog.can_read=false、UI“请切换到获权门店”；single_store拒绝明细读取，汇总写 middleware409。真实跨店库存/收发汇总从原统计同范围图/表/CSV核对，不把集团汇总量当某店可用量。当前scope仅源合同评估，以上权限/数据/UI阴性全部未执行，不新增完整check或继承其它权限场景成绩。

## 7. 待实测和边界

四项所有自动结果与六类人工标准均待原生浏览器执行。建议新三宽度检查原候选选择、套餐两次确认、退货可售状态/安装保留费及简洁提示；旧录入或折叠时序缺陷不因源码存在算通过。套餐下一版停售/旧售单冻结及套餐组件原退、多次最后余分、欠款先退、混合本金/券/权益退款、退货整改/拒收交回（未选入主退货时）、版本冲突/重入幂等均按实际执行与条件分开记录。HK071、HK086不属于本批四完整check。PostgreSQL、真实银行/实物/扫描环境、模型/员工试用及193全目标仍原门槛，本文不冒实测或生产可用。
