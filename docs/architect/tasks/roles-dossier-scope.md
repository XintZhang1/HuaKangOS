# 任务：角色管理与逐原单、逐文件授权范围

负责人：`test_inventory`，交接根代理。2026-10-01 只读研究；仅新增本文，没有运行应用、浏览器、测试或导入 app，也没有修改生产、已有候选、夹具、执行器、目录和计划。本代理未触碰此前交付的提醒作者候选 `47c404888cfa8c31ab228cd80279d25e9a462997fbf0f398b8f78c20b808fa4c`；收尾只读观测当前字节为 `5c391d964cee95b1f143cef036c0ba85f11511f2e505ee7ca84b311caf270e6d`，已向根报告，以根注册及运行指纹为准，不拼接两版结论。

## 原需求与来源

原题为系统管理模块 **HK-190「角色管理」**，唯一完整 check 为 `HK-190-business`；对应 `wf-employee-store-roles`、`wf-cross-store-service-history`，原入口 `#users`、`#dossier-grants/received`。目录要求真实账号访问更新以及跨店指定员工的原单快照、逐文件申请、独立复核、读取和失效；新员工创建或 HK099 的客户车辆历史摘要授权不替代本项。当前仅提出一项完整候选，尚未登记通过；体验、人员验收、193 完整验收仍 pending。

最短同轮父闭包：`system-management-hk189-191` 的真实两名新员工，加 `sales-order-hk008-009-011-022` 的已交付原单。父报告必须 executed/passed、checkpoint complete/passed、原完整 checks 全 passed，目录与本轮镜像/源/脚本/manifest 指纹一致。销售父自身的售前、采购等依赖仍须同轮 passed，不能从另一 run 拼来源。若执行过 `system-followon-hk190-192-193`，须同轮 passed 且 `temporary_auditor_restored=true`，再核当前授权。

- 接收人甲固定来自 HK191 `staff_actions[0].user_id`：账号 role=sales，二店 UserStore=service，新第三店=auditor，一店无授权，已完成首次改密；乙来自 `[1]`，一店 manager。全部 current roles、active、must_change_password、access_version 由限定 ID 重读，不以旧账号默认岗位代替当前店岗位。
- 私有密码只读父 observations 中唯一 `synthetic_system_private_credentials.value.path`，校验本次外部 runtime、账号 ID/username、当前密码阶段；全部私有密码先加入 scrubber。证据不包含密码、User.password_hash、session/CSRF hash 或附件正文。
- 原单固定为销售父 `report_sources.delivered_order_id`；选定 F1=HK009 `handover.generated.id`、F2=`signed_handover.file.id`（消费时重验实际父对象结构、不同 ID、同原 case/store、原 SHA/size/类别/双方可读性及检查状态）。不 SELECT latest，不上传第三件来假造授权成果。乙 manager 发起，既有随机 admin 独立复核，甲二店读取；不需要新 fixture 身份。
- 当前 source version 和投影取原 `GET /api/dossier-grants/source/{case}`。后继合法业务可能使原单版本不同于早先父 checkpoint；须保护父的历史行并绑定申请时的当前真实版本，不倒贴旧版本或静默忽略差异。若原候选出处并非上述 metadata 键，停止并报告，不能扫描附件兜底。

## 最小实际输入到结果

| 顺序 | 原生操作与精确接口 | 结果与核对 |
| --- | --- | --- |
| 1 | 甲二店真实登录，打开“收到的授权”；乙一店点“选择本店原业务”，以有限原单号查找，`GET /api/flow/cases?q=...&page=1`，点 `data-act=dossier-new/data-case=原ID` | 无甲一店访问权限；乙可读本张订单，甲二店 service 属 order 可接收岗位。原目录/选项 GET 仅只读，不生成业务 Task。 |
| 2 | G1 “跨店协同”：真实选择二店/甲、用途、带时区未来7天到期、include_record=true、include_contact=false、include_financials=false，只勾 F1，confirmed=true；原 `POST /api/dossier-grants` 201，body={request_id,values} | {grant,replayed:false}；只新增一 Grant、一个 GrantFile、一 DossierReceipt、一 dossier_propose Audit。锁当前 source_case_version、双方 role/access_version；快照和 scope_digest 冻结。F2/关联单/后续附件不加入。 |
| 3 | admin 一店“待我复核”→G1→“独立批准”，原 `POST /{g}/actions/approve`，{request_id,version,values:{reason,confirmed:true}} | G1 pending v1→approved v2，精确一 Decision(previous_version=1)、一 Receipt、一 dossier_approve Audit；原单/事件/文件字节完全不变。乙本人的批准按钮不显示，不伪造可点击控件测试自批。 |
| 4 | 甲二店收到列表→G1，页面原 `GET /{g}` 后 `GET /{g}/record`，点 F1 “核验并下载”→`GET /{g}/files/{F1}` | 真实快照 header/event window/姓名/VIN 同冻结数据；无 phone/contact/financials/自由 data/account/evidence/关联原单 URL/写按钮。文件目录恰 F1，下载原字节 SHA、size、媒体类型及安全头一致。文件正文按逐件授权，不因快照未选金额/电话自动脱敏；必须先实际核对 F1 合成内容。 |
| 5 | admin 原 #users 编辑甲，二店 service→auditor，保留第三店 auditor、不加一店、账号默认 sales/启用/姓名不变；明确 can_group_summary=true。同时保留另一 admin 原编辑窗口的旧 access_version，待成功后真实提交旧窗口 | 原 `PUT /api/users/{甲}` 200 后 access_version+1、精确 UserStore 替换、一 AccessReceipt、一 global0 update_user Audit、甲全部旧 LoginSession 撤销；其他人会话不变。旧页面下一原 GET 401，重新登录当前二店 auditor；汇总仅二店/第三店可读且 dossier catalog can_read=false。旧编辑 PUT 409、原请求号保留、关闭旧窗口/刷新核对，业务与全部旧授权无写入。 |
| 6 | 甲重新登录二店核 G1 suspended/can_read=false；admin 原表单恢复甲原两店岗位和原汇总开关，再真实重新登录甲 | 原授权 pinned access_version 永久失配，恢复同样 service 也不能复活 G1；Grant 物理 status/version/snapshot/文件/Decision 不改，effective_status 由当前事实投影。不得把恢复操作伪装成原授权重新批准。 |
| 7 | 乙针对相同当前原单另建 G2：include_record=false、其他两项 false，仅 F2；admin 独立批准；甲二店打开、原 `GET /{g}/files`，下载 F2 | 第二张新授权与新 scope_digest；目录恰 F2，不含 record/customer/vehicle/financials 或 F1。原 GET directory 和 file 分别留合法读取事实；不得重用 G1 request_id。 |
| 8 | 乙一店或 admin 打开 G2 点“撤销授权”，真实最新版本 POST revoke；甲真实刷新/重新进入 | G2 approved v2→revoked v3，独立一 revoke Decision/Receipt/Audit；旧 snapshot/文件保留。接收页不再显示原编号、用途、姓名或文件 metadata/下载控件；撤销不远程删除此前已合法下载的外部副本。 |
| 9 | G3 新 record-only 授权，以原 datetime-local 输入真实当前时间后至少2分钟的整分钟时间，独立批准后甲实际读一次；每次等待≤60秒，保持到期前后原焦点/刷新操作 | 真实 UTC时钟跨过 expires_at 后 detail/list 为 expired、can_read=false、payload 不再显示，物理 Grant 仍 approved，原 Decision/Receipt/Access 都保留。不改时钟、不 SQL 改期限、不把撤销当到期；运行预算预留真实等待，批准前已到期须按原失败收尾。 |

原前端定位来自 `web/dossiergrants.js`：`[data-act=dossier-pick]`、`#dossier-search [name=q]`、`[data-act=dossier-new][data-case]`；modal `to_store_id/recipient_id/purpose/expires_at/include_record/include_contact/include_financials/dossier_file/confirmed`。门店改变后等待真实 source GET 并等 recipient enabled，选择员工后再等待精确 source GET/file choices；文件默认不勾，不能填内部 ID 绕可见候选。决策用 `[data-act=dossier-decision][data-key]`、`reason/confirmed`；下载用精确 `[data-act=dossier-download][data-grant][data-file]`。所有新单响应 listener 必须先绑 POST 新 id 后等同 id GET；modal 先 visible 再 title，不能接旧 DOM 或加载中的瞬时0按钮。

## 精确原事实与保护

账号改权原 `UserUpdate` 字段是 request_id/access_version/store_ids/store_roles/can_group_summary/role/display_name/active。访问回执 digest 为 SHA256(json.dumps({target_id,values:body排除request_id}, sort_keys=True,ensure_ascii=False))；request_data **保留 access_version、排除 request_id**，result=account_info，previous_version=旧版，audit_id 精确绑定 global0 原审计。只允许指定甲的上述明确字段和全部本人会话删除；其他 User/UserStore/会话、密码 hash、旧回执审计、源业务全行保护。runtime flag 启用时 `emit_user_access_changed` 从原回执派生受影响门店并集（当前两店+真实旧 memberships+甲所拥有 Run/FollowupGrant 的 store），逐店唯一 `user_access_receipt:{receipt}:store:{store}`、topic=access.changed、source_ref={type:user_access_receipt,id,version}；先有限读取甲路由元数据计算集合，未知来源停止。不能豁免整表或假定永远恰两条；worker 后续调度按既有 runtime 证据边界另核。

Dossier 写入每动作保护全旧行/其他表，只允许当前 Grant 的 status/version/updated_at，新增限定 grant_id 的 GrantFile/Decision/Receipt 及一条对应 dossier Audit；scope fields/记录/逐文件 metadata immutable。Receipt digest 为 rules.canonical `{action,payload}` 的 SHA，propose 的 expires_at 原 UTC 规范化，decision payload={grant_id,version,reason,confirmed}；Receipt.store_id 为来源店，不是接收店；无 FlowReceipt/GroupReceipt/Task/FlowEvent/Cash/StockMove/会员流水新增。propose/decision 返回 `{grant,replayed}`，不套用 Case command 回执。

真实每次成功 record/directory/file GET **分别新增一 DossierAccess+一 `dossier_read_{action}` Audit**，在返回 JSON/字节前 commit；action/file_id、grant_version、actor/current role/access_version、接收 store、scope_digest 和发生时间精确绑定。listing/detail/source/catalog 不追加 DossierAccess；页面焦点/可见性重验可能触发另一次实际 record GET，必须逐实际请求计账，不能固定整页只有一条或整 audit 表排除。下载不要再调用 response.body 以免驱动重读，使用 native download 原件+SHA/size/Content-Disposition/nosniff/no-store/CSP sandbox 核对；DB BLOB 仅内存比较，报告 metadata/长度/摘要。所有其他 Case/Task/Customer/车辆/钱包/现金/库存/附件字节与旧授权事实全行不变；登录完成后建立业务基线。

快照白名单为 definition_version=1；case 严格14字段，customer 默认仅 name，vehicle 仅 vin/model/color；events 含 id/label/from_state/to_state/occurred_at，最多最近200条且 event_total/events_omitted 一致；金额为整数分，未知 cost=null 保留。授权有效期实际上限 **366天**（客户历史授权的365天合同不同），至多100逐件文件，日期须带时区、未来且不超限，confirm必须true。授予/复核同时核原版本、快照依赖、文件完整 metadata/hash、原双方岗位/账号代次；读时重验两店active、请求人/接收人/批准人代次与岗位、source可读、文件 usable 和冻结metadata。

## 条件与未覆盖

可在原 UI 追加空门店422、管理员自身降权/停用409和旧版CAS409；记录服务器实际拒绝后断言精确原写入/零写边界，不把 self409 说成最后另一管理员删除已验。自批/未获金额/不匹配岗位控件原本不存在或 disabled 时，留真实0请求的展示保护；不通过脚本注入字段/HTTP、重放或改源版本制造服务端拒绝。真实403及带权限语义422会由原异常处理器追加准确 `escalation_refusals`，须按实际路径/actor/store/message/category/source=page/null消费允许唯一新增，不能统称整库不变。

真实过期仅以上G3实际时钟结果计；短期限跨日、取消/拒绝分支、停店/停员、另一管理员最后active admin、真实并发/多浏览器竞争、超366天、100文件资源边界、已批准后新增附件、正文病毒扫描、PG/恢复及员工体验仍独立条件。排除的业务类型为 business_entity/opening_import/reconciliation/interstore_clearing/retail_group_rule/business_finance，不利用分享入口开放管理类原单。原普通 case/file 路由仍 StoreScoped，接收页没有原单/action深链；可见控件验证不冒充任意越权 HTTP 已验。首次实际出现事务409/503应保留失败，不重试求绿；当前 routes/get_db 潜在SQLite写竞争只能以后续真实结果定位，本文不声称已经复现产品缺陷。

建议后续独占作者文件为 `tests/browser_click/roles_dossier_business.py` 与 `docs/architect/tasks/roles-dossier-click.md`，三元导出建议 `ROLES_DOSSIER_SCENARIOS`、单场景 `roles-dossier-hk190`、固定有限900秒；须根另登记精确 patch 后才写。当前没有新测试脚本和运行结果。

## 读取指纹

HEAD `8993ca8c755194a42a48e7323fe355e80c6bf9ae`；工作树有根与其他作者改动，以实际字节为准。19源文件组合指纹 `9239b29cbfa6a8a232a90f263ab2043b5d429efac5beb194bd980246644c262e`，算法：按路径排序，拼接 `path+NUL+sha256(bytes)+LF` 后 SHA256。文件为 app/{main,schemas,security,tenancy,user_access_service,user_access_models,assistant_runtime_access_signals,dossier_grant_api,dossier_grant_service,dossier_grant_models,dossier_grant_rules,flow_documents,flow_engine}.py、web/{app,dossiergrants}.js、tests/browser_click/{system_management_business,system_followon_business,sales_order_business}.py、business_acceptance_catalog.json。

| 核心源 | SHA256 |
| --- | --- |
| business_acceptance_catalog.json | eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff |
| user_access_service.py | 34edda137dabb428e636e823c1a4d80431ae39fe4386481dac45c4fbb581bf77 |
| dossier_grant_api.py | dc3719ff796a7b0a9323536b6a00cb5ccde6b6a28ed49e6f87a8a42fc2cccfee |
| dossier_grant_service.py | 3c919aa4686968daef8b6b8e4ebb050476876c4e16097e094793905ca16825af |
| dossier_grant_models.py | 3334bd5a69b4eef838fe55cfb114dbb1d2bc1dee7d2752bf20b01b8f21dd17de |
| dossier_grant_rules.py | 7563327920e998234de0ee05549e6a50d58b581403c3ed7c46fcbd324a181df7 |
| web/dossiergrants.js | f2975794ecf7f4122cede8c637147ea9438bee75f46c79940fd895dab4b3667e |

检查为原接口/schema/UI/model/回执及角色来源只读对照；没有执行验收，也不修改共享进度。
