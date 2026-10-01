# 物资采购、库位、盘点与调拨的最小原业务链研究

2026-10-01 根接线与实际运行追加：九项已在`V/browser-click/business-material-system-20261001-01/evidence/`同次完整本场景通过，530动作/239点击、页面异常0；该次系统场景因凭据目录装置误判失败，因此整个选定4场景仍failed，不能写全套通过。根按原UI展开“首次启用库位”，activate只填写实际location；只读基线放在原登录审计完成之后，保留整张audit及其旧行；库存、现金及异常判据未放宽。前期01隐藏按钮、02不存在destination、03合法login审计及一次无效选定名称的失败原件全部保留。当前脚本已注册，automatic-business06为新指纹完整23场景联合运行，尚无联合结果。本段取代下文候选历史的“未注册/未执行”，不改变真实环境、人工体验及跨店待测边界。

2026-10-01，负责人授权的只读研究记录。负责人 test_inventory；只维护本页，其余源文件只读。当前没有物资候选脚本、注册或执行成绩；后续编码须负责人登记精确补丁和写入窗口。本页不修改生产、fixture、已有场景、共享目录或实施计划，不启动实例、不导入 app，不读取真实环境或数据库。

## 建议逐项范围

先做同店完整链，再做依赖该库存的跨店链；每项保留独立原 UI/API/SELECT-only DB 证据，不把共用工作流的一次跳转算成多项业务通过。

| 建议段 | 精确需求与原业务核对 |
| --- | --- |
| 同店采购、结算、退货 | HK-069 物资采购订货：真实多行约定、独立采购批准、预付款申请/独立批准/实际支付；HK-045 物资采购入库：两批真实验收、已启用库位分配、预付抵用及尾款；HK-054 物资采购入库退货：原验收批次部分退货、独立批准、实物发出；HK-083 采购入库退货收款：财务实际退款入原付款账户、引用明确原付款。 |
| 同店库存、移库、盘点 | HK-070 物资库存查询：本轮非空物资的账面/可用/预占/在途及位置账；HK-072 物资店内移库：批准、移出在途、分批实际接收，门店总量与价值不增加；HK-073 物资库存盘点：正差、负差、零差三次独立观察/批准，保留期间收发；HK-051 物资盘盈入库查询与 HK-061 盘亏出库查询：分别查询本轮已经真实过账的正、负差来源。 |
| 紧邻跨店段 | HK-055 物资调拨出库：双方批准后原出店实物发出；HK-047 物资调拨入库：目的店分批合格接收与拒收、原拒收发运退回、源店实际质量合格接回；HK-071 机构库存查询：已授权读取身份在原 UI 切店核对两店非空来源，另保留未获另一店权限员工的原读取拒绝。 |

首段9项，跨店段3项；它们尚未执行。HK-052/058/074 必须另有明确精品商品的原采购/退回，不能由当前材料 Item 代替。HK-046/057 其他入库/原退、HK-056/048 耗材领出/原退、HK-059/050 礼品发出/原退、HK-060 其他处置均需各自原因、领取人、原作业及原收发；可在真实库存后另登记增量，当前不计入。HK-049/053 须维修原单领退料；HK-062/063/064/066/067/068 须真实精品销售/原退/套餐；HK-065 须真实销售加装，均不能由采购结果充当。人工流程简洁度、文案审阅和完整193业务验收继续 pending/false。

## 同次原点击前序与最小前置

只读取当前 `manifest.evidence_root` 下对应完整通过的 checkpoint 与同次稳定 provenance；核源脚本/目录指纹、scope、check_id、实际身份/门店、原响应/DB关联。不得读取旧 fresh 的 ID、继承 demo 库存、挑全库最新记录或猜内部编号。

| 前序来源 | 精确取值与当前事实 |
| --- | --- |
| `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187` 的 `business-checkpoint.json` | HK-183 `acceptance_checks[0].evidence.item` 是原 UI 新增并调整补货阈值的 Item，单位“升”、初始 quantity/value 为0；`evidence.profile` 有真实 item/category/location/brand FK，supplier_id=null。HK-181/182 同 shared item/profile 可交叉核，不能把字典名称当真实 Item ID。 |
| 同一主档 checkpoint 的 HK-184 | `evidence.warehouse.row`、`evidence.location.row` 是材料仓和真实库位，active=true；location.warehouse_id 与材料仓一致。仅主档引用，尚未 WarehouseEnrollment，不能直接声称已定位或有库存。 |
| `vehicle-purchase-hk171-177-178-026-021-018-029` 的 HK-171 | `acceptance_checks[0].evidence.supplier` 是本轮原 typed Supplier 新增/编辑结果，含真实 id/name/code/payment_terms_days；可复用，不使用夹具为旧空表单建立的供应商或 demo 名称。 |
| 已有外部合成账号 | 本店1 inventory、manager、finance 已可登录，分别真实 UserStore 岗位。已有本店 active 合成 Account 可以沿原资金 lookup 选择，仍须核本次账户/主体守卫，不把演示账户视作公司正式账户。 |

同店段无需新增夹具身份。第二采购物资由 inventory 在 `#master/items` 原 UI 新增为明确材料、零库存；材料第二库位由原 typed 主档 UI 建立在本轮材料仓下。若需要 ItemProfile，同样原 UI 关联本轮分类/品牌/真实位置，不由 fixture 写行。所有 Item 必须先真实启用：`#warehouse` 点 `wh-new[data-operation=activate]`，填当前已对平数量（新 Item 为0）、至少一个原位置分配0、原因/期限；原 POST create 后本单上传实际依据，manager 原 approve 才产生 Enrollment/Balances。启用本身不得产生 StockMove/CashEntry。

跨店段尚缺可登录的 store2 manager/inventory 本人。建议后续精确 fixture 补丁只增加两个随机身份及对应 store2 UserStore 与入口 key；不登录或重置 demo，不造接收 Item、仓库/位、Enrollment、采购、余额、现金、调拨或结算。目的店接收材料必须由其库管 UI 建**同 SKU、同名称、同单位**的零库存 Item 和材料仓/位，再真实 activate；原 receive 守卫核 name/unit，但目的店 `warehouse/allocations/{to_case_id}` 候选还按源 TransferLine.sku 筛选，只同名不足。需要的主档和启用事实均可由本次员工操作制造。HK-071 可使用已经获两店读取授权的合成 admin 仅做只读切店；不借其办理上述业务写入，仍核实际 auth/me 门店岗位和原 store selector。另一店未获权 inventory 保留本地身份读取他店真实 Item 的原404/403，具体服务器拒绝以运行事实为准。

## 同店最小动作与原整数合同

建议明确合成输入：原材料A采购8.000升，单价10.00元；原 UI 新材料B采购2.000单位，单价20.00元。两行约定共120.00元。所有数量由 UI 精确转换为整数 milli，金额为整数 cents；观察原响应、原单/Item版本与 request_id，每个办理阶段重新从原页面取真实版本。日期用原 UI 业务日，不用运行机器时区猜。

1. inventory `#procurement` 点 `[data-act=procurement-new]`，供应商 live choice 标签 `code · name`，两条 `[data-purchase-line]` Item 标签 `sku · name（unit）`，填 quantity/cost/reason。原 `POST /api/procurement/orders` 201 产生 flow_version=3 Case/PurchaseOrder/两条 PurchaseLine、待独立批准任务；无 Receipt、StockMove 或 Cash。manager 原 `approve`（values为空对象）200；申请人与审批人不同。
2. finance 在原单上传 category=procurement_contract 的合成合同依据，点 `prepay_request` 填30.00元、原业务日有效期与原因；manager 点对应申请的 `prepay_approve`；finance 上传 category=receipt 原付款凭据，点 `prepay_pay`，选本店原 Account、唯一凭证号，真实勾选 confirmed。三步都走 `/api/procurement/orders/{id}/actions/{key}`；后两步携 funds_request_id/funds_version。申请及批准不写 Cash；实际付款独立 PurchasePayment/Cash/Disbursement，期初预付3000分、无验收抵用。
3. inventory 原 `receive` 第一批A3.000、B1.000，填本单到货 evidence。原 modal 内实际点 `[data-prep-open]`、逐 `[data-prep-item]` 选择明确仓/位并填本次数量，再 `[data-prep-save]` 保存 Allocation，随后本人提交原验收。第二批A5.000、B1.000。每批 Allocation 只是准备、无库存或现金改变；原 receive 恰好增加 Receipt、StockMove(procurement_receipt)、WarehouseEntry、Item/Bin量值。两批金额50.00/70.00元；30.00预付抵第一批后应付20.00，finance 实际 pay20.00；第二批尾款pay70.00。净实际付款12000分，抵用不另写现金，未到余量结束后 payable=0。
4. 为核 HK073 期间桥接：第一批A到货3.000后，inventory 原 `count` 申请A库位（quantity固定0），manager approve；inventory capture实盘3.500，留原 baseline3000/counted3500/entry_cursor。观察提交后再完成上述第二批原 receive 的A+5000；manager post_count只追加+500 milli/+500分，桥接仍为+5000，不重记第二批。原 UI显示 baseline/counted/difference/bridge/current/projected，各值与 Observation/Entry对应。正差查询独立留 HK051 证据。
5. 到货/尾款结束后，inventory 原 `return_request` 选第一批A Receipt 的1.000，原本单凭据与原因；manager `return_approve`，库存只预占，不过账、不退款；inventory 先从原 Case 的“准备物资库位”进入 `#warehouse-allocation/{case_id}`，明确目的 `procurement_return`、1.000出方向和原库位，保存后回原采购单 `return_dispatch`。附 return_id/return_version 与当前 Case version，追加负 StockMove、PurchaseReturnPosting、PurchaseReturnValuation，supplier credit1000分与当前均价库存扣减分别核，不猜成本。原抵用顺序使预付30.00全部关联第一批A；本次退货必须追加-1000分 Allocation 引用原正抵用及 return_posting_id，释放这笔**原预付款**的1000分可退量。finance `refund` 精确选择此原 prepay_pay 的 PurchasePayment（不能选仍全部抵用的第一批 pay20.00）、原 Account、1000分、receipt凭据和唯一凭证号；运行时再次按实际 original_cash.available_cents/负抵用原关联核实。退款是入方向追加且 original_id明确，旧付款不改；最终净款11000分、应付/供应商应退均0。HK054/HK083分别保存申请批准、实物发出、原抵用冲回和实际退款事实。
6. inventory 原 local_move 申请A2.000到同仓第二真实位置，manager approve形成Hold；inventory dispatch只把原Bin数量移入同店transit，不写 StockMove、不改门店总量/价值；原 accept实际分批0.750与1.250，Entry、源/在途/目的数量与均价分配守恒。在途阶段可用量降低，实际全部接收后transit0，原任务结束。HK072独立保存全阶段。
7. 再在A实际源位做负差count（少0.250）与零差count两次独立create/approve/capture/post_count。负差只追加-250 milli及原均价成本；零差保留独立Observation/Approval/Task/Event但不增加StockMove。HK061查询负差来源，HK073须三组原事实全部满足才标自动check通过；不能只创建盘点单。每轮均使用当前实际Bin数量与版本，别复用上次基线。原先正差已得到可靠非零成本；零库存盘盈被原409保护的边界仍列未测。
8. manager/finance 原 `#warehouse-item/{item_id}` 与 warehouse 搜索查询非空量/价值，inventory同页不得读取金额；StockMove、Entry、Balance、Item数量、库存均价与 available/reserved/transit逐阶段对平。只读刷新不重复过账，HK070独立留证。各采购/盘点/退货旧原行、未授权业务表及其他 Item/Cash保护，不只核计数。

仓储自己的 execute/post_count 由原 service 内部 prepare精确位置；无需测试额外 API准备替代。采购 receive已有 inline库位准备；采购 return_dispatch 与跨店各动作仍须原 Case 的“准备物资库位”页面，不能因多一步绕过原 UI 或直接 POST Allocation。

## 紧邻跨店完整链

从上述本轮非空A物资及实际可用源位开始，真实来源留到同次材料 checkpoint，包含 source_item_id/sku/name/unit、原采购/收退款、各原 Move/Entry/Balance/Enrollment/Count IDs。采购B可保留后续维修用来源，当前不预填维修结果。

建议沿既有 checkpoint 追加顶层 `material_sources`，明确 primary/secondary 两个本店 Item 的实际 item_id/sku/name/unit、warehouse_id/location_ids/enrollment_id、purchase_order_id/receipt_ids/stock_move_ids；另有原付款/退款、盘点、移库 IDs 的对应逐check证据。全部字段只能从该场景真实已提交的原响应及只读DB取，不从 fixture manifest预置结果。维修候选可固定读取 primary 的“升”物资，net1250 milli（领1250、原退250、再领250）成本来自本轮采购原流水；材料链同店/跨店结束后仍有足够可用量。后继须读取此明确Item的真实当前数量/版本/位置，不要求初始零库存快照或材料前阶段整行仍与后继相等；不能为了复用报告重新覆写已完成checkpoint。

- source inventory `#transfers` 原 `transfer-new`：选另一启用门店、计划日、原因、A1.500；`POST /api/transfers` 201产生唯一 MaterialTransfer、两店不同 Case、TransferLine及双方任务。两店 manager 分别原 approve，申请人不得自批；仅 source/destination_approved_by与任务推进，库存/现金不变。
- source inventory 进本店 from_case 原 UI准备 `transfer_out` -1500及原位置（分配数量栏填正1.500，原 UI决定符号），回 `#transfers/{transfer_id}` 原 dispatch。请求含 transfer.version 与本店 case_version，StockMove -1500与源WarehouseEntry/TransferMovement.dispatch同量值；转为transit。HK055此独立事实成立后可留证，不能以之后目的入库替代。
- destination inventory 在本店 to_case 原 UI准备 `transfer_in` 的接收 Item及Bin，再 receive第一次 accept0.750/reject0，第二次 accept0.500/reject0.250。每次原 `[data-id=line_id].transfer-receive-line` 明确item、accept/reject，actual evidence属于本店Case。合格合计1250，真实入庫StockMove/Entry/Movement与来源dispatch成本比例一致；拒收250暂留跨店在途，不入目的库存、不产生cash。
- destination inventory 对明确 rejection_id 原 return_ship，250完整发运退回；source inventory 在from_case原页面准备 `transfer_return` +250，再原 return_receive quantity0.250、shipment_id、真实勾选passed=true并提交本店实际凭据。原StockMove original_id引用dispatch.stock_move_id、Movement.original_id引用return_ship；全部1500量与价值由accept1250+return_receive250结清，transfer.completed，两个店Case/Tasks关闭。
- manager读取目的合格接收对应 TransferSettlement：每个accept的两店amount_cents等額反向、合计0；不是银行实际收付款，不新增CashEntry。源店减少1250，目的店增加1250，集团物资量/成本守恒；250拒收原退保持完整追溯。HK047独立保存接收/拒收/退运/回库，运输损失、赔付、坏件与找回另项未测。
- 原获权读取身份实际切两家门店，按本轮同 SKU 的**不同 Item ID**核本店库存、Bin和来源；不能把切店后的source ID当destination本地ID。集团汇总只读与未获权读取拒绝分别保留证据，HK071不由单店HK070继承。

## 原接口、数据与选择器边界

采购写统一 `POST /api/procurement/orders/{case_id}/actions/{action}`：request_id/version/values；Approve空values，Receive line_id，Return receipt_id、return_id/return_version，Refund **original_payment_id**（不是flow PaymentLink original_id）。预付通过同一路由使用 funds_request_id/funds_version，prepay_pay confirmed=true。原读取 `/orders/{id}` 与 `/api/flow/cases/{id}` 的真实任务/附件、每次原提交后的详细GET必须完成，避免仅等POST响应即点迟到UI。

Warehouse create `POST /api/warehouse/cases`，commands `POST /api/warehouse/cases/{case_id}/commands/{action}`；字段上文明确，count申请quantity_milli=0，capture=counted_quantity_milli，approve仅other_in可value_cents。读取 `/api/warehouse/items/{item_id}/stock`。页面按钮 `wh-new[data-operation]`、`wh-action[data-key]`；activation `[data-wh-location] [name=location/location_qty]`；原作业form的source/destination/evidence_id/count字段不是助手表单。盘盈/亏查询要真实非空原Case详情的“本单实物收发”和库存不可变Entry，不能看空库存列表。

Allocation原 UI是 `#warehouse-allocation/{local_case_id}`，`[data-act=wh-allocate][data-id=item]`；字段purpose/quantity及`#wh-locations [data-wh-location]`。原POST `/api/warehouse/allocations/{case_id}` 携当前Case version、signed quantity_milli、purpose、locations；返回准备后的真实版本。保存前后只允许Allocation/Case/原回执推进，不改变Item/Bin/StockMove/资金；原实际动作消费指定Allocation并同事务过账。跨店目标 Item 必须匹配sku候选。

Transfer原写 `POST /api/transfers/{transfer_id}/actions/{action}`：request_id/**version+case_version**/values；收到原POST后等详细GET/body和表单关闭、真实新按钮可见再继续。实际凭据先从本店“业务任务与上传凭据”原Case页面上传；两店文件不互借。退回return_receive严格passed=true，不自动根据状态推合格。

SELECT-only核心表为 flow_cases/tasks/events/request_receipts/items/stock_moves、procurement_orders/lines/receipts/returns/return_lines/return_postings/payments/return_valuations、procurement_prepayment_facilities/requests/decisions/disbursements/payment_allocations、warehouse_documents/approvals/enrollments/balances/entries/holds/allocations/allocation_lines/count_observations、material_transfers/transfer_lines/transfer_movements/transfer_settlements/transfer_receipts、flow_files/file_scan_events、cash_entries和原资金主体来源。实现时使用模型声明的实际表名（调拨表带 material_transfer 前缀），不能照概念名构造SQL。旧不可变原行与其他业务全行保护；每笔新增资金核唯一category/direction/account/reference/actor/amount/original，库存与现金不可互相代替。合成附件只验structure_only，真实银行/现场、公司合同、PG/Linux、真实模型及员工验收保持独立。

## 静态研究来源与待执行边界

读取并人工核对 requirements_manifest/business_acceptance_catalog、master_data/vehicle_purchase/fixture、采购/预付API+service+models、Warehouse API/service/stock/models与原web、Transfer API/service/models及原web；未运行应用或测试。原 source 守卫已核：材料位置只允许active materials/mixed仓；已Enrollment原收发缺精确Allocation会409；盘点capture后允许期间收发但当前counting围栏仍保护；原付款/退款账户与经营主体守卫保持；退货批准和申请不得同人；调拨双方当前Store role及两个版本即时重验。

读取时前序源码指纹：master_data_business.py `e599184ff67bb93fcb332e39c555985a83a6c6f795096b432f0111b0d2d98a6b`；vehicle_purchase_business.py `bf404e4ca2723509faf448b2daa5a3545928afc1e84efb60c68b88d203e062ae`；fixture_server.py `614766ded87d36f8257acd573bc0470a09eeb66f4b1c1136c2adf55c42d3352f`；business_acceptance_catalog.json `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`；requirements_manifest.json `19840f4fc5fd816d94ea35a4602a31bde4674105e44621eeb4cfe42bdad27a1f`。这些是源审查指纹，不是服务镜像或验收结果；执行必须以负责人当轮统一镜像/脚本/依赖指纹为准。

最小后续候选建议仅新增 `tests/browser_click/material_business.py` 与本页；先同店9项原链落盘/短审，再由负责人决定是否同一精确补丁纳入跨店3项及两身份。注册/runner由根负责，fixture须独立明确授权窗口。前序不齐、原任务未交本人、原来源/余额不对平、真实409冲突或下载/响应未完整时保留失败/partial，不能直接补 SQL 或减少check求绿。当前全部状态为 source_reviewed/not_tested。

## PATCH-M8-4-BUSINESS-193-07 未注册候选

2026-10-01，负责人登记精确补丁并明确允许只写本页及新 `tests/browser_click/material_business.py` 后，九项本店候选已落盘。上文“没有物资候选脚本”是此前只读阶段记录；当前已有源码，尚未注册、启动或执行，全部业务成绩仍为 not_tested。本次不纳入上述跨店3项，也不修改 fixture、生产、已有场景、共享 runner 或计划。

入口 `SCENARIO=materials-hk069-045-054-083-070-072-073-051-061`，函数 `material_business(e, context, credentials)`，原 native 元组导出 `MATERIAL_SCENARIOS`，有限单场景上限420秒。九个原源 check_id 精确为 HK-069/045/054/083/070/072/073/051/061-business。每项原操作范围和证据分别保存；HK073捕捉正差后暂留 running，回到HK045完成第二批验收及尾款后再复核正差，最终另有负差/零差两次独立观察，三组全部满足才完整通过。失败时当前项 failed、其他正在办理项 partial，未办项 not_tested，不重放或覆盖历史失败。

实现承接同次 runner 已 passed 的固定 master/purchase 检查点，核同次外置 runtime、snapshot_stable、目录和6份实际脚本指纹；从明确原来源 ID SELECT 核零库存A、profile、材料仓/原库位、原供应商和原采购使用账户。第二B材料及第二库位由当前 inventory 原主档表单新增；B实际补货阈值为3.000件，使最终2.000件库存的原补货明细真实非空。两材料分别零数量启用，由不同 manager 依据本单实际上传凭据批准；无 StockMove 或现金成果预置。原Case待办未交给当前随机员工时，manager 先通过原 AssignInput（version/assignee_id/reason）交接，只登录 manifest 中的本人身份。

两行8.000升×10.00元及2.000件×20.00元、30.00预付申请/独立批准/财务原实际勾选、两批50.00/70.00验收及20.00/70.00尾款均走可见原表单。原 inline 库位逐项保存携连续实际版本、精确数量和本店仓/位；保存不改变库存，原 receive 才消费对应 Allocation、逐行形成 Receipt/StockMove/Entry。退第一批A1.000须独立批准、原Case库位准备、实物发出，保留原批冲款与实际库存成本；原正预付抵用须追加-1000分冲回并引用该 ReturnPosting，财务才选择释放的**原预付款**同账户实退10.00元。旧付款及旧抵用不可改写，实际现金净款11000分。

盘盈实盘baseline3000/count3500之后，第二批原到货+5000构成明确期间桥接；独立复核只追加+500 milli/+500分。原2.000升本店移库批准、移入在途、0.750/1.250两次实际接收保持门店量值不变，无门店 StockMove。后续负差-250 milli/-250分与零差分别原申请/批准/捕捉/复核，零差只有原观察和任务事件，没有物资流水。最终计划A7250 milli/7250分，原位5250、移入位2000；B2000 milli/4000分。这里是代码断言目标，当前没有执行证据，不能写作真实当前余额。

每次业务提交观测原 Cookie/CSRF/store/version/request_id、完成原POST及详细GET/渲染，核本人事件、任务、唯一原回执和真实 DB 关联。有限原行守卫对未授权表全行哈希保持、所有旧追加事实逐行保持，只有本轮明确原Case/Task/Item/Balance/Allocation/资金申请/退货/账户的指定列可推进；新增行限定本店与本轮Case/Item，库位Entry及准备明细还核明确关联。附件用外部合成TXT和原上传、原structure_only检查，不声称ClamAV或真实款物验收。全部数据库读取由 Evidence 的 mode=ro/query_only 入口；候选没有 app 导入、直接HTTP写入、JavaScript注入、SQL写入、夹具结果或外网调用。

HK070原只读查询覆盖本人库管量/可用/预占及金额隐藏、财务原量值、真实库位和不可变流水、原非空物资目录，以及本轮B“需补货”的原材料明细。HK051/HK061分别从本轮独立已过账盘盈/盘亏Case原UI查询，原流水数量、金额、ID及DB逐项对应，查询保持全部业务行不变；不把空列表或任意非空条目当源通过。

最后九项完整才输出 checkpoint 顶层 `material_sources.primary/secondary`，有限字段为 item_id/sku/name/unit/store_id/warehouse_id/location_ids/**source_location_id**/enrollment_id/purchase_order_id/receipt_ids/stock_move_ids/entry_ids/balance_ids/current_quantity_milli/current_value_cents/current_version。primary是本轮HK183的升材料，source_location_id显式指实际启用和本次采购接收原位，后继维修不能猜数组第一。后继仍须核同run passed、真实剩余可用量及有限关联；旧current_version是此场景终点证据，不要求之后办理仍相等。

已完成轻量AST、9个源名称/check绑定、有限SQL表名对应原模型、全部DB读取SELECT-only、无app/浏览器执行调用及空白检查。实现人工静态核对原角色、AssignInput、付款/退款原关联、原数量精度、库位目的/符号、盘点桥接和不可变流水合同；独立短审及负责人注册/全新镜像实际运行仍待做。候选源码指纹 `81634a82aa73c03bf24046c262995cb1e06072817de78c9bfc445a3e31bb7464`。完整193业务、人工流程/文案评价、跨店、维修、真实银行/实物、PG/Linux、真实模型与上线仍保持独立 pending/false。
