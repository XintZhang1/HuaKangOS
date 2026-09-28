# PATCH-CP-00A-01：纠正首批回归与验收判定

- 编写日期：2026-09-27。
- 状态：审阅补丁已编写，待用户交给DeepSeek执行；不构成下一批放行。
- 关联：docs/implementation-checkpoints/CP-00A-v1.md及CP-00A-review-v1.md。
- 依据计划：R2.1-20260927；本补丁是M0.2.A内部修补，不新增milestone，不改变108项顺序。
- 审阅输入：生产service SHA256为068ce43da1ed00ece9c71fa370c0514d7a88bdfc4a522e8da129a1aae9f0bd1b；执行器/隔离/manifest指纹及差异见V/review/CP-00A/review-state.json，原run 20260927T093938Z-cdcb3f18da。
- 目标：修复本轮新文案回归，使首批结果只能在完整执行、精确隔离和输入未变时通过。
- 停止点：**仍为CP-00A，提交CP-00A-v2；不运行M0.2.B或M0.3。**
- 另行放行下一批：否。

V = E:/HuaKangOS-agent-validation/runtime-v1。补丁授权后先核对实际代码与审阅指纹；出现额外生产改动先报告，不覆盖用户修改。

## 允许修改与禁止修改

| 文件 | 允许范围 |
|---|---|
| app/business_assistant_service.py | CLAIM_*常量、unquoted、clause_is_affirmative、claimed_actions及必要私有纯helper |
| V/run_validation.py | phase注册选择、verdict/counts、命令证据收集、run_commands/main的隔离上下文与完整性判定；必要纯helper |
| V/harness/isolation.py | fake_config_allowlist/check_test_config/validate_environment及必要的当前测试上下文helper；不削弱DB/路径守卫 |
| V/harness/runtime_guard.py | 仅为上述上下文校验传递必要参数，保留网络、SQLite、导入守卫 |
| V/harness/baseline_results.py | 当前node上下文、collect/execute证据、逐项状态；不改业务测试结果 |
| V/harness/selftest.py | 保留原安全用例，补精确配置、网络及输入完整性负例 |
| V/tests/baseline/overlay/tests/test_m02_claim_contract.py | 补本文句式与纠正轮行为回归 |
| V/tests/baseline/overlay/tests/test_m02_harness_contract.py | 补完整性、注册、配置、超时、漂移和依赖判定用例 |
| V/tests/baseline/overlay/tests/m02_runner_adapter.py、m02_runner_report.py | 仅补每个unittest节点结果/跳过原因及command绑定证据，不另改原脚本业务测试 |
| V/validation-manifest.json | 分阶段注册及精确离线配置合同，静态声明；不存通过结论 |
| V/harness/baseline.py及V/archive恢复清单 | 仅同步新增/更新测试覆盖层的来源、哈希，不替换当前业务代码 |
| V/tests/baseline的适配diff/缺陷记录、V/m02-progress.json | 保留旧记录并追加本补丁状态与证据 |
| V/review、V/checkpoints、V/runs | 新的合成证据、diff、冻结清单；不覆盖旧run |
| implementation_plan.md当前项记录/验收与CP行、CP-00A-v2.md | 如实回填，不自行改变其他milestone和门禁 |

原两项已审过的测试迁移保留，本补丁不再改其业务断言。允许把现有
tests/test_business_assistant.py::test_status_is_independent_and_test_config_isolated
加入A阶段定向selection，但不修改它来迎合harness。

禁止：_conversation纠正提示/轮数/工具权限、business_assistant_prompt.py、stream/frontend、原API/schema/RBAC/业务状态机/金额数量/迁移；禁止全量测试或后续Runtime；禁止真实配置/公司库/原预览库/模型联网；禁止换验证根、重装环境、删除旧证据或扩大归档恢复范围。

## P1. 先修结果判定（R1）

1. 将collect与execute分支分开：
   - baseline_collect只读本command目录的pytest-collection.json，要求非空无重复collected、零collection_errors、正确command/source标识、进程及报告exit均为0。
   - collect只表示收集完成，不要求call记录，也不算执行通过；测试数下限取collected。
   - baseline_pytest只读pytest-results.json；不能拿共享reports下的旧文件或别的command报告补缺失。删除collect_evidence跨命令兜底，selftest也写本command证据。
2. 对pytest的collected和results逐nodeid核对：
   - 结果不得出现未收集节点，不得重复同node的同phase；终态节点集合必须等于准确collected集合。
   - 正常通过须setup/call/teardown全部完成且passed；只有setup记录不算执行完成。
   - setup/call/teardown任一失败均判失败，不能因为外层exit=0而忽略；报告exit与进程exit必须一致。
   - skip/xfail/xpass必须单独记录。首批必需用例不准跳过；未来只有精确nodeid及理由经登记的skip才可分类，不计为passed，不用数量阈值掩盖缺项。
   - empty、缺结果、缺终态、集合不等、未知状态、下限不足均不可complete。
3. unittest脚本除汇总外记录实际test id、outcome、skip原因；所有必需节点必须完成。testsRun包括skip，不能直接当有效通过数；本批要求零skip/xfail。
4. timed_out=true立即返回complete=false，无论进程最终是否刚好返回0、报告是否success。任何错误reason存在时都不能complete。
5. 所有报告须匹配本command_id/source；schema不全给明确缺字段错误，不把缺字段默认为成功。
6. 分阶段注册：A只声明其完整定向清单，B的完整业务/助手/Node/workflow未注册前保持registration_complete=false。默认缺注册不得视为true。移除manifest的phase_complete结果值及人为milestone_complete开关，通过结果由runner计算。
7. 当前判定范围固定：
   - M0.1严格自检通过可记该自检完成；
   - M0.2.A通过只能phase_complete=true，milestone_complete永远false；
   - B未完整注册不得产出完整基线通过；本补丁不实现/运行完整B。
8. 保持原两条执行命令。A启动前绑定最近一次成功M0.1严格自检run_id，核对受检源码/harness/依赖输入相同；缺失或不匹配则拒绝，不凭“以前17项过了”继承。绑定写本run记录，不回写manifest制造指纹自变。

必补负例：两收集一执行、仅setup、失败但exit0、报告exit不符、全部skip、重复/额外节点、缺teardown、timeout+exit0、错误command_id、缺报告、有report但注册不完整。补collect-only正常成功例及空/错误收集拒绝例。原17项自检和现有runner测试不删除。

## P2. 精确限定离线配置（R2）

1. 删除整个M0.2的布尔例外。manifest按command_id登记合同：
   - 独立离线R3T3脚本只授权准确script/arguments和固定假key/model，不扩展其他脚本。
   - pytest按完整nodeid（参数化含参数后缀）登记所需fake配置，不能使用模块通配或“所有M0.2”。
   - A已选用例确需assistant fixture的，先从确定的selection/collection清单取得精确nodeid再登记；不能因方便给整库授权。
2. runner把所选command合同冻结到run元数据；校验函数使用传入env与本run元数据，不能只读全局os.environ中的可覆盖名单。
3. pytest插件在setup/call/teardown按实际节点建立当前上下文，结束清理；collection阶段没有活跃节点，默认严格。不能仅改PYTEST_CURRENT_TEST字符串就获得另一个节点的许可。脚本上下文由runner的实际分派绑定。
4. 保留run内fixtures/tmp路径、固定假key/model、拒绝任意URL/endpoint的规则。默认enabled=false、空key、ALLOW_AI_EXTERNAL=false。
5. 仅精确配置测试节点test_status_is_independent_and_test_config_isolated允许这些预定状态：
   - ALLOW_AI_EXTERNAL暂为true但没有BUSINESS_ASSISTANT_CONFIG：产品status应未就绪，不读取外部配置。
   - 本run路径中的固定假key/model，synthetic=false：harness允许完成测试，产品必须拒绝启用。
   - 同一配置synthetic=true：产品接受合成配置，返回status不含key。
   - 该节点结束后严格默认恢复；其他节点不得继承此例外。
6. 这只是产品配置单元测试例外。所有状态下网络审计照常禁止非回环外连；不开放live gate，不使真实API可达。原数据库和附件边界不变。
7. 在A增加原配置测试节点，不改它的断言；测试注册/未注册command与node、metadata不许可、环境名单伪造、未知key/model/路径/endpoint、节点结束后残留例外均被拒绝。
8. 在配置允许ALLOW_AI_EXTERNAL=true的准确节点内验证网络调用在审计入口被拒，必须在建立实际连接前结束。用合成固定地址/假key，无真实凭据，无实际外发。

无需迁移到NTFS。直接调用纯判定函数覆盖组合即可；必须证明网络/子进程路径时，通过同一V的runner和现有venv启动受控子进程，不克隆验证根或依赖junction。

## P3. 修复文案回归（R3）

1. “实际/真实/确实/真的”不能独立作为已完成标记；仅作为明确“已/已经/成功”等的受限修饰。保留原本支持的“准备好了/生成成功”结构。
2. 恢复原真阳性中的有限空白和“都”等明确修饰；数量/修饰有边界，不回退到无界 .*，不引入完整NLP解析器。
3. 否定/疑问/未证实只约束其对应的卡片宣称；后面另一件事待核对或询问是否还需帮助，不能让前面的已完成宣称消失。
4. 中文及英文双引号中的引用/解释不当成模型正在宣称完成。不能靠删除所有带问号/引号的整句解决。
5. 本表全部纳入正式runner回归，不只放在独立扫描：

| 文案 | claimed_actions预期 |
|---|---:|
| 第 7 批 4 张待确认卡已真实生成，请逐张核对后点击确认。 | true |
| 确认卡已生成。 | true |
| 确认卡 已生成。 | true |
| 确认卡都已生成。 | true |
| 确认卡已生成，请问还需要其他帮助吗？ | true |
| 确认卡已生成，客户地址需要核对。 | true |
| 实际生成确认卡前，请先补齐资料。 | false |
| 若实际生成确认卡，请逐张核对。 | false |
| 尚未生成确认卡。 | false |
| 会准备确认卡。 | false |
| 如果确认卡已生成，请核对。 | false |
| 确认卡已真实生成吗？ | false |
| 未证实确认卡已真实生成。 | false |
| “确认卡已真实生成”是一个错误说法。 | false |
| 请解释“确认卡已真实生成”这句话。 | false |
| "确认卡已真实生成"是一个错误说法。 | false |

6. 行为测试至少分别用一个旧真阳性和一个流程说明反例验证模型调用轮数：实际0卡时真阳性只纠正一次；反例一次正常结束，不新增卡。保留原只查询、数据库卡数、已有卡不重复纠正、纠正轮合法准备但不自动提交的断言。
7. 保存修补前后同一组反例结果。纯AST报告可作为定位依据，最终以真实当前镜像的runner定向结果关闭；不改旧报告、不以当前模型能力评分代替。

## P4. 冻结输入与修正报告（R4）

1. 对生产源码、测试覆盖层、正在被加载的harness/runner、manifest、applicability/恢复清单、依赖输入/锁分别冻结清单及哈希。开始前和结束后均核对；不新增实时读取私有配置。
2. phase_complete必须同时要求：所有注册必需命令通过、证据完整、各类受检输入未变、dependency_lock_matches=true、required_dependencies_match=true。任何一项false均exit非零且明确原因。
3. 原子结果不依赖动态manifest写回。manifest只放静态注册条件，通过状态写run/summary/progress；保存run使用的安全manifest副本，使后续能审阅diff。
4. 用纯聚合判定负例证明harness/manifest/依赖不一致会拒绝；不要在正式验收运行中编辑真实harness。通过临时合成文件或隔离子进程fixture验证前后检查机制。
5. 当前manifest与旧run的差异如实记录，不追写旧run哈希。无旧文件可生成diff时，写明只有旧hash/缺快照；本补丁开始前保存当前外部文件的安全副本，之后每处改动提供真正文本diff。hash清单不能代替diff。
6. 更新m02-progress指向最后真实验收run，移除“待运行”作为当前状态的误导；旧记录作为历史保留。修正正式pytest、unittest、独立扫描的统计口径。
7. CP-00A-v1保留原文；用v2纠正其不准确指纹/计数说明，列明此次哪些输入重新验证、哪些未执行，不写“全部相同”掩盖变化。

## P5. 最终执行顺序、验收与停止

先完成P1/P2/P3/P4所需修改和定向失败修复，再停止编辑，运行：

```powershell
$RepoRoot = (Resolve-Path '.').Path
$V = 'E:/HuaKangOS-agent-validation/runtime-v1'
$VPython = "$V/.venv/Scripts/python.exe"
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M0.1
& $VPython "$V/run_validation.py" --repo "$RepoRoot" --milestone M0.2 --phase A
```

A阶段manifest必须包含：两个已审过的合同迁移测试、完整claim合同回归、本补丁配置节点与隔离负例、runner判定负例、匿名内存/迁移组及原离线R3T3脚本。最低数量由准确collection清单登记，不能通过降数字、skip或删测试求绿。

验收：

- [ ] R1全部反例拒绝，collect-only正确成功；所有必需节点都有完整终态，无skip冒充通过。
- [ ] R2准确节点的配置测试通过；未登记command/node/default、伪造环境名单、越界配置和外连都拒绝。
- [ ] R3上表及原句式回归全部通过，至少两类真实会话行为符合轮数与零业务写入要求。
- [ ] 严格自检和A定向都在当前输入下通过，A明确绑定该严格run；依赖/执行器漂移必失败。
- [ ] 当前证据含逐节点结果、实际diff、输入快照、源/测试/harness/依赖指纹及有效进程清理记录。
- [ ] 原业务权限/提示词/纠正轮数/SSE/迁移未改，真实模型0调用，无公司/预览数据访问。
- [ ] M0.2仍in_progress；门禁回awaiting_review，报告为CP-00A-v2；没有开始B或M0.3。

异常：允许范围内失败继续修复；确需扩大生产范围或根本改变合同则提前报告并停同一CP，不自加修复权限。外部依赖缺失如实记录blocked，不把“无需NTFS”解释为允许绕过隔离。

完成后保存docs/implementation-checkpoints/CP-00A-v2.md，并在计划当前项记录本补丁与run。**仍停CP-00A，等待用户再次审阅；本补丁没有下一批放行授权。**
