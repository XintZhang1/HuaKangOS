# PATCH-M8-4-BUSINESS-193-24：客户回访、问卷及其它收入七项候选

2026-10-01，当前M8.1连续浏览器交付授权内，依据customer-remaining-scope.md冻结SHA256 30dff1c913c432b11d5db1e6742447a7c9d4c76e7970a273bf4621916d9fa148。仅作者新增tests/browser_click/customer_followon_business.py与docs/architect/tasks/customer-followon-click.md，先不注册、不镜像；生产、fixture、共享helpers/runner、目录、计划及其他作者文件只读。

完整候选HK100/101/102/103/104/110/111，按原题名及HK-xxx-business合同逐项核。依赖同轮完整passed的售前/采购/主档/客户/销售交付/物资/维修有限来源，当前交付VIN与原维修VIN明确不同，不合并客户车辆。可为真实销售回访登记本次已交付VIN的原客户车辆，但HK099跨店身份、摘要与原文件授权未执行时继续partial，不因为补本地车辆宣称全项。105/106/112提醒仍下批，不在本候选提前记完成。

原其它收入新单经本版报价、另一主管复核、客户授权、实际办结、原财务账户实收；旧两收入单只读，不能重复收费。原销售/维修回访分别选对应真实已交付/完成原单，当前本店责任人接手、两次真实联系、原结果结案；原列表非空筛选、全部记录/刷新无重复与后台事实核对。意向回访使用新原接待链真实分派/意向/本人follow，不将已converted旧lead倒退。新问卷两版本真实提案/不同员工批准，原发放Binding题目和哈希不可变；必答缺失原拒绝/完整0与否及choice各实际答卷，原版本过滤、图/完整表/CSV/原钻取同范围。不得将问卷发布或回访结束冒充外部服务完成。

全部正向写仅原页面可见控件及原确认点击，SQL SELECT-only，原门店/岗位/原Case/Task/CAS/request_id/整数及独立事务守卫不变；每登录后再拍有限Guard，所有旧行与其他门店保护。问卷binding及care_history_link的合法新事实只限本批明确ID，不全表排除；附件随机凭据与完整证据外置，不借管理员代办、不扫库找可用旧业务、不重放未知结果。作者静态自审冻结SHA、根及独立短审后在关联验证退出窗口仅接注册，首次新镜像无预写成绩。原193人工/模型/PG/Linux/员工及生产门槛保留。
根注册续记：所有关联实例与setup已退出；作者c3b649bffb9919d2f0c8df5f43a84501220f931a64db65ccb592e755785ca787、文档5a8f11b6经根及独立只读短审，无确定静态误配、AST通过。按本补丁原“根审阅后仅接注册”范围仅run.py SCRIPT_FILES与scenarios.py import/BUSINESS_SCENARIOS接线，三元1200秒；同轮七父实际passed后首次点击。HK099 partial、105/106/112未测，静态不作七项passed。
