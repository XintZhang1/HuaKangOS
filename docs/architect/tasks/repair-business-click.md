# 维修原业务浏览器链：独立候选

2026-10-01 根接线实测追加：冻结018051e…短审无确定合同误配后注册。automatic-business06完整23项执行22通过/维修失败，维修到139动作/66点击（预约、实际到店、转换、提醒、报价、核价、授权、开工与首次领料原API已有事实），记录first_issue时原FileAsset.content的bytes无法JSON保存。原磁盘checkpoint保留HK031/HK044局部passed及running；整维修场景failed，聚合不提交这两个局部check，整轮只有60项自动完整检查。失败保存也被该对象污染，不改旧文件补写假结果。停库只读确认实际blob167字节且SHA匹配，本错误为证据装置问题。

根最小修复：上传仍用原文件和API验证，只将报告返回的content替为实际字节长度及SHA；完整bytes保留Guard内存旧行保护，正业务数据库不改。checkpoint.note先确认待合并证据可序列化再更新，以免证据错误掩盖原失败。business-repair01现在全新镜像运行采购/主档/客服/物资/维修五前序，尚无完整结果。原失败与不同指纹定向结果独立，不称维修通过、联合23通过或193完整验收。

2026-10-01，最初仅获只读研究授权，以下保留该阶段的来源设计和验收边界。随后负责人登记 PATCH-M8-4-BUSINESS-193-08，授权只新增维修候选并维护本页；候选实施记录见页末。生产、fixture、共享 runner/scenarios、目录及已注册候选仍由负责人或原作者控制，本页不是业务通过报告。

## 首个可执行增量

建议先做一个普通自费维修输入到结果场景，逐项核对 `HK-031-business`、`HK-034-business`、`HK-044-business`、`HK-049-business`、`HK-053-business`、`HK-079-business`。共用一张本次预约和关联维修，但每项保存自己的真实操作、响应、任务、不可变记录与只读数据库证据。预约和提醒不因后续维修完成自动通过；现金不因结算或接车通过。

建议候选名 `repair-selfpay-hk031-034-044-049-053-079`，入口沿现有 Evidence 小型 helper，函数签名 `(e, context, credentials)`，有限 timeout 暂建议 300 秒。实际耗时尚未运行，不能承诺通过或反复重跑求绿。脚本未获写入窗口；负责人登记补丁并授权后再新增独立 `tests/browser_click/repair_business.py`，不搭共享框架。

## 固定同次前序

只读当前 `e.manifest.evidence_root` 下的 `browser-click-report.json` 和明确依赖的 checkpoint。父 runner 必须记对应场景 passed，同一 run 根、源码/脚本 provenance、目录指纹一致；checkpoint 对应 check 已完整通过或具备明确的本店子来源通过合同。只从这些固定文件取有限 ID，再 SELECT 核对当前原事实；缺依赖时明确失败，不扫描全库挑新单，不跨 fresh 复用旧 ID。

| 来源 | 必须取的事实 | 本批不允许替代 |
| --- | --- | --- |
| `customer-service-hk098-107-108-109/business-checkpoint.json` | `partial_requirements` 中 HK-099 的 `local_scope_status=local_scope_passed`、`evidence.vehicle` 完整 `care_customer_vehicles` 行；`observations` 中 original_form/observation；identity_link、vehicle_identity、original_consultation_history。客户 ID 为 vehicle.customer_id，再按该 ID 查询原客户。父场景完整四项必须 passed。 | 本店车辆子来源不是完整 HK-099 业务验收；不从售前客户或整车新库存推断已建立客户车辆关系。不得更改原咨询历史。 |
| `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187/business-checkpoint.json` | HK-175 原 UI 维护的 active WorkItem，核实际单位/标准费用/版本；HK-183 的 `acceptance_checks[0].evidence.item`、profile；HK-184 的 evidence.warehouse.row/location.row，必须 materials 仓、active 原库位。 | 主档初始零库存不是维修可领料，ItemProfile 的位置不是 WarehouseEnrollment，也不是实际库位余额。班组存在不表示原技师已接手维修任务。 |
| 待完成的同次物资原采购 checkpoint | 明确的 Item/Enrollment/库位及采购验收 Receipt、StockMove、WarehouseAllocation/Entry 来源 ID。实际原库管分配位置，主管批准启用；正余额来自采购真实 receive。后继 SELECT 核当前可用量和库存价值。 | 不继承 demo 余额，不填期初正余额，不直接改 Item/Balance；后续采购、盘点、移库已经改变版本时，不再要求主档行仍为初始零库存。 |

维修依赖 **原物资采购先成功**，仅创建物资仓、物资或库位还不足。物资作者已确认：零数量 activate 也须至少一个真实 location；之后 procurement receive 才能产生 StockMove/库位 Entry 和维修所需正余额。采购付款与物料收货分别留证；维修只读取已真实验收的数量和原成本，不能把申请付款当入库。

物资作者当前只读设计拟输出顶层 `material_sources.primary/secondary`：item_id/sku/name/unit、warehouse_id/location_ids/enrollment_id、purchase_order_id/receipt_ids/stock_move_ids。primary 为本轮 HK183 的“升”Item；完整物资设计即便执行退采购、盘点和跨店发运后仍计划留足净领1.250升的数量。此合同尚未编写/注册/运行，维修依赖必须等实际 checkpoint 的当前剩余可用量，不把拟定“6升”当库事实。

## 最小身份及夹具合同建议

已有本店 `service`、`manager`、`inventory`、`finance` 随机登录可复用。只需新增 **store 1 的启用 technician User/UserStore 及外置随机密码**，不需要为本首链新增 customer_service 身份，也不预置预约、工位、维修、授权、物料或现金结果。建议 `business_fixtures.repair={store_id:1,service_key:'service',manager_key:'manager',inventory_key:'inventory',finance_key:'finance',technician_key:'technician'}`；由负责人登记后交 fixture 作者实施，本页不修改 fixture。

原 `ensure_task` 按启用岗位的未结任务负载/ID 分派，不保证新随机员工被自动选中。每一步核实际 assignee；若分给不可登录 demo 员工，由 manager 在该原单的“岗位交接”真实选择可登录同岗位员工，提交 `/api/flow/tasks/{task_id}/assign` 的原 version/assignee_id/reason。不能借 admin 办理或数据库改负责人。技师可读价格受原 MONEY_ROLES 限制，成本核对使用 manager/finance 的原响应及 SELECT；不要求技师页面暴露金额。

| 原动作 | 当前门店岗位与原任务 |
| --- | --- |
| resource / preset 新建、配置启停 | manager；由本次原 UI 产生工位，不使用 fixture 结果。 |
| book/reschedule/arrive | service；FRONT 也允许 reception/customer_service，但其客户范围不同，不替换当前 service 链。arrive 必须 intake_arrive 当前负责人。 |
| convert / quote / authorize / quality / release | service；intake_convert、repair_quote、repair_authorize_{quote_id}、repair_quality、repair_release 按实际任务核对。 |
| price_approve / allocate | manager，报价人和审批人独立。allocate 冻结当前已合格报价的一次承担。 |
| start / finish | technician；repair_work 本人办理。start 同事务真实占用工位。 |
| issue / return_material、原实际库位准备 | inventory；issue 必须 repair_issue 当前负责人；退料必须原 RepairStock，本单且不是一条退料。 |
| receive | finance；repair_receive_{allocation_id} 本人办理，实际账户、凭据和流水由原 UI 明确选择/输入。 |

## 首条原 UI 顺序与判据

所有正向写入从原页面表单实际点击提交；原网络响应、Cookie/CSRF/当前店/version/request_id 摘要及只读 DB 事实留证，不使用正向 API 写、不注入 state/fetch 或隐藏 select，不预填应由员工点击产生的结果。

1. **工位**：manager 打开 `#service-intake/resources`，点击 `[data-act=intake-resource-new]`。“新增服务工位”填 code/name/type=维修，原 POST `/api/service-intake/resources`；SELECT `intake_resources` 核类型 repair、active、无 active_case_id。普通首链不需 QuickPreset。
2. **预约**：service 打开 `#service-intake/appointments`，点击 `[data-act=intake-new][data-mode=appointment]`；可见真实客户车辆候选含姓名/电话/车牌/VIN，明确选本次 CV；resource_id 选新工位，明确计划开始/结束与诉求，点击“保存接待安排”。原 POST `/api/service-intake/appointments` 生成 ServiceAppointment + service_intake Case + intake_arrive Task + intake_book Event；不生成 RepairStock/Cash、也不占用工位。预约开始必须未来、时段至多12小时；时间由本页面 datetime-local 和业务时区核对，不用 host date.today()。
3. **改约与实际到店**：在同 `#service-intake/appointments/{id}` 点 `[data-act=intake-action][data-key=reschedule]`，明确一个新的未来时段；保存后核新时段/原 id/任务日期和追加 intake_reschedule。随后上传本次合成现场凭据（evidence 类别，原扫描 can_use），实际“记录实际到店”填本 CV 的逐位 VIN/本批明确的现场里程，原 `/actions/arrive`。核唯一 `intake_arrivals`、actor/evidence/CV/VIN/里程、status arrived、intake_arrive done、intake_convert open。`gate_attendance.arrive_guard` 在本事务锁 VIN 和核原进出厂区间；**不另造 GateVisit 再记重复进厂**。原单已有独立进厂来源时必须先从原 UI 核对/交接，不能绕过。
4. **维修明细**：service “建立本次维修明细”填交接日期，原 `/actions/convert`；Appointment 唯一 repair_case_id，status converted；新 `flow_cases.kind=repair,flow_version=4,state=assessment`，`intake_repair_contexts.profile=regular`、`intake_vehicle_bindings` 同 CV/customer/vehicle identity/VIN/到店凭据、追加 model_snapshot 和 intake_convert，原接待任务结束。实际点击“办理维修明细工单”进入 `#repair-orders/{case_id}`。
5. **维修提醒 HK044**：在一个原开放待办阶段，由真实负责人进入 `#work/repair`，点击 `[data-mux-due=today]` 或与 DB 一致的 overdue，保持 scope=mine/status=open。原 GET `/api/flow/tasks?...area=repair&due=...` 的目标 Task 与本单 number/title、assignee、due_date/status 一致且页面非空；实际点目标行“接着办理”进入同维修原单。不能只保存计划日期或读通知算提醒，不能把多个模块的同 Task 相加。
6. **报价**：service 点击 `[data-act=repair-action][data-key=quote]`。原 `[data-repair-line]` 通过可见 source 候选分别选当次 WorkItem 和已采购 Item，数量/单价/优惠/原因明确输入；按钮“提交本版本价格审批”。原 `/api/repair-orders/{id}/actions/quote` 携带 version/request_id/values，金额整数分、数量整数千分位。SELECT `repair_quotes/repair_lines` 核 source/code/name/unit/line_key/qty/price/gross/discount/digest，本版唯一且客户、到店和已采购原料不变。建议 part=1.250 升、折扣0，单价为本批明确合成报价输入；成本仍来自采购，不从售价推断。
7. **价格与授权**：另一 manager “主管价格授权”，明确最低金额、例外开关 false、原因，原 price_approve，核 RepairPriceApproval actor != Quote.created_by、报价不被覆盖。service 上传本版不同字节的 authorization，原 authorize 绑定 quote_id/digest/evidence，核 authorized_quote_id、RepairAuthorization、repair_work open。上传并不等于授权，重新上传同字节不代替新版客户授权。
8. **开工与原领退料**：技师确认“本人实际办理情况”后 start；核 started + start_result、ResourceUse acquire、工位 active_case_id=本维修。库管 issue 表单选择当前授权 part 行/数量1.250、实际凭据，点 `[data-prep-open]`，选本次真实材料仓位并填1.250，`[data-prep-save]` 原 POST `/api/warehouse/allocations/{case_id}` purpose repair_issue_v3、quantity -1250；只生成准备，尚未减库存。最终“确认本人办理”才原 issue，生成 RepairStock qty1250/value 原成本、StockMove -1250/-value、WarehouseAllocation consumed 与 Entry；余量精确减少。
9. **退料 HK049**：在结算冻结前，从该原 RepairStock 的可见候选选“原领料退回”，实退0.250/凭据/接收位置。原 inline 保存 purpose repair_return_v3 quantity +250；return_material 的 original_id 为原 RepairStock（不是原 StockMove）。核退料 RepairStock.original_id、qty -250/value负；新 StockMove original_id 引原 issue StockMove，qty/value正；Entry 同量值恢复，累计实退不越原批。随后再次真实 issue0.250，使本行净领1250后继续完工。此路径保留原授权量、不删旧领退事实、不猜成本、不用退料后净领不足的状态跳过 finish 守卫。
10. **施工及质检**：technician “提交施工结果” finish，原 task done/state quality；service 上传 inspection 质检凭据、quality 选合格并填真实合成检测结果，核 RepairQuality.quote_id 当前授权版本、actor/evidence、state settling、repair_allocate open。本首链不宣称“不合格—整改—复检”也通过。
11. **承担与现金**：manager 原“确认费用承担”点击 `[data-repair-customer-all]`，当前授权合计全由真实原客户承担，人工成本填写本批预先明确的合成现场事实（无此事实不得估计）；保存承担确认凭据。核一次 RepairSettlement、单 customer RepairAllocation、合计等报价、due_date、Case.cost_cents=明确人工成本+实际净领料价值、原 cash 尚无。finance 对该 allocation 原 receive 实际选 active 原账户、金额、独立流水和 evidence；核 RepairPayment→原 PaymentLink→CashEntry、in/同店/同客户/本单金额一次到账、due0，不能把 allocate 当已付。
12. **客户接车**：service 原 release 的实际凭据/点击产生 released_date、唯一 repair_v4_release 事件、Task done；原 departure_guard 核对应实际到店区间，工位由 ResourceUse release 真实释放。核本单 completed（纯自费已清）、completed_date、无未结任务、两类事实仍独立：现金来自 receive，出厂来自 release。刷新原页并只读重验，不重复材料或现金。

原字段/选择器基于 `web/serviceintake.js`、`web/repair.js`、`web/warehouseprep.js`。formDialog 原最终按钮沿现有“确认本人办理”合同；动态候选和重渲染后 Locator 重新解析，不缓存候选 ID/nth-child，不 force/trial、sleep 或重试写。

## 首链定向异常与统一评分

- 到店表使用一个合法17位但不相符 VIN，真实原提交预计409（不是采购收车422）；保存服务真实 refusal 与全原业务摘要 unchanged。随后按原 dirty guard 明确“放弃填写”、重新打开并现场核对正确 VIN。错误请求不自动重放。
- 原新时段在新工位重叠另一个预约的409可作为 HK031 分支，但必须实际创建那条预约并从原 UI 取消收尾；不为首链凑数据。未执行则 not_tested，不能继承源码守卫成绩。
- arrive 前不能提前 convert；未当前版本授权不能开工/领料；净领不足不能 finish；未结清客户款不能 release。记录实际可见门槛及本批必要的一次真实拒绝，不强造所有分支、不能从按钮隐藏声称后端全部负例通过。
- 存在原版本冲突时保留409/原 request_id/业务 unchanged，先员工刷新核对。未知结果立即停止，不换 request_id 重放，不循环求绿。
- 每项自动 hard gates：原 UI 可见可操作、原响应成功/真实拒绝、原数据关联/数量金额成本/状态任务一致、追加历史不丢、同店本人权限、无重复业务、无硬性错误。失败当前项 terminal failed；未完成项 not_tested/partial，不能留 running 或归错项。
- 人工体验、流程简单、文案简洁继续 human_pending；保存 actions/click count/截图给人工审阅，不伪造效率提高20%。本店合成文件只有原 structure-only 检查记录，不冒充 ClamAV、真实客户授权、生产现场施工、银行到账或员工试用；`business_accepted=false/full_193_business_acceptance=false`。

## 其余请求项各自需要的增量

下表所有项仅 source-reviewed、not_tested。不能凭第一张维修单或进入共享页面记 passed。

| 需求 / 精确 check_id | 独立原链及来源 | 本轮首链边界 |
| --- | --- | --- |
| HK032 洗车开单 / HK-032-business；HK080 洗车收款 / HK-080-business | manager 原 resources 建 wash 工位、QuickPreset profile wash/实际 WorkItem/数量；service 新预约→独立 arrive→convert 产生 profile wash/预填 Quote。之后独立主管核价、当前版授权、tech施工、质检/承担、finance原到账、release。 | 普通 profile regular 不覆盖。可在首单已 release 后用同 CV 原 UI 新建，不重复开区间；物料不必强添。 |
| HK033 快捷开单 / HK-033-business | 新 QuickPreset profile quick/同 WorkItem版本和qty，repair 工位；独立到店/convert 唯一 RepairIntake/Quote/Line，再完整授权施工收款接车。 | 一次普通报价不能代替原预设转单；需另张实际 quick 单。 |
| HK035 保险理赔维修 / HK-035-business；HK039 保险账核价单 / HK-039-business | 已报价但未冻承担的 repair，原本店 insurer（可复用本次 HK172 master）；service 从原维修申请 claims，party insurer/route repair_receivable。原 assess 当前 Quote/Line→另一 manager approve→实际合成外部 transmit/result（各次不同新原件）→原 repair allocation 对应额度→bind→finance 原实际款。ClaimAssessment/Approval/Transmission/Result/Binding 与 RepairAllocation/Payment 分开。 | 首单全额客户承担后不能覆盖冻结承担来冒充保险链；新增原维修分支。批准与外部结果都不是到账。 |
| HK036 厂家索赔维修 / HK-036-business；HK040 索赔账核价单 / HK-040-business | 原本店 active Reference.category=厂家，需要原主档 UI 明确创建/维护；另一原维修 party manufacturer/route repair_receivable，同核损/独立批准/外部结果/承担/到账链。 | 不用保险公司或任意数字代厂家，缺来源明确待前置。 |
| HK041 内部账核价单 / HK-041-business | party internal 必须 route internal/明确实际合成承担主体；service assess、独立 manager approve 直接 ready、原 repair internal allocation/bind。 | 不造外部 Transmission/Result，也不能为 internal 生成现金。须在另一未冻承担的原维修办理。 |
| HK042 客户报销结算 / HK-042-business | 可复用首单真实客户自付；新增 claim party insurer 或 manufacturer，route customer_direct 或 customer_via_store。原核价/外部结果→另一 manager reimbursement_approve；finance direct_confirm 记录客户直接收款事实（不是门店 Cash），或 pass_receive→引用本次原到账的 pass_pay。额度不越客户真实自付，原 RepairPayment 保留。 | 最小先选一条明确合成客户直收路线；代收转付与各类原返还另有独立资金条件，未执行保留 not_tested。每事实凭据字节不同，不能复用文件作不同实际结果。 |
| HK038 返修单 / HK-038-business | 必须首单已实际 release、最终结算 Quote/责任 Line、同 customer/VIN/identity；service 原 ReworkRequest→不同 manager approve/internal责任→现场 VIN/里程/新凭据 convert 新 repair；原款领料保留，新单另行施工结算。当前 catalog 同时要求原责任与新增自费分行：要用现有 `#rework-extensions` 原 SourceGrant（原店独立批准/指定真实 recipient 接收）及 ReworkQuoteScope/LineScope，而不是把基础“全额内部责任返修”改成自费。 | 最小基本返修仍不足以冒充 catalog 全合同；精确补丁应登记 extension 子链。同店也能出现在 targets，读取真实 target/CV/员工，不需要为它伪造跨店同车关系。 |
| HK081 维修收款单调整 / HK-081-business | 依首单 RepairPayment/PaymentLink/Cash 原款，finance 原 `#business-finance/{customer_id}` 的“更正业务收款”创建 purpose correction，明确查明错误/正确账户日期流水、remaining_after_refunds 逐原单分配；另一 manager approve、finance execute。原 `business_finance_corrections/bases/refund_slices` 与新 Cash/PaymentLink，保留旧现金和有效已退。 | 更正是追加误记冲正/正确重记，不是退款也不重新施工。需先声明一个合成录入错误作为员工输入，不能将全部正确现金无理由“纠正”；若已退分支未发生，不称该分支通过。 |

首链之后建议按 quick/wash 两单 → 原已交付客户报销/原款更正 → 保险/厂家/internal 明确承担维修 → 原责任与新增自费返修分批登记。范围中未执行条件继续保留，任何阶段不宣称所有17项或完整193验收通过。

## 静态来源与指纹

本次只读 HEAD `5069b2bcc9f580ebb9d70780769049a14a6de946`，共享工作树存在负责人/其它作者未提交修改，HEAD 不是完整测试指纹。本页没有启动 app/测试或导入 app。源合同已按原 workflow manual、实际 JS 表单、Pydantic、service 状态机与模型表交叉核对：

| 文件 | SHA-256 |
| --- | --- |
| tests/browser_click/business_acceptance_catalog.json | eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff |
| app/repair_service.py | ab51e9b2874b5f0bb44750c15c71d4c0622f4ff6130f27a0ea7da2db45cab4c4 |
| web/repair.js | 97edfa86f503d54c5d9262352282a350b511e65d3ad8c51c2f5dba008b2985ea |
| app/service_intake_service.py | 6752792d72efb211be1d407e9d5c3c44dc301fde6d6ef94c16b5931affc551f6 |
| web/serviceintake.js | 0a68de52f885dc8589ec84c0c695f95358e1a76a9c4be305a6847291ef245f41 |
| app/warehouse_stock.py | 5181e6c6a610cdf5cf2ffbdb1c14ffe8e1f7d8680534ba8b08de44b6fc80c302 |
| web/warehouseprep.js | b66abd77482b563049a8b66318e5e1e0e99a540aeaee0d53a3c992529a8a6525 |

待负责人下一补丁明确：新独立维修候选/本页、最小 technician 凭据/原 UserStore 夹具、runner 注册与当前物资 checkpoint 名及有限输出键；不要求生产变更。实际失败若发现生产接线缺口，先保存该轮证据、收尾进程，再登记针对性补丁，不能由设计预设生产缺陷或降低原合同。

## PATCH-M8-4-BUSINESS-193-08 候选实施

2026-10-01，已新增 `tests/browser_click/repair_business.py`，导出 `SCENARIO='repair-selfpay-hk031-034-044-049-053-079'`、`repair_business(e, context, credentials)` 及 `REPAIR_SCENARIOS=((SCENARIO, repair_business, 300),)`。候选未注册、未执行；本节不继承此前客服、材料或维修源码的通过成绩。负责人已另行建立 technician 原 User/UserStore 与外置随机凭据，精确角色合同为前述 `business_fixtures.repair` 六键（店与五个本人岗位），候选不修改夹具、不预造业务结果。

实际代码只从当前 `evidence_root/browser-click-report.json` 中确认三个固定父场景均 passed，再读取该同目录下各自 `business-checkpoint.json`：客服 `customer-service-hk098-107-108-109`、主档 `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187`、材料 `materials-hk069-045-054-083-070-072-073-051-061`。父检查点必须 complete/passed、完整主检查均 passed、目录 SHA 一致；若原报告声明 provenance，必须与本轮 origin/source/runtime/evidence/database 完全一致。另核本次 `provenance.json.snapshot_stable` 与维修、客服、主档、材料、共用三个 helper 和目录的实际镜像脚本哈希。缺来源时失败并保存检查点，不扫描旧实例或全库挑单。

材料合同已按作者落盘接口接线：`material_sources.primary` 提供 item_id/sku/name/unit/store_id/warehouse_id/location_ids/**source_location_id**/enrollment_id/purchase_order_id/receipt_ids/stock_move_ids 等有限原 ID；维修只选明确 `source_location_id`，不猜数组第一位。SELECT 重验本轮 HK183 的同 Item、原 Enrollment、materials 仓、启用原位置、当前该位及全店余额、原本次采购 Receipt/正 StockMove；后继已经改变的数量和版本不要求仍等于主档零库存。材料场景尚未在同轮 passed 时，此候选不能继续。

六项实现各有原需求检查、状态和证据：HK031 工位/预约/改约/到店/唯一转换及错误 VIN 409；HK044 原本人今天未结维修任务、真实筛选和点击进入同原单；HK034 冻结逐行报价摘要、独立主管核价、客户明确授权、技师开工/施工、质检、承担和最终接车；HK053 当前授权的两次原领料与净量；HK049 引本次原 RepairStock 的实际退回；HK079 原承担对应唯一 RepairPayment/PaymentLink/Cash，接车前已到账但尚未离场。员工输入事先明确为 part 单价8020分、授权1250千分量、现场里程32100公里、人工成本1234分；成本按原真实采购余额与原批计算，不能从配件报价猜成本。

每次正向提交和库位准备均有全原业务摘要与有限行保护：无关表须完全不变；允许表的全部旧行逐列比较，只有当前原 Case/Task、预约、工位、VIN 版本锁、实际 Item/Balance、本单位置准备和明确收款账户的源合同列可变。新增原事实核本店、原单、办理人、物资、客户车辆、工位、报价及流水关联；旧报价、授权、材料、现金、会员与其他门店行不能借表级放行而被覆盖。授权时原服务确实创建一个无会员/无规则的 `membership_points_claims` 来源，单独核 null 规则与零奖励；本链只接普通非会员客户，不声称会员奖励流程通过。位置准备只产生 prepared 原来源，Item/Balance/StockMove/Entry 必须保持不变，最终实际收发才消耗它。

外部 `business-checkpoint.json` 逐项保存 check_id、criterion、实际 UI/API/DB、动作区间、源保护及截图。失败归当前需求；先前仅开始而未完成的项改为 partial，未执行项 not_tested，不残留 running。最终仅六项实际完整通过才 complete/passed，输出有限 `report_sources={customer_id,customer_vehicle_id,vin,appointment_id,intake_case_id,repair_case_id,quote_id,allocation_id,payment_link_id,cash_id,material_item_id}`，供同轮后继按 ID 重验，不输出凭据密码。

边界保持：人工流程与文案为 pending，business_accepted/full_193_business_acceptance/full_registered_suite_complete 均 false；合成结构检查不代表 ClamAV、真实施工/客户授权/银行到账或生产经营主体验收。洗车/快捷/索赔/报销/返修/原收款调整、不合格整改复检、原预约重叠/未到、已结算退料及额外角色异常仍按原目录未执行条件记录，不能把首六项映射扩算为17项或193项通过。

静态检查仅解析 Python AST、核导出签名、正向 submit 保护参数与文件空白、只读对照原 JS/API/service/model；未导入 app、启动服务、浏览器或测试。当前候选实际可执行性和动态页面时序仍须负责人隔离联合实测确认，失败原件保留后再精确修复。
