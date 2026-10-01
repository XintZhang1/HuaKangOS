# 剩余客户需求：原生浏览器业务增量范围

2026-10-01 只读设计；HEAD `8993ca8c755194a42a48e7323fe355e80c6bf9ae`。本页只登记源码合同和建议次序，没有新增脚本、夹具、注册、业务写入或实测成绩。当前联合运行的会员及财务报表结果不预先继承；193 项业务验收和六类人工评价仍未完成。

目录为 `tests/browser_click/business_acceptance_catalog.json`，SHA256 `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`。以下完整检查编号均为相应的 `HK-xxx-business`，不能用前轮局部子动作自动填为 passed。

## 原题名与最少非空事实

| 需求 | 原题名 | 原页面 / 动作 | 原事实与完成边界 |
| --- | --- | --- | --- |
| HK-099 | 车辆档案 | `#customer-vehicles` 登记、编辑、观察、服务历史；跨店摘要和原单附件分别走原授权页 | 当前客户与本轮新交付 VIN/车型对应；`care_customer_vehicles`、`care_vehicle_observations`、集团客户/车辆身份、实际售后原单及 `care_history_links` 一致。本店查询子范围不足以完成全项。跨店须明确双方身份及有限授权，不能凭同 VIN 或换 `store_id` 合并。 |
| HK-100 | 其它收入单 | `#service-orders`，`other_income`：报价→另一主管批准→客户本版授权→实际办结→财务到账 | `service_orders/quotes/lines/price_approvals/authorizations/fulfillments/tender_slices` 与原 `PaymentLink/CashEntry` 同源。fee、代缴、预收抵用分开；上传、批准、履约或已结任务均不能代替实收。 |
| HK-101 | 问卷设置 | `#customer-questionnaires` 新版提案、独立复核；原问卷服务单接手、填写、结案；`#customer-questionnaire-report` | `care_questionnaire_policies/versions/reviews/bindings/responses` 与原 `CareRecord`。发放时冻结题目和版本；必答缺失拒绝，空白不等于否或 0；真实回答的图表、明细、CSV 同范围。版本发布或提醒生成都不是答卷。 |
| HK-102 | 车辆销售回访 | `#customer-service` 的 `sales_callback`：选择真实交付 order，接手→联系→结案 | `CareCase.source_case_id` 对应同客户、状态为 delivered/completed/credit_open 的原 order；若原单有 VIN，所选客户车辆 VIN 必须一致。原 `Case(flow_version=2)/CareRecord/care_handle Task` 与实际联系结果一致。 |
| HK-103 | 意向客户回访 | `#cases/lead` / `#case/{id}` 的本人原 `follow` | 必须当前仍为 intent 的真实 lead；原 follow Task、至少一次实际 result/due_date、追加 FlowEvent、今日待办与原所有权一致。Care 回访不能替代；已转换销售的 lead 不能恢复 intent。 |
| HK-104 | 维修工单回访 | `#customer-service` 的 `repair_callback`：选择真实完成 repair，接手→联系→结案 | 同客户、同实际客户车辆/VIN的原维修已完成来源；`CareCase`、原责任 Task、逐次 CareRecord 和结果分别核对。原接车完成不等于已回访。 |
| HK-105 | 保养提醒 | `#customer-reminders` 建立/编辑 maintenance 规则→检查生成→实际办理 | 有效 delivery/maintenance/first_service 基准及独立实际里程；周期天或公里至少一项，提前量小于周期。`ReminderRule/Basis/Invalidation/Replacement` 与原 Care/Task 周期及去重一致；不能把联系完成写成保养完成。 |
| HK-106 | 保修提醒 | 同页 warranty 规则→检查生成→实际办理 | 原规则只用 lead_days；有效 warranty 观察的 valid_until 有明确来源。核对到期日期、实际任务、原基准及去重；不猜厂商保修年限、公里周期或外部短信结果。 |
| HK-110 | 客户回访查询 | 原列表 subtype/status/q→原详情、来源及回答 | 非空 sales_callback 和 repair_callback 都需实际存在；q 后端只筛 Case.number/CareCase.topic，不声称姓名/电话检索。销售/接待同时满足本人 Care 范围和客户范围。跨店历史另按 HK-099 授权。 |
| HK-111 | 跟进记录查询 | 原服务单“办理记录”；原意向单“操作留痕” | 多次真正提交的 CareRecord，其 actor/date/channel/contact_result/note 逐条匹配、刷新不覆盖不重复；意向 FlowEvent/Task 另查，不能混成同一回访记录。 |
| HK-112 | 首保提醒回访 | 同页 first_service 规则→检查生成→本人回访 | 基准只取 delivery；已有有效 first_service 观察时不再生成。首保回访、实际首保维修完成、登记首保观察是三个事实；缺实际首保来源时后两步及抑制分支保留未测。 |

## 建议三条输入到结果链

### 一、交付车辆档案、实际回访与原题问卷

1. 固定读取同次销售交付 checkpoint 的 `report_sources.customer_id/delivered_order_id/delivered_vehicle_id`，只读核当前 order、Vehicle、VIN、车型、交付日期、客户关系和原生成/签回凭据。服务顾问经原 UI 登记该新 VIN 的客户车辆，编辑已知车牌/车型，并按本轮交付/PDI的明确输入登记日期、里程和来源；不从库存状态推断里程，不重建旧局部 CV 为另一 VIN。
2. 原 UI 新建该 order 的 sales_callback，显式选实际责任人，接手、两次 phone/in_person 跟进、选择真实结果结案，再链接该原售后 Care 单与原销售单到车辆历史。另从首维修有限来源选择其原 CV 与已接车 repair 办 repair_callback；它与新交付 VIN 的 CV 可以是两辆明确不同的车，不能伪称同 VIN 维修。原列表分别筛 subtype/status/单号或主题，点击详情核源单和每条联系记录；刷新验证无重复、无写入。
3. HK-103 使用明确仍为 intent 的本轮原 lead。当前销售承接后的主 lead 已 converted，首售前另一路接待提醒也不等于 intent；没有有效来源就经原 UI 新建→真实分派→意向→本人 follow，核原任务、事件和日期，不扫描库选 demo 旧单，不倒退销售来源。
4. manager 提案新问卷版，另一位当前店 manager/admin 独立批准，创建 questionnaire 冻结该版。发放后再发布另一已审版，核旧单 Binding/题目/哈希不变；员工接手旧版单，在原表单真正填写整数 0、布尔否及原 choice，先缺必答提交拒绝且原业务不变，再完整 resolved close。另建新版问卷并填写，报告按版本/题目筛明细、展开原记录、真实下载三个 CSV，原回答与图表同范围，CSV 每次只增加精确一次原导出审计。
5. HK-099 跨店完整分支保留：来源店与目标店各自经原 UI 建立同集团客户身份、同车辆身份的明确 CV，本店业务独立办理。主管在 `#customer-history-grants` 建摘要授权（日期为今日至最多 365 天），目标店查看真实来源摘要；原 UI 撤销后再读不开放。附件需要时另走 `#dossier-grants/sent|review|received`：发起人选原单版本/明确接收员工/逐件可用文件，来源店另一主管独立批准，接收人打开快照及实际下载，再撤销核拒读。摘要授权不开放原单、费用或文件；附件授权不替代双方客户车辆身份。真正过期分支缺真实时间条件时标未测，不改时钟或数据库。

本链候选覆盖 HK-099/101/102/103/104/110/111；每项按实际完成子链独立计数。跨店分支未执行时 HK-099 仍 partial。首版缺必答、未授权接收、撤销后读取及查询无结果都保留真实拒绝与零业务变化证据，不能以可导航代替原合同。

### 二、三类原观察提醒与员工实际办理

1. 复用链一明确 CV；从原交付或实际维修有限来源读取有效观察。主管原 UI 分别建立 maintenance、first_service、warranty 规则并选本店 service 责任人，必要编辑使用原 rule.version。maintenance/first_service 的天数或公里触发必须有对应真实输入；当日新交付不能凭虚构早日交付来触发日期。使用当日明确的合成用车里程依据时须经原观察表单提交、日期及里程单调且与来源一致；保修截止日须另有明确合成保修依据，不能由销售价、VIN 或保险期限推算。
2. service 点“检查并生成到期任务”，捕获原 `/reminders/generate` 真实响应，逐个核 created case/rule/baseline/current/effect/triggered_on/cycle_key 与 `observation_reminder_bases`。分别打开三类原单接手、联系、按真实结果结案，再次生成应不重复同周期。此前保险 renewal 规则/基准/历史不得停用或改写来凑这三类结果。
3. 首保完成抑制、保养新基准或观察纠正引起的失效/替代只能在原真实维修、观察及独立纠正结果存在后执行。若需要首保完整分支，追加同新交付 VIN 的原预约→到店→首保作业→承担到账→客户接车，然后原 UI 登记对应 first_service 观察并再生成；原洗车、普通维修、联系电话或回访结案不能冒充首次保养完成。尚无这类来源时 HK-112 的抑制要求及 HK-105 的基准变更要求单独保留未测，不宣称全部提醒完整。

本链优先补 HK-105/106/112 的真实内部任务和实际联系；没有外部消息渠道验收，不记录短信已发送。原手动 NewCare schema 不接收这三类 subtype，必须由原 generate 产生，不能绕原规则直接新建提醒。

### 三、客户其它收入单与真实金融关联

1. 优先新建一张可审的小原服务单：复用本轮已交付客户及明确 CV/来源 order，原 UI 选择已启用 ServiceIncomeItem（现财务链有明确 `income_item_id`）；若要新项目由 manager 原主档按钮建立。前台 service/sales 建 other_income，数量为整数千分之一、费用为整数分，逐 fee 明细报价；来源 order 关联使用当前 source_version，不把它误记为代办/代缴。
2. 另一 manager 独立批准当前价格（不得为建单/报价人），经办上传可用 authorization 类合成凭据并确认本版客户授权，原责任任务本人登记各项实际 fulfill。finance 原 receipt 凭据、明确原账户/金额/流水实际 receive，核 PaymentLink、Cash、TenderSlice 和业务款分配；再查原单、履约及现金明细。没有代缴行就明确 pass_total=0，不为收入单编外部办理结果。
3. 同轮 `finance-hk087-090-091-093-096` 的两张原 other_income 单可作金额/账期/预收关联补充源：只取 `finance_sources.service_case_ids/quote_ids/income_item_id/account_id`，核各自原全部 UI 证据、CreditLink 与逐 Statement/CashAllocation。其原 4000 分预收抵用不产生第二份现金，月结实际 3000+5000 分到账独立留源；之前全结清可证明实收，却不能用于应收非零报表。没有完整重核证据不能从那五个 check 直接登记 HK-100 完成。退款/改价为出现真实条件后的分支，不无缘由更正正确原款。

本链只补 HK-100，预收/月结补充不增加 HK-088/089/092/094 或各类应收报表完成数。原 other_income 服务历史不是 `careChoices(source_cases)` 可选类型，不能强填它到原客户车辆历史对话框。

## 精确原接口、模型与可复用小 helper

- `app/customer_service_api.py:149–248` / `app/customer_service.py:113–429` / `app/customer_service_models.py`：`GET/POST /api/customer-service/vehicles`，`GET/PUT /vehicles/{id}`、`POST /observations|history-links`、`GET /history`；`GET/POST /cases`、`GET /cases/{id}`、`POST /cases/{id}/actions/{start|followup|handoff|close|cancel}`；`GET/POST /reminders/rules`、`PUT /rules/{id}`、`POST /reminders/generate`；`GET/POST /history/grants`、`POST /history/grants/{id}/revoke`。普通新建 `{request_id,values}`，修改/办理 `{request_id,version,values}`；生成只有 request_id。每次实际回执核 actor/当前店/原单和请求摘要。
- `web/customerservice.js:16–73,80–159,179–231`：`#care-filters`，`care-new`、`care-action`/`data-action`，`care-observe`/`care-vehicle-edit`，`care_rule_kind`/`care-rule-new`/`care-rule-edit`/`care-generate`，`care-grant-new`/`care-grant-revoke`，`care-q-propose`/`care-q-review`/`care-q-export`。用可见原 lookup/native enum 值，不给隐藏 select 写值；看真实 GET body 和原 h1/唯一按钮再点，不加 sleep、force 或 POST 自动重放。
- `app/questionnaire_service.py:54–149`、`questionnaire_schema.py`、`questionnaire_models.py`、`questionnaire_analytics.py`；API `GET/POST /api/customer-service/questionnaires/versions`、`POST /versions/{id}/review`，review 的 CAS 是 **values.policy_version**；`GET /questionnaires/report`、`GET /questionnaires/export/{questionnaire_issued|questionnaire_answers|questionnaire_distribution}`，`date_from/date_to` 同范围，特定题目的 version_number/schema_digest/question_key 三者齐全。报告按实际发放日和回答日各自范围，不把不同样本数算答复率。
- `app/observation_corrections_service.py:129–155,384–460`、`observation_corrections_models.py`：有效观察及 `observation_reminder_bases/invalidations/replacements`；生成循环全部本店启用 CV，触碰 updated_at/version 并同步有效保险基准。旧周期已完成或手动取消不重新生成；仅真实失效且关闭了旧 open Task 时允许原替代。
- `app/service_orders_api.py:15–104`、`service_orders_service.py:202–262,359+`、`service_orders_models.py`、`web/serviceorders.js`：原 income-items 与 service-orders，actions `quote/approve/authorize/fulfill/receive`，JSON 的钱/数量按原 schema 分/千分之一；原 UI 元输入由原控件换算。批准/授权/履约凭据为 authorization、实际到账为 receipt。`other_income` 不办理外部 submit 动作。
- `app/dossier_grant_api.py:19–124`、`dossier_grant_service.py:443–617`、`dossier_grant_models.py`、`web/dossiergrants.js`：原 `GET /api/dossier-grants/source/{case_id}`、POST根、GET原授权/record/files/具体文件、POST actions approve/revoke。scope 固定 source_case_version/recipient/明确文件列表，expires_at 为含时区且当前之后最多一年；审核人不同于发起人。读取也会增加原访问事实和审计，不能按零所有写入误判，但原业务、库存和资金不得改变。
- 可复用 `customer_service_business.py` 的 `business_today/fields/open_page/submit/refresh/vehicle_facts/care_facts/before_write/after_write`，`sales_business.py` 的 `login_as/employee_choice`，finance 的 `create_service_source/service_facts/upload_original` 或原小型交接 helper。不要调用只能 consultation/complaint/rescue 的既有 `handle_care` 去冒其他 subtype；新增源专属流程，不复制通用执行框架。

## 同次有限来源、权限及旧行保护

- 每个父来源先核同一 evidence_root 下 runner 场景 passed 与相应 checkpoint complete/passed、source/script/provenance 指纹；按固定路径取明确 ID。售前、采购、销售、客服、维修、财务、系统来自同次原 UI，不能拼不同 run、扫描库取最近旧单或根据待执行计划推断终态。
- `customer-service-hk098-107-108-109/business-checkpoint.json` 的 `partial_requirements[HK-099].evidence` 只提供局部 `vehicle/observations/identity_link/vehicle_identity/original_consultation_history`；它仍是局部来源。首维修 `repair-selfpay-hk031-034-044-049-053-079` 的 11 个 report_sources 给明确客户、CV、预约、维修、quote、领料及 Cash；交付销售 `sales-order-hk008-009-011-022` 给明确新 VIN/订单。原自动 `flow_cases.kind=callback` 只是计划来源，不能当 CareRecord 已联系或已答卷。
- service 可合法办理 callbacks/提醒；sales/reception 只能本人客户且本人 Care 责任/建单范围。Care 的 task_key=`care_handle`、Task.role 固定 `customer_service`，实际 assignee 可以为合法 service/manager；不要求夹具另造 customer_service 账号，不借 admin 代办。phone 必须客户 contact_allowed 且有电话；电话/联系结果为明确合成输入，不能猜真实客户资料。
- 问卷/规则/历史授权需当前店 manager；问卷/档案独立复核可以使用不同的已有 admin 当前店有效投影，不错误要求 admin 一定有 UserStore 行。跨店实际接收可优先复用同轮系统 HK-191 原 UI 建立的员工甲（第二原门店 service、第三店 auditor）；仅从该 checkpoint 明确员工/授权来源及外置私密凭据当前密码阶段取用，再核目标店实际角色，绝不输出密码/hash。缺原目标店客户/CV或必要来源时先原 UI 建立，不扩 fixture 预制它们。
- 登录审计落盘后建立原业务旧行基线。每个正向提交只允许本动作有限 append，当前原 Case/Task、指定 CV/rule/policy、指定 source_order 和其源必需列变化；客户、旧 Cash/Payment/库存/会员、旧问卷版本/绑定/回答、旧 CareRecord/观察/附件保持。生成需预先固定全部本店 active CV 的有限 ID 和当前状态，只允许原 control 所需 version/updated_at 等源明确列及有效基准同步，不能排除整张 CV 表。原摘要与原单/流水逐行保护同时留证。
- CV、源单、材料等已被后继业务合法更新，不比对旧 checkpoint 的整行/current_version；重读指定 ID 当前版本和身份/VIN/原不可变来源。拒绝/取消、刷新、查询分别核零业务变化；允许的导出/授权访问审计与会话更新列单独核一次，不删除日志或吞异常。历史观测正文、文件 content bytes、密钥和员工密码/hash 不持久化；文件报告仅实际 sha/size/security 元数据。
- 统一日期来自 APP_TIMEZONE=Asia/Shanghai；JSON null 先按字段解码，SQLite bool 数字与 API bool 分别核型。金额分、物资千分之一不用浮点猜值。版本冲突显示原服务器拒绝并重新核对，未知提交结果不换 request_id 自动重放。

## 登记与执行次序

建议先链一的非空回访/查询/问卷，再链二有源的三提醒；HK-099 跨店/实际首保及基准变更等前置不足的分支保留 partial、not_tested 和具体原因；最后单独链三收入单。各项必须输出原题名/稳定 check_id、实际动作数、请求/响应、DOM/截图、DB有限事实及保护结果；空场景、未提交或缺来源不计通过。六类标准为前端显示、流程简单、文案简洁、后端一致、硬性 bug、来源完整；自动断言与人工体验审阅分别记录，simple_flow/concise_copy/human_review 保持 pending，不虚构员工效率提升或 193 完成。

本次只读源码指纹：`app/customer_service.py` `924f5f5217d667d719c572a6599e76d674908cc06a28c437535f68de77d5e54b`；`web/customerservice.js` `aa669dba86043529f346be8b95e25e0526e80a4bca6dfc910ded7d53e723f4d7`；`app/observation_corrections_service.py` `86553f820af261bd447aded2e154802a8a0497ce339492bdffcf2083aba04acf`；`app/questionnaire_service.py` `3e535d3bae7abe48a9be29ead4082f7735f8a6c9b0cc38103526e89db8e86c59`；`app/service_orders_service.py` `47110414c7510e44b39a7d28c1416f43323310539774c1cf3b992b8ee66ec06a`；`app/dossier_grant_service.py` `3c919aa4686968daef8b6b8e4ebb050476876c4e16097e094793905ca16825af`。静态来源不等于这些新链已执行。
