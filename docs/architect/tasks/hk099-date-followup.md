# HK099 授权截止日人工补测

2026-10-01，M8.1 只读设计；只新增本页，未改生产、测试、夹具、runner 或计划，未导入 app、启动实例、浏览器或执行 SQL。当前三组隔离验证仍由根运行；本页不记录任何新的 passed。HK-099 原题名为“车辆档案”，其原 check 明确要求跨店摘要在撤销和过期后不再读取。

## 日期合同和同实例窗口

`HistoryGrant.valid_until` 是 Date。`app/customer_service.py:370/417` 分别要求创建期限为实际 today..today+365、读取期限 `valid_until >= today()`；`app/db.py:14` 用配置时区，镜像固定 Asia/Shanghai，前端 `web/app.js:79` 同时区。因此 D 日截止的授权在 D 日仍有效，D+1 日 00:00 后原 recipient GET **200、external 摘要消失**；授权原行仍 status=active、version/active_pair 不变，主管授权列表原 UI 显示“已过期”。不应期待 403、自动改状态或删除原行；不调用撤销、停用 CV、改时钟、改数据库或把 HK190 的两分钟 Dossier expiry 作为本证据。

必须预先以完整默认入口及 `--review-after-tests` 保留**同一个** fresh 服务；不要另开 `--serve` 的空实例。自动 `browser-click-report.json` 须 complete=true、passed=true、full_registered_suite_complete=true，53 个固定场景全部终局 passed，193/111/70/9 的原 UI 门禁完整；相关 checkpoint 完整 passed、当前镜像/provenance 指纹相同。此时 runner `run-summary.json` 仍 complete/passed=false、post_test_review=awaiting_external_stop，是正常待人工窗口，最终 provider 与原门禁在请求停止后才核对。不能将存在报告文件、部分父场景通过或 selected run 当完整前置。人工证据另存同实例外部 evidence/manual-review/hk099-date-expiry，不修改原自动报告或 check 结果。

可以在自动全场通过后临近 D 日午夜创建授权并读取，实际跨日后再次点击刷新/重新进入原页。任一等待分段不超过 60 秒；截止日当天已过午夜则必须选当前新 D，不能提交昨日日期。八小时默认登录有效期由实际配置/会话决定；临近前后读时真实重新登录并取新基线即可，不能将会话 401 误记为摘要授权过期。长时间等待不能冒充已完成；机器及原服务须保持运行。原日报 scheduler 在镜像为 off，不启动独立 reminder_worker；原 assistant Worker 的后台记录若发生变化，须区分来源，不能豁免整张审计或业务表。

## 完整自动结束后可用的有限来源

| 来源 | 精确字段和即时重核 |
| --- | --- |
| `customer-followon-hk100-101-102-103-104-110-111/business-checkpoint.json` | report_sources.customer_id/customer_vehicle_id/delivered_order_id/delivered_vehicle_id；来源 CV 必须 active、本店1、同原客户，原交付及关联 HistoryLink 非空。 |
| `customer-reminders-hk105-106-112/business-checkpoint.json` | partial_requirements 中 id=HK-099 的 evidence.source_cv_id/receiver_customer_id/receiver_cv_id/original_local/grant/revoke；source_cv_id 须等于上行 customer_vehicle_id。**本 checkpoint 的 report_sources.customer_vehicle_id 是另一辆提醒 VIN，不能当摘要授权来源。** report_sources.receiver_customer_vehicle_id 须等于 evidence.receiver_cv_id；旧 grant_id 必须实际 revoked/active_pair=null，保留其旧原行。 |
| `system-management-hk189-191/business-checkpoint.json` 与 observations.json | HK191 staff_actions[0].user_id/store_roles 为原 UI 新员工甲；observations 唯一 synthetic_system_private_credentials 只提供当前 runtime 私有文件指针。读取私有 accounts.receiver 当前 current_password_stage，核 id/username，密码不输出、不重置。 |
| `system-followon-hk192-193`、`roles-dossier-hk190`、`inventory-store-scope-hk071` | 本轮均须完整 passed。系统后继 temporary_auditor_restored=true；HK190 report_sources.current_employees.receiver 的 id/store_roles/access_version/private_account_key=receiver 与当前实库核对；HK071 调整的是另一员工乙，不把其 manager 代接收甲。最终 Users/UserStore 是即时权限事实，不用历史 access_version 或旧登录会话。 |
| 本轮 manifest | 来源授权人是 business_fixtures.sales_order.manager_key 对应一店 manager；接收员工甲账号级 sales、实际二店 UserStore=service（另有原三店 auditor，不扩至一店）。两人均 active、must_change_password=false；两店 active；两 CV 分别为 store1/store2、active、customer_identity_id 和 vehicle_identity_id 相同。普通员工办理，admin 不代办、不加权。 |

所有路径来自本轮 manifest/provenance/evidence；私有指针 resolved parent 必须等于该 runtime_root，文件名 system-management-accounts-*、synthetic_data_only=true，不扫描其它实例或真实库。每个 checkpoint/candidate 哈希与本轮镜像的 script_files 对照。新授权仅复用真实双方关系和原摘要，不造客户/CV/GroupIdentity/历史或附件。若来源状态、身份、当前岗位或旧撤销不符，则停报，不能补找其它车或重放原提交。

## 最短原 UI 点击和核对

1. 来源 manager 本人登录、确认当前一店，在原 `#customer-vehicles/<source_cv_id>` 核实际 VIN/客户身份及原非空摘要；接收员工甲独立同源会话登录切二店，在 `#customer-vehicles/<receiver_cv_id>` 核同车关系，原 `GET /api/customer-service/vehicles/<id>/history`=200，此时无 external 摘要。等原 GET body 与正确 h1“客户车辆 · 车牌或VIN”完成，避免旧同 hash 页面或登录 loading 响应。
2. 来源 manager 点击原 `#customer-history-grants` → `[data-act=care-grant-new]`“登记授权”，选择可见本店来源车、接收门店2；填写对方提供的有限 receiver_cv_id、“授权截止日”实际 D、仅合成客户确认摘要授权的独立说明（3..180字），勾选“已确认仅将该客户该车辆的服务摘要提供给所选门店”，只点击一次提交。原新表单生成**新** request_id；不得复制旧 grant 的 request_id 或重复调用其成功 POST。
3. 原 POST `/api/customer-service/history/grants`=201，body 为 `{request_id, values:{from_vehicle_id:<source_cv>,to_store_id:2,to_vehicle_id:<receiver_cv>,valid_until:D,source_reference:<新合成说明>,confirmed:true}}`，无原单/Grant version 字段。保留真实同源 Cookie 存在、X-CSRF-Token 校验、当前店头和实际请求内容的脱敏证据。响应新 grant.id 与列表新增行一致；同对尚有效授权原409需停止核对，不能换请求盲重试。
4. 接收员工原 CV 页实际刷新/重新进入，捕获唯一当前 GET history=200。`external=true` 的条目须逐条等于当前来源本地 history 去掉 case_id 后的最小摘要；仅 number/kind/business_date/completed_date/state/summary/store_name/external 八键。页面显示“已授权跨店摘要”，外部条目无金额、电话、case_id、原单办理链接或文件；其他本店原摘要保持。截图、GET完整脱敏JSON及真实 UTC/Shanghai 时间必须在 D 日。
5. 真实进入 D+1 后接收员工再实际刷新同页，捕获当前新 GET=200、external 条目为0；若有本地原摘要则完整保留，不能把整个 items=[] 写为普遍要求。来源 manager 重新读取原授权列表 GET `/api/customer-service/history/grants`=200，**新** grant 行截止日 D、UI“已过期”；来源 CV 本地非空历史仍一致。截图及请求/DB只读快照须在 D+1，明确未点击 revoke、未改 CV/身份/权限。旧成功请求不重放，不再创建同对授权来间接写旧 grant。

## 最少 SELECT 字段及旧行保护

仅从本轮 `manifest.database_path` 仓库外 synthetic.sqlite 以 URI mode=ro、PRAGMA query_only=ON、短读取事务核对；不导入 app，不输出数据库全量客户资料/附件 BLOB/密码或会话散列。参数只取上表固定有限 ID，新 grant/receipt/audit ID 来自唯一实际成功 UI POST；查询参数不打印。

| 表 | 只读关键列 |
| --- | --- |
| users / user_stores / stores | users.id/active/must_change_password/role/access_version；user_stores.user_id/store_id/role；stores.id/active。当前姓名/用户名只作合成员工确认，不读取 password_hash 或会话 token/hash。 |
| care_customer_vehicles / group_identity_links / group_identities | CV id/store_id/customer_id/customer_identity_id/vehicle_identity_id/vin/active/version；两店客户 link.identity_id/local_kind/local_id/confirmed_by；两个 Identity.id/kind；不得把同 VIN 或同电话代替明确同人身份。 |
| care_history_grants | id/version/from_store_id/to_store_id/from_vehicle_id/to_vehicle_id/customer_identity_id/vehicle_identity_id/valid_until/status/active_pair/source_reference/granted_by/revoked_by/revoke_reason/created_at。跨日后上述原值全不变。 |
| care_history_links / flow_cases | 仅有限来源 CV 的 link.id/store_id/vehicle_id/case_id/summary/source_reference/confirmed_by；来源 Case.id/store_id/number/kind/business_date/completed_date/state/customer_id/vehicle_id。既有记录及原金额/任务/流水不修改。 |
| care_receipts / audit_logs | 新 receipt.id/store_id/request_key/actor_id/digest/result 与本次 grant 对应；digest 为 SHA256 原 `["grant_history", values]` 稳定 JSON（日期 ISO）。新唯一 audit actor_id=本次 manager、store_id=1、action=care_history_grant、entity_type=care_grant、entity_id=新grant、reason=实际说明，before_data/after_data 原 JSON null。仅输出必要元数据/摘要，不输出任何秘密值。 |

创建前基线在真实登录审计完成、页面请求稳定之后取：仅允许 **1新 HistoryGrant＋1新 CareReceipt＋1新 AuditLog**，全部旧行逐列不变；不允许原 CV touch、旧 Grant 改写、Case/Task/Event/历史/观察/GroupIdentity/附件/现金/库存/会员写入。GET 读取与跨日等待不制造上述事实；全原业务表及全部旧行保持，新授权也不自动写为 expired。会话重新登录的原 LoginAttempt/LoginSession/本人 login 审计另独立记准，放在新的只读基线之前，不能整表排除 audit 或将后台未知写入当合法 GET。BLOB仅在本地内存校验/hash，证据不得默认字符串化或 base64 化。

收尾以该实例外部 runtime/stop-requested 正常停止，保持原自动证据并让 runner 完成 provider=0真实模型/0外部网络、全登记/UI覆盖/终局退出码门禁；人工结果另记，不在等待前填通过。真正跨日还未执行；HK099 自动现有 partial、逐原单/逐文件 Dossier 条件及其单独事实、PG/并发/员工体验/生产门槛保持原定义，由根决定整体验收登记。

## 当前只读来源

本页读取当前 `app/customer_service.py` SHA256 `924f5f5217d667d719c572a6599e76d674908cc06a28c437535f68de77d5e54b`、`customer_service_api.py` `b83bb4c354dba5ecddf58c2d76c7f7cf2811e657918e89c8fd8062469f6c241d`、`web/customerservice.js` `aa669dba86043529f346be8b95e25e0526e80a4bca6dfc910ded7d53e723f4d7`、提醒脚本 `b16cb44633043585d1f9693041bc7cf956891334ee333b0d66894821ba31093a`、客户七项 `a550e24088bff8facb9c8d60ae044f301f89e8ebc5fedc33203c27998352ea18`；原 catalog SHA256 `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`。这些只证明研究来源，不是本轮53场/过期通过证据；实施人工窗口必须重新核对当次实际 provenance 与父终局。
