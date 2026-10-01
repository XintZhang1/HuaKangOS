# 会员身份、识别卡与本金原款点击候选

2026-10-01 根接线追加：冻结f2897c…候选经原UI/来源/旧行守卫窄审后纳入外部镜像白名单及统一注册，第24场景。没有新增fixture或生产会员改动；automatic-business07正在全新镜像联合执行，尚无会员实际结果。下文“未注册”仅为作者冻结时历史，五完整check与HK124/125仅partial口径不变。附件实际字节仅内存核验，来源及凭据仍全部外部；人工体验与193完整业务不继承。

2026-10-01，负责人 test_inventory。精确授权为 PATCH-M8-4-BUSINESS-193-10；只新增本页与 tests/browser_click/membership_business.py。候选已落盘并完成下述静态检查，尚未注册、未启动业务实例、未运行浏览器，不记录任何运行通过成绩。共享注册、白名单、fixture、生产及计划均由根维护。

## 五项完整候选与两个局部支路

入口常量为 membership-hk117-128-118-089-094，函数 membership_business，导出 MEMBERSHIP_SCENARIOS 单个原生场景，候选超时420秒。沿现有 Evidence、登录、上传、主档候选与有限原源检查点，不新增执行平台。

| 原需求及 check | 实际输入与要求产生的原结果 |
| --- | --- |
| HK-117-business 会员信息管理 | 销售从原客户列表检索本人同轮客户；服务顾问用完整电话核对、明确选择新建独立身份并确认关联，再开通零本金会员。原客户、身份、链接、会员及请求收据一致；销售本人读取会员，实际点击独立集团权益页，开通不制造识别卡、资金、有效期或赠品。 |
| HK-128-business 会员卡生成 | 服务顾问从无卡历史的本会员申请首卡、上传客户确认凭据并以原本人待办执行；唯一首卡生成代次1，原单、任务、会员事件和审计一致；完整原卡号实际只读查询识别该客户。 |
| HK-118-business 会员换补卡 | 分别建立原卡挂失单及换补单，各上传独立凭据、各确认原本人任务。原卡号及历史保留，旧卡先 lost 后 replaced；新卡唯一、代次2、previous_id引用首卡。挂失及换补旧号均原生查询404，新号有效；拒绝后实际关闭、明确放弃原填写，再重新检索该客户。 |
| HK-089-business 会员储值卡充值收款 | 服务顾问申请100.00元本金，原财务待办必要时由主管原UI转交本人。财务上传独立合成到账凭据、选同轮采购账户、填唯一流水并实际确认。冻结10000分、唯一正本金 GroupEntry、原 CashEntry、双边内部往来及会员余额一致；本金、识别卡和权益分别保护。 |
| HK-094-business 会员储值卡退款 | 服务顾问向上述精确原充值申请40.00元；另一主管原本人待办批准，先占4000分；财务上传另一份独立退款凭据，从同原账户填不同流水并实际退款。负本金、正金额出款现金、原退款请求及原任务一致；净本金6000分、占额0，原充值及现金不可改写，原内部往来等额双边。实际刷新原账不新增业务。 |

HK-124“会员储值卡充值”和HK-125“会员储值卡退款请求”仅记录普通本金局部支路及其有限来源ID为 partial，不提交这两项 business check。原组合套餐发布版本、条款接受、购买履约、完整未用份额退款、赠品批次及取消释放未执行；不得将这两个局部结果记成完整需求通过。

## 同轮来源与真实岗位

候选只读取本轮外部 browser-click-report.json 已注册并 passed 的两个精确场景：

- sales-order-hk008-009-011-022/business-checkpoint.json 的 report_sources.customer_id。
- vehicle-purchase-hk171-177-178-026-021-018-029/business-checkpoint.json 内 HK-021 原证据的 payment.account_id。

检查点必须 complete/passed、每项实际 passed，目录摘要及 origin/source/runtime/evidence/database 五项来源一致；自身、目录、售前、采购及销售脚本指纹必须匹配同轮稳定镜像。数据库必须处于该轮外部 runtime。只重新核这两个有限ID的实际本店、sales_peer本人客户、可联系完整电话、启用账户及真实 UserStore 岗位；不扫描全库选最新事实、不借demo会员或旧首卡、不继承另一轮成绩。

复用 business_fixtures.sales_order 中 sales_key、service_key、manager_key、finance_key，且核实际用户及门店1 UserStore角色。新增岗位、fixture及预置会员余额/卡/订单均为零。原待办若归demo同岗员工，只由随机主管实际打开原任务表单、选明确本人并填原因转交；AssignInput仅原version/assignee_id/reason，没有伪造request_id。

当前原合成实例没有本店经营主体策略；候选显式核此条件，并照常调用原主体守卫。若条件改变即失败留证，不能关闭守卫继续。此支路不构成生产经营主体、合同抬头或银行验收。

## 原 UI、API 与数据库合同

所有业务写入都由页面唯一且可见、可用的原按钮和表单确认，捕获原POST与随后的真实页面GET；检查同源Cookie、CSRF、x-app-request、当前店及请求号，仅存请求号摘要。不使用fetch/API写入、SQL写入、DOM注入、force点击或未知结果重放。

原路由为 /api/group/identities、/api/group/identities/link、/api/group/members、/api/group/members/{id}/actions/{refund_request|refund_approve|refund}，以及 /api/membership/members、/api/membership/cards/lookup、/api/membership/orders 和 /api/membership/orders/{case_id}/actions/execute。原审批/支付待办转交及文件上传沿 /api/flow/tasks/{id}/assign、/api/flow/cases/{case_id}/files。

会员执行分别携带实际 order/version、case_version及member_version；退款另携带准确原请求版本、原充值ID和原单版本。GroupReceipt核本人/本店/唯一request_key、原动作及精确载荷digest，并要求保存result与该次原响应相等。每次提交核有限新增条目数；原 FlowEvent、MembershipEvent、GroupEvent、AuditLog 及原任务分别保留可追溯事实，不以弹窗关闭或提示字代替结果。

业务快照保护所有原业务表；只有该步允许的追加表可新增，原单/会员/卡/退款/账户/任务更新只准明确原ID及列，其余旧行逐列不变、不许删除。识别卡操作只准当前会员version/updated_at变化，不允许金额变化；原卡只准status/version/updated_at变化。充值/退款不触碰识别卡、会员期间、积分债、权益钱包、规则、组合及库存，原充值、原现金和旧流水逐行保留。登录审计发生在每步业务基线之前，不排除整张audit表。

DB读取仅6处 SELECT 调用（两处有限白名单表名 helper）；沿现有只读SQLite Evidence。不导入app。文件是该原单的外部合成TXT，由员工实际选文件上传；核metadata、结构检查、实际blob字节等于所选内容、长度及SHA。正文bytes仅在内存验证及全量旧行守卫比较，证据只写文件metadata和stored_blob.length/sha256，绝不default=str/base64处理正文。无User/password_hash、会话hash或凭据输出，随机密码仍只留原外部私有文件。

## 结果边界与交接

每项初始 not_tested，原动作完成并核一致才写该项 passed；异常使当前项 failed并停止，剩余项不自动通过。最终只有五项及两个ordinary本金partial都实际完成，场景complete/passed才为true。各截图、输入、日志与checkpoint全在原外部Evidence目录。

最终 membership_sources 输出有限ID：customer_id、identity_id、identity_link_id、member_id、card_issue_case_id、original_card_id、card_loss_case_id、card_replace_case_id、active_card_id、topup_case_id、topup_entry_id、topup_cash_id、account_id、refund_request_id、refund_entry_id、refund_cash_id。

人工流程简洁度、文案审阅、真实到账/退款、ClamAV、员工试用、会员有效期/积分/权益消费、组合充值退款、真实经营主体和193完整业务验收保持 pending/false。本候选未行使旧admin自批例外，也不改变原业务规则。

静态检查：Python AST通过；5个原标题与business check精确绑定当前source_reviewed目录；6处SQL调用均 SELECT-only，有限动态表名单人工核对；所有跨脚本helper实际存在；未导入app、未运行候选；两文件无尾随空白。原UI参数、岗位、上传标签“文件名 · 业务凭据”、Task AssignInput和当前API/schema/service/model已逐路径静态核对，仍须根短审及新外部镜像实际执行，不把静态结果计业务成绩。

冻结候选 membership_business.py SHA256：f2897c762cbb9b0de213679afe47e86297a55fe7cdbeb986f20bd65ba0e649f8（834行）。本页hash由交接另报，避免自引用。
