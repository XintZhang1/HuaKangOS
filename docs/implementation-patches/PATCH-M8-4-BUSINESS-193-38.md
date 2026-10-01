# PATCH-M8-4-BUSINESS-193-38：仓库来源与无旧简表采购批次点击候选

2026-10-01，延续业主193需求表尽量全覆盖、当前代码及浏览器交付授权。当前49注册四轮仍有在跑实例，本补丁只允许新增未注册owned候选，不改生产/注册/runner/原fixture/helper/目录/旧证据/业务规则/时钟。唯一实施项仍M8.1。

允许写 tests/browser_click/report_complete_source_business.py 和 docs/architect/tasks/report-complete-source-click.md；click_scenarios独占。一个有限原生场景 reports-complete-source-hk152-153 / REPORT_COMPLETE_SOURCE_SCENARIOS /1500秒，两个原HK-152-business/HK-153-business check。代码先静态审阅/独立核对，待全部关联实例关闭后才另登记白名单及接线，不预报完整通过。

有限同轮父为system-management真实第三店（active且没有legacy kind=purchase），现master/material采购原流程和库存当前实现对应的完整父；不得扫描latest、拼旧run、删历史单或改夹具去求complete。用原#users明确仅给三个原不同员工追加第三店inventory/manager/finance岗位，保留原所有岗位/账号/汇总开关，原access_version CAS、Receipt/Audit/精确Wake、旧sessions撤销均核，重新本人真实登录和切店；管理员只管理授权，不办理原库存/采购/资金。恢复原全部岗位时版本只递增，旧会话不能复活，所有其它员工/原业务/旧Grant保持。

第三店通过原可见主档新建必要单位/品牌/类别/供应商/账户/物资仓及两个库位、物资与零分配启用，真实物资采购、不同主管批准、本次实际收货及付款、原供应商退回批准/实物出库/原账户退款。只原UI实际输入明示整数数量和分金额，原证据文件外置，原price/version/task/receipt/事件/资金/库存/成本来源逐项保护，不能绕审批或借其它店可用量。没有必要的原前置入口、当前岗位或来源则如实停报。

HK153本人第三店当前真实日期批次没有历史简表采购差异，完整枚举逐行采购/收货/退回/原StockMove与冻结价格，独立核数量和金额守恒、全部原KPI/表/动态单位图/同范围CSV与原单钻取；全库业务旧行保护、一次export仅精确原Audit。不能删旧源、回填创建日、假造日期或把其它店遗留问题吞掉。

HK152以原功能合同的未知期初/有据期末分开验证：真实当前物资＋具体仓/库位及原基准/Entry，完整来源oracle、API/表/期末图/三原CSV/原单钻取同范围，期初/期间未知仍null和明确说明；已知非零期末须有来源成本，不补零。period_complete仍false时不称历史完整，真实start>启用日的完整历史窗口另列not_tested；旧partial失败/成绩保留，不直接升级旧结果。不改原报表定义或降低源完整性合同。

人工六标准、真正历史期初窗口、日期授权自然到期、真实模型/PG/Linux/员工/银行/扫描及生产全部独立待测。无金融/会员/其它店额外业务，默认四开关仍关闭。
