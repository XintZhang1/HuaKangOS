# PATCH-M8-3-OWNED-PG-PROBE-01

2026-10-05。M8.2 已在 `bf08ec11abead3a0703d264d1441d98b37160d5f` 登记本次双平台完整通过，CP-35 已 released。按业主“除员工试用外继续完成”的授权，当前仅推进 M8.3，先完成真实非空旧库升级和联合恢复的一条实际路径。

## 精确范围

外部根仍为 `V=C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1`。本补丁允许：
- 新增 `V/tests/baseline/overlay/tests/m83_database_probe.py` 与 `tests/m83_owned_postgres.py`：单次登记探针及其有限 PG 进程/对象目录所有权助手。
- 将既有 `V/tests/m82-closeout/shared-contracts/m82_contract_helpers.py` 与 `original-unittest/fake_provider.py` 原字节复制为 overlay 的 `tests/m82_shared_contracts/m82_contract_helpers.py`、`tests/m82_original_unittest/fake_provider.py`。只在 M8.3 的 additions 中选择，来源 SHA 明确登记，复用实际员工 HTTP / Worker / 合成 provider，不修改原 M8.2 来源。
- `V/validation-manifest.json` 仅新增 M8.3 固定 python_script 命令、固定 `--pg-bin`、精确新增 overlay 路径和既有有限 fake-config 授权；`V/archive/baseline-restoration.json` 只追加对应来源/SHA。原 319 归档、M8.2 命令/数组/适用范围保持。
- `V/harness/isolation.py::redact` 只补本项目实际 `postgresql+psycopg://` 凭据格式，保留原 postgres/postgresql 处理；不打印随机密码、URL、环境或未脱敏异常。
- 仓库仅维护本补丁、M8.3 当前记录、architect 进度/任务及其后续验收小报告。生产代码本补丁只读；实际出现方言或完整性缺陷后另记精确所属修复。

不扩充 runner 阶段、通用环境框架或新的命令类型。复用已有 overlay_additions、python_script、fixture_runtime、command-result 和 strict 指纹合同；源文件先在新的外部 before/candidate 目录审阅，合入登记后只经原 `V/run_validation.py` 执行。

原字节 ContractRuntime 导入既有 `tests.conftest.login`，而 python_script 不会自动执行 pytest 的 autouse 初始化。本探针因此显式核 runner 新建的主合成库为空，初始化合成 Store/User/UserStore 与随机密码，再局部委托原 login 传该密码；原 HTTP 认证路径不替换。M8.3 登记 `legacy_compatibility=true` 仅容纳原测试 conftest 的导入边界，相关环境、settings 和 login 包装在退出时恢复；不重置已有库或修改生产 legacy-write 默认值。两份复制 helper 的原字节保持。

原 `private_file_backup._new_stage` 在真实备份流程内生成随机临时目录；python_script 不具有 pytest 节点的自动合成库登记。本探针只在该调用外局部包装：先委托原函数，核阶段目录的物理路径位于本 command-runtime、当前 run/command 所有权匹配且目标数据库尚不存在，再独占写该 `database.sqlite.synthetic.json` 的原 run/synthetic 标记；退出还原包装。原目录随机值、数据库连接守卫、备份算法、拒覆盖和发布 rename 均不修改。发布后的标记随目录保留并复核，仅用于测试库所有权，不作为生产备份内容或成功判据。

## 实际路径与边界

五个可信 PG 二进制使用当前独立缓存 `V/dependencies/postgresql-16.15-5/binaries/pgsql/bin` 的精确物理路径，记录各 SHA 和版本。全新 command-runtime 中建立带合成标记的 SCRAM 集群、随机密码和 loopback 端口；DDL 前核对进程、data_directory、端口及固定专用库身份。退出核对原集群停止与输入二进制未变。主 DATABASE_URL 始终为 runner 标记的外部 SQLite，PG 只作显式所有权核验后的辅助连接；Python socket 拦截本身不冒作 native libpq 隔离证明。

通过既有实际员工 API / 原 Worker / 合成响应准备旧消息、待确认卡、原业务和私有附件，按 h52j 实际列投影构建非空旧库，逐表记录原行/键/JSON/null/整数与附件事实。升级唯一 h53k 后核旧行、legacy 默认值和九张新 Runtime 空表，再调用实际完整性守卫。SQL NULL、JSON null、重复 JSON 键及原员工/门店/依赖约束保持，禁止关外键、猜填事实或把异常改成预期通过。

SQLite 联合备份及真实 PG 原生 pg_dump/pg_restore 使用各自全新目标和独立附件根，核行、序列和对象字节；不把现有 SQLite CLI 宣称为 PG 备份。PG 工具 stdout/stderr 使用每次独立文件名，报告只保安全诊断；不使用旧 main 将对象根复用为联合恢复证据。

首探针的固定收集节点和原命令结果如实留档。现有 runner 对 M8.3 的 milestone_complete 本就为 false；本次单命令 phase_complete 只表示该登记范围完整，不能代替 M8.3 四条原检查。首次探针成功后，仍需原约束/错误引用、SQLite与PG并发、双worker租约、事务发件箱竞态和联合恢复拒绝路径的完整本轮证据。

本补丁未启动公司库、已有预览、真实模型或生产服务；四个生产功能开关保持默认关闭。员工试用、人工验收和后续独立环境门槛保留。

## 首轮实际失败与夹具修正

2026-10-05，正式 strict `20261005T004325Z-890277a866` 18 项通过；首探针 `20261005T004405Z-a5a0da8c12` 实际执行 1 项、1 error、退出 1，21.25 秒自然退出，五项输入指纹与 strict 相同且全程未变。实际员工 HTTP、3 次合成 provider、SQLite h52j 投影及 h53k 升级已执行；到旧计划完整性检查失败，尚未启动 PG 或执行联合恢复。

原因是新探针自行构造的旧步骤多写了 `status='waiting'`，而原 `WorkStep(Strict)` 存储合同无此字段；等待说明应留在原 `wait_for`。仅删除探针 legacy.steps 中这一个多余键，保留原业务完整性拒绝、迁移、历史行比较和所有验收项；生产代码不修改。原失败及旧探针字节保留，修改来源登记后重新 strict 和完整首探针，不拼接成绩。合入前误跑的 `20261005T004207Z-a51176c3b5` 使用旧登记，仅保留操作历史，不作为本次新探针的 strict。

第二轮：strict `20261005T004800Z-f73271e14c` 18通过；M8.3 `20261005T004837Z-4cd69a12b0` 1执行/1error/exit1、44.407秒自然退出。五指纹与本轮strict一致且未变。SQLite升级、原完整性守卫、原联合备份和独立恢复均实际完成；PG五工具版本和指纹核对、initdb/start已执行，实际连接在DDL前被所有权比较拒绝（`owned_native_identity_mismatch`）。finally停止rc0/status3、原PID和pidfile消失，验证进程正常排空。下一步仅在该助手已有比较前补各项布尔结果及安全IP/端口/版本/时间差诊断，保持所有判断与拒绝、无凭据或原始异常输出；不猜因改规则、不预记PG迁移通过。

第三轮诊断：strict `20261005T005517Z-f138030a71` 18通过；M8.3 `20261005T005549Z-020d3ee13a` 1error/exit1、31.953秒自然退出，同五指纹稳定、PG正常停止。11项比较只有server_address为false，实际值为`127.0.0.1/32`；其余库、用户、目录、端口、时间、SCRAM、监听和版本都匹配。原因是探针用`inet::text`取得带掩码文本，却按无掩码地址比较。仅将该固定查询表达式改为`host(inet_server_addr())`，继续严格等于`127.0.0.1`，其余所有权守卫不变；不扩大允许IP或关闭核验。此语义与[PostgreSQL 16网络地址函数文档](https://www.postgresql.org/docs/16/functions-net.html)一致，原诊断证据保留。

第四轮 `20261005T010103Z-f53841ca0e`（strict `20261005T010006Z-119aa9f05e` 18通过）身份检查全部通过，PG实际开始h52j建库迁移，在n46a创建表时失败，SQLSTATE53200；45.89秒自然退出、同五指纹未变、PG正常停止。原server.log明确`out of shared memory`并提示`max_locks_per_transaction`；新集群配置原本`max_connections = 100`、锁默认64，助手却追加了`max_connections=20`。仅删除这项测试助手覆盖，使用initdb已选出的默认资源容量；保留loopback、SCRAM、随机端口、全部迁移及原单事务，不改旧迁移来绕过资源限制。[PG锁配置文档](https://www.postgresql.org/docs/16/runtime-config-locks.html)说明共享锁容量与服务进程数相关。下一次仍使用全新集群，原失败库不重用。
