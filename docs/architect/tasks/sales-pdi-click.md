# PDI、精品加装出库与车辆销售收款点击候选

2026-10-01；精确授权 `PATCH-M8-4-BUSINESS-193-32.md`，范围来源为 `sales-pdi-addon-scope.md`（SHA `fd8b0273b04b4475dfdf0fdacabaa552de56a9c28fb46265daf6b3ca31856124`）。仅新增本人脚本和本任务页；没有修改生产、已有 helper、fixture、runner、目录、注册、计划或其它冻结候选，没有导入 app、启动应用、浏览器或测试。本文记录静态实现，全部三项仍未实际执行。

入口 `sales-pdi-addon-hk037-065-075`，函数 `sales_pdi_business(e, context, credentials)`；导出 `SALES_PDI_SCENARIOS=((SCENARIO, sales_pdi_business, 720),)`。继续使用现有 Evidence 的真实动作、网络、截图与 SQLite 只读能力，复用原 sales_order/sales_followon 的有限 UI 小型 helper，未新增执行框架。

| 需求与原标题 | 本候选闭包 | 自动检查边界 |
| --- | --- | --- |
| HK037 新车检测(PDI)，`HK-037-business` | 新订单当前第二 VIN 初检不合格 → 原发车禁用且仅 PDI 原因 → 技师整改 → 同 VIN 独立复检合格 → 原库管出库 → 当前版提车字节/签回 → 销售实际交车。 | 两轮检查、三不同原件、事件/任务/轮次/VIN/原成本/代次逐项核；生成原 callback 后只读打开，不算员工已回访或自动 CV。 |
| HK065 精品加装出库，`HK-065-business` | 消费本次完整 sales-followon 的已执行领料、安装、不合格整改、复检、接收及实收；再实际打开本次 Addon 详情，逐项核页面与即时原件。 | 原父 actions.json 的有限动作区间/native response/唯一本人回执与 DB 同时核对；本场景零追加领料、安装或现金，不用静态映射计通过。 |
| HK075 车辆销售收款，`HK-075-business` | 同一新 PDI Quote 13000000 分，finance 原 UI 收 5000000 和 8000000 分，独立 receipt、账户/凭据/reference/原款/Cash。 | 每笔原生 dblclick 连续两点击，仅一个 POST/Receipt/PaymentLink/Cash；页面累计与后笔表单原剩余默认金额核对，刷新不二记。没有 raw 正向 HTTP 重放。 |

## 同轮有限前置

固定父检查点仅从当前 manifest.evidence_root 读取，父必须已在当前 browser-click-report 注册并实际 passed，检查点 complete/passed 和全部完整要求均为 passed。同 run 路径、原目录指纹、稳定镜像、原脚本 SHA 必须对应；缺父直接失败，不从旧 run 或全库扫描替代来源。七父为：

- `sales-presales-hk001-007`；`vehicle-purchase-hk171-177-178-026-021-018-029`。
- `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187`；`materials-hk069-045-054-083-070-072-073-051-061`。
- `sales-order-hk008-009-011-022`；`sales-cancellation-hk010`；`sales-followon-hk012-015-016-017`。

客户由销售父 `report_sources.customer_id` 指定，新 PDI 车由退订父 `cancelled_order_id/cancelled_vehicle_id` 指定，必须与原已交付车辆不同。即时只读重验原取消净款零、已解占，采购 HK021 的有限两车 Receipt→Shipment→Line→Model、原位置、原成本、当前代次、已审核、stored、无 Hold、GroupIdentityLink/Custody/VIN 身份。原售前 lead 已 converted，因此新报价原 UI 选择同店本人已知客户，不再次承接或改旧意向；lead_id/lead_version 均为空。

fixture 只读取既有 `business_fixtures.sales_order` 的 store_id/sales_key/manager_key/inventory_key/finance_key/service_key；technician 读取已有 `business_fixtures.repair.technician_key`。各真实 User/UserStore 和 Store 来源以本店原角色为准，每次原登录响应再核实际 ID、active、当前一店 role 与 aggregate_scope=false。原任务若在 demo 员工名下，仅不同 manager 经原 Case GET/CAS、可见具体 Task、真实员工 lookup、原三字段 AssignInput 转交，不借 admin 办业务。

## 新单、原件和保护

原新报价 → 不同主管复核 → 原可用车候选明确选有限 VIN → 本版生成合同并实际下载核 SHA/快照/字节 → 原 signed_contract 选择生成 source_file_id → 本版确认。配套 addon/insurance/agency 均明确未选，没有新服务子单或预置付款。初检/整改/复检值为原中文 `不合格/合格`；generic Case 的已有真实摘要保留原警告，再回专用销售页面办理。dispatch 的原任务先真实交到 inventory，本店本人 UI 的阻断理由须精确为“交车检查尚未合格，须处理缺陷并复检通过”，不能把他人任务或欠款当 PDI 阻断。

每次登录审计和页面读取完成后取基线。Guard 全原业务表摘要与旧行对比，只允许当前新 Case/有限 Task 的列、当前实车版本、原位置/占车、明确账户版本及原 Quote/Review/Consent/Resolution/文件/事件/回执/资金追加；其它旧单、原采购/退订/交付、旧现金、库存、会员、附件与他店全行不变。新 FlowCase 只可为本次 order 或同客户 parent 的 callback；旧行不能删。文件 BLOB 仅内存保护，报告仅长度/SHA/实际下载元数据，上传后原 UI 再下载核实际字节；SQLite b'' 私有对象分支不当作假内容，下载/上传各唯一精确原审计。

所有正向写都来自可见原表单和原生点击。同源 Cookie/CSRF/当前 store、提交 Case/Task CAS、原 request_id 内容摘要和唯一原回执逐项核；原金额 input 字符串与后端 FlowEvent 整数分分别核对。第二次原点击由原 UI 截止，不补原 API 重放、强点 disabled、改 JS state、换 request_id、固定 sleep 或重试。UI 防重复的本次硬事实为连续点击之后的唯一请求和原款；不声称执行了后台回执重放分支。

## 事前 BANK 与 ENTRY 合成说明及后继接口

在任何新报价提交前创建仓库外 `{e.directory}/synthetic-inputs/payment-declaration.json`，其中第一笔 `correct_bank_reference=PDI-{随机本次token}-BANK-01` 与 `deliberate_entry_reference=PDI-{token}-ENTRY-01` 必须不同；金额 5000000 分和账户有限 ID 同时冻结。第一份原 UI 上传 receipt 字节含 BANK 正确编号，员工原 UI reference 故意填写 ENTRY；原 PaymentLink/Cash 不修改。第二笔新 receipt/reference 独立，金额 8000000 分。正确编号是事前声明的合成输入，不是事后给正确原款编错款理由，也不代表真实银行凭据。

仅三完整自动检查均 passed 才输出 `report_sources`：customer_id、pdi_order_id/pdi_order_number、vehicle_id/vin、quote_id、account_id、addon_case_id、callback_case_id；first_payment_link_id/first_cash_id/first_receipt_id/first_evidence_id、first_correct_bank_reference/first_misrecorded_reference；second_payment_link_id/second_cash_id；declaration_path/declaration_sha256；correction_executed=false。HK075 明细另有两笔原件 SHA/长度、Receipt digest/request_id SHA、原款/Cash、native 请求和保护结果。动态声明 SHA 只能在本次实际运行创建后给出，静态阶段没有捏造该证据。

此接口仅给后继 HK078 读取同 run passed 来源，不能本批进行更正；HK076、后台 raw replay、交车前阻断加装、赠送、拆回、超期/换车、跨店、PostgreSQL、原生 Linux、真实银行/现场、ClamAV、公司合同审批、主体策略和员工体验仍未测。demo 模板只验证合成生成/签回流程。脚本报告 business_accepted=false、human pending、full_193_business_acceptance=false，不能把三个自动闭包扩大成全 193 验收。

## 静态交接

AST、原三标题/check_id、三个有限入口元组、SELECT-only/无 app import、现有 helper 签名、真实 UI selector 与原 native value、Task/Quote/Receipt/Position/Hold/Account 模型合同已逐项静态核对。首次真实渲染、连续点击时序、lookup、上传/下载与三业务闭包尚待根在稳定指纹的新隔离实例执行；静态审阅没有新增 passed 成绩。最终源和本页 SHA 由交接消息记录，避免自引用文件摘要。
