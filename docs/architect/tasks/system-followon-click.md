# 任务：参数密码与系统日志真实点击候选

**任务 id 与负责人**：`system-followon-click`；`click_scenarios`。只拥有本任务页与 `tests/browser_click/system_followon_business.py`，向根代理冻结交接。

**目标与交付结果**：按 PATCH-M8-4-BUSINESS-193-16、冻结范围 `system-followon-scope.md` SHA256 `3184685da448c32fe6b9a48e76884790d23918aeafd82a82573eda6d3c74986b` 实现两个唯一完整 check：HK-192 参数设置密码修改／`HK-192-business`，HK-193 系统日志／`HK-193-business`。当前为未注册、未执行候选，不继承父系统两项 partial 为成绩。

**架构依据与决定**：保留原个人密码、参数目录、登录图片、账号授权与 AuditLog 合同。复用 `sales_business.login_as`、`sales_order_business.fixed_dependency/checkpoint_evidence`、`system_management_business` 的本人登录、密码、字段和失效会话 helpers，以及原 checkbox/select 小 helper。新增 Guard 只服务本批两种有限写入，Checkpoint 沿现有同轮报告结构，不引入新执行器或通用框架；没有 app／runner 导入、SQL 正写或正向 API 捷径。

**代码快照与影响范围**：HEAD `5069b2bcc9f580ebb9d70780769049a14a6de946`，实际读取当前未提交源。原审计生产补丁由根实现，本候选已读取 `web/app.js` SHA256 `2700fb9aac46bc01e7f43c93abbd7421da096a96f839c5beeb8acfd3e16c6bdc` 的真实控件与详情合同；不修改该文件或任何注册源、目录、夹具、实施计划。

## 接线与来源合同

- `SCENARIO="system-followon-hk192-193"`；入口 `async system_followon_business(e, context, credentials)`；导出 `SYSTEM_FOLLOWON_SCENARIOS=((SCENARIO,system_followon_business,240),)`。根负责加入已有 SCENARIOS 和原白名单，不由作者代改。
- 父依赖固定本轮 `system-management-hk189-191`、`vehicle-purchase-hk171-177-178-026-021-018-029`。既有 runner 当前报告必须已记录 passed，父 checkpoint 必须 complete／passed、每个完整 check passed；原目录 digest 一致。当前 provenance.snapshot_stable、原源／脚本总摘要、相关脚本逐文件 SHA 与 manifest 五个路径一并核对，未满足即失败。
- 从父 HK-191 `staff_actions` 首两个真实 UI 新员工事实取明确 receiver／manager id；核当前 Users／UserStore。甲原二店 service／本批第三店 auditor，乙一店 manager，账号级均 sales；当前密码和当前逐店角色均重新核，不把创建时 version 当当前版。
- 私有密码只消费父固定 `observations.json` 中唯一 `synthetic_system_private_credentials.value.path`，路径必须是本轮外置 runtime 下原私有文件，id／username 匹配。新密码只追加其 `accounts.receiver.system_followon`、成功改密后更新 current_password_stage；所有密码进入共用 scrubber，不记录明文、哈希或请求体，不改主 credentials 或原账号密码。
- Supplier 使用父 HK-171 `evidence.supplier.id`，核本店原当前完整行和明确 `reason=供应商` 的 master_create/master_update Audit 两行，actor 是前场景真实 manager。不同 typed 主档表可共用 entity_id；UI/API 的 type/id 筛选结果照原范围逐行核对，不能误要求只返回供应商。
- 来源报告保存有限用户／供应商／原 audit id、父 checkpoint 摘要及指纹，没有 User.password_hash、照片 base64 或附件正文。不存在跨 run 扫描／SELECT latest／夹具预制本应点击产生的成果。

## HK-192 实际拟执行路径

1. admin 原登录具体一店；原安全参数目录逐卡存在、写权限与当前岗位一致。真实展开 deployment 只读区域，十个白名单键的显示值与响应一致，处理 JS 对整值 float 的正常无小数显示。service／manager／auditor 的目录分别读取并核真实岗位投影，非管理岗位 deployment=None，无密钥／连接串／私有路径。
2. 从 manager 参数卡真实打开工位与快捷项目（GET `/api/service-intake/catalog`，原标题“工位与快捷项目”）；从甲 service 参数卡打开原提醒规则（GET `/api/customer-service/reminders/rules`，原标题“车辆提醒与续保提取”）。只读 API 与当前店、实际标题和原业务摘要一致，再回原参数页。不借导航声称发布所有业务规则。
3. 甲本人至少两个独立原生会话，原改密表单一次错误旧密码400、相同新旧422、少于12位原 HTML 阻止且实际0POST；再真实合法改密200。User 只变化 password_hash／must_change_password，全部本人旧 LoginSession 删除，唯一 global0 change_password Audit，Cookie 清除；旧两页原 me401，再用新密码登录，真实二店 service 投影。
4. admin 用原页面“更换图片”打开原图片 form，通过原文件 input 选择 runtime 中本批独占合成360×360 PNG（无客户资料）并保存，实际 multipart Cookie／CSRF／当前店 POST200。原新 img 请求返回公开 JPEG，解码尺寸、无 EXIF、DOM visible/complete/naturalWidth、响应／metadata／字节 SHA 一致。只报告字节长度／SHA／尺寸，不持久化 blob到报告。
5. admin 原“恢复默认” DELETE200、真实 img GET；public_login_photo key 撤除，公开 JPEG SHA 与替换前原默认图一致，两个精确 maintenance 审计与 actor／store1／action／sha 对齐。最初要求本批无既有自定义登录图片，避免覆盖其他来源。不是头像、私有附件、ClamAV 或公司品牌批准。

密码原 API 无 request_id 或 CAS，不附造该合同，不重放未知结果。图片原接口也未增加业务请求号。本批不创建新资金／会员／库存／规则，不修改 .env 或任何任意部署设置。

## HK-193 实际拟执行路径

原控件精确为 `#audit-filters` 的 entity_type select、entity_id input、submit查询及 `[data-act=audit-reset]`；详情仍 `[data-act=auditdetail][data-id]`，分页 `[data-act=page][data-page]`。只通过这些真实 UI 发原 GET，不改 fetch 或前端 state。

1. admin、乙 manager、一店 auditor 甲各打开非空原日志；每次登录后新基线。UI/API/DB 全行对齐范围、总数、30行分页、id降序、时间、操作人、动作描述、类型、原编号与说明。API UTC Z 与 UI Asia/Shanghai 精确转换，不只判断日期含今天。
2. 从原重置后的全部日志真实下一页／上一页，必须 total>30、第二页非空、两页无重复、返回第一页数据不变。缺实际分页条件则失败，不造30次写入。typed_master 类型和有限 supplier 编号真实查询；若同编号原范围跨页，只读求该固定 audit id 的真实目标页，再通过原相邻分页读取，不冻结数组索引。原类型筛选确有第二页时另实际验证分页保留类型。
3. 原编号输入0由原自定义 validity 拒绝，监听实际0GET、全部业务不变；原 fill 修正后 validity 清除。随后正常查询，不把客户端拒绝写成后端HTTP成功或422。
4. 对有限 supplier 新增／编辑日志各点击详情，核业务范围“业务资料”、原编号、actor／说明／时间与前后名称／编码／联系人／联系电话，精确选“操作前／操作后”对应 facts。admin 再筛本次门店 id并点父明确 update_store Audit，核 global0 和真实名称前后。金额／数量 formatter保留原整数单位，但本次详情源没有金融数值，明示 money_details_without_source=not_tested，不泛称所有财务详情验证通过。
5. manager／auditor 各用原类型控件筛 users/stores/feedback/maintenance，结果必须0且属于真实保护负例；另返回本店非空供应商数据，不能以空保护页代替正向查询通过。admin 具体店只含当前店+global0，非admin只含当前店，类型/id均不能突破范围。
6. admin 仅通过原 `#users` 编辑追加甲一店 auditor，保留其它 profile和原二店 service／新店 auditor；严格实际 access_version、原 request_id digest、唯一 UserAccessReceipt、唯一global0 update_user Audit及全部本人旧会话撤销。甲旧页me401，再本人原登录实际一店auditor（账号role仍sales）。
7. 甲真实切原第三店 auditor再读，原一店 supplier日志不可出现；原 type/id筛得空是跨店来源保护负例，换店清筛选和门店 header亦核对。最后 admin 原编辑明确取消一店授权并保留原两店，全量CAS／收据／会话再次核；甲旧页401、重新登录二店service且授权只为原两店，恢复 HK190 接收人无一店权限前置。

正常完成必须 `temporary_auditor_restored=true`。若临时授权已知成功而后续读取失败，可在保留 failed 的前提下仅一次原 UI 明确恢复；该清理不用原未知写请求重放，当前没有本人会话时仍核0会话与CAS；未知写／恢复失败保持失败和错误证据，不循环求绿。原 access_version递增保留，不倒改版本；旧 grant不会因同岗位恢复自动复活。

审计 CSV 原实现不存在；条件与证据均固定 `audit_export_supported=false/audit_export_executed=false`，不修改原目录，也不生成伪 CSV 或调用原 records export冒充同范围审计导出。

## 旧行保护和输出

Guard 使用现有全业务行摘要保护其它表、所有他店以及现金／库存／会员／文件；允许表内逐旧行保持。原登录图片只允许 AppMetadata指定 public_login_photo键创建／删除和本次唯一 maintenance Audit；只有已有统一守卫排除的 `assistant_runtime_worker:` 精确前缀不纳入旧行比对，不排除整张 metadata。原临时授权只允许该新员工access_version、其明确 UserStore集合变化及唯一receipt／audit；其它 User与所有其它人LoginSession保持。原改密仍复用已核准有限本人列／会话／审计守卫。所有SQL SELECT-only，原blob只在内存比对；JSON evidence先序列化核验。

`business-checkpoint.json` 输出 requirements 两行、各 check_id／status／criteria／原 UI/API/DB证据、动作起止、同轮依赖、candidate/catalog/provenance摘要、授权恢复及 report_sources有限IDs。任一 required失败整场景失败，running行终止为failed/partial，空／未执行不能passed。每项 `business_accepted=false`，人工 simple_flow／concise_copy pending；full193及full_registered_suite_complete均false，不替代公司、跨平台或生产验收。

**已完成与当前位置**：两项完整候选代码已落盘，控件按根实际2700fb9a源合同读核；未注册、未运行。源依赖、公开JPEG、密码与会话、有限授权恢复、审计分页／范围／详情／拒绝及失败保留均在代码中。

**下一步**：冻结并由根安排独立只读短审；根完成白名单／注册后，使用同轮父系统+采购先通过的原隔离实例实际点击。观察动态时序／图片载入／多角色范围／任务源后再判断结果，保留首次失败，不由静态 review登记成绩。

**验证与实际阻塞**：仅 AST／SQL入口与导入静态审阅、UTF-8与空白／指纹核对；没有 app导入、模型调用、服务、浏览器或测试运行。必要条件为本轮稳定镜像、两个完整父场景及私有随机员工文件、同轮非空本店日志>30；根的审计生产补丁与最终执行环境仍需真实联合验证。
