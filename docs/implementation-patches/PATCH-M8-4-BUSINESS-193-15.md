# PATCH-M8-4-BUSINESS-193-15：原开票与期间核账候选

根接线：作者最终候选SHA256 `8850917fc8472149b74408f28dba85647f19053cc7c75fcd4a0614a384e9ab0e`，文档 `24414ddc240a3f020b5c234d1b6731e83f94ff1d9345416b6be6c35df07daf1b`。根独立静态短审对照原invoice/reconciliation schema、UI及原服务，Task三字段/先等GET和DOM、双CAS、原回执digest、两事件追加新版本、原CSV完整字节/票据单审计、旧行保护合同无确定缺口；AST通过。保险最小实例结束后，仅扩run.py该文件白名单/scenarios.py单导入拼接，当前注册30；首次实际两项无成绩，随后新镜像同轮原财务来源定向验证。

2026-10-01，按业主193项实际点击持续授权及冻结 `docs/architect/tasks/finance-followon-scope.md`（SHA256 `60c28fc3a6bb6d1791475a66a049ecb3e5dc928e3c77b57b7bba17a22dc8ac71`），只新增 `tests/browser_click/finance_followon_business.py` 及维护 `docs/architect/tasks/finance-followon-click.md`。

精确完整候选为HK095「月结查询」、HK097「开发票」两项。不得把蓝红票、差异、重算和封存分拆成新需求数量，不重复HK096，不借预收退款替销售原款退款。生产、fixture、共享runner/注册与计划只读，不导入app或运行实例。必须取未来本轮finance五项已完整passed的finance_sources有限来源，重新核本店A/B及原有效款、原版本/角色；没有该事实则停止，不用API/SQL造结果。

原财务UI未封存核账v1；A蓝票60申请/独立批准/明确实际票面58与差异复核、原票冲红8、新蓝10恢复净60，全部旧款不变。旧批来源变化原拒绝后实际重算v2，有限有据差异核对/独立封存、复开v3再封存，旧manifest/summary/digest不可覆盖。CSV实际原下载、全冻结manifest精确逐行对照；下载审计依原合同单独核，不能额外HTTP获取代替真实文件。本人Task、双CAS、幂等、金额整数分、原件字节/摘要、独立manager与全旧业务事实保护保留。

冻结及独立审阅后根再加入白名单/场景注册，候选不计成绩；发现原生产缺口另报精确补丁，不放宽守卫。外部税务、银行/实物/员工/ClamAV/PG/Linux、模型及193全部人工体验/生产条件仍待相应证据。
