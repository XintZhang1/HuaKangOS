# CP-00A 审阅结论 v1

日期：2026-09-27。审阅对象：CP-00A-v1、当前生产diff、外部执行器/测试及两份最终run。审阅后计划版本：R2.1-20260927。

**结论：修复方向和产品范围保持正确，但本批暂不通过，CP-00A不放行。** 需要执行PATCH-CP-00A-01并提交CP-00A-v2。本次只写审阅/补丁/计划文档，没有代替DeepSeek修改生产或验证器。

## 已确认成立的部分

- 指定BASE-001句“第 7 批 4 张待确认卡已真实生成，请逐张核对后点击确认。”已能触发识别。
- 两项旧测试的文案迁移合理，保留了纠正次数、无卡及原行为断言，并加强数据库真实卡数核验。没有回退成强迫模型准备卡。
- 生产diff仅在service的文案识别区域；_conversation提示/轮数、业务提交、RBAC、迁移和SSE没有被修改。
- 辅助字面:memory:恢复真正内存语义，主库仍要求本run的合成标记文件，方向正确。
- 已核对最终run 20260927T093923Z-27f36d7a68和20260927T093938Z-cdcb3f18da：确实记录17、21、39、12项通过。没有把这些记录否定为“没运行”，但它们未覆盖下列缺陷。
- M0.2仍in_progress，CP-00A为awaiting_review，未发现启动M0.2.B/M0.3或后台继续执行的证据。

## 必须修正的问题

### R1 / P1：验证器仍可把不完整执行判为通过

位置：V/run_validation.py的verdict，约99—150行；harness/baseline_results.py的pytest_sessionfinish。

纯函数审阅探针已复现：

| 输入证据 | 当前结果 | 必需结果 |
|---|---|---|
| collected两项，只完成一项 | complete=true | 不完整，不通过 |
| 只有setup passed，没有call/teardown | complete=true | 不完整，不通过 |
| 必需脚本所有用例skipped | complete=true | 未验收，不通过 |
| timed_out=true，同时进程exit=0及成功报告 | complete=true，reason=timed_out | 超时无条件不通过 |

此外，baseline_collect实际写pytest-collection.json，verdict却读pytest-results.json并要求执行记录。正常collect-only无法作为成功收集证据；不能靠跳过collect解决。

影响：当前已通过的用例仍有效，但判定机制不能支持“完整套件已验收”的结论。补丁须核验节点集合、每个节点终态、退出码、跳过及超时，并分别处理collect/execute。

### R2 / P1：离线假配置例外作用于整个milestone，没有限定节点

位置：V/harness/isolation.py约305—331行；run_validation.py约279—282行；manifest的M0.2.offline_fake_config。

check_test_config没有使用传入metadata判断权限，也不验证当前command/node。探针设置未注册command、未注册node及metadata.offline_fake_config=false，仍可使用名单中的假key/model获得enabled=true例外。

另一个方向是validate_environment约291—295行无条件要求ALLOW_AI_EXTERNAL=false，不能明确支持计划要求的原配置测试节点：
tests/test_business_assistant.py::test_status_is_independent_and_test_config_isolated。
该测试需要在隔离环境中暂时切换字段，验证synthetic=false被产品拒绝、synthetic=true被接受。当前是否被harness打断取决于何时发生环境检查，不能只靠本轮没触发认为合同已实现。

**外网socket守卫仍在，这不是已发生真实模型调用或凭据泄漏。** 问题是测试权限过宽、合法配置测试又缺少精确例外。补丁只修测试环境，不改产品配置加载逻辑。

### R3 / P2：文本识别引入了新的误报和旧真阳性漏报

位置：app/business_assistant_service.py的CLAIM_MARK（约682行）、CLAIM_FILLER（约686行）、clause_is_affirmative（约709—712行）及claimed_actions。

HEAD与当前纯函数对比结果：

| 文案 | HEAD | 当前 | 应当 |
|---|---:|---:|---:|
| 实际生成确认卡前，请先补齐资料。 | false | true | false |
| 若实际生成确认卡，请逐张核对。 | false | true | false |
| 确认卡 已生成。 | true | false | true |
| 确认卡都已生成。 | true | false | true |
| 确认卡已生成，请问还需要其他帮助吗？ | true | false | true |
| 确认卡已生成，客户地址需要核对。 | true | false | true |

原因分别是把“实际/真实”单独作为完成标记、过窄的填充字符集合、用后半句的疑问/核对词否定前半句。零卡场景会发生不必要的纠正调用，或漏掉本来应纠正的虚假宣称。英文双引号引用也需纳入与中文引号一致的反例。

补丁保持狭窄句式识别；不引入全套自然语言解析，不改纠正轮权限和SSE。

### R4 / P2：受检输入完整性没有纳入最终判定，交接证据存在差异

位置：V/run_validation.py约258—261、285—328行；CP-00A-v1的指纹一致性说明。

- dependency_lock_matches、required_dependencies_match被计算但未参与phase_complete/status。
- 仅在开始记录harness_files，结束不重查正在被子进程加载的harness/manifest；仓库和镜像不变不能证明执行器不变。
- 审阅时生产service及312个overlay文件与最终run匹配，但validation-manifest.json已变化：run记录c8d61db4e9cd17dc0a2b46c3a264bad1b4456bf52048b89dc589faea91296f94，当前464fa83d933081054c09afdeaa9c5c1f8ce7252a3c8286a245ebe58acf25df5c。不能写“除两个文档外全部一致”。
- 外部harness修改表多处只链接hash清单，没有计划要求的可审阅diff；m02-progress仍指旧run/v2及phase_a_evidence_pending_run。
- 正式新增claim测试为14个参数句式+5个行为，加2个迁移用例共21项；独立22句扫描不是同一套计数，“22句式+6行为”的叙述应更正。

这不证明已有成功结果造假，但不足以作为下一批的可靠输入基线。补丁须冻结输入、将匹配条件纳入判定，并追加准确报告。

## 审阅方法与证据

V固定为E:/HuaKangOS-agent-validation/runtime-v1。

- review/CP-00A/claim-pure-ast-probe.json：HEAD/当前纯函数AST对比。
- review/CP-00A/review_verdict_probe.py及runner-verdict-probe/review-results.json：抽取counts/verdict，使用审阅目录中的合成JSON验证判定。
- review/CP-00A/probe_fake_config_review.py及同名.json：内存配置/元数据探针，无真实配置读取。
- review/CP-00A/review-state.json：审阅前代码哈希及当前manifest与run的差异。
- 原run和CP-00A-v1全部保留；审阅脚本不是正式业务验收，不计入17/21/39/12。

未运行完整基线、真实模型、数据库业务场景或浏览器。未修改业务代码、实际harness/overlay/manifest；仅新增仓库外审阅证据和本轮审阅文档。

## 对原报告三个问题的裁定

1. CP-00A暂不通过；SSE瞬时文字问题继续作为既有边界，**不扩大本补丁修复范围**。后续相关阶段另行审阅，不能宣称本次已消除。
2. 指定BASE-001文案已修好，但新增回归尚在；保留其历史定向证据，本批不能因此视为通过。修补后再形成新版关闭依据。
3. **不要求迁移到NTFS或另建验证根。** 本批负例可用纯判定测试和现有venv启动的受控子进程实现，不需要junction。需要真实隔离证明的项目仍由同一V的runner执行。

当前门禁保持awaiting_review，无下一批授权。补丁默认执行后仍停CP-00A，提交v2等待再审。
