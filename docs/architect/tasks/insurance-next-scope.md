# 保险、原款及续保下一批源码范围

2026-10-01，只读设计。依据当前193项目录、`wf-insurance-order`、`wf-insurance-renewal`与实际保险/客户服务代码。没有新增测试、生产、fixture、注册或运行服务；所有输入数字均为拟议合成输入，没有对应执行成绩。当前销售后继候选保持冻结。

本页源合同记录：HEAD `5069b2bcc9f580ebb9d70780769049a14a6de946`，不把同HEAD当同源码。对app下insurance_api/service/finance/models、customer_service、observation_corrections_service，web下insuranceorders/customerservice，business_acceptance_catalog及workflow-source的business/services两个源JSON，共11个实际文件取SHA256，以路径为键的排序紧凑JSON再次取SHA256，得到`a46db54a38c9dbd1ca74f91f3093794ef8489246d8307bf6bb8852bbf5f17a2c`。保险UI当前SHA256 `69a08efb8b986df08a545b72f629812703411287d68c874b17b8472b4f61b685`，接线修复后应记录新源指纹，不继承本页为运行通过。

建议一次连贯增量覆盖七个完整自动check：HK-013/014/077/113/114/115/116。保险报价、出保、资金、提醒、分派及回访每项分别保存实际动作与原事实，不由一次保险建单或页面导航继承通过。

## 最短真实前序

现有主档场景HK172已通过的明确本店启用Insurer，以及客户场景HK098实际客户和HK099 local_scope_passed中的明确本店CustomerVehicle，可作为有限来源。客户车辆仍是HK099 partial，不能由复用改记HK099-business通过。优先使用该同客户车辆、不强行关联另一销售客户的原订单；保险原create允许仅customer_vehicle_id。普通维修已通过时可以引用其report_sources.customer_vehicle_id/customer_id确认同一实际车辆，维修不是保险必需前序。

不得假定已交付销售自动有CustomerVehicle：原销售客户与客户场景客户可能不同。若负责人要求保险沿本轮已交付销售客户继续，应在本候选原UI新增该同客户同VIN车辆关系并冻结明确编号，再建立非阻断保险；不能取另一客户的CV、改customer_id或凭相同VIN当同客户。原create同时选销售/CV时两者必须同客户同VIN、原销售当前source_version。

使用现有service、manager、finance，提醒交接可service→manager，二者均属原OPS；不需新fixture或借admin。新保险仍由service建立/办理，另一manager保险核价；续保CareCase由明确接手员工办理。该manager接手续保不会使其获得保险建单FRONT岗位。实际现金选本轮明确原Account及每笔独立流水，密码仍只用外部现有credentials。

## 七个check与拟议实际链

| check_id及原名称 | 必须发生的原UI动作与独立判据 |
| --- | --- |
| HK-014-business 保险核价单 | 第1版险种合计200元、预计佣金10元，由service报价、另一manager review批准、客户authorize绑定quote_id+digest。实际资金和投保提交前再报价第2版220元、预计佣金15元；旧Quote/Review/Consent及QuoteCancellation追加历史保留，当前版无旧核价/旧授权准入，再独立review与本版authorize。当前UI展开历史与API/DB两个摘要对应；新增实际提交仅可用第2版。 |
| HK-013-business 车辆保险单 | 第2版明确store_collect、冻结真实合成收款户、保险期间与本版valid_until。原submit→result need_documents（不得填写policy_number）→独立补件submit→result rejected（仍无保单号）→再次原submit→result issued，填写唯一实际合成保单号。每个结果绑定自身原submission_id，同quote_id及当前CAS；原API没有agency的supplement_result_id，不能造该字段。出保独立产生InsuranceResult和同CV保险来源观察，不能由报价、佣金或现金推断。后续保费、代缴及实际佣金齐全才核对完整终点。 |
| HK-077-business 保险服务收款 | 财务receive22000分生成唯一CashEntry/PaymentLink/InsuranceTender，再disburse该原Tender22000分生成独立原InsurancePassEntry和现金；门店本金净额零。另commission提出实际累计1200分、另一manager commission_review、finance commission_receive1200分，与报价预计1500分区分。后续续保单采用customer_direct并明确direct_paid原证明，旧现金/付款链全行不变，该DirectEntry不生成店内保费现金。三类资金各自单独原事实核对；不能用保险13的出保断言代替本项。 |
| HK-113-business 续保信息提取 | 首单保单end_date取业务日D+10，真实issued后形成原有效insurance来源；manager在原customer-reminders配置唯一renewal规则，initial lead_days=9，OPS generate不应提取该CV；按原version编辑lead_days=10，OPS generate实际提取同CV/原Observation/Rule的非空renewal CareCase，原提醒Basis冻结；原UI“查看续保跟进”精确定位该单。只生成内部任务，不能称已外发。 |
| HK-114-business 续保信息分派 | 在本轮明确renewal详情原handoff，将service原care_handle交给当前启用manager，明确due_date和reason。Case.owner/due与同一Task.assignee/due同事务推进，CareRecord保留from_assignee_id/previous_due_date/was_overdue，旧记录不覆盖。下一身份实际登录可见同原单与可办动作，不能只核对姓名显示。 |
| HK-115-business 续保分派回访 | 新负责人start并两次真实followup，channel/date/note分别留原CareRecord；新有效保险来源之前close(result=renewed)须原拒绝，业务表不被改写（原权限refusal审计如实际产生须精确核原来源）。service另建customer_direct续保保险，显式previous_policy_id=首InsuranceResult.id、renewal_task_id=该CareCase.id及renewal_version、同CV/客户；独立报价/批准/authorize，期限晚于首保单且未来，实际submit/issued/direct_paid和零实际佣金的原确认/独立复核结束对应任务。接手人重新读当前续保CAS后close renewed，新原有效Observation.id不同、截止日确实延长；电话文字不能代替新保单。 |
| HK-116-business 保险到期提醒 | 分别记录提前9天未到边界、10天边界生成与再generate同周期不重复；service“我的工作”实有该到期原care_handle提醒，实际点击打开同原单，不能只共用113提取数。完成续保后、新未来保期尚未触发时generate不再生成旧周期。为验证基准失效，从首保单实际撤保方案/独立复核/客户同意/finance生效，产生InsuranceBasisInvalidation；客户车辆原有效来源显示旧保期失效、新续保保期仍有效，旧已完成CareRecord保留，生成不能再采用失效来源。实际源失效和原款结清见下节。 |

首保单D+10是原API允许的合成短期保险期间，声明为合成短期险；不能将其描述成真实一年期保险或保险产品推荐。所有实际business_date仍为已发生业务日，业务时区取fixture明确Asia/Shanghai；不改服务时钟、数据库日期或已有保期造边界。

## 原返还分支的准确终点

首单已issued并已代收/代缴220元，须真实外部退保依据，不能普通cancel。service termination选择external_result=terminated、retained_cents=0、returns[{tender_id:原正Tender.id,amount_cents:22000}]；另一manager termination_review，service termination_consent绑定本版plan_id+digest，finance termination_apply生效。该步骤追加原保险失效关联和提醒基准失效；应用不是现金退款。

finance insurer_return引用首InsurancePassEntry.id、同原账户，实际收回22000分；随后finance refund选择原plan_id/原Tender.id和原客户收款账户，实际退22000分，新增负Tender及PaymentLink.original_id指原客户收款，原CashEntry全行保留。原退款额度由refund_limit核对，不能将保险公司退回直接当客户退款。

撤保后另提commission累计目标0，另一manager commission_review；finance commission_return引用原InsuranceCommissionPayment.id、同原账户退1200分。保费本金回转和佣金回转分别有现金与独立原关联，不能抵作一笔。最终原保费/门店本金/应收应退与原佣金净额均零，历史出保事实仍保留，同时有效观察将旧保期明确标为失效。

这组返还用于保险原款和HK116真实基准失效；不新增不存在的需求ID，不借它证明整车退车、精品拆回、代办终止或会员退款。整车提车后退车另需aftercare vehicle_return→原VIN隔离接收/技师检查/另一主管验收入库新代次→finance apply→原款退款，及关联加装/代办/保险分别原域结清。HK023原名是“车辆采购退回”，不能用销售退车当该项完成。此批保留该后继分支未执行。

## 原API、Task及模型合同

保险原POST `/api/insurance-orders`，原GET/catalog与`/{id}`，动作`/{id}/actions/{action}`携request_id/version/values。quote必须insurer_id/version、lines[{name,premium_cents}]、collection_mode、payee_account_name/reference、expected_commission_cents、start_date/end_date/valid_until/terms/reason；客户授权quote_id/digest。原任务insurance_quote/review/authorize/handle/receive/disburse/direct_paid/commission/commission_review/commission_receive/commission_return及撤保任务保持岗位/本人。quote已有实际Tender/DirectEntry/Submission后禁止改价；实际提交/资金/佣金和原版本分别保留。

原模型InsuranceOrder/Quote/Review/Consent/QuoteCancellation/Submission/Result/Tender/PassEntry/DirectEntry/Commission/CommissionReview/CommissionPayment/Termination及各Review/Consent/Application/Refund、InsuranceRenewalLink、InsuranceReceipt、原Case/Task/Event、CashEntry/PaymentLink/Account与Case/CashEntityContext需各自核实际关联。出保的观察来源字段observation_id连接care_vehicle_observations；effective_observations将其source_type标保险原单、odometer_measured=false且不暴露为实测里程，禁止据保费业务推算公里。

提醒原GET/POST `/api/customer-service/reminders/rules`、PUT `/{rule_id}`须version，POST `/reminders/generate`只request_id；case原GET与actions/start/followup/handoff/close用request_id/version/values。renewal规则仅lead_days，其interval_days/interval_km/lead_km为0；ReminderRule每店kind唯一，先查现有规则，不能重复新建另一renewal。已有本轮明确规则时只按原CAS编辑并保留旧版本来源，不能擅自停用其它规则。generate遍历当前店实际有效CV和规则，候选必须事先核其它实际到期来源，不能过滤/隐藏合法原生成结果来保期望数。

CareCase/Record/Receipt、ReminderRule、VehicleObservation、ReminderBasis、InsuranceBasisInvalidation、ReminderInvalidation/Replacement与同原Task均为真实来源。renewed守卫要求有效保险来源较原baseline不同且期限未来/延长。需所有旧行、另一店、其它单、原款/附件字节保护；读取基线在合法登录完成后，结果不明停止不重放。同一文件不得替另一个事实，原件只记metadata与实际BLOB长度/SHA。

## 已确认静态UI缺口及实施前置

`web/insuranceorders.js:114` 当前所有非取消原action的evidence_id均固定`file_category:'evidence'`，与`app/insurance_service.py:48–52`原非财务authorization/财务receipt不一致；`app/insurance_finance.py`的commission/commission_review虽非现金提交，也明确financial=True、须receipt。这是静态源合同错配，尚未实际执行该保险表单，不宣称捕获422。

建议负责人仅登记原前端动作类别接线：review/authorize/submit/result/termination_review/termination_consent使用authorization；receive/disburse/insurer_return/direct_paid/direct_return/termination_apply/refund/commission/commission_review/commission_receive/commission_return使用receipt；quote无需原件，quote_cancel/termination_cancel/cancel无原件。独立insuranceTermination原方案已经过滤authorization，不应改为evidence。保持后端 `_proof`、文件安全、唯一SHA、权限、当前店、CAS、金额、状态与事务；不得放宽候选过滤或原件守卫来求通过。

新scope仅建议七项候选范围；需负责人登记精确脚本/文档补丁并授权后再写候选。没有脚本、服务或业务通过成绩。自动断言和人工体验/文案各自留结果，business_accepted/full193仍false；真实保险公司、客户签字、银行、ClamAV、PG/Linux、员工试用和生产门槛均待各自条件与证据。
