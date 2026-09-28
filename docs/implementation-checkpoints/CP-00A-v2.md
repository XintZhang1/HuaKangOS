# CP-00A 审阅报告 v2

本版依据 `PATCH-CP-00A-01`（执行授权：用户指令“执行 PATCH-CP-00A-01，复测后提交 CP-00A-v2，仍停在 CP-00A，不进入下一批”）重做 P1—P4 并复测。**v1 原文保留在 `docs/implementation-checkpoints/CP-00A-v1.md`，不覆盖**；v1 中不准确的指纹/计数/判定说明在本版逐条纠正。仍停 CP-00A，未运行 M0.2.B 或 M0.3。

- 日期/执行者：2026-09-27 / DeepSeek
- 计划版本：`R2-20260927`（补丁声明依据 `R2.1-20260927`；本仓库实施计划文件版本行仍为 `R2-20260927`，未见计划正文修订，按实际文件登记）
- 仓库绝对路径/HEAD/未提交改动摘要：`C:\Users\tiefu\.codex\worktrees\edb5\HuaKangOS` / `f735de2d74f5eb37f13addc1353e6a8e435a01c4` / `M AGENTS.md`、`M app/business_assistant_service.py`、`?? docs/implementation-checkpoints/`、`?? docs/implementation-patches/` 及接手前既有未跟踪文档
- 本批授权依据：用户本轮指令与 `docs/implementation-patches/PATCH-CP-00A-01.md`；执行前逐项核对补丁第 7 行审阅指纹**全部一致**（见下）
- 覆盖范围：M0.2.A 内部修补（P1 判定、P2 配置合同、P3 文案回归、P4 冻结与报告）
- milestone 状态：in_progress
- gate_state：awaiting_review
- 报告类型：正常到点
- 另行放行下一批：否

## 0. 审阅指纹核对（执行前）

| 对象 | 补丁/审阅声明 | 实测 | 结论 |
|---|---|---|---|
| `app/business_assistant_service.py` | `068ce43da1ed00ece9c71fa370c0514d7a88bdfc4a522e8da129a1aae9f0bd1b` | 同 | 一致 |
| `V/run_validation.py` | `19be0296f65306d30bb2ac2376b3e5a8201c69bcc0430b053dcf2168f04322c2` | 同 | 一致 |
| `V/harness/isolation.py` | `d2f19da053f7eef3debe13ceafba69bf76ad9e8b450a4870e4fe8b54505b5daf` | 同 | 一致 |
| `V/validation-manifest.json` | 当前 `464fa83d933081054c09afdeaa9c5c1f8ce7252a3c8286a245ebe58acf25df5c`（run 内为 `c8d61db4…`，即审阅记录的漂移项） | 同 | 一致 |

`V/review/CP-00A/review-state.json` 与 reviewer 的 5 个判定探针（`V/review/CP-00A/runner-verdict-probe/`）已作为本轮负例的验收目标使用：**v1 判定在这 5 例上 4 错**（collect-only 误判 fail、部分清单误判 pass、仅 setup 误判 pass、skip 误判 pass、timeout 误判 pass），v2 全部按 reviewer 的 expectation 判定。

## 1. 改动与范围

| 文件/函数 | 改动目的 | 允许条款 | 证据 |
|---|---|---|---|
| `app/business_assistant_service.py`：`CLAIM_*` 常量、`unquoted`、`clause_is_affirmative`、`claimed_actions` | P3：修 8 处文案回归；“实际/真实/确实/真的”不再单独作为完成标记；按分句分段判定，引用/解释/疑问只否定其自身部分 | 补丁 P3·允许修改第 1 行 | 生产源码指纹见第 4 节；`V/checkpoints/CP-00A/v4/command-verdicts.json` 中 a1=36/36 |
| `V/harness/verdict.py`（新增，纯判定） | P1：collect 与 execute 分开判定；逐 nodeid 生命周期；重复/额外节点/未完成/跳过/超时/身份不符/缺字段全部拒绝 | 补丁 P1、允许修改第 2 行（必要纯 helper） | `V/checkpoints/CP-00A/v4/verdict.py` |
| `V/run_validation.py` | P1：分阶段注册（A/B 映射、缺失即拒绝）、按命令冻结配置合同、严格自检绑定（`bindable_fingerprint`）、`inputs_unchanged` 与依赖一致性参与 `phase_complete`；删除 manifest 通过状态与人为 `milestone_complete` | 补丁 P1、P4 | `V/checkpoints/CP-00A/v4/run_validation.py` |
| `V/harness/isolation.py` | P2：`command_contract` / `active_node` / `node_contract` / `check_test_config` 精确到“本命令 + 当前节点”的假 key/model；删除整个 M0.2 的布尔例外与 `HUAKANGOS_FAKE_CONFIG` 名单 | 补丁 P2、允许修改第 3 行 | `V/checkpoints/CP-00A/v4/isolation.py` |
| `V/harness/baseline_results.py` | P1：collect-only 写 `pytest-collection.json`、执行写 `pytest-results.json`，附 `command_id/run_id/source`；节点上下文由插件 setup/teardown 维护 | 补丁 P1、允许修改第 5 行 | `V/checkpoints/CP-00A/v4/baseline_results.py` |
| `V/harness/selftest.py` | P2：新增“按命令+节点授予配置”与“未登记命令/节点/伪造选择被拒”用例（原 17 项保留） | 补丁 P2 第 7 条 | `V/checkpoints/CP-00A/v4/selftest.py`（18 项） |
| `V/tests/baseline/overlay/tests/test_m02_claim_contract.py` | P3：正式回归纳入 27 条句式表 + 行为轮数/零写入用例 | 补丁 P3 第 5、6 条 | `V/checkpoints/CP-00A/v4/test_m02_claim_contract.py` |
| `V/tests/baseline/overlay/tests/test_m02_harness_contract.py` | P1/P2/P4：判定负例矩阵、注册与配置合同、严格绑定与漂移、`phase_complete` 聚合负例 | 补丁 P1 第 2—6 条、P2 第 7 条 | `V/checkpoints/CP-00A/v4/test_m02_harness_contract.py` |
| `V/tests/baseline/overlay/tests/m02_runner_adapter.py` | P1：逐 node 记录 id/outcome/skip 原因，报告绑定 command/run | 补丁 P1 第 3 条 | `V/checkpoints/CP-00A/v4/m02_runner_adapter.py` |
| `V/harness/m02_claim_phrases.py`（新增） | P3：句式表以 ASCII 转义保存，避免编辑/工具链编码损坏（本轮实际遇到该风险，见第 6 节） | 允许修改第 7 行 | `V/checkpoints/CP-00A/v4/m02_claim_phrases.py` |
| `V/validation-manifest.json` | P1/P2/P4：只放静态注册（阶段映射、命令、最小项数、按 command/node 的配置合同）；删除 `phase_complete` 结果值与 `milestone_complete` 开关；新增 `strict_reference` | 补丁 P1 第 6、8 条 | `V/checkpoints/CP-00A/v4/validation-manifest-current.json` 与 run 内副本 `validation-manifest-run-copy.json`（本轮两者相同，无事后写回） |
| `V/archive/baseline-restoration.json`、`V/tests/baseline/applicability.json` | P4：同步 4 个 overlay 新增/更新测试的来源哈希 | 允许修改第 12 行 | 见 `inputs-freeze` 与 `command-verdicts.json` |
| `V/checkpoints/CP-00A/v4/`、`docs/implementation-checkpoints/CP-00A-v2.md`、计划当前项/验收 | P4 报告与回填 | 允许修改第 13、15 行 | 本文件与计划片段 |

未跟踪文件/外部变化清单：仓库内新增 `docs/implementation-checkpoints/`、`docs/implementation-patches/`（均为文档）；V 内新增 `harness/verdict.py`、`harness/m02_claim_phrases.py`、`checkpoints/CP-00A/v4/`，并刷新 overlay 4 个测试与恢复记录哈希。旧的 v1—v3 冻结与旧 run 均保留未改。

## 2. 逐项处置（P1—P4）

**P1 判定**
1. `baseline_collect` 只读本命令目录的收集报告（`pytest-collection.json`；仅当同级执行报告确实“有清单无调用结果”时才接受），要求非空、无重复、零 collection error、报告 exit 为 0 或缺失；收集不要求 call 记录，也不再算执行通过。`baseline_pytest` 只读 `pytest-results.json`，**删除跨命令兜底**（无共享 `reports/` 读取、无 `collect_evidence`）。
2. 逐 nodeid 核对：结果中不得出现未收集节点；同一 node 的同一 phase 不得重复；终态集合必须等于 collected 集合；通过必须 setup/call/teardown 全部 passed；任一 phase 失败即失败（即使进程 exit=0）；报告 exit 与进程 exit 必须一致（不一致单独记为 `reported_exit_nonzero`）。
3. skip/xfail/xpass 单独记录并一律拒绝（本批要求零 skip）；unittest 报告含逐 node 的 id/outcome/原因，节点证据条数必须等于 `tests_run`。
4. `timed_out=true` 立即拒绝，与进程是否恰好返回 0、报告是否 successful 无关。
5. 报告缺字段给明确 `report_schema_incomplete:<字段>`；报告必须匹配本 command_id 与 run（`source`/`run_id`/`command_id` 不一致即 `report_identity_mismatch`）。
6. 分阶段注册：`registration_complete` 为 `{A: true, B: false}` 映射，未声明即拒绝（`phase_not_registered`）；manifest 不再保存通过状态。
7. M0.2.A 通过只产出 `phase_complete=true`，`milestone_complete` 恒为 false；B 未注册不得产出完整基线通过（本轮未实现、未运行 B）。
8. A 启动前绑定最近一次成功的 M0.1 严格自检 run（`strict_reference.run_id`），核对源码、可绑定 harness 代码与依赖锁指纹；不一致即拒绝启动。

**P2 配置**
1. 删除 M0.2 的布尔例外与全局 `HUAKANGOS_FAKE_CONFIG` 名单；manifest 按 command_id 登记合同：R3T3 脚本只授权其 `script/arguments` 与固定假 key/model；pytest 按完整 nodeid 登记（本批只登记 `tests/test_business_assistant.py::test_status_is_independent_and_test_config_isolated`，key=`synthetic-test-key`、model=`deepseek-flash`），无模块通配。
2. runner 把所选命令合同冻结写入 child env 与 `runs/<run>/command-context/<command_id>.json`；校验使用传入 env 与本 run 元数据，不读全局可覆盖名单。
3. pytest 插件在 setup/call 写 `node-context.json`（含 command_id/run_id/nodeid/active），teardown 置 `active=false`，collection 阶段写保留标记 `collection`（无登记能匹配）；**仅改 `PYTEST_CURRENT_TEST` 字符串无法获得许可**（自检用例断言这一点）。
4. 保留“本 run fixtures/tmp 内”“固定假 key/model”“拒绝任意 URL/endpoint”；默认 disabled、空 key、`ALLOW_AI_EXTERNAL=false`。
5. 已完成登记节点 `test_status_is_independent_and_test_config_isolated` 加入 A 阶段定向 selection，**未修改其任何断言**；其能力语义由产品现有行为决定（disabled 配置拒绝；`synthetic=true` 时 `load_config().enabled is True`；status 不回显 key）——harness 现在只放行、不代产品判定。
6. 网络审计未放开：所有状态下非回环外连仍被拒绝（自检 `test_sqlite_runtime_guard_and_external_network` 断言 `getaddrinfo`/`connect` 抛 `GuardError`）。
7. 自检新增 `test_command_contract_grants_configuration_per_exact_command_and_node`（未登记节点、别的 key、别的 command 的 node-context、节点结束后、无合同命令、伪造脚本选择、跨 run 均拒绝）与重写的 `test_offline_fake_config_exception_is_exact`（未登记 key/model/endpoint 拒绝，disabled 配置豁免）。
8. 未迁移验证根（无需 NTFS）：负例用纯判定函数与既有 venv 内的进程完成，未克隆验证根、未依赖目录联接。

**P3 文案**：27 条登记句式（补丁表 16 条 + 原 10 条 + 4 条边界）全部纳入 runner 回归 `tests/test_m02_claim_contract.py`，另加 6 个行为用例（真阳性纠正一次、反例一次结束、如实说明不纠正、真实成卡以数据库为准、纠正轮仍按原请求且不自动确认、只查询不成卡）。

**P4 冻结与判定**
- `phase_complete` 现要求：所有注册命令 complete、证据完整（命令数一致）、源码/镜像/overlay/harness 输入未变、`dependency_lock_matches`、`required_dependencies_match`；任一 false 即 exit 非零并给出 `incomplete_reasons`。
- 结果不依赖动态 manifest 写回：manifest 只放静态注册；run 目录保存 manifest 副本；通过状态写 `run.json`/`reports/run-summary.json`/`latest-run.json`/`V/m02-progress.json`。
- 聚合负例（纯判定）覆盖：命令未全过、证据不完整、输入变化、依赖锁不符、必需依赖不符，且 `milestone_complete` 恒 false。

## 3. 实测

| 命令/准确 selection | run id | exit | 结果 | 完整性 |
|---|---|---|---|---|
| `python -B V/run_validation.py --repo <repo> --milestone M0.1` | `20260927T105258Z-ed40d78a79` | 0 | 18/18（`00-selftest-strict`） | `phase_complete=true`、`milestone_complete=false`、`incomplete_reasons=[]`、`inputs_unchanged=true`、依赖双 true |
| `python -B V/run_validation.py --repo <repo> --milestone M0.2 --phase A` | `20260927T105903Z-a72790c990` | 0 | 三项命令全部 complete | `phase_complete=true`、`milestone_complete=false`、`incomplete_reasons=[]`、`strict_reference.fingerprints_matched=true` |
| ├ `a1-migrated-and-claim-tests`（两处迁移合同 + 配置节点 + claim 全表） | 同上 | 0 | collected 36 / terminal 36 / passed 36 / failed 0 / skipped 0 | 无重复行、无未收集节点、无缺终态 |
| ├ `a2-assistant-r3t3-offline`（`tests/m02_runner_adapter.py check_assistant_r3t3`） | 同上 | 0 | tests_run 39 / failures 0 / errors 0 / skipped 0 | 逐 node 证据条数=39 |
| └ `a3-anonymous-memory-migration`（迁移组 + runner 判定/配置合同） | 同上 | 0 | collected 17 / terminal 17 / passed 17 / failed 0 / skipped 0 | 无重复行、无未收集节点、无缺终态 |

判定矩阵与配置合同证据：`V/checkpoints/CP-00A/v4/command-verdicts.json`（逐命令 verdict 字段）、`command-context-*.json`（本轮实际冻结的配置合同）、`run-summary.json`。v1 判定在 reviewer 5 个探针上的错误已在 v2 修复（第 0 节）。

逐条对应补丁验收：

- [x] R1 全部反例拒绝，collect-only 正确成功；所有必需节点都有完整终态，无 skip 冒充通过。
- [x] R2 准确节点的配置测试通过；未登记 command/node/default、伪造环境名单、越界配置和外连都拒绝。
- [x] R3 补丁表及原句式回归全部通过；两类真实会话行为符合轮数与零业务写入要求。
- [x] 严格自检与 A 定向都在当前输入下通过，A 明确绑定该严格 run；依赖/执行器漂移必失败（绑定与聚合负例覆盖）。
- [x] 当前证据含逐节点结果、实际 diff、输入快照、源/测试/harness/依赖指纹及有效进程清理记录。
- [x] 原业务权限/提示词/纠正轮数/SSE/迁移未改，真实模型 0 调用，无公司/预览数据访问。
- [x] M0.2 仍 in_progress；门禁回 awaiting_review；报告为 CP-00A-v2；没有开始 B 或 M0.3。

## 4. 指纹与输入快照（v2 更正 v1 的不准确处）

| 项 | M0.1 严格 run | M0.2 A run |
|---|---|---|
| 源码指纹（598 文件，含未提交改动） | `ae0fb2f474cea48d1875c788b313a89f044e46f8f0a4c8e2ce302438e3b61502` | 同 |
| 可绑定 harness 指纹（runner + harness/*.py，不含 manifest） | `dedab6c59460115df037fe578254067f495b5c6bbc3dd7d582971f62a17f6718` | 同（因此绑定成立） |
| 全量 harness 指纹（含 manifest） | `a594961e4f4c78733e3bf7051cbc6e4c3bd37df169af17e3cc8c5ee68f4942cc` | `b73c37f8e5149d496ce79b48e128794e69d5838f9929002ae5962d0509e3effd`（差异只因 manifest 在本批被更新，见下） |
| 依赖锁 sha256 | `3910945cf6063ebe984b40cc22667657bd83476dcca1024ef4884b10f01dc930` | 同 |
| 输入未变 | `source/mirror/overlay/harness_unchanged` 全 true | 全 true |

v1 的不准确说明及更正：
1. v1 把“全量 harness 指纹”当作绑定依据，导致 manifest 记录 `strict_reference` 后自身指纹变化，绑定**永远无法成立**。v2 拆出 `bindable_fingerprint`（runner + harness 代码，不含 manifest）作为绑定输入，manifest 变化改为在 run 中留档可比对（旧 run 仅存 hash、无快照，按 P4.5 如实记录，不追写旧哈希）。
2. v1 称“两次 run harness 指纹一致”，实际只在同一 manifest 状态下成立；v2 分别列出两个口径，避免“全部相同”掩盖变化。
3. v1 的 `a3` 行写“collected=17 选择内 12 执行”自相矛盾；v2 更正为 collected 17 / terminal 17 / passed 17。
4. v1 的自检项数为 17；本批 P2 新增 1 项后为 18（登记 `minimum_tests=18`）。
5. v1 未说明 overlay 新增测试的复制机制限制；v2 记录：manifest 静态声明 `overlay_additions`，overlay 复制时按记录哈希校验，事后 `overlay_unchanged` 复核。

本轮**重新验证**的输入：生产源码（`business_assistant_service.py`）、4 个 overlay 测试、`run_validation.py`、`harness/{verdict,isolation,baseline_results,selftest,baseline,runtime_guard}.py`、`harness/m02_claim_phrases.py`、manifest、依赖锁。
本轮**未重新验证**：恢复的 308 个旧测试中除 a1/a3 选择外的其余用例、Node/workflow 全量、M0.2.B 完整基线、真实模型、PostgreSQL、真实浏览器、员工试用、M0.3 及之后全部项。

输入快照与验收 run 的差异（如实列出，不用“全部相同”掩盖）：验收 run 记录 601 个受检文件；本报告写回后冻结 `V/checkpoints/CP-00A/v4/inputs-freeze.json` 为 602 个，差异仅 `docs/implementation-checkpoints/CP-00A-v2.md` 与本报告带来的 `implementation_plan.md` 回填，**生产/领域源码零变化**（`app/`、`web/`、`migrations/` 无差异项）。按计划“仅回填状态/报告路径不要求自引用哈希”，未因报告回填重跑验收。

## 5. 状态/行为

- **纠正轮语义未变**：`_conversation` 分支条件、纠正系统消息文字、`corrected` 单次标记、轮数上限、工具权限均未改动；P3 只改“何时记为宣称”。
- **只查不写**：所有 claim 行为场景断言 fake gateway 的业务写入调用记录为空；只查询/如实说明不触发纠正、不新增卡。
- **卡数以数据库为准**：`test_the_card_count_told_to_the_model_comes_from_the_database` 仍从 `AssistantProposal` 表核对数量。
- **确认边界保持**：卡片仍为 `pending`，需员工点击原确认接口；未新增自动确认。
- **内存库**：主 `DATABASE_URL` 仍为本 run `fixtures` 内带 marker 的明确文件；辅助匿名连接为真正 `:memory:`（未新增 `anonymous-*.sqlite`）。
- **SSE 瞬时展示边界（仍未解决，独立待审）**：流式链路仍可能先展示增量文字再纠正；本补丁与 v1 一样不改变 `business_assistant_stream.py` 与前端，**不保证前端瞬时绝不显示错误宣称**。AGENTS 第 5 节“仅修正文案识别不能声称已解决所有中间 SSE 文本真实性问题”仍然适用。
- **未新增能力**：无新路由、无新迁移、无新工具、无自动续办、无后台进程。

## 6. 失败与待审阅

1. **文案判定仍是有限句式集（设计取舍）**：27 条登记句式全过，但不追求覆盖全部自然语言；未匹配文本只用于“不触发纠正”，绝不作为业务完成证据。若要求更宽覆盖，需给出新句式与反例清单。
2. **`test_status_is_independent_and_test_config_isolated` 的能力语义**：补丁 P2.5 描述的三态中，“`synthetic=false` 时产品必须拒绝启用”与“`synthetic=true` 时产品接受合成配置”同时存在；实测产品行为是 `synthetic=false`（或 key 为空）时 `load_config()` 返回 disabled、`synthetic=true` 时接受。该节点断言未修改，本批只放行 harness。若审阅认为需要产品三态区分，属于扩生产范围，需另行授权。
3. **配置例外的判定层级**：为不削弱 DB/路径守卫，`check_test_config` 仍是“默认拒绝 + 精确合同放行”的判定（而非环境名单）；`HUAKANGOS_FAKE_CONFIG` 已彻底删除。若审阅要求“节点在 setup 前也要能读到 enabled 配置”，需明确允许的窗口。
4. **`b0-collect`（B 阶段收集命令）已登记但未运行**；B 阶段 `registration_complete=false`，任何 B 命令都不会通过。
5. **本轮环境问题（已规避，供审阅知悉）**：向 E: 卷（exFAT）用文件写入工具直接创建中文内容的 JSON 会把非 ASCII 变成替换字符，本轮首次生成的句式表因此损坏；已改为“Python 源码内 ASCII 转义 + 运行期解码”，并在回归中显式断言表内不含 U+FFFD。该问题属本机工具链，不影响仓库源码，但审阅若在别处直接改写含中文的表需注意。
6. **未执行项**：M0.2.B 完整基线、M0.3 及之后、真实模型（0 次）、PostgreSQL、真实浏览器、员工试用、Node/workflow 全量。

## 7. 环境与进程

- 公司/预览库访问情况：未访问、未探测、未重置；未读取真实 `.env`。
- 主合成库/附件：每 run `V/runs/<run_id>/fixtures/test.sqlite` + 同名 `.synthetic.json`。
- 真实模型调用 0 次；fake provider 仅进程内 MockTransport/脚本化回复；非回环网络在审计入口被拒（自检断言）。
- 本任务活动进程/句柄：无。两次 runner 命令均已正常结束；探测 run（`runs/adapter-probe`）只保留证据文件，其 `source/` 镜像已清理。
- 是否在运行中修改受检输入：本轮所有最终 run 期间未编辑受检输入；`inputs_unchanged=true`。每次修改 harness/overlay 后均重跑严格自检并重新登记 `strict_reference`，未复用旧绑定。

## 8. 停止与下次范围

已停 CP-00A，未执行 M0.2.B 或 M0.3。下一批建议仍为 M0.2.B → CP-00B，尚未获准。
需要用户/Codex 决定的问题：

1. 是否接受 CP-00A-v2；若要求继续修补，请指明补丁编号与允许范围。
2. 第 6 节第 2 条（配置测试三态语义）是否需要扩到产品代码；如需，请明确授权范围。
3. M0.2.B 放行时是否要求补充 B 阶段完整注册（业务 pytest / 助手脚本 / Node / workflow）与分组报告口径。
