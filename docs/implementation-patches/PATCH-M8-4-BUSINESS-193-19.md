# PATCH-M8-4-BUSINESS-193-19：四项财务与保险报表候选

2026-10-01，当前M8.1。冻结范围 `finance-report-next-scope.md` SHA256 `2652984edab3444ef237b75afb0b6f790d06245315ea3355c6861cca6d435890` 中HK141/161/162/163四项；作者仅新增 `tests/browser_click/finance_report_business.py`、`docs/architect/tasks/finance-report-click.md`，其他源/目录/fixture/入口/注册/实施计划只读，不导入app或运行服务/浏览器。

只消费未来本轮原销售/交车后、物资/首维修、保险、财务五项/开票核账完整passed检查点的有限原事实，先核真实当前店岗位、出处及全部旧行。原UI日期/筛选/全部明细与图、原单钻取和原CSV实际下载均沿原合同，三个日期与现金/佣金/成本/抵用分开；0终局不抹负向或真实原账。结算批次后续业务晚到允许原source_changed=true并核正确提示，不能重算求绿。material-value专用CSV原参数/字节/唯一审计独立适配，无多余HTTP或下载重读，实际事务缺陷如有另登记根修。

本候选不消费未冻结会员六项；HK169在其来源正式冻结及根补充范围以前保持not_tested。HK168及三种非空应收缺来源不计完整check，原160已通过不重复新增。正写仅原下载的精确审计，SQL SELECT-only；完整193、六项人工体验、真实外部/员工/PG/Linux/模型与生产边界全部保留。作者冻结自审、独立短审后根注册新镜像，候选存在不等于通过。

根接线范围补充：关联运行全部退出后，仅run.py的SCRIPT_FILES和scenarios.py固定import/顺序追加FINANCE_REPORT_SCENARIOS，在已冻结会员六项之后。1a536320经AST、根原接口/七表/金额/CAS/冻结CSV/58原表id及store_id适用列短审；额外会员精品只作161全范围背景，仍不新增168/169或其他会员验收。源条件与实际动态尚待本次新镜像。
