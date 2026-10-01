# PATCH-M8-4-BOUTIQUE-EVENT-SOURCE-01

2026-10-01，M8.1。全部关联验证进程已收尾。精确仅 tests/browser_click/boutique_business.py 的末尾 installation_event_id/accept_event_id 两来源表达式。

business-member-boutique-20261001-05 六本地check已真实完成，包括供应商退款与零售三类资金守恒；但汇总时 KeyError id，因此整场/整轮失败，59完整/65诊断原件保留。原 MF.event 返回 event_id/audit_id/action/detail 的已核元数据，末尾误用 event.id。修正为其真实 event_id，保留原独立Event/Audit/当前原单校验，不从另一行猜ID、不将旧局部改passed。新镜像再次完整执行六项并生成完整有限来源才计通过。
