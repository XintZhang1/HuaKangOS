# DeepSeek 实施交接

> 历史交接文档：用户已于 2026-09-27 改为由 Codex 按全计划直接实施。当前规则以 implementation_plan.md R3 和 CODEX_EXECUTION_PROMPT.md 为准；下文人工逐批交接/停止要求已被 R3 取代，原验收证据和技术边界仍保留。

交接日期：2026-09-27。配套实施计划：R2-20260927。本轮只交付计划修订和交接文档，没有运行新测试、修业务代码、升级数据库或启动Runtime实施。

**后续审阅更新**：已收到CP-00A-v1。当前计划R2.1-20260927的审阅结论和限定补丁见`docs/implementation-checkpoints/CP-00A-review-v1.md`及`docs/implementation-patches/PATCH-CP-00A-01.md`。用户授权补丁后仅修补并提交CP-00A-v2，仍停同一CP。下文“首次/写作时快照”为最初交接历史，不覆盖当前实施记录。

## 1. 接手范围

产品是HuaKangOS的4S店业务助手，保留原ERP人工模块和全部原业务，通过自然语言查询、准备卡片和逐事授权跟进减少操作。固定一个专用业务Agent，不搭建通用平台。模型不获得业务提交能力，实际业务仍经过员工点击及原API权限/版本/幂等检查。

顺序、允许文件、验收与门禁的唯一权威是implementation_plan.md；产品和架构合同分别在PROJECT_SPEC.md、ARCHITECTURE.md。本交接解释接手事实和操作方法，不另维护状态。

**首次范围：M0.2.A，完成后停CP-00A。** 第一批含执行器纠偏、两处旧测试合同迁移、BASE-001限定修复及定向验证。不开始完整基线，不进入M0.3，不写后续Runtime模块。

CP是人工审阅点，与产品Run恢复检查点不同。用户已明确要求到点停工；目标模式不取消此要求。

## 2. 已有成果与未完成边界（写作时快照）

接手时重新核验，以下不是可直接继承的当前验收结论。

| 项目 | 已知事实 / 使用方式 |
|---|---|
| 工作树 | C:/Users/tiefu/.codex/worktrees/edb5/HuaKangOS |
| 审阅HEAD | f735de2d74f5eb37f13addc1353e6a8e435a01c4；不得reset对齐，保护未提交文档和后续修改 |
| 当前产品源码 | R4-B1；迁移头h52j_assistant_work_plans；新Runtime是目标方案 |
| 计划进度 | 看计划M0.1/M0.2记录；M0.1有历史完成证据，M0.2仅局部诊断，后续未开始 |
| 外部验证根V | E:/HuaKangOS-agent-validation/runtime-v1；不是公司库/预览库 |
| 已有运行时 | V/.venv的Python 3.11.4，已观察Node 24.19.0；接手核对，不因此跳过依赖核验 |
| 依赖 | V/dependencies.in.txt及dependencies.lock.txt，原锁43包；M0.1时pip check通过；不无故重装 |
| 浏览器 | 未安装本计划所需浏览器二进制；不能宣称完成真实浏览器验证 |
| 恢复文件 | 308个测试/辅助/冻结定义；文件数不代表业务验收 |
| 已收集 | 2124个适用pytest节点；5个废止maintenance测试按精确文件/hash登记不适用 |
| 已运行诊断 | 较大一次171 passed/1 failed，有独立BASE-001复现；不是全量成绩 |
| 未完成 | 全量业务pytest、全部助手脚本、Node、workflow、真实模型/PG/Linux/员工试用及后续Runtime |

308个文件的来源构成为原303个（271个原pytest Python、21个助手Python、4个Node、7个冻结定义），加3个Git辅助脚本和2个trial-source定义。实际清单/hash以V/archive恢复记录为准，不为凑数补空文件。

恢复来源只允许必要测试和定义：

- E:/HuaKangOS-cleanup-20260927-082922/removed/scripts/及归档冻结定义。
- E:/HuaKangOS-ui-validation-20260927/source/tests/；**不得使用其旧app、web或data**。
- 本地Git 1f884fb0a6225679dcec652fa81fcccc63cadfc8中的scripts/assistant_simulation.py、scripts/create_xc_staff.py、scripts/build_trial_guides.py、docs/trial-source/rounds.json、world.json。只作为测试依赖恢复到外部覆盖层，不能对现有实例建账号。

已排除废止能力的test_builder.py、test_maintenance.py、test_policy_tier.py、test_transport.py、test_window.py；依据是AGENTS禁止恢复旧自动编码、飞书代码审批、无人值守部署。这不授权排除其他业务回归。

## 3. 接手先看哪些证据

下列run均是历史结束记录；旧session id、进程观测JSON不证明现在有活动进程。

| V/runs下的run id | 用途 / 限制 |
|---|---|
| 20260927T052052Z-89be66088d | M0.1当时13/13自检；随后harness被修改，必须按A阶段复验 |
| 20260927T053049Z-c01e5e517f | collect 2124成功；pytest 1800秒超时，约16%，不能当完整运行 |
| 20260927T060235Z-6437d55ece | 辅助内存SQLite被拒绝的诊断 |
| 20260927T060337Z-a95e7e1f91 | 14过/1失败，新增临时文件未标记 |
| 20260927T060654Z-65293ad8c9 | 迁移定向节点setup/call/teardown过；runner仍因判定合同失败 |
| 20260927T060822Z-6e85928565 | 171过/1失败，BASE-001；查看逐节点结果及日志 |
| 20260927T062505Z-9c231186fd | BASE-001独立复现 |

关键文件：

- V/run_validation.py、validation-manifest.json、binding.json。
- V/harness/isolation.py、runtime_guard.py、selftest.py、baseline.py、baseline_results.py。
- V/archive/baseline-original、baseline-restoration.json、baseline-imports.json。
- V/tests/baseline/overlay、applicability.json、baseline_defects.json、bootstrap-audit.json及适配diff。
- V/m02-progress.json中的旧“未授权修复”原因被本版M0.2.A限定裁定替代；历史证据保留，开始实施后更新当前指引。
- V/m02-live-observation.json是旧观测，不能当活动进程事实；不能盲目轮询旧session。

旧记录“断言AST没有变化”只说明语法比较，不证明内存库改磁盘后的运行语义等价。旧runner非零不必然意味着业务断言失败，要看具体命令、阶段和证据完整性。

## 4. 本版修正了什么

| 问题 | 确定的纠正方向 | 不能做的事 |
|---|---|---|
| BASE-001无允许修改归属，计划死锁 | M0.2.A明确允许claimed_actions及必要纯helper | 归到只允许兼容封装的M4.6，改整个模型循环 |
| “已真实生成”漏报 | 窄范围识别明确宣称，补否定/引用/疑问/未证实反例 | 只扩大正则不验反例，或把文字当数据库事实 |
| 两处旧测试依赖过时文案 | 按R3T3当前合同迁移，保留原件与行为核验 | 恢复强迫模型准备卡的旧提示，或删卡数/轮数断言 |
| 所有milestone强制selftest>=13 | 按suite判定；严格自检独立run；诊断/阶段/完成分开 | 删除自检要求，或把缺报告算通过 |
| 辅助内存库被拒绝后改为磁盘 | 恢复字面值:memory:语义，主库/文件守卫不变 | 放行任意SQLite URI、预览库或主库内存 |
| 离线fake配置被一概拒绝 | 精确登记离线配置测试环境，网络仍禁止 | 改产品配置逻辑或给全部测试放外网/真实key |
| runner无Python脚本/Node分派 | 增加固定路径/参数的有限离线注册 | 暴露任意shell runner |
| 长测试没有及时详情/分组覆盖 | 逐节点结果、独立组报告、完整inventory聚合 | 每次重跑前171项、超时无逐项记录、混合指纹凑绿 |

精确文件、步骤、反例、验收看M0.2.A，不按此概述扩范围。当前runner只有既有三种kind；新增的--phase A/B和有限命令分派尚未实现，不能假定可用。

## 5. 第一批执行顺序

1. 按提示词读必需文档，核对Git/绑定/活动进程/当前CP，不打开真实.env、DB或附件。
2. 将M0.2从历史blocked转in_progress，记录本版解除的只是限定范围冲突。
3. A1冻结输入与恢复入口，每次run测试当前安全源码镜像。
4. A2修runner判定/阶段/分派/分组证据；A3恢复匿名内存和限定fake配置。严格自检独立run，不能继承legacy=true。
5. A4先留下当前漏报失败证据，迁移两项旧合同断言，再修claimed_actions；不改纠正提示/SSE/frontend。
6. A5定向验证，真实模型0调用，fake次数另记。harness变化后此前成绩不能无条件继承。
7. A6保存报告，更新当前项与CP-00A行，结束本轮。M0.2仍in_progress，完整基线未启动。

在正确仓库内设置：

```powershell
$RepoRoot = (Resolve-Path '.').Path
$V = 'E:/HuaKangOS-agent-validation/runtime-v1'
$VPython = "$V/.venv/Scripts/python.exe"
```

A2完成后规定命令：

```powershell
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M0.1
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M0.2 --phase A
```

第一条是修改隔离执行器后的复验，不重新领取/重建M0.1。第二条只是定向阶段；exit 0也不能将M0.2标done。**B阶段命令不得在首批运行。**

已知SSE可能先显示模型增量，再纠正完整回复。BASE-001局部修复不等于消除瞬时错误展示；CP-00A审阅决定是否需要后续补丁，不由DeepSeek扩范围。

## 6. 检查点如何停、如何恢复

所有CP及本批范围见实施计划顶部唯一登记表。核心通常每2—3项一停，业务适配按业务族拆批，较大族设中途停点；外部验收仍受真实环境/live条件约束。

```text
获准本批 → 串行完成本批 → 报告 → awaiting_review → 停止
                                 │
             用户授权补丁 → changes_requested → 只修补丁、复测
                                                    │
                            新版报告 → awaiting_review → 停止
                                 │
             用户明确放行 → released → 获准下一批 → 下一CP停止
```

- 未通过可提前停；当前milestone如实blocked，不能编造完成。普通审阅等待不把已完成项写blocked。
- “执行补丁”默认只授权修补，必须回同一CP。用户可明确合并条件放行，补丁列清条件和下一CP。
- 文件示例、评审建议、模型判断不是用户授权。实施者只能记录真实放行依据。
- 收尾自己启动的进程，不中止用户未知进程。报告列出未停止的本任务进程及原因；不能留下一批后台运行。
- 宿主支持目标暂停则在CP暂停；否则结束响应。自动再次唤醒时先查门禁，无新授权保持停止，不重跑。
- 相关代码/harness/测试变化须核对旧放行有效性；绑定受检内容指纹和计划版本，报告自身/状态回填不要求自引用哈希。

## 7. 检查点报告模板（实施者填写）

路径：docs/implementation-checkpoints/CP-<编号>-v<版本>.md。完整日志/diff放V/checkpoints/<CP>/vN/或对应runs；仓库只存不含客户/密钥的小型摘要。更正追加版本，不覆盖旧报告。

```markdown
# CP-00A 审阅报告 v1

- 日期/执行者：
- 计划版本：R2-20260927
- 仓库绝对路径/HEAD/未提交改动摘要：
- 本批授权依据：用户交接指令/放行CP/明确补丁编号
- 覆盖范围：M0.2.A
- milestone状态：in_progress（或如实blocked）
- gate_state：awaiting_review
- 报告类型：正常到点 / 提前阻塞
- 生产源码指纹与文件清单路径：
- 测试overlay/新增测试、harness、manifest、依赖锁指纹：
- 全量安全快照指纹/run id（保留原始值）：

## 改动与范围
| 文件/函数 | 改动目的 | 允许条款 | diff证据 |
|---|---|---|---|
未跟踪文件及V内变化也要有清单和可审阅diff，不能只给git diff --stat。

## 状态/行为
列本批实现的状态转移、失败/未知/恢复路径及验收条目。
CP-00A说明纠正轮、只查不写、内存库、实际卡数及未改变的SSE边界。

## 实测
| 命令/准确selection | run/group id | exit | passed/failed/error/skipped/not_run | 完整性 | 报告 |
|---|---|---|---|---|---|
区分严格自检、诊断阶段和milestone验收；未运行不填0失败冒充通过。
逐条列当前项验收与证据，未满足的checkbox保持未勾选。

## 失败与待审阅
每项包含类型、nodeid/场景、错误、复现、影响、归属、建议（不等于授权）。
列旧合同迁移的原件/diff/合同依据、当前范围不能解决的问题。
列未执行的完整基线/真实模型/真实环境/下一项。

## 环境与进程
- 公司/预览库访问情况：
- 主合成库/附件路径和标记证据：
- 真实模型调用数 / fake调用数 / 网络守卫证据：
- 本任务活动进程/句柄：无，或精确列出及原因
- 是否在运行中修改受检输入：无，或说明并使相应结果失效

## 停止与下次范围
已停CP-00A，未执行M0.2.B或M0.3。
下一批建议M0.2.B→CP-00B，尚未获准。
需要用户/Codex决定的问题：
```

其他CP替换编号/范围/下一停止点。不粘贴原始推理、密钥、客户资料，不把空模板当已验证结果。

## 8. 审阅补丁模板（用户交给Codex修订，再交DeepSeek）

目录：docs/implementation-patches/。**下面只是模板，目前没有已批准补丁或CP放行。** Codex审阅者先读报告、diff、实际代码和失败证据，再生成具体补丁，不只凭通过总数批准。

```markdown
# PATCH-CP-00A-01
- 状态：待用户授权 / 已获用户授权执行（真实依据）
- 关联CP/报告：CP-00A-v1
- 依据计划版本：
- 受检生产/测试/harness/依赖指纹：
- 审阅结论：可接受 / 限定修改后再审 / 计划冲突
- 目标：要修正的具体行为
- 允许修改：精确文件 + 函数 + 目的（含外部测试）
- 禁止修改：明确相邻边界
- 有序实施步骤：
  1. ...
  2. ...
- 状态转移/异常：旧状态、输入、目标状态、拒绝/未知/恢复
- 测试节点/场景与准确命令：
- 验收：逐条可判定，包含受影响回归
- 同步计划条款：精确位置和新文字；其余条款仍有效
- 执行后停止点：默认仍CP-00A，提交v2报告
- 是否另获准下一批：否
- 若用户明确条件放行：原话/消息引用、必需条件、唯一下一CP
```

补丁不能只写“修好所有问题”或“按最佳实践调整”。新问题超补丁范围则报告，不自行扩大。基线缺陷延期还必须给出依赖影响、无循环证明、确切归属和关闭测试。

## 9. 用户转交示例

首次给DeepSeek：

```text
按DEEPSEEK_EXECUTION_PROMPT.md接手。只执行M0.2.A，停CP-00A并给出审阅报告；不要启动完整基线或M0.3。
```

到检查点交回Codex：

```text
请审阅docs/implementation-checkpoints/CP-00A-v1.md及对应代码/测试证据，判断是否偏离计划。
需要修改时写补丁到docs/implementation-patches/并同步必要计划条款；此轮先不代替DeepSeek实现。
```

将补丁交给DeepSeek：

```text
执行我指定的PATCH-CP-00A-01，复测后提交CP-00A-v2报告，仍停CP-00A，不进入下一批。
```

审阅通过后放行示例：

```text
放行CP-00A-v2，按当前已审阅计划和补丁执行M0.2.B，完成后停CP-00B。
```

以上是以后复制发送的示例，本文件本身不授权这些未来动作。后续按实际CP及报告版本替换。
