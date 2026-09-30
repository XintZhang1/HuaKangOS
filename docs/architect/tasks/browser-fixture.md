# 任务：外部隔离浏览器入口与合成服务

**任务 id 与负责人**：browser-fixture；子代理 test_inventory，向 browser-click 负责人报告。

**目标与交付结果**：删除旧套件前完成可替换的新隔离入口和 CI，提供真实 HTTP 服务供自动实际点击与交互审阅共同使用。

**架构依据与决定**：依据 PATCH-M8-4-BROWSER-CLICK-01 和当前实际代码。生产 API、登录 Cookie/CSRF/CSP/SSE、原业务事务和 Worker 保持真实；只模拟模型协议回复。所有源镜像、凭据、数据库和证据外置，Windows 强制 NTFS，不提供页面桥接模式。

**代码快照与影响范围**：接手 HEAD 7127603。只拥有 tests/browser_click/run.py、fixture_server.py、provider.py、README.md、.github/workflows/browser-click-checks.yml 与本记录；scenarios.py/rubric.json 由点击场景子代理负责。旧套件删除和计划更新由负责人完成。

**已完成与当前位置**：只读盘点确认旧测试 39 个 tracked 文件、旧 CI 1 个、scripts 旧回归检查 2 个；业务帮助生成与历史报告需保留。新入口落盘：白名单镜像、环境隔离、外网 DNS/socket 守卫、随机账号密码、真实 lead seed、动态模型回复、真实 Web/worker、优雅停止信号与外部证据。默认执行外部 scenarios CLI，--serve 可交互审阅；新 CI 仅运行同一实际点击入口。新增销售本人客户及原 group_service 创建的会员读取样例；查询文字只用真实原工具返回的 label。自动判定核对预期/实际场景集合、重复 ID、逐项 passed 与原模型外网请求为零。来源记录同时保留 Git HEAD、工作树文件名及完整双指纹。

**当前收口**：负责人已完成 automatic-20260930-07 的13组原生联合点击，结果及证据见末尾追加记录；本任务不再等待联合启动。

**接续修订**：初始化 app 前比较源码和脚本复制前、复制内容、复制后三份逐文件指纹；并行改动导致任一不一致时写 snapshot_stable=false 并拒绝启动。--serve 收到 runtime/stop-requested 后成功关闭记录 stopped=true、exit 0，complete/passed 仍为 false；无请求退出或非零退出仍失败。

**监听预检修复**：automatic-20260930-02 合成初始化成功，但 uvicorn 在 Windows 重绑 127.0.0.1:59498 时返回 Errno 13；未执行场景，原失败保留。端口预检由 bind-only 改为 SO_REUSEADDR + bind + listen 后关闭，不增加自动换端口或重试。独立一次 socket 探针在 53173 端口完成 listen → close → 同选项 rebind/listen；run.py AST 通过，未导入 app。此探针不代表 uvicorn 或浏览器通过，由负责人在 fresh03 复跑真实入口。

**场景日志收口（历史阶段）**：负责人完成 fresh03（8/9，服务已停），要求保留 Playwright 内部 Task 警告原件。run.py 仅将 scenarios 子进程 stdout/stderr 合并写入该次外部 evidence/scenarios.log，不新增 tee 或日志平台、不改场景判定；当时尚未以此修订重新运行 app，后续已纳入07轮完整联合复验。

**初版静态验证（历史阶段）**：run.py、fixture_server.py、provider.py 通过 Python 3.11 AST 语法检查；git diff --check 无 whitespace 错误。审阅 cli/flow_seed 确认不打印密码，原 gateway 内部使用 localhost，不放宽 Host。当时子代理未导入 app、启动服务或运行联合测试，后续负责人已完成07轮实际点击。历史静态结果不替代该轮证据。

**代表表单前置阶段（历史）**：依据 PATCH-M8-4-REQUIREMENTS-CLICK-01 的追加登记，当时先只读核对已停止的 automatic-20260930-05 manifest 与其外部合成库，以及原 seed/flow_seed/master_data。车辆采购需要启用的 typed 供应商和车型，物资采购需要启用的 typed 供应商和物资。仅缺少时在本夹具初始化中调用原主数据 schema/service 创建最小合成资料；不改旧外部实例，不直接 SQL 构造关系或订单，当时暂不启动联合测试。

**前置核验与修订结果（历史阶段）**：05 的 manifest 指向该外部实例 `runtime/synthetic.sqlite`。只读计数为 typed 供应商0、typed车型0、启用物资8（两店各4）；读前后数据库 SHA256 均为 `2b951520f0fa592f13f660e1ef19f486c1e1243b286130a2dbe7193e2be76080`。原 seed/flow_seed 的供应商和车型为旧文本/Reference，故新初始化在 `set_scope` 后以原 admin 身份经 `SupplierInput`、`VehicleModelInput` 和 `save_master` 各补1条本店合成主档，保留原审计、版本、权限与幂等；复用本店既有物资，不新增物资、库存或采购订单。新增 `domain_samples.form_prerequisites` 记录本店与三项真实 ID，以及初始化实际读取的 `existing_active_item_count`。本修订 AST 和 whitespace 检查通过；fixture SHA256 `695a28c9b32f924747be9493e1d9f39659f5e0b6dd40f96d7bef9e6b2dbacec3`。当时未运行初始化或浏览器；07轮已使用该前置完成原表单点击复验。

**最终集成复验（2026-09-30）**：已只读核对仓库外 `runtime-v1/browser-click/automatic-20260930-07/` 的 `evidence/run-summary.json`、`browser-click-report.json`、`provenance.json`、`provider.json`、需求覆盖与代表表单 checkpoint，以及该轮 manifest。自动入口 `complete=true`、`passed=true`、`scenario_exit_code=0`；预期、注册、执行及通过均13组，失败0。`native_transport=true`，使用显式本机 Chrome、Playwright 1.56.0和Python 3.11.4。17次合成模型请求，真实模型调用0、阻止外网尝试0。源码与脚本复制前后指纹一致，`snapshot_stable=true`：生产源码 SHA256 `0ade3e7a781de93a963bc341242488abf386ee7d68bed55178838cc815e22f7a`，脚本 SHA256 `e4265ebdc23ce75c2d1767e272da5bc37167221f380d0c14d4857735eacff921`。

该轮实际完成193项搜索、111篇指引、70个去重原页面和9个原空表单打开/聚焦/取消；原页面与空表单 checkpoint 均记录 `original_business_unchanged=true`。manifest 的本店供应商、车型、物资 ID 均1，实际既有启用物资计数4。SQLite退出事务机制另有 `auth-logout-probe-20260930/report.json` 两组通过原件，07轮慢查询退出场景也通过；两类证据各自保留，不拼接冒充一次测试。

本结果是本次合成数据、真实HTTP与原生浏览器自动检查通过。报告仍将人工统一评价列为 pending、员工效率未测；四个页面的来源不完整提示保留，193项业务验收、完整状态机、真实模型、PostgreSQL、员工试用及生产门槛没有据此通过。旧失败、探针和源码候选记录不覆盖。

**随后主代理人工审阅结果（独立证据）**：manual02与automatic07生产/脚本指纹完全相同，实际IAB销售登录、三宽度、手机准备客户→单次确认→刷新→原客户页→退出已执行，数据库对应客户恰一条。六项人工评分3/3/3/4/3/3，详见 `V/browser-click/manual-20260930-02/evidence/manual-review.json` 和v2浏览器检查点；自动报告自身的pending保持当时事实，不改写原件。开发者审阅不替代员工试用或效率。
