# 销售交付后四项原业务链候选范围

2026-10-01，只读设计。负责人remaining_audit，仅维护本页；生产、fixture、测试、runner、源目录合同与计划没有修改，没有导入app、启动实例或运行浏览器。依据当前HK012–017源目录、原工作流JSON、实际app/web合同；文件存在和源码审阅均不是业务成绩。全部execution_status=not_tested、manual_review=pending、business_accepted=false、full193=false。

建议下一独立批为四个check：`HK-012-business`、`HK-015-business`、`HK-016-business`、`HK-017-business`。路径接同轮真实销售交付、材料、主档：交付车辆加装→同客户代办报价改版及实际办结→同销售客户其它服务收入→原供应商整车其它收入与有据修订退款。HK017必须客户／厂家两种原来源均完成；不能只收一笔厂家款就通过整项。HK013/014为独立后批保险路径，下文保留合同与前置。

## 当前原UI接线缺口：先登记、实际复现，不能绕过

以下是明确**源码合同不一致**，当前尚未实际点击复现422。根已收到并计划在当前实例收尾后登记最小接线；本页不实施修复、改后端Proof或扩大可接受类别。正常原动作表单按file_category过滤候选并预选就地上传；不能在候选脚本改DOM或提交隐藏API绕过。

| 原文件／位置 | 当前原UI | 原API实际类别 | 最小待接线范围 |
| --- | --- | --- | --- |
| `web/serviceorders.js:63` | 全部有原件动作一律file_category=evidence | `service_orders_service.py:51`的_proof：非资金authorization；financial=True时receipt，沿`flow_engine.py:410`严格校验 | approve、authorize、submit、external_result、fulfill、termination_approve、consent用authorization；receive、disburse、thirdparty_return、termination_apply、refund用receipt；cancel／termination_cancel无原件。termination独立方案弹窗已选authorization。 |
| `web/insuranceorders.js:115` | 全部有原件动作一律evidence | `insurance_service.py:48`的_proof同样authorization／receipt；insurance_finance逐动作调用 | 独立保险候选前须核每个原动作 financial 参数后接类别；至少review／authorize／submit／result用authorization，receive／disburse／insurer_return／direct_paid／direct_return／refund等实际资金用receipt。佣金及撤保动作须逐函数核准，不能靠岗位猜类别。 |
| `web/vehicleincome.js:32` | 全部有原件动作一律receipt | `vehicle_income_service.py:43`的_proof：非资金只收evidence/authorization/signed_contract/invoice；实际receive/refund只receipt | propose／approve／reject选原非资金依据类别；receive／refund保留receipt；cancel／withdraw无原件。原生成空白文件仍不能作实际原件。 |

加装原UI已经有明确addonEvidenceCategory映射：approve/authorize/accept及处置同意用authorization，dispatch用evidence，install/quality/rectify及拆回检查用inspection，receive/refund用receipt。原附件必须本单、非generated、security.can_use，**每次事实使用独立实际原件／独立SHA**；服务／保险／厂家均检查原件SHA已用于其他事实，不能复制同一TXT改文件名反复确认。

## 同轮最小前序与现场重读

1. 必须同次evidence_root、已冻结provenance以及本次实际镜像/脚本指纹；读取 `sales-order-hk008-009-011-022/business-checkpoint.json` 的complete/passed与逐check，然后取得 `report_sources.delivered_order_id/customer_id/delivered_vehicle_id`。不能SELECT latest、借旧run或用已退订第二车。当前销售是order flow_version4；重新原GET本单取**当前**version、customer_id、VIN、quote/交付原事实及原主体，不能照前序checkpoint陈旧version写入。
2. 材料前序是本次 `materials-hk069-045-054-083-070-072-073-051-061` 九项complete/passed后有限 `material_sources.primary/secondary`。包含item_id、source_location_id、warehouse_id、明确stock_move/entry/receipt IDs；源地点必须明示，不能取location_ids第一项。加装优先secondary“件”材料1.000件；原库位／门店可用量、reserved、Item.version与本店均价**在当前原页面重读**，不得假定仍为前序终点2.000件。若当前可用不足，等待其他原链释放或另走明确原采购到货；不注入库存或把报价当出库。
3. 读取本次主档HK175启用WorkItem和HK179启用AgencyProject真实ID/单位/版本，以及采购HK171 Supplier真实ID/版本、HK021真实原账户。目前fixture已有sales/sales_peer、service、manager、inventory、finance、technician本店身份；不加fixture，不借admin代办独立核价或技师事实。尽量源销售本人sales_peer提加装／agency，另一manager复核，service质检，technician安装，inventory出入库，finance资金。原客户所有权先原读取核准；service可在原范围办理其它客户服务。
4. Agency代缴单位及other_income收费项目若不存在，由有权manager在原 `#service-orders` 新增代缴单位／其它客户服务项目，分别原POST `/api/service-orders/payees` 与 `/income-items`；实际保存重读主档、唯一原回执/审计。不能以AgencyProject冒ServiceIncomeItem，也不能把Payee收款户名当本店Account。
5. 建立已交付车辆后续都明确delivery_blocking=false：Addon create拒绝已delivered销售追加交车前要求，Service create亦拒绝已delivered_at的交车前条件。新增子单及动作会触碰原父销售version/updated_at；每个后继重新取真实父/子版本。父销售、原合同生成字节／签回、原交车事实与现金不变，只允许源码明确的关联与版本推进。

## 四项逐check完整准入

| check／原中文标题 | 本批完整原路径 | 不能省略的事实 |
| --- | --- | --- |
| HK-012-business／精品加装单 | `#addon-orders` 建立已交付销售的非阻断加装，明确当前source_order_id/source_version；quote收费行→另一manager approve→客户当前quote_id authorize→原库位准备→原VIN dispatch→技师install→service quality（建议实际不合格→技师rectify→service复检合格）→本人原accept→finance receive | AddonOrder flow_version3、AddonTarget真实VIN；AddonQuote/Line/Approval/Authorization当前版，Reservation不等于StockMove；Dispatch引用原StockMove与Target，Installation/Inspection/Rectification/Acceptance分别真实追加；收费真实CashEntry/PaymentLink/AddonPayment，accept不等于到账。 |
| HK-015-business／代办服务单 | 同原销售及同客户agency创建flow_version3；明确fee AgencyProject+pass Payee两行→当前报价独立approve/authorize→finance实际receive→逐原pass TenderSlice disburse→每行submit→真实need_documents→引用补件结果再次submit→approved external_result→逐行fulfill | ServiceOrder/Quote/Line/PriceApproval/Authorization、Payee冻结户名/账户；Submission/ExternalResult/Fulfillment分别关联当前line_key和最新submission_id；pass实际第三方净支出须等于原净本金才可办结。服务费收入、本金、实际现金、外部结果分别核对。 |
| HK-016-business／代办核价单 | 独立记录同agency v1 quote→另一manager批准→本版客户authorize；在无履约／无收款前原quote改价形成v2→保留v1及其批准授权→核v2待批准且未授权→重新manager批准／客户当前v2 authorize，后续全部使用v2 | 当前quote_id/Quote.revision/digest、原价行与fee/pass净额一致；新版本不得借v1授权提交，报价／批准本身无TenderSlice/PassEntry/Fulfillment/CashEntry。已有实际履约／原资金行不可改价，不能为改版删除旧事实。 |
| HK-017-business／整车其它收入单 | A：同销售客户独立other_income flow_version2，明确ServiceIncomeItem的fee行→quote/独立approve/authorize→本人fulfill→finance真实receive；B：`#vehicle-income` 原Supplier+本次明确销售车辆来源+结算号→create→finance propose→另一manager approve→finance receive→有据降低目标新revision→另一manager批准→原收入原账户实际refund | A使用ServiceOrder/Line/Fulfillment/独立真实现金；B是vehicle_income flow_version1，VehicleIncomeOrder/Source/Revision/Decision/Cash/Receipt；来源冻结原Case/版本/VIN/allocation事件/主体，supplier_version和external_reference真实一致。两方来源各自应收与现金，不能把客户充值/销售尾款/代缴本金算厂家收入。 |

### 代表合成输入与可对账结果（计划目标，未实际发生）

加装：secondary当前可用至少1.000件、明确source_location；收费商品30.00元+安装5.00元、折扣0；商品成本必须原均价，不能写20.00猜成本。原authorize占1.000件而不减账面；dispatch才原库存-1000 milli及实际平均成本、对应原WarehouseAllocation consumed和WarehouseEntry；技师安装、service合格、客户accept后真实履约3500分，finance单笔3500分原账户收款，原Hold净0。另零价赠送属于conditional来源，需要新明确零价行/成本承担、独立gift批准及实际库存；本批收费主路径不能宣称赠送已验证。

Agency：v1 fee20.00/pass10.00；v2 fee25.00/pass10.00，discount0、各quantity1000。改版阶段无任何收付款／履约。v2批准授权后finance一次实际收3500分，原TenderSlice按fee2500/pass1000明确分配；原pass TenderSlice实际disburse1000分独立现金支出。本人与真实外部受理的每行原submit/result/fulfill完整；终点fee履约2500分、pass本金1000分、第三方净支出1000分、客户尚欠0、本店持有本金0。至少一个fee行need_documents→补件→approved，补件不是拒绝也不是办结；pass行亦要自己的submit/result。完整第三方原退款／客户退款非本主分支，见下文conditional。

其它客户收入A：新原项目标准收费8.00元，报价800分、独立批准授权、本人实际fulfill与finance实收800分分别追加；不调用submit/external_result虚构外部代办（后端other_income明确拒绝submit）。厂家收入B：本次同供应商、已交付销售VIN作为一个明确VehicleIncomeSource，原external_reference；首目标100.00元，independent批准后finance实际收10000分；原新有据目标70.00元，独立批准产生原revision差额-3000分与refund_pending，finance选择**原VehicleIncomeCash.id**同原账户实际退3000分。终点target/net_received7000分、receivable/refund_due0，旧收10000不覆盖。使用external_document明确对方结算依据；不因厂家名自动本店开票，不冒发票193以外业务通过。

## 精确原提交、任务及范围守卫

- Addon原POST `/api/addon-orders` 是request_id/source_order_id/source_version/delivery_blocking/due_date/reason；所有原 `/actions/{action}` 携request_id/version/values。quote.lines使用稳定line_key/item_id/work_item_id/quantity_milli/goods_unit_cents/installation_unit_cents；approve.minimum_cents/allow_below_minimum/evidence_id/reason；authorize/accept明确quote_id；dispatch checked_vin + lines[{line_key,quantity_milli}]；install dispatch_id；quality installation_id/passed；rectify inspection_id；资金amount_cents/account_id/reference/evidence_id。原tasks为addon_quote/approve/authorize/dispatch/install/quality/rectify/accept/receive及独立处置任务。role与Task.assignee必须本人；非本次本人时主管只转交明确原Task，不默选员工。
- Service原POST `/api/service-orders` 是subtype/customer_id/source_order_id/source_version/customer_vehicle_id可空/delivery_blocking/due_date/reason。原动作request_id/version/values，ServiceRequest回执独立，不借flow_request_receipt猜。quote.lines稳定line_key/bucket/agency_project_id或income_item_id或payee_id/quantity_milli/unit_price_cents/due_date；pass.name必填。approve.minimum_fee_cents/allow_below_minimum；authorize.quote_id；submit.line_key/external_reference/submitted_on/supplement_result_id；external_result.line_key/submission_id/outcome/result；fulfill.line_key/result；disburse.tender_id，thirdparty_return.original_id；资金amount_cents/account_id/reference。原task前缀serviceorder_，handle/receive/pass与独立价格任务不能用结束一个Task冒全部办结。状态pending→approval/working→completed来自_sync，不写任意状态。
- VehicleIncome原POST `/api/vehicle-income` 的supplier_id/supplier_version/external_reference/sources[{source_case_id,source_version,vehicle_id}]/due_date/reason；propose.target_cents/invoice_mode/due_date/evidence_id/reason；approve.revision_id/evidence_id/reason；receive/refund带实际business_date，refund.original_id。每版冻结source_versions/digest、旧Decision与Cash不可覆写；原Task前缀vehicle_income_，提出者／created_by不得独立自批，原管理岗位／财务接手人原校验。状态pending→approval→credit_open→completed，降低目标后refund_pending→completed。
- 代表厂家来源使用`GET /api/vehicle-income/source/{delivered_order_id}?vehicle_id=<同原实车>`与catalog实际候选；原order仅flow_version2/3/4且executing/delivered/credit_open可用，并须VehicleHold配车及不可变allocate事件对应VIN。原Supplier真实来源和该收入目标证明须单独核对，不能由原销量推断厂家返利。
- 门店/本人/Cookie/CSRF、原CAS、原幂等和同事务事件/Task/回执每步实际核对；原材料余量、成本、库位不猜。读取基线在真实登录合法login审计完成后取，原导航/详情保持全部原业务；不能排除整张audit表。写守卫仅允许本批明确新case/task/item/balance/allocation/account指定列、关联父销售的源码明确version/updated_at及本次新增事实，所有他店、其它原单、旧库存/现金/签回/证据原行保护。失败或结果不明保留并停止，不重放POST。

## Conditional与独立后批，不能静默继承通过

加装拆回/取消/随VIN赠送是不同原处置：resolution→另一主管resolution_approve→客户resolution_consent→原实物return_receive合格（或整改/拒收交回）→原ReturnPosting后才允许库存恢复与商品原退款；已安装保留安装费独立按冻结批次核对。客户资金refund要明确kind=cash或advance/original_id；预收恢复不是现金。主收费加装完成并不证明这些分支。

Agency第三方退回是thirdparty_return引用原ServicePassEntry.id、同原账户真实现金，不自动退客户。客户原退款须termination逐行retained+returns[{tender_id,amount_cents}]→另一主管termination_approve→客户consent→finance termination_apply→finance refund引用plan_id/tender_id；只有未用/实际返还本金可退，原实际服务保留费和原收费减免分开。该额外分支如未在本批真发生，保留conditional/not_tested；不得为了“交易完成”简化为一笔通用退款。

客户授权、实际外部批准、安装检查、客户接收、实际银行款、原签字分别有独立原事实。合成业务可验证系统记录链和字段；结构检查附件不证明ClamAV，独立authorization上传不证明真实客户签字；原销售生成合同/签回字节保持。本轮没有真实保险公司、牌照代办机关、厂家结算或银行往来条件时，真实外部gate仍pending。原字段不足、原件未可用或相关原任务未生成不能通过选择空项/造历史/改DB补齐。

后批HK-013 **车辆保险单**／HK-013-business 与HK-014 **保险核价单**／HK-014-business：必须各自原InsuranceOrder flow_version3；本客户/原销售或真实客户车辆、HK172当前Insurer与版本；quote insurer_id/version、险种premium整数分、起止/valid_until、collection_mode、冻结收款户；独立review→quote_id+digest authorize；v2报价保留v1批准/授权且重新核价授权，HK014才成立。HK013另要真实submit→result(issued保单号／need_documents补件／rejected原结果)、明确store_collect收款+按原Tender代缴或customer_direct原直付证明；佣金commission→独立commission_review→实际commission_receive/return独立现金。保费代缴非本店收入，预计佣金不等实际已确认佣金，直付证明不造本店CashEntry。保险拒绝／补件／撤保退款均保留各自未测边界，不能将v2报价通过当整保险单通过。

## 本页交接结论

4项候选范围和本版原字段／状态／资金／原事实已源审，优先4项是12/15/16/17；两项保险后批仍明确待实施。当前原正常UI因service/vehicle_income凭据类别接线尚不能完整验证四链；根先记录精确最小补丁，再由原点击复现／复验，不降低后端守卫。所列金额数量均为计划输入与断言目标，尚无执行证据。下一候选脚本、注册、服务和业务通过不在本页授权，等待根登记；本页不能作为implemented/passed/released或193目标完成报告。
