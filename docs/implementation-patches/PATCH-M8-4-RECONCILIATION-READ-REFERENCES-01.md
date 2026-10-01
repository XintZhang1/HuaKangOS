# PATCH-M8-4-RECONCILIATION-READ-REFERENCES-01：身份与门店只读表范围

2026-10-01，当前M8.1，仅 `tests/browser_click/finance_followon_business.py` 的 READ_TABLES。automatic-business10完整32执行、31通过1失败、退出1，源0ce46e44/脚本a55c795a稳定；财务后继仍零动作，在ADMIN-SCOPE-01新增前置读取有效users时被原参考表白名单拒绝，尚未办理两新项。原角色判定修正有效，但根遗漏两原参考表的登记；此为候选接线错误，不是业务权限拒绝。系统两新项及七报表本次已整场通过，不能将局部拼成32完整passed。原失败保留。

关联实例已结束，只登记users、stores为SELECT参考表，保持可写Guard TABLES原集合不变；二表不进入任何允许修改或追加范围，不持久化users行、密码hash或凭据。仍核本批有效本人、有效一店、非admin实际逐店岗位、原登录真实身份与当前店投影，admin仅第三版独立reconcile_seal。AST与独立短审后新镜像原最小财务链复验及后续联合，不以白名单存在记通过。

静态复核：SHA256 e2c5123c1149d75326d24fdc90e94094c0f87c1aff14f2c90b4546698cb4dc8b；AST及click_scenarios独立短审通过，仅READ_TABLES两项追加，原Guard集合和身份/门店原登录核对不变，无users凭据输出。实际复验尚待新镜像。
