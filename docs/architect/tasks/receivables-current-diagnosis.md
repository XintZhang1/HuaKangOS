# 应收07有限主键诊断

2026-10-01，只读诊断；没有导入 app、启动服务/浏览器/测试、重放提交或修改生产/测试入口。仅读取本轮外部 JSON/日志/镜像源码，并按 manifest 的明确外部合成库路径以 SQLite `mode=ro` 执行 schema PRAGMA；没有读取业务行、密码、附件正文或真实数据库。

## 本轮原件与状态

唯一来源为 `V/browser-click/business-receivables-20261001-07`。browser-click-report 终局 complete=true、passed=false，selected 11/11 执行、10pass/1fail。最终场景 `receivables-hk157-158-159` 54.2秒、334动作、149点击，错误 `OperationalError: no such column: id`。checkpoint complete/passed=false：HK157 passed、HK158 failed、HK159 not_tested；本页不汇入其它 run 或全193成绩。

- source SHA：`a2cd8704e5e02aa0c24a72bec269497e62554adc8284300098ae4191e8e6a9f7`。
- scripts SHA：`02c316bac9eb1903554159c9bfab92620610ff7613ae0fd7d059a1da8fcd5307`；provenance snapshot_stable=true。
- 此候选镜像与诊断时工作区均 SHA：`223db064967c25f337695efbe75590eead0a5b2c9c18ce12c16f76981445f192`。
- 外部原件：`evidence/receivables-hk157-158-159/{business-checkpoint,actions,network,observations}.json`、`230-failure.png`，以及 `evidence/{scenarios,server,initialize}.log`。

## 确定失败点

最后动作334为员工在原配车表单选择当前新VIN；之前报价独立审核 POST `/api/flow/cases/121/actions/quote_approve` 返回200，原订单/可选车 GET均200。network中本候选没有任何 allocate POST。最后业务观察为 `before_ar_sales_allocate`，其后直接 failure。

镜像 `receivables_business.py` 的确定调用链为：`sales_source:607` 构造配车 Guard → `Guard.__init__:149` 保存 before snapshot → `:150` 逐有限表读取旧行 → `rows:58` 按 TABLES 的键生成 ORDER BY。此前新采购/发运/接收已完成，失败处在 `:610` 原提交 helper调用之前。

该链的 append集合包含 `flow_vehicle_holds`，但 `TABLES:38–43` 最后通用字典将其映射为 `id`。本轮 schema `PRAGMA table_info(flow_vehicle_holds)` 确认列只有 `vehicle_id/case_id/delivered/store_id`，主键为 `vehicle_id`，无 `id`；原 `app/flow_models.py:91–96` 的 VehicleHold 也明确此主键。故候选旧行守卫执行 `ORDER BY id` 抛错，是测试适配缺口，尚未提交的配车动作不能记成功，也不能称原产品接口失败。

三份日志均没有该错误的 Traceback；scenarios原异常处理只持久化类型/消息。因此以上是动作/观察时序、真实 schema 和唯一源码调用链定位，**不是捕获到了不存在的完整异常栈**。

## 全有限映射对照

未 import helper，静态解析镜像 SF.TABLES、R.PRIMARY_KEYS、VO.TABLES/PK、MF.READ_TABLES、MAT.TABLES、BT.TABLES/原 pk、RT.TABLES 及 RCV 最后合并；共182个明确表映射。逐表只核 PRAGMA table_info；非PK映射再核 index_list/index_info 的真实唯一键，不按“不是PK”误判合法键。

| 结果 | 数量/事实 |
|---|---|
| 现存、映射列为真实PK或唯一合法键 | 180；包括 `file_security.file_id` 原唯一索引，虽该表PK为id仍为合法有限旧行键。 |
| 本次实际Guard的缺列映射 | 唯一 `flow_vehicle_holds → id`；准确主键 `vehicle_id`。 |
| 未使用的不存在表声明 | `sales_pdi_records → id`，本轮 schema为空。RCV仅映射声明出现此字面量，无任何读取/append/update引用；不能冒称182全部合法，也不将其归为本次失败或猜换其它PDI表扩守卫。 |

配车Guard其它有限表 `flow_cases/flow_tasks/vehicles/vehicle_custodies/flow_events/audit_logs/flow_request_receipts` 均有真实PK id。尤其 `vehicle_custodies.id` 及原GroupIdentity主键没有缺列问题；不能因猜测而豁免整个Identity/Custody表。

## 最小修正与边界

建议根仅在 TABLES最后合并后显式设 `flow_vehicle_holds="vehicle_id"`，供 rows/one/Guard旧行字典及 appended_ids统一使用；不改SQL执行器、原生产模型、守卫允许集合、CAS、提交次数或保留失败。未使用的sales_pdi_records声明另列待清理，不自动扩大或替换业务守卫。

checkpoint的原新车前序保留：采购120；原集团身份7/version1；发运Custody3/version2/generation0/current为空；接收Custody3/version4/generation1/current_vehicle75/store1；原身份全行保护和仅四列Custody更新的证据已存在。这些事实不能替代本次未提交配车、未签回/到账或未执行HK159。

轻量静态：本轮七个有限映射相关脚本AST解析通过；整合映射仅 schema核对，没有执行业务SELECT、app导入或复验。修正后的真实原配车/后继流程、全旧行守卫及同指纹完整联合仍待根新隔离run；此页不记新版passed。

## 根窄修独立增量审阅

根登记 `PATCH-M8-4-RECEIVABLES-HOLD-PRIMARY-KEY-01` 后，只在 TABLES字面量的合并末尾新增显式 `"flow_vehicle_holds": "vehicle_id"`。精确原字节为 `V/browser-click/launches/current-three-fixes-before-20261001/tests/browser_click/receivables_business.py`，SHA与07镜像一致 `223db064967c25f337695efbe75590eead0a5b2c9c18ce12c16f76981445f192`；新 SHA `d8b6b360fa6920c72f6bbc7ebcf5cfc807d9a87e9659e361cf8ad7e2f2c41d11`。

逐字diff仅末尾dict标点及这一显式键；反向删除这个唯一最后键后，完整 AST 与原字节解析结果完全一致。VIN/Identity/Custody/hold事实、Guard全旧行保护与动作允许范围、原提交/金额/CAS/回执没有其它变化；两版AST解析通过，未发现此增量静态阻断。没有重读SQL、运行测试或将静态修正记实测通过。
