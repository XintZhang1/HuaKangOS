# 客户主档与实际服务点击候选

对应 PATCH-M8-4-BUSINESS-193-05，仅新增 `tests/browser_click/customer_service_business.py` 与本任务文档。根负责镜像、注册、运行和最终汇总。候选沿现有 Evidence、原生登录、原表单及外部 business-checkpoint，不导入工作树 app，不启动服务，不新建夹具或测试框架。

完整自动检查仅四项：`HK-098-business`、`HK-107-business`、`HK-108-business`、`HK-109-business`。场景 `customer-service-hk098-107-108-109`，导出 `CUSTOMER_SERVICE_SCENARIOS`，候选超时360秒。source目录逐项标题与稳定check_id先核对；错误终止当前项，后续仍not_tested，成功自动检查仍business_accepted=false、simple_flow/concise_copy人工pending、full193false，不继承旧成绩。

HK098：已有service通过原客户表先搜索、实际新建无电话客户，编辑补电话和说明；另一个同号客户在原同号提示下先被明确另建校验阻止，零业务POST和整库业务hash不变，再由员工勾选“仍然新建客户”保存独立档案。原客户及旧客户保持，原owner不随主管维护变化。service撤回联系后本人恢复由原PUT返回403，原中文refusal、完整业务hash和明确放弃表单留证；manager原表核对客户意愿后恢复，保存CAS、审计、原列表及刷新匹配。无业务API直写或结果未知重放。

本店车辆来源：service通过原客户车辆表选择此客户、17位VIN、车牌车型和明确来源，不填猜测的集团身份编号。原service创建客户与车辆集团身份及本店关系；同号独立客户不自动合并。原编辑维护车牌车型，VIN/客户/集团身份/店归属保持。两次原表观察填实际合成日期和整数公里（昨天12000、今天12125），来源明确、两条追加、最新有效值正确显示；不产生库存、现金、会员余额、交付或保养事实。真实已结案咨询通过原候选明确选择后，形成非空本车服务摘要，刷新原历史/API/DB一致且无重复。

HK099只在外部checkpoint的 `partial_requirements` 记录 `partial/local_scope_passed` 和来源证据，`acceptance_check_submitted=false`；绝不创建 `HK-099-business` 或提交HK099passed。跨店身份、摘要授权、来源店独立批准原单/逐件文件、期限撤销与有据原观察纠正仍未执行，完整HK099由后续独立场景补齐。

HK107/108/109：同一真实客户与车辆，分别创建独立consultation/complaint/rescue原单，救援原表填写明确合成停车位置，原候选明确选择本人service经办。每单实际start，再两次不同当面办理内容、结果和下一次日期，最后原resolved结案。Case/CareCase/Task/Record/Event/Receipt绑定本店本人；原记录事件单次追加，唯一care_handle任务期限更新，结案done_by/date与原事实匹配，刷新不重复且结束后无办理按钮。客服结案不宣称真实外部派车、车辆维修、保险续保或付款。

所有数据库读取均SELECT。每次正向提交核对原Cookie/CSRF/店/ID/CAS/request_id回执，并对完整业务snapshot除本动作有限表以外保持；有限表的旧行只允许更新本客户、本车辆、本原单或本任务，追加记录旧行不可改。其它客户、他店、CashEntry/StockMove及无关业务保护。有效主体策略若已存在，原新建事务仅允许本店主体control推进与追加原CaseEntityContext，不覆盖历史主体。DOM只通过原可见控件填选、点击与浏览器刷新，不用fetch、Cookie桥接、业务SQL或强制改状态。

候选尚未注册、未启动app或浏览器。静态核对及交叉代码审阅完成后冻结交根；实际失败保留原报告并由根先收尾进程，再登记适配或生产修复。自动UI/API/DB断言与人工体验、真实模型、PG/Linux、员工试用和生产验收分别留证。

独立只读短审已核对四项范围、原API/字段/拒绝/车辆受控版本、记录任务事件与旧行保护，未发现当前Windows执行的明显合同误配。审阅指出Linux默认UTC日期可能与夹具业务日不一致：`fixture_server.py`明确`APP_TIMEZONE=Asia/Shanghai`，原`app.db.today`使用该ZoneInfo。本候选五处日期统一通过仅标准库的`business_today()`读取同一明确业务时区，不导入app、不增加用例；静态AST、四check源绑定、SELECT-only与无业务API直写再次核对。Linux及真实运行仍未执行，不将时区修正写成跨平台验收通过。

根集成与实际结果：已注册到原统一镜像和汇总。Fresh01在本人恢复联系原403正确拒绝时，装置误要求不新增服务器refusal；实际仅本人/本店/原PUT/真实message的rule记录新增，客户未变。根局部核对仅允许精确一条未消费rule/page refusal、can_escalate=false、旧行及其他业务表保持；原取消填写也不产生后续变化。Fresh02原客户已通过，但建立咨询合法新增flow_care_create审计被候选遗漏；根仅在客服原动作允许追加audit，逐次严格核本人/店/原单/事件label、before=null和实际after状态，旧audit完整保持。两失败外部原件保留，不称产品硬bug或回退正确审计。

Fresh03外部`V/browser-click/business-customer-service-20261001-03/evidence/`同次原UI四check通过、selected/退出0、174动作/66点击、页面异常0；HK099本店来源及已结案咨询历史partial/local_scope_passed，不提交完整check。生产e25325fbe9f82527fa7d9ebff5750d8505fa7984c6d58e4904b631b47a488c58，脚本998c2210416900706800a4dbac6c08040f670eddbbbf8b8e1fb67402006daae6。人工体验与全193仍pending/false；不同selected结果不拼成完整注册通过。
