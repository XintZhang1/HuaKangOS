# PATCH-M8-1-QUESTIONNAIRE-EXPORT-WRITER-01

2026-10-01，M8.1 同一实施项，三个当前a2cd8704/02c316ba运行均完整失败且自然收尾，已确认相关Python与64950–64952监听不存在，编辑窗口开启。finance08为15/17、应收07为10/11、报表06为5/6；失败原件全部保留。

finance08首个真实失败是HK101第二个原问卷CSV，动作406 GET /api/customer-service/questionnaires/export/questionnaire_answers返回503 application/json；第一issued CSV已200并追加唯一审计。问卷原题目、实际回答和前序保留。原questionnaire_export的get_db先读身份及统计，307行实际audit+commit，却未使用审计读写依赖；本GET不在已登记127同步POST/PUT业务写清单，不能宣称上个补丁已覆盖它。

只修改app/customer_service_api.py：导入既有get_audited_read_db，唯一questionnaire_export的db默认依赖改该alias，保持db先get_user；原report、其它GET、函数体、过滤/期间/题目/原答案/CSV转义、审计/commit、岗位及同店范围均不变。沿app/db.py当前请求级SQLite OptionEngine在认证前预留短审计事务；普通读/Worker/PG保持，不重试下载或制造业务写入。

另仅tests/browser_click/customer_followon_business.py的questionnaire_csv失败诊断顺序：在expect_download作用域内先等待真实response，记录脱敏HTTP/Content-Type/同源Cookie存在性和实际key，再严格核200+CSV；异常即退出并取消不存在的download等待，不让15秒下载timeout掩盖503。成功下载、原字节/BOM/完整范围行/筛选参数/单条本人本店审计与全旧行Guard不变，超时不延长、非200不通过。

精确增量源码审阅及AST后从全新外部镜像重办受影响财务父闭包；应收字段映射及报表原款断言另精确补丁实施后各自重办，再同当前指纹全53单次联合。未观察193体验/真实Date、独立环境/模型/员工/生产门槛和四默认关闭开关保持。
