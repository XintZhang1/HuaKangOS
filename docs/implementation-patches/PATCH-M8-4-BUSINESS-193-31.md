# PATCH-M8-4-BUSINESS-193-31

2026-10-01，M8.1，既定代码与真实浏览器点击授权。以 customer-reminders-scope.md SHA256 e5471d56bbec57044c92e295f05c80a914a371eb2cbe996589bf5ea21359c578 为精确合同，仅新增 tests/browser_click/customer_reminders_business.py 与 docs/architect/tasks/customer-reminders-click.md。生产、夹具、已有helper/注册/runner/目录/计划只读，不启动/注册候选。

三完整业务检查 HK105/106/112：原规则、真实本次车辆独立观察、边界生成与去重、当前本人接手/跟进/结案；maintenance更正和warranty撤销须原独立批准/不可变观察/失效与替代有限事实，first_service实际完成观察抑制后继。生成每次独立枚举本店全部有效CV/rule/observation及保险失效来源，精确计算候选集合和合法CV版本touch，禁止把0生成当全库零写或仅豁免本车。

HK099仅有意义的部分核对：原本店CV登记/编辑、真实本地非空历史、两店同集团客户和车辆身份/原有限摘要授权/明确撤销。只记录 partial 证据及待真正授权到期条件，不新增重复 HK099-business acceptance check、不改目录门槛或用撤销冒充过期。本日实际截止仍有效；不改时钟、monkeypatch、SQL造到期、等待自动化或联系客户。原原单与文件权限仍另行待测。

固定同轮客户七项与原system-management两项都完整passed，读取其有限公开IDs及外部私有账号指针；system-followon若执行也须passed且权限恢复。二店service员工必须重验当前门店岗位，实际先改初始密码再办理；不借admin办理，不新增fixture。三提醒用另一明确新VIN的本店CV，跨店摘要用实际已交付父CV，身份分别核对。只通过原可见UI提交；SQL只读、全库旧行保护、原回执/CAS/任务/材料/现金/会员分别核对。复杂未知实际副作用先报告，不能全表豁免。未运行不登记passed，人工作用评价/PG/Linux/全193及生产门槛不动。
