# 客户车辆档案与原提醒下一批范围

2026-10-01，M8.1 只读研究。仅新增本页；生产、所有候选和已注册脚本、夹具、runner、目录、计划均未修改；未导入 app、启动服务或执行浏览器。以下是拟实施合同，四项均未实测，不登记 passed。源码实际入口以 `app/customer_service_api.py`、`customer_service.py`、`customer_service_models.py`、`app/observation_corrections_api.py`、`observation_corrections_service.py`、`observation_corrections_models.py`、`web/customerservice.js`、`web/observationcorrections.js` 为准。

## 原四项与可计范围

| 原条目 / check | 最短原输入→结果 | 必须分别保留的事实 |
| --- | --- | --- |
| HK-099 车辆档案 / HK-099-business | 本人原 UI 新建并编辑本店 CV，明确客户/VIN/车型/集团身份和实际观察；查看父已交付 CV 的真实本店摘要；二店本人另建与这辆已交付车同客户身份、同车身份关系，由来源店主管授予 ≤365 天摘要读取，接收店实际查看后来源主管撤销，再读不含外部摘要 | CustomerVehicle/VehicleObservation、双方 GroupIdentity/Link、ServiceHistoryLink、HistoryGrant/version/status/active_pair、CareReceipt 与原审计。相同 VIN 不代替相同客户身份；摘要无金额、电话、外部 case_id、办理按钮或文件权限。真正到期分支尚缺跨截止日证据，不能因撤销或车辆停用替代“过期”而报完整 check。 |
| HK-105 保养提醒 / HK-105-business | MANAGE 原 maintenance 规则→OPS 原检查生成→本人接手/两次真实跟进/结案；另对原观察有据纠正并独立批准，旧开放提醒取消、保留历史，按有效新基准再次生成关联替代任务后真实办结 | Rule/Basis/Invalidation/Replacement、CareCase/Record、FlowCase/Task/Event；日期与独立公里来源分别核对，周期至少一项且提前量严格小于周期。生成和结案不表示外发消息或已做保养。 |
| HK-106 保修提醒 / HK-106-business | MANAGE 原 warranty 规则只配置 lead_days；本人有效 warranty 观察的 valid_until→OPS 原生成→本人接手/跟进/结案；有据撤销该手工误登记观察并独立批准后再检查，不再使用失效期限 | 原截止日、有效观察及 effect、Basis/Invalidation、旧已结案记录不改状态；保险/保修不得填周期公里或猜期限。同一有效截止周期去重。 |
| HK-112 首保提醒回访 / HK-112-business | MANAGE 原 first_service 规则按 delivery 基准和独立 odometer 触发→OPS 原生成→本人接手/两次跟进/按明确预约结果结案；之后另以原客户车辆 UI 登记有明确合成凭据的 first_service 观察，再检查须抑制该车首保生成 | 首保来源/阈值/Basis/current、本人 Task/Record；预约回访与实际首保观察分开，不能从 close/维修旧单/组合权益推算已做首保。已有有效 first_service 即抑制，不以领取新任务数提高成绩。 |

原目录 `ui_action` 冻结上述四项；HK099 的共享 workflow 还含原单快照/逐文件独立授权，这些不由摘要授权替代，仍保留各自未测条件。当前建议三项完整提醒候选＋HK099 明确 partial；HK099 的过期证据齐备后才可提交完整 check，不更改目录门槛。

## 同轮最小前置与身份

直接父 `customer-followon-hk100-101-102-103-104-110-111` 必须本轮报告和 checkpoint 完整 passed；其七项闭包为售前、整车采购、主档、客服四项、销售交付、物资采购、首维修。仅读取它的 `report_sources.customer_id/customer_vehicle_id/delivered_order_id/delivered_vehicle_id/sales_callback_id`，核当前关系、源单和联系意愿，不继承其 HK099 partial 为本批完整成绩。新本店 CV 可以由 `sales_peer` 对本人客户登记；原 delivered CV/观察/原销售、维修及已结案回访保持。

第二直接父 `system-management-hk189-191` 必须实际完整 passed。通过 HK191 `staff_actions[0].user_id/store_roles` 取原 UI 新员工 receiver，核账号级 sales、二店 UserStore=service、active、must_change_password=false。仅从该父 `observations.json` 唯一 `synthetic_system_private_credentials` 指针读取本轮 runtime 私有账户的 `current_password_stage`；先将所有私密字符串加入 secrets，密码、User.password_hash、会话/hash 不入证据。若同轮 `system-followon-hk190-192-193` 已执行，也须完整 passed/原临时授权恢复并重读当前 UserStore；不取其 auditor 临时身份办理业务。无需新增 fixture、重置员工或授予旧账号二店权限；接收摘要由二店 service 实际登录，来源授权及规则由一店 manager，原观察纠正由 service 申请、另一 manager 批准，admin 不代办。

二店 service 从原 `#master/customers` 新建与父客户姓名/电话一致、明确已核对同一人的本店独立 Customer；再从 `#customer-vehicles` 新建 CV，原 `[name=customer_identity_id]` 显式填父已交付 CV 来源页已核编号、同 17 位交付 VIN，确认关系。新 customer 的 owner 为实际创建人；集团 customer identity 和 vehicle identity 必须分别匹配。摘要授权 from_vehicle_id 固定父客户七项输出 `customer_vehicle_id`，其真实销售/回访 history_links 必须非空逐条对照，to_vehicle_id 固定这次二店新关系。一店提醒新 CV 与父客户同人但采用本批另一新合成 VIN，避免追加第二个有效 delivery 到旧车；两个用途不能混成同一个编号。二店只登记关系不造保养/保险、订单或金额。原客户重复提示必须明确人工选择，不按姓名/电话自动合并。

## 原表单、字段与回执

`#customer-vehicles` 原 `[data-act=care-vehicle-new]` / 详情 `[data-act=care-vehicle-edit]` / `[data-act=care-observe]`，创建 POST `/api/customer-service/vehicles`=201，编辑 PUT `/{id}`=200，观察 POST `/{id}/observations`=200。创建 values 为 customer_id/customer_identity_id/vin/plate/model_name/source_reference/confirmed；编辑 version＋plate/model_name/active/reason，不改 customer/VIN/身份/来源/created_by。观察携带当前 CV version＋kind/observed_date/odometer_km/valid_until/evidence_id/confirmed/source_reference；公里是 0..3000000 整数，实际日期 ≤当前业务日且 ≥2000-01-01，按有效观察顺序日期和公里不倒退，保险/保修截止日不早于观察日，其他种类期限为 null。

`#customer-history-grants` 原 `care-grant-new`：POST `/api/customer-service/history/grants`=201，values 为 from_vehicle_id/to_store_id/to_vehicle_id/valid_until/source_reference/confirmed；来源当前店 MANAGE，双方 CV active且两个 identity相同。已有效同对关系 409；365天以上或身份不符422。原 `care-grant-revoke`：POST `/{id}/revoke`=200，携带当前 grant version、reason，仅变 status/active_pair/revoked_by/revoke_reason/version，撤销双方都可由其本店主管办理。接收方由原 CV 页面 GET `/{id}/history` 展示摘要，未授权/撤销后没有 external 条目，其他车/店摘要完整不变；原单与附件不因 grant 获权。

`#customer-reminders` 原 `[name=care_rule_kind]`、`care-rule-new`/`care-rule-edit`；POST `/reminders/rules`=201，PUT `/{id}`=200。values=name/kind/interval_days/interval_km/lead_days/lead_km/assignee_id/active，编辑带当前 rule version，type 不可换，每店每 kind 唯一；若已有该种规则，只明确维护那一行和精确字段，其他规则/旧 Basis 快照不变。原 `care-generate` POST `/api/customer-service/reminders/generate`=200，只有 request_id；禁止正例用 context.request/fetch 代点。员工来源 original lookup/employees?subtype 必须实际可见、按本店 TYPE_ROLES 选择，三种提醒配置 MANAGE、生成/办理 OPS（manager/admin/service/customer_service）；sales/reception 可维护本人 CV，但不能生成提醒。

原 `#customer-service/{case_id}` 先等待正确 GET/唯一可见 `care-action`，依次 start={}；两 followup={channel,contact_result,note,next_due_date}；close={result,note,satisfaction:null,recommend:null}，均 POST `/cases/{id}/actions/{action}`=200，顶层 request_id/version/values。Task 为本单 care_handle， assignee/owner/source/currentstore 重验；phone 仅有电话且 contact_allowed 时，预约/联系不伪称真正保养完成。每步当前 CV 由 control_vehicle 合法 touch version/updated_at，Case/Task/Record/Event/Care.result 列按动作有限允许，旧记录不可更新或删除。

CareReceipt 精确 SHA256(JSON `[action,payload]`，sort_keys/ensure_ascii=false/separators(',',':')，日期原 ISO)：vehicle_create=v；vehicle_update/observe={id,version,**v}；rule_save={id:规则id或null,version:当前或null,**v}；grant_history=v；revoke_history={id,version,reason}；care_{action}={case_id,version,**v}（close answers=null 时原服务先剔除 answers）。结果、actor/store/request_key 必须精确匹配。生成当前已委派 `observation_corrections_service._execute` 的 CorrectionReceipt action=generate、payload={day:业务日,automatic:false}；不是新 CareReceipt，也不是 legacy generate_reminders digest。未知结果不改请求号重放。

## 确定阈值、纠正与全店集合守卫

本批新 CV 的显式合成实际资料可取 delivery=D−30、1000km，独立 odometer=D−1、4900km；日期与里程来源分别填写，取页面/同一 Asia/Shanghai 业务日 D。maintenance 用周期30天、提前0、公里0；初次生成后 service 由原“原观察纠错与有效版本”`#observation-corrections/vehicles/{id}` 的 `oc-new` 对该 delivery 更正为 D−29，公里仍1000，说明明确误录依据。POST `/api/observation-corrections/cases`=201 顶层 vehicle_id/vehicle_version/observation_id/base_digest/operation=replace/proposed/reason/request_id；上传本纠正单 evidence 原件，再 `oc-action` submit→另一 manager approve，各带原 Case version/values/evidence_id，Review另带reason。独立 Review/Effect/CorrEvent/CorrectionReceipt 保留，原 Observation 字节及 ID 不改；待复核旧提醒只允许内部跟进/交接/取消，原 phone 外联409，批准后有限旧开放提醒 cancelled且 Task关闭、Invalidation.closed_open_task=true。maintenance lead_days 明确改1使新有效目标D+1到期，替代 Case 的 ReminderReplacement 指向准确旧单；完成旧单不回退。原件只留metadata＋length/SHA，BLOB仅内存核验。

first_service 可用 interval_days=0、interval_km=4000、lead_days=0；lead_km=99 对4900km不触发，实际改100后恰达阈值。有效首保观察另原 UI 登记 D、5000km、独立合成完成凭据，不能拿同轮别的 VIN 已修完代填；再生成无该车首保新单。warranty 原观察 D、5000km、valid_until=D+9；规则 interval_days/interval_km/lead_km 均0，lead_days=8 不到期，实际改9恰触发；两次检查及已结案同周期均不重复。另从原纠错入口 retract该手工 warranty，上传原件→submit→另一主管 approve，精确保留旧 completed case，仅追加失效记录/跟进，失效观察不再生成；不能修改真实保险原单自动生成的 observation。

**每次 generate 前独立 SELECT 全本店 active CV（≤500）、全部 active rule、有效 Observation/CorrectionEffect/InsuranceInvalidation、待复核 Correction、当前 CareCase/Task/ReminderInvalidation/Replacement 和完整关联保险来源**，按原 `_candidate` 顺序计算集合：first_service 已有有效完成观察则排除；保养取最后有效 delivery/maintenance/first_service，首保只 delivery；保修只 warranty.valid_until；日期或独立公里任一到阈值触发。当前 measured 仅独立实测，实际保险结果 km=null不得造0。基准同 observation 或保修同有效截止周期，旧 pending/working/completed 或未被失效流程关闭的 cancelled 阻止重复；只有有明确 closed_open_task 的旧取消单可进入替代 eligible，reminder_key按原baseline/current effect与eligible计算。rule经办/批准岗位变化精确 skipped而非漏掉。

原生成对**全部已枚举 active CV** 调用 control_vehicle，合法仅 touch其 version/updated_at，0 created也不是全库零写。先只读检查 sync_vehicle_insurance_bases 的有限实际已终止原链是否全部已有失效记录；若仍有待同步来源，明确该源 Order/Result/Termination/Review/Consent/Application/Observation/Care集及新失效追加，无法精确核对即停，不豁免整表。created必须等于全部预计算 `(CV,rule,baseline,current,effects,eligible)` 集合，每个恰 Case+Care+Task+Record+Basis及两 Event/两 Audit，额外 Replacement数按eligible精确；统一一条 CorrectionReceipt。旧全部 Observation/Effect/Basis/Record/Receipt/规则快照/历史Event不动；库存、Cash、会员、订单、其它店全部旧行保护。名单外 CV/Case/Task不能因为批生成而放宽更新。重复检查不追加Case/Record/Basis，但仍按上述有限CV touch及一条原回执核对。

## 未决边界与冻结来源

真正授权过期必须业务日越过原 valid_until（today有效，次日才失效），本批同日 UI不能提交过去截止日。可以先授 valid_until=D并留首次可读证据，跨日以同一外部实例/原 grant 再读，按原指纹条件独立记录；当前不启动等待、改OS时钟、monkeypatch today、SQL造过期或fixture改grant。停用 source/target CV 会阻断外部历史，但只是另一真实失效原因。跨店文件逐件批准/下载、资料原单快照、完整超过500辆/并发/PG/Linux/真实联系/ClamAV/员工体验/生产仍未测；所有负向422/409保全原业务，403若真实refusal则只允许精确对应追加，不笼统全库零写或整表豁免。

原目录 SHA256 `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`。本页研究来源14文件合同指纹 `26bb634ed13763d5c03e19b06a5e06ed72400374db1040ee1d90d5fa72f17230`：上列8个app/web文件＋`tests/browser_click/business_acceptance_catalog.json`、`customer_followon_business.py`、`system_management_business.py`、`system_followon_business.py`、`app/flow_api.py`、`web/customerchoice.js`；算法为每仓库相对路径→原bytes SHA256，JSON sort_keys/separators(',',':')再 SHA256。研究时客户脚本 `cd2d8d8b9b04c0bbadf5a99d147bdb754301b879e4545b584c7cc05336749a1e`、系统原两项 `7a0425a770c8db492f7489a0190364deac062626be3d4af29be56a3a8ed3bdce`、系统后继 `08603ff77f3c7d4eaf8e6da76c688a5aced595bd4228e77231bcb07133e762b0`。这些是静态合同来源，不是本轮父场景 passed证据。根精确补丁后建议只授权 `tests/browser_click/customer_reminders_business.py` 与 `docs/architect/tasks/customer-reminders-click.md` 两新文件，源码缺口先报告，不增通用平台或改变业务规则。
