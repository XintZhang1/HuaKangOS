# 保险资金与原周期续保点击候选

2026-10-01，执行 PATCH-M8-4-BUSINESS-193-14；来源范围为已冻结 insurance-next-scope.md（8bdbd821…）。仅新增 insurance_business.py 和本任务记录，不改生产、fixture、runner、注册、目录或计划，不运行或导入应用。

七个独立候选 check：HK-013/014/077/113/114/115/116-business。沿同次主档启用 Insurer、客服 HK099 local_scope_passed 的明确客户车辆和采购真实账户，HK099 保持 partial。service/manager/finance 分别本人原 UI 办理；不借管理员，不预置业务结果。

候选已落盘，单一入口 insurance-renewal-hk013-014-077-113-114-115-116，900秒独立预算。没有注册、业务执行或通过成绩。两版独立核价、客户同版摘要授权，三个独立提交对应补件/拒绝/出保；保费220元实际代收、同原款代缴和独立确认12元实际佣金。第二原保单采用客户直付300元、零实际佣金独立确认，不制造店内现金。

真实业务日明确Asia/Shanghai。首保期是声明的合成D至D+10短期险，规则提前9天未触发、CAS编辑10天触发、同周期再生成不重复；不改服务时钟或DB日期。原“我的工作”今日提醒实际显示并点击同单。service原care_handle通过原care handoff交manager，保留原负责人/日期；本人两次电话跟进，旧源renewed原409全业务不变。新原保险显式绑定首InsuranceResult.id与CareCase.id/当前version，真正issued追加新的有效观察且保期D+365后才原close renewed。

随后首保单原termination→独立review→本版客户consent→finance apply，追加保险/提醒失效，已完成CareCase/Task/旧记录/ReminderBasis原行不覆盖。保险公司原代缴追回220、原客户款退款220、原佣金返还12分别独立现金与原账户/来源关联；新保单仍有效且原出保历史保留。每步当前原GET/CAS、本人Task和唯一原请求回执核对，未知结果停止，不换请求号重放。

全业务表摘要、旧行与旧附件字节受保护；允许变更逐表有限原ID/列，生成前有限枚举本店active CV≤500，仅版本/更新时间可变。另一店与无关Case、CashEntry、库存、原观察不得改。附件复用既有原上传helper，报告只保留metadata及真实BLOB长度/SHA；不序列化正文、base64或default=str。新增实例文件只写本轮外部Evidence目录。

最短同轮前序：采购场景账户与HK172主档、customer-service-hk098-107-108-109的099本店partial来源；不扫描旧run，不要求无关维修或销售交付。开始前检查没有其它启用提醒规则及未知旧renewal规则；遇到这些前置停止说明，不覆盖规则、不隐藏合法生成结果。使用已有service/manager/finance，无fixture扩展。原待办落在其它合成人时，主管先读同原FlowCase GET200/currentID/DOM，再按原三字段AssignInput交接一次；不向该独立接口虚构request_id。

静态核对已完成：960行Python AST、全部直SQL SELECT-only、无app导入、七项原标题/check_id一致、本人文件空白检查；未导入候选或运行实例。click_scenarios独立只读短审确认原POST包装、双层native资金metadata、Task/CAS、generate有限全CV版本、completed Care失效保护、三类原款及BLOB报告均未见另一确定静态误配。发现并精确修正一处装置类型适配：SQLite原closed_open_task存储值为整数0，改为==0；API与已解码JSON布尔仍保留is False。修前候选402ecc6f…留本页记录，不将其当运行失败或通过。

实际待测：所有原select/lookup与折叠区、Task岗位/版本推进、文件原类别与结构检查、三种结果、短期险边界、旧源409、真正新保期、三笔返还和失效投影、原行有限保护。原保险附件类别生产接线由负责人处理，本候选不改后端proof或前端过滤。未覆盖销售退车、采购退回、其它提醒类型/未知旧规则、任意多车辆周期、真实保险公司/银行/客户签字/ClamAV、PG/Linux、员工试用与生产。自动断言与人工体验/文案分别记录，business_accepted/full193 均 false；partial/failed/not_tested不冒passed。
