# 任务：HK190 角色与逐单逐文件授权真实点击候选

负责人：`test_inventory`，交接根代理。依据 `PATCH-M8-4-BUSINESS-193-34` 和冻结范围 `roles-dossier-scope.md` SHA `7579d6ba18a8cedbbd0e9b1419d8b8bf38a0c6dd400f2c03998b89d5e7902560`。本阶段只新增 `tests/browser_click/roles_dossier_business.py` 与本文；没有导入 app、运行应用或浏览器、注册候选、修改生产/夹具/helper/目录/runner/计划。当前 M8.1 既有根任务不变。

## 原合同与有限同轮来源

唯一完整候选是 HK-190「角色管理」/`HK-190-business`，原 `#users`、`#dossier-grants/received`。导出 `ROLES_DOSSIER_SCENARIOS=(("roles-dossier-hk190", roles_dossier_business, 900),)`；三元组、固定有限900秒。原账号访问版本/门店岗位/集团开关及指定员工逐原单、逐文件授权分别留事实，Dossier 不生成原业务 Task 或现金库存。`full_193_business_acceptance`、`business_accepted` 和生产验收保持 false，人工体验与文案 pending。

依赖必须来自当前外置 `browser-click-report.json` 的真实 passed/完整 checkpoint、相同原目录 SHA/镜像/五项 provenance；父闭包从 `system-management-hk189-191`、`sales-order-hk008-009-011-022` 的原 dependencies 逐项重验，不拿历史截图/静态文件表示通过。可选已执行父名称严格为 **`system-followon-hk192-193`**，须 passed 且 temporary_auditor_restored=true；范围旧拼写不继承。

- HK191 staff_actions[0] 的甲账号 role=sales、二店 service、UI新第三店 auditor，无一店授权；[1] 乙账号 role=sales、一店 manager。两人 active/完成改密、当前 memberships/access_version 每次限定ID重读。现有合成 admin 独立复核；没有新 fixture 或扩大岗位。
- 甲/乙随机密码只从本轮父 observations 唯一私有指针读取、校验本次runtime和ID/username/当前阶段，全部密码加入共用 scrubber。本文和证据不含密码、User.password_hash、session/CSRF hash。本文所述岗位为执行合同，尚无本候选实际新版本/登录结果。
- 原单固定为销售父 report_sources.delivered_order_id，并由HK009 evidence.case_id交叉核对。两件有限原件固定 `handover.generated.id`、`signed_handover.file.id`；签回必须引用本生成件。只读核当前同store/case/类别/原SHA/size，不扫描补找附件。当前 source_case_version 取真实 source GET；原历史与原字节保护，不倒贴早先父版本。

## 已落盘路径

| 原生步骤 | 实际结果断言与保护 |
| --- | --- |
| G1 乙原页面选择明确本店原单、二店甲，记录=true、电话/金额=false，仅F1、用途/7天原期限/明确确认 | POST201，新原grant+一逐件metadata+一DossierReceipt+一精确 dossier_propose Audit；锁当前原版本和双方岗位/访问代次、冻结scope摘要和白名单记录。原自身批准按钮不存在，只作真实0请求展示保护。 |
| 乙原“核对原文件”真实下载F1并解析生成DOCX核本客户/VIN，admin不同员工独立批准 | 原原件下载仅一download审计；原字节/size/SHA与父/BLOB逐一核对，正文核对不等于自动脱敏。approve以本授权当前version+reason+confirmed，一Decision/Receipt/Audit；原source/文件/其他grant不变。 |
| 甲二店服务岗位真实收到→打开→record→F1核验并下载 | 原Record与Grant.record_snapshot完全一致，头/姓名/VIN/最近200原事件窗口与限定原DB来源一致；未选电话/资金/自由嵌套资料/关联单/源操作/未选F2不展示。每次真实成功record/file GET分别Access+审计，下载用native原件，不读取response.body触发重读。 |
| 两真实admin浏览器窗口，一旧表单保留access_version；主窗口仅甲二店service→auditor、集团查询=true，不授一店 | PUT原完整UserUpdate，唯一访问回执/审计、access_version+1、全甲旧LoginSession撤销，其他人会话不变；旧窗口实际原PUT409与完整原文案，保留请求号、实际放弃旧输入后刷新，不重放。甲旧页真实me401后本人重新登录。 |
| 甲核G1 suspended；真实集团只读投影只二店/第三店、Dossier目录关闭；admin原UI恢复原岗位和原集团开关 | 第二真实PUT使访问版本再+1，旧会话再次撤销；甲再次原生登录恢复service，G1仍suspended/can_read=false，原Grant物理approved/版本/快照/文件/决定都不改。失败时只允许同一个甲的原岗位/开关经原UI明确恢复，失败证据不改为通过。 |
| G2 乙新file-only申请，仅F2，record/contact/financials=false→admin独立批准→甲真实directory和下载→admin实际revoke | 新独立scope/request/决定，不复用G1。JSON不含原record/customer/vehicle/金额/F1；directory和file分别Access+审计。revoke批准v2→revoked v3，一Decision/Receipt/Audit；甲刷新后原内容/下载控件消失，旧元数据与已合法下载副本保留。 |
| G3 乙新record-only申请，原datetime-local当前UTC未来整分钟期限→独立批准→甲真实读→真实等待并刷新 | UI input以真实Date.now/浏览器offset求本地值，向上取整留提交/批准裕量，保存时仍至少2分钟有效；每段实际等待最多50秒、不改钟/库/原期限。服务器原detail/list为expired/can_read=false，物理approved和原决定/读取历史保留；到期后不得出现成功payload读取。 |

## 守卫与观察合同

原业务全表摘要保护，允许表中的所有旧行再逐列/主键保护。Grant仅当前id可改status/version/updated_at；Scope、Record、GrantFile、Decision、Access、Receipt immutable。新增对象逐个核当前grant/来源店/actor/动作/version/scope_digest。Dossier Receipt是原 `{action,payload}` canonical SHA，propose期限转UTC，decision payload准确grant_id/version/reason/confirmed；不误要求FlowReceipt或GroupReceipt。listing/detail/source/catalog只读；接收 ended detail严格限定无source payload的17字段。收到的页面有本人本店申请入口，不开放来源单办理。

`AccessLedger`仅被动观察原页面成功GET；record、directory、file各自匹配原DossierAccess和 `dossier_read_{action}` Audit 的grant/version/actor/currentrole/access_version/接收store/file_id/digest/时间/原因。页面focus/visibility可能合法再次读取，按实际GET逐次计账，保全每条旧Access/Audit；不把审计全表排除或假定每页固定一条。原可见导航在外层精确读取Guard下核对合法重核，不放宽现金、库存、会员、源Case/Task/Customer/Vehicle/附件或旧授权。

角色改权只放甲 access_version/can_group_summary 和甲明确UserStore替换，密码/其他User列/其他员工关系与会话全保护。UserAccessReceipt request_data排除request_id、保留access_version；标准json.dumps `{target_id,values}` SHA、before/result/audit绑定完整原列表投影及实际DB列。原启用runtime时，按甲当前/原store和有限本人Run/FollowupGrant派生门店集合核每个WakeEvent.signal_key/topic/null业务指针/source_ref；不臆测固定数量，也不把worker调度状态当原业务办理。

新单响应先被动监听，再按唯一POST返回grant.id等待同id原GET，顺序竞争时绑定正确实体并清理listener/Future。每个modal先visible再title，原控件visible/enabled等待；不注入字段、Cookie、确认或源码，不写SQL，不调用HTTP写代理。下载response只检查原头和native download，真实BLOB在内存比较长度/SHA/字节，正文不进JSON；DOCX只读解析本次下载的固定内部document.xml，无app导入。

成功后有限 `report_sources.current_employees` 输出 receiver/sender 的实际id、当前store_roles/access_version、private_source_scenario/对应私有账户key/current_password_stage，不含私有密码或hash。receiver按合同恢复原两店岗位/原集团开关且版本保留+2；sender一店manager不改。下批仍须即时重验，不以本文预写实际新ID/版本。

## 静态检查与待测

2026-10-01：候选AST、4个原helper模块/导入符号、13处SQL调用（含f字符串）SELECT-only、0app导入/0直接HTTP业务写、原三元900秒导出、精确原HK190题目/check和敏感数据/BLOB不进checkpoint的人工审查已完成；空白检查完成。只读核实际原API/schema/models/JS及文档34。当前没有候选运行，不记1passed或业务验收；viewport、下载、原异步render、到期真实等待、回执/审计实际并发仍待根唯一外部实例。

未测条件：原隐藏自批按钮没有实际403提交；另一位最后admin/真实并发互撤、停店/停员/源负责人转交、资源超限/后续新文件、任意越权HTTP、短时跨日/PG/Linux/ClamAV/生产和员工试用。若运行真实GET/POST出现403或带权限语义422，原异常处理器可能新增准确Refusal，须保留真实原件并单独定位；本候选未伪造该分支、不全表豁免或盲重放。SQLite事务竞争出现409/503应真实失败并诊断，不能靠重试改绿。

读取源码组合SHA `6fd16a4db367b3d4625d40599d1b691183cee143316e3f9cb9b45c8d083d2047`，23路径按排序拼 `path+NUL+sha256(bytes)+LF` 后SHA：app/{main,schemas,security,tenancy,user_access_service,user_access_models,assistant_runtime_access_signals,dossier_grant_api,dossier_grant_service,dossier_grant_models,dossier_grant_rules,flow_documents,flow_engine,flow_specs,sales_quote_specs}.py；web/{app,dossiergrants}.js；tests/browser_click/{system_management_business,system_followon_business,sales_order_business,sales_business,vehicle_purchase_business}.py及business_acceptance_catalog.json（目录SHA eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff）。候选和本文最终SHA由冻结交接记录，本文不自嵌循环hash。

最终自审附记：临时交接的171c9828尚未注册，补读原flow_specs/sales_quote_specs后发现Dossier快照的kind_label应取原工作流名称，不能用销售页面标题“预订合同”。只把本候选v3/v4快照断言分别更正为“车辆报价与交付”/“车辆报价与明细服务交付”；已提车状态、scope、来源、Guard及所有已注册文件不变。这是静态测试适配错误，未作为实际失败、产品缺陷或新版通过登记；更正后重新AST和入口形状检查并冻结交独立短审。

提醒作者历史47c40488未修改；根唯一接线修正5c391d96已注册首跑，属于根的独立源码/运行指纹。本任务不修改或复用其成绩。
