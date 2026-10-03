# PATCH-M8-1-DAY-BOUNDARY-CLOSEOUT-01

2026-10-03 窄接线追加：`tests/browser_click/day_boundary_entry.py` 自有阶段服务复用原 `fixture_server.read_instance` 与 `configure_environment(initialize=False)`、原 app lifespan/uvicorn/合成网络守卫；仅原 UI Date/流水合同，0 Runtime worker 与0报表定时作业前中后据真实 app 状态核实，不当作 worker 部署验收。入口及业务模块纳入原 `run.py` 精确60镜像脚本，普通SCENARIOS仍80，不在同日全量中伪造跨日通过。所有旧full证据/runtime配置逐文件哈希及旧Run/worker行指纹保持；独立phase stop/control/provider/lifecycle和证据目录，原DB仅原UI合法业务提交，不初始化或迁移。root已独立审阅代码、原app/scheduler/lifespan及Evidence/stop语义，静态AST/差异检查；stage/verify尚未执行。

2026-10-03，M8.1 自然日期条件的隔离候选；尚未执行。业主要求除员工试用外完成其余门槛，本补丁不改变原业务日期、权限或验收口径。

允许新增 `tests/browser_click/day_boundary_business.py` 及本记录和本任务记录。生产文件、共享 helper、正式实施计划、`run.py` 和 `scenarios.py` 由主任务持有，本候选不修改。

两个独立原合同不能由 Runtime 的 30 分钟卡片过期替代：

- HK099 服务摘要授权的 `valid_until` 是 Shanghai `Date`，D 当天仍有效，D+1 原 GET 应排除外部摘要。数据库授权整行保留 `active`，列表显示“已过期”。原 `customer_reminders_business.share_partial` 已撤销旧授权，候选必须在原 UI 重新登记 D 截止的新授权，不复活旧行。
- HK152 库位历史从唯一真实 `warehouse_approve` FlowEvent 时刻开始。开始日严格晚于实际启用日时，原 OpeningStock、StockMove 和 WarehouseEntry 可重建完整期初及期间；开始日为启用日仍须显示未知期初。没有午夜定时生成期初的作业要求，正常停服务保留库即可等待真实日界。

候选复用原浏览器 `Evidence`、当前原表单 helper 和 SELECT-only `Database`，没有新建测试框架、数据库直写、时钟替换、HTTP 写入桥接或真实模型调用。

`day_boundary_stage(e, context, credentials)` 的固定来源为同轮已通过的客户后继、系统员工、提醒、主档、车辆采购和物资检查点。它通过原 UI 新建 D 截止授权并读取真实非空摘要；在本店明确原库位新建零库存物资，原申请/主管批准真实启用，再原其他入库 5.000 包、20.00 元。对 D 当日原 API 验证期初未知、有据期末非零，封存 `evidence/day-boundary-original-ui-stage/day-boundary-stage.json`。封存不代表跨日通过，stage 检查点保留 `complete=false/passed=false` 和 `waiting_real_shanghai_d_plus_one`。

`day_boundary_verify(e, context, credentials)` 仅允许 D+1、同一个外部 manifest、同一 origin、数据库、凭据来源、source/scripts 镜像及原套件证据指纹。先逐表核对 stage 的原业务全行摘要和授权、批准/启用/位置/流水原件；本人原登录读取摘要排除外部记录，原授权列表显示过期但物理整行不变。原仓库报表先从 D 历史流水重建非零期初 5.000/20.00，再原 UI 实际入库 1.000/4.00、领用 0.500/2.00、引用本次原领用退回 0.125/0.50。D+1 期间应为入库 1.125/4.50、出库 0.500/-2.00、期末 5.625/22.50。逐条原库存/库位流水、当前余额、原单、全部表行、图表和 CSV 精确同范围；D..D+1 原期间仍未知期初，不能用后日完整覆盖启用当日缺口。

导出接口及主任务接线要求：

- `STAGE`、`VERIFY` 两个固定场景名；`DAY_BOUNDARY_STAGE_SCENARIOS` 和 `DAY_BOUNDARY_VERIFY_SCENARIOS` 各自一个 1200 秒场景，不能一起加入普通同日全量注册表。
- `resume_checkpoint(manifest)` 是重启前只读预检，不初始化、不导入 app、不读模型密钥。只有实际 D+1 才返回固定 stage 引用。
- 将候选纳入正式 `SCRIPT_FILES` 可使日常 full 在无跨日等待的情况下保存固定脚本。自然跨日阶段需要正式入口明确 resume 原实例；复用原启动、关闭和浏览器生命周期，禁止 `--initialize`、重新迁移/造夹具、重新镜像当前仓库、换库或覆盖原 `browser-click-report.json`。
- phase 报告写独立目录及独立聚合报告；保留原 full 报告和 stage 原件不改。业务条件检查点是 `technical_subrange_passed`，不替代 HK099 原单/逐件附件授权、HK152 其余完整业务合同、193 项业务验收或员工试用。

静态审阅发现的真实接线缺口：实际 `warehouse_service.PURPOSES` 使用 `wh_consume_return`、`wh_other_return`，而仓库期间 `REASONS` 原未登记这两个原动作名称。主任务另按 `PATCH-M8-1-WAREHOUSE-RETURN-LABEL-01` 追加真实动作 label，保留历史 keys；本候选严格核对真实 `wh_consume_return` 为“耗材原单退回”，不降级为通用 fallback 求绿。

审阅范围包括：全部数据库调用为 SELECT，所有业务写入走原可见表单；原角色和任务必要交接用既有本人原接口；使用真实本机上海日期/UTC 原事件；密码仅在外部合成 runtime 文件和当前内存，证据只保留凭据路径/指纹，不含密码或 API key；stage/verify 各异常保留独立失败检查点，不将日期未到、缺 parent、源码变化、超时或非零退出记为 passed。当前仅 AST 静态检查，未启动服务、浏览器或测试，未发生真实跨日实测。
