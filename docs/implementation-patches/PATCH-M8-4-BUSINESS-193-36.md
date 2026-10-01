# PATCH-M8-4-BUSINESS-193-36

2026-10-01，M8.1。按 receivables-remaining-scope.md SHAcbbc51e196a566f68af56394a415dd04018462bc63d2eb61ff19d9ff32077cbd，仅新增 tests/browser_click/receivables_business.py 和 docs/architect/tasks/receivables-click.md；生产、已有helper/候选/fixture、runner/注册/目录/计划只读，不运行。选项A原界面另购/收车一个新明确VIN，避免借用已交付父车辆；单场景receivables-hk157-158-159 / RECEIVABLES_SCENARIOS / 有限1500秒。

三完整HK157/158/159，新的真实正欠额来源：普通Retail约定2000/实收500/待收1500；新签回配车销售10000/实收3000/待收7000及真实关联服务fee1000/实收300/待收700；现场纯作业Repair3000/客户2000+内部1000/客户实收500/客户待收1500，内部不造现金或客户应收，原接车守卫保持。工位如存在真实保留则原UI新建独立工位，不擅改他人预约/VIN锁；施工完成实际移出工位与客户出厂区分。

库存必须消费本轮完整父有限来源、即时足额真实库位；本轮追加Retail父若执行也须完整passed，不能使用零余量旧快照。来源不足时报告真实缺口，必要补原采购须后续登记，不SQL造库存或无依据改价格/数量。原财务KPI、全部正gap表/完整分页、同范围CSV和各原单原领域钻取核当前全授权来源；原没有专用应收图，不新增图或把cash_category当应收图。原独立批准/原本人/任务/CAS/幂等/整数/原字节/全旧行有限保护，合成前置不是重复登记旧业务checks。真实环境、员工、并发/占额及全193/生产条件保持待测。
