# 原维修附带精品、部分退货和销售套餐点击候选

2026-10-01，M8.1，按 PATCH-M8-4-BUSINESS-193-33 与 retail-remaining-scope.md SHA5edcd1702ebd7c2a00d6d3c325e56df97ef7ae155f51e880162f0ab03833f07b 作者。只新增本记录和 tests/browser_click/retail_remaining_business.py；生产、已有候选/helper、fixture、目录、runner、注册与计划保持只读。当前是未注册、未运行候选，静态核对不记业务通过。

入口 `retail-repair-return-bundle-hk063-066-067-068`，导出 `RETAIL_REMAINING_SCENARIOS=((SCENARIO, retail_remaining_business, 1200),)`。四个独立完整 check 为 HK-063-business「维修精品销售单」、HK-066-business「维修精品销售出库」、HK-067-business「精品销售退货」、HK-068-business「精品销售套餐设置」。运行前全部 not_tested；失败仅当前 check failed，已开始未闭合项 partial，未执行项保留 not_tested。所有人工标准、business_accepted、full_193_business_acceptance 均保持 pending/false。

## 有限本轮来源

直接父是本次完整 passed 的 `boutique-purchase-retail-hk074-052-058-062-064-082` 和 `repair-selfpay-hk031-034-044-049-053-079`，原 runner 登记、整场结果、全部 check、catalog digest、provenance 与固定检查点一起核对，不使用局部通过或历史 run。最短完整闭包为售前、整车采购、主档、物资、客服、首维修、整车销售、会员基础、会员后继、精品六项及本入口；由根按当前注册依赖排序执行。

- BT.report_sources：`item_ids[2]`、`profile_ids`、`enrollment_ids`、`warehouse_id/location_id`、`brand_id/category_id`、`work_item_id`、`account_id`。重读当前 active Item/Profile/Work/Account/库位及真实 Balance、原启用和现有 Retail 预占；A 当前本库位至少2000、B至少1000千分之一，其余库位无实物。金额成本使用当前原账，不从商品报价或旧 checkpoint 兜底。
- REP.report_sources：`customer_id/customer_vehicle_id/repair_case_id`。本店原已接车完成维修与同客户资料；顾问原读取可以选择该维修。当前客户必须没有有效集团会员关联，无实体策略新前序，以保留本批明确纯 Cash、无消费积分规则合同。
- 原五岗位是本店 service、manager、inventory、technician、finance；全部用 existing 本人身份和当前店 UserStore role，不使用 admin 代办。原 Task 需要交接时沿已有本人候选和 AssignInput，待办/CAS/原事件逐核。合法登录完成后才取 Guard 基线，原 login Audit 不排除。

## 两张原单输入到结果

1. A：service 原「新建精品订单」，选择同客户和原 repair，A 1000数量、商品单价2000分、真实作业安装500分、无折扣。新增独立 RetailOrder/Line/Reservation，建单不改变库存量值。manager 独立价格授权，service 本版 authorization；inventory 原准备 `retail_dispatch=-1000`，实际出库才产生 StockMove/Dispatch/Entry、释放预占；technician 实际 install，service 客户 accept，finance 原 receive2500。HK066 仅完成此独立出库，HK063 在安装/接收/实收全闭合后才结束；原入口真实钻取同客户已完成维修，所有旧维修款/材料/任务不变。
2. A 退货：service 明确原 Dispatch 的500数量申请；另一 manager 复核原 Return.version 与 Case.version，冻结已安装费用保留；inventory 原准备 `retail_return=+500`、本次实际独立可售检查合格。原 Posting goods=1000、installation=250、retained=250，减应收仅1000、成本按原 Dispatch 剩余 `_portion` 恢复，未验收前不产生应退或库存恢复。finance 原 UI 提交1100分阴性，精确409文案、全库不变并明确丢弃；之后新正确独立提交原款退款1000分，同原 account/payment，净实收和 charge=1500、应收/应退0，安装事实仍保留。阴性是已知拒绝后另一明确输入，未知结果不重放。
3. B：manager 原套餐配置新 code/base_version0，明确启用和销售期，A每套500数量商品参考1000/真实作业安装参考300，B每套500数量商品参考2000/无安装，成交每套3000分。原最大余分冻结909/273/1818；service 原客户/套数两阶段预览，不写 DB，再明确条款创建2套，总分摊1818/546/3636、总价6000、A和B各1000数量。该 UI 没有维修关联字段，B 不注入 related_repair_id；A 单独证明HK063。独立 manager 批准、本版授权、两原库位准备/实际出库、技师安装、客户接收、finance 原纯 Cash6000，完整普通 Retail 任务闭合。Bundle Rule/Component/Sale/Allocation 和旧版事实均不可覆盖。

## 事前误录声明及后继 HK086 来源

A 任何付款提交前，在本场景仓库外 synthetic-inputs 写独立 JSON 声明并观察其 SHA：合成款确到、本次2500分/原账户/业务日一致，正确 BANK `RT-IN-CORRECT-<token>` 与本次故意输入的 ENTRY `RT-IN-MISRECORDED-<token>` 不同。finance 原上传 receipt 文件包含该完整声明，数据库原 bytes 与大小/SHA 一致，输出只 metadata 和 stored_blob.length/sha256。不能事后把正确流水假称错误或将已知误录称已更正。

`report_sources.cash_correction_source` 明确提供 `customer_id,case_id,original_cash_id,original_payment_id,refund_cash_id,refund_payment_id,original_account_id,business_date,entered_reference,correct_reference,gross_cents=2500,refunded_cents=1000,remaining_cents=1500,allocation_basis=remaining_after_refunds`，以及事前 declaration 路径/SHA、原 receipt metadata/blob SHA；`intentional_reference_error=true,correction_executed=false,HK086_status=not_tested`。新 B 使用另一个正确独立 reference。当前候选不创建 Correction，不做更正、第二笔收入或额外出入库。

其他有限输出包括两 Case、A原 Dispatch/Line、Return/Posting、各 Cash/PaymentLink、B Rule/version/Sale/Allocation/Line/Dispatch、WarehouseAllocation/StockMove 与终局当前库存。A净15元和B60元分别核对，旧 BT 原 RetailGroup/券/本金/Cash/采购和原 REP 全旧行保留。

## 原合同和保护

按 app/retail_api.py、retail_service.py、retail_models.py、retail_bundle_api.py、retail_bundle_service.py、retail_bundle_models.py、warehouse_api.py/warehouse_stock.py、flow_engine.py、membership_service.py 与 web/retail.js/retailbundles.js 的实际参数、UI类别和状态编写；复用既有读页、原表单、文件、任务交接、库位和明细 helper，不增加 HTTP/Cookie 桥或新执行框架。

- 所有正向写均原 visible 表单单次确认；original_submit 的 POST/同原 ID 自动 render GET 配对，不提交后另抓旧 response 或盲 reload。每次 Case/Return 当前 version，原 Task 本人，整数分/千分之一。
- Guard 全业务哈希覆盖，只放当前两个新 Case、有限本商品/旧 Balance/原 PreparedAllocation、目标 Return/Account 的原必要列及本次有界新增；未允许原行/表逐列保护，原 Case.data 只追加事实。库存成本不是售价；每次出退 `_portion` 与 Item/StockMove/Dispatch/Posting/Entry/Allocation 守恒。新单 authorize 原来会追加 member_id/rule_id均null 的 PointsClaim，不能冒有会期/消费积分或宽放旧 Claim/PointsChange。
- 普通 Retail/库位沿 FlowRequestReceipt 原 family/digest；Bundle create 含 schema 原 `related_repair_id=null` 默认和两原 flow event/audit，发布 Rule 只一条 RetailBundleReceipt、无 FlowReceipt。原 Audit 本人/门店/原 entity/action 匹配。
- Cash/PaymentLink/RetailPayment 金额、方向、category、原账户、原付款、日期、reference、本人/receipt 同时核对。退款1000不能超过验收减免或原实收未退额度。所有旧资金和权益独立保护，真实退款不当新收入。
- 普通上传仅结构扫描条件；使用原 authorization/receipt/evidence 类别。BLOB 仅内存原字节 Guard，报告不含 bytes、base64 或 default=str。末次详情刷新原状态/金额完全相同，全库不变；原仓位库存页面核当前值，不只看后台 state。

## 静态核对与待测

当前已经完成源合同人工自审；新增模块 AST、四原标题/check_id、七处直接 DB 调用均为 SELECT、finite动态表/字段及 helper 符号、三元1200s shape、UTF-8和空白静态检查通过。源码840行 SHAabc8b7211a29bd65b34daf44fcda9c26063271d0feb257f6acc7aaaf5ce1bb51，文档自身 SHA 另在交接消息登记，不自引用。没有 app 导入、业务实例、浏览器或测试运行；当前候选所有自动结果仍未执行，独立交叉只读审阅待根安排。

HK071 的授权双店非空库存/非零当前在途和HK086另批更正不计第五或第六。退货整改复检/拒收交回、撤销、多次最后余分、套餐下一版停售与历史版/套餐组件退货、会员混合退款、并发/幂等分别 not_tested。实际 DOM/候选/折叠时序、原 preview及 multipart 可观测性、库存原成本还须根在新鲜同轮原生浏览器实测；人工六类标准、PG/Linux、真实实物/银行/ClamAV/模型、员工试用与生产门槛保持待测。不得从目录、单步或静态核对继承任何 passed。
