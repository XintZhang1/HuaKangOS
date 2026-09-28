# PATCH-CP-00B-05：完整基线的测试合同与隔离适配

状态：补丁范围已审阅，候选正在合并，尚未应用或复验。旧完整 B `20260927T140257Z-053b24940f` 已自然结束，退出 1；41 命令全部终结，3042 passed / 36 failed / 1 skipped，无缺项或输入漂移。终态和各修补方案已独立审阅；见 CP-00B-v3。通过本补丁的静态审阅不等于通过测试或放行检查点。

适用项：M0.2.B / CP-00B，依据用户 R3 连续实施授权及计划 A3.2/B2/B4。不是新里程碑，不改变 108 项顺序、产品架构、原业务规则或发布门槛。CP-00B 保持 changes_requested。

## 目标与已观察问题

1. 修正流程帮助四个、岗位/前序事实四个旧测试合同，按已批准的当前 R4 行为验收。分类是相关性提示；角色权限、真实事实和人工确认约束仍须保留。
2. 让原迁移回环、两个 CLI 拒绝节点、两个预览 prepare 节点真正执行产品代码。当前失败来自测试库标记或有限环境语义未登记，不能接受守卫拒绝来代替产品拒绝。
3. 允许已标记合成库的规范只读 URI：原预览三个节点与原完整备份恢复节点使用同一种安全只读调用。复用原路径及 marker 校验，不改变产品存储代码。
4. 修正 browser 存储隔离节点的外部 bootstrap，使其新临时库落在本命令 fixtures 中；保留上传、数据库存储、PrivateFileObject 为零及外部 sentinel 原字节断言。
5. 为计划已允许的单独诊断提供有限统一入口，并确保任何诊断不能被计作完整 B。
6. 修正车辆运输 18 个参数化完整性用例被节点字符白名单拦住的问题：用真实 reporter 活跃节点身份登记，保留完整参数文本和原业务断言。

Windows 文件/目录符号链接权限是独立外部条件；原节点已实际 skipped。不能删掉、跳过后记绿，不能用 hardlink/junction 替换其产品断言。

## 允许修改（完成最终审阅后才应用）

V 固定为 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1`。

- `V/harness/isolation.py`：规范只读 URI 纯解析；五个精确子进程 profile 接入；只有 fresh preview 的 DB 检查延迟到全部非 DB/config 检查之后；通用 fixture 登记使用冻结命令及 reporter 节点身份，保留原路径/marker 边界。
- `V/harness/selftest.py`：只补齐原 fixture 登记自检的独立合成命令/节点 metadata，原 18 自检节点和拒绝断言保留，禁止改写正式 run metadata。
- `V/harness/runtime_guard.py`：真实 SQLite 调用参数包装、一次审计许可及重复安装保护；原网络/Node/来源守卫保留。
- 新增 `V/harness/fixture_profiles.py`：固定五节点的合成 provenance，不创建数据库或产品文件，不泛化为任意子进程授权。
- `V/run_validation.py`、新增 `V/harness/diagnostic.py`：精确诊断选择、前置完整 collect、独立结果和选择指纹；command contract 的五节点 fixture_profiles 映射。
- `V/harness/verdict.py`、`V/harness/baseline_aggregate.py`：诊断精确集合验证和拒绝冒充 full 的双重门禁。
- `V/tests/baseline/overlay/tests/conftest.py`：原已验证 DB 路径不再被强制改 basename；journal_mode 使用同一路径；仅已登记五节点的 autouse provenance。
- `V/tests/baseline/overlay/tests/test_business_assistant_guides.py`、`test_business_assistant_scope.py`：各四个已列原节点及必要局部数据/注释。
- `V/tests/baseline/overlay/tests/test_test_storage_isolation.py`：仅新合成 browser bootstrap，原两个节点及全部产品断言保留。必要的最小私有 helper 不得成为产品 API。
- 新增外部纯合同 `test_m02_fixture_profiles_contract.py`、`test_m02_sqlite_uri_contract.py`、`test_m02_diagnostic_contract.py`、`test_m02_storage_bootstrap_contract.py`、`test_m02_fixture_registration_contract.py`。不得从目标原节点删断言来提高新合同通过率。
- `V/tests/baseline/overlay/tests/test_m02_baseline_aggregate.py`：仅 `_phase_record` fixture 补齐 full 的 run_mode、registered_selection、selection、result command_id，原 7 个相关参数节点和全部断言保留；storage 新纯合同按真实 active_node 断言身份。
- `V/validation-manifest.json`、`V/archive/baseline-restoration.json` 和限定登记辅助程序：登记真实新增节点/输入哈希、来源和完整差异，原件 319 文件和原 2124 节点必须保留。
- 仓库仅更新本补丁、CP-00B 本轮报告、implementation_plan.md 当前 M0.2 记录/CP 行。全量日志、差异和合成数据仍留 V。

## 禁止修改

所有生产 app/web/migrations、旧原件与历史 run、E: 旧验证根、total_plan.md、原业务权限/状态机/确认接口及生产配置。本补丁不扩大 synthetic 三态到产品，不引入真实模型或生产数据，不更改 Windows 系统设置，不创建新 Runtime 或开始 M0.3。

## 五个精确子进程 profile

完整 node ID 以 `fixture-profiles-independent-review.json`、`cli-negative-configuration-triage.json` 和最终 manifest 为准，包含 CLI 的原 literal `\\u` 参数文本，不能改名、按前缀或关键词授权。

- 迁移节点：保持 `l248_business_entities → k137_user_access → l248_business_entities`、16 张主体表、原版本与外键断言。仅在尚不存在的固定 `entity-migration.sqlite` 旁登记 sidecar；实际子进程参数仍是原 Alembic 命令。
- 两个 CLI 节点：保持原 local/quarantine、production/clamav 环境对与 `python -m app.cli init --demo`。仅 marker 可存在，目标 DB 不得预建；检查真实产品拒绝文案、非零退出和 DB 仍不存在，86/守卫错误不是成功。
- 两个 preview 节点：父测试只登记 tmp_path；不得预建 fresh/旧目录。sitecustomize 初始环境仍为原 main DB + test；产品 configure 后，仅精确 fresh prepare 可使用 local。产品已自行 mkdir 并独占写完 preview.json 后，全部非 DB/config 校验成功，才独占创建 synthetic sidecar，再执行原 db_path。旧目录不补写、不接管；重复校验不重写 marker，DB 已存在而 marker 丢失时拒绝。

profile 必须绑定当前 run、冻结 command、reporter 活跃完整 node、真实解释器、完整 sys.orig_argv、镜像 cwd 和该节点 tmp_path。错误/失效身份、其它命令、额外参数、错路径/链接、已有未标记库、错 marker/config 或不安全环境均拒绝；不得给通用 APP_ENV=local/production 权限。

2026-09-28 第二轮诊断确认五个原节点均被 Windows venv redirector 的原始程序路径误拒。仅在既有 fixture_profiles.py 和其新增纯合同内兼容：实际 sys.executable 与 sys.prefix 必须属于固定 V/.venv，原完整参数和 cwd 不变；Windows 的 orig_argv[0] 额外只允许解释器自身非空绝对 _base_executable，且其规范父目录等于非空绝对 sys.base_prefix、文件名为 python.exe。不接受相对路径、任意系统 Python 或从 PATH/环境取替代值，不读取 pyvenv.cfg，不改产品测试。合成 child_identity 补齐 prefix，原 46 节点保留，增加必要正反例并按实际收集登记。该局部修复先验证全部 profile 合同和原五个子进程节点；完整 B 仍必须以最终指纹执行全部 41 命令，不复用旧诊断的通过片段。

## 只读 URI 与 browser bootstrap

URI 恰为规范本机绝对 `Path.as_uri() + '?mode=ro'`，目标已存在且通过原 db_path。只接受原实际 `uri=True` 调用形状；wrapper 发放一次线程局部许可，audit 先消费再重验身份和目标，finally 撤销。直接 native connect、uri=False/省略、其它参数、UNC/host/query/fragment、未标记库和链接路径均拒绝。不按 registered_for 限制普通读取；不能增加 marker 绝对路径字段而破坏备份整目录发布。

browser bootstrap 继续调用原 browser_environment。新目录位于当前命令 pytest 临时树，必须为空；helper 返回 URL 必须指向该目录固定新库，DB/sidecar 均不存在，再调用既有登记 helper。保留 conftest 已验证的实际 DB 目标，不给 browser 另开 `-c`、环境或网络例外。

## 通用 fixture 登记的节点身份

原 18 个运输失败均为 damaged.sqlite 首次连接时登记拒绝，尚未执行损坏 SQL 和完整性断言。禁止改原车辆测试/SQL、sanitize 或重命名参数，禁止为这些节点再造业务白名单。

登记函数只接受当前 hash-bound baseline_pytest 命令及 reporter active_node，函数 run 必须等于合同环境 run；pytest 临时根必须位于同一 run/fixtures 内。完整节点文本仅写 JSON 值，不用于文件路径、命令或 SQL，不再用字符白名单或 split 空格截断。缺失/错误/失效身份时拒绝，不退回 PYTEST_CURRENT_TEST。原链接、越界、匿名内存、当前 marker 复用及错 run marker 拒绝语义保持。

原 strict 自检只在自身合成目录里建立必要的冻结合同与 reporter metadata，结束恢复环境，不改正式运行记录。新增纯合同验证带引号/空格/SQL/中文/长参数的完整身份，以及伪造环境身份、错误 run/command/node、路径与 marker 拒绝。

## 诊断状态与异常路径

仅 M0.2/B 可接受原 command ID 或原 command ID=精确 node；完整注册仍为 41 命令。每次新 run 前置原完整 collect，所选节点必须属于同次 collection 和原命令文件组。文件路径与参数文本分开处理，不把参数 ID 中的空格、斜杠、等号当作路径或命令。

重复、混选整命令与其节点、错组、glob/前缀、任意选项、只 collect、未登记脚本及 A/strict 诊断均拒绝。命令/节点/config 许可取交集，不借同组未选节点。只有诊断副本的 minimum 可取所选数量，并要求 collected 与终态集合精确相等。原注册、full minimum、timeout、脚本参数不变。

`diagnostic_passed/diagnostic_failed` 的 phase_complete 和 milestone_complete 永远为 false。结果与 latest-diagnostic 指针独立，不能覆盖 baseline/latest-run。即使诊断全选且全绿，也不能复用为完整 B。phase verdict 与 aggregate 分别拒绝这类冒用。无诊断参数时继续原 full 路径，并核对全部注册选择。

2026-09-28 首轮正式诊断发现 Windows 环境变量长度限制：643 节点的 expected/unregistered 清单重复写入子进程环境，测试恢复环境时超出 32767 UTF-16 单元并造成后续身份错误。仍在上述 runner/新增诊断合同允许范围内修正：完整列表保留在 hash-bound diagnostic-selection 及 command，继续用于逐节点集合核验；子进程权限合同只保留列表的数量、规范摘要与原 selection 哈希，fake-config/profile 仍取精确交集。完整 full 路径不变；环境传递增加长度拒绝保护，禁止截断、省略节点或扩大权限，也不引入新的环境引用协议。补充大清单及 ASCII/非 BMP 长度边界回归，真实收集后更新原 b01 数量与现有 addition 指纹，保留本轮失败。

## 验收与推进

- [x] 当前旧 run 已真实结束，退出码、全部结果、进程收尾及前后指纹已记录。
- [x] 最终合并差异通过独立审阅；不同 staging 的 isolation/runner 改动按限定 hunk 合并，未互相覆盖。新 URI 纯夹具补齐 reporter 身份后重新冻结并复审，18 文件已按哈希应用。
- [x] 319 原件不变，2124 原节点精确保留；所有新纯合同按实际收集登记，原测试断言和来源差异可追溯。
- [x] 新 profile/URI/诊断/storage 的正反合同通过，非法身份、路径、参数、环境及异常清理符合边界。
- [x] 新 strict 与诊断绑定同一组输入；原失败节点实际执行产品并关闭。原安全解析器与 PATCH-04 的 27 项覆盖保留。
- [x] 新 full B 完整执行全部 41 命令；无缺报告、缺项、隐藏失败或通过片段拼接；全部前后指纹和依赖一致。
- [ ] 原符号链接节点真实执行且通过，未把 skipped 当 passed；如系统条件仍缺，明确保留阻塞。
- [ ] CP-00B 只有满足原计划条件才可放行；之后仍按 108 项顺序逐项实施。

2026-09-28 终态回填：完整 B `20260927T163618Z-574f417642` 全部 41 命令执行，3336 passed / 0 failed / 1 skipped；原 36 失败全部关闭。原符号链接测试仍 skipped，因此 M0.2 blocked、CP-00B changes_requested，详见 CP-00B-v5。以上勾选表示相应证据条件成立，不表示整份补丁或完整基线验收通过；旧报告和冻结指纹保留。
