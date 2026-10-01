# 单店仓储八项原业务点击候选

2026-10-01，依据 `PATCH-M8-4-BUSINESS-193-21.md` 及已冻结 `inventory-next-scope.md`（`35bc5eaa05359f0c3cf54344a0e6a7802e63e78ac9de388afe4dcaf341496c8e`）。当前 HEAD `8993ca8c755194a42a48e7323fe355e80c6bf9ae`，实际未提交源码另有根代理维护；本作者只写本页和 `tests/browser_click/warehouse_operations_business.py`。未注册、未运行、不启动或导入业务应用、不改生产、夹具、runner、计划和其他候选。静态实现不是八项通过，人工六类评价统一 pending，`business_accepted=false`、193 全验收 false。脚本及本页最终 SHA 在冻结交接报告，避免自引用。

## 完整候选与原输入结果

场景 `warehouse-original-flows-hk046-056-048-059-050-057-060-085`，导出 `WAREHOUSE_OPERATIONS_SCENARIOS` 与统一原入口相同的 `(name, coroutine, timeout_seconds)` 三元组，固定有限超时720秒；共八个唯一 `HK-xxx-business`，原标题和 check 绑定从本轮原目录验证。沿原 Evidence/per-check checkpoint，无新平台或外部业务 HTTP 写入。原单位数量为整数千分之一，金额为整数分。

| 原需求 | 本次真实原页面办理与必须结果 |
| --- | --- |
| HK046 物资其它入库 | 库管从原 `#master/items` 新增耗材和礼品，两者账面数量、成本均零。分别原 `activate` 明确 `locations:[{location_id,quantity_milli:0}]`，另一主管批准原 Enrollment；零启用没有 StockMove/Entry。耗材 `other_in` 4000 milli / 批准 1600 分，礼品 2000 milli / 批准 600 分，库管原 execute 才增加量值及真实位置。 |
| HK056 耗材领用出库 | 耗材源位 `consumable` 1000 milli，明确合成维修班组。另一主管批准预占1000，库管实际 execute 原 StockMove −1000/−400、Entry同值，批准与实物分开。 |
| HK048 耗材领用退回 | 原已完成 consumable 的确切 StockMove → 原“退回这批” → `consumable_return` 250 milli。页面原批次/尚可退量与只读旧流水核对，主管批准、库管实际接收 +250/+100，原领用行保留。 |
| HK059 礼品出库 | 礼品 `gift` 500 milli、明确合成接收人，独立批准后实际赠出 −500/−150；无收入或现金。 |
| HK050 礼品退货入库 | 本次 gift 原 StockMove → 原退回表单 → `gift_return` 250 milli，实际接收 +250/+75，保留原赠礼来源与剩余可退量。 |
| HK057 其它入库退货 | 本次耗材 other_in 原批次 → `other_in_return` 500 milli，主管批准后库管实际退发 −500/−200，purpose=`wh_other_return`，original_id为该确切原入库流水。此步骤没有供应方收款。 |
| HK060 物资其他出库 | 明确合成破损耗材0.25包及回收方，`disposal` 250 milli，主管批准后实际出库 −250/−100。最终耗材2500 milli/1000分；礼品1750 milli/525分。 |
| HK085 其他入库退货收款 | 本次 completed wh_other_return500/200 → 财务原 `business-finance-other` 表单申请应收200分 → 不同manager本人原待办批准 FinanceReturnReceivable200 → 原财务账户、独立 receipt 与唯一合成流水号 collect200分。实际 CashEntry+PaymentLink+CashBatch+Allocation分别核对，库存原退物保持；最终目标200、净收200、超收/退款占额0。 |

这些是候选自动输入到结果检查，不表示银行或实物现场已真实交接。每个正向命令仅一次原可见控件点击；没有状态回写、余额构造、隐藏DOM赋值、强制点击、无理由重试或换request_id重放。

## 同轮有限前序与岗位

必须满足当前 runner 的 expected/实际 passed，固定 checkpoint `complete=true/passed=true` 且所有需求 passed、目录SHA相同、五路径 provenance相同。新候选及相关helper必须在该镜像 `provenance.json` 中匹配，`snapshot_stable=true`，合成 DB 属该外部runtime。缺依赖即停，不扫描旧业务寻找替代。

- `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187` 的 HK184 `warehouse.row.id` / `location.row.id`。再次核当前实际 warehouse/type=materials、location.warehouse_id、启用、门店和原行；不从默认位猜历史库存。
- `vehicle-purchase-hk171-177-178-026-021-018-029` 的 HK171 `supplier.id`、HK021 `payment.account_id`。原供应方保持、本店实际账户启用；应退200分是本次原合成协议的明确输入。
- `materials-hk069-045-054-083-070-072-073-051-061` 的 `material_sources.primary` 确切 Item/Enrollment/source_location_id/warehouse/StockMove IDs。当前旧 Item 量值重新读取并留在前置说明，**不用历史snapshot当新物资当前库存、不消费旧物资**；后继维修造成旧量变化合法，不要求它仍等于采购时余额。

岗位复用 `business_fixtures.vehicle_purchase` 的 `inventory_key/manager_key/finance_key/store_id=1`，逐个 SELECT 验证真实 UserStore(role/store)，零新fixture身份。库管申请/实物、另一主管批准、财务原到账。本人任务若原负载分派给demo员工，主管在原 genericCase GET 与实际h1/可见按钮完成后明确转交，AssignInput只 `version/assignee_id/reason` 三字段；原Task CAS与reassign Event/Audit核对，不登录demo或借管理员实物办理。

## 原 UI/API、成本与文件合同

原 `#warehouse` / `#warehouse/{id}` / `#warehouse-item/{id}`；POST `/api/warehouse/cases` 与 `/cases/{id}/commands/{approve,execute}`。返回专用原 `warehousereturns.js` 表单，直接点本次完成原 StockMove 的 `wh-original-return`；隐藏原批次值只读取，库位经原可见 lookup 按真实“仓库 / 库位”标签选取，原剩余数量/表单max与DB旧退回流水一致。普通原表单 raw select 用实际用户选择。

新单响应监听绑定**本次唯一POST body.id**到相同新ID原GET，保留快速GET竞态缓冲；财务原新单用 body.case.id。监听finally清理，超时或失败即终止，旧单GET不能满足条件。既有单命令取当前Case版本，085同取FinanceOrder/Case双版本；上传不会推进业务版本。原回执核完整payload及schema默认值的SHA，Warehouse approve非other_in的value_cents默认None，create补原None/recipient/locations默认。

成本取 `warehouse_service.portion` 原整数算法：普通出库按当前量值平均；原退回按原批次未退 quantity/value。StockMove.unit_cost按原绝对值/数量整数除法，Item.unit_cost按原剩余库存整数四舍五入算法；本批单一真实库位使 Entry 与 StockMove signed量值一致。每次核原准备 Allocation及Line、consumed与move ID、出库 reserve/release守恒、独立批准、原本人done Task、Event和Audit。零实物启用只能形成零Balance/Enrollment和consumed activation准备，不制造假Entry。

批准other_in使用本次独立 `receipt`，其它批准/实物独立 `evidence`，财务批准 evidence、实际到账receipt。每次文件只由员工原 filechooser 上传仓库外合成TXT；原 FileAsset.metadata、原字节size/SHA、FileSecurity.state/初次Scan及可使用状态逐核。原BLOB只在内存比较，不写checkpoint JSON，报告仅stored_blob长度/hash、文件元数据及structure_only说明；不使用default=str/base64、不输出凭据/用户hash/会话hash。结构检查不算ClamAV。

## 旧事实保护与来源输出

每次主档保存、交接、上传、业务创建及命令有完整业务snapshot。只允许该动作精确追加数量及有限当前ID/列改变，其它表全部hash不变；旧行不得删除，旧immutable row包括BLOB在内存逐列比较。主档只追加两个零Item和其Audit。每个仓储命令只改该Case/Task、该Item、该Item原Balance及本单准备的明确列；财务只改该财务Case/Order/Task与本次账户版本，不允许任何旧退货Case、库存或会员表改变。合法登录原审计在只读页面守卫基线前完成，不能粗排除Audit。

最终 `warehouse_sources` 与 `report_sources` 同结构：

- `consumable` / `gift`：`item_id,sku,name,unit,store_id,warehouse_id,source_location_id,location_ids,enrollment_id,activation_case_id,case_ids,stock_move_ids,entry_ids,balance_ids,current_quantity_milli,current_value_cents,current_version`。所有ID由当次原UI产生及只读事实取得。
- `other_return_finance`：`source_stock_move_id,source_case_id,case_id,receivable_id,cash_id,payment_link_id,cash_batch_id,cash_allocation_id,account_id,supplier_id,actual_received_cents=200`。

085独立批准后尚未收款的非零阶段保存在 HK085 check 的 `original_other_return_finance.stages[0].db`，包含目标200、payments/cash空；末阶段已全收200，不能以末状态为HK157非零待收来源。后继报告或消费须先完整同轮passed，再核当前finite ID/原量值；候选静态映射不是passed来源。

## 静态审阅与待测

作者按实际 schema/service/models/原UI/helper阅读，AST、有限SQL调用的SELECT-only、helper符号及8目录标题/check绑定静态核对；没有app import、直接业务HTTP写、应用/浏览器执行。根短审发现导出缺统一入口第三个timeout字段，本页及候选仅修三元组720秒并重新AST/形状核对，不改业务合同、不记实测失败。精确事实守卫追加数量和字段、文件字节脱JSON、原Task CAS、原批次可退上限、新实体GET竞争已经源码自审。独立短审和根注册后仍必须从新白名单镜像实际运行；动态渲染、lookup、任务分派、同源Cookie/CSRF/CSP及原拒绝/超时只能实际证据说明。

完整候选仅这八check；超量/超退、取消/拒绝、过时CAS、重复request、未知结果、不足可用库存、另一未授权身份与跨店、复杂多库位成本再分配、供应方目标修订/超收退款均conditional未执行，不假称本次已覆盖。HK086物资收款更正和HK157应收报告无独立check；会员本金/权益、采购退回、调拨、精品和维修验收不从本页增计。实际银行/实物、真实模型、PG/Linux/生产、员工体验六评价以及193完整验收继续pending，当前M8.1唯一进行项不变。

本次审阅源指纹：目录 `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`；warehouse_service `9057de29700532600db581dc83d982858f0ec09cb3c713cb8f96ea0d6e36d1b7`；warehouse_api `b4e0f9970bcf8e0a6104c58067bba6d2497e3141cd275679e27646c60a6c13ad`；warehouse_stock `5181e6c6a610cdf5cf2ffbdb1c14ffe8e1f7d8680534ba8b08de44b6fc80c302`；business_finance_service `790f96d4f34694412faaab87aae867e1168a4c1cb5ea6bd6e5c11867aa2b2b7e`；business_finance_api `5d582589f56b8b9dbe047aafe1c9a496230b7a0f75b442151023b234ad28ccd5`；web warehouse `a7e5548ee2d4dffee5200269219ef725693bb915852c20fe56143fd22731e7cf`、warehousereturns `c2b5422c7635498c40026672ab9ee8106e7a33d6be6113363bd9a72f0546fdd0`、businessfinance `f34d7cc7636b0d259e24a76ccef423399ae88501cede0a1f59fac1a643f24c27`。源改变后此静态意见须重核，不拼接不同指纹运行成绩。
