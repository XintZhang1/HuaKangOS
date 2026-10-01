# 精品六项原生业务点击范围研究

2026-10-01；只读源合同研究。当前 HEAD `8993ca8c755194a42a48e7323fe355e80c6bf9ae`，M8.1 顺序内后继候选；只新增本文，车辆候选保持冻结。本研究没有启动服务、浏览器或验证进程，没有导入 app、修改业务、夹具、目录、注册或 runner。下列均为 `not_tested`、`manual_review=pending`、`business_accepted=false`、`full_193_business_acceptance=false`，不继承其他场景的成绩。

## 六项合同与顺序

原目录顺序为 HK052、058、062、064、074、082；建议实际办理顺序为 **074 → 052 → 058 → 062 → 064 → 082**，固定候选名 `boutique-purchase-retail-hk074-052-058-062-064-082`。每项分别保留原 check ID，不能以同一个采购或销售页面替六项通过。

| 原需求 / check ID | 本批完整主路径必须有的实际结果 |
| --- | --- |
| HK074 精品采购订货 / `HK-074-business` | 本批两件明确精品分类商品的原 PurchaseOrder 多行申请及另一主管批准；供应商、商品、数量、约定单价、冻结行与原任务/事件/回执逐项一致。申请与批准均未入库或付款。 |
| HK052 精品采购入库 / `HK-052-business` | 上述两行分两批原 receive，逐行实际库位准备、实际验收入库、原 Receipt/StockMove/应付与库存成本；两批实付分别留原款。准备库位不增加库存。 |
| HK058 精品采购入库退货 / `HK-058-business` | 指定第一批 A 的部分原 Receipt，原申请、独立批准占量、实际库位准备、实际发出及供应商原款退款；原批次数量、供应商冲款、库存均价成本与差额分别核对。 |
| HK062 精品销售单 / `HK-062-business` | 本店客户原 Retail 两商品明细，A 明确实际 WorkItem/安装费；另一主管报价批准、客户本版授权、库存出库、本人技师实际 install、客户 accept 和独立资金结算均闭合。仅建单或无安装不能满足本批合同。 |
| HK064 精品销售出库 / `HK-064-business` | 上述已批准并获客户授权原单整单 dispatch；两行冻结量、各实际源库位、当前库存成本、RetailDispatch/StockMove、预占释放与库位守恒一致。 |
| HK082 精品销售收款 / `HK-082-business` | 客户接收后，明确原券、本金与现金混合方案；财务分别 reserve/capture 原券和本金，再两笔原 receive 实收现金余额。RetailPayment/PaymentLink/Cash 各笔唯一，权益核销没有第二笔现金，累计实收及未收准确。缺少真实权益来源只记 partial，不将纯现金缩成此完整合同。 |

目录出处 `tests/browser_click/business_acceptance_catalog.json`；工作流源为 `docs/workflow-source/business.json` 的 `wf-material-purchase`、`wf-material-purchase-return`、`wf-retail-sale`。本批不要求这三个工作流中所有可选分支同时办理，六项各自必需动作以上表与目录 `ui_action` 为准。六类标准仍分别记录：显示符合预期、流程简单、文案简洁、后端匹配、无硬性 bug、来源完整；自动 UI/API/DB 断言通过不等于人工体验已评或业务已接受。

## 最小有限前序

同一稳定外部镜像中，只接受固定前序 checkpoint 的原来源 ID，并重读当前原 GET 和只读 DB；不按全表最新一行或名称猜来源，不拼不同 run 的成绩。

| 固定前序 | 精确可复用来源及当前重验 |
| --- | --- |
| `vehicle-purchase-hk171-177-178-026-021-018-029` | HK171 `evidence.supplier.id`；HK021 `evidence.payment.account_id`。Supplier/Account 本店启用、原 code/name 和账户经营主体合同合法；本批新建新采购，不重办其已完成采购。 |
| `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187` | HK175 `evidence.row.id/code` 的启用 WorkItem；HK181 `evidence.row.id`、HK182 `evidence.parent.row.id` 原父分类、HK184 `evidence.warehouse.row.id` 与 `evidence.location.row.id`。材料仓、库位及适用主档同店启用。旧物资数量不能从这个主档零库存快照继承。 |
| `member-followon-hk123-124-125-129-130-132` | `member_followon_sources` / `report_sources.customer_id/member_id/account_id`、当前会员本金及原账；其来源继续要求本轮 `membership-hk117-128-118-089-094`、物资、主档及销售各固定前序实际完成。当前源代码最终断言本金 9700 分、无占额，赠金/赠券/付费券余额为 0，积分 100、次数套餐 1；这些是候选输出合同，不是本文读取库后认定的实测现状，运行时须重验。 |

上述前序的传递最小场景清单是：`sales-presales-hk001-007`、`vehicle-purchase-hk171-177-178-026-021-018-029`、主档十五项、`sales-order-hk008-009-011-022`、物资九项、会员五项、会员后继六项，再本批。`sales-cancellation-hk010` 及其他保险/维修/报表不是本批数据前提；完整联合回归另按根清单执行。

沿现有真实岗位：admin 仅作第二名获权主管的独立商品规则复核，manager 原采购/报价/库位启用审批，inventory 实物，service 本店客户销售及客户确认，technician 实际安装，finance 实付、实退、实际收款及核销。fixture 现只有一名 manager；商品规则申请 manager → 不同 admin 批准是原 ROLES/Task 允许且管理员仍不能自批的明确复核路径，不能让 admin 代 inventory、technician 或 finance 办理。每次当前店/实际岗位由原登录和原 GET 重验，随机口令仅外置、全部脱敏。

## 本批新输入与最短真原 UI 链

建议合成输入只为便于精确对账，不预制交易结果：两件新商品 A/B，均单位“件”，明确新“精品”子分类；A 4 件 × 10 元、B 2 件 × 20 元，约定 80 元。复用本轮原启用品牌/材料仓/库位，通过 `#masters/material_categories` 新子类与 `#master/items` 新 Item，再 `#masters/item_profiles` 明确各 Item/category/brand/location/supplier 原 ID。原 `/api/masters/material_categories`、`/api/flow/master/items`、`/api/masters/item_profiles` 对应实际表单创建；物资没有单独 boutique 状态字段，不以普通物资旧单冒充，分类/名称/冻结计量均需实际可见。每件零库存 Item 经 `#warehouse` 原 `activate` 作业及 manager `approve` 启用真实库位；零量也须至少一个位置，`warehouse_enrollments` 与桥接为零，不能制造 StockMove 或现金。此为六项前置，不额外领取主档或启用验收成绩。

1. inventory 在 `#procurement` 点“申请多行采购”，实际选原 Supplier 与两新精品，提交上述两行/原因；manager 在当前原单点“批准采购”。POST `/api/procurement/orders`，新 `Case(kind=procurement,flow_version=3,state=approval)` 与 `procurement_orders/lines`；批准 `.../actions/approve` 后 receiving。原 `procurement_approve` 结束，生成本人 `procurement_receive`。不能依据 demo 默认负责人直接确认：如分给其他员工，主管原通用 `#case/{id}` 交接后重登实际经办人，核 current GET/原单 h1/唯一可见按钮。
2. 两批均 A2/B1；inventory 在原 receive 弹窗逐行填本次数量、实际库位与本单已检查原件。原 `/api/warehouse/allocations/{case_id}` `purpose=procurement_receipt` 每商品分别准备本批精确正量，获得当前 case version 后原 `.../actions/receive`。每批各两 `PurchaseReceipt` 与正量 `StockMove`、已 consumed allocation 和实际 `WarehouseEntry`，每批 40 元。finance 在原采购单实际 pay 40 元各一次，账户/凭证号/receipt 原件明确，每批付后相应应付为零；两批累计 80 元并到货关闭。这里不用预付款，预付独立申请/占额/抵用已属另批条件。
3. inventory 从第一批 A receipt 申请退 1 件；manager 原 return_approve 后才占可用量，原 `PurchaseReturn.version` 与 Case.version 均重读。inventory 在 `#warehouse-allocation/{purchase_id}` 为 A `purpose=procurement_return` 准备 -1000，回原单实际 return_dispatch；finance 原 refund 10 元明确第一笔 40 元 PurchasePayment 及其原账户。原 `PurchaseReturnPosting.receipt_id`、StockMove.original_id 指第一批采购入库 move；供应商 credit 1000 分、该时刻当前均价成本 1000 分，valuation 差额 0。原采购总验收 8000、实退 1000、净付款 7000、应付/应退均 0；剩 A3/B2。差额 0 只来自此明确单价和未混成本样例，代码应独立重算两种金额，不写死普遍相等。
4. 新券真实来源必须先于使用。manager 从 `#benefits/{customer_id}` 原“新增冻结规则版本”发布本店独立 coupon 版：每张 C=5 元、P=4 元、S=5 元、`discount_bearer=group`，明确有效期/原退款政策，非跨店；原 POST `/api/group/benefits/rules`。在 `#retail-group-rules` 申请其新商品用途，原 `POST /api/retail-group/rules`、`.../{id}/actions/submit` 明确本批 A 的 goods 原 ID/unit，三约定 `accumulate_original_unit/original_expiry/none` 逐项选；实际规则原件检查后提交，由另一获权主管按本人 Task 独立 approve。冻结 Eligibility/Scope/Decision 后才能发行。本例不把旧钱包后补授权、不修改原同编码旧版。
5. service 在 `#membership/{customer_id}` 新“购买券或套餐”办理 `purpose=benefit_issue`、`values={action:purchase,rule_id:新券版,units:1}`，POST `/api/membership/orders`；finance 本人 `membership_execute` 的原 `.../actions/execute`，本单 evidence/原账户/唯一凭证，实际到账 4 元。原 MembershipOrder/Event/Task、BenefitWallet/Entry(purchase)、CashEntry、BenefitSettlement 及 `retail_group_wallets` 的 issuance-time origin/decision 绑定一致。**不能用 Retail 本身作发行宿主**：`group_benefits_service._source` 只允许有效 lead/order/repair/membership，原已交付销售或已完成维修也不能冒充新发行宿主。不得直 SQL 调余额。
6. service 在 `#retail` 点“新建精品订单”，选本轮相同客户；A1 × 25 元，真实 HK175 WorkItem、安装单价明确填 5 元；B1 × 30 元，无安装。原 POST `/api/retail/orders` 冻结 6000 分、两行、revision1、installation_policy，`related_repair_id=null`；正 RetailReservation 分别 +1000，仅占可用库存、不动实际数量/成本。manager 原 approve 的最低价明确 60 元、无低价例外，service 上传客户 authorization 原件并用原 authorize revision1 确认。
7. inventory 原 `#warehouse-allocation/{retail_id}` 两商品准备 `purpose=retail_dispatch` 各 -1000；prepare 原 case version 推进，库存不变。回原 Retail 整单 dispatch：各一次负 StockMove/RetailDispatch/消费 allocation、负 RetailReservation 释放；本例库存成本 A1000/B2000 分，剩 A2/2000 分、B1/2000 分。technician 本人 `retail_install` Task 原 install：本单 evidence+明确实际结果，不改库量；service 本人 `retail_accept` 原 accept：本单实际接收 evidence，accepted_date 为业务当日。Retail 没有独立 quality 动作，本批不能虚构加装/维修质检替它；如完整需求后续需要相关业务质检，须其各自原流程另验。
8. 客户已实际接收、没有实际收款/预收抵用/原退后，service 从 Retail “核对集团付款资格”进入 `#retail-group/{id}`，原 authorize 明确新券 1 张、本金 5 元，剩现金 50 元由原行生成。券范围只选本批 A 商品，不用 points；plan 不占额或扣钱。finance 本人当前 `retail_group_payment` 分别 reserve 后 capture 券及本金，当前 case/plan/member/wallet/reservation versions 逐笔重读，先看原 GET 再一次 POST，不重放未知结果。finance 回 Retail 原 receive 两次 20 元、30 元；每次唯一账户流水/receipt，剩现金应收依次 30、0 元。最终 Case completed、本人 Task 无 open；Retail cash=5000、集团抵扣=1000、net_paid=charge=6000、应收/退款均0，券实款对价400分、本金对价500分、集团净履约对价900分、履约净对外对价5900分、内部结算总额1000分（本金500+券500）/集团优惠承担100分分列。发行券4元现金是原发行现金，不计为本 Retail 再收4元。

金额输入元精确换整数分，数量输入实数精确换整数千分之一。初始/每次库存、可用量、库位及成本从当前原源重算；这里的新 Item 隔离旧材料成本，但所有别的 Item/原流水仍全保护。日期按 fixture `Asia/Shanghai` 业务当日，不使用进程默认 UTC、不造历史时钟。

## 原 API、Task 与模型约束

- 采购：`app/procurement_api.py:15–45,60–81`、`procurement_service.py:115–140,174–199,234–359`。create `{request_id,supplier_id,reason,lines[{item_id,quantity_milli,unit_cost_cents}]}`；原动作 `{request_id,version,values}`；return review/dispatch 明确 `{return_id,return_version,...}`；receive 的 line_id、return_request 的 receipt_id 不可混。Task `procurement_approve/receive/pay/refund` 及带 return_id 的 review/dispatch 逐个身份/状态核对。Case.version、PurchaseReturn.version 冲突后停并保留原请求号。业务 Cash 与 PurchasePayment 原账户/原款上限均由原守卫检查。
- 仓位：`warehouse_api.py:91–96`、`warehouse_service.py:328–381`、`warehouse_stock.py:100–124`。allocation 原 POST 只准备与日志/回执；已有真实 Enrollment 的 Item 实际 posting 必须找到同 Case/Item/purpose/符号/精确量 prepared allocation，消费并生成 attributed WarehouseEntry。每次准备必须先刷新库存和 case version，新的准备可能取消同项未用旧 allocation；只准有限精确旧 ID 的 status 变更，其他旧准备全保护。库位分配数量填正，operation.quantity 入正出负；本批三用途为 procurement_receipt、procurement_return、retail_dispatch。
- 精品：`retail_api.py:14–48,81–93`、`retail_service.py:15–24,89–172,243–326`、`retail_models.py:9–54,94–106`。create 最多100行且同 Item 合并，原商品/安装价格整分和 qty milli；报价 revision1 与 snapshot immutable。approve manager、authorize/accept service、dispatch inventory、install technician、receive finance。原 `retail_approve/authorize/dispatch/install/accept/receive` 的本人 Task；create reservation、实际 dispatch、install、accept、cash 各自留事实。Task 被交给别员工必须先原交接，不能以管理员豁免办理。
- 混合资金：`retail_group_api.py:21–55,76–113`、`retail_group_service.py:101–157,169–208,291–340,445–492`、`retail_group_rules.py:29–162`。原 authorize 带 `{member_id,member_version,selections,evidence_id}`；reserve/capture 带 `plan_version/member_version/tender_id`、券 wallet_version、capture另 reservation_version；`.../actions/reassign` 只准两个明确财务 Task。新的现金不得超过被冻结原现金单元，Capture/GroupPaymentLink/BenefitPaymentLink 不是 CashEntry。新规则发布必须先独立商品适用批准再发新钱包，否则旧批无商品授权。
- 文件：必须原页面上传/检查/选择。采购 pay/refund 与 Retail receive 用 receipt，Retail authorize 和混合 authorize 用 authorization，其它实物/安装/原券宿主使用各原表单允许 evidence；`group._evidence` 允许 evidence/receipt，不能借 authorization。真实 FileAsset.case_id/store_id/上传人、可用检查、stored content 长度和 SHA 全核；附件 metadata 可入 checkpoint，BLOB 原字节只在内存 guard，不 JSON/default=str/base64 输出原件。

## 实际安装出处及后续可复用来源

本批安装的原事实是 **FlowEvent.action=`retail_install` + 原 RetailLine.work_item_id/work_code/安装核价 + RetailDispatch**。`service_analytics.py:80–113` 构建 `retail_installation` table/chart：取技师原事件的本地实际完工日期，先扣完工前真实原退，对应原安装 quantity/当时核价；后来退货不抹掉施工历史。当前 app/web/workflow-source 搜索没有注册 `repair_installation` 表或同名事实，不能造它替代；原维修项另 `repair_projects`，精品安装不等于维修配件耗用、库存价值或实收收入。本例可给后续 HK156 “期间精品实际安装”提供非空原源，但本批不登记报表或 HK156 通过。

建议 checkpoint 只新增有限 `boutique_sources`/`report_sources`：store_id/customer_id/member_id/account_id；supplier_id/category_id/brand_id、两个 item_id/profile_id、warehouse/location/enrollment IDs；purchase_case_id/line_ids、四 receipt_id、相应 StockMove/allocation/entry IDs、两 purchase payment/cash IDs、return_request/return_line/posting/valuation/original_payment/refund_cash IDs；WorkItem id/code；Retail case/两 line/dispatch/move/reservation/installation_event/accept_event IDs；规则原 BenefitRule id/version、retail eligibility Case/Eligibility/Scope/Decision ID、新 MembershipOrder/issued wallet/origin/issuance_cash/binding IDs；混合 plan/tender/unit/allocation/reservation/capture IDs、原 GroupEntry/BenefitEntry/PaymentLink/Settlement IDs、两 RetailPayment/PaymentLink/Cash IDs。所有 IDs 来自原响应或有限同 Case 只读 SELECT，并重验 UI 当前版本/金额，不把全表 dump 当新来源。

## 旧行保护、异常与未测边界

所有正向均真实页面操作；API 仅观察原网络/响应，DB 仅 SELECT。每次合法登录完成后才做业务 baseline，保留原 login 审计，不能粗略忽略 audit_logs。旧全表摘要与旧 BLOB 内存比较，合法写仅允许本批新 Case/Task/凭据/回执/事件/审计及明确原 ID 的有限列。原供应商、主档、原销售/维修/会员卡/期会、其它客户、旧所有现金与库存/权益流水不得覆写；其它店全保护。

采购/销售有限 Case 只许原状态、data、updated/version、结案日期、实际cost等动作实际修改列；Item 只有两新 Item 的 quantity/value/unit_cost/updated/version（return批准与 reservation也会touch updated/version）；精确本批库位 Balance 的 qty/value/version，精确 allocation consumed/cancelled/status/stock_move；新 PurchaseReturn 状态/approve/version；原本人 Task 精确承接/结案字段。所选原资金 Account 只准原现金方法实际 touch 的 updated/version，不改主档或凭空余额。所选 GroupMember 只准余额/占额/updated/version，新券钱包余额/占额/updated/version，明确 plan updated/version 与新reservation状态；既有原本金 GroupEntry 等 append-only 不改。Retail authorize 的 PointsClaim 及 member touch 来源为 `membership_points.freeze_points_rule`；现同轮无会员期会/points规则则 rule_id=null、无消费奖积分，不把充值赠送积分当消费积分；若前序已改变需重核条件而非宽放全部权益表。invoice同步只维护当前原单适用任务，未申请发票不得造票事实。通用任务交接原 `/api/flow/tasks/{id}/assign` 仅 `{version,assignee_id,reason}`，没有 request_id；仅此原封包适配例外，其他业务封包仍强制原 request_id 与回执。

每项必需源完整检查：原 UI/native Cookie/CSRF/current store、原 request_id/当前 version、精确 actor、最终重读一次的 UI/API/DB 与附属流水一致；无未知结果重放、不因超时再换 request_id。负向如没有真实服务器 refusal，一律不猜类型/消息；规则拒绝原单与原资金保持，只允许原 middleware 精确新增 refusal，不能全表豁免。

未覆盖的建议/条件分支均明确 `not_tested`：采购预付/失效/终止余量/取消和已批准未发退货撤销、不同成本混批非零差额、缺货/超额/重复提交/并发 CAS、跨店调拨、会员券过期/原退凑整恢复/现金退款、积分兑换、真实病毒扫描与PG/Linux/员工人工试用。HK063/066 另需同客户 related_repair_id，HK065 原加装出库、HK067 精品客户退货/整改/复检/保留安装费、HK068 真 RetailBundleRule 均不计本批。没有现成新券商品授权前序，不能用现钱包余额和纯现金提前宣布 HK082 完整。

当前源码未发现这条主路径缺少原路由或所需字段；静态可见安装与混合支付入口都存在。真实 lookup/折叠/任务默认经办、一次现金按钮与上传观察，以及六类体验标准仍待新外部实例验证，本文不声称真实 UI 无缺陷。源指纹：原 inventory scope `35bc5eaa05359f0c3cf54344a0e6a7802e63e78ac9de388afe4dcaf341496c8e`；193 catalog `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`；procurement_service `135aac829c470716aa4df150bd102b4781ff8738247982f3c7544a3080ac49e8`；retail_service `47fda5feeb540d9da941398787eb7bfdf3d956649e8f83c4956d86f271882296`；retail_group_service `bd868ef35b97aa4eab91c1f3821156b844d2e2d5b3af9e596f96d5b446e3e264`；retail_group_rules `116e2549977fee567fd80e4fad0629b70e68f10cc485ea9c2e7279c3e2bd32e9`；service_analytics `7dd628a5ebd4901a9a8d3de10b65deb16b25438e740a3cc59b06899a63b7de16`。
