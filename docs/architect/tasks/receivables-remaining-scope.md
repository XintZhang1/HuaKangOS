# 三类当前待收款的最小真实来源研究

2026-10-01；仅源码研究，未编写或执行本批脚本。研究时 HEAD `8993ca8c755194a42a48e7323fe355e80c6bf9ae`，保留根代理及其他作者的工作树改动。仅新增本文，生产、已注册脚本、fixture、helper、catalog、runner、计划及旧 scope 均未改动。

## 原合同与本批范围

| 原 ID / 标题 / 固定 check | 原入口与必须非空来源 | 本批建议原单中间事实 |
| --- | --- | --- |
| HK157 物资应收账统计；`HK-157-business` | `#table/receivables`；业务为“精品销售”或“加装商品及安装费”的真实原客户待收，核原价、原退、实际净收 | 新普通 Retail v2，真实出库并客户接收，部分实际现金收款后仍有正欠额；不使用采购应付或供应商退款应收 |
| HK158 整车相关应收账统计；`HK-158-business` | 同表；辨认原整车订单及相关服务的约定、累计结算和待收，包含尚未到收款点的业务 | 新本版复核、当前 VIN 配车、原生成字节签回的订单，部分实收；另建明确关联该订单的已授权代办服务费，部分实收后仍有正欠额 |
| HK159 维修应收账统计；`HK-159-business` | 同表；真实 RepairAllocation 的外部承担方金额、已结算、欠款及到期状态；内部承担单独核对并排除客户应收 | 新实际到店 Repair v4，已授权、真实施工、独立质检、主管冻结客户及明确内部承担，客户款仅部分到账 |

来源逐项核对 `tests/browser_click/business_acceptance_catalog.json`、`requirements_manifest.json` 和 `docs/workflow-source/services.json` 的 `wf-report-157/158/159`。三项 completion 都是“按相同范围核对明细、原单及可导出结果”。原工作流最后一句“图表页使用对应图的导出按钮”描述已有图的条件操作，没有明确要求新建应收专图；PROJECT_SPEC 仅要求原冻结口径报表。

当前源码确有财务“当前尚待收取”KPI、完整待收表、原单钻取和 CSV，但没有 `table='receivables'` 的专用 chart。财务现有 `cash_category` 图属于实际现金，不能冒称应收图。本批按上述真实合同检查 KPI / 全表 / CSV / 原单；不为统一模板补图或改口径。无应收图应在证据中明确记录，不登记该不存在图的操作通过。原表说明“与图表使用同一份有效数据”是共享展示文案，不产生另一张应收图合同。

本批最多新增三个完整报表 check；其新原单是必要非空前置，不重复登记销售、采购、精品或维修旧 check。六类 criteria 分别留状态，自动 UI/API/DB 断言不替代人工体验、文案与显示审阅，`business_accepted=false`、`full_193_business_acceptance=false`。本文所有条件均 `not_tested`。

## 共同报表事实与实际入口

- `app/flow_analytics.py:93`：真实表键 `receivables`、标题“当前待收款”，八列为业务单号、门店、客户、业务、约定金额（元）、累计已收（元）、尚待收取（元）、应收状态。金额列是由整数分转换的精确两位元字符串，行 metadata 的 `amount_cents` 是正 gap；行 route 为原 `case` ID。
- `flow_analytics.py:146–189`：只列正欠额。Retail 为原 `totals.charge_cents/net_paid_cents/receivable_cents`；普通订单为原 `net_charge` 和 `case_paid`；已授权 ServiceOrder 的 `fee/pass` 分别显示“本店服务费 / 客户代缴本金”；维修为 `repair_service.receivable_rows`，按承担方独立列“维修多方承担”。内部承担明确不返回该应收行。
- `flow_analytics.py:547,563`：`receivable_cents` 是当前授权范围内全部正 gap 之和，不能硬断仅等于本批三张单；历史日期筛选不重建历史应收余额。累计结算可以包含原预收、集团或权益抵用；本批新单明确只现金，仍分别核 CashEntry 和原结算关联，不能把全部 paid 称作现金。
- 财务本人真实登录并确认具体店后，由原目录进入 `#analytics/finance`，选择业务时区 Asia/Shanghai 的开始/结束日并点“更新报表”：`GET /api/flow/analytics?date_from=...&date_to=...`。无 `kind` 筛选，不造新 dataset。核 KPI“当前尚待收取”与整个原表分值合计，再点该 KPI 的“查看明细”进入 `#table/receivables`。
- `web/app.js:337–349,452–454`：KPI 用原 metrics；表每页 50 行，分页与原 row index 一致。KPI 跳表可复用同份缓存，不要求凭空再 GET；重新选择日期或付款后更新报表必须清缓存再 GET。逐页核全表，不仅筛三个目标行。三张单的“查看”走返回 route，真实 `#case/{id}` 与 `GET /api/flow/cases/{id}`；再进入对应原领域详情核冻结报价/付款/承担，不能只看通用标题。
- CSV 原入口是表上“导出明细”：`GET /api/flow/analytics/export?dataset=receivables&date_from=...&date_to=...`。使用真实下载，UTF-8 BOM、八列表头和全量每行与同范围原表一致；`safe` 对字符串公式首字符作原保护，不能擅自改数值。每次原下载只允许精确一条本人/本店 `AuditLog(action='export', entity_type='flow_analytics', entity_id=null, reason='当前待收款')` 新增。其余旧审计逐列相同，全部业务数据不变；原导出采用 `get_audited_read_db`，不重试或忽略未知响应。

## HK157：新普通精品留下正欠额

固定父为同轮整场通过的 `boutique-purchase-retail-hk074-052-058-062-064-082`，读取其 `report_sources.item_ids/profile_ids/enrollment_ids/warehouse_id/location_id/account_id`；客户可用同轮 `repair-selfpay-hk031-034-044-049-053-079.report_sources.customer_id`。父终态只供明确主档/真实库存，不供终态零欠额。

提交前重读原 Item、profile、启用 WarehouseEnrollment、当前库位 Balance/Hold 及可用量，有限目标 item 至少可售 `1000`。原库存本轮已被其他链消费时使用真实当前值，不能按父购买数量推断余量；若不足，另登记原采购/分批收货前置，不能填库存或借另一批成本。

服务顾问从 `#retail` 原“新建精品销售”给同店客户新建一件纯商品：`quantity_milli=1000, unit_price_cents=2000, work_item_id=null, installation_unit_price_cents=0, discount_cents=0, related_repair_id=null`；不选择会员价格/集团混合支付。`POST /api/retail/orders` 原 Create，普通 helper 必须按真实顶层 `id` 读取，不漏必需 `body_key=('id',)`。

另一主管办理 `approve`，顾问上传本版 authorization 并 `authorize(revision)`；库管在原仓储表单 `POST /api/warehouse/allocations/{case_id}` 明确原实库位准备后，通过原 Retail `dispatch` 实际发出；顾问 `accept` 记录客户实际接收。纯商品没有安装作业，因此不捏造 install。财务本人原 `receive` 表单实收 `500` 分，原 receipt / 本店启用 account / 独立 reference；最终 charge `2000`、net paid `500`、due `1500`、state `settling`，只作为当前欠额来源，不称已结清。

原命令 `POST /api/retail/orders/{id}/actions/{approve|authorize|dispatch|accept|receive}`，每次当前 `version/request_id/values`；每张原 Task 由本人办理，需交接时仅主管原 assign 严格三字段。DB 核新 `retail_orders/lines/reservations/dispatches/payments`、原方向 StockMove 与成本、WarehouseEntry/Balance、PaymentLink/CashEntry，旧 Repair 原领料/现金/所有其他 RetailGroup 方案及 C/P/S 全不变。新库存实际成本从当前原库账取值，未取到不能猜零。目标表行显示“精品销售 / 20.00 / 5.00 / 15.00 / 尚待收取”。

## HK158：整车和相关服务的两个实施选项

**选项 A：独立新采购并留下新订单中间欠额，建议优先。** 同轮通过的 `vehicle-purchase-hk171-177-178-026-021-018-029` 提供已明确供应商、车型、整车仓位、原账户的有限 acceptance evidence（该父没有统一 `report_sources`，按 HK171/177/178/021 原 check evidence 取 ID）；不要从全库找第一行。复用这些启用主档，通过原 `#vehicle-procurement` 新建一台新 VIN 采购，另一主管冻结真实 C/P，财务原款支付，库管按真实发运凭据发运、按现场核验新 VIN 原验收收车。实际 `POST /api/vehicle-procurement/orders` 建计划，原 `/{id}/actions/{approve|request_funds|pay|ship|receive}` 分别批准逐行价格、请款、付款、发运、收车；具体供应商/车型/仓位/价格/来源版本和原合同字节沿现行 `vehicle_procurement_api/service`，不能拿父旧采购 receipt 当新操作。

随后由该客户实际销售负责人从 `#sales-quotes` 新建当前车型版本报价，另一主管 `quote_approve`、库管 `allocate` 当前已审核可用 VIN、销售生成本版车型/VIN/金额合同并上传原签回字节后 `sign`。`POST /api/sales-quotes/orders` 建单；实际审批/配车/签回/收款走 `/api/flow/cases/{id}/actions/{action}` 原 v4 合同。选择明确新约定 `10000` 分，财务只实收 `3000` 分，则当前待收 `7000` 分；未做实际交付不称客户提车。原 SalesQuote、Review、Resolution、Consent、VehicleHold、generated/signed FileAsset 字节来源链与 quote/model/VIN 同一，原款 CashEntry / PaymentLink 单独核。

同一已签回新单再从 `#service-orders` 新建 `subtype=agency, source_order_id=新order_id, source_version=当时当前CAS, customer_id=同客户, delivery_blocking=false`。从本轮主档 HK179 acceptance evidence 取启用 AgencyProject，逐行 quote 一项 `fee`：数量 `1000`、单价 `1000` 分、明确到期日、无 pass 代缴。另一主管批准、顾问上传当前 quote authorization，财务实收 `300` 分；`POST /api/service-orders` 与 `/{id}/actions/{quote|approve|authorize|receive}`。目标服务费行 `10.00 / 3.00 / 7.00`，真实 `ServiceOrder.source_order_id/Case.parent_id` 指新 order。只验证已授权相关服务待收，未提交外部手续/办结，不捏造 external_result 或 ServiceFulfillment。

两行都已到本版有效约定与原收款关口，且有正欠额。关联服务不能在无签回新报价上偷渡：`sales_quote_service.py:142–146` 拒绝 pending quote / 无 active quote。虽然 `_new_quote` 在未配车的新 reserved 单先设置金额，原当前待收也包括未到收款点的约定，**只建未配车报价不足本批选择的完整 HK158 准入**，不使用该轻路径替代有效 VIN 与本版签回。

**选项 B：在未来一次完整 PDI 新鲜链的中间时点加独立只读检查。** `sales-pdi-addon-hk037-065-075` 在同次签回、第一笔原实收后、第二笔收齐/实际交付前保存正欠额原 GET/全表/CSV/原单证据，并同步办理上段真正关联服务的正欠额，再收尾 PDI。该方案须根另登记作者/执行顺序与固定中间 evidence source schema；当前已经通过并交付的 PDI checkpoint 只保存终态，不能把历史 API/终态重新解释成待收，也不能改旧父原单造余额。

有限 VIN 约束：原销售取消的第二 VIN 已被 PDI 再配车并交付时不可用；`vehicle-import-operations-hk019-027-028-030-025-023.current_vehicle_id` 亦可能已经在跨店链目的店实际验收。跨店退运若同轮整场 passed 可明确提供 `interstore-original-hk020-024-047-055-084.report_sources.returned_vehicle_id` 的新代次，但只能在当时当前店 Custody/Position/审批/无 Hold/未售/真实车型均可用且与父顺序不冲突时另登记有限分支，不能默选旧 `cancelled_vehicle_id`。建议 A 不依赖这些有消费顺序冲突的车辆。

## HK159：新维修承担与部分原款，工位条件

有限父 `repair-selfpay-hk031-034-044-049-053-079.report_sources.customer_id/customer_vehicle_id/vin/appointment_id/repair_case_id`，以该明确原 `intake_repair_contexts.case_id` 找 resource，不扫任意工位。读原 CustomerVehicle 及当前 customer/group vehicle identity；同 VIN 无其他工位实际占用，resource 启用、未被占且本时段无 scheduled/arrived/未终结 converted 预约方可复用。

若同轮别链占用原工位，**新建独立服务工位**是最短可控前置：主管原 `#service-intake/resources` “新增服务工位”，`POST /api/service-intake/resources {request_id,code,name,resource_type:'repair'}`，保留 `intake_resources/intake_command_receipts/Audit`；不直接写资源，也不提前释放他人的车辆。若同一客户 VIN 自身尚有真实活动维修，应等待它原流程收尾，或另登记 UI 建立明确新 CustomerVehicle 来源，不能只换工位绕 VIN 开工锁。

顾问原接待现场排队 `POST /api/service-intake/appointments`（`mode='walk_in', customer_vehicle_id/resource_id/带时区starts_at/ends_at/problem/preset_id=null`）；原 `arrive` 现场 17 位 VIN、整数里程与 evidence，原 `convert` 生成独立 Repair v4。使用本轮主档 HK175 evidence 的有效作业，纯 work 一行 `quantity_milli=1000, unit_price_cents=3000`，不造领料。顾问 quote→另一主管 price_approve→顾问授权当前 quote；技师真实 start/finish，顾问独立于技师 quality passed。

主管 `allocate` 冻结客户承担 `2000` 分（`payer_id=null`，姓名来自本客户）＋内部承担 `1000` 分（`payer_id=null,payer_name=明确合成承担主体`），金额和当前授权价 `3000` 严格相等；due_date 业务今日或明确未来日，labor_cost_cents 使用本次事前明确的合成实际人工成本，不估利润。财务原 `receive` 仅给客户 allocation 实收 `500` 分，原 receipt/account/reference，最终客户金额 `2000`、已结算 `500`、due `1500`，内部 `1000` 不出现在 receivables、不生成内部 Cash；无保险/厂家申请则不造 ClaimBinding。

原 API `GET /api/repair-orders/{id}` 与 `POST /api/repair-orders/{id}/actions/{quote|price_approve|authorize|start|finish|quality|allocate|receive}`；每次 Case/CAS、Quote ID、真实本人 Task 和严格 schema，payer 默认字段仍按原校验回执 canonical 结果核，不能漏 null/name/due。核 `intake_appointments/arrivals/vehicle_bindings/repair_contexts/resource_uses`、`repair_quotes/lines/price_approvals/authorizations/quality/settlements/allocations/payments` 和 `flow_payment_links/cash_entries`。原所有 StockMove / RepairStock /其他现金旧行不变；target 表显示“维修多方承担 / 本客户 / 20.00 / 5.00 / 15.00”。

未结清客户款时 Case 留 `settling`，`repair_service.py:454–459` 的客户接车守卫保持，不能按任务准备或质检通过认定出厂。为不占后续真实工位，施工已完时技师可原“确认实际移出工位”并上传事实凭据：`POST /api/service-intake/orders/{id}/resource/release`，原 case version/evidence/reason，追加 `ResourceUse` 并清本次 `active_case_id`；这与客户接车/GateRepairExit 不同，不能造实际离场。是否实际移出需在合成演练说明先明确。该源仍有未收账款/开放财务任务，不伪造全部流程终结。

## 下一候选合同与保护

建议根后续登记新 `tests/browser_click/receivables_business.py` 与对应任务记录，一条场景三完整 check，先决定选项 A 或 B；本文不是作者授权。父 checkpoint 必须同轮、整场 passed、源码/脚本/manifest 相符，固定有限路径；必要父失败则本批全 `not_tested`，不得用局部数、历史库或手工状态顶替。

建议输出 `report_sources`：`store_id/business_date/account_id/customer_id`，新 `retail_case_id/line_ids/dispatch_ids/payment_link_id/cash_id/charge_cents/paid_cents/due_cents`；新 `sales_case_id/vehicle_id/inventory_generation/quote_id/consent_id/payment_link_id/cash_id`，关联 `service_case_id/quote_id/line_ids/tender_ids/payment_link_id/cash_id`；新 `repair_case_id/customer_vehicle_id/resource_id/quote_id/settlement_id/customer_allocation_id/internal_allocation_id/payment_link_id/cash_id`；每类正欠额检查时的原版本、analytics date range/table digest/CSV digest、有限原 drill URL 和全部原封包 request digest。保留 source branch，不能只写“3 项通过”。

正向原 UI 每次提交前读取当前身份/店/原对象 CAS；未知结果停止，不换 request_id 重放。登录本身合法 Audit/session 写应在动作基线之前完成，再全表旧行 guard；每步只允许该原单明确 ID 的可变列、新实体/任务/回执/事件及正确原账户现金。普通 FlowReceipt、Retail/Service/Repair 原 canonical digest 各自按真实 service，不能强令另域回执。跨店和集团账户、旧 generated/signed/receipt 文件、原付款与账款不可覆盖；附件 JSON 仅元信息、实际存储 blob 长度/SHA，原 bytes 留内存 guard，不 default=str/base64 输出。

报表每次重新取全部当前范围 rows，逐原来源构建整数分 oracle，并核 KPI 为全范围所有正欠额总和；三个目标来源不能替代其他既有合法行。三个 check 可共用同一次完整 table/CSV 事实但各自有独立非空目标行、原单钻取/DB核验和状态。读取普通 GET 全业务零写；每次 CSV 仅精确原 export Audit 新增，旧 Audit/所有业务行不放宽。

## 未测条件与静态指纹

必须待执行：真实表单/lookup/任务交接、同轮当前剩库存/资源/车辆、原收款成功结果、全范围分页/下载/三类钻取、更新后缓存、人工宽度/文案/流程。建议分支仍未测：跨店汇总读权限、逾期边界、保险/厂家正待收、预收或权益抵用、原退后的正余额/冻结更正、并发版本与拒绝、收齐后行退出；不机械扩写本批，也不将它们隐含记 passed。

源读取指纹：catalog `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`；原 services `5b302d5c731edc424788efd1765bf32b9dea827a3bd9691500f261ed98f11040`；`flow_analytics.py` `dde62d794a4ea194ea8dd93988362d2a5c1ef2d3df2962be78b52ac8527745bc`；`flow_api.py` `b453a1088e324b8b7f79f1c9c14f1c24f63970ece00df3c827e9af38d116df8e`；`web/app.js` `642525adde83676ed157d6ee96e667bb38feb1d57b331e37e027bbba3bad6453`。静态只读核对，不代表运行指纹或实测通过。
