# PATCH-M8-4-RECONCILIATION-INDEPENDENT-REVIEW-01：复开版本独立复核

2026-10-01，当前M8.1，仅 `tests/browser_click/finance_followon_business.py` 当前候选。fresh finance-followon03所选5为4通过1失败、退出1；HK097整条蓝58/红8/补蓝10及三原下载已通过，HK095版本2已独立封存，店长明确复开版本3后仍用该店长封存，原服务按 prepared_by/submitted_by 拒绝403。两项整体仍未通过，局部HK097不继承为新完整批成绩；原实例已退出。

原 `reconciliation_service.py:419` 明确要求另一位店长或管理员复核，拒绝是正确规则。仅测试第三版 seal 明确改用本批已有、当前一店有权的独立管理员；财务继续提交、店长继续复开，管理员不办理任何原收费/票据写入，不代替员工业务身份，不新增授权。原任务先由有权店长在原页面明确转交该真实候选，随后管理员本人原登录/原凭据/原form点击，保留全部Task/CAS/幂等/原件/DB旧行守卫。原v2继续独立店长复核，无动态换身份求绿，不回放失败写。

实现后AST、独立短审，再新镜像同五场景及原异常路径复验。未经实际运行不记两新项通过；原生产、fixture、员工规则和数据不修改。

脚本355e4952经AST和独立增量短审：管理员仅本批原reconcile_seal、原Task.role保持manager、assignee为明确本人admin，Task与Actor岗位分别留证；原三字段转交、当前店角色、上传及全部守卫保持。实际待复验。
