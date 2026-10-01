# 任务：参数与个人密码、系统日志后续范围

**任务 id 与负责人**：`system-followon-scope`；`click_scenarios`，向根代理交接。

**目标与交付结果**：只读核准 HK-192／HK-193 的最小完整原 UI 路径、同轮身份与非空来源，以及必须先登记的前端接线补丁。本次只新增本文，不修改生产、目录、测试、夹具、执行器或实施计划，不启动应用和浏览器，不登记业务通过。

**架构依据与决定**：沿现有原参数入口、本人密码接口和 StoreScoped 审计查询。正向操作必须由真实员工点击；API 观察和 SQLite SELECT 只用于核对。沿 DSH Architect 先确定最近一条完整路径，复用现有系统候选的小型登录／表单／旧行保护，不创建新的框架。

**代码快照与影响范围**：2026-10-01，HEAD `5069b2bcc9f580ebb9d70780769049a14a6de946`，工作树存在根及其他作者的未提交产物。下表绑定实际读取字节，不能以 HEAD 代替工作树。当前已注册源与候选保持冻结。

| 读取文件 | SHA256 |
| --- | --- |
| `web/app.js` | `48b44811911c861b208a0fe09ae9bc5241f5ba591cea73159147717cbc42d124` |
| `app/main.py` | `f32cff9a83525010fdecd50fc7ae0e1d5b6d50d8abe47c01406dc40043633e95` |
| `app/tenancy.py` | `7c39d67e6af3e719dc8f9dc4040394297ea360daa048a41968d3a789373606a8` |
| `app/parameter_api.py` | `c928837a57455fed1cff6c9098408629ae377fee28444274e6bc8526a5cbeb6c` |
| `web/parameters.js` | `fef0f72073719b60e2c5de92c4484687b1dacce516415cbfcc63173855393ad2` |
| `app/branding_api.py` | `c102c0815767f71fb1512e841e4a23e8e576c257819e3c39100d374817916ae6` |
| `tests/browser_click/system_management_business.py` | `7a0425a770c8db492f7489a0190364deac062626be3d4af29be56a3a8ed3bdce` |
| `tests/browser_click/business_acceptance_catalog.json` | `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff` |
| `docs/workflow-source/services.json` | `5b302d5c731edc424788efd1765bf32b9dea827a3bd9691500f261ed98f11040` |

## 原题与目录合同

| 原编号／原标题 | 唯一完整 check | 原工作流／路由 | 本项必需行为 |
| --- | --- | --- | --- |
| HK-192 参数设置密码修改 | `HK-192-business` | `wf-parameters-password-brand`／`#parameters` | 安全配置投影与原规则入口；本人错误旧密码 400、相同新密码 422、真实强度校验；合法改密、哈希变化、全部本人旧会话撤销、新密码重新登录。部署参数只读，不冒充在线改阈值。 |
| HK-193 系统日志 | `HK-193-business` | `wf-audit-business-history`／`#audit` | 同轮非空原业务日志，真实分页、业务类型和原记录编号筛选、详情；UI／原响应／DB 对齐操作人、操作、对象类型及编号、前后依据、说明、发生时间；admin／manager／auditor 的真实当前店范围，非 admin 排除四类全局管理记录。 |

`docs/requirements.json` 保留上述原题，其历史 JUnit 和旧报告均不继承。完整目录明确 `workflow_reference_scope`：必需动作以 `ui_action` 为准，`role_sequence` 是完整工作流来源参考，不强制本项重复完成共享工作流中的全部其他需求。两项六个统一评价标准仍是预期显示、简单流程、简洁文案、后端一致、硬 bug、来源完整；人工流程／文案仍 pending，自动 check 不能赋值 `business_accepted=true`。

当前系统核心 `system-management-hk189-191` 只提交 HK-189／HK-191 两项完整 check。其 HK-192 已实际执行改密负例与安全目录子范围，HK-193 已实际点击本次门店编辑的非空日志详情；两项仍为 `partial`、`acceptance_check_submitted=false`。后续不能仅把这两个旧 partial 改名为 passed，必须在同轮后续入口独立提交完整 check 并留下新动作与来源。

## 同轮有限来源与身份

父来源固定为本次 `evidence_root/browser-click-report.json` 中 `system-management-hk189-191` 的 passed，以及同目录该场景 `business-checkpoint.json` 的 complete／passed、两项完整 check。同时核对本次 `provenance.json` 的稳定镜像、源／脚本指纹和 manifest；单选后续而缺父来源应明确失败，不查上一轮数据库或选 demo 账号。

现有 checkpoint HK-191 的 `acceptance_checks[0].evidence.staff_actions` 中首两个 `user_id` 对应 UI 新建员工甲／乙，创建事实还带精确 `audit_id`、`store_roles`。后续重新 SELECT 这些指定 User／UserStore 的当前状态，不要求当前版本等于早先创建版，也不扫描全库默选最新员工。

- 员工甲账号级 role=sales，最终授权二店 service／本批新第三店 auditor；员工乙账号级 role=sales，一店 manager。实际当前岗位由 `/api/auth/me` 与 UserStore 投影取得，不能使用账号级 sales 代替。
- 随机密码只在本次 runtime 内的私有文件。固定读取父场景 `observations.json` 中唯一 `synthetic_system_private_credentials.value.path`，校验路径确在本次外置 runtime；不 glob 其他 run。`accounts.receiver.current_password_stage=final`、`accounts.manager.current_password_stage=first` 是当前生成代码的阶段，消费时按指定账号再核当前文件。密码进入共用 scrubber，不保存到新 checkpoint／日志／截图文本，改密后的新阶段只能回写本次私有文件。
- admin 使用本次 manifest／外置 credentials 的实际管理员；manager 可使用本轮新员工乙，证明有限真实员工来源。每次原登录之后建立业务基线。
- 对非空本店审计，最小额外前置是 admin 通过原 `#users` 的编辑按钮给员工甲明确追加一店 auditor，保留原二店 service 和新店 auditor。原 `PUT /api/users/{甲}` 使用当前 access_version／同表单 request_id，核精确 UserAccessReceipt、update_user Audit、版本 +1 和旧会话撤销，再由甲原生重新登录选择一店。该动作须先由根登记后续范围；不在 fixture 预分配，不 SQL 改授权。
- 上述追加一店授权会改变后续 HK-190“接收人无来源店权限”的前置。若同轮包含该链，应先完成 HK-190，或在本轮系统后续末尾通过原 UI 精确恢复甲原两店授权并核新的版本／会话撤销；旧授权不会因恢复同样岗位自动复活。不能暗中让两条链共享矛盾权限。

非空业务来源优先复用同轮 `vehicle-purchase-hk171-177-178-026-021-018-029` 的 HK-171 `acceptance_checks[0].evidence.supplier.id`，该父 `SCENARIO` 已按当前源码精确核准，由 UI 新增并编辑的本店 Supplier。原 `master_data.save_master` 为该有限 id 追加 `entity_type=typed_master`、`master_create/master_update` 审计。核对应原 create/edit 响应、actor、store_id、before/after，不复制来源的局部“passed”作为审计通过。若采用另一已注册主档／原单，只接受其 checkpoint 显式输出的有限 id／动作，不 SELECT latest、造日志或制造 30 次无意义提交。

## HK-192 最小完整路径

1. 本人真实登录具体店，打开 `#parameters`，原 GET `/api/parameters/catalog` 完成后等标题“参数与个人密码”。按当前岗位核 `entries`、`can_write`、`password_action=password`、`deployment_read_only=true`、`aggregate_scope`，目录不得出现密钥、数据库连接、私有路径或密码字段。GET 与导航均保护全部旧业务行。
2. 由 service、manager、auditor 的实际投影各核一个有源目录；manager/admin 可真实展开“部署负责人查看：技术参数”，核显示值来自安全 whitelist。其它岗位没有 deployment，不猜填遗漏字段。汇总时 entries 为空且显示切具体店提示，若未实际进入汇总则该分支未测。
3. 用原每个配置卡的 `[data-act=open][data-route]` 点开本岗位返回的原入口，等真实原标题和本店原响应，再返回参数页。最小代表为 manager 的 `service-intake/resources` 与员工甲 service 的 `customer-reminders`，对应页面有真实岗位读取。全部返回入口可按去重固定目录导航，记录实际执行数；不以页面打开代替规则发布。规则创建／复核由其对应业务 check 负责，本批不额外造规则或覆盖已发规则版本。
4. 员工甲在参数页真实点“修改本人密码”，使用本次阶段的真实旧密码。错误旧密码只提交一次：400“当前密码不正确”，哈希、本人现存会话与业务不变；相同新旧密码只提交一次：422“新密码不能与旧密码相同”。新密码少于 12 位由真实 HTML minlength 阻止应是 0 POST，不能伪写成后端 422。
5. 形成至少两个本人原生会话，再填 12–128 位合成有效新密码，真实 POST `/api/auth/password` 200。只允许本人 User.password_hash／must_change_password 更新、本人 LoginSession 删除及一条 change_password Audit；原 access_version、UserStore、其他人会话和全部业务保持。数据库只报告哈希是否变化／会话数，不输出哈希或密码。旧两页再读真实 401；新密码原生登录 200，再打开参数页核当前店岗位。

原 `PasswordInput` 只有 `current_password`（1–128）、`new_password`（12–128）；原 POST 没有 request_id 或 CAS 字段，不能给它附造幂等合同。未知结果立即停止核对，不自动重放或重置已有管理员密码。原后端写入经 Cookie／CSRF 核验；所有正向写均原表单。

HK-192 不新建头像业务。当前头部 `.avatar` 只是 display_name 首字；没有头像编辑接口。现有登录图片是另一个**真实已有**管理员分支，`web/parameters.js:10–11` 与 `/api/branding/photo` 已接线；未经本批明确选择／执行仍记 `not_tested`，不以截图、图片 GET 或路径存在记通过。

若根选择把该既有分支纳入同一批，必须使用仓库外无客户资料合成图片，原 UI 文件选择→保存→公开 JPEG 实际显示→原恢复默认。写权限为 account admin 且非汇总；图片最大 8MiB、JPG/PNG/WebP、最短边 320、最多 2400 万像素，服务器重新编码 JPEG／去 EXIF。只允许 `app_metadata.public_login_photo` 与精确 replace_photo/reset_photo maintenance 审计；其余 metadata、会员、现金、库存与原附件保持。该图公开，不称私有附件／病毒扫描／公司品牌批准，不能借它补造 avatar、品牌主档或公司设置成果。

## HK-193 原接口、真实范围与最小路径

`app/main.py:535–545` 原 GET `/api/audit` 参数只有：`page:int>=1`（默认1）、`entity_type:str`（默认空）、`entity_id:int|None`。返回 `{items,total,page}`，每页30，按 AuditLog.id 倒序；没有 actor/date_from/date_to/filter-by-time/sort 参数，也没有单日志详情 GET。前端详情来自这次已授权 items 的那一行，不可借猜 id 补查未获授权日志。

`AuditLog` 是 `StoreScoped`。`tenancy.attach_scope` 以真实当前店及本店岗位设置范围，ORM `with_loader_criteria` 同时作用于 total 和 items。管理员具体店范围是当前店 + global0，非“管理员默认看所有店”；汇总仅限实际获授权的汇总岗位店。非 admin 的 manager/auditor 额外排除 `users/stores/feedback/maintenance`。users/stores 的原 audit 强制归 global0，不能拿这些日志证明非 admin 本店业务非空。后台未开放的店不能通过过滤 entity_id 突破 scope。

拟定完整点击顺序：

1. admin 一店真实打开操作记录，等待本次 GET 200 和“操作记录”标题；对原本店 + global0 的非空结果做逐行 UI/API/DB 核对，包含父系统 check 显式 audit_id 的门店／账号动作。不得把未过滤的总数等同某类业务数。
2. admin 在原 UI 类型控件筛 `stores`，原编号填父创建／编辑的新店 id，点击查询；请求必须真的携两个参数，结果精确匹配原日志。清空并以 `typed_master` + 本次 supplier id 筛出原 create/edit 记录；点每个固定 audit_id 的真实“详情”，核姓名、发生时间、说明及实际前后姓名／编码等字段。机器 action、entity_type、entity_id 与真实响应／原数据库一致，不能仅截图一段模糊“资料管理”。
3. 清空筛选，原“下一页／上一页”产生 page=2／1 的原 GET，核总数、30行上限、倒序、两页 id 不重叠、当前筛选与 scope。必须使用同轮确已超过30行的原来源；缺这个实际条件不能凭 disabled 下一页宣称分页完整，不补造日志。筛选只得到两行时，核第一页和 disabled 下一页是另一条边界。
4. 新员工乙以一店 manager 真实登录；核一店非空 typed_master 原记录与其 UI 详情一致，所有返回行归一店，不含四种管理类型。真实筛 stores + 该已存在新店 id 得空结果是受保护负例，不作为非空业务通过。对账号／维护等类型逐一核过滤；只读补充 Cookie GET 若需要，应另记 supplemental_read，不能替代原 UI 筛选。
5. 员工甲按明确追加的一店 auditor 关系重新登录，走同一非空本店查询／详情和排除负例，确认账号 role=sales、本店 role=auditor。实际切到其原第三店审计岗位后重读，已知一店 supplier id 不可混入；该空结果仅证明范围负例，再回一店非空。切二店 service 后审计入口不可办理，原有效深链接若读取则应403；原 refusal 若写审计拒绝依据须精确核响应指定行，不能粗排除整表。
6. 每原登录后建立新基线；审计读取、筛选、分页、详情零业务写入，原 AuditLog 行也保持，不为查询另 append 审计。时间 API `plain()` 按 UTC Z，页面 `time()` 按 Asia/Shanghai；用准确时间转换核该有限行，不能以显示日期包含今天替代。

## 必须先登记的窄生产补丁与合同未决项

**确定接线缺口**：`web/app.js:383` 的 auditPage 只请求 `'/api/audit?page='+state.page`，没有类型／原编号表单。原 `bindFilters():244` 只保存 q/state，不能直接给审计套该通用表单后宣称筛选已接。建议根只登记 `web/app.js` 的审计独立表单和绑定：安全 URLSearchParams 序列化原 `entity_type/entity_id`；空编号省略，填写编号严格按原整数规则，不默改错误输入；提交／重置 page=1；分页保留这两值；hash进入／离开、清业务上下文、换店成功时清筛选，迟到页面响应沿原 renderId 丢弃。按钮只叫“查询／重置”，不增加后台不存在的姓名／日期／资金筛选。后端权限、门店 criteria、查询排序与30行合同无需改动。

**详情展示的有限问题**：当前详情 `app.js:434` 只有 reason/actor/time 和被 known label 白名单保留的标量 before/after，未显示原记录编号；未知业务类型一律“资料管理”。原响应有真实 entity_type/entity_id，若本批要求员工直接辨认原对象，可在同一精确显示补丁加入中文业务范围／原记录编号和已知 action 描述，保留 whitelist，不直接 dump 嵌套原资料。本轮 supplier edit 实际变的是 contact_name／phone，但当前 known 白名单没有这两字段，原联系人修改无法在详情中呈现；若采用该编辑记录作 UI 前后变更证据，需根登记最小这两个中文字段映射，不能仅以未变的名称／编码冒充编辑内容已显示。已读代码还显示 `prettify()` 先把 `amount_cents` 键变成“约定金额（元）”，再传 `facts()`；后者依赖原 `_cents/_milli` 键换算，因而资金／数量审计详情有静态单位丢失风险。若本批选资金详情，需真实复现并保留原键完成格式化，不能因供应商详情通过就泛称所有金额详情一致。本研究未运行该复现，不把推断写成已观察失败。

**CSV 确认不存在**：源码没有审计 CSV UI、`/api/audit/export` 或其他审计导出路由。`/api/export/{module}` 仅原 MODULES 的 vehicles/sales/repairs/policies/cash，不接受 audit，也不是相同审计过滤。原工作流没有承诺审计 CSV；目录 `HK-193-edge-source` 泛用“UI/API/DB及导出”字样与本项现有 API 绑定有范围歧义。根登记本批时必须明确 export_supported=false／export_executed=false 及其原来源范围；本研究不改目录、不把不存在的导出记通过。若根要求审计 CSV 成为本项必需，则应另登记真实同范围后端／UI 实现及下载验收，当前不能宣称该分支完成。

HK-192 当前缺的是独立完整 check 的新证据与原导航点击覆盖，不是任意环境参数写入口。catalog 中品牌说明与参考步骤保留，需报告实际未测分支。新 check 的完成不能等同整个工作流全部分支、人工体验、193全量或生产验收。

## 交接与验证边界

**已完成与当前位置**：已核原题、目录 check、原参数投影／密码 schema、真实登录图片实现、auditPage／auditdetail、后端过滤、ORM门店约束、CSV缺口及父系统有限来源；完成本文。保险候选一行 SQLite 布尔窄修已另回根：最终脚本 `ab7e7e472b17f36be774fb8936a269b018c82bfb3474282b7e470715a052cd05`、文档 `dcb0f85ecc03841508b2ae7674ffff7ad4c4e1b5aa4800114bbd1c2bd36a713f`，raw row `closed_open_task==0`，decoded JSON 仍 `is False`。

**下一步**：根先登记审计 UI 两字段接线及本批身份变更／CSV口径，再授权独立后续候选。建议两个函数共一个独立候选文件，各提交 HK-192／HK-193 唯一 check；受精确父场景、同轮非空与分页条件约束。正常预期约1–2分钟，动态执行耗时需实测；不以预计时长记通过。旧核心／partial／失败证据全部保留。

**验证与实际阻塞**：只读 Python AST 解析 main／tenancy／parameter_api／branding_api／system候选／insurance候选成功；仅静态读取，未导入 app 或候选、未运行测试、服务或浏览器。本次只新增文档。HK-193 UI过滤尚未接线；非空 auditor 一店岗位、同轮分页>30来源及 CSV口径需根按上述有限范围决定。其余人工简单流程／简洁文案、实际浏览器结果、原生其他平台、生产与193全业务均未由本文验收。
