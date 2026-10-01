# 任务：维修与物资报表后继范围

**任务 id 与负责人**：`report-followon-scope`；`remaining_audit`。2026-10-01，仅源码研究；本文件是唯一写入产物。未启动应用、浏览器或验证，未修改生产、测试、夹具、目录、runner、计划。没有新增已执行成绩。

**目标与架构依据**：沿 DSH Architect 最近一个连贯增量，使用 `business_acceptance_catalog.json` 的原标题、`HK-xxx-business` 原 check 和 `docs/workflow-source/services.json` 的 `wf-report-xxx` 原入口。剩余25个报表需求不能用之前11项、空表、导航或其它模块的业务通过替代。图表、表格、原单及 CSV 使用同门店、同期间、同一真实来源；金额整数分、数量整数千分之一，未知保留。六类 criterion 中体验与文案仍需独立人工审阅，自动通过不设置 `business_accepted` 或 `full_193_business_acceptance`。

**代码快照**：当前 HEAD `8993ca8`，读取当前工作树。根报告保险最小4场景源 `978552f0…`／脚本 `a4e18d82…` 已退出0；这仅是根提供的前序进度，不是本任务执行结果。保险原附件类别及新注册在工作树；随后审计页原筛选显示变更 `web/app.js` SHA256 `2700fb9aac46bc01e7f43c93abbd7421da096a96f839c5beeb8acfd3e16c6bdc` 已只读短审。后续真正运行必须重新冻结整个联合镜像指纹，不与旧运行拼成绩。

## 最近可作者的一批：8个完整自动 check

建议一个独立报表场景，逐项 active／passed／failed／not_tested；失败即停止，先前局部诊断不等于整场完成。这是候选范围，不授权本任务写测试。原查询使用本店 manager，沿真实统计分析目录检索编号后点击入口，原表日期提交、分页、图表、钻取、下载；不直接请求 API 代替操作。

| check／原标题 | 原入口与 API | 必须匹配的同轮事实、图表与边界 |
|---|---|---|
| `HK-146-business` 维修预约分析 | `#table/service_appointments`；GET `/api/flow/analytics`；CSV dataset=`service_appointments` | 以首维修 `report_sources.appointment_id` 的当前 `intake_appointments.starts_at` 转 Asia/Shanghai 后日期选批次；原改约时段、mode=appointment、status=converted、唯一 `intake_arrivals`、关联维修原编号与 UI 一致。建立日、到店日分别核对，不能替代预约日。图 `service_appointments` 按实际批次当前状态计数；从原接待单钻取。 |
| `HK-147-business` 维修工单分析 | `#table/repairs`；同 flow GET／CSV dataset=`repairs` | 首维修原 Case(kind=repair, flow_version=4)、开单 business_date、完成态、amount、`payer=多方承担`、当前累计实收匹配。原承担细节用明确 `allocation_id`、`repair_allocations`、`repair_payments`→`flow_payment_links`→`cash_entries`核对；表内“多方承担”不是各方比例明细。图 `repair_state` 与同表状态计数；`repair_value` 使用实际接车日的 `repair_settlements`，金额另核，不混成开单日收入。 |
| `HK-148-business` 维修项目分析 | `#table/repair_projects`；同 flow GET／CSV dataset=`repair_projects` | 唯一 `repair_settlements.quote_id` 等于首维修最终已授权服务报价，`Case.data.released_date`是真正接车日；work `RepairLine` 的代码、名称、quantity_milli、计费单位、revision、amount 与表及 `repair_projects` 图一致。配件另 `repair_parts`，不混进作业行，不把核价当现金或作业级耗料成本。 |
| `HK-149-business` 维修领料分析 | `#repair-materials`；GET `/api/repair-material-reports?date_from&date_to&case_id&item_id&model_name&work_item_id`；CSV `/export/{key}` 同参数 | 原首维修领1250、退250、补领250，净1250千分之一；各 `RepairStock`→`StockMove` 的实际业务日、原报价行／授权摘要、退料 original_id 和真实原成本一致。历史车型只用 `repair_vehicle_model_snapshot` 与原 Binding，不用现在车型猜补。UI四筛选逐一真实选择，再组合核同三流水，无作业半连接重复。`repair_material_totals`、`repair_material_movements`、`repair_material_issues` 及图 `repair_material_cost`；本明确维修须 complete/model_complete=true、issues空，差异表空是正确结果，不算本项非空来源。明细点击“查看原维修单”。 |
| `HK-150-business` 物资入库历史统计 | `#table/movements`；同 flow GET／CSV dataset=`movements` | 原物资两个分批采购 receipt、维修真实退料、已批准正盘差分别为实际入方向；用 `StockMove.quantity_milli/value_cents/business_date/purpose/case_id/original_id` 对照原单。逐来源保留，不能把领料退回再作为第二笔采购。图 `material_value` 的入库成本按原正价值累计，单位不相加。 |
| `HK-151-business` 物资出库历史统计 | 同 `#table/movements`；同原 dataset，无虚构出库子接口 | 单独核物资采购原退、负盘差、首维修两次领料的原负 quantity／value；真实原退指向原收货，领料指向原维修／报价。与150共享整表和导出可复用一次原读取／下载证据，但本项仍独立核非空出方向、原单及 `material_value` 出库成本，不能复用入方向判 passed。 |
| `HK-153-business` 物资采购订货统计 | `#procurement-cohort`；GET `/api/inventory-reports/procurement?date_from&date_to`；CSV `/api/inventory-reports/procurement/export/{table_key}` | 按唯一 `procurement_create` 事件本地日选原订货批次；现代码依据是原申请事件日，不能改用当前 Case 字段或到货日。原A8、B2两行和两个真实分批验收、A原批退1，对照 `PurchaseOrder/Line/Receipt/ReturnPosting/StockMove`：订货=到货+仍待+关闭未到+待批；净留存=到货-原退。这些是截至 as_of 当前累计，不是截止所选期末的历史履约。`procurement_cohort_lines/postings/issues`；同单位升图的动态 `procurement_cohort_unit_N` 表由实际响应取得，禁止猜编号。图原始行导出必须用该动态键，空问题表不代替非空订货及收退记录。 |
| `HK-155-business` 物资移库明细统计 | `#table/warehouse_local_moves`；同 flow GET／CSV dataset=`warehouse_local_moves` | 从 material primary 的明确 `entry_ids/balance_ids` 重读原 `WarehouseDocument.operation=local_move` 的有限 case_id，原发出2、分次接收0.75/1.25，原库位→在途→目的库位每次配对 quantity／value 守恒；`average_revaluation` 单列，不新增门店采购／StockMove。图 `warehouse_local_moves` 是期间价值净变化，应零；原UI目前全零图显示“当前范围暂无可绘制数据”，应与非空配对明细和零净额一起核对，不伪造非零图。 |

通用 flow API 当前入口 `app/flow_api.py:405/436`，实际 UI `web/app.js` 的 `analyticData/analyticsTablePage/analyticsPage`。专用入口见 `web/repairmaterials.js:5–9`、`web/inventoryreports.js:25–31`。源实现分别为 `operations_analytics.py:129–152`、`flow_analytics.py:137–152,310–318,357–361`、`service_analytics.py:56–85`、`repair_material_analytics.py:16–130`、`procurement_analytics.py:16–139`、`operations_analytics.py:57–69`。这些原路径均已存在，不需新增统计口径或业务写入口。

## 有限前序与最小定向清单

同轮依次执行以下5个前序，再执行新报表场景（名字由根登记）。三个基础场景独立生成原事实；material 固定依赖 master／purchase，first repair 固定依赖 customer／master／material。无需销售、会员、财务、保险或洗车场景才能验这8项。

1. `vehicle-purchase-hk171-177-178-026-021-018-029`
2. `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187`
3. `customer-service-hk098-107-108-109`
4. `materials-hk069-045-054-083-070-072-073-051-061`
5. `repair-selfpay-hk031-034-044-049-053-079`

读取固定 scenario 的本轮 checkpoint，必须 complete/passed、runner本轮对应passed、同一次来源指纹；没有来源即停，不扫描旧目录寻找通过结果。来源包括：

- first repair `report_sources` 的 `appointment_id/intake_case_id/repair_case_id/quote_id/allocation_id/payment_link_id/cash_id/customer_vehicle_id/material_item_id`。明确原三笔维修 StockMove ID 从该维修 RepairStock.stock_move_id读，不能扫同名物资或旧维修。
- material `material_sources.primary/secondary` 的 `item_id/purchase_order_id/receipt_ids/stock_move_ids/entry_ids/balance_ids/enrollment_id/warehouse_id/source_location_id/location_ids`。原采购及移库老行保持；库存当前值、版本、库位余额必须现场重读，后继维修或加装已经改变它们，不强行等于物资 checkpoint 当时数量。
- customer HK099只读本地车辆局部来源，仍 partial、business_accepted=false；本批报表不提升99、无跨店共享车辆／文件或集团往来准入。

日期从上述原事实的本地业务日选择（Asia/Shanghai）；预约用 starts_at，维修项目用 released_date，库存用 business_date，采购批次用原事件日。日期不得晚于服务端 today、不得超过原一年上限；若本次改约跨日尚在未来，先报告原前置不能纳入当前报表，不篡改时钟／日期以造记录。flow整包可能含同店其它原事实，图及 CSV 须核整个响应范围；目标有限行从全表逐行匹配，重复外观行按多重集／原关联计数，不按单号或金额去重。

## 查询、钻取与下载的准入

- 每次登录后再建立业务／审计 baseline（真实登录本来追加 login AuditLog）。普通GET、筛选、分页、钻取只读；全部旧行和其它表摘要原样。只从原DOM明确行点击，等待同原ID的GET成功与h1／当前详情渲染，不立即在“正在读取”页点按钮。窄屏只点可见唯一表／卡入口。
- flow图与表使用 `state.analytics` 同数据；日期提交清缓存，不能借旧期间缓存。专用报表每次原查询响应必须核返回date/filter及current store，图数值与原API及独立DB一致。专用所有明细页25行、flow50行，真实翻到全部原分页，不只比较第一页。
- CSV走原按钮、原下载事件、实际文件；同参数、全部headers／rows／排序／公式防护。原CSV响应仅读状态／请求信息，**不能为获取正文再次 `response.body()`／CDP读取原URL**；CSV正文只来自保存的下载文件。结果不明不得重放。
- 每次 flow CSV仅允许精确一条当前员工当前店 `AuditLog(action=export,entity_type=flow_analytics,entity_id=null,reason=原table.title)`；采购为 `procurement_inventory_report`，reason=`date_from至date_to table_key`；维修领料为 `repair_material_report` 同reason形式。before/after应空，全部旧AuditLog逐行原字节、其它表完整摘要不变；不排除整个 audit_logs、不放宽到多条。一次导出可被两个共享表check引用，不能说执行了两次下载。
- 现有 `report_business.export_csv` 只支持 flow、vehicles，else是 visit-activity，**不得传 procurement 或 repair_materials 直接复用else分支**。后续作者只在本人新脚本显式适配这两原路径、完整参数和精确审计类别；不改旧注册 helper 或扩建平台。`graph` 已按0图显示处理，可窄复用。
- 自动结论仍含人工 pending：前端预期、流程简易、简洁文案、后端匹配、硬bug及来源完整分别记录；体感与文案不由代码行数或自动passed推断。真实模型／PG／员工／外部资金等gates继续独立。

## 待根决策的生产接线与真实条件

1. **HK149 CSV的同型SQLite事务条件，未实测失败。** `app/repair_material_api.py:20–28` 仍 `db=Depends(get_db)`，鉴权及原来源读取后 `audit+commit`；已有 `flow_api:436`、`inventory_reports_api`、`visit_activity_api:18` 使用服务端 `get_audited_read_db=get_write_db`，在SQLite读身份前保留writer。下一作者保持一条audit严格断言，由根决定先原点击复现或另登记有限依赖接线。不能声称已捕获本路径517；不自动retry、rollback重放或放宽审计。
2. **HK161后批同型条件。** `app/material_value_api.py:24–35` 同为get_db→读→audit+commit，目前未进推荐8项；独立记待实测，不假定是已观察bug。
3. **HK152完整期间来源不足。** `warehouse_period_analytics.py:159–165` 只有查询开始日严格晚于真实桥接本地日才返回完整期初／入／出；本轮今日UI启用、原期间不允许未来结束，不能制造“午夜期初0”。当天真实baseline/entries/closing可局部核对，`complete=false/closing_complete=true`及null必须保留。需要另一真实后续业务日或明确可授权原历史启用来源后独立验完整期间；不改旧定义、回填昨日或把unknown改0。

## 其余17项的下一前置，均未执行

| 原check／原标题 | 当前可追溯来源与下一范围决定 |
|---|---|
| HK139 加装单分析 | sales-followon `report_sources.addon_case_id` 已有实际 AddonAcceptance／Dispatch、商品原成本；后批可核非空 `addon_actual_facts`、原单、图、CSV。真实售后原退尚未产生则该分支not_tested，不编退货。 |
| HK140 代办单分析 | 同轮 `agency_case_id` 的逐项目 ServiceFulfillment（补件后真办结）与 `customer_other_case_id` 明确服务费；后批 `service_fee_facts` 逐原行、fee/pass分桶和原CSV，不以代缴现金当收入。 |
| HK141 保险单分析 | insurance `report_sources` 的两原保险单／issued results、原CommissionReview及真实CommissionPayment可读。source `sales_service_analytics.py:32–54` 有policy表但无绑定该policy表的chart，当前sales图为独立佣金目标差额和现金；旧 `service_analytics.insurance_completed` 排除v3，不能拿其空图替代新保单来源。后批按原合同明确核保单表与两佣金图；若要每保单单独图须根登记产品接线，不猜图键。撤保不删除原实际出保历史，佣金净0不代表没有非空收退明细。 |
| HK152 物资仓库入出存统计 | 上述真实日期前置缺口；当天只partial，不列推荐完整check。 |
| HK154 精品销售统计 | 当前已登记链没有真实 RetailDispatch/Settlement/ReturnPosting；加装不等于精品销售，待原retail实际交付。 |
| HK156 精品销售施工统计 | 待原retail实际安装完工event及WorkItem冻结引用；首维修或加装技师完成不能替代。 |
| HK157 物资应收账统计 | 待真实retail/物资业务尚待收事实；现物资采购是应付、已付加装不造应收。 |
| HK158 整车相关应收账统计 | 当前销售／代办完整收款后表中目标余额0；需在原报价已生效／尚待收阶段插入真正报表验收，或新独立同客户合法未收来源。不能结束后空表通过。 |
| HK159 维修应收账统计 | 首维修已全款，source完整却当前应收空；需原冻结承担后到账前（明确原payer／amount／due）验收，不能用已付款历史行充当前未收。 |
| HK161 物资收入成本对照表 | first repair及sales-followon实际加装可支撑 repair/addon两来源；`goods+services+unallocated=原对外净额`，按本Item筛选时原单核对仍保留全部组件。stock采购／原退／盘差为非履约库存；暂无retail/售后调整/已领未履约条件则明确未测，不额外扩业务为凑7表。专用CSV事务待根处理。 |
| HK162 预收款统计 | finance `report_sources.advance_id/original_advance_cash_id/stored_correction_id/credit_link_id/refund_cash_id` 已有 receive10000/correction-1000/apply-4000/refund-5000；当前余额0但原非空Advance行、四流水可核，非空不要求余额正。后批同flow表／图／CSV，当前余额与期间变动分别核，不当历史余额。会员集团本金非此预收。 |
| HK163 财务结算统计 | 等新finance-followon场景实际 complete/passed产生有限 `reconciliation_batch_ids` 后可读各definition22冻结manifest/hash/summary和原CSV。当前未注册作者文件存在不代表实际批次；旧1..21冻结。原 `/api/reconciliation/batches/{id}/export` 合同不写export audit，与flow CSV“一条”不同，禁止统一套断言。原95创建/独立seal不由163读报表替代。 |
| HK164 客户车辆统计 | customer099local／first repair明确CV身份当前关系可支持本店非空 `customer_vehicle_stats`。manager原钻取route=`customer_vehicle`已有 `web/app.js`分支；按vehicle_identity_id去重/有效关系数，不当库存。跨店共享同车与车型冲突暂无源，单列未测，不造跨店关系。可作为同5前序的紧邻增量，不必先做集团。 |
| HK165 客户回访统计 | sales delivered原 `make_callback`（flow_engine.py:622）在允许联系时建立parent=delivered order的独立callback；必须现场限定parent／customer／store读取实际新callback和Task再选非空。咨询／投诉／救援／renewal不在本表，不能复用customer链四单。manager可看原文／原单，finance/汇总只计数，原同期间批次/一次任务一次。 |
| HK166 进出厂统计 | first repair的实际ArrivalFact＋唯一repair_v4_release／原接车凭据已有闭合进出源；可作为同5前序的紧邻增量，经原visit-activity UI明确选择该repair。完整源下核2动作、1到店批次、真实分钟时长与CSV；GateFact非维修进出／纠正/取消独立离场未发生则未测，不推断。 |
| HK168 会员积分统计 | membership当前 `report_sources` 只有身份／识别卡／集团本金充值退款，无points；候选明确 `points_tier_period_benefit_consumption_acceptance=false`。需未来真实 BenefitEntry(points)、消费目标 PointsChange及追回债务源。原表 `benefit_points/membership_points/membership_points_debts`，不能拿member_entries本金替代原标题积分。 |
| HK169 消费券统计 | 同会员卡本金不能产生coupon变动；需未来原购买／赠送／核销／原退的BenefitEntry(kind=coupon)与冻结rule/version/source。benefit_coupon张、占额和现金分别核，无跨店来源不声明集团全部消费。 |

**当前位置与下一步**：八项源码范围可交根登记独立作者；HK164/166随后可复用同五前序，不迫使本批增加链长。其余按上述原事实是否真的发生选择，尚未生成的前序等待。静态阅读不产生passed，必需负向／未知源与建议覆盖区分；不把条件未具备的分支静默算已验收。
