# 系统管理五项真实点击研究

2026-10-01 根注册及执行追加：`V/browser-click/business-system-20261001-04/evidence/`选定1/1退出0，HK189/191两项自动检查完整通过，166动作/50点击、25.69秒、页面异常0。原路径判断改为本次稳定provenance的真实仓库和外部镜像，凭据仍外置且动态脱敏；本人改密按钮按原头栏/主栏各自缩小选择；切店先等待原实际首页和本店身份，不能把旧parameters页当切店结果。这些是测试装置修正，未改生产或密码/权限守卫。material-system01路径误判、system01两处同名动作、system02切店时序失败原件保留；system03错误显式浏览器名称在启动前被拒绝，无执行成绩。HK192/193仍partial、190及最后可用店分支not_tested。当前23场景联合automatic-business06正在运行，定向通过不替代联合成绩或人工体验。

## PATCH-M8-4-BUSINESS-193-09 未注册候选交接

2026-10-01，按根登记补丁只新增 `tests/browser_click/system_management_business.py`，本任务页为作者本人维护；生产、fixture、已注册脚本、runner、源目录合同、计划没有修改。场景导出 `SYSTEM_MANAGEMENT_SCENARIOS`，名称 `system-management-hk189-191`，单场景上限420秒；根负责后续镜像、注册与实际运行。当前仅候选已落盘和静态审查，不是浏览器运行成绩。

- 两个完整**本批自动 check** 为 `HK-189-business`（机构管理）和 `HK-191-business`（员工管理）。原 admin 表单新增第三家合成店、编辑名称；原员工表单新增两个随机账号，核默认销售、没有默认门店、集团汇总未选，明确甲为二店service／新店auditor、乙为一店manager。两名本人分别在全新浏览器 context 首次改密、实际重登录，核账号默认岗位与当前店岗位分离。
- 仅新员工甲的原编辑、停用、启用使 access_version 精确推进，原 UserAccessReceipt 绑定 actor、target、request_key、原版本、原请求和审计；每次删除全部甲的旧会话，旧页面实际原 `/api/auth/me` 返回401且回登录页。管理员只为甲重置；重置前形成两个真实会话，两页都失效，再本人首次改密和重新登录。本人再次改密覆盖错误旧密码400、新旧相同422、原minlength不足12位0POST，拒绝保持全部原业务与登录会话；成功清Cookie并撤销两个本人会话。
- 仅本批新店成为当前店后停用，核原表单成功与真实回到第一可用店、原中文提示；原编辑重新启用并切回新店重新取本人岗位。原两店、所有已有员工（包含原密码哈希）与原员工逐店关系全行保持。最后可用店拒绝因需要停原两店，保持conditional／not_tested，不能称已测。
- `HK-192` 只记录本人密码和实际安全配置目录子范围；`HK-193` 只记录本次非空门店改名审计原详情、actor/ID/前后资料、UTC事实与上海可见时间一致。两项始终partial、`acceptance_check_submitted=false`，没有提交其 `-business` check。机构图片、类型／ID筛选、其他岗位非空审计范围／分页未测；`HK-190` 原跨店逐件授权／独立批准／接收／撤销／到期和换岗失效全部未执行。

随机密码（含错误旧值及不足长度临时值）只由运行时生成，预先加入 Evidence 实际共用的 `e.secrets` 列表；整份动作、网络、观察使用同一个脱敏词表，所有密码填写用 `private=True`。完整恢复记录只在本次外部 runtime `system-management-accounts-<随机后缀>.json`，首次O_EXCL创建、0o600，保存两个新账号原ID与各阶段密码，不修改原credentials文件或账号。User／LoginSession 原行仅在内存比对，不写password_hash、会话哈希、Cookie或CSRF值到报告。新 context 均附加已有同源网络防护且最终关闭，没有复制Cookie、API正向提交或SQL业务写。

每次原写保护全部其他表的行哈希和被允许表全部旧行；只允许精确指定新 Store／User 更新、新 UserStore、单条 AuditLog及单条UserAccessReceipt，其他员工LoginSession逐行保持。创建精确校验新增ID集合，编辑不允许意外新增／删除，库存／现金和原业务无修改。原 GET 导航及只读日志详情另做整库原业务不变。网络失败或结果不明只失败保留，不重试／重放；checkpoint按两项独立判据记录，失败时其他未完成项为partial或not_tested，人工流程／文案始终pending，business_accepted与full193均false。

静态自查：Python AST成功；22处数据库 `rows` 调用全部仅SELECT；没有app导入、request.post、SQL写或browser启动；已按实际原 API/schema/UI 手工核对 StoreInput、UserInput／UserUpdate、PasswordInput、ResetPasswordInput、原审计global0、收据request_data排除request_id与实际角色中文。脚本 SHA256：`b26b967f27d105b6aac4c12f0774566b66eb22b24bcc5684466acc74130579cf`。跨代理只读短审与原生实际点击仍待完成；Windows/Linux、SQLite/PostgreSQL、人工体验各自留证，不继承其他场景成绩。

同日交叉短审追加：test_inventory只读核对上述脚本及本页候选边界，未发现两个本批check的实质静态误配；确核默认销售／空勾店、UserStore/CAS及Receipt.request_data排除request_id、本人密码／重置及原me401、第三店停启真实回店、旧行／其他会话保持、唯一真实login审计和整份共享密码scrub。审阅未编辑、未导入app、未运行浏览器。脚本指纹保持不变；作者现正式冻结两文件交根接线，实际UI执行、192/193未办范围、190授权、人工六类标准及完整193仍待验证。

以下保留最初只读研究与后继原授权链建议，**不代表本批已编写或执行其范围**。

2026-10-01。只读研究，依据当前工作树、193 源合同与原工作流；未登记或编写候选脚本，未修改生产、fixture、已注册脚本、目录或计划，未导入 app、启动实例或浏览器。HEAD 为 `5069b2bcc9f580ebb9d70780769049a14a6de946`；当前工作树有根已授权的未提交实现和点击候选，不能以 HEAD 代替实际源码指纹。本页首次建立，没有覆盖其他人的任务记录。

全部五项 `execution_status=not_tested`、`manual_review=pending`、`business_accepted=false`；本研究不继承导航、旧场景或其他模块的成绩。

| ID／原标题 | 唯一 check_id | 原入口 | 本轮完整业务边界 |
| --- | --- | --- | --- |
| HK-189 机构管理 | HK-189-business | stores | 新店新增、编辑、真实员工门店配置、停启用与权限重读；历史原业务保留，当前店停用后管理员实际切到可用店。最后可用店拒绝分支另需安全执行窗口。 |
| HK-190 角色管理 | HK-190-business | users；dossier-grants/received | 默认岗位与逐店岗位分离、版本化改权、旧会话撤销、重新登录后的原权限；另包含跨店原单及逐件文件的发起、独立主管复核、指定本人读取、换岗／到期／撤销失效。只改账号不能通过整项。 |
| HK-191 员工管理 | HK-191-business | users | 实际新增随机合成员工，默认销售且门店不默认勾选；明确逐店岗位，首次改密、登录、对应原业务范围；编辑／停启与他人重置密码均留痕，旧会话失效。 |
| HK-192 参数设置密码修改 | HK-192-business | parameters | 安全配置目录与部署只读边界；新增合成员工本人原密码校验、改密及重新登录。原工作流还有管理员更换／恢复登录图片，应单列已执行或未执行范围，不把个人头像当成原接口。 |
| HK-193 系统日志 | HK-193-business | audit | 本次非空原业务审计的时间、员工、原 ID、前后资料、原因与 UI/API/DB 一致；真实分页／详情、岗位及门店范围；不显示密码、凭据或推理。目录的类型／ID 筛选目前没有原 UI 控件，见下文。 |

## 已存在的身份与最小新增事实

`fixture_server.py` 已提供随机合成 admin 和 sales 两店身份，以及一店 manager、sales_peer、inventory、finance、service；所有原密码均在外部 runtime。两店均真实启用。无需修改 fixture 为系统管理预制账号或状态。

建议先由现有 admin 在原界面新建第三家合成店；名称、编码使用本轮唯一随机后缀。随后原界面新建两个随机员工：

- 接收员工 R：账号默认 `sales`，明确只勾二店 `service`、新店 `auditor`，无一店授权；首次登录由本人改密。这样可证明账号默认岗位不等于当前店岗位、原店单据不能直接读取，以及集团汇总只包含获授汇总的管理岗位店。
- 独立主管 M：账号默认 `sales`，明确一店 `manager`；首次本人改密后成为不同于发起人的真实主管。原角色管理没有账号审批流程；这名主管只用于原 dossier 的独立复核，不能把新增账号包装成主管审批。

所有新增／自改／重置密码仅作用于这两个本轮新建合成员工；不改已有 fixture 员工或任何真实账号密码。随机密码仅存当前执行内存和外部权限收紧的凭据文件，加入既有 Evidence 的脱敏词表；动作／观察／checkpoint 不保存密码、password_hash、会话哈希或 Cookie 值。密码哈希比较只记录“是否变化／是否保持”的布尔结论，旧会话只记录计数与失效结果。

## 最短核心链：门店 → 员工 → 改权／密码 → 非空日志

1. admin 在 `#stores` 点击新增，提交 `POST /api/stores`，再原编辑 `PUT /api/stores/{new_id}`。核对原 `stores` 精确行、唯一 `create_store/update_store` 审计、UI 名称／编码／启用状态。管理账号／门店的审计归属 `store_id=0`，不能误断为一店审计。
2. admin 在 `#users` 打开新增。提交前核对默认 `role=sales`、`can_group_summary=false`、所有 `store_ids` 未选；未选门店不得产生有效员工。原表单明确选 R/M 门店及岗位，提交 `POST /api/users`。`users.must_change_password=true`，`user_stores.role` 必须逐店明确，创建响应及审计均不含密码。新建路由没有 request_id，不虚构其幂等合同。
3. R/M 本人原生登录；`GET /api/auth/me` 显示首次改密，原业务不能先办理。本人 `POST /api/auth/password` 成功后密码哈希变化、must_change_password=false、全部本人旧会话删除、Cookie 清除，再用新密码真实登录。该路由没有 request_id；网络结果不明时核对，不重放。
4. R 实际切二店／新店，分别观测原 `GET /api/auth/me`、当前店目录和页面。账号 `account_role=sales` 不变，当前 role 应分别为 service/auditor。新店审计岗位的原写入口不应可办；不能因账号默认销售放行。可用本轮新客户原 UI 写作为二店非空事实和日志来源；不要创建任意完成、付款或库存事实。
5. admin 原编辑 R，`PUT /api/users/{id}` 携原 `access_version` 和同一表单 `request_id`，只改本轮新员工。核对 access_version 精确 +1、UserStore、唯一 UserAccessReceipt（actor/target/key/digest/previous_version/result/audit_id）和 update_user 审计。所有 R 旧 LoginSession 删除；此前打开的 R 页面下一次原读取应真实 401 并回登录页，重新登录才取得新岗位／门店／汇总范围。全局默认岗位和门店岗位必须各自核对。
6. 两个真实 admin 浏览器会话同时打开 R 的同版编辑：第一张原提交成功；第二张原表单只提交一次，旧 access_version 应 409，不覆盖第一张授权。保留原 request_id、真实拒绝文案，关闭旧表单后刷新。没有第二个 admin 账号的前置需求，可以同一个合成管理员独立登录两次。
7. 对 R 的另一真实会话执行原他人重置：admin 在员工行点“重置密码”，`POST /api/users/{R}/password`，核对新哈希、must_change_password=true、所有 R 会话删除、reset_password 原原因；R 再用重置密码登录、本人首次改密、重新登录。管理员本人的员工行不显示“重置密码”；原后端禁止自重置，不借该接口修改已有 admin。
8. R 在 `#parameters` 点“修改本人密码”：错误旧密码使用至少12位的随机错值，原 POST 应400、哈希／会话／业务保持；新旧相同原 POST 应422；新密码少于12位由原 HTML minlength 阻止，记录0POST与原字段提示，不虚构服务器422。真正有效改密后所有旧会话失效，新密码登录成功。当前密码强度合同是12–128位，不自增字母／数字／符号政策。
9. admin 在新店作为当前店操作停用该店。原 `PUT /api/stores/{id}` 成功后原 UI `GET /api/stores` 无显式旧店头，选择可用店，`switchStore` 重读 auth/me／目录／实际 feature，并显示真实切店提示。R 若仍持该店旧页面，下一原请求应409，不继续用缓存角色办理。随后 admin 原编辑重新启用新店，R 正常切回并重读；店内已建原事实保持。
10. admin 查 `#audit`，用本次新增店／员工／改权／密码的非空原日志逐行核对，真实点详情；另一页不是空页占位。manager 查原本店非空客户／业务日志，不能显示 `users/stores/feedback/maintenance`；新店 auditor 查该店非空原客户／业务日志，二店来源不能混入。页面读取、分页和详情不得改业务。

写保护应每步保护全部旧业务行；只能更新本轮指定 User／UserStore／Store、追加精确 AccessReceipt／AuditLog，并核对原 stock_moves、cash_entries、原业务／文件不变。登录 LoginSession/LoginAttempt 的原记账另留精确数量和身份边界。403 或带权限语义422可能由原 main.note_refusal 追加 `escalation_refusals`，不能要求绝对整库不变，也不能粗排除整表；仅允许真实 response.refusal 指定的一条本员工／本店／原 method/path/message 拒绝，其余旧行保持，规则拒绝不得被误称可提权。

账号改权由 `user_access_service.change_access` 重新锁定实际 admin、校验当前权限与 CAS，同事务撤销会话。不能降权或停用当前管理员；启用非 admin 至少一家在用门店。当前有效 admin 发起、不同 target 的“最后 admin”分支不能通过伪造不再有效的管理员调用来制造；自停降拒绝另有先行守卫，未实际执行的分支保留未测。

“最后可用店”是原不可绕过守卫。当前两家来源店承载其他链，核心链只停启本轮新店。若本批要实际覆盖最后可用店拒绝，需要根另定本实例末尾的独占窗口：先按原 UI 停其他店，剩余当前店停用提交一次应409，然后逐店原 UI恢复；记录期间真实访问／跟进失效，不能忽略 worker 的合法状态推进或把恢复说成未发生。该分支未执行时不写已验证，不能静态判断代替实际证据。

## HK190 的第二链：明确原单／文件授权

来源必须是同一 evidence_root 中本次已完成的销售交付原单。读取 `sales-order-hk008-009-011-022/business-checkpoint.json` 的 complete/passed、逐 check 状态及 `report_sources.delivered_order_id`，同时绑定该 run 的稳定 provenance 和镜像指纹。再用只读 SQLite 核对真实一店 Case、当前 version、VIN／客户、FlowEvent、原 FileAsset；文件 ID应来自 HK008 本版签回／HK011 交付证据的明确来源，不能 SELECT latest、demo 原单或别的 run 补事实。

最小路线是已有一店 manager 发起，UI 新建的一店主管 M 独立批准，二店 service 员工 R 接收；三人不同。R 无一店权限，通过明确授权接收，不为其追加一店角色。此路由不要求接收店预先有同一集团车辆／客户关系，不能与 HK099 的车辆摘要授权合同混为一谈。

1. manager 在 `#dossier-grants/sent` 用“选择本店原业务”查本次明确订单，实际选择原单。`GET /api/dossier-grants/source/{case_id}` 返回来源版本；原下拉明确选择二店，再明确选择 R，调用同路径带 to_store_id／recipient_id 的候选。确认 R 的二店实际 role=service 且已首次改密；无默选第一项。
2. 原表单勾原单快照、逐件勾至少一个真实可用原合同或签回文件；默认不共享联系电话，不勾金额（R非financial，原控件不可用）。填写用途、真实未来有效期、明确确认，原 `POST /api/dossier-grants` 携 request_id 和 values(source_case_id/source_case_version/to_store_id/recipient_id/include_record/include_contact/include_financials/file_ids/purpose/expires_at/confirmed)。核对 DossierGrant 的原角色／access_version／范围 digest、DossierGrantFile 的逐件 metadata_snapshot、唯一 Receipt／Audit。原 Case 和文件字节不变。
3. 发起人 manager 不应有本申请“独立批准”按钮；M 登录一店在“待我复核”看到该申请、核原范围／逐件文件，原 `/actions/approve` 提交原 grant.version 和 request_id/confirmed/reason。Decision.actor!=requested_by、actor_role=manager、同一 source/version/digest，原范围不可扩展。若要实测服务器自批403，只能登记为单独安全拒绝 probe，不能伪造原 UI 按钮，也不能把未执行后端分支写成通过。
4. R 登录二店在“收到的授权”只看到指定申请，打开详情由原 `GET /{id}/record` 返回批准时白名单快照，并下载明确文件 `GET /{id}/files/{file_id}`。逐件比原 FileAsset sha256／size／source版本与下载字节。查看不开放普通原店 Case/file 路由、关联单、后续新增文件或全客户资料；已下载合法副本不承诺远程删除。
5. 每次 record、directory、file 读取均合法追加 DossierAccess 与唯一 dossier_read_* Audit，提交后才返回 JSON／字节。逐条核 grant/version/actor/role/access_version/store/action/file_id/scope_digest；保护旧 Access／Audit 原行、Case／Cash／Stock／FileAsset 和文件字节。不能把这类 GET 当整库绝对零写。
6. 使用不同的真实原授权覆盖失效原因：G1读取后 admin 原界面改变 R 的门店角色／access_version，旧会话401；重登后原申请 effective_status=suspended、不能读，恢复相同角色仍因 access_version 不匹配不恢复旧 grant。G2重新发起／独立批准／读取，再原 revoke，一次动作追加 Decision，接收页刷新不再显示快照／文件。G3用原 datetime-local 选择真实短未来期限，独立批准及读取后等待真实 UTC 到期，刷新／焦点重验清空已展示资料。不得改数据库 expiry、快进服务器或以取消代替撤销。
7. 到期输入是浏览器本地 datetime-local，经原前端转UTC，不是业务 date；执行器需按实际浏览器时区计算并核回服务器 expires_at。等待分段不超过60秒并保持进度沟通。若执行窗口不足，expiry必须not_tested，不能把页面定时器存在当实测。

文件原 `file_security.security_info.can_use=true` 与双方 can_file 均需真实确认。当前隔离环境 structure_only 允许非生产结构检查件，这只证明原读取／字节／权限链；不能声称ClamAV或生产附件验收。资金收款凭据不因同单自动分享，金融原快照也不因显示合同自动获授。

## 已核实的接口与事实

| 原 API | 事实／守卫来源 |
| --- | --- |
| GET/POST /api/users；PUT /api/users/{id}；POST /api/users/{id}/password | main.py 257–352；schemas.py UserInput/UserUpdate/ResetPasswordInput；user_access_service.py change_access；users、user_stores、user_access_receipts、login_sessions、audit_logs |
| POST /api/auth/login；GET /api/auth/me；POST /api/auth/password | main.py 220–248；security.py get_user/set_session；tenancy.py attach_scope/role_for_store；current_password核验、12–128新密码、会话撤销、逐店投影 |
| GET/POST /api/stores；PUT /api/stores/{id} | main.py 593–623；stores、global Audit；真实 active、最后可用店守卫、runtime的store access信号 |
| GET /api/parameters/catalog | parameter_api.py 固定入口与安全 deployment投影；原页面只读，不接受任意配置键／密钥／路径 |
| POST/DELETE /api/branding/photo；GET /api/branding/photo | branding_api.py；仅具体门店的account admin可写，app_metadata key=public_login_photo、sha256与maintenance Audit；公开经过重新编码的JPEG，不是私有附件 |
| GET /api/audit?page&entity_type&entity_id | main.py audit_list；tenancy ORM StoreScoped范围（admin另包含global0）；非admin排除账号／门店／反馈／维护；原页面30行分页与detail |
| GET /api/dossier-grants/catalog,/source/{case_id},空路径,/{id},/{id}/record,/{id}/files,/{id}/files/{file_id}；POST空路径,/{id}/actions/{approve,reject,cancel,revoke} | dossier_grant_api/service/rules/models、flow_documents.can_file、file_security.require_usable；dossier_grants/files/decisions/accesses/receipts 与原审计；源单、逐件字节、身份岗位版本、到期与独立复核重新核验 |

## 编码前需要根明确的窄范围差异

- HK193：原 `web/app.js:auditPage` 只请求 `/api/audit?page=...`，无类型／原ID筛选控件。原工作流仅要求查看并点详情，现目录额外写了类型／ID筛选；不能在原 UI 点击候选中宣称这些筛选已执行。根可依据原要求登记最小 UI 接线，或先保留该目录条件未验证；本研究不修改目录、不降低准入。安全后台过滤接口已有，无需改后端守卫。
- HK192：管理员原登录图片确有完整实现，可在外部 runtime 生成不含客户资料的合成 PNG（至少320×320、最多2400万像素、文件≤8MB），原文件选择→POST→公开图 GET 的真实 JPEG哈希／显示→DELETE恢复默认；AppMetadata 只更新指定key、maintenance审计逐条精确核对。该页原业务参数入口跳转不是把全部会员／问卷规则重新验收一次；写规则的实绩由各独立需求负责。若只执行本人密码，明确登录图片分支未测。
- HK190：现有两店身份有完整原角色前置，但还要两名通过UI新增并首次改密的员工与本次交付原单／真实可用文件。没有同轮交付或文件前序时，先执行账号核心链、不给 HK190-business通过；不扩fixture造授权或业务终态。
- 最后可用店、服务器自批拒绝、到期、其他人／未列文件原端拒绝，分别列 required安全验收或本批 conditional未测。脚本通过只能证明实际UI/API/DB断言；人工简单流程／简洁文案始终单独 pending，没有人工证据不汇总 business_accepted。

建议在根登记精确补丁后新增一个系统候选模块，复用已有 Evidence/checkpoint及少量原登录／原表单 helpers，分“核心”与“跨店授权”两个场景，五项唯一 check不重复。核心先形成真实店／员工／非空审计，跨店授权严格依赖本次交付来源；未知结果立即失败并保留已执行／未执行分项，不自动重试或换请求号。研究记录不等于编码或运行验收。
