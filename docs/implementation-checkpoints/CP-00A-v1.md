# CP-00A 审阅报告 v1

- 日期/执行者：2026-09-27 / DeepSeek（本轮唯一实施者）
- 计划版本：`R2-20260927`
- 仓库绝对路径/HEAD/未提交改动摘要：`C:\Users\tiefu\.codex\worktrees\edb5\HuaKangOS` / `f735de2d74f5eb37f13addc1353e6a8e435a01c4` / `M AGENTS.md`（接手前既有）、`M app/business_assistant_service.py`（本轮唯一生产修复）、`?? ARCHITECTURE.md、ASTRA_LOW_EXECUTION_PROMPT.md、DEEPSEEK_EXECUTION_PROMPT.md、DEEPSEEK_HANDOFF.md、PROJECT_SPEC.md、implementation_plan.md、total_plan.md`（接手前既有文档，本轮只回填当前项记录与CP行）
- 本批授权依据：用户交接指令“按 DEEPSEEK_EXECUTION_PROMPT.md 接手；只执行 M0.2.A，停 CP-00A 并给出审阅报告；不要启动完整基线或 M0.3”；未见更晚的放行记录，CP 表在本轮开始前为 `not_ready`
- 覆盖范围：M0.2.A（A1—A6）
- milestone 状态：in_progress
- gate_state：awaiting_review
- 报告类型：正常到点
- 生产源码指纹与文件清单路径：源码指纹（598个受检文件，含未提交改动）= `37ab03397241bb301391d624e1b31f9c855404e6c5b18440e34c8510edc5e500`；清单见 `E:/HuaKangOS-agent-validation/runtime-v1/checkpoints/CP-00A/v3/inputs-freeze.json`（`source_files`）
- 测试 overlay/新增测试、harness、manifest、依赖锁指纹：
  - 输入冻结：`V/checkpoints/CP-00A/v3/inputs-freeze.json`（harness 20 文件、overlay 312 文件、archive 原始 308 文件、applicability 记录 13 文件）
  - harness 指纹（本次两次run一致）= `3a9bc0e5ee0de8ca1a0e0b4fc51e47ad4396776e63a11263a2d09f3d5ea581f8`
  - 依赖锁 `dependencies.lock.txt` sha256 = `3910945cf6063ebe984b40cc22667657bd83476dcca1024ef4884b10f01dc930`（`dependency_lock_matches=true`，43包）
  - overlay 适配 diff：`V/tests/baseline/conftest.py.m02a.diff`（34行）、`V/tests/baseline/test_business_assistant.py.m02a.diff`（63行）；适配记录（original/overlay 双哈希）写入 `V/archive/baseline-restoration.json` 的 `adapted` 与 `overlay_additions`
- 全量安全快照指纹/run id（保留原始值）：
  - M0.1 严格自检独立 run：`20260927T093923Z-27f36d7a68`（exit 0，`phase_complete=true`，`milestone_complete=false`）
  - M0.2 `--phase A` run：`20260927T093938Z-cdcb3f18da`（exit 0，`phase_complete=true`，`milestone_complete=false`）
  - 两次 run 的 `source_unchanged/mirror_unchanged/overlay_unchanged` 均为 `true`

## 改动与范围

| 文件/函数 | 改动目的 | 允许条款 | diff证据 |
|---|---|---|---|
| `app/business_assistant_service.py`：`claimed_actions` | 让“第 7 批 4 张待确认卡已真实生成…”这类明确宣称被识别（BASE-001 漏报）；仍只在“无工具调用 + 本轮0卡”时退回一轮 | M0.2 涉及文件表第1行；A4 第3条 | `V/checkpoints/CP-00A/v3/production.diff`、`production.stat.txt`；仅本文件该函数与新增纯helper、常量变化 |
| `app/business_assistant_service.py`：新增私有纯函数 `unquoted`、`clause_is_affirmative` 及 `CLAIM_*` 常量 | 把“否定/疑问/引用/未证实”判断写成纯文本helper；不访问DB/网络 | 同上（“必要的同文件私有纯文本判断helper”） | 同上 |
| `V/run_validation.py` | M0.2 `--phase A|B` 选择与校验；按注册suite判定；每条命令独立 `command-results/<id>/`；`python_script` 有限分派；`phase_complete`/`milestone_complete` 分开；overlay 新增文件与事后哈希复核 | M0.2 涉及文件表第2行；A2 | `V/checkpoints/CP-00A/v3/harness-and-tests-hashes.json`（逐文件sha256） |
| `V/harness/isolation.py` | 主库守卫不变；新增 `auxiliary_connection_allowed`（只放行字面 `:memory:`）、`fixture_path_for_registration`、`fixture_is_marked`、`marker_is_current`、`register_fixture_database`；离线fake配置例外精确到本轮 fixtures/tmp 与已知假key/模型 | 涉及文件表第3行；A3 | 同上 |
| `V/harness/runtime_guard.py` | 审计钩子只对字面 `:memory:` 放行，其余 sqlite 路径仍走 `db_path`；网络与导入守卫不变 | 同上 | 同上 |
| `V/harness/baseline.py` | 除308条恢复记录外，按 manifest 声明的 M0.2 新增测试复制 overlay，并校验其记录哈希 | 涉及文件表第6行；A2/A5 | 同上 |
| `V/harness/baseline_results.py` | 证据只写本命令独立目录；目录缺失即失败；同一命令不得二次写证据 | 同上 | 同上 |
| `V/harness/selftest.py` | 原13项保留，新增4项（匿名内存不落盘、夹具注册与外来marker、离线fake配置精确例外、未注册辅助库仍拒绝）；最小项数改由 runner 注册值决定 | 涉及文件表第4行；A2第4条、A3 | 同上 |
| `V/tests/baseline/overlay/tests/conftest.py` | 撤销“`:memory:` 变匿名磁盘文件”，恢复真正内存语义；仅对本次 pytest 临时树内无当前marker的库登记合成标记 | 涉及文件表第7行；A3.2 | `V/checkpoints/CP-00A/v3/conftest.py.m02a.diff`（原件在 `V/archive/baseline-original`） |
| `V/tests/baseline/overlay/tests/test_business_assistant.py` | 仅迁移两处过时文案断言；其余断言逐字保留 | 涉及文件表第8行；A4第1—2条 | `V/checkpoints/CP-00A/v3/test_business_assistant.py.m02a.diff` |
| `V/tests/baseline/overlay/tests/test_m02_claim_contract.py`（新增） | BASE-001 边界与反例回归（22条句式 + 6个行为场景） | 涉及文件表第9行 | 文件本体 + `V/archive/baseline-restoration.json` 的 `overlay_additions` 记录哈希 |
| `V/tests/baseline/overlay/tests/test_m02_harness_contract.py`（新增） | runner 阶段选择与判定合同（空集合/收集错误/无结果/超时/低于注册项/证据缺失均不得通过） | 同上 | 同上 |
| `V/tests/baseline/overlay/tests/m02_runner_report.py`、`m02_runner_adapter.py`（新增） | runner 拥有的离线脚本证据写入器与适配器（让恢复的 unittest 脚本产出 `command-result.json`） | 同上 | 同上 |
| `V/validation-manifest.json` | M0.2 A/B 命令登记、最小项数、overlay新增清单、离线fake配置白名单、`phase_complete.A=true` | 涉及文件表第10行 | `V/checkpoints/CP-00A/v3/harness-and-tests-hashes.json` |
| `V/tests/baseline/{applicability,baseline_defects}.json`、`V/m02-progress.json` | BASE-001 归属与当前状态；A阶段进度指向本版；旧失败记录不改写 | 涉及文件表第10—11行 | 同上 |
| `implementation_plan.md` 当前项记录与 CP-00A 行、`docs/implementation-checkpoints/CP-00A-v1.md` | 真实状态与审阅摘要 | 涉及文件表第12行 | 本文件 + 计划片段 |

未跟踪文件与 V 内变化均有清单：仓库内未新增跟踪文件（本轮未在仓库新增测试或数据）；V 内新增见 `v3/inputs-freeze.json` 的 `trees` 与 `overlay_additions`。临时诊断脚本 `V/harness/probe_*.py`、`V/harness/dbg_probe_*.py`、`V/harness/record_adaptations.py` 属验证器，已计入 harness 指纹，不进入源码镜像。

## 状态/行为

- **纠正轮语义未变**：`_conversation` 的分支条件、纠正系统消息文字、`corrected` 单次标记、轮数上限、工具权限全未改动。BASE-001 修的是“明确宣称未被识别”，不是“纠正轮做什么”。
- **只查不写**：`test_a_read_only_question_never_gains_a_card`、`test_truthful_reply_about_missing_fields_is_not_corrected` 证明只查询/如实说明不触发纠正、不新增卡；`tests/test_m02_claim_contract.py` 中所有场景的 `assistant[1] == []`（fake gateway 的业务写入调用记录）保持为空。
- **卡数以数据库为准**：`test_the_card_count_told_to_the_model_comes_from_the_database` 现按当前合同核验系统消息“实际准备或复用 2 张待确认卡”，并直接从 `AssistantProposal` 表读取2张pending、排除被拒绝的 `no_such_operation`。
- **原确认边界保持**：卡片仍为 `pending`，需员工点击原确认接口；本轮未改 `confirm_proposal`/`decide_proposal`，未新增自动确认。
- **内存库**：主 `DATABASE_URL` 仍是本run `fixtures` 内带marker的明确文件；辅助匿名连接恢复真正 `:memory:`（两次连接互不可见、关闭即失、未新增任何 `anonymous-*.sqlite` 磁盘文件）。
- **未改变的 SSE 边界（独立待审阅）**：现有流式链路仍可能先把模型增量文字展示给员工，再在完整回复阶段触发纠正。BASE-001 修复不改变 `business_assistant_stream.py` 与前端处理，因此**不保证前端瞬时绝不显示错误宣称**。是否调整属后续 M4/M5 范围，由审阅决定。
- **未新增能力**：无新路由、无新迁移、无新工具、无自动续办、无后台进程；`LEGACY_BUSINESS_WRITE` 仍只用于恢复的旧测试子环境。
- **状态回填后的指纹说明**：验收 run 之后，本报告（`docs/implementation-checkpoints/`）与计划当前项记录被写回，因此工作树整树指纹会随之变化；除这两个自引用文档外，受检生产/测试/harness/依赖文件与 run 记录逐项一致（`app/business_assistant_service.py` 的 sha256 `068ce43da1ed00ece9c71fa370c0514d7a88bdfc4a522e8da129a1aae9f0bd1b` 与run记录相同，其余变更文件仅此两项）。按计划规则，状态/报告回填不要求自引用哈希。

## 实测

| 命令/准确selection | run/group id | exit | passed/failed/error/skipped/not_run | 完整性 | 报告 |
|---|---|---|---|---|---|
| `python -B V/run_validation.py --repo <repo> --milestone M0.1` | `20260927T093923Z-27f36d7a68` | 0 | 17/0/0/0/0（`00-selftest-strict`） | `commands_ok=true`，`evidence_complete=true`，`registration_complete=true`，源/镜像/overlay未变 | `V/runs/20260927T093923Z-27f36d7a68/run.json`、`reports/run-summary.json` |
| `python -B V/run_validation.py --repo <repo> --milestone M0.2 --phase A` | `20260927T093938Z-cdcb3f18da` | 0 | 见下三条 | `phase_complete=true`，`milestone_complete=false` | `V/runs/20260927T093938Z-cdcb3f18da/run.json` |
| ├ `a1-migrated-and-claim-tests`（迁移后两处旧合同 + `tests/test_m02_claim_contract.py`） | 同上 | 0 | 21/0/0/0/0 | collected=21，≥注册最小18 | `command-results/a1-migrated-and-claim-tests/` |
| ├ `a2-assistant-r3t3-offline`（`tests/m02_runner_adapter.py check_assistant_r3t3`） | 同上 | 0 | 39/0/0/0/0 | tests_run=39=注册最小值 | `command-results/a2-assistant-r3t3-offline/` |
| └ `a3-anonymous-memory-migration`（匿名内存迁移 + 两处 gift 迁移 + runner合同） | 同上 | 0 | 12/0/0/0/0 | collected=12（含 10 项 runner 合同用例） | `command-results/a3-anonymous-memory-migration/` |
| 修复前同源镜像（仅原始归档测试文件）：两处旧合同 + claim合同 | `V/runs/adapter-probe/results/prefix-pristine` | 1 | 17/4/0/0/0 | 诊断用，不作为验收 | `V/checkpoints/CP-00A/v2/evidence/prefix-pristine-results.json` |
| 修复后同源镜像同一选择 | `V/runs/adapter-probe/results/postfix` | 0 | 21/0/0/0/0 | 诊断用 | `V/checkpoints/CP-00A/v2/evidence/postfix-results.json` |
| 22条句式扫描（A4表全部输入） | `V/runs/adapter-probe/results/scan` | 0 | 22/22 预期一致 | 含真阳性4、反例10及其他已登记句式 | `V/checkpoints/CP-00A/v2/evidence/claim-scan.txt` |

逐条对应 CP-00A 验收条件：

- [x] 新旧严格隔离自检完整；辅助内存连接不落盘，主库/路径/网络/假配置边界仍有效 —— M0.1 run 17/17（含新增4项），`test_anonymous_memory_connections_stay_in_memory` 断言无 `anonymous-*.sqlite`，`test_unregistered_auxiliary_database_still_fails_closed` 保持拒绝。
- [x] runner 能区分定向成功、注册未完成、空集合、失败/超时，必需结果均非空；不会混写分组报告 —— 判定函数逐条覆盖（`empty_selection`/`collection_error`/`no_test_results`/`missing_report`/`missing_result_directory`/`timed_out`/`nonzero_exit`/`below_registered_minimum`/`suite_reported_failure`），每条命令独立目录；本轮真实出现过的“空集合”（`16abc5b6cb`）与“源在run中被改”（`a5e881a64a`）都被拒绝而非计通过。
- [x] 两项旧断言有当前合同映射、原件/diff及等强度行为核验，未恢复强制准备卡的旧提示 —— 原件在 `V/archive/baseline-original`（哈希每run复核），diff 见上表；新断言核验“本轮实际确认卡数量为0 / 不能为了使一句话成立而新增业务 / 员工的原请求”与“实际准备或复用 2 张（数据库核对）”；`_conversation` 纠正提示未改，未新增任何“逼模型准备卡”的措辞。
- [x] BASE-001 修前失败/修后通过及反例通过，数据库卡数/只查不写/原确认边界保持 —— 见上表前两行与句式扫描；`assistant[1]==[]` 与 `AssistantProposal` 计数断言覆盖只查不写。
- [x] 当前离线 R3T3 脚本运行，模型真实调用0；SSE瞬时展示边界如实列出 —— 39项通过，全部为脚本化回复与进程内 MockTransport；`model_calls=0`、`network_mode=loopback_only`；SSE 边界见上一节。
- [x] 报告绑定当前源码/测试/harness/依赖指纹，范围核对无越界；不执行完整基线，M0.2 不设 done，停 CP-00A —— 两次 run 指纹一致；B 阶段命令未运行；计划中 M0.2 仍为 `in_progress`。

## 失败与待审阅

本轮范围内的失败均已修复并复测；以下为需要审阅判断的事项：

1. **SSE 瞬时展示边界（类型：既有产品表现，未修）**。nodeid 不适用；现象=流式增量可能先展示“已生成”类文字，随后完整回复才纠正。复现=`business_assistant_stream.py` + 前端增量渲染路径，本轮未运行真实浏览器。影响=员工可能短暂看到未经证实的宣称。归属=后续 M4/M5 范围。建议（不等于授权）=CP-00A 放行后由审阅决定是否补丁或并入 M4/M5。
2. **判定用词触发条件较窄（类型：设计取舍）**。`claimed_actions` 仍是句式匹配，不追求识别全部自然语言；24项已登记句式外的新表述可能既不触发纠正也不被当作证据（后者是正确方向：未匹配文本绝不作为业务完成证据）。若审阅要求更宽覆盖，需明确句式清单与反例。
3. **契约测试为单元级（类型：可验证性说明）**。本验证根在 exFAT 卷上，无法创建 runner 专用 venv 所需的目录联接，因此 `test_m02_harness_contract.py` 以“直接调用 runner 的选择与判定函数 + 真实报告文件”验证负例；正向端到端由真实 `--phase A` run 证明。若审阅要求子进程级负例，需要在 NTFS 卷上重绑一个验证根（属新增外部条件）。
4. **旧合同迁移外的其他旧测试冲突**：本轮未发现新的旧文案冲突；`tests/` 在仓库被清理，B 阶段恢复后可能出现新冲突，按计划 B4 处理。
5. **未执行项**：M0.2.B 完整基线、M0.3 及之后全部项、真实模型（0次）、PostgreSQL、真实浏览器、员工试用、Node/workflow 全量套件。

## 环境与进程

- 公司/预览库访问情况：未访问、未探测、未重置；验证器不读取仓库 `.env`。
- 主合成库/附件路径和标记证据：每次run `V/runs/<run_id>/fixtures/test.sqlite` + 同名 `.synthetic.json`（`{"run":"<run_id>","synthetic":true}`）；附件/临时目录隔离在 `V/runs/<run_id>/{attachments,tmp,profile}`。
- 真实模型调用数 / fake调用数 / 网络守卫证据：真实模型 0 次；fake provider 调用仅发生在进程内 MockTransport/脚本化回复中（R3T3 39项与 claim 合同6场景），不产生外连；`runtime_guard` 审计钩子仍在，非回环 `socket.connect`/`getaddrinfo` 直接拒绝（自检用例覆盖）。
- 本任务活动进程/句柄：无。两次 runner 命令已结束；探测run（`runs/adapter-probe`、`runs/dbg-probe`）只留证据文件，其 `source/` 镜像与临时目录已清理，无后台进程。
- 是否在运行中修改受检输入：本轮出现过一次（`implementation_plan.md` 在 M0.1 运行中被编辑，run `a5e881a64a` 因此被 `source_changed_during_copy` 拒绝，该run不计通过）。其后所有最终 run 均在无编辑状态下完成，`source_unchanged=true`。

## 停止与下次范围

已停 CP-00A，未执行 M0.2.B 或 M0.3。
下一批建议 M0.2.B→CP-00B，尚未获准。
需要用户/Codex决定的问题：

1. 是否接受 CP-00A，以及是否为上述 SSE 瞬时展示边界写补丁（若写，需明确允许修改文件与关闭测试）。
2. BASE-001 是否按本轮定向证据标 `resolved`（当前登记为 `resolved_pending_cp_review`），还是要求补充子进程级 runner 负例后再标。
3. M0.2.B 放行时是否要求换到 NTFS 卷上的第二个验证根，以便把 runner 负例做成真实子进程端到端。
