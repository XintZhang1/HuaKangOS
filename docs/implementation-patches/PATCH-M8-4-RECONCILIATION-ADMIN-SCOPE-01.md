# PATCH-M8-4-RECONCILIATION-ADMIN-SCOPE-01：独立复核身份的原权限投影

2026-10-01，当前M8.1，仅 `tests/browser_click/finance_followon_business.py`。finance-followon04所选5场4通过1失败、退出1，源a2632178/脚本6d03251f镜像稳定，23完整自动check；新场景在零动作的依赖检查失败，未办理票据或核账。原tenancy.role_for_store/accessible_stores对有效管理员按有效门店投影，不要求user_stores行；外置只读核本批admin有效且无该表行，原候选错误要求所有岗位都存在逐店行。原业务规则保持。

相关三验证实例均已结束。只将明确admin前置核对改为当前users有效admin和一店有效；财务/店长仍要求实际逐店岗位行。每次read_as同时观察本人真实原登录POST响应，严格核ID、account_role、当前role、active_store_id=1、非汇总和store_ids包含1；不伪造或新增授权，不借管理员办理票据/收费，仍仅第三版reconcile_seal独立复核。原页面GET、原Task.role/assignee、CAS、收据及全部旧行守卫保持。AST和短审后新镜像复验，零动作失败不记业务通过。

e1fb54bb经根AST及独立tenancy原合同/增量短审，真实角色投影核对无确定缺口，原reconcile_seal管理Task与实际admin岗位分开留证。新联合镜像待出结果。
