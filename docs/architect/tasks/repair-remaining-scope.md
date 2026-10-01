# 剩余维修、车辆与代办收款范围

2026-10-01，只读源码设计。HEAD `8993ca8c755194a42a48e7323fe355e80c6bf9ae`；原目录 SHA256 `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`。本页只新增范围说明，没有修改生产、候选、fixture、注册或实施计划，没有导入 app、启动实例、浏览器或测试。以下批次全部为建议，不能登记执行通过、人工验收或全 193 完成。目录题名与稳定 `HK-xxx-business` 保持。

| 原需求 | 必需完整行为 | 原入口与主要来源 |
| --- | --- | --- |
| HK035 保险理赔维修 | 当前维修行核价、不同主管批准、外部提交及补件／拒赔／部分核准事实、绑定冻结保险承担、对应实际款；核准不代到账。 | `#claims`、`#repair-orders/{id}`；`claims_service.py:168–231,280–325`、`repair_service.py:364–395,444–453`。 |
| HK036 厂家索赔维修 | 同一实际厂家、当前维修行及获准数量金额，从核价到独立复核、外部结果、冻结厂家承担和实际款。 | 同上；厂家必须为启用 `flow_references.category='厂家'`，不是供应商或保险公司。 |
| HK037 新车检测(PDI) | 已配同 VIN 当前签回版检查不合格、出库被阻、技师整改、同 VIN 复检合格；各轮检查、缺陷、凭据和任务独立。 | `#sales-order/{id}`；`flow_specs.py:182–191`、`flow_engine.py:856–870`、`sales_quote_service.py:156,182`。 |
| HK038 返修单 | 已接车原单的冻结责任行申请、不同主管批准、同客户身份／VIN 实际到店与新独立维修；原责任与新增自费逐行分开，不复制旧领料或现金。 | `#rework-extensions` → `#service-intake/reworks/{id}` → 原维修；`rework_extension_api.py:14–38,40–57`、`rework_extension_service.py:135–150,167–242,286–313`。 |
| HK039 保险账核价单 | insurer 的原 `ClaimAssessment/Approval/Transmission/Result` 当前版本、行数量、金额和额度一一对应，核价步骤不造现金。 | `#claims/{id}`；`claims_api.py:15–53,71–96`、`claims_models.py:24–84`。 |
| HK040 索赔账核价单 | manufacturer 的独立核价、批准、实际结果；新版不能借旧报价、旧复核或旧核赔结果。 | 同上，厂家身份单独核对。 |
| HK041 内部账核价单 | 明确实际内部主体，当前行核价、不同主管批准、绑定内部承担；不伪造外部提交、结果或 Cash。 | `party_type=internal/payment_route=internal`；`claims_service.py:178,218–226,296–300`，内部 `_allocation_due=0`。 |
| HK075 车辆销售收款 | 当前有效签回版分笔真实 receive，账户、日期、流水、文件、原 PaymentLink/Cash、累计与未收余额一致；原请求与重复风险分别留证。 | `#sales-order/{id}`；`POST /api/flow/cases/{id}/actions/receive`，`sales_quote_service.py:182`、`flow_engine.py` 原付款事务。 |
| HK076 代办服务收款 | 当前版 fee/pass 两桶真实到账及原本金代缴来源、对象、剩余分别核；履约和到账不是同一事实。 | `#service-order/{id}`；`service_orders_api.py:100–104`、原 `receive/disburse`；`ServiceTenderSlice/ServicePassEntry/PaymentLink/Cash`。 |
| HK078 整车收款单调整 | 已声明原误记、独立批准、按当前原款与来源版本追加冲正／正确重记，原退款及剩余分配守恒，不重交车。 | `#business-finance/{customer_id}` → `#business-finance-order/{id}`；原 `correction`，`business_finance_service.py:413–436,443–483,604–643`。 |
| HK081 维修收款单调整 | 另一份明确原 repair 现金误记按原路径追加更正；旧现金、原退款、施工、承担及正确有效余额保持。 | 同 HK078；不能把预收／续会更正或一次普通维修到账替代。 |

## 同轮有限前序

每条后继先核当前 `evidence_root/browser-click-report.json` 中固定前序实际 passed、原 checkpoint complete/passed、需求 check 完整及本轮 source/script/catalog/provenance。文件存在、上一 fresh 的成绩或当前目录状态都不是来源；缺固定父源立即明确失败，不能扫描旧业务默选。

- 首维修 `repair-selfpay-hk031-034-044-049-053-079/business-checkpoint.json` 的 `report_sources`：`customer_id/customer_vehicle_id/vin/appointment_id/intake_case_id/repair_case_id/quote_id/allocation_id/payment_link_id/cash_id/material_item_id`。只重读这些 ID 及其原关系。
- 洗车／快捷和 `repair-customer-reimbursement-hk042` 是独立父场景；后者成功输出 `claim_sources` 中原维修、报价、承担、PaymentLink/Cash、claim/assessment/transmission/result/approval/customer_payment ID。直接付客户不生门店 Cash，不可用其客户付款伪造保险到店。
- 同轮主档取 HK172 真实 insurer、HK175 WorkItem、HK184 材料仓／位；物资只用 `material_sources.primary/secondary` 的明确 `item_id/source_location_id/enrollment_id/receipt_ids/stock_move_ids`。当前 CV 版本、里程、实际来访／工位及物料余额已变，按稳定身份关系核并重新读当前版本，不要求旧整行／旧零库存相等。
- 整车交付父 `sales-order-hk008-009-011-022` 只有有限 `report_sources={lead_id,customer_id,delivered_order_id,delivered_vehicle_id}`，该 VIN 已交付不能重新检查或出库。另一可用车须取同轮采购实际 VIN，再核当前 Position/Custody/Hold／代次及取消单的释放事实；不存在可用源时先真实原采购，不能找 demo 车。
- 代办父 `sales-followon-hk012-015-016-017` 的 `report_sources.agency_case_id/agency_project_id/account_id/customer_id/delivered_order_id` 可给出当前真实款与版本来源。不得把厂家返款单 `manufacturer_income_case_id` 当成厂家维修核赔。

## 建议第一批：一张新维修上的五个核赔检查

HK035/036/039/040/041 可共享一张**新、未冻结承担**的 regular v4 原维修，逐项仍留独立 check 证据。已完成自费首单的 Settlement/Allocation 不可重分配。建议复用同客户/CV、明确空闲工位，原预约或现场登记 → 新 Arrival → convert → 新报价与不同主管 price_approve → 本版客户 authorize → 实际施工/质检；纯作业行可避免为核价再造库存，但不能继承已完成首单的施工。

三行合成作业各自有真实 WorkItem、已知数量与固定价格；例如 30/40/50 元总额 12000 分。行及金额在员工填写前明确，不从成本、保险额度或毛利倒推。insurer 对第一行初版核价：上传各次不同内容的 authorization 原件，approve → transmit → `need_documents(lines=[])` → 引用本次 `supplement_result_id` 补件 → `rejected(lines=[])`，再建立独立第二版 assessment/approve/transmit → 当前 `partial` 20 元；旧两版核价／提交／结果完整保留。manufacturer 对第二行独立核价和 approved 40 元；internal 第三行独立核价 50 元，直接进入 ready，**没有** Transmission/Result。

核价阶段不得生成 Cash/Payment。主管在维修原表单 allocate 冻结客户 10、保险 20、厂家 40、内部 50 元，合计 120 元；同类只能一行。`claims_service.validate_allocation` 要求各核赔单位及金额恰等当前获准结果。原 `_allocate` 同事务 `bind_after_allocation` 会创建各 ClaimBinding；应核此真实绑定，不为补点击重复执行 bind。财务按 `repair_receive_{allocation_id}` 本人任务分别收客户／保险／厂家原款；每笔有新 receipt 原件、原账户与流水、RepairPayment→PaymentLink→Cash。内部承担只留 Allocation，绝不收内部现金。保险／厂家欠额为零由 `sync_source` 实际关闭对应核赔；客户接车另点 release，工位、到离场、现金和原任务各自核对。

此批原 API：`POST /api/claims` 为 `{request_id,source_case_id,source_version,party_type,payment_route,payer_id,payer_name,reason}`；命令为 `{request_id,version,source_version,values}`。Assessment 行 `line_id/quantity_milli/amount_cents`；Result 再带 `transmission_id/outcome/result_on/result/evidence_id`，数量金额不得超原行／申请限额。所有日期按 Asia/Shanghai；结果日在提交日至业务今天之间。

前置仅需现 service、不同 manager、technician、finance；库存若无配件可不新增领料。厂家必须先从原 `#master/references` UI 建立本店 `category=厂家` 真实启用档案并保存有限 ID；HK170 只生成“公共字典”，其 row 不能冒充厂家。现保险主档可复用。外部提交号／文件只能声明合成流程事实，不称真实保险公司或厂家确认；结构检查不称 ClamAV 验收。

## 建议第二批：同店原责任与新增自费返修

原 `#service-intake/reworks` 首版 `ReworkRequest` 只能全额内部责任；`service_intake_service.py:367–376` 明确拒绝把该首版转成新增客户收费。为满足目录原责任／新增自费分行，走已有 `#rework-extensions`，不改原规则。`targets` 会枚举包括当前店的同 VIN、customer_identity_id、vehicle_identity_id 客车与 ADVISE 接收人，所以本店原 service/CV 即可，不为此强建跨店关系或 fixture。

service 依据已实际接车首单最终 Settlement.quote_id 的明确原责任 Work 行，在原维修上传本次责任原件；UI 指定当前店、同 CV、原 service 接收人、明确责任限额、含时区且九十天内 expires_at → 原 `POST /api/rework-extensions/grants`。不同 manager `approve`；指定 service 原 UI `requests` 接受 → 本店不同 manager 原 rework `approve` → service 重填同 VIN、非回退里程和本次到店凭据 `convert`，产生唯一新 Repair Case/Arrival。不能只拿申请或授权当到店。

原 `/api/rework-extensions/orders/{repair_id}/quote` 与 `web/reworkextensions.js:31–41` 提供逐行 `charge_scope=original_liability/customer_extra` 和 `source_line_id`。至少一条引用获准原责任行、另一条新增已知作业自费；原责任数量／项目／金额不超冻结授权，新增自费不带原 source_line_id，不能换授权后旧行类别。原报价独立批准、客户本版授权、技师实际工位与施工、独立质量、allocate 内部责任／客户新增金额、财务只收新增自费、service release。完整比对 ReworkGrant/Decision/Extension/SourceLine/QuoteScope/LineScope/Liability/RepairQuote/Authorization/Settlement/Allocation、ResourceUse、Arrival、原成本及新资金；旧单 Quote/StockMove/Payment/Cash/历史原件均不复制或改写。跨店原授权、撤销、延期及客户停工分支本批未测。

## 建议第三批：PDI、车辆收款与代办收款

HK037 应新建原报价车辆订单或在同轮明确未 PDI 的新订单继续，不能对已交付 VIN 再写 inspect。原本版签回和配车后 service `inspect(outcome='不合格')`，真实 inspection 文件与发现 → 原 dispatch 不可办理／原服务拒绝且零业务变化 → 当前 technician `rectify` 留结果 → service `reinspect(outcome='合格')` 同 VIN。`flow_engine` 冻结 inspection.round/vehicle_id，新增 rectify/reinspect 任务；原整改不是加装 quality 检查，HK014 的不合格复检不能映射 HK037。

该新订单同时做 HK075：财务两个明确实际款分笔 receive，核原当前 quote/客户签回、PaymentLink/Cash/账户/独立流水、累计余额以及每笔当前版本/请求回执。刷新和按钮忙保护只能证明 UI 不二记；没有真实同 request_id 重复提交证据时，后台重复请求分支仍未测，不用正向 API 回放伪造点击。资金齐全、合格 PDI、库管实际出库和销售本版提车若作为本批终态，各自留事实，不以终态抹掉中间未收与不合格阶段。

HK076 原代办父已通过时可在**本次重新执行的完整父链**登记精确映射，而非重复收一笔钱：第二版 quote fee=2500/pass=1000，真实 receive=3500，Tender 按桶分开；pass Tender 对同 payee 的原 disburse=1000 与独立 Cash(out)；原履约/受理/补件/结果保留。现 `sales_followon_business.py:810–852` 已有对应原点击与逐分来源。若未来单独候选不依赖完整父执行，则须另建原代办并完整报价/独立批准/客户授权/办理/原到账/代缴，不能拿历史 API GET 或 fulfill 计收款完成。

## 建议第四批：两类原收款误记更正

HK078/081 共用原 business-finance 服务，但各用独立车辆／维修原 Cash。必须**先明确合成正确依据与实际误录**，例如本次有凭据支持的流水号被员工录错，再通过原 UI 新增 correction；不能事后给一笔正确账编理由。金额同额、账户同店也可验证真实追加更正，不必故意超收或制造退款。原业务来源须无阻止调整的已批准占额／售后／报销冲突。

原 Create 值为 `original_cash_id/amount_cents/account_id/reference/allocations[{source_case_id,amount_cents}]/allocation_basis='remaining_after_refunds'/actual_business_date`；批准与执行分别用当前 FinanceOrder/Case CAS，执行的 `source_versions` 取全部有限 affected 原单当前版本。独立 manager 审核原误记及正确凭据，finance 本人执行。原服务追加 Cash(out)＋反向 Batch／关联原 PaymentLink、Cash(in)＋正确 Batch／正确分配、FinanceCorrection；保留原 Cash 和原退款，账户／日期／流水符合冻结正确依据。不是实际给客户退款，不重施工或交车。

已实退分支必须用原 `FinanceCorrectionBasis/Refund` 的有限真实来源；`remaining_after_refunds` 把原退款金额加入正确总原款，剩余分配必须守恒。没有真实退款时保留该分支未测，不以空退款表给通过。更正后 `business_finance_sources.sync_source` 可能将原完成 repair 变为 credit_open 或结清，应按真实未收与版本核，不强断言所有原 Case 状态不变；RepairPayment/Invoice/积分联动只允许原事务实际触碰的有限来源，其他旧行保持。

首维修实际客户款已用于 HK042 客户直接报销时，`claims_service.py:136–139` 以 `_reimbursement_usage>0` 拒绝现金更正；即使 claim completed 也不能绕开。因此优先用新无报销的原 selfpay 单并预先声明凭证误录，或在另精确批先完成获准的原路径返还；不得删除 ClaimCustomerPayment、改报销状态、借 admin 或碰原已正确付款。车辆原款若已有已退款切片，也保留原账户和事实，不调用新的 refund 凑守恒。

## 守卫、体验和实施边界

复用 `repair_business.Guard/command/upload`、`repair_followon` 原 claim helper、`sales_order` 原登录/签回/物理事实 helper、`sales_followon` 原 fee/pass command 和 `finance_business` 原表单/回执 helper；先核当前实际签名，不复制通用框架、不改注册 helper。每次真实登录／读取完成后建立基线；正写全为原 UI。每动作只允许本单、明确源 Case/CV/工位/Task、原受影响 Payment/Allocation/Member 等有限 ID 和列，其余所有旧业务／他店／旧资金／库存／会员／不可变历史保持；计数不足以替代旧行哈希。所有文件报告只存实际字节长度／SHA/security 元数据，不能把 BLOB 存进 checkpoint。

真正难点是两个源版本同时变化、不同主管及当前 Task 本人、同 VIN 实际到店无重叠、授权/核价版本冻结、原证据不能复用相同字节确认不同事实、原责任与新增自费限制、实退切片/报销占额/原成本以及真实外部结果边界。只修真实执行发现的产品接线或脚本时序，停止关联进程、先登记精确补丁；不降 CAS、不自动换 request_id 重放、失败保留原件。

建议先核赔五项，再同店返修，随后整车 PDI/收款与两类更正；HK076 优先使用同轮真实完整代办源作精确映射，避免额外资金操作。后继 checkpoint 每项独立 check、当前动作/请求/DB/旧行保护与明确未测条件，真实异常立即 failed；局部通过不能拼成整轮通过。前端显示、流程简易、文案简洁、后端匹配、硬 bug、来源完整六类分别记录，截图只能辅助，人工仍待指定员工观察；本页不修改目录或任何通过计数。
