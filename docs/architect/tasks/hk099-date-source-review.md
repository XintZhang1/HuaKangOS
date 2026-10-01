# HK099 真实跨午夜补充草案源码审阅

2026-10-01，独立只读审阅。对象为仓库外 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/launches/hk099-date-review-draft.py`：366行，SHA256 `eb2f78f25ac6e626843eac3c2fdf21fa290bcff70ba1489a25a3752cd75ad858`。标准库 AST 解析成功，未导入/执行该草案或应用、运行浏览器、执行 SQL、读取数据库/私有凭据/真实配置；审阅者只新增本文。

## 静态结论及调用前提

未发现阻止草案按既定两阶段合同调用的确定源码错误。before 必须使用唯一同轮、完整53场景通过且仍 awaiting_external_stop 的原合成实例；after 必须保留同一实例与同源/脚本原件，并在真实上海 D+1 执行。不能拿已停止实例、不同 run、selected 17/11结果或旧 report 代入。本次没有执行任一阶段，不记真实 Date 通过。

依赖为同目录 `native-review-draft.py`，本审阅已复核其435行 SHA256 `4ccf21b0e0729319606c3019e29f0fa6b14a8521a58a3a515ce813d5acad4198`。Date main 只在实际调用时导入该外部模块并调用 preflight；preflight 从冻结镜像脚本目录载入原 helpers。它核53注册/完整报告、同轮40业务 parent、193/111/70/9导航计数、原件指纹及保留阶段，不要求HK099 partial变成已验收。Date将此依赖字节SHA与自身SHA写入before文件，after要求精确一致。

## 精确原来源和本人身份

草案 source 用 customer-followon 的 delivered_order_id/delivered_vehicle_id/customer_vehicle_id，而不是 customer-reminders 另一个提醒 VIN；要求 HK099 partial 唯一、status=partial、acceptance_check_submitted=false。原 source CV/交付原单/实车在店1、接收 CV在店2且都启用；原客户、实车、VIN、customer_identity_id、vehicle_identity_id及已确认 GroupIdentityLink 逐项绑定。原交付 state=delivered，有真实同店 care_history_links。原撤销授权必须全行等于 partial.revoke、仍 revoked且 active_pair为空；新授权前同对车辆没有active授权，after只接受本次唯一新grant。

manager 为原 sales_order fixture 的当前店1 manager，核启用/已改密及 user_stores。receiver 为 roles-dossier HK190当前员工甲，核其ID仍等于系统HK191新员工甲、账号sales、店2当前service、无店1权限、启用/已改密、当前access_version与恢复后的逐店岗位。没有临时提升、改权限或恢复角色动作。

运行时 receiver_password 只接受同runtime的原私有system-management账户指针、schema1/synthetic标记、同ID/username和**精确等于HK190 current_password_stage**的阶段键；密码只进入原native_login内存，原 private=True填写与Evidence脱敏继承。本次审阅只读其取值与保护逻辑，未打开指向的文件或密码。

## before：原D当天一张授权

`CR.day()` 原 helper 为 `datetime.now(ZoneInfo('Asia/Shanghai')).date()`；stamp同时记录UTC和上海时间。原服务 `app/customer_service.py` 取 `app/db.py.today()`，配置默认Asia/Shanghai；隔离runner的child_environment不继承APP_TIMEZONE。原UI `web/app.js:79 day`也固定上海日期。草案不改时钟、不伪造日期或等待跨午夜。

before保存真实D，在提交前再次检查实际day仍等于D和原表单valid_until输入为D；完成当天页面核对后再次检查仍D。若时间跨过午夜则失败，不重放或新造request_id求通过。原服务要求valid_until从today起且不超一年；跨午夜提交本身也受原服务合同约束。

先由原manager和receiver分别native_login；`SYS.fresh_identity(e,seed,contexts)`/`native_login(e,account,password)`/`switch_store(e,store,account,role)`签名与当前系统脚本一致。原login的before_write/audit_one/after_write核单条真实login审计、旧业务行及其他员工会话不变，切店仅原GET重取当前岗位。两次登录与授权业务基线分别记录。

授权完全沿原 `customer-history-grants` 页面、care-grant-new表单、`CR.fields(e,values)`和 `CR.submit(e,actor,store,path,guard,status=201,render=...,action='grant_history',payload=lambda r:r['values'])`。fields虽在customer_reminders模块导入，其定义实际为customer_service_business.py:201，与使用参数一致。原API `Grant` schema 的from_vehicle_id/to_store_id/to_vehicle_id/valid_until/source_reference/confirmed逐项匹配；confirmed=True不替代显式表单点击。

`CR.Guard` 的appends严格是 care_history_grants=1、care_receipts=1、audit_logs=1，无updates。它比较全部原业务表摘要，允许表也要求旧行所有列不变及新增精确数量、原店/本人。原grant_history新增/flush授权与audit，原_execute在同事务追加CareReceipt/commit。草案检查实际POST201、Cookie/CSRF/x-store、输入/原输出、grant版本1/active_pair/同身份、原request/receipt digest与返回、原审计action/entity/id/reason。原撤销grant全行仍保留。

原接收车辆history必须只在当天增加来源原历史的八键摘要：number/kind/business_date/completed_date/state/summary/store_name/external，不能带case_id、金额、电话或附件；接收本地旧行仍完整相等。`web/customerservice.js:86`的实际strong包含门店/日期及“已授权跨店摘要”，草案用has_text准确匹配该子文案，检查对应article没有按钮或原单链接。manager授权行原第4列D、第5列“有效”与实际UI列一致。

网络守卫只有两次单次原POSTlogin窗口和一个原POST history/grants窗口，其余非GET/HEAD/OPTIONS全拒绝，并继续原Evidence外网守卫。它不能发revoke、业务确认或第二次grant。若201已知而随后读取失败，预览保存actual_created_grant；没有成功retained文件，after拒绝，重复before也会因同对active授权拒绝，不能盲重放。

## after：真实D+1只读失效

after首先加载同run manual-review/hk099-date-expiry下的retained-before-midnight.json及同目录phase-preview，要求before_complete=true、preview before/native observed/terminal clean、指针一致、原五个run字段、源/脚本自动原件及两外部草案SHA一致。真实day必须恰为D+1；D、D+2或不同实例均拒绝。

在新登录之前，整份原业务摘要必须仍等于before.after_day_read_business，核真实等待期间没有原业务变化。receiver/manager登录仍分别走原系统写审计守卫；**after不是全数据库零写入**，其两次合法login审计与会话记录不混入history GET的零业务写断言。

原 `CR.history(e,vehicle_id)` 和 `CR.read_page(e,route,title,path)` 都在每个GET导航前后核全部原业务行摘要。接收 history 现在必须全行等于原 receiver_local、无external摘要，实际panel也无授权摘要strong。原grant数据库全行必须仍等于before.grant、列表status仍active，UI状态是“已过期”；原valid_until仍D，原撤销grant全行相等，源店本地history整体不变。原server service_history只用status=active且valid_until>=today筛选，并不因读取而撤销/写授权；UI相同日期条件仅显示已过期。这是要实测的真实日期读取失效，保留原事实。

after grant计数必须0；不会revoke原授权，不能靠写状态让外摘要消失。最终再次检查真实day仍D+1，并记录当前返回/页面、真实时间及retained SHA。

## 异常与终局证据

paths_read直到全部context/seed/browser关闭完成才设true。任何来源/页面/提交/日期/关闭异常都写native_phase=failed；finally捕获finish_error、重核自动原件、pending_response_jobs、page_errors、外网尝试、5xx、denied writes与精确2 login/1或0 grant计数。仅paths_read且terminal_clean时才写observed/返回0，并在before此时才落成功retained文件；否则date_contract_observed和real_date_expiry_observed清false/返回1。没有原生草案旧版关闭异常覆盖failed的问题。

输出全部位于新的manual-review子目录，原full53 report/checkpoint/count与HK099 partial不改。阶段文件始终complete=false、full193_business_acceptance=false、人工PNG/评分/员工/最终provider pending。真实两阶段成功也只补本次同车授权Date条件；原HK099其他需求、193逐项验收、真实模型/PG/Linux/员工/ClamAV及生产门槛仍单独保留。主任务实际原runner正常停止、CLI0和provider终局仍须另核。
